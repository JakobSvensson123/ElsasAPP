import os
import re
import sys
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import pymupdf
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

LIST_URL = "https://eped.se/backup/eped/lists/7476950922805723811.html"
BASE_PDF_URL = "https://eped.se/backup/eped/"
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", ".cache_pdfs")
OUT_JSON = os.path.join(os.path.dirname(__file__), "..", "data", "eped_skane.json")
OUT_JS = os.path.join(os.path.dirname(__file__), "..", "data", "eped_skane_data.js")


def parse_swedish_float(s: str):
    if not s:
        return None
    s = s.strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def extract_route(title: str) -> str:
    t = title.lower()
    if "oralt" in t or "oral " in t or "tablett" in t or "kapsel" in t or "munhåle" in t or "sublingual" in t or "buckal" in t or "enteral" in t:
        return "Oralt"
    if "intravenös" in t or "iv " in t or "infusion" in t or "injektion" in t or "inj/inf" in t or "inf " in t or "inj " in t:
        if "subkutan" in t and "intravenös" not in t:
            return "Subkutant"
        if "intramuskulär" in t and "intravenös" not in t:
            return "Intramuskulärt"
        return "Intravenöst / Inj"
    if "rektal" in t or "suppositorium" in t or "lavemang" in t or "klysma" in t:
        return "Rektalt"
    if "inhalation" in t or "nebulisator" in t:
        return "Inhalation"
    if "intranasal" in t or "nässpray" in t or "näsdroppar" in t:
        return "Intranasalt"
    if "ögon" in t or "öron" in t:
        return "Ögon / Öron"
    if "kutan" in t or "kräm" in t or "salva" in t or "gel" in t or "plåster" in t or "topikal" in t or "schampo" in t:
        return "Kutant / Utvärtes"
    if "subkutan" in t:
        return "Subkutant"
    if "intramuskulär" in t:
        return "Intramuskulärt"
    return "Övrigt"


def extract_title_metadata(title: str):
    # Extract brand names inside parentheses e.g. (ex Alvedon, Panodil) or (Ziagen)
    brands = []
    for m in re.finditer(r"\(([^)]+)\)", title):
        inner = m.group(1)
        # Skip if it's purely numbers or technical words
        inner_clean = re.sub(r"^\b(ex|t\.ex\.|f\.d\.|alt\.?)\b\s*", "", inner, flags=re.IGNORECASE).strip()
        if inner_clean and not re.match(r"^\d", inner_clean):
            brands.append(inner_clean)

    # Extract substance (words before route keywords or numbers)
    route_words = r"\b(oralt|intravenös|intravenöst|rektalt|inhalation|subkutant|intramuskulärt|kutant|intranasalt|enteralt|topikalt|ögondroppar|örondroppar|inj|inf|tablett|kapsel)\b"
    m_sub = re.split(route_words, title, maxsplit=1, flags=re.IGNORECASE)
    substance = m_sub[0].strip() if m_sub else title.split()[0]
    substance = re.sub(r"\s+\d.*$", "", substance).strip()
    if not substance:
        substance = title.split()[0]

    # Concentration / Strength parsing from title
    # Examples:
    # "50 + 13 mg/mL" -> primary 50 mg/mL
    # "24 mg/mL" -> 24 mg/mL
    # "100 mikrog/mL" -> 100 mikrog/mL
    # "500 + 125 mg" -> 500 mg
    # "250 mg" -> 250 mg
    # "100 E/mL" -> 100 E/mL
    conc_val = None
    conc_unit = None
    conc_text = None
    is_liquid = False

    # Combo concentration like "50 + 13 mg/mL" or "80 + 12 mg/mL"
    m_combo_liq = re.search(r"(\d+(?:[.,]\d+)?)\s*\+\s*(\d+(?:[.,]\d+)?)\s*(mg|mikrog|g|gram|IE|E|mmol)/mL", title, re.IGNORECASE)
    if m_combo_liq:
        conc_val = parse_swedish_float(m_combo_liq.group(1))
        raw_u = m_combo_liq.group(3)
        conc_unit = normalize_mass_unit(raw_u) + "/mL"
        conc_text = m_combo_liq.group(0)
        is_liquid = True
    else:
        # Standard liquid concentration e.g. "24 mg/mL", "0,5 mg/mL", "100 mikrog/mL"
        m_liq = re.search(r"(\d+(?:[.,]\d+)?)\s*(mg|mikrog|µg|g|gram|IE|E|mmol|kE)/mL\b", title, re.IGNORECASE)
        if m_liq:
            conc_val = parse_swedish_float(m_liq.group(1))
            raw_u = m_liq.group(2)
            conc_unit = normalize_mass_unit(raw_u) + "/mL"
            conc_text = m_liq.group(0)
            is_liquid = True
        else:
            # Combo solid e.g. "500 + 125 mg"
            m_combo_sol = re.search(r"(\d+(?:[.,]\d+)?)\s*\+\s*(\d+(?:[.,]\d+)?)\s*(mg|mikrog|g|gram|IE|E|mmol)\b", title, re.IGNORECASE)
            if m_combo_sol:
                conc_val = parse_swedish_float(m_combo_sol.group(1))
                raw_u = m_combo_sol.group(3)
                conc_unit = normalize_mass_unit(raw_u)
                conc_text = m_combo_sol.group(0)
            else:
                # Standard solid / dose e.g. "250 mg", "100 mikrog/dos"
                m_sol = re.search(r"(\d+(?:[.,]\d+)?)\s*(mg|mikrog|µg|g|gram|IE|E|mmol)(?:/dos)?\b", title, re.IGNORECASE)
                if m_sol:
                    conc_val = parse_swedish_float(m_sol.group(1))
                    raw_u = m_sol.group(2)
                    conc_unit = normalize_mass_unit(raw_u)
                    conc_text = m_sol.group(0)

    return {
        "substance": substance,
        "brands": brands,
        "route": extract_route(title),
        "concValue": conc_val,
        "concUnit": conc_unit,
        "concText": conc_text,
        "isLiquid": is_liquid,
    }


def normalize_mass_unit(u: str) -> str:
    ul = u.lower().strip()
    if ul in ("mikrog", "µg", "ug", "mikrogram"):
        return "mikrog"
    if ul in ("g", "gram"):
        return "g"
    if ul in ("mg", "milligram"):
        return "mg"
    if ul in ("ie",):
        return "IE"
    if ul in ("e", "enh", "enheter"):
        return "E"
    if ul in ("mmol",):
        return "mmol"
    if ul in ("ml",):
        return "mL"
    return u


def clean_pdf_text(s: str) -> str:
    if not s:
        return ""
    # Remove private use area glyphs like arrows \uf0ea
    s = re.sub(r"[\uf000-\uf8ff]", "", s)
    s = s.replace("\u00a0", " ")
    return s.strip()


def parse_age_weight_bounds(text_str: str):
    t = (text_str or "").lower()
    min_age_m = None
    max_age_m = None
    min_wt = None
    max_wt = None

    # Weight bounds:
    m_wt_range = re.search(r"(\d+(?:[.,]\d+)?)\s*-\s*(\d+(?:[.,]\d+)?)\s*kg", t)
    if m_wt_range:
        min_wt = parse_swedish_float(m_wt_range.group(1))
        max_wt = parse_swedish_float(m_wt_range.group(2))
    else:
        m_under_w = re.search(r"(?:under|mindre\s+än|upp\s+till|<)\s*(\d+(?:[.,]\d+)?)\s*kg", t)
        if m_under_w:
            max_wt = parse_swedish_float(m_under_w.group(1))
        m_over_w = re.search(r"(?:från|över|>|minst)\s*(\d+(?:[.,]\d+)?)\s*kg", t)
        if m_over_w:
            min_wt = parse_swedish_float(m_over_w.group(1))

    # Age bounds:
    m_my = re.search(r"(\d+(?:[.,]\d+)?)\s*mån(?:ader)?\s*-\s*(\d+(?:[.,]\d+)?)\s*år", t)
    if m_my:
        min_age_m = parse_swedish_float(m_my.group(1))
        max_age_m = parse_swedish_float(m_my.group(2)) * 12.0
    else:
        m_mm = re.search(r"(\d+(?:[.,]\d+)?)\s*-\s*(\d+(?:[.,]\d+)?)\s*mån", t)
        if m_mm:
            min_age_m = parse_swedish_float(m_mm.group(1))
            max_age_m = parse_swedish_float(m_mm.group(2))
        else:
            m_yy = re.search(r"(\d+(?:[.,]\d+)?)\s*-\s*(\d+(?:[.,]\d+)?)\s*år", t)
            if m_yy:
                min_age_m = parse_swedish_float(m_yy.group(1)) * 12.0
                max_age_m = parse_swedish_float(m_yy.group(2)) * 12.0
            else:
                m_oy = re.search(r"(?:från|över)\s+(\d+(?:[.,]\d+)?)\s*(år|mån)", t)
                if m_oy:
                    val = parse_swedish_float(m_oy.group(1))
                    min_age_m = val * 12.0 if m_oy.group(2).startswith("år") else val
                    max_age_m = 216.0
                m_uy = re.search(r"(?:under|yngre\s+än)\s+(\d+(?:[.,]\d+)?)\s*(år|mån)", t)
                if m_uy:
                    val = parse_swedish_float(m_uy.group(1))
                    if min_age_m is None:
                        min_age_m = 0.0
                    max_age_m = val * 12.0 if m_uy.group(2).startswith("år") else val

    if min_age_m is None and max_age_m is None:
        if any(w in t for w in ("nyfödd", "prematur", "gestationsålder", "ga vecka", "från ga ", "postnatal ålder", "fullgångna")):
            min_age_m = 0.0
            max_age_m = 1.0

    return {
        "minAgeMonths": min_age_m,
        "maxAgeMonths": max_age_m,
        "minWeightKg": min_wt,
        "maxWeightKg": max_wt,
    }


def extract_regimens_from_lines(lines, indication_title=""):
    """
    Extract structured weight-based, Holliday-Segar, and max-capped dosing regimens from text lines under an indication.
    """
    regimens = []
    age_context = ""
    step_context = ""
    in_example_block = False

    age_header_re = re.compile(
        r"^(GA\s+vecka[^:]*|Från\s+GA\s+vecka[^:]*|Fullgångna[^:]*|Prematur[^:]*|Nyfödda[^:]*|Barn[^:]*|Ungdomar[^:]*|Vuxna[^:]*|Kroppsvikt[^:]*|Vikt[^:]*):?$",
        re.IGNORECASE,
    )
    step_header_re = re.compile(
        r"^(Laddningsdos|Underhållsdos[^:]*|Startdos[^:]*|Bolusdos[^:]*|Steg\s*\d+[^:]*|Dag\s*\d+[^:]*):?$",
        re.IGNORECASE,
    )

    cleaned_lines = []
    for raw_ln in lines:
        ln = clean_pdf_text(raw_ln)
        if ln:
            ln = re.sub(r"\s{3,}GA\s*=\s*Gestationsålder.*$", "", ln).strip()
            cleaned_lines.append(ln)

    # Check if this indication uses the Holliday and Segar maintenance fluid formula
    joined_text = " ".join(cleaned_lines)
    if re.search(r"Holliday\s+and\s+Segar|1000\s*mL\s*\+\s*50\s*mL/kg", joined_text, re.IGNORECASE):
        for ln in cleaned_lines:
            if re.search(r"Nyfödda.*?\d+\s*mL/kg", ln, re.IGNORECASE):
                m_neo = re.search(r"(\d+(?:[.,]\d+)?)\s*mL/kg(?:/(dygn|d|tim|t))?", ln, re.IGNORECASE)
                if m_neo:
                    val = parse_swedish_float(m_neo.group(1))
                    prefix = ln[:m_neo.start()].strip(" :,-|.") or "Nyfödda"
                    regimens.append({
                        "label": prefix,
                        "rawLine": ln,
                        "calcType": "standard",
                        "doseMin": val,
                        "doseMax": val,
                        "optLow": None,
                        "optHigh": None,
                        "unit": "mL/kg/dygn",
                        "massUnit": "mL",
                        "isPerDay": True,
                        "infusionTime": None,
                        "freqMin": None,
                        "freqMax": None,
                        "maxDoseVal": None,
                        "maxDoseUnit": None,
                        "maxDayVal": None,
                        "maxDayUnit": None,
                        "maxDosePerKg": None,
                        "maxDayPerKg": None,
                        "escMaxNote": None,
                        "minAgeMonths": 0.0,
                        "maxAgeMonths": 1.0,
                        "minWeightKg": None,
                        "maxWeightKg": 10.0,
                    })

        regimens.append({
            "label": "Barn 1 mån – 18 år (Holliday & Segar underhållsvätska)",
            "rawLine": "<10 kg: 100 mL/kg/dygn | 10–20 kg: 1000 mL + 50 mL/kg över 10 kg | >20 kg: 1500 mL + 20 mL/kg över 20 kg (flickor max 2000 mL/dygn, pojkar max 2500 mL/dygn)",
            "calcType": "holliday_segar",
            "doseMin": 100.0,
            "doseMax": 100.0,
            "optLow": None,
            "optHigh": None,
            "unit": "mL/dygn (Holliday-Segar)",
            "massUnit": "mL",
            "isPerDay": True,
            "infusionTime": None,
            "freqMin": None,
            "freqMax": None,
            "maxDoseVal": None,
            "maxDoseUnit": None,
            "maxDayVal": 2500.0,
            "maxDayUnit": "mL",
            "maxDayGirlVal": 2000.0,
            "maxDayBoyVal": 2500.0,
            "maxDosePerKg": None,
            "maxDayPerKg": None,
            "escMaxNote": None,
            "minAgeMonths": 1.0,
            "maxAgeMonths": 216.0,
            "minWeightKg": None,
            "maxWeightKg": None,
        })
        return regimens

    def parse_max_tokens(text_str):
        """Extract primary max dose / max daily dose / per-kg max / escalation note from a clause or line."""
        # Collapse spaces inside thousands numbers like "5 000 E" -> "5000 E"
        s = re.sub(r"(\d)\s+(\d{3})\b", r"\1\2", text_str)
        # Normalize "mg järn" -> "mg"
        s = re.sub(r"\b(mg|mikrog|µg|g|gram)\s+järn\b", r"\1", s, flags=re.IGNORECASE)

        m_dose_val, m_dose_unit = None, None
        m_day_val, m_day_unit = None, None
        m_dose_kg = None
        m_day_kg = None

        # 1. Per-kg max (e.g. "max 100 mg/kg/DYGN", "max 40 mikrog/kg per dygn", "max 5 mg/kg x 1")
        for mk in re.finditer(
            r"\bmax(?:dos|imalt|imal)?\b[^0-9]{0,25}?(\d+(?:[.,]\d+)?)(?:\s*-\s*(\d+(?:[.,]\d+)?))?\s*(mg|mikrog|µg|g|gram|IE|E|mmol|mL)/kg(?:\s*(?:/|per\s+)(dygn|d|tim|t|min|dos))?(?:\s*(?:x|×)\s*(\d+))?",
            s,
            re.IGNORECASE,
        ):
            v1 = parse_swedish_float(mk.group(1))
            v2 = parse_swedish_float(mk.group(2))
            val = v2 or v1
            scope = (mk.group(4) or "").lower()
            fx = int(mk.group(5)) if mk.group(5) else None
            if scope in ("dygn", "d"):
                m_day_kg = val
            elif fx:
                m_dose_kg = val
                m_day_kg = val * fx
            else:
                m_dose_kg = val

        # 2. Separate primary clause from escalation clause ("Vid behov kan dosen ökas till max 2 gram x 3")
        split_esc = re.split(
            r"(?:\.\s*|\b)(?:vid\s+behov\s+kan|kan\s+vid\s+behov|i\s+undantagsfall|vid\s+svårare|för\s+vissa\s+agens)",
            s,
            maxsplit=1,
            flags=re.IGNORECASE,
        )
        primary_part = split_esc[0]
        escalation_part = s[len(primary_part):].strip(" .,") if len(split_esc) > 1 else ""

        def extract_abs_max(sub_s):
            dv, du, dayv, dayu = None, None, None, None
            max_re = re.compile(
                r"(?:\bmax(?:dos|imal\s+dygnsdos|imalt|imal)?\b(?:\s*,\s*enligt\s+fass)?(?:\s+är)?(?:\s+vanligen)?(?:\s+totalt)?(?:\s+underhållsdos)?|\bupp\s+till\b)\s*:?\s*"
                r"(?:(\d+(?:[.,]\d+)?)\s*-\s*)?"
                r"(\d+(?:[.,]\d+)?)"
                r"(?:\s*\(\s*-\s*(\d+(?:[.,]\d+)?)\s*\))?"
                r"\s*(mg|mikrog|µg|g|gram|IE|E|mmol|mL)\b"
                r"(?:\s*(?:/|per\s+)(dos|dygn|d|tim|t|min|kg|m²|m2|\d+\s*tim))?"
                r"(?:\s*(?:x|×)\s*(\d+))?",
                re.IGNORECASE,
            )
            for mm in max_re.finditer(sub_s):
                if mm.group(0).lower().startswith("upp till") and "max" not in sub_s.lower():
                    continue
                scope = (mm.group(5) or "").lower().strip()
                if scope in ("kg", "m²", "m2"):
                    continue
                after_pos = mm.end()
                after_slice = sub_s[after_pos:after_pos + 5].lower().strip()
                if after_slice.startswith("/kg") or after_slice.startswith("/m"):
                    continue

                low_v = parse_swedish_float(mm.group(1))
                high_v = parse_swedish_float(mm.group(2))
                opt_v = parse_swedish_float(mm.group(3))
                val = opt_v or high_v or low_v
                if not val:
                    continue
                u = normalize_mass_unit(mm.group(4))
                freq_x = int(mm.group(6)) if mm.group(6) else None

                if scope in ("dygn", "d") or "dygnsdos" in mm.group(0).lower():
                    if dayv is None:
                        dayv, dayu = val, u
                elif freq_x and freq_x >= 1:
                    if dv is None:
                        dv, du = val, u
                    if dayv is None:
                        dayv, dayu = val * freq_x, u
                else:
                    if dv is None:
                        dv, du = val, u
            return dv, du, dayv, dayu

        m_dose_val, m_dose_unit, m_day_val, m_day_unit = extract_abs_max(primary_part)
        esc_dv, esc_du, esc_dayv, esc_dayu = extract_abs_max(escalation_part) if escalation_part else (None, None, None, None)

        # If there was NO primary max at all, but there was a max in escalation_part (e.g. "Vid behov kan dosen ökas till max 1 gram/DOS" as its own sentence)
        if m_dose_val is None and m_day_val is None and (esc_dv or esc_dayv) and not re.search(r"\bmax", primary_part, re.IGNORECASE):
            m_dose_val, m_dose_unit = esc_dv, esc_du
            m_day_val, m_day_unit = esc_dayv, esc_dayu
            esc_note = None
        else:
            esc_note = escalation_part if (esc_dv or esc_dayv) else None

        return m_dose_val, m_dose_unit, m_day_val, m_day_unit, m_dose_kg, m_day_kg, esc_note

    for line_c in cleaned_lines:
        if re.match(r"^Räkneexempel\b", line_c, re.IGNORECASE):
            in_example_block = True
            continue
        if in_example_block:
            if age_header_re.match(line_c) or step_header_re.match(line_c):
                in_example_block = False
            else:
                continue

        # Collapse thousands separator spaces for easier regex matching
        line_norm = re.sub(r"(\d)\s+(\d{3})\b", r"\1\2", line_c)
        line_norm = re.sub(r"\b(mg|mikrog|µg|g|gram)\s+järn\b", r"\1", line_norm, flags=re.IGNORECASE)

        has_dose_num = bool(re.search(r"\d+\s*(mg|mikrog|µg|g|gram|E|IE|mmol|mL)/kg", line_norm, re.IGNORECASE))

        # Check if a line with "/kg" is actually a pure standalone Max-cap line (e.g. "Maxdos 80 mg/kg/DYGN." or "Maxdos 40 mg/kg/DYGN eller 1,5 gram/DYGN" or "Max 60 mg/kg/DYGN, dock max 4 gram/DYGN")
        is_pure_max_line = bool(re.match(r"^(?:dock\s+)?(?:vanligen\s+)?max(?:dos|imalt|imal)?\b", line_norm.strip(), re.IGNORECASE))
        if is_pure_max_line and regimens:
            has_dose_num = False

        if not has_dose_num:
            if age_header_re.match(line_c):
                age_context = line_c.rstrip(":").strip()
                step_context = ""
                continue
            if step_header_re.match(line_c):
                step_context = line_c.rstrip(":").strip()
                continue
            if line_c.endswith(":") and "max" not in line_c.lower():
                step_context = line_c.rstrip(":").strip()
                continue

            # Case A: Weight-or-age conditional max line, e.g.
            # "Maxdos barn under 50 kg: 15 mg/DOS, 60 mg/DYGN" / "Maxdos barn från 50 kg: 30 mg/DOS, 90 mg/DYGN"
            m_cond_wt_max = re.search(
                r"max(?:dos)?\s+barn\s+(under|från|över)\s+(\d+(?:[.,]\d+)?)\s*kg\s*:\s*"
                r"(\d+(?:[.,]\d+)?)\s*(mg|mikrog|µg|g|gram|IE|E|mmol|mL)/(?:dos)\s*(?:,\s*(\d+(?:[.,]\d+)?)\s*(mg|mikrog|µg|g|gram|IE|E|mmol|mL)/(?:dygn|d))?",
                line_norm,
                re.IGNORECASE,
            )
            if m_cond_wt_max and regimens:
                cond_dir = m_cond_wt_max.group(1).lower()
                cond_wt = parse_swedish_float(m_cond_wt_max.group(2))
                c_dv = parse_swedish_float(m_cond_wt_max.group(3))
                c_du = normalize_mass_unit(m_cond_wt_max.group(4))
                c_dayv = parse_swedish_float(m_cond_wt_max.group(5)) if m_cond_wt_max.group(5) else None
                c_dayu = normalize_mass_unit(m_cond_wt_max.group(6)) if m_cond_wt_max.group(6) else None
                rule = {
                    "type": "under" if cond_dir == "under" else "from",
                    "weightKg": cond_wt,
                    "maxDoseVal": c_dv,
                    "maxDoseUnit": c_du,
                    "maxDayVal": c_dayv,
                    "maxDayUnit": c_dayu,
                }
                for prev_r in regimens:
                    prev_r.setdefault("weightMaxRules", []).append(rule)
                    if not prev_r["maxDoseVal"] or c_dv > prev_r["maxDoseVal"]:
                        prev_r["maxDoseVal"], prev_r["maxDoseUnit"] = c_dv, c_du
                    if c_dayv and (not prev_r["maxDayVal"] or c_dayv > prev_r["maxDayVal"]):
                        prev_r["maxDayVal"], prev_r["maxDayUnit"] = c_dayv, c_dayu
                continue

            # Case B: General standalone max line (e.g. "Max 20 GRAM", "Max 1,2 gram/DYGN", "Max 60 mg/kg/DYGN, dock max 4 gram/DYGN", "Maxdos, enligt FASS: 60 mg")
            if ("max" in line_norm.lower() or step_context.lower().startswith("max")) and "/m²" not in line_norm.lower() and regimens:
                md_v, md_u, mday_v, mday_u, md_kg, mday_kg, esc_n = parse_max_tokens(
                    ("Max " + line_norm) if not ("max" in line_norm.lower()) else line_norm
                )
                if md_v or mday_v or md_kg or mday_kg:
                    # Check if this line is age-scoped (e.g. "Barn 1 mån - 12 år: 2 gram/DYGN" under "Maxdos")
                    bounds = parse_age_weight_bounds(line_c)
                    if bounds["minAgeMonths"] is not None or bounds["maxAgeMonths"] is not None:
                        age_rule = {
                            "minAgeMonths": bounds["minAgeMonths"],
                            "maxAgeMonths": bounds["maxAgeMonths"],
                            "maxDoseVal": md_v,
                            "maxDoseUnit": md_u,
                            "maxDayVal": mday_v,
                            "maxDayUnit": mday_u,
                        }
                        for prev_r in regimens:
                            prev_r.setdefault("ageMaxRules", []).append(age_rule)

                    for prev_r in reversed(regimens):
                        if prev_r["isPerDay"] and md_v and not mday_v:
                            if not prev_r["maxDayVal"]:
                                prev_r["maxDayVal"], prev_r["maxDayUnit"] = md_v, md_u
                        else:
                            if md_v and not prev_r["maxDoseVal"]:
                                prev_r["maxDoseVal"], prev_r["maxDoseUnit"] = md_v, md_u
                            if mday_v and not prev_r["maxDayVal"]:
                                prev_r["maxDayVal"], prev_r["maxDayUnit"] = mday_v, mday_u
                        if md_kg and not prev_r.get("maxDosePerKg"):
                            prev_r["maxDosePerKg"] = md_kg
                        if mday_kg and not prev_r.get("maxDayPerKg"):
                            prev_r["maxDayPerKg"] = mday_kg
                    continue

            # Case C: Fixed dose for heavier/older children right after a weight-based regimen
            # e.g. "Barn över 12 år, eller från 50 kg: 400 mg x 1" or "Barn från 40 kg: 400 mg x 2"
            m_fixed_cap = re.search(
                r"^(?:Barn[^:]*?(?:från|över)\s+(\d+(?:[.,]\d+)?)\s*kg[^:]*|"
                r"(?:Från|Över)\s+(\d+(?:[.,]\d+)?)\s*kg[^:]*|"
                r"Barn\s+(?:1[23456]\s*-\s*18|över\s+12)\s*år[^:]*):\s*"
                r"(?:vanligen\s+|engångsdos\s+)?"
                r"(\d+(?:[.,]\d+)?)(?:\s*-\s*(\d+(?:[.,]\d+)?))?\s*(mg|mikrog|µg|g|gram|IE|E|mmol|mL)\b"
                r"(?:/(dygn|d|dos))?"
                r"(?:\s*(?:x|×)\s*(\d+)(?:\s*-\s*(\d+))?)?",
                line_norm,
                re.IGNORECASE,
            )
            if m_fixed_cap and regimens and "/m²" not in line_norm.lower():
                wt_thresh = parse_swedish_float(m_fixed_cap.group(1) or m_fixed_cap.group(2))
                fix_min = parse_swedish_float(m_fixed_cap.group(3))
                fix_max = parse_swedish_float(m_fixed_cap.group(4)) or fix_min
                fix_unit = normalize_mass_unit(m_fixed_cap.group(5))
                fix_per = (m_fixed_cap.group(6) or "").lower()
                fix_fmin = int(m_fixed_cap.group(7)) if m_fixed_cap.group(7) else None
                fix_fmax = int(m_fixed_cap.group(8)) if m_fixed_cap.group(8) else fix_fmin

                md_v, md_u, mday_v, mday_u, _, _, _ = parse_max_tokens(line_norm)

                for prev_r in regimens:
                    if prev_r["maxDoseVal"] or prev_r["maxDayVal"]:
                        continue
                    if fix_per in ("dygn", "d") or prev_r["isPerDay"]:
                        day_cap = mday_v or (fix_max * (fix_fmax or 1))
                        prev_r["maxDayVal"] = day_cap
                        prev_r["maxDayUnit"] = mday_u or fix_unit
                    else:
                        prev_r["maxDoseVal"] = md_v or fix_max
                        prev_r["maxDoseUnit"] = md_u or fix_unit
                        if mday_v:
                            prev_r["maxDayVal"] = mday_v
                            prev_r["maxDayUnit"] = mday_u
                        elif fix_fmax:
                            prev_r["maxDayVal"] = fix_max * fix_fmax
                            prev_r["maxDayUnit"] = fix_unit
                    if wt_thresh and not prev_r.get("maxWeightKg"):
                        prev_r["maxWeightKg"] = wt_thresh
                continue

        # Look for weight-based dosing patterns:
        pattern = re.compile(
            r"(?:\(\s*(\d+(?:[.,]\d+)?)\s*-\s*\)\s*)?"
            r"(\d+(?:[.,]\d+)?)"
            r"(?:\s*-\s*(\d+(?:[.,]\d+)?))?"
            r"(?:\s*\(\s*-\s*(\d+(?:[.,]\d+)?)\s*\))?"
            r"\s*(mg|mikrog|µg|g|gram|IE|E|mmol|mL)/kg"
            r"(?:/(dygn|d|tim|t|min|dos|\d+\s*tim))?"
            r"(?:\s*(?:x|×)\s*(\d+)(?:\s*-\s*(\d+))?(?:\s*\(\s*-\s*(\d+)\s*\))?)?",
            re.IGNORECASE,
        )

        matches = list(pattern.finditer(line_norm))
        # Filter out matches that are:
        # 1) Preceded by "max" (e.g. "max 5 mg/kg x 1" or "max 100 mg/kg/dygn")
        # 2) Inside prose ("jämfört med dosering 20 mg/kg", "överskrider 20 mg/kg")
        # 3) Equivalent unit conversions on the same line separated only by "=" or "(" (not "alt"/"eller")
        valid_matches = []
        for idx_m, m in enumerate(matches):
            before_slice = line_norm[max(0, m.start() - 25):m.start()].lower()
            if re.search(r"\bmax(?:dos|imalt|imal)?\b[^0-9]*$", before_slice):
                continue
            if re.search(r"(?:jämfört\s+med\s+dosering|överskrider|mer\s+än|inte\s+mer\s+än|upp\s+mot)\s*$", line_norm[:m.start()], re.IGNORECASE):
                continue
            if valid_matches:
                prev_m = valid_matches[-1]
                between = line_norm[prev_m.end():m.start()].strip()
                # If separated by "=" or "(" without "alt"/"eller", it's an equivalent unit representation of the same dose
                if (between.startswith("=") or "(" in between or "motsvara" in between.lower()) and not re.search(r"\b(?:alt|alternativt|eller)\b", between, re.IGNORECASE):
                    continue
            valid_matches.append(m)

        # Fallback: line-level max tokens if a clause doesn't have its own
        line_md_v, line_md_u, line_mday_v, line_mday_u, line_md_kg, line_mday_kg, line_esc = parse_max_tokens(line_norm)

        # Also check if the same line has a two-column fixed cap at the end like "Depåjärn: 15 mg/kg   500 mg"
        if not line_md_v and len(valid_matches) == 1:
            after_first = line_norm[valid_matches[0].end():]
            m_col_fix = re.search(r"^\s+(\d+(?:[.,]\d+)?)\s*(mg|mikrog|µg|g|gram|IE|E|mmol|mL)\s*$", after_first, re.IGNORECASE)
            if m_col_fix:
                line_md_v = parse_swedish_float(m_col_fix.group(1))
                line_md_u = normalize_mass_unit(m_col_fix.group(2))

        for idx_vm, m in enumerate(valid_matches):
            opt_low = parse_swedish_float(m.group(1))
            d_min = parse_swedish_float(m.group(2))
            d_max = parse_swedish_float(m.group(3)) or d_min
            opt_high = parse_swedish_float(m.group(4))
            unit = normalize_mass_unit(m.group(5))
            per_what = (m.group(6) or "").lower().strip()
            f_min = int(m.group(7)) if m.group(7) else None
            f_max = int(m.group(8)) if m.group(8) else (int(m.group(9)) if m.group(9) else f_min)

            if d_min is None:
                continue

            is_per_day = per_what in ("dygn", "d")
            infusion_time = None
            if per_what in ("tim", "t") or per_what.endswith("tim"):
                infusion_time = "tim" if per_what in ("tim", "t") else per_what
            elif per_what == "min":
                infusion_time = "min"

            if is_per_day and not f_min:
                m_div = re.search(r"(?:fördelat|uppdelat)\s+(?:på|i)\s+(\d+)(?:\s*-\s*(\d+))?\s*(?:doser|tillfällen|gånger)", line_norm, re.IGNORECASE)
                if m_div:
                    f_min = int(m_div.group(1))
                    f_max = int(m_div.group(2)) if m_div.group(2) else f_min

            # Determine clause slice for this specific match
            clause_end = valid_matches[idx_vm + 1].start() if idx_vm + 1 < len(valid_matches) else len(line_norm)
            clause_str = line_norm[m.start():clause_end]
            c_md_v, c_md_u, c_mday_v, c_mday_u, c_md_kg, c_mday_kg, c_esc = parse_max_tokens(clause_str)

            max_dose_val = c_md_v if c_md_v is not None else line_md_v
            max_dose_unit = c_md_u if c_md_v is not None else line_md_u
            max_day_val = c_mday_v if c_mday_v is not None else line_mday_v
            max_day_unit = c_mday_u if c_mday_v is not None else line_mday_u
            max_dose_kg = c_md_kg if c_md_kg is not None else line_md_kg
            max_day_kg = c_mday_kg if c_mday_kg is not None else line_mday_kg
            esc_note = c_esc or line_esc

            # If this is a per-day regimen and the clause said "max 600 mg" without "/dygn", treat it as maxDayVal
            if is_per_day and max_dose_val and not max_day_val and not f_min:
                max_day_val, max_day_unit = max_dose_val, max_dose_unit
                max_dose_val, max_dose_unit = None, None

            prefix_start = valid_matches[idx_vm - 1].end() if idx_vm > 0 else 0
            prefix = line_norm[prefix_start:m.start()].strip(" :,-|.")
            if idx_vm > 0:
                # Clean trailing "max ..." from previous clause if this is a second regimen on the same line
                prefix = re.sub(r"^.*?\b(?:alt\.?|alternativt|eller)\b\s*", "Alternativt ", prefix, flags=re.IGNORECASE).strip(" :,-|.")
            if prefix.lower() in ("alt", "alt.", "alternativt", "eller"):
                prefix = "Alternativt"

            parts = []
            if age_context and (not prefix or age_context.lower() not in prefix.lower()):
                parts.append(age_context)
            if step_context and (not prefix or step_context.lower() not in prefix.lower()):
                parts.append(step_context)
            if prefix:
                parts.append(prefix)

            label = " • ".join(parts) if parts else (indication_title or "Standarddos")
            bounds = parse_age_weight_bounds(f"{label} {line_norm}")

            regimens.append({
                "label": label,
                "rawLine": line_c,
                "calcType": "standard",
                "doseMin": d_min,
                "doseMax": d_max,
                "optLow": opt_low,
                "optHigh": opt_high,
                "unit": f"{unit}/kg" + (f"/{infusion_time}" if infusion_time else ("/dygn" if is_per_day else "")),
                "massUnit": unit,
                "isPerDay": is_per_day,
                "infusionTime": infusion_time,
                "freqMin": f_min,
                "freqMax": f_max,
                "maxDoseVal": max_dose_val,
                "maxDoseUnit": max_dose_unit,
                "maxDayVal": max_day_val,
                "maxDayUnit": max_day_unit,
                "maxDosePerKg": max_dose_kg,
                "maxDayPerKg": max_day_kg,
                "escMaxNote": esc_note,
                "minAgeMonths": bounds["minAgeMonths"],
                "maxAgeMonths": bounds["maxAgeMonths"],
                "minWeightKg": bounds["minWeightKg"],
                "maxWeightKg": bounds["maxWeightKg"],
            })

    # Post-pass: if a later regimen in the same indication has a maxDoseVal/maxDayVal and earlier ones (e.g. Nyfödda / yngre barn)
    # have the exact same or lower dose rate without a cap, propagate the cap so a 60 kg weight never exceeds adult max dose on any row.
    if len(regimens) > 1:
        known_max_dose = next(((r["maxDoseVal"], r["maxDoseUnit"]) for r in regimens if r.get("maxDoseVal")), (None, None))
        known_max_day = next(((r["maxDayVal"], r["maxDayUnit"]) for r in regimens if r.get("maxDayVal")), (None, None))
        for r in regimens:
            if not r.get("maxDoseVal") and not r.get("maxDayVal"):
                if known_max_dose[0]:
                    r["maxDoseVal"], r["maxDoseUnit"] = known_max_dose
                if known_max_day[0]:
                    r["maxDayVal"], r["maxDayUnit"] = known_max_day

    return regimens


def get_visual_words(page):
    rot = page.rotation
    H = page.mediabox.height
    W = page.mediabox.width
    raw_words = page.get_text("words")
    if rot == 90:
        return [(H - w[3], w[0], H - w[1], w[2], w[4], w[5], w[6], w[7]) for w in raw_words]
    elif rot == 270:
        return [(w[1], W - w[2], w[3], W - w[0], w[4], w[5], w[6], w[7]) for w in raw_words]
    return raw_words


def get_visual_blocks(page):
    rot = page.rotation
    H = page.mediabox.height
    W = page.mediabox.width
    raw_blocks = page.get_text("blocks")
    if rot == 90:
        return [(H - b[3], b[0], H - b[1], b[2], b[4], b[5], b[6]) for b in raw_blocks]
    elif rot == 270:
        return [(b[1], W - b[2], b[3], W - b[0], b[4], b[5], b[6]) for b in raw_blocks]
    return raw_blocks


def parse_rimlig_dos_table(doc):
    """
    Locate 'RIMLIG DOS' on any page of the PDF and reconstruct the exact weight table.
    """
    for page in doc:
        words = get_visual_words(page)
        rimlig_words = [w for w in words if "RIMLIG" in w[4] and w[0] < 410]
        if not rimlig_words:
            continue

        ry = rimlig_words[0][1]
        # Find where the next section starts (e.g. HÅLLBARHET or ePedID footer)
        stop_y = 525
        for w in words:
            if w[0] < 100 and w[1] > ry + 15 and w[4] in ("HÅLLBARHET", "ARBETSMILJÖ", "ePedID:"):
                stop_y = min(stop_y, w[1] - 4)

        table_words = [w for w in words if w[0] < 415 and ry <= w[1] <= stop_y]
        # Group into horizontal lines by y0 (tolerance 5pt)
        lines_by_y = []
        for w in sorted(table_words, key=lambda x: (x[1], x[0])):
            placed = False
            for grp in lines_by_y:
                if abs(grp["y"] - w[1]) <= 5.5:
                    grp["words"].append(w)
                    placed = True
                    break
            if not placed:
                lines_by_y.append({"y": w[1], "words": [w]})

        header_title = ""
        rows = []
        note_lines = []

        for idx, grp in enumerate(lines_by_y):
            ws = sorted(grp["words"], key=lambda x: x[0])
            full_line = clean_pdf_text(" ".join(w[4] for w in ws))
            if idx == 0 and "RIMLIG" in full_line:
                header_title = full_line
                continue
            if re.search(r"\b1\s*kg\b.*\b5\s*kg\b", full_line):
                continue

            # Partition words by column x-coordinate:
            # Col 0 (label): x < 162
            # Col 1 (1 kg): 162 <= x < 226
            # Col 2 (5 kg): 226 <= x < 292
            # Col 3 (10 kg): 292 <= x < 354
            # Col 4 (50 kg): x >= 354
            c0 = clean_pdf_text(" ".join(w[4] for w in ws if w[0] < 162))
            c1 = clean_pdf_text(" ".join(w[4] for w in ws if 162 <= w[0] < 226))
            c5 = clean_pdf_text(" ".join(w[4] for w in ws if 226 <= w[0] < 292))
            c10 = clean_pdf_text(" ".join(w[4] for w in ws if 292 <= w[0] < 354))
            c50 = clean_pdf_text(" ".join(w[4] for w in ws if w[0] >= 354))

            if c0 and (c1 or c5 or c10 or c50):
                # Parse rate if c0 is like "10 mg/kg" or "0,5 mikrog/kg"
                rate_val = None
                rate_unit = None
                max_val = None
                max_unit = None
                m_rate = re.search(r"(\d+(?:[.,]\d+)?)\s*(mg|mikrog|µg|g|gram|IE|E|mmol)/kg(?:/(tim|min|dygn))?", c0, re.IGNORECASE)
                if m_rate:
                    rate_val = parse_swedish_float(m_rate.group(1))
                    rate_unit = normalize_mass_unit(m_rate.group(2)) + "/kg" + (f"/{m_rate.group(3).lower()}" if m_rate.group(3) else "")

                m_max_r = re.search(r"max\s*,?\s*(\d+(?:[.,]\d+)?)\s*(mg|mikrog|µg|g|gram|IE|E|mmol)\b", c0, re.IGNORECASE)
                if m_max_r:
                    max_val = parse_swedish_float(m_max_r.group(1))
                    max_unit = normalize_mass_unit(m_max_r.group(2))

                rows.append({
                    "label": c0,
                    "rateVal": rate_val,
                    "rateUnit": rate_unit,
                    "maxVal": max_val,
                    "maxUnit": max_unit,
                    "kg1": c1 or "-",
                    "kg5": c5 or "-",
                    "kg10": c10 or "-",
                    "kg50": c50 or "-",
                })
            elif full_line:
                note_lines.append(full_line)

        if rows:
            # If the table has a single fixed/max row at the bottom (e.g. "400 mg" or "max 400 mg" for 50 kg)
            # and rate rows above have "-" in kg50, associate that cap with those rate rows
            fixed_cap_rows = []
            for r in rows:
                if r["rateVal"] is None and r["kg50"] != "-" and r["kg1"] == "-" and r["kg5"] == "-":
                    m_fc = re.search(r"(?:max\s*,?\s*)?(\d+(?:[.,]\d+)?)\s*(mg|mikrog|µg|g|gram|IE|E|mmol)\b(?!\s*/\s*m)", r["label"], re.IGNORECASE)
                    if m_fc:
                        fixed_cap_rows.append((parse_swedish_float(m_fc.group(1)), normalize_mass_unit(m_fc.group(2))))

            if len(fixed_cap_rows) == 1:
                fc_val, fc_unit = fixed_cap_rows[0]
                for r in rows:
                    if r["rateVal"] is not None and not r.get("maxVal") and r["kg50"] == "-":
                        r["maxVal"] = fc_val
                        r["maxUnit"] = fc_unit

            return {
                "title": header_title,
                "rows": rows,
                "note": " ".join(note_lines).strip(),
            }
    return None


def parse_single_pdf(item):
    title, pdf_url, date_str, filename = item
    cache_path = os.path.join(CACHE_DIR, filename)
    try:
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 500:
            with open(cache_path, "rb") as f:
                pdf_bytes = f.read()
        else:
            r = requests.get(pdf_url, timeout=20)
            r.raise_for_status()
            pdf_bytes = r.content
            with open(cache_path, "wb") as f:
                f.write(pdf_bytes)

        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        meta = extract_title_metadata(title)
        return {
            "id": filename.replace(".pdf", ""),
            "title": title,
            "date": date_str,
            "pdfUrl": pdf_url,
            **meta,
            "indications": [],
            "rimligDos": None,
            "warnings": [],
            "appliesTo": "",
            "dilution": "",
            "administration": "",
            "stability": "",
            "otherInfo": "",
            "error": str(e),
        }

    meta = extract_title_metadata(title)
    rimlig_dos = parse_rimlig_dos_table(doc)

    # Check if rimlig_dos title or note clarifies concentration (e.g. "Doserna ovan avser AMOXICILLIN, 50 mg/mL")
    if rimlig_dos:
        for txt_check in (rimlig_dos.get("note", ""), rimlig_dos.get("title", "")):
            m_c = re.search(r"(\d+(?:[.,]\d+)?)\s*(mg|mikrog|µg|g|gram|IE|E|mmol)/mL", txt_check, re.IGNORECASE)
            if m_c and not meta["concValue"]:
                meta["concValue"] = parse_swedish_float(m_c.group(1))
                meta["concUnit"] = normalize_mass_unit(m_c.group(2)) + "/mL"
                meta["concText"] = m_c.group(0)
                meta["isLiquid"] = True

    warnings = []
    applies_to = []
    dilution = []
    administration = []
    stability = []
    other_info = []
    indications = []
    current_indication = None

    left_section = "TOP"
    right_section = "TOP"

    for page_idx, page in enumerate(doc):
        blocks = get_visual_blocks(page)
        left_blocks = sorted([b for b in blocks if b[0] < 410], key=lambda x: (round(x[1] / 5), x[0]))
        right_blocks = sorted([b for b in blocks if b[0] >= 410], key=lambda x: (round(x[1] / 5), x[0]))

        # Parse Left Column
        for b in left_blocks:
            x0, y0, x1, y1, raw_txt = b[0], b[1], b[2], b[3], b[4]
            txt = clean_pdf_text(raw_txt)
            if not txt:
                continue
            if y0 < 82 or y0 > 525:
                continue
            if txt.startswith("BARNLÄKEMEDELSINSTRUKTION") or txt.startswith("ePedID:") or "Versionshantering:" in txt:
                continue

            # Detect Left Column Section Headers
            upper_t = txt.upper()
            if "INSTRUKTIONEN GÄLLER FÖR" in upper_t:
                left_section = "APPLIES"
                continue
            elif any(h in upper_t for h in ("INGEN SPÄDNING", "EN-STEGSSPÄDNING", "TVÅ-STEGSSPÄDNING", "FLER-STEGSSPÄDNING", "SPÄDNING")):
                left_section = "DILUTION"
                dilution.append(txt.replace("\n", " "))
                continue
            elif upper_t.startswith("ARBETSMILJÖ"):
                left_section = "WORK_ENV"
                continue
            elif upper_t.startswith("ADMINISTRERING"):
                left_section = "ADMIN"
                continue
            elif upper_t.startswith("RIMLIG DOS"):
                left_section = "RIMLIG"
                continue
            elif upper_t.startswith("HÅLLBARHET OCH FÖRVARING"):
                left_section = "STABILITY"
                continue

            flat_txt = re.sub(r"\s*\n\s*", " ", txt)
            if left_section == "TOP" and page_idx == 0:
                warnings.append(flat_txt)
            elif left_section == "APPLIES":
                applies_to.append(flat_txt)
            elif left_section == "DILUTION":
                dilution.append(flat_txt)
            elif left_section == "ADMIN":
                administration.append(flat_txt)
            elif left_section == "STABILITY":
                stability.append(flat_txt)

        # Parse Right Column
        for b in right_blocks:
            x0, y0, x1, y1, raw_txt = b[0], b[1], b[2], b[3], b[4]
            txt = clean_pdf_text(raw_txt)
            if not txt:
                continue
            if y0 < 85 or y0 > 525:
                continue
            if txt.startswith("ePedID:") or "KONTROLLERA ATT UTSKRIVEN" in txt or "Fastställare/läkare" in txt or "Lokal kontakt:" in txt:
                continue

            upper_t = txt.upper()
            if "VANLIG INDIKATION OCH DOS" in upper_t:
                right_section = "INDICATIONS"
                continue
            elif upper_t.startswith("ÖVRIG INFORMATION"):
                right_section = "OTHER"
                continue
            elif upper_t.startswith("REFERENS/LÄNK") or upper_t.startswith("LOKAL LÄNK"):
                right_section = "REF"
                continue

            if right_section == "INDICATIONS":
                # In ePed PDFs, indication headers sit at x0 ~ 458..470, while body lines sit at x0 ~ 478..485
                lines_in_block = [clean_pdf_text(ln) for ln in raw_txt.split("\n") if clean_pdf_text(ln)]
                if x0 < 473:
                    ind_title = " ".join(lines_in_block)
                    # If the previous indication has no lines yet, merge multi-line indication titles
                    if current_indication and len(current_indication["lines"]) == 0:
                        current_indication["title"] += " / " + ind_title
                    elif current_indication and current_indication["title"].lower() == ind_title.lower():
                        # Repeated indication header on a continuation page
                        pass
                    else:
                        current_indication = {
                            "title": ind_title,
                            "lines": [],
                        }
                        indications.append(current_indication)
                else:
                    if current_indication is None:
                        current_indication = {
                            "title": "Allmän dosering / Kommentar",
                            "lines": [],
                        }
                        indications.append(current_indication)
                    current_indication["lines"].extend(lines_in_block)

            elif right_section == "OTHER":
                flat_txt = re.sub(r"\s*\n\s*", " ", txt)
                other_info.append(flat_txt)

    # Extract structured regimens for each indication
    for ind in indications:
        ind["regimens"] = extract_regimens_from_lines(ind["lines"], ind["title"])

    # Also check if any line in indications specifies concentration (e.g. "slutkoncentration 50 mg/mL")
    # Only do this if the title is not explicitly a solid dosage form (tablets/capsules/suppositories)
    t_lower = title.lower()
    is_solid_title = any(w in t_lower for w in ("tablett", "kapsel", "kapslar", "suppositorium", "plåster", "pulver", "granulat")) and not any(
        w in t_lower for w in ("suspension", "lösning", "inf", "inj", "mixtur", "droppar", "klysma", "lavemang", "vatten")
    )
    meta["solidStrengths"] = []
    if not meta["concValue"]:
        if is_solid_title:
            # Find all solid strengths in applies_to lines that describe the solid form
            sol_items = []
            seen_sol = set()
            for app_ln in applies_to:
                if "/ml" in app_ln.lower() or "suspension" in app_ln.lower() or "lösning" in app_ln.lower():
                    continue
                if any(w in app_ln.lower() for w in ("tablett", "kapsel", "kapslar", "suppositorium", "granulat", "pulver", "plåster")):
                    for ms in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(mg|mikrog|µg|g|gram|IE|E)\b(?!\s*/)", app_ln, re.IGNORECASE):
                        sv = parse_swedish_float(ms.group(1))
                        su = normalize_mass_unit(ms.group(2))
                        if sv and (sv, su) not in seen_sol:
                            seen_sol.add((sv, su))
                            sol_items.append({"val": sv, "unit": su, "text": f"{ms.group(1)} {su}"})
            if len(sol_items) == 1:
                meta["concValue"] = sol_items[0]["val"]
                meta["concUnit"] = sol_items[0]["unit"]
                meta["concText"] = sol_items[0]["text"]
                meta["isLiquid"] = False
                meta["solidStrengths"] = sol_items
            elif len(sol_items) > 1:
                meta["concText"] = " / ".join(x["text"] for x in sol_items)
                meta["isLiquid"] = False
                meta["solidStrengths"] = sol_items
        else:
            all_ind_text = " ".join(" ".join(i["lines"]) for i in indications) + " " + " ".join(applies_to)
            m_c = re.search(r"(\d+(?:[.,]\d+)?)\s*(mg|mikrog|µg|g|gram|IE|E|mmol)/mL", all_ind_text, re.IGNORECASE)
            if m_c:
                meta["concValue"] = parse_swedish_float(m_c.group(1))
                meta["concUnit"] = normalize_mass_unit(m_c.group(2)) + "/mL"
                meta["concText"] = m_c.group(0)
                meta["isLiquid"] = True

    doc.close()

    return {
        "id": filename.replace(".pdf", ""),
        "epedId": filename.split("_")[0],
        "title": title,
        "date": date_str,
        "pdfUrl": pdf_url,
        **meta,
        "warnings": warnings,
        "appliesTo": "\n".join(applies_to),
        "dilution": "\n".join(dilution),
        "administration": "\n".join(administration),
        "stability": "\n".join(stability),
        "otherInfo": "\n".join(other_info),
        "rimligDos": rimlig_dos,
        "indications": indications,
    }


def main():
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)

    print("Fetching Region Skåne ePed list...")
    resp = requests.get(LIST_URL, timeout=20)
    resp.encoding = "utf-8"
    soup = BeautifulSoup(resp.text, "html.parser")

    items = []
    for tr in soup.find_all("tr"):
        a = tr.find("a")
        tds = tr.find_all("td")
        if a and a.get("href", "").endswith(".pdf"):
            href = a["href"]
            filename = href.split("/")[-1]
            pdf_url = BASE_PDF_URL + filename
            title = clean_pdf_text(a.get_text(" ", strip=True))
            date_str = clean_pdf_text(tds[-1].get_text(strip=True)) if len(tds) >= 3 else ""
            items.append((title, pdf_url, date_str, filename))

    print(f"Found {len(items)} PDF instructions for Region Skåne. Downloading & parsing with 24 threads...")
    t0 = time.time()
    results = [None] * len(items)

    with ThreadPoolExecutor(max_workers=24) as ex:
        fut_to_idx = {ex.submit(parse_single_pdf, item): idx for idx, item in enumerate(items)}
        done_count = 0
        for fut in as_completed(fut_to_idx):
            idx = fut_to_idx[fut]
            results[idx] = fut.result()
            done_count += 1
            if done_count % 100 == 0 or done_count == len(items):
                print(f"  Processed {done_count}/{len(items)} PDFs ({time.time() - t0:.1f}s)")

    payload = {
        "region": "Region Skåne",
        "sourceListUrl": LIST_URL,
        "generatedAt": time.strftime("%Y-%m-%d %H:%M"),
        "count": len(results),
        "medications": results,
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    with open(OUT_JS, "w", encoding="utf-8") as f:
        f.write("window.EPED_SKANE_DATA = ")
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    size_mb = os.path.getsize(OUT_JSON) / (1024 * 1024)
    with_rimlig = sum(1 for r in results if r.get("rimligDos"))
    with_ind = sum(1 for r in results if r.get("indications"))
    print(f"Done! Saved {len(results)} medications ({size_mb:.2f} MB). With Rimlig Dos: {with_rimlig}, With Indications: {with_ind}")


if __name__ == "__main__":
    main()

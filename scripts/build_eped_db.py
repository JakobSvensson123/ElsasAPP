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


def extract_regimens_from_lines(lines, indication_title=""):
    """
    Extract structured weight-based and fixed dosing regimens from text lines under an indication.
    """
    regimens = []
    age_context = ""
    step_context = ""

    age_header_re = re.compile(
        r"^(GA\s+vecka[^:]*|Från\s+GA\s+vecka[^:]*|Fullgångna[^:]*|Prematur[^:]*|Nyfödda[^:]*|Barn[^:]*|Ungdomar[^:]*|Vuxna[^:]*|Kroppsvikt[^:]*|Vikt[^:]*):?$",
        re.IGNORECASE,
    )
    step_header_re = re.compile(
        r"^(Laddningsdos|Underhållsdos[^:]*|Startdos[^:]*|Bolusdos[^:]*|Steg\s*\d+[^:]*|Dag\s*\d+[^:]*):?$",
        re.IGNORECASE,
    )

    for line in lines:
        line_c = clean_pdf_text(line)
        if not line_c:
            continue
        # Strip trailing "GA = Gestationsålder" column note if present on same line
        line_c = re.sub(r"\s{3,}GA\s*=\s*Gestationsålder.*$", "", line_c).strip()

        has_dose_num = bool(re.search(r"\d+\s*(mg|mikrog|µg|g|gram|E|IE|mmol|mL)/kg", line_c, re.IGNORECASE))

        if not has_dose_num:
            if age_header_re.match(line_c):
                age_context = line_c.rstrip(":").strip()
                step_context = ""
                continue
            if step_header_re.match(line_c):
                step_context = line_c.rstrip(":").strip()
                continue
            if line_c.endswith(":"):
                step_context = line_c.rstrip(":").strip()
                continue

        # Look for weight-based dosing patterns:
        pattern = re.compile(
            r"(?:\(\s*(\d+(?:[.,]\d+)?)\s*-\s*\)\s*)?"
            r"(\d+(?:[.,]\d+)?)"
            r"(?:\s*-\s*(\d+(?:[.,]\d+)?))?"
            r"(?:\s*\(\s*-\s*(\d+(?:[.,]\d+)?)\s*\))?"
            r"\s*(mg|mikrog|µg|g|gram|IE|E|mmol|mL)/kg"
            r"(?:/(dygn|d|tim|t|min|dos))?"
            r"(?:\s*(?:x|×)\s*(\d+)(?:\s*-\s*(\d+))?(?:\s*\(\s*-\s*(\d+)\s*\))?)?",
            re.IGNORECASE,
        )

        for m in pattern.finditer(line_c):
            opt_low = parse_swedish_float(m.group(1))
            d_min = parse_swedish_float(m.group(2))
            d_max = parse_swedish_float(m.group(3)) or d_min
            opt_high = parse_swedish_float(m.group(4))
            unit = normalize_mass_unit(m.group(5))
            per_what = (m.group(6) or "").lower()
            f_min = int(m.group(7)) if m.group(7) else None
            f_max = int(m.group(8)) if m.group(8) else (int(m.group(9)) if m.group(9) else f_min)

            if d_min is None:
                continue

            is_per_day = per_what in ("dygn", "d")
            infusion_time = None
            if per_what in ("tim", "t"):
                infusion_time = "tim"
            elif per_what == "min":
                infusion_time = "min"

            if is_per_day and not f_min:
                m_div = re.search(r"fördelat\s+på\s+(\d+)(?:\s*-\s*(\d+))?\s*(?:doser|tillfällen|gånger)", line_c, re.IGNORECASE)
                if m_div:
                    f_min = int(m_div.group(1))
                    f_max = int(m_div.group(2)) if m_div.group(2) else f_min

            max_dose_val, max_dose_unit = None, None
            max_day_val, max_day_unit = None, None
            max_day_kg = None

            m_max_kg = re.search(r"max\s+(\d+(?:[.,]\d+)?)\s*(mg|mikrog|g|gram|IE|E|mmol)/kg/(?:dygn|d)\b", line_c, re.IGNORECASE)
            if m_max_kg:
                max_day_kg = parse_swedish_float(m_max_kg.group(1))

            for m_max in re.finditer(r"max\s+(\d+(?:[.,]\d+)?)\s*(mg|mikrog|g|gram|IE|E|mmol)(?:/(dos|dygn|d|kg))?", line_c, re.IGNORECASE):
                val = parse_swedish_float(m_max.group(1))
                u = normalize_mass_unit(m_max.group(2))
                scope = (m_max.group(3) or "").lower()
                if scope == "kg":
                    continue
                if scope in ("dygn", "d"):
                    max_day_val, max_day_unit = val, u
                else:
                    max_dose_val, max_dose_unit = val, u

            prefix = line_c[:m.start()].strip(" :,-|.")
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

            regimens.append({
                "label": label,
                "rawLine": line_c,
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
                "maxDayPerKg": max_day_kg,
            })

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
                m_rate = re.search(r"(\d+(?:[.,]\d+)?)\s*(mg|mikrog|µg|g|gram|IE|E|mmol)/kg(?:/(tim|min|dygn))?", c0, re.IGNORECASE)
                if m_rate:
                    rate_val = parse_swedish_float(m_rate.group(1))
                    rate_unit = normalize_mass_unit(m_rate.group(2)) + "/kg" + (f"/{m_rate.group(3).lower()}" if m_rate.group(3) else "")

                rows.append({
                    "label": c0,
                    "rateVal": rate_val,
                    "rateUnit": rate_unit,
                    "kg1": c1 or "-",
                    "kg5": c5 or "-",
                    "kg10": c10 or "-",
                    "kg50": c50 or "-",
                })
            elif full_line:
                note_lines.append(full_line)

        if rows:
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
    if not meta["concValue"]:
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

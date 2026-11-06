(function () {
  'use strict';

  const DATA = window.EPED_SKANE_DATA || { medications: [], count: 0 };
  const MEDS = DATA.medications || [];

  // Application State
  const state = {
    weightKg: parseFloat(localStorage.getItem('elsa_eped_weight') || '12') || 12,
    searchQuery: '',
    routeFilter: 'ALL',
    selectedMedId: null,
    activeCalcTab: 'indications',
    favorites: new Set(JSON.parse(localStorage.getItem('elsa_eped_favs') || '[]')),
    deferredInstallPrompt: null,
  };

  // DOM Elements
  const headerStats = document.getElementById('headerStats');
  const childWeightInput = document.getElementById('childWeightInput');
  const weightMinusBtn = document.getElementById('weightMinusBtn');
  const weightPlusBtn = document.getElementById('weightPlusBtn');
  const activeWeightBadge = document.getElementById('activeWeightBadge');
  const weightChips = document.querySelectorAll('.weight-chip');

  const medSearchInput = document.getElementById('medSearchInput');
  const clearSearchBtn = document.getElementById('clearSearchBtn');
  const routeFilterBtns = document.querySelectorAll('.filter-pill');
  const listCountText = document.getElementById('listCountText');
  const medListContainer = document.getElementById('medListContainer');

  const emptyDetailState = document.getElementById('emptyDetailState');
  const medDetailContent = document.getElementById('medDetailContent');
  const backToListBtn = document.getElementById('backToListBtn');
  const homeLogoBtn = document.getElementById('homeLogoBtn');
  const mobileQuickPdfBtn = document.getElementById('mobileQuickPdfBtn');

  const detailBadges = document.getElementById('detailBadges');
  const toggleFavDetailBtn = document.getElementById('toggleFavDetailBtn');
  const detailTitle = document.getElementById('detailTitle');
  const detailMeta = document.getElementById('detailMeta');
  const detailPdfLink = document.getElementById('detailPdfLink');
  const footerPdfLink = document.getElementById('footerPdfLink');
  const detailWarningsBox = document.getElementById('detailWarningsBox');

  const calcWeightSubtitle = document.getElementById('calcWeightSubtitle');
  const detailConcPill = document.getElementById('detailConcPill');
  const calcTabs = document.querySelectorAll('.calc-tab');
  const tabBtnRimlig = document.getElementById('tabBtnRimlig');
  const tabPanelIndications = document.getElementById('tabPanelIndications');
  const tabPanelRimlig = document.getElementById('tabPanelRimlig');
  const tabPanelCustom = document.getElementById('tabPanelCustom');

  const indicationsCalcContainer = document.getElementById('indicationsCalcContainer');
  const rimligDosContainer = document.getElementById('rimligDosContainer');

  const customDoseInput = document.getElementById('customDoseInput');
  const customDoseUnit = document.getElementById('customDoseUnit');
  const customFreqSelect = document.getElementById('customFreqSelect');
  const customConcInput = document.getElementById('customConcInput');
  const customConcUnit = document.getElementById('customConcUnit');
  const customQuickRates = document.getElementById('customQuickRates');
  const customCalcResult = document.getElementById('customCalcResult');

  const cardAppliesTo = document.getElementById('cardAppliesTo');
  const bodyAppliesTo = document.getElementById('bodyAppliesTo');
  const cardDilution = document.getElementById('cardDilution');
  const bodyDilution = document.getElementById('bodyDilution');
  const cardAdministration = document.getElementById('cardAdministration');
  const bodyAdministration = document.getElementById('bodyAdministration');
  const cardStability = document.getElementById('cardStability');
  const bodyStability = document.getElementById('bodyStability');
  const cardOtherInfo = document.getElementById('cardOtherInfo');
  const bodyOtherInfo = document.getElementById('bodyOtherInfo');

  const installAppBtn = document.getElementById('installAppBtn');
  const phoneGuideBtn = document.getElementById('phoneGuideBtn');
  const lockAppBtn = document.getElementById('lockAppBtn');
  const phoneGuideModal = document.getElementById('phoneGuideModal');
  const closeModalBtn = document.getElementById('closeModalBtn');
  const localUrlBox = document.getElementById('localUrlBox');

  // PIN Lock Elements & Logic (PIN: 1234)
  const APP_PIN = '1234';
  const PIN_STORAGE_KEY = 'elsa_eped_pin_unlocked_v1';
  const pinLockOverlay = document.getElementById('pinLockOverlay');
  const pinDots = document.querySelectorAll('#pinDotsContainer .pin-dot');
  const pinErrorMsg = document.getElementById('pinErrorMsg');
  const pinKeys = document.querySelectorAll('.pin-key[data-digit]');
  const pinClearBtn = document.getElementById('pinClearBtn');
  const pinBackspaceBtn = document.getElementById('pinBackspaceBtn');
  const pinRememberCheck = document.getElementById('pinRememberCheck');
  let enteredPin = '';

  function updatePinDots(isError = false) {
    pinDots.forEach((dot, idx) => {
      dot.classList.toggle('filled', idx < enteredPin.length);
      dot.classList.toggle('error', isError);
    });
  }

  function unlockApp() {
    if (pinRememberCheck && pinRememberCheck.checked) {
      localStorage.setItem(PIN_STORAGE_KEY, 'true');
    } else {
      sessionStorage.setItem(PIN_STORAGE_KEY, 'true');
    }
    if (pinLockOverlay) {
      pinLockOverlay.classList.add('hidden');
    }
    enteredPin = '';
    updatePinDots(false);
  }

  function lockApp() {
    localStorage.removeItem(PIN_STORAGE_KEY);
    sessionStorage.removeItem(PIN_STORAGE_KEY);
    enteredPin = '';
    updatePinDots(false);
    if (pinErrorMsg) pinErrorMsg.classList.add('hidden');
    if (pinLockOverlay) pinLockOverlay.classList.remove('hidden');
  }

  function handlePinDigit(digit) {
    if (enteredPin.length >= 4) return;
    if (pinErrorMsg) pinErrorMsg.classList.add('hidden');
    enteredPin += digit;
    updatePinDots(false);

    if (enteredPin.length === 4) {
      if (enteredPin === APP_PIN) {
        setTimeout(unlockApp, 100);
      } else {
        updatePinDots(true);
        if (pinErrorMsg) pinErrorMsg.classList.remove('hidden');
        setTimeout(() => {
          enteredPin = '';
          updatePinDots(false);
        }, 550);
      }
    }
  }

  if (localStorage.getItem(PIN_STORAGE_KEY) === 'true' || sessionStorage.getItem(PIN_STORAGE_KEY) === 'true') {
    if (pinLockOverlay) pinLockOverlay.classList.add('hidden');
  }

  pinKeys.forEach((btn) => {
    btn.addEventListener('click', () => handlePinDigit(btn.dataset.digit));
  });

  if (pinClearBtn) {
    pinClearBtn.addEventListener('click', () => {
      enteredPin = '';
      updatePinDots(false);
      if (pinErrorMsg) pinErrorMsg.classList.add('hidden');
    });
  }

  if (pinBackspaceBtn) {
    pinBackspaceBtn.addEventListener('click', () => {
      enteredPin = enteredPin.slice(0, -1);
      updatePinDots(false);
    });
  }

  if (lockAppBtn) {
    lockAppBtn.addEventListener('click', lockApp);
  }

  window.addEventListener('keydown', (e) => {
    if (!pinLockOverlay || pinLockOverlay.classList.contains('hidden')) return;
    if (e.key >= '0' && e.key <= '9') {
      handlePinDigit(e.key);
    } else if (e.key === 'Backspace') {
      enteredPin = enteredPin.slice(0, -1);
      updatePinDots(false);
    } else if (e.key === 'Escape') {
      enteredPin = '';
      updatePinDots(false);
    }
  });

  // Formatting Helpers
  function fmtNum(n, maxDecimals = 2) {
    if (n === null || n === undefined || isNaN(n)) return '–';
    if (Math.abs(n) > 0 && Math.abs(n) < 0.05) {
      return n.toFixed(3).replace('.', ',').replace(/0+$/, '').replace(/,$/, '');
    }
    const rounded = Number(Math.round(n + 'e' + maxDecimals) + 'e-' + maxDecimals);
    return rounded.toString().replace('.', ',');
  }

  function parseInputNum(str) {
    if (!str) return null;
    const cleaned = String(str).trim().replace(',', '.');
    const val = parseFloat(cleaned);
    return isNaN(val) || val <= 0 ? null : val;
  }

  function escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // Convert between mass units (g, mg, mikrog)
  function convertMass(value, fromUnit, toUnit) {
    if (value === null || value === undefined) return null;
    const f = (fromUnit || '').toLowerCase();
    const t = (toUnit || '').toLowerCase();
    if (f === t) return value;

    const toMg = {
      g: 1000,
      gram: 1000,
      mg: 1,
      mikrog: 0.001,
      'µg': 0.001,
    };

    if (toMg[f] && toMg[t]) {
      return (value * toMg[f]) / toMg[t];
    }
    return null;
  }

  function hasWeightCalculableData(med) {
    if (med.rimligDos && med.rimligDos.rows && med.rimligDos.rows.length > 0) return true;
    if (med.indications) {
      for (const ind of med.indications) {
        if (ind.regimens && ind.regimens.length > 0) return true;
      }
    }
    return false;
  }

  function saveFavorites() {
    localStorage.setItem('elsa_eped_favs', JSON.stringify(Array.from(state.favorites)));
  }

  // Weight Management
  function setWeight(newWeight, updateInputField = true) {
    if (newWeight !== null && newWeight > 0 && newWeight <= 250) {
      state.weightKg = newWeight;
      localStorage.setItem('elsa_eped_weight', String(newWeight));
    } else if (newWeight === null) {
      state.weightKg = null;
    }

    if (updateInputField && state.weightKg !== null) {
      childWeightInput.value = fmtNum(state.weightKg, 2);
    }

    activeWeightBadge.textContent = state.weightKg ? `${fmtNum(state.weightKg, 2)} kg` : 'Ange vikt';
    weightChips.forEach((chip) => {
      const cw = parseFloat(chip.dataset.weight);
      chip.classList.toggle('active', state.weightKg !== null && Math.abs(cw - state.weightKg) < 0.01);
    });

    if (state.selectedMedId) {
      const med = MEDS.find((m) => m.id === state.selectedMedId);
      if (med) {
        renderCalculatorSections(med);
      }
    }
  }

  // Filter & Render Medication List
  function getFilteredMeds() {
    const q = state.searchQuery.trim().toLowerCase();
    const terms = q ? q.split(/\s+/) : [];

    return MEDS.filter((med) => {
      if (state.routeFilter === 'FAV' && !state.favorites.has(med.id)) return false;
      if (state.routeFilter === 'CALC' && !hasWeightCalculableData(med)) return false;
      if (
        state.routeFilter !== 'ALL' &&
        state.routeFilter !== 'FAV' &&
        state.routeFilter !== 'CALC' &&
        med.route !== state.routeFilter
      ) {
        return false;
      }

      if (terms.length > 0) {
        const hay = `${med.title} ${med.substance} ${(med.brands || []).join(' ')} ${med.epedId}`.toLowerCase();
        return terms.every((t) => hay.includes(t));
      }
      return true;
    });
  }

  function renderMedList() {
    const filtered = getFilteredMeds();
    listCountText.textContent = `Visar ${filtered.length} av ${MEDS.length} instruktioner (Skåne)`;

    if (filtered.length === 0) {
      medListContainer.innerHTML = `
        <div style="padding: 28px 16px; text-align: center; color: #64748b;">
          Inga läkemedel matchade din sökning. Prova att söka på substansnamn eller rensa filtret.
        </div>
      `;
      return;
    }

    const html = filtered
      .map((med) => {
        const isSelected = med.id === state.selectedMedId;
        const isFav = state.favorites.has(med.id);
        const hasCalc = hasWeightCalculableData(med);
        const isIv = med.route.includes('Intravenöst');

        return `
          <div class="med-item ${isSelected ? 'active' : ''}" data-id="${escapeHtml(med.id)}" role="option" aria-selected="${isSelected}">
            <div class="med-item-top">
              <div class="med-item-title">
                ${isFav ? '⭐ ' : ''}${escapeHtml(med.title)}
              </div>
            </div>
            <div class="med-item-badges">
              <span class="badge badge-route ${isIv ? 'iv' : ''}">${escapeHtml(med.route)}</span>
              ${med.concText ? `<span class="badge badge-conc">${escapeHtml(med.concText)}</span>` : ''}
              ${hasCalc ? `<span class="badge badge-calc">🧮 Vikt-dos</span>` : ''}
              <span style="font-size: 0.72rem; color: #64748b; margin-left: auto;">ePed ${escapeHtml(med.epedId)}</span>
            </div>
          </div>
        `;
      })
      .join('');

    medListContainer.innerHTML = html;
  }

  // Compute Dose for a Single Regimen & Child Weight
  function calculateRegimenForWeight(reg, weightKg, med) {
    if (!weightKg || weightKg <= 0) return null;

    // Special handling for Holliday and Segar maintenance fluid formula
    if (reg.calcType === 'holliday_segar') {
      let rawDayMl = 0;
      let formulaBreakdown = '';
      if (weightKg <= 10) {
        rawDayMl = weightKg * 100;
        formulaBreakdown = `${fmtNum(weightKg)} kg × 100 mL/kg = ${fmtNum(rawDayMl)} mL/dygn`;
      } else if (weightKg <= 20) {
        const extraKg = weightKg - 10;
        rawDayMl = 1000 + extraKg * 50;
        formulaBreakdown = `1000 mL (för 0–10 kg) + 50 mL × ${fmtNum(extraKg)} kg (kg över 10) = ${fmtNum(rawDayMl)} mL/dygn`;
      } else {
        const extraKg = weightKg - 20;
        rawDayMl = 1500 + extraKg * 20;
        formulaBreakdown = `1500 mL (för 0–20 kg) + 20 mL × ${fmtNum(extraKg)} kg (kg över 20) = ${fmtNum(rawDayMl)} mL/dygn`;
      }

      const girlMax = reg.maxDayGirlVal || 2000;
      const boyMax = reg.maxDayBoyVal || 2500;
      let capped = false;
      let maxNote = '';
      let perDayMin = rawDayMl;
      let perDayMax = rawDayMl;

      if (rawDayMl > boyMax) {
        capped = true;
        perDayMin = girlMax;
        perDayMax = boyMax;
        maxNote = `Max dygnsvolym: Flickor ${fmtNum(girlMax)} mL/dygn, Pojkar ${fmtNum(boyMax)} mL/dygn`;
      } else if (rawDayMl > girlMax) {
        capped = true;
        perDayMin = girlMax;
        perDayMax = rawDayMl;
        maxNote = `Flickor max ${fmtNum(girlMax)} mL/dygn (Pojkar ${fmtNum(rawDayMl)} mL/dygn, max ${fmtNum(boyMax)} mL/dygn)`;
      }

      const hourlyMin = perDayMin / 24;
      const hourlyMax = perDayMax / 24;

      return {
        isHollidaySegar: true,
        perDoseMin: null,
        perDoseMax: null,
        perDayMin,
        perDayMax,
        hourlyMin,
        hourlyMax,
        adhMin: perDayMin * 0.5,
        adhMax: perDayMax * 0.8,
        volMin: null,
        volMax: null,
        volUnitLabel: 'mL/dygn',
        concUsed: null,
        massUnit: 'mL',
        capped,
        maxNote,
        customFormulaText: formulaBreakdown,
      };
    }

    const massUnit = reg.massUnit || 'mg';
    let rawMin = reg.doseMin * weightKg;
    let rawMax = reg.doseMax * weightKg;

    let perDoseMin = rawMin;
    let perDoseMax = rawMax;
    let perDayMin = null;
    let perDayMax = null;

    const fMin = reg.freqMin || null;
    const fMax = reg.freqMax || fMin;

    if (reg.isPerDay) {
      perDayMin = rawMin;
      perDayMax = rawMax;
      if (fMin && fMin > 0) {
        perDoseMin = rawMin / (fMax || fMin);
        perDoseMax = rawMax / fMin;
      } else {
        perDoseMin = null;
        perDoseMax = null;
      }
    } else if (!reg.infusionTime && fMin) {
      perDayMin = perDoseMin * fMin;
      perDayMax = perDoseMax * (fMax || fMin);
    }

    let cappedByMaxDose = false;
    let cappedByMaxDay = false;
    let maxNote = '';

    // Check max per dose cap
    if (reg.maxDoseVal && reg.maxDoseUnit && perDoseMin !== null) {
      const capInUnit = convertMass(reg.maxDoseVal, reg.maxDoseUnit, massUnit) ?? reg.maxDoseVal;
      if (capInUnit && perDoseMax > capInUnit) {
        cappedByMaxDose = true;
        perDoseMax = capInUnit;
        if (perDoseMin > capInUnit) perDoseMin = capInUnit;
        maxNote = `Maxdos per tillfälle: ${fmtNum(reg.maxDoseVal)} ${reg.maxDoseUnit}`;
        if (fMin) {
          perDayMin = perDoseMin * fMin;
          perDayMax = perDoseMax * (fMax || fMin);
        }
      }
    }

    // Check max per day cap
    if (reg.maxDayVal && reg.maxDayUnit && perDayMax !== null) {
      const dayCapInUnit = convertMass(reg.maxDayVal, reg.maxDayUnit, massUnit) ?? reg.maxDayVal;
      if (dayCapInUnit && perDayMax > dayCapInUnit) {
        cappedByMaxDay = true;
        perDayMax = dayCapInUnit;
        if (perDayMin > dayCapInUnit) perDayMin = dayCapInUnit;
        if (fMin && fMin > 0 && perDoseMax !== null) {
          const maxSingleFromDay = dayCapInUnit / fMin;
          if (perDoseMax > maxSingleFromDay) perDoseMax = maxSingleFromDay;
          if (perDoseMin > maxSingleFromDay) perDoseMin = maxSingleFromDay;
        }
        maxNote = maxNote
          ? `${maxNote} • Max dygnsdos: ${fmtNum(reg.maxDayVal)} ${reg.maxDayUnit}`
          : `Max dygnsdos: ${fmtNum(reg.maxDayVal)} ${reg.maxDayUnit}`;
      }
    }

    // Volume calculation (mL) if medication has liquid concentration
    let volMin = null;
    let volMax = null;
    let volUnitLabel = 'mL';
    let concUsed = null;

    if (massUnit === 'mL') {
      volMin = perDoseMin;
      volMax = perDoseMax;
    } else if (med.concValue && med.concUnit) {
      const baseConcUnit = med.concUnit.replace('/mL', '');
      if (med.isLiquid) {
        const concInRegUnit = convertMass(med.concValue, baseConcUnit, massUnit) ?? (baseConcUnit.toLowerCase() === massUnit.toLowerCase() ? med.concValue : null);
        if (concInRegUnit && concInRegUnit > 0) {
          concUsed = `${fmtNum(med.concValue)} ${med.concUnit}`;
          const targetMin = perDoseMin !== null ? perDoseMin : perDayMin;
          const targetMax = perDoseMax !== null ? perDoseMax : perDayMax;
          if (targetMin !== null) {
            volMin = targetMin / concInRegUnit;
            volMax = targetMax / concInRegUnit;
            if (reg.infusionTime) {
              volUnitLabel = `mL/${reg.infusionTime}`;
            } else if (perDoseMin === null && perDayMin !== null) {
              volUnitLabel = 'mL/dygn';
            }
          }
        }
      } else {
        // Solid tablet/capsule strength
        const tabInRegUnit = convertMass(med.concValue, baseConcUnit, massUnit) ?? (baseConcUnit.toLowerCase() === massUnit.toLowerCase() ? med.concValue : null);
        if (tabInRegUnit && tabInRegUnit > 0 && perDoseMin !== null) {
          concUsed = `${fmtNum(med.concValue)} ${med.concUnit}`;
          volMin = perDoseMin / tabInRegUnit;
          volMax = perDoseMax / tabInRegUnit;
          volUnitLabel = 'st (enh)';
        }
      }
    }

    return {
      isHollidaySegar: false,
      perDoseMin,
      perDoseMax,
      perDayMin,
      perDayMax,
      volMin,
      volMax,
      volUnitLabel,
      concUsed,
      massUnit,
      capped: cappedByMaxDose || cappedByMaxDay,
      maxNote,
      customFormulaText: null,
    };
  }

  function formatRange(minVal, maxVal, unit) {
    if (minVal === null || minVal === undefined) return '–';
    if (maxVal === null || Math.abs(minVal - maxVal) < 0.001) {
      return `${fmtNum(minVal)} ${unit}`;
    }
    return `${fmtNum(minVal)} – ${fmtNum(maxVal)} ${unit}`;
  }

  // Render Indications & Automatic Dose Calculation
  function renderIndicationsCalc(med) {
    const w = state.weightKg;
    if (!med.indications || med.indications.length === 0) {
      indicationsCalcContainer.innerHTML = `
        <div class="indication-raw-lines">
          Ingen strukturerad indikationstext hittades. Kontrollera original-PDF eller använd fliken "Fri kalkylator".
        </div>
      `;
      return;
    }

    const html = med.indications
      .map((ind) => {
        const regs = ind.regimens || [];
        let regCardsHtml = '';

        if (regs.length > 0 && w) {
          regCardsHtml = `
            <div class="regimen-calc-grid">
              ${regs
                .map((reg) => {
                  const res = calculateRegimenForWeight(reg, w, med);
                  if (!res) return '';

                  if (res.isHollidaySegar) {
                    const mainDoseValue = formatRange(res.perDayMin, res.perDayMax, 'mL/dygn');
                    const hourlyValue = formatRange(res.hourlyMin, res.hourlyMax, 'mL/tim');
                    const adhValue = formatRange(res.adhMin, res.adhMax, 'mL/dygn');
                    return `
                      <div class="dose-result-card ${res.capped ? 'capped' : ''}">
                        <div class="dose-result-label">
                          💧 ${escapeHtml(reg.label)}
                        </div>
                        <div class="dose-numbers-row">
                          <div class="dose-big-box vol-box">
                            <div class="dose-big-caption">Underhållsvätska (100 %)</div>
                            <div class="dose-big-value">${escapeHtml(mainDoseValue)}</div>
                          </div>
                          <div class="dose-big-box">
                            <div class="dose-big-caption">Infusionshastighet (dygn ÷ 24 tim)</div>
                            <div class="dose-big-value">${escapeHtml(hourlyValue)}</div>
                          </div>
                          <div class="dose-big-box">
                            <div class="dose-big-caption">Vid ADH-påslag (50 – 80 %)</div>
                            <div class="dose-big-value">${escapeHtml(adhValue)}</div>
                          </div>
                        </div>
                        ${
                          res.capped
                            ? `<div class="max-warning-pill">⚠️ Maxvolym tillämpad (${escapeHtml(res.maxNote)})</div>`
                            : ''
                        }
                        <div class="dose-formula-line">
                          Holliday & Segar (${fmtNum(w)} kg): ${escapeHtml(res.customFormulaText)}
                        </div>
                      </div>
                    `;
                  }

                  const rateStr =
                    reg.doseMin === reg.doseMax
                      ? `${fmtNum(reg.doseMin)} ${reg.unit}`
                      : `${fmtNum(reg.doseMin)} – ${fmtNum(reg.doseMax)} ${reg.unit}`;

                  const freqStr = reg.freqMin
                    ? reg.freqMin === reg.freqMax
                      ? `× ${reg.freqMin} / dygn`
                      : `× ${reg.freqMin}–${reg.freqMax} / dygn`
                    : '';

                  const mainDoseLabel = reg.infusionTime
                    ? `Infusionshastighet (per ${reg.infusionTime})`
                    : res.perDoseMin !== null
                    ? 'Dos per tillfälle'
                    : 'Total dygnsdos';

                  const mainDoseValue =
                    res.perDoseMin !== null
                      ? formatRange(res.perDoseMin, res.perDoseMax, res.massUnit)
                      : formatRange(res.perDayMin, res.perDayMax, `${res.massUnit}/dygn`);

                  const formulaText = `${fmtNum(w)} kg × ${rateStr}${
                    res.capped ? ` → Begränsad till maxdos (${res.maxNote})` : ''
                  }${res.concUsed ? ` ÷ ${res.concUsed}` : ''}`;

                  return `
                    <div class="dose-result-card ${res.capped ? 'capped' : ''}">
                      <div class="dose-result-label">
                        🔹 ${escapeHtml(reg.label)} (${escapeHtml(rateStr)} ${escapeHtml(freqStr)})
                      </div>
                      <div class="dose-numbers-row">
                        <div class="dose-big-box">
                          <div class="dose-big-caption">${escapeHtml(mainDoseLabel)}</div>
                          <div class="dose-big-value">${escapeHtml(mainDoseValue)}</div>
                        </div>
                        ${
                          res.volMin !== null
                            ? `
                          <div class="dose-big-box vol-box">
                            <div class="dose-big-caption">${res.volUnitLabel.includes('st') ? 'Antal vid styrka ' + escapeHtml(res.concUsed) : 'Volym att ge (' + escapeHtml(res.concUsed) + ')'}</div>
                            <div class="dose-big-value">${escapeHtml(formatRange(res.volMin, res.volMax, res.volUnitLabel))}</div>
                          </div>
                        `
                            : ''
                        }
                        ${
                          res.perDayMin !== null && res.perDoseMin !== null
                            ? `
                          <div class="dose-big-box">
                            <div class="dose-big-caption">Dygnsdos (${escapeHtml(freqStr)})</div>
                            <div class="dose-big-value">${escapeHtml(formatRange(res.perDayMin, res.perDayMax, res.massUnit + '/dygn'))}</div>
                          </div>
                        `
                            : ''
                        }
                      </div>
                      ${
                        res.capped
                          ? `<div class="max-warning-pill">⚠️ Maxdos tillämpad (${escapeHtml(res.maxNote)})</div>`
                          : ''
                      }
                      <div class="dose-formula-line">
                        Uträkning: ${escapeHtml(formulaText)}
                      </div>
                    </div>
                  `;
                })
                .join('')}
            </div>
          `;
        }

        const rawLinesHtml = (ind.lines || [])
          .map((ln) => `<p>${escapeHtml(ln)}</p>`)
          .join('');

        return `
          <div class="indication-block">
            <div class="indication-header">${escapeHtml(ind.title)}</div>
            <div class="indication-body">
              ${regCardsHtml}
              <div class="indication-raw-lines">
                ${rawLinesHtml}
              </div>
            </div>
          </div>
        `;
      })
      .join('');

    indicationsCalcContainer.innerHTML = html;
  }

  // Render Rimlig Dos Table with Live Child Weight Column
  function renderRimligDos(med) {
    const rd = med.rimligDos;
    if (!rd || !rd.rows || rd.rows.length === 0) {
      rimligDosContainer.innerHTML = `
        <div class="indication-raw-lines">
          Denna ePed-instruktion har ingen separat "Rimlig dos"-tabell i PDF-filen (vanligt för fasta tabletter/kapslar). Använd fliken "Enligt indikation" eller "Fri kalkylator".
        </div>
      `;
      return;
    }

    const w = state.weightKg;
    const rowsHtml = rd.rows
      .map((row) => {
        let childCellText = '–';
        if (w && row.rateVal) {
          const massUnit = (row.rateUnit || 'mg/kg').split('/')[0];
          let doseAmount = row.rateVal * w;
          let capped = false;
          if (row.maxVal && row.maxUnit) {
            const capInUnit = convertMass(row.maxVal, row.maxUnit, massUnit) ?? row.maxVal;
            if (capInUnit && doseAmount > capInUnit) {
              doseAmount = capInUnit;
              capped = true;
            }
          }
          let volStr = '';
          if (med.isLiquid && med.concValue && med.concUnit) {
            const baseConcUnit = med.concUnit.replace('/mL', '');
            const concInUnit = convertMass(med.concValue, baseConcUnit, massUnit) ?? med.concValue;
            if (concInUnit > 0) {
              const ml = doseAmount / concInUnit;
              volStr = `<strong>${fmtNum(ml, 2)} mL</strong> <span style="font-size:0.76rem;opacity:0.85;">(${fmtNum(doseAmount)} ${massUnit}${capped ? ' • max' : ''})</span>`;
            }
          }
          childCellText = volStr || `<strong>${fmtNum(doseAmount)} ${escapeHtml(massUnit)}${capped ? ' (max)' : ''}</strong>`;
        } else if (row.label.toLowerCase().includes('max') || row.label.toLowerCase().includes('gram')) {
          childCellText = escapeHtml(row.kg50 !== '-' ? row.kg50 : row.kg10);
        }

        return `
          <tr>
            <td>${escapeHtml(row.label)}</td>
            <td class="child-col-cell">${childCellText}</td>
            <td>${escapeHtml(row.kg1)}</td>
            <td>${escapeHtml(row.kg5)}</td>
            <td>${escapeHtml(row.kg10)}</td>
            <td>${escapeHtml(row.kg50)}</td>
          </tr>
        `;
      })
      .join('');

    rimligDosContainer.innerHTML = `
      <p style="font-size: 0.85rem; color: #475569; margin-bottom: 10px;">
        <strong>${escapeHtml(rd.title || 'RIMLIG DOS')}</strong> – Den gröna kolumnen räknar ut exakt volym/dos för barnets inmatade vikt (${w ? fmtNum(w) + ' kg' : 'ange vikt'}) bredvid ePeds referensvikter.
      </p>
      <div class="rimlig-table-wrap">
        <table class="rimlig-table">
          <thead>
            <tr>
              <th>Dosering</th>
              <th class="child-col-header">Barn: ${w ? fmtNum(w) + ' kg' : '–'}</th>
              <th>1 kg</th>
              <th>5 kg</th>
              <th>10 kg</th>
              <th>50 kg</th>
            </tr>
          </thead>
          <tbody>
            ${rowsHtml}
          </tbody>
        </table>
      </div>
      ${rd.note ? `<p style="margin-top: 8px; font-size: 0.8rem; color: #475569;"><em>Obs: ${escapeHtml(rd.note)}</em></p>` : ''}
    `;
  }

  // Render Custom Dose Calculator
  function setupCustomCalculatorForMed(med) {
    if (med.concValue) {
      customConcInput.value = fmtNum(med.concValue);
      const u = med.concUnit || 'mg/mL';
      if ([...customConcUnit.options].some((o) => o.value === u)) {
        customConcUnit.value = u;
      }
    } else {
      customConcInput.value = '';
    }

    // Gather quick rate buttons from rimligDos and regimens
    const quickRates = [];
    const seen = new Set();

    if (med.rimligDos && med.rimligDos.rows) {
      med.rimligDos.rows.forEach((r) => {
        if (r.rateVal) {
          const u = (r.rateUnit || 'mg/kg').split('/').slice(0, 2).join('/');
          const key = `${r.rateVal}_${u}`;
          if (!seen.has(key)) {
            seen.add(key);
            quickRates.push({ val: r.rateVal, unit: u, label: `${fmtNum(r.rateVal)} ${u}` });
          }
        }
      });
    }

    if (med.indications) {
      med.indications.forEach((ind) => {
        (ind.regimens || []).forEach((reg) => {
          const u = `${reg.massUnit}/kg`;
          [reg.doseMin, reg.doseMax].forEach((v) => {
            if (v) {
              const key = `${v}_${u}`;
              if (!seen.has(key)) {
                seen.add(key);
                quickRates.push({ val: v, unit: u, label: `${fmtNum(v)} ${u}` });
              }
            }
          });
        });
      });
    }

    if (quickRates.length > 0) {
      customDoseInput.value = fmtNum(quickRates[0].val);
      if ([...customDoseUnit.options].some((o) => o.value === quickRates[0].unit)) {
        customDoseUnit.value = quickRates[0].unit;
      }
      customQuickRates.innerHTML =
        `<span style="font-size:0.78rem;color:#475569;align-self:center;margin-right:4px;">Snabbval från ePed:</span>` +
        quickRates
          .slice(0, 8)
          .map(
            (q) =>
              `<button type="button" class="quick-rate-btn" data-val="${q.val}" data-unit="${escapeHtml(q.unit)}">${escapeHtml(q.label)}</button>`
          )
          .join('');

      customQuickRates.querySelectorAll('.quick-rate-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
          customDoseInput.value = fmtNum(parseFloat(btn.dataset.val));
          if ([...customDoseUnit.options].some((o) => o.value === btn.dataset.unit)) {
            customDoseUnit.value = btn.dataset.unit;
          }
          updateCustomCalculatorResult();
        });
      });
    } else {
      customQuickRates.innerHTML = '';
    }

    updateCustomCalculatorResult();
  }

  function updateCustomCalculatorResult() {
    const w = state.weightKg;
    const rate = parseInputNum(customDoseInput.value);
    const rateUnit = customDoseUnit.value; // e.g. mg/kg
    const freq = parseInt(customFreqSelect.value, 10) || 1;
    const conc = parseInputNum(customConcInput.value);
    const concUnit = customConcUnit.value; // e.g. mg/mL

    if (!w || !rate) {
      customCalcResult.innerHTML = `<div>Ange både <strong>barnets vikt (kg)</strong> och <strong>dos per kg</strong> för att se uträkningen.</div>`;
      return;
    }

    const massUnit = rateUnit.split('/')[0]; // mg, mikrog, E, mL
    const singleDose = w * rate;
    const dailyDose = singleDose * freq;

    let volHtml = '';
    let formulaExtra = '';

    if (conc && conc > 0) {
      const isLiquidConc = concUnit.endsWith('/mL');
      const concBaseUnit = concUnit.replace('/mL', '');
      const concConverted = convertMass(conc, concBaseUnit, massUnit) ?? (concBaseUnit === massUnit ? conc : null);

      if (concConverted && concConverted > 0) {
        const singleVol = singleDose / concConverted;
        const dailyVol = dailyDose / concConverted;
        const unitLabel = isLiquidConc ? 'mL' : 'tabletter/doser';
        volHtml = `
          <div class="dose-big-box vol-box">
            <div class="dose-big-caption">${isLiquidConc ? 'Volym per dos' : 'Antal per dos'} (${fmtNum(conc)} ${escapeHtml(concUnit)})</div>
            <div class="dose-big-value">${fmtNum(singleVol, 2)} ${unitLabel}</div>
          </div>
          <div class="dose-big-box">
            <div class="dose-big-caption">${isLiquidConc ? 'Volym per dygn' : 'Antal per dygn'} (× ${freq})</div>
            <div class="dose-big-value">${fmtNum(dailyVol, 2)} ${unitLabel}/dygn</div>
          </div>
        `;
        formulaExtra = ` → ${fmtNum(singleDose)} ${massUnit} ÷ ${fmtNum(concConverted)} ${massUnit}/${isLiquidConc ? 'mL' : 'st'} = ${fmtNum(singleVol, 2)} ${unitLabel}`;
      }
    }

    customCalcResult.innerHTML = `
      <div class="dose-numbers-row">
        <div class="dose-big-box">
          <div class="dose-big-caption">Dos per tillfälle</div>
          <div class="dose-big-value">${fmtNum(singleDose)} ${escapeHtml(massUnit)}</div>
        </div>
        ${volHtml}
        <div class="dose-big-box">
          <div class="dose-big-caption">Total dygnsdos (× ${freq})</div>
          <div class="dose-big-value">${fmtNum(dailyDose)} ${escapeHtml(massUnit)}/dygn</div>
        </div>
      </div>
      <div class="dose-formula-line">
        Formel: ${fmtNum(w)} kg × ${fmtNum(rate)} ${escapeHtml(rateUnit)} = ${fmtNum(singleDose)} ${escapeHtml(massUnit)}${escapeHtml(formulaExtra)}
      </div>
    `;
  }

  function renderCalculatorSections(med) {
    calcWeightSubtitle.innerHTML = state.weightKg
      ? `Beräknat för barnets vikt: <strong>${fmtNum(state.weightKg)} kg</strong>`
      : `<span style="color:#dc2626;">Ange barnets vikt i kg högst upp för att räkna ut dos</span>`;

    renderIndicationsCalc(med);
    renderRimligDos(med);
    updateCustomCalculatorResult();
  }

  // Select and Display Medication
  function selectMedication(medId, openMobileView = true) {
    const med = MEDS.find((m) => m.id === medId);
    if (!med) return;

    state.selectedMedId = medId;
    renderMedList();

    emptyDetailState.classList.add('hidden');
    medDetailContent.classList.remove('hidden');

    if (openMobileView) {
      document.body.classList.add('mobile-detail-open');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // Header & Badges
    const isIv = med.route.includes('Intravenöst');
    detailBadges.innerHTML = `
      <span class="badge badge-route ${isIv ? 'iv' : ''}">${escapeHtml(med.route)}</span>
      ${med.concText ? `<span class="badge badge-conc">Styrka: ${escapeHtml(med.concText)}</span>` : ''}
      <span class="badge" style="background:#f1f5f9;color:#475569;">ePed-ID: ${escapeHtml(med.epedId)}</span>
    `;

    const isFav = state.favorites.has(med.id);
    toggleFavDetailBtn.textContent = isFav ? '★' : '☆';
    toggleFavDetailBtn.title = isFav ? 'Ta bort favorit' : 'Spara som favorit';

    detailTitle.textContent = med.title;
    detailMeta.textContent = `Substans: ${med.substance}${
      med.brands && med.brands.length ? ' • Exempel: ' + med.brands.join(', ') : ''
    } • Senast granskad/ändrad i Region Skåne: ${med.date || 'Se PDF'}`;

    detailPdfLink.href = med.pdfUrl;
    footerPdfLink.href = med.pdfUrl;
    mobileQuickPdfBtn.href = med.pdfUrl;

    detailConcPill.textContent = med.concText || 'Se dosering';

    // Warnings
    if (med.warnings && med.warnings.length > 0) {
      detailWarningsBox.classList.remove('hidden');
      detailWarningsBox.innerHTML = `⚠️ ${escapeHtml(med.warnings.join(' '))}`;
    } else {
      detailWarningsBox.classList.add('hidden');
    }

    // Update Rimlig Dos Tab Badge
    const hasRimlig = med.rimligDos && med.rimligDos.rows && med.rimligDos.rows.length > 0;
    tabBtnRimlig.textContent = hasRimlig ? '2. Rimlig dos-tabell ✓' : '2. Rimlig dos-tabell';

    setupCustomCalculatorForMed(med);
    renderCalculatorSections(med);

    // Populate Info Cards
    toggleInfoCard(cardAppliesTo, bodyAppliesTo, med.appliesTo);
    toggleInfoCard(cardDilution, bodyDilution, med.dilution);
    toggleInfoCard(cardAdministration, bodyAdministration, med.administration);
    toggleInfoCard(cardStability, bodyStability, med.stability);
    toggleInfoCard(cardOtherInfo, bodyOtherInfo, med.otherInfo);
  }

  function toggleInfoCard(cardEl, bodyEl, text) {
    if (text && text.trim()) {
      cardEl.classList.remove('hidden');
      bodyEl.textContent = text.trim();
    } else {
      cardEl.classList.add('hidden');
    }
  }

  function switchCalcTab(tabName) {
    state.activeCalcTab = tabName;
    calcTabs.forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.tab === tabName);
    });
    tabPanelIndications.classList.toggle('hidden', tabName !== 'indications');
    tabPanelRimlig.classList.toggle('hidden', tabName !== 'rimlig');
    tabPanelCustom.classList.toggle('hidden', tabName !== 'custom');
  }

  // Event Listeners
  childWeightInput.addEventListener('input', () => {
    const val = parseInputNum(childWeightInput.value);
    setWeight(val, false);
  });

  weightMinusBtn.addEventListener('click', () => {
    const cur = state.weightKg || 10;
    const step = cur <= 5 ? 0.5 : 1;
    setWeight(Math.max(0.5, Math.round((cur - step) * 10) / 10), true);
  });

  weightPlusBtn.addEventListener('click', () => {
    const cur = state.weightKg || 10;
    const step = cur < 5 ? 0.5 : 1;
    setWeight(Math.min(150, Math.round((cur + step) * 10) / 10), true);
  });

  weightChips.forEach((chip) => {
    chip.addEventListener('click', () => {
      setWeight(parseFloat(chip.dataset.weight), true);
    });
  });

  medSearchInput.addEventListener('input', () => {
    state.searchQuery = medSearchInput.value;
    clearSearchBtn.classList.toggle('hidden', !state.searchQuery);
    renderMedList();
  });

  clearSearchBtn.addEventListener('click', () => {
    state.searchQuery = '';
    medSearchInput.value = '';
    clearSearchBtn.classList.add('hidden');
    renderMedList();
    medSearchInput.focus();
  });

  routeFilterBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      state.routeFilter = btn.dataset.route;
      routeFilterBtns.forEach((b) => b.classList.toggle('active', b === btn));
      renderMedList();
    });
  });

  medListContainer.addEventListener('click', (e) => {
    const item = e.target.closest('.med-item');
    if (item && item.dataset.id) {
      selectMedication(item.dataset.id, true);
    }
  });

  backToListBtn.addEventListener('click', () => {
    document.body.classList.remove('mobile-detail-open');
  });

  homeLogoBtn.addEventListener('click', () => {
    document.body.classList.remove('mobile-detail-open');
  });

  toggleFavDetailBtn.addEventListener('click', () => {
    if (!state.selectedMedId) return;
    if (state.favorites.has(state.selectedMedId)) {
      state.favorites.delete(state.selectedMedId);
    } else {
      state.favorites.add(state.selectedMedId);
    }
    saveFavorites();
    const isFav = state.favorites.has(state.selectedMedId);
    toggleFavDetailBtn.textContent = isFav ? '★' : '☆';
    renderMedList();
  });

  calcTabs.forEach((btn) => {
    btn.addEventListener('click', () => {
      switchCalcTab(btn.dataset.tab);
    });
  });

  [customDoseInput, customDoseUnit, customFreqSelect, customConcInput, customConcUnit].forEach((el) => {
    el.addEventListener('input', updateCustomCalculatorResult);
    el.addEventListener('change', updateCustomCalculatorResult);
  });

  // Phone Guide Modal & PWA Install
  phoneGuideBtn.addEventListener('click', () => {
    localUrlBox.textContent = window.location.href;
    phoneGuideModal.classList.remove('hidden');
  });

  closeModalBtn.addEventListener('click', () => {
    phoneGuideModal.classList.add('hidden');
  });

  phoneGuideModal.addEventListener('click', (e) => {
    if (e.target === phoneGuideModal) {
      phoneGuideModal.classList.add('hidden');
    }
  });

  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    state.deferredInstallPrompt = e;
    installAppBtn.classList.remove('hidden');
  });

  installAppBtn.addEventListener('click', async () => {
    if (state.deferredInstallPrompt) {
      state.deferredInstallPrompt.prompt();
      await state.deferredInstallPrompt.userChoice;
      state.deferredInstallPrompt = null;
      installAppBtn.classList.add('hidden');
    } else {
      phoneGuideModal.classList.remove('hidden');
    }
  });

  // Register Service Worker for Offline & Samsung Home Screen PWA
  if ('serviceWorker' in navigator && window.location.protocol.startsWith('http')) {
    navigator.serviceWorker.register('./sw.js').catch(() => {});
  }

  // Initialize App
  const APP_VERSION = 'v1.1 (Vätske- & Maxdosfix)';

  function init() {
    headerStats.textContent = `${MEDS.length} instruktioner • ${APP_VERSION}`;
    setWeight(state.weightKg, true);
    renderMedList();

    // Pre-select Paracetamol oral 24 mg/mL (Alvedon) on desktop so the user immediately sees the calculator in action
    const defaultMed = MEDS.find((m) => m.id.startsWith('3428_')) || MEDS[0];
    if (defaultMed) {
      const isMobile = window.matchMedia('(max-width: 900px)').matches;
      selectMedication(defaultMed.id, !isMobile);
      if (isMobile) {
        document.body.classList.remove('mobile-detail-open');
      }
    }
  }

  init();
})();

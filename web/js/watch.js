let watchPageInitialized = false;
let currentSortKey = null;
let currentSortDirection = "desc";
let watchFetchToken = 0;
let watchFetchTimer = null;
let currentUnitsMetric = "units_net";
let expandedNationId = null;

const UNITS_METRIC_LABELS = {
    units_net: "All Units", soldiers_lost: "Soldiers", tanks_lost: "Tanks",
    aircraft_lost: "Aircraft", ships_lost: "Ships", missiles_lost: "Missiles", nukes_lost: "Nukes",
};
const UNITS_METRIC_ICONS = {
    units_net: "/static/Emojis/Watcher/cost.png", soldiers_lost: "/static/Emojis/Watcher/soldier.png",
    tanks_lost: "/static/Emojis/Watcher/tank.png", aircraft_lost: "/static/Emojis/Watcher/jet.png",
    ships_lost: "/static/Emojis/Watcher/ship.png", missiles_lost: "/static/Emojis/Watcher/missile.png",
    nukes_lost: "/static/Emojis/Watcher/bomb.png",
};
let currentCostMetric = "gross_cost";
const COST_METRIC_LABELS = { gross_cost: "Gross Cost", net_damage: "Net Costs" };
const COST_METRIC_ICONS = { gross_cost: "/static/Emojis/Watcher/cost.png", net_damage: "/static/Emojis/Watcher/net.png" };
let currentConsumptionMetric = "consumption";
const CONSUMPTION_METRIC_LABELS = { consumption: "Consumption", gasoline_sell_value: "Gasoline", munitions_sell_value: "Munitions" };
const CONSUMPTION_METRIC_ICONS = {
    consumption: "/static/Emojis/Watcher/consumption.png",
    gasoline_sell_value: "/static/Emojis/Resources/gasoline.png",
    munitions_sell_value: "/static/Emojis/Resources/munitions.png",
};
let currentDestructionMetric = "destruction_total";
const DESTRUCTION_METRIC_LABELS = { destruction_total: "Destruction", infra_net: "Infrastructure", improvements: "Improvements" };
const DESTRUCTION_METRIC_ICONS = {
    destruction_total: "/static/Emojis/Watcher/infra.png",
    infra_net: "/static/Emojis/Watcher/infra.png",
    improvements: "/static/Emojis/Watcher/improvement.png",
};
let currentWarsMetric = "wars_total";
const WARS_METRIC_LABELS = { wars_total: "Wars", offense_wars_count: "Offensive", defense_wars_count: "Defensive" };
const WARS_METRIC_ICONS = {
    wars_total: "/static/Emojis/Watcher/war.png",
    offense_wars_count: "/static/Emojis/Watcher/off.png",
    defense_wars_count: "/static/Emojis/Watcher/def.png",
};
let currentGainsMetric = "total_gains";
const GAINS_METRIC_LABELS = {
    total_gains: "Total Gains", gains_cash: "Cash", gains_res_coal: "Coal", gains_res_oil: "Oil",
    gains_res_uranium: "Uranium", gains_res_iron: "Iron", gains_res_bauxite: "Bauxite", gains_res_lead: "Lead",
    gains_res_gasoline: "Gasoline", gains_res_munitions: "Munitions", gains_res_steel: "Steel",
    gains_res_aluminum: "Aluminum", gains_res_food: "Food",
};
const GAINS_METRIC_ICONS = {
    total_gains: "/static/Emojis/Watcher/loot.png", gains_cash: "/static/Emojis/Resources/credit.png",
    gains_res_coal: "/static/Emojis/Resources/coal.png", gains_res_oil: "/static/Emojis/Resources/oil.png",
    gains_res_uranium: "/static/Emojis/Resources/uranium.png", gains_res_iron: "/static/Emojis/Resources/iron.png",
    gains_res_bauxite: "/static/Emojis/Resources/bauxite.png", gains_res_lead: "/static/Emojis/Resources/lead.png",
    gains_res_gasoline: "/static/Emojis/Resources/gasoline.png", gains_res_munitions: "/static/Emojis/Resources/munitions.png",
    gains_res_steel: "/static/Emojis/Resources/steel.png", gains_res_aluminum: "/static/Emojis/Resources/aluminum.png",
    gains_res_food: "/static/Emojis/Resources/food.png",
};
const RESOURCE_ICONS = {
    coal: "/static/Emojis/Resources/coal.png", oil: "/static/Emojis/Resources/oil.png",
    uranium: "/static/Emojis/Resources/uranium.png", iron: "/static/Emojis/Resources/iron.png",
    bauxite: "/static/Emojis/Resources/bauxite.png", lead: "/static/Emojis/Resources/lead.png",
    gasoline: "/static/Emojis/Resources/gasoline.png", munitions: "/static/Emojis/Resources/munitions.png",
    steel: "/static/Emojis/Resources/steel.png", aluminum: "/static/Emojis/Resources/aluminum.png",
    food: "/static/Emojis/Resources/food.png",
};
const watchRangeState = {
    availableStartDate: null, availableEndDate: null,
    selectedStartDate: null, selectedEndDate: null,
};

// ── Helpers ──────────────────────────────────────────────────────────────────
function parseIsoDate(dateString) {
    if (!dateString) return null;
    const parsed = new Date(`${dateString}T00:00:00`);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
}
function formatDateLabel(dateString) {
    const parsed = parseIsoDate(dateString);
    if (!parsed) return "Unavailable";
    return parsed.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
function daysBetween(startDate, endDate) {
    if (!startDate || !endDate) return 0;
    return Math.round((endDate.getTime() - startDate.getTime()) / 86400000);
}
function addDays(dateString, dayOffset) {
    const baseDate = parseIsoDate(dateString);
    if (!baseDate) return null;
    const next = new Date(baseDate.getTime());
    next.setDate(next.getDate() + dayOffset);
    return next.toISOString().slice(0, 10);
}
function formatNumber(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n.toLocaleString() : "0";
}
function formatCurrency(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n.toLocaleString() : "$0";
}
function getSliderElements() {
    return {
        startSlider: document.getElementById("watch-start-slider"),
        endSlider: document.getElementById("watch-end-slider"),
        rangeFill: document.getElementById("watch-slider-range"),
    };
}

// ── Slider / range ───────────────────────────────────────────────────────────
function updateRangeLabels(meta = {}) {
    document.getElementById("watch-available-range").textContent =
        meta.available_start_date && meta.available_end_date
            ? `${formatDateLabel(meta.available_start_date)} - ${formatDateLabel(meta.available_end_date)}`
            : "No data";
    document.getElementById("watch-selected-start").textContent = formatDateLabel(watchRangeState.selectedStartDate);
    document.getElementById("watch-selected-end").textContent = formatDateLabel(watchRangeState.selectedEndDate);
    document.getElementById("watch-scale-start").textContent = formatDateLabel(meta.available_start_date);
    document.getElementById("watch-scale-end").textContent = formatDateLabel(meta.available_end_date);
    document.getElementById("watch-war-count").textContent = formatNumber(meta.war_count || 0);
}
function syncSliderUI() {
    const { startSlider, endSlider, rangeFill } = getSliderElements();
    const availableStart = parseIsoDate(watchRangeState.availableStartDate);
    const availableEnd = parseIsoDate(watchRangeState.availableEndDate);
    if (!availableStart || !availableEnd) {
        startSlider.disabled = true; endSlider.disabled = true;
        rangeFill.style.left = "0%"; rangeFill.style.width = "0%";
        return;
    }
    const maxOffset = Math.max(daysBetween(availableStart, availableEnd), 0);
    const selectedStart = parseIsoDate(watchRangeState.selectedStartDate) || availableStart;
    const selectedEnd = parseIsoDate(watchRangeState.selectedEndDate) || availableEnd;
    const startOffset = Math.max(daysBetween(availableStart, selectedStart), 0);
    const endOffset = Math.max(daysBetween(availableStart, selectedEnd), 0);
    startSlider.disabled = false; endSlider.disabled = false;
    startSlider.max = String(maxOffset); endSlider.max = String(maxOffset);
    startSlider.value = String(Math.min(startOffset, endOffset));
    endSlider.value = String(Math.max(startOffset, endOffset));
    const denom = maxOffset || 1;
    const sp = (Number(startSlider.value) / denom) * 100;
    const ep = (Number(endSlider.value) / denom) * 100;
    rangeFill.style.left = `${sp}%`;
    rangeFill.style.width = `${Math.max(ep - sp, 0)}%`;
}
function applyMeta(meta = {}) {
    watchRangeState.availableStartDate = meta.available_start_date || null;
    watchRangeState.availableEndDate = meta.available_end_date || null;
    watchRangeState.selectedStartDate = meta.selected_start_date || meta.available_start_date || null;
    watchRangeState.selectedEndDate = meta.selected_end_date || meta.available_end_date || null;
    updateRangeLabels(meta);
    syncSliderUI();
}
function queueDateWindowFetch() {
    if (watchFetchTimer) clearTimeout(watchFetchTimer);
    watchFetchTimer = setTimeout(() => { watchFetchTimer = null; fetchData(); }, 120);
}
function setStatus(message, isError = false) {
    const status = document.getElementById("watch-status");
    const table = document.getElementById("war-stats-table");
    if (!message) {
        status.style.display = "none"; status.textContent = "";
        status.classList.remove("is-error"); table.style.display = "";
        return;
    }
    status.style.display = "block"; status.textContent = message;
    status.classList.toggle("is-error", isError);
    table.style.display = isError ? "none" : "";
}

// ── Sort helpers ─────────────────────────────────────────────────────────────
function getResolvedSortKey(sortKey) {
    if (sortKey === "cost_metric") return currentCostMetric;
    if (sortKey === "units_metric") return currentUnitsMetric === "units_net" ? "units_total_cost" : currentUnitsMetric;
    if (sortKey === "consumption_metric") return currentConsumptionMetric;
    if (sortKey === "destruction_metric") return currentDestructionMetric === "destruction_total" ? "infra_net" : currentDestructionMetric;
    if (sortKey === "wars_metric") return currentWarsMetric;
    if (sortKey === "gains_metric") return currentGainsMetric;
    return sortKey;
}

// Sort only the top-level nation rows (not expanded sub-rows)
function sortRows(sortKey, direction) {
    if (!sortKey) return;
    const resolvedSortKey = getResolvedSortKey(sortKey);
    const tbody = document.getElementById("war-stats-body");

    // Collect nation rows (data-nation-id) and their associated expand rows
    const groups = [];
    let i = 0;
    const children = Array.from(tbody.children);
    while (i < children.length) {
        const row = children[i];
        if (row.dataset.nationId) {
            const group = [row];
            i++;
            while (i < children.length && children[i].dataset.expandFor) {
                group.push(children[i]);
                i++;
            }
            groups.push(group);
        } else {
            i++;
        }
    }

    groups.sort((a, b) => {
        const aRow = a[0]; const bRow = b[0];
        // Pinned (expanded) nation always stays at top
        if (aRow.dataset.pinned === "true") return -1;
        if (bRow.dataset.pinned === "true") return 1;
        const aCell = aRow.querySelector(`td[data-key='${resolvedSortKey}']`);
        const bCell = bRow.querySelector(`td[data-key='${resolvedSortKey}']`);
        if (!aCell || !bCell) return 0;
        const aSV = aCell.dataset.sortValue ?? aCell.textContent;
        const bSV = bCell.dataset.sortValue ?? bCell.textContent;
        const aV = parseFloat(aSV.replace(/[,$]/g, ""));
        const bV = parseFloat(bSV.replace(/[,$]/g, ""));
        if (Number.isNaN(aV) || Number.isNaN(bV)) {
            return direction === "asc" ? aSV.localeCompare(bSV) : bSV.localeCompare(aSV);
        }
        return direction === "asc" ? aV - bV : bV - aV;
    });

    groups.forEach(group => group.forEach(row => tbody.appendChild(row)));
}

// ── Cell update helpers ───────────────────────────────────────────────────────
function updateUnitsCells() {
    document.querySelectorAll("#war-stats-body tr[data-nation-id]").forEach((row) => {
        const metricCell = row.querySelector("td[data-key='units_metric']");
        if (!metricCell) return;
        if (currentUnitsMetric === "units_net") {
            const countCell = row.querySelector("td[data-key='units_net']");
            const costCell = row.querySelector("td[data-key='units_total_cost']");
            if (!countCell || !costCell) return;
            metricCell.innerHTML = buildAllUnitsDisplay(countCell.dataset.sortValue ?? 0, costCell.dataset.sortValue ?? 0);
            metricCell.dataset.sortValue = costCell.dataset.sortValue ?? "0";
            return;
        }
        const sourceCell = row.querySelector(`td[data-key='${currentUnitsMetric}']`);
        const costCell = row.querySelector(`td[data-key='${currentUnitsMetric}_cost']`);
        if (!sourceCell) return;
        if (costCell) {
            metricCell.innerHTML = buildAllUnitsDisplay(sourceCell.dataset.sortValue ?? 0, costCell.dataset.sortValue ?? 0);
            metricCell.dataset.sortValue = costCell.dataset.sortValue ?? "0";
            return;
        }
        metricCell.textContent = sourceCell.textContent;
        metricCell.dataset.sortValue = sourceCell.dataset.sortValue ?? sourceCell.textContent;
    });
}
function updateCostCells() {
    document.querySelectorAll("#war-stats-body tr[data-nation-id]").forEach((row) => {
        const metricCell = row.querySelector("td[data-key='cost_metric']");
        if (!metricCell) return;
        const grossCell = row.querySelector("td[data-key='gross_cost']");
        const netCell = row.querySelector("td[data-key='net_damage']");
        metricCell.innerHTML = buildCostDisplay(grossCell?.dataset.sortValue ?? 0, netCell?.dataset.sortValue ?? 0);
        metricCell.dataset.sortValue = currentCostMetric === "net_damage"
            ? (netCell?.dataset.sortValue ?? "0") : (grossCell?.dataset.sortValue ?? "0");
    });
}
function updateConsumptionCells() {
    document.querySelectorAll("#war-stats-body tr[data-nation-id]").forEach((row) => {
        const metricCell = row.querySelector("td[data-key='consumption_metric']");
        if (!metricCell) return;
        const gasUsedCell = row.querySelector("td[data-key='gas_used']");
        const gasValCell = row.querySelector("td[data-key='gasoline_sell_value']");
        const munUsedCell = row.querySelector("td[data-key='mun_used']");
        const munValCell = row.querySelector("td[data-key='munitions_sell_value']");
        if (currentConsumptionMetric === "consumption") {
            metricCell.innerHTML = buildConsumptionDisplay(
                gasUsedCell?.dataset.sortValue ?? 0, gasValCell?.dataset.sortValue ?? 0,
                munUsedCell?.dataset.sortValue ?? 0, munValCell?.dataset.sortValue ?? 0);
            metricCell.dataset.sortValue = String((Number(gasValCell?.dataset.sortValue) || 0) + (Number(munValCell?.dataset.sortValue) || 0));
        } else if (currentConsumptionMetric === "gasoline_sell_value") {
            metricCell.innerHTML = buildConsumptionDisplay(gasUsedCell?.dataset.sortValue ?? 0, gasValCell?.dataset.sortValue ?? 0, 0, 0);
            metricCell.dataset.sortValue = gasValCell?.dataset.sortValue ?? "0";
        } else {
            metricCell.innerHTML = buildConsumptionDisplay(0, 0, munUsedCell?.dataset.sortValue ?? 0, munValCell?.dataset.sortValue ?? 0);
            metricCell.dataset.sortValue = munValCell?.dataset.sortValue ?? "0";
        }
    });
}
function updateDestructionCells() {
    document.querySelectorAll("#war-stats-body tr[data-nation-id]").forEach((row) => {
        const metricCell = row.querySelector("td[data-key='destruction_metric']");
        if (!metricCell) return;
        const infraLevelsCell = row.querySelector("td[data-key='infra_levels_lost']");
        const infraValCell = row.querySelector("td[data-key='infra_net']");
        const impCountCell = row.querySelector("td[data-key='improvements_count']");
        const impValCell = row.querySelector("td[data-key='improvements']");
        if (currentDestructionMetric === "destruction_total" || currentDestructionMetric === "infra_net") {
            metricCell.innerHTML = buildDestructionDisplay(
                infraLevelsCell?.dataset.sortValue ?? 0, infraValCell?.dataset.sortValue ?? 0,
                impCountCell?.dataset.sortValue ?? 0, impValCell?.dataset.sortValue ?? 0);
            metricCell.dataset.sortValue = currentDestructionMetric === "improvements"
                ? (impValCell?.dataset.sortValue ?? "0") : (infraValCell?.dataset.sortValue ?? "0");
        } else {
            metricCell.innerHTML = buildDestructionDisplay(0, 0, impCountCell?.dataset.sortValue ?? 0, impValCell?.dataset.sortValue ?? 0);
            metricCell.dataset.sortValue = impValCell?.dataset.sortValue ?? "0";
        }
    });
}
function updateWarsCells() {
    document.querySelectorAll("#war-stats-body tr[data-nation-id]").forEach((row) => {
        const metricCell = row.querySelector("td[data-key='wars_metric']");
        if (!metricCell) return;
        const offCell = row.querySelector("td[data-key='offense_wars_count']");
        const defCell = row.querySelector("td[data-key='defense_wars_count']");
        const off = Number(offCell?.dataset.sortValue) || 0;
        const def = Number(defCell?.dataset.sortValue) || 0;
        metricCell.innerHTML = buildWarsDisplay(off, def);
        if (currentWarsMetric === "offense_wars_count") metricCell.dataset.sortValue = String(off);
        else if (currentWarsMetric === "defense_wars_count") metricCell.dataset.sortValue = String(def);
        else metricCell.dataset.sortValue = String(off + def);
    });
}
function updateGainsCells() {
    document.querySelectorAll("#war-stats-body tr[data-nation-id]").forEach((row) => {
        const metricCell = row.querySelector("td[data-key='gains_metric']");
        if (!metricCell) return;
        let sortVal = 0;
        if (currentGainsMetric === "total_gains") {
            sortVal = Number(row.querySelector("td[data-key='total_gains']")?.dataset.sortValue) || 0;
        } else if (currentGainsMetric === "gains_cash") {
            sortVal = Number(row.querySelector("td[data-key='gains_cash']")?.dataset.sortValue) || 0;
        } else {
            sortVal = Number(row.querySelector(`td[data-key='${currentGainsMetric}']`)?.dataset.sortValue) || 0;
        }
        metricCell.dataset.sortValue = String(sortVal);
        // Keep the displayed value green and updated
        const inner = metricCell.querySelector("span");
        if (inner) inner.textContent = formatCurrency(sortVal);
    });
}

function updateSortUI(sortKey, direction) {
    currentSortKey = sortKey;
    currentSortDirection = direction;
    const arrow = direction === "asc" ? "\u2191" : "\u2193";
    document.querySelectorAll("th[data-sort]").forEach((header) => {
        const isActive = sortKey && header.dataset.sort === sortKey;
        header.dataset.direction = isActive ? direction : "";
        header.classList.toggle("active-sort", !!isActive);
        const arrowEl = header.querySelector(".th-arrow");
        if (arrowEl) arrowEl.textContent = isActive ? arrow : "";
    });
    const setDropdown = (sortId, dirId, selId, iconId, metricKey, labels, icons, currentMetric) => {
        const sortEl = document.getElementById(sortId);
        const dirEl = document.getElementById(dirId);
        const selEl = document.getElementById(selId);
        const iconEl = document.getElementById(iconId);
        if (!sortEl) return;
        sortEl.classList.toggle("is-active", sortKey === metricKey);
        dirEl.textContent = sortKey === metricKey ? arrow : "\u2195";
        selEl.value = currentMetric;
        iconEl.src = icons[currentMetric] || Object.values(icons)[0];
        iconEl.alt = labels[currentMetric] || "";
    };
    setDropdown("watch-cost-sort", "watch-cost-direction", "watch-cost-select", "watch-cost-icon", "cost_metric", COST_METRIC_LABELS, COST_METRIC_ICONS, currentCostMetric);
    setDropdown("watch-gains-sort", "watch-gains-direction", "watch-gains-select", "watch-gains-icon", "gains_metric", GAINS_METRIC_LABELS, GAINS_METRIC_ICONS, currentGainsMetric);
    setDropdown("watch-units-sort", "watch-units-direction", "watch-units-select", "watch-units-icon", "units_metric", UNITS_METRIC_LABELS, UNITS_METRIC_ICONS, currentUnitsMetric);
    setDropdown("watch-consumption-sort", "watch-consumption-direction", "watch-consumption-select", "watch-consumption-icon", "consumption_metric", CONSUMPTION_METRIC_LABELS, CONSUMPTION_METRIC_ICONS, currentConsumptionMetric);
    setDropdown("watch-destruction-sort", "watch-destruction-direction", "watch-destruction-select", "watch-destruction-icon", "destruction_metric", DESTRUCTION_METRIC_LABELS, DESTRUCTION_METRIC_ICONS, currentDestructionMetric);
    setDropdown("watch-wars-sort", "watch-wars-direction", "watch-wars-select", "watch-wars-icon", "wars_metric", WARS_METRIC_LABELS, WARS_METRIC_ICONS, currentWarsMetric);

    const isDropdownSort = ["cost_metric","units_metric","consumption_metric","destruction_metric","wars_metric","gains_metric"].includes(sortKey);
    const activeLabel = !sortKey
        ? "None"
        : isDropdownSort
        ? ({ cost_metric: COST_METRIC_LABELS[currentCostMetric], units_metric: UNITS_METRIC_LABELS[currentUnitsMetric],
             consumption_metric: CONSUMPTION_METRIC_LABELS[currentConsumptionMetric], destruction_metric: DESTRUCTION_METRIC_LABELS[currentDestructionMetric],
             wars_metric: WARS_METRIC_LABELS[currentWarsMetric], gains_metric: GAINS_METRIC_LABELS[currentGainsMetric] }[sortKey] || sortKey)
        : (document.querySelector(`th[data-sort="${sortKey}"] .th-label`)?.textContent.replace(/[\u2191\u2193]/g, "").trim() || sortKey);
    const ss = formatDateLabel(watchRangeState.selectedStartDate);
    const se = formatDateLabel(watchRangeState.selectedEndDate);
    document.getElementById("watch-sort-summary").textContent = !sortKey
        ? `No sort applied | ${ss} - ${se}`
        : `Sorted by ${activeLabel} (${direction === "asc" ? "ascending" : "descending"}) | ${ss} - ${se}`;
}

function applySort(sortKey, direction) {
    if (sortKey === "cost_metric") updateCostCells();
    else if (sortKey === "units_metric") updateUnitsCells();
    else if (sortKey === "consumption_metric") updateConsumptionCells();
    else if (sortKey === "destruction_metric") updateDestructionCells();
    else if (sortKey === "wars_metric") updateWarsCells();
    else if (sortKey === "gains_metric") updateGainsCells();
    sortRows(sortKey, direction);
    updateSortUI(sortKey, direction);
    // Re-sort the expanded sub-table if one is open
    if (expandedNationId) sortExpandedRows(sortKey, direction);
}

// ── Cell builders ─────────────────────────────────────────────────────────────
function buildRowCell(key, value, displayValue = value, hidden = false, extraAttrs = {}) {
    const safeSV = String(value ?? 0).replace(/"/g, "&quot;");
    const hiddenStyle = hidden ? ' style="display:none"' : "";
    const extraStr = Object.entries(extraAttrs).map(([k, v]) => ` ${k}="${String(v).replace(/"/g, "&quot;")}"`).join("");
    return `<td data-key="${key}" data-sort-value="${safeSV}"${hiddenStyle}${extraStr}>${displayValue}</td>`;
}
function buildCostDisplay(grossCost, netCost) {
    const net = Number(netCost) || 0;
    const netClass = net <= 0 ? "watch-val--gain" : "watch-val--loss";
    return `<div class="watch-units-cell">
        <span class="watch-units-cell-main watch-val--loss"><img class="watch-sort-icon" src="/static/Emojis/Watcher/cost.png" alt=""> ${formatCurrency(grossCost)}</span>
        <span class="watch-units-cell-sub ${netClass}"><img class="watch-sort-icon" src="/static/Emojis/Watcher/net.png" alt=""> ${formatCurrency(net)}</span>
    </div>`;
}
function buildAllUnitsDisplay(unitsCount, unitsCost) {
    return `<div class="watch-units-cell">
        <span class="watch-units-cell-main watch-val--loss">${formatNumber(unitsCount)}</span>
        <span class="watch-units-cell-sub watch-val--loss">${formatCurrency(unitsCost)}</span>
    </div>`;
}
function buildDestructionDisplay(infraLevels, infraValue, improvementsCount, improvementsValue) {
    return `<div class="watch-units-cell">
        <span class="watch-units-cell-main watch-val--loss">${formatNumber(infraLevels)} infra levels</span>
        <span class="watch-units-cell-sub watch-val--loss">${formatCurrency(infraValue)}</span>
        <span class="watch-units-cell-main watch-val--loss">${formatNumber(improvementsCount)} improvements</span>
        <span class="watch-units-cell-sub watch-val--loss">${formatCurrency(improvementsValue)}</span>
    </div>`;
}
function buildConsumptionDisplay(gasUsed, gasValue, munUsed, munValue) {
    return `<div class="watch-units-cell">
        <span class="watch-units-cell-main watch-val--loss"><img class="watch-sort-icon" src="/static/Emojis/Resources/gasoline.png" alt=""> ${formatNumber(gasUsed)}</span>
        <span class="watch-units-cell-sub watch-val--loss">${formatCurrency(gasValue)}</span>
        <span class="watch-units-cell-main watch-val--loss"><img class="watch-sort-icon" src="/static/Emojis/Resources/munitions.png" alt=""> ${formatNumber(munUsed)}</span>
        <span class="watch-units-cell-sub watch-val--loss">${formatCurrency(munValue)}</span>
    </div>`;
}
function buildWarsDisplay(offenseWars, defenseWars) {
    const total = (Number(offenseWars) || 0) + (Number(defenseWars) || 0);
    return `<div class="watch-units-cell">
        <span class="watch-units-cell-main"><img class="watch-sort-icon" src="/static/Emojis/Watcher/war.png" alt=""> ${formatNumber(total)} total</span>
        <span class="watch-units-cell-sub"><img class="watch-sort-icon" src="/static/Emojis/Watcher/off.png" alt=""> ${formatNumber(offenseWars)} &nbsp; <img class="watch-sort-icon" src="/static/Emojis/Watcher/def.png" alt=""> ${formatNumber(defenseWars)}</span>
    </div>`;
}


// ── Opponent-side cell builders (colors flipped — their costs = good, their gains = bad) ──
function buildCostDisplayOpp(grossCost, netCost) {
    const net = Number(netCost) || 0;
    // net = opponent's gross_cost - what they looted from us
    // Positive = they spent more than they gained from us = good for us (green)
    // Negative = they looted more than they spent = bad for us (red)
    const netClass = net >= 0 ? "watch-val--gain" : "watch-val--loss";
    return `<div class="watch-units-cell">
        <span class="watch-units-cell-main watch-val--gain"><img class="watch-sort-icon" src="/static/Emojis/Watcher/cost.png" alt=""> ${formatCurrency(grossCost)}</span>
        <span class="watch-units-cell-sub ${netClass}"><img class="watch-sort-icon" src="/static/Emojis/Watcher/net.png" alt=""> ${formatCurrency(net)}</span>
    </div>`;
}
function buildAllUnitsDisplayOpp(unitsCount, unitsCost) {
    return `<div class="watch-units-cell">
        <span class="watch-units-cell-main watch-val--gain">${formatNumber(unitsCount)}</span>
        <span class="watch-units-cell-sub watch-val--gain">${formatCurrency(unitsCost)}</span>
    </div>`;
}
function buildDestructionDisplayOpp(infraLevels, infraValue, improvementsCount, improvementsValue) {
    return `<div class="watch-units-cell">
        <span class="watch-units-cell-main watch-val--gain">${formatNumber(infraLevels)} infra levels</span>
        <span class="watch-units-cell-sub watch-val--gain">${formatCurrency(infraValue)}</span>
        <span class="watch-units-cell-main watch-val--gain">${formatNumber(improvementsCount)} improvements</span>
        <span class="watch-units-cell-sub watch-val--gain">${formatCurrency(improvementsValue)}</span>
    </div>`;
}
function buildConsumptionDisplayOpp(gasUsed, gasValue, munUsed, munValue) {
    return `<div class="watch-units-cell">
        <span class="watch-units-cell-main watch-val--gain"><img class="watch-sort-icon" src="/static/Emojis/Resources/gasoline.png" alt=""> ${formatNumber(gasUsed)}</span>
        <span class="watch-units-cell-sub watch-val--gain">${formatCurrency(gasValue)}</span>
        <span class="watch-units-cell-main watch-val--gain"><img class="watch-sort-icon" src="/static/Emojis/Resources/munitions.png" alt=""> ${formatNumber(munUsed)}</span>
        <span class="watch-units-cell-sub watch-val--gain">${formatCurrency(munValue)}</span>
    </div>`;
}

// ── Expand / collapse ─────────────────────────────────────────────────────────
function buildNationRow(nationId, nation, linkedNationId) {
    const nationName = nation.name || `Unknown ${nationId}`;
    const currentUnitsValue = currentUnitsMetric === "units_net"
        ? Number(nation.units_total_cost) || 0
        : Number(nation[currentUnitsMetric]) || 0;
    const row = document.createElement("tr");
    row.dataset.nationId = nationId;
    row.classList.add("watch-nation-row");
    if (linkedNationId && nationId === linkedNationId) row.classList.add("my-nation-row");

    const warsWith = nation.wars_with || [];
    const expandIcon = warsWith.length > 0
        ? `<span class="watch-expand-icon" aria-hidden="true">&#9654;</span>`
        : `<span class="watch-expand-icon watch-expand-icon--none" aria-hidden="true"></span>`;

    row.innerHTML = [
        `<td data-key="name" data-sort-value="${nationName.replace(/"/g,"&quot;")}">${expandIcon}${nationName}</td>`,
        buildRowCell("cost_metric", Number(nation.gross_cost)||0, buildCostDisplay(nation.gross_cost, nation.net_damage)),
        buildRowCell("gains_metric", Number(nation.total_gains)||0,
            `<span class="watch-val--gain" style="cursor:default">${formatCurrency(nation.total_gains)}</span>`,
            false, { "data-loot-breakdown": JSON.stringify(nation.loot_breakdown||{}) }),
        buildRowCell("total_gains", Number(nation.total_gains)||0, "", true),
        buildRowCell("gains_cash", Number((nation.loot_breakdown||{}).cash)||0, "", true),
        ...Object.entries(RESOURCE_ICONS).map(([res]) => {
            const resData = ((nation.loot_breakdown||{}).resources||{})[res];
            return buildRowCell(`gains_res_${res}`, Number(resData?.value)||0, "", true);
        }),
        buildRowCell("gross_cost", Number(nation.gross_cost)||0, formatCurrency(nation.gross_cost), true),
        buildRowCell("net_damage", Number(nation.net_damage)||0, formatCurrency(nation.net_damage), true),
        buildRowCell("units_metric", currentUnitsValue, currentUnitsMetric === "units_net"
            ? buildAllUnitsDisplay(nation.units_net, nation.units_total_cost)
            : buildAllUnitsDisplay(nation[currentUnitsMetric], nation[`${currentUnitsMetric}_cost`])),
        buildRowCell("consumption_metric", Number(nation.consumption)||0, buildConsumptionDisplay(
            nation.gas_used, nation.gasoline_sell_value, nation.mun_used, nation.munitions_sell_value)),
        buildRowCell("destruction_metric", Number(nation.infra_net)||0, buildDestructionDisplay(
            nation.infra_levels_lost, nation.infra_net, nation.improvements_count, nation.improvements)),
        (() => {
            const off = Number(nation.offense_wars_count)||0;
            const def = Number(nation.defense_wars_count)||0;
            return buildRowCell("wars_metric", off+def, buildWarsDisplay(off, def));
        })(),
        buildRowCell("damages", Number(nation.damages)||0, `<span class="watch-val--gain">${formatCurrency(nation.damages)}</span>`),
        buildRowCell("units_net", Number(nation.units_net)||0, formatNumber(nation.units_net), true),
        buildRowCell("units_total_cost", Number(nation.units_total_cost)||0, formatCurrency(nation.units_total_cost), true),
        buildRowCell("soldiers_lost", Number(nation.soldiers_lost)||0, formatNumber(nation.soldiers_lost), true),
        buildRowCell("soldiers_lost_cost", Number(nation.soldiers_lost_cost)||0, formatCurrency(nation.soldiers_lost_cost), true),
        buildRowCell("tanks_lost", Number(nation.tanks_lost)||0, formatNumber(nation.tanks_lost), true),
        buildRowCell("tanks_lost_cost", Number(nation.tanks_lost_cost)||0, formatCurrency(nation.tanks_lost_cost), true),
        buildRowCell("aircraft_lost", Number(nation.aircraft_lost)||0, formatNumber(nation.aircraft_lost), true),
        buildRowCell("aircraft_lost_cost", Number(nation.aircraft_lost_cost)||0, formatCurrency(nation.aircraft_lost_cost), true),
        buildRowCell("ships_lost", Number(nation.ships_lost)||0, formatNumber(nation.ships_lost), true),
        buildRowCell("ships_lost_cost", Number(nation.ships_lost_cost)||0, formatCurrency(nation.ships_lost_cost), true),
        buildRowCell("missiles_lost", Number(nation.missiles_lost)||0, formatNumber(nation.missiles_lost), true),
        buildRowCell("missiles_lost_cost", Number(nation.missiles_lost_cost)||0, formatCurrency(nation.missiles_lost_cost), true),
        buildRowCell("nukes_lost", Number(nation.nukes_lost)||0, formatNumber(nation.nukes_lost), true),
        buildRowCell("nukes_lost_cost", Number(nation.nukes_lost_cost)||0, formatCurrency(nation.nukes_lost_cost), true),
        buildRowCell("infra_levels_lost", Number(nation.infra_levels_lost)||0, formatNumber(nation.infra_levels_lost), true),
        buildRowCell("infra_net", Number(nation.infra_net)||0, formatCurrency(nation.infra_net), true),
        buildRowCell("improvements", Number(nation.improvements)||0, formatCurrency(nation.improvements), true),
        buildRowCell("consumption", Number(nation.consumption)||0, formatCurrency(nation.consumption), true),
        buildRowCell("gas_used", Number(nation.gas_used)||0, formatNumber(nation.gas_used), true),
        buildRowCell("mun_used", Number(nation.mun_used)||0, formatNumber(nation.mun_used), true),
        buildRowCell("gasoline_sell_value", Number(nation.gasoline_sell_value)||0, formatCurrency(nation.gasoline_sell_value), true),
        buildRowCell("munitions_sell_value", Number(nation.munitions_sell_value)||0, formatCurrency(nation.munitions_sell_value), true),
        buildRowCell("improvements_count", Number(nation.improvements_count)||0, formatNumber(nation.improvements_count), true),
        buildRowCell("offense_wars_count", Number(nation.offense_wars_count)||0, formatNumber(nation.offense_wars_count), true),
        buildRowCell("defense_wars_count", Number(nation.defense_wars_count)||0, formatNumber(nation.defense_wars_count), true),
    ].join("");

    if (warsWith.length > 0) {
        row.style.cursor = "pointer";
        row.addEventListener("click", (e) => {
            if (e.target.closest("select, button, td[data-loot-breakdown]")) return;
            toggleNationExpand(nationId, nation, row);
        });
    }
    return row;
}

function buildExpandRow(nationId, warsWith) {
    const colCount = document.querySelectorAll("#war-stats-table thead th").length;
    const expandRow = document.createElement("tr");
    expandRow.dataset.expandFor = nationId;
    expandRow.classList.add("watch-expand-row");

    if (!warsWith || warsWith.length === 0) {
        expandRow.innerHTML = `<td colspan="${colCount}" class="watch-expand-cell">
            <div class="watch-expand-header"><span class="watch-expand-title">No war opponents found</span></div>
        </td>`;
        return expandRow;
    }

    const subRows = warsWith.map(opp => {
        const s = opp.stats || {};
        const off = Number(s.offense_wars_count) || 0;
        const def = Number(s.defense_wars_count) || 0;
        const warCount = off + def;

        const roleTag = off > 0 && def > 0
            ? `<span class="watch-opp-role watch-opp-role--both">Off &amp; Def</span>`
            : off > 0
                ? `<span class="watch-opp-role watch-opp-role--off">Offensive</span>`
                : `<span class="watch-opp-role watch-opp-role--def">Defensive</span>`;

        // loot_breakdown = what THEY looted from us; opp_loot_breakdown = what WE looted from them
        const theyLootedBreakdown = s.loot_breakdown || {};
        const weLootedBreakdown = s.opp_loot_breakdown || {};

        const theyLooted = (Number(theyLootedBreakdown.cash) || 0) +
            Object.values(theyLootedBreakdown.resources || {}).reduce((sum, r) => sum + (Number(r.value)||0), 0);
        const weLooted = (Number(weLootedBreakdown.cash) || 0) +
            Object.values(weLootedBreakdown.resources || {}).reduce((sum, r) => sum + (Number(r.value)||0), 0);

        // Show both independently:
        // they looted us = red positive (bad for us)
        // we looted them = green negative (loss for them = good for us)
        // If neither, show 0
        let lootLines = [];
        if (theyLooted > 0) lootLines.push(`<span class="watch-val--loss">+${formatCurrency(theyLooted)}</span>`);
        if (weLooted > 0)   lootLines.push(`<span class="watch-val--gain">-${formatCurrency(weLooted)}</span>`);
        const lootDisplay = lootLines.length > 0
            ? `<div class="watch-units-cell" style="cursor:default">${lootLines.join("")}</div>`
            : `<span style="color:var(--text-secondary)">0</span>`;

        return `<tr class="watch-sub-row" data-opp-id="${opp.id}" data-opp-name="${(opp.name||"").replace(/"/g,"&quot;")}">
            <td class="watch-sub-nation">
                <span class="watch-sub-name">${opp.name || opp.id}</span>
                ${roleTag}
                <span class="watch-opp-count">${warCount} war${warCount !== 1 ? "s" : ""}</span>
            </td>
            <td>${buildCostDisplayOpp(s.gross_cost, s.net_damage)}</td>
            <td data-loot-breakdown="${JSON.stringify(theyLootedBreakdown).replace(/"/g,"&quot;")}" data-loot-opp="true" data-loot-opp-breakdown="${JSON.stringify(weLootedBreakdown).replace(/"/g,"&quot;")}">
                ${lootDisplay}
            </td>
            <td>${buildAllUnitsDisplayOpp(s.units_net, s.units_total_cost)}</td>
            <td>${buildConsumptionDisplayOpp(s.gas_used, s.gasoline_sell_value, s.mun_used, s.munitions_sell_value)}</td>
            <td>${buildDestructionDisplayOpp(s.infra_levels_lost, s.infra_net, s.improvements_count, s.improvements)}</td>
            <td>${buildWarsDisplay(off, def)}</td>
            <td><span class="watch-val--loss">${formatCurrency(s.damages)}</span></td>
        </tr>`;
    }).join("");

    const oppCount = warsWith.length;
    expandRow.innerHTML = `<td colspan="${colCount}" class="watch-expand-cell">
        <div class="watch-expand-header">
            <span class="watch-expand-title">Wars With</span>
            <span class="watch-expand-count">${oppCount} opponent${oppCount !== 1 ? "s" : ""}</span>
        </div>
        <div class="watch-sub-table-wrap">
            <table class="watch-sub-table" id="watch-sub-table-${nationId}">
                <thead>
                    <tr>
                        <th class="watch-sub-th">Opponent</th>
                        <th class="watch-sub-th">Cost / Net</th>
                        <th class="watch-sub-th">Gains</th>
                        <th class="watch-sub-th">Units</th>
                        <th class="watch-sub-th">Consumption</th>
                        <th class="watch-sub-th">Destruction</th>
                        <th class="watch-sub-th">Wars</th>
                        <th class="watch-sub-th">Damages</th>
                    </tr>
                </thead>
                <tbody id="watch-sub-body-${nationId}">${subRows}</tbody>
            </table>
        </div>
    </td>`;
    return expandRow;
}

function sortExpandedRows(sortKey, direction) {
    if (!expandedNationId) return;
    const tbody = document.getElementById(`watch-sub-body-${expandedNationId}`);
    if (!tbody) return;
    const rows = Array.from(tbody.querySelectorAll("tr.watch-sub-row"));
    const colMap = { name: 0, cost_metric: 1, gains_metric: 2, units_metric: 3,
        consumption_metric: 4, destruction_metric: 5, wars_metric: 6, damages: 7 };
    const colIdx = colMap[sortKey] ?? 0;
    rows.sort((a, b) => {
        if (colIdx === 0) {
            const an = a.dataset.oppName || "", bn = b.dataset.oppName || "";
            return direction === "asc" ? an.localeCompare(bn) : bn.localeCompare(an);
        }
        const aV = parseFloat((a.querySelectorAll("td")[colIdx]?.textContent || "0").replace(/[,$]/g, "")) || 0;
        const bV = parseFloat((b.querySelectorAll("td")[colIdx]?.textContent || "0").replace(/[,$]/g, "")) || 0;
        return direction === "asc" ? aV - bV : bV - aV;
    });
    rows.forEach(r => tbody.appendChild(r));
}

function toggleNationExpand(nationId, nation, nationRow) {
    const tbody = document.getElementById("war-stats-body");
    const isExpanded = expandedNationId === nationId;

    if (expandedNationId) {
        const oldExpand = tbody.querySelector(`tr[data-expand-for="${expandedNationId}"]`);
        if (oldExpand) oldExpand.remove();
        const oldRow = tbody.querySelector(`tr[data-nation-id="${expandedNationId}"]`);
        if (oldRow) {
            oldRow.classList.remove("watch-nation-row--expanded");
            oldRow.dataset.pinned = "";
            const icon = oldRow.querySelector(".watch-expand-icon");
            if (icon) icon.innerHTML = "&#9654;";
        }
        expandedNationId = null;
    }

    if (isExpanded) return;

    expandedNationId = nationId;
    nationRow.classList.add("watch-nation-row--expanded");
    nationRow.dataset.pinned = "true";
    const icon = nationRow.querySelector(".watch-expand-icon");
    if (icon) icon.innerHTML = "&#9660;";

    tbody.insertBefore(nationRow, tbody.firstChild);
    const expandRow = buildExpandRow(nationId, nation.wars_with || []);
    tbody.insertBefore(expandRow, nationRow.nextSibling);
    sortExpandedRows(currentSortKey, currentSortDirection);
}

// ── Fetch ─────────────────────────────────────────────────────────────────────
async function fetchData() {
    const tableBody = document.getElementById("war-stats-body");
    const requestToken = ++watchFetchToken;
    tableBody.innerHTML = "";
    expandedNationId = null;

    let linkedNationId = null;
    try {
        const linkedRes = await fetch("/api/discord/linked-nation");
        if (linkedRes.ok) {
            const linkedData = await linkedRes.json();
            if (linkedData.linked && linkedData.nation_id) linkedNationId = String(linkedData.nation_id);
        }
    } catch (_) {}

    try {
        const params = new URLSearchParams();
        if (watchRangeState.selectedStartDate) params.set("start_date", watchRangeState.selectedStartDate);
        if (watchRangeState.selectedEndDate) params.set("end_date", watchRangeState.selectedEndDate);

        const response = await fetch(`/api/watch/wars${params.toString() ? `?${params.toString()}` : ""}`);
        const data = await response.json();

        if (requestToken !== watchFetchToken) return;
        if (!response.ok) throw new Error(data.error || `Request failed with status ${response.status}`);

        const meta = data && data.meta ? data.meta : {};
        applyMeta(meta);

        const nations = data && data.nations ? data.nations : {};
        const nationIds = Object.keys(nations);

        if (data.error) setStatus(data.error, nationIds.length === 0);
        else setStatus("");

        if (nationIds.length === 0) {
            setStatus(data.error || "No Night Watch wars were found in the selected date range.");
            updateSortUI(currentSortKey, currentSortDirection);
            return;
        }

        for (const nationId of nationIds) {
            tableBody.appendChild(buildNationRow(nationId, nations[nationId] || {}, linkedNationId));
        }

        // Pin linked nation to top without sorting the rest
        if (linkedNationId) {
            const linkedRow = tableBody.querySelector(`tr[data-nation-id="${linkedNationId}"]`);
            if (linkedRow) tableBody.insertBefore(linkedRow, tableBody.firstChild);
        }

        // Only sort if user has already chosen a sort column; otherwise leave API order
        if (currentSortKey) {
            applySort(currentSortKey, currentSortDirection);
        } else {
            updateSortUI(null, currentSortDirection);
        }
    } catch (error) {
        console.error("Error fetching war data:", error);
        setStatus("Night Watch data could not be loaded right now.", true);
    }
}

// ── Loot tooltip ──────────────────────────────────────────────────────────────
const lootTooltipEl = document.getElementById("loot-tooltip");
let lootTooltipTarget = null;

function positionTooltip(x, y) {
    const pad = 14;
    const tw = lootTooltipEl.offsetWidth || 240;
    const th = lootTooltipEl.offsetHeight || 200;
    let left = x + pad, top = y + pad;
    if (left + tw > window.innerWidth - pad) left = x - tw - pad;
    if (top + th > window.innerHeight - pad) top = y - th - pad;
    lootTooltipEl.style.left = `${left}px`;
    lootTooltipEl.style.top = `${top}px`;
}

function showLootTooltip(cell, x, y) {
    let breakdown;
    try { breakdown = JSON.parse(cell.dataset.lootBreakdown || "null"); } catch { breakdown = null; }
    if (!breakdown) return;

    const isOpp = cell.dataset.lootOpp === "true";
    const cash = Number(breakdown.cash) || 0;
    const resources = breakdown.resources || {};
    const grandTotal = cash + Object.values(resources).reduce((s, r) => s + (Number(r.value)||0), 0);

    // For opponent cells, also show what they looted FROM us
    let oppBreakdown = null;
    if (isOpp) {
        try { oppBreakdown = JSON.parse(cell.dataset.lootOppBreakdown || "null"); } catch { oppBreakdown = null; }
    }

    const titleText = isOpp ? "Looted by Opponent" : "Total Gains Breakdown";
    const valueClass = isOpp ? "watch-val--loss" : "";
    let html = `<p class="loot-tooltip-title">${titleText}</p>`;
    html += `<div class="loot-tooltip-row"><span class="loot-tooltip-label">💰 Cash</span><span class="loot-tooltip-value ${valueClass}">${formatCurrency(cash)}</span></div>`;
    for (const [res, data] of Object.entries(resources)) {
        const icon = RESOURCE_ICONS[res] || "";
        const label = res.charAt(0).toUpperCase() + res.slice(1);
        const iconHtml = icon ? `<img src="${icon}" alt="${label}">` : "";
        html += `<div class="loot-tooltip-row"><span class="loot-tooltip-label">${iconHtml} ${formatNumber(data.amount)} ${label}</span><span class="loot-tooltip-value ${valueClass}">${formatCurrency(data.value)}</span></div>`;
    }
    html += `<div class="loot-tooltip-total"><span>Total</span><span class="${valueClass}">${formatCurrency(grandTotal)}</span></div>`;

    if (oppBreakdown) {
        const oppCash = Number(oppBreakdown.cash) || 0;
        const oppRes = oppBreakdown.resources || {};
        const oppTotal = oppCash + Object.values(oppRes).reduce((s, r) => s + (Number(r.value)||0), 0);
        html += `<p class="loot-tooltip-title" style="margin-top:0.6rem">Looted From Opponent</p>`;
        html += `<div class="loot-tooltip-row"><span class="loot-tooltip-label">💰 Cash</span><span class="loot-tooltip-value watch-val--gain">${formatCurrency(oppCash)}</span></div>`;
        for (const [res, data] of Object.entries(oppRes)) {
            const icon = RESOURCE_ICONS[res] || "";
            const label = res.charAt(0).toUpperCase() + res.slice(1);
            const iconHtml = icon ? `<img src="${icon}" alt="${label}">` : "";
            html += `<div class="loot-tooltip-row"><span class="loot-tooltip-label">${iconHtml} ${formatNumber(data.amount)} ${label}</span><span class="loot-tooltip-value watch-val--gain">${formatCurrency(data.value)}</span></div>`;
        }
        html += `<div class="loot-tooltip-total"><span>Total</span><span class="watch-val--gain">${formatCurrency(oppTotal)}</span></div>`;
    }

    lootTooltipEl.innerHTML = html;
    lootTooltipEl.setAttribute("aria-hidden", "false");
    positionTooltip(x, y);
    lootTooltipEl.classList.add("is-visible");
}

function hideLootTooltip() {
    lootTooltipEl.classList.remove("is-visible");
    lootTooltipEl.setAttribute("aria-hidden", "true");
    lootTooltipTarget = null;
}

document.addEventListener("mouseover", (e) => {
    const cell = e.target.closest("td[data-loot-breakdown]");
    if (!cell) return;
    lootTooltipTarget = cell;
    showLootTooltip(cell, e.clientX, e.clientY);
});
document.addEventListener("mousemove", (e) => {
    if (!lootTooltipTarget) return;
    positionTooltip(e.clientX, e.clientY);
});
document.addEventListener("mouseout", (e) => {
    if (!lootTooltipTarget) return;
    const cell = e.target.closest("td[data-loot-breakdown]");
    if (cell && !cell.contains(e.relatedTarget)) hideLootTooltip();
    else if (!cell) hideLootTooltip();
});

// ── Init ──────────────────────────────────────────────────────────────────────
function initializeWatchPage() {
    if (watchPageInitialized) return;
    watchPageInitialized = true;

    document.querySelectorAll("th[data-sort]").forEach((header) => {
        if (header.dataset.watchInit === "true" || header.dataset.sort === "units_metric") return;
        header.dataset.watchInit = "true";
        header.addEventListener("click", () => {
            const sortKey = header.dataset.sort;
            const direction = currentSortKey === sortKey && currentSortDirection === "asc" ? "desc" : "asc";
            applySort(sortKey, direction);
        });    });

    const { startSlider, endSlider } = getSliderElements();
    const bindSelect = (id, onChange) => {
        const el = document.getElementById(id);
        if (el && el.dataset.watchInit !== "true") { el.dataset.watchInit = "true"; el.addEventListener("change", onChange); }
    };
    const bindClick = (id, onClick) => {
        const el = document.getElementById(id);
        if (el && el.dataset.watchInit !== "true") { el.dataset.watchInit = "true"; el.addEventListener("click", onClick); }
    };

    if (startSlider.dataset.watchInit !== "true") {
        startSlider.dataset.watchInit = "true";
        startSlider.addEventListener("input", () => {
            if (Number(startSlider.value) > Number(endSlider.value)) startSlider.value = endSlider.value;
            watchRangeState.selectedStartDate = addDays(watchRangeState.availableStartDate, Number(startSlider.value));
            updateRangeLabels({ available_start_date: watchRangeState.availableStartDate, available_end_date: watchRangeState.availableEndDate, war_count: document.getElementById("watch-war-count").textContent });
            syncSliderUI(); updateSortUI(currentSortKey, currentSortDirection);
        });
        startSlider.addEventListener("change", queueDateWindowFetch);
    }
    if (endSlider.dataset.watchInit !== "true") {
        endSlider.dataset.watchInit = "true";
        endSlider.addEventListener("input", () => {
            if (Number(endSlider.value) < Number(startSlider.value)) endSlider.value = startSlider.value;
            watchRangeState.selectedEndDate = addDays(watchRangeState.availableStartDate, Number(endSlider.value));
            updateRangeLabels({ available_start_date: watchRangeState.availableStartDate, available_end_date: watchRangeState.availableEndDate, war_count: document.getElementById("watch-war-count").textContent });
            syncSliderUI(); updateSortUI(currentSortKey, currentSortDirection);
        });
        endSlider.addEventListener("change", queueDateWindowFetch);
    }

    bindSelect("watch-units-select", () => { currentUnitsMetric = document.getElementById("watch-units-select").value; applySort("units_metric", currentSortKey === "units_metric" ? currentSortDirection : "desc"); });
    bindClick("watch-units-direction", (e) => { e.stopPropagation(); applySort("units_metric", currentSortKey === "units_metric" && currentSortDirection === "asc" ? "desc" : "asc"); });
    bindSelect("watch-cost-select", () => { currentCostMetric = document.getElementById("watch-cost-select").value; applySort("cost_metric", currentSortKey === "cost_metric" ? currentSortDirection : "desc"); });
    bindClick("watch-cost-direction", (e) => { e.stopPropagation(); applySort("cost_metric", currentSortKey === "cost_metric" && currentSortDirection === "asc" ? "desc" : "asc"); });
    bindSelect("watch-consumption-select", () => { currentConsumptionMetric = document.getElementById("watch-consumption-select").value; applySort("consumption_metric", currentSortKey === "consumption_metric" ? currentSortDirection : "desc"); });
    bindClick("watch-consumption-direction", (e) => { e.stopPropagation(); applySort("consumption_metric", currentSortKey === "consumption_metric" && currentSortDirection === "asc" ? "desc" : "asc"); });
    bindSelect("watch-destruction-select", () => { currentDestructionMetric = document.getElementById("watch-destruction-select").value; applySort("destruction_metric", currentSortKey === "destruction_metric" ? currentSortDirection : "desc"); });
    bindClick("watch-destruction-direction", (e) => { e.stopPropagation(); applySort("destruction_metric", currentSortKey === "destruction_metric" && currentSortDirection === "asc" ? "desc" : "asc"); });
    bindSelect("watch-wars-select", () => { currentWarsMetric = document.getElementById("watch-wars-select").value; applySort("wars_metric", currentSortKey === "wars_metric" ? currentSortDirection : "desc"); });
    bindClick("watch-wars-direction", (e) => { e.stopPropagation(); applySort("wars_metric", currentSortKey === "wars_metric" && currentSortDirection === "asc" ? "desc" : "asc"); });
    bindSelect("watch-gains-select", () => { currentGainsMetric = document.getElementById("watch-gains-select").value; applySort("gains_metric", currentSortKey === "gains_metric" ? currentSortDirection : "desc"); });
    bindClick("watch-gains-direction", (e) => { e.stopPropagation(); applySort("gains_metric", currentSortKey === "gains_metric" && currentSortDirection === "asc" ? "desc" : "asc"); });

    updateSortUI(currentSortKey, currentSortDirection);
    syncSliderUI();
    fetchData();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeWatchPage, { once: true });
} else {
    initializeWatchPage();
}
document.addEventListener("dashboardPageLoaded", (event) => {
    if (event.detail && event.detail.page === "watch.html") initializeWatchPage();
});

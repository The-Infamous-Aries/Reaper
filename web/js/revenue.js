// ── Revenue Page ──────────────────────────────────────────────────────────────

let revenueData = [];
let filteredData = [];
let currentSort = { col: 'turn_revenue', dir: 'desc' };
let currentView = 'members';

// ── Init ──────────────────────────────────────────────────────────────────────

function initRevenuePage() {
  console.log('[Revenue] Initializing revenue page...');

  // Reset state for fresh load
  revenueData = [];
  filteredData = [];
  currentSort = { col: 'turn_revenue', dir: 'desc' };
  currentView = 'members';

  setupEventListeners();
  loadRevenueData();
}

// dashboardPageLoaded fires after this script's onload — belt-and-suspenders
// in case the direct call below somehow missed (shouldn't happen).
document.addEventListener('dashboardPageLoaded', (e) => {
  if (e.detail && e.detail.page === 'revenue.html') {
    if (!document.getElementById('rev-body')?.hasChildNodes()) {
      initRevenuePage();
    }
  }
});

// Run immediately — HTML is already in the DOM when this script executes
initRevenuePage();

function setupEventListeners() {
  console.log('[Revenue] Setting up event listeners...');

  // Remove any previous handler before adding (prevents duplicates on re-navigation)
  document.removeEventListener('click', _revenueClickHandler);
  document.addEventListener('click', _revenueClickHandler);

  const searchInput = document.getElementById('rev-search');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => filterData(e.target.value));
  }

  console.log('[Revenue] Event listeners setup complete');
}

function _revenueClickHandler(e) {
  // Only handle clicks while the revenue page is active
  if (!document.getElementById('rev-table')) return;

  // View tab toggle
  const tab = e.target.closest('.rev-view-tab');
  if (tab) {
    const view = tab.dataset.view;
    console.log('[Revenue] View tab clicked:', view);
    switchView(view);
    return;
  }

  // Refresh button
  if (e.target.closest('#rev-refresh')) {
    console.log('[Revenue] Refresh button clicked');
    loadRevenueData();
    return;
  }

  // Table header sorting
  const th = e.target.closest('#rev-table th[data-col]');
  if (th) {
    console.log('[Revenue] Table header clicked:', th.dataset.col);
    sortTable(th.dataset.col);
    return;
  }
}

// ── Data Loading ──────────────────────────────────────────────────────────────

async function loadRevenueData() {
  console.log('[Revenue] Loading revenue data from API...');
  showStatus('Loading revenue data...', false);

  try {
    const response = await fetch('/api/watch/revenue');
    console.log('[Revenue] API response status:', response.status);

    if (!response.ok) {
      const errorText = await response.text();
      console.error('[Revenue] API error response:', errorText);
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    console.log('[Revenue] API data received:', {
      nationCount: data.nations?.length || 0,
      allianceTotalTurn: data.alliance_total_turn,
      hasError: !!data.error,
      sampleNation: data.nations?.[0] || null
    });

    if (data.error) {
      console.error('[Revenue] API returned error:', data.error);
      showStatus(`Error: ${data.error}`, true);
      return;
    }

    if (!data.nations || !Array.isArray(data.nations)) {
      console.error('[Revenue] Invalid data structure:', data);
      showStatus('Error: Invalid data received from server', true);
      return;
    }

    revenueData = data.nations;
    filteredData = [...revenueData];

    console.log('[Revenue] Loaded', revenueData.length, 'nations');

    // Update counts
    const memberCountEl = document.getElementById('rev-member-count');
    const allianceMemberCountEl = document.getElementById('alliance-member-count');
    if (memberCountEl) memberCountEl.textContent = data.count || 0;
    if (allianceMemberCountEl) allianceMemberCountEl.textContent = data.count || 0;

    // Update alliance totals
    const allianceTurnEl = document.getElementById('alliance-turn-revenue');
    const allianceDayEl  = document.getElementById('alliance-day-revenue');
    if (allianceTurnEl) allianceTurnEl.textContent = formatMoney(data.alliance_total_turn || 0);
    if (allianceDayEl)  allianceDayEl.textContent  = formatMoney(data.alliance_total_day  || 0);

    const avgTurn = data.count > 0 ? (data.alliance_total_turn / data.count) : 0;
    const avgDay  = data.count > 0 ? (data.alliance_total_day  / data.count) : 0;
    const avgTurnEl = document.getElementById('alliance-avg-turn');
    const avgDayEl  = document.getElementById('alliance-avg-day');
    if (avgTurnEl) avgTurnEl.textContent = formatMoney(avgTurn);
    if (avgDayEl)  avgDayEl.textContent  = formatMoney(avgDay);

    if (revenueData.length > 0) {
      const topEarnerEl = document.getElementById('alliance-top-earner');
      if (topEarnerEl) topEarnerEl.textContent = revenueData[0].nation_name;
    }

    hideStatus();
    renderCurrentView();

  } catch (error) {
    console.error('[Revenue] Error loading revenue data:', error);
    showStatus(`Failed to load revenue data: ${error.message}`, true);
  }
}

// ── View Switching ────────────────────────────────────────────────────────────

function switchView(view) {
  console.log('[Revenue] Switching to view:', view);
  currentView = view;

  document.querySelectorAll('.rev-view-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.view === view);
  });

  const membersView  = document.getElementById('view-members');
  const allianceView = document.getElementById('view-alliance');
  if (membersView)  membersView.style.display  = view === 'members'  ? 'block' : 'none';
  if (allianceView) allianceView.style.display = view === 'alliance' ? 'block' : 'none';

  renderCurrentView();
}

function renderCurrentView() {
  if (currentView === 'members') {
    renderMembersTable();
  } else {
    renderAllianceView();
  }
}

// ── Members Table ─────────────────────────────────────────────────────────────

function renderMembersTable() {
  const tbody = document.getElementById('rev-body');
  if (!tbody) return;

  tbody.innerHTML = '';

  if (filteredData.length === 0) {
    tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;padding:2rem;color:var(--text-secondary);">No revenue data available</td></tr>';
    return;
  }

  filteredData.forEach((nation, index) => {
    const row = document.createElement('tr');
    row.dataset.nationId = nation.nation_id;

    const turnRev  = nation.turn_revenue || 0;
    const dayRev   = nation.day_revenue  || 0;
    const turnClass = turnRev >= 0 ? 'rev-positive' : 'rev-negative';
    const dayClass  = dayRev  >= 0 ? 'rev-positive' : 'rev-negative';

    row.innerHTML = `
      <td>${index + 1}</td>
      <td>
        <div class="rev-name-cell">
          ${nation.flag ? `<img src="${nation.flag}" class="rev-flag" alt="Flag">` : ''}
          <div>
            <a href="https://politicsandwar.com/nation/id=${nation.nation_id}"
               target="_blank" class="rev-pnw-link">${escapeHtml(nation.nation_name)}</a>
            <span class="rev-leader">${escapeHtml(nation.leader_name)}</span>
          </div>
        </div>
      </td>
      <td class="${turnClass}">${formatMoney(turnRev)}</td>
      <td class="${dayClass}">${formatMoney(dayRev)}</td>
      <td>${formatNumber(nation.num_cities)}</td>
      <td>${formatNumber(nation.score)}</td>
      <td>${formatNumber(nation.population)}</td>
      <td>${formatMoney(nation.color_bonus || 0)}</td>
      <td class="rev-negative">${formatMoney(-(nation.military_upkeep    || 0))}</td>
      <td class="rev-negative">${formatMoney(-(nation.improvement_upkeep || 0))}</td>
      <td class="rev-negative">${formatMoney(-(nation.alliance_tax       || 0))}</td>
    `;

    tbody.appendChild(row);
  });
}

// ── Alliance View ─────────────────────────────────────────────────────────────

function renderAllianceView() {
  renderTopEarners();
  renderColorDistribution();
}

function renderTopEarners() {
  const container = document.getElementById('rev-top-list');
  if (!container) return;

  container.innerHTML = '';

  revenueData.slice(0, 10).forEach((nation, index) => {
    const item = document.createElement('div');
    item.className = 'rev-top-item';

    const turnRev   = nation.turn_revenue || 0;
    const turnClass = turnRev >= 0 ? 'rev-positive' : 'rev-negative';

    item.innerHTML = `
      <div class="rev-top-rank">#${index + 1}</div>
      <div class="rev-top-nation">
        ${nation.flag ? `<img src="${nation.flag}" class="rev-flag" alt="Flag">` : ''}
        <div>
          <a href="https://politicsandwar.com/nation/id=${nation.nation_id}"
             target="_blank" class="rev-pnw-link">${escapeHtml(nation.nation_name)}</a>
          <span class="rev-leader">${escapeHtml(nation.leader_name)}</span>
        </div>
      </div>
      <div class="rev-top-value ${turnClass}">${formatMoney(turnRev)}/t</div>
    `;

    container.appendChild(item);
  });
}

function renderColorDistribution() {
  const container = document.getElementById('rev-color-bars');
  if (!container) return;

  container.innerHTML = '';

  const colorRevenue = {};
  revenueData.forEach(nation => {
    const color = nation.color || 'beige';
    if (!colorRevenue[color]) colorRevenue[color] = { turn: 0, count: 0 };
    colorRevenue[color].turn  += nation.turn_revenue || 0;
    colorRevenue[color].count += 1;
  });

  const sortedColors = Object.entries(colorRevenue).sort((a, b) => b[1].turn - a[1].turn);
  const maxRevenue   = sortedColors.length > 0 ? sortedColors[0][1].turn : 1;

  sortedColors.forEach(([color, data]) => {
    const bar = document.createElement('div');
    bar.className = 'rev-color-bar';

    const percentage = (data.turn / maxRevenue) * 100;
    const turnClass  = data.turn >= 0 ? 'rev-positive' : 'rev-negative';

    bar.innerHTML = `
      <div class="rev-color-name">${color} (${data.count})</div>
      <div class="rev-color-bar-bg">
        <div class="rev-color-bar-fill" style="width:${percentage}%"></div>
      </div>
      <div class="rev-color-value ${turnClass}">${formatMoney(data.turn)}/t</div>
    `;

    container.appendChild(bar);
  });
}

// ── Sorting ───────────────────────────────────────────────────────────────────

function sortTable(col) {
  if (currentSort.col === col) {
    currentSort.dir = currentSort.dir === 'asc' ? 'desc' : 'asc';
  } else {
    currentSort.col = col;
    currentSort.dir = 'desc';
  }
  applySortAndRender();
}

function applySortAndRender() {
  const col = currentSort.col;

  document.querySelectorAll('#rev-table th').forEach(th => {
    th.classList.remove('rev-sort-active');
    th.textContent = th.textContent.replace(/[↑↓]/g, '').trim();
  });

  const activeHeader = document.querySelector(`#rev-table th[data-col="${col}"]`);
  if (activeHeader) {
    activeHeader.classList.add('rev-sort-active');
    activeHeader.textContent = `${activeHeader.textContent.trim()} ${currentSort.dir === 'asc' ? '↑' : '↓'}`;
  }

  filteredData.sort((a, b) => {
    let aVal = a[col];
    let bVal = b[col];

    if (typeof aVal === 'string') {
      aVal = aVal.toLowerCase();
      bVal = (bVal || '').toLowerCase();
      return currentSort.dir === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
    }

    aVal = aVal || 0;
    bVal = bVal || 0;
    return currentSort.dir === 'asc' ? aVal - bVal : bVal - aVal;
  });

  const colName = activeHeader ? activeHeader.textContent.replace(/[↑↓]/g, '').trim() : col;
  const summaryEl = document.getElementById('rev-sort-summary');
  if (summaryEl) summaryEl.textContent = `Sorted by ${colName} ${currentSort.dir === 'asc' ? '↑' : '↓'}`;

  renderMembersTable();
}

// ── Filtering ─────────────────────────────────────────────────────────────────

function filterData(query) {
  if (!query || query.trim() === '') {
    filteredData = [...revenueData];
  } else {
    const lowerQuery = query.toLowerCase();
    filteredData = revenueData.filter(nation => {
      return (nation.nation_name || '').toLowerCase().includes(lowerQuery) ||
             (nation.leader_name || '').toLowerCase().includes(lowerQuery);
    });
  }
  applySortAndRender();
}

// ── Status Messages ───────────────────────────────────────────────────────────

function showStatus(message, isError = false) {
  const statusEl = document.getElementById('rev-status');
  if (!statusEl) return;
  statusEl.textContent = message;
  statusEl.className = isError ? 'rev-status rev-status-error' : 'rev-status';
  statusEl.style.display = 'block';
}

function hideStatus() {
  const statusEl = document.getElementById('rev-status');
  if (statusEl) statusEl.style.display = 'none';
}

// ── Utilities ─────────────────────────────────────────────────────────────────

function formatMoney(value) {
  if (value === null || value === undefined) return '$0';
  const sign = value < 0 ? '-' : '';
  const abs  = Math.abs(value);
  return `${sign}$${abs.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatNumber(value) {
  if (value === null || value === undefined) return '0';
  return value.toLocaleString('en-US', { maximumFractionDigits: 0 });
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text || '';
  return div.innerHTML;
}

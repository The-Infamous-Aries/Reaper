/* ── Scratch Cards JS ─────────────────────────────────────────────────────── */
(function () {
'use strict';

const $ = id => document.getElementById(id);

// ── State ─────────────────────────────────────────────────────────────────────
let _xp        = 0;
let _funMode   = false;
let _cardType  = null;   // 1-7
let _bet       = 0;
let _playing   = false;
let _result    = null;   // last API result
let _revealed  = [];     // booleans per cell
let _cardInfo  = {};     // from /api/casino/scratch/info

// Win-line definitions for 3×3 (8 lines, 0-indexed flat)
const LINES_3x3 = [
    [0,1,2], [3,4,5], [6,7,8],   // rows
    [0,3,6], [1,4,7], [2,5,8],   // cols
    [0,4,8], [2,4,6],             // diagonals
];

// ── Boot ──────────────────────────────────────────────────────────────────────
function init() {
    if (!$('scratch-root')) return;
    showState('loading');
    Promise.all([checkAuth(), loadCardInfo()]);
    bindEvents();
}

async function checkAuth() {
    try {
        const r = await fetch('/api/casino/xp');
        if (r.status === 401) { showState('login'); return; }
        if (!r.ok)            { showState('login'); return; }
        const d = await r.json();
        if (!d.has_pet) { showState('nopet'); return; }
        _xp = d.total_xp || 0;
        updateXP();
        showState('main');
    } catch {
        showState('login');
    }
}

async function loadCardInfo() {
    try {
        const r = await fetch('/api/casino/scratch/info');
        if (!r.ok) return;
        const d = await r.json();
        _cardInfo = d.cards || {};
        renderCardGrid();
    } catch { /* silent */ }
}

async function refreshXP() {
    try {
        const r = await fetch('/api/casino/xp');
        if (!r.ok) return;
        const d = await r.json();
        if (d.has_pet) { _xp = d.total_xp || 0; updateXP(); }
    } catch { /* silent */ }
}

// ── UI helpers ────────────────────────────────────────────────────────────────
function showState(s) {
    $('sc-loading') && ($('sc-loading').style.display = s === 'loading' ? '' : 'none');
    $('sc-login')   && ($('sc-login').style.display   = s === 'login'   ? '' : 'none');
    $('sc-nopet')   && ($('sc-nopet').style.display   = s === 'nopet'   ? '' : 'none');
    $('sc-main')    && ($('sc-main').style.display    = s === 'main'    ? '' : 'none');
}

function updateXP() {
    const el = $('sc-xp');
    if (el) el.textContent = _xp.toLocaleString();
}

function checkBuyReady() {
    const btn = $('sc-buy-btn');
    if (!btn) return;
    const ok = _cardType !== null && (_funMode || _bet >= 10);
    btn.disabled = !ok;
}

// ── Card grid ─────────────────────────────────────────────────────────────────
function renderCardGrid() {
    const grid = $('sc-card-grid');
    if (!grid) return;
    grid.innerHTML = '';
    const CARD_COLORS = ['#e74c3c','#e67e22','#f1c40f','#2ecc71','#9b59b6','#1abc9c','#e84393'];
    for (let i = 1; i <= 7; i++) {
        const info = _cardInfo[i] || {};
        const btn = document.createElement('button');
        btn.className = 'sc-card-btn';
        btn.dataset.card = i;
        btn.style.setProperty('--card-accent', CARD_COLORS[i-1] || '#888');
        let payoutHTML = '';
        if (i <= 4) {
            payoutHTML = `
            <div class="sc-payout-row"><span>2 match</span><span>${info.two_mult || ''}×</span></div>
            <div class="sc-payout-row"><span>3 match</span><span>${info.three_mult || ''}×</span></div>`;
        } else if (i === 5) {
            payoutHTML = `
            <div class="sc-payout-row"><span>2 match</span><span>${info.two_mult || ''}×</span></div>
            <div class="sc-payout-row"><span>3 match</span><span>${info.three_mult || ''}×</span></div>
            <div class="sc-payout-row" style="opacity:0.75"><span>Type 2</span><span>${info.type_two_mult || 4}×</span></div>
            <div class="sc-payout-row" style="opacity:0.75"><span>Type 3</span><span>${info.type_three_mult || 8}×</span></div>
            <div class="sc-payout-row"><span>Same-type ×2</span><span>${info.bonus_mult || 75}×</span></div>`;
        } else if (i === 6) {
            payoutHTML = `
            <div class="sc-payout-row"><span>3 match</span><span>${info.three_mult || 4}×</span></div>
            <div class="sc-payout-row"><span>4 match</span><span>${info.four_mult || 20}×</span></div>`;
        } else if (i === 7) {
            payoutHTML = `
            <div class="sc-payout-row"><span>4+ match</span><span>${info.four_mult || 6}×</span></div>
            <div class="sc-payout-row"><span>6 match</span><span>${info.six_mult || 50}×</span></div>`;
        }
        btn.innerHTML = `
            <div class="sc-card-icon">${info.icon || '🎟️'}</div>
            <div class="sc-card-name">Card ${i}: ${info.name || ''}</div>
            <div class="sc-card-desc">${info.desc || ''}</div>
            <div class="sc-card-grid-badge">${info.grid || ''} Grid</div>
            ${payoutHTML}
        `;
        grid.appendChild(btn);
    }
}

// ── Events ────────────────────────────────────────────────────────────────────
function bindEvents() {
    // Fun mode toggle
    const toggle = $('sc-fun-toggle');
    if (toggle) toggle.addEventListener('change', e => {
        _funMode = e.target.checked;
        const betSec = $('sc-bet-section');
        if (betSec) betSec.style.display = _funMode ? 'none' : '';
        checkBuyReady();
    });

    // Card selection (delegated)
    document.addEventListener('click', e => {
        const btn = e.target.closest('.sc-card-btn');
        if (!btn || !$('scratch-root')) return;
        document.querySelectorAll('.sc-card-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        _cardType = parseInt(btn.dataset.card);
        checkBuyReady();
    });

    // Bet presets
    document.addEventListener('click', e => {
        const btn = e.target.closest('.sc-preset');
        if (!btn || !$('scratch-root')) return;
        const inp = $('sc-bet-input');
        if (inp) { inp.value = btn.dataset.amount; _bet = parseInt(inp.value); checkBuyReady(); }
    });

    // Bet input
    document.addEventListener('input', e => {
        if (e.target.id === 'sc-bet-input') {
            _bet = parseInt(e.target.value) || 0;
            checkBuyReady();
        }
    });

    // Buy & Scratch
    document.addEventListener('click', e => {
        if (e.target.id === 'sc-buy-btn') buyScratch();
        if (e.target.id === 'sc-reveal-all-btn') revealAll();
        if (e.target.id === 'sc-play-again-btn') resetToSelect();
    });

    // Individual cell scratch
    document.addEventListener('click', e => {
        const cell = e.target.closest('.sc-cell');
        if (!cell || !$('scratch-root')) return;
        const idx = parseInt(cell.dataset.idx);
        if (!isNaN(idx)) scratchCell(idx);
    });
}

// ── Buy & play ────────────────────────────────────────────────────────────────
async function buyScratch() {
    if (_playing) return;
    if (_cardType === null) return;
    if (!_funMode && _bet < 10) return;

    _playing = true;
    const btn = $('sc-buy-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Scratching...'; }

    try {
        const r = await fetch('/api/casino/scratch/play', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                card_type: _cardType,
                bet_amount: _funMode ? 1000 : _bet,
                fun_mode: _funMode,
            }),
        });
        const d = await r.json();
        if (!r.ok || d.error) {
            alert(d.error || 'Scratch failed');
            _playing = false;
            if (btn) { btn.disabled = false; btn.textContent = '🎟️ Buy & Scratch'; }
            return;
        }
        _result = d;
        _revealed = new Array((d.symbols || []).length).fill(false);
        showRevealPanel();
        await refreshXP();
    } catch (err) {
        console.error('Scratch error:', err);
        _playing = false;
        if (btn) { btn.disabled = false; btn.textContent = '🎟️ Buy & Scratch'; }
    }
}

// ── Reveal panel ──────────────────────────────────────────────────────────────
function showRevealPanel() {
    $('sc-select-panel').style.display = 'none';
    const panel = $('sc-reveal-panel');
    panel.style.display = '';

    const info = _cardInfo[_cardType] || {};
    const titleEl = $('sc-reveal-title');
    if (titleEl) titleEl.textContent = `${info.icon || '🎟️'} Card ${_cardType}: ${info.name || ''}`;

    const betEl = $('sc-reveal-bet');
    if (betEl) betEl.textContent = _funMode ? 'Fun' : _bet.toLocaleString();

    // Show correct grid
    const gtype = _result.grid_type || '1x3';
    ['sc-grid-1x3','sc-grid-3x3','sc-grid-1x4','sc-grid-1x6'].forEach(id => {
        const el = $(id);
        if (el) el.style.display = 'none';
    });
    const gridMap = { '1x3': 'sc-grid-1x3', '3x3': 'sc-grid-3x3', '1x4': 'sc-grid-1x4', '1x6': 'sc-grid-1x6' };
    const gridEl = $(gridMap[gtype] || 'sc-grid-1x3');
    if (gridEl) gridEl.style.display = '';

    // Populate cell images (hidden behind covers)
    const symbols = _result.symbols || [];
    if (gridEl) {
        const cells = gridEl.querySelectorAll('.sc-cell');
        cells.forEach((cell, i) => {
            cell.classList.remove('revealed', 'win-cell');
            const inner = cell.querySelector('.sc-cell-inner');
            if (inner && symbols[i]) {
                inner.innerHTML = `<img src="${symbols[i].path}" alt="${symbols[i].name}" title="${symbols[i].name}">`;
            }
        });
    }

    // Hide result until all revealed
    $('sc-result-area').style.display = 'none';
    $('sc-play-again-btn').style.display = 'none';
    $('sc-reveal-all-btn').style.display = '';
}

function getGridEl() {
    const gtype = _result.grid_type || '1x3';
    const map = { '1x3': 'sc-grid-1x3', '3x3': 'sc-grid-3x3', '1x4': 'sc-grid-1x4', '1x6': 'sc-grid-1x6' };
    return $(map[gtype]);
}

function scratchCell(idx) {
    if (!_result) return;
    if (_revealed[idx]) return;
    _revealed[idx] = true;

    const gridEl = getGridEl();
    const cells = gridEl.querySelectorAll('.sc-cell');
    if (cells[idx]) cells[idx].classList.add('revealed');

    // Check if all revealed
    if (_revealed.every(v => v)) {
        setTimeout(showResult, 300);
    }
}

function revealAll() {
    if (!_result) return;
    const gridEl = getGridEl();
    const cells = gridEl.querySelectorAll('.sc-cell');
    let delay = 0;
    cells.forEach((cell, i) => {
        if (!_revealed[i]) {
            setTimeout(() => {
                _revealed[i] = true;
                cell.classList.add('revealed');
            }, delay);
            delay += 80;
        }
    });
    setTimeout(showResult, delay + 350);
    $('sc-reveal-all-btn').style.display = 'none';
}

function showResult() {
    if (!_result) return;
    const resultArea = $('sc-result-area');
    resultArea.style.display = '';

    const textEl = $('sc-result-text');
    const winEl  = $('sc-result-winnings');
    const bonusEl = $('sc-bonus-badge');

    const won = _result.match > 0;
    textEl.textContent = _result.result || '';
    textEl.className = 'sc-result-text ' + (won ? 'win' : 'lose');

    if (won && !_funMode && _result.winnings > 0) {
        winEl.style.display = '';
        winEl.textContent = `+${_result.winnings.toLocaleString()} XP`;
    } else if (won && _funMode) {
        winEl.style.display = '';
        winEl.textContent = `(Fun Mode — ${_result.multiplier}× would win)`;
    } else {
        winEl.style.display = 'none';
    }

    // Multi-line breakdown badge for 3×3 cards
    const multiEl = $('sc-multiline-badge');
    if (multiEl) {
        const e3 = _result.exact_three_count || 0;
        const e2 = _result.exact_two_count   || 0;
        const t3 = _result.type_three_count  || 0;
        const t2 = _result.type_two_count    || 0;
        const totalWins = e3 + e2 + t3 + t2;

        if (_result.grid_type === '3x3' && totalWins > 0) {
            const parts = [];
            if (e3) parts.push(`${e3}×exact-3 (${e3*25}×)`);
            if (e2) parts.push(`${e2}×exact-2 (${e2*10}×)`);
            if (t3) parts.push(`${t3}×type-3 (${t3*8}×)`);
            if (t2) parts.push(`${t2}×type-2 (${t2*4}×)`);
            if (totalWins > 1 || t3 || t2) {
                multiEl.style.display = '';
                multiEl.textContent = '🎯 ' + parts.join(' + ') + ` = ${_result.multiplier}× total`;
            } else {
                multiEl.style.display = 'none';
            }
        } else {
            multiEl.style.display = 'none';
        }
    }

    // Bonus badge for Card 5
    if (_result.bonus_group) {
        bonusEl.style.display = '';
        bonusEl.textContent = `🎯 ${_result.bonus_group} Type Bonus! ${_result.bonus_mult}× multiplier applied!`;
    } else {
        bonusEl.style.display = 'none';
    }

    // Highlight winning cells
    highlightWinCells();

    $('sc-play-again-btn').style.display = '';
    $('sc-reveal-all-btn').style.display = 'none';
    _playing = false;
}

function highlightWinCells() {
    if (!_result || _result.match === 0) return;
    const gridEl = getGridEl();
    const cells = gridEl.querySelectorAll('.sc-cell');
    const gtype = _result.grid_type || '1x3';

    if (gtype === '3x3') {
        // 3×3: highlight cells in winning lines
        const winLineIndices = _result.win_lines || [];
        const winCellSet = new Set();
        winLineIndices.forEach(lineIdx => {
            const line = LINES_3x3[lineIdx];
            if (line) line.forEach(ci => winCellSet.add(ci));
        });
        winCellSet.forEach(ci => {
            cells[ci] && cells[ci].classList.add('win-cell');
        });
    } else if (gtype === '1x3') {
        // 1×3: all 3 cells win if match >= 2
        const symbols = _result.symbols || [];
        const names = symbols.map(s => s.name);
        const counts = {};
        names.forEach(n => counts[n] = (counts[n] || 0) + 1);
        const winSym = Object.entries(counts).sort((a,b) => b[1]-a[1])[0][0];
        names.forEach((n, i) => {
            if (n === winSym) cells[i] && cells[i].classList.add('win-cell');
        });
    } else {
        // 1×4 / 1×6: use win_lines cell indices from API
        const winIdx = _result.win_lines && _result.win_lines[0];
        if (winIdx) {
            winIdx.forEach(i => {
                cells[i] && cells[i].classList.add('win-cell');
            });
        }
    }
}

function resetToSelect() {
    _result = null;
    _revealed = [];
    _playing = false;
    $('sc-reveal-panel').style.display = 'none';
    $('sc-select-panel').style.display = '';
    const btn = $('sc-buy-btn');
    if (btn) { btn.disabled = false; btn.textContent = '🎟️ Buy & Scratch'; }
    checkBuyReady();
}

// ── Back to casino ────────────────────────────────────────────────────────────
window._scratchBack = function () {
    if (typeof navigateTo === 'function') {
        navigateTo('casino');
    } else {
        history.pushState({ page: 'casino' }, '', '?page=casino');
        if (typeof loadPage === 'function') loadPage('casino', null, 'script', null);
    }
};

// ── Init ──────────────────────────────────────────────────────────────────────
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

})();

/* ── Blackjack JS ─────────────────────────────────────────────────────────── */
(function () {
'use strict';

const $ = id => document.getElementById(id);

let _xp      = 0;
let _bet     = 0;
let _funMode = false;
let _state   = null;   // last server response

// ── Boot ──────────────────────────────────────────────────────────────────────
function init() {
    if (!$('bj-root')) return;
    _xp = 0; _bet = 0; _funMode = false; _state = null;
    loadXP().then(showSetup);
    bindEvents();
}

async function loadXP() {
    try {
        const r = await fetch('/api/casino/xp');
        if (!r.ok) return;
        const d = await r.json();
        if (d.has_pet) { _xp = d.total_xp || 0; renderXP(); }
    } catch { /* silent */ }
}

function renderXP() {
    const el = $('bj-xp-display');
    if (el) el.textContent = _xp.toLocaleString() + ' XP';
}

// ── Setup screen ──────────────────────────────────────────────────────────────
function showSetup() {
    $('bj-setup-screen').style.display  = '';
    $('bj-game-screen').style.display   = 'none';
    $('bj-result-area').style.display   = 'none';
    updateDealBtn();
}

function bindEvents() {
    // Fun mode toggle
    const tog = $('bj-fun-toggle');
    if (tog) tog.addEventListener('change', e => {
        _funMode = e.target.checked;
        const betRow = $('bj-bet-row');
        if (betRow) betRow.style.display = _funMode ? 'none' : '';
        updateDealBtn();
    });

    // Bet input
    const inp = $('bj-bet-input');
    if (inp) inp.addEventListener('input', () => {
        _bet = parseInt(inp.value) || 0;
        updateDealBtn();
    });

    // Preset buttons
    document.addEventListener('click', e => {
        const btn = e.target.closest('.bj-preset');
        if (!btn || !$('bj-root')) return;
        const inp2 = $('bj-bet-input');
        if (inp2) { inp2.value = btn.dataset.amount; _bet = parseInt(btn.dataset.amount); updateDealBtn(); }
    });

    // Action buttons
    document.addEventListener('click', e => {
        if (!$('bj-root')) return;
        const id = e.target.id || e.target.closest('button')?.id;
        if (id === 'bj-deal-btn')   deal();
        if (id === 'bj-hit-btn')    action('hit');
        if (id === 'bj-stand-btn')  action('stand');
        if (id === 'bj-double-btn') action('double');
        if (id === 'bj-split-btn')  action('split');
        if (id === 'bj-again-btn')  showSetup();
        if (id === 'bj-quit-btn')   showSetup();
    });
}

function updateDealBtn() {
    const btn = $('bj-deal-btn');
    if (!btn) return;
    const ok = _funMode || (_bet >= 10 && _bet <= _xp);
    btn.disabled = !ok;
}

// ── Deal ──────────────────────────────────────────────────────────────────────
async function deal() {
    setLoading(true);
    try {
        const r = await fetch('/api/casino/blackjack/deal', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ bet: _funMode ? 0 : _bet, fun_mode: _funMode })
        });
        const d = await r.json();
        if (!r.ok) { showError(d.error || 'Deal failed'); return; }
        _state = d;
        $('bj-setup-screen').style.display = 'none';
        $('bj-game-screen').style.display  = '';
        renderGame(d);
        if (d.phase === 'done') showResult(d);
    } catch(e) { showError(e.message); }
    finally { setLoading(false); }
}

// ── Actions ───────────────────────────────────────────────────────────────────
async function action(type) {
    setButtons(false);
    try {
        const r = await fetch(`/api/casino/blackjack/${type}`, {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: '{}'
        });
        const d = await r.json();
        if (!r.ok) { showError(d.error || type + ' failed'); setButtons(true); return; }
        _state = d;
        renderGame(d);
        if (d.phase === 'done') {
            showResult(d);
            await loadXP();
        } else {
            setButtons(true);
        }
    } catch(e) { showError(e.message); setButtons(true); }
}

// ── Render ────────────────────────────────────────────────────────────────────
function renderGame(state) {
    renderHand('bj-dealer-hand', state.dealer_hand, false);
    renderValBadge('bj-dealer-val', state.dealer_val, state.dealer_hand);

    const isActive = state.active_hand === 'main' && state.phase === 'player';
    renderHand('bj-player-hand', state.player_hand, isActive);
    renderValBadge('bj-player-val', state.player_val, state.player_hand);

    // Split hand
    const splitWrap = $('bj-split-wrap');
    if (state.split_hand && state.split_hand.length) {
        splitWrap.style.display = '';
        const splitActive = state.active_hand === 'split' && state.phase === 'player';
        renderHand('bj-split-hand', state.split_hand, splitActive);
        renderValBadge('bj-split-val', state.split_val, state.split_hand);
        $('bj-player-hand-wrap').classList.toggle('active', isActive);
        $('bj-split-hand-wrap').classList.toggle('active', splitActive);
    } else {
        splitWrap.style.display = 'none';
        $('bj-player-hand-wrap').classList.remove('active');
    }

    // Bet display
    const betEl = $('bj-current-bet');
    if (betEl) betEl.textContent = state.fun_mode ? 'Fun Mode' : (state.bet.toLocaleString() + ' XP');

    // Buttons
    if (state.phase === 'player') {
        $('bj-hit-btn').disabled    = false;
        $('bj-stand-btn').disabled  = false;
        $('bj-double-btn').disabled = !state.can_double;
        $('bj-split-btn').disabled  = !state.can_split;
    }
}

function renderHand(containerId, cards, _active) {
    const el = $(containerId);
    if (!el) return;
    el.innerHTML = '';
    cards.forEach((card, i) => {
        const img = document.createElement('img');
        img.className = 'bj-card bj-card--new';
        img.src = card.img;
        img.alt = card.hidden ? 'Hidden' : card.code;
        img.style.animationDelay = (i * 0.06) + 's';
        el.appendChild(img);
    });
}

function renderValBadge(elId, val, cards) {
    const el = $(elId);
    if (!el) return;
    const hand = cards.filter(c => !c.hidden).map(c => c.code);
    const total = hand.length ? _handVal(hand) : '?';
    el.textContent = total;
    el.className = 'bj-val';
    if (total > 21)  el.classList.add('bj-val--bust');
    if (total === 21 && hand.length === 2) el.classList.add('bj-val--bj');
    if (val === '?') el.classList.add('bj-val--hidden');
}

function _handVal(codes) {
    const rankVal = r => {
        if (r === 'J' || r === 'Q' || r === 'K') return 10;
        if (r === '1') return 11;
        return parseInt(r);
    };
    let total = 0, aces = 0;
    codes.forEach(c => {
        const r = c.slice(1);
        total += rankVal(r);
        if (r === '1') aces++;
    });
    while (total > 21 && aces) { total -= 10; aces--; }
    return total;
}

// ── Result ────────────────────────────────────────────────────────────────────
function showResult(state) {
    const area = $('bj-result-area');
    if (!area) return;

    const resultClass = {
        blackjack: 'bj-result--bj',
        win:       'bj-result--win',
        push:      'bj-result--push',
        lose:      'bj-result--lose',
    }[state.result] || 'bj-result--lose';

    const xpChange = state.xp_change || 0;
    const xpClass  = xpChange > 0 ? 'positive' : xpChange < 0 ? 'negative' : 'neutral';
    const xpText   = state.fun_mode
        ? ''
        : `<div class="bj-xp-change ${xpClass}">${xpChange >= 0 ? '+' : ''}${xpChange.toLocaleString()} XP</div>`;

    area.innerHTML = `
        <div class="bj-result ${resultClass}">
            <div class="bj-result-text">${escHtml(state.message || '')}</div>
            ${xpText}
            <div class="bj-actions mt-3">
                <button class="bj-btn" id="bj-again-btn">Deal Again</button>
                <button class="bj-btn bj-btn--stand" id="bj-quit-btn">New Game</button>
            </div>
        </div>`;
    area.style.display = '';
    setButtons(false);
    if (typeof window._casinoLobbyActivity === 'function') {
        const xp = state.xp_change || 0;
        const xpStr = !state.fun_mode && xp !== 0 ? ` (${xp >= 0 ? '+' : ''}${xp.toLocaleString()} XP)` : '';
        window._casinoLobbyActivity(`🃏 Blackjack: ${state.message || state.result}${xpStr}`);
    }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function setLoading(on) {
    const btn = $('bj-deal-btn');
    if (btn) { btn.disabled = on; btn.textContent = on ? 'Dealing...' : '🃏 Deal Cards'; }
}

function setButtons(enabled) {
    ['bj-hit-btn','bj-stand-btn','bj-double-btn','bj-split-btn'].forEach(id => {
        const b = $(id); if (b) b.disabled = !enabled;
    });
}

function showError(msg) {
    const el = $('bj-error');
    if (el) { el.textContent = msg; el.style.display = ''; setTimeout(() => el.style.display = 'none', 4000); }
}

function escHtml(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Boot ──────────────────────────────────────────────────────────────────────
init();

})();

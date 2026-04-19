/* ── Texas Hold'em JS ─────────────────────────────────────────────────────── */
(function () {
'use strict';

const $ = id => document.getElementById(id);

const STAGE_LABELS = {
    idle: 'Waiting', preflop: 'Pre-Flop',
    flop: 'Flop', turn: 'Turn', river: 'River', showdown: 'Showdown'
};

let _state    = null;
let _xp       = 0;
let _numBots  = 2;
let _buyIn    = 500;
let _funMode  = false;

// ── Boot ──────────────────────────────────────────────────────────────────────
function init() {
    if (!$('holdem-root')) return;
    _state = null;
    loadXP().then(() => {
        fetch('/api/casino/holdem/state')
            .then(r => r.json())
            .then(d => {
                if (d.active) {
                    _state = d;
                    // Restore settings from state for recovery
                    if (d.buy_in)    _buyIn   = d.buy_in;
                    if (d.num_bots)  _numBots = d.num_bots;
                    _funMode = d.fun_mode || false;
                    showGame();
                } else showSetup();
            })
            .catch(() => showSetup());
    });
    bindEvents();
}

// ── Session recovery ──────────────────────────────────────────────────────────
async function _recoverSession() {
    if (!_state) return false;
    try {
        const r = await fetch('/api/casino/holdem/start', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({
                buy_in:   _state.buy_in   || _buyIn,
                fun_mode: _state.fun_mode || _funMode,
                num_bots: _state.num_bots || _numBots
            })
        });
        if (!r.ok) return false;
        _state = await r.json();
        return true;
    } catch { return false; }
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
    const el = $('holdem-xp-display');
    if (el) el.textContent = _xp.toLocaleString() + ' XP';
}

// ── Setup / Game screens ──────────────────────────────────────────────────────
function showSetup() {
    $('holdem-setup-screen').style.display = '';
    $('holdem-game-screen').style.display  = 'none';
}

function showGame() {
    $('holdem-setup-screen').style.display = 'none';
    $('holdem-game-screen').style.display  = '';
    renderGame(_state);
}

// ── Events ────────────────────────────────────────────────────────────────────
function bindEvents() {
    // Bot count selector
    document.addEventListener('click', e => {
        const btn = e.target.closest('.holdem-bot-btn');
        if (!btn || !$('holdem-root')) return;
        document.querySelectorAll('.holdem-bot-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
        _numBots = parseInt(btn.dataset.bots);
    });

    // Fun mode
    document.addEventListener('change', e => {
        if (e.target.id === 'holdem-fun-toggle') {
            _funMode = e.target.checked;
            const buyRow = $('holdem-buyin-row');
            if (buyRow) buyRow.style.display = _funMode ? 'none' : '';
        }
    });

    // Buy-in presets
    document.addEventListener('click', e => {
        const btn = e.target.closest('.holdem-buyin-preset');
        if (!btn || !$('holdem-root')) return;
        const inp = $('holdem-buyin-input');
        if (inp) { inp.value = btn.dataset.amount; _buyIn = parseInt(btn.dataset.amount); }
    });

    document.addEventListener('input', e => {
        if (e.target.id === 'holdem-buyin-input') _buyIn = parseInt(e.target.value) || 500;
    });

    // Start
    document.addEventListener('click', e => {
        if (e.target.id === 'holdem-start-btn') startGame();
    });

    // Actions
    document.addEventListener('click', e => {
        if (!$('holdem-root')) return;
        const id = e.target.id || e.target.closest('button')?.id;
        if (id === 'holdem-fold-btn')   playerAction('fold');
        if (id === 'holdem-check-btn')  playerAction('check');
        if (id === 'holdem-call-btn')   playerAction('call');
        if (id === 'holdem-raise-btn')  submitRaise();
        if (id === 'holdem-next-btn')   nextHand();
        if (id === 'holdem-cashout-btn') cashOut();
    });
}

// ── Start ─────────────────────────────────────────────────────────────────────
async function startGame() {
    const btn = $('holdem-start-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Dealing...'; }
    try {
        const r = await fetch('/api/casino/holdem/start', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ buy_in: _funMode ? 1000 : _buyIn, fun_mode: _funMode, num_bots: _numBots })
        });
        const d = await r.json();
        if (!r.ok) { showError(d.error || 'Failed to start'); return; }
        _state = d;
        showGame();
    } catch(e) { showError(e.message); }
    finally { if (btn) { btn.disabled = false; btn.textContent = 'Deal Cards'; } }
}

// ── Player action ─────────────────────────────────────────────────────────────
async function playerAction(action, amount) {
    setActionButtons(false);
    try {
        const body = { action };
        if (amount !== undefined) body.amount = amount;
        let r = await fetch('/api/casino/holdem/action', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify(body)
        });
        let d = await r.json();

        // Auto-recover lost session then retry
        if (!r.ok && r.status === 400 && d.error === 'No active session') {
            const recovered = await _recoverSession();
            if (recovered) {
                r = await fetch('/api/casino/holdem/action', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify(body)
                });
                d = await r.json();
            }
        }

        if (!r.ok) { showError(d.error || action + ' failed'); setActionButtons(true); return; }
        _state = d;
        renderGame(_state);
        if (_state.stage !== 'showdown') setActionButtons(true);
        if (!_state.fun_mode) loadXP();
    } catch(e) { showError(e.message); setActionButtons(true); }
}

function submitRaise() {
    const inp = $('holdem-raise-input');
    const amount = parseInt(inp ? inp.value : '0') || 0;
    if (amount <= 0) { showError('Enter a raise amount'); return; }
    playerAction('raise', amount);
}

// ── Next hand / cashout ───────────────────────────────────────────────────────
async function nextHand() {
    const btn = $('holdem-next-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Dealing...'; }
    try {
        let r = await fetch('/api/casino/holdem/next_hand', {
            method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}'
        });
        let d = await r.json();

        // Auto-recover lost session then retry
        if (!r.ok && r.status === 400 && d.error === 'No active session') {
            const recovered = await _recoverSession();
            if (recovered) {
                r = await fetch('/api/casino/holdem/next_hand', {
                    method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}'
                });
                d = await r.json();
            }
        }

        if (d.game_over) {
            showGameOver(d);
            return;
        }
        if (!r.ok) { showError(d.error || 'Failed'); return; }
        _state = d;
        renderGame(_state);
        setActionButtons(true);
        if (!_state.fun_mode) loadXP();
    } catch(e) { showError(e.message); }
    finally { if (btn) { btn.disabled = false; btn.textContent = 'Next Hand'; } }
}

async function cashOut() {
    try {
        let r = await fetch('/api/casino/holdem/cashout', {
            method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}'
        });
        let d = await r.json();

        // If session was lost, just go back to setup — nothing to cash out
        if (!r.ok && r.status === 400 && d.error === 'No active session') {
            _state = null;
            showSetup();
            return;
        }

        if (!r.ok) { showError(d.error || 'Cashout failed'); return; }
        const stack = d.cashed_out || 0;
        const wasFun = d.fun_mode;
        _state = null;
        if (!wasFun) loadXP();
        showGameOver({ message: `Cashed out ${stack.toLocaleString()} XP. Thanks for playing!`, won: stack });
    } catch(e) { showError(e.message); }
}

function showGameOver(d) {
    _state = null;
    $('holdem-game-screen').style.display = 'none';
    const go = $('holdem-gameover-screen');
    if (go) {
        go.style.display = '';
        const msg = go.querySelector('#holdem-gameover-msg');
        if (msg) msg.textContent = d.message || 'Game over.';
    }
}

// ── Render ────────────────────────────────────────────────────────────────────
function renderGame(state) {
    if (!state) return;

    // Stage badge
    const badge = $('holdem-stage-badge');
    if (badge) badge.textContent = STAGE_LABELS[state.stage] || state.stage;

    // Pot / current bet
    const potEl = $('holdem-pot-val');
    const betEl = $('holdem-bet-val');
    if (potEl) potEl.textContent = state.pot.toLocaleString() + ' XP';
    if (betEl) betEl.textContent = state.current_bet.toLocaleString() + ' XP';

    // Community cards
    renderCommunity(state.community);

    // Seats
    renderSeats(state);

    // Actions
    renderActions(state);

    // Result / showdown
    const resultArea = $('holdem-result-area');
    if (state.stage === 'showdown' && state.result) {
        renderResult(state.result, state);
        if (resultArea) resultArea.style.display = '';
    } else {
        if (resultArea) resultArea.style.display = 'none';
    }

    // Log
    renderLog(state.log);
}

function renderCommunity(cards) {
    const el = $('holdem-community');
    if (!el) return;
    el.innerHTML = '';
    if (!cards || !cards.length) {
        // Show 5 placeholders
        for (let i = 0; i < 5; i++) {
            const img = document.createElement('img');
            img.className = 'holdem-card';
            img.src = '/static/Emojis/Cards/BJ.png';
            img.alt = 'Card';
            img.style.opacity = '0.25';
            el.appendChild(img);
        }
        return;
    }
    cards.forEach((c, i) => {
        const img = document.createElement('img');
        img.className = 'holdem-card holdem-card--new';
        img.src = c.img;
        img.alt = c.hidden ? '?' : c.code;
        img.style.animationDelay = (i * 0.05) + 's';
        el.appendChild(img);
    });
    // Pad remaining with faded backs
    for (let i = cards.length; i < 5; i++) {
        const img = document.createElement('img');
        img.className = 'holdem-card';
        img.src = '/static/Emojis/Cards/BJ.png';
        img.alt = '?';
        img.style.opacity = '0.2';
        el.appendChild(img);
    }
}

function renderSeats(state) {
    const el = $('holdem-seats');
    if (!el) return;
    el.innerHTML = '';
    state.seats.forEach((seat, i) => {
        const div = document.createElement('div');
        div.className = 'holdem-seat'
            + (seat.is_active_turn ? ' active-turn' : '')
            + (seat.folded ? ' folded' : '')
            + (!seat.is_bot ? ' is-player' : '');

        const isDealer = (i === state.dealer_idx);
        const dealerBtn = isDealer ? '<span class="dealer-btn">D</span>' : '';
        const statusText = seat.folded ? 'Folded' : seat.left ? 'Left' : '';

        // -1 sentinel = infinite bot stack
        const stackDisplay = seat.stack === -1 ? '∞' : seat.stack.toLocaleString() + ' XP';

        // Cards
        let cardsHtml = '';
        if (seat.hole && seat.hole.length) {
            cardsHtml = '<div class="holdem-seat-cards">';
            seat.hole.forEach(c => {
                cardsHtml += `<img class="holdem-card holdem-card--sm" src="${escHtml(c.img)}" alt="${c.hidden ? '?' : escHtml(c.code)}">`;
            });
            cardsHtml += '</div>';
        }

        div.innerHTML = `
            <div class="holdem-seat-name">${dealerBtn}${escHtml(seat.name)}${seat.is_active_turn ? ' ▶' : ''}</div>
            <div class="holdem-seat-stack">Stack: ${stackDisplay}</div>
            ${seat.round_bet > 0 ? `<div class="holdem-seat-bet">Bet: ${seat.round_bet.toLocaleString()}</div>` : ''}
            ${statusText ? `<div class="holdem-seat-status">${statusText}</div>` : ''}
            ${cardsHtml}
        `;
        el.appendChild(div);
    });
}

function renderActions(state) {
    const row = $('holdem-action-row');
    const raiseRow = $('holdem-raise-row');
    if (!row) return;

    const actions = state.actions || [];
    const hasFold  = actions.includes('fold');
    const hasCheck = actions.includes('check');
    const hasCall  = actions.includes('call');
    const hasRaise = actions.includes('raise');

    const foldBtn  = $('holdem-fold-btn');
    const checkBtn = $('holdem-check-btn');
    const callBtn  = $('holdem-call-btn');
    const raiseBtn = $('holdem-raise-btn');

    if (foldBtn)  { foldBtn.disabled  = !hasFold;  foldBtn.style.display  = hasFold  ? '' : 'none'; }
    if (checkBtn) { checkBtn.disabled = !hasCheck; checkBtn.style.display = hasCheck ? '' : 'none'; }
    if (callBtn) {
        callBtn.disabled = !hasCall;
        callBtn.style.display = hasCall ? '' : 'none';
        if (hasCall) {
            const toCall = state.current_bet - (state.seats[0]?.round_bet || 0);
            callBtn.textContent = `Call ${toCall.toLocaleString()}`;
        }
    }
    if (raiseBtn) { raiseBtn.disabled = !hasRaise; raiseBtn.style.display = hasRaise ? '' : 'none'; }
    if (raiseRow) raiseRow.style.display = hasRaise ? '' : 'none';

    // Min raise hint
    const minHint = $('holdem-min-raise-hint');
    if (minHint && hasRaise) {
        const toCall = state.current_bet - (state.seats[0]?.round_bet || 0);
        const minRaise = state.current_bet + 50;
        minHint.textContent = `Min raise: ${minRaise}`;
        const inp = $('holdem-raise-input');
        if (inp && !inp.value) inp.value = minRaise;
    }
}

function renderResult(result, state) {
    const el = $('holdem-result-area');
    if (!el) return;

    let html = `<div class="holdem-result">
        <div class="holdem-result-msg">${escHtml(result.message)}</div>`;

    if (result.showdown && result.showdown.length) {
        html += '<div class="holdem-showdown-row">';
        result.showdown.forEach(sd => {
            html += `<div class="holdem-showdown-seat${sd.winner ? ' winner' : ''}">
                <div class="holdem-showdown-name">${escHtml(sd.name)}${sd.winner ? ' 🏆' : ''}</div>
                <div class="holdem-seat-cards" style="justify-content:center">
                    ${sd.hole.map(c => `<img class="holdem-card holdem-card--sm" src="${escHtml(c.img)}" alt="${escHtml(c.code)}">`).join('')}
                </div>
                <div class="holdem-showdown-hand">${escHtml(sd.hand_name)}</div>
            </div>`;
        });
        html += '</div>';
    }

    html += `<div class="holdem-actions mt-2">
        <button class="holdem-btn holdem-btn--call" id="holdem-next-btn">Next Hand</button>
        <button class="holdem-btn" id="holdem-cashout-btn">Cash Out</button>
    </div></div>`;

    el.innerHTML = html;
    if (typeof window._casinoLobbyActivity === 'function' && result.message) {
        window._casinoLobbyActivity(`♠️ Hold'em: ${result.message}`);
    }
}

function renderLog(log) {
    const el = $('holdem-log');
    if (!el || !log) return;
    el.innerHTML = log.length
        ? log.map(l => `<div>${escHtml(l)}</div>`).join('')
        : '<div style="color:var(--text-secondary)">No actions yet.</div>';
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function setActionButtons(enabled) {
    ['holdem-fold-btn','holdem-check-btn','holdem-call-btn','holdem-raise-btn'].forEach(id => {
        const b = $(id); if (b) b.disabled = !enabled;
    });
}

function showError(msg) {
    const el = $('holdem-error');
    if (el) { el.textContent = msg; el.style.display = ''; setTimeout(() => el.style.display = 'none', 4000); }
}

function escHtml(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Boot ──────────────────────────────────────────────────────────────────────
init();

})();

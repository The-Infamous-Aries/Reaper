/* ── Craps JS ─────────────────────────────────────────────────────────────── */
(function () {
'use strict';

const $ = id => document.getElementById(id);

const DICE_COLORS = ["Red","Orange","Blue","Yellow","Pink","Green","Purple"];

const BET_INFO = [
    { type:"Pass Line",   name:"Pass Line",  odds:"1:1",   desc:"Win on 7/11 come-out or Point. Lose on 2/3/12 or 7-out." },
    { type:"Don't Pass",  name:"Don't Pass", odds:"1:1",   desc:"Opposite of Pass Line. Push on 12." },
    { type:"Field",       name:"Field",      odds:"1:1",   desc:"One roll. Win on 2,3,4,9,10,11,12. 2x on 2 or 12." },
    { type:"Place 4",     name:"Place 4",    odds:"9:5",   desc:"Win if 4 before 7. Stays up on win." },
    { type:"Place 5",     name:"Place 5",    odds:"7:5",   desc:"Win if 5 before 7. Stays up on win." },
    { type:"Place 6",     name:"Place 6",    odds:"7:6",   desc:"Win if 6 before 7. Stays up on win." },
    { type:"Place 8",     name:"Place 8",    odds:"7:6",   desc:"Win if 8 before 7. Stays up on win." },
    { type:"Place 9",     name:"Place 9",    odds:"7:5",   desc:"Win if 9 before 7. Stays up on win." },
    { type:"Place 10",    name:"Place 10",   odds:"9:5",   desc:"Win if 10 before 7. Stays up on win." },
    { type:"Any 7",       name:"Any 7",      odds:"4:1",   desc:"One roll. Win only on 7." },
    { type:"Hard 4",      name:"Hard 4",     odds:"7:1",   desc:"Win on 2+2 before 7 or easy 4." },
    { type:"Hard 6",      name:"Hard 6",     odds:"9:1",   desc:"Win on 3+3 before 7 or easy 6." },
    { type:"Hard 8",      name:"Hard 8",     odds:"9:1",   desc:"Win on 4+4 before 7 or easy 8." },
    { type:"Hard 10",     name:"Hard 10",    odds:"7:1",   desc:"Win on 5+5 before 7 or easy 10." },
];

let _state      = null;
let _xp         = 0;
let _pendingBet = null;   // {type} waiting for amount input

// ── Boot ──────────────────────────────────────────────────────────────────────
function init() {
    if (!$('craps-root')) return;
    _state = null; _xp = 0; _pendingBet = null;
    loadXP().then(() => {
        // Check for existing session
        fetch('/api/casino/craps/state')
            .then(r => r.json())
            .then(d => {
                if (d.active) { _state = d; showGame(); }
                else showSetup();
            })
            .catch(() => showSetup());
    });
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
    const el = $('craps-xp-display');
    if (el) el.textContent = _xp.toLocaleString() + ' XP';
}

// ── Setup ─────────────────────────────────────────────────────────────────────
function showSetup() {
    $('craps-setup-screen').style.display = '';
    $('craps-game-screen').style.display  = 'none';
    closeBetModal();
}

function showGame() {
    $('craps-setup-screen').style.display = 'none';
    $('craps-game-screen').style.display  = '';
    renderGame(_state);
}

// ── Events ────────────────────────────────────────────────────────────────────
function bindEvents() {
    // Color picker
    document.addEventListener('click', e => {
        const btn = e.target.closest('.craps-color-btn');
        if (!btn || !$('craps-root')) return;
        document.querySelectorAll('.craps-color-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
    });

    // Start button
    document.addEventListener('click', e => {
        if (e.target.id === 'craps-start-btn') startGame();
    });

    // Bet buttons
    document.addEventListener('click', e => {
        const btn = e.target.closest('.craps-bet-btn');
        if (!btn || !$('craps-game-screen') || $('craps-game-screen').style.display === 'none') return;
        openBetModal(btn.dataset.type);
    });

    // Modal confirm
    document.addEventListener('click', e => {
        if (e.target.id === 'craps-modal-confirm') confirmBet();
        if (e.target.id === 'craps-modal-cancel')  closeBetModal();
    });
    document.addEventListener('keydown', e => {
        if (e.key === 'Enter' && $('craps-modal') && $('craps-modal').style.display !== 'none') confirmBet();
        if (e.key === 'Escape') closeBetModal();
    });

    // Preset amounts in modal
    document.addEventListener('click', e => {
        const btn = e.target.closest('.craps-modal-preset');
        if (!btn) return;
        const inp = $('craps-modal-amount');
        if (inp) inp.value = btn.dataset.amount;
    });

    // Roll, clear, quit
    document.addEventListener('click', e => {
        if (!$('craps-root')) return;
        if (e.target.id === 'craps-roll-btn')  roll();
        if (e.target.id === 'craps-clear-btn') clearBets();
        if (e.target.id === 'craps-quit-btn')  quit();
    });

    // Remove individual bet chip
    document.addEventListener('click', e => {
        const x = e.target.closest('.chip-x');
        if (!x || !$('craps-root')) return;
        removeBet(parseInt(x.dataset.idx));
    });
}

// ── Start ─────────────────────────────────────────────────────────────────────
async function startGame() {
    const funToggle = $('craps-fun-toggle');
    const funMode   = funToggle ? funToggle.checked : false;
    const colorBtn  = document.querySelector('.craps-color-btn.selected');
    const color     = colorBtn ? colorBtn.dataset.color : 'Red';

    const btn = $('craps-start-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Starting...'; }

    try {
        const r = await fetch('/api/casino/craps/start', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ fun_mode: funMode, dice_color: color })
        });
        const d = await r.json();
        if (!r.ok) { showError(d.error || 'Failed to start'); return; }
        _state = d;
        showGame();
    } catch(e) { showError(e.message); }
    finally { if (btn) { btn.disabled = false; btn.textContent = 'Start Game'; } }
}

// ── Bet modal ─────────────────────────────────────────────────────────────────
function openBetModal(betType) {
    _pendingBet = betType;
    const info = BET_INFO.find(b => b.type === betType);
    const title = $('craps-modal-title');
    const desc  = $('craps-modal-desc');
    const inp   = $('craps-modal-amount');
    if (title) title.textContent = `Bet: ${betType}`;
    if (desc)  desc.textContent  = info ? `${info.odds} · ${info.desc}` : '';
    if (inp)   { inp.value = ''; inp.focus(); }
    const modal = $('craps-modal');
    if (modal) modal.style.display = 'flex';
}

function closeBetModal() {
    _pendingBet = null;
    const modal = $('craps-modal');
    if (modal) modal.style.display = 'none';
}

async function confirmBet() {
    if (!_pendingBet) return;
    const inp    = $('craps-modal-amount');
    const amount = parseInt(inp ? inp.value : '0') || 0;
    if (amount < 10) { showError('Minimum bet is 10 XP'); return; }

    closeBetModal();
    try {
        const r = await fetch('/api/casino/craps/bet', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ type: _pendingBet, amount })
        });
        const d = await r.json();
        if (!r.ok) { showError(d.error || 'Bet failed'); return; }
        _state = d;
        renderGame(_state);
    } catch(e) { showError(e.message); }
}

// ── Remove single bet (refund) ────────────────────────────────────────────────
async function removeBet(idx) {
    if (!_state || !_state.bets[idx]) return;
    const bet = _state.bets[idx];
    // Refund by clearing all then re-adding the rest
    // Simpler: just call clear and re-add remaining — but that's complex.
    // Instead: send a targeted remove. We don't have that endpoint, so
    // clear all and re-place the others (fun mode only needs no XP ops).
    // For real mode: clear refunds all, then re-place remaining bets.
    const remaining = _state.bets.filter((_, i) => i !== idx);
    try {
        // Clear all (refunds everything)
        const cr = await fetch('/api/casino/craps/clear_bets', { method:'POST', headers:{'Content-Type':'application/json'}, body:'{}' });
        const cd = await cr.json();
        if (!cr.ok) { showError(cd.error || 'Clear failed'); return; }
        _state = cd;

        // Re-place remaining bets
        for (const b of remaining) {
            const br = await fetch('/api/casino/craps/bet', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({ type: b.type, amount: b.amount })
            });
            const bd = await br.json();
            if (br.ok) _state = bd;
        }
        renderGame(_state);
    } catch(e) { showError(e.message); }
}

// ── Roll ──────────────────────────────────────────────────────────────────────
async function roll() {
    const btn = $('craps-roll-btn');
    if (btn) { btn.disabled = true; btn.textContent = '🎲 Rolling...'; }

    // Animate dice
    const d1el = $('craps-die-1'), d2el = $('craps-die-2');
    if (d1el) d1el.classList.add('rolling');
    if (d2el) d2el.classList.add('rolling');

    try {
        const r = await fetch('/api/casino/craps/roll', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: '{}'
        });
        const d = await r.json();
        if (!r.ok) { showError(d.error || 'Roll failed'); return; }
        _state = d;

        // Wait for animation then render
        setTimeout(() => {
            if (d1el) d1el.classList.remove('rolling');
            if (d2el) d2el.classList.remove('rolling');
            renderGame(_state);
            if (!_state.fun_mode) loadXP();
            if (typeof window._casinoLobbyActivity === 'function' && d.headline) {
                const xp = d.xp_change || 0;
                const xpStr = !d.fun_mode && xp !== 0 ? ` (${xp >= 0 ? '+' : ''}${xp.toLocaleString()} XP)` : '';
                window._casinoLobbyActivity(`🎲 Craps [${d.last_d1}+${d.last_d2}]: ${d.headline}${xpStr}`);
            }
        }, 520);
    } catch(e) {
        if (d1el) d1el.classList.remove('rolling');
        if (d2el) d2el.classList.remove('rolling');
        showError(e.message);
    } finally {
        setTimeout(() => {
            if (btn) { btn.disabled = false; btn.textContent = '🎲 Roll Dice'; }
        }, 540);
    }
}

// ── Clear bets ────────────────────────────────────────────────────────────────
async function clearBets() {
    try {
        const r = await fetch('/api/casino/craps/clear_bets', {
            method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}'
        });
        const d = await r.json();
        if (!r.ok) { showError(d.error || 'Clear failed'); return; }
        _state = d;
        renderGame(_state);
        if (!_state.fun_mode && d.refunded) {
            loadXP();
            showToast(`Refunded ${d.refunded.toLocaleString()} XP`);
        }
    } catch(e) { showError(e.message); }
}

// ── Quit ──────────────────────────────────────────────────────────────────────
async function quit() {
    try {
        await fetch('/api/casino/craps/quit', { method:'POST', headers:{'Content-Type':'application/json'}, body:'{}' });
    } catch { /* silent */ }
    _state = null;
    if (!_state?.fun_mode) loadXP();
    showSetup();
}

// ── Render ────────────────────────────────────────────────────────────────────
function renderGame(state) {
    if (!state) return;

    // Phase bar
    const phaseEl = $('craps-phase-val');
    const puckEl  = $('craps-point-puck');
    if (phaseEl) phaseEl.textContent = state.phase === 'come_out' ? 'Come Out Roll' : `Point Phase`;
    if (puckEl) {
        if (state.point) {
            puckEl.textContent = state.point;
            puckEl.className = 'craps-point-puck on';
        } else {
            puckEl.textContent = 'OFF';
            puckEl.className = 'craps-point-puck off';
        }
    }

    // Dice
    const d1el = $('craps-die-1'), d2el = $('craps-die-2');
    const totalEl = $('craps-total');
    if (state.last_d1 > 0) {
        if (d1el) { d1el.src = `/static/Emojis/Dice/${state.last_color1}${state.last_d1}.png`; d1el.style.display = ''; }
        if (d2el) { d2el.src = `/static/Emojis/Dice/${state.last_color2}${state.last_d2}.png`; d2el.style.display = ''; }
        if (totalEl) totalEl.textContent = state.last_d1 + state.last_d2;
    } else {
        if (d1el) d1el.style.display = 'none';
        if (d2el) d2el.style.display = 'none';
        if (totalEl) totalEl.textContent = '?';
    }

    // Headline
    const hl = $('craps-headline');
    if (hl && state.headline) {
        hl.textContent = state.headline;
        hl.className = 'craps-headline ' + headlineClass(state.event);
    } else if (hl && !state.last_d1) {
        hl.textContent = 'Place your bets, then roll!';
        hl.className = 'craps-headline neutral';
    }

    // Active bets
    renderBets(state.bets);

    // Log
    renderLog(state.log);

    // Bet total
    const totalBetEl = $('craps-total-bet');
    if (totalBetEl) totalBetEl.textContent = (state.total_bet || 0).toLocaleString() + ' XP';

    // Fun mode label
    const modeEl = $('craps-mode-label');
    if (modeEl) modeEl.textContent = state.fun_mode ? 'Fun Mode' : 'Betting Mode';
}

function headlineClass(event) {
    if (!event) return 'neutral';
    if (event === 'come_out_win' || event === 'point_win') return 'win';
    if (event === 'come_out_loss' || event === 'seven_out') return 'lose';
    if (event === 'point_established') return 'info';
    return 'neutral';
}

function renderBets(bets) {
    const el = $('craps-bets-list');
    if (!el) return;
    if (!bets || !bets.length) {
        el.innerHTML = '<span style="color:var(--text-secondary);font-size:0.72rem">No active bets</span>';
        return;
    }
    el.innerHTML = bets.map((b, i) =>
        `<span class="craps-bet-chip">
            ${escHtml(b.type)}: ${b.amount.toLocaleString()}
            <span class="chip-x" data-idx="${i}" title="Remove bet">×</span>
        </span>`
    ).join('');
}

function renderLog(log) {
    const el = $('craps-log');
    if (!el || !log) return;
    if (!log.length) { el.innerHTML = '<div style="color:var(--text-secondary)">No rolls yet.</div>'; return; }
    el.innerHTML = log.map(entry =>
        `<div class="craps-log-entry">${escHtml(entry)}</div>`
    ).join('');
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function showError(msg) {
    const el = $('craps-error');
    if (el) { el.textContent = msg; el.style.display = ''; setTimeout(() => el.style.display = 'none', 4000); }
}

function showToast(msg) {
    const el = $('craps-toast');
    if (!el) return;
    el.textContent = msg;
    el.style.opacity = '1';
    setTimeout(() => { el.style.opacity = '0'; }, 2500);
}

function escHtml(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Boot ──────────────────────────────────────────────────────────────────────
init();

})();

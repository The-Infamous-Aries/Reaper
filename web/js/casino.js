/* ── Casino JS ────────────────────────────────────────────────────────────── */
(function () {
'use strict';

const $ = id => document.getElementById(id);

let _xp      = 0;
let _funMode = false;
let _slots   = { difficulty: null, bet: 0, spinning: false, emojis: [] };

// ── Boot — script tag in casino.html, runs on DOM inject (same as arena/mypet)
function init() {
    const loading = $('casino-loading');
    if (!loading) return;
    _slots = { difficulty: null, bet: 0, spinning: false, emojis: [] };
    _funMode = false;
    _xp = 0;
    showState('loading');
    checkAuth();
    bindEvents();
}

async function checkAuth() {
    try {
        const r = await fetch('/api/casino/xp');
        if (r.status === 401) { showState('login'); return; }
        if (!r.ok) { showState('login'); return; }
        const d = await r.json();
        if (!d.has_pet) { showState('nopet'); return; }
        _xp = d.total_xp || 0;
        updateXPDisplay();
        showState('main');
    } catch(e) {
        console.error('Casino checkAuth failed:', e);
        showState('login');
    }
}

async function refreshXP() {
    try {
        const r = await fetch('/api/casino/xp');
        if (!r.ok) return;
        const d = await r.json();
        if (d.has_pet) { _xp = d.total_xp || 0; updateXPDisplay(); }
    } catch { /* silent */ }
}

function showState(state) {
    $('casino-loading')       && ($('casino-loading').style.display       = state === 'loading' ? '' : 'none');
    $('casino-login-prompt')  && ($('casino-login-prompt').style.display  = state === 'login'   ? '' : 'none');
    $('casino-no-pet')        && ($('casino-no-pet').style.display        = state === 'nopet'   ? '' : 'none');
    $('casino-main')          && ($('casino-main').style.display          = state === 'main'    ? '' : 'none');
}

function updateXPDisplay() {
    const el = $('current-xp');
    if (el) el.textContent = _xp.toLocaleString();
    const el2 = $('slots-current-xp');
    if (el2) el2.textContent = 'XP: ' + _xp.toLocaleString();
}

// ── Events ────────────────────────────────────────────────────────────────
function bindEvents() {
    const toggle = $('fun-mode-toggle');
    if (toggle) toggle.addEventListener('change', e => {
        _funMode = e.target.checked;
        const betSec = $('slots-bet-section');
        if (betSec) betSec.style.display = _funMode ? 'none' : '';
        const modeEl = $('slots-current-mode');
        if (modeEl) modeEl.textContent = _funMode ? 'Fun Mode' : 'Betting Mode';
        checkSlotsReady();
    });

    document.addEventListener('click', e => {
        const btn = e.target.closest('.casino-diff-btn');
        if (!btn || !$('casino-root')) return;
        document.querySelectorAll('.casino-diff-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        _slots.difficulty = btn.dataset.difficulty;
        checkSlotsReady();
    });

    document.addEventListener('click', e => {
        const btn = e.target.closest('.preset-btn');
        if (!btn || !$('casino-root')) return;
        const inp = $('slots-bet-amount');
        if (inp) { inp.value = btn.dataset.amount; _slots.bet = parseInt(inp.value); checkSlotsReady(); }
    });

    document.addEventListener('input', e => {
        if (e.target.id === 'slots-bet-amount') {
            _slots.bet = parseInt(e.target.value) || 0;
            checkSlotsReady();
        }
    });

    document.addEventListener('click', e => {
        if (e.target.id === 'start-slots-btn') startSlots();
        if (e.target.id === 'spin-slots-btn')  spinSlots();
        if (e.target.id === 'slots-play-again') resetSlots();
    });
}

// ── Game open/close ───────────────────────────────────────────────────────
window._casinoOpen = function(game) {
    if (game === 'slots') {
        const panel = $('casino-slots-panel');
        if (panel) { panel.style.display = ''; panel.scrollIntoView({behavior:'smooth', block:'nearest'}); }
        resetSlots();
    }
};

window._casinoOpenGame = function(game) {
    // Navigate to dedicated game page via dashboard router
    if (typeof navigateTo === 'function') {
        navigateTo(game);
    } else {
        // Fallback: push state and load page directly
        history.pushState({ page: game }, '', '?page=' + game);
        if (typeof loadPage === 'function') loadPage(game, null, 'script', null);
    }
};

window._casinoClose = function() {
    const panel = $('casino-slots-panel');
    if (panel) panel.style.display = 'none';
};

// ── Slots ─────────────────────────────────────────────────────────────────
function checkSlotsReady() {
    const btn = $('start-slots-btn');
    if (!btn) return;
    const ready = _slots.difficulty && (_funMode || (_slots.bet >= 10 && _slots.bet <= _xp));
    btn.disabled = !ready;
}

async function startSlots() {
    $('slots-setup').style.display = 'none';
    $('slots-game').style.display  = '';

    const betEl  = $('current-bet');
    const diffEl = $('current-difficulty');
    if (betEl)  betEl.textContent  = _funMode ? '0' : _slots.bet.toLocaleString();
    if (diffEl) diffEl.textContent = _slots.difficulty;

    try {
        const r = await fetch(`/api/casino/slots/emojis/${_slots.difficulty}`);
        if (r.ok) { const d = await r.json(); _slots.emojis = d.emojis || []; }
    } catch { /* use fallback */ }

    if (!_slots.emojis.length) {
        _slots.emojis = [{name:'Cat',path:'/static/Emojis/Pets/Cat.png'},{name:'Dog',path:'/static/Emojis/Pets/Dog.png'}];
    }

    populateReels();

    const reg = $('regular-slots'), ins = $('insanity-slots');
    if (_slots.difficulty === 'Insanity') {
        if (reg) reg.style.display = 'none';
        if (ins) ins.style.display = '';
    } else {
        if (reg) reg.style.display = '';
        if (ins) ins.style.display = 'none';
    }
}

function populateReels() {
    const emojis = _slots.emojis;
    // Each symbol slot = 90px (80px img + 10px margin-bottom)
    // Generate enough symbols to fill the reel and loop smoothly during spin
    const makeContent = () => {
        let h = '';
        for (let i = 0; i < 12; i++) {
            const e = emojis[Math.floor(Math.random() * emojis.length)];
            h += `<img src="${e.path}" alt="${e.name}" style="width:80px;height:80px;object-fit:contain;display:block;margin-bottom:10px;flex-shrink:0">`;
        }
        return h;
    };

    if (_slots.difficulty === 'Insanity') {
        for (let i = 1; i <= 3; i++) {
            const er = $(`element-reel-${i}`), pr = $(`pet-reel-${i}`);
            if (er) er.innerHTML = makeContent();
            if (pr) pr.innerHTML = makeContent();
        }
    } else {
        for (let i = 1; i <= 3; i++) {
            const r = $(`reel-${i}`);
            if (r) r.innerHTML = makeContent();
        }
    }
}

async function spinSlots() {
    if (_slots.spinning) return;
    _slots.spinning = true;

    const spinBtn = $('spin-slots-btn');
    if (spinBtn) { spinBtn.disabled = true; spinBtn.textContent = '🎰 SPINNING...'; }
    $('slots-result-text') && ($('slots-result-text').textContent = '');
    $('slots-winnings')    && ($('slots-winnings').style.display = 'none');
    $('slots-play-again')  && ($('slots-play-again').style.display = 'none');

    document.querySelectorAll('.casino-reel').forEach((r, i) => {
        setTimeout(() => r.classList.add('spinning'), i * 150);
    });

    try {
        const r = await fetch('/api/casino/slots/spin', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({
                theme: _slots.difficulty,
                bet_amount: _funMode ? 0 : _slots.bet,
                fun_mode: _funMode
            })
        });
        const d = await r.json();
        if (!r.ok) throw new Error(d.error || 'Spin failed');
        setTimeout(() => showSlotsResult(d), 2800);
    } catch(e) {
        setTimeout(() => showSlotsResult({result_text: 'Error: ' + e.message, winnings: 0}), 2800);
    }
}

function showSlotsResult(result) {
    document.querySelectorAll('.casino-reel').forEach(r => r.classList.remove('spinning'));

    // Snap the middle symbol of each reel to the server result
    if (result.reels && !result.insanity_mode) {
        result.reels.forEach((sym, i) => {
            const reel = $(`reel-${i + 1}`);
            if (!reel) return;
            // Replace middle 3 imgs (indices 1,2,3 of 12) so the visible window shows result
            const imgs = reel.querySelectorAll('img');
            // Set slots 0,1,2 (the first 3 visible) to: random, result, random
            const pool = _slots.emojis;
            const rand = () => pool[Math.floor(Math.random() * pool.length)];
            const above = rand(), below = rand();
            if (imgs[0]) { imgs[0].src = above.path; imgs[0].alt = above.name; }
            if (imgs[1]) { imgs[1].src = sym.path;   imgs[1].alt = sym.name; }
            if (imgs[2]) { imgs[2].src = below.path;  imgs[2].alt = below.name; }
            // Reset scroll position so slot 0 is at top → result is in middle row
            reel.style.transform = 'translateY(0)';
        });
    }

    const rt = $('slots-result-text');
    if (rt) rt.textContent = result.result_text || '';

    if (result.winnings > 0) {
        const wd = $('slots-winnings'), wa = $('winnings-amount');
        if (wd) wd.style.display = '';
        if (wa) wa.textContent = result.winnings.toLocaleString() + ' XP';
    }

    refreshXP();

    // Post to lobby
    if (typeof window._casinoLobbyActivity === 'function') {
        const msg = result.result_text || '';
        const xp  = result.winnings > 0 ? ` +${result.winnings.toLocaleString()} XP` : '';
        window._casinoLobbyActivity(`🎰 Slots: ${msg}${xp}`);
    }

    const spinBtn = $('spin-slots-btn');
    if (spinBtn) { spinBtn.disabled = false; spinBtn.textContent = '🎰 SPIN'; spinBtn.style.display = 'none'; }

    const pa = $('slots-play-again');
    if (pa) pa.style.display = '';

    _slots.spinning = false;
}

function resetSlots() {
    $('slots-setup').style.display = '';
    $('slots-game').style.display  = 'none';

    _slots = { difficulty: null, bet: 0, spinning: false, emojis: [] };

    document.querySelectorAll('.casino-diff-btn').forEach(b => b.classList.remove('active'));
    const inp = $('slots-bet-amount');
    if (inp) inp.value = '';

    const spinBtn = $('spin-slots-btn');
    if (spinBtn) { spinBtn.style.display = ''; spinBtn.textContent = '🎰 SPIN'; }

    checkSlotsReady();
}

// ── Boot ──────────────────────────────────────────────────────────────────
init();

})();

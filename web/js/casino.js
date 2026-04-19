/* â”€â”€ Casino JS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
(function () {
'use strict';

const $ = id => document.getElementById(id);

let _xp      = 0;
let _funMode = false;
let _slots   = { difficulty: null, bet: 0, spinning: false, emojis: [] };

// â”€â”€ Boot â€” script tag in casino.html, runs on DOM inject (same as arena/mypet)
function init() {
    const loading = $('casino-loading');
    if (!loading) return;
    _slots = { difficulty: null, bet: 0, spinning: false, emojis: [], insanityPools: null };
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

// â”€â”€ Events â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

// â”€â”€ Game open/close â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

// â”€â”€ Slots â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

    if (_slots.difficulty === 'Insanity') {
        // Fetch per-reel pools: Pets, Pet Type, Elements
        const fetchPool = async (theme) => {
            try {
                const r = await fetch(`/api/casino/slots/emojis/${theme}`);
                if (r.ok) { const d = await r.json(); return d.emojis || []; }
            } catch {}
            return [];
        };
        const [pets, types, elements] = await Promise.all([
            fetchPool('Very Hard'),   // Pets
            fetchPool('Very Easy'),   // Pet Type (Flying/Land/Swimming)
            fetchPool('Hard'),        // Elements
        ]);
        _slots.insanityPools = { pets, types, elements };
        _slots.emojis = [...pets, ...types, ...elements]; // fallback
    } else {
        try {
            const r = await fetch(`/api/casino/slots/emojis/${_slots.difficulty}`);
            if (r.ok) { const d = await r.json(); _slots.emojis = d.emojis || []; }
        } catch {}
    }

    if (!_slots.emojis.length) {
        _slots.emojis = [{name:'Cat',path:'/static/Emojis/Pets/Cat.png'},{name:'Dog',path:'/static/Emojis/Pets/Dog.png'}];
    }

    populateReels();

    // Always use regular-slots div; for Insanity just show/hide the 4th reel col
    const reg = $('regular-slots');
    if (reg) reg.style.display = '';
    const reel4Col = $('reel-4-col');
    if (reel4Col) reel4Col.style.display = _slots.difficulty === 'Insanity' ? '' : 'none';
    const labels = $('insanity-labels');
    if (labels) labels.style.display = _slots.difficulty === 'Insanity' ? '' : 'none';
}

function populateReels() {
    const makeContent = (pool) => {
        let h = '';
        for (let i = 0; i < 12; i++) {
            const e = pool[Math.floor(Math.random() * pool.length)];
            h += `<img src="${e.path}" alt="${e.name}" style="width:80px;height:80px;object-fit:contain;display:block;margin-bottom:10px;flex-shrink:0">`;
        }
        return h;
    };

    if (_slots.difficulty === 'Insanity' && _slots.insanityPools) {
        const { pets, types, elements } = _slots.insanityPools;
        // Reel 1 = Species (Pets), Reel 2 = Type (Pet Type), Reel 3 = Element1, Reel 4 = Element2
        const pools = [pets, types, elements, elements];
        for (let i = 1; i <= 4; i++) {
            const r = $(`reel-${i}`);
            const pool = pools[i - 1].length ? pools[i - 1] : _slots.emojis;
            if (r) r.innerHTML = makeContent(pool);
        }
    } else {
        const emojis = _slots.emojis;
        for (let i = 1; i <= 3; i++) {
            const r = $(`reel-${i}`);
            if (r) r.innerHTML = makeContent(emojis);
        }
    }
}

async function spinSlots() {
    if (_slots.spinning) return;
    _slots.spinning = true;

    const spinBtn = $('spin-slots-btn');
    if (spinBtn) { spinBtn.disabled = true; spinBtn.textContent = 'ðŸŽ° SPINNING...'; }
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

    // Always keep the reels wrap visible
    const reg = $('regular-slots');
    if (reg) reg.style.display = '';

    // Snap the middle symbol of each reel to the server result
    if (result.reels) {
        if (result.insanity_mode) {
            // Insanity mode: 3 or 4 targeted reels (Pet, Type, Element1, Element2?)
            const reqs = result.requirements || {};
            const matches = result.matches || {};
            
            // Show/hide 4th reel based on dual-element
            const reel4Col = $('reel-4-col');
            if (reel4Col) reel4Col.style.display = result.reel_count === 4 ? '' : 'none';
            
            // Update labels to show "need X | got Y âœ“/âœ—"
            const reelLabels = [
                { id: 'label-species',  need: reqs.species,  got: result.reels[0]?.name, match: matches.species },
                { id: 'label-type',     need: reqs.type,     got: result.reels[1]?.name, match: matches.type },
                { id: 'label-element1', need: reqs.element1, got: result.reels[2]?.name, match: matches.element1 },
            ];
            if (reqs.element2 && result.reels[3]) {
                reelLabels.push({ id: 'label-element2', need: reqs.element2, got: result.reels[3]?.name, match: matches.element2 });
            }
            reelLabels.forEach(l => {
                const el = $(l.id);
                if (!el) return;
                const cap = s => s ? s.charAt(0).toUpperCase() + s.slice(1) : '';
                el.textContent = cap(l.need);
                el.style.color = l.match ? '#2ecc71' : 'var(--gold-secondary)';
            });
            const e2Wrap = $('label-element2-wrap');
            if (e2Wrap) e2Wrap.style.display = reqs.element2 ? '' : 'none';
            const labels = $('insanity-labels');
            if (labels) labels.style.display = '';
            
            // Render reels â€” set all 3 visible slots, center one is the result
            result.reels.forEach((sym, i) => {
                const reel = $(`reel-${i + 1}`);
                if (!reel) return;
                const imgs = reel.querySelectorAll('img');
                const isMatch = i === 0 ? matches.species : i === 1 ? matches.type : i === 2 ? matches.element1 : matches.element2;
                const border = isMatch ? '3px solid #2ecc71' : '2px solid rgba(255,255,255,0.1)';
                // Set the center (middle) image to the result symbol
                if (imgs[1]) {
                    imgs[1].src = sym.path;
                    imgs[1].alt = sym.name;
                    imgs[1].style.border = border;
                    imgs[1].style.borderRadius = '8px';
                }
                reel.style.transform = 'translateY(0)';
            });
        } else {
            // Regular mode: 3 reels
            // Hide 4th reel and labels
            const reel4Col = $('reel-4-col');
            if (reel4Col) reel4Col.style.display = 'none';
            const labels = $('insanity-labels');
            if (labels) labels.style.display = 'none';
            
            result.reels.forEach((sym, i) => {
                const reel = $(`reel-${i + 1}`);
                if (!reel) return;
                const imgs = reel.querySelectorAll('img');
                const pool = _slots.emojis;
                const rand = () => pool[Math.floor(Math.random() * pool.length)];
                const above = rand(), below = rand();
                if (imgs[0]) { imgs[0].src = above.path; imgs[0].alt = above.name; imgs[0].style.border = ''; }
                if (imgs[1]) { imgs[1].src = sym.path;   imgs[1].alt = sym.name; imgs[1].style.border = ''; }
                if (imgs[2]) { imgs[2].src = below.path;  imgs[2].alt = below.name; imgs[2].style.border = ''; }
                reel.style.transform = 'translateY(0)';
            });
        }
    }

    const rt = $('slots-result-text');
    if (rt) rt.textContent = result.result_text || '';

    const wd = $('slots-winnings'), wa = $('winnings-amount');
    if (result.winnings > 0) {
        if (wd) wd.style.display = '';
        if (wa) wa.textContent = result.winnings.toLocaleString() + ' XP';
    } else {
        // Explicitly hide so a previous win's amount doesn't linger
        if (wd) wd.style.display = 'none';
        if (wa) wa.textContent = '0 XP';
    }

    refreshXP();

    // Post to lobby
    if (typeof window._casinoLobbyActivity === 'function') {
        const msg = result.result_text || '';
        const xp  = result.winnings > 0 ? ` +${result.winnings.toLocaleString()} XP` : '';
        window._casinoLobbyActivity(`ðŸŽ° Slots: ${msg}${xp}`);
    }

    const spinBtn = $('spin-slots-btn');
    if (spinBtn) { spinBtn.disabled = false; spinBtn.textContent = 'ðŸŽ° SPIN'; spinBtn.style.display = 'none'; }

    const pa = $('slots-play-again');
    if (pa) pa.style.display = '';

    _slots.spinning = false;
}

function resetSlots() {
    $('slots-setup').style.display = '';
    $('slots-game').style.display  = 'none';

    _slots = { difficulty: null, bet: 0, spinning: false, emojis: [], insanityPools: null };

    document.querySelectorAll('.casino-diff-btn').forEach(b => b.classList.remove('active'));
    const inp = $('slots-bet-amount');
    if (inp) inp.value = '';

    const spinBtn = $('spin-slots-btn');
    if (spinBtn) { spinBtn.style.display = ''; spinBtn.textContent = 'ðŸŽ° SPIN'; }

    checkSlotsReady();
}

// â”€â”€ Boot â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
init();

// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

})(); // end casino.js IIFE


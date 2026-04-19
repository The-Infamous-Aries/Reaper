/* ── Mega Keno JS ─────────────────────────────────────────────────────────── */
(function () {
'use strict';

const $ = id => document.getElementById(id);

// ── State ─────────────────────────────────────────────────────────────────
let _xp       = 0;
let _funMode  = false;
let _bet      = 0;
let _running  = false;

// Selections
let _selType     = null;   // single string
let _selElements = [];     // up to 3
let _selPets     = [];     // up to 10

// Static data (loaded from API)
let _types    = [];
let _elements = [];
let _pets     = [];

// ── Keno odds & payout tables ─────────────────────────────────────────────
// Pet draw: pick 10, bot draws 20 from 103
// Hypergeometric distribution — exact probabilities for 4-10 matches
// P(k matches) = C(10,k)*C(93,20-k)/C(103,20)
// Base multipliers calibrated for ~80% RTP across all outcomes
const PET_PAYOUTS = {
    // matches: multiplier on bet (0 = loss)
    0:  0,
    1:  0,
    2:  0,
    3:  0,
    4:  1.5,    // ~18.7% chance of 4+ → pays 1.5×
    5:  3.5,    // ~8.4%
    6:  10,     // ~2.5%
    7:  35,     // ~0.47%
    8:  150,    // ~0.054%
    9:  800,    // ~0.0035%
    10: 5000,   // ~0.000097%
};

// Element draw: pick 3, bot draws 3 from 13
// P(k matches) = C(3,k)*C(10,3-k)/C(13,3)
// Multipliers applied ON TOP of base payout
const ELEMENT_MULTIPLIERS = {
    0: 1,    // no bonus (base only)
    1: 1,    // 1 match — no bonus
    2: 2.5,  // 2 matches → 2.5× multiplier
    3: 8,    // 3 matches → 8× multiplier
};

// Type draw: pick 1, bot draws 1 from 3
// P(hit) = 1/3
// MEGA multiplier applied on top of element multiplier
const TYPE_MULTIPLIER = 5;  // 1/3 chance → 5× (slightly below fair 3× for house edge, but stacked = massive)

// ── Boot ──────────────────────────────────────────────────────────────────
function init() {
    if (!$('keno-root')) return;
    showState('loading');
    checkAuth();
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
        await loadEmojis();
        buildUI();
        showState('main');
    } catch(e) {
        console.error('[keno] checkAuth failed:', e);
        showState('login');
    }
}

async function loadEmojis() {
    const r = await fetch('/api/casino/keno/emojis');
    if (!r.ok) throw new Error('Failed to load keno emojis');
    const d = await r.json();
    _types    = d.types    || [];
    _elements = d.elements || [];
    _pets     = d.pets     || [];
}

// ── UI builders ───────────────────────────────────────────────────────────
function buildUI() {
    buildTypeRow();
    buildElementRow();
    buildPetGrid();
}

function buildTypeRow() {
    const row = $('keno-type-row');
    if (!row) return;
    row.innerHTML = '';
    _types.forEach(t => {
        const el = document.createElement('div');
        el.className = 'keno-pick-item';
        el.dataset.name = t.name;
        el.innerHTML = `<img src="${t.path}" alt="${t.name}" loading="lazy"><div class="keno-pick-label">${t.name}</div>`;
        el.addEventListener('click', () => toggleType(t.name, el));
        row.appendChild(el);
    });
}

function buildElementRow() {
    const row = $('keno-element-row');
    if (!row) return;
    row.innerHTML = '';
    _elements.forEach(e => {
        const el = document.createElement('div');
        el.className = 'keno-pick-item';
        el.dataset.name = e.name;
        el.innerHTML = `<img src="${e.path}" alt="${e.name}" loading="lazy"><div class="keno-pick-label">${e.name}</div>`;
        el.addEventListener('click', () => toggleElement(e.name, el));
        row.appendChild(el);
    });
}

function buildPetGrid() {
    const grid = $('keno-pet-grid');
    if (!grid) return;
    grid.innerHTML = '';
    _pets.forEach(p => {
        const el = document.createElement('div');
        el.className = 'keno-pet-item';
        el.dataset.name = p.name;
        el.innerHTML = `<img src="${p.path}" alt="${p.name}" loading="lazy"><div class="keno-pet-name">${p.name}</div>`;
        el.addEventListener('click', () => togglePet(p.name, el));
        grid.appendChild(el);
    });
}

// ── Selection toggles ─────────────────────────────────────────────────────
function toggleType(name, el) {
    if (_running) return;
    // Deselect previous
    document.querySelectorAll('#keno-type-row .keno-pick-item').forEach(i => i.classList.remove('selected'));
    if (_selType === name) {
        _selType = null;
    } else {
        _selType = name;
        el.classList.add('selected');
    }
    checkReady();
}

function toggleElement(name, el) {
    if (_running) return;
    const idx = _selElements.indexOf(name);
    if (idx >= 0) {
        _selElements.splice(idx, 1);
        el.classList.remove('selected');
    } else {
        if (_selElements.length >= 3) return; // max 3
        _selElements.push(name);
        el.classList.add('selected');
    }
    checkReady();
}

function togglePet(name, el) {
    if (_running) return;
    const idx = _selPets.indexOf(name);
    if (idx >= 0) {
        _selPets.splice(idx, 1);
        el.classList.remove('selected');
        el.classList.remove('disabled');
    } else {
        if (_selPets.length >= 10) return; // max 10
        _selPets.push(name);
        el.classList.add('selected');
    }
    // Disable unselected items when at 10
    const atMax = _selPets.length >= 10;
    document.querySelectorAll('#keno-pet-grid .keno-pet-item').forEach(i => {
        if (!i.classList.contains('selected')) {
            i.classList.toggle('disabled', atMax);
        }
    });
    const countEl = $('keno-pet-count');
    if (countEl) countEl.textContent = _selPets.length;
    checkReady();
}

function checkReady() {
    const btn = $('keno-play-btn');
    if (!btn) return;
    const betOk = _funMode || (_bet >= 10);
    const ready = _selType && _selElements.length === 3 && _selPets.length === 10 && betOk;
    btn.disabled = !ready;
}

// ── Events ────────────────────────────────────────────────────────────────
function bindEvents() {
    const toggle = $('keno-fun-mode-toggle');
    if (toggle) toggle.addEventListener('change', e => {
        _funMode = e.target.checked;
        const betSec = $('keno-bet-section');
        if (betSec) betSec.style.display = _funMode ? 'none' : '';
        checkReady();
    });

    document.addEventListener('input', e => {
        if (e.target.id === 'keno-bet-amount') {
            _bet = parseInt(e.target.value) || 0;
            checkReady();
        }
    });

    document.addEventListener('click', e => {
        const btn = e.target.closest('.keno-preset');
        if (!btn || !$('keno-root')) return;
        const inp = $('keno-bet-amount');
        if (inp) { inp.value = btn.dataset.amount; _bet = parseInt(inp.value); checkReady(); }
    });

    document.addEventListener('click', e => {
        if (e.target.id === 'keno-play-btn')       startGame();
        if (e.target.id === 'keno-play-again-btn') resetGame();
    });
}

// ── Game flow ─────────────────────────────────────────────────────────────
async function startGame() {
    if (_running) return;
    _running = true;
    $('keno-play-btn').disabled = true;

    // Clear any leftover draw state from previous round
    clearDrawState();

    // Show result panel below setup
    $('keno-game-panel').style.display = '';
    $('keno-final-result').style.display = 'none';
    $('keno-play-again-btn').style.display = 'none';
    $('keno-pet-result-text').style.display     = 'none';
    $('keno-element-result-text').style.display = 'none';
    $('keno-type-result-text').style.display    = 'none';
    $('keno-pet-result-text').textContent     = '';
    $('keno-element-result-text').textContent = '';
    $('keno-type-result-text').textContent    = '';

    // Reset payout bar
    $('keno-display-bet').textContent   = _funMode ? 'Fun' : _bet.toLocaleString() + ' XP';
    $('keno-display-base').textContent  = '—';
    $('keno-display-total').textContent = '—';
    $('keno-elem-payout-item').style.display = 'none';
    $('keno-mega-payout-item').style.display = 'none';

    // Scroll to top of setup so player watches their own grid
    $('keno-setup').scrollIntoView({ behavior: 'smooth', block: 'start' });

    try {
        const resp = await fetch('/api/casino/keno/play', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                bet_amount:      _funMode ? 0 : _bet,
                fun_mode:        _funMode,
                picked_type:     _selType,
                picked_elements: _selElements,
                picked_pets:     _selPets,
            })
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            alert(err.error || 'Something went wrong. Please try again.');
            resetGame();
            return;
        }

        const result = await resp.json();
        await runAnimation(result);

    } catch(e) {
        console.error('[keno] play error:', e);
        alert('Network error. Please try again.');
        resetGame();
    }
}

// ── Clear draw-state classes from all tiles ───────────────────────────────
function clearDrawState() {
    document.querySelectorAll('#keno-pet-grid .keno-pet-item').forEach(el => {
        el.classList.remove('bot-drawn', 'bot-hit', 'bot-miss', 'bot-scanning', 'disabled');
    });
    document.querySelectorAll('#keno-element-row .keno-pick-item').forEach(el => {
        el.classList.remove('bot-drawn', 'bot-hit', 'bot-miss', 'bot-scanning');
    });
    document.querySelectorAll('#keno-type-row .keno-pick-item').forEach(el => {
        el.classList.remove('bot-drawn', 'bot-hit', 'bot-miss', 'bot-scanning', 'mega-cycling');
    });
}

// ── Animation engine ──────────────────────────────────────────────────────
async function runAnimation(result) {
    const drawnPets  = result.drawn_pets;   // [{name,path}, ...]
    const petHits    = result.pet_hits;     // [name, ...]
    const petMatches = result.pet_matches;

    // ── PHASE 1: Pet draw — light up tiles on the grid ───────────────────
    // Dim everything first
    document.querySelectorAll('#keno-pet-grid .keno-pet-item').forEach(el => {
        el.classList.add('bot-scanning');
    });
    await sleep(200);

    // Reveal bot's 20 picks one by one directly on the grid
    for (let i = 0; i < drawnPets.length; i++) {
        await sleep(70);
        const name = drawnPets[i].name;
        const tile = document.querySelector(`#keno-pet-grid .keno-pet-item[data-name="${name}"]`);
        if (!tile) continue;
        tile.classList.remove('bot-scanning');
        const isHit = petHits.includes(name);
        if (isHit) {
            tile.classList.add('bot-hit');
            spawnParticles(tile, '#4cff88', 8);
        } else {
            tile.classList.add('bot-drawn');
        }
    }

    // After all drawn, mark player's non-drawn picks as misses
    await sleep(300);
    _selPets.forEach(name => {
        if (!petHits.includes(name)) {
            const tile = document.querySelector(`#keno-pet-grid .keno-pet-item[data-name="${name}"]`);
            if (tile) tile.classList.add('bot-miss');
        }
    });
    // Un-dim everything that wasn't drawn
    document.querySelectorAll('#keno-pet-grid .keno-pet-item.bot-scanning').forEach(el => {
        el.classList.remove('bot-scanning');
    });

    await sleep(400);

    // Pet result text
    const basePayout  = result.base_payout;
    const petResultEl = $('keno-pet-result-text');
    petResultEl.style.display = '';
    if (petMatches >= 4) {
        petResultEl.innerHTML = `<span style="color:#4cff88;font-weight:700">🎉 ${petMatches} matches! Base payout: ${_funMode ? 'Fun' : basePayout.toLocaleString() + ' XP'}</span>`;
        $('keno-display-base').textContent = _funMode ? 'Fun' : basePayout.toLocaleString() + ' XP';
        spawnParticles(petResultEl, '#4cff88', 20);
    } else {
        petResultEl.innerHTML = `<span style="color:var(--text-secondary)">${petMatches} match${petMatches !== 1 ? 'es' : ''} — need 4+ to trigger Element Bonus</span>`;
        $('keno-display-base').textContent = '0 XP';
    }

    await sleep(800);

    // ── PHASE 2: Element draw — fancier, on the element row ──────────────
    if (result.element_draw_triggered) {
        const drawnElems  = result.drawn_elements; // [{name,path}]
        const elemHits    = result.element_hits;
        const elemMatches = result.element_matches;

        // Pulse-scan the element row
        document.querySelectorAll('#keno-element-row .keno-pick-item').forEach(el => {
            el.classList.add('bot-scanning');
        });
        await sleep(350);

        // Reveal each drawn element with a bigger pop
        for (let i = 0; i < drawnElems.length; i++) {
            await sleep(320);
            const name = drawnElems[i].name;
            const tile = document.querySelector(`#keno-element-row .keno-pick-item[data-name="${name}"]`);
            if (!tile) continue;
            tile.classList.remove('bot-scanning');
            const isHit = elemHits.includes(name);
            if (isHit) {
                tile.classList.add('bot-hit', 'bot-hit--elem');
                spawnParticles(tile, '#b464ff', 18);
                spawnParticles(tile, '#ffffff', 8);
            } else {
                tile.classList.add('bot-drawn', 'bot-drawn--elem');
            }
        }

        await sleep(300);
        // Mark player's non-hit element picks as misses
        _selElements.forEach(name => {
            if (!elemHits.includes(name)) {
                const tile = document.querySelector(`#keno-element-row .keno-pick-item[data-name="${name}"]`);
                if (tile) tile.classList.add('bot-miss');
            }
        });
        document.querySelectorAll('#keno-element-row .keno-pick-item.bot-scanning').forEach(el => {
            el.classList.remove('bot-scanning');
        });

        await sleep(400);

        const elemMult    = result.element_multiplier;
        const elemResultEl = $('keno-element-result-text');
        elemResultEl.style.display = '';
        if (elemMatches >= 2) {
            elemResultEl.innerHTML = `<span style="color:#b464ff;font-weight:700">✨ ${elemMatches} element match${elemMatches !== 1 ? 'es' : ''}! ×${elemMult} multiplier!</span>`;
            $('keno-elem-payout-item').style.display = '';
            $('keno-display-elem-mult').textContent = '×' + elemMult;
            spawnParticles(elemResultEl, '#b464ff', 28);
        } else {
            elemResultEl.innerHTML = `<span style="color:var(--text-secondary)">${elemMatches} element match — need 2+ for Type MEGA Bonus</span>`;
        }

        await sleep(800);

        // ── PHASE 3: Type draw — MEGA, on the type row ───────────────────
        if (result.type_draw_triggered) {
            const drawnType = result.drawn_type; // {name, path}
            const typeHit   = result.type_hit;

            // Rapid cycling scan across all 3 type tiles
            const typeTiles = Array.from(document.querySelectorAll('#keno-type-row .keno-pick-item'));
            spawnParticles($('keno-type-row'), '#ff6464', 30);
            spawnParticles($('keno-type-row'), '#ffd700', 30);

            // Cycle highlight rapidly across tiles 6 times before landing
            for (let cycle = 0; cycle < 6; cycle++) {
                for (const tile of typeTiles) {
                    tile.classList.add('mega-cycling');
                    await sleep(90 + cycle * 18); // slows down each pass
                    tile.classList.remove('mega-cycling');
                }
            }

            await sleep(200);

            // Land on the drawn type
            const drawnTile = document.querySelector(`#keno-type-row .keno-pick-item[data-name="${drawnType.name}"]`);
            if (drawnTile) {
                if (typeHit) {
                    drawnTile.classList.add('bot-hit', 'bot-hit--mega');
                    spawnParticles(drawnTile, '#ff6464', 40);
                    spawnParticles(drawnTile, '#ffd700', 40);
                    await sleep(200);
                    spawnParticles(drawnTile, '#b464ff', 25);
                } else {
                    drawnTile.classList.add('bot-drawn', 'bot-miss');
                    // Mark player's pick as miss if different
                    const playerTile = document.querySelector(`#keno-type-row .keno-pick-item[data-name="${_selType}"]`);
                    if (playerTile && _selType !== drawnType.name) playerTile.classList.add('bot-miss');
                }
            }

            await sleep(500);

            const typeMult    = result.type_multiplier;
            const typeResultEl = $('keno-type-result-text');
            typeResultEl.style.display = '';
            if (typeHit) {
                typeResultEl.innerHTML = `<span style="color:#ff6464;font-weight:700;font-size:1rem">🌟 MEGA BONUS! ${drawnType.name} matched! ×${typeMult} MEGA multiplier!</span>`;
                $('keno-mega-payout-item').style.display = '';
                $('keno-display-mega-mult').textContent = '×' + typeMult;
                spawnParticles(typeResultEl, '#ff6464', 50);
                spawnParticles(typeResultEl, '#ffd700', 50);
                await sleep(300);
                spawnParticles(typeResultEl, '#b464ff', 30);
            } else {
                typeResultEl.innerHTML = `<span style="color:var(--text-secondary)">Drawn: ${drawnType.name} — your pick was ${_selType}. No MEGA Bonus.</span>`;
            }

            await sleep(600);
        }
    }

    // ── Final result ──────────────────────────────────────────────────────
    await sleep(300);
    const totalWon   = result.total_winnings;
    const finalBlock = $('keno-final-result');
    const finalText  = $('keno-final-text');
    const finalWin   = $('keno-final-winnings');

    $('keno-display-total').textContent = _funMode ? 'Fun Mode' : totalWon.toLocaleString() + ' XP';

    if (totalWon > 0 && !_funMode) {
        finalText.textContent = '🎉 You Won!';
        finalWin.textContent  = '+' + totalWon.toLocaleString() + ' XP';
        finalWin.style.color  = '#4cff88';
        spawnParticles(finalBlock, '#ffd700', 60);
        spawnParticles(finalBlock, '#4cff88', 30);
    } else if (_funMode) {
        finalText.textContent = petMatches >= 4 ? '🎉 Fun Win!' : '😔 No win this time.';
        finalWin.textContent  = 'Fun Mode — no XP wagered';
        finalWin.style.color  = 'var(--text-secondary)';
    } else {
        finalText.textContent = '😔 Better luck next time!';
        finalWin.textContent  = _bet > 0 ? '-' + _bet.toLocaleString() + ' XP' : '';
        finalWin.style.color  = '#ff6464';
    }

    // Scroll to results
    $('keno-game-panel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    finalBlock.style.display = '';
    $('keno-play-again-btn').style.display = '';

    if (!_funMode) refreshXP();
    _running = false;
}

// ── Helpers ───────────────────────────────────────────────────────────────
function sleep(ms) {
    return new Promise(r => setTimeout(r, ms));
}

function spawnParticles(anchor, color, count) {
    const rect = anchor.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top  + rect.height / 2;
    for (let i = 0; i < count; i++) {
        const p = document.createElement('div');
        p.className = 'keno-particle';
        const angle = Math.random() * Math.PI * 2;
        const dist  = 60 + Math.random() * 160;
        p.style.cssText = `
            left:${cx}px; top:${cy}px;
            width:${4 + Math.random()*6}px; height:${4 + Math.random()*6}px;
            background:${color};
            --dx:${Math.cos(angle)*dist}px;
            --dy:${Math.sin(angle)*dist}px;
            animation-delay:${Math.random()*0.3}s;
            animation-duration:${0.8 + Math.random()*0.6}s;
        `;
        document.body.appendChild(p);
        p.addEventListener('animationend', () => p.remove());
    }
}

function showState(state) {
    $('keno-loading')       && ($('keno-loading').style.display       = state === 'loading' ? '' : 'none');
    $('keno-login-prompt')  && ($('keno-login-prompt').style.display  = state === 'login'   ? '' : 'none');
    $('keno-no-pet')        && ($('keno-no-pet').style.display        = state === 'nopet'   ? '' : 'none');
    $('keno-main')          && ($('keno-main').style.display          = state === 'main'    ? '' : 'none');
}

function updateXP() {
    const el = $('keno-current-xp');
    if (el) el.textContent = _xp.toLocaleString();
}

async function refreshXP() {
    try {
        const r = await fetch('/api/casino/xp');
        if (!r.ok) return;
        const d = await r.json();
        if (d.has_pet) { _xp = d.total_xp || 0; updateXP(); }
    } catch { /* silent */ }
}

function resetGame() {
    _running = false;

    // Clear all draw-state highlights from tiles
    clearDrawState();

    // Re-enable disabled pet tiles
    document.querySelectorAll('#keno-pet-grid .keno-pet-item').forEach(i => {
        if (!i.classList.contains('selected')) {
            i.classList.toggle('disabled', _selPets.length >= 10);
        }
    });

    // Hide results panel, re-enable play button
    $('keno-game-panel').style.display = 'none';
    $('keno-play-btn').disabled = false;
    checkReady();

    // Scroll back up to setup
    $('keno-setup').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Back to casino ────────────────────────────────────────────────────────
window._kenoBack = function() {
    if (typeof navigateTo === 'function') {
        navigateTo('casino');
    } else {
        history.pushState({ page: 'casino' }, '', '?page=casino');
        if (typeof loadPage === 'function') loadPage('casino', null, 'script', null);
    }
};

// ── Init ──────────────────────────────────────────────────────────────────
init();

})();

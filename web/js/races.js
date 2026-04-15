/* ── Pet Races JS ─────────────────────────────────────────────────────────── */
(function () {
'use strict';

const $ = id => document.getElementById(id);

// ── State ─────────────────────────────────────────────────────────────────────
let _xp         = 0;
let _bet        = 0;
let _difficulty = 'apprentice';
let _funMode    = false;
let _raceData   = null;   // full server response
let _animFrame  = null;
let _tickIdx    = 0;
let _running    = false;

const MAX_SEGMENTS = 10;

// ── Boot ──────────────────────────────────────────────────────────────────────
function init() {
    if (!$('race-root')) return;
    _xp = 0; _bet = 0; _raceData = null; _running = false;
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
    const el = $('race-xp-display');
    if (el) el.textContent = _xp.toLocaleString() + ' XP';
}

// ── Setup ─────────────────────────────────────────────────────────────────────
function showSetup() {
    $('race-setup-screen').style.display = '';
    $('race-game-screen').style.display  = 'none';
    $('race-result-area').style.display  = 'none';
    updateStartBtn();
}

function showGame() {
    $('race-setup-screen').style.display = 'none';
    $('race-game-screen').style.display  = '';
}

// ── Events ────────────────────────────────────────────────────────────────────
function bindEvents() {
    // Difficulty
    document.addEventListener('click', e => {
        const btn = e.target.closest('.race-diff-btn');
        if (!btn || !$('race-root')) return;
        document.querySelectorAll('.race-diff-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
        _difficulty = btn.dataset.diff;
        updateStartBtn();
    });

    // Fun mode
    document.addEventListener('change', e => {
        if (e.target.id !== 'race-fun-toggle') return;
        _funMode = e.target.checked;
        const betRow = $('race-bet-row');
        if (betRow) betRow.style.display = _funMode ? 'none' : '';
        updateStartBtn();
    });

    // Bet input
    document.addEventListener('input', e => {
        if (e.target.id === 'race-bet-input') {
            _bet = parseInt(e.target.value) || 0;
            updateStartBtn();
        }
    });

    // Bet presets
    document.addEventListener('click', e => {
        const btn = e.target.closest('.race-bet-preset');
        if (!btn || !$('race-root')) return;
        const inp = $('race-bet-input');
        if (inp) { inp.value = btn.dataset.amount; _bet = parseInt(btn.dataset.amount); updateStartBtn(); }
    });

    // Start
    document.addEventListener('click', e => {
        if (e.target.id === 'race-start-btn') startRace();
    });

    // Post-race actions
    document.addEventListener('click', e => {
        if (!$('race-root')) return;
        if (e.target.id === 'race-continue-btn') continueRace();
        if (e.target.id === 'race-cashout-btn')  cashOut();
        if (e.target.id === 'race-again-btn')    showSetup();
        if (e.target.id === 'race-quit-btn')     quit();
    });
}

function updateStartBtn() {
    const btn = $('race-start-btn');
    if (!btn) return;
    const ok = _funMode || (_bet >= 10 && _bet <= _xp);
    btn.disabled = !ok;
}

// ── Start race ────────────────────────────────────────────────────────────────
async function startRace() {
    const btn = $('race-start-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Loading...'; }
    try {
        const r = await fetch('/api/casino/races/start', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ difficulty: _difficulty, bet: _funMode ? 0 : _bet, fun_mode: _funMode })
        });
        const d = await r.json();
        if (!r.ok) { showError(d.error || 'Failed to start'); return; }
        _raceData = d;
        showGame();
        buildTrack(d);
        startCountdown(() => animateRace(d));
    } catch(e) { showError(e.message); }
    finally { if (btn) { btn.disabled = false; btn.textContent = 'Start Race!'; } }
}

// ── Build track DOM ───────────────────────────────────────────────────────────
function buildTrack(data) {
    const area = $('race-track-area');
    if (!area) return;

    // Clear old lanes
    area.querySelectorAll('.race-lane').forEach(l => l.remove());

    data.racers.forEach((racer, i) => {
        const lane = document.createElement('div');
        lane.className = 'race-lane';
        lane.id = `lane-${racer.id}`;

        const nameEl = document.createElement('div');
        nameEl.className = 'race-lane-name' + (racer.is_player ? ' is-player' : '');
        nameEl.textContent = racer.name;

        const track = document.createElement('div');
        track.className = 'race-lane-track';
        track.id = `track-${racer.id}`;

        const pet = document.createElement('img');
        pet.className = 'race-pet' + (racer.is_player ? ' is-player' : '');
        pet.id = `pet-${racer.id}`;
        pet.src = racer.img;
        pet.alt = racer.species;
        pet.onerror = () => { pet.src = '/static/Emojis/Pets/Cat.png'; };
        pet.style.left = '0px';

        const badge = document.createElement('div');
        badge.className = 'race-finish-badge';
        badge.id = `badge-${racer.id}`;

        const speedWrap = document.createElement('div');
        speedWrap.className = 'race-speed-bar-wrap';
        const speedBar = document.createElement('div');
        speedBar.className = 'race-speed-bar';
        speedBar.id = `speed-${racer.id}`;
        speedBar.style.width = '0%';
        speedWrap.appendChild(speedBar);

        track.appendChild(pet);
        track.appendChild(badge);
        track.appendChild(speedWrap);
        lane.appendChild(nameEl);
        lane.appendChild(track);
        area.appendChild(lane);
    });

    // Result area hidden during race
    const resultArea = $('race-result-area');
    if (resultArea) resultArea.style.display = 'none';
}

// ── Countdown ─────────────────────────────────────────────────────────────────
function startCountdown(cb) {
    const area = $('race-track-area');
    if (!area) { cb(); return; }

    const counts = ['3', '2', '1', 'GO!'];
    let i = 0;

    function showNext() {
        // Remove old overlay
        const old = area.querySelector('.race-countdown');
        if (old) old.remove();

        if (i >= counts.length) { cb(); return; }

        const overlay = document.createElement('div');
        overlay.className = 'race-countdown';
        overlay.textContent = counts[i];
        area.appendChild(overlay);
        i++;

        // Remove after animation
        setTimeout(() => {
            overlay.remove();
            showNext();
        }, 850);
    }
    showNext();
}

// ── Animate race ──────────────────────────────────────────────────────────────
function animateRace(data) {
    _running  = true;
    _tickIdx  = 0;
    const ticks    = data.ticks;
    const racers   = data.racers;
    const maxSegs  = data.max_segments;
    const tickMs   = data.tick_ms || 180;   // server-controlled pace

    // Apply CSS transition so movement between ticks is smooth
    racers.forEach(racer => {
        const petEl   = $(`pet-${racer.id}`);
        const speedEl = $(`speed-${racer.id}`);
        if (petEl)   petEl.style.transition   = `left ${tickMs * 0.9}ms ease-out`;
        if (speedEl) speedEl.style.transition = `width ${tickMs * 0.9}ms ease-out`;
    });

    // Track width for positioning
    function getTrackWidth(racerId) {
        const track = $(`track-${racerId}`);
        return track ? track.clientWidth - 60 : 200;
    }

    let lastTick = performance.now();

    function step(now) {
        if (!_running) return;
        if (now - lastTick < tickMs) { _animFrame = requestAnimationFrame(step); return; }
        lastTick = now;

        if (_tickIdx >= ticks.length) {
            finishRace(data);
            return;
        }

        const tick = ticks[_tickIdx];
        racers.forEach((racer, i) => {
            const progress = tick[i];
            const pct      = Math.min(progress / maxSegs, 1);
            const trackW   = getTrackWidth(racer.id);
            const leftPx   = Math.round(pct * trackW);

            const petEl    = $(`pet-${racer.id}`);
            const speedEl  = $(`speed-${racer.id}`);
            if (petEl)   petEl.style.left  = leftPx + 'px';
            if (speedEl) speedEl.style.width = (pct * 100).toFixed(1) + '%';
        });

        _tickIdx++;
        _animFrame = requestAnimationFrame(step);
    }

    _animFrame = requestAnimationFrame(step);
}

function finishRace(data) {
    _running = false;
    if (_animFrame) { cancelAnimationFrame(_animFrame); _animFrame = null; }

    const finishOrder = data.finish_order;
    const racers      = data.racers;

    // Remove transitions before snapping to final position
    racers.forEach(racer => {
        const petEl   = $(`pet-${racer.id}`);
        const speedEl = $(`speed-${racer.id}`);
        if (petEl)   petEl.style.transition   = 'none';
        if (speedEl) speedEl.style.transition = 'none';
    });

    // Snap all pets to finish line
    racers.forEach(racer => {
        const petEl   = $(`pet-${racer.id}`);
        const speedEl = $(`speed-${racer.id}`);
        const track   = $(`track-${racer.id}`);
        if (petEl && track) {
            const trackW = track.clientWidth - 60;
            petEl.style.left = trackW + 'px';
        }
        if (speedEl) speedEl.style.width = '100%';
    });

    // Show finish badges with delay
    finishOrder.forEach((racerIdx, pos) => {
        const racer = racers[racerIdx];
        setTimeout(() => {
            const badge = $(`badge-${racer.id}`);
            if (!badge) return;
            const labels = ['🥇 1st', '🥈 2nd', '🥉 3rd', '4th'];
            badge.textContent = labels[pos] || `${pos+1}th`;
            badge.className = `race-finish-badge show pos-${pos+1}`;
        }, pos * 200);
    });

    // Show result after badges
    setTimeout(() => showResult(data), finishOrder.length * 200 + 400);
}

// ── Result ────────────────────────────────────────────────────────────────────
function showResult(data) {
    const area = $('race-result-area');
    if (!area) return;

    const won        = data.player_won;
    const streak     = data.win_streak;
    const pendingXP  = data.pending_xp;
    const pendingKeys = data.pending_keys || [];
    const funMode    = data.fun_mode;

    let html = `<div class="race-result">`;
    html += `<div class="race-result-title ${won ? 'win' : 'lose'}">${won ? '🏆 You Win!' : '💀 You Lost!'}</div>`;

    if (won) {
        html += `<div class="race-streak-badge">🔥 Win Streak: ${streak}</div>`;
        if (!funMode) {
            html += `<div class="race-pending-box">
                <div>Pending Winnings</div>
                <div class="pending-xp">+${pendingXP.toLocaleString()} XP</div>
                ${pendingKeys.length ? `<div class="pending-keys">🗝️ ${pendingKeys.join(', ')}</div>` : ''}
                <div style="font-size:0.68rem;color:var(--text-secondary);margin-top:6px">
                    Continue racing to multiply your streak bonus, or cash out now.
                </div>
            </div>`;
        } else {
            html += `<div style="font-size:0.82rem;color:var(--text-secondary);margin:8px 0">Fun Mode — no XP wagered.</div>`;
        }
        html += `<div class="race-actions">`;
        if (!funMode) {
            html += `<button class="race-btn race-btn--continue" id="race-continue-btn">Race Again (Keep Streak)</button>`;
            html += `<button class="race-btn race-btn--cashout" id="race-cashout-btn">Cash Out</button>`;
        } else {
            html += `<button class="race-btn race-btn--continue" id="race-continue-btn">Race Again</button>`;
        }
        html += `</div>`;
    } else {
        if (!funMode) {
            html += `<div style="font-size:0.82rem;color:var(--text-secondary);margin:8px 0">
                Lost ${data.bet.toLocaleString()} XP · Streak reset.
            </div>`;
        }
        html += `<div class="race-actions">
            <button class="race-btn" id="race-again-btn">Try Again</button>
            <button class="race-btn race-btn--quit" id="race-quit-btn">Leave</button>
        </div>`;
    }

    html += `</div>`;
    area.innerHTML = html;
    area.style.display = '';

    if (!funMode) loadXP();
    if (typeof window._casinoLobbyActivity === 'function') {
        const won = data.player_won;
        const streak = data.win_streak;
        const xp = data.pending_xp || 0;
        const xpStr = !funMode && xp > 0 ? ` +${xp.toLocaleString()} XP` : '';
        const streakStr = won && streak > 1 ? ` 🔥 Streak x${streak}` : '';
        window._casinoLobbyActivity(`🏁 Races: ${won ? '🏆 Won' : '💀 Lost'}${xpStr}${streakStr}`);
    }
}

// ── Continue / cashout / quit ─────────────────────────────────────────────────
async function continueRace() {
    // Re-race with same settings, streak carries over server-side
    const btn = $('race-continue-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Loading...'; }
    try {
        const r = await fetch('/api/casino/races/start', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ difficulty: _difficulty, bet: _funMode ? 0 : _bet, fun_mode: _funMode })
        });
        const d = await r.json();
        if (!r.ok) { showError(d.error || 'Failed'); return; }
        _raceData = d;
        buildTrack(d);
        startCountdown(() => animateRace(d));
    } catch(e) { showError(e.message); }
    finally { if (btn) { btn.disabled = false; } }
}

async function cashOut() {
    try {
        const r = await fetch('/api/casino/races/cashout', {
            method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}'
        });
        const d = await r.json();
        if (!r.ok) { showError(d.error || 'Cashout failed'); return; }
        const area = $('race-result-area');
        if (area) {
            area.innerHTML = `<div class="race-result">
                <div class="race-result-title win">💰 Cashed Out!</div>
                <div style="font-size:0.85rem;color:var(--text-secondary);margin:8px 0">
                    ${d.fun_mode ? 'Fun mode — nothing to cash out.' :
                      `+${(d.cashed_xp||0).toLocaleString()} XP${d.cashed_keys?.length ? ' · 🗝️ ' + d.cashed_keys.join(', ') : ''}`}
                </div>
                <div class="race-actions">
                    <button class="race-btn" id="race-again-btn">Race Again</button>
                </div>
            </div>`;
        }
        loadXP();
    } catch(e) { showError(e.message); }
}

async function quit() {
    try {
        await fetch('/api/casino/races/quit', { method:'POST', headers:{'Content-Type':'application/json'}, body:'{}' });
    } catch { /* silent */ }
    showSetup();
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function showError(msg) {
    const el = $('race-error');
    if (el) { el.textContent = msg; el.style.display = ''; setTimeout(() => el.style.display = 'none', 4000); }
}

function escHtml(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── Boot ──────────────────────────────────────────────────────────────────────
init();

})();

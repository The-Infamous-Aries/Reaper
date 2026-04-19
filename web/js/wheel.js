/* ── Wheel of Pets JS ─────────────────────────────────────────────────────── */
(function () {
'use strict';

const $ = id => document.getElementById(id);

// ── State ─────────────────────────────────────────────────────────────────
let _xp       = 0;
let _funMode  = false;
let _pets     = [];     // [{name, path}, …] — all 103
let _ownSpec  = '';     // player's own pet species
let _chosen   = null;  // selected pet name
let _bet      = 0;
let _spinning = false;
let _angle    = 0;     // current wheel rotation (radians)
let _animId   = null;
let _canvas   = null;
let _ctx      = null;
let _hover    = -1;    // hovered segment index

// ── Boot ──────────────────────────────────────────────────────────────────
function init() {
    if (!$('wheel-root')) return;
    showState('loading');
    checkAuth();
}

async function checkAuth() {
    try {
        const r = await fetch('/api/casino/xp');
        if (r.status === 401) { showState('login'); return; }
        if (!r.ok)            { showState('login'); return; }
        const d = await r.json();
        if (!d.has_pet) { showState('nopet'); return; }
        _xp      = d.total_xp || 0;
        _ownSpec = d.species  || '';
        updateXP();
        await loadPets();
        showState('main');
        initCanvas();
        bindEvents();
        drawWheel(_angle);
        updateSidebar();
    } catch(e) {
        console.error('[wheel] checkAuth failed:', e);
        showState('login');
    }
}

async function loadPets() {
    const r = await fetch('/api/casino/wheel/pets');
    if (!r.ok) throw new Error('Failed to load pets');
    const d = await r.json();
    _pets = d.pets || [];
    // Preload all images so the wheel renders immediately
    await Promise.all(_pets.map(p => new Promise(res => {
        const img = new Image();
        img.onload = img.onerror = res;
        img.src = p.path;
    })));
}

// ── Canvas setup ──────────────────────────────────────────────────────────
function initCanvas() {
    _canvas = $('wop-canvas');
    _ctx    = _canvas ? _canvas.getContext('2d') : null;
}

// ── Events ────────────────────────────────────────────────────────────────
function bindEvents() {
    // Fun mode toggle
    const toggle = $('wop-fun-toggle');
    if (toggle) toggle.addEventListener('change', e => {
        _funMode = e.target.checked;
        updateSidebar();
    });

    // Canvas hover + click
    const wrap = $('wop-canvas-wrap');
    if (wrap) {
        wrap.addEventListener('mousemove', onHover);
        wrap.addEventListener('mouseleave', () => { _hover = -1; drawWheel(_angle); hideTip(); });
        wrap.addEventListener('click', onClick);
    }

    // Bet input
    const betEl = $('wop-bet');
    if (betEl) betEl.addEventListener('input', () => { _bet = parseInt(betEl.value)||0; updateSidebar(); });

    // Bet presets
    document.querySelectorAll('.wop-preset').forEach(btn => {
        btn.addEventListener('click', () => {
            const inp = $('wop-bet');
            if (inp) { inp.value = btn.dataset.amount; _bet = parseInt(inp.value); }
            updateSidebar();
        });
    });

    // Spin button
    const spinBtn = $('wop-spin-btn');
    if (spinBtn) spinBtn.addEventListener('click', doSpin);

    // Result buttons
    const againBtn  = $('wop-again-btn');
    const changeBtn = $('wop-change-btn');
    if (againBtn)  againBtn.addEventListener('click',  spinAgain);
    if (changeBtn) changeBtn.addEventListener('click', changePet);
}

// ── Canvas hit-test ───────────────────────────────────────────────────────
function segmentAt(clientX, clientY) {
    if (!_canvas || !_pets.length) return -1;
    const rect = _canvas.getBoundingClientRect();
    const sx = _canvas.width  / rect.width;
    const sy = _canvas.height / rect.height;
    const cx = _canvas.width  / 2;
    const cy = _canvas.height / 2;
    const R  = Math.min(cx, cy) - 6;
    const Ro = R * RING_OUTER_FRAC;
    const Ri = R * RING_INNER_FRAC;
    const px = (clientX - rect.left) * sx - cx;
    const py = (clientY - rect.top)  * sy - cy;
    const d  = Math.sqrt(px * px + py * py);
    // Only register clicks within the ring band
    if (d > Ro || d < Ri) return -1;
    const arc = (2 * Math.PI) / _pets.length;
    let a = Math.atan2(py, px) - _angle;
    a = ((a % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);
    return Math.floor(a / arc) % _pets.length;
}

function onHover(e) {
    if (_spinning) return;
    const idx = segmentAt(e.clientX, e.clientY);
    if (idx === _hover) return;
    _hover = idx;
    drawWheel(_angle);
    if (idx >= 0) {
        const tip = $('wop-hover-tip');
        if (tip) { tip.textContent = _pets[idx].name; tip.style.display = ''; }
    } else {
        hideTip();
    }
}

function onClick(e) {
    if (_spinning) return;
    const idx = segmentAt(e.clientX, e.clientY);
    if (idx < 0) return;
    _chosen = _pets[idx].name;
    drawWheel(_angle);
    updateSidebar();
}

function hideTip() {
    const t = $('wop-hover-tip');
    if (t) t.style.display = 'none';
}

// ── Draw wheel ────────────────────────────────────────────────────────────
// Ring geometry constants
const RING_OUTER_FRAC = 0.97;  // outer edge of ring (fraction of canvas radius)
const RING_INNER_FRAC = 0.62;  // inner edge of ring — hollow centre starts here
const IMG_RING_FRAC   = 0.795; // centre of emoji images within the ring

// Image cache — keyed by pet name, values are HTMLImageElement
const _imgCache = {};
function getImg(name, path) {
    if (_imgCache[name]) return _imgCache[name];
    const img = new Image();
    img.src = path;
    img.onload = () => { _imgCache[name] = img; drawWheel(_angle); };
    _imgCache[name] = img;
    return img;
}

function drawWheel(rot) {
    if (!_ctx || !_canvas || !_pets.length) return;
    const W  = _canvas.width, H = _canvas.height;
    const cx = W / 2, cy = H / 2;
    const R  = Math.min(cx, cy) - 6;   // usable radius
    const Ro = R * RING_OUTER_FRAC;     // outer ring edge
    const Ri = R * RING_INNER_FRAC;     // inner ring edge (hollow starts here)
    const Rm = R * IMG_RING_FRAC;       // emoji centre radius
    const n  = _pets.length;
    const arc = (2 * Math.PI) / n;

    _ctx.clearRect(0, 0, W, H);

    // ── Outer glow halo ───────────────────────────────────────────────────
    const halo = _ctx.createRadialGradient(cx, cy, Ro, cx, cy, Ro + 18);
    halo.addColorStop(0, 'rgba(255,215,0,0.45)');
    halo.addColorStop(1, 'rgba(255,215,0,0)');
    _ctx.beginPath(); _ctx.arc(cx, cy, Ro + 18, 0, 2 * Math.PI);
    _ctx.fillStyle = halo; _ctx.fill();

    // ── Draw each ring segment ────────────────────────────────────────────
    for (let i = 0; i < n; i++) {
        const sa  = rot + i * arc;
        const ea  = sa + arc;
        const mid = sa + arc / 2;
        const pet = _pets[i];
        const isChosen  = pet.name === _chosen;
        const isOwn     = pet.name === _ownSpec;
        const isHovered = i === _hover;

        // Segment background (donut slice)
        _ctx.beginPath();
        _ctx.arc(cx, cy, Ro, sa, ea);
        _ctx.arc(cx, cy, Ri, ea, sa, true);
        _ctx.closePath();

        if (isChosen) {
            _ctx.fillStyle = 'rgba(255,215,0,0.55)';
        } else if (isOwn) {
            _ctx.fillStyle = 'rgba(255,140,0,0.38)';
        } else if (isHovered) {
            _ctx.fillStyle = 'rgba(255,255,255,0.18)';
        } else {
            // Alternating subtle tones so adjacent slots are distinguishable
            _ctx.fillStyle = i % 2 === 0
                ? 'rgba(255,255,255,0.05)'
                : 'rgba(0,0,0,0.18)';
        }
        _ctx.fill();

        // Thin divider line between slots
        _ctx.beginPath();
        _ctx.moveTo(cx + Ri * Math.cos(sa), cy + Ri * Math.sin(sa));
        _ctx.lineTo(cx + Ro * Math.cos(sa), cy + Ro * Math.sin(sa));
        _ctx.strokeStyle = isChosen
            ? 'rgba(255,215,0,0.9)'
            : 'rgba(255,215,0,0.18)';
        _ctx.lineWidth = isChosen ? 1.5 : 0.6;
        _ctx.stroke();

        // ── Pet emoji image ───────────────────────────────────────────────
        const ix  = cx + Rm * Math.cos(mid);
        const iy  = cy + Rm * Math.sin(mid);
        // Size: fill most of the ring band, capped so images don't overlap
        const bandW = (Ro - Ri);
        const sz  = Math.min(bandW * 0.82, (2 * Math.PI * Rm / n) * 0.78);

        const img = getImg(pet.name, pet.path);
        if (img && img.complete && img.naturalWidth > 0) {
            _ctx.save();
            _ctx.translate(ix, iy);
            // Keep images upright — don't rotate with the wheel
            _ctx.rotate(mid + Math.PI / 2);
            _ctx.drawImage(img, -sz / 2, -sz / 2, sz, sz);
            _ctx.restore();
        }

        // ── Chosen star overlay ───────────────────────────────────────────
        if (isChosen) {
            const sr = Ri + (Ro - Ri) * 0.18;
            const sx2 = cx + sr * Math.cos(mid);
            const sy2 = cy + sr * Math.sin(mid);
            _ctx.save();
            _ctx.translate(sx2, sy2);
            _ctx.font = `${Math.max(8, sz * 0.45)}px sans-serif`;
            _ctx.textAlign = 'center'; _ctx.textBaseline = 'middle';
            _ctx.fillText('⭐', 0, 0);
            _ctx.restore();
        }
    }

    // ── Outer gold rim ────────────────────────────────────────────────────
    _ctx.beginPath(); _ctx.arc(cx, cy, Ro, 0, 2 * Math.PI);
    _ctx.strokeStyle = 'rgba(255,215,0,0.9)'; _ctx.lineWidth = 3; _ctx.stroke();

    // ── Inner gold rim (edge of hollow) ──────────────────────────────────
    _ctx.beginPath(); _ctx.arc(cx, cy, Ri, 0, 2 * Math.PI);
    _ctx.strokeStyle = 'rgba(255,215,0,0.55)'; _ctx.lineWidth = 2; _ctx.stroke();

    // ── Hollow centre fill (dark, so it looks intentionally empty) ────────
    _ctx.beginPath(); _ctx.arc(cx, cy, Ri - 1, 0, 2 * Math.PI);
    const centreGrad = _ctx.createRadialGradient(cx, cy, 0, cx, cy, Ri);
    centreGrad.addColorStop(0, 'rgba(20,20,20,0.92)');
    centreGrad.addColorStop(1, 'rgba(10,10,10,0.75)');
    _ctx.fillStyle = centreGrad; _ctx.fill();
}

// ── Sidebar ───────────────────────────────────────────────────────────────
function updateSidebar() {
    // Selected pet box
    const box    = $('wop-selected-box');
    const petDiv = $('wop-selected-pet');
    const lbl    = box ? box.querySelector('.wop-selected-label') : null;
    const sImg   = $('wop-sel-img');
    const sName  = $('wop-sel-name');
    const sSub   = $('wop-sel-sub');
    if (_chosen) {
        const p = _pets.find(x => x.name === _chosen);
        if (p && sImg)  sImg.src = p.path;
        if (sName) sName.textContent = _chosen;
        if (sSub)  sSub.textContent  = _chosen === _ownSpec ? '⭐ Your pet — 2× bonus!' : 'Click wheel to change';
        if (lbl)   lbl.style.display  = 'none';
        if (petDiv) petDiv.style.display = '';
        if (box)   box.classList.add('has-pet');
    } else {
        if (lbl)   lbl.style.display  = '';
        if (petDiv) petDiv.style.display = 'none';
        if (box)   box.classList.remove('has-pet');
    }

    // Payout preview
    const n   = _pets.length || 103;
    const win = Math.floor(_bet * n * 0.95);
    const own = Math.floor(win * 2);
    const pw  = $('wop-pay-win');
    const po  = $('wop-pay-own');
    if (pw) pw.textContent = _bet > 0 ? win.toLocaleString()+' XP' : '—';
    if (po) po.textContent = _bet > 0 ? own.toLocaleString()+' XP' : '—';

    // Bet section visibility
    const bs = $('wop-bet-section');
    if (bs) bs.style.display = _funMode ? 'none' : '';

    // Spin button
    const sb = $('wop-spin-btn');
    if (sb) sb.disabled = !_chosen || _spinning || (!_funMode && (_bet < 10 || _bet > _xp));
}

// ── Spin ──────────────────────────────────────────────────────────────────
async function doSpin() {
    if (_spinning || !_chosen) return;
    _spinning = true;

    const bet = _funMode ? 0 : _bet;

    const sb = $('wop-spin-btn');
    if (sb) { sb.disabled = true; sb.classList.add('spinning-state'); sb.textContent = '🎡 SPINNING…'; }
    const resEl = $('wop-result');
    if (resEl) resEl.style.display = 'none';
    const wrap = $('wop-canvas-wrap');
    if (wrap) wrap.classList.add('spinning');

    let result;
    try {
        const r = await fetch('/api/casino/wheel/spin', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ bet_amount: bet, chosen_pet: _chosen, fun_mode: _funMode })
        });
        result = await r.json();
        if (!r.ok) throw new Error(result.error || 'Spin failed');
    } catch(e) {
        _spinning = false;
        if (wrap) wrap.classList.remove('spinning');
        if (sb) { sb.disabled=false; sb.classList.remove('spinning-state'); sb.textContent='🎡 SPIN'; }
        alert('Spin failed: ' + e.message);
        return;
    }

    await animateTo(result.winner_index);

    if (wrap) wrap.classList.remove('spinning');
    _spinning = false;
    showResult(result);
    refreshXP();
    if (sb) { sb.classList.remove('spinning-state'); sb.textContent='🎡 SPIN'; sb.disabled=false; }
}

// ── Animation ─────────────────────────────────────────────────────────────
function animateTo(winnerIdx) {
    return new Promise(resolve => {
        const n   = _pets.length;
        const arc = (2*Math.PI) / n;
        // Pointer at top = -π/2; centre winner segment there
        const base   = -Math.PI/2 - winnerIdx*arc - arc/2;
        const extra  = (6 + Math.floor(Math.random()*4)) * 2*Math.PI;
        const target = base - extra;
        const start  = _angle;
        const delta  = target - start;
        const dur    = 5200;
        const t0     = performance.now();
        // Ease-out quart — realistic wheel deceleration
        const ease = t => 1 - Math.pow(1-t, 4);
        function frame(now) {
            const t = Math.min((now-t0)/dur, 1);
            _angle = start + delta * ease(t);
            drawWheel(_angle);
            if (t < 1) { _animId = requestAnimationFrame(frame); }
            else { _angle = target; drawWheel(_angle); cancelAnimationFrame(_animId); resolve(); }
        }
        _animId = requestAnimationFrame(frame);
    });
}

// ── Result ────────────────────────────────────────────────────────────────
function showResult(result) {
    const el = $('wop-result');
    if (!el) return;
    el.className = 'wop-result';
    if (result.own_pet_bonus) el.classList.add('wop-result--own');
    else if (result.won)      el.classList.add('wop-result--win');
    else                      el.classList.add('wop-result--loss');

    const img  = $('wop-res-img');
    const name = $('wop-res-name');
    const txt  = $('wop-res-text');
    const xpEl = $('wop-res-xp');
    if (img)  { img.src = result.winner_path; img.alt = result.winner; }
    if (name) name.textContent = result.winner;
    if (txt)  txt.textContent  = result.result_text || '';
    if (xpEl) {
        if (result.winnings > 0) { xpEl.style.display=''; xpEl.textContent='+'+result.winnings.toLocaleString()+' XP'; }
        else xpEl.style.display = 'none';
    }
    el.style.display = '';

    if (result.own_pet_bonus) spawnConfetti();

    if (typeof window._casinoLobbyActivity === 'function') {
        const xs = result.winnings > 0 ? ` +${result.winnings.toLocaleString()} XP` : '';
        window._casinoLobbyActivity(`🎡 Wheel: ${result.result_text}${xs}`);
    }
}

// ── Spin again / change pet ───────────────────────────────────────────────
function spinAgain() {
    const resEl = $('wop-result');
    if (resEl) resEl.style.display = 'none';
    doSpin();
}

function changePet() {
    _chosen = null;
    drawWheel(_angle);
    updateSidebar();
    const resEl = $('wop-result');
    if (resEl) resEl.style.display = 'none';
    const wrap = $('wop-canvas-wrap');
    if (wrap) wrap.scrollIntoView({ behavior:'smooth', block:'nearest' });
}

// ── Confetti ──────────────────────────────────────────────────────────────
function spawnConfetti() {
    const cols = ['#FFD700','#FFA500','#FF6B6B','#4ECDC4','#45B7D1','#96CEB4','#FFEAA7','#fff','#ff69b4'];
    for (let i = 0; i < 90; i++) {
        const p = document.createElement('div');
        p.className = 'wop-confetti';
        p.style.cssText = `left:${Math.random()*100}vw;top:${8+Math.random()*35}vh;`
            + `background:${cols[i%cols.length]};`
            + `animation-duration:${1.3+Math.random()*2}s;`
            + `animation-delay:${Math.random()*0.6}s;`
            + `width:${5+Math.random()*7}px;height:${5+Math.random()*7}px;`;
        document.body.appendChild(p);
        p.addEventListener('animationend', () => p.remove());
    }
}

// ── Helpers ───────────────────────────────────────────────────────────────
function showState(state) {
    $('wop-loading')      && ($('wop-loading').style.display      = state === 'loading' ? '' : 'none');
    $('wop-login-prompt') && ($('wop-login-prompt').style.display = state === 'login'   ? '' : 'none');
    $('wop-no-pet')       && ($('wop-no-pet').style.display       = state === 'nopet'   ? '' : 'none');
    $('wop-main')         && ($('wop-main').style.display         = state === 'main'    ? '' : 'none');
}

function updateXP() {
    const el = $('wop-xp-display');
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

// ── Back to casino ────────────────────────────────────────────────────────
window._wopBack = function() {
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

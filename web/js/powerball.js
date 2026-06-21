/* ── Pet Powerball JS ─────────────────────────────────────────────────────── */
(function () {
'use strict';

const $ = id => document.getElementById(id);
const esc = s => String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

// ── State ─────────────────────────────────────────────────────────────────
let _info        = null;   // full /api/powerball/info response
let _xp          = 0;
let _step        = 1;      // 1 | 2 | 3
let _selPets     = [];     // up to 5 names, ordered
let _selElement  = null;   // string or null
let _useEM       = false;
let _countdownId = null;
let _reloadScheduled = false;

const DRAW_LOCK_SECONDS = 300; // must match backend DRAW_LOCK_SECONDS

// ── Boot ──────────────────────────────────────────────────────────────────
function init() {
    if (!$('pb-root')) return;
    showState('loading');
    loadInfo();
}

async function loadInfo() {
    try {
        const r = await fetch('/api/powerball/info');
        if (r.status === 401) { showState('login'); return; }
        if (!r.ok)            { showState('login'); return; }
        const d = await r.json();
        if (!d.has_pet) { showState('nopet'); return; }
        _info = d;
        _xp   = d.total_xp || 0;
        renderXP();
        renderPage();
        showState('main');
        startCountdown();
    } catch(e) {
        console.error('[powerball] loadInfo failed:', e);
        showState('login');
    }
}

async function refreshXP() {
    try {
        const r = await fetch('/api/casino/xp');
        if (!r.ok) return;
        const d = await r.json();
        if (d.has_pet) { _xp = d.total_xp || 0; renderXP(); }
    } catch { /* silent */ }
}

function renderXP() {
    const el = $('pb-xp-display');
    if (el) el.textContent = _xp.toLocaleString();
}

// ── Page render ───────────────────────────────────────────────────────────
function renderPage() {
    if (!_info) return;

    // Draw date
    const ddEl = $('pb-draw-date');
    if (ddEl) ddEl.textContent = _info.draw_date;

    // Pot — label shows which draw this is for
    const potEl = $('pb-pot-display');
    if (potEl) {
        potEl.textContent = (_info.pot_xp || 0).toLocaleString() + ' XP';

        // Remove any stale rollover indicator before potentially re-adding
        const existingRollover = potEl.parentNode.querySelector('.pb-rollover-indicator');
        if (existingRollover) existingRollover.remove();

        // Check if pot grew due to rollover multiplier
        if (_info.last_draw && _info.last_draw.pot_after && _info.last_draw.pot_before) {
            const lastPot = _info.last_draw.pot_after;
            const beforePot = _info.last_draw.pot_before;
            const winners = _info.last_draw.winners || [];
            const majorWinners = winners.filter(w => w.tier === 'MEGA' || w.tier === 'TIER1');

            // If pot grew significantly and no major winners, show rollover indicator
            if (majorWinners.length === 0 && lastPot > beforePot && (lastPot / beforePot) > 2) {
                const rolloverEl = document.createElement('div');
                rolloverEl.className = 'pb-rollover-indicator';
                rolloverEl.style.cssText = `
                    font-size: 0.6rem;
                    color: #27ae60;
                    margin-top: 2px;
                    font-weight: 600;
                    animation: pbRolloverGlow 2s ease-in-out infinite;
                `;
                rolloverEl.textContent = `\uD83D\uDE80 Rolled over from ${beforePot.toLocaleString()} XP (2.5x multiplier)`;
                potEl.parentNode.appendChild(rolloverEl);
            }
        }
    }

    // Payout table — show live XP estimates from pot
    const p = _info.payouts || {};
    const fmtXp = n => typeof n === 'number' ? n.toLocaleString() + ' XP' : '—';
    if ($('pb-pay-mega-xp')) $('pb-pay-mega-xp').textContent = fmtXp(p.MEGA_xp);
    if ($('pb-pay-1-xp'))    $('pb-pay-1-xp').textContent   = fmtXp(p.TIER1_xp);
    if ($('pb-pay-2em-xp'))  $('pb-pay-2em-xp').textContent = fmtXp(p.TIER2_EM_xp);
    if ($('pb-pay-2-xp'))    $('pb-pay-2-xp').textContent   = fmtXp(p.TIER2_xp);
    if ($('pb-pay-3em-xp'))  $('pb-pay-3em-xp').textContent = fmtXp(p.TIER3_EM_xp);
    if ($('pb-pay-3-xp'))    $('pb-pay-3-xp').textContent   = fmtXp(p.TIER3_xp);

    // Last draw
    renderLastDraw(_info.last_draw);

    // Already has ticket?
    if (_info.ticket) {
        $('pb-has-ticket').style.display = '';
        $('pb-builder').style.display    = 'none';
        renderTicketDisplay(_info.ticket, $('pb-ticket-display'));
    } else {
        $('pb-has-ticket').style.display = 'none';
        $('pb-builder').style.display    = '';
        buildPetGrid();
        buildElemGrid();
        buildSelectedRow();
        bindEvents();
        goToStep(1);
    }
}

// ── Ticket display ────────────────────────────────────────────────────────
function renderTicketDisplay(ticket, container) {
    if (!container) return;
    const petsHtml = (ticket.pets || []).map(p =>
        `<div class="pb-ticket-pet">
            <img src="/static/Emojis/Pets/${esc(p)}.png" alt="${esc(p)}">
            <span>${esc(p)}</span>
        </div>`
    ).join('');
    const emHtml = ticket.element
        ? `<div class="pb-ticket-em">
               <img src="/static/Emojis/Pets/Deco/${esc(ticket.element)}.png" alt="${esc(ticket.element)}">
               ⚡ Elemental Ball: <strong>${esc(ticket.element)}</strong>
           </div>`
        : `<div class="pb-ticket-no-em">No Elemental Ball selected</div>`;
    container.innerHTML = `
        <div class="pb-ticket">
            <div class="pb-ticket-header">
                <div class="pb-ticket-title">🎟️ Pet Powerball Ticket</div>
                <div class="pb-ticket-date">${esc(ticket.purchased_at ? ticket.purchased_at.slice(0,10) : '')}</div>
            </div>
            <div class="pb-ticket-pets">${petsHtml}</div>
            ${emHtml}
            <div class="pb-ticket-cost">Cost: <strong>${(ticket.cost||0).toLocaleString()} XP</strong></div>
        </div>`;
}

// ── Last draw ─────────────────────────────────────────────────────────────
function renderLastDraw(draw) {
    const sec = $('pb-last-draw-section');
    const con = $('pb-last-draw-content');
    if (!sec || !con || !draw) return;
    sec.style.display = '';

    const petsHtml = (draw.drawn_pets || []).map((p, i) =>
        `<div class="pb-last-draw-pet">
            <span class="pb-last-draw-pos">#${i+1}</span>
            <img src="/static/Emojis/Pets/${esc(p)}.png" alt="${esc(p)}">
            <span>${esc(p)}</span>
        </div>`
    ).join('');

    const emHtml = draw.drawn_element
        ? `<div class="pb-last-draw-em">
               <img src="/static/Emojis/Pets/Deco/${esc(draw.drawn_element)}.png" alt="${esc(draw.drawn_element)}">
               ⚡ ${esc(draw.drawn_element)}
           </div>`
        : '';

    // Pot summary row
    const potHtml = `
        <div class="pb-last-draw-pot">
            <span>🏦 Pot</span>
            <span><strong style="color:var(--gold-primary)">${(draw.pot_before||0).toLocaleString()} XP</strong></span>
        </div>`;

    // Winners section
    let winnersHtml = '';
    if (!draw.winners || draw.winners.length === 0) {
        winnersHtml = `<div class="pb-no-winners">😔 No winners — pot rolled over to ${(draw.pot_after||0).toLocaleString()} XP!</div>`;
    } else {
        const TIER_LABELS = {
            MEGA:     { icon: '🏆', label: 'MEGA JACKPOT', cls: 'mega' },
            TIER1:    { icon: '🥇', label: '5 Pets',       cls: 'tier1' },
            TIER2_EM: { icon: '🥈', label: '4 Pets + ⚡',  cls: 'tier2em' },
            TIER2:    { icon: '🥈', label: '4 Pets',       cls: 'tier2' },
            TIER3_EM: { icon: '🥉', label: '3 Pets + ⚡',  cls: 'tier3em' },
            TIER3:    { icon: '🎖️', label: '3 Pets',       cls: 'tier3' },
        };
        winnersHtml = `<div class="pb-last-draw-winners-label">🎉 Winners</div>` +
            draw.winners.map(w => {
                const t = TIER_LABELS[w.tier] || { icon: '🎖️', label: w.tier, cls: '' };
                return `<div class="pb-winner-row ${t.cls}">
                    <span>${t.icon} ${t.label}</span>
                    <span class="pb-winner-payout">+${(w.payout||0).toLocaleString()} XP</span>
                </div>`;
            }).join('');
    }

    con.innerHTML = `
        <div class="pb-last-draw-date">${esc(draw.draw_date)}</div>
        ${potHtml}
        <div class="pb-last-draw-pets">${petsHtml}</div>
        ${emHtml}
        <div class="pb-last-draw-winners">${winnersHtml}</div>`;
}

// ── Pet grid ──────────────────────────────────────────────────────────────
function buildPetGrid() {
    const grid = $('pb-pet-grid');
    if (!grid || !_info) return;
    grid.innerHTML = '';
    (_info.pets || []).forEach(p => {
        const tile = document.createElement('div');
        tile.className = 'pb-pet-tile';
        tile.dataset.name = p.name;
        tile.innerHTML = `<img src="${esc(p.path)}" alt="${esc(p.name)}" loading="lazy"><span>${esc(p.name)}</span>`;
        tile.addEventListener('click', () => togglePet(p.name));
        grid.appendChild(tile);
    });
}

function buildElemGrid() {
    const grid = $('pb-elem-grid');
    if (!grid || !_info) return;
    grid.innerHTML = '';
    (_info.elements || []).forEach(e => {
        const tile = document.createElement('div');
        tile.className = 'pb-elem-tile';
        tile.dataset.name = e.name;
        tile.innerHTML = `<img src="${esc(e.path)}" alt="${esc(e.name)}" loading="lazy"><span>${esc(e.name)}</span>`;
        tile.addEventListener('click', () => toggleElement(e.name));
        grid.appendChild(tile);
    });
}

function buildSelectedRow() {
    const row = $('pb-selected-row');
    if (!row) return;
    row.innerHTML = '';
    for (let i = 0; i < 5; i++) {
        const slot = document.createElement('div');
        slot.className = 'pb-selected-slot';
        slot.id = `pb-sel-slot-${i}`;
        slot.dataset.idx = i;
        slot.innerHTML = `<span class="pb-slot-num">#${i+1}</span><span class="pb-slot-empty">empty</span>`;
        slot.addEventListener('click', () => removeFromSlot(i));
        row.appendChild(slot);
    }
}

// ── Quick Pick ────────────────────────────────────────────────────────────
function doQuickPick() {
    if (!_info || !_info.pets) return;

    // Pick 5 unique random pets
    const allNames = _info.pets.map(p => p.name);
    const shuffled = allNames.slice().sort(() => Math.random() - 0.5);
    _selPets = shuffled.slice(0, 5);

    // If "Include EM" toggle is on, pick a random element and set _useEM
    const qpEmCheck = $('pb-qp-em-include');
    const withEM = qpEmCheck && qpEmCheck.checked;
    if (withEM && _info.elements && _info.elements.length > 0) {
        _useEM = true;
        _selElement = _info.elements[Math.floor(Math.random() * _info.elements.length)].name;
        // Keep the step-2 EM toggle in sync so step 3 preview is correct
        const emToggle = $('pb-em-toggle');
        if (emToggle) emToggle.checked = true;
        // Refresh element tile enabled state
        document.querySelectorAll('.pb-elem-tile').forEach(t => {
            t.classList.add('enabled');
            t.classList.toggle('selected', t.dataset.name === _selElement);
        });
        const badge = $('pb-em-cost-badge');
        if (badge && _info) badge.textContent = `+${(_info.cost_with_em - _info.cost_no_em).toLocaleString()} XP`;
    } else {
        // No EM — clear any prior selection
        _useEM = false;
        _selElement = null;
        const emToggle = $('pb-em-toggle');
        if (emToggle) emToggle.checked = false;
        document.querySelectorAll('.pb-elem-tile').forEach(t => {
            t.classList.remove('enabled', 'selected');
        });
        const badge = $('pb-em-cost-badge');
        if (badge) badge.textContent = '+50% cost';
    }

    syncPetUI();
    updateStep3Preview();
    checkBuyReady();

    // Visual flash on the button to confirm the pick fired
    const btn = $('pb-quick-pick-btn');
    if (btn) {
        btn.textContent = '✅ Picked!';
        setTimeout(() => { btn.textContent = '🎲 Quick Pick'; }, 900);
    }
}

// ── Selection logic ───────────────────────────────────────────────────────
function togglePet(name) {
    const idx = _selPets.indexOf(name);
    if (idx >= 0) {
        _selPets.splice(idx, 1);
    } else {
        if (_selPets.length >= 5) return;
        _selPets.push(name);
    }
    syncPetUI();
}

function removeFromSlot(idx) {
    if (_selPets[idx] !== undefined) {
        _selPets.splice(idx, 1);
        syncPetUI();
    }
}

function syncPetUI() {
    // Update grid tiles
    document.querySelectorAll('.pb-pet-tile').forEach(tile => {
        const name = tile.dataset.name;
        const idx  = _selPets.indexOf(name);
        tile.classList.toggle('selected', idx >= 0);
        tile.classList.toggle('disabled', _selPets.length >= 5 && idx < 0);
        // Remove old badge
        const old = tile.querySelector('.pb-pet-slot-badge');
        if (old) old.remove();
        if (idx >= 0) {
            const badge = document.createElement('div');
            badge.className = 'pb-pet-slot-badge';
            badge.textContent = idx + 1;
            tile.appendChild(badge);
        }
    });

    // Update selected row
    for (let i = 0; i < 5; i++) {
        const slot = $(`pb-sel-slot-${i}`);
        if (!slot) continue;
        const name = _selPets[i];
        if (name) {
            slot.className = 'pb-selected-slot filled';
            slot.innerHTML = `
                <span class="pb-slot-num">#${i+1}</span>
                <img src="/static/Emojis/Pets/${esc(name)}.png" alt="${esc(name)}">
                <span class="pb-slot-name">${esc(name)}</span>`;
        } else {
            slot.className = 'pb-selected-slot';
            slot.innerHTML = `<span class="pb-slot-num">#${i+1}</span><span class="pb-slot-empty">empty</span>`;
        }
    }

    // Badge count
    const badge = $('pb-pet-count-badge');
    if (badge) badge.textContent = `${_selPets.length} / 5`;

    // Enable continue button when 5 selected
    const cont = $('pb-to-step2');
    if (cont) cont.disabled = _selPets.length < 5;
}

function toggleElement(name) {
    if (!_useEM) return;
    _selElement = (_selElement === name) ? null : name;
    document.querySelectorAll('.pb-elem-tile').forEach(t => {
        t.classList.toggle('selected', t.dataset.name === _selElement);
    });
    updateStep3Preview();
    checkBuyReady();
}

// ── Step navigation ───────────────────────────────────────────────────────
function goToStep(n) {
    _step = n;
    $('pb-step1-panel').style.display = n === 1 ? '' : 'none';
    $('pb-step2-panel').style.display = n === 2 ? '' : 'none';
    $('pb-step3-panel').style.display = n === 3 ? '' : 'none';
    ['pb-step-1','pb-step-2','pb-step-3'].forEach((id, i) => {
        const el = $(id);
        if (!el) return;
        el.classList.remove('active','done');
        if (i + 1 < n)  el.classList.add('done');
        if (i + 1 === n) el.classList.add('active');
    });
    if (n === 3) updateStep3Preview();
}

function updateStep3Preview() {
    if (!_info) return;
    // Ticket preview
    const prev = $('pb-preview-ticket');
    if (prev) {
        renderTicketDisplay({
            pets: _selPets,
            element: _useEM ? _selElement : null,
            cost: _useEM ? _info.cost_with_em : _info.cost_no_em,
            purchased_at: new Date().toISOString(),
        }, prev);
    }
    // Cost breakdown
    const cost = _useEM ? _info.cost_with_em : _info.cost_no_em;
    const baseCost = _info.cost_no_em;
    const emExtra  = _info.cost_with_em - _info.cost_no_em;
    const potContrib = cost;  // house matches 100% of ticket cost into pot

    if ($('pb-cost-level'))  $('pb-cost-level').textContent  = `Level ${_info.pet_level}`;
    if ($('pb-cost-equip'))  $('pb-cost-equip').textContent  = `${_info.equip_mult}×`;
    if ($('pb-cost-base'))   $('pb-cost-base').textContent   = baseCost.toLocaleString() + ' XP';
    if ($('pb-cost-em-row')) $('pb-cost-em-row').style.display = _useEM ? '' : 'none';
    if ($('pb-cost-em-extra')) $('pb-cost-em-extra').textContent = '+' + emExtra.toLocaleString() + ' XP';
    if ($('pb-cost-total'))  $('pb-cost-total').textContent  = cost.toLocaleString() + ' XP';
    if ($('pb-cost-pot-contrib')) $('pb-cost-pot-contrib').textContent = '+' + potContrib.toLocaleString() + ' XP to pot';

    checkBuyReady();
}

function checkBuyReady() {
    const btn = $('pb-buy-btn');
    if (!btn || !_info) return;

    // Block during draw lock window
    if (_info.draw_locked) {
        btn.disabled = true;
        const err = $('pb-buy-error');
        if (err) { err.textContent = '⏳ Draw in progress — tickets resume in a few minutes.'; err.style.display = ''; }
        return;
    }

    const cost = _useEM ? _info.cost_with_em : _info.cost_no_em;
    const emOk = !_useEM || (_selElement !== null);
    const ready = _selPets.length === 5 && emOk && cost <= _xp;
    btn.disabled = !ready;
    if (cost > _xp && _selPets.length === 5) {
        const err = $('pb-buy-error');
        if (err) { err.textContent = `Insufficient XP. Need ${cost.toLocaleString()} XP, have ${_xp.toLocaleString()} XP.`; err.style.display = ''; }
    } else {
        const err = $('pb-buy-error');
        if (err) err.style.display = 'none';
    }
}

// ── Events ────────────────────────────────────────────────────────────────
function bindEvents() {
    // Quick Pick
    const qpBtn = $('pb-quick-pick-btn');
    if (qpBtn && !qpBtn._pbBound) {
        qpBtn._pbBound = true;
        qpBtn.addEventListener('click', doQuickPick);
    }

    // Pet search
    const search = $('pb-pet-search');
    if (search && !search._pbBound) {
        search._pbBound = true;
        search.addEventListener('input', () => {
            const q = search.value.toLowerCase().trim();
            document.querySelectorAll('.pb-pet-tile').forEach(t => {
                t.classList.toggle('hidden', !!q && !t.dataset.name.toLowerCase().includes(q));
            });
        });
    }

    // Step 1 → 2 button (injected dynamically)
    document.addEventListener('click', e => {
        if (!$('pb-root')) return;
        if (e.target.id === 'pb-to-step2' && _selPets.length === 5) goToStep(2);
        if (e.target.id === 'pb-back-to-step1') goToStep(1);
        if (e.target.id === 'pb-to-step3') goToStep(3);
        if (e.target.id === 'pb-back-to-step2') goToStep(2);
        if (e.target.id === 'pb-buy-btn') buyTicket();
        if (e.target.id === 'pb-draw-close-btn') closeDrawOverlay();
    });

    // EM toggle
    const emToggle = $('pb-em-toggle');
    if (emToggle && !emToggle._pbBound) {
        emToggle._pbBound = true;
        emToggle.addEventListener('change', e => {
            _useEM = e.target.checked;
            _selElement = null;
            document.querySelectorAll('.pb-elem-tile').forEach(t => {
                t.classList.toggle('enabled', _useEM);
                t.classList.remove('selected');
            });
            const badge = $('pb-em-cost-badge');
            if (badge) badge.textContent = _useEM ? `+${(_info.cost_with_em - _info.cost_no_em).toLocaleString()} XP` : '+50% cost';
            updateStep3Preview();
            checkBuyReady();
        });
    }

    // Add "Continue →" button to step 1 panel dynamically
    const step1Panel = $('pb-step1-panel');
    if (step1Panel && !step1Panel.querySelector('#pb-to-step2')) {
        const btn = document.createElement('button');
        btn.id = 'pb-to-step2';
        btn.className = 'casino-btn w-100 mt-3';
        btn.textContent = 'Continue →';
        btn.disabled = true;
        step1Panel.appendChild(btn);
    }
}

// ── Buy ticket ────────────────────────────────────────────────────────────
async function buyTicket() {
    const btn = $('pb-buy-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Purchasing…'; }

    try {
        const r = await fetch('/api/powerball/buy', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({
                pets:    _selPets,
                element: _useEM ? _selElement : null,
            })
        });
        const d = await r.json();
        if (!r.ok) {
            const err = $('pb-buy-error');
            if (err) { err.textContent = d.error || 'Purchase failed'; err.style.display = ''; }
            if (btn) { btn.disabled = false; btn.textContent = '🎟️ Buy Ticket'; }
            return;
        }

        // Update pot display
        const potEl = $('pb-pot-display');
        if (potEl) potEl.textContent = (d.pot_xp || 0).toLocaleString() + ' XP';

        // Update info for display
        _info.ticket = { pets: d.pets, element: d.element, cost: d.cost, purchased_at: d.purchased_at };
        _info.pot_xp = d.pot_xp;

        // Show ticket
        $('pb-builder').style.display    = 'none';
        $('pb-has-ticket').style.display = '';
        renderTicketDisplay(_info.ticket, $('pb-ticket-display'));

        refreshXP();

        // Task tracking notification
        if (typeof window._casinoLobbyActivity === 'function') {
            window._casinoLobbyActivity(`🎟️ Powerball: ticket purchased for ${d.draw_date}`);
        }

    } catch(e) {
        const err = $('pb-buy-error');
        if (err) { err.textContent = 'Network error: ' + e.message; err.style.display = ''; }
        if (btn) { btn.disabled = false; btn.textContent = '🎟️ Buy Ticket'; }
    }
}

// ── Countdown ─────────────────────────────────────────────────────────────
function startCountdown() {
    if (_countdownId) clearInterval(_countdownId);

    // Target: midnight UTC at the END of draw_date (i.e. the start of draw_date + 1 day).
    // The draw fires at 00:00 UTC on the day AFTER draw_date, so for draw_date "2026-05-02"
    // the target is 2026-05-03T00:00:00Z.
    function getTargetMs() {
        if (!_info || !_info.draw_date) return null;
        const parts = _info.draw_date.split('-').map(Number);
        // Add 1 to the day to get midnight ending draw_date
        return Date.UTC(parts[0], parts[1] - 1, parts[2] + 1);
    }

    function tick() {
        const target = getTargetMs();
        if (!target) return;
        const now = Date.now();
        const diff = Math.max(0, Math.floor((target - now) / 1000));
        const h = Math.floor(diff / 3600);
        const m = Math.floor((diff % 3600) / 60);
        const s = diff % 60;
        const el = $('pb-countdown');
        if (el) el.textContent = `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;

        // When countdown hits zero, reload info after the lock window clears
        if (diff === 0 && !_reloadScheduled) {
            _reloadScheduled = true;
            setTimeout(() => { _reloadScheduled = false; loadInfo(); }, (DRAW_LOCK_SECONDS + 5) * 1000);
        }
    }
    tick();
    _countdownId = setInterval(tick, 1000);
}

// ── Draw animation (called when draw result is available) ─────────────────
function showDrawAnimation(result) {
    const overlay = $('pb-draw-overlay');
    const ballsEl = $('pb-draw-balls');
    const textEl  = $('pb-draw-result-text');
    if (!overlay || !ballsEl || !textEl) return;

    ballsEl.innerHTML = '';
    textEl.textContent = '';
    textEl.className = 'pb-draw-result-text';
    overlay.style.display = 'flex';

    // Build ball elements
    const pets = result.drawn_pets || [];
    const elem = result.drawn_element;
    const allBalls = pets.map((p, i) => ({
        type: 'pet', name: p, path: `/static/Emojis/Pets/${p}.png`, idx: i
    }));
    if (elem) allBalls.push({ type: 'em', name: elem, path: `/static/Emojis/Pets/Deco/${elem}.png`, idx: 5 });

    allBalls.forEach(b => {
        const div = document.createElement('div');
        div.className = 'pb-draw-ball' + (b.type === 'em' ? ' em-ball' : '');
        div.id = `pb-ball-${b.idx}`;
        div.innerHTML = `<img src="${esc(b.path)}" alt="${esc(b.name)}"><span>${esc(b.name)}</span>`;
        ballsEl.appendChild(div);
    });

    // Reveal balls one by one
    let delay = 400;
    allBalls.forEach((b, i) => {
        setTimeout(() => {
            const el = $(`pb-ball-${b.idx}`);
            if (el) el.classList.add('revealed');
        }, delay + i * 700);
    });

    // Show result text after all balls revealed
    const totalDelay = delay + allBalls.length * 700 + 500;
    setTimeout(() => {
        const winners = result.winners || [];
        if (winners.length === 0) {
            textEl.textContent = '😔 No winners today — pot rolls over!';
        } else {
            const mega = winners.find(w => w.tier === 'MEGA');
            if (mega) {
                textEl.textContent = `🏆 MEGA JACKPOT! ${winners.length} winner(s)!`;
                textEl.className = 'pb-draw-result-text mega';
                spawnConfetti();
            } else {
                textEl.textContent = `🎉 ${winners.length} winner(s) this draw!`;
                textEl.className = 'pb-draw-result-text win';
            }
        }
    }, totalDelay);
}

function closeDrawOverlay() {
    const overlay = $('pb-draw-overlay');
    if (overlay) overlay.style.display = 'none';
}

// ── Confetti ──────────────────────────────────────────────────────────────
function spawnConfetti() {
    const cols = ['#FFD700','#FFA500','#FF6B6B','#4ECDC4','#45B7D1','#96CEB4','#FFEAA7','#fff'];
    for (let i = 0; i < 80; i++) {
        const p = document.createElement('div');
        p.className = 'pb-confetti';
        p.style.cssText = `left:${Math.random()*100}vw;top:${5+Math.random()*30}vh;`
            + `background:${cols[i%cols.length]};`
            + `animation-duration:${1.4+Math.random()*2}s;`
            + `animation-delay:${Math.random()*0.5}s;`
            + `width:${5+Math.random()*7}px;height:${5+Math.random()*7}px;`;
        document.body.appendChild(p);
        p.addEventListener('animationend', () => p.remove());
    }
}

// ── Helpers ───────────────────────────────────────────────────────────────
function showState(state) {
    $('pb-loading')       && ($('pb-loading').style.display       = state === 'loading' ? '' : 'none');
    $('pb-login-prompt')  && ($('pb-login-prompt').style.display  = state === 'login'   ? '' : 'none');
    $('pb-no-pet')        && ($('pb-no-pet').style.display        = state === 'nopet'   ? '' : 'none');
    $('pb-main')          && ($('pb-main').style.display          = state === 'main'    ? '' : 'none');
}

// ── Back to casino ────────────────────────────────────────────────────────
window._pbBack = function() {
    if (_countdownId) clearInterval(_countdownId);
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

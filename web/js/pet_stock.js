// Pet Stock Page JS

let _psMarket = null;   // { prices, changes, history, events, type_emojis, element_emojis, base_prices }
let _psHoldings = {};   // { token: qty }
let _psPetData = null;  // logged-in user's pet (or null)
let _psTradeToken = null;
let _psTradeMode = 'buy'; // 'buy' | 'sell'

const PS_TYPES    = ['land', 'swimming', 'flying'];
const PS_ELEMENTS = ['basic','fire','water','electric','ice','plant','rock','air','magic','holy','necro','psychic','fighting'];

const TYPE_LABELS = { land: 'Land', swimming: 'Swimming', flying: 'Flying' };
const ELEM_LABELS = {
    basic:'Basic', fire:'Fire', water:'Water', electric:'Electric',
    ice:'Ice', plant:'Plant', rock:'Rock', air:'Air',
    magic:'Magic', holy:'Holy', necro:'Necro', psychic:'Psychic', fighting:'Fighting',
};

// ── Init ──────────────────────────────────────────────────────────────────────

// Format a price: show 2 decimal places below 1, otherwise integer with commas
function fmtPrice(p) {
    return p < 1 ? p.toFixed(2) : Math.round(p).toLocaleString();
}

async function initPetStock() {
    if (!document.getElementById('ps-grid-types')) return;

    // Check login state first (same pattern as arena, casino, bazaar)
    try {
        const r = await fetch('/api/discord/user');
        if (!r.ok) {
            psShowLoginPrompt();
            // Still load market data so prices/charts are visible to guests
            await psLoadMarket();
            psRenderAll();
            psRenderEvents();
            return;
        }
        const u = await r.json();
        // Store user id so we can pass it if needed
        window._psUserId = String(u.id);
    } catch {
        psShowLoginPrompt();
        await psLoadMarket();
        psRenderAll();
        psRenderEvents();
        return;
    }

    await Promise.all([
        psLoadMarket(),
        psLoadHoldings(),
        psLoadPet(),
    ]);

    psRenderAll();
    psRenderEvents();
}

function psShowLoginPrompt() {
    const el = document.getElementById('ps-login-prompt');
    if (el) el.style.display = '';
    const grid = document.getElementById('ps-grid-types');
    if (grid) grid.closest('.ps-section')?.querySelectorAll('.ps-trade-btn').forEach(b => {
        b.disabled = true;
        b.title = 'Log in to trade';
    });
}

async function psLoadMarket() {
    try {
        const r = await fetch('/api/pet-stock/market');
        if (r.ok) _psMarket = await r.json();
    } catch (e) { console.error('psLoadMarket', e); }
}

async function psLoadHoldings() {
    try {
        const r = await fetch('/api/pet-stock/holdings');
        if (r.ok) {
            const d = await r.json();
            _psHoldings = d.holdings || {};
        }
    } catch (_) {}
}

async function psLoadPet() {
    try {
        const r = await fetch('/api/user/pet');
        if (r.ok) {
            const d = await r.json();
            _psPetData = d.has_pet ? d : null;
        }
    } catch (_) {}
}

function psRenderAll() {
    if (!_psMarket) return;
    psRenderGrid('types',    PS_TYPES,    _psMarket.type_emojis,    TYPE_LABELS);
    psRenderGrid('elements', PS_ELEMENTS, _psMarket.element_emojis, ELEM_LABELS);
}

function psRenderGrid(section, tokens, emojis, labels) {
    const grid = document.getElementById(`ps-grid-${section}`);
    if (!grid) return;

    const petType  = (_psPetData?.category || '').toLowerCase();
    const petElem1 = (_psPetData?.element   || '').toLowerCase();
    const petElem2 = (_psPetData?.element2  || '').toLowerCase();
    const allowed  = new Set([petType, petElem1, petElem2].filter(Boolean));

    grid.innerHTML = tokens.map(token => {
        const price    = _psMarket.prices[token] ?? 0;
        const change   = _psMarket.changes[token] ?? 0;
        const history  = _psMarket.history[token] ?? [];
        const base     = _psMarket.base_prices[token] ?? price;
        const holding  = _psHoldings[token] ?? 0;
        const emoji    = emojis[token] ?? '';
        const label    = labels[token] ?? token;
        const canTrade = _psPetData && allowed.has(token);

        const trendClass = change > 0 ? 'positive' : change < 0 ? 'negative' : 'neutral';
        const changeSign = change >= 0 ? '▲' : '▼';
        const chart      = psBuildChart(history);

        // Multiplier badge — only shown in trade modal, not on card
        const tradeBtn = _psPetData
            ? `<button class="ps-trade-btn${canTrade ? '' : ' off-affinity'}" onclick="psOpenModal('${token}')">Trade</button>`
            : `<button class="ps-trade-btn locked" disabled title="You need a pet to trade">Trade</button>`;

        return `
        <div class="ps-card ${trendClass}">
            <div class="ps-card-header">
                <img src="${emoji}" class="ps-card-icon" alt="${token}">
                <span class="ps-card-price">${fmtPrice(price)} XP</span>
                <span class="ps-card-change ${trendClass}">${changeSign} ${Math.abs(change).toFixed(1)}%</span>
            </div>
            <div class="ps-card-chart">${chart}</div>
            <div class="ps-card-footer">
                <div class="ps-footer-stat">
                    <span class="ps-footer-label">Base</span>
                    <span class="ps-footer-val">${base.toLocaleString()}</span>
                </div>
                <div class="ps-footer-stat">
                    <span class="ps-footer-label">Change</span>
                    <span class="ps-footer-val ${trendClass}">${changeSign} ${Math.abs(change).toFixed(2)}%</span>
                </div>
                <div class="ps-footer-stat">
                    <span class="ps-footer-label">Held</span>
                    <span class="ps-footer-val">${holding}</span>
                </div>
                ${tradeBtn}
            </div>
        </div>`;
    }).join('');
}

function psBuildChart(history) {
    if (!history || history.length < 2) {
        return '<div class="chart-placeholder">Not enough data</div>';
    }

    const prices = history.map(h => h.price);
    const n      = prices.length;
    const min    = Math.min(...prices);
    const max    = Math.max(...prices);
    const range  = (max - min) || 1;

    const W = 400, H = 100;
    const pad = { t: 10, r: 6, b: 18, l: 44 };
    const dw  = W - pad.l - pad.r;
    const dh  = H - pad.t - pad.b;

    const px = i => pad.l + (i / (n - 1)) * dw;
    const py = p => H - pad.b - ((p - min) / range) * dh;

    // ── Y-axis labels (3 ticks) ───────────────────────────────────────────────
    const fmt = v => v >= 1e6 ? (v/1e6).toFixed(1)+'M'
                   : v >= 1e3 ? (v/1e3).toFixed(1)+'k'
                   : Math.round(v).toString();

    const yTicks = [min, (min + max) / 2, max];
    const yLabels = yTicks.map(v =>
        `<text x="${pad.l - 4}" y="${py(v) + 4}" text-anchor="end"
               font-size="9" fill="rgba(255,255,255,0.45)">${fmt(v)}</text>`
    ).join('');

    // ── Baseline grid lines ───────────────────────────────────────────────────
    const gridLines = yTicks.map(v =>
        `<line x1="${pad.l}" y1="${py(v)}" x2="${W - pad.r}" y2="${py(v)}"
               stroke="rgba(255,255,255,0.07)" stroke-width="1"/>`
    ).join('');

    // ── Segment-coloured area + line ─────────────────────────────────────────
    // For each consecutive pair, draw a filled trapezoid (green if rising, red if falling)
    // then draw the line segment on top.
    const areas = [];
    const lines = [];

    for (let i = 0; i < n - 1; i++) {
        const x0 = px(i),   y0 = py(prices[i]);
        const x1 = px(i+1), y1 = py(prices[i+1]);
        const base = H - pad.b;
        const rising = prices[i+1] >= prices[i];
        const fill   = rising ? 'rgba(76,175,80,0.18)'  : 'rgba(244,67,54,0.18)';
        const stroke = rising ? '#4caf50'               : '#f44336';

        areas.push(
            `<polygon points="${x0},${base} ${x0},${y0} ${x1},${y1} ${x1},${base}"
                      fill="${fill}"/>`
        );
        lines.push(
            `<line x1="${x0}" y1="${y0}" x2="${x1}" y2="${y1}"
                   stroke="${stroke}" stroke-width="1.8"
                   stroke-linecap="round"/>`
        );
    }

    // ── Dot at current price ──────────────────────────────────────────────────
    const lastX  = px(n - 1);
    const lastY  = py(prices[n - 1]);
    const dotCol = prices[n-1] >= prices[0] ? '#4caf50' : '#f44336';
    const dot    = `<circle cx="${lastX}" cy="${lastY}" r="3" fill="${dotCol}"/>`;

    // ── X-axis: first and last timestamp labels ───────────────────────────────
    const fmtTs = ts => {
        if (!ts) return '';
        const d = new Date(ts.replace(' ', 'T') + 'Z');
        return isNaN(d) ? '' : d.toLocaleDateString([], {month:'short', day:'numeric'});
    };
    const xFirst = fmtTs(history[0].timestamp);
    const xLast  = fmtTs(history[n-1].timestamp);
    const xLabels = [
        `<text x="${pad.l}" y="${H - 2}" text-anchor="start" font-size="9" fill="rgba(255,255,255,0.4)">${xFirst}</text>`,
        `<text x="${W - pad.r}" y="${H - 2}" text-anchor="end" font-size="9" fill="rgba(255,255,255,0.4)">${xLast}</text>`,
    ].join('');

    return `<svg class="ps-chart-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"
                 style="width:100%;height:100px;display:block">
        ${gridLines}
        ${yLabels}
        ${areas.join('')}
        ${lines.join('')}
        ${dot}
        ${xLabels}
    </svg>`;
}

// ── Events feed ───────────────────────────────────────────────────────────────

function psRenderEvents() {
    const el = document.getElementById('ps-events-text');
    if (!el) return;

    const events = _psMarket?.events;
    if (!events || !events.length) {
        el.textContent = 'No active market events.';
        return;
    }

    // msgs already contain severity prefix e.g. "🌟 MAJOR 📢 Tidal Wave Day: ..."
    const parts = events.map(e => e.msg);

    // Duplicate so the scroll loops seamlessly
    const ticker = parts.join('  •  ') + '     •     ' + parts.join('  •  ');
    el.textContent = ticker;

    // Scale speed to content length — ~80px/sec is comfortable reading speed
    const charCount = parts.join('').length;
    const duration = Math.max(60, charCount * 0.18);
    el.style.animationDuration = duration + 's';
}

// ── Trade Modal ───────────────────────────────────────────────────────────────

function psOpenModal(token) {
    _psTradeToken = token;
    _psTradeMode  = 'buy';

    const allEmojis = { ..._psMarket.type_emojis, ..._psMarket.element_emojis };
    const allLabels = { ...TYPE_LABELS, ...ELEM_LABELS };
    const price     = _psMarket.prices[token] ?? 0;
    const holding   = _psHoldings[token] ?? 0;
    const mult      = (_psMarket.multipliers && _psMarket.multipliers[token]) || 1;

    const multNote = mult > 1
        ? `<span class="ps-mult-badge" style="margin-left:4px">${mult}x cost (off-affinity)</span>`
        : '';

    document.getElementById('ps-modal-title').textContent = `Trade ${allLabels[token] ?? token} Token`;
    document.getElementById('ps-modal-info').innerHTML = `
        <img src="${allEmojis[token] ?? ''}" alt="${token}">
        <span>Market: <strong style="color:#ffd700">${fmtPrice(price)} XP</strong>${multNote}</span>
        <span>Held: <strong style="color:#ffd700">${holding}</strong></span>
        ${_psPetData ? `<span>Your XP: <strong style="color:#ffd700">${((_psPetData.total_xp ?? _psPetData.experience ?? 0)).toLocaleString()}</strong></span>` : ''}
    `;

    document.getElementById('ps-qty-input').value = 1;
    document.getElementById('ps-trade-status').textContent = '';
    document.getElementById('ps-trade-status').className = 'ps-trade-status';
    psModalTab('buy');
    psUpdateCostPreview();

    document.getElementById('ps-trade-modal').style.display = 'block';
    document.getElementById('ps-modal-backdrop').onclick = psCloseModal;
    document.getElementById('ps-modal-close').onclick    = psCloseModal;
    document.getElementById('ps-qty-input').oninput      = psUpdateCostPreview;
}

function psCloseModal() {
    document.getElementById('ps-trade-modal').style.display = 'none';
    _psTradeToken = null;
}

function psModalTab(mode) {
    _psTradeMode = mode;
    document.getElementById('ps-buy-tab').classList.toggle('active',  mode === 'buy');
    document.getElementById('ps-sell-tab').classList.toggle('active', mode === 'sell');
    psUpdateCostPreview();
}

function psAdjQty(delta) {
    const inp = document.getElementById('ps-qty-input');
    inp.value = Math.max(1, (parseInt(inp.value) || 1) + delta);
    psUpdateCostPreview();
}

function psUpdateCostPreview() {
    if (!_psTradeToken || !_psMarket) return;
    const qty   = Math.max(1, parseInt(document.getElementById('ps-qty-input').value) || 1);
    const price = _psMarket.prices[_psTradeToken] ?? 0;
    const mult  = (_psTradeMode === 'buy' && _psMarket.multipliers)
        ? (_psMarket.multipliers[_psTradeToken] || 1)
        : 1;
    const total = price * mult * qty;
    const el    = document.getElementById('ps-cost-preview');

    if (_psTradeMode === 'buy') {
        const xp = _psPetData?.total_xp ?? _psPetData?.experience ?? 0;
        const canAfford = xp >= total;
        const multStr = mult > 1 ? ` <span style="color:#f4a336">(${mult}x off-affinity)</span>` : '';
        el.innerHTML = `Cost: <span class="ps-cost-xp">${fmtPrice(total)} XP</span>${multStr}` +
            (canAfford ? '' : ` <span style="color:#f44336">(need ${fmtPrice(total - xp)} more)</span>`);
    } else {
        const held = _psHoldings[_psTradeToken] ?? 0;
        const payout = price * qty;
        const canSell = held >= qty;
        el.innerHTML = `Payout: <span class="ps-cost-xp">${fmtPrice(payout)} XP</span>` +
            (canSell ? ` (have ${held})` : ` <span style="color:#f44336">(only have ${held})</span>`);
    }
}

async function psConfirmTrade() {
    if (!_psTradeToken) return;
    const qty = Math.max(1, parseInt(document.getElementById('ps-qty-input').value) || 1);
    const btn = document.getElementById('ps-confirm-btn');
    const status = document.getElementById('ps-trade-status');

    btn.disabled = true;
    status.textContent = 'Processing…';
    status.className = 'ps-trade-status';

    try {
        const endpoint = _psTradeMode === 'buy' ? '/api/pet-stock/buy' : '/api/pet-stock/sell';
        const r = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: _psTradeToken, quantity: qty }),
        });
        const d = await r.json();

        if (d.ok) {
            const verb = _psTradeMode === 'buy' ? 'Bought' : 'Sold';
            const xpWord = _psTradeMode === 'buy' ? `−${d.cost?.toLocaleString()}` : `+${d.payout?.toLocaleString()}`;
            let msg = `✅ ${verb} ×${qty} | XP: ${xpWord} | Now holding: ${d.new_qty}`;

            if (d.level_change) {
                const lc = d.level_change;
                const oldLvl = lc.old_level;
                const newLvl = lc.new_level;
                if (newLvl > oldLvl) {
                    // Level up — show stat gains
                    const gains = lc.ATT || lc.DEF || lc.INT || lc.DEX || lc.HAP || lc.ENE
                        ? Object.entries({ ATT: lc.ATT, DEF: lc.DEF, INT: lc.INT, DEX: lc.DEX, HAP: lc.HAP, ENE: lc.ENE })
                            .filter(([, v]) => v > 0)
                            .map(([k, v]) => `${k}+${v}`)
                            .join(' ')
                        : '';
                    msg += ` | 🎉 LEVEL UP! ${oldLvl}→${newLvl}` + (gains ? ` (${gains})` : '');
                } else if (newLvl < oldLvl) {
                    msg += ` | ⬇️ Level down: ${oldLvl}→${newLvl}`;
                }
            }

            status.textContent = msg;
            status.className = 'ps-trade-status success';

            // Update local state
            _psHoldings[_psTradeToken] = d.new_qty;
            if (_psPetData) _psPetData.total_xp = d.new_xp;

            // Re-render cards
            psRenderAll();
            psUpdateCostPreview();
        } else {
            status.textContent = `❌ ${d.error || 'Trade failed'}`;
            status.className = 'ps-trade-status error';
        }
    } catch (e) {
        status.textContent = '❌ Network error';
        status.className = 'ps-trade-status error';
    } finally {
        btn.disabled = false;
    }
}

// ── Boot ──────────────────────────────────────────────────────────────────────

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPetStock);
} else {
    initPetStock();
}

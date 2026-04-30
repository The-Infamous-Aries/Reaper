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

    const allEmojis = { ..._psMarket.type_emojis, ..._psMarket.element_emojis };
    const allLabels = { ...TYPE_LABELS, ...ELEM_LABELS };
    const price     = _psMarket.prices[token] ?? 0;
    const holding   = _psHoldings[token] ?? 0;
    const mult      = (_psMarket.multipliers && _psMarket.multipliers[token]) || 1;
    const xp        = _psPetData ? (_psPetData.total_xp ?? _psPetData.experience ?? 0) : 0;

    // Header
    const icon = document.getElementById('ps-modal-icon');
    icon.src = allEmojis[token] ?? '';
    icon.alt = token;
    document.getElementById('ps-modal-title').textContent = `Trade ${allLabels[token] ?? token} Token`;

    // Stats bar
    document.getElementById('ps-modal-stats').innerHTML = `
        <div class="ps-stat">
            <span class="ps-stat-label">Market Price</span>
            <span class="ps-stat-value">${fmtPrice(price)} XP</span>
        </div>
        <div class="ps-stat">
            <span class="ps-stat-label">You Hold</span>
            <span class="ps-stat-value">${holding.toLocaleString()}</span>
        </div>
        <div class="ps-stat">
            <span class="ps-stat-label">Your XP</span>
            <span class="ps-stat-value">${xp.toLocaleString()}</span>
        </div>
    `;

    // Affinity badge
    const affEl = document.getElementById('ps-modal-affinity');
    if (mult > 1) {
        affEl.innerHTML = `<span class="ps-affinity-bad">⚠️ Off-affinity token — Buy costs ×${mult} &nbsp;|&nbsp; Sell pays ÷${mult}</span>`;
    } else {
        affEl.innerHTML = `<span class="ps-affinity-ok">✅ Affinity match — no penalty</span>`;
    }

    // Reset inputs & status
    document.getElementById('ps-buy-qty').value  = 1;
    document.getElementById('ps-sell-qty').value = 1;
    document.getElementById('ps-trade-status').textContent = '';
    document.getElementById('ps-trade-status').className   = 'ps-trade-status';

    psUpdatePreviews();

    document.getElementById('ps-trade-modal').style.display = 'block';
    document.getElementById('ps-modal-backdrop').onclick = psCloseModal;
    document.getElementById('ps-modal-close').onclick    = psCloseModal;
}

function psCloseModal() {
    document.getElementById('ps-trade-modal').style.display = 'none';
    _psTradeToken = null;
}

function psAdjQty(side, delta) {
    const inp = document.getElementById(side === 'buy' ? 'ps-buy-qty' : 'ps-sell-qty');
    inp.value = Math.max(1, (parseInt(inp.value) || 1) + delta);
    psUpdatePreviews();
}

function psUpdatePreviews() {
    if (!_psTradeToken || !_psMarket) return;
    const price = _psMarket.prices[_psTradeToken] ?? 0;
    const mult  = (_psMarket.multipliers && _psMarket.multipliers[_psTradeToken]) || 1;
    const xp    = _psPetData ? (_psPetData.total_xp ?? _psPetData.experience ?? 0) : 0;
    const held  = _psHoldings[_psTradeToken] ?? 0;

    // Buy preview
    const buyQty  = Math.max(1, parseInt(document.getElementById('ps-buy-qty').value) || 1);
    const buyCost = Math.round(price * mult * buyQty);
    const canAfford = xp >= buyCost;
    const buyMultStr = mult > 1 ? ` <span style="color:#f4a336">(×${mult} off-affinity)</span>` : '';
    const buyShortfall = canAfford ? '' : ` <span style="color:#f44336">(need ${fmtPrice(buyCost - xp)} more)</span>`;
    document.getElementById('ps-buy-preview').innerHTML =
        `Cost: <span class="ps-cost-xp">${fmtPrice(buyCost)} XP</span>${buyMultStr}${buyShortfall}`;

    // Sell preview
    const sellQty    = Math.max(1, parseInt(document.getElementById('ps-sell-qty').value) || 1);
    const sellPayout = Math.round(price * sellQty / mult);
    const canSell    = held >= sellQty;
    const sellMultStr = mult > 1 ? ` <span style="color:#f4a336">(÷${mult} off-affinity)</span>` : '';
    const sellHeld = canSell
        ? ` <span style="color:#888">(have ${held.toLocaleString()})</span>`
        : ` <span style="color:#f44336">(only have ${held.toLocaleString()})</span>`;
    document.getElementById('ps-sell-preview').innerHTML =
        `Payout: <span class="ps-cost-xp">${fmtPrice(sellPayout)} XP</span>${sellMultStr}${sellHeld}`;
}

function _psHandleResult(d, verb, qty, mode) {
    const status = document.getElementById('ps-trade-status');
    if (!d.ok) {
        status.textContent = `❌ ${d.error || 'Trade failed'}`;
        status.className = 'ps-trade-status error';
        return;
    }

    const xpWord = mode === 'buy'
        ? `−${d.cost?.toLocaleString()}`
        : `+${d.payout?.toLocaleString()}`;
    const penaltyStr = (mode === 'sell' && d.mult > 1) ? ` (÷${d.mult} off-affinity)` : '';
    let msg = `✅ ${verb} ×${qty} | XP: ${xpWord}${penaltyStr} | Holding: ${d.new_qty?.toLocaleString()}`;

    if (d.level_change) {
        const lc = d.level_change;
        if (lc.new_level > lc.old_level) {
            const gainStr = Object.entries(lc.gains || {}).filter(([,v])=>v>0).map(([k,v])=>`${k}+${v}`).join(' ');
            msg += ` | 🎉 LEVEL UP! ${lc.old_level}→${lc.new_level}` + (gainStr ? ` (${gainStr})` : '');
        } else if (lc.new_level < lc.old_level) {
            const lossStr = Object.entries(lc.losses || {}).filter(([,v])=>v>0).map(([k,v])=>`${k}-${v}`).join(' ');
            msg += ` | 📉 Level down: ${lc.old_level}→${lc.new_level}` + (lossStr ? ` (${lossStr})` : '');
        }
    }

    status.textContent = msg;
    status.className = 'ps-trade-status success';

    _psHoldings[_psTradeToken] = d.new_qty;
    if (_psPetData) _psPetData.total_xp = d.new_xp;

    // Refresh stats bar XP + held
    const xpEl = document.querySelector('#ps-modal-stats .ps-stat:nth-child(3) .ps-stat-value');
    const heldEl = document.querySelector('#ps-modal-stats .ps-stat:nth-child(2) .ps-stat-value');
    if (xpEl)   xpEl.textContent  = d.new_xp?.toLocaleString() ?? '';
    if (heldEl) heldEl.textContent = d.new_qty?.toLocaleString() ?? '';

    psRenderAll();
    psUpdatePreviews();
}

async function psDoTrade(mode) {
    if (!_psTradeToken) return;
    const qty = Math.max(1, parseInt(document.getElementById(mode === 'buy' ? 'ps-buy-qty' : 'ps-sell-qty').value) || 1);
    const btn = document.getElementById(mode === 'buy' ? 'ps-buy-btn' : 'ps-sell-btn');
    const status = document.getElementById('ps-trade-status');

    btn.disabled = true;
    status.textContent = 'Processing…';
    status.className = 'ps-trade-status';

    try {
        const endpoint = mode === 'buy' ? '/api/pet-stock/buy' : '/api/pet-stock/sell';
        const r = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: _psTradeToken, quantity: qty }),
        });
        _psHandleResult(await r.json(), mode === 'buy' ? 'Bought' : 'Sold', qty, mode);
    } catch {
        status.textContent = '❌ Network error';
        status.className = 'ps-trade-status error';
    } finally {
        btn.disabled = false;
    }
}

async function psDoBulk(mode) {
    if (!_psTradeToken) return;
    const btn = document.getElementById(mode === 'buy' ? 'ps-buymax-btn' : 'ps-sellall-btn');
    const status = document.getElementById('ps-trade-status');
    const prevQty = _psHoldings[_psTradeToken] ?? 0;

    btn.disabled = true;
    status.textContent = 'Processing…';
    status.className = 'ps-trade-status';

    try {
        const endpoint = mode === 'buy' ? '/api/pet-stock/buy-all' : '/api/pet-stock/sell-all';
        const r = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: _psTradeToken }),
        });
        const d = await r.json();
        const traded = mode === 'buy' ? ((d.new_qty ?? 0) - prevQty) : prevQty;
        _psHandleResult(d, mode === 'buy' ? 'Bought' : 'Sold', traded, mode);
    } catch {
        status.textContent = '❌ Network error';
        status.className = 'ps-trade-status error';
    } finally {
        btn.disabled = false;
    }
}

// Legacy stubs kept so any old inline references don't hard-crash
function psModalTab() {}
function psConfirmTrade() { psDoTrade(_psTradeMode ?? 'buy'); }
function psBulkTrade()    { psDoBulk(_psTradeMode ?? 'buy'); }
function psUpdateCostPreview() { psUpdatePreviews(); }


// ── Boot ──────────────────────────────────────────────────────────────────────

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPetStock);
} else {
    initPetStock();
}

// Buy MAX functionality
async function psRefreshData() {
    await Promise.all([
        psLoadMarket(),
        psLoadHoldings(),
        psLoadPet()
    ]);
    psRenderAll();
    psRenderEvents();
}

function psShowBuyMaxConfirm() {
    if (!_psMarket || !_psPetData) {
        alert('Market data not loaded yet. Please wait a moment and try again.');
        return;
    }

    // Calculate preview
    const allTokens = [...Object.keys(_psMarket.type_emojis), ...Object.keys(_psMarket.element_emojis)];
    let totalCost = 0;
    let previewText = '';

    allTokens.forEach(token => {
        const price = _psMarket.prices[token] ?? 0;
        const mult = (_psMarket.multipliers && _psMarket.multipliers[token]) || 1;
        const costEach = Math.round(price * mult);
        const maxToBuy = 100000;
        const currentHolding = _psHoldings[token] ?? 0;
        const canBuy = Math.max(0, maxToBuy - currentHolding);
        const cost = costEach * canBuy;
        
        if (canBuy > 0) {
            totalCost += cost;
            previewText += `${token}: ${canBuy.toLocaleString()} tokens (${cost.toLocaleString()} XP)\n`;
        }
    });

    const xp = _psPetData ? (_psPetData.total_xp ?? _psPetData.experience ?? 0) : 0;
    previewText += `\nTotal Cost: ${totalCost.toLocaleString()} XP\nYour XP: ${xp.toLocaleString()}`;
    
    if (totalCost > xp) {
        previewText += `\n⚠️ Insufficient XP (need ${(totalCost - xp).toLocaleString()} more)`;
    }

    document.getElementById('ps-buymax-preview').textContent = previewText;
    document.getElementById('ps-buymax-modal').style.display = 'block';
}

function psCloseBuyMaxModal() {
    document.getElementById('ps-buymax-modal').style.display = 'none';
}

async function psExecuteBuyMax() {
    const btn = document.querySelector('.ps-confirm-yes');
    btn.disabled = true;
    btn.textContent = 'Processing...';

    try {
        const r = await fetch('/api/pet-stock/buy-max', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        });
        const result = await r.json();
        
        psCloseBuyMaxModal();
        
        if (result.ok) {
            alert(`✅ Buy MAX completed!\nTotal bought: ${result.total_bought.toLocaleString()} tokens\nTotal cost: ${result.total_cost.toLocaleString()} XP`);
            await psRefreshData();
        } else {
            alert(`❌ Buy MAX failed: ${result.error}`);
        }
    } catch (e) {
        alert('❌ Network error during Buy MAX');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Yes, Buy MAX';
    }
}

// Sell MAX functionality
function psShowSellMaxConfirm() {
    if (!_psMarket || !_psHoldings) {
        alert('Market data not loaded yet. Please wait a moment and try again.');
        return;
    }

    // Calculate preview
    let totalPayout = 0;
    let totalTokens = 0;
    let previewText = '';

    Object.entries(_psHoldings).forEach(([token, qty]) => {
        if (qty > 0) {
            const price = _psMarket.prices[token] ?? 0;
            const mult = (_psMarket.multipliers && _psMarket.multipliers[token]) || 1;
            const payout = Math.round(price * qty / mult);
            totalPayout += payout;
            totalTokens += qty;
            previewText += `${token}: ${qty.toLocaleString()} tokens (${payout.toLocaleString()} XP)\n`;
        }
    });

    if (totalTokens === 0) {
        alert('You don\'t have any tokens to sell.');
        return;
    }

    previewText += `\nTotal Tokens: ${totalTokens.toLocaleString()}\nTotal Payout: ${totalPayout.toLocaleString()} XP`;

    document.getElementById('ps-sellmax-preview').textContent = previewText;
    document.getElementById('ps-sellmax-modal').style.display = 'block';
}

function psCloseSellMaxModal() {
    document.getElementById('ps-sellmax-modal').style.display = 'none';
}

async function psExecuteSellMax() {
    const btn = document.querySelector('#ps-sellmax-modal .ps-confirm-yes');
    btn.disabled = true;
    btn.textContent = 'Processing...';

    try {
        const r = await fetch('/api/pet-stock/sell-max', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        });
        const result = await r.json();
        
        psCloseSellMaxModal();
        
        if (result.ok) {
            alert(`✅ Sell MAX completed!\nTotal sold: ${result.total_sold.toLocaleString()} tokens\nTotal payout: ${result.total_payout.toLocaleString()} XP`);
            await psRefreshData();
        } else {
            alert(`❌ Sell MAX failed: ${result.error}`);
        }
    } catch (e) {
        alert('❌ Network error during Sell MAX');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Yes, Sell ALL';
    }
}
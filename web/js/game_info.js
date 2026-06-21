// Game Info Page JavaScript - Extracted from game_info.html

// Info Selection functionality
function setupInfoSelection() {
    console.log('Setting up info selection...');
    const infoButtons = document.querySelectorAll('.graph-emoji-button');
    const contentSections = document.querySelectorAll('.info-content-section');
    
    console.log('Found buttons:', infoButtons.length);
    console.log('Found sections:', contentSections.length);

    infoButtons.forEach(button => {
        console.log('Setting up button:', button.dataset.infoType);
        button.addEventListener('click', function() {
            console.log('Button clicked:', this.dataset.infoType);
            const infoType = this.dataset.infoType;
            switchInfoSection(infoType);
        });
    });
}

// Function to restart ticker animations
function restartTickerAnimations() {
    const tickers = document.querySelectorAll('.lb-ticker-track');
    tickers.forEach(track => {
        if (track) {
            const isResource = track.closest('.resource-ticker');
            const duration = isResource ? '100s' : '120s';
            track.style.animation = `ticker-scroll ${duration} linear infinite`;
        }
    });
}

// Function to switch between info sections
function switchInfoSection(infoType) {
    console.log('Switching to section:', infoType);
    const infoButtons = document.querySelectorAll('.graph-emoji-button');
    const contentSections = document.querySelectorAll('.info-content-section');
    
    // Update button active states
    infoButtons.forEach(btn => btn.classList.remove('active'));
    const activeButton = document.querySelector(`[data-info-type="${infoType}"]`);
    if (activeButton) {
        activeButton.classList.add('active');
    }
    
    // Show/hide content sections
    contentSections.forEach(section => {
        section.classList.remove('active');
        if (section.id === infoType + '-section') {
            section.classList.add('active');
            
            // Restart ticker animations immediately
            restartTickerAnimations();
        }
    });
}

// Compact number formatter: 60356000 → "60.36m", 1500 → "1.5k", 999 → "999"
function fmtPrice(n) {
    n = Math.abs(n);
    if (n >= 1e9)  return (n / 1e9).toFixed(2).replace(/\.?0+$/, '') + 'b';
    if (n >= 1e6)  return (n / 1e6).toFixed(3).replace(/\.?0+$/, '') + 'm';
    if (n >= 1e3)  return (n / 1e3).toFixed(1).replace(/\.?0+$/, '') + 'k';
    return Math.round(n).toString();
}

// Generates a stock-like chart with buy and sell price lines
function generateStockLikeChart(historyData, resourceName) {    if (!historyData || historyData.length < 2) {
        return '<div class="chart-placeholder">Not enough historical data</div>';
    }

    const width = 400;
    const height = 120;
    const padding = { top: 20, right: 20, bottom: 30, left: 40 };

    const buyPrices = historyData.map(d => d.buy).filter(p => p > 0);
    const sellPrices = historyData.map(d => d.sell).filter(p => p > 0);
    
    if (buyPrices.length < 2 && sellPrices.length < 2) {
        return '<div class="chart-placeholder">Not enough valid price data</div>';
    }

    const allPrices = [...buyPrices, ...sellPrices];
    const minPrice = Math.min(...allPrices);
    const maxPrice = Math.max(...allPrices);
    const range = (maxPrice - minPrice) || 1;

    const drawableHeight = height - padding.top - padding.bottom;

    const getPath = (prices, color) => {
        if (prices.length < 2) return '';
        let path = 'M';
        for (let i = 0; i < historyData.length; i++) {
            const dataPoint = historyData[i];
            const price = (prices === buyPrices) ? dataPoint.buy : dataPoint.sell;
            if (price > 0) {
                const x = padding.left + (i / (historyData.length - 1)) * (width - padding.left - padding.right);
                const y = height - padding.bottom - ((price - minPrice) / range) * drawableHeight;
                path += ` ${x},${y}`;
                if (i > 0) path += 'L';
            }
        }
        return `<path d="${path.slice(0, -1)}" stroke="${color}" stroke-width="2" fill="none" stroke-linecap="round"/>`;
    };

    const buyPath = getPath(buyPrices, '#4caf50'); // Green for buy
    const sellPath = getPath(sellPrices, '#f44336'); // Red for sell

    // Legend
    const legend = `
        <g transform="translate(${padding.left}, 0)">
            <rect x="0" y="5" width="10" height="10" fill="#4caf50"/>
            <text x="15" y="14" font-size="12" fill="#fff">Buy</text>
            <rect x="50" y="5" width="10" height="10" fill="#f44336"/>
            <text x="65" y="14" font-size="12" fill="#fff">Sell</text>
        </g>
    `;

    return `
        <svg class="advanced-chart" viewBox="0 0 ${width} ${height}">
            ${legend}
            ${buyPath}
            ${sellPath}
        </svg>
    `;
}

// ---------------------------------------------------------------------------
// Alert modal helpers
// ---------------------------------------------------------------------------

// key format: "resource:price_type:direction"  e.g. "food:buy:below"
// key: "resource:price_type:direction"  e.g. "food:buy:below"
let _activeAlerts = {};

async function loadUserAlerts() {
    try {
        const res = await fetch('/api/alerts');
        if (!res.ok) return;
        const alerts = await res.json();
        _activeAlerts = {};
        alerts.forEach(a => {
            _activeAlerts[`${a.resource}:${a.price_type}:${a.direction}`] = a.threshold;
        });
    } catch (_) {}
}

function openAlertModal(resource, buyPrice, sellPrice) {
    document.getElementById('rss-alert-modal')?.remove();

    // All 4 combinations: buy/sell price × above/below direction
    const combos = [
        { pt: 'buy',  dir: 'above', ptLabel: 'Buy price',  dirLabel: '≥ rises to/above', hint: buyPrice  },
        { pt: 'buy',  dir: 'below', ptLabel: 'Buy price',  dirLabel: '≤ drops to/below', hint: buyPrice  },
        { pt: 'sell', dir: 'above', ptLabel: 'Sell price', dirLabel: '≥ rises to/above', hint: sellPrice },
        { pt: 'sell', dir: 'below', ptLabel: 'Sell price', dirLabel: '≤ drops to/below', hint: sellPrice },
    ];

    const rowsHtml = combos.map(c => {
        const existing = _activeAlerts[`${resource}:${c.pt}:${c.dir}`] ?? '';
        const delHtml  = existing !== ''
            ? `<button class="rss-btn rss-btn-del" data-pt="${c.pt}" data-dir="${c.dir}">×</button>`
            : '';
        return `
        <div class="rss-alert-row">
            <label>
                <span class="rss-type-badge ${c.pt}">${c.ptLabel}</span>
                <span class="rss-dir-label">${c.dirLabel}</span>
            </label>
            <div class="rss-input-row">
                <span class="rss-dollar">$</span>
                <input type="number" class="rss-input" data-pt="${c.pt}" data-dir="${c.dir}"
                       min="0" step="1" placeholder="${c.hint}" value="${existing}">
                <button class="rss-btn rss-btn-set" data-pt="${c.pt}" data-dir="${c.dir}">Set</button>
                ${delHtml}
            </div>
        </div>`;
    }).join('');

    const modal = document.createElement('div');
    modal.id = 'rss-alert-modal';
    modal.innerHTML = `
        <div class="rss-modal-backdrop" id="rss-modal-backdrop"></div>
        <div class="rss-modal-box">
            <div class="rss-modal-header">
                <span>&#x1F514; Price Alerts &mdash; ${resource.toUpperCase()}</span>
                <button class="rss-modal-close" id="rss-modal-close">&times;</button>
            </div>
            <div class="rss-modal-body">
                <p class="rss-modal-hint">
                    Current:
                    <span class="rss-price-tag buy">Buy $${buyPrice}</span>
                    <span class="rss-price-tag sell">Sell $${sellPrice}</span>
                </p>
                ${rowsHtml}
                <p id="rss-modal-status" class="rss-modal-status"></p>
            </div>
        </div>
    `;
    document.body.appendChild(modal);

    const status = document.getElementById('rss-modal-status');
    const close  = () => modal.remove();
    document.getElementById('rss-modal-close').addEventListener('click', close);
    document.getElementById('rss-modal-backdrop').addEventListener('click', close);

    // Set buttons
    modal.querySelectorAll('.rss-btn-set').forEach(btn => {
        btn.addEventListener('click', async () => {
            const pt    = btn.dataset.pt;
            const dir   = btn.dataset.dir;
            const input = modal.querySelector(`.rss-input[data-pt="${pt}"][data-dir="${dir}"]`);
            const val   = parseFloat(input.value);
            if (!val || val <= 0) {
                status.textContent = 'Enter a valid price.';
                status.className = 'rss-modal-status error';
                return;
            }
            try {
                const r = await fetch('/api/alerts', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ resource, price_type: pt, direction: dir, threshold: val })
                });
                if (r.status === 401) {
                    status.textContent = 'Log in with Discord to set alerts.';
                    status.className = 'rss-modal-status error';
                    return;
                }
                if (!r.ok) throw new Error(await r.text());
                _activeAlerts[`${resource}:${pt}:${dir}`] = val;
                const comp = dir === 'above' ? '≥' : '≤';
                status.textContent = `✅ ${pt} ${comp} $${val.toLocaleString()} alert set`;
                status.className = 'rss-modal-status success';
                updateBellState(resource);
            } catch (e) {
                status.textContent = 'Error: ' + e.message;
                status.className = 'rss-modal-status error';
            }
        });
    });

    // Delete buttons
    modal.querySelectorAll('.rss-btn-del').forEach(btn => {
        btn.addEventListener('click', async () => {
            const pt  = btn.dataset.pt;
            const dir = btn.dataset.dir;
            try {
                const r = await fetch(
                    `/api/alerts?resource=${resource}&price_type=${pt}&direction=${dir}`,
                    { method: 'DELETE' }
                );
                if (!r.ok) throw new Error(await r.text());
                delete _activeAlerts[`${resource}:${pt}:${dir}`];
                const comp = dir === 'above' ? '≥' : '≤';
                status.textContent = `🗑 ${pt} ${comp} alert removed.`;
                status.className = 'rss-modal-status success';
                updateBellState(resource);
                const input = modal.querySelector(`.rss-input[data-pt="${pt}"][data-dir="${dir}"]`);
                if (input) input.value = '';
                btn.remove();
            } catch (e) {
                status.textContent = 'Error: ' + e.message;
                status.className = 'rss-modal-status error';
            }
        });
    });
}

function updateBellState(resource) {
    const bell = document.querySelector(`.rc-bell-btn[data-resource="${resource}"]`);
    if (!bell) return;
    const hasAlert = Object.keys(_activeAlerts).some(k => k.startsWith(`${resource}:`));
    bell.classList.toggle('active', hasAlert);
    bell.title = hasAlert ? 'Alert active — click to edit' : 'Set price alert';
}

// ---------------------------------------------------------------------------
// Chart zoom modal — fetches full history on demand
// ---------------------------------------------------------------------------
function generateFullHistoryChart(historyData) {
    if (!historyData || historyData.length < 2) {
        return '<div class="chart-placeholder">Not enough data</div>';
    }

    const PX_PER_POINT = 5;
    const H = 260;
    const PAD = { top: 16, right: 24, bottom: 52 };
    const W = Math.max(900, historyData.length * PX_PER_POINT);
    const dW = W - PAD.right;
    const dH = H - PAD.top - PAD.bottom;

    const buyPrices  = historyData.map(d => d.buy).filter(p => p > 0);
    const sellPrices = historyData.map(d => d.sell).filter(p => p > 0);
    if (!buyPrices.length && !sellPrices.length) {
        return '<div class="chart-placeholder">No valid price data</div>';
    }

    const allPrices = [...buyPrices, ...sellPrices];
    const rawMin = Math.min(...allPrices);
    const rawMax = Math.max(...allPrices);
    // Nice round Y bounds
    const range   = rawMax - rawMin || 1;
    const pad     = range * 0.08;
    const minP    = rawMin - pad;
    const maxP    = rawMax + pad;
    const pRange  = maxP - minP;

    const toX = i  => (i / (historyData.length - 1)) * dW;
    const toY = p  => H - PAD.bottom - ((p - minP) / pRange) * dH;

    // --- Y axis ticks (6 ticks) ---
    const Y_TICKS = 6;
    let yGrid = '';
    for (let i = 0; i <= Y_TICKS; i++) {
        const val = minP + (pRange / Y_TICKS) * i;
        const y   = toY(val);
        yGrid   += `<line x1="0" y1="${y.toFixed(1)}" x2="${W - PAD.right}" y2="${y.toFixed(1)}" stroke="#252528" stroke-width="1"/>`;
    }

    // --- X axis ticks: one label per day, minor ticks every 6 hours ---
    // 15-min intervals → 96 per day, 24 per 6h
    const MINOR_EVERY = 24; // 6 hours
    const MAJOR_EVERY = 96; // 1 day
    let xGrid = '', xLabels = '';
    historyData.forEach((pt, i) => {
        if (i % MINOR_EVERY !== 0) return;
        const x   = toX(i);
        const ts  = pt.timestamp ? new Date(pt.timestamp * 1000) : null;
        const isMajor = i % MAJOR_EVERY === 0;
        xGrid += `<line x1="${x.toFixed(1)}" y1="${PAD.top}" x2="${x.toFixed(1)}" y2="${H - PAD.bottom}" stroke="${isMajor ? '#333' : '#1e1e20'}" stroke-width="1"/>`;
        if (ts && isMajor) {
            const lbl = `${ts.getMonth()+1}/${ts.getDate()}`;
            xLabels += `<text x="${x.toFixed(1)}" y="${H - PAD.bottom + 18}" text-anchor="middle" font-size="11" fill="#777" font-family="JetBrains Mono,monospace">${lbl}</text>`;
        } else if (ts) {
            const lbl = `${ts.getHours().toString().padStart(2,'0')}:00`;
            xLabels += `<text x="${x.toFixed(1)}" y="${H - PAD.bottom + 14}" text-anchor="middle" font-size="9" fill="#444" font-family="JetBrains Mono,monospace">${lbl}</text>`;
        }
    });

    // --- Price paths ---
    const buildPath = key => {
        let d = '', first = true;
        historyData.forEach((pt, i) => {
            const p = pt[key];
            if (!p || p <= 0) return;
            const x = toX(i).toFixed(1), y = toY(p).toFixed(1);
            d += first ? `M${x},${y}` : ` L${x},${y}`;
            first = false;
        });
        return d;
    };

    const buyD  = buildPath('buy');
    const sellD = buildPath('sell');

    // --- Axis line ---
    const xAxis = `<line x1="0" y1="${H - PAD.bottom}" x2="${W - PAD.right}" y2="${H - PAD.bottom}" stroke="#444" stroke-width="1.5"/>`;

    return `
        <div class="chart-history-shell">
            <svg class="chart-history-plot" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}">
                ${yGrid}${xGrid}
                ${xAxis}
                ${xLabels}
                ${buyD  ? `<path d="${buyD}"  stroke="#4caf50" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>` : ''}
                ${sellD ? `<path d="${sellD}" stroke="#f44336" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>` : ''}
                <g class="chart-history-hover-layer" style="display:none">
                    <line class="chart-history-crosshair" x1="0" y1="${PAD.top}" x2="0" y2="${H - PAD.bottom}"/>
                    <circle class="chart-history-point-buy" r="4"/>
                    <circle class="chart-history-point-sell" r="4"/>
                    <rect class="chart-history-time-bg" x="0" y="2" width="86" height="18" rx="4"/>
                    <text class="chart-history-time-label" x="0" y="15" text-anchor="middle"></text>
                </g>
                <rect class="chart-history-hitbox" x="0" y="${PAD.top}" width="${W - PAD.right}" height="${dH}"/>
            </svg>
        </div>`;
}

function setupFullHistoryChartInteraction(scrollEl, historyData) {
    const shell = scrollEl.querySelector('.chart-history-shell');
    const plot = scrollEl.querySelector('.chart-history-plot');
    const modalBox = scrollEl.closest('.chart-modal-box');
    if (!shell || !plot || !historyData || historyData.length < 2) return;

    const hoverLayer = plot.querySelector('.chart-history-hover-layer');
    const crosshair = plot.querySelector('.chart-history-crosshair');
    const buyPoint = plot.querySelector('.chart-history-point-buy');
    const sellPoint = plot.querySelector('.chart-history-point-sell');
    const timeBg = plot.querySelector('.chart-history-time-bg');
    const timeLabel = plot.querySelector('.chart-history-time-label');
    const activePrices = modalBox?.querySelector('.chart-modal-active-readout');
    const activeTime = modalBox?.querySelector('.chart-modal-active-time');
    const activeBuy = modalBox?.querySelector('.chart-modal-active-buy');
    const activeSell = modalBox?.querySelector('.chart-modal-active-sell');
    if (!hoverLayer || !crosshair || !activePrices || !activeTime || !activeBuy || !activeSell) return;

    const H = 260;
    const PAD = { top: 16, right: 24, bottom: 52 };
    const viewBox = plot.viewBox.baseVal;
    const dW = viewBox.width - PAD.right;
    const dH = H - PAD.top - PAD.bottom;
    const prices = historyData.flatMap(pt => [pt.buy, pt.sell]).filter(p => p > 0);
    if (!prices.length) return;

    const rawMin = Math.min(...prices);
    const rawMax = Math.max(...prices);
    const range = rawMax - rawMin || 1;
    const pad = range * 0.08;
    const minP = rawMin - pad;
    const maxP = rawMax + pad;
    const pRange = maxP - minP;
    const toX = i => (i / (historyData.length - 1)) * dW;
    const toY = p => H - PAD.bottom - ((p - minP) / pRange) * dH;
    const fmtMoney = val => val && val > 0
        ? '$' + Number(val).toLocaleString(undefined, { maximumFractionDigits: 0 })
        : '--';
    const fmtTime = timestamp => {
        if (!timestamp) return '';
        const dt = new Date(timestamp * 1000);
        const hours = dt.getHours().toString().padStart(2, '0');
        const minutes = dt.getMinutes().toString().padStart(2, '0');
        return `${dt.getMonth() + 1}/${dt.getDate()} ${hours}:${minutes}`;
    };

    const setPoint = (point, x, price) => {
        if (!point) return;
        if (!price || price <= 0) {
            point.style.display = 'none';
            return;
        }
        point.style.display = '';
        point.setAttribute('cx', x.toFixed(1));
        point.setAttribute('cy', toY(price).toFixed(1));
    };

    const updateHighlight = clientX => {
        const rect = plot.getBoundingClientRect();
        if (!rect.width) return;
        const svgX = Math.max(0, Math.min(dW, ((clientX - rect.left) / rect.width) * viewBox.width));
        const index = Math.max(0, Math.min(historyData.length - 1, Math.round((svgX / dW) * (historyData.length - 1))));
        const pt = historyData[index];
        const x = toX(index);
        const timeText = fmtTime(pt.timestamp);

        hoverLayer.style.display = '';
        activePrices.classList.add('active');
        crosshair.setAttribute('x1', x.toFixed(1));
        crosshair.setAttribute('x2', x.toFixed(1));
        setPoint(buyPoint, x, pt.buy);
        setPoint(sellPoint, x, pt.sell);

        if (timeBg && timeLabel) {
            const labelX = Math.max(45, Math.min(dW - 45, x));
            timeBg.setAttribute('x', (labelX - 43).toFixed(1));
            timeLabel.setAttribute('x', labelX.toFixed(1));
            timeLabel.textContent = timeText;
        }

        activeTime.textContent = timeText;
        activeBuy.textContent = fmtMoney(pt.buy);
        activeSell.textContent = fmtMoney(pt.sell);
    };

    plot.addEventListener('pointerdown', e => updateHighlight(e.clientX));
    plot.addEventListener('pointermove', e => {
        if (e.pointerType === 'mouse' || e.buttons || e.pointerType === 'pen') {
            updateHighlight(e.clientX);
        }
    });
    requestAnimationFrame(() => {
        const rect = plot.getBoundingClientRect();
        updateHighlight(rect.right - 1);
    });
}

function openChartModal(resource, iconSrc) {
    document.getElementById('chart-zoom-modal')?.remove();

    const modal = document.createElement('div');
    modal.id = 'chart-zoom-modal';
    modal.innerHTML = `
        <div class="chart-modal-backdrop" id="chart-modal-backdrop">
            <div class="chart-modal-box" id="chart-modal-inner">
                <div class="chart-modal-header">
                    <div class="chart-modal-title">
                        ${iconSrc ? `<img src="${iconSrc}" alt="${resource}">` : ''}
                        ${resource.toUpperCase()} — Full Price History
                    </div>
                    <button class="chart-modal-close" id="chart-modal-close">&times;</button>
                </div>
                <div class="chart-modal-legend">
                    <div class="chart-modal-legend-item">
                        <div class="chart-modal-legend-dot" style="background:#4caf50"></div>
                        Buy price
                    </div>
                    <div class="chart-modal-legend-item">
                        <div class="chart-modal-legend-dot" style="background:#f44336"></div>
                        Sell price
                    </div>
                    <div class="chart-modal-active-readout" aria-live="polite">
                        <span class="chart-modal-active-time"></span>
                        <span class="chart-modal-active-price buy">Buy <strong class="chart-modal-active-buy"></strong></span>
                        <span class="chart-modal-active-price sell">Sell <strong class="chart-modal-active-sell"></strong></span>
                    </div>
                </div>
                <div class="chart-modal-scroll" id="chart-modal-scroll">
                    <div class="chart-modal-loading">
                        <div class="chart-modal-spinner"></div>
                        Loading full history…
                    </div>
                </div>
                <div class="chart-modal-hint">← scroll to explore full history →</div>
            </div>
        </div>`;

    document.body.appendChild(modal);

    const close = () => modal.remove();
    document.getElementById('chart-modal-close').addEventListener('click', close);
    document.getElementById('chart-modal-backdrop').addEventListener('click', e => {
        if (e.target === document.getElementById('chart-modal-backdrop')) close();
    });
    document.addEventListener('keydown', function onKey(e) {
        if (e.key === 'Escape') { close(); document.removeEventListener('keydown', onKey); }
    });

    // Fetch full history on demand
    fetch(`/api/game-info/resource-history/${resource}`)
        .then(r => { if (!r.ok) throw new Error('Failed to load history'); return r.json(); })
        .then(data => {
            const scrollEl = document.getElementById('chart-modal-scroll');
            if (!scrollEl) return;
            const history = data.history || [];
            const days = history.length > 0 ? (history.length / 96).toFixed(1) : '?';
            // Update title with day count
            const titleEl = modal.querySelector('.chart-modal-title');
            if (titleEl) {
                titleEl.innerHTML = `${iconSrc ? `<img src="${iconSrc}" alt="${resource}" style="width:24px;height:24px">` : ''}
                    ${resource.toUpperCase()} — Full Price History <span style="color:#888;font-size:0.8rem;font-weight:400">(${days} days)</span>`;
            }
            scrollEl.innerHTML = generateFullHistoryChart(history);
            setupFullHistoryChartInteraction(scrollEl, history);
            // Scroll to most recent (right side)
            requestAnimationFrame(() => { scrollEl.scrollLeft = scrollEl.scrollWidth; });
        })
        .catch(err => {
            const scrollEl = document.getElementById('chart-modal-scroll');
            if (scrollEl) scrollEl.innerHTML = `<div class="chart-placeholder" style="height:200px">Error loading history: ${err.message}</div>`;
        });
}

// ---------------------------------------------------------------------------
// Main execution function to run when the page is ready
// ---------------------------------------------------------------------------
function initializeGameInfo() {
    console.log('Initializing Game Info page...');
    
    const marketContainer = document.getElementById('market-prices');
    if (!marketContainer) {
        console.log('Game Info containers not found, skipping initialization');
        return;
    }
    
    setupInfoSelection();

    // Load user's existing alerts so bells reflect current state
    loadUserAlerts();

    // --- FETCH: Market Prices ---
    fetch('/api/game-info/resource-prices-comparison')
        .then(response => response.json())
        .then(data => {
            const marketContainer = document.getElementById('market-prices');
            const tickerContainer = document.getElementById('resources-ticker-container');
            if (!marketContainer || !tickerContainer) return;

            console.log('Resource prices data received:', data);
            const prices = data.current || {};
            const oldPrices = data.previous || {};
            const history = data.history || {};
            const hasComparison = data.has_comparison_data || false;
            
            console.log('Current prices:', Object.keys(prices));
            console.log('History data available for:', Object.keys(history));

            // Specific check for credit and aluminum
            console.log('History for credit:', history['credit']);
            console.log('History for aluminum:', history['aluminum']);

            const resourceEmojis = { /* Emojis remain the same */
                'credit': '/static/Emojis/Resources/credit.png', 'food': '/static/Emojis/Resources/food.png', 'uranium': '/static/Emojis/Resources/uranium.png',
                'oil': '/static/Emojis/Resources/oil.png', 'gasoline': '/static/Emojis/Resources/gasoline.png', 'lead': '/static/Emojis/Resources/lead.png',
                'munitions': '/static/Emojis/Resources/munitions.png', 'bauxite': '/static/Emojis/Resources/bauxite.png', 'aluminum': '/static/Emojis/Resources/aluminum.png',
                'coal': '/static/Emojis/Resources/coal.png', 'iron': '/static/Emojis/Resources/iron.png', 'steel': '/static/Emojis/Resources/steel.png'
            };
            const resourceOrder = [
                'credit', 'food', 'uranium', 'oil', 'gasoline', 'lead', 
                'munitions', 'bauxite', 'aluminum', 'coal', 'iron', 'steel'
            ];

            // --- Generate Resource Ticker ---
            let tickerHtml = '';
            resourceOrder.forEach(resource => {
                const priceData = prices[resource];
                if (!priceData) return;

                const margin = (priceData.buy > 0 && priceData.sell > 0) ? priceData.buy - priceData.sell : 0;
        const marginClass = margin > 0 ? 'positive' : 'negative';

                tickerHtml += `
                    <div class="resource-ticker-item">
                        <img src="${resourceEmojis[resource]}" class="lb-ticker-icon">
                        <span class="lb-ticker-name">${resource.toUpperCase()}:</span>
                        <span class="rt-value">$${priceData.avg.toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0})}</span>
                        <span class="rt-margin ${marginClass}">$${margin.toFixed(0)}</span>
                    </div>
                `;
            });

            // Duplicate the ticker content for seamless scrolling
            if (tickerHtml) {
                tickerContainer.innerHTML = `<div class="resource-ticker"><div class="lb-ticker-track">${tickerHtml}${tickerHtml}</div></div>`;
                
                // Immediate animation start
                const track = tickerContainer.querySelector('.lb-ticker-track');
                if (track) {
                    track.style.animation = 'ticker-scroll 100s linear infinite';
                }
            } else {
                tickerContainer.innerHTML = `<h4 class="mb-0 p-3" style="color: #ffd700; text-align: center; display: flex; align-items: center; justify-content: center;"><img src="/static/Emojis/Menu/graph.png" class="home-card-icon me-2" style="width: 28px; height: 28px;">Market Prices</h4>`;
            }

            let html = '<div class="resource-grid">';
            
            for (const resource of resourceOrder) {
                const priceData = prices[resource];
                
                // Handle missing data - show placeholder card
                if (!priceData) {
                    html += `
                        <div class="resource-card neutral">
                            <div class="rc-header" style="position: relative;">
                                <img src="${resourceEmojis[resource]}" class="rc-icon">
                                <div style="display: flex; flex-direction: row; align-items: center; justify-content: space-between; width: 100%;">
                                    <span class="rc-name">${resource.toUpperCase()}</span>
                                    <div style="display: flex; align-items: center; gap: 8px;">
                                        <span style="font-size: 1.3rem; font-weight: 700; color: #fff;">No Data</span>
                                    </div>
                                </div>
                            </div>
                            <div class="rc-body">
                                <div class="rc-chart-container">
                                    <div class="chart-placeholder">Awaiting data...</div>
                                </div>
                            </div>
                            <div class="rc-footer">
                                <div class="rc-footer-stats">
                                    <div class="rc-footer-item">
                                        <span class="rc-label">Buy</span>
                                        <span class="rc-value">-</span>
                                    </div>
                                    <div class="rc-footer-item">
                                        <span class="rc-label">Sell</span>
                                        <span class="rc-value">-</span>
                                    </div>
                                    <div class="rc-footer-item">
                                        <span class="rc-label">Margin</span>
                                        <span class="rc-value">-</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                    continue;
                }

                const price = priceData.avg;
                const oldPrice = (oldPrices[resource] && oldPrices[resource].avg) ? oldPrices[resource].avg : price;
                const valueChange = price - oldPrice;
                const percentChange = oldPrice > 0 ? (valueChange / oldPrice) * 100 : 0;

                const margin = (priceData.buy > 0 && priceData.sell > 0) ? priceData.buy - priceData.sell : 0;
                const marginClass = margin > 0 ? 'positive' : (margin < 0 ? 'negative' : 'neutral');

                let trendColor = '#9e9e9e'; // Neutral Gray
                let trendClass = 'neutral';
                if (valueChange > 0) {
                    trendColor = '#4caf50'; // Green
                    trendClass = 'positive';
                } else if (valueChange < 0) {
                    trendColor = '#f44336'; // Red
                    trendClass = 'negative';
                }

                const fullHistory = history[resource] || [];
                let chart;
                if (fullHistory.length > 1) {
                    const displayHistory = fullHistory.slice(-144); // Get the last 1.5 days to display
                    chart = generateStockLikeChart(displayHistory, resource);
                } else {
                    chart = '<div class="chart-placeholder">Not enough historical data</div>';
                }

                const urlResource = resource === 'credit' ? 'credits' : resource;
                const buyUrl = `https://politicsandwar.com/index.php?id=26&display=world&resource1=${urlResource}&buysell=buy&ob=price&od=DEF&maximum=50&minimum=0&search=Go`;
                const sellUrl = `https://politicsandwar.com/index.php?id=90&display=world&resource1=${urlResource}&buysell=sell&ob=price&od=DEF&maximum=50&minimum=0&search=Go`;

                const isCredit = resource === 'credit';
                const buyDisplay  = isCredit ? fmtPrice(priceData.buy)  : priceData.buy.toFixed(0);
                const sellDisplay = isCredit ? fmtPrice(priceData.sell) : priceData.sell.toFixed(0);
                const marginDisplay = isCredit
                    ? (margin < 0 ? '-' : '') + fmtPrice(Math.abs(margin))
                    : margin.toFixed(0);

                // For credits: overlay full prices on the chart
                const chartPriceOverlay = isCredit ? `
                    <div style="position:absolute;top:4px;right:6px;font-size:0.68rem;font-weight:700;color:#f44336;background:rgba(0,0,0,0.55);padding:1px 4px;border-radius:3px;pointer-events:none">
                        ${priceData.sell.toLocaleString(undefined,{maximumFractionDigits:0})}
                    </div>
                    <div style="position:absolute;bottom:4px;right:6px;font-size:0.68rem;font-weight:700;color:#4caf50;background:rgba(0,0,0,0.55);padding:1px 4px;border-radius:3px;pointer-events:none">
                        ${priceData.buy.toLocaleString(undefined,{maximumFractionDigits:0})}
                    </div>` : '';

                html += `
                    <div class="resource-card ${trendClass}">
                        <div class="rc-header">
                            <img src="${resourceEmojis[resource]}" class="rc-icon">
                            <div style="display:flex;flex-direction:row;align-items:center;justify-content:flex-end;width:100%;">
                                <div style="display:flex;align-items:center;gap:8px;">
                                    <span style="font-size:1.3rem;font-weight:700;color:#fff;">${price.toLocaleString(undefined,{minimumFractionDigits:0,maximumFractionDigits:0})}</span>
                                    ${hasComparison ? `
                                    <span class="rc-price-change ${trendClass}" style="font-size:0.9rem;padding:2px 6px;">
                                        ${valueChange >= 0 ? '▲' : '▼'} ${Math.abs(valueChange).toFixed(0)} (${percentChange.toFixed(2)}%)
                                    </span>
                                    ` : ''}
                                </div>
                            </div>
                        </div>
                        <div class="rc-body">
                            <div class="rc-chart-container" style="position:relative" data-resource="${resource}">
                                ${chart}
                                ${chartPriceOverlay}
                            </div>
                        </div>
                        <div class="rc-footer">
                            <button class="rc-bell-btn" data-resource="${resource}" title="Set price alert">&#x1F514;</button>
                            <div class="rc-footer-stats">
                                <div class="rc-footer-item">
                                    <a href="${buyUrl}" target="_blank" rel="noopener noreferrer" class="rc-trade-btn rc-buy-btn">${buyDisplay}</a>
                                </div>
                                <div class="rc-footer-item">
                                    <a href="${sellUrl}" target="_blank" rel="noopener noreferrer" class="rc-trade-btn rc-sell-btn">${sellDisplay}</a>
                                </div>
                                <div class="rc-footer-item">
                                    <span class="rc-label">Margin</span>
                                    <span class="rc-value ${marginClass}">${marginDisplay}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                `
            }
            html += '</div>';
            marketContainer.innerHTML = html;

            // Wire up bell buttons — after DOM is set
            marketContainer.querySelectorAll('.rc-bell-btn').forEach(btn => {
                const res = btn.dataset.resource;
                const pd = prices[res];
                if (!pd) return;
                const hasAlert = Object.keys(_activeAlerts).some(k => k.startsWith(`${res}:`));
                if (hasAlert) btn.classList.add('active');
                btn.addEventListener('click', e => {
                    e.preventDefault();
                    e.stopPropagation();
                    openAlertModal(res, pd.buy, pd.sell);
                });
            });

            // Wire up chart zoom — click on chart area fetches full history on demand
            marketContainer.querySelectorAll('.rc-chart-container[data-resource]').forEach(container => {
                const res = container.dataset.resource;
                container.addEventListener('click', e => {
                    e.preventDefault();
                    e.stopPropagation();
                    openChartModal(res, resourceEmojis[res]);
                });
            });
        })
        .catch(error => {
            console.error('Error fetching market prices:', error);
            const marketContainer = document.getElementById('market-prices');
            if (marketContainer) {
                marketContainer.innerHTML = '<div class="text-danger">Error loading market prices: ' + error.message + '</div>';
            }
        });

    // --- FETCH: Turn Bonuses ---
    console.log('Fetching turn bonuses...');
    fetch('/api/game-info/colors-comparison')
        .then(response => {
            console.log('Turn bonuses response status:', response.status);
            if (!response.ok) throw new Error('Failed to fetch color data');
            return response.json();
        })
        .then(data => {
            console.log('Turn bonuses data received');
            const tickerContainer = document.getElementById('bonuses-ticker-container');
            const contentContainer = document.getElementById('turn-bonuses-content');
            if (!tickerContainer || !contentContainer) return;

            const colorEmojis = {
                'white': '/static/Emojis/Colors/white.png', 'grey': '/static/Emojis/Colors/gray.png', 'gray': '/static/Emojis/Colors/gray.png',
                'black': '/static/Emojis/Colors/black.png', 'gold': '/static/Emojis/Colors/gold.png', 'pink': '/static/Emojis/Colors/pink.png',
                'brown': '/static/Emojis/Colors/brown.png', 'mint': '/static/Emojis/Colors/mint.png', 'green': '/static/Emojis/Colors/green.png',
                'aqua': '/static/Emojis/Colors/aqua.png', 'lavender': '/static/Emojis/Colors/lavender.png', 'lime': '/static/Emojis/Colors/lime.png',
                'maroon': '/static/Emojis/Colors/maroon.png', 'olive': '/static/Emojis/Colors/olive.png', 'yellow': '/static/Emojis/Colors/yellow.png',
                'turquoise': '/static/Emojis/Colors/turquoise.png', 'red': '/static/Emojis/Colors/red.png', 'purple': '/static/Emojis/Colors/purple.png',
                'orange': '/static/Emojis/Colors/orange.png', 'blue': '/static/Emojis/Colors/blue.png', 'beige': '/static/Emojis/Colors/beige.png'
            };

            const currentColors = data.current || {};
            const sortedColors = Object.entries(currentColors).sort(([,a], [,b]) => b.bonus - a.bonus);

            // Top 3 for the podium with enhanced styling
            let top3Html = '';
            const top3 = sortedColors.slice(0, 3);
            
            // Color mapping for box backgrounds
            const colorMap = {
                'white': '#f8f8f8',
                'grey': '#808080', 'gray': '#808080',
                'black': '#2c2c2c',
                'gold': '#ffd700',
                'pink': '#ff69b4',
                'brown': '#8b4513',
                'mint': '#98fb98',
                'green': '#228b22',
                'aqua': '#00ced1',
                'lavender': '#9370db',
                'lime': '#32cd32',
                'maroon': '#800000',
                'olive': '#808000',
                'yellow': '#ffd700',
                'turquoise': '#40e0d0',
                'red': '#dc143c',
                'purple': '#8a2be2',
                'orange': '#ff8c00',
                'blue': '#1e90ff',
                'beige': '#f5deb3'
            };
            
            top3.forEach(([color, data], index) => {
                const rank = index + 1;
                const emoji = colorEmojis[color.toLowerCase()] || '/static/Emojis/Colors/gold.png';
                
                // Try multiple ways to get the bloc name
                let blocName = 'Unknown';
                if (data.bloc) {
                    blocName = data.bloc;
                } else if (data.name) {
                    blocName = data.name;
                } else if (data.alliance) {
                    blocName = data.alliance;
                } else {
                    blocName = color.charAt(0).toUpperCase() + color.slice(1) + ' Color';
                }
                
                const bonus = data.bonus.toLocaleString();
                const boxColor = colorMap[color.toLowerCase()] || color.toLowerCase();
                
                // Debug logging (minimal)
                console.log(`Rank ${rank}: ${blocName} (+${bonus})`);

                top3Html += `
                    <div class="leaderboard-player rank-${rank}" style="background: linear-gradient(145deg, ${boxColor}, ${boxColor}dd) !important; border: 2px solid ${boxColor};">
                        ${rank === 1 ? '<div class="crown-container">👑</div>' : ''}
                        <img src="${emoji}" class="lb-icon" style="border-color: rgba(255,255,255,0.3);">
                        <div class="nameplate">
                            <div class="nameplate-name">${blocName}</div>
                            <div class="nameplate-bonus">+${bonus}</div>
                        </div>
                    </div>
                `;
            });

            // Ranks 4-10 for the main list with enhanced styling
            let listHtml = '';
            const listRanks = sortedColors.slice(3, 10);
            listRanks.forEach(([color, data], index) => {
                const rank = index + 4;
                const emoji = colorEmojis[color.toLowerCase()] || '/static/Emojis/Colors/gold.png';
                const blocName = data.bloc || 'Unknown';
                const bonus = data.bonus.toLocaleString();
                
                // Calculate bonus difference from #1 for context
                const bonusDiff = sortedColors[0][1].bonus - data.bonus;
                const diffText = bonusDiff > 0 ? `(-${bonusDiff.toLocaleString()})` : '';

                listHtml += `
                    <div class="leaderboard-item" style="border-left: 3px solid ${color.toLowerCase()};">
                        <div class="lb-list-rank">#${rank}</div>
                        <img src="${emoji}" class="lb-list-icon" title="${color.toUpperCase()} Color">
                        <div class="lb-list-name" title="${blocName}">${blocName}</div>
                        <div class="lb-list-bonus">
                            +${bonus}
                            <div style="font-size: 0.75rem; color: #888; margin-top: 2px;">${diffText}</div>
                        </div>
                    </div>
                `;
            });

            // Enhanced ticker for ranks 11+ with better styling
            let tickerHtml = '';
            const tickerRanks = sortedColors.slice(10);
            tickerRanks.forEach(([color, data], index) => {
                const rank = index + 11;
                const emoji = colorEmojis[color.toLowerCase()] || '/static/Emojis/Colors/gold.png';
                const blocName = data.bloc || 'Unknown';
                const bonus = data.bonus.toLocaleString();

                tickerHtml += `
                    <div class="lb-ticker-item" style="border-left: 2px solid ${color.toLowerCase()};">
                        <span class="lb-ticker-rank">#${rank}</span>
                        <img src="${emoji}" class="lb-ticker-icon" title="${color.toUpperCase()} Color">
                        <span class="lb-ticker-name">${blocName}</span>
                        <span class="lb-ticker-bonus">+${bonus}</span>
                    </div>
                `;
            });

            // Duplicate the ticker content for seamless scrolling
            if (tickerHtml) {
                tickerContainer.innerHTML = `<div class="leaderboard-ticker"><div class="lb-ticker-track">${tickerHtml}${tickerHtml}</div></div>`;
                
                // Immediate animation start
                const track = tickerContainer.querySelector('.lb-ticker-track');
                if (track) {
                    track.style.animation = 'ticker-scroll 120s linear infinite';
                }
            } else {
                tickerContainer.innerHTML = `<h4 class="mb-0 p-3" style="color: #ffd700; text-align: center; display: flex; align-items: center; justify-content: center;"><img src="/static/Emojis/Menu/graph.png" class="home-card-icon me-2" style="width: 28px; height: 28px;">Turn Bonuses</h4>`;
            }

            contentContainer.innerHTML = `
                <div id="turn-bonuses-container">
                    <div class="leaderboard-top-3">${top3Html}</div>
                    <div class="leaderboard-list">${listHtml}</div>
                </div>
            `;
        })
        .catch(error => {
            console.error('Error fetching turn bonuses:', error);
            const bonusesContainer = document.getElementById('turn-bonuses');
            if (bonusesContainer) {
                bonusesContainer.innerHTML = '<div class="text-danger">Error loading turn bonuses.</div>';
            }
        });
}

// Simplified and efficient initialization
let gameInfoInitialized = false;

function initializeGameInfoOnce() {
    const marketContainer = document.getElementById('market-prices');
    const bonusesContainer = document.getElementById('turn-bonuses-content');
    
    if (marketContainer || bonusesContainer) {
        console.log('Initializing Game Info');
        gameInfoInitialized = true;
        initializeGameInfo();
    }
}

// Primary: dashboard navigation — always re-initialize on each visit
document.addEventListener('dashboardPageLoaded', function(e) {
    if (e.detail.page === 'game_info.html') {
        console.log('Dashboard page loaded: game_info.html');
        gameInfoInitialized = false;  // reset so re-navigation always re-fetches
        initializeGameInfoOnce();
    }
});

// Fallback: direct page load (no dashboard wrapper)
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeGameInfoOnce);
} else {
    initializeGameInfoOnce();
}

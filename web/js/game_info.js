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

// Function to switch between info sections
function switchInfoSection(infoType) {
    console.log('Switching to section:', infoType);
    const infoButtons = document.querySelectorAll('.graph-emoji-button');
    const contentSections = document.querySelectorAll('.info-content-section');
    
    console.log('Found buttons for switching:', infoButtons.length);
    console.log('Found sections for switching:', contentSections.length);
    
    // Update button active states
    infoButtons.forEach(btn => btn.classList.remove('active'));
    const activeButton = document.querySelector(`[data-info-type="${infoType}"]`);
    if (activeButton) {
        activeButton.classList.add('active');
        console.log('Activated button:', infoType);
    } else {
        console.log('Button not found for:', infoType);
    }
    
    // Show/hide content sections
    contentSections.forEach(section => {
        section.classList.remove('active');
        if (section.id === infoType + '-section') {
            section.classList.add('active');
            console.log('Activated section:', section.id);
        }
    });
}

// Advanced Chart Generator
function generateAdvancedChart(data, resourceName) {
    if (!data || data.length < 2) return '<div class="chart-placeholder">Not enough historical data</div>';

    const width = 400;
    const height = 120;
    const padding = { top: 20, right: 20, bottom: 30, left: 40 };
    const drawableHeight = height - padding.top - padding.bottom;

    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = (max - min) || 1;

    // Calculate Y position of the zero axis
    const yZero = height - padding.bottom - ((0 - min) / range) * drawableHeight;

    const points = data.map((val, i) => {
        const x = padding.left + (i / (data.length - 1)) * (width - padding.left - padding.right);
        const y = height - padding.bottom - ((val - min) / range) * drawableHeight;
        const color = i > 0 ? (data[i] > data[i-1] ? '#4caf50' : '#f44336') : '#9e9e9e';
        return { x, y, val, color };
    });

    let paths = '';
    let gradients = '';

    for (let i = 1; i < points.length; i++) {
        const p1 = points[i-1];
        const p2 = points[i];
        const segmentColor = p2.color;
        const gradientId = `gradient-${resourceName}-${i}`;

        gradients += `
            <linearGradient id="${gradientId}" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="${segmentColor}" stop-opacity="0.4"/>
                <stop offset="100%" stop-color="${segmentColor}" stop-opacity="0.05"/>
            </linearGradient>
        `;

        const areaPath = `M ${p1.x} ${p1.y} L ${p2.x} ${p2.y} L ${p2.x} ${yZero} L ${p1.x} ${yZero} Z`;
        const linePath = `M ${p1.x} ${p1.y} L ${p2.x} ${p2.y}`;

        paths += `
            <path d="${areaPath}" fill="url(#${gradientId})" />
            <path d="${linePath}" stroke="${segmentColor}" stroke-width="2.5" stroke-linecap="round" />
        `;
    }

    const lastPoint = points[points.length - 1];

    return `
        <svg class="advanced-chart" viewBox="0 0 ${width} ${height}">
            <defs>${gradients}</defs>
            <line x1="${padding.left}" y1="${yZero}" x2="${width - padding.right}" y2="${yZero}" stroke="#555" stroke-width="1" stroke-dasharray="4" />
            ${paths}
            <circle cx="${lastPoint.x}" cy="${lastPoint.y}" r="5" fill="${lastPoint.color}" stroke="rgba(10,10,10,0.8)" stroke-width="2" />
        </svg>
    `;
}

// Main execution function to run when the page is ready
function initializeGameInfo() {
    console.log('Initializing Game Info page...');
    
    const marketContainer = document.getElementById('market-prices');
    if (!marketContainer) {
        console.log('Game Info containers not found, skipping initialization');
        return;
    }
    
    setupInfoSelection();

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

            if (tickerHtml) {
                tickerContainer.innerHTML = `<div class="resource-ticker"><div class="lb-ticker-track">${tickerHtml}${tickerHtml}</div></div>`;
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
                                <div class="rc-price-main" style="display: none;">
                                    <div class="rc-price-avg">No Data</div>
                                </div>
                                <div class="rc-chart-container">
                                    <div class="chart-placeholder">Awaiting data...</div>
                                </div>
                            </div>
                            <div class="rc-footer">
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
            const startPrice = fullHistory[0]; // Use the oldest price as the stable zero-point
            const displayHistory = fullHistory.slice(-144); // Get the last 1.5 days to display
            const relativeChanges = displayHistory.map(price => price - startPrice);
            chart = generateAdvancedChart(relativeChanges, resource);
        } else {
            chart = '<div class="chart-placeholder">Not enough historical data</div>';
        }

                const urlResource = resource === 'credit' ? 'credits' : resource;
                const resourceUrl = `https://politicsandwar.com/index.php?id=90&display=world&resource1=${urlResource}&buysell=sell&ob=price&od=DEF&maximum=50&minimum=0&search=Go`;

                html += `
                    <a href="${resourceUrl}" target="_blank" rel="noopener noreferrer" class="resource-card-link">
                        <div class="resource-card ${trendClass}">
                            <div class="rc-header" style="position: relative;">
                                <img src="${resourceEmojis[resource]}" class="rc-icon">
                                <div style="display: flex; flex-direction: row; align-items: center; justify-content: flex-end; width: 100%;">
                                    <div style="display: flex; align-items: center; gap: 8px;">
                                        <span style="font-size: 1.3rem; font-weight: 700; color: #fff;">$${price.toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0})}</span>
                                        ${hasComparison ? `
                                        <span class="rc-price-change ${trendClass}" style="font-size: 0.9rem; padding: 2px 6px;">
                                            ${valueChange >= 0 ? '▲' : '▼'} ${Math.abs(valueChange).toFixed(0)} (${percentChange.toFixed(2)}%)
                                        </span>
                                        ` : ''}
                                    </div>
                                </div>
                            </div>
                            <div class="rc-body">
                                <div class="rc-chart-container">
                                    ${chart}
                                </div>
                            </div>
                            <div class="rc-footer">
                                <div class="rc-footer-item">
                                    <span class="rc-label">Buy</span>
                                    <span class="rc-value">$${priceData.buy.toFixed(0)}</span>
                                </div>
                                <div class="rc-footer-item">
                                    <span class="rc-label">Sell</span>
                                    <span class="rc-value">$${priceData.sell.toFixed(0)}</span>
                                </div>
                                <div class="rc-footer-item">
                                    <span class="rc-label">Margin</span>
                                    <span class="rc-value ${marginClass}">$${margin.toFixed(0)}</span>
                                </div>
                            </div>
                        </div>
                    </a>
                `;
            }
            html += '</div>';
            marketContainer.innerHTML = html;
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
            console.log('Turn bonuses data received:', data);
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

            // Top 3 for the podium
            let top3Html = '';
            const top3 = sortedColors.slice(0, 3);
            top3.forEach(([color, data], index) => {
                const rank = index + 1;
                const emoji = colorEmojis[color.toLowerCase()] || '/static/Emojis/Colors/gold.png';
                const blocName = data.bloc || 'Unknown';
                const bonus = data.bonus.toLocaleString();

                top3Html += `
                    <div class="leaderboard-player rank-${rank}" style="border-left: 4px solid ${color.toLowerCase()};">
                        <div class="lb-rank">#${rank}</div>
                        <img src="${emoji}" class="lb-icon" style="border-color: ${color.toLowerCase()};">
                        <div class="lb-name">${blocName}</div>
                        <div class="lb-bonus">+${bonus}</div>
                    </div>
                `;
            });

            // Ranks 4-10 for the main list
            let listHtml = '';
            const listRanks = sortedColors.slice(3, 10);
            listRanks.forEach(([color, data], index) => {
                const rank = index + 4;
                const emoji = colorEmojis[color.toLowerCase()] || '/static/Emojis/Colors/gold.png';
                const blocName = data.bloc || 'Unknown';
                const bonus = data.bonus.toLocaleString();

                listHtml += `
                    <div class="leaderboard-item" style="border-left: 3px solid ${color.toLowerCase()};">
                        <div class="lb-list-rank">#${rank}</div>
                        <img src="${emoji}" class="lb-list-icon">
                        <div class="lb-list-name">${blocName}</div>
                        <div class="lb-list-bonus">+${bonus}</div>
                    </div>
                `;
            });

            // Ranks 11+ for the ticker
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
                        <img src="${emoji}" class="lb-ticker-icon">
                        <span class="lb-ticker-name">${blocName} (+${bonus})</span>
                    </div>
                `;
            });

            if (tickerHtml) {
                tickerContainer.innerHTML = `<div class="leaderboard-ticker"><div class="lb-ticker-track">${tickerHtml}${tickerHtml}</div></div>`;
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

// Initialize when dashboard page is loaded (this is how other pages work)
document.addEventListener('dashboardPageLoaded', function(e) {
    console.log('dashboardPageLoaded fired for:', e.detail.page);
    // Ensure we only run this for the game_info page
    if (e.detail.page === 'game_info.html') {
        console.log('Initializing game_info from dashboardPageLoaded');
        initializeGameInfo();
    }
});

// For SPA navigation, we need to wait for the dashboardPageLoaded event
// The script executes immediately when inserted, but the event comes later
let initializationAttempted = false;

function tryInitialization() {
    if (initializationAttempted) return;
    
    const marketContainer = document.getElementById('market-prices');
    const bonusesContainer = document.getElementById('turn-bonuses');
    
    if (marketContainer || bonusesContainer) {
        console.log('Containers found, running initialization');
        initializationAttempted = true;
        initializeGameInfo();
    } else {
        console.log('Containers not found, will wait for dashboardPageLoaded event');
    }
}

// Try immediate initialization
setTimeout(tryInitialization, 100);

// Also try after a longer delay as fallback
setTimeout(() => {
    if (!initializationAttempted) {
        console.log('Fallback initialization after 1 second');
        tryInitialization();
    }
}, 1000);

// Immediate initialization attempt (for debugging)
console.log('game_info.js loaded - document.readyState:', document.readyState);
console.log('game_info.js - checking for containers immediately:');
console.log('market-prices container:', !!document.getElementById('market-prices'));
console.log('turn-bonuses container:', !!document.getElementById('turn-bonuses'));

// Force initialization after 2 seconds as final fallback
setTimeout(() => {
    console.log('Force initialization after 2 seconds');
    const marketContainer = document.getElementById('market-prices');
    const bonusesContainer = document.getElementById('turn-bonuses');
    if (marketContainer || bonusesContainer) {
        console.log('Containers found in force initialization');
        initializeGameInfo();
    } else {
        console.log('Containers still not found after 2 seconds');
    }
}, 2000);

// Ultra simple fallback - just try to initialize if containers exist
(function() {
    const marketContainer = document.getElementById('market-prices');
    const bonusesContainer = document.getElementById('turn-bonuses');
    if (marketContainer || bonusesContainer) {
        console.log('Ultra-simple fallback: containers found, initializing');
        setTimeout(() => initializeGameInfo(), 50);
    }
})();
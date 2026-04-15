const calculatorToggle = document.getElementById('calculator-toggle');
        if (calculatorToggle && !calculatorToggle.hasAttribute('data-initialized')) {
            calculatorToggle.setAttribute('data-initialized', 'true');

        // Auto-fill nation ID from linked nation
        (function() {
            const input = document.getElementById('nation-query');
            if (!input || input.value.trim()) return;
            // Try localStorage first (works without Discord login)
            try {
                const stored = localStorage.getItem('pnw_linked_nation');
                if (stored) {
                    const nation = JSON.parse(stored);
                    if (nation && nation.nation_id) {
                        input.value = nation.nation_id;
                        return;
                    }
                }
            } catch (_) {}
            // Fall back to server session
            fetch('/api/discord/linked-nation')
                .then(r => r.ok ? r.json() : null)
                .then(data => {
                    if (data && data.linked && data.nation_id && !input.value.trim()) {
                        input.value = data.nation_id;
                    }
                })
                .catch(() => {});
        })();

        const buildingCalculator = document.getElementById('building-calculator');
        const militaryCalculator = document.getElementById('military-calculator');
        const calculateBtn = document.getElementById('calculate-btn');
        const resultsContainer = document.getElementById('results-container');
        const resultsBody = document.getElementById('results-body');

        calculatorToggle.addEventListener('change', () => {
            if (calculatorToggle.checked) {
                buildingCalculator.style.display = 'none';
                militaryCalculator.style.display = 'block';
                document.querySelector('label[for="calculator-toggle"]').textContent = 'Switch to Building Calculator';
            } else {
                buildingCalculator.style.display = 'block';
                militaryCalculator.style.display = 'none';
                document.querySelector('label[for="calculator-toggle"]').textContent = 'Switch to Military Calculator';
            }
        });

        calculateBtn.addEventListener('click', () => {
            resultsContainer.style.display = 'block';
            resultsBody.innerHTML = '<div class="text-center"><div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div></div>';
            
            if (calculatorToggle.checked) {
                calculateMilitaryCosts();
            } else {
                calculateBuildingCosts();
            }
        });

        const fmt = n => '$' + n.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
        const fmtNum = n => n.toLocaleString('en-US', {maximumFractionDigits: 0});

        function getResourceEmoji(resource) {
            const resourceIcons = {
                'food': '/static/Emojis/Resources/food.png',
                'coal': '/static/Emojis/Resources/coal.png',
                'oil': '/static/Emojis/Resources/oil.png',
                'uranium': '/static/Emojis/Resources/uranium.png',
                'lead': '/static/Emojis/Resources/lead.png',
                'iron': '/static/Emojis/Resources/iron.png',
                'bauxite': '/static/Emojis/Resources/bauxite.png',
                'gasoline': '/static/Emojis/Resources/gasoline.png',
                'munitions': '/static/Emojis/Resources/munitions.png',
                'steel': '/static/Emojis/Resources/steel.png',
                'aluminum': '/static/Emojis/Resources/aluminum.png',
                'credit': '/static/Emojis/Resources/credit.png'
            };
            const iconPath = resourceIcons[resource.toLowerCase()];
            return iconPath ? `<img src="${iconPath}" alt="${resource}" height="16" style="margin-right: 4px;">` : '';
        }

        function costRow(label, value) {
            return `<div class="d-flex justify-content-between align-items-center py-1 border-bottom border-secondary">
                        <span style="color: #c0c0c0;">${label}</span>
                        <span class="fw-bold text-warning">${value}</span>
                    </div>`;
        }
        function costSection(title, rows) {
            return `<div class="mb-3">
                        <h6 class="text-light border-bottom border-warning pb-1 mb-2">${title}</h6>
                        ${rows}
                    </div>`;
        }
        function savingsBadge(saved) {
            if (saved <= 0.01) return '';
            return ` <span class="badge bg-success ms-2">Saved ${fmt(saved)}</span>`;
        }
        function discountBadge(label) {
            return `<span class="badge bg-info text-dark ms-1" style="font-size:0.7rem">${label}</span>`;
        }

        async function calculateBuildingCosts() {
            const nationQuery = document.getElementById('nation-query').value.trim();
            const infraTarget = parseFloat(document.getElementById('infra-to-buy').value) || 0;
            const landTarget = parseFloat(document.getElementById('land-to-buy').value) || 0;
            const citiesToBuy = parseInt(document.getElementById('cities-to-buy').value) || 0;
            const projectsToBuy = [...selectedProjects];

            try {
                const [nationData, gameInfo, resourcePrices] = await Promise.all([
                    nationQuery ? fetch(`/api/pnw/nation-info/${nationQuery}`).then(r => r.json()) : Promise.resolve(null),
                    fetch('/api/pnw/game-info').then(r => r.json()),
                    fetch('/api/pnw/resource-prices').then(r => r.json())
                ]);

                if (nationQuery && nationData && nationData.error) {
                    resultsBody.innerHTML = `<p class="text-center text-danger">Error: ${nationData.error}</p>`;
                    return;
                }

                // Use best sell prices from reaper.db (what you pay to buy resources on the market)
                const sellPrices = {};
                let priceTs = null;
                if (resourcePrices && resourcePrices.data) {
                    for (const [resource, data] of Object.entries(resourcePrices.data)) {
                        sellPrices[resource.toLowerCase()] = data.sell || 0;
                    }
                    priceTs = resourcePrices.timestamp 
                        ? new Date(resourcePrices.timestamp * 1000).toLocaleString() 
                        : null;
                }

                let resultsHTML = '';
                let grandTotalProjectsOnly = 0;
                let grandTotalAllDiscounts = 0;

                // --- INFRA ---
                if (infraTarget > 0 && nationData && nationData.cities && nationData.cities.length > 0) {
                    const currentCities = nationData ? (nationData.num_cities || nationData.cities.length) : 0;
                    const totalCitiesAfterPurchase = currentCities + (citiesToBuy || 0);
                    let totalRaw = 0, totalBase = 0, totalFinal = 0;
                    let cityBreakdown = [];
                    
                    // Calculate for existing cities
                    nationData.cities.forEach((city, index) => {
                        const cur = city.infrastructure || 0;
                        const cityName = city.name || `City ${index + 1}`;
                        if (cur < infraTarget) {
                            const rawCost = calc_infra_value(cur, infraTarget);
                            const res = infra_purchase_cost(cur, infraTarget - cur, nationData);
                            totalRaw += rawCost;
                            totalBase += res.base_cost;
                            totalFinal += res.final_cost;
                            
                            cityBreakdown.push({
                                name: cityName,
                                current: cur,
                                target: infraTarget,
                                amount: infraTarget - cur,
                                rawCost: rawCost,
                                baseCost: res.base_cost,
                                finalCost: res.final_cost,
                                isNew: false
                            });
                        } else {
                            cityBreakdown.push({
                                name: cityName,
                                current: cur,
                                target: infraTarget,
                                amount: 0,
                                rawCost: 0,
                                baseCost: 0,
                                finalCost: 0,
                                isNew: false
                            });
                        }
                    });
                    
                    // Calculate for new cities (if any) - they start with 0 infrastructure
                    if (citiesToBuy > 0) {
                        for (let i = 0; i < citiesToBuy; i++) {
                            const rawCost = calc_infra_value(0, infraTarget);
                            const res = infra_purchase_cost(0, infraTarget, nationData);
                            totalRaw += rawCost;
                            totalBase += res.base_cost;
                            totalFinal += res.final_cost;
                            
                            cityBreakdown.push({
                                name: `New City ${i + 1}`,
                                current: 0,
                                target: infraTarget,
                                amount: infraTarget,
                                rawCost: rawCost,
                                baseCost: res.base_cost,
                                finalCost: res.final_cost,
                                isNew: true
                            });
                        }
                    }
                    
                    const avgCur = nationData.cities.reduce((a, c) => a + (c.infrastructure || 0), 0) / nationData.cities.length;
                    const saved = totalRaw - totalFinal;
                    const discounts = calculate_project_discounts(nationData);
                    const projReduction = discounts.infra_cost_reduction;
                    const policyReduction = 0.05 * discounts.domestic_policy_multiplier;

                    let projectDiscountLabels = '';
                    let policyDiscountLabels = '';
                    if (projReduction > 0) projectDiscountLabels += discountBadge(`Project -${(projReduction*100).toFixed(0)}%`);
                    if (policyReduction > 0) policyDiscountLabels += discountBadge(`Urbanization -${(policyReduction*100).toFixed(1)}%`);

                    let rows = costRow(`Target: ${fmtNum(infraTarget)} (from ${fmtNum(Math.round(avgCur))} avg, ${totalCitiesAfterPurchase} cities total)`, '');
                    rows += costRow('Raw Cost', fmt(totalRaw));
                    if (projReduction > 0) rows += costRow(`After Project Discounts ${projectDiscountLabels}`, fmt(totalBase));
                    rows += `<div class="d-flex justify-content-between align-items-center py-1 border-bottom border-secondary">
                                <span style="color: #c0c0c0;">Final Cost (with Policy) ${policyDiscountLabels}</span>
                                <span class="fw-bold text-warning fs-6">${fmt(totalFinal)}${savingsBadge(saved)}</span>
                             </div>`;
                    
                    // Add collapsible per-city breakdown
                    const infraBreakdownId = 'infra-breakdown-' + Math.random().toString(36).substr(2, 9);
                    rows += `<div class="mt-2">
                                <button class="btn btn-sm btn-outline-secondary w-100 breakdown-toggle" type="button" data-bs-toggle="collapse" data-bs-target="#${infraBreakdownId}" aria-expanded="false">
                                    <i class="fas fa-chevron-down me-1"></i> Show Per-City Breakdown
                                </button>
                                <div class="collapse mt-2" id="${infraBreakdownId}">
                                    <div class="card card-body bg-dark border-secondary" style="font-size: 0.85em;">`;
                    
                    cityBreakdown.forEach(city => {
                        const cityClass = city.isNew ? 'breakdown-city-new' : '';
                        const cityStyle = city.isNew ? 'color: #28a745; font-weight: bold;' : '';
                        const amountText = city.amount > 0 ? `+${fmtNum(city.amount)}` : 'No change';
                        rows += `<div class="d-flex justify-content-between align-items-center py-1 border-bottom border-dark ${cityClass}" style="${cityStyle}">
                                    <div>
                                        <strong>${city.name}</strong>${city.isNew ? ' <small class="badge bg-success">NEW</small>' : ''}<br>
                                        <small class="text-muted">${fmtNum(city.current)} → ${fmtNum(city.target)} (${amountText})</small>
                                    </div>
                                    <div class="text-end">
                                        ${city.finalCost > 0 ? fmt(city.finalCost) : '<span class="text-muted">$0.00</span>'}
                                    </div>
                                 </div>`;
                    });
                    
                    rows += `</div></div></div>`;
                    
                    resultsHTML += costSection('<img src="/static/Emojis/Calc/infra.png" alt="Infrastructure" height="20"> Infrastructure', rows);
                    grandTotalProjectsOnly += totalBase;
                    grandTotalAllDiscounts += totalFinal;
                }

                // --- LAND ---
                if (landTarget > 0 && nationData && nationData.cities && nationData.cities.length > 0) {
                    const currentCities = nationData ? (nationData.num_cities || nationData.cities.length) : 0;
                    const totalCitiesAfterPurchase = currentCities + (citiesToBuy || 0);
                    let totalRaw = 0, totalBase = 0, totalFinal = 0;
                    let cityBreakdown = [];
                    
                    // Calculate for existing cities
                    nationData.cities.forEach((city, index) => {
                        const cur = city.land || 0;
                        const cityName = city.name || `City ${index + 1}`;
                        if (cur < landTarget) {
                            const rawCost = calc_land_value(cur, landTarget);
                            const res = land_purchase_cost(cur, landTarget - cur, nationData);
                            totalRaw += rawCost;
                            totalBase += res.base_cost;
                            totalFinal += res.final_cost;
                            
                            cityBreakdown.push({
                                name: cityName,
                                current: cur,
                                target: landTarget,
                                amount: landTarget - cur,
                                rawCost: rawCost,
                                baseCost: res.base_cost,
                                finalCost: res.final_cost,
                                isNew: false
                            });
                        } else {
                            cityBreakdown.push({
                                name: cityName,
                                current: cur,
                                target: landTarget,
                                amount: 0,
                                rawCost: 0,
                                baseCost: 0,
                                finalCost: 0,
                                isNew: false
                            });
                        }
                    });
                    
                    // Calculate for new cities (if any) - they start with 0 land
                    if (citiesToBuy > 0) {
                        for (let i = 0; i < citiesToBuy; i++) {
                            const rawCost = calc_land_value(0, landTarget);
                            const res = land_purchase_cost(0, landTarget, nationData);
                            totalRaw += rawCost;
                            totalBase += res.base_cost;
                            totalFinal += res.final_cost;
                            
                            cityBreakdown.push({
                                name: `New City ${i + 1}`,
                                current: 0,
                                target: landTarget,
                                amount: landTarget,
                                rawCost: rawCost,
                                baseCost: res.base_cost,
                                finalCost: res.final_cost,
                                isNew: true
                            });
                        }
                    }
                    
                    const avgCur = nationData.cities.reduce((a, c) => a + (c.land || 0), 0) / nationData.cities.length;
                    const saved = totalRaw - totalFinal;
                    const discounts = calculate_project_discounts(nationData);
                    const projReduction = discounts.land_cost_reduction;
                    const policyReduction = 0.05 * discounts.domestic_policy_multiplier;

                    let projectDiscountLabels = '';
                    let policyDiscountLabels = '';
                    if (projReduction > 0) projectDiscountLabels += discountBadge(`Project -${(projReduction*100).toFixed(0)}%`);
                    if (policyReduction > 0) policyDiscountLabels += discountBadge(`Rapid Expansion -${(policyReduction*100).toFixed(1)}%`);

                    let rows = costRow(`Target: ${fmtNum(landTarget)} (from ${fmtNum(Math.round(avgCur))} avg, ${totalCitiesAfterPurchase} cities total)`, '');
                    rows += costRow('Raw Cost', fmt(totalRaw));
                    if (projReduction > 0) rows += costRow(`After Project Discounts ${projectDiscountLabels}`, fmt(totalBase));
                    rows += `<div class="d-flex justify-content-between align-items-center py-1 border-bottom border-secondary">
                                <span style="color: #c0c0c0;">Final Cost (with Policy) ${policyDiscountLabels}</span>
                                <span class="fw-bold text-warning fs-6">${fmt(totalFinal)}${savingsBadge(saved)}</span>
                             </div>`;
                    
                    // Add collapsible per-city breakdown
                    const landBreakdownId = 'land-breakdown-' + Math.random().toString(36).substr(2, 9);
                    rows += `<div class="mt-2">
                                <button class="btn btn-sm btn-outline-secondary w-100 breakdown-toggle" type="button" data-bs-toggle="collapse" data-bs-target="#${landBreakdownId}" aria-expanded="false">
                                    <i class="fas fa-chevron-down me-1"></i> Show Per-City Breakdown
                                </button>
                                <div class="collapse mt-2" id="${landBreakdownId}">
                                    <div class="card card-body bg-dark border-secondary" style="font-size: 0.85em;">`;
                    
                    cityBreakdown.forEach(city => {
                        const cityClass = city.isNew ? 'breakdown-city-new' : '';
                        const cityStyle = city.isNew ? 'color: #28a745; font-weight: bold;' : '';
                        const amountText = city.amount > 0 ? `+${fmtNum(city.amount)}` : 'No change';
                        rows += `<div class="d-flex justify-content-between align-items-center py-1 border-bottom border-dark ${cityClass}" style="${cityStyle}">
                                    <div>
                                        <strong>${city.name}</strong>${city.isNew ? ' <small class="badge bg-success">NEW</small>' : ''}<br>
                                        <small class="text-muted">${fmtNum(city.current)} → ${fmtNum(city.target)} (${amountText})</small>
                                    </div>
                                    <div class="text-end">
                                        ${city.finalCost > 0 ? fmt(city.finalCost) : '<span class="text-muted">$0.00</span>'}
                                    </div>
                                 </div>`;
                    });
                    
                    rows += `</div></div></div>`;
                    
                    resultsHTML += costSection('<img src="/static/Emojis/Calc/land.png" alt="Land" height="20"> Land', rows);
                    grandTotalProjectsOnly += totalBase;
                    grandTotalAllDiscounts += totalFinal;
                }

                // --- CITIES ---
                if (citiesToBuy > 0 && gameInfo) {
                    const currentCities = nationData ? (nationData.num_cities || 0) : 0;
                    const top20avg = gameInfo.city_average || 40;
                    let totalBase = 0, totalFinal = 0, totalRaw = 0;
                    for (let i = 0; i < citiesToBuy; i++) {
                        const cityNum = currentCities + i + 1;
                        const res = city_purchase_cost(cityNum, top20avg, nationData || {});
                        const rawRes = city_purchase_cost(cityNum, top20avg, {});
                        totalBase += res.base_cost;
                        totalFinal += res.final_cost;
                        totalRaw += rawRes.base_cost;
                    }
                    const saved = totalRaw - totalFinal;
                    const discounts = calculate_project_discounts(nationData || {});
                    const policyReduction = 0.05 * discounts.domestic_policy_multiplier;

                    let policyDiscountLabels = '';
                    if (policyReduction > 0) policyDiscountLabels += discountBadge(`Manifest Destiny -${(policyReduction*100).toFixed(1)}%`);

                    let rows = costRow(`Buying ${citiesToBuy} cit${citiesToBuy > 1 ? 'ies' : 'y'} (City ${currentCities+1}${citiesToBuy > 1 ? '�'+(currentCities+citiesToBuy) : ''})`, '');
                    rows += costRow('Raw Cost', fmt(totalRaw));
                    rows += `<div class="d-flex justify-content-between align-items-center py-1 border-bottom border-secondary">
                                <span style="color: #c0c0c0;">Final Cost (with Policy) ${policyDiscountLabels}</span>
                                <span class="fw-bold text-warning fs-6">${fmt(totalFinal)}${savingsBadge(saved)}</span>
                             </div>`;
                    resultsHTML += costSection('<img src="/static/Emojis/Calc/city.png" alt="Cities" height="20"> Cities', rows);
                    grandTotalProjectsOnly += totalBase;
                    grandTotalAllDiscounts += totalFinal;
                }

                // --- PROJECTS ---
                if (projectsToBuy.length > 0) {
                    const discounts = calculate_project_discounts(nationData || {});
                    const policyMultiplier = discounts.domestic_policy_multiplier;
                    const discountRate = 0.05 * policyMultiplier;
                    let projectRows = '';
                    let projTotalMoney = 0, projTotalMoneyFinal = 0;
                    let projTotalResValue = 0, projTotalResValueDiscounted = 0;

                    // Check for missing requirements and add them
                    const allProjectsNeeded = new Set(projectsToBuy);
                    const missingRequirements = new Set();
                    
                    projectsToBuy.forEach(projectName => {
                        const reqCheck = checkProjectRequirements(projectName, nationData || {});
                        if (!reqCheck.hasAll) {
                            reqCheck.missing.forEach(req => {
                                if (!allProjectsNeeded.has(req)) {
                                    missingRequirements.add(req);
                                    allProjectsNeeded.add(req);
                                }
                            });
                        }
                    });

                    // Display warning if there are missing requirements
                    if (missingRequirements.size > 0) {
                        const missingList = Array.from(missingRequirements).join(', ');
                        projectRows += `<div class="alert alert-warning mb-3" style="background: rgba(255, 193, 7, 0.1); border: 1px solid rgba(255, 193, 7, 0.3); border-radius: 0.5rem; padding: 0.75rem;">
                            <div class="fw-bold" style="color: #ffc107; margin-bottom: 0.5rem;">⚠️ Missing Required Projects</div>
                            <div style="color: #c0c0c0; font-size: 0.9rem;">
                                The following projects are required but not yet built: <strong style="color: #ffc107;">${missingList}</strong>
                                <br>Costs for these required projects are included below.
                            </div>
                        </div>`;
                    }

                    // Calculate costs for all projects (selected + required)
                    Array.from(allProjectsNeeded).forEach(projectName => {
                        const cost = project_build_cost(projectName, nationData || {});
                        if (!cost) return;

                        const baseMoney = cost.base_costs.money || 0;
                        const finalMoney = cost.final_costs.money || 0;
                        const moneySaved = baseMoney - finalMoney;

                        let baseResValue = 0;
                        let resLines = '';
                        for (const res in cost.base_costs) {
                            if (res === 'money') continue;
                            const amount = cost.base_costs[res];
                            const price = sellPrices[res.toLowerCase()] || 0;
                            const discountedAmount = amount * (1 - discountRate);
                            const val = price * amount;
                            const discountedVal = price * discountedAmount;
                            baseResValue += val;
                            resLines += `<div class="d-flex justify-content-between ps-3 py-1" style="font-size:0.85rem; color: #c0c0c0;">
                                            <span>${getResourceEmoji(res)}${res.charAt(0).toUpperCase()+res.slice(1)}: ${discountRate > 0.001 ? 
                                                fmtNum(amount) + ' → ' + fmtNum(discountedAmount) : 
                                                fmtNum(amount)
                                            }</span>
                                            <span>${price > 0 ? 
                                                (discountRate > 0.001 ? 
                                                    fmt(val) + ' → ' + fmt(discountedVal) + ' @ ' + fmt(price) + '/u' : 
                                                    fmt(val) + ' @ ' + fmt(price) + '/u'
                                                ) : 
                                                (discountRate > 0.001 ? 
                                                    fmtNum(amount) + ' → ' + fmtNum(discountedAmount) + ' (no price data)' :
                                                    fmtNum(amount) + ' (no price data)'
                                                )
                                            }</span>
                                         </div>`;
                        }
                        const finalResValue = baseResValue * (1 - discountRate);
                        const totalBase = baseMoney + baseResValue;
                        const totalFinal = finalMoney + finalResValue;
                        projTotalMoney += baseMoney;
                        projTotalMoneyFinal += finalMoney;
                        projTotalResValue += baseResValue;
                        projTotalResValueDiscounted += finalResValue;

                        let moneyLine = `<div class="d-flex justify-content-between ps-3 py-1" style="font-size:0.85rem; color: #c0c0c0;">
                                            <span>Money${discountRate > 0.001 ? ' ' + discountBadge('Tech Advancement -'+(discountRate*100).toFixed(1)+'%') : ''}</span>
                                            <span class="text-warning">${fmt(baseMoney)}${moneySaved > 0.01 ? ' → ' + fmt(finalMoney) + savingsBadge(moneySaved) : ''}</span>
                                         </div>`;

                        const isRequired = missingRequirements.has(projectName);
                        const isSelected = projectsToBuy.includes(projectName);
                        
                        let projectTitle = projectName;
                        if (isRequired && !isSelected) {
                            projectTitle += ' <span class="badge bg-warning text-dark ms-2" style="font-size: 0.7rem;">REQUIRED</span>';
                        }

                        projectRows += `<div class="mb-2 p-2 rounded" style="background:rgba(255,215,0,0.04);border:1px solid rgba(255,215,0,0.15)">
                            <div class="fw-semibold text-light mb-1">${projectTitle}</div>
                            ${moneyLine}
                            ${resLines}
                            <div class="d-flex justify-content-between ps-3 pt-1 border-top border-secondary mt-1">
                                <span style="font-size:0.85rem; color: #c0c0c0;">Total Est. Value (money + resources)</span>
                                <span class="fw-bold text-warning" style="font-size:0.85rem">${fmt(totalBase)}${Math.abs(totalBase-totalFinal) > 0.01 ? ' → ' + fmt(totalFinal) + savingsBadge(totalBase-totalFinal) : ''}</span>
                            </div>
                        </div>`;
                    });

                    const projGrandBase = projTotalMoney + projTotalResValue;
                    const projGrandFinal = projTotalMoneyFinal + projTotalResValueDiscounted;
                    grandTotalProjectsOnly += projGrandBase;
                    grandTotalAllDiscounts += projGrandFinal;

                    let summaryRow = projectsToBuy.length > 1
                        ? `<div class="d-flex justify-content-between py-1 border-top border-warning mt-2">
                               <span class="fw-semibold" style="color: #c0c0c0;">All Projects Total</span>
                               <span class="fw-bold text-warning">${fmt(projGrandBase)}${Math.abs(projGrandBase-projGrandFinal)>0.01?' → '+fmt(projGrandFinal)+savingsBadge(projGrandBase-projGrandFinal):''}</span>
                           </div>` : '';

                    resultsHTML += costSection('<img src="/static/Emojis/Calc/project.png" alt="Projects" height="20"> Projects', projectRows + summaryRow);
                }

                // --- GRAND TOTALS ---
                if (grandTotalProjectsOnly > 0 || grandTotalAllDiscounts > 0) {
                    let rows = costRow('Total Estimated Money Cost (Project Discounts Only)', fmt(grandTotalProjectsOnly));
                    rows += `<div class="d-flex justify-content-between align-items-center py-1">
                                <span class="fw-semibold" style="color: #c0c0c0;">Total Estimated Money Cost (All Discounts Applied)</span>
                                <span class="fw-bold text-warning fs-5">${fmt(grandTotalAllDiscounts)}</span>
                             </div>`;
                    if (priceTs) rows += `<div class="text-end mt-1" style="font-size:0.75rem; color: #a0a0a0;">Market prices as of ${priceTs}</div>`;
                    resultsHTML += costSection('<img src="/static/Emojis/Calc/project.png" alt="Grand Total" height="20"> Grand Total', rows);
                }

                if (!resultsHTML) {
                    resultsHTML = '<p class="text-center text-secondary">No costs to calculate. Fill in at least one field.</p>';
                }

                resultsBody.innerHTML = resultsHTML;

            } catch (error) {
                resultsBody.innerHTML = `<p class="text-center text-danger">Error calculating costs: ${error.message}</p>`;
                console.error(error);
            }
        }
        async function calculateMilitaryCosts() {
            const soldiers = parseInt(document.getElementById('soldiers').value) || 0;
            const tanks    = parseInt(document.getElementById('tanks').value)    || 0;
            const aircraft = parseInt(document.getElementById('aircraft').value) || 0;
            const ships    = parseInt(document.getElementById('ships').value)    || 0;
            const missiles = parseInt(document.getElementById('missiles').value) || 0;
            const nukes    = parseInt(document.getElementById('nukes').value)    || 0;

            const units = { soldiers, tanks, aircraft, ships, missiles, nukes };

            // Unit display metadata
            const UNIT_META = {
                soldiers: { label: 'Soldiers',  img: '/static/Emojis/Military/soldier.png' },
                tanks:    { label: 'Tanks',     img: '/static/Emojis/Military/tank.png'    },
                aircraft: { label: 'Aircraft',  img: '/static/Emojis/Military/jet.png'     },
                ships:    { label: 'Ships',     img: '/static/Emojis/Military/ship.png'    },
                missiles: { label: 'Missiles',  img: '/static/Emojis/Military/missile.png' },
                nukes:    { label: 'Nukes',     img: '/static/Emojis/Military/bomb.png'    },
            };

            // Per-unit costs (cash + resources)
            const UNIT_COSTS = {
                soldiers: { cash: 5 },
                tanks:    { cash: 60,      steel: 0.5 },
                aircraft: { cash: 4000,    aluminum: 10 },
                ships:    { cash: 50000,   steel: 30 },
                missiles: { cash: 150000,  gasoline: 100, munitions: 100, aluminum: 150 },
                nukes:    { cash: 1750000, uranium: 500,  gasoline: 500,  aluminum: 1000 },
            };

            const RESOURCE_IMG = {
                cash:      null,
                steel:     '/static/Emojis/Resources/steel.png',
                aluminum:  '/static/Emojis/Resources/aluminum.png',
                gasoline:  '/static/Emojis/Resources/gasoline.png',
                munitions: '/static/Emojis/Resources/munitions.png',
                uranium:   '/static/Emojis/Resources/uranium.png',
            };

            const rImg = (r) => RESOURCE_IMG[r]
                ? `<img src="${RESOURCE_IMG[r]}" alt="${r}" height="16" style="vertical-align:middle;margin-right:3px;">`
                : '💵 ';

            const uImg = (u) => `<img src="${UNIT_META[u].img}" alt="${UNIT_META[u].label}" height="22" style="vertical-align:middle;margin-right:5px;">`;

            try {
                const resourcePrices = await fetch('/api/pnw/resource-prices').then(r => r.json());

                const getPrice = (res) => (resourcePrices?.data?.[res]?.sell) || 0;

                // Accumulators
                let grandCash = 0;
                const grandResources = {}; // { resource: qty }

                // ── Per-unit breakdown cards ──────────────────────────────────
                let unitCardsHTML = '';
                for (const [unit, qty] of Object.entries(units)) {
                    if (qty <= 0) continue;
                    const costs = UNIT_COSTS[unit];
                    const meta  = UNIT_META[unit];
                    const unitCash = costs.cash * qty;
                    grandCash += unitCash;

                    // Build resource rows for this unit
                    let resRows = '';
                    let unitResourceValue = 0;
                    for (const [res, perUnit] of Object.entries(costs)) {
                        if (res === 'cash') continue;
                        const totalQty = perUnit * qty;
                        const mktVal   = getPrice(res) * totalQty;
                        unitResourceValue += mktVal;
                        grandResources[res] = (grandResources[res] || 0) + totalQty;
                        // Format perUnit with decimals if needed, otherwise as integer
                        const perUnitStr = perUnit % 1 === 0 ? fmtNum(perUnit) : perUnit.toLocaleString('en-US', {minimumFractionDigits: 1, maximumFractionDigits: 2});
                        resRows += `
                            <div class="d-flex justify-content-between align-items-center py-1 border-bottom border-secondary" style="font-size:0.88rem;">
                                <span style="color:#c0c0c0;">${rImg(res)}<span style="text-transform:capitalize;">${res}</span>
                                    <small class="text-muted ms-1">(${perUnitStr} × ${fmtNum(qty)})</small>
                                </span>
                                <span>
                                    <span class="fw-bold" style="color:#e0e0e0;">${fmtNum(totalQty)}</span>
                                    <small class="text-muted ms-2">≈ ${fmt(mktVal)}</small>
                                </span>
                            </div>`;
                    }

                    const unitTotal = unitCash + unitResourceValue;
                    unitCardsHTML += `
                        <div class="mb-3 p-3 rounded" style="background:rgba(255,215,0,0.04);border:1px solid rgba(255,215,0,0.18);">
                            <div class="d-flex justify-content-between align-items-center mb-2">
                                <h6 class="mb-0" style="color:#ffd700;">${uImg(unit)}${meta.label}
                                    <span class="badge ms-2" style="background:rgba(255,215,0,0.2);color:#ffd700;font-size:0.8rem;">× ${fmtNum(qty)}</span>
                                </h6>
                                <span class="fw-bold" style="color:#ffd700;font-size:0.95rem;">${fmt(unitTotal)}</span>
                            </div>
                            <div class="d-flex justify-content-between align-items-center py-1 border-bottom border-secondary" style="font-size:0.88rem;">
                                <span style="color:#c0c0c0;">💵 Cash
                                    <small class="text-muted ms-1">(${fmt(costs.cash)} × ${fmtNum(qty)})</small>
                                </span>
                                <span class="fw-bold text-warning">${fmt(unitCash)}</span>
                            </div>
                            ${resRows}
                        </div>`;
                }

                if (!unitCardsHTML) {
                    resultsBody.innerHTML = `<p class="text-center text-muted">Enter at least one unit quantity above.</p>`;
                    return;
                }

                // ── Resource totals table ─────────────────────────────────────
                let grandResourceValue = 0;
                let resourceTotalsHTML = '';
                for (const [res, qty] of Object.entries(grandResources)) {
                    const mktVal = getPrice(res) * qty;
                    grandResourceValue += mktVal;
                    resourceTotalsHTML += `
                        <div class="d-flex justify-content-between align-items-center py-1 border-bottom border-secondary">
                            <span style="color:#c0c0c0;">${rImg(res)}<span style="text-transform:capitalize;">${res}</span></span>
                            <span>
                                <span class="fw-bold" style="color:#e0e0e0;">${fmtNum(qty)}</span>
                                <small class="text-muted ms-2">≈ ${fmt(mktVal)}</small>
                            </span>
                        </div>`;
                }

                const grandTotal = grandCash + grandResourceValue;

                // ── Assemble final HTML ───────────────────────────────────────
                resultsBody.innerHTML = `
                    <h5 class="text-center mb-3" style="color:#ffd700;">Unit Cost Breakdown</h5>
                    ${unitCardsHTML}

                    <div class="mb-3 p-3 rounded" style="background:rgba(255,215,0,0.06);border:1px solid rgba(255,215,0,0.3);">
                        <h6 class="mb-2" style="color:#ffd700;">📦 Total Resources Required</h6>
                        <div class="d-flex justify-content-between align-items-center py-1 border-bottom border-secondary">
                            <span style="color:#c0c0c0;">💵 Cash</span>
                            <span class="fw-bold text-warning">${fmt(grandCash)}</span>
                        </div>
                        ${resourceTotalsHTML}
                    </div>

                    <div class="p-3 rounded text-center" style="background:rgba(255,215,0,0.1);border:2px solid rgba(255,215,0,0.5);">
                        <div style="color:#a0a0a0;font-size:0.85rem;">Cash + Market Value of Resources</div>
                        <div class="fw-bold" style="color:#ffd700;font-size:1.5rem;text-shadow:0 0 8px #ffd700;">
                            ${fmt(grandTotal)}
                        </div>
                        <small class="text-muted">Resource prices from live market data</small>
                    </div>`;

            } catch (error) {
                resultsBody.innerHTML = `<p class="text-center text-danger">Error calculating costs: ${error.message}</p>`;
            }
        }
        
        // Building Cost Functions (from costs.py)
        function infra_price(amount) {
            return ((Math.abs(amount - 10) ** 2.2) / 710.0) + 300.0;
        }

        function calc_infra_value(starting_amount, ending_amount) {
            let start = parseFloat(starting_amount.toFixed(2));
            let end = parseFloat(ending_amount.toFixed(2));
            let diff = end - start;

            if (diff > 10000) return Infinity;
            if (diff <= 0) return 150.0 * diff;

            let total_cost = 0;
            while(start < end) {
                let chunk = Math.min(100, end - start);
                total_cost += infra_price(start) * chunk;
                start += chunk;
            }
            return total_cost;
        }
        
        function land_price(amount) {
            return (0.002 * (amount - 20) * (amount - 20)) + 50.0;
        }

        function calc_land_value(starting_amount, ending_amount) {
            let start = parseFloat(starting_amount.toFixed(2));
            let end = parseFloat(ending_amount.toFixed(2));
            let diff = end - start;

            if (diff > 10000) return Infinity;
            if (diff <= 0) return 50.0 * diff;

            let total_cost = 0;
            while(start < end) {
                let chunk = Math.min(500, end-start);
                total_cost += land_price(start) * chunk;
                start += chunk;
            }
            return total_cost;
        }

        function calculate_project_discounts(nation_data) {
            if (!nation_data) return { infra_cost_reduction: 0.0, land_cost_reduction: 0.0, domestic_policy_multiplier: 1.0 };
            const discounts = { infra_cost_reduction: 0.0, land_cost_reduction: 0.0, domestic_policy_multiplier: 1.0 };
            if (nation_data.center_for_civil_engineering) discounts.infra_cost_reduction += 0.05;
            if (nation_data.advanced_engineering_corps) {
                discounts.infra_cost_reduction += 0.05;
                discounts.land_cost_reduction += 0.05;
            }
            if (nation_data.arable_land_agency) discounts.land_cost_reduction += 0.05;
            if (nation_data.bureau_of_domestic_affairs) discounts.domestic_policy_multiplier += 0.25;
            if (nation_data.government_support_agency) discounts.domestic_policy_multiplier += 0.50;
            return discounts;
        }

        function infra_purchase_cost(current_infra, infra_to_buy, nation_data) {
            const target_infra = current_infra + infra_to_buy;
            const raw_cost = calc_infra_value(current_infra, target_infra);
            const project_discounts = calculate_project_discounts(nation_data);
            const project_reduction = project_discounts.infra_cost_reduction;
            const base_cost = raw_cost * (1.0 - project_reduction);
            const policy_reduction = 0.05 * project_discounts.domestic_policy_multiplier;
            const final_cost = base_cost * (1.0 - policy_reduction);
            return { base_cost, final_cost };
        }

        function land_purchase_cost(current_land, land_to_buy, nation_data) {
            const target_land = current_land + land_to_buy;
            const raw_cost = calc_land_value(current_land, target_land);
            const project_discounts = calculate_project_discounts(nation_data);
            const project_reduction = project_discounts.land_cost_reduction;
            const base_cost = raw_cost * (1.0 - project_reduction);
            const policy_reduction = 0.05 * project_discounts.domestic_policy_multiplier;
            const final_cost = base_cost * (1.0 - policy_reduction);
            return { base_cost, final_cost };
        }

        function city_purchase_cost(city_to_buy, top_20_average, nation_data) {
            const term1 = 100000 * ((city_to_buy - (top_20_average / 4)) ** 3);
            const term2 = 150000 * (city_to_buy - (top_20_average / 4));
            const term3 = 75000;
            const cost1 = term1 + term2 + term3;
            const cost2 = (city_to_buy ** 2) * 100000;
            const base_cost = Math.max(cost1, cost2);
            const project_discounts = calculate_project_discounts(nation_data);
            const policy_reduction = 0.05 * project_discounts.domestic_policy_multiplier;
            const final_cost = base_cost * (1.0 - policy_reduction);
            return { base_cost, final_cost };
        }
        
        const PROJECT_BUILD_COSTS = {
            'Activity Center': { money: 500000, food: 1000 },
            'Advanced Engineering Corps': { money: 50000000, munitions: 10000, gasoline: 10000, uranium: 1000 },
            'Arable Land Agency': { money: 3000000, coal: 1500, lead: 1500 },
            'Bureau of Domestic Affairs': { money: 20000000, food: 500000, coal: 8000, bauxite: 8000, lead: 8000, iron: 8000, oil: 8000 },
            'Center Civil Engineering': { money: 3000000, oil: 1000, iron: 1000, bauxite: 1000 },
            'Clinical Research Center': { money: 10000000, food: 100000 },
            'Government Support Agency': { money: 20000000, aluminum: 10000, food: 200000 },
            'Green Technologies': { money: 50000000, food: 100000, aluminum: 10000, iron: 10000, oil: 10000 },
            'International Trade Center': { money: 50000000, aluminum: 10000 },
            'Advanced Pirate Economy': { money: 50000000, coal: 10000, iron: 10000, oil: 10000, bauxite: 10000, lead: 10000 },
            'Central Intelligence Agency': { money: 5000000, steel: 500, gasoline: 500 },
            'Guiding Satellite': { money: 200000000, munitions: 40000, aluminum: 40000, uranium: 40000, gasoline: 40000, steel: 20000 },
            'Iron Dome': { money: 15000000, munitions: 5000 },
            'Missile Launch Pad': { money: 5000000, steel: 500, gasoline: 500 },
            'Nuclear Research Facility': { money: 50000000, aluminum: 10000, uranium: 1000 },
            'Propaganda Bureau': { money: 5000000, coal: 1000, iron: 1000 },
            'Space Program': { money: 50000000, aluminum: 10000, steel: 10000, gasoline: 10000 },
            'Vital Defense System': { money: 60000000, steel: 25000, aluminum: 25000, munitions: 25000 },
            'Military Research Center': { money: 100000000, steel: 10000, aluminum: 10000, munitions: 10000, gasoline: 10000 },
            'Military Doctrine': { money: 10000000, steel: 10000, aluminum: 10000, munitions: 10000, gasoline: 10000 },
            'Arms Stockpile': { money: 10000000, coal: 500, iron: 500, oil: 500, bauxite: 500, lead: 500 },
            'Bauxite Works': { money: 10000000, coal: 500, iron: 500, oil: 500, bauxite: 500, lead: 500 },
            'Emergency Gasoline Reserve': { money: 10000000, coal: 500, iron: 500, oil: 500, bauxite: 500, lead: 500 },
            'Fallout Shelter': { money: 25000000, food: 100000, lead: 10000, aluminum: 15000, steel: 10000 },
            'Iron Works': { money: 10000000, coal: 500, iron: 500, oil: 500, bauxite: 500, lead: 500 },
            'Mars Landing': { money: 200000000, oil: 20000, aluminum: 20000, munitions: 20000, steel: 20000, gasoline: 20000, uranium: 20000 },
            'Mass Irrigation': { money: 10000000, food: 50000, coal: 500, iron: 500, oil: 500, bauxite: 500, lead: 500 },
            'Military Salvage': { money: 20000000, aluminum: 5000, steel: 5000, gasoline: 5000 },
            'Moon Landing': { money: 50000000, oil: 5000, aluminum: 5000, munitions: 5000, steel: 5000, gasoline: 5000, uranium: 10000 },
            'Nuclear Launch Facility': { money: 750000000, uranium: 50000, gasoline: 50000, aluminum: 50000 },
            'Pirate Economy': { money: 25000000, coal: 7500, iron: 7500, oil: 7500, bauxite: 7500, lead: 7500 },
            'Recycling Initiative': { money: 10000000, food: 100000 },
            'Research & Development Center': { money: 50000000, aluminum: 5000, food: 100000, uranium: 1000 },
            'Specialized Police Training Program': { money: 50000000, food: 250000, aluminum: 5000 },
            'Spy Satellite': { money: 20000000, oil: 10000, bauxite: 10000, iron: 10000, lead: 10000, coal: 10000 },
            'Surveillance Network': { money: 50000000, aluminum: 50000, bauxite: 15000, iron: 15000, lead: 15000, coal: 15000 },
            'Telecommunications Satellite': { money: 300000000, oil: 10000, aluminum: 10000, iron: 10000, uranium: 10000 },
            'Uranium Enrichment Program': { money: 25000000, uranium: 2500, coal: 500, iron: 500, oil: 500, bauxite: 500, lead: 500 },
        };

        // --- Project Picker (init after PROJECT_BUILD_COSTS) ---
        const PROJECT_NAMES = Object.keys(PROJECT_BUILD_COSTS).sort();
        const selectedProjects = new Set();

        function ppUpdateLabel() {
            const count = selectedProjects.size;
            const label = document.getElementById('pp-label');
            if (count === 0) {
                label.innerHTML = 'Select projects...';
            } else {
                const names = [...selectedProjects].join(', ');
                label.innerHTML = `${names.length > 42 ? names.slice(0, 42) + '…' : names}<span class="pp-badge">${count}</span>`;
            }
        }

        function ppBuildList(filter = '') {
            const list = document.getElementById('pp-list');
            const lower = filter.toLowerCase();
            list.innerHTML = '';
            PROJECT_NAMES.forEach(name => {
                if (lower && !name.toLowerCase().includes(lower)) return;
                const item = document.createElement('label');
                item.className = 'project-toggle-item' + (selectedProjects.has(name) ? ' checked' : '');
                item.setAttribute('role', 'option');
                item.setAttribute('aria-selected', String(selectedProjects.has(name)));
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.checked = selectedProjects.has(name);
                cb.addEventListener('change', () => {
                    if (cb.checked) selectedProjects.add(name);
                    else selectedProjects.delete(name);
                    item.classList.toggle('checked', cb.checked);
                    item.setAttribute('aria-selected', String(cb.checked));
                    ppUpdateLabel();
                });
                item.appendChild(cb);
                item.appendChild(document.createTextNode(name));
                list.appendChild(item);
            });
        }

        function ppPosition() {
            const trigger = document.getElementById('pp-trigger');
            const panel   = document.getElementById('pp-panel');
            const rect    = trigger.getBoundingClientRect();
            panel.style.left  = rect.left + 'px';
            panel.style.width = rect.width + 'px';
            panel.style.top   = (rect.bottom + 4) + 'px';
        }

        function ppOpen() {
            ppPosition();
            document.getElementById('pp-panel').classList.add('open');
            document.getElementById('pp-trigger').classList.add('open');
            document.getElementById('pp-trigger').setAttribute('aria-expanded', 'true');
            document.getElementById('pp-search').focus();
        }

        function ppClose() {
            document.getElementById('pp-panel').classList.remove('open');
            document.getElementById('pp-trigger').classList.remove('open');
            document.getElementById('pp-trigger').setAttribute('aria-expanded', 'false');
        }

        // Reposition on scroll/resize so the fixed panel tracks the trigger
        window.addEventListener('scroll', () => { if (document.getElementById('pp-panel').classList.contains('open')) ppPosition(); }, true);
        window.addEventListener('resize', () => { if (document.getElementById('pp-panel').classList.contains('open')) ppPosition(); });

        document.getElementById('pp-trigger').addEventListener('click', () => {
            document.getElementById('pp-panel').classList.contains('open') ? ppClose() : ppOpen();
        });
        document.getElementById('pp-trigger').addEventListener('keydown', e => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); ppOpen(); }
        });
        document.getElementById('pp-search').addEventListener('input', e => ppBuildList(e.target.value));
        document.getElementById('pp-select-all').addEventListener('click', () => {
            const filter = document.getElementById('pp-search').value.toLowerCase();
            PROJECT_NAMES.forEach(n => { if (!filter || n.toLowerCase().includes(filter)) selectedProjects.add(n); });
            ppBuildList(filter);
            ppUpdateLabel();
        });
        document.getElementById('pp-clear-all').addEventListener('click', () => {
            selectedProjects.clear();
            ppBuildList(document.getElementById('pp-search').value);
            ppUpdateLabel();
        });
        document.addEventListener('click', e => {
            if (!document.getElementById('project-picker').contains(e.target)) ppClose();
        });
        ppBuildList();
        ppUpdateLabel();
        // Project requirements data (from rev_calc.py PROJECT_EFFECTS)
        const PROJECT_REQUIREMENTS = {
            'Advanced Engineering Corps': ['Center Civil Engineering', 'Arable Land Agency'],
            'Advanced Pirate Economy': ['Pirate Economy'], // Missing from rev_calc.py but logically required
            'Fallout Shelter': ['Research & Development Center', 'Mass Irrigation'],
            'Green Technologies': ['Space Program'],
            'Mars Landing': ['Space Program', 'Moon Landing'],
            'Moon Landing': ['Space Program'],
            'Nuclear Launch Facility': ['Nuclear Research Facility', 'Missile Launch Pad', 'Space Program'],
            'Pirate Economy': ['Propaganda Bureau'],
            'Military Research Center': ['Propaganda Bureau'],
            'Military Doctrine': ['Military Research Center'],
            'Recycling Initiative': ['Center Civil Engineering'],
            'Space Program': ['Missile Launch Pad'],
            'Spy Satellite': ['Space Program', 'Central Intelligence Agency'],
            'Surveillance Network': ['Spy Satellite'],
            'Telecommunications Satellite': ['Space Program']
        };

        // Mapping from project display names to API boolean field names
        const PROJECT_NAME_TO_FLAG = {
            'Activity Center': 'activity_center',
            'Advanced Engineering Corps': 'advanced_engineering_corps',
            'Advanced Pirate Economy': 'advanced_pirate_economy',
            'Arable Land Agency': 'arable_land_agency',
            'Arms Stockpile': 'arms_stockpile',
            'Bauxite Works': 'bauxite_works',
            'Bureau of Domestic Affairs': 'bureau_of_domestic_affairs',
            'Center Civil Engineering': 'center_for_civil_engineering',
            'Clinical Research Center': 'clinical_research_center',
            'Emergency Gasoline Reserve': 'emergency_gasoline_reserve',
            'Fallout Shelter': 'fallout_shelter',
            'Government Support Agency': 'government_support_agency',
            'Green Technologies': 'green_technologies',
            'Guiding Satellite': 'guiding_satellite',
            'Central Intelligence Agency': 'central_intelligence_agency',
            'International Trade Center': 'international_trade_center',
            'Iron Dome': 'iron_dome',
            'Iron Works': 'iron_works',
            'Moon Landing': 'moon_landing',
            'Mars Landing': 'mars_landing',
            'Mass Irrigation': 'mass_irrigation',
            'Military Doctrine': 'military_doctrine',
            'Military Research Center': 'military_research_center',
            'Military Salvage': 'military_salvage',
            'Missile Launch Pad': 'missile_launch_pad',
            'Nuclear Launch Facility': 'nuclear_launch_facility',
            'Nuclear Research Facility': 'nuclear_research_facility',
            'Pirate Economy': 'pirate_economy',
            'Propaganda Bureau': 'propaganda_bureau',
            'Recycling Initiative': 'recycling_initiative',
            'Research & Development Center': 'research_and_development_center',
            'Space Program': 'space_program',
            'Specialized Police Training Program': 'specialized_police_training_program',
            'Spy Satellite': 'spy_satellite',
            'Surveillance Network': 'surveillance_network',
            'Telecommunications Satellite': 'telecommunications_satellite',
            'Uranium Enrichment Program': 'uranium_enrichment_program',
            'Vital Defense System': 'vital_defense_system'
        };

        function checkProjectRequirements(projectName, nationData) {
            const requirements = PROJECT_REQUIREMENTS[projectName];
            if (!requirements) return { hasAll: true, missing: [] };
            
            const missing = requirements.filter(req => {
                const flagName = PROJECT_NAME_TO_FLAG[req];
                return !flagName || !nationData[flagName];
            });
            
            return { hasAll: missing.length === 0, missing };
        }
        
        function project_build_cost(project_name, nation_data) {
            if (!PROJECT_BUILD_COSTS[project_name]) return null;

            const raw_costs = { ...PROJECT_BUILD_COSTS[project_name] };
            const project_discounts = calculate_project_discounts(nation_data);

            const final_cost = { ...raw_costs };
            if (final_cost.money) {
                const policy_discount_multiplier = project_discounts.domestic_policy_multiplier || 1.0;
                const discount_rate = 0.05 * policy_discount_multiplier;
                final_cost.money -= final_cost.money * discount_rate;
            }

            return { base_costs: raw_costs, final_costs: final_cost };
        }
    }

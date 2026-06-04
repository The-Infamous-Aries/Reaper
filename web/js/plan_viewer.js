/**
 * ═══════════════════════════════════════════════════════════════
 * Build Plan Viewer — Progress Display
 * ═══════════════════════════════════════════════════════════════
 * 
 * Fetches and displays the current build plan with progress tracking.
 * Shows what's completed vs outstanding with costs breakdown.
 */

// Main render function
async function renderPlanViewer(nationId, containerEl) {
  containerEl.innerHTML = '<div class="plan-loading">Loading plan...</div>';
  
  try {
    const response = await fetch(`/api/mynation/plan/${nationId}`);
    if (!response.ok) {
      throw new Error(`Failed to load plan: ${response.statusText}`);
    }
    
    const data = await response.json();
    
    // No plan exists
    if (!data.plan) {
      containerEl.innerHTML = renderEmptyState();
      return;
    }
    
    // Render complete plan view
    const html = `
      ${renderPlanHeader(data)}
      ${renderNewCitiesSection(data.plan.plan_data.new_cities || [], data.progress.new_cities || [])}
      ${renderExistingCitiesSection(data.plan.plan_data.existing_cities || [], data.progress.existing_cities || [])}
      ${renderProjectsSection(data.plan.plan_data.projects || [], data.progress.projects || [])}
      ${renderFooterSummary(data.progress, data.total_costs, data.remaining_costs)}
    `;
    
    containerEl.innerHTML = html;
    
  } catch (error) {
    console.error('Error rendering plan viewer:', error);
    containerEl.innerHTML = `
      <div class="plan-error">
        ⚠️ Error loading plan: ${error.message}
      </div>
    `;
  }
}

// Empty state when no plan exists
function renderEmptyState() {
  return `
    <div class="plan-empty-state">
      <div style="text-align: center; padding: 2rem;">
        <div style="font-size: 3rem; margin-bottom: 1rem;">📋</div>
        <h3 style="margin-bottom: 0.5rem;">No Build Plan Yet</h3>
        <p style="color: var(--text-secondary); margin-bottom: 1.5rem;">
          Create a build plan to track your nation's development goals, including new cities, improvements, and projects.
        </p>
        <button class="plan-create-btn" onclick="switchPlanTab(event, 'editor')" style="
          padding: 0.75rem 2rem;
          font-size: 1.1rem;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
          border: none;
          border-radius: 8px;
          cursor: pointer;
          font-weight: 600;
          box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
          transition: transform 0.2s, box-shadow 0.2s;
        " onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 6px 20px rgba(102, 126, 234, 0.6)'" 
           onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 4px 15px rgba(102, 126, 234, 0.4)'">
          ✨ Create Your First Plan
        </button>
      </div>
    </div>
  `;
}

// Plan header with name, costs, time estimate
function renderPlanHeader(data) {
  const { plan, total_costs, remaining_costs, progress } = data;
  
  const invested = {
    cash: (total_costs.total.cash || 0) - (remaining_costs.total.cash || 0),
    ...Object.keys(total_costs.total)
      .filter(k => k !== 'cash')
      .reduce((acc, k) => {
        acc[k] = (total_costs.total[k] || 0) - (remaining_costs.total[k] || 0);
        return acc;
      }, {})
  };
  
  // Format currency
  const formatCost = (cost) => {
    if (!cost || !cost.cash) return '$0';
    const parts = [formatMoney(cost.cash)];
    if (cost.steel) parts.push(`${cost.steel.toLocaleString()} 🔩`);
    if (cost.aluminum) parts.push(`${cost.aluminum.toLocaleString()} ⚙️`);
    if (cost.gasoline) parts.push(`${cost.gasoline.toLocaleString()} ⛽`);
    if (cost.munitions) parts.push(`${cost.munitions.toLocaleString()} 💣`);
    if (cost.uranium) parts.push(`${cost.uranium.toLocaleString()} ☢️`);
    return parts.join(' + ');
  };
  
  // Time estimate (if revenue data available)
  let timeEstimate = '';
  if (remaining_costs.total.cash && data.nation_revenue) {
    const daysNeeded = Math.ceil(remaining_costs.total.cash / data.nation_revenue);
    timeEstimate = `<div class="plan-time-estimate">⏱ ~${daysNeeded} days remaining at ${formatMoney(data.nation_revenue)}/day</div>`;
  }
  
  return `
    <div class="plan-header">
      <div class="plan-title">📋 ${escapeHtml(plan.plan_name)}</div>
      <div class="plan-costs">
        <span class="plan-cost-total">💰 Total: ${formatCost(total_costs.total)}</span>
        <span class="plan-cost-invested">✅ Invested: ${formatCost(invested)}</span>
        <span class="plan-cost-remaining">⏳ Remaining: ${formatCost(remaining_costs.total)}</span>
      </div>
      ${timeEstimate}
    </div>
  `;
}

// New cities section
function renderNewCitiesSection(planCities, progressCities) {
  if (!planCities || planCities.length === 0) {
    return '';
  }
  
  const doneCount = progressCities.filter(c => c.done).length;
  
  const cardsHtml = planCities.map((city, idx) => {
    const progress = progressCities[idx] || { done: false, steps: {} };
    return renderNewCityCard(city, progress);
  }).join('');
  
  return `
    <div class="plan-section">
      <div class="plan-section-header">
        <div>
          <span class="plan-section-title">🏙️ New Cities</span>
          <span class="plan-section-progress">(${doneCount}/${planCities.length} done)</span>
        </div>
      </div>
      <div class="plan-section-body">
        ${cardsHtml}
      </div>
    </div>
  `;
}

// Individual new city card
function renderNewCityCard(city, progress) {
  const status = progress.done ? '✅' : '⏳';
  const cardClass = progress.done ? 'plan-city-done' : 'plan-city-pending';
  const label = city.label || `City ${city.slot}`;
  
  // Build steps list
  const steps = progress.steps || {};
  const stepsHtml = `
    ${renderStep('City purchased', steps.city_purchased)}
    ${renderStep(`Infra to ${city.infra}`, steps.infra_done)}
    ${renderStep(`Land to ${city.land}`, steps.land_done)}
    ${renderStep(`Improvements`, steps.improvements_done)}
  `;
  
  // Improvements summary
  const impHtml = renderImprovementsSummary(city.improvements || {});
  
  return `
    <div class="plan-city-card ${cardClass}">
      <div class="plan-city-header">
        <span class="plan-city-status">${status}</span>
        <span class="plan-city-name">${label}</span>
      </div>
      <div class="plan-city-steps">
        ${stepsHtml}
      </div>
      ${impHtml ? `<div class="plan-city-improvements">${impHtml}</div>` : ''}
    </div>
  `;
}

// Existing cities section
function renderExistingCitiesSection(planCities, progressCities) {
  if (!planCities || planCities.length === 0) {
    return '';
  }
  
  const doneCount = progressCities.filter(c => c.done).length;
  
  const cardsHtml = planCities.map((city, idx) => {
    const progress = progressCities.find(p => p.city_id === city.city_id) || { done: false, steps: {} };
    return renderExistingCityCard(city, progress);
  }).join('');
  
  return `
    <div class="plan-section">
      <div class="plan-section-header">
        <div>
          <span class="plan-section-title">🏗️ Existing Cities</span>
          <span class="plan-section-progress">(${doneCount}/${planCities.length} done)</span>
        </div>
      </div>
      <div class="plan-section-body">
        ${cardsHtml}
      </div>
    </div>
  `;
}

// Individual existing city card
function renderExistingCityCard(city, progress) {
  const status = progress.done ? '✅' : '⏳';
  const cardClass = progress.done ? 'plan-city-done' : 'plan-city-pending';
  
  // Build steps list
  const steps = progress.steps || {};
  let stepsHtml = '';
  if (city.target_infra) {
    stepsHtml += renderStep(`Infra to ${city.target_infra}`, steps.infra_done);
  }
  if (city.target_land) {
    stepsHtml += renderStep(`Land to ${city.target_land}`, steps.land_done);
  }
  if (city.target_improvements) {
    const impSteps = steps.improvements || {};
    Object.keys(city.target_improvements).forEach(impCol => {
      const count = city.target_improvements[impCol];
      const name = getImprovementName(impCol);
      stepsHtml += renderStep(`${name} x${count}`, impSteps[impCol]);
    });
  }
  
  return `
    <div class="plan-city-card ${cardClass}">
      <div class="plan-city-header">
        <span class="plan-city-status">${status}</span>
        <span class="plan-city-name">${city.city_name} (ID: ${city.city_id})</span>
      </div>
      <div class="plan-city-steps">
        ${stepsHtml}
      </div>
    </div>
  `;
}

// Projects section
function renderProjectsSection(planProjects, progressProjects) {
  if (!planProjects || planProjects.length === 0) {
    return '';
  }
  
  const doneCount = progressProjects.filter(p => p.done).length;
  
  const cardsHtml = planProjects.map((projectCol, idx) => {
    const progress = progressProjects.find(p => p.db_col === projectCol) || { done: false };
    return renderProjectCard(projectCol, idx + 1, progress);
  }).join('');
  
  return `
    <div class="plan-section">
      <div class="plan-section-header">
        <div>
          <span class="plan-section-title">🔬 Projects</span>
          <span class="plan-section-progress">(${doneCount}/${planProjects.length} done)</span>
        </div>
      </div>
      <div class="plan-section-body">
        ${cardsHtml}
      </div>
    </div>
  `;
}

// Individual project card
function renderProjectCard(projectCol, number, progress) {
  const cardClass = progress.done ? 'plan-project-done' : 'plan-project-pending';
  const projectName = getProjectName(projectCol);
  
  let statusHtml = '';
  if (progress.done) {
    statusHtml = '<span class="plan-project-status">done</span>';
  }
  
  return `
    <div class="plan-project-card ${cardClass}">
      <div class="plan-project-header">
        <span class="plan-project-number">${number}.</span>
        <span class="plan-project-name">${projectName}</span>
        ${statusHtml}
      </div>
      ${progress.done ? '<div class="plan-project-note">Already owned</div>' : ''}
    </div>
  `;
}

// Footer summary
function renderFooterSummary(progress, totalCosts, remainingCosts) {
  const overall = progress.overall_progress || { total_steps: 0, completed_steps: 0, percent_complete: 0 };
  
  const formatCostLine = (cost) => {
    if (!cost) return '$0';
    const parts = [];
    if (cost.cash) parts.push(formatMoney(cost.cash));
    if (cost.steel) parts.push(`🔩 ${cost.steel.toLocaleString()}`);
    if (cost.aluminum) parts.push(`⚙️ ${cost.aluminum.toLocaleString()}`);
    if (cost.gasoline) parts.push(`⛽ ${cost.gasoline.toLocaleString()}`);
    if (cost.munitions) parts.push(`💣 ${cost.munitions.toLocaleString()}`);
    if (cost.uranium) parts.push(`☢️ ${cost.uranium.toLocaleString()}`);
    return parts.join(' + ') || '$0';
  };
  
  const invested = {
    cash: (totalCosts.total.cash || 0) - (remainingCosts.total.cash || 0)
  };
  
  return `
    <div class="plan-footer-summary">
      <div class="plan-overall-progress">
        <div class="plan-progress-label">📊 Overall Progress: ${overall.percent_complete.toFixed(1)}% complete (${overall.completed_steps}/${overall.total_steps} steps)</div>
        <div class="plan-progress-bar">
          <div class="plan-progress-fill" style="width: ${overall.percent_complete}%"></div>
        </div>
      </div>
      <div class="plan-cost-breakdown">
        <div class="plan-cost-line">
          <span class="plan-cost-label">💰 Total Cost:</span>
          <span class="plan-cost-value">${formatCostLine(totalCosts.total)}</span>
        </div>
        <div class="plan-cost-line">
          <span class="plan-cost-label">✅ Invested:</span>
          <span class="plan-cost-value plan-cost-invested">${formatMoney(invested.cash)}</span>
        </div>
        <div class="plan-cost-line">
          <span class="plan-cost-label">⏳ Remaining:</span>
          <span class="plan-cost-value plan-cost-remaining">${formatCostLine(remainingCosts.total)}</span>
        </div>
      </div>
    </div>
  `;
}

// ═══════════════════════════════════════════════════════════════
// Helper Functions
// ═══════════════════════════════════════════════════════════════

// Render a single step
function renderStep(label, isDone) {
  const icon = isDone ? '✅' : '⬜';
  const stepClass = isDone ? 'plan-step-done' : '';
  return `
    <div class="plan-step ${stepClass}">
      <span class="plan-step-icon">${icon}</span>
      <span class="plan-step-label">${label}</span>
    </div>
  `;
}

// Render improvements summary with icons
function renderImprovementsSummary(improvements) {
  if (!improvements || Object.keys(improvements).length === 0) {
    return '';
  }
  
  const parts = [];
  for (const [impCol, count] of Object.entries(improvements)) {
    if (count > 0) {
      const icon = getImprovementIcon(impCol);
      parts.push(`<img src="${icon}" class="plan-imp-icon" title="${getImprovementName(impCol)}">×${count}`);
    }
  }
  return parts.join(' ');
}

// Get improvement icon path - EXACT SAME AS NATIONS PAGE
function getImprovementIcon(impCol) {
  const iconMap = {
    // Power
    coal_power: '/static/Emojis/Resources/coal.png',
    oil_power: '/static/Emojis/Resources/oil.png',
    nuclear_power: '/static/Emojis/Resources/uranium.png',
    wind_power: '/static/Emojis/Improvements/windmill.png',
    // Mines
    coal_mine: '/static/Emojis/Resources/coal.png',
    oil_well: '/static/Emojis/Resources/oil.png',
    uranium_mine: '/static/Emojis/Resources/uranium.png',
    iron_mine: '/static/Emojis/Resources/iron.png',
    bauxite_mine: '/static/Emojis/Resources/bauxite.png',
    lead_mine: '/static/Emojis/Resources/lead.png',
    farm: '/static/Emojis/Resources/food.png',
    // Manufacturing
    oil_refinery: '/static/Emojis/Resources/gasoline.png',
    aluminum_refinery: '/static/Emojis/Resources/aluminum.png',
    steel_mill: '/static/Emojis/Resources/steel.png',
    munitions_factory: '/static/Emojis/Resources/munitions.png',
    factory: '/static/Emojis/Military/tank.png',
    // Civil
    police_station: '/static/Emojis/Improvements/police.png',
    hospital: '/static/Emojis/Improvements/hospital.png',
    recycling_center: '/static/Emojis/Improvements/recycle.png',
    subway: '/static/Emojis/Improvements/subway.png',
    // Commerce
    supermarket: '/static/Emojis/Improvements/supermarket.png',
    bank: '/static/Emojis/Improvements/bank.png',
    shopping_mall: '/static/Emojis/Improvements/market.png',
    stadium: '/static/Emojis/Improvements/stadium.png',
    // Military
    barracks: '/static/Emojis/Military/soldier.png',
    hangar: '/static/Emojis/Military/jet.png',
    drydock: '/static/Emojis/Military/ship.png'
  };
  return iconMap[impCol] || '/static/Emojis/placeholder.png';
}

// Get improvement display name — matches IMP_DEF on the nations page
function getImprovementName(impCol) {
  const nameMap = {
    coal_power:         'Coal Power',
    oil_power:          'Oil Power',
    nuclear_power:      'Nuclear Power',
    wind_power:         'Wind Power',
    coal_mine:          'Coal Mine',
    oil_well:           'Oil Well',
    uranium_mine:       'Uranium Mine',
    iron_mine:          'Iron Mine',
    bauxite_mine:       'Bauxite Mine',
    lead_mine:          'Lead Mine',
    farm:               'Farm',
    oil_refinery:       'Oil Refinery',
    aluminum_refinery:  'Alu Refinery',
    steel_mill:         'Steel Mill',
    munitions_factory:  'Munitions Factory',
    factory:            'Factory',
    police_station:     'Police Station',
    hospital:           'Hospital',
    recycling_center:   'Recycling Center',
    subway:             'Subway',
    supermarket:        'Supermarket',
    bank:               'Bank',
    shopping_mall:      'Shopping Mall',
    stadium:            'Stadium',
    barracks:           'Barracks',
    hangar:             'Hangar',
    drydock:            'Drydock'
  };
  return nameMap[impCol] || impCol.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

// Get project display name
function getProjectName(projectCol) {
  // This would ideally come from a data file, but hardcoding for now
  const nameMap = {
    advanced_engineering_corps: 'Advanced Engineering Corps',
    arable_land_agency: 'Arable Land Agency',
    bureau_of_domestic_affairs: 'Bureau of Domestic Affairs',
    center_for_civil_engineering: 'Center for Civil Engineering',
    clinical_research_center: 'Clinical Research Center',
    government_support_agency: 'Government Support Agency',
    international_trade_center: 'International Trade Center',
    iron_dome: 'Iron Dome',
    manifest_destiny: 'Manifest Destiny',
    mass_irrigation: 'Mass Irrigation',
    metropolitan_planning: 'Metropolitan Planning',
    missile_launch_pad: 'Missile Launch Pad',
    nuclear_research_facility: 'Nuclear Research Facility',
    propaganda_bureau: 'Propaganda Bureau',
    intelligence_agency: 'Intelligence Agency',
    uranium_enrichment_program: 'Uranium Enrichment Program',
    vital_defense_system: 'Vital Defense System'
  };
  return nameMap[projectCol] || projectCol.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

// Format money
function formatMoney(amount) {
  if (!amount) return '$0';
  if (amount >= 1_000_000_000) {
    return `$${(amount / 1_000_000_000).toFixed(2)}B`;
  } else if (amount >= 1_000_000) {
    return `$${(amount / 1_000_000).toFixed(2)}M`;
  } else if (amount >= 1_000) {
    return `$${(amount / 1_000).toFixed(2)}K`;
  }
  return `$${amount.toLocaleString()}`;
}

// Escape HTML
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

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

    // Store data globally so editor can access sell_prices for live preview
    window._planViewerData = data;
    
    // Render complete plan view — only the Overall Progress box (header + step list + totals).
    // The redundant city/project section cards and the duplicate totals at the top are omitted.
    const html = renderFooterSummary(data);
    
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
        <button class="plan-create-btn" onclick="
          const ea = document.getElementById('plan-editor-area');
          const btn = document.getElementById('plan-edit-toggle-btn');
          if (ea) { ea.style.display='block'; if(btn){btn.textContent='✕ Close Editor';btn.classList.add('active');} }
          if (typeof renderPlanEditor === 'function' && window.currentPlanNationId && ea && !ea.dataset.loaded) {
            renderPlanEditor(window.currentPlanNationId, ea);
            ea.dataset.loaded = '1';
          }
        " style="
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
  const sellPrices = data.sell_prices || {};

  // Map of resource key → image icon path (shared with footer)
  const RESOURCE_ICONS = {
    steel:     '/static/Emojis/Resources/steel.png',
    aluminum:  '/static/Emojis/Resources/aluminum.png',
    gasoline:  '/static/Emojis/Resources/gasoline.png',
    munitions: '/static/Emojis/Resources/munitions.png',
    uranium:   '/static/Emojis/Resources/uranium.png',
    food:      '/static/Emojis/Resources/food.png',
    coal:      '/static/Emojis/Resources/coal.png',
    oil:       '/static/Emojis/Resources/oil.png',
    iron:      '/static/Emojis/Resources/iron.png',
    bauxite:   '/static/Emojis/Resources/bauxite.png',
    lead:      '/static/Emojis/Resources/lead.png',
  };
  const RESOURCE_ORDER = ['steel', 'aluminum', 'gasoline', 'munitions', 'uranium',
                           'food', 'coal', 'oil', 'iron', 'bauxite', 'lead'];

  // Compute invested as (total - remaining) per resource
  const invested = {};
  const allKeys = new Set([
    ...Object.keys(total_costs.total || {}),
    ...Object.keys(remaining_costs.total || {}),
  ]);
  for (const k of allKeys) {
    const diff = (total_costs.total[k] || 0) - (remaining_costs.total[k] || 0);
    if (diff > 0) invested[k] = diff;
  }
  
  // Format a cost object: cash + resource icons + ≈ total
  const formatCost = (cost) => {
    if (!cost) return '$0';
    const parts = [];
    let totalDollars = cost.cash || 0;

    if (cost.cash) parts.push(`<span>${formatMoney(cost.cash)}</span>`);

    for (const res of RESOURCE_ORDER) {
      const qty = cost[res];
      if (!qty) continue;
      const iconSrc = RESOURCE_ICONS[res] || '';
      const iconHtml = iconSrc
        ? `<img src="${iconSrc}" class="plan-res-icon" title="${res}" style="width:15px;height:15px;vertical-align:middle;margin:0 2px;">`
        : `[${res}]`;
      parts.push(`${iconHtml}${Math.round(qty).toLocaleString()}`);
      totalDollars += qty * (sellPrices[res] || 0);
    }

    if (parts.length === 0) return '$0';

    const hasResources = Object.keys(cost).some(k => k !== 'cash' && cost[k]);
    const totalHtml = hasResources
      ? ` <span class="plan-cost-total-eq" title="Cash + resources at best sell price">≈ ${formatMoney(totalDollars)}</span>`
      : '';
    return parts.join(' + ') + totalHtml;
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
function renderNewCitiesSection(planCities, progressCities, cityCosts, sellPrices) {
  if (!planCities || planCities.length === 0) {
    return '';
  }
  
  const doneCount = progressCities.filter(c => c.done).length;
  
  const cardsHtml = planCities.map((city, idx) => {
    const progress = progressCities[idx] || { done: false, steps: {} };
    const costData  = cityCosts[idx]    || { costs: {} };
    return renderViewerNewCityCard(city, progress, costData, sellPrices);
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
function renderViewerNewCityCard(city, progress, costData, sellPrices) {
  const status    = progress.done ? '✅' : '⏳';
  const cardClass = progress.done ? 'plan-city-done' : 'plan-city-pending';
  const label     = city.label || `City ${city.slot}`;

  
  // Build steps list
  const steps = progress.steps || {};
  const stepsHtml = `
    ${renderStep('City purchased', steps.city_purchased)}
    ${renderStep(`Infra to ${city.infra}`, steps.infra_done)}
    ${renderStep(`Land to ${city.land}`, steps.land_done)}
    ${renderStep('Improvements', steps.improvements_done)}
  `;
  
  // Improvements summary
  const impHtml = renderImprovementsSummary(city.improvements || {});

  // Cost line
  const costHtml = (costData && costData.costs) ? renderInlineCost(costData.costs, sellPrices) : '';
  
  return `
    <div class="plan-city-card ${cardClass}">
      <div class="plan-city-header">
        <span class="plan-city-status">${status}</span>
        <span class="plan-city-name">${label}</span>
        ${costHtml ? `<span class="plan-city-cost">${costHtml}</span>` : ''}
      </div>
      <div class="plan-city-steps">
        ${stepsHtml}
      </div>
      ${impHtml ? `<div class="plan-city-improvements">${impHtml}</div>` : ''}
    </div>
  `;
}

// Existing cities section
function renderExistingCitiesSection(planCities, progressCities, cityCosts, sellPrices) {
  if (!planCities || planCities.length === 0) {
    return '';
  }
  
  const doneCount = progressCities.filter(c => c.done).length;
  
  const cardsHtml = planCities.map((city, idx) => {
    const progress = progressCities.find(p => p.city_id === city.city_id) || { done: false, steps: {} };
    const costData  = (cityCosts || []).find(c => c.city_id === city.city_id) || { costs: {} };
    return renderViewerExistingCityCard(city, progress, costData, sellPrices);
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
function renderViewerExistingCityCard(city, progress, costData, sellPrices) {
  const status    = progress.done ? '✅' : '⏳';
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
      const name  = getImprovementName(impCol);
      stepsHtml  += renderStep(`${name} ×${count}`, impSteps[impCol]);
    });
  }

  const costHtml = (costData && costData.costs) ? renderInlineCost(costData.costs, sellPrices || {}) : '';
  
  return `
    <div class="plan-city-card ${cardClass}">
      <div class="plan-city-header">
        <span class="plan-city-status">${status}</span>
        <span class="plan-city-name">${city.city_name}</span>
        ${costHtml ? `<span class="plan-city-cost">${costHtml}</span>` : ''}
      </div>
      <div class="plan-city-steps">
        ${stepsHtml}
      </div>
    </div>
  `;
}

// Projects section
function renderProjectsSection(planProjects, progressProjects, projectCosts, sellPrices) {
  if (!planProjects || planProjects.length === 0) {
    return '';
  }
  
  const doneCount = progressProjects.filter(p => p.done).length;
  
  const cardsHtml = planProjects.map((projectCol, idx) => {
    const progress  = progressProjects.find(p => p.db_col === projectCol) || { done: false };
    const costEntry = (projectCosts || []).find(c => c.db_col === projectCol) || { costs: {}, name: null };
    return renderProjectCard(projectCol, idx + 1, progress, costEntry, sellPrices);
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
function renderProjectCard(projectCol, number, progress, costEntry, sellPrices) {
  const cardClass   = progress.done ? 'plan-project-done' : 'plan-project-pending';
  const projectName = (costEntry && costEntry.name) || getProjectName(projectCol);
  const costs       = (costEntry && costEntry.costs) || {};

  const statusBadge = progress.done
    ? '<span class="plan-project-status plan-project-owned-badge">✅ owned</span>'
    : '';

  // Cost line — only render for unowned projects that have cost data
  let costHtml = '';
  if (!progress.done && Object.keys(costs).length > 0) {
    costHtml = `<span class="plan-project-cost">${renderInlineCost(costs, sellPrices || {})}</span>`;
  }
  
  return `
    <div class="plan-project-card ${cardClass}">
      <div class="plan-project-header">
        <span class="plan-project-number">${number}.</span>
        <span class="plan-project-name">${projectName}</span>
        ${statusBadge}
        ${costHtml}
      </div>
    </div>
  `;
}

// Footer summary — Overall Progress bar + step checklist + cost totals
function renderFooterSummary(data) {
  const progress           = data.progress      || {};
  const totalCosts         = data.all_policy_total_costs     || data.total_costs     || { total: {} };
  const remainingCosts     = data.all_policy_remaining_costs || data.remaining_costs || { total: {} };
  const sellPrices         = data.sell_prices   || {};
  const planData           = data.plan          ? data.plan.plan_data : {};
  const cityCosts          = data.city_costs    || { new_cities: [], existing_cities: [] };
  const projectCosts       = data.project_costs || [];

  const overall = progress.overall_progress || { total_steps: 0, completed_steps: 0, percent_complete: 0 };
  const overallPercent = Math.max(0, Math.min(100, Number(overall.percent_complete) || 0));
  const progressBgSize = overallPercent > 0 ? (10000 / overallPercent) : 100;

  // ── Cost formatter (returns HTML string) ───────────────────────────────────
  function costHtml(costs) {
    if (!costs || !Object.keys(costs).length) return '';
    return renderInlineCost(costs, sellPrices);
  }

  // ── Total-line formatter (returns {html, totalDollars}) ────────────────────
  function totalLine(costObj) {
    if (!costObj || !Object.keys(costObj).length) return { html: '<span class="plan-cost-zero">$0</span>', totalDollars: 0 };
    return { html: renderInlineCost(costObj, sellPrices) || '<span class="plan-cost-zero">$0</span>', totalDollars: 0 };
  }

  // ── Build step rows ────────────────────────────────────────────────────────
  let stepRows = '';
  let stepNum  = 0;

  // ── New Cities ──────────────────────────────────────────────────────────
  const newCitiesPlan     = planData.new_cities     || [];
  const newCitiesProgress = progress.new_cities     || [];
  const newCitiesCosts    = cityCosts.new_cities    || [];

  if (newCitiesPlan.length) {
    stepRows += `<div class="pfs-group-header">🏙️ New Cities</div>`;

    newCitiesPlan.forEach((cp, idx) => {
      const pr      = newCitiesProgress[idx] || { done: false, steps: {} };
      const cc      = newCitiesCosts[idx]    || { costs: {}, substep_costs: {} };
      const steps   = pr.steps || {};
      const label   = cp.label || `City ${cp.slot}`;
      const cityNum = '';
      const isDone  = pr.done;
      const sub     = cc.substep_costs || {};

      // Per-city cost (total)
      const cHtml = costHtml(cc.costs);

      // City-level row (the whole city as one item)
      stepNum++;
      stepRows += `
        <div class="pfs-step ${isDone ? 'pfs-step-done' : ''}">
          <span class="pfs-check">${isDone ? '✅' : '⬜'}</span>
          <span class="pfs-label">
            <strong>${label}</strong>
            ${cityNum ? `<span class="pfs-sub">${cityNum}</span>` : ''}
          </span>
          ${cHtml ? `<span class="pfs-cost">${cHtml}</span>` : ''}
        </div>`;

      // Sub-steps with individual costs
      const subSteps = [
        { key: 'city_purchased',    label: 'Purchase city',                     costKey: 'city_purchase' },
        { key: 'infra_done',        label: `Infrastructure → ${cp.infra || 10}`, costKey: 'infra' },
        { key: 'land_done',         label: `Land → ${cp.land || 250}`,           costKey: 'land' },
        { key: 'improvements_done', label: 'All improvements',                   costKey: 'improvements' },
      ];
      subSteps.forEach(ss => {
        const done      = steps[ss.key] === true;
        const ssCosts   = sub[ss.costKey] || {};
        const ssCostHtml = Object.keys(ssCosts).length ? costHtml(ssCosts) : '';
        stepRows += `
          <div class="pfs-substep ${done ? 'pfs-step-done' : ''}">
            <span class="pfs-check">${done ? '✅' : '⬜'}</span>
            <span class="pfs-label">${ss.label}</span>
            ${ssCostHtml ? `<span class="pfs-cost">${ssCostHtml}</span>` : ''}
          </div>`;
      });
    });
  }

  // ── Existing Cities ─────────────────────────────────────────────────────
  const existCitiesPlan     = planData.existing_cities     || [];
  const existCitiesProgress = progress.existing_cities     || [];
  const existCitiesCosts    = cityCosts.existing_cities    || [];

  if (existCitiesPlan.length) {
    stepRows += `<div class="pfs-group-header">🏗️ Existing Cities</div>`;

    existCitiesPlan.forEach((cp, idx) => {
      const pr    = existCitiesProgress.find(p => p.city_id === cp.city_id) || { done: false, steps: {} };
      const cc    = existCitiesCosts.find(c => c.city_id === cp.city_id) || { costs: {}, substep_costs: {} };
      const steps = pr.steps || {};
      const isDone = pr.done;
      const sub   = cc.substep_costs || {};
      const cHtml = costHtml(cc.costs);

      stepNum++;
      stepRows += `
        <div class="pfs-step ${isDone ? 'pfs-step-done' : ''}">
          <span class="pfs-check">${isDone ? '✅' : '⬜'}</span>
          <span class="pfs-label"><strong>${cp.city_name || `City ${cp.city_id}`}</strong></span>
          ${cHtml ? `<span class="pfs-cost">${cHtml}</span>` : ''}
        </div>`;

      // Infra sub-step with cost
      if (cp.target_infra != null) {
        const done = steps.infra_done === true;
        const ssCostHtml = sub.infra && Object.keys(sub.infra).length ? costHtml(sub.infra) : '';
        stepRows += `
          <div class="pfs-substep ${done ? 'pfs-step-done' : ''}">
            <span class="pfs-check">${done ? '✅' : '⬜'}</span>
            <span class="pfs-label">Infrastructure → ${cp.target_infra}</span>
            ${ssCostHtml ? `<span class="pfs-cost">${ssCostHtml}</span>` : ''}
          </div>`;
      }
      // Land sub-step with cost
      if (cp.target_land != null) {
        const done = steps.land_done === true;
        const ssCostHtml = sub.land && Object.keys(sub.land).length ? costHtml(sub.land) : '';
        stepRows += `
          <div class="pfs-substep ${done ? 'pfs-step-done' : ''}">
            <span class="pfs-check">${done ? '✅' : '⬜'}</span>
            <span class="pfs-label">Land → ${cp.target_land}</span>
            ${ssCostHtml ? `<span class="pfs-cost">${ssCostHtml}</span>` : ''}
          </div>`;
      }
      // Improvement sub-steps — show a summary row with cost, then individual items
      const impSteps = steps.improvements || {};
      const impEntries = Object.entries(cp.target_improvements || {});
      if (impEntries.length) {
        const ssCostHtml = sub.improvements && Object.keys(sub.improvements).length ? costHtml(sub.improvements) : '';
        const allImpDone = impEntries.every(([col]) => impSteps[col] === true);
        stepRows += `
          <div class="pfs-substep ${allImpDone ? 'pfs-step-done' : ''}">
            <span class="pfs-check">${allImpDone ? '✅' : '⬜'}</span>
            <span class="pfs-label">All improvements</span>
            ${ssCostHtml ? `<span class="pfs-cost">${ssCostHtml}</span>` : ''}
          </div>`;
        impEntries.forEach(([col, tgt]) => {
          const done = impSteps[col] === true;
          const icon = getImprovementIcon(col);
          const name = getImprovementName(col);
          stepRows += `
            <div class="pfs-substep pfs-substep-l2 ${done ? 'pfs-step-done' : ''}">
              <span class="pfs-check">${done ? '✅' : '⬜'}</span>
              <span class="pfs-label">
                <img src="${icon}" class="plan-res-icon" style="width:13px;height:13px;vertical-align:middle;margin-right:2px;">
                ${name} ×${tgt}
              </span>
            </div>`;
        });
      }
    });
  }

  // ── Projects ─────────────────────────────────────────────────────────────
  const projectsPlan     = planData.projects     || [];
  const projectsProgress = progress.projects     || [];

  if (projectsPlan.length) {
    stepRows += `<div class="pfs-group-header">🔬 Projects</div>`;

    projectsPlan.forEach((projCol, idx) => {
      const pr    = projectsProgress.find(p => p.db_col === projCol) || { done: false };
      const pc    = projectCosts.find(c => c.db_col === projCol)    || { costs: {}, all_policy_costs: {}, name: null };
      const isDone = pr.done;
      const name  = pc.name || getProjectName(projCol);

      // Always show all-policy-discount costs (what it costs with every applicable policy active),
      // regardless of what policies the nation currently has. Never show costs for owned projects.
      const displayCosts = isDone ? {} : (pc.all_policy_costs && Object.keys(pc.all_policy_costs).length ? pc.all_policy_costs : pc.costs);
      const cHtml = isDone ? '' : costHtml(displayCosts);

      stepNum++;
      stepRows += `
        <div class="pfs-step ${isDone ? 'pfs-step-done' : ''}">
          <span class="pfs-check">${isDone ? '✅' : '⬜'}</span>
          <span class="pfs-label">${name}${isDone ? ' <span class="pfs-owned-tag">owned</span>' : ''}</span>
          ${cHtml ? `<span class="pfs-cost">${cHtml}</span>` : ''}
        </div>`;
    });
  }

  // ── Totals ─────────────────────────────────────────────────────────────────
  const investedCost = {};
  const allKeys = new Set([
    ...Object.keys(totalCosts.total    || {}),
    ...Object.keys(remainingCosts.total || {}),
  ]);
  for (const k of allKeys) {
    const diff = (totalCosts.total[k] || 0) - (remainingCosts.total[k] || 0);
    if (diff > 0) investedCost[k] = diff;
  }

  const totalHtml    = totalLine(totalCosts.total).html;
  const investedHtml = totalLine(investedCost).html;
  const remainHtml   = totalLine(remainingCosts.total).html;

  return `
    <div class="plan-footer-summary">

      <!-- Progress bar -->
      <div class="plan-overall-progress">
        <div class="plan-progress-label">
          📊 Overall Progress: <strong>${overallPercent.toFixed(1)}%</strong> complete
          (${overall.completed_steps}/${overall.total_steps} steps)
        </div>
        <div class="plan-progress-bar">
          <div class="plan-progress-fill" style="width: ${overallPercent}%; background-size: ${progressBgSize}% 100%;"></div>
        </div>
      </div>

      <!-- Step checklist -->
      <div class="pfs-step-list">
        ${stepRows || '<div class="pfs-empty">No steps in this plan.</div>'}
      </div>

      <!-- Cost totals — all figures shown with full policy discounts applied -->
      <div class="plan-cost-breakdown pfs-totals">
        <div class="pfs-policy-note">💡 Costs shown with all applicable policy discounts</div>
        <div class="plan-cost-line">
          <span class="plan-cost-label">💰 Total Cost:</span>
          <span class="plan-cost-value">${totalHtml}</span>
        </div>
        <div class="plan-cost-line">
          <span class="plan-cost-label">✅ Invested:</span>
          <span class="plan-cost-value plan-cost-invested">${investedHtml}</span>
        </div>
        <div class="plan-cost-line">
          <span class="plan-cost-label">⏳ Remaining:</span>
          <span class="plan-cost-value plan-cost-remaining">${remainHtml}</span>
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

// ═══════════════════════════════════════════════════════════════
// Shared cost rendering helper
// Used by project cards, city cards, and the footer summary.
// ═══════════════════════════════════════════════════════════════

const PLAN_RESOURCE_ICONS = {
  steel:     '/static/Emojis/Resources/steel.png',
  aluminum:  '/static/Emojis/Resources/aluminum.png',
  gasoline:  '/static/Emojis/Resources/gasoline.png',
  munitions: '/static/Emojis/Resources/munitions.png',
  uranium:   '/static/Emojis/Resources/uranium.png',
  food:      '/static/Emojis/Resources/food.png',
  coal:      '/static/Emojis/Resources/coal.png',
  oil:       '/static/Emojis/Resources/oil.png',
  iron:      '/static/Emojis/Resources/iron.png',
  bauxite:   '/static/Emojis/Resources/bauxite.png',
  lead:      '/static/Emojis/Resources/lead.png',
};

const PLAN_RESOURCE_ORDER = [
  'steel', 'aluminum', 'gasoline', 'munitions', 'uranium',
  'food', 'coal', 'oil', 'iron', 'bauxite', 'lead',
];

/**
 * Render a compact inline cost string with resource images + ≈ total.
 * Returns an HTML string suitable for inline use inside a card header.
 *
 * costs = { cash: number, steel: number, ... }
 * sellPrices = { steel: pricePerUnit, ... }
 */
function renderInlineCost(costs, sellPrices) {
  if (!costs || Object.keys(costs).length === 0) return '';
  sellPrices = sellPrices || {};

  const parts = [];
  let totalDollars = costs.cash || 0;

  if (costs.cash) {
    parts.push(`<span class="pic-cash">${formatMoney(costs.cash)}</span>`);
  }

  for (const res of PLAN_RESOURCE_ORDER) {
    const qty = costs[res];
    if (!qty) continue;
    const src = PLAN_RESOURCE_ICONS[res] || '';
    const img = src
      ? `<img src="${src}" class="plan-res-icon" title="${res}" style="width:14px;height:14px;vertical-align:middle;margin:0 1px 1px;">`
      : `[${res}]`;
    parts.push(`${img}<span class="pic-qty">${Math.round(qty).toLocaleString()}</span>`);
    totalDollars += qty * (sellPrices[res] || 0);
  }

  // Handle any unlisted resource keys
  for (const [res, qty] of Object.entries(costs)) {
    if (res === 'cash' || PLAN_RESOURCE_ORDER.includes(res) || !qty) continue;
    const src = PLAN_RESOURCE_ICONS[res] || '';
    const img = src
      ? `<img src="${src}" class="plan-res-icon" title="${res}" style="width:14px;height:14px;vertical-align:middle;margin:0 1px 1px;">`
      : `[${res}]`;
    parts.push(`${img}<span class="pic-qty">${Math.round(qty).toLocaleString()}</span>`);
    totalDollars += qty * (sellPrices[res] || 0);
  }

  if (parts.length === 0) return '';

  const hasResources = Object.keys(costs).some(k => k !== 'cash' && costs[k]);
  const eqBadge = hasResources
    ? ` <span class="plan-cost-total-eq" title="Cash + resources at current best sell price">≈ ${formatMoney(totalDollars)}</span>`
    : '';

  return `<span class="plan-inline-cost">${parts.join(' + ')}${eqBadge}</span>`;
}

// Ordinal suffix helper (1st, 2nd, 3rd…)  — also used by plan_editor.js
// Defined as a var so it doesn't conflict if plan_editor.js defines it too.
var nth = nth || function nth(n) {
  const s = ['th','st','nd','rd'];
  const v = n % 100;
  return s[(v - 20) % 10] || s[v] || s[0];
};

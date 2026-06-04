/**
 * ═══════════════════════════════════════════════════════════════
 * Build Plan Preview — Nation Simulation
 * ═══════════════════════════════════════════════════════════════
 * 
 * Shows simulated nation state after plan completion.
 * NOTE: This is a simplified initial implementation.
 */

// Main render function
async function renderPlanPreview(nationId, containerEl) {
  containerEl.innerHTML = '<div class="plan-loading">Loading preview...</div>';
  
  try {
    // First, get the current plan
    const planResponse = await fetch(`/api/mynation/plan/${nationId}`);
    if (!planResponse.ok) {
      throw new Error('No plan found. Create a plan first.');
    }
    
    const planData = await planResponse.json();
    if (!planData.plan) {
      containerEl.innerHTML = `
        <div class="plan-empty-state">
          <div style="text-align: center; padding: 2rem;">
            <div style="font-size: 3rem; margin-bottom: 1rem;">🔍</div>
            <h3 style="margin-bottom: 0.5rem;">No Plan to Preview</h3>
            <p style="color: var(--text-secondary); margin-bottom: 1.5rem;">
              Create a build plan first to see a preview of your nation after completion.
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
      return;
    }
    
    // Request preview from API
    const previewResponse = await fetch('/api/mynation/plan/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        nation_id: nationId,
        plan_data: planData.plan.plan_data
      })
    });
    
    if (!previewResponse.ok) {
      throw new Error(`Preview failed: ${previewResponse.statusText}`);
    }
    
    const preview = await previewResponse.json();
    
    // Render preview
    const html = `
      <div class="plan-preview">
        <h3>📊 Nation Preview — After Plan Completion</h3>
        
        ${renderRevenuePreview(preview.revenue)}
        ${renderMilitaryCaps(preview.military_caps)}
        ${renderCitySummary(preview.city_summary)}
        ${preview.warnings && preview.warnings.length > 0 ? renderWarnings(preview.warnings) : ''}
      </div>
    `;
    
    containerEl.innerHTML = html;
    
  } catch (error) {
    console.error('Error rendering preview:', error);
    containerEl.innerHTML = `
      <div class="plan-error">
        ⚠️ ${error.message}
      </div>
    `;
  }
}

// Revenue table
function renderRevenuePreview(revenue) {
  if (!revenue) return '';
  
  const formatMoney = (val) => {
    if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(2)}M`;
    if (val >= 1_000) return `$${(val / 1_000).toFixed(2)}K`;
    return `$${val.toLocaleString()}`;
  };
  
  const colorClass = (val) => val >= 0 ? 'plan-revenue-positive' : 'plan-revenue-negative';
  
  return `
    <div class="plan-preview-section">
      <h4>💰 Revenue (Simulated)</h4>
      <table class="plan-revenue-table">
        <thead>
          <tr>
            <th></th>
            <th>Per Turn</th>
            <th>Per Day</th>
            <th>Per Week</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Gross Income</td>
            <td class="${colorClass(revenue.gross_income)}">${formatMoney(revenue.gross_income)}</td>
            <td class="${colorClass(revenue.gross_income * 12)}">${formatMoney(revenue.gross_income * 12)}</td>
            <td class="${colorClass(revenue.gross_income * 12 * 7)}">${formatMoney(revenue.gross_income * 12 * 7)}</td>
          </tr>
          <tr>
            <td>Net Cash</td>
            <td class="${colorClass(revenue.net_cash_turn)}">${formatMoney(revenue.net_cash_turn)}</td>
            <td class="${colorClass(revenue.net_cash_day)}">${formatMoney(revenue.net_cash_day)}</td>
            <td class="${colorClass(revenue.net_cash_week)}">${formatMoney(revenue.net_cash_week)}</td>
          </tr>
        </tbody>
      </table>
      ${renderResourceOutputs(revenue.resources)}
    </div>
  `;
}

// Resource outputs
function renderResourceOutputs(resources) {
  if (!resources) return '';
  
  const resourceList = [];
  const resourceNames = {
    food: '🌾 Food',
    coal: '⚫ Coal',
    oil: '🛢️ Oil',
    uranium: '☢️ Uranium',
    steel: '🔩 Steel',
    aluminum: '⚙️ Aluminum',
    gasoline: '⛽ Gasoline',
    munitions: '💣 Munitions'
  };
  
  for (const [key, value] of Object.entries(resources)) {
    if (value !== 0) {
      const sign = value > 0 ? '+' : '';
      resourceList.push(`${resourceNames[key] || key}: ${sign}${value.toLocaleString()}`);
    }
  }
  
  if (resourceList.length === 0) return '';
  
  return `
    <div style="margin-top: 1rem; padding: 0.75rem; background: rgba(0,0,0,0.2); border-radius: 4px;">
      <strong>Resource Production (per day):</strong><br>
      ${resourceList.join(' • ')}
    </div>
  `;
}

// Military caps
function renderMilitaryCaps(milCaps) {
  if (!milCaps) return '';
  
  return `
    <div class="plan-preview-section">
      <h4>⚔️ Military Capacity (with planned improvements)</h4>
      <div class="plan-military-grid">
        ${renderMilitaryItem('Soldiers', milCaps.max_soldiers, milCaps.soldiers_per_day)}
        ${renderMilitaryItem('Tanks', milCaps.max_tanks, milCaps.tanks_per_day)}
        ${renderMilitaryItem('Aircraft', milCaps.max_aircraft, milCaps.aircraft_per_day)}
        ${renderMilitaryItem('Ships', milCaps.max_ships, milCaps.ships_per_day)}
        ${renderMilitaryItem('Missiles', null, milCaps.missiles_per_day, '/day')}
        ${renderMilitaryItem('Nukes', null, milCaps.nukes_per_day, '/day')}
      </div>
    </div>
  `;
}

function renderMilitaryItem(label, maxCap, dailyProd, suffix = '') {
  return `
    <div class="plan-military-item">
      <div class="plan-military-label">${label}</div>
      <div class="plan-military-value">${maxCap !== null ? `Max: ${maxCap.toLocaleString()}` : ''}</div>
      <div class="plan-military-daily">${dailyProd.toLocaleString()}${suffix ? suffix : '/day'}</div>
    </div>
  `;
}

// City summary
function renderCitySummary(citySummary) {
  if (!citySummary) return '';
  
  return `
    <div class="plan-preview-section">
      <h4>🏙️ City Summary (Planned)</h4>
      <div class="plan-city-summary">
        <div class="plan-summary-stat">
          <div class="plan-summary-label">Cities</div>
          <div class="plan-summary-value">${citySummary.num_cities}</div>
        </div>
        <div class="plan-summary-stat">
          <div class="plan-summary-label">Avg Infrastructure</div>
          <div class="plan-summary-value">${citySummary.avg_infra.toFixed(0)}</div>
        </div>
        <div class="plan-summary-stat">
          <div class="plan-summary-label">Avg Land</div>
          <div class="plan-summary-value">${citySummary.avg_land.toFixed(0)}</div>
        </div>
        <div class="plan-summary-stat">
          <div class="plan-summary-label">Power Status</div>
          <div class="plan-summary-value">${citySummary.all_powered ? '✅ All Powered' : '⚠️ Issues'}</div>
        </div>
        <div class="plan-summary-stat">
          <div class="plan-summary-label">Slots</div>
          <div class="plan-summary-value">${citySummary.all_within_slots ? '✅ Valid' : '⚠️ Overflow'}</div>
        </div>
        <div class="plan-summary-stat">
          <div class="plan-summary-label">MMR</div>
          <div class="plan-summary-value">${citySummary.mmr || 'N/A'}</div>
        </div>
      </div>
    </div>
  `;
}

// Warnings
function renderWarnings(warnings) {
  if (!warnings || warnings.length === 0) return '';
  
  const warningItems = warnings.map(w => `
    <div class="plan-warning-item">⚠️ ${escapeHtml(w)}</div>
  `).join('');
  
  return `
    <div class="plan-preview-section">
      <div class="plan-warnings">
        <h4>⚠️ Warnings</h4>
        ${warningItems}
      </div>
    </div>
  `;
}

// Helper
function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

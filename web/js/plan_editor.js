/**
 * ═══════════════════════════════════════════════════════════════
 * Build Plan Editor — FULL IMPLEMENTATION (Phase 8B)
 * ═══════════════════════════════════════════════════════════════
 * 
 * Complete visual editor with:
 * - Improvement toggle grid (27 improvements)
 * - City editor cards (expand/collapse)
 * - Project selector with drag-to-reorder
 * - Live validation and save
 */

// ═══════════════════════════════════════════════════════════════
// Global State
// ═══════════════════════════════════════════════════════════════

let editorState = {
  nationId: null,
  nation: null,
  cities: [],
  planName: '',
  newCities: [],
  existingCities: [],
  projects: [],
  isDirty: false
};

// All improvements grouped by category — icons match the nations page exactly.
// Ordered: Power → Mines → Manufacturing → Civil → Commerce → Military
const IMPROVEMENTS = {
  power: [
    { col: 'coal_power',        name: 'Coal Power',        icon: '/static/Emojis/Resources/coal.png' },
    { col: 'oil_power',         name: 'Oil Power',         icon: '/static/Emojis/Resources/oil.png' },
    { col: 'nuclear_power',     name: 'Nuclear Power',     icon: '/static/Emojis/Resources/uranium.png' },
    { col: 'wind_power',        name: 'Wind Power',        icon: '/static/Emojis/Improvements/windmill.png' }
  ],
  mines: [
    { col: 'coal_mine',         name: 'Coal Mine',         icon: '/static/Emojis/Resources/coal.png' },
    { col: 'oil_well',          name: 'Oil Well',          icon: '/static/Emojis/Resources/oil.png' },
    { col: 'uranium_mine',      name: 'Uranium Mine',      icon: '/static/Emojis/Resources/uranium.png' },
    { col: 'iron_mine',         name: 'Iron Mine',         icon: '/static/Emojis/Resources/iron.png' },
    { col: 'bauxite_mine',      name: 'Bauxite Mine',      icon: '/static/Emojis/Resources/bauxite.png' },
    { col: 'lead_mine',         name: 'Lead Mine',         icon: '/static/Emojis/Resources/lead.png' },
    { col: 'farm',              name: 'Farm',              icon: '/static/Emojis/Resources/food.png' }
  ],
  manufacturing: [
    { col: 'oil_refinery',      name: 'Oil Refinery',      icon: '/static/Emojis/Resources/gasoline.png' },
    { col: 'aluminum_refinery', name: 'Alu Refinery',      icon: '/static/Emojis/Resources/aluminum.png' },
    { col: 'steel_mill',        name: 'Steel Mill',        icon: '/static/Emojis/Resources/steel.png' },
    { col: 'munitions_factory', name: 'Munitions Factory', icon: '/static/Emojis/Resources/munitions.png' }
  ],
  civil: [
    { col: 'police_station',    name: 'Police Station',    icon: '/static/Emojis/Improvements/police.png' },
    { col: 'hospital',          name: 'Hospital',          icon: '/static/Emojis/Improvements/hospital.png' },
    { col: 'recycling_center',  name: 'Recycling Center',  icon: '/static/Emojis/Improvements/recycle.png' },
    { col: 'subway',            name: 'Subway',            icon: '/static/Emojis/Improvements/subway.png' }
  ],
  commerce: [
    { col: 'supermarket',       name: 'Supermarket',       icon: '/static/Emojis/Improvements/supermarket.png' },
    { col: 'bank',              name: 'Bank',              icon: '/static/Emojis/Improvements/bank.png' },
    { col: 'shopping_mall',     name: 'Shopping Mall',     icon: '/static/Emojis/Improvements/market.png' },
    { col: 'stadium',           name: 'Stadium',           icon: '/static/Emojis/Improvements/stadium.png' }
  ],
  // Factory is military — it enables tanks, uses the tank emoji
  military: [
    { col: 'barracks',          name: 'Barracks',          icon: '/static/Emojis/Military/soldier.png' },
    { col: 'factory',           name: 'Factory',           icon: '/static/Emojis/Military/tank.png' },
    { col: 'hangar',            name: 'Hangar',            icon: '/static/Emojis/Military/jet.png' },
    { col: 'drydock',           name: 'Drydock',           icon: '/static/Emojis/Military/ship.png' }
  ]
};

// All projects — matches the full list from the nations page.
// Only unowned ones are shown to the user in the editor.
const PROJECTS = {
  'Economic': [
    { col: 'activity_center',                     name: 'Activity Center' },
    { col: 'advanced_engineering_corps',           name: 'Advanced Engineering Corps' },
    { col: 'arable_land_agency',                   name: 'Arable Land Agency' },
    { col: 'bureau_of_domestic_affairs',           name: 'Bureau of Domestic Affairs' },
    { col: 'center_for_civil_engineering',         name: 'Center for Civil Engineering' },
    { col: 'government_support_agency',            name: 'Government Support Agency' },
    { col: 'international_trade_center',           name: 'International Trade Center' },
    { col: 'telecommunications_satellite',         name: 'Telecom Satellite' },
    { col: 'research_and_development_center',      name: 'R&D Center' }
  ],
  'Resource': [
    { col: 'arms_stockpile',                       name: 'Arms Stockpile' },
    { col: 'bauxite_works',                        name: 'Bauxite Works' },
    { col: 'emergency_gasoline_reserve',           name: 'Emergency Gasoline Reserve' },
    { col: 'green_technologies',                   name: 'Green Technologies' },
    { col: 'iron_works',                           name: 'Iron Works' },
    { col: 'mass_irrigation',                      name: 'Mass Irrigation' },
    { col: 'recycling_initiative',                 name: 'Recycling Initiative' },
    { col: 'uranium_enrichment_program',           name: 'Uranium Enrichment Program' },
    { col: 'clinical_research_center',             name: 'Clinical Research Center' },
    { col: 'specialized_police_training_program',  name: 'Spec. Police Training' }
  ],
  'Military': [
    { col: 'advanced_pirate_economy',              name: 'Advanced Pirate Economy' },
    { col: 'central_intelligence_agency',          name: 'CIA' },
    { col: 'fallout_shelter',                      name: 'Fallout Shelter' },
    { col: 'guiding_satellite',                    name: 'Guiding Satellite' },
    { col: 'iron_dome',                            name: 'Iron Dome' },
    { col: 'military_doctrine',                    name: 'Military Doctrine' },
    { col: 'military_research_center',             name: 'Military Research Center' },
    { col: 'military_salvage',                     name: 'Military Salvage' },
    { col: 'missile_launch_pad',                   name: 'Missile Launch Pad' },
    { col: 'nuclear_launch_facility',              name: 'Nuclear Launch Facility' },
    { col: 'nuclear_research_facility',            name: 'Nuclear Research Facility' },
    { col: 'pirate_economy',                       name: 'Pirate Economy' },
    { col: 'propaganda_bureau',                    name: 'Propaganda Bureau' },
    { col: 'space_program',                        name: 'Space Program' },
    { col: 'spy_satellite',                        name: 'Spy Satellite' },
    { col: 'surveillance_network',                 name: 'Surveillance Network' },
    { col: 'vital_defense_system',                 name: 'Vital Defense System' }
  ],
  'Space': [
    { col: 'moon_landing',                         name: 'Moon Landing' },
    { col: 'mars_landing',                         name: 'Mars Landing' }
  ]
};

// ═══════════════════════════════════════════════════════════════
// Main Render Function
// ═══════════════════════════════════════════════════════════════

async function renderPlanEditor(nationId, containerEl) {
  editorState = {
    nationId,
    nation: null,
    cities: [],
    planName: '',
    newCities: [],
    existingCities: [],
    projects: [],
    isDirty: false
  };
  
  containerEl.innerHTML = '<div class="plan-loading">Loading editor...</div>';
  
  try {
    // Try to use cached nation/cities data first
    if (window.currentPlanNation && window.currentPlanCities) {
      console.log('Using cached nation data');
      editorState.nation = window.currentPlanNation;
      editorState.cities = normalizeEditorCities(window.currentPlanCities || []);
    } else {
      // Load nation and city data from the API
      console.log('Fetching nation data from API');
      const nationResponse = await fetch(`/api/mynation/${nationId}`);
      if (!nationResponse.ok) {
        const errorText = await nationResponse.text();
        throw new Error(`Failed to load nation data: ${nationResponse.status} - ${errorText}`);
      }
      
      const bundleData = await nationResponse.json();
      editorState.nation = bundleData.nation;
      editorState.cities = normalizeEditorCities(bundleData.cities || []);
    }
    
    // Validate we have required data
    if (!editorState.nation) {
      throw new Error('Nation data not available');
    }
    
    console.log(`Loaded nation ${editorState.nation.nation_name || editorState.nation.id} with ${editorState.cities.length} cities`);
    
    // Load existing plan if it exists
    const planResponse = await fetch(`/api/mynation/plan/${nationId}`);
    if (planResponse.ok) {
      const planData = await planResponse.json();
      if (planData.plan) {
        editorState.planName = planData.plan.plan_name;
        editorState.newCities = planData.plan.plan_data.new_cities || [];
        editorState.existingCities = planData.plan.plan_data.existing_cities || [];
        editorState.projects = planData.plan.plan_data.projects || [];
        console.log('Loaded existing plan:', editorState.planName);
      }
    } else {
      console.log('No existing plan found, starting fresh');
    }
    
    // Render the editor
    renderEditorContent(containerEl);
    
  } catch (error) {
    console.error('Error rendering plan editor:', error);
    containerEl.innerHTML = `
      <div class="plan-error">
        <p>⚠️ Error loading editor</p>
        <p style="font-size: 0.9em; margin-top: 0.5rem;">Details: ${error.message}</p>
        <button onclick="location.reload()" style="margin-top: 1rem; padding: 0.5rem 1rem; cursor: pointer;">
          Reload Page
        </button>
      </div>
    `;
  }
}

function normalizeEditorCities(cities) {
  return (cities || []).map(city => {
    const cityId = city.city_id ?? city.id;
    return {
      ...city,
      city_id: Number(cityId),
      id: Number(city.id ?? cityId),
    };
  }).filter(city => Number.isFinite(city.city_id));
}

// ═══════════════════════════════════════════════════════════════
// Editor Content Renderer
// ═══════════════════════════════════════════════════════════════

function renderEditorContent(containerEl) {
  // Check if this is a new plan
  const isNewPlan = !editorState.planName && editorState.newCities.length === 0 && 
                    editorState.existingCities.length === 0 && editorState.projects.length === 0;
  
  const welcomeHeader = isNewPlan ? `
    <div class="plan-editor-welcome" style="
      background: linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%);
      border: 2px solid rgba(102, 126, 234, 0.3);
      border-radius: 8px;
      padding: 1.5rem;
      margin-bottom: 1.5rem;
      text-align: center;
    ">
      <h3 style="margin: 0 0 0.5rem 0; color: var(--gold-primary);">✨ Create Your Build Plan</h3>
      <p style="margin: 0; color: var(--text-secondary); font-size: 0.95rem;">
        Give your plan a name, then configure your existing cities, plan new cities, and select projects to build.
        Click "💾 Save Plan" when you're ready!
      </p>
    </div>
  ` : '';
  
  const html = `
    <div class="plan-editor">
      ${welcomeHeader}

      <!-- Live cost preview bar — updated on every edit -->
      <div id="live-cost-preview" class="plan-live-cost-bar">
        <span style="color:var(--text-secondary)">💰 Est. Total: calculating…</span>
      </div>
      
      <!-- Plan Name -->
      <div class="plan-form-group">
        <label class="plan-form-label">📋 Plan Name <span style="color: #e74c3c;">*</span></label>
        <input type="text" id="plan-name-input" class="plan-form-input" 
               placeholder="e.g., Road to c30 — full mil build" 
               value="${escapeHtml(editorState.planName)}"
               maxlength="100"
               onchange="editorState.planName = this.value; editorState.isDirty = true; scheduleLiveCostUpdate();"
               ${isNewPlan ? 'autofocus' : ''}>
        <small style="color: var(--text-secondary); font-size: 0.85rem; display: block; margin-top: 0.25rem;">
          Required — Give your plan a memorable name
        </small>
      </div>
      
      <!-- Existing Cities Section -->
      ${renderExistingCitiesEditor()}
      
      <!-- New Cities Section -->
      ${renderNewCitiesEditor()}
      
      <!-- Projects Section -->
      ${renderProjectsEditor()}
      
      <!-- Save Button -->
      <button class="plan-save-btn" onclick="savePlan()" style="
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
        width: 100%;
        margin-top: 1.5rem;
      " onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 6px 20px rgba(102, 126, 234, 0.6)'" 
         onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 4px 15px rgba(102, 126, 234, 0.4)'">
        💾 Save Plan
      </button>
      
      <div id="editor-status" style="margin-top: 1rem;"></div>
    </div>
  `;
  
  containerEl.innerHTML = html;

  // Trigger an immediate cost estimate now that the DOM is ready
  scheduleLiveCostUpdate();
}

// ═══════════════════════════════════════════════════════════════
// Existing Cities Editor
// ═══════════════════════════════════════════════════════════════

function renderExistingCitiesEditor() {
  if (!editorState.cities || editorState.cities.length === 0) {
    return '';
  }
  
  const citiesHtml = editorState.cities.map((city, idx) => {
    // Find if this city is in the plan
    let cityPlan = editorState.existingCities.find(c => c.city_id === city.city_id);
    if (!cityPlan) {
      // Initialize empty plan for this city - use actual city name
      const actualCityName = city.name || city.city_name || `City ${idx + 1}`;
      cityPlan = {
        city_id: city.city_id,
        city_name: actualCityName,
        target_infra: null,
        target_land: null,
        target_improvements: {}
      };
    }
    
    return renderExistingCityCard(city, cityPlan, idx);
  }).join('');
  
  return `
    <div class="plan-editor-section">
      <div class="plan-editor-section-header" onclick="toggleEditorSection(this)">
        <span>🏗️ Existing Cities (${editorState.cities.length} cities)</span>
        <span class="plan-chevron">▼</span>
      </div>
      <div class="plan-editor-section-body">
        ${citiesHtml}
      </div>
    </div>
  `;
}

function renderExistingCityCard(city, cityPlan, idx) {
  const currentInfra = city.infrastructure || 0;
  const currentLand  = city.land || 0;
  const targetInfra  = cityPlan.target_infra != null ? cityPlan.target_infra : currentInfra;
  const targetLand   = cityPlan.target_land  != null ? cityPlan.target_land  : currentLand;

  const actualCityName = city.name || city.city_name || `City ${idx + 1}`;
  const cityId = `existing-city-${idx}`;

  return `
    <div class="plan-city-editor-card" id="${cityId}">
      <div class="plan-city-editor-header" onclick="toggleCityEditor(this)">
        <span class="plan-city-editor-name">${escapeHtml(actualCityName)}</span>
        <span class="plan-city-editor-current">${currentInfra.toFixed(0)} infra · ${currentLand.toFixed(0)} land</span>
        <span class="plan-chevron">▼</span>
      </div>
      <div class="plan-city-editor-body">
        ${renderCityTileGrid(city, cityPlan, 'existing', idx, targetInfra, targetLand)}
      </div>
    </div>
  `;
}

// ═══════════════════════════════════════════════════════════════
// New Cities Editor
// ═══════════════════════════════════════════════════════════════

function renderNewCitiesEditor() {
  const currentCityCount = editorState.cities.length;
  
  const citiesHtml = editorState.newCities.map((cityPlan, idx) => {
    return renderNewCityCard(cityPlan, idx, currentCityCount);
  }).join('');
  
  return `
    <div class="plan-editor-section">
      <div class="plan-editor-section-header" onclick="toggleEditorSection(this)">
        <span>🏙️ New Cities (${editorState.newCities.length} planned)</span>
        <span class="plan-chevron">▼</span>
      </div>
      <div class="plan-editor-section-body">
        ${citiesHtml}
        <button class="plan-add-city-btn" onclick="addNewCity()">
          ➕ Add New City
        </button>
      </div>
    </div>
  `;
}

function renderNewCityCard(cityPlan, idx, currentCityCount) {
  const slot       = cityPlan.slot || (idx + 1);
  const cityNumber = currentCityCount + slot;
  const label      = cityPlan.label || `City ${cityNumber}`;
  const infra      = cityPlan.infra || 1000;
  const land       = cityPlan.land  || 500;

  const cityId = `new-city-${idx}`;

  return `
    <div class="plan-new-city-card" id="${cityId}">
      <div class="plan-new-city-header">
        <span class="plan-new-city-title">🏙️ <input type="text" class="plan-city-label-input"
          value="${escapeHtml(label)}" placeholder="City name…" maxlength="50"
          onchange="updateNewCityLabel(${idx}, this.value)"></span>
        <button class="plan-remove-city-btn" onclick="removeNewCity(${idx})">✕</button>
      </div>
      ${renderCityTileGrid(null, cityPlan, 'new', idx, infra, land)}
    </div>
  `;
}

// ═══════════════════════════════════════════════════════════════
// Compact Tile Grid  (Infra + Land + all improvements)
// ═══════════════════════════════════════════════════════════════

function renderCityTileGrid(city, cityPlan, type, idx, infraVal, landVal) {
  const improvements = cityPlan.improvements || cityPlan.target_improvements || {};

  // Slot accounting
  let slotsUsed = 0;
  for (const cnt of Object.values(improvements)) slotsUsed += (cnt || 0);
  const maxSlots   = calculateMaxSlots(infraVal || 10);
  const slotClass  = slotsUsed > maxSlots ? 'plan-slot-error' : (slotsUsed === maxSlots ? 'plan-slot-warning' : '');

  // Helper: one tile
  function tile({ emoji, label, value, subtext, onDec, onInc, onChange, min, max, step, wide }) {
    return `
      <div class="pct-tile${wide ? ' pct-tile--wide' : ''}">
        <div class="pct-tile-top">
          <span class="pct-tile-emoji">${emoji}</span>
          <span class="pct-tile-label">${label}</span>
        </div>
        ${subtext ? `<div class="pct-tile-sub">${subtext}</div>` : ''}
        <div class="pct-tile-controls">
          <button class="pct-btn" onclick="${onDec}">−</button>
          <input  class="pct-val" type="number" value="${value}"
                  min="${min}" max="${max}" step="${step || 1}"
                  onchange="${onChange}">
          <button class="pct-btn" onclick="${onInc}">+</button>
        </div>
      </div>`;
  }

  // ── Infra + Land tiles ──
  const infraSub  = city ? `now: ${(city.infrastructure || 0).toFixed(0)}` : '';
  const landSub   = city ? `now: ${(city.land || 0).toFixed(0)}` : '';

  let infraOnDec, infraOnInc, infraOnChange, landOnDec, landOnInc, landOnChange;
  if (type === 'existing') {
    const cid = city.city_id;
    infraOnChange = `updateExistingCityInfra(${cid},this.value)`;
    infraOnDec    = `(function(b){var v=Math.max(10,parseFloat(b.closest('.pct-tile').querySelector('.pct-val').value||0)-100);b.closest('.pct-tile').querySelector('.pct-val').value=v;updateExistingCityInfra(${cid},v)})(this)`;
    infraOnInc    = `(function(b){var v=Math.min(15000,parseFloat(b.closest('.pct-tile').querySelector('.pct-val').value||0)+100);b.closest('.pct-tile').querySelector('.pct-val').value=v;updateExistingCityInfra(${cid},v)})(this)`;
    landOnChange  = `updateExistingCityLand(${cid},this.value)`;
    landOnDec     = `(function(b){var v=Math.max(250,parseFloat(b.closest('.pct-tile').querySelector('.pct-val').value||0)-250);b.closest('.pct-tile').querySelector('.pct-val').value=v;updateExistingCityLand(${cid},v)})(this)`;
    landOnInc     = `(function(b){var v=Math.min(50000,parseFloat(b.closest('.pct-tile').querySelector('.pct-val').value||0)+250);b.closest('.pct-tile').querySelector('.pct-val').value=v;updateExistingCityLand(${cid},v)})(this)`;
  } else {
    infraOnChange = `updateNewCityInfra(${idx},this.value)`;
    infraOnDec    = `(function(b){var v=Math.max(10,parseFloat(b.closest('.pct-tile').querySelector('.pct-val').value||0)-100);b.closest('.pct-tile').querySelector('.pct-val').value=v;updateNewCityInfra(${idx},v)})(this)`;
    infraOnInc    = `(function(b){var v=Math.min(15000,parseFloat(b.closest('.pct-tile').querySelector('.pct-val').value||0)+100);b.closest('.pct-tile').querySelector('.pct-val').value=v;updateNewCityInfra(${idx},v)})(this)`;
    landOnChange  = `updateNewCityLand(${idx},this.value)`;
    landOnDec     = `(function(b){var v=Math.max(250,parseFloat(b.closest('.pct-tile').querySelector('.pct-val').value||0)-250);b.closest('.pct-tile').querySelector('.pct-val').value=v;updateNewCityLand(${idx},v)})(this)`;
    landOnInc     = `(function(b){var v=Math.min(50000,parseFloat(b.closest('.pct-tile').querySelector('.pct-val').value||0)+250);b.closest('.pct-tile').querySelector('.pct-val').value=v;updateNewCityLand(${idx},v)})(this)`;
  }

  let html = `<div class="pct-grid">`;

  // Infra tile (wide so the number input has room)
  html += tile({ emoji: '🏗️', label: 'Infrastructure', value: infraVal.toFixed(0),
                 subtext: infraSub, min: 10, max: 15000, step: 100, wide: true,
                 onDec: infraOnDec, onInc: infraOnInc, onChange: infraOnChange });
  // Land tile
  html += tile({ emoji: '🌾', label: 'Land', value: landVal.toFixed(0),
                 subtext: landSub, min: 250, max: 50000, step: 250, wide: true,
                 onDec: landOnDec, onInc: landOnInc, onChange: landOnChange });

  // ── Improvement tiles by category ──
  const CATEGORY_LABELS = {
    power:         '⚡ Power',
    mines:         '⛏️ Mines',
    manufacturing: '🏭 Mfg',
    civil:         '🏛️ Civil',
    commerce:      '🛒 Commerce',
    military:      '⚔️ Military'
  };

  for (const [category, impList] of Object.entries(IMPROVEMENTS)) {
    // Category separator
    html += `<div class="pct-category-sep">${CATEGORY_LABELS[category] || category}</div>`;

    for (const imp of impList) {
      const cur    = city ? (city[imp.col] || 0) : 0;
      const target = improvements[imp.col] || 0;
      const sub    = city ? `now: ${cur}` : '';

      const onDec    = `adjustImprovement('${type}',${idx},'${imp.col}',-1)`;
      const onInc    = `adjustImprovement('${type}',${idx},'${imp.col}',1)`;
      const onChange = `setImprovement('${type}',${idx},'${imp.col}',this.value)`;

      html += tile({ emoji: `<img src="${imp.icon}" class="pct-imp-icon" alt="">`,
                     label: imp.name, value: target, subtext: sub,
                     min: 0, max: 50, step: 1,
                     onDec, onInc, onChange });
    }
  }

  html += `</div>`;

  // Slot counter below the grid
  html += `
    <div class="pct-slot-bar">
      <span class="plan-slot-counter ${slotClass}" id="slot-counter-${type}-${idx}">
        🧱 ${slotsUsed} / ${maxSlots} slots used
      </span>
    </div>`;

  return html;
}

// Keep old entry point name so nothing else breaks
function renderImprovementsSection(city, cityPlan, type, idx) {
  const infra = type === 'existing'
    ? (cityPlan.target_infra != null ? cityPlan.target_infra : (city ? city.infrastructure : 0) || 0)
    : (cityPlan.infra || 10);
  const land  = type === 'existing'
    ? (cityPlan.target_land  != null ? cityPlan.target_land  : (city ? city.land : 0) || 0)
    : (cityPlan.land || 250);
  return renderCityTileGrid(city, cityPlan, type, idx, infra, land);
}

// ═══════════════════════════════════════════════════════════════
// Projects Editor
// ═══════════════════════════════════════════════════════════════

function renderProjectsEditor() {
  const selectedProjects = editorState.projects || [];
  const nation = editorState.nation || {};
  
  // Get owned projects
  const ownedProjects = [];
  for (const [category, projList] of Object.entries(PROJECTS)) {
    for (const proj of projList) {
      if (nation[proj.col]) {
        ownedProjects.push(proj.col);
      }
    }
  }
  
  // Selected projects HTML
  const selectedHtml = selectedProjects.map((projCol, idx) => {
    const isOwned = ownedProjects.includes(projCol);
    const projName = getProjectName(projCol);
    
    return `
      <div class="plan-project-item" draggable="true" 
           ondragstart="dragProjectStart(event, ${idx})"
           ondragover="dragProjectOver(event)"
           ondrop="dragProjectDrop(event, ${idx})">
        <span class="plan-project-drag">⠿</span>
        <span class="plan-project-num">${idx + 1}.</span>
        <span class="plan-project-label">${projName}</span>
        ${isOwned ? '<span class="plan-project-owned">✅ owned</span>' : ''}
        <button class="plan-project-remove" onclick="removeProject(${idx})">✕</button>
      </div>
    `;
  }).join('') || '<div class="plan-no-data">No projects selected. Click below to add.</div>';
  
  // Available projects HTML - ONLY SHOW UNOWNED PROJECTS
  let availableHtml = '';
  for (const [category, projList] of Object.entries(PROJECTS)) {
    // Filter to only unowned projects
    const unownedProjects = projList.filter(proj => !ownedProjects.includes(proj.col));
    
    // Skip category if all projects are owned
    if (unownedProjects.length === 0) continue;
    
    const chipsHtml = unownedProjects.map(proj => {
      const isSelected = selectedProjects.includes(proj.col);
      const chipClass = isSelected ? 'disabled' : '';
      
      return `
        <button class="plan-project-chip ${chipClass}" 
                onclick="addProject('${proj.col}')"
                ${isSelected ? 'disabled' : ''}>
          ${proj.name}
        </button>
      `;
    }).join('');
    
    availableHtml += `
      <div class="plan-project-category">
        <div class="plan-project-category-name">${category}:</div>
        <div class="plan-project-chips">
          ${chipsHtml}
        </div>
      </div>
    `;
  }
  
  const unownedCount = selectedProjects.filter(p => !ownedProjects.includes(p)).length;
  const limitWarning = unownedCount >= 5 ? '<div class="plan-warning">⚠️ Maximum 5 unowned projects reached</div>' : '';
  
  return `
    <div class="plan-editor-section">
      <div class="plan-editor-section-header" onclick="toggleEditorSection(this)">
        <span>🔬 Projects (${selectedProjects.length} selected, ${unownedCount} unowned)</span>
        <span class="plan-chevron">▼</span>
      </div>
      <div class="plan-editor-section-body">
        <div class="plan-projects-section">
          <div class="plan-projects-selected">
            <div class="plan-projects-title">📌 Selected Projects (in order):</div>
            ${limitWarning}
            <div class="plan-project-list" id="plan-project-list">
              ${selectedHtml}
            </div>
          </div>
          <div class="plan-projects-available">
            <div class="plan-projects-title">📦 Available Projects (click to add):</div>
            ${availableHtml}
          </div>
        </div>
      </div>
    </div>
  `;
}

// Continue in next message due to length...

// ═══════════════════════════════════════════════════════════════
// Event Handlers - Existing Cities
// ═══════════════════════════════════════════════════════════════

function updateExistingCityInfra(cityId, value) {
  const infra = parseFloat(value) || 0;
  if (infra < 10 || infra > 15000) {
    alert('Infrastructure must be between 10 and 15,000');
    return;
  }
  
  let cityPlan = editorState.existingCities.find(c => c.city_id === cityId);
  if (!cityPlan) {
    const city = editorState.cities.find(c => c.city_id === cityId);
    if (!city) return;
    
    cityPlan = {
      city_id: cityId,
      city_name: city.name || city.city_name || `City ${cityId}`,
      target_infra: null,
      target_land: null,
      target_improvements: {}
    };
    editorState.existingCities.push(cityPlan);
  }
  
  cityPlan.target_infra = infra;
  editorState.isDirty = true;
  
  // Update slot counter
  updateSlotCounter('existing', editorState.cities.findIndex(c => c.city_id === cityId));
  scheduleLiveCostUpdate();
}

function updateExistingCityLand(cityId, value) {
  const land = parseFloat(value) || 0;
  if (land < 250 || land > 50000) {
    alert('Land must be between 250 and 50,000');
    return;
  }
  
  let cityPlan = editorState.existingCities.find(c => c.city_id === cityId);
  if (!cityPlan) {
    const city = editorState.cities.find(c => c.city_id === cityId);
    if (!city) return;
    
    cityPlan = {
      city_id: cityId,
      city_name: city.name || city.city_name || `City ${cityId}`,
      target_infra: null,
      target_land: null,
      target_improvements: {}
    };
    editorState.existingCities.push(cityPlan);
  }
  
  cityPlan.target_land = land;
  editorState.isDirty = true;
  scheduleLiveCostUpdate();
}

// ═══════════════════════════════════════════════════════════════
// Event Handlers - New Cities
// ═══════════════════════════════════════════════════════════════

function addNewCity() {
  const slot = editorState.newCities.length + 1;
  const currentCityCount = editorState.cities.length;
  const cityNumber = currentCityCount + slot;
  
  editorState.newCities.push({
    slot: slot,
    label: `City ${cityNumber}`,
    land: 2000,
    infra: 2000,
    improvements: {}
  });
  
  editorState.isDirty = true;
  
  // Re-render new cities section
  const container = document.getElementById('plan-editor-area') || document.querySelector('#plan-tab-content');
  renderEditorContent(container);
}

function removeNewCity(idx) {
  if (confirm('Remove this city from the plan?')) {
    editorState.newCities.splice(idx, 1);
    
    // Renumber slots
    editorState.newCities.forEach((city, i) => {
      city.slot = i + 1;
    });
    
    editorState.isDirty = true;
    
    // Re-render
    const container = document.getElementById('plan-editor-area') || document.querySelector('#plan-tab-content');
    renderEditorContent(container);
  }
}

function updateNewCityLabel(idx, value) {
  if (editorState.newCities[idx]) {
    editorState.newCities[idx].label = value;
    editorState.isDirty = true;
  }
}

function updateNewCityInfra(idx, value) {
  const infra = parseFloat(value) || 0;
  if (infra < 10 || infra > 15000) {
    alert('Infrastructure must be between 10 and 15,000');
    return;
  }
  
  if (editorState.newCities[idx]) {
    editorState.newCities[idx].infra = infra;
    editorState.isDirty = true;
    
    // Update slot counter
    updateSlotCounter('new', idx);
    scheduleLiveCostUpdate();
  }
}

function updateNewCityLand(idx, value) {
  const land = parseFloat(value) || 0;
  if (land < 250 || land > 50000) {
    alert('Land must be between 250 and 50,000');
    return;
  }
  
  if (editorState.newCities[idx]) {
    editorState.newCities[idx].land = land;
    editorState.isDirty = true;
    scheduleLiveCostUpdate();
  }
}

// ═══════════════════════════════════════════════════════════════
// Event Handlers - Improvements
// ═══════════════════════════════════════════════════════════════

function adjustImprovement(type, idx, impCol, delta) {
  const current = getImprovementCount(type, idx, impCol);
  const newValue = Math.max(0, Math.min(50, current + delta));
  setImprovement(type, idx, impCol, newValue);
}

function setImprovement(type, idx, impCol, value) {
  const count = parseInt(value) || 0;
  
  if (count < 0 || count > 50) {
    alert('Improvement count must be between 0 and 50');
    return;
  }
  
  if (type === 'existing') {
    const city = editorState.cities[idx];
    if (!city) return;
    
    let cityPlan = editorState.existingCities.find(c => c.city_id === city.city_id);
    if (!cityPlan) {
      cityPlan = {
        city_id: city.city_id,
        city_name: city.name || city.city_name || `City ${city.city_id}`,
        target_infra: null,
        target_land: null,
        target_improvements: {}
      };
      editorState.existingCities.push(cityPlan);
    }
    
    if (!cityPlan.target_improvements) {
      cityPlan.target_improvements = {};
    }
    
    if (count > 0) {
      cityPlan.target_improvements[impCol] = count;
    } else {
      delete cityPlan.target_improvements[impCol];
    }
    
  } else if (type === 'new') {
    const cityPlan = editorState.newCities[idx];
    if (!cityPlan) return;
    
    if (!cityPlan.improvements) {
      cityPlan.improvements = {};
    }
    
    if (count > 0) {
      cityPlan.improvements[impCol] = count;
    } else {
      delete cityPlan.improvements[impCol];
    }
  }
  
  editorState.isDirty = true;
  
  // Update UI
  updateSlotCounter(type, idx);
  updateImprovementToggle(type, idx, impCol, count);
  scheduleLiveCostUpdate();
}

function getImprovementCount(type, idx, impCol) {
  if (type === 'existing') {
    const city = editorState.cities[idx];
    if (!city) return 0;
    
    const cityPlan = editorState.existingCities.find(c => c.city_id === city.city_id);
    return (cityPlan?.target_improvements?.[impCol]) || 0;
    
  } else if (type === 'new') {
    const cityPlan = editorState.newCities[idx];
    return (cityPlan?.improvements?.[impCol]) || 0;
  }
  
  return 0;
}

function updateSlotCounter(type, idx) {
  const counter = document.getElementById(`slot-counter-${type}-${idx}`);
  if (!counter) return;
  
  let infra, improvements;
  
  if (type === 'existing') {
    const city = editorState.cities[idx];
    if (!city) return;
    
    const cityPlan = editorState.existingCities.find(c => c.city_id === city.city_id);
    infra = cityPlan?.target_infra || city.infrastructure || 0;
    improvements = cityPlan?.target_improvements || {};
    
  } else if (type === 'new') {
    const cityPlan = editorState.newCities[idx];
    if (!cityPlan) return;
    
    infra = cityPlan.infra || 10;
    improvements = cityPlan.improvements || {};
  }
  
  const maxSlots = calculateMaxSlots(infra);
  let slotsUsed = 0;
  for (const count of Object.values(improvements)) {
    slotsUsed += (count || 0);
  }
  
  counter.textContent = `${slotsUsed} / ${maxSlots} slots used`;
  counter.className = 'plan-slot-counter';
  if (slotsUsed > maxSlots) {
    counter.className += ' plan-slot-error';
  } else if (slotsUsed === maxSlots) {
    counter.className += ' plan-slot-warning';
  }
}

function updateImprovementToggle(type, idx, impCol, count) {
  // Update the .pct-val input for this specific improvement tile.
  // Tiles are identified by their inc-button onclick which contains
  // adjustImprovement('type', idx, 'col', 1)
  const allInputs = document.querySelectorAll('.pct-val');
  for (const input of allInputs) {
    const tile = input.closest('.pct-tile');
    if (!tile) continue;
    const incBtn = tile.querySelector('.pct-btn:last-child');
    if (!incBtn) continue;
    const onclickStr = incBtn.getAttribute('onclick') || '';
    if (onclickStr.includes(`'${type}'`) &&
        onclickStr.includes(`,${idx},`) &&
        onclickStr.includes(`'${impCol}'`)) {
      input.value = count;
      // Highlight tile border when non-zero
      tile.style.borderColor = count > 0 ? 'rgba(255,215,0,0.45)' : '';
      break;
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// Event Handlers - Projects
// ═══════════════════════════════════════════════════════════════

function addProject(projCol) {
  const nation = editorState.nation || {};
  
  // Check if already selected
  if (editorState.projects.includes(projCol)) {
    return;
  }
  
  // Count unowned projects
  const ownedProjects = [];
  for (const [category, projList] of Object.entries(PROJECTS)) {
    for (const proj of projList) {
      if (nation[proj.col]) {
        ownedProjects.push(proj.col);
      }
    }
  }
  
  const unownedCount = editorState.projects.filter(p => !ownedProjects.includes(p)).length;
  const isOwned = ownedProjects.includes(projCol);
  
  // Check 5 unowned limit
  if (!isOwned && unownedCount >= 5) {
    alert('Maximum 5 unowned projects allowed');
    return;
  }
  
  editorState.projects.push(projCol);
  editorState.isDirty = true;
  
  // Re-render projects section
  const container = document.getElementById('plan-editor-area') || document.querySelector('#plan-tab-content');
  renderEditorContent(container);
}

function removeProject(idx) {
  editorState.projects.splice(idx, 1);
  editorState.isDirty = true;
  
  // Re-render projects section
  const container = document.getElementById('plan-editor-area') || document.querySelector('#plan-tab-content');
  renderEditorContent(container);
}

// Drag and drop for projects
let draggedProjectIdx = null;

function dragProjectStart(event, idx) {
  draggedProjectIdx = idx;
  event.target.classList.add('dragging');
}

function dragProjectOver(event) {
  event.preventDefault();
}

function dragProjectDrop(event, targetIdx) {
  event.preventDefault();
  
  if (draggedProjectIdx === null || draggedProjectIdx === targetIdx) {
    return;
  }
  
  // Reorder projects
  const [removed] = editorState.projects.splice(draggedProjectIdx, 1);
  editorState.projects.splice(targetIdx, 0, removed);
  
  editorState.isDirty = true;
  draggedProjectIdx = null;
  
  // Re-render
  const container = document.getElementById('plan-editor-area') || document.querySelector('#plan-tab-content');
  renderEditorContent(container);
}

// ═══════════════════════════════════════════════════════════════
// Save Function
// ═══════════════════════════════════════════════════════════════

async function savePlan() {
  const statusEl = document.getElementById('editor-status');
  
  try {
    // Validate plan name
    if (!editorState.planName || editorState.planName.trim() === '') {
      statusEl.innerHTML = `
        <div class="plan-error" style="
          background: rgba(231, 76, 60, 0.1);
          border: 2px solid #e74c3c;
          border-radius: 8px;
          padding: 1rem;
          color: #e74c3c;
          font-weight: 600;
        ">
          ⚠️ Please enter a plan name in the field above
        </div>
      `;
      // Scroll to and focus the plan name input
      const nameInput = document.getElementById('plan-name-input');
      if (nameInput) {
        nameInput.focus();
        nameInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
      return;
    }
    
    // Clean up existing cities (remove empty ones)
    const cleanedExisting = editorState.existingCities.filter(city => {
      const hasInfra = city.target_infra !== null;
      const hasLand = city.target_land !== null;
      const hasImprovements = city.target_improvements && Object.keys(city.target_improvements).length > 0;
      return hasInfra || hasLand || hasImprovements;
    });
    
    // Validate slot limits
    for (const city of cleanedExisting) {
      const cityData = editorState.cities.find(c => c.city_id === city.city_id);
      if (!cityData) continue;
      
      const infra = city.target_infra || cityData.infrastructure || 0;
      const maxSlots = calculateMaxSlots(infra);
      
      let slotsUsed = 0;
      for (const count of Object.values(city.target_improvements || {})) {
        slotsUsed += (count || 0);
      }
      
      if (slotsUsed > maxSlots) {
        statusEl.innerHTML = `
          <div class="plan-error" style="
            background: rgba(231, 76, 60, 0.1);
            border: 2px solid #e74c3c;
            border-radius: 8px;
            padding: 1rem;
            color: #e74c3c;
            font-weight: 600;
          ">
            ⚠️ ${city.city_name}: Too many improvements (${slotsUsed}) for infra level (max ${maxSlots} slots)
          </div>
        `;
        return;
      }
    }
    
    // Validate new cities
    for (const city of editorState.newCities) {
      const maxSlots = calculateMaxSlots(city.infra || 10);
      
      let slotsUsed = 0;
      for (const count of Object.values(city.improvements || {})) {
        slotsUsed += (count || 0);
      }
      
      if (slotsUsed > maxSlots) {
        statusEl.innerHTML = `
          <div class="plan-error" style="
            background: rgba(231, 76, 60, 0.1);
            border: 2px solid #e74c3c;
            border-radius: 8px;
            padding: 1rem;
            color: #e74c3c;
            font-weight: 600;
          ">
            ⚠️ ${city.label}: Too many improvements (${slotsUsed}) for infra level (max ${maxSlots} slots)
          </div>
        `;
        return;
      }
    }
    
    // Build plan data
    const planData = {
      nation_id: editorState.nationId,
      plan_name: editorState.planName.trim(),
      plan_data: {
        new_cities: editorState.newCities,
        existing_cities: cleanedExisting,
        projects: editorState.projects
      }
    };
    
    // Show saving status
    statusEl.innerHTML = `
      <div class="plan-loading" style="
        background: rgba(102, 126, 234, 0.1);
        border: 2px solid rgba(102, 126, 234, 0.5);
        border-radius: 8px;
        padding: 1rem;
        color: var(--gold-primary);
        font-weight: 600;
        text-align: center;
      ">
        💾 Saving your plan...
      </div>
    `;
    
    // POST to API
    const response = await fetch('/api/mynation/plan', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(planData)
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to save plan');
    }
    
    const result = await response.json();
    
    // Show success
    statusEl.innerHTML = `
      <div class="plan-success" style="
        background: rgba(46, 213, 115, 0.1);
        border: 2px solid #2ed573;
        border-radius: 8px;
        padding: 1rem;
        color: #2ed573;
        font-weight: 600;
        text-align: center;
      ">
        ✅ Plan saved successfully!
      </div>
    `;
    editorState.isDirty = false;

    // Refresh the viewer section (above the editor) to show updated costs/progress
    if (typeof refreshPlanViewer === 'function') {
      await refreshPlanViewer();
    }
    
  } catch (error) {
    console.error('Error saving plan:', error);
    statusEl.innerHTML = `
      <div class="plan-error" style="
        background: rgba(231, 76, 60, 0.1);
        border: 2px solid #e74c3c;
        border-radius: 8px;
        padding: 1rem;
        color: #e74c3c;
        font-weight: 600;
      ">
        ⚠️ Error saving plan: ${error.message}
        <br><small style="font-weight: 400; margin-top: 0.5rem; display: block;">
          Please check your internet connection and try again. If the problem persists, contact support.
        </small>
      </div>
    `;
  }
}

// ═══════════════════════════════════════════════════════════════
// Live Cost Preview
// ═══════════════════════════════════════════════════════════════

// Debounce handle
let _liveCostTimer = null;

/**
 * Schedule a live cost update 300ms after the last edit.
 * Called from every state-mutation handler.
 */
function scheduleLiveCostUpdate() {
  clearTimeout(_liveCostTimer);
  _liveCostTimer = setTimeout(renderLiveCostPreview, 300);
}

/**
 * Client-side cost estimate that mirrors the backend logic closely enough
 * to give instant feedback without a round-trip.
 *
 * Uses:
 *  - window._planViewerData.sell_prices   for resource → $ conversion
 *  - IMPROVEMENT_CASH_COSTS / IMPROVEMENT_RESOURCE_COSTS from pnw_costs (exposed below)
 *  - Infra/land/city purchase formulae approximated client-side
 */
function renderLiveCostPreview() {
  const el = document.getElementById('live-cost-preview');
  if (!el) return;

  const sellPrices = (window._planViewerData && window._planViewerData.sell_prices) || {};
  const nation     = editorState.nation || {};
  const startCities = editorState.cities ? editorState.cities.length : (nation.num_cities || 0);

  // ── Client-side cost approximations ──────────────────────────────────────
  // These mirror the backend formulas in costs.py as closely as possible.

  // ── Discount helpers ──────────────────────────────────────────────────────
  // Mirrors calculate_project_discounts() in costs.py
  function getDiscounts(nation) {
    let infraRed = 0.0;
    let landRed  = 0.0;
    let polyMult = 1.0;  // BDA / GSA amplifier
    if (nation.center_for_civil_engineering) infraRed += 0.05;
    if (nation.advanced_engineering_corps)   { infraRed += 0.05; landRed += 0.05; }
    if (nation.arable_land_agency)           landRed  += 0.05;
    if (nation.bureau_of_domestic_affairs)   polyMult += 0.25;
    if (nation.government_support_agency)    polyMult += 0.50;
    return { infraRed, landRed, polyMult };
  }

  function infraCost(fromInfra, toInfra, nation) {
    if (toInfra <= fromInfra) return 0;
    // Midpoint approximation — accurate within ~2-3% vs. recursive formula
    const mid     = (fromInfra + toInfra) / 2;
    const perUnit = (Math.pow(Math.abs(mid - 10), 2.2) / 710) + 300;
    const raw     = perUnit * (toInfra - fromInfra);
    const { infraRed, polyMult } = getDiscounts(nation);
    // Always apply full policy discount (Urbanization baseline 5% × BDA/GSA multiplier)
    const baseAfterProjects = raw * (1 - infraRed);
    return baseAfterProjects * (1 - 0.05 * polyMult);
  }

  function landCost(fromLand, toLand, nation) {
    if (toLand <= fromLand) return 0;
    const mid     = (fromLand + toLand) / 2;
    const perUnit = 0.002 * (mid - 20) * (mid - 20) + 50;
    const raw     = perUnit * (toLand - fromLand);
    const { landRed, polyMult } = getDiscounts(nation);
    // Always apply full policy discount (Rapid Expansion baseline 5% × BDA/GSA multiplier)
    const baseAfterProjects = raw * (1 - landRed);
    return baseAfterProjects * (1 - 0.05 * polyMult);
  }

  function cityCost(cityNumber, nation) {
    // Exact formula from costs.py city_purchase_cost()
    const top20 = (window._planViewerData && window._planViewerData._top20) || 0;
    const adj   = cityNumber - (top20 / 4);
    const cost1 = 100000 * Math.pow(adj, 3) + 150000 * adj + 75000;
    const cost2 = cityNumber * cityNumber * 100000;
    const base  = Math.max(cost1, cost2);
    const { polyMult } = getDiscounts(nation);
    // Always apply full policy discount (Manifest Destiny baseline 5% × BDA/GSA multiplier)
    return base * (1 - 0.05 * polyMult);
  }

  // ── Improvement cost tables (exact values from war_calc.py) ───────────────
  const IMP_RES = {
    nuclear_power:     { steel: 100, aluminum: 50 },
    wind_power:        { aluminum: 30 },
    police_station:    { steel: 20 },
    hospital:          { aluminum: 25 },
    subway:            { steel: 50, aluminum: 25 },
    bank:              { steel: 5,  aluminum: 10 },
    shopping_mall:     { steel: 20, aluminum: 25 },
    stadium:           { steel: 40, aluminum: 50 },
    factory:           { aluminum: 5 },
    hangar:            { steel: 10 },
    drydock:           { aluminum: 20 },
  };
  // Exact cash costs from war_calc.py IMPROVEMENT_COSTS
  const IMP_CASH = {
    coal_power:           5000,
    oil_power:            7000,
    nuclear_power:      500000,
    wind_power:          30000,
    coal_mine:            1000,
    oil_well:             1500,
    uranium_mine:        25000,
    iron_mine:            9500,
    bauxite_mine:         9500,
    lead_mine:            7500,
    farm:                 1000,
    oil_refinery:        45000,
    steel_mill:          45000,
    aluminum_refinery:   30000,
    munitions_factory:   35000,
    police_station:      75000,
    hospital:           100000,
    recycling_center:   125000,
    subway:             250000,
    supermarket:          5000,
    bank:                15000,
    shopping_mall:       45000,
    stadium:            100000,
    barracks:             3000,
    factory:             15000,
    hangar:             100000,
    drydock:            250000,
  };

  // ── Accumulate costs ──────────────────────────────────────────────────────
  const totals = {}; // { cash, steel, aluminum, ... }
  function add(key, amt) { totals[key] = (totals[key] || 0) + amt; }

  // New cities
  for (const cp of editorState.newCities) {
    const slot    = cp.slot || 1;
    const cityNum = startCities + slot;
    add('cash', cityCost(cityNum, nation));
    add('cash', infraCost(10, cp.infra || 10, nation));
    add('cash', landCost(250, cp.land || 250, nation));
    for (const [impCol, cnt] of Object.entries(cp.improvements || {})) {
      if (!cnt) continue;
      add('cash', (IMP_CASH[impCol] || 0) * cnt);
      for (const [res, perUnit] of Object.entries(IMP_RES[impCol] || {})) {
        add(res, perUnit * cnt);
      }
    }
  }

  // Existing cities
  for (const cp of editorState.existingCities) {
    const city = editorState.cities.find(c => c.city_id === cp.city_id);
    if (!city) continue;
    if (cp.target_infra  != null) add('cash', infraCost(city.infrastructure || 0, cp.target_infra, nation));
    if (cp.target_land   != null) add('cash', landCost(city.land || 0, cp.target_land, nation));
    for (const [impCol, tgt] of Object.entries(cp.target_improvements || {})) {
      const cur   = city[impCol] || 0;
      const delta = tgt - cur;
      if (delta <= 0) continue;
      add('cash', (IMP_CASH[impCol] || 0) * delta);
      for (const [res, perUnit] of Object.entries(IMP_RES[impCol] || {})) {
        add(res, perUnit * delta);
      }
    }
  }

  // Projects — use data from viewer if available, else skip
  if (window._planViewerData && window._planViewerData.project_costs) {
    for (const pc of window._planViewerData.project_costs) {
      if (!editorState.projects.includes(pc.db_col)) continue;
      if (pc.is_owned) continue;
      for (const [k, v] of Object.entries(pc.costs || {})) {
        add(k, v);
      }
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────
  const html = renderInlineCost(totals, sellPrices);
  el.innerHTML = html
    ? `<span style="color:var(--text-secondary);margin-right:0.5rem;">💰 Est. Total:</span>${html}`
    : '<span style="color:var(--text-secondary);">No costs yet</span>';
}

// Hook all state mutations to trigger live preview.
// scheduleLiveCostUpdate() is called directly in each mutating handler.

function toggleEditorSection(headerEl) {
  const section = headerEl.parentElement;
  const body = section.querySelector('.plan-editor-section-body');
  const chevron = headerEl.querySelector('.plan-chevron');
  
  if (body.style.display === 'none') {
    body.style.display = 'block';
    chevron.textContent = '▼';
  } else {
    body.style.display = 'none';
    chevron.textContent = '▶';
  }
}

function toggleCityEditor(headerEl) {
  const card = headerEl.parentElement;
  const body = card.querySelector('.plan-city-editor-body');
  const chevron = headerEl.querySelector('.plan-chevron');
  
  if (body.classList.contains('expanded')) {
    body.classList.remove('expanded');
    chevron.textContent = '▶';
  } else {
    body.classList.add('expanded');
    chevron.textContent = '▼';
  }
}

// ═══════════════════════════════════════════════════════════════
// Utility Functions
// ═══════════════════════════════════════════════════════════════

function calculateMaxSlots(infra) {
  // PnW formula: each full 50 infra gives one slot. No bonus +1.
  // 976 infra → floor(976/50) = 19 slots. Max is 50.
  return Math.min(Math.floor(infra / 50), 50);
}

function getCategoryIcon(category) {
  const icons = {
    power: '⚡',
    resources: '🏭',
    commerce: '🏪',
    military: '⚔️',
    special: '💎'
  };
  return icons[category] || '📦';
}

function getProjectName(projCol) {
  for (const [category, projList] of Object.entries(PROJECTS)) {
    const proj = projList.find(p => p.col === projCol);
    if (proj) return proj.name;
  }
  return projCol.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

function nth(n) {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return s[(v - 20) % 10] || s[v] || s[0];
}

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

(function() {
  // State - Alliance-based approach
  let _universeData = null;
  let _selectedAlliances = new Set(); // Set of alliance IDs that are selected
  let _visibleAlliances = new Set(); // Set of all visible alliance IDs (selected + their allies)
  
  // Autocomplete state
  let _acData = null; // { alliances: [...] }
  let _acIdx = -1;
  
  // Treaty type colors
  const TREATY_COLORS = {
    'Protectorate': '#ff6464',
    'Extension': '#c83232',
    'MDoAP': '#6464ff',
    'MDP': '#3232c8',
    'ODoAP': '#ffff96',
    'ODP': '#c8c864',
    'PIAT': '#96ff96',
    'NAP': '#64c864'
  };
  
  // Normalize treaty type
  function normalizeTreatyType(ttype) {
    const t = (ttype || '').toLowerCase().replace(/[\s-]/g, '');
    const map = {
      'protectorate': 'Protectorate',
      'extension': 'Extension',
      'mdoap': 'MDoAP',
      'mdp': 'MDP',
      'odoap': 'ODoAP',
      'odp': 'ODP',
      'piat': 'PIAT',
      'nap': 'NAP'
    };
    return map[t] || 'NAP';
  }
  
  // Fetch universe data
  async function fetchUniverse() {
    const res = await fetch('/api/treaties/universe');
    if (!res.ok) throw new Error('Failed to fetch universe data');
    return await res.json();
  }
  
  // Fetch autocomplete data
  async function fetchAcData() {
    if (_acData) return _acData;
    try {
      const res = await fetch('/api/treaties/ac_data');
      _acData = await res.json();
    } catch (e) {
      console.error('[TreatyUniverse] Failed to fetch autocomplete data:', e);
      _acData = { alliances: [] };
    }
    return _acData;
  }
  
  // Position autocomplete dropdown using fixed positioning to escape parent overflow
  function positionDropdown() {
    const inp = document.getElementById('tu-alliance-input');
    const dd = document.getElementById('tu-ac-dropdown');
    if (!inp || !dd || dd.style.display === 'none') return;
    
    const inpRect = inp.getBoundingClientRect();
    
    // Use fixed positioning so dropdown can escape any parent overflow:hidden
    dd.style.position = 'fixed';
    dd.style.top = (inpRect.bottom + window.scrollY + 4) + 'px';
    dd.style.left = (inpRect.left + window.scrollX) + 'px';
    dd.style.width = inpRect.width + 'px';
    dd.style.zIndex = '9999';
  }
  
  // Build autocomplete dropdown
  function buildDropdown(val) {
    const dd = document.getElementById('tu-ac-dropdown');
    if (!dd) return;
    dd.innerHTML = '';
    _acIdx = -1;
    const items = [];
    const low = (val || '').toLowerCase().trim();
    
    if (_acData) {
      for (const a of (_acData.alliances || [])) {
        const name = (a.name || '').toLowerCase();
        if (!low || name.includes(low) || String(a.id).includes(low)) {
          if (!_visibleAlliances.has(String(a.id))) {
            items.push({ label: a.name, value: String(a.id), count: a.member_count });
          }
        }
        if (items.length >= 15) break;
      }
    }
    
    if (!items.length) {
      dd.style.display = 'none';
      return;
    }
    
    items.forEach((item, i) => {
      const el = document.createElement('div');
      el.className = 'tu-ac-item';
      el.innerHTML = `<span>${item.label}</span><span class="tu-ac-count">${item.count} members</span>`;
      el.addEventListener('mousedown', (ev) => {
        ev.preventDefault();
        document.getElementById('tu-alliance-input').value = '';
        dd.style.display = 'none';
        addAlliance(item.value);
      });
      dd.appendChild(el);
    });
    dd.style.display = 'block';
    dd.classList.add('open');
    positionDropdown();
  }
  
  // Initialize autocomplete
  function initAutocomplete() {
    const inp = document.getElementById('tu-alliance-input');
    const dd = document.getElementById('tu-ac-dropdown');
    if (!inp || !dd) {
      console.error('[TreatyUniverse] Autocomplete elements not found');
      return;
    }
    
    console.log('[TreatyUniverse] Setting up autocomplete event listeners');
    
    // Show dropdown on focus with all alliances (or filtered if text exists)
    inp.addEventListener('focus', async () => {
      console.log('[TreatyUniverse] Input focused, building dropdown');
      await fetchAcData();
      buildDropdown(inp.value.trim());
    });
    
    // Filter dropdown on input
    inp.addEventListener('input', async () => {
      await fetchAcData();
      buildDropdown(inp.value.trim());
    });
    
    window.addEventListener('scroll', positionDropdown, true);
    window.addEventListener('resize', positionDropdown);
    
    inp.addEventListener('keydown', (e) => {
      const items = dd.querySelectorAll('.tu-ac-item');
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        _acIdx = Math.min(_acIdx + 1, items.length - 1);
        items.forEach((el, i) => el.classList.toggle('active', i === _acIdx));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        _acIdx = Math.max(_acIdx - 1, 0);
        items.forEach((el, i) => el.classList.toggle('active', i === _acIdx));
      } else if (e.key === 'Enter') {
        if (_acIdx >= 0 && items[_acIdx]) {
          items[_acIdx].dispatchEvent(new MouseEvent('mousedown'));
        } else {
          dd.style.display = 'none';
        }
      } else if (e.key === 'Escape') {
        dd.style.display = 'none';
      }
    });
    
    document.addEventListener('click', (ev) => {
      if (!inp.contains(ev.target) && !dd.contains(ev.target)) {
        dd.style.display = 'none';
        dd.classList.remove('open');
      }
    });
  }
  
  // Render selected alliance tags (with remove button)
  function renderSelectedTags(data) {
    const tagsContainer = document.getElementById('tu-selected-tags');
    if (!tagsContainer) return;
    
    tagsContainer.innerHTML = '';
    
    _selectedAlliances.forEach(aid => {
      const alliance = data.alliances[aid];
      if (!alliance) return;
      
      const tag = document.createElement('span');
      tag.className = 'tu-alliance-tag';
      tag.innerHTML = `
        <span class="tu-tag-name">${alliance.name}</span>
        <button class="tu-tag-remove" data-aid="${aid}">&times;</button>
      `;
      
      tag.querySelector('.tu-tag-remove').addEventListener('click', () => {
        removeAlliance(aid);
      });
      
      tagsContainer.appendChild(tag);
    });
  }
  
  // Add alliance to selection
  function addAlliance(allianceId) {
    if (_visibleAlliances.has(allianceId)) {
      console.log(`[TreatyUniverse] Alliance ${allianceId} already visible`);
      return;
    }
    
    _selectedAlliances.add(allianceId);
    updateVisibleAlliances();
    renderUniverse(_universeData);
    renderSelectedTags(_universeData);
    
    // Refresh autocomplete dropdown to hide newly selected alliance
    const inp = document.getElementById('tu-alliance-input');
    if (inp) {
      buildDropdown(inp.value.trim());
    }
  }
  
  // Remove alliance from selection
  function removeAlliance(allianceId) {
    _selectedAlliances.delete(allianceId);
    updateVisibleAlliances();
    renderUniverse(_universeData);
    renderSelectedTags(_universeData);
    
    // Refresh autocomplete dropdown to show newly available alliance
    const inp = document.getElementById('tu-alliance-input');
    if (inp) {
      buildDropdown(inp.value.trim());
    }
  }
  
  // Update visible alliances (selected + their allies)
  function updateVisibleAlliances() {
    _visibleAlliances = new Set();
    
    _selectedAlliances.forEach(aid => {
      // Add the selected alliance
      _visibleAlliances.add(aid);
      
      // Add all its treaty partners
      _universeData.treaties.forEach(treaty => {
        const a1 = String(treaty.alliance1_id);
        const a2 = String(treaty.alliance2_id);
        
        if (a1 === aid) {
          _visibleAlliances.add(a2);
        } else if (a2 === aid) {
          _visibleAlliances.add(a1);
        }
      });
    });
    
    console.log('[TreatyUniverse] Visible alliances:', _visibleAlliances.size, Array.from(_visibleAlliances));
  }
  
  // Calculate positions using FULL canvas with elliptical distribution
  // Selected in center, allies fan out to use entire width AND height
  function calculatePositions(allianceCount, containerWidth, containerHeight) {
    if (allianceCount === 0) return {};
    
    const centerX = containerWidth / 2;
    const centerY = containerHeight / 2;
    
    // Use full dimensions with padding (allow elliptical spread)
    const maxX = (containerWidth / 2) - 80;  // Horizontal reach
    const maxY = (containerHeight / 2) - 80; // Vertical reach
    
    const positions = {};
    const selectedIds = Array.from(_selectedAlliances).filter(id => _visibleAlliances.has(id));
    const allyIds = Array.from(_visibleAlliances).filter(id => !_selectedAlliances.has(id));
    
    // Position selected alliances - spread them if multiple
    if (selectedIds.length === 1) {
      positions[selectedIds[0]] = { x: centerX, y: centerY };
    } else if (selectedIds.length > 1) {
      // Spread selected alliances in a small tight cluster near center
      const innerSpread = Math.min(80, 40 * selectedIds.length);
      selectedIds.forEach((aid, i) => {
        const angle = (i / selectedIds.length) * 2 * Math.PI - Math.PI / 2;
        positions[aid] = {
          x: centerX + innerSpread * 0.5 * Math.cos(angle),
          y: centerY + innerSpread * 0.5 * Math.sin(angle)
        };
      });
    }
    
    // Group allies by their primary connection
    const groupedAllies = new Map();
    selectedIds.forEach(sid => groupedAllies.set(sid, []));
    
    allyIds.forEach(aid => {
      const connectedTo = [];
      _universeData.treaties.forEach(treaty => {
        const a1 = String(treaty.alliance1_id);
        const a2 = String(treaty.alliance2_id);
        if (a1 === aid && _selectedAlliances.has(a2)) {
          connectedTo.push(a2);
        } else if (a2 === aid && _selectedAlliances.has(a1)) {
          connectedTo.push(a1);
        }
      });
      
      if (connectedTo.length > 0 && groupedAllies.has(connectedTo[0])) {
        groupedAllies.get(connectedTo[0]).push(aid);
      } else if (selectedIds.length > 0) {
        groupedAllies.get(selectedIds[0]).push(aid);
      }
    });
    
    // Position allies using elliptical fan-out based on count
    const numSelected = selectedIds.length || 1;
    
    selectedIds.forEach((selectedId, selectedIndex) => {
      const group = groupedAllies.get(selectedId) || [];
      if (group.length === 0) return;
      
      // Calculate sector for this selected alliance
      const sectorAngle = (2 * Math.PI) / numSelected;
      const baseAngle = (selectedIndex * sectorAngle) - (Math.PI / 2);
      
      // How much of the sector to use (wider spread when fewer groups)
      const sectorSpread = numSelected === 1 ? 2 * Math.PI : sectorAngle * 0.9;
      
      group.forEach((aid, i) => {
        // Calculate position to maximize spread
        // Use golden angle for even distribution, but bias toward edges
        const goldenAngle = Math.PI * (3 - Math.sqrt(5)); // ~137.5 degrees
        
        // Mix of golden angle and sector-based positioning
        const angleOffset = (i * goldenAngle) % sectorSpread;
        const angle = baseAngle + angleOffset - (sectorSpread / 2);
        
        // Calculate radius - push to edges when few, fill rings when many
        const totalInGroup = group.length;
        let radiusFactor;
        
        if (totalInGroup <= 6) {
          // Few allies - push them far out (80-100% of max)
          radiusFactor = 0.75 + (0.25 * (i / Math.max(totalInGroup - 1, 1)));
        } else if (totalInGroup <= 15) {
          // Medium - spread across middle range (50-100%)
          radiusFactor = 0.5 + (0.5 * (i / Math.max(totalInGroup - 1, 1)));
        } else {
          // Many - fill multiple rings
          const ringSize = 8;
          const ring = Math.floor(i / ringSize);
          const maxRings = Math.ceil(totalInGroup / ringSize);
          radiusFactor = 0.35 + (0.65 * (ring / Math.max(maxRings - 1, 1)));
        }
        
        // Apply radius with elliptical scaling
        const radiusX = maxX * radiusFactor;
        const radiusY = maxY * radiusFactor;
        
        positions[aid] = {
          x: centerX + radiusX * Math.cos(angle),
          y: centerY + radiusY * Math.sin(angle)
        };
      });
    });
    
    return positions;
  }
  
  // Render the universe
  function renderUniverse(data) {
    const container = document.getElementById('tu-universe');
    if (!container) return;
    
    console.log('[TreatyUniverse] Rendering universe, visible alliances:', _visibleAlliances.size);
    
    // Hide loading spinner if it exists
    const loading = document.getElementById('tu-loading');
    if (loading) loading.style.display = 'none';
    
    // Clear existing content (but preserve loading element if we want to reuse it)
    container.innerHTML = '';
    
    if (_visibleAlliances.size === 0) {
      container.innerHTML = `
        <div class="tu-empty-state">
          <p><strong>Click the search box above</strong> and type to find alliances</p>
          <p style="font-size: 0.9rem; opacity: 0.8; margin-top: 0.5rem;">
            Selected alliances appear in the center with their treaty partners around them
          </p>
        </div>
      `;
      updateStats(data);
      return;
    }
    
    // Create SVG for treaty lines
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.style.position = 'absolute';
    svg.style.top = '0';
    svg.style.left = '0';
    svg.style.width = '100%';
    svg.style.height = '100%';
    svg.style.pointerEvents = 'none';
    svg.style.zIndex = '1';
    container.appendChild(svg);
    
    // Calculate positions
    const positions = calculatePositions(
      _visibleAlliances.size,
      container.offsetWidth,
      container.offsetHeight
    );
    
    // Draw treaty lines first (behind flags)
    const visibleAllianceIds = Array.from(_visibleAlliances);
    const drawnPairs = new Set();
    
    data.treaties.forEach(treaty => {
      const a1 = String(treaty.alliance1_id);
      const a2 = String(treaty.alliance2_id);
      
      // Only draw if both alliances are visible
      if (!_visibleAlliances.has(a1) || !_visibleAlliances.has(a2)) {
        return;
      }
      
      // Avoid duplicate lines
      const pairKey = [a1, a2].sort().join('-');
      if (drawnPairs.has(pairKey)) return;
      drawnPairs.add(pairKey);
      
      const pos1 = positions[a1];
      const pos2 = positions[a2];
      if (!pos1 || !pos2) return;
      
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', pos1.x);
      line.setAttribute('y1', pos1.y);
      line.setAttribute('x2', pos2.x);
      line.setAttribute('y2', pos2.y);
      
      const ttype = normalizeTreatyType(treaty.treaty_type);
      line.classList.add('tu-treaty-line', `tu-${ttype.toLowerCase()}`);
      
      svg.appendChild(line);
    });
    
    // Draw alliance flags
    visibleAllianceIds.forEach(aid => {
      const alliance = data.alliances[aid];
      if (!alliance) return;
      
      const pos = positions[aid];
      if (!pos) return;
      
      const isSelected = _selectedAlliances.has(aid);
      const flagEl = createAllianceElement(alliance, pos, isSelected);
      container.appendChild(flagEl);
    });
    
    updateStats(data);
  }
  
  // Create alliance element
  function createAllianceElement(alliance, pos, isSelected) {
    const el = document.createElement('div');
    el.className = 'tu-alliance';
    if (isSelected) {
      el.classList.add('tu-selected');
    }
    // Center the element at the position (pos is center of grid cell)
    el.style.left = `${pos.x}px`;
    el.style.top = `${pos.y}px`;
    el.style.transform = 'translate(-50%, -50%)';
    el.style.zIndex = '10';
    
    const flagSize = alliance.flag_size || 48;
    const flagUrl = window.ImageUtils ? window.ImageUtils.proxyImageUrl(alliance.flag) : alliance.flag;
    
    el.innerHTML = `
      <div class="tu-flag-container" style="width: ${flagSize}px; height: ${flagSize}px;">
        <img src="${flagUrl}" 
             alt="${alliance.name}"
             class="tu-flag"
             style="width: 100%; height: 100%; object-fit: cover;"
             onerror="this.style.display='none'">
      </div>
      <div class="tu-alliance-name">${alliance.name}</div>
    `;
    
    // Click to show details
    el.addEventListener('click', () => {
      showModal(alliance);
    });
    
    // Hover effects - need to maintain the translate transform while scaling
    el.addEventListener('mouseenter', () => {
      el.style.transform = 'translate(-50%, -50%) scale(1.1)';
      el.style.filter = 'drop-shadow(0 0 8px var(--tu-gold-glow))';
    });
    
    el.addEventListener('mouseleave', () => {
      el.style.transform = 'translate(-50%, -50%)';
      el.style.filter = '';
    });
    
    return el;
  }
  
  // Show modal
  function showModal(alliance) {
    const modal = document.getElementById('tu-modal');
    const title = document.getElementById('tu-modal-title');
    const body = document.getElementById('tu-modal-body');
    
    if (!modal || !title || !body) return;
    
    title.textContent = alliance.name;
    body.innerHTML = `
      <div style="text-align:center;margin-bottom:1rem">
        <img src="${window.ImageUtils ? window.ImageUtils.proxyImageUrl(alliance.flag) : alliance.flag}" 
             style="width:80px;height:80px;border-radius:50%;border:2px solid var(--gold-primary)">
      </div>
      <div class="tu-modal-stats">
        <div><strong>Total Score:</strong> ${alliance.total_score.toLocaleString()}</div>
        <div><strong>Average Score:</strong> ${alliance.avg_score.toLocaleString()}</div>
        <div><strong>Member Count:</strong> ${alliance.member_count.toLocaleString()}</div>
      </div>
    `;
    
    modal.style.display = 'flex';
  }
  
  // Update stats
  function updateStats(data) {
    const totalAlliances = document.getElementById('tu-total-alliances');
    const totalTreaties = document.getElementById('tu-total-treaties');
    const visibleCount = document.getElementById('tu-visible-count');
    
    if (totalAlliances) {
      totalAlliances.textContent = Object.keys(data.alliances).length;
    }
    if (totalTreaties) {
      totalTreaties.textContent = data.treaties.length;
    }
    if (visibleCount) {
      visibleCount.textContent = _visibleAlliances.size;
    }
  }
  
  // Initialize
  async function init() {
    try {
      console.log('[TreatyUniverse] Starting initialization...');
      
      // Wait for container to exist in DOM first
      let retries = 0;
      while (!document.getElementById('tu-alliance-input') && retries < 50) {
        await new Promise(resolve => setTimeout(resolve, 50));
        retries++;
      }
      
      if (!document.getElementById('tu-alliance-input')) {
        console.error('[TreatyUniverse] Input not found after 50 retries');
        return;
      }
      
      console.log('[TreatyUniverse] DOM ready, fetching data...');
      
      // Fetch autocomplete data first
      await fetchAcData();
      console.log('[TreatyUniverse] Autocomplete data loaded:', {
        alliances: _acData ? _acData.alliances.length : 0
      });
      
      // Fetch universe data
      _universeData = await fetchUniverse();
      console.log('[TreatyUniverse] Universe data loaded:', {
        alliances: Object.keys(_universeData.alliances).length,
        treaties: _universeData.treaties.length
      });
      
      console.log('[TreatyUniverse] Initializing autocomplete...');
      initAutocomplete();
      
      console.log('[TreatyUniverse] Rendering universe...');
      renderUniverse(_universeData);
      updateStats(_universeData);
      
      console.log('[TreatyUniverse] Initialization complete');
    } catch (e) {
      console.error('[TreatyUniverse] Failed to load treaty universe:', e);
      const loading = document.getElementById('tu-loading');
      if (loading) {
        loading.innerHTML = '<p style="color:#e74c3c">Failed to load treaty universe</p>';
      }
    }
  }
  
  // Event listeners
  const refreshBtn = document.getElementById('tu-refresh');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', init);
  }
  
  const modalClose = document.getElementById('tu-modal-close');
  if (modalClose) {
    modalClose.addEventListener('click', () => {
      const modal = document.getElementById('tu-modal');
      if (modal) modal.style.display = 'none';
    });
  }
  
  // Wait for dashboardPageLoaded event (for SPA navigation)
  document.addEventListener('dashboardPageLoaded', function(e) {
    if (e.detail.page === 'treaty_universe') {
      console.log('[TreatyUniverse] dashboardPageLoaded event received');
      _acData = null; // Reset cached data on page reload
      _universeData = null;
      _selectedAlliances.clear();
      _visibleAlliances.clear();
      setTimeout(() => init(), 100);
    }
  });
  
  // Also try immediate init if page is already loaded (direct URL access)
  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    console.log('[TreatyUniverse] Page already loaded, initiating immediately');
    setTimeout(() => init(), 100);
  } else {
    document.addEventListener('DOMContentLoaded', () => {
      console.log('[TreatyUniverse] DOMContentLoaded, initiating');
      setTimeout(() => init(), 100);
    });
  }
})();

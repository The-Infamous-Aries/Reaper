var petsData = [];
var equipmentData = {};
var currentSort = {
    pets:           { field: 'name', direction: 'asc' },
    materials:      { field: 'name', direction: 'asc' },
    potions:        { field: 'name', direction: 'asc' },
    gems:           { field: 'name', direction: 'asc' },
    monsters:       { field: 'name', direction: 'asc' },
    rings:          { field: 'name', direction: 'asc' },
    equipment_sets: { field: 'set',  direction: 'asc' },
    weapons:        { field: 'set',  direction: 'asc' },
};
var currentViewType = 'cards'; // 'cards' or 'list'

// Category switching function
function switchCategory(category) {
    document.querySelectorAll('.category-toggle .btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelectorAll(`.category-toggle .btn[onclick="switchCategory('${category}')"]`).forEach(btn => {
        btn.classList.add('active');
    });
    document.querySelectorAll('.tab-pane').forEach(pane => {
        pane.classList.remove('show', 'active');
    });
    const newPane = document.getElementById(category);
    if (newPane) newPane.classList.add('show', 'active');

    renderSortBar(category);

    const renderMap = {
        pets: renderPets, materials: renderMaterials, potions: renderPotions,
        gems: renderGems, monsters: renderMonsters,
        rings: renderRings, equipment_sets: renderEquipmentSets, weapons: renderWeapons,
    };
    if (renderMap[category]) renderMap[category]();
}

// Sort bar definitions per category
const SORT_BARS = {
    pets:           [['name','Name'],['att','ATT'],['def','DEF'],['int','INT'],['dex','DEX'],['hap','HAP'],['ene','ENE']],
    materials:      [['name','Name'],['rarity','Rarity'],['att','ATT'],['def','DEF'],['dex','DEX']],
    gems:           [['name','Name'],['rarity','Rarity'],['int','INT'],['hap','HAP'],['ene','ENE']],
    monsters:       [['name','Name'],['rarity','Rarity'],['att','ATT'],['def','DEF'],['dex','DEX'],['int','INT'],['hap','HAP'],['ene','ENE']],
    potions:        [['name','Name'],['rarity','Rarity'],['boost','Boost']],
    rings:          [['name','Name'],['rarity','Rarity'],['att','ATT'],['def','DEF'],['int','INT'],['dex','DEX'],['hap','HAP'],['ene','ENE']],
    equipment_sets: [['set','Set Type'],['name','Name'],['rarity','Rarity']],
    weapons:        [['set','Set Type'],['name','Name'],['rarity','Rarity'],['att','ATT'],['dex','DEX'],['ene','ENE'],['int','INT']],
};

function renderSortBar(category) {
    const bar = document.getElementById('sort-bar');
    if (!bar) return;
    const defs = SORT_BARS[category] || [];
    if (!defs.length) { bar.innerHTML = ''; return; }
    const btns = defs.map(([field, label]) =>
        `<button class="btn btn-sm btn-primary sort-btn me-1 mb-1" data-sort-field="${field}" data-sort-label="${label}" onclick="toggleSort('${category}','${field}')">${label}</button>`
    ).join('');
    bar.innerHTML = `<div class="d-flex flex-wrap align-items-center gap-1">${btns}</div>`;
    updateSortButtons(category);
}

// Initial data load
async function init() {
    await loadPetsData();
    await loadEquipmentData();
    renderSortBar('pets');
    renderAll();
    updateSortButtons('pets');
}

init();

function setViewType(type) {
    currentViewType = type;
    document.querySelectorAll('.view-toggle .btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.textContent.toLowerCase() === type) btn.classList.add('active');
    });
    const activePane = document.querySelector('.tab-pane.active');
    if (!activePane) return;
    const renderMap = {
        pets: renderPets, materials: renderMaterials, potions: renderPotions,
        gems: renderGems, monsters: renderMonsters,
        rings: renderRings, equipment_sets: renderEquipmentSets, weapons: renderWeapons,
    };
    const fn = renderMap[activePane.id];
    if (fn) fn();
}

function toggleSort(category, field) {
    const current = currentSort[category];
    if (current.field === field) {
        current.direction = current.direction === 'asc' ? 'desc' : 'asc';
    } else {
        current.field = field;
        current.direction = 'asc';
    }
    const renderMap = {
        pets: renderPets, materials: renderMaterials, potions: renderPotions,
        gems: renderGems, monsters: renderMonsters,
        rings: renderRings, equipment_sets: renderEquipmentSets, weapons: renderWeapons,
    };
    if (renderMap[category]) renderMap[category]();
    updateSortButtons(category);
}

// Update button states to show current sort direction
function updateSortButtons(category) {
    const current = currentSort[category];
    if (!current) return;
    const buttons = document.querySelectorAll('#sort-bar .sort-btn');
    buttons.forEach(button => {
        const field = button.dataset.sortField;
        if (field === current.field) {
            const arrow = current.direction === 'asc' ? '↑' : '↓';
            button.innerHTML = `${button.dataset.sortLabel} ${arrow}`;
            button.classList.add('active');
        } else {
            button.innerHTML = button.dataset.sortLabel;
            button.classList.remove('active');
        }
    });
}

// Load pet data
async function loadPetsData() {
    try {
        const baseUrl = window.location.origin;
        const response = await fetch(`${baseUrl}/api/pets-data`);
        const data = await response.json();
        petsData = Object.entries(data.Pets).map(([name, pet]) => ({
            name,
            ...pet,
            totalStats: Object.values(pet.Stats).reduce((a, b) => a + b, 0)
        }));
        
        // Only touch the DOM if we're still on the pets page (not mypet page)
        if (!document.getElementById('petContainer')) return;

        // Hide the loading spinner in petContainer after data is loaded
        const petContainer = document.getElementById('petContainer');
        if (petContainer && petContainer.innerHTML.includes('spinner-border')) {
            petContainer.innerHTML = '';
        }
        
        renderPets();
        updateSortButtons('pets');
    } catch (error) {
        console.error('Error loading pets data:', error);
        if (!document.getElementById('petContainer')) return;
        document.getElementById('petContainer').innerHTML = 
            '<div class="col-12"><div class="alert alert-danger">Error loading pet data. Please try again later.</div></div>';
    }
}

// Load equipment data
async function loadEquipmentData() {
    try {
        console.log('Loading equipment data from API...');
        const baseUrl = window.location.origin;
        const response = await fetch(`${baseUrl}/api/equipment-data`);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        equipmentData = await response.json();
        console.log('Equipment data loaded:', equipmentData);
        
        // Add emoji paths for each item
        for (const category in equipmentData) {
            if (Array.isArray(equipmentData[category])) {
                equipmentData[category].forEach(item => {
                    if (item.emoji_file) {
                        item.emoji_path = `/static/Emojis/Pets/Equipment/${item.emoji_file}`;
                    }
                });
            }
        }

        // Hide the main loading spinner after all data is loaded
        const loadingSpinner = document.getElementById('loading-spinner');
        if (loadingSpinner) {
            loadingSpinner.style.display = 'none';
        }

    } catch (error) {
        console.error('Error loading equipment data:', error);
        const errorHtml = `
            <div class="col-12">
                <div class="alert alert-danger" role="alert">
                    <h5 class="alert-heading">Error Loading Equipment Data</h5>
                    <p>Failed to load equipment data: ${error.message}</p>
                </div>
            </div>
        `;
        
        // Show error in all containers
        const containers = [
            'materials-container','potions-container','gems-container','monsters-container',
            'rings-container','helmets-container','armor-container','boots-container','shields-container',
            'daggers-container','katanas-container','swords-container','axes-container','hammers-container','bows-container',
        ];
        containers.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.innerHTML = errorHtml;
        });
    }
}

// Render all categories
function renderAll() {
    renderPets(); renderMaterials(); renderPotions(); renderGems(); renderMonsters();
    renderRings(); renderEquipmentSets(); renderWeapons();
}

// Rarity color mapping
function getRarityColor(rarity) {
    const colors = {
        'Common': '#9e9e9e',
        'Uncommon': '#4caf50',
        'Rare': '#2196f3',
        'Epic': '#9c27b0',
        'Mythic': '#ff9800'
    };
    return colors[rarity] || '#9e9e9e';
}

// Render Pets
function renderPets() {
    if (!document.getElementById('petContainer')) return;
    const container = document.getElementById('petContainer');
    const sort = currentSort.pets;
    
    // Sort pets
    const sortedPets = [...petsData].sort((a, b) => {
        let aVal, bVal;
        
        switch (sort.field) {
            case 'name':
                aVal = a.name.toLowerCase();
                bVal = b.name.toLowerCase();
                break;
            case 'att':
                aVal = a.Stats.ATT;
                bVal = b.Stats.ATT;
                break;
            case 'def':
                aVal = a.Stats.DEF;
                bVal = b.Stats.DEF;
                break;
            case 'int':
                aVal = a.Stats.INT;
                bVal = b.Stats.INT;
                break;
            case 'dex':
                aVal = a.Stats.DEX;
                bVal = b.Stats.DEX;
                break;
            case 'hap':
                aVal = a.Stats.HAP;
                bVal = b.Stats.HAP;
                break;
            case 'ene':
                aVal = a.Stats.ENE;
                bVal = b.Stats.ENE;
                break;
        }
        
        if (sort.direction === 'asc') {
            return aVal > bVal ? 1 : -1;
        } else {
            return aVal < bVal ? 1 : -1;
        }
    });

    if (currentViewType === 'cards') {
        container.innerHTML = sortedPets.map(pet => `
            <div class="col-xl-3 col-lg-4 col-md-6 mb-2">
                <div class="card pet-card">
                    <div class="card-header text-center py-2">
                        <img src="/static/Emojis/Pets/${pet.name}.png" 
                             alt="${pet.name}" 
                             class="pet-emoji"
                             onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'">
                        <h6 class="mb-0 mt-1">${pet.name}</h6>
                    </div>
                    <div class="card-body">
                        <!-- Stats -->
                        <div class="mb-2">
                            <h6 class="text-primary mb-1 small">📊 Base Stats</h6>
                            <div class="row">
                                <div class="col-6">
                                    <div class="stat-item">
                                        <img src="/static/Emojis/Pets/Deco/ATT.png" alt="ATT" class="stat-emoji">
                                        <span class="${pet.Spec.includes('ATT') ? 'stat-special' : ''}">ATT: ${pet.Stats.ATT}</span>
                                    </div>
                                    <div class="stat-item">
                                        <img src="/static/Emojis/Pets/Deco/DEF.png" alt="DEF" class="stat-emoji">
                                        <span class="${pet.Spec.includes('DEF') ? 'stat-special' : ''}">DEF: ${pet.Stats.DEF}</span>
                                    </div>
                                    <div class="stat-item">
                                        <img src="/static/Emojis/Pets/Deco/INT.png" alt="INT" class="stat-emoji">
                                        <span class="${pet.Spec.includes('INT') ? 'stat-special' : ''}">INT: ${pet.Stats.INT}</span>
                                    </div>
                                </div>
                                <div class="col-6">
                                    <div class="stat-item">
                                        <img src="/static/Emojis/Pets/Deco/DEX.png" alt="DEX" class="stat-emoji">
                                        <span class="${pet.Spec.includes('DEX') ? 'stat-special' : ''}">DEX: ${pet.Stats.DEX}</span>
                                    </div>
                                    <div class="stat-item">
                                        <img src="/static/Emojis/Pets/Deco/HAP.png" alt="HAP" class="stat-emoji">
                                        <span class="${pet.Spec.includes('HAP') ? 'stat-special' : ''}">HAP: ${pet.Stats.HAP}</span>
                                    </div>
                                    <div class="stat-item">
                                        <img src="/static/Emojis/Pets/Deco/ENE.png" alt="ENE" class="stat-emoji">
                                        <span class="${pet.Spec.includes('ENE') ? 'stat-special' : ''}">ENE: ${pet.Stats.ENE}</span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Specialties -->
                        <div class="mb-2">
                            <h6 class="text-primary mb-1 small">⭐ Specialties</h6>
                            <div>
                                ${pet.Spec.map(spec => 
                                    `<span class="badge spec-badge">${spec}</span>`
                                ).join('')}
                            </div>
                        </div>

                        <!-- Description -->
                        <div class="mb-2">
                            <h6 class="text-primary mb-1 small">📝 Description</h6>
                            <p class="small mb-0 pet-description">${pet.Descriptions}</p>
                        </div>

                        <!-- Actions -->
                        <div>
                            <h6 class="text-primary mb-1 small">⚔️ Battle Actions</h6>
                            ${Object.entries(pet.Actions).map(([type, name]) => `
                                <div class="action-item">
                                    <div class="action-type">${type}:</div>
                                    <div class="action-name">${name}</div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            </div>
        `).join('');
    } else {
        // List view
        container.innerHTML = `
            <div class="col-12">
                <div class="table-responsive">
                    <table class="table table-dark table-striped">
                        <thead>
                            <tr>
                                <th>Pet</th>
                                <th>ATT</th>
                                <th>DEF</th>
                                <th>INT</th>
                                <th>DEX</th>
                                <th>HAP</th>
                                <th>ENE</th>
                                <th>Specialties</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${sortedPets.map(pet => `
                                <tr>
                                    <td>
                                        <img src="/static/Emojis/Pets/${pet.name}.png" 
                                             alt="${pet.name}" 
                                             style="width: 32px; height: 32px; object-fit: contain; margin-right: 8px;"
                                             onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'">
                                        ${pet.name}
                                    </td>
                                    <td class="${pet.Spec.includes('ATT') ? 'stat-special' : ''}">${pet.Stats.ATT}</td>
                                    <td class="${pet.Spec.includes('DEF') ? 'stat-special' : ''}">${pet.Stats.DEF}</td>
                                    <td class="${pet.Spec.includes('INT') ? 'stat-special' : ''}">${pet.Stats.INT}</td>
                                    <td class="${pet.Spec.includes('DEX') ? 'stat-special' : ''}">${pet.Stats.DEX}</td>
                                    <td class="${pet.Spec.includes('HAP') ? 'stat-special' : ''}">${pet.Stats.HAP}</td>
                                    <td class="${pet.Spec.includes('ENE') ? 'stat-special' : ''}">${pet.Stats.ENE}</td>
                                    <td>${pet.Spec.join(', ')}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }
}

// Render Materials
function renderMaterials() {
    const container = document.getElementById('materials-container');
    
    const materials = [...(equipmentData.Materials || [])];
    
    if (materials.length === 0) {
        container.innerHTML = '<div class="col-12"><p class="text-center text-muted">No materials found.</p></div>';
        return;
    }
    
    // Apply current sorting
    materials.sort(getSortFunction('materials'));
    
    if (currentViewType === 'cards') {
        container.innerHTML = materials.map(material => `
            <div class="col-md-3 col-lg-2 mb-2">
                <div class="card h-100" style="border-color: ${getRarityColor(material.rarity)};">
                    <div class="card-body text-center p-2">
                        <img src="${material.emoji_path}" 
                             alt="${material.name}" 
                             class="mb-1" 
                             style="width: 48px; height: 48px; object-fit: contain;"
                             onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                        <div style="display: none; color: red; font-size: 10px;">Image not found: ${material.emoji_file}</div>
                        <h6 class="card-title text-warning mb-1 small">${material.name}</h6>
                        <p class="card-text">
                            <span class="badge" style="background-color: ${getRarityColor(material.rarity)};">${material.rarity}</span>
                        </p>
                        <div class="row g-1">
                            ${material.bonuses?.ATT ? `<div class="col-6"><span class="text-danger fw-bold">ATT: +${material.bonuses.ATT}</span></div>` : ''}
                            ${material.bonuses?.DEF ? `<div class="col-6"><span class="text-primary fw-bold">DEF: +${material.bonuses.DEF}</span></div>` : ''}
                            ${material.bonuses?.DEX ? `<div class="col-6"><span class="text-success fw-bold">DEX: +${material.bonuses.DEX}</span></div>` : ''}
                        </div>
                    </div>
                </div>
            </div>
        `).join('');
    } else {
        // List view
        container.innerHTML = `
            <div class="col-12">
                <div class="table-responsive">
                    <table class="table table-dark table-striped">
                        <thead>
                            <tr>
                                <th>Material</th>
                                <th>Rarity</th>
                                <th>ATT</th>
                                <th>DEF</th>
                                <th>DEX</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${materials.map(material => `
                                <tr>
                                    <td>
                                        <img src="${material.emoji_path}" 
                                             alt="${material.name}" 
                                             style="width: 32px; height: 32px; object-fit: contain; margin-right: 8px;"
                                             onerror="this.style.display='none';">
                                        ${material.name}
                                    </td>
                                    <td><span class="badge" style="background-color: ${getRarityColor(material.rarity)};">${material.rarity}</span></td>
                                    <td>${material.bonuses?.ATT || '-'}</td>
                                    <td>${material.bonuses?.DEF || '-'}</td>
                                    <td>${material.bonuses?.DEX || '-'}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }
}

// Render Potions
function renderPotions() {
    const container = document.getElementById('potions-container');
    
    const potions = [...(equipmentData.Potions || [])];
    
    if (potions.length === 0) {
        container.innerHTML = '<div class="col-12"><p class="text-center text-muted">No potions found.</p></div>';
        return;
    }
    
    potions.sort(getSortFunction('potions'));
    
    if (currentViewType === 'cards') {
        container.innerHTML = potions.map(potion => {
            let boostInfo = '';
            if (potion.use_effect) {
                const effect = potion.use_effect;
                switch (effect.type) {
                    case 'attribute_boost':
                        boostInfo = `<p class="mb-1">+${effect.value} to ${effect.attribute}</p>`;
                        break;
                    case 'elemental_boost':
                        boostInfo = `
                            <p class="mb-1">+${effect.value_single} to 3 random stats (1 element)</p>
                            <p class="mb-1">+${effect.value_dual} to 4 random stats (2 elements)</p>
                            <small class="text-danger d-block mt-2">Only works if pet's element matches.</small>
                        `;
                        break;
                    case 'random_boost':
                        boostInfo = `<p class="mb-0">+${effect.value} to ${effect.count} random stats.</p>`;
                        break;
                    case 'luck_boost':
                        boostInfo = `<p class="mb-0">+${effect.min}-${effect.max} to ALL 6 attributes (random roll for each).</p>`;
                        break;
                    case 'mega_boost':
                        boostInfo = `<p class="mb-0">+${effect.value} to ALL 6 attributes.</p>`;
                        break;
                    case 'health_boost':
                        boostInfo = `<p class="mb-0">+${effect.value} to HAP & ENE attributes.</p>`;
                        break;
                    case 'xp_boost':
                        boostInfo = `
                            <p class="mb-1">Instantly gain ${effect.multiplier}x your pet's level in XP.</p>
                            <p class="mb-0">May trigger level ups with additional stat gains.</p>
                        `;
                        break;
                    default:
                        boostInfo = '<p class="mb-0 text-muted">No effect description available.</p>';
                }
            }

            return `
            <div class="col-md-3 col-lg-2 mb-2">
                <div class="card h-100" style="border-color: ${getRarityColor(potion.rarity)};">
                    <div class="card-body text-center p-2">
                        <img src="${potion.emoji_path}" 
                             alt="${potion.name}" 
                             class="mb-1" 
                             style="width: 48px; height: 48px; object-fit: contain;"
                             onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                        <div style="display: none; color: red; font-size: 10px;">Image not found</div>
                        <h6 class="card-title text-warning mb-1 small">${potion.name}</h6>
                        <p class="card-text"><span class="badge" style="background-color: ${getRarityColor(potion.rarity)};">${potion.rarity}</span></p>
                        <div class="card-text text-center text-warning mt-3" style="font-size: 0.95rem;">
                            ${boostInfo}
                        </div>
                    </div>
                </div>
            </div>
        `;
        }).join('');
    } else {
        // List view
        container.innerHTML = `
            <div class="col-12">
                <div class="table-responsive">
                    <table class="table table-dark table-striped">
                        <thead>
                            <tr>
                                <th>Potion</th>
                                <th>Rarity</th>
                                <th>Effect</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${potions.map(potion => {
                                let effectDesc = 'No effect';
                                if (potion.use_effect) {
                                    const effect = potion.use_effect;
                                    switch (effect.type) {
                                        case 'attribute_boost':
                                            effectDesc = `+${effect.value} ${effect.attribute}`;
                                            break;
                                        case 'elemental_boost':
                                            effectDesc = `+${effect.value_single}/+${effect.value_dual} elemental`;
                                            break;
                                        case 'random_boost':
                                            effectDesc = `+${effect.value} to ${effect.count} stats`;
                                            break;
                                        case 'luck_boost':
                                            effectDesc = `+${effect.min}-${effect.max} all stats`;
                                            break;
                                        case 'mega_boost':
                                            effectDesc = `+${effect.value} all stats`;
                                            break;
                                        case 'health_boost':
                                            effectDesc = `+${effect.value} HAP&ENE`;
                                            break;
                                        case 'xp_boost':
                                            effectDesc = `${effect.multiplier}x XP`;
                                            break;
                                    }
                                }
                                
                                return `
                                    <tr>
                                        <td>
                                            <img src="${potion.emoji_path}" 
                                                 alt="${potion.name}" 
                                                 style="width: 32px; height: 32px; object-fit: contain; margin-right: 8px;"
                                                 onerror="this.style.display='none';">
                                            ${potion.name}
                                        </td>
                                        <td><span class="badge" style="background-color: ${getRarityColor(potion.rarity)};">${potion.rarity}</span></td>
                                        <td>${effectDesc}</td>
                                    </tr>
                                `;
                            }).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }
}

// Render Gems
function renderGems() {
    const container = document.getElementById('gems-container');
    
    const gems = [...(equipmentData.Gems || [])];
    
    if (gems.length === 0) {
        container.innerHTML = '<div class="col-12"><p class="text-center text-muted">No gems found.</p></div>';
        return;
    }
    
    gems.sort(getSortFunction('gems'));
    
    if (currentViewType === 'cards') {
        container.innerHTML = gems.map(gem => `
            <div class="col-md-3 col-lg-2 mb-2">
                <div class="card h-100" style="border-color: ${getRarityColor(gem.rarity)};">
                    <div class="card-body text-center p-2">
                        <img src="${gem.emoji_path}" 
                             alt="${gem.name}" 
                             class="mb-1" 
                             style="width: 48px; height: 48px; object-fit: contain;"
                             onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                        <div style="display: none; color: red; font-size: 10px;">Image not found</div>
                        <h6 class="card-title text-warning mb-1 small">${gem.name}</h6>
                        <p class="card-text">
                            <span class="badge" style="background-color: ${getRarityColor(gem.rarity)};">${gem.rarity}</span>
                        </p>
                        <div class="row g-1">
                            ${gem.bonuses?.INT ? `<div class="col-6"><span style="color: #6f42c1;" class="fw-bold">INT: +${gem.bonuses.INT}</span></div>` : ''}
                            ${gem.bonuses?.HAP ? `<div class="col-6"><span style="color: #ffc107;" class="fw-bold">HAP: +${gem.bonuses.HAP}</span></div>` : ''}
                            ${gem.bonuses?.ENE ? `<div class="col-6"><span style="color: #0dcaf0;" class="fw-bold">ENE: +${gem.bonuses.ENE}</span></div>` : ''}
                        </div>
                    </div>
                </div>
            </div>
        `).join('');
    } else {
        // List view
        container.innerHTML = `
            <div class="col-12">
                <div class="table-responsive">
                    <table class="table table-dark table-striped">
                        <thead>
                            <tr>
                                <th>Gem</th>
                                <th>Rarity</th>
                                <th>INT</th>
                                <th>HAP</th>
                                <th>ENE</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${gems.map(gem => `
                                <tr>
                                    <td>
                                        <img src="${gem.emoji_path}" 
                                             alt="${gem.name}" 
                                             style="width: 32px; height: 32px; object-fit: contain; margin-right: 8px;"
                                             onerror="this.style.display='none';">
                                        ${gem.name}
                                    </td>
                                    <td><span class="badge" style="background-color: ${getRarityColor(gem.rarity)};">${gem.rarity}</span></td>
                                    <td>${gem.bonuses?.INT || '-'}</td>
                                    <td>${gem.bonuses?.HAP || '-'}</td>
                                    <td>${gem.bonuses?.ENE || '-'}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }
}

// Render Monsters
function renderMonsters() {
    const container = document.getElementById('monsters-container');
    
    const monsters = [...(equipmentData.Monsters || [])];
    
    if (monsters.length === 0) {
        container.innerHTML = '<div class="col-12"><p class="text-center text-muted">No monsters found.</p></div>';
        return;
    }
    
    monsters.sort(getSortFunction('monsters'));
    
    if (currentViewType === 'cards') {
        container.innerHTML = monsters.map(monster => `
            <div class="col-md-3 col-lg-2 mb-2">
                <div class="card h-100" style="border-color: ${getRarityColor(monster.rarity)};">
                    <div class="card-body text-center p-2">
                        <img src="${monster.emoji_path}" 
                             alt="${monster.name}" 
                             class="mb-1" 
                             style="width: 48px; height: 48px; object-fit: contain;"
                             onerror="this.style.display='none'; this.nextElementSibling.style.display='block';">
                        <div style="display: none; color: red; font-size: 10px;">Image not found</div>
                        <h6 class="card-title text-warning mb-1">${monster.name}</h6>
                        <p class="card-text">
                            <span class="badge" style="background-color: ${getRarityColor(monster.rarity)};">${monster.rarity}</span>
                        </p>
                        <div class="row g-1">
                            ${monster.bonuses?.ATT ? `<div class="col-6"><span class="text-danger fw-bold">ATT: +${monster.bonuses.ATT}</span></div>` : ''}
                            ${monster.bonuses?.DEF ? `<div class="col-6"><span class="text-primary fw-bold">DEF: +${monster.bonuses.DEF}</span></div>` : ''}
                            ${monster.bonuses?.DEX ? `<div class="col-6"><span class="text-success fw-bold">DEX: +${monster.bonuses.DEX}</span></div>` : ''}
                            ${monster.bonuses?.INT ? `<div class="col-6"><span style="color: #6f42c1;" class="fw-bold">INT: +${monster.bonuses.INT}</span></div>` : ''}
                            ${monster.bonuses?.HAP ? `<div class="col-6"><span style="color: #ffc107;" class="fw-bold">HAP: +${monster.bonuses.HAP}</span></div>` : ''}
                            ${monster.bonuses?.ENE ? `<div class="col-6"><span style="color: #0dcaf0;" class="fw-bold">ENE: +${monster.bonuses.ENE}</span></div>` : ''}
                        </div>
                    </div>
                </div>
            </div>
        `).join('');
    } else {
        // List view
        container.innerHTML = `
            <div class="col-12">
                <div class="table-responsive">
                    <table class="table table-dark table-striped">
                        <thead>
                            <tr>
                                <th>Monster</th>
                                <th>Rarity</th>
                                <th>ATT</th>
                                <th>DEF</th>
                                <th>DEX</th>
                                <th>INT</th>
                                <th>HAP</th>
                                <th>ENE</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${monsters.map(monster => `
                                <tr>
                                    <td>
                                        <img src="${monster.emoji_path}" 
                                             alt="${monster.name}" 
                                             style="width: 32px; height: 32px; object-fit: contain; margin-right: 8px;"
                                             onerror="this.style.display='none';">
                                        ${monster.name}
                                    </td>
                                    <td><span class="badge" style="background-color: ${getRarityColor(monster.rarity)};">${monster.rarity}</span></td>
                                    <td>${monster.bonuses?.ATT || '-'}</td>
                                    <td>${monster.bonuses?.DEF || '-'}</td>
                                    <td>${monster.bonuses?.DEX || '-'}</td>
                                    <td>${monster.bonuses?.INT || '-'}</td>
                                    <td>${monster.bonuses?.HAP || '-'}</td>
                                    <td>${monster.bonuses?.ENE || '-'}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }
}

// ── Generic gear renderer (Armor, Boots, Helmets, Shields, Rings, weapons) ──────
function renderGearCategory(category, sectionKey, statCols) {
    const container = document.getElementById(category + '-container');
    if (!container) return;
    // Ensure sort state exists for this category
    if (!currentSort[category]) currentSort[category] = { field: 'name', direction: 'asc' };
    const items = [...(equipmentData[sectionKey] || [])];
    if (!items.length) {
        container.innerHTML = '<div class="col-12"><p class="text-center text-muted">No items found.</p></div>';
        return;
    }
    items.sort(getSortFunction(category));

    const statColor = { ATT:'#e74c3c', DEF:'#2196f3', DEX:'#4caf50', INT:'#6f42c1', HAP:'#ffc107', ENE:'#0dcaf0' };

    if (currentViewType === 'cards') {
        container.innerHTML = items.map(item => {
            const bonusHtml = Object.entries(item.bonuses || {}).map(([k,v]) =>
                `<div class="col-6"><span style="color:${statColor[k]||'#fff'}" class="fw-bold">${k}: +${v}</span></div>`
            ).join('');
            const setTag = item.set ? `<span class="badge bg-secondary ms-1" style="font-size:0.6rem">${item.set}</span>` : '';
            return `
            <div class="col-md-3 col-lg-2 mb-2">
                <div class="card h-100" style="border-color:${getRarityColor(item.rarity)}">
                    <div class="card-body text-center p-2">
                        <img src="${item.emoji_path}" alt="${item.name}" class="mb-1"
                             style="width:48px;height:48px;object-fit:contain"
                             onerror="this.style.display='none'">
                        <h6 class="card-title text-warning mb-1 small">${item.name}${setTag}</h6>
                        <p class="card-text"><span class="badge" style="background-color:${getRarityColor(item.rarity)}">${item.rarity}</span></p>
                        <div class="row g-1">${bonusHtml}</div>
                    </div>
                </div>
            </div>`;
        }).join('');
    } else {
        const headers = statCols.map(s => `<th>${s}</th>`).join('');
        const rows = items.map(item => {
            const cells = statCols.map(s => `<td>${item.bonuses?.[s] || '-'}</td>`).join('');
            return `<tr>
                <td><img src="${item.emoji_path}" alt="${item.name}" style="width:28px;height:28px;object-fit:contain;margin-right:6px" onerror="this.style.display='none'">${item.name}${item.set ? ` <small class="text-secondary">[${item.set}]</small>` : ''}</td>
                <td><span class="badge" style="background-color:${getRarityColor(item.rarity)}">${item.rarity}</span></td>
                ${cells}
            </tr>`;
        }).join('');
        container.innerHTML = `<div class="col-12"><div class="table-responsive">
            <table class="table table-dark table-striped">
                <thead><tr><th>Item</th><th>Rarity</th>${headers}</tr></thead>
                <tbody>${rows}</tbody>
            </table></div></div>`;
    }
}

function renderRings()   { renderGearCategory('rings',   'Rings',   ['ATT','DEF','INT','DEX','HAP','ENE']); }

// ── Equipment Sets: Helmets + Armor + Boots + Shields grouped by set ──────────
function renderEquipmentSets() {
    const container = document.getElementById('equipment_sets-container');
    if (!container) return;
    if (!currentSort['equipment_sets']) currentSort['equipment_sets'] = { field: 'set', direction: 'asc' };

    // Collect all items from the 4 gear sections, tagging each with its slot type
    const GEAR_SECTIONS = [
        { key: 'Helmets', label: 'Helmet', icon: '⛑️' },
        { key: 'Armor',   label: 'Armor',  icon: '🛡️' },
        { key: 'Boots',   label: 'Boots',  icon: '👢' },
        { key: 'Shields', label: 'Shield', icon: '🔰' },
    ];
    let allItems = [];
    GEAR_SECTIONS.forEach(({ key, label, icon }) => {
        (equipmentData[key] || []).forEach(item => {
            allItems.push({ ...item, _slotLabel: label, _slotIcon: icon });
        });
    });

    if (!allItems.length) {
        container.innerHTML = '<p class="text-center text-muted mt-3">No equipment found.</p>';
        return;
    }

    const sort = currentSort['equipment_sets'];
    allItems.sort((a, b) => {
        let aVal, bVal;
        if (sort.field === 'set') {
            // Primary: set tag, secondary: slot type, tertiary: name
            const aSet = a.set || 'zzz';
            const bSet = b.set || 'zzz';
            if (aSet !== bSet) return sort.direction === 'asc' ? aSet.localeCompare(bSet) : bSet.localeCompare(aSet);
            if (a._slotLabel !== b._slotLabel) return a._slotLabel.localeCompare(b._slotLabel);
            return a.name.localeCompare(b.name);
        } else if (sort.field === 'name') {
            aVal = a.name.toLowerCase(); bVal = b.name.toLowerCase();
        } else if (sort.field === 'rarity') {
            const ro = { Common:1, Uncommon:2, Rare:3, Epic:4, Mythic:5 };
            aVal = ro[a.rarity] || 0; bVal = ro[b.rarity] || 0;
        } else {
            aVal = (a.bonuses || {})[sort.field.toUpperCase()] || 0;
            bVal = (b.bonuses || {})[sort.field.toUpperCase()] || 0;
        }
        return sort.direction === 'asc' ? (aVal < bVal ? -1 : aVal > bVal ? 1 : 0)
                                        : (aVal > bVal ? -1 : aVal < bVal ? 1 : 0);
    });

    const statColor = { ATT:'#e74c3c', DEF:'#2196f3', DEX:'#4caf50', INT:'#6f42c1', HAP:'#ffc107', ENE:'#0dcaf0' };

    if (sort.field === 'set' && currentViewType === 'cards') {
        // Group by set — show each set as a labelled section with 4 cards side by side
        const groups = {};
        allItems.forEach(item => {
            const g = item.set || 'No Set';
            if (!groups[g]) groups[g] = [];
            groups[g].push(item);
        });
        const setOrder = Object.keys(groups).sort();
        let html = '';
        setOrder.forEach(setName => {
            html += `<div class="mb-4">
                <h6 class="text-warning mb-2" style="font-family:Orbitron,sans-serif;font-size:0.8rem;letter-spacing:1px;border-bottom:1px solid rgba(255,215,0,0.2);padding-bottom:4px">
                    ✨ ${setName} Set
                </h6>
                <div class="row g-2">`;
            groups[setName].forEach(item => {
                const bonusHtml = Object.entries(item.bonuses || {}).map(([k,v]) =>
                    `<span style="color:${statColor[k]||'#fff'}" class="fw-bold me-2">${k}:+${v}</span>`
                ).join('');
                html += `<div class="col-md-3 col-sm-6">
                    <div class="card h-100" style="border-color:${getRarityColor(item.rarity)}">
                        <div class="card-body text-center p-2">
                            <div style="font-size:0.65rem;color:var(--text-secondary);margin-bottom:2px">${item._slotIcon} ${item._slotLabel}</div>
                            <img src="${item.emoji_path}" alt="${item.name}" style="width:44px;height:44px;object-fit:contain" onerror="this.style.display='none'">
                            <h6 class="card-title text-warning mb-1 mt-1" style="font-size:0.78rem">${item.name}</h6>
                            <span class="badge mb-1" style="background-color:${getRarityColor(item.rarity)}">${item.rarity}</span>
                            <div style="font-size:0.7rem">${bonusHtml}</div>
                        </div>
                    </div>
                </div>`;
            });
            html += '</div></div>';
        });
        container.innerHTML = html;
    } else {
        // List view or non-set sort — flat table
        const rows = allItems.map(item => {
            const bonusHtml = Object.entries(item.bonuses || {}).map(([k,v]) =>
                `<span style="color:${statColor[k]||'#fff'}" class="me-1">${k}:+${v}</span>`
            ).join('');
            return `<tr>
                <td>${item._slotIcon} ${item._slotLabel}</td>
                <td><img src="${item.emoji_path}" alt="${item.name}" style="width:28px;height:28px;object-fit:contain;margin-right:6px" onerror="this.style.display='none'">${item.name}</td>
                <td><span class="badge" style="background-color:${getRarityColor(item.rarity)}">${item.rarity}</span></td>
                <td>${item.set || '-'}</td>
                <td style="font-size:0.8rem">${bonusHtml}</td>
            </tr>`;
        }).join('');
        container.innerHTML = `<div class="table-responsive">
            <table class="table table-dark table-striped table-sm">
                <thead><tr><th>Slot</th><th>Item</th><th>Rarity</th><th>Set</th><th>Bonuses</th></tr></thead>
                <tbody>${rows}</tbody>
            </table></div>`;
    }
}

// ── Weapons: Daggers + Katanas + Swords + Axes + Hammers + Bows grouped by set ─
function renderWeapons() {
    const container = document.getElementById('weapons-container');
    if (!container) return;
    if (!currentSort['weapons']) currentSort['weapons'] = { field: 'set', direction: 'asc' };

    const WEAPON_SECTIONS = [
        { key: 'Daggers', label: 'Dagger', icon: '🗡️' },
        { key: 'Katanas', label: 'Katana', icon: '⚔️' },
        { key: 'Swords',  label: 'Sword',  icon: '🗡️' },
        { key: 'Axes',    label: 'Axe',    icon: '🪓' },
        { key: 'Hammers', label: 'Hammer', icon: '🔨' },
        { key: 'Bows',    label: 'Bow',    icon: '🏹' },
    ];
    let allItems = [];
    WEAPON_SECTIONS.forEach(({ key, label, icon }) => {
        (equipmentData[key] || []).forEach(item => {
            allItems.push({ ...item, _slotLabel: label, _slotIcon: icon });
        });
    });

    if (!allItems.length) {
        container.innerHTML = '<p class="text-center text-muted mt-3">No weapons found.</p>';
        return;
    }

    const sort = currentSort['weapons'];
    allItems.sort((a, b) => {
        let aVal, bVal;
        if (sort.field === 'set') {
            const aSet = a.set || 'zzz';
            const bSet = b.set || 'zzz';
            if (aSet !== bSet) return sort.direction === 'asc' ? aSet.localeCompare(bSet) : bSet.localeCompare(aSet);
            if (a._slotLabel !== b._slotLabel) return a._slotLabel.localeCompare(b._slotLabel);
            return a.name.localeCompare(b.name);
        } else if (sort.field === 'name') {
            aVal = a.name.toLowerCase(); bVal = b.name.toLowerCase();
        } else if (sort.field === 'rarity') {
            const ro = { Common:1, Uncommon:2, Rare:3, Epic:4, Mythic:5 };
            aVal = ro[a.rarity] || 0; bVal = ro[b.rarity] || 0;
        } else {
            aVal = (a.bonuses || {})[sort.field.toUpperCase()] || 0;
            bVal = (b.bonuses || {})[sort.field.toUpperCase()] || 0;
        }
        return sort.direction === 'asc' ? (aVal < bVal ? -1 : aVal > bVal ? 1 : 0)
                                        : (aVal > bVal ? -1 : aVal < bVal ? 1 : 0);
    });

    const statColor = { ATT:'#e74c3c', DEF:'#2196f3', DEX:'#4caf50', INT:'#6f42c1', HAP:'#ffc107', ENE:'#0dcaf0' };

    if (sort.field === 'set' && currentViewType === 'cards') {
        // Group by set — show each set as a labelled section
        const groups = {};
        allItems.forEach(item => {
            const g = item.set || 'No Set';
            if (!groups[g]) groups[g] = [];
            groups[g].push(item);
        });
        const setOrder = Object.keys(groups).sort();
        let html = '';
        setOrder.forEach(setName => {
            html += `<div class="mb-4">
                <h6 class="text-warning mb-2" style="font-family:Orbitron,sans-serif;font-size:0.8rem;letter-spacing:1px;border-bottom:1px solid rgba(255,215,0,0.2);padding-bottom:4px">
                    ⚔️ ${setName} Weapons
                </h6>
                <div class="row g-2">`;
            groups[setName].forEach(item => {
                const bonusHtml = Object.entries(item.bonuses || {}).map(([k,v]) =>
                    `<span style="color:${statColor[k]||'#fff'}" class="fw-bold me-2">${k}:+${v}</span>`
                ).join('');
                html += `<div class="col-md-2 col-sm-4 col-6">
                    <div class="card h-100" style="border-color:${getRarityColor(item.rarity)}">
                        <div class="card-body text-center p-2">
                            <div style="font-size:0.65rem;color:var(--text-secondary);margin-bottom:2px">${item._slotIcon} ${item._slotLabel}</div>
                            <img src="${item.emoji_path}" alt="${item.name}" style="width:44px;height:44px;object-fit:contain" onerror="this.style.display='none'">
                            <h6 class="card-title text-warning mb-1 mt-1" style="font-size:0.75rem">${item.name}</h6>
                            <span class="badge mb-1" style="background-color:${getRarityColor(item.rarity)}">${item.rarity}</span>
                            <div style="font-size:0.7rem">${bonusHtml}</div>
                        </div>
                    </div>
                </div>`;
            });
            html += '</div></div>';
        });
        container.innerHTML = html;
    } else {
        const rows = allItems.map(item => {
            const bonusHtml = Object.entries(item.bonuses || {}).map(([k,v]) =>
                `<span style="color:${statColor[k]||'#fff'}" class="me-1">${k}:+${v}</span>`
            ).join('');
            return `<tr>
                <td>${item._slotIcon} ${item._slotLabel}</td>
                <td><img src="${item.emoji_path}" alt="${item.name}" style="width:28px;height:28px;object-fit:contain;margin-right:6px" onerror="this.style.display='none'">${item.name}</td>
                <td><span class="badge" style="background-color:${getRarityColor(item.rarity)}">${item.rarity}</span></td>
                <td>${item.set || '-'}</td>
                <td style="font-size:0.8rem">${bonusHtml}</td>
            </tr>`;
        }).join('');
        container.innerHTML = `<div class="table-responsive">
            <table class="table table-dark table-striped table-sm">
                <thead><tr><th>Type</th><th>Item</th><th>Rarity</th><th>Set</th><th>Bonuses</th></tr></thead>
                <tbody>${rows}</tbody>
            </table></div>`;
    }
}

// Sorting functions
function getSortFunction(category) {
    const sort = currentSort[category];
    return (a, b) => {
        let aVal, bVal;
        
        switch (sort.field) {
            case 'name':
                aVal = a.name.toLowerCase();
                bVal = b.name.toLowerCase();
                break;
            case 'rarity':
                const rarityOrder = { 'Common': 1, 'Uncommon': 2, 'Rare': 3, 'Epic': 4, 'Mythic': 5 };
                aVal = rarityOrder[a.rarity] || 0;
                bVal = rarityOrder[b.rarity] || 0;
                break;
            case 'set':
                aVal = (a.set || 'zzz').toLowerCase();
                bVal = (b.set || 'zzz').toLowerCase();
                break;
            case 'att':
                aVal = a.bonuses?.ATT || 0;
                bVal = b.bonuses?.ATT || 0;
                break;
            case 'def':
                aVal = a.bonuses?.DEF || 0;
                bVal = b.bonuses?.DEF || 0;
                break;
            case 'dex':
                aVal = a.bonuses?.DEX || 0;
                bVal = b.bonuses?.DEX || 0;
                break;
            case 'int':
                aVal = a.bonuses?.INT || 0;
                bVal = b.bonuses?.INT || 0;
                break;
            case 'hap':
                aVal = a.bonuses?.HAP || 0;
                bVal = b.bonuses?.HAP || 0;
                break;
            case 'ene':
                aVal = a.bonuses?.ENE || 0;
                bVal = b.bonuses?.ENE || 0;
                break;
            case 'boost':
                // For potions - get the main boost value
                if (a.use_effect) {
                    const effect = a.use_effect;
                    if (effect.type === 'attribute_boost') aVal = effect.value;
                    else if (effect.type === 'elemental_boost') aVal = effect.value_single;
                    else if (effect.type === 'random_boost') aVal = effect.value;
                    else if (effect.type === 'luck_boost') aVal = effect.max;
                    else if (effect.type === 'mega_boost') aVal = effect.value;
                    else if (effect.type === 'health_boost') aVal = effect.value;
                    else if (effect.type === 'xp_boost') aVal = effect.multiplier;
                    else aVal = 0;
                } else aVal = 0;
                
                if (b.use_effect) {
                    const effect = b.use_effect;
                    if (effect.type === 'attribute_boost') bVal = effect.value;
                    else if (effect.type === 'elemental_boost') bVal = effect.value_single;
                    else if (effect.type === 'random_boost') bVal = effect.value;
                    else if (effect.type === 'luck_boost') bVal = effect.max;
                    else if (effect.type === 'mega_boost') bVal = effect.value;
                    else if (effect.type === 'health_boost') bVal = effect.value;
                    else if (effect.type === 'xp_boost') bVal = effect.multiplier;
                    else bVal = 0;
                } else bVal = 0;
                break;
            default:
                return 0;
        }
        
        if (sort.direction === 'asc') {
            return aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
        } else {
            return aVal > bVal ? -1 : aVal < bVal ? 1 : 0;
        }
    };
}

// Initialize the page
    // Listen for dashboard page loaded event to initialize the page
    document.addEventListener('dashboardPageLoaded', function(event) {
        console.log('Dashboard page loaded event received for:', event.detail.page);
        if (event.detail.page.includes('pets.html')) {
            console.log('Initializing unified pets page...');
            const spinner = document.getElementById('loading-spinner');
            if (spinner) spinner.style.display = 'none';
            loadPetsData().then(() => {
                renderSortBar('pets');
                updateSortButtons('pets');
            });
            loadEquipmentData();
            initializeCategoryButtonEffects();
        }
    });

// Enhanced category button effects
function initializeCategoryButtonEffects() {
    const categoryButtons = document.querySelectorAll('.category-toggle .btn');
    
    categoryButtons.forEach(button => {
        // Add click ripple effect
        button.addEventListener('click', function(e) {
            // Remove any existing ripples
            const existingRipples = this.querySelectorAll('.ripple');
            existingRipples.forEach(ripple => ripple.remove());
            
            // Create ripple element
            const ripple = document.createElement('span');
            ripple.classList.add('ripple');
            
            // Calculate ripple position and size
            const rect = this.getBoundingClientRect();
            const size = Math.max(rect.width, rect.height);
            const x = e.clientX - rect.left - size / 2;
            const y = e.clientY - rect.top - size / 2;
            
            ripple.style.width = ripple.style.height = size + 'px';
            ripple.style.left = x + 'px';
            ripple.style.top = y + 'px';
            
            // Add ripple styles
            ripple.style.cssText += `
                position: absolute;
                border-radius: 50%;
                background: radial-gradient(circle, rgba(255, 215, 0, 0.6) 0%, transparent 70%);
                transform: scale(0);
                animation: rippleEffect 0.6s ease-out;
                pointer-events: none;
                z-index: 1000;
            `;
            
            this.appendChild(ripple);
            
            // Remove ripple after animation
            setTimeout(() => {
                if (ripple.parentNode) {
                    ripple.parentNode.removeChild(ripple);
                }
            }, 600);
        });
        
        // Add hover sound effect (visual feedback)
        button.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-3px) scale(1.05)';
            
            // Create sparkle effect
            createSparkleEffect(this);
        });
        
        button.addEventListener('mouseleave', function() {
            if (!this.classList.contains('active')) {
                this.style.transform = '';
            }
        });
        
        // Add keyboard navigation enhancement
        button.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                this.click();
                
                // Add keyboard activation effect
                this.style.transform = 'translateY(-1px) scale(0.98)';
                setTimeout(() => {
                    if (this.classList.contains('active')) {
                        this.style.transform = 'translateY(-2px) scale(1.08)';
                    } else {
                        this.style.transform = '';
                    }
                }, 100);
            }
        });
    });
    
    // Add ripple animation to CSS
    const style = document.createElement('style');
    style.textContent = `
        @keyframes rippleEffect {
            0% {
                transform: scale(0);
                opacity: 1;
            }
            100% {
                transform: scale(4);
                opacity: 0;
            }
        }
        
        @keyframes sparkleEffect {
            0% {
                transform: translate(-50%, -50%) scale(0) rotate(0deg);
                opacity: 1;
            }
            50% {
                transform: translate(-50%, -50%) scale(1) rotate(180deg);
                opacity: 0.8;
            }
            100% {
                transform: translate(-50%, -50%) scale(0) rotate(360deg);
                opacity: 0;
            }
        }
    `;
    document.head.appendChild(style);
}

// Create sparkle effect on hover
function createSparkleEffect(button) {
    const sparkleCount = 3;
    
    for (let i = 0; i < sparkleCount; i++) {
        setTimeout(() => {
            const sparkle = document.createElement('span');
            sparkle.classList.add('sparkle');
            
            const rect = button.getBoundingClientRect();
            const x = Math.random() * rect.width;
            const y = Math.random() * rect.height;
            
            sparkle.style.cssText = `
                position: absolute;
                left: ${x}px;
                top: ${y}px;
                width: 4px;
                height: 4px;
                background: radial-gradient(circle, #ffd700 0%, transparent 70%);
                border-radius: 50%;
                pointer-events: none;
                animation: sparkleEffect 0.8s ease-out;
                z-index: 999;
            `;
            
            button.appendChild(sparkle);
            
            setTimeout(() => {
                if (sparkle.parentNode) {
                    sparkle.parentNode.removeChild(sparkle);
                }
            }, 800);
        }, i * 100);
    }
}
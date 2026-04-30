/**
 * Battle Settings UI Component
 * ===========================
 * 
 * Provides a comprehensive interface for users to customize their battle formulas.
 * Supports single-player settings and PvP/Boss room configurations.
 */

class BattleSettingsUI {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        this.options = {
            mode: 'singleplayer', // 'singleplayer' or 'pvp'
            roomId: null,
            onSave: null,
            onTest: null,
            ...options
        };
        
        this.currentSettings = null;
        this.presets = {};
        this.availableStats = [];
        this.testResults = null;
        
        this.init();
    }
    
    async init() {
        try {
            console.log('Initializing battle settings UI...');
            await this.loadAvailableStats();
            console.log('Available stats loaded:', this.availableStats);
            await this.loadPresets();
            console.log('Presets loaded:', Object.keys(this.presets));
            await this.loadCurrentSettings();
            console.log('Current settings loaded:', this.currentSettings);
            this.render();
            console.log('Battle settings UI rendered successfully');
        } catch (error) {
            console.error('Error initializing battle settings:', error);
            this.showError('Failed to load battle settings: ' + error.message);
        }
    }
    
    async loadAvailableStats() {
        try {
            const response = await fetch('/api/battle/settings/available-stats');
            const data = await response.json();
            
            if (data.success) {
                this.availableStats = data.stats;
                this.statDescriptions = data.descriptions;
            } else {
                // Fallback to default stats
                this.setDefaultStats();
            }
        } catch (error) {
            console.error('Error loading available stats:', error);
            // Fallback to default stats
            this.setDefaultStats();
        }
    }
    
    setDefaultStats() {
        this.availableStats = ['ATT', 'DEF', 'INT', 'DEX', 'HAP', 'ENE'];
        this.statDescriptions = {
            'ATT': 'Attack - Raw offensive power',
            'DEF': 'Defense - Physical damage resistance', 
            'INT': 'Intelligence - Magical abilities',
            'DEX': 'Dexterity - Speed and accuracy',
            'HAP': 'Happiness - Overall well-being',
            'ENE': 'Energy - Stamina and endurance'
        };
    }
    
    async loadPresets() {
        try {
            const response = await fetch('/api/battle/settings/presets');
            const data = await response.json();
            
            if (data.success) {
                this.presets = data.presets;
            } else {
                // Fallback to default presets
                this.setDefaultPresets();
            }
        } catch (error) {
            console.error('Error loading presets:', error);
            // Fallback to default presets
            this.setDefaultPresets();
        }
    }
    
    setDefaultPresets() {
        this.presets = {
            'default': this.getDefaultFormula()
        };
    }
    
    async loadCurrentSettings() {
        try {
            if (this.options.mode === 'pvp' && this.options.roomId) {
                // Load room settings
                const response = await fetch(`/api/battle/room/${this.options.roomId}/settings`);
                const data = await response.json();
                
                if (data.success) {
                    this.currentSettings = {
                        formula: data.room_settings.formula,
                        room_info: data.room_settings
                    };
                } else {
                    // Fallback to default for PvP rooms
                    this.currentSettings = {
                        formula: this.presets.default || this.getDefaultFormula(),
                        active_preset: 'default',
                        isDefault: true
                    };
                }
            } else {
                // Load user settings
                try {
                    const response = await fetch('/api/battle/settings/my');
                    
                    if (response.status === 401 || response.status === 403) {
                        // User not authenticated - use default preset
                        console.log('User not authenticated, using default preset');
                        this.currentSettings = {
                            formula: this.presets.default || this.getDefaultFormula(),
                            active_preset: 'default',
                            isDefault: true
                        };
                        return;
                    }
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        this.currentSettings = data.settings;
                    } else {
                        // API error - use default preset
                        console.log('API error, using default preset:', data.error);
                        this.currentSettings = {
                            formula: this.presets.default || this.getDefaultFormula(),
                            active_preset: 'default',
                            isDefault: true
                        };
                    }
                } catch (fetchError) {
                    console.log('Fetch error, using default preset:', fetchError);
                    this.currentSettings = {
                        formula: this.presets.default || this.getDefaultFormula(),
                        active_preset: 'default',
                        isDefault: true
                    };
                }
            }
        } catch (error) {
            console.error('Error loading current settings:', error);
            // On any error, use default preset
            this.currentSettings = {
                formula: this.presets.default || this.getDefaultFormula(),
                active_preset: 'default',
                isDefault: true
            };
        }
    }
    
    getDefaultFormula() {
        // Fallback default formula if presets aren't loaded
        const defaultFormula = {
            // Health: HAP + ENE average * 10
            health_stats: ['HAP', 'ENE'],
            health_use_average: true,
            health_multiplier: 10.0,
            health_level_factor: true,
            health_equipment_factor: true,
            health_custom_multiplier: 1.0,
            health_custom_divider: 1.0,
            
            // Attack: ATT + DEX
            attack_stats: ['ATT', 'DEX'],
            attack_use_average: false,
            attack_multiplier: 1.0,
            attack_level_factor: true,
            attack_equipment_factor: true,
            attack_custom_multiplier: 1.0,
            attack_custom_divider: 1.0,
            
            // Defense: DEF + INT
            defense_stats: ['DEF', 'INT'],
            defense_use_average: false,
            defense_multiplier: 1.0,
            defense_level_factor: true,
            defense_equipment_factor: true,
            defense_custom_multiplier: 1.0,
            defense_custom_divider: 1.0,
            
            use_original_scaling: false,
            formula_name: "Default Formula"
        };
        
        console.log('Generated default formula:', defaultFormula);
        return defaultFormula;
    }
    
    render() {
        if (!this.container) {
            console.error('Battle settings container not found');
            return;
        }
        
        // Ensure we always have a valid formula
        let formula = this.currentSettings?.formula;
        if (!formula) {
            console.log('No formula found, using default');
            formula = this.presets?.default || this.getDefaultFormula();
        }
        
        console.log('Rendering battle settings with formula:', formula);
        
        this.container.innerHTML = `
            <div class="battle-settings-container">
                ${this.renderHeader()}
                ${this.renderPresetSelector()}
                ${this.renderFormulaEditor(formula)}
                ${this.renderTestSection()}
                ${this.renderActions()}
            </div>
        `;
        
        this.attachEventListeners();
    }
    
    renderHeader() {
        const title = this.options.mode === 'pvp' ? 'PvP Battle Settings' : 'My Battle Settings';
        const subtitle = this.options.mode === 'pvp' 
            ? 'Configure battle formulas for this room'
            : 'Customize your battle formulas for single-player encounters';
            
        // Check if user is authenticated by seeing if we have real user settings
        const isAuthenticated = this.currentSettings && !this.currentSettings.isDefault;
        const authMessage = !isAuthenticated ? 
            '<div class="alert alert-info mt-2"><small><strong>Note:</strong> Log in with Discord to save your settings and test with your pet. You can still configure and validate formulas.</small></div>' : '';
            
        return `
            <div class="battle-settings-header">
                <h3>⚔️ ${title}</h3>
                <p class="text-muted">${subtitle}</p>
                ${authMessage}
                ${this.options.mode === 'pvp' ? this.renderRoomInfo() : ''}
            </div>
        `;
    }
    
    renderRoomInfo() {
        if (!this.currentSettings?.room_info) return '';
        
        const roomInfo = this.currentSettings.room_info;
        return `
            <div class="room-info alert alert-info">
                <strong>Room #${roomInfo.room_id}</strong> - ${roomInfo.description}
                <br><small>Created by user ${roomInfo.creator_user_id}</small>
            </div>
        `;
    }
    
    renderPresetSelector() {
        const presetOptions = Object.keys(this.presets).map(name => {
            const preset = this.presets[name];
            const presetName = preset.formula_name || name;
            return `<option value="${name}">${presetName}</option>`;
        }).join('');
        
        return `
            <div class="preset-selector mb-3">
                <label class="form-label">Quick Presets</label>
                <div class="d-flex gap-2">
                    <select class="form-select" id="presetSelect">
                        <option value="">Choose a preset...</option>
                        ${presetOptions}
                    </select>
                    <button type="button" class="btn btn-outline-primary" id="loadPresetBtn">Load</button>
                </div>
            </div>
        `;
    }
    
    renderFormulaEditor(formula) {
        return `
            <div class="formula-editor">
                <div class="row">
                    <div class="col-md-4">
                        ${this.renderHealthFormula(formula)}
                    </div>
                    <div class="col-md-4">
                        ${this.renderAttackFormula(formula)}
                    </div>
                    <div class="col-md-4">
                        ${this.renderDefenseFormula(formula)}
                    </div>
                </div>
                
                <div class="row mt-3">
                    <div class="col-12">
                        ${this.renderGeneralSettings(formula)}
                    </div>
                </div>
            </div>
        `;
    }
    
    renderHealthFormula(formula) {
        // Ensure formula has all required properties with defaults
        const healthStats = formula.health_stats || ['HAP', 'ENE'];
        const healthUseAverage = formula.health_use_average !== undefined ? formula.health_use_average : true;
        const healthMultiplier = formula.health_multiplier || 10.0;
        const healthLevelFactor = formula.health_level_factor !== undefined ? formula.health_level_factor : true;
        const healthEquipmentFactor = formula.health_equipment_factor !== undefined ? formula.health_equipment_factor : true;
        const healthCustomMultiplier = formula.health_custom_multiplier || 1.0;
        const healthCustomDivider = formula.health_custom_divider || 1.0;
        
        return `
            <div class="formula-section">
                <h5>💚 Health Formula</h5>
                
                <div class="mb-3">
                    <label class="form-label">Stats to Include</label>
                    ${this.renderStatCheckboxes('health', healthStats)}
                </div>
                
                <div class="mb-3">
                    <div class="form-check form-switch">
                        <input class="form-check-input" type="checkbox" id="healthUseAverage" 
                               ${healthUseAverage ? 'checked' : ''}>
                        <label class="form-check-label" for="healthUseAverage">
                            Use Average (vs Sum)
                        </label>
                    </div>
                </div>
                
                <div class="mb-3">
                    <label for="healthMultiplier" class="form-label">Base Multiplier</label>
                    <input type="number" class="form-control" id="healthMultiplier" 
                           value="${healthMultiplier}" step="0.1" min="0.1">
                </div>
                
                <div class="mb-3">
                    <div class="form-check form-switch">
                        <input class="form-check-input" type="checkbox" id="healthLevelFactor" 
                               ${healthLevelFactor ? 'checked' : ''}>
                        <label class="form-check-label" for="healthLevelFactor">
                            Include Level Factor
                        </label>
                    </div>
                </div>
                
                <div class="mb-3">
                    <div class="form-check form-switch">
                        <input class="form-check-input" type="checkbox" id="healthEquipmentFactor" 
                               ${healthEquipmentFactor ? 'checked' : ''}>
                        <label class="form-check-label" for="healthEquipmentFactor">
                            Include Equipment Factor
                        </label>
                    </div>
                </div>
                
                <div class="row">
                    <div class="col-6">
                        <label for="healthCustomMultiplier" class="form-label">Custom Multiplier</label>
                        <input type="number" class="form-control" id="healthCustomMultiplier" 
                               value="${healthCustomMultiplier}" step="0.1" min="0.1">
                    </div>
                    <div class="col-6">
                        <label for="healthCustomDivider" class="form-label">Custom Divider</label>
                        <input type="number" class="form-control" id="healthCustomDivider" 
                               value="${healthCustomDivider}" step="0.1" min="0.1">
                    </div>
                </div>
            </div>
        `;
    }
    
    renderAttackFormula(formula) {
        // Ensure formula has all required properties with defaults
        const attackStats = formula.attack_stats || ['ATT', 'DEX'];
        const attackUseAverage = formula.attack_use_average !== undefined ? formula.attack_use_average : false;
        const attackMultiplier = formula.attack_multiplier || 1.0;
        const attackLevelFactor = formula.attack_level_factor !== undefined ? formula.attack_level_factor : true;
        const attackEquipmentFactor = formula.attack_equipment_factor !== undefined ? formula.attack_equipment_factor : true;
        const attackCustomMultiplier = formula.attack_custom_multiplier || 1.0;
        const attackCustomDivider = formula.attack_custom_divider || 1.0;
        
        return `
            <div class="formula-section">
                <h5>⚔️ Attack Formula</h5>
                
                <div class="mb-3">
                    <label class="form-label">Stats to Include</label>
                    ${this.renderStatCheckboxes('attack', attackStats)}
                </div>
                
                <div class="mb-3">
                    <div class="form-check form-switch">
                        <input class="form-check-input" type="checkbox" id="attackUseAverage" 
                               ${attackUseAverage ? 'checked' : ''}>
                        <label class="form-check-label" for="attackUseAverage">
                            Use Average (vs Sum)
                        </label>
                    </div>
                </div>
                
                <div class="mb-3">
                    <label for="attackMultiplier" class="form-label">Base Multiplier</label>
                    <input type="number" class="form-control" id="attackMultiplier" 
                           value="${attackMultiplier}" step="0.1" min="0.1">
                </div>
                
                <div class="mb-3">
                    <div class="form-check form-switch">
                        <input class="form-check-input" type="checkbox" id="attackLevelFactor" 
                               ${attackLevelFactor ? 'checked' : ''}>
                        <label class="form-check-label" for="attackLevelFactor">
                            Include Level Factor
                        </label>
                    </div>
                </div>
                
                <div class="mb-3">
                    <div class="form-check form-switch">
                        <input class="form-check-input" type="checkbox" id="attackEquipmentFactor" 
                               ${attackEquipmentFactor ? 'checked' : ''}>
                        <label class="form-check-label" for="attackEquipmentFactor">
                            Include Equipment Factor
                        </label>
                    </div>
                </div>
                
                <div class="row">
                    <div class="col-6">
                        <label for="attackCustomMultiplier" class="form-label">Custom Multiplier</label>
                        <input type="number" class="form-control" id="attackCustomMultiplier" 
                               value="${attackCustomMultiplier}" step="0.1" min="0.1">
                    </div>
                    <div class="col-6">
                        <label for="attackCustomDivider" class="form-label">Custom Divider</label>
                        <input type="number" class="form-control" id="attackCustomDivider" 
                               value="${attackCustomDivider}" step="0.1" min="0.1">
                    </div>
                </div>
            </div>
        `;
    }
    
    renderDefenseFormula(formula) {
        // Ensure formula has all required properties with defaults
        const defenseStats = formula.defense_stats || ['DEF', 'INT'];
        const defenseUseAverage = formula.defense_use_average !== undefined ? formula.defense_use_average : false;
        const defenseMultiplier = formula.defense_multiplier || 1.0;
        const defenseLevelFactor = formula.defense_level_factor !== undefined ? formula.defense_level_factor : true;
        const defenseEquipmentFactor = formula.defense_equipment_factor !== undefined ? formula.defense_equipment_factor : true;
        const defenseCustomMultiplier = formula.defense_custom_multiplier || 1.0;
        const defenseCustomDivider = formula.defense_custom_divider || 1.0;
        
        return `
            <div class="formula-section">
                <h5>🛡️ Defense Formula</h5>
                
                <div class="mb-3">
                    <label class="form-label">Stats to Include</label>
                    ${this.renderStatCheckboxes('defense', defenseStats)}
                </div>
                
                <div class="mb-3">
                    <div class="form-check form-switch">
                        <input class="form-check-input" type="checkbox" id="defenseUseAverage" 
                               ${defenseUseAverage ? 'checked' : ''}>
                        <label class="form-check-label" for="defenseUseAverage">
                            Use Average (vs Sum)
                        </label>
                    </div>
                </div>
                
                <div class="mb-3">
                    <label for="defenseMultiplier" class="form-label">Base Multiplier</label>
                    <input type="number" class="form-control" id="defenseMultiplier" 
                           value="${defenseMultiplier}" step="0.1" min="0.1">
                </div>
                
                <div class="mb-3">
                    <div class="form-check form-switch">
                        <input class="form-check-input" type="checkbox" id="defenseLevelFactor" 
                               ${defenseLevelFactor ? 'checked' : ''}>
                        <label class="form-check-label" for="defenseLevelFactor">
                            Include Level Factor
                        </label>
                    </div>
                </div>
                
                <div class="mb-3">
                    <div class="form-check form-switch">
                        <input class="form-check-input" type="checkbox" id="defenseEquipmentFactor" 
                               ${defenseEquipmentFactor ? 'checked' : ''}>
                        <label class="form-check-label" for="defenseEquipmentFactor">
                            Include Equipment Factor
                        </label>
                    </div>
                </div>
                
                <div class="row">
                    <div class="col-6">
                        <label for="defenseCustomMultiplier" class="form-label">Custom Multiplier</label>
                        <input type="number" class="form-control" id="defenseCustomMultiplier" 
                               value="${defenseCustomMultiplier}" step="0.1" min="0.1">
                    </div>
                    <div class="col-6">
                        <label for="defenseCustomDivider" class="form-label">Custom Divider</label>
                        <input type="number" class="form-control" id="defenseCustomDivider" 
                               value="${defenseCustomDivider}" step="0.1" min="0.1">
                    </div>
                </div>
            </div>
        `;
    }
    
    renderStatCheckboxes(type, selectedStats) {
        if (!Array.isArray(selectedStats)) {
            console.warn(`selectedStats for ${type} is not an array:`, selectedStats);
            selectedStats = [];
        }
        
        return this.availableStats.map(stat => `
            <div class="form-check">
                <input class="form-check-input" type="checkbox" id="${type}Stat${stat}" 
                       value="${stat}" ${selectedStats.includes(stat) ? 'checked' : ''}>
                <label class="form-check-label" for="${type}Stat${stat}" title="${this.statDescriptions[stat] || stat}">
                    ${stat}
                </label>
            </div>
        `).join('');
    }
    
    renderGeneralSettings(formula) {
        const formulaName = formula.formula_name || "Default Formula";
        const useOriginalScaling = formula.use_original_scaling !== undefined ? formula.use_original_scaling : false;
        
        return `
            <div class="general-settings">
                <h5>⚙️ General Settings</h5>
                
                <div class="row">
                    <div class="col-md-6">
                        <div class="mb-3">
                            <label for="formulaName" class="form-label">Formula Name</label>
                            <input type="text" class="form-control" id="formulaName" 
                                   value="${formulaName}" maxlength="50">
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="mb-3">
                            <div class="form-check form-switch">
                                <input class="form-check-input" type="checkbox" id="useOriginalScaling" 
                                       ${useOriginalScaling ? 'checked' : ''}>
                                <label class="form-check-label" for="useOriginalScaling">
                                    Use Original System (Ignore Custom Formula)
                                </label>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    renderTestSection() {
        return `
            <div class="test-section mt-4">
                <h5>🧪 Test Formula</h5>
                <div class="d-flex gap-2 mb-3">
                    <button type="button" class="btn btn-info" id="testFormulaBtn">Test with My Pet</button>
                    <button type="button" class="btn btn-outline-secondary" id="validateFormulaBtn">Validate Formula</button>
                </div>
                <div id="testResults" class="test-results" style="display: none;"></div>
            </div>
        `;
    }
    
    renderActions() {
        if (this.options.mode === 'pvp') {
            return `
                <div class="actions mt-4">
                    <div class="d-flex gap-2">
                        <button type="button" class="btn btn-success" id="acceptSettingsBtn">Accept Settings</button>
                        <button type="button" class="btn btn-secondary" id="cancelBtn">Cancel</button>
                    </div>
                </div>
            `;
        } else {
            return `
                <div class="actions mt-4">
                    <div class="d-flex gap-2">
                        <button type="button" class="btn btn-primary" id="saveSettingsBtn">Save Settings</button>
                        <button type="button" class="btn btn-outline-secondary" id="resetBtn">Reset to Default</button>
                    </div>
                </div>
            `;
        }
    }
    
    attachEventListeners() {
        // Ensure all elements are interactive
        const container = this.container;
        if (container) {
            container.style.position = 'relative';
            container.style.zIndex = '10005';
            
            // Make all interactive elements properly clickable
            const interactiveElements = container.querySelectorAll('input, select, button, textarea, .form-check-input, .form-control, .form-select');
            interactiveElements.forEach(element => {
                element.style.position = 'relative';
                element.style.zIndex = '10010';
                element.style.pointerEvents = 'auto';
            });
        }
        
        // Preset loader
        const loadPresetBtn = document.getElementById('loadPresetBtn');
        if (loadPresetBtn) {
            loadPresetBtn.addEventListener('click', () => this.loadPreset());
        }
        
        // Test formula
        const testBtn = document.getElementById('testFormulaBtn');
        if (testBtn) {
            testBtn.addEventListener('click', () => this.testFormula());
        }
        
        // Validate formula
        const validateBtn = document.getElementById('validateFormulaBtn');
        if (validateBtn) {
            validateBtn.addEventListener('click', () => this.validateFormula());
        }
        
        // Save settings
        const saveBtn = document.getElementById('saveSettingsBtn');
        if (saveBtn) {
            saveBtn.addEventListener('click', () => this.saveSettings());
        }
        
        // Accept settings (PvP mode)
        const acceptBtn = document.getElementById('acceptSettingsBtn');
        if (acceptBtn) {
            acceptBtn.addEventListener('click', () => this.acceptSettings());
        }
        
        // Reset to default
        const resetBtn = document.getElementById('resetBtn');
        if (resetBtn) {
            resetBtn.addEventListener('click', () => this.resetToDefault());
        }
        
        // Auto-test on changes
        this.container.addEventListener('change', () => {
            // Clear previous test results when settings change
            const testResults = document.getElementById('testResults');
            if (testResults) {
                testResults.style.display = 'none';
            }
        });
    }
    
    async loadPreset() {
        const select = document.getElementById('presetSelect');
        const presetName = select.value;
        
        if (!presetName) return;
        
        try {
            const response = await fetch(`/api/battle/settings/preset/${presetName}`, {
                method: 'POST'
            });
            const data = await response.json();
            
            if (data.success) {
                this.showSuccess(`Loaded preset: ${presetName}`);
                await this.loadCurrentSettings();
                this.render();
            } else {
                this.showError(data.error);
            }
        } catch (error) {
            console.error('Error loading preset:', error);
            this.showError('Failed to load preset');
        }
    }
    
    async testFormula() {
        const formula = this.getFormulaFromForm();
        
        try {
            const response = await fetch('/api/battle/settings/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formula)
            });
            
            if (response.status === 401 || response.status === 403) {
                this.showError('Please log in with Discord to test your formula with your pet. You can still validate the formula configuration.');
                return;
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.displayTestResults(data.test_results);
            } else {
                this.showError(data.error);
            }
        } catch (error) {
            console.error('Error testing formula:', error);
            this.showError('Failed to test formula. Please check your connection and try again.');
        }
    }
    
    async validateFormula() {
        const formula = this.getFormulaFromForm();
        
        try {
            const response = await fetch('/api/battle/settings/validate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formula)
            });
            const data = await response.json();
            
            if (data.success) {
                if (data.valid) {
                    this.showSuccess('Formula is valid!');
                } else {
                    this.showError(`Formula validation failed: ${data.message}`);
                }
            } else {
                this.showError(data.error);
            }
        } catch (error) {
            console.error('Error validating formula:', error);
            this.showError('Failed to validate formula');
        }
    }
    
    async saveSettings() {
        const formula = this.getFormulaFromForm();
        const settings = {
            formula: formula,
            active_preset: 'custom'
        };
        
        try {
            const response = await fetch('/api/battle/settings/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });
            
            if (response.status === 401 || response.status === 403) {
                this.showError('Please log in with Discord to save your battle settings. You can still test and use the settings in this session.');
                return;
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.showSuccess('Battle settings saved successfully!');
                if (this.options.onSave) {
                    this.options.onSave(settings);
                }
            } else {
                this.showError(data.error);
            }
        } catch (error) {
            console.error('Error saving settings:', error);
            this.showError('Failed to save settings. Please check your connection and try again.');
        }
    }
    
    async acceptSettings() {
        if (!this.options.roomId) return;
        
        try {
            const response = await fetch(`/api/battle/room/${this.options.roomId}/accept`, {
                method: 'POST'
            });
            const data = await response.json();
            
            if (data.success) {
                this.showSuccess('Battle settings accepted!');
                if (this.options.onSave) {
                    this.options.onSave();
                }
            } else {
                this.showError(data.error);
            }
        } catch (error) {
            console.error('Error accepting settings:', error);
            this.showError('Failed to accept settings');
        }
    }
    
    resetToDefault() {
        if (confirm('Reset to default formula? This will lose your current changes.')) {
            const defaultFormula = this.presets.default;
            this.populateFormWithFormula(defaultFormula);
        }
    }
    
    getFormulaFromForm() {
        return {
            // Health settings
            health_stats: this.getCheckedStats('health'),
            health_use_average: document.getElementById('healthUseAverage').checked,
            health_multiplier: parseFloat(document.getElementById('healthMultiplier').value),
            health_level_factor: document.getElementById('healthLevelFactor').checked,
            health_equipment_factor: document.getElementById('healthEquipmentFactor').checked,
            health_custom_multiplier: parseFloat(document.getElementById('healthCustomMultiplier').value),
            health_custom_divider: parseFloat(document.getElementById('healthCustomDivider').value),
            
            // Attack settings
            attack_stats: this.getCheckedStats('attack'),
            attack_use_average: document.getElementById('attackUseAverage').checked,
            attack_multiplier: parseFloat(document.getElementById('attackMultiplier').value),
            attack_level_factor: document.getElementById('attackLevelFactor').checked,
            attack_equipment_factor: document.getElementById('attackEquipmentFactor').checked,
            attack_custom_multiplier: parseFloat(document.getElementById('attackCustomMultiplier').value),
            attack_custom_divider: parseFloat(document.getElementById('attackCustomDivider').value),
            
            // Defense settings
            defense_stats: this.getCheckedStats('defense'),
            defense_use_average: document.getElementById('defenseUseAverage').checked,
            defense_multiplier: parseFloat(document.getElementById('defenseMultiplier').value),
            defense_level_factor: document.getElementById('defenseLevelFactor').checked,
            defense_equipment_factor: document.getElementById('defenseEquipmentFactor').checked,
            defense_custom_multiplier: parseFloat(document.getElementById('defenseCustomMultiplier').value),
            defense_custom_divider: parseFloat(document.getElementById('defenseCustomDivider').value),
            
            // General settings
            use_original_scaling: document.getElementById('useOriginalScaling').checked,
            formula_name: document.getElementById('formulaName').value
        };
    }
    
    getCheckedStats(type) {
        const stats = [];
        this.availableStats.forEach(stat => {
            const checkbox = document.getElementById(`${type}Stat${stat}`);
            if (checkbox && checkbox.checked) {
                stats.push(stat);
            }
        });
        return stats;
    }
    
    populateFormWithFormula(formula) {
        // This would populate the form fields with the formula data
        // Implementation would set all the form values based on the formula object
        this.render(); // For now, just re-render
    }
    
    displayTestResults(results) {
        const testResultsDiv = document.getElementById('testResults');
        if (!testResultsDiv) return;
        
        testResultsDiv.innerHTML = `
            <div class="test-results-content">
                <h6>Test Results for ${results.pet_info.name} (Level ${results.pet_info.level})</h6>
                <div class="row">
                    <div class="col-md-4">
                        <strong>Health:</strong><br>
                        Original: ${results.original.health.toLocaleString()}<br>
                        Custom: ${results.custom.health.toLocaleString()}
                        ${this.getChangeIndicator(results.original.health, results.custom.health)}
                    </div>
                    <div class="col-md-4">
                        <strong>Attack:</strong><br>
                        Original: ${results.original.attack.toLocaleString()}<br>
                        Custom: ${results.custom.attack.toLocaleString()}
                        ${this.getChangeIndicator(results.original.attack, results.custom.attack)}
                    </div>
                    <div class="col-md-4">
                        <strong>Defense:</strong><br>
                        Original: ${results.original.defense.toLocaleString()}<br>
                        Custom: ${results.custom.defense.toLocaleString()}
                        ${this.getChangeIndicator(results.original.defense, results.custom.defense)}
                    </div>
                </div>
            </div>
        `;
        testResultsDiv.style.display = 'block';
    }
    
    getChangeIndicator(original, custom) {
        const change = ((custom - original) / original) * 100;
        const color = change > 0 ? 'text-success' : change < 0 ? 'text-danger' : 'text-muted';
        const icon = change > 0 ? '↗' : change < 0 ? '↘' : '→';
        return `<br><small class="${color}">${icon} ${change.toFixed(1)}%</small>`;
    }
    
    showSuccess(message) {
        this.showAlert(message, 'success');
    }
    
    showError(message) {
        this.showAlert(message, 'danger');
    }
    
    showAlert(message, type) {
        // Create or update alert
        let alert = this.container.querySelector('.battle-settings-alert');
        if (!alert) {
            alert = document.createElement('div');
            alert.className = 'battle-settings-alert alert';
            this.container.insertBefore(alert, this.container.firstChild);
        }
        
        alert.className = `battle-settings-alert alert alert-${type}`;
        alert.textContent = message;
        
        // Auto-hide after 5 seconds
        setTimeout(() => {
            if (alert.parentNode) {
                alert.parentNode.removeChild(alert);
            }
        }, 5000);
    }
}

// Export for use in other scripts
window.BattleSettingsUI = BattleSettingsUI;
/**
 * Abilities & Mastery Tree — Frontend (Compact Redesign)
 * Public API: window.AbilityTree.open() / .close()
 */
(function () {
    'use strict';

    var STAT_META = {
        ATT: { label:'ATT', icon:'/static/Emojis/Pets/Deco/ATT.png', color:'#e74c3c' },
        DEF: { label:'DEF', icon:'/static/Emojis/Pets/Deco/DEF.png', color:'#3498db' },
        INT: { label:'INT', icon:'/static/Emojis/Pets/Deco/INT.png', color:'#9b59b6' },
        DEX: { label:'DEX', icon:'/static/Emojis/Pets/Deco/DEX.png', color:'#1abc9c' },
        HAP: { label:'HAP', icon:'/static/Emojis/Pets/Deco/HAP.png', color:'#f39c12' },
        ENE: { label:'ENE', icon:'/static/Emojis/Pets/Deco/ENE.png', color:'#2ecc71' },
    };

    var ABILITY_ICONS = {
        'att_npc_damage':'🤖','att_pvp_damage':'⚔️','att_boss_damage':'🐉',
        'att_survive_aggression':'🔥','att_critical_chance':'🎯','att_critical_multiplier':'💥',
        'def_npc_defense':'🛡️','def_pvp_defense':'🏰','def_boss_defense':'⛰️',
        'def_survive_endurance':'🧱','def_charge_protection':'🔋','def_last_stand':'💀',
        'int_train_xp':'🧠','int_mission_xp':'🎯','int_play_xp':'🎮','int_quest_xp':'📜',
        'int_survive_xp':'🧠','int_npc_battle_xp':'🤖','int_pvp_battle_xp':'⚔️','int_boss_battle_xp':'🐉',
        'dex_speed_boost':'💨','dex_slots_loss_reduction':'🎰','dex_blackjack_loss_reduction':'🃏',
        'dex_holdem_loss_reduction':'♠️','dex_craps_loss_reduction':'🎲','dex_wheel_loss_reduction':'🎡',
        'dex_keno_loss_reduction':'🔢','dex_scratch_loss_reduction':'🎫','dex_powerball_loss_reduction':'🎱',
        'dex_races_loss_reduction':'🏇','dex_coinflip_loss_reduction':'🪙','dex_rps_loss_reduction':'✂️',
        'hap_battle_health':'❤️','hap_slots_win_bonus':'🎰','hap_blackjack_win_bonus':'🃏',
        'hap_holdem_win_bonus':'♠️','hap_craps_win_bonus':'🎲','hap_wheel_win_bonus':'🎡',
        'hap_keno_win_bonus':'🔢','hap_scratch_win_bonus':'🎫','hap_powerball_win_bonus':'🎱',
        'hap_races_win_bonus':'🏇','hap_coinflip_win_bonus':'🪙','hap_rps_win_bonus':'✂️',
        'ene_battle_stamina':'💪','ene_charge_mastery':'⚡','ene_speed_burst':'🚀',
        'ene_charged_start':'🔋','ene_overcharged':'⚡',
    };

    var STATS = ['ATT','DEF','INT','DEX','HAP','ENE'];
    var _treeState    = null;
    var _loading      = false;
    var _selectedNode = null;
    var _openStat     = null;   // which stat section is currently expanded

    function el(id) { return document.getElementById(id); }

    // ── Overlay shell ─────────────────────────────────────────────────────────
    function ensureOverlay() {
        if (el('ability-tree-overlay')) return;
        if (!document.querySelector('link[href="/css/ability_tree.css"]')) {
            var lnk = document.createElement('link');
            lnk.rel = 'stylesheet'; lnk.href = '/css/ability_tree.css';
            document.head.appendChild(lnk);
        }
        var ov = document.createElement('div');
        ov.id = 'ability-tree-overlay';
        ov.style.display = 'none';
        ov.innerHTML =
            '<div id="ability-tree-modal">' +
                '<div class="at-header">' +
                    '<h5 class="at-title">💎 Abilities &amp; Mastery</h5>' +
                    '<span class="at-points-badge" id="at-points-badge">✨ 0 pts</span>' +
                    '<button class="at-close-btn" onclick="window.AbilityTree.close()">✕</button>' +
                '</div>' +
                '<div class="at-body" id="at-body">' +
                    '<div style="text-align:center;padding:30px;color:var(--text-secondary)">Loading…</div>' +
                '</div>' +
            '</div>' +
            '<div id="at-toast"></div>';
        ov.addEventListener('click', function(e){ if (e.target === ov) window.AbilityTree.close(); });
        document.body.appendChild(ov);
    }

    // ── Toast ─────────────────────────────────────────────────────────────────
    var _toastTimer = null;
    function showToast(msg, ok) {
        var t = el('at-toast'); if (!t) return;
        t.textContent = msg;
        t.className = 'at-toast-show ' + (ok ? 'at-toast-ok' : 'at-toast-err');
        if (_toastTimer) clearTimeout(_toastTimer);
        _toastTimer = setTimeout(function(){ t.className = ''; }, 3000);
    }

    // ── Fetch ─────────────────────────────────────────────────────────────────
    function fetchTree(cb) {
        fetch('/api/pets/ability-tree')
            .then(function(r){ return r.json(); })
            .then(function(d){ _treeState = d; if (cb) cb(d); })
            .catch(function(e){ showToast('Failed to load: ' + e.message, false); });
    }

    // ── Render ────────────────────────────────────────────────────────────────
    function render(state) {
        _treeState = state;
        var pts = state.available_points || 0;
        var badge = el('at-points-badge');
        if (badge) badge.textContent = '✨ ' + pts + ' pt' + (pts !== 1 ? 's' : '');
        var body = el('at-body'); if (!body) return;
        body.innerHTML =
            '<div class="at-topbar">' +
                renderPurchaseBar(state) +
                renderAdvMasteryCards(state) +
            '</div>' +
            '<div class="at-content-layout">' +
                '<div class="at-tree-container">' + renderTree(state) + '</div>' +
                '<div class="at-details-container" id="at-details-panel">' + renderDetails() + '</div>' +
            '</div>';
        
        // Expose all global handlers
        exposeGlobalHandlers();
    }

    // ── Purchase bar ──────────────────────────────────────────────────────────
    function renderPurchaseBar(state) {
        var pts = state.available_points || 0;
        var level = state.current_level || 1;
        var canBuy = state.can_purchase_point || false;
        var cost = state.point_cost || 500;
        return '<div class="at-purchase-compact">' +
            '<div class="at-purchase-info">' +
                '<span class="at-purchase-label">💎 ' + pts + ' pt' + (pts !== 1 ? 's' : '') + '</span>' +
                '<span class="at-purchase-cost">Cost: ' + cost + ' Lvls</span>' +
                '<span class="at-purchase-level">Lv.' + level + '</span>' +
            '</div>' +
            '<button class="at-purchase-btn-compact"' + (canBuy ? '' : ' disabled') +
                ' onclick="window.AbilityTree._purchasePoint()">' +
                (canBuy ? '🛒 Buy Point' : '❌ Need ' + (cost - level) + ' Lvls') +
            '</button>' +
        '</div>';
    }

    // ── Advantage mastery cards ───────────────────────────────────────────────
    function renderAdvMasteryCards(state) {
        var adv = state.advantage_mastery || {};
        var pts = state.available_points || 0;
        var canSpend = pts >= 1;
        var cards = [
            { key:'type',    icon:'⚔️', label:'Type Adv.' },
            { key:'element', icon:'✨', label:'Elem Adv.' },
        ];
        var html = '<div class="at-adv-mastery-group">';
        cards.forEach(function(c) {
            var m = adv[c.key] || { points:0, bonus:0 };
            var mpts = m.points || 0;
            var bonus = m.bonus !== undefined ? m.bonus : (mpts * 0.1);
            var isSelected = _selectedNode && _selectedNode.type === 'adv' && _selectedNode.key === c.key;
            html += '<div class="at-adv-card' + (isSelected ? ' at-selected' : '') +
                '" onclick="selectAdvNode(\'' + c.key + '\')">' +
                '<div class="at-adv-card-icon">' + c.icon + '</div>' +
                '<div class="at-adv-card-info">' +
                    '<div class="at-adv-card-label">' + c.label + '</div>' +
                    '<div class="at-adv-card-val">+' + bonus.toFixed(1) + '</div>' +
                    '<div class="at-adv-card-pts">' + mpts + ' pts</div>' +
                '</div>' +
                '<button class="at-adv-upgrade-btn"' + (canSpend ? '' : ' disabled') +
                    ' onclick="event.stopPropagation(); upgradeAdvMastery(\'' + c.key + '\')">+</button>' +
            '</div>';
        });
        return html + '</div>';
    }

    // ── Accordion toggle ──────────────────────────────────────────────────────
    function toggleStatSection(stat) {
        console.log('Toggling stat section:', stat, 'Current open:', _openStat);
        _openStat = (_openStat === stat) ? null : stat;
        console.log('New open stat:', _openStat);
        // Re-render just the tree container to avoid losing the details panel
        var tc = document.querySelector('.at-tree-container');
        if (tc && _treeState) {
            tc.innerHTML = renderTree(_treeState);
            // Re-expose globals (onclick handlers need them)
            exposeGlobalHandlers();
        }
    }

    // Helper function to expose global handlers
    function exposeGlobalHandlers() {
        window.toggleStatSection = toggleStatSection;
        window.selectMasteryNode = selectMasteryNode;
        window.selectAbilityNode = selectAbilityNode;
        window.upgradeMastery    = function(s){ window.AbilityTree._spendMastery(s); };
        window.unlockMastery     = window.upgradeMastery;
        window.upgradeAbility    = function(id){ window.AbilityTree._unlockAbility(id); };
        window.selectAdvNode     = selectAdvNode;
        window.upgradeAdvMastery = function(k){ window.AbilityTree._spendAdvMastery(k); };
    }

    // ── Stat sections tree ────────────────────────────────────────────────────
    function renderTree(state) {
        var mastery   = state.stat_mastery || {};
        var abilities = state.abilities    || {};
        var pts       = state.available_points || 0;

        return STATS.map(function(stat) {
            var m    = mastery[stat] || { points:0, multiplier:1.0 };
            var meta = STAT_META[stat];
            var isUnlocked = m.points > 0;
            var canUnlock  = pts >= 1 && !isUnlocked;
            var mClass = isUnlocked ? 'at-stat-unlocked' : canUnlock ? 'at-stat-available' : 'at-stat-locked';
            var isSelMastery = _selectedNode && _selectedNode.type === 'mastery' && _selectedNode.stat === stat;
            var isOpen = _openStat === stat;

            // Count abilities with progress for the collapsed summary
            var statAbs = Object.keys(abilities)
                .map(function(id){ return abilities[id]; })
                .filter(function(a){ return a.stat === stat; });
            var ownedCount = statAbs.filter(function(a){ return (a.current_level || 0) > 0; }).length;
            var totalCount = statAbs.length;

            // Summary chips shown when collapsed
            var summaryHtml = '';
            if (!isOpen) {
                if (isUnlocked) {
                    summaryHtml = '<span class="at-section-summary">' +
                        '<span class="at-summary-mult">x' + m.multiplier.toFixed(1) + '</span>' +
                        (totalCount > 0 ? '<span class="at-summary-ab">' + ownedCount + '/' + totalCount + ' ab</span>' : '') +
                    '</span>';
                } else {
                    summaryHtml = '<span class="at-section-summary"><span class="at-summary-locked">🔒 ' + totalCount + ' ab</span></span>';
                }
            }

            var chevron = '<span class="at-chevron' + (isOpen ? ' at-chevron-open' : '') + '">›</span>';

            var masteryRow =
                '<div class="at-stat-mastery ' + mClass + (isSelMastery ? ' at-selected' : '') + '">' +
                    '<div class="at-stat-icon"><img src="' + meta.icon + '" alt="' + stat + '" onerror="this.style.display=\'none\'"></div>' +
                    '<div class="at-stat-info">' +
                        '<div class="at-stat-name">' + stat + ' Mastery</div>' +
                        '<div class="at-stat-multiplier">x' + m.multiplier.toFixed(1) + '</div>' +
                        '<div class="at-stat-points">' + m.points + ' pts</div>' +
                    '</div>' +
                    summaryHtml +
                    '<div class="at-stat-action" onclick="event.stopPropagation()">' +
                        (isUnlocked
                            ? '<button class="at-upgrade-btn" onclick="upgradeMastery(\'' + stat + '\')">+</button>'
                            : canUnlock
                                ? '<button class="at-unlock-btn" onclick="unlockMastery(\'' + stat + '\')">Unlock</button>'
                                : '<span class="at-locked-indicator">🔒</span>') +
                    '</div>' +
                    chevron +
                '</div>';

            var abilitiesHtml = '';
            if (isOpen) {
                if (isUnlocked) {
                    abilitiesHtml = '<div class="at-abilities-list">' +
                        statAbs.map(function(ab) {
                            var lvl     = ab.current_level || 0;
                            var maxLvl  = ab.effective_max_level || ab.max_level || 5;
                            var canUp   = ab.can_upgrade || false;
                            var isMaxed = lvl >= maxLvl;
                            var icon    = ABILITY_ICONS[ab.id] || '✨';
                            var isSelAb = _selectedNode && _selectedNode.type === 'ability' && _selectedNode.abilityId === ab.id;

                            var rowClass = 'at-ability-row ' +
                                (isMaxed ? 'at-ability-maxed' :
                                 lvl > 0  ? 'at-ability-owned' :
                                 canUp    ? 'at-ability-available' : 'at-ability-locked') +
                                (isSelAb ? ' at-selected' : '');

                            var pips = '';
                            for (var i = 1; i <= maxLvl; i++) {
                                var pc = i <= lvl ? (isMaxed ? 'maxed' : 'filled') :
                                         (i === lvl + 1 && canUp ? 'next' : '');
                                pips += '<div class="at-pip' + (pc ? ' ' + pc : '') + '"></div>';
                            }

                            var badge = isMaxed
                                ? '<span class="at-row-badge at-badge-max">MAX</span>'
                                : canUp
                                    ? '<span class="at-row-badge at-badge-up">' + (lvl === 0 ? 'UNLOCK' : 'UP') + '</span>'
                                    : lvl > 0
                                        ? '<span class="at-row-badge at-badge-lv">Lv.' + lvl + '</span>'
                                        : '<span class="at-row-badge at-badge-lock">🔒</span>';

                            return '<div class="' + rowClass + '" onclick="selectAbilityNode(\'' + ab.id + '\')">' +
                                '<span class="at-row-icon">' + icon + '</span>' +
                                '<span class="at-row-name">' + ab.name + '</span>' +
                                '<div class="at-row-pips">' + pips + '</div>' +
                                badge +
                            '</div>';
                        }).join('') +
                    '</div>';
                } else {
                    abilitiesHtml = '<div class="at-abilities-locked">🔒 Unlock ' + stat + ' Mastery to access ' + totalCount + ' abilities</div>';
                }
            }

            return '<div class="at-stat-section' + (isOpen ? ' at-section-open' : '') + '" data-stat="' + stat + '">' +
                '<div class="at-section-header" style="border-color:' + meta.color + '" onclick="toggleStatSection(\'' + stat + '\'); selectMasteryNode(\'' + stat + '\');">' +
                    masteryRow +
                '</div>' +
                (isOpen ? '<div class="at-section-content">' + abilitiesHtml + '</div>' : '') +
            '</div>';
        }).join('');
    }

    // ── Details panel ─────────────────────────────────────────────────────────
    function renderDetails() {
        if (!_selectedNode) {
            return '<div class="at-details-empty">' +
                '<div class="at-details-empty-icon">👆</div>' +
                'Click any mastery, ability, or advantage card to see details &amp; actions.' +
            '</div>';
        }
        var node = _selectedNode;

        // ── Advantage mastery detail ──────────────────────────────────────────
        if (node.type === 'adv') {
            var key   = node.key;
            var adv   = (_treeState.advantage_mastery || {})[key] || { points:0, bonus:0 };
            var mpts  = adv.points || 0;
            var bonus = adv.bonus !== undefined ? adv.bonus : (mpts * 0.1);
            var canUp = (_treeState.available_points || 0) >= 1;
            var label = key === 'type' ? 'Type Advantage' : 'Element Advantage';
            var icon  = key === 'type' ? '⚔️' : '✨';
            var desc  = key === 'type'
                ? 'Adds a flat bonus to your type advantage multiplier when you have the matchup advantage (e.g. Flying vs Land). Only applies when you already have the advantage — neutral and disadvantaged matchups are unaffected.'
                : 'Adds a flat bonus to your element effectiveness multiplier when your element is strong against the opponent. Averaged across dual-element matchups. Only applies when you already have the advantage.';
            return '<div class="at-details-header">' +
                '<div class="at-details-icon-large">' + icon + '</div>' +
                '<div><div class="at-details-title">' + label + ' Mastery</div>' +
                '<div class="at-details-subtitle">Advantage Bonus</div></div>' +
            '</div>' +
            '<div class="at-details-description">' + desc + '</div>' +
            '<div class="at-details-stats">' +
                '<div class="at-detail-row"><span class="at-detail-label">Points Invested</span><span class="at-detail-value">' + mpts + '</span></div>' +
                '<div class="at-detail-row"><span class="at-detail-label">Current Bonus</span><span class="at-detail-value">+' + bonus.toFixed(1) + '</span></div>' +
                '<div class="at-detail-row"><span class="at-detail-label">Next Point</span><span class="at-detail-value">+' + (bonus + 0.1).toFixed(1) + '</span></div>' +
            '</div>' +
            '<div class="at-details-action">' +
                (canUp
                    ? '<button class="at-action-btn at-action-upgrade" onclick="upgradeAdvMastery(\'' + key + '\')">⬆️ Spend 1 Point (+0.1 bonus)</button>'
                    : '<button class="at-action-btn at-action-disabled" disabled>❌ Need more ability points</button>') +
            '</div>';
        }

        // ── Stat mastery detail ───────────────────────────────────────────────
        if (node.type === 'mastery') {
            var stat  = node.stat;
            var m     = (_treeState.stat_mastery || {})[stat] || { points:0, multiplier:1.0 };
            var meta  = STAT_META[stat];
            var canUp = (_treeState.available_points || 0) >= 1;
            return '<div class="at-details-header">' +
                '<div class="at-details-icon-large"><img src="' + meta.icon + '" alt="' + stat + '" onerror="this.style.display=\'none\'"></div>' +
                '<div><div class="at-details-title">' + stat + ' Mastery</div>' +
                '<div class="at-details-subtitle">Stat Multiplier</div></div>' +
            '</div>' +
            '<div class="at-details-description">Each point multiplies your ' + stat + ' stat by an additional 0.1x. ' +
                'At least 1 point is required to unlock abilities in this branch.</div>' +
            '<div class="at-details-stats">' +
                '<div class="at-detail-row"><span class="at-detail-label">Points Invested</span><span class="at-detail-value">' + m.points + '</span></div>' +
                '<div class="at-detail-row"><span class="at-detail-label">Current Multiplier</span><span class="at-detail-value">x' + m.multiplier.toFixed(1) + '</span></div>' +
                '<div class="at-detail-row"><span class="at-detail-label">Next Point</span><span class="at-detail-value">x' + (m.multiplier + 0.1).toFixed(1) + '</span></div>' +
            '</div>' +
            '<div class="at-details-action">' +
                (canUp
                    ? '<button class="at-action-btn at-action-upgrade" onclick="upgradeMastery(\'' + stat + '\')">⬆️ Spend 1 Point (+0.1x)</button>'
                    : '<button class="at-action-btn at-action-disabled" disabled>❌ Need more ability points</button>') +
            '</div>';
        }

        // ── Ability detail ────────────────────────────────────────────────────
        if (node.type === 'ability') {
            var abs    = _treeState.abilities || {};
            var ab     = abs[node.abilityId];
            if (!ab) return '<div class="at-details-empty">Ability not found.</div>';
            var lvl    = ab.current_level || 0;
            var maxLvl = ab.effective_max_level || ab.max_level || 5;
            var canUp  = ab.can_upgrade || false;
            var isMaxed = lvl >= maxLvl;
            var icon   = ABILITY_ICONS[ab.id] || '✨';

            var pips = '';
            for (var i = 1; i <= maxLvl; i++) {
                var pc = i <= lvl ? (isMaxed ? 'maxed' : 'filled') :
                         (i === lvl + 1 && canUp ? 'next' : '');
                pips += '<div class="at-pip' + (pc ? ' ' + pc : '') + '"></div>';
            }

            return '<div class="at-details-header">' +
                '<div class="at-details-icon-large">' + icon + '</div>' +
                '<div><div class="at-details-title">' + ab.name + '</div>' +
                '<div class="at-details-subtitle">' + ab.stat + ' Ability</div></div>' +
            '</div>' +
            '<div class="at-details-level">' +
                '<div class="at-level-display">' +
                    '<span class="at-level-text">Lv.' + lvl + '/' + maxLvl + '</span>' +
                    '<div class="at-level-dots-detail">' + pips + '</div>' +
                '</div>' +
            '</div>' +
            '<div class="at-details-description">' + ab.description + '</div>' +
            '<div class="at-details-stats">' +
                '<div class="at-detail-row"><span class="at-detail-label">Current Effect</span><span class="at-detail-value">' + (ab.formatted_value || '—') + '</span></div>' +
                (!isMaxed && canUp ? '<div class="at-detail-row"><span class="at-detail-label">Next Level</span><span class="at-detail-value">' + (ab.next_level_value || '—') + '</span></div>' : '') +
            '</div>' +
            '<div class="at-details-action">' +
                (isMaxed
                    ? '<button class="at-action-btn at-action-maxed" disabled>✨ Maxed Out</button>'
                    : canUp
                        ? '<button class="at-action-btn at-action-upgrade" onclick="upgradeAbility(\'' + ab.id + '\')">' +
                            (lvl === 0 ? '🔓 Unlock' : '⬆️ Upgrade to Lv.' + (lvl + 1)) + '</button>'
                        : !ab.stat_mastery_met
                            ? '<button class="at-action-btn at-action-disabled" disabled>🔒 Unlock ' + ab.stat + ' Mastery first</button>'
                            : '<button class="at-action-btn at-action-disabled" disabled>❌ Need more ability points</button>') +
            '</div>';
        }

        return '';
    }

    // ── Selection handlers ────────────────────────────────────────────────────
    function _refreshPanel() {
        var panel = el('at-details-panel');
        if (panel) panel.innerHTML = renderDetails();
    }
    function _clearSelection() {
        document.querySelectorAll('.at-stat-mastery.at-selected, .at-ability-row.at-selected, .at-adv-card.at-selected')
            .forEach(function(e){ e.classList.remove('at-selected'); });
    }

    function selectMasteryNode(stat) {
        _selectedNode = { type:'mastery', stat:stat };
        // also open this section if it isn't already
        if (_openStat !== stat) {
            _openStat = stat;
            var tc = document.querySelector('.at-tree-container');
            if (tc && _treeState) {
                tc.innerHTML = renderTree(_treeState);
                exposeGlobalHandlers();
            }
        }
        _clearSelection();
        var el2 = document.querySelector('.at-stat-section[data-stat="' + stat + '"] .at-stat-mastery');
        if (el2) el2.classList.add('at-selected');
        _refreshPanel();
    }
    function selectAbilityNode(abilityId) {
        _selectedNode = { type:'ability', abilityId:abilityId };
        _clearSelection();
        var el2 = document.querySelector('.at-ability-row[onclick*="' + abilityId + '"]');
        if (el2) el2.classList.add('at-selected');
        _refreshPanel();
    }
    function selectAdvNode(key) {
        _selectedNode = { type:'adv', key:key };
        _clearSelection();
        var el2 = document.querySelector('.at-adv-card[onclick*="' + key + '"]');
        if (el2) el2.classList.add('at-selected');
        _refreshPanel();
    }

    window.selectMasteryNode = selectMasteryNode;
    window.selectAbilityNode = selectAbilityNode;
    window.selectAdvNode     = selectAdvNode;

    // Expose global handlers initially
    exposeGlobalHandlers();

    // ── Animations ────────────────────────────────────────────────────────────
    function animateUnlock(selector, cls, duration) {
        var el2 = document.querySelector(selector);
        if (!el2) return;
        el2.classList.add(cls);
        setTimeout(function(){ el2.classList.remove(cls); }, duration);
    }
    function showUnlockEffect(stat, isAbility, abilityId) {
        if (isAbility) {
            animateUnlock('.at-ability-row[onclick*="' + abilityId + '"]', 'at-unlock-animation', 500);
        } else {
            animateUnlock('.at-stat-section[data-stat="' + stat + '"] .at-stat-mastery', 'at-unlock-animation', 700);
        }
    }

    // ── DOMContentLoaded cleanup ──────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', function() {
        var isMypet = new URLSearchParams(window.location.search).get('page') === 'mypet'
                   || !!document.getElementById('mypet-root');
        if (!isMypet) {
            var ov = document.getElementById('ability-tree-overlay');
            if (ov) ov.remove();
        }
    });

    // ── Actions ───────────────────────────────────────────────────────────────
    function spendMastery(stat) {
        if (_loading) return;
        _loading = true;
        fetch('/api/pets/ability-tree/mastery', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ stat:stat, points:1 }),
        })
        .then(function(r){ return r.json(); })
        .then(function(d){
            _loading = false;
            if (d.ok) {
                showToast(d.message, true);
                render(d.tree);
                setTimeout(function(){ showUnlockEffect(stat, false); }, 80);
            } else { showToast(d.message || 'Failed', false); }
        })
        .catch(function(e){ _loading = false; showToast('Error: ' + e.message, false); });
    }

    function unlockAbility(abilityId) {
        if (_loading) return;
        _loading = true;
        fetch('/api/pets/ability-tree/unlock', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ ability_id:abilityId }),
        })
        .then(function(r){ return r.json(); })
        .then(function(d){
            _loading = false;
            if (d.ok) {
                showToast(d.message, true);
                render(d.tree);
                setTimeout(function(){
                    var ab = d.tree.abilities && d.tree.abilities[abilityId];
                    showUnlockEffect(ab ? ab.stat : null, true, abilityId);
                }, 80);
            } else { showToast(d.message || 'Failed', false); }
        })
        .catch(function(e){ _loading = false; showToast('Error: ' + e.message, false); });
    }

    function spendAdvMastery(key) {
        if (_loading) return;
        _loading = true;
        fetch('/api/pets/ability-tree/advantage-mastery', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ key:key, points:1 }),
        })
        .then(function(r){ return r.json(); })
        .then(function(d){
            _loading = false;
            if (d.ok) {
                showToast(d.message, true);
                render(d.tree);
                // re-select the adv node so panel refreshes
                setTimeout(function(){
                    if (_selectedNode && _selectedNode.type === 'adv' && _selectedNode.key === key) {
                        _refreshPanel();
                    }
                }, 80);
            } else { showToast(d.message || 'Failed', false); }
        })
        .catch(function(e){ _loading = false; showToast('Error: ' + e.message, false); });
    }

    function purchasePoint() {
        if (_loading) return;
        if (!confirm('Spend 500 levels to purchase 1 ability point? This cannot be undone!')) return;
        _loading = true;
        fetch('/api/pets/ability-tree/purchase', {
            method:'POST', headers:{'Content-Type':'application/json'},
        })
        .then(function(r){ return r.json(); })
        .then(function(d){
            _loading = false;
            if (d.ok) { showToast(d.message, true); render(d.tree); }
            else { showToast(d.message || 'Failed', false); }
        })
        .catch(function(e){ _loading = false; showToast('Error: ' + e.message, false); });
    }

    // ── Public API ────────────────────────────────────────────────────────────
    window.AbilityTree = {
        open: function() {
            var isMypet = new URLSearchParams(window.location.search).get('page') === 'mypet'
                       || !!document.getElementById('mypet-root');
            if (!isMypet) { console.warn('AbilityTree: mypet page only'); return; }
            ensureOverlay();
            var ov = el('ability-tree-overlay');
            if (ov) { ov.style.display = 'flex'; ov.classList.add('open'); }
            fetchTree(function(state){ render(state); });
        },
        close: function() {
            var ov = el('ability-tree-overlay');
            if (ov) { ov.style.display = 'none'; ov.classList.remove('open'); }
            _selectedNode = null;
        },
        cleanup: function() {
            var ov = el('ability-tree-overlay');
            if (ov) ov.remove();
            _selectedNode = null;
        },
        _spendMastery:   spendMastery,
        _unlockAbility:  unlockAbility,
        _spendAdvMastery: spendAdvMastery,
        _purchasePoint:  purchasePoint,
    };

})();

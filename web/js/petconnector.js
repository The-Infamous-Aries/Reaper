(function () {
'use strict';

// ── State ──────────────────────────────────────────────────────────────────
var _users       = [];   // enriched user+pet objects from API
var _currentUser = null; // entry where is_current_user === true
var _detailUserId = null; // which user's detail panel is open
var _giftTargetId = null; // target for the gift overlay

// ── Helpers ────────────────────────────────────────────────────────────────
function esc(s) {
    return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : ''; }
function el(id) { return document.getElementById(id); }
function petImg(sp)  { return '/static/Emojis/Pets/' + (sp||'Cat') + '.png'; }
function elemImg(e)  { return '/static/Emojis/Pets/Deco/' + cap(e||'basic') + '.png'; }

// Format large numbers: 3000→3k, 4530→4.53k, 1500000→1.5m, etc.
function fmtStat(n) {
    n = Number(n) || 0;
    var tiers = [
        [1e18, 'q'],
        [1e15, 'qa'],
        [1e12, 't'],
        [1e9,  'b'],
        [1e6,  'm'],
        [1e3,  'k'],
    ];
    for (var i = 0; i < tiers.length; i++) {
        if (n >= tiers[i][0]) {
            var val = n / tiers[i][0];
            var str = val >= 100 ? val.toFixed(0)
                    : val >= 10  ? val.toFixed(1).replace(/\.0$/, '')
                    :              val.toFixed(2).replace(/\.?0+$/, '');
            return str + tiers[i][1];
        }
    }
    return n.toLocaleString();
}
function catImg(c) {
    var m = {land:'Land',flying:'Flying',swimming:'Swimming',water:'Swimming',air:'Flying'};
    return '/static/Emojis/Pets/Deco/' + (m[(c||'land').toLowerCase()] || 'Land') + '.png';
}

// ── Relationship helpers ───────────────────────────────────────────────────
var REL = {
    best_friend: { label:'Best Friend', icon:'💚', color:'#4caf50', btnCls:'pc-rel-green'  },
    friend:      { label:'Friend',      icon:'💙', color:'#2196f3', btnCls:'pc-rel-blue'   },
    foe:         { label:'Foe',         icon:'🧡', color:'#ff9800', btnCls:'pc-rel-orange' },
    enemy:       { label:'Enemy',       icon:'❤️', color:'#f44336', btnCls:'pc-rel-red'    },
};
function relColor(t) { return (REL[t] || {}).color  || '#9e9e9e'; }
function relIcon(t)  { return (REL[t] || {}).icon   || '⚪'; }
function relLabel(t) { return (REL[t] || {}).label  || 'Neutral'; }

// ── API wrappers ───────────────────────────────────────────────────────────
function apiCall(url, opts) {
    return fetch(url, Object.assign({ credentials:'include', headers:{'Content-Type':'application/json'} }, opts||{}))
        .then(function(r){ return r.json(); })
        .catch(function(e){ console.error('API error', e); return null; });
}

// ── Small pet cards ────────────────────────────────────────────────────────
function buildCard(user) {
    var pet  = user.pet || {};
    var elem1 = pet.element  || 'basic';
    var elem2 = pet.element2 || '';
    var cat   = pet.category || 'land';
    var sp    = pet.species  || 'Cat';
    var lv    = pet.level    || 1;
    var stats = pet.computed_stats || {};
    var xpCur = pet.experience || 0;
    var xpMax = pet.xp_for_next_level || 100;
    var xpPct = Math.min(100, Math.round(xpCur / Math.max(1, xpMax) * 100));
    var rel   = user.relationship || null;

    return '<div class="col-xl-2 col-lg-3 col-md-4 col-sm-6">' +
        '<div class="pc-pet-card' + (rel ? ' pc-rel-border-' + rel : '') + '" style="' + (rel ? 'margin-bottom:14px' : '') + '" onclick="openDetail(\'' + esc(user.user_id) + '\')">' +

            // Avatar + name row
            '<div class="pc-card-top">' +
                '<img class="pc-card-avatar" src="' + esc(user.avatar_url) + '" onerror="this.src=\'/static/Emojis/Pets/Cat.png\'" alt="">' +
                '<div class="pc-card-names">' +
                    '<div class="pc-card-owner">' + esc(user.username) + '</div>' +
                    '<div class="pc-card-petname">' + esc(pet.name || 'Unnamed') + '</div>' +
                '</div>' +
                '<div class="pc-card-lv">Lv.' + lv + '</div>' +
            '</div>' +

            // Pet image + element badges
            '<div class="pc-card-img-wrap">' +
                '<img class="pc-card-pet-img" src="' + petImg(sp) + '" onerror="this.src=\'/static/Emojis/Pets/Cat.png\'" alt="' + esc(sp) + '">' +
                '<div class="pc-card-badges">' +
                    '<img class="pc-card-elem" src="' + elemImg(elem1) + '" title="' + cap(elem1) + '">' +
                    (elem2 ? '<img class="pc-card-elem" src="' + elemImg(elem2) + '" title="' + cap(elem2) + '">' : '') +
                    '<img class="pc-card-cat" src="' + catImg(cat) + '" title="' + cap(cat) + '">' +
                '</div>' +
            '</div>' +

            // Quick stats
            '<div class="pc-card-stats">' +
                '<div class="pc-mini-stat"><span class="pc-mini-lbl">HP</span><span class="pc-mini-val">' + fmtStat(stats.hp || stats.max_health || 100) + '</span></div>' +
                '<div class="pc-mini-stat"><span class="pc-mini-lbl">ATK</span><span class="pc-mini-val">' + fmtStat(stats.attack || 10) + '</span></div>' +
                '<div class="pc-mini-stat"><span class="pc-mini-lbl">DEF</span><span class="pc-mini-val">' + fmtStat(stats.defense || 5) + '</span></div>' +
            '</div>' +

            // XP bar
            '<div class="pc-card-xp">' +
                '<div class="pc-xp-track"><div class="pc-xp-fill" style="width:' + xpPct + '%"></div></div>' +
                '<div class="pc-xp-txt">' + fmtNum(xpCur) + '/' + fmtNum(xpMax) + ' XP</div>' +
            '</div>' +

            // Relationship tag (bottom outside border)
            (rel ? '<div class="pc-rel-tag" style="color:' + relColor(rel) + ';border-color:' + relColor(rel) + '">' + relLabel(rel) + '</div>' : '') +

        '</div></div>';
}

// ── Detail panel ───────────────────────────────────────────────────────────
function openDetail(userId) {
    var user = _users.find(function(u){ return u.user_id === userId; });
    if (!user) return;
    _detailUserId = userId;

    var pet   = user.pet || {};
    var elem1 = pet.element  || 'basic';
    var elem2 = pet.element2 || '';
    var cat   = pet.category || 'land';
    var sp    = pet.species  || 'Cat';
    var lv    = pet.level    || 1;
    var stats = pet.computed_stats || {};
    var xpCur = pet.experience || 0;
    var xpMax = pet.xp_for_next_level || 100;
    var xpPct = Math.min(100, Math.round(xpCur / Math.max(1, xpMax) * 100));
    var rel   = user.relationship || null;
    var mutual = user.mutual_relationship || {};
    var isMe  = !!user.is_current_user;

    // Spec tags
    var specs = (pet.specializations || pet.Spec || []);
    var specHtml = specs.length
        ? '<div class="pc-spec-tags">' + specs.map(function(s){ return '<span class="pc-spec-tag">' + esc(s) + '</span>'; }).join('') + '</div>'
        : '';

    var html =
        // Top: avatar + pet portrait + identity (matching MyPet layout)
        '<div class="pc-detail-hero">' +
            '<div class="pc-detail-portrait">' +
                '<img src="' + petImg(sp) + '" onerror="this.src=\'/static/Emojis/Pets/Cat.png\'" class="pc-detail-pet-img" alt="' + esc(sp) + '">' +
                (rel ? '<div class="pc-detail-rel-ring" style="border-color:' + relColor(rel) + ';box-shadow:0 0 14px ' + relColor(rel) + '60">' + relIcon(rel) + '</div>' : '') +
            '</div>' +
            '<div class="pc-detail-identity">' +
                '<div class="pc-detail-petname">' + esc(pet.name || 'Unnamed Pet') + '</div>' +
                '<div class="pc-detail-owner">' +
                    '<img src="' + esc(user.avatar_url) + '" onerror="this.src=\'/static/Emojis/Pets/Cat.png\'" class="pc-detail-owner-avatar" alt=""> ' +
                    esc(user.username) +
                '</div>' +
                '<div class="pc-detail-meta">' +
                    '<span class="pc-detail-lv">Lv. ' + lv + '</span>' +
                    '<img src="' + elemImg(elem1) + '" class="pc-detail-elem-icon" title="' + cap(elem1) + '">' +
                    (elem2 ? '<img src="' + elemImg(elem2) + '" class="pc-detail-elem-icon" title="' + cap(elem2) + '">' : '') +
                    '<img src="' + catImg(cat) + '" class="pc-detail-elem-icon" title="' + cap(cat) + '">' +
                '</div>' +
                '<div class="pc-detail-species">' + esc(sp) + '</div>' +
                specHtml +
            '</div>' +
        '</div>' +

        // XP bar
        '<div class="pc-detail-xp">' +
            '<div class="d-flex justify-content-between" style="font-size:0.72rem;color:var(--text-secondary);margin-bottom:3px">' +
                '<span>Experience</span><span>' + fmtNum(xpCur) + ' / ' + fmtNum(xpMax) + ' XP</span>' +
            '</div>' +
            '<div class="pc-xp-track"><div class="pc-xp-fill" style="width:' + xpPct + '%"></div></div>' +
        '</div>' +

        // Equipment section (matching MyPet)
        buildEquippedSection(pet) +

        // Equipment bonus section (matching MyPet)
        buildEquipBonusSection(pet) +

        // Base stats section (collapsible like MyPet)
        buildBaseStatsSection(pet) +

        // Combat stats section
        buildCombatStatsSection(pet) +

        // Breakdown section (collapsible like MyPet)
        buildBreakdownSection(pet, user) +

        // Relationship section (only for other users)
        (!isMe ? buildRelationshipSection(user, rel, mutual) : '') +

        // Gift button (only for other users)
        (!isMe ? '<div class="pc-detail-section"><button class="pc-rel-btn" style="color:var(--gold-secondary);border-color:rgba(255,215,0,0.4);width:100%" onclick="openGift(\'' + esc(userId) + '\')">🎁 Gift an Item</button></div>' : '');

    el('pc-detail-inner').innerHTML = html;
    el('pc-detail-overlay').style.display = 'flex';
    document.body.style.overflow = 'hidden';
}

function statBox(lbl, val, color) {
    return '<div class="pc-stat-box">' +
        '<div class="pc-stat-box-val" style="color:' + color + '">' + fmtStat(val) + '</div>' +
        '<div class="pc-stat-box-lbl">' + lbl + '</div>' +
    '</div>';
}
function baseRow(lbl, val) {
    return '<div class="pc-base-row"><span class="pc-base-lbl">' + lbl + '</span><span class="pc-base-val">' + val + '</span></div>';
}

// ── Equipment helpers (mirrors pet_brain.py StatsCalculator exactly) ─────────
function equipImgFile(item) {
    var name = (item && item.name) ? item.name : (typeof item === 'string' ? item : '');
    return name.toLowerCase().replace(/ /g, '_') + '.png';
}

function getEquipSetState(pet) {
    var eq    = pet.equipment || {};
    var level = parseInt(pet.level || 1, 10);
    // specs come from specializations or Spec array, uppercased
    var specs = (pet.specializations || pet.Spec || []).map(function(s){ return s.toUpperCase(); });

    // ── Collect typed items (mirrors Python logic) ────────────────────────────
    var items = [];  // [{t, item}]
    var mat = eq.Material;
    if (Array.isArray(mat)) {
        mat.forEach(function(m){ if (m && m.name) items.push({t:'Material', item:m}); });
    } else if (mat && typeof mat === 'object' && mat.name) {
        items.push({t:'Material', item:mat});
    }
    var gems = eq.Gems;
    if (Array.isArray(gems)) {
        gems.forEach(function(g){ if (g && g.name) items.push({t:'Gem', item:g}); });
    } else if (gems && typeof gems === 'object' && gems.name) {
        items.push({t:'Gem', item:gems});
    }
    var mons = eq.Monsters;
    if (Array.isArray(mons)) {
        mons.forEach(function(m){ if (m && m.name) items.push({t:'Monster', item:m}); });
    } else if (mons && typeof mons === 'object' && mons.name) {
        items.push({t:'Monster', item:mons});
    }
    var hat = eq.Hat;
    // Hat may be stored as a list (from backend) or a plain dict (legacy)
    if (Array.isArray(hat)) hat = hat[0] || null;
    var hatEquipped = !!(hat && typeof hat === 'object' && hat.name);
    if (hatEquipped) items.push({t:'Hat', item:hat});

    // ── Count duplicates ──────────────────────────────────────────────────────
    var matCounts = {}, gemCounts = {}, monCounts = {};
    items.forEach(function(e) {
        var n = (e.item.name || '').toLowerCase();
        if (!n) return;
        if (e.t === 'Material') matCounts[n] = (matCounts[n] || 0) + 1;
        else if (e.t === 'Gem')     gemCounts[n] = (gemCounts[n] || 0) + 1;
        else if (e.t === 'Monster') monCounts[n] = (monCounts[n] || 0) + 1;
    });

    var hasMatPair = Object.keys(matCounts).some(function(k){ return matCounts[k] >= 2; });
    var hasGemPair = Object.keys(gemCounts).some(function(k){ return gemCounts[k] >= 2; });
    var hasMonPair = Object.keys(monCounts).some(function(k){ return monCounts[k] >= 2; });

    // ── Hat spec matching — mirrors Python exactly ────────────────────────────
    // hat.bonuses is an object like {"ATT": 5, "DEF": 3}
    // hatSpecMatches = how many of those bonus keys are in the pet's specs
    var hatSpecMatches = 0;
    if (hatEquipped && specs.length) {
        var hatBonusStats = Object.keys((hat.bonuses) || {}).map(function(s){ return s.toUpperCase(); });
        hatSpecMatches = hatBonusStats.filter(function(s){ return specs.indexOf(s) !== -1; }).length;
    }

    // ── Set multiplier (mirrors Python) ──────────────────────────────────────
    var fullSet = hasMatPair && hasGemPair && hasMonPair && hatEquipped;
    var setMult;
    if (fullSet) {
        setMult = hatSpecMatches >= 2 ? 4 : 3;
    } else {
        setMult = 1;
    }
    var levelBonus = Math.floor(level / 50);
    var finalMult  = setMult + levelBonus;

    return {
        matPair: hasMatPair, gemPair: hasGemPair, monPair: hasMonPair,
        hatEquipped: hatEquipped, hatSpecMatches: hatSpecMatches,
        fullSet: fullSet, setMult: setMult, finalMult: finalMult,
        hatMatchesSpec: hatSpecMatches >= 1
    };
}

// ── Section builders (matching MyPet layout) ──────────────────────────────────
function buildEquippedSection(pet) {
    var eq = pet.equipment || {};
    var state = getEquipSetState(pet);

    var slots = [
        {type:'Monsters',idx:0,label:'Monster 1'},{type:'Gems',idx:0,label:'Gem 1'},
        {type:'Material',idx:0,label:'Material 1'},{type:'Hat',label:'Hat'},
        {type:'Material',idx:1,label:'Material 2'},{type:'Gems',idx:1,label:'Gem 2'},
        {type:'Monsters',idx:1,label:'Monster 2'}
    ];
    
    var html = '<div class="pc-detail-section">' +
        '<div class="pc-detail-section-title">⚔️ Equipped</div>' +
        '<div class="d-flex flex-wrap gap-1 mb-1" style="padding-bottom:18px">';
    
    slots.forEach(function(sl) {
        var item = sl.type==='Hat' ? (Array.isArray(eq.Hat) ? (eq.Hat[0]||null) : (eq.Hat||null)) : ((eq[sl.type]||[])[sl.idx]||null);
        var isEmpty = !item || !item.name;
        var src = isEmpty ? '/static/Emojis/Pets/Deco/Basic.png' : '/static/Emojis/Pets/Equipment/' + equipImgFile(item);

        if (isEmpty) {
            html += '<div class="pc-equip-slot pc-equip-empty" title="' + sl.label + ' (empty)">' +
                '<img src="' + src + '">' +
                '<span class="pc-slot-label">' + sl.label + '</span></div>';
        } else {
            var tip = item.name + ' (equipped)';
            
            // Determine glow tier for this slot
            var glowClass = '';
            if (state.fullSet) {
                glowClass = ' pc-equip-fullset';
            } else {
                var isPair = (sl.type === 'Monsters' && state.monPair) ||
                             (sl.type === 'Gems' && state.gemPair) ||
                             (sl.type === 'Material' && state.matPair) ||
                             (sl.type === 'Hat' && state.hatMatchesSpec);
                if (isPair) glowClass = ' pc-equip-pair';
            }

            html += '<div class="pc-equip-slot pc-equip-filled' + glowClass + '" title="' + esc(tip) + '">' +
                '<img src="' + src + '" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">' +
                '<span class="pc-slot-label">' + esc(item.name) + '</span></div>';
        }
    });
    
    return html + '</div></div>';
}

function buildEquipBonusSection(pet) {
    var state = getEquipSetState(pet);
    if (!state.matPair && !state.gemPair && !state.monPair && !state.hatEquipped) return '';

    var multColor = state.fullSet
        ? (state.hatSpecMatches >= 2 ? '#f59e0b' : '#a855f7')
        : '#57d9a3';

    var cardStyle = 'style="flex:0 0 auto;min-width:0;width:52px;padding:4px 6px"';
    var html = '<div class="pc-detail-section">' +
        '<div class="pc-detail-section-title">⚡ Equipment Bonus</div>' +
        '<div class="d-flex gap-1 mb-2" style="padding:4px 0;flex-wrap:nowrap">';
    
    html += '<div class="pc-mini-stat-card" ' + cardStyle + '>' +
        '<div class="pc-mini-label" style="font-size:0.58rem">Multi</div>' +
        '<div style="font-size:0.82rem;font-weight:700;color:' + multColor + '">x' + state.finalMult + '</div>' +
        '</div>';

    var checks = [
        {label:'🧵', ok: state.matPair},
        {label:'💎', ok: state.gemPair},
        {label:'👹', ok: state.monPair},
        {label:'👤', ok: state.hatEquipped},
        {label:'👥', ok: state.hatSpecMatches >= 2},
    ];
    checks.forEach(function(c) {
        html += '<div class="pc-mini-stat-card" ' + cardStyle + '>' +
            '<div style="font-size:1rem;line-height:1">' + c.label + '</div>' +
            '<div style="font-size:0.9rem">' + (c.ok ? '✅' : '❌') + '</div>' +
            '</div>';
    });
    
    return html + '</div></div>';
}

function buildBaseStatsSection(pet) {
    var statKeys = ['ATT','DEF','INT','DEX','HAP','ENE'];
    var specs = (pet.specializations || pet.Spec || []);
    var cs = pet.computed_stats || {};

    // Raw base stats: pet.ATT etc. (top-level, set by _migrate_pet).
    // computed_stats.ATT = base + equipment bonuses (the total).
    // We show raw base here. If pet.ATT is missing/0 but computed_stats.ATT exists,
    // back-calculate: base = total - equipment_bonus.
    var state = getEquipSetState(pet);

    var bodyId = 'pc-base-stats-body';
    var chevId = 'pc-base-stats-chev';

    var html = '<div class="pc-detail-section">' +
        '<div class="pc-collapse-header" onclick="pcToggleCollapse(\'' + bodyId + '\',\'' + chevId + '\')">' +
            '<span class="pc-detail-section-title" style="margin:0">📊 Base Stats</span>' +
            '<span id="' + chevId + '" class="pc-chev pc-chev-collapsed">▼</span>' +
        '</div>' +
        '<div id="' + bodyId + '" class="pc-collapse-body" style="display:none">' +
            '<div class="row g-1 mb-2">';

    statKeys.forEach(function(s) {
        // pet[s] is the raw base value stored at the top level of the pet object.
        // It may be a number, a string, or missing. Parse carefully.
        var raw = pet[s];
        var base;
        if (raw !== undefined && raw !== null && raw !== '') {
            base = parseInt(raw, 10);
            if (isNaN(base)) base = 0;
        } else {
            // Not present at top level — try to back-calculate from computed total
            // by subtracting the equipment bonus for this stat
            var total = cs[s] !== undefined ? parseInt(cs[s], 10) : 0;
            var equipBonus = calcEquipBonusForStat(pet, s, state);
            base = Math.max(0, total - equipBonus);
        }

        var isSp = specs.indexOf(s) !== -1;
        html += '<div class="col-6"><div class="pc-stat-row">' +
            '<img src="/static/Emojis/Pets/Deco/' + s + '.png" onerror="this.style.display=\'none\'" style="width:22px;height:22px;object-fit:contain">' +
            '<span class="' + (isSp ? 'pc-stat-special' : '') + '">' + s + ': ' + base + '</span>' +
            '</div></div>';
    });

    return html + '</div></div></div>';
}

// Calculate the equipment bonus for a single stat, mirroring Python logic
function calcEquipBonusForStat(pet, stat, state) {
    var eq = pet.equipment || {};
    var items = [];
    var mat = eq.Material;
    if (Array.isArray(mat)) {
        mat.forEach(function(m){ if (m && m.name) items.push({t:'Material', item:m}); });
    } else if (mat && typeof mat === 'object' && mat.name) {
        items.push({t:'Material', item:mat});
    }
    var gems = eq.Gems;
    if (Array.isArray(gems)) {
        gems.forEach(function(g){ if (g && g.name) items.push({t:'Gem', item:g}); });
    } else if (gems && typeof gems === 'object' && gems.name) {
        items.push({t:'Gem', item:gems});
    }
    var mons = eq.Monsters;
    if (Array.isArray(mons)) {
        mons.forEach(function(m){ if (m && m.name) items.push({t:'Monster', item:m}); });
    } else if (mons && typeof mons === 'object' && mons.name) {
        items.push({t:'Monster', item:mons});
    }
    var hat = eq.Hat;
    if (Array.isArray(hat)) hat = hat[0] || null;
    if (hat && typeof hat === 'object' && hat.name) items.push({t:'Hat', item:hat});

    var matCounts = {}, gemCounts = {}, monCounts = {};
    items.forEach(function(e) {
        var n = (e.item.name || '').toLowerCase();
        if (!n) return;
        if (e.t === 'Material') matCounts[n] = (matCounts[n] || 0) + 1;
        else if (e.t === 'Gem')     gemCounts[n] = (gemCounts[n] || 0) + 1;
        else if (e.t === 'Monster') monCounts[n] = (monCounts[n] || 0) + 1;
    });

    var level = parseInt(pet.level || 1, 10);
    var levelBonus = Math.floor(level / 50);
    var total = 0;

    items.forEach(function(e) {
        var bonuses = (e.item.bonuses) || {};
        var val = parseInt(bonuses[stat] || 0, 10);
        if (!val) return;
        var n = (e.item.name || '').toLowerCase();
        var itemMult;
        if (state.fullSet) {
            itemMult = state.finalMult;
        } else {
            var isPair = (e.t === 'Material' && (matCounts[n] || 0) >= 2) ||
                         (e.t === 'Gem'      && (gemCounts[n] || 0) >= 2) ||
                         (e.t === 'Monster'  && (monCounts[n] || 0) >= 2);
            itemMult = (isPair ? 2 : 1) + levelBonus;
        }
        total += val * itemMult;
    });
    return total;
}

function buildCombatStatsSection(pet) {
    var stats = pet.computed_stats || {};
    return '<div class="pc-detail-section">' +
        '<div class="pc-detail-section-title">⚔️ Combat Stats</div>' +
        '<div class="pc-detail-stats-grid">' +
            statBox('HP',  stats.hp  || stats.max_health || 100, '#4caf50') +
            statBox('ATK', stats.attack   || 10, '#f44336') +
            statBox('DEF', stats.defense  || 5,  '#2196f3') +
        '</div>' +
    '</div>';
}

function buildBreakdownSection(pet, user) {
    var bodyId = 'pc-breakdown-body';
    var chevId = 'pc-breakdown-chev';

    // ── XP Sources ────────────────────────────────────────────────────────────
    var xs = pet.xp_sources || {};
    var activities = [
        { label:'Play',    emoji:'🎮', keys:['play'] },
        { label:'Train',   emoji:'🏋️', keys:['training'] },
        { label:'Mission', emoji:'🎯', keys:['mission','mission_fail'] },
        { label:'Quest',   emoji:'📜', keys:['quest'] },
        { label:'Battle',  emoji:'⚔️', keys:['battle','npc_battle','pvp_battle'] },
    ];
    var xpRows = activities.map(function(a) {
        var net = a.keys.reduce(function(sum, k){ return sum + (xs[k] || 0); }, 0);
        return { label:a.label, emoji:a.emoji, net:net };
    }).filter(function(r){ return r.net !== 0; });

    var xpHtml = '';
    if (xpRows.length) {
        xpHtml += '<div class="pc-breakdown-sub">XP Sources</div><div class="d-flex gap-2 flex-wrap mb-2">';
        xpRows.forEach(function(r) {
            var cls = r.net >= 0 ? 'text-success' : 'text-danger';
            xpHtml += '<div class="pc-mini-stat-card">' +
                '<div class="pc-mini-label" style="font-size:0.7rem;display:flex;flex-direction:column;align-items:center;gap:1px">' +
                    '<span>' + r.emoji + '</span><span>' + r.label.toUpperCase() + '</span></div>' +
                '<div style="font-size:0.78rem;font-weight:700" class="' + cls + '">' + fmtXp(r.net) + ' XP</div>' +
                '</div>';
        });
        xpHtml += '</div>';
    }

    // ── Battle Records ────────────────────────────────────────────────────────
    var bs = pet.battle_stats || {};
    var battleTypes = [{key:'pvp',name:'PvP'},{key:'npc',name:'NPC'},{key:'wild_encounter',name:'Wild'},{key:'boss',name:'Boss'}];
    var battleHtml = '<div class="pc-breakdown-sub">Battle Records</div><div class="d-flex gap-2 flex-wrap mb-2">';
    battleTypes.forEach(function(bt) {
        var s = bs[bt.key] || {wins:0, losses:0};
        var wr = (s.wins + s.losses) > 0 ? ((s.wins / (s.wins + s.losses)) * 100).toFixed(0) : 0;
        battleHtml += '<div class="pc-mini-stat-card">' +
            '<div class="pc-mini-label">' + bt.name + '</div>' +
            '<div><span class="text-success" style="font-size:0.78rem;font-weight:700">' + (s.wins||0) + 'W</span>' +
            '<span style="color:var(--text-secondary);font-size:0.7rem"> / </span>' +
            '<span class="text-danger" style="font-size:0.78rem;font-weight:700">' + (s.losses||0) + 'L</span></div>' +
            '<div style="font-size:0.62rem;color:var(--text-secondary)">' + wr + '% WR</div>' +
            '</div>';
    });
    battleHtml += '</div>';

    // ── Casino ────────────────────────────────────────────────────────────────
    var gs = pet.gambling_stats || {};
    var games = [
        {key:'slots',     name:'Slots',    playedKey:'total_games_played'},
        {key:'blackjack', name:'BJ',       playedKey:'rounds_played'},
        {key:'holdem',    name:"Hold'em",  playedKey:'games_played'},
        {key:'craps',     name:'Craps',    playedKey:'games_played'},
        {key:'races',     name:'Races',    playedKey:'races_played'},
        {key:'coinflip',  name:'Coin Flip',playedKey:'games_played'},
        {key:'rps',       name:'RPS',      playedKey:'games_played'},
    ];
    var netByGame = {
        'Slots':    (xs.slots_win||0)     + (xs.slots_bet||0),
        'Races':    (xs.race_win||0)      + (xs.race_bet||0),
        'BJ':       (xs.blackjack_win||0) + (xs.blackjack_bet||0) + (xs.blackjack_double||0) + (xs.blackjack_split||0),
        'Craps':    (xs.craps_win||0)     + (xs.craps_bet||0),
        "Hold'em":  (xs.holdem_win||0)    + (xs.holdem_buyin||0)  + (xs.holdem_cashout||0),
        'Coin Flip':(xs.coinflip_win||0)  + (xs.minigame_bet||0),
        'RPS':      (xs.rps_win||0)       + (xs.rps_tie||0),
    };
    var playedGames = games.filter(function(g) {
        var s = gs[g.key] || {};
        var played = s[g.playedKey] || s.games_played || s.races_played || s.rounds_played || s.total_games_played || 0;
        return played > 0 || Math.abs(netByGame[g.name] || 0) > 0;
    });
    var casinoHtml = '';
    if (playedGames.length) {
        casinoHtml += '<div class="pc-breakdown-sub">Casino</div><div class="d-flex gap-2 flex-wrap mb-2">';
        playedGames.forEach(function(g) {
            var s = gs[g.key] || {};
            var played = s[g.playedKey] || s.games_played || s.races_played || s.rounds_played || s.total_games_played || 0;
            var wins   = s.games_won || s.races_won || s.rounds_won || 0;
            var net    = netByGame[g.name] || 0;
            var wr     = played > 0 ? ((wins / played) * 100).toFixed(0) : '—';
            casinoHtml += '<div class="pc-mini-stat-card">' +
                '<div class="pc-mini-label">' + g.name + '</div>' +
                (played ? '<div style="font-size:0.72rem;color:var(--text-secondary)">' + played + ' played</div>' : '') +
                (played ? '<div style="font-size:0.7rem">' + wr + '% WR</div>' : '') +
                '<div style="font-size:0.68rem" class="' + (net >= 0 ? 'text-success' : 'text-danger') + '">' + fmtXp(net) + ' XP</div>' +
                '</div>';
        });
        casinoHtml += '</div>';
    }

    // Show empty state if no data at all
    var hasData = xpRows.length || battleTypes.some(function(bt){ var s=bs[bt.key]||{}; return (s.wins||0)+(s.losses||0)>0; }) || playedGames.length;
    var innerHtml = hasData
        ? (xpHtml + battleHtml + casinoHtml)
        : '<div style="font-size:0.75rem;color:var(--text-secondary);padding:8px 0">No activity data yet.</div>';

    return '<div class="pc-detail-section">' +
        '<div class="pc-collapse-header" onclick="pcToggleCollapse(\'' + bodyId + '\',\'' + chevId + '\')">' +
            '<span class="pc-detail-section-title" style="margin:0">📈 Breakdown</span>' +
            '<span id="' + chevId + '" class="pc-chev pc-chev-collapsed">▼</span>' +
        '</div>' +
        '<div id="' + bodyId + '" class="pc-collapse-body" style="display:none">' +
            innerHtml +
        '</div>' +
    '</div>';
}

function fmtXp(n) {
    var abs = Math.abs(n);
    var sign = n < 0 ? '-' : '+';
    if (abs >= 1e12) return sign + (abs/1e12).toFixed(1).replace(/\.0$/,'') + 't';
    if (abs >= 1e9)  return sign + (abs/1e9 ).toFixed(1).replace(/\.0$/,'') + 'b';
    if (abs >= 1e6)  return sign + (abs/1e6 ).toFixed(1).replace(/\.0$/,'') + 'm';
    if (abs >= 1000) return sign + (abs/1000).toFixed(1).replace(/\.0$/,'') + 'k';
    return (n >= 0 ? '+' : '') + n;
}

// Compact number formatter without sign — for XP bar display
function fmtNum(n) {
    var abs = Math.abs(n);
    if (abs >= 1e15) return (n/1e15).toFixed(1).replace(/\.0$/,'') + 'q';
    if (abs >= 1e12) return (n/1e12).toFixed(1).replace(/\.0$/,'') + 't';
    if (abs >= 1e9)  return (n/1e9 ).toFixed(1).replace(/\.0$/,'') + 'b';
    if (abs >= 1e6)  return (n/1e6 ).toFixed(1).replace(/\.0$/,'') + 'm';
    if (abs >= 1000) return (n/1000).toFixed(1).replace(/\.0$/,'') + 'k';
    return String(n);
}

function buildRelationshipSection(user, rel, mutual) {
    // Mutual status info
    var mutualHtml = '';
    if (mutual.user_to_target || mutual.target_to_user) {
        mutualHtml =
            '<div class="pc-mutual-row">' +
                '<span>You → ' + esc(user.username) + ': <strong style="color:' + relColor(mutual.user_to_target) + '">' + relLabel(mutual.user_to_target) + ' ' + relIcon(mutual.user_to_target) + '</strong></span>' +
                '<span>' + esc(user.username) + ' → You: <strong style="color:' + relColor(mutual.target_to_user) + '">' + relLabel(mutual.target_to_user) + ' ' + relIcon(mutual.target_to_user) + '</strong></span>' +
            '</div>';
    }

    // Four relationship toggle buttons
    var btnRow = ['best_friend','friend','foe','enemy'].map(function(type) {
        var r = REL[type];
        var active = rel === type;
        return '<button class="pc-rel-btn ' + (active ? 'pc-rel-active' : '') + '" ' +
            'style="border-color:' + r.color + ';' + (active ? 'background:' + r.color + ';color:#fff' : 'color:' + r.color) + '" ' +
            'onclick="setRel(\'' + esc(user.user_id) + '\',\'' + type + '\')">' +
            r.icon + ' ' + r.label +
            '</button>';
    }).join('');

    var removeBtn = rel ? '<button class="pc-rel-btn" style="color:var(--text-secondary);border-color:rgba(255,255,255,0.2)" onclick="setRel(\'' + esc(user.user_id) + '\',null)">✕ Remove</button>' : '';

    return '<div class="pc-detail-section">' +
        '<div class="pc-detail-section-title">⚔️ Relationship</div>' +
        mutualHtml +
        '<div class="pc-rel-buttons">' + btnRow + removeBtn + '</div>' +
    '</div>';
}

// ── Collapse toggle functionality (matching MyPet) ────────────────────────────
window.pcToggleCollapse = function(bodyId, chevId) {
    var body = document.getElementById(bodyId);
    var chev = document.getElementById(chevId);
    if (!body) return;
    var open = body.style.display !== 'none';
    body.style.display = open ? 'none' : '';
    if (chev) {
        chev.className = open ? 'pc-chev pc-chev-collapsed' : 'pc-chev pc-chev-expanded';
        chev.textContent = open ? '▼' : '▲';
    }
};

window.closeDetail = function() {
    el('pc-detail-overlay').style.display = 'none';
    document.body.style.overflow = '';
    _detailUserId = null;
};

// Close on overlay click (outside panel)
el('pc-detail-overlay').addEventListener('click', function(e) {
    if (e.target === this) window.closeDetail();
});

// ── Relationship set / remove ──────────────────────────────────────────────
window.setRel = function(userId, type) {
    var user = _users.find(function(u){ return u.user_id === userId; });
    if (!user) return;

    var p;
    if (!type) {
        p = apiCall('/api/world/relationship/' + encodeURIComponent(userId), { method:'DELETE' });
    } else {
        p = apiCall('/api/world/relationship', {
            method: 'POST',
            body: JSON.stringify({ target_user_id: userId, relationship_type: type })
        });
    }

    p.then(function(r) {
        if (r && r.success) {
            user.relationship = type || null;
            // Refresh card
            renderPets();
            // Refresh detail panel if still open for this user
            if (_detailUserId === userId) openDetail(userId);
            showToast(r.message || 'Updated', 'success');
        } else {
            showToast((r && r.detail) || 'Failed', 'error');
        }
    });
};

// ── Gift overlay ───────────────────────────────────────────────────────────
window.openGift = function(userId) {
    _giftTargetId = userId;
    var target = _users.find(function(u){ return u.user_id === userId; });
    if (!target) return;

    el('pc-gift-title').textContent = '🎁 Gift Item to ' + (target.username || 'Unknown');

    var inv = (_currentUser && _currentUser.pet && _currentUser.pet.inventory) || [];
    var sel = el('pc-gift-select');
    sel.innerHTML = '<option value="">Choose an item…</option>';
    inv.forEach(function(item) {
        var opt = document.createElement('option');
        opt.value = item.name;
        opt.textContent = item.name + ' (x' + (item.quantity || 1) + ')';
        opt.dataset.qty = item.quantity || 1;
        sel.appendChild(opt);
    });

    el('pc-gift-qty').value = 1;
    el('pc-gift-qty').max = 1;
    el('pc-gift-overlay').style.display = 'flex';
};

window.pcUpdateGiftQty = function() {
    var sel = el('pc-gift-select');
    var opt = sel.options[sel.selectedIndex];
    var max = opt ? (parseInt(opt.dataset.qty) || 1) : 1;
    var inp = el('pc-gift-qty');
    inp.max = max;
    if (parseInt(inp.value) > max) inp.value = max;
};

window.closeGiftOverlay = function() {
    el('pc-gift-overlay').style.display = 'none';
    _giftTargetId = null;
};

window.pcSendGift = function() {
    var itemName = el('pc-gift-select').value;
    var qty      = parseInt(el('pc-gift-qty').value) || 1;
    if (!itemName || !_giftTargetId) { showToast('Select an item first', 'warning'); return; }

    el('pc-gift-send').textContent = 'Sending…';
    el('pc-gift-send').disabled = true;

    apiCall('/api/world/gift', {
        method: 'POST',
        body: JSON.stringify({ target_user_id: _giftTargetId, item_name: itemName, quantity: qty })
    }).then(function(r) {
        el('pc-gift-send').textContent = 'Send Gift';
        el('pc-gift-send').disabled = false;
        if (r && r.success) {
            showToast(r.message || 'Gift sent!', 'success');
            window.closeGiftOverlay();
            loadPets(); // refresh to update inventory
        } else {
            showToast((r && r.detail) || 'Failed to send gift', 'error');
        }
    });
};

function pcUpdateGiftQty() {
    var sel = el('pc-gift-select');
    var qty = el('pc-gift-qty');
    if (!sel || !qty) return;
    var itemName = sel.value;
    if (!itemName) { qty.max = 1; qty.value = 1; return; }
    qty.max = 10;
    qty.value = Math.min(parseInt(qty.value) || 1, parseInt(qty.max));
}

// ── Toast ──────────────────────────────────────────────────────────────────
function showToast(msg, type) {
    var bg = { success:'#4caf50', error:'#f44336', warning:'#ff9800' }[type] || '#2196f3';
    var wrap = document.querySelector('.pc-toast-wrap');
    if (!wrap) {
        wrap = document.createElement('div');
        wrap.className = 'pc-toast-wrap';
        wrap.style.cssText = 'position:fixed;top:1rem;right:1rem;z-index:99999;display:flex;flex-direction:column;gap:6px';
        document.body.appendChild(wrap);
    }
    var t = document.createElement('div');
    t.style.cssText = 'background:' + bg + ';color:#fff;padding:8px 14px;border-radius:6px;font-size:0.82rem;box-shadow:0 4px 12px rgba(0,0,0,0.4);transition:opacity 0.3s';
    t.textContent = msg;
    wrap.appendChild(t);
    setTimeout(function() { t.style.opacity = '0'; setTimeout(function(){ t.remove(); }, 350); }, 3000);
}

// ── Render grid ────────────────────────────────────────────────────────────
function renderPets() {
    var grid = el('pc-pets-grid');
    if (!grid) return;
    if (_users.length === 0) {
        grid.innerHTML = '<div class="col-12 text-center py-5" style="color:var(--text-secondary)">No pets found.</div>';
        return;
    }
    grid.innerHTML = _users.map(buildCard).join('');
}

function updateBadge() {
    var b = el('pc-count-badge');
    if (!b) return;
    var count = _users.length;
    b.textContent = count + ' pet' + (count === 1 ? '' : 's');
    b.style.display = count > 0 ? '' : 'none';
}

// ── Load data ──────────────────────────────────────────────────────────────
function loadPets() {
    el('pc-loading').style.display = '';
    el('pc-main').style.display    = 'none';
    el('pc-error').style.display   = 'none';

    apiCall('/api/world/pets').then(function(data) {
        if (!data || !data.users) {
            el('pc-loading').style.display = 'none';
            el('pc-error-msg').textContent = 'Failed to load pet data.';
            el('pc-error').style.display   = '';
            return;
        }
        _users       = data.users;
        _currentUser = _users.find(function(u){ return u.is_current_user; }) || null;

        renderPets();
        updateBadge();

        el('pc-loading').style.display = 'none';
        el('pc-main').style.display    = '';
    }).catch(function() {
        el('pc-loading').style.display = 'none';
        el('pc-error-msg').textContent = 'Network error — could not load pets.';
        el('pc-error').style.display   = '';
    });
}

// ── Expose globals ─────────────────────────────────────────────────────────
window.openDetail = openDetail;

// ── Boot ───────────────────────────────────────────────────────────────────
loadPets();

})();

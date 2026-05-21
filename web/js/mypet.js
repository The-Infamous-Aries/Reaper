(function () {
'use strict';

var ELEM_IMG_BASE = '/static/Emojis/Pets/Deco/';

// Format large numbers: 3000→3k, 4530→4.53k, 1500000→1.5m, etc.
function fmtStat(n) {
    n = Number(n) || 0;
    var tiers = [
        [1e18, 'q'],   // quintillion
        [1e15, 'qa'],  // quadrillion
        [1e12, 't'],   // trillion
        [1e9,  'b'],   // billion
        [1e6,  'm'],   // million
        [1e3,  'k'],   // thousand
    ];
    for (var i = 0; i < tiers.length; i++) {
        if (n >= tiers[i][0]) {
            var val = n / tiers[i][0];
            // Up to 2 significant decimal places, strip trailing zeros
            var str = val >= 100 ? val.toFixed(0)
                    : val >= 10  ? val.toFixed(1).replace(/\.0$/, '')
                    :              val.toFixed(2).replace(/\.?0+$/, '');
            return str + tiers[i][1];
        }
    }
    return n.toLocaleString();
}

var _pet = null;
var _adoptList = [];
var _adoptSel  = null;
var _adoptE1   = 'basic';
var _adoptE2   = '';
var _adoptE3   = '';
var _adoptCat  = 'land';
var ELEMENTS = ['Air','Basic','Electric','Fighting','Fire','Holy','Ice','Magic','Necro','Plant','Psychic','Rock','Water'];

var TYPE_INFO = {
    land:     { label:'Land',     img:'Land.png',     desc:'Deals +15% damage vs Swimming.' },
    flying:   { label:'Flying',   img:'Flying.png',   desc:'Deals +15% damage vs Land.' },
    swimming: { label:'Swimming', img:'Swimming.png', desc:'Deals +15% damage vs Flying.' }
};

var ELEM_INFO = {
    basic:    { label:'Basic',    img:'Basic.png',    strong:[], weak:[],                          desc:'Deals 0.9x to all elements. No strengths or weaknesses.' },
    fire:     { label:'Fire',     img:'Fire.png',     strong:['Ice','Plant','Necro'],              weak:['Water','Rock'],           desc:'Strong vs Ice, Plant, Necro. Weak to Water & Rock.' },
    water:    { label:'Water',    img:'Water.png',    strong:['Fire','Rock','Air'],                weak:['Electric','Plant'],       desc:'Strong vs Fire, Rock, Air. Weak to Electric & Plant.' },
    electric: { label:'Electric', img:'Electric.png', strong:['Water','Plant','Fighting'],        weak:['Rock','Air'],             desc:'Strong vs Water, Plant, Fighting. Weak to Rock & Air.' },
    ice:      { label:'Ice',      img:'Ice.png',      strong:['Air','Electric','Water'],          weak:['Fire','Rock','Fighting'], desc:'Strong vs Air, Electric, Water. Weak to Fire, Rock & Fighting.' },
    plant:    { label:'Plant',    img:'Plant.png',    strong:['Water','Air','Psychic'],           weak:['Fire','Ice','Necro'],     desc:'Strong vs Water, Air, Psychic. Weak to Fire, Ice & Necro.' },
    rock:     { label:'Rock',     img:'Rock.png',     strong:['Electric','Fire','Ice'],           weak:['Water','Air','Holy'],     desc:'Strong vs Electric, Fire, Ice. Weak to Water, Air & Holy.' },
    air:      { label:'Air',      img:'Air.png',      strong:['Rock','Fighting','Electric'],      weak:['Ice','Water','Plant'],    desc:'Strong vs Rock, Fighting, Electric. Weak to Ice, Water & Plant.' },
    magic:    { label:'Magic',    img:'Magic.png',    strong:['Psychic','Fighting','Fire'],       weak:['Necro','Holy'],           desc:'Strong vs Psychic, Fighting, Fire. Weak to Necro & Holy.' },
    holy:     { label:'Holy',     img:'Holy.png',     strong:['Necro','Magic','Rock'],            weak:['Psychic','Fighting'],     desc:'Strong vs Necro, Magic, Rock. Weak to Psychic & Fighting.' },
    necro:    { label:'Necro',    img:'Necro.png',    strong:['Holy','Magic','Plant'],            weak:['Fire','Psychic'],         desc:'Strong vs Holy, Magic, Plant. Weak to Fire & Psychic.' },
    psychic:  { label:'Psychic',  img:'Psychic.png',  strong:['Holy','Necro','Magic'],            weak:['Necro','Magic'],          desc:'Strong vs Holy, Necro, Magic. Weak to Necro & Magic.' },
    fighting: { label:'Fighting', img:'Fighting.png', strong:['Ice','Psychic','Holy'],            weak:['Electric','Air','Magic'], desc:'Strong vs Ice, Psychic, Holy. Weak to Electric, Air & Magic.' }
};

function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : ''; }
function petImg(sp)  { return '/static/Emojis/Pets/' + sp + '.png'; }
function elemImg(e)  { return elemImgPath(e); }
function catImg(cat) {
    var m = {water:'Swimming',swimming:'Swimming',flying:'Flying',land:'Land'};
    return ELEM_IMG_BASE + (m[(cat||'land').toLowerCase()] || 'Land') + '.png';
}
function elemImgPath(e) {
    if (!e) return ELEM_IMG_BASE + 'Basic.png';
    var info = ELEM_INFO[e.toLowerCase()];
    return ELEM_IMG_BASE + (info ? info.img : (cap(e) + '.png'));
}
function rc(r) { return ({Common:'#9e9e9e',Uncommon:'#4caf50',Rare:'#2196f3',Epic:'#9c27b0',Mythic:'#ff9800'})[r] || '#9e9e9e'; }
function show(id) { var e=document.getElementById(id); if(e) e.style.display=''; }
function hide(id) { var e=document.getElementById(id); if(e) e.style.display='none'; }
function el(id)   { return document.getElementById(id); }

// ── Equipment data cache (bonuses + emoji_file lookup) ────────────────────────
var _equipData = {};  // name.toLowerCase() → {bonuses, emoji_file, rarity, type}

function loadEquipData() {
    fetch('/api/equipment-data')
        .then(function(r){ return r.json(); })
        .then(function(d) {
            ['Materials','Gems','Monsters','Potions',
             'Hats','Rings','Helmets','Armor','Boots','Shields',
             'Daggers','Katanas','Swords','Axes','Hammers','Bows'].forEach(function(cat) {
                (d[cat]||[]).forEach(function(item) {
                    if (item && item.name) _equipData[item.name.toLowerCase()] = item;
                });
            });
        })
        .catch(function(){});
}

function getEquipItem(name) {
    return _equipData[(name||'').toLowerCase()] || null;
}

// Always resolve the correct emoji filename for an equipment item.
// Checks cached _equipData first, then falls back to the item's own emoji_file,
// then derives from name — preventing 404s for items whose names don't match filenames.
function equipImgFile(item) {
    var name = (item && item.name) ? item.name : (typeof item === 'string' ? item : '');
    var cached = getEquipItem(name);
    if (cached && cached.emoji_file) return cached.emoji_file;
    if (item && item.emoji_file) return item.emoji_file;
    return name.toLowerCase().replace(/ /g, '_') + '.png';
}

function bonusTooltip(item) {
    if (!item) return '';
    var bonuses = item.bonuses || {};
    var parts = Object.keys(bonuses).map(function(k){ return k+': +'+bonuses[k]; });
    if (!parts.length) return item.rarity || '';
    return parts.join(' | ') + (item.rarity ? ' · '+item.rarity : '');
}

// Client-side equipment bonus calculation
// MIRRORS pet_brain.py StatsCalculator._calculate_equipment_bonuses EXACTLY.
//   Main slots: Helmet, Armor, Boots, Ring, Shield, Weapon (1 each)
//   Ring sub-slots: Material (1), Monsters (2), Gems (2)
//   base_mult = slots_filled + set_bonus(3) + ring_sub_bonus + level_bonus
//   final_mult = base_mult * 2 if full_set else base_mult
function calcEquipBonuses(pet) {
    var STATS = ['ATT','DEF','INT','DEX','HAP','ENE'];
    var out = {ATT:0, DEF:0, INT:0, DEX:0, HAP:0, ENE:0};
    var state = getEquipSetState(pet);

    // Collect all equipped items
    var eq = pet.equipment || {};
    function _getSingle(key) {
        var v = eq[key];
        if (Array.isArray(v)) v = v[0] || null;
        return (v && v.name) ? v : null;
    }
    function _getList(key) {
        var v = eq[key] || [];
        if (!Array.isArray(v)) v = (v && v.name) ? [v] : [];
        return v.filter(function(i){ return i && i.name; });
    }

    var allItems = [];
    ['Helmet','Armor','Boots','Ring','Shield','Weapon'].forEach(function(k){
        var item = _getSingle(k);
        if (item) allItems.push(item);
    });
    var mat = _getSingle('Material');
    if (mat) allItems.push(mat);
    _getList('Monsters').forEach(function(m){ allItems.push(m); });
    _getList('Gems').forEach(function(g){ allItems.push(g); });

    // Sum raw bonuses (prefer cached equipment data, fallback to item's own bonuses)
    allItems.forEach(function(item) {
        var data = getEquipItem(item.name);
        var b = (data && data.bonuses) ? data.bonuses : (item.bonuses || {});
        STATS.forEach(function(stat) {
            var val = parseInt(b[stat] || 0, 10);
            if (!isNaN(val)) out[stat] += val;
        });
    });

    // Apply multiplier (full-set doubling already baked into state.finalMult)
    STATS.forEach(function(stat){ out[stat] = out[stat] * state.finalMult; });
    return out;
}

function init() {
    hide('mypet-empty'); hide('mypet-display'); hide('mypet-error'); show('mypet-loading');
    loadEquipData();
    // Restore any active cooldowns from the server (survives page reload)
    _restoreCooldowns();
    fetch('/api/user/pet')
        .then(function(r) { if(r.status===401){showLogin();return null;} return r.json(); })
        .then(function(d) {
            if(!d) return;
            hide('mypet-loading');
            if(d.has_pet && d.species) {
                _pet = d;
                renderPetCard(d);
                renderAllPanels(d);
                show('mypet-display');
                bindTabs();
                // Pre-fetch ability tree data so Stats tab has mastery info immediately.
                // openInline with the real mount id — the panel is hidden but the element exists.
                if (window.AbilityTree) {
                    window.AbilityTree.openInline('at-inline-mount');
                }
            } else {
                show('mypet-empty');
                bindAdoptBtn();
            }
        })
        .catch(function(err) {
            hide('mypet-loading');
            var e=el('mypet-error-msg'); if(e) e.textContent='Error: '+err.message;
            show('mypet-error');
        });
}

function showLogin() {
    hide('mypet-loading');
    var e=el('mypet-error-msg');
    if(e) e.innerHTML='Please <a href="/api/discord/login">log in with Discord</a> to view your pet.';
    show('mypet-error');
}

// ── Lightweight pet refresh ───────────────────────────────────────────────────
// Updates _pet, re-renders the pet card (stats/equipment/XP), and refreshes the
// inventory panel in-place — without rebuilding all tabs or resetting the active tab.
function _refreshPet(newPet) {
    if (!newPet) return;
    _pet = newPet;
    renderPetCard(newPet);
    // Refresh inventory panel content in-place (preserves active tab)
    var invPanel = el('panel-inventory');
    if (invPanel) invPanel.innerHTML = buildInventoryPanel(newPet);
    // Refresh reforge panel content in-place
    var rfPanel = el('panel-reforge');
    if (rfPanel) rfPanel.innerHTML = buildReforgePanel(newPet);
    // Refresh loot bar (keys + chests) in loot market panel in-place
    var mktPanel = el('panel-market');
    if (mktPanel) {
        var keysBar = mktPanel.querySelector('.mp-inv-keys-bar');
        var inv = newPet.inventory || [];
        var keyItems   = inv.filter(function(i){ return i.type === 'Key'; });
        var chestItems = inv.filter(function(i){ return i.type === 'Chest'; });
        var CHEST_COLORS = { chest1:'#9e9e9e', chest2:'#4caf50', chest3:'#2196f3', chest4:'#ff9800' };
        var newBar = '';
        if (keyItems.length || chestItems.length) {
            newBar = '<div class="mp-inv-keys-bar mb-3">';
            newBar += '<div style="font-size:0.65rem;color:var(--text-secondary);font-weight:600;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px">🗝️ Loot</div>';
            newBar += '<div class="d-flex flex-wrap gap-2">';
            keyItems.forEach(function(item) {
                var f = equipImgFile(item); var count = item.count || 1;
                newBar += '<div class="mp-key-badge" title="' + escHtml(item.name) + ' ×' + count + '">' +
                    '<img src="/static/Emojis/Pets/Equipment/' + f + '" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">' +
                    '<span class="mp-key-badge-count">×' + count + '</span>' +
                    '<span class="mp-key-badge-name">' + escHtml(item.name) + '</span></div>';
            });
            chestItems.forEach(function(item) {
                var f = equipImgFile(item); var count = item.count || 1;
                var chestKey = item.name.toLowerCase().replace(/\s/g,'');
                var chestColor = CHEST_COLORS[chestKey] || '#ffd700';
                newBar += '<div class="mp-key-badge mp-inv-clickable" style="border-color:' + chestColor + '40;cursor:pointer" ' +
                    'title="' + escHtml(item.name) + ' ×' + count + ' — Click to open" ' +
                    'onclick="window._mpInvClick(' + escArg(item.name) + ',\'Chest\',\'Open\',1,' + escArg(item.rarity||'Common') + ',' + count + ')">' +
                    '<img src="/static/Emojis/Pets/Equipment/' + f + '" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">' +
                    '<span class="mp-key-badge-count" style="color:' + chestColor + '">×' + count + '</span>' +
                    '<span class="mp-key-badge-name">' + escHtml(item.name) + '</span></div>';
            });
            newBar += '</div></div>';
        }
        if (keysBar) {
            if (newBar) { keysBar.outerHTML = newBar; }
            else { keysBar.remove(); }
        } else if (newBar) {
            var descCard = mktPanel.querySelector('.mp-battle-card');
            if (descCard) descCard.insertAdjacentHTML('afterend', newBar);
        }
    }
    // Refresh stat breakdown
    if (window._mpRefreshStatBreakdown) window._mpRefreshStatBreakdown(newPet);
}

function renderPetCard(pet) {
    var cat  = (pet.category||pet.type||'land').toLowerCase();
    var e1   = (pet.element||'basic').toLowerCase();
    var _raw2 = pet.element2;
    var e2   = (_raw2 && _raw2 !== 'none' && _raw2 !== 'null' && _raw2 !== 'basic' && String(_raw2).trim() !== '') ? String(_raw2).toLowerCase() : '';
    var sp   = pet.species||'Unknown';
    var cs   = pet.computed_stats||{};
    var specs= pet.specializations||pet.Spec||[];
    var xpMax= pet.xp_for_next_level || 1;
    var xpCur= pet.experience || 0;
    var xpPct= xpMax > 0 ? Math.min((xpCur / xpMax) * 100, 100).toFixed(1) : 0;
    var hdr = el('my-pet-header');
    if (hdr) {
        var level = parseInt(pet.level||1, 10);
        var rank     = Math.floor(level / 50);
        var rankImg  = Math.min(rank, 58);  // emoji caps at 58, but rank number continues forever
        var rankHtml = rank > 0
            ? '<img src="/static/Emojis/Pet Rank/'+rankImg+'.png" style="width:52px;height:52px;object-fit:contain;flex-shrink:0" title="Rank '+rank+'" onerror="this.style.display=\'none\'">'
            : '<div style="width:52px;height:52px;flex-shrink:0"></div>';

        hdr.innerHTML =
            '<div class="d-flex align-items-center justify-content-between gap-2" style="width:100%">'+
            '<img src="'+petImg(sp)+'" class="mp-pet-img" onerror="this.src=\'/static/Emojis/Pets/Basic.png\'">'+
            '<div style="flex:1;min-width:0">'+
            '<div class="fw-bold" style="font-family:Orbitron,sans-serif;color:var(--gold-primary);font-size:0.95rem;text-shadow:0 0 8px var(--gold-glow)">'+(pet.name||sp)+'</div>'+
            '<div class="d-flex align-items-center gap-1 mt-1 flex-wrap">'+
            '<span class="badge bg-warning text-dark" style="font-size:0.6rem">Lv.'+(pet.level||1)+'</span>'+
            '<img src="'+catImg(cat)+'" style="width:18px;height:18px;object-fit:contain" title="'+cap(cat)+'" onerror="this.style.display=\'none\'">'+
            '<span style="font-size:0.75rem;color:var(--text-secondary)">'+cap(cat)+'</span>'+
            '<span style="color:rgba(255,215,0,0.4);margin:0 2px">|</span>'+
            '<img src="'+elemImgPath(e1)+'" style="width:18px;height:18px;object-fit:contain" title="'+cap(e1)+'" onerror="this.style.display=\'none\'">'+
            '<span style="font-size:0.75rem;color:var(--gold-secondary)">'+cap(e1)+'</span>'+
            (e2 ? '<span style="color:rgba(255,215,0,0.4);margin:0 2px">/</span><img src="'+elemImgPath(e2)+'" style="width:18px;height:18px;object-fit:contain" title="'+cap(e2)+'" onerror="this.style.display=\'none\'"><span style="font-size:0.75rem;color:var(--gold-secondary)">'+cap(e2)+'</span>' : '')+
            '</div></div>'+
            rankHtml+
            '</div>';
    }
    var statKeys = ['ATT','DEF','INT','DEX','HAP','ENE'];
    var equipBonuses = calcEquipBonuses(pet);
    var statsHtml = '<div class="row g-1 mb-2">';
    statKeys.forEach(function(s) {
        var base = pet[s]||0;
        var bonus = equipBonuses[s]||0;
        var total = cs[s]!==undefined ? cs[s] : (base + bonus);
        var isSp = specs.indexOf(s) !== -1;
        var bonusStr = bonus > 0 ? ' <span style="font-size:0.65rem;color:#4caf50">(+'+bonus+')</span>' : '';
        statsHtml += '<div class="col-6"><div class="mp-stat-row">'+
            '<img src="/static/Emojis/Pets/Deco/'+s+'.png" onerror="this.style.display=\'none\'">'+
            '<span class="'+(isSp?'stat-special':'')+'">'+s+': '+total+'</span>'+bonusStr+
            '</div></div>';
    });
    statsHtml += '</div>';

    // Combat stats — same formulas as pet_brain.py, using equipment-adjusted stats
    var eb   = calcEquipBonuses(pet);
    var att  = (cs.ATT!==undefined ? cs.ATT : (pet.ATT||0)) + (cs.ATT!==undefined ? 0 : (eb.ATT||0));
    var def  = (cs.DEF!==undefined ? cs.DEF : (pet.DEF||0)) + (cs.DEF!==undefined ? 0 : (eb.DEF||0));
    var int_ = (cs.INT!==undefined ? cs.INT : (pet.INT||0)) + (cs.INT!==undefined ? 0 : (eb.INT||0));
    var dex  = (cs.DEX!==undefined ? cs.DEX : (pet.DEX||0)) + (cs.DEX!==undefined ? 0 : (eb.DEX||0));
    var hap  = (cs.HAP!==undefined ? cs.HAP : (pet.HAP||0)) + (cs.HAP!==undefined ? 0 : (eb.HAP||0));
    var ene  = (cs.ENE!==undefined ? cs.ENE : (pet.ENE||0)) + (cs.ENE!==undefined ? 0 : (eb.ENE||0));
    var atk  = cs.attack    !== undefined ? cs.attack    : (att + dex);
    var dfn  = cs.defense   !== undefined ? cs.defense   : (def + int_);
    var hp   = cs.max_health !== undefined ? cs.max_health : Math.floor(((att+def+int_+dex+hap+ene)/6 + hap*ene)*10);

    var combatHtml =
        '<div class="mp-combat-row">'+
        '<span class="mp-combat-item"><span class="mp-combat-label">⚔️ ATK</span><span class="mp-combat-val">'+fmtStat(atk)+'</span></span>'+
        '<span class="mp-combat-item"><span class="mp-combat-label">🛡️ DEF</span><span class="mp-combat-val">'+fmtStat(dfn)+'</span></span>'+
        '<span class="mp-combat-item"><span class="mp-combat-label">❤️ HP</span><span class="mp-combat-val">'+fmtStat(hp)+'</span></span>'+
        '</div>';
    var xpHtml =
        '<div class="mp-xp-bar-wrap mb-1"><div class="mp-xp-bar" style="width:'+xpPct+'%"></div></div>'+
        '<div style="font-size:0.68rem;color:var(--text-secondary);text-align:right">'+xpCur.toLocaleString()+' / '+xpMax.toLocaleString()+' XP</div>';
    var body = el('my-pet-body');
    if (body) body.innerHTML = xpHtml + buildEquipped(pet) + '<hr class="mp-divider my-2">' + statsHtml + combatHtml + buildFriendFoeCard();
}

function bindTabs() {}

// Expose _pet globally so ability_tree.js can trigger a stat breakdown refresh
Object.defineProperty(window, '_pet', {
    get: function() { return _pet; },
    set: function(v) { _pet = v; },
    configurable: true
});

// Called by ability_tree.js after tree data loads to refresh mastery column
window._mpRefreshStatBreakdown = function(pet) {
    var panel = el('panel-breakdown');
    if (!panel) return;
    // Replace just the stat breakdown section (first child after the description card)
    var existing = panel.querySelector('.mp-stat-breakdown-wrap');
    if (existing) {
        var fresh = document.createElement('div');
        fresh.innerHTML = buildFullStatBreakdown(pet);
        existing.parentNode.replaceChild(fresh.firstChild, existing);
    }
};

function renderAllPanels(pet) {
    var c = el('pet-tab-content');
    if (!c) return;
    c.innerHTML = buildInteractions(pet);
}

function buildInteractions(pet) {
    var acts = pet.action_labels || {};
    var atkVal = acts.attack  || (pet.actions && (pet.actions.Attack||pet.actions.attack)) || '';
    var defVal = acts.defend  || acts.defense || (pet.actions && (pet.actions.Defense||pet.actions.defense)) || '';
    var chgVal = acts.charge  || (pet.actions && (pet.actions.Charge||pet.actions.charge)) || '';

    var LOCATIONS = ['Camp','Bonfire','Beach','Forest','Hot Air Balloon','Cruiseship','Mountain','Gym','Graveyard','Festival','Glacier','Pyramids'];
    var LOC_EMOJI = {Camp:'camping',Bonfire:'bonfire',Beach:'beach',Forest:'forest','Hot Air Balloon':'hotairballoon',Cruiseship:'cruiseship',Mountain:'mountain',Gym:'gym',Graveyard:'graveyard',Festival:'festival',Glacier:'glacier',Pyramids:'pyramids'};

    var tabs = [
        {id:'breakdown', label:'Stats',       icon:'stats.png'},
        {id:'abilities', label:'Abilities',   icon:'ability.png'},
        {id:'inventory', label:'Inventory',   icon:'inventory.png'},
        {id:'reforge',   label:'Reforge',     icon:'forge.png'},
        {id:'market',    label:'Loot Market', icon:'market.png'},
        {id:'train',     label:'Train',       icon:'train.png'},
        {id:'mission',   label:'Mission',     icon:'mission.png'},
        {id:'play',      label:'Play',        icon:'play.png'},
        {id:'quest',     label:'Quest',       icon:'quest.png'},
        {id:'rename',    label:'Rename',      icon:'rename.png'},
        {id:'kill',      label:'Kill Pet',    icon:'kill.png'}
    ];

    var html = '<div class="d-flex gap-2 mb-4 flex-wrap">';
    tabs.forEach(function(t, i) {
        html += '<button class="mp-action-tab-img'+(i===0?' active':'')+'" id="tab-'+t.id+'" onclick="window._mpTab(\''+t.id+'\')">' +
            '<img src="/static/Emojis/MyPet/'+t.icon+'" class="mp-tab-icon" onerror="this.style.display=\'none\'">' +
            '<span>'+t.label+'</span></button>';
    });
    html += '</div>';

    // ── Stats Breakdown (first — shown by default) ──────────────────────────
    html += '<div id="panel-breakdown">'+
        '<div class="mp-section-title">📊 Stats Breakdown</div>'+
        '<div class="mp-battle-card mb-3" style="font-size:0.82rem;color:var(--text-secondary)">'+
        'XP earned across all activities, plus battle records, Survivor Series, casino results, and pet stocks.'+
        '</div>'+
        buildFullStatBreakdown(pet)+
        '<hr class="mp-divider my-2">'+
        '<div id="breakdown-panel-body">'+buildBreakdownPanel(pet)+'</div>'+
        buildTokenStatsPanel(pet)+
        '</div>';

    // ── Abilities (inline tab — loaded on demand) ──────────────────────────
    html += '<div id="panel-abilities" style="display:none">'+
        '<div id="at-inline-mount" style="min-height:200px;display:block">'+
        '<div style="text-align:center;padding:30px;color:var(--text-secondary);font-size:0.82rem">Loading abilities…</div>'+
        '</div>'+
        '</div>';

    // ── Inventory ─────────────────────────────────────────────────────────
    html += '<div id="panel-inventory" style="display:none">'+
        buildInventoryPanel(pet)+
        '</div>';

    // ── Reforge ────────────────────────────────────────────────────────────
    html += '<div id="panel-reforge" style="display:none">'+
        buildReforgePanel(pet)+
        '</div>';

    // ── Loot Market ────────────────────────────────────────────────────────
    var CHEST_INFO = {
        chest1:{label:'Chest 1',cost:'1× Key1',items:'1 Common or Uncommon item',color:'#9e9e9e'},
        chest2:{label:'Chest 2',cost:'1× Key2',items:'1 Rare item',color:'#4caf50'},
        chest3:{label:'Chest 3',cost:'1× Key3',items:'1 Epic item',color:'#2196f3'},
        chest4:{label:'Chest 4',cost:'1× Key1 + Key2 + Key3',items:'1 picked type + 1 Uncommon+',color:'#ff9800'}
    };
    // Build keys+chests bar for loot market
    var lmKeysBar = (function() {
        var inv = pet.inventory || [];
        var keyItems   = inv.filter(function(i){ return i.type === 'Key'; });
        var chestItems = inv.filter(function(i){ return i.type === 'Chest'; });
        if (!keyItems.length && !chestItems.length) return '';
        var CHEST_COLORS = { chest1:'#9e9e9e', chest2:'#4caf50', chest3:'#2196f3', chest4:'#ff9800' };
        var bar = '<div class="mp-inv-keys-bar mb-3">';
        bar += '<div style="font-size:0.65rem;color:var(--text-secondary);font-weight:600;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px">🗝️ Loot</div>';
        bar += '<div class="d-flex flex-wrap gap-2">';
        keyItems.forEach(function(item) {
            var f = equipImgFile(item);
            var count = item.count || 1;
            bar += '<div class="mp-key-badge" title="' + escHtml(item.name) + ' ×' + count + '">' +
                '<img src="/static/Emojis/Pets/Equipment/' + f + '" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">' +
                '<span class="mp-key-badge-count">×' + count + '</span>' +
                '<span class="mp-key-badge-name">' + escHtml(item.name) + '</span>' +
                '</div>';
        });
        chestItems.forEach(function(item) {
            var f = equipImgFile(item);
            var count = item.count || 1;
            var chestKey = item.name.toLowerCase().replace(/\s/g,'');
            var chestColor = CHEST_COLORS[chestKey] || '#ffd700';
            bar += '<div class="mp-key-badge mp-inv-clickable" ' +
                'style="border-color:' + chestColor + '40;cursor:pointer" ' +
                'title="' + escHtml(item.name) + ' ×' + count + ' — Click to open" ' +
                'onclick="window._mpInvClick(' + escArg(item.name) + ',\'Chest\',\'Open\',1,' + escArg(item.rarity||'Common') + ',' + count + ')">' +
                '<img src="/static/Emojis/Pets/Equipment/' + f + '" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">' +
                '<span class="mp-key-badge-count" style="color:' + chestColor + '">×' + count + '</span>' +
                '<span class="mp-key-badge-name">' + escHtml(item.name) + '</span>' +
                '</div>';
        });
        bar += '</div></div>';
        return bar;
    })();
    html += '<div id="panel-market" style="display:none">'+
        '<div class="mp-section-title">📦 Loot Market</div>'+
        '<div class="mp-battle-card mb-3" style="font-size:0.82rem;color:var(--text-secondary)">'+
        'Spend keys to open chests and earn items. Keys are earned from Play, Mission, and Quest activities.'+
        '</div>'+
        lmKeysBar+
        '<div class="row g-2 mb-3">'+
        Object.keys(CHEST_INFO).map(function(c){
            var info=CHEST_INFO[c];
            return '<div class="col-md-3 col-sm-6"><div class="mp-mini-stat-card" style="cursor:pointer;transition:all 0.2s;border-color:'+info.color+'40" id="lm-'+c+'" onclick="window._mpSelectLmChest(\''+c+'\')">'+
                '<img src="/static/Emojis/Pets/Equipment/'+c+'.png" style="width:32px;height:32px;object-fit:contain;margin-bottom:4px" onerror="this.style.display=\'none\'">'+
                '<div class="mp-mini-label" style="color:'+info.color+'">'+info.label+'</div>'+
                '<div style="font-size:0.72rem;color:var(--text-secondary);margin-top:2px">'+
                    info.cost.replace('Key1','<img src="/static/Emojis/Pets/Equipment/Key1.png" style="width:14px;height:14px;vertical-align:middle"> Key1')
                             .replace('Key2','<img src="/static/Emojis/Pets/Equipment/Key2.png" style="width:14px;height:14px;vertical-align:middle"> Key2')
                             .replace('Key3','<img src="/static/Emojis/Pets/Equipment/Key3.png" style="width:14px;height:14px;vertical-align:middle"> Key3')+
                '</div>'+
                '<div style="font-size:0.7rem;color:var(--gold-secondary);margin-top:2px">'+info.items+'</div>'+
                '</div></div>';
        }).join('')+
        '</div>'+
        '<div id="lm-type-row" style="display:none" class="mb-3">'+
        '<label class="form-label" style="font-size:0.8rem;color:var(--text-secondary)">Select guaranteed item type (Chest 4)</label>'+
        '<div class="d-flex gap-2 flex-wrap">'+
        ['Material','Gem','Monster','Potion','Hat'].map(function(t){
            return '<div class="mp-mini-stat-card" style="cursor:pointer;transition:all 0.2s;padding:5px 10px" id="lm-type-'+t+'" onclick="window._mpSelectLmType(\''+t+'\')">'+
                '<div class="mp-mini-label">'+t+'</div></div>';
        }).join('')+
        '</div></div>'+
        '<div id="lm-amt-row" class="mb-3">'+
        '<label class="form-label" style="font-size:0.8rem;color:var(--text-secondary)">Amount to open</label>'+
        '<input type="number" class="form-control mp-input" id="lm-amount" min="1" max="10" value="1" style="max-width:100px">'+
        '</div>'+
        '<button class="mp-adopt-btn" onclick="window._mpOpenChest()">📦 Open Chest</button>'+
        '<div id="lm-result" class="mt-3"></div>'+
        '</div>';

    // ── Train ──────────────────────────────────────────────────────────────
    html += '<div id="panel-train" style="display:none">'+
        '<div class="mp-section-title">Train Your Pet</div>'+
        '<div class="mp-battle-card mb-3" style="font-size:0.82rem;color:var(--text-secondary)">'+
        'Send your pet to train and earn XP. Higher difficulty = more XP but lower success rate.'+
        '</div>'+
        '<div class="row g-2 mb-3">'+
        ['Easy','Average','Hard'].map(function(d) {
            var xp = {Easy:'50+',Average:'100+',Hard:'200+'}[d];
            var chance = {Easy:'90%',Average:'70%',Hard:'50%'}[d];
            return '<div class="col-md-4"><div class="mp-mini-stat-card" style="cursor:pointer;transition:all 0.2s" id="train-opt-'+d+'" onclick="window._mpSelectTrain(\''+d+'\')">'+
                '<div class="mp-mini-label">'+d+'</div>'+
                '<div style="font-size:0.78rem;color:var(--gold-secondary);font-weight:700">'+xp+' XP</div>'+
                '<div style="font-size:0.7rem;color:var(--text-secondary)">'+chance+' success</div>'+
                '</div></div>';
        }).join('')+
        '</div>'+
        '<div style="font-size:0.68rem;color:var(--text-secondary);margin-bottom:8px">⚡ XP scales with your pet\'s level (+10% per level above 1). 5 sec cooldown.</div>'+
        '<button class="mp-adopt-btn" id="train-btn" onclick="window._mpTrain()">Start Training</button>'+
        '<div id="train-result" class="mt-3"></div>'+
        '</div>';

    // ── Mission ────────────────────────────────────────────────────────────
    html += '<div id="panel-mission" style="display:none">'+
        '<div class="mp-section-title">Send on Mission</div>'+
        '<div class="mp-battle-card mb-3" style="font-size:0.82rem;color:var(--text-secondary)">'+
        'Missions reward more XP and keys. Optionally gamble XP — win it back doubled on success, lose it on failure.'+
        '</div>'+
        '<div class="row g-2 mb-3">'+
        ['Easy','Average','Hard'].map(function(d) {
            var xp = {Easy:'100+',Average:'250+',Hard:'500+'}[d];
            var chance = {Easy:'70%',Average:'50%',Hard:'30%'}[d];
            var keys = {Easy:'33% Key1',Average:'Key1+Key2',Hard:'Key1+Key2+Key3'}[d];
            return '<div class="col-md-4"><div class="mp-mini-stat-card" style="cursor:pointer;transition:all 0.2s" id="mission-opt-'+d+'" onclick="window._mpSelectMission(\''+d+'\')">'+
                '<div class="mp-mini-label">'+d+'</div>'+
                '<div style="font-size:0.78rem;color:var(--gold-secondary);font-weight:700">'+xp+' XP</div>'+
                '<div style="font-size:0.7rem;color:var(--text-secondary)">'+chance+' success</div>'+
                '<div style="font-size:0.65rem;color:var(--text-secondary)">'+keys+'</div>'+
                '</div></div>';
        }).join('')+
        '</div>'+
        '<div style="font-size:0.68rem;color:var(--text-secondary);margin-bottom:8px">⚡ XP scales with your pet\'s level (+10% per level above 1). 5 sec cooldown.</div>'+
        '<div class="mb-3">'+
        '<label class="form-label" style="font-size:0.8rem;color:var(--text-secondary)">Gamble XP <small>(optional — risk XP for bonus reward)</small></label>'+
        '<input type="number" class="form-control mp-input" id="mission-gamble" min="0" placeholder="0" style="max-width:160px">'+
        '</div>'+
        '<button class="mp-adopt-btn" id="mission-btn" onclick="window._mpMission()">Launch Mission</button>'+
        '<div id="mission-result" class="mt-3"></div>'+
        '</div>';

    // ── Play ───────────────────────────────────────────────────────────────
    html += '<div id="panel-play" style="display:none">'+
        '<div class="mp-section-title">Take Your Pet to Play</div>'+
        '<div class="mp-battle-card mb-3" style="font-size:0.82rem;color:var(--text-secondary)">'+
        'XP = 5 × Level × element bonus. Matching your pet\'s element to the location gives 2x or 3x XP and better keys.'+
        '</div>'+
        '<div class="row g-2 mb-3">'+
        LOCATIONS.map(function(loc) {
            var deco = LOC_EMOJI[loc] || 'camping';
            return '<div class="col-md-3 col-sm-4 col-6"><div class="mp-mini-stat-card" style="cursor:pointer;transition:all 0.2s" id="play-opt-'+loc.replace(/ /g,'-')+'" onclick="window._mpSelectPlay(\''+loc+'\')">'+
                '<img src="/static/Emojis/Pets/Deco/'+deco+'.png" style="width:28px;height:28px;object-fit:contain;margin-bottom:3px" onerror="this.style.display=\'none\'">'+
                '<div class="mp-mini-label">'+loc+'</div>'+
                '</div></div>';
        }).join('')+
        '</div>'+
        '<button class="mp-adopt-btn" id="play-btn" onclick="window._mpPlay()">Go Play!</button>'+
        '<div id="play-result" class="mt-3"></div>'+
        '</div>';

    // ── Quest ──────────────────────────────────────────────────────────────
    var QLOC_EMOJI = {Camp:'camping',Bonfire:'bonfire',Beach:'beach',Forest:'forest','Hot Air Balloon':'hotairballoon',Cruiseship:'cruiseship',Mountain:'mountain',Gym:'gym',Graveyard:'graveyard',Festival:'festival',Glacier:'glacier',Pyramids:'pyramids'};
    html += '<div id="panel-quest" style="display:none">'+
        '<div class="mp-section-title">⚔️ Quest</div>'+
        '<div class="mp-battle-card mb-3" style="font-size:0.82rem;color:var(--text-secondary)">'+
        'AI-generated 5-stage quests. Each stage presents a challenge with 3 choices tied to your pet\'s stats. Earn XP and loot along the way.<br>'+
        '<span style="color:var(--gold-secondary)">Quests are generated by AI — may take a moment to start.</span>'+
        '</div>'+
        '<div id="quest-setup">'+
        '<div class="row g-2 mb-3">'+
        '<div class="col-md-6">'+
        '<label class="form-label" style="font-size:0.8rem;color:var(--text-secondary)">Location</label>'+
        '<div class="row g-1">'+
        LOCATIONS.map(function(loc) {
            var deco = QLOC_EMOJI[loc] || 'camping';
            return '<div class="col-4"><div class="mp-mini-stat-card" style="cursor:pointer;transition:all 0.2s;padding:4px" id="qloc-'+loc.replace(/ /g,'-')+'" onclick="window._mpSelectQLoc(\''+loc+'\')">'+
                '<img src="/static/Emojis/Pets/Deco/'+deco+'.png" style="width:22px;height:22px;object-fit:contain" onerror="this.style.display=\'none\'">'+
                '<div class="mp-mini-label" style="font-size:0.58rem">'+loc+'</div>'+
                '</div></div>';
        }).join('')+
        '</div></div>'+
        '<div class="col-md-6">'+
        '<label class="form-label" style="font-size:0.8rem;color:var(--text-secondary)">Difficulty</label>'+
        '<div class="d-flex flex-column gap-2">'+
        [['Apprentice','Easy — lower stat requirements, smaller rewards'],
         ['Journeyman','Medium — balanced challenge and rewards'],
         ['Senior','Hard — high stat requirements, best loot']].map(function(d) {
            return '<div class="mp-mini-stat-card" style="cursor:pointer;transition:all 0.2s;text-align:left;padding:6px 10px" id="qdiff-'+d[0]+'" onclick="window._mpSelectQDiff(\''+d[0]+'\')">'+
                '<div class="mp-mini-label">'+d[0]+'</div>'+
                '<div style="font-size:0.68rem;color:var(--text-secondary)">'+d[1]+'</div>'+
                '</div>';
        }).join('')+
        '</div></div></div>'+
        '<button class="mp-adopt-btn" id="quest-start-btn" onclick="window._mpQuestStart()">⚔️ Begin Quest</button>'+
        '<div id="quest-start-result" class="mt-2"></div>'+
        '</div>'+
        '<div id="quest-active" style="display:none">'+
        '<div class="mp-battle-card mb-3" id="quest-stage-box">'+
        '<div id="quest-progress" style="font-size:0.7rem;color:var(--text-secondary);margin-bottom:6px"></div>'+
        '<div id="quest-stage-name" class="mp-section-title" style="margin-bottom:6px"></div>'+
        '<div id="quest-event" style="font-size:0.85rem;color:var(--text-primary);margin-bottom:12px;line-height:1.5"></div>'+
        '<div id="quest-choices" class="d-flex flex-column gap-2"></div>'+
        '</div>'+
        '<div id="quest-outcome" class="mt-2"></div>'+
        '<div id="quest-xp-track" style="font-size:0.75rem;color:var(--gold-secondary);margin-top:4px"></div>'+
        '<button class="mp-adopt-btn" onclick="window._mpQuestAbandon()" style="font-size:0.72rem;padding:5px 12px;margin-top:8px;background:rgba(231,76,60,0.15);border-color:rgba(231,76,60,0.4);color:#e74c3c">🚪 Abandon Quest</button>'+
        '</div>'+
        '<div id="quest-result" style="display:none"></div>'+
        '</div>';

    // ── Rename ─────────────────────────────────────────────────────────────
    html += '<div id="panel-rename" style="display:none">'+
        '<div class="mp-section-title">Rename Pet &amp; Battle Actions</div>'+
        '<div class="mb-3">'+
        '<label class="form-label" style="font-size:0.82rem;color:var(--text-secondary)">Pet Name</label>'+
        '<input type="text" class="form-control mp-input" id="rename-name" maxlength="32" value="'+escHtml(pet.name||'')+'" placeholder="Enter new name">'+
        '<div class="invalid-feedback" id="rename-name-err"></div>'+
        '</div>'+
        '<div class="mb-3">'+
        '<label class="form-label" style="font-size:0.82rem;color:var(--text-secondary)">Battle Actions <small style="color:var(--text-secondary)">(leave blank to keep current)</small></label>'+
        '<div class="row g-2">'+
        '<div class="col-md-4"><label class="form-label" style="font-size:0.75rem;color:var(--gold-secondary)">⚔️ Attack</label>'+
        '<input type="text" class="form-control mp-input" id="rename-atk" maxlength="32" value="'+escHtml(atkVal)+'" placeholder="Attack action"></div>'+
        '<div class="col-md-4"><label class="form-label" style="font-size:0.75rem;color:var(--gold-secondary)">🛡️ Defense</label>'+
        '<input type="text" class="form-control mp-input" id="rename-def" maxlength="32" value="'+escHtml(defVal)+'" placeholder="Defense action"></div>'+
        '<div class="col-md-4"><label class="form-label" style="font-size:0.75rem;color:var(--gold-secondary)">⚡ Charge</label>'+
        '<input type="text" class="form-control mp-input" id="rename-chg" maxlength="32" value="'+escHtml(chgVal)+'" placeholder="Charge action"></div>'+
        '</div></div>'+
        '<button class="mp-adopt-btn" onclick="window._mpRename()">Save Changes</button>'+
        '<div id="rename-result" class="mt-3"></div>'+
        '</div>';

    // ── Kill ───────────────────────────────────────────────────────────────
    html += '<div id="panel-kill" style="display:none">'+
        '<div class="mp-section-title" style="color:#e74c3c">💀 Release Pet</div>'+
        '<div class="mp-battle-card mb-3" style="border-color:rgba(231,76,60,0.3)">'+
        '<p style="font-size:0.85rem;color:var(--text-primary);margin-bottom:8px">This will <strong style="color:#e74c3c">permanently delete</strong> '+escHtml(pet.name||'your pet')+'. All stats, inventory, and history will be lost.</p>'+
        '<p style="font-size:0.82rem;color:var(--text-secondary);margin:0">You will be able to adopt a new pet afterwards.</p>'+
        '</div>'+
        '<div class="mb-3">'+
        '<label class="form-label" style="font-size:0.82rem;color:var(--text-secondary)">Type <strong style="color:#e74c3c">'+escHtml(pet.name||'your pet')+'</strong> to confirm</label>'+
        '<input type="text" class="form-control mp-input" id="kill-confirm" placeholder="Type pet name to confirm">'+
        '</div>'+
        '<button class="mp-adopt-btn" style="background:linear-gradient(135deg,#c0392b,#e74c3c);color:#fff" onclick="window._mpKill()">💀 Release Pet</button>'+
        '<div id="kill-result" class="mt-3"></div>'+
        '</div>';

    return html;
}

function escHtml(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Safely encode a value for embedding inside an HTML onclick="..." attribute as a JS string argument.
// Uses JSON.stringify then escapes the surrounding double quotes so it sits inside a double-quoted attribute.
function escArg(v) {
    return JSON.stringify(String(v)).replace(/"/g, '&quot;');
}

// Map Discord emoji slugs → local PNG paths
var EMOJI_PATH_MAP = (function() {
    var eq  = '/static/Emojis/Pets/Equipment/';
    var dec = '/static/Emojis/Pets/Deco/';
    var pet = '/static/Emojis/Pets/';
    var map = {};

    // Equipment items — all files in Equipment/
    ['chest1','chest2','chest3','chest4',
     'Key1','Key2','Key3',
     'air_potion','att_potion','basic_potion','def_potion','dex_potion',
     'electric_potion','ene_potion','fighting_potion','fire_potion',
     'greater_health_potion','hap_potion','hap_potion','health_potion',
     'holy_potion','ice_potion','int_potion','lesser_health_potion',
     'lesser_xp_potion','luck_potion','magic_potion','mega_potion',
     'necro_potion','plant_potion','psychic_potion','rock_potion',
     's1_potion','s2_potion','s3_potion','water_potion','xp_potion',
     'AzureApex','Bliz','Bone','Bood','Brick','Dirt','Dodl','Drak','Dvod',
     'Dwep','Dwim','EmberCube','EmberHeart','EmeraldSoul','Fabric','Felr',
     'FluxDiamond','ForestEye','FrostShard','Fwit','GildedPrism','Glass',
     'Gold','Gufi','Itle','JadeSlab','Jle','Jlum','Krep','Laser','Leaf',
     'Leather','Lozd','MagmaDiamond','MintGaze','Mok','MoonQuartz','Nad',
     'Neri','OceanTear','Pir','Plat','PrismaticFlux','Qizi','Rowr','Sand',
     'Sili','SkySpire','Smart','Smuj','SolarCore','SolarSphere','Steel',
     'Stone','VoidSpark','Wirm','Wood','Yoa','ZephyrShard','Zhy','Zlik','Ztuk',
     'aviator','ballcap','beanie','bearskin','beret','boater','bowler',
     'capotain','cattleman','fedora','fez','fool','gat','keffiyeh','knights',
     'mitre','mortarboard','necromancer','nursing','paper','peaked','pith',
     'plutonium','rice','rock_1','rps','safety','santa','scissor','service',
     'sombrero','sorcerer','stovepipe','tank','toque','tricorne','turban','ushanka',
     'jet','ship'
    ].forEach(function(n){ map[n.toLowerCase()] = eq + n + '.png'; });

    // Deco / element / type
    ['Air','Basic','Electric','Fighting','Fire','Holy','Ice','Magic','Necro',
     'Plant','Psychic','Rock','Water','Flying','Land','Swimming',
     'ATT','DEF','INT','DEX','HAP','ENE',
     'camping','bonfire','beach','forest','hotairballoon','cruiseship',
     'mountain','gym','graveyard','festival','glacier','pyramids'
    ].forEach(function(n){ map[n.toLowerCase()] = dec + n + '.png'; });

    // Pet species
    ['Alligator','Ant','Anteater','Axolotl','Badger','Bat','Beaver','Bee',
     'Beetle','Bison','BlueTang','Camel','Cardinal','Cat','Centipede','Cheetah',
     'Chicken','Clownfish','Cow','Crab','Crow','Deer','Dog','Dolphin','Duck',
     'Eagle','Elephant','Emu','Firefly','Fox','Frog','Giraffe','Goat','Goose',
     'Gorilla','Grizzly','Hamster','Hedgehog','Hippo','Horse','Hummingbird',
     'Iguana','Jaguar','Jellyfish','Kangaroo','Kiwi','Koala','Ladybug','Lemur',
     'Leopard','Lion','Llama','Mantis','Monkey','Mouse','Octopus','Orangutan',
     'Orca','Ostrich','Otter','Owl','Panda','Parrot','Peacock','Pelican',
     'Penguin','Pig','Pigeon','Platypus','PolarBear','Pufferfish','Rabbit',
     'Raccoon','Ram','Rat','RedPanda','Reindeer','Rhino','Salmon','Scorpion',
     'Seahorse','Seal','Shark','Sheep','Shrimp','Skunk','Sloth','Snail',
     'Snake','Spider','Squirrel','Starfish','Stingray','SugarGlider','Tiger',
     'Toucan','Turkey','Turtle','Walrus','Whale','Wolf','Yak','Zebra'
    ].forEach(function(n){ map[n.toLowerCase()] = pet + n + '.png'; });

    return map;
}());

/**
 * Convert a Discord API response string into safe HTML:
 * - <:slug:id> and <a:slug:id> → <img> using local PNGs
 * - **text** → <strong>text</strong>
 * - Plain text is HTML-escaped
 */
function cleanDiscordText(raw) {
    if (!raw) return '';
    // Split on Discord emoji mentions
    var parts = String(raw).split(/(<a?:[^:>]+:\d+>)/g);
    var out = '';
    parts.forEach(function(part) {
        var m = part.match(/^<a?:([^:>]+):\d+>$/);
        if (m) {
            var slug = m[1].toLowerCase();
            var src  = EMOJI_PATH_MAP[slug] || null;
            if (src) {
                out += '<img src="'+src+'" style="width:18px;height:18px;object-fit:contain;vertical-align:middle;margin:0 1px" onerror="this.style.display=\'none\'">';
            }
            // If no mapping found, just drop the Discord mention (don't show raw ID)
        } else {
            // Escape HTML, then convert **bold**
            var safe = part
                .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
                .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
            out += safe;
        }
    });
    return out;
}

// Inject equipment item images into a cleaned message string.
// Replaces known item names (Keys, etc.) with an inline img + name.
function injectItemImages(text) {
    if (!text) return text;
    // Match item names that have a known Equipment image — word boundary aware
    return text.replace(/\b(Key[123]|Key 1|Key 2|Key 3)\b/g, function(match) {
        var file = match.replace(/ /g, '') + '.png'; // "Key 1" → "Key1.png"
        return '<img src="/static/Emojis/Pets/Equipment/'+file+'" '+
            'style="width:14px;height:14px;object-fit:contain;vertical-align:middle;margin:0 2px" '+
            'onerror="this.style.display=\'none\'"> '+match;
    });
}


window._mpTab = function(tab) {
    ['breakdown','abilities','inventory','reforge','market','train','mission','play','quest','rename','kill'].forEach(function(t) {
        var btn = el('tab-'+t), panel = el('panel-'+t);
        if (btn)   btn.classList.toggle('active', t===tab);
        if (panel) panel.style.display = t===tab ? '' : 'none';
    });
    // Load ability tree inline when switching to the abilities tab
    if (tab === 'abilities' && window.AbilityTree) {
        // Ensure the mount div is visible before rendering
        var mount = el('at-inline-mount');
        if (mount) mount.style.display = 'block';
        window.AbilityTree.openInline('at-inline-mount');
    }
};

// ── selection state ───────────────────────────────────────────────────────────
var _trainDiff   = 'Easy';
var _missionDiff = 'Easy';
var _playLoc     = '';

window._mpSelectTrain = function(d) {
    _trainDiff = d;
    ['Easy','Average','Hard'].forEach(function(x) {
        var el2 = el('train-opt-'+x);
        if (el2) el2.style.borderColor = x===d ? 'var(--gold-primary)' : 'rgba(255,215,0,0.15)';
        if (el2) el2.style.boxShadow   = x===d ? '0 0 8px var(--gold-glow)' : '';
    });
};

window._mpSelectMission = function(d) {
    _missionDiff = d;
    ['Easy','Average','Hard'].forEach(function(x) {
        var el2 = el('mission-opt-'+x);
        if (el2) el2.style.borderColor = x===d ? 'var(--gold-primary)' : 'rgba(255,215,0,0.15)';
        if (el2) el2.style.boxShadow   = x===d ? '0 0 8px var(--gold-glow)' : '';
    });
};

window._mpSelectPlay = function(loc) {
    _playLoc = loc;
    document.querySelectorAll('[id^="play-opt-"]').forEach(function(el2) {
        el2.style.borderColor = '';
        el2.style.boxShadow   = '';
    });
    var key = 'play-opt-'+loc.replace(/ /g,'-');
    var sel = el(key);
    if (sel) { sel.style.borderColor = 'var(--gold-primary)'; sel.style.boxShadow = '0 0 8px var(--gold-glow)'; }
};

function showResult(id, success, text) {
    var r = el(id);
    if (!r) return;
    var color = success ? 'rgba(39,174,96,0.4)' : 'rgba(231,76,60,0.4)';
    var textColor = success ? '#2ecc71' : '#e74c3c';
    r.innerHTML = '<div class="mp-battle-card" style="border-color:'+color+';color:'+textColor+';font-size:0.82rem;white-space:pre-line">'+cleanDiscordText(text)+'</div>';
}

function showLevelChangePopup(data, isDown) {
    var existing = document.getElementById('mp-level-popup');
    if (existing) existing.remove();

    var isLevelDown = isDown || (data.new_level < data.old_level);
    var emoji = isLevelDown ? '📉' : '🎉';
    var title = isLevelDown ? 'Level Down!' : 'Level Up!';
    var color = isLevelDown ? '#e74c3c' : 'var(--gold-primary)';
    var glow  = isLevelDown ? 'rgba(231,76,60,0.4)' : 'var(--gold-glow)';
    var bg    = isLevelDown ? 'rgba(231,76,60,0.15)' : 'rgba(255,215,0,0.1)';

    var gainsHtml = '';
    if (!isLevelDown && data.gains && Object.keys(data.gains).length) {
        gainsHtml = '<div style="margin-top:8px;font-size:0.75rem;color:var(--text-secondary)">';
        Object.entries(data.gains).forEach(function(kv) {
            if (kv[1] && kv[1] !== 0) gainsHtml += '<span style="margin-right:8px">+'+kv[1]+' '+kv[0]+'</span>';
        });
        gainsHtml += '</div>';
    }

    var popup = document.createElement('div');
    popup.id = 'mp-level-popup';
    popup.style.cssText = [
        'position:fixed','top:50%','left:50%',
        'transform:translate(-50%,-50%) scale(0.8)',
        'z-index:9999','text-align:center','padding:28px 36px',
        'border-radius:16px','border:2px solid '+color,
        'background:'+bg,'backdrop-filter:blur(12px)',
        'box-shadow:0 0 40px '+glow,
        'transition:transform 0.25s ease,opacity 0.25s ease',
        'opacity:0','pointer-events:none'
    ].join(';');

    popup.innerHTML = (
        '<div style="font-size:2.8rem;line-height:1">'+emoji+'</div>'+
        '<div style="font-size:1.4rem;font-weight:700;color:'+color+';margin-top:6px">'+title+'</div>'+
        '<div style="font-size:1rem;color:var(--text-primary);margin-top:4px">'+
            'Level <span style="color:var(--text-secondary)">'+data.old_level+'</span>'+
            ' → <span style="color:'+color+';font-weight:700">'+data.new_level+'</span>'+
        '</div>'+
        gainsHtml
    );

    document.body.appendChild(popup);

    // Animate in
    requestAnimationFrame(function() {
        popup.style.opacity = '1';
        popup.style.transform = 'translate(-50%,-50%) scale(1)';
        popup.style.pointerEvents = 'auto';
    });

    // Dismiss on click or after 4s
    function dismiss() {
        popup.style.opacity = '0';
        popup.style.transform = 'translate(-50%,-50%) scale(0.8)';
        setTimeout(function() { if (popup.parentNode) popup.remove(); }, 300);
    }
    popup.addEventListener('click', dismiss);
    setTimeout(dismiss, 4000);
}

// ── Cooldown timer helper ─────────────────────────────────────────────────────
// Maps: button ID → { interval, end }
var _cdTimers = {};

// Map action name → {btnId, resultId}
var _CD_TARGETS = {
    'train':   { btn:'train-btn',       result:'train-result'      },
    'mission': { btn:'mission-btn',     result:'mission-result'    },
    'play':    { btn:'play-btn',        result:'play-result'       },
    'quest':   { btn:'quest-start-btn', result:'quest-start-result'},
};

/**
 * Start (or restore) a cooldown timer for a button.
 *
 * @param {string} btnId       - ID of the button to disable
 * @param {string} resultId    - ID of the result container
 * @param {string|null} errorMsg - Error text from server (parses remaining time from it)
 * @param {number} [secsOverride] - Use this many seconds instead of parsing
 */
function _startCooldownTimer(btnId, resultId, errorMsg, secsOverride) {
    var secs = secsOverride || 0;
    if (!secs && errorMsg) {
        var m = errorMsg.match(/(\d+)m\s*(\d+)s/);
        if (m) secs = parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
        else { var s2 = errorMsg.match(/(\d+)s/); if (s2) secs = parseInt(s2[1], 10); }
    }
    if (!secs || secs <= 0) return;

    var btn = el(btnId);
    if (btn) {
        btn._cdOrigLabel = btn._cdOrigLabel || btn.textContent;
        btn.disabled = true;
    }

    // Cancel any existing timer for this button
    if (_cdTimers[btnId]) { clearInterval(_cdTimers[btnId].iv); }

    var end = Date.now() + secs * 1000;
    _cdTimers[btnId] = { iv: null, end: end };

    function tick() {
        var left = Math.max(0, Math.ceil((end - Date.now()) / 1000));
        var mins = Math.floor(left / 60), ss = left % 60;
        var timeStr = (mins > 0 ? mins + 'm ' : '') + ss + 's';

        if (btn) btn.textContent = left > 0 ? ('⏳ ' + timeStr) : (btn._cdOrigLabel || 'Go');

        // Update the cooldown pill inside the result area WITHOUT wiping reward content
        var r = el(resultId);
        if (r) {
            var pill = r.querySelector('.mp-cd-pill');
            if (left > 0) {
                if (!pill) {
                    pill = document.createElement('div');
                    pill.className = 'mp-cd-pill';
                    pill.style.cssText = 'font-size:0.72rem;color:var(--text-secondary);margin-top:6px';
                    r.appendChild(pill);  // append below existing reward content
                }
                pill.textContent = '⏳ Next use in: ' + timeStr;
            } else {
                if (pill) pill.remove();
            }
        }

        if (left <= 0) {
            clearInterval(_cdTimers[btnId].iv);
            delete _cdTimers[btnId];
            if (btn) { btn.disabled = false; btn.textContent = btn._cdOrigLabel || 'Go'; }
        }
    }

    tick();
    _cdTimers[btnId].iv = setInterval(tick, 1000);
}

// ── Restore cooldowns from server on page load ────────────────────────────────
function _restoreCooldowns() {
    fetch('/api/pets/cooldowns', { credentials:'include' })
        .then(function(r){ return r.ok ? r.json() : null; })
        .then(function(d) {
            if (!d || !d.cooldowns) return;
            Object.keys(d.cooldowns).forEach(function(action) {
                var remaining = d.cooldowns[action];
                if (remaining <= 0) return;
                var t = _CD_TARGETS[action];
                if (!t) return;
                // Only start timer — don't touch the result area content (no previous reward to show)
                _startCooldownTimer(t.btn, t.result, null, remaining);
            });
        })
        .catch(function(){});
}


window._mpTrain = async function() {
    if (!_trainStat) { showResult('train-result', false, 'Please select a stat to train.'); return; }
    var r = el('train-result');
    if (r) r.innerHTML = '<div class="mp-battle-card" style="font-size:0.8rem;color:var(--text-secondary)">Training...</div>';
    if (window.PetGPP) PetGPP.StateMachine.transition('waiting_server');
    try {
        var res = await fetch('/api/pets/train', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({difficulty: _trainDiff, stat: _trainStat})
        });
        var d = await res.json();
        if (res.status === 429) {
            showResult('train-result', false, d.error || 'On cooldown.');
            _startCooldownTimer('train-btn', 'train-result', d.error);
            if (window.PetGPP) PetGPP.StateMachine.reset();
        } else if (res.ok) {
            showResult('train-result', d.success, d.outcome);
            var oldPet = _pet;
            if (d.pet) { _refreshPet(d.pet); }
            if (window.PetGPP) {
                if (d.animation) PetGPP.push(d.animation);
                if (oldPet && d.pet) PetGPP.pushXpBar(oldPet, d.pet);
                if (d.level_change) PetGPP.pushLevelChange(d.level_change);
            }
            _startCooldownTimer('train-btn', 'train-result', null, 5);
        } else {
            showResult('train-result', false, d.error || d.detail || 'Failed');
            if (window.PetGPP) PetGPP.StateMachine.reset();
        }
    } catch(e) { showResult('train-result', false, e.message); if (window.PetGPP) PetGPP.StateMachine.reset(); }
};

window._mpMission = async function() {
    var r = el('mission-result');
    if (r) r.innerHTML = '<div class="mp-battle-card" style="font-size:0.8rem;color:var(--text-secondary)">Launching mission...</div>';
    var gambleEl = el('mission-gamble');
    var gamble = gambleEl ? parseInt(gambleEl.value||'0',10)||0 : 0;
    if (window.PetGPP) PetGPP.StateMachine.transition('waiting_server');
    try {
        var res = await fetch('/api/pets/mission', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({difficulty: _missionDiff, gamble_xp: gamble})
        });
        var d = await res.json();
        if (res.status === 429) {
            showResult('mission-result', false, d.error || 'On cooldown.');
            _startCooldownTimer('mission-btn', 'mission-result', d.error);
            if (window.PetGPP) PetGPP.StateMachine.reset();
        } else if (res.ok) {
            showResult('mission-result', d.success, d.outcome);
            var oldPet = _pet;
            if (d.pet) { _refreshPet(d.pet); }
            if (window.PetGPP) {
                if (d.animation) PetGPP.push(d.animation);
                if (oldPet && d.pet) PetGPP.pushXpBar(oldPet, d.pet);
                if (d.level_up)   PetGPP.pushLevelChange(d.level_up);
                if (d.level_down) PetGPP.pushLevelChange(d.level_down);
            }
            if (d.level_up) showLevelChangePopup(d.level_up, false);
            else if (d.level_down) showLevelChangePopup(d.level_down, true);
            _startCooldownTimer('mission-btn', 'mission-result', null, 5);
        } else {
            showResult('mission-result', false, d.error || d.detail || 'Failed');
            if (window.PetGPP) PetGPP.StateMachine.reset();
        }
    } catch(e) { showResult('mission-result', false, e.message); if (window.PetGPP) PetGPP.StateMachine.reset(); }
};
window._mpPlay = async function() {
    if (!_playLoc) { showResult('play-result', false, 'Please select a location first.'); return; }
    var r = el('play-result');
    if (r) r.innerHTML = '<div class="mp-battle-card" style="font-size:0.8rem;color:var(--text-secondary)">Playing...</div>';
    var petSnapshot = _pet || {};
    if (window.PetGPP) PetGPP.StateMachine.transition('waiting_server');
    try {
        var res = await fetch('/api/pets/play', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({location: _playLoc})
        });
        var d = await res.json();
        if (res.status === 429) {
            showResult('play-result', false, d.error || 'On cooldown.');
            _startCooldownTimer('play-btn', 'play-result', d.error);
            if (window.PetGPP) PetGPP.StateMachine.reset();
        } else if (res.ok) {
            var resultEl = el('play-result');
            if (resultEl) resultEl.innerHTML = buildPlayResult(d, _playLoc, petSnapshot);
            var oldPet = _pet;
            if (d.pet) { _refreshPet(d.pet); }
            if (window.PetGPP) {
                if (d.animation) PetGPP.push(d.animation);
                if (oldPet && d.pet) PetGPP.pushXpBar(oldPet, d.pet);
                if (d.level_up) PetGPP.pushLevelChange(d.level_up);
            }
            if (d.level_up) showLevelChangePopup(d.level_up, false);
            _startCooldownTimer('play-btn', 'play-result', null, 5);
        } else {
            showResult('play-result', false, d.error || d.detail || 'Failed');
            if (window.PetGPP) PetGPP.StateMachine.reset();
        }
    } catch(e) { showResult('play-result', false, e.message); if (window.PetGPP) PetGPP.StateMachine.reset(); }
};

// ── Quest state & handlers ────────────────────────────────────────────────────
var _questLoc  = '';
var _questDiff = 'Apprentice';

// _buildBattleHpBar is still used by the quest battle integration below
function _buildBattleHpBar(cur, max, enemy) {
    var pct = max > 0 ? Math.max(0, Math.min(100, Math.round((cur/max)*100))) : 0;
    var color = pct > 50 ? '#2ecc71' : pct > 25 ? '#f39c12' : '#e74c3c';
    if (enemy) color = pct > 50 ? '#e74c3c' : pct > 25 ? '#f39c12' : '#95a5a6';
    return '<div class="mp-xp-bar-wrap" style="height:8px;border-radius:4px;background:rgba(255,255,255,0.08)">'+
        '<div style="height:100%;width:'+pct+'%;background:'+color+';border-radius:4px;transition:width 0.3s"></div>'+
        '</div>'+
        '<div style="font-size:0.65rem;color:var(--text-secondary);margin-top:1px">'+cur+' / '+max+' HP</div>';
}

// ── Quest state & handlers ────────────────────────────────────────────────────
var _questLoc  = '';
var _questDiff = 'Apprentice';

window._mpSelectQLoc = function(loc) {
    _questLoc = loc;
    document.querySelectorAll('[id^="qloc-"]').forEach(function(e2){e2.style.borderColor='';e2.style.boxShadow='';});
    var s = el('qloc-'+loc.replace(/ /g,'-'));
    if(s){s.style.borderColor='var(--gold-primary)';s.style.boxShadow='0 0 8px var(--gold-glow)';}
};

window._mpSelectQDiff = function(d) {
    _questDiff = d;
    ['Apprentice','Journeyman','Senior'].forEach(function(x){
        var e2=el('qdiff-'+x);
        if(e2){e2.style.borderColor=x===d?'var(--gold-primary)':'rgba(255,215,0,0.15)';e2.style.boxShadow=x===d?'0 0 8px var(--gold-glow)':'';}
    });
};

window._mpQuestStart = async function() {
    if (!_questLoc) { showResult('quest-start-result', false, 'Please select a location.'); return; }
    var sr = el('quest-start-result');
    if(sr) sr.innerHTML = '<div class="mp-battle-card" style="font-size:0.8rem;color:var(--text-secondary)">⏳ Generating quest with AI... this may take a moment.</div>';
    try {
        var res = await fetch('/api/pets/quest/start', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({location:_questLoc, difficulty:_questDiff})
        });
        var d = await res.json();
        if (res.status === 429) {
            showResult('quest-start-result', false, d.error || 'On cooldown.');
            _startCooldownTimer('quest-start-btn', 'quest-start-result', d.error);
            return;
        }
        if (!res.ok) { showResult('quest-start-result', false, d.error || d.detail || 'Failed to start quest'); return; }
        if(sr) sr.innerHTML='';
        el('quest-setup').style.display = 'none';
        el('quest-active').style.display = '';
        el('quest-result').style.display = 'none';
        _renderQuestStage(d);
    } catch(e) { showResult('quest-start-result', false, e.message); }
};

function _renderQuestStage(d) {
    var prog = el('quest-progress');
    var name = el('quest-stage-name');
    var evt  = el('quest-event');
    var cho  = el('quest-choices');
    var xpt  = el('quest-xp-track');
    if(prog) prog.textContent = 'Stage '+(d.stage_idx+1)+' of '+d.total_stages;
    if(name) name.textContent = d.stage_name;
    if(evt)  evt.textContent  = d.event;
    if(xpt && d.xp_so_far !== undefined) xpt.textContent = 'XP earned so far: '+d.xp_so_far;
    if(cho) {
        cho.innerHTML = '';
        var statMaps = [
            {stats: 'ATT + DEF', desc: 'Physical approach'},
            {stats: 'DEX + INT', desc: 'Skillful approach'}, 
            {stats: 'ENE + HAP', desc: 'Endurance approach'}
        ];
        Object.keys(d.choices).forEach(function(k) {
            var choiceNum = parseInt(k, 10);
            var statInfo = statMaps[choiceNum - 1] || {stats: 'Unknown', desc: 'Unknown'};
            
            var btn = document.createElement('button');
            btn.className = 'mp-adopt-btn';
            btn.style.cssText = 'font-size:0.8rem;padding:8px 14px;text-align:left;width:100%;position:relative';
            
            // Create choice content with stat indicators
            var choiceDiv = document.createElement('div');
            choiceDiv.innerHTML = 
                '<div style="display:flex;align-items:center;justify-content:space-between">'+
                    '<span><strong>'+k+'.</strong> '+d.choices[k]+'</span>'+
                    '<span style="font-size:0.7rem;color:var(--gold-secondary);background:rgba(255,215,0,0.1);padding:2px 6px;border-radius:10px;margin-left:8px">'+statInfo.stats+'</span>'+
                '</div>';
            
            btn.appendChild(choiceDiv);
            btn.onclick = function(){ window._mpQuestChoice(parseInt(k,10)); };
            cho.appendChild(btn);
        });
    }
    var out = el('quest-outcome');
    if(out && d.outcome_msg) {
        var ok = d.outcome_msg.indexOf('✅')!==-1 || d.outcome_msg.indexOf('📦')!==-1 || d.outcome_msg.indexOf('⚔️')!==-1;
        out.innerHTML = '<div class="mp-battle-card" style="border-color:'+(ok?'rgba(39,174,96,0.4)':'rgba(231,76,60,0.4)')+';color:'+(ok?'#2ecc71':'#e74c3c')+';font-size:0.8rem;margin-bottom:6px">'+cleanDiscordText(d.outcome_msg)+'</div>';
    } else if(out) { out.innerHTML=''; }
}

window._mpQuestChoice = async function(choice) {
    // Disable all choice buttons while waiting
    var cho = el('quest-choices');
    if(cho) cho.querySelectorAll('button').forEach(function(b){b.disabled=true;b.style.opacity='0.5';});
    try {
        var res = await fetch('/api/pets/quest/choice', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({choice: choice})
        });
        var d = await res.json();
        if (!res.ok) { showResult('quest-outcome', false, d.detail||'Error'); if(cho) cho.querySelectorAll('button').forEach(function(b){b.disabled=false;b.style.opacity='1';}); return; }

        if (d.done) {
            _renderQuestDone(d);
        } else if (d.battle_required) {
            _startQuestBattle(d);
        } else {
            _renderQuestStage(d);
        }
    } catch(e) {
        var out = el('quest-outcome');
        if(out) out.innerHTML='<div class="mp-battle-card" style="border-color:rgba(231,76,60,0.4);color:#e74c3c;font-size:0.8rem">❌ '+escHtml(e.message)+'</div>';
        if(cho) cho.querySelectorAll('button').forEach(function(b){b.disabled=false;b.style.opacity='1';});
    }
};

// ── Quest battle integration ──────────────────────────────────────────────────
// When a hostile pet encounter fails the skill check, we run a real turn-based
// battle using the same engine as the NPC Battle tab.

function _startQuestBattle(d) {
    var stageBox = el('quest-stage-box');
    var out      = el('quest-outcome');
    var cho      = el('quest-choices');
    var xpt      = el('quest-xp-track');

    // Show the failure message
    if(out) out.innerHTML = '<div class="mp-battle-card" style="border-color:rgba(231,76,60,0.4);color:#e74c3c;font-size:0.8rem;margin-bottom:6px">'+cleanDiscordText(d.outcome_msg)+'</div>';
    if(cho) cho.innerHTML = '';
    if(xpt) xpt.textContent = 'XP earned so far: '+(d.xp_so_far||0);

    // Build an inline battle arena inside the quest panel
    var bossName = d.boss_name || 'Wild Creature';
    var hp       = d.hostile_pet ? (d.hostile_pet.ENE || 50) : 50;

    if(stageBox) stageBox.innerHTML =
        '<div id="quest-progress" style="font-size:0.7rem;color:var(--text-secondary);margin-bottom:6px">⚔️ Battle!</div>'+
        '<div id="quest-stage-name" class="mp-section-title" style="margin-bottom:6px;color:#e74c3c">Fight: '+escHtml(bossName)+'</div>'+
        '<div id="quest-event" style="font-size:0.85rem;color:var(--text-primary);margin-bottom:12px">Defeat the enemy to continue your quest!</div>'+
        '<div id="quest-choices" class="d-flex flex-column gap-2"></div>';

    // Start the actual NPC battle using the existing battle engine
    // We pass the hostile_pet data so the server uses it as the enemy
    _questBattleState = null;
    _startQuestBattleFetch(d.hostile_pet);
}

var _questBattleState = null;

async function _startQuestBattleFetch(hostilePet) {
    var cho = el('quest-choices');
    if(cho) cho.innerHTML = '<div style="font-size:0.8rem;color:var(--text-secondary)">⏳ Starting battle...</div>';
    try {
        var res = await fetch('/api/pets/battle/npc/start', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({difficulty: 'quest', hostile_pet: hostilePet})
        });
        var d = await res.json();
        if(!res.ok) { _questBattleFallback(d.detail||'Battle failed'); return; }
        _questBattleState = d;
        _renderQuestBattleArena();
    } catch(e) { _questBattleFallback(e.message); }
}

function _questBattleFallback(msg) {
    // If battle can't start, treat as a win so quest can continue
    console.warn('Quest battle fallback:', msg);
    _resolveQuestBattle(true, 20);
}

function _renderQuestBattleArena() {
    var cho = el('quest-choices');
    if(!cho || !_questBattleState) return;
    var p = _questBattleState.player, e = _questBattleState.enemy;
    var labels = _questBattleState.action_labels || {};

    cho.innerHTML =
        '<div style="display:flex;gap:8px;margin-bottom:8px">'+
            '<div style="flex:1;font-size:0.75rem">'+
                '<div style="color:var(--gold-secondary);font-weight:700">'+escHtml(p.name||'You')+'</div>'+
                _buildBattleHpBar(p.cur_hp, p.max_hp, false)+
            '</div>'+
            '<div style="font-size:0.8rem;color:var(--text-secondary);align-self:center">VS</div>'+
            '<div style="flex:1;font-size:0.75rem;text-align:right">'+
                '<div style="color:#e74c3c;font-weight:700">'+escHtml(e.name||'Enemy')+'</div>'+
                _buildBattleHpBar(e.cur_hp, e.max_hp, true)+
            '</div>'+
        '</div>'+
        '<div id="quest-battle-log" style="font-size:0.72rem;color:var(--text-secondary);max-height:80px;overflow-y:auto;margin-bottom:8px"></div>'+
        '<div style="display:flex;gap:6px;flex-wrap:wrap">'+
            '<button class="mp-adopt-btn" style="font-size:0.75rem;padding:6px 10px" onclick="window._mpQuestBattleTurn(\'attack\')">⚔️ '+(labels.attack||'Attack')+'</button>'+
            '<button class="mp-adopt-btn" style="font-size:0.75rem;padding:6px 10px" onclick="window._mpQuestBattleTurn(\'defend\')">🛡️ '+(labels.defend||'Defend')+'</button>'+
            '<button class="mp-adopt-btn" style="font-size:0.75rem;padding:6px 10px" onclick="window._mpQuestBattleTurn(\'charge\')">⚡ '+(labels.charge||'Charge')+'</button>'+
        '</div>';
}

window._mpQuestBattleTurn = async function(action) {
    if(!_questBattleState || _questBattleState.over) return;
    // Disable buttons
    var cho = el('quest-choices');
    if(cho) cho.querySelectorAll('button').forEach(function(b){b.disabled=true;b.style.opacity='0.5';});
    try {
        var res = await fetch('/api/pets/battle/npc/turn', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({
                action: action,
                player: _questBattleState.player,
                enemy:  _questBattleState.enemy,
                turn:   _questBattleState.turn,
                difficulty: _questBattleState.difficulty,
                action_labels: _questBattleState.action_labels || {}
            })
        });
        var d = await res.json();
        if(!res.ok) { _questBattleFallback(d.detail||'Turn failed'); return; }

        _questBattleState.player = d.player;
        _questBattleState.enemy  = d.enemy;
        _questBattleState.turn   = d.turn;
        _questBattleState.over   = d.over;

        // ── GPP: push battle animation events ─────────────────────────────────
        if (window.PetGPP && d.animations) PetGPP.push(d.animations);

        // Update HP bars and log
        _renderQuestBattleArena();
        var log = el('quest-battle-log');
        if(log && d.combat) {
            var c = d.combat;
            var line = 'Turn '+d.turn+': ';
            if(c.p_action==='charge') line += 'You charge up!';
            else if(c.p_action==='defend') line += 'You defend.';
            else line += 'You deal '+(c.p_dmg||0)+' dmg.';
            if(c.e_action==='attack') line += ' Enemy deals '+(c.e_dmg||0)+' dmg.';
            log.innerHTML += '<div>'+escHtml(line)+'</div>';
            log.scrollTop = log.scrollHeight;
        }

        if(d.over) {
            var xpGained = d.xp_gained || 0;
            _resolveQuestBattle(d.won, xpGained);
        } else {
            // Re-enable buttons
            if(cho) cho.querySelectorAll('button').forEach(function(b){b.disabled=false;b.style.opacity='1';});
        }
    } catch(e) { _questBattleFallback(e.message); }
};

async function _resolveQuestBattle(won, xpGained) {
    _questBattleState = null;
    try {
        var res = await fetch('/api/pets/quest/battle_result', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({won: won, xp_gained: xpGained||0})
        });
        var d = await res.json();
        if(!res.ok) { showResult('quest-outcome', false, d.detail||'Error'); return; }
        if(d.done) {
            _renderQuestDone(d);
        } else {
            _renderQuestStage(d);
        }
    } catch(e) {
        showResult('quest-outcome', false, e.message);
    }
}

function _renderQuestDone(d) {
    el('quest-active').style.display = 'none';
    var r = el('quest-result');
    if(!r) return;
    r.style.display = '';
    var ok = d.success;
    var html = '<div class="mp-battle-card" style="border-color:'+(ok?'rgba(255,215,0,0.5)':'rgba(231,76,60,0.4)')+';margin-bottom:8px">'+
        '<div class="mp-section-title" style="color:'+(ok?'var(--gold-primary)':'#e74c3c')+'">'+(ok?'🏆 Quest Complete!':'💀 Quest Failed')+'</div>'+
        '<div style="font-size:0.82rem;margin-bottom:6px">'+
        '<span style="color:var(--gold-secondary)">XP Earned: '+d.xp+'</span>';
    if(d.loot && d.loot.length) html += ' &bull; <span style="color:#2ecc71">Loot: '+d.loot.join(', ')+'</span>';
    html += '</div>';
    if(d.event_log && d.event_log.length) {
        html += '<div style="font-size:0.75rem;color:var(--text-secondary)">';
        d.event_log.forEach(function(e,i){
            html += '<div style="margin-bottom:3px;padding:3px 0;border-bottom:1px solid rgba(255,215,0,0.1)">'+
                '<span style="color:var(--gold-secondary)">Stage '+(i+1)+' — '+escHtml(e.stage)+'</span><br>'+
                '<span>Choice: '+escHtml(e.choice)+'</span> &bull; '+
                '<span class="'+(e.success?'text-success':'text-danger')+'">'+(e.success?'✅ Success':'❌ Failed')+'</span>'+
                ' <span style="color:var(--text-secondary)">('+e.success_rate+'%)</span><br>'+
                '<span style="color:var(--text-primary)">'+cleanDiscordText(e.outcome)+'</span>'+
                '</div>';
        });
        html += '</div>';
    }
    html += '</div>';
    html += '<button class="mp-adopt-btn" onclick="window._mpQuestReset()" style="font-size:0.8rem">⚔️ New Quest</button>';
    r.innerHTML = html;
    var oldPet = _pet;
    if(d.pet){ _refreshPet(d.pet); }
    if (window.PetGPP) {
        if (oldPet && d.pet) PetGPP.pushXpBar(oldPet, d.pet);
        if (d.success) PetGPP.Particles.spawnAt('xp_burst',
            document.querySelector('#my-pet-header .mp-pet-img'), '#ffd700');
    }
}

window._mpQuestReset = function() {
    el('quest-setup').style.display = '';
    el('quest-active').style.display = 'none';
    el('quest-result').style.display = 'none';
    var out = el('quest-outcome'); if(out) out.innerHTML='';
    var xpt = el('quest-xp-track'); if(xpt) xpt.textContent='';
    _questBattleState = null;
};

window._mpQuestAbandon = async function() {
    try {
        await fetch('/api/pets/quest/abandon', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    } catch(e) { /* silent */ }
    window._mpQuestReset();
};

// ── Loot Market state & handlers ──────────────────────────────────────────────
var _lmChest = '';
var _lmType  = '';
var _lmAmt   = 1;

window._mpSelectLmChest = function(c) {
    _lmChest = c; _lmType = '';
    ['chest1','chest2','chest3','chest4'].forEach(function(x){
        var e2=el('lm-'+x);
        if(e2){e2.style.borderColor=x===c?'var(--gold-primary)':'rgba(255,215,0,0.15)';e2.style.boxShadow=x===c?'0 0 8px var(--gold-glow)':'';}
    });
    var t4 = el('lm-type-row');
    if(t4) t4.style.display = c==='chest4' ? '' : 'none';
    var amtRow = el('lm-amt-row');
    if(amtRow) amtRow.style.display = c==='chest4' ? 'none' : '';
    el('lm-result') && (el('lm-result').innerHTML='');
};

window._mpSelectLmType = function(t) {
    _lmType = t;
    ['Material','Gem','Monster','Potion','Hat'].forEach(function(x){
        var e2=el('lm-type-'+x);
        if(e2){e2.style.borderColor=x===t?'var(--gold-primary)':'rgba(255,215,0,0.15)';e2.style.boxShadow=x===t?'0 0 8px var(--gold-glow)':'';}
    });
};

window._mpOpenChest = async function() {
    if(!_lmChest){ showResult('lm-result',false,'Select a chest first.'); return; }
    if(_lmChest==='chest4' && !_lmType){ showResult('lm-result',false,'Select an item type for Chest 4.'); return; }
    var amtEl = el('lm-amount');
    _lmAmt = amtEl ? Math.max(1,parseInt(amtEl.value||'1',10)||1) : 1;
    var r = el('lm-result');
    if(r) r.innerHTML = '';

    var chestImgSrc = '/static/Emojis/Pets/Equipment/' + _lmChest + '.png';
    var chestColor = ({chest1:'#9e9e9e',chest2:'#4caf50',chest3:'#2196f3',chest4:'#ff9800'})[_lmChest] || '#ffd700';

    try {
        // Fetch first, then animate with the results
        var res = await fetch('/api/pets/loot/open', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({chest:_lmChest, amount:_lmAmt, selected_type:_lmType||null})
        });
        var d = await res.json();

        if(res.ok && d.success) {
            var items = d.items || [];
            _showChestAnimation(chestImgSrc, chestColor, items, function() {
                var html = '<div class="mp-battle-card" style="border-color:rgba(255,215,0,0.4)">';
                html += '<div class="mp-section-title" style="color:var(--gold-primary)">📦 Chest Opened!</div>';
                html += '<div class="d-flex flex-wrap gap-2 mt-2">';
                items.forEach(function(item){
                    var f = equipImgFile(item);
                    var rcClass = 'rc-'+(item.rarity||'Common').toLowerCase();
                    html += '<div class="mp-inv-item">'+
                        '<img src="/static/Emojis/Pets/Equipment/'+f+'" style="width:28px;height:28px" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">'+
                        '<div><div class="fw-bold '+rcClass+'" style="font-size:0.78rem">'+escHtml(item.name)+'</div>'+
                        '<div style="font-size:0.65rem;color:var(--text-secondary)">'+(item.rarity||'Common')+'</div></div></div>';
                });
                html += '</div>';
                if (d.messages && d.messages.length) {
                    html += '<div style="font-size:0.75rem;color:var(--text-secondary);margin-top:8px">';
                    d.messages.forEach(function(m){
                        var stripped = String(m).replace(/<img[^>]*>/gi, '').replace(/<[^>]+>/g, '').trim();
                        var clean = injectItemImages(cleanDiscordText(stripped).replace(/\*\*/g,'').trim());
                        if (clean) html += '<div>'+clean+'</div>';
                    });
                    html += '</div>';
                }
                html += '</div>';
                if(r) r.innerHTML = html;
                var oldPet = _pet;
                if(d.pet){ _refreshPet(d.pet); }
                if (window.PetGPP) {
                    if (d.animation) PetGPP.push(d.animation);
                    if (oldPet && d.pet) PetGPP.pushXpBar(oldPet, d.pet);
                }
            });
        } else {
            showResult('lm-result', false, d.detail||d.error||'Failed');
        }
    } catch(e){ showResult('lm-result',false,e.message); }
};

function _showChestAnimation(chestSrc, chestColor, items, callback) {
    // Inject keyframes once
    if (!document.getElementById('chest-anim-style')) {
        var s = document.createElement('style');
        s.id = 'chest-anim-style';
        s.textContent =
            '@keyframes chestZoomIn{0%{transform:scale(0.6);opacity:0}40%{transform:scale(1.12);opacity:1}70%{transform:scale(0.97)}100%{transform:scale(1);opacity:1}}'+
            '@keyframes chestFadeOut{0%{transform:scale(1);opacity:1}100%{transform:scale(1.3);opacity:0}}'+
            '@keyframes itemsReveal{0%{opacity:0;transform:scale(0.5) translateY(20px)}60%{transform:scale(1.08) translateY(-4px)}100%{opacity:1;transform:scale(1) translateY(0)}}'+
            '@keyframes shimmer{0%,100%{box-shadow:0 0 20px rgba(255,215,0,0.3)}50%{box-shadow:0 0 50px rgba(255,215,0,0.9),0 0 80px rgba(255,215,0,0.4)}}';
        document.head.appendChild(s);
    }

    var overlay = document.createElement('div');
    overlay.id = 'chest-anim-overlay';
    overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:10500;'+
        'display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.82);backdrop-filter:blur(6px)';

    // Build item icons HTML
    var itemIconsHtml = items.map(function(item, idx) {
        var f = equipImgFile(item);
        var rc = ({Common:'#9e9e9e',Uncommon:'#4caf50',Rare:'#2196f3',Epic:'#9c27b0',Mythic:'#ff9800'})[item.rarity||'Common'] || '#9e9e9e';
        return '<div style="text-align:center;animation:itemsReveal 0.5s ease forwards;animation-delay:'+(idx*0.12)+'s;opacity:0">'+
            '<img src="/static/Emojis/Pets/Equipment/'+f+'" style="width:56px;height:56px;object-fit:contain;filter:drop-shadow(0 0 10px '+rc+')" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">'+
            '<div style="font-size:0.65rem;color:'+rc+';margin-top:4px;max-width:64px;word-break:break-word;font-weight:600">'+escHtml(item.name)+'</div>'+
            '<div style="font-size:0.58rem;color:rgba(255,255,255,0.45);margin-top:1px">'+(item.rarity||'Common')+'</div>'+
            '</div>';
    }).join('');

    overlay.innerHTML =
        '<div style="text-align:center;max-width:420px;padding:24px">'+
        // Phase 1: chest
        '<div id="chest-phase1">'+
        '<img id="chest-anim-img" src="'+chestSrc+'" style="width:96px;height:96px;object-fit:contain;animation:chestZoomIn 0.6s ease forwards;filter:drop-shadow(0 0 24px '+chestColor+')" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">'+
        '<div style="font-size:0.9rem;color:'+chestColor+';font-family:Orbitron,sans-serif;margin-top:10px;animation:shimmer 1s ease infinite">Opening...</div>'+
        '</div>'+
        // Phase 2: items (hidden initially)
        '<div id="chest-phase2" style="display:none">'+
        '<div style="font-size:1rem;color:var(--gold-primary);font-family:Orbitron,sans-serif;margin-bottom:14px">✨ You got!</div>'+
        '<div style="display:flex;flex-wrap:wrap;gap:12px;justify-content:center">'+itemIconsHtml+'</div>'+
        '<div style="font-size:0.75rem;color:var(--text-secondary);margin-top:14px">Click anywhere to continue</div>'+
        '</div>'+
        '</div>';

    document.body.appendChild(overlay);

    // After zoom-in pause, fade chest out then show items
    setTimeout(function() {
        var chestImg = document.getElementById('chest-anim-img');
        var phase1 = document.getElementById('chest-phase1');
        var phase2 = document.getElementById('chest-phase2');
        if (chestImg) chestImg.style.animation = 'chestFadeOut 0.4s ease forwards';
        setTimeout(function() {
            if (phase1) phase1.style.display = 'none';
            if (phase2) phase2.style.display = '';
        }, 380);
    }, 1200);

    // Click anywhere to dismiss
    overlay.addEventListener('click', function() {
        overlay.remove();
        callback();
    });

    // Auto-dismiss after 4s
    setTimeout(function() {
        if (document.getElementById('chest-anim-overlay')) {
            overlay.remove();
            callback();
        }
    }, 4000);
}

window._mpRename = async function() {
    var nameEl = el('rename-name');
    var nameErr = el('rename-name-err');
    var name = (nameEl ? nameEl.value : '').trim();
    var result = el('rename-result');

    nameEl && nameEl.classList.remove('is-invalid');
    if (!name) {
        nameErr && (nameErr.textContent = 'Name is required.');
        nameEl && nameEl.classList.add('is-invalid');
        return;
    }
    if (name.length > 32 || !/^[a-zA-Z0-9 \-_.,!?']+$/.test(name)) {
        nameErr && (nameErr.textContent = 'Invalid name (max 32 chars, basic punctuation only).');
        nameEl && nameEl.classList.add('is-invalid');
        return;
    }

    var atkEl = el('rename-atk'), defEl = el('rename-def'), chgEl = el('rename-chg');

    try {
        var r = await fetch('/api/pets/rename', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({
                name: name,
                actions: {
                    Attack:  atkEl ? atkEl.value.trim() : '',
                    Defense: defEl ? defEl.value.trim() : '',
                    Charge:  chgEl ? chgEl.value.trim() : ''
                }
            })
        });
        var d = await r.json();
        if (r.ok && d.success) {
            if (result) result.innerHTML = '<div class="mp-battle-card" style="border-color:rgba(39,174,96,0.4);color:#2ecc71;font-size:0.82rem">✅ Saved! Refreshing...</div>';
            // ── GPP: flash confirmation ───────────────────────────────────────
            if (window.PetGPP) PetGPP.Flash.flash('rgba(39,174,96,0.12)', 20);
            setTimeout(function(){ init(); }, 1200);
        } else {
            if (result) result.innerHTML = '<div class="mp-battle-card" style="border-color:rgba(231,76,60,0.4);color:#e74c3c;font-size:0.82rem">❌ '+(d.detail||d.error||'Failed')+'</div>';
        }
    } catch(e) {
        if (result) result.innerHTML = '<div class="mp-battle-card" style="border-color:rgba(231,76,60,0.4);color:#e74c3c;font-size:0.82rem">❌ '+e.message+'</div>';
    }
};

window._mpGift = async function() {
    var recipientEl = el('gift-recipient-id');
    var itemEl      = el('gift-item-name');
    var resultEl    = el('gift-result');
    var recipientId = (recipientEl ? recipientEl.value : '').trim();
    var itemName    = (itemEl ? itemEl.value : '').trim();

    if (!recipientId) { if (resultEl) resultEl.innerHTML = '<div class="alert alert-warning">Enter a recipient Discord User ID.</div>'; return; }
    if (!itemName)    { if (resultEl) resultEl.innerHTML = '<div class="alert alert-warning">Enter an item name.</div>'; return; }

    if (resultEl) resultEl.innerHTML = '<div style="font-size:0.82rem;color:var(--text-secondary)">Sending gift…</div>';

    try {
        var r = await fetch('/api/pets/gift', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ item_name: itemName, recipient_user_id: recipientId })
        });
        var d = await r.json();
        if (r.ok && d.success) {
            if (resultEl) resultEl.innerHTML = '<div class="alert alert-success">🎁 Gifted <strong>' + escHtml(d.gifted) + '</strong> to <strong>' + escHtml(d.to) + '</strong>!</div>';
            if (itemEl) itemEl.value = '';
            // ── GPP: particle burst on gift ───────────────────────────────────
            if (window.PetGPP) {
                var petImg = document.querySelector('#my-pet-header .mp-pet-img');
                PetGPP.Particles.spawnAt('float_up', petImg, '#ffd700');
            }
            if (_pet) { _refreshPet(_pet); } else { init(); }
        } else {
            if (resultEl) resultEl.innerHTML = '<div class="alert alert-danger">' + escHtml(d.error || 'Gift failed.') + '</div>';
        }
    } catch(e) {
        if (resultEl) resultEl.innerHTML = '<div class="alert alert-danger">Error: ' + escHtml(e.message) + '</div>';
    }
};

window._mpKill = async function() {
    var confirmEl = el('kill-confirm');
    var result = el('kill-result');
    var typed = (confirmEl ? confirmEl.value : '').trim();

    if (!_pet || typed.toLowerCase() !== (_pet.name||'').toLowerCase()) {
        if (result) result.innerHTML = '<div class="mp-battle-card" style="border-color:rgba(231,76,60,0.4);color:#e74c3c;font-size:0.82rem">❌ Name does not match. Type the exact pet name to confirm.</div>';
        return;
    }

    try {
        var r = await fetch('/api/pets/kill', { method: 'DELETE' });
        var d = await r.json();
        if (r.ok && d.success) {
            if (result) result.innerHTML = '<div class="mp-battle-card" style="border-color:rgba(39,174,96,0.4);color:#2ecc71;font-size:0.82rem">✅ Pet released. Redirecting...</div>';
            // ── GPP: stop loop, clear queue on kill ───────────────────────────
            if (window.PetGPP) { PetGPP.EventQueue.clear(); PetGPP.StateMachine.reset(); }
            setTimeout(function(){ init(); }, 1200);
        } else {
            if (result) result.innerHTML = '<div class="mp-battle-card" style="border-color:rgba(231,76,60,0.4);color:#e74c3c;font-size:0.82rem">❌ '+(d.detail||d.error||'Failed')+'</div>';
        }
    } catch(e) {
        if (result) result.innerHTML = '<div class="mp-battle-card" style="border-color:rgba(231,76,60,0.4);color:#e74c3c;font-size:0.82rem">❌ '+e.message+'</div>';
    }
};

// Returns the new-slot-system equipment state.
// MIRRORS pet_brain.py StatsCalculator._calculate_equipment_bonuses + get_equipment_xp_multiplier.
//   Main slots:     Helmet, Armor, Boots, Ring, Shield, Weapon  (1 each)
//   Ring sub-slots: Material (1), Monsters (2), Gems (2)
//   Set match:      Helmet+Armor+Boots+Shield+Weapon all share `set` tag (Ring excluded)
//   ringSubBonus:   +1 matching monsters, +1 matching gems, +1 material equipped
//   baseMult:       mainFilled + (set ? 3 : 0) + ringSubBonus + levelBonus  (min 1)
//   fullSet:        matchingSet AND ring AND material AND matchingMonsters AND matchingGems
//   finalMult:      baseMult * 2 if fullSet else baseMult
function getEquipSetState(pet) {
    var eq    = pet.equipment || {};
    var level = parseInt(pet.level || 1, 10);
    var levelBonus = Math.floor(level / 50);

    function getSingle(key) {
        var v = eq[key];
        if (Array.isArray(v)) v = v[0] || null;
        return (v && v.name) ? v : null;
    }
    function getList(key) {
        var v = eq[key] || [];
        if (!Array.isArray(v)) v = (v && v.name) ? [v] : [];
        return v.filter(function(i){ return i && i.name; });
    }

    // ── Main slots ────────────────────────────────────────────────────────────
    var helmet = getSingle('Helmet');
    var armor  = getSingle('Armor');
    var boots  = getSingle('Boots');
    var ring   = getSingle('Ring');
    var shield = getSingle('Shield');
    var weapon = getSingle('Weapon');
    var mainSlots  = [helmet, armor, boots, ring, shield, weapon];
    var mainFilled = mainSlots.filter(function(s){ return s !== null; });

    // ── Ring sub-slots ────────────────────────────────────────────────────────
    var material = getSingle('Material');
    var monsters = getList('Monsters');
    var gems     = getList('Gems');

    // ── Set matching (Helmet+Armor+Boots+Shield+Weapon; Ring excluded) ───────
    var setSlots = [helmet, armor, boots, shield, weapon];
    var setSlotsFilled = setSlots.filter(function(s){ return s !== null; });
    var setTags = setSlotsFilled.map(function(s){ return s.set || null; }).filter(function(t){ return t; });
    var matchingSet = (setSlotsFilled.length === 5 && setTags.length === 5 &&
                       (new Set(setTags)).size === 1);

    // ── Ring sub-slot matching ────────────────────────────────────────────────
    var monNames = monsters.map(function(m){ return (m.name || '').toLowerCase(); });
    var gemNames = gems.map(function(g){ return (g.name || '').toLowerCase(); });
    var matchingMonsters = (monNames.length === 2 && monNames[0] === monNames[1]);
    var matchingGems     = (gemNames.length === 2 && gemNames[0] === gemNames[1]);
    var hasMaterial      = material !== null;
    var ringSubBonus = (matchingMonsters ? 1 : 0) + (matchingGems ? 1 : 0) + (hasMaterial ? 1 : 0);

    // ── Full set ──────────────────────────────────────────────────────────────
    var fullSet = (matchingSet && ring !== null &&
                   hasMaterial && matchingMonsters && matchingGems);

    // ── Multiplier ────────────────────────────────────────────────────────────
    var slotsFilledBonus = mainFilled.length;
    var setBonus = matchingSet ? 3 : 0;
    var baseMult = slotsFilledBonus + setBonus + ringSubBonus + levelBonus;
    if (baseMult < 1) baseMult = 1;
    var finalMult = fullSet ? baseMult * 2 : baseMult;

    return {
        // raw slot items
        helmet: helmet, armor: armor, boots: boots, ring: ring,
        shield: shield, weapon: weapon,
        material: material, monsters: monsters, gems: gems,
        // counts/flags
        mainFilled: mainFilled.length,
        matchingSet: matchingSet, setTag: matchingSet ? setTags[0] : null,
        matchingMonsters: matchingMonsters, matchingGems: matchingGems,
        hasMaterial: hasMaterial, ringSubBonus: ringSubBonus,
        fullSet: fullSet,
        levelBonus: levelBonus,
        slotsFilledBonus: slotsFilledBonus, setBonus: setBonus,
        baseMult: baseMult, finalMult: finalMult
    };
}

function buildEquipped(pet) {
    var eq = pet.equipment || {};
    var state = getEquipSetState(pet);

    // ── Row 1: main gear slots ────────────────────────────────────────────────
    var row1 = [
        {key:'Helmet', label:'Helmet'},
        {key:'Armor',  label:'Armor'},
        {key:'Boots',  label:'Boots'},
        {key:'Ring',   label:'Ring'},
        {key:'Shield', label:'Shield'},
        {key:'Weapon', label:'Weapon'}
    ];
    // ── Row 2: ring sub-slots ─────────────────────────────────────────────────
    var row2 = [
        {key:'Monsters', idx:0, label:'Monster 1'},
        {key:'Gems',     idx:0, label:'Gem 1'},
        {key:'Material', idx:-1, label:'Material'},
        {key:'Gems',     idx:1, label:'Gem 2'},
        {key:'Monsters', idx:1, label:'Monster 2'}
    ];

    function getItem(sl) {
        if (sl.idx === undefined || sl.idx === -1) {
            var v = eq[sl.key];
            if (Array.isArray(v)) v = v[0] || null;
            return (v && v.name) ? v : null;
        }
        var arr = eq[sl.key] || [];
        if (!Array.isArray(arr)) arr = (arr && arr.name) ? [arr] : [];
        return (arr[sl.idx] && arr[sl.idx].name) ? arr[sl.idx] : null;
    }

    function glowClass(sl, item) {
        if (!item) return '';
        if (state.fullSet) return ' equip-fullset';
        // Row 1 main slots
        if (sl.idx === undefined || sl.idx === -1) {
            if (sl.key !== 'Ring' && state.matchingSet &&
                ['Helmet','Armor','Boots','Shield','Weapon'].indexOf(sl.key) !== -1) return ' equip-pair';
            if (sl.key === 'Ring' && state.ringSubBonus > 0) return ' equip-pair';
        }
        // Row 2 ring sub-slots
        if (sl.key === 'Monsters' && state.matchingMonsters) return ' equip-pair';
        if (sl.key === 'Gems'     && state.matchingGems)     return ' equip-pair';
        if (sl.key === 'Material' && state.hasMaterial)      return ' equip-pair';
        return '';
    }

    function renderSlot(sl, isRingSub) {
        var item    = getItem(sl);
        var isEmpty = !item;
        var f       = isEmpty ? 'Basic.png' : equipImgFile(item);
        var src     = isEmpty ? '/static/Emojis/Pets/Deco/Basic.png' : '/static/Emojis/Pets/Equipment/' + f;
        var ringRequired = isRingSub;
        var ringMissing  = ringRequired && !state.ring;
        var subCls = isRingSub ? ' equip-ring-sub' : '';

        if (isEmpty) {
            var emptyLabel = ringMissing ? sl.label + ' (need Ring)' : sl.label + ' (empty)';
            return '<div class="mp-equip-slot empty' + subCls + '" title="' + escHtml(emptyLabel) + '">' +
                '<img src="' + src + '">' +
                '</div>';
        }

        var data        = getEquipItem(item.name);
        var tip         = item.name + ' — ' + bonusTooltip(data || item) + ' (click to unequip)';
        var gc          = glowClass(sl, item);
        var unequipSlot = sl.key;  // server accepts Helmet/Armor/Boots/Ring/Shield/Weapon/Material/Gems/Monsters/Hat

        return '<div class="mp-equip-slot mp-equip-filled' + gc + subCls + '" title="' + escHtml(tip) + '" ' +
            'onclick="window._mpUnequipSlot(' + escArg(unequipSlot) + ')" style="cursor:pointer"' +
            ' data-hover-item="' + escHtml(item.name) + '">' +
            '<img src="' + src + '" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">' +
            '</div>';
    }

    // ── Render ────────────────────────────────────────────────────────────────
    var html = '<div class="mp-section-title">Equipped</div>';

    // Row 1 — main gear
    html += '<div class="d-flex flex-wrap gap-1 mb-1">';
    row1.forEach(function(sl){ html += renderSlot(sl, false); });
    html += '</div>';

    // Row 2 — ring sub-slots (always shown so user can see what they're missing)
    var ringLabel = state.ring
        ? '<span style="font-size:0.58rem;color:var(--gold-secondary);opacity:0.75">💍 Ring sub-slots</span>'
        : '<span style="font-size:0.58rem;color:var(--text-secondary);opacity:0.55">💍 Ring sub-slots (equip a Ring first)</span>';
    html += '<div style="margin-top:2px">' + ringLabel +
        '<div class="d-flex flex-wrap gap-1 mt-1">';
    row2.forEach(function(sl){ html += renderSlot(sl, true); });
    html += '</div></div>';

    return html;
}

function buildInventoryCollapsible(pet) {
    var inv = pet.inventory||[];
    var eq  = pet.equipment||{};

    // ── Build a set of equipped item names for glow + label ───────────────────
    // Covers both the new slot system and legacy slots.
    var equippedNames = {};
    function _mark(name) {
        if (!name) return;
        var k = name.toLowerCase();
        equippedNames[k] = (equippedNames[k]||0) + 1;
    }
    // New main slots (single-item each)
    ['Helmet','Armor','Boots','Ring','Shield','Weapon'].forEach(function(k){
        var v = eq[k];
        if (Array.isArray(v)) v = v[0] || null;
        if (v && v.name) _mark(v.name);
    });
    // Ring sub-slots + legacy
    var mat = eq.Material;
    if (mat && !Array.isArray(mat) && mat.name) _mark(mat.name);
    (Array.isArray(eq.Material) ? eq.Material : []).forEach(function(m){ if(m&&m.name) _mark(m.name); });
    if (eq.Hat && eq.Hat.name) _mark(eq.Hat.name);
    (eq.Gems||[]).forEach(function(g){ if(g&&g.name) _mark(g.name); });
    (eq.Monsters||[]).forEach(function(m){ if(m&&m.name) _mark(m.name); });

    // Item types that can be equipped via /api/pets/equip
    var EQUIPPABLE_TYPES = ['Hat','Material','Gem','Monster',
                            'Helmet','Armor','Boots','Ring','Shield',
                            'Dagger','Katana','Sword','Axe','Hammer','Bow'];

    // Count how many of each equippable item the user has in inventory
    var invCounts = {};
    inv.forEach(function(item){
        if (EQUIPPABLE_TYPES.indexOf(item.type||'') !== -1) {
            var k = item.name.toLowerCase();
            invCounts[k] = (invCounts[k]||0) + (item.count||1);
        }
    });

    var uid    = 'inv-collapse-body';
    var chevId = 'inv-collapse-chev';
    var isOpen = (function() {
        var existing = document.getElementById(uid);
        return existing ? existing.style.display !== 'none' : false;
    })();
    var header =
        '<hr class="mp-divider my-2">' +
        '<div class="mp-collapse-header" onclick="mpToggleCollapse(\'' + uid + '\',\'' + chevId + '\')">' +
            '<span class="mp-section-title" style="margin:0">🎒 Inventory <span style="font-size:0.65rem;color:var(--text-secondary)">(' + inv.length + ' items)</span></span>' +
            '<span id="' + chevId + '" class="mp-chev ' + (isOpen ? 'mp-chev-open' : 'mp-chev-collapsed') + '">▼</span>' +
        '</div>';
    if (!inv.length) return header + '<div id="' + uid + '" class="mp-collapse-body" style="display:' + (isOpen ? '' : 'none') + '"><div class="mp-empty-state" style="padding:8px">Inventory is empty.</div></div>';

    var grouped = {};
    inv.forEach(function(item){ var t=item.type||'Other'; if(!grouped[t])grouped[t]=[]; grouped[t].push(item); });

    var content = '<div id="' + uid + '" class="mp-collapse-body" style="display:' + (isOpen ? '' : 'none') + '">';
    // Display order: main gear first, then ring sub-slots, then consumables/loot
    var CATEGORY_ORDER = ['Helmet','Armor','Boots','Ring','Shield',
                          'Dagger','Katana','Sword','Axe','Hammer','Bow',
                          'Hat','Material','Gem','Monster',
                          'Potion','Key','Chest','Other'];
    // Types that are stored in single-slot equipment slots (Material is single in new system,
    // Hat is single, but Gem/Monster allow up to 2 on the ring)
    var SINGLE_SLOT = ['Hat','Helmet','Armor','Boots','Ring','Shield',
                       'Dagger','Katana','Sword','Axe','Hammer','Bow','Material'];

    CATEGORY_ORDER.forEach(function(t) {
        if (!grouped[t]) return;
        content += '<div style="font-size:0.68rem;color:var(--gold-secondary);font-weight:700;margin:5px 0 3px">'+t+'s</div>';
        content += '<div class="d-flex flex-wrap gap-1 mb-1">';
        grouped[t].forEach(function(item) {
            var f = equipImgFile(item);
            var rcClass = 'rc-'+(item.rarity||'Common').toLowerCase();
            var isEquippable = EQUIPPABLE_TYPES.indexOf(t) !== -1;
            var isPotion     = t === 'Potion';
            var isChest      = t === 'Chest';
            var clickable    = isEquippable || isPotion || isChest;

            var eqCount  = equippedNames[item.name.toLowerCase()]||0;
            var invCount = item.count||1;
            var isEquipped = eqCount > 0;

            // Determine action label and equip count to send
            var action = isPotion ? 'Use' : (isChest ? 'Open' : (isEquipped ? 'Equipped' : 'Equip'));
            // Multi-slot types (Gems/Monsters): if 0 equipped and ≥2 in inventory, equip both
            var equipCount = 1;
            if (!isPotion && isEquippable && SINGLE_SLOT.indexOf(t) === -1 &&
                invCount >= 2 && eqCount === 0) {
                equipCount = 2;
                action = 'Equip Both';
            }

            // Bonus tooltip from equipment data
            var data = getEquipItem(item.name);
            var tip = item.name;
            if (data && data.bonuses) {
                var bParts = Object.keys(data.bonuses).map(function(k){ return k+': +'+data.bonuses[k]; });
                if (bParts.length) tip += ' | '+bParts.join(' | ');
            }
            if (isEquipped) tip += ' · Currently Equipped ('+eqCount+'x)';
            else if (clickable) tip += ' · Click to '+action.toLowerCase();

            var onclick = clickable ? ' onclick="window._mpInvClick('+escArg(item.name)+','+escArg(t)+','+escArg(action)+','+equipCount+','+escArg(item.rarity||'Common')+','+invCount+')"' : '';

            var glowStyle = isEquipped ? 'box-shadow:0 0 5px rgba(255,215,0,0.3);border-color:rgba(255,215,0,0.6);' : '';
            content += '<div class="mp-inv-item'+(clickable?' mp-inv-clickable':'')+'" '+
                'style="padding:4px 6px;'+glowStyle+'" title="'+escHtml(tip)+'"'+onclick+
                ' data-hover-item="'+escHtml(item.name)+'">'+
                '<img src="/static/Emojis/Pets/Equipment/'+f+'" style="width:22px;height:22px" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">'+
                '<div>'+
                '<div class="fw-bold '+rcClass+'" style="font-size:0.72rem">'+item.name+'</div>'+
                '<div style="font-size:0.62rem;color:'+(isEquipped?'var(--gold-secondary)':'var(--text-secondary)')+'">'+
                'x'+invCount+(clickable?' · '+action:'')+
                '</div></div></div>';
        });
        content += '</div>';
    });
    return header + content + '</div>';
}

function buildInventoryPanel(pet) {
    var inv = pet.inventory||[];
    var eq  = pet.equipment||{};

    // ── Build a set of equipped item names for glow + label ───────────────────
    var equippedNames = {};
    function _mark(name) {
        if (!name) return;
        var k = name.toLowerCase();
        equippedNames[k] = (equippedNames[k]||0) + 1;
    }
    ['Helmet','Armor','Boots','Ring','Shield','Weapon'].forEach(function(k){
        var v = eq[k];
        if (Array.isArray(v)) v = v[0] || null;
        if (v && v.name) _mark(v.name);
    });
    var mat = eq.Material;
    if (mat && !Array.isArray(mat) && mat.name) _mark(mat.name);
    (Array.isArray(eq.Material) ? eq.Material : []).forEach(function(m){ if(m&&m.name) _mark(m.name); });
    if (eq.Hat && eq.Hat.name) _mark(eq.Hat.name);
    (eq.Gems||[]).forEach(function(g){ if(g&&g.name) _mark(g.name); });
    (eq.Monsters||[]).forEach(function(m){ if(m&&m.name) _mark(m.name); });

    var EQUIPPABLE_TYPES = ['Hat','Material','Gem','Monster',
                            'Helmet','Armor','Boots','Ring','Shield',
                            'Dagger','Katana','Sword','Axe','Hammer','Bow'];
    var SINGLE_SLOT = ['Hat','Helmet','Armor','Boots','Ring','Shield',
                       'Dagger','Katana','Sword','Axe','Hammer','Bow','Material'];

    var CATEGORY_ORDER = ['Helmet','Armor','Boots','Ring','Shield',
                          'Dagger','Katana','Sword','Axe','Hammer','Bow',
                          'Hat','Material','Gem','Monster',
                          'Potion','Key','Chest','Other'];

    var CATEGORY_LABELS = {
        Helmet:'Helmets', Armor:'Armor', Boots:'Boots', Ring:'Rings', Shield:'Shields',
        Dagger:'Daggers', Katana:'Katanas', Sword:'Swords', Axe:'Axes', Hammer:'Hammers', Bow:'Bows',
        Hat:'Hats', Material:'Materials', Gem:'Gems', Monster:'Monsters',
        Potion:'Potions', Key:'Keys', Chest:'Chests', Other:'Other'
    };

    var html = '<div class="mp-section-title">🎒 Inventory <span style="font-size:0.65rem;color:var(--text-secondary)">(' + inv.length + ' items)</span></div>';
    if (!inv.length) return html + '<div class="mp-empty-state" style="padding:8px">Inventory is empty.</div>';

    // Group items by type
    var grouped = {};
    inv.forEach(function(item){
        var t = item.type||'Other';
        if (!grouped[t]) grouped[t] = [];
        grouped[t].push(item);
    });

    // ── Loot bar — Keys + Chests always visible at top, no collapse ──────────
    var keyItems   = grouped['Key']   || [];
    var chestItems = grouped['Chest'] || [];
    if (keyItems.length || chestItems.length) {
        var totalLoot = keyItems.reduce(function(s,i){ return s+(i.count||1); }, 0) +
                        chestItems.reduce(function(s,i){ return s+(i.count||1); }, 0);
        html += '<div class="mp-inv-keys-bar mb-2">';
        html += '<div style="font-size:0.65rem;color:var(--text-secondary);font-weight:600;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px">🗝️ Loot <span style="color:rgba(255,215,0,0.4);font-weight:400">' + totalLoot + ' items</span></div>';
        html += '<div class="d-flex flex-wrap gap-2">';

        // Keys first
        keyItems.forEach(function(item) {
            var f     = equipImgFile(item);
            var count = item.count || 1;
            html += '<div class="mp-key-badge" title="' + escHtml(item.name) + ' ×' + count + '">' +
                '<img src="/static/Emojis/Pets/Equipment/' + f + '" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">' +
                '<span class="mp-key-badge-count">×' + count + '</span>' +
                '<span class="mp-key-badge-name">' + escHtml(item.name) + '</span>' +
                '</div>';
        });

        // Chests — clickable to open
        var CHEST_COLORS = { chest1:'#9e9e9e', chest2:'#4caf50', chest3:'#2196f3', chest4:'#ff9800' };
        chestItems.forEach(function(item) {
            var f     = equipImgFile(item);
            var count = item.count || 1;
            var chestKey = item.name.toLowerCase().replace(/\s/g,'');
            var chestColor = CHEST_COLORS[chestKey] || '#ffd700';
            html += '<div class="mp-key-badge mp-inv-clickable" ' +
                'style="border-color:' + chestColor + '40;cursor:pointer" ' +
                'title="' + escHtml(item.name) + ' ×' + count + ' — Click to open" ' +
                'onclick="window._mpInvClick(' + escArg(item.name) + ',\'Chest\',\'Open\',1,' + escArg(item.rarity||'Common') + ',' + count + ')">' +
                '<img src="/static/Emojis/Pets/Equipment/' + f + '" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">' +
                '<span class="mp-key-badge-count" style="color:' + chestColor + '">×' + count + '</span>' +
                '<span class="mp-key-badge-name">' + escHtml(item.name) + '</span>' +
                '</div>';
        });

        html += '</div></div>';
    }

    CATEGORY_ORDER.forEach(function(t) {
        if (!grouped[t]) return;
        // Keys and Chests are shown in the Loot bar above — skip them here
        if (t === 'Key' || t === 'Chest') return;
        var items = grouped[t];
        var bodyId = 'inv-body-' + t.toLowerCase();
        var chevId = 'inv-chev-' + t.toLowerCase();
        var label  = CATEGORY_LABELS[t] || (t + 's');
        var count  = items.reduce(function(s, i){ return s + (i.count||1); }, 0);

        // ALL sections start collapsed
        var startOpen = false;

        html += '<div class="mp-inv-section">';
        html += '<div class="mp-inv-section-header" onclick="mpToggleCollapse(\''+bodyId+'\',\''+chevId+'\')">' +
            '<span style="font-size:0.72rem;color:var(--gold-secondary);font-weight:700">'+label+'</span>' +
            '<div style="display:flex;align-items:center;gap:6px">' +
            '<span class="mp-inv-count-badge">'+count+'</span>' +
            '<span class="mp-chev '+(startOpen?'mp-chev-open':'mp-chev-collapsed')+'" id="'+chevId+'">▼</span>' +
            '</div></div>';

        html += '<div id="'+bodyId+'" class="mp-inv-grid" style="'+(startOpen?'':'display:none')+'">';

        items.forEach(function(item) {
            var f = equipImgFile(item);
            var rcClass = 'rc-'+(item.rarity||'Common').toLowerCase();
            var isEquippable = EQUIPPABLE_TYPES.indexOf(t) !== -1;
            var isPotion     = t === 'Potion';
            var isChest      = t === 'Chest';
            var clickable    = isEquippable || isPotion || isChest;

            var eqCount  = equippedNames[item.name.toLowerCase()]||0;
            var invCount = item.count||1;
            var isEquipped = eqCount > 0;

            // Reforge info
            var isReforged   = !!(item.reforged);
            var reforgeLevel = isReforged ? (parseInt(item.reforge_level||0,10)) : 0;

            var action = isPotion ? 'Use' : (isChest ? 'Open' : (isEquipped ? 'Equipped' : 'Equip'));
            var equipCount = 1;
            if (!isPotion && isEquippable && SINGLE_SLOT.indexOf(t) === -1 &&
                invCount >= 2 && eqCount === 0) {
                equipCount = 2;
                action = 'Equip Both';
            }

            // Resolve bonuses — reforged items carry their own bonuses; plain items use catalog
            var bonuses = {};
            if (isReforged && item.bonuses && Object.keys(item.bonuses).length) {
                bonuses = item.bonuses;
            } else {
                var catalogData = getEquipItem(item.name);
                if (catalogData && catalogData.bonuses) bonuses = catalogData.bonuses;
            }

            var onclick = clickable ? ' onclick="window._mpInvClick('+escArg(item.name)+','+escArg(t)+','+escArg(action)+','+equipCount+','+escArg(item.rarity||'Common')+','+invCount+')"' : '';
            var glowStyle = isEquipped ? 'border-color:rgba(255,215,0,0.6);box-shadow:0 0 8px rgba(255,215,0,0.25);' : '';
            var reforgeGlow = isReforged ? 'border-color:rgba(168,85,247,0.5);box-shadow:0 0 8px rgba(168,85,247,0.2);' : '';

            html += '<div class="mp-inv-panel-item'+(clickable?' mp-inv-clickable':'')+'" style="'+glowStyle+reforgeGlow+'"'+onclick+
                ' data-hover-item="'+escHtml(item.name)+'">';

            // Image + equipped badge
            html += '<div class="mp-inv-panel-img-wrap">';
            html += '<img class="mp-inv-panel-img" src="/static/Emojis/Pets/Equipment/'+f+'" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">';
            if (isEquipped) {
                html += '<div class="mp-inv-equipped-badge" title="Equipped">E</div>';
            }
            if (isReforged) {
                html += '<div style="position:absolute;bottom:-4px;left:-4px;background:rgba(168,85,247,0.9);color:#fff;font-size:0.5rem;font-weight:900;border-radius:4px;padding:1px 4px;white-space:nowrap">Lv.'+reforgeLevel+'</div>';
            }
            html += '</div>';

            // Name + rarity
            html += '<div class="mp-inv-panel-info">';
            html += '<div class="mp-inv-panel-name '+rcClass+'" title="'+escHtml(item.name)+'">'+escHtml(item.name)+'</div>';

            // Reforge badge
            if (isReforged) {
                html += '<div style="font-size:0.6rem;color:#a855f7;font-weight:700;margin-top:1px">⚗️ Reforged Lv.'+reforgeLevel+'</div>';
            }

            // Rarity dot + label
            html += '<div class="mp-inv-panel-meta">';
            html += '<div class="mp-inv-rarity-dot" style="background:'+rc(item.rarity||'Common')+'"></div>';
            html += '<span style="font-size:0.62rem;color:var(--text-secondary)">'+(item.rarity||'Common')+'</span>';
            html += '</div>';

            // Bonus chips
            if (Object.keys(bonuses).length) {
                html += '<div class="mp-inv-panel-bonuses">';
                Object.keys(bonuses).forEach(function(stat) {
                    var val = bonuses[stat];
                    if (!val) return;
                    var col = BONUS_COLORS[stat] || '#4caf50';
                    html += '<span class="mp-inv-bonus-chip" style="color:'+col+';background:'+col+'1a;border-color:'+col+'40">'+stat+': +'+val+'</span>';
                });
                html += '</div>';
            }
            html += '</div>';

            // Qty + action row
            html += '<div class="mp-inv-panel-right">';
            html += '<span class="mp-inv-qty">×'+invCount+'</span>';
            if (clickable) {
                var actionColor = isEquipped ? 'var(--gold-secondary)' : (isPotion ? '#ce93d8' : (isChest ? '#ff9800' : '#4caf50'));
                html += '<span class="mp-inv-action" style="color:'+actionColor+'">'+action+'</span>';
            }
            html += '</div>';

            html += '</div>'; // mp-inv-panel-item
        });

        html += '</div>'; // mp-inv-grid
        html += '</div>'; // mp-inv-section
    });

    return html;
}

// ── Reforge Panel ─────────────────────────────────────────────────────────────
// State for the reforge UI
var _rfCandidates   = null;  // { reforge_candidates, sacrifice_candidates }
var _rfItem         = null;  // selected item to reforge
var _rfSacrifices   = [];    // up to 3 selected sacrifice items
var _rfStats        = [];    // up to 6 selected stats

function buildReforgePanel(pet) {
    return '<div class="mp-section-title">⚗️ Reforge</div>' +
        '<div class="mp-battle-card mb-3" style="font-size:0.82rem;color:var(--text-secondary)">' +
        'Combine 5 copies of an item to create a more powerful reforged version. ' +
        'Choose 3 sacrifice items and up to 6 stats to boost. ' +
        '<span style="color:var(--gold-secondary)">Reforged items have 5× the original stat points distributed across your chosen stats.</span>' +
        '</div>' +
        '<button class="mp-adopt-btn" style="font-size:0.78rem;padding:6px 16px;margin-bottom:12px" onclick="window._mpLoadReforge()">🔄 Load Reforge Candidates</button>' +
        '<div id="reforge-candidates" style="display:none">' +
            '<div class="mp-breakdown-sub" style="margin-bottom:6px">Step 1 — Select item to reforge (need ≥5 copies)</div>' +
            '<div id="rf-item-list" class="d-flex flex-wrap gap-2 mb-3"></div>' +
            '<div class="mp-breakdown-sub" style="margin-bottom:6px">Step 2 — Select 3 sacrifice items</div>' +
            '<div id="rf-sac-list" class="d-flex flex-wrap gap-2 mb-3"></div>' +
            '<div class="mp-breakdown-sub" style="margin-bottom:6px">Step 3 — Select stats to boost (1–6)</div>' +
            '<div class="d-flex gap-2 flex-wrap mb-3" id="rf-stat-list">' +
            ['ATT','DEF','DEX','INT','HAP','ENE'].map(function(s) {
                return '<div class="mp-mini-stat-card" style="cursor:pointer;min-width:52px;transition:all 0.2s" id="rf-stat-'+s+'" onclick="window._mpRfToggleStat(\''+s+'\')">' +
                    '<img src="/static/Emojis/Pets/Deco/'+s+'.png" style="width:20px;height:20px;object-fit:contain;margin-bottom:2px" onerror="this.style.display=\'none\'">' +
                    '<div class="mp-mini-label">'+s+'</div>' +
                    '</div>';
            }).join('') +
            '</div>' +
            '<div id="rf-preview" class="mb-3" style="display:none">' +
                '<div class="mp-breakdown-sub">Preview</div>' +
                '<div id="rf-preview-body" class="mp-battle-card" style="font-size:0.82rem"></div>' +
            '</div>' +
            '<button class="mp-adopt-btn" id="rf-submit-btn" onclick="window._mpDoReforge()" style="display:none">⚗️ Reforge Item</button>' +
        '</div>' +
        '<div id="reforge-result" class="mt-3"></div>';
}

window._mpLoadReforge = function() {
    var r = el('reforge-result');
    if (r) r.innerHTML = '<div class="mp-battle-card" style="font-size:0.8rem;color:var(--text-secondary)">Loading candidates...</div>';
    fetch('/api/pets/forge/eligible-items', { credentials:'include' })
        .then(function(res){ return res.json(); })
        .then(function(d) {
            if (d.error) { if (r) r.innerHTML = '<div class="mp-battle-card" style="color:#e74c3c;font-size:0.82rem">'+escHtml(d.error)+'</div>'; return; }
            _rfCandidates = d;
            _rfItem = null; _rfSacrifices = []; _rfStats = [];
            if (r) r.innerHTML = '';
            _renderRfCandidates();
            var panel = el('reforge-candidates');
            if (panel) panel.style.display = '';
        })
        .catch(function(e){ if (r) r.innerHTML = '<div class="mp-battle-card" style="color:#e74c3c;font-size:0.82rem">'+escHtml(e.message)+'</div>'; });
};

function _renderRfCandidates() {
    if (!_rfCandidates) return;
    var itemList = el('rf-item-list');
    var sacList  = el('rf-sac-list');
    if (!itemList || !sacList) return;

    // Reforge candidates
    itemList.innerHTML = '';
    (_rfCandidates.reforge_candidates||[]).forEach(function(item) {
        var isReforged   = !!(item.reforged);
        var reforgeLevel = isReforged ? (parseInt(item.reforge_level||0,10)) : 0;
        var isSelected   = _rfItem && _rfItem.name === item.name && _rfItem.reforge_level === reforgeLevel && !!_rfItem.reforged === isReforged;
        var f = equipImgFile(item);
        var bonuses = (isReforged && item.bonuses) ? item.bonuses : ((getEquipItem(item.name)||{}).bonuses||{});
        var bonusParts = Object.keys(bonuses).map(function(k){ return k+':+'+bonuses[k]; }).join(' ');
        var totalPts = Object.values(bonuses).reduce(function(s,v){ return s+parseInt(v||0,10); }, 0);

        var div = document.createElement('div');
        div.className = 'mp-inv-panel-item' + (isSelected ? '' : ' mp-inv-clickable');
        div.style.cssText = 'min-width:130px;max-width:160px;cursor:pointer;' +
            (isSelected ? 'border-color:var(--gold-primary);box-shadow:0 0 10px var(--gold-glow);' :
             isReforged ? 'border-color:rgba(168,85,247,0.4);' : '');
        div.innerHTML =
            '<div class="mp-inv-panel-img-wrap">' +
            '<img class="mp-inv-panel-img" src="/static/Emojis/Pets/Equipment/'+f+'" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">' +
            (isReforged ? '<div style="position:absolute;bottom:-4px;left:-4px;background:rgba(168,85,247,0.9);color:#fff;font-size:0.5rem;font-weight:900;border-radius:4px;padding:1px 4px">Lv.'+reforgeLevel+'</div>' : '') +
            '</div>' +
            '<div class="mp-inv-panel-info">' +
            '<div class="mp-inv-panel-name rc-'+(item.rarity||'Common').toLowerCase()+'" style="font-size:0.72rem">'+escHtml(item.name)+'</div>' +
            (isReforged ? '<div style="font-size:0.58rem;color:#a855f7;font-weight:700">⚗️ Reforged Lv.'+reforgeLevel+'</div>' : '') +
            (bonusParts ? '<div style="font-size:0.6rem;color:var(--text-secondary);margin-top:2px">'+escHtml(bonusParts)+'</div>' : '') +
            '<div style="font-size:0.6rem;color:var(--gold-secondary);margin-top:1px">'+totalPts+' pts → '+(totalPts*5)+' pts</div>' +
            '</div>' +
            '<div class="mp-inv-panel-right">' +
            '<span class="mp-inv-qty">×'+(item.count||1)+'</span>' +
            '<span class="mp-inv-action" style="color:'+(isSelected?'var(--gold-primary)':'#4caf50')+'">'+(isSelected?'✓ Selected':'Select')+'</span>' +
            '</div>';
        div.addEventListener('click', function() {
            _rfItem = item;
            _rfItem.reforge_level = reforgeLevel;
            _renderRfCandidates();
            _updateRfPreview();
        });
        itemList.appendChild(div);
    });
    if (!(_rfCandidates.reforge_candidates||[]).length) {
        itemList.innerHTML = '<div style="font-size:0.78rem;color:var(--text-secondary)">No items with ≥5 copies available.</div>';
    }

    // Sacrifice candidates
    sacList.innerHTML = '';
    (_rfCandidates.sacrifice_candidates||[]).forEach(function(item) {
        var isSelected = _rfSacrifices.some(function(s){ return s.name === item.name && !!s.reforged === !!item.reforged && (s.reforge_level||0) === (item.reforge_level||0); });
        var isReforged = !!(item.reforged);
        var reforgeLevel = isReforged ? (parseInt(item.reforge_level||0,10)) : 0;
        var f = equipImgFile(item);

        var div = document.createElement('div');
        div.className = 'mp-inv-panel-item mp-inv-clickable';
        div.style.cssText = 'min-width:110px;max-width:140px;cursor:pointer;' +
            (isSelected ? 'border-color:rgba(231,76,60,0.6);box-shadow:0 0 8px rgba(231,76,60,0.2);' :
             isReforged ? 'border-color:rgba(168,85,247,0.3);' : '');
        div.innerHTML =
            '<div class="mp-inv-panel-img-wrap">' +
            '<img class="mp-inv-panel-img" style="width:36px;height:36px" src="/static/Emojis/Pets/Equipment/'+f+'" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">' +
            (isReforged ? '<div style="position:absolute;bottom:-4px;left:-4px;background:rgba(168,85,247,0.9);color:#fff;font-size:0.5rem;font-weight:900;border-radius:4px;padding:1px 4px">Lv.'+reforgeLevel+'</div>' : '') +
            '</div>' +
            '<div class="mp-inv-panel-info">' +
            '<div class="mp-inv-panel-name rc-'+(item.rarity||'Common').toLowerCase()+'" style="font-size:0.68rem">'+escHtml(item.name)+'</div>' +
            (isReforged ? '<div style="font-size:0.55rem;color:#a855f7">⚗️ Lv.'+reforgeLevel+'</div>' : '') +
            '</div>' +
            '<div class="mp-inv-panel-right">' +
            '<span class="mp-inv-qty" style="font-size:0.68rem">×'+(item.count||1)+'</span>' +
            '<span class="mp-inv-action" style="color:'+(isSelected?'#e74c3c':'var(--text-secondary)')+'">'+(isSelected?'✗ Remove':'+ Add')+'</span>' +
            '</div>';
        div.addEventListener('click', function() {
            var idx = _rfSacrifices.findIndex(function(s){ return s.name === item.name && !!s.reforged === !!item.reforged && (s.reforge_level||0) === (item.reforge_level||0); });
            if (idx !== -1) {
                _rfSacrifices.splice(idx, 1);
            } else if (_rfSacrifices.length < 3) {
                _rfSacrifices.push(item);
            } else {
                _showToast('❌ Max 3 sacrifice items', false);
                return;
            }
            _renderRfCandidates();
            _updateRfPreview();
        });
        sacList.appendChild(div);
    });
    if (!(_rfCandidates.sacrifice_candidates||[]).length) {
        sacList.innerHTML = '<div style="font-size:0.78rem;color:var(--text-secondary)">No sacrifice items available.</div>';
    }

    // Stat buttons
    ['ATT','DEF','DEX','INT','HAP','ENE'].forEach(function(s) {
        var btn = el('rf-stat-'+s);
        if (!btn) return;
        var sel = _rfStats.indexOf(s) !== -1;
        btn.style.borderColor = sel ? 'var(--gold-primary)' : 'rgba(255,215,0,0.15)';
        btn.style.boxShadow   = sel ? '0 0 8px var(--gold-glow)' : '';
        btn.style.background  = sel ? 'rgba(255,215,0,0.12)' : '';
    });
}

window._mpRfToggleStat = function(stat) {
    var idx = _rfStats.indexOf(stat);
    if (idx !== -1) {
        _rfStats.splice(idx, 1);
    } else if (_rfStats.length < 6) {
        _rfStats.push(stat);
    }
    _renderRfCandidates();
    _updateRfPreview();
};

function _updateRfPreview() {
    var previewDiv = el('rf-preview');
    var previewBody = el('rf-preview-body');
    var submitBtn = el('rf-submit-btn');
    if (!previewDiv || !previewBody) return;

    var ready = _rfItem && _rfSacrifices.length === 3 && _rfStats.length >= 1;
    if (!ready) {
        previewDiv.style.display = 'none';
        if (submitBtn) submitBtn.style.display = 'none';
        return;
    }

    // Calculate preview
    var isReforged = !!_rfItem.reforged;
    var reforgeLevel = isReforged ? (parseInt(_rfItem.reforge_level||0,10)) : 0;
    var bonuses = (isReforged && _rfItem.bonuses) ? _rfItem.bonuses : ((getEquipItem(_rfItem.name)||{}).bonuses||{});
    var totalPts = Object.values(bonuses).reduce(function(s,v){ return s+parseInt(v||0,10); }, 0);
    var newTotal = totalPts * 5;
    var perStat  = Math.floor(newTotal / _rfStats.length);
    var remainder = newTotal % _rfStats.length;

    var newBonuses = {};
    _rfStats.forEach(function(s, i) { newBonuses[s] = perStat + (i === 0 ? remainder : 0); });

    var newLevel = reforgeLevel + 1;
    var html = '<div style="font-size:0.78rem;color:var(--text-primary);margin-bottom:6px">' +
        '<strong style="color:var(--gold-secondary)">'+escHtml(_rfItem.name)+'</strong>' +
        (isReforged ? ' Lv.'+reforgeLevel : ' (plain)') + ' → ' +
        '<strong style="color:#a855f7">⚗️ Reforged Lv.'+newLevel+'</strong>' +
        '</div>' +
        '<div style="font-size:0.72rem;color:var(--text-secondary);margin-bottom:4px">'+totalPts+' pts × 5 = '+newTotal+' pts across '+_rfStats.length+' stat'+ (_rfStats.length>1?'s':'')+'</div>' +
        '<div class="d-flex flex-wrap gap-2 mb-2">';
    Object.keys(newBonuses).forEach(function(s) {
        var col = BONUS_COLORS[s] || '#4caf50';
        html += '<span class="mp-inv-bonus-chip" style="color:'+col+';background:'+col+'1a;border-color:'+col+'40;font-size:0.72rem">'+s+': +'+newBonuses[s]+'</span>';
    });
    html += '</div>';
    html += '<div style="font-size:0.7rem;color:var(--text-secondary)">Consumes: 5× '+escHtml(_rfItem.name)+
        (isReforged?' Lv.'+reforgeLevel:'')+' + '+
        _rfSacrifices.map(function(s){ return escHtml(s.name)+(s.reforged?' Lv.'+(s.reforge_level||0):''); }).join(', ')+'</div>';

    previewBody.innerHTML = html;
    previewDiv.style.display = '';
    if (submitBtn) submitBtn.style.display = '';
}

window._mpDoReforge = async function() {
    if (!_rfItem || _rfSacrifices.length !== 3 || _rfStats.length < 1) {
        showResult('reforge-result', false, 'Please complete all steps first.');
        return;
    }
    var r = el('reforge-result');
    if (r) r.innerHTML = '<div class="mp-battle-card" style="font-size:0.8rem;color:var(--text-secondary)">Reforging...</div>';
    var btn = el('rf-submit-btn');
    if (btn) btn.disabled = true;

    try {
        var res = await fetch('/api/pets/reforge', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            credentials: 'include',
            body: JSON.stringify({
                reforge_item: {
                    name:          _rfItem.name,
                    type:          _rfItem.type,
                    reforged:      !!_rfItem.reforged,
                    reforge_level: parseInt(_rfItem.reforge_level||0,10)
                },
                sacrifice_items: _rfSacrifices.map(function(s){ return {name:s.name, type:s.type, reforged:!!s.reforged, reforge_level:parseInt(s.reforge_level||0,10)}; }),
                target_stats: _rfStats
            })
        });
        var d = await res.json();
        if (res.ok && d.success) {
            var bonusParts = Object.keys(d.new_bonuses||{}).map(function(s){ return s+': +'+d.new_bonuses[s]; }).join(', ');
            var msg = '⚗️ Reforge successful! ' + escHtml(_rfItem.name) + ' → Lv.' + d.reforge_level +
                (bonusParts ? ' (' + bonusParts + ')' : '');
            showResult('reforge-result', true, msg);
            if (d.pet) { _refreshPet(d.pet); }
            if (window.PetGPP) {
                if (d.animation) PetGPP.push(d.animation);
                var petImg = document.querySelector('#my-pet-header .mp-pet-img');
                PetGPP.Particles.spawnAt('chest_open', petImg, '#a855f7');
                PetGPP.Flash.flash('rgba(168,85,247,0.2)', 25);
            }
            // Reset and reload candidates
            _rfItem = null; _rfSacrifices = []; _rfStats = [];
            var panel = el('reforge-candidates');
            if (panel) panel.style.display = 'none';
        } else {
            showResult('reforge-result', false, d.error || d.detail || 'Reforge failed.');
        }
    } catch(e) {
        showResult('reforge-result', false, e.message);
    } finally {
        if (btn) btn.disabled = false;
    }
};

function fmtXp(n) {
    var abs = Math.abs(n);
    var sign = n < 0 ? '-' : '+';
    if (abs >= 1e12) return sign + (abs / 1e12).toFixed(abs % 1e12 === 0 ? 0 : 1).replace(/\.0$/, '') + 't';
    if (abs >= 1e9)  return sign + (abs / 1e9 ).toFixed(abs % 1e9  === 0 ? 0 : 1).replace(/\.0$/, '') + 'b';
    if (abs >= 1e6)  return sign + (abs / 1e6 ).toFixed(abs % 1e6  === 0 ? 0 : 1).replace(/\.0$/, '') + 'm';
    if (abs >= 1000) return sign + (abs / 1000).toFixed(abs % 1000 === 0 ? 0 : 1).replace(/\.0$/, '') + 'k';
    return (n >= 0 ? '+' : '') + n;
}

function buildEquipBonus(pet) {
    var state = getEquipSetState(pet);
    // Hide if literally nothing is equipped
    if (state.mainFilled === 0 && !state.hasMaterial &&
        state.monsters.length === 0 && state.gems.length === 0) return '';

    var multColor = state.fullSet ? '#f59e0b'
                  : state.matchingSet ? '#a855f7'
                  : '#57d9a3';

    var cardStyle = 'style="flex:0 0 auto;min-width:0;width:46px;padding:3px 5px"';
    var html = '<div class="d-flex gap-1 mb-2" style="padding:4px 0;flex-wrap:nowrap;align-items:center">';

    // Multiplier card — shows base × 2 when full-set
    var multLabel = state.fullSet
        ? ('x' + state.baseMult + '×2')
        : ('x' + state.finalMult);
    html += '<div class="mp-mini-stat-card" ' + cardStyle +
        ' title="slots(' + state.slotsFilledBonus + ') + set(' + state.setBonus +
        ') + ringSub(' + state.ringSubBonus + ') + level(' + state.levelBonus + ')' +
        (state.fullSet ? ' — DOUBLED (full set)' : '') + '">' +
        '<div class="mp-mini-label" style="font-size:0.55rem">Multi</div>' +
        '<div style="font-size:0.78rem;font-weight:700;color:' + multColor + '">' + multLabel + (state.fullSet ? '🔥' : '') + '</div>' +
        '</div>';

    var checks = [
        {label:'⚔️', ok: state.mainFilled >= 1,   tip: state.mainFilled + '/6 main slots filled'},
        {label:'🎯', ok: state.matchingSet,        tip: state.matchingSet ? 'Set: ' + state.setTag : 'Helmet+Armor+Boots+Shield+Weapon need to match'},
        {label:'💍', ok: state.ring !== null,      tip: state.ring ? state.ring.name : 'No ring equipped (required for sub-slots)'},
        {label:'👹', ok: state.matchingMonsters,   tip: 'Two matching monsters on ring'},
        {label:'💎', ok: state.matchingGems,       tip: 'Two matching gems on ring'},
        {label:'🧵', ok: state.hasMaterial,        tip: 'Material attached to ring'}
    ];
    checks.forEach(function(c) {
        html += '<div class="mp-mini-stat-card" ' + cardStyle + ' title="' + escHtml(c.tip || '') + '">' +
            '<div style="font-size:0.9rem;line-height:1.1">' + c.label + '</div>' +
            '<div style="font-size:0.85rem;line-height:1.1">' + (c.ok ? '✅' : '❌') + '</div>' +
            '</div>';
    });
    return html + '</div>';
}

// ── Full stat breakdown for the Stats tab ─────────────────────────────────────
// Shows base stats, mastery multipliers, ability bonuses, equipment bonuses,
// computed totals, combat stats, and the equipment multiplier breakdown.
function buildFullStatBreakdown(pet) {
    var STAT_KEYS  = ['ATT','DEF','INT','DEX','HAP','ENE'];
    var STAT_COLORS = { ATT:'#e74c3c', DEF:'#3498db', INT:'#9b59b6', DEX:'#2ecc71', HAP:'#f1c40f', ENE:'#1abc9c' };
    var cs    = pet.computed_stats || {};
    var specs = pet.specializations || pet.Spec || [];
    var state = getEquipSetState(pet);
    var equipBonuses = calcEquipBonuses(pet);

    // ── Multiplier breakdown ──────────────────────────────────────────────────
    var multColor = state.fullSet ? '#f59e0b' : state.matchingSet ? '#a855f7' : '#57d9a3';
    var multLabel = state.fullSet ? ('x' + state.baseMult + ' × 2') : ('x' + state.finalMult);

    var multHtml = '<div class="mp-breakdown-sub">⚙️ Equipment Multiplier</div>' +
        '<div class="mp-battle-card mb-3" style="padding:10px 14px">' +
        '<div class="d-flex align-items-center gap-3 flex-wrap mb-2">' +
        '<div style="font-size:1.4rem;font-weight:900;color:' + multColor + ';font-family:Orbitron,sans-serif">' +
            multLabel + (state.fullSet ? ' 🔥' : '') +
        '</div>' +
        '<div style="font-size:0.72rem;color:var(--text-secondary)">' +
            (state.fullSet ? '<span style="color:#f59e0b;font-weight:700">Full Set — all bonuses doubled</span>' :
             state.matchingSet ? '<span style="color:#a855f7">Matching set equipped</span>' : 'Partial set') +
        '</div>' +
        '</div>' +
        '<div class="d-flex flex-wrap gap-2">';

    // Component rows — exactly mirrors server formula:
    // base_mult = slots_filled + set_bonus(3) + ring_sub_bonus + level_bonus
    // ring_sub_bonus = matching_monsters(1) + matching_gems(1) + material(1)  max 3
    // full_set doubles the result
    var components = [
        {
            label: 'Slots Filled',
            val:   state.slotsFilledBonus,
            tip:   state.mainFilled + '/6 main slots (Helmet, Armor, Boots, Ring, Shield, Weapon)',
            ok:    state.mainFilled > 0
        },
        {
            label: 'Matching Set',
            val:   state.setBonus,
            tip:   state.matchingSet ? 'Set: ' + state.setTag + ' — Helmet+Armor+Boots+Shield+Weapon all match' : 'Need Helmet+Armor+Boots+Shield+Weapon to share the same set tag',
            ok:    state.matchingSet
        },
        {
            label: 'Ring Sub-slots',
            val:   state.ringSubBonus,
            tip:   'Ring sub-slot bonuses: ' +
                   (state.matchingMonsters ? '✅' : '❌') + ' Matching Monsters (+1)  ' +
                   (state.matchingGems     ? '✅' : '❌') + ' Matching Gems (+1)  ' +
                   (state.hasMaterial      ? '✅' : '❌') + ' Material (+1)  ' +
                   (state.ring             ? '(Ring equipped ✅)' : '(No ring — sub-slots locked)'),
            ok:    state.ringSubBonus > 0
        },
        {
            label: 'Level Bonus',
            val:   state.levelBonus,
            tip:   'Level ' + (pet.level||1) + ' ÷ 50 = ' + state.levelBonus + ' (rounds down)',
            ok:    state.levelBonus > 0
        },
    ];
    components.forEach(function(c) {
        multHtml += '<div class="mp-mini-stat-card" style="min-width:90px;padding:5px 8px" title="' + escHtml(c.tip) + '">' +
            '<div style="font-size:0.58rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.4px">' + c.label + '</div>' +
            '<div style="font-size:0.88rem;font-weight:700;color:' + (c.ok ? '#57d9a3' : 'rgba(255,255,255,0.25)') + '">' +
                (c.ok ? '+' + c.val : '—') +
            '</div>' +
            '</div>';
    });

    // Ring sub-slot detail chips (shown inline under the main cards)
    var ringSubDetails = [
        { label: 'Monsters ×2', ok: state.matchingMonsters, tip: 'Two matching monsters on ring' },
        { label: 'Gems ×2',     ok: state.matchingGems,     tip: 'Two matching gems on ring'     },
        { label: 'Material',    ok: state.hasMaterial,      tip: 'Material attached to ring'     },
        { label: 'Ring',        ok: state.ring !== null,    tip: state.ring ? state.ring.name + ' (required for sub-slots)' : 'No ring equipped — sub-slots locked' },
    ];
    multHtml += '</div><div class="d-flex flex-wrap gap-1 mt-1">';
    ringSubDetails.forEach(function(r) {
        multHtml += '<div style="font-size:0.62rem;padding:2px 7px;border-radius:10px;border:1px solid ' +
            (r.ok ? 'rgba(87,217,163,0.4)' : 'rgba(255,255,255,0.1)') + ';color:' +
            (r.ok ? '#57d9a3' : 'rgba(255,255,255,0.3)') + '" title="' + escHtml(r.tip) + '">' +
            (r.ok ? '✅' : '❌') + ' ' + r.label +
            '</div>';
    });

    multHtml += '</div>' +
        '<div style="font-size:0.68rem;color:var(--text-secondary);margin-top:8px;border-top:1px solid rgba(255,215,0,0.1);padding-top:6px">' +
        '<strong style="color:var(--text-primary)">Formula:</strong> ' +
        state.slotsFilledBonus + ' (slots) + ' + state.setBonus + ' (set) + ' + state.ringSubBonus + ' (ring subs) + ' + state.levelBonus + ' (level) = ' +
        '<strong style="color:' + multColor + '">' + state.baseMult + '</strong>' +
        (state.fullSet ? ' × 2 (full set) = <strong style="color:#f59e0b">' + state.finalMult + '</strong> 🔥' : '') +
        '</div>' +
        '</div>';

    // ── Per-stat breakdown ────────────────────────────────────────────────────
    var statHtml = '<div class="mp-breakdown-sub">📊 Stat Breakdown</div>' +
        '<div class="mp-battle-card mb-3" style="padding:10px 14px">';

    // Header row
    statHtml += '<div style="display:grid;grid-template-columns:60px repeat(5,1fr);gap:4px;margin-bottom:6px;font-size:0.6rem;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.4px;border-bottom:1px solid rgba(255,215,0,0.1);padding-bottom:4px">' +
        '<div>Stat</div><div>Base</div><div>Mastery</div><div>Abilities</div><div>Equipment</div><div>Total</div>' +
        '</div>';

    STAT_KEYS.forEach(function(s) {
        var base  = pet[s] || 0;
        var total = cs[s] !== undefined ? cs[s] : (base + (equipBonuses[s] || 0));
        var col   = STAT_COLORS[s] || '#fff';
        var isSp  = specs.indexOf(s) !== -1;

        // Mastery multiplier from ability tree (server provides computed_stats which already includes it,
        // so we back-calculate: mastery_contribution = total_before_equip - base)
        // We show what we know: base, equip bonus, and the total from server.
        // Ability bonuses are baked into computed_stats by the server.
        var equipBonus = equipBonuses[s] || 0;
        // The server's computed_stats already includes mastery + ability + equipment.
        // We can show: base | (total - base - equipBonus) as "mastery+abilities" | equipBonus | total
        var masteryAbilityBonus = total - base - equipBonus;
        if (masteryAbilityBonus < 0) masteryAbilityBonus = 0;

        // Try to get mastery multiplier from tree state if available
        var masteryMult = 1.0;
        if (window._mpAbilityTreeState && window._mpAbilityTreeState.stat_mastery) {
            var m = window._mpAbilityTreeState.stat_mastery[s];
            if (m) masteryMult = m.multiplier || 1.0;
        }
        var masteryBonus = Math.round(base * (masteryMult - 1));
        var abilityBonus = masteryAbilityBonus - masteryBonus;
        if (abilityBonus < 0) { masteryBonus = masteryAbilityBonus; abilityBonus = 0; }

        statHtml += '<div style="display:grid;grid-template-columns:60px repeat(5,1fr);gap:4px;align-items:center;padding:3px 0;border-bottom:1px solid rgba(255,255,255,0.04)">' +
            '<div style="display:flex;align-items:center;gap:4px">' +
                '<img src="/static/Emojis/Pets/Deco/' + s + '.png" style="width:14px;height:14px;object-fit:contain" onerror="this.style.display=\'none\'">' +
                '<span style="font-size:0.72rem;font-weight:700;color:' + col + (isSp ? ';text-shadow:0 0 6px ' + col : '') + '">' + s + '</span>' +
            '</div>' +
            '<div style="font-size:0.72rem;color:var(--text-primary)">' + base.toLocaleString() + '</div>' +
            '<div style="font-size:0.72rem;color:' + (masteryBonus > 0 ? '#a855f7' : 'rgba(255,255,255,0.25)') + '">' +
                (masteryBonus > 0 ? '+' + masteryBonus.toLocaleString() : '—') +
            '</div>' +
            '<div style="font-size:0.72rem;color:' + (abilityBonus > 0 ? '#f59e0b' : 'rgba(255,255,255,0.25)') + '">' +
                (abilityBonus > 0 ? '+' + abilityBonus.toLocaleString() : '—') +
            '</div>' +
            '<div style="font-size:0.72rem;color:' + (equipBonus > 0 ? '#57d9a3' : 'rgba(255,255,255,0.25)') + '">' +
                (equipBonus > 0 ? '+' + equipBonus.toLocaleString() : '—') +
            '</div>' +
            '<div style="font-size:0.78rem;font-weight:700;color:' + col + '">' + total.toLocaleString() + '</div>' +
            '</div>';
    });

    // Combat stats row
    var att  = cs.ATT !== undefined ? cs.ATT : (pet.ATT || 0);
    var def  = cs.DEF !== undefined ? cs.DEF : (pet.DEF || 0);
    var int_ = cs.INT !== undefined ? cs.INT : (pet.INT || 0);
    var dex  = cs.DEX !== undefined ? cs.DEX : (pet.DEX || 0);
    var hap  = cs.HAP !== undefined ? cs.HAP : (pet.HAP || 0);
    var ene  = cs.ENE !== undefined ? cs.ENE : (pet.ENE || 0);
    var atk  = cs.attack     !== undefined ? cs.attack     : (att + dex);
    var dfn  = cs.defense    !== undefined ? cs.defense    : (def + int_);
    var hp   = cs.max_health !== undefined ? cs.max_health : Math.floor(((att+def+int_+dex+hap+ene)/6 + hap*ene)*10);

    statHtml += '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:8px;padding-top:6px;border-top:1px solid rgba(255,215,0,0.1)">' +
        '<div style="font-size:0.7rem"><span style="color:var(--text-secondary)">⚔️ ATK = ATT+DEX = </span><strong style="color:#e74c3c">' + fmtStat(atk) + '</strong></div>' +
        '<div style="font-size:0.7rem"><span style="color:var(--text-secondary)">🛡️ DEF = DEF+INT = </span><strong style="color:#3498db">' + fmtStat(dfn) + '</strong></div>' +
        '<div style="font-size:0.7rem"><span style="color:var(--text-secondary)">❤️ HP = f(all stats) = </span><strong style="color:#e74c3c">' + fmtStat(hp) + '</strong></div>' +
        '</div>';

    statHtml += '<div style="font-size:0.62rem;color:var(--text-secondary);margin-top:6px">' +
        '<span style="color:#a855f7">■</span> Mastery &nbsp;' +
        '<span style="color:#f59e0b">■</span> Abilities &nbsp;' +
        '<span style="color:#57d9a3">■</span> Equipment' +
        (specs.length ? ' &nbsp;· <span style="color:var(--gold-secondary)">★ Specialization stat</span>' : '') +
        '</div>';

    statHtml += '</div>';

    return '<div class="mp-stat-breakdown-wrap">' + multHtml + statHtml + '</div>';
}

// Returns just the inner breakdown HTML (XP + Battle + SS + Casino) — used by the
// "Stats Breakdown" tab panel. No collapse wrapper, no divider.
function buildBreakdownPanel(pet) {
    var xs = pet.xp_sources || {};
    var bs = pet.battle_stats || {};
    var gs = pet.gambling_stats || {};

    // ── XP Sources ──────────────────────────────────────────────
    var activities = [
        { label: 'Play',    emoji: '🎮', keys: ['play'] },
        { label: 'Train',   emoji: '🏋️', keys: ['training'] },
        { label: 'Mission', emoji: '🎯', keys: ['mission', 'mission_fail'] },
        { label: 'Quest',   emoji: '📜', keys: ['quest'] },
        { label: 'Battle',  emoji: '⚔️', keys: ['battle', 'npc_battle', 'pvp_battle'] },
    ];
    var xpRows = activities.map(function(a) {
        var net = a.keys.reduce(function(sum, k) { return sum + (xs[k] || 0); }, 0);
        return { label: a.label, emoji: a.emoji, net: net };
    }).filter(function(r) { return r.net !== 0; });

    var xpHtml = '';
    if (xpRows.length) {
        xpHtml += '<div class="mp-breakdown-sub">XP Sources</div><div class="d-flex gap-2 flex-wrap mb-2">';
        xpRows.forEach(function(r) {
            xpHtml += '<div class="mp-mini-stat-card">' +
                '<div class="mp-mini-label" style="font-size:0.7rem;display:flex;flex-direction:column;align-items:center;gap:1px">' +
                '<span>' + r.emoji + '</span><span>' + r.label.toUpperCase() + '</span></div>' +
                '<div style="font-size:0.78rem;font-weight:700" class="' + (r.net >= 0 ? 'text-success' : 'text-danger') + '">' +
                fmtXp(r.net) + ' XP</div>' +
                '</div>';
        });
        xpHtml += '</div>';
    }

    // ── Battle Records ───────────────────────────────────────────
    var battleTypes = [
        {key:'pvp',           name:'PvP'},
        {key:'npc',           name:'NPC'},
        {key:'wild_encounter',name:'Wild'},
        {key:'boss',          name:'Boss'},
        {key:'colosseum',     name:'Colosseum'}
    ];
    var battleHtml = '<div class="mp-breakdown-sub">Battle Records</div><div class="d-flex gap-2 flex-wrap mb-2">';
    battleTypes.forEach(function(bt) {
        var s = bs[bt.key] || {wins:0, losses:0};
        var wins   = s.wins   || 0;
        var losses = s.losses || 0;
        var rounds = s.rounds || 0;  // colosseum uses rounds
        var total  = bt.key === 'colosseum' ? rounds : (wins + losses);
        var wr = total > 0 ? ((wins / total) * 100).toFixed(0) : 0;
        battleHtml += '<div class="mp-mini-stat-card">' +
            '<div class="mp-mini-label">' + bt.name + '</div>' +
            '<div><span class="text-success" style="font-size:0.78rem;font-weight:700">' + wins + 'W</span>' +
            '<span style="color:var(--text-secondary);font-size:0.7rem"> / </span>' +
            '<span class="text-danger" style="font-size:0.78rem;font-weight:700">' + losses + 'L</span></div>' +
            '<div style="font-size:0.62rem;color:var(--text-secondary)">' + wr + '% WR</div>' +
            (bt.key === 'colosseum' && rounds > 0 ? '<div style="font-size:0.58rem;color:var(--text-secondary)">' + rounds + ' rounds</div>' : '') +
            '</div>';
    });
    battleHtml += '</div>';

    // ── Survivor Series ──────────────────────────────────────────
    var ssUid = 'mp-ss-stats-' + Date.now();
    var ssHtml = '<div class="mp-breakdown-sub">⚔️ Survivor Series</div>' +
        '<div id="' + ssUid + '" class="d-flex gap-2 flex-wrap mb-2" style="min-height:48px">' +
        '<div style="font-size:0.72rem;color:var(--text-secondary);padding:4px 0">Loading…</div></div>';
    setTimeout(function() { _loadSsStats(ssUid); }, 0);

    // ── Casino ───────────────────────────────────────────────────
    var games = [
        {key:'slots',        name:'Slots',      playedKey:'total_games_played', wonKey:''},
        {key:'blackjack',    name:'Blackjack',  playedKey:'rounds_played',      wonKey:'rounds_won'},
        {key:'holdem',       name:"Hold'em",    playedKey:'games_played',       wonKey:'games_won'},
        {key:'craps',        name:'Craps',      playedKey:'games_played',       wonKey:'games_won'},
        {key:'races',        name:'Races',      playedKey:'races_played',       wonKey:'races_won'},
        {key:'coinflip',     name:'Coin Flip',  playedKey:'games_played',       wonKey:'games_won'},
        {key:'rps',          name:'RPS',        playedKey:'games_played',       wonKey:'games_won'},
        {key:'keno',         name:'Keno',       playedKey:'games_played',       wonKey:'games_won'},
        {key:'wheel_of_pets',name:'Wheel',      playedKey:'games_played',       wonKey:'games_won'},
        {key:'powerball',    name:'Powerball',  playedKey:'tickets_bought',     wonKey:'games_won'},
        {key:'scratch_cards',name:'Scratch',    playedKey:'games_played',       wonKey:'games_won'},
    ];
    var netByGame = {
        'Slots':    (xs.slots_win||0)     + (xs.slots_bet||0),
        'Races':    (xs.race_win||0)      + (xs.race_bet||0),
        'Blackjack':(xs.blackjack_win||0) + (xs.blackjack_bet||0) + (xs.blackjack_double||0) + (xs.blackjack_split||0),
        'Craps':    (xs.craps_win||0)     + (xs.craps_bet||0),
        "Hold'em":  (xs.holdem_win||0)    + (xs.holdem_buyin||0)  + (xs.holdem_cashout||0),
        'Coin Flip':(xs.coinflip_win||0)  + (xs.minigame_bet||0),
        'RPS':      (xs.rps_win||0)       + (xs.rps_tie||0),
        'Keno':     (xs.keno_win||0)      + (xs.keno_bet||0),
        'Wheel':    (xs.wheel_win||0)     + (xs.wheel_bet||0),
        'Powerball':(xs.powerball_win||0),
        'Scratch':  (xs.scratch_win||0)   + (xs.scratch_bet||0),
    };
    var playedGames = games.filter(function(g) {
        var s = gs[g.key] || {};
        var played = s[g.playedKey] || s.games_played || s.races_played || s.rounds_played || s.total_games_played || s.tickets_bought || 0;
        return played > 0 || Math.abs(netByGame[g.name] || 0) > 0;
    });
    var casinoHtml = '';
    if (playedGames.length) {
        casinoHtml += '<div class="mp-breakdown-sub">Casino</div><div class="d-flex gap-2 flex-wrap mb-2">';
        playedGames.forEach(function(g) {
            var s = gs[g.key] || {};
            var played = s[g.playedKey] || s.games_played || s.races_played || s.rounds_played || s.total_games_played || s.tickets_bought || 0;
            var wins   = g.wonKey ? (s[g.wonKey] || 0) : 0;
            var won    = s.xp_won_total  || s.total_won  || 0;
            var lost   = s.xp_lost_total || s.total_lost || 0;
            var net    = (won - lost) || netByGame[g.name] || 0;
            var wr     = (played > 0 && wins > 0) ? ((wins / played) * 100).toFixed(0) + '%' : (played > 0 ? '—' : '');
            var highWin = s.highest_xp_win || 0;
            casinoHtml += '<div class="mp-mini-stat-card">' +
                '<div class="mp-mini-label">' + g.name + '</div>' +
                (played ? '<div style="font-size:0.72rem;color:var(--text-secondary)">' + played.toLocaleString() + ' played</div>' : '') +
                (wr ? '<div style="font-size:0.7rem">' + wr + ' WR</div>' : '') +
                (highWin > 0 ? '<div style="font-size:0.62rem;color:var(--gold-secondary)">Best: ' + fmtXp(highWin) + '</div>' : '') +
                '<div style="font-size:0.68rem" class="' + (net >= 0 ? 'text-success' : 'text-danger') + '">' +
                fmtXp(net) + ' XP</div>' +
                '</div>';
        });
        casinoHtml += '</div>';
    }

    // ── Empty state ──────────────────────────────────────────────
    if (!xpRows.length && !casinoHtml &&
        battleTypes.every(function(bt){ var s = bs[bt.key]||{}; return !(s.wins||s.losses); })) {
        return '<div style="font-size:0.78rem;color:var(--text-secondary);padding:8px 0">No activity data yet. Play, Train, Mission, or Battle to populate this view.</div>'
             + ssHtml;
    }
    return xpHtml + battleHtml + ssHtml + casinoHtml;
}

// Legacy stub — kept so older callers don't break. Returns the new panel content,
// minus any wrapper, since the Stats Breakdown tab now serves as the container.
function buildBreakdownCard(pet) { return buildBreakdownPanel(pet); }
function buildXpSourcesCard(pet)    { return ''; }
function buildBattleRecordCard(pet) { return ''; }
function buildCasinoCard(pet)       { return ''; }

// ── Collapse toggle ───────────────────────────────────────────────────────────
window.mpToggleCollapse = function(bodyId, chevId) {
    var body = document.getElementById(bodyId);
    var chev = document.getElementById(chevId);
    if (!body) return;
    var open = body.style.display !== 'none';
    body.style.display = open ? 'none' : '';
    if (chev) {
        chev.classList.toggle('mp-chev-collapsed', open);
        chev.classList.toggle('mp-chev-open', !open);
    }
};

// ── Friends & Foes card ───────────────────────────────────────────────────────
function buildFriendFoeCard() {
    var bodyId = 'mp-ff-body';
    var chevId = 'mp-ff-chev';
    var loadId = 'mp-ff-load-' + Date.now();

    var html =
        '<hr class="mp-divider my-2">' +
        '<div class="mp-collapse-header" onclick="mpToggleCollapse(\'' + bodyId + '\',\'' + chevId + '\')">' +
            '<span class="mp-section-title" style="margin:0">⚔️ Friends &amp; Foes</span>' +
            '<span id="' + chevId + '" class="mp-chev mp-chev-collapsed">▼</span>' +
        '</div>' +
        // Collapsed summary (always visible)
        '<div id="' + loadId + '-summary" class="mp-ff-summary">Loading…</div>' +
        // Expanded detail
        '<div id="' + bodyId + '" class="mp-collapse-body" style="display:none">' +
            '<div id="' + loadId + '-detail"></div>' +
        '</div>';

    setTimeout(function() { _loadFriendFoe(loadId + '-summary', loadId + '-detail'); }, 0);
    return html;
}

var _FF_COLORS = {
    best_friend: '#4caf50',
    friend:      '#2196f3',
    foe:         '#ff9800',
    enemy:       '#f44336',
};
var _FF_LABELS = {
    best_friend: 'Best Friend',
    friend:      'Friend',
    foe:         'Foe',
    enemy:       'Enemy',
};
var _FF_ICONS = {
    best_friend: '💚',
    friend:      '💙',
    foe:         '🧡',
    enemy:       '❤️',
};

function _loadFriendFoe(summaryId, detailId) {
    fetch('/api/world/my-relationships', { credentials: 'include' })
        .then(function(r) { return r.ok ? r.json() : null; })
        .then(function(d) {
            var sumEl = document.getElementById(summaryId);
            var detEl = document.getElementById(detailId);
            if (!sumEl) return;

            if (!d) {
                sumEl.innerHTML = '<span style="font-size:0.72rem;color:var(--text-secondary)">No relationships set.</span>';
                return;
            }

            var rels = d.relationships || [];           // outgoing: who I marked
            var incoming = d.incoming_relationships || []; // incoming: who marked me

            // ── Count helpers ──────────────────────────────────────
            function countByType(arr) {
                var c = { best_friend: 0, friend: 0, foe: 0, enemy: 0 };
                arr.forEach(function(r) { if (c[r.type] !== undefined) c[r.type]++; });
                return c;
            }

            var outCounts = countByType(rels);
            var inCounts  = countByType(incoming);

            // ── Summary row (always visible): two mini-sections ───
            function buildCountPills(counts) {
                var html = '<div class="mp-ff-counts">';
                ['best_friend','friend','foe','enemy'].forEach(function(t) {
                    html += '<span class="mp-ff-count-pill" style="border-color:' + _FF_COLORS[t] + ';color:' + _FF_COLORS[t] + '">' +
                        _FF_ICONS[t] + ' ' + counts[t] + ' ' + _FF_LABELS[t] + (counts[t] !== 1 ? 's' : '') +
                        '</span>';
                });
                html += '</div>';
                return html;
            }

            var sumHtml =
                '<div class="mp-ff-section-label">My Friends &amp; Foes</div>' +
                buildCountPills(outCounts) +
                '<div class="mp-ff-section-label" style="margin-top:6px">Who Has Me As…</div>' +
                buildCountPills(inCounts);
            sumEl.innerHTML = sumHtml;

            if (!detEl) return;

            // ── Expanded detail: two full sections ────────────────
            function buildGroupList(arr, showMutualLabel) {
                if (!arr.length) {
                    return '<div style="font-size:0.72rem;color:var(--text-secondary);padding:4px 0">None yet.</div>';
                }
                var html = '';
                ['best_friend','friend','foe','enemy'].forEach(function(t) {
                    var group = arr.filter(function(r) { return r.type === t; });
                    if (!group.length) return;
                    html += '<div class="mp-ff-group">' +
                        '<div class="mp-ff-group-title" style="color:' + _FF_COLORS[t] + '">' +
                            _FF_ICONS[t] + ' ' + _FF_LABELS[t] + 's (' + group.length + ')' +
                        '</div>' +
                        '<div class="mp-ff-group-list">';
                    group.forEach(function(r) {
                        html += '<div class="mp-ff-entry" style="border-left:3px solid ' + _FF_COLORS[t] + '">' +
                            '<span class="mp-ff-name">' + escHtml(r.username) + '</span>' +
                            (r.mutual_type ? '<span class="mp-ff-mutual" style="color:' + _FF_COLORS[r.mutual_type] + '">' +
                                (showMutualLabel ? '↔ I marked: ' : '↔ ') + _FF_LABELS[r.mutual_type] + '</span>' : '') +
                            '</div>';
                    });
                    html += '</div></div>';
                });
                return html;
            }

            var detHtml =
                '<div class="mp-ff-detail-section">' +
                    '<div class="mp-ff-detail-heading">👤 My Friends &amp; Foes</div>' +
                    buildGroupList(rels, false) +
                '</div>' +
                '<div class="mp-ff-detail-section" style="margin-top:10px">' +
                    '<div class="mp-ff-detail-heading">🔍 Who Has Me As…</div>' +
                    buildGroupList(incoming, true) +
                '</div>';
            detEl.innerHTML = detHtml;
        })
        .catch(function() {
            var sumEl = document.getElementById(summaryId);
            if (sumEl) sumEl.innerHTML = '<span style="font-size:0.72rem;color:var(--text-secondary)">Could not load relationships.</span>';
        });
}

function _loadSsStats(containerId) {
    fetch('/api/ss/pet-stats')
        .then(function(r) { return r.ok ? r.json() : null; })
        .then(function(d) {
            var c = document.getElementById(containerId);
            if (!c) return;
            if (!d || !d.games_played) {
                c.innerHTML = '<div style="font-size:0.72rem;color:var(--text-secondary)">No Survivor Series games yet.</div>';
                return;
            }
            var gp   = d.games_played  || 0;
            var gw   = d.games_won     || 0;
            var gl   = gp - gw;
            var wr   = gp > 0 ? ((gw / gp) * 100).toFixed(0) : 0;
            var kills = d.total_kills  || 0;
            var best  = d.best_placement != null ? '#' + d.best_placement : '—';

            function ssCard(label, val, sub) {
                return '<div class="mp-mini-stat-card">' +
                    '<div class="mp-mini-label" style="font-size:0.62rem;text-transform:uppercase;letter-spacing:0.5px">' + label + '</div>' +
                    '<div style="font-family:Orbitron,sans-serif;font-size:0.9rem;font-weight:700;color:var(--gold-primary)">' + val + '</div>' +
                    (sub ? '<div style="font-size:0.6rem;color:var(--text-secondary)">' + sub + '</div>' : '') +
                    '</div>';
            }

            c.innerHTML =
                ssCard('Games', gp, gw + 'W / ' + gl + 'L') +
                ssCard('Win Rate', wr + '%', gw + ' wins') +
                ssCard('Kills', kills, 'total elims') +
                ssCard('Best Place', best, 'all-time');
        })
        .catch(function() {
            var c = document.getElementById(containerId);
            if (c) c.innerHTML = '<div style="font-size:0.72rem;color:var(--text-secondary)">Could not load SS stats.</div>';
        });
}

function buildTokenStatsPanel(pet) {
    // Returns non-collapsible panel content; loads async into the body div
    var bodyId = 'mp-token-stats-panel-body';
    var summaryId = 'mp-token-stats-panel-summary';
    setTimeout(function() { _loadTokenStats(summaryId, bodyId); }, 0);
    return '<hr class="mp-divider my-2">' +
        '<div class="mp-section-title">📈 Pet Stocks</div>' +
        '<div id="' + summaryId + '" class="mp-ff-summary" style="font-size:0.75rem;color:var(--text-secondary);padding:4px 0">Loading token stats…</div>' +
        '<div id="' + bodyId + '"></div>';
}

function buildTokenStatsCard(pet) {
    // Returns a collapsible card shell; content is loaded async into the body div
    var bodyId = 'mp-token-stats-body';
    var chevId = 'mp-token-stats-chev';
    var uid    = 'mp-token-stats-' + Date.now();
    setTimeout(function() { _loadTokenStats(uid, bodyId); }, 0);
    return '<hr class="mp-divider my-2">' +
        '<div class="mp-collapse-header" onclick="mpToggleCollapse(\'' + bodyId + '\',\'' + chevId + '\')">' +
            '<span class="mp-section-title" style="margin:0">📈 Pet Stocks</span>' +
            '<span id="' + chevId + '" class="mp-chev mp-chev-collapsed">▼</span>' +
        '</div>' +
        '<div id="' + uid + '" class="mp-ff-summary" style="font-size:0.75rem;color:var(--text-secondary);padding:4px 0">Loading token stats…</div>' +
        '<div id="' + bodyId + '" class="mp-collapse-body" style="display:none"></div>';
}

function _loadTokenStats(summaryId, bodyId) {
    fetch('/api/pet-stock/pnl')
        .then(function(r) {
            if (r.status === 401) return null;
            if (!r.ok) throw new Error('Failed');
            return r.json();
        })
        .then(function(d) {
            var sumEl = document.getElementById(summaryId);
            var bodyEl = document.getElementById(bodyId);
            if (!sumEl) return;
            if (!d) { sumEl.textContent = 'Log in to see token stats.'; return; }

            var perToken   = d.per_token || {};
            var tokens     = Object.keys(perToken);
            var totalNet   = d.total_net || 0;
            var totalSpent = d.total_spent || 0;

            if (!tokens.length && !totalSpent) {
                sumEl.innerHTML = '<div style="font-size:0.75rem;color:var(--text-secondary)">No token trades yet.</div>';
                return;
            }

            var netCls  = totalNet >= 0 ? 'text-success' : 'text-danger';
            var netSign = totalNet >= 0 ? '+' : '';

            // Always-visible summary row
            sumEl.innerHTML =
                '<span style="font-size:0.72rem;color:var(--text-secondary)">Total Spent: <strong style="color:#ccc">' + totalSpent.toLocaleString() + ' XP</strong></span>' +
                '<span style="font-size:0.72rem;color:var(--text-secondary);margin-left:10px">Net P&amp;L: <strong class="' + netCls + '">' + netSign + totalNet.toLocaleString() + ' XP</strong></span>';

            if (!bodyEl) return;

            // Expanded per-token breakdown
            var ELEM_LABELS_MAP = {
                basic:'Basic', fire:'Fire', water:'Water', electric:'Electric', ice:'Ice',
                plant:'Plant', rock:'Rock', air:'Air', magic:'Magic', holy:'Holy',
                necro:'Necro', psychic:'Psychic', fighting:'Fighting',
                land:'Land', swimming:'Swimming', flying:'Flying'
            };
            var ELEM_EMOJIS_MAP = {
                basic:'/static/Emojis/Pets/Deco/Basic.png', fire:'/static/Emojis/Pets/Deco/Fire.png',
                water:'/static/Emojis/Pets/Deco/Water.png', electric:'/static/Emojis/Pets/Deco/Electric.png',
                ice:'/static/Emojis/Pets/Deco/Ice.png', plant:'/static/Emojis/Pets/Deco/Plant.png',
                rock:'/static/Emojis/Pets/Deco/Rock.png', air:'/static/Emojis/Pets/Deco/Air.png',
                magic:'/static/Emojis/Pets/Deco/Magic.png', holy:'/static/Emojis/Pets/Deco/Holy.png',
                necro:'/static/Emojis/Pets/Deco/Necro.png', psychic:'/static/Emojis/Pets/Deco/Psychic.png',
                fighting:'/static/Emojis/Pets/Deco/Fighting.png',
                land:'/static/Emojis/Pets/Deco/Land.png',
                swimming:'/static/Emojis/Pets/Deco/Swimming.png',
                flying:'/static/Emojis/Pets/Deco/Flying.png'
            };

            var html = '<div class="d-flex gap-2 flex-wrap">';
            tokens.forEach(function(tok) {
                var t     = perToken[tok];
                var net   = t.net || 0;
                var spent = t.spent || 0;
                var recv  = t.received || 0;
                var heldQ = t.held_qty || 0;
                var heldV = t.held_value || 0;
                var cls   = net >= 0 ? 'text-success' : 'text-danger';
                var sign  = net >= 0 ? '+' : '';
                var label = ELEM_LABELS_MAP[tok] || tok;
                var emoji = ELEM_EMOJIS_MAP[tok] || '';

                html += '<div class="mp-mini-stat-card" style="min-width:110px">' +
                    '<div style="display:flex;align-items:center;gap:5px;margin-bottom:3px">' +
                    (emoji ? '<img src="' + emoji + '" style="width:16px;height:16px;border-radius:3px">' : '') +
                    '<span class="mp-mini-label">' + label + '</span>' +
                    '</div>' +
                    '<div style="font-size:0.68rem;color:var(--text-secondary)">Spent: ' + spent.toLocaleString() + '</div>' +
                    '<div style="font-size:0.68rem;color:var(--text-secondary)">Sold: ' + recv.toLocaleString() + '</div>' +
                    (heldQ > 0 ? '<div style="font-size:0.68rem;color:#aaa">Held: ×' + heldQ + ' (~' + heldV.toLocaleString() + ' XP)</div>' : '') +
                    '<div style="font-size:0.72rem;font-weight:700;margin-top:3px" class="' + cls + '">' + sign + net.toLocaleString() + ' XP</div>' +
                    '</div>';
            });
            html += '</div>';
            bodyEl.innerHTML = html;
        })
        .catch(function() {
            var sumEl = document.getElementById(summaryId);
            if (sumEl) sumEl.textContent = 'Could not load token stats.';
        });
}

function bindAdoptBtn() {
    var btn=el('open-adopt-btn');
    if(btn) btn.addEventListener('click', openAdoptModal);
}

function openAdoptModal() {
    // Remove any existing modal first
    var existing = document.getElementById('adoptModal');
    if (existing) existing.remove();

    // Build modal and append to body — avoids z-index/overflow stacking issues
    var div = document.createElement('div');
    div.innerHTML =
        '<div class="modal fade" id="adoptModal" tabindex="-1">'+
        '<div class="modal-dialog modal-xl modal-dialog-scrollable">'+
        '<div class="modal-content">'+
        '<div class="modal-header">'+
        '<h5 class="modal-title">🐾 Adopt a Pet</h5>'+
        '<button type="button" class="btn-close" data-bs-dismiss="modal"></button>'+
        '</div>'+
        '<div class="modal-body" id="adopt-modal-body">'+
        '<div class="text-center py-4"><div class="spinner-border text-primary" role="status"></div><p class="mt-2">Loading species...</p></div>'+
        '</div>'+
        '</div></div></div>';
    document.body.appendChild(div.firstChild);

    bootstrap.Modal.getOrCreateInstance(document.getElementById('adoptModal')).show();

    fetch('/api/pets/available')
        .then(function(r){return r.json();})
        .then(function(d){
            _adoptList=d.species||[];
            showAdoptForm();
        })
        .catch(function(e){
            var body=el('adopt-modal-body');
            if(body) body.innerHTML='<div class="alert alert-danger">Failed to load: '+e.message+'</div>';
        });
}

function showAdoptForm() {
    var body=el('adopt-modal-body'); if(!body) return;

    var typeOpts=Object.keys(TYPE_INFO).map(function(k){
        return '<option value="'+k+'">'+TYPE_INFO[k].label+'</option>';
    }).join('');

    var e1Opts=Object.keys(ELEM_INFO).map(function(k){
        return '<option value="'+k+'">'+ELEM_INFO[k].label+'</option>';
    }).join('');

    body.innerHTML=
        '<div class="row g-3">'+

        // LEFT
        '<div class="col-lg-7">'+

        // Species custom picker
        '<div class="mb-3">'+
        '<label class="form-label fw-bold">🐾 Species</label>'+
        '<div class="sp-picker" id="sp-picker">'+
          '<div class="sp-trigger" id="sp-trigger" onclick="window._mpTogglePicker()">'+
            '<img id="sp-trig-img" src="/static/Emojis/Pets/Deco/Basic.png" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">'+
            '<span class="sp-name" id="sp-trig-name">-- Select a species --</span>'+
            '<span class="sp-arrow">▼</span>'+
          '</div>'+
          '<div class="sp-dropdown" id="sp-dropdown">'+
            '<div class="sp-search"><input type="text" id="sp-search-input" placeholder="Search species..." oninput="window._mpFilterPicker(this.value)" autocomplete="off"></div>'+
            '<div class="sp-list" id="sp-list"></div>'+
          '</div>'+
        '</div>'+
        '<div id="a-sp-desc" class="form-text text-muted mt-1"></div>'+
        '</div>'+

        // Type
        '<div class="mb-3">'+
        '<label class="form-label fw-bold">🏷️ Type</label>'+
        '<div class="d-flex align-items-center gap-2">'+
        '<img id="a-type-img" src="'+ELEM_IMG_BASE+'Land.png" style="width:28px;height:28px;object-fit:contain;flex-shrink:0">'+
        '<select class="form-select" id="a-type" onchange="window._mpTypeChange(this.value)">'+typeOpts+'</select>'+
        '</div>'+
        '<div id="a-type-desc" class="form-text mt-1" style="color:var(--gold-secondary)">'+TYPE_INFO.land.desc+'</div>'+
        '</div>'+

        // Elements
        '<div class="mb-3">'+
        '<label class="form-label fw-bold">⚡ Elements</label>'+
        '<div class="row g-2">'+
        '<div class="col-md-6">'+
        '<label class="form-label small">Primary Element</label>'+
        '<div class="d-flex align-items-center gap-2">'+
        '<img id="a-e1-img" src="'+ELEM_IMG_BASE+'Basic.png" style="width:28px;height:28px;object-fit:contain;flex-shrink:0">'+
        '<select class="form-select" id="a-e1" onchange="window._mpE1(this.value)">'+e1Opts+'</select>'+
        '</div>'+
        '<div id="a-e1-desc" class="form-text mt-1" style="color:var(--gold-secondary)">'+ELEM_INFO.basic.desc+'</div>'+
        '</div>'+
        '<div class="col-md-6" id="a-e2-col">'+
        '<label class="form-label small">Secondary Element <small class="text-muted">(optional)</small></label>'+
        '<div class="d-flex align-items-center gap-2">'+
        '<img id="a-e2-img" src="'+ELEM_IMG_BASE+'Basic.png" style="width:28px;height:28px;object-fit:contain;flex-shrink:0;opacity:.35">'+
        '<select class="form-select" id="a-e2" onchange="window._mpE2(this.value)"><option value="">None</option></select>'+
        '</div>'+
        '<div id="a-e2-desc" class="form-text mt-1 text-muted">No secondary element</div>'+
        '</div>'+
        '</div>'+
        '</div>'+

        // Name
        '<div class="mb-3">'+
        '<label class="form-label fw-bold">✏️ Pet Name</label>'+
        '<input type="text" class="form-control" id="a-name" maxlength="32" placeholder="Give your pet a name (required)">'+
        '<div class="invalid-feedback" id="a-name-err"></div>'+
        '</div>'+

        // Battle actions
        '<div class="mb-3">'+
        '<label class="form-label fw-bold">⚔️ Battle Actions <small class="text-muted fw-normal">(pre-filled from species — edit if you want)</small></label>'+
        '<div class="row g-2">'+
        '<div class="col-md-4"><label class="form-label small">Attack</label><input type="text" class="form-control form-control-sm" id="a-act-attack" maxlength="32" placeholder="Attack action"></div>'+
        '<div class="col-md-4"><label class="form-label small">Defense</label><input type="text" class="form-control form-control-sm" id="a-act-defense" maxlength="32" placeholder="Defense action"></div>'+
        '<div class="col-md-4"><label class="form-label small">Charge</label><input type="text" class="form-control form-control-sm" id="a-act-charge" maxlength="32" placeholder="Charge action"></div>'+
        '</div>'+
        '</div>'+

        '<button class="btn btn-primary" onclick="window._mpSubmit()">🐾 Adopt!</button>'+
        '</div>'+

        // RIGHT preview
        '<div class="col-lg-5">'+
        '<div class="card">'+
        '<div class="card-header text-center" id="a-preview-header"><span class="text-muted">Select a species to preview</span></div>'+
        '<div class="card-body" id="a-preview-body"><p class="text-muted text-center small">Species info will appear here</p></div>'+
        '</div>'+
        '</div>'+

        '</div>';

    // Populate the picker list
    renderPickerList(_adoptList);

    // Close picker when clicking outside
    document.addEventListener('click', closePicker);
}

function renderPickerList(list) {
    var container = el('sp-list'); if(!container) return;
    if(!list.length){ container.innerHTML='<div class="p-3 text-muted text-center small">No species found</div>'; return; }
    container.innerHTML = list.map(function(s) {
        var idx = _adoptList.indexOf(s);
        var cat = (s.category||'land').toLowerCase();
        var acts = s.actions||{};
        var actStr = [acts.Attack||acts.attack, acts.Defense||acts.defense, acts.Charge||acts.charge].filter(Boolean).join(' · ');
        var specBadges = (s.spec||[]).map(function(sp){
            return '<span class="badge spec-badge">'+sp+'</span>';
        }).join('');
        return '<div class="sp-item" data-idx="'+idx+'" onclick="window._mpPickForm('+idx+')">'+
            '<img src="/static/Emojis/Pets/'+s.name+'.png" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">'+
            '<div class="sp-item-info">'+
                '<div class="sp-item-name">'+s.name+'</div>'+
                '<div class="sp-item-meta">'+cap(cat)+'</div>'+
                '<div class="sp-item-stats">ATT:'+s.stats.ATT+' DEF:'+s.stats.DEF+' INT:'+s.stats.INT+' DEX:'+s.stats.DEX+' HAP:'+s.stats.HAP+' ENE:'+s.stats.ENE+'</div>'+
                (actStr?'<div class="sp-item-actions">⚔️ '+actStr+'</div>':'')+
                (specBadges?'<div class="sp-item-spec">'+specBadges+'</div>':'')+
            '</div>'+
        '</div>';
    }).join('');
}

function closePicker(e) {
    var picker = el('sp-picker');
    if(picker && !picker.contains(e.target)) {
        var dd = el('sp-dropdown');
        if(dd) dd.classList.remove('open');
        document.removeEventListener('click', closePicker);
    }
}

window._mpTogglePicker = function() {
    var dd = el('sp-dropdown');
    if(!dd) return;
    var isOpen = dd.classList.contains('open');
    dd.classList.toggle('open');
    if(!isOpen) {
        var inp = el('sp-search-input');
        if(inp) { inp.value=''; renderPickerList(_adoptList); setTimeout(function(){inp.focus();},50); }
        // re-attach close listener
        setTimeout(function(){ document.addEventListener('click', closePicker); }, 0);
    }
};

window._mpFilterPicker = function(q) {
    var lower = q.toLowerCase();
    var filtered = _adoptList.filter(function(s){
        return s.name.toLowerCase().includes(lower) ||
               (s.category||'').toLowerCase().includes(lower) ||
               (s.description||'').toLowerCase().includes(lower);
    });
    renderPickerList(filtered);
};

function adoptPickForm(idx) {
    var s=_adoptList[idx]; if(!s) return;
    _adoptSel=s;
    _adoptCat=(s.category||'land').toLowerCase();
    _adoptE1=(s.element||'basic').toLowerCase();
    _adoptE2='';

    // Update trigger display
    var tImg=el('sp-trig-img'), tName=el('sp-trig-name');
    if(tImg){ tImg.src=petImg(s.name); tImg.onerror=function(){this.src='/static/Emojis/Pets/Deco/Basic.png';}; }
    if(tName) tName.textContent=s.name;

    // Mark selected in list
    document.querySelectorAll('.sp-item').forEach(function(item){
        item.classList.toggle('selected', parseInt(item.dataset.idx)===idx);
    });

    // Close dropdown
    var dd=el('sp-dropdown'); if(dd) dd.classList.remove('open');
    document.removeEventListener('click', closePicker);

    // Description
    var desc=el('a-sp-desc'); if(desc) desc.textContent=s.description||'';

    // Type
    var typeEl=el('a-type');
    if(typeEl){ typeEl.value=_adoptCat; adoptTypeChange(_adoptCat); }

    // Primary element
    var e1El=el('a-e1');
    if(e1El){ e1El.value=_adoptE1; adoptE1(_adoptE1); }

    // Battle actions
    var acts=s.actions||{};
    var atkEl=el('a-act-attack'), defEl=el('a-act-defense'), chgEl=el('a-act-charge');
    if(atkEl) atkEl.value=acts.Attack||acts.attack||'';
    if(defEl) defEl.value=acts.Defense||acts.defense||'';
    if(chgEl) chgEl.value=acts.Charge||acts.charge||'';

    updateAdoptPreview();
}

function adoptTypeChange(val) {
    _adoptCat=val;
    var info=TYPE_INFO[val]||TYPE_INFO.land;
    var img=el('a-type-img');
    if(img) img.src=ELEM_IMG_BASE+info.img;
    var desc=el('a-type-desc');
    if(desc) desc.textContent=info.desc;
    updateAdoptPreview();
}

function adoptE1(val) {
    _adoptE1=val;
    var info=ELEM_INFO[val]||ELEM_INFO.basic;
    var img=el('a-e1-img');
    if(img){ img.src=ELEM_IMG_BASE+info.img; img.style.opacity='1'; }
    var desc=el('a-e1-desc');
    if(desc){ desc.textContent=info.desc; }

    // If Basic selected, disable and clear secondary
    var e2col=el('a-e2-col');
    var e2sel=el('a-e2');
    if(val==='basic') {
        _adoptE2='';
        if(e2sel){ e2sel.innerHTML='<option value="">Locked — Basic has no secondary</option>'; e2sel.disabled=true; }
        var e2desc=el('a-e2-desc');
        if(e2desc) e2desc.textContent='Basic element cannot have a secondary.';
        if(e2col) e2col.style.opacity='0.5';
    } else {
        if(e2sel){ e2sel.disabled=false; }
        if(e2col) e2col.style.opacity='1';
        // Rebuild secondary options excluding primary
        var prev=_adoptE2;
        var opts='<option value="">None</option>'+Object.keys(ELEM_INFO).filter(function(k){
            return k!==val && k!=='basic';
        }).map(function(k){
            return '<option value="'+k+'"'+(k===prev?' selected':'')+'>'+ELEM_INFO[k].label+'</option>';
        }).join('');
        if(e2sel){ e2sel.innerHTML=opts; _adoptE2=e2sel.value; }
        adoptE2(_adoptE2);
    }
    updateAdoptPreview();
}

function adoptE2(val) {
    _adoptE2=val||'';
    var info=val?ELEM_INFO[val]:null;
    var img=el('a-e2-img');
    if(img){ img.src=info?ELEM_IMG_BASE+info.img:ELEM_IMG_BASE+'Basic.png'; img.style.opacity=info?'1':'.35'; }
    var desc=el('a-e2-desc');
    if(desc){
        if(info){
            desc.textContent = info.desc;
            desc.style.color = 'var(--gold-secondary)';
        } else {
            desc.textContent = 'No secondary element';
            desc.style.color = '';
        }
    }
    updateAdoptPreview();
}

function updateAdoptPreview() {
    var hdr=el('a-preview-header'), bdy=el('a-preview-body');
    if(!hdr||!bdy) return;

    if(!_adoptSel){
        hdr.innerHTML='<span class="text-muted">Select a species to preview</span>';
        bdy.innerHTML='<p class="text-muted text-center small">Species info will appear here</p>';
        return;
    }

    var s=_adoptSel, e1=_adoptE1||'basic', e2=_adoptE2||'';
    hdr.innerHTML=
        '<img src="'+petImg(s.name)+'" style="width:64px;height:64px;object-fit:contain" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">'+
        '<div class="fw-bold mt-1">'+s.name+'</div>'+
        '<div class="d-flex justify-content-center gap-2 mt-1 flex-wrap">'+
        '<img src="'+catImg(_adoptCat)+'" style="width:22px;height:22px;object-fit:contain" title="'+cap(_adoptCat)+'" onerror="this.style.display=\'none\'">'+
        '<span class="badge bg-secondary small">'+cap(_adoptCat)+'</span>'+
        '<img src="'+elemImgPath(e1)+'" style="width:22px;height:22px;object-fit:contain" title="'+cap(e1)+'" onerror="this.style.display=\'none\'">'+
        '<span class="badge bg-primary small">'+cap(e1)+'</span>'+
        (e2?'<img src="'+elemImgPath(e2)+'" style="width:22px;height:22px;object-fit:contain" title="'+cap(e2)+'" onerror="this.style.display=\'none\'"><span class="badge bg-info text-dark small">'+cap(e2)+'</span>':'')+
        '</div>';

    var statsHtml='<div class="row g-1 mb-2">';
    ['ATT','DEF','INT','DEX','HAP','ENE'].forEach(function(st){
        var isSp=(s.spec||[]).indexOf(st)!==-1;
        statsHtml+='<div class="col-6 d-flex align-items-center">'+
            '<img src="/static/Emojis/Pets/Deco/'+st+'.png" style="width:16px;height:16px;margin-right:4px" onerror="this.style.display=\'none\'">'+
            '<span class="small'+(isSp?' stat-special':'')+'">'+st+': '+(s.stats[st]||0)+'</span></div>';
    });
    statsHtml+='</div>';

    var specHtml='';
    if(s.spec&&s.spec.length){
        specHtml='<div class="mb-2">';
        s.spec.forEach(function(sp){specHtml+='<span class="badge spec-badge me-1">'+sp+'</span>';});
        specHtml+='</div>';
    }

    bdy.innerHTML=statsHtml+specHtml+(s.description?'<p class="small text-muted mb-0">'+s.description+'</p>':'');
}

function submitAdopt() {
    var nameEl=el('a-name'), nameErr=el('a-name-err'), name=nameEl?nameEl.value.trim():'';
    if(nameEl) nameEl.classList.remove('is-invalid');
    if(!name){
        if(nameErr) nameErr.textContent='Pet name is required.';
        if(nameEl) nameEl.classList.add('is-invalid');
        return;
    }
    if(name.length>32||!/^[a-zA-Z0-9 \-_.,!?']+$/.test(name)){
        if(nameErr) nameErr.textContent='Invalid name (max 32 chars, letters/numbers/basic punctuation).';
        if(nameEl) nameEl.classList.add('is-invalid');
        return;
    }
    if(!_adoptSel){
        alert('Please select a species first.');
        return;
    }

    var body=el('adopt-modal-body');

    // Read form values BEFORE replacing body HTML (which destroys the DOM elements)
    var e1el=el('a-e1'), e2el=el('a-e2'), typeEl=el('a-type');
    var atkEl=el('a-act-attack'), defEl=el('a-act-defense'), chgEl=el('a-act-charge');
    var cat    = typeEl ? typeEl.value : _adoptCat;
    var elem1  = e1el  ? e1el.value   : (_adoptE1||'basic');
    var elem2  = e2el  ? e2el.value   : '';
    var actAtk = atkEl ? atkEl.value.trim() : '';
    var actDef = defEl ? defEl.value.trim() : '';
    var actChg = chgEl ? chgEl.value.trim() : '';

    if(body) body.innerHTML='<div class="text-center py-5"><div class="spinner-border text-primary" role="status"></div><p class="mt-3">Creating your pet...</p></div>';

    fetch('/api/pets/adopt',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
            category:   cat,
            species:    _adoptSel.name,
            element1:   elem1,
            element2:   elem2,
            customName: name,
            actions: {
                Attack:  actAtk,
                Defense: actDef,
                Charge:  actChg
            }
        })
    })
    .then(function(r){return r.json().then(function(d){return {ok:r.ok,d:d};});})
    .then(function(res){
        if(res.ok&&res.d.success){
            bootstrap.Modal.getInstance(el('adoptModal')).hide();
            init();
        } else {
            if(body) body.innerHTML='<div class="alert alert-danger"><strong>Adoption failed:</strong> '+(res.d.detail||res.d.error||'Unknown error')+
                '<br><button class="btn btn-sm btn-primary mt-2" onclick="window._mpForm()">Try Again</button></div>';
        }
    })
    .catch(function(e){
        if(body) body.innerHTML='<div class="alert alert-danger">Error: '+e.message+
            '<br><button class="btn btn-sm btn-primary mt-2" onclick="window._mpForm()">Try Again</button></div>';
    });
}

window._mpForm       = showAdoptForm;
window._mpPickForm   = adoptPickForm;
window._mpTypeChange = adoptTypeChange;
window._mpE1         = adoptE1;
window._mpE2         = adoptE2;
window._mpSubmit     = submitAdopt;
window.initMyPetPage = init;

init();
// ── Inventory item click — confirm + action ───────────────────────────────────
window._mpInvClick = function(name, type, action, equipCount, rarity, invCount) {
    var old = document.getElementById('inv-confirm-modal');
    if (old) old.remove();

    var isPotion = action === 'Use';
    var isChest  = action === 'Open';
    var isEquippable = !isPotion && !isChest;
    var count    = equipCount || 1;
    rarity   = rarity || 'Common';
    invCount = invCount || 1;

    // ── Chest opening flow ────────────────────────────────────────────────────
    if (isChest) {
        var chestMap = {
            Chest1:'chest1', Chest2:'chest2', Chest3:'chest3', Chest4:'chest4',
            chest1:'chest1', chest2:'chest2', chest3:'chest3', chest4:'chest4',
        };
        var chestType = chestMap[name] || 'chest1';
        if (chestType === 'chest4') {
            // Need type selection first
            _mpOpenInventoryChest4(chestType);
        } else {
            _mpOpenInventoryChest(chestType, null);
        }
        return;
    }

    var data = getEquipItem(name);
    var imgFile = (data && data.emoji_file) ? data.emoji_file : (name + '.png');
    var imgSrc  = '/static/Emojis/Pets/Equipment/' + imgFile;

    // Build effect/bonus description for confirm dialog
    var descLine = '';
    if (isPotion && data && data.use_effect) {
        var eff = data.use_effect;
        if (eff.type === 'attribute_boost') {
            descLine = '<div style="font-size:0.78rem;color:#ce93d8;margin-top:6px">+' + eff.value + ' ' + eff.attribute + ' permanently</div>';
        } else if (eff.type === 'elemental_boost') {
            descLine = '<div style="font-size:0.78rem;color:#ce93d8;margin-top:6px">Boosts stats matching <b>' + escHtml(eff.element) + '</b> element (+' + eff.value_single + ' single / +' + eff.value_dual + ' dual)</div>';
        } else if (eff.type === 'health_restore') {
            descLine = '<div style="font-size:0.78rem;color:#2ecc71;margin-top:6px">Restores ' + (eff.percent ? eff.percent + '% HP' : eff.value + ' HP') + '</div>';
        } else if (eff.type === 'xp_boost') {
            descLine = '<div style="font-size:0.78rem;color:var(--gold-primary);margin-top:6px">+' + eff.value + ' XP</div>';
        } else if (eff.type === 'random_boost') {
            descLine = '<div style="font-size:0.78rem;color:#ce93d8;margin-top:6px">+' + eff.value + ' to ' + eff.count + ' random stats</div>';
        } else {
            descLine = '<div style="font-size:0.78rem;color:var(--text-secondary);margin-top:6px">' + escHtml(eff.type.replace(/_/g,' ')) + '</div>';
        }
    } else if (!isPotion && data && data.bonuses) {
        var bParts = Object.keys(data.bonuses).map(function(k){ return k+': +'+data.bonuses[k]; });
        if (bParts.length) descLine = '<div style="font-size:0.72rem;color:#4caf50;margin-top:4px">'+bParts.join(' | ')+(count===2?' (×2 equipped)':'')+'</div>';
    }

    var confirmText = isPotion
        ? 'Use <b>' + escHtml(name) + '</b> on your pet? This cannot be undone.'
        : count === 2
            ? 'Equip both <b>' + escHtml(name) + '</b> to your pet (fills both slots)?'
            : 'Equip this ' + type.toLowerCase() + ' to your pet?';

    // Consume section with quantity slider
    var rarityLevels = {Common:1, Uncommon:2, Rare:3, Epic:4, Mythic:5};
    var petLevel = (_pet && _pet.level) ? parseInt(_pet.level) : 1;
    var xpPer = 10 * (rarityLevels[rarity] || 1) * petLevel;

    var consumeSection =
        '<div style="margin-top:10px;padding-top:8px;border-top:1px solid rgba(255,255,255,0.08)">'+
        '<div style="font-size:0.7rem;color:var(--text-secondary);margin-bottom:4px">🔥 Consume for XP</div>'+
        '<div style="display:flex;align-items:center;gap:6px;justify-content:center">'+
        '<span style="font-size:0.7rem;color:var(--text-secondary)">1</span>'+
        '<input id="consume-qty" type="range" min="1" max="'+invCount+'" value="'+invCount+'" style="flex:1;accent-color:#e74c3c">'+
        '<span style="font-size:0.7rem;color:var(--text-secondary)">'+invCount+'</span>'+
        '</div>'+
        '<div style="font-size:0.78rem;color:#fff;margin-top:2px">Qty: <span id="consume-qty-label" style="font-weight:700">'+invCount+'</span></div>'+
        '<div id="consume-xp-preview" style="font-size:0.82rem;color:var(--gold-primary);font-weight:700;margin-top:1px">'+
        '+' + (xpPer * invCount).toLocaleString() + ' XP'+
        '</div>'+
        '</div>';

    var div = document.createElement('div');
    div.innerHTML =
        '<div class="modal fade" id="inv-confirm-modal" tabindex="-1">'+
        '<div class="modal-dialog modal-sm modal-dialog-centered">'+
        '<div class="modal-content" style="background:var(--bg-secondary);border:1px solid var(--gold-primary)">'+
        '<div class="modal-header" style="border-bottom:1px solid rgba(255,215,0,0.2)">'+
        '<h6 class="modal-title" style="color:var(--gold-primary);font-family:Orbitron,sans-serif;font-size:0.85rem">'+
        (isPotion ? '🧪 Use Potion' : '⚔️ ' + action) + '</h6>'+
        '<button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>'+
        '</div>'+
        '<div class="modal-body text-center">'+
        '<img src="'+imgSrc+'" style="width:60px;height:60px;object-fit:contain;margin-bottom:8px;filter:drop-shadow(0 0 10px var(--gold-glow))" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'"><br>'+
        '<div style="font-size:0.95rem;color:var(--gold-primary);font-weight:700;font-family:Orbitron,sans-serif">'+escHtml(name)+'</div>'+
        descLine+
        '<div style="font-size:0.78rem;color:var(--text-secondary);margin-top:8px">'+confirmText+'</div>'+
        consumeSection+
        '</div>'+
        '<div class="modal-footer" style="border-top:1px solid rgba(255,215,0,0.2);justify-content:center;gap:8px">'+
        '<button class="btn btn-secondary btn-sm" data-bs-dismiss="modal">Cancel</button>'+
        '<button class="btn btn-sm" id="inv-consume-btn" style="background:rgba(231,76,60,0.2);border:1px solid #e74c3c;color:#e74c3c">🔥 Consume</button>'+
        '<button class="btn btn-primary btn-sm" id="inv-confirm-btn">'+action+'</button>'+
        '</div>'+
        '</div></div></div>';
    document.body.appendChild(div.firstChild);

    var modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('inv-confirm-modal'));
    modal.show();

    // Live-update XP preview as slider moves
    document.getElementById('consume-qty').addEventListener('input', function() {
        var q = parseInt(this.value);
        document.getElementById('consume-qty-label').textContent = q;
        document.getElementById('consume-xp-preview').textContent = '+' + (xpPer * q).toLocaleString() + ' XP';
    });

    document.getElementById('inv-confirm-btn').onclick = function() {
        var qty = parseInt(document.getElementById('consume-qty').value) || 1;
        modal.hide();
        if (isPotion) {
            _mpUsePotion(name, data, qty);
        } else if (count === 2) {
            _mpEquipItem(name, type, function() { _mpEquipItem(name, type); });
        } else {
            _mpEquipItem(name, type);
        }
    };

    document.getElementById('inv-consume-btn').onclick = function() {
        var qty = parseInt(document.getElementById('consume-qty').value) || invCount;
        modal.hide();
        _mpDoConsume(name, rarity, qty, imgSrc);
    };
};

// ── Inventory chest opening ───────────────────────────────────────────────────

function _mpOpenInventoryChest(chestType, selectedType) {
    var chestImgSrc = '/static/Emojis/Pets/Equipment/' + chestType + '.png';
    var chestColor  = ({chest1:'#9e9e9e',chest2:'#4caf50',chest3:'#2196f3',chest4:'#ff9800'})[chestType] || '#ffd700';

    fetch('/api/pets/inventory/open-chest', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({chest: chestType, selected_type: selectedType})
    })
    .then(function(r) { return r.json(); })
    .then(function(d) {
        if (d.success) {
            var items = d.items || [];
            _showChestAnimation(chestImgSrc, chestColor, items, function() {
                var oldPet = _pet;
                if (d.pet) { _refreshPet(d.pet); }
                if (window.PetGPP) {
                    if (d.animation) PetGPP.push(d.animation);
                    if (oldPet && d.pet) PetGPP.pushXpBar(oldPet, d.pet);
                }
            });
        } else {
            showResult('lm-result', false, d.error || d.detail || 'Failed to open chest.');
        }
    })
    .catch(function(e) { showResult('lm-result', false, 'Error: ' + e.message); });
}

function _mpOpenInventoryChest4(chestType) {
    // Show type selection modal for chest4
    var old = document.getElementById('chest4-inv-modal');
    if (old) old.remove();
    var types = ['Material','Gem','Monster','Potion','Hat'];
    var div = document.createElement('div');
    div.innerHTML =
        '<div class="modal fade" id="chest4-inv-modal" tabindex="-1">'+
        '<div class="modal-dialog modal-sm modal-dialog-centered">'+
        '<div class="modal-content" style="background:var(--bg-secondary);border:1px solid var(--gold-primary)">'+
        '<div class="modal-header" style="border-bottom:1px solid rgba(255,215,0,0.2)">'+
        '<h6 class="modal-title" style="color:var(--gold-primary);font-family:Orbitron,sans-serif;font-size:0.85rem">🌟 Open Mythic Chest</h6>'+
        '<button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>'+
        '</div>'+
        '<div class="modal-body text-center">'+
        '<p style="font-size:0.82rem;color:var(--text-secondary)">Choose your item type:</p>'+
        '<div class="d-flex flex-wrap gap-2 justify-content-center">'+
        types.map(function(t) {
            return '<button class="btn btn-sm" style="background:rgba(255,215,0,0.1);border:1px solid rgba(255,215,0,0.3);color:var(--gold-primary)" onclick="window._mpChest4InvSelect(\''+t+'\')">'+t+'</button>';
        }).join('')+
        '</div></div></div></div></div>';
    document.body.appendChild(div.firstChild);
    var modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('chest4-inv-modal'));
    modal.show();
}

window._mpChest4InvSelect = function(selectedType) {
    var modal = bootstrap.Modal.getInstance(document.getElementById('chest4-inv-modal'));
    if (modal) modal.hide();
    _mpOpenInventoryChest('chest4', selectedType);
};

function _mpEquipItem(name, type, callback) {
    fetch('/api/pets/equip', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({name: name, type: type})
    })
    .then(function(r){ return r.json(); })
    .then(function(d) {
        if (d.success && d.pet) {
            if (callback) {
                _pet = d.pet;
                callback();
            } else {
                _refreshPet(d.pet);
                _showToast('✅ ' + name + ' equipped!', true);
                if (window.PetGPP) {
                    var petImg = document.querySelector('#my-pet-header .mp-pet-img');
                    PetGPP.Particles.spawnAt('sparkle_up', petImg, '#ffd700');
                }
            }
        } else {
            _showToast('❌ ' + cleanDiscordText(d.detail || d.message || 'Equip failed').replace(/\*\*/g,'').trim(), false);
        }
    })
    .catch(function(e){ _showToast('❌ '+e.message, false); });
}

window._mpUnequipSlot = function(slotType) {
    fetch('/api/pets/unequip', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({slot: slotType})
    })
    .then(function(r){ return r.json(); })
    .then(function(d) {
        if (d.success && d.pet) {
            _refreshPet(d.pet);
            _showToast('📦 ' + cleanDiscordText(d.message || 'Unequipped').replace(/\*\*/g,'').trim(), true);
            if (window.PetGPP) {
                var petImg = document.querySelector('#my-pet-header .mp-pet-img');
                PetGPP.Particles.spawnAt('sparkle_up', petImg, '#9e9e9e');
            }
        } else {
            _showToast('❌ '+cleanDiscordText(d.detail||d.message||'Unequip failed'), false);
        }
    })
    .catch(function(e){ _showToast('❌ '+e.message, false); });
};

window._mpConsumeItem = function(name, rarity, count) {
    var data = getEquipItem(name);
    var imgFile = (data && data.emoji_file) ? data.emoji_file : (name + '.png');
    _mpDoConsume(name, rarity, count, '/static/Emojis/Pets/Equipment/' + imgFile);
};

function _mpDoConsume(name, rarity, qty, imgSrc) {
    _mpFeedAnimation(imgSrc, qty, function() {
        fetch('/api/pets/consume', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({name: name, quantity: qty})
        })
        .then(function(r){ return r.json(); })
        .then(function(d) {
            if (d.success && d.pet) {
                var oldPet = _pet;
                _refreshPet(d.pet);
                _showToast('🔥 ' + (d.message || 'Consumed!'), true);
                if (window.PetGPP) {
                    if (oldPet && d.pet) PetGPP.pushXpBar(oldPet, d.pet);
                    if (d.level_up) PetGPP.pushLevelChange(d.level_up);
                    var petImg = document.querySelector('#my-pet-header .mp-pet-img');
                    PetGPP.Particles.spawnAt('xp_burst', petImg, '#e74c3c');
                }
            } else {
                _showToast('❌ ' + (d.detail || d.message || 'Consume failed'), false);
            }
        })
        .catch(function(e){ _showToast('❌ ' + e.message, false); });
    });
}

function _mpFeedAnimation(imgSrc, qty, onComplete) {
    var petImgEl = document.querySelector('#my-pet-header .mp-pet-img');
    if (!petImgEl) { onComplete(); return; }

    var petRect = petImgEl.getBoundingClientRect();
    var targetX = petRect.left + petRect.width / 2;
    var targetY = petRect.top + petRect.height / 2;

    var count = Math.min(qty, 12);
    var completed = 0;

    for (var i = 0; i < count; i++) {
        (function(idx) {
            setTimeout(function() {
                var node = document.createElement('img');
                node.src = imgSrc;
                node.onerror = function() { this.src = '/static/Emojis/Pets/Deco/Basic.png'; };
                node.style.cssText = 'position:fixed;width:28px;height:28px;object-fit:contain;pointer-events:none;z-index:9999;border-radius:6px;filter:drop-shadow(0 0 6px rgba(231,76,60,0.9));';
                var startX = window.innerWidth * 0.25 + Math.random() * window.innerWidth * 0.5;
                var startY = window.innerHeight * 0.65 + Math.random() * 100;
                node.style.left = startX + 'px';
                node.style.top  = startY + 'px';
                document.body.appendChild(node);

                var startTime = null;
                var dur = 380 + Math.random() * 160;
                var arcH = 50 + Math.random() * 60;

                function step(ts) {
                    if (!startTime) startTime = ts;
                    var p = Math.min((ts - startTime) / dur, 1);
                    var ep = p * p;
                    var cx = startX + (targetX - startX) * ep;
                    var cy = startY + (targetY - startY) * ep - Math.sin(p * Math.PI) * arcH;
                    var sc = 1 - p * 0.55;
                    node.style.left    = (cx - 14) + 'px';
                    node.style.top     = (cy - 14) + 'px';
                    node.style.opacity = p < 0.8 ? '1' : String(1 - (p - 0.8) / 0.2);
                    node.style.transform = 'scale(' + sc + ')';
                    if (p < 1) {
                        requestAnimationFrame(step);
                    } else {
                        node.remove();
                        // Bounce pet image on each hit
                        petImgEl.style.transition = 'transform 0.07s ease-out';
                        petImgEl.style.transform  = 'scale(1.3)';
                        setTimeout(function() { petImgEl.style.transform = 'scale(1)'; }, 110);
                        completed++;
                        if (completed === count) {
                            setTimeout(function() {
                                petImgEl.style.transition = 'transform 0.12s ease-out';
                                petImgEl.style.transform  = 'scale(1.45)';
                                setTimeout(function() {
                                    petImgEl.style.transform  = 'scale(1)';
                                    petImgEl.style.transition = '';
                                    onComplete();
                                }, 180);
                            }, 60);
                        }
                    }
                }
                requestAnimationFrame(step);
            }, idx * 75);
        })(i);
    }
}
function _mpUsePotion(name, data, qty) {
    qty = qty || 1;
    _showPotionAnimation(name, data, function() {
        fetch('/api/pets/use-potion', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({name: name, quantity: qty})
        })
        .then(function(r){ return r.json(); })
        .then(function(d) {
            if (d.success && d.pet) {
                var oldPet = _pet;
                _refreshPet(d.pet);
                var msg = name + (qty > 1 ? ' x'+qty : '') + ' used!';
                if (d.message) {
                    var clean = String(d.message)
                        .replace(/<img[^>]*>/gi, '').replace(/<[^>]+>/g, '')
                        .replace(/\*\*/g, '')
                        .replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>')
                        .trim();
                    if (clean) msg = name + (qty > 1 ? ' x'+qty : '') + ' — ' + clean;
                }
                _showToast('🧪 ' + msg, true);
                if (window.PetGPP) {
                    if (oldPet && d.pet) PetGPP.pushXpBar(oldPet, d.pet);
                    var petImg = document.querySelector('#my-pet-header .mp-pet-img');
                    PetGPP.Particles.spawnAt('xp_burst', petImg, '#ce93d8');
                }
            } else {
                _showToast('❌ ' + (d.detail || d.message || 'Potion failed'), false);
            }
        })
        .catch(function(e){ _showToast('❌ ' + e.message, false); });
    });
}

function _showPotionAnimation(name, data, callback) {
    var imgFile = (data && data.emoji_file) ? data.emoji_file : (name + '.png');
    var imgSrc  = '/static/Emojis/Pets/Equipment/' + imgFile;

    var overlay = document.createElement('div');
    overlay.id = 'potion-anim-overlay';
    overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:9999;display:flex;align-items:center;justify-content:center;pointer-events:none;';
    overlay.innerHTML =
        '<div id="potion-anim-inner" style="text-align:center;animation:potionPop 1.8s ease forwards">'+
        '<img src="'+imgSrc+'" style="width:88px;height:88px;object-fit:contain;filter:drop-shadow(0 0 24px #9c27b0)" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">'+
        '<div style="font-size:1.1rem;color:#ce93d8;font-family:Orbitron,sans-serif;margin-top:10px;text-shadow:0 0 12px #9c27b0">✨ '+escHtml(name)+'</div>'+
        '<div style="font-size:0.82rem;color:#e1bee7;margin-top:4px">Applying effects...</div>'+
        '</div>';
    document.body.appendChild(overlay);

    if (!document.getElementById('potion-anim-style')) {
        var style = document.createElement('style');
        style.id = 'potion-anim-style';
        style.textContent =
            '@keyframes potionPop {'+
            '0%   { opacity:0; transform:scale(0.3) translateY(40px); }'+
            '30%  { opacity:1; transform:scale(1.15) translateY(-10px); }'+
            '60%  { opacity:1; transform:scale(1.0) translateY(0); }'+
            '80%  { opacity:1; transform:scale(1.05); }'+
            '100% { opacity:0; transform:scale(0.8) translateY(-30px); }'+
            '}';
        document.head.appendChild(style);
    }

    setTimeout(function() {
        overlay.remove();
        callback();
    }, 1800);
}

function _showToast(msg, success) {
    var old = document.getElementById('mp-toast');
    if (old) old.remove();
    var t = document.createElement('div');
    t.id = 'mp-toast';
    t.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:9998;padding:10px 18px;border-radius:8px;font-size:0.82rem;font-weight:600;max-width:320px;word-break:break-word;'+
        'background:'+(success?'rgba(39,174,96,0.95)':'rgba(192,57,43,0.95)')+';color:#fff;box-shadow:0 4px 16px rgba(0,0,0,0.5);animation:toastIn 0.3s ease;';
    t.textContent = msg;
    if (!document.getElementById('toast-anim-style')) {
        var s = document.createElement('style');
        s.id = 'toast-anim-style';
        s.textContent = '@keyframes toastIn{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}';
        document.head.appendChild(s);
    }
    document.body.appendChild(t);
    setTimeout(function(){ t.style.opacity='0'; t.style.transition='opacity 0.4s'; setTimeout(function(){t.remove();},400); }, 3000);
}

// ── Item hover card ───────────────────────────────────────────────────────────
var _hoverEl = null;

var BONUS_COLORS = {
    ATT:'#e74c3c', DEF:'#3498db', INT:'#9b59b6',
    DEX:'#2ecc71', HAP:'#f1c40f', ENE:'#1abc9c'
};

function _showItemHover(name, x, y) {
    var card = document.getElementById('mp-item-hover');
    if (!card) return;
    var data = getEquipItem(name);
    if (!data) { _hideItemHover(); return; }

    var imgSrc = EMOJI_PATH_MAP[name.toLowerCase()]
        || '/static/Emojis/Pets/Equipment/' + (data.emoji_file || name + '.png');
    var rarity = data.rarity || 'Common';
    var rarityColor = rc(rarity);
    var bonuses = data.bonuses || {};
    var effect  = data.use_effect || null;

    document.getElementById('mp-hover-img').src = imgSrc;
    document.getElementById('mp-hover-name').textContent = name;

    var rarEl = document.getElementById('mp-hover-rarity');
    rarEl.textContent = rarity;
    rarEl.style.background = rarityColor;
    rarEl.style.color = rarity === 'Common' ? '#fff' : '#000';

    var bonEl = document.getElementById('mp-hover-bonuses');
    bonEl.innerHTML = '';
    Object.keys(bonuses).forEach(function(stat) {
        var span = document.createElement('span');
        span.className = 'mp-hover-bonus';
        span.style.color = BONUS_COLORS[stat] || '#fff';
        span.textContent = stat + ': +' + bonuses[stat];
        bonEl.appendChild(span);
    });

    var descEl = document.getElementById('mp-hover-desc');
    if (effect) {
        var t2 = effect.type, desc = '';
        if (t2 === 'attribute_boost')  desc = '+'+effect.value+' '+effect.attribute;
        else if (t2 === 'elemental_boost') desc = '+'+effect.value_single+' to 3 stats (single) / +'+effect.value_dual+' to 4 (dual)';
        else if (t2 === 'random_boost') desc = '+'+effect.value+' to '+effect.count+' random stats';
        else if (t2 === 'luck_boost')   desc = '+'+effect.min+'–'+effect.max+' to all 6 stats';
        else if (t2 === 'mega_boost')   desc = '+'+effect.value+' to all 6 stats';
        else if (t2 === 'health_boost') desc = '+'+effect.value+' HAP & ENE';
        else if (t2 === 'xp_boost')     desc = effect.multiplier+'× Level XP instantly';
        descEl.textContent = desc;
        descEl.style.display = desc ? '' : 'none';
    } else {
        descEl.style.display = 'none';
    }

    // Position — keep inside viewport
    var w = 168, h = 190;
    var vw = window.innerWidth, vh = window.innerHeight;
    var left = x + 14;
    var top  = y + 14;
    if (left + w > vw - 8) left = x - w - 8;
    if (top  + h > vh - 8) top  = y - h - 8;
    card.style.left    = left + 'px';
    card.style.top     = top  + 'px';
    card.style.display = 'block';
}

function _hideItemHover() {
    var card = document.getElementById('mp-item-hover');
    if (card) card.style.display = 'none';
}

document.addEventListener('mousemove', function(e) {
    if (_hoverEl) _showItemHover(_hoverEl, e.clientX, e.clientY);
});
document.addEventListener('mouseover', function(e) {
    var t = e.target.closest('[data-hover-item]');
    if (t) _hoverEl = t.getAttribute('data-hover-item');
});
document.addEventListener('mouseout', function(e) {
    var t = e.target.closest('[data-hover-item]');
    if (t && !t.contains(e.relatedTarget)) { _hoverEl = null; _hideItemHover(); }
});

}());


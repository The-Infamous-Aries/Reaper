(function () {
'use strict';

var ELEM_IMG_BASE = '/static/Emojis/Pets/Deco/';

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
            ['Materials','Gems','Monsters','Hats','Potions'].forEach(function(cat) {
                (d[cat]||[]).forEach(function(item) {
                    _equipData[item.name.toLowerCase()] = item;
                });
            });
        })
        .catch(function(){});
}

function getEquipItem(name) {
    return _equipData[(name||'').toLowerCase()] || null;
}

function bonusTooltip(item) {
    if (!item) return '';
    var bonuses = item.bonuses || {};
    var parts = Object.keys(bonuses).map(function(k){ return k+': +'+bonuses[k]; });
    if (!parts.length) return item.rarity || '';
    return parts.join(' | ') + (item.rarity ? ' · '+item.rarity : '');
}

// Client-side equipment bonus calculation (mirrors pet_brain.py _calculate_equipment_bonuses)
function calcEquipBonuses(pet) {
    var eq = pet.equipment || {};
    var level = parseInt(pet.level||1, 10);
    var levelMult = 1 + Math.floor(level / 50);
    var bonuses = {ATT:0,DEF:0,INT:0,DEX:0,HAP:0,ENE:0};

    var items = [];
    var mat = eq.Material;
    if (mat && typeof mat === 'object' && !Array.isArray(mat)) items.push(mat);
    var matList = Array.isArray(eq.Material) ? eq.Material : [];
    matList.forEach(function(m){ if(m && m.name) items.push(m); });
    var hat = eq.Hat;
    if (hat && typeof hat === 'object') items.push(hat);
    (eq.Gems||[]).forEach(function(g){ if(g && g.name) items.push(g); });
    (eq.Monsters||[]).forEach(function(m){ if(m && m.name) items.push(m); });

    // Count duplicates
    var counts = {};
    items.forEach(function(item){
        var k = (item.name||'').toLowerCase();
        counts[k] = (counts[k]||0) + 1;
    });

    items.forEach(function(item) {
        var data = getEquipItem(item.name);
        var b = (data && data.bonuses) ? data.bonuses : (item.bonuses || {});
        var isDup = counts[(item.name||'').toLowerCase()] >= 2;
        var mult = isDup ? 2 : 1;
        Object.keys(b).forEach(function(stat){
            if (bonuses[stat] !== undefined) bonuses[stat] += parseInt(b[stat]||0, 10) * mult;
        });
    });

    Object.keys(bonuses).forEach(function(k){ bonuses[k] *= levelMult; });
    return bonuses;
}

function init() {
    hide('mypet-empty'); hide('mypet-display'); hide('mypet-error'); show('mypet-loading');
    loadEquipData();
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

function renderPetCard(pet) {
    var cat  = (pet.category||pet.type||'land').toLowerCase();
    var e1   = (pet.element||'basic').toLowerCase();
    var _raw2 = pet.element2;
    var e2   = (_raw2 && _raw2 !== 'none' && _raw2 !== 'null' && _raw2 !== 'basic' && String(_raw2).trim() !== '') ? String(_raw2).toLowerCase() : '';
    var sp   = pet.species||'Unknown';
    var cs   = pet.computed_stats||{};
    var specs= pet.specializations||pet.Spec||[];
    var xpMax= pet.xp_for_next_level||200;
    var xpPct= Math.min(((pet.experience||0)/xpMax)*100,100).toFixed(1);
    var hdr = el('my-pet-header');
    if (hdr) {
        hdr.innerHTML =
            '<div class="d-flex align-items-center gap-2">'+
            '<img src="'+petImg(sp)+'" class="mp-pet-img" onerror="this.src=\'/static/Emojis/Pets/Basic.png\'">'+
            '<div>'+
            '<div class="fw-bold" style="font-family:Orbitron,sans-serif;color:var(--gold-primary);font-size:0.95rem;text-shadow:0 0 8px var(--gold-glow)">'+(pet.name||sp)+'</div>'+
            '<div class="d-flex align-items-center gap-1 mt-1 flex-wrap">'+
            '<span class="badge bg-warning text-dark" style="font-size:0.6rem">Lv.'+(pet.level||1)+'</span>'+
            '<img src="'+catImg(cat)+'" style="width:18px;height:18px;object-fit:contain" title="'+cap(cat)+'" onerror="this.style.display=\'none\'">'+
            '<span style="font-size:0.75rem;color:var(--text-secondary)">'+cap(cat)+'</span>'+
            '<span style="color:rgba(255,215,0,0.4);margin:0 2px">|</span>'+
            '<img src="'+elemImgPath(e1)+'" style="width:18px;height:18px;object-fit:contain" title="'+cap(e1)+'" onerror="this.style.display=\'none\'">'+
            '<span style="font-size:0.75rem;color:var(--gold-secondary)">'+cap(e1)+'</span>'+
            (e2 ? '<span style="color:rgba(255,215,0,0.4);margin:0 2px">/</span><img src="'+elemImgPath(e2)+'" style="width:18px;height:18px;object-fit:contain" title="'+cap(e2)+'" onerror="this.style.display=\'none\'"><span style="font-size:0.75rem;color:var(--gold-secondary)">'+cap(e2)+'</span>' : '')+
            '</div></div></div>';
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
        '<span class="mp-combat-item"><span class="mp-combat-label">⚔️ ATK</span><span class="mp-combat-val">'+atk+'</span></span>'+
        '<span class="mp-combat-item"><span class="mp-combat-label">🛡️ DEF</span><span class="mp-combat-val">'+dfn+'</span></span>'+
        '<span class="mp-combat-item"><span class="mp-combat-label">❤️ HP</span><span class="mp-combat-val">'+hp.toLocaleString()+'</span></span>'+
        '</div>';
    var xpHtml =
        '<div class="mp-xp-bar-wrap mb-1"><div class="mp-xp-bar" style="width:'+xpPct+'%"></div></div>'+
        '<div style="font-size:0.68rem;color:var(--text-secondary);text-align:right">'+(pet.experience||0).toLocaleString()+' / '+xpMax.toLocaleString()+' XP</div>';
    var body = el('my-pet-body');
    if (body) body.innerHTML = xpHtml + buildEquipped(pet) + buildInventoryCollapsible(pet) + '<hr class="mp-divider my-2">' + statsHtml + combatHtml + buildBattleRecordCard(pet) + buildCasinoCard(pet);
}

function bindTabs() {}
function renderTab(tab) {}

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
        {id:'train',  label:'🏋️ Train'},
        {id:'mission',label:'🗺️ Mission'},
        {id:'play',   label:'🎮 Play'},
        {id:'battle', label:'⚔️ Battle'},
        {id:'quest',  label:'🗡️ Quest'},
        {id:'market', label:'📦 Loot Market'},
        {id:'rename', label:'✏️ Rename'},
        {id:'kill',   label:'💀 Kill Pet'}
    ];

    var html = '<div class="d-flex gap-2 mb-4 flex-wrap">';
    tabs.forEach(function(t, i) {
        html += '<button class="mp-action-tab'+(i===0?' active':'')+'" id="tab-'+t.id+'" onclick="window._mpTab(\''+t.id+'\')">'+t.label+'</button>';
    });
    html += '</div>';

    // ── Train ──────────────────────────────────────────────────────────────
    html += '<div id="panel-train">'+
        '<div class="mp-section-title">Train Your Pet</div>'+
        '<div class="mp-battle-card mb-3" style="font-size:0.82rem;color:var(--text-secondary)">'+
        'Send your pet to train and earn XP. Higher difficulty = more XP but lower success rate.'+
        '</div>'+
        '<div class="row g-2 mb-3">'+
        ['Easy','Average','Hard'].map(function(d) {
            var xp = {Easy:50,Average:100,Hard:200}[d];
            var chance = {Easy:'90%',Average:'70%',Hard:'50%'}[d];
            return '<div class="col-md-4"><div class="mp-mini-stat-card" style="cursor:pointer;transition:all 0.2s" id="train-opt-'+d+'" onclick="window._mpSelectTrain(\''+d+'\')">'+
                '<div class="mp-mini-label">'+d+'</div>'+
                '<div style="font-size:0.78rem;color:var(--gold-secondary);font-weight:700">'+xp+' XP</div>'+
                '<div style="font-size:0.7rem;color:var(--text-secondary)">'+chance+' success</div>'+
                '</div></div>';
        }).join('')+
        '</div>'+
        '<button class="mp-adopt-btn" onclick="window._mpTrain()">Start Training</button>'+
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
            var xp = {Easy:100,Average:250,Hard:500}[d];
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
        '<div class="mb-3">'+
        '<label class="form-label" style="font-size:0.8rem;color:var(--text-secondary)">Gamble XP <small>(optional — risk XP for bonus reward)</small></label>'+
        '<input type="number" class="form-control mp-input" id="mission-gamble" min="0" placeholder="0" style="max-width:160px">'+
        '</div>'+
        '<button class="mp-adopt-btn" onclick="window._mpMission()">Launch Mission</button>'+
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
        '<button class="mp-adopt-btn" onclick="window._mpPlay()">Go Play!</button>'+
        '<div id="play-result" class="mt-3"></div>'+
        '</div>';

    // ── Battle ─────────────────────────────────────────────────────────────
    html += '<div id="panel-battle" style="display:none">'+
        '<div class="mp-section-title">⚔️ NPC Battle</div>'+
        '<div class="mp-battle-card mb-3" style="font-size:0.82rem;color:var(--text-secondary)">'+
        'Fight a generated enemy scaled to your pet\'s stats. Win to earn XP and loot. Difficulty affects enemy strength and XP rewards.'+
        '</div>'+
        '<div class="row g-2 mb-3">'+
        [['easy','Easy','Weaker enemy, 0.7x stats'],['average','Average','Matched enemy, 1.1x stats'],['hard','Hard','Stronger enemy, 1.5x stats']].map(function(d){
            return '<div class="col-md-4"><div class="mp-mini-stat-card" style="cursor:pointer;transition:all 0.2s" id="battle-opt-'+d[0]+'" onclick="window._mpSelectBattle(\''+d[0]+'\')">'+
                '<div class="mp-mini-label">'+d[1]+'</div>'+
                '<div style="font-size:0.7rem;color:var(--text-secondary)">'+d[2]+'</div>'+
                '</div></div>';
        }).join('')+
        '</div>'+
        '<button class="mp-adopt-btn" id="battle-start-btn" onclick="window._mpBattle()">⚔️ Start Battle</button>'+
        '<div id="battle-result" class="mt-3"></div>'+
        '</div>';

    // ── Quest ──────────────────────────────────────────────────────────────
    var QLOC_EMOJI = {Camp:'camping',Bonfire:'bonfire',Beach:'beach',Forest:'forest','Hot Air Balloon':'hotairballoon',Cruiseship:'cruiseship',Mountain:'mountain',Gym:'gym',Graveyard:'graveyard',Festival:'festival',Glacier:'glacier',Pyramids:'pyramids'};
    html += '<div id="panel-quest" style="display:none">'+
        '<div class="mp-section-title">⚔️ Quest</div>'+
        '<div class="mp-battle-card mb-3" style="font-size:0.82rem;color:var(--text-secondary)">'+
        'AI-generated 5-stage quests. Each stage presents a challenge with 3 choices tied to your pet\'s stats. Earn XP and loot along the way.<br>'+
        '<span style="color:var(--gold-secondary)">Quests are generated by AI — may take a moment to start.</span>'+
        '</div>'+

        // Setup (shown before quest starts)
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
        '<button class="mp-adopt-btn" onclick="window._mpQuestStart()">⚔️ Begin Quest</button>'+
        '<div id="quest-start-result" class="mt-2"></div>'+
        '</div>'+

        // Active quest (shown during quest)
        '<div id="quest-active" style="display:none">'+
        '<div class="mp-battle-card mb-3" id="quest-stage-box">'+
        '<div id="quest-progress" style="font-size:0.7rem;color:var(--text-secondary);margin-bottom:6px"></div>'+
        '<div id="quest-stage-name" class="mp-section-title" style="margin-bottom:6px"></div>'+
        '<div id="quest-event" style="font-size:0.85rem;color:var(--text-primary);margin-bottom:12px;line-height:1.5"></div>'+
        '<div id="quest-choices" class="d-flex flex-column gap-2"></div>'+
        '</div>'+
        '<div id="quest-outcome" class="mt-2"></div>'+
        '<div id="quest-xp-track" style="font-size:0.75rem;color:var(--gold-secondary);margin-top:4px"></div>'+
        '</div>'+

        // Quest result (shown when done)
        '<div id="quest-result" style="display:none"></div>'+
        '</div>';

    // ── Loot Market ────────────────────────────────────────────────────────
    var CHEST_INFO = {
        chest1:{label:'Chest 1',cost:'1× Key1',items:'1 Common or Uncommon item',color:'#9e9e9e'},
        chest2:{label:'Chest 2',cost:'1× Key2',items:'1 Rare item',color:'#4caf50'},
        chest3:{label:'Chest 3',cost:'1× Key3',items:'1 Epic item',color:'#2196f3'},
        chest4:{label:'Chest 4',cost:'1× Key1 + Key2 + Key3',items:'1 picked type + 1 Uncommon+',color:'#ff9800'}
    };
    html += '<div id="panel-market" style="display:none">'+
        '<div class="mp-section-title">📦 Loot Market</div>'+
        '<div class="mp-battle-card mb-3" style="font-size:0.82rem;color:var(--text-secondary)">'+
        'Spend keys to open chests and earn items. Keys are earned from Play, Mission, and Quest activities.'+
        '</div>'+

        // Chest selection
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

        // Chest 4 type selector (hidden unless chest4 selected)
        '<div id="lm-type-row" style="display:none" class="mb-3">'+
        '<label class="form-label" style="font-size:0.8rem;color:var(--text-secondary)">Select guaranteed item type (Chest 4)</label>'+
        '<div class="d-flex gap-2 flex-wrap">'+
        ['Material','Gem','Monster','Potion','Hat'].map(function(t){
            return '<div class="mp-mini-stat-card" style="cursor:pointer;transition:all 0.2s;padding:5px 10px" id="lm-type-'+t+'" onclick="window._mpSelectLmType(\''+t+'\')">'+
                '<div class="mp-mini-label">'+t+'</div></div>';
        }).join('')+
        '</div></div>'+

        // Amount (hidden for chest4)
        '<div id="lm-amt-row" class="mb-3">'+
        '<label class="form-label" style="font-size:0.8rem;color:var(--text-secondary)">Amount to open</label>'+
        '<input type="number" class="form-control mp-input" id="lm-amount" min="1" max="10" value="1" style="max-width:100px">'+
        '</div>'+

        '<button class="mp-adopt-btn" onclick="window._mpOpenChest()">📦 Open Chest</button>'+
        '<div id="lm-result" class="mt-3"></div>'+
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

window._mpTab = function(tab) {
    ['train','mission','play','battle','quest','market','rename','kill'].forEach(function(t) {
        var btn = el('tab-'+t), panel = el('panel-'+t);
        if (btn)   btn.classList.toggle('active', t===tab);
        if (panel) panel.style.display = t===tab ? '' : 'none';
    });
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

window._mpTrain = async function() {
    var r = el('train-result');
    if (r) r.innerHTML = '<div class="mp-battle-card" style="font-size:0.8rem;color:var(--text-secondary)">Training...</div>';
    try {
        var res = await fetch('/api/pets/train', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({difficulty: _trainDiff})
        });
        var d = await res.json();
        if (res.ok) {
            showResult('train-result', d.success, d.outcome);
            if (d.pet) { _pet = d.pet; renderPetCard(d.pet); }
            if (d.level_up) showLevelChangePopup(d.level_up, false);
        } else {
            showResult('train-result', false, d.detail||'Failed');
        }
    } catch(e) { showResult('train-result', false, e.message); }
};

window._mpMission = async function() {
    var r = el('mission-result');
    if (r) r.innerHTML = '<div class="mp-battle-card" style="font-size:0.8rem;color:var(--text-secondary)">Launching mission...</div>';
    var gambleEl = el('mission-gamble');
    var gamble = gambleEl ? parseInt(gambleEl.value||'0',10)||0 : 0;
    try {
        var res = await fetch('/api/pets/mission', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({difficulty: _missionDiff, gamble_xp: gamble})
        });
        var d = await res.json();
        if (res.ok) {
            showResult('mission-result', d.success, d.outcome);
            if (d.pet) { _pet = d.pet; renderPetCard(d.pet); }
            if (d.level_up) showLevelChangePopup(d.level_up, false);
            else if (d.level_down) showLevelChangePopup(d.level_down, true);
        } else {
            showResult('mission-result', false, d.detail||'Failed');
        }
    } catch(e) { showResult('mission-result', false, e.message); }
};

window._mpPlay = async function() {
    if (!_playLoc) { showResult('play-result', false, 'Please select a location first.'); return; }
    var r = el('play-result');
    if (r) r.innerHTML = '<div class="mp-battle-card" style="font-size:0.8rem;color:var(--text-secondary)">Playing...</div>';
    try {
        var res = await fetch('/api/pets/play', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({location: _playLoc})
        });
        var d = await res.json();
        if (res.ok) {
            showResult('play-result', d.success, d.outcome);
            if (d.pet) { _pet = d.pet; renderPetCard(d.pet); }
            if (d.level_up) showLevelChangePopup(d.level_up, false);
        } else {
            showResult('play-result', false, d.detail||'Failed');
        }
    } catch(e) { showResult('play-result', false, e.message); }
};

// ── Battle state & handlers ───────────────────────────────────────────────────
var _battleDiff = 'easy';

window._mpSelectBattle = function(d) {
    _battleDiff = d;
    ['easy','average','hard'].forEach(function(x) {
        var e2 = el('battle-opt-'+x);
        if (e2) { e2.style.borderColor = x===d ? 'var(--gold-primary)' : 'rgba(255,215,0,0.15)'; e2.style.boxShadow = x===d ? '0 0 8px var(--gold-glow)' : ''; }
    });
};

window._mpBattle = async function() {
    var btn = el('battle-start-btn');
    var r   = el('battle-result');
    if (btn) btn.disabled = true;
    if (r) r.innerHTML = '<div class="mp-battle-card" style="font-size:0.8rem;color:var(--text-secondary)">⚔️ Battle in progress...</div>';
    try {
        var res = await fetch('/api/pets/battle/npc', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({difficulty: _battleDiff, action: 'attack'})
        });
        var d = await res.json();
        if (!res.ok) { showResult('battle-result', false, d.detail || 'Battle failed'); return; }

        // ── Build battle log UI ───────────────────────────────────────────
        var won = d.won;
        var enemy = d.enemy || {};
        var player = d.player || {};
        var turns = d.turns || [];

        var html = '<div class="mp-battle-card" style="border-color:'+(won?'rgba(39,174,96,0.5)':'rgba(231,76,60,0.5)')+'">';

        // Header
        html += '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">'+
            '<div style="font-size:1rem;font-weight:700;color:'+(won?'#2ecc71':'#e74c3c')+'">'+(won?'🏆 Victory!':'💀 Defeated')+' vs '+escHtml(enemy.name||'Enemy')+'</div>'+
            '<div style="font-size:0.72rem;color:var(--text-secondary)">'+turns.length+' turns</div>'+
            '</div>';

        // HP bars final state
        var lastTurn = turns[turns.length-1] || {};
        html += '<div class="row g-2 mb-3">'+
            '<div class="col-6">'+
            '<div style="font-size:0.72rem;color:var(--gold-secondary);margin-bottom:2px">'+escHtml(player.name||'Your Pet')+'</div>'+
            _buildBattleHpBar(lastTurn.player_hp||0, player.max_hp||1)+
            '</div>'+
            '<div class="col-6">'+
            '<div style="font-size:0.72rem;color:var(--text-secondary);margin-bottom:2px">'+escHtml(enemy.name||'Enemy')+'</div>'+
            _buildBattleHpBar(lastTurn.enemy_hp||0, enemy.max_hp||1, true)+
            '</div>'+
            '</div>';

        // Turn log (collapsible)
        html += '<details style="margin-bottom:8px"><summary style="cursor:pointer;font-size:0.78rem;color:var(--gold-secondary);user-select:none">📜 Battle Log ('+turns.length+' turns)</summary>'+
            '<div style="max-height:220px;overflow-y:auto;margin-top:6px">';
        turns.forEach(function(t) {
            var pPct = Math.round((t.player_hp / (t.player_max_hp||1)) * 100);
            var ePct = Math.round((t.enemy_hp  / (t.enemy_max_hp||1))  * 100);
            html += '<div style="border-left:2px solid rgba(255,215,0,0.2);padding:4px 8px;margin-bottom:4px;font-size:0.75rem">'+
                '<div style="color:var(--text-secondary);font-size:0.68rem;margin-bottom:2px">Turn '+t.turn+
                ' — '+escHtml(player.name||'You')+': <span style="color:'+(pPct>30?'#2ecc71':'#e74c3c')+'">'+t.player_hp+' HP</span>'+
                ' | '+escHtml(enemy.name||'Enemy')+': <span style="color:'+(ePct>30?'#e74c3c':'#e74c3c')+'">'+t.enemy_hp+' HP</span></div>';
            (t.lines||[]).forEach(function(line) { html += '<div>'+escHtml(line)+'</div>'; });
            html += '</div>';
        });
        html += '</div></details>';

        // XP and loot
        if (d.xp_gained) {
            html += '<div style="font-size:0.8rem;color:var(--gold-primary);margin-bottom:4px">📈 +'+(d.xp_gained)+' XP</div>';
        }
        if (d.messages && d.messages.length) {
            d.messages.forEach(function(m) {
                if (!m.includes('XP')) html += '<div style="font-size:0.75rem;color:var(--text-secondary)">'+cleanDiscordText(m)+'</div>';
            });
        }

        html += '</div>';
        if (r) r.innerHTML = html;

        if (d.pet) { _pet = d.pet; renderPetCard(d.pet); }
        if (d.level_change) showLevelChangePopup(d.level_change, d.level_change.new_level < d.level_change.old_level);

    } catch(e) { showResult('battle-result', false, e.message); }
    finally { if (btn) btn.disabled = false; }
};

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
        if (!res.ok) { showResult('quest-start-result', false, d.detail||'Failed to start quest'); return; }
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
        Object.keys(d.choices).forEach(function(k) {
            var btn = document.createElement('button');
            btn.className = 'mp-adopt-btn';
            btn.style.cssText = 'font-size:0.8rem;padding:8px 14px;text-align:left;width:100%';
            btn.textContent = k+'. '+d.choices[k];
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
        if (!res.ok) { showResult('quest-outcome', false, d.detail||'Error'); return; }
        if (d.done) {
            _renderQuestDone(d);
        } else {
            _renderQuestStage(d);
        }
    } catch(e) {
        var out = el('quest-outcome');
        if(out) out.innerHTML='<div class="mp-battle-card" style="border-color:rgba(231,76,60,0.4);color:#e74c3c;font-size:0.8rem">❌ '+escHtml(e.message)+'</div>';
        if(cho) cho.querySelectorAll('button').forEach(function(b){b.disabled=false;b.style.opacity='1';});
    }
};

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
    if(d.pet){ _pet=d.pet; renderPetCard(d.pet); }
}

window._mpQuestReset = function() {
    el('quest-setup').style.display = '';
    el('quest-active').style.display = 'none';
    el('quest-result').style.display = 'none';
    var out = el('quest-outcome'); if(out) out.innerHTML='';
    var xpt = el('quest-xp-track'); if(xpt) xpt.textContent='';
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
    if(r) r.innerHTML='<div class="mp-battle-card" style="font-size:0.8rem;color:var(--text-secondary)">Opening chest...</div>';
    try {
        var res = await fetch('/api/pets/loot/open', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({chest:_lmChest, amount:_lmAmt, selected_type:_lmType||null})
        });
        var d = await res.json();
        if(res.ok && d.success) {
            var html = '<div class="mp-battle-card" style="border-color:rgba(255,215,0,0.4)">'+
                '<div class="mp-section-title" style="color:var(--gold-primary)">📦 Chest Opened!</div>'+
                '<div class="d-flex flex-wrap gap-2 mt-2">';
            (d.items||[]).forEach(function(item){
                var f=item.emoji_file||(item.name+'.png');
                var rcClass='rc-'+(item.rarity||'Common').toLowerCase();
                html+='<div class="mp-inv-item">'+
                    '<img src="/static/Emojis/Pets/Equipment/'+f+'" style="width:28px;height:28px" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">'+
                    '<div><div class="fw-bold '+rcClass+'" style="font-size:0.78rem">'+item.name+'</div>'+
                    '<div style="font-size:0.65rem;color:var(--text-secondary)">'+(item.rarity||'Common')+'</div></div></div>';
            });
            html += '</div>';
            // Also show raw messages cleaned up
            if (d.messages && d.messages.length) {
                html += '<div style="font-size:0.75rem;color:var(--text-secondary);margin-top:8px">';
                d.messages.forEach(function(m){ html += '<div>'+cleanDiscordText(m)+'</div>'; });
                html += '</div>';
            }
            html += '</div>';
            if(r) r.innerHTML=html;
            if(d.pet){ _pet=d.pet; renderPetCard(d.pet); }
        } else {
            showResult('lm-result', false, d.detail||d.error||'Failed');
        }
    } catch(e){ showResult('lm-result',false,e.message); }
};

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
            setTimeout(function(){ init(); }, 1200);
        } else {
            if (result) result.innerHTML = '<div class="mp-battle-card" style="border-color:rgba(231,76,60,0.4);color:#e74c3c;font-size:0.82rem">❌ '+(d.detail||d.error||'Failed')+'</div>';
        }
    } catch(e) {
        if (result) result.innerHTML = '<div class="mp-battle-card" style="border-color:rgba(231,76,60,0.4);color:#e74c3c;font-size:0.82rem">❌ '+e.message+'</div>';
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
            setTimeout(function(){ init(); }, 1200);
        } else {
            if (result) result.innerHTML = '<div class="mp-battle-card" style="border-color:rgba(231,76,60,0.4);color:#e74c3c;font-size:0.82rem">❌ '+(d.detail||d.error||'Failed')+'</div>';
        }
    } catch(e) {
        if (result) result.innerHTML = '<div class="mp-battle-card" style="border-color:rgba(231,76,60,0.4);color:#e74c3c;font-size:0.82rem">❌ '+e.message+'</div>';
    }
};

function buildEquipped(pet) {
    var eq = pet.equipment||{};
    var slots = [
        {type:'Monsters',idx:0,label:'Monster 1'},{type:'Gems',idx:0,label:'Gem 1'},
        {type:'Material',idx:0,label:'Material 1'},{type:'Hat',label:'Hat'},
        {type:'Material',idx:1,label:'Material 2'},{type:'Gems',idx:1,label:'Gem 2'},
        {type:'Monsters',idx:1,label:'Monster 2'}
    ];
    var html = '<div class="mp-section-title">Equipped</div><div class="d-flex flex-wrap gap-1 mb-1" style="padding-bottom:18px">';
    slots.forEach(function(sl) {
        var item = sl.type==='Hat' ? (eq.Hat||null) : ((eq[sl.type]||[])[sl.idx]||null);
        var isEmpty = !item || !item.name;
        var f = isEmpty ? 'Basic.png' : (item.emoji_file||(item.name+'.png'));
        var src = isEmpty ? '/static/Emojis/Pets/Deco/Basic.png' : '/static/Emojis/Pets/Equipment/'+f;

        if (isEmpty) {
            html += '<div class="mp-equip-slot empty" title="'+sl.label+' (empty)">'+
                '<img src="'+src+'">'+
                '<span class="mp-slot-label">'+sl.label+'</span></div>';
        } else {
            var data = getEquipItem(item.name);
            var tip = item.name+' — '+bonusTooltip(data||item)+' (click to unequip)';
            var unequipSlot = sl.type === 'Material' ? 'Material' : sl.type;
            html += '<div class="mp-equip-slot mp-equip-filled" title="'+tip+'" '+
                'onclick="window._mpUnequipSlot(\''+unequipSlot+'\')" style="cursor:pointer"'+
                ' data-hover-item="'+escHtml(item.name)+'">'+
                '<img src="'+src+'" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">'+
                '<span class="mp-slot-label">'+item.name+'</span></div>';
        }
    });
    return html + '</div>';
}

function buildInventoryCollapsible(pet) {
    var inv = pet.inventory||[];
    var eq  = pet.equipment||{};

    // Build a set of equipped item names for glow + label
    var equippedNames = {};
    var mat = eq.Material;
    if (mat && mat.name) equippedNames[mat.name.toLowerCase()] = (equippedNames[mat.name.toLowerCase()]||0)+1;
    (Array.isArray(eq.Material) ? eq.Material : []).forEach(function(m){ if(m&&m.name) equippedNames[m.name.toLowerCase()]=(equippedNames[m.name.toLowerCase()]||0)+1; });
    if (eq.Hat && eq.Hat.name) equippedNames[eq.Hat.name.toLowerCase()] = (equippedNames[eq.Hat.name.toLowerCase()]||0)+1;
    (eq.Gems||[]).forEach(function(g){ if(g&&g.name) equippedNames[g.name.toLowerCase()]=(equippedNames[g.name.toLowerCase()]||0)+1; });
    (eq.Monsters||[]).forEach(function(m){ if(m&&m.name) equippedNames[m.name.toLowerCase()]=(equippedNames[m.name.toLowerCase()]||0)+1; });

    // Count how many of each equippable item the user has in inventory
    var invCounts = {};
    inv.forEach(function(item){
        if (['Hat','Material','Gem','Monster'].indexOf(item.type||'') !== -1) {
            var k = item.name.toLowerCase();
            invCounts[k] = (invCounts[k]||0) + (item.count||1);
        }
    });

    var uid = 'inv-collapse-'+Date.now();
    var header = '<div class="mp-section-title" style="cursor:pointer;user-select:none" onclick="var c=document.getElementById(\''+uid+'\');c.style.display=c.style.display===\'none\'?\'block\':\'none\'">'+
        '🎒 Inventory <span style="font-size:0.65rem;color:var(--text-secondary)">('+inv.length+' items — click to expand)</span>'+
        '</div>';
    if (!inv.length) return header+'<div id="'+uid+'" style="display:none"><div class="mp-empty-state" style="padding:8px">Inventory is empty.</div></div>';

    var grouped = {};
    inv.forEach(function(item){ var t=item.type||'Other'; if(!grouped[t])grouped[t]=[]; grouped[t].push(item); });

    var content = '<div id="'+uid+'" style="display:none">';
    ['Hat','Potion','Material','Gem','Monster','Key','Chest','Other'].forEach(function(t) {
        if (!grouped[t]) return;
        content += '<div style="font-size:0.68rem;color:var(--gold-secondary);font-weight:700;margin:5px 0 3px">'+t+'s</div>';
        content += '<div class="d-flex flex-wrap gap-1 mb-1">';
        grouped[t].forEach(function(item) {
            var f = item.emoji_file||(item.name+'.png');
            var rcClass = 'rc-'+(item.rarity||'Common').toLowerCase();
            var isEquippable = ['Hat','Material','Gem','Monster'].indexOf(t) !== -1;
            var isPotion     = t === 'Potion';
            var clickable    = isEquippable || isPotion;

            var eqCount  = equippedNames[item.name.toLowerCase()]||0;
            var invCount = item.count||1;
            var isEquipped = eqCount > 0;

            // Determine action label and equip count to send
            var action = isPotion ? 'Use' : (isEquipped ? 'Equipped' : 'Equip');
            // For equippable multi-slot types: if user has ≥2 in inventory and 0 equipped, equip both
            var equipCount = 1;
            if (!isPotion && isEquippable && t !== 'Hat' && invCount >= 2 && eqCount === 0) {
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

            var onclick = clickable ? ' onclick="window._mpInvClick(\''+escHtml(item.name)+'\',\''+t+'\',\''+action+'\','+equipCount+')"' : '';

            var glowStyle = isEquipped ? 'box-shadow:0 0 8px var(--gold-glow);border-color:var(--gold-primary);' : '';
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

function buildBattleRecordCard(pet) {
    var bs = pet.battle_stats||{};
    var types = [{key:'pvp',name:'PvP'},{key:'npc',name:'NPC'},{key:'wild_encounter',name:'Wild'},{key:'boss',name:'Boss'}];
    var html = '<hr class="mp-divider my-2"><div class="mp-section-title">Battle Records</div>'+
        '<div class="d-flex gap-2 flex-wrap">';
    types.forEach(function(bt) {
        var s = bs[bt.key]||{wins:0,losses:0};
        var wr = (s.wins+s.losses)>0 ? ((s.wins/(s.wins+s.losses))*100).toFixed(0) : 0;
        html += '<div class="mp-mini-stat-card">'+
            '<div class="mp-mini-label">'+bt.name+'</div>'+
            '<div><span class="text-success" style="font-size:0.78rem;font-weight:700">'+s.wins+'W</span>'+
            '<span style="color:var(--text-secondary);font-size:0.7rem"> / </span>'+
            '<span class="text-danger" style="font-size:0.78rem;font-weight:700">'+s.losses+'L</span></div>'+
            '<div style="font-size:0.62rem;color:var(--text-secondary)">'+wr+'% WR</div>'+
            '</div>';
    });
    return html + '</div>';
}

function buildCasinoCard(pet) {
    var gs = pet.gambling_stats||{};
    var games = [
        {key:'slots',name:'Slots'},{key:'blackjack',name:'BJ'},
        {key:'holdem',name:"Hold'em"},{key:'craps',name:'Craps'},{key:'races',name:'Races'}
    ];
    var html = '<hr class="mp-divider my-2"><div class="mp-section-title">Casino</div>'+
        '<div class="d-flex gap-2 flex-wrap">';
    games.forEach(function(g) {
        var s = gs[g.key]||{};
        var played = s.total_played||s.games_played||s.races_played||s.rounds_played||0;
        var wins   = s.wins||s.games_won||s.races_won||s.rounds_won||0;
        var won    = s.total_won||s.xp_won_total||0;
        var lost   = s.total_lost||s.xp_lost_total||0;
        var net    = won-lost;
        var wr     = played>0 ? ((wins/played)*100).toFixed(0) : 0;
        html += '<div class="mp-mini-stat-card">'+
            '<div class="mp-mini-label">'+g.name+'</div>'+
            '<div style="font-size:0.72rem;color:var(--text-secondary)">'+played+' played</div>'+
            '<div style="font-size:0.7rem">'+wr+'% WR</div>'+
            '<div style="font-size:0.68rem" class="'+(net>=0?'text-success':'text-danger')+'">'+(net>=0?'+':'')+net.toLocaleString()+' XP</div>'+
            '</div>';
    });
    return html + '</div>';


    var base = {ATT:pet.ATT||0,DEF:pet.DEF||0,INT:pet.INT||0,DEX:pet.DEX||0,HAP:pet.HAP||0,ENE:pet.ENE||0};
    var cs = pet.computed_stats||{}, bs = pet.battle_stats||{};
    var specs = pet.specializations||pet.Spec||[];

    // Use computed_stats from server if present, otherwise calculate using exact same formulas as pet_brain.py
    // attack  = ATT + DEX
    // defense = DEF + INT
    // max_health = ((ATT+DEF+INT+DEX+HAP+ENE)/6 + HAP*ENE) * 10
    var att = cs.ATT !== undefined ? cs.ATT : base.ATT;
    var def = cs.DEF !== undefined ? cs.DEF : base.DEF;
    var int_ = cs.INT !== undefined ? cs.INT : base.INT;
    var dex = cs.DEX !== undefined ? cs.DEX : base.DEX;
    var hap = cs.HAP !== undefined ? cs.HAP : base.HAP;
    var ene = cs.ENE !== undefined ? cs.ENE : base.ENE;

    var attack  = cs.attack  !== undefined ? cs.attack  : (att + dex);
    var defense = cs.defense !== undefined ? cs.defense : (def + int_);
    var totalStats = att + def + int_ + dex + hap + ene;
    var maxHp = cs.max_health !== undefined ? cs.max_health : Math.floor(((totalStats / 6) + (hap * ene)) * 10);
    var html = '<div class="mp-section-title">Stats Breakdown</div><div class="row g-2 mb-2">';
    html += '<div class="col-md-4"><div class="mp-battle-card"><div style="font-size:0.7rem;color:var(--gold-secondary);font-weight:700;margin-bottom:6px">Base Stats</div>';
    html += '<div class="row g-1">';
    Object.keys(base).forEach(function(k) {
        var isSp = specs.indexOf(k) !== -1;
        html += '<div class="col-6"><div class="mp-stat-row"><img src="/static/Emojis/Pets/Deco/'+k+'.png" onerror="this.style.display=\'none\'">'+
            '<span class="'+(isSp?'stat-special':'')+'" style="font-size:0.85rem">'+k+': '+base[k]+'</span></div></div>';
    });
    html += '</div></div></div>';
    html += '<div class="col-md-4"><div class="mp-battle-card"><div style="font-size:0.7rem;color:var(--gold-secondary);font-weight:700;margin-bottom:6px">Combat</div>'+
        '<div style="font-size:0.75rem;margin-bottom:4px">⚔️ Attack: <strong>'+attack+'</strong> <span style="font-size:0.65rem;color:var(--text-secondary)">(ATT+DEX)</span></div>'+
        '<div style="font-size:0.75rem;margin-bottom:4px">🛡️ Defense: <strong>'+defense+'</strong> <span style="font-size:0.65rem;color:var(--text-secondary)">(DEF+INT)</span></div>'+
        '<div style="font-size:0.75rem">❤️ Max HP: <strong>'+maxHp.toLocaleString()+'</strong> <span style="font-size:0.65rem;color:var(--text-secondary)">(avg+HAP×ENE)×10</span></div>'+
        '</div></div>';
    html += '<div class="col-md-4"><div class="mp-battle-card"><div style="font-size:0.7rem;color:var(--gold-secondary);font-weight:700;margin-bottom:6px">Battle Records</div>';
    [{key:'pvp',name:'PvP'},{key:'npc',name:'NPC'},{key:'wild_encounter',name:'Wild'},{key:'boss',name:'Boss'}].forEach(function(bt) {
        var s = bs[bt.key]||{wins:0,losses:0};
        var wr = (s.wins+s.losses)>0 ? ((s.wins/(s.wins+s.losses))*100).toFixed(0) : 0;
        html += '<div style="font-size:0.72rem;margin-bottom:2px"><span style="color:var(--text-secondary)">'+bt.name+':</span> '+
            '<span class="text-success">'+s.wins+'W</span>/<span class="text-danger">'+s.losses+'L</span> '+
            '<span style="color:var(--text-secondary)">('+wr+'%)</span></div>';
    });
    html += '</div></div></div>';
    var xpE = Object.entries(pet).filter(function(kv){ return kv[0].endsWith('_xp_earned') && kv[1]!==0; });
    if (xpE.length) {
        html += '<div style="font-size:0.7rem;color:var(--gold-secondary);font-weight:700;margin-bottom:4px">XP Sources</div><div class="d-flex flex-wrap gap-2">';
        xpE.sort(function(a,b){return b[1]-a[1];}).forEach(function(kv) {
            var v = kv[1];
            html += '<div class="mp-battle-card" style="font-size:0.7rem">'+
                '<div>'+kv[0].replace('_xp_earned','').replace(/_/g,' ').toUpperCase()+'</div>'+
                '<div class="'+(v>=0?'text-success':'text-danger')+' fw-bold">'+(v>=0?'+':'')+v.toLocaleString()+' XP</div></div>';
        });
        html += '</div>';
    }
    return html;
}

function buildCasino(pet) {
    var gs = pet.gambling_stats||{};
    var games = [
        {key:'slots',name:'Slots'},{key:'blackjack',name:'Blackjack'},
        {key:'holdem',name:"Hold'em"},{key:'craps',name:'Craps'},{key:'races',name:'Races'}
    ];
    var html = '<div class="mp-section-title">Casino Stats</div><div class="row g-2">';
    games.forEach(function(g) {
        var s = gs[g.key]||{};
        var played = s.total_played||s.games_played||s.races_played||s.rounds_played||0;
        var wins   = s.wins||s.games_won||s.races_won||s.rounds_won||0;
        var losses = s.losses||s.games_lost||s.races_lost||s.rounds_lost||0;
        var won    = s.total_won||s.xp_won_total||0;
        var lost   = s.total_lost||s.xp_lost_total||0;
        var net    = won-lost;
        var wr     = played>0 ? ((wins/played)*100).toFixed(1) : 0;
        html += '<div class="col-md-4 col-sm-6"><div class="mp-casino-card">'+
            '<div style="font-size:0.72rem;color:var(--gold-secondary);font-weight:700;margin-bottom:4px">'+g.name+'</div>'+
            '<div class="d-flex justify-content-between" style="font-size:0.7rem">'+
            '<span class="text-muted">'+played+' played</span>'+
            '<span><span class="text-success">'+wins+'W</span>/<span class="text-danger">'+losses+'L</span></span>'+
            '</div>'+
            '<div class="mp-xp-bar-wrap mt-1 mb-1" style="height:5px"><div class="mp-xp-bar" style="width:'+wr+'%"></div></div>'+
            '<div class="d-flex justify-content-between" style="font-size:0.68rem;color:var(--text-secondary)">'+
            '<span>'+wr+'% WR</span>'+
            '<span class="'+(net>=0?'text-success':'text-danger')+'">'+(net>=0?'+':'')+net.toLocaleString()+' XP</span>'+
            '</div></div></div>';
    });
    return html + '</div>';
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
window._mpInvClick = function(name, type, action, equipCount) {
    var old = document.getElementById('inv-confirm-modal');
    if (old) old.remove();

    var isPotion = action === 'Use';
    var count    = equipCount || 1;

    var imgSrc = EMOJI_PATH_MAP[name.toLowerCase()]
        || '/static/Emojis/Pets/Equipment/' + name + '.png';

    // Build bonus description for confirm dialog
    var data = getEquipItem(name);
    var bonusLine = '';
    if (!isPotion && data && data.bonuses) {
        var bParts = Object.keys(data.bonuses).map(function(k){ return k+': +'+data.bonuses[k]; });
        if (bParts.length) bonusLine = '<div style="font-size:0.72rem;color:#4caf50;margin-top:4px">'+bParts.join(' | ')+(count===2?' (×2 equipped)':'')+'</div>';
    }

    var div = document.createElement('div');
    div.innerHTML =
        '<div class="modal fade" id="inv-confirm-modal" tabindex="-1">'+
        '<div class="modal-dialog modal-sm">'+
        '<div class="modal-content" style="background:var(--bg-secondary);border:1px solid var(--gold-primary)">'+
        '<div class="modal-header" style="border-bottom:1px solid rgba(255,215,0,0.2)">'+
        '<h6 class="modal-title" style="color:var(--gold-primary);font-family:Orbitron,sans-serif;font-size:0.85rem">'+
        (isPotion ? '🧪 Use Potion' : '⚔️ '+action)+'</h6>'+
        '<button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>'+
        '</div>'+
        '<div class="modal-body text-center">'+
        '<img src="'+imgSrc+'" style="width:56px;height:56px;object-fit:contain;margin-bottom:8px;filter:drop-shadow(0 0 8px var(--gold-glow))" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'"><br>'+
        '<div style="font-size:0.9rem;color:var(--gold-primary);font-weight:700;font-family:Orbitron,sans-serif">'+escHtml(name)+'</div>'+
        bonusLine+
        '<div style="font-size:0.75rem;color:var(--text-secondary);margin-top:6px">'+
        (isPotion ? 'Use this potion on your pet? This cannot be undone.' :
         count===2 ? 'Equip both '+escHtml(name)+' to your pet (fills both slots)?' :
         'Equip this '+type.toLowerCase()+' to your pet?')+
        '</div>'+
        '</div>'+
        '<div class="modal-footer" style="border-top:1px solid rgba(255,215,0,0.2);justify-content:center;gap:8px">'+
        '<button class="btn btn-secondary btn-sm" data-bs-dismiss="modal">Cancel</button>'+
        '<button class="btn btn-primary btn-sm" id="inv-confirm-btn">'+action+'</button>'+
        '</div>'+
        '</div></div></div>';
    document.body.appendChild(div.firstChild);

    var modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('inv-confirm-modal'));
    modal.show();

    document.getElementById('inv-confirm-btn').onclick = function() {
        modal.hide();
        if (isPotion) {
            _mpUsePotion(name);
        } else if (count === 2) {
            // Equip first, then equip second
            _mpEquipItem(name, type, function() { _mpEquipItem(name, type); });
        } else {
            _mpEquipItem(name, type);
        }
    };
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
            _pet = d.pet;
            if (callback) {
                // Chain second equip, then refresh
                callback();
            } else {
                renderPetCard(d.pet);
                renderAllPanels(d.pet);
                _showToast('✅ '+escHtml(name)+' equipped!', true);
            }
        } else {
            _showToast('❌ '+cleanDiscordText(d.detail||d.message||'Equip failed'), false);
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
            _pet = d.pet;
            renderPetCard(d.pet);
            renderAllPanels(d.pet);
            _showToast('📦 '+cleanDiscordText(d.message||'Unequipped'), true);
        } else {
            _showToast('❌ '+cleanDiscordText(d.detail||d.message||'Unequip failed'), false);
        }
    })
    .catch(function(e){ _showToast('❌ '+e.message, false); });
};function _mpUsePotion(name) {
    // Show potion animation overlay
    _showPotionAnimation(name, function() {
        fetch('/api/pets/use-potion', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({name: name})
        })
        .then(function(r){ return r.json(); })
        .then(function(d) {
            if (d.success && d.pet) {
                _pet = d.pet;
                renderPetCard(d.pet);
                renderAllPanels(d.pet);
                _showToast('🧪 '+escHtml(name)+' used! '+cleanDiscordText(d.message||''), true);
            } else {
                _showToast('❌ '+(d.detail||d.message||'Potion failed'), false);
            }
        })
        .catch(function(e){ _showToast('❌ '+e.message, false); });
    });
}

function _showPotionAnimation(name, callback) {
    var imgSrc = EMOJI_PATH_MAP[name.toLowerCase()]
        || '/static/Emojis/Pets/Equipment/' + name + '.png';
    var overlay = document.createElement('div');
    overlay.id = 'potion-anim-overlay';
    overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:9999;display:flex;align-items:center;justify-content:center;pointer-events:none;';
    overlay.innerHTML =
        '<div id="potion-anim-inner" style="text-align:center;animation:potionPop 1.8s ease forwards">'+
        '<img src="'+imgSrc+'" style="width:80px;height:80px;object-fit:contain;filter:drop-shadow(0 0 20px #9c27b0)" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">'+
        '<div style="font-size:1.2rem;color:#ce93d8;font-family:Orbitron,sans-serif;margin-top:8px;text-shadow:0 0 12px #9c27b0">✨ '+escHtml(name)+'</div>'+
        '<div style="font-size:0.85rem;color:#e1bee7;margin-top:4px">Applying effects...</div>'+
        '</div>';
    document.body.appendChild(overlay);

    // Inject keyframes if not already present
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


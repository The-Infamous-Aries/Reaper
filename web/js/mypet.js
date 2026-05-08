(function () {
'use strict';

var ELEM_IMG_BASE = '/static/Emojis/Pets/Deco/';

// Fo// Format large numbers: 3000→3k, 4530→4.53k, 1500000→1.5m, etc.
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

// Client-side equipment bonus calculation (mirrors pet_brain.py _calculate_equipment_bonuses)
function calcEquipBonuses(pet) {
    var eq     = pet.equipment || {};
    var level  = parseInt(pet.level || 1, 10);
    var specs  = (pet.specializations || pet.Spec || []).map(function(s){ return s.toUpperCase(); });
    var levelBonus = Math.floor(level / 50); // +1 per 50 levels
    var bonuses = {ATT:0, DEF:0, INT:0, DEX:0, HAP:0, ENE:0};

    // ── Collect typed items ───────────────────────────────────────────────────
    var items = []; // [{t, item}]
    var mat = eq.Material;
    if (mat && typeof mat === 'object' && !Array.isArray(mat) && mat.name) items.push({t:'Material', item:mat});
    (Array.isArray(eq.Material) ? eq.Material : []).forEach(function(m){ if(m&&m.name) items.push({t:'Material', item:m}); });
    (eq.Gems||[]).forEach(function(g){ if(g&&g.name) items.push({t:'Gem', item:g}); });
    (eq.Monsters||[]).forEach(function(m){ if(m&&m.name) items.push({t:'Monster', item:m}); });
    var hat = eq.Hat;
    // Hat may be stored as a list (from backend) or a plain dict (legacy)
    if (Array.isArray(hat)) hat = hat[0] || null;
    var hatEquipped = hat && typeof hat === 'object' && hat.name;
    if (hatEquipped) items.push({t:'Hat', item:hat});

    // ── Count duplicates ──────────────────────────────────────────────────────
    var matCounts = {}, gemCounts = {}, monCounts = {};
    items.forEach(function(e2) {
        var n = (e2.item.name||'').toLowerCase();
        if (e2.t === 'Material') matCounts[n] = (matCounts[n]||0) + 1;
        else if (e2.t === 'Gem')     gemCounts[n] = (gemCounts[n]||0) + 1;
        else if (e2.t === 'Monster') monCounts[n] = (monCounts[n]||0) + 1;
    });

    var hasMatPair = Object.values(matCounts).some(function(c){ return c >= 2; });
    var hasGemPair = Object.values(gemCounts).some(function(c){ return c >= 2; });
    var hasMonPair = Object.values(monCounts).some(function(c){ return c >= 2; });

    // ── Hat spec matching ─────────────────────────────────────────────────────
    var hatSpecMatches = 0;
    if (hatEquipped && specs.length) {
        var hatData = getEquipItem(hat.name);
        var hatBonuses = (hatData && hatData.bonuses) ? hatData.bonuses : (hat.bonuses || {});
        Object.keys(hatBonuses).forEach(function(s){
            if (specs.indexOf(s.toUpperCase()) !== -1) hatSpecMatches++;
        });
    }

    // ── Determine global set multiplier ──────────────────────────────────────
    var fullSet = hasMatPair && hasGemPair && hasMonPair && hatEquipped;
    var setMult;
    if (fullSet) {
        setMult = hatSpecMatches >= 2 ? 4 : 3;
    } else if (hasMatPair || hasGemPair || hasMonPair) {
        setMult = 2;
    } else {
        setMult = 1;
    }
    var finalMult = setMult + levelBonus;

    // ── Sum raw bonuses first, then apply global multiplier ───────────────────
    var rawBonuses = {ATT:0, DEF:0, INT:0, DEX:0, HAP:0, ENE:0};
    items.forEach(function(e2) {
        var data = getEquipItem(e2.item.name);
        var b = (data && data.bonuses) ? data.bonuses : (e2.item.bonuses || {});
        Object.keys(b).forEach(function(stat){
            if (rawBonuses[stat] !== undefined) rawBonuses[stat] += parseInt(b[stat]||0, 10);
        });
    });
    Object.keys(rawBonuses).forEach(function(stat){
        bonuses[stat] = rawBonuses[stat] * finalMult;
    });

    return bonuses;
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
            '<img src="'+petImg(sp)+'" class="mp-pet-img" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">'+
            '<div style="flex:1;min-width:0">'+
            '<div class="fw-bold" style="font-family:Orbitron,sans-serif;color:var(--gold-primary);font-size:0.95rem;text-shadow:0 0 8px var(--gold-glow)">'+(pet.name||sp)+'</div>'+
            '<div class="d-flex align-items-center gap-1 mt-1 flex-wrap">'+
            '<span class="badge bg-warning text-dark" style="font-size:0.6rem">Lv.'+(pet.level||1)+'</span>'+
            '<img src="'+catImg(cat)+'" style="width:18px;height:18px;object-fit:contain" title="'+cap(cat)+'" onerror="this.style.display=\'none\'">'+
            '<span class="mp-type-chip" data-type="'+cat+'" style="font-size:0.75rem;color:var(--text-secondary);cursor:pointer">'+cap(cat)+'</span>'+
            '<span style="color:rgba(255,215,0,0.4);margin:0 2px">|</span>'+
            '<img src="'+elemImgPath(e1)+'" style="width:18px;height:18px;object-fit:contain" title="'+cap(e1)+'" onerror="this.style.display=\'none\'">'+
            '<span class="mp-elem-chip" data-elem="'+e1+'" style="font-size:0.75rem;color:var(--gold-secondary);cursor:pointer">'+cap(e1)+'</span>'+
            (e2 ? '<span style="color:rgba(255,215,0,0.4);margin:0 2px">/</span><img src="'+elemImgPath(e2)+'" style="width:18px;height:18px;object-fit:contain" title="'+cap(e2)+'" onerror="this.style.display=\'none\'"><span class="mp-elem-chip" data-elem="'+e2+'" style="font-size:0.75rem;color:var(--gold-secondary);cursor:pointer">'+cap(e2)+'</span>' : '')+
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

        var bonusStr = bonus > 0 ? ' <span style="font-size:0.65rem;color:#4caf50">(+' + bonus + ')</span>' : '';
        statsHtml += '<div class="col-6"><div class="mp-stat-row mp-stat-hoverable" data-stat="'+s+'" style="cursor:pointer">' +
            '<img src="/static/Emojis/Pets/Deco/' + s + '.png" onerror="this.style.display=\'none\'">' +
            '<span class="' + (isSp ? 'stat-special' : '') + '">' + s + ': ' + total + '</span>' + bonusStr +
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
    if (body) body.innerHTML = xpHtml + buildEquipped(pet) + buildEquipBonus(pet) + '<hr class="mp-divider my-2">' + statsHtml + combatHtml + buildInventoryCollapsible(pet) + buildTokenStatsCard(pet) + buildFriendFoeCard() + buildBreakdownCard(pet);
    bindStatTooltips(pet);
}

// ── Stat / Type / Element hover tooltip system ────────────────────────────────

var _mpTip = null;
var _mpTipTimer = null;

function _mpGetTip() {
    if (!_mpTip) {
        _mpTip = document.createElement('div');
        _mpTip.id = 'mp-hover-tip';
        _mpTip.className = 'mp-hover-tip';
        document.body.appendChild(_mpTip);
        _mpTip.addEventListener('mouseenter', function() { clearTimeout(_mpTipTimer); });
        _mpTip.addEventListener('mouseleave', _mpHideTip);
    }
    return _mpTip;
}

function _mpHideTip() {
    _mpTipTimer = setTimeout(function() {
        var t = document.getElementById('mp-hover-tip');
        if (t) { t.classList.remove('mp-hover-tip--visible'); }
    }, 120);
}

function _mpShowTip(anchor, html) {
    clearTimeout(_mpTipTimer);
    var tip = _mpGetTip();
    tip.innerHTML = html;
    tip.classList.remove('mp-hover-tip--visible');
    // Position
    var rect = anchor.getBoundingClientRect();
    var scrollY = window.scrollY || document.documentElement.scrollTop;
    var scrollX = window.scrollX || document.documentElement.scrollLeft;
    tip.style.left = '0px'; tip.style.top = '0px';
    document.body.appendChild(tip);
    var tw = tip.offsetWidth;
    var th = tip.offsetHeight;
    var left = rect.left + scrollX + rect.width / 2 - tw / 2;
    var top  = rect.top  + scrollY - th - 10;
    // Clamp to viewport
    left = Math.max(8, Math.min(left, window.innerWidth - tw - 8));
    if (top < scrollY + 8) top = rect.bottom + scrollY + 10;
    tip.style.left = left + 'px';
    tip.style.top  = top  + 'px';
    tip.classList.add('mp-hover-tip--visible');
}

function _mpBuildStatTip(pet, stat) {
    var masteryRaw = pet.stat_mastery && pet.stat_mastery[stat];
    var masteryPts = masteryRaw && typeof masteryRaw === 'object' ? (masteryRaw.points || 0) : (masteryRaw || 0);
    var masteryMult = masteryPts > 0 ? (1.0 + masteryPts * 0.1).toFixed(1) : null;

    var abilities = [];
    if (pet.abilities) {
        var prefix = stat.toLowerCase() + '_';
        Object.keys(pet.abilities).forEach(function(id) {
            var lvl = pet.abilities[id];
            if (id.indexOf(prefix) === 0 && lvl > 0) {
                // Pretty-print the id: "att_npc_damage" → "Npc Damage"
                var label = id.slice(prefix.length).replace(/_/g, ' ').replace(/\b\w/g, function(c){ return c.toUpperCase(); });
                abilities.push({ label: label, level: lvl });
            }
        });
    }

    var rows = '';

    // Mastery row
    rows += '<div class="mp-tip-row">' +
        '<span class="mp-tip-label">Stat Mastery</span>' +
        '<span class="mp-tip-val' + (masteryPts > 0 ? ' mp-tip-val--gold' : ' mp-tip-val--dim') + '">' +
        (masteryPts > 0 ? masteryPts + ' pt' + (masteryPts !== 1 ? 's' : '') + ' &nbsp;→&nbsp; <strong>' + masteryMult + 'x</strong>' : 'None') +
        '</span></div>';

    // Abilities
    rows += '<div class="mp-tip-divider"></div>';
    rows += '<div class="mp-tip-label mp-tip-section-head">Abilities</div>';
    if (abilities.length === 0) {
        rows += '<div class="mp-tip-row"><span class="mp-tip-val--dim" style="font-size:0.7rem">None unlocked</span></div>';
    } else {
        abilities.forEach(function(ab) {
            rows += '<div class="mp-tip-row">' +
                '<span class="mp-tip-label">' + ab.label + '</span>' +
                '<span class="mp-tip-val mp-tip-val--gold">Lv.' + ab.level + '</span>' +
                '</div>';
        });
    }

    return '<div class="mp-tip-header">' +
        '<img src="/static/Emojis/Pets/Deco/' + stat + '.png" class="mp-tip-icon" onerror="this.style.display=\'none\'">' +
        '<span>' + stat + ' Mastery</span>' +
        '</div>' +
        '<div class="mp-tip-body">' + rows + '</div>';
}

function _mpBuildTypeTip(pet, typeKey) {
    var info = TYPE_INFO[typeKey] || { label: cap(typeKey), desc: '' };
    var advMastery = pet.advantage_mastery || {};
    var typePts = parseInt(advMastery['type'] || 0, 10);
    var typeBonus = typePts > 0 ? (typePts * 0.1).toFixed(1) : null;

    var rows = '<div class="mp-tip-row">' +
        '<span class="mp-tip-label">Matchup</span>' +
        '<span class="mp-tip-val" style="font-size:0.7rem;color:var(--text-secondary)">' + info.desc + '</span>' +
        '</div>';

    rows += '<div class="mp-tip-divider"></div>';
    rows += '<div class="mp-tip-row">' +
        '<span class="mp-tip-label">Type Adv. Mastery</span>' +
        '<span class="mp-tip-val' + (typePts > 0 ? ' mp-tip-val--gold' : ' mp-tip-val--dim') + '">' +
        (typePts > 0 ? typePts + ' pt' + (typePts !== 1 ? 's' : '') + ' &nbsp;→&nbsp; <strong>+' + typeBonus + '</strong> bonus' : 'None') +
        '</span></div>';

    return '<div class="mp-tip-header">' +
        '<img src="' + catImg(typeKey) + '" class="mp-tip-icon" onerror="this.style.display=\'none\'">' +
        '<span>' + info.label + ' Type</span>' +
        '</div>' +
        '<div class="mp-tip-body">' + rows + '</div>';
}

function _mpBuildElemTip(pet, elemKey) {
    var info = ELEM_INFO[elemKey] || { label: cap(elemKey), strong: [], weak: [], desc: '' };
    var advMastery = pet.advantage_mastery || {};
    var elemPts = parseInt(advMastery['element'] || 0, 10);
    var elemBonus = elemPts > 0 ? (elemPts * 0.1).toFixed(1) : null;

    var strongStr = info.strong && info.strong.length ? info.strong.join(', ') : '—';
    var weakStr   = info.weak   && info.weak.length   ? info.weak.join(', ')   : '—';

    var rows = '<div class="mp-tip-row">' +
        '<span class="mp-tip-label" style="color:#4caf50">Strong vs</span>' +
        '<span class="mp-tip-val" style="color:#4caf50">' + strongStr + '</span>' +
        '</div>' +
        '<div class="mp-tip-row">' +
        '<span class="mp-tip-label" style="color:#e74c3c">Weak to</span>' +
        '<span class="mp-tip-val" style="color:#e74c3c">' + weakStr + '</span>' +
        '</div>';

    rows += '<div class="mp-tip-divider"></div>';
    rows += '<div class="mp-tip-row">' +
        '<span class="mp-tip-label">Elem Adv. Mastery</span>' +
        '<span class="mp-tip-val' + (elemPts > 0 ? ' mp-tip-val--gold' : ' mp-tip-val--dim') + '">' +
        (elemPts > 0 ? elemPts + ' pt' + (elemPts !== 1 ? 's' : '') + ' &nbsp;→&nbsp; <strong>+' + elemBonus + '</strong> bonus' : 'None') +
        '</span></div>';

    return '<div class="mp-tip-header">' +
        '<img src="' + elemImgPath(elemKey) + '" class="mp-tip-icon" onerror="this.style.display=\'none\'">' +
        '<span>' + info.label + ' Element</span>' +
        '</div>' +
        '<div class="mp-tip-body">' + rows + '</div>';
}

function bindStatTooltips(pet) {
    // Stat rows
    var rows = document.querySelectorAll('.mp-stat-hoverable[data-stat]');
    rows.forEach(function(row) {
        var stat = row.getAttribute('data-stat');
        row.addEventListener('mouseenter', function() {
            clearTimeout(_mpTipTimer);
            _mpShowTip(row, _mpBuildStatTip(pet, stat));
        });
        row.addEventListener('mouseleave', _mpHideTip);
    });

    // Type chips
    var typeChips = document.querySelectorAll('.mp-type-chip[data-type]');
    typeChips.forEach(function(chip) {
        var typeKey = chip.getAttribute('data-type');
        chip.addEventListener('mouseenter', function() {
            clearTimeout(_mpTipTimer);
            _mpShowTip(chip, _mpBuildTypeTip(pet, typeKey));
        });
        chip.addEventListener('mouseleave', _mpHideTip);
    });

    // Element chips
    var elemChips = document.querySelectorAll('.mp-elem-chip[data-elem]');
    elemChips.forEach(function(chip) {
        var elemKey = chip.getAttribute('data-elem');
        chip.addEventListener('mouseenter', function() {
            clearTimeout(_mpTipTimer);
            _mpShowTip(chip, _mpBuildElemTip(pet, elemKey));
        });
        chip.addEventListener('mouseleave', _mpHideTip);
    });
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
    var LOC_SPECIALS = {
        Camp:              ['Plant','Fighting'],
        Bonfire:           ['Fire','Necro'],
        Beach:             ['Water','Holy'],
        Forest:            ['Plant','Rock'],
        'Hot Air Balloon': ['Air','Fire'],
        Cruiseship:        ['Water','Electric'],
        Mountain:          ['Rock','Ice'],
        Gym:               ['Fighting','Psychic'],
        Graveyard:         ['Holy','Necro'],
        Festival:          ['Magic','Psychic'],
        Glacier:           ['Ice','Air'],
        Pyramids:          ['Magic','Electric']
    };

    // Normalise pet elements for comparison
    var petElem1 = (pet.element  || '').toLowerCase();
    var petElem2 = (pet.element2 || '').toLowerCase();

    function _locMatchCount(loc) {
        var specials = LOC_SPECIALS[loc] || [];
        var count = 0;
        specials.forEach(function(s) {
            var sl = s.toLowerCase();
            if (sl === petElem1 || (petElem2 && sl === petElem2)) count++;
        });
        return count;
    }

    var tabs = [
        {id:'train',  label:'🏋️ Train'},
        {id:'mission',label:'🗺️ Mission'},
        {id:'play',   label:'🎮 Play'},
        {id:'quest',  label:'🗡️ Quest'},
        {id:'market', label:'📦 Loot Market'},
        {id:'absorb', label:'⚡ Absorb'},
        {id:'abilities', label:'💎 Abilities'},
        {id:'battle', label:'⚔️ Battle Settings'},
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
        'Pick a stat to train and a difficulty. Success raises the stat; failure lowers it. '+
        'The change is <strong>difficulty multiplier × equipment multiplier</strong>. No XP is gained or lost.'+
        '</div>'+

        // Stat picker
        '<div class="mp-mini-label mb-1">Choose Stat</div>'+
        '<div class="d-flex gap-2 flex-wrap mb-3">'+
        ['ATT','DEF','INT','DEX','HAP','ENE'].map(function(s) {
            return '<div class="mp-mini-stat-card" style="cursor:pointer;transition:all 0.2s;min-width:70px;text-align:center" '+
                'id="train-stat-'+s+'" onclick="window._mpSelectTrainStat(\''+s+'\')">'+
                '<img src="/static/Emojis/Pets/Deco/'+s+'.png" style="width:28px;height:28px;object-fit:contain;margin-bottom:3px" onerror="this.style.display=\'none\'">'+
                '<div class="mp-mini-label">'+s+'</div>'+
                '</div>';
        }).join('')+
        '</div>'+

        // Difficulty picker
        '<div class="mp-mini-label mb-1">Choose Difficulty</div>'+
        '<div class="row g-2 mb-3">'+
        ['Easy','Average','Hard'].map(function(d) {
            var mult  = {Easy:'1×',Average:'3×',Hard:'5×'}[d];
            var chance = {Easy:'75%',Average:'60%',Hard:'45%'}[d];
            return '<div class="col-md-4"><div class="mp-mini-stat-card" style="cursor:pointer;transition:all 0.2s" id="train-opt-'+d+'" onclick="window._mpSelectTrain(\''+d+'\')">'+
                '<div class="mp-mini-label">'+d+'</div>'+
                '<div style="font-size:0.78rem;color:var(--gold-secondary);font-weight:700">±'+mult+' equip mult</div>'+
                '<div style="font-size:0.7rem;color:var(--text-secondary)">'+chance+' success</div>'+
                '</div></div>';
        }).join('')+
        '</div>'+

        '<div style="font-size:0.68rem;color:var(--text-secondary);margin-bottom:8px">'+
        '⚡ Stat change = difficulty multiplier × equipment multiplier. 5 sec cooldown.'+
        '</div>'+
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
        var keys = {
            Easy:    '50% per key',
            Average: '65% per key',
            Hard:    '75% per key'
        }[d];
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
        'XP = 5 × Level × element bonus. Matching your pet\'s element to the location gives 2× or 3× XP and better keys. '+
        '<span style="color:var(--gold-secondary)">★ = your element matches</span>'+
        '</div>'+
        '<div class="row g-2 mb-3">'+
        LOCATIONS.map(function(loc) {
            var deco     = LOC_EMOJI[loc] || 'camping';
            var specials = LOC_SPECIALS[loc] || [];
            var matches  = _locMatchCount(loc);
            // Border glow: gold for 2 matches, green for 1, default for 0
            var borderStyle = matches === 2
                ? 'border-color:var(--gold-primary);box-shadow:0 0 8px rgba(255,215,0,0.35)'
                : matches === 1
                    ? 'border-color:#4caf50;box-shadow:0 0 6px rgba(76,175,80,0.25)'
                    : '';
            // XP badge
            var xpBadge = matches === 2
                ? '<span style="font-size:0.6rem;font-weight:700;color:var(--gold-primary);background:rgba(255,215,0,0.12);border-radius:4px;padding:1px 5px;display:block;margin-top:2px">3× XP ★★</span>'
                : matches === 1
                    ? '<span style="font-size:0.6rem;font-weight:700;color:#4caf50;background:rgba(76,175,80,0.1);border-radius:4px;padding:1px 5px;display:block;margin-top:2px">2× XP ★</span>'
                    : '<span style="font-size:0.6rem;color:var(--text-secondary);display:block;margin-top:2px">1× XP</span>';
            // Element icons row
            var elemIcons = specials.map(function(s) {
                var isMatch = s.toLowerCase() === petElem1 || (petElem2 && s.toLowerCase() === petElem2);
                return '<img src="/static/Emojis/Pets/Deco/'+s+'.png" '+
                    'title="'+s+(isMatch?' — matches your element!':'')+'" '+
                    'style="width:16px;height:16px;object-fit:contain;vertical-align:middle;'+
                    (isMatch ? 'filter:drop-shadow(0 0 3px gold);outline:1px solid gold;border-radius:2px;' : 'opacity:0.55;')+'">';
            }).join('');
            return '<div class="col-md-3 col-sm-4 col-6">'+
                '<div class="mp-mini-stat-card" style="cursor:pointer;transition:all 0.2s;'+borderStyle+'" '+
                'id="play-opt-'+loc.replace(/ /g,'-')+'" onclick="window._mpSelectPlay(\''+loc+'\')">'+
                '<img src="/static/Emojis/Pets/Deco/'+deco+'.png" style="width:28px;height:28px;object-fit:contain;margin-bottom:3px" onerror="this.style.display=\'none\'">'+
                '<div class="mp-mini-label">'+loc+'</div>'+
                '<div style="display:flex;gap:3px;justify-content:center;align-items:center;margin-top:3px">'+elemIcons+'</div>'+
                xpBadge+
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
        '<button class="mp-adopt-btn" id="quest-start-btn" onclick="window._mpQuestStart()">⚔️ Begin Quest</button>'+
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
        '<button class="mp-adopt-btn" onclick="window._mpQuestAbandon()" style="font-size:0.72rem;padding:5px 12px;margin-top:8px;background:rgba(231,76,60,0.15);border-color:rgba(231,76,60,0.4);color:#e74c3c">🚪 Abandon Quest</button>'+
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

    // ── Abilities ──────────────────────────────────────────────────────────
    html += '<div id="panel-abilities" style="display:none">'+
        '<div class="mp-section-title">💎 Abilities & Mastery</div>'+
        '<div class="mp-battle-card mb-3" style="font-size:0.82rem;color:var(--text-secondary)">'+
        'Spend ability points to unlock powerful abilities and stat mastery bonuses. Purchase points with levels (500 levels per point).'+
        '</div>'+
        '<div id="abilities-content">'+
        '<div class="text-center py-4">'+
        '<div class="spinner-border" style="color: var(--gold-primary);" role="status">'+
        '<span class="visually-hidden">Loading...</span>'+
        '</div>'+
        '<p class="mt-2" style="color: var(--text-secondary);">Loading abilities...</p>'+
        '</div>'+
        '</div>'+
        '</div>';

    // ── Battle Settings ────────────────────────────────────────────────────
    html += '<div id="panel-battle" style="display:none">'+
        '<div class="mp-section-title">⚔️ Battle Settings</div>'+
        '<div class="mp-battle-card mb-3" style="font-size:0.82rem;color:var(--text-secondary)">'+
        'Customize your battle formulas and scaling behavior. Configure health, attack, and defense calculations.'+
        '</div>'+
        '<div id="battle-settings-content">'+
        '<div class="text-center py-4">'+
        '<div class="spinner-border" style="color: var(--gold-primary);" role="status">'+
        '<span class="visually-hidden">Loading...</span>'+
        '</div>'+
        '<p class="mt-2" style="color: var(--text-secondary);">Loading battle settings...</p>'+
        '</div>'+
        '</div>'+
        '</div>';

    // ── Absorb ─────────────────────────────────────────────────────────────
    html += '<div id="panel-absorb" style="display:none">'+
        '<div class="mp-section-title">⚡ Absorb War Power</div>'+
        '<div class="mp-battle-card mb-3" style="font-size:0.82rem;color:var(--text-secondary)">'+
        'Your PnW nation\'s war history fuels your pet. Absorb your wins and unit kills as XP — each type absorbed once, nothing counted twice.'+
        '</div>'+
        '<div id="absorb-loading" class="text-center py-4">'+
        '<div class="spinner-border" style="color:var(--gold-primary)" role="status"></div>'+
        '<p class="mt-2" style="color:var(--text-secondary)">Loading war data...</p>'+
        '</div>'+
        '<div id="absorb-no-nation" style="display:none" class="mp-battle-card" style="text-align:center">'+
        '<p style="color:var(--text-secondary);font-size:0.85rem">No PnW nation linked to your Discord account.<br>Link your nation in-game to use this feature.</p>'+
        '</div>'+
        '<div id="absorb-content" style="display:none">'+
        // Nation lock banner
        '<div id="absorb-lock-banner" class="mp-battle-card mb-3" style="border-color:rgba(255,215,0,0.25);padding:10px 14px"></div>'+
        // Wins box
        '<div class="mp-battle-card mb-3" id="absorb-wins-box">'+
        '<div class="d-flex align-items-center justify-content-between flex-wrap gap-2 mb-2">'+
        '<div class="d-flex align-items-center gap-2">'+
        '<img src="/static/Emojis/Military/wars.png" style="width:28px;height:28px;object-fit:contain" onerror="this.style.display=\'none\'">'+
        '<span style="font-family:Orbitron,sans-serif;color:var(--gold-primary);font-size:0.95rem;font-weight:700">Wars Won</span>'+
        '</div>'+
        '<div id="absorb-wins-badge" style="font-size:0.78rem;color:var(--text-secondary)"></div>'+
        '</div>'+
        '<div id="absorb-wins-souls" style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:10px;min-height:32px"></div>'+
        '<div style="font-size:0.75rem;color:var(--gold-secondary);margin-bottom:10px" id="absorb-wins-xp-preview"></div>'+
        '<button class="mp-adopt-btn" id="absorb-wins-btn" onclick="window._mpAbsorbWins()" style="background:linear-gradient(135deg,#2d6e2d,#3a8f3a);border:1px solid rgba(76,175,80,0.8);color:#fff;opacity:1">'+
        '⚡ Absorb Wins</button>'+
        '<div id="absorb-wins-result" class="mt-2"></div>'+
        '</div>'+
        // Kills box
        '<div class="mp-battle-card" id="absorb-kills-box">'+
        '<div class="d-flex align-items-center justify-content-between flex-wrap gap-2 mb-2">'+
        '<div class="d-flex align-items-center gap-2">'+
        '<img src="/static/Emojis/Military/soldier.png" style="width:28px;height:28px;object-fit:contain" onerror="this.style.display=\'none\'">'+
        '<span style="font-family:Orbitron,sans-serif;color:var(--gold-primary);font-size:0.95rem;font-weight:700">Units Destroyed</span>'+
        '</div>'+
        '<div id="absorb-kills-badge" style="font-size:0.78rem;color:var(--text-secondary)"></div>'+
        '</div>'+
        '<div class="row g-2 mb-3" id="absorb-kills-stats"></div>'+
        '<div style="font-size:0.75rem;color:var(--gold-secondary);margin-bottom:10px" id="absorb-kills-xp-preview"></div>'+
        '<button class="mp-adopt-btn" id="absorb-kills-btn" onclick="window._mpAbsorbKills()" style="background:linear-gradient(135deg,#2d2d8f,#3a3ab0);border:1px solid rgba(120,120,255,0.8);color:#fff;opacity:1">'+
        '⚡ Absorb Kills</button>'+
        '<div id="absorb-kills-result" class="mt-2"></div>'+
        '</div>'+
        '</div>'+
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
})();

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


// ── Play themed result builder ────────────────────────────────────────────────
// Builds a clean, emoji-rich result card from the play API response.
// Avoids rendering the raw outcome string (which contains Discord emoji codes
// and Unicode that can display as mojibake).
var _ELEM_VERBS = {
    fire:     ['scorched the area','breathed a jet of flame','ignited the surroundings','radiated heat'],
    water:    ['summoned a refreshing mist','splashed through the area','called the rain','purified the water nearby'],
    electric: ['crackled with energy','lit up the area','zapped through the space','hummed with static'],
    ice:      ['frosted the ground','chilled the air','left icy paw prints','sculpted a tiny ice figure'],
    plant:    ['grew a ring of flowers','rustled the leaves','coaxed vines to bloom','scattered seeds'],
    rock:     ['skipped a stone','carved a small rune','stacked a little cairn','shook the ground'],
    air:      ['stirred a gentle breeze','whirled the dust','carried a scent on the wind','lifted a leaf'],
    magic:    ['conjured a sparkle','left a trail of glowing motes','enchanted the surroundings','made something shimmer'],
    holy:     ['radiated a warm glow','blessed the area','left a golden shimmer','soothed the space'],
    necro:    ['whispered to the shadows','found an old bone','chilled the air with spectral energy','summoned a wisp'],
    psychic:  ['levitated a pebble','sensed the surroundings','projected a mental image','read the environment'],
    fighting: ['shadowboxed the air','trained with fierce intensity','struck a powerful pose','cleared the path'],
    basic:    ['explored the area','sniffed around','wandered curiously','took in the sights']
};

var _LOC_EMOJI_KEY = {
    Camp:'camping', Bonfire:'bonfire', Beach:'beach', Forest:'forest',
    'Hot Air Balloon':'hotairballoon', Cruiseship:'cruiseship', Mountain:'mountain',
    Gym:'gym', Graveyard:'graveyard', Festival:'festival', Glacier:'glacier', Pyramids:'pyramids'
};

function _eImg(elem, size) {
    size = size || 16;
    var e = (elem||'basic').toLowerCase();
    // Capitalise first letter for filename
    var file = e.charAt(0).toUpperCase() + e.slice(1);
    return '<img src="/static/Emojis/Pets/Deco/'+file+'.png" '+
        'style="width:'+size+'px;height:'+size+'px;object-fit:contain;vertical-align:middle;margin:0 2px" '+
        'onerror="this.style.display=\'none\'">';
}

function _kImg(key, size) {
    size = size || 14;
    return '<img src="/static/Emojis/Pets/Equipment/'+key+'.png" '+
        'style="width:'+size+'px;height:'+size+'px;object-fit:contain;vertical-align:middle;margin:0 2px" '+
        'onerror="this.style.display=\'none\'">';
}

function _randVerb(elem) {
    var verbs = _ELEM_VERBS[(elem||'basic').toLowerCase()] || _ELEM_VERBS.basic;
    return verbs[Math.floor(Math.random() * verbs.length)];
}

function buildPlayResult(d, loc, petBefore) {
    // d = API response, loc = location string, petBefore = pet snapshot before play
    var pet      = d.pet || petBefore || {};
    var petName  = escHtml(pet.name || 'Your pet');
    var elem1    = (pet.element  || 'basic').toLowerCase();
    var elem2    = (pet.element2 || '').toLowerCase();
    var xp       = d.xp || 0;
    var locKey   = _LOC_EMOJI_KEY[loc] || 'camping';
    var locImg   = '<img src="/static/Emojis/Pets/Deco/'+locKey+'.png" style="width:16px;height:16px;object-fit:contain;vertical-align:middle;margin:0 2px" onerror="this.style.display=\'none\'">';

    // Determine keys awarded by diffing inventory (or fall back to parsing outcome)
    // We detect keys from the outcome string since the API doesn't return them separately
    var keysAwarded = [];
    var raw = d.outcome || '';
    ['Key3','Key2','Key1'].forEach(function(k) {
        // Count occurrences of each key name in the outcome
        var re = new RegExp(k, 'g');
        var matches = raw.match(re);
        if (matches) keysAwarded.push({name: k, count: matches.length});
    });

    // Build the activity description line
    var actLine = '';
    if (elem2 && elem2 !== 'basic' && elem2 !== elem1) {
        actLine = petName + ' ' + _randVerb(elem1) + ' ' +
            _eImg(elem1) + ' and ' + _randVerb(elem2) + ' ' + _eImg(elem2) +
            ' at ' + locImg + ' <strong>' + escHtml(loc) + '</strong>';
    } else {
        actLine = petName + ' ' + _randVerb(elem1) + ' ' + _eImg(elem1) +
            ' at ' + locImg + ' <strong>' + escHtml(loc) + '</strong>';
    }

    // XP line
    var xpLine = '✨ Gained <strong style="color:var(--gold-primary)">' + xp.toLocaleString() + ' XP</strong>';

    // Key lines
    var keyLines = keysAwarded.map(function(k) {
        return _kImg(k.name) + ' Looted <strong>' + k.name + '</strong>' + (k.count > 1 ? ' ×' + k.count : '');
    }).join('<br>');

    // Level up line
    var lvlLine = '';
    if (d.level_up) {
        lvlLine = '🎉 <strong style="color:var(--gold-primary)">Level Up!</strong> Now level ' + d.level_up.new_level + '!';
    }

    var lines = [actLine, keyLines, xpLine, lvlLine].filter(Boolean).join('<br>');

    return '<div class="mp-battle-card" style="border-color:rgba(39,174,96,0.4);font-size:0.82rem;line-height:1.8;color:var(--text-secondary)">'+lines+'</div>';
}

window._mpTab = function(tab) {
    ['train','mission','play','quest','market','absorb','abilities','battle','rename','kill'].forEach(function(t) {
        var btn = el('tab-'+t), panel = el('panel-'+t);
        if (btn)   btn.classList.toggle('active', t===tab);
        if (panel) panel.style.display = t===tab ? '' : 'none';
    });
    
    // Load content for abilities and battle settings tabs when they're opened
    if (tab === 'abilities') {
        loadAbilitiesContent();
    } else if (tab === 'battle') {
        loadBattleSettingsContent();
    } else if (tab === 'absorb') {
        _mpLoadAbsorb();
    }
};

// ── selection state ───────────────────────────────────────────────────────────
var _trainDiff   = 'Easy';
var _trainStat   = '';
var _missionDiff = 'Easy';
var _playLoc     = '';

window._mpSelectTrainStat = function(s) {
    _trainStat = s;
    ['ATT','DEF','INT','DEX','HAP','ENE'].forEach(function(x) {
        var el2 = el('train-stat-'+x);
        if (el2) el2.style.borderColor = x===s ? 'var(--gold-primary)' : 'rgba(255,215,0,0.15)';
        if (el2) el2.style.boxShadow   = x===s ? '0 0 8px var(--gold-glow)' : '';
    });
};

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

    var statHtml = '';
    if (!isLevelDown && data.gains && Object.keys(data.gains).length) {
        statHtml = '<div style="margin-top:8px;font-size:0.75rem;color:var(--text-secondary)">';
        Object.entries(data.gains).forEach(function(kv) {
            if (kv[1] && kv[1] > 0) statHtml += '<span style="margin-right:8px;color:#2ecc71">+'+kv[1]+' '+kv[0]+'</span>';
        });
        statHtml += '</div>';
    } else if (isLevelDown && data.losses && Object.keys(data.losses).length) {
        statHtml = '<div style="margin-top:8px;font-size:0.75rem;color:var(--text-secondary)">';
        Object.entries(data.losses).forEach(function(kv) {
            if (kv[1] && kv[1] > 0) statHtml += '<span style="margin-right:8px;color:#e74c3c">-'+kv[1]+' '+kv[0]+'</span>';
        });
        statHtml += '</div>';
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
        statHtml
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
    if (!_trainStat) {
        showResult('train-result', false, 'Please select a stat to train.');
        return;
    }
    var r = el('train-result');
    if (r) r.innerHTML = '<div class="mp-battle-card" style="font-size:0.8rem;color:var(--text-secondary)">Training...</div>';
    try {
        var res = await fetch('/api/pets/train', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({difficulty: _trainDiff, stat: _trainStat})
        });
        var d = await res.json();
        if (res.status === 429) {
            showResult('train-result', false, d.error || 'On cooldown.');
            _startCooldownTimer('train-btn', 'train-result', d.error);
        } else if (res.ok) {
            showResult('train-result', d.success, d.outcome);
            if (d.pet) { _pet = d.pet; renderPetCard(d.pet); }
            _startCooldownTimer('train-btn', 'train-result', null, 5);
        } else {
            showResult('train-result', false, d.error || d.detail || 'Failed');
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
        if (res.status === 429) {
            showResult('mission-result', false, d.error || 'On cooldown.');
            _startCooldownTimer('mission-btn', 'mission-result', d.error);
        } else if (res.ok) {
            showResult('mission-result', d.success, d.outcome);
            if (d.pet) { _pet = d.pet; renderPetCard(d.pet); }
            if (d.level_up) showLevelChangePopup(d.level_up, false);
            else if (d.level_down) showLevelChangePopup(d.level_down, true);
            _startCooldownTimer('mission-btn', 'mission-result', null, 5);
        } else {
            showResult('mission-result', false, d.error || d.detail || 'Failed');
        }
    } catch(e) { showResult('mission-result', false, e.message); }
};

window._mpPlay = async function() {
    if (!_playLoc) { showResult('play-result', false, 'Please select a location first.'); return; }
    var r = el('play-result');
    if (r) r.innerHTML = '<div class="mp-battle-card" style="font-size:0.8rem;color:var(--text-secondary)">Playing...</div>';
    var petSnapshot = _pet || {};
    try {
        var res = await fetch('/api/pets/play', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({location: _playLoc})
        });
        var d = await res.json();
        if (res.status === 429) {
            showResult('play-result', false, d.error || 'On cooldown.');
            _startCooldownTimer('play-btn', 'play-result', d.error);
        } else if (res.ok) {
            var resultEl = el('play-result');
            if (resultEl) resultEl.innerHTML = buildPlayResult(d, _playLoc, petSnapshot);
            if (d.pet) { _pet = d.pet; renderPetCard(d.pet); }
            if (d.level_up) showLevelChangePopup(d.level_up, false);
            _startCooldownTimer('play-btn', 'play-result', null, 5);
        } else {
            showResult('play-result', false, d.error || d.detail || 'Failed');
        }
    } catch(e) { showResult('play-result', false, e.message); }
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
    if(d.pet){ _pet=d.pet; renderPetCard(d.pet); }
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
                if(d.pet){ _pet=d.pet; renderPetCard(d.pet); }
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
            init(); // refresh pet to show updated inventory
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
            setTimeout(function(){ init(); }, 1200);
        } else {
            if (result) result.innerHTML = '<div class="mp-battle-card" style="border-color:rgba(231,76,60,0.4);color:#e74c3c;font-size:0.82rem">❌ '+(d.detail||d.error||'Failed')+'</div>';
        }
    } catch(e) {
        if (result) result.innerHTML = '<div class="mp-battle-card" style="border-color:rgba(231,76,60,0.4);color:#e74c3c;font-size:0.82rem">❌ '+e.message+'</div>';
    }
};

// Returns {matPair, gemPair, monPair, hatEquipped, hatSpecMatches, fullSet, setMult} for a pet's equipment
function getEquipSetState(pet) {
    var eq    = pet.equipment || {};
    var specs = (pet.specializations || pet.Spec || []).map(function(s){ return s.toUpperCase(); });
    var level = parseInt(pet.level || 1, 10);
    var levelBonus = Math.floor(level / 50);

    var matCounts = {}, gemCounts = {}, monCounts = {};
    (Array.isArray(eq.Material) ? eq.Material : (eq.Material && eq.Material.name ? [eq.Material] : []))
        .forEach(function(m){ if(m&&m.name){ var n=m.name.toLowerCase(); matCounts[n]=(matCounts[n]||0)+1; } });
    (eq.Gems||[]).forEach(function(g){ if(g&&g.name){ var n=g.name.toLowerCase(); gemCounts[n]=(gemCounts[n]||0)+1; } });
    (eq.Monsters||[]).forEach(function(m){ if(m&&m.name){ var n=m.name.toLowerCase(); monCounts[n]=(monCounts[n]||0)+1; } });

    var matPair = Object.values(matCounts).some(function(c){ return c >= 2; });
    var gemPair = Object.values(gemCounts).some(function(c){ return c >= 2; });
    var monPair = Object.values(monCounts).some(function(c){ return c >= 2; });

    var hat = eq.Hat;
    var hatEquipped = !!(hat && hat.name);

    // Count how many of the hat's bonus stats match a pet spec
    var hatSpecMatches = 0;
    if (hatEquipped && specs.length) {
        var hatData = getEquipItem(hat.name);
        var hatBonuses = (hatData && hatData.bonuses) ? hatData.bonuses : (hat.bonuses || {});
        Object.keys(hatBonuses).forEach(function(s){
            if (specs.indexOf(s.toUpperCase()) !== -1) hatSpecMatches++;
        });
    }

    var fullSet = matPair && gemPair && monPair && hatEquipped;
    var setMult = fullSet ? (hatSpecMatches >= 2 ? 4 : 3) : 1;
    var finalMult = setMult + levelBonus;

    return {
        matPair: matPair, gemPair: gemPair, monPair: monPair,
        hatEquipped: hatEquipped, hatSpecMatches: hatSpecMatches,
        fullSet: fullSet, setMult: setMult, finalMult: finalMult,
        // legacy alias used by buildEquipped glow logic
        hatMatchesSpec: hatSpecMatches >= 1
    };
}

function buildEquipped(pet) {
    var eq = pet.equipment||{};
    var state = getEquipSetState(pet);

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
        var f = isEmpty ? 'Basic.png' : equipImgFile(item);
        var src = isEmpty ? '/static/Emojis/Pets/Deco/Basic.png' : '/static/Emojis/Pets/Equipment/'+f;

        if (isEmpty) {
            html += '<div class="mp-equip-slot empty" title="'+sl.label+' (empty)">'+
                '<img src="'+src+'">'+
                '<span class="mp-slot-label">'+sl.label+'</span></div>';
        } else {
            var data = getEquipItem(item.name);
            var tip = item.name+' — '+bonusTooltip(data||item)+' (click to unequip)';
            var unequipSlot = sl.type === 'Material' ? 'Material' : sl.type;

            // Determine glow tier for this slot
            var glowClass = '';
            if (state.fullSet) {
                glowClass = ' equip-fullset';
            } else {
                var isPair = (sl.type === 'Monsters' && state.monPair) ||
                             (sl.type === 'Gems'     && state.gemPair) ||
                             (sl.type === 'Material' && state.matPair) ||
                             (sl.type === 'Hat'      && state.hatMatchesSpec);
                if (isPair) glowClass = ' equip-pair';
            }

            html += '<div class="mp-equip-slot mp-equip-filled'+glowClass+'" title="'+escHtml(tip)+'" '+
                'onclick="window._mpUnequipSlot('+escArg(unequipSlot)+')" style="cursor:pointer"'+
                ' data-hover-item="'+escHtml(item.name)+'">'+
                '<img src="'+src+'" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">'+
                '<span class="mp-slot-label">'+escHtml(item.name)+'</span></div>';
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
    ['Hat','Potion','Material','Gem','Monster','Key','Chest','Other'].forEach(function(t) {
        if (!grouped[t]) return;
        content += '<div style="font-size:0.68rem;color:var(--gold-secondary);font-weight:700;margin:5px 0 3px">'+t+'s</div>';
        content += '<div class="d-flex flex-wrap gap-1 mb-1">';
        grouped[t].forEach(function(item) {
            var f = equipImgFile(item);
            var rcClass = 'rc-'+(item.rarity||'Common').toLowerCase();
            var isEquippable = ['Hat','Material','Gem','Monster'].indexOf(t) !== -1;
            var isPotion     = t === 'Potion';
            var isChest      = t === 'Chest';
            var clickable    = isEquippable || isPotion || isChest;

            var eqCount  = equippedNames[item.name.toLowerCase()]||0;
            var invCount = item.count||1;
            var isEquipped = eqCount > 0;

            // Determine action label and equip count to send
            var action = isPotion ? 'Use' : (isChest ? 'Open' : (isEquipped ? 'Equipped' : 'Equip'));
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
    if (!state.matPair && !state.gemPair && !state.monPair && !state.hatEquipped) return '';

    var multColor = state.fullSet
        ? (state.hatSpecMatches >= 2 ? '#f59e0b' : '#a855f7')
        : '#57d9a3';

    var cardStyle = 'style="flex:0 0 auto;min-width:0;width:52px;padding:4px 6px"';
    var html = '<div class="d-flex gap-1 mb-2" style="padding:4px 0;flex-wrap:nowrap">';
    html += '<div class="mp-mini-stat-card" ' + cardStyle + '>' +
        '<div class="mp-mini-label" style="font-size:0.58rem">Multi</div>' +
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
        html += '<div class="mp-mini-stat-card" ' + cardStyle + '>' +
            '<div style="font-size:1rem;line-height:1">' + c.label + '</div>' +
            '<div style="font-size:0.9rem">' + (c.ok ? '✅' : '❌') + '</div>' +
            '</div>';
    });
    return html + '</div>';
}

function buildBreakdownCard(pet) {
    var xs = pet.xp_sources || {};
    var bs = pet.battle_stats || {};
    var gs = pet.gambling_stats || {};

    // ── XP Sources ──────────────────────────────────────────────
    var activities = [
        { label: 'Play',      emoji: '🎮', keys: ['play'] },
        { label: 'Train',     emoji: '🏋️', keys: ['training'] },
        { label: 'Mission',   emoji: '🎯', keys: ['mission', 'mission_fail'] },
        { label: 'Quest',     emoji: '📜', keys: ['quest'] },
        { label: 'Battle',    emoji: '⚔️', keys: ['battle', 'npc_battle', 'pvp_battle'] },
        { label: 'Colosseum', emoji: '🏛️', keys: ['colosseum'] },
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
    var battleTypes = [{key:'pvp',name:'PvP'},{key:'npc',name:'NPC'},{key:'wild_encounter',name:'Wild'},{key:'boss',name:'Boss'},{key:'colosseum',name:'Colosseum'}];
    var battleHtml = '<div class="mp-breakdown-sub">Battle Records</div><div class="d-flex gap-2 flex-wrap mb-2">';
    battleTypes.forEach(function(bt) {
        var s = bs[bt.key] || {wins:0, losses:0};
        var wr = (s.wins + s.losses) > 0 ? ((s.wins / (s.wins + s.losses)) * 100).toFixed(0) : 0;
        battleHtml += '<div class="mp-mini-stat-card">' +
            '<div class="mp-mini-label">' + bt.name + '</div>' +
            '<div><span class="text-success" style="font-size:0.78rem;font-weight:700">' + s.wins + 'W</span>' +
            '<span style="color:var(--text-secondary);font-size:0.7rem"> / </span>' +
            '<span class="text-danger" style="font-size:0.78rem;font-weight:700">' + s.losses + 'L</span></div>' +
            '<div style="font-size:0.62rem;color:var(--text-secondary)">' + wr + '% WR</div>' +
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

    // ── Collapsible wrapper ──────────────────────────────────────
    var bodyId = 'mp-breakdown-body';
    var chevId = 'mp-breakdown-chev';
    // Default: collapsed
    var html =
        '<hr class="mp-divider my-2">' +
        '<div class="mp-collapse-header" onclick="mpToggleCollapse(\'' + bodyId + '\',\'' + chevId + '\')">' +
            '<span class="mp-section-title" style="margin:0">Breakdown</span>' +
            '<span id="' + chevId + '" class="mp-chev mp-chev-collapsed">▼</span>' +
        '</div>' +
        '<div id="' + bodyId + '" class="mp-collapse-body" style="display:none">' +
            xpHtml + battleHtml + ssHtml + casinoHtml +
        '</div>';

    return html;
}
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

    // Show skill selection step before finalizing adoption
    if(body) body.innerHTML='<div class="text-center py-4"><div class="spinner-border text-primary" role="status"></div><p class="mt-2">Drawing skill choices...</p></div>';

    fetch('/api/pets/skills/adopt-draw', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({ element1: elem1, element2: elem2 || null })
    })
    .then(function(r){ return r.json(); })
    .then(function(d){
        var choices = d.choices || [];
        showSkillPickStep(body, choices, {
            category: cat, species: _adoptSel.name,
            element1: elem1, element2: elem2,
            customName: name,
            actions: { Attack: actAtk, Defense: actDef, Charge: actChg }
        });
    })
    .catch(function(e){
        // If skill draw fails, proceed without a skill
        doFinalAdopt(body, {
            category: cat, species: _adoptSel.name,
            element1: elem1, element2: elem2,
            customName: name, battleSkillId: '',
            actions: { Attack: actAtk, Defense: actDef, Charge: actChg }
        });
    });
}

function showSkillPickStep(body, choices, adoptPayload) {
    if(!body) return;
    var elem1 = adoptPayload.element1 || 'basic';
    var elem2 = adoptPayload.element2 || '';
    var elemLabel = cap(elem1) + (elem2 ? ' / ' + cap(elem2) : '');

    var ELEM_COLORS_LOCAL = {
        basic:'#aaa', fire:'#e74c3c', water:'#3498db', electric:'#f1c40f',
        ice:'#a8d8ea', plant:'#2ecc71', rock:'#95a5a6', air:'#bdc3c7',
        magic:'#9b59b6', holy:'#f39c12', necro:'#8e44ad', psychic:'#e91e63', fighting:'#e67e22',
    };
    var EFFECT_LABELS = {
        instant_damage:'Instant Damage', dot:'Damage Over Time', shield:'Shield',
        damage_reduction:'Damage Reduction', elemental_damage:'Elemental Damage',
        heal:'Heal', charge_boost:'Charge Boost', stat_debuff:'Stat Debuff',
        stat_buff:'Stat Buff', lifesteal:'Lifesteal', stun:'Stun',
        cleanse:'Cleanse', reflect:'Reflect',
    };

    var cardsHtml = choices.map(function(sk) {
        var col = ELEM_COLORS_LOCAL[sk.element] || '#aaa';
        var eff = EFFECT_LABELS[sk.effect && sk.effect.type] || (sk.effect && sk.effect.type) || '';
        return '<div class="adopt-skill-card" data-skill-id="'+escHtml(sk.id)+'" onclick="window._mpPickSkill(this,'+JSON.stringify(sk.id).replace(/"/g,'&quot;')+')" style="border:2px solid '+col+';border-radius:10px;padding:12px;cursor:pointer;transition:background 0.15s;background:rgba(0,0,0,0.3)">' +
            '<div style="font-weight:700;color:'+col+';margin-bottom:4px">'+escHtml(sk.name)+'</div>' +
            '<div style="font-size:0.72rem;color:var(--text-secondary);margin-bottom:6px">'+cap(sk.element)+' · '+eff+'</div>' +
            '<div style="font-size:0.8rem;color:var(--text-primary)">'+escHtml(sk.description)+'</div>' +
        '</div>';
    }).join('');

    body.innerHTML =
        '<div class="text-center mb-3">' +
        '<h5 style="color:var(--gold-primary)">⚔️ Choose Your Starting Battle Skill</h5>' +
        '<p style="font-size:0.85rem;color:var(--text-secondary)">Pick 1 skill from your <strong>'+escHtml(elemLabel)+'</strong> element pool. You can reroll later with ability points.</p>' +
        '</div>' +
        '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-bottom:16px" id="adopt-skill-grid">' +
        cardsHtml +
        '</div>' +
        '<div id="adopt-skill-selected" style="display:none;margin-bottom:12px;padding:10px;border-radius:8px;background:rgba(255,215,0,0.08);border:1px solid rgba(255,215,0,0.3);font-size:0.85rem;color:var(--gold-primary)"></div>' +
        '<div class="d-flex gap-2 justify-content-end">' +
        '<button class="btn btn-secondary btn-sm" onclick="window._mpForm()">← Back</button>' +
        '<button class="btn btn-primary" id="adopt-skill-confirm-btn" disabled onclick="window._mpConfirmSkill()">🐾 Adopt with this Skill</button>' +
        '</div>';

    // Store payload for confirm step
    window._adoptSkillPayload = adoptPayload;
    window._adoptChosenSkillId = '';

    window._mpPickSkill = function(cardEl, skillId) {
        document.querySelectorAll('.adopt-skill-card').forEach(function(c){
            c.style.background = 'rgba(0,0,0,0.3)';
            c.style.boxShadow = '';
        });
        cardEl.style.background = 'rgba(255,215,0,0.12)';
        cardEl.style.boxShadow = '0 0 0 2px rgba(255,215,0,0.5)';
        window._adoptChosenSkillId = skillId;
        var confirmBtn = el('adopt-skill-confirm-btn');
        if(confirmBtn) confirmBtn.disabled = false;
        var selDiv = el('adopt-skill-selected');
        if(selDiv){ selDiv.style.display='block'; selDiv.textContent='✅ Selected: ' + skillId.replace(/_/g,' ').replace(/\b\w/g,function(c){return c.toUpperCase();}); }
    };

    window._mpConfirmSkill = function() {
        if(!window._adoptChosenSkillId) return;
        var payload = Object.assign({}, window._adoptSkillPayload, { battleSkillId: window._adoptChosenSkillId });
        doFinalAdopt(body, payload);
    };
}

function doFinalAdopt(body, payload) {
    if(body) body.innerHTML='<div class="text-center py-5"><div class="spinner-border text-primary" role="status"></div><p class="mt-3">Creating your pet...</p></div>';

    fetch('/api/pets/adopt',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(payload)
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
                if (d.pet) { _pet = d.pet; renderPetCard(d.pet); renderAllPanels(d.pet); }
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
            _pet = d.pet;
            if (callback) {
                // Chain second equip, then refresh
                callback();
            } else {
                renderPetCard(d.pet);
                renderAllPanels(d.pet);
                _showToast('✅ ' + name + ' equipped!', true);
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
            _pet = d.pet;
            renderPetCard(d.pet);
            renderAllPanels(d.pet);
            _showToast('📦 ' + cleanDiscordText(d.message || 'Unequipped').replace(/\*\*/g,'').trim(), true);
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
                _pet = d.pet;
                renderPetCard(d.pet);
                renderAllPanels(d.pet);
                _showToast('🔥 ' + (d.message || 'Consumed!'), true);
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
                _pet = d.pet;
                renderPetCard(d.pet);
                renderAllPanels(d.pet);
                var msg = name + (qty > 1 ? ' x'+qty : '') + ' used!';
                if (d.message) {
                    var clean = String(d.message)
                        .replace(/<img[^>]*>/gi, '')
                        .replace(/<[^>]+>/g, '')
                        .replace(/\*\*/g, '')
                        .replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>')
                        .trim();
                    if (clean) msg = name + (qty > 1 ? ' x'+qty : '') + ' — ' + clean;
                }
                _showToast('🧪 ' + msg, true);
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

// ── Load abilities content inline ─────────────────────────────────────────────
function loadAbilitiesContent() {
    var container = el('abilities-content');
    if (!container) return;
    
    // Show loading state
    container.innerHTML = '<div class="text-center py-4">'+
        '<div class="spinner-border" style="color: var(--gold-primary);" role="status">'+
        '<span class="visually-hidden">Loading...</span>'+
        '</div>'+
        '<p class="mt-2" style="color: var(--text-secondary);">Loading abilities...</p>'+
        '</div>';
    
    // Load ability tree CSS if not already loaded
    if (!document.querySelector('link[href="/css/ability_tree.css"]')) {
        var lnk = document.createElement('link');
        lnk.rel = 'stylesheet'; lnk.href = '/css/ability_tree.css';
        document.head.appendChild(lnk);
    }
    
    // Load ability tree data + skill state in parallel
    Promise.all([
        fetch('/api/pets/ability-tree').then(function(r){ return r.json(); }),
        fetch('/api/pets/skills').then(function(r){ return r.json(); }).catch(function(){ return null; }),
    ]).then(function(results) {
        var data = results[0];
        var skillData = results[1];
        if (data && data.available_points !== undefined) {
            if (skillData) data.skill_state = skillData;
            renderFullAbilityTreeInline(data, container);
        } else {
            container.innerHTML = '<div class="mp-battle-card" style="color:#e74c3c">Failed to load abilities data</div>';
        }
    }).catch(function(e) {
        container.innerHTML = '<div class="mp-battle-card" style="color:#e74c3c">Error loading abilities: ' + e.message + '</div>';
    });
}
window.loadAbilitiesContent = loadAbilitiesContent;
function renderFullAbilityTreeInline(state, container) {
    // Set up the ability tree state for inline rendering
    window._abilityTreeState = state;
    window._abilityTreeSelectedNode = null;
    window._abilityTreeOpenStat = null;
    
    var pts = state.available_points || 0;
    var skillState = state.skill_state || null;
    var needsMigration = skillState && skillState.slots && skillState.slots.length > 0 && !skillState.slots[0].filled;
    
    // Create the full ability tree interface inline
    var html = '<div class="at-inline-container" style="background:linear-gradient(135deg,rgba(8,8,8,0.85),rgba(14,14,14,0.85));border-radius:8px;padding:12px">';
    
    // Migration banner for existing pets with no battle skill
    if (needsMigration) {
        html += '<div id="skill-migration-banner" style="background:rgba(231,76,60,0.12);border:1px solid rgba(231,76,60,0.4);border-radius:8px;padding:10px 14px;margin-bottom:10px;display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap">' +
            '<div style="font-size:0.82rem;color:#e74c3c"><strong>⚔️ No Battle Skill!</strong> Your pet doesn\'t have a starting battle skill yet.</div>' +
            '<button class="mp-adopt-btn" style="font-size:0.75rem;padding:5px 14px;background:rgba(231,76,60,0.2);border-color:rgba(231,76,60,0.5);color:#e74c3c" onclick="window.migrateSkill()">Get Free Skill + 1 Point</button>' +
        '</div>';
    }
    
    // Header with points badge
    html += '<div class="at-inline-header" style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">';
    html += '<div class="at-inline-title" style="font-family:Orbitron,sans-serif;font-size:1rem;color:var(--gold-primary);text-shadow:0 0 10px rgba(255,215,0,0.4);font-weight:700">💎 Abilities & Mastery</div>';
    html += '<div class="at-points-badge" style="background:rgba(255,215,0,0.12);border:1px solid rgba(255,215,0,0.35);border-radius:20px;padding:4px 12px;font-size:0.75rem;color:var(--gold-primary);font-weight:700">✨ ' + pts + ' pt' + (pts !== 1 ? 's' : '') + '</div>';
    html += '</div>';
    
    // Top bar with purchase and advantage mastery
    html += '<div class="at-topbar" style="display:flex;align-items:stretch;gap:8px;margin-bottom:10px;flex-wrap:wrap">';
    html += renderPurchaseBarInline(state);
    html += renderAdvMasteryCardsInline(state);
    html += '</div>';
    
    // Main content layout
    html += '<div class="at-content-layout" style="display:flex;gap:12px;align-items:flex-start">';
    html += '<div class="at-tree-container" style="flex:2;min-width:0;padding-right:4px">' + renderTreeInline(state) + '</div>';
    html += '<div class="at-details-container" style="flex:1;min-width:220px;position:sticky;top:0" id="at-details-panel-inline">' + renderDetailsInline() + '</div>';
    html += '</div>';
    
    html += '</div>';
    
    // Add toast container for notifications
    html += '<div id="at-toast-inline" style="display:none"></div>';
    
    container.innerHTML = html;
    
    // Expose global handlers for inline version
    exposeInlineAbilityHandlers();

    // Migration handler
    window.migrateSkill = function() {
        var banner = el('skill-migration-banner');
        if (banner) banner.innerHTML = '<div style="font-size:0.82rem;color:var(--text-secondary)">Assigning skill...</div>';
        fetch('/api/pets/skills/migrate', { method:'POST', headers:{'Content-Type':'application/json'} })
            .then(function(r){ return r.json(); })
            .then(function(d){
                if (d.ok) {
                    showToastInline(d.message || 'Skill assigned!', true);
                    loadAbilitiesContent();
                } else {
                    showToastInline(d.message || 'Failed', false);
                }
            })
            .catch(function(e){ showToastInline('Error: ' + e.message, false); });
    };
}

// ── Purchase bar for inline version ───────────────────────────────────────────
function renderPurchaseBarInline(state) {
    var pts = state.available_points || 0;
    var level = state.current_level || 1;
    var canBuy = state.can_purchase_point || false;
    var cost = state.point_cost || 500;
    return '<div class="at-purchase-compact" style="background:linear-gradient(135deg,rgba(255,215,0,0.08),rgba(255,140,0,0.04));border:1px solid rgba(255,215,0,0.25);border-radius:6px;padding:6px 12px;display:flex;align-items:center;gap:10px;flex:1;min-width:0">' +
        '<div class="at-purchase-info" style="display:flex;align-items:center;gap:10px;flex:1;flex-wrap:wrap">' +
            '<span class="at-purchase-label" style="font-size:0.75rem;color:var(--gold-primary);font-weight:700;white-space:nowrap">💎 ' + pts + ' pt' + (pts !== 1 ? 's' : '') + '</span>' +
            '<span class="at-purchase-cost" style="font-size:0.72rem;color:var(--text-secondary);white-space:nowrap">Cost: ' + cost + ' Lvls</span>' +
            '<span class="at-purchase-level" style="font-size:0.72rem;color:var(--text-secondary);white-space:nowrap">Lv.' + level + '</span>' +
        '</div>' +
        '<button class="at-purchase-btn-compact" style="background:' + (canBuy ? 'linear-gradient(135deg,var(--gold-primary),#ffb300)' : 'rgba(80,80,80,0.4)') + ';border:none;border-radius:5px;color:' + (canBuy ? '#000' : 'rgba(255,255,255,0.4)') + ';font-size:0.72rem;font-weight:700;padding:5px 10px;cursor:' + (canBuy ? 'pointer' : 'not-allowed') + ';transition:all 0.2s;white-space:nowrap;flex-shrink:0"' + (canBuy ? '' : ' disabled') +
            ' onclick="purchaseAbilityPointInline()">' +
            (canBuy ? '🛒 Buy Point' : '❌ Need ' + (cost - level) + ' Lvls') +
        '</button>' +
    '</div>';
}

// ── Advantage mastery cards for inline version ────────────────────────────────
function renderAdvMasteryCardsInline(state) {
    var adv = state.advantage_mastery || {};
    var pts = state.available_points || 0;
    var canSpend = pts >= 1;
    var cards = [
        { key:'type',    icon:'⚔️', label:'Type Adv.' },
        { key:'element', icon:'✨', label:'Elem Adv.' },
    ];
    var html = '<div class="at-adv-mastery-group" style="display:flex;gap:6px">';
    cards.forEach(function(c) {
        var m = adv[c.key] || { points:0, bonus:0 };
        var mpts = m.points || 0;
        var bonus = m.bonus !== undefined ? m.bonus : (mpts * 0.1);
        var isSelected = window._abilityTreeSelectedNode && window._abilityTreeSelectedNode.type === 'adv' && window._abilityTreeSelectedNode.key === c.key;
        html += '<div class="at-adv-card' + (isSelected ? ' at-selected' : '') +
            '" data-adv-key="' + c.key + '" style="background:linear-gradient(135deg,rgba(255,215,0,0.07),rgba(255,140,0,0.03));border:1px solid rgba(255,215,0,0.22);border-radius:6px;padding:5px 10px;display:flex;align-items:center;gap:6px;cursor:pointer;transition:all 0.2s;min-width:110px" onclick="selectAdvNodeInline(\'' + c.key + '\')">' +
            '<div class="at-adv-card-icon" style="font-size:1rem;flex-shrink:0">' + c.icon + '</div>' +
            '<div class="at-adv-card-info" style="flex:1;min-width:0">' +
                '<div class="at-adv-card-label" style="font-family:Orbitron,sans-serif;font-size:0.62rem;color:var(--gold-primary);font-weight:700;line-height:1.1">' + c.label + '</div>' +
                '<div class="at-adv-card-val" style="font-size:0.68rem;color:#4caf50;font-weight:700;line-height:1">+' + bonus.toFixed(1) + '</div>' +
                '<div class="at-adv-card-pts" style="font-size:0.58rem;color:var(--text-secondary);line-height:1">' + mpts + ' pts</div>' +
            '</div>' +
            '<button class="at-adv-upgrade-btn" style="background:' + (canSpend ? 'linear-gradient(135deg,#4caf50,#45a049)' : 'rgba(80,80,80,0.4)') + ';border:none;border-radius:3px;color:#fff;font-size:0.6rem;font-weight:700;cursor:' + (canSpend ? 'pointer' : 'not-allowed') + ';padding:2px 6px;transition:all 0.2s"' + (canSpend ? '' : ' disabled') +
                ' onclick="event.stopPropagation(); upgradeAdvMasteryInline(\'' + c.key + '\')">+</button>' +
        '</div>';
    });
    return html + '</div>';
}

// ── Load battle settings content inline ───────────────────────────────────────
function loadBattleSettingsContent() {
    var container = el('battle-settings-content');
    if (!container) return;
    
    // Show loading state
    container.innerHTML = '<div class="text-center py-4">'+
        '<div class="spinner-border" style="color: var(--gold-primary);" role="status">'+
        '<span class="visually-hidden">Loading...</span>'+
        '</div>'+
        '<p class="mt-2" style="color: var(--text-secondary);">Loading battle settings...</p>'+
        '</div>';
    
    // Load battle settings and render inline
    fetch('/api/battle/settings/my')
        .then(function(r){ 
            if (r.status === 401 || r.status === 403) {
                // User not authenticated - show default settings
                renderBattleSettingsInline(getDefaultBattleSettings(), container);
                return;
            }
            return r.json(); 
        })
        .then(function(data) {
            if (data && data.settings) {
                renderBattleSettingsInline(data.settings, container);
            } else if (data) {
                // Already handled above for auth errors
                return;
            } else {
                renderBattleSettingsInline(getDefaultBattleSettings(), container);
            }
        })
        .catch(function(e) {
            console.log('Battle settings error:', e);
            renderBattleSettingsInline(getDefaultBattleSettings(), container);
        });
}

// ── Render battle settings content inline ─────────────────────────────────────
function renderBattleSettingsInline(settings, container) {
    var formula = settings.formula || getDefaultBattleSettings().formula;
    
    var html = '<div class="row g-3">';
    
    // Left column - Health formula
    html += '<div class="col-md-4">';
    html += '<div class="mp-battle-card">';
    html += '<div class="mp-mini-label mb-2">Health Formula</div>';
    html += '<div class="mb-2">';
    html += '<label style="font-size:0.75rem;color:var(--text-secondary)">Stats to include:</label>';
    html += '<div class="d-flex flex-wrap gap-1 mt-1">';
    ['ATT', 'DEF', 'INT', 'DEX', 'HAP', 'ENE'].forEach(function(stat) {
        var checked = formula.health_stats.indexOf(stat) !== -1;
        html += '<label class="d-flex align-items-center gap-1" style="font-size:0.7rem;cursor:pointer">';
        html += '<input type="checkbox" ' + (checked ? 'checked' : '') + ' onchange="updateHealthStats(\'' + stat + '\')">';
        html += '<span>' + stat + '</span>';
        html += '</label>';
    });
    html += '</div>';
    html += '</div>';
    html += '<div class="mb-2">';
    html += '<label class="d-flex align-items-center gap-2" style="font-size:0.75rem;cursor:pointer">';
    html += '<input type="checkbox" ' + (formula.health_use_average ? 'checked' : '') + ' onchange="toggleHealthAverage()">';
    html += '<span>Use average instead of sum</span>';
    html += '</label>';
    html += '</div>';
    html += '<div class="mb-2">';
    html += '<label style="font-size:0.75rem;color:var(--text-secondary)">Multiplier:</label>';
    html += '<input type="number" class="form-control mp-input" style="font-size:0.75rem;padding:0.25rem 0.5rem" value="' + formula.health_multiplier + '" onchange="updateHealthMultiplier(this.value)">';
    html += '</div>';
    html += '</div>';
    html += '</div>';
    
    // Middle column - Attack formula
    html += '<div class="col-md-4">';
    html += '<div class="mp-battle-card">';
    html += '<div class="mp-mini-label mb-2">Attack Formula</div>';
    html += '<div class="mb-2">';
    html += '<label style="font-size:0.75rem;color:var(--text-secondary)">Stats to include:</label>';
    html += '<div class="d-flex flex-wrap gap-1 mt-1">';
    ['ATT', 'DEF', 'INT', 'DEX', 'HAP', 'ENE'].forEach(function(stat) {
        var checked = formula.attack_stats.indexOf(stat) !== -1;
        html += '<label class="d-flex align-items-center gap-1" style="font-size:0.7rem;cursor:pointer">';
        html += '<input type="checkbox" ' + (checked ? 'checked' : '') + ' onchange="updateAttackStats(\'' + stat + '\')">';
        html += '<span>' + stat + '</span>';
        html += '</label>';
    });
    html += '</div>';
    html += '</div>';
    html += '<div class="mb-2">';
    html += '<label class="d-flex align-items-center gap-2" style="font-size:0.75rem;cursor:pointer">';
    html += '<input type="checkbox" ' + (formula.attack_use_average ? 'checked' : '') + ' onchange="toggleAttackAverage()">';
    html += '<span>Use average instead of sum</span>';
    html += '</label>';
    html += '</div>';
    html += '<div class="mb-2">';
    html += '<label style="font-size:0.75rem;color:var(--text-secondary)">Multiplier:</label>';
    html += '<input type="number" class="form-control mp-input" style="font-size:0.75rem;padding:0.25rem 0.5rem" value="' + formula.attack_multiplier + '" onchange="updateAttackMultiplier(this.value)">';
    html += '</div>';
    html += '</div>';
    html += '</div>';
    
    // Right column - Defense formula
    html += '<div class="col-md-4">';
    html += '<div class="mp-battle-card">';
    html += '<div class="mp-mini-label mb-2">Defense Formula</div>';
    html += '<div class="mb-2">';
    html += '<label style="font-size:0.75rem;color:var(--text-secondary)">Stats to include:</label>';
    html += '<div class="d-flex flex-wrap gap-1 mt-1">';
    ['ATT', 'DEF', 'INT', 'DEX', 'HAP', 'ENE'].forEach(function(stat) {
        var checked = formula.defense_stats.indexOf(stat) !== -1;
        html += '<label class="d-flex align-items-center gap-1" style="font-size:0.7rem;cursor:pointer">';
        html += '<input type="checkbox" ' + (checked ? 'checked' : '') + ' onchange="updateDefenseStats(\'' + stat + '\')">';
        html += '<span>' + stat + '</span>';
        html += '</label>';
    });
    html += '</div>';
    html += '</div>';
    html += '<div class="mb-2">';
    html += '<label class="d-flex align-items-center gap-2" style="font-size:0.75rem;cursor:pointer">';
    html += '<input type="checkbox" ' + (formula.defense_use_average ? 'checked' : '') + ' onchange="toggleDefenseAverage()">';
    html += '<span>Use average instead of sum</span>';
    html += '</label>';
    html += '</div>';
    html += '<div class="mb-2">';
    html += '<label style="font-size:0.75rem;color:var(--text-secondary)">Multiplier:</label>';
    html += '<input type="number" class="form-control mp-input" style="font-size:0.75rem;padding:0.25rem 0.5rem" value="' + formula.defense_multiplier + '" onchange="updateDefenseMultiplier(this.value)">';
    html += '</div>';
    html += '</div>';
    html += '</div>';
    
    html += '</div>';
    
    // Save button
    html += '<div class="text-center mt-3">';
    html += '<button class="mp-adopt-btn" onclick="saveBattleSettings()">Save Battle Settings</button>';
    html += '</div>';
    
    container.innerHTML = html;
}

// ── Default battle settings ───────────────────────────────────────────────────
function getDefaultBattleSettings() {
    return {
        formula: {
            health_stats: ['HAP', 'ENE'],
            health_use_average: true,
            health_multiplier: 10.0,
            health_level_factor: true,
            health_equipment_factor: true,
            health_custom_multiplier: 1.0,
            health_custom_divider: 1.0,
            
            attack_stats: ['ATT', 'DEX'],
            attack_use_average: false,
            attack_multiplier: 1.0,
            attack_level_factor: true,
            attack_equipment_factor: true,
            attack_custom_multiplier: 1.0,
            attack_custom_divider: 1.0,
            
            defense_stats: ['DEF', 'INT'],
            defense_use_average: false,
            defense_multiplier: 1.0,
            defense_level_factor: true,
            defense_equipment_factor: true,
            defense_custom_multiplier: 1.0,
            defense_custom_divider: 1.0,
            
            use_original_scaling: false,
            formula_name: "Default Formula"
        }
    };
}

// ── Ability and battle settings interaction functions ─────────────────────────
window.purchaseAbilityPoint = function() {
    fetch('/api/pets/ability-tree/purchase-point', {method: 'POST'})
        .then(function(r){ return r.json(); })
        .then(function(d) {
            if (d.success) {
                loadAbilitiesContent(); // Reload to show updated points
                if (_pet) { _pet = d.pet; renderPetCard(_pet); } // Update pet display
            } else {
                alert('Failed to purchase point: ' + (d.error || 'Unknown error'));
            }
        })
        .catch(function(e) { alert('Error: ' + e.message); });
};

window.spendStatMastery = function(stat) {
    fetch('/api/pets/ability-tree/spend-stat-mastery', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({stat: stat})
    })
        .then(function(r){ return r.json(); })
        .then(function(d) {
            if (d.success) {
                loadAbilitiesContent(); // Reload to show updated mastery
            } else {
                alert('Failed to spend mastery point: ' + (d.error || 'Unknown error'));
            }
        })
        .catch(function(e) { alert('Error: ' + e.message); });
};

window.upgradeAbility = function(abilityId) {
    fetch('/api/pets/ability-tree/unlock-ability', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ability_id: abilityId})
    })
        .then(function(r){ return r.json(); })
        .then(function(d) {
            if (d.success) {
                loadAbilitiesContent(); // Reload to show updated abilities
            } else {
                alert('Failed to upgrade ability: ' + (d.error || 'Unknown error'));
            }
        })
        .catch(function(e) { alert('Error: ' + e.message); });
};

// Battle settings update functions (simplified for inline display)
var _currentBattleSettings = null;

window.updateHealthStats = function(stat) {
    if (!_currentBattleSettings) _currentBattleSettings = getDefaultBattleSettings();
    var stats = _currentBattleSettings.formula.health_stats;
    var index = stats.indexOf(stat);
    if (index !== -1) {
        stats.splice(index, 1);
    } else {
        stats.push(stat);
    }
};

window.toggleHealthAverage = function() {
    if (!_currentBattleSettings) _currentBattleSettings = getDefaultBattleSettings();
    _currentBattleSettings.formula.health_use_average = !_currentBattleSettings.formula.health_use_average;
};

window.updateHealthMultiplier = function(value) {
    if (!_currentBattleSettings) _currentBattleSettings = getDefaultBattleSettings();
    _currentBattleSettings.formula.health_multiplier = parseFloat(value) || 1.0;
};

window.updateAttackStats = function(stat) {
    if (!_currentBattleSettings) _currentBattleSettings = getDefaultBattleSettings();
    var stats = _currentBattleSettings.formula.attack_stats;
    var index = stats.indexOf(stat);
    if (index !== -1) {
        stats.splice(index, 1);
    } else {
        stats.push(stat);
    }
};

window.toggleAttackAverage = function() {
    if (!_currentBattleSettings) _currentBattleSettings = getDefaultBattleSettings();
    _currentBattleSettings.formula.attack_use_average = !_currentBattleSettings.formula.attack_use_average;
};

window.updateAttackMultiplier = function(value) {
    if (!_currentBattleSettings) _currentBattleSettings = getDefaultBattleSettings();
    _currentBattleSettings.formula.attack_multiplier = parseFloat(value) || 1.0;
};

window.updateDefenseStats = function(stat) {
    if (!_currentBattleSettings) _currentBattleSettings = getDefaultBattleSettings();
    var stats = _currentBattleSettings.formula.defense_stats;
    var index = stats.indexOf(stat);
    if (index !== -1) {
        stats.splice(index, 1);
    } else {
        stats.push(stat);
    }
};

window.toggleDefenseAverage = function() {
    if (!_currentBattleSettings) _currentBattleSettings = getDefaultBattleSettings();
    _currentBattleSettings.formula.defense_use_average = !_currentBattleSettings.formula.defense_use_average;
};

window.updateDefenseMultiplier = function(value) {
    if (!_currentBattleSettings) _currentBattleSettings = getDefaultBattleSettings();
    _currentBattleSettings.formula.defense_multiplier = parseFloat(value) || 1.0;
};

window.saveBattleSettings = function() {
    if (!_currentBattleSettings) {
        alert('No settings to save');
        return;
    }
    
    fetch('/api/battle/settings/save', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(_currentBattleSettings)
    })
        .then(function(r){ return r.json(); })
        .then(function(d) {
            if (d.success) {
                alert('Battle settings saved successfully!');
            } else {
                alert('Failed to save settings: ' + (d.error || 'Unknown error'));
            }
        })
        .catch(function(e) { 
            console.log('Save error:', e);
            alert('Settings saved locally (server unavailable)');
        });
};

})();

// ── Tree rendering for inline version ─────────────────────────────────────────
function renderTreeInline(state) {
    var STATS = ['ATT','DEF','INT','DEX','HAP','ENE'];
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
    
    var mastery   = state.stat_mastery || {};
    var abilities = state.abilities    || {};
    var pts       = state.available_points || 0;

    return STATS.map(function(stat) {
        var m    = mastery[stat] || { points:0, multiplier:1.0 };
        var meta = STAT_META[stat];
        var isUnlocked = m.points > 0;
        var canUnlock  = pts >= 1 && !isUnlocked;
        var mClass = isUnlocked ? 'at-stat-unlocked' : canUnlock ? 'at-stat-available' : 'at-stat-locked';
        var isSelMastery = window._abilityTreeSelectedNode && window._abilityTreeSelectedNode.type === 'mastery' && window._abilityTreeSelectedNode.stat === stat;
        var isOpen = window._abilityTreeOpenStat === stat;

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
                summaryHtml = '<span class="at-section-summary" style="display:flex;gap:4px;margin-left:auto">' +
                    '<span class="at-summary-mult" style="background:rgba(76,175,80,0.15);color:#4caf50;padding:2px 6px;border-radius:10px;font-size:0.6rem;font-weight:700">x' + m.multiplier.toFixed(1) + '</span>' +
                    (totalCount > 0 ? '<span class="at-summary-ab" style="background:rgba(255,215,0,0.15);color:var(--gold-primary);padding:2px 6px;border-radius:10px;font-size:0.6rem;font-weight:700">' + ownedCount + '/' + totalCount + ' ab</span>' : '') +
                '</span>';
            } else {
                summaryHtml = '<span class="at-section-summary" style="margin-left:auto"><span class="at-summary-locked" style="background:rgba(128,128,128,0.15);color:#888;padding:2px 6px;border-radius:10px;font-size:0.6rem;font-weight:700">🔒 ' + totalCount + ' ab</span></span>';
            }
        }

        var chevron = '<span class="at-chevron' + (isOpen ? ' at-chevron-open' : '') + '" style="margin-left:8px;transition:transform 0.2s;transform:rotate(' + (isOpen ? '90deg' : '0deg') + ');color:var(--gold-primary);font-weight:700">›</span>';

        var masteryRow =
            '<div class="at-stat-mastery ' + mClass + (isSelMastery ? ' at-selected' : '') + '" data-stat="' + stat + '" style="display:flex;align-items:center;gap:8px;padding:8px;border-radius:6px;cursor:pointer;transition:all 0.2s;background:' + (isSelMastery ? 'rgba(255,215,0,0.1)' : 'rgba(0,0,0,0.2)') + ';border:1px solid ' + (isSelMastery ? 'var(--gold-primary)' : 'rgba(255,215,0,0.2)') + '" onclick="selectMasteryNodeInline(\'' + stat + '\')">' +
                '<div class="at-stat-icon" style="width:32px;height:32px;flex-shrink:0"><img src="' + meta.icon + '" alt="' + stat + '" style="width:100%;height:100%;object-fit:contain" onerror="this.style.display=\'none\'"></div>' +
                '<div class="at-stat-info" style="flex:1;min-width:0">' +
                    '<div class="at-stat-name" style="font-size:0.8rem;font-weight:700;color:var(--gold-primary)">' + stat + ' Mastery</div>' +
                    '<div style="display:flex;gap:8px;font-size:0.7rem;color:var(--text-secondary)">' +
                        '<span class="at-stat-multiplier">x' + m.multiplier.toFixed(1) + '</span>' +
                        '<span class="at-stat-points">' + m.points + ' pts</span>' +
                    '</div>' +
                '</div>' +
                summaryHtml +
                '<div class="at-stat-action" style="flex-shrink:0" onclick="event.stopPropagation()">' +
                    (isUnlocked
                        ? '<button class="at-upgrade-btn" style="background:linear-gradient(135deg,#4caf50,#45a049);border:none;border-radius:4px;color:#fff;font-size:0.7rem;font-weight:700;padding:4px 8px;cursor:pointer;transition:all 0.2s" onclick="event.stopPropagation(); upgradeMasteryInline(\'' + stat + '\')">+</button>'
                        : canUnlock
                            ? '<button class="at-unlock-btn" style="background:linear-gradient(135deg,var(--gold-primary),#ffb300);border:none;border-radius:4px;color:#000;font-size:0.7rem;font-weight:700;padding:4px 8px;cursor:pointer;transition:all 0.2s" onclick="event.stopPropagation(); unlockMasteryInline(\'' + stat + '\')">Unlock</button>'
                            : '<span class="at-locked-indicator" style="color:#888;font-size:0.8rem">🔒</span>') +
                '</div>' +
                chevron +
            '</div>';

        var abilitiesHtml = '';
        if (isOpen) {
            if (isUnlocked) {
                abilitiesHtml = '<div class="at-abilities-list" style="margin-top:8px;padding-left:16px">' +
                    statAbs.map(function(ab) {
                        var lvl     = ab.current_level || 0;
                        var maxLvl  = ab.effective_max_level || ab.max_level || 5;
                        var canUp   = ab.can_upgrade || false;
                        var isMaxed = lvl >= maxLvl;
                        var icon    = ABILITY_ICONS[ab.id] || '✨';
                        var isSelAb = window._abilityTreeSelectedNode && window._abilityTreeSelectedNode.type === 'ability' && window._abilityTreeSelectedNode.abilityId === ab.id;

                        var rowClass = 'at-ability-row ' +
                            (isMaxed ? 'at-ability-maxed' :
                             lvl > 0  ? 'at-ability-owned' :
                             canUp    ? 'at-ability-available' : 'at-ability-locked');

                        var pips = '';
                        for (var i = 1; i <= maxLvl; i++) {
                            var pc = i <= lvl ? (isMaxed ? 'maxed' : 'filled') :
                                     (i === lvl + 1 && canUp ? 'next' : '');
                            var pipColor = pc === 'maxed' ? '#ff9800' : pc === 'filled' ? '#4caf50' : pc === 'next' ? 'var(--gold-primary)' : 'rgba(255,255,255,0.2)';
                            pips += '<div class="at-pip" style="width:8px;height:8px;border-radius:50%;background:' + pipColor + ';border:1px solid rgba(255,255,255,0.3)"></div>';
                        }

                        var badge = isMaxed
                            ? '<span class="at-row-badge at-badge-max" style="background:#ff9800;color:#fff;padding:2px 6px;border-radius:10px;font-size:0.6rem;font-weight:700">MAX</span>'
                            : canUp
                                ? '<span class="at-row-badge at-badge-up" style="background:var(--gold-primary);color:#000;padding:2px 6px;border-radius:10px;font-size:0.6rem;font-weight:700">' + (lvl === 0 ? 'UNLOCK' : 'UP') + '</span>'
                                : lvl > 0
                                    ? '<span class="at-row-badge at-badge-lv" style="background:#4caf50;color:#fff;padding:2px 6px;border-radius:10px;font-size:0.6rem;font-weight:700">Lv.' + lvl + '</span>'
                                    : '<span class="at-row-badge at-badge-lock" style="background:#888;color:#fff;padding:2px 6px;border-radius:10px;font-size:0.6rem;font-weight:700">🔒</span>';

                        // Show the current value at the current level (or level-1 preview if locked)
                        var valueChip = '';
                        if (ab.formatted_value) {
                            var chipColor = lvl > 0 ? (isMaxed ? '#ff9800' : '#4caf50') : 'rgba(255,255,255,0.3)';
                            valueChip = '<span style="font-size:0.6rem;color:' + chipColor + ';font-weight:700;min-width:28px;text-align:right;flex-shrink:0">' + ab.formatted_value + '</span>';
                        }

                        return '<div class="' + rowClass + '" data-ability-id="' + ab.id + '" style="display:flex;align-items:center;gap:8px;padding:6px 8px;margin-bottom:4px;border-radius:4px;cursor:pointer;transition:all 0.2s;background:' + (isSelAb ? 'rgba(255,215,0,0.1)' : 'rgba(0,0,0,0.3)') + ';border:1px solid ' + (isSelAb ? 'var(--gold-primary)' : 'rgba(255,215,0,0.1)') + '" onclick="selectAbilityNodeInline(\'' + ab.id + '\')">' +
                            '<span class="at-row-icon" style="font-size:1rem;flex-shrink:0">' + icon + '</span>' +
                            '<span class="at-row-name" style="flex:1;font-size:0.75rem;color:var(--text-primary);font-weight:600">' + ab.name + '</span>' +
                            '<div class="at-row-pips" style="display:flex;gap:2px;flex-shrink:0">' + pips + '</div>' +
                            valueChip +
                            badge +
                            (canUp ? '<button class="at-ability-upgrade-btn" style="background:linear-gradient(135deg,var(--gold-primary),#ffb300);border:none;border-radius:3px;color:#000;font-size:0.6rem;font-weight:700;padding:2px 6px;margin-left:4px;cursor:pointer;transition:all 0.2s" onclick="event.stopPropagation(); upgradeAbilityInline(\'' + ab.id + '\')">+</button>' : '') +
                        '</div>';
                    }).join('') +
                '</div>';
            } else {
                abilitiesHtml = '<div class="at-abilities-locked" style="margin-top:8px;padding:12px;text-align:center;color:#888;font-size:0.8rem;background:rgba(0,0,0,0.2);border-radius:4px">🔒 Unlock ' + stat + ' Mastery to access ' + totalCount + ' abilities</div>';
            }
        }

        return '<div class="at-stat-section' + (isOpen ? ' at-section-open' : '') + '" data-stat="' + stat + '" style="margin-bottom:8px">' +
            '<div class="at-section-header" style="border-left:3px solid ' + meta.color + ';padding-left:8px" onclick="toggleStatSectionInline(\'' + stat + '\');">' +
                masteryRow +
            '</div>' +
            (isOpen ? '<div class="at-section-content">' + abilitiesHtml + '</div>' : '') +
        '</div>';
    }).join('') + renderSkillBranchInline(state);
}

// ── SKILL branch for inline version ───────────────────────────────────────────
function renderSkillBranchInline(state) {
    var ABILITY_ICONS_SKILL = {
        'skill_slot_2':'🎴','skill_slot_3':'🎴','skill_slot_4':'🎴',
        'skill_reroll_all':'🔄','skill_cross_element':'🌀',
    };
    var ELEM_COLORS_INLINE = {
        basic:'#aaa', fire:'#e74c3c', water:'#3498db', electric:'#f1c40f',
        ice:'#a8d8ea', plant:'#2ecc71', rock:'#95a5a6', air:'#bdc3c7',
        magic:'#9b59b6', holy:'#f39c12', necro:'#8e44ad', psychic:'#e91e63', fighting:'#e67e22',
    };
    var EFFECT_LABELS_INLINE = {
        instant_damage:'Instant Damage', dot:'Damage Over Time', shield:'Shield',
        damage_reduction:'Damage Reduction', elemental_damage:'Elemental Damage',
        heal:'Heal', charge_boost:'Charge Boost', stat_debuff:'Stat Debuff',
        stat_buff:'Stat Buff', lifesteal:'Lifesteal', stun:'Stun',
        cleanse:'Cleanse', reflect:'Reflect',
    };

    var abilities  = state.abilities || {};
    var pts        = state.available_points || 0;
    var skillState = state.skill_state || null;
    var isOpen     = window._abilityTreeOpenStat === 'SKILL';

    var skillAbs = Object.keys(abilities)
        .map(function(id){ return abilities[id]; })
        .filter(function(a){ return a.stat === 'SKILL'; });
    var ownedCount = skillAbs.filter(function(a){ return (a.current_level || 0) > 0; }).length;
    var totalCount = skillAbs.length;

    var equippedCount = skillState ? skillState.slots.filter(function(s){ return s.filled; }).length : 0;
    var isSelSkill = window._abilityTreeSelectedNode && window._abilityTreeSelectedNode.type === 'skill_branch';

    var summaryHtml = '';
    if (!isOpen) {
        summaryHtml = '<span class="at-section-summary" style="display:flex;gap:4px;margin-left:auto">' +
            '<span style="background:rgba(230,126,34,0.15);color:#e67e22;padding:2px 6px;border-radius:10px;font-size:0.6rem;font-weight:700">' + equippedCount + ' skill' + (equippedCount !== 1 ? 's' : '') + '</span>' +
            (ownedCount > 0 ? '<span style="background:rgba(255,215,0,0.15);color:var(--gold-primary);padding:2px 6px;border-radius:10px;font-size:0.6rem;font-weight:700">' + ownedCount + '/' + totalCount + ' ab</span>' : '') +
        '</span>';
    }

    var chevron = '<span class="at-chevron' + (isOpen ? ' at-chevron-open' : '') + '" style="margin-left:8px;transition:transform 0.2s;transform:rotate(' + (isOpen ? '90deg' : '0deg') + ');color:var(--gold-primary);font-weight:700">›</span>';

    var headerRow =
        '<div class="at-stat-mastery at-stat-unlocked' + (isSelSkill ? ' at-selected' : '') + '" style="display:flex;align-items:center;gap:8px;padding:8px;border-radius:6px;cursor:pointer;transition:all 0.2s;background:' + (isSelSkill ? 'rgba(255,215,0,0.1)' : 'rgba(0,0,0,0.2)') + ';border:1px solid ' + (isSelSkill ? 'var(--gold-primary)' : 'rgba(255,215,0,0.2)') + '" onclick="selectSkillBranchInline()">' +
            '<div style="width:32px;height:32px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:1.2rem">⚔️</div>' +
            '<div style="flex:1;min-width:0">' +
                '<div style="font-size:0.8rem;font-weight:700;color:var(--gold-primary)">Battle Skills</div>' +
                '<div style="display:flex;gap:8px;font-size:0.7rem;color:var(--text-secondary)">' +
                    '<span>Free Branch</span>' +
                    '<span>' + (skillState ? skillState.max_slots : 1) + ' slot' + ((skillState ? skillState.max_slots : 1) !== 1 ? 's' : '') + '</span>' +
                '</div>' +
            '</div>' +
            summaryHtml +
            '<div style="flex-shrink:0"></div>' +
            chevron +
        '</div>';

    var contentHtml = '';
    if (isOpen) {
        // Equipped skill slots
        var slotsHtml = '<div style="margin-top:8px;padding-left:16px">';
        if (skillState && skillState.slots) {
            skillState.slots.forEach(function(slot) {
                var sk = slot.skill;
                var elemColor = sk ? (ELEM_COLORS_INLINE[sk.element] || '#aaa') : '#555';
                var effType = sk ? (EFFECT_LABELS_INLINE[sk.effect && sk.effect.type] || (sk.effect && sk.effect.type) || '') : '';
                var isSelSlot = window._abilityTreeSelectedNode && window._abilityTreeSelectedNode.type === 'skill_slot' && window._abilityTreeSelectedNode.slot === slot.slot;
                var canDraw = pts >= 1;
                slotsHtml +=
                    '<div style="display:flex;align-items:center;gap:8px;padding:8px;margin-bottom:6px;border-radius:6px;cursor:pointer;background:' + (isSelSlot ? 'rgba(255,215,0,0.08)' : 'rgba(0,0,0,0.3)') + ';border:1px solid ' + elemColor + ';transition:all 0.2s" onclick="selectSkillSlotInline(' + slot.slot + ')">' +
                        '<div style="font-size:0.7rem;color:var(--text-secondary);flex-shrink:0;min-width:40px">Slot ' + (slot.slot + 1) + '</div>' +
                        (sk
                            ? '<div style="flex:1;min-width:0">' +
                                '<div style="font-size:0.78rem;font-weight:700;color:' + elemColor + '">' + sk.name + '</div>' +
                                '<div style="font-size:0.68rem;color:var(--text-secondary)">' + (sk.element.charAt(0).toUpperCase() + sk.element.slice(1)) + ' · ' + effType + '</div>' +
                              '</div>'
                            : '<div style="flex:1;font-size:0.75rem;color:#666;font-style:italic">Empty — draw to fill</div>') +
                        (canDraw
                            ? '<button style="background:rgba(255,215,0,0.12);border:1px solid rgba(255,215,0,0.3);border-radius:4px;color:var(--gold-primary);font-size:0.65rem;padding:3px 8px;cursor:pointer" onclick="event.stopPropagation(); drawSkillForSlotInline(' + slot.slot + ')">🎲 1pt</button>'
                            : '<button style="background:rgba(128,128,128,0.1);border:1px solid rgba(128,128,128,0.2);border-radius:4px;color:#888;font-size:0.65rem;padding:3px 8px;cursor:not-allowed" disabled title="Need 1 ability point">🔒</button>') +
                    '</div>';
            });
        }
        slotsHtml += '</div>';

        // Skill branch abilities
        var skillAbHtml = '<div style="margin-top:8px;padding-left:16px">' +
            skillAbs.map(function(ab) {
                var lvl    = ab.current_level || 0;
                var maxLvl = ab.effective_max_level || ab.max_level || 1;
                var canUp  = ab.can_upgrade || false;
                var isMaxed = lvl >= maxLvl;
                var icon   = ABILITY_ICONS_SKILL[ab.id] || '⚔️';
                var isSelAb = window._abilityTreeSelectedNode && window._abilityTreeSelectedNode.type === 'ability' && window._abilityTreeSelectedNode.abilityId === ab.id;

                var pips = '';
                for (var i = 1; i <= maxLvl; i++) {
                    var pc = i <= lvl ? (isMaxed ? 'maxed' : 'filled') : (i === lvl + 1 && canUp ? 'next' : '');
                    var pipColor = pc === 'maxed' ? '#ff9800' : pc === 'filled' ? '#4caf50' : pc === 'next' ? 'var(--gold-primary)' : 'rgba(255,255,255,0.2)';
                    pips += '<div style="width:8px;height:8px;border-radius:50%;background:' + pipColor + ';border:1px solid rgba(255,255,255,0.3)"></div>';
                }

                var badge = isMaxed
                    ? '<span style="background:#ff9800;color:#fff;padding:2px 6px;border-radius:10px;font-size:0.6rem;font-weight:700">MAX</span>'
                    : canUp
                        ? '<span style="background:var(--gold-primary);color:#000;padding:2px 6px;border-radius:10px;font-size:0.6rem;font-weight:700">' + (lvl === 0 ? 'UNLOCK' : 'UP') + '</span>'
                        : lvl > 0
                            ? '<span style="background:#4caf50;color:#fff;padding:2px 6px;border-radius:10px;font-size:0.6rem;font-weight:700">Lv.' + lvl + '</span>'
                            : '<span style="background:#888;color:#fff;padding:2px 6px;border-radius:10px;font-size:0.6rem;font-weight:700">🔒</span>';

                return '<div style="display:flex;align-items:center;gap:8px;padding:6px 8px;margin-bottom:4px;border-radius:4px;cursor:pointer;transition:all 0.2s;background:' + (isSelAb ? 'rgba(255,215,0,0.1)' : 'rgba(0,0,0,0.3)') + ';border:1px solid ' + (isSelAb ? 'var(--gold-primary)' : 'rgba(255,215,0,0.1)') + '" onclick="selectAbilityNodeInline(\'' + ab.id + '\')">' +
                    '<span style="font-size:1rem;flex-shrink:0">' + icon + '</span>' +
                    '<span style="flex:1;font-size:0.75rem;color:var(--text-primary);font-weight:600">' + ab.name + '</span>' +
                    '<div style="display:flex;gap:2px;flex-shrink:0">' + pips + '</div>' +
                    badge +
                    (canUp ? '<button style="background:linear-gradient(135deg,var(--gold-primary),#ffb300);border:none;border-radius:3px;color:#000;font-size:0.6rem;font-weight:700;padding:2px 6px;margin-left:4px;cursor:pointer" onclick="event.stopPropagation(); upgradeAbilityInline(\'' + ab.id + '\')">+</button>' : '') +
                '</div>';
            }).join('') +
        '</div>';

        contentHtml = slotsHtml + skillAbHtml;
    }

    return '<div class="at-stat-section' + (isOpen ? ' at-section-open' : '') + '" data-stat="SKILL" style="margin-bottom:8px">' +
        '<div class="at-section-header" style="border-left:3px solid #e67e22;padding-left:8px" onclick="toggleStatSectionInline(\'SKILL\')">' +
            headerRow +
        '</div>' +
        (isOpen ? '<div class="at-section-content">' + contentHtml + '</div>' : '') +
    '</div>';
}

// ── Details panel for inline version ──────────────────────────────────────────
function renderDetailsInline() {
    if (!window._abilityTreeSelectedNode) {
        return '<div class="at-details-empty" style="text-align:center;padding:20px;color:var(--text-secondary);background:rgba(0,0,0,0.2);border-radius:6px">' +
            '<div class="at-details-empty-icon" style="font-size:2rem;margin-bottom:8px">👆</div>' +
            '<div style="font-size:0.8rem">Click any mastery, ability, or advantage card to see details & actions.</div>' +
        '</div>';
    }
    
    var node = window._abilityTreeSelectedNode;
    var state = window._abilityTreeState;

    // ── Skill branch header ───────────────────────────────────────────────────
    if (node.type === 'skill_branch') {
        return '<div style="padding:12px;background:rgba(0,0,0,0.2);border-radius:6px">' +
            '<div style="font-size:1.5rem;text-align:center;margin-bottom:8px">⚔️</div>' +
            '<div style="font-size:0.85rem;font-weight:700;color:var(--gold-primary);text-align:center;margin-bottom:4px">Battle Skills</div>' +
            '<div style="font-size:0.72rem;color:var(--text-secondary);text-align:center;margin-bottom:10px">Free Branch — No mastery required</div>' +
            '<div style="font-size:0.78rem;color:var(--text-primary)">Battle skills are active abilities used in combat — one per slot, usable every 3 turns. ' +
                'Your first slot is free. Unlock more slots and utilities with ability points. ' +
                'Click a skill slot to draw new choices or see details.</div>' +
        '</div>';
    }

    // ── Skill slot detail ─────────────────────────────────────────────────────
    if (node.type === 'skill_slot') {
        var slotIdx = node.slot;
        var skillState = state && state.skill_state;
        var slotData = skillState && skillState.slots && skillState.slots[slotIdx];
        var sk = slotData && slotData.skill;
        var ELEM_COLORS_D = {
            basic:'#aaa', fire:'#e74c3c', water:'#3498db', electric:'#f1c40f',
            ice:'#a8d8ea', plant:'#2ecc71', rock:'#95a5a6', air:'#bdc3c7',
            magic:'#9b59b6', holy:'#f39c12', necro:'#8e44ad', psychic:'#e91e63', fighting:'#e67e22',
        };
        var EFFECT_LABELS_D = {
            instant_damage:'Instant Damage', dot:'Damage Over Time', shield:'Shield',
            damage_reduction:'Damage Reduction', elemental_damage:'Elemental Damage',
            heal:'Heal', charge_boost:'Charge Boost', stat_debuff:'Stat Debuff',
            stat_buff:'Stat Buff', lifesteal:'Lifesteal', stun:'Stun',
            cleanse:'Cleanse', reflect:'Reflect',
        };
        var elemColor = sk ? (ELEM_COLORS_D[sk.element] || '#aaa') : '#888';
        var effType = sk ? (EFFECT_LABELS_D[sk.effect && sk.effect.type] || (sk.effect && sk.effect.type) || '') : '';
        var pts = (state && state.available_points) || 0;
        var canDraw = pts >= 1;

        var skillInfo = sk
            ? '<div style="border-left:3px solid ' + elemColor + ';padding-left:10px;margin:10px 0">' +
                '<div style="font-weight:700;color:' + elemColor + ';margin-bottom:2px">' + sk.name + '</div>' +
                '<div style="font-size:0.72rem;color:var(--text-secondary);margin-bottom:6px">' + (sk.element.charAt(0).toUpperCase() + sk.element.slice(1)) + ' · ' + effType + '</div>' +
                '<div style="font-size:0.78rem;color:var(--text-primary)">' + sk.description + '</div>' +
              '</div>'
            : '<div style="color:var(--text-secondary);font-size:0.78rem;margin:10px 0">No skill equipped. Draw 5 choices from your element pool to pick one.</div>';

        return '<div style="padding:12px;background:rgba(0,0,0,0.2);border-radius:6px">' +
            '<div style="font-size:0.85rem;font-weight:700;color:var(--gold-primary);margin-bottom:4px">🎴 Skill Slot ' + (slotIdx + 1) + '</div>' +
            '<div style="font-size:0.72rem;color:var(--text-secondary);margin-bottom:8px">' + (sk ? 'Equipped' : 'Empty') + '</div>' +
            skillInfo +
            '<div style="display:flex;justify-content:space-between;font-size:0.72rem;color:var(--text-secondary);margin:8px 0 4px">' +
                '<span>Draw cost: <strong style="color:var(--gold-primary)">1 ability point</strong></span>' +
                '<span>You have: <strong style="color:' + (canDraw ? '#4caf50' : '#e74c3c') + '">' + pts + ' pt' + (pts !== 1 ? 's' : '') + '</strong></span>' +
            '</div>' +
            (canDraw
                ? '<button style="width:100%;background:linear-gradient(135deg,rgba(255,215,0,0.15),rgba(255,140,0,0.1));border:1px solid rgba(255,215,0,0.4);border-radius:6px;color:var(--gold-primary);font-size:0.78rem;font-weight:700;padding:8px;cursor:pointer;margin-top:4px" onclick="drawSkillForSlotInline(' + slotIdx + ')">🎲 Draw 5 Choices (1 pt)</button>'
                : '<button style="width:100%;background:rgba(128,128,128,0.1);border:1px solid rgba(128,128,128,0.3);border-radius:6px;color:#888;font-size:0.78rem;font-weight:700;padding:8px;cursor:not-allowed;margin-top:4px" disabled>❌ Need 1 ability point to draw</button>') +
            '<div id="at-skill-draw-result-inline" style="margin-top:10px"></div>' +
        '</div>';
    }

    // ── Skill draw choices ────────────────────────────────────────────────────
    if (node.type === 'skill_choices') {
        var choices = node.choices || [];
        var slotIdx2 = node.slot;
        var ELEM_COLORS_C = {
            basic:'#aaa', fire:'#e74c3c', water:'#3498db', electric:'#f1c40f',
            ice:'#a8d8ea', plant:'#2ecc71', rock:'#95a5a6', air:'#bdc3c7',
            magic:'#9b59b6', holy:'#f39c12', necro:'#8e44ad', psychic:'#e91e63', fighting:'#e67e22',
        };
        var EFFECT_LABELS_C = {
            instant_damage:'Instant Damage', dot:'Damage Over Time', shield:'Shield',
            damage_reduction:'Damage Reduction', elemental_damage:'Elemental Damage',
            heal:'Heal', charge_boost:'Charge Boost', stat_debuff:'Stat Debuff',
            stat_buff:'Stat Buff', lifesteal:'Lifesteal', stun:'Stun',
            cleanse:'Cleanse', reflect:'Reflect',
        };
        var html = '<div style="padding:12px;background:rgba(0,0,0,0.2);border-radius:6px">' +
            '<div style="font-size:0.85rem;font-weight:700;color:var(--gold-primary);margin-bottom:4px">🎲 Choose a Skill</div>' +
            '<div style="font-size:0.72rem;color:var(--text-secondary);margin-bottom:10px">Slot ' + (slotIdx2 + 1) + ' — Pick one</div>';
        choices.forEach(function(sk) {
            var elemColor = ELEM_COLORS_C[sk.element] || '#aaa';
            var effType = EFFECT_LABELS_C[sk.effect && sk.effect.type] || (sk.effect && sk.effect.type) || '';
            html += '<div style="border:1px solid ' + elemColor + ';border-radius:6px;padding:8px;margin-bottom:8px;cursor:pointer;transition:background 0.15s;background:rgba(0,0,0,0.3)" onclick="equipSkillChoiceInline(\'' + sk.id + '\',' + slotIdx2 + ')" onmouseover="this.style.background=\'rgba(255,215,0,0.08)\'" onmouseout="this.style.background=\'rgba(0,0,0,0.3)\'">' +
                '<div style="font-weight:700;color:' + elemColor + ';font-size:0.8rem;margin-bottom:2px">' + sk.name + '</div>' +
                '<div style="font-size:0.68rem;color:var(--text-secondary);margin-bottom:4px">' + (sk.element.charAt(0).toUpperCase() + sk.element.slice(1)) + ' · ' + effType + '</div>' +
                '<div style="font-size:0.75rem;color:var(--text-primary)">' + sk.description + '</div>' +
            '</div>';
        });
        html += '</div>';
        return html;
    }
    
    if (node.type === 'mastery') {
        var stat = node.stat;
        var m = (state.stat_mastery || {})[stat] || { points:0, multiplier:1.0 };
        var canUp = (state.available_points || 0) >= 1;
        return '<div class="at-details-panel" style="background:rgba(0,0,0,0.2);border-radius:6px;padding:12px">' +
            '<div class="at-details-header" style="display:flex;align-items:center;gap:8px;margin-bottom:12px">' +
                '<img src="/static/Emojis/Pets/Deco/' + stat + '.png" style="width:32px;height:32px" onerror="this.style.display=\'none\'">' +
                '<div>' +
                    '<div class="at-details-title" style="font-size:0.9rem;font-weight:700;color:var(--gold-primary)">' + stat + ' Mastery</div>' +
                    '<div class="at-details-subtitle" style="font-size:0.7rem;color:var(--text-secondary)">Stat Multiplier</div>' +
                '</div>' +
            '</div>' +
            '<div class="at-details-description" style="font-size:0.75rem;color:var(--text-secondary);margin-bottom:12px">Each point multiplies your ' + stat + ' stat by an additional 0.1x. At least 1 point is required to unlock abilities in this branch.</div>' +
            '<div class="at-details-stats" style="margin-bottom:12px">' +
                '<div class="at-detail-row" style="display:flex;justify-content:space-between;margin-bottom:4px;font-size:0.75rem"><span>Points Invested</span><span style="color:var(--gold-secondary);font-weight:700">' + m.points + '</span></div>' +
                '<div class="at-detail-row" style="display:flex;justify-content:space-between;margin-bottom:4px;font-size:0.75rem"><span>Current Multiplier</span><span style="color:#4caf50;font-weight:700">x' + m.multiplier.toFixed(1) + '</span></div>' +
                '<div class="at-detail-row" style="display:flex;justify-content:space-between;font-size:0.75rem"><span>Next Point</span><span style="color:var(--gold-primary);font-weight:700">x' + (m.multiplier + 0.1).toFixed(1) + '</span></div>' +
            '</div>' +
            '<div class="at-details-action">' +
                (canUp
                    ? '<button class="at-action-btn" style="width:100%;background:linear-gradient(135deg,#4caf50,#45a049);border:none;border-radius:4px;color:#fff;font-size:0.8rem;font-weight:700;padding:8px;cursor:pointer;transition:all 0.2s" onclick="upgradeMasteryInline(\'' + stat + '\')">⬆️ Spend 1 Point (+0.1x)</button>'
                    : '<button class="at-action-btn" style="width:100%;background:rgba(80,80,80,0.4);border:none;border-radius:4px;color:rgba(255,255,255,0.4);font-size:0.8rem;font-weight:700;padding:8px;cursor:not-allowed" disabled>❌ Need more ability points</button>') +
            '</div>' +
        '</div>';
    }

    if (node.type === 'ability') {
        var abilityId = node.abilityId;
        var abilities = state.abilities || {};
        var ab = abilities[abilityId];
        if (!ab) return '<div class="at-details-empty" style="text-align:center;padding:20px;color:var(--text-secondary);background:rgba(0,0,0,0.2);border-radius:6px">Ability not found.</div>';
        var lvl    = ab.current_level || 0;
        var maxLvl = ab.effective_max_level || ab.max_level || 5;
        var canUp  = ab.can_upgrade || false;
        var isMaxed = lvl >= maxLvl;
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
            'ene_charged_start':'🔋','ene_overcharged':'⚡'
        };
        var icon = ABILITY_ICONS[abilityId] || '✨';
        var pips = '';
        for (var i = 1; i <= maxLvl; i++) {
            var pc = i <= lvl ? (isMaxed ? '#ff9800' : '#4caf50') : (i === lvl + 1 && canUp ? 'var(--gold-primary)' : 'rgba(255,255,255,0.15)');
            pips += '<div style="width:12px;height:12px;border-radius:50%;background:' + pc + ';border:1px solid rgba(255,255,255,0.3)"></div>';
        }
        var statusLabel = isMaxed
            ? '<span style="background:#ff9800;color:#fff;padding:2px 8px;border-radius:10px;font-size:0.65rem;font-weight:700">MAX</span>'
            : lvl > 0
                ? '<span style="background:#4caf50;color:#fff;padding:2px 8px;border-radius:10px;font-size:0.65rem;font-weight:700">Lv.' + lvl + ' / ' + maxLvl + '</span>'
                : '<span style="background:#888;color:#fff;padding:2px 8px;border-radius:10px;font-size:0.65rem;font-weight:700">Locked</span>';
        return '<div class="at-details-panel" style="background:rgba(0,0,0,0.2);border-radius:6px;padding:12px">' +
            '<div class="at-details-header" style="display:flex;align-items:center;gap:8px;margin-bottom:12px">' +
                '<span style="font-size:1.8rem;flex-shrink:0">' + icon + '</span>' +
                '<div style="flex:1;min-width:0">' +
                    '<div class="at-details-title" style="font-size:0.9rem;font-weight:700;color:var(--gold-primary)">' + (ab.name || abilityId) + '</div>' +
                    '<div style="margin-top:4px">' + statusLabel + '</div>' +
                '</div>' +
            '</div>' +
            (ab.description ? (function() {
                // Replace {value} placeholder with the actual formatted value at current level
                var displayVal = ab.formatted_value || '';
                var desc = ab.description.replace(/\{value\}/g, '<strong style="color:var(--gold-primary)">' + displayVal + '</strong>');
                return '<div class="at-details-description" style="font-size:0.75rem;color:var(--text-secondary);margin-bottom:12px">' + desc + '</div>';
            })() : '') +
            '<div class="at-details-stats" style="margin-bottom:12px">' +
                '<div class="at-detail-row" style="display:flex;justify-content:space-between;margin-bottom:4px;font-size:0.75rem"><span>Level</span><span style="color:var(--gold-secondary);font-weight:700">' + lvl + ' / ' + maxLvl + '</span></div>' +
                (lvl > 0 && ab.formatted_value ? '<div class="at-detail-row" style="display:flex;justify-content:space-between;margin-bottom:4px;font-size:0.75rem"><span>Current Value</span><span style="color:#4caf50;font-weight:700">' + ab.formatted_value + '</span></div>' : '') +
                (ab.effect && ab.effect.per_level ? (function() {
                    // Calculate next level value for preview
                    var nextLvl = Math.min(lvl + 1, maxLvl);
                    var base = ab.effect.base || 0;
                    var perLvl = ab.effect.per_level || 0;
                    var nextVal = base + perLvl * (nextLvl - 1);
                    // Format next value same way as formatted_value
                    var fmtNext = '';
                    var effType = (ab.effect && ab.effect.type) || '';
                    if (effType.endsWith('_mult') || effType.endsWith('_multiplier')) {
                        if (effType === 'battle_defense_mult' || effType === 'battle_damage_mult' || effType === 'xp_multiplier' || effType === 'casino_xp_gain_mult') {
                            fmtNext = Math.round((nextVal - 1.0) * 100) + '%';
                        } else {
                            fmtNext = nextVal.toFixed(1);
                        }
                    } else if (effType === 'casino_xp_loss_reduction' || effType === 'battle_health_bonus' || effType === 'low_health_damage_reduction' || effType === 'charge_vulnerability_reduction' || effType === 'critical_hit_chance') {
                        fmtNext = Math.round(nextVal * 100) + '%';
                    } else if (effType === 'charge_limit_bonus' || effType === 'starting_charge_bonus' || effType === 'overcharged_bonus') {
                        fmtNext = String(Math.round(nextVal));
                    } else {
                        fmtNext = nextVal.toFixed(1);
                    }
                    return (lvl < maxLvl ? '<div class="at-detail-row" style="display:flex;justify-content:space-between;font-size:0.75rem"><span>Next Level (' + nextLvl + ')</span><span style="color:var(--gold-primary);font-weight:700">' + fmtNext + '</span></div>' : '');
                })() : '') +
            '</div>' +
            '<div style="display:flex;gap:4px;margin-bottom:12px">' + pips + '</div>' +
            '<div class="at-details-action">' +
                (isMaxed
                    ? '<button style="width:100%;background:rgba(255,152,0,0.2);border:1px solid #ff9800;border-radius:4px;color:#ff9800;font-size:0.8rem;font-weight:700;padding:8px;cursor:default">✅ Maxed Out</button>'
                    : canUp
                        ? '<button class="at-action-btn" style="width:100%;background:linear-gradient(135deg,var(--gold-primary),#ffb300);border:none;border-radius:4px;color:#000;font-size:0.8rem;font-weight:700;padding:8px;cursor:pointer;transition:all 0.2s" onclick="upgradeAbilityInline(\'' + abilityId + '\')">' + (lvl === 0 ? '🔓 Unlock Ability' : '⬆️ Upgrade Ability') + '</button>'
                        : '<button style="width:100%;background:rgba(80,80,80,0.4);border:none;border-radius:4px;color:rgba(255,255,255,0.4);font-size:0.8rem;font-weight:700;padding:8px;cursor:not-allowed" disabled>❌ Need more ability points</button>') +
            '</div>' +
        '</div>';
    }
    
    if (node.type === 'adv') {
        var advKey = node.key;
        var advLabels = { type: 'Type Advantage', element: 'Element Advantage' };
        var advIcons  = { type: '⚔️', element: '✨' };
        var advDescs  = {
            type:    'Each point adds +0.1 flat bonus to your type advantage multiplier when you have a type matchup advantage.',
            element: 'Each point adds +0.1 flat bonus to your element advantage multiplier when you have an element matchup advantage.'
        };
        var advM   = (state.advantage_mastery || {})[advKey] || { points: 0, bonus: 0 };
        var advPts = advM.points || 0;
        var advBonus = advM.bonus !== undefined ? advM.bonus : (advPts * 0.1);
        var canUpAdv = (state.available_points || 0) >= 1;
        return '<div class="at-details-panel" style="background:rgba(0,0,0,0.2);border-radius:6px;padding:12px">' +
            '<div class="at-details-header" style="display:flex;align-items:center;gap:8px;margin-bottom:12px">' +
                '<span style="font-size:1.8rem;flex-shrink:0">' + (advIcons[advKey] || '✨') + '</span>' +
                '<div>' +
                    '<div class="at-details-title" style="font-size:0.9rem;font-weight:700;color:var(--gold-primary)">' + (advLabels[advKey] || advKey) + '</div>' +
                    '<div class="at-details-subtitle" style="font-size:0.7rem;color:var(--text-secondary)">Advantage Mastery</div>' +
                '</div>' +
            '</div>' +
            '<div class="at-details-description" style="font-size:0.75rem;color:var(--text-secondary);margin-bottom:12px">' + (advDescs[advKey] || '') + '</div>' +
            '<div class="at-details-stats" style="margin-bottom:12px">' +
                '<div class="at-detail-row" style="display:flex;justify-content:space-between;margin-bottom:4px;font-size:0.75rem"><span>Points Invested</span><span style="color:var(--gold-secondary);font-weight:700">' + advPts + '</span></div>' +
                '<div class="at-detail-row" style="display:flex;justify-content:space-between;margin-bottom:4px;font-size:0.75rem"><span>Current Bonus</span><span style="color:#4caf50;font-weight:700">+' + advBonus.toFixed(1) + '</span></div>' +
                '<div class="at-detail-row" style="display:flex;justify-content:space-between;font-size:0.75rem"><span>Next Point</span><span style="color:var(--gold-primary);font-weight:700">+' + (advBonus + 0.1).toFixed(1) + '</span></div>' +
            '</div>' +
            '<div class="at-details-action">' +
                (canUpAdv
                    ? '<button class="at-action-btn" style="width:100%;background:linear-gradient(135deg,#4caf50,#45a049);border:none;border-radius:4px;color:#fff;font-size:0.8rem;font-weight:700;padding:8px;cursor:pointer;transition:all 0.2s" onclick="upgradeAdvMasteryInline(\'' + advKey + '\')">⬆️ Spend 1 Point (+0.1 bonus)</button>'
                    : '<button style="width:100%;background:rgba(80,80,80,0.4);border:none;border-radius:4px;color:rgba(255,255,255,0.4);font-size:0.8rem;font-weight:700;padding:8px;cursor:not-allowed" disabled>❌ Need more ability points</button>') +
            '</div>' +
        '</div>';
    }

    return '<div class="at-details-empty" style="text-align:center;padding:20px;color:var(--text-secondary);background:rgba(0,0,0,0.2);border-radius:6px">Select an item to see details</div>';
}

// ── Inline ability tree handlers ──────────────────────────────────────────────
function exposeInlineAbilityHandlers() {
    window.toggleStatSectionInline = function(stat) {
        console.log('[mypet.js] toggleStatSectionInline called with stat:', stat);
        window._abilityTreeOpenStat = (window._abilityTreeOpenStat === stat) ? null : stat;
        // Re-render just the tree container
        var tc = document.querySelector('.at-tree-container');
        if (tc && window._abilityTreeState) {
            tc.innerHTML = renderTreeInline(window._abilityTreeState);
        }
    };
    
    window.selectMasteryNodeInline = function(stat) {
        console.log('[mypet.js] selectMasteryNodeInline called with stat:', stat);
        try {
            window._abilityTreeSelectedNode = { type: 'mastery', stat: stat };
            
            // Clear previous selections
            document.querySelectorAll('.at-selected').forEach(function(node_el) {
                node_el.classList.remove('at-selected');
            });
            
            // Add selection to current node
            var masteryNode = document.querySelector('.at-stat-section[data-stat="' + stat + '"] .at-stat-mastery');
            if (masteryNode) {
                masteryNode.classList.add('at-selected');
            }
            
            var dp = document.getElementById('at-details-panel-inline');
            if (dp) dp.innerHTML = renderDetailsInline();
        } catch (e) {
            console.error('[mypet.js] Error in selectMasteryNodeInline:', e);
        }
    };
    
    window.selectAbilityNodeInline = function(abilityId) {
        console.log('[mypet.js] selectAbilityNodeInline called with abilityId:', abilityId);
        try {
            window._abilityTreeSelectedNode = { type: 'ability', abilityId: abilityId };
            
            // Clear previous selections
            document.querySelectorAll('.at-selected').forEach(function(node_el) {
                node_el.classList.remove('at-selected');
            });
            
            // Add selection to current node
            var abilityNode = document.querySelector('.at-ability-row[data-ability-id="' + abilityId + '"]');
            if (abilityNode) {
                abilityNode.classList.add('at-selected');
            }
            
            var dp = document.getElementById('at-details-panel-inline');
            if (dp) dp.innerHTML = renderDetailsInline();
        } catch (e) {
            console.error('[mypet.js] Error in selectAbilityNodeInline:', e);
        }
    };
    
    window.selectAdvNodeInline = function(key) {
        console.log('[mypet.js] selectAdvNodeInline called with key:', key);
        try {
            window._abilityTreeSelectedNode = { type: 'adv', key: key };
            
            // Clear previous selections
            document.querySelectorAll('.at-selected').forEach(function(node_el) {
                node_el.classList.remove('at-selected');
            });
            
            // Add selection to current node
            var advNode = document.querySelector('.at-adv-card[data-adv-key="' + key + '"]');
            if (advNode) {
                advNode.classList.add('at-selected');
            }
            
            var dp = document.getElementById('at-details-panel-inline');
            if (dp) dp.innerHTML = renderDetailsInline();
        } catch (e) {
            console.error('[mypet.js] Error in selectAdvNodeInline:', e);
        }
    };
    
    window.purchaseAbilityPointInline = function() {
        console.log('[mypet.js] purchaseAbilityPointInline called');
        var state = window._abilityTreeState || {};
        var currentLevel = state.current_level || 0;
        var cost = state.point_cost || 500;
        var newLevel = currentLevel - cost;
        showAbilityPurchaseConfirmModal(currentLevel, cost, newLevel);
    };

    window._confirmAbilityPointPurchase = function() {
        var modal = document.getElementById('at-purchase-modal');
        if (modal) modal.style.display = 'none';
        var btn = document.getElementById('at-purchase-confirm-btn');
        if (btn) { btn.disabled = true; btn.textContent = 'Purchasing...'; }

        fetch('/api/pets/ability-tree/purchase', {method: 'POST'})
            .then(function(r){ return r.json(); })
            .then(function(d) {
                if (d.ok) {
                    showAbilityPurchaseResultModal(true, d.message || 'Ability point purchased!', d.tree);
                    loadAbilitiesContent();
                } else {
                    showAbilityPurchaseResultModal(false, d.message || 'Purchase failed.');
                }
            })
            .catch(function(e) {
                console.error('[mypet.js] Error in _confirmAbilityPointPurchase:', e);
                showAbilityPurchaseResultModal(false, 'Error: ' + e.message);
            });
    };
    
    window.upgradeMasteryInline = function(stat) {
        console.log('[mypet.js] upgradeMasteryInline called with stat:', stat);
        fetch('/api/pets/ability-tree/mastery', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({stat: stat, points: 1})
        })
            .then(function(r){ return r.json(); })
            .then(function(d) {
                if (d.ok) {
                    showToastInline(d.message || 'Mastery upgraded!', true);
                    loadAbilitiesContent(); // Reload to show updated mastery
                } else {
                    showToastInline('Failed to upgrade mastery: ' + (d.message || 'Unknown error'), false);
                }
            })
            .catch(function(e) { 
                console.error('[mypet.js] Error in upgradeMasteryInline:', e);
                showToastInline('Error: ' + e.message, false); 
            });
    };
    
    window.unlockMasteryInline = window.upgradeMasteryInline;
    
    window.upgradeAbilityInline = function(abilityId) {
        console.log('[mypet.js] upgradeAbilityInline called with abilityId:', abilityId);
        fetch('/api/pets/ability-tree/unlock', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ability_id: abilityId})
        })
            .then(function(r){ return r.json(); })
            .then(function(d) {
                if (d.ok) {
                    showToastInline(d.message || 'Ability upgraded!', true);
                    loadAbilitiesContent(); // Reload to show updated abilities
                } else {
                    showToastInline('Failed to upgrade ability: ' + (d.message || 'Unknown error'), false);
                }
            })
            .catch(function(e) { 
                console.error('[mypet.js] Error in upgradeAbilityInline:', e);
                showToastInline('Error: ' + e.message, false); 
            });
    };
    
    window.upgradeAdvMasteryInline = function(key) {
        console.log('[mypet.js] upgradeAdvMasteryInline called with key:', key);
        fetch('/api/pets/ability-tree/advantage-mastery', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({key: key})
        })
            .then(function(r){ return r.json(); })
            .then(function(d) {
                if (d.ok) {
                    showToastInline(d.message || 'Advantage mastery upgraded!', true);
                    loadAbilitiesContent(); // Reload to show updated mastery
                } else {
                    showToastInline('Failed to upgrade advantage mastery: ' + (d.message || 'Unknown error'), false);
                }
            })
            .catch(function(e) { 
                console.error('[mypet.js] Error in upgradeAdvMasteryInline:', e);
                showToastInline('Error: ' + e.message, false); 
            });
    };

    // ── Skill branch handlers ─────────────────────────────────────────────────
    window.selectSkillBranchInline = function() {
        window._abilityTreeSelectedNode = { type: 'skill_branch' };
        document.querySelectorAll('.at-selected').forEach(function(n){ n.classList.remove('at-selected'); });
        var dp = document.getElementById('at-details-panel-inline');
        if (dp) dp.innerHTML = renderDetailsInline();
    };

    window.selectSkillSlotInline = function(slotIdx) {
        window._abilityTreeSelectedNode = { type: 'skill_slot', slot: slotIdx };
        document.querySelectorAll('.at-selected').forEach(function(n){ n.classList.remove('at-selected'); });
        var dp = document.getElementById('at-details-panel-inline');
        if (dp) dp.innerHTML = renderDetailsInline();
    };

    window.drawSkillForSlotInline = function(slotIdx) {
        var pts = (window._abilityTreeState && window._abilityTreeState.available_points) || 0;
        if (pts < 1) {
            showToastInline('Not enough ability points — drawing costs 1 point.', false);
            return;
        }
        if (!confirm('Draw 5 new skill choices for slot ' + (slotIdx + 1) + '? This costs 1 ability point.')) return;

        fetch('/api/pets/skills/draw', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ slot: slotIdx, cross_element: false }),
        })
            .then(function(r){ return r.json(); })
            .then(function(d){
                if (!d.ok) {
                    showToastInline(d.message || 'Draw failed.', false);
                    return;
                }
                // Update local points count
                if (window._abilityTreeState && d.ability_points !== undefined) {
                    window._abilityTreeState.available_points = d.ability_points;
                }
                if (d.choices && d.choices.length) {
                    window._abilityTreeSelectedNode = { type: 'skill_choices', slot: slotIdx, choices: d.choices };
                    var dp = document.getElementById('at-details-panel-inline');
                    if (dp) dp.innerHTML = renderDetailsInline();
                } else {
                    showToastInline('No skills available to draw.', false);
                }
            })
            .catch(function(e){ showToastInline('Error: ' + e.message, false); });
    };

    window.equipSkillChoiceInline = function(skillId, slotIdx) {
        fetch('/api/pets/skills/equip', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ skill_id: skillId, slot: slotIdx }),
        })
        .then(function(r){ return r.json(); })
        .then(function(d){
            if (d.ok) {
                showToastInline(d.message, true);
                // Update skill state and re-render
                if (window._abilityTreeState) window._abilityTreeState.skill_state = d.skills;
                var tc = document.querySelector('.at-tree-container');
                if (tc && window._abilityTreeState) tc.innerHTML = renderTreeInline(window._abilityTreeState);
                window._abilityTreeSelectedNode = { type: 'skill_slot', slot: slotIdx };
                var dp = document.getElementById('at-details-panel-inline');
                if (dp) dp.innerHTML = renderDetailsInline();
            } else {
                showToastInline(d.message || 'Failed', false);
            }
        })
        .catch(function(e){ showToastInline('Error: ' + e.message, false); });
    };
}

// ── Toast notifications for inline version ────────────────────────────────────
function showToastInline(msg, ok) {
    var t = document.getElementById('at-toast-inline');
    if (!t) {
        // Toast container was removed (e.g. after DOM reload) — create a floating one
        t = document.createElement('div');
        t.id = 'at-toast-inline';
        document.body.appendChild(t);
    }
    t.textContent = msg;
    t.style.cssText = 'position:fixed;top:20px;right:20px;z-index:10000;padding:8px 16px;border-radius:6px;font-size:0.8rem;font-weight:700;' +
        (ok ? 'background:#2ecc71;color:#fff;' : 'background:#e74c3c;color:#fff;') +
        'box-shadow:0 4px 12px rgba(0,0,0,0.3);transition:all 0.3s ease;display:block;';
    setTimeout(function(){ if (t) t.style.cssText = 'display:none;'; }, 3000);
}

// ── Ability point purchase modals ─────────────────────────────────────────────
function _getOrCreateModal(id) {
    var m = document.getElementById(id);
    if (!m) {
        m = document.createElement('div');
        m.id = id;
        document.body.appendChild(m);
    }
    return m;
}

function showAbilityPurchaseConfirmModal(currentLevel, cost, newLevel) {
    var modal = _getOrCreateModal('at-purchase-modal');
    modal.innerHTML =
        '<div style="position:fixed;inset:0;background:rgba(0,0,0,0.75);z-index:9998;display:flex;align-items:center;justify-content:center;padding:16px">' +
            '<div style="background:linear-gradient(135deg,#111,#1a1a1a);border:1px solid rgba(255,215,0,0.35);border-radius:10px;padding:24px;max-width:380px;width:100%;box-shadow:0 8px 32px rgba(0,0,0,0.6)">' +
                '<div style="font-family:Orbitron,sans-serif;font-size:1rem;color:var(--gold-primary);font-weight:700;margin-bottom:16px;text-align:center">💎 Buy Ability Point</div>' +
                '<div style="background:rgba(255,215,0,0.07);border:1px solid rgba(255,215,0,0.2);border-radius:6px;padding:12px;margin-bottom:14px">' +
                    '<div style="display:flex;justify-content:space-between;font-size:0.8rem;margin-bottom:6px"><span style="color:var(--text-secondary)">Cost</span><span style="color:#e74c3c;font-weight:700">−' + cost + ' Levels</span></div>' +
                    '<div style="display:flex;justify-content:space-between;font-size:0.8rem;margin-bottom:6px"><span style="color:var(--text-secondary)">Level</span><span style="font-weight:700"><span style="color:var(--text-secondary)">' + currentLevel + '</span> → <span style="color:var(--gold-primary)">' + newLevel + '</span></span></div>' +
                    '<div style="display:flex;justify-content:space-between;font-size:0.8rem"><span style="color:var(--text-secondary)">Reward</span><span style="color:#4caf50;font-weight:700">+1 Ability Point</span></div>' +
                '</div>' +
                '<div style="background:rgba(231,76,60,0.1);border:1px solid rgba(231,76,60,0.3);border-radius:6px;padding:10px;margin-bottom:18px;font-size:0.75rem;color:#e74c3c">' +
                    '⚠️ Spending levels will reduce your stats proportionally. This cannot be undone.' +
                '</div>' +
                '<div style="display:flex;gap:10px">' +
                    '<button onclick="document.getElementById(\'at-purchase-modal\').style.display=\'none\'" style="flex:1;background:rgba(80,80,80,0.4);border:1px solid rgba(255,255,255,0.15);border-radius:6px;color:rgba(255,255,255,0.7);font-size:0.8rem;font-weight:700;padding:10px;cursor:pointer">Cancel</button>' +
                    '<button id="at-purchase-confirm-btn" onclick="window._confirmAbilityPointPurchase()" style="flex:1;background:linear-gradient(135deg,var(--gold-primary),#ffb300);border:none;border-radius:6px;color:#000;font-size:0.8rem;font-weight:700;padding:10px;cursor:pointer;transition:all 0.2s">✅ Confirm Purchase</button>' +
                '</div>' +
            '</div>' +
        '</div>';
    modal.style.display = 'block';
}

function showAbilityPurchaseResultModal(ok, message, tree) {
    var modal = _getOrCreateModal('at-purchase-modal');
    // Parse stat losses out of the message for nicer display
    var statMatch = message.match(/Stats reduced: ([^)]+)/);
    var statLines = '';
    if (statMatch) {
        statMatch[1].split(',').forEach(function(s) {
            var parts = s.trim().split(':');
            if (parts.length === 2) {
                statLines += '<div style="display:flex;justify-content:space-between;font-size:0.78rem;margin-bottom:4px">' +
                    '<span style="color:var(--text-secondary)">' + parts[0].trim() + '</span>' +
                    '<span style="color:#e74c3c;font-weight:700">' + parts[1].trim() + '</span>' +
                '</div>';
            }
        });
    }
    var newLevel = tree ? (tree.current_level || '') : '';
    var newPts   = tree ? (tree.available_points || '') : '';
    modal.innerHTML =
        '<div style="position:fixed;inset:0;background:rgba(0,0,0,0.75);z-index:9998;display:flex;align-items:center;justify-content:center;padding:16px">' +
            '<div style="background:linear-gradient(135deg,#111,#1a1a1a);border:1px solid ' + (ok ? 'rgba(46,204,113,0.4)' : 'rgba(231,76,60,0.4)') + ';border-radius:10px;padding:24px;max-width:380px;width:100%;box-shadow:0 8px 32px rgba(0,0,0,0.6)">' +
                '<div style="font-size:2rem;text-align:center;margin-bottom:10px">' + (ok ? '✅' : '❌') + '</div>' +
                '<div style="font-family:Orbitron,sans-serif;font-size:0.95rem;color:' + (ok ? '#2ecc71' : '#e74c3c') + ';font-weight:700;margin-bottom:14px;text-align:center">' + (ok ? 'Point Purchased!' : 'Purchase Failed') + '</div>' +
                (ok && (newLevel || newPts) ?
                    '<div style="background:rgba(46,204,113,0.07);border:1px solid rgba(46,204,113,0.2);border-radius:6px;padding:12px;margin-bottom:12px">' +
                        (newLevel ? '<div style="display:flex;justify-content:space-between;font-size:0.8rem;margin-bottom:6px"><span style="color:var(--text-secondary)">New Level</span><span style="color:var(--gold-primary);font-weight:700">' + newLevel + '</span></div>' : '') +
                        (newPts   ? '<div style="display:flex;justify-content:space-between;font-size:0.8rem"><span style="color:var(--text-secondary)">Ability Points</span><span style="color:#4caf50;font-weight:700">' + newPts + '</span></div>' : '') +
                    '</div>'
                : '') +
                (statLines ?
                    '<div style="background:rgba(231,76,60,0.07);border:1px solid rgba(231,76,60,0.2);border-radius:6px;padding:12px;margin-bottom:14px">' +
                        '<div style="font-size:0.72rem;color:var(--text-secondary);margin-bottom:8px;font-weight:700">STAT CHANGES</div>' +
                        statLines +
                    '</div>'
                : (!ok ? '<div style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:14px;text-align:center">' + message + '</div>' : '')) +
                '<button onclick="document.getElementById(\'at-purchase-modal\').style.display=\'none\'" style="width:100%;background:linear-gradient(135deg,rgba(255,215,0,0.15),rgba(255,140,0,0.1));border:1px solid rgba(255,215,0,0.3);border-radius:6px;color:var(--gold-primary);font-size:0.8rem;font-weight:700;padding:10px;cursor:pointer">Close</button>' +
            '</div>' +
        '</div>';
    modal.style.display = 'block';
}


// ══════════════════════════════════════════════════════════════════════════════
// ── Absorb Tab ────────────────────────────────────────────────────────────────
// ══════════════════════════════════════════════════════════════════════════════

// Use document.getElementById directly — this code lives outside the IIFE
// that defines el() and _absEsc(), so we can't use them here.
function _absEl(id) { return document.getElementById(id); }
function _absEsc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

// Military emoji paths — /static/Emojis/Military/
var _ABSORB_EMOJI = {
    soldier:  { img: '/static/Emojis/Military/soldier.png'  },
    tank:     { img: '/static/Emojis/Military/tank.png'     },
    jet:      { img: '/static/Emojis/Military/jet.png'      },
    ship:     { img: '/static/Emojis/Military/ship.png'     },
    missile:  { img: '/static/Emojis/Military/missile.png'  },
    bomb:     { img: '/static/Emojis/Military/bomb.png'     },
    wars:     { img: '/static/Emojis/Military/wars.png'     },
};

var _absorbData = null;  // cached status response

function _mpLoadAbsorb() {
    var loading  = _absEl('absorb-loading');
    var noNation = _absEl('absorb-no-nation');
    var content  = _absEl('absorb-content');
    if (!loading || !content) return;

    loading.style.display  = '';
    if (noNation) noNation.style.display = 'none';
    content.style.display  = 'none';

    fetch('/api/pets/absorb/status')
        .then(function(r) { return r.json(); })
        .then(function(d) {
            loading.style.display = 'none';
            if (!d.linked) {
                if (noNation) noNation.style.display = '';
                return;
            }
            _absorbData = d;
            content.style.display = '';
            _renderAbsorbContent(d);
        })
        .catch(function(err) {
            loading.style.display = 'none';
            if (content) {
                content.style.display = '';
                content.innerHTML = '<div class="mp-battle-card" style="color:#e74c3c;font-size:0.85rem">Failed to load war data: ' + _absEsc(err.message) + '</div>';
            }
        });
}

function _renderAbsorbContent(d) {
    var avail    = d.available   || {};
    var absorbed = d.absorbed    || {};
    var total    = d.total       || {};
    var preview  = d.xp_preview  || {};
    var isLocked = d.locked      || false;
    var nationId = d.nation_id   || null;

    // ── Nation lock banner ────────────────────────────────────────────────────
    var lockBanner = _absEl('absorb-lock-banner');
    if (lockBanner) {
        if (isLocked) {
            lockBanner.style.display = '';
            lockBanner.innerHTML =
                '<div style="display:flex;align-items:center;gap:8px;font-size:0.78rem;color:rgba(255,215,0,0.85)">' +
                '<span style="font-size:1rem">🔒</span>' +
                '<span>Nation <strong style="color:var(--gold-primary)">#' + nationId + '</strong> is permanently bound to this pet. ' +
                'Wins and kills from this nation only.</span>' +
                '</div>';
        } else {
            lockBanner.style.display = '';
            lockBanner.innerHTML =
                '<div style="display:flex;align-items:center;gap:8px;font-size:0.78rem;color:rgba(255,200,50,0.75)">' +
                '<span style="font-size:1rem">⚠️</span>' +
                '<span>Nation <strong style="color:var(--gold-primary)">#' + nationId + '</strong> is currently linked. ' +
                'Once you absorb, this nation is <strong>permanently locked</strong> to your pet.</span>' +
                '</div>';
        }
    }

    // ── Wins box ──────────────────────────────────────────────────────────────
    var winsBadge = _absEl('absorb-wins-badge');
    if (winsBadge) {
        winsBadge.textContent = absorbed.wins + ' already absorbed';
    }

    var winsAvail = avail.wins || 0;
    var winsTotal = total.wins || 0;

    // Build soul/spirit emoji grid — one icon per available win, randomly soul or spirit
    var soulsContainer = _absEl('absorb-wins-souls');
    if (soulsContainer) {
        if (winsAvail <= 0) {
            soulsContainer.innerHTML = '<span style="font-size:0.75rem;color:var(--text-secondary)">No new wins to absorb</span>';
        } else {
            var soulsHtml = '';
            for (var wi = 0; wi < winsAvail; wi++) {
                var sImg = Math.random() < 0.5 ? '/static/Emojis/Floaters/soul.png' : '/static/Emojis/Floaters/spirit.png';
                soulsHtml += '<img src="' + sImg + '" class="absorb-soul-icon" data-idx="' + wi + '" ' +
                    'style="width:24px;height:24px;object-fit:contain;flex-shrink:0;' +
                    'filter:drop-shadow(0 0 4px rgba(255,215,0,0.6))" ' +
                    'onerror="this.src=\'/static/Emojis/Pets/Deco/XP.png\'">';
            }
            soulsContainer.innerHTML = soulsHtml;
        }
    }

    var winsXp = _absEl('absorb-wins-xp-preview');
    if (winsXp) {
        var xpW = preview.wins || 0;
        winsXp.innerHTML = xpW > 0
            ? '⚡ <strong style="color:var(--gold-primary)">' + xpW.toLocaleString() + ' XP</strong> ready to absorb'
            : '<span style="color:var(--text-secondary)">No new wins to absorb</span>';
    }

    var winsBtn = _absEl('absorb-wins-btn');
    if (winsBtn) {
        winsBtn.disabled = winsAvail <= 0;
        winsBtn.style.opacity = winsAvail <= 0 ? '0.45' : '1';
    }

    // ── Kills box ─────────────────────────────────────────────────────────────
    var killsBadge = _absEl('absorb-kills-badge');
    if (killsBadge) {
        var totalAbsorbed = (absorbed.soldiers||0) + (absorbed.tanks||0) + (absorbed.aircraft||0) +
                            (absorbed.ships||0) + (absorbed.missiles||0) + (absorbed.nukes||0);
        killsBadge.textContent = totalAbsorbed.toLocaleString() + ' already absorbed';
    }

    var killsStats = _absEl('absorb-kills-stats');
    if (killsStats) {
        var unitDefs = [
            { key:'soldiers', label:'Soldiers', emojiImg:'/static/Emojis/Military/soldier.png', xpKey:'soldiers' },
            { key:'tanks',    label:'Tanks',    emojiImg:'/static/Emojis/Military/tank.png',    xpKey:'tanks'    },
            { key:'aircraft', label:'Aircraft', emojiImg:'/static/Emojis/Military/jet.png',     xpKey:'aircraft' },
            { key:'ships',    label:'Ships',    emojiImg:'/static/Emojis/Military/ship.png',    xpKey:'ships'    },
            { key:'missiles', label:'Missiles', emojiImg:'/static/Emojis/Military/missile.png', xpKey:'missiles' },
            { key:'nukes',    label:'Nukes',    emojiImg:'/static/Emojis/Military/bomb.png',    xpKey:'nukes'    },
        ];
        var killsHtml = '';
        unitDefs.forEach(function(u) {
            var cnt   = avail[u.key] || 0;
            var tot   = total[u.key] || 0;
            var xpAmt = preview[u.xpKey] || 0;
            var hasUnits = cnt > 0;
            // Each card is toggleable — selected by default if it has units
            killsHtml +=
                '<div class="col-6 col-md-4">' +
                '<div class="mp-mini-stat-card absorb-unit-card' + (hasUnits ? ' absorb-unit-selected' : '') + '" ' +
                'id="absorb-unit-' + u.key + '" ' +
                'data-unit="' + u.key + '" ' +
                'onclick="window._mpToggleUnit(\'' + u.key + '\')" ' +
                'style="text-align:center;padding:8px 6px;cursor:' + (hasUnits ? 'pointer' : 'default') + ';' +
                'transition:all 0.15s;' +
                (hasUnits ? 'border-color:rgba(120,120,255,0.7);box-shadow:0 0 8px rgba(100,100,255,0.3);' : 'opacity:0.45;') + '">' +
                '<img src="' + u.emojiImg + '" style="width:28px;height:28px;object-fit:contain;margin-bottom:3px" onerror="this.style.display=\'none\'">' +
                '<div style="font-size:0.65rem;color:var(--text-secondary);margin-bottom:2px">' + u.label + '</div>' +
                '<div style="font-size:1.1rem;font-weight:800;color:' + (hasUnits ? 'var(--gold-primary)' : 'rgba(255,255,255,0.3)') + ';font-family:Orbitron,sans-serif">' + cnt.toLocaleString() + '</div>' +
                '<div style="font-size:0.58rem;color:rgba(255,255,255,0.3)">' + tot.toLocaleString() + ' total</div>' +
                (xpAmt > 0 ? '<div style="font-size:0.6rem;color:#4caf50;margin-top:2px">+' + xpAmt.toLocaleString() + ' XP</div>' : '') +
                '<div style="font-size:0.55rem;margin-top:4px;font-weight:700;' + (hasUnits ? 'color:rgba(120,120,255,0.9)' : 'color:rgba(255,255,255,0.2)') + '">' +
                (hasUnits ? '&#10003; Selected' : 'None') + '</div>' +
                '</div></div>';
        });
        killsStats.innerHTML = killsHtml;
    }

    var killsXp = _absEl('absorb-kills-xp-preview');
    if (killsXp) {
        var totalKillXp = (preview.soldiers||0) + (preview.tanks||0) + (preview.aircraft||0) +
                          (preview.ships||0) + (preview.missiles||0) + (preview.nukes||0);
        killsXp.innerHTML = totalKillXp > 0
            ? '&#9889; <strong style="color:var(--gold-primary)">' + totalKillXp.toLocaleString() + ' XP</strong> ready to absorb &mdash; click units to select/deselect'
            : '<span style="color:var(--text-secondary)">No new kills to absorb</span>';
    }

    var killsBtn = _absEl('absorb-kills-btn');
    if (killsBtn) {
        var anyKills = ['soldiers','tanks','aircraft','ships','missiles','nukes'].some(function(k){ return (avail[k]||0) > 0; });
        killsBtn.disabled = !anyKills;
        killsBtn.style.opacity = anyKills ? '1' : '0.45';
    }
}

// ── Win absorb animation: feed soul/spirit icons from the grid to the pet ─────
function _mpAbsorbWinsAnimation(onComplete) {
    var petImgEl = document.querySelector('#my-pet-header .mp-pet-img');
    var icons    = document.querySelectorAll('#absorb-wins-souls .absorb-soul-icon');

    if (!petImgEl || icons.length === 0) { onComplete(); return; }

    var petRect  = petImgEl.getBoundingClientRect();
    var targetX  = petRect.left + petRect.width  / 2;
    var targetY  = petRect.top  + petRect.height / 2;

    var total    = icons.length;
    var completed = 0;

    // Inject keyframe once
    if (!document.getElementById('absorb-soul-style')) {
        var s = document.createElement('style');
        s.id = 'absorb-soul-style';
        s.textContent = '@keyframes absorbSoulPulse{0%,100%{filter:drop-shadow(0 0 5px gold) brightness(1.3)}50%{filter:drop-shadow(0 0 16px gold) brightness(2)}}';
        document.head.appendChild(s);
    }

    icons.forEach(function(icon, idx) {
        setTimeout(function() {
            // Get the icon's current position in the grid
            var rect   = icon.getBoundingClientRect();
            var startX = rect.left + rect.width  / 2;
            var startY = rect.top  + rect.height / 2;

            // Hide the grid icon immediately so it looks like it left the row
            icon.style.visibility = 'hidden';

            // Create a flying clone
            var node = document.createElement('img');
            node.src = icon.src;
            node.style.cssText = 'position:fixed;width:24px;height:24px;object-fit:contain;pointer-events:none;z-index:9999;animation:absorbSoulPulse 0.5s ease infinite;';
            node.style.left = (startX - 12) + 'px';
            node.style.top  = (startY - 12) + 'px';
            document.body.appendChild(node);

            var startTime = null;
            var dur  = 420 + Math.random() * 160;
            var arcH = 60 + Math.random() * 80;

            function step(ts) {
                if (!startTime) startTime = ts;
                var p  = Math.min((ts - startTime) / dur, 1);
                var ep = p * p;
                var cx = startX + (targetX - startX) * ep;
                var cy = startY + (targetY - startY) * ep - Math.sin(p * Math.PI) * arcH;
                var sc = 1.1 - p * 0.65;
                node.style.left      = (cx - 12) + 'px';
                node.style.top       = (cy - 12) + 'px';
                node.style.opacity   = p < 0.75 ? '1' : String(1 - (p - 0.75) / 0.25);
                node.style.transform = 'scale(' + sc + ')';
                if (p < 1) {
                    requestAnimationFrame(step);
                } else {
                    node.remove();
                    petImgEl.style.transition = 'transform 0.07s ease-out';
                    petImgEl.style.transform  = 'scale(1.3)';
                    setTimeout(function() { petImgEl.style.transform = 'scale(1)'; }, 110);
                    completed++;
                    if (completed === total) {
                        setTimeout(function() {
                            petImgEl.style.transition = 'transform 0.12s ease-out';
                            petImgEl.style.transform  = 'scale(1.5)';
                            setTimeout(function() {
                                petImgEl.style.transform  = 'scale(1)';
                                petImgEl.style.transition = '';
                                onComplete();
                            }, 200);
                        }, 60);
                    }
                }
            }
            requestAnimationFrame(step);
        }, idx * 70);
    });
}

// ── Kill absorb animation: military unit emojis ───────────────────────────────

// ── Kill absorb animation: steady stream of one unit type to the pet ──────────
// count = total units, imgSrc = emoji path for that unit type
function _mpAbsorbKillsAnimation(count, imgSrc, onComplete) {
    var petImgEl = document.querySelector('#my-pet-header .mp-pet-img');
    if (!petImgEl || count <= 0) { onComplete(); return; }

    var petRect = petImgEl.getBoundingClientRect();
    var targetX = petRect.left + petRect.width  / 2;
    var targetY = petRect.top  + petRect.height / 2;

    // Cap at 120 visible emojis — each represents (count/120) units
    var visible  = Math.min(count, 120);
    var interval = 18; // ms between launches — fast but visible
    var completed = 0;

    function launchOne() {
        var node = document.createElement('img');
        node.src = imgSrc;
        node.onerror = function() { this.src = '/static/Emojis/Military/soldier.png'; };
        node.style.cssText = 'position:fixed;width:22px;height:22px;object-fit:contain;pointer-events:none;z-index:9999;filter:drop-shadow(0 0 6px rgba(100,180,255,0.9));';
        var startX = window.innerWidth * 0.1 + Math.random() * window.innerWidth * 0.8;
        var startY = window.innerHeight * 0.75 + Math.random() * (window.innerHeight * 0.2);
        node.style.left = startX + 'px';
        node.style.top  = startY + 'px';
        document.body.appendChild(node);

        var startTime = null;
        var dur  = 350 + Math.random() * 120;
        var arcH = 50 + Math.random() * 60;

        function step(ts) {
            if (!startTime) startTime = ts;
            var p  = Math.min((ts - startTime) / dur, 1);
            var ep = p * p;
            var cx = startX + (targetX - startX) * ep;
            var cy = startY + (targetY - startY) * ep - Math.sin(p * Math.PI) * arcH;
            var sc = 1 - p * 0.55;
            node.style.left      = (cx - 11) + 'px';
            node.style.top       = (cy - 11) + 'px';
            node.style.opacity   = p < 0.8 ? '1' : String(1 - (p - 0.8) / 0.2);
            node.style.transform = 'scale(' + sc + ')';
            if (p < 1) {
                requestAnimationFrame(step);
            } else {
                node.remove();
                petImgEl.style.transition = 'transform 0.05s ease-out';
                petImgEl.style.transform  = 'scale(1.18)';
                setTimeout(function() { petImgEl.style.transform = 'scale(1)'; }, 80);
                completed++;
                if (completed === visible) {
                    setTimeout(function() {
                        petImgEl.style.transition = 'transform 0.12s ease-out';
                        petImgEl.style.transform  = 'scale(1.5)';
                        setTimeout(function() {
                            petImgEl.style.transform  = 'scale(1)';
                            petImgEl.style.transition = '';
                            onComplete();
                        }, 200);
                    }, 60);
                }
            }
        }
        requestAnimationFrame(step);
    }

    for (var i = 0; i < visible; i++) {
        setTimeout(launchOne, i * interval);
    }
}

// ── Level-up result HTML ───────────────────────────────────────────────────────
function _absorbLevelUpHtml(d) {
    if (!d || !d.leveled_up || !d.level_data) return '';
    var ld     = d.level_data || {};
    var oldLvl = ld.old_level || '?';
    var newLvl = ld.new_level || '?';
    var gains  = ld.gains     || {};

    // Build stat gains rows
    var statImgs = { ATT:'/static/Emojis/Pets/Deco/ATT.png', DEF:'/static/Emojis/Pets/Deco/DEF.png',
                     INT:'/static/Emojis/Pets/Deco/INT.png', DEX:'/static/Emojis/Pets/Deco/DEX.png',
                     HAP:'/static/Emojis/Pets/Deco/HAP.png', ENE:'/static/Emojis/Pets/Deco/ENE.png' };
    var gainRows = '';
    Object.keys(gains).forEach(function(stat) {
        var val = gains[stat];
        if (!val) return;
        gainRows +=
            '<div style="display:flex;align-items:center;gap:6px;font-size:0.75rem;margin-bottom:2px">' +
            '<img src="' + (statImgs[stat] || '') + '" style="width:16px;height:16px;object-fit:contain" onerror="this.style.display=\'none\'">' +
            '<span style="color:var(--text-secondary)">' + stat + '</span>' +
            '<span style="color:#4caf50;font-weight:700">+' + val + '</span>' +
            '</div>';
    });

    var levelsGained = (typeof newLvl === 'number' && typeof oldLvl === 'number') ? (newLvl - oldLvl) : '';

    return '<div style="background:linear-gradient(135deg,rgba(255,215,0,0.15),rgba(255,140,0,0.08));' +
           'border:1px solid rgba(255,215,0,0.6);border-radius:8px;padding:12px 14px;margin-top:8px">' +
           '<div style="font-family:Orbitron,sans-serif;color:var(--gold-primary);font-size:1rem;font-weight:800;margin-bottom:6px">' +
           '&#127881; LEVEL UP' + (levelsGained > 1 ? ' x' + levelsGained : '') + '!</div>' +
           '<div style="font-size:0.85rem;color:rgba(255,255,255,0.85);margin-bottom:8px">' +
           'Level <span style="color:var(--gold-primary);font-weight:700">' + oldLvl + '</span>' +
           ' &rarr; <span style="color:var(--gold-primary);font-weight:700;font-size:1rem">' + newLvl + '</span>' +
           '</div>' +
           (gainRows ? '<div style="border-top:1px solid rgba(255,215,0,0.2);padding-top:8px;margin-top:4px">' +
           '<div style="font-size:0.65rem;color:var(--text-secondary);margin-bottom:4px;font-weight:700;letter-spacing:0.05em">STAT INCREASES</div>' +
           gainRows + '</div>' : '') +
           '</div>';
}

// ── Toggle unit card selection ────────────────────────────────────────────────
window._mpToggleUnit = function(unitKey) {
    var card = _absEl('absorb-unit-' + unitKey);
    if (!card || card.style.cursor === 'default') return;
    var isSelected = card.classList.contains('absorb-unit-selected');
    var lbl = card.querySelector('.absorb-unit-sel-label');
    if (isSelected) {
        card.classList.remove('absorb-unit-selected');
        card.style.borderColor = 'rgba(255,255,255,0.1)';
        card.style.boxShadow   = 'none';
        if (lbl) lbl.textContent = 'Click to select';
    } else {
        card.classList.add('absorb-unit-selected');
        card.style.borderColor = 'rgba(120,120,255,0.7)';
        card.style.boxShadow   = '0 0 8px rgba(100,100,255,0.3)';
        if (lbl) lbl.textContent = '\u2713 Selected';
    }
    _absorbUpdateKillsPreview();
};

function _absorbGetSelectedUnits() {
    var selected = [];
    ['soldiers','tanks','aircraft','ships','missiles','nukes'].forEach(function(k) {
        var card = _absEl('absorb-unit-' + k);
        if (card && card.classList.contains('absorb-unit-selected')) selected.push(k);
    });
    return selected;
}

function _absorbUpdateKillsPreview() {
    if (!_absorbData) return;
    var preview  = _absorbData.xp_preview || {};
    var selected = _absorbGetSelectedUnits();
    var totalXp  = 0;
    selected.forEach(function(k) { totalXp += (preview[k] || 0); });
    var killsXp = _absEl('absorb-kills-xp-preview');
    if (killsXp) {
        killsXp.innerHTML = totalXp > 0
            ? '&#9889; <strong style="color:var(--gold-primary)">' + totalXp.toLocaleString() + ' XP</strong> from ' + selected.length + ' selected type' + (selected.length !== 1 ? 's' : '')
            : '<span style="color:var(--text-secondary)">Select units to absorb</span>';
    }
    var killsBtn = _absEl('absorb-kills-btn');
    if (killsBtn) {
        killsBtn.disabled      = selected.length === 0;
        killsBtn.style.opacity = selected.length > 0 ? '1' : '0.45';
    }
}

// ── Absorb Wins ───────────────────────────────────────────────────────────────
window._mpAbsorbWins = async function() {
    var btn    = _absEl('absorb-wins-btn');
    var result = _absEl('absorb-wins-result');
    if (btn) btn.disabled = true;
    if (result) result.innerHTML = '<span style="color:var(--text-secondary);font-size:0.8rem">Absorbing...</span>';

    try {
        var resp = await fetch('/api/pets/absorb/wins', { method: 'POST' });
        var d    = await resp.json();

        if (!resp.ok || d.error) {
            if (result) result.innerHTML = '<span style="color:#e74c3c;font-size:0.82rem">&#10060; ' + _absEsc(d.error || 'Failed') + '</span>';
            if (btn) { btn.disabled = false; btn.style.opacity = '1'; }
            return;
        }

        if ((d.wins_absorbed || 0) <= 0) {
            if (result) result.innerHTML = '<span style="color:var(--text-secondary);font-size:0.82rem">No new wins to absorb.</span>';
            if (btn) btn.disabled = true;
            return;
        }

        _mpAbsorbWinsAnimation(function() {
            if (result) {
                result.innerHTML =
                    '<div class="mp-battle-card" style="border-color:rgba(76,175,80,0.4);margin-top:8px">' +
                    '<div style="color:#4caf50;font-weight:700;font-size:0.9rem;margin-bottom:4px">&#9989; ' + _absEsc(d.message) + '</div>' +
                    '<div style="font-size:0.78rem;color:var(--text-secondary)">+' + (d.xp_gained||0).toLocaleString() + ' XP absorbed</div>' +
                    _absorbLevelUpHtml(d) +
                    '</div>';
            }
            if (d.pet) { _pet = d.pet; renderPetCard(d.pet); }
            _mpLoadAbsorb();
        });

    } catch(err) {
        if (result) result.innerHTML = '<span style="color:#e74c3c;font-size:0.82rem">&#10060; ' + _absEsc(err.message) + '</span>';
        if (btn) { btn.disabled = false; btn.style.opacity = '1'; }
    }
};

// ── Absorb Kills (per selected unit type) ────────────────────────────────────
window._mpAbsorbKills = async function() {
    var btn    = _absEl('absorb-kills-btn');
    var result = _absEl('absorb-kills-result');

    var selected = _absorbGetSelectedUnits();
    if (selected.length === 0) {
        if (result) result.innerHTML = '<span style="color:var(--text-secondary);font-size:0.82rem">Select at least one unit type first.</span>';
        return;
    }

    if (btn) btn.disabled = true;
    if (result) result.innerHTML = '<span style="color:var(--text-secondary);font-size:0.8rem">Absorbing...</span>';

    // Unit emoji map for animation
    var unitImgMap = {
        soldiers: '/static/Emojis/Military/soldier.png',
        tanks:    '/static/Emojis/Military/tank.png',
        aircraft: '/static/Emojis/Military/jet.png',
        ships:    '/static/Emojis/Military/ship.png',
        missiles: '/static/Emojis/Military/missile.png',
        nukes:    '/static/Emojis/Military/bomb.png',
    };

    // Absorb each selected unit type sequentially
    var allBreakdown = {};
    var allAbsorbed  = {};
    var totalXpGained = 0;
    var anyLevelUp   = false;
    var lastLevelData = null;
    var lastPet       = null;
    var errors        = [];

    async function absorbOne(unitKey) {
        try {
            var resp = await fetch('/api/pets/absorb/kills', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ unit_type: unitKey })
            });
            var d = await resp.json();
            if (!resp.ok || d.error) { errors.push(unitKey + ': ' + (d.error || 'failed')); return; }
            var cnt = (d.kills_absorbed || {})[unitKey] || 0;
            if (cnt <= 0) return;

            allAbsorbed[unitKey]  = cnt;
            allBreakdown[unitKey] = (d.xp_breakdown || {})[unitKey] || 0;
            totalXpGained += (d.xp_gained || 0);
            if (d.leveled_up) { anyLevelUp = true; lastLevelData = d.level_data; }
            if (d.pet) lastPet = d.pet;

            // Run streaming animation for this unit type
            await new Promise(function(resolve) {
                _mpAbsorbKillsAnimation(cnt, unitImgMap[unitKey] || unitImgMap.soldiers, resolve);
            });
        } catch(e) {
            errors.push(unitKey + ': ' + e.message);
        }
    }

    for (var i = 0; i < selected.length; i++) {
        await absorbOne(selected[i]);
    }

    // Build result card
    var unitLabels = { soldiers:'Soldiers', tanks:'Tanks', aircraft:'Aircraft', ships:'Ships', missiles:'Missiles', nukes:'Nukes' };
    var bkHtml = Object.keys(allAbsorbed).map(function(k) {
        return '<div style="display:flex;justify-content:space-between;font-size:0.75rem;color:var(--text-secondary);margin-bottom:2px">' +
            '<span>' + (unitLabels[k]||k) + ': ' + (allAbsorbed[k]||0).toLocaleString() + '</span>' +
            '<span style="color:#4caf50">+' + (allBreakdown[k]||0).toLocaleString() + ' XP</span>' +
            '</div>';
    }).join('');

    // Build a synthetic level_data that spans the full range if multiple unit types leveled up
    var fakeD = { leveled_up: anyLevelUp, level_data: lastLevelData };

    if (result) {
        result.innerHTML =
            '<div class="mp-battle-card" style="border-color:rgba(100,100,255,0.4);margin-top:8px">' +
            '<div style="color:#7986cb;font-weight:700;font-size:0.9rem;margin-bottom:6px">&#9989; Absorbed!</div>' +
            bkHtml +
            '<div style="font-size:0.82rem;color:var(--gold-primary);font-weight:700;margin-top:6px;border-top:1px solid rgba(255,255,255,0.1);padding-top:6px">Total: +' + totalXpGained.toLocaleString() + ' XP</div>' +
            _absorbLevelUpHtml(fakeD) +
            (errors.length ? '<div style="font-size:0.7rem;color:#e74c3c;margin-top:4px">Errors: ' + errors.join(', ') + '</div>' : '') +
            '</div>';
    }

    if (lastPet) { _pet = lastPet; renderPetCard(lastPet); }
    _mpLoadAbsorb();
};

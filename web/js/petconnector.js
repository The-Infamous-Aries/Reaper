(function () {
'use strict';

// ── Enhanced State Variables ──────────────────────────────────────────────────
var _users       = [];   // enriched user+pet objects from API
var _currentUser = null; // entry where is_current_user === true
var _detailUserId = null; // which user's detail panel is open
var _giftTargetId = null; // target for the gift overlay
var _filteredUsers = []; // users after applying search/filter
var _currentSort = 'username'; // current sort field
var _sortAsc = true; // sort direction
var _currentRelFilter = 'all'; // relationship filter
var _compareMode = false; // compare mode active
var _compareSelected = []; // selected pets for comparison (max 2)
var _leaderboardSort = 'level'; // current leaderboard sort
var _PET_INFO_CACHE = null; // cached pet species info

// ── Helpers ────────────────────────────────────────────────────────────────
function esc(s) {
    return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : ''; }
function el(id) { return document.getElementById(id); }
function petImg(sp)  { return '/static/Emojis/Pets/' + (sp||'Cat') + '.png'; }
function petBadgeImg(pet) { return (pet && pet.badge_url) ? pet.badge_url : petImg((pet && pet.species) || 'Cat'); }
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

// ── Enhanced Relationship helpers with animations ─────────────────────────────
var REL = {
    best_friend: { 
        label:'Best Friend', 
        icon:'💚', 
        color:'#4caf50', 
        btnCls:'pc-rel-green',
        emoji:'💚',
        animation:'pcHeartbeat'
    },
    friend: { 
        label:'Friend', 
        icon:'💙', 
        color:'#2196f3', 
        btnCls:'pc-rel-blue',
        emoji:'💙',
        animation:'pcPulse'
    },
    foe: { 
        label:'Foe', 
        icon:'🧡', 
        color:'#ff9800', 
        btnCls:'pc-rel-orange',
        emoji:'🧡',
        animation:'pcShake'
    },
    enemy: { 
        label:'Enemy', 
        icon:'❤️', 
        color:'#f44336', 
        btnCls:'pc-rel-red',
        emoji:'❤️',
        animation:'pcIntensePulse'
    },
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

// ── Enhanced Search & Filter Functions ────────────────────────────────────────
function pcApplyFilters() {
    var searchTerm = (el('pc-search').value || '').toLowerCase();
    var speciesFilter = el('pc-species-filter').value.toLowerCase();
    var elementFilter = el('pc-element-filter').value.toLowerCase();
    var categoryFilter = el('pc-category-filter').value.toLowerCase();
    
    _filteredUsers = _users.filter(function(user) {
        var pet = user.pet || {};
        var username = (user.username || '').toLowerCase();
        var petName = (pet.name || '').toLowerCase();
        var species = (pet.species || '').toLowerCase();
        var element1 = (pet.element || '').toLowerCase();
        var element2 = (pet.element2 || '').toLowerCase();
        var category = (pet.category || '').toLowerCase();
        
        // Search filter
        if (searchTerm && !username.includes(searchTerm) && !petName.includes(searchTerm) && 
            !species.includes(searchTerm) && !element1.includes(searchTerm) && !element2.includes(searchTerm)) {
            return false;
        }
        
        // Species filter
        if (speciesFilter && species !== speciesFilter) return false;
        
        // Element filter
        if (elementFilter && element1 !== elementFilter && element2 !== elementFilter) return false;
        
        // Category filter
        if (categoryFilter && category !== categoryFilter) return false;
        
        // Relationship filter
        if (_currentRelFilter !== 'all') {
            if (_currentRelFilter === 'none') {
                if (user.relationship) return false;
            } else {
                if (user.relationship !== _currentRelFilter) return false;
            }
        }
        
        return true;
    });
    
    // Apply sorting
    pcSortUsers();
    renderPets();
    updateBadge();
}

function pcSortUsers() {
    _filteredUsers.sort(function(a, b) {
        var aVal = pcGetSortValue(a, _currentSort);
        var bVal = pcGetSortValue(b, _currentSort);
        
        if (typeof aVal === 'string') {
            aVal = aVal.toLowerCase();
            bVal = bVal.toLowerCase();
        }
        
        var result = aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
        return _sortAsc ? result : -result;
    });
}

function pcGetSortValue(user, sortKey) {
    var pet = user.pet || {};
    var stats = pet.computed_stats || {};
    
    switch (sortKey) {
        case 'username': return user.username || 'Unknown';
        case 'level': return pet.level || 1;
        case 'hp': return stats.hp || stats.max_health || 100;
        case 'attack': return stats.attack || 10;
        case 'defense': return stats.defense || 5;
        case 'xp': return pet.experience || 0;
        case 'total_xp': return pet.total_xp || 0;
        case 'species': return pet.species || 'Cat';
        case 'element': return pet.element || 'basic';
        case 'relationship': 
            var relOrder = {best_friend: 0, friend: 1, foe: 2, enemy: 3, null: 4};
            return relOrder[user.relationship] || 4;
        default: return 0;
    }
}

function pcSetRelFilter(relType) {
    _currentRelFilter = relType;
    
    // Update active tab
    var tabs = document.querySelectorAll('.pc-filter-tab');
    tabs.forEach(function(tab) {
        tab.classList.remove('pc-filter-active');
        if (tab.dataset.rel === relType) {
            tab.classList.add('pc-filter-active');
        }
    });
    
    pcApplyFilters();
}

function pcToggleSortDir() {
    _sortAsc = !_sortAsc;
    el('pc-sort-dir').textContent = _sortAsc ? '↓' : '↑';
    pcApplyFilters();
}

// ── Compare Mode Functions ─────────────────────────────────────────────────────
window.pcToggleCompareMode = function() {
    _compareMode = !_compareMode;
    _compareSelected = [];

    var btn     = el('pc-compare-mode-btn');
    var clearBtn = el('pc-clear-compare-btn');
    var icon    = el('pc-compare-icon');

    if (_compareMode) {
        btn.style.background  = 'rgba(76,175,80,0.2)';
        btn.style.borderColor = '#4caf50';
        btn.style.color       = '#4caf50';
        icon.textContent      = '✓';
        clearBtn.style.display = 'inline-block';
        renderPets(); // re-render cards with compare-mode click handlers
        showToast('Compare mode on — click 2 pets to compare', 'info');
    } else {
        btn.style.background  = '';
        btn.style.borderColor = '';
        btn.style.color       = '';
        icon.textContent      = '⚖️';
        clearBtn.style.display = 'none';
        el('pc-compare-overlay').style.display = 'none';
        document.body.style.overflow = '';
        renderPets(); // re-render cards without compare-mode click handlers
    }
};

window.pcClearCompare = function() {
    _compareSelected = [];
    el('pc-compare-overlay').style.display = 'none';
    document.body.style.overflow = '';
    // Remove selection badges without full re-render
    document.querySelectorAll('.pc-pet-card').forEach(function(card) {
        card.classList.remove('pc-compare-selected');
        var badge = card.querySelector('.pc-compare-badge');
        if (badge) badge.remove();
    });
};

window.pcSelectForCompare = function(userId) {
    if (!_compareMode) return;

    var index = _compareSelected.indexOf(userId);
    if (index !== -1) {
        _compareSelected.splice(index, 1);
    } else {
        if (_compareSelected.length >= 2) {
            showToast('Already have 2 pets selected — deselect one first', 'warning');
            return;
        }
        _compareSelected.push(userId);
    }

    pcUpdateCompareVisuals();

    if (_compareSelected.length === 2) {
        pcShowComparison();
    } else {
        el('pc-compare-overlay').style.display = 'none';
        document.body.style.overflow = '';
    }
};

function pcUpdateCompareVisuals() {
    document.querySelectorAll('.pc-pet-card').forEach(function(card) {
        var userId = card.getAttribute('data-user-id');
        var index  = _compareSelected.indexOf(userId);
        var badge  = card.querySelector('.pc-compare-badge');

        if (index !== -1) {
            card.classList.add('pc-compare-selected');
            if (!badge) {
                badge = document.createElement('div');
                badge.className = 'pc-compare-badge';
                card.appendChild(badge);
            }
            badge.textContent = index + 1;
        } else {
            card.classList.remove('pc-compare-selected');
            if (badge) badge.remove();
        }
    });
}

function pcShowComparison() {
    var user1 = _users.find(function(u) { return u.user_id === _compareSelected[0]; });
    var user2 = _users.find(function(u) { return u.user_id === _compareSelected[1]; });
    if (!user1 || !user2) return;

    var pet1 = user1.pet || {};
    var pet2 = user2.pet || {};

    // VS label
    el('pc-compare-vs-label').innerHTML =
        '<span style="color:var(--gold-primary)">' + esc(pet1.name || user1.username) + '</span>' +
        '<span style="color:var(--text-secondary);margin:0 0.6rem">vs</span>' +
        '<span style="color:var(--gold-primary)">' + esc(pet2.name || user2.username) + '</span>';

    el('pc-compare-content').innerHTML = buildCompareModalBody(user1, user2);

    el('pc-compare-overlay').style.display = 'flex';
    document.body.style.overflow = 'hidden';
}

// ── Build the full comparison modal body ──────────────────────────────────────
function buildCompareModalBody(user1, user2) {
    return '<div class="pc-cmp-grid">' +
        buildCmpHeroCol(user1, user2) +
        buildCmpDivider(user1, user2) +
        buildCmpHeroCol(user2, user1) +
    '</div>' +
    '<div class="pc-cmp-stats-section">' +
        buildCmpStatsTable(user1, user2) +
    '</div>';
}

function buildCmpHeroCol(user, opponent) {
    var pet     = user.pet || {};
    var sp      = pet.species  || 'Cat';
    var elem1   = pet.element  || 'basic';
    var elem2   = pet.element2 || '';
    var cat     = pet.category || 'land';
    var lv      = pet.level    || 1;
    var rel     = user.relationship || null;
    var xpCur   = pet.experience || 0;
    var xpMax   = pet.xp_for_next_level || 100;
    var xpPct   = Math.min(100, Math.round(xpCur / Math.max(1, xpMax) * 100));
    var specs   = (pet.specializations || pet.Spec || []);
    var stats   = pet.computed_stats || {};

    var relRingHtml = '';
    if (rel) {
        var rd = REL[rel] || {};
        relRingHtml = '<div class="pc-hero-rel-ring" style="border-color:' + (rd.color || '#9e9e9e') + '">' + (rd.icon || '⚪') + '</div>';
    }

    var specHtml = specs.length
        ? '<div class="pc-hero-specs">' + specs.map(function(s){ return '<span class="pc-hero-spec-tag">' + esc(s) + '</span>'; }).join('') + '</div>'
        : '';

    return '<div class="pc-cmp-hero-col">' +

        // Portrait
        '<div class="pc-hero-portrait" style="margin-bottom:0.6rem">' +
            '<img src="' + petBadgeImg(pet) + '" class="pc-hero-pet-img" onerror="this.src=\'/static/Emojis/Pets/Cat.png\'">' +
            '<div class="pc-hero-glow-ring"></div>' +
            relRingHtml +
        '</div>' +

        // Pet name
        '<div class="pc-hero-pet-name" style="font-size:1rem;margin-bottom:0.3rem">' + esc(pet.name || 'Unnamed') + '</div>' +

        // Level + species
        '<div class="pc-hero-level-species" style="margin-bottom:0.4rem">' +
            '<span class="pc-hero-level">Lv. ' + lv + '</span>' +
            '<span class="pc-hero-species">' + esc(sp) + '</span>' +
        '</div>' +

        // Badges
        '<div class="pc-hero-badges" style="margin-bottom:0.4rem">' +
            '<img src="' + elemImg(elem1) + '" class="pc-hero-badge" title="' + cap(elem1) + '">' +
            (elem2 ? '<img src="' + elemImg(elem2) + '" class="pc-hero-badge" title="' + cap(elem2) + '">' : '') +
            '<img src="' + catImg(cat) + '" class="pc-hero-badge" title="' + cap(cat) + '">' +
        '</div>' +

        specHtml +

        // Owner
        '<div class="pc-hero-owner" style="margin-bottom:0.8rem">' +
            '<img src="' + esc(user.avatar_url) + '" class="pc-hero-owner-avatar" onerror="this.src=\'/static/Emojis/Pets/Cat.png\'">' +
            '<span class="pc-hero-owner-name">' + esc(user.username) + '</span>' +
        '</div>' +

        // Quick combat stats
        '<div class="pc-cmp-quick-stats">' +
            buildCmpQuickStat('HP',  fmtStat(stats.hp  || stats.max_health || 100), '#4caf50') +
            buildCmpQuickStat('ATK', fmtStat(stats.attack  || 10), '#f44336') +
            buildCmpQuickStat('DEF', fmtStat(stats.defense || 5),  '#2196f3') +
        '</div>' +

        // XP bar
        '<div class="pc-hero-xp" style="margin-top:auto">' +
            '<div class="pc-hero-xp-label"><span>XP</span><span>' + fmtNum(xpCur) + ' / ' + fmtNum(xpMax) + '</span></div>' +
            '<div class="pc-hero-xp-track"><div class="pc-hero-xp-fill" style="width:' + xpPct + '%"></div></div>' +
            '<div class="pc-hero-total-xp">Total: ' + fmtNum(pet.total_xp || 0) + ' XP</div>' +
        '</div>' +

    '</div>';
}

function buildCmpQuickStat(label, val, color) {
    return '<div class="pc-cmp-quick-stat">' +
        '<div class="pc-cmp-quick-val" style="color:' + color + '">' + val + '</div>' +
        '<div class="pc-cmp-quick-lbl">' + label + '</div>' +
    '</div>';
}

function buildCmpDivider(user1, user2) {
    var pet1 = user1.pet || {};
    var pet2 = user2.pet || {};
    var s1   = pet1.computed_stats || {};
    var s2   = pet2.computed_stats || {};

    // Determine overall winner by total of HP+ATK+DEF
    var score1 = (s1.hp || s1.max_health || 100) + (s1.attack || 10) + (s1.defense || 5);
    var score2 = (s2.hp || s2.max_health || 100) + (s2.attack || 10) + (s2.defense || 5);
    var winnerName = score1 > score2 ? (pet1.name || user1.username)
                   : score2 > score1 ? (pet2.name || user2.username)
                   : null;

    return '<div class="pc-cmp-divider">' +
        '<div class="pc-cmp-vs">VS</div>' +
        (winnerName ? '<div class="pc-cmp-winner-label">🏆 ' + esc(winnerName) + ' leads</div>' : '<div class="pc-cmp-winner-label">Tied</div>') +
    '</div>';
}

function buildCmpStatsTable(user1, user2) {
    var pet1 = user1.pet || {};
    var pet2 = user2.pet || {};
    var s1   = pet1.computed_stats || {};
    var s2   = pet2.computed_stats || {};
    var bs1  = pet1.battle_stats   || {};
    var bs2  = pet2.battle_stats   || {};
    var gs1  = pet1.gambling_stats || {};
    var gs2  = pet2.gambling_stats || {};
    var xs1  = pet1.xp_sources     || {};
    var xs2  = pet2.xp_sources     || {};
    var sm1  = pet1.stat_mastery   || {};
    var sm2  = pet2.stat_mastery   || {};
    var am1  = pet1.advantage_mastery || {};
    var am2  = pet2.advantage_mastery || {};
    var eq1  = getEquipSetState(pet1);
    var eq2  = getEquipSetState(pet2);

    // Helper: build a section header row
    function sectionRow(label) {
        return '<div class="pc-cmp-section-row">' + label + '</div>';
    }

    // Helper: build a numeric stat row
    function numRow(icon, label, v1, v2) {
        var w1 = v1 > v2 ? 'pc-cmp-row-win'  : '';
        var w2 = v2 > v1 ? 'pc-cmp-row-win'  : '';
        var l1 = v1 < v2 ? 'pc-cmp-row-lose' : '';
        var l2 = v2 < v1 ? 'pc-cmp-row-lose' : '';
        return '<div class="pc-cmp-row">' +
            '<div class="pc-cmp-cell pc-cmp-cell-left ' + w1 + ' ' + l1 + '">' +
                (v1 > v2 ? '<span class="pc-cmp-win-badge">▲</span>' : '') +
                fmtStat(v1) +
            '</div>' +
            '<div class="pc-cmp-cell pc-cmp-cell-mid">' +
                '<span class="pc-cmp-row-icon">' + icon + '</span>' +
                '<span class="pc-cmp-row-label">' + label + '</span>' +
            '</div>' +
            '<div class="pc-cmp-cell pc-cmp-cell-right ' + w2 + ' ' + l2 + '">' +
                fmtStat(v2) +
                (v2 > v1 ? '<span class="pc-cmp-win-badge">▲</span>' : '') +
            '</div>' +
        '</div>';
    }

    // Helper: text row (no winner highlight — for non-numeric like species)
    function txtRow(icon, label, t1, t2) {
        return '<div class="pc-cmp-row">' +
            '<div class="pc-cmp-cell pc-cmp-cell-left" style="color:var(--text-primary)">' + esc(String(t1)) + '</div>' +
            '<div class="pc-cmp-cell pc-cmp-cell-mid">' +
                '<span class="pc-cmp-row-icon">' + icon + '</span>' +
                '<span class="pc-cmp-row-label">' + label + '</span>' +
            '</div>' +
            '<div class="pc-cmp-cell pc-cmp-cell-right" style="color:var(--text-primary)">' + esc(String(t2)) + '</div>' +
        '</div>';
    }

    // Helper: battle type row  W/L/WR
    function battleRow(icon, label, b1, b2) {
        var w1 = b1.wins || 0, l1 = b1.losses || 0;
        var w2 = b2.wins || 0, l2 = b2.losses || 0;
        var wr1 = (w1+l1) > 0 ? ((w1/(w1+l1))*100).toFixed(0)+'%' : '—';
        var wr2 = (w2+l2) > 0 ? ((w2/(w2+l2))*100).toFixed(0)+'%' : '—';
        var winsWin1 = w1 > w2 ? 'pc-cmp-row-win' : w1 < w2 ? 'pc-cmp-row-lose' : '';
        var winsWin2 = w2 > w1 ? 'pc-cmp-row-win' : w2 < w1 ? 'pc-cmp-row-lose' : '';
        return '<div class="pc-cmp-row">' +
            '<div class="pc-cmp-cell pc-cmp-cell-left ' + winsWin1 + '">' +
                (w1 > w2 ? '<span class="pc-cmp-win-badge">▲</span>' : '') +
                '<span style="color:#81c784">' + w1 + 'W</span>' +
                '<span style="color:rgba(255,255,255,0.4);font-size:0.7rem"> / </span>' +
                '<span style="color:#e57373">' + l1 + 'L</span>' +
                '<span style="color:var(--text-secondary);font-size:0.65rem;margin-left:4px">' + wr1 + '</span>' +
            '</div>' +
            '<div class="pc-cmp-cell pc-cmp-cell-mid">' +
                '<span class="pc-cmp-row-icon">' + icon + '</span>' +
                '<span class="pc-cmp-row-label">' + label + '</span>' +
            '</div>' +
            '<div class="pc-cmp-cell pc-cmp-cell-right ' + winsWin2 + '">' +
                '<span style="color:#81c784">' + w2 + 'W</span>' +
                '<span style="color:rgba(255,255,255,0.4);font-size:0.7rem"> / </span>' +
                '<span style="color:#e57373">' + l2 + 'L</span>' +
                '<span style="color:var(--text-secondary);font-size:0.65rem;margin-left:4px">' + wr2 + '</span>' +
                (w2 > w1 ? '<span class="pc-cmp-win-badge">▲</span>' : '') +
            '</div>' +
        '</div>';
    }

    // Helper: casino game row — net XP = won - lost (lost is stored as positive)
    function casinoRow(icon, label, g1, g2, playedKey, wonKey, xpWonKey, xpLostKey) {
        var p1 = g1[playedKey] || 0, p2 = g2[playedKey] || 0;
        // xp_lost_total is stored as a POSITIVE number (absolute value of losses)
        var n1 = (g1[xpWonKey] || 0) - (g1[xpLostKey] || 0);
        var n2 = (g2[xpWonKey] || 0) - (g2[xpLostKey] || 0);
        var wr1 = p1 > 0 ? (((g1[wonKey]||0)/p1)*100).toFixed(0)+'%' : '—';
        var wr2 = p2 > 0 ? (((g2[wonKey]||0)/p2)*100).toFixed(0)+'%' : '—';
        // Winner = more games played (activity) OR better net XP
        var pw1 = p1 > p2 ? 'pc-cmp-row-win' : p1 < p2 ? 'pc-cmp-row-lose' : '';
        var pw2 = p2 > p1 ? 'pc-cmp-row-win' : p2 < p1 ? 'pc-cmp-row-lose' : '';
        var netCol1 = n1 >= 0 ? '#81c784' : '#e57373';
        var netCol2 = n2 >= 0 ? '#81c784' : '#e57373';
        return '<div class="pc-cmp-row">' +
            '<div class="pc-cmp-cell pc-cmp-cell-left ' + pw1 + '">' +
                (p1 > p2 ? '<span class="pc-cmp-win-badge">▲</span>' : '') +
                p1 + ' played · ' + wr1 +
                ' <span style="color:' + netCol1 + ';font-size:0.65rem">' + fmtXp(n1) + ' XP</span>' +
            '</div>' +
            '<div class="pc-cmp-cell pc-cmp-cell-mid">' +
                '<span class="pc-cmp-row-icon">' + icon + '</span>' +
                '<span class="pc-cmp-row-label">' + label + '</span>' +
            '</div>' +
            '<div class="pc-cmp-cell pc-cmp-cell-right ' + pw2 + '">' +
                p2 + ' played · ' + wr2 +
                ' <span style="color:' + netCol2 + ';font-size:0.65rem">' + fmtXp(n2) + ' XP</span>' +
                (p2 > p1 ? '<span class="pc-cmp-win-badge">▲</span>' : '') +
            '</div>' +
        '</div>';
    }

    // Helper: casino row for games with no win-rate (powerball tickets, etc.)
    function casinoSimpleRow(icon, label, g1, g2, playedKey) {
        var p1 = g1[playedKey] || 0, p2 = g2[playedKey] || 0;
        var n1 = (g1.xp_won_total || 0) - (g1.xp_lost_total || 0);
        var n2 = (g2.xp_won_total || 0) - (g2.xp_lost_total || 0);
        var pw1 = p1 > p2 ? 'pc-cmp-row-win' : p1 < p2 ? 'pc-cmp-row-lose' : '';
        var pw2 = p2 > p1 ? 'pc-cmp-row-win' : p2 < p1 ? 'pc-cmp-row-lose' : '';
        var netCol1 = n1 >= 0 ? '#81c784' : '#e57373';
        var netCol2 = n2 >= 0 ? '#81c784' : '#e57373';
        return '<div class="pc-cmp-row">' +
            '<div class="pc-cmp-cell pc-cmp-cell-left ' + pw1 + '">' +
                (p1 > p2 ? '<span class="pc-cmp-win-badge">▲</span>' : '') +
                p1 + ' played' +
                ' <span style="color:' + netCol1 + ';font-size:0.65rem">' + fmtXp(n1) + ' XP</span>' +
            '</div>' +
            '<div class="pc-cmp-cell pc-cmp-cell-mid">' +
                '<span class="pc-cmp-row-icon">' + icon + '</span>' +
                '<span class="pc-cmp-row-label">' + label + '</span>' +
            '</div>' +
            '<div class="pc-cmp-cell pc-cmp-cell-right ' + pw2 + '">' +
                p2 + ' played' +
                ' <span style="color:' + netCol2 + ';font-size:0.65rem">' + fmtXp(n2) + ' XP</span>' +
                (p2 > p1 ? '<span class="pc-cmp-win-badge">▲</span>' : '') +
            '</div>' +
        '</div>';
    }

    var html = '';

    // ── IDENTITY ──────────────────────────────────────────────────────────────
    html += sectionRow('📋 Identity');
    html += txtRow('📊', 'Species',  pet1.species  || 'Cat',  pet2.species  || 'Cat');
    html += txtRow('🌍', 'Element',  cap(pet1.element || 'basic'), cap(pet2.element || 'basic'));
    html += txtRow('🏷️', 'Category', cap(pet1.category || 'land'), cap(pet2.category || 'land'));
    html += numRow('📊', 'Level',    pet1.level || 1,    pet2.level || 1);
    html += numRow('✨', 'XP',       pet1.experience || 0, pet2.experience || 0);
    html += numRow('🌟', 'Total XP', pet1.total_xp || 0,  pet2.total_xp || 0);

    // Ability points: current unspent + all points ever spent (mastery + abilities)
    function totalAbilityPointsEver(pet) {
        var current = pet.ability_points || 0;
        var sm = pet.stat_mastery || {};
        var spentMastery = Object.keys(sm).reduce(function(s, k) { return s + (sm[k] || 0); }, 0);
        var ab = pet.abilities || {};
        // Each ability level costs 1 point per level
        var spentAbilities = Object.keys(ab).reduce(function(s, k) { return s + (ab[k] || 0); }, 0);
        // Advantage mastery
        var am = pet.advantage_mastery || {};
        var spentAdv = Object.keys(am).reduce(function(s, k) { return s + (am[k] || 0); }, 0);
        return current + spentMastery + spentAbilities + spentAdv;
    }
    html += numRow('⚡', 'Ability Pts (total)', totalAbilityPointsEver(pet1), totalAbilityPointsEver(pet2));
    html += numRow('⚡', 'Ability Pts (unspent)', pet1.ability_points || 0, pet2.ability_points || 0);
    html += numRow('🎒', 'Inventory',    (pet1.inventory||[]).length, (pet2.inventory||[]).length);

    // ── COMBAT STATS ──────────────────────────────────────────────────────────
    html += sectionRow('⚔️ Combat Stats');
    html += numRow('❤️', 'HP',      s1.hp || s1.max_health || 100, s2.hp || s2.max_health || 100);
    html += numRow('⚔️', 'Attack',  s1.attack  || 10, s2.attack  || 10);
    html += numRow('🛡️', 'Defense', s1.defense || 5,  s2.defense || 5);

    // ── BASE STATS ────────────────────────────────────────────────────────────
    html += sectionRow('📊 Base Stats');
    html += numRow('⚔️', 'ATT', pet1.ATT || 0, pet2.ATT || 0);
    html += numRow('🛡️', 'DEF', pet1.DEF || 0, pet2.DEF || 0);
    html += numRow('🧠', 'INT', pet1.INT || 0, pet2.INT || 0);
    html += numRow('💨', 'DEX', pet1.DEX || 0, pet2.DEX || 0);
    html += numRow('💚', 'HAP', pet1.HAP || 0, pet2.HAP || 0);
    html += numRow('⚡', 'ENE', pet1.ENE || 0, pet2.ENE || 0);

    // ── EQUIPMENT ─────────────────────────────────────────────────────────────
    html += sectionRow('🎒 Equipment');
    html += numRow('⚡', 'Equip ×',      eq1.finalMult, eq2.finalMult);
    html += numRow('🧵', 'Mat Pair',     eq1.matPair ? 1 : 0, eq2.matPair ? 1 : 0);
    html += numRow('💎', 'Gem Pair',     eq1.gemPair ? 1 : 0, eq2.gemPair ? 1 : 0);
    html += numRow('👹', 'Mon Pair',     eq1.monPair ? 1 : 0, eq2.monPair ? 1 : 0);
    html += numRow('🎩', 'Hat Equipped', eq1.hatEquipped ? 1 : 0, eq2.hatEquipped ? 1 : 0);
    html += numRow('🎯', 'Hat Spec Match', eq1.hatSpecMatches, eq2.hatSpecMatches);

    // ── STAT MASTERY ──────────────────────────────────────────────────────────
    var hasMastery = ['ATT','DEF','INT','DEX','HAP','ENE'].some(function(s){ return (sm1[s]||0)+(sm2[s]||0) > 0; });
    if (hasMastery) {
        html += sectionRow('🌟 Stat Mastery');
        ['ATT','DEF','INT','DEX','HAP','ENE'].forEach(function(s) {
            var icons = {ATT:'⚔️',DEF:'🛡️',INT:'🧠',DEX:'💨',HAP:'💚',ENE:'⚡'};
            if ((sm1[s]||0) || (sm2[s]||0)) {
                html += numRow(icons[s], s + ' Mastery', sm1[s]||0, sm2[s]||0);
            }
        });
        if ((am1.type||0) || (am2.type||0)) html += numRow('🎯', 'Type Adv.',    am1.type||0, am2.type||0);
        if ((am1.element||0) || (am2.element||0)) html += numRow('🔥', 'Elem Adv.', am1.element||0, am2.element||0);
    }

    // ── ACTIVITY ──────────────────────────────────────────────────────────────
    html += sectionRow('🗺️ Activity');
    // missions_completed / training_completed / play_attempts are top-level pet fields
    var mc1 = pet1.missions_completed || 0, mc2 = pet2.missions_completed || 0;
    var mf1 = pet1.missions_failed    || 0, mf2 = pet2.missions_failed    || 0;
    var tc1 = pet1.training_completed || 0, tc2 = pet2.training_completed || 0;
    var tf1 = pet1.training_failed    || 0, tf2 = pet2.training_failed    || 0;
    var pa1 = pet1.play_attempts      || 0, pa2 = pet2.play_attempts      || 0;
    html += numRow('🎯', 'Missions Done',   mc1, mc2);
    html += numRow('❌', 'Missions Failed', mf1, mf2);
    html += numRow('🏋️', 'Training Done',   tc1, tc2);
    html += numRow('❌', 'Training Failed', tf1, tf2);
    html += numRow('🎮', 'Play Attempts',   pa1, pa2);

    // ── BATTLE RECORDS ────────────────────────────────────────────────────────
    var battleTypes = [
        {key:'pvp',             icon:'⚔️',  label:'PvP'},
        {key:'npc',             icon:'🤖',  label:'NPC'},
        {key:'wild_encounter',  icon:'🌿',  label:'Wild'},
        {key:'boss',            icon:'👹',  label:'Boss'},
        {key:'tournament',      icon:'🏆',  label:'Tournament'},
        {key:'survivor_series', icon:'💀',  label:'Survivor Series'},
    ];
    var anyBattle = battleTypes.some(function(bt) {
        var b1 = bs1[bt.key] || {}, b2 = bs2[bt.key] || {};
        return (b1.wins||0)+(b1.losses||0)+(b2.wins||0)+(b2.losses||0) > 0;
    });
    if (anyBattle) {
        html += sectionRow('🏆 Battle Records');
        battleTypes.forEach(function(bt) {
            var b1 = bs1[bt.key] || {wins:0,losses:0};
            var b2 = bs2[bt.key] || {wins:0,losses:0};
            if ((b1.wins||0)+(b1.losses||0)+(b2.wins||0)+(b2.losses||0) === 0) return;
            html += battleRow(bt.icon, bt.label, b1, b2);
            if ((b1.eliminations||0) || (b2.eliminations||0)) {
                html += numRow('💥', bt.label + ' Elims', b1.eliminations||0, b2.eliminations||0);
            }
        });
    }

    // ── CASINO ────────────────────────────────────────────────────────────────
    // All game types with their exact field names from user_data_manager.py
    var casinoGames = [
        {key:'slots',         icon:'🎰', label:'Slots',         playedKey:'total_games_played', wonKey:'games_won',   xpWonKey:'xp_won_total', xpLostKey:'xp_lost_total'},
        {key:'blackjack',     icon:'🃏', label:'Blackjack',     playedKey:'rounds_played',      wonKey:'rounds_won',  xpWonKey:'xp_won_total', xpLostKey:'xp_lost_total'},
        {key:'holdem',        icon:'♠️', label:"Hold'em",       playedKey:'games_played',       wonKey:'games_won',   xpWonKey:'xp_won_total', xpLostKey:'xp_lost_total'},
        {key:'craps',         icon:'🎲', label:'Craps',         playedKey:'games_played',       wonKey:'games_won',   xpWonKey:'xp_won_total', xpLostKey:'xp_lost_total'},
        {key:'races',         icon:'🏇', label:'Races',         playedKey:'races_played',       wonKey:'races_won',   xpWonKey:'xp_won_total', xpLostKey:'xp_lost_total'},
        {key:'coinflip',      icon:'🪙', label:'Coin Flip',     playedKey:'games_played',       wonKey:'games_won',   xpWonKey:'xp_won_total', xpLostKey:'xp_lost_total'},
        {key:'rps',           icon:'✊', label:'Rock Paper Scissors', playedKey:'games_played', wonKey:'games_won',   xpWonKey:'xp_won_total', xpLostKey:'xp_lost_total'},
        {key:'wheel_of_pets', icon:'🎡', label:'Wheel of Pets', playedKey:'games_played',       wonKey:'games_won',   xpWonKey:'xp_won_total', xpLostKey:'xp_lost_total'},
        {key:'keno',          icon:'🎯', label:'Keno',          playedKey:'games_played',       wonKey:'games_won',   xpWonKey:'xp_won_total', xpLostKey:'xp_lost_total'},
        {key:'scratch_cards', icon:'🎫', label:'Scratch Cards', playedKey:'games_played',       wonKey:'games_won',   xpWonKey:'xp_won_total', xpLostKey:'xp_lost_total'},
    ];
    // Powerball uses tickets_bought instead of games_played
    var powerball1 = gs1.powerball || {}, powerball2 = gs2.powerball || {};

    var anyCasino = casinoGames.some(function(g) {
        return (gs1[g.key]||{})[g.playedKey] || (gs2[g.key]||{})[g.playedKey];
    }) || (powerball1.tickets_bought || 0) || (powerball2.tickets_bought || 0);

    if (anyCasino) {
        html += sectionRow('🎰 Casino');
        casinoGames.forEach(function(g) {
            var c1 = gs1[g.key] || {}, c2 = gs2[g.key] || {};
            if (!(c1[g.playedKey]||0) && !(c2[g.playedKey]||0)) return;
            html += casinoRow(g.icon, g.label, c1, c2, g.playedKey, g.wonKey, g.xpWonKey, g.xpLostKey);
        });
        if ((powerball1.tickets_bought || 0) || (powerball2.tickets_bought || 0)) {
            html += casinoSimpleRow('🎟️', 'Powerball', powerball1, powerball2, 'tickets_bought');
        }
    }

    // ── XP SOURCES ────────────────────────────────────────────────────────────
    // xp_sources values can be negative (losses). Use absolute comparison for winner.
    var xpGroups = [
        {label:'Play XP',     icon:'🎮', keys:['play']},
        {label:'Training XP', icon:'🏋️', keys:['training']},
        {label:'Mission XP',  icon:'🎯', keys:['mission','mission_fail']},
        {label:'Quest XP',    icon:'📜', keys:['quest']},
        {label:'Battle XP',   icon:'⚔️', keys:['battle','npc_battle','pvp_battle']},
        {label:'Slots XP',    icon:'🎰', keys:['slots_win','slots_bet']},
        {label:'Blackjack XP',icon:'🃏', keys:['blackjack_win','blackjack_bet']},
        {label:"Hold'em XP",  icon:'♠️', keys:['holdem_win','holdem_buyin','holdem_cashout']},
        {label:'Craps XP',    icon:'🎲', keys:['craps_win','craps_bet']},
        {label:'Races XP',    icon:'🏇', keys:['race_win','race_bet']},
        {label:'Coin Flip XP',icon:'🪙', keys:['coinflip_win']},
        {label:'Minigame XP', icon:'🎮', keys:['minigame_bet','rps_win','rps_tie']},
        {label:'Casino XP (total)', icon:'🎰', keys:['slots_win','slots_bet','blackjack_win','blackjack_bet','holdem_win','holdem_buyin','holdem_cashout','craps_win','craps_bet','race_win','race_bet','coinflip_win','minigame_bet','rps_win','rps_tie']},
    ];
    var anyXp = xpGroups.some(function(g) {
        var n1 = g.keys.reduce(function(s,k){ return s+(xs1[k]||0); }, 0);
        var n2 = g.keys.reduce(function(s,k){ return s+(xs2[k]||0); }, 0);
        return n1 || n2;
    });
    if (anyXp) {
        html += sectionRow('✨ XP Sources');
        xpGroups.forEach(function(g) {
            var n1 = g.keys.reduce(function(s,k){ return s+(xs1[k]||0); }, 0);
            var n2 = g.keys.reduce(function(s,k){ return s+(xs2[k]||0); }, 0);
            if (!n1 && !n2) return;
            // For XP sources: winner = higher absolute value (more activity), color by sign
            var abs1 = Math.abs(n1), abs2 = Math.abs(n2);
            var w1 = abs1 > abs2 ? 'pc-cmp-row-win' : abs1 < abs2 ? 'pc-cmp-row-lose' : '';
            var w2 = abs2 > abs1 ? 'pc-cmp-row-win' : abs2 < abs1 ? 'pc-cmp-row-lose' : '';
            var col1 = n1 >= 0 ? 'var(--text-primary)' : '#e57373';
            var col2 = n2 >= 0 ? 'var(--text-primary)' : '#e57373';
            html += '<div class="pc-cmp-row">' +
                '<div class="pc-cmp-cell pc-cmp-cell-left ' + w1 + '" style="color:' + col1 + '">' +
                    (abs1 > abs2 ? '<span class="pc-cmp-win-badge">▲</span>' : '') +
                    fmtXp(n1) +
                '</div>' +
                '<div class="pc-cmp-cell pc-cmp-cell-mid">' +
                    '<span class="pc-cmp-row-icon">' + g.icon + '</span>' +
                    '<span class="pc-cmp-row-label">' + g.label + '</span>' +
                '</div>' +
                '<div class="pc-cmp-cell pc-cmp-cell-right ' + w2 + '" style="color:' + col2 + '">' +
                    fmtXp(n2) +
                    (abs2 > abs1 ? '<span class="pc-cmp-win-badge">▲</span>' : '') +
                '</div>' +
            '</div>';
        });
    }

    return '<div class="pc-cmp-table-header">' +
        '<div style="flex:1;text-align:right;color:var(--gold-primary);font-weight:700">' + esc(pet1.name || user1.username) + '</div>' +
        '<div style="width:160px;text-align:center;color:var(--text-secondary);font-size:0.7rem;text-transform:uppercase;letter-spacing:1px">Stat</div>' +
        '<div style="flex:1;text-align:left;color:var(--gold-primary);font-weight:700">'  + esc(pet2.name || user2.username) + '</div>' +
    '</div>' +
    '<div class="pc-cmp-table">' + html + '</div>';
}

function pcBuildCompareCard(user, opponent) {
    var pet = user.pet || {};
    var stats = pet.computed_stats || {};
    var oppStats = (opponent.pet || {}).computed_stats || {};
    
    var compareStats = [
        {key: 'Level', val: pet.level || 1, opp: (opponent.pet || {}).level || 1},
        {key: 'HP', val: stats.hp || stats.max_health || 100, opp: oppStats.hp || oppStats.max_health || 100},
        {key: 'ATK', val: stats.attack || 10, opp: oppStats.attack || 10},
        {key: 'DEF', val: stats.defense || 5, opp: oppStats.defense || 5},
        {key: 'ATT', val: pet.ATT || 0, opp: (opponent.pet || {}).ATT || 0},
        {key: 'DEF', val: pet.DEF || 0, opp: (opponent.pet || {}).DEF || 0},
        {key: 'INT', val: pet.INT || 0, opp: (opponent.pet || {}).INT || 0},
        {key: 'DEX', val: pet.DEX || 0, opp: (opponent.pet || {}).DEX || 0},
        {key: 'HAP', val: pet.HAP || 0, opp: (opponent.pet || {}).HAP || 0},
        {key: 'ENE', val: pet.ENE || 0, opp: (opponent.pet || {}).ENE || 0},
    ];
    
    var statsHtml = compareStats.map(function(stat) {
        var isWinner = stat.val > stat.opp;
        var isLoser = stat.val < stat.opp;
        var cls = isWinner ? 'pc-compare-stat-winner' : isLoser ? 'pc-compare-stat-loser' : '';
        
        return '<div class="pc-compare-stat ' + cls + '">' +
            '<span>' + stat.key + '</span>' +
            '<span>' + fmtStat(stat.val) + '</span>' +
        '</div>';
    }).join('');
    
    return '<div class="pc-compare-pet">' +
        '<div style="display:flex;align-items:center;gap:0.8rem;margin-bottom:0.8rem">' +
            '<img src="' + esc(user.avatar_url) + '" style="width:32px;height:32px;border-radius:50%;border:1px solid rgba(255,215,0,0.3)">' +
            '<div>' +
                '<div style="font-weight:700;color:var(--gold-primary)">' + esc(pet.name || 'Unnamed') + '</div>' +
                '<div style="font-size:0.75rem;color:var(--text-secondary)">' + esc(user.username) + '</div>' +
            '</div>' +
        '</div>' +
        '<div class="pc-compare-stats">' + statsHtml + '</div>' +
    '</div>';
}

// ── Enhanced Leaderboard Functions ─────────────────────────────────────────────
function pcLbSort(sortKey) {
    _leaderboardSort = sortKey;
    
    // Update active button
    var btns = document.querySelectorAll('.pc-lb-sort-btn');
    btns.forEach(function(btn) {
        btn.classList.remove('pc-lb-active');
        if (btn.dataset.lbkey === sortKey) {
            btn.classList.add('pc-lb-active');
        }
    });
    
    pcUpdateLeaderboard();
}

function pcUpdateLeaderboard() {
    var sortedUsers = _users.slice().sort(function(a, b) {
        var aVal = pcGetLeaderboardValue(a, _leaderboardSort);
        var bVal = pcGetLeaderboardValue(b, _leaderboardSort);
        return bVal - aVal; // Always descending for leaderboard
    });
    
    var html = sortedUsers.slice(0, 20).map(function(user, index) {
        var value = pcGetLeaderboardValue(user, _leaderboardSort);
        var displayValue = pcFormatLeaderboardValue(value, _leaderboardSort);
        
        return '<div class="pc-lb-item" onclick="openDetail(\'' + esc(user.user_id) + '\')">' +
            '<div class="pc-lb-rank">' + (index + 1) + '</div>' +
            '<img src="' + esc(user.avatar_url) + '" class="pc-lb-avatar">' +
            '<div class="pc-lb-name">' + esc(user.username) + '</div>' +
            '<div class="pc-lb-value">' + displayValue + '</div>' +
        '</div>';
    }).join('');
    
    el('pc-lb-list').innerHTML = html;
}

function pcGetLeaderboardValue(user, key) {
    var pet = user.pet || {};
    var stats = pet.computed_stats || {};
    var battleStats = pet.battle_stats || {};
    var gamblingStats = pet.gambling_stats || {};
    var xpSources = pet.xp_sources || {};
    
    switch (key) {
        // Identity & Progress
        case 'level': return pet.level || 1;
        case 'total_xp': return pet.total_xp || 0;
        case 'xp_progress': 
            var cur = pet.experience || 0;
            var max = pet.xp_for_next_level || 100;
            return Math.round((cur / max) * 100);
            
        // Base Stats
        case 'ATT': return pet.ATT || 0;
        case 'DEF': return pet.DEF || 0;
        case 'INT': return pet.INT || 0;
        case 'DEX': return pet.DEX || 0;
        case 'HAP': return pet.HAP || 0;
        case 'ENE': return pet.ENE || 0;
        
        // Combat Stats
        case 'cs_hp': return stats.hp || stats.max_health || 100;
        case 'cs_attack': return stats.attack || 10;
        case 'cs_defense': return stats.defense || 5;
        
        // Battle Records
        case 'pvp_wins': return (battleStats.pvp || {}).wins || 0;
        case 'pvp_losses': return (battleStats.pvp || {}).losses || 0;
        case 'pvp_wr': 
            var pvp = battleStats.pvp || {};
            var w = pvp.wins || 0, l = pvp.losses || 0;
            return (w + l) > 0 ? Math.round((w / (w + l)) * 100) : 0;
        case 'npc_wins': return (battleStats.npc || {}).wins || 0;
        case 'boss_wins': return (battleStats.boss || {}).wins || 0;
        case 'tournament_wins': return (battleStats.tournament || {}).wins || 0;
        case 'total_wins': 
            return Object.keys(battleStats).reduce(function(sum, type) {
                return sum + ((battleStats[type] || {}).wins || 0);
            }, 0);
        case 'total_losses':
            return Object.keys(battleStats).reduce(function(sum, type) {
                return sum + ((battleStats[type] || {}).losses || 0);
            }, 0);
        case 'eliminations':
            return Object.keys(battleStats).reduce(function(sum, type) {
                return sum + ((battleStats[type] || {}).eliminations || 0);
            }, 0);
            
        // Activity
        case 'missions_completed': return pet.missions_completed || 0;
        case 'missions_failed': return pet.missions_failed || 0;
        case 'training_completed': return pet.training_completed || 0;
        case 'training_failed': return pet.training_failed || 0;
        case 'play_attempts': return pet.play_attempts || 0;
        
        // Casino
        case 'casino_net':
            return Object.keys(gamblingStats).reduce(function(sum, game) {
                var g = gamblingStats[game] || {};
                return sum + (g.xp_won_total || 0) + (g.xp_lost_total || 0);
            }, 0);
        case 'casino_played':
            return Object.keys(gamblingStats).reduce(function(sum, game) {
                var g = gamblingStats[game] || {};
                return sum + (g.total_games_played || g.rounds_played || g.games_played || g.races_played || 0);
            }, 0);
        case 'slots_played': return (gamblingStats.slots || {}).total_games_played || 0;
        case 'blackjack_played': return (gamblingStats.blackjack || {}).rounds_played || 0;
        case 'holdem_played': return (gamblingStats.holdem || {}).games_played || 0;
        case 'craps_played': return (gamblingStats.craps || {}).games_played || 0;
        case 'races_played': return (gamblingStats.races || {}).races_played || 0;
        
        // Economy
        case 'stock_tokens': return pet.stock_tokens || 0;
        case 'ability_points': return pet.ability_points || 0;
        case 'equip_mult': {
            // Full equipment multiplier using the new slot system
            var _eqState = getEquipSetState(pet);
            return _eqState.finalMult;
        }
        case 'inventory_count': return (pet.inventory || []).length;
        
        // XP Sources
        case 'xp_play': return xpSources.play || 0;
        case 'xp_training': return xpSources.training || 0;
        case 'xp_mission': return (xpSources.mission || 0) + (xpSources.mission_fail || 0);
        case 'xp_battle': return (xpSources.battle || 0) + (xpSources.npc_battle || 0) + (xpSources.pvp_battle || 0);
        case 'xp_casino':
            var casinoKeys = ['slots_win','slots_bet','blackjack_win','blackjack_bet','holdem_win','holdem_buyin','holdem_cashout','craps_win','craps_bet','race_win','race_bet','coinflip_win','minigame_bet','rps_win','rps_tie'];
            return casinoKeys.reduce(function(sum, key) {
                return sum + (xpSources[key] || 0);
            }, 0);
            
        default: return 0;
    }
}

function pcFormatLeaderboardValue(value, key) {
    if (key.includes('_wr') || key === 'xp_progress') {
        return value + '%';
    }
    if (key.includes('xp') || key.includes('tokens')) {
        return fmtStat(value);
    }
    return value.toLocaleString();
}

function pcToggleLeaderboard() {
    var list = el('pc-lb-list');
    if (!list) return;
    list.style.display = list.style.display === 'none' ? '' : 'none';
}

// ── Enhanced Gift Functions ────────────────────────────────────────────────────
function pcUpdateGiftQty() {
    var sel = el('pc-gift-select');
    var opt = sel.options[sel.selectedIndex];
    var max = opt ? (parseInt(opt.dataset.qty) || 1) : 1;
    var inp = el('pc-gift-qty');
    var maxSpan = el('pc-gift-qty-max');
    
    inp.max = max;
    maxSpan.textContent = '/ ' + max;
    if (parseInt(inp.value) > max) inp.value = max;
    
    // Update preview
    var preview = el('pc-gift-item-preview');
    if (opt && opt.value) {
        var itemType = opt.dataset.type || 'Material';
        var itemData = (typeof getEquipItem === 'function') ? getEquipItem(opt.value) : null;
        var imgPath = '/static/Emojis/Pets/Equipment/' + equipImgFile(itemData || {name: opt.value});
        preview.innerHTML = '<img src="' + imgPath + '" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">';
    } else {
        preview.innerHTML = '';
    }
}

// ── Enhanced Hover Tooltips ───────────────────────────────────────────────────
window.pcShowHoverTip = function pcShowHoverTip(event, userId) {
    var user = _users.find(function(u) { return u.user_id === userId; });
    if (!user) return;
    
    var pet = user.pet || {};
    var stats = pet.computed_stats || {};
    
    var html = '<div style="text-align:center;margin-bottom:0.5rem">' +
        '<div style="font-weight:700;color:var(--gold-primary)">' + esc(pet.name || 'Unnamed') + '</div>' +
        '<div style="font-size:0.7rem;color:var(--text-secondary)">' + esc(user.username) + '</div>' +
    '</div>' +
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.3rem;font-size:0.7rem">' +
        '<div>Level: <strong>' + (pet.level || 1) + '</strong></div>' +
        '<div>Species: <strong>' + esc(pet.species || 'Cat') + '</strong></div>' +
        '<div>HP: <strong>' + fmtStat(stats.hp || stats.max_health || 100) + '</strong></div>' +
        '<div>ATK: <strong>' + fmtStat(stats.attack || 10) + '</strong></div>' +
        '<div>DEF: <strong>' + fmtStat(stats.defense || 5) + '</strong></div>' +
        '<div>XP: <strong>' + fmtStat(pet.experience || 0) + '</strong></div>' +
    '</div>';
    
    var tip = el('pc-hover-tip');
    el('pc-hover-tip-inner').innerHTML = html;
    tip.style.display = 'block';
    tip.style.left = (event.pageX + 10) + 'px';
    tip.style.top = (event.pageY - 10) + 'px';
};

window.pcHideHoverTip = function pcHideHoverTip() {
    el('pc-hover-tip').style.display = 'none';
};

// ── Enhanced Initialization ───────────────────────────────────────────────────
function pcInitializeFilters() {
    // Populate species filter
    var species = [...new Set(_users.map(function(u) { return (u.pet || {}).species || 'Cat'; }))].sort();
    var speciesSelect = el('pc-species-filter');
    species.forEach(function(sp) {
        var opt = document.createElement('option');
        opt.value = sp.toLowerCase();
        opt.textContent = sp;
        speciesSelect.appendChild(opt);
    });
    
    // Populate element filter
    var elements = [...new Set(_users.flatMap(function(u) {
        var pet = u.pet || {};
        var elems = [pet.element, pet.element2].filter(Boolean);
        return elems.map(function(e) { return e || 'basic'; });
    }))].sort();
    var elementSelect = el('pc-element-filter');
    elements.forEach(function(elem) {
        var opt = document.createElement('option');
        opt.value = elem.toLowerCase();
        opt.textContent = cap(elem);
        elementSelect.appendChild(opt);
    });
    
    // Populate category filter
    var categories = [...new Set(_users.map(function(u) { return (u.pet || {}).category || 'land'; }))].sort();
    var categorySelect = el('pc-category-filter');
    categories.forEach(function(cat) {
        var opt = document.createElement('option');
        opt.value = cat.toLowerCase();
        opt.textContent = cap(cat);
        categorySelect.appendChild(opt);
    });
    
    // Set up sort change handler
    el('pc-sort-select').addEventListener('change', function() {
        _currentSort = this.value;
        pcApplyFilters();
    });
    
    // Show controls and compare button
    el('pc-controls').style.display = '';
    el('pc-compare-mode-btn').style.display = '';
}

// ── Enhanced Small pet cards with compare mode and hover ──────────────────────
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

    var cardClass = 'pc-pet-card' + (rel ? ' pc-rel-border-' + rel : '');
    if (_compareMode) cardClass += ' pc-compare-mode';
    
    // Fix compare mode click handlers - prevent detail panel opening during compare mode
    var cardEvents = _compareMode 
        ? 'onclick="event.stopPropagation(); pcSelectForCompare(\'' + esc(user.user_id) + '\'); return false;"'
        : 'onclick="openDetail(\'' + esc(user.user_id) + '\')" onmouseenter="pcShowHoverTip(event, \'' + esc(user.user_id) + '\')" onmouseleave="pcHideHoverTip()"';

    return '<div class="col-xl-2 col-lg-3 col-md-4 col-sm-6">' +
        '<div class="' + cardClass + '" data-user-id="' + esc(user.user_id) + '" style="' + (rel ? 'margin-bottom:14px' : '') + '" ' + cardEvents + '>' +

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
                '<img class="pc-card-pet-img" src="' + petBadgeImg(pet) + '" onerror="this.src=\'/static/Emojis/Pets/Cat.png\'" alt="' + esc(sp) + '">' +
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

// ── Enhanced Wide Detail Panel ────────────────────────────────────────────────
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

    // Build Hero Section (Left Column)
    var heroHtml = buildHeroSection(user, pet, elem1, elem2, cat, sp, lv, xpCur, xpMax, xpPct, rel);
    
    // Build Stats Section (Right Column)
    var statsHtml = buildStatsSection(pet, user);
    
    // Build Relationship Section (Bottom Left)
    var relationshipHtml = buildRelationshipSectionWide(user, rel, mutual, isMe);
    
    // Build Gift Section (Bottom Right)
    var giftHtml = buildGiftSectionWide(user, isMe);

    // Populate the sections
    el('pc-detail-hero').innerHTML = heroHtml;
    el('pc-detail-stats').innerHTML = statsHtml;
    el('pc-mutual-status').innerHTML = buildMutualStatus(user, mutual);
    el('pc-relationship-cards').innerHTML = relationshipHtml;
    el('pc-gift-items-grid').innerHTML = giftHtml;
    
    // Initialize gift functionality
    if (!isMe) {
        initializeGiftSection(user);
    }

    // Show the panel
    el('pc-detail-overlay').style.display = 'flex';
    document.body.style.overflow = 'hidden';
}

function buildHeroSection(user, pet, elem1, elem2, cat, sp, lv, xpCur, xpMax, xpPct, rel) {
    var specs = (pet.specializations || pet.Spec || []);
    var specHtml = specs.length
        ? '<div class="pc-hero-specs">' + specs.map(function(s){ return '<span class="pc-hero-spec-tag">' + esc(s) + '</span>'; }).join('') + '</div>'
        : '';

    var relRingHtml = '';
    if (rel) {
        var relData = REL[rel] || {};
        relRingHtml = '<div class="pc-hero-rel-ring" style="border-color:' + (relData.color || '#9e9e9e') + '">' + (relData.icon || '⚪') + '</div>';
    }

    // Single wrapper div — flex column, everything stacked cleanly
    return '<div class="pc-hero-inner">' +

        // Portrait with glow ring + relationship ring
        '<div class="pc-hero-portrait">' +
            '<img src="' + petBadgeImg(pet) + '" class="pc-hero-pet-img" alt="' + esc(sp) + '" onerror="this.src=\'/static/Emojis/Pets/Cat.png\'">' +
            '<div class="pc-hero-glow-ring"></div>' +
            relRingHtml +
        '</div>' +

        // Pet name
        '<div class="pc-hero-pet-name">' + esc(pet.name || 'Unnamed Pet') + '</div>' +

        // Level + species row
        '<div class="pc-hero-level-species">' +
            '<span class="pc-hero-level">Lv. ' + lv + '</span>' +
            '<span class="pc-hero-species">' + esc(sp) + '</span>' +
        '</div>' +

        // Element / category badges
        '<div class="pc-hero-badges">' +
            '<img src="' + elemImg(elem1) + '" class="pc-hero-badge" title="' + cap(elem1) + '">' +
            (elem2 ? '<img src="' + elemImg(elem2) + '" class="pc-hero-badge" title="' + cap(elem2) + '">' : '') +
            '<img src="' + catImg(cat) + '" class="pc-hero-badge" title="' + cap(cat) + '">' +
        '</div>' +

        // Spec tags
        specHtml +

        // Owner row
        '<div class="pc-hero-owner">' +
            '<img src="' + esc(user.avatar_url) + '" class="pc-hero-owner-avatar" alt="' + esc(user.username) + '" onerror="this.src=\'/static/Emojis/Pets/Cat.png\'">' +
            '<span class="pc-hero-owner-name">' + esc(user.username) + '</span>' +
        '</div>' +

        // XP bar — pinned to bottom of left column via mt-auto
        '<div class="pc-hero-xp">' +
            '<div class="pc-hero-xp-label">' +
                '<span>Experience</span>' +
                '<span>' + fmtNum(xpCur) + ' / ' + fmtNum(xpMax) + '</span>' +
            '</div>' +
            '<div class="pc-hero-xp-track">' +
                '<div class="pc-hero-xp-fill" style="width:' + xpPct + '%"></div>' +
            '</div>' +
            '<div class="pc-hero-total-xp">Total: ' + fmtNum(pet.total_xp || 0) + ' XP</div>' +
        '</div>' +

    '</div>';
}

function buildStatsSection(pet, user) {
    return buildCombatStatsSection(pet) +
           buildBaseStatsSection(pet) +
           buildEquippedSection(pet) +
           buildEquipBonusSection(pet) +
           buildEquipDetailSection(pet) +
           buildAbilitiesSection(pet) +
           buildActivitySection(pet) +
           buildBreakdownSection(pet, user) +
           buildSpeciesSection(pet);
}

function buildMutualStatus(user, mutual) {
    if (!mutual.user_to_target && !mutual.target_to_user) {
        return '<div style="text-align:center;color:var(--text-secondary);font-style:italic;">No mutual relationship data</div>';
    }
    
    return '<div style="display:flex;flex-direction:column;gap:0.3rem;">' +
        '<div>You → ' + esc(user.username) + ': <strong style="color:' + relColor(mutual.user_to_target) + '">' + relLabel(mutual.user_to_target) + ' ' + relIcon(mutual.user_to_target) + '</strong></div>' +
        '<div>' + esc(user.username) + ' → You: <strong style="color:' + relColor(mutual.target_to_user) + '">' + relLabel(mutual.target_to_user) + ' ' + relIcon(mutual.target_to_user) + '</strong></div>' +
    '</div>';
}

function buildRelationshipSectionWide(user, rel, mutual, isMe) {
    if (isMe) {
        return '<div style="text-align:center;color:var(--text-secondary);font-style:italic;padding:2rem;">This is your own pet</div>';
    }

    var relationships = [
        {key: 'best_friend', label: 'Best Friend', emoji: '💚', class: 'pc-rel-best-friend'},
        {key: 'friend', label: 'Friend', emoji: '💙', class: 'pc-rel-friend'},
        {key: 'foe', label: 'Foe', emoji: '🧡', class: 'pc-rel-foe'},
        {key: 'enemy', label: 'Enemy', emoji: '❤️', class: 'pc-rel-enemy'}
    ];

    return relationships.map(function(r) {
        var isActive = rel === r.key;
        var cardClass = 'pc-rel-card ' + r.class + (isActive ? ' pc-rel-active' : '');
        
        return '<div class="' + cardClass + '" onclick="setRelWide(\'' + esc(user.user_id) + '\',\'' + r.key + '\')">' +
            '<span class="pc-rel-emoji-large">' + r.emoji + '</span>' +
            '<div class="pc-rel-label">' + r.label + '</div>' +
        '</div>';
    }).join('') + 
    (rel ? '<div class="pc-rel-card" onclick="setRelWide(\'' + esc(user.user_id) + '\',null)" style="grid-column:span 2;background:rgba(244,67,54,0.1);border-color:rgba(244,67,54,0.3);">' +
        '<span class="pc-rel-emoji-large">✕</span>' +
        '<div class="pc-rel-label">Remove</div>' +
    '</div>' : '');
}

function buildGiftSectionWide(user, isMe) {
    if (isMe) {
        return '<div style="text-align:center;color:var(--text-secondary);font-style:italic;padding:2rem;">Cannot gift to yourself</div>';
    }

    var inv = (_currentUser && _currentUser.pet && _currentUser.pet.inventory) || [];
    if (inv.length === 0) {
        return '<div style="text-align:center;color:var(--text-secondary);font-style:italic;padding:2rem;">No items in inventory</div>';
    }

    // Group items by name and sum quantities
    var itemGroups = {};
    inv.forEach(function(item) {
        var name = item.name || 'Unknown';
        if (!itemGroups[name]) {
            itemGroups[name] = {
                name: name,
                type: item.type || 'Material',
                rarity: item.rarity || 'Common',
                emoji_file: item.emoji_file || null,
                count: 0
            };
        }
        itemGroups[name].count += (item.count || item.quantity || 1);
    });

    // Sort items by rarity and name
    var rarityOrder = {Mythic: 0, Epic: 1, Rare: 2, Uncommon: 3, Common: 4};
    var sortedItems = Object.values(itemGroups).sort(function(a, b) {
        var rarityDiff = (rarityOrder[a.rarity] || 4) - (rarityOrder[b.rarity] || 4);
        if (rarityDiff !== 0) return rarityDiff;
        return a.name.localeCompare(b.name);
    });

    return sortedItems.map(function(item) {
        // Use cache-aware equipImgFile for correct subfolder paths
        var f = equipImgFile(item);
        var imgPath = '/static/Emojis/Pets/Equipment/' + f;
        var rarityClass = 'pc-rarity-' + (item.rarity || 'Common').toLowerCase();

        return '<div class="pc-gift-item-card" data-item="' + esc(item.name) + '" data-count="' + item.count + '" data-type="' + esc(item.type) + '" onclick="selectGiftItem(this)">' +
            '<img src="' + imgPath + '" class="pc-gift-item-img" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">' +
            '<div class="pc-gift-item-name ' + rarityClass + '">' + esc(item.name) + '</div>' +
            '<div class="pc-gift-item-qty">x' + item.count + '</div>' +
        '</div>';
    }).join('');
}

// Gift functionality
var _selectedGiftItem = null;

function initializeGiftSection(user) {
    _selectedGiftItem = null;
    updateGiftSelection();
    
    // Set up search functionality
    var searchInput = el('pc-gift-search');
    var filterSelect = el('pc-gift-filter');
    
    if (searchInput) {
        searchInput.addEventListener('input', filterGiftItems);
    }
    if (filterSelect) {
        filterSelect.addEventListener('change', filterGiftItems);
    }
}

window.selectGiftItem = function(cardElement) {
    // Remove previous selection
    var cards = document.querySelectorAll('.pc-gift-item-card');
    cards.forEach(function(card) {
        card.classList.remove('pc-gift-selected');
    });
    
    // Select new item
    cardElement.classList.add('pc-gift-selected');
    _selectedGiftItem = {
        name: cardElement.dataset.item,
        count: parseInt(cardElement.dataset.count),
        type: cardElement.dataset.type
    };
    
    updateGiftSelection();
};

function updateGiftSelection() {
    var infoEl = el('pc-gift-selected-text');
    var qtyEl = el('pc-gift-quantity');
    var sendBtn = el('pc-gift-send-btn');
    
    if (_selectedGiftItem) {
        infoEl.textContent = _selectedGiftItem.name + ' (x' + _selectedGiftItem.count + ' available)';
        qtyEl.max = _selectedGiftItem.count;
        qtyEl.value = Math.min(parseInt(qtyEl.value) || 1, _selectedGiftItem.count);
        sendBtn.disabled = false;
    } else {
        infoEl.textContent = 'No item selected';
        qtyEl.max = 1;
        qtyEl.value = 1;
        sendBtn.disabled = true;
    }
}

function filterGiftItems() {
    var searchTerm = (el('pc-gift-search').value || '').toLowerCase();
    var typeFilter = el('pc-gift-filter').value;
    
    var cards = document.querySelectorAll('.pc-gift-item-card');
    cards.forEach(function(card) {
        var itemName = card.dataset.item.toLowerCase();
        var itemType = card.dataset.type;
        
        var matchesSearch = !searchTerm || itemName.includes(searchTerm);
        var matchesType = !typeFilter || itemType === typeFilter;
        
        card.style.display = (matchesSearch && matchesType) ? '' : 'none';
    });
}

window.pcSendGiftInline = function() {
    if (!_selectedGiftItem || !_detailUserId) {
        showToast('Please select an item first', 'warning');
        return;
    }

    var quantity = parseInt(el('pc-gift-quantity').value) || 1;
    var sendBtn = el('pc-gift-send-btn');
    
    sendBtn.textContent = 'Sending…';
    sendBtn.disabled = true;

    apiCall('/api/world/gift', {
        method: 'POST',
        body: JSON.stringify({ 
            target_user_id: _detailUserId, 
            item_name: _selectedGiftItem.name, 
            quantity: quantity 
        })
    }).then(function(r) {
        sendBtn.textContent = 'Send Gift';
        sendBtn.disabled = false;
        
        if (r && r.success) {
            showToast(r.message || 'Gift sent!', 'success');
            _selectedGiftItem = null;
            updateGiftSelection();
            // Refresh gift items
            var user = _users.find(function(u){ return u.user_id === _detailUserId; });
            if (user) {
                loadPets(); // Refresh inventory
            }
        } else {
            showToast((r && r.detail) || 'Failed to send gift', 'error');
        }
    });
};

// Enhanced relationship setting for wide panel
window.setRelWide = function(userId, type) {
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
            // Refresh the relationship cards
            var relationshipHtml = buildRelationshipSectionWide(user, type, user.mutual_relationship || {}, false);
            el('pc-relationship-cards').innerHTML = relationshipHtml;
            // Refresh main grid
            renderPets();
            showToast(r.message || 'Updated', 'success');
        } else {
            showToast((r && r.detail) || 'Failed', 'error');
        }
    });
};

// ── Equipment helpers (mirrors pet_brain.py StatsCalculator exactly) ─────────

// Equipment data cache — loaded from /api/equipment-data (same as mypet.js)
var _pcEquipData = {};

function pcLoadEquipData() {
    fetch('/api/equipment-data')
        .then(function(r){ return r.json(); })
        .then(function(d) {
            ['Materials','Gems','Monsters','Potions',
             'Hats','Rings','Helmets','Armor','Boots','Shields',
             'Daggers','Katanas','Swords','Axes','Hammers','Bows'].forEach(function(cat) {
                var arr = d[cat] || [];
                arr.forEach(function(item) {
                    if (item && item.name) {
                        _pcEquipData[item.name.toLowerCase()] = item;
                    }
                });
            });
        })
        .catch(function(){});
}
pcLoadEquipData();

function pcGetEquipItem(name) {
    return _pcEquipData[(name||'').toLowerCase()] || null;
}

function equipImgFile(item) {
    var name = (item && item.name) ? item.name : (typeof item === 'string' ? item : '');
    // Check cache first (has correct emoji_file with subfolder prefix)
    var cached = pcGetEquipItem(name);
    if (cached && cached.emoji_file) return cached.emoji_file;
    // Fall back to item's own emoji_file field
    if (item && item.emoji_file) return item.emoji_file;
    return name.toLowerCase().replace(/ /g, '_') + '.png';
}

function getEquipSetState(pet) {
    var eq    = pet.equipment || {};
    var level = parseInt(pet.level || 1, 10);
    var levelBonus = Math.floor(level / 50);

    // ── Helper: get single-slot item ─────────────────────────────────────────
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
    var monsters = getList('Monsters');   // up to 2
    var gems     = getList('Gems');       // up to 2

    // ── Set matching (Helmet + Armor + Boots + Shield + Weapon only; Ring excluded) ──
    // For reforged items, fall back to canonical equipment data for the set tag
    function setTag(item) {
        if (!item) return null;
        if (item.set) return item.set;
        var canonical = typeof getEquipItem === 'function' ? getEquipItem(item.name) : null;
        return (canonical && canonical.set) ? canonical.set : null;
    }
    var setSlots = [helmet, armor, boots, shield, weapon];
    var setSlotsFilled = setSlots.filter(function(s){ return s !== null; });
    var setSlotTags = setSlotsFilled.map(setTag).filter(function(t){ return t; });
    var matchingSet = (setSlotsFilled.length === 5 && setSlotTags.length === 5 &&
        (new Set(setSlotTags)).size === 1);
    var mainSetTags = setSlotTags;

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
    var setBonus  = matchingSet ? 3 : 0;
    var baseMult  = slotsFilledBonus + setBonus + ringSubBonus + levelBonus;
    if (baseMult < 1) baseMult = 1;
    var finalMult = fullSet ? baseMult * 2 : baseMult;

    return {
        helmet: helmet, armor: armor, boots: boots, ring: ring,
        shield: shield, weapon: weapon,
        material: material, monsters: monsters, gems: gems,
        mainFilled: mainFilled.length,
        matchingSet: matchingSet, setTag: matchingSet ? mainSetTags[0] : null,
        matchingMonsters: matchingMonsters, matchingGems: matchingGems,
        hasMaterial: hasMaterial, ringSubBonus: ringSubBonus,
        fullSet: fullSet, baseMult: baseMult, finalMult: finalMult,
        levelBonus: levelBonus,
        // Legacy aliases kept so callers that reference old fields don't break
        matPair: hasMaterial, gemPair: matchingGems, monPair: matchingMonsters,
        hatEquipped: false, hatSpecMatches: 0, setMult: baseMult
    };
}

// ── Section builders (matching MyPet layout) ──────────────────────────────────
function buildEquippedSection(pet) {
    var eq = pet.equipment || {};
    var state = getEquipSetState(pet);

    // ── Row 1: main gear slots ────────────────────────────────────────────────
    var row1 = [
        {key:'Helmet', label:'Helmet'},
        {key:'Armor',  label:'Armor'},
        {key:'Boots',  label:'Boots'},
        {key:'Ring',   label:'Ring'},
        {key:'Shield', label:'Shield'},
        {key:'Weapon', label:'Weapon'},
    ];

    // ── Row 2: ring sub-slots ─────────────────────────────────────────────────
    var row2 = [
        {key:'Monsters', idx:0, label:'Monster 1'},
        {key:'Gems',     idx:0, label:'Gem 1'},
        {key:'Material', idx:-1, label:'Material'},
        {key:'Gems',     idx:1, label:'Gem 2'},
        {key:'Monsters', idx:1, label:'Monster 2'},
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
        if (state.fullSet) return ' pc-equip-fullset';
        // Row 1 set glow — only on the 5 set pieces (not Ring)
        if (sl.idx === undefined || sl.idx === -1) {
            if (state.matchingSet && ['Helmet','Armor','Boots','Shield','Weapon'].indexOf(sl.key) !== -1)
                return ' pc-equip-pair';
            if (sl.key === 'Ring' && state.ringSubBonus > 0) return ' pc-equip-pair';
        }
        // Row 2 ring sub-slot glow
        if (sl.key === 'Monsters' && state.matchingMonsters) return ' pc-equip-pair';
        if (sl.key === 'Gems'     && state.matchingGems)     return ' pc-equip-pair';
        if (sl.key === 'Material' && state.hasMaterial)      return ' pc-equip-pair';
        return '';
    }

    function renderSlot(sl, isRingSub) {
        var item = getItem(sl);
        var isEmpty = !item;
        var f   = isEmpty ? 'Basic.png' : equipImgFile(item);
        var src = isEmpty ? '/static/Emojis/Pets/Deco/Basic.png' : '/static/Emojis/Pets/Equipment/' + f;
        var gc  = isEmpty ? '' : glowClass(sl, item);
        var ringRequired = ['Monsters','Gems','Material'].indexOf(sl.key) !== -1;
        var ringMissing  = ringRequired && !state.ring;

        if (isEmpty) {
            var emptyLabel = ringMissing ? sl.label + ' (need Ring)' : sl.label + ' (empty)';
            return '<div class="pc-equip-slot pc-equip-empty" title="' + esc(emptyLabel) + '">' +
                '<img src="' + src + '">' +
                (isRingSub ? '<span class="pc-slot-label">' + esc(sl.label) + '</span>' : '') +
                '</div>';
        }
        var tip = item.name + ' (equipped)';
        return '<div class="pc-equip-slot pc-equip-filled' + gc + '" title="' + esc(tip) + '">' +
            '<img src="' + src + '" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">' +
            (isRingSub ? '<span class="pc-slot-label">' + esc(item.name) + '</span>' : '') +
            '</div>';
    }

    var html = '<div class="pc-detail-section">' +
        '<div class="pc-detail-section-title">⚔️ Equipped</div>';

    // Row 1 — main gear
    html += '<div class="d-flex flex-wrap gap-1 mb-1">';
    row1.forEach(function(sl){ html += renderSlot(sl, false); });
    html += '</div>';

    // Row 2 — ring sub-slots
    var ringLabel = state.ring
        ? '<span style="font-size:0.55rem;color:var(--gold-secondary);opacity:0.7">💍 Ring slots</span>'
        : '<span style="font-size:0.55rem;color:var(--text-secondary);opacity:0.5">💍 Ring slots (equip a Ring first)</span>';
    html += '<div style="margin-top:4px">' + ringLabel +
        '<div class="d-flex flex-wrap gap-1 mt-1">';
    row2.forEach(function(sl){ html += renderSlot(sl, true); });
    html += '</div></div>';

    return html + '</div>';
}

function buildEquipBonusSection(pet) {
    var state = getEquipSetState(pet);
    if (state.mainFilled === 0 && !state.hasMaterial && state.monsters.length === 0 && state.gems.length === 0) return '';

    var multColor = state.fullSet ? '#f59e0b' : (state.matchingSet ? '#a855f7' : '#57d9a3');

    var cardStyle = 'style="flex:0 0 auto;min-width:0;width:46px;padding:3px 4px"';
    var html = '<div class="pc-detail-section">' +
        '<div class="pc-detail-section-title">⚡ Equipment Bonus</div>' +
        '<div class="d-flex gap-1 mb-2 pc-multi-row" style="padding:4px 0;flex-wrap:nowrap;align-items:center">';
    
    html += '<div class="pc-mini-stat-card" ' + cardStyle + '>' +
        '<div class="pc-mini-label" style="font-size:0.55rem">Multi</div>' +
        '<div style="font-size:0.78rem;font-weight:700;color:' + multColor + '">x' + state.finalMult + (state.fullSet ? '🔥' : '') + '</div>' +
        '</div>';

    var checks = [
        {label:'⚔️',  ok: state.mainFilled >= 1, tip: state.mainFilled + '/6 slots'},
        {label:'🎯',  ok: state.matchingSet,      tip: state.matchingSet ? 'Set: ' + state.setTag : 'No matching set'},
        {label:'💍',  ok: state.ring !== null,    tip: state.ring ? state.ring.name : 'No ring'},
        {label:'👹',  ok: state.matchingMonsters, tip: 'Matching monsters'},
        {label:'💎',  ok: state.matchingGems,     tip: 'Matching gems'},
        {label:'🧵',  ok: state.hasMaterial,      tip: 'Material on ring'},
    ];
    checks.forEach(function(c) {
        html += '<div class="pc-mini-stat-card" ' + cardStyle + ' title="' + (c.tip || '') + '">' +
            '<div style="font-size:0.85rem;line-height:1.2">' + c.label + '</div>' +
            '<div style="font-size:0.78rem;line-height:1.2">' + (c.ok ? '✅' : '❌') + '</div>' +
            '</div>';
    });
    
    return html + '</div></div>';
}

function buildBaseStatsSection(pet) {
    var statKeys = ['ATT','DEF','INT','DEX','HAP','ENE'];
    var statColors = {ATT:'#f44336',DEF:'#2196f3',INT:'#9c27b0',DEX:'#00bcd4',HAP:'#4caf50',ENE:'#ff9800'};
    var statIcons  = {ATT:'⚔️',DEF:'🛡️',INT:'🧠',DEX:'💨',HAP:'💚',ENE:'⚡'};
    var specs = (pet.specializations || pet.Spec || []);
    var cs = pet.computed_stats || {};
    var state = getEquipSetState(pet);

    var bodyId = 'pc-base-stats-body';
    var chevId = 'pc-base-stats-chev';

    // Compute base values and find max for bar scaling
    var vals = {};
    statKeys.forEach(function(s) {
        var raw = pet[s];
        var base;
        if (raw !== undefined && raw !== null && raw !== '') {
            base = parseInt(raw, 10);
            if (isNaN(base)) base = 0;
        } else {
            var total = cs[s] !== undefined ? parseInt(cs[s], 10) : 0;
            var equipBonus = calcEquipBonusForStat(pet, s, state);
            base = Math.max(0, total - equipBonus);
        }
        vals[s] = base;
    });
    var maxVal = Math.max.apply(null, statKeys.map(function(s){ return vals[s]; })) || 1;

    var html = '<div class="pc-detail-section">' +
        '<div class="pc-collapse-header" onclick="pcToggleCollapse(\'' + bodyId + '\',\'' + chevId + '\')">' +
            '<span class="pc-detail-section-title" style="margin:0">📊 Base Stats</span>' +
            '<span id="' + chevId + '" class="pc-chev pc-chev-collapsed">▼</span>' +
        '</div>' +
        '<div id="' + bodyId + '" class="pc-collapse-body" style="display:none">';

    statKeys.forEach(function(s) {
        var v = vals[s];
        var isSp = specs.indexOf(s) !== -1;
        var pct = Math.round((v / maxVal) * 100);
        var col = statColors[s] || 'var(--gold-primary)';
        html += '<div class="pc-stat-bar-row">' +
            '<span class="pc-stat-bar-label ' + (isSp ? 'pc-stat-special' : '') + '" style="color:' + col + '">' + statIcons[s] + ' ' + s + '</span>' +
            '<div class="pc-stat-bar-track">' +
                '<div class="pc-stat-bar-fill" style="width:' + pct + '%;background:' + col + ';' + (isSp ? 'box-shadow:0 0 6px ' + col + '80' : '') + '"></div>' +
            '</div>' +
            '<span class="pc-stat-bar-val" style="color:' + (isSp ? col : 'var(--text-primary)') + '">' + v + (isSp ? ' ★' : '') + '</span>' +
        '</div>';
    });

    return html + '</div></div>';
}

// Calculate the equipment bonus for a single stat, mirroring Python _calculate_equipment_bonuses
function calcEquipBonusForStat(pet, stat, state) {
    var eq = pet.equipment || {};

    // Collect all equipped items from new slot system
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

    var allItems = [];
    ['Helmet','Armor','Boots','Ring','Shield','Weapon'].forEach(function(k){
        var item = getSingle(k);
        if (item) allItems.push(item);
    });
    var mat = getSingle('Material');
    if (mat) allItems.push(mat);
    getList('Monsters').forEach(function(m){ allItems.push(m); });
    getList('Gems').forEach(function(g){ allItems.push(g); });

    // Sum raw bonuses for this stat, then apply the shared multiplier
    var raw = 0;
    allItems.forEach(function(item) {
        var val = parseInt((item.bonuses || {})[stat] || 0, 10);
        if (val) raw += val;
    });

    return raw * state.finalMult;
}

// ── Species info: description + actions ───────────────────────────────────────
// PET_INFO is injected inline from the server or loaded from a global.
// We embed a compact lookup table here for the most common data.
var _PET_INFO_CACHE = null;
function getPetInfo(species) {
    // Try window.PET_INFO first (if server injects it), then our cache
    var src = (window.PET_INFO) || _PET_INFO_CACHE || {};
    return src[species] || null;
}

function buildSpeciesSection(pet) {
    var sp   = pet.species || 'Cat';
    var info = getPetInfo(sp);
    if (!info) return '';

    var desc    = info.Descriptions || info.description || '';
    var actions = info.Actions || {};
    var atk  = actions.Attack  || '—';
    var def  = actions.Defense || '—';
    var chg  = actions.Charge  || '—';

    // Custom action labels override defaults
    var labels = pet.action_labels || {};
    if (labels.attack)  atk = labels.attack;
    if (labels.defense) def = labels.defense;
    if (labels.charge)  chg = labels.charge;

    var bodyId = 'pc-species-body';
    var chevId = 'pc-species-chev';

    return '<div class="pc-detail-section">' +
        '<div class="pc-collapse-header" onclick="pcToggleCollapse(\'' + bodyId + '\',\'' + chevId + '\')">' +
            '<span class="pc-detail-section-title" style="margin:0">🐾 Species Info</span>' +
            '<span id="' + chevId + '" class="pc-chev pc-chev-collapsed">▼</span>' +
        '</div>' +
        '<div id="' + bodyId + '" class="pc-collapse-body" style="display:none">' +
            (desc ? '<p class="pc-species-desc mb-3">' + esc(desc) + '</p>' : '') +
            '<div class="d-flex gap-2 flex-wrap">' +
                '<div class="pc-action-card">' +
                    '<div class="pc-action-type">⚔️ Attack</div>' +
                    '<div class="pc-action-name">' + esc(atk) + '</div>' +
                '</div>' +
                '<div class="pc-action-card">' +
                    '<div class="pc-action-type">🛡️ Defense</div>' +
                    '<div class="pc-action-name">' + esc(def) + '</div>' +
                '</div>' +
                '<div class="pc-action-card">' +
                    '<div class="pc-action-type">⚡ Charge</div>' +
                    '<div class="pc-action-name">' + esc(chg) + '</div>' +
                '</div>' +
            '</div>' +
        '</div>' +
    '</div>';
}

// ── Equipment detail: show each item's bonuses ────────────────────────────────
function buildEquipDetailSection(pet) {
    var eq = pet.equipment || {};
    var state = getEquipSetState(pet);

    // Collect all equipped items with their slot labels
    var equipped = [];
    var mat = eq.Material;
    if (Array.isArray(mat)) { mat.forEach(function(m,i){ if(m&&m.name) equipped.push({slot:'Material '+(i+1), item:m}); }); }
    else if (mat&&mat.name) equipped.push({slot:'Material', item:mat});
    var gems = eq.Gems;
    if (Array.isArray(gems)) { gems.forEach(function(g,i){ if(g&&g.name) equipped.push({slot:'Gem '+(i+1), item:g}); }); }
    else if (gems&&gems.name) equipped.push({slot:'Gem', item:gems});
    var mons = eq.Monsters;
    if (Array.isArray(mons)) { mons.forEach(function(m,i){ if(m&&m.name) equipped.push({slot:'Monster '+(i+1), item:m}); }); }
    else if (mons&&mons.name) equipped.push({slot:'Monster', item:mons});
    var hat = eq.Hat;
    if (Array.isArray(hat)) hat = hat[0]||null;
    if (hat&&hat.name) equipped.push({slot:'Hat', item:hat});
    var pot = eq.Potion;
    if (Array.isArray(pot)) pot = pot[0]||null;
    if (pot&&pot.name) equipped.push({slot:'Potion', item:pot});

    if (!equipped.length) return '';

    var rarityColor = {Common:'#9e9e9e',Uncommon:'#4caf50',Rare:'#2196f3',Epic:'#9c27b0',Mythic:'#f59e0b'};

    var rows = equipped.map(function(e) {
        var item = e.item;
        var rCol = rarityColor[item.rarity] || '#9e9e9e';
        var bonuses = item.bonuses || {};
        var bonusChips = Object.keys(bonuses).map(function(k){
            return '<span class="pc-equip-bonus-chip">+' + bonuses[k] + ' ' + k + '</span>';
        }).join('');
        var src = '/static/Emojis/Pets/Equipment/' + equipImgFile(item);
        return '<div style="display:flex;align-items:flex-start;gap:8px;padding:6px 0;border-bottom:1px solid rgba(255,215,0,0.07)">' +
            '<img src="' + src + '" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'" style="width:32px;height:32px;object-fit:contain;flex-shrink:0">' +
            '<div style="flex:1;min-width:0">' +
                '<div style="display:flex;align-items:center;gap:5px;flex-wrap:wrap">' +
                    '<span style="font-size:0.72rem;font-weight:700;color:var(--text-primary)">' + esc(item.name) + '</span>' +
                    '<span style="font-size:0.6rem;color:' + rCol + '">' + esc(item.rarity||'') + '</span>' +
                    '<span style="font-size:0.58rem;color:var(--text-secondary)">' + esc(e.slot) + '</span>' +
                '</div>' +
                (bonusChips ? '<div class="pc-equip-bonus-row">' + bonusChips + '</div>' : '') +
            '</div>' +
        '</div>';
    }).join('');

    var bodyId = 'pc-equip-detail-body';
    var chevId = 'pc-equip-detail-chev';

    return '<div class="pc-detail-section">' +
        '<div class="pc-collapse-header" onclick="pcToggleCollapse(\'' + bodyId + '\',\'' + chevId + '\')">' +
            '<span class="pc-detail-section-title" style="margin:0">🎒 Equipment Details</span>' +
            '<span id="' + chevId + '" class="pc-chev pc-chev-collapsed">▼</span>' +
        '</div>' +
        '<div id="' + bodyId + '" class="pc-collapse-body" style="display:none">' +
            '<div style="font-size:0.65rem;color:var(--text-secondary);margin-bottom:6px">Multiplier: <strong style="color:var(--gold-primary)">x' + state.finalMult + '</strong></div>' +
            rows +
        '</div>' +
    '</div>';
}

// ── Abilities & Mastery ───────────────────────────────────────────────────────
function buildAbilitiesSection(pet) {
    var abilities    = pet.abilities || {};
    var statMastery  = pet.stat_mastery || {};
    var advMastery   = pet.advantage_mastery || {};
    var abilityPts   = pet.ability_points || 0;

    var hasAny = Object.keys(abilities).length > 0 ||
                 Object.keys(statMastery).some(function(k){ return (statMastery[k]||0) > 0; }) ||
                 Object.keys(advMastery).some(function(k){ return (advMastery[k]||0) > 0; }) ||
                 abilityPts > 0;

    if (!hasAny) return '';

    var bodyId = 'pc-abilities-body';
    var chevId = 'pc-abilities-chev';

    var statKeys = ['ATT','DEF','INT','DEX','HAP','ENE'];
    var branchColors = {ATT:'#f44336',DEF:'#2196f3',INT:'#9c27b0',DEX:'#00bcd4',HAP:'#4caf50',ENE:'#ff9800'};
    var branchIcons  = {ATT:'⚔️',DEF:'🛡️',INT:'🧠',DEX:'💨',HAP:'💚',ENE:'⚡'};

    // ── Stat Mastery bars ─────────────────────────────────────────────────────
    var masteryHtml = '';
    var hasMastery = statKeys.some(function(s){ return (statMastery[s]||0) > 0; });
    if (hasMastery) {
        masteryHtml = '<div style="font-size:0.62rem;text-transform:uppercase;letter-spacing:1px;color:var(--text-secondary);margin-bottom:6px">Stat Mastery</div>';
        statKeys.forEach(function(s) {
            var pts = statMastery[s] || 0;
            if (!pts) return;
            var mult = (1.0 + pts * 0.1).toFixed(1);
            var col = branchColors[s] || 'var(--gold-primary)';
            var pct = Math.min(100, pts * 5); // 20 pts = 100%
            masteryHtml += '<div class="pc-mastery-row">' +
                '<span class="pc-mastery-label" style="color:' + col + '">' + branchIcons[s] + ' ' + s + '</span>' +
                '<div class="pc-mastery-track"><div class="pc-mastery-fill" style="width:' + pct + '%;background:' + col + '"></div></div>' +
                '<span class="pc-mastery-val">' + mult + 'x</span>' +
            '</div>';
        });
    }

    // ── Advantage Mastery ─────────────────────────────────────────────────────
    var advHtml = '';
    var typeAdv = advMastery['type'] || 0;
    var elemAdv = advMastery['element'] || 0;
    if (typeAdv > 0 || elemAdv > 0) {
        advHtml = '<div class="pc-adv-mastery-row">' +
            (typeAdv > 0 ? '<div class="pc-adv-card"><div class="pc-adv-label">Type Adv.</div><div class="pc-adv-val">+' + (typeAdv*0.1).toFixed(1) + '</div></div>' : '') +
            (elemAdv > 0 ? '<div class="pc-adv-card"><div class="pc-adv-label">Elem Adv.</div><div class="pc-adv-val">+' + (elemAdv*0.1).toFixed(1) + '</div></div>' : '') +
        '</div>';
    }

    // ── Unlocked Abilities ────────────────────────────────────────────────────
    var abilitiesHtml = '';
    var unlockedIds = Object.keys(abilities).filter(function(id){ return (abilities[id]||0) > 0; });
    if (unlockedIds.length) {
        abilitiesHtml = '<div style="font-size:0.62rem;text-transform:uppercase;letter-spacing:1px;color:var(--text-secondary);margin:8px 0 6px">Unlocked Abilities</div>' +
            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:5px">';
        unlockedIds.forEach(function(id) {
            var lvl = abilities[id] || 0;
            // Derive stat branch from id prefix
            var branch = id.split('_')[0].toUpperCase();
            var col = branchColors[branch] || 'var(--gold-primary)';
            var displayName = id.replace(/_/g,' ').replace(/\b\w/g,function(c){return c.toUpperCase();});
            var pips = '';
            for (var i = 1; i <= 5; i++) {
                pips += '<div class="pc-pip' + (i <= lvl ? ' pc-pip-filled' : '') + '"></div>';
            }
            abilitiesHtml += '<div class="pc-ability-card">' +
                '<div class="pc-ability-name" style="color:' + col + '">' + esc(displayName) + '</div>' +
                '<div class="pc-ability-level-pips">' + pips + '</div>' +
            '</div>';
        });
        abilitiesHtml += '</div>';
    }

    var html = '<div class="pc-detail-section">' +
        '<div class="pc-collapse-header" onclick="pcToggleCollapse(\'' + bodyId + '\',\'' + chevId + '\')">' +
            '<span class="pc-detail-section-title" style="margin:0">🌟 Abilities & Mastery</span>' +
            '<span id="' + chevId + '" class="pc-chev pc-chev-collapsed">▼</span>' +
        '</div>' +
        '<div id="' + bodyId + '" class="pc-collapse-body" style="display:none">';

    if (abilityPts > 0) {
        html += '<div style="margin-bottom:8px"><span class="pc-ap-badge">✨ ' + abilityPts + ' Ability Point' + (abilityPts !== 1 ? 's' : '') + ' Available</span></div>';
    }
    html += masteryHtml + advHtml + abilitiesHtml;

    return html + '</div></div>';
}

// ── Activity & Missions ───────────────────────────────────────────────────────
function buildActivitySection(pet) {
    var mc  = pet.missions_completed || 0;
    var mf  = pet.missions_failed    || 0;
    var tc  = pet.training_completed || 0;
    var tf  = pet.training_failed    || 0;
    var pa  = pet.play_attempts      || 0;

    var hasAny = mc || mf || tc || tf || pa;
    if (!hasAny) return '';

    var bodyId = 'pc-activity-body';
    var chevId = 'pc-activity-chev';

    var mTotal = mc + mf;
    var mWr = mTotal > 0 ? Math.round(mc/mTotal*100) : 0;
    var tTotal = tc + tf;
    var tWr = tTotal > 0 ? Math.round(tc/tTotal*100) : 0;

    var html = '<div class="pc-detail-section">' +
        '<div class="pc-collapse-header" onclick="pcToggleCollapse(\'' + bodyId + '\',\'' + chevId + '\')">' +
            '<span class="pc-detail-section-title" style="margin:0">🗺️ Activity</span>' +
            '<span id="' + chevId + '" class="pc-chev pc-chev-collapsed">▼</span>' +
        '</div>' +
        '<div id="' + bodyId + '" class="pc-collapse-body" style="display:none">' +
            '<div class="d-flex gap-2 flex-wrap">';

    if (mTotal > 0) {
        html += '<div class="pc-activity-chip">' +
            '<div class="pc-activity-chip-icon">🎯</div>' +
            '<div class="pc-activity-chip-label">Missions</div>' +
            '<div class="pc-activity-chip-val" style="color:#4caf50">' + mc + 'W</div>' +
            '<div style="font-size:0.6rem;color:var(--text-secondary)">' + mf + 'F · ' + mWr + '%</div>' +
        '</div>';
    }
    if (tTotal > 0) {
        html += '<div class="pc-activity-chip">' +
            '<div class="pc-activity-chip-icon">🏋️</div>' +
            '<div class="pc-activity-chip-label">Training</div>' +
            '<div class="pc-activity-chip-val" style="color:#2196f3">' + tc + 'W</div>' +
            '<div style="font-size:0.6rem;color:var(--text-secondary)">' + tf + 'F · ' + tWr + '%</div>' +
        '</div>';
    }
    if (pa > 0) {
        html += '<div class="pc-activity-chip">' +
            '<div class="pc-activity-chip-icon">🎮</div>' +
            '<div class="pc-activity-chip-label">Play</div>' +
            '<div class="pc-activity-chip-val" style="color:#ff9800">' + pa.toLocaleString() + '</div>' +
            '<div style="font-size:0.6rem;color:var(--text-secondary)">attempts</div>' +
        '</div>';
    }

    return html + '</div></div></div>';
}

function buildCombatStatsSection(pet) {
    var stats = pet.computed_stats || {};
    return '<div class="pc-detail-section">' +
        '<div class="pc-detail-section-title">⚔️ Combat Stats</div>' +
        '<div class="pc-detail-stats-grid">' +
            '<div class="pc-stat-box pc-stat-box-glow-hp">' +
                '<div class="pc-stat-box-val" style="color:#4caf50">' + fmtStat(stats.hp || stats.max_health || 100) + '</div>' +
                '<div class="pc-stat-box-lbl">HP</div>' +
            '</div>' +
            '<div class="pc-stat-box pc-stat-box-glow-atk">' +
                '<div class="pc-stat-box-val" style="color:#f44336">' + fmtStat(stats.attack || 10) + '</div>' +
                '<div class="pc-stat-box-lbl">ATK</div>' +
            '</div>' +
            '<div class="pc-stat-box pc-stat-box-glow-def">' +
                '<div class="pc-stat-box-val" style="color:#2196f3">' + fmtStat(stats.defense || 5) + '</div>' +
                '<div class="pc-stat-box-lbl">DEF</div>' +
            '</div>' +
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
        { label:'Casino',  emoji:'🎰', keys:['slots_win','slots_bet','blackjack_win','blackjack_bet','holdem_win','holdem_buyin','holdem_cashout','craps_win','craps_bet','race_win','race_bet','coinflip_win','minigame_bet','rps_win','rps_tie'] },
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
    var battleTypes = [
        {key:'pvp',name:'PvP',icon:'⚔️'},
        {key:'npc',name:'NPC',icon:'🤖'},
        {key:'wild_encounter',name:'Wild',icon:'🌿'},
        {key:'boss',name:'Boss',icon:'👹'},
        {key:'tournament',name:'Tourn.',icon:'🏆'},
        {key:'survivor_series',name:'SS',icon:'💀'},
    ];
    var battleHtml = '<div class="pc-breakdown-sub">Battle Records</div><div class="d-flex gap-2 flex-wrap mb-2">';
    var anyBattle = false;
    battleTypes.forEach(function(bt) {
        var s = bs[bt.key] || {wins:0, losses:0};
        var w = s.wins || 0, l = s.losses || 0;
        if (!w && !l) return;
        anyBattle = true;
        var wr = (w + l) > 0 ? ((w / (w + l)) * 100).toFixed(0) : 0;
        var elims = s.eliminations ? (' · ' + s.eliminations + ' elim') : '';
        battleHtml += '<div class="pc-battle-card">' +
            '<div class="pc-battle-card-name">' + bt.icon + ' ' + bt.name + '</div>' +
            '<div class="pc-battle-wl"><span class="text-success">' + w + 'W</span><span style="color:var(--text-secondary);font-size:0.7rem"> / </span><span class="text-danger">' + l + 'L</span></div>' +
            '<div class="pc-battle-wr">' + wr + '% WR' + elims + '</div>' +
        '</div>';
    });
    battleHtml += '</div>';

    // ── Casino ────────────────────────────────────────────────────────────────
    var gs = pet.gambling_stats || {};
    var games = [
        {key:'slots',     name:'Slots',    icon:'🎰', playedKey:'total_games_played', wonKey:'games_won', wonXpKey:'xp_won_total', lostXpKey:'xp_lost_total'},
        {key:'blackjack', name:'BJ',       icon:'🃏', playedKey:'rounds_played',      wonKey:'rounds_won', wonXpKey:'xp_won_total', lostXpKey:'xp_lost_total'},
        {key:'holdem',    name:"Hold'em",  icon:'♠️', playedKey:'games_played',       wonKey:'games_won', wonXpKey:'xp_won_total', lostXpKey:'xp_lost_total'},
        {key:'craps',     name:'Craps',    icon:'🎲', playedKey:'games_played',       wonKey:'games_won', wonXpKey:'xp_won_total', lostXpKey:'xp_lost_total'},
        {key:'races',     name:'Races',    icon:'🏇', playedKey:'races_played',       wonKey:'races_won', wonXpKey:'xp_won_total', lostXpKey:'xp_lost_total'},
    ];
    var casinoHtml = '';
    var playedGames = games.filter(function(g) {
        var s = gs[g.key] || {};
        return (s[g.playedKey] || 0) > 0;
    });
    if (playedGames.length) {
        casinoHtml += '<div class="pc-breakdown-sub">Casino</div><div class="d-flex gap-2 flex-wrap mb-2">';
        playedGames.forEach(function(g) {
            var s = gs[g.key] || {};
            var played = s[g.playedKey] || 0;
            var wins   = s[g.wonKey] || 0;
            var wonXp  = s[g.wonXpKey] || 0;
            var lostXp = s[g.lostXpKey] || 0;
            var net    = wonXp + lostXp; // lostXp is stored negative
            var wr     = played > 0 ? ((wins / played) * 100).toFixed(0) : '—';
            casinoHtml += '<div class="pc-casino-card">' +
                '<div class="pc-casino-name">' + g.icon + ' ' + g.name + '</div>' +
                '<div class="pc-casino-played">' + played + ' played</div>' +
                '<div style="font-size:0.65rem;color:var(--text-secondary)">' + wr + '% WR</div>' +
                '<div class="pc-casino-net ' + (net >= 0 ? 'text-success' : 'text-danger') + '">' + fmtXp(net) + ' XP</div>' +
            '</div>';
        });
        casinoHtml += '</div>';
    }

    var hasData = xpRows.length || anyBattle || playedGames.length;
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

    // Enhanced relationship toggle buttons with animated emojis
    var btnRow = ['best_friend','friend','foe','enemy'].map(function(type) {
        var r = REL[type];
        var active = rel === type;
        var emojiClass = 'pc-rel-emoji';
        if (active) emojiClass += ' ' + r.animation;
        
        return '<button class="pc-rel-btn ' + (active ? 'pc-rel-active' : '') + '" ' +
            'style="border-color:' + r.color + ';' + (active ? 'background:' + r.color + ';color:#fff' : 'color:' + r.color) + '" ' +
            'onclick="setRel(\'' + esc(user.user_id) + '\',\'' + type + '\')">' +
            '<span class="' + emojiClass + '">' + r.emoji + '</span> ' + r.label +
            '</button>';
    }).join('');

    var removeBtn = rel ? '<button class="pc-rel-btn" style="color:var(--text-secondary);border-color:rgba(255,255,255,0.2)" onclick="setRel(\'' + esc(user.user_id) + '\',null)">✕ Remove</button>' : '';

    return '<div class="pc-detail-section">' +
        '<div class="pc-detail-section-title">💫 Relationship</div>' +
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

// ── Enhanced Gift overlay with auto-populated inventory ───────────────────────
window.openGift = function(userId) {
    _giftTargetId = userId;
    var target = _users.find(function(u){ return u.user_id === userId; });
    if (!target) return;

    el('pc-gift-title').textContent = '🎁 Gift Item to ' + (target.username || 'Unknown');

    var inv = (_currentUser && _currentUser.pet && _currentUser.pet.inventory) || [];
    var sel = el('pc-gift-select');
    sel.innerHTML = '<option value="">Choose an item…</option>';
    
    // Group items by name and sum quantities
    var itemGroups = {};
    inv.forEach(function(item) {
        var name = item.name || 'Unknown';
        if (!itemGroups[name]) {
            itemGroups[name] = {
                name: name,
                type: item.type || 'Material',
                rarity: item.rarity || 'Common',
                count: 0
            };
        }
        itemGroups[name].count += (item.count || item.quantity || 1);
    });
    
    // Sort items by rarity and name
    var rarityOrder = {Mythic: 0, Epic: 1, Rare: 2, Uncommon: 3, Common: 4};
    var sortedItems = Object.values(itemGroups).sort(function(a, b) {
        var rarityDiff = (rarityOrder[a.rarity] || 4) - (rarityOrder[b.rarity] || 4);
        if (rarityDiff !== 0) return rarityDiff;
        return a.name.localeCompare(b.name);
    });
    
    sortedItems.forEach(function(item) {
        var opt = document.createElement('option');
        opt.value = item.name;
        opt.textContent = item.name + ' (x' + item.count + ')' + (item.rarity !== 'Common' ? ' [' + item.rarity + ']' : '');
        opt.dataset.qty = item.count;
        opt.dataset.type = item.type;
        opt.dataset.rarity = item.rarity;
        sel.appendChild(opt);
    });

    el('pc-gift-qty').value = 1;
    el('pc-gift-qty').max = 1;
    el('pc-gift-qty-max').textContent = '/ 1';
    el('pc-gift-item-preview').innerHTML = '';
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

// ── Enhanced Search & Filter Functions ────────────────────────────────────────
window.pcApplyFilters = function() {
    console.log('pcApplyFilters called'); // Debug log
    
    var searchInput = el('pc-search');
    var speciesSelect = el('pc-species-filter');
    var elementSelect = el('pc-element-filter');
    var categorySelect = el('pc-category-filter');
    
    var searchTerm = searchInput ? searchInput.value.toLowerCase() : '';
    var speciesFilter = speciesSelect ? speciesSelect.value.toLowerCase() : '';
    var elementFilter = elementSelect ? elementSelect.value.toLowerCase() : '';
    var categoryFilter = categorySelect ? categorySelect.value.toLowerCase() : '';
    
    console.log('Filters:', {searchTerm, speciesFilter, elementFilter, categoryFilter, relFilter: _currentRelFilter}); // Debug log
    
    _filteredUsers = _users.filter(function(user) {
        var pet = user.pet || {};
        var username = (user.username || '').toLowerCase();
        var petName = (pet.name || '').toLowerCase();
        var species = (pet.species || '').toLowerCase();
        var element1 = (pet.element || '').toLowerCase();
        var element2 = (pet.element2 || '').toLowerCase();
        var category = (pet.category || '').toLowerCase();
        
        // Search filter
        if (searchTerm && !username.includes(searchTerm) && !petName.includes(searchTerm) && 
            !species.includes(searchTerm) && !element1.includes(searchTerm) && !element2.includes(searchTerm)) {
            return false;
        }
        
        // Species filter
        if (speciesFilter && species !== speciesFilter) return false;
        
        // Element filter
        if (elementFilter && element1 !== elementFilter && element2 !== elementFilter) return false;
        
        // Category filter
        if (categoryFilter && category !== categoryFilter) return false;
        
        // Relationship filter
        if (_currentRelFilter !== 'all') {
            if (_currentRelFilter === 'none') {
                if (user.relationship) return false;
            } else {
                if (user.relationship !== _currentRelFilter) return false;
            }
        }
        
        return true;
    });
    
    console.log('Filtered users count:', _filteredUsers.length); // Debug log
    
    // Apply sorting
    pcSortUsers();
    renderPets();
    updateBadge();
};

function pcSortUsers() {
    _filteredUsers.sort(function(a, b) {
        var aVal = pcGetSortValue(a, _currentSort);
        var bVal = pcGetSortValue(b, _currentSort);
        
        if (typeof aVal === 'string') {
            aVal = aVal.toLowerCase();
            bVal = bVal.toLowerCase();
        }
        
        var result = aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
        return _sortAsc ? result : -result;
    });
}

function pcGetSortValue(user, sortKey) {
    var pet = user.pet || {};
    var stats = pet.computed_stats || {};
    
    switch (sortKey) {
        case 'username': return user.username || 'Unknown';
        case 'level': return pet.level || 1;
        case 'hp': return stats.hp || stats.max_health || 100;
        case 'attack': return stats.attack || 10;
        case 'defense': return stats.defense || 5;
        case 'xp': return pet.experience || 0;
        case 'total_xp': return pet.total_xp || 0;
        case 'species': return pet.species || 'Cat';
        case 'element': return pet.element || 'basic';
        case 'relationship': 
            var relOrder = {best_friend: 0, friend: 1, foe: 2, enemy: 3, null: 4};
            return relOrder[user.relationship] || 4;
        default: return 0;
    }
}

window.pcSetRelFilter = function(relType) {
    _currentRelFilter = relType;
    
    // Update active tab (handle both enhanced and inline versions)
    var tabs = document.querySelectorAll('.pc-filter-tab, .pc-filter-tab-enhanced, .pc-filter-tab-inline');
    tabs.forEach(function(tab) {
        tab.classList.remove('pc-filter-active');
        if (tab.dataset.rel === relType) {
            tab.classList.add('pc-filter-active');
        }
    });
    
    pcApplyFilters();
};

window.pcToggleSortDir = function() {
    _sortAsc = !_sortAsc;
    var btn = el('pc-sort-dir');
    var arrow = btn.querySelector('.pc-sort-arrow');
    if (arrow) {
        arrow.textContent = _sortAsc ? '↓' : '↑';
        arrow.style.transform = _sortAsc ? 'rotate(0deg)' : 'rotate(180deg)';
    } else {
        btn.textContent = _sortAsc ? '↓' : '↑';
    }
    pcApplyFilters();
};

// ── Enhanced Leaderboard Functions ─────────────────────────────────────────────
window.pcLbSort = function(sortKey) {
    _leaderboardSort = sortKey;
    
    // Update the select dropdown to show active selection
    var select = el('pc-lb-category');
    if (select) {
        select.value = sortKey;
    }
    
    pcUpdateLeaderboard();
};

function pcUpdateLeaderboard() {
    var sortedUsers = _users.slice().sort(function(a, b) {
        var aVal = pcGetLeaderboardValue(a, _leaderboardSort);
        var bVal = pcGetLeaderboardValue(b, _leaderboardSort);
        return bVal - aVal; // Always descending for leaderboard
    });
    
    var html = sortedUsers.slice(0, 15).map(function(user, index) {
        var value = pcGetLeaderboardValue(user, _leaderboardSort);
        var displayValue = pcFormatLeaderboardValue(value, _leaderboardSort);
        var pet = user.pet || {};
        var petSpecies = pet.species || 'Cat';
        var petName = pet.name || 'Unnamed';
        
        // Add medal emojis for top 3
        var rankDisplay = index + 1;
        if (index === 0) rankDisplay = '🥇';
        else if (index === 1) rankDisplay = '🥈';
        else if (index === 2) rankDisplay = '🥉';
        
        return '<div class="pc-lb-item" onclick="openDetail(\'' + esc(user.user_id) + '\')">' +
            '<div class="pc-lb-rank">' + rankDisplay + '</div>' +
            '<img src="' + esc(user.avatar_url) + '" class="pc-lb-avatar" onerror="this.src=\'/static/Emojis/Pets/Cat.png\'">' +
            '<img src="' + petBadgeImg(pet) + '" class="pc-lb-pet-emoji" onerror="this.src=\'/static/Emojis/Pets/Cat.png\'" title="' + esc(petSpecies) + '">' +
            '<div class="pc-lb-user-info">' +
                '<div class="pc-lb-name">' + esc(user.username) + '</div>' +
                '<div class="pc-lb-pet-name">' + esc(petName) + '</div>' +
            '</div>' +
            '<div class="pc-lb-value">' + displayValue + '</div>' +
        '</div>';
    }).join('');
    
    el('pc-lb-list').innerHTML = html;
}

function pcGetLeaderboardValue(user, key) {
    var pet = user.pet || {};
    var stats = pet.computed_stats || {};
    var battleStats = pet.battle_stats || {};
    var gamblingStats = pet.gambling_stats || {};
    var xpSources = pet.xp_sources || {};
    
    switch (key) {
        // Identity & Progress
        case 'level': return pet.level || 1;
        case 'total_xp': return pet.total_xp || 0;
        case 'xp_progress': 
            var cur = pet.experience || 0;
            var max = pet.xp_for_next_level || 100;
            return Math.round((cur / max) * 100);
            
        // Base Stats
        case 'ATT': return pet.ATT || 0;
        case 'DEF': return pet.DEF || 0;
        case 'INT': return pet.INT || 0;
        case 'DEX': return pet.DEX || 0;
        case 'HAP': return pet.HAP || 0;
        case 'ENE': return pet.ENE || 0;
        
        // Combat Stats
        case 'cs_hp': return stats.hp || stats.max_health || 100;
        case 'cs_attack': return stats.attack || 10;
        case 'cs_defense': return stats.defense || 5;
        
        // Battle Records
        case 'pvp_wins': return (battleStats.pvp || {}).wins || 0;
        case 'pvp_losses': return (battleStats.pvp || {}).losses || 0;
        case 'pvp_wr': 
            var pvp = battleStats.pvp || {};
            var w = pvp.wins || 0, l = pvp.losses || 0;
            return (w + l) > 0 ? Math.round((w / (w + l)) * 100) : 0;
        case 'npc_wins': return (battleStats.npc || {}).wins || 0;
        case 'boss_wins': return (battleStats.boss || {}).wins || 0;
        case 'tournament_wins': return (battleStats.tournament || {}).wins || 0;
        case 'total_wins': 
            return Object.keys(battleStats).reduce(function(sum, type) {
                return sum + ((battleStats[type] || {}).wins || 0);
            }, 0);
        case 'total_losses':
            return Object.keys(battleStats).reduce(function(sum, type) {
                return sum + ((battleStats[type] || {}).losses || 0);
            }, 0);
        case 'eliminations':
            return Object.keys(battleStats).reduce(function(sum, type) {
                return sum + ((battleStats[type] || {}).eliminations || 0);
            }, 0);
            
        // Activity
        case 'missions_completed': return pet.missions_completed || 0;
        case 'missions_failed': return pet.missions_failed || 0;
        case 'training_completed': return pet.training_completed || 0;
        case 'training_failed': return pet.training_failed || 0;
        case 'play_attempts': return pet.play_attempts || 0;
        
        // Casino
        case 'casino_net':
            return Object.keys(gamblingStats).reduce(function(sum, game) {
                var g = gamblingStats[game] || {};
                return sum + (g.xp_won_total || 0) + (g.xp_lost_total || 0);
            }, 0);
        case 'casino_played':
            return Object.keys(gamblingStats).reduce(function(sum, game) {
                var g = gamblingStats[game] || {};
                return sum + (g.total_games_played || g.rounds_played || g.games_played || g.races_played || 0);
            }, 0);
        case 'slots_played': return (gamblingStats.slots || {}).total_games_played || 0;
        case 'blackjack_played': return (gamblingStats.blackjack || {}).rounds_played || 0;
        case 'holdem_played': return (gamblingStats.holdem || {}).games_played || 0;
        case 'craps_played': return (gamblingStats.craps || {}).games_played || 0;
        case 'races_played': return (gamblingStats.races || {}).races_played || 0;
        
        // Economy
        case 'stock_tokens': return pet.stock_tokens || 0;
        case 'ability_points': return pet.ability_points || 0;
        case 'equip_mult': {
            // Full equipment multiplier using the new slot system
            var _eqState = getEquipSetState(pet);
            return _eqState.finalMult;
        }
        case 'inventory_count': return (pet.inventory || []).length;
        
        // XP Sources
        case 'xp_play': return xpSources.play || 0;
        case 'xp_training': return xpSources.training || 0;
        case 'xp_mission': return (xpSources.mission || 0) + (xpSources.mission_fail || 0);
        case 'xp_battle': return (xpSources.battle || 0) + (xpSources.npc_battle || 0) + (xpSources.pvp_battle || 0);
        case 'xp_casino':
            var casinoKeys = ['slots_win','slots_bet','blackjack_win','blackjack_bet','holdem_win','holdem_buyin','holdem_cashout','craps_win','craps_bet','race_win','race_bet','coinflip_win','minigame_bet','rps_win','rps_tie'];
            return casinoKeys.reduce(function(sum, key) {
                return sum + (xpSources[key] || 0);
            }, 0);
            
        default: return 0;
    }
}

function pcFormatLeaderboardValue(value, key) {
    if (key.includes('_wr') || key === 'xp_progress') {
        return value + '%';
    }
    if (key.includes('xp') || key.includes('tokens')) {
        return fmtStat(value);
    }
    return value.toLocaleString();
}

window.pcToggleLeaderboard = function() {
    var list = el('pc-lb-list');
    if (!list) return;
    list.style.display = list.style.display === 'none' ? '' : 'none';
};

// ── Enhanced Initialization ───────────────────────────────────────────────────
function pcInitializeFilters() {
    console.log('Initializing filters...'); // Debug log
    
    // Initialize filtered users
    _filteredUsers = _users.slice();
    
    // Populate species filter
    var species = [...new Set(_users.map(function(u) { return (u.pet || {}).species || 'Cat'; }))].sort();
    var speciesSelect = el('pc-species-filter');
    if (speciesSelect) {
        // Clear existing options except first
        speciesSelect.innerHTML = '<option value="">All Species</option>';
        species.forEach(function(sp) {
            var opt = document.createElement('option');
            opt.value = sp.toLowerCase();
            opt.textContent = sp;
            speciesSelect.appendChild(opt);
        });
        console.log('Species options added:', species.length);
    }
    
    // Populate element filter
    var elements = [...new Set(_users.flatMap(function(u) {
        var pet = u.pet || {};
        var elems = [pet.element, pet.element2].filter(Boolean);
        return elems.map(function(e) { return e || 'basic'; });
    }))].sort();
    var elementSelect = el('pc-element-filter');
    if (elementSelect) {
        elementSelect.innerHTML = '<option value="">All Elements</option>';
        elements.forEach(function(elem) {
            var opt = document.createElement('option');
            opt.value = elem.toLowerCase();
            opt.textContent = cap(elem);
            elementSelect.appendChild(opt);
        });
        console.log('Element options added:', elements.length);
    }
    
    // Populate category filter
    var categories = [...new Set(_users.map(function(u) { return (u.pet || {}).category || 'land'; }))].sort();
    var categorySelect = el('pc-category-filter');
    if (categorySelect) {
        categorySelect.innerHTML = '<option value="">All Categories</option>';
        categories.forEach(function(cat) {
            var opt = document.createElement('option');
            opt.value = cat.toLowerCase();
            opt.textContent = cap(cat);
            categorySelect.appendChild(opt);
        });
        console.log('Category options added:', categories.length);
    }
    
    // Set up sort change handler
    var sortSelect = el('pc-sort-select');
    if (sortSelect) {
        sortSelect.addEventListener('change', function() {
            console.log('Sort changed to:', this.value);
            _currentSort = this.value;
            pcApplyFilters();
        });
    }
    
    // Show controls and compare button
    var controls = el('pc-controls');
    var compareBtn = el('pc-compare-mode-btn');
    if (controls) {
        controls.style.display = '';
        console.log('Controls shown');
    }
    if (compareBtn) {
        compareBtn.style.display = '';
        console.log('Compare button shown');
    }
    
    // Initial filter application
    pcApplyFilters();
}

// ── Enhanced Gift Functions ────────────────────────────────────────────────────
window.pcUpdateGiftQty = function() {
    var sel = el('pc-gift-select');
    var opt = sel.options[sel.selectedIndex];
    var max = opt ? (parseInt(opt.dataset.qty) || 1) : 1;
    var inp = el('pc-gift-qty');
    var maxSpan = el('pc-gift-qty-max');
    
    inp.max = max;
    if (maxSpan) maxSpan.textContent = '/ ' + max;
    if (parseInt(inp.value) > max) inp.value = max;
    
    // Update preview
    var preview = el('pc-gift-item-preview');
    if (preview && opt && opt.value) {
        var itemType = opt.dataset.type || 'Material';
        var itemData2 = (typeof getEquipItem === 'function') ? getEquipItem(opt.value) : null;
        var imgPath = '/static/Emojis/Pets/Equipment/' + equipImgFile(itemData2 || {name: opt.value});
        preview.innerHTML = '<img src="' + imgPath + '" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">';
    } else if (preview) {
        preview.innerHTML = '';
    }
};

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

// ── Enhanced Render grid with filtering ───────────────────────────────────────
function renderPets() {
    var grid = el('pc-pets-grid');
    if (!grid) return;
    
    var usersToRender = _filteredUsers.length > 0 ? _filteredUsers : _users;
    
    if (usersToRender.length === 0) {
        grid.innerHTML = '<div class="col-12 text-center py-5" style="color:var(--text-secondary)">No pets found.</div>';
        return;
    }
    grid.innerHTML = usersToRender.map(buildCard).join('');
    
    // Update compare visuals if in compare mode
    if (_compareMode) {
        pcUpdateCompareVisuals();
    }
}

function updateBadge() {
    var b = el('pc-count-badge');
    if (!b) return;
    var totalCount = _users.length;
    var filteredCount = _filteredUsers.length > 0 ? _filteredUsers.length : totalCount;
    
    if (filteredCount !== totalCount) {
        b.textContent = filteredCount + ' of ' + totalCount + ' pets';
    } else {
        b.textContent = totalCount + ' pet' + (totalCount === 1 ? '' : 's');
    }
    b.style.display = totalCount > 0 ? '' : 'none';
}

// ── Enhanced Load data with initialization ─────────────────────────────────────
function loadPets() {
    console.log('Loading pets...'); // Debug log
    
    el('pc-loading').style.display = '';
    el('pc-main').style.display    = 'none';
    el('pc-error').style.display   = 'none';

    // Load pet info (species descriptions/actions) and pet list in parallel
    Promise.all([
        apiCall('/api/world/pets'),
        apiCall('/api/world/pet-info'),
    ]).then(function(results) {
        var data     = results[0];
        var infoData = results[1];

        console.log('API responses received:', {
            pets: data ? data.users?.length : 0,
            petInfo: infoData ? Object.keys(infoData.pets || {}).length : 0
        });

        // Cache species info globally for buildSpeciesSection
        if (infoData && infoData.pets) {
            _PET_INFO_CACHE = infoData.pets;
        }

        if (!data || !data.users) {
            el('pc-loading').style.display = 'none';
            el('pc-error-msg').textContent = 'Failed to load pet data.';
            el('pc-error').style.display   = '';
            return;
        }
        _users       = data.users;
        _currentUser = _users.find(function(u){ return u.is_current_user; }) || null;
        _filteredUsers = _users.slice(); // Initialize filtered users

        console.log('Data loaded successfully:', {
            totalUsers: _users.length,
            currentUser: _currentUser ? _currentUser.username : 'None'
        });

        // Initialize enhanced features
        pcInitializeFilters();
        pcUpdateLeaderboard();
        
        renderPets();
        updateBadge();

        el('pc-loading').style.display = 'none';
        el('pc-main').style.display    = '';
        
        // Debug function availability after load
        setTimeout(function() {
            if (window.pcDebugFunctions) {
                console.log('Running function availability check...');
                window.pcDebugFunctions();
            }
        }, 500);
        
    }).catch(function(error) {
        console.error('Failed to load pets:', error);
        el('pc-loading').style.display = 'none';
        el('pc-error-msg').textContent = 'Network error — could not load pets.';
        el('pc-error').style.display   = '';
    });
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

// ── Expose all globals for proper functionality ───────────────────────────────
window.openDetail = openDetail;
window.pcApplyFilters = pcApplyFilters;
window.pcSetRelFilter = pcSetRelFilter;
window.pcToggleSortDir = pcToggleSortDir;
window.pcToggleCompareMode = pcToggleCompareMode;
window.pcClearCompare = pcClearCompare;
window.pcLbSort = pcLbSort;
window.pcToggleLeaderboard = pcToggleLeaderboard;
window.pcUpdateGiftQty = pcUpdateGiftQty;
window.pcSendGift = pcSendGift;
window.pcSendGiftInline = pcSendGiftInline;
window.selectGiftItem = selectGiftItem;
window.setRel = setRel;
window.setRelWide = setRelWide;
window.openGift = openGift;
window.closeDetail = closeDetail;
window.closeGiftOverlay = closeGiftOverlay;
window.pcToggleCollapse = pcToggleCollapse;

// Debug function to verify all functions are available
window.pcDebugFunctions = function() {
    var functions = [
        'pcApplyFilters', 'pcSetRelFilter', 'pcToggleSortDir', 'pcToggleCompareMode',
        'pcClearCompare', 'pcLbSort', 'pcToggleLeaderboard', 'openDetail', 'openGift',
        'setRel', 'pcSendGift', 'closeDetail', 'closeGiftOverlay', 'pcUpdateGiftQty'
    ];
    
    console.log('=== Pet Connector Function Check ===');
    functions.forEach(function(funcName) {
        var exists = typeof window[funcName] === 'function';
        console.log(funcName + ': ' + (exists ? '✅ Available' : '❌ Missing'));
    });
    
    console.log('Users loaded:', _users ? _users.length : 0);
    console.log('Filtered users:', _filteredUsers ? _filteredUsers.length : 0);
    console.log('Current filter:', _currentRelFilter);
    console.log('Compare mode:', _compareMode);
    console.log('=== End Function Check ===');
};

// ── Enhanced Rich Comparison Functions ────────────────────────────────────────
function pcBuildRichCompareCard(user, opponent) {
    var pet = user.pet || {};
    var stats = pet.computed_stats || {};
    var oppStats = (opponent.pet || {}).computed_stats || {};
    var petSpecies = pet.species || 'Cat';
    var petName = pet.name || 'Unnamed';
    var level = pet.level || 1;
    
    var compareStats = [
        {key: 'Level', val: level, opp: (opponent.pet || {}).level || 1},
        {key: 'HP', val: stats.hp || stats.max_health || 100, opp: oppStats.hp || oppStats.max_health || 100},
        {key: 'ATK', val: stats.attack || 10, opp: oppStats.attack || 10},
        {key: 'DEF', val: stats.defense || 5, opp: oppStats.defense || 5},
        {key: 'ATT', val: pet.ATT || 0, opp: (opponent.pet || {}).ATT || 0},
        {key: 'DEF', val: pet.DEF || 0, opp: (opponent.pet || {}).DEF || 0},
        {key: 'INT', val: pet.INT || 0, opp: (opponent.pet || {}).INT || 0},
        {key: 'DEX', val: pet.DEX || 0, opp: (opponent.pet || {}).DEX || 0},
        {key: 'HAP', val: pet.HAP || 0, opp: (opponent.pet || {}).HAP || 0},
        {key: 'ENE', val: pet.ENE || 0, opp: (opponent.pet || {}).ENE || 0},
    ];
    
    var statsHtml = compareStats.map(function(stat) {
        var isWinner = stat.val > stat.opp;
        var isLoser = stat.val < stat.opp;
        var cls = isWinner ? 'pc-compare-stat-winner' : isLoser ? 'pc-compare-stat-loser' : '';
        
        return '<div class="pc-compare-stat ' + cls + '">' +
            '<span>' + stat.key + '</span>' +
            '<span>' + fmtStat(stat.val) + '</span>' +
        '</div>';
    }).join('');
    
    return '<div class="pc-compare-pet-rich">' +
        '<div class="pc-compare-pet-header">' +
            '<img src="' + esc(user.avatar_url) + '" class="pc-compare-user-avatar" onerror="this.src=\'/static/Emojis/Pets/Cat.png\'">' +
            '<img src="' + petBadgeImg(pet) + '" class="pc-compare-pet-img" onerror="this.src=\'/static/Emojis/Pets/Cat.png\'">' +
            '<div class="pc-compare-pet-info">' +
                '<div class="pc-compare-pet-name">' + esc(petName) + '</div>' +
                '<div class="pc-compare-user-name">' + esc(user.username) + '</div>' +
                '<div class="pc-compare-pet-level">Level ' + level + '</div>' +
            '</div>' +
        '</div>' +
        '<div class="pc-compare-stats">' + statsHtml + '</div>' +
    '</div>';
}

// ── Boot ───────────────────────────────────────────────────────────────────
loadPets();

})();

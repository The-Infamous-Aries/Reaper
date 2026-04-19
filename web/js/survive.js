(function () {
'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
var _game           = null;
var _myUserId       = null;
var _evtSource      = null;
var _cdInterval     = null;
var _roundCdInterval = null;
var _nextRoundAt    = 0;

// ── DOM helpers ───────────────────────────────────────────────────────────────
function el(id)   { return document.getElementById(id); }
function show(id) { var e = el(id); if (e) e.style.display = ''; }
function hide(id) { var e = el(id); if (e) e.style.display = 'none'; }
function esc(s)   { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

function petImg(sp) { return '/static/Emojis/Pets/' + (sp || 'Cat') + '.png'; }

function addFeedItem(text, type) {
    var feed = el('ss-live-feed');
    if (!feed) return;
    var d = document.createElement('div');
    d.className = 'ss-feed-item ' + (type || 'action');
    d.textContent = text;
    feed.insertBefore(d, feed.firstChild);
    while (feed.children.length > 200) feed.removeChild(feed.lastChild);
}

function fmtTime(secs) {
    secs = Math.max(0, Math.floor(secs));
    var h = Math.floor(secs / 3600);
    var m = Math.floor((secs % 3600) / 60);
    var s = secs % 60;
    return (h > 0 ? h + ':' : '') +
           (h > 0 ? String(m).padStart(2,'0') : m) + ':' +
           String(s).padStart(2,'0');
}

// ── Init ──────────────────────────────────────────────────────────────────────
function init() {
    // Resolve user identity FIRST, then load game state so renderButtons()
    // has _myUserId available on the very first render.
    fetch('/api/discord/me')
        .then(function(r){ return r.ok ? r.json() : null; })
        .then(function(u){
            if (u && u.id) {
                _myUserId = String(u.id);
                hide('ss-login-prompt');
            } else {
                // Not logged in — show prompt but still load state for spectators
                show('ss-login-prompt');
            }
        })
        .catch(function(){})
        .finally(function(){
            // Load game state after identity is known
            fetch('/api/ss/state')
                .then(function(r){ return r.json(); })
                .then(function(g){
                    applyState(g);
                    // Re-render buttons now that _myUserId is resolved
                    renderButtons(g, (g && g.status) || 'none');
                })
                .catch(function(){});
        });

    connectSSE();
}

function connectSSE() {
    if (_evtSource) _evtSource.close();
    _evtSource = new EventSource('/api/ss/events');
    _evtSource.onmessage = function(e) {
        try { handleSSE(JSON.parse(e.data)); } catch(_){}
    };
    _evtSource.onerror = function(){ setTimeout(connectSSE, 5000); };
}

// ── SSE ───────────────────────────────────────────────────────────────────────
function handleSSE(msg) {
    var evt = msg.event, data = msg.data;

    // The SSE 'init' event fires immediately on connect — at that point
    // _myUserId may not be resolved yet. applyState handles null _myUserId
    // gracefully (buttons stay hidden), and the real state load in init()
    // will re-render once the identity fetch completes.
    if (evt === 'init') { applyState(data); return; }

    if (evt === 'player_joined') {
        fetch('/api/ss/state').then(function(r){return r.json();}).then(applyState);
        addFeedItem('🐾 ' + esc(data.participant.pet_name || data.participant.username) + ' joined the lobby!', 'system');
        // Immediately refresh the map so the new pet marker appears without delay.
        // _refreshMap fetches /api/ss/map which now has the position already persisted.
        _refreshMap();
        return;
    }
    if (evt === 'player_left') {
        fetch('/api/ss/state').then(function(r){return r.json();}).then(applyState);
        addFeedItem('🚪 A player left the lobby.', 'system');
        return;
    }
    if (evt === 'lobby_closed') {
        _game = null; applyState({status:'none'});
        addFeedItem('Lobby closed.', 'system');
        return;
    }
    if (evt === 'countdown_started') {
        // NPCs already in participants list — just refresh full state
        fetch('/api/ss/state').then(function(r){return r.json();}).then(function(g){
            applyState(g);
        });
        var npc = data.npc_count || 0;
        addFeedItem('🚀 Game starting in 15 minutes! ' + (data.participants||[]).length + ' participants (' + npc + ' NPCs). DMs sent.', 'system');
        // NPCs were just added — clear animPos so all pets (including new NPCs)
        // snap to their starting positions on the next map fetch.
        _map.animPos = {};
        _refreshMap();
        if (window.ssNavRefresh) window.ssNavRefresh();
        return;
    }
    if (evt === 'game_started') {
        fetch('/api/ss/state').then(function(r){return r.json();}).then(function(g){
            applyState(g);
        });
        addFeedItem('⚔️ The Survivor Series has begun! ' + (data.participants||[]).length + ' enter the arena.', 'system');
        if (data.next_round_at) { _nextRoundAt = data.next_round_at; startRoundCountdown(data.next_round_at); }
        if (window.ssNavRefresh) window.ssNavRefresh();
        return;
    }
    if (evt === 'round') {
        fetch('/api/ss/state').then(function(r){return r.json();}).then(applyState);
        var round = data.round;
        if (round) {
            addFeedItem('━━━ Round ' + round.round_index + ' ━━━', 'system');
            (round.actions||[]).forEach(function(a){ addFeedItem(a,'action'); });
            (round.eliminations||[]).forEach(function(e){ addFeedItem(e,'elim'); });
            addFeedItem(round.remaining_count + ' pets remain.', 'system');
        }
        // Update round label immediately
        var rl = el('ss-round-label');
        if (rl && round) {
            rl.textContent = 'Round ' + round.round_index + ' • Next round in:';
        }
        if (data.next_round_at) { _nextRoundAt = data.next_round_at; startRoundCountdown(data.next_round_at); }
        // Refresh map after a short delay so server positions are updated
        setTimeout(_refreshMap, 400);
        if (window.ssNavRefresh) window.ssNavRefresh();
        return;
    }    if (evt === 'game_over') {
        fetch('/api/ss/state').then(function(r){return r.json();}).then(applyState);
        var w = data.winner;
        if (w) addFeedItem('🏆 ' + esc(w.pet_name || w.username) + ' wins the Survivor Series!', 'system');
        if (window.ssNavRefresh) window.ssNavRefresh();
        return;
    }
    if (evt === 'reset') {
        _game = null; applyState({status:'none'});
        addFeedItem('Game has been reset.', 'system');
        if (window.ssNavRefresh) window.ssNavRefresh();
        return;
    }
}

// ── Full state renderer ───────────────────────────────────────────────────────
function applyState(g) {
    _game = g;
    var status = (g && g.status) || 'none';

    // Status banner
    var banner = el('ss-status-banner');
    if (banner) {
        banner.className = 'ss-status-banner ss-status-' + status;
        var labels = {
            none:      'No Active Game',
            lobby:     '🐾 Lobby Open — Waiting for Players',
            countdown: '⏳ Game Starting Soon',
            running:   '⚔️ GAME IN PROGRESS',
            finished:  '🏆 Game Over',
        };
        banner.textContent = labels[status] || status;
    }

    // Live badge
    if (status === 'running') show('ss-live-badge'); else hide('ss-live-badge');
    // Countdown (start timer)
    if (status === 'countdown' && g.countdown_end) {
        show('ss-countdown-wrap');
        startCountdown(g.countdown_end);
        stopRoundCountdown();
    } else {
        hide('ss-countdown-wrap');
        stopCountdown();
    }

    // Per-round countdown (running state)
    if (status === 'running') {
        var nra = g.next_round_at || 0;
        var nowSec = Math.floor(Date.now() / 1000);
        if (nra && nra > nowSec) {
            // Always (re)start if the epoch changed or timer isn't running
            if (nra !== _nextRoundAt || !_roundCdInterval) {
                _nextRoundAt = nra;
                startRoundCountdown(nra);
            }
        } else {
            stopRoundCountdown();
        }
    } else {
        stopRoundCountdown();
    }

    // Winner
    if (status === 'finished' && g.winner) {
        show('ss-winner-wrap');
        var wi = el('ss-winner-img'), wn = el('ss-winner-name'), ws = el('ss-winner-sub');
        if (wi) { wi.src = petImg(g.winner.species); wi.onerror = function(){ this.src='/static/Emojis/Pets/Cat.png'; }; }
        if (wn) wn.textContent = (g.winner.pet_name || g.winner.username) + ' 🏆';
        if (ws) ws.textContent = 'Champion • ' + (g.rounds||[]).length + ' rounds';
    } else {
        hide('ss-winner-wrap');
    }

    // Round label
    var rl = el('ss-round-label');
    if (rl) {
        if (status === 'running') {
            var rnd = g.round_index || 0;
            rl.textContent = rnd === 0 ? 'Starting • Next round in:' : 'Round ' + rnd + ' • Next round in:';
        } else if (status === 'finished') {
            rl.textContent = 'Game over — ' + (g.rounds||[]).length + ' rounds';
        } else {
            rl.textContent = 'Waiting...';
        }
    }

    renderButtons(g, status);

    // Populate feed from persisted state (only on full state load, not SSE events)
    if (g && g.feed && g.feed.length > 0) {
        var feed = el('ss-live-feed');
        if (feed) {
            // Only repopulate if feed is empty or just has the default placeholder
            var isEmpty = feed.children.length === 0 ||
                (feed.children.length === 1 && feed.children[0].classList.contains('system'));
            if (isEmpty) {
                feed.innerHTML = '';
                // Render oldest first (feed is stored oldest→newest, display newest on top)
                var items = g.feed.slice(-200); // last 200
                for (var i = items.length - 1; i >= 0; i--) {
                    var d = document.createElement('div');
                    d.className = 'ss-feed-item ' + (items[i].type || 'system');
                    d.textContent = items[i].text;
                    feed.appendChild(d);
                }
            }
        }
    }

    // Update map
    _updateMapVisibility(status);
}

// ── Buttons ───────────────────────────────────────────────────────────────────
function renderButtons(g, status) {
    var parts     = (g && g.participants) || [];
    var isJoined  = _myUserId && parts.some(function(p){ return String(p.user_id) === String(_myUserId); });
    var realCount = parts.filter(function(p){ return !p.is_npc; }).length;

    hide('ss-join-btn'); hide('ss-start-btn'); hide('ss-reset-btn');
    if (!_myUserId) return;

    if (status === 'none' || status === 'lobby') {
        if (!isJoined) {
            show('ss-join-btn');
        } else {
            if (realCount >= 2) show('ss-start-btn');
        }
    }
    if (status === 'finished') show('ss-reset-btn');
}

// ── Countdown (game start) ────────────────────────────────────────────────────
function startCountdown(endEpoch) {
    stopCountdown();
    function tick() {
        var rem = endEpoch - Math.floor(Date.now()/1000);
        var t = el('ss-countdown-timer');
        if (t) t.textContent = fmtTime(rem);
        if (rem <= 0) stopCountdown();
    }
    tick();
    _cdInterval = setInterval(tick, 1000);
}
function stopCountdown() {
    if (_cdInterval) { clearInterval(_cdInterval); _cdInterval = null; }
}

// ── Per-round countdown (running state) ───────────────────────────────────────
function startRoundCountdown(endEpoch) {
    stopRoundCountdown();
    // Also update the dashboard nav timer if available
    if (window.ssNavSetRoundTimer) window.ssNavSetRoundTimer(endEpoch);
    function tick() {
        var rem = endEpoch - Math.floor(Date.now()/1000);
        var span = el('ss-round-timer');
        if (span) span.textContent = rem > 0 ? fmtTime(rem) : '0:00';
        if (rem <= 0) stopRoundCountdown();
    }
    tick();
    _roundCdInterval = setInterval(tick, 1000);
}
function stopRoundCountdown() {
    if (_roundCdInterval) { clearInterval(_roundCdInterval); _roundCdInterval = null; }
    var span = el('ss-round-timer');
    if (span) span.textContent = '';
}

// ── Start modal ───────────────────────────────────────────────────────────────
window.ssOpenStartModal = function() {
    var modal = el('ss-start-modal');
    if (!modal) return;

    var parts     = (_game && _game.participants) || [];
    var realCount = parts.filter(function(p){ return !p.is_npc; }).length;
    var maxNpcs   = Math.max(0, 100 - realCount);

    var slider = el('sm-npc-slider');
    if (slider) { slider.max = maxNpcs; slider.value = 0; }

    var maxLbl = el('sm-slider-max-label');
    if (maxLbl) maxLbl.textContent = 'max ' + maxNpcs;

    var rc = el('sm-real-count'); if (rc) rc.textContent = realCount;
    var nc = el('sm-npc-count');  if (nc) nc.textContent = 0;
    var tc = el('sm-total-count'); if (tc) tc.textContent = realCount;
    var nv = el('sm-npc-val');    if (nv) nv.textContent = 0;

    modal.style.display = 'flex';
};

window.ssCloseStartModal = function() {
    var modal = el('ss-start-modal');
    if (modal) modal.style.display = 'none';
};

window.ssModalSliderChange = function() {
    var slider = el('sm-npc-slider');
    if (!slider) return;
    var npcVal = parseInt(slider.value, 10) || 0;

    var parts     = (_game && _game.participants) || [];
    var realCount = parts.filter(function(p){ return !p.is_npc; }).length;

    var nv = el('sm-npc-val');    if (nv) nv.textContent = npcVal;
    var nc = el('sm-npc-count');  if (nc) nc.textContent = npcVal;
    var tc = el('sm-total-count'); if (tc) tc.textContent = realCount + npcVal;
};

window.ssConfirmStart = function() {
    var slider = el('sm-npc-slider');
    var npcCount = slider ? (parseInt(slider.value, 10) || 0) : 0;

    var btn = el('sm-confirm-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Starting...'; }

    fetch('/api/ss/start', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({npc_count: npcCount})
    })
    .then(function(r){ return r.json(); })
    .then(function(d) {
        if (btn) { btn.disabled = false; btn.textContent = '⚔️ Start'; }
        if (d.error) { alert(d.error); return; }
        ssCloseStartModal();
    })
    .catch(function(e) {
        if (btn) { btn.disabled = false; btn.textContent = '⚔️ Start'; }
        alert('Error: ' + e.message);
    });
};

// ── Equipment multiplier (mirrors pet_brain.py StatsCalculator._calculate_equipment_bonuses) ──
function calcEquipMultiplier(pet) {
    var eq     = (pet && pet.equipment) || {};
    var level  = parseInt((pet && pet.level) || 1, 10);
    var specs  = ((pet && (pet.specializations || pet.Spec)) || []).map(function(s){ return s.toUpperCase(); });
    var levelBonus = Math.floor(level / 50);

    // Collect typed items
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
    var hatEquipped = !!(hat && typeof hat === 'object' && hat.name);
    if (hatEquipped) items.push({t:'Hat', item:hat});

    // Count duplicates
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

    // Hat spec matching
    var hatSpecMatches = 0;
    if (hatEquipped && specs.length) {
        var hatBonusStats = Object.keys((hat.bonuses) || {}).map(function(s){ return s.toUpperCase(); });
        hatSpecMatches = hatBonusStats.filter(function(s){ return specs.indexOf(s) !== -1; }).length;
    }

    // Set multiplier
    var fullSet = hasMatPair && hasGemPair && hasMonPair && hatEquipped;
    var setMult;
    if (fullSet) {
        setMult = hatSpecMatches >= 2 ? 4 : 3;
    } else {
        setMult = 1;
    }

    return Math.max(1, setMult + levelBonus);
}

// ── Join modal ────────────────────────────────────────────────────────────────
window.ssOpenJoinModal = function() {
    var modal = el('ss-join-modal');
    if (!modal) return;

    // Populate pet stat card from the current user's participant record if already
    // in the game state, otherwise fetch fresh from /api/discord/me + /api/pets/me
    var parts = (_game && _game.participants) || [];
    var myPart = _myUserId
        ? parts.find(function(p){ return String(p.user_id) === String(_myUserId); })
        : null;

    function _fillCard(name, species, level, multiplier, element, element2) {
        var img = el('sj-pet-img');
        if (img) { img.src = petImg(species); }

        var nameEl = el('sj-pet-name');
        if (nameEl) nameEl.textContent = name || 'Your Pet';

        var metaEl = el('sj-pet-meta');
        if (metaEl) {
            var e2 = element2 ? ' / ' + element2 : '';
            metaEl.textContent = (species || '?') + ' • Lv.' + (level||1) + ' • ×' + (multiplier||1) + ' • ' + (element||'basic') + e2;
        }

        var scoreEl = el('sj-survive-score');
        var score = (level||1) / Math.max(1, multiplier||1) / 10;
        if (scoreEl) scoreEl.textContent = score.toFixed(2);

        var noteEl = el('sj-score-note');
        if (noteEl) {
            var tier = score >= 10 ? '🔥 Terrifying' : score >= 5 ? '⚡ Strong' : score >= 2 ? '🐾 Decent' : '🥚 Baby';
            noteEl.textContent = '(' + tier + ')';
        }
    }

    // Always fetch live pet data — never use the stale game snapshot
    fetch('/api/user/pet')
        .then(function(r){ return r.ok ? r.json() : null; })
        .then(function(d) {
            if (d && d.has_pet) {
                var mult = calcEquipMultiplier(d);
                _fillCard(d.name, d.species, d.level, mult, d.element, d.element2);
            }
        })
        .catch(function(){});

    modal.style.display = 'flex';
};

window.ssCloseJoinModal = function() {
    var modal = el('ss-join-modal');
    if (modal) modal.style.display = 'none';
};

window.ssConfirmJoin = function() {
    var btn = el('sj-confirm-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Joining...'; }

    fetch('/api/ss/join', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'})
        .then(function(r){ return r.json(); })
        .then(function(d) {
            if (btn) { btn.disabled = false; btn.textContent = '⚔️ Proceed with Join'; }
            if (d.error) { alert(d.error); return; }
            window.ssCloseJoinModal();
            if (d.game) applyState(d.game);
        })
        .catch(function(e) {
            if (btn) { btn.disabled = false; btn.textContent = '⚔️ Proceed with Join'; }
            alert('Error: ' + e.message);
        });
};


function ssLeave() {
    if (!confirm('Leave the lobby?')) return;
    fetch('/api/ss/leave', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'})
        .then(function(r){ return r.json(); })
        .then(function(d){
            if (d.error) { alert(d.error); return; }
            fetch('/api/ss/state').then(function(r2){return r2.json();}).then(applyState);
        })
        .catch(function(e){ alert('Error: ' + e.message); });
}

function ssReset() {
    if (!confirm('Reset the game? This will clear all data.')) return;
    fetch('/api/ss/reset', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'})
        .then(function(r){ return r.json(); })
        .then(function(d){ if (d.error) alert(d.error); })
        .catch(function(e){ alert('Error: ' + e.message); });
}

// ── Expose ────────────────────────────────────────────────────────────────────
window.ssLeave = ssLeave;
window.ssReset = ssReset;

// ── Boot ──────────────────────────────────────────────────────────────────────
init();

})();


// ── Pet Survivor Series JavaScript ──────────────────────────────────────────
'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
var _game           = null;
var _myUserId       = null;
var _evtSource      = null;
var _cdInterval     = null;
var _roundCdInterval = null;
var _nextRoundAt    = 0;
var _pollInterval   = null;  // setInterval ID for the 10s state poll

// New state for enhanced start menu
var _gameMode       = 'classic';
var _difficulty     = 'normal';
var _selectedPets   = [];
var _availablePets  = [];

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
    console.log('[survive.js] init() called');
    
    // Always fetch the latest state first, regardless of SSE
    function loadGameState() {
        console.log('[survive.js] Loading game state...');
        return fetch('/api/ss/state')
            .then(function(r){ 
                console.log('[survive.js] ss/state response:', r.status);
                return r.json(); 
            })
            .then(function(g){
                console.log('[survive.js] Game state received:', g);
                applyState(g);
                // Re-render buttons now that _myUserId is resolved
                renderButtons(g, (g && g.status) || 'none');
            })
            .catch(function(err){
                console.error('[survive.js] Error fetching game state:', err);
            });
    }
    
    // Resolve user identity FIRST, then load game state so renderButtons()
    // has _myUserId available on the very first render.
    console.log('[survive.js] Fetching user identity...');
    fetch('/api/discord/me')
        .then(function(r){ return r.ok ? r.json() : null; })
        .then(function(u){
            console.log('[survive.js] Discord user:', u);
            if (u && u.id) {
                _myUserId = String(u.id);
                hide('ss-login-prompt');
            } else {
                // Not logged in — show prompt but still load state for spectators
                show('ss-login-prompt');
            }
        })
        .catch(function(err){
            console.error('[survive.js] Error fetching discord user:', err);
        })
        .finally(function(){
            console.log('[survive.js] User identity resolved, loading game state...');
            // Load game state first so the DOM is fully painted before SSE
            // starts firing events (avoids "Banner element not found" on fast init events)
            loadGameState().finally(function() {
                connectSSE();
            });
        });
    
    // Also refresh state every 10 seconds as a fallback
    if (_pollInterval) clearInterval(_pollInterval);
    _pollInterval = setInterval(loadGameState, 10000);
}

// ── Cleanup on SPA navigation away from survive page ─────────────────────────
document.addEventListener('dashboardPageLoaded', function(e) {
    if (e.detail && e.detail.page === 'survive.html') return; // still on survive page
    // Navigated away — tear down intervals and SSE
    if (_pollInterval)      { clearInterval(_pollInterval);      _pollInterval = null; }
    if (_cdInterval)        { clearInterval(_cdInterval);        _cdInterval = null; }
    if (_roundCdInterval)   { clearInterval(_roundCdInterval);   _roundCdInterval = null; }
    if (_evtSource)         { _evtSource.close();                _evtSource = null; }
    console.log('[survive.js] Cleaned up intervals and SSE on page navigation');
});

function connectSSE() {
    console.log('[survive.js] Connecting to SSE...');
    if (_evtSource) _evtSource.close();
    _evtSource = new EventSource('/api/ss/events');
    _evtSource.onmessage = function(e) {
        console.log('[survive.js] SSE message received:', e.data);
        try { handleSSE(JSON.parse(e.data)); } catch(err) { console.error('[survive.js] SSE parse error:', err); }
    };
    _evtSource.onerror = function(err){ 
        console.error('[survive.js] SSE error:', err);
        // Only reconnect if we're still on the survive page
        if (_evtSource) setTimeout(connectSSE, 5000); 
    };
    _evtSource.onopen = function() {
        console.log('[survive.js] SSE connection opened');
    };
}

// ── SSE ───────────────────────────────────────────────────────────────────────
function handleSSE(msg) {
    var evt = msg.event, data = msg.data;
    console.log('[survive.js] SSE event:', evt, data);

    // The SSE 'init' event fires immediately on connect — at that point
    // _myUserId may not be resolved yet. applyState handles null _myUserId
    // gracefully (buttons stay hidden), and the real state load in init()
    // will re-render once the identity fetch completes.
    if (evt === 'init') { 
        console.log('[survive.js] SSE init event, applying state:', data);
        // Only apply SSE init state if we don't already have a better state
        if (!_game || _game.status === 'none') {
            applyState(data);
        } else {
            console.log('[survive.js] SSE init ignored, already have state:', _game.status);
        }
        return; 
    }

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
    console.log('[survive.js] applyState called with:', g);
    _game = g;
    var status = (g && g.status) || 'none';
    console.log('[survive.js] Status:', status);

    // Status banner - wait for DOM to be ready
    function updateBanner() {
        var banner = el('ss-status-banner');
        console.log('[survive.js] Banner element:', banner);
        console.log('[survive.js] All elements with ss-status-banner ID:', document.querySelectorAll('#ss-status-banner'));
        console.log('[survive.js] All elements with ss-status-banner class:', document.querySelectorAll('.ss-status-banner'));
        
        if (banner) {
            console.log('[survive.js] Current banner text before update:', banner.textContent);
            console.log('[survive.js] Current banner class before update:', banner.className);
            
            banner.className = 'ss-status-banner ss-status-' + status;
            var labels = {
                none:      'No Active Game',
                lobby:     '🐾 Lobby Open — Waiting for Players',
                countdown: '⏳ Game Starting Soon',
                running:   '⚔️ GAME IN PROGRESS',
                finished:  '🏆 Game Over',
            };
            banner.textContent = labels[status] || status;
            
            console.log('[survive.js] Banner updated to:', banner.textContent, 'with class:', banner.className);
            console.log('[survive.js] Banner text after update:', banner.textContent);
            console.log('[survive.js] Banner innerHTML after update:', banner.innerHTML);
            return true;
        } else {
            console.error('[survive.js] Banner element not found!');
            return false;
        }
    }
    
    // Retry banner update if element not found, with more robust checking
    var retryCount = 0;
    var maxRetries = 10;
    
    function tryUpdateBanner() {
        if (updateBanner()) {
            return; // Success
        }
        
        retryCount++;
        if (retryCount < maxRetries) {
            console.log('[survive.js] Retrying banner update in 100ms... (attempt ' + (retryCount + 1) + '/' + maxRetries + ')');
            setTimeout(tryUpdateBanner, 100);
        } else {
            console.error('[survive.js] Failed to update banner after ' + maxRetries + ' attempts');
            // Try to create the banner element if it doesn't exist
            var container = document.querySelector('#ss-root');
            if (container && !el('ss-status-banner')) {
                console.log('[survive.js] Creating missing banner element');
                var banner = document.createElement('div');
                banner.id = 'ss-status-banner';
                banner.className = 'ss-status-banner ss-status-' + status;
                var labels = {
                    none:      'No Active Game',
                    lobby:     '🐾 Lobby Open — Waiting for Players',
                    countdown: '⏳ Game Starting Soon',
                    running:   '⚔️ GAME IN PROGRESS',
                    finished:  '🏆 Game Over',
                };
                banner.textContent = labels[status] || status;
                
                // Insert after the divider
                var divider = container.querySelector('.ss-divider');
                if (divider && divider.nextSibling) {
                    container.insertBefore(banner, divider.nextSibling);
                } else {
                    container.appendChild(banner);
                }
                console.log('[survive.js] Banner element created and inserted');
            }
        }
    }
    
    tryUpdateBanner();

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

    // Update map - only if function is available
    if (typeof _updateMapVisibility === 'function') {
        _updateMapVisibility(status);
    } else {
        console.log('[survive.js] _updateMapVisibility not available, map script may not be loaded');
    }
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
            // Allow single player to start (removed minimum 2 player requirement)
            show('ss-start-btn');
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
    var maxNpcs   = Math.max(0, 100 - realCount - _selectedPets.length);

    var slider = el('sm-npc-slider');
    if (slider) { 
        slider.max = maxNpcs; 
        slider.value = Math.min(10, maxNpcs); // Default to 10 NPCs or max available
    }

    var maxLbl = el('sm-slider-max-label');
    if (maxLbl) maxLbl.textContent = 'max ' + maxNpcs;

    // Reset state
    _gameMode = 'classic';
    _difficulty = 'normal';
    _selectedPets = [];
    
    // Update UI
    ssSetGameMode('classic');
    ssSetDifficulty('normal');
    ssUpdateCounts();
    ssUpdateSelectedPetsDisplay();

    // Reset the add-all-user-pets toggle
    var toggle = el('sm-add-all-toggle');
    if (toggle) toggle.checked = false;

    modal.style.display = 'flex';
};

window.ssCloseStartModal = function() {
    var modal = el('ss-start-modal');
    if (modal) modal.style.display = 'none';
};

// ── Game Mode Selection ───────────────────────────────────────────────────────
window.ssSetGameMode = function(mode) {
    _gameMode = mode;
    
    // Update button styles
    var classicBtn = el('sm-mode-classic');
    var quickBtn = el('sm-mode-quick');
    
    if (classicBtn && quickBtn) {
        classicBtn.className = 'ss-mode-btn' + (mode === 'classic' ? ' active' : '');
        quickBtn.className = 'ss-mode-btn' + (mode === 'quick' ? ' active' : '');
        
        if (mode === 'classic') {
            classicBtn.style.background = 'rgba(255,215,0,0.1)';
            classicBtn.style.borderColor = 'var(--gold-primary)';
            classicBtn.style.color = 'var(--gold-primary)';
            quickBtn.style.background = 'rgba(0,0,0,0.3)';
            quickBtn.style.borderColor = 'rgba(255,255,255,0.2)';
            quickBtn.style.color = 'var(--text-secondary)';
        } else {
            quickBtn.style.background = 'rgba(255,215,0,0.1)';
            quickBtn.style.borderColor = 'var(--gold-primary)';
            quickBtn.style.color = 'var(--gold-primary)';
            classicBtn.style.background = 'rgba(0,0,0,0.3)';
            classicBtn.style.borderColor = 'rgba(255,255,255,0.2)';
            classicBtn.style.color = 'var(--text-secondary)';
        }
    }
};

// ── Difficulty Selection ──────────────────────────────────────────────────────
window.ssSetDifficulty = function(diff) {
    _difficulty = diff;
    
    // Update button styles
    var easyBtn = el('sm-diff-easy');
    var normalBtn = el('sm-diff-normal');
    var hardBtn = el('sm-diff-hard');
    
    // Reset all buttons
    [easyBtn, normalBtn, hardBtn].forEach(function(btn) {
        if (btn) {
            btn.className = 'ss-diff-btn';
            btn.style.opacity = '0.6';
        }
    });
    
    // Highlight selected
    var activeBtn = diff === 'easy' ? easyBtn : diff === 'normal' ? normalBtn : hardBtn;
    if (activeBtn) {
        activeBtn.className = 'ss-diff-btn active';
        activeBtn.style.opacity = '1';
    }
    
    // Update description
    var desc = el('sm-diff-desc');
    if (desc) {
        var descriptions = {
            easy: 'NPCs will be weaker than player levels for easier victories',
            normal: 'NPCs will be calibrated to player levels with balanced stats',
            hard: 'NPCs will be stronger than player levels for maximum challenge'
        };
        desc.textContent = descriptions[diff] || descriptions.normal;
    }
};

// ── Pet Selection ─────────────────────────────────────────────────────────────
window.ssToggleAddAll = function() {
    var toggle = el('sm-add-all-toggle');
    var manualSection = el('sm-manual-selection');
    
    if (toggle && manualSection) {
        if (toggle.checked) {
            manualSection.style.display = 'none';
            _selectedPets = []; // Clear manual selections
        } else {
            manualSection.style.display = 'block';
        }
        ssUpdateCounts();
        ssUpdateSelectedPetsDisplay();
    }
};

window.ssOpenPetSelector = function() {
    var modal = el('ss-pet-selector-modal');
    if (!modal) return;
    
    modal.style.display = 'flex';
    ssLoadAvailablePets();
};

window.ssClosePetSelector = function() {
    var modal = el('ss-pet-selector-modal');
    if (modal) modal.style.display = 'none';
};

window.ssLoadAvailablePets = function() {
    var listEl = el('ps-pet-list');
    if (!listEl) return;
    
    listEl.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--text-secondary);font-size:0.75rem">Loading pets...</div>';
    
    // Fetch all pets from the server
    fetch('/api/pets/all')
        .then(function(r) { return r.ok ? r.json() : null; })
        .then(function(data) {
            if (data && data.pets) {
                _availablePets = data.pets;
                ssRenderPetList();
            } else {
                listEl.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--text-secondary);font-size:0.75rem">No pets found</div>';
            }
        })
        .catch(function() {
            listEl.innerHTML = '<div style="text-align:center;padding:2rem;color:#f44336;font-size:0.75rem">Error loading pets</div>';
        });
};

window.ssRenderPetList = function() {
    var listEl = el('ps-pet-list');
    var searchEl = el('ps-search');
    if (!listEl) return;
    
    var searchTerm = searchEl ? searchEl.value.toLowerCase() : '';
    var filteredPets = _availablePets.filter(function(pet) {
        if (!searchTerm) return true;
        var username = (pet.username || '').toLowerCase();
        var petName = (pet.pet_name || '').toLowerCase();
        return username.includes(searchTerm) || petName.includes(searchTerm);
    });
    
    if (filteredPets.length === 0) {
        listEl.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--text-secondary);font-size:0.75rem">No pets match your search</div>';
        return;
    }
    
    var html = '';
    filteredPets.forEach(function(pet) {
        var isSelected = _selectedPets.indexOf(pet.user_id) !== -1;
        var checkmark = isSelected ? '✓' : '';
        var bgColor = isSelected ? 'rgba(76,175,80,0.1)' : 'rgba(0,0,0,0.2)';
        var borderColor = isSelected ? 'rgba(76,175,80,0.5)' : 'rgba(255,255,255,0.1)';
        
        html += '<div onclick="ssTogglePetSelection(\'' + pet.user_id + '\')" style="' +
            'display:flex;align-items:center;gap:0.8rem;padding:0.6rem;margin-bottom:0.3rem;' +
            'background:' + bgColor + ';border:1px solid ' + borderColor + ';' +
            'border-radius:6px;cursor:pointer;transition:all 0.2s">' +
            '<img src="' + petImg(pet.species) + '" style="width:32px;height:32px;object-fit:contain" ' +
            'onerror="this.src=\'/static/Emojis/Pets/Cat.png\'">' +
            '<div style="flex:1;min-width:0">' +
            '<div style="font-size:0.75rem;font-weight:600;color:var(--text-primary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' +
            esc(pet.pet_name || 'Unnamed Pet') + '</div>' +
            '<div style="font-size:0.65rem;color:var(--text-secondary)">' +
            esc(pet.username || 'Unknown User') + ' • Lv.' + (pet.level || 1) + '</div>' +
            '</div>' +
            '<div style="width:20px;height:20px;border:2px solid ' + (isSelected ? '#4caf50' : 'rgba(255,255,255,0.3)') + ';' +
            'border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:0.7rem;color:#4caf50;font-weight:900">' +
            checkmark + '</div>' +
            '</div>';
    });
    
    listEl.innerHTML = html;
    ssUpdateSelectedCount();
};

window.ssTogglePetSelection = function(userId) {
    var index = _selectedPets.indexOf(userId);
    if (index === -1) {
        _selectedPets.push(userId);
    } else {
        _selectedPets.splice(index, 1);
    }
    ssRenderPetList();
    ssUpdateCounts();
};

window.ssFilterPets = function() {
    ssRenderPetList();
};

window.ssClearSelectedPets = function() {
    _selectedPets = [];
    ssRenderPetList();
    ssUpdateCounts();
};

window.ssConfirmPetSelection = function() {
    ssClosePetSelector();
    ssUpdateSelectedPetsDisplay();
    ssUpdateCounts();
};

window.ssUpdateSelectedCount = function() {
    var countEl = el('ps-selected-count');
    if (countEl) countEl.textContent = _selectedPets.length;
};

window.ssUpdateSelectedPetsDisplay = function() {
    var container = el('sm-selected-pets');
    if (!container) return;
    
    if (_selectedPets.length === 0) {
        container.innerHTML = '<div style="font-size:0.65rem;color:var(--text-secondary);text-align:center;padding:1rem">' +
            'No pets selected. Click "Add Pets" to choose specific pets.</div>';
        return;
    }
    
    var html = '';
    _selectedPets.forEach(function(userId) {
        var pet = _availablePets.find(function(p) { return p.user_id === userId; });
        if (pet) {
            html += '<div style="display:flex;align-items:center;gap:0.5rem;padding:0.4rem;margin-bottom:0.2rem;' +
                'background:rgba(76,175,80,0.1);border:1px solid rgba(76,175,80,0.3);border-radius:4px">' +
                '<img src="' + petImg(pet.species) + '" style="width:24px;height:24px;object-fit:contain" ' +
                'onerror="this.src=\'/static/Emojis/Pets/Cat.png\'">' +
                '<div style="flex:1;min-width:0">' +
                '<div style="font-size:0.65rem;font-weight:600;color:var(--text-primary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' +
                esc(pet.pet_name || 'Unnamed Pet') + '</div>' +
                '</div>' +
                '<button onclick="ssRemoveSelectedPet(\'' + userId + '\')" style="' +
                'background:none;border:none;color:#f44336;cursor:pointer;font-size:0.8rem;padding:0 2px">×</button>' +
                '</div>';
        }
    });
    
    container.innerHTML = html;
};

window.ssRemoveSelectedPet = function(userId) {
    var index = _selectedPets.indexOf(userId);
    if (index !== -1) {
        _selectedPets.splice(index, 1);
        ssUpdateSelectedPetsDisplay();
        ssUpdateCounts();
    }
};

// ── Count Updates ─────────────────────────────────────────────────────────────
window.ssUpdateCounts = function() {
    var parts = (_game && _game.participants) || [];
    var realCount = parts.filter(function(p){ return !p.is_npc; }).length;
    var selectedCount = _selectedPets.length;
    var slider = el('sm-npc-slider');
    var npcCount = slider ? parseInt(slider.value, 10) || 0 : 0;
    
    var toggle = el('sm-add-all-toggle');
    var addingAll = toggle ? toggle.checked : false;
    
    // Estimate total if adding all pets
    var estimatedTotal = realCount + npcCount;
    if (addingAll) {
        estimatedTotal = '~' + (realCount + npcCount); // Approximate since we don't know exact count
    } else {
        estimatedTotal = realCount + selectedCount + npcCount;
    }
    
    var rc = el('sm-real-count'); 
    if (rc) rc.textContent = addingAll ? realCount + '+' : realCount + selectedCount;
    
    var nc = el('sm-npc-count');  
    if (nc) nc.textContent = npcCount;
    
    var tc = el('sm-total-count'); 
    if (tc) tc.textContent = estimatedTotal;
    
    var nv = el('sm-npc-val');    
    if (nv) nv.textContent = npcCount;
};

window.ssModalSliderChange = function() {
    ssUpdateCounts();
};

window.ssConfirmStart = function() {
    var slider = el('sm-npc-slider');
    var npcCount = slider ? (parseInt(slider.value, 10) || 0) : 0;
    var toggle = el('sm-add-all-toggle');
    var addAllUserPets = toggle ? toggle.checked : false;

    var btn = el('sm-confirm-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Starting...'; }

    // Prepare enhanced request data
    var requestData = {
        npc_count: npcCount,
        add_all_user_pets: addAllUserPets,
        game_mode: _gameMode,
        difficulty: _difficulty,
        selected_pets: addAllUserPets ? [] : _selectedPets
    };

    fetch('/api/ss/start', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(requestData)
    })
    .then(function(r){ return r.json(); })
    .then(function(d) {
        if (btn) { btn.disabled = false; btn.textContent = '⚔️ Start Battle'; }
        if (d.error) { alert(d.error); return; }
        ssCloseStartModal();
    })
    .catch(function(e) {
        if (btn) { btn.disabled = false; btn.textContent = '⚔️ Start Battle'; }
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

    // ── Survive score ability multiplier (mirrors get_ability_effect in ability_tree.py) ──
    // Abilities that boost survive_score_mult: att_survive_aggression, def_survive_endurance
    // Effect formula: base + per_level * (level - 1), multiplicative across all abilities.
    var _SS_ABILITY_DEFS = [
        { id: 'att_survive_aggression', base: 1.1, per_level: 0.1 },
        { id: 'def_survive_endurance',  base: 1.1, per_level: 0.1 },
    ];
    function calcSsAbilityMult(pet) {
        var abilities = (pet && pet.abilities) || {};
        var result = 1.0;
        _SS_ABILITY_DEFS.forEach(function(ab) {
            var lvl = parseInt(abilities[ab.id] || 0, 10);
            if (lvl > 0) {
                result *= ab.base + ab.per_level * (lvl - 1);
            }
        });
        return result;
    }

    // ── Stat mastery multiplier (mirrors get_all_mastery_multipliers in ability_tree.py) ──
    // Formula: 1.0 + points * 0.1 per stat. We use the average across all 6 stats.
    // stat_mastery stores either a plain number (points) or {points: N} (new format).
    var _SS_STATS = ['ATT', 'DEF', 'INT', 'DEX', 'HAP', 'ENE'];
    function calcStatMasteryMult(pet) {
        var mastery = (pet && pet.stat_mastery) || {};
        var total = 0;
        _SS_STATS.forEach(function(s) {
            var raw = mastery[s] || 0;
            var pts = (typeof raw === 'object' && raw !== null) ? (raw.points || 0) : parseInt(raw, 10);
            total += 1.0 + pts * 0.1;
        });
        return total / _SS_STATS.length;
    }

    // ── Advantage mastery bonuses (mirrors get_advantage_mastery_bonus in ability_tree.py) ──
    // Formula: points * 0.1 flat bonus added to the 1.2 base advantage multiplier.
    function calcAdvMasteryBonus(pet, key) {
        var mastery = (pet && pet.advantage_mastery) || {};
        var pts = parseInt(mastery[key] || 0, 10);
        return pts * 0.1;
    }

    function _fillCard(name, species, level, multiplier, ssAbilityMult, statMasteryMult, element, element2, startingCharge, chargeLimit) {
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
        var ssAMult = ssAbilityMult || 1.0;
        var smMult  = statMasteryMult || 1.0;
        var score = (level||1) / Math.max(1, multiplier||1) / 10 * ssAMult * smMult;
        if (scoreEl) scoreEl.textContent = score.toFixed(2);

        var noteEl = el('sj-score-note');
        if (noteEl) {
            var tier = score >= 10 ? '🔥 Terrifying' : score >= 5 ? '⚡ Strong' : score >= 2 ? '🐾 Decent' : '🥚 Baby';
            var multNote = '';
            if (ssAMult !== 1.0) multNote += ' ×' + ssAMult.toFixed(2) + ' ability';
            if (smMult  !== 1.0) multNote += ' ×' + smMult.toFixed(2) + ' mastery';
            noteEl.textContent = '(' + tier + (multNote ? ' |' + multNote : '') + ')';
        }

        // Charge info
        var chargeEl = el('sj-charge-info');
        if (chargeEl) {
            var sc  = parseInt(startingCharge || 0, 10);
            var cl  = Math.max(8, parseInt(chargeLimit || 8, 10));
            var txt = 'Limit: ' + cl;
            if (sc > 0) txt += ' • Starts with: +' + sc;
            chargeEl.textContent = txt;
        }
    }

    // Always fetch live pet data — never use the stale game snapshot
    fetch('/api/user/pet')
        .then(function(r){ return r.ok ? r.json() : null; })
        .then(function(d) {
            if (d && d.has_pet) {
                var mult           = calcEquipMultiplier(d);
                var ssAbilityMult  = calcSsAbilityMult(d);
                var statMastMult   = calcStatMasteryMult(d);
                // Charge abilities
                var abilities      = (d && d.abilities) || {};
                var chargedLvl     = parseInt(abilities['ene_charged_start']  || 0, 10);
                var overchargedLvl = parseInt(abilities['ene_overcharged']    || 0, 10);
                var chargeMastLvl  = parseInt(abilities['ene_charge_mastery'] || 0, 10);
                var startingCharge = (chargedLvl > 0 ? (1 + (chargedLvl - 1)) : 0)
                                   + (overchargedLvl > 0 ? (1 + (overchargedLvl - 1)) : 0);
                var chargeLimit    = 8 + (chargeMastLvl > 0 ? (1 + (chargeMastLvl - 1)) : 0);
                _fillCard(d.name, d.species, d.level, mult, ssAbilityMult, statMastMult, d.element, d.element2, startingCharge, chargeLimit);
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

// ── Initialize when script loads ────────────────────────────────────────────
console.log('[survive.js] Script loaded, initializing...');

// Load map script first, then initialize
function loadMapScript() {
    var mapSrc = '/js/ss_map.js';
    
    // Check if map functions are already available
    if (typeof _updateMapVisibility === 'function') {
        console.log('[survive.js] Map functions already loaded, calling init()');
        init();
        return;
    }
    
    console.log('[survive.js] Loading map script...');
    var s = document.createElement('script');
    s.src = mapSrc + '?v=' + Date.now();
    s.onload = function() { 
        console.log('[survive.js] Map script loaded, calling init()');
        init(); 
    };
    s.onerror = function() {
        console.error('[survive.js] Failed to load ss_map.js, continuing without map');
        init(); // still init so the lobby/start UI works
    };
    document.head.appendChild(s);
}

// Start initialization when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadMapScript);
} else {
    loadMapScript();
}


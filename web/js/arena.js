/* ── Arena JS ─────────────────────────────────────────────────────────────── */
(function () {
'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
let _ws          = null;
let _arenaRooms  = [];   // from unified WS
let _casinoRooms = [];   // from unified WS
let _myUserId    = null;
let _myArenaRoomId  = null;
let _myCasinoRoomId = null;
let _viewRoomId  = null;   // {id, type: 'arena'|'casino'}
let _diff        = 'easy';
let _wsRetries   = 0;
const MAX_RETRIES = 8;

// Turn-based battle state
let _battle      = null;

// Tracks whether a casino game is currently embedded in the panel — prevents
// WebSocket room broadcasts from wiping the active game UI.
let _gameEmbedActive = false;

// ── Global guard: any code (colosseum.js, etc.) can check this before
//    touching shared-panel-area.
window._arenaIsInBattle = function() {
    return !!(_battle || _bossBattle || _gameEmbedActive);
};

// ── DOM helpers ───────────────────────────────────────────────────────────────
const $   = id => document.getElementById(id);
const esc = s  => String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

// Element → glow colour mapping
const ELEM_COLORS = {
    fire:'#e74c3c', water:'#3498db', electric:'#f1c40f', ice:'#a8d8ea',
    plant:'#2ecc71', rock:'#95a5a6', air:'#bdc3c7', magic:'#9b59b6',
    holy:'#f9ca24', necro:'#6c5ce7', psychic:'#fd79a8', fighting:'#e17055',
    basic:'#ffd700'
};
function elemColor(e) { return ELEM_COLORS[(e||'basic').toLowerCase()] || '#ffd700'; }
function petImgUrl(species) {
    if (!species) return '/static/Emojis/Pets/Deco/Basic.png';
    return '/static/Emojis/Pets/' + species + '.png';
}
function petImgOrDefault(pet) {
    if (pet && pet.badge_url) return pet.badge_url;
    return petImgUrl((pet && pet.species) || null);
}

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
    // Check login
    try {
        const r = await fetch('/api/discord/user');
        if (!r.ok) { showLoginPrompt(); return; }
        const u = await r.json();
        _myUserId = String(u.id);
    } catch {
        showLoginPrompt();
        return;
    }

    $('arena-loading').style.display = 'none';
    $('arena-main').style.display    = '';

    connectWS();
}

function showLoginPrompt() {
    $('arena-loading').style.display      = 'none';
    $('arena-login-prompt').style.display = '';
}

// ── WebSocket ─────────────────────────────────────────────────────────────────
function connectWS() {
    // Prefer the shared live bus from dashboard.js — avoids a second WS connection.
    // If the bus isn't available (e.g. arena page loaded standalone), fall back to
    // opening our own connection.
    if (typeof window._liveWS !== 'undefined') {
        document.addEventListener('liveRooms', _onLiveRooms);
        // Try to ping for an immediate push; if the WS isn't open yet, fall back
        // to a REST fetch so rooms appear right away instead of waiting for the
        // next server-side broadcast event.
        const sent = window._liveWS.send('ping');
        if (!sent) {
            // WS not ready — fetch rooms directly and retry ping once it opens
            fetch('/api/arena/rooms').then(r => r.json()).then(d => {
                if (d.rooms) _onLiveRooms({ detail: { arena: d.rooms, casino: [] } });
            }).catch(() => {});
            fetch('/api/casino/lobby/rooms').then(r => r.json()).then(d => {
                if (d.rooms) _onLiveRooms({ detail: { arena: _arenaRooms, casino: d.rooms } });
            }).catch(() => {});
        }
        return;
    }

    // Fallback: own connection
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    _ws = new WebSocket(`${proto}://${location.host}/api/ws/unified`);

    _ws.onopen = () => {
        _wsRetries = 0;
        _ws._ping = setInterval(() => { if (_ws.readyState === 1) _ws.send('ping'); }, 25000);
    };

    _ws.onmessage = e => {
        try {
            const msg = JSON.parse(e.data);
            if (msg.type === 'unified') _onLiveRooms({ detail: { arena: msg.arena, casino: msg.casino } });
        } catch { /* ignore */ }
    };

    _ws.onclose = () => {
        clearInterval(_ws._ping);
        if (_wsRetries < MAX_RETRIES) {
            _wsRetries++;
            setTimeout(connectWS, Math.min(2000 * _wsRetries, 15000));
        }
    };

    _ws.onerror = () => _ws.close();
}

function _onLiveRooms(e) {
    _arenaRooms  = e.detail.arena  || [];
    _casinoRooms = e.detail.casino || [];
    renderUnifiedGrid();
    refreshPanelIfNeeded();
    updateOnlineCount();
}

// ── Unified room grid — 12 rooms (battle) + casino rooms (view-only) ─────────
function renderUnifiedGrid() {
    const grid = $('unified-grid');
    if (!grid) return;

    const GAME_ICONS = {
        slots:'🎰', blackjack:'🃏', craps:'🎲', holdem:'♠️', races:'🏁', minigames:'🎮'
    };

    // Merge both room sets by room_id — a room is "occupied" if it appears in
    // either the arena or casino list with a non-empty state.
    // Layout: rooms 0-3 (left bank), then Colosseum (center), then rooms 4-7 (right bank).
    // Rooms 8-11 are still accessible but shown below as a second row.
    const cards = Array.from({length: 12}, (_, i) => {
        const arenaRoom  = _arenaRooms.find(r => r.room_id === i);
        const casinoRoom = _casinoRooms.find(r => r.room_id === i);

        // Determine which side is active (prefer whichever is non-empty)
        const aEmpty = !arenaRoom  || arenaRoom.state  === 'empty';
        const cEmpty = !casinoRoom || casinoRoom.state === 'empty';

        const isArena  = !aEmpty;
        const isCasino = !isArena && !cEmpty;
        const isEmpty  = aEmpty && cEmpty;

        const room     = isArena ? arenaRoom : (isCasino ? casinoRoom : null);
        const type     = isArena ? 'arena' : 'casino';
        const isMe     = room ? (room.occupants.some(o => o.user_id === _myUserId) || (room.observers && room.observers.some(o => o.user_id === _myUserId))) : false;
        const myClass  = isMe ? ' my-room' : '';

        // State class for CSS border/glow
        let stateClass = 'empty';
        if (isArena)  stateClass = arenaRoom.state;
        if (isCasino) stateClass = casinoRoom.state;

        let inner = `<div class="u-room-num">#${i + 1}</div>`;

        if (isEmpty) {
            inner += `<div class="u-room-icon">🚪</div>
                      <div class="u-room-status empty">Open</div>`;
        } else if (isArena) {
            const avatars = arenaRoom.occupants.slice(0,4).map(o =>
                `<img class="u-avatar-mini" src="${esc(o.avatar)}" title="${esc(o.username)}"
                      onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'">`
            ).join('');
            inner += `<div style="display:flex;gap:2px;justify-content:center;flex-wrap:wrap">${avatars}</div>`;
            const sm = {
                npc_battle:   ['battle',    '⚔️ NPC'],
                pvp_waiting:  ['pvp-wait',  '🔥 PvP'],
                pvp_battle:   ['pvp-live',  '⚡ Live'],
                boss_waiting: ['boss-wait', '👹 Boss'],
                boss_battle:  ['boss-live', '👹 Live'],
            };
            const [cls, lbl] = sm[arenaRoom.state] || ['battle', arenaRoom.state];
            inner += `<div class="u-room-status ${cls}">${lbl}</div>`;
        } else {
            const avatars = casinoRoom.occupants.slice(0,2).map(o =>
                `<img class="u-avatar-mini" src="${esc(o.avatar)}" title="${esc(o.username)}"
                      onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'">`
            ).join('');
            inner += `<div style="display:flex;gap:2px;justify-content:center">${avatars}</div>`;
            const icon = casinoRoom.game ? (GAME_ICONS[casinoRoom.game] || '🎰') : '🎰';
            inner += `<div class="u-room-icon">${icon}</div>`;
            const obsCount = (casinoRoom.observers || []).length;
            const lbl = casinoRoom.state === 'picking' ? 'Choosing' : casinoRoom.state === 'open' ? 'Join!' : icon;
            const cls = casinoRoom.state === 'picking' ? 'picking' : casinoRoom.state === 'open' ? 'open' : 'playing';
            inner += `<div class="u-room-status ${cls}">${lbl}${obsCount > 0 ? ` <span style="font-size:0.6rem;opacity:0.7">👁${obsCount}</span>` : ''}</div>`;
        }

        const clickType = isEmpty ? 'arena' : type;
        return `<div class="u-room ${stateClass}${myClass}"
                     onclick="window._uClickRoom('${clickType}',${i})">${inner}</div>`;
    });

    // Single flat row — CSS grid handles the 12-column layout
    grid.innerHTML = cards.join('');
}

function updateOnlineCount() {
    const total = _arenaRooms.reduce((n,r) => n + r.occupants.length, 0)
                + _casinoRooms.reduce((n,r) => n + r.occupants.length, 0);
    const el = $('arena-online');
    if (el) el.textContent = `${total} online`;
    // Also update the sidebar nav badge
    const nav = document.getElementById('arena-nav-online');
    if (nav) nav.textContent = total > 0 ? `${total}` : '';
}

function refreshPanelIfNeeded() {
    if (!_viewRoomId) return;
    // Never interrupt an active battle or embedded casino game
    if (_battle || _bossBattle || _gameEmbedActive) return;

    const { id, type } = _viewRoomId;
    if (type === 'arena') {
        const room = _arenaRooms.find(r => r.room_id === id);
        if (!room) return;
        const isMine = room.occupants.some(o => o.user_id === _myUserId);

        // If the server says this room is in an active battle state and we're in it,
        // never overwrite the panel — the turn-based UI owns it until the battle ends.
        if (isMine && (room.state === 'npc_battle' || room.state === 'pvp_battle' || room.state === 'boss_battle')) return;

        if (room.state === 'empty') { /* keep join panel */ }
        else if (isMine) {
            if (!_battle && !_bossBattle) {
                if (room.state === 'boss_waiting') showBossWaitingRoom(room);
                else showArenaMyRoom(room);
            }
        }
        else if (room.state === 'pvp_waiting') showChallengePanel(room);
        else if (room.state === 'boss_waiting') showBossJoinPanel(room);
        else showArenaSpectate(room);
    } else {
        const room = _casinoRooms.find(r => r.room_id === id);
        if (!room) return;
        const isMine = room.occupants.some(o => o.user_id === _myUserId);
        const isObserving = room.observers && room.observers.some(o => o.user_id === _myUserId);
        if (room.state === 'empty') { /* keep join panel */ }
        else if (isMine) showCasinoMyRoom(room);
        else if (isObserving) showCasinoSpectate(room);
        else if (room.state === 'open') showCasinoJoinOpen(room);
        else showCasinoSpectate(room);
    }
}

// ── Unified room click ────────────────────────────────────────────────────────
window._uClickRoom = function(type, roomId) {
    _viewRoomId = { id: roomId, type: 'arena' };

    // Arena rooms always handle the click — casino rooms are view-only from here
    const arenaRoom = _arenaRooms.find(r => r.room_id === roomId);
    const casinoRoom = _casinoRooms.find(r => r.room_id === roomId);

    const aEmpty = !arenaRoom  || arenaRoom.state  === 'empty';
    const cEmpty = !casinoRoom || casinoRoom.state === 'empty';

    // If a casino game is running in this room, show spectate view (read-only)
    if (!cEmpty && aEmpty) {
        _viewRoomId = { id: roomId, type: 'casino' };
        const isMine = casinoRoom.occupants.some(o => o.user_id === _myUserId);
        const isObserving = casinoRoom.observers && casinoRoom.observers.some(o => o.user_id === _myUserId);
        if (isMine)              showCasinoMyRoom(casinoRoom);
        else if (isObserving)    showCasinoSpectate(casinoRoom);
        else if (casinoRoom.state === 'open') showCasinoJoinOpen(casinoRoom);
        else                     showCasinoObservePrompt(casinoRoom);
        return;
    }

    // Battle room (or empty → go to battle join panel)
    if (!arenaRoom || arenaRoom.state === 'empty') {
        showEmptyRoomPicker(roomId);
        return;
    }

    const isMine = arenaRoom.occupants.some(o => o.user_id === _myUserId);
    if (isMine) {
        if (arenaRoom.state === 'boss_waiting') showBossWaitingRoom(arenaRoom);
        else if (arenaRoom.state === 'boss_battle' && _bossBattle) { /* already in battle */ }
        else showArenaMyRoom(arenaRoom);
    } else if (arenaRoom.state === 'pvp_waiting') showChallengePanel(arenaRoom);
    else if (arenaRoom.state === 'boss_waiting')  showBossJoinPanel(arenaRoom);
    else                                          showArenaSpectate(arenaRoom);
};

// ── Empty room picker — goes straight to battle join panel ───────────────────
function showEmptyRoomPicker(roomId) {
    const alreadyIn = _myArenaRoomId !== null || _myCasinoRoomId !== null;

    if (!alreadyIn) {
        // Go straight to the battle join panel — casino has its own page
        showJoinPanel(roomId);
        return;
    }

    // Already in a room — show a warning instead
    setPanel(`
        <div class="arena-panel">
            <div class="arena-panel-title">🚪 Room #${roomId + 1}</div>
            <div style="font-size:0.75rem;color:#e74c3c;margin-bottom:12px">⚠️ You're already in a room — leave it first.</div>
            <div style="font-size:0.68rem;color:var(--text-secondary);text-align:center">
                Others can watch your room live from the grid above
            </div>
        </div>
    `);
}

// ── Arena join panel ──────────────────────────────────────────────────────────
function showJoinPanel(roomId) {
    const alreadyIn = _myArenaRoomId !== null;

    setPanel(`
        <div class="arena-panel">
            <div class="arena-panel-title">⚔️ Room #${roomId + 1} — Battle</div>
            ${alreadyIn ? `<div style="font-size:0.75rem;color:#e74c3c;margin-bottom:10px">⚠️ You're already in a room. Leave it first.</div>` : ''}
            <div style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:14px">
                Choose your battle mode and enter the room.
            </div>

            <div style="font-size:0.72rem;color:var(--text-secondary);margin-bottom:6px">Mode</div>
            <div class="d-flex gap-2 mb-3 flex-wrap">
                <button class="arena-btn" id="mode-npc"  onclick="window._arenaSetMode('npc',${roomId})">⚔️ NPC Battle</button>
                <button class="arena-btn" id="mode-pvp"  onclick="window._arenaSetMode('pvp',${roomId})">🔥 Seek PvP</button>
                <button class="arena-btn boss-mode-btn" id="mode-boss" onclick="window._arenaSetMode('boss',${roomId})">👹 Boss Battle</button>
            </div>

            <div id="join-npc-opts" style="display:none">
                <button class="arena-btn" id="join-enter-btn" onclick="window._arenaJoin(${roomId},'npc')" ${alreadyIn?'disabled':''}>
                    Enter Room
                </button>
            </div>

            <div id="join-pvp-opts" style="display:none">
                <div style="font-size:0.78rem;color:var(--gold-secondary);margin-bottom:10px">
                    Your room will glow and pulse so other users know you want to fight.
                </div>
                <button class="arena-btn" id="join-pvp-btn" onclick="window._arenaJoin(${roomId},'pvp')" ${alreadyIn?'disabled':''}>
                    Enter &amp; Seek PvP
                </button>
            </div>

            <div id="join-boss-opts" style="display:none">
                <div class="boss-info-box">
                    <div style="font-size:0.85rem;font-weight:700;color:#ff6b35;margin-bottom:6px">👹 Boss Battle</div>
                    <div style="font-size:0.75rem;color:var(--text-secondary);line-height:1.6">
                        Up to <strong style="color:var(--gold-primary)">4 players</strong> join the room and fight a single massive Boss Pet together.<br>
                        The Boss is generated from the <strong>average stats</strong> of all players — massive HP, reduced attack &amp; defense.<br>
                        Players always attack the Boss. When defending, choose a teammate to <strong>shield</strong>.<br>
                        All players must submit their action each turn before the round resolves.
                    </div>
                </div>
                <button class="arena-btn boss-mode-btn" id="join-boss-btn" onclick="window._arenaJoin(${roomId},'boss')" ${alreadyIn?'disabled':''}>
                    👹 Enter Boss Room
                </button>
            </div>
        </div>
    `);
}

window._arenaSetMode = function(mode, roomId) {
    $('join-npc-opts')  && ($('join-npc-opts').style.display  = mode === 'npc'  ? '' : 'none');
    $('join-pvp-opts')  && ($('join-pvp-opts').style.display  = mode === 'pvp'  ? '' : 'none');
    $('join-boss-opts') && ($('join-boss-opts').style.display = mode === 'boss' ? '' : 'none');
    ['mode-npc','mode-pvp','mode-boss'].forEach(id => {
        const el = $(id);
        if (el) el.style.borderColor = id.endsWith(mode) ? 'var(--gold-primary)' : '';
    });
};

window._arenaSetDiff = function(d) {
    _diff = d;
    document.querySelectorAll('.arena-diff-btn').forEach(b => {
        b.classList.toggle('active', b.textContent.toLowerCase() === d);
    });
};

window._arenaJoin = async function(roomId, mode) {
    const btn = $('join-enter-btn') || $('join-pvp-btn') || $('join-boss-btn');
    if (btn) btn.disabled = true;
    try {
        const r = await fetch('/api/arena/join', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({room_id: roomId, mode})
        });
        const d = await r.json();
        if (!r.ok) { alert(d.detail || 'Failed to join'); return; }
        _myArenaRoomId = roomId;
        _viewRoomId = { id: roomId, type: 'arena' };
        if (mode === 'npc') {
            showArenaMyRoom(_arenaRooms.find(rm => rm.room_id === roomId) || {room_id: roomId, state:'npc_battle', occupants:[], battle_log:[]});
        } else if (mode === 'boss') {
            const room = _arenaRooms.find(rm => rm.room_id === roomId) || {room_id: roomId, state:'boss_waiting', occupants:[], battle_log:[]};
            showBossWaitingRoom(room);
        }
    } catch(e) { alert(e.message); }
    finally { if (btn) btn.disabled = false; }
};

// ── Arena my room panel ───────────────────────────────────────────────────────
function showArenaMyRoom(room) {
    const isPvpWait = room.state === 'pvp_waiting';

    setPanel(`
        <div class="arena-panel">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <div class="arena-panel-title">⚔️ Room #${room.room_id + 1} — Your Battle Room</div>
                <button class="arena-btn danger" style="padding:4px 10px;font-size:0.7rem" onclick="window._arenaLeave()">Leave</button>
            </div>
            ${isPvpWait ? `
                <div style="font-size:0.82rem;color:var(--gold-primary);margin-bottom:10px;text-align:center">
                    🔥 Seeking PvP — your room is glowing for others to see.<br>
                    <span style="font-size:0.72rem;color:var(--text-secondary)">Waiting for a challenger...</span>
                </div>
            ` : `
                <div style="font-size:0.72rem;color:var(--text-secondary);margin-bottom:6px">Difficulty</div>
                <div class="d-flex gap-2 mb-3 flex-wrap">
                    ${['easy','average','hard'].map(d =>
                        `<button class="arena-diff-btn${d===_diff?' active':''}" onclick="window._arenaSetDiff('${d}')">${d.charAt(0).toUpperCase()+d.slice(1)}</button>`
                    ).join('')}
                </div>
                <button class="arena-btn" id="arena-fight-btn" onclick="window._arenaStartBattle(${room.room_id})">
                    ⚔️ Start NPC Battle
                </button>
            `}
        </div>
    `);
}

window._arenaFight = window._arenaStartBattle = async function(roomId) {
    const btn = $('arena-fight-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Starting...'; }
    try {
        const r = await fetch('/api/pets/battle/npc/start', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({difficulty: _diff})
        });
        const d = await r.json();
        if (!r.ok) { alert(d.detail || 'Failed to start'); if(btn){btn.disabled=false;btn.textContent='⚔️ Start NPC Battle';} return; }
        _battle = d;
        _battle.roomId = roomId;
        _showBattleStage();
    } catch(e) { alert(e.message); if(btn){btn.disabled=false;btn.textContent='⚔️ Start NPC Battle';} }
};

// ── Battle stage ──────────────────────────────────────────────────────────────
function _showBattleStage() {
    if (!_battle) return;
    _gameEmbedActive = true;
    // Tell colosseum.js (and any other co-loaded scripts) to stop overwriting the panel
    document.dispatchEvent(new CustomEvent('arenaBattleStarted'));
    const p = _battle.player, e = _battle.enemy;
    const labels = _battle.action_labels || {};
    const atkLabel = labels.attack || 'Attack';
    const defLabel = labels.defend || 'Defend';
    const chgLabel = labels.charge || 'Charge';

    setPanel(`
        <div class="arena-panel" id="arena-battle-panel">
            <div class="d-flex justify-content-between align-items-center mb-2">
                <div class="arena-panel-title" style="margin-bottom:0">⚔️ NPC Battle</div>
                <button class="arena-btn danger" style="padding:4px 10px;font-size:0.7rem" onclick="window._arenaLeave()">Flee</button>
            </div>
            <div class="arena-stage" id="arena-stage">
                <div class="arena-fighter" id="af-player">
                    <div class="arena-fighter-img-wrap" id="af-player-wrap">
                        <div class="arena-charge-ring" id="af-player-ring"></div>
                        <img class="arena-fighter-img" id="af-player-img"
                             src="${petImgOrDefault(p)}"
                             onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'" alt="${esc(p.name)}">
                    </div>
                    <div class="arena-fighter-name">${esc(p.name)}</div>
                    <div class="arena-fighter-sub">${esc(p.species||'')}</div>
                    <div class="arena-fighter-hp-wrap">
                        <div class="arena-fighter-hp-bar" id="af-player-hp" style="width:100%;background:#2ecc71"></div>
                    </div>
                    <div class="arena-fighter-hp-text" id="af-player-hp-text">${p.cur_hp} / ${p.max_hp}</div>
                    ${_buildEquipBar(p.equipment)}
                </div>
                <div class="arena-vs-badge">VS</div>
                <div class="arena-fighter enemy" id="af-enemy">
                    <div class="arena-fighter-img-wrap" id="af-enemy-wrap">
                        <div class="arena-charge-ring" id="af-enemy-ring"></div>
                        <img class="arena-fighter-img" id="af-enemy-img"
                             src="${petImgUrl(e.species)}"
                             onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'" alt="${esc(e.name)}">
                    </div>
                    <div class="arena-fighter-name">${esc(e.name)}</div>
                    <div class="arena-fighter-sub">${esc(e.species||'')} · ${esc(e.element||'')}</div>
                    <div class="arena-fighter-hp-wrap">
                        <div class="arena-fighter-hp-bar" id="af-enemy-hp" style="width:100%;background:#e74c3c"></div>
                    </div>
                    <div class="arena-fighter-hp-text" id="af-enemy-hp-text">${e.cur_hp} / ${e.max_hp}</div>
                    ${_buildEquipBar(e.equipment)}
                </div>
            </div>
            <div class="arena-action-row" id="arena-actions">
                <button class="arena-action-btn atk" id="ab-attack" onclick="window._arenaTurn('attack')">
                    ⚔️ Attack<span class="arena-action-sub">${esc(atkLabel)}</span>
                </button>
                <button class="arena-action-btn def" id="ab-defend" onclick="window._arenaTurn('defend')">
                    🛡️ Defend<span class="arena-action-sub">${esc(defLabel)}</span>
                </button>
                <button class="arena-action-btn chg" id="ab-charge" onclick="window._arenaTurn('charge')">
                    ⚡ Charge<span class="arena-action-sub">${esc(chgLabel)}</span>
                </button>
                ${_buildArenaSkillButtons(p)}
            </div>
            <div class="arena-status-text" id="arena-status">Your turn — pick an action!</div>
            <div class="arena-log" id="arena-turn-log"></div>
            <div id="arena-result" style="display:none"></div>
        </div>
    `);

    _setChargeRingColors('af-player-ring', p.element, p.element2);
    _setChargeRingColors('af-enemy-ring',  e.element, e.element2);
}

function _buildEquipBar(items) {
    if (!items || !items.length) return '';
    const RARITY_GLOW = {
        Common:   'rgba(158,158,158,0.55)',
        Uncommon: 'rgba(76,175,80,0.65)',
        Rare:     'rgba(33,150,243,0.65)',
        Epic:     'rgba(156,39,176,0.7)',
        Mythic:   'rgba(255,152,0,0.75)',
    };
    const imgs = items.map(item => {
        const f    = item.emoji_file || (item.name + '.png');
        const glow = RARITY_GLOW[item.rarity] || RARITY_GLOW.Common;
        const tip  = esc(item.name || '');
        return `<img class="af-equip-icon" src="/static/Emojis/Pets/Equipment/${esc(f)}"
                     title="${tip}"
                     style="filter:drop-shadow(0 0 3px ${glow})"
                     onerror="this.style.display='none'" alt="${tip}">`;
    }).join('');
    return `<div class="af-equip-bar">${imgs}</div>`;
}

function _setChargeRingColors(ringId, e1, e2) {
    const ring = $(ringId);
    if (!ring) return;
    ring.style.setProperty('--charge-c1', elemColor(e1));
    ring.style.setProperty('--charge-c2', elemColor(e2 || e1));
}

function _setChargeRingLevel(ringId, chargeValue) {
    const ring = $(ringId);
    if (!ring) return;
    // Remove all level classes
    ring.classList.remove('charge-1','charge-2','charge-3','charge-4','charge-5','charged');
    const lvl = Math.round(chargeValue);
    if (lvl >= 2) {
        ring.classList.add('charge-' + Math.min(5, lvl));
    }
    // If dropping back to 1 (charge consumed or reset), force reflow to kill animation
    if (lvl <= 1) {
        ring.style.animation = 'none';
        ring.offsetHeight; // trigger reflow
        ring.style.animation = '';
    }
}

function _setBattleButtons(enabled) {
    ['ab-attack','ab-defend','ab-charge'].forEach(id => {
        const b = $(id); if (b) b.disabled = !enabled;
    });
    // Skill buttons: when disabling (turn processing), disable all;
    // when re-enabling, only re-enable slots that are off cooldown
    if (_battle && _battle.player) {
        const skills = _battle.player.equipped_skills || [];
        const cds = _battle.player.skill_cooldowns || {};
        skills.forEach((sk, idx) => {
            const btn = $(`ab-skill-${idx}`);
            if (!btn) return;
            if (!sk) return; // empty slot stays disabled always
            if (!enabled) {
                btn.disabled = true;
            } else {
                const cd = cds[String(idx)] || 0;
                btn.disabled = cd > 0;
            }
        });
    }
}

function _updateHpBar(barId, textId, cur, max, isEnemy) {
    const pct = max > 0 ? Math.max(0, Math.min(100, Math.round((cur/max)*100))) : 0;
    const color = isEnemy
        ? (pct > 50 ? '#e74c3c' : pct > 25 ? '#f39c12' : '#95a5a6')
        : (pct > 50 ? '#2ecc71' : pct > 25 ? '#f39c12' : '#e74c3c');
    const bar = $(barId), text = $(textId);
    if (bar)  { bar.style.width = pct + '%'; bar.style.background = color; }
    if (text) text.textContent = cur + ' / ' + max;
}

function _showDmgFloat(wrapId, amount, color) {
    const wrap = $(wrapId);
    if (!wrap || !amount) return;
    const span = document.createElement('div');
    span.className = 'arena-dmg-float';
    span.style.color = color || '#e74c3c';
    span.textContent = amount > 0 ? '-' + amount : 'BLOCK';
    wrap.appendChild(span);
    setTimeout(() => span.remove(), 1300);
}

function _randomSkullUrl() {
    const n = Math.floor(Math.random() * 16) + 1;
    return `/static/Emojis/Skulls/${n}.png`;
}

function _eliminateFighter(imgId, cause, isEnemy) {
    const img = $(imgId);
    if (!img) return;
    // Pick the right exit animation
    let animName;
    if (cause === 'parry') {
        animName = isEnemy ? 'fighterKilledByParryEnemy' : 'fighterKilledByParry';
    } else {
        animName = isEnemy ? 'fighterKilledByAttackEnemy' : 'fighterKilledByAttack';
    }
    img.style.animation = `${animName} 700ms ease forwards`;
    // After exit, swap to skull
    setTimeout(() => {
        img.style.animation = '';
        img.style.opacity = '0';
        img.src = _randomSkullUrl();
        img.onerror = null;
        img.style.filter = 'drop-shadow(0 0 10px rgba(231,76,60,0.7)) grayscale(0.3)';
        // Remove flip for enemy so skull faces same way
        if (isEnemy) img.style.transform = 'scaleX(-1)';
        img.style.transition = 'opacity 0.4s';
        setTimeout(() => {
            img.style.opacity = '1';
            img.style.animation = 'skullReveal 0.5s ease forwards';
        }, 50);
        // Disable charge ring
        const ringId = isEnemy ? 'af-enemy-ring' : 'af-player-ring';
        const ring = $(ringId);
        if (ring) _setChargeRingLevel(ringId, 1);
    }, 680);
}

function _animateFighters(combat, isOver, won) {
    const pImg = $('af-player-img'), eImg = $('af-enemy-img');
    if (!pImg || !eImg) return;
    const DUR = 600;

    function anim(el, name, dur) {
        el.style.animation = 'none';
        el.offsetHeight;
        el.style.animation = `${name} ${dur}ms ease forwards`;
        setTimeout(() => { el.style.animation = ''; }, dur + 60);
    }

    const pa = combat.p_action, ea = combat.e_action;
    const both = pa === 'attack' && ea === 'attack';

    const playerDied = isOver && !won;
    const enemyDied  = isOver && won;
    const enemyKilledByParry  = enemyDied  && pa === 'defend' && (combat.e_parry || 0) > 0;
    const playerKilledByParry = playerDied && ea === 'defend' && (combat.p_parry || 0) > 0;

    // Normal animations for surviving fighters
    if (!playerDied) {
        if (pa === 'charge') {
            anim(pImg, 'fighterCharge', 900);
        } else if (pa === 'defend') {
            anim(pImg, 'fighterDefend', DUR);
            if (combat.e_parry > 0 && !enemyDied) setTimeout(() => anim(eImg, 'fighterParryBounceEnemy', DUR), 220);
        } else {
            anim(pImg, both ? 'fighterCollide' : 'fighterAttack', DUR);
            if (ea === 'charge' && !enemyDied) setTimeout(() => anim(eImg, 'fighterPushedBack', DUR), 200);
        }
    }

    if (!enemyDied) {
        if (ea === 'charge') {
            anim(eImg, 'fighterCharge', 900);
        } else if (ea === 'defend') {
            anim(eImg, 'fighterDefendEnemy', DUR);
            if (combat.p_parry > 0 && !playerDied) setTimeout(() => anim(pImg, 'fighterParryBounce', DUR), 220);
        } else {
            if (!both) anim(eImg, 'fighterAttackEnemy', DUR);
            if (pa === 'charge' && !playerDied) setTimeout(() => anim(pImg, 'fighterPushedBackPlayer', DUR), 200);
        }
    }

    // Hit flash on surviving fighters
    if (!playerDied && (combat.e_dmg > 0 || combat.p_parry > 0)) setTimeout(() => anim(pImg, 'fighterHit', 500), 300);
    if (!enemyDied  && (combat.p_dmg > 0 || combat.e_parry > 0)) setTimeout(() => anim(eImg, 'fighterHit', 500), 300);

    // Elimination animations
    if (enemyDied)  setTimeout(() => _eliminateFighter('af-enemy-img',  enemyKilledByParry  ? 'parry' : 'attack', true),  350);
    if (playerDied) setTimeout(() => _eliminateFighter('af-player-img', playerKilledByParry ? 'parry' : 'attack', false), 350);
}

function _appendTurnLog(turn, combat, pName, eName, extraLines) {
    const log = $('arena-turn-log');
    if (!log || !combat) return;
    const c = combat;
    let html = `<div style="border-left:2px solid rgba(255,215,0,0.18);padding:4px 7px;margin-bottom:4px;font-size:0.72rem">`;
    html += `<div style="font-size:0.65rem;color:var(--text-secondary);margin-bottom:2px">Turn ${turn}</div>`;

    // Player action
    if (c.p_action === 'charge') {
        html += `<div><span style="color:#9b59b6">⚡ ${esc(pName)}</span> charges → <span style="color:var(--gold-primary)">x${c.p_charge_after.toFixed(0)} ready</span></div>`;
    } else if (c.p_action === 'defend') {
        html += `<div><span style="color:#3498db">🛡️ ${esc(pName)}</span> defends`;
        if (c.e_parry > 0) html += ` → <span style="color:#2ecc71">parried <b>${c.e_parry}</b> back!</span>`;
        else if (c.e_dmg === 0 && c.e_action === 'attack') html += ` → <span style="color:#2ecc71">fully blocked!</span>`;
        else if (c.p_final_defense > 0 && c.e_dmg > 0) html += ` → <span style="color:#7fb3d3">blocked ${c.e_final_attack - c.e_dmg}</span>`;
        if (c.p_defense_roll) html += ` <span style="color:var(--text-secondary);opacity:0.6">[def roll: ${c.p_defense_roll}]</span>`;
        html += `</div>`;
    } else if (c.p_action === 'skill') {
        html += `<div><span style="color:#9b59b6">✨ ${esc(pName)}</span> uses <b>${esc(c.p_action_label)}</b></div>`;
    } else {
        const ct = c.p_charge_mult > 1 ? ` <span style="color:#9b59b6">x${c.p_charge_mult.toFixed(0)}</span>` : '';
        const crit = c.p_is_critical ? ` <span style="color:#ff6b35;font-weight:700">⚡CRITICAL!</span>` : '';
        html += `<div><span style="color:#e74c3c">⚔️ ${esc(pName)}</span> uses <b>${esc(c.p_action_label)}</b>${ct}${crit}`;
        if (c.p_dmg > 0) {
            const eff = c.p_type_elem_mult > 1.05 ? ' <span style="color:#f39c12">super effective</span>' : c.p_type_elem_mult < 0.95 ? ' <span style="color:#7f8c8d">not very effective</span>' : '';
            html += ` → <span style="color:#e74c3c"><b>${c.p_dmg}</b> dmg</span>${eff}`;
            if (c.p_critical_mult > 1) html += ` <span style="color:var(--text-secondary);opacity:0.6">x${c.p_critical_mult.toFixed(1)}</span>`;
        } else html += ` → <span style="color:#7f8c8d">blocked</span>`;
        if (c.p_attack_roll) html += ` <span style="color:var(--text-secondary);opacity:0.6">[atk roll: ${c.p_attack_roll}]</span>`;
        html += `</div>`;
    }

    // Enemy action
    if (c.e_action === 'charge') {
        html += `<div><span style="color:#9b59b6">⚡ ${esc(eName)}</span> charges → <span style="color:#e74c3c">x${c.e_charge_after.toFixed(0)} ready</span></div>`;
    } else if (c.e_action === 'defend') {
        html += `<div><span style="color:#3498db">🛡️ ${esc(eName)}</span> defends`;
        if (c.p_parry > 0) html += ` → <span style="color:#e74c3c">parried <b>${c.p_parry}</b> back!</span>`;
        else if (c.p_dmg === 0 && c.p_action === 'attack') html += ` → <span style="color:#2ecc71">fully blocked!</span>`;
        else if (c.e_final_defense > 0 && c.p_dmg > 0) html += ` → <span style="color:#7fb3d3">blocked ${c.p_final_attack - c.p_dmg}</span>`;
        if (c.e_defense_roll) html += ` <span style="color:var(--text-secondary);opacity:0.6">[def roll: ${c.e_defense_roll}]</span>`;
        html += `</div>`;
    } else if (c.e_action === 'skill') {
        html += `<div><span style="color:#9b59b6">✨ ${esc(eName)}</span> uses <b>${esc(c.e_action_label || 'Skill')}</b></div>`;
    } else {
        const ct = c.e_charge_mult > 1 ? ` <span style="color:#9b59b6">x${c.e_charge_mult.toFixed(0)}</span>` : '';
        const crit = c.e_is_critical ? ` <span style="color:#ff6b35;font-weight:700">⚡CRITICAL!</span>` : '';
        html += `<div><span style="color:#e67e22">💥 ${esc(eName)}</span> attacks${ct}${crit}`;
        if (c.e_dmg > 0) {
            const eff = c.e_type_elem_mult > 1.05 ? ' <span style="color:#f39c12">super effective</span>' : c.e_type_elem_mult < 0.95 ? ' <span style="color:#7f8c8d">not very effective</span>' : '';
            html += ` → <span style="color:#e67e22"><b>${c.e_dmg}</b> dmg</span>${eff}`;
            if (c.e_critical_mult > 1) html += ` <span style="color:var(--text-secondary);opacity:0.6">x${c.e_critical_mult.toFixed(1)}</span>`;
        } else html += ` → <span style="color:#7f8c8d">blocked</span>`;
        if (c.e_attack_roll) html += ` <span style="color:var(--text-secondary);opacity:0.6">[atk roll: ${c.e_attack_roll}]</span>`;
        html += `</div>`;
    }

    // Extra lines from skills/effects
    if (extraLines && extraLines.length) {
        extraLines.forEach(line => {
            html += `<div style="color:#9b59b6;font-size:0.68rem;padding-left:4px">${esc(line)}</div>`;
        });
    }

    html += `</div>`;
    const div = document.createElement('div');
    div.innerHTML = html;
    log.appendChild(div.firstChild);
    log.scrollTop = log.scrollHeight;
}

function _buildArenaSkillButtons(player) {
    const skills = (player && player.equipped_skills) || [];
    if (!skills.length) return '';
    const cds = (player && player.skill_cooldowns) || {};
    return skills.map((sk, idx) => {
        if (!sk) {
            // Unlocked slot but no skill equipped — show as empty/dimmed
            return `<button class="arena-action-btn arena-skill-empty"
                            id="ab-skill-${idx}"
                            style="background:rgba(100,100,100,0.1);border-color:rgba(100,100,100,0.3);color:rgba(150,150,150,0.5);font-size:0.72rem;cursor:not-allowed"
                            disabled
                            title="No skill equipped in slot ${idx + 1}">
                ✨ Slot ${idx + 1}<span class="arena-action-sub">Empty</span>
            </button>`;
        }
        const cd = cds[String(idx)] || 0;
        const onCd = cd > 0;
        return `<button class="arena-action-btn${onCd ? ' arena-skill-cd' : ''}"
                        id="ab-skill-${idx}"
                        style="background:rgba(155,89,182,0.15);border-color:rgba(155,89,182,0.5);color:#9b59b6;font-size:0.72rem"
                        onclick="window._arenaTurn('skill',${idx})"
                        ${onCd ? 'disabled' : ''}
                        title="${esc(sk.description || '')}">
            ✨ ${esc(sk.name)}<span class="arena-action-sub">${onCd ? `(${cd})` : 'Ready'}</span>
        </button>`;
    }).join('');
}

function _updateArenaSkillCooldowns(skillCooldowns) {
    if (!skillCooldowns || !_battle || !_battle.player) return;
    const skills = _battle.player.equipped_skills || [];
    skills.forEach((sk, idx) => {
        const btn = $(`ab-skill-${idx}`);
        if (!btn) return;
        if (!sk) return; // empty slot — stays disabled, nothing to update
        const cd = skillCooldowns[String(idx)] || 0;
        btn.disabled = cd > 0;
        btn.classList.toggle('arena-skill-cd', cd > 0);
        const sub = btn.querySelector('.arena-action-sub');
        if (sub) sub.textContent = cd > 0 ? `(${cd})` : 'Ready';
    });
    // Keep player state in sync
    _battle.player.skill_cooldowns = skillCooldowns;
}

window._arenaTurn = async function(action, slotIndex) {
    if (!_battle || _battle.over) return;
    _setBattleButtons(false);
    const status = $('arena-status');
    if (status) status.textContent = 'Processing turn...';

    try {
        const res = await fetch('/api/pets/battle/npc/turn', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({
                action,
                slot_index: slotIndex !== undefined ? slotIndex : 0,
                player: _battle.player,
                enemy:  _battle.enemy,
                turn:   _battle.turn,
                difficulty: _battle.difficulty,
                action_labels: _battle.action_labels || {},
                room_id: _battle.roomId
            })
        });
        const d = await res.json();
        if (!res.ok) { if(status) status.textContent = d.detail || 'Error'; _setBattleButtons(true); return; }

        if (d.combat) _animateFighters(d.combat, d.over, d.won);

        // ── GPP: push battle animation events to the game loop ────────────────
        if (window.PetGPP && d.animations) PetGPP.push(d.animations);
        if (window.PetGPP && d.level_change) PetGPP.pushLevelChange(d.level_change);

        // ── Charge ring: clear immediately when charge is consumed ────────────
        // Both attack AND defend consume charge (defend parries and deals damage).
        const c0 = d.combat || {};
        const pConsumedCharge = (c0.p_action === 'attack' || c0.p_action === 'defend') && (c0.p_charge_mult || 1) > 1;
        const eConsumedCharge = (c0.e_action === 'attack' || c0.e_action === 'defend') && (c0.e_charge_mult || 1) > 1;
        if (pConsumedCharge) _setChargeRingLevel('af-player-ring', 1);
        if (eConsumedCharge) _setChargeRingLevel('af-enemy-ring',  1);

        setTimeout(() => {
            const c = d.combat || {};
            if (c.e_dmg > 0 || c.e_parry > 0) _showDmgFloat('af-player-wrap', c.e_dmg + (c.e_parry||0), '#e74c3c');
            if (c.p_dmg > 0 || c.p_parry > 0) _showDmgFloat('af-enemy-wrap',  c.p_dmg + (c.p_parry||0), '#2ecc71');
        }, 280);

        _battle.player = d.player;
        _battle.enemy  = d.enemy;
        _battle.turn   = d.turn;
        _battle.over   = d.over;

        // Update skill cooldowns from server response
        if (d.skill_cooldowns) {
            _updateArenaSkillCooldowns(d.skill_cooldowns);
        }

        setTimeout(() => {
            _updateHpBar('af-player-hp', 'af-player-hp-text', d.player.cur_hp, d.player.max_hp, false);
            _updateHpBar('af-enemy-hp',  'af-enemy-hp-text',  d.enemy.cur_hp,  d.enemy.max_hp,  true);
            // Always sync charge rings to server state — this is the authoritative reset.
            // If charge was consumed this turn the server returns 1, clearing the ring.
            // If the battle is over, both rings go to 1 (dead fighters don't stay charged).
            const pCharge = d.over ? 1 : (d.player.charge || 1);
            const eCharge = d.over ? 1 : (d.enemy.charge  || 1);
            _setChargeRingLevel('af-player-ring', pCharge);
            _setChargeRingLevel('af-enemy-ring',  eCharge);
        }, 350);

        _appendTurnLog(d.turn, d.combat, _battle.player.name, _battle.enemy.name, d.lines);

        if (d.over) {
            // Delay result card until skull animation completes (~1.4s total)
            setTimeout(() => _showBattleResult(d), 1500);
        } else {
            if (status) status.textContent = `Turn ${d.turn} — pick your next action!`;
            setTimeout(() => _setBattleButtons(true), 650);
        }
    } catch(e) {
        if (status) status.textContent = 'Error: ' + e.message;
        _setBattleButtons(true);
    }
};

function _showBattleResult(d) {
    _gameEmbedActive = false;
    const won = d.won;
    const res = $('arena-result');
    const status = $('arena-status');
    if (status) status.textContent = '';
    if (!res) return;

    let html = `<div style="text-align:center;padding:12px 0;border-top:1px solid rgba(255,215,0,0.15);margin-top:8px">`;
    html += `<div style="font-size:1.1rem;font-weight:700;color:${won?'#2ecc71':'#e74c3c'};margin-bottom:6px">${won?'🏆 Victory!':'💀 Defeated'}</div>`;
    if (d.xp_gained) html += `<div style="font-size:0.82rem;color:var(--gold-primary);margin-bottom:4px">📈 +${d.xp_gained} XP</div>`;
    if (d.messages && d.messages.length) {
        d.messages.forEach(m => {
            let clean = String(m).replace(/<img[^>]*>/gi,'').replace(/<[^>]+>/g,'').replace(/\*\*/g,'').trim();
            if (!clean || /^\+?\d+\s*XP$/.test(clean)) return;
            clean = clean.replace(/\b(Key[123])\b/g, (match) =>
                `<img src="/static/Emojis/Pets/Equipment/${match}.png" style="width:13px;height:13px;object-fit:contain;vertical-align:middle;margin:0 2px" onerror="this.style.display='none'"> ${match}`
            );
            const isLoot = clean.includes('🎁');
            html += `<div style="font-size:0.72rem;color:${isLoot?'#2ecc71':'var(--text-secondary)'};margin-bottom:2px">${clean}</div>`;
        });
    }
    html += `<div class="d-flex gap-2 justify-content-center mt-3">
        <button class="arena-btn" onclick="window._arenaStartBattle(${_battle.roomId})">⚔️ Fight Again</button>
        <button class="arena-btn danger" onclick="window._arenaLeave()">Leave Room</button>
    </div></div>`;
    res.innerHTML = html;
    res.style.display = '';

    // ── GPP: push level change + result particles ─────────────────────────────
    if (window.PetGPP) {
        if (d.level_change) PetGPP.pushLevelChange(d.level_change);
        const playerImg = document.getElementById('af-player-img');
        PetGPP.Particles.spawnAt(won ? 'level_burst' : 'fail_flash', playerImg, won ? '#ffd700' : '#e74c3c');
    }

    if (d.level_change && typeof showLevelChangePopup === 'function') {
        showLevelChangePopup(d.level_change, d.level_change.new_level < d.level_change.old_level);
    }
}

// ── Challenge panel (PvP waiting room) ───────────────────────────────────────
function showChallengePanel(room) {
    const occ = room.occupants[0] || {};
    setPanel(`
        <div class="arena-panel">
            <div class="arena-panel-title">🔥 PvP Challenge</div>
            <div class="arena-combatant mb-3" style="max-width:160px;margin:0 auto">
                <img src="${esc(occ.avatar)}" onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'" alt="">
                <div class="name">${esc(occ.username)}</div>
                <div class="pet-name">🐾 ${esc(occ.pet_name)}</div>
            </div>
            <div style="font-size:0.78rem;color:var(--text-secondary);margin-bottom:14px;text-align:center">
                ${esc(occ.username)} is looking for a fight. Accept to battle their pet!
            </div>
            <button class="arena-btn" onclick="window._arenaChallenge(${room.room_id})">⚔️ Accept Challenge</button>
        </div>
    `);
}

window._arenaChallenge = async function(roomId) {
    const btn = document.querySelector(`#shared-panel-area .arena-btn`);
    if (btn) btn.disabled = true;
    try {
        const r = await fetch('/api/arena/battle/pvp', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({room_id: roomId})
        });
        const d = await r.json();
        if (!r.ok) { alert(d.detail || 'PvP failed'); return; }
        showPvpResult(d);
    } catch(e) { alert(e.message); }
};

function showPvpResult(d) {
    const iWon = d.winner_id === _myUserId;
    let logHtml = '';
    if (d.turns && d.turns.length) {
        d.turns.forEach(t => {
            logHtml += `<div style="border-left:2px solid rgba(255,215,0,0.18);padding:4px 7px;margin-bottom:4px;font-size:0.72rem">`;
            logHtml += `<div style="font-size:0.65rem;color:var(--text-secondary);margin-bottom:2px">Turn ${t.turn}</div>`;
            if (t.p_action === 'charge') {
                logHtml += `<div><span style="color:#9b59b6">⚡ ${esc(d.player_name)}</span> charges → <span style="color:var(--gold-primary)">x${t.p_charge.toFixed(0)} ready</span></div>`;
            } else if (t.p_action === 'defend') {
                logHtml += `<div><span style="color:#3498db">🛡️ ${esc(d.player_name)}</span> defends`;
                if (t.e_parry > 0) logHtml += ` → <span style="color:#2ecc71">parried <b>${t.e_parry}</b> back!</span>`;
                else if (t.e_dmg === 0 && t.e_action === 'attack') logHtml += ` → <span style="color:#2ecc71">fully blocked!</span>`;
                logHtml += `</div>`;
            } else if (t.p_action === 'skill') {
                logHtml += `<div><span style="color:#9b59b6">✨ ${esc(d.player_name)}</span> uses skill</div>`;
            } else {
                const ct = t.p_charge > 1 ? ` <span style="color:#9b59b6">x${t.p_charge.toFixed(0)}</span>` : '';
                const crit = t.p_crit ? ` <span style="color:#ff6b35;font-weight:700">⚡CRITICAL!</span>` : '';
                logHtml += `<div><span style="color:#e74c3c">⚔️ ${esc(d.player_name)}</span> attacks${ct}${crit}`;
                if (t.p_dmg > 0) {
                    const eff = t.p_type_elem > 1.05 ? ' <span style="color:#f39c12">super effective</span>' : t.p_type_elem < 0.95 ? ' <span style="color:#7f8c8d">not very effective</span>' : '';
                    logHtml += ` → <span style="color:#e74c3c"><b>${t.p_dmg}</b> dmg</span>${eff}`;
                } else logHtml += ` → <span style="color:#7f8c8d">blocked</span>`;
                if (t.p_parry > 0) logHtml += ` <span style="color:#e74c3c">parried ${t.p_parry}</span>`;
                logHtml += `</div>`;
            }
            if (t.e_action === 'charge') {
                logHtml += `<div><span style="color:#9b59b6">⚡ ${esc(d.enemy_name)}</span> charges → <span style="color:#e74c3c">x${t.e_charge.toFixed(0)} ready</span></div>`;
            } else if (t.e_action === 'defend') {
                logHtml += `<div><span style="color:#3498db">🛡️ ${esc(d.enemy_name)}</span> defends`;
                if (t.p_parry > 0) logHtml += ` → <span style="color:#e74c3c">parried <b>${t.p_parry}</b> back!</span>`;
                else if (t.p_dmg === 0 && t.p_action === 'attack') logHtml += ` → <span style="color:#2ecc71">fully blocked!</span>`;
                logHtml += `</div>`;
            } else if (t.e_action === 'skill') {
                logHtml += `<div><span style="color:#9b59b6">✨ ${esc(d.enemy_name)}</span> uses skill</div>`;
            } else {
                const ct = t.e_charge > 1 ? ` <span style="color:#9b59b6">x${t.e_charge.toFixed(0)}</span>` : '';
                const crit = t.e_crit ? ` <span style="color:#ff6b35;font-weight:700">⚡CRITICAL!</span>` : '';
                logHtml += `<div><span style="color:#e67e22">💥 ${esc(d.enemy_name)}</span> attacks${ct}${crit}`;
                if (t.e_dmg > 0) {
                    const eff = t.e_type_elem > 1.05 ? ' <span style="color:#f39c12">super effective</span>' : t.e_type_elem < 0.95 ? ' <span style="color:#7f8c8d">not very effective</span>' : '';
                    logHtml += ` → <span style="color:#e67e22"><b>${t.e_dmg}</b> dmg</span>${eff}`;
                } else logHtml += ` → <span style="color:#7f8c8d">blocked</span>`;
                if (t.e_parry > 0) logHtml += ` <span style="color:#e67e22">parried ${t.e_parry}</span>`;
                logHtml += `</div>`;
            }
            logHtml += `<div style="font-size:0.6rem;color:var(--text-secondary);margin-top:2px">&nbsp;⚔︎ HP: ${t.hp_a}/${d.start_hp_a || '?'} &nbsp;💥 HP: ${t.hp_b}/${d.start_hp_b || '?'}</div>`;
            logHtml += `</div>`;
        });
    } else {
        logHtml = (d.log || []).map(l => `<div>${esc(l)}</div>`).join('');
    }
    setPanel(`
        <div class="arena-panel">
            <div class="arena-panel-title" style="color:${iWon?'#2ecc71':'#e74c3c'}">${iWon?'🏆 You Won!':'💀 You Lost'}</div>
            <div style="font-size:0.82rem;color:var(--text-secondary);margin-bottom:10px">
                ${esc(d.winner_name)} defeated ${esc(d.loser_name)}
            </div>
            <div style="font-size:0.8rem;color:var(--gold-primary);margin-bottom:8px">
                📈 +${iWon ? d.winner_xp : d.loser_xp} XP
            </div>
            <details open>
                <summary style="cursor:pointer;font-size:0.75rem;color:var(--text-secondary);user-select:none">📜 Battle Log</summary>
                <div class="arena-log mt-2">${logHtml}</div>
            </details>
        </div>
    `);
}

// ── Arena spectate ────────────────────────────────────────────────────────────
function showArenaSpectate(room) {
    const occs = room.occupants;
    const stateLabel = {npc_battle:'⚔️ NPC Battle', pvp_battle:'⚡ PvP Battle', pvp_waiting:'🔥 Seeking PvP'}[room.state] || room.state;

    setPanel(`
        <div class="arena-panel">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <div class="arena-panel-title">👁️ Spectating Room #${room.room_id + 1}</div>
                <span class="arena-live-badge"><span class="arena-live-dot"></span>${stateLabel}</span>
            </div>
            <div class="d-flex gap-2 mb-3 flex-wrap">
                ${occs.map(o => `
                    <div class="arena-combatant" style="flex:1;min-width:100px">
                        <img src="${esc(o.avatar)}" onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'" alt="">
                        <div class="name">${esc(o.username)}</div>
                        <div class="pet-name">🐾 ${esc(o.pet_name)}</div>
                    </div>
                `).join('')}
            </div>
            <div style="font-size:0.7rem;color:var(--text-secondary);margin-bottom:4px;text-transform:uppercase;letter-spacing:0.5px">Live Log</div>
            <div class="arena-log" id="spectate-log">
                ${room.battle_log && room.battle_log.length
                    ? room.battle_log.map(l => `<div>${esc(l)}</div>`).join('')
                    : '<div style="opacity:0.4">Battle in progress...</div>'}
            </div>
        </div>
    `);
    const log = $('spectate-log');
    if (log) log.scrollTop = log.scrollHeight;
}

// ── Boss Battle State ─────────────────────────────────────────────────────────
let _bossBattle = null;   // full battle state from server
let _bossDefendTarget = null;  // user_id of the player this user is shielding

// ── Boss waiting room (player is in the room, waiting for others) ─────────────
function showBossWaitingRoom(room) {
    const occs = room.occupants || [];
    const canStart = occs.length >= 2;
    const isFull   = occs.length >= 4;

    setPanel(`
        <div class="arena-panel">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <div class="arena-panel-title">👹 Boss Battle — Room #${room.room_id + 1}</div>
                <button class="arena-btn danger" style="padding:4px 10px;font-size:0.7rem" onclick="window._arenaLeave()">Leave</button>
            </div>
            <div class="boss-waiting-info">
                <div style="font-size:0.78rem;color:var(--text-secondary);margin-bottom:10px">
                    Waiting for players… <strong style="color:var(--gold-primary)">${occs.length} / 4</strong> joined
                </div>
                <div class="boss-player-slots">
                    ${[0,1,2,3].map(i => {
                        const o = occs[i];
                        if (o) {
                            const npcTag = o.is_npc
                                ? `<div style="font-size:0.55rem;color:#9b59b6;margin-top:1px">🤖 AI</div>`
                                : '';
                            return `
                                <div class="boss-player-slot filled">
                                    <img src="${esc(o.avatar)}" onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'" alt="">
                                    <div class="bps-name">${esc(o.username)}</div>
                                    <div class="bps-pet">🐾 ${esc(o.pet_name)}</div>
                                    ${npcTag}
                                </div>`;
                        }
                        // Empty slot — clickable to invite or add NPC
                        if (!isFull) return `
                            <div class="boss-player-slot empty" style="cursor:pointer" title="Click to fill this slot"
                                 onclick="window._bossSlotClick(${room.room_id})">
                                <span style="font-size:1.4rem">+</span>
                                <div class="bps-name" style="opacity:0.5;font-size:0.6rem">Invite / AI</div>
                            </div>`;
                        return `<div class="boss-player-slot empty"><span style="opacity:0.3">🔒</span><div class="bps-name" style="opacity:0.3">Full</div></div>`;
                    }).join('')}
                </div>
            </div>
            <div style="font-size:0.7rem;color:var(--text-secondary);margin-bottom:12px;text-align:center">
                The Boss is generated from the average stats of all players once the battle starts.<br>
                <span style="opacity:0.7">Click an empty slot to invite a friend or add an AI pet.</span>
            </div>
            ${canStart ? `
                <button class="arena-btn boss-mode-btn" id="boss-start-btn" onclick="window._bossStart(${room.room_id})">
                    👹 Start Boss Battle (${occs.length} players)
                </button>
            ` : `
                <div style="font-size:0.75rem;color:var(--text-secondary);text-align:center;padding:8px;border:1px dashed rgba(255,107,53,0.3);border-radius:6px">
                    Need at least 2 players to start. Click an empty slot to invite someone or add an AI!
                </div>
            `}
        </div>
    `);
}

// ── Empty slot clicked — show invite/NPC modal ────────────────────────────────
window._bossSlotClick = async function(roomId) {
    // Build the modal overlay inline inside the panel
    const panel = document.getElementById('shared-panel-area');
    if (!panel) return;

    // Create modal
    const overlay = document.createElement('div');
    overlay.id = 'boss-slot-modal';
    overlay.style.cssText = `
        position:fixed;inset:0;background:rgba(0,0,0,0.75);z-index:9999;
        display:flex;align-items:center;justify-content:center;padding:16px;
    `;
    overlay.innerHTML = `
        <div style="background:var(--bg-card,#1a1a2e);border:1px solid rgba(255,107,53,0.4);border-radius:12px;
                    padding:20px;max-width:380px;width:100%;box-shadow:0 8px 32px rgba(0,0,0,0.5)">
            <div style="font-size:0.95rem;font-weight:700;color:#ff6b35;margin-bottom:14px">
                👹 Fill Slot — Room #${roomId + 1}
            </div>

            <!-- Tabs -->
            <div style="display:flex;gap:8px;margin-bottom:14px">
                <button id="bsm-tab-invite" class="arena-btn" style="flex:1;font-size:0.75rem"
                        onclick="window._bsmTab('invite',${roomId})">👤 Invite Player</button>
                <button id="bsm-tab-npc" class="arena-btn" style="flex:1;font-size:0.75rem;opacity:0.6"
                        onclick="window._bsmTab('npc',${roomId})">🤖 Add AI Pet</button>
            </div>

            <!-- Invite panel -->
            <div id="bsm-invite-panel">
                <div style="font-size:0.7rem;color:var(--text-secondary);margin-bottom:8px">
                    Search for a player to invite. They'll receive a Discord DM with a link to this room.
                    Enemies cannot be invited.
                </div>
                <input id="bsm-search" type="text" placeholder="Search by username or pet name…"
                       style="width:100%;background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.15);
                              border-radius:6px;padding:6px 10px;color:var(--text-primary,#fff);font-size:0.78rem;
                              box-sizing:border-box;margin-bottom:8px"
                       oninput="window._bsmSearch(this.value)">
                <div id="bsm-candidates" style="max-height:200px;overflow-y:auto">
                    <div style="font-size:0.72rem;color:var(--text-secondary);text-align:center;padding:8px">
                        ⏳ Loading candidates…
                    </div>
                </div>
                <div id="bsm-invite-status" style="font-size:0.72rem;margin-top:6px;min-height:18px"></div>
            </div>

            <!-- NPC panel (hidden by default) -->
            <div id="bsm-npc-panel" style="display:none">
                <div style="font-size:0.7rem;color:var(--text-secondary);margin-bottom:10px">
                    Add an AI-controlled pet to fill this slot. Its stats will be scaled to match the
                    current players so it contributes meaningfully to the fight.
                </div>
                <button class="arena-btn boss-mode-btn" id="bsm-add-npc-btn"
                        onclick="window._bsmAddNpc(${roomId})"
                        style="width:100%;margin-bottom:6px">
                    🤖 Add AI Pet
                </button>
                <div id="bsm-npc-status" style="font-size:0.72rem;text-align:center;min-height:18px"></div>
            </div>

            <button class="arena-btn danger" style="width:100%;margin-top:12px;font-size:0.75rem"
                    onclick="document.getElementById('boss-slot-modal').remove()">Cancel</button>
        </div>
    `;
    document.body.appendChild(overlay);

    // Load candidates immediately
    window._bsmAllCandidates = [];
    try {
        const r = await fetch(`/api/arena/battle/boss/invite-candidates?room_id=${roomId}`);
        if (r.ok) {
            const d = await r.json();
            window._bsmAllCandidates = d.candidates || [];
        }
    } catch(e) { /* ignore */ }
    window._bsmRoomId = roomId;
    window._bsmSearch('');
};

// ── Tab switch ────────────────────────────────────────────────────────────────
window._bsmTab = function(tab, roomId) {
    const inv = document.getElementById('bsm-invite-panel');
    const npc = document.getElementById('bsm-npc-panel');
    const tInv = document.getElementById('bsm-tab-invite');
    const tNpc = document.getElementById('bsm-tab-npc');
    if (!inv || !npc) return;
    const showInvite = tab === 'invite';
    inv.style.display = showInvite ? '' : 'none';
    npc.style.display = showInvite ? 'none' : '';
    if (tInv) tInv.style.opacity = showInvite ? '1' : '0.6';
    if (tNpc) tNpc.style.opacity = showInvite ? '0.6' : '1';
};

// ── Live search filter ────────────────────────────────────────────────────────
window._bsmSearch = function(query) {
    const el = document.getElementById('bsm-candidates');
    if (!el) return;
    const q = (query || '').toLowerCase();
    const list = (window._bsmAllCandidates || []).filter(c =>
        !q || c.username.toLowerCase().includes(q) || c.pet_name.toLowerCase().includes(q)
    );
    if (!list.length) {
        el.innerHTML = `<div style="font-size:0.72rem;color:var(--text-secondary);text-align:center;padding:8px">${query ? 'No matches.' : 'No eligible players found.'}</div>`;
        return;
    }
    el.innerHTML = list.slice(0, 20).map(c => `
        <div style="display:flex;align-items:center;gap:8px;padding:5px 4px;border-bottom:1px solid rgba(255,255,255,0.05);cursor:pointer"
             onclick="window._bsmInvite('${esc(c.user_id)}','${esc(c.username)}')"
             onmouseenter="this.style.background='rgba(255,107,53,0.08)'"
             onmouseleave="this.style.background=''">
            <img src="${esc(c.avatar) || '/static/Emojis/Pets/Deco/Basic.png'}"
                 onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'"
                 style="width:28px;height:28px;border-radius:50%;object-fit:cover;flex-shrink:0">
            <div style="flex:1;min-width:0">
                <div style="font-size:0.75rem;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
                    ${esc(c.username)}
                </div>
                <div style="font-size:0.62rem;color:var(--text-secondary)">🐾 ${esc(c.pet_name)} · Lv${c.pet_level}</div>
            </div>
            <button class="arena-btn" style="font-size:0.65rem;padding:3px 8px;flex-shrink:0">Invite</button>
        </div>
    `).join('');
};

// ── Send invite ───────────────────────────────────────────────────────────────
window._bsmInvite = async function(targetId, targetName) {
    const statusEl = document.getElementById('bsm-invite-status');
    const roomId   = window._bsmRoomId;
    if (statusEl) statusEl.textContent = `⏳ Sending invite to ${targetName}…`;
    try {
        const r = await fetch('/api/arena/battle/boss/invite', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ target_user_id: targetId, room_id: roomId }),
        });
        const d = await r.json();
        if (!r.ok) {
            if (statusEl) statusEl.innerHTML = `<span style="color:#e74c3c">❌ ${esc(d.detail || 'Failed')}</span>`;
        } else {
            if (statusEl) statusEl.innerHTML = `<span style="color:#2ecc71">✅ ${esc(d.message || 'Invite sent!')}</span>`;
            // Remove from candidate list so they can't be invited twice
            window._bsmAllCandidates = (window._bsmAllCandidates || []).filter(c => c.user_id !== targetId);
            const searchEl = document.getElementById('bsm-search');
            window._bsmSearch(searchEl ? searchEl.value : '');
        }
    } catch(e) {
        if (statusEl) statusEl.innerHTML = `<span style="color:#e74c3c">❌ ${e.message}</span>`;
    }
};

// ── Add NPC pet ───────────────────────────────────────────────────────────────
window._bsmAddNpc = async function(roomId) {
    const btn     = document.getElementById('bsm-add-npc-btn');
    const statusEl= document.getElementById('bsm-npc-status');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Generating AI pet…'; }
    try {
        const r = await fetch('/api/arena/battle/boss/add_npc', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ room_id: roomId }),
        });
        const d = await r.json();
        if (!r.ok) {
            if (statusEl) statusEl.innerHTML = `<span style="color:#e74c3c">❌ ${esc(d.detail || 'Failed')}</span>`;
            if (btn) { btn.disabled = false; btn.textContent = '🤖 Add AI Pet'; }
        } else {
            if (statusEl) statusEl.innerHTML = `<span style="color:#2ecc71">✅ ${esc(d.npc_name)} added! (ATK ${d.npc_stats.attack} / DEF ${d.npc_stats.defense} / HP ${d.npc_stats.hp})</span>`;
            // Close modal after a short delay — room update via WS will refresh the waiting room
            setTimeout(() => {
                const m = document.getElementById('boss-slot-modal');
                if (m) m.remove();
            }, 1400);
        }
    } catch(e) {
        if (statusEl) statusEl.innerHTML = `<span style="color:#e74c3c">❌ ${e.message}</span>`;
        if (btn) { btn.disabled = false; btn.textContent = '🤖 Add AI Pet'; }
    }
};

// ── Boss join panel (non-member sees a boss_waiting room) ─────────────────────
function showBossJoinPanel(room) {
    const occs = room.occupants || [];
    const alreadyIn = _myArenaRoomId !== null;
    const full = occs.length >= 4;

    setPanel(`
        <div class="arena-panel">
            <div class="arena-panel-title">👹 Boss Battle — Room #${room.room_id + 1}</div>
            <div class="boss-player-slots" style="margin-bottom:14px">
                ${[0,1,2,3].map(i => {
                    const o = occs[i];
                    if (o) return `
                        <div class="boss-player-slot filled">
                            <img src="${esc(o.avatar)}" onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'" alt="">
                            <div class="bps-name">${esc(o.username)}</div>
                            <div class="bps-pet">🐾 ${esc(o.pet_name)}</div>
                        </div>`;
                    return `<div class="boss-player-slot empty"><span>+</span><div class="bps-name" style="opacity:0.3">Open</div></div>`;
                }).join('')}
            </div>
            ${full ? `<div style="font-size:0.75rem;color:#e74c3c;text-align:center">Room is full (4/4)</div>` : `
                ${alreadyIn ? `<div style="font-size:0.75rem;color:#e74c3c;margin-bottom:8px">⚠️ Leave your current room first.</div>` : ''}
                <button class="arena-btn boss-mode-btn" onclick="window._arenaJoin(${room.room_id},'boss')" ${alreadyIn||full?'disabled':''}>
                    👹 Join Boss Battle
                </button>
            `}
        </div>
    `);
}

// ── Start boss battle ─────────────────────────────────────────────────────────
window._bossStart = async function(roomId) {
    const btn = $('boss-start-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Generating Boss...'; }
    try {
        const r = await fetch('/api/arena/battle/boss/start', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({room_id: roomId})
        });
        const d = await r.json();
        if (!r.ok) { alert(d.detail || 'Failed to start boss battle'); if(btn){btn.disabled=false;btn.textContent='👹 Start Boss Battle';} return; }
        _bossBattle = d.battle;
        _bossBattle.roomId = roomId;
        _bossDefendTarget = _myUserId;  // default: defend yourself
        _showBossStage();
    } catch(e) { alert(e.message); if(btn){btn.disabled=false;btn.textContent='👹 Start Boss Battle';} }
};

// ── Boss battle stage ─────────────────────────────────────────────────────────
function _buildBossSkillButtons(player) {
    const skills = (player && player.equipped_skills) || [];
    if (!skills.length) return '';
    const cds = (player && player.skill_cooldowns) || {};
    return skills.map((sk, idx) => {
        if (!sk) return '';
        const cd = cds[String(idx)] || 0;
        const onCd = cd > 0;
        return `<button class="arena-action-btn${onCd ? ' arena-skill-cd' : ''}"
                        id="bab-skill-${idx}"
                        style="background:rgba(155,89,182,0.15);border-color:rgba(155,89,182,0.5);color:#9b59b6;font-size:0.72rem"
                        onclick="window._bossAction('skill',${idx})"
                        ${onCd ? 'disabled' : ''}
                        title="${esc(sk.description || '')}">
            ✨ ${esc(sk.name)}<span class="arena-action-sub">${onCd ? `(${cd})` : 'Ready'}</span>
        </button>`;
    }).join('');
}

function _showBossStage() {
    if (!_bossBattle) return;
    _gameEmbedActive = true;
    // Tell colosseum.js (and any other co-loaded scripts) to stop overwriting the panel
    document.dispatchEvent(new CustomEvent('arenaBattleStarted'));
    const boss = _bossBattle.boss;
    const players = _bossBattle.players;
    const me = players.find(p => p.user_id === _myUserId);
    if (!me) return;

    const labels = me.action_labels || {};
    const atkLabel = labels.attack || 'Attack';
    const defLabel = labels.defend || 'Defend';
    const chgLabel = labels.charge || 'Charge';

    setPanel(`
        <div class="arena-panel" id="boss-battle-panel">
            <div class="d-flex justify-content-between align-items-center mb-2">
                <div class="arena-panel-title" style="margin-bottom:0;color:#ff6b35">👹 Boss Battle</div>
                <button class="arena-btn danger" style="padding:4px 10px;font-size:0.7rem" onclick="window._arenaLeave()">Flee</button>
            </div>

            <!-- Boss HP bar -->
            <div class="boss-hp-section">
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <div style="font-size:0.82rem;font-weight:700;color:#ff6b35">
                        <img src="${petImgUrl(boss.species)}" style="width:22px;height:22px;object-fit:contain;vertical-align:middle;margin-right:4px" onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'">
                        ${esc(boss.name)}
                    </div>
                    <div style="font-size:0.72rem;color:var(--text-secondary)" id="boss-hp-text">${boss.cur_hp} / ${boss.max_hp}</div>
                </div>
                <div style="background:rgba(0,0,0,0.4);border-radius:20px;height:14px;overflow:hidden;border:1px solid rgba(255,107,53,0.3)">
                    <div id="boss-hp-bar" style="height:100%;background:linear-gradient(90deg,#ff6b35,#e74c3c);border-radius:20px;transition:width 0.6s ease;width:100%"></div>
                </div>
                <div style="font-size:0.65rem;color:var(--text-secondary);margin-top:2px">
                    ${esc(boss.element)} · ${esc(boss.type)} · ATK ${boss.attack} · DEF ${boss.defense}
                    <span id="boss-charge-badge" style="display:none;color:#9b59b6;margin-left:6px">⚡ Charging x<span id="boss-charge-val">1</span></span>
                </div>
            </div>

            <!-- Player HP bars -->
            <div class="boss-players-row" id="boss-players-row">
                ${players.map(p => _buildBossPlayerCard(p, p.user_id === _myUserId)).join('')}
            </div>

            <!-- Defend target selector -->
            <div class="boss-defend-section" id="boss-defend-section">
                <div style="font-size:0.68rem;color:var(--text-secondary);margin-bottom:4px">🛡️ Shield target (when defending):</div>
                <div class="d-flex gap-2 flex-wrap" id="boss-defend-targets">
                    ${players.map(p => `
                        <button class="boss-defend-btn${p.user_id === _myUserId ? ' active' : ''}"
                                id="bdt-${p.user_id}"
                                onclick="window._bossSetDefendTarget('${p.user_id}')">
                            ${esc(p.name.split(' ')[0])}
                        </button>
                    `).join('')}
                </div>
            </div>

            <!-- Action buttons -->
            <div class="arena-action-row" id="boss-actions">
                <button class="arena-action-btn atk" id="bab-attack" onclick="window._bossAction('attack')">
                    ⚔️ Attack<span class="arena-action-sub">${esc(atkLabel)}</span>
                </button>
                <button class="arena-action-btn def" id="bab-defend" onclick="window._bossAction('defend')">
                    🛡️ Defend<span class="arena-action-sub">${esc(defLabel)}</span>
                </button>
                <button class="arena-action-btn chg" id="bab-charge" onclick="window._bossAction('charge')">
                    ⚡ Charge<span class="arena-action-sub">${esc(chgLabel)}</span>
                </button>
                ${_buildBossSkillButtons(me)}
            </div>

            <div class="arena-status-text" id="boss-status">Your turn — pick an action! All players must act before the round resolves.</div>
            <div class="arena-log" id="boss-turn-log"></div>
            <div id="boss-result" style="display:none"></div>
        </div>
    `);

    _updateBossHpBar(boss.cur_hp, boss.max_hp);
    _updateBossPlayerCards(players);
}

function _buildBossPlayerCard(p, isMe) {
    const pct = p.max_hp > 0 ? Math.max(0, Math.min(100, Math.round((p.cur_hp / p.max_hp) * 100))) : 0;
    const hpColor = pct > 50 ? '#2ecc71' : pct > 25 ? '#f39c12' : '#e74c3c';
    const elimStyle = p.alive ? '' : 'opacity:0.35;filter:grayscale(0.8)';
    const meBorder = isMe ? 'border-color:var(--gold-primary);box-shadow:0 0 8px var(--gold-glow)' : '';
    return `
        <div class="boss-player-card" id="bpc-${p.user_id}" style="${elimStyle};${meBorder}">
            <div class="arena-fighter-img-wrap" style="width:52px;height:52px">
                <div class="arena-charge-ring" id="bpc-ring-${p.user_id}"
                     style="--charge-c1:${elemColor(p.element)};--charge-c2:${elemColor(p.element2||p.element)}"></div>
                <img style="width:44px;height:44px;object-fit:contain"
                     src="${petImgOrDefault(p)}"
                     onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'" alt="">
            </div>
            <div style="font-size:0.65rem;font-weight:600;color:${isMe?'var(--gold-primary)':'var(--text-primary)'};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:70px">${esc(p.name)}</div>
            <div style="width:100%;background:rgba(0,0,0,0.4);border-radius:10px;height:6px;overflow:hidden;margin-top:2px">
                <div id="bpc-hp-${p.user_id}" style="height:100%;background:${hpColor};border-radius:10px;transition:width 0.5s ease;width:${pct}%"></div>
            </div>
            <div style="font-size:0.58rem;color:var(--text-secondary)" id="bpc-hp-text-${p.user_id}">${p.cur_hp}/${p.max_hp}</div>
            ${!p.alive ? '<div style="font-size:0.65rem;color:#e74c3c">💀 Eliminated</div>' : ''}
            <div id="bpc-pending-${p.user_id}" style="font-size:0.6rem;color:#9b59b6;min-height:14px"></div>
        </div>`;
}

function _updateBossHpBar(cur, max) {
    const pct = max > 0 ? Math.max(0, Math.min(100, Math.round((cur / max) * 100))) : 0;
    const color = pct > 50 ? 'linear-gradient(90deg,#ff6b35,#e74c3c)' : pct > 25 ? 'linear-gradient(90deg,#f39c12,#e74c3c)' : '#e74c3c';
    const bar = $('boss-hp-bar'), text = $('boss-hp-text');
    if (bar)  { bar.style.width = pct + '%'; bar.style.background = color; }
    if (text) text.textContent = cur + ' / ' + max;
}

function _updateBossPlayerCards(players) {
    players.forEach(p => {
        const pct = p.max_hp > 0 ? Math.max(0, Math.min(100, Math.round((p.cur_hp / p.max_hp) * 100))) : 0;
        const hpColor = pct > 50 ? '#2ecc71' : pct > 25 ? '#f39c12' : '#e74c3c';
        const bar  = $(`bpc-hp-${p.user_id}`);
        const text = $(`bpc-hp-text-${p.user_id}`);
        const card = $(`bpc-${p.user_id}`);
        if (bar)  { bar.style.width = pct + '%'; bar.style.background = hpColor; }
        if (text) text.textContent = p.cur_hp + '/' + p.max_hp;
        if (card && !p.alive) { card.style.opacity = '0.35'; card.style.filter = 'grayscale(0.8)'; }
        _setChargeRingLevel(`bpc-ring-${p.user_id}`, p.charge || 1);
    });
}

function _setBossButtons(enabled) {
    ['bab-attack','bab-defend','bab-charge'].forEach(id => {
        const b = $(id); if (b) b.disabled = !enabled;
    });
    // Skill buttons: only enable if not on cooldown
    if (_bossBattle) {
        const me = _bossBattle.players.find(p => p.user_id === _myUserId);
        const skills = (me && me.equipped_skills) || [];
        const cds = (me && me.skill_cooldowns) || {};
        skills.forEach((sk, idx) => {
            const b = $(`bab-skill-${idx}`);
            if (!b) return;
            if (!sk) { b.disabled = true; return; }
            const cd = cds[String(idx)] || 0;
            b.disabled = cd > 0 || !enabled;
        });
    }
}

window._bossSetDefendTarget = function(uid) {
    _bossDefendTarget = uid;
    document.querySelectorAll('.boss-defend-btn').forEach(b => {
        b.classList.toggle('active', b.id === 'bdt-' + uid);
    });
};

window._bossAction = async function(action, slotIndex) {
    if (!_bossBattle || _bossBattle.over) return;
    const me = _bossBattle.players.find(p => p.user_id === _myUserId);
    if (!me || !me.alive) return;

    _setBossButtons(false);
    const status = $('boss-status');
    if (status) status.textContent = '⏳ Action submitted — waiting for other players...';

    // Mark pending locally
    const pendingEl = $(`bpc-pending-${_myUserId}`);
    const actionIcons = {attack:'⚔️', defend:'🛡️', charge:'⚡', skill:'✨'};
    if (pendingEl) pendingEl.textContent = (actionIcons[action] || '⚔️') + ' Submitted';

    try {
        const r = await fetch('/api/arena/battle/boss/action', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({
                room_id:       _bossBattle.roomId,
                action,
                slot_index:    slotIndex !== undefined ? slotIndex : 0,
                defend_target: action === 'defend' ? (_bossDefendTarget || _myUserId) : _myUserId,
            })
        });
        const d = await r.json();
        if (!r.ok) { if(status) status.textContent = d.detail || 'Error'; _setBossButtons(true); return; }

        if (d.resolved) {
            // Turn resolved — update full state
            _bossBattle = d.battle;
            _bossBattle.roomId = _bossBattle.room_id || _bossBattle.roomId;

            // Update boss HP
            _updateBossHpBar(_bossBattle.boss.cur_hp, _bossBattle.boss.max_hp);

            // Update player cards
            _updateBossPlayerCards(_bossBattle.players);

            // Boss charge badge
            const chargeBadge = $('boss-charge-badge'), chargeVal = $('boss-charge-val');
            if (chargeBadge && chargeVal) {
                const bc = _bossBattle.boss.charge || 1;
                chargeBadge.style.display = bc > 1 ? '' : 'none';
                chargeVal.textContent = bc.toFixed(0);
            }

            // Clear pending indicators
            _bossBattle.players.forEach(p => {
                const el = $(`bpc-pending-${p.user_id}`);
                if (el) el.textContent = '';
            });

            // Append turn log with styling
            (d.turn_log || []).forEach(line => _appendBossLogLine(line));
            // Update skill cooldowns
            if (_bossBattle.players) {
                const me = _bossBattle.players.find(p => p.user_id === _myUserId);
                if (me) {
                    const skills = (me.equipped_skills) || [];
                    const cds = (me.skill_cooldowns) || {};
                    skills.forEach((sk, idx) => {
                        const b = $(`bab-skill-${idx}`);
                        if (!b) return;
                        const cd = cds[String(idx)] || 0;
                        b.disabled = cd > 0;
                        b.classList.toggle('arena-skill-cd', cd > 0);
                        const sub = b.querySelector('.arena-action-sub');
                        if (sub) sub.textContent = cd > 0 ? `(${cd})` : 'Ready';
                    });
                }
            }

            if (_bossBattle.over) {
                setTimeout(() => _showBossResult(), 1200);
            } else {
                if (status) status.textContent = `Turn ${_bossBattle.turn} complete — pick your next action!`;
                setTimeout(() => _setBossButtons(true), 500);
            }
        } else {
            // Waiting for others
            const waiting = d.waiting_for || 0;
            if (status) status.textContent = `⏳ Waiting for ${waiting} more player${waiting !== 1 ? 's' : ''}...`;
            // Poll for resolution
            _pollBossResolution();
        }
    } catch(e) {
        if (status) status.textContent = 'Error: ' + e.message;
        _setBossButtons(true);
    }
};

function _appendBossLogLine(line) {
    const log = $('boss-turn-log');
    if (!log) return;
    const div = document.createElement('div');
    if (line.startsWith('━━━')) {
        div.style.cssText = 'font-size:0.68rem;color:var(--text-secondary);margin-bottom:2px;margin-top:4px;text-align:center';
        div.textContent = line.replace(/━/g, '—');
    } else if (line.includes('CRITICAL')) {
        div.style.cssText = 'font-size:0.72rem;border-left:2px solid rgba(255,107,53,0.3);padding:2px 6px;margin-bottom:2px;color:#ff6b35;font-weight:700';
        div.innerHTML = line.replace(/⚡CRITICAL!/g, '<span style="color:#ff6b35;font-weight:700">⚡CRITICAL!</span>');
    } else if (line.startsWith('⚔️') || line.startsWith('💥')) {
        div.style.cssText = 'font-size:0.72rem;border-left:2px solid rgba(255,107,53,0.3);padding:2px 6px;margin-bottom:2px';
        div.innerHTML = line.replace(/(→ \d+ dmg)/g, '<b style="color:#e74c3c">$1</b>')
                           .replace(/(⚡CRITICAL!)/g, '<span style="color:#ff6b35;font-weight:700">$1</span>');
    } else if (line.startsWith('🛡️')) {
        div.style.cssText = 'font-size:0.72rem;border-left:2px solid rgba(255,107,53,0.3);padding:2px 6px;margin-bottom:2px;color:#3498db';
        div.textContent = line;
    } else if (line.startsWith('⚡')) {
        div.style.cssText = 'font-size:0.72rem;border-left:2px solid rgba(255,107,53,0.3);padding:2px 6px;margin-bottom:2px;color:#9b59b6';
        div.textContent = line;
    } else if (line.startsWith('✨')) {
        div.style.cssText = 'font-size:0.72rem;border-left:2px solid rgba(255,107,53,0.3);padding:2px 6px;margin-bottom:2px;color:#9b59b6';
        div.textContent = line;
    } else if (line.startsWith('💀') || line.startsWith('🏆')) {
        div.style.cssText = 'font-size:0.72rem;padding:2px 6px;margin-bottom:2px;font-weight:700';
        div.style.color = line.startsWith('🏆') ? '#f1c40f' : '#e74c3c';
        div.textContent = line;
    } else {
        div.style.cssText = 'font-size:0.72rem;border-left:2px solid rgba(255,107,53,0.3);padding:2px 6px;margin-bottom:2px';
        div.textContent = line;
    }
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
}

// Poll for boss turn resolution (when waiting for other players)
let _bossPollTimer = null;
function _pollBossResolution() {
    if (_bossPollTimer) clearTimeout(_bossPollTimer);
    _bossPollTimer = setTimeout(async () => {
        if (!_bossBattle || _bossBattle.over) return;
        try {
            const r = await fetch(`/api/arena/battle/boss/state?room_id=${_bossBattle.roomId}`);
            if (!r.ok) return;
            const d = await r.json();
            const newBattle = d.battle;
            if (!newBattle) return;

            // Check if turn advanced
            if (newBattle.turn > _bossBattle.turn) {
                _bossBattle = newBattle;
                _bossBattle.roomId = newBattle.room_id || _bossBattle.roomId;

                _updateBossHpBar(_bossBattle.boss.cur_hp, _bossBattle.boss.max_hp);
                _updateBossPlayerCards(_bossBattle.players);

                const chargeBadge = $('boss-charge-badge'), chargeVal = $('boss-charge-val');
                if (chargeBadge && chargeVal) {
                    const bc = _bossBattle.boss.charge || 1;
                    chargeBadge.style.display = bc > 1 ? '' : 'none';
                    chargeVal.textContent = bc.toFixed(0);
                }

                // Show new log lines
                const newLines = _bossBattle.log.slice(-10);
                newLines.forEach(line => _appendBossLogLine(line));

                // Update skill cooldowns
                const me = _bossBattle.players.find(p => p.user_id === _myUserId);
                if (me) {
                    const skills = (me.equipped_skills) || [];
                    const cds = (me.skill_cooldowns) || {};
                    skills.forEach((sk, idx) => {
                        const b = $(`bab-skill-${idx}`);
                        if (!b) return;
                        const cd = cds[String(idx)] || 0;
                        b.disabled = cd > 0;
                        b.classList.toggle('arena-skill-cd', cd > 0);
                        const sub = b.querySelector('.arena-action-sub');
                        if (sub) sub.textContent = cd > 0 ? `(${cd})` : 'Ready';
                    });
                }

                _bossBattle.players.forEach(p => {
                    const el = $(`bpc-pending-${p.user_id}`);
                    if (el) el.textContent = '';
                });

                if (_bossBattle.over) {
                    setTimeout(() => _showBossResult(), 1200);
                } else {
                    const status = $('boss-status');
                    if (status) status.textContent = `Turn ${_bossBattle.turn} complete — pick your next action!`;
                    _setBossButtons(true);
                }
            } else {
                // Still waiting — check pending actions
                const alive = newBattle.players.filter(p => p.alive);
                const submitted = Object.keys(newBattle.pending_actions || {}).length;
                const waiting = alive.length - submitted;
                const status = $('boss-status');
                if (status && waiting > 0) status.textContent = `⏳ Waiting for ${waiting} more player${waiting !== 1 ? 's' : ''}...`;
                // Update pending indicators from server state
                alive.forEach(p => {
                    const el = $(`bpc-pending-${p.user_id}`);
                    if (el) {
                        const hasSubmitted = (newBattle.pending_actions || {})[p.user_id];
                        el.textContent = hasSubmitted ? '✅ Ready' : '';
                    }
                });
                _pollBossResolution();
            }
        } catch(e) {
            _pollBossResolution();
        }
    }, 1500);
}

function _showBossResult() {
    _gameEmbedActive = false;
    if (!_bossBattle) return;
    const won = _bossBattle.won;
    const res = $('boss-result');
    const status = $('boss-status');
    if (status) status.textContent = '';
    if (!res) return;

    const me = _bossBattle.players.find(p => p.user_id === _myUserId);
    const myXp = me ? (me.xp_gained || 0) : 0;
    const survivors = _bossBattle.players.filter(p => p.alive).map(p => esc(p.name)).join(', ');

    let html = `<div style="text-align:center;padding:12px 0;border-top:1px solid rgba(255,107,53,0.2);margin-top:8px">`;
    html += `<div style="font-size:1.1rem;font-weight:700;color:${won?'#2ecc71':'#e74c3c'};margin-bottom:6px">${won?'🏆 Boss Defeated!':'💀 Party Wiped'}</div>`;
    if (won && survivors) html += `<div style="font-size:0.78rem;color:var(--text-secondary);margin-bottom:6px">Survivors: ${survivors}</div>`;
    if (myXp > 0) html += `<div style="font-size:0.82rem;color:var(--gold-primary);margin-bottom:4px">📈 +${myXp} XP</div>`;
    html += `<div class="d-flex gap-2 justify-content-center mt-3">
        <button class="arena-btn" onclick="window._arenaLeave()">Leave Room</button>
    </div></div>`;
    res.innerHTML = html;
    res.style.display = '';
    _bossBattle = null;
}

// ── Leave ─────────────────────────────────────────────────────────────────────
window._arenaLeave = async function() {
    if (_bossPollTimer) { clearTimeout(_bossPollTimer); _bossPollTimer = null; }
    try {
        await fetch('/api/arena/leave', {method:'POST'});
    } catch { /* ignore */ }
    _myArenaRoomId   = null;
    _viewRoomId      = null;
    _battle          = null;
    _bossBattle      = null;
    _bossDefendTarget = null;
    _gameEmbedActive = false;
    setPanel(`
        <div class="arena-panel" style="text-align:center;padding:32px 18px">
            <div style="font-size:2rem;opacity:0.3">⚔️🎰</div>
            <div style="color:var(--text-secondary);font-size:0.82rem;margin-top:8px">Pick a room to battle or gamble.</div>
        </div>
    `);
};

// ── Helpers ───────────────────────────────────────────────────────────────────
function setPanel(html) {
    const area = $('shared-panel-area');
    if (area) area.innerHTML = html;
}

// ── Casino panel functions ────────────────────────────────────────────────────
const GAME_INFO_MAP = {
    slots:     { label: 'Slot Machine',  icon: '🎰' },
    blackjack: { label: 'Blackjack',     icon: '🃏' },
    craps:     { label: 'Craps',         icon: '🎲' },
    holdem:    { label: "Texas Hold'em", icon: '♠️' },
    races:     { label: 'Pet Races',     icon: '🏁' },
    minigames: { label: 'Mini-Games',    icon: '🎮' },
};

const GAME_CSS = {
    slots:'css/casino.css', blackjack:'/css/blackjack.css', craps:'/css/craps.css',
    holdem:'/css/holdem.css', races:'/css/races.css', minigames:'/css/minigames.css',
};
const GAME_PAGE = {
    slots:'casino', blackjack:'blackjack', craps:'craps',
    holdem:'holdem', races:'races', minigames:'minigames',
};

let _activeGameScript = null;

function showCasinoMyRoom(room) {
    const gi = room.game ? GAME_INFO_MAP[room.game] : null;
    const observerCount = (room.observers || []).length;
    const pendingCount  = (room.pending_seats || []).length;
    const isCraps = room.game === 'craps';
    const hasObservers = observerCount > 0;

    setPanel(`
        <div class="cl-panel">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <div class="cl-panel-title">🎰 Room #${room.room_id + 1} — Your Casino Room</div>
                <button class="cl-btn danger" style="padding:4px 10px;font-size:0.7rem" onclick="window._casinoLeave()">Leave</button>
            </div>
            ${gi ? `
                <div style="font-size:0.82rem;color:var(--gold-secondary);margin-bottom:14px;text-align:center">
                    ${gi.icon} Currently playing: <strong>${gi.label}</strong>
                </div>
                <div class="d-flex gap-2 justify-content-center mb-3 flex-wrap">
                    <button class="cl-btn" onclick="window._clOpenGameInline('${room.game}')">
                        ${gi.icon} Open ${gi.label}
                    </button>
                    <button class="cl-btn" style="font-size:0.72rem;padding:6px 12px" onclick="window._casinoChangePick()">
                        Change Game
                    </button>
                    ${isCraps && hasObservers ? `
                        <button class="cl-btn" style="font-size:0.72rem;padding:6px 12px;border-color:rgba(241,196,15,0.5);color:#f1c40f" onclick="window._crapsSwapRoller(${room.room_id})">
                            🎲 Swap Roller
                        </button>
                    ` : ''}
                </div>
            ` : `
                <div style="font-size:0.78rem;color:var(--text-secondary);margin-bottom:12px">Pick a game to play:</div>
                <div class="cl-game-grid">
                    ${Object.entries(GAME_INFO_MAP).map(([key, g]) => `
                        <button class="cl-game-btn" onclick="window._clPickGame('${key}', ${room.room_id})">
                            <span class="game-icon">${g.icon}</span>
                            <span class="game-label">${g.label}</span>
                        </button>
                    `).join('')}
                </div>
            `}
            ${observerCount > 0 ? `
                <div style="font-size:0.68rem;color:var(--text-secondary);margin-bottom:4px;margin-top:8px">
                    👁️ ${observerCount} watching${pendingCount > 0 ? ` · 🪑 ${pendingCount} waiting for seat` : ''}
                </div>
                <div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px">
                    ${(room.observers||[]).map(o => `<img class="u-avatar-mini" src="${esc(o.avatar)}" title="${esc(o.username)}" onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'">`).join('')}
                </div>
            ` : ''}
            ${room.activity && room.activity.length ? `
                <div style="font-size:0.68rem;color:var(--text-secondary);margin-bottom:4px;margin-top:4px">Activity</div>
                <div class="cl-activity-log">
                    ${room.activity.map(l => `<div class="cl-activity-line">${esc(l)}</div>`).join('')}
                </div>
            ` : ''}
        </div>
    `);
}

window._casinoChangePick = function() {
    const room = _casinoRooms.find(r => r.room_id === _myCasinoRoomId);
    if (room) { room.game = null; showCasinoMyRoom(room); }
};

function showCasinoJoinOpen(room) {
    const gi   = GAME_INFO_MAP[room.game] || { label: room.game, icon: '🎮' };
    const host = room.occupants[0];
    setPanel(`
        <div class="cl-panel">
            <div class="cl-panel-title">🎰 Room #${room.room_id + 1} — Open Seat</div>
            <div class="cl-spectate-info">
                <img class="cl-spectate-avatar" src="${esc(host?.avatar||'')}" onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'">
                <div>
                    <div class="cl-spectate-name">${esc(host?.username||'?')}</div>
                    <div class="cl-spectate-game">${gi.icon} ${gi.label} — looking for a player</div>
                </div>
            </div>
            <div class="d-flex gap-2">
                <button class="cl-btn join" onclick="window._casinoJoinOpen(${room.room_id},'${room.game}')">Join Game</button>
                <button class="cl-btn" onclick="window._casinoSpectate(${room.room_id})">👁 Watch</button>
            </div>
        </div>
    `);
}

function showCasinoSpectate(room) {
    const gi = room.game ? GAME_INFO_MAP[room.game] : null;
    const canJoin    = room.game && ['blackjack','holdem','races','minigames'].includes(room.game);
    const canBetOn   = room.game && ['craps','races','minigames'].includes(room.game);
    const isCraps    = room.game === 'craps';
    const isRaces    = room.game === 'races';
    const isMini     = room.game === 'minigames';

    // Build observer bet UI
    let betUI = '';
    if (canBetOn && room.game === 'craps') {
        betUI = `
            <div style="margin-top:12px;padding:10px;background:rgba(255,215,0,0.05);border-radius:8px;border:1px solid rgba(255,215,0,0.15)">
                <div style="font-size:0.72rem;color:var(--gold-secondary);margin-bottom:8px">🎲 Bet on the Roll</div>
                <div class="d-flex gap-2 mb-2">
                    <button class="cl-btn" style="flex:1;font-size:0.72rem" onclick="window._observerCrapsBet(${room.room_id},'pass')">Pass Line</button>
                    <button class="cl-btn" style="flex:1;font-size:0.72rem" onclick="window._observerCrapsBet(${room.room_id},'dont_pass')">Don't Pass</button>
                </div>
                <div class="d-flex gap-2 align-items-center">
                    <input id="obs-craps-bet-amt" type="number" min="10" value="50" class="cl-input" style="width:90px;padding:4px 8px;font-size:0.78rem">
                    <span style="font-size:0.68rem;color:var(--text-secondary)">XP</span>
                </div>
            </div>`;
    } else if (canBetOn && room.game === 'races') {
        const racerBtns = (room.occupants || []).map(p =>
            `<button class="cl-btn" style="font-size:0.7rem;padding:4px 8px" onclick="window._observerRaceBet(${room.room_id},'${p.user_id}','${esc(p.username)}')">${esc(p.username)}</button>`
        ).join('');
        betUI = `
            <div style="margin-top:12px;padding:10px;background:rgba(255,215,0,0.05);border-radius:8px;border:1px solid rgba(255,215,0,0.15)">
                <div style="font-size:0.72rem;color:var(--gold-secondary);margin-bottom:8px">🏁 Bet on a Racer</div>
                <div class="d-flex gap-2 flex-wrap mb-2">${racerBtns}</div>
                <div class="d-flex gap-2 align-items-center">
                    <input id="obs-race-bet-amt" type="number" min="10" value="50" class="cl-input" style="width:90px;padding:4px 8px;font-size:0.78rem">
                    <span style="font-size:0.68rem;color:var(--text-secondary)">XP</span>
                </div>
            </div>`;
    } else if (canBetOn && room.game === 'minigames') {
        betUI = `
            <div style="margin-top:12px;padding:10px;background:rgba(255,215,0,0.05);border-radius:8px;border:1px solid rgba(255,215,0,0.15)">
                <div style="font-size:0.72rem;color:var(--gold-secondary);margin-bottom:8px">🪙 Bet on Coin Flip</div>
                <div class="d-flex gap-2 mb-2">
                    <button class="cl-btn" style="flex:1;font-size:0.72rem" onclick="window._observerCoinBet(${room.room_id},'heads')">Heads</button>
                    <button class="cl-btn" style="flex:1;font-size:0.72rem" onclick="window._observerCoinBet(${room.room_id},'tails')">Tails</button>
                </div>
                <div class="d-flex gap-2 align-items-center">
                    <input id="obs-coin-bet-amt" type="number" min="10" value="50" class="cl-input" style="width:90px;padding:4px 8px;font-size:0.78rem">
                    <span style="font-size:0.68rem;color:var(--text-secondary)">XP</span>
                </div>
            </div>`;
    }

    // Join / seat request button
    let joinBtn = '';
    if (canJoin) {
        if (room.game === 'races') {
            joinBtn = `<button class="cl-btn join" style="margin-top:10px;width:100%" onclick="window._observerJoinRace(${room.room_id})">🏁 Join Next Race</button>`;
        } else if (room.game === 'minigames') {
            joinBtn = `<button class="cl-btn join" style="margin-top:10px;width:100%" onclick="window._observerJoinRPS(${room.room_id})">🎮 Challenge to RPS</button>`;
        } else {
            joinBtn = `<button class="cl-btn join" style="margin-top:10px;width:100%" onclick="window._observerRequestSeat(${room.room_id})">🪑 Request Seat (Next Round)</button>`;
        }
    }

    setPanel(`
        <div class="cl-panel">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <div class="cl-panel-title">👁️ Casino Room #${room.room_id + 1} — Spectating</div>
                <span class="arena-live-badge"><span class="arena-live-dot"></span>${gi ? gi.icon + ' ' + gi.label : '🎰 Casino'}</span>
            </div>
            <div style="display:flex;flex-direction:column;gap:8px;margin-bottom:14px">
                ${room.occupants.map(p => `
                    <div class="cl-spectate-info">
                        <img class="cl-spectate-avatar" src="${esc(p.avatar)}" onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'">
                        <div>
                            <div class="cl-spectate-name">${esc(p.username)}</div>
                            <div class="cl-spectate-game">${gi ? gi.icon + ' ' + gi.label : '🎰 Casino'}${p.pet_name ? ' · 🐾 ' + esc(p.pet_name) : ''}</div>
                        </div>
                    </div>
                `).join('')}
            </div>
            ${room.observers && room.observers.length ? `
                <div style="font-size:0.68rem;color:var(--text-secondary);margin-bottom:4px">Watching (${room.observers.length})</div>
                <div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:10px">
                    ${room.observers.map(o => `<img class="u-avatar-mini" src="${esc(o.avatar)}" title="${esc(o.username)}" onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'">`).join('')}
                </div>
            ` : ''}
            ${betUI}
            ${joinBtn}
            ${room.activity && room.activity.length ? `
                <div style="font-size:0.68rem;color:var(--text-secondary);margin-bottom:4px;margin-top:12px">Live Activity</div>
                <div class="cl-activity-log">
                    ${room.activity.map(l => `<div class="cl-activity-line">${esc(l)}</div>`).join('')}
                </div>
            ` : `<div style="font-size:0.78rem;color:var(--text-secondary);text-align:center;padding:20px 0">Waiting for activity...</div>`}
            <button class="cl-btn danger" style="margin-top:12px;width:100%;font-size:0.72rem" onclick="window._casinoLeave()">Leave Room</button>
        </div>
    `);
}

window._casinoSpectate = function(roomId) {
    _viewRoomId = { id: roomId, type: 'casino' };
    const room = _casinoRooms.find(r => r.room_id === roomId);
    if (room) showCasinoSpectate(room);
};

window._casinoJoinOpen = async function(roomId, game) {
    try {
        const r = await fetch('/api/casino/lobby/join', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ room_id: roomId })
        });
        const d = await r.json();
        if (!r.ok) { alert(d.detail || 'Failed'); return; }
        _myCasinoRoomId = roomId;
        await fetch('/api/casino/lobby/set_game', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ game })
        });
        await window._clOpenGameInline(game);
    } catch(e) { alert(e.message); }
};

window._clPickGame = async function(game) {
    try {
        const r = await fetch('/api/casino/lobby/set_game', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ game })
        });
        if (!r.ok) { const d = await r.json(); alert(d.detail || 'Failed'); return; }
        await window._clOpenGameInline(game);
    } catch(e) { alert(e.message); }
};

window._clOpenGameInline = async function(game) {
    const panel = $('shared-panel-area');
    if (!panel) return;
    _gameEmbedActive = true;

    const gi = GAME_INFO_MAP[game] || { icon: '🎮', label: game };
    panel.innerHTML = `<div class="cl-panel" style="text-align:center;padding:40px 18px">
        <div class="spinner-border" style="color:var(--gold-primary)" role="status"></div>
        <p style="color:var(--text-secondary);font-size:0.82rem;margin-top:10px">Loading ${gi.label}...</p>
    </div>`;

    const cssHref = GAME_CSS[game];
    if (cssHref && !document.querySelector(`link[href="${cssHref}"]`)) {
        const link = document.createElement('link');
        link.rel = 'stylesheet'; link.href = cssHref;
        document.head.appendChild(link);
    }

    let html;
    try {
        const res = await fetch(`/Pages/${GAME_PAGE[game] || game}.html?v=${Date.now()}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        html = await res.text();
    } catch(e) {
        panel.innerHTML = `<div class="cl-panel" style="text-align:center;padding:30px">
            <div style="color:#e74c3c">Failed to load: ${e.message}</div>
            <button class="cl-btn" style="margin-top:12px" onclick="window._clCloseGame()">← Back</button>
        </div>`;
        return;
    }

    const scriptMatch = html.match(/<script\s+src="([^"]+)"/i);
    const scriptSrc   = scriptMatch ? scriptMatch[1] : null;
    const cleanHtml   = html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '')
                            .replace(/<link\b[^>]*rel="stylesheet"[^>]*>/gi, '');

    panel.innerHTML = `
        <div class="cl-panel cl-game-embed">
            <div class="cl-game-embed-header">
                <span class="cl-panel-title" style="margin-bottom:0">${gi.icon} ${gi.label}</span>
                <button class="cl-btn danger" style="padding:4px 12px;font-size:0.72rem" onclick="window._clCloseGame()">✕ Close</button>
            </div>
            <div class="cl-game-embed-body" id="cl-game-body">${cleanHtml}</div>
        </div>`;

    if (_activeGameScript) { _activeGameScript.remove(); _activeGameScript = null; }
    if (scriptSrc) {
        const s = document.createElement('script');
        s.src = scriptSrc + '?t=' + Date.now();
        document.head.appendChild(s);
        _activeGameScript = s;
    }

    // For games with pending XP, show a prominent cashout button in the header
    const CASHOUT_GAMES = { races: '/api/casino/races/cashout', holdem: '/api/casino/holdem/cashout' };
    if (CASHOUT_GAMES[game]) {
        const cashoutUrl = CASHOUT_GAMES[game];
        const header = document.querySelector('.cl-game-embed-header');
        if (header) {
            const btn = document.createElement('button');
            btn.className = 'cl-btn';
            btn.style.cssText = 'padding:4px 12px;font-size:0.72rem;border-color:rgba(46,204,113,0.6);color:#2ecc71;background:rgba(46,204,113,0.08)';
            btn.textContent = '💰 Cash Out';
            btn.onclick = async function() {
                btn.disabled = true;
                btn.textContent = '⏳...';
                try {
                    const r = await fetch(cashoutUrl, { method:'POST', headers:{'Content-Type':'application/json'}, body:'{}' });
                    const d = await r.json();
                    const xp = d.cashed_out || d.cashed_xp || 0;
                    const keys = d.cashed_keys || [];
                    btn.textContent = `✅ +${xp.toLocaleString()} XP${keys.length ? ' 🗝️' : ''}`;
                    setTimeout(() => window._clCloseGame(), 1200);
                } catch(e) {
                    btn.textContent = '💰 Cash Out';
                    btn.disabled = false;
                }
            };
            // Insert before the close button
            const closeBtn = header.querySelector('.cl-btn.danger');
            if (closeBtn) header.insertBefore(btn, closeBtn);
            else header.appendChild(btn);
        }
    }

    if (game === 'slots') {
        setTimeout(() => {
            const els = { grid: 'casino-game-grid', panel: 'casino-slots-panel', loading: 'casino-loading', login: 'casino-login-prompt', nopet: 'casino-no-pet', main: 'casino-main' };
            if (document.getElementById(els.grid))    document.getElementById(els.grid).style.display    = 'none';
            if (document.getElementById(els.loading)) document.getElementById(els.loading).style.display = 'none';
            if (document.getElementById(els.login))   document.getElementById(els.login).style.display   = 'none';
            if (document.getElementById(els.nopet))   document.getElementById(els.nopet).style.display   = 'none';
            if (document.getElementById(els.panel))   document.getElementById(els.panel).style.display   = '';
            if (document.getElementById(els.main))    document.getElementById(els.main).style.display    = '';
        }, 150);
    }
};

window._clCloseGame = function() {
    if (_activeGameScript) { _activeGameScript.remove(); _activeGameScript = null; }
    _gameEmbedActive = false;
    // Auto-cashout any games with pending server-side state before closing
    _autoCashoutPending().then(() => {
        const room = _casinoRooms.find(r => r.room_id === _myCasinoRoomId);
        if (room) showCasinoMyRoom(room);
        else setPanel(`<div class="arena-panel" style="text-align:center;padding:40px 18px">
            <div style="font-size:2.5rem;opacity:0.25">⚔️🎰</div>
            <div style="color:var(--text-secondary);font-size:0.85rem;margin-top:10px">Pick a room to battle or gamble.</div>
        </div>`);
    });
};

window._casinoLeave = async function() {
    if (_activeGameScript) { _activeGameScript.remove(); _activeGameScript = null; }
    _gameEmbedActive = false;
    await _autoCashoutPending();
    try {
        await fetch('/api/casino/lobby/leave', { method:'POST', headers:{'Content-Type':'application/json'}, body:'{}' });
    } catch { /* silent */ }
    _myCasinoRoomId = null;
    _viewRoomId     = null;
    setPanel(`<div class="arena-panel" style="text-align:center;padding:40px 18px">
        <div style="font-size:2.5rem;opacity:0.25">⚔️🎰</div>
        <div style="color:var(--text-secondary);font-size:0.85rem;margin-top:10px">Pick a room to battle or gamble.</div>
    </div>`);
};

// Auto-cashout any games that have pending server-side XP before closing the panel
async function _autoCashoutPending() {
    const checks = [
        // Races — cashout pending winnings
        { state: '/api/casino/races/state',   cashout: '/api/casino/races/cashout',   hasXp: d => d.active && d.player_won && (d.pending_xp || 0) > 0 },
        // Hold'em — cashout remaining stack
        { state: '/api/casino/holdem/state',  cashout: '/api/casino/holdem/cashout',  hasXp: d => d.active && (d.seats?.[0]?.stack || 0) > 0 },
        // Craps — refund any active bets
        { state: '/api/casino/craps/state',   cashout: '/api/casino/craps/quit',      hasXp: d => d.active && (d.total_bet || 0) > 0 },
    ];
    for (const c of checks) {
        try {
            const sr = await fetch(c.state);
            if (!sr.ok) continue;
            const sd = await sr.json();
            if (c.hasXp(sd)) {
                await fetch(c.cashout, { method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}' });
            }
        } catch { /* silent — never block the close */ }
    }
}

// ── Observe prompt — shown when clicking an occupied casino room ──────────────
function showCasinoObservePrompt(room) {
    const gi   = room.game ? GAME_INFO_MAP[room.game] : null;
    const host = room.occupants[0];
    const canJoin = room.game && ['blackjack','holdem','races','minigames'].includes(room.game);
    setPanel(`
        <div class="cl-panel">
            <div class="cl-panel-title">🎰 Room #${room.room_id + 1} — ${gi ? gi.icon + ' ' + gi.label : 'Casino'}</div>
            <div class="cl-spectate-info" style="margin-bottom:14px">
                <img class="cl-spectate-avatar" src="${esc(host?.avatar||'')}" onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'">
                <div>
                    <div class="cl-spectate-name">${esc(host?.username||'?')}</div>
                    <div class="cl-spectate-game">${gi ? gi.icon + ' ' + gi.label : '🎰 Casino'}</div>
                </div>
            </div>
            <div class="d-flex gap-2 flex-wrap">
                <button class="cl-btn" onclick="window._casinoEnterObserve(${room.room_id})">👁 Watch</button>
                ${canJoin ? `<button class="cl-btn join" onclick="window._casinoEnterObserve(${room.room_id}, true)">🪑 Watch &amp; Request Seat</button>` : ''}
            </div>
        </div>
    `);
}

window._casinoEnterObserve = async function(roomId, requestSeat = false) {
    try {
        const r = await fetch('/api/casino/lobby/observe', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ room_id: roomId })
        });
        const d = await r.json();
        if (!r.ok) { alert(d.detail || 'Failed to observe'); return; }
        _myCasinoRoomId = roomId;
        _viewRoomId = { id: roomId, type: 'casino' };
        if (requestSeat) {
            await fetch('/api/casino/lobby/request_seat', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({ room_id: roomId })
            });
        }
        const room = _casinoRooms.find(r => r.room_id === roomId);
        if (room) showCasinoSpectate(room);
    } catch(e) { alert(e.message); }
};

// ── Observer actions ──────────────────────────────────────────────────────────

window._observerRequestSeat = async function(roomId) {
    try {
        const r = await fetch('/api/casino/lobby/request_seat', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ room_id: roomId })
        });
        const d = await r.json();
        if (!r.ok) { alert(d.detail || 'Failed'); return; }
        alert("✅ You'll be seated at the next round!");
    } catch(e) { alert(e.message); }
};

window._observerCrapsBet = async function(roomId, side) {
    const amt = parseInt(document.getElementById('obs-craps-bet-amt')?.value || '50');
    try {
        const r = await fetch('/api/casino/lobby/observer_bet', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ room_id: roomId, target_id: side, amount: amt })
        });
        const d = await r.json();
        if (!r.ok) { alert(d.detail || 'Failed'); return; }
        alert(`✅ Bet ${amt} XP on ${side}!`);
    } catch(e) { alert(e.message); }
};

window._observerRaceBet = async function(roomId, targetUserId, targetName) {
    const amt = parseInt(document.getElementById('obs-race-bet-amt')?.value || '50');
    try {
        const r = await fetch('/api/casino/lobby/observer_bet', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ room_id: roomId, target_id: targetUserId, amount: amt })
        });
        const d = await r.json();
        if (!r.ok) { alert(d.detail || 'Failed'); return; }
        alert(`✅ Bet ${amt} XP on ${targetName}!`);
    } catch(e) { alert(e.message); }
};

window._observerCoinBet = async function(roomId, pick) {
    const amt = parseInt(document.getElementById('obs-coin-bet-amt')?.value || '50');
    try {
        const r = await fetch('/api/casino/coinflip/observer_bet', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ room_id: roomId, pick, amount: amt })
        });
        const d = await r.json();
        if (!r.ok) { alert(d.detail || 'Failed'); return; }
        alert(`✅ Bet ${amt} XP on ${pick}!`);
    } catch(e) { alert(e.message); }
};

window._observerJoinRace = async function(roomId) {
    const bet = prompt('Enter your race wager (XP):', '100');
    if (!bet) return;
    try {
        // First observe if not already
        if (!_myCasinoRoomId) {
            await fetch('/api/casino/lobby/observe', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({ room_id: roomId })
            });
            _myCasinoRoomId = roomId;
        }
        const r = await fetch('/api/casino/races/room/join', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ room_id: roomId, bet: parseInt(bet), fun_mode: false })
        });
        const d = await r.json();
        if (!r.ok) { alert(d.detail || d.error || 'Failed'); return; }
        alert("✅ You'll race in the next round!");
    } catch(e) { alert(e.message); }
};

window._observerJoinRPS = async function(roomId) {
    const wager = prompt('Enter your RPS wager (XP):', '100');
    if (!wager) return;
    // The host needs to have created a PvP challenge — show the accept flow
    try {
        const r = await fetch('/api/casino/rps/pvp/accept', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ room_id: String(roomId) })
        });
        const d = await r.json();
        if (!r.ok) { alert(d.detail || d.error || 'No active RPS challenge in this room'); return; }
        alert(`✅ Challenge accepted! Wager: ${d.wager} XP. Now choose your move in the game panel.`);
    } catch(e) { alert(e.message); }
};

// ── Craps swap roller (shown in the game panel for the current roller) ─────────
window._crapsSwapRoller = async function(roomId) {
    const room = _casinoRooms.find(r => r.room_id === roomId);
    if (!room || !room.observers || !room.observers.length) {
        alert('No observers available to swap with.');
        return;
    }
    const list = room.observers.map((o, i) => `${i + 1}. ${o.username}`).join('\n');
    const pick = prompt(`Pick a new roller:\n${list}\n\nEnter number:`);
    if (!pick) return;
    const idx = parseInt(pick) - 1;
    if (isNaN(idx) || idx < 0 || idx >= room.observers.length) { alert('Invalid selection'); return; }
    const newRoller = room.observers[idx];
    try {
        const r = await fetch('/api/casino/lobby/craps_swap_roller', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ room_id: roomId, new_roller_id: newRoller.user_id })
        });
        const d = await r.json();
        if (!r.ok) { alert(d.detail || 'Failed'); return; }
        alert(`🎲 ${newRoller.username} is now rolling!`);
    } catch(e) { alert(e.message); }
};

window._casinoLobbyActivity = async function(line) {
    try {
        await fetch('/api/casino/lobby/activity', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ line })
        });
    } catch { /* silent */ }
};

// ── Cleanup on page unload ────────────────────────────────────────────────────
function cleanup() {
    // Remove the shared bus listener so stale callbacks don't fire after navigation
    document.removeEventListener('liveRooms', _onLiveRooms);
    if (_ws) { clearInterval(_ws._ping); _ws.close(); _ws = null; }
    if (_myArenaRoomId !== null) {
        fetch('/api/arena/leave', {method:'POST', keepalive: true}).catch(()=>{});
    }
    if (_myCasinoRoomId !== null) {
        fetch('/api/casino/lobby/leave', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}', keepalive: true}).catch(()=>{});
    }
}

document.addEventListener('dashboardPageLoaded', e => {
    if (e.detail && e.detail.page && !e.detail.page.includes('arena')) cleanup();
});
window.addEventListener('beforeunload', cleanup);

// Expose rooms array for combined online count
window._arenaRooms = _arenaRooms;

// ── Colosseum click handler (delegates to colosseum.js) ──────────────────────
window._uClickColosseum = function() {
    if (typeof window._colosseumOpen === 'function') {
        window._colosseumOpen();
    }
};

// ── Boot ──────────────────────────────────────────────────────────────────────
init();

})();

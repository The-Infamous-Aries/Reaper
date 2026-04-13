/* ── Arena JS ─────────────────────────────────────────────────────────────── */
(function () {
'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
let _ws          = null;
let _rooms       = [];
let _myUserId    = null;
let _myRoomId    = null;   // room I'm currently in (-1 = none)
let _viewRoomId  = null;   // room panel is showing
let _diff        = 'easy';
let _battling    = false;
let _wsRetries   = 0;
const MAX_RETRIES = 8;

// ── DOM helpers ───────────────────────────────────────────────────────────────
const $  = id => document.getElementById(id);
const esc = s  => String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

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
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const url   = `${proto}://${location.host}/api/ws/arena`;
    _ws = new WebSocket(url);

    _ws.onopen = () => {
        _wsRetries = 0;
        // ping every 25s to keep alive
        _ws._ping = setInterval(() => { if (_ws.readyState === 1) _ws.send('ping'); }, 25000);
    };

    _ws.onmessage = e => {
        try {
            const msg = JSON.parse(e.data);
            if (msg.type === 'rooms') {
                _rooms = msg.rooms;
                renderGrid();
                if (_viewRoomId !== null) refreshPanel();
                updateOnlineCount();
            }
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

// ── Room grid ─────────────────────────────────────────────────────────────────
function renderGrid() {
    const grid = $('arena-grid');
    if (!grid) return;

    grid.innerHTML = _rooms.map(room => {
        const isMe    = room.occupants.some(o => o.user_id === _myUserId);
        const isEmpty = room.state === 'empty';
        const stateClass = isEmpty ? 'empty' : room.state;
        const myClass    = isMe ? ' my-room' : '';

        let inner = `<span class="arena-room-num">#${room.room_id + 1}</span>`;

        if (isEmpty) {
            inner += `<div class="arena-empty-icon">🚪</div>
                      <div class="arena-room-label">Empty Room</div>
                      <div class="arena-room-status empty">Available</div>`;
        } else {
            // Avatars
            const avatarHtml = room.occupants.slice(0, 4).map(o =>
                `<img class="arena-avatar${o.status === 'battling' ? ' battling' : ''}"
                      src="${esc(o.avatar)}" alt="${esc(o.username)}"
                      title="${esc(o.username)} — ${esc(o.pet_name)}"
                      onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'">`
            ).join('');
            inner += `<div class="arena-avatars">${avatarHtml}</div>`;

            // Names
            const names = room.occupants.map(o => esc(o.username)).join(' vs ');
            inner += `<div class="arena-room-label" style="font-size:0.62rem">${names}</div>`;

            // Status badge
            const statusMap = {
                npc_battle:  ['npc',      '⚔️ NPC Battle'],
                pvp_waiting: ['pvp-wait', '🔥 Seeking PvP'],
                pvp_battle:  ['pvp-live', '⚡ PvP Live'],
            };
            const [cls, label] = statusMap[room.state] || ['npc', room.state];
            inner += `<div class="arena-room-status ${cls}">${label}</div>`;
        }

        return `<div class="arena-room ${stateClass}${myClass}"
                     data-room="${room.room_id}"
                     onclick="window._arenaClickRoom(${room.room_id})">
                    ${inner}
                </div>`;
    }).join('');
}

function updateOnlineCount() {
    const total = _rooms.reduce((n, r) => n + r.occupants.length, 0);
    const el = $('arena-online');
    if (el) el.textContent = `${total} online`;
}

// ── Room click ────────────────────────────────────────────────────────────────
window._arenaClickRoom = function(roomId) {
    _viewRoomId = roomId;
    const room  = _rooms.find(r => r.room_id === roomId);
    if (!room) return;

    const isMine = room.occupants.some(o => o.user_id === _myUserId);

    if (room.state === 'empty') {
        showJoinPanel(roomId);
    } else if (isMine) {
        showMyRoomPanel(room);
    } else if (room.state === 'pvp_waiting') {
        showChallengePanel(room);
    } else {
        showSpectatePanel(room);
    }
};

function refreshPanel() {
    if (_viewRoomId === null) return;
    const room = _rooms.find(r => r.room_id === _viewRoomId);
    if (!room) return;
    const isMine = room.occupants.some(o => o.user_id === _myUserId);
    if (room.state === 'empty') {
        // keep join panel open
    } else if (isMine) {
        showMyRoomPanel(room);
    } else if (room.state === 'pvp_waiting') {
        showChallengePanel(room);
    } else {
        showSpectatePanel(room);
    }
}

// ── Join panel ────────────────────────────────────────────────────────────────
function showJoinPanel(roomId) {
    // If already in a room, show leave first
    const alreadyIn = _myRoomId !== null;

    setPanel(`
        <div class="arena-panel">
            <div class="arena-panel-title">🚪 Room #${roomId + 1}</div>
            ${alreadyIn ? `<div style="font-size:0.75rem;color:#e74c3c;margin-bottom:10px">⚠️ You're already in a room. Leave it first.</div>` : ''}
            <div style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:14px">
                Choose your battle mode and enter the room.
            </div>

            <div style="font-size:0.72rem;color:var(--text-secondary);margin-bottom:6px">Mode</div>
            <div class="d-flex gap-2 mb-3">
                <button class="arena-btn" id="mode-npc" onclick="window._arenaSetMode('npc',${roomId})">⚔️ NPC Battle</button>
                <button class="arena-btn" id="mode-pvp" onclick="window._arenaSetMode('pvp',${roomId})">🔥 Seek PvP</button>
            </div>

            <div id="join-npc-opts" style="display:none">
                <div style="font-size:0.72rem;color:var(--text-secondary);margin-bottom:6px">Difficulty</div>
                <div class="d-flex gap-2 mb-3 flex-wrap">
                    ${['easy','average','hard'].map(d =>
                        `<button class="arena-diff-btn${d===_diff?' active':''}" onclick="window._arenaSetDiff('${d}')">${d.charAt(0).toUpperCase()+d.slice(1)}</button>`
                    ).join('')}
                </div>
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
        </div>
    `);
}

window._arenaSetMode = function(mode, roomId) {
    $('join-npc-opts') && ($('join-npc-opts').style.display = mode === 'npc' ? '' : 'none');
    $('join-pvp-opts') && ($('join-pvp-opts').style.display = mode === 'pvp' ? '' : 'none');
    ['mode-npc','mode-pvp'].forEach(id => {
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
    const btn = $('join-enter-btn') || $('join-pvp-btn');
    if (btn) btn.disabled = true;
    try {
        const r = await fetch('/api/arena/join', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({room_id: roomId, mode})
        });
        const d = await r.json();
        if (!r.ok) { alert(d.detail || 'Failed to join'); return; }
        _myRoomId = roomId;
        _viewRoomId = roomId;
        // Panel will update via WS broadcast
        if (mode === 'npc') {
            showMyRoomPanel(_rooms.find(rm => rm.room_id === roomId) || {room_id: roomId, state:'npc_battle', occupants:[], battle_log:[]});
        }
    } catch(e) { alert(e.message); }
    finally { if (btn) btn.disabled = false; }
};

// ── My room panel ─────────────────────────────────────────────────────────────
function showMyRoomPanel(room) {
    const isPvpWait = room.state === 'pvp_waiting';
    const isBattling = _battling;

    const logHtml = room.battle_log && room.battle_log.length
        ? `<div class="arena-log mt-3">${room.battle_log.map(l => `<div>${esc(l)}</div>`).join('')}</div>`
        : '';

    setPanel(`
        <div class="arena-panel">
            <div class="d-flex justify-content-between align-items-center mb-2">
                <div class="arena-panel-title">Room #${room.room_id + 1} — Your Room</div>
                <button class="arena-btn danger" style="padding:4px 10px;font-size:0.7rem" onclick="window._arenaLeave()">Leave</button>
            </div>

            ${isPvpWait ? `
                <div style="font-size:0.82rem;color:var(--gold-primary);margin-bottom:10px;text-align:center">
                    🔥 Seeking PvP — your room is glowing for others to see.<br>
                    <span style="font-size:0.72rem;color:var(--text-secondary)">Waiting for a challenger...</span>
                </div>
            ` : `
                <div style="font-size:0.72rem;color:var(--text-secondary);margin-bottom:8px">Difficulty</div>
                <div class="d-flex gap-2 mb-3 flex-wrap">
                    ${['easy','average','hard'].map(d =>
                        `<button class="arena-diff-btn${d===_diff?' active':''}" onclick="window._arenaSetDiff('${d}')">${d.charAt(0).toUpperCase()+d.slice(1)}</button>`
                    ).join('')}
                </div>
                <button class="arena-btn" id="arena-fight-btn" onclick="window._arenaFight(${room.room_id})" ${isBattling?'disabled':''}>
                    ${isBattling ? '⏳ Battling...' : '⚔️ Start NPC Battle'}
                </button>
            `}

            ${logHtml}
        </div>
    `);
}

window._arenaFight = async function(roomId) {
    if (_battling) return;
    _battling = true;
    const btn = $('arena-fight-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Battling...'; }

    try {
        const r = await fetch('/api/arena/battle/npc', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({room_id: roomId, difficulty: _diff})
        });
        const d = await r.json();
        if (!r.ok) { alert(d.detail || 'Battle failed'); return; }
        showBattleResult(d, roomId);
    } catch(e) { alert(e.message); }
    finally { _battling = false; }
};

function showBattleResult(d, roomId) {
    const won = d.won;
    const turns = d.turns || [];
    const last  = turns[turns.length - 1] || {};
    const pHp   = last.player_hp ?? 0;
    const eHp   = last.enemy_hp  ?? 0;
    const pMax  = d.player?.max_hp || 1;
    const eMax  = d.enemy?.max_hp  || 1;

    const logLines = (d.log || []).map(l => `<div>${esc(l)}</div>`).join('');

    setPanel(`
        <div class="arena-panel">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <div class="arena-panel-title" style="color:${won?'#2ecc71':'#e74c3c'}">${won?'🏆 Victory!':'💀 Defeated'}</div>
                <button class="arena-btn danger" style="padding:4px 10px;font-size:0.7rem" onclick="window._arenaLeave()">Leave Room</button>
            </div>

            <div class="row g-2 mb-3">
                <div class="col-6">
                    <div style="font-size:0.7rem;color:var(--gold-secondary);margin-bottom:3px">${esc(d.player?.name||'Your Pet')}</div>
                    ${hpBar(pHp, pMax, false)}
                </div>
                <div class="col-6">
                    <div style="font-size:0.7rem;color:var(--text-secondary);margin-bottom:3px">${esc(d.enemy?.name||'Enemy')}</div>
                    ${hpBar(eHp, eMax, true)}
                </div>
            </div>

            <div style="font-size:0.8rem;color:var(--gold-primary);margin-bottom:6px">📈 +${d.xp_gained||0} XP</div>

            <details>
                <summary style="cursor:pointer;font-size:0.75rem;color:var(--text-secondary);user-select:none">📜 Battle Log (${turns.length} turns)</summary>
                <div class="arena-log mt-2">${logLines || '<div style="opacity:0.4">No log available</div>'}</div>
            </details>

            <div class="mt-3 d-flex gap-2 flex-wrap">
                <button class="arena-btn" onclick="window._arenaFight(${roomId})">⚔️ Fight Again</button>
                <button class="arena-btn danger" onclick="window._arenaLeave()">Leave Room</button>
            </div>
        </div>
    `);

    // Level change popup
    if (d.level_change) {
        if (typeof showLevelChangePopup === 'function') {
            showLevelChangePopup(d.level_change, d.level_change.new_level < d.level_change.old_level);
        }
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
    const btn = document.querySelector(`#arena-panel-area .arena-btn`);
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
    const log = (d.log || []).map(l => `<div>${esc(l)}</div>`).join('');
    const iWon = d.winner_id === _myUserId;
    setPanel(`
        <div class="arena-panel">
            <div class="arena-panel-title" style="color:${iWon?'#2ecc71':'#e74c3c'}">${iWon?'🏆 You Won!':'💀 You Lost'}</div>
            <div style="font-size:0.82rem;color:var(--text-secondary);margin-bottom:10px">
                ${esc(d.winner_name)} defeated ${esc(d.loser_name)}
            </div>
            <div style="font-size:0.8rem;color:var(--gold-primary);margin-bottom:8px">
                📈 +${iWon ? d.winner_xp : d.loser_xp} XP
            </div>
            <details>
                <summary style="cursor:pointer;font-size:0.75rem;color:var(--text-secondary);user-select:none">📜 Battle Log</summary>
                <div class="arena-log mt-2">${log}</div>
            </details>
        </div>
    `);
}

// ── Spectate panel ────────────────────────────────────────────────────────────
function showSpectatePanel(room) {
    const occs = room.occupants;
    const combatants = occs.slice(0, 2).map(o => `
        <div class="arena-combatant">
            <img src="${esc(o.avatar)}" onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'" alt="">
            <div class="name">${esc(o.username)}</div>
            <div class="pet-name">🐾 ${esc(o.pet_name)}</div>
        </div>
    `).join('');

    const vsSection = occs.length >= 2
        ? `<div class="d-flex align-items-center gap-2 mb-3">${combatants.split('</div>').filter(Boolean).map((c,i) => i===0 ? c+'</div>' : c+'</div>').join('<div class="arena-vs">VS</div>')}</div>`
        : `<div class="mb-3">${combatants}</div>`;

    const logHtml = room.battle_log && room.battle_log.length
        ? room.battle_log.map(l => `<div>${esc(l)}</div>`).join('')
        : '<div style="opacity:0.4">Battle in progress...</div>';

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
            <div class="arena-log" id="spectate-log">${logHtml}</div>
        </div>
    `);
    scrollLog();
}

function scrollLog() {
    const log = $('spectate-log');
    if (log) log.scrollTop = log.scrollHeight;
}

// ── Leave ─────────────────────────────────────────────────────────────────────
window._arenaLeave = async function() {
    try {
        await fetch('/api/arena/leave', {method:'POST'});
    } catch { /* ignore */ }
    _myRoomId   = null;
    _viewRoomId = null;
    setPanel(`
        <div class="arena-panel" style="text-align:center;padding:32px 18px">
            <div style="font-size:2rem;opacity:0.3">⚔️</div>
            <div style="color:var(--text-secondary);font-size:0.82rem;margin-top:8px">Select a room to get started.</div>
        </div>
    `);
};

// ── Helpers ───────────────────────────────────────────────────────────────────
function setPanel(html) {
    const area = $('arena-panel-area');
    if (area) area.innerHTML = html;
}

function hpBar(cur, max, enemy) {
    const pct   = max > 0 ? Math.max(0, Math.min(100, Math.round((cur / max) * 100))) : 0;
    const color = enemy
        ? (pct > 50 ? '#e74c3c' : pct > 25 ? '#f39c12' : '#95a5a6')
        : (pct > 50 ? '#2ecc71' : pct > 25 ? '#f39c12' : '#e74c3c');
    return `<div class="arena-hp-wrap"><div class="arena-hp-bar" style="width:${pct}%;background:${color}"></div></div>
            <div style="font-size:0.65rem;color:var(--text-secondary);margin-top:1px">${cur} / ${max} HP</div>`;
}

// ── Cleanup on page unload ────────────────────────────────────────────────────
function cleanup() {
    if (_ws) { clearInterval(_ws._ping); _ws.close(); _ws = null; }
    // Leave room silently
    if (_myRoomId !== null) {
        fetch('/api/arena/leave', {method:'POST', keepalive: true}).catch(()=>{});
    }
}

document.addEventListener('dashboardPageLoaded', e => {
    if (e.detail && e.detail.page && !e.detail.page.includes('arena')) cleanup();
});
window.addEventListener('beforeunload', cleanup);

// ── Boot ──────────────────────────────────────────────────────────────────────
init();

})();

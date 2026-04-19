/* ── Casino Lobby JS — mirrors arena.js room/WS pattern ──────────────────── */
(function () {
'use strict';

const $ = id => document.getElementById(id);
const esc = s => String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

// ── State ─────────────────────────────────────────────────────────────────────
let _ws         = null;
let _rooms      = [];
let _myUserId   = null;
let _myRoomId   = null;
let _viewRoomId = null;
let _wsRetries  = 0;
const MAX_RETRIES = 8;

const GAME_INFO = {
    slots:     { label: "Slot Machine",  icon: "🎰" },
    blackjack: { label: "Blackjack",     icon: "🃏" },
    craps:     { label: "Craps",         icon: "🎲" },
    holdem:    { label: "Texas Hold'em", icon: "♠️" },
    races:     { label: "Pet Races",     icon: "🏁" },
    minigames: { label: "Mini-Games",    icon: "🎮" },
    scratch:   { label: "Scratch Cards", icon: "🎫" },
};

// ── Boot ──────────────────────────────────────────────────────────────────────
async function init() {
    if (!$('cl-root')) return;

    try {
        const r = await fetch('/api/discord/user');
        if (!r.ok) { showLoginPrompt(); return; }
        const u = await r.json();
        _myUserId = String(u.id);
    } catch { showLoginPrompt(); return; }

    $('cl-loading').style.display = 'none';
    $('cl-main').style.display    = '';

    // Check if already in a room
    try {
        const r = await fetch('/api/casino/lobby/my_room');
        const d = await r.json();
        if (d.room_id !== null && d.room_id !== undefined) {
            _myRoomId = d.room_id;
        }
    } catch { /* silent */ }

    connectWS();
}

function showLoginPrompt() {
    $('cl-loading').style.display      = 'none';
    $('cl-login-prompt').style.display = '';
}

// ── WebSocket ─────────────────────────────────────────────────────────────────
function connectWS() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    _ws = new WebSocket(`${proto}://${location.host}/api/ws/casino`);

    _ws.onopen = () => {
        _wsRetries = 0;
        _ws._ping = setInterval(() => { if (_ws.readyState === 1) _ws.send('ping'); }, 25000);
    };

    _ws.onmessage = e => {
        try {
            const msg = JSON.parse(e.data);
            if (msg.type === 'rooms') {
                _rooms = msg.rooms;
                renderGrid();
                updateOnlineCount();
                if (_viewRoomId !== null) refreshPanel();
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
    const grid = $('cl-room-grid');
    if (!grid) return;

    grid.innerHTML = _rooms.map(room => {
        const isMe    = room.occupants.some(o => o.user_id === _myUserId);
        const isEmpty = room.state === 'empty';
        const myClass = isMe ? ' my-room' : '';
        const gi      = room.game ? GAME_INFO[room.game] : null;

        let inner = `<div class="cl-room-num">#${room.room_id + 1}</div>`;

        if (isEmpty) {
            inner += `<div class="cl-room-icon" style="opacity:0.2">🎰</div>
                      <div class="cl-room-status empty">Open</div>`;
        } else {
            // Show avatars
            const avatarHtml = room.occupants.slice(0, 2).map(o =>
                `<img class="cl-avatar-mini" src="${esc(o.avatar)}"
                      title="${esc(o.username)}"
                      onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'">`
            ).join('');
            inner += `<div style="display:flex;gap:2px;justify-content:center">${avatarHtml}</div>`;
            inner += `<div class="cl-room-icon">${gi ? gi.icon : '🎰'}</div>`;
            const statusLabels = {
                picking: ['picking', 'Choosing'],
                playing: ['playing', gi ? gi.label : 'Playing'],
                open:    ['open',    'Join Me!'],
            };
            const [cls, lbl] = statusLabels[room.state] || ['playing', room.state];
            inner += `<div class="cl-room-status ${cls}">${lbl}</div>`;
        }

        return `<div class="cl-room ${room.state}${myClass}"
                     data-room="${room.room_id}"
                     onclick="window._clClickRoom(${room.room_id})">
                    ${inner}
                </div>`;
    }).join('');
}

function updateOnlineCount() {
    const total = _rooms.reduce((n, r) => n + r.occupants.length, 0);
    const el = $('cl-online');
    if (el) el.textContent = `${total} online`;
}

// ── Panel helpers ─────────────────────────────────────────────────────────────
function setPanel(html) {
    const area = $('cl-panel-area');
    if (area) area.innerHTML = html;
}

function refreshPanel() {
    if (_viewRoomId === null) return;
    const room = _rooms.find(r => r.room_id === _viewRoomId);
    if (!room) return;
    const isMe = room.occupants.some(o => o.user_id === _myUserId);

    if (room.state === 'empty') {
        // keep join panel open
    } else if (isMe) {
        showMyRoomPanel(room);
    } else {
        showSpectatePanel(room);
    }
}

// ── Room click ────────────────────────────────────────────────────────────────
window._clClickRoom = function(roomId) {
    _viewRoomId = roomId;
    const room  = _rooms.find(r => r.room_id === roomId);
    if (!room) return;
    const isMe = room.occupants.some(o => o.user_id === _myUserId);

    if (room.state === 'empty') {
        showJoinPanel(roomId);
    } else if (isMe) {
        showMyRoomPanel(room);
    } else if (room.state === 'open') {
        showJoinOpenPanel(room);
    } else {
        showSpectatePanel(room);
    }
};

// ── Join empty room ───────────────────────────────────────────────────────────
function showJoinPanel(roomId) {
    const alreadyIn = _myRoomId !== null;
    setPanel(`
        <div class="cl-panel">
            <div class="cl-panel-title">🎰 Room #${roomId + 1}</div>
            ${alreadyIn ? `<div style="font-size:0.75rem;color:#e74c3c;margin-bottom:10px">⚠️ Leave your current room first.</div>` : ''}
            <div style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:16px">
                Enter this room and pick a game to play. Others can watch or join open games.
            </div>
            <button class="cl-btn join" onclick="window._clJoin(${roomId})" ${alreadyIn ? 'disabled' : ''}>
                Enter Room
            </button>
        </div>
    `);
}

window._clJoin = async function(roomId) {
    try {
        const r = await fetch('/api/casino/lobby/join', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ room_id: roomId })
        });
        const d = await r.json();
        if (!r.ok) { alert(d.detail || 'Failed to join'); return; }
        _myRoomId   = roomId;
        _viewRoomId = roomId;
        // WS broadcast will update grid; show game picker immediately
        const room = _rooms.find(r => r.room_id === roomId) || { room_id: roomId, state:'picking', occupants:[], activity:[], game:null };
        showMyRoomPanel(room);
    } catch(e) { alert(e.message); }
};

// ── My room panel ─────────────────────────────────────────────────────────────
function showMyRoomPanel(room) {
    const gi = room.game ? GAME_INFO[room.game] : null;

    setPanel(`
        <div class="cl-panel">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <div class="cl-panel-title">Room #${room.room_id + 1} — Your Room</div>
                <button class="cl-btn danger" style="padding:4px 10px;font-size:0.7rem" onclick="window._clLeave()">Leave</button>
            </div>

            ${gi ? `
                <div style="font-size:0.82rem;color:var(--gold-secondary);margin-bottom:14px;text-align:center">
                    ${gi.icon} Currently playing: <strong>${gi.label}</strong>
                </div>
                <div class="d-flex gap-2 justify-content-center mb-3">
                    <button class="cl-btn" onclick="window._clPlayGame('${room.game}')">
                        ${gi.icon} Open ${gi.label}
                    </button>
                    <button class="cl-btn" style="font-size:0.72rem;padding:6px 12px" onclick="window._clChangePick()">
                        Change Game
                    </button>
                </div>
            ` : `
                <div style="font-size:0.78rem;color:var(--text-secondary);margin-bottom:12px">Pick a game to play:</div>
                <div class="cl-game-grid">
                    ${Object.entries(GAME_INFO).map(([key, g]) => `
                        <button class="cl-game-btn" onclick="window._clPickGame('${key}', ${room.room_id})">
                            <span class="game-icon">${g.icon}</span>
                            <span class="game-label">${g.label}</span>
                        </button>
                    `).join('')}
                </div>
            `}

            ${room.activity && room.activity.length ? `
                <div style="font-size:0.68rem;color:var(--text-secondary);margin-bottom:4px">Activity</div>
                <div class="cl-activity-log">
                    ${room.activity.map(l => `<div class="cl-activity-line">${esc(l)}</div>`).join('')}
                </div>
            ` : ''}
        </div>
    `);
}

window._clChangePick = function() {
    const room = _rooms.find(r => r.room_id === _myRoomId);
    if (room) { room.game = null; showMyRoomPanel(room); }
};

window._clPickGame = async function(game, roomId) {
    try {
        const r = await fetch('/api/casino/lobby/set_game', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ game })
        });
        if (!r.ok) { const d = await r.json(); alert(d.detail || 'Failed'); return; }
        // Navigate to game page
        window._clPlayGame(game);
    } catch(e) { alert(e.message); }
};

window._clPlayGame = function(game) {
    // Use the dashboard router — same as casino.html cards do
    if (typeof navigateTo === 'function') {
        navigateTo(game);
    } else {
        history.pushState({ page: game }, '', '?page=' + game);
        if (typeof loadPage === 'function') loadPage(game, null, 'script', null);
    }
};

// ── Join open room (minigames with open seat) ─────────────────────────────────
function showJoinOpenPanel(room) {
    const gi = GAME_INFO[room.game] || { label: room.game, icon: '🎮' };
    const host = room.occupants[0];
    setPanel(`
        <div class="cl-panel">
            <div class="cl-panel-title">Room #${room.room_id + 1} — Open Seat</div>
            <div class="cl-spectate-info">
                <img class="cl-spectate-avatar" src="${esc(host?.avatar||'')}" onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'">
                <div>
                    <div class="cl-spectate-name">${esc(host?.username||'?')}</div>
                    <div class="cl-spectate-game">${gi.icon} ${gi.label} — looking for a player</div>
                </div>
            </div>
            <div class="d-flex gap-2">
                <button class="cl-btn join" onclick="window._clJoinOpen(${room.room_id}, '${room.game}')">
                    Join Game
                </button>
                <button class="cl-btn" onclick="window._clSpectate(${room.room_id})">
                    👁 Watch
                </button>
            </div>
        </div>
    `);
}

window._clJoinOpen = async function(roomId, game) {
    try {
        const r = await fetch('/api/casino/lobby/join', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ room_id: roomId })
        });
        const d = await r.json();
        if (!r.ok) { alert(d.detail || 'Failed'); return; }
        _myRoomId = roomId;
        // Set game and navigate
        await fetch('/api/casino/lobby/set_game', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ game })
        });
        window._clPlayGame(game);
    } catch(e) { alert(e.message); }
};

// ── Spectate panel ────────────────────────────────────────────────────────────
function showSpectatePanel(room) {
    const gi = room.game ? GAME_INFO[room.game] : null;
    const players = room.occupants;

    setPanel(`
        <div class="cl-panel">
            <div class="cl-panel-title">Room #${room.room_id + 1} — Spectating</div>

            <div style="display:flex;flex-direction:column;gap:8px;margin-bottom:14px">
                ${players.map(p => `
                    <div class="cl-spectate-info">
                        <img class="cl-spectate-avatar" src="${esc(p.avatar)}" onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'">
                        <div>
                            <div class="cl-spectate-name">${esc(p.username)}</div>
                            <div class="cl-spectate-game">
                                ${gi ? gi.icon + ' ' + gi.label : '🎰 Casino'}
                                ${p.pet_name ? ` · 🐾 ${esc(p.pet_name)}` : ''}
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>

            ${room.activity && room.activity.length ? `
                <div style="font-size:0.68rem;color:var(--text-secondary);margin-bottom:4px">Live Activity</div>
                <div class="cl-activity-log" id="cl-spectate-log">
                    ${room.activity.map(l => `<div class="cl-activity-line">${esc(l)}</div>`).join('')}
                </div>
            ` : `<div style="font-size:0.78rem;color:var(--text-secondary);text-align:center;padding:20px 0">Waiting for activity...</div>`}
        </div>
    `);
}

window._clSpectate = function(roomId) {
    _viewRoomId = roomId;
    const room = _rooms.find(r => r.room_id === roomId);
    if (room) showSpectatePanel(room);
};

// ── Leave ─────────────────────────────────────────────────────────────────────
window._clLeave = async function() {
    try {
        await fetch('/api/casino/lobby/leave', {
            method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}'
        });
    } catch { /* silent */ }
    _myRoomId   = null;
    _viewRoomId = null;
    setPanel(`
        <div class="cl-panel" style="text-align:center;padding:40px 18px">
            <div style="font-size:2.5rem;opacity:0.25">🎰</div>
            <div style="color:var(--text-secondary);font-size:0.85rem;margin-top:10px">Select a room above to get started.</div>
        </div>
    `);
};

// ── Global helper — game pages call this to post activity ─────────────────────
window._casinoLobbyActivity = async function(line) {
    try {
        await fetch('/api/casino/lobby/activity', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ line })
        });
    } catch { /* silent — never block gameplay */ }
};

// ── Boot ──────────────────────────────────────────────────────────────────────
init();

})();

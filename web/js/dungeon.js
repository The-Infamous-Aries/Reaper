// Dungeon Crawl JavaScript
(function () {
'use strict';

console.log('[dungeon.js] Script loaded!');

let currentDungeon = null;
let currentUser = null;
let pollInterval = null;

// Event type emojis
const EVENT_EMOJIS = {
    'monster': '⚔️',
    'boss': '👹',
    'chest': '📦',
    'chest1': '📦',
    'chest2': '🎁',
    'chest3': '💎',
    'chest4': '✨',
    'trap': '🪤',
    'shrine': '⛩️'
};

// Initialize function
async function initializeDungeon() {
    console.log('[dungeon.js] Initializing...');
    console.log('[dungeon.js] document.readyState:', document.readyState);
    console.log('[dungeon.js] Looking for buttons...');
    
    await loadCurrentUser();
    await loadActiveDungeons();
    
    // Event listeners
    const createSoloBtn = document.getElementById('create-solo-btn');
    const createPartyBtn = document.getElementById('create-party-btn');
    const continueBtn = document.getElementById('continue-btn');
    const addInviteBtn = document.getElementById('add-invite-btn');
    const startPartyBtn = document.getElementById('start-party-dungeon-btn');
    
    console.log('[dungeon.js] Solo button:', createSoloBtn);
    console.log('[dungeon.js] Party button:', createPartyBtn);
    
    if (createSoloBtn) {
        console.log('[dungeon.js] Attaching Solo button listener');
        createSoloBtn.addEventListener('click', createSoloDungeon);
    } else {
        console.error('[dungeon.js] Solo button not found!');
    }
    
    if (createPartyBtn) {
        console.log('[dungeon.js] Attaching Party button listener');
        createPartyBtn.addEventListener('click', showPartyModal);
    } else {
        console.error('[dungeon.js] Party button not found!');
    }
    
    if (continueBtn) continueBtn.addEventListener('click', markReady);
    if (addInviteBtn) addInviteBtn.addEventListener('click', addPartyInviteInput);
    if (startPartyBtn) startPartyBtn.addEventListener('click', createPartyDungeon);
    
    console.log('[dungeon.js] Initialization complete');
}

// Load current user
async function loadCurrentUser() {
    try {
        const response = await fetch('/api/discord/me');
        if (response.ok) {
            currentUser = await response.json();
            console.log('[dungeon.js] User loaded:', currentUser);
        } else {
            console.log('[dungeon.js] User not logged in');
        }
    } catch (error) {
        console.error('Error loading user:', error);
    }
}

// Load active dungeons
async function loadActiveDungeons() {
    const container = document.getElementById('active-dungeons-list');
    if (!container) {
        console.error('[dungeon.js] active-dungeons-list element not found');
        return;
    }
    
    try {
        console.log('[dungeon.js] Fetching active dungeons...');
        const response = await fetch('/api/dungeon/active');
        
        if (!response.ok) {
            console.log('[dungeon.js] No active dungeons or error:', response.status);
            container.innerHTML = '<p class="text-muted">No active dungeons</p>';
            return;
        }
        
        const dungeons = await response.json();
        console.log('[dungeon.js] Active dungeons:', dungeons);
        
        if (!dungeons || dungeons.length === 0) {
            container.innerHTML = '<p class="text-muted">No active dungeons</p>';
            return;
        }
        
        container.innerHTML = dungeons.map(dungeon => `
            <div class="dungeon-list-item" onclick="loadDungeon('${dungeon.dungeon_id}')">
                <div class="dungeon-list-info">
                    <div class="dungeon-list-title">Floor ${dungeon.current_floor} - Room ${dungeon.current_room}</div>
                    <div class="dungeon-list-details">
                        ${dungeon.party_size} player${dungeon.party_size > 1 ? 's' : ''} • 
                        ${dungeon.total_rooms_cleared} rooms cleared
                    </div>
                </div>
                <button class="btn-dungeon-primary btn-sm">Continue</button>
            </div>
        `).join('');
    } catch (error) {
        console.error('[dungeon.js] Error loading dungeons:', error);
        container.innerHTML = '<p class="text-muted">No active dungeons</p>';
    }
}

// Create solo dungeon
async function createSoloDungeon() {
    try {
        showLoading();
        const response = await fetch('/api/dungeon/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ party_members: [] })
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to create dungeon');
        }

        const data = await response.json();
        await loadDungeon(data.dungeon_id);
    } catch (error) {
        console.error('Error creating dungeon:', error);
        alert('Failed to create dungeon: ' + error.message);
        showLobby();
    }
}

// Show party modal
function showPartyModal() {
    // Reset modal
    const inviteList = document.getElementById('party-invite-list');
    inviteList.innerHTML = `
        <div class="party-invite-input mb-2">
            <label>Player 2 Discord ID:</label>
            <input type="text" class="form-control party-member-input" placeholder="Enter Discord User ID">
        </div>
    `;
    
    const modal = new bootstrap.Modal(document.getElementById('partyModal'));
    modal.show();
}

// Add party invite input
function addPartyInviteInput() {
    const inviteList = document.getElementById('party-invite-list');
    const currentInputs = inviteList.querySelectorAll('.party-invite-input').length;
    
    if (currentInputs >= 3) {
        alert('Maximum party size is 4 players (including you)');
        return;
    }
    
    const newInput = document.createElement('div');
    newInput.className = 'party-invite-input mb-2';
    newInput.innerHTML = `
        <label>Player ${currentInputs + 2} Discord ID:</label>
        <div class="input-group">
            <input type="text" class="form-control party-member-input" placeholder="Enter Discord User ID">
            <button class="btn btn-danger btn-sm" onclick="removePartyInviteInput(this)">Remove</button>
        </div>
    `;
    
    inviteList.appendChild(newInput);
}

// Remove party invite input
function removePartyInviteInput(button) {
    button.closest('.party-invite-input').remove();
    
    // Renumber labels
    const inputs = document.querySelectorAll('.party-invite-input');
    inputs.forEach((input, index) => {
        input.querySelector('label').textContent = `Player ${index + 2} Discord ID:`;
    });
}

// Create party dungeon
async function createPartyDungeon() {
    try {
        // Get all user IDs
        const inputs = document.querySelectorAll('.party-member-input');
        const partyMembers = [];
        
        for (const input of inputs) {
            const userId = input.value.trim();
            if (userId) {
                // Validate it's a number
                if (!/^\d+$/.test(userId)) {
                    alert(`Invalid Discord ID: ${userId}. Must be numbers only.`);
                    return;
                }
                partyMembers.push(parseInt(userId));
            }
        }
        
        if (partyMembers.length === 0) {
            alert('Please add at least one other player!');
            return;
        }
        
        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('partyModal'));
        modal.hide();
        
        showLoading();
        
        const response = await fetch('/api/dungeon/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ party_members: partyMembers })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to create dungeon');
        }
        
        const data = await response.json();
        await loadDungeon(data.dungeon_id);
    } catch (error) {
        console.error('Error creating party dungeon:', error);
        alert(`Failed to create party dungeon: ${error.message}`);
        showLobby();
    }
}

// Load dungeon
async function loadDungeon(dungeonId) {
    try {
        showLoading();
        
        const response = await fetch(`/api/dungeon/${dungeonId}`);
        if (!response.ok) {
            throw new Error('Failed to load dungeon');
        }
        
        currentDungeon = await response.json();
        renderDungeon();
        showDungeon();
        
        // Start polling for updates
        startPolling();
    } catch (error) {
        console.error('Error loading dungeon:', error);
        alert('Failed to load dungeon. Please try again.');
        showLobby();
    }
}

// Render dungeon UI
function renderDungeon() {
    if (!currentDungeon) return;
    
    // Update floor/room indicators
    document.getElementById('current-floor').textContent = currentDungeon.current_floor;
    document.getElementById('current-room').textContent = currentDungeon.current_room;
    
    // Render map
    renderMap();
    
    // Render party
    renderParty();
    
    // Render active effects
    renderActiveEffects();
    
    // Render current room
    renderCurrentRoom();
}

// Render dungeon map
function renderMap() {
    const mapContainer = document.getElementById('dungeon-map');
    const rooms = currentDungeon.dungeon_state.rooms;
    const currentRoom = currentDungeon.current_room;

    // Static image paths for each event type
    const EVENT_IMGS = {
        'monster': '/static/Emojis/Crawl/enemy.png',
        'boss':    '/static/Emojis/Crawl/boss.png',
        'chest':   '/static/Emojis/Pets/Equipment/chest1.png',
        'trap':    '/static/Emojis/Crawl/trap.png',
        'shrine':  '/static/Emojis/Crawl/shrine.png',
    };

    mapContainer.innerHTML = rooms.map(room => {
        const isCurrent   = room.room === currentRoom;
        const isCompleted = room.completed;
        // Locked = future room that hasn't been reached yet
        const isLocked    = room.room > currentRoom;

        let classes = ['room-icon'];
        if (isCurrent)   classes.push('current');
        if (isCompleted) classes.push('completed');
        if (isLocked)    classes.push('locked');

        // Choose the right chest image based on chest_type stored in room data
        let imgSrc = EVENT_IMGS[room.event_type] || '/static/Emojis/Crawl/shrine.png';
        if (room.event_type === 'chest' && room.chest_emoji) {
            imgSrc = `/static/Emojis/Pets/Equipment/${room.chest_emoji}.png`;
        } else if (['chest1','chest2','chest3','chest4'].includes(room.event_type)) {
            const chestEmoji = room.chest_emoji || room.event_type;
            imgSrc = `/static/Emojis/Pets/Equipment/${chestEmoji}.png`;
        }

        // Locked rooms show a ? — don't reveal event type
        const inner = isLocked
            ? `<span class="room-number">${room.room}</span><span class="room-question">?</span>`
            : `<span class="room-number">${room.room}</span><img class="room-event-img" src="${imgSrc}" alt="${room.event_type}" onerror="this.style.display='none'">`;

        return `<div class="${classes.join(' ')}" title="${isLocked ? 'Unknown' : room.event_type}">${inner}</div>`;
    }).join('');
}

// Render party list
function renderParty() {
    const partyContainer = document.getElementById('party-list');
    const partyMembers = currentDungeon.party_members;
    const readyUsers = currentDungeon.ready_users || [];
    
    if (partyMembers.length === 1) {
        partyContainer.innerHTML = '<p class="text-muted">Solo adventure</p>';
        return;
    }
    
    partyContainer.innerHTML = partyMembers.map(memberId => {
        const isReady = readyUsers.includes(String(memberId));
        const isCurrentUser = currentUser && String(currentUser.id) === String(memberId);
        
        return `
            <div class="party-member ${isReady ? 'ready' : 'not-ready'}">
                <div class="party-member-avatar"></div>
                <div class="party-member-info">
                    <div class="party-member-name">
                        ${isCurrentUser ? 'You' : `Player ${memberId}`}
                    </div>
                    <div class="party-member-status">
                        ${isReady ? '✅ Ready' : '⏳ Not Ready'}
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// Render active effects
function renderActiveEffects() {
    const effectsContainer = document.getElementById('active-effects-list');
    const buffs = currentDungeon.party_buffs || {};
    
    let allEffects = [];
    for (const userId in buffs) {
        const userBuffs = buffs[userId];
        allEffects = allEffects.concat(userBuffs.map(buff => ({
            ...buff,
            userId: userId
        })));
    }
    
    if (allEffects.length === 0) {
        effectsContainer.innerHTML = '<p class="text-muted">No active effects</p>';
        return;
    }
    
    effectsContainer.innerHTML = allEffects.map(effect => `
        <div class="effect-item ${effect.type}">
            <div class="effect-emoji">${_renderEmoji(effect.emoji, 18)}</div>
            <div class="effect-info">
                <div class="effect-name">${effect.name}</div>
                <div class="effect-duration">${effect.rooms_remaining} rooms remaining</div>
            </div>
        </div>
    `).join('');
}

// Render current room
function renderCurrentRoom() {
    const roomData = currentDungeon.current_room_data;
    if (!roomData) return;
    
    const eventType = roomData.event_type;
    const roomContent = document.getElementById('room-content');
    const roomTitle = document.getElementById('room-title');
    
    roomTitle.textContent = `${EVENT_EMOJIS[eventType]} Room ${currentDungeon.current_room}`;
    
    switch (eventType) {
        case 'monster':
            renderMonsterRoom(roomContent, roomData);
            break;
        case 'boss':
            renderBossRoom(roomContent, roomData);
            break;
        case 'chest':
        case 'chest1':
        case 'chest2':
        case 'chest3':
        case 'chest4':
            renderChestRoom(roomContent, roomData);
            break;
        case 'trap':
            renderTrapRoom(roomContent, roomData);
            break;
        case 'shrine':
            renderShrineRoom(roomContent, roomData);
            break;
        default:
            roomContent.innerHTML = '<p>Unknown room type</p>';
    }
    
    updateContinueButton();
}

// Render monster room
function renderMonsterRoom(container, roomData) {
    if (roomData.battle_active) {
        container.innerHTML = `
            <div class="room-event-container">
                <div class="room-event-icon"><img src="/static/Emojis/Crawl/enemy.png" style="width:80px;height:80px;object-fit:contain"></div>
                <div class="room-event-description">Battle in progress...</div>
                <button class="btn-dungeon-primary" onclick="openBattle()">Join Battle</button>
            </div>
        `;
    } else if (roomData.completed) {
        container.innerHTML = `
            <div class="room-event-container">
                <div class="room-event-icon">✅</div>
                <div class="room-event-description">Monster defeated!</div>
            </div>
        `;
    } else {
        container.innerHTML = `
            <div class="room-event-container">
                <div class="room-event-icon"><img src="/static/Emojis/Crawl/enemy.png" style="width:80px;height:80px;object-fit:contain"></div>
                <div class="room-event-description">A wild monster blocks your path!</div>
                <button class="btn-dungeon-primary" onclick="startMonsterBattle()">Start Battle</button>
            </div>
        `;
    }
}

// Render boss room
function renderBossRoom(container, roomData) {
    if (roomData.battle_active) {
        container.innerHTML = `
            <div class="room-event-container">
                <div class="room-event-icon"><img src="/static/Emojis/Crawl/boss.png" style="width:80px;height:80px;object-fit:contain"></div>
                <div class="room-event-description">BOSS BATTLE in progress!</div>
                <button class="btn-dungeon-primary" onclick="openBattle()">Join Battle</button>
            </div>
        `;
    } else if (roomData.completed) {
        container.innerHTML = `
            <div class="room-event-container">
                <div class="room-event-icon">🏆</div>
                <div class="room-event-description">Boss defeated! Floor complete!</div>
            </div>
        `;
    } else {
        container.innerHTML = `
            <div class="room-event-container">
                <div class="room-event-icon"><img src="/static/Emojis/Crawl/boss.png" style="width:80px;height:80px;object-fit:contain"></div>
                <div class="room-event-description">
                    <strong>BOSS ROOM!</strong><br>
                    A powerful enemy awaits!
                </div>
                <button class="btn-dungeon-primary" onclick="startBossBattle()">Fight Boss</button>
            </div>
        `;
    }
}

// Render chest room
function renderChestRoom(container, roomData) {
    // Check if current user has opened
    const chestOpeners = roomData.chest_openers || [];
    const userHasOpened = currentUser && chestOpeners.includes(String(currentUser.id));
    // Pick the correct chest image (chest1–chest4)
    const chestEmoji = roomData.chest_emoji || 'chest1';
    const chestImgSrc = `/static/Emojis/Pets/Equipment/${chestEmoji}.png`;

    if (userHasOpened) {
        container.innerHTML = `
            <div class="room-event-container">
                <div class="room-event-icon">✅</div>
                <div class="room-event-description">You opened this chest! Waiting for party...</div>
                <p class="text-muted">${chestOpeners.length} / ${currentDungeon.party_members.length} opened</p>
            </div>
        `;
    } else if (roomData.completed) {
        container.innerHTML = `
            <div class="room-event-container">
                <div class="room-event-icon">✅</div>
                <div class="room-event-description">All party members opened the chest!</div>
            </div>
        `;
    } else {
        const chestType = roomData.chest_type || 'Chest 1';
        container.innerHTML = `
            <div class="chest-display">
                <div class="chest-icon"><img src="${chestImgSrc}" style="width:100px;height:100px;object-fit:contain" onerror="this.style.display='none'"></div>
                <div class="chest-type">${chestType}</div>
                <div class="room-event-description">Click to open the chest!</div>
                <button class="btn-dungeon-primary" onclick="openChest()">Open Chest</button>
            </div>
        `;
    }
}

// Render trap room
function renderTrapRoom(container, roomData) {
    if (roomData.completed) {
        container.innerHTML = `
            <div class="room-event-container">
                <div class="room-event-icon">✅</div>
                <div class="room-event-description">Trap already triggered</div>
            </div>
        `;
    } else {
        const trap = roomData.trap_data || { name: 'Unknown Trap', emoji: '🪤', effect: 'unknown', value: 0, duration: 0 };
        const effectDesc = _describeTrapEffect(trap);
        const durationDesc = trap.duration ? `Lasts <strong>${trap.duration} room${trap.duration !== 1 ? 's' : ''}</strong>` : '';
        const tf = trap.target_filter;
        let targetDesc = '⚠️ Affects <strong>all party members</strong>';
        if (tf) {
            const targets = tf.values.map(v => v.charAt(0).toUpperCase() + v.slice(1)).join(', ');
            const mode = tf.mode === 'type' ? 'Type' : 'Element';
            targetDesc = `⚠️ Full effect on <strong>${mode}: ${targets}</strong> pets — 50% splash on others`;
        }
        container.innerHTML = `
            <div class="trap-display">
                <div class="trap-icon"><img src="/static/Emojis/Crawl/trap.png" style="width:60px;height:60px;object-fit:contain"></div>
                <div class="trap-name">${_renderEmoji(trap.emoji, 20)} ${trap.name}</div>
                <div class="trap-effect" style="margin:8px 0;line-height:1.6">
                    ${targetDesc}<br>
                    📉 ${effectDesc}<br>
                    ${durationDesc ? `⏱️ ${durationDesc}` : ''}
                </div>
                <button class="btn-dungeon-primary" onclick="triggerTrap()">Continue (Trigger Trap)</button>
            </div>
        `;
    }
}

// Render shrine room
function renderShrineRoom(container, roomData) {
    if (roomData.completed) {
        container.innerHTML = `
            <div class="room-event-container">
                <div class="room-event-icon">✅</div>
                <div class="room-event-description">Shrine already blessed</div>
            </div>
        `;
    } else {
        const shrine = roomData.shrine_data || { name: 'Unknown Shrine', emoji: '⛩️', effect: 'unknown', value: 0, duration: 0 };
        const effectDesc = _describeShrineEffect(shrine);
        const durationDesc = shrine.duration ? `Lasts <strong>${shrine.duration} room${shrine.duration !== 1 ? 's' : ''}</strong>` : '';
        const tf = shrine.target_filter;
        let targetDesc = '✨ Blesses <strong>all party members</strong>';
        if (tf) {
            const targets = tf.values.map(v => v.charAt(0).toUpperCase() + v.slice(1)).join(', ');
            const mode = tf.mode === 'type' ? 'Type' : 'Element';
            targetDesc = `✨ Only blesses <strong>${mode}: ${targets}</strong> pets`;
        }
        container.innerHTML = `
            <div class="shrine-display">
                <div class="shrine-icon"><img src="/static/Emojis/Crawl/shrine.png" style="width:60px;height:60px;object-fit:contain"></div>
                <div class="shrine-name">${_renderEmoji(shrine.emoji, 20)} ${shrine.name}</div>
                <div class="shrine-effect" style="margin:8px 0;line-height:1.6">
                    ${targetDesc}<br>
                    📈 ${effectDesc}<br>
                    ${durationDesc ? `⏱️ ${durationDesc}` : ''}
                </div>
                <button class="btn-dungeon-primary" onclick="activateShrine()">Receive Blessing</button>
            </div>
        `;
    }
}

// Render an emoji field — if it's a static path (/static/...) render as <img>, else as text
function _renderEmoji(emoji, size) {
    size = size || 18;
    if (!emoji) return '';
    if (emoji.startsWith('/')) {
        return `<img src="${_escHtml(emoji)}" style="width:${size}px;height:${size}px;object-fit:contain;vertical-align:middle" onerror="this.style.display='none'">`;
    }
    return emoji;
}
function _describeTrapEffect(trap) {
    const pct = trap.value ? Math.round(trap.value * 100) : 0;
    switch (trap.effect) {
        case 'att_reduction':  return `Reduces <strong>ATT (Attack)</strong> by <strong>${pct}%</strong>`;
        case 'def_reduction':  return `Reduces <strong>DEF (Defense)</strong> by <strong>${pct}%</strong>`;
        case 'dex_reduction':  return `Reduces <strong>DEX (Dexterity)</strong> by <strong>${pct}%</strong>`;
        case 'int_reduction':  return `Reduces <strong>INT (Intelligence)</strong> by <strong>${pct}%</strong>`;
        case 'health_half':    return `Reduces current <strong>HP</strong> by <strong>${pct}%</strong>`;
        case 'no_defend':      return `<strong>Cannot Defend</strong> — forced to attack each turn`;
        default:               return `Unknown effect: ${trap.effect}`;
    }
}

// Human-readable shrine effect descriptions
function _describeShrineEffect(shrine) {
    const pct = shrine.value ? Math.round(shrine.value * 100) : 0;
    switch (shrine.effect) {
        case 'att_boost':    return `Boosts <strong>ATT (Attack)</strong> by <strong>${pct}%</strong>`;
        case 'def_boost':    return `Boosts <strong>DEF (Defense)</strong> by <strong>${pct}%</strong>`;
        case 'dex_boost':    return `Boosts <strong>DEX (Dexterity)</strong> by <strong>${pct}%</strong>`;
        case 'int_boost':    return `Boosts <strong>INT (Intelligence)</strong> by <strong>${pct}%</strong>`;
        case 'health_boost': return `Restores <strong>HP</strong> by <strong>${pct}%</strong> of max`;
        case 'charge_boost': return `Grants <strong>+${shrine.value || 0} Charge</strong> immediately`;
        default:             return `Unknown effect: ${shrine.effect}`;
    }
}

// Update continue button
function updateContinueButton() {
    const continueBtn = document.getElementById('continue-btn');
    const readyStatus = document.getElementById('ready-status');
    const roomData = currentDungeon.current_room_data;
    
    if (!roomData || !roomData.completed) {
        continueBtn.disabled = true;
        readyStatus.textContent = 'Complete the room event first';
        return;
    }
    
    const readyUsers = currentDungeon.ready_users || [];
    const isReady = currentUser && readyUsers.includes(String(currentUser.id));
    
    if (isReady) {
        continueBtn.disabled = true;
        readyStatus.textContent = 'Waiting for other party members...';
    } else {
        continueBtn.disabled = false;
        readyStatus.textContent = 'Click to continue';
    }
}

// Mark user as ready
async function markReady() {
    try {
        const response = await fetch(`/api/dungeon/${currentDungeon.dungeon_id}/ready`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            throw new Error('Failed to mark ready');
        }
        
        // Reload dungeon state
        await loadDungeon(currentDungeon.dungeon_id);
    } catch (error) {
        console.error('Error marking ready:', error);
        alert('Failed to mark ready. Please try again.');
    }
}

// Start monster battle
async function startMonsterBattle() {
    try {
        const response = await fetch(`/api/dungeon/${currentDungeon.dungeon_id}/battle/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_boss: false })
        });
        
        if (!response.ok) {
            throw new Error('Failed to start battle');
        }
        
        const data = await response.json();
        openBattle(data);
    } catch (error) {
        console.error('Error starting battle:', error);
        alert('Failed to start battle. Please try again.');
    }
}

// Start boss battle
async function startBossBattle() {
    try {
        const response = await fetch(`/api/dungeon/${currentDungeon.dungeon_id}/battle/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_boss: true })
        });
        
        if (!response.ok) {
            throw new Error('Failed to start battle');
        }
        
        const data = await response.json();
        openBattle(data);
    } catch (error) {
        console.error('Error starting battle:', error);
        alert('Failed to start battle. Please try again.');
    }
}

// Open battle modal with real battle UI
let currentBattle = null;

function openBattle(battleData) {
    currentBattle = battleData;

    renderBattleUI(battleData);

    // Clean up any stale backdrops before showing
    document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
    document.body.classList.remove('modal-open');
    document.body.style.removeProperty('overflow');
    document.body.style.removeProperty('padding-right');

    const modal = new bootstrap.Modal(document.getElementById('battleModal'), {
        backdrop: false,
        keyboard: false
    });
    modal.show();
}

function _buildSkillButton(member) {
    if (!member || !member.pet) return '';
    const skills = member.pet.equipped_skills || [];
    if (!skills.length) return '';

    // Render one button per equipped skill slot
    return skills.map((skill, slotIdx) => {
        if (!skill) return '';
        const skillName = skill.name || 'Skill';
        const skillDesc = skill.description || '';
        // Initial cooldown from pet data (slot 0 legacy key, or 0 for others)
        const cooldown = slotIdx === 0 ? (member.pet.skill_cooldown || 0) : 0;
        const onCd = cooldown > 0;
        return `<button class="btn-battle-action btn-skill${onCd ? ' btn-skill-cd' : ''}"
                        id="btn-skill-${slotIdx}"
                        data-slot="${slotIdx}"
                        onclick="submitBattleAction('skill', ${slotIdx})"
                        ${onCd ? 'disabled' : ''}
                        title="${_escHtml(skillDesc)}">
            ✨ ${_escHtml(skillName)}<span style="display:block;font-size:0.6rem;opacity:0.75;font-family:sans-serif;font-weight:400">${onCd ? `(${cooldown})` : 'Ready'}</span>
        </button>`;
    }).join('');
}

function renderBattleUI(battleData) {
    const battleContent = document.getElementById('battle-content');
    const monster = battleData.monster;
    const party   = battleData.party;

    // Action labels from the current user's party member
    const myMember = party.find(m => currentUser && m.user_id === String(currentUser.id)) || party[0];
    const labels   = (myMember && myMember.pet && myMember.pet.action_labels) || {};
    const atkLabel = labels.attack || 'Attack';
    const defLabel = labels.defend || 'Defend';
    const chgLabel = labels.charge || 'Charge';

    // Monster image:
    // - Boss: uses pet species → /static/Emojis/Pets/{species}.png
    // - Regular monster: uses emoji_file → /static/Emojis/Pets/Equipment/{emoji_file}
    let monsterImgSrc, monsterFallback;
    if (monster.is_boss && monster.species) {
        monsterImgSrc  = `/static/Emojis/Pets/${monster.species}.png`;
        monsterFallback = '/static/Emojis/Crawl/boss.png';
    } else if (!monster.is_boss && monster.emoji_file) {
        monsterImgSrc  = `/static/Emojis/Pets/Equipment/${monster.emoji_file}`;
        monsterFallback = '/static/Emojis/Crawl/enemy.png';
    } else {
        monsterImgSrc  = monster.is_boss ? '/static/Emojis/Crawl/boss.png' : '/static/Emojis/Crawl/enemy.png';
        monsterFallback = monsterImgSrc;
    }

    // Element color helper
    const ELEM_COLORS = {fire:'#e74c3c',water:'#3498db',electric:'#f1c40f',ice:'#a8d8ea',plant:'#2ecc71',rock:'#95a5a6',air:'#bdc3c7',magic:'#9b59b6',holy:'#f9ca24',necro:'#6c5ce7',psychic:'#fd79a8',fighting:'#e17055',basic:'#ffd700'};
    const elemColor = e => ELEM_COLORS[(e||'basic').toLowerCase()] || '#ffd700';

    // Equipment bar builder (matches arena style)
    function buildEquipBar(items) {
        if (!items || !items.length) return '';
        const RARITY_GLOW = {Common:'rgba(158,158,158,0.55)',Uncommon:'rgba(76,175,80,0.65)',Rare:'rgba(33,150,243,0.65)',Epic:'rgba(156,39,176,0.7)',Mythic:'rgba(255,152,0,0.75)'};
        const imgs = items.map(item => {
            const f    = item.emoji_file || (item.name.replace(/ /g,'') + '.png');
            const glow = RARITY_GLOW[item.rarity] || RARITY_GLOW.Common;
            return `<img src="/static/Emojis/Pets/Equipment/${_escHtml(f)}" title="${_escHtml(item.name)}" style="width:20px;height:20px;object-fit:contain;filter:drop-shadow(0 0 3px ${glow})" onerror="this.style.display='none'">`;
        }).join('');
        return `<div style="display:flex;gap:3px;justify-content:center;flex-wrap:wrap;margin-top:4px">${imgs}</div>`;
    }

    battleContent.innerHTML = `
        <div class="battle-arena" style="padding:16px">
            <!-- Monster Section -->
            <div class="battle-monster-section">
                <div style="display:flex;align-items:center;justify-content:center;gap:10px;margin-bottom:8px">
                    <img src="${monsterImgSrc}" style="width:48px;height:48px;object-fit:contain;filter:drop-shadow(0 0 8px rgba(244,67,54,0.7))" onerror="this.src='${monsterFallback}'">
                    <div>
                        <h4 style="margin:0;font-size:1rem">${monster.is_boss ? '👹' : '⚔️'} ${_escHtml(monster.name)}</h4>
                        <div style="font-size:0.7rem;color:var(--text-secondary)">${_escHtml(monster.element||'')} · ${_escHtml(monster.type||'')} · Lv ${monster.level||1}</div>
                    </div>
                </div>
                <div class="battle-health-bar">
                    <div class="health-bar-fill" id="monster-health-bar" style="width:100%"></div>
                </div>
                <p class="battle-health-text" style="font-size:0.85rem">
                    <span id="monster-health">${monster.health}</span> / ${monster.max_health} HP
                </p>
                <div class="battle-stats-mini">
                    <span>⚔️ ${monster.attack}</span>
                    <span>🛡️ ${monster.defense}</span>
                </div>
            </div>

            <!-- Battle Log -->
            <div class="battle-log" id="battle-log">
                <p class="text-muted" style="font-size:0.8rem">Battle started! Choose your action.</p>
            </div>

            <!-- Party Section -->
            <div class="battle-party-section">
                <h5>Your Party</h5>
                <div id="battle-party-list">
                    ${party.map(member => {
                        const petImgSrc = member.pet.species
                            ? `/static/Emojis/Pets/${member.pet.species}.png`
                            : '/static/Emojis/Pets/Deco/Basic.png';
                        const e1 = (member.pet.element||'basic').toLowerCase();
                        const e2 = (member.pet.element2||'').toLowerCase();
                        const c1 = elemColor(e1), c2 = elemColor(e2||e1);
                        return `
                        <div class="battle-party-member" data-user-id="${member.user_id}">
                            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
                                <div style="position:relative;width:36px;height:36px;flex-shrink:0">
                                    <div class="arena-charge-ring" id="charge-ring-${member.user_id}" style="--charge-c1:${c1};--charge-c2:${c2}"></div>
                                    <img src="${petImgSrc}" style="width:32px;height:32px;object-fit:contain;position:absolute;top:2px;left:2px" onerror="this.src='/static/Emojis/Pets/Deco/Basic.png'">
                                </div>
                                <div>
                                    <div class="party-member-name" style="font-size:0.8rem">${_escHtml(member.pet.name)} (Lv ${member.pet.level})</div>
                                    <div style="font-size:0.65rem;color:var(--text-secondary)">⚔️ ${member.pet.attack} · 🛡️ ${member.pet.defense}</div>
                                </div>
                            </div>
                            <div class="battle-health-bar-small">
                                <div class="health-bar-fill" style="width:100%;background:#2ecc71"></div>
                            </div>
                            <p class="battle-health-text-small">${member.pet.health} / ${member.pet.max_health} HP</p>
                            ${buildEquipBar(member.pet.equipment || [])}
                            ${member.buffs && member.buffs.length > 0 ? `
                                <div class="battle-buffs">
                                    ${member.buffs.map(b => `<span title="${_escHtml(b.name)}">${_renderEmoji(b.emoji, 16)}</span>`).join('')}
                                </div>
                            ` : ''}
                        </div>`;
                    }).join('')}
                </div>
            </div>

            <!-- Action Buttons with custom labels -->
            <div class="battle-actions" id="battle-actions">
                <button class="btn-battle-action" id="btn-attack" onclick="submitBattleAction('attack')">
                    ⚔️ Attack<span style="display:block;font-size:0.6rem;opacity:0.75;font-family:sans-serif;font-weight:400">${_escHtml(atkLabel)}</span>
                </button>
                <button class="btn-battle-action" id="btn-defend" onclick="submitBattleAction('defend')">
                    🛡️ Defend<span style="display:block;font-size:0.6rem;opacity:0.75;font-family:sans-serif;font-weight:400">${_escHtml(defLabel)}</span>
                </button>
                <button class="btn-battle-action" id="btn-charge" onclick="submitBattleAction('charge')">
                    ⚡ Charge<span style="display:block;font-size:0.6rem;opacity:0.75;font-family:sans-serif;font-weight:400">${_escHtml(chgLabel)}</span>
                </button>
                ${_buildSkillButton(myMember)}
            </div>

            <p class="text-center text-muted mt-2" id="battle-status" style="font-size:0.8rem">Waiting for your action...</p>
        </div>
    `;
}

async function submitBattleAction(action, slotIndex) {
    if (!currentBattle || !currentUser) return;
    
    try {
        // Disable all action buttons
        document.querySelectorAll('.btn-battle-action').forEach(btn => btn.disabled = true);
        document.getElementById('battle-status').textContent = 'Action submitted! Waiting for party...';
        
        // Build the request body — include slot_index for skill actions
        const body = {
            battle_id: currentBattle.battle_id,
            action: action,
            user_id: String(currentUser.id)
        };
        if (action === 'skill' && slotIndex !== undefined) {
            body.slot_index = slotIndex;
        }
        
        const response = await fetch(`/api/dungeon/${currentDungeon.dungeon_id}/battle/action`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        
        if (!response.ok) {
            throw new Error('Failed to submit action');
        }
        
        const data = await response.json();
        
        if (data.waiting) {
            document.getElementById('battle-status').textContent = 
                `Waiting for party... (${data.actions_received}/${data.actions_needed})`;
            
            // Poll for turn result using status endpoint
            pollBattleTurn();
        } else if (data.turn_result) {
            processTurnResult(data.turn_result);
        }
        
    } catch (error) {
        console.error('Error submitting action:', error);
        alert('Failed to submit action. Please try again.');
        document.querySelectorAll('.btn-battle-action').forEach(btn => btn.disabled = false);
    }
}

let battlePollInterval = null;

function pollBattleTurn() {
    if (battlePollInterval) return;

    battlePollInterval = setInterval(async () => {
        try {
            const response = await fetch(
                `/api/dungeon/${currentDungeon.dungeon_id}/battle/${currentBattle.battle_id}/status`
            );

            if (response.ok) {
                const data = await response.json();

                // Turn resolved — the action endpoint already processed it and stored
                // the result. Re-fetch the full turn result via the action endpoint
                // by checking if the turn counter advanced.
                if (!data.waiting) {
                    clearInterval(battlePollInterval);
                    battlePollInterval = null;

                    // Fetch the latest turn result from the battle status
                    // The status endpoint now returns turn_result when resolved
                    if (data.turn_result) {
                        processTurnResult(data.turn_result);
                    } else {
                        // Fallback: just re-enable buttons so player can act again
                        document.querySelectorAll('.btn-battle-action').forEach(btn => btn.disabled = false);
                        document.getElementById('battle-status').textContent = 'Choose your next action...';
                    }
                }
            }
        } catch (error) {
            console.error('Battle poll error:', error);
        }
    }, 2000);
}

function processTurnResult(result) {
    // Update battle log
    const battleLog = document.getElementById('battle-log');
    const logEntries = result.turn_log.map(entry => {
        if (entry.action === 'attack' && entry.target) {
            let msg = `<p>${_escHtml(entry.actor)} attacked ${_escHtml(entry.target)} for <strong>${entry.damage}</strong> damage!`;
            if (entry.is_critical) {
                msg += ` <span class="text-warning">CRITICAL HIT!</span>`;
            }
            if (entry.charge_used && entry.charge_multiplier) {
                msg += ` <span class="text-info">(Charged ×${entry.charge_multiplier.toFixed(1)})</span>`;
            }
            msg += `</p>`;
            return msg;
        } else if (entry.action === 'defend') {
            return `<p style="color:#3498db">🛡️ ${_escHtml(entry.message || entry.actor + ' defends!')}</p>`;
        } else if (entry.action === 'charge') {
            return `<p style="color:#9b59b6">⚡ ${_escHtml(entry.message || entry.actor + ' charges up!')}</p>`;
        } else if (entry.message) {
            return `<p style="color:var(--text-secondary)">${_escHtml(entry.message)}</p>`;
        }
        return '';
    }).join('');

    battleLog.innerHTML += logEntries;
    battleLog.scrollTop = battleLog.scrollHeight;

    // Update monster health bar
    const monsterHealth = result.monster_health;
    const monsterHealthEl = document.getElementById('monster-health');
    const monsterHealthBar = document.getElementById('monster-health-bar');
    if (monsterHealthEl) monsterHealthEl.textContent = Math.max(0, monsterHealth);
    if (monsterHealthBar && currentBattle) {
        const pct = Math.max(0, (monsterHealth / currentBattle.monster.max_health) * 100);
        monsterHealthBar.style.width = `${pct}%`;
        // Color shift as health drops
        monsterHealthBar.style.background = pct > 50
            ? 'linear-gradient(90deg,#e74c3c,#c0392b)'
            : pct > 25
                ? 'linear-gradient(90deg,#f39c12,#e74c3c)'
                : '#95a5a6';
    }

    // Update party health
    if (result.party_health) {
        for (const userId in result.party_health) {
            const health = result.party_health[userId];
            const memberEl = document.querySelector(`[data-user-id="${userId}"]`);
            if (memberEl && currentBattle) {
                const member = currentBattle.party.find(m => m.user_id === userId);
                if (member) {
                    const healthBar = memberEl.querySelector('.health-bar-fill');
                    const healthText = memberEl.querySelector('.battle-health-text-small');
                    const pct = Math.max(0, (health / member.pet.max_health) * 100);
                    if (healthBar) {
                        healthBar.style.width = `${pct}%`;
                        healthBar.style.background = pct > 50 ? '#2ecc71' : pct > 25 ? '#f39c12' : '#e74c3c';
                    }
                    if (healthText) healthText.textContent = `${Math.max(0, health)} / ${member.pet.max_health} HP`;
                }
            }
        }
    }

    // Update charge displays and rings
    if (result.party_charges) {
        for (const userId in result.party_charges) {
            const charge = result.party_charges[userId];
            const memberEl = document.querySelector(`[data-user-id="${userId}"]`);
            if (memberEl) {
                let chargeDisplay = memberEl.querySelector('.charge-display');
                if (!chargeDisplay) {
                    chargeDisplay = document.createElement('div');
                    chargeDisplay.className = 'charge-display';
                    chargeDisplay.style.cssText = 'font-size:0.65rem;color:#9b59b6;margin-top:2px';
                    memberEl.appendChild(chargeDisplay);
                }
                // charge > 1.0 means the player has built up charge via the Charge action
                chargeDisplay.textContent = charge > 1.0 ? `⚡ ×${charge.toFixed(0)} Charge ready` : '';
            }
            // Update charge ring level (charge value = ring level)
            const ring = document.getElementById(`charge-ring-${userId}`);
            if (ring) {
                ring.classList.remove('charge-1','charge-2','charge-3','charge-4','charge-5');
                const lvl = Math.round(charge);
                if (lvl >= 2) ring.classList.add('charge-' + Math.min(5, lvl));
            }
        }
    }

    // Battle over?
    if (result.battle_over) {
        if (result.victory) {
            battleLog.innerHTML += '<p class="text-success"><strong>🎉 Victory! The monster has been defeated!</strong></p>';
            completeBattleVictory();
        } else {
            battleLog.innerHTML += '<p class="text-danger"><strong>💀 Defeat! Your party has been defeated...</strong></p>';
            document.getElementById('battle-actions').innerHTML =
                '<button class="btn-dungeon-secondary" onclick="closeBattleModal()">Return to Dungeon</button>';
        }
    } else {
        document.querySelectorAll('.btn-battle-action').forEach(btn => btn.disabled = false);
        document.getElementById('battle-status').textContent = 'Choose your next action...';
        // Update skill button cooldowns from turn result (all slots)
        if (result.skill_cooldowns && currentUser) {
            const mySlots = result.skill_cooldowns[String(currentUser.id)] || {};
            const myMember = currentBattle && currentBattle.party
                ? currentBattle.party.find(m => m.user_id === String(currentUser.id))
                : null;
            const mySkills = (myMember && myMember.pet && myMember.pet.equipped_skills) || [];
            mySkills.forEach((skill, slotIdx) => {
                const skillBtn = document.getElementById(`btn-skill-${slotIdx}`);
                if (!skillBtn) return;
                // mySlots is {slot_str: cooldown_int}
                const cd = typeof mySlots === 'object' && !Array.isArray(mySlots)
                    ? (mySlots[String(slotIdx)] || 0)
                    : (slotIdx === 0 ? (mySlots || 0) : 0);  // backwards compat
                const skillName = skill ? skill.name : 'Skill';
                skillBtn.disabled = cd > 0;
                skillBtn.classList.toggle('btn-skill-cd', cd > 0);
                const sub = skillBtn.querySelector('span');
                if (sub) sub.textContent = cd > 0 ? `(${cd})` : 'Ready';
            });
        }
    }
}

async function completeBattleVictory() {
    try {
        const response = await fetch(`/api/dungeon/${currentDungeon.dungeon_id}/battle/complete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                victory: true,
                monster_name: currentBattle.monster.equipment_name,
                is_boss: currentBattle.monster.is_boss
            })
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to complete battle');
        }

        const data = await response.json();
        const myLoot = (data.loot && data.loot[String(currentUser.id)]) || [];

        // Build loot display in battle log
        const battleLog = document.getElementById('battle-log');
        if (myLoot.length > 0) {
            battleLog.innerHTML += '<p class="text-warning"><strong>💰 Loot Received!</strong></p>';
            myLoot.forEach(item => {
                const imgSrc = _dungeonItemImgSrc(item);
                const rarityColor = _dungeonRarityColor(item.rarity || 'Common');
                battleLog.innerHTML += `<p style="display:flex;align-items:center;gap:6px">
                    <img src="${imgSrc}" style="width:20px;height:20px;object-fit:contain;filter:drop-shadow(0 0 4px ${rarityColor})" onerror="this.style.display='none'">
                    <span style="color:${rarityColor}">${_escHtml(item.name)}</span> ×${item.count || 1}
                </p>`;
            });
        } else {
            battleLog.innerHTML += '<p class="text-muted">No loot this time.</p>';
        }
        battleLog.scrollTop = battleLog.scrollHeight;

        // Replace action buttons with continue button
        document.getElementById('battle-actions').innerHTML =
            '<button class="btn-dungeon-primary" onclick="closeBattleModal()">Continue Dungeon</button>';

    } catch (error) {
        console.error('Error completing battle:', error);
        // Still let player close the modal even if loot failed
        document.getElementById('battle-actions').innerHTML =
            '<button class="btn-dungeon-primary" onclick="closeBattleModal()">Continue Dungeon</button>';
    }
}

function closeBattleModal() {
    const modal = bootstrap.Modal.getInstance(document.getElementById('battleModal'));
    if (modal) {
        modal.hide();
    }
    // Clean up any stale backdrops
    document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
    document.body.classList.remove('modal-open');
    document.body.style.removeProperty('overflow');
    document.body.style.removeProperty('padding-right');

    currentBattle = null;
    if (battlePollInterval) {
        clearInterval(battlePollInterval);
        battlePollInterval = null;
    }
    loadDungeon(currentDungeon.dungeon_id);
}

// ── Chest animation (ported from mypet.js) ───────────────────────────────────

function _dungeonEquipImgFile(item) {
    if (item && item.emoji_file) return item.emoji_file;
    var name = (item && item.name) ? item.name : (typeof item === 'string' ? item : '');
    // Try exact name match first (Equipment filenames match item names with spaces removed)
    return name.replace(/ /g, '') + '.png';
}

// Resolve the full static image URL for any inventory item (keys, chests, monsters, gems, etc.)
function _dungeonItemImgSrc(item) {
    if (!item) return '/static/Emojis/Pets/Deco/Basic.png';
    const name = (item.name || '').trim();
    const type = (item.type || '').toLowerCase();
    const nameLower = name.toLowerCase();

    // Keys and Chests live in Equipment root
    if (type === 'key' || ['key1','key2','key3'].includes(nameLower)) {
        return `/static/Emojis/Pets/Equipment/${name}.png`;
    }
    if (type === 'chest' || ['chest1','chest2','chest3','chest4'].includes(nameLower)) {
        return `/static/Emojis/Pets/Equipment/${nameLower}.png`;
    }
    // Monsters
    if (type === 'monster') {
        return `/static/Emojis/Pets/Equipment/Monsters/${name.replace(/ /g,'')}.png`;
    }
    // Gems
    if (type === 'gem') {
        return `/static/Emojis/Pets/Equipment/Gems/${name.replace(/ /g,'')}.png`;
    }
    // Materials
    if (type === 'material') {
        return `/static/Emojis/Pets/Equipment/Materials/${name.replace(/ /g,'')}.png`;
    }
    // Potions
    if (type === 'potion') {
        const stem = name.toLowerCase().replace(/ /g,'_');
        return `/static/Emojis/Pets/Equipment/Potions/${stem}.png`;
    }
    // Hats
    if (type === 'hat') {
        const stem = name.toLowerCase().replace(/ /g,'_');
        return `/static/Emojis/Pets/Equipment/Hats/${stem}.png`;
    }
    // Fallback: try Equipment root with name
    return `/static/Emojis/Pets/Equipment/${name.replace(/ /g,'')}.png`;
}

const _DUNGEON_RARITY_COLORS = {
    Common:   '#9e9e9e',
    Uncommon: '#4caf50',
    Rare:     '#2196f3',
    Epic:     '#9c27b0',
    Mythic:   '#ff9800'
};
function _dungeonRarityColor(rarity) {
    return _DUNGEON_RARITY_COLORS[rarity] || '#9e9e9e';
}

function _escHtml(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function _showDungeonChestAnimation(chestSrc, chestColor, items, callback) {
    // Inject keyframes once globally
    if (!document.getElementById('chest-anim-style')) {
        var s = document.createElement('style');
        s.id = 'chest-anim-style';
        s.textContent =
            '@keyframes chestZoomIn{0%{transform:scale(0.6);opacity:0}40%{transform:scale(1.12);opacity:1}70%{transform:scale(0.97)}100%{transform:scale(1);opacity:1}}' +
            '@keyframes chestFadeOut{0%{transform:scale(1);opacity:1}100%{transform:scale(1.3);opacity:0}}' +
            '@keyframes itemsReveal{0%{opacity:0;transform:scale(0.5) translateY(20px)}60%{transform:scale(1.08) translateY(-4px)}100%{opacity:1;transform:scale(1) translateY(0)}}' +
            '@keyframes shimmer{0%,100%{box-shadow:0 0 20px rgba(255,215,0,0.3)}50%{box-shadow:0 0 50px rgba(255,215,0,0.9),0 0 80px rgba(255,215,0,0.4)}}';
        document.head.appendChild(s);
    }

    var overlay = document.createElement('div');
    overlay.id = 'chest-anim-overlay';
    overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:10500;' +
        'display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.82);backdrop-filter:blur(6px)';

    var itemIconsHtml = items.map(function(item, idx) {
        var imgSrc = _dungeonItemImgSrc(item);
        var rc = _dungeonRarityColor(item.rarity || 'Common');
        return '<div style="text-align:center;animation:itemsReveal 0.5s ease forwards;animation-delay:' + (idx * 0.12) + 's;opacity:0">' +
            '<img src="' + imgSrc + '" style="width:56px;height:56px;object-fit:contain;filter:drop-shadow(0 0 10px ' + rc + ')" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">' +
            '<div style="font-size:0.65rem;color:' + rc + ';margin-top:4px;max-width:64px;word-break:break-word;font-weight:600">' + _escHtml(item.name) + '</div>' +
            '<div style="font-size:0.58rem;color:rgba(255,255,255,0.45);margin-top:1px">' + (item.rarity || 'Common') + '</div>' +
            '</div>';
    }).join('');

    overlay.innerHTML =
        '<div style="text-align:center;max-width:420px;padding:24px">' +
        '<div id="chest-phase1">' +
        '<img id="chest-anim-img" src="' + chestSrc + '" style="width:96px;height:96px;object-fit:contain;animation:chestZoomIn 0.6s ease forwards;filter:drop-shadow(0 0 24px ' + chestColor + ')" onerror="this.src=\'/static/Emojis/Pets/Deco/Basic.png\'">' +
        '<div style="font-size:0.9rem;color:' + chestColor + ';font-family:Orbitron,sans-serif;margin-top:10px;animation:shimmer 1s ease infinite">Opening...</div>' +
        '</div>' +
        '<div id="chest-phase2" style="display:none">' +
        '<div style="font-size:1rem;color:var(--gold-primary);font-family:Orbitron,sans-serif;margin-bottom:14px">✨ You got!</div>' +
        '<div style="display:flex;flex-wrap:wrap;gap:12px;justify-content:center">' + itemIconsHtml + '</div>' +
        '<div style="font-size:0.75rem;color:var(--text-secondary);margin-top:14px">Click anywhere to continue</div>' +
        '</div>' +
        '</div>';

    document.body.appendChild(overlay);

    // Phase 1 → Phase 2 transition
    setTimeout(function() {
        var chestImg = document.getElementById('chest-anim-img');
        var phase1   = document.getElementById('chest-phase1');
        var phase2   = document.getElementById('chest-phase2');
        if (chestImg) chestImg.style.animation = 'chestFadeOut 0.4s ease forwards';
        setTimeout(function() {
            if (phase1) phase1.style.display = 'none';
            if (phase2) phase2.style.display = '';
        }, 380);
    }, 1200);

    function dismiss() {
        var el = document.getElementById('chest-anim-overlay');
        if (el) { el.remove(); callback(); }
    }

    overlay.addEventListener('click', dismiss);
    setTimeout(dismiss, 5000); // auto-dismiss after 5s
}

// Open chest
async function openChest() {
    try {
        const response = await fetch(`/api/dungeon/${currentDungeon.dungeon_id}/chest/open`, {
            method: 'POST'
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to open chest');
        }

        const data = await response.json();
        const loot = data.loot || [];

        // Determine chest image + color from current room data
        const roomData = currentDungeon.current_room_data || {};
        const chestEmoji = roomData.chest_emoji || 'chest1';
        const chestSrc   = `/static/Emojis/Pets/Equipment/${chestEmoji}.png`;
        const CHEST_COLORS = { chest1:'#9e9e9e', chest2:'#4caf50', chest3:'#2196f3', chest4:'#ff9800' };
        const chestColor = CHEST_COLORS[chestEmoji] || '#ffd700';

        _showDungeonChestAnimation(chestSrc, chestColor, loot, async function() {
            // Reload dungeon state after animation dismisses
            await loadDungeon(currentDungeon.dungeon_id);
        });

    } catch (error) {
        console.error('Error opening chest:', error);
        alert('Failed to open chest: ' + error.message);
    }
}

// Trigger trap
async function triggerTrap() {
    try {
        const response = await fetch(`/api/dungeon/${currentDungeon.dungeon_id}/trap/trigger`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            throw new Error('Failed to trigger trap');
        }
        
        await loadDungeon(currentDungeon.dungeon_id);
    } catch (error) {
        console.error('Error triggering trap:', error);
        alert('Failed to trigger trap. Please try again.');
    }
}

// Activate shrine
async function activateShrine() {
    try {
        const response = await fetch(`/api/dungeon/${currentDungeon.dungeon_id}/shrine/activate`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            throw new Error('Failed to activate shrine');
        }
        
        await loadDungeon(currentDungeon.dungeon_id);
    } catch (error) {
        console.error('Error activating shrine:', error);
        alert('Failed to activate shrine. Please try again.');
    }
}

// Polling for updates
let pollErrorCount = 0;
const MAX_POLL_ERRORS = 5;

function startPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
    }
    
    pollErrorCount = 0;
    
    pollInterval = setInterval(async () => {
        if (currentDungeon) {
            try {
                const response = await fetch(`/api/dungeon/${currentDungeon.dungeon_id}`);
                if (response.ok) {
                    currentDungeon = await response.json();
                    renderDungeon();
                    pollErrorCount = 0; // Reset on success
                } else if (response.status === 404) {
                    console.error('Dungeon not found, stopping polling');
                    stopPolling();
                    alert('Dungeon no longer exists. Returning to lobby.');
                    showLobby();
                } else {
                    pollErrorCount++;
                    if (pollErrorCount >= MAX_POLL_ERRORS) {
                        console.error('Too many polling errors, stopping');
                        stopPolling();
                    }
                }
            } catch (error) {
                console.error('Polling error:', error);
                pollErrorCount++;
                if (pollErrorCount >= MAX_POLL_ERRORS) {
                    console.error('Too many polling errors, stopping');
                    stopPolling();
                    alert('Lost connection to dungeon. Please refresh.');
                }
            }
        }
    }, 3000); // Poll every 3 seconds
}

function stopPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
}

// UI State Management
function showLobby() {
    document.getElementById('dungeon-lobby').style.display = 'block';
    document.getElementById('dungeon-active').style.display = 'none';
    document.getElementById('dungeon-loading').style.display = 'none';
    stopPolling();
}

function showDungeon() {
    document.getElementById('dungeon-lobby').style.display = 'none';
    document.getElementById('dungeon-active').style.display = 'block';
    document.getElementById('dungeon-loading').style.display = 'none';
}

function showLoading() {
    document.getElementById('dungeon-lobby').style.display = 'none';
    document.getElementById('dungeon-active').style.display = 'none';
    document.getElementById('dungeon-loading').style.display = 'block';
}

    // Expose functions to global scope for onclick handlers
    window.loadDungeon = loadDungeon;
    window.removePartyInviteInput = removePartyInviteInput;
    window.openBattle = openBattle;
    window.startMonsterBattle = startMonsterBattle;
    window.startBossBattle = startBossBattle;
    window.submitBattleAction = submitBattleAction;
    window.openChest = openChest;
    window.triggerTrap = triggerTrap;
    window.activateShrine = activateShrine;
    window.completeBattleVictory = completeBattleVictory;
    window.closeBattleModal = closeBattleModal;
    window.startPolling = startPolling;
    window.stopPolling = stopPolling;
    window.showLobby = showLobby;
    window.showDungeon = showDungeon;
    window.showLoading = showLoading;

// Start initialization — DOM is already ready when this script is injected
initializeDungeon();

})(); // end IIFE

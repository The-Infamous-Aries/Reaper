// Dungeon Crawl JavaScript
(function () {
'use strict';

console.log('[dungeon.js] Script loaded!');

let currentDungeon = null;
let currentUser = null;
let pollInterval = null;
let cooldownInterval = null;

// Event type emojis (UPDATED with static images from Crawl folder)
const EVENT_EMOJIS = {
    'monster': '<img src="/static/Emojis/Crawl/enemy.png" style="width:24px;height:24px;object-fit:contain;vertical-align:middle">',
    'monster_encounter': '<img src="/static/Emojis/Crawl/enemy.png" style="width:24px;height:24px;object-fit:contain;vertical-align:middle">',
    'story_segment': '<img src="/static/Emojis/Crawl/story.png" style="width:24px;height:24px;object-fit:contain;vertical-align:middle">',
    'puzzle': '<img src="/static/Emojis/Crawl/puzzle.png" style="width:24px;height:24px;object-fit:contain;vertical-align:middle">',
    'merchant': '<img src="/static/Emojis/Crawl/merchant.png" style="width:24px;height:24px;object-fit:contain;vertical-align:middle">',
    'chest_mimic': '📦',  // Will be overridden with actual chest image from room data
    'boss': '<img src="/static/Emojis/Crawl/boss.png" style="width:24px;height:24px;object-fit:contain;vertical-align:middle">',
    'floor_loot': '🎁',  // Will be overridden with actual chest image from room data
    'chest': '📦',
    'chest1': '<img src="/static/Emojis/Pets/Equipment/chest1.png" style="width:24px;height:24px;object-fit:contain;vertical-align:middle">',
    'chest2': '<img src="/static/Emojis/Pets/Equipment/chest2.png" style="width:24px;height:24px;object-fit:contain;vertical-align:middle">',
    'chest3': '<img src="/static/Emojis/Pets/Equipment/chest3.png" style="width:24px;height:24px;object-fit:contain;vertical-align:middle">',
    'chest4': '<img src="/static/Emojis/Pets/Equipment/chest4.png" style="width:24px;height:24px;object-fit:contain;vertical-align:middle">',
    'trap': '<img src="/static/Emojis/Crawl/trap.png" style="width:24px;height:24px;object-fit:contain;vertical-align:middle">',
    'shrine': '<img src="/static/Emojis/Crawl/shrine.png" style="width:24px;height:24px;object-fit:contain;vertical-align:middle">'
};

// Dungeon type emojis from Deco folder
const DUNGEON_TYPE_EMOJIS = {
    'Camp': '/static/Emojis/Pets/Deco/camping.png',
    'Bonfire': '/static/Emojis/Pets/Deco/bonfire.png',
    'Beach': '/static/Emojis/Pets/Deco/beach.png',
    'Forest': '/static/Emojis/Pets/Deco/forest.png',
    'Hot Air Balloon': '/static/Emojis/Pets/Deco/hotairballoon.png',
    'Cruiseship': '/static/Emojis/Pets/Deco/cruiseship.png',
    'Mountain': '/static/Emojis/Pets/Deco/mountain.png',
    'Gym': '/static/Emojis/Pets/Deco/gym.png',
    'Graveyard': '/static/Emojis/Pets/Deco/graveyard.png',
    'Festival': '/static/Emojis/Pets/Deco/festival.png',
    'Glacier': '/static/Emojis/Pets/Deco/glacier.png',
    'Pyramids': '/static/Emojis/Pets/Deco/pyramids.png'
};

// Initialize function
async function initializeDungeon() {
    console.log('[dungeon.js] Initializing...');
    
    await loadCurrentUser();
    await loadActiveDungeons();
    
    // Event listeners (UPDATED - removed party buttons)
    const createSoloBtn = document.getElementById('create-solo-btn');
    const continueBtn = document.getElementById('continue-btn');
    const dungeonTypeSelect = document.getElementById('dungeon-type-select');
    
    if (createSoloBtn) {
        createSoloBtn.addEventListener('click', createSoloDungeon);
    }
    
    if (continueBtn) continueBtn.addEventListener('click', markReady);
    
    // Dungeon type selector - show emoji preview
    if (dungeonTypeSelect) {
        // Show initial selection
        updateDungeonTypeDisplay(dungeonTypeSelect.value);
        
        // Update on change
        dungeonTypeSelect.addEventListener('change', function() {
            updateDungeonTypeDisplay(this.value);
        });
    }
    
    console.log('[dungeon.js] Initialization complete');
}

// Update dungeon type emoji display
function updateDungeonTypeDisplay(dungeonType) {
    const display = document.getElementById('selected-dungeon-type-display');
    const emoji = document.getElementById('selected-dungeon-emoji');
    const name = document.getElementById('selected-dungeon-name');
    
    if (!display || !emoji || !name) return;
    
    const emojiPath = DUNGEON_TYPE_EMOJIS[dungeonType];
    if (emojiPath) {
        emoji.src = emojiPath;
        emoji.alt = dungeonType;
        name.textContent = dungeonType;
        display.style.display = 'block';
    } else {
        display.style.display = 'none';
    }
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

// Create solo dungeon (UPDATED with dungeon type)
async function createSoloDungeon() {
    try {
        showLoading();
        
        // Get selected dungeon type
        const dungeonTypeSelect = document.getElementById('dungeon-type-select');
        const dungeonType = dungeonTypeSelect ? dungeonTypeSelect.value : 'Crypt';
        
        const response = await fetch('/api/dungeon/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                party_members: [],
                dungeon_type: dungeonType
            })
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

// Party functions removed - solo mode only

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

    // Static image paths for each event type (using Crawl folder images)
    const EVENT_IMGS = {
        'monster': '/static/Emojis/Crawl/enemy.png',
        'monster_encounter': '/static/Emojis/Crawl/enemy.png',
        'boss': '/static/Emojis/Crawl/boss.png',
        'trap': '/static/Emojis/Crawl/trap.png',
        'shrine': '/static/Emojis/Crawl/shrine.png',
        'story_segment': '/static/Emojis/Crawl/story.png',
        'puzzle': '/static/Emojis/Crawl/puzzle.png',
        'merchant': '/static/Emojis/Crawl/merchant.png'
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

        // Choose the right image based on event type
        let imgSrc = EVENT_IMGS[room.event_type];
        
        // For ALL chest-related events, use the chest_emoji from room data
        if (room.event_type === 'chest' || room.event_type === 'chest_mimic' || room.event_type === 'floor_loot' ||
            ['chest1','chest2','chest3','chest4'].includes(room.event_type)) {
            const chestEmoji = room.chest_emoji || 'chest1';
            imgSrc = `/static/Emojis/Pets/Equipment/${chestEmoji}.png`;
        }
        
        // Fallback to shrine image if no specific image
        if (!imgSrc) {
            imgSrc = '/static/Emojis/Crawl/shrine.png';
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
    if (!partyContainer) return; // solo mode - no party list element
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

// Render current room (UPDATED with new event types)
function renderCurrentRoom() {
    const roomData = currentDungeon.current_room_data;
    if (!roomData) return;
    
    const eventType = roomData.event_type;
    const roomContent = document.getElementById('room-content');
    const roomTitle = document.getElementById('room-title');
    
    // Get emoji for room title - use chest image for chest events
    let roomEmoji = EVENT_EMOJIS[eventType] || '🚪';
    
    // For chest_mimic, use the actual chest image to disguise the mimic
    if (eventType === 'chest_mimic' && roomData.chest_emoji) {
        roomEmoji = `<img src="/static/Emojis/Pets/Equipment/${roomData.chest_emoji}.png" style="width:24px;height:24px;object-fit:contain;vertical-align:middle">`;
    }
    // For floor_loot, use the actual chest tier image
    else if (eventType === 'floor_loot' && roomData.chest_emoji) {
        roomEmoji = `<img src="/static/Emojis/Pets/Equipment/${roomData.chest_emoji}.png" style="width:24px;height:24px;object-fit:contain;vertical-align:middle">`;
    }
    // For regular chests, use their specific chest image
    else if (['chest', 'chest1', 'chest2', 'chest3', 'chest4'].includes(eventType) && roomData.chest_emoji) {
        roomEmoji = `<img src="/static/Emojis/Pets/Equipment/${roomData.chest_emoji}.png" style="width:24px;height:24px;object-fit:contain;vertical-align:middle">`;
    }
    
    roomTitle.innerHTML = `${roomEmoji} Room ${currentDungeon.current_room}`;
    
    switch (eventType) {
        case 'monster_encounter':
            renderMonsterEncounterRoom(roomContent, roomData);
            break;
        case 'story_segment':
            renderStorySegmentRoom(roomContent, roomData);
            break;
        case 'puzzle':
            renderPuzzleRoom(roomContent, roomData);
            break;
        case 'merchant':
            renderMerchantRoom(roomContent, roomData);
            break;
        case 'chest_mimic':
            renderChestMimicRoom(roomContent, roomData);
            break;
        case 'boss':
            renderBossRoom(roomContent, roomData);
            break;
        case 'floor_loot':
            renderFloorLootRoom(roomContent, roomData);
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
        // LEGACY SUPPORT: Old monster event (redirect to new handler)
        case 'monster':
            renderMonsterRoom(roomContent, roomData);
            break;
        default:
            roomContent.innerHTML = '<p>Unknown room type</p>';
    }
    
    updateContinueButton();
    updateEventHistory();
    updateXPBalance();
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
                <div class="room-event-description">Trap resolved</div>
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
                <div class="trap-icon">${_renderEmoji(trap.emoji, 60)}</div>
                <div class="trap-name">${trap.name}</div>
                <div class="trap-effect" style="margin:8px 0;line-height:1.6">
                    ${targetDesc}<br>
                    📉 ${effectDesc}<br>
                    ${durationDesc ? `⏱️ ${durationDesc}` : ''}
                </div>
                <div class="d-flex gap-2 justify-content-center mt-3 flex-wrap">
                    <button class="btn-dungeon-primary" onclick="handleTrapChoice('attempt')">
                        🏃 Attempt Escape<br><small style="opacity:0.7">Risk escaping or take 1-hour cooldown</small>
                    </button>
                    <button class="btn-dungeon-primary" onclick="handleTrapChoice('accept')">
                        🛡️ Accept Trap<br><small style="opacity:0.7">Take the debuff and continue</small>
                    </button>
                </div>
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
                <div class="shrine-icon">${_renderEmoji(shrine.emoji, 60)}</div>
                <div class="shrine-name">${_escHtml(shrine.name)}</div>
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

// ═══════════════════════════════════════════════════════════════════════════
// NEW ROOM RENDERERS FOR PHASE 5
// ═══════════════════════════════════════════════════════════════════════════

// Render monster encounter room (Fight/Scare/Flee)
function renderMonsterEncounterRoom(container, roomData) {
    if (roomData.completed) {
        container.innerHTML = `
            <div class="room-event-container">
                <div class="room-event-icon">✅</div>
                <div class="room-event-description">Monster encounter resolved!</div>
            </div>
        `;
        return;
    }
    
    const monster = roomData.monster_data || { name: 'Unknown Monster', level: 1, element: 'basic', type: 'basic' };
    const monsterImgSrc = monster.emoji_file 
        ? `/static/Emojis/Pets/Equipment/${monster.emoji_file}` 
        : '/static/Emojis/Crawl/enemy.png';
    
    container.innerHTML = `
        <div class="room-event-container">
            <div class="room-event-icon">
                <img src="${monsterImgSrc}" style="width:80px;height:80px;object-fit:contain" onerror="this.src='/static/Emojis/Crawl/enemy.png'">
            </div>
            <div class="room-event-description">
                <h5>${_escHtml(monster.name)}</h5>
                <p>Level ${monster.level} • ${_escHtml(monster.element)} • ${_escHtml(monster.type)}</p>
                <p class="text-muted mt-2">How will you approach this encounter?</p>
            </div>
            <div class="d-flex gap-2 justify-content-center mt-3 flex-wrap">
                <button class="btn-dungeon-primary" onclick="handleMonsterAction('fight')">
                    ⚔️ Fight<br><small style="opacity:0.7">Battle for loot</small>
                </button>
                <button class="btn-dungeon-primary" onclick="handleMonsterAction('scare')">
                    😱 Scare<br><small style="opacity:0.7">Intimidate it away</small>
                </button>
                <button class="btn-dungeon-primary" onclick="handleMonsterAction('flee')">
                    🏃 Flee<br><small style="opacity:0.7">Run past it</small>
                </button>
            </div>
        </div>
    `;
}

// Render story segment room
function renderStorySegmentRoom(container, roomData) {
    if (roomData.completed) {
        container.innerHTML = `
            <div class="room-event-container">
                <div class="room-event-icon">✅</div>
                <div class="room-event-description">Story resolved!</div>
            </div>
        `;
        return;
    }
    
    const story = roomData.story_data || { scene: 'A mysterious passage awaits...', choices: [] };
    
    container.innerHTML = `
        <div class="room-event-container">
            <div class="room-event-icon">📖</div>
            <div class="room-event-description">
                <h5>Story Segment</h5>
                <p style="line-height:1.6;margin:12px 0">${_escHtml(story.scene)}</p>
            </div>
            <div class="d-flex flex-column gap-2 mt-3">
                ${story.choices.map((choice, idx) => `
                    <button class="btn-dungeon-primary text-start" onclick="handleStoryChoice(${idx + 1})" style="white-space:normal;padding:12px">
                        <strong>${idx + 1}.</strong> ${_escHtml(choice.description)}<br>
                        <small style="opacity:0.7">Requires: ${_escHtml(choice.skill_type)} • Difficulty: ${choice.difficulty_percentage}%</small>
                    </button>
                `).join('')}
            </div>
        </div>
    `;
}

// Render puzzle room
function renderPuzzleRoom(container, roomData) {
    if (roomData.completed) {
        container.innerHTML = `
            <div class="room-event-container">
                <div class="room-event-icon">✅</div>
                <div class="room-event-description">Puzzle solved!</div>
            </div>
        `;
        return;
    }
    
    const puzzle = roomData.puzzle_data || { description: 'A puzzle awaits...', hint: '', choices: [] };
    
    container.innerHTML = `
        <div class="room-event-container">
            <div class="room-event-icon">🧩</div>
            <div class="room-event-description">
                <h5>Puzzle Challenge</h5>
                <p style="line-height:1.6;margin:12px 0">${_escHtml(puzzle.description)}</p>
                ${puzzle.hint ? `<p class="text-muted"><em>Hint: ${_escHtml(puzzle.hint)}</em></p>` : ''}
            </div>
            <div class="d-flex flex-column gap-2 mt-3">
                ${puzzle.choices.map((choice, idx) => `
                    <button class="btn-dungeon-primary text-start" onclick="handlePuzzleAttempt(${idx + 1})" style="white-space:normal;padding:12px">
                        <strong>${idx + 1}.</strong> ${_escHtml(choice.description)}<br>
                        <small style="opacity:0.7">Requires: ${_escHtml(choice.skill_type)} • Difficulty: ${choice.difficulty_percentage}%</small>
                    </button>
                `).join('')}
            </div>
        </div>
    `;
}

// Render merchant room
function renderMerchantRoom(container, roomData) {
    if (!roomData.merchant_data || !roomData.merchant_data.items) {
        container.innerHTML = '<p class="text-muted">Merchant unavailable</p>';
        return;
    }
    
    const merchant = roomData.merchant_data;
    const xpBalance = currentDungeon.xp_balance || 0;
    
    container.innerHTML = `
        <div class="room-event-container">
            <div class="room-event-icon">🏪</div>
            <div class="room-event-description">
                <h5>Traveling Merchant</h5>
                <p>"Welcome, traveler! Browse my wares!"</p>
                <div class="p-2 mb-3" style="background:rgba(255,215,0,0.1);border-radius:8px;border:1px solid var(--gold-primary);">
                    <div class="d-flex justify-content-between align-items-center">
                        <span style="color:var(--gold-primary);font-weight:600;">💰 Your XP:</span>
                        <span id="merchant-xp-display" style="color:var(--gold-primary);font-size:1.2em;font-weight:700;">${xpBalance.toLocaleString()}</span>
                    </div>
                </div>
            </div>
            <div class="d-flex flex-column gap-2 mt-3">
                ${merchant.items.map((item, idx) => {
                    const imgSrc = _dungeonItemImgSrc(item);
                    const rarityColor = _dungeonRarityColor(item.rarity || 'Common');
                    const canAfford = xpBalance >= item.cost;
                    return `
                        <div class="p-3" style="background:rgba(255,255,255,0.05);border-radius:8px;border:1px solid ${rarityColor}">
                            <div class="d-flex align-items-center gap-3">
                                <img src="${imgSrc}" style="width:40px;height:40px;object-fit:contain;filter:drop-shadow(0 0 6px ${rarityColor})" onerror="this.style.display='none'">
                                <div class="flex-grow-1">
                                    <div style="color:${rarityColor};font-weight:600;">${_escHtml(item.name)}</div>
                                    <div style="font-size:0.8em;color:var(--text-secondary)">${_escHtml(item.type)} • ${_escHtml(item.rarity)}</div>
                                </div>
                                <div class="text-end">
                                    <div style="color:var(--gold-primary);font-weight:700;">${item.cost.toLocaleString()} XP</div>
                                    <button class="btn-dungeon-primary btn-sm mt-1" onclick="handleMerchantPurchase(${idx})" ${!canAfford ? 'disabled' : ''}>
                                        Buy
                                    </button>
                                </div>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        </div>
    `;
}

// Render chest/mimic room
function renderChestMimicRoom(container, roomData) {
    if (roomData.completed) {
        container.innerHTML = `
            <div class="room-event-container">
                <div class="room-event-icon">✅</div>
                <div class="room-event-description">Chest/Mimic resolved!</div>
            </div>
        `;
        return;
    }
    
    // Use the actual chest image from room data to disguise mimics
    const chestEmoji = roomData.chest_emoji || 'chest1';
    const chestImgSrc = `/static/Emojis/Pets/Equipment/${chestEmoji}.png`;
    const chestType = roomData.chest_type || 'Mysterious Chest';
    
    container.innerHTML = `
        <div class="room-event-container">
            <div class="room-event-icon">
                <img src="${chestImgSrc}" style="width:80px;height:80px;object-fit:contain" onerror="this.src='/static/Emojis/Pets/Equipment/chest1.png'">
            </div>
            <div class="room-event-description">
                <h5>${chestType}</h5>
                <p>A chest sits before you... but is it real, or a mimic?</p>
                <p class="text-muted mt-2">Choose your approach carefully!</p>
            </div>
            <div class="d-flex flex-column gap-2 mt-3">
                <button class="btn-dungeon-primary" onclick="handleChestMimicApproach(1)">
                    🗡️ Smash Open<br><small style="opacity:0.7">Quick but risky (low success rate)</small>
                </button>
                <button class="btn-dungeon-primary" onclick="handleChestMimicApproach(2)">
                    🔓 Carefully Unlock<br><small style="opacity:0.7">Balanced approach (medium success rate)</small>
                </button>
                <button class="btn-dungeon-primary" onclick="handleChestMimicApproach(3)">
                    👀 Watch & Wait<br><small style="opacity:0.7">Reveals mimics, highest success rate</small>
                </button>
            </div>
        </div>
    `;
}

// Render floor loot room (room 10)
function renderFloorLootRoom(container, roomData) {
    if (roomData.completed) {
        // Check if floor cooldown is active
        const floorCooldownUntil = currentDungeon.floor_cooldown_until || 0;
        const nowTime = Math.floor(Date.now() / 1000);
        const onCooldown = floorCooldownUntil > nowTime;
        const timeRemaining = onCooldown ? floorCooldownUntil - nowTime : 0;
        
        // Get the chest image for this floor
        const chestEmoji = roomData.chest_emoji || 'chest4';
        const chestImgSrc = `/static/Emojis/Pets/Equipment/${chestEmoji}.png`;
        
        container.innerHTML = `
            <div class="room-event-container">
                <div class="room-event-icon">
                    <img src="${chestImgSrc}" style="width:80px;height:80px;object-fit:contain" onerror="this.src='/static/Emojis/Pets/Equipment/chest4.png'">
                </div>
                <div class="room-event-description">
                    <h5>Floor Complete!</h5>
                    <p>You've claimed the ${roomData.chest_type || 'floor'} rewards!</p>
                    ${onCooldown ? `
                        <div class="p-3 mt-3" style="background:rgba(255,152,0,0.1);border-radius:8px;border:1px solid #ff9800;">
                            <p style="color:#ff9800;font-weight:600;margin:0">⏰ Floor Cooldown Active</p>
                            <p style="margin:8px 0;color:var(--text-secondary)">Time remaining: <span id="floor-cooldown-timer">${formatTimeRemaining(timeRemaining)}</span></p>
                            <p style="font-size:0.85em;margin:0;color:var(--text-muted)">Rest before advancing to the next floor</p>
                        </div>
                        <button class="btn-dungeon-primary mt-3" id="advance-floor-btn" disabled>
                            Advance to Next Floor
                        </button>
                    ` : `
                        <button class="btn-dungeon-primary mt-3" onclick="advanceFloor()">
                            🚀 Advance to Next Floor
                        </button>
                    `}
                </div>
            </div>
        `;
        
        // Start cooldown timer if active
        if (onCooldown) {
            startFloorCooldownTimer();
        }
    } else {
        // Get the chest image for this floor
        const chestEmoji = roomData.chest_emoji || 'chest4';
        const chestImgSrc = `/static/Emojis/Pets/Equipment/${chestEmoji}.png`;
        const chestType = roomData.chest_type || 'Floor Treasure';
        
        container.innerHTML = `
            <div class="room-event-container">
                <div class="room-event-icon">
                    <img src="${chestImgSrc}" style="width:80px;height:80px;object-fit:contain" onerror="this.src='/static/Emojis/Pets/Equipment/chest4.png'">
                </div>
                <div class="room-event-description">
                    <h5>${chestType}</h5>
                    <p>You've reached the end of this floor! Claim your rewards!</p>
                </div>
                <button class="btn-dungeon-primary mt-3" onclick="claimFloorLoot()">
                    🎁 Claim Floor Rewards
                </button>
            </div>
        `;
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
                        const petImgSrc = _dungeonPetImg(member.pet);
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

// Pet image helper: use badge_url if present, otherwise fall back to species sprite
function _dungeonPetImg(pet) {
    if (pet && pet.badge_url) return pet.badge_url;
    return pet && pet.species ? '/static/Emojis/Pets/' + pet.species + '.png' : '/static/Emojis/Pets/Deco/Basic.png';
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

// ═══════════════════════════════════════════════════════════════════════════
// NEW API HANDLERS FOR PHASE 5
// ═══════════════════════════════════════════════════════════════════════════

// Handle monster encounter action (Fight/Scare/Flee)
async function handleMonsterAction(action) {
    try {
        const response = await fetch(`/api/dungeon/${currentDungeon.dungeon_id}/monster/action`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: action })
        });
        
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to perform action');
        }
        
        const data = await response.json();
        
        // Show result message
        alert(data.result);
        
        // If forced battle, start battle
        if (data.forced_battle) {
            await startMonsterBattle();
        } else {
            // Reload dungeon state
            await loadDungeon(currentDungeon.dungeon_id);
        }
    } catch (error) {
        console.error('Error handling monster action:', error);
        alert('Failed to perform action: ' + error.message);
    }
}

// Handle story segment choice
async function handleStoryChoice(choice) {
    try {
        const response = await fetch(`/api/dungeon/${currentDungeon.dungeon_id}/story/choice`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ choice: choice })
        });
        
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to make choice');
        }
        
        const data = await response.json();
        
        // Show result with loot if any
        let message = data.result;
        if (data.loot && data.loot.length > 0) {
            message += '\n\nLoot received:\n' + data.loot.map(item => `• ${item.name} (${item.rarity})`).join('\n');
        }
        if (data.xp_reward) {
            message += `\n\nXP earned: ${data.xp_reward}`;
        }
        alert(message);
        
        // Reload dungeon state
        await loadDungeon(currentDungeon.dungeon_id);
    } catch (error) {
        console.error('Error handling story choice:', error);
        alert('Failed to make choice: ' + error.message);
    }
}

// Handle puzzle attempt
async function handlePuzzleAttempt(choice) {
    try {
        const response = await fetch(`/api/dungeon/${currentDungeon.dungeon_id}/puzzle/attempt`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ choice: choice })
        });
        
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to attempt puzzle');
        }
        
        const data = await response.json();
        
        // Show result with loot if any
        let message = data.result;
        if (data.loot && data.loot.length > 0) {
            message += '\n\nLoot received:\n' + data.loot.map(item => `• ${item.name} (${item.rarity})`).join('\n');
        }
        if (data.xp_reward) {
            message += `\n\nXP earned: ${data.xp_reward}`;
        }
        alert(message);
        
        // Reload dungeon state
        await loadDungeon(currentDungeon.dungeon_id);
    } catch (error) {
        console.error('Error handling puzzle attempt:', error);
        alert('Failed to attempt puzzle: ' + error.message);
    }
}

// Handle merchant purchase
async function handleMerchantPurchase(itemIndex) {
    try {
        const response = await fetch(`/api/dungeon/${currentDungeon.dungeon_id}/merchant/purchase`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ item_index: itemIndex })
        });
        
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to purchase item');
        }
        
        const data = await response.json();
        
        // Show result
        alert(data.result);
        
        // Update XP balance display
        if (data.new_xp_balance !== undefined) {
            const xpDisplay = document.getElementById('merchant-xp-display');
            if (xpDisplay) {
                xpDisplay.textContent = data.new_xp_balance.toLocaleString();
            }
            // Update dungeon XP balance
            currentDungeon.xp_balance = data.new_xp_balance;
        }
        
        // Reload dungeon state to update merchant inventory
        await loadDungeon(currentDungeon.dungeon_id);
    } catch (error) {
        console.error('Error handling merchant purchase:', error);
        alert('Failed to purchase item: ' + error.message);
    }
}

// Handle chest/mimic approach
async function handleChestMimicApproach(approach) {
    try {
        const response = await fetch(`/api/dungeon/${currentDungeon.dungeon_id}/chest_mimic/approach`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ approach: approach })
        });
        
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to approach chest');
        }
        
        const data = await response.json();
        
        // Show result
        alert(data.result);
        
        // If forced battle (mimic), start battle
        if (data.forced_battle) {
            await startMonsterBattle();
        } else if (data.loot && data.loot.length > 0) {
            // Show loot animation if it's a real chest
            const chestSrc = '/static/Emojis/Pets/Equipment/chest1.png';
            const chestColor = '#ffd700';
            _showDungeonChestAnimation(chestSrc, chestColor, data.loot, async function() {
                await loadDungeon(currentDungeon.dungeon_id);
            });
        } else {
            // Reload dungeon state
            await loadDungeon(currentDungeon.dungeon_id);
        }
    } catch (error) {
        console.error('Error handling chest/mimic approach:', error);
        alert('Failed to approach chest: ' + error.message);
    }
}

// Handle trap choice (Escape/Accept)
async function handleTrapChoice(choice) {
    try {
        const response = await fetch(`/api/dungeon/${currentDungeon.dungeon_id}/trap/choice`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ choice: choice })
        });
        
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to handle trap');
        }
        
        const data = await response.json();
        
        // Show result
        alert(data.result);
        
        // Reload dungeon state
        await loadDungeon(currentDungeon.dungeon_id);
    } catch (error) {
        console.error('Error handling trap choice:', error);
        alert('Failed to handle trap: ' + error.message);
    }
}

// Claim floor loot (room 10)
async function claimFloorLoot() {
    try {
        const response = await fetch(`/api/dungeon/${currentDungeon.dungeon_id}/floor_loot/claim`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to claim floor loot');
        }
        
        const data = await response.json();
        
        // Show loot animation
        const chestSrc = '/static/Emojis/Pets/Equipment/chest4.png';
        const chestColor = '#ff9800';
        _showDungeonChestAnimation(chestSrc, chestColor, data.loot || [], async function() {
            await loadDungeon(currentDungeon.dungeon_id);
        });
    } catch (error) {
        console.error('Error claiming floor loot:', error);
        alert('Failed to claim floor loot: ' + error.message);
    }
}

// Advance to next floor
async function advanceFloor() {
    try {
        const response = await fetch(`/api/dungeon/${currentDungeon.dungeon_id}/advance_floor`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to advance floor');
        }
        
        const data = await response.json();
        
        // Show result
        alert(data.result);
        
        // Reload dungeon state
        await loadDungeon(currentDungeon.dungeon_id);
    } catch (error) {
        console.error('Error advancing floor:', error);
        alert('Failed to advance floor: ' + error.message);
    }
}

// Check cooldowns (room and floor)
async function checkCooldowns() {
    try {
        const response = await fetch(`/api/dungeon/${currentDungeon.dungeon_id}/cooldown/check`);
        
        if (!response.ok) {
            throw new Error('Failed to check cooldowns');
        }
        
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Error checking cooldowns:', error);
        return null;
    }
}

// Update event history display
function updateEventHistory() {
    const historyContainer = document.getElementById('event-history-list');
    if (!historyContainer) return;
    
    const eventHistory = currentDungeon.event_history || [];
    
    if (eventHistory.length === 0) {
        historyContainer.innerHTML = '<p class="text-muted">No events yet</p>';
        return;
    }
    
    // Show last 5 events
    const recentEvents = eventHistory.slice(-5).reverse();
    
    historyContainer.innerHTML = recentEvents.map(event => {
        let emoji = EVENT_EMOJIS[event.event_type] || '❓';
        
        // For chest types and floor_loot, use the actual chest image
        if (['chest', 'chest1', 'chest2', 'chest3', 'chest4', 'chest_mimic', 'floor_loot'].includes(event.event_type)) {
            // Try to get chest_emoji from the event data, or use default based on type
            const chestEmoji = event.chest_emoji || event.event_type.replace('chest', 'chest') || 'chest1';
            emoji = `<img src="/static/Emojis/Pets/Equipment/${chestEmoji}.png" style="width:20px;height:20px;object-fit:contain;vertical-align:middle" onerror="this.style.display='none'">`;
        }
        
        return `
            <div class="event-history-item" style="padding:8px;margin-bottom:6px;background:rgba(255,255,255,0.03);border-radius:6px">
                <div style="display:flex;align-items:center;gap:8px">
                    <span style="font-size:1.2em">${emoji}</span>
                    <div style="flex-grow:1">
                        <div style="font-size:0.85em;font-weight:600;color:var(--gold-primary)">${event.event_type}</div>
                        <div style="font-size:0.75em;color:var(--text-secondary)">Floor ${event.floor} • Room ${event.room}</div>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// Update XP balance display
function updateXPBalance() {
    const xpBalanceDisplay = document.getElementById('xp-balance-display');
    const currentXPBalance = document.getElementById('current-xp-balance');
    
    if (!xpBalanceDisplay || !currentXPBalance) return;
    
    const xpBalance = currentDungeon.xp_balance || 0;
    
    // Show XP balance
    xpBalanceDisplay.style.display = 'block';
    currentXPBalance.textContent = xpBalance.toLocaleString();
}

// Format time remaining (seconds to mm:ss)
function formatTimeRemaining(seconds) {
    if (seconds <= 0) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Start floor cooldown countdown timer
function startFloorCooldownTimer() {
    // Clear any existing timer
    if (window.floorCooldownInterval) {
        clearInterval(window.floorCooldownInterval);
    }
    
    window.floorCooldownInterval = setInterval(() => {
        const floorCooldownUntil = currentDungeon.floor_cooldown_until || 0;
        const nowTime = Math.floor(Date.now() / 1000);
        const timeRemaining = Math.max(0, floorCooldownUntil - nowTime);
        
        const timerEl = document.getElementById('floor-cooldown-timer');
        const advanceBtn = document.getElementById('advance-floor-btn');
        
        if (timeRemaining <= 0) {
            // Cooldown expired
            clearInterval(window.floorCooldownInterval);
            if (timerEl) timerEl.textContent = '0:00';
            if (advanceBtn) {
                advanceBtn.disabled = false;
                advanceBtn.onclick = advanceFloor;
            }
            // Reload to update UI
            loadDungeon(currentDungeon.dungeon_id);
        } else {
            if (timerEl) timerEl.textContent = formatTimeRemaining(timeRemaining);
        }
    }, 1000);
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
    window.removePartyInviteInput = function() {}; // no-op, party removed
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
    // New Phase 5 handlers
    window.handleMonsterAction = handleMonsterAction;
    window.handleStoryChoice = handleStoryChoice;
    window.handlePuzzleAttempt = handlePuzzleAttempt;
    window.handleMerchantPurchase = handleMerchantPurchase;
    window.handleChestMimicApproach = handleChestMimicApproach;
    window.handleTrapChoice = handleTrapChoice;
    window.claimFloorLoot = claimFloorLoot;
    window.advanceFloor = advanceFloor;
    window.checkCooldowns = checkCooldowns;

// Start initialization — DOM is already ready when this script is injected
initializeDungeon();

})(); // end IIFE

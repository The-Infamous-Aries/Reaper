"""
Dungeon Crawl API Endpoints
"""
from fastapi import APIRouter, HTTPException, Request, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import logging
import json
import time
from typing import Dict, List, Optional
from Systems.Pets.PetGames.dungeon_crawl import (
    DungeonCrawl, 
    EVENT_MONSTER, EVENT_BOSS, EVENT_CHEST, EVENT_TRAP, EVENT_SHRINE,
    EVENT_CHEST1, EVENT_CHEST2, EVENT_CHEST3, EVENT_CHEST4,
    CHEST_EVENT_MAP, TRAP_EFFECTS, SHRINE_EFFECTS,
    TRAP_EFFECTS_GENERIC, TRAP_EFFECTS_ELEMENTAL, TRAP_EFFECTS_TYPE,
    SHRINE_EFFECTS_GENERIC, SHRINE_EFFECTS_ELEMENTAL, SHRINE_EFFECTS_TYPE,
    CHEST_TYPES, _resolve_emoji
)
from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.event_bus import EventQueue
from Systems.Pets.Logic.pet_components import AnimationComponent
from web.api.pets.gpp_helpers import _invalidate_stats_cache

logger = logging.getLogger("dungeon_api")
router = APIRouter()

# ── Per-user locks ────────────────────────────────────────────────────────────
# Active dungeon instances (in-memory cache)
active_dungeons: Dict[str, DungeonCrawl] = {}

# Active battle instances (with cleanup)
active_battles: Dict[str, Dict] = {}
BATTLE_TIMEOUT = 300  # 5 minutes


# ── Request models ────────────────────────────────────────────────────────────

class CreateDungeonRequest(BaseModel):
    party_members: List[int] = []

class StartBattleRequest(BaseModel):
    is_boss: bool = False

class BattleActionRequest(BaseModel):
    battle_id: str
    action: str
    user_id: str
    slot_index: Optional[int] = None

class CompleteBattleRequest(BaseModel):
    victory: bool
    monster_name: Optional[str] = None
    is_boss: bool = False


def get_user_id_from_session(request: Request) -> Optional[int]:
    """Get user ID from session (handles both discord_user and legacy user_id shapes)."""
    # Primary shape: {"discord_user": {"id": "..."}}
    discord_user = request.session.get('discord_user')
    if discord_user and isinstance(discord_user, dict):
        uid = discord_user.get('id')
        if uid:
            try:
                return int(uid)
            except (ValueError, TypeError):
                pass
    # Fallback shape (legacy): {"user_id": ...}
    uid = request.session.get('user_id')
    if uid:
        try:
            return int(uid)
        except (ValueError, TypeError):
            pass
    return None


async def get_dungeon_instance(dungeon_id: str, user_id: int) -> DungeonCrawl:
    """Return a DungeonCrawl from cache, loading from DB if needed. Raises 404 if not found."""
    if dungeon_id not in active_dungeons:
        dungeon = DungeonCrawl(user_id)
        if not await dungeon.load_dungeon(dungeon_id):
            raise HTTPException(status_code=404, detail='Dungeon not found')
        active_dungeons[dungeon_id] = dungeon
    return active_dungeons[dungeon_id]


@router.get('/user/me')
async def get_current_user(request: Request):
    """Get current user info"""
    try:
        user_id = get_user_id_from_session(request)
        if not user_id:
            raise HTTPException(status_code=401, detail='Not authenticated')
            
        return JSONResponse({
            'id': str(user_id),
            'user_id': user_id
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting current user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/dungeon/create')
async def create_dungeon(request: Request, body: CreateDungeonRequest):
    """Create a new dungeon"""
    try:
        user_id = get_user_id_from_session(request)
        if not user_id:
            raise HTTPException(status_code=401, detail='Not authenticated')

        # Validate creator has a pet
        creator_pet = await user_data_manager.get_pet_data_async(str(user_id))
        if not creator_pet:
            raise HTTPException(status_code=400, detail='You need a pet to enter the dungeon!')

        # Add creator to party
        party_members_list = [user_id] + body.party_members

        # Create dungeon
        dungeon = DungeonCrawl(user_id)
        dungeon_id = await dungeon.create_dungeon(party_members_list)

        # Cache dungeon instance
        active_dungeons[dungeon_id] = dungeon

        logger.info(f"Created dungeon {dungeon_id} for user {user_id}")

        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("dungeon_created", {"user_id": user_id, "dungeon_id": dungeon_id, "party_size": len(party_members_list)})
        await queue.flush()

        animation = AnimationComponent.for_ui_update("dungeon_enter", 600)

        return JSONResponse({
            'success': True,
            'dungeon_id': dungeon_id,
            'party_size': len(party_members_list),
            'animation': animation
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating dungeon: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/dungeon/active')
async def get_active_dungeons(request: Request):
    """Get user's active dungeons"""
    try:
        user_id = get_user_id_from_session(request)
        if not user_id:
            raise HTTPException(status_code=401, detail='Not authenticated')
            
        # Query database for user's dungeons
        import aiosqlite
        dungeons = []
        
        # Use same db_path as DungeonCrawl class
        db_path = "Databases/Pets/dungeon.db"
        
        # Ensure the table exists before querying
        _tmp = DungeonCrawl(user_id)
        await _tmp.initialize_database()
        
        async with aiosqlite.connect(db_path) as db:
            # Find dungeons where user is party leader or member
            async with db.execute('''
                SELECT dungeon_id, party_leader_id, party_members, current_floor, 
                       current_room, completed
                FROM dungeons 
                WHERE party_leader_id = ? OR party_members LIKE ?
                ORDER BY updated_at DESC
            ''', (str(user_id), f'%{user_id}%')) as cursor:
                async for row in cursor:
                    if not row[5]:  # Not completed
                        party_members = json.loads(row[2])
                        dungeons.append({
                            'dungeon_id': row[0],
                            'party_leader_id': int(row[1]),
                            'party_size': len(party_members),
                            'current_floor': row[3],
                            'current_room': row[4],
                            'total_rooms_cleared': (row[3] - 1) * 10 + (row[4] - 1)
                        })
                        
        return JSONResponse(dungeons)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting active dungeons: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/dungeon/{dungeon_id}')
async def get_dungeon(dungeon_id: str, request: Request):
    """Get dungeon state"""
    try:
        user_id = get_user_id_from_session(request)
        if not user_id:
            raise HTTPException(status_code=401, detail='Not authenticated')
            
        # Load from cache or database
        if dungeon_id not in active_dungeons:
            dungeon = DungeonCrawl(user_id)
            if not await dungeon.load_dungeon(dungeon_id):
                raise HTTPException(status_code=404, detail='Dungeon not found')
            active_dungeons[dungeon_id] = dungeon
        else:
            dungeon = active_dungeons[dungeon_id]
            
        # Verify user is in party
        if str(user_id) not in [str(m) for m in dungeon.party_members]:
            raise HTTPException(status_code=403, detail='Not in this dungeon party')
            
        # Get current room data
        room_data = dungeon.get_current_room_data()
        
        # Room data already has event-specific info from generation
        # No need to re-randomize
                
        return JSONResponse({
            'dungeon_id': dungeon.dungeon_id,
            'party_leader_id': dungeon.party_leader_id,
            'party_members': [str(m) for m in dungeon.party_members],
            'current_floor': dungeon.current_floor,
            'current_room': dungeon.current_room,
            'dungeon_state': dungeon.dungeon_state,
            'party_buffs': dungeon.party_buffs,
            'current_room_data': room_data,
            'ready_users': list(dungeon.ready_users)
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting dungeon: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/dungeon/{dungeon_id}/ready')
async def mark_ready(dungeon_id: str, request: Request):
    """Mark user as ready to continue"""
    try:
        user_id = get_user_id_from_session(request)
        if not user_id:
            raise HTTPException(status_code=401, detail='Not authenticated')
            
        dungeon = await get_dungeon_instance(dungeon_id, user_id)
        
        # Verify user is in party
        if str(user_id) not in [str(m) for m in dungeon.party_members]:
            raise HTTPException(status_code=403, detail='Not in this dungeon party')
            
        # Mark user as ready
        all_ready = dungeon.mark_user_ready(user_id)
        
        # Save state
        await dungeon.save_dungeon()

        # If all users ready, advance room
        if all_ready:
            await dungeon.complete_room()

        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("dungeon_ready", {"user_id": user_id, "dungeon_id": dungeon_id, "all_ready": all_ready})
        await queue.flush()

        animation = AnimationComponent.for_ui_update("ready_check", 400)

        return JSONResponse({
            'success': True,
            'all_ready': all_ready,
            'ready_users': list(dungeon.ready_users),
            'animation': animation
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking ready: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def cleanup_old_battles():
    """Remove battles older than BATTLE_TIMEOUT or past their cleanup_at time."""
    current_time = time.time()
    to_remove = []

    for battle_id, battle_data in active_battles.items():
        # Explicit cleanup_at set when battle ended
        cleanup_at = battle_data.get('cleanup_at')
        if cleanup_at and current_time >= cleanup_at:
            to_remove.append(battle_id)
            continue
        # General timeout for battles that never finished
        if not cleanup_at and current_time - battle_data.get('created_at', current_time) > BATTLE_TIMEOUT:
            to_remove.append(battle_id)

    for battle_id in to_remove:
        del active_battles[battle_id]
        logger.info(f"Cleaned up battle: {battle_id}")

    return len(to_remove)


@router.post('/dungeon/{dungeon_id}/battle/start')
async def start_battle(dungeon_id: str, request: Request, body: StartBattleRequest = None):
    """Start a monster or boss battle"""
    try:
        # Cleanup old battles first
        cleanup_old_battles()
        
        user_id = get_user_id_from_session(request)
        if not user_id:
            raise HTTPException(status_code=401, detail='Not authenticated')
            
        dungeon = await get_dungeon_instance(dungeon_id, user_id)
        is_boss = body.is_boss if body else False
        
        # Generate monster
        monster = await dungeon.generate_monster(is_boss=is_boss)
        
        # Get party members with their pets and buffs
        party_data = []
        for member_id in dungeon.party_members:
            pet = await user_data_manager.get_pet_data_async(str(member_id))

            if not pet:
                raise HTTPException(
                    status_code=400,
                    detail=f'Party member {member_id} does not have a pet. All party members need pets to battle.'
                )

            # Apply dungeon buffs to pet
            from Systems.Pets.PetGames.dungeon_crawl import apply_dungeon_buffs_to_pet
            active_buffs = dungeon.get_active_buffs(int(member_id))
            modified_pet = apply_dungeon_buffs_to_pet(pet, active_buffs)

            # Calculate stats (includes stat masteries)
            stats = StatsCalculator.calculate_pet_stats(modified_pet)

            # Use the computed attack/defense/max_health from StatsCalculator
            # (these already include equipment bonuses + mastery multipliers)
            p_atk = int(stats.get('attack', stats['ATT'] + stats['DEX']))
            p_def = int(stats.get('defense', stats['DEF'] + stats['INT']))
            # Cap health to 20× attack so dungeon battles last ~15-20 turns
            raw_hp = int(stats.get('max_health', 500))
            p_hp   = max(500, min(raw_hp, p_atk * 20))

            # Get action labels for this pet's species/type/element
            p_type = str(modified_pet.get('category', 'land')).lower()
            p_elem = str(modified_pet.get('element', 'basic')).lower()
            p_spec = str(modified_pet.get('species', '')).strip()
            action_labels = DamageCalculator.get_action_labels(
                p_type, p_elem, p_spec,
                custom_labels=modified_pet.get('action_labels', {})
            )

            # Get charge abilities
            starting_charge = 0
            charge_limit = 8
            try:
                from Systems.Pets.Logic.ability_tree import get_starting_charge_bonus, get_ability_effect
                starting_charge = int(get_starting_charge_bonus(pet))
                charge_limit_bonus = int(get_ability_effect(pet, "charge_limit_bonus"))
                charge_limit = 8 + charge_limit_bonus
            except Exception:
                pass

            # Build equipment display list (same order as arena: Mon, Gem, Mat, Hat, Mat, Gem, Mon)
            def _equip_items(p):
                eq = p.get('equipment') or {}
                slots = []
                mons = eq.get('Monsters', [])
                gems = eq.get('Gems', [])
                mats = eq.get('Material', [])
                hat  = eq.get('Hat')
                if isinstance(mons, dict): mons = [mons]
                if isinstance(gems, dict): gems = [gems]
                if isinstance(mats, dict): mats = [mats]
                def _item(i): return {'name': i.get('name',''), 'emoji_file': i.get('emoji_file', i.get('name','').replace(' ','') + '.png'), 'rarity': i.get('rarity','Common')}
                if len(mons) > 0: slots.append(_item(mons[0]))
                if len(gems) > 0: slots.append(_item(gems[0]))
                if len(mats) > 0: slots.append(_item(mats[0]))
                if hat and isinstance(hat, dict): slots.append(_item(hat))
                if len(mats) > 1: slots.append(_item(mats[1]))
                if len(gems) > 1: slots.append(_item(gems[1]))
                if len(mons) > 1: slots.append(_item(mons[1]))
                return slots

            # Get equipped skills for display in battle UI
            equipped_skills_display = []
            try:
                from Systems.Pets.Logic.battle_skills import get_equipped_skills, SKILL_BY_ID
                equipped_ids = get_equipped_skills(pet)
                for sid in equipped_ids:
                    sk = SKILL_BY_ID.get(sid)
                    if sk:
                        equipped_skills_display.append({
                            'id': sid,
                            'name': sk['name'],
                            'description': sk['description'],
                            'element': sk.get('element', ''),
                        })
            except Exception:
                pass

            party_data.append({
                'user_id': str(member_id),
                'pet': {
                    'name': modified_pet.get('name', 'Unknown'),
                    'level': modified_pet.get('level', 1),
                    'attack': p_atk,
                    'defense': p_def,
                    'health': p_hp,
                    'max_health': p_hp,
                    'element': modified_pet.get('element', 'Basic'),
                    'element2': modified_pet.get('element2'),
                    'category': modified_pet.get('category', 'Land'),
                    'species': modified_pet.get('species'),
                    'equipment': _equip_items(modified_pet),
                    'action_labels': action_labels,
                    'equipped_skills': equipped_skills_display,
                    'skill_cooldown': 0,  # starts ready
                },
                'pet_data': modified_pet,
                'buffs': active_buffs,
                'charge': starting_charge,
                'charge_limit': charge_limit
            })
        
        # Store battle data with timestamp
        battle_id = f"{dungeon_id}_battle_{dungeon.current_room}"
        active_battles[battle_id] = {
            'dungeon_id': dungeon_id,
            'monster': monster,
            'party': party_data,
            'is_boss': is_boss,
            'turn': 0,
            'party_actions': {},
            'battle_log': [],
            'created_at': time.time(),
            'monster_charge': 1.0,
            'party_charges': {p['user_id']: 1.0 + p['charge'] + float(p.get('pet_data', {}).get('_dungeon_charge_boost', 0)) for p in party_data},
            # Per-member skill state (cooldowns + active effects)
            'skill_states': {
                p['user_id']: {
                    'pet': p['pet_data'],
                    'total_attack': p['pet']['attack'],
                    'max_hp': p['pet']['max_health'],
                    'active_effects': [],
                    'skill_cooldowns': {},
                    'equipped_skills': [],
                }
                for p in party_data
            },
        }
        # Initialise skill state for each party member
        try:
            from Systems.Pets.Logic.battle_skills import init_battle_skill_state
            for p in party_data:
                state = active_battles[battle_id]['skill_states'][p['user_id']]
                init_battle_skill_state(state)
        except Exception as e:
            logger.warning(f"Could not init skill states: {e}")

        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("dungeon_battle_started", {"user_id": user_id, "dungeon_id": dungeon_id, "battle_id": battle_id, "is_boss": is_boss})
        await queue.flush()

        animation = AnimationComponent.for_battle_action(
            action="attack",
            damage=0,
            is_player=True,
            element_mult=1.0,
            effect="monster_spawn" if not is_boss else "boss_spawn"
        )

        return JSONResponse({
            'success': True,
            'battle_id': battle_id,
            'monster': monster,
            'party': party_data,
            'animation': animation
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting battle: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/dungeon/{dungeon_id}/battle/{battle_id}/status')
async def get_battle_status(dungeon_id: str, battle_id: str, request: Request):
    """Get current battle status (for polling). Returns turn_result when all players have acted."""
    try:
        user_id = get_user_id_from_session(request)
        if not user_id:
            raise HTTPException(status_code=401, detail='Not authenticated')
            
        if battle_id not in active_battles:
            raise HTTPException(status_code=404, detail='Battle not found')
            
        battle = active_battles[battle_id]
        
        # Check if all players have acted
        party_size = len(battle['party'])
        actions_received = len(battle['party_actions'])
        waiting = actions_received < party_size

        response_data: dict = {
            'success': True,
            'waiting': waiting,
            'actions_received': actions_received,
            'actions_needed': party_size,
            'turn': battle['turn'],
            'monster_health': battle['monster']['health']
        }

        # If the last turn was already processed (party_actions reset to {}),
        # include the last turn result so the polling client can process it.
        if not waiting and battle.get('last_turn_result'):
            response_data['turn_result'] = battle['last_turn_result']

        return JSONResponse(response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting battle status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/dungeon/{dungeon_id}/battle/action')
async def battle_action(
    dungeon_id: str,
    request: Request,
    body: BattleActionRequest
):
    """Submit a battle action"""
    try:
        session_user_id = get_user_id_from_session(request)
        if not session_user_id:
            raise HTTPException(status_code=401, detail='Not authenticated')
            
        battle_id = body.battle_id
        action = body.action
        user_id = body.user_id
        
        if battle_id not in active_battles:
            raise HTTPException(status_code=404, detail='Battle not found')
            
        battle = active_battles[battle_id]
        
        # Validate action
        if action not in ['attack', 'defend', 'charge', 'skill']:
            raise HTTPException(status_code=400, detail='Invalid action')
        
        # Record action — store slot_index alongside action for skill use
        battle['party_actions'][user_id] = action
        if action == 'skill' and body.slot_index is not None:
            battle['party_skill_slots'] = battle.get('party_skill_slots', {})
            battle['party_skill_slots'][user_id] = body.slot_index
        
        # Check if all players have acted
        party_size = len(battle['party'])
        if len(battle['party_actions']) >= party_size:
            # Process turn
            result = await process_battle_turn(battle)
            battle['party_actions'] = {}  # Reset for next turn
            battle['turn'] += 1
            battle['last_turn_result'] = result  # Store for status polling

            # Clean up battle if over
            if result.get('battle_over'):
                battle['cleanup_at'] = time.time() + 30

            # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
            queue = EventQueue()
            queue.push("dungeon_battle_action", {"user_id": user_id, "dungeon_id": dungeon_id, "battle_id": battle_id, "action": action, "battle_over": result.get('battle_over', False)})
            await queue.flush()

            animation = AnimationComponent.for_battle_action(
                action=action,
                damage=result.get('total_damage_dealt', 0),
                is_player=True,
                element_mult=1.0,
                effect="victory" if result.get('won') else "defeat"
            )

            return JSONResponse({
                'success': True,
                'turn_result': result,
                'battle_over': result.get('battle_over', False),
                'animation': animation
            })
        else:
            return JSONResponse({
                'success': True,
                'waiting': True,
                'actions_received': len(battle['party_actions']),
                'actions_needed': party_size
            })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing battle action: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def process_battle_turn(battle: Dict) -> Dict:
    """Process a battle turn with full skill + ability integration"""
    try:
        from Systems.Pets.Logic.battle_skills import (
            apply_skill, tick_battle_effects, tick_monster_effects,
            is_stunned, consume_stun,
            get_atk_multiplier, get_def_multiplier, get_damage_reduction,
            absorb_damage_through_shield, get_reflect_value, can_use_skill
        )
        _skills_available = True
    except Exception:
        _skills_available = False

    monster       = battle['monster']
    party         = battle['party']
    actions       = battle['party_actions']
    party_charges = battle.get('party_charges', {})
    monster_charge = float(battle.get('monster_charge', 1.0))
    skill_states  = battle.get('skill_states', {})

    # Ensure monster has a persistent active_effects list
    if 'active_effects' not in monster:
        monster['active_effects'] = []

    turn_log = []

    # ── Tick active effects for all party members ─────────────────────────
    if _skills_available:
        for member in party:
            uid   = member['user_id']
            state = skill_states.get(uid)
            if state:
                net_delta, tick_lines = tick_battle_effects(state, member['pet']['attack'])
                if net_delta != 0:
                    member['pet']['health'] = max(0, min(
                        member['pet']['max_health'],
                        member['pet']['health'] + net_delta
                    ))
                for line in tick_lines:
                    turn_log.append({'actor': member['pet']['name'], 'action': 'effect', 'message': line})

        # ── Tick active effects on the monster (DoT, stat debuffs, stun) ──
        monster_net_delta, monster_tick_lines = tick_monster_effects(monster)
        if monster_net_delta != 0:
            monster['health'] = max(0, monster['health'] + monster_net_delta)
        for line in monster_tick_lines:
            turn_log.append({'actor': monster['name'], 'action': 'effect', 'message': line})

    # ── Process party actions ─────────────────────────────────────────────
    for member in party:
        uid    = member['user_id']
        action = actions.get(uid, 'attack')
        pet    = member['pet']
        pet_data = member.get('pet_data', {})
        current_charge = float(party_charges.get(uid, 1.0))
        charge_limit   = float(member.get('charge_limit', 8))
        state = skill_states.get(uid, {})

        # Stun check — forced defend
        if _skills_available and state and is_stunned(state):
            consume_stun(state)
            action = 'defend'
            turn_log.append({'actor': pet['name'], 'action': 'effect',
                             'message': f"{pet['name']} is stunned and skips their turn!"})

        # no_defend trap check — forced attack (cannot defend)
        if action == 'defend' and pet_data.get('_dungeon_no_defend'):
            action = 'attack'
            turn_log.append({'actor': pet['name'], 'action': 'effect',
                             'message': f"{pet['name']} is cursed and cannot defend!"})

        # Apply ATK/DEF multipliers from active effects
        atk_mult = (get_atk_multiplier(state) if (_skills_available and state) else 1.0)
        def_mult = (get_def_multiplier(state) if (_skills_available and state) else 1.0)
        effective_atk = int(pet['attack'] * atk_mult)

        if action == 'skill' and _skills_available:
            equipped = state.get('equipped_skills', []) if state else []
            skill_used = False
            # Use the specific slot the player chose, or fall back to first ready slot
            party_skill_slots = battle.get('party_skill_slots', {})
            requested_slot = party_skill_slots.get(uid)
            slots_to_try = ([requested_slot] if requested_slot is not None and requested_slot < len(equipped)
                            else range(len(equipped)))
            for slot_idx in slots_to_try:
                skill_id = equipped[slot_idx] if slot_idx < len(equipped) else None
                if not skill_id:
                    continue
                if can_use_skill(state, slot_idx):
                    # Pass the persistent monster dict so DoT/stun/debuff effects accumulate
                    # Inject current charge so charge_boost can read and update it
                    state['charge'] = current_charge
                    state['charge_limit'] = charge_limit
                    state['max_charge_limit'] = charge_limit
                    result = apply_skill(skill_id, state, monster,
                                        battle_type='npc', slot_index=slot_idx)
                    if result['ok']:
                        hp_delta_target = result.get('hp_delta_target', 0)
                        hp_delta_user   = result.get('hp_delta_user', 0)
                        # Apply damage to monster
                        if hp_delta_target < 0:
                            monster['health'] = max(0, monster['health'] + hp_delta_target)
                        # Apply heal/lifesteal to player
                        if hp_delta_user > 0:
                            pet['health'] = min(pet['max_health'], pet['health'] + hp_delta_user)
                        elif hp_delta_user < 0:
                            pet['health'] = max(0, pet['health'] + hp_delta_user)
                        # Sync charge_boost result back to party_charges
                        if '_charge_boost_result' in state:
                            party_charges[uid] = float(state.pop('_charge_boost_result'))
                        turn_log.append({
                            'actor': pet['name'], 'action': 'skill',
                            'message': f"✨ {result.get('message', result.get('skill_name', 'Skill used'))}"
                        })
                        skill_used = True
                        break
            if not skill_used:
                action = 'attack'  # fall back to attack if no skill ready
                turn_log.append({'actor': pet['name'], 'action': 'effect',
                                 'message': f"{pet['name']}'s skill is on cooldown — attacking instead!"})

        if action == 'attack':
            # Apply monster DEF multiplier from skill debuffs on monster
            monster_def_mult = (get_def_multiplier(monster) if _skills_available else 1.0)
            effective_monster_def = int(monster['defense'] * monster_def_mult)

            battle_result = DamageCalculator.calculate_battle_action(
                attacker_attack=effective_atk,
                target_defense=effective_monster_def,
                charge_multiplier=current_charge,
                target_charge_multiplier=1.0,
                action_type='attack',
                attacker_action_type='attack',
                target_action_type='attack',
                attacker_type=pet.get('category'),
                attacker_element=pet.get('element'),
                attacker_element2=pet.get('element2'),
                defender_type=monster.get('type'),
                defender_element=monster.get('element'),
                attacker_species=pet.get('species'),
                attacker_pet_data=pet_data,
                use_scaling=False,
                battle_type='npc',
            )
            damage = battle_result['final_damage']
            monster['health'] = max(0, monster['health'] - damage)
            # Parry: if monster was defending and parry_damage > 0, reflect back to attacker
            if battle_result.get('parry_damage', 0) > 0:
                parry = battle_result['parry_damage']
                pet['health'] = max(0, pet['health'] - parry)
                turn_log.append({'actor': monster['name'], 'action': 'effect',
                                 'message': f"🪞 {monster['name']} parries {pet['name']} for {parry} damage!"})
            party_charges[uid] = 1.0
            turn_log.append({
                'actor': pet['name'], 'action': 'attack',
                'target': monster['name'], 'damage': damage,
                'is_critical': battle_result.get('is_critical', False),
                'charge_used': current_charge > 1.0,
                'charge_multiplier': current_charge
            })

        elif action == 'defend':
            # Defend does NOT build charge — it parries incoming attacks.
            # The parry is resolved when the monster attacks this player (see monster turn below).
            # We store the player's defense result so the monster turn can reference it.
            defend_result = DamageCalculator.calculate_battle_action(
                attacker_attack=int(pet['defense'] * def_mult),
                target_defense=0,
                charge_multiplier=1.0,
                action_type='defend',
                attacker_action_type='defend',
                attacker_type=pet.get('category'),
                attacker_element=pet.get('element'),
                attacker_element2=pet.get('element2'),
                defender_type=monster.get('type'),
                defender_element=monster.get('element'),
                attacker_species=pet.get('species'),
                attacker_pet_data=pet_data,
                use_scaling=False,
                battle_type='npc',
            )
            # Charge is NOT reset or built on defend — it persists unchanged
            turn_log.append({'actor': pet['name'], 'action': 'defend',
                             'message': f"{pet['name']} takes a defensive stance!"})

        elif action == 'charge':
            # Use the same progression as arena: get_next_charge_multiplier
            new_charge = min(charge_limit, DamageCalculator.get_next_charge_multiplier(current_charge))
            party_charges[uid] = new_charge
            turn_log.append({'actor': pet['name'], 'action': 'charge',
                             'message': f"{pet['name']} charges up! (×{new_charge:.0f})"})

    # ── Monster defeated? ─────────────────────────────────────────────────
    if monster['health'] <= 0:
        battle['party_charges'] = party_charges
        return {
            'battle_over': True, 'victory': True,
            'turn_log': turn_log, 'monster_health': 0,
            'party_charges': party_charges,
            'party_health': {m['user_id']: m['pet']['health'] for m in party},
        }

    # ── Monster's turn ────────────────────────────────────────────────────
    # Check if monster is stunned (from player skill)
    monster_stunned = _skills_available and is_stunned(monster)
    if monster_stunned:
        consume_stun(monster)
        monster_action = 'stun_skip'
        turn_log.append({'actor': monster['name'], 'action': 'effect',
                         'message': f"{monster['name']} is stunned and cannot act!"})
    else:
        monster_action = random.choice(['attack', 'attack', 'attack', 'charge'])

    if monster_action == 'attack':
        alive  = [m for m in party if m['pet']['health'] > 0]
        target = max(alive or party, key=lambda m: m['pet']['health'])
        target_pet   = target['pet']
        target_uid   = target['user_id']
        target_state = skill_states.get(target_uid, {})
        target_action = actions.get(target_uid, 'attack')

        t_def_mult = (get_def_multiplier(target_state) if (_skills_available and target_state) else 1.0)
        # When the player is defending, pass their defense stat so parry can fire
        effective_target_def = int(target_pet['defense'] * t_def_mult) if target_action == 'defend' else 0

        # Apply monster ATK multiplier from skill debuffs on monster
        monster_atk_mult = (get_atk_multiplier(monster) if _skills_available else 1.0)
        effective_monster_atk = int(monster['attack'] * monster_atk_mult)

        battle_result = DamageCalculator.calculate_battle_action(
            attacker_attack=effective_monster_atk,
            target_defense=effective_target_def,
            charge_multiplier=monster_charge,
            target_charge_multiplier=1.0,
            action_type='attack',
            attacker_action_type='attack',
            target_action_type=target_action,
            attacker_type=monster.get('type'),
            attacker_element=monster.get('element'),
            defender_type=target_pet.get('category'),
            defender_element=target_pet.get('element'),
            defender_element2=target_pet.get('element2'),
            defender_species=target_pet.get('species'),
            defender_pet_data=target.get('pet_data'),
            defender_current_hp=target_pet['health'],
            defender_max_hp=target_pet['max_health'],
            use_scaling=False,
            battle_type='npc',
        )
        damage = battle_result['final_damage']

        # Apply damage reduction / shield / reflect from active effects
        if _skills_available and target_state:
            dr = get_damage_reduction(target_state)
            damage = max(1, int(damage * (1.0 - dr)))
            damage, _absorbed, shield_log = absorb_damage_through_shield(target_state, damage)
            for sl in shield_log:
                turn_log.append({'actor': target_pet['name'], 'action': 'effect', 'message': sl})
            reflect = get_reflect_value(target_state)
            if reflect > 0 and damage > 0:
                reflect_dmg = max(1, int(damage * reflect))
                monster['health'] = max(0, monster['health'] - reflect_dmg)
                turn_log.append({'actor': target_pet['name'], 'action': 'effect',
                                 'message': f"🔄 Reflects {reflect_dmg} damage!"})

        target_pet['health'] = max(0, target_pet['health'] - damage)

        # Parry: if the player was defending and parry_damage > 0, deal it back to monster
        if battle_result.get('parry_damage', 0) > 0:
            parry = battle_result['parry_damage']
            monster['health'] = max(0, monster['health'] - parry)
            turn_log.append({'actor': target_pet['name'], 'action': 'effect',
                             'message': f"🪞 {target_pet['name']} parries {monster['name']} for {parry} damage!"})

        monster_charge = 1.0

        turn_log.append({
            'actor': monster['name'], 'action': 'attack',
            'target': target_pet['name'], 'damage': damage,
            'is_critical': battle_result.get('is_critical', False),
            'charge_used': float(battle.get('monster_charge', 1.0)) > 1.0,
            'charge_multiplier': float(battle.get('monster_charge', 1.0))
        })
    elif monster_action == 'charge':
        # Monster charges using the same progression as arena
        monster_charge = min(8.0, DamageCalculator.get_next_charge_multiplier(monster_charge))
        turn_log.append({'actor': monster['name'], 'action': 'charge',
                         'message': f"{monster['name']} charges! (×{monster_charge:.0f})"})
    # stun_skip: monster does nothing this turn (already logged above)

    # ── Party defeated? ───────────────────────────────────────────────────
    if all(m['pet']['health'] <= 0 for m in party):
        battle['party_charges'] = party_charges
        battle['monster_charge'] = monster_charge
        return {
            'battle_over': True, 'victory': False,
            'turn_log': turn_log, 'monster_health': monster['health'],
            'party_charges': party_charges,
            'party_health': {m['user_id']: m['pet']['health'] for m in party},
        }

    battle['party_charges'] = party_charges
    battle['monster_charge'] = monster_charge

    # Build per-user skill cooldown map for the frontend (all slots)
    skill_cooldowns = {}
    for uid, state in skill_states.items():
        cds = state.get('skill_cooldowns', {})
        skill_cooldowns[uid] = {str(k): v for k, v in cds.items()}

    return {
        'battle_over': False,
        'turn_log': turn_log,
        'monster_health': monster['health'],
        'party_health': {m['user_id']: m['pet']['health'] for m in party},
        'party_charges': party_charges,
        'monster_charge': monster_charge,
        'skill_cooldowns': skill_cooldowns,
    }


@router.post('/dungeon/{dungeon_id}/battle/complete')
async def complete_battle(
    dungeon_id: str, 
    request: Request,
    body: CompleteBattleRequest
):
    """Complete a battle and award loot"""
    try:
        user_id = get_user_id_from_session(request)
        if not user_id:
            raise HTTPException(status_code=401, detail='Not authenticated')
            
        dungeon = await get_dungeon_instance(dungeon_id, user_id)
        
        if not body.victory:
            raise HTTPException(status_code=400, detail='Battle not won')
            
        victory = body.victory
        monster_name = body.monster_name
        is_boss = body.is_boss
            
        # Award loot to all party members
        loot_by_user = {}
        
        for member_id in dungeon.party_members:
            user_loot = []
            
            if is_boss:
                # Bosses give Keys + XP only — no Monster item loot
                user_loot.extend([
                    {'name': 'Key1', 'type': 'Key', 'count': 1},
                    {'name': 'Key2', 'type': 'Key', 'count': 1},
                    {'name': 'Key3', 'type': 'Key', 'count': 1}
                ])
            else:
                # Regular monsters drop their Monster equipment item
                if monster_name:
                    user_loot.append({
                        'name': monster_name,
                        'type': 'Monster',
                        'count': 1
                    })
                
            # Add loot to user inventory
            pet = await user_data_manager.get_pet_data_async(str(member_id))

            if pet:
                inventory = pet.get('inventory', [])
                for item in user_loot:
                    existing = next((i for i in inventory if i['name'] == item['name'] and i['type'] == item['type']), None)
                    if existing:
                        existing['count'] = existing.get('count', 1) + item['count']
                    else:
                        inventory.append(item)

                pet['inventory'] = inventory
                await user_data_manager.save_pet_data(str(member_id), pet.get('name', 'Pet'), pet)
                # ── GPP: invalidate cache after pet data mutation ─────────────────────
                _invalidate_stats_cache(pet)

            loot_by_user[str(member_id)] = user_loot

        # Mark room as complete - update the actual room in dungeon_state
        room_data = dungeon.get_current_room_data()
        if room_data:
            # Find and update the room in the dungeon state
            for room in dungeon.dungeon_state.get('rooms', []):
                if room['room'] == dungeon.current_room:
                    room['completed'] = True
                    break
            await dungeon.save_dungeon()

        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("dungeon_battle_complete", {"user_id": user_id, "dungeon_id": dungeon_id, "victory": victory, "is_boss": is_boss})
        await queue.flush()

        animation = AnimationComponent.for_loot(loot_by_user, 800)

        return JSONResponse({
            'success': True,
            'loot': loot_by_user,
            'animation': animation
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing battle: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/dungeon/{dungeon_id}/chest/open')
async def open_chest(dungeon_id: str, request: Request):
    """Open a chest and get loot"""
    try:
        user_id = get_user_id_from_session(request)
        if not user_id:
            raise HTTPException(status_code=401, detail='Not authenticated')
            
        dungeon = await get_dungeon_instance(dungeon_id, user_id)
        
        # Get chest type from room data
        room_data = dungeon.get_current_room_data()
        if not room_data or room_data['event_type'] not in CHEST_EVENT_MAP:
            raise HTTPException(status_code=400, detail='Not a chest room')
            
        # Check if user already opened this chest
        user_id_str = str(user_id)
        chest_openers = room_data.get('chest_openers', [])
        
        if user_id_str in chest_openers:
            raise HTTPException(status_code=400, detail='You already opened this chest')
        
        # Resolve chest type from the event type
        chest_idx = CHEST_EVENT_MAP[room_data['event_type']]
        chest_type = {
            "name": room_data.get("chest_type", CHEST_TYPES[chest_idx]["name"]),
            "rarity_pool": room_data.get("chest_rarity_pool", CHEST_TYPES[chest_idx]["rarity_pool"]),
            "count": room_data.get("chest_count", CHEST_TYPES[chest_idx]["count"]),
        }
        
        # Generate loot for current user
        user_loot = await dungeon.generate_chest_loot(chest_type, user_id)

        # Add loot to user inventory
        pet = await user_data_manager.get_pet_data_async(str(user_id))

        if pet:
            inventory = pet.get('inventory', [])
            for item in user_loot:
                existing = next((i for i in inventory if i['name'] == item['name'] and i['type'] == item['type']), None)
                if existing:
                    existing['count'] = existing.get('count', 1) + item['count']
                else:
                    inventory.append(item)

            pet['inventory'] = inventory
            await user_data_manager.save_pet_data(str(user_id), pet.get('name', 'Pet'), pet)
            # ── GPP: invalidate cache after pet data mutation ─────────────────────
            _invalidate_stats_cache(pet)

        # Mark user as having opened the chest
        chest_openers.append(user_id_str)
        room_data['chest_openers'] = chest_openers

        # Mark room complete only if ALL party members have opened
        if len(chest_openers) >= len(dungeon.party_members):
            room_data['completed'] = True

        await dungeon.save_dungeon()

        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("dungeon_chest_opened", {"user_id": user_id, "dungeon_id": dungeon_id, "chest_type": chest_type['name']})
        await queue.flush()

        animation = AnimationComponent.for_loot(user_loot, 600)

        return JSONResponse({
            'success': True,
            'loot': user_loot,
            'chest_type': chest_type['name'],
            'all_opened': room_data.get('completed', False),
            'animation': animation
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error opening chest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/dungeon/{dungeon_id}/trap/trigger')
async def trigger_trap(dungeon_id: str, request: Request):
    """Trigger a trap"""
    try:
        user_id = get_user_id_from_session(request)
        if not user_id:
            raise HTTPException(status_code=401, detail='Not authenticated')
            
        dungeon = await get_dungeon_instance(dungeon_id, user_id)
        
        room_data = dungeon.get_current_room_data()
        if not room_data or room_data['event_type'] != EVENT_TRAP:
            raise HTTPException(status_code=400, detail='Not a trap room')
            
        if room_data.get('completed'):
            raise HTTPException(status_code=400, detail='Trap already triggered')
            
        # Use pre-generated trap data from room
        trap = room_data.get("trap_data")
        if not trap:
            # Fallback: 50/50 generic vs elemental+type (same logic as _generate_floor)
            _pool = (TRAP_EFFECTS_GENERIC if random.random() < 0.5
                     else TRAP_EFFECTS_ELEMENTAL + TRAP_EFFECTS_TYPE)
            trap = _resolve_emoji(random.choice(_pool))
        
        # Apply trap effect to party (async — respects element/type filters)
        await dungeon.apply_trap_effect_async(trap)

        # Build per-member effect summary for the frontend
        member_effects = []
        for member_id in dungeon.party_members:
            member_id_str = str(member_id)
            tf = trap.get("target_filter")
            if tf is not None:
                matched = await dungeon._pet_matches_filter(member_id_str, tf)
                effective_value = trap["value"] if matched else trap["value"] * 0.5
                hit_type = "full" if matched else "splash"
            else:
                effective_value = trap["value"]
                hit_type = "full"
            member_effects.append({
                "user_id": member_id_str,
                "hit_type": hit_type,
                "value": effective_value,
            })

        # Mark room as complete
        room_data['completed'] = True
        await dungeon.save_dungeon()

        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("dungeon_trap_triggered", {"user_id": user_id, "dungeon_id": dungeon_id, "trap": trap.get("emoji")})
        await queue.flush()

        animation = AnimationComponent.for_ui_update("trap_trigger", 500, {"trap_emoji": trap.get("emoji")})

        return JSONResponse({
            'success': True,
            'trap': trap,
            'member_effects': member_effects,
            'animation': animation
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering trap: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/dungeon/{dungeon_id}/shrine/activate')
async def activate_shrine(dungeon_id: str, request: Request):
    """Activate a shrine"""
    try:
        user_id = get_user_id_from_session(request)
        if not user_id:
            raise HTTPException(status_code=401, detail='Not authenticated')
            
        dungeon = await get_dungeon_instance(dungeon_id, user_id)
        
        room_data = dungeon.get_current_room_data()
        if not room_data or room_data['event_type'] != EVENT_SHRINE:
            raise HTTPException(status_code=400, detail='Not a shrine room')
            
        if room_data.get('completed'):
            raise HTTPException(status_code=400, detail='Shrine already activated')
            
        # Use pre-generated shrine data from room
        shrine = room_data.get("shrine_data")
        if not shrine:
            # Fallback: 50/50 generic vs elemental+type (same logic as _generate_floor)
            _pool = (SHRINE_EFFECTS_GENERIC if random.random() < 0.5
                     else SHRINE_EFFECTS_ELEMENTAL + SHRINE_EFFECTS_TYPE)
            shrine = _resolve_emoji(random.choice(_pool))
        
        # Apply shrine effect to party (async — respects element/type filters)
        await dungeon.apply_shrine_effect_async(shrine)

        # Build per-member blessing summary for the frontend
        member_effects = []
        for member_id in dungeon.party_members:
            member_id_str = str(member_id)
            tf = shrine.get("target_filter")
            if tf is not None:
                blessed = await dungeon._pet_matches_filter(member_id_str, tf)
            else:
                blessed = True
            member_effects.append({
                "user_id": member_id_str,
                "blessed": blessed,
            })

        # Mark room as complete
        room_data['completed'] = True
        await dungeon.save_dungeon()

        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("dungeon_shrine_activated", {"user_id": user_id, "dungeon_id": dungeon_id, "shrine": shrine.get("emoji")})
        await queue.flush()

        animation = AnimationComponent.for_ui_update("shrine_bless", 500, {"shrine_emoji": shrine.get("emoji")})

        return JSONResponse({
            'success': True,
            'shrine': shrine,
            'member_effects': member_effects,
            'animation': animation
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating shrine: {e}")
        raise HTTPException(status_code=500, detail=str(e))

"""
Arena API — manages live arena rooms, WebSocket broadcast, NPC battles, PvP matchmaking,
and 4-player Boss battles.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Body, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.event_bus import EventQueue
from Systems.Pets.Logic.pet_components import AnimationComponent
from web.api.pets.gpp_helpers import _invalidate_stats_cache

logger = logging.getLogger("arena_api")
router = APIRouter()

# ── Pet badge helpers ─────────────────────────────────────────────────────────
ARENA_PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARENA_BADGE_STATIC_ROOT = ARENA_PROJECT_ROOT / "web" / "static" / "pet_badges"

def _arena_selected_badge_url(user_id: str) -> str:
    safe_user_id = re.sub(r"[^0-9A-Za-z_-]", "", str(user_id))
    selected = ARENA_BADGE_STATIC_ROOT / safe_user_id / "selected.png"
    if not selected.exists():
        return ""
    return f"/static/pet_badges/{safe_user_id}/selected.png?v={int(selected.stat().st_mtime)}"

# ── Arena state ───────────────────────────────────────────────────────────────
# 12 rooms total
NUM_ROOMS = 12

# ── Boss battle in-memory state ───────────────────────────────────────────────
# Keyed by room_id. Holds the full boss battle state between turns.
_boss_battles: Dict[int, Dict[str, Any]] = {}

BOSS_MAX_PLAYERS = 4


class ArenaRoom:
    def __init__(self, room_id: int):
        self.room_id   = room_id
        self.occupants: List[Dict[str, Any]] = []   # [{user_id, username, avatar, status, pet_name, pet_species}]
        self.state     = "empty"   # empty | npc_battle | pvp_waiting | pvp_battle | boss_waiting | boss_battle | spectating
        self.battle_log: List[str] = []
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "room_id":   self.room_id,
            "state":     self.state,
            "occupants": self.occupants,
            "battle_log": self.battle_log[-6:],  # last 6 lines for spectators
            "updated_at": self.updated_at,
        }

    def is_empty(self) -> bool:
        return len(self.occupants) == 0

    def has_user(self, user_id: str) -> bool:
        return any(o["user_id"] == user_id for o in self.occupants)

    def remove_user(self, user_id: str):
        self.occupants = [o for o in self.occupants if o["user_id"] != user_id]
        if not self.occupants:
            self.state = "empty"
            self.battle_log = []
            _boss_battles.pop(self.room_id, None)
        self.updated_at = time.time()

    def add_user(self, info: Dict[str, Any]):
        if not self.has_user(info["user_id"]):
            self.occupants.append(info)
        self.updated_at = time.time()


_rooms: Dict[int, ArenaRoom] = {i: ArenaRoom(i) for i in range(NUM_ROOMS)}

# ── WebSocket manager ─────────────────────────────────────────────────────────
class ArenaConnectionManager:
    def __init__(self):
        self._connections: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket):
        self._connections.discard(ws)

    async def broadcast(self, data: Any):
        msg = json.dumps(data)
        dead: Set[WebSocket] = set()
        for ws in list(self._connections):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._connections.discard(ws)

    @property
    def count(self) -> int:
        return len(self._connections)


_arena_manager = ArenaConnectionManager()


async def _broadcast_rooms():
    """Push full room state to all arena WebSocket clients."""
    await _arena_manager.broadcast({
        "type": "rooms",
        "rooms": [r.to_dict() for r in _rooms.values()],
    })
    try:
        await broadcast_unified()
    except Exception:
        pass


# ── WebSocket endpoint ────────────────────────────────────────────────────────
@router.websocket("/ws/arena")
async def arena_ws(websocket: WebSocket):
    await _arena_manager.connect(websocket)
    # Send current state immediately on connect
    await websocket.send_text(json.dumps({
        "type": "rooms",
        "rooms": [r.to_dict() for r in _rooms.values()],
    }))
    try:
        while True:
            await websocket.receive_text()   # keep-alive; client sends pings
    except WebSocketDisconnect:
        _arena_manager.disconnect(websocket)


# ── REST: get all rooms ───────────────────────────────────────────────────────
@router.get("/arena/rooms")
async def get_rooms():
    return JSONResponse({"rooms": [r.to_dict() for r in _rooms.values()]})


# ── REST: join a room ─────────────────────────────────────────────────────────
@router.post("/arena/join")
async def join_room(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    user_id  = str(user["id"])
    room_id  = int(data.get("room_id", 0))
    mode     = data.get("mode", "npc")   # "npc" | "pvp" | "boss"

    if room_id not in _rooms:
        raise HTTPException(status_code=400, detail="Invalid room")

    room = _rooms[room_id]

    # Remove user from any OTHER room first (not the target room)
    for r in _rooms.values():
        if r.room_id != room_id and r.has_user(user_id):
            r.remove_user(user_id)

    # Boss mode: allow up to BOSS_MAX_PLAYERS to join a waiting room
    if mode == "boss":
        if room.state not in ("empty", "boss_waiting"):
            raise HTTPException(status_code=400, detail="Room is not available for boss battle")
        if len(room.occupants) >= BOSS_MAX_PLAYERS:
            raise HTTPException(status_code=400, detail=f"Boss room is full ({BOSS_MAX_PLAYERS} players max)")
    elif not room.is_empty() and room.state not in ("pvp_waiting",):
        raise HTTPException(status_code=400, detail="Room is occupied")

    pet = await user_data_manager.get_pet_data_async(user_id)
    avatar_hash = user.get("avatar") or ""
    
    from Systems.Functions.discord_utils import get_discord_avatar_url
    avatar_url = get_discord_avatar_url(user_id, avatar_hash, size=64)

    occupant = {
        "user_id":     user_id,
        "username":    user.get("username", "Unknown"),
        "avatar":      avatar_url,
        "status":      "idle",
        "pet_name":    pet.get("name", "No Pet") if pet else "No Pet",
        "pet_species": pet.get("species", "") if pet else "",
        "mode":        mode,
    }
    room.add_user(occupant)

    if mode == "boss":
        room.state = "boss_waiting"
    elif mode == "pvp":
        room.state = "pvp_waiting"
    else:
        room.state = "npc_battle"
    room.updated_at = time.time()

    await _broadcast_rooms()

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("arena_joined", {"user_id": user_id, "room_id": room_id, "mode": mode})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("arena_join", 400)

    return JSONResponse({"success": True, "room_id": room_id, "player_count": len(room.occupants), "animation": animation})


# ── REST: leave a room ────────────────────────────────────────────────────────
@router.post("/arena/leave")
async def leave_room(request: Request):
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    user_id = str(user["id"])
    for r in _rooms.values():
        if r.has_user(user_id):
            r.remove_user(user_id)
    await _broadcast_rooms()

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("arena_left", {"user_id": user_id})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("arena_leave", 400)

    return JSONResponse({"success": True, "animation": animation})


# ── REST: NPC battle (full simulation, streams log via broadcast) ─────────────
@router.post("/arena/battle/npc")
async def arena_npc_battle(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    user_id  = str(user["id"])
    room_id  = int(data.get("room_id", 0))
    difficulty = (data.get("difficulty") or "easy").lower()
    if difficulty not in ("easy", "average", "hard"):
        difficulty = "easy"

    if room_id not in _rooms:
        raise HTTPException(status_code=400, detail="Invalid room")

    room = _rooms[room_id]
    if not room.has_user(user_id):
        raise HTTPException(status_code=400, detail="You are not in this room")

    # Mark occupant as in-battle
    for occ in room.occupants:
        if occ["user_id"] == user_id:
            occ["status"] = "battling"
    room.state = "npc_battle"
    room.battle_log = []
    room.updated_at = time.time()
    await _broadcast_rooms()

    # ── Run battle (reuse pets_api logic) ────────────────────────────────────
    try:
        from web.api.pets_api import _run_npc_battle_sim
        result = await _run_npc_battle_sim(user_id, difficulty)
    except Exception as e:
        logger.error(f"Arena NPC battle error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Battle failed")

    # Build a readable log for spectators
    log_lines: List[str] = []
    pet_name   = result["player"]["name"]
    enemy_name = result["enemy"]["name"]
    log_lines.append(f"⚔️ {pet_name} vs {enemy_name} ({difficulty.title()})")
    for t in result["turns"]:
        for line in t.get("lines", []):
            log_lines.append(f"[T{t['turn']}] {line}")
    outcome = "🏆 Victory!" if result["won"] else "💀 Defeated"
    log_lines.append(f"{outcome} +{result['xp_gained']} XP")

    room.battle_log = log_lines
    room.updated_at = time.time()
    await _broadcast_rooms()

    # Mark occupant idle again
    for occ in room.occupants:
        if occ["user_id"] == user_id:
            occ["status"] = "idle"
    room.updated_at = time.time()
    await _broadcast_rooms()

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("arena_npc_battle", {"user_id": user_id, "difficulty": difficulty, "won": result["won"], "xp_gained": result["xp_gained"]})
    await queue.flush()

    animation = AnimationComponent.for_battle_action(
        action="attack",
        damage=result.get("total_damage_dealt", 0),
        is_player=True,
        element_mult=1.0,
        effect="victory" if result["won"] else "defeat"
    )

    return JSONResponse({**result, "log": log_lines, "animation": animation})


# ── REST: PvP challenge (accept another user in a pvp_waiting room) ───────────
@router.post("/arena/battle/pvp")
async def arena_pvp_battle(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    user_id  = str(user["id"])
    room_id  = int(data.get("room_id", 0))

    if room_id not in _rooms:
        raise HTTPException(status_code=400, detail="Invalid room")

    room = _rooms[room_id]
    challenger_id = next(
        (o["user_id"] for o in room.occupants if o["user_id"] != user_id), None
    )
    if not challenger_id:
        raise HTTPException(status_code=400, detail="No challenger in room")

    # Add challenger to room
    pet = await user_data_manager.get_pet_data_async(user_id)
    avatar_hash = user.get("avatar") or ""
    
    from Systems.Functions.discord_utils import get_discord_avatar_url
    avatar_url = get_discord_avatar_url(user_id, avatar_hash, size=64)
    
    room.add_user({
        "user_id":     user_id,
        "username":    user.get("username", "Unknown"),
        "avatar":      avatar_url,
        "status":      "battling",
        "pet_name":    pet.get("name", "No Pet") if pet else "No Pet",
        "pet_species": pet.get("species", "") if pet else "",
        "mode":        "pvp",
    })
    for occ in room.occupants:
        occ["status"] = "battling"
    room.state = "pvp_battle"
    room.battle_log = []
    room.updated_at = time.time()
    await _broadcast_rooms()

    # ── Simulate PvP ─────────────────────────────────────────────────────────
    try:
        from web.api.pets_api import _run_pvp_battle_sim
        result = await _run_pvp_battle_sim(user_id, challenger_id)
    except Exception as e:
        logger.error(f"Arena PvP battle error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="PvP battle failed")

    log_lines: List[str] = result.get("log", [])
    room.battle_log = log_lines
    room.state = "empty"
    room.occupants = []
    room.updated_at = time.time()
    await _broadcast_rooms()

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("arena_pvp_battle", {"user_id": user_id, "challenger_id": challenger_id, "winner": result.get("winner")})
    await queue.flush()

    animation = AnimationComponent.for_battle_action(
        action="attack",
        damage=result.get("total_damage_dealt", 0),
        is_player=True,
        element_mult=1.0,
        effect="victory" if result.get("winner") == user_id else "defeat"
    )

    return JSONResponse({**result, "animation": animation})


# ── REST: Boss battle — start (generates boss from player avg stats) ──────────
@router.post("/arena/battle/boss/start")
async def arena_boss_start(request: Request, data: Dict[str, Any] = Body(...)):
    """
    Start a boss battle for the room. Any player in the room can trigger this.
    Generates the boss from the average stats of all players in the room.
    Requires at least 2 players (max 4).
    """
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    user_id = str(user["id"])
    room_id = int(data.get("room_id", 0))

    if room_id not in _rooms:
        raise HTTPException(status_code=400, detail="Invalid room")

    room = _rooms[room_id]
    if not room.has_user(user_id):
        raise HTTPException(status_code=400, detail="You are not in this room")
    if room.state not in ("boss_waiting", "boss_battle"):
        raise HTTPException(status_code=400, detail="Room is not in boss mode")
    if len(room.occupants) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 players to start a boss battle")

    # Check relationships between all participants
    participant_ids = [occ["user_id"] for occ in room.occupants]
    
    # Import the relationship checking function
    from Systems.Pets.PetGames.pvp_system import can_battle_boss_together, get_boss_battle_multipliers
    
    can_battle, reason = await can_battle_boss_together(participant_ids)
    if not can_battle:
        raise HTTPException(status_code=400, detail=reason)
    
    # Get relationship multipliers for boss battle
    relationship_multipliers = await get_boss_battle_multipliers(participant_ids)
    if not relationship_multipliers:  # Empty dict means battle blocked
        raise HTTPException(status_code=400, detail="Enemies cannot fight boss battles together!")

    # Load all player pets
    from Systems.Pets.Logic.pet_brain import StatsCalculator, DamageCalculator
    from Systems.Pets.Logic.ability_tree import get_ability_effect, get_starting_charge_bonus
    from Systems.Pets.Logic.battle_skills import (
        init_battle_skill_state, get_max_skill_slots, SKILL_BY_ID
    )
    import os as _os

    player_states: List[Dict[str, Any]] = []
    avg_atk = 0
    avg_def = 0
    avg_hp  = 0

    # Store per-player skill state server-side so it survives across turns
    # (same pattern as _arena_battle_sessions in pets_api.py)
    if not hasattr(arena_boss_start, "_boss_skill_sessions"):
        arena_boss_start._boss_skill_sessions = {}
    boss_skill_sessions: Dict[str, Any] = {}

    for occ in room.occupants:
        uid = occ["user_id"]
        pet = await user_data_manager.get_pet_data_async(uid)
        if not pet:
            raise HTTPException(status_code=400, detail=f"{occ['username']} has no pet")
        stats = StatsCalculator.calculate_pet_stats(pet)
        p_atk  = int(stats.get("attack", 10))
        p_def  = int(stats.get("defense", 5))
        p_hp   = int(stats.get("max_health", 500))
        p_type = str(pet.get("category", "land")).lower()
        p_elem = str(pet.get("element", "basic")).lower()
        p_elem2= str(pet.get("element2", "") or "").lower() or None
        p_spec = str(pet.get("species", "")).strip()
        action_labels = DamageCalculator.get_action_labels(p_type, p_elem, p_spec, custom_labels=pet.get("action_labels", {}))

        # Apply ability-tree bonuses (same as NPC battle)
        health_bonus = get_ability_effect(pet, "battle_health_bonus")
        if health_bonus > 0:
            p_hp = int(p_hp * (1.0 + health_bonus))

        p_charge_limit = int(DamageCalculator.get_max_charge(pet))  # base 5 + charge_limit_bonus

        p_starting_charge = 1.0 + int(get_starting_charge_bonus(pet))
        p_starting_charge = min(p_starting_charge, float(p_charge_limit))

        # Initialise server-side skill state for this player
        skill_state: Dict[str, Any] = {
            "pet": pet,
            "total_attack": p_atk,
            "max_hp": p_hp,
            "active_effects": [],
            "skill_cooldowns": {},
            "equipped_skills": [],
        }
        init_battle_skill_state(skill_state)

        # Build equipped-skills display list for the frontend
        max_slots = get_max_skill_slots(pet)
        equipped_ids = skill_state.get("equipped_skills", [])
        equipped_skills_display: List[Any] = []
        for slot_idx in range(max_slots):
            sid = equipped_ids[slot_idx] if slot_idx < len(equipped_ids) else None
            sk = SKILL_BY_ID.get(sid) if sid else None
            if sk:
                equipped_skills_display.append({
                    "id": sid,
                    "name": sk["name"],
                    "description": sk["description"],
                    "element": sk.get("element", ""),
                    "unlocked": True,
                })
            else:
                equipped_skills_display.append(None)

        # Store skill state keyed by uid so arena_boss_action can retrieve it
        boss_skill_sessions[uid] = {
            "skill_state": skill_state,
            "p_charge_limit": p_charge_limit,
        }

        avg_atk += p_atk
        avg_def += p_def
        avg_hp  += p_hp

        player_badge_url = _arena_selected_badge_url(uid) or None

        player_states.append({
            "user_id":   uid,
            "username":  occ["username"],
            "name":      pet.get("name", occ["username"]),
            "species":   p_spec,
            "badge_url": player_badge_url,
            "element":   p_elem,
            "element2":  p_elem2 or "",
            "type":      p_type,
            "attack":    p_atk,
            "defense":   p_def,
            "max_hp":    p_hp,
            "cur_hp":    p_hp,
            "charge":    p_starting_charge,
            "charge_limit": p_charge_limit,
            "last_action": None,
            "alive":     True,
            "action_labels": action_labels,
            "pending_action": None,
            "relationship_multiplier": relationship_multipliers.get(uid, 1.0),
            "pet_data": pet,
            "equipped_skills": equipped_skills_display,
            "skill_cooldowns": {str(k): v for k, v in skill_state.get("skill_cooldowns", {}).items()},
        })

    n = len(room.occupants)
    avg_atk = avg_atk // n
    avg_def = avg_def // n
    avg_hp  = avg_hp  // n

    # Boss stats: massive HP (4× avg × player count), small attack & defense
    # Attack/defense are meaningful but not overwhelming — 4 players should need strategy
    boss_hp  = int(avg_hp  * 4.5 * n * random.uniform(0.9, 1.1))
    boss_atk = int(avg_atk * 0.55 * random.uniform(0.85, 1.15))   # ~55% of avg player attack
    boss_def = int(avg_def * 0.45 * random.uniform(0.85, 1.15))   # ~45% of avg player defense
    boss_atk = max(5, boss_atk)
    boss_def = max(3, boss_def)

    # Pick boss species, element, name
    boss_elements = list(DamageCalculator.ELEMENT_EFFECTIVENESS.keys())
    boss_elem = random.choice(boss_elements)
    boss_type = random.choice(["land", "flying", "swimming"])

    boss_species = ""
    try:
        from Systems.Functions.optimal_file_manager import OptimalFileManager
        _info = OptimalFileManager().get_data("info")
        _all_species = list(_info.get("Pets", {}).keys())
        if _all_species:
            boss_species = random.choice(_all_species)
    except Exception:
        boss_species = "Dragon"

    try:
        from Systems.Functions.optimal_file_manager import OptimalFileManager
        _base = OptimalFileManager().get_data("base")
        adj  = random.choice(_base.get("element_bases", {}).get(boss_elem, ["Ancient"]))
        noun = random.choice(_base.get("category_bases", {}).get(boss_type, ["Titan"]))
        boss_name = f"{adj} {noun} [BOSS]"
    except Exception:
        boss_name = f"{boss_elem.title()} Boss"

    boss_state = {
        "name":      boss_name,
        "species":   boss_species,
        "element":   boss_elem,
        "element2":  "",
        "type":      boss_type,
        "attack":    boss_atk,
        "defense":   boss_def,
        "max_hp":    boss_hp,
        "cur_hp":    boss_hp,
        "prev_hp":   boss_hp,
        "charge":    1.0,
        "last_action": None,
    }

    battle_state = {
        "room_id":      room_id,
        "turn":         0,
        "over":         False,
        "won":          None,
        "boss":         boss_state,
        "players":      player_states,
        "log":          [f"⚔️ Boss Battle begins! {n} heroes vs {boss_name}"],
        "pending_actions": {},   # user_id -> action
        "started_at":   time.time(),
        "skill_sessions": boss_skill_sessions,  # server-side skill state per player
    }
    _boss_battles[room_id] = battle_state

    room.state = "boss_battle"
    room.battle_log = [f"⚔️ Boss Battle: {boss_name} vs {n} heroes"]
    room.updated_at = time.time()
    for occ in room.occupants:
        occ["status"] = "battling"
    await _broadcast_rooms()

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("arena_boss_started", {"user_id": user_id, "room_id": room_id, "boss_name": boss_name, "player_count": n})
    await queue.flush()

    animation = AnimationComponent.for_battle_action(
        action="attack",
        damage=0,
        is_player=True,
        element_mult=1.0,
        effect="boss_spawn"
    )

    return JSONResponse({"success": True, "battle": battle_state, "animation": animation})


@router.get("/arena/battle/boss/state")
async def arena_boss_state(request: Request, room_id: int):
    """Return current boss battle state for a room."""
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    if room_id not in _boss_battles:
        raise HTTPException(status_code=404, detail="No boss battle in this room")
    return JSONResponse({"battle": _boss_battles[room_id]})


@router.post("/arena/battle/boss/action")
async def arena_boss_action(request: Request, data: Dict[str, Any] = Body(...)):
    """
    Submit a player's action for the current boss turn.
    Also specify which pet to defend (defend_target: user_id of the player to protect).
    Players always attack the boss. Defense target is who they shield.
    Once ALL alive players have submitted, the turn resolves automatically.
    """
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    user_id  = str(user["id"])
    room_id  = int(data.get("room_id", 0))
    action   = (data.get("action") or "attack").lower()
    defend_target = str(data.get("defend_target") or user_id)  # who to shield

    if action not in ("attack", "defend", "charge", "skill"):
        action = "attack"

    if room_id not in _boss_battles:
        raise HTTPException(status_code=404, detail="No boss battle in this room")

    battle = _boss_battles[room_id]
    if battle["over"]:
        return JSONResponse({"battle": battle, "resolved": False})

    # Find this player in the battle
    player = next((p for p in battle["players"] if p["user_id"] == user_id), None)
    if not player:
        raise HTTPException(status_code=400, detail="You are not in this battle")
    if not player["alive"]:
        return JSONResponse({"battle": battle, "resolved": False, "error": "You are eliminated"})

    # Record action
    slot_index = int(data.get("slot_index", 0))
    battle["pending_actions"][user_id] = {
        "action": action,
        "slot_index": slot_index,
        "defend_target": defend_target,
    }

    # ── NPC players auto-submit random actions ────────────────────────────────
    alive_players = [p for p in battle["players"] if p["alive"]]
    for p in alive_players:
        npc_uid = p["user_id"]
        if npc_uid.startswith("npc_") and npc_uid not in battle["pending_actions"]:
            # Pick a weighted random action: mostly attack/charge, rarely defend
            npc_act = random.choices(
                ["attack", "charge", "defend"],
                weights=[60, 25, 15],
                k=1,
            )[0]
            # NPC defends itself (only self-targeting makes sense for NPCs)
            battle["pending_actions"][npc_uid] = {
                "action": npc_act,
                "defend_target": npc_uid,
            }

    all_submitted = all(p["user_id"] in battle["pending_actions"] for p in alive_players)

    if not all_submitted:
        # Not everyone has acted yet — return current state
        submitted_count = len(battle["pending_actions"])
        return JSONResponse({
            "battle": battle,
            "resolved": False,
            "waiting_for": len(alive_players) - submitted_count,
        })

    # ── All players submitted — resolve the turn ──────────────────────────────
    from Systems.Pets.Logic.pet_brain import DamageCalculator, NPCBrain, LootCalculator
    from Systems.Pets.Logic.battle_skills import (
        apply_skill, tick_battle_effects,
        is_stunned, consume_stun,
        get_atk_multiplier, get_def_multiplier, get_damage_reduction,
        absorb_damage_through_shield, get_reflect_value,
        can_use_skill, SKILL_BY_ID, SKILL_COOLDOWN_TURNS,
    )

    battle["turn"] += 1
    turn_log: List[str] = [f"━━━ Turn {battle['turn']} ━━━"]

    # Retrieve the server-side skill sessions for this battle
    skill_sessions: Dict[str, Any] = battle.get("skill_sessions", {})

    # ── Tick active effects (DoT/HoT/stun/shield/buff/debuff) for all players ──
    # Also decrement per-slot skill cooldowns (done inside tick_battle_effects)
    for p in battle["players"]:
        if not p["alive"]:
            continue
        uid = p["user_id"]
        ss = skill_sessions.get(uid, {}).get("skill_state")
        if not ss:
            continue
        # Sync current HP/ATK into skill state so heal caps and DoT scale correctly
        ss["max_hp"] = p["max_hp"]
        ss["total_attack"] = p["attack"]
        # Tick effects (DoT, HoT, shields expire, buff/debuff expire)
        net_delta, tick_lines = tick_battle_effects(ss, p["attack"])
        if net_delta != 0:
            p["cur_hp"] = max(0, min(p["max_hp"], p["cur_hp"] + net_delta))
        for line in tick_lines:
            turn_log.append(f"  {line}")
        # Sync updated cooldowns back to the player state so the frontend sees them
        p["skill_cooldowns"] = {str(k): v for k, v in ss.get("skill_cooldowns", {}).items()}

    boss = battle["boss"]

    # ── Boss AI decides action ────────────────────────────────────────────────
    npc_brain = NPCBrain()
    monster_state = {
        "hp":              boss["cur_hp"],
        "max_hp":          boss["max_hp"],
        "prev_hp":         boss.get("prev_hp", boss["cur_hp"]),
        "charge_multiplier": boss["charge"],
        "last_action":     boss["last_action"],
        "attack_stat":     float(boss["attack"]),
        "defense_stat":    float(boss["defense"]),
        "seed":            battle["turn"],
    }
    players_for_brain = [
        {"alive": p["alive"], "hp": p["cur_hp"], "max_hp": p["max_hp"],
         "charging": battle["pending_actions"].get(p["user_id"], {}).get("action") == "charge"}
        for p in battle["players"]
    ]
    boss_decision = npc_brain.decide_action(monster_state, players_for_brain)
    boss_action   = boss_decision["action"]
    boss_strategy = boss_decision.get("strategy", "spread")

    # ── Boss charge accumulation ──────────────────────────────────────────────
    boss["prev_hp"] = boss["cur_hp"]
    if boss_action == "charge":
        boss["charge"] = DamageCalculator.get_next_charge_multiplier(boss["charge"])
        turn_log.append(f"⚡ {boss['name']} charges up! (x{boss['charge']:.0f})")
    elif boss_action == "defend":
        turn_log.append(f"🛡️ {boss['name']} braces for impact!")

    # ── Players attack boss ───────────────────────────────────────────────────
    total_player_dmg = 0
    total_parry_to_boss = 0

    for player in alive_players:
        uid = player["user_id"]
        p_action_data = battle["pending_actions"].get(uid, {"action": "attack", "defend_target": uid})
        p_action = p_action_data["action"]

        # ── Stun check: stunned players are forced to defend ──────────────────
        ss_for_stun = skill_sessions.get(uid, {}).get("skill_state")
        if ss_for_stun and is_stunned(ss_for_stun):
            consume_stun(ss_for_stun)
            p_action = "defend"
            turn_log.append(f"💫 {player['name']} is stunned and cannot act!")

        # Charge accumulation for player — pass pet_data so charge_limit_bonus applies
        if p_action == "charge":
            p_pet_data = skill_sessions.get(uid, {}).get("skill_state", {}).get("pet")
            player["charge"] = DamageCalculator.get_next_charge_multiplier(player["charge"], p_pet_data)
            turn_log.append(f"⚡ {player['name']} charges up! (x{player['charge']:.0f})")
            player["last_action"] = "charge"
            continue

        # Player uses skill
        if p_action == "skill":
            slot_index = p_action_data.get("slot_index", 0)
            ss = skill_sessions.get(uid, {}).get("skill_state")
            skill_used = False
            if ss:
                equipped_ids = ss.get("equipped_skills", [])
                if slot_index < len(equipped_ids) and can_use_skill(ss, slot_index):
                    skill_id = equipped_ids[slot_index]
                    sk = SKILL_BY_ID.get(skill_id)
                    if sk:
                        sk_name = sk["name"]
                        turn_log.append(f"✨ {player['name']} uses {sk_name}!")
                        # Inject charge so charge_boost can read/update it
                        ss["charge"] = player.get("charge", 1.0)
                        ss["charge_limit"] = float(
                            skill_sessions.get(uid, {}).get("p_charge_limit", 5.0)
                        )
                        ss["max_charge_limit"] = ss["charge_limit"]
                        # Boss is the target — wrap its mutable HP in a proxy dict
                        boss_proxy: Dict[str, Any] = {
                            "element": boss.get("element", "basic"),
                            "active_effects": boss.setdefault("active_effects", []),
                            "max_hp": boss["max_hp"],
                            "total_attack": boss.get("attack", 1),
                        }
                        result = apply_skill(
                            skill_id,
                            ss,
                            boss_proxy,
                            battle_type="boss",
                            slot_index=slot_index,
                        )
                        if result["ok"]:
                            skill_hp_delta_p = result.get("hp_delta_user", 0)
                            skill_hp_delta_e = result.get("hp_delta_target", 0)
                            # Apply damage to boss
                            if skill_hp_delta_e < 0:
                                boss["cur_hp"] = max(0, boss["cur_hp"] + skill_hp_delta_e)
                                total_player_dmg += abs(skill_hp_delta_e)
                            # Apply heal/lifesteal to player
                            if skill_hp_delta_p > 0:
                                player["cur_hp"] = min(player["max_hp"], player["cur_hp"] + skill_hp_delta_p)
                            elif skill_hp_delta_p < 0:
                                player["cur_hp"] = max(0, player["cur_hp"] + skill_hp_delta_p)
                            # Sync charge_boost result
                            if "_charge_boost_result" in ss:
                                player["charge"] = float(ss.pop("_charge_boost_result"))
                            turn_log.append(f"  {result.get('message', sk_name + ' used!')}")
                            skill_used = True
                        else:
                            turn_log.append(f"  ❌ {result.get('message', 'Skill failed')}")
                        # Sync updated cooldowns to player state for frontend
                        player["skill_cooldowns"] = {
                            str(k): v for k, v in ss.get("skill_cooldowns", {}).items()
                        }
                    else:
                        turn_log.append(f"✨ {player['name']} tries to use a skill but nothing happens!")
                else:
                    turn_log.append(f"⏳ {player['name']}'s skill is on cooldown — attacking instead!")
                    p_action = "attack"
            else:
                turn_log.append(f"✨ {player['name']} tries to use a skill but nothing happens!")

            if not skill_used and p_action == "skill":
                # Fallthrough: skill failed/empty — treat as no-op
                player["charge"] = 1.0
                player["last_action"] = "skill"
                player["last_combat"] = {"action": "skill", "dmg_dealt": 0, "parry_dealt": 0}
                continue

            if skill_used:
                player["charge"] = 1.0
                player["last_action"] = "skill"
                player["last_combat"] = {"action": "skill", "dmg_dealt": abs(skill_hp_delta_e), "parry_dealt": 0}
                continue

        # Player attacks boss (always targets boss)
        if p_action in ("attack", "defend"):
            # Construct minimal boss pet_data for ability tree checks
            boss_pet_data: Dict[str, Any] = {
                "level": 1,
                "category": boss["type"],
                "element": boss["element"],
                "species": boss.get("species", ""),
            }
            player_pet_data = player.get("pet_data")
            # Apply ATK multiplier from active skill buffs/debuffs
            p_ss = skill_sessions.get(uid, {}).get("skill_state")
            effective_p_atk = int(player["attack"] * (get_atk_multiplier(p_ss) if p_ss else 1.0))
            p_result = DamageCalculator.calculate_battle_action(
                attacker_attack=effective_p_atk,
                target_defense=boss["defense"],
                charge_multiplier=player["charge"] if p_action == "attack" else 1.0,
                target_charge_multiplier=boss["charge"] if boss_action == "defend" else 1.0,
                attacker_action_type=p_action,
                target_action_type=boss_action,
                attacker_type=player["type"],
                attacker_element=player["element"],
                attacker_element2=player.get("element2") or None,
                defender_type=boss["type"],
                defender_element=boss["element"],
                attacker_species=player["species"],
                attacker_pet_data=player_pet_data,
                attacker_user_id=uid,
                battle_type="boss",
            )
            p_dmg   = p_result["final_damage"]
            p_parry = p_result["parry_damage"]  # boss defended → parry back at player
            
            # Apply relationship multiplier to damage
            relationship_mult = player.get("relationship_multiplier", 1.0)
            p_dmg = int(p_dmg * relationship_mult)
            p_parry = int(p_parry * relationship_mult)

            if p_action == "attack":
                if p_dmg > 0:
                    mult = p_result.get("type_element_bonus_mult_attack", 1.0)
                    eff  = " 🔥 Super effective!" if mult > 1.05 else (" 💨 Not very effective..." if mult < 0.95 else "")
                    ctag = f" [x{player['charge']:.0f}]" if player["charge"] > 1.0 else ""
                    rel_tag = f" [+{int((relationship_mult-1)*100)}%]" if relationship_mult > 1.0 else (f" [{int((relationship_mult-1)*100)}%]" if relationship_mult < 1.0 else "")
                    crit_tag = " ⚡CRITICAL!" if p_result.get("is_critical") else ""
                    turn_log.append(f"⚔️ {player['name']}{ctag}{crit_tag}{rel_tag} → {p_dmg} dmg to {boss['name']}{eff}")
                    total_player_dmg += p_dmg
                else:
                    turn_log.append(f"⚔️ {player['name']} attacks → blocked by {boss['name']}!")
            elif p_action == "defend":
                if p_parry > 0:
                    rel_tag = f" [+{int((relationship_mult-1)*100)}%]" if relationship_mult > 1.0 else (f" [{int((relationship_mult-1)*100)}%]" if relationship_mult < 1.0 else "")
                    turn_log.append(f"🛡️ {player['name']} defends and parries {p_parry} dmg{rel_tag} back at {boss['name']}!")
                    total_parry_to_boss += p_parry
                else:
                    turn_log.append(f"🛡️ {player['name']} defends.")

            # Reset charge after use
            player["charge"] = 1.0
            player["last_action"] = p_action

            # Store per-player combat result for frontend
            player["last_combat"] = {
                "action": p_action,
                "dmg_dealt": p_dmg,
                "parry_dealt": p_parry,
                "charge_used": p_result.get("charge_used", False),
                "attack_roll": p_result.get("attack_roll"),
                "defense_roll": p_result.get("defense_roll"),
                "attack_result": p_result.get("attack_result", ""),
                "defense_result": p_result.get("defense_result", ""),
                "type_elem_mult": round(p_result.get("type_element_bonus_mult_attack", 1.0), 2),
                "is_critical": p_result.get("is_critical", False),
                "critical_multiplier": p_result.get("critical_multiplier", 1.0),
            }

    # Apply player damage to boss
    if boss_action != "charge":
        boss["cur_hp"] = max(0, boss["cur_hp"] - total_player_dmg - total_parry_to_boss)

    # Reset boss charge after attack/defend
    if boss_action in ("attack", "defend"):
        boss_charge_used = boss["charge"]
        boss["charge"] = 1.0
    else:
        boss_charge_used = 1.0

    boss["last_action"] = boss_action

    # ── Boss attacks players ──────────────────────────────────────────────────
    if boss_action == "attack" and boss["cur_hp"] > 0:
        # Build defense map for all alive players
        player_defenses: Dict[str, Any] = {}
        for player in alive_players:
            uid = player["user_id"]
            p_action_data = battle["pending_actions"].get(uid, {"action": "attack", "defend_target": uid})
            p_action = p_action_data["action"]
            defend_tgt = p_action_data.get("defend_target", uid)

            # A player who chose "defend" protects their defend_target
            # The defend_target gets the defender's defense stat applied
            player_defenses[uid] = {
                "defense":          player["defense"],
                "charge_multiplier": player["charge"],
                "action":           p_action,
                "type":             player["type"],
                "element":          player["element"],
                "element2":         player.get("element2") or None,
                "species":          player["species"],
                "defending":        p_action == "defend",
                "charging":         p_action == "charge",
                "defend_target":    defend_tgt,
            }

        # Determine who the boss targets based on strategy
        if boss_strategy == "focus_weakest":
            target_player = min(alive_players, key=lambda p: p["cur_hp"] / max(1, p["max_hp"]))
        elif boss_strategy == "focus_strongest":
            target_player = max(alive_players, key=lambda p: p["cur_hp"] / max(1, p["max_hp"]))
        else:
            # Spread: pick random alive player
            target_player = random.choice(alive_players)

        target_uid = target_player["user_id"]

        # Check if any player is defending the target
        defender_for_target = None
        for uid, pd in player_defenses.items():
            if pd["action"] == "defend" and pd["defend_target"] == target_uid and uid != target_uid:
                defender_for_target = next((p for p in alive_players if p["user_id"] == uid), None)
                break

        # Resolve boss attack against the target (or their defender)
        effective_target = defender_for_target if defender_for_target else target_player
        eff_uid = effective_target["user_id"]
        eff_pd  = player_defenses[eff_uid]

        # Construct minimal boss pet_data for ability tree checks
        boss_pet_data: Dict[str, Any] = {
            "level": 1,
            "category": boss["type"],
            "element": boss["element"],
            "species": boss.get("species", ""),
        }
        eff_defender_pet_data = effective_target.get("pet_data")
        boss_result = DamageCalculator.calculate_battle_action(
            attacker_attack=boss["attack"],
            target_defense=int(effective_target["defense"] * (get_def_multiplier(skill_sessions.get(eff_uid, {}).get("skill_state")) if skill_sessions.get(eff_uid, {}).get("skill_state") else 1.0)),
            charge_multiplier=boss_charge_used,
            target_charge_multiplier=effective_target["charge"],
            attacker_action_type="attack",
            target_action_type=eff_pd["action"],
            attacker_type=boss["type"],
            attacker_element=boss["element"],
            defender_type=effective_target["type"],
            defender_element=effective_target["element"],
            defender_element2=effective_target.get("element2") or None,
            defender_species=effective_target["species"],
            attacker_pet_data=boss_pet_data,
            defender_pet_data=eff_defender_pet_data,
            defender_current_hp=effective_target["cur_hp"],
            defender_max_hp=effective_target["max_hp"],
            battle_type="boss",
        )
        boss_dmg   = boss_result["final_damage"]
        boss_parry = boss_result["parry_damage"]

        # Apply active skill effects on the effective target (damage reduction, shield, reflect)
        eff_ss = skill_sessions.get(eff_uid, {}).get("skill_state")
        if eff_ss and boss_dmg > 0:
            dr = get_damage_reduction(eff_ss)
            if dr > 0:
                boss_dmg = max(1, int(boss_dmg * (1.0 - dr)))
            boss_dmg, _absorbed, shield_log = absorb_damage_through_shield(eff_ss, boss_dmg)
            for sl in shield_log:
                turn_log.append(f"  {sl}")
            reflect_frac = get_reflect_value(eff_ss)
            if reflect_frac > 0 and boss_dmg > 0:
                reflect_dmg = max(1, int(boss_dmg * reflect_frac))
                boss["cur_hp"] = max(0, boss["cur_hp"] - reflect_dmg)
                turn_log.append(f"🪞 {effective_target['name']} reflects {reflect_dmg} damage back!")

        # Apply damage to the effective target
        boss_is_crit = boss_result.get("is_critical", False)
        if boss_dmg > 0:
            effective_target["cur_hp"] = max(0, effective_target["cur_hp"] - boss_dmg)
            ctag = f" [x{boss_charge_used:.0f}]" if boss_charge_used > 1.0 else ""
            crit_tag = " ⚡CRITICAL!" if boss_is_crit else ""
            if defender_for_target:
                turn_log.append(
                    f"💥 {boss['name']}{ctag}{crit_tag} targets {target_player['name']} "
                    f"but {effective_target['name']} intercepts → {boss_dmg} dmg!"
                )
            else:
                turn_log.append(f"💥 {boss['name']}{ctag}{crit_tag} attacks {effective_target['name']} → {boss_dmg} dmg!")
        elif eff_pd["action"] == "defend":
            turn_log.append(f"🛡️ {effective_target['name']} fully blocks {boss['name']}'s attack!")
        else:
            turn_log.append(f"💥 {boss['name']} attacks {effective_target['name']} → blocked!")

        # Parry damage back to boss
        if boss_parry > 0:
            boss["cur_hp"] = max(0, boss["cur_hp"] - boss_parry)
            turn_log.append(f"↩️ {effective_target['name']} parries {boss_parry} dmg back at {boss['name']}!")

        # Store boss combat result for frontend
        boss["last_combat"] = {
            "action": "attack",
            "target_uid": target_uid,
            "effective_target_uid": eff_uid,
            "intercepted": defender_for_target is not None,
            "dmg_dealt": boss_dmg,
            "parry_taken": boss_parry,
            "charge_used": boss_charge_used,
            "attack_roll": boss_result.get("attack_roll"),
            "defense_roll": boss_result.get("defense_roll"),
            "is_critical": boss_is_crit,
            "critical_multiplier": boss_result.get("critical_multiplier", 1.0),
        }

        # Mark eliminated players
        for player in battle["players"]:
            if player["alive"] and player["cur_hp"] <= 0:
                player["alive"] = False
                turn_log.append(f"💀 {player['name']} has been eliminated!")

    elif boss_action == "defend":
        boss["last_combat"] = {"action": "defend", "dmg_dealt": 0, "parry_taken": total_parry_to_boss}
    else:
        boss["last_combat"] = {"action": "charge", "dmg_dealt": 0, "parry_taken": 0}

    # ── Check win/loss conditions ─────────────────────────────────────────────
    alive_after = [p for p in battle["players"] if p["alive"]]
    boss_dead   = boss["cur_hp"] <= 0

    if boss_dead:
        battle["over"] = True
        battle["won"]  = True
        turn_log.append(f"🏆 {boss['name']} has been defeated! Heroes win!")
        # Award XP to all surviving players
        for player in battle["players"]:
            uid = player["user_id"]
            if uid.startswith("npc_"):
                continue
            try:
                pet = await user_data_manager.get_pet_data_async(uid)
                if pet:
                    xp_mult = 1.5 if player["alive"] else 0.5
                    xp = int(200 * xp_mult * len(battle["players"]))
                    await LootCalculator.apply_xp_change(int(uid), xp, "boss_battle")
                    player["xp_gained"] = xp
                    await user_data_manager.update_pet_battle_stats(
                        uid, "npc", wins=1 if player["alive"] else 0,
                        losses=0, xp_earned=xp, damage_dealt=0, damage_taken=0
                    )
                    # ── GPP: emit boss battle event via EventBus ─────────────
                    if player["alive"]:
                        queue = EventQueue()
                        queue.push("boss_battle_ended", {"user_id": uid, "won": True})
                        await queue.flush()
            except Exception as e:
                logger.error(f"Boss XP award error for {uid}: {e}")

    elif not alive_after:
        battle["over"] = True
        battle["won"]  = False
        turn_log.append(f"💀 All heroes have fallen! {boss['name']} wins!")

    # Append turn log
    battle["log"].extend(turn_log)
    if len(battle["log"]) > 300:
        battle["log"] = battle["log"][-300:]

    # Clear pending actions for next turn
    battle["pending_actions"] = {}

    # Update room broadcast log
    room = _rooms.get(room_id)
    if room:
        room.battle_log = turn_log[-6:]
        if battle["over"]:
            room.state = "empty"
            room.occupants = []
            _boss_battles.pop(room_id, None)
        room.updated_at = time.time()
        await _broadcast_rooms()

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("arena_boss_action", {"user_id": user_id, "room_id": room_id, "action": action, "turn": battle["turn"], "over": battle["over"]})
    await queue.flush()

    animation = AnimationComponent.for_battle_action(
        action=action,
        damage=total_player_dmg,
        is_player=True,
        element_mult=1.0,
        effect="boss_hit" if total_player_dmg > 0 else "boss_block"
    )

    return JSONResponse({"battle": battle, "resolved": True, "turn_log": turn_log, "animation": animation})


# ── Unified WebSocket endpoint (arena + casino in one feed) ───────────────────
# The unified manager lives here; casino_lobby_api imports and uses it too.

class UnifiedConnectionManager:
    def __init__(self):
        self._connections: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket):
        self._connections.discard(ws)

    async def broadcast(self, data: Any):
        msg = json.dumps(data)
        dead: Set[WebSocket] = set()
        for ws in list(self._connections):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._connections.discard(ws)


_unified_manager = UnifiedConnectionManager()


async def broadcast_unified():
    """Push both room sets to all unified WS clients. Called by both APIs."""
    from web.api.casino_lobby_api import _casino_rooms
    await _unified_manager.broadcast({
        "type":   "unified",
        "arena":  [r.to_dict() for r in _rooms.values()],
        "casino": [r.to_dict() for r in _casino_rooms.values()],
    })


@router.websocket("/ws/unified")
async def unified_ws(websocket: WebSocket):
    await _unified_manager.connect(websocket)
    from web.api.casino_lobby_api import _casino_rooms
    # Send current state immediately on connect
    await websocket.send_text(json.dumps({
        "type":   "unified",
        "arena":  [r.to_dict() for r in _rooms.values()],
        "casino": [r.to_dict() for r in _casino_rooms.values()],
    }))
    try:
        while True:
            msg = await websocket.receive_text()
            # Respond to ping with a fresh room snapshot
            if msg == "ping":
                from web.api.casino_lobby_api import _casino_rooms as _cr
                await websocket.send_text(json.dumps({
                    "type":   "unified",
                    "arena":  [r.to_dict() for r in _rooms.values()],
                    "casino": [r.to_dict() for r in _cr.values()],
                }))
    except WebSocketDisconnect:
        _unified_manager.disconnect(websocket)


# ── REST: Boss invite — list candidates ──────────────────────────────────────
@router.get("/arena/battle/boss/invite-candidates")
async def arena_boss_invite_candidates(request: Request, room_id: int):
    """
    Return a list of users (with pets) who can be invited to the boss room.
    Excludes: the requester, anyone already in the room, and anyone who is
    an enemy of ANY current room member (we check mutual enemy relationships).
    """
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    requester_id = str(user["id"])

    if room_id not in _rooms:
        raise HTTPException(status_code=400, detail="Invalid room")

    room = _rooms[room_id]
    room_member_ids = {o["user_id"] for o in room.occupants}

    # Collect all user IDs who have pets (pets_db helper)
    try:
        from Systems.Functions.pets_db import pets_db as _pets_db
        all_pet_user_ids: List[str] = await _pets_db.get_user_ids_with_pets()
    except Exception as e:
        logger.error(f"Could not load pet user IDs: {e}")
        all_pet_user_ids = []

    # Build set of enemy user IDs — anyone who is an enemy with ANY room member
    from Systems.Pets.PetGames.pvp_system import can_battle_boss_together
    enemy_set: set = set()
    try:
        from Systems.Functions.pets_db import pets_db as _pets_db
        for member_id in room_member_ids:
            # get_user_relationships returns {target_user_id: relationship_type}
            rels: Dict[str, str] = await _pets_db.get_user_relationships(member_id)
            for target_uid, rel_type in rels.items():
                if rel_type == "enemy":
                    enemy_set.add(str(target_uid))
        # Also check if any candidate has marked a room member as enemy (reverse direction)
        for candidate_id in all_pet_user_ids:
            if candidate_id in room_member_ids or candidate_id == requester_id:
                continue
            for member_id in room_member_ids:
                r1, r2 = await _pets_db.get_mutual_relationship(candidate_id, member_id)
                if r1 == "enemy" or r2 == "enemy":
                    enemy_set.add(candidate_id)
    except Exception as e:
        logger.warning(f"Relationship check error in invite-candidates: {e}")

    # Fetch Discord usernames for candidates via bot
    try:
        from Systems.Functions.web_server import get_bot_instance
        bot = get_bot_instance()
    except Exception:
        bot = None

    candidates = []
    for uid in all_pet_user_ids:
        # Skip room members, NPC IDs, enemies, and requester
        if uid in room_member_ids:
            continue
        if uid == requester_id:
            continue
        if uid in enemy_set:
            continue
        if uid.startswith("npc_"):
            continue

        # Fetch pet name
        try:
            pet = await user_data_manager.get_pet_data_async(uid)
            pet_name = pet.get("name", "Unknown") if pet else "Unknown"
            pet_level = int(pet.get("level", 1)) if pet else 1
        except Exception:
            pet_name = "Unknown"
            pet_level = 1

        # Fetch Discord username
        username = uid
        avatar_url = ""
        try:
            if bot:
                discord_user = bot.get_user(int(uid)) or await bot.fetch_user(int(uid))
                if discord_user:
                    username = discord_user.display_name or discord_user.name
                    avatar_hash = discord_user.avatar.key if discord_user.avatar else None
                    if avatar_hash:
                        from Systems.Functions.discord_utils import get_discord_avatar_url
                        avatar_url = get_discord_avatar_url(uid, avatar_hash, size=64)
        except Exception:
            pass

        candidates.append({
            "user_id":   uid,
            "username":  username,
            "avatar":    avatar_url,
            "pet_name":  pet_name,
            "pet_level": pet_level,
        })
        if len(candidates) >= 50:  # Cap at 50 to keep the payload small
            break

    return JSONResponse({"candidates": candidates})


# ── REST: Boss invite — send DM ───────────────────────────────────────────────
@router.post("/arena/battle/boss/invite")
async def arena_boss_invite(request: Request, data: Dict[str, Any] = Body(...)):
    """
    Send a Discord DM to `target_user_id` inviting them to join the boss room.
    Validates they are not an enemy of any current room member before sending.
    """
    import discord as _discord

    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    inviter_id    = str(user["id"])
    inviter_name  = user.get("username", "A player")
    target_id     = str(data.get("target_user_id", ""))
    room_id       = int(data.get("room_id", 0))

    if not target_id:
        raise HTTPException(status_code=400, detail="No target user specified")
    if room_id not in _rooms:
        raise HTTPException(status_code=400, detail="Invalid room")

    room = _rooms[room_id]
    if len(room.occupants) >= BOSS_MAX_PLAYERS:
        raise HTTPException(status_code=400, detail="Room is already full")

    # Enemy check: target must not be an enemy of any current member
    room_member_ids = [o["user_id"] for o in room.occupants]
    try:
        from Systems.Functions.pets_db import pets_db as _pets_db
        for member_id in room_member_ids:
            r1, r2 = await _pets_db.get_mutual_relationship(target_id, member_id)
            if r1 == "enemy" or r2 == "enemy":
                raise HTTPException(
                    status_code=400,
                    detail="Cannot invite — this player has an enemy relationship with someone in the room."
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Relationship check failed during invite: {e}")

    # Verify target has a pet
    target_pet = await user_data_manager.get_pet_data_async(target_id)
    if not target_pet:
        raise HTTPException(status_code=400, detail="That player doesn't have a pet yet.")

    # Send the DM
    try:
        from Systems.Functions.web_server import get_bot_instance
        bot = get_bot_instance()
        if not bot:
            raise HTTPException(status_code=503, detail="Bot is unavailable — cannot send DM.")

        target_discord = bot.get_user(int(target_id)) or await bot.fetch_user(int(target_id))
        if not target_discord:
            raise HTTPException(status_code=404, detail="Could not find that Discord user.")

        arena_url = f"https://reaper.qzz.io/Pages/arena.html"
        room_num  = room_id + 1

        embed = _discord.Embed(
            title="👹 Boss Battle Invitation!",
            description=(
                f"**{inviter_name}** is inviting you to join a Boss Battle!\n\n"
                f"🏟️ **Room:** #{room_num}\n"
                f"👥 **Players already waiting:** {len(room.occupants)} / {BOSS_MAX_PLAYERS}\n\n"
                f"Click the link below to join, then select **Boss** mode and join Room #{room_num}."
            ),
            color=0xFF6B35,
        )
        embed.add_field(
            name="⚔️ Join the battle",
            value=f"[Open Arena →]({arena_url})",
            inline=False,
        )
        embed.set_footer(text="Reaper Bot • Boss Arena")

        await target_discord.send(embed=embed)
    except _discord.Forbidden:
        raise HTTPException(
            status_code=400,
            detail="That player has DMs disabled — they cannot receive the invite."
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Boss invite DM error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to send invite: {e}")

    return JSONResponse({"success": True, "message": f"Invite sent to {target_discord.display_name}!"})


# ── REST: Boss — add NPC pet to room ─────────────────────────────────────────
@router.post("/arena/battle/boss/add_npc")
async def arena_boss_add_npc(request: Request, data: Dict[str, Any] = Body(...)):
    """
    Add an AI-controlled NPC pet to the boss waiting room.
    Stats are scaled to match the current room's average player stats so the
    NPC contributes meaningfully without distorting the boss difficulty.
    The NPC is added as a room occupant and auto-acts each turn in the battle.
    """
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    requester_id = str(user["id"])
    room_id      = int(data.get("room_id", 0))

    if room_id not in _rooms:
        raise HTTPException(status_code=400, detail="Invalid room")

    room = _rooms[room_id]
    if not room.has_user(requester_id):
        raise HTTPException(status_code=400, detail="You are not in this room")
    if room.state not in ("boss_waiting", "boss_battle"):
        raise HTTPException(status_code=400, detail="Room is not in boss waiting mode")
    if len(room.occupants) >= BOSS_MAX_PLAYERS:
        raise HTTPException(status_code=400, detail=f"Room is full ({BOSS_MAX_PLAYERS} max)")

    # Count how many NPC slots are already taken
    npc_count = sum(1 for o in room.occupants if o["user_id"].startswith("npc_"))
    npc_uid   = f"npc_{room_id}_{npc_count}"

    # ── Generate NPC pet stats scaled to room average ─────────────────────────
    from Systems.Pets.Logic.pet_brain import StatsCalculator, DamageCalculator
    from Systems.Functions.optimal_file_manager import OptimalFileManager

    total_atk, total_def, total_hp, human_count = 0, 0, 0, 0
    for occ in room.occupants:
        if occ["user_id"].startswith("npc_"):
            continue
        try:
            pet = await user_data_manager.get_pet_data_async(occ["user_id"])
            if pet:
                stats = StatsCalculator.calculate_pet_stats(pet)
                total_atk += int(stats.get("attack", 10))
                total_def += int(stats.get("defense", 5))
                total_hp  += int(stats.get("max_health", 500))
                human_count += 1
        except Exception:
            pass

    if human_count == 0:
        # Fallback defaults if no human stats available
        avg_atk, avg_def, avg_hp = 20, 10, 500
    else:
        avg_atk = total_atk // human_count
        avg_def = total_def // human_count
        avg_hp  = total_hp  // human_count

    # NPC stats: 85-115% of human avg with small random variance
    npc_atk = max(5,  int(avg_atk * random.uniform(0.85, 1.15)))
    npc_def = max(3,  int(avg_def * random.uniform(0.85, 1.15)))
    npc_hp  = max(50, int(avg_hp  * random.uniform(0.90, 1.10)))

    # Pick random element and type
    all_elements = list(DamageCalculator.ELEMENT_EFFECTIVENESS.keys())
    all_types    = ["land", "flying", "swimming"]
    npc_element  = random.choice(all_elements)
    npc_type     = random.choice(all_types)

    # Pick random species from info.json
    npc_species = ""
    npc_name    = f"AI Companion {npc_count + 1}"
    try:
        _ofm  = OptimalFileManager()
        _info = _ofm.get_data("info")
        _base = _ofm.get_data("base")
        species_list = list(_info.get("Pets", {}).keys())
        if species_list:
            npc_species = random.choice(species_list)
        adj  = random.choice(_base.get("element_bases", {}).get(npc_element, ["Brave"]))
        noun = random.choice(_base.get("category_bases", {}).get(npc_type, ["Companion"]))
        npc_name = f"{adj} {noun}"
    except Exception:
        pass

    # Build a minimal pet_data dict the battle system can use
    # Compute average level from human occupants
    avg_level = 1
    try:
        level_sum, level_cnt = 0, 0
        for occ in room.occupants:
            if not occ["user_id"].startswith("npc_"):
                occ_pet = await user_data_manager.get_pet_data_async(occ["user_id"])
                if occ_pet:
                    level_sum += int(occ_pet.get("level", 1))
                    level_cnt += 1
        if level_cnt:
            avg_level = max(1, level_sum // level_cnt)
    except Exception:
        pass

    npc_pet_data: Dict[str, Any] = {
        "name":     npc_name,
        "species":  npc_species,
        "category": npc_type,
        "element":  npc_element,
        "element2": "",
        "level":    avg_level,
        "attack":    npc_atk,
        "defense":   npc_def,
        "max_health": npc_hp,
        "health":    npc_hp,
        "is_npc":    True,
    }

    action_labels = DamageCalculator.get_action_labels(npc_type, npc_element, npc_species)

    # Add NPC as a room occupant (no avatar — use element image)
    npc_occupant = {
        "user_id":      npc_uid,
        "username":     npc_name,
        "avatar":       f"/static/Emojis/Pets/Deco/{npc_element.title()}.png",
        "status":       "idle",
        "pet_name":     npc_name,
        "pet_species":  npc_species,
        "mode":         "boss",
        "is_npc":       True,
    }
    room.add_user(npc_occupant)
    room.updated_at = time.time()

    # If a battle is already live, inject the NPC into the battle state too
    if room_id in _boss_battles:
        battle = _boss_battles[room_id]
        npc_player_state: Dict[str, Any] = {
            "user_id":    npc_uid,
            "username":   npc_name,
            "name":       npc_name,
            "species":    npc_species,
            "badge_url":  None,
            "element":    npc_element,
            "element2":   "",
            "type":       npc_type,
            "attack":     npc_atk,
            "defense":    npc_def,
            "max_hp":     npc_hp,
            "cur_hp":     npc_hp,
            "charge":     1.0,
            "last_action": None,
            "alive":      True,
            "action_labels": action_labels,
            "pending_action": None,
            "relationship_multiplier": 1.0,
            "pet_data":   npc_pet_data,
            "is_npc":     True,
        }
        battle["players"].append(npc_player_state)

    await _broadcast_rooms()

    return JSONResponse({
        "success":    True,
        "npc_user_id": npc_uid,
        "npc_name":   npc_name,
        "npc_stats":  {"attack": npc_atk, "defense": npc_def, "hp": npc_hp},
        "element":    npc_element,
        "type":       npc_type,
        "species":    npc_species,
    })

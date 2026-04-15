"""
Arena API — manages live arena rooms, WebSocket broadcast, NPC battles, and PvP matchmaking.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Body, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from Systems.Functions.user_data_manager import user_data_manager

logger = logging.getLogger("arena_api")
router = APIRouter()

# ── Arena state ───────────────────────────────────────────────────────────────
# 12 rooms total
NUM_ROOMS = 12

class ArenaRoom:
    def __init__(self, room_id: int):
        self.room_id   = room_id
        self.occupants: List[Dict[str, Any]] = []   # [{user_id, username, avatar, status, pet_name, pet_species}]
        self.state     = "empty"   # empty | npc_battle | pvp_waiting | pvp_battle | spectating
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
    mode     = data.get("mode", "npc")   # "npc" | "pvp"

    if room_id not in _rooms:
        raise HTTPException(status_code=400, detail="Invalid room")

    room = _rooms[room_id]

    # Remove user from any OTHER room first (not the target room)
    for r in _rooms.values():
        if r.room_id != room_id and r.has_user(user_id):
            r.remove_user(user_id)

    if not room.is_empty() and room.state not in ("pvp_waiting",):
        raise HTTPException(status_code=400, detail="Room is occupied")

    pet = await user_data_manager.get_pet_data_async(user_id)
    avatar_hash = user.get("avatar") or ""
    avatar_url  = (
        f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png"
        if avatar_hash else
        f"https://cdn.discordapp.com/embed/avatars/{int(user_id) % 5}.png"
    )

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
    room.state = "pvp_waiting" if mode == "pvp" else "npc_battle"
    room.updated_at = time.time()

    await _broadcast_rooms()
    return JSONResponse({"success": True, "room_id": room_id})


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
    return JSONResponse({"success": True})


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

    return JSONResponse({**result, "log": log_lines})


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
    avatar_url  = (
        f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png"
        if avatar_hash else
        f"https://cdn.discordapp.com/embed/avatars/{int(user_id) % 5}.png"
    )
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

    return JSONResponse(result)


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

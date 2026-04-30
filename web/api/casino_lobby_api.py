"""
Casino Lobby API — room-based casino lobby with WebSocket broadcast.
Supports observers, seat-joining, and per-game multiplayer rules.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Body, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.pet_brain import LootCalculator

logger = logging.getLogger("casino_lobby_api")
router = APIRouter()

# ── Constants ─────────────────────────────────────────────────────────────────

NUM_CASINO_ROOMS = 12

GAME_INFO = {
    "slots":      {"label": "Slots",        "icon": "🎰", "max_players": 1,  "can_observe": True,  "can_bet_on": False, "can_join": False},
    "blackjack":  {"label": "Blackjack",    "icon": "🃏", "max_players": 6,  "can_observe": True,  "can_bet_on": False, "can_join": True},
    "craps":      {"label": "Craps",        "icon": "🎲", "max_players": 1,  "can_observe": True,  "can_bet_on": True,  "can_join": False},
    "holdem":     {"label": "Hold'em",      "icon": "♠️", "max_players": 6,  "can_observe": True,  "can_bet_on": False, "can_join": True},
    "races":      {"label": "Pet Races",    "icon": "🏁", "max_players": 4,  "can_observe": True,  "can_bet_on": True,  "can_join": True},
    "minigames":  {"label": "Mini-Games",   "icon": "🎮", "max_players": 2,  "can_observe": True,  "can_bet_on": True,  "can_join": True},
}

# ── Room model ────────────────────────────────────────────────────────────────

class CasinoRoom:
    def __init__(self, room_id: int):
        self.room_id    = room_id
        self.occupants: List[Dict[str, Any]] = []   # active players (seated)
        self.observers: List[Dict[str, Any]] = []   # watching only
        # state: empty | picking | playing | open
        self.state      = "empty"
        self.game       = None
        self.activity   = []
        self.updated_at = time.time()
        # Shared game state for multiplayer
        self.shared_state: Dict[str, Any] = {}
        # Observer bets: {user_id: {target_id: amount, ...}}
        self.observer_bets: Dict[str, Dict[str, int]] = {}
        # Pending seat requests (waiting for next round)
        self.pending_seats: List[Dict[str, Any]] = []
        # Craps: who is the roller
        self.craps_roller_id: Optional[str] = None
        # Race: pending racers waiting for next race
        self.pending_racers: List[Dict[str, Any]] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "room_id":       self.room_id,
            "state":         self.state,
            "game":          self.game,
            "occupants":     self.occupants,
            "observers":     self.observers,
            "activity":      self.activity[-6:],
            "updated_at":    self.updated_at,
            "shared_state":  self.shared_state,
            "observer_bets": self.observer_bets,
            "pending_seats": self.pending_seats,
            "craps_roller_id": self.craps_roller_id,
            "pending_racers": self.pending_racers,
        }

    def is_empty(self) -> bool:
        return len(self.occupants) == 0 and len(self.observers) == 0

    def has_user(self, user_id: str) -> bool:
        return (any(o["user_id"] == user_id for o in self.occupants) or
                any(o["user_id"] == user_id for o in self.observers))

    def is_player(self, user_id: str) -> bool:
        return any(o["user_id"] == user_id for o in self.occupants)

    def is_observer(self, user_id: str) -> bool:
        return any(o["user_id"] == user_id for o in self.observers)

    def remove_user(self, user_id: str):
        self.occupants = [o for o in self.occupants if o["user_id"] != user_id]
        self.observers = [o for o in self.observers if o["user_id"] != user_id]
        self.pending_seats = [o for o in self.pending_seats if o["user_id"] != user_id]
        self.pending_racers = [o for o in self.pending_racers if o["user_id"] != user_id]
        self.observer_bets.pop(user_id, None)
        if not self.occupants and not self.observers:
            self.state    = "empty"
            self.game     = None
            self.activity = []
            self.shared_state = {}
            self.observer_bets = {}
            self.pending_seats = []
            self.craps_roller_id = None
            self.pending_racers = []
        self.updated_at = time.time()

    def add_player(self, info: Dict[str, Any]):
        if not self.is_player(info["user_id"]):
            self.occupants.append(info)
        self.updated_at = time.time()

    def add_observer(self, info: Dict[str, Any]):
        if not self.is_observer(info["user_id"]):
            self.observers.append(info)
        self.updated_at = time.time()

    def add_activity(self, line: str):
        self.activity.append(line)
        if len(self.activity) > 20:
            self.activity = self.activity[-20:]
        self.updated_at = time.time()


_casino_rooms: Dict[int, CasinoRoom] = {i: CasinoRoom(i) for i in range(NUM_CASINO_ROOMS)}

# ── WebSocket manager ─────────────────────────────────────────────────────────

class CasinoConnectionManager:
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


_casino_manager = CasinoConnectionManager()


async def _broadcast_casino_rooms():
    await _casino_manager.broadcast({
        "type":  "rooms",
        "rooms": [r.to_dict() for r in _casino_rooms.values()],
    })
    try:
        from web.api.arena_api import broadcast_unified
        await broadcast_unified()
    except Exception:
        pass


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@router.websocket("/ws/casino")
async def casino_ws(websocket: WebSocket):
    await _casino_manager.connect(websocket)
    await websocket.send_text(json.dumps({
        "type":  "rooms",
        "rooms": [r.to_dict() for r in _casino_rooms.values()],
    }))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _casino_manager.disconnect(websocket)


# ── REST: get rooms ───────────────────────────────────────────────────────────

@router.get("/casino/lobby/rooms")
async def get_casino_rooms():
    return JSONResponse({"rooms": [r.to_dict() for r in _casino_rooms.values()]})


# ── REST: join a room as player ───────────────────────────────────────────────

@router.post("/casino/lobby/join")
async def casino_join(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    user_id  = str(user["id"])
    room_id  = int(data.get("room_id", 0))

    if room_id not in _casino_rooms:
        raise HTTPException(status_code=400, detail="Invalid room")

    room = _casino_rooms[room_id]

    # Leave any other room first
    for r in _casino_rooms.values():
        if r.room_id != room_id and r.has_user(user_id):
            r.remove_user(user_id)

    # Check capacity
    gi = GAME_INFO.get(room.game or "", {})
    max_p = gi.get("max_players", 1)
    if room.is_player(user_id):
        pass  # already seated
    elif room.state not in ("empty", "picking", "open") and len(room.occupants) >= max_p:
        raise HTTPException(status_code=400, detail="Room is full")

    pet = await user_data_manager.get_pet_data_async(user_id)
    avatar_hash = user.get("avatar") or ""
    
    from Systems.Functions.discord_utils import get_discord_avatar_url
    avatar_url = get_discord_avatar_url(user_id, avatar_hash, size=64)

    info = {
        "user_id":     user_id,
        "username":    user.get("username", "Unknown"),
        "avatar":      avatar_url,
        "status":      "picking",
        "pet_name":    pet.get("name", "No Pet") if pet else "No Pet",
        "pet_species": pet.get("species", "") if pet else "",
        "game":        room.game,
    }
    room.add_player(info)
    if room.state == "empty":
        room.state = "picking"
    room.add_activity(f"🚪 {user.get('username','?')} entered the room.")

    await _broadcast_casino_rooms()
    return JSONResponse({"success": True, "room_id": room_id})


# ── REST: observe a room (watch only) ────────────────────────────────────────

@router.post("/casino/lobby/observe")
async def casino_observe(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    user_id = str(user["id"])
    room_id = int(data.get("room_id", 0))

    if room_id not in _casino_rooms:
        raise HTTPException(status_code=400, detail="Invalid room")

    room = _casino_rooms[room_id]

    # Leave any other room first
    for r in _casino_rooms.values():
        if r.room_id != room_id and r.has_user(user_id):
            r.remove_user(user_id)

    if room.is_empty():
        raise HTTPException(status_code=400, detail="Room is empty")

    pet = await user_data_manager.get_pet_data_async(user_id)
    avatar_hash = user.get("avatar") or ""
    
    from Systems.Functions.discord_utils import get_discord_avatar_url
    avatar_url = get_discord_avatar_url(user_id, avatar_hash, size=64)

    info = {
        "user_id":     user_id,
        "username":    user.get("username", "Unknown"),
        "avatar":      avatar_url,
        "pet_name":    pet.get("name", "No Pet") if pet else "No Pet",
        "pet_species": pet.get("species", "") if pet else "",
    }
    room.add_observer(info)
    room.add_activity(f"👁️ {user.get('username','?')} is watching.")

    await _broadcast_casino_rooms()
    return JSONResponse({"success": True, "room_id": room_id, "room": room.to_dict()})


# ── REST: leave a room ────────────────────────────────────────────────────────

@router.post("/casino/lobby/leave")
async def casino_leave(request: Request):
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    user_id  = str(user["id"])
    username = user.get("username", "?")

    for r in _casino_rooms.values():
        if r.has_user(user_id):
            r.add_activity(f"🚶 {username} left the room.")
            r.remove_user(user_id)

    await _broadcast_casino_rooms()
    return JSONResponse({"success": True})


# ── REST: set game ────────────────────────────────────────────────────────────

@router.post("/casino/lobby/set_game")
async def casino_set_game(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    user_id  = str(user["id"])
    username = user.get("username", "?")
    game     = str(data.get("game", ""))

    if game not in GAME_INFO:
        raise HTTPException(status_code=400, detail="Unknown game")

    room = next((r for r in _casino_rooms.values() if r.is_player(user_id)), None)
    if not room:
        raise HTTPException(status_code=400, detail="You are not in a room")

    room.game  = game
    room.state = "playing"
    gi = GAME_INFO[game]

    if gi["max_players"] > 1 and len(room.occupants) < gi["max_players"]:
        room.state = "open"

    for occ in room.occupants:
        if occ["user_id"] == user_id:
            occ["game"]   = game
            occ["status"] = "playing"

    room.add_activity(f"{gi['icon']} {username} started {gi['label']}.")
    await _broadcast_casino_rooms()
    return JSONResponse({"success": True, "game": game})


# ── REST: request a seat (join next round) ────────────────────────────────────

@router.post("/casino/lobby/request_seat")
async def casino_request_seat(request: Request, data: Dict[str, Any] = Body(...)):
    """Observer requests to be seated at the table for the next round."""
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    user_id = str(user["id"])
    room_id = int(data.get("room_id", 0))

    if room_id not in _casino_rooms:
        raise HTTPException(status_code=400, detail="Invalid room")

    room = _casino_rooms[room_id]
    gi   = GAME_INFO.get(room.game or "", {})

    if not gi.get("can_join"):
        raise HTTPException(status_code=400, detail="This game does not support joining mid-session")

    if not room.is_observer(user_id):
        raise HTTPException(status_code=400, detail="You must be observing the room first")

    # Check if already pending
    if any(p["user_id"] == user_id for p in room.pending_seats):
        return JSONResponse({"success": True, "message": "Already queued for next round"})

    obs = next((o for o in room.observers if o["user_id"] == user_id), None)
    if obs:
        room.pending_seats.append(dict(obs))
        room.add_activity(f"🪑 {obs['username']} is waiting for the next round.")

    await _broadcast_casino_rooms()
    return JSONResponse({"success": True, "message": "You'll be seated at the next round"})


# ── REST: observer place bet on a player/racer ────────────────────────────────

@router.post("/casino/lobby/observer_bet")
async def casino_observer_bet(request: Request, data: Dict[str, Any] = Body(...)):
    """Observer places a side-bet on a player or racer in the room."""
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    user_id  = str(user["id"])
    room_id  = int(data.get("room_id", 0))
    target   = str(data.get("target_id", ""))   # user_id or racer id
    amount   = int(data.get("amount", 0))

    if room_id not in _casino_rooms:
        raise HTTPException(status_code=400, detail="Invalid room")

    room = _casino_rooms[room_id]
    gi   = GAME_INFO.get(room.game or "", {})

    if not gi.get("can_bet_on"):
        raise HTTPException(status_code=400, detail="This game does not support side-bets")

    if not room.has_user(user_id):
        raise HTTPException(status_code=400, detail="You must be in the room to bet")

    if amount < 10:
        raise HTTPException(status_code=400, detail="Minimum bet is 10 XP")

    # Deduct XP
    pet = await user_data_manager.get_pet_data_async(user_id)
    if not pet:
        raise HTTPException(status_code=404, detail="No pet found")

    from web.api.craps_api import _compute_total_xp
    total_xp = _compute_total_xp(pet)
    existing_bets = sum(room.observer_bets.get(user_id, {}).values())
    if amount > total_xp - existing_bets:
        raise HTTPException(status_code=400, detail="Insufficient XP")

    await LootCalculator.apply_xp_change(int(user_id), -amount, source="observer_bet")

    if user_id not in room.observer_bets:
        room.observer_bets[user_id] = {}
    room.observer_bets[user_id][target] = room.observer_bets[user_id].get(target, 0) + amount

    username = user.get("username", "?")
    room.add_activity(f"💰 {username} bet {amount} XP on {target}.")

    await _broadcast_casino_rooms()
    return JSONResponse({"success": True, "bets": room.observer_bets[user_id]})


# ── REST: settle observer bets (called by game logic after result) ─────────────

@router.post("/casino/lobby/settle_observer_bets")
async def settle_observer_bets(request: Request, data: Dict[str, Any] = Body(...)):
    """
    Called by game APIs after a result is determined.
    data: {room_id, winner_id, payout_mult (default 2.0)}
    """
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    room_id    = int(data.get("room_id", -1))
    winner_id  = str(data.get("winner_id", ""))
    payout_mult = float(data.get("payout_mult", 2.0))

    if room_id not in _casino_rooms:
        raise HTTPException(status_code=400, detail="Invalid room")

    room = _casino_rooms[room_id]
    results = []

    for bettor_id, bets in list(room.observer_bets.items()):
        for target_id, amount in bets.items():
            if target_id == winner_id:
                payout = int(amount * payout_mult)
                await LootCalculator.apply_xp_change(int(bettor_id), payout, source="observer_bet_win")
                results.append({"user_id": bettor_id, "won": payout})
                room.add_activity(f"🏆 Observer won {payout} XP on their bet!")
            # Losers already had XP deducted on placement

    room.observer_bets = {}
    await _broadcast_casino_rooms()
    return JSONResponse({"settled": results})


# ── REST: craps swap roller ───────────────────────────────────────────────────

@router.post("/casino/lobby/craps_swap_roller")
async def craps_swap_roller(request: Request, data: Dict[str, Any] = Body(...)):
    """Current roller picks a new roller from observers."""
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    user_id    = str(user["id"])
    room_id    = int(data.get("room_id", 0))
    new_roller = str(data.get("new_roller_id", ""))

    if room_id not in _casino_rooms:
        raise HTTPException(status_code=400, detail="Invalid room")

    room = _casino_rooms[room_id]

    if room.game != "craps":
        raise HTTPException(status_code=400, detail="Not a craps room")

    # Only the current roller (first occupant) can swap
    if not room.occupants or room.occupants[0]["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Only the current roller can swap")

    # New roller must be an observer
    new_obs = next((o for o in room.observers if o["user_id"] == new_roller), None)
    if not new_obs:
        raise HTTPException(status_code=400, detail="Target must be an observer in this room")

    # Move old roller to observers, new roller to occupants[0]
    old_roller = room.occupants[0]
    room.occupants = [dict(new_obs)] + room.occupants[1:]
    room.observers = [o for o in room.observers if o["user_id"] != new_roller]
    room.observers.append(old_roller)
    room.craps_roller_id = new_roller

    room.add_activity(f"🎲 {new_obs['username']} is now rolling!")
    await _broadcast_casino_rooms()
    return JSONResponse({"success": True, "new_roller": new_roller})


# ── REST: post activity line ──────────────────────────────────────────────────

@router.post("/casino/lobby/activity")
async def casino_activity(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    user_id = str(user["id"])
    line    = str(data.get("line", ""))[:120]

    room = next((r for r in _casino_rooms.values() if r.has_user(user_id)), None)
    if room and line:
        room.add_activity(line)
        await _broadcast_casino_rooms()

    return JSONResponse({"ok": True})


# ── REST: update shared state (game APIs push state for observers) ─────────────

@router.post("/casino/lobby/update_state")
async def casino_update_state(request: Request, data: Dict[str, Any] = Body(...)):
    """Game APIs call this to push shared game state to observers."""
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    user_id = str(user["id"])

    room = next((r for r in _casino_rooms.values() if r.is_player(user_id)), None)
    if not room:
        return JSONResponse({"ok": False})

    state_update = data.get("state", {})
    room.shared_state.update(state_update)
    room.updated_at = time.time()
    await _broadcast_casino_rooms()
    return JSONResponse({"ok": True})


# ── REST: get my room ─────────────────────────────────────────────────────────

@router.get("/casino/lobby/my_room")
async def casino_my_room(request: Request):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"room_id": None})
    user_id = str(user["id"])
    room = next((r for r in _casino_rooms.values() if r.has_user(user_id)), None)
    if not room:
        return JSONResponse({"room_id": None})
    return JSONResponse({"room_id": room.room_id, **room.to_dict()})


# ── REST: promote pending seat (called at start of new round) ─────────────────

@router.post("/casino/lobby/promote_pending")
async def casino_promote_pending(request: Request, data: Dict[str, Any] = Body(...)):
    """Move pending seat requests into active occupants for the next round."""
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    user_id = str(user["id"])

    room_id = int(data.get("room_id", -1))
    if room_id not in _casino_rooms:
        raise HTTPException(status_code=400, detail="Invalid room")

    room = _casino_rooms[room_id]
    gi   = GAME_INFO.get(room.game or "", {})
    max_p = gi.get("max_players", 1)

    promoted = []
    for pending in list(room.pending_seats):
        if len(room.occupants) >= max_p:
            break
        # Move from observers to occupants
        room.observers = [o for o in room.observers if o["user_id"] != pending["user_id"]]
        pending["status"] = "playing"
        pending["game"]   = room.game
        room.occupants.append(pending)
        promoted.append(pending["user_id"])
        room.add_activity(f"🪑 {pending['username']} joined the table!")

    room.pending_seats = [p for p in room.pending_seats if p["user_id"] not in promoted]
    await _broadcast_casino_rooms()
    return JSONResponse({"promoted": promoted})

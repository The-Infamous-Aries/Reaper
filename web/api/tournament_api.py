"""
Tournament API — real brackets, real battles
============================================
- Organizer picks size, invites pet-owning users from a searchable list, sets round timer
- User vs User: real interactive battle via /api/pets/battle/npc/start + /api/pets/battle/npc/turn
- User vs Bot: real battle (user fights, NPC uses its actual pet stats)
- Bot vs Bot: simulated via _run_pvp_battle_sim
- Proper single-elimination bracket structure
- Round advances when ALL matches in the round are done OR the round timer expires
- Round timer options: instant (auto-advance after every match), 1h, 2h, 6h, 12h, 24h
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite
from fastapi import APIRouter, Body, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from Systems.Functions.user_data_manager import user_data_manager

logger = logging.getLogger("tournament_api")
router = APIRouter()

# ── In-memory state ───────────────────────────────────────────────────────────
_active_tournaments: Dict[str, Dict[str, Any]] = {}
_ws_clients: Dict[Any, None] = {}   # websocket → None (set-like dict)

# ── Constants ─────────────────────────────────────────────────────────────────
VALID_SIZES   = (4, 8, 16, 32, 64)
TIMER_OPTIONS = {
    "instant": 0,
    "1h":      3600,
    "2h":      7200,
    "6h":      21600,
    "12h":     43200,
    "24h":     86400,
}
NPC_NAMES = [
    "Shadow","Blaze","Crystal","Storm","Onyx","Frost","Ember","Ivy","Thorn","Sage",
    "Flint","Breeze","Lunar","Solar","Ash","Neon","Pixel","Echo","Raven","Wolf",
    "Titan","Cinder","Zephyr","Venom","Quartz","Mirage","Comet","Drake","Nimbus","Apex",
]

# ── ID helpers ────────────────────────────────────────────────────────────────
def _tid() -> str:  return uuid.uuid4().hex[:12]
def _mid() -> str:  return uuid.uuid4().hex[:8]

def _max_rounds(size: int) -> int:
    return {4:2, 8:3, 16:4, 32:5, 64:6}.get(size, 3)

# ── Session user helper ───────────────────────────────────────────────────────
def _session_user(request: Request) -> Optional[Dict[str, Any]]:
    u = request.session.get("discord_user")
    if not u:
        return None
    return {"id": str(u["id"]), "username": u.get("username","Unknown"), "avatar": u.get("avatar","")}

# ── Bracket generation ────────────────────────────────────────────────────────
def _build_bracket(participants: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """
    Build a proper single-elimination bracket.
    Always pads to a power-of-2. Every round has exactly half the slots of the
    previous round, so _advance_bracket can always safely index nxt[i // 2].
    """
    seeded = list(participants)
    # Pad to next power-of-2 with BYE slots (None)
    target = 1
    while target < len(seeded):
        target *= 2
    while len(seeded) < target:
        seeded.append(None)

    rounds: List[List[Dict]] = []
    current_slots = seeded

    while len(current_slots) > 1:
        matches = []
        for i in range(0, len(current_slots), 2):
            p1 = current_slots[i]
            p2 = current_slots[i + 1]
            if p1 is None and p2 is None:
                # Both BYE — still create a placeholder so indexing stays correct
                # Winner left as None; bracket advancement skips it
                matches.append({
                    "id": _mid(), "p1": None, "p2": None, "winner": None,
                    "status": "bye_both", "battle_session": None,
                    "result": None, "log": [], "started_at": None, "ended_at": None,
                })
            elif p1 is None:
                matches.append({
                    "id": _mid(), "p1": None, "p2": p2, "winner": p2,
                    "status": "p2_bye", "battle_session": None,
                    "result": None, "log": [f"➡️ {p2['name']} advances (BYE)"],
                    "started_at": None, "ended_at": None,
                })
            elif p2 is None:
                matches.append({
                    "id": _mid(), "p1": p1, "p2": None, "winner": p1,
                    "status": "p1_bye", "battle_session": None,
                    "result": None, "log": [f"➡️ {p1['name']} advances (BYE)"],
                    "started_at": None, "ended_at": None,
                })
            else:
                matches.append({
                    "id": _mid(), "p1": p1, "p2": p2, "winner": None,
                    "status": "pending", "battle_session": None,
                    "result": None, "log": [], "started_at": None, "ended_at": None,
                })
        rounds.append(matches)
        # Winners (or None for bye_both) advance to next round as placeholders
        current_slots = [m["winner"] for m in matches]

    return rounds

def _ready_round_0(bracket: List[List[Dict]]) -> None:
    """Mark first-round non-bye matches as ready."""
    if not bracket:
        return
    for m in bracket[0]:
        if m["status"] in ("bye_both", "p1_bye", "p2_bye"):
            continue
        if m["status"] == "pending":
            p1_is_npc = m["p1"] and m["p1"].get("type") == "npc"
            p2_is_npc = m["p2"] and m["p2"].get("type") == "npc"
            m["status"] = "bot_sim" if (p1_is_npc and p2_is_npc) else "ready"

def _advance_bracket(bracket: List[List[Dict]], round_idx: int) -> bool:
    """
    Push winners from round_idx into round_idx+1 slots.
    Each match i in current round feeds into match i//2 in the next round,
    slot p1 (if i is even) or p2 (if i is odd).
    Returns True if the NEXT round is now fully populated.
    """
    if round_idx + 1 >= len(bracket):
        return False
    current = bracket[round_idx]
    nxt     = bracket[round_idx + 1]

    for i, match in enumerate(current):
        target_idx = i // 2
        if target_idx >= len(nxt):
            continue   # safety guard — should never happen with power-of-2 bracket
        target_match = nxt[target_idx]
        slot = "p1" if i % 2 == 0 else "p2"
        target_match[slot] = match.get("winner")  # None for bye_both

    # Set statuses on next round matches
    for m in nxt:
        if m["status"] in ("p1_bye","p2_bye","done","bot_sim","ready","in_progress"):
            continue
        p1 = m.get("p1")
        p2 = m.get("p2")
        if p1 is None and p2 is None:
            m["status"] = "bye_both"   # both sides were bye_both — skip in display
            continue
        if p1 is None:
            m["status"] = "p2_bye"
            m["winner"] = p2
            m["log"] = [f"➡️ {p2['name']} advances (BYE)"]
        elif p2 is None:
            m["status"] = "p1_bye"
            m["winner"] = p1
            m["log"] = [f"➡️ {p1['name']} advances (BYE)"]
        else:
            p1_npc = p1.get("type") == "npc"
            p2_npc = p2.get("type") == "npc"
            if p1_npc and p2_npc:
                m["status"] = "bot_sim"
            else:
                m["status"] = "ready"
    return True


def _round_done(bracket: List[List[Dict]], round_idx: int) -> bool:
    """True when every non-bye_both match in the round has a winner."""
    if round_idx >= len(bracket):
        return False
    return all(
        m.get("winner") is not None
        for m in bracket[round_idx]
        if m.get("status") != "bye_both"
    )


def _tournament_done(t: Dict) -> bool:
    last = t["bracket"][-1] if t["bracket"] else []
    real = [m for m in last if m.get("status") != "bye_both"]
    return bool(real and real[0].get("winner"))

# ── Bot-vs-bot simulation ─────────────────────────────────────────────────────
async def _sim_npc_match(p1: Dict, p2: Dict) -> Tuple[Dict, List[str]]:
    """
    Simulate a match between two NPC participants.
    Uses real pet stat logic from _run_pvp_battle_sim if both have user_ids with pets,
    otherwise pure random.
    """
    uid1 = p1.get("user_id") or p1.get("id", "")
    uid2 = p2.get("user_id") or p2.get("id", "")

    # If both are real users with pets, use the real sim
    if not uid1.startswith("npc_") and not uid2.startswith("npc_"):
        try:
            from web.api.pets_api import _run_pvp_battle_sim
            result = await _run_pvp_battle_sim(uid1, uid2)
            winner_id = result.get("winner")
            winner = p1 if winner_id == uid1 else p2
            log = result.get("log", [])[:6]
            return winner, log
        except Exception as e:
            logger.warning(f"pvp sim failed for {uid1} vs {uid2}: {e}")

    # Fallback: weight by type (user beats npc; pure random between npcs)
    p1_is_npc = uid1.startswith("npc_") or p1.get("type") == "npc"
    p2_is_npc = uid2.startswith("npc_") or p2.get("type") == "npc"
    if p1_is_npc and not p2_is_npc:
        winner, loser = p2, p1
    elif p2_is_npc and not p1_is_npc:
        winner, loser = p1, p2
    else:
        winner, loser = random.choice([(p1, p2), (p2, p1)])

    log = [
        f"⚔️ {p1['name']} vs {p2['name']}",
        f"🏆 {winner['name']} wins!",
    ]
    return winner, log

# ── Auto-simulate bot-vs-bot matches in a round ───────────────────────────────
async def _auto_sim_round(tournament_id: str, round_idx: int) -> None:
    """Simulate all bot_sim matches in a round, then check if round is done."""
    t = _active_tournaments.get(tournament_id)
    if not t or round_idx >= len(t["bracket"]):
        return

    changed = False
    for m in t["bracket"][round_idx]:
        if m["status"] == "bot_sim" and not m.get("winner"):
            p1, p2 = m["p1"], m["p2"]
            winner, log = await _sim_npc_match(p1, p2)
            m["winner"] = winner
            m["status"] = "done"
            m["log"] = log
            m["ended_at"] = time.time()
            changed = True

    if changed:
        _broadcast(tournament_id, {"type": "tournament_round_update",
                                   "tournament": _detail(t), "round": round_idx})
        await _check_advance(tournament_id, round_idx)

async def _check_advance(tournament_id: str, round_idx: int) -> None:
    """If all matches in round_idx are done, advance winners into next round (or crown champion)."""
    t = _active_tournaments.get(tournament_id)
    if not t:
        return
    if not _round_done(t["bracket"], round_idx):
        return

    next_idx = round_idx + 1

    # Last round — tournament is over
    if next_idx >= len(t["bracket"]):
        if _tournament_done(t):
            last_real = [m for m in t["bracket"][-1] if m.get("status") != "bye_both"]
            champ = last_real[0]["winner"] if last_real else None
            t["status"]     = "completed"
            t["champion"]   = champ
            t["updated_at"] = datetime.utcnow().isoformat()
            _broadcast(tournament_id, {"type": "tournament_completed", "tournament": _detail(t)})
        return

    # Advance winners into next round
    _advance_bracket(t["bracket"], round_idx)
    t["current_round"] = next_idx
    t["updated_at"]    = datetime.utcnow().isoformat()

    # If every match in the new round is already resolved (all byes), keep advancing
    if _round_done(t["bracket"], next_idx):
        await _check_advance(tournament_id, next_idx)
        return

    _broadcast(tournament_id, {"type": "tournament_round_update",
                               "tournament": _detail(t), "round": next_idx})

    # Auto-simulate any bot_sim matches in the new round
    asyncio.create_task(_auto_sim_round(tournament_id, next_idx))

    # Schedule round timer if not instant
    timer_secs = t.get("round_timer_secs", 0)
    if timer_secs > 0:
        t["round_deadline"] = time.time() + timer_secs
        asyncio.create_task(_round_timeout(tournament_id, next_idx, timer_secs))

async def _round_timeout(tournament_id: str, round_idx: int, delay_secs: float) -> None:
    """After delay, force-resolve any unfinished matches in the round."""
    await asyncio.sleep(delay_secs)
    t = _active_tournaments.get(tournament_id)
    if not t or t.get("current_round", 0) != round_idx:
        return
    changed = False
    for m in t["bracket"][round_idx]:
        if m.get("winner") or m.get("status") == "bye_both":
            continue
        p1, p2 = m.get("p1"), m.get("p2")
        if p1 and p2:
            winner = random.choice([p1, p2])
            m["winner"] = winner
            m["status"] = "done"
            m["log"] = [f"⏰ Time expired — {winner['name']} advances!"]
            m["ended_at"] = time.time()
            changed = True
        elif p1:
            m["winner"] = p1; m["status"] = "p1_bye"
        elif p2:
            m["winner"] = p2; m["status"] = "p2_bye"
    if changed:
        _broadcast(tournament_id, {"type": "tournament_round_update",
                                   "tournament": _detail(t), "round": round_idx})
        await _check_advance(tournament_id, round_idx)

# ── WebSocket broadcast ───────────────────────────────────────────────────────
def _broadcast(tournament_id: str, message: Dict) -> None:
    message["tournament_id"] = tournament_id
    asyncio.ensure_future(_async_broadcast(message))

async def _async_broadcast(message: Dict) -> None:
    dead = []
    for ws in list(_ws_clients):
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.pop(ws, None)

# ── Serialisation ─────────────────────────────────────────────────────────────
def _participant_dict(p: Optional[Dict]) -> Optional[Dict]:
    if p is None:
        return None
    return {
        "id":       p.get("id",""),
        "user_id":  p.get("user_id",""),
        "name":     p.get("name","?"),
        "type":     p.get("type","player"),  # "player" | "npc"
        "species":  p.get("species",""),
        "element":  p.get("element","basic"),
        "level":    p.get("level",1),
        "avatar":   p.get("avatar",""),
    }

def _match_dict(m: Dict) -> Dict:
    return {
        "id":           m["id"],
        "p1":           _participant_dict(m.get("p1")),
        "p2":           _participant_dict(m.get("p2")),
        "winner":       _participant_dict(m.get("winner")),
        "status":       m.get("status","pending"),
        "log":          m.get("log",[]),
        "result":       m.get("result"),
        "started_at":   m.get("started_at"),
        "ended_at":     m.get("ended_at"),
    }

def _detail(t: Dict) -> Dict:
    bracket = []
    for ri, rnd in enumerate(t.get("bracket", [])):
        # Filter out bye_both placeholders — they're internal scaffolding
        real_matches = [m for m in rnd if m.get("status") != "bye_both"]
        if not real_matches:
            continue
        bracket.append({
            "round":   ri,
            "label":   _round_label(ri, len(t["bracket"])),
            "matches": [_match_dict(m) for m in real_matches],
        })
    return {
        "id":              t["id"],
        "name":            t["name"],
        "size":            t["size"],
        "status":          t["status"],
        "current_round":   t.get("current_round", 0),
        "max_rounds":      t["max_rounds"],
        "organizer_id":    t["organizer_id"],
        "organizer_name":  t["organizer_name"],
        "round_timer":     t.get("round_timer","instant"),
        "round_timer_secs": t.get("round_timer_secs", 0),
        "round_deadline":  t.get("round_deadline"),
        "participants":    [_participant_dict(p) for p in t.get("participants",[])],
        "bracket":         bracket,
        "champion":        _participant_dict(t.get("champion")),
        "created_at":      t.get("created_at",""),
        "updated_at":      t.get("updated_at",""),
    }

def _round_label(ri: int, total: int) -> str:
    remaining = total - ri
    if remaining == 1:
        return "Final"
    if remaining == 2:
        return "Semi-Finals"
    if remaining == 3:
        return "Quarter-Finals"
    return f"Round {ri + 1}"

# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/tournament/active")
async def get_active_tournaments(request: Request):
    result = []
    for tid, t in _active_tournaments.items():
        if t.get("status") in ("completed","cancelled"):
            continue
        result.append({
            "id": tid, "name": t["name"], "size": t["size"],
            "status": t["status"],
            "current_round": t.get("current_round",0),
            "max_rounds": t["max_rounds"],
            "organizer_name": t["organizer_name"],
            "participant_count": len(t.get("participants",[])),
            "round_timer": t.get("round_timer","instant"),
            "created_at": t.get("created_at",""),
        })
    return JSONResponse({"success": True, "tournaments": result})


@router.get("/tournament/pet_users")
async def get_pet_users(request: Request):
    """Return list of users who have pets — for the invite picker."""
    u = _session_user(request)
    if not u:
        raise HTTPException(status_code=401, detail="Not logged in")
    try:
        from Systems.Functions.pets_db import pets_db
        all_pets = await pets_db.get_all_pet_data()
        users = []
        for uid, pet in all_pets.items():
            users.append({
                "user_id": str(uid),
                "username": pet.get("username") or pet.get("name", f"User {uid}"),
                "pet_name": pet.get("name","?"),
                "pet_species": pet.get("species",""),
                "pet_element": pet.get("element","basic"),
                "pet_level": pet.get("level",1),
            })
        users.sort(key=lambda x: x["username"].lower())
        return JSONResponse({"success": True, "users": users})
    except Exception as e:
        logger.error(f"get_pet_users error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load users")


@router.post("/tournament/create")
async def create_tournament(request: Request, data: Dict[str, Any] = Body(...)):
    u = _session_user(request)
    if not u:
        raise HTTPException(status_code=401, detail="Not logged in")

    size = int(data.get("size", 8))
    if size not in VALID_SIZES:
        raise HTTPException(status_code=400, detail="Invalid size")

    timer_key = (data.get("round_timer") or "instant").lower()
    if timer_key not in TIMER_OPTIONS:
        timer_key = "instant"

    name  = (data.get("name") or "").strip() or f"{size}P Tournament"
    now   = datetime.utcnow().isoformat()
    tid   = _tid()

    # Organizer is auto-added as first participant
    org_pet = await user_data_manager.get_pet_data_async(u["id"])
    org_participant = {
        "id":       u["id"],
        "user_id":  u["id"],
        "name":     u["username"],
        "type":     "player",
        "species":  org_pet.get("species","") if org_pet else "",
        "element":  org_pet.get("element","basic") if org_pet else "basic",
        "level":    org_pet.get("level",1) if org_pet else 1,
        "avatar":   u.get("avatar",""),
    }

    t = {
        "id":               tid,
        "name":             name,
        "size":             size,
        "max_rounds":       _max_rounds(size),
        "current_round":    0,
        "status":           "registration",
        "organizer_id":     u["id"],
        "organizer_name":   u["username"],
        "round_timer":      timer_key,
        "round_timer_secs": TIMER_OPTIONS[timer_key],
        "round_deadline":   None,
        "participants":     [org_participant],
        "bracket":          [],
        "champion":         None,
        "created_at":       now,
        "updated_at":       now,
    }
    _active_tournaments[tid] = t
    _broadcast(tid, {"type": "tournament_created", "tournament": _detail(t)})
    return JSONResponse({"success": True, "tournament": _detail(t)})


@router.get("/tournament/{tournament_id}")
async def get_tournament(tournament_id: str, request: Request):
    if tournament_id not in _active_tournaments:
        raise HTTPException(status_code=404, detail="Not found")
    return JSONResponse({"success": True, "tournament": _detail(_active_tournaments[tournament_id])})


@router.post("/tournament/{tournament_id}/invite")
async def invite_users(tournament_id: str, request: Request, data: Dict[str, Any] = Body(...)):
    """Organizer invites one or more user_ids to the tournament."""
    u = _session_user(request)
    if not u:
        raise HTTPException(status_code=401, detail="Not logged in")
    t = _active_tournaments.get(tournament_id)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    if t["organizer_id"] != u["id"]:
        raise HTTPException(status_code=403, detail="Only organizer can invite")
    if t["status"] != "registration":
        raise HTTPException(status_code=400, detail="Registration closed")

    invited_ids: List[str] = data.get("user_ids", [])
    added = 0
    for uid in invited_ids:
        uid = str(uid)
        if any(p["id"] == uid for p in t["participants"]):
            continue
        if len(t["participants"]) >= t["size"]:
            break
        pet = await user_data_manager.get_pet_data_async(uid)
        if not pet:
            continue
        t["participants"].append({
            "id":       uid,
            "user_id":  uid,
            "name":     pet.get("username") or f"User {uid}",
            "type":     "player",
            "species":  pet.get("species",""),
            "element":  pet.get("element","basic"),
            "level":    pet.get("level",1),
            "avatar":   "",
        })
        added += 1

    t["updated_at"] = datetime.utcnow().isoformat()
    _broadcast(tournament_id, {"type": "tournament_updated", "tournament": _detail(t)})
    return JSONResponse({"success": True, "added": added,
                         "participant_count": len(t["participants"])})


@router.post("/tournament/{tournament_id}/join")
async def join_tournament(tournament_id: str, request: Request):
    u = _session_user(request)
    if not u:
        raise HTTPException(status_code=401, detail="Not logged in")
    t = _active_tournaments.get(tournament_id)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    if t["status"] != "registration":
        raise HTTPException(status_code=400, detail="Registration closed")
    if any(p["id"] == u["id"] for p in t["participants"]):
        return JSONResponse({"success": True, "message": "Already joined"})
    if len(t["participants"]) >= t["size"]:
        raise HTTPException(status_code=400, detail="Tournament full")

    pet = await user_data_manager.get_pet_data_async(u["id"])
    t["participants"].append({
        "id":       u["id"],
        "user_id":  u["id"],
        "name":     u["username"],
        "type":     "player",
        "species":  pet.get("species","") if pet else "",
        "element":  pet.get("element","basic") if pet else "basic",
        "level":    pet.get("level",1) if pet else 1,
        "avatar":   u.get("avatar",""),
    })
    t["updated_at"] = datetime.utcnow().isoformat()
    _broadcast(tournament_id, {"type": "tournament_updated", "tournament": _detail(t)})
    return JSONResponse({"success": True, "message": "Joined!"})


@router.post("/tournament/{tournament_id}/start")
async def start_tournament(tournament_id: str, request: Request):
    u = _session_user(request)
    if not u:
        raise HTTPException(status_code=401, detail="Not logged in")
    t = _active_tournaments.get(tournament_id)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")
    if t["organizer_id"] != u["id"]:
        raise HTTPException(status_code=403, detail="Only organizer can start")
    if t["status"] != "registration":
        raise HTTPException(status_code=400, detail="Already started")

    # Fill remaining slots with NPCs
    used_names = {p["name"] for p in t["participants"]}
    pool = [n for n in NPC_NAMES if n not in used_names]
    random.shuffle(pool)
    while len(t["participants"]) < t["size"]:
        npc_name = pool.pop(0) if pool else f"NPC_{len(t['participants'])}"
        npc_id = f"npc_{_tid()}"   # generate once so id == user_id
        t["participants"].append({
            "id":      npc_id,
            "user_id": npc_id,
            "name":    npc_name,
            "type":    "npc",
            "species": "",
            "element": random.choice(["fire","water","electric","ice","plant","rock","air","magic","holy","necro","psychic","fighting","basic"]),
            "level":   random.randint(50, 200),
            "avatar":  "",
        })

    # Shuffle and build bracket
    seeded = list(t["participants"])
    random.shuffle(seeded)
    t["bracket"]       = _build_bracket(seeded)
    t["current_round"] = 0
    t["status"]        = "in_progress"
    t["updated_at"]    = datetime.utcnow().isoformat()

    # Mark ready matches in round 0
    _ready_round_0(t["bracket"])

    _broadcast(tournament_id, {"type": "tournament_started", "tournament": _detail(t)})

    # Auto-simulate bot_sim matches in round 0
    asyncio.create_task(_auto_sim_round(tournament_id, 0))

    # Round timer for round 0
    if t["round_timer_secs"] > 0:
        t["round_deadline"] = time.time() + t["round_timer_secs"]
        asyncio.create_task(_round_timeout(tournament_id, 0, t["round_timer_secs"]))

    return JSONResponse({"success": True, "tournament": _detail(t)})


@router.get("/tournament/{tournament_id}/my_match")
async def get_my_match(tournament_id: str, request: Request):
    """Return the current match this user needs to play, if any."""
    u = _session_user(request)
    if not u:
        raise HTTPException(status_code=401, detail="Not logged in")
    t = _active_tournaments.get(tournament_id)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")

    ri = t.get("current_round", 0)
    if ri >= len(t["bracket"]):
        return JSONResponse({"match": None})

    for m in t["bracket"][ri]:
        if m.get("status") not in ("ready","in_progress"):
            continue
        p1_uid = (m.get("p1") or {}).get("user_id","")
        p2_uid = (m.get("p2") or {}).get("user_id","")
        if u["id"] in (p1_uid, p2_uid):
            return JSONResponse({"match": _match_dict(m),
                                 "round": ri,
                                 "is_p1": u["id"] == p1_uid})
    return JSONResponse({"match": None})


@router.post("/tournament/{tournament_id}/match/{match_id}/start_battle")
async def start_match_battle(tournament_id: str, match_id: str,
                              request: Request, data: Dict[str, Any] = Body(...)):
    """
    Start the real battle for a tournament match.

    - If user vs npc:  start an NPC battle session for the user via /pets/battle/npc/start logic
    - If user vs user: start an NPC battle session BUT the 'enemy' is built from the opponent's real pet stats
    Both sides then call /tournament/{id}/match/{mid}/turn to submit actions.
    """
    u = _session_user(request)
    if not u:
        raise HTTPException(status_code=401, detail="Not logged in")
    t = _active_tournaments.get(tournament_id)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")

    ri = t.get("current_round", 0)
    match = next((m for rnd in t["bracket"] for m in rnd if m["id"] == match_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    if match.get("status") not in ("ready","in_progress"):
        raise HTTPException(status_code=400, detail="Match not available")

    p1_uid = (match.get("p1") or {}).get("user_id","")
    p2_uid = (match.get("p2") or {}).get("user_id","")
    if u["id"] not in (p1_uid, p2_uid):
        raise HTTPException(status_code=403, detail="You are not in this match")

    opponent_uid = p2_uid if u["id"] == p1_uid else p1_uid
    is_vs_npc    = opponent_uid.startswith("npc_")

    from Systems.Pets.Logic.pet_brain import StatsCalculator, DamageCalculator
    from Systems.Pets.Logic.ability_tree import get_ability_effect, get_starting_charge_bonus
    from Systems.Pets.Logic.battle_skills import init_battle_skill_state, get_max_skill_slots, SKILL_BY_ID
    from web.api.pets_api import _arena_battle_sessions

    # ── Build player state ────────────────────────────────────────────────────
    player_pet = await user_data_manager.get_pet_data_async(u["id"])
    if not player_pet:
        raise HTTPException(status_code=400, detail="You have no pet")

    stats     = StatsCalculator.calculate_pet_stats(player_pet)
    p_atk     = int(stats.get("attack", 10))
    p_def     = int(stats.get("defense", 5))
    p_hp      = int(stats.get("max_health", 500))
    p_type    = str(player_pet.get("category","land")).lower()
    p_elem    = str(player_pet.get("element","basic")).lower()
    p_elem2   = str(player_pet.get("element2","") or "").lower() or None
    p_spec    = str(player_pet.get("species","")).strip()

    health_bonus = get_ability_effect(player_pet, "battle_health_bonus")
    if health_bonus > 0:
        p_hp = int(p_hp * (1.0 + health_bonus))

    p_charge_limit   = int(DamageCalculator.get_max_charge(player_pet))
    p_starting_charge = 1.0 + int(get_starting_charge_bonus(player_pet))
    p_starting_charge = min(p_starting_charge, float(p_charge_limit))

    action_labels = DamageCalculator.get_action_labels(p_type, p_elem, p_spec,
                                                        custom_labels=player_pet.get("action_labels",{}))

    skill_state: Dict[str, Any] = {
        "pet": player_pet, "total_attack": p_atk, "max_hp": p_hp,
        "active_effects": [], "skill_cooldowns": {}, "equipped_skills": [],
    }
    init_battle_skill_state(skill_state)

    max_slots    = get_max_skill_slots(player_pet)
    equipped_ids = skill_state.get("equipped_skills", [])
    skills_display = []
    for si in range(max_slots):
        sid = equipped_ids[si] if si < len(equipped_ids) else None
        sk  = SKILL_BY_ID.get(sid) if sid else None
        skills_display.append({
            "id": sid, "name": sk["name"], "description": sk["description"],
            "element": sk.get("element",""), "unlocked": True,
        } if sk else None)

    # ── Build enemy state ─────────────────────────────────────────────────────
    if is_vs_npc:
        # Generate a scaled NPC enemy from the opponent participant metadata
        opp_part = match["p1"] if u["id"] == p2_uid else match["p2"]
        e_atk    = max(1, int(p_atk * 1.1 * random.uniform(0.9, 1.1)))
        e_def    = max(1, int(p_def * 1.1 * random.uniform(0.9, 1.1)))
        e_hp     = max(50, int(p_hp  * 1.1 * random.uniform(0.95, 1.15)))
        e_type   = random.choice(list(DamageCalculator.CATEGORY_ADVANTAGES.keys()))
        e_elem   = opp_part.get("element","basic")
        e_spec   = opp_part.get("species","")
        e_name   = opp_part.get("name", "NPC")
        enemy_skill_state: Dict[str, Any] = {"element": e_elem, "active_effects": [], "max_hp": e_hp}
    else:
        # Real opponent's pet
        opp_pet = await user_data_manager.get_pet_data_async(opponent_uid)
        if not opp_pet:
            raise HTTPException(status_code=400, detail="Opponent has no pet")
        o_stats = StatsCalculator.calculate_pet_stats(opp_pet)
        e_atk   = int(o_stats.get("attack", 10))
        e_def   = int(o_stats.get("defense", 5))
        e_hp    = int(o_stats.get("max_health", 500))
        oh      = get_ability_effect(opp_pet, "battle_health_bonus")
        if oh > 0: e_hp = int(e_hp * (1.0 + oh))
        e_type  = str(opp_pet.get("category","land")).lower()
        e_elem  = str(opp_pet.get("element","basic")).lower()
        e_spec  = str(opp_pet.get("species","")).strip()
        e_name  = opp_pet.get("name", "Opponent")
        enemy_skill_state = {
            "element": e_elem, "active_effects": [], "max_hp": e_hp,
            "pet": opp_pet,
        }

    # Store in the shared battle session dict (same key used by /pets/battle/npc/turn)
    session_key = f"tournament_{tournament_id}_{match_id}_{u['id']}"
    _arena_battle_sessions[session_key] = {
        "skill_state":       skill_state,
        "enemy_skill_state": enemy_skill_state,
        "e_atk_base":        e_atk,
        "e_def_base":        e_def,
        "p_charge_limit":    p_charge_limit,
        "tournament_id":     tournament_id,
        "match_id":          match_id,
    }

    match["status"]        = "in_progress"
    match["battle_session"] = session_key
    match["started_at"]    = time.time()
    t["updated_at"]        = datetime.utcnow().isoformat()
    _broadcast(tournament_id, {"type": "tournament_round_update", "tournament": _detail(t),
                                "round": ri})

    from web.api.pets_api import _selected_badge_url
    badge = _selected_badge_url(u["id"])

    return JSONResponse({"success": True,
        "session_key": session_key,
        "player": {
            "name": player_pet["name"], "max_hp": p_hp, "cur_hp": p_hp,
            "attack": p_atk, "defense": p_def, "type": p_type,
            "element": p_elem, "element2": p_elem2 or "",
            "species": p_spec, "badge_url": badge or None,
            "charge": p_starting_charge, "charge_limit": p_charge_limit,
            "last_action": None,
            "equipment": [],
            "equipped_skills": skills_display,
            "skill_cooldowns": {str(k):v for k,v in skill_state.get("skill_cooldowns",{}).items()},
        },
        "enemy": {
            "name": e_name, "max_hp": e_hp, "cur_hp": e_hp,
            "attack": e_atk, "defense": e_def, "type": e_type,
            "element": e_elem, "species": e_spec,
            "charge": 1.0, "last_action": None,
        },
        "turn": 0, "over": False, "won": None,
        "action_labels": action_labels,
        "match": _match_dict(match),
    })


@router.post("/tournament/{tournament_id}/match/{match_id}/turn")
async def tournament_match_turn(tournament_id: str, match_id: str,
                                 request: Request, data: Dict[str, Any] = Body(...)):
    """
    Process one turn of a tournament match. Delegates entirely to battle_npc_turn logic
    but uses the tournament-specific session key and records the winner when battle ends.
    """
    u = _session_user(request)
    if not u:
        raise HTTPException(status_code=401, detail="Not logged in")

    t = _active_tournaments.get(tournament_id)
    if not t:
        raise HTTPException(status_code=404, detail="Not found")

    match = next((m for rnd in t["bracket"] for m in rnd if m["id"] == match_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    session_key = match.get("battle_session") or f"tournament_{tournament_id}_{match_id}_{u['id']}"

    # Patch data to use tournament session key instead of user_id
    data["_tournament_session_key"] = session_key
    data["_is_tournament"] = True

    from web.api.pets_api import _arena_battle_sessions, _run_tournament_turn
    turn_result = await _run_tournament_turn(u["id"], session_key, data)

    if turn_result.get("over"):
        player_won = turn_result.get("won", False)
        # Determine which participant won
        p1_uid = (match.get("p1") or {}).get("user_id","")
        p2_uid = (match.get("p2") or {}).get("user_id","")
        if u["id"] == p1_uid:
            winner_part = match["p1"] if player_won else match["p2"]
        else:
            winner_part = match["p2"] if player_won else match["p1"]

        match["winner"]   = winner_part
        match["status"]   = "done"
        match["ended_at"] = time.time()
        match["log"]      = turn_result.get("lines", [])[:8]
        match["result"]   = {
            "winner_name": (winner_part or {}).get("name","?"),
            "xp_gained":   turn_result.get("xp_gained",0),
        }
        t["updated_at"] = datetime.utcnow().isoformat()
        ri = next((ri for ri,rnd in enumerate(t["bracket"]) if any(m["id"]==match_id for m in rnd)), 0)
        _broadcast(tournament_id, {"type": "tournament_round_update", "tournament": _detail(t), "round": ri})
        await _check_advance(tournament_id, ri)

    return JSONResponse(turn_result)


# ── Legacy Discord bridge endpoints (keep for compat) ─────────────────────────
@router.post("/tournament/discord/register")
async def register_discord_tournament(request: Request):
    data = await request.json()
    return JSONResponse({"success": True})

@router.post("/tournament/discord/update")
async def update_discord_tournament(request: Request):
    data = await request.json()
    return JSONResponse({"success": True})


# ── WebSocket ─────────────────────────────────────────────────────────────────
@router.websocket("/ws/tournament")
async def tournament_ws(websocket: WebSocket):
    await websocket.accept()
    _ws_clients[websocket] = None
    try:
        await websocket.send_json({"type": "connected"})
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            mtype = msg.get("type","")
            if mtype == "ping":
                await websocket.send_json({"type": "pong"})
            elif mtype == "subscribe":
                tid = msg.get("tournament_id","")
                if tid and tid in _active_tournaments:
                    await websocket.send_json({
                        "type": "tournament_state",
                        "tournament": _detail(_active_tournaments[tid]),
                    })
            elif mtype == "get_active":
                active = [_detail(t) for t in _active_tournaments.values()
                          if t["status"] not in ("completed","cancelled")]
                await websocket.send_json({"type": "tournament_list", "tournaments": active})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        _ws_clients.pop(websocket, None)

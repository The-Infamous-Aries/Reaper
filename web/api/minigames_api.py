"""
Casino Mini-Games API — Coin Flip & Rock Paper Scissors with XP gambling.
Reuses the existing /api/fun/coin-flip and /api/fun/rps logic but adds
session-based XP deduction/payout via LootCalculator.
"""
from __future__ import annotations
import random
import logging
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.requests import Request

from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.pet_brain import LootCalculator

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Shared data (mirrors web_server.py exactly) ───────────────────────────────

COIN_THEMES = {
    "Raider":    {"heads": "Pirate",  "tails": "Poop",   "heads_img": "/static/Emojis/Coins/Pirate.png",  "tails_img": "/static/Emojis/Coins/Poop.png"},
    "Time":      {"heads": "Future",  "tails": "Retro",  "heads_img": "/static/Emojis/Coins/Future.png",  "tails_img": "/static/Emojis/Coins/Retro.png"},
    "Battery":   {"heads": "Full",    "tails": "Empty",  "heads_img": "/static/Emojis/Coins/Full.png",    "tails_img": "/static/Emojis/Coins/Empty.png"},
    "Electric":  {"heads": "Plug",    "tails": "Socket", "heads_img": "/static/Emojis/Coins/Plug.png",    "tails_img": "/static/Emojis/Coins/Socket.png"},
    "Business":  {"heads": "Open",    "tails": "Close",  "heads_img": "/static/Emojis/Coins/Open.png",    "tails_img": "/static/Emojis/Coins/Close.png"},
    "Sky":       {"heads": "Day",     "tails": "Night",  "heads_img": "/static/Emojis/Coins/Day.png",     "tails_img": "/static/Emojis/Coins/Night.png"},
    "Tempature": {"heads": "Hot",     "tails": "Cold",   "heads_img": "/static/Emojis/Coins/Hot.png",     "tails_img": "/static/Emojis/Coins/Cold.png"},
}

RPS_THEMES = {
    "Traditional": {
        "rock_1":    {"name": "Rock",        "beats": "scissor",     "img": "/static/Emojis/RPS/rock_1.png"},
        "paper":     {"name": "Paper",       "beats": "rock_1",      "img": "/static/Emojis/RPS/paper.png"},
        "scissor":   {"name": "Scissors",    "beats": "paper",       "img": "/static/Emojis/RPS/scissor.png"},
    },
    "Fantasy": {
        "knights":      {"name": "Knight",      "beats": "necromancer", "img": "/static/Emojis/RPS/knights.png"},
        "archer":       {"name": "Archer",      "beats": "knights",     "img": "/static/Emojis/RPS/archer.png"},
        "necromancer":  {"name": "Necromancer", "beats": "archer",      "img": "/static/Emojis/RPS/necromancer.png"},
    },
    "War": {
        "tank": {"name": "Tank", "beats": "ship", "img": "/static/Emojis/RPS/tank.png"},
        "jet":  {"name": "Jet",  "beats": "tank", "img": "/static/Emojis/RPS/jet.png"},
        "ship": {"name": "Ship", "beats": "jet",  "img": "/static/Emojis/RPS/ship.png"},
    },
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _compute_total_xp(pet: dict) -> int:
    lvl = int(pet.get("level", 1))
    exp = int(pet.get("experience", 0))
    return int(LootCalculator.get_total_experience_for_level(lvl)) + exp

async def _deduct(user_id: str, amount: int) -> bool:
    pet = await user_data_manager.get_pet_data_async(user_id)
    if not pet:
        return False
    if amount > _compute_total_xp(pet):
        return False
    await LootCalculator.apply_xp_change(int(user_id), -amount, source="minigame_bet")
    return True

async def _payout(user_id: str, amount: int, source: str):
    await LootCalculator.apply_xp_change(int(user_id), amount, source=source)

# ── Coin Flip ─────────────────────────────────────────────────────────────────

@router.post("/casino/coinflip/flip")
async def coinflip(request: Request):
    """
    Flip a coin with optional XP bet.
    Body: {theme, pick: "heads"|"tails", bet: int, fun_mode: bool}
    """
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    try:
        body     = await request.json()
        theme    = str(body.get("theme", "Raider"))
        pick     = str(body.get("pick", "heads")).lower()
        bet      = int(body.get("bet", 0))
        fun_mode = bool(body.get("fun_mode", False))
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    if theme not in COIN_THEMES:
        return JSONResponse({"error": "Invalid theme"}, status_code=400)
    if pick not in ("heads", "tails"):
        return JSONResponse({"error": "Pick must be heads or tails"}, status_code=400)

    if not fun_mode:
        if bet < 10:
            return JSONResponse({"error": "Minimum bet is 10 XP"}, status_code=400)
        ok = await _deduct(user_id, bet)
        if not ok:
            return JSONResponse({"error": "Insufficient XP"}, status_code=400)

    # Flip
    result   = "heads" if random.random() < 0.5 else "tails"
    won      = (result == pick)
    td       = COIN_THEMES[theme]
    xp_change = 0

    if not fun_mode:
        if won:
            # Return bet + equal winnings (1:1)
            await _payout(user_id, bet * 2, "coinflip_win")
            xp_change = bet
        else:
            xp_change = -bet
        await user_data_manager.update_pet_gambling_stats(
            user_id, "coinflip", xp_change, bet_amount=bet
        )

    # Settle observer bets on this flip
    try:
        from web.api.casino_lobby_api import _casino_rooms, _broadcast_casino_rooms
        room = next((r for r in _casino_rooms.values() if r.is_player(user_id)), None)
        if room and room.observer_bets:
            for bettor_id, bets in list(room.observer_bets.items()):
                won_amount = bets.get(result, 0)
                if won_amount > 0:
                    await _payout(bettor_id, won_amount * 2, "observer_coinflip_win")
            room.observer_bets = {}
            await _broadcast_casino_rooms()
    except Exception:
        pass

    return JSONResponse({
        "result":     result,
        "won":        won,
        "pick":       pick,
        "heads_img":  td["heads_img"],
        "tails_img":  td["tails_img"],
        "result_img": td["heads_img"] if result == "heads" else td["tails_img"],
        "heads_name": td["heads"],
        "tails_name": td["tails"],
        "xp_change":  xp_change,
        "fun_mode":   fun_mode,
        "bet":        bet,
    })

# ── Rock Paper Scissors ───────────────────────────────────────────────────────

@router.post("/casino/rps/play")
async def rps_play(request: Request):
    """
    Play one round of RPS with optional XP bet.
    Body: {theme, choice: str, bet: int, fun_mode: bool}
    """
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    try:
        body     = await request.json()
        theme    = str(body.get("theme", "Traditional"))
        choice   = str(body.get("choice", ""))
        bet      = int(body.get("bet", 0))
        fun_mode = bool(body.get("fun_mode", False))
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    if theme not in RPS_THEMES:
        return JSONResponse({"error": "Invalid theme"}, status_code=400)
    theme_data = RPS_THEMES[theme]
    if choice not in theme_data:
        return JSONResponse({"error": f"Invalid choice for theme {theme}"}, status_code=400)

    if not fun_mode:
        if bet < 10:
            return JSONResponse({"error": "Minimum bet is 10 XP"}, status_code=400)
        ok = await _deduct(user_id, bet)
        if not ok:
            return JSONResponse({"error": "Insufficient XP"}, status_code=400)

    # AI picks
    ai_choice = random.choice(list(theme_data.keys()))

    # Determine result
    player_data = theme_data[choice]
    ai_data     = theme_data[ai_choice]

    if choice == ai_choice:
        result = "tie"
    elif player_data["beats"] == ai_choice:
        result = "win"
    else:
        result = "lose"

    xp_change = 0
    if not fun_mode:
        if result == "win":
            await _payout(user_id, bet * 2, "rps_win")
            xp_change = bet
        elif result == "tie":
            # Return bet on tie
            await _payout(user_id, bet, "rps_tie")
            xp_change = 0
        else:
            xp_change = -bet
        await user_data_manager.update_pet_gambling_stats(
            user_id, "rps", xp_change, bet_amount=bet
        )

    return JSONResponse({
        "result":       result,
        "player_choice": choice,
        "player_name":  player_data["name"],
        "player_img":   player_data["img"],
        "ai_choice":    ai_choice,
        "ai_name":      ai_data["name"],
        "ai_img":       ai_data["img"],
        "xp_change":    xp_change,
        "fun_mode":     fun_mode,
        "bet":          bet,
        "theme":        theme,
    })


# ── PvP Rock Paper Scissors ───────────────────────────────────────────────────
# Both players pay the wager; winner takes the pot.

_pvp_rps_rooms: Dict[str, dict] = {}  # room_id → {host, challenger, wager, theme, host_choice, challenger_choice}
import asyncio as _asyncio
_pvp_rps_lock = _asyncio.Lock()


@router.post("/casino/rps/pvp/challenge")
async def rps_pvp_challenge(request: Request):
    """
    Host creates a PvP RPS challenge in their casino room.
    Body: {room_id, wager, theme, fun_mode}
    """
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    try:
        body     = await request.json()
        room_id  = str(body.get("room_id", ""))
        wager    = int(body.get("wager", 0))
        theme    = str(body.get("theme", "Traditional"))
        fun_mode = bool(body.get("fun_mode", False))
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    if theme not in RPS_THEMES:
        return JSONResponse({"error": "Invalid theme"}, status_code=400)

    if not fun_mode and wager < 10:
        return JSONResponse({"error": "Minimum wager is 10 XP"}, status_code=400)

    if not fun_mode:
        ok = await _deduct(user_id, wager)
        if not ok:
            return JSONResponse({"error": "Insufficient XP"}, status_code=400)

    async with _pvp_rps_lock:
        _pvp_rps_rooms[room_id] = {
            "host":              user_id,
            "host_name":         user.get("username", "?"),
            "challenger":        None,
            "challenger_name":   None,
            "wager":             wager,
            "theme":             theme,
            "fun_mode":          fun_mode,
            "host_choice":       None,
            "challenger_choice": None,
            "state":             "waiting",  # waiting | choosing | done
        }

    return JSONResponse({"ok": True, "room_id": room_id})


@router.post("/casino/rps/pvp/accept")
async def rps_pvp_accept(request: Request):
    """Challenger accepts the PvP RPS challenge."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    try:
        body    = await request.json()
        room_id = str(body.get("room_id", ""))
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    async with _pvp_rps_lock:
        match = _pvp_rps_rooms.get(room_id)
        if not match:
            return JSONResponse({"error": "No challenge found"}, status_code=404)
        if match["challenger"]:
            return JSONResponse({"error": "Already accepted"}, status_code=400)
        if match["host"] == user_id:
            return JSONResponse({"error": "Cannot accept your own challenge"}, status_code=400)

        if not match["fun_mode"]:
            ok = await _deduct(user_id, match["wager"])
            if not ok:
                return JSONResponse({"error": "Insufficient XP"}, status_code=400)

        match["challenger"]      = user_id
        match["challenger_name"] = user.get("username", "?")
        match["state"]           = "choosing"

    return JSONResponse({"ok": True, "theme": match["theme"], "wager": match["wager"]})


@router.post("/casino/rps/pvp/choose")
async def rps_pvp_choose(request: Request):
    """Player submits their choice. When both have chosen, resolve."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    try:
        body    = await request.json()
        room_id = str(body.get("room_id", ""))
        choice  = str(body.get("choice", ""))
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    async with _pvp_rps_lock:
        match = _pvp_rps_rooms.get(room_id)
        if not match or match["state"] != "choosing":
            return JSONResponse({"error": "No active match"}, status_code=400)

        theme_data = RPS_THEMES.get(match["theme"], {})
        if choice not in theme_data:
            return JSONResponse({"error": "Invalid choice"}, status_code=400)

        if user_id == match["host"]:
            match["host_choice"] = choice
        elif user_id == match["challenger"]:
            match["challenger_choice"] = choice
        else:
            return JSONResponse({"error": "You are not in this match"}, status_code=400)

        # Both chosen — resolve
        if match["host_choice"] and match["challenger_choice"]:
            hc = match["host_choice"]
            cc = match["challenger_choice"]
            hd = theme_data[hc]
            cd = theme_data[cc]

            if hc == cc:
                result = "tie"
                winner_id = None
            elif hd["beats"] == cc:
                result = "host_wins"
                winner_id = match["host"]
            else:
                result = "challenger_wins"
                winner_id = match["challenger"]

            pot = match["wager"] * 2
            if not match["fun_mode"] and winner_id:
                await _payout(winner_id, pot, "rps_pvp_win")
            elif not match["fun_mode"] and result == "tie":
                # Refund both
                await _payout(match["host"],       match["wager"], "rps_pvp_tie")
                await _payout(match["challenger"],  match["wager"], "rps_pvp_tie")

            match["state"]     = "done"
            match["result"]    = result
            match["winner_id"] = winner_id
            match["pot"]       = pot

            # Settle observer bets
            try:
                from web.api.casino_lobby_api import _casino_rooms, _broadcast_casino_rooms
                lobby_room = _casino_rooms.get(int(room_id))
                if lobby_room and lobby_room.observer_bets and winner_id:
                    for bettor_id, bets in list(lobby_room.observer_bets.items()):
                        for target_id, amount in bets.items():
                            if target_id == winner_id:
                                await _payout(bettor_id, amount * 2, "observer_bet_win")
                    lobby_room.observer_bets = {}
                    await _broadcast_casino_rooms()
            except Exception:
                pass

            return JSONResponse({
                "resolved":          True,
                "result":            result,
                "winner_id":         winner_id,
                "host_choice":       hc,
                "challenger_choice": cc,
                "host_choice_name":  hd["name"],
                "challenger_choice_name": cd["name"],
                "pot":               pot,
                "fun_mode":          match["fun_mode"],
            })

    return JSONResponse({"resolved": False, "waiting": True})


@router.get("/casino/rps/pvp/state")
async def rps_pvp_state(request: Request):
    """Get current PvP RPS match state."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)

    room_id = request.query_params.get("room_id", "")
    match   = _pvp_rps_rooms.get(room_id)
    if not match:
        return JSONResponse({"active": False})

    return JSONResponse({"active": True, **{k: v for k, v in match.items() if k not in ("host_choice", "challenger_choice")}})


# ── Observer coin-flip betting ────────────────────────────────────────────────

@router.post("/casino/coinflip/observer_bet")
async def coinflip_observer_bet(request: Request):
    """
    Observer bets on the outcome of another user's coin flip.
    Body: {room_id, pick: heads|tails, amount, fun_mode}
    The bet is settled when the host flips via /casino/coinflip/flip.
    """
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    try:
        body     = await request.json()
        room_id  = int(body.get("room_id", -1))
        pick     = str(body.get("pick", "heads")).lower()
        amount   = int(body.get("amount", 0))
        fun_mode = bool(body.get("fun_mode", False))
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    if pick not in ("heads", "tails"):
        return JSONResponse({"error": "Pick must be heads or tails"}, status_code=400)

    if not fun_mode:
        if amount < 10:
            return JSONResponse({"error": "Minimum bet is 10 XP"}, status_code=400)
        ok = await _deduct(user_id, amount)
        if not ok:
            return JSONResponse({"error": "Insufficient XP"}, status_code=400)

    try:
        from web.api.casino_lobby_api import _casino_rooms, _broadcast_casino_rooms
        lobby_room = _casino_rooms.get(room_id)
        if lobby_room:
            if user_id not in lobby_room.observer_bets:
                lobby_room.observer_bets[user_id] = {}
            lobby_room.observer_bets[user_id][pick] = lobby_room.observer_bets[user_id].get(pick, 0) + amount
            lobby_room.add_activity(f"💰 {user.get('username','?')} bet {amount} XP on {pick}.")
            await _broadcast_casino_rooms()
    except Exception as e:
        logger.warning(f"coinflip_observer_bet lobby error: {e}")

    return JSONResponse({"ok": True, "pick": pick, "amount": amount})

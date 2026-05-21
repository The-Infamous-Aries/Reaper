"""
Web Craps API — stateless, session-backed.
Game state lives in request.session["craps_game"].
Mirrors CrapsSession / _resolve_bets logic from Systems/Pets/PetGames/craps.py exactly.
"""
from __future__ import annotations
import asyncio
import random
import logging
from typing import List, Optional, Dict, Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.requests import Request

from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.pet_brain import LootCalculator
from Systems.Pets.Logic.event_bus import EventQueue
from Systems.Pets.Logic.pet_components import AnimationComponent
from web.api.pets.gpp_helpers import _invalidate_stats_cache, _compute_total_xp, _get_user_lock

logger = logging.getLogger("craps_api")
router = APIRouter()

# ── Constants ─────────────────────────────────────────────────────────────────

DICE_COLORS = ["Red", "Orange", "Blue", "Yellow", "Pink", "Green", "Purple"]

BET_TYPES = [
    "Pass Line", "Don't Pass", "Field",
    "Place 4", "Place 5", "Place 6", "Place 8", "Place 9", "Place 10",
    "Any 7",
    "Hard 4", "Hard 6", "Hard 8", "Hard 10",
]

PLACE_PAYOUTS = {4: 9/5, 5: 7/5, 6: 7/6, 8: 7/6, 9: 7/5, 10: 9/5}
HARD_PAYOUTS  = {4: 7.0, 6: 9.0, 8: 9.0, 10: 7.0}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _dice_img(value: int, color: str) -> str:
    return f"/static/Emojis/Dice/{color}{value}.png"

def _get_game(session) -> Optional[dict]:
    return session.get("craps_game")

def _set_game(session, game: dict):
    session["craps_game"] = game

def _clear_game(session):
    session.pop("craps_game", None)

def _new_game(fun_mode: bool, dice_color: str) -> dict:
    return {
        "fun_mode":    fun_mode,
        "dice_color":  dice_color,   # e.g. "Red", "Random"
        "phase":       "come_out",   # "come_out" | "point"
        "point":       None,
        "last_d1":     0,
        "last_d2":     0,
        "last_color1": dice_color if dice_color != "Random" else "Red",
        "last_color2": dice_color if dice_color != "Random" else "Red",
        "bets":        [],           # [{type, amount}]
        "log":         [],           # list of result strings (newest first, max 8)
        "xp_balance":  0,            # refreshed from server on each roll
        "headline":    "Place your bets, then roll!",
        "event":       "",
    }

def _add_log(game: dict, msg: str):
    game["log"].insert(0, msg)
    if len(game["log"]) > 8:
        game["log"] = game["log"][:8]

def _game_response(game: dict) -> dict:
    return {
        "active":      True,
        "fun_mode":    game["fun_mode"],
        "dice_color":  game["dice_color"],
        "phase":       game["phase"],
        "point":       game["point"],
        "last_d1":     game["last_d1"],
        "last_d2":     game["last_d2"],
        "last_color1": game["last_color1"],
        "last_color2": game["last_color2"],
        "bets":        game["bets"],
        "log":         game["log"],
        "total_bet":   sum(b["amount"] for b in game["bets"]),
        "headline":    game.get("headline", "Place your bets, then roll!"),
        "event":       game.get("event", ""),
    }

# ── Resolve bets (mirrors _resolve_bets exactly) ──────────────────────────────

async def _resolve_bets(game: dict, roll: int, d1: int, d2: int,
                        event: str, user_id: str) -> dict:
    """
    event: come_out_win | come_out_loss | point_established |
           point_win | point_continue | seven_out
    Returns {xp_change, result_lines, kept_bets}
    """
    is_hard     = (d1 == d2)
    is_come_out = (event in ("come_out_win", "come_out_loss", "point_established"))

    kept_bets   = []
    won_total   = 0
    lost_total  = 0
    result_lines = []

    for bet in game["bets"]:
        btype      = bet["type"]
        amount     = bet["amount"]
        win        = False
        loss       = False
        stay_up    = False
        payout_ratio = 1.0

        # ── Pass Line ────────────────────────────────────────────────────────
        if btype == "Pass Line":
            if event == "come_out_win":   win  = True
            elif event == "come_out_loss": loss = True
            elif event == "point_win":    win  = True
            elif event == "seven_out":    loss = True

        # ── Don't Pass ───────────────────────────────────────────────────────
        elif btype == "Don't Pass":
            if event == "come_out_win":    loss = True
            elif event == "come_out_loss":
                if roll == 12: stay_up = True  # push on 12 — bet stays
                else:          win = True
            elif event == "point_win":     loss = True
            elif event == "seven_out":     win  = True

        # ── Field (always working) ────────────────────────────────────────────
        elif btype == "Field":
            if roll in (3, 4, 9, 10, 11):
                win = True
            elif roll in (2, 12):
                win = True
                payout_ratio = 2.0
            else:
                loss = True

        # ── Place bets (OFF on come-out) ──────────────────────────────────────
        elif btype.startswith("Place "):
            if not is_come_out:
                target = int(btype.split(" ")[1])
                if roll == target:
                    win = True
                    stay_up = True
                    payout_ratio = PLACE_PAYOUTS[target]
                elif roll == 7:
                    loss = True

        # ── Any 7 (always working) ────────────────────────────────────────────
        elif btype == "Any 7":
            if roll == 7:
                win = True
                payout_ratio = 4.0
            else:
                loss = True

        # ── Hardways (OFF on come-out) ────────────────────────────────────────
        elif btype.startswith("Hard "):
            if not is_come_out:
                target = int(btype.split(" ")[1])
                if roll == target and is_hard:
                    win = True
                    stay_up = True
                    payout_ratio = HARD_PAYOUTS[target]
                elif roll == 7 or (roll == target and not is_hard):
                    loss = True

        # ── Resolution ────────────────────────────────────────────────────────
        if win:
            profit = int(amount * payout_ratio)
            payout = profit if stay_up else (amount + profit)
            if not game["fun_mode"]:
                await LootCalculator.apply_xp_change(int(user_id), payout, source="craps_win")
            won_total += profit
            result_lines.append(f"✅ {btype}: +{profit} XP")
            if stay_up:
                kept_bets.append(bet)
        elif loss:
            lost_total += amount
            result_lines.append(f"❌ {btype}: -{amount} XP")
        else:
            kept_bets.append(bet)   # push or not yet resolved

    xp_change = won_total - lost_total if not game["fun_mode"] else 0
    return {
        "xp_change":    xp_change,
        "won_total":    won_total,
        "lost_total":   lost_total,
        "result_lines": result_lines,
        "kept_bets":    kept_bets,
    }

# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/casino/craps/start")
async def craps_start(request: Request):
    """Start a new craps session. Body: {fun_mode, dice_color}"""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)

    try:
        body       = await request.json()
        fun_mode   = bool(body.get("fun_mode", False))
        dice_color = str(body.get("dice_color", "Red"))
        if dice_color not in DICE_COLORS and dice_color != "Random":
            dice_color = "Red"
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    game = _new_game(fun_mode, dice_color)
    _set_game(request.session, game)

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("craps_start", {"user_id": str(user["id"]), "fun_mode": fun_mode, "dice_color": dice_color})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("dice_roll_start", 400)

    return JSONResponse(_game_response(game), animation=animation)


@router.post("/casino/craps/bet")
async def craps_bet(request: Request):
    """Place a bet. Body: {type: str, amount: int}"""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    game = _get_game(request.session)
    if not game:
        return JSONResponse({"error": "No active session"}, status_code=400)

    try:
        body   = await request.json()
        btype  = str(body.get("type", ""))
        amount = int(body.get("amount", 0))
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    if btype not in BET_TYPES:
        return JSONResponse({"error": f"Unknown bet type: {btype}"}, status_code=400)
    if amount < 10:
        return JSONResponse({"error": "Minimum bet is 10 XP"}, status_code=400)

    async with _get_user_lock(user_id):
        if not game["fun_mode"]:
            pet = await user_data_manager.get_pet_data_async(user_id)
            if not pet:
                return JSONResponse({"error": "No pet found"}, status_code=404)
            total_xp = _compute_total_xp(pet)
            current_bets = sum(b["amount"] for b in game["bets"])
            if amount > total_xp - current_bets:
                return JSONResponse({"error": "Insufficient XP"}, status_code=400)
            await LootCalculator.apply_xp_change(int(user_id), -amount, source="craps_bet")

        game["bets"].append({"type": btype, "amount": amount})
        _set_game(request.session, game)

        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("craps_bet", {"user_id": user_id, "type": btype, "amount": amount})
        await queue.flush()

        animation = AnimationComponent.for_ui_update("bet_place", 300)

        return JSONResponse(_game_response(game), animation=animation)


@router.post("/casino/craps/clear_bets")
async def craps_clear_bets(request: Request):
    """Refund all bets."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    game = _get_game(request.session)
    if not game:
        return JSONResponse({"error": "No active session"}, status_code=400)

    async with _get_user_lock(user_id):
        refund = sum(b["amount"] for b in game["bets"])
        if not game["fun_mode"] and refund > 0:
            await LootCalculator.apply_xp_change(int(user_id), refund, source="craps_refund")

        game["bets"] = []
        _set_game(request.session, game)
        resp = _game_response(game)
        resp["refunded"] = refund

        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("craps_clear_bets", {"user_id": user_id, "refund": refund})
        await queue.flush()

        animation = AnimationComponent.for_ui_update("bets_clear", 300)

        resp["animation"] = animation
        return JSONResponse(resp)


@router.post("/casino/craps/roll")
async def craps_roll(request: Request):
    """Roll the dice and resolve all bets."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    game = _get_game(request.session)
    if not game:
        return JSONResponse({"error": "No active session"}, status_code=400)

    async with _get_user_lock(user_id):
        return await _craps_roll_inner(game, request, user_id)


async def _craps_roll_inner(game: dict, request: Request, user_id: str):
    d1 = random.randint(1, 6)
    d2 = random.randint(1, 6)
    total = d1 + d2

    # Dice colors
    if game["dice_color"] == "Random":
        c1 = random.choice(DICE_COLORS)
        c2 = random.choice(DICE_COLORS)
    else:
        c1 = c2 = game["dice_color"]

    game["last_d1"]     = d1
    game["last_d2"]     = d2
    game["last_color1"] = c1
    game["last_color2"] = c2

    # Determine event
    phase = game["phase"]
    point = game["point"]
    event = ""
    headline = ""

    if phase == "come_out":
        if total in (7, 11):
            event    = "come_out_win"
            headline = f"🎉 Natural {total}! Pass Line Wins!"
        elif total in (2, 3, 12):
            event    = "come_out_loss"
            headline = f"💀 Craps {total}! Pass Line Loses!"
        else:
            event       = "point_established"
            game["point"] = total
            game["phase"] = "point"
            headline    = f"🎯 Point is {total}. Roll again!"
    else:  # point phase
        if total == point:
            event         = "point_win"
            game["point"] = None
            game["phase"] = "come_out"
            headline      = f"🏆 Hit the Point {total}! Pass Line Wins!"
        elif total == 7:
            event         = "seven_out"
            game["point"] = None
            game["phase"] = "come_out"
            headline      = f"💀 Seven Out! Pass Line Loses!"
        else:
            event    = "point_continue"
            headline = f"Rolled {total}. Point is still {point}."

    # Resolve bets
    resolution = await _resolve_bets(game, total, d1, d2, event, user_id)
    game["bets"] = resolution["kept_bets"]

    # Track gambling stats for this roll
    if not game["fun_mode"] and (resolution["won_total"] > 0 or resolution["lost_total"] > 0):
        net = resolution["won_total"] - resolution["lost_total"]
        total_wagered = resolution["won_total"] + resolution["lost_total"]
        await user_data_manager.update_pet_gambling_stats(
            user_id, "craps", net, bet_amount=total_wagered
        )

    # Settle observer bets on this roll result
    try:
        from web.api.casino_lobby_api import _casino_rooms, _broadcast_casino_rooms
        room = next((r for r in _casino_rooms.values() if r.is_player(user_id)), None)
        if room and room.observer_bets:
            # Observer bets are keyed by event name (e.g. "pass_line_win", "seven_out")
            # Simple model: observers bet on "pass" (pass line wins) or "dont_pass"
            pass_events   = {"come_out_win", "point_win"}
            nopass_events = {"come_out_loss", "seven_out"}
            for bettor_id, bets in list(room.observer_bets.items()):
                for target, amount in bets.items():
                    if target == "pass" and event in pass_events:
                        await LootCalculator.apply_xp_change(int(bettor_id), amount * 2, source="observer_craps_win")
                    elif target == "dont_pass" and event in nopass_events:
                        await LootCalculator.apply_xp_change(int(bettor_id), amount * 2, source="observer_craps_win")
                    # Losers already had XP deducted on placement
            # Only clear bets that resolved (pass/dont_pass settle on come_out and point events)
            if event in pass_events | nopass_events:
                room.observer_bets = {}
                await _broadcast_casino_rooms()
    except Exception:
        pass

    # Build log entry
    log_parts = [headline]
    log_parts.extend(resolution["result_lines"])
    if not game["fun_mode"] and resolution["xp_change"] != 0:
        sign = "+" if resolution["xp_change"] > 0 else ""
        log_parts.append(f"Net: {sign}{resolution['xp_change']} XP")
    _add_log(game, " · ".join(log_parts))

    # Persist headline and event so state endpoint can return them
    game["headline"] = headline
    game["event"]    = event

    _set_game(request.session, game)

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("craps_roll", {"user_id": user_id, "total": total, "d1": d1, "d2": d2, "event": event, "xp_change": resolution["xp_change"]})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("dice_roll", 500, {"d1": d1, "d2": d2, "total": total})

    resp = _game_response(game)
    resp["roll"]       = total
    resp["d1"]         = d1
    resp["d2"]         = d2
    resp["event"]      = event
    resp["headline"]   = headline
    resp["xp_change"]  = resolution["xp_change"]
    resp["result_lines"] = resolution["result_lines"]
    resp["animation"] = animation
    return JSONResponse(resp)


@router.get("/casino/craps/state")
async def craps_state(request: Request):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    game = _get_game(request.session)
    if not game:
        return JSONResponse({"active": False})
    resp = _game_response(game)
    resp["active"] = True
    return JSONResponse(resp)


@router.post("/casino/craps/quit")
async def craps_quit(request: Request):
    """Refund all bets and end session."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    game = _get_game(request.session)
    if game:
        refund = sum(b["amount"] for b in game["bets"])
        if not game["fun_mode"] and refund > 0:
            await LootCalculator.apply_xp_change(int(user_id), refund, source="craps_refund")
    _clear_game(request.session)

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("craps_quit", {"user_id": user_id, "refund": refund})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("game_quit", 300)

    return JSONResponse({"ok": True, "animation": animation})

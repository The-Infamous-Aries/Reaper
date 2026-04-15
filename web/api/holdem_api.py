"""
Web Texas Hold'em API — stateless, session-backed.
Full correct Texas Hold'em: blinds, burn cards, proper betting rounds,
showdown with get_hand_rank from ai_gambling.py.
"""
from __future__ import annotations
import asyncio
import random
import logging
from typing import List, Optional, Dict, Any, Tuple

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.requests import Request

from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.pet_brain import LootCalculator
from Systems.Functions.ai_gambling import get_hand_rank, get_holdem_bot_action

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Per-user locks ────────────────────────────────────────────────────────────
_user_locks: Dict[str, asyncio.Lock] = {}

def _get_user_lock(user_id: str) -> asyncio.Lock:
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    return _user_locks[user_id]

# ── Constants ─────────────────────────────────────────────────────────────────

RANKS  = ["2","3","4","5","6","7","8","9","10","J","Q","K","1"]
SUITS  = ["H","D","C","S"]
SMALL_BLIND = 25
BIG_BLIND   = 50
BOT_NAMES   = ["Ace","Blaze","Chip","Duke","Echo"]

HAND_NAMES = {
    8: "Straight Flush", 7: "Four of a Kind", 6: "Full House",
    5: "Flush", 4: "Straight", 3: "Three of a Kind",
    2: "Two Pair", 1: "One Pair", 0: "High Card"
}

# ── Deck ──────────────────────────────────────────────────────────────────────

def _fresh_deck() -> List[str]:
    deck = [f"{s}{r}" for s in SUITS for r in RANKS]
    random.shuffle(deck)
    return deck

def _card_img(code: str) -> str:
    return f"/static/Emojis/Cards/{code}.png"

def _serialize_cards(codes: List[str], hidden: bool = False) -> List[dict]:
    if hidden:
        return [{"code": "back", "img": "/static/Emojis/Cards/BJ.png", "hidden": True}
                for _ in codes]
    return [{"code": c, "img": _card_img(c), "hidden": False} for c in codes]

# ── Session helpers ───────────────────────────────────────────────────────────

def _get_game(session) -> Optional[dict]:
    return session.get("holdem_game")

def _set_game(session, game: dict):
    session["holdem_game"] = game

def _clear_game(session):
    session.pop("holdem_game", None)

def _compute_total_xp(pet: dict) -> int:
    lvl = int(pet.get("level", 1))
    exp = int(pet.get("experience", 0))
    return int(LootCalculator.get_total_experience_for_level(lvl)) + exp

# ── Game factory ──────────────────────────────────────────────────────────────

def _new_game(buy_in: int, fun_mode: bool, num_bots: int) -> dict:
    """
    seats: list of {id, name, is_bot, hole, folded, left, stack, round_bet, acted}
    seat 0 = human player
    """
    seats = []
    # Human
    seats.append({
        "id": "player", "name": "You", "is_bot": False,
        "hole": [], "folded": False, "left": False,
        "stack": buy_in, "round_bet": 0, "acted": False
    })
    # Bots
    for i in range(min(num_bots, 4)):
        seats.append({
            "id": f"bot_{i}", "name": BOT_NAMES[i], "is_bot": True,
            "hole": [], "folded": False, "left": False,
            "stack": buy_in, "round_bet": 0, "acted": False
        })

    return {
        "fun_mode":   fun_mode,
        "buy_in":     buy_in,
        "seats":      seats,
        "deck":       _fresh_deck(),
        "community":  [],
        "pot":        0,
        "stage":      "idle",      # idle|preflop|flop|turn|river|showdown
        "dealer_idx": 0,
        "action_idx": 0,           # index into seats of whose turn it is
        "current_bet": 0,          # highest bet this round
        "last_raiser": -1,         # seat index of last aggressor
        "log":        [],
        "result":     None,        # set at showdown
        "hand_num":   0,
    }

def _add_log(game: dict, msg: str):
    game["log"].insert(0, msg)
    if len(game["log"]) > 20:
        game["log"] = game["log"][:20]

# ── Serialise for client ──────────────────────────────────────────────────────

def _game_response(game: dict, player_seat: int = 0) -> dict:
    stage   = game["stage"]
    seats_out = []
    for i, s in enumerate(game["seats"]):
        is_player = (i == player_seat)
        show_hole = (
            is_player
            or stage == "showdown"
            or (stage not in ("idle","preflop","flop","turn","river") )
        )
        seats_out.append({
            "id":        s["id"],
            "name":      s["name"],
            "is_bot":    s["is_bot"],
            "hole":      _serialize_cards(s["hole"], hidden=(not show_hole and not s["folded"])),
            "hole_count": len(s["hole"]),
            "folded":    s["folded"],
            "left":      s["left"],
            "stack":     s["stack"],
            "round_bet": s["round_bet"],
            "acted":     s["acted"],
            "is_active_turn": (i == game["action_idx"] and stage not in ("idle","showdown")),
        })

    # Community cards — reveal progressively
    comm = game["community"]
    if stage == "preflop":
        comm_out = []
    elif stage == "flop":
        comm_out = _serialize_cards(comm[:3])
    elif stage == "turn":
        comm_out = _serialize_cards(comm[:4])
    else:
        comm_out = _serialize_cards(comm)

    # Player's valid actions
    actions = _valid_actions(game, player_seat)

    return {
        "stage":        stage,
        "pot":          game["pot"],
        "current_bet":  game["current_bet"],
        "community":    comm_out,
        "seats":        seats_out,
        "action_idx":   game["action_idx"],
        "player_seat":  player_seat,
        "actions":      actions,
        "log":          game["log"],
        "result":       game["result"],
        "hand_num":     game["hand_num"],
        "fun_mode":     game["fun_mode"],
        "dealer_idx":   game["dealer_idx"],
    }

def _valid_actions(game: dict, seat_idx: int) -> List[str]:
    if game["stage"] in ("idle", "showdown"):
        return []
    if game["action_idx"] != seat_idx:
        return []
    s = game["seats"][seat_idx]
    if s["folded"] or s["left"]:
        return []
    to_call = game["current_bet"] - s["round_bet"]
    actions = ["fold"]
    if to_call == 0:
        actions.append("check")
    else:
        actions.append("call")
    if s["stack"] > to_call:
        actions.append("raise")
    return actions

# ── Betting helpers ───────────────────────────────────────────────────────────

def _active_seats(game: dict) -> List[int]:
    return [i for i, s in enumerate(game["seats"]) if not s["folded"] and not s["left"]]

def _seats_to_act(game: dict) -> List[int]:
    """Seats that still need to act this round."""
    return [i for i in _active_seats(game) if not game["seats"][i]["acted"]]

def _apply_bet(game: dict, seat_idx: int, total_this_round: int):
    """Set a seat's round_bet to total_this_round, deducting from stack."""
    s = game["seats"][seat_idx]
    extra = total_this_round - s["round_bet"]
    extra = min(extra, s["stack"])
    s["stack"]     -= extra
    s["round_bet"] += extra
    game["pot"]    += extra
    if total_this_round > game["current_bet"]:
        game["current_bet"] = total_this_round
        game["last_raiser"] = seat_idx
        # Everyone else needs to act again
        for i, other in enumerate(game["seats"]):
            if i != seat_idx and not other["folded"] and not other["left"]:
                other["acted"] = False
    s["acted"] = True

def _collect_round_bets(game: dict):
    """Reset round_bet and acted for next street."""
    for s in game["seats"]:
        s["round_bet"] = 0
        s["acted"]     = False
    game["current_bet"] = 0
    game["last_raiser"] = -1

def _next_active_after(game: dict, start: int) -> int:
    n = len(game["seats"])
    for offset in range(1, n + 1):
        idx = (start + offset) % n
        s = game["seats"][idx]
        if not s["folded"] and not s["left"]:
            return idx
    return start

# ── Deal a new hand ───────────────────────────────────────────────────────────

def _deal_hand(game: dict):
    game["deck"]      = _fresh_deck()
    game["community"] = []
    game["pot"]       = 0
    game["result"]    = None
    game["hand_num"] += 1
    _collect_round_bets(game)

    active = _active_seats(game)
    if len(active) < 2:
        return

    # Reset hole cards
    for s in game["seats"]:
        s["hole"] = []
        s["folded"] = False

    # Rotate dealer
    game["dealer_idx"] = _next_active_after(game, game["dealer_idx"])
    dealer = game["dealer_idx"]

    # Post blinds
    sb_idx = _next_active_after(game, dealer)
    bb_idx = _next_active_after(game, sb_idx)

    sb = game["seats"][sb_idx]
    bb = game["seats"][bb_idx]

    sb_amt = min(SMALL_BLIND, sb["stack"])
    bb_amt = min(BIG_BLIND,   bb["stack"])

    sb["stack"]     -= sb_amt
    sb["round_bet"]  = sb_amt
    game["pot"]     += sb_amt

    bb["stack"]     -= bb_amt
    bb["round_bet"]  = bb_amt
    game["pot"]     += bb_amt
    game["current_bet"] = bb_amt
    game["last_raiser"] = bb_idx

    # BB has option — mark as not acted so they can raise
    bb["acted"] = False
    sb["acted"] = False

    # Deal 2 hole cards each
    for _ in range(2):
        for i in _active_seats(game):
            game["seats"][i]["hole"].append(game["deck"].pop())

    # Action starts left of BB
    game["action_idx"] = _next_active_after(game, bb_idx)
    game["stage"]      = "preflop"

    _add_log(game, f"Hand #{game['hand_num']} — Blinds posted. {sb['name']} SB {sb_amt}, {bb['name']} BB {bb_amt}.")

# ── Advance street ────────────────────────────────────────────────────────────

def _advance_street(game: dict):
    active = _active_seats(game)
    if len(active) <= 1:
        _resolve_showdown(game)
        return

    _collect_round_bets(game)

    stage = game["stage"]
    if stage == "preflop":
        game["deck"].pop()  # burn
        game["community"].extend([game["deck"].pop() for _ in range(3)])
        game["stage"] = "flop"
        _add_log(game, f"Flop: {' '.join(game['community'][:3])}")
    elif stage == "flop":
        game["deck"].pop()
        game["community"].append(game["deck"].pop())
        game["stage"] = "turn"
        _add_log(game, f"Turn: {game['community'][3]}")
    elif stage == "turn":
        game["deck"].pop()
        game["community"].append(game["deck"].pop())
        game["stage"] = "river"
        _add_log(game, f"River: {game['community'][4]}")
    elif stage == "river":
        _resolve_showdown(game)
        return

    # Action starts left of dealer
    game["action_idx"] = _next_active_after(game, game["dealer_idx"])

# ── Showdown ──────────────────────────────────────────────────────────────────

def _resolve_showdown(game: dict):
    game["stage"] = "showdown"
    active = _active_seats(game)

    if len(active) == 1:
        winner_idx = active[0]
        winner = game["seats"][winner_idx]
        winner["stack"] += game["pot"]
        game["result"] = {
            "winners": [winner_idx],
            "pot":     game["pot"],
            "share":   game["pot"],
            "hand_name": "—",
            "showdown": [],
            "message": f"{winner['name']} wins {game['pot']} XP (everyone else folded)!"
        }
        _add_log(game, game["result"]["message"])
        game["pot"] = 0
        return

    # Evaluate hands
    ranked = []
    for i in active:
        s = game["seats"][i]
        rk = get_hand_rank(s["hole"], game["community"])
        ranked.append((i, rk))

    ranked.sort(key=lambda x: (x[1][0], x[1][1]), reverse=True)
    best = ranked[0][1]
    winners = [i for i, rk in ranked if rk == best]
    share = game["pot"] // len(winners)

    for i in winners:
        game["seats"][i]["stack"] += share

    hand_name = HAND_NAMES.get(best[0], "High Card")
    winner_names = " & ".join(game["seats"][i]["name"] for i in winners)
    msg = f"{winner_names} win {share} XP each with {hand_name}!" if len(winners) > 1 \
          else f"{game['seats'][winners[0]]['name']} wins {share} XP with {hand_name}!"

    showdown_info = []
    for i in active:
        s = game["seats"][i]
        rk = get_hand_rank(s["hole"], game["community"])
        showdown_info.append({
            "seat_idx":  i,
            "name":      s["name"],
            "hole":      _serialize_cards(s["hole"]),
            "hand_name": HAND_NAMES.get(rk[0], "High Card"),
            "winner":    i in winners,
        })

    game["result"] = {
        "winners":   winners,
        "pot":       game["pot"],
        "share":     share,
        "hand_name": hand_name,
        "showdown":  showdown_info,
        "message":   msg,
    }
    _add_log(game, msg)
    game["pot"] = 0

# ── Bot action ────────────────────────────────────────────────────────────────

def _bot_act(game: dict, seat_idx: int):
    s = game["seats"][seat_idx]
    to_call   = game["current_bet"] - s["round_bet"]
    can_check = to_call == 0
    action, amount = get_holdem_bot_action(
        s["hole"], game["community"], to_call, game["pot"], game["stage"], can_check
    )
    if action == "fold":
        s["folded"] = True
        s["acted"]  = True
        _add_log(game, f"{s['name']} folds.")
    elif action in ("check",):
        s["acted"] = True
        _add_log(game, f"{s['name']} checks.")
    elif action == "call":
        _apply_bet(game, seat_idx, s["round_bet"] + to_call)
        _add_log(game, f"{s['name']} calls {to_call}.")
    elif action in ("bet", "raise"):
        total = s["round_bet"] + max(amount, to_call + BIG_BLIND)
        total = min(total, s["stack"] + s["round_bet"])
        _apply_bet(game, seat_idx, total)
        _add_log(game, f"{s['name']} raises to {total}.")

def _run_bots_until_player(game: dict, player_seat: int = 0):
    """Advance bot turns until it's the player's turn, a street ends, or showdown."""
    MAX = 50
    iterations = 0
    while iterations < MAX:
        iterations += 1
        if game["stage"] in ("idle", "showdown"):
            break
        active = _active_seats(game)
        if len(active) <= 1:
            _resolve_showdown(game)
            break
        # Check if betting round is over
        to_act = _seats_to_act(game)
        if not to_act:
            _advance_street(game)
            if game["stage"] == "showdown":
                break
            # After advancing, check again
            continue
        cur = game["action_idx"]
        if cur == player_seat and not game["seats"][player_seat]["folded"]:
            break  # Player's turn
        s = game["seats"][cur]
        if s["folded"] or s["left"] or s["acted"]:
            # Skip to next
            game["action_idx"] = _next_active_after(game, cur)
            continue
        if s["is_bot"]:
            _bot_act(game, cur)
            # Advance action_idx
            game["action_idx"] = _next_active_after(game, cur)
        else:
            break

# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/casino/holdem/start")
async def holdem_start(request: Request):
    """Start a new Hold'em session. Body: {buy_in, fun_mode, num_bots}"""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    try:
        body     = await request.json()
        buy_in   = int(body.get("buy_in", 500))
        fun_mode = bool(body.get("fun_mode", False))
        num_bots = max(1, min(4, int(body.get("num_bots", 2))))
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    if buy_in < BIG_BLIND * 2:
        return JSONResponse({"error": f"Minimum buy-in is {BIG_BLIND * 2} XP"}, status_code=400)

    async with _get_user_lock(user_id):
        if not fun_mode:
            pet = await user_data_manager.get_pet_data_async(user_id)
            if not pet:
                return JSONResponse({"error": "No pet found"}, status_code=404)
            if buy_in > _compute_total_xp(pet):
                return JSONResponse({"error": "Insufficient XP"}, status_code=400)
            await LootCalculator.apply_xp_change(int(user_id), -buy_in, source="holdem_buyin")

        game = _new_game(buy_in, fun_mode, num_bots)
        _deal_hand(game)
        _run_bots_until_player(game)
        _set_game(request.session, game)
        return JSONResponse(_game_response(game))


@router.post("/casino/holdem/action")
async def holdem_action(request: Request):
    """
    Player action. Body: {action: fold|check|call|raise, amount?: int}
    """
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    game = _get_game(request.session)
    if not game or game["stage"] in ("idle", "showdown"):
        return JSONResponse({"error": "No active hand"}, status_code=400)

    try:
        body   = await request.json()
        action = str(body.get("action", ""))
        amount = int(body.get("amount", 0))
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    async with _get_user_lock(user_id):
        PLAYER = 0
        s = game["seats"][PLAYER]
        if game["action_idx"] != PLAYER:
            return JSONResponse({"error": "Not your turn"}, status_code=400)
        if s["folded"]:
            return JSONResponse({"error": "You have already folded"}, status_code=400)

        to_call = game["current_bet"] - s["round_bet"]

        if action == "fold":
            s["folded"] = True
            s["acted"]  = True
            _add_log(game, "You fold.")
        elif action == "check":
            if to_call > 0:
                return JSONResponse({"error": f"Cannot check — must call {to_call}"}, status_code=400)
            s["acted"] = True
            _add_log(game, "You check.")
        elif action == "call":
            call_total = s["round_bet"] + to_call
            _apply_bet(game, PLAYER, call_total)
            _add_log(game, f"You call {to_call}.")
        elif action == "raise":
            min_raise = s["round_bet"] + to_call + BIG_BLIND
            if amount < min_raise:
                return JSONResponse({"error": f"Minimum raise is {min_raise}"}, status_code=400)
            if amount > s["stack"] + s["round_bet"]:
                return JSONResponse({"error": "Not enough chips"}, status_code=400)
            _apply_bet(game, PLAYER, amount)
            _add_log(game, f"You raise to {amount}.")
        else:
            return JSONResponse({"error": f"Unknown action: {action}"}, status_code=400)

        # Advance action pointer
        game["action_idx"] = _next_active_after(game, PLAYER)

        # Check if round is over
        active = _active_seats(game)
        if len(active) <= 1:
            _resolve_showdown(game)
        else:
            to_act = _seats_to_act(game)
            if not to_act:
                _advance_street(game)

        # Run bots
        if game["stage"] not in ("idle", "showdown"):
            _run_bots_until_player(game)

        _set_game(request.session, game)
        return JSONResponse(_game_response(game))


@router.post("/casino/holdem/next_hand")
async def holdem_next_hand(request: Request):
    """Deal the next hand after showdown."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    game = _get_game(request.session)
    if not game:
        return JSONResponse({"error": "No active session"}, status_code=400)

    async with _get_user_lock(user_id):
        # Remove busted players (stack == 0)
        game["seats"] = [s for s in game["seats"] if s["stack"] > 0 or s["id"] == "player"]

        # If player is busted, settle and end
        player = game["seats"][0]
        if player["stack"] <= 0:
            if not game["fun_mode"]:
                await user_data_manager.update_pet_gambling_stats(
                    user_id, "holdem", -game["buy_in"], bet_amount=game["buy_in"]
                )
            _clear_game(request.session)
            return JSONResponse({"error": "You are out of chips. Game over.", "game_over": True})

        if len(game["seats"]) < 2:
            # Player won everything
            winnings = player["stack"] - game["buy_in"]
            if not game["fun_mode"] and winnings > 0:
                await LootCalculator.apply_xp_change(int(user_id), player["stack"], source="holdem_win")
            if not game["fun_mode"]:
                await user_data_manager.update_pet_gambling_stats(
                    user_id, "holdem", winnings, bet_amount=game["buy_in"]
                )
            _clear_game(request.session)
            return JSONResponse({"game_over": True, "won": player["stack"],
                                 "message": f"You won! Cashing out {player['stack']} XP."})

        _deal_hand(game)
        _run_bots_until_player(game)
        _set_game(request.session, game)
        return JSONResponse(_game_response(game))


@router.post("/casino/holdem/cashout")
async def holdem_cashout(request: Request):
    """Cash out current stack and end session."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    game = _get_game(request.session)
    if not game:
        return JSONResponse({"error": "No active session"}, status_code=400)

    async with _get_user_lock(user_id):
        stack = game["seats"][0]["stack"]
        if not game["fun_mode"] and stack > 0:
            await LootCalculator.apply_xp_change(int(user_id), stack, source="holdem_cashout")

        if not game["fun_mode"]:
            net = stack - game["buy_in"]
            await user_data_manager.update_pet_gambling_stats(
                user_id, "holdem", net, bet_amount=game["buy_in"]
            )

        _clear_game(request.session)
        return JSONResponse({"ok": True, "cashed_out": stack, "fun_mode": game["fun_mode"]})


@router.get("/casino/holdem/state")
async def holdem_state(request: Request):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    game = _get_game(request.session)
    if not game:
        return JSONResponse({"active": False})
    resp = _game_response(game)
    resp["active"] = True
    return JSONResponse(resp)


# ── Shared room game state (room_id → game) ───────────────────────────────────
# Allows multiple real players to sit at the same table.
_room_games: Dict[int, dict] = {}
_room_locks: Dict[int, asyncio.Lock] = {}

def _get_room_lock(room_id: int) -> asyncio.Lock:
    if room_id not in _room_locks:
        _room_locks[room_id] = asyncio.Lock()
    return _room_locks[room_id]


@router.get("/casino/holdem/room/state")
async def holdem_room_state(request: Request):
    """Get the shared Hold'em game state for a room (observers + players)."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)

    try:
        room_id = int(request.query_params.get("room_id", -1))
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    game = _room_games.get(room_id)
    if not game:
        return JSONResponse({"active": False})

    user_id = str(user["id"])
    # Find which seat this user is in (if any)
    player_seat = next(
        (i for i, s in enumerate(game["seats"]) if s.get("user_id") == user_id),
        None
    )
    resp = _game_response(game, player_seat=player_seat if player_seat is not None else 0)
    resp["active"]      = True
    resp["player_seat"] = player_seat  # None if observer
    return JSONResponse(resp)


@router.post("/casino/holdem/room/start")
async def holdem_room_start(request: Request):
    """
    Host starts a shared Hold'em table in a casino room.
    Body: {room_id, buy_in, fun_mode, num_bots}
    """
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    try:
        body     = await request.json()
        room_id  = int(body.get("room_id", -1))
        buy_in   = int(body.get("buy_in", 500))
        fun_mode = bool(body.get("fun_mode", False))
        num_bots = max(0, min(4, int(body.get("num_bots", 2))))
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    if buy_in < BIG_BLIND * 2:
        return JSONResponse({"error": f"Minimum buy-in is {BIG_BLIND * 2} XP"}, status_code=400)

    async with _get_room_lock(room_id):
        if not fun_mode:
            pet = await user_data_manager.get_pet_data_async(user_id)
            if not pet:
                return JSONResponse({"error": "No pet found"}, status_code=404)
            if buy_in > _compute_total_xp(pet):
                return JSONResponse({"error": "Insufficient XP"}, status_code=400)
            await LootCalculator.apply_xp_change(int(user_id), -buy_in, source="holdem_buyin")

        game = _new_game(buy_in, fun_mode, num_bots)
        # Tag seat 0 with the host's user_id
        game["seats"][0]["user_id"] = user_id
        game["seats"][0]["name"]    = user.get("username", "You")
        _deal_hand(game)
        _run_bots_until_player(game, player_seat=0)
        _room_games[room_id] = game

    return JSONResponse({**_game_response(game, player_seat=0), "room_id": room_id})


@router.post("/casino/holdem/room/action")
async def holdem_room_action(request: Request):
    """Player action in a shared room game."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    try:
        body    = await request.json()
        room_id = int(body.get("room_id", -1))
        action  = str(body.get("action", ""))
        amount  = int(body.get("amount", 0))
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    async with _get_room_lock(room_id):
        game = _room_games.get(room_id)
        if not game or game["stage"] in ("idle", "showdown"):
            return JSONResponse({"error": "No active hand"}, status_code=400)

        # Find this user's seat
        player_seat = next(
            (i for i, s in enumerate(game["seats"]) if s.get("user_id") == user_id),
            None
        )
        if player_seat is None:
            return JSONResponse({"error": "You are not seated at this table"}, status_code=400)

        if game["action_idx"] != player_seat:
            return JSONResponse({"error": "Not your turn"}, status_code=400)

        s = game["seats"][player_seat]
        if s["folded"]:
            return JSONResponse({"error": "You have already folded"}, status_code=400)

        to_call = game["current_bet"] - s["round_bet"]

        if action == "fold":
            s["folded"] = True; s["acted"] = True
            _add_log(game, f"{s['name']} folds.")
        elif action == "check":
            if to_call > 0:
                return JSONResponse({"error": f"Cannot check — must call {to_call}"}, status_code=400)
            s["acted"] = True
            _add_log(game, f"{s['name']} checks.")
        elif action == "call":
            _apply_bet(game, player_seat, s["round_bet"] + to_call)
            _add_log(game, f"{s['name']} calls {to_call}.")
        elif action == "raise":
            min_raise = s["round_bet"] + to_call + BIG_BLIND
            if amount < min_raise:
                return JSONResponse({"error": f"Minimum raise is {min_raise}"}, status_code=400)
            _apply_bet(game, player_seat, amount)
            _add_log(game, f"{s['name']} raises to {amount}.")
        else:
            return JSONResponse({"error": f"Unknown action: {action}"}, status_code=400)

        game["action_idx"] = _next_active_after(game, player_seat)
        active = _active_seats(game)
        if len(active) <= 1:
            _resolve_showdown(game)
        else:
            to_act = _seats_to_act(game)
            if not to_act:
                _advance_street(game)

        if game["stage"] not in ("idle", "showdown"):
            _run_bots_until_player(game, player_seat=player_seat)

    return JSONResponse({**_game_response(game, player_seat=player_seat), "room_id": room_id})


@router.post("/casino/holdem/room/next_hand")
async def holdem_room_next_hand(request: Request):
    """Deal next hand in a shared room, promoting any pending players."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    try:
        body    = await request.json()
        room_id = int(body.get("room_id", -1))
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    async with _get_room_lock(room_id):
        game = _room_games.get(room_id)
        if not game:
            return JSONResponse({"error": "No active session"}, status_code=400)

        # Promote pending seats from lobby
        try:
            from web.api.casino_lobby_api import _casino_rooms, GAME_INFO
            room = _casino_rooms.get(room_id)
            if room and room.pending_seats:
                for pending in list(room.pending_seats):
                    if len(game["seats"]) < 6:
                        buy_in = game["buy_in"]
                        pid    = pending["user_id"]
                        if not game["fun_mode"]:
                            pet = await user_data_manager.get_pet_data_async(pid)
                            if pet and _compute_total_xp(pet) >= buy_in:
                                await LootCalculator.apply_xp_change(int(pid), -buy_in, source="holdem_buyin")
                                game["seats"].append({
                                    "id": f"user_{pid}", "name": pending["username"],
                                    "user_id": pid, "is_bot": False,
                                    "hole": [], "folded": False, "left": False,
                                    "stack": buy_in, "round_bet": 0, "acted": False
                                })
                                room.observers = [o for o in room.observers if o["user_id"] != pid]
                                room.occupants.append(pending)
                                room.add_activity(f"🪑 {pending['username']} joined the table!")
                room.pending_seats = []
        except Exception as e:
            logger.warning(f"Could not promote pending seats: {e}")

        # Remove busted players
        game["seats"] = [s for s in game["seats"] if s["stack"] > 0 or s.get("user_id") == user_id]

        player_seat = next(
            (i for i, s in enumerate(game["seats"]) if s.get("user_id") == user_id), 0
        )

        if len(game["seats"]) < 2:
            # Settle and end
            player = game["seats"][0] if game["seats"] else {"stack": 0}
            stack  = player.get("stack", 0)
            if not game["fun_mode"] and stack > 0:
                await LootCalculator.apply_xp_change(int(user_id), stack, source="holdem_win")
            _room_games.pop(room_id, None)
            return JSONResponse({"game_over": True, "won": stack,
                                 "message": f"You won! Cashing out {stack} XP."})

        _deal_hand(game)
        _run_bots_until_player(game, player_seat=player_seat)

    return JSONResponse({**_game_response(game, player_seat=player_seat), "room_id": room_id})


@router.post("/casino/holdem/room/cashout")
async def holdem_room_cashout(request: Request):
    """Cash out from a shared room game."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    try:
        body    = await request.json()
        room_id = int(body.get("room_id", -1))
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    async with _get_room_lock(room_id):
        game = _room_games.get(room_id)
        if not game:
            return JSONResponse({"error": "No active session"}, status_code=400)

        player_seat = next(
            (i for i, s in enumerate(game["seats"]) if s.get("user_id") == user_id), None
        )
        if player_seat is None:
            return JSONResponse({"error": "Not seated"}, status_code=400)

        stack = game["seats"][player_seat]["stack"]
        if not game["fun_mode"] and stack > 0:
            await LootCalculator.apply_xp_change(int(user_id), stack, source="holdem_cashout")

        # Remove this player from the game
        game["seats"][player_seat]["left"] = True
        game["seats"][player_seat]["stack"] = 0

        # If no real players remain, clean up
        real_players = [s for s in game["seats"] if not s.get("is_bot") and not s.get("left")]
        if not real_players:
            _room_games.pop(room_id, None)

    return JSONResponse({"ok": True, "cashed_out": stack})

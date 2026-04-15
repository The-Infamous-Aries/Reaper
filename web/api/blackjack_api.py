"""
Web Blackjack API — stateless, session-backed with shared table support.
Solo game state lives in request.session.
When a room_id is provided the deck is shared across all seated players.
"""
from __future__ import annotations
import asyncio
import random
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.requests import Request

from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.pet_brain import LootCalculator

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Shared table state (room_id → table dict) ─────────────────────────────────
# Allows multiple players to share the same deck (card counting is possible).
_shared_tables: Dict[int, Dict] = {}
_table_lock = asyncio.Lock()

# ── Per-user locks ────────────────────────────────────────────────────────────
# Prevents race conditions when a player fires multiple requests simultaneously
# (e.g. double-clicking Hit, or having two tabs open).

_user_locks: Dict[str, asyncio.Lock] = {}

def _get_user_lock(user_id: str) -> asyncio.Lock:
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    return _user_locks[user_id]

# ── Deck helpers ──────────────────────────────────────────────────────────────

SUITS  = ["H", "D", "C", "S"]
RANKS  = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

def _fresh_deck() -> List[str]:
    deck = [f"{s}{r}" for s in SUITS for r in RANKS] * 4
    random.shuffle(deck)
    return deck

def _card_value(code: str) -> int:
    r = code[1:]
    if r in ("J", "Q", "K"):
        return 10
    if r == "1":
        return 11
    return int(r)

def _hand_value(hand: List[str]):
    """Return (total, is_soft)."""
    total = sum(_card_value(c) for c in hand)
    aces  = sum(1 for c in hand if c[1:] == "1")
    while total > 21 and aces:
        total -= 10
        aces  -= 1
    return total, False

def _card_img(code: str) -> str:
    return f"/static/Emojis/Cards/{code}.png"

def _serialize_hand(hand: List[str], hide_hole: bool = False):
    cards = []
    for i, c in enumerate(hand):
        if hide_hole and i == 1:
            cards.append({"code": "back", "img": "/static/Emojis/Cards/BJ.png", "hidden": True})
        else:
            cards.append({"code": c, "img": _card_img(c), "hidden": False})
    return cards

def _compute_total_xp(pet: dict) -> int:
    lvl = int(pet.get("level", 1))
    exp = int(pet.get("experience", 0))
    return int(LootCalculator.get_total_experience_for_level(lvl)) + exp

# ── Session helpers ───────────────────────────────────────────────────────────

def _get_bj(session) -> Optional[dict]:
    return session.get("bj_game")

def _set_bj(session, game: dict):
    session["bj_game"] = game

def _clear_bj(session):
    session.pop("bj_game", None)

# ── Dealer AI ─────────────────────────────────────────────────────────────────

def _dealer_should_hit(hand: List[str]) -> bool:
    total, soft = _hand_value(hand)
    # Dealer hits soft 17
    if total < 17:
        return True
    if total == 17:
        aces = sum(1 for c in hand if c[1:] == "1")
        raw  = sum(_card_value(c) for c in hand)
        return raw != 17  # soft 17
    return False

# ── State builder ─────────────────────────────────────────────────────────────

def _game_response(game: dict, hide_hole: bool = True) -> dict:
    phase = game["phase"]
    player_hand = game["player_hand"]
    dealer_hand = game["dealer_hand"]
    split_hand  = game.get("split_hand")

    p_val, _  = _hand_value(player_hand)
    d_val, _  = _hand_value(dealer_hand)
    s_val     = _hand_value(split_hand)[0] if split_hand else None

    active = game.get("active_hand", "main")  # "main" | "split"

    can_double = (
        phase == "player"
        and active == "main"
        and len(player_hand) == 2
        and not game.get("split_hand")
    )
    can_split = (
        phase == "player"
        and active == "main"
        and len(player_hand) == 2
        and not game.get("split_hand")
        and _card_value(player_hand[0]) == _card_value(player_hand[1])
    )

    return {
        "phase":       phase,
        "player_hand": _serialize_hand(player_hand),
        "player_val":  p_val,
        "dealer_hand": _serialize_hand(dealer_hand, hide_hole=(hide_hole and phase == "player")),
        "dealer_val":  (dealer_hand[0][1:] if hide_hole and phase == "player" else str(d_val)),
        "split_hand":  _serialize_hand(split_hand) if split_hand else None,
        "split_val":   s_val,
        "active_hand": active,
        "bet":         game["bet"],
        "split_bet":   game.get("split_bet", 0),
        "fun_mode":    game["fun_mode"],
        "can_double":  can_double,
        "can_split":   can_split,
        "result":      game.get("result"),       # set when phase == "done"
        "xp_change":   game.get("xp_change", 0),
        "message":     game.get("message", ""),
    }

# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/casino/blackjack/deal")
async def bj_deal(request: Request):
    """Start a new hand. Body: {bet: int, fun_mode: bool}"""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    try:
        body     = await request.json()
        bet      = int(body.get("bet", 0))
        fun_mode = bool(body.get("fun_mode", False))
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    async with _get_user_lock(user_id):
        return await _bj_deal_inner(request, user_id, bet, fun_mode)


async def _bj_deal_inner(request: Request, user_id: str, bet: int, fun_mode: bool):
    if not fun_mode:
        if bet < 10:
            return JSONResponse({"error": "Minimum bet is 10 XP"}, status_code=400)
        pet = await user_data_manager.get_pet_data_async(user_id)
        if not pet:
            return JSONResponse({"error": "No pet found"}, status_code=404)
        total_xp = _compute_total_xp(pet)
        if bet > total_xp:
            return JSONResponse({"error": "Insufficient XP"}, status_code=400)
        await LootCalculator.apply_xp_change(int(user_id), -bet, source="blackjack_bet")

    deck = _fresh_deck()
    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]

    p_val, _ = _hand_value(player_hand)
    d_val, _ = _hand_value(dealer_hand)

    # Natural blackjack check
    player_bj = p_val == 21
    dealer_bj = d_val == 21

    if player_bj or dealer_bj:
        phase = "done"
        if player_bj and dealer_bj:
            result, xp_change, msg = "push", 0, "Both Blackjack — Push!"
        elif player_bj:
            result, xp_change, msg = "blackjack", int(bet * 1.5), "🃏 Blackjack! You win 3:2!"
        else:
            result, xp_change, msg = "lose", 0, "Dealer Blackjack — you lose."
        if not fun_mode and xp_change > 0:
            await LootCalculator.apply_xp_change(int(user_id), bet + xp_change, source="blackjack_win")
        # Track stats for instant resolution
        if not fun_mode:
            net = xp_change if result != "lose" else -bet
            await user_data_manager.update_pet_gambling_stats(
                user_id, "blackjack", net, bet_amount=bet,
                extra_data={"is_push": result == "push"}
            )
    else:
        phase, result, xp_change, msg = "player", None, 0, ""

    game = {
        "deck":        deck,
        "player_hand": player_hand,
        "dealer_hand": dealer_hand,
        "split_hand":  None,
        "active_hand": "main",
        "bet":         bet,
        "split_bet":   0,
        "fun_mode":    fun_mode,
        "phase":       phase,
        "result":      result,
        "xp_change":   xp_change,
        "message":     msg,
    }
    _set_bj(request.session, game)
    return JSONResponse(_game_response(game, hide_hole=(phase == "player")))


@router.post("/casino/blackjack/hit")
async def bj_hit(request: Request):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    async with _get_user_lock(user_id):
        game = _get_bj(request.session)
        if not game or game["phase"] != "player":
            return JSONResponse({"error": "No active hand"}, status_code=400)

        active = game.get("active_hand", "main")
        hand_key = "player_hand" if active == "main" else "split_hand"
        game[hand_key].append(game["deck"].pop())

        val, _ = _hand_value(game[hand_key])
        if val > 21:
            # Bust — if split hand active, switch back to main or end
            if active == "split":
                game["active_hand"] = "main"
                # If main is also done, go to dealer
                main_val, _ = _hand_value(game["player_hand"])
                if main_val > 21:
                    await _finish_dealer(game, request)
            else:
                if game.get("split_hand"):
                    game["active_hand"] = "split"
                else:
                    await _finish_dealer(game, request)

        _set_bj(request.session, game)
        return JSONResponse(_game_response(game, hide_hole=(game["phase"] == "player")))


@router.post("/casino/blackjack/stand")
async def bj_stand(request: Request):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    async with _get_user_lock(user_id):
        game = _get_bj(request.session)
        if not game or game["phase"] != "player":
            return JSONResponse({"error": "No active hand"}, status_code=400)

        active = game.get("active_hand", "main")
        if active == "main" and game.get("split_hand"):
            # Move to split hand
            game["active_hand"] = "split"
            _set_bj(request.session, game)
            return JSONResponse(_game_response(game, hide_hole=True))

        await _finish_dealer(game, request)
        _set_bj(request.session, game)
        return JSONResponse(_game_response(game, hide_hole=False))


@router.post("/casino/blackjack/double")
async def bj_double(request: Request):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    async with _get_user_lock(user_id):
        game = _get_bj(request.session)
        if not game or game["phase"] != "player":
            return JSONResponse({"error": "No active hand"}, status_code=400)
        if len(game["player_hand"]) != 2 or game.get("split_hand"):
            return JSONResponse({"error": "Cannot double"}, status_code=400)

        bet = game["bet"]
        if not game["fun_mode"]:
            pet = await user_data_manager.get_pet_data_async(user_id)
            if not pet:
                return JSONResponse({"error": "No pet"}, status_code=404)
            if bet > _compute_total_xp(pet):
                return JSONResponse({"error": "Insufficient XP to double"}, status_code=400)
            await LootCalculator.apply_xp_change(int(user_id), -bet, source="blackjack_double")

        game["bet"] = bet * 2
        game["player_hand"].append(game["deck"].pop())
        await _finish_dealer(game, request)
        _set_bj(request.session, game)
        return JSONResponse(_game_response(game, hide_hole=False))


@router.post("/casino/blackjack/split")
async def bj_split(request: Request):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    async with _get_user_lock(user_id):
        game = _get_bj(request.session)
        if not game or game["phase"] != "player":
            return JSONResponse({"error": "No active hand"}, status_code=400)

        ph = game["player_hand"]
        if len(ph) != 2 or _card_value(ph[0]) != _card_value(ph[1]) or game.get("split_hand"):
            return JSONResponse({"error": "Cannot split"}, status_code=400)

        bet = game["bet"]
        if not game["fun_mode"]:
            pet = await user_data_manager.get_pet_data_async(user_id)
            if not pet:
                return JSONResponse({"error": "No pet"}, status_code=404)
            if bet > _compute_total_xp(pet):
                return JSONResponse({"error": "Insufficient XP to split"}, status_code=400)
            await LootCalculator.apply_xp_change(int(user_id), -bet, source="blackjack_split")

        card_a, card_b = ph[0], ph[1]
        game["player_hand"] = [card_a, game["deck"].pop()]
        game["split_hand"]  = [card_b, game["deck"].pop()]
        game["split_bet"]   = bet
        game["active_hand"] = "main"

        _set_bj(request.session, game)
        return JSONResponse(_game_response(game, hide_hole=True))


@router.post("/casino/blackjack/insurance")
async def bj_insurance(request: Request):
    """Decline insurance (we just continue — insurance is offered client-side only as info)."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    game = _get_bj(request.session)
    if not game:
        return JSONResponse({"error": "No active hand"}, status_code=400)
    return JSONResponse(_game_response(game, hide_hole=(game["phase"] == "player")))


@router.get("/casino/blackjack/state")
async def bj_state(request: Request):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    game = _get_bj(request.session)
    if not game:
        return JSONResponse({"active": False})
    resp = _game_response(game, hide_hole=(game["phase"] == "player"))
    resp["active"] = True
    return JSONResponse(resp)


# ── Dealer resolution ─────────────────────────────────────────────────────────

async def _finish_dealer(game: dict, request: Request):
    """Run dealer, settle both hands, write XP."""
    user    = request.session.get("discord_user")
    user_id = str(user["id"]) if user else None

    # Dealer draws
    while _dealer_should_hit(game["dealer_hand"]):
        game["dealer_hand"].append(game["deck"].pop())

    d_val, _ = _hand_value(game["dealer_hand"])
    dealer_bust = d_val > 21

    total_xp_change = 0
    results = []

    def _settle_hand(hand: List[str], bet: int) -> tuple[str, int]:
        p_val, _ = _hand_value(hand)
        if p_val > 21:
            return "lose", 0
        if dealer_bust or p_val > d_val:
            return "win", bet * 2   # return bet + winnings
        if p_val == d_val:
            return "push", bet      # return bet only
        return "lose", 0

    main_result, main_return = _settle_hand(game["player_hand"], game["bet"])
    results.append(main_result)
    total_xp_change += main_return - game["bet"]  # net change (already deducted bet)

    split_result = None
    if game.get("split_hand"):
        split_result, split_return = _settle_hand(game["split_hand"], game["split_bet"])
        results.append(split_result)
        total_xp_change += split_return - game["split_bet"]

    # Apply XP
    if not game["fun_mode"] and user_id:
        # Return winnings (bet was already deducted on deal/split/double)
        main_payout = main_return
        if main_payout > 0:
            await LootCalculator.apply_xp_change(int(user_id), main_payout, source="blackjack_win")
        if game.get("split_hand"):
            split_payout = split_return if split_result else 0
            if split_payout > 0:
                await LootCalculator.apply_xp_change(int(user_id), split_payout, source="blackjack_win")

    # Build message
    if split_result:
        msg = f"Main: {main_result.upper()} · Split: {split_result.upper()}"
    elif main_result == "win":
        msg = "🏆 You win!"
    elif main_result == "push":
        msg = "🤝 Push — bet returned."
    else:
        msg = "💀 Dealer wins."

    if dealer_bust:
        msg = f"💥 Dealer busts! {msg}"

    game["phase"]      = "done"
    game["result"]     = main_result
    game["xp_change"]  = total_xp_change if not game["fun_mode"] else 0
    game["message"]    = msg

    # Track gambling stats — net XP across both hands
    if not game["fun_mode"] and user_id:
        total_bet = game["bet"] + game.get("split_bet", 0)
        await user_data_manager.update_pet_gambling_stats(
            user_id, "blackjack", total_xp_change, bet_amount=total_bet,
            extra_data={"is_push": main_result == "push"}
        )


# ── Shared table endpoints (arena multiplayer) ────────────────────────────────

def _get_shared_table(room_id: int) -> Optional[dict]:
    return _shared_tables.get(room_id)

def _ensure_shared_table(room_id: int) -> dict:
    if room_id not in _shared_tables:
        _shared_tables[room_id] = {
            "deck":    _fresh_deck(),
            "players": {},   # user_id → hand state
            "phase":   "waiting",  # waiting | dealing | done
        }
    return _shared_tables[room_id]


@router.post("/casino/blackjack/table/join")
async def bj_table_join(request: Request):
    """Join a shared blackjack table in a casino room."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    try:
        body    = await request.json()
        room_id = int(body.get("room_id", -1))
        bet     = int(body.get("bet", 0))
        fun_mode = bool(body.get("fun_mode", False))
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    async with _table_lock:
        table = _ensure_shared_table(room_id)

        if not fun_mode:
            if bet < 10:
                return JSONResponse({"error": "Minimum bet is 10 XP"}, status_code=400)
            pet = await user_data_manager.get_pet_data_async(user_id)
            if not pet:
                return JSONResponse({"error": "No pet found"}, status_code=404)
            if bet > _compute_total_xp(pet):
                return JSONResponse({"error": "Insufficient XP"}, status_code=400)
            await LootCalculator.apply_xp_change(int(user_id), -bet, source="blackjack_bet")

        # Reshuffle if deck is running low
        if len(table["deck"]) < 20:
            table["deck"] = _fresh_deck()

        table["players"][user_id] = {
            "hand":     [table["deck"].pop(), table["deck"].pop()],
            "bet":      bet,
            "fun_mode": fun_mode,
            "phase":    "player",
            "result":   None,
            "xp_change": 0,
        }

    return JSONResponse({"ok": True, "room_id": room_id, "deck_remaining": len(table["deck"])})


@router.get("/casino/blackjack/table/state")
async def bj_table_state(request: Request):
    """Get the shared table state for observers."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)

    try:
        room_id = int(request.query_params.get("room_id", -1))
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    table = _get_shared_table(room_id)
    if not table:
        return JSONResponse({"active": False})

    # Serialize player hands (hide hole card for active players)
    players_out = {}
    for uid, p in table["players"].items():
        players_out[uid] = {
            "hand":      _serialize_hand(p["hand"], hide_hole=(p["phase"] == "player")),
            "hand_val":  _hand_value(p["hand"])[0],
            "bet":       p["bet"],
            "phase":     p["phase"],
            "result":    p["result"],
            "xp_change": p["xp_change"],
        }

    return JSONResponse({
        "active":         True,
        "room_id":        room_id,
        "deck_remaining": len(table["deck"]),
        "players":        players_out,
    })


@router.post("/casino/blackjack/table/leave")
async def bj_table_leave(request: Request):
    """Leave the shared table (waits until current hand is done)."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    try:
        body    = await request.json()
        room_id = int(body.get("room_id", -1))
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    async with _table_lock:
        table = _get_shared_table(room_id)
        if table:
            table["players"].pop(user_id, None)
            if not table["players"]:
                _shared_tables.pop(room_id, None)

    return JSONResponse({"ok": True})

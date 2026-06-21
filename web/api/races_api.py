"""
Web Pet Races API — stateless, session-backed.
Mirrors RaceSession / _settle_bets logic from Systems/Pets/PetGames/races.py exactly.

Race is computed server-side in one shot (all ticks pre-calculated) so the
client can animate it smoothly without polling.  The full tick-by-tick
progress array is returned so the JS can replay it at any speed.
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

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Server-side game store (keyed by user_id) ─────────────────────────────────
# Storing game state server-side instead of in the session cookie prevents
# concurrent requests (e.g. discord/user profile refresh) from overwriting
# the cookie and losing the active game state.
_game_store: Dict[str, dict] = {}

def _get_game(session) -> Optional[dict]:
    """Look up game state by user_id from the server-side store."""
    user = session.get("discord_user")
    if not user:
        return None
    return _game_store.get(str(user.get("id")))

def _set_game(session, game: dict):
    """Persist game state server-side, keyed by user_id."""
    user = session.get("discord_user")
    if not user:
        return
    _game_store[str(user.get("id"))] = game

def _clear_game(session):
    """Remove game state for this user from the server-side store."""
    user = session.get("discord_user")
    if not user:
        return
    _game_store.pop(str(user.get("id")), None)

def _get_game_for_user(user_id: str) -> Optional[dict]:
    """Direct lookup by user_id (used inside locked sections)."""
    return _game_store.get(user_id)

def _set_game_for_user(user_id: str, game: dict):
    """Direct store by user_id (used inside locked sections)."""
    _game_store[user_id] = game

def _clear_game_for_user(user_id: str):
    """Direct clear by user_id (used inside locked sections)."""
    _game_store.pop(user_id, None)

# ── Constants (mirrors races.py) ──────────────────────────────────────────────

MAX_SEGMENTS   = 10
# diff_mult controls bot stat ADVANTAGE over the player (>1 = harder bots)
DIFF_MULTS     = {"apprentice": 0.85, "journeyman": 1.15, "senior": 1.5}
PAYOUT_MULTS   = {"apprentice": 1.25, "journeyman": 2.0, "senior": 3.0}

# Absolute bot stat ranges per difficulty — independent of player stats
# so a high-level player can't trivially beat "easy" bots
BOT_STAT_RANGES = {
    "apprentice": (1.0, 4.0),   # weak bots — player should win ~60-65%
    "journeyman": (3.0, 8.0),   # mid bots  — roughly even odds
    "senior":     (6.0, 14.0),  # strong bots — player wins ~35-40%
}

BOT_NAMES = ["Ace", "Blaze", "Chip", "Duke"]

ALL_PETS = [
    'Alligator','Ant','Anteater','Axolotl','Badger','Bat','Beaver','Bee','Beetle',
    'Bison','BlueTang','Camel','Cardinal','Cat','Centipede','Cheetah','Chicken',
    'Clownfish','Cow','Crab','Crow','Deer','Dog','Dolphin','Duck','Eagle','Elephant',
    'Emu','Firefly','Fox','Frog','Giraffe','Goat','Goose','Gorilla','Grizzly',
    'Hamster','Hedgehog','Hippo','Horse','Hummingbird','Iguana','Jaguar','Jellyfish',
    'Kangaroo','Kiwi','Koala','Ladybug','Lemur','Leopard','Lion','Llama','Mantis',
    'Monkey','Mouse','Octopus','Orangutan','Orca','Ostrich','Otter','Owl','Panda',
    'Parrot','Peacock','Pelican','Penguin','Pig','Pigeon','Platypus','PolarBear',
    'Pufferfish','Rabbit','Raccoon','Ram','Rat','RedPanda','Reindeer','Rhino',
    'Salmon','Scorpion','Seahorse','Seal','Shark','Sheep','Shrimp','Skunk','Sloth',
    'Snail','Snake','Spider','Squirrel','Starfish','Stingray','SugarGlider','Tiger',
    'Toucan','Turkey','Turtle','Walrus','Whale','Wolf','Yak','Zebra'
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _pet_speed(stats: dict, pet_data: dict = None) -> float:
    """Return a randomised speed value for one tick. Stats influence variance and mean."""
    dex = float(stats.get("DEX", 1))
    ene = float(stats.get("ENE", 1))
    hap = float(stats.get("HAP", 1))
    
    # Apply ability tree speed multipliers
    speed_multiplier = 1.0
    if pet_data:
        try:
            from Systems.Pets.Logic.ability_tree import get_ability_effect
            speed_multiplier = get_ability_effect(pet_data, "speed_multiplier")
        except Exception:
            pass
    
    # Use log-scale so high stats don't explode the value
    import math
    base = (math.log1p(dex) + math.log1p(ene) + math.log1p(hap)) / 3.0
    return base * speed_multiplier * random.uniform(0.6, 1.4)


def _simulate_race(racers: List[dict], target_ticks: int = 60) -> List[List[int]]:
    """
    Simulate a race that always takes roughly target_ticks ticks to complete,
    regardless of how high the pets' stats are.

    Strategy:
      1. Compute each racer's mean speed (log-scaled).
      2. Set segment_threshold so the fastest racer crosses MAX_SEGMENTS in
         exactly target_ticks ticks on average.
      3. Run the simulation tick-by-tick, recording progress snapshots.

    Returns (ticks, finish_tick) where finish_tick[i] is the tick index when
    racer i crossed MAX_SEGMENTS (or MAX_TICKS if they never finished).
    """
    import math

    # Step 1 — estimate mean speed per racer (no randomness yet)
    def mean_speed(stats: dict, pet_data: dict = None) -> float:
        dex = float(stats.get("DEX", 1))
        ene = float(stats.get("ENE", 1))
        hap = float(stats.get("HAP", 1))
        
        # Apply ability tree speed multipliers
        speed_multiplier = 1.0
        if pet_data:
            try:
                from Systems.Pets.Logic.ability_tree import get_ability_effect
                speed_multiplier = get_ability_effect(pet_data, "speed_multiplier")
            except Exception:
                pass
        
        return (math.log1p(dex) + math.log1p(ene) + math.log1p(hap)) / 3.0 * speed_multiplier

    speeds = [mean_speed(r["stats"], r.get("pet_data")) for r in racers]
    fastest = max(speeds) if speeds else 1.0

    # Step 2 — threshold so fastest racer finishes in ~target_ticks ticks
    # fastest_speed * target_ticks = MAX_SEGMENTS * threshold
    segment_threshold = (fastest * target_ticks) / MAX_SEGMENTS

    # Step 3 — simulate
    progress  = [0] * len(racers)
    accum     = [0.0] * len(racers)
    finished  = [False] * len(racers)
    finish_tick = [None] * len(racers)  # tick index when each racer finished
    ticks: List[List[int]] = []

    MAX_TICKS = target_ticks * 4  # safety ceiling
    for tick_idx in range(MAX_TICKS):
        for i, racer in enumerate(racers):
            if finished[i]:
                continue
            spd = _pet_speed(racer["stats"], racer.get("pet_data"))
            accum[i] += spd
            while accum[i] >= segment_threshold and progress[i] < MAX_SEGMENTS:
                accum[i] -= segment_threshold
                progress[i] += 1
            if progress[i] >= MAX_SEGMENTS:
                finished[i] = True
                finish_tick[i] = tick_idx

        ticks.append(list(progress))
        if all(finished):
            break

    # Fill in finish_tick for any racer that never reached MAX_SEGMENTS
    for i in range(len(racers)):
        if finish_tick[i] is None:
            finish_tick[i] = MAX_TICKS

    return ticks, finish_tick

# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/casino/races/start")
async def races_start(request: Request):
    """
    Start a race.
    Body: {difficulty: str, bet: int, fun_mode: bool}
    Returns full race simulation so client can animate it.
    """
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    try:
        body       = await request.json()
        difficulty = str(body.get("difficulty", "apprentice")).lower()
        bet        = int(body.get("bet", 0))
        fun_mode   = bool(body.get("fun_mode", False))
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    if difficulty not in DIFF_MULTS:
        difficulty = "apprentice"

    async with _get_user_lock(user_id):
        return await _races_start_inner(request, user_id, difficulty, bet, fun_mode)

async def _races_start_inner(request: Request, user_id: str, difficulty: str, bet: int, fun_mode: bool):
    # Load player pet
    pet = await user_data_manager.get_pet_data_async(user_id)
    if not pet:
        return JSONResponse({"error": "No pet found"}, status_code=404)

    if not fun_mode:
        if bet < 10:
            return JSONResponse({"error": "Minimum bet is 10 XP"}, status_code=400)
        total_xp = _compute_total_xp(pet)
        if bet > total_xp:
            return JSONResponse({"error": "Insufficient XP"}, status_code=400)
        await LootCalculator.apply_xp_change(int(user_id), -bet, source="race_bet")

    # Existing session — carry over win streak
    existing = _get_game_for_user(user_id)
    win_streak  = existing["win_streak"]  if existing else 0
    pending_xp  = existing["pending_xp"]  if existing else 0
    pending_keys = existing["pending_keys"] if existing else []
    total_bet_this_streak = existing.get("total_bet_this_streak", 0) if existing else 0
    if not fun_mode:
        total_bet_this_streak += bet

    # Build racers
    player_species = str(pet.get("species", "Cat"))

    racers = [{
        "id":      "player",
        "name":    "You",
        "species": player_species,
        "img":     f"/static/Emojis/Pets/{player_species}.png",
        "is_player": True,
        "pet_data": pet,  # Include pet data for ability tree effects
        "stats": {
            "DEX": float(pet.get("DEX", 1)),
            "ENE": float(pet.get("ENE", 1)),
            "HAP": float(pet.get("HAP", 1)),
        }
    }]

    used_species = {player_species}

    # Scale bot stats relative to the player's speed stats so difficulty is always felt
    # Easy:    bots run at 75–90% of player stats  → player should win most of the time
    # Average: bots run at 90–110% of player stats → roughly even
    # Hard:    bots run at 110–130% of player stats → player needs to be lucky
    player_dex = float(pet.get("DEX", 1))
    player_ene = float(pet.get("ENE", 1))
    player_hap = float(pet.get("HAP", 1))

    DIFF_SCALE = {
        "apprentice": (0.75, 0.90),
        "journeyman": (0.90, 1.10),
        "senior":     (1.10, 1.30),
        # web aliases
        "easy":       (0.75, 0.90),
        "average":    (0.90, 1.10),
        "hard":       (1.10, 1.30),
    }
    scale_lo, scale_hi = DIFF_SCALE.get(difficulty, (0.90, 1.10))

    for i in range(3):
        sp = random.choice([s for s in ALL_PETS if s not in used_species] or ALL_PETS)
        used_species.add(sp)
        racers.append({
            "id":      f"bot_{i}",
            "name":    BOT_NAMES[i],
            "species": sp,
            "img":     f"/static/Emojis/Pets/{sp}.png",
            "is_player": False,
            "stats": {
                "DEX": max(1.0, player_dex * random.uniform(scale_lo, scale_hi)),
                "ENE": max(1.0, player_ene * random.uniform(scale_lo, scale_hi)),
                "HAP": max(1.0, player_hap * random.uniform(scale_lo, scale_hi)),
            }
        })

    # Target tick count controls race duration — difficulty adds more ticks for drama
    target_ticks = {"apprentice": 55, "journeyman": 65, "senior": 75}.get(difficulty, 60)

    # Simulate
    ticks, finish_tick = _simulate_race(racers, target_ticks=target_ticks)

    # Determine finish order by who crossed the line first (lowest finish_tick wins)
    finish_order = sorted(range(len(racers)), key=lambda i: finish_tick[i])
    winner_idx   = finish_order[0]
    player_won   = racers[winner_idx]["is_player"]

    # Settle
    if player_won:
        win_streak += 1
        payout_mult = PAYOUT_MULTS[difficulty]
        streak_mult = 1
        if win_streak >= 9:   streak_mult = 8
        elif win_streak >= 6: streak_mult = 4
        elif win_streak >= 3: streak_mult = 2

        win_amount = int(bet * payout_mult * streak_mult) if not fun_mode else 0
        pending_xp += win_amount

        if win_streak >= 9:
            pending_keys.extend(["Key1", "Key2", "Key3"])
        elif win_streak >= 6:
            pending_keys.append("Key3")
        elif win_streak >= 3:
            pending_keys.append("Key2")
        else:
            pending_keys.append("Key1")
    else:
        # Loss will be tracked when session ends (cashout/quit) to avoid double-counting
        win_streak   = 0
        pending_xp   = 0
        pending_keys = []

    game = {
        "difficulty":   difficulty,
        "bet":          bet,
        "fun_mode":     fun_mode,
        "win_streak":   win_streak,
        "pending_xp":   pending_xp,
        "pending_keys": pending_keys,
        "player_won":   player_won,
        "winner_name":  racers[winner_idx]["name"],
        "winner_species": racers[winner_idx]["species"],
        "total_bet_this_streak": total_bet_this_streak if player_won else 0,
    }
    _set_game_for_user(user_id, game)

    # ── Per-race stat tracking (races_played + races_won/lost per race) ───────
    if not fun_mode:
        try:
            xp_delta = win_amount if player_won else -bet
            await user_data_manager.update_pet_gambling_stats(
                user_id, "races", xp_delta, bet_amount=bet
            )
        except Exception as e:
            logger.debug(f"races per-race stat error: {e}")

    # ── Task tracking ─────────────────────────────────────────────────────────
    try:
        from web.api.tasks_api import record_action as _task_record
        await _task_record(user_id, "race_play")
        if player_won:
            await _task_record(user_id, "race_win")
    except Exception as e:
        logger.debug(f"races task tracking error: {e}")

    # Racer info for client (strip stats)
    racer_info = [{"id": r["id"], "name": r["name"], "species": r["species"],
                   "img": r["img"], "is_player": r["is_player"]} for r in racers]

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("races_start", {"user_id": user_id, "difficulty": difficulty, "bet": bet, "player_won": player_won})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("race_start", 500)

    return JSONResponse({
        "racers":        racer_info,
        "ticks":         ticks,
        "finish_order":  finish_order,
        "player_won":    player_won,
        "winner_name":   racers[winner_idx]["name"],
        "win_streak":    win_streak,
        "pending_xp":    pending_xp,
        "pending_keys":  pending_keys,
        "fun_mode":      fun_mode,
        "bet":           bet,
        "difficulty":    difficulty,
        "max_segments":  MAX_SEGMENTS,
        "tick_ms":       180,
        "animation": animation
    })


@router.post("/casino/races/cashout")
async def races_cashout(request: Request):
    """Cash out pending winnings."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    game = _get_game_for_user(user_id)
    if not game:
        return JSONResponse({"error": "No active session"}, status_code=400)

    async with _get_user_lock(user_id):
        pending_xp   = game.get("pending_xp", 0)
        pending_keys = game.get("pending_keys", [])
        fun_mode     = game.get("fun_mode", False)

        if not fun_mode and pending_xp > 0:
            await LootCalculator.apply_xp_change(int(user_id), pending_xp, source="race_win")

        # Stats are now tracked per-race in _races_start_inner — no double-count here

        if not fun_mode and pending_keys:
            pet = await user_data_manager.get_pet_data_async(user_id)
            if pet:
                for key_name in pending_keys:
                    await LootCalculator.add_item_to_inventory(
                        int(user_id), {"name": key_name, "type": "Key"}, pet
                    )

        _clear_game_for_user(user_id)

        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("races_cashout", {"user_id": user_id, "cashed_xp": pending_xp, "cashed_keys": len(pending_keys)})
        await queue.flush()

        # Build items list for animation
        items = []
        if pending_xp > 0:
            items.append({"name": f"{pending_xp} XP", "rarity": "Common"})
        for key in pending_keys:
            items.append({"name": key, "rarity": "Uncommon"})
        animation = AnimationComponent.for_loot(items)

        return JSONResponse({
            "ok":          True,
            "cashed_xp":   pending_xp,
            "cashed_keys": pending_keys,
            "fun_mode":    fun_mode,
            "animation": animation
        })


@router.post("/casino/races/quit")
async def races_quit(request: Request):
    """Abandon pending winnings and clear session."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    # Stats already tracked per-race — just clear the session
    _clear_game_for_user(user_id)

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("races_quit", {"user_id": user_id})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("race_quit", 300)

    return JSONResponse({"ok": True, "animation": animation})


@router.get("/casino/races/state")
async def races_state(request: Request):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    game = _get_game(request.session)
    if not game:
        return JSONResponse({"active": False})
    return JSONResponse({"active": True, **game})


# ── Shared room race state (room_id → race) ───────────────────────────────────
_room_races: Dict[int, dict] = {}
_room_race_locks: Dict[int, asyncio.Lock] = {}

def _get_room_race_lock(room_id: int) -> asyncio.Lock:
    if room_id not in _room_race_locks:
        _room_race_locks[room_id] = asyncio.Lock()
    return _room_race_locks[room_id]


@router.get("/casino/races/room/state")
async def races_room_state(request: Request):
    """Get shared race state for a room (observers + racers)."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)

    try:
        room_id = int(request.query_params.get("room_id", -1))
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    race = _room_races.get(room_id)
    if not race:
        return JSONResponse({"active": False})

    return JSONResponse({"active": True, **race})


@router.post("/casino/races/room/start")
async def races_room_start(request: Request):
    """
    Start a shared race in a casino room.
    All seated players race; observers can bet on racers.
    Body: {room_id, difficulty, bet, fun_mode}
    """
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    try:
        body       = await request.json()
        room_id    = int(body.get("room_id", -1))
        difficulty = str(body.get("difficulty", "apprentice")).lower()
        bet        = int(body.get("bet", 0))
        fun_mode   = bool(body.get("fun_mode", False))
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    if difficulty not in DIFF_MULTS:
        difficulty = "apprentice"

    async with _get_room_race_lock(room_id):
        # Gather all seated players from the lobby room
        try:
            from web.api.casino_lobby_api import _casino_rooms
            lobby_room = _casino_rooms.get(room_id)
            seated_users = [o["user_id"] for o in (lobby_room.occupants if lobby_room else [])]
        except Exception:
            seated_users = [user_id]

        if user_id not in seated_users:
            seated_users = [user_id] + seated_users

        racers = []
        racer_bets: Dict[str, int] = {}  # user_id → bet amount

        for uid in seated_users:
            pet = await user_data_manager.get_pet_data_async(uid)
            if not pet:
                continue

            if not fun_mode and bet > 0:
                total_xp = _compute_total_xp(pet)
                if bet > total_xp:
                    continue  # skip players who can't afford the bet
                await LootCalculator.apply_xp_change(int(uid), -bet, source="race_bet")
                racer_bets[uid] = bet

            species = str(pet.get("species", "Cat"))
            racers.append({
                "id":        uid,
                "name":      pet.get("name", "Unknown"),
                "species":   species,
                "img":       f"/static/Emojis/Pets/{species}.png",
                "is_player": True,
                "user_id":   uid,
                "stats": {
                    "DEX": float(pet.get("DEX", 1)),
                    "ENE": float(pet.get("ENE", 1)),
                    "HAP": float(pet.get("HAP", 1)),
                }
            })

        # Add bots to fill up to 4 racers
        used_species = {r["species"] for r in racers}
        stat_lo, stat_hi = BOT_STAT_RANGES[difficulty]

        while len(racers) < 4:
            sp = random.choice([s for s in ALL_PETS if s not in used_species] or ALL_PETS)
            used_species.add(sp)
            idx = len(racers) - len(seated_users)
            racers.append({
                "id":        f"bot_{idx}",
                "name":      BOT_NAMES[idx % len(BOT_NAMES)],
                "species":   sp,
                "img":       f"/static/Emojis/Pets/{sp}.png",
                "is_player": False,
                "stats": {
                    "DEX": random.uniform(stat_lo, stat_hi),
                    "ENE": random.uniform(stat_lo, stat_hi),
                    "HAP": random.uniform(stat_lo, stat_hi),
                }
            })

        target_ticks = {"apprentice": 55, "journeyman": 65, "senior": 75}.get(difficulty, 60)
        ticks, finish_tick = _simulate_race(racers, target_ticks=target_ticks)

        finish_order = sorted(range(len(racers)), key=lambda i: finish_tick[i])
        winner_idx   = finish_order[0]
        winner       = racers[winner_idx]

        # Settle bets for real players
        payout_mult = PAYOUT_MULTS[difficulty]
        payouts: Dict[str, int] = {}
        for uid, wagered in racer_bets.items():
            racer = next((r for r in racers if r.get("user_id") == uid), None)
            if racer and racer["id"] == winner["id"]:
                payout = int(wagered * payout_mult)
                await LootCalculator.apply_xp_change(int(uid), payout, source="race_win")
                payouts[uid] = payout
            else:
                payouts[uid] = 0

        # Settle observer bets
        try:
            from web.api.casino_lobby_api import _casino_rooms
            lobby_room = _casino_rooms.get(room_id)
            if lobby_room and lobby_room.observer_bets:
                for bettor_id, bets in list(lobby_room.observer_bets.items()):
                    for target_id, amount in bets.items():
                        if target_id == winner["id"] or target_id == winner.get("user_id"):
                            payout = int(amount * payout_mult)
                            await LootCalculator.apply_xp_change(int(bettor_id), payout, source="observer_bet_win")
                lobby_room.observer_bets = {}
        except Exception as e:
            logger.warning(f"Could not settle observer bets: {e}")

        racer_info = [{"id": r["id"], "name": r["name"], "species": r["species"],
                       "img": r["img"], "is_player": r["is_player"],
                       "user_id": r.get("user_id")} for r in racers]

        race_result = {
            "room_id":      room_id,
            "racers":       racer_info,
            "ticks":        ticks,
            "finish_order": finish_order,
            "winner_id":    winner["id"],
            "winner_name":  winner["name"],
            "difficulty":   difficulty,
            "fun_mode":     fun_mode,
            "bet":          bet,
            "payouts":      payouts,
            "max_segments": MAX_SEGMENTS,
            "tick_ms":      180,
        }
        _room_races[room_id] = race_result

        # Add pending racers for next race
        try:
            from web.api.casino_lobby_api import _casino_rooms
            lobby_room = _casino_rooms.get(room_id)
            if lobby_room:
                for pending in lobby_room.pending_racers:
                    lobby_room.observers = [o for o in lobby_room.observers if o["user_id"] != pending["user_id"]]
                    lobby_room.occupants.append(pending)
                    lobby_room.add_activity(f"🏁 {pending['username']} will race next round!")
                lobby_room.pending_racers = []
        except Exception:
            pass

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("races_room_start", {"user_id": user_id, "room_id": room_id, "difficulty": difficulty, "bet": bet, "winner_id": winner["id"]})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("race_start", 500)

    race_result["animation"] = animation
    return JSONResponse(race_result)


@router.post("/casino/races/room/join")
async def races_room_join(request: Request):
    """
    Observer joins the race as a racer (queued for next race).
    Body: {room_id, bet, fun_mode}
    """
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user["id"])

    try:
        body     = await request.json()
        room_id  = int(body.get("room_id", -1))
        bet      = int(body.get("bet", 0))
        fun_mode = bool(body.get("fun_mode", False))
    except Exception:
        return JSONResponse({"error": "Bad request"}, status_code=400)

    try:
        from web.api.casino_lobby_api import _casino_rooms
        lobby_room = _casino_rooms.get(room_id)
        if not lobby_room:
            return JSONResponse({"error": "Room not found"}, status_code=404)

        if not lobby_room.is_observer(user_id):
            return JSONResponse({"error": "You must be observing the room first"}, status_code=400)

        obs = next((o for o in lobby_room.observers if o["user_id"] == user_id), None)
        if obs and not any(p["user_id"] == user_id for p in lobby_room.pending_racers):
            lobby_room.pending_racers.append(dict(obs))
            lobby_room.add_activity(f"🏁 {obs['username']} will join the next race!")
            from web.api.casino_lobby_api import _broadcast_casino_rooms
            await _broadcast_casino_rooms()
    except Exception as e:
        logger.warning(f"races_room_join error: {e}")

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("races_room_join", {"user_id": user_id, "room_id": room_id})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("race_join", 300)

    return JSONResponse({"ok": True, "message": "You'll race in the next round", "animation": animation})

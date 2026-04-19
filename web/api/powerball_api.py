"""
Pet Powerball API
=================
A daily lottery where players buy tickets with XP.
Drawing happens at UTC midnight (same as the tasks reset).

Ticket structure
----------------
  5 pets (ordered) + optional Elemental Multiplier (1 element)

Matching rules (order matters — must match exact draw order)
------------------------------------------------------------
  3 pets match (no EM)   → Tier 3 payout
  3 pets + EM match      → Tier 3 × EM_MULT
  4 pets match (no EM)   → Tier 2 payout
  4 pets + EM match      → Tier 2 × EM_MULT
  5 pets match (no EM)   → Tier 1 payout  (fixed % of pot)
  5 pets + EM match      → MEGA JACKPOT   (full pot)

Ticket cost
-----------
  base_cost = pet_level × equipment_multiplier × 500
  with_em   = base_cost × 1.5   (50 % surcharge for the EM ball)

Pot mechanics
-------------
  • 80 % of every ticket purchase goes into the pot.
  • Tier 3 / Tier 2 payouts are fixed XP amounts (not from pot).
  • Tier 1 (5-match, no EM) pays 25 % of the pot.
  • MEGA JACKPOT (5-match + EM) pays 100 % of the pot.
  • If no winner at midnight the pot rolls over to the next day.
  • After a MEGA win the pot resets to a seed of 50,000 XP.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.pet_brain import LootCalculator, StatsCalculator

logger = logging.getLogger("powerball_api")
router = APIRouter()

# ── Constants ─────────────────────────────────────────────────────────────────

DB_PATH = "c:/Users/codyr/DiscordBots/Reaper/Databases/powerball.db"
POT_SEED = 50_000          # XP seeded into a fresh pot after a MEGA win
POT_TICKET_SHARE = 0.80    # fraction of ticket cost added to pot
TICKET_BASE_MULT = 500     # base multiplier: level × equip_mult × 500
EM_SURCHARGE = 1.5         # ticket costs 50 % more when EM is included

# Fixed payouts for partial matches (not from pot)
TIER3_PAYOUT = 5_000       # 3 pets match (no EM)
TIER3_EM_PAYOUT = 15_000   # 3 pets + EM match
TIER2_PAYOUT = 50_000      # 4 pets match (no EM)
TIER2_EM_PAYOUT = 150_000  # 4 pets + EM match
TIER1_POT_SHARE = 0.25     # 5 pets match (no EM) → 25 % of pot

ALL_PETS: List[str] = [
    "Alligator","Ant","Anteater","Axolotl","Badger","Bat","Beaver","Bee","Beetle","Bison",
    "BlueTang","Camel","Cardinal","Cat","Centipede","Cheetah","Chicken","Clownfish","Cow",
    "Crab","Crow","Deer","Dog","Dolphin","Duck","Eagle","Elephant","Emu","Firefly","Fox",
    "Frog","Giraffe","Goat","Goose","Gorilla","Grizzly","Hamster","Hedgehog","Hippo",
    "Horse","Hummingbird","Iguana","Jaguar","Jellyfish","Kangaroo","Kiwi","Koala",
    "Ladybug","Lemur","Leopard","Lion","Llama","Mantis","Monkey","Mouse","Octopus",
    "Orangutan","Orca","Ostrich","Otter","Owl","Panda","Parrot","Peacock","Pelican",
    "Penguin","Pig","Pigeon","Platypus","PolarBear","Pufferfish","Rabbit","Raccoon",
    "Ram","Rat","RedPanda","Reindeer","Rhino","Salmon","Scorpion","Seahorse","Seal",
    "Shark","Sheep","Shrimp","Skunk","Sloth","Snail","Snake","Spider","Squirrel",
    "Starfish","Stingray","SugarGlider","Tiger","Toucan","Turkey","Turtle","Walrus",
    "Whale","Wolf","Yak","Zebra",
]

ALL_ELEMENTS: List[str] = [
    "Air","Basic","Electric","Fire","Holy","Ice","Magic","Necro","Plant","Rock",
    "Water","Psychic","Fighting",
]

# ── Per-user locks ─────────────────────────────────────────────────────────────
_user_locks: Dict[str, asyncio.Lock] = {}

def _get_user_lock(uid: str) -> asyncio.Lock:
    if uid not in _user_locks:
        _user_locks[uid] = asyncio.Lock()
    return _user_locks[uid]

# ── DB helpers ─────────────────────────────────────────────────────────────────

def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def _ensure_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        # Pot state — one row, keyed by draw_date
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pb_pot (
                draw_date   TEXT PRIMARY KEY,
                pot_xp      INTEGER NOT NULL DEFAULT 0,
                drawn       INTEGER NOT NULL DEFAULT 0,
                draw_result TEXT
            )
        """)
        # Tickets — one row per user per draw_date
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pb_tickets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT NOT NULL,
                draw_date   TEXT NOT NULL,
                pets        TEXT NOT NULL,
                element     TEXT,
                cost        INTEGER NOT NULL,
                pot_contrib INTEGER NOT NULL,
                purchased_at TEXT NOT NULL,
                UNIQUE(user_id, draw_date)
            )
        """)
        # Draw history — one row per completed draw
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pb_draws (
                draw_date    TEXT PRIMARY KEY,
                drawn_pets   TEXT NOT NULL,
                drawn_element TEXT,
                pot_before   INTEGER NOT NULL,
                pot_after    INTEGER NOT NULL,
                winner_count INTEGER NOT NULL DEFAULT 0,
                winners      TEXT,
                drawn_at     TEXT NOT NULL
            )
        """)
        await db.commit()


async def _get_or_create_pot(draw_date: str) -> Dict[str, Any]:
    """Return the pot row for draw_date, creating it if needed."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT pot_xp, drawn, draw_result FROM pb_pot WHERE draw_date=?",
            (draw_date,)
        ) as cur:
            row = await cur.fetchone()
        if row:
            return {"pot_xp": row["pot_xp"], "drawn": bool(row["drawn"]),
                    "draw_result": json.loads(row["draw_result"]) if row["draw_result"] else None}
        # New day — seed the pot
        await db.execute(
            "INSERT INTO pb_pot(draw_date, pot_xp, drawn) VALUES(?,?,0)",
            (draw_date, POT_SEED)
        )
        await db.commit()
        return {"pot_xp": POT_SEED, "drawn": False, "draw_result": None}


async def _add_to_pot(draw_date: str, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE pb_pot SET pot_xp = pot_xp + ? WHERE draw_date=?",
            (amount, draw_date)
        )
        await db.commit()


async def _get_tickets_for_draw(draw_date: str) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id, pets, element FROM pb_tickets WHERE draw_date=?",
            (draw_date,)
        ) as cur:
            rows = await cur.fetchall()
    return [{"user_id": r["user_id"],
             "pets": json.loads(r["pets"]),
             "element": r["element"]} for r in rows]


async def _get_ticket_for_user(user_id: str, draw_date: str) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT pets, element, cost, purchased_at FROM pb_tickets WHERE user_id=? AND draw_date=?",
            (user_id, draw_date)
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    return {"pets": json.loads(row["pets"]), "element": row["element"],
            "cost": row["cost"], "purchased_at": row["purchased_at"]}


# ── Ticket cost calculation ────────────────────────────────────────────────────

def _compute_ticket_cost(pet_data: Dict[str, Any], with_em: bool) -> Tuple[int, float]:
    """
    Returns (ticket_cost_xp, equipment_multiplier).
    cost = level × equip_mult × TICKET_BASE_MULT  (× EM_SURCHARGE if with_em)
    """
    level = max(1, int(pet_data.get("level", 1)))
    try:
        equip_mult = StatsCalculator.get_equipment_xp_multiplier(pet_data)
    except Exception:
        equip_mult = 1.0
    equip_mult = max(1.0, float(equip_mult))
    base = int(level * equip_mult * TICKET_BASE_MULT)
    if with_em:
        base = int(base * EM_SURCHARGE)
    return max(500, base), equip_mult   # floor at 500 XP


def _compute_total_xp(pet_data: Dict[str, Any]) -> int:
    lvl = int(pet_data.get("level", 1))
    rem = int(pet_data.get("experience", 0))
    return int(LootCalculator.get_total_experience_for_level(lvl)) + rem


def _pet_img(name: str) -> str:
    return f"/static/Emojis/Pets/{name}.png"


def _elem_img(name: str) -> str:
    return f"/static/Emojis/Pets/Deco/{name}.png"


# ── Draw logic ─────────────────────────────────────────────────────────────────

def _score_ticket(ticket_pets: List[str], ticket_elem: Optional[str],
                  drawn_pets: List[str], drawn_elem: Optional[str]) -> Dict[str, Any]:
    """
    Compare a ticket against the draw result.
    Returns a dict with match counts and tier.
    """
    # Count ordered matches from the left
    pet_matches = sum(1 for a, b in zip(ticket_pets, drawn_pets) if a == b)
    em_match = (ticket_elem is not None and ticket_elem == drawn_elem)

    if pet_matches == 5 and em_match:
        tier = "MEGA"
    elif pet_matches == 5:
        tier = "TIER1"
    elif pet_matches == 4 and em_match:
        tier = "TIER2_EM"
    elif pet_matches == 4:
        tier = "TIER2"
    elif pet_matches == 3 and em_match:
        tier = "TIER3_EM"
    elif pet_matches == 3:
        tier = "TIER3"
    else:
        tier = "NONE"

    return {"pet_matches": pet_matches, "em_match": em_match, "tier": tier}


async def run_daily_draw(draw_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Execute the daily Powerball draw for draw_date (defaults to today UTC).
    Called by the midnight scheduler.  Safe to call multiple times — skips if
    already drawn.
    """
    await _ensure_db()
    if draw_date is None:
        draw_date = _utc_today()

    pot = await _get_or_create_pot(draw_date)
    if pot["drawn"]:
        logger.info(f"Powerball: draw for {draw_date} already completed, skipping.")
        return pot["draw_result"] or {}

    # Draw 5 pets (without replacement) and 1 element
    drawn_pets = random.sample(ALL_PETS, 5)
    drawn_elem = random.choice(ALL_ELEMENTS)
    pot_before = pot["pot_xp"]

    tickets = await _get_tickets_for_draw(draw_date)
    winners: List[Dict[str, Any]] = []
    pot_after = pot_before

    # Score every ticket
    scored = []
    for t in tickets:
        score = _score_ticket(t["pets"], t["element"], drawn_pets, drawn_elem)
        if score["tier"] != "NONE":
            scored.append({**t, **score})

    # Calculate payouts — MEGA / TIER1 come from pot; others are fixed
    mega_winners = [s for s in scored if s["tier"] == "MEGA"]
    tier1_winners = [s for s in scored if s["tier"] == "TIER1"]

    # Determine pot payouts
    if mega_winners:
        # Split full pot among MEGA winners
        share = pot_before // len(mega_winners) if mega_winners else 0
        for w in mega_winners:
            w["payout"] = share
        pot_after = POT_SEED   # reset to seed
    elif tier1_winners:
        # Split 25 % of pot among TIER1 winners
        tier1_pool = int(pot_before * TIER1_POT_SHARE)
        share = tier1_pool // len(tier1_winners) if tier1_winners else 0
        for w in tier1_winners:
            w["payout"] = share
        pot_after = pot_before - tier1_pool
    # else pot rolls over unchanged

    # Fixed payouts for lower tiers
    FIXED = {
        "TIER2_EM": TIER2_EM_PAYOUT,
        "TIER2":    TIER2_PAYOUT,
        "TIER3_EM": TIER3_EM_PAYOUT,
        "TIER3":    TIER3_PAYOUT,
    }
    for s in scored:
        if s["tier"] in FIXED:
            s["payout"] = FIXED[s["tier"]]

    # Deliver payouts
    for s in scored:
        payout = s.get("payout", 0)
        if payout > 0:
            try:
                await LootCalculator.apply_xp_change(
                    int(s["user_id"]), payout, source="powerball_win"
                )
                await user_data_manager.update_pet_gambling_stats(
                    s["user_id"], "powerball", payout, bet_amount=0
                )
            except Exception as e:
                logger.error(f"Powerball payout error for {s['user_id']}: {e}")
        winners.append({
            "user_id":    s["user_id"],
            "tier":       s["tier"],
            "pet_matches": s["pet_matches"],
            "em_match":   s["em_match"],
            "payout":     payout,
        })

    draw_result = {
        "draw_date":    draw_date,
        "drawn_pets":   drawn_pets,
        "drawn_element": drawn_elem,
        "pot_before":   pot_before,
        "pot_after":    pot_after,
        "winner_count": len(winners),
        "winners":      winners,
        "drawn_at":     datetime.now(timezone.utc).isoformat(),
    }

    # Persist
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE pb_pot SET pot_xp=?, drawn=1, draw_result=? WHERE draw_date=?",
            (pot_after, json.dumps(draw_result), draw_date)
        )
        # Ensure tomorrow's pot row exists with the rolled-over amount
        tomorrow = _next_draw_date(draw_date)
        await db.execute(
            "INSERT OR IGNORE INTO pb_pot(draw_date, pot_xp, drawn) VALUES(?,?,0)",
            (tomorrow, pot_after)
        )
        await db.execute(
            """INSERT OR REPLACE INTO pb_draws
               (draw_date, drawn_pets, drawn_element, pot_before, pot_after,
                winner_count, winners, drawn_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (draw_date, json.dumps(drawn_pets), drawn_elem,
             pot_before, pot_after, len(winners),
             json.dumps(winners), draw_result["drawn_at"])
        )
        await db.commit()

    logger.info(
        f"Powerball draw {draw_date}: pets={drawn_pets} elem={drawn_elem} "
        f"pot={pot_before}→{pot_after} winners={len(winners)}"
    )
    return draw_result


def _next_draw_date(from_date: str) -> str:
    from datetime import timedelta
    d = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return (d + timedelta(days=1)).strftime("%Y-%m-%d")


# ── API endpoints ──────────────────────────────────────────────────────────────

@router.get("/powerball/info")
async def get_powerball_info(request: Request):
    """Return current pot, draw date, and whether the user already has a ticket."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    await _ensure_db()
    draw_date = _utc_today()
    pot = await _get_or_create_pot(draw_date)
    ticket = await _get_ticket_for_user(user_id, draw_date)

    pet_data = await user_data_manager.get_pet_data_async(user_id)
    if not pet_data:
        return JSONResponse({"has_pet": False})

    cost_no_em, equip_mult = _compute_ticket_cost(pet_data, False)
    cost_with_em, _ = _compute_ticket_cost(pet_data, True)
    total_xp = _compute_total_xp(pet_data)

    # Last draw result (yesterday)
    from datetime import timedelta
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    last_draw: Optional[Dict] = None
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT drawn_pets, drawn_element, pot_before, pot_after, winner_count, winners, drawn_at "
            "FROM pb_draws WHERE draw_date=?", (yesterday,)
        ) as cur:
            row = await cur.fetchone()
    if row:
        last_draw = {
            "draw_date":     yesterday,
            "drawn_pets":    json.loads(row["drawn_pets"]),
            "drawn_element": row["drawn_element"],
            "pot_before":    row["pot_before"],
            "pot_after":     row["pot_after"],
            "winner_count":  row["winner_count"],
            "winners":       json.loads(row["winners"]) if row["winners"] else [],
            "drawn_at":      row["drawn_at"],
        }

    return JSONResponse({
        "has_pet":       True,
        "draw_date":     draw_date,
        "pot_xp":        pot["pot_xp"],
        "already_drawn": pot["drawn"],
        "ticket":        ticket,
        "cost_no_em":    cost_no_em,
        "cost_with_em":  cost_with_em,
        "equip_mult":    round(equip_mult, 3),
        "pet_level":     pet_data.get("level", 1),
        "total_xp":      total_xp,
        "pets":          [{"name": p, "path": _pet_img(p)} for p in ALL_PETS],
        "elements":      [{"name": e, "path": _elem_img(e)} for e in ALL_ELEMENTS],
        "last_draw":     last_draw,
        "payouts": {
            "TIER3":    TIER3_PAYOUT,
            "TIER3_EM": TIER3_EM_PAYOUT,
            "TIER2":    TIER2_PAYOUT,
            "TIER2_EM": TIER2_EM_PAYOUT,
            "TIER1":    "25% of pot",
            "MEGA":     "100% of pot",
        },
    })


@router.post("/powerball/buy")
async def buy_ticket(request: Request):
    """
    Purchase a Powerball ticket for today's draw.
    Body: { pets: [str×5], element: str|null }
    One ticket per user per draw day.
    """
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    pets: List[str] = data.get("pets", [])
    element: Optional[str] = data.get("element") or None

    # Validate
    if len(pets) != 5:
        return JSONResponse({"error": "Must pick exactly 5 pets"}, status_code=400)
    if not all(p in ALL_PETS for p in pets):
        return JSONResponse({"error": "Invalid pet selection"}, status_code=400)
    if len(set(pets)) != 5:
        return JSONResponse({"error": "All 5 pets must be different"}, status_code=400)
    if element is not None and element not in ALL_ELEMENTS:
        return JSONResponse({"error": "Invalid element"}, status_code=400)

    await _ensure_db()
    draw_date = _utc_today()

    async with _get_user_lock(user_id):
        # Check pot not already drawn
        pot = await _get_or_create_pot(draw_date)
        if pot["drawn"]:
            return JSONResponse({"error": "Today's draw has already happened. Wait for tomorrow!"}, status_code=400)

        # Check existing ticket
        existing = await _get_ticket_for_user(user_id, draw_date)
        if existing:
            return JSONResponse({"error": "You already have a ticket for today's draw."}, status_code=400)

        # Get pet data
        pet_data = await user_data_manager.get_pet_data_async(user_id)
        if not pet_data:
            return JSONResponse({"error": "No pet found"}, status_code=404)

        with_em = element is not None
        cost, equip_mult = _compute_ticket_cost(pet_data, with_em)
        total_xp = _compute_total_xp(pet_data)

        if cost > total_xp:
            return JSONResponse({
                "error": f"Insufficient XP. Ticket costs {cost:,} XP but you only have {total_xp:,} XP."
            }, status_code=400)

        # Deduct XP
        await LootCalculator.apply_xp_change(int(user_id), -cost, source="powerball_ticket")

        # Add 80 % to pot
        pot_contrib = int(cost * POT_TICKET_SHARE)
        await _add_to_pot(draw_date, pot_contrib)

        # Save ticket
        now_str = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO pb_tickets
                   (user_id, draw_date, pets, element, cost, pot_contrib, purchased_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (user_id, draw_date, json.dumps(pets), element, cost, pot_contrib, now_str)
            )
            await db.commit()

        # Update gambling stats
        await user_data_manager.update_pet_gambling_stats(
            user_id, "powerball", -cost, bet_amount=cost
        )

        # Task tracking
        try:
            from web.api.tasks_api import record_action as _task_record
            await _task_record(user_id, "buy_powerball")
        except Exception:
            pass

        # Refresh pot display
        pot_updated = await _get_or_create_pot(draw_date)

        return JSONResponse({
            "success":    True,
            "draw_date":  draw_date,
            "pets":       pets,
            "element":    element,
            "cost":       cost,
            "pot_contrib": pot_contrib,
            "pot_xp":     pot_updated["pot_xp"],
            "purchased_at": now_str,
        })


@router.get("/powerball/history")
async def get_draw_history(request: Request):
    """Return the last 30 draw results."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)

    await _ensure_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT draw_date, drawn_pets, drawn_element, pot_before, pot_after,
                      winner_count, winners, drawn_at
               FROM pb_draws ORDER BY draw_date DESC LIMIT 30"""
        ) as cur:
            rows = await cur.fetchall()

    history = []
    for r in rows:
        history.append({
            "draw_date":     r["draw_date"],
            "drawn_pets":    json.loads(r["drawn_pets"]),
            "drawn_element": r["drawn_element"],
            "pot_before":    r["pot_before"],
            "pot_after":     r["pot_after"],
            "winner_count":  r["winner_count"],
            "winners":       json.loads(r["winners"]) if r["winners"] else [],
            "drawn_at":      r["drawn_at"],
        })
    return JSONResponse({"history": history})


@router.get("/powerball/my_tickets")
async def get_my_tickets(request: Request):
    """Return the current user's ticket history (last 30 draws)."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    await _ensure_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT draw_date, pets, element, cost, purchased_at
               FROM pb_tickets WHERE user_id=? ORDER BY draw_date DESC LIMIT 30""",
            (user_id,)
        ) as cur:
            rows = await cur.fetchall()

    tickets = []
    for r in rows:
        tickets.append({
            "draw_date":    r["draw_date"],
            "pets":         json.loads(r["pets"]),
            "element":      r["element"],
            "cost":         r["cost"],
            "purchased_at": r["purchased_at"],
        })
    return JSONResponse({"tickets": tickets})

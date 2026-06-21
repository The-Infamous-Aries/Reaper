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
  3 pets match (no EM)   → 1% of pot
  3 pets + EM match      → 2% of pot
  4 pets match (no EM)   → 5% of pot
  4 pets + EM match      → 10% of pot
  5 pets match (no EM)   → 25% of pot
  5 pets + EM match      → MEGA JACKPOT (full pot)

Ticket cost
-----------
  base_cost = pet_level × equipment_multiplier × 500
  with_em   = base_cost × 1.5   (50 % surcharge for the EM ball)

Pot mechanics
-------------
  • The house MATCHES every ticket cost 1-for-1 into the pot.
    e.g. a 1,000,000 XP ticket → 1,000,000 XP added to the pot.
  • Every player's contribution is matched, so the pot grows by the
    sum of ALL ticket costs (house matches each one individually).
  • All partial-match tiers (3–4 pets) pay a % of the pot at draw time.
  • Tier 3 (3 pets, no EM) pays 1% of the pot.
  • Tier 3 EM (3 pets + EM) pays 2% of the pot.
  • Tier 2 (4 pets, no EM) pays 5% of the pot.
  • Tier 2 EM (4 pets + EM) pays 10% of the pot.
  • Tier 1 (5-match, no EM) pays 25% of the pot.
  • MEGA JACKPOT (5-match + EM) pays 100% of the pot.
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
from Systems.Pets.Logic.event_bus import EventQueue
from Systems.Pets.Logic.pet_components import AnimationComponent
from web.api.pets.gpp_helpers import _invalidate_stats_cache, _compute_total_xp, _get_user_lock

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Constants ─────────────────────────────────────────────────────────────────

from Systems.Functions.db_paths import POWERBALL_DB_STR as DB_PATH
POT_SEED = 50_000          # XP seeded into a fresh pot after a MEGA win
POT_TICKET_SHARE = 1.0     # house matches 100% of ticket cost into the pot (1-for-1)
POT_NO_WINNER_MULT = 2.5   # multiplier applied to pot when no MEGA/TIER1 winners
TICKET_BASE_MULT = 500     # base multiplier: level × equip_mult × 500
EM_SURCHARGE = 1.5         # ticket costs 50 % more when EM is included

# Hard cap to prevent integer overflow in the SQLite INTEGER column (max 8-byte signed = ~9.2e18).
# We cap at 999.999 trillion XP so the number is always representable and human-readable.
POT_MAX = 999_999_999_999_999

# ── Ticket-count → win-probability schedule ──────────────────────────────────
# Each entry: (min_tickets, chance_of_any_win, chance_of_major_win)
#   any_win   = probability (0–1) that we force at least one synthetic winner
#               from a random tier (TIER3 / TIER3_EM / TIER2 / TIER2_EM / TIER1)
#   major_win = probability (0–1) that we specifically force a MEGA/TIER1 winner
# These are checked ONLY if no real matches exist for that tier yet.
# The schedule is applied AFTER scoring real tickets; it can add forced winners
# on top of—or instead of—the normal no-match rollover.
_WIN_SCHEDULE: List[Tuple[int, float, float]] = [
    # (min_tickets, p_any_win, p_major_win)
    (60,  0.95, 0.55),   # 60+ tickets: near-certain any-tier win, >50% major
    (50,  0.90, 0.40),   # 50+ tickets: 90% any-tier, 40% major
    (40,  0.80, 0.25),   # 40+ tickets
    (30,  0.65, 0.15),   # 30+ tickets
    (20,  0.50, 0.08),   # 20+ tickets
    (10,  0.30, 0.04),   # 10+ tickets
    (5,   0.15, 0.01),   # 5+ tickets: 15% any-tier, 1% major
    # below 5 tickets: no forced wins
]

# Pot-percentage payouts for all tiers (no hardcoded XP amounts)
TIER3_POT_SHARE    = 0.01   # 3 pets match (no EM)   → 1% of pot
TIER3_EM_POT_SHARE = 0.02   # 3 pets + EM match      → 2% of pot
TIER2_POT_SHARE    = 0.05   # 4 pets match (no EM)   → 5% of pot
TIER2_EM_POT_SHARE = 0.10   # 4 pets + EM match      → 10% of pot
TIER1_POT_SHARE    = 0.25   # 5 pets match (no EM)   → 25% of pot

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

# ── DB helpers ─────────────────────────────────────────────────────────────────

DRAW_LOCK_SECONDS = 300  # 5 minutes before/after midnight UTC


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _draw_lock_status() -> tuple[bool, str]:
    """Return (is_locked, draw_date_to_sell_for).

    Locked window: 5 min before midnight UTC (pre-draw) and 5 min after
    midnight UTC (post-draw settling).  Outside that window:
      - Before midnight  → sell for today's draw date
      - After the 5-min post-draw window → sell for tomorrow's draw date
    """
    now = datetime.now(timezone.utc)
    # Seconds elapsed since midnight UTC today
    seconds_since_midnight = now.hour * 3600 + now.minute * 60 + now.second
    # Seconds until next midnight UTC
    seconds_until_midnight = 86400 - seconds_since_midnight

    if seconds_until_midnight <= DRAW_LOCK_SECONDS:
        # Pre-draw lock: within 5 min BEFORE midnight
        return True, _next_draw_date(now.strftime("%Y-%m-%d"))
    if seconds_since_midnight < DRAW_LOCK_SECONDS:
        # Post-draw lock: within 5 min AFTER midnight
        return True, now.strftime("%Y-%m-%d")
    # Normal window — sell for today
    return False, now.strftime("%Y-%m-%d")


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
    """Return the pot row for draw_date, creating it if needed.

    When creating a new row the starting amount is inherited from the most
    recent previous draw's pot_after value so the pot always rolls over
    correctly even across server restarts.
    """
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

        # New day — inherit pot_after from the most recent completed draw,
        # falling back to POT_SEED only if there is no prior draw at all.
        async with db.execute(
            "SELECT pot_after FROM pb_draws ORDER BY draw_date DESC LIMIT 1"
        ) as cur:
            prev = await cur.fetchone()
        seed = int(prev["pot_after"]) if prev else POT_SEED
        seed = _cap_pot(seed)

        await db.execute(
            "INSERT INTO pb_pot(draw_date, pot_xp, drawn) VALUES(?,?,0)",
            (draw_date, seed)
        )
        await db.commit()
        return {"pot_xp": seed, "drawn": False, "draw_result": None}


async def _add_to_pot(draw_date: str, amount: int):
    """Add *amount* to the pot, hard-capping at POT_MAX."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE pb_pot SET pot_xp = MIN(pot_xp + ?, ?) WHERE draw_date=?",
            (amount, POT_MAX, draw_date)
        )
        await db.commit()


def _cap_pot(value: int) -> int:
    """Clamp a pot value to [0, POT_MAX]."""
    return max(0, min(int(value), POT_MAX))


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


async def update_current_pot_for_multiplier():
    """
    One-time function to apply the 2.5x multiplier to the current active pot
    if there were no major winners in recent draws.
    """
    await _ensure_db()
    today = _utc_today()
    
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Find the next undrawn pot (should be tomorrow or later)
        async with db.execute(
            "SELECT draw_date, pot_xp, drawn FROM pb_pot WHERE drawn = 0 AND draw_date > ? ORDER BY draw_date ASC LIMIT 1",
            (today,)
        ) as cur:
            current_pot = await cur.fetchone()
        
        if not current_pot:
            logger.info("No undrawn pot found")
            return None
            
        pot_date = current_pot["draw_date"]
        logger.info(f"Found undrawn pot for {pot_date}: {current_pot['pot_xp']:,} XP")
            
        # Check recent draws to see if there were major winners
        async with db.execute(
            "SELECT winners FROM pb_draws ORDER BY draw_date DESC LIMIT 3"
        ) as cur:
            recent_draws = await cur.fetchall()
            
        if recent_draws:
            # Check if any recent draw had major winners
            had_major_winners = False
            for draw in recent_draws:
                winners = json.loads(draw["winners"]) if draw["winners"] else []
                major_winners = [w for w in winners if w["tier"] in ["MEGA", "TIER1"]]
                if major_winners:
                    had_major_winners = True
                    break
            
            if not had_major_winners:
                # No major winners in recent draws, apply multiplier (capped)
                old_pot = current_pot["pot_xp"]
                new_pot = _cap_pot(int(old_pot * POT_NO_WINNER_MULT))
                
                await db.execute(
                    "UPDATE pb_pot SET pot_xp=? WHERE draw_date=?",
                    (new_pot, pot_date)
                )
                await db.commit()
                
                logger.info(f"Updated pot for {pot_date} from {old_pot:,} to {new_pot:,} XP (2.5x multiplier applied)")
                return {"old_pot": old_pot, "new_pot": new_pot, "pot_date": pot_date}
            else:
                logger.info("Recent draws had major winners, no multiplier needed")
        else:
            logger.info("No previous draws found")
    
    return None


async def run_daily_draw(draw_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Execute the daily Powerball draw for draw_date (defaults to today UTC).
    Called by the midnight scheduler.  Safe to call multiple times — skips if
    already drawn.

    Win-probability scaling
    -----------------------
    After scoring real tickets we check _WIN_SCHEDULE.  If the ticket count
    meets a threshold and the RNG fires, we inject synthetic forced winners so
    high-participation days always produce some kind of payout:
      • p_any_win   → force a random lower-tier winner (TIER3→TIER1)
      • p_major_win → force a MEGA winner (full jackpot)
    Forced winners are picked randomly from real ticket holders who didn't
    already win that tier or better.  If everyone already won we skip forcing.
    The pot is always hard-capped at POT_MAX after every mutation.
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
    pot_before = _cap_pot(pot["pot_xp"])  # always work with capped value

    tickets = await _get_tickets_for_draw(draw_date)
    ticket_count = len(tickets)
    winners: List[Dict[str, Any]] = []
    pot_after = pot_before

    # ── Score every real ticket ───────────────────────────────────────────────
    scored = []
    for t in tickets:
        score = _score_ticket(t["pets"], t["element"], drawn_pets, drawn_elem)
        if score["tier"] != "NONE":
            scored.append({**t, **score})

    # ── Ticket-count forced-win injection ─────────────────────────────────────
    # Determine which probability thresholds apply for today's participation.
    p_any_win = 0.0
    p_major_win = 0.0
    for min_t, p_any, p_major in _WIN_SCHEDULE:
        if ticket_count >= min_t:
            p_any_win = p_any
            p_major_win = p_major
            break

    if ticket_count > 0 and (p_any_win > 0 or p_major_win > 0):
        existing_tiers = {s["tier"] for s in scored}
        winners_set = {s["user_id"] for s in scored}
        non_winners = [t for t in tickets if t["user_id"] not in winners_set]

        # 1) Check for forced MAJOR win (MEGA jackpot)
        forced_major = False
        if p_major_win > 0 and random.random() < p_major_win:
            if "MEGA" not in existing_tiers and "TIER1" not in existing_tiers:
                candidates = non_winners if non_winners else tickets
                lucky = random.choice(candidates)
                scored.append({
                    "user_id": lucky["user_id"],
                    "pets": lucky["pets"],
                    "element": lucky["element"],
                    "pet_matches": 5,
                    "em_match": True,
                    "tier": "MEGA",
                    "forced": True,
                })
                forced_major = True
                logger.info(
                    f"Powerball: forced MEGA winner {lucky['user_id']} "
                    f"(ticket_count={ticket_count}, p_major={p_major_win:.2f})"
                )

        # 2) Check for forced ANY-tier win (only if major didn't fire and no high tiers exist)
        if not forced_major and p_any_win > 0 and random.random() < p_any_win:
            if not existing_tiers.intersection({"MEGA", "TIER1", "TIER2_EM", "TIER2"}):
                # Weight tier pool by participation level
                if ticket_count >= 40:
                    forced_tier_pool = ["TIER3_EM", "TIER2", "TIER2", "TIER2_EM", "TIER1", "TIER1"]
                elif ticket_count >= 20:
                    forced_tier_pool = ["TIER3", "TIER3_EM", "TIER2", "TIER2", "TIER2_EM"]
                else:
                    forced_tier_pool = ["TIER3", "TIER3", "TIER3_EM", "TIER2", "TIER2_EM", "TIER1"]
                force_tier = random.choice(forced_tier_pool)
                candidates = non_winners if non_winners else tickets
                lucky = random.choice(candidates)
                scored.append({
                    "user_id": lucky["user_id"],
                    "pets": lucky["pets"],
                    "element": lucky["element"],
                    "pet_matches": {"TIER3": 3, "TIER3_EM": 3, "TIER2": 4, "TIER2_EM": 4, "TIER1": 5}.get(force_tier, 3),
                    "em_match": force_tier.endswith("_EM"),
                    "tier": force_tier,
                    "forced": True,
                })
                logger.info(
                    f"Powerball: forced {force_tier} winner {lucky['user_id']} "
                    f"(ticket_count={ticket_count}, p_any={p_any_win:.2f})"
                )

    # ── Calculate payouts ─────────────────────────────────────────────────────
    mega_winners  = [s for s in scored if s["tier"] == "MEGA"]
    tier1_winners = [s for s in scored if s["tier"] == "TIER1"]

    if mega_winners:
        # Split full pot among MEGA winners
        share = pot_before // len(mega_winners)
        for w in mega_winners:
            w["payout"] = share
        pot_after = _cap_pot(POT_SEED)   # reset to seed
    elif tier1_winners:
        # Split 25% of pot among TIER1 winners
        tier1_pool = int(pot_before * TIER1_POT_SHARE)
        share = tier1_pool // len(tier1_winners)
        for w in tier1_winners:
            w["payout"] = share
        pot_after = _cap_pot(pot_before - tier1_pool)
    else:
        # No MEGA or TIER1 winners — pot grows 2.5x, capped
        pot_after = _cap_pot(int(pot_before * POT_NO_WINNER_MULT))
        logger.info(f"Powerball: No major winners, pot grows from {pot_before:,} to {pot_after:,} XP (2.5x multiplier)")

    # Pot-percentage payouts for lower tiers (each winner gets their own share of the pot)
    POT_PCT = {
        "TIER2_EM": TIER2_EM_POT_SHARE,
        "TIER2":    TIER2_POT_SHARE,
        "TIER3_EM": TIER3_EM_POT_SHARE,
        "TIER3":    TIER3_POT_SHARE,
    }
    for s in scored:
        if s["tier"] in POT_PCT:
            s["payout"] = max(1, int(pot_before * POT_PCT[s["tier"]]))

    # ── Deliver payouts ───────────────────────────────────────────────────────
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
            "forced":     s.get("forced", False),
        })

    draw_result = {
        "draw_date":     draw_date,
        "drawn_pets":    drawn_pets,
        "drawn_element": drawn_elem,
        "pot_before":    pot_before,
        "pot_after":     pot_after,
        "winner_count":  len(winners),
        "winners":       winners,
        "ticket_count":  ticket_count,
        "drawn_at":      datetime.now(timezone.utc).isoformat(),
    }

    # ── Persist ───────────────────────────────────────────────────────────────
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE pb_pot SET pot_xp=?, drawn=1, draw_result=? WHERE draw_date=?",
            (pot_after, json.dumps(draw_result), draw_date)
        )
        # Ensure tomorrow's pot row exists with the rolled-over amount (capped)
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
        f"pot={pot_before:,}→{pot_after:,} winners={len(winners)} tickets={ticket_count}"
    )
    return draw_result


def _next_draw_date(from_date: str) -> str:
    from datetime import timedelta
    d = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return (d + timedelta(days=1)).strftime("%Y-%m-%d")


# ── API endpoints ──────────────────────────────────────────────────────────────

@router.get("/powerball/info")
async def get_powerball_info(request: Request):
    """Return current pot, draw date, and whether the user already has a ticket.

    If today's draw has already happened we automatically advance to tomorrow's
    draw so players can immediately buy a ticket for the next round.
    """
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    await _ensure_db()
    today = _utc_today()

    draw_locked, sell_date = _draw_lock_status()

    # If the sell_date pot is already drawn (edge case: lock window after draw
    # ran but sell_date still points to today), advance to next draw.
    sell_pot = await _get_or_create_pot(sell_date)
    if sell_pot["drawn"]:
        draw_date = _next_draw_date(sell_date)
    else:
        draw_date = sell_date

    pot = await _get_or_create_pot(draw_date)
    ticket = await _get_ticket_for_user(user_id, draw_date)

    pet_data = await user_data_manager.get_pet_data_async(user_id)
    if not pet_data:
        return JSONResponse({"has_pet": False})

    cost_no_em, equip_mult = _compute_ticket_cost(pet_data, False)
    cost_with_em, _ = _compute_ticket_cost(pet_data, True)
    total_xp = _compute_total_xp(pet_data)

    # Last draw result — most recent completed draw
    last_draw: Optional[Dict] = None
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT draw_date, drawn_pets, drawn_element, pot_before, pot_after, "
            "winner_count, winners, drawn_at "
            "FROM pb_draws ORDER BY draw_date DESC LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
    if row:
        last_draw = {
            "draw_date":     row["draw_date"],
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
        "draw_locked":   draw_locked,
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
            "TIER3":    f"{int(TIER3_POT_SHARE*100)}% of pot",
            "TIER3_EM": f"{int(TIER3_EM_POT_SHARE*100)}% of pot",
            "TIER2":    f"{int(TIER2_POT_SHARE*100)}% of pot",
            "TIER2_EM": f"{int(TIER2_EM_POT_SHARE*100)}% of pot",
            "TIER1":    f"{int(TIER1_POT_SHARE*100)}% of pot",
            "MEGA":     "100% of pot",
            # Live XP estimates based on current pot
            "TIER3_xp":    int(pot["pot_xp"] * TIER3_POT_SHARE),
            "TIER3_EM_xp": int(pot["pot_xp"] * TIER3_EM_POT_SHARE),
            "TIER2_xp":    int(pot["pot_xp"] * TIER2_POT_SHARE),
            "TIER2_EM_xp": int(pot["pot_xp"] * TIER2_EM_POT_SHARE),
            "TIER1_xp":    int(pot["pot_xp"] * TIER1_POT_SHARE),
            "MEGA_xp":     pot["pot_xp"],
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
    draw_locked, draw_date = _draw_lock_status()

    async with _get_user_lock(user_id):
        # Block purchases during the ±5-minute draw window
        if draw_locked:
            return JSONResponse(
                {"error": "Tickets are paused around draw time. Try again in a few minutes!"},
                status_code=400,
            )

        # Check pot not already drawn (safety net)
        pot = await _get_or_create_pot(draw_date)
        if pot["drawn"]:
            draw_date = _next_draw_date(draw_date)
            pot = await _get_or_create_pot(draw_date)

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

        # Add 100% to pot (house matches ticket cost 1-for-1), capped at POT_MAX
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

        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("powerball_buy", {"user_id": user_id, "draw_date": draw_date, "pets": pets, "element": element, "cost": cost})
        await queue.flush()

        animation = AnimationComponent.for_ui_update("ticket_purchased", 400)

        return JSONResponse({
            "success":    True,
            "draw_date":  draw_date,
            "pets":       pets,
            "element":    element,
            "cost":       cost,
            "pot_contrib": pot_contrib,
            "pot_xp":     pot_updated["pot_xp"],
            "purchased_at": now_str,
            "animation": animation
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


@router.post("/admin/update-pot-multiplier")
async def admin_update_pot_multiplier(request: Request):
    """Admin endpoint to apply 2.5x multiplier to current pot if no major winners."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    
    # Add admin check here if needed
    # user_id = str(user.get("id"))
    # if user_id not in ADMIN_USER_IDS:
    #     return JSONResponse({"error": "Admin access required"}, status_code=403)
    
    result = await update_current_pot_for_multiplier()
    if result:
        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("powerball_pot_multiplier", {"pot_date": result["pot_date"], "old_pot": result["old_pot"], "new_pot": result["new_pot"]})
        await queue.flush()

        animation = AnimationComponent.for_ui_update("pot_multiplier_applied", 500)

        return JSONResponse({
            "success": True,
            "message": f"Pot for {result['pot_date']} updated from {result['old_pot']:,} to {result['new_pot']:,} XP",
            "old_pot": result["old_pot"],
            "new_pot": result["new_pot"],
            "pot_date": result["pot_date"],
            "animation": animation
        })
    else:
        return JSONResponse({
            "success": False,
            "message": "No pot update needed (already drawn, had major winners, or no pot found)"
        })
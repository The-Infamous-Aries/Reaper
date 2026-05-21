"""
absorb_api.py — Pet War Absorb System

Lets users absorb their PnW war wins and unit kills as pet XP.

Tracking DB: Databases/Pets/absorb.db
  - absorb_state table: one row per user, tracks:
      * locked_nation_id  — set on FIRST absorb, NEVER changes again
      * absorbed_*        — running totals of what has already been absorbed
    This means a user cannot unlink their nation and re-absorb with a
    different nation's stats. The nation is permanently bound to the pet
    the moment the first absorb happens.

XP Formulas:
  Win XP  = level × equip_mult × wins × 5000
  Unit XP = level × equip_mult × count × unit_multiplier
    unit_multipliers: soldiers=10, tanks=25, aircraft=50, ships=100
    missile_multiplier: 250, nuke_multiplier: 500

Bombs (missiles/nukes that actually destroyed infra) are counted from
war_attacks where type = 'MISSILE' or 'NUKE' (MISSILEFAIL/NUKEFAIL are
intercepts and are automatically excluded by the type filter).

Nation linking:
  - GlobalNations.db stores discord_id → nation_id mapping (updated live
    by the nations subscription whenever a player sets their Discord in PnW).
  - On status check: we look up the CURRENT discord_id → nation_id.
    If the user has a locked_nation_id in absorb_state, we use THAT instead
    and ignore whatever nation they currently have linked — prevents swapping.
  - On first absorb: we lock the current nation_id into absorb_state.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import sqlite3
import asyncio
import logging
import os
from typing import Optional, Dict, Any

from Systems.Functions.db_paths import (
    GLOBAL_NATIONS_DB_STR,
    IRS_WARS_DB_STR,
    ABSORB_DB_STR,
)
from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.pet_brain import LootCalculator, StatsCalculator
from Systems.Pets.Logic.event_bus import EventQueue
from Systems.Pets.Logic.pet_components import AnimationComponent
from web.api.pets.gpp_helpers import _invalidate_stats_cache

logger = logging.getLogger(__name__)

router = APIRouter()

_ABSORB_DB = ABSORB_DB_STR

# Unit XP multipliers (soldiers/tanks/aircraft/ships)
_UNIT_MULT = {
    "soldiers": 25,
    "tanks":    100,
    "aircraft": 500,
    "ships":    1000,
}
# Bomb XP multipliers (missiles/nukes that hit infra)
_BOMB_MULT = {
    "missiles": 10000,
    "nukes":    50000,
}

# ── DB init ────────────────────────────────────────────────────────────────────

def _init_absorb_db():
    """Create absorb.db and its tables if they don't exist."""
    os.makedirs(os.path.dirname(_ABSORB_DB), exist_ok=True)
    with sqlite3.connect(_ABSORB_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS absorb_state (
                user_id             TEXT PRIMARY KEY,
                -- locked_nation_id is set on first absorb and NEVER changes.
                -- This prevents users from unlinking their nation and absorbing
                -- a different nation's stats into the same pet.
                locked_nation_id    INTEGER,
                -- running totals of everything already absorbed (never decremented)
                absorbed_wins       INTEGER NOT NULL DEFAULT 0,
                absorbed_soldiers   INTEGER NOT NULL DEFAULT 0,
                absorbed_tanks      INTEGER NOT NULL DEFAULT 0,
                absorbed_aircraft   INTEGER NOT NULL DEFAULT 0,
                absorbed_ships      INTEGER NOT NULL DEFAULT 0,
                absorbed_missiles   INTEGER NOT NULL DEFAULT 0,
                absorbed_nukes      INTEGER NOT NULL DEFAULT 0,
                last_absorb_at      TEXT,
                created_at          TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Migrate old schema: rename nation_id → locked_nation_id if needed
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(absorb_state)").fetchall()]
            if "nation_id" in cols and "locked_nation_id" not in cols:
                conn.execute("ALTER TABLE absorb_state RENAME COLUMN nation_id TO locked_nation_id")
        except Exception:
            pass
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_absorb_updated
            AFTER UPDATE ON absorb_state
            FOR EACH ROW
            BEGIN
                UPDATE absorb_state SET updated_at = datetime('now') WHERE user_id = OLD.user_id;
            END
        """)
        conn.commit()


_init_absorb_db()


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _get_absorb_state(user_id: str) -> Optional[Dict[str, Any]]:
    with sqlite3.connect(_ABSORB_DB) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM absorb_state WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def _lock_and_update_absorb_state(user_id: str, nation_id: int, delta: Dict[str, int]) -> Dict[str, Any]:
    """
    Atomically:
      1. If no row exists → INSERT with locked_nation_id = nation_id and delta values.
      2. If row exists → UPDATE absorbed totals. locked_nation_id is NEVER overwritten.
    Returns the updated row.
    """
    with sqlite3.connect(_ABSORB_DB) as conn:
        existing = conn.execute(
            "SELECT locked_nation_id FROM absorb_state WHERE user_id = ?", (user_id,)
        ).fetchone()

        if existing is None:
            # First absorb — lock the nation permanently
            conn.execute("""
                INSERT INTO absorb_state
                    (user_id, locked_nation_id,
                     absorbed_wins, absorbed_soldiers, absorbed_tanks,
                     absorbed_aircraft, absorbed_ships,
                     absorbed_missiles, absorbed_nukes,
                     last_absorb_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                user_id, nation_id,
                delta.get("wins", 0),
                delta.get("soldiers", 0),
                delta.get("tanks", 0),
                delta.get("aircraft", 0),
                delta.get("ships", 0),
                delta.get("missiles", 0),
                delta.get("nukes", 0),
            ))
        else:
            # Nation already locked — only update the absorbed counters
            conn.execute("""
                UPDATE absorb_state SET
                    absorbed_wins     = absorbed_wins     + ?,
                    absorbed_soldiers = absorbed_soldiers + ?,
                    absorbed_tanks    = absorbed_tanks    + ?,
                    absorbed_aircraft = absorbed_aircraft + ?,
                    absorbed_ships    = absorbed_ships    + ?,
                    absorbed_missiles = absorbed_missiles + ?,
                    absorbed_nukes    = absorbed_nukes    + ?,
                    last_absorb_at    = datetime('now')
                WHERE user_id = ?
            """, (
                delta.get("wins", 0),
                delta.get("soldiers", 0),
                delta.get("tanks", 0),
                delta.get("aircraft", 0),
                delta.get("ships", 0),
                delta.get("missiles", 0),
                delta.get("nukes", 0),
                user_id,
            ))
        conn.commit()

        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM absorb_state WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row)


# ── PnW data helpers ───────────────────────────────────────────────────────────

def _get_nation_id_for_discord(discord_user_id: str) -> Optional[int]:
    """Look up the PnW nation ID currently linked to a Discord user ID."""
    try:
        with sqlite3.connect(GLOBAL_NATIONS_DB_STR) as conn:
            row = conn.execute(
                "SELECT id FROM nations WHERE discord_id = ? LIMIT 1",
                (str(discord_user_id),)
            ).fetchone()
            return row[0] if row else None
    except Exception as e:
        logger.error(f"_get_nation_id_for_discord({discord_user_id}): {e}")
        return None


def _resolve_nation_id(user_id: str, state: Optional[Dict[str, Any]]) -> tuple[Optional[int], bool]:
    """
    Determine which nation_id to use and whether it is locked.

    Returns (nation_id, is_locked):
      - If the user has already absorbed (locked_nation_id is set), return that
        nation_id and is_locked=True regardless of current Discord link.
      - Otherwise look up the current Discord → nation link and return is_locked=False.
      - Returns (None, False) if no nation can be found.
    """
    if state and state.get("locked_nation_id"):
        return int(state["locked_nation_id"]), True

    # No lock yet — look up current link
    current = _get_nation_id_for_discord(user_id)
    return current, False


def _get_war_stats_for_nation(nation_id: int) -> Dict[str, int]:
    """
    Query IRSWars.db for all ended wars involving nation_id.

    Wars table (ended wars only, is_active = 0):
      Wins:
        COUNT(*) WHERE winner_id = nation_id

      Unit kills (enemy losses = our kills):
        As attacker → SUM(def_*_lost) from wars WHERE att_id = nation_id
        As defender → SUM(att_*_lost) from wars WHERE def_id = nation_id

    war_attacks table:
      Bombs that hit infra:
        COUNT(*) WHERE attacker_id = nation_id
                   AND attack_type IN (5=missile, 6=nuke)
                   AND infra_destroyed > 0
    """
    stats: Dict[str, int] = {
        "wins": 0,
        "soldiers": 0, "tanks": 0, "aircraft": 0, "ships": 0,
        "missiles": 0, "nukes": 0,
    }

    try:
        with sqlite3.connect(IRS_WARS_DB_STR) as conn:
            conn.row_factory = sqlite3.Row

            # ── Wars won ──────────────────────────────────────────────────────
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM wars WHERE winner_id = ? AND is_active = 0",
                (nation_id,)
            ).fetchone()
            stats["wins"] = int(row["cnt"]) if row else 0

            # ── Unit kills as attacker ────────────────────────────────────────
            att = conn.execute(
                """
                SELECT
                    COALESCE(SUM(def_soldiers_lost), 0) AS soldiers,
                    COALESCE(SUM(def_tanks_lost),    0) AS tanks,
                    COALESCE(SUM(def_aircraft_lost), 0) AS aircraft,
                    COALESCE(SUM(def_ships_lost),    0) AS ships
                FROM wars WHERE att_id = ? AND is_active = 0
                """,
                (nation_id,)
            ).fetchone()

            # ── Unit kills as defender ────────────────────────────────────────
            dfn = conn.execute(
                """
                SELECT
                    COALESCE(SUM(att_soldiers_lost), 0) AS soldiers,
                    COALESCE(SUM(att_tanks_lost),    0) AS tanks,
                    COALESCE(SUM(att_aircraft_lost), 0) AS aircraft,
                    COALESCE(SUM(att_ships_lost),    0) AS ships
                FROM wars WHERE def_id = ? AND is_active = 0
                """,
                (nation_id,)
            ).fetchone()

            for src in (att, dfn):
                if src:
                    stats["soldiers"] += int(src["soldiers"] or 0)
                    stats["tanks"]    += int(src["tanks"]    or 0)
                    stats["aircraft"] += int(src["aircraft"] or 0)
                    stats["ships"]    += int(src["ships"]    or 0)

            # ── Bombs that hit (type='MISSILE'/'NUKE'; MISSILEFAIL/NUKEFAIL excluded) ──
            bombs = conn.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN type = 'MISSILE' THEN 1 ELSE 0 END), 0) AS missiles,
                    COALESCE(SUM(CASE WHEN type = 'NUKE'    THEN 1 ELSE 0 END), 0) AS nukes
                FROM war_attacks WHERE attacker_id = ?
                """,
                (nation_id,)
            ).fetchone()

            if bombs:
                stats["missiles"] += int(bombs["missiles"] or 0)
                stats["nukes"]    += int(bombs["nukes"]    or 0)

    except Exception as e:
        logger.error(f"_get_war_stats_for_nation({nation_id}): {e}", exc_info=True)

    return stats


def _compute_available(total: Dict[str, int], absorbed: Dict[str, int]) -> Dict[str, int]:
    """Return how many of each type are still available to absorb (total − absorbed, floored at 0)."""
    return {k: max(0, total.get(k, 0) - absorbed.get(k, 0)) for k in total}


# ── API endpoints ──────────────────────────────────────────────────────────────

@router.get("/pets/absorb/status")
async def absorb_status(request: Request):
    """
    Return absorb status for the logged-in user.

    Response fields:
      linked          — True if a nation is available (linked or locked)
      locked          — True if the nation is permanently locked to this pet
      nation_id       — the nation being used (locked or current)
      total           — all-time stats from IRSWars.db for that nation
      absorbed        — what has already been absorbed (from absorb.db)
      available       — total − absorbed (what can still be absorbed)
      xp_preview      — XP that would be gained per absorb type right now
    """
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not logged in"})

    user_id = str(user.get("id"))

    pet = await user_data_manager.get_pet_data_async(user_id)
    if not pet:
        return JSONResponse(status_code=404, content={"error": "No pet found"})

    state = await asyncio.to_thread(_get_absorb_state, user_id)
    nation_id, is_locked = await asyncio.to_thread(_resolve_nation_id, user_id, state)

    if not nation_id:
        return JSONResponse(content={
            "linked": False, "locked": False,
            "nation_id": None,
            "total": {}, "absorbed": {}, "available": {}, "xp_preview": {},
        })

    total = await asyncio.to_thread(_get_war_stats_for_nation, nation_id)

    absorbed = {
        "wins":     int(state["absorbed_wins"])     if state else 0,
        "soldiers": int(state["absorbed_soldiers"]) if state else 0,
        "tanks":    int(state["absorbed_tanks"])    if state else 0,
        "aircraft": int(state["absorbed_aircraft"]) if state else 0,
        "ships":    int(state["absorbed_ships"])    if state else 0,
        "missiles": int(state["absorbed_missiles"]) if state else 0,
        "nukes":    int(state["absorbed_nukes"])    if state else 0,
    }

    available = _compute_available(total, absorbed)

    level      = int(pet.get("level", 1))
    equip_mult = StatsCalculator.get_equipment_xp_multiplier(pet)

    xp_preview: Dict[str, int] = {
        "wins": int(level * equip_mult * available["wins"] * 5000)
    }
    for unit, mult in _UNIT_MULT.items():
        xp_preview[unit] = int(level * equip_mult * available.get(unit, 0) * mult)
    for bomb, mult in _BOMB_MULT.items():
        xp_preview[bomb] = int(level * equip_mult * available.get(bomb, 0) * mult)

    return JSONResponse(content={
        "linked":     True,
        "locked":     is_locked,
        "nation_id":  nation_id,
        "total":      total,
        "absorbed":   absorbed,
        "available":  available,
        "xp_preview": xp_preview,
        "pet_level":  level,
    })


@router.post("/pets/absorb/wins")
async def absorb_wins(request: Request):
    """Absorb all available war wins as XP."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not logged in"})

    user_id = str(user.get("id"))

    pet = await user_data_manager.get_pet_data_async(user_id)
    if not pet:
        return JSONResponse(status_code=404, content={"error": "No pet found"})

    state     = await asyncio.to_thread(_get_absorb_state, user_id)
    nation_id, is_locked = await asyncio.to_thread(_resolve_nation_id, user_id, state)

    if not nation_id:
        return JSONResponse(status_code=400, content={
            "error": "No PnW nation linked to your Discord account. Link your nation in-game first."
        })

    total          = await asyncio.to_thread(_get_war_stats_for_nation, nation_id)
    absorbed_wins  = int(state["absorbed_wins"]) if state else 0
    available_wins = max(0, total["wins"] - absorbed_wins)

    if available_wins <= 0:
        return JSONResponse(content={"xp_gained": 0, "wins_absorbed": 0, "message": "No new wins to absorb"})

    level      = int(pet.get("level", 1))
    equip_mult = StatsCalculator.get_equipment_xp_multiplier(pet)
    xp_gain    = int(level * equip_mult * available_wins * 5000)

    leveled_up, level_data = await LootCalculator.apply_xp_change(int(user_id), xp_gain, "absorb_wins")
    # apply_xp_change returns has_changed (True for both up and down) — check direction
    actually_leveled_up = leveled_up and level_data and level_data.get("new_level", 0) > level_data.get("old_level", 0)

    # Lock nation on first absorb, increment counter on subsequent ones
    await asyncio.to_thread(
        _lock_and_update_absorb_state,
        user_id, nation_id, {"wins": available_wins}
    )

    pet = await user_data_manager.get_pet_data_async(user_id)

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("absorb_wins", {"user_id": user_id, "wins_absorbed": available_wins, "xp_gained": xp_gain, "leveled_up": actually_leveled_up})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("absorb_wins", 500, {"xp_gained": xp_gain, "wins": available_wins})

    return JSONResponse(content={
        "xp_gained":     xp_gain,
        "wins_absorbed": available_wins,
        "leveled_up":    actually_leveled_up,
        "level_data":    level_data,
        "locked":        True,
        "nation_id":     nation_id,
        "pet":           pet,
        "message":       f"Absorbed {available_wins:,} war win{'s' if available_wins != 1 else ''} for {xp_gain:,} XP!",
        "animation": animation
    })


@router.post("/pets/absorb/kills")
async def absorb_kills(request: Request):
    """
    Absorb available unit kills as XP.
    Accepts optional JSON body: {"unit_type": "soldiers"} to absorb a single type.
    If unit_type is omitted or "all", absorbs all available types.
    """
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(status_code=401, content={"error": "Not logged in"})

    user_id = str(user.get("id"))

    # Parse optional unit_type from body
    unit_type: Optional[str] = None
    try:
        body = await request.json()
        unit_type = body.get("unit_type") or None
    except Exception:
        pass

    pet = await user_data_manager.get_pet_data_async(user_id)
    if not pet:
        return JSONResponse(status_code=404, content={"error": "No pet found"})

    state     = await asyncio.to_thread(_get_absorb_state, user_id)
    nation_id, is_locked = await asyncio.to_thread(_resolve_nation_id, user_id, state)

    if not nation_id:
        return JSONResponse(status_code=400, content={
            "error": "No PnW nation linked to your Discord account. Link your nation in-game first."
        })

    total = await asyncio.to_thread(_get_war_stats_for_nation, nation_id)

    absorbed = {
        "soldiers": int(state["absorbed_soldiers"]) if state else 0,
        "tanks":    int(state["absorbed_tanks"])    if state else 0,
        "aircraft": int(state["absorbed_aircraft"]) if state else 0,
        "ships":    int(state["absorbed_ships"])    if state else 0,
        "missiles": int(state["absorbed_missiles"]) if state else 0,
        "nukes":    int(state["absorbed_nukes"])    if state else 0,
    }

    all_available = {k: max(0, total.get(k, 0) - absorbed.get(k, 0)) for k in absorbed}

    # Filter to requested unit type(s)
    all_unit_keys = list(_UNIT_MULT.keys()) + list(_BOMB_MULT.keys())
    if unit_type and unit_type != "all" and unit_type in all_unit_keys:
        available = {k: (all_available[k] if k == unit_type else 0) for k in all_available}
    else:
        available = all_available

    if sum(available.values()) <= 0:
        return JSONResponse(content={
            "xp_gained": 0, "kills_absorbed": available,
            "message": "No new kills to absorb"
        })

    level      = int(pet.get("level", 1))
    equip_mult = StatsCalculator.get_equipment_xp_multiplier(pet)

    xp_breakdown: Dict[str, int] = {}
    total_xp = 0

    for unit, mult in _UNIT_MULT.items():
        xp = int(level * equip_mult * available.get(unit, 0) * mult)
        xp_breakdown[unit] = xp
        total_xp += xp

    for bomb, mult in _BOMB_MULT.items():
        xp = int(level * equip_mult * available.get(bomb, 0) * mult)
        xp_breakdown[bomb] = xp
        total_xp += xp

    if total_xp <= 0:
        return JSONResponse(content={
            "xp_gained": 0, "kills_absorbed": available,
            "message": "No XP to gain from available kills"
        })

    leveled_up, level_data = await LootCalculator.apply_xp_change(int(user_id), total_xp, "absorb_kills")
    actually_leveled_up = leveled_up and level_data and level_data.get("new_level", 0) > level_data.get("old_level", 0)

    await asyncio.to_thread(
        _lock_and_update_absorb_state,
        user_id, nation_id, available
    )

    pet = await user_data_manager.get_pet_data_async(user_id)

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("absorb_kills", {"user_id": user_id, "kills_absorbed": available, "xp_gained": total_xp, "leveled_up": actually_leveled_up})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("absorb_kills", 500, {"xp_gained": total_xp, "kills": available})

    return JSONResponse(content={
        "xp_gained":      total_xp,
        "xp_breakdown":   xp_breakdown,
        "kills_absorbed": available,
        "leveled_up":     actually_leveled_up,
        "level_data":     level_data,
        "animation": animation,
        "locked":         True,
        "nation_id":      nation_id,
        "pet":            pet,
        "message":        f"Absorbed {unit_type or 'all'} kills for {total_xp:,} XP!",
    })

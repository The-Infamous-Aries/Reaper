"""
my_nation_api.py — Personal nation dashboard API endpoints.

All endpoints are scoped to the requesting user's own linked nation.
Requests for other nations are rejected with HTTP 403.

Endpoints:
  GET  /api/mynation/{nation_id}               → full nation data bundle (cached 2 min)
  POST /api/mynation/goals/check-completion/{nation_id}  → auto-complete goals
  GET  /api/mynation/cost-preview              → live cost + time estimate
  GET  /api/mynation/war-stats/{nation_id}     → combat history panel
  GET  /api/mynation/goals/{nation_id}         → list goals
  POST /api/mynation/goals                     → create goal
  POST /api/mynation/goals/{goal_id}/complete  → mark goal done
  DELETE /api/mynation/goals/{goal_id}         → delete goal
  POST /api/mynation/snapshot                  → save/refresh snapshot
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

router = APIRouter()
logger = logging.getLogger("Reaper.WebServer.MyNationAPI")

# ── Leaderboard category definitions (matching leaderboard.js) ───────────────
LEADERBOARD_CATEGORIES = [
    {'id': 'lowest_cost',           'label': 'Lowest Cost',                      'field': 'gross_cost',              'prefix': 'c', 'asc': True},
    {'id': 'highest_cost',          'label': 'Highest Cost',                     'field': 'gross_cost',              'prefix': 'c', 'asc': False},
    {'id': 'best_net',              'label': 'Best Net',                         'field': 'net_damage',              'prefix': 'n', 'asc': True},
    {'id': 'most_damage',           'label': 'Most Damage Dealt',                'field': 'total_damages',           'prefix': 'n', 'asc': False},
    {'id': 'most_wins',             'label': 'Most Wins',                        'field': 'wins_count',              'prefix': 'd', 'asc': False},
    {'id': 'most_losses',           'label': 'Most Losses',                      'field': 'losses_count',            'prefix': 'p', 'asc': False},
    {'id': 'most_draws',            'label': 'Most Draws',                       'field': 'draws_count',             'prefix': 'd', 'asc': False},
    {'id': 'most_peace',            'label': 'Most Peace',                       'field': 'peace_count',             'prefix': 'p', 'asc': False},
    {'id': 'most_off_wars',         'label': 'Most Offensive Wars',              'field': 'offense_wars_count',      'prefix': 'c', 'asc': False},
    {'id': 'most_def_wars',         'label': 'Most Defensive Wars',              'field': 'defense_wars_count',      'prefix': 'c', 'asc': False},
    {'id': 'most_raid_wars',        'label': 'Most Raid Wars',                   'field': 'raid_wars_count',         'prefix': 'w', 'asc': False},
    {'id': 'most_attrition_wars',   'label': 'Most Attrition Wars',              'field': 'attrition_wars_count',    'prefix': 'w', 'asc': False},
    {'id': 'most_money_loot',       'label': 'Most Money Looted/Stolen',         'field': 'gains_cash',              'prefix': 'm', 'asc': False},
    {'id': 'most_res_loot',         'label': 'Most Resource Value Looted',       'field': 'gains_res_total',         'prefix': 'm', 'asc': False},
    {'id': 'most_infra_lvl',        'label': 'Most Infra Levels Destroyed',      'field': 'enemy_infra_destroyed',   'prefix': 'r', 'asc': False},
    {'id': 'most_infra_val',        'label': 'Most Infra Value Destroyed',       'field': 'enemy_infra_destroyed_value', 'prefix': 'r', 'asc': False},
    {'id': 'most_soldiers_killed',  'label': 'Most Soldiers Killed',             'field': 'enemy_soldiers_killed',   'prefix': 'k', 'asc': False},
    {'id': 'most_tanks_killed',     'label': 'Most Tanks Killed',                'field': 'enemy_tanks_killed',      'prefix': 'k', 'asc': False},
    {'id': 'most_aircraft_killed',  'label': 'Most Aircraft Killed',             'field': 'enemy_aircraft_killed',   'prefix': 'k', 'asc': False},
    {'id': 'most_ships_killed',     'label': 'Most Ships Killed',                'field': 'enemy_ships_killed',      'prefix': 'k', 'asc': False},
    {'id': 'most_soldiers_lost',    'label': 'Most Soldiers Lost',               'field': 'soldiers_lost',           'prefix': 'l', 'asc': False},
    {'id': 'most_tanks_lost',       'label': 'Most Tanks Lost',                  'field': 'tanks_lost',              'prefix': 'l', 'asc': False},
    {'id': 'most_aircraft_lost',    'label': 'Most Aircraft Lost',               'field': 'aircraft_lost',           'prefix': 'l', 'asc': False},
    {'id': 'most_ships_lost',       'label': 'Most Ships Lost',                  'field': 'ships_lost',              'prefix': 'l', 'asc': False},
    {'id': 'most_missiles_sent',    'label': 'Most Missiles Sent',               'field': 'missiles_hit',            'prefix': 'a', 'asc': False},
    {'id': 'most_missiles_miss',    'label': 'Most Missiles Missed',             'field': 'missiles_missed',         'prefix': 'a', 'asc': False},
    {'id': 'most_missiles_eat',     'label': 'Most Missiles Eaten',              'field': 'missiles_eaten',          'prefix': 'a', 'asc': False},
    {'id': 'most_missiles_blk',     'label': 'Most Missiles Blocked',            'field': 'missiles_blocked',        'prefix': 'a', 'asc': False},
    {'id': 'most_nukes_sent',       'label': 'Most Nukes Sent',                  'field': 'nukes_hit',               'prefix': 'a', 'asc': False},
    {'id': 'most_nukes_miss',       'label': 'Most Nukes Missed',                'field': 'nukes_missed',            'prefix': 'a', 'asc': False},
    {'id': 'most_nukes_eat',        'label': 'Most Nukes Eaten',                 'field': 'nukes_eaten',             'prefix': 'a', 'asc': False},
    {'id': 'most_nukes_blk',        'label': 'Most Nukes Blocked',               'field': 'nukes_blocked',           'prefix': 'a', 'asc': False},
]

# ── Auth helper ───────────────────────────────────────────────────────────────

async def _get_linked_nation_id(request: Request) -> Optional[int]:
    """Return the nation_id linked to the current session user, or None."""
    user = request.session.get("discord_user")
    if not user:
        return None
    user_id = str(user.get("id"))
    try:
        from Systems.Functions.pets_db import pets_db
        settings = await pets_db.get_user_settings(user_id)
        lid = settings.get("linked_nation_id")
        if lid:
            return int(lid)
    except Exception:
        pass
    # Fall back to session-cached linked_nation
    session_nation = request.session.get("linked_nation")
    if session_nation:
        lid = session_nation.get("nation_id")
        if lid:
            return int(lid)
    return None


async def _require_own_nation(request: Request, nation_id: int) -> None:
    """
    Raise HTTP 403 if `nation_id` is not the caller's own linked nation.
    Raise HTTP 401 if the user is not logged in / has no linked nation.
    """
    linked = await _get_linked_nation_id(request)
    if linked is None:
        raise HTTPException(
            status_code=401,
            detail="You must be logged in and have a linked nation to use this page.",
        )
    if linked != nation_id:
        raise HTTPException(
            status_code=403,
            detail="You can only view your own nation on this page.",
        )


# ── Module-level singletons (lazy-init, same pattern as watch_api.py) ─────────

_my_nations_db = None
_global_nations_db = None


def _get_my_nations_db():
    global _my_nations_db
    if _my_nations_db is None:
        from PnWHarvester.db.my_nations_db import MyNationsDB
        from Systems.Functions.db_paths import MY_NATIONS_DB_STR
        _my_nations_db = MyNationsDB(MY_NATIONS_DB_STR)
    return _my_nations_db


def _get_global_nations_db():
    global _global_nations_db
    if _global_nations_db is None:
        from PnWHarvester.db.global_nations_db import GlobalNationsDB
        from Systems.Functions.db_paths import GLOBAL_NATIONS_DB_STR
        _global_nations_db = GlobalNationsDB(GLOBAL_NATIONS_DB_STR)
    return _global_nations_db


_global_wars_db = None


def _get_global_wars_db():
    global _global_wars_db
    if _global_wars_db is None:
        from PnWHarvester.db.global_wars_db import GlobalWarsDB
        from Systems.Functions.db_paths import GLOBAL_WARS_DB_STR
        _global_wars_db = GlobalWarsDB(GLOBAL_WARS_DB_STR)
    return _global_wars_db


# ── 2-minute in-memory cache keyed by nation_id ───────────────────────────────
_NATION_CACHE_TTL = 120  # seconds
_nation_cache: Dict[int, Tuple[float, Any]] = {}


def _cache_nation_get(nation_id: int) -> Optional[Any]:
    entry = _nation_cache.get(nation_id)
    if entry and (time.monotonic() - entry[0]) < _NATION_CACHE_TTL:
        return entry[1]
    return None


def _cache_nation_set(nation_id: int, value: Any) -> None:
    _nation_cache[nation_id] = (time.monotonic(), value)


def _cache_nation_bust(nation_id: int) -> None:
    _nation_cache.pop(nation_id, None)


# ── Improvement columns for slots_used calculation ────────────────────────────
_IMPROVEMENT_COLS = [
    "coal_mine", "oil_well", "uranium_mine", "lead_mine", "iron_mine",
    "bauxite_mine", "farm", "coal_power", "oil_power", "nuclear_power",
    "wind_power", "oil_refinery", "aluminum_refinery", "steel_mill",
    "munitions_factory", "factory", "police_station", "hospital",
    "recycling_center", "subway", "supermarket", "bank", "shopping_mall",
    "stadium", "barracks", "hangar", "drydock",
]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _compute_city_derived(city: Dict[str, Any]) -> Dict[str, Any]:
    """Add derived fields to a city dict (mutates and returns it)."""
    infra = float(city.get("infrastructure") or 0)

    # PnW real-game formula: 1 slot per 50 infra, max 50
    improvement_slots = min(int(infra // 50), 50)

    # Sum all improvement columns
    raw_slots_used = sum(int(city.get(col) or 0) for col in _IMPROVEMENT_COLS)
    slots_used = min(raw_slots_used, improvement_slots)

    # Power
    powered_needs = math.ceil(infra / 100)
    wind = int(city.get("wind_power") or 0)
    nuclear = int(city.get("nuclear_power") or 0)
    oil = int(city.get("oil_power") or 0)
    coal = int(city.get("coal_power") or 0)
    power_produced = (wind * 250) + (nuclear * 2000) + (oil * 500) + (coal * 500)
    is_powered = power_produced >= powered_needs

    # Age
    age_days = 0
    city_date = city.get("date")
    if city_date:
        try:
            dt = datetime.fromisoformat(str(city_date).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_days = max(0, (datetime.now(timezone.utc) - dt).days)
        except Exception:
            pass

    city["improvement_slots"] = improvement_slots
    city["slots_used"] = slots_used
    city["powered_needs"] = powered_needs
    city["power_produced"] = power_produced
    city["is_powered"] = is_powered
    city["age_days"] = age_days
    return city


def _build_seasonal_mod(game_info: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """Build seasonal modifier dict from game_info (same logic as watch_api.py)."""
    seasonal_mod: Dict[str, float] = {
        "na": 1, "sa": 1, "eu": 1, "as": 1, "af": 1, "au": 1, "an": 0.5,
    }
    if not game_info:
        return seasonal_mod
    game_date_str = game_info.get("game_date")
    if not game_date_str:
        return seasonal_mod
    try:
        parsed = datetime.fromisoformat(str(game_date_str).replace("Z", "+00:00"))
        month = parsed.month
    except Exception:
        return seasonal_mod
    if month in (6, 7, 8):
        seasonal_mod.update({"na": 1.2, "as": 1.2, "eu": 1.2, "sa": 0.8, "af": 0.8, "au": 0.8})
    elif month in (12, 1, 2):
        seasonal_mod.update({"na": 0.8, "as": 0.8, "eu": 0.8, "sa": 1.2, "af": 1.2, "au": 1.2})
    return seasonal_mod


def _build_radiation(radiation_data: Optional[Dict[str, float]]) -> Dict[str, float]:
    """Build radiation dict from database data (same logic as watch_api.py)."""
    if not radiation_data:
        return {"na": 0, "sa": 0, "eu": 0, "as": 0, "af": 0, "au": 0, "an": 0}
    global_rad = radiation_data.get("global", 0)
    return {
        "na": (radiation_data.get("north_america", 0) + global_rad) / -1000,
        "sa": (radiation_data.get("south_america", 0) + global_rad) / -1000,
        "eu": (radiation_data.get("europe", 0) + global_rad) / -1000,
        "as": (radiation_data.get("asia", 0) + global_rad) / -1000,
        "af": (radiation_data.get("africa", 0) + global_rad) / -1000,
        "au": (radiation_data.get("australia", 0) + global_rad) / -1000,
        "an": (radiation_data.get("antarctica", 0) + global_rad) / -1000,
    }


# ── Check-completion logic ────────────────────────────────────────────────────

def _goal_is_complete(
    goal: Dict[str, Any],
    nation: Dict[str, Any],
    cities: List[Dict[str, Any]],
) -> bool:
    """Return True if the goal's target has been reached by the live nation state."""
    goal_type = goal.get("goal_type", "")
    tv = goal.get("target_value") or {}
    if isinstance(tv, str):
        try:
            tv = json.loads(tv)
        except Exception:
            tv = {}

    if goal_type == "city":
        return int(nation.get("num_cities") or 0) >= int(tv.get("num_cities", 0))

    if goal_type == "infra":
        target_infra = float(tv.get("infra", 0))
        city_id = tv.get("city_id")
        
        if city_id:
            # Specific city: check that exact city
            city = next((c for c in cities if c.get("id") == city_id), None)
            if not city:
                return False
            return float(city.get("infrastructure") or 0) >= target_infra
        else:
            # All cities: EVERY city must meet target
            if not cities:
                return False
            return all(float(c.get("infrastructure") or 0) >= target_infra for c in cities)

    if goal_type == "land":
        target_land = float(tv.get("land", 0))
        city_id = tv.get("city_id")
        
        if city_id:
            # Specific city: check that exact city
            city = next((c for c in cities if c.get("id") == city_id), None)
            if not city:
                return False
            return float(city.get("land") or 0) >= target_land
        else:
            # All cities: EVERY city must meet target
            if not cities:
                return False
            return all(float(c.get("land") or 0) >= target_land for c in cities)

    if goal_type == "project":
        col = tv.get("project_col")
        if not col:
            return False
        # Projects are stored as integer 0/1 or boolean in the nation table
        val = nation.get(col)
        return bool(val) and val != 0

    if goal_type == "improvement":
        imp = tv.get("improvement")
        count = int(tv.get("count", 0))
        city_id = tv.get("city_id")
        
        if not imp or city_id is None:
            return False
        
        # Find the specific city
        city = next((c for c in cities if c.get("id") == city_id), None)
        if not city:
            return False
        
        # Check if that city has the target number of improvements
        current_count = int(city.get(imp) or 0)
        return current_count >= count

    if goal_type == "military":
        unit = tv.get("unit")
        count = int(tv.get("count", 0))
        if not unit:
            return False
        current = int(nation.get(unit, 0) or 0)
        return current >= count

    # "custom" and unknown types never auto-complete
    return False


async def _run_check_completion(
    nation_id: int,
    nation: Dict[str, Any],
    cities: List[Dict[str, Any]],
    db,
) -> List[int]:
    """Check all pending goals and complete those whose targets are met.

    Returns a list of newly completed goal IDs.
    """
    try:
        all_goals = await db.get_goals(nation_id)
        pending = [g for g in all_goals if not g.get("completed")]
        newly_completed: List[int] = []
        for goal in pending:
            if _goal_is_complete(goal, nation, cities):
                ok = await db.complete_goal(goal["id"])
                if ok:
                    newly_completed.append(goal["id"])
        return newly_completed
    except Exception as e:
        logger.error(f"_run_check_completion({nation_id}): {e}", exc_info=True)
        return []


# ── Main nation endpoint ──────────────────────────────────────────────────────

@router.get("/mynation/{nation_id}")
async def get_mynation(
    request: Request,
    nation_id: int,
    refresh: bool = Query(False, description="Bust the cache and recompute"),
) -> JSONResponse:
    """
    Return full nation dashboard data bundle for a single nation.
    Only accessible for the user's own linked nation.
    """
    await _require_own_nation(request, nation_id)

    if refresh:
        _cache_nation_bust(nation_id)

    cached = _cache_nation_get(nation_id)
    if cached is not None:
        return JSONResponse(cached)

    # ── Lazy imports ──────────────────────────────────────────────────────────
    from Systems.PnW.Util.rev_correct import revenue_calc_sync, calculate_nation_modifiers
    from Systems.Functions.database_manager import (
        get_latest_resource_prices,
        get_latest_game_data,
        get_latest_game_info,
        get_latest_radiation_data,
    )

    gdb = _get_global_nations_db()
    mdb = _get_my_nations_db()

    # ── Load nation and cities ────────────────────────────────────────────────
    nation = await gdb.get_nation(nation_id)
    if not nation:
        raise HTTPException(
            status_code=404,
            detail="Nation not found. It may not be tracked in our database yet.",
        )

    cities_raw = await gdb.get_cities_for_nation(nation_id)

    # ── Compute per-city derived fields ───────────────────────────────────────
    cities = [_compute_city_derived(dict(c)) for c in cities_raw]

    # ── Fetch active war counts (authoritative slot display) ──────────────────
    # offensive_wars_count / defensive_wars_count on the nation record are
    # cumulative lifetime totals — they must NOT be used for slot display.
    try:
        wdb = _get_global_wars_db()
        all_war_counts = await wdb.get_active_war_counts()
        nation_war_counts = all_war_counts.get(nation_id, {"off": 0, "def": 0})
    except Exception as _we:
        logger.warning(f"Could not load active war counts for nation {nation_id}: {_we}")
        nation_war_counts = {"off": 0, "def": 0}

    # Inject as dedicated fields so the frontend never touches the stale totals
    nation = dict(nation)
    nation["active_off_wars"] = nation_war_counts["off"]
    nation["active_def_wars"] = nation_war_counts["def"]

    # ── Gather game context in parallel ──────────────────────────────────────
    (
        price_data,
        colors_data,
        game_info,
        radiation_data,
    ) = await asyncio.gather(
        get_latest_resource_prices(),
        get_latest_game_data("colors"),
        get_latest_game_info(),
        get_latest_radiation_data(),
        return_exceptions=True,
    )

    if isinstance(price_data, Exception) or not price_data:
        price_data = {}
    if isinstance(colors_data, Exception) or not colors_data:
        colors_data = []
    if isinstance(game_info, Exception):
        game_info = None
    if isinstance(radiation_data, Exception):
        radiation_data = None

    # ── Build revenue inputs exactly as watch_api.py does ────────────────────
    market_prices: Dict[str, float] = {
        r: p["sell"] for r, p in price_data.items()
    } if price_data else {}

    # Raw color names (NOT lowercased) — revenue_calc_sync looks up by raw name
    colors_for_calc: Dict[str, float] = {
        c["color"]: float(c.get("turn_bonus", 0)) for c in colors_data
    } if colors_data else {}

    radiation = _build_radiation(radiation_data)
    seasonal_mod = _build_seasonal_mod(game_info)

    is_war = (
        (nation.get("offensive_wars_count") or 0) > 0
        or (nation.get("defensive_wars_count") or 0) > 0
    )

    # Cities must be injected onto the nation dict for revenue_calc_sync
    nation_for_rev = {**nation, "cities": cities}

    # ── Run revenue calculation in thread pool ────────────────────────────────
    revenue_error = False
    revenue_block: Dict[str, Any] = {
        "gross_income": 0.0,
        "tax_income": 0.0,
        "net_cash_turn": 0.0,
        "net_cash_day": 0.0,
        "net_cash_week": 0.0,
        "monetary_net_turn": 0.0,
        "military_upkeep_turn": 0.0,
        "improvement_upkeep_turn": 0.0,
        "power_upkeep_turn": 0.0,
        "rss_upkeep_turn": 0.0,
        "population": 0,
        "color_bonus": 0.0,
        "at_war": is_war,
        "resources": {
            "food": 0.0, "coal": 0.0, "oil": 0.0, "uranium": 0.0,
            "lead": 0.0, "iron": 0.0, "bauxite": 0.0, "gasoline": 0.0,
            "munitions": 0.0, "steel": 0.0, "aluminum": 0.0,
        },
    }

    try:
        rev = await asyncio.to_thread(
            revenue_calc_sync,
            nation=nation_for_rev,
            radiation=radiation,
            treasures=[],
            prices=market_prices,
            colors=colors_for_calc,
            seasonal_mod=seasonal_mod,
            is_war=is_war,
        )
        if rev:
            # revenue_calc_sync returns resources as top-level keys (food, coal, etc.)
            # NOT as a nested "resources" dict — build it from individual keys.
            resources_dict = {
                "food":      rev.get("food", 0.0),
                "coal":      rev.get("coal", 0.0),
                "oil":       rev.get("oil", 0.0),
                "uranium":   rev.get("uranium", 0.0),
                "lead":      rev.get("lead", 0.0),
                "iron":      rev.get("iron", 0.0),
                "bauxite":   rev.get("bauxite", 0.0),
                "gasoline":  rev.get("gasoline", 0.0),
                "munitions": rev.get("munitions", 0.0),
                "steel":     rev.get("steel", 0.0),
                "aluminum":  rev.get("aluminum", 0.0),
            }
            revenue_block = {
                # gross_money_income = tax_revenue * policy * treasure + color_bonus
                # (this is what the revenue command calls "gross income")
                "gross_income":            rev.get("gross_money_income", 0.0),
                # tax_income = gross_income minus color bonus = pure national tax revenue
                # (matches "Net Income (Gross)" row in the revenue command embed)
                "tax_income":              rev.get("gross_money_income", 0.0) - rev.get("color_bonus_turn", 0.0),
                "net_cash_turn":           rev.get("net_cash_num", 0.0),
                "net_cash_day":            rev.get("net_cash_num", 0.0) * 12,
                "net_cash_week":           rev.get("net_cash_num", 0.0) * 84,
                "monetary_net_turn":       rev.get("monetary_net_num", 0.0),
                "military_upkeep_turn":    rev.get("military_upkeep_turn", 0.0),
                # improvement_upkeep_turn = civil_upkeep + power_upkeep + rss_upkeep (all combined)
                "improvement_upkeep_turn": rev.get("improvement_upkeep_turn", 0.0),
                "power_upkeep_turn":       rev.get("power_upkeep_turn", 0.0),
                "rss_upkeep_turn":         rev.get("rss_upkeep_turn", 0.0),
                "population":              int(rev.get("nationpop", 0) or 0),
                "color_bonus":             rev.get("color_bonus_turn", 0.0),
                "at_war":                  is_war,
                "resources":               resources_dict,
            }
    except Exception as e:
        logger.error(f"revenue_calc_sync failed for nation {nation_id}: {e}", exc_info=True)
        revenue_error = True

    # ── Run nation modifiers ──────────────────────────────────────────────────
    try:
        modifiers = calculate_nation_modifiers(nation)
    except Exception as e:
        logger.error(f"calculate_nation_modifiers failed for nation {nation_id}: {e}", exc_info=True)
        modifiers = {}

    # ── Load goals and snapshot from MyNationsDB ──────────────────────────────
    goals_error = False
    goals: List[Dict[str, Any]] = []
    snapshot: Optional[Dict[str, Any]] = None

    try:
        goals = await mdb.get_goals(nation_id)
        snapshot = await mdb.get_snapshot(nation_id)
    except Exception as e:
        logger.error(f"MyNationsDB query failed for nation {nation_id}: {e}", exc_info=True)
        goals_error = True

    # ── Inline check-completion logic ─────────────────────────────────────────
    newly_completed_goals: List[int] = await _run_check_completion(
        nation_id, nation, cities, mdb
    )

    # Reload goals after potential completion updates
    if newly_completed_goals:
        try:
            goals = await mdb.get_goals(nation_id)
        except Exception:
            pass

    # ── Build flat prices dict for response ───────────────────────────────────
    prices_flat: Dict[str, float] = {
        r: float(p.get("sell", 0)) for r, p in price_data.items()
    } if price_data else {}

    # ── Assemble and return response ─────────────────────────────────────────
    response: Dict[str, Any] = {
        "nation":                nation,
        "cities":                cities,
        "revenue":               revenue_block,
        "modifiers":             modifiers,
        "goals":                 goals,
        "newly_completed_goals": newly_completed_goals,
        "snapshot":              snapshot,
        "prices":                prices_flat,
        "updated_at":            _utcnow_iso(),
    }

    if revenue_error:
        response["revenue_error"] = True
    if goals_error:
        response["goals_error"] = True

    _cache_nation_set(nation_id, response)
    return JSONResponse(response)


# ── Check-completion endpoint ─────────────────────────────────────────────────

@router.post("/mynation/goals/check-completion/{nation_id}")
async def check_goal_completion(request: Request, nation_id: int) -> JSONResponse:
    """
    Compare every pending goal for a nation against the live GlobalNationsDB state.
    Only accessible for the user's own linked nation.
    """
    await _require_own_nation(request, nation_id)
    gdb = _get_global_nations_db()
    mdb = _get_my_nations_db()

    nation = await gdb.get_nation(nation_id)
    if not nation:
        raise HTTPException(status_code=404, detail="Nation not found.")

    cities = await gdb.get_cities_for_nation(nation_id)
    newly = await _run_check_completion(nation_id, nation, cities, mdb)

    return JSONResponse({"completed": newly, "count": len(newly)})


# ── Goals CRUD ────────────────────────────────────────────────────────────────

@router.get("/mynation/goals/{nation_id}")
async def get_goals(request: Request, nation_id: int) -> JSONResponse:
    """Return all goals for a nation. Only accessible for the user's own linked nation."""
    await _require_own_nation(request, nation_id)
    mdb = _get_my_nations_db()
    try:
        goals = await mdb.get_goals(nation_id)
        return JSONResponse(goals)
    except Exception as e:
        logger.error(f"get_goals({nation_id}): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load goals.")


@router.post("/mynation/goals")
async def create_goal(request: Request, body: Dict[str, Any]) -> JSONResponse:
    """
    Create a new goal for the user's own linked nation only.
    """
    import html

    nation_id = body.get("nation_id")
    if not isinstance(nation_id, int) or nation_id <= 0:
        raise HTTPException(status_code=422, detail="nation_id must be a positive integer.")

    await _require_own_nation(request, nation_id)

    goal_label = html.escape(str(body.get("goal_label", "") or ""))
    if not goal_label.strip():
        raise HTTPException(status_code=422, detail="goal_label cannot be empty.")

    notes = html.escape(str(body.get("notes", "") or ""))
    goal_type = body.get("goal_type", "custom")
    target_value = body.get("target_value")
    estimated_cost = body.get("estimated_cost")

    mdb = _get_my_nations_db()
    gdb = _get_global_nations_db()

    # Load nation and cities for validation
    nation = await gdb.get_nation(nation_id)
    if not nation:
        raise HTTPException(status_code=404, detail="Nation not found.")
    
    cities = await gdb.get_cities_for_nation(nation_id)

    # ── Validate target_value based on goal_type ──────────────────────────────
    if not isinstance(target_value, dict):
        raise HTTPException(status_code=422, detail="target_value must be an object.")

    if goal_type == "city":
        num_cities = target_value.get("num_cities")
        if not isinstance(num_cities, (int, float)) or num_cities < 1:
            raise HTTPException(status_code=422, detail="num_cities must be at least 1.")
        if num_cities > 100:
            raise HTTPException(status_code=422, detail="num_cities cannot exceed 100 (game limit).")
        current = int(nation.get("num_cities") or 0)
        if num_cities <= current:
            raise HTTPException(status_code=422, detail=f"Target city count ({num_cities}) must be greater than current ({current}).")

    elif goal_type == "infra":
        infra = target_value.get("infra")
        if not isinstance(infra, (int, float)) or infra < 10:
            raise HTTPException(status_code=422, detail="infra must be at least 10.")
        if infra > 15000:
            raise HTTPException(status_code=422, detail="infra cannot exceed 15,000 (game limit).")
        
        city_id = target_value.get("city_id")
        if city_id:
            # Validate city exists
            city = next((c for c in cities if c.get("id") == city_id), None)
            if not city:
                raise HTTPException(status_code=422, detail=f"City {city_id} not found.")
            current_infra = float(city.get("infrastructure") or 0)
            if infra <= current_infra:
                raise HTTPException(status_code=422, detail=f"Target infra ({infra}) must be greater than current ({current_infra:.2f}).")

    elif goal_type == "land":
        land = target_value.get("land")
        if not isinstance(land, (int, float)) or land < 250:
            raise HTTPException(status_code=422, detail="land must be at least 250 (minimum city land).")
        if land > 50000:
            raise HTTPException(status_code=422, detail="land cannot exceed 50,000 (reasonable limit).")
        
        city_id = target_value.get("city_id")
        if city_id:
            # Validate city exists
            city = next((c for c in cities if c.get("id") == city_id), None)
            if not city:
                raise HTTPException(status_code=422, detail=f"City {city_id} not found.")
            current_land = float(city.get("land") or 0)
            if land <= current_land:
                raise HTTPException(status_code=422, detail=f"Target land ({land}) must be greater than current ({current_land:.2f}).")

    elif goal_type == "project":
        project_col = target_value.get("project_col")
        if not project_col:
            raise HTTPException(status_code=422, detail="project_col is required for project goals.")
        
        # Validate it's a known project column
        from PnWHarvester.db import pnw_costs
        if project_col not in pnw_costs._PROJECT_DB_COL_TO_DISPLAY:
            raise HTTPException(status_code=422, detail=f"Unknown project: {project_col}")
        
        # Check if already owned
        if nation.get(project_col):
            raise HTTPException(status_code=422, detail=f"You already own this project.")

    elif goal_type == "improvement":
        imp = target_value.get("improvement")
        count = target_value.get("count")
        city_id = target_value.get("city_id")
        
        if not imp:
            raise HTTPException(status_code=422, detail="improvement is required.")
        if not isinstance(count, (int, float)) or count < 1:
            raise HTTPException(status_code=422, detail="count must be at least 1.")
        if count > 50:
            raise HTTPException(status_code=422, detail="count cannot exceed 50 (max improvement slots).")
        if not city_id:
            raise HTTPException(status_code=422, detail="city_id is required for improvement goals.")
        
        # Validate city exists
        city = next((c for c in cities if c.get("id") == city_id), None)
        if not city:
            raise HTTPException(status_code=422, detail=f"City {city_id} not found.")
        
        # Validate improvement column exists
        if imp not in _IMPROVEMENT_COLS:
            raise HTTPException(status_code=422, detail=f"Unknown improvement: {imp}")
        
        # Check current count
        current_count = int(city.get(imp) or 0)
        if count <= current_count:
            raise HTTPException(status_code=422, detail=f"Target count ({count}) must be greater than current ({current_count}).")
        
        # Check if city has enough improvement slots
        city_infra = float(city.get("infrastructure") or 0)
        max_slots = min(int(city_infra // 50), 50)
        
        # Calculate total improvements that will be in the city
        current_total = sum(int(city.get(col) or 0) for col in _IMPROVEMENT_COLS)
        added = int(count) - current_count
        new_total = current_total + added
        
        if new_total > max_slots:
            raise HTTPException(
                status_code=422, 
                detail=f"This would require {new_total} slots, but city only has {max_slots} slots (need {int((new_total * 50) / 1)} infra)."
            )

    elif goal_type == "military":
        unit = target_value.get("unit")
        count = target_value.get("count")
        
        if not unit:
            raise HTTPException(status_code=422, detail="unit is required.")
        if unit not in ("soldiers", "tanks", "aircraft", "ships", "missiles", "nukes"):
            raise HTTPException(status_code=422, detail=f"Invalid military unit: {unit}")
        if not isinstance(count, (int, float)) or count < 1:
            raise HTTPException(status_code=422, detail="count must be at least 1.")
        
        # Check reasonable limits
        limits = {
            "soldiers": 1_000_000_000,
            "tanks": 100_000_000,
            "aircraft": 50_000_000,
            "ships": 10_000_000,
            "missiles": 1000,
            "nukes": 500
        }
        if count > limits[unit]:
            raise HTTPException(status_code=422, detail=f"count cannot exceed {limits[unit]} (reasonable limit).")
        
        current = int(nation.get(unit) or 0)
        if count <= current:
            raise HTTPException(status_code=422, detail=f"Target {unit} ({count}) must be greater than current ({current}).")

    elif goal_type == "custom":
        # Custom goals have no strict validation
        pass

    else:
        raise HTTPException(status_code=422, detail=f"Unknown goal_type: {goal_type}")

    # Auto-capture snapshot if none exists
    try:
        existing_snapshot = await mdb.get_snapshot(nation_id)
        if existing_snapshot is None:
            await mdb.save_snapshot(nation_id, nation, cities)
    except Exception as e:
        logger.warning(f"Snapshot auto-capture failed for nation {nation_id}: {e}")

    goal: Dict[str, Any] = {
        "nation_id":    nation_id,
        "goal_type":    goal_type,
        "goal_label":   goal_label,
        "target_value": target_value,
        "estimated_cost": estimated_cost,
        "notes":        notes,
    }

    new_id = await mdb.save_goal(goal)
    if new_id < 0:
        raise HTTPException(status_code=500, detail="Failed to save goal.")

    # Return the created goal
    all_goals = await mdb.get_goals(nation_id)
    created = next((g for g in all_goals if g.get("id") == new_id), {"id": new_id, **goal})
    return JSONResponse(created, status_code=201)


@router.post("/mynation/goals/{goal_id}/complete")
async def complete_goal(request: Request, goal_id: int) -> JSONResponse:
    """Manually mark a goal as completed. Only the goal owner may do this."""
    mdb = _get_my_nations_db()
    goal = await _get_goal_by_id(mdb, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found.")
    await _require_own_nation(request, int(goal["nation_id"]))
    ok = await mdb.complete_goal(goal_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Goal not found or already completed.")
    return JSONResponse({"goal_id": goal_id, "completed": True})


@router.delete("/mynation/goals/{goal_id}")
async def delete_goal(request: Request, goal_id: int, nation_id: int = Query(...)) -> JSONResponse:
    """
    Delete a goal. Verifies that nation_id matches the goal's stored nation_id
    AND that the requester owns that nation.
    """
    mdb = _get_my_nations_db()

    goal = await _get_goal_by_id(mdb, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found.")

    if int(goal.get("nation_id", -1)) != nation_id:
        raise HTTPException(status_code=403, detail="nation_id does not match goal owner.")

    await _require_own_nation(request, nation_id)

    ok = await mdb.delete_goal(goal_id)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to delete goal.")
    return JSONResponse({"goal_id": goal_id, "deleted": True})


async def _get_goal_by_id(mdb, goal_id: int) -> Optional[Dict[str, Any]]:
    """Helper: fetch a single goal by its id."""
    try:
        return await asyncio.to_thread(_get_goal_by_id_sync, mdb, goal_id)
    except Exception as e:
        logger.error(f"_get_goal_by_id({goal_id}): {e}", exc_info=True)
        return None


def _get_goal_by_id_sync(mdb, goal_id: int) -> Optional[Dict[str, Any]]:
    try:
        with mdb._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM nation_goals WHERE id = ?", (goal_id,)
            ).fetchone()
            if row is None:
                return None
            return mdb._row_to_goal(row)
    except Exception as e:
        logger.error(f"_get_goal_by_id_sync({goal_id}): {e}", exc_info=True)
        return None


# ── War-stats endpoint ────────────────────────────────────────────────────────

# 10-minute in-memory cache keyed by nation_id
_WAR_STATS_CACHE_TTL = 600  # seconds
_war_stats_cache: Dict[int, Tuple[float, Any]] = {}

DARKSTAR_ALLIANCE_ID = 10259

_LOOT_RESOURCES = (
    "coal", "oil", "uranium", "iron", "bauxite", "lead",
    "gasoline", "munitions", "steel", "aluminum", "food",
)


def _war_stats_cache_get(nation_id: int) -> Optional[Any]:
    entry = _war_stats_cache.get(nation_id)
    if entry and (time.monotonic() - entry[0]) < _WAR_STATS_CACHE_TTL:
        return entry[1]
    return None


def _war_stats_cache_set(nation_id: int, value: Any) -> None:
    _war_stats_cache[nation_id] = (time.monotonic(), value)


def _query_irs_war_stats_sync(db_path: str, nation_id: int) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Run all IRSWars.db queries synchronously.
    Intended to be called via asyncio.to_thread.
    """
    import sqlite3 as _sqlite3

    nid = nation_id
    stats: Dict[str, Any] = {
        "money_gained": 0.0,
        "money_lost": 0.0,
        "resources_gained": {r: 0.0 for r in _LOOT_RESOURCES},
        "resources_lost": {r: 0.0 for r in _LOOT_RESOURCES},
        "infra_dealt_levels": 0.0,
        "infra_dealt_value": 0.0,
        "infra_recv_levels": 0.0,
        "infra_recv_value": 0.0,
        "soldiers_killed": 0,
        "tanks_killed": 0,
        "aircraft_killed": 0,
        "ships_killed": 0,
        "soldiers_lost": 0,
        "tanks_lost": 0,
        "aircraft_lost": 0,
        "ships_lost": 0,
        "missiles_fired": 0,
        "missiles_received": 0,
        "nukes_fired": 0,
        "nukes_received": 0,
        "wars_won": 0,
        "wars_lost": 0,
        "total_wars": 0,
    }
    tracked_since: Optional[str] = None

    try:
        conn = _sqlite3.connect(db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.row_factory = _sqlite3.Row

        with conn:
            cur = conn.cursor()

            # ── Loot gained (nation was attacker) ────────────────────────────
            loot_gained_select = ", ".join(
                f"SUM(COALESCE({r}_looted, 0)) AS {r}_gained"
                for r in _LOOT_RESOURCES
            )
            cur.execute(
                f"""
                SELECT
                    SUM(COALESCE(money_looted, 0) + COALESCE(money_stolen, 0)) AS money_gained,
                    {loot_gained_select}
                FROM war_attacks
                WHERE attacker_id = ?
                """,
                (nid,),
            )
            row = cur.fetchone()
            if row:
                stats["money_gained"] = float(row["money_gained"] or 0)
                for r in _LOOT_RESOURCES:
                    stats["resources_gained"][r] = float(row[f"{r}_gained"] or 0)

            # ── Loot lost (nation was defender) ──────────────────────────────
            loot_lost_select = ", ".join(
                f"SUM(COALESCE({r}_looted, 0)) AS {r}_lost"
                for r in _LOOT_RESOURCES
            )
            cur.execute(
                f"""
                SELECT
                    SUM(COALESCE(money_looted, 0)) AS money_lost,
                    {loot_lost_select}
                FROM war_attacks
                WHERE defender_id = ?
                """,
                (nid,),
            )
            row = cur.fetchone()
            if row:
                stats["money_lost"] = float(row["money_lost"] or 0)
                for r in _LOOT_RESOURCES:
                    stats["resources_lost"][r] = float(row[f"{r}_lost"] or 0)

            # ── Infra dealt and received ──────────────────────────────────────
            cur.execute(
                """
                SELECT
                    SUM(CASE WHEN attacker_id = ? THEN COALESCE(infra_destroyed, 0) ELSE 0 END)
                        AS infra_dealt_lvls,
                    SUM(CASE WHEN attacker_id = ? THEN COALESCE(infra_destroyed_value, 0) ELSE 0 END)
                        AS infra_dealt_val,
                    SUM(CASE WHEN defender_id = ? THEN COALESCE(infra_destroyed, 0) ELSE 0 END)
                        AS infra_recv_lvls,
                    SUM(CASE WHEN defender_id = ? THEN COALESCE(infra_destroyed_value, 0) ELSE 0 END)
                        AS infra_recv_val
                FROM war_attacks
                WHERE attacker_id = ? OR defender_id = ?
                """,
                (nid, nid, nid, nid, nid, nid),
            )
            row = cur.fetchone()
            if row:
                stats["infra_dealt_levels"] = float(row["infra_dealt_lvls"] or 0)
                stats["infra_dealt_value"]  = float(row["infra_dealt_val"] or 0)
                stats["infra_recv_levels"]  = float(row["infra_recv_lvls"] or 0)
                stats["infra_recv_value"]   = float(row["infra_recv_val"] or 0)

            # ── Unit kills and losses from wars table ───────────────────────
            # The wars table has aggregated att_*_lost and def_*_lost columns.
            # When nation_id is attacker: their losses = att_*_lost, their kills = def_*_lost
            # When nation_id is defender: their losses = def_*_lost, their kills = att_*_lost
            cur.execute(
                """
                SELECT
                    SUM(CASE WHEN att_id = ? THEN COALESCE(def_soldiers_lost, 0) ELSE 0 END)
                        AS soldiers_killed,
                    SUM(CASE WHEN att_id = ? THEN COALESCE(def_tanks_lost, 0) ELSE 0 END)
                        AS tanks_killed,
                    SUM(CASE WHEN att_id = ? THEN COALESCE(def_aircraft_lost, 0) ELSE 0 END)
                        AS aircraft_killed,
                    SUM(CASE WHEN att_id = ? THEN COALESCE(def_ships_lost, 0) ELSE 0 END)
                        AS ships_killed,
                    SUM(CASE WHEN def_id = ? THEN COALESCE(att_soldiers_lost, 0) ELSE 0 END)
                        AS soldiers_killed_def,
                    SUM(CASE WHEN def_id = ? THEN COALESCE(att_tanks_lost, 0) ELSE 0 END)
                        AS tanks_killed_def,
                    SUM(CASE WHEN def_id = ? THEN COALESCE(att_aircraft_lost, 0) ELSE 0 END)
                        AS aircraft_killed_def,
                    SUM(CASE WHEN def_id = ? THEN COALESCE(att_ships_lost, 0) ELSE 0 END)
                        AS ships_killed_def,
                    SUM(CASE WHEN att_id = ? THEN COALESCE(att_soldiers_lost, 0) ELSE 0 END)
                        AS soldiers_lost,
                    SUM(CASE WHEN att_id = ? THEN COALESCE(att_tanks_lost, 0) ELSE 0 END)
                        AS tanks_lost,
                    SUM(CASE WHEN att_id = ? THEN COALESCE(att_aircraft_lost, 0) ELSE 0 END)
                        AS aircraft_lost,
                    SUM(CASE WHEN att_id = ? THEN COALESCE(att_ships_lost, 0) ELSE 0 END)
                        AS ships_lost,
                    SUM(CASE WHEN def_id = ? THEN COALESCE(def_soldiers_lost, 0) ELSE 0 END)
                        AS soldiers_lost_def,
                    SUM(CASE WHEN def_id = ? THEN COALESCE(def_tanks_lost, 0) ELSE 0 END)
                        AS tanks_lost_def,
                    SUM(CASE WHEN def_id = ? THEN COALESCE(def_aircraft_lost, 0) ELSE 0 END)
                        AS aircraft_lost_def,
                    SUM(CASE WHEN def_id = ? THEN COALESCE(def_ships_lost, 0) ELSE 0 END)
                        AS ships_lost_def
                FROM wars
                WHERE att_id = ? OR def_id = ?
                """,
                (nid, nid, nid, nid, nid, nid, nid, nid, nid, nid, nid, nid, nid, nid, nid, nid, nid, nid),
            )
            row = cur.fetchone()
            if row:
                # Total kills = kills as attacker + kills as defender
                stats["soldiers_killed"]  = int(row["soldiers_killed"] or 0) + int(row["soldiers_killed_def"] or 0)
                stats["tanks_killed"]     = int(row["tanks_killed"] or 0) + int(row["tanks_killed_def"] or 0)
                stats["aircraft_killed"]  = int(row["aircraft_killed"] or 0) + int(row["aircraft_killed_def"] or 0)
                stats["ships_killed"]     = int(row["ships_killed"] or 0) + int(row["ships_killed_def"] or 0)
                # Total losses = losses as attacker + losses as defender
                stats["soldiers_lost"]    = int(row["soldiers_lost"] or 0) + int(row["soldiers_lost_def"] or 0)
                stats["tanks_lost"]       = int(row["tanks_lost"] or 0) + int(row["tanks_lost_def"] or 0)
                stats["aircraft_lost"]    = int(row["aircraft_lost"] or 0) + int(row["aircraft_lost_def"] or 0)
                stats["ships_lost"]       = int(row["ships_lost"] or 0) + int(row["ships_lost_def"] or 0)

            # ── Wars table: tracked_since, win/loss record ───────────────────
            cur.execute(
                """
                SELECT
                    MIN(date) AS tracked_since,
                    SUM(CASE WHEN winner_id = ? THEN 1 ELSE 0 END) AS wars_won_irs,
                    SUM(CASE WHEN (att_id = ? OR def_id = ?)
                              AND winner_id IS NOT NULL AND winner_id != 0
                              AND winner_id != ? THEN 1 ELSE 0 END) AS wars_lost_irs,
                    COUNT(*) AS total_wars_irs
                FROM wars
                WHERE att_id = ? OR def_id = ?
                """,
                (nid, nid, nid, nid, nid, nid),
            )
            row = cur.fetchone()
            if row:
                stats["wars_won"]           = int(row["wars_won_irs"] or 0)
                stats["wars_lost"]          = int(row["wars_lost_irs"] or 0)
                stats["total_wars"]         = int(row["total_wars_irs"] or 0)
                raw_tracked = row["tracked_since"]
                if raw_tracked:
                    # Normalise to ISO-8601 UTC string
                    try:
                        ts = str(raw_tracked).strip()
                        # If it's already a date string, make it ISO with Z suffix
                        if "T" not in ts:
                            ts = ts.replace(" ", "T")
                        if not ts.endswith("Z") and "+" not in ts:
                            ts += "Z"
                        tracked_since = ts
                    except Exception:
                        tracked_since = str(raw_tracked)

            # ── Missiles and nukes from war_attacks table ────────────────────
            # These are tracked per-attack, not per-war
            # When nation is attacker: fired = att_*_lost, received = def_*_lost
            # When nation is defender: fired = def_*_lost, received = att_*_lost
            cur.execute(
                """
                SELECT
                    SUM(CASE WHEN attacker_id = ? THEN COALESCE(att_missiles_lost, 0) ELSE 0 END)
                        AS missiles_fired_as_att,
                    SUM(CASE WHEN defender_id = ? THEN COALESCE(def_missiles_lost, 0) ELSE 0 END)
                        AS missiles_fired_as_def,
                    SUM(CASE WHEN attacker_id = ? THEN COALESCE(def_missiles_lost, 0) ELSE 0 END)
                        AS missiles_received_as_att,
                    SUM(CASE WHEN defender_id = ? THEN COALESCE(att_missiles_lost, 0) ELSE 0 END)
                        AS missiles_received_as_def,
                    SUM(CASE WHEN attacker_id = ? THEN COALESCE(att_nukes_lost, 0) ELSE 0 END)
                        AS nukes_fired_as_att,
                    SUM(CASE WHEN defender_id = ? THEN COALESCE(def_nukes_lost, 0) ELSE 0 END)
                        AS nukes_fired_as_def,
                    SUM(CASE WHEN attacker_id = ? THEN COALESCE(def_nukes_lost, 0) ELSE 0 END)
                        AS nukes_received_as_att,
                    SUM(CASE WHEN defender_id = ? THEN COALESCE(att_nukes_lost, 0) ELSE 0 END)
                        AS nukes_received_as_def
                FROM war_attacks
                WHERE attacker_id = ? OR defender_id = ?
                """,
                (nid, nid, nid, nid, nid, nid, nid, nid, nid, nid),
            )
            row = cur.fetchone()
            if row:
                stats["missiles_fired"]     = int(row["missiles_fired_as_att"] or 0) + int(row["missiles_fired_as_def"] or 0)
                stats["missiles_received"]  = int(row["missiles_received_as_att"] or 0) + int(row["missiles_received_as_def"] or 0)
                stats["nukes_fired"]        = int(row["nukes_fired_as_att"] or 0) + int(row["nukes_fired_as_def"] or 0)
                stats["nukes_received"]     = int(row["nukes_received_as_att"] or 0) + int(row["nukes_received_as_def"] or 0)
                raw_tracked = row["tracked_since"]
                if raw_tracked:
                    # Normalise to ISO-8601 UTC string
                    try:
                        ts = str(raw_tracked).strip()
                        # If it's already a date string, make it ISO with Z suffix
                        if "T" not in ts:
                            ts = ts.replace(" ", "T")
                        if not ts.endswith("Z") and "+" not in ts:
                            ts += "Z"
                        tracked_since = ts
                    except Exception:
                        tracked_since = str(raw_tracked)

    except Exception as exc:
        logger.error(
            f"_query_irs_war_stats_sync(nation_id={nation_id}): {exc}", exc_info=True
        )

    return stats, tracked_since


@router.get("/mynation/war-stats/{nation_id}")
async def get_war_stats(request: Request, nation_id: int) -> JSONResponse:
    """
    Return full combat history panel data for a nation.
    Only accessible for the user's own linked nation.
    """
    await _require_own_nation(request, nation_id)

    cached = _war_stats_cache_get(nation_id)
    if cached is not None:
        return JSONResponse(cached)

    gdb = _get_global_nations_db()

    # ── Load nation from GlobalNationsDB ─────────────────────────────────────
    nation = await gdb.get_nation(nation_id)
    if not nation:
        raise HTTPException(
            status_code=404,
            detail="Nation not found. It may not be tracked in our database yet.",
        )

    # ── Global kill stats — always returned ──────────────────────────────────
    global_kill_stats: Dict[str, Any] = {
        "soldier_kills":          int(nation.get("soldier_kills") or 0),
        "tank_kills":             int(nation.get("tank_kills") or 0),
        "aircraft_kills":         int(nation.get("aircraft_kills") or 0),
        "ship_kills":             int(nation.get("ship_kills") or 0),
        "missile_kills":          int(nation.get("missile_kills") or 0),
        "nuke_kills":             int(nation.get("nuke_kills") or 0),
        "spy_kills":              int(nation.get("spy_kills") or 0),
        "wars_won":               int(nation.get("wars_won") or 0),
        "wars_lost":              int(nation.get("wars_lost") or 0),
        "offensive_wars_count":   int(nation.get("offensive_wars_count") or 0),
        "defensive_wars_count":   int(nation.get("defensive_wars_count") or 0),
    }

    is_darkstar = nation.get("alliance_id") == DARKSTAR_ALLIANCE_ID

    # ── IRSWars.db queries (Darkstar only) ────────────────────────────────────
    irs_stats: Optional[Dict[str, Any]] = None
    tracked_since: Optional[str] = None

    if is_darkstar:
        try:
            from Systems.Functions.db_paths import IRS_WARS_DB_STR
            irs_raw, tracked_since = await asyncio.to_thread(
                _query_irs_war_stats_sync, IRS_WARS_DB_STR, nation_id
            )
            irs_stats = {
                "money_gained":       irs_raw["money_gained"],
                "money_lost":         irs_raw["money_lost"],
                "resources_gained":   irs_raw["resources_gained"],
                "resources_lost":     irs_raw["resources_lost"],
                "infra_dealt_levels": irs_raw["infra_dealt_levels"],
                "infra_dealt_value":  irs_raw["infra_dealt_value"],
                "infra_recv_levels":  irs_raw["infra_recv_levels"],
                "infra_recv_value":   irs_raw["infra_recv_value"],
                "soldiers_killed":    irs_raw["soldiers_killed"],
                "tanks_killed":       irs_raw["tanks_killed"],
                "aircraft_killed":    irs_raw["aircraft_killed"],
                "ships_killed":       irs_raw["ships_killed"],
                "soldiers_lost":      irs_raw["soldiers_lost"],
                "tanks_lost":         irs_raw["tanks_lost"],
                "aircraft_lost":      irs_raw["aircraft_lost"],
                "ships_lost":         irs_raw["ships_lost"],
                "missiles_fired":     irs_raw["missiles_fired"],
                "missiles_received":  irs_raw["missiles_received"],
                "nukes_fired":        irs_raw["nukes_fired"],
                "nukes_received":     irs_raw["nukes_received"],
                "wars_won":           irs_raw["wars_won"],
                "wars_lost":          irs_raw["wars_lost"],
                "total_wars":         irs_raw["total_wars"],
            }
        except Exception as e:
            logger.error(
                f"get_war_stats: IRSWars.db query failed for nation {nation_id}: {e}",
                exc_info=True,
            )
            # Requirement 12.9 — still return global kill stats
            irs_stats = None

    response: Dict[str, Any] = {
        "is_darkstar":       is_darkstar,
        "tracked_since":     tracked_since,
        "irs_stats":         irs_stats,
        "global_kill_stats": global_kill_stats,
    }

    _war_stats_cache_set(nation_id, response)
    return JSONResponse(response)


# ── Cost-preview endpoint ────────────────────────────────────────────────────

_VALID_COST_TYPES = frozenset(
    {"city", "infra", "land", "project", "improvement", "military"}
)


@router.get("/mynation/cost-preview")
async def get_cost_preview(
    request: Request,
    nation_id: int = Query(..., description="Nation ID"),
    type: str = Query(..., description="Cost type"),
    current: float = Query(..., description="Current value"),
    target: float = Query(..., description="Target value"),
    city_id: Optional[int] = Query(None, description="City ID (optional)"),
    unit: Optional[str] = Query(None, description="Military unit (for type=military)"),
    improvement: Optional[str] = Query(None, description="Improvement DB column name (for type=improvement)"),
    project_col: Optional[str] = Query(None, description="Project DB column name (for type=project)"),
) -> JSONResponse:
    """
    Return a cost estimate + time-to-goal for a planned upgrade.
    Only accessible for the user's own linked nation.
    """
    await _require_own_nation(request, nation_id)

    if type not in _VALID_COST_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"type must be one of: {', '.join(sorted(_VALID_COST_TYPES))}",
        )

    # ── Lazy imports ──────────────────────────────────────────────────────────
    from Systems.PnW.IA.costs import (
        infra_purchase_cost,
        land_purchase_cost,
        city_purchase_cost,
        project_build_cost,
    )
    import PnWHarvester.db.pnw_costs as pnw_costs
    from Systems.PnW.Util.war_calc import UNIT_COSTS

    # ── Load nation for discount calculation ──────────────────────────────────
    gdb = _get_global_nations_db()
    nation = await gdb.get_nation(nation_id)
    if not nation:
        raise HTTPException(
            status_code=404,
            detail="Nation not found. It may not be tracked in our database yet.",
        )

    total_cash: float = 0.0
    resources: Dict[str, float] = {}
    breakdown: str = ""

    # ── Route to correct cost function ───────────────────────────────────────

    if type == "infra":
        # second arg is delta (amount to buy), NOT target
        delta = target - current
        if delta <= 0:
            total_cash = 0.0
        else:
            result = infra_purchase_cost(current, delta, nation)
            total_cash = float(result.get("final_cost", 0.0))

    elif type == "land":
        # second arg is delta (amount to buy), NOT target
        delta = target - current
        if delta <= 0:
            total_cash = 0.0
        else:
            result = land_purchase_cost(current, delta, nation)
            total_cash = float(result.get("final_cost", 0.0))

    elif type == "city":
        top20 = pnw_costs._get_top_20_average()
        city_start = int(current) + 1
        city_end = int(target)
        breakdown_parts: list = []
        for n in range(city_start, city_end + 1):
            result = city_purchase_cost(n, top20, nation)
            fc = float(result.get("final_cost", 0.0))
            total_cash += fc
            breakdown_parts.append(f"City {n}: ${fc / 1_000_000:.1f}M")
        breakdown = ", ".join(breakdown_parts)

    elif type == "project":
        if not project_col:
            raise HTTPException(status_code=422, detail="project_col is required for type=project")
        display_name = pnw_costs._PROJECT_DB_COL_TO_DISPLAY.get(project_col)
        if not display_name:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown project_col: {project_col!r}",
            )
        result = project_build_cost(display_name, nation)
        if not result:
            raise HTTPException(
                status_code=422,
                detail=f"Cost data not found for project: {display_name!r}",
            )
        final_costs: Dict[str, Any] = result.get("final_costs") or {}
        total_cash = float(final_costs.get("money", 0.0))
        for res_key, res_val in final_costs.items():
            if res_key != "money" and float(res_val) > 0:
                resources[res_key] = float(res_val)

    elif type == "improvement":
        if not improvement:
            raise HTTPException(status_code=422, detail="improvement is required for type=improvement")
        qty = int(target - current)
        if qty < 0:
            qty = 0
        unit_cash = pnw_costs.IMPROVEMENT_CASH_COSTS.get(improvement)
        if unit_cash is None:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown improvement: {improvement!r}",
            )
        total_cash = float(unit_cash) * qty
        rss_map = pnw_costs.IMPROVEMENT_RESOURCE_COSTS.get(improvement, {})
        for res_key, per_unit in rss_map.items():
            val = float(per_unit) * qty
            if val > 0:
                resources[res_key] = val

    elif type == "military":
        if not unit:
            raise HTTPException(status_code=422, detail="unit is required for type=military")
        unit_entry = UNIT_COSTS.get(unit)
        if unit_entry is None:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown military unit: {unit!r}",
            )
        delta = int(target - current)
        if delta < 0:
            delta = 0
        total_cash = float(unit_entry.get("cash", 0)) * delta
        for res_key, per_unit in unit_entry.items():
            if res_key != "cash":
                val = float(per_unit) * delta
                if val > 0:
                    resources[res_key] = val

    # ── Compute net_cash_day (use cache when fresh, else recalculate) ─────────
    net_cash_day: Optional[float] = None

    cached_nation_data = _cache_nation_get(nation_id)
    if cached_nation_data is not None:
        # Cache hit — extract net_cash_turn from the cached revenue block
        cached_rev = cached_nation_data.get("revenue") or {}
        net_cash_turn = float(cached_rev.get("net_cash_turn", 0.0) or 0.0)
        net_cash_day = net_cash_turn * 12
    else:
        # No cached data — run revenue_calc_sync in thread pool
        try:
            from Systems.PnW.Util.rev_correct import revenue_calc_sync
            from Systems.Functions.database_manager import (
                get_latest_resource_prices,
                get_latest_game_data,
                get_latest_game_info,
                get_latest_radiation_data,
            )

            cities_raw = await gdb.get_cities_for_nation(nation_id)
            cities_for_rev = [_compute_city_derived(dict(c)) for c in cities_raw]

            (
                price_data,
                colors_data,
                game_info,
                radiation_data,
            ) = await asyncio.gather(
                get_latest_resource_prices(),
                get_latest_game_data("colors"),
                get_latest_game_info(),
                get_latest_radiation_data(),
                return_exceptions=True,
            )

            if isinstance(price_data, Exception) or not price_data:
                price_data = {}
            if isinstance(colors_data, Exception) or not colors_data:
                colors_data = []
            if isinstance(game_info, Exception):
                game_info = None
            if isinstance(radiation_data, Exception):
                radiation_data = None

            market_prices: Dict[str, float] = {
                r: p["sell"] for r, p in price_data.items()
            } if price_data else {}

            colors_for_calc: Dict[str, float] = {
                c["color"]: float(c.get("turn_bonus", 0)) for c in colors_data
            } if colors_data else {}

            radiation = _build_radiation(radiation_data)
            seasonal_mod = _build_seasonal_mod(game_info)

            is_war = (
                (nation.get("offensive_wars_count") or 0) > 0
                or (nation.get("defensive_wars_count") or 0) > 0
            )

            nation_for_rev = {**nation, "cities": cities_for_rev}

            rev = await asyncio.to_thread(
                revenue_calc_sync,
                nation=nation_for_rev,
                radiation=radiation,
                treasures=[],
                prices=market_prices,
                colors=colors_for_calc,
                seasonal_mod=seasonal_mod,
                is_war=is_war,
            )
            if rev:
                net_cash_turn = float(rev.get("net_cash_num", 0.0) or 0.0)
                net_cash_day = net_cash_turn * 12
        except Exception as e:
            logger.error(
                f"cost_preview revenue_calc_sync failed for nation {nation_id}: {e}",
                exc_info=True,
            )
            net_cash_day = None

    # ── Compute days_to_goal ──────────────────────────────────────────────────
    days_to_goal: Optional[float] = None
    if net_cash_day is not None and net_cash_day > 0:
        days_to_goal = total_cash / net_cash_day

    return JSONResponse({
        "cash": total_cash,
        "resources": resources,
        "days_to_goal": days_to_goal,
        "breakdown": breakdown,
    })


# ── Snapshot endpoint ─────────────────────────────────────────────────────────

@router.post("/mynation/snapshot")
async def save_snapshot(request: Request, body: Dict[str, Any]) -> JSONResponse:
    """Capture or refresh the nation snapshot. Only accessible for the user's own linked nation."""
    nation_id = body.get("nation_id")
    if not isinstance(nation_id, int) or nation_id <= 0:
        raise HTTPException(status_code=422, detail="nation_id must be a positive integer.")

    await _require_own_nation(request, nation_id)

    gdb = _get_global_nations_db()
    mdb = _get_my_nations_db()

    nation = await gdb.get_nation(nation_id)
    if not nation:
        raise HTTPException(status_code=404, detail="Nation not found.")

    cities = await gdb.get_cities_for_nation(nation_id)
    ok = await mdb.save_snapshot(nation_id, nation, cities)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save snapshot.")

    snapshot = await mdb.get_snapshot(nation_id)
    return JSONResponse(snapshot or {"nation_id": nation_id, "saved": True})


# ── Awards endpoint ───────────────────────────────────────────────────────────
# Uses the identical pipeline as watch_api.py / leaderboard.js:
#   IRSWarsDB → _attach_war_attacks → WarsNetBD._get_nation_breakdown → _build_watch_response
# This guarantees every field (gross_cost, gains_cash, enemy_soldiers_killed, etc.)
# is computed the same way the leaderboard page computes them.

def _rank_nations_for_category(nations: Dict[str, Any], category: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Rank nations for one leaderboard category.  Mirrors leaderboard.js rankNations() exactly:
      - enrichNation fields already populated by _build_watch_response (gains_cash, etc.)
      - filter: skip None / NaN; skip zero unless allow_neg (best_net)
      - dense ranking — only yield groups with rank 1, 2, or 3
    Returns list of {rank, nations:[{name, …}]}
    """
    field = category["field"]
    asc = category["asc"]
    allow_neg = (category["id"] == "best_net")

    valid: List[Dict[str, Any]] = []
    for n in nations.values():
        val = n.get(field)
        if val is None:
            continue
        try:
            val = float(val)
        except (TypeError, ValueError):
            continue
        if not allow_neg and val == 0:
            continue
        valid.append({**n, field: val})

    if not valid:
        return []

    valid.sort(key=lambda x: x[field], reverse=not asc)

    groups: List[Dict[str, Any]] = []
    dense_rank = 1
    for i, n in enumerate(valid):
        if i > 0 and valid[i][field] != valid[i - 1][field]:
            dense_rank = i + 1
        if dense_rank > 3:
            break
        if groups and groups[-1]["rank"] == dense_rank:
            groups[-1]["nations"].append(n)
        else:
            groups.append({"rank": dense_rank, "nations": [n]})
    return groups


@router.get("/mynation/awards/{nation_id}")
async def get_nation_awards(request: Request, nation_id: int) -> JSONResponse:
    """
    Count how many times this nation placed 1st / 2nd / 3rd in each leaderboard
    category across every week and month that has war data.

    Uses the same pipeline as /api/watch/wars so rankings are identical to what
    the Leaderboard page shows.
    """
    await _require_own_nation(request, nation_id)

    import calendar as _calendar
    from datetime import date as _date, timedelta as _timedelta

    # ── lazy imports that mirror watch_api.py ─────────────────────────────────
    from Systems.Functions.irs_wars_db import IRSWarsDB
    from Systems.Functions.db_paths import IRS_WARS_DB_STR as WATCH_DB_PATH
    from Systems.PnW.Util.war_calc import get_resource_prices, calculate_unit_cost
    from Systems.PnW.MA.war_net_bd import WarsNetBD

    # Reuse watch_api helpers (imported at module level in watch_api.py)
    from web.api.watch_api import (
        _attach_war_attacks,
        _build_watch_response,
        WATCH_ALLIANCE_ID,
    )

    WATCH_DB_INST = IRSWarsDB(WATCH_DB_PATH)

    # ── look up the nation's name ─────────────────────────────────────────────
    gdb = _get_global_nations_db()
    nation = await gdb.get_nation(nation_id)
    if not nation:
        raise HTTPException(status_code=404, detail="Nation not found.")
    # The leaderboard pipeline names nations from att_nation_name / def_nation_name
    # in the wars rows, and falls back to GlobalNationsDB.  Use nation_name field
    # (the in-game nation name), not leader_name.
    nation_name: str = (nation.get("nation_name") or nation.get("name") or "").strip()
    if not nation_name:
        raise HTTPException(status_code=404, detail="Nation name could not be resolved.")

    # ── fetch all distinct war dates for Darkstar ─────────────────────────────
    def _sync_fetch_dates() -> List[str]:
        import sqlite3 as _sq
        with _sq.connect(WATCH_DB_INST.db_path) as conn:
            return [
                r[0] for r in conn.execute(
                    "SELECT DISTINCT date(substr(date,1,10)) AS d FROM wars "
                    "WHERE att_alliance_id=? OR def_alliance_id=? ORDER BY d ASC",
                    (WATCH_ALLIANCE_ID, WATCH_ALLIANCE_ID),
                ).fetchall()
                if r[0]
            ]

    all_dates = await asyncio.to_thread(_sync_fetch_dates)
    if not all_dates:
        return JSONResponse({"awards": [], "total_count": 0, "nation_name": nation_name})

    # ── build Sun–Sat week and calendar-month period buckets ──────────────────
    seen_weeks: Dict[str, Dict[str, str]] = {}
    seen_months: Dict[str, Dict[str, str]] = {}

    for ds in all_dates:
        d = _date.fromisoformat(ds)
        dsun = (d.weekday() + 1) % 7          # days since last Sunday
        week_sun = d - _timedelta(days=dsun)
        week_sat = week_sun + _timedelta(days=6)
        wk = week_sun.isoformat()
        if wk not in seen_weeks:
            seen_weeks[wk] = {"start": wk, "end": week_sat.isoformat()}

        mk = d.strftime("%Y-%m")
        if mk not in seen_months:
            y, m = int(mk[:4]), int(mk[5:7])
            last_day = _calendar.monthrange(y, m)[1]
            seen_months[mk] = {
                "start": f"{y:04d}-{m:02d}-01",
                "end": f"{y:04d}-{m:02d}-{last_day:02d}",
            }

    periods = (
        [{"type": "week",  **v} for v in seen_weeks.values()] +
        [{"type": "month", **v} for v in seen_months.values()]
    )

    # ── fetch resource prices once (needed by nation-breakdown) ───────────────
    try:
        resource_prices = await get_resource_prices()
    except Exception as e:
        logger.error("awards: could not fetch resource prices: %s", e)
        raise HTTPException(status_code=503, detail="Resource prices unavailable, cannot compute awards.")

    # ── per-category award accumulators ──────────────────────────────────────
    awards_data: Dict[str, Dict[int, int]] = {
        cat["id"]: {1: 0, 2: 0, 3: 0} for cat in LEADERBOARD_CATEGORIES
    }

    # ── process every period ─────────────────────────────────────────────────
    war_net_cog = WarsNetBD(bot=None)
    nation_name_lower = nation_name.lower()

    for period in periods:
        p_start = _date.fromisoformat(period["start"])
        p_end   = _date.fromisoformat(period["end"])
        try:
            # 1. Fetch raw wars for the period (same call as watch_api.py)
            wars = await WATCH_DB_INST.get_all_wars_for_alliance_in_range(
                WATCH_ALLIANCE_ID, start_date=p_start, end_date=p_end
            )
            if not wars:
                continue

            # 2. Bulk-attach all attacks (identical to watch_api.py)
            wars = await _attach_war_attacks(WATCH_DB_INST, wars)

            # 3. Build nation breakdown (identical to watch_api.py)
            nation_breakdown = await war_net_cog._get_nation_breakdown(
                wars, str(WATCH_ALLIANCE_ID), False, resource_prices
            )
            if not nation_breakdown:
                continue

            # 4. Enrich "Nation {id}" placeholder names from GlobalNationsDB
            #    (identical step from watch_api.py)
            placeholder_ids = [
                int(nid) for nid, nd in nation_breakdown.items()
                if (nd.get("name") or "").startswith("Nation ")
            ]
            if placeholder_ids:
                try:
                    real_names = await gdb.get_nation_names_by_ids(placeholder_ids)
                    for nid, nd in nation_breakdown.items():
                        if (nd.get("name") or "").startswith("Nation ") and int(nid) in real_names:
                            nd["name"] = real_names[int(nid)]
                except Exception:
                    pass

            # 5. Normalise into the same shape _build_watch_response produces
            watch_resp = _build_watch_response(nation_breakdown, resource_prices=resource_prices)
            nations = watch_resp.get("nations", {})
            if not nations:
                continue

            # 6. Check every category — find our nation by name (case-insensitive)
            for cat in LEADERBOARD_CATEGORIES:
                ranked = _rank_nations_for_category(nations, cat)
                for group in ranked:
                    rank = group["rank"]
                    for n in group["nations"]:
                        if (n.get("name") or "").strip().lower() == nation_name_lower:
                            awards_data[cat["id"]][rank] += 1
                            break   # found in this group, move to next group

        except Exception as e:
            logger.debug(
                "awards: error processing period %s – %s: %s",
                period["start"], period["end"], e, exc_info=True,
            )
            continue

    # ── build response (only categories with at least one award) ─────────────
    awards_list: List[Dict[str, Any]] = []
    total_awards = 0

    for cat in LEADERBOARD_CATEGORIES:
        counts = awards_data[cat["id"]]
        cat_total = counts[1] + counts[2] + counts[3]
        if cat_total == 0:
            continue
        awards_list.append({
            "category_id":    cat["id"],
            "category_label": cat["label"],
            "prefix":         cat["prefix"],
            "first":          counts[1],
            "second":         counts[2],
            "third":          counts[3],
            "total":          cat_total,
        })
        total_awards += cat_total

    awards_list.sort(key=lambda x: x["total"], reverse=True)

    return JSONResponse({
        "awards":       awards_list,
        "total_count":  total_awards,
        "nation_id":    nation_id,
        "nation_name":  nation_name,
    })

"""
pnw_costs.py — Politics & War purchase cost formulas for HoldingsDB.

All formulas and cost tables are imported directly from the authoritative
sources already in the codebase:

  Systems/PnW/IA/costs.py      → infra, land, city, project formulas + PROJECT_BUILD_COSTS
  Systems/PnW/Util/war_calc.py → IMPROVEMENT_COSTS (cash + resource components)

This file is a thin adapter that:
  1. Re-exports the raw formula functions under stable names.
  2. Provides helpers that work with DB column names and nation dicts
     (as stored in GlobalNationsDB) rather than the display-layer dicts
     that costs.py was designed for.
  3. Exposes cost functions that return BOTH cash AND resource components
     so HoldingsDB can deduct everything a purchase actually costs.

Resource components ARE deducted for improvements and projects.
Nations spend resources directly from their stockpile when building —
these are not bankrec transfers and must be tracked separately.

IMPORTANT: All cost calculations use the EXACT same functions as the /costs
command (Systems/PnW/IA/costs.py) — infra_purchase_cost, land_purchase_cost,
and city_purchase_cost — so results are always consistent between the listener
and the command output.  The top-20 city average is fetched from the DB cache
(updated every 15 min by the harvester) so city costs are accurate.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Re-export raw formula functions from costs.py ─────────────────────────────

from Systems.PnW.IA.costs import (
    # Infrastructure — exact recursive formula (same as /costs command)
    infra_price,
    calc_infra_value,
    infra_purchase_cost as _infra_purchase_cost_raw,
    # Land — exact recursive formula (same as /costs command)
    land_price,
    calc_land_value,
    land_purchase_cost as _land_purchase_cost_raw,
    # City
    city_purchase_cost as _city_purchase_cost_raw,
    # Project
    PROJECT_BUILD_COSTS,
    project_build_cost as _project_build_cost_raw,
    calculate_project_discounts,
)

# ── Re-export improvement costs from war_calc.py ──────────────────────────────

from Systems.PnW.Util.war_calc import IMPROVEMENT_COSTS as _WAR_CALC_IMPROVEMENT_COSTS


# ── DB column name → war_calc key mapping ─────────────────────────────────────
# GlobalNationsDB cities table uses snake_case column names; war_calc uses
# slightly different keys for power plants.

_DB_COL_TO_WAR_CALC: Dict[str, str] = {
    # Power
    "coal_power":          "coal_power_plant",
    "oil_power":           "oil_power_plant",
    "nuclear_power":       "nuclear_power_plant",
    "wind_power":          "wind_power_plant",
    # Raw resources
    "coal_mine":           "coal_mine",
    "oil_well":            "oil_well",
    "uranium_mine":        "uranium_mine",
    "lead_mine":           "lead_mine",
    "iron_mine":           "iron_mine",
    "bauxite_mine":        "bauxite_mine",
    # Manufacturing
    "oil_refinery":        "oil_refinery",
    "steel_mill":          "steel_mill",
    "aluminum_refinery":   "aluminum_refinery",
    "munitions_factory":   "munitions_factory",
    # Agriculture
    "farm":                "farm",
    # Civil
    "police_station":      "police_station",
    "hospital":            "hospital",
    "recycling_center":    "recycling_center",
    "subway":              "subway",
    "supermarket":         "supermarket",
    "bank":                "bank",
    "shopping_mall":       "shopping_mall",
    "stadium":             "stadium",
    # Military
    "barracks":            "barracks",
    "factory":             "factory",
    "hangar":              "hangar",
    "drydock":             "drydock",
}

# Build a DB-column → cash-only cost dict
IMPROVEMENT_CASH_COSTS: Dict[str, float] = {
    db_col: float((_WAR_CALC_IMPROVEMENT_COSTS.get(wc_key) or {}).get("cash", 0))
    for db_col, wc_key in _DB_COL_TO_WAR_CALC.items()
}

# Build a DB-column → {resource: amount} dict for resource components only
# (excludes "cash" — that's handled by IMPROVEMENT_CASH_COSTS)
IMPROVEMENT_RESOURCE_COSTS: Dict[str, Dict[str, float]] = {}
for _db_col, _wc_key in _DB_COL_TO_WAR_CALC.items():
    _entry = _WAR_CALC_IMPROVEMENT_COSTS.get(_wc_key) or {}
    _rss = {k: float(v) for k, v in _entry.items() if k != "cash" and float(v) > 0}
    if _rss:
        IMPROVEMENT_RESOURCE_COSTS[_db_col] = _rss

# DB column name → display name mapping for PROJECT_BUILD_COSTS
# costs.py uses Title Case names; GlobalNationsDB uses snake_case boolean columns.
_PROJECT_DB_COL_TO_DISPLAY: Dict[str, str] = {
    "activity_center":                      "Activity Center",
    "advanced_engineering_corps":           "Advanced Engineering Corps",
    "arable_land_agency":                   "Arable Land Agency",
    "bureau_of_domestic_affairs":           "Bureau of Domestic Affairs",
    "center_for_civil_engineering":         "Center Civil Engineering",
    "clinical_research_center":             "Clinical Research Center",
    "government_support_agency":            "Government Support Agency",
    "green_technologies":                   "Green Technologies",
    "international_trade_center":           "International Trade Center",
    "advanced_pirate_economy":              "Advanced Pirate Economy",
    "central_intelligence_agency":          "Central Intelligence Agency",
    "guiding_satellite":                    "Guiding Satellite",
    "iron_dome":                            "Iron Dome",
    "missile_launch_pad":                   "Missile Launch Pad",
    "nuclear_research_facility":            "Nuclear Research Facility",
    "propaganda_bureau":                    "Propaganda Bureau",
    "space_program":                        "Space Program",
    "vital_defense_system":                 "Vital Defense System",
    "military_research_center":             "Military Research Center",
    "military_doctrine":                    "Military Doctrine",
    "arms_stockpile":                       "Arms Stockpile",
    "bauxite_works":                        "Bauxite Works",
    "emergency_gasoline_reserve":           "Emergency Gasoline Reserve",
    "fallout_shelter":                      "Fallout Shelter",
    "iron_works":                           "Iron Works",
    "mars_landing":                         "Mars Landing",
    "mass_irrigation":                      "Mass Irrigation",
    "military_salvage":                     "Military Salvage",
    "moon_landing":                         "Moon Landing",
    "nuclear_launch_facility":              "Nuclear Launch Facility",
    "pirate_economy":                       "Pirate Economy",
    "recycling_initiative":                 "Recycling Initiative",
    "research_and_development_center":      "Research & Development Center",
    "specialized_police_training_program":  "Specialized Police Training Program",
    "spy_satellite":                        "Spy Satellite",
    "surveillance_network":                 "Surveillance Network",
    "telecommunications_satellite":         "Telecommunications Satellite",
    "uranium_enrichment_program":           "Uranium Enrichment Program",
}

# All boolean project DB column names we track
ALL_PROJECT_FIELDS: List[str] = list(_PROJECT_DB_COL_TO_DISPLAY.keys())


# ── Top-20 city average cache ─────────────────────────────────────────────────
# Mirrors what the /costs command does: read from db_manager cache (updated
# every 15 min by the harvester).  Falls back to 40.0 if unavailable.

def _get_top_20_average() -> float:
    """
    Return the current game-wide top-20 city average from the DB cache.
    This is the same value the /costs command uses so city cost calculations
    are always consistent between the listener and the command output.

    Reads synchronously from reaper.db (game_info table) since this is called
    from within an already-running asyncio event loop (subscription context).
    """
    try:
        import sqlite3
        from Systems.Functions.db_paths import REAPER_DB_STR
        conn = sqlite3.connect(REAPER_DB_STR)
        row = conn.execute(
            "SELECT city_average FROM game_info ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row and row[0] is not None:
            return float(row[0])
    except Exception as e:
        logger.debug(f"_get_top_20_average fallback to 40.0: {e}")
    return 40.0


# ── City cost ─────────────────────────────────────────────────────────────────

def city_cost(
    num_cities_before: int,
    top_20_average: Optional[float] = None,
    nation_data: Optional[Dict[str, Any]] = None,
) -> float:
    """
    Cash cost to buy the next city when the nation currently has
    `num_cities_before` cities.

    Uses the EXACT same formula as the /costs command:
      city_purchase_cost(city_to_buy, top_20_average, nation_data)

    top_20_average is fetched from the DB cache if not supplied, matching
    the /costs command behaviour exactly.

    Args:
        num_cities_before : Current city count (before purchase).
        top_20_average    : Game-wide top-20 city average.  If None, fetched
                            from the DB cache automatically.
        nation_data       : Nation dict for discount calculation.
                            Pass None or {} for no discounts.

    Returns:
        Final cash cost in dollars (after all applicable discounts).
    """
    if top_20_average is None:
        top_20_average = _get_top_20_average()
    result = _city_purchase_cost_raw(
        city_to_buy=num_cities_before + 1,
        top_20_average=top_20_average,
        nation_data=nation_data or {},
    )
    return float(result.get("final_cost", 0.0))


# ── Infrastructure cost ───────────────────────────────────────────────────────

def infra_cost(
    infra_before: float,
    infra_after: float,
    nation_data: Optional[Dict[str, Any]] = None,
) -> float:
    """
    Cash cost to buy infrastructure in one city from `infra_before` to
    `infra_after`, applying CCE/AEC/Urbanization discounts from nation_data.

    Uses the EXACT same function as the /costs command:
      infra_purchase_cost(current, amount_to_buy, nation_data)
    which calls calc_infra_value (exact recursive formula) internally.

    Args:
        infra_before : Infrastructure level before purchase.
        infra_after  : Infrastructure level after purchase.
        nation_data  : Nation dict for discount calculation. Pass None for no discounts.

    Returns:
        Final cash cost in dollars, or 0 if infra_after <= infra_before.
    """
    if infra_after <= infra_before:
        return 0.0
    amount = float(infra_after) - float(infra_before)
    result = _infra_purchase_cost_raw(
        current_infra=float(infra_before),
        infra_to_buy=amount,
        nation_data=nation_data or {},
    )
    return float(result.get("final_cost", 0.0))


# ── Land cost ─────────────────────────────────────────────────────────────────

def land_cost(
    land_before: float,
    land_after: float,
    nation_data: Optional[Dict[str, Any]] = None,
) -> float:
    """
    Cash cost to buy land in one city from `land_before` to `land_after`,
    applying ALA/AEC/Rapid Expansion discounts from nation_data.

    Uses the EXACT same function as the /costs command:
      land_purchase_cost(current, amount_to_buy, nation_data)
    which calls calc_land_value (exact recursive formula) internally.

    Args:
        land_before : Land level before purchase.
        land_after  : Land level after purchase.
        nation_data : Nation dict for discount calculation. Pass None for no discounts.

    Returns:
        Final cash cost in dollars, or 0 if land_after <= land_before.
    """
    if land_after <= land_before:
        return 0.0
    amount = float(land_after) - float(land_before)
    result = _land_purchase_cost_raw(
        current_land=float(land_before),
        land_to_buy=amount,
        nation_data=nation_data or {},
    )
    return float(result.get("final_cost", 0.0))


# ── Improvement purchase cost ─────────────────────────────────────────────────

def improvement_purchase_cost(
    improvement: str,
    count_before: int,
    count_after: int,
) -> float:
    """
    Cash cost to buy improvements of a given type (DB column name).
    Only counts increases. Resource components excluded (see module docstring).
    """
    delta = max(0, int(count_after) - int(count_before))
    if delta == 0:
        return 0.0
    unit_cost = IMPROVEMENT_CASH_COSTS.get(improvement, 0.0)
    return float(delta * unit_cost)


def city_improvements_cost(
    city_before: Dict[str, Any],
    city_after: Dict[str, Any],
) -> float:
    """
    Total cash cost of all improvement purchases detected between two city
    snapshots (DB column names). Only counts increases.
    """
    total = 0.0
    for col, unit_cost in IMPROVEMENT_CASH_COSTS.items():
        before = int(city_before.get(col) or 0)
        after  = int(city_after.get(col) or 0)
        delta  = max(0, after - before)
        if delta:
            total += delta * unit_cost
    return total


def city_improvements_resource_costs(
    city_before: Dict[str, Any],
    city_after: Dict[str, Any],
) -> Dict[str, float]:
    """
    Resource costs (steel, aluminum) consumed when building improvements
    between two city snapshots.  Returns {resource: total_amount}.

    Only counts increases (purchases).  Losses/demolitions cost nothing.
    """
    totals: Dict[str, float] = {}
    for col, rss_map in IMPROVEMENT_RESOURCE_COSTS.items():
        before = int(city_before.get(col) or 0)
        after  = int(city_after.get(col) or 0)
        delta  = max(0, after - before)
        if delta:
            for resource, per_unit in rss_map.items():
                totals[resource] = totals.get(resource, 0.0) + per_unit * delta
    return totals


# ── Project purchase cost ─────────────────────────────────────────────────────

def project_cash_cost(
    db_col: str,
    nation_data: Optional[Dict[str, Any]] = None,
) -> float:
    """
    Cash (money) cost to buy a single project identified by its DB column name,
    applying Technological Advancement policy discount if applicable.

    Args:
        db_col      : DB column name (e.g. "iron_dome", "missile_launch_pad").
        nation_data : Nation dict for discount calculation. Pass None for no discounts.

    Returns:
        Final cash cost in dollars, or 0 if the project is unknown.
    """
    display_name = _PROJECT_DB_COL_TO_DISPLAY.get(db_col)
    if not display_name:
        return 0.0
    result = _project_build_cost_raw(display_name, nation_data or {})
    if not result:
        return 0.0
    return float((result.get("final_costs") or {}).get("money", 0.0))


def projects_purchased_cost(
    nation_before: Dict[str, Any],
    nation_after: Dict[str, Any],
) -> float:
    """
    Total cash cost of all projects that flipped from falsy→truthy between
    two nation snapshots, applying Technological Advancement policy discount.

    Args:
        nation_before : Nation dict from GlobalNationsDB before the update.
        nation_after  : Incoming nation dict from the subscription event.

    Returns:
        Total cash cost in dollars.
    """
    total = 0.0
    for db_col in ALL_PROJECT_FIELDS:
        was_owned = bool(nation_before.get(db_col))
        now_owned = bool(nation_after.get(db_col))
        if not was_owned and now_owned:
            total += project_cash_cost(db_col, nation_after)
    return total


def projects_purchased_resource_costs(
    nation_before: Dict[str, Any],
    nation_after: Dict[str, Any],
) -> Dict[str, float]:
    """
    Resource costs consumed when building projects that flipped from
    falsy→truthy between two nation snapshots, applying Technological
    Advancement policy discount if the nation has that policy active.

    Returns {resource: total_amount} for all non-cash components.
    The cash component is handled separately by projects_purchased_cost().
    """
    # Check if Technological Advancement discount applies
    _raw_dp = str(nation_after.get("domestic_policy") or "").upper()
    _dp = _raw_dp.replace("DOMESTICPOLICY.", "").replace(" ", "_")
    if _dp == "TECHNOLOGICAL_ADVANCEMENT":
        from Systems.PnW.IA.costs import calculate_project_discounts
        _discounts = calculate_project_discounts(nation_after)
        discount_rate = 0.05 * _discounts.get("domestic_policy_multiplier", 1.0)
    else:
        discount_rate = 0.0

    totals: Dict[str, float] = {}
    for db_col in ALL_PROJECT_FIELDS:
        was_owned = bool(nation_before.get(db_col))
        now_owned = bool(nation_after.get(db_col))
        if not was_owned and now_owned:
            display_name = _PROJECT_DB_COL_TO_DISPLAY.get(db_col)
            if not display_name:
                continue
            raw_costs = PROJECT_BUILD_COSTS.get(display_name) or {}
            for resource, amount in raw_costs.items():
                if resource != "money" and amount > 0:
                    final_amount = float(amount) * (1.0 - discount_rate)
                    totals[resource] = totals.get(resource, 0.0) + final_amount
    return totals

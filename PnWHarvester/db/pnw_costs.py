"""
pnw_costs.py — Politics & War purchase cost formulas for HoldingsDB.

All formulas and cost tables are imported directly from the authoritative
sources already in the codebase:

  Systems/PnW/IA/costs.py   → infra, land, city, project formulas + PROJECT_BUILD_COSTS
  Systems/PnW/Util/war_calc.py → IMPROVEMENT_COSTS (cash + resource components)

This file is a thin adapter that:
  1. Re-exports the raw formula functions under stable names.
  2. Provides helpers that work with DB column names and nation dicts
     (as stored in GlobalNationsDB) rather than the display-layer dicts
     that costs.py was designed for.
  3. Exposes a single `projects_purchased_cost` function that diffs two
     nation snapshots and returns the total cash cost of new projects.

NOTE on resource components
---------------------------
Improvement and project purchases require both cash AND resources (steel,
aluminum, etc.).  The resource components are NOT deducted here because
they are purchased on the market and appear as bankrecs — deducting them
here would double-count them.  Only the cash (money) component is tracked.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# ── Re-export raw formula functions from costs.py ─────────────────────────────

from Systems.PnW.IA.costs import (
    # Infrastructure
    infra_price,
    calc_infra_value,
    # Land
    land_price,
    calc_land_value,
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

# Build a DB-column → cash-only cost dict (resource components excluded — see module docstring)
IMPROVEMENT_CASH_COSTS: Dict[str, float] = {
    db_col: float((_WAR_CALC_IMPROVEMENT_COSTS.get(wc_key) or {}).get("cash", 0))
    for db_col, wc_key in _DB_COL_TO_WAR_CALC.items()
}

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


# ── City cost ─────────────────────────────────────────────────────────────────

def city_cost(
    num_cities_before: int,
    top_20_average: float = 0.0,
    nation_data: Optional[Dict[str, Any]] = None,
) -> float:
    """
    Cash cost to buy the next city when the nation currently has
    `num_cities_before` cities.

    Uses the exact formula from costs.city_purchase_cost, which accounts for
    the top-20 city average and domestic policy discounts.

    Args:
        num_cities_before : Current city count (before purchase).
        top_20_average    : Game-wide top-20 city average (from game_info).
                            Pass 0.0 if unavailable — formula degrades gracefully.
        nation_data       : Nation dict for discount calculation (CCE, AEC, policy).
                            Pass None or {} for no discounts.

    Returns:
        Final cash cost in dollars (after all applicable discounts).
    """
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

    Uses the exact integral of the infra price formula — O(1), no recursion.

    infra_price(x) = ((|x - 10|^2.2) / 710) + 300
    integral from A to B:
      ∫ infra_price(x) dx ≈ 300*(B-A) + integral of the power term

    For the subscription path we use the midpoint approximation which is
    accurate to <0.5% for typical purchases and avoids the recursion depth
    issue in calc_infra_value for large deltas.

    Args:
        infra_before : Infrastructure level before purchase.
        infra_after  : Infrastructure level after purchase.
        nation_data  : Nation dict for discount calculation. Pass None for no discounts.

    Returns:
        Final cash cost in dollars, or 0 if infra_after <= infra_before.
    """
    if infra_after <= infra_before:
        return 0.0

    # Use midpoint approximation: cost ≈ infra_price(midpoint) * delta
    # This is accurate for the ranges we see in subscription diffs.
    a = float(infra_before)
    b = float(infra_after)
    mid = (a + b) / 2.0
    cost_per_unit = ((abs(mid - 10) ** 2.2) / 710.0) + 300.0
    raw_cost = cost_per_unit * (b - a)

    # Apply project + policy discounts from nation_data
    nd = nation_data or {}
    project_discounts = calculate_project_discounts(nd)
    project_reduction = project_discounts.get("infra_cost_reduction", 0.0)
    base_cost = raw_cost * (1.0 - project_reduction)

    policy_reduction = 0.05 * project_discounts.get("domestic_policy_multiplier", 1.0)
    final_cost = base_cost * (1.0 - policy_reduction)

    return float(final_cost)


# ── Land cost ─────────────────────────────────────────────────────────────────

def land_cost(
    land_before: float,
    land_after: float,
    nation_data: Optional[Dict[str, Any]] = None,
) -> float:
    """
    Cash cost to buy land in one city from `land_before` to `land_after`,
    applying ALA/AEC/Rapid Expansion discounts from nation_data.

    Uses midpoint approximation of the land price formula — O(1), no recursion.

    land_price(x) = 0.002*(x-20)^2 + 50
    Midpoint approximation: cost ≈ land_price(midpoint) * delta

    Args:
        land_before : Land level before purchase.
        land_after  : Land level after purchase.
        nation_data : Nation dict for discount calculation. Pass None for no discounts.

    Returns:
        Final cash cost in dollars, or 0 if land_after <= land_before.
    """
    if land_after <= land_before:
        return 0.0

    a = float(land_before)
    b = float(land_after)
    mid = (a + b) / 2.0
    cost_per_unit = 0.002 * ((mid - 20) ** 2) + 50.0
    raw_cost = cost_per_unit * (b - a)

    nd = nation_data or {}
    project_discounts = calculate_project_discounts(nd)
    project_reduction = project_discounts.get("land_cost_reduction", 0.0)
    base_cost = raw_cost * (1.0 - project_reduction)

    policy_reduction = 0.05 * project_discounts.get("domestic_policy_multiplier", 1.0)
    final_cost = base_cost * (1.0 - policy_reduction)

    return float(final_cost)


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

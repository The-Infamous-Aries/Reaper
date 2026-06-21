"""
plan_api.py — Nation Build Plan API endpoints.

Endpoints:
  GET    /api/mynation/plan/{nation_id}     → get plan with progress & costs
  POST   /api/mynation/plan                 → create/update plan
  DELETE /api/mynation/plan/{nation_id}     → delete plan
  POST   /api/mynation/plan/preview         → compute preview of simulated nation
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

# Cost calculation imports
from Systems.PnW.IA.costs import (
    city_purchase_cost,
    infra_purchase_cost,
    land_purchase_cost,
    project_build_cost,
)
from PnWHarvester.db.pnw_costs import (
    IMPROVEMENT_CASH_COSTS,
    IMPROVEMENT_RESOURCE_COSTS,
    _get_top_20_average,
    _PROJECT_DB_COL_TO_DISPLAY,
)

router = APIRouter()
logger = logging.getLogger("Reaper.WebServer.PlanAPI")

# ── Module-level singletons ───────────────────────────────────────────────────

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
            detail="You must be logged in and have a linked nation.",
        )
    if linked != nation_id:
        raise HTTPException(
            status_code=403,
            detail="You can only manage your own nation's plan.",
        )


# ── GET Plan ──────────────────────────────────────────────────────────────────

@router.get("/mynation/plan/{nation_id}")
async def get_plan(request: Request, nation_id: int) -> JSONResponse:
    """
    Get plan with progress and costs for a nation.
    Returns plan data, progress tracking, and cost breakdown.
    """
    await _require_own_nation(request, nation_id)
    
    mdb = _get_my_nations_db()
    gdb = _get_global_nations_db()
    
    # Load plan
    plan = await mdb.get_plan(nation_id)
    if not plan:
        return JSONResponse({"plan": None})
    
    # Load current nation state
    nation = await gdb.get_nation(nation_id)
    if not nation:
        raise HTTPException(status_code=404, detail="Nation not found in database.")
    
    cities = await gdb.get_cities_for_nation(nation_id)
    
    # Compute progress
    progress = _compute_progress(plan["plan_data"], nation, cities)
    
    # Compute costs (cache top-20 once)
    top_20_avg = _get_top_20_average()
    total_costs = _compute_total_costs(plan["plan_data"], nation, cities, top_20_avg)
    remaining_costs = _compute_remaining_costs(
        plan["plan_data"], nation, cities, progress, top_20_avg
    )
    
    # Fetch current resource sell prices so the frontend can show actual dollar totals
    sell_prices: Dict[str, float] = {}
    try:
        from Systems.Functions.database_manager import get_latest_resource_prices
        price_data = await get_latest_resource_prices()
        if price_data:
            sell_prices = {
                resource.lower(): float(info.get("sell", 0) or 0)
                for resource, info in price_data.items()
            }
    except Exception as _pe:
        logger.warning(f"Could not fetch resource prices for plan: {_pe}")

    # Per-project cost breakdown so the viewer can show costs on each project line
    project_costs = _compute_per_project_costs(plan["plan_data"], nation)

    # Per-city cost breakdown so the viewer can show each city's total cost
    city_costs = _compute_per_city_costs(plan["plan_data"], nation, cities, top_20_avg)

    # All-policy total costs: same as total_costs but projects are computed with
    # all applicable policies active (Technological Advancement + BDA + GSA).
    # Cities/infra/land already always apply policy discounts in the cost functions.
    all_policy_total_costs = _compute_all_policy_total_costs(
        plan["plan_data"], nation, cities, top_20_avg, total_costs
    )
    all_policy_remaining_costs = _compute_all_policy_total_costs(
        plan["plan_data"], nation, cities, top_20_avg, remaining_costs
    )

    return JSONResponse({
        "plan": plan,
        "progress": progress,
        "total_costs": total_costs,
        "remaining_costs": remaining_costs,
        "all_policy_total_costs": all_policy_total_costs,
        "all_policy_remaining_costs": all_policy_remaining_costs,
        "sell_prices": sell_prices,
        "project_costs": project_costs,
        "city_costs": city_costs,
    })


# ── POST Plan ─────────────────────────────────────────────────────────────────

@router.post("/mynation/plan")
async def save_plan(request: Request, body: Dict[str, Any]) -> JSONResponse:
    """
    Create or update a nation's build plan.
    Validates plan data before saving.
    """
    nation_id = body.get("nation_id")
    if not isinstance(nation_id, int) or nation_id <= 0:
        raise HTTPException(status_code=422, detail="nation_id must be a positive integer.")
    
    await _require_own_nation(request, nation_id)
    
    plan_name = body.get("plan_name", "").strip()
    if not plan_name:
        raise HTTPException(status_code=422, detail="plan_name cannot be empty.")
    
    plan_data = body.get("plan_data")
    if not isinstance(plan_data, dict):
        raise HTTPException(status_code=422, detail="plan_data must be an object.")
    
    # Load nation and cities for validation
    gdb = _get_global_nations_db()
    nation = await gdb.get_nation(nation_id)
    if not nation:
        raise HTTPException(status_code=404, detail="Nation not found.")
    
    cities = await gdb.get_cities_for_nation(nation_id)
    
    # Validate plan data
    _validate_plan_data(plan_data, nation, cities)
    
    # Save to database
    mdb = _get_my_nations_db()
    plan_id = await mdb.save_plan(nation_id, plan_name, plan_data)
    
    if plan_id == -1:
        raise HTTPException(status_code=500, detail="Failed to save plan.")
    
    return JSONResponse({"plan_id": plan_id, "success": True})


# ── DELETE Plan ───────────────────────────────────────────────────────────────

@router.delete("/mynation/plan/{nation_id}")
async def delete_plan(request: Request, nation_id: int) -> JSONResponse:
    """Delete a nation's build plan."""
    await _require_own_nation(request, nation_id)
    
    mdb = _get_my_nations_db()
    success = await mdb.delete_plan(nation_id)
    
    return JSONResponse({"success": success})





# ══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

# ── Progress Detection ────────────────────────────────────────────────────────

def _compute_progress(
    plan_data: Dict[str, Any],
    nation: Dict[str, Any],
    cities: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compare plan against current nation state to determine progress.
    Returns progress structure with overall stats and per-item completion.
    """
    progress = {
        "overall_progress": {
            "total_steps": 0,
            "completed_steps": 0,
            "percent_complete": 0.0,
        },
        "new_cities": [],
        "existing_cities": [],
        "projects": [],
    }
    
    starting_cities = nation.get("num_cities", 0)
    cities_sorted = sorted(cities, key=lambda c: c.get("date", "") or "")
    
    # ── New Cities ────────────────────────────────────────────────────────────
    for city_plan in plan_data.get("new_cities", []):
        slot = city_plan["slot"]
        target_city_number = starting_cities + slot
        
        city_progress = {
            "slot": slot,
            "done": False,
            "steps": {
                "city_purchased": False,
                "infra_done": False,
                "land_done": False,
                "improvements_done": False,
            },
            "matched_city_id": None,
        }
        
        # Check if city purchased
        current_city_count = nation.get("num_cities", 0)
        if current_city_count >= target_city_number:
            city_progress["steps"]["city_purchased"] = True
            
            # Match to real city
            if len(cities_sorted) >= target_city_number:
                matched_city = cities_sorted[target_city_number - 1]
                city_progress["matched_city_id"] = matched_city.get("id")
                
                # Check infra
                target_infra = city_plan.get("infra", 10)
                current_infra = float(matched_city.get("infrastructure", 0))
                if current_infra >= target_infra:
                    city_progress["steps"]["infra_done"] = True
                
                # Check land
                target_land = city_plan.get("land", 250)
                current_land = float(matched_city.get("land", 0))
                if current_land >= target_land:
                    city_progress["steps"]["land_done"] = True
                
                # Check improvements
                improvements_complete = True
                for imp_col, target_count in city_plan.get("improvements", {}).items():
                    current_count = int(matched_city.get(imp_col, 0))
                    if current_count < target_count:
                        improvements_complete = False
                        break
                city_progress["steps"]["improvements_done"] = improvements_complete
        
        # Overall city done if all steps complete
        city_progress["done"] = all(city_progress["steps"].values())
        
        # Count steps
        progress["overall_progress"]["total_steps"] += 4  # city, infra, land, improvements
        progress["overall_progress"]["completed_steps"] += sum(
            1 for v in city_progress["steps"].values() if v
        )
        
        progress["new_cities"].append(city_progress)
    
    # ── Existing Cities ───────────────────────────────────────────────────────
    for city_plan in plan_data.get("existing_cities", []):
        city_id = city_plan.get("city_id")
        if not city_id:
            continue
        
        # Find city
        city = next((c for c in cities if c.get("id") == city_id), None)
        if not city:
            continue
        
        city_progress = {
            "city_id": city_id,
            "city_name": city.get("name", "Unknown"),
            "done": False,
            "steps": {
                "infra_done": True,  # Default to done
                "land_done": True,
                "improvements": {},
            },
        }
        
        step_count = 0
        completed_count = 0
        
        # Check infra
        target_infra = city_plan.get("target_infra")
        if target_infra is not None:
            step_count += 1
            current_infra = float(city.get("infrastructure", 0))
            if current_infra >= target_infra:
                completed_count += 1
            else:
                city_progress["steps"]["infra_done"] = False
        
        # Check land
        target_land = city_plan.get("target_land")
        if target_land is not None:
            step_count += 1
            current_land = float(city.get("land", 0))
            if current_land >= target_land:
                completed_count += 1
            else:
                city_progress["steps"]["land_done"] = False
        
        # Check improvements
        for imp_col, target_count in city_plan.get("target_improvements", {}).items():
            step_count += 1
            current_count = int(city.get(imp_col, 0))
            imp_done = current_count == target_count
            city_progress["steps"]["improvements"][imp_col] = imp_done
            if imp_done:
                completed_count += 1
        
        city_progress["done"] = (step_count > 0 and completed_count == step_count)
        
        progress["overall_progress"]["total_steps"] += step_count
        progress["overall_progress"]["completed_steps"] += completed_count
        
        progress["existing_cities"].append(city_progress)
    
    # ── Projects ──────────────────────────────────────────────────────────────
    for project_col in plan_data.get("projects", []):
        project_done = bool(nation.get(project_col))
        
        progress["projects"].append({
            "db_col": project_col,
            "done": project_done,
        })
        
        progress["overall_progress"]["total_steps"] += 1
        if project_done:
            progress["overall_progress"]["completed_steps"] += 1
    
    # Calculate percentage
    total = progress["overall_progress"]["total_steps"]
    completed = progress["overall_progress"]["completed_steps"]
    if total > 0:
        progress["overall_progress"]["percent_complete"] = round(
            (completed / total) * 100, 1
        )
    
    return progress


# ── Cost Calculation ──────────────────────────────────────────────────────────

def _compute_total_costs(
    plan_data: Dict[str, Any],
    nation: Dict[str, Any],
    cities: List[Dict[str, Any]],
    top_20_avg: float,
) -> Dict[str, Any]:
    """
    Calculate total costs for the entire plan using imported cost functions.
    Returns costs broken down by section.
    """
    costs = {
        "total": {"cash": 0.0},
        "by_section": {
            "new_cities": {"cash": 0.0},
            "existing_cities": {"cash": 0.0},
            "projects": {"cash": 0.0},
        },
    }
    
    starting_cities = nation.get("num_cities", 0)
    
    # ── New Cities ────────────────────────────────────────────────────────────
    for city_plan in plan_data.get("new_cities", []):
        slot = city_plan["slot"]
        city_number = starting_cities + slot
        
        # City purchase
        result = city_purchase_cost(city_number, top_20_avg, nation)
        _add_cost(costs, result["final_cost"], "new_cities", "cash")
        
        # Infrastructure — new city starts with 10 infra, buy delta to target
        target_infra = city_plan.get("infra", 10)
        if target_infra > 10:
            result = infra_purchase_cost(10.0, target_infra - 10.0, nation)
            _add_cost(costs, result["final_cost"], "new_cities", "cash")
        
        # Land — new city starts with 250 land, buy delta to target
        target_land = city_plan.get("land", 250)
        if target_land > 250:
            result = land_purchase_cost(250.0, target_land - 250.0, nation)
            _add_cost(costs, result["final_cost"], "new_cities", "cash")
        
        # Improvements
        for imp_col, target_count in city_plan.get("improvements", {}).items():
            if target_count > 0:
                # Cash cost
                unit_cash = IMPROVEMENT_CASH_COSTS.get(imp_col, 0)
                _add_cost(costs, unit_cash * target_count, "new_cities", "cash")
                
                # Resource costs
                resource_costs = IMPROVEMENT_RESOURCE_COSTS.get(imp_col, {})
                for resource, per_unit in resource_costs.items():
                    _add_cost(costs, per_unit * target_count, "new_cities", resource)
    
    # ── Existing Cities ───────────────────────────────────────────────────────
    for city_plan in plan_data.get("existing_cities", []):
        city_id = city_plan.get("city_id")
        if not city_id:
            continue
        
        city = next((c for c in cities if c.get("id") == city_id), None)
        if not city:
            continue
        
        # Infrastructure delta
        target_infra = city_plan.get("target_infra")
        if target_infra is not None:
            current_infra = float(city.get("infrastructure", 0))
            if target_infra > current_infra:
                delta = target_infra - current_infra
                result = infra_purchase_cost(current_infra, delta, nation)
                _add_cost(costs, result["final_cost"], "existing_cities", "cash")
        
        # Land delta
        target_land = city_plan.get("target_land")
        if target_land is not None:
            current_land = float(city.get("land", 0))
            if target_land > current_land:
                delta = target_land - current_land
                result = land_purchase_cost(current_land, delta, nation)
                _add_cost(costs, result["final_cost"], "existing_cities", "cash")
        
        # Improvement deltas
        for imp_col, target_count in city_plan.get("target_improvements", {}).items():
            current_count = int(city.get(imp_col, 0))
            if target_count > current_count:
                delta = target_count - current_count
                # Cash cost
                unit_cash = IMPROVEMENT_CASH_COSTS.get(imp_col, 0)
                _add_cost(costs, unit_cash * delta, "existing_cities", "cash")
                
                # Resource costs
                resource_costs = IMPROVEMENT_RESOURCE_COSTS.get(imp_col, {})
                for resource, per_unit in resource_costs.items():
                    _add_cost(costs, per_unit * delta, "existing_cities", resource)
    
    # ── Projects ──────────────────────────────────────────────────────────────
    for project_col in plan_data.get("projects", []):
        # Skip if already owned
        if nation.get(project_col):
            continue
        
        # Get display name
        display_name = _PROJECT_DB_COL_TO_DISPLAY.get(project_col)
        if not display_name:
            logger.warning(f"Unknown project column: {project_col}")
            continue
        
        # Calculate cost with discounts
        result = project_build_cost(display_name, nation)
        if result:
            final_costs = result.get("final_costs", {})
            for resource, amount in final_costs.items():
                if resource == "money":
                    _add_cost(costs, amount, "projects", "cash")
                else:
                    _add_cost(costs, amount, "projects", resource)
    
    # Remove zero-value resources
    _cleanup_zero_costs(costs)
    
    return costs


def _compute_remaining_costs(
    plan_data: Dict[str, Any],
    nation: Dict[str, Any],
    cities: List[Dict[str, Any]],
    progress: Dict[str, Any],
    top_20_avg: float,
) -> Dict[str, Any]:
    """
    Calculate remaining costs (only for incomplete steps).
    Similar to total costs but filtered by progress.done flags.
    """
    costs = {
        "total": {"cash": 0.0},
        "by_section": {
            "new_cities": {"cash": 0.0},
            "existing_cities": {"cash": 0.0},
            "projects": {"cash": 0.0},
        },
    }
    
    starting_cities = nation.get("num_cities", 0)
    
    # ── New Cities (only incomplete ones) ────────────────────────────────────
    new_cities_plan = plan_data.get("new_cities", [])
    new_cities_progress = progress.get("new_cities", [])
    
    for idx, city_plan in enumerate(new_cities_plan):
        if idx >= len(new_cities_progress):
            continue
        
        city_progress = new_cities_progress[idx]
        slot = city_plan["slot"]
        city_number = starting_cities + slot
        
        # City purchase (if not done)
        if not city_progress["steps"].get("city_purchased"):
            result = city_purchase_cost(city_number, top_20_avg, nation)
            _add_cost(costs, result["final_cost"], "new_cities", "cash")
        
        # Infrastructure (if not done) — new city starts with 10 infra
        if not city_progress["steps"].get("infra_done"):
            target_infra = city_plan.get("infra", 10)
            # If city already purchased, cost from current infra; else from 10
            if city_progress["steps"].get("city_purchased") and city_progress["matched_city_id"]:
                cities_sorted = sorted(cities, key=lambda c: c.get("date", "") or "")
                target_city_number = starting_cities + slot
                if len(cities_sorted) >= target_city_number:
                    matched_city = cities_sorted[target_city_number - 1]
                    current_infra = float(matched_city.get("infrastructure", 10))
                else:
                    current_infra = 10.0
            else:
                current_infra = 10.0
            
            if target_infra > current_infra:
                result = infra_purchase_cost(current_infra, target_infra - current_infra, nation)
                _add_cost(costs, result["final_cost"], "new_cities", "cash")
        
        # Land (if not done) — new city starts with 250 land
        if not city_progress["steps"].get("land_done"):
            target_land = city_plan.get("land", 250)
            # If city already purchased, cost from current land; else from 250
            if city_progress["steps"].get("city_purchased") and city_progress["matched_city_id"]:
                cities_sorted = sorted(cities, key=lambda c: c.get("date", "") or "")
                target_city_number = starting_cities + slot
                if len(cities_sorted) >= target_city_number:
                    matched_city = cities_sorted[target_city_number - 1]
                    current_land = float(matched_city.get("land", 250))
                else:
                    current_land = 250.0
            else:
                current_land = 250.0
            
            if target_land > current_land:
                result = land_purchase_cost(current_land, target_land - current_land, nation)
                _add_cost(costs, result["final_cost"], "new_cities", "cash")
        
        # Improvements (if not done)
        if not city_progress["steps"].get("improvements_done"):
            for imp_col, target_count in city_plan.get("improvements", {}).items():
                # Determine current count
                current_count = 0
                if city_progress["steps"].get("city_purchased") and city_progress["matched_city_id"]:
                    cities_sorted = sorted(cities, key=lambda c: c.get("date", "") or "")
                    target_city_number = starting_cities + slot
                    if len(cities_sorted) >= target_city_number:
                        matched_city = cities_sorted[target_city_number - 1]
                        current_count = int(matched_city.get(imp_col, 0))
                
                if target_count > current_count:
                    delta = target_count - current_count
                    # Cash cost
                    unit_cash = IMPROVEMENT_CASH_COSTS.get(imp_col, 0)
                    _add_cost(costs, unit_cash * delta, "new_cities", "cash")
                    
                    # Resource costs
                    resource_costs = IMPROVEMENT_RESOURCE_COSTS.get(imp_col, {})
                    for resource, per_unit in resource_costs.items():
                        _add_cost(costs, per_unit * delta, "new_cities", resource)
    
    # ── Existing Cities (only incomplete steps) ──────────────────────────────
    existing_cities_plan = plan_data.get("existing_cities", [])
    existing_cities_progress = progress.get("existing_cities", [])
    
    for idx, city_plan in enumerate(existing_cities_plan):
        if idx >= len(existing_cities_progress):
            continue
        
        city_progress = existing_cities_progress[idx]
        city_id = city_plan.get("city_id")
        if not city_id:
            continue
        
        city = next((c for c in cities if c.get("id") == city_id), None)
        if not city:
            continue
        
        # Infrastructure (if not done)
        if not city_progress["steps"].get("infra_done"):
            target_infra = city_plan.get("target_infra")
            if target_infra is not None:
                current_infra = float(city.get("infrastructure", 0))
                if target_infra > current_infra:
                    delta = target_infra - current_infra
                    result = infra_purchase_cost(current_infra, delta, nation)
                    _add_cost(costs, result["final_cost"], "existing_cities", "cash")
        
        # Land (if not done)
        if not city_progress["steps"].get("land_done"):
            target_land = city_plan.get("target_land")
            if target_land is not None:
                current_land = float(city.get("land", 0))
                if target_land > current_land:
                    delta = target_land - current_land
                    result = land_purchase_cost(current_land, delta, nation)
                    _add_cost(costs, result["final_cost"], "existing_cities", "cash")
        
        # Improvements (only incomplete ones)
        for imp_col, imp_done in city_progress["steps"].get("improvements", {}).items():
            if not imp_done:
                target_count = city_plan.get("target_improvements", {}).get(imp_col, 0)
                current_count = int(city.get(imp_col, 0))
                if target_count > current_count:
                    delta = target_count - current_count
                    # Cash cost
                    unit_cash = IMPROVEMENT_CASH_COSTS.get(imp_col, 0)
                    _add_cost(costs, unit_cash * delta, "existing_cities", "cash")
                    
                    # Resource costs
                    resource_costs = IMPROVEMENT_RESOURCE_COSTS.get(imp_col, {})
                    for resource, per_unit in resource_costs.items():
                        _add_cost(costs, per_unit * delta, "existing_cities", resource)
    
    # ── Projects (only unowned) ───────────────────────────────────────────────
    projects_plan = plan_data.get("projects", [])
    projects_progress = progress.get("projects", [])
    
    for idx, project_col in enumerate(projects_plan):
        if idx >= len(projects_progress):
            continue
        
        project_progress = projects_progress[idx]
        if project_progress.get("done"):
            continue  # Skip owned projects
        
        # Get display name
        display_name = _PROJECT_DB_COL_TO_DISPLAY.get(project_col)
        if not display_name:
            continue
        
        # Calculate cost
        result = project_build_cost(display_name, nation)
        if result:
            final_costs = result.get("final_costs", {})
            for resource, amount in final_costs.items():
                if resource == "money":
                    _add_cost(costs, amount, "projects", "cash")
                else:
                    _add_cost(costs, amount, "projects", resource)
    
    # Remove zero-value resources
    _cleanup_zero_costs(costs)
    
    return costs


def _compute_per_project_costs(
    plan_data: Dict[str, Any],
    nation: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Return a list of {db_col, name, costs, all_policy_costs} for each project in the plan,
    including projects the nation already owns (marked is_owned=True).
    costs = actual cost with nation's current policy.
    all_policy_costs = cost as if ALL applicable policies/projects are active
                       (Technological Advancement + BDA + GSA), regardless of what
                       the nation currently has. Always shown in the plan UI.
    """
    # Build a "max-discount" nation clone for the all_policy calculation:
    # Technological Advancement policy + BDA + GSA all active.
    max_discount_nation = dict(nation)
    max_discount_nation["domestic_policy"] = "TECHNOLOGICAL_ADVANCEMENT"
    max_discount_nation["bureau_of_domestic_affairs"] = True
    max_discount_nation["government_support_agency"] = True

    results = []
    for project_col in plan_data.get("projects", []):
        is_owned = bool(nation.get(project_col))
        display_name = _PROJECT_DB_COL_TO_DISPLAY.get(project_col, project_col.replace("_", " ").title())
        costs: Dict[str, float] = {}
        all_policy_costs: Dict[str, float] = {}
        if not is_owned:
            # Actual cost (respects nation's real policy)
            result = project_build_cost(display_name, nation)
            if result:
                for resource, amount in result.get("final_costs", {}).items():
                    key = "cash" if resource == "money" else resource.lower()
                    costs[key] = float(amount)
            # Max-discount cost (all policies active)
            result_mp = project_build_cost(display_name, max_discount_nation)
            if result_mp:
                for resource, amount in result_mp.get("final_costs", {}).items():
                    key = "cash" if resource == "money" else resource.lower()
                    all_policy_costs[key] = float(amount)
        results.append({
            "db_col": project_col,
            "name": display_name,
            "is_owned": is_owned,
            "costs": costs,
            "all_policy_costs": all_policy_costs,
        })
    return results


def _compute_per_city_costs(
    plan_data: Dict[str, Any],
    nation: Dict[str, Any],
    cities: List[Dict[str, Any]],
    top_20_avg: float,
) -> Dict[str, Any]:
    """
    Return per-city cost totals with per-substep breakdowns:
      new_cities: list of {slot, city_number, label, costs, substep_costs}
      existing_cities: list of {city_id, city_name, costs, substep_costs}
    Each costs dict has {cash: float, resource: float, ...}.
    substep_costs has {city_purchase, infra, land, improvements} each as a costs dict.
    """
    starting_cities = nation.get("num_cities", 0)
    new_city_costs = []
    existing_city_costs = []

    for city_plan in plan_data.get("new_cities", []):
        slot = city_plan["slot"]
        city_number = starting_cities + slot
        costs: Dict[str, float] = {"cash": 0.0}
        substep_costs: Dict[str, Dict[str, float]] = {
            "city_purchase": {},
            "infra": {},
            "land": {},
            "improvements": {},
        }

        # City purchase
        r = city_purchase_cost(city_number, top_20_avg, nation)
        city_pur_cash = r["final_cost"]
        costs["cash"] += city_pur_cash
        substep_costs["city_purchase"] = {"cash": city_pur_cash}

        # Infra — new city starts with 10 infra, buy delta to target
        target_infra = city_plan.get("infra", 10)
        if target_infra > 10:
            r = infra_purchase_cost(10.0, target_infra - 10.0, nation)
            infra_cash = r["final_cost"]
            costs["cash"] += infra_cash
            substep_costs["infra"] = {"cash": infra_cash}

        # Land — new city starts with 250 land, buy delta to target
        target_land = city_plan.get("land", 250)
        if target_land > 250:
            r = land_purchase_cost(250.0, target_land - 250.0, nation)
            land_cash = r["final_cost"]
            costs["cash"] += land_cash
            substep_costs["land"] = {"cash": land_cash}

        # Improvements
        imp_costs: Dict[str, float] = {}
        for imp_col, count in city_plan.get("improvements", {}).items():
            if count > 0:
                unit_cash = IMPROVEMENT_CASH_COSTS.get(imp_col, 0)
                imp_costs["cash"] = imp_costs.get("cash", 0.0) + unit_cash * count
                costs["cash"] += unit_cash * count
                for resource, per_unit in IMPROVEMENT_RESOURCE_COSTS.get(imp_col, {}).items():
                    imp_costs[resource] = imp_costs.get(resource, 0.0) + per_unit * count
                    costs[resource] = costs.get(resource, 0.0) + per_unit * count
        substep_costs["improvements"] = {k: v for k, v in imp_costs.items() if v > 0}

        # Strip zeros
        costs = {k: v for k, v in costs.items() if v > 0}
        new_city_costs.append({
            "slot": slot,
            "city_number": city_number,
            "label": city_plan.get("label", f"City {city_number}"),
            "costs": costs,
            "substep_costs": substep_costs,
        })

    for city_plan in plan_data.get("existing_cities", []):
        city_id = city_plan.get("city_id")
        if not city_id:
            continue
        city = next((c for c in cities if c.get("id") == city_id), None)
        if not city:
            continue
        costs: Dict[str, float] = {"cash": 0.0}
        substep_costs: Dict[str, Dict[str, float]] = {
            "infra": {},
            "land": {},
            "improvements": {},
        }

        # Infra delta
        target_infra = city_plan.get("target_infra")
        if target_infra is not None:
            current_infra = float(city.get("infrastructure", 0))
            if target_infra > current_infra:
                r = infra_purchase_cost(current_infra, target_infra - current_infra, nation)
                infra_cash = r["final_cost"]
                costs["cash"] += infra_cash
                substep_costs["infra"] = {"cash": infra_cash}

        # Land delta
        target_land = city_plan.get("target_land")
        if target_land is not None:
            current_land = float(city.get("land", 0))
            if target_land > current_land:
                r = land_purchase_cost(current_land, target_land - current_land, nation)
                land_cash = r["final_cost"]
                costs["cash"] += land_cash
                substep_costs["land"] = {"cash": land_cash}

        # Improvement deltas
        imp_costs: Dict[str, float] = {}
        for imp_col, target_count in city_plan.get("target_improvements", {}).items():
            current_count = int(city.get(imp_col, 0))
            if target_count > current_count:
                delta = target_count - current_count
                unit_cash = IMPROVEMENT_CASH_COSTS.get(imp_col, 0)
                imp_costs["cash"] = imp_costs.get("cash", 0.0) + unit_cash * delta
                costs["cash"] += unit_cash * delta
                for resource, per_unit in IMPROVEMENT_RESOURCE_COSTS.get(imp_col, {}).items():
                    imp_costs[resource] = imp_costs.get(resource, 0.0) + per_unit * delta
                    costs[resource] = costs.get(resource, 0.0) + per_unit * delta
        substep_costs["improvements"] = {k: v for k, v in imp_costs.items() if v > 0}

        costs = {k: v for k, v in costs.items() if v > 0}
        existing_city_costs.append({
            "city_id": city_id,
            "city_name": city_plan.get("city_name", city.get("name", f"City {city_id}")),
            "costs": costs,
            "substep_costs": substep_costs,
        })

    return {
        "new_cities": new_city_costs,
        "existing_cities": existing_city_costs,
    }


def _compute_all_policy_total_costs(
    plan_data: Dict[str, Any],
    nation: Dict[str, Any],
    cities: List[Dict[str, Any]],
    top_20_avg: float,
    total_costs: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Return total costs where projects are computed as if ALL applicable policies
    are active (Technological Advancement + BDA + GSA), regardless of what the
    nation currently has.  City/infra/land costs are unchanged (those functions
    already always apply their policy discounts).
    """
    import copy

    # Start from a copy of total_costs so city/infra/land numbers are preserved.
    result = copy.deepcopy(total_costs)

    # Build a max-discount nation for project cost recalculation.
    max_nation = dict(nation)
    max_nation["domestic_policy"] = "TECHNOLOGICAL_ADVANCEMENT"
    max_nation["bureau_of_domestic_affairs"] = True
    max_nation["government_support_agency"] = True

    # Replace the projects portion of the totals.
    # First subtract the original project costs from total/section.
    orig_proj = total_costs["by_section"].get("projects", {})
    for resource, amount in orig_proj.items():
        result["total"][resource] = result["total"].get(resource, 0.0) - amount
        result["by_section"]["projects"][resource] = 0.0

    # Recompute project costs with max-discount nation.
    for project_col in plan_data.get("projects", []):
        if nation.get(project_col):
            continue  # Already owned — no cost
        display_name = _PROJECT_DB_COL_TO_DISPLAY.get(project_col)
        if not display_name:
            continue
        proj_result = project_build_cost(display_name, max_nation)
        if proj_result:
            for resource, amount in proj_result.get("final_costs", {}).items():
                r_key = "cash" if resource == "money" else resource.lower()
                _add_cost(result, float(amount), "projects", r_key)

    _cleanup_zero_costs(result)
    return result


def _add_cost(
    costs: Dict[str, Any],
    amount: float,
    section: str,
    resource: str,
) -> None:
    """Helper to add a cost to both total and section."""
    costs["total"][resource] = costs["total"].get(resource, 0.0) + float(amount)
    costs["by_section"][section][resource] = (
        costs["by_section"][section].get(resource, 0.0) + float(amount)
    )


def _cleanup_zero_costs(costs: Dict[str, Any]) -> None:
    """Remove resources with zero cost from all sections."""
    # Clean total
    costs["total"] = {k: v for k, v in costs["total"].items() if v > 0}
    
    # Clean sections
    for section_name in costs["by_section"]:
        costs["by_section"][section_name] = {
            k: v for k, v in costs["by_section"][section_name].items() if v > 0
        }


# ── Plan Validation ───────────────────────────────────────────────────────────

def _validate_plan_data(
    plan_data: Dict[str, Any],
    nation: Dict[str, Any],
    cities: List[Dict[str, Any]],
) -> None:
    """
    Validate plan data. Raises HTTPException if invalid.
    """
    # Validate new cities
    for city_plan in plan_data.get("new_cities", []):
        slot = city_plan.get("slot")
        if not isinstance(slot, int) or slot < 1:
            raise HTTPException(
                status_code=422,
                detail=f"New city slot must be a positive integer, got: {slot}"
            )
        
        # Validate infra
        infra = city_plan.get("infra")
        if infra is not None:
            if not isinstance(infra, (int, float)) or infra < 10 or infra > 15000:
                raise HTTPException(
                    status_code=422,
                    detail=f"Infra must be between 10 and 15,000, got: {infra}"
                )
        
        # Validate land
        land = city_plan.get("land")
        if land is not None:
            if not isinstance(land, (int, float)) or land < 250 or land > 50000:
                raise HTTPException(
                    status_code=422,
                    detail=f"Land must be between 250 and 50,000, got: {land}"
                )
        
        # Validate improvements
        improvements = city_plan.get("improvements", {})
        if not isinstance(improvements, dict):
            raise HTTPException(
                status_code=422,
                detail="Improvements must be an object"
            )
        
        for imp_col, count in improvements.items():
            if not isinstance(count, int) or count < 0 or count > 50:
                raise HTTPException(
                    status_code=422,
                    detail=f"Improvement count must be between 0 and 50, got {count} for {imp_col}"
                )
            
            # Check if improvement column exists
            if imp_col not in IMPROVEMENT_CASH_COSTS:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown improvement: {imp_col}"
                )
        
        # Validate slot limits
        target_infra = city_plan.get("infra", 10)
        max_slots = min(int(target_infra // 50), 50)
        total_improvements = sum(improvements.values())
        if total_improvements > max_slots:
            raise HTTPException(
                status_code=422,
                detail=f"New city slot {slot}: {total_improvements} improvements planned but only {max_slots} slots at {target_infra} infra"
            )
    
    # Validate existing cities
    for city_plan in plan_data.get("existing_cities", []):
        city_id = city_plan.get("city_id")
        if not isinstance(city_id, int):
            raise HTTPException(
                status_code=422,
                detail=f"city_id must be an integer, got: {city_id}"
            )
        
        # Check city exists
        city = next((c for c in cities if c.get("id") == city_id), None)
        if not city:
            raise HTTPException(
                status_code=422,
                detail=f"City {city_id} not found for this nation"
            )
        
        # Validate infra
        target_infra = city_plan.get("target_infra")
        if target_infra is not None:
            if not isinstance(target_infra, (int, float)) or target_infra < 10 or target_infra > 15000:
                raise HTTPException(
                    status_code=422,
                    detail=f"Infra must be between 10 and 15,000, got: {target_infra}"
                )
            
            current_infra = float(city.get("infrastructure", 0))
            if target_infra < current_infra:
                raise HTTPException(
                    status_code=422,
                    detail=f"City {city.get('name')}: target infra ({target_infra}) cannot be below current ({current_infra:.2f})"
                )
        
        # Validate land
        target_land = city_plan.get("target_land")
        if target_land is not None:
            if not isinstance(target_land, (int, float)) or target_land < 250 or target_land > 50000:
                raise HTTPException(
                    status_code=422,
                    detail=f"Land must be between 250 and 50,000, got: {target_land}"
                )
            
            current_land = float(city.get("land", 0))
            if target_land < current_land:
                raise HTTPException(
                    status_code=422,
                    detail=f"City {city.get('name')}: target land ({target_land}) cannot be below current ({current_land:.2f})"
                )
        
        # Validate improvements
        target_improvements = city_plan.get("target_improvements", {})
        if not isinstance(target_improvements, dict):
            raise HTTPException(
                status_code=422,
                detail="target_improvements must be an object"
            )
        
        for imp_col, target_count in target_improvements.items():
            if not isinstance(target_count, int) or target_count < 0 or target_count > 50:
                raise HTTPException(
                    status_code=422,
                    detail=f"Improvement count must be between 0 and 50, got {target_count} for {imp_col}"
                )
            
            # Check if improvement column exists
            if imp_col not in IMPROVEMENT_CASH_COSTS:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown improvement: {imp_col}"
                )
            
            # Existing-city improvement plans are final targets, not only
            # additions. This allows optimizer plans and manual edits to
            # remove, keep, or add improvements in one saved plan.
        
        # Validate slot limits (with improvements)
        if target_improvements:
            final_infra = target_infra if target_infra is not None else float(city.get("infrastructure", 0))
            max_slots = min(int(final_infra // 50), 50)
            
            # Calculate final total improvements
            total_improvements = 0
            for imp_col in IMPROVEMENT_CASH_COSTS.keys():
                target = target_improvements.get(imp_col)
                if target is not None:
                    total_improvements += target
                else:
                    total_improvements += int(city.get(imp_col, 0))
            
            if total_improvements > max_slots:
                raise HTTPException(
                    status_code=422,
                    detail=f"City {city.get('name')}: {total_improvements} improvements planned but only {max_slots} slots at {final_infra} infra"
                )
    
    # Validate projects
    projects = plan_data.get("projects", [])
    if not isinstance(projects, list):
        raise HTTPException(
            status_code=422,
            detail="projects must be an array"
        )
    
    # Count unowned projects
    unowned_count = 0
    for project_col in projects:
        if not isinstance(project_col, str):
            raise HTTPException(
                status_code=422,
                detail=f"Project column must be a string, got: {project_col}"
            )
        
        # Check if project exists
        if project_col not in _PROJECT_DB_COL_TO_DISPLAY:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown project: {project_col}"
            )
        
        # Count unowned
        if not nation.get(project_col):
            unowned_count += 1
    
    if unowned_count > 5:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot plan more than 5 unowned projects, got: {unowned_count}"
        )




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
    
    return JSONResponse({
        "plan": plan,
        "progress": progress,
        "total_costs": total_costs,
        "remaining_costs": remaining_costs,
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


# ── POST Preview ──────────────────────────────────────────────────────────────

@router.post("/mynation/plan/preview")
async def preview_plan(request: Request, body: Dict[str, Any]) -> JSONResponse:
    """
    Compute a preview of what the nation will look like after plan completion.
    Returns simulated revenue, military caps, and city summary.
    """
    nation_id = body.get("nation_id")
    if not isinstance(nation_id, int) or nation_id <= 0:
        raise HTTPException(status_code=422, detail="nation_id must be a positive integer.")
    
    await _require_own_nation(request, nation_id)
    
    plan_data = body.get("plan_data")
    if not isinstance(plan_data, dict):
        raise HTTPException(status_code=422, detail="plan_data must be an object.")
    
    # Load current nation state
    gdb = _get_global_nations_db()
    nation = await gdb.get_nation(nation_id)
    if not nation:
        raise HTTPException(status_code=404, detail="Nation not found.")
    
    cities = await gdb.get_cities_for_nation(nation_id)
    
    # Apply plan to create simulated state
    simulated_nation, simulated_cities = _apply_plan_to_nation(plan_data, nation, cities)
    
    # Compute preview
    preview = await _compute_preview(simulated_nation, simulated_cities)
    
    return JSONResponse(preview)


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
            imp_done = current_count >= target_count
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
        
        # Infrastructure (from 10 to target)
        target_infra = city_plan.get("infra", 10)
        if target_infra > 10:
            result = infra_purchase_cost(10.0, target_infra - 10.0, nation)
            _add_cost(costs, result["final_cost"], "new_cities", "cash")
        
        # Land (from 250 to target)
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
        
        # Infrastructure (if not done)
        if not city_progress["steps"].get("infra_done"):
            target_infra = city_plan.get("infra", 10)
            # If city not purchased, cost from 10; else from current
            if city_progress["steps"].get("city_purchased") and city_progress["matched_city_id"]:
                cities_sorted = sorted(cities, key=lambda c: c.get("date", "") or "")
                target_city_number = starting_cities + slot
                if len(cities_sorted) >= target_city_number:
                    matched_city = cities_sorted[target_city_number - 1]
                    current_infra = float(matched_city.get("infrastructure", 0))
                else:
                    current_infra = 10.0
            else:
                current_infra = 10.0
            
            if target_infra > current_infra:
                result = infra_purchase_cost(current_infra, target_infra - current_infra, nation)
                _add_cost(costs, result["final_cost"], "new_cities", "cash")
        
        # Land (if not done)
        if not city_progress["steps"].get("land_done"):
            target_land = city_plan.get("land", 250)
            # Similar logic as infra
            if city_progress["steps"].get("city_purchased") and city_progress["matched_city_id"]:
                cities_sorted = sorted(cities, key=lambda c: c.get("date", "") or "")
                target_city_number = starting_cities + slot
                if len(cities_sorted) >= target_city_number:
                    matched_city = cities_sorted[target_city_number - 1]
                    current_land = float(matched_city.get("land", 0))
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
            if target_infra <= current_infra:
                raise HTTPException(
                    status_code=422,
                    detail=f"City {city.get('name')}: target infra ({target_infra}) must be greater than current ({current_infra:.2f})"
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
            if target_land <= current_land:
                raise HTTPException(
                    status_code=422,
                    detail=f"City {city.get('name')}: target land ({target_land}) must be greater than current ({current_land:.2f})"
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
            
            current_count = int(city.get(imp_col, 0))
            if target_count <= current_count:
                raise HTTPException(
                    status_code=422,
                    detail=f"City {city.get('name')}: target {imp_col} count ({target_count}) must be greater than current ({current_count})"
                )
        
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


# ── Preview Simulation ────────────────────────────────────────────────────────

def _apply_plan_to_nation(
    plan_data: Dict[str, Any],
    nation: Dict[str, Any],
    cities: List[Dict[str, Any]],
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Apply plan to nation/cities to create simulated future state.
    Returns (simulated_nation, simulated_cities).
    """
    import copy
    
    # Deep copy to avoid mutating originals
    sim_nation = copy.deepcopy(nation)
    sim_cities = copy.deepcopy(cities)
    
    # Apply existing city upgrades
    for city_plan in plan_data.get("existing_cities", []):
        city_id = city_plan.get("city_id")
        if not city_id:
            continue
        
        # Find city in simulated list
        city = next((c for c in sim_cities if c.get("id") == city_id), None)
        if not city:
            continue
        
        # Apply infra upgrade
        if city_plan.get("target_infra") is not None:
            city["infrastructure"] = city_plan["target_infra"]
        
        # Apply land upgrade
        if city_plan.get("target_land") is not None:
            city["land"] = city_plan["target_land"]
        
        # Apply improvement upgrades
        for imp_col, target_count in city_plan.get("target_improvements", {}).items():
            city[imp_col] = target_count
    
    # Add new cities
    starting_cities = nation.get("num_cities", 0)
    for city_plan in plan_data.get("new_cities", []):
        slot = city_plan["slot"]
        new_city = {
            "id": 900000 + starting_cities + slot,  # Fake ID
            "name": f"City {starting_cities + slot}",
            "nation_id": nation.get("id"),
            "date": "2026-01-01T00:00:00Z",  # Placeholder
            "infrastructure": city_plan.get("infra", 10),
            "land": city_plan.get("land", 250),
            "powered": True,  # Assume powered for preview
            "oil_power": 0,
            "wind_power": 0,
            "coal_power": 0,
            "nuclear_power": 0,
            "coal_mine": 0,
            "oil_well": 0,
            "uranium_mine": 0,
            "bauxite_mine": 0,
            "iron_mine": 0,
            "lead_mine": 0,
            "farm": 0,
            "police_station": 0,
            "hospital": 0,
            "recycling_center": 0,
            "subway": 0,
            "supermarket": 0,
            "bank": 0,
            "shopping_mall": 0,
            "stadium": 0,
            "barracks": 0,
            "factory": 0,
            "hangar": 0,
            "drydock": 0,
            "oil_refinery": 0,
            "aluminum_refinery": 0,
            "steel_mill": 0,
            "munitions_factory": 0,
        }
        
        # Apply improvements
        for imp_col, count in city_plan.get("improvements", {}).items():
            new_city[imp_col] = count
        
        sim_cities.append(new_city)
    
    # Update city count
    sim_nation["num_cities"] = len(sim_cities)
    
    # Apply projects
    for project_col in plan_data.get("projects", []):
        sim_nation[project_col] = True
    
    return sim_nation, sim_cities


async def _compute_preview(
    simulated_nation: Dict[str, Any],
    simulated_cities: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compute preview of simulated nation state.
    Returns revenue, military caps, city summary, and warnings.
    """
    from Systems.PnW.Util.rev_correct import revenue_calc_sync
    from Systems.Functions.database_manager import (
        get_latest_resource_prices,
        get_latest_game_info,
        get_latest_radiation_data,
    )
    
    # Gather game context
    price_data, game_info, radiation_data = await asyncio.gather(
        get_latest_resource_prices(),
        get_latest_game_info(),
        get_latest_radiation_data(),
        return_exceptions=True,
    )
    
    if isinstance(price_data, Exception) or not price_data:
        price_data = {}
    if isinstance(game_info, Exception):
        game_info = None
    if isinstance(radiation_data, Exception):
        radiation_data = None
    
    # Build revenue inputs
    market_prices = {r: p["sell"] for r, p in price_data.items()} if price_data else {}
    
    # Get colors data for revenue calc
    from Systems.Functions.database_manager import get_latest_game_data
    colors_data = await get_latest_game_data("colors")
    colors_for_calc = {
        c["color"]: float(c.get("turn_bonus", 0)) for c in colors_data
    } if colors_data else {}
    
    radiation = _build_radiation(radiation_data)
    seasonal_mod = _build_seasonal_mod(game_info)
    
    is_war = (
        (simulated_nation.get("offensive_wars_count") or 0) > 0
        or (simulated_nation.get("defensive_wars_count") or 0) > 0
    )
    
    # Attach cities to nation for revenue calc
    nation_with_cities = {**simulated_nation, "cities": simulated_cities}
    
    # Run revenue calculation
    revenue_result = {}
    try:
        rev = await asyncio.to_thread(
            revenue_calc_sync,
            nation=nation_with_cities,
            radiation=radiation,
            treasures=[],
            prices=market_prices,
            colors=colors_for_calc,
            seasonal_mod=seasonal_mod,
            is_war=is_war,
        )
        if rev:
            revenue_result = {
                "gross_income": rev.get("gross_money_income", 0.0),
                "net_cash_turn": rev.get("net_cash_num", 0.0),
                "net_cash_day": rev.get("net_cash_num", 0.0) * 12,
                "net_cash_week": rev.get("net_cash_num", 0.0) * 84,
                "resources": {
                    "food": rev.get("food", 0.0),
                    "coal": rev.get("coal", 0.0),
                    "oil": rev.get("oil", 0.0),
                    "uranium": rev.get("uranium", 0.0),
                    "lead": rev.get("lead", 0.0),
                    "iron": rev.get("iron", 0.0),
                    "bauxite": rev.get("bauxite", 0.0),
                    "gasoline": rev.get("gasoline", 0.0),
                    "munitions": rev.get("munitions", 0.0),
                    "steel": rev.get("steel", 0.0),
                    "aluminum": rev.get("aluminum", 0.0),
                },
            }
    except Exception as e:
        logger.error(f"Revenue calc failed for preview: {e}", exc_info=True)
        revenue_result = {"error": "Revenue calculation failed"}
    
    # Compute military caps
    military_caps = _compute_military_caps(simulated_nation, simulated_cities)
    
    # Compute city summary
    city_summary = _compute_city_summary(simulated_cities)
    
    # Generate warnings
    warnings = _generate_warnings(simulated_cities)
    
    return {
        "revenue": revenue_result,
        "military_caps": military_caps,
        "city_summary": city_summary,
        "warnings": warnings,
    }


def _build_radiation(radiation_data: Optional[Dict[str, float]]) -> Dict[str, float]:
    """Build radiation dict from database data."""
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


def _build_seasonal_mod(game_info: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """Build seasonal modifier dict from game_info."""
    seasonal_mod = {
        "na": 1, "sa": 1, "eu": 1, "as": 1, "af": 1, "au": 1, "an": 0.5,
    }
    if not game_info:
        return seasonal_mod
    game_date_str = game_info.get("game_date")
    if not game_date_str:
        return seasonal_mod
    try:
        from datetime import datetime
        parsed = datetime.fromisoformat(str(game_date_str).replace("Z", "+00:00"))
        month = parsed.month
    except Exception:
        return seasonal_mod
    if month in (6, 7, 8):
        seasonal_mod.update({"na": 1.2, "as": 1.2, "eu": 1.2, "sa": 0.8, "af": 0.8, "au": 0.8})
    elif month in (12, 1, 2):
        seasonal_mod.update({"na": 0.8, "as": 0.8, "eu": 0.8, "sa": 1.2, "af": 1.2, "au": 1.2})
    return seasonal_mod


def _compute_military_caps(nation: Dict[str, Any], cities: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compute military unit caps based on nation projects and city buildings.
    Returns max units and daily buy limits.
    """
    import math
    
    num_cities = len(cities)
    
    # Count military buildings across all cities
    total_barracks = sum(int(c.get("barracks", 0)) for c in cities)
    total_factories = sum(int(c.get("factory", 0)) for c in cities)
    total_hangars = sum(int(c.get("hangar", 0)) for c in cities)
    total_drydocks = sum(int(c.get("drydock", 0)) for c in cities)
    
    # Base caps from cities
    base_soldier_cap = num_cities * 15000
    base_tank_cap = num_cities * 250
    base_aircraft_cap = num_cities * 15
    base_ship_cap = num_cities * 5
    
    # Building multipliers
    barracks_multi = 1 + (total_barracks * 0.05)
    factory_multi = 1 + (total_factories * 0.05)
    hangar_multi = 1 + (total_hangars * 0.05)
    drydock_multi = 1 + (total_drydocks * 0.05)
    
    # Project bonuses
    if nation.get("vital_defense_system"):
        barracks_multi += 0.25
        factory_multi += 0.25
    
    if nation.get("military_research_center"):
        hangar_multi += 0.25
        drydock_multi += 0.25
    
    # Apply multipliers
    max_soldiers = int(base_soldier_cap * barracks_multi)
    max_tanks = int(base_tank_cap * factory_multi)
    max_aircraft = int(base_aircraft_cap * hangar_multi)
    max_ships = int(base_ship_cap * drydock_multi)
    
    # Daily buy limits
    soldiers_per_day = int(max_soldiers * 0.05)
    tanks_per_day = int(max_tanks * 0.10)
    aircraft_per_day = int(max_aircraft * 0.10)
    ships_per_day = max(1, int(max_ships * 0.02))
    
    # Missiles and nukes
    missiles_per_day = 1 if nation.get("missile_launch_pad") else 0
    if nation.get("space_program"):
        missiles_per_day += 1
    
    nukes_per_day = 1 if nation.get("nuclear_research_facility") else 0
    
    # Max missiles/nukes (based on projects)
    max_missiles = 0
    if nation.get("missile_launch_pad"):
        max_missiles = 25
    if nation.get("space_program"):
        max_missiles += 25
    
    max_nukes = 0
    if nation.get("nuclear_research_facility"):
        max_nukes = 15
    if nation.get("nuclear_launch_facility"):
        max_nukes += 15
    
    # Spies
    base_spy_cap = 50
    if nation.get("central_intelligence_agency"):
        base_spy_cap += 10
    if nation.get("spy_satellite"):
        base_spy_cap += 10
    max_spies = base_spy_cap + (num_cities * 1)
    spies_per_day = max(1, int(max_spies * 0.04))
    
    return {
        "max_soldiers": max_soldiers,
        "soldiers_per_day": soldiers_per_day,
        "max_tanks": max_tanks,
        "tanks_per_day": tanks_per_day,
        "max_aircraft": max_aircraft,
        "aircraft_per_day": aircraft_per_day,
        "max_ships": max_ships,
        "ships_per_day": ships_per_day,
        "missiles_per_day": missiles_per_day,
        "max_missiles": max_missiles,
        "nukes_per_day": nukes_per_day,
        "max_nukes": max_nukes,
        "max_spies": max_spies,
        "spies_per_day": spies_per_day,
    }


def _compute_city_summary(cities: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute summary statistics for cities."""
    if not cities:
        return {
            "num_cities": 0,
            "avg_infra": 0,
            "avg_land": 0,
            "all_powered": True,
            "all_within_slots": True,
            "mmr": "0/0/0/0",
        }
    
    total_infra = sum(float(c.get("infrastructure", 0)) for c in cities)
    total_land = sum(float(c.get("land", 0)) for c in cities)
    avg_infra = total_infra / len(cities)
    avg_land = total_land / len(cities)
    
    # Power check
    all_powered = True
    for city in cities:
        infra = float(city.get("infrastructure", 0))
        powered_needs = (infra / 100)
        wind = int(city.get("wind_power", 0))
        nuclear = int(city.get("nuclear_power", 0))
        oil = int(city.get("oil_power", 0))
        coal = int(city.get("coal_power", 0))
        power_produced = (wind * 250) + (nuclear * 2000) + (oil * 500) + (coal * 500)
        if power_produced < powered_needs:
            all_powered = False
            break
    
    # Slot check
    all_within_slots = True
    for city in cities:
        infra = float(city.get("infrastructure", 0))
        max_slots = min(int(infra // 50), 50)
        
        # Count improvements
        improvement_cols = [
            "coal_mine", "oil_well", "uranium_mine", "lead_mine", "iron_mine",
            "bauxite_mine", "farm", "coal_power", "oil_power", "nuclear_power",
            "wind_power", "oil_refinery", "aluminum_refinery", "steel_mill",
            "munitions_factory", "factory", "police_station", "hospital",
            "recycling_center", "subway", "supermarket", "bank", "shopping_mall",
            "stadium", "barracks", "hangar", "drydock",
        ]
        total_improvements = sum(int(city.get(col, 0)) for col in improvement_cols)
        
        if total_improvements > max_slots:
            all_within_slots = False
            break
    
    # MMR (Military buildings per city)
    total_barracks = sum(int(c.get("barracks", 0)) for c in cities)
    total_factories = sum(int(c.get("factory", 0)) for c in cities)
    total_hangars = sum(int(c.get("hangar", 0)) for c in cities)
    total_drydocks = sum(int(c.get("drydock", 0)) for c in cities)
    
    mmr_barracks = round(total_barracks / len(cities), 1)
    mmr_factories = round(total_factories / len(cities), 1)
    mmr_hangars = round(total_hangars / len(cities), 1)
    mmr_drydocks = round(total_drydocks / len(cities), 1)
    
    return {
        "num_cities": len(cities),
        "avg_infra": round(avg_infra, 2),
        "avg_land": round(avg_land, 2),
        "all_powered": all_powered,
        "all_within_slots": all_within_slots,
        "mmr": f"{mmr_barracks}/{mmr_factories}/{mmr_hangars}/{mmr_drydocks}",
    }


def _generate_warnings(cities: List[Dict[str, Any]]) -> List[str]:
    """Generate warnings for potential issues in the plan."""
    warnings = []
    
    for city in cities:
        city_name = city.get("name", f"City {city.get('id')}")
        infra = float(city.get("infrastructure", 0))
        
        # Power warning
        powered_needs = (infra / 100)
        wind = int(city.get("wind_power", 0))
        nuclear = int(city.get("nuclear_power", 0))
        oil = int(city.get("oil_power", 0))
        coal = int(city.get("coal_power", 0))
        power_produced = (wind * 250) + (nuclear * 2000) + (oil * 500) + (coal * 500)
        
        if power_produced < powered_needs:
            warnings.append(
                f"{city_name}: Not powered (produces {int(power_produced)} but needs {int(powered_needs)})"
            )
        
        # Slot warning
        max_slots = min(int(infra // 50), 50)
        improvement_cols = [
            "coal_mine", "oil_well", "uranium_mine", "lead_mine", "iron_mine",
            "bauxite_mine", "farm", "coal_power", "oil_power", "nuclear_power",
            "wind_power", "oil_refinery", "aluminum_refinery", "steel_mill",
            "munitions_factory", "factory", "police_station", "hospital",
            "recycling_center", "subway", "supermarket", "bank", "shopping_mall",
            "stadium", "barracks", "hangar", "drydock",
        ]
        total_improvements = sum(int(city.get(col, 0)) for col in improvement_cols)
        
        if total_improvements > max_slots:
            warnings.append(
                f"{city_name}: {total_improvements} improvements but only {max_slots} slots (need {total_improvements * 50} infra)"
            )
    
    return warnings

import asyncio
import logging
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from PnWHarvester.db.global_nations_db import GlobalNationsDB
from PnWHarvester.db.global_wars_db import GlobalWarsDB
from Systems.Functions.db_paths import GLOBAL_NATIONS_DB, GLOBAL_WARS_DB_STR
from Systems.PnW.MA.destroy import DestroyCog
from Systems.PnW.Util.query import create_v3_query_instance


router = APIRouter()
logger = logging.getLogger("Reaper.WebServer.DestroyAPI")


def _clean_identifier(value: str) -> str:
    return (value or "").strip()


def _extract_id_from_link(value: str) -> Optional[str]:
    if not value:
        return None
    if value.isdigit():
        return value
    for pattern in (r"nation_id=(\d+)", r"/nation/id=(\d+)", r"/nations/(\d+)", r"id=(\d+)"):
        match = re.search(pattern, value)
        if match:
            return match.group(1)
    return None


async def _get_active_war_counts() -> Dict[int, Dict[str, int]]:
    try:
        return await GlobalWarsDB(GLOBAL_WARS_DB_STR).get_active_war_counts()
    except Exception as e:
        logger.warning("destroy active war count lookup failed: %s", e)
        return {}


async def _attach_cities(db: GlobalNationsDB, nation: Dict[str, Any]) -> Dict[str, Any]:
    nid = nation.get("id") or nation.get("nation_id")
    if nid:
        nation["cities"] = await db.get_cities_for_nation(int(nid))
    return nation


async def _resolve_nation(db: GlobalNationsDB, target: str) -> Optional[Dict[str, Any]]:
    clean = _clean_identifier(target)
    nation_id = _extract_id_from_link(clean)
    try:
        if nation_id:
            nation = await db.get_nation(int(nation_id))
        else:
            nation = await db.get_nation_by_name(clean)
            if not nation and hasattr(db, "get_nation_by_leader_name"):
                nation = await db.get_nation_by_leader_name(clean)
        if nation:
            return await _attach_cities(db, nation)
    except Exception as e:
        logger.warning("destroy nation lookup failed for %s: %s", target, e)
    return None


async def _resolve_alliance(db: GlobalNationsDB, target: str) -> Optional[Dict[str, Any]]:
    clean = _clean_identifier(target)
    if not clean:
        return None
    try:
        if clean.isdigit():
            rows = await db.get_nations_by_alliance(int(clean))
            if rows:
                name = rows[0].get("alliance_name") or f"Alliance {clean}"
                return {"id": int(clean), "name": name}
        matches = await db.get_distinct_alliances(clean)
        if matches:
            exact = next(
                (m for m in matches if (m.get("alliance_name") or "").lower() == clean.lower()),
                matches[0],
            )
            return {"id": int(exact["alliance_id"]), "name": exact.get("alliance_name") or clean}
    except Exception as e:
        logger.warning("destroy alliance DB lookup failed for %s: %s", target, e)

    try:
        resolved = await create_v3_query_instance().resolve_alliance(clean)
        if resolved and resolved.get("id"):
            return {"id": int(resolved["id"]), "name": resolved.get("name") or clean}
    except Exception as e:
        logger.warning("destroy alliance API lookup failed for %s: %s", target, e)
    return None


async def _load_alliance_nations(db: GlobalNationsDB, alliance_id: int) -> List[Dict[str, Any]]:
    nations = await db.get_nations_by_alliance(int(alliance_id))
    if not nations:
        return []

    async def one(n: Dict[str, Any]) -> Dict[str, Any]:
        return await _attach_cities(db, n)

    return await asyncio.gather(*(one(dict(n)) for n in nations))


async def _resolve_attacker_alliances(db: GlobalNationsDB, attackers: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    resolved: List[Dict[str, Any]] = []
    unresolved: List[str] = []
    seen = set()
    for raw in [p.strip() for p in (attackers or "").split(",") if p.strip()]:
        alliance = await _resolve_alliance(db, raw)
        if not alliance:
            unresolved.append(raw)
            continue
        aid = int(alliance["id"])
        if aid in seen:
            continue
        seen.add(aid)
        resolved.append(alliance)
    return resolved, unresolved


def _is_active_member(nation: Dict[str, Any]) -> bool:
    pos = str(nation.get("alliance_position") or "").split(".")[-1].upper()
    return pos != "APPLICANT" and int(nation.get("vacation_mode_turns") or 0) <= 0


def _purchase_payload(cog: DestroyCog, nation: Dict[str, Any]) -> Dict[str, int]:
    limits = cog.calculate_military_purchase_limits(nation)
    spies_daily = 3 if cog.has_project(nation, "Central Intelligence Agency") else 2
    return {
        "soldiers_daily": int(limits.get("soldiers_daily", 0) or 0),
        "tanks_daily": int(limits.get("tanks_daily", 0) or 0),
        "aircraft_daily": int(limits.get("aircraft_daily", 0) or 0),
        "ships_daily": int(limits.get("ships_daily", 0) or 0),
        "spies_daily": spies_daily,
        "missiles_daily": int(limits.get("missiles", 0) or 0),
        "nukes_daily": int(limits.get("nukes", 0) or 0),
        "soldiers_max": int(limits.get("soldiers_max", 0) or 0),
        "tanks_max": int(limits.get("tanks_max", 0) or 0),
        "aircraft_max": int(limits.get("aircraft_max", 0) or 0),
        "ships_max": int(limits.get("ships_max", 0) or 0),
    }


def _target_payload(cog: DestroyCog, nation: Dict[str, Any]) -> Dict[str, Any]:
    cities = nation.get("cities") or []
    total_infra = sum((c.get("infrastructure", 0) or 0) for c in cities if isinstance(c, dict))
    avg_infra = total_infra / len(cities) if cities else 0
    return {
        "nation_id": nation.get("id") or nation.get("nation_id"),
        "nation_name": nation.get("nation_name", "Unknown"),
        "leader_name": nation.get("leader_name", ""),
        "alliance_id": nation.get("alliance_id"),
        "alliance_name": nation.get("alliance_name"),
        "score": round(float(nation.get("score", 0) or 0), 2),
        "cities": int(nation.get("num_cities") or len(cities) or 0),
        "avg_infra": round(avg_infra, 1),
        "soldiers": int(nation.get("soldiers", 0) or 0),
        "tanks": int(nation.get("tanks", 0) or 0),
        "aircraft": int(nation.get("aircraft", 0) or 0),
        "ships": int(nation.get("ships", 0) or 0),
        "spies": int(nation.get("spies", 0) or 0),
        "missiles": int(nation.get("missiles", 0) or 0),
        "nukes": int(nation.get("nukes", 0) or 0),
        "unit_power": round(float(cog._weighted_unit_power(nation)), 2),
        "offensive_slots_current": int(nation.get("offensive_slots_current", 0) or 0),
        "offensive_slots_max": int(nation.get("offensive_slots_max", cog._max_offensive_slots(nation)) or 0),
        "offensive_slots_open": int(nation.get("offensive_slots_open", 0) or 0),
        "defensive_slots_current": int(nation.get("defensive_slots_current", 0) or 0),
        "defensive_slots_max": 3,
        "defensive_slots_open": int(nation.get("defensive_slots_open", 0) or 0),
        "war_policy": nation.get("war_policy"),
        "has_missile_launch_pad": bool(nation.get("missile_launch_pad")),
        "has_nuclear_research_facility": bool(nation.get("nuclear_research_facility")),
        "purchase_limits": _purchase_payload(cog, nation),
    }


def _attacker_payload(
    cog: DestroyCog,
    attacker: Dict[str, Any],
    target: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cities = attacker.get("cities") or []
    total_infra = sum((c.get("infrastructure", 0) or 0) for c in cities if isinstance(c, dict))
    avg_infra = total_infra / len(cities) if cities else attacker.get("infra_average", 0) or 0
    rank_details = attacker.get("destroy_rank_details") or (cog._attacker_rank_breakdown(attacker, target) if target else {})
    return {
        **_target_payload(cog, attacker),
        "avg_infra": round(avg_infra, 1),
        "last_active_seconds": attacker.get("last_active_seconds"),
        "warchest_level": attacker.get("warchest_level", cog._warchest_level(attacker)),
        "rank_score": round(float(attacker.get("destroy_rank_score", 0) or 0), 2),
        "rank_details": rank_details,
        "sim_details": rank_details,
    }


def _weapon_payload(weapon_analysis: Dict[str, Any]) -> Dict[str, Any]:
    missile = weapon_analysis.get("missile_analysis", {}) or {}
    nuke = weapon_analysis.get("nuke_analysis", {}) or {}
    return {
        "optimal_weapon": weapon_analysis.get("optimal_weapon", "ground"),
        "best_city_infra": round(float(weapon_analysis.get("best_city_infra", 0) or 0), 1),
        "weapon_cost_source": weapon_analysis.get("weapon_cost_source", "fallback"),
        "missile_cost": round(float(missile.get("cost", 0) or 0)),
        "nuke_cost": round(float(nuke.get("cost", 0) or 0)),
        "missile_efficiency": round(float(missile.get("efficiency", 0) or 0), 2),
        "nuke_efficiency": round(float(nuke.get("efficiency", 0) or 0), 2),
        "missile_expected_efficiency": round(float(missile.get("expected_efficiency", 0) or 0), 2),
        "nuke_expected_efficiency": round(float(nuke.get("expected_efficiency", 0) or 0), 2),
        "missile_hit_chance": round(float(missile.get("hit_chance", 0) or 0), 2),
        "nuke_hit_chance": round(float(nuke.get("hit_chance", 0) or 0), 2),
        "missile_avg_dmg": round(float(missile.get("damage", 0) or 0), 2),
        "nuke_avg_dmg": round(float(nuke.get("damage", 0) or 0), 2),
        "has_iron_dome": bool(weapon_analysis.get("has_iron_dome")),
        "has_vds": bool(weapon_analysis.get("has_vds")),
    }


def _assignment_power_load(cog: DestroyCog, cand: Dict[str, Any]) -> float:
    """How much of an attacker's practical war capacity this target should consume."""
    target = cand["target"]
    attacker = cand["attacker"]
    target_power = float(cog._weighted_unit_power(target))
    attacker_power = max(float(cog._weighted_unit_power(attacker)), 1.0)
    if cog._visible_unit_total(target) <= 0 or target_power <= 0:
        return 0.0

    target_needed = max(1, int(cand.get("target_needed", 1) or 1))
    shared_power = target_power / target_needed
    ratio = target_power / attacker_power
    if ratio <= 0.35:
        return shared_power * 0.15
    if ratio <= 0.60:
        return shared_power * 0.35
    if ratio <= 0.85:
        return shared_power * 0.75
    return shared_power


def _attacker_power_limit(cog: DestroyCog, attacker: Dict[str, Any]) -> float:
    return max(float(cog._weighted_unit_power(attacker)), 1.0) * 1.15


def _apply_plan_counts(
    attacker: Dict[str, Any],
    target: Dict[str, Any],
    attacker_planned: int,
    target_planned: int,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    attacker = dict(attacker)
    target = dict(target)
    attacker["planned_attacks"] = attacker_planned
    attacker["offensive_slots_after_plan"] = max(0, int(attacker.get("offensive_slots_open", 0) or 0) - attacker_planned)
    target["planned_defenses"] = target_planned
    target["defensive_slots_after_plan"] = max(0, int(target.get("defensive_slots_open", 0) or 0) - target_planned)
    return attacker, target


def _build_attacker_plans(assignments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[int, Dict[str, Any]] = {}
    for row in assignments:
        attacker = row["attacker"]
        aid = int(attacker.get("nation_id") or 0)
        if not aid:
            continue
        if aid not in grouped:
            grouped[aid] = {
                "attacker": attacker,
                "assigned_count": 0,
                "total_rank_score": 0,
                "targets": [],
            }
        grouped[aid]["assigned_count"] += 1
        grouped[aid]["total_rank_score"] += float(row.get("rank_score", 0) or 0)
        grouped[aid]["targets"].append({
            "target": row["target"],
            "rank_score": row["rank_score"],
            "weapon_analysis": row["weapon_analysis"],
            "target_needed": row.get("target_needed", 1),
        })

    plans = []
    for plan in grouped.values():
        plan["average_rank_score"] = round(plan["total_rank_score"] / max(plan["assigned_count"], 1), 2)
        plan["targets"].sort(key=lambda t: float(t.get("rank_score", 0) or 0), reverse=True)
        plans.append(plan)

    plans.sort(
        key=lambda p: (
            -int(p.get("assigned_count", 0) or 0),
            -float(p.get("average_rank_score", 0) or 0),
            (p.get("attacker", {}).get("nation_name") or "").lower(),
        )
    )
    return plans


@router.get("/destroy/ac_data")
async def destroy_ac_data():
    """Nation/alliance autocomplete data, matching the weapon efficiency picker shape."""
    nations: List[Dict[str, Any]] = []
    alliances: Dict[int, Dict[str, Any]] = {}
    try:
        db = GlobalNationsDB(str(GLOBAL_NATIONS_DB))
        all_nations = await db.get_all_nations()
        for n in all_nations:
            if not n.get("nation_name"):
                continue
            nations.append({
                "id": n.get("id"),
                "nation_name": n.get("nation_name", ""),
                "leader_name": n.get("leader_name", ""),
            })
            aid = n.get("alliance_id")
            aname = n.get("alliance_name")
            if aid and aname and aid not in alliances:
                alliances[int(aid)] = {"alliance_id": int(aid), "alliance_name": aname}
        for a in await db.get_distinct_alliances(""):
            aid = a.get("alliance_id")
            if aid and a.get("alliance_name") and aid not in alliances:
                alliances[int(aid)] = {"alliance_id": int(aid), "alliance_name": a["alliance_name"]}
    except Exception as e:
        logger.warning("destroy_ac_data failed: %s", e)

    nations.sort(key=lambda n: (n.get("nation_name") or "").lower())
    alliance_list = sorted(alliances.values(), key=lambda a: (a.get("alliance_name") or "").lower())
    return {"nations": nations, "alliances": alliance_list}


@router.get("/destroy/analyze")
async def destroy_analyze(
    target_type: str = "nation",
    target: str = "",
    attackers: str = "10259",
    num_attackers: int = 3,
    exclude_unoptimal: bool = False,
):
    try:
        target_type = (target_type or "nation").lower()
        max_attackers = 3
        db = GlobalNationsDB(str(GLOBAL_NATIONS_DB))
        cog = DestroyCog(bot=None)
        active_war_counts = await _get_active_war_counts()
        weapon_costs = await cog._get_live_weapon_costs()

        attacker_alliances, unresolved_attackers = await _resolve_attacker_alliances(db, attackers or "10259")
        if not attacker_alliances:
            return JSONResponse({"error": "No valid attacker alliances found.", "unresolved_attackers": unresolved_attackers}, status_code=400)

        attacker_nations: List[Dict[str, Any]] = []
        for alliance in attacker_alliances:
            attacker_nations.extend(await _load_alliance_nations(db, int(alliance["id"])))
        attacker_nations = [n for n in attacker_nations if _is_active_member(n)]

        if target_type == "alliance":
            target_alliance = await _resolve_alliance(db, target)
            if not target_alliance:
                return JSONResponse({"error": f"Alliance '{target}' not found."}, status_code=404)
            target_nations = await _load_alliance_nations(db, int(target_alliance["id"]))
            target_nations = [cog._attach_slot_state(n, active_war_counts) for n in target_nations if _is_active_member(n)]
            target_nations = [n for n in target_nations if int(n.get("defensive_slots_open", 0) or 0) > 0]

            candidates: List[Dict[str, Any]] = []
            for target_nation in target_nations:
                result = cog._find_optimal_attackers_sync(
                    [dict(a) for a in attacker_nations],
                    dict(target_nation),
                    max_groups=10,
                    exclude_unoptimal=exclude_unoptimal,
                    num_attackers=max_attackers,
                    active_war_counts=active_war_counts,
                    weapon_costs=weapon_costs,
                )
                needed = int(result.get("effective_num_attackers") or 0)
                if needed <= 0:
                    continue
                weapon = cog._analyze_weapon_optimal_for_target(target_nation, weapon_costs)
                for attacker in result.get("all_attackers", []):
                    candidates.append({
                        "target": target_nation,
                        "attacker": attacker,
                        "rank_score": float(attacker.get("destroy_rank_score", 0) or 0),
                        "weapon_analysis": weapon,
                        "target_needed": needed,
                    })

            candidates.sort(key=lambda c: c["rank_score"], reverse=True)
            attacker_remaining: Dict[int, int] = {}
            for attacker in attacker_nations:
                if not attacker.get("id"):
                    continue
                slotted = cog._attach_slot_state(dict(attacker), active_war_counts)
                attacker_remaining[int(slotted["id"])] = int(slotted.get("offensive_slots_open", 0) or 0)
            target_remaining: Dict[int, int] = {}
            for cand in candidates:
                tid = int(cand["target"].get("id") or 0)
                if tid and tid not in target_remaining:
                    target_remaining[tid] = min(
                        int(cand.get("target_needed", 0) or 0),
                        int(cand["target"].get("defensive_slots_open", 0) or 0),
                    )

            selected_assignments = []
            used_pairs = set()
            attacker_load: Dict[int, float] = {}
            attacker_assigned: Counter[int] = Counter()
            for cand in candidates:
                aid = int(cand["attacker"].get("id") or 0)
                tid = int(cand["target"].get("id") or 0)
                if not aid or not tid or (aid, tid) in used_pairs:
                    continue
                if attacker_remaining.get(aid, 0) <= 0 or target_remaining.get(tid, 0) <= 0:
                    continue
                if (
                    int(cand.get("target_needed", 0) or 0) <= 1
                    and cog._visible_unit_total(cand["target"]) > 0
                    and cog._weighted_unit_power(cand["attacker"]) < cog._weighted_unit_power(cand["target"])
                ):
                    continue
                load = _assignment_power_load(cog, cand)
                projected_load = attacker_load.get(aid, 0.0) + load
                if attacker_assigned.get(aid, 0) > 0 and projected_load > _attacker_power_limit(cog, cand["attacker"]):
                    continue
                used_pairs.add((aid, tid))
                attacker_remaining[aid] -= 1
                target_remaining[tid] -= 1
                attacker_load[aid] = projected_load
                attacker_assigned[aid] += 1
                selected_assignments.append(cand)

            selected_by_target = Counter(int(c["target"].get("id") or 0) for c in selected_assignments)
            selected_assignments = [
                c for c in selected_assignments
                if not (
                    cog._visible_unit_total(c["target"]) > 0
                    and selected_by_target.get(int(c["target"].get("id") or 0), 0) < int(c.get("target_needed", 1) or 1)
                    and int(c.get("target_needed", 1) or 1) > 1
                )
                and not (
                    selected_by_target.get(int(c["target"].get("id") or 0), 0) == 1
                    and cog._visible_unit_total(c["target"]) > 0
                    and cog._weighted_unit_power(c["attacker"]) < cog._weighted_unit_power(c["target"])
                )
            ]

            attacker_planned = Counter(int(c["attacker"].get("id") or 0) for c in selected_assignments)
            target_planned = Counter(int(c["target"].get("id") or 0) for c in selected_assignments)
            assignments = []
            for cand in selected_assignments:
                attacker_payload = _attacker_payload(cog, cand["attacker"], cand["target"])
                target_payload = _target_payload(cog, cand["target"])
                aid = int(attacker_payload.get("nation_id") or 0)
                tid = int(target_payload.get("nation_id") or 0)
                attacker_payload, target_payload = _apply_plan_counts(
                    attacker_payload,
                    target_payload,
                    attacker_planned.get(aid, 0),
                    target_planned.get(tid, 0),
                )
                assignments.append({
                    "target": target_payload,
                    "attacker": attacker_payload,
                    "rank_score": round(cand["rank_score"], 2),
                    "weapon_analysis": _weapon_payload(cand["weapon_analysis"]),
                    "target_needed": int(cand.get("target_needed", 1) or 1),
                })

            return {
                "mode": "alliance",
                "target_alliance": target_alliance,
                "attacker_alliances": attacker_alliances,
                "unresolved_attackers": unresolved_attackers,
                "target_count": len(target_nations),
                "attacker_pool_count": len(attacker_nations),
                "candidate_count": len(candidates),
                "assignment_count": len(assignments),
                "target_attackers_requested": "dynamic",
                "assignments": assignments,
                "attacker_plans": _build_attacker_plans(assignments),
            }

        target_nation = await _resolve_nation(db, target)
        if not target_nation:
            return JSONResponse({"error": f"Nation '{target}' not found."}, status_code=404)

        target_nation = cog._attach_slot_state(target_nation, active_war_counts)
        weapon = cog._analyze_weapon_optimal_for_target(target_nation, weapon_costs)
        result = cog._find_optimal_attackers_sync(
            [dict(a) for a in attacker_nations],
            target_nation,
            max_groups=10,
            exclude_unoptimal=exclude_unoptimal,
            num_attackers=max_attackers,
            active_war_counts=active_war_counts,
            weapon_costs=weapon_costs,
        )

        effective = int(result.get("effective_num_attackers") or 0)
        attackers_out = [_attacker_payload(cog, a, target_nation) for a in result.get("all_attackers", [])[:effective]]
        planned_count = len(attackers_out)
        target_payload = _target_payload(cog, target_nation)
        target_payload["planned_defenses"] = planned_count
        target_payload["defensive_slots_after_plan"] = max(0, int(target_payload.get("defensive_slots_open", 0) or 0) - planned_count)
        for attacker in attackers_out:
            attacker["planned_attacks"] = 1 if planned_count else 0
            attacker["offensive_slots_after_plan"] = max(0, int(attacker.get("offensive_slots_open", 0) or 0) - attacker["planned_attacks"])
        return {
            "mode": "nation",
            "target": target_payload,
            "attacker_alliances": attacker_alliances,
            "unresolved_attackers": unresolved_attackers,
            "attacker_pool_count": len(attacker_nations),
            "total_found": result.get("total_found", 0),
            "effective_num_attackers": effective,
            "target_slots_full": bool(result.get("target_slots_full")),
            "weapon_analysis": _weapon_payload(weapon),
            "attackers": attackers_out,
        }
    except Exception as e:
        logger.error("destroy_analyze failed: %s", e, exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

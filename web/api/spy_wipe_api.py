"""Spy wipe planner API.

Builds deterministic Assassinate Spies assignments from GlobalNations.db using
the same odds and assassination formulas used by the Discord spy command.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional
from heapq import heappop, heappush

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from Systems.Functions.db_paths import GLOBAL_NATIONS_DB
from Systems.PnW.Util.spy_calc import EspionageOperation, SafetyLevel, SpyCalculator

router = APIRouter()
logger = logging.getLogger("Reaper.WebServer.SpyWipeAPI")

OPERATION = EspionageOperation.ASSASSINATE_SPIES
SAFETY_LEVELS = (
    SafetyLevel.QUICK_AND_DIRTY,
    SafetyLevel.NORMAL_PRECAUTIONS,
    SafetyLevel.EXTREMELY_COVERT,
)
SAFETY_NAMES = {
    SafetyLevel.QUICK_AND_DIRTY: "Quick and Dirty",
    SafetyLevel.NORMAL_PRECAUTIONS: "Normal Precautions",
    SafetyLevel.EXTREMELY_COVERT: "Extremely Covert",
}


class SpyWipeRequest(BaseModel):
    attacker_alliances: list[str] = Field(default_factory=list)
    target_type: str = "alliance"
    target: str
    attacker_daily_cap: int = 2
    target_daily_cap: int = 3


def _db_path() -> Path:
    return Path(GLOBAL_NATIONS_DB)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    return conn


def _nation_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "nation_name": row["nation_name"] or f"Nation {row['id']}",
        "leader_name": row["leader_name"] or "",
        "flag": row["flag"] or "",
        "alliance_id": row["alliance_id"],
        "alliance_name": row["alliance_name"] or "",
        "alliance_position": row["alliance_position"] or "",
        "vacation_mode_turns": int(row["vacation_mode_turns"] or 0),
        "score": float(row["score"] or 0),
        "espionage_available": bool(row["espionage_available"]),
        "spies": int(row["spies"] or 0),
        "war_policy": row["war_policy"] or None,
        "spy_satellite": bool(row["spy_satellite"]),
        "central_intelligence_agency": bool(row["central_intelligence_agency"]),
    }


def _active_target_nation(nation: dict[str, Any]) -> bool:
    if nation["vacation_mode_turns"] > 0:
        return False
    if (nation["alliance_position"] or "").strip().upper() == "APPLICANT":
        return False
    return nation["score"] > 0


def _active_attacker_nation(nation: dict[str, Any]) -> bool:
    return _active_target_nation(nation) and bool(nation.get("espionage_available", True))


def _clean_identifier(identifier: str) -> str:
    text = (identifier or "").strip()
    if " - " in text and text.rsplit(" - ", 1)[-1].isdigit():
        return text.rsplit(" - ", 1)[-1].strip()
    return text


def _resolve_alliance(conn: sqlite3.Connection, identifier: str) -> Optional[dict[str, Any]]:
    text = _clean_identifier(identifier)
    cur = conn.cursor()
    if text.isdigit():
        cur.execute(
            """
            SELECT alliance_id, alliance_name, COUNT(*) AS member_count
            FROM nations
            WHERE alliance_id = ?
            GROUP BY alliance_id, alliance_name
            """,
            (int(text),),
        )
    else:
        cur.execute(
            """
            SELECT alliance_id, alliance_name, COUNT(*) AS member_count
            FROM nations
            WHERE lower(alliance_name) = lower(?)
              AND alliance_id IS NOT NULL
            GROUP BY alliance_id, alliance_name
            ORDER BY member_count DESC
            LIMIT 1
            """,
            (text,),
        )
    row = cur.fetchone()
    if not row and text and not text.isdigit():
        cur.execute(
            """
            SELECT alliance_id, alliance_name, COUNT(*) AS member_count
            FROM nations
            WHERE lower(alliance_name) LIKE lower(?)
              AND alliance_id IS NOT NULL
            GROUP BY alliance_id, alliance_name
            ORDER BY member_count DESC
            LIMIT 1
            """,
            (f"%{text}%",),
        )
        row = cur.fetchone()
    if not row or not row["alliance_id"]:
        return None
    return {
        "id": int(row["alliance_id"]),
        "name": row["alliance_name"] or f"Alliance {row['alliance_id']}",
        "member_count": int(row["member_count"] or 0),
    }


def _get_nations_by_alliance(conn: sqlite3.Connection, alliance_id: int) -> list[dict[str, Any]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, nation_name, leader_name, flag, alliance_id, alliance_name,
               alliance_position, vacation_mode_turns, score, espionage_available,
               spies, war_policy, spy_satellite, central_intelligence_agency
        FROM nations
        WHERE alliance_id = ?
        ORDER BY spies DESC, score DESC
        """,
        (alliance_id,),
    )
    return [_nation_from_row(row) for row in cur.fetchall()]


def _resolve_nation(conn: sqlite3.Connection, identifier: str) -> Optional[dict[str, Any]]:
    text = _clean_identifier(identifier)
    cur = conn.cursor()
    if text.isdigit():
        cur.execute(
            """
            SELECT id, nation_name, leader_name, flag, alliance_id, alliance_name,
                   alliance_position, vacation_mode_turns, score, espionage_available,
                   spies, war_policy, spy_satellite, central_intelligence_agency
            FROM nations
            WHERE id = ?
            """,
            (int(text),),
        )
    else:
        cur.execute(
            """
            SELECT id, nation_name, leader_name, flag, alliance_id, alliance_name,
                   alliance_position, vacation_mode_turns, score, espionage_available,
                   spies, war_policy, spy_satellite, central_intelligence_agency
            FROM nations
            WHERE lower(nation_name) = lower(?) OR lower(leader_name) = lower(?)
            ORDER BY spies DESC
            LIMIT 1
            """,
            (text, text),
        )
    row = cur.fetchone()
    if not row and text and not text.isdigit():
        cur.execute(
            """
            SELECT id, nation_name, leader_name, flag, alliance_id, alliance_name,
                   alliance_position, vacation_mode_turns, score, espionage_available,
                   spies, war_policy, spy_satellite, central_intelligence_agency
            FROM nations
            WHERE lower(nation_name) LIKE lower(?) OR lower(leader_name) LIKE lower(?)
            ORDER BY spies DESC
            LIMIT 1
            """,
            (f"%{text}%", f"%{text}%"),
        )
        row = cur.fetchone()
    return _nation_from_row(row) if row else None


def _success_spy_kills(attacking_spies: int, defender_spies: float, defender_spy_satellite: bool) -> int:
    """Average successful Assassinate Spies kills, matching spy_calc ordering."""
    if attacking_spies <= 0 or defender_spies <= 0:
        return 0
    base_value = (attacking_spies - (defender_spies * 0.4)) * 0.5
    if base_value <= 0:
        return 0
    kills = base_value * 0.95
    max_cap = (defender_spies * 0.25) + 4
    kills = min(kills, max_cap)
    if defender_spy_satellite:
        kills *= 1.5
    return min(int(kills), int(defender_spies))


def _minimum_spies_for_kills(
    max_spies: int,
    defender_spies: float,
    defender_spy_satellite: bool,
    required_kills: int,
) -> Optional[int]:
    if required_kills <= 0:
        return None
    low = 1
    high = max_spies
    best: Optional[int] = None
    while low <= high:
        mid = (low + high) // 2
        kills = _success_spy_kills(mid, defender_spies, defender_spy_satellite)
        if kills >= required_kills:
            best = mid
            high = mid - 1
        else:
            low = mid + 1
    return best


def _minimum_spies_for_odds(
    low_spies: int,
    max_spies: int,
    defender_spies: float,
    safety: SafetyLevel,
    attacker_war_policy: Optional[str],
    defender_war_policy: Optional[str],
    target_odds: float,
) -> Optional[int]:
    low = max(1, int(low_spies))
    high = max_spies
    best: Optional[int] = None
    while low <= high:
        mid = (low + high) // 2
        odds = SpyCalculator.calculate_final_odds(
            mid,
            defender_spies,
            safety,
            OPERATION,
            attacker_war_policy,
            defender_war_policy,
        )
        if odds >= target_odds:
            best = mid
            high = mid - 1
        else:
            low = mid + 1
    return best


def _best_assassination(attacker: dict[str, Any], target: dict[str, Any], defender_spies: float) -> Optional[dict[str, Any]]:
    max_spies = int(attacker["spies"] or 0)
    if max_spies <= 0 or defender_spies <= 0:
        return None

    defender_spy_satellite = bool(target.get("spy_satellite"))
    success_kills = _success_spy_kills(max_spies, defender_spies, defender_spy_satellite)
    if success_kills <= 0:
        return None

    min_kill_spies = _minimum_spies_for_kills(
        max_spies,
        defender_spies,
        defender_spy_satellite,
        success_kills,
    )
    if min_kill_spies is None:
        return None

    attacker_policy = attacker.get("war_policy")
    defender_policy = target.get("war_policy")
    best_100: Optional[dict[str, Any]] = None
    for safety in SAFETY_LEVELS:
        spies_for_100 = _minimum_spies_for_odds(
            min_kill_spies,
            max_spies,
            defender_spies,
            safety,
            attacker_policy,
            defender_policy,
            100.0,
        )
        if spies_for_100 is None:
            continue
        candidate = {
            "spies_to_use": spies_for_100,
            "safety": safety,
            "odds": 100.0,
        }
        if (
            best_100 is None
            or candidate["spies_to_use"] < best_100["spies_to_use"]
            or (
                candidate["spies_to_use"] == best_100["spies_to_use"]
                and candidate["safety"].value < best_100["safety"].value
            )
        ):
            best_100 = candidate

    if best_100:
        spies_to_use = int(best_100["spies_to_use"])
        safety = best_100["safety"]
        odds = float(best_100["odds"])
    else:
        safety = SafetyLevel.EXTREMELY_COVERT
        spies_to_use = max_spies
        odds = SpyCalculator.calculate_final_odds(
            spies_to_use,
            defender_spies,
            safety,
            OPERATION,
            attacker_policy,
            defender_policy,
        )

    return {
        "spies_to_use": spies_to_use,
        "safety_level": safety.value,
        "safety_name": SAFETY_NAMES[safety],
        "odds": odds,
        "success_kills": success_kills,
        "expected_kills": success_kills * (odds / 100.0),
    }


def _public_nation(nation: dict[str, Any], include_remaining: bool = False) -> dict[str, Any]:
    out = {
        "id": nation["id"],
        "nation_name": nation["nation_name"],
        "leader_name": nation["leader_name"],
        "flag": nation["flag"],
        "alliance_id": nation["alliance_id"],
        "alliance_name": nation["alliance_name"],
        "score": round(nation["score"], 2),
        "spies": int(nation["spies"] or 0),
        "war_policy": nation["war_policy"],
        "spy_satellite": bool(nation["spy_satellite"]),
        "central_intelligence_agency": bool(nation["central_intelligence_agency"]),
    }
    if include_remaining:
        out["remaining_spies"] = round(float(nation.get("remaining_spies", 0)), 2)
        out["ops_received"] = int(nation.get("ops_received", 0))
    return out


class _MinCostMaxFlow:
    def __init__(self, node_count: int):
        self.graph: list[list[list[float]]] = [[] for _ in range(node_count)]

    def add_edge(self, src: int, dst: int, capacity: int, cost: float) -> None:
        fwd = [dst, capacity, cost, len(self.graph[dst])]
        rev = [src, 0, -cost, len(self.graph[src])]
        self.graph[src].append(fwd)
        self.graph[dst].append(rev)

    def flow(self, source: int, sink: int, max_flow: int) -> tuple[int, float]:
        node_count = len(self.graph)
        potential = [0.0] * node_count
        for edge in self.graph[source]:
            if edge[1] > 0:
                potential[int(edge[0])] = 0.0
        for node in range(node_count):
            if node == source:
                continue
            for edge in self.graph[node]:
                if edge[1] > 0:
                    nxt = int(edge[0])
                    potential[nxt] = min(potential[nxt], potential[node] + float(edge[2]))
        sent = 0
        total_cost = 0.0

        while sent < max_flow:
            dist = [float("inf")] * node_count
            parent_node = [-1] * node_count
            parent_edge = [-1] * node_count
            dist[source] = 0.0
            heap: list[tuple[float, int]] = [(0.0, source)]

            while heap:
                current_dist, node = heappop(heap)
                if current_dist != dist[node]:
                    continue
                for edge_index, edge in enumerate(self.graph[node]):
                    if edge[1] <= 0:
                        continue
                    nxt = int(edge[0])
                    next_dist = current_dist + float(edge[2]) + potential[node] - potential[nxt]
                    if next_dist + 1e-9 < dist[nxt]:
                        dist[nxt] = next_dist
                        parent_node[nxt] = node
                        parent_edge[nxt] = edge_index
                        heappush(heap, (next_dist, nxt))

            if parent_node[sink] == -1:
                break

            for node in range(node_count):
                if dist[node] < float("inf"):
                    potential[node] += dist[node]

            add = max_flow - sent
            node = sink
            while node != source:
                prev = parent_node[node]
                edge = self.graph[prev][parent_edge[node]]
                add = min(add, int(edge[1]))
                node = prev

            node = sink
            while node != source:
                prev = parent_node[node]
                edge = self.graph[prev][parent_edge[node]]
                edge[1] -= add
                reverse = self.graph[node][int(edge[3])]
                reverse[1] += add
                total_cost += add * float(edge[2])
                node = prev

            sent += add

        return sent, total_cost


def _build_plan(
    attackers: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    attacker_daily_cap: int,
    target_daily_cap: int,
) -> dict[str, Any]:
    attacker_daily_cap = max(1, min(int(attacker_daily_cap or 2), 2))
    target_daily_cap = max(1, min(int(target_daily_cap or 3), 4))

    attacker_state = {
        a["id"]: {**a, "ops_sent": 0}
        for a in attackers
        if _active_attacker_nation(a) and int(a.get("spies") or 0) > 0
    }
    target_state = {
        t["id"]: {
            **t,
            "ops_received": 0,
            "remaining_spies": float(t.get("spies") or 0),
            "expected_kills_received": 0.0,
            "success_kills_received": 0,
        }
        for t in targets
        if _active_target_nation(t) and int(t.get("spies") or 0) > 0
    }

    assignments: list[dict[str, Any]] = []

    def optimize_pass(pass_targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        available_attackers = [
            attacker for attacker in attacker_state.values()
            if attacker["ops_sent"] < attacker_daily_cap
        ]
        if not available_attackers or not pass_targets:
            return []

        source = 0
        attacker_offset = 1
        target_offset = attacker_offset + len(available_attackers)
        sink = target_offset + len(pass_targets)
        solver = _MinCostMaxFlow(sink + 1)
        edge_payload: dict[tuple[int, int], dict[str, Any]] = {}

        for attacker_index, attacker in enumerate(available_attackers):
            remaining_ops = max(0, attacker_daily_cap - int(attacker["ops_sent"]))
            solver.add_edge(source, attacker_offset + attacker_index, remaining_ops, 0.0)

        for target_index, _target in enumerate(pass_targets):
            solver.add_edge(target_offset + target_index, sink, 1, 0.0)

        for attacker_index, attacker in enumerate(available_attackers):
            attacker_node = attacker_offset + attacker_index
            for target_index, target in enumerate(pass_targets):
                if attacker["id"] == target["id"]:
                    continue
                if not SpyCalculator.can_espionage_target(attacker["score"], target["score"]):
                    continue
                op = _best_assassination(attacker, target, target["remaining_spies"])
                if not op:
                    continue
                target_node = target_offset + target_index
                # Min-cost flow minimizes, so negate expected value. Small tie breakers
                # prefer larger successful hits and fuller attackers for identical EVs.
                cost = -(
                    float(op["expected_kills"])
                    + float(op["success_kills"]) / 10000.0
                    + float(attacker["spies"]) / 1000000.0
                )
                edge_index = len(solver.graph[attacker_node])
                solver.add_edge(attacker_node, target_node, 1, cost)
                edge_payload[(attacker_node, edge_index)] = {
                    "attacker": attacker,
                    "target": target,
                    "operation": op,
                }

        solver.flow(source, sink, min(len(pass_targets), sum(
            max(0, attacker_daily_cap - int(a["ops_sent"])) for a in available_attackers
        )))

        chosen: list[dict[str, Any]] = []
        for (attacker_node, edge_index), payload in edge_payload.items():
            edge = solver.graph[attacker_node][edge_index]
            if int(edge[1]) == 0:
                chosen.append(payload)

        chosen.sort(
            key=lambda p: (
                p["target"]["remaining_spies"],
                p["operation"]["expected_kills"],
                p["operation"]["success_kills"],
            ),
            reverse=True,
        )
        return chosen

    def append_assignment(attacker: dict[str, Any], target: dict[str, Any], op: dict[str, Any]) -> None:
        before = float(target["remaining_spies"])
        after = max(0.0, before - float(op["expected_kills"]))
        attacker["ops_sent"] += 1
        target["ops_received"] += 1
        target["expected_kills_received"] += float(op["expected_kills"])
        target["success_kills_received"] += int(op["success_kills"])
        target["remaining_spies"] = after
        assignments.append({
            "order": len(assignments) + 1,
            "attacker": _public_nation(attacker),
            "target": _public_nation(target, include_remaining=True),
            "spies_to_use": int(op["spies_to_use"]),
            "safety_level": int(op["safety_level"]),
            "safety_name": op["safety_name"],
            "odds": round(float(op["odds"]), 2),
            "success_kills": int(op["success_kills"]),
            "expected_kills": round(float(op["expected_kills"]), 2),
            "target_spies_before": round(before, 2),
            "target_spies_after": round(after, 2),
        })

    # Pass-based scheduling spreads hits across as many target nations as possible:
    # first pass gives each high-spy target one best hit, then second and third
    # passes revisit the same sorted pool while caps and attacker ops remain.
    for pass_index in range(target_daily_cap):
        made_assignment = False
        ordered_targets = sorted(
            target_state.values(),
            key=lambda t: (t["remaining_spies"], t["spies"]),
            reverse=True,
        )
        pass_targets = [
            target for target in ordered_targets
            if target["ops_received"] == pass_index
            and target["ops_received"] < target_daily_cap
            and target["remaining_spies"] >= 1
        ]
        for best in optimize_pass(pass_targets):
            append_assignment(best["attacker"], best["target"], best["operation"])
            made_assignment = True
        if not made_assignment:
            break

    target_summaries = sorted(
        (
            {
                **_public_nation(t, include_remaining=True),
                "expected_kills_received": round(float(t.get("expected_kills_received", 0)), 2),
                "success_kills_received": int(t.get("success_kills_received", 0)),
            }
            for t in target_state.values()
        ),
        key=lambda t: (t["ops_received"], t["spies"]),
        reverse=True,
    )
    attacker_summaries = sorted(
        (
            {
                **_public_nation(a),
                "ops_sent": int(a["ops_sent"]),
                "ops_remaining": max(0, attacker_daily_cap - int(a["ops_sent"])),
            }
            for a in attacker_state.values()
        ),
        key=lambda a: (a["ops_sent"], a["spies"]),
        reverse=True,
    )

    total_expected = sum(a["expected_kills"] for a in assignments)
    total_success = sum(a["success_kills"] for a in assignments)
    return {
        "assignments": assignments,
        "targets": target_summaries,
        "attackers": attacker_summaries,
        "summary": {
            "planned_ops": len(assignments),
            "total_expected_kills": round(total_expected, 2),
            "total_success_kills": int(total_success),
            "attackers_loaded": len(attackers),
            "attackers_eligible": len(attacker_state),
            "attackers_used": len({a["attacker"]["id"] for a in assignments}),
            "targets_loaded": len(targets),
            "targets_eligible": len(target_state),
            "targets_hit": len({a["target"]["id"] for a in assignments}),
            "attacker_daily_cap": attacker_daily_cap,
            "target_daily_cap": target_daily_cap,
            "operation": "Assassinate Spies",
        },
    }


@router.post("/spy-wipe/plan")
async def spy_wipe_plan(request: SpyWipeRequest):
    if not _db_path().exists():
        return JSONResponse({"error": "GlobalNations.db was not found."}, status_code=503)
    if not request.attacker_alliances:
        return JSONResponse({"error": "Select at least one attacker alliance."}, status_code=400)
    if request.target_type not in {"nation", "alliance"}:
        return JSONResponse({"error": "target_type must be nation or alliance."}, status_code=400)

    try:
        with _connect() as conn:
            attacker_alliances: list[dict[str, Any]] = []
            attackers_by_id: dict[int, dict[str, Any]] = {}
            unresolved_attackers: list[str] = []
            for identifier in request.attacker_alliances:
                alliance = _resolve_alliance(conn, identifier)
                if not alliance:
                    unresolved_attackers.append(identifier)
                    continue
                attacker_alliances.append(alliance)
                for nation in _get_nations_by_alliance(conn, alliance["id"]):
                    attackers_by_id[nation["id"]] = nation

            if not attacker_alliances:
                return JSONResponse(
                    {"error": f"Could not resolve attacker alliances: {', '.join(unresolved_attackers)}"},
                    status_code=404,
                )

            target_info: dict[str, Any]
            targets: list[dict[str, Any]]
            if request.target_type == "nation":
                nation = _resolve_nation(conn, request.target)
                if not nation:
                    return JSONResponse({"error": f"Target nation '{request.target}' was not found."}, status_code=404)
                target_info = {
                    "type": "nation",
                    "id": nation["id"],
                    "name": nation["nation_name"],
                }
                targets = [nation]
            else:
                alliance = _resolve_alliance(conn, request.target)
                if not alliance:
                    return JSONResponse({"error": f"Target alliance '{request.target}' was not found."}, status_code=404)
                target_info = {
                    "type": "alliance",
                    "id": alliance["id"],
                    "name": alliance["name"],
                }
                targets = _get_nations_by_alliance(conn, alliance["id"])

        attackers = list(attackers_by_id.values())
        target_ids = {t["id"] for t in targets}
        attackers = [a for a in attackers if a["id"] not in target_ids]

        plan = _build_plan(
            attackers=attackers,
            targets=targets,
            attacker_daily_cap=request.attacker_daily_cap,
            target_daily_cap=request.target_daily_cap,
        )
        return JSONResponse({
            "attacker_alliances": attacker_alliances,
            "unresolved_attackers": unresolved_attackers,
            "target": target_info,
            **plan,
        })
    except Exception as e:
        logger.error("spy_wipe_plan error: %s", e, exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

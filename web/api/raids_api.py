"""
Raids API — web endpoint that mirrors the /raids Discord command.
Also handles beige notification alerts (save/delete/list) stored in alerts.db.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import aiosqlite
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.requests import Request

from Systems.Functions.db_paths import (
    ALERTS_DB_STR as ALERTS_DB,
    GLOBAL_NATIONS_DB_STR,
)

router = APIRouter()
logger = logging.getLogger("Reaper.RaidsAPI")


def _current_user_id(request: Request) -> str | None:
    discord_user = request.session.get("discord_user")
    if discord_user and isinstance(discord_user, dict):
        uid = discord_user.get("id")
        if uid:
            return str(uid)
    uid = request.session.get("user_id")
    return str(uid) if uid else None


async def _require_access(request: Request):
    """Raise 403 if the session user does not have raids page access."""
    from Systems.Functions.page_access import has_access
    uid = _current_user_id(request)
    if not uid or not await has_access(uid, "raids"):
        raise HTTPException(status_code=403, detail="Access denied. You are not authorised to view this page.")

# ── Constants (mirrors raids.py) ──────────────────────────────────────────────
WAR_RANGE_MIN   = 0.75
WAR_RANGE_MAX   = 2.5
INACTIVITY_DAYS = 7

LOOT_MULTIPLIERS = {
    "war_type": {
        "ordinary_war": 0.10,
        "raid":         0.075,
        "attrition_war":0.12,
        "blockade":     0.05,
    },
    "offense": {"pirate": 1.4, "ape": 1.1},
    "defense":  {"fortress": 0.9, "moneybags": 0.6, "turtle": 0.95, "pirate": 1.1},
}

RESOURCES = ["coal", "oil", "uranium", "iron", "bauxite", "lead",
             "gasoline", "munitions", "steel", "aluminum", "food"]

# ── Revenue accumulation since last loot ─────────────────────────────────────
# PnW constants
TURNS_PER_DAY  = 12
TURNS_PER_YEAR = 365 * TURNS_PER_DAY   # 4380 — kept for any legacy callers


async def _get_revenue_per_turn(nation: dict) -> tuple:
    """
    Returns (net_cash_per_turn, {resource: units_per_turn}).
    Uses the full city-build engine — same as /revenue command.
    Resource values can be negative (consumed > produced).
    """
    if not nation.get("cities"):
        return 0.0, {}
    try:
        from Systems.PnW.Util.rev_correct import calculate_full_revenue_with_query
        result = await calculate_full_revenue_with_query(nation_data=nation, is_war=False)
        cash_pt = float(result.get("gross_income") or 0.0)
        rss_pt  = {r: float((result.get("resources") or {}).get(r) or 0.0) for r in RESOURCES}
        return cash_pt, rss_pt
    except Exception as e:
        logger.warning(f"Revenue calc failed for nation {nation.get('id')}: {e}")
        return 0.0, {}


def _turns_since_last_looted(nation: dict) -> int:
    """Return turns elapsed since the nation was last looted (fallback only)."""
    loot_event = nation.get("_loot_event")
    if not loot_event:
        return 0
    raw = loot_event.get("date")
    if not raw:
        return 0
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return max(0, int((datetime.now(timezone.utc) - dt).total_seconds() / 7200))
    except Exception:
        return 0


def _parse_loot_str(s: Optional[str]) -> float:
    if not s:
        return 0.0
    s = s.strip().lower()
    mult = 1
    if s.endswith("m"):
        mult = 1_000_000; s = s[:-1]
    elif s.endswith("k"):
        mult = 1_000; s = s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return 0.0


def _is_inactive(nation: dict) -> bool:
    la = nation.get("last_active")
    if not la:
        return True
    try:
        dt = datetime.fromisoformat(la.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days >= INACTIVITY_DAYS
    except Exception:
        return True


def _military_strength(n: dict) -> float:
    return (
        (n.get("soldiers", 0) or 0) * 0.1 +
        (n.get("tanks",    0) or 0) * 5 +
        (n.get("aircraft", 0) or 0) * 50 +
        (n.get("ships",    0) or 0) * 100 +
        (n.get("missiles", 0) or 0) * 250 +
        (n.get("nukes",    0) or 0) * 1000
    )




async def _calculate_loot(
    nation: dict,
    attacker_has_ape: bool,
    prices: Dict[str, float],
    holdings: Optional[Dict[str, Any]] = None,
) -> Dict[str, float]:
    """
    Holdings-only loot projection.

    Primary path (holdings row exists):
      holdings.money_held and holdings.*_held are the complete picture —
      already net of all spending (city/infra/land/improvements/projects)
      and all transfers (bankrecs). No revenue accumulation added on top.

    Fallback path (no holdings row):
      Revenue-based accumulation since last_loot_date.
    """
    m = LOOT_MULTIPLIERS

    bp  = m["war_type"]["raid"]
    off = m["offense"]["pirate"] * (m["offense"]["ape"] if attacker_has_ape else 1.0)
    dfn = m["defense"].get((nation.get("war_policy") or "fortress").lower(), 1.0)
    loot_pct = bp * off * dfn

    if holdings:
        cash_pool = max(0.0, float(holdings.get("money_held") or 0))
        rss_pool  = {r: max(0.0, float(holdings.get(f"{r}_held") or 0)) for r in RESOURCES}
        confidence = holdings.get("confidence", "tracked")
    else:
        # Fallback: revenue accumulation (no holdings row)
        turns     = _turns_since_last_looted(nation)
        cap_turns = 30 * TURNS_PER_DAY
        eff_turns = min(turns if turns > 0 else 7 * TURNS_PER_DAY, cap_turns)

        cash_pt, rss_pt = await _get_revenue_per_turn(nation)
        cash_pool  = max(0.0, cash_pt * eff_turns)
        rss_pool   = {r: max(0.0, rss_pt.get(r, 0) * eff_turns) for r in RESOURCES}
        confidence = "estimated"

    proj_cash      = cash_pool * loot_pct
    proj_rss       = {r: rss_pool[r] * loot_pct for r in RESOURCES}
    proj_rss_value = sum(proj_rss[r] * prices.get(r, 0) for r in RESOURCES)
    total_projected = proj_cash + proj_rss_value

    rss_pool_value   = sum(rss_pool[r] * prices.get(r, 0) for r in RESOURCES)
    total_pool_value = cash_pool + rss_pool_value

    return {
        "projected_loot":      total_projected,
        "projected_cash":      proj_cash,
        "projected_resources": proj_rss,
        "proj_rss_value":      proj_rss_value,
        "previous_loot_value": 0.0,
        "remaining_loot":      0.0,
        "accumulated_rev":     0.0,
        "bankrec_net":         0.0,
        "cash_pool":           cash_pool,
        "rss_pool":            rss_pool,
        "rss_pool_value":      rss_pool_value,
        "total_pool_value":    total_pool_value,
        "rss_remaining":       {},
        "rss_looted":          {},
        "confidence":          confidence,
    }



# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user(request: Request) -> Optional[dict]:
    return request.session.get("discord_user")



async def _get_prices() -> Dict[str, float]:
    try:
        import Systems.Functions.database_manager as db_manager
        raw = await db_manager.get_latest_resource_prices()
        if not raw:
            return {}
        return {k.lower(): v.get("sell", 0) for k, v in raw.items() if v.get("sell", 0) > 0}
    except Exception as e:
        logger.error(f"Could not fetch prices: {e}")
        return {}


async def _fetch_all_nations_local(
    min_score: Optional[float],
    max_score: Optional[float],
) -> List[Dict[str, Any]]:
    """
    Fetch raid candidates from the local GlobalNations.db.
    Much faster than querying the PnW API — no network round-trips.
    Returns nations with their cities attached (needed for revenue calc).
    """
    from PnWHarvester.db.global_nations_db import GlobalNationsDB
    db = GlobalNationsDB(GLOBAL_NATIONS_DB_STR)

    try:
        import sqlite3
        async with db._lock:
            with sqlite3.connect(db.db_path) as conn:
                conn.row_factory = sqlite3.Row

                # Build score filter
                score_clause = ""
                params: list = []
                if min_score is not None and max_score is not None:
                    score_clause = "AND score BETWEEN ? AND ?"
                    params = [min_score, max_score]
                elif min_score is not None:
                    score_clause = "AND score >= ?"
                    params = [min_score]
                elif max_score is not None:
                    score_clause = "AND score <= ?"
                    params = [max_score]

                rows = conn.execute(
                    f"""SELECT * FROM nations
                        WHERE vacation_mode_turns = 0
                          AND nation_name IS NOT NULL
                          AND nation_name != ''
                          {score_clause}
                        ORDER BY score""",
                    params
                ).fetchall()

                nations = [dict(r) for r in rows]

                # Attach cities for revenue calculation
                if nations:
                    nation_ids = [n["id"] for n in nations]
                    # Fetch all cities for these nations in one query
                    placeholders = ",".join("?" * len(nation_ids))
                    city_rows = conn.execute(
                        f"SELECT * FROM cities WHERE nation_id IN ({placeholders})",
                        nation_ids
                    ).fetchall()

                    cities_by_nation: Dict[int, list] = {}
                    for cr in city_rows:
                        cd = dict(cr)
                        nid = cd["nation_id"]
                        cities_by_nation.setdefault(nid, []).append(cd)

                    for n in nations:
                        n["cities"] = cities_by_nation.get(n["id"], [])
                        # Wrap alliance info to match the API response shape
                        n["alliance"] = {
                            "id":   n.get("alliance_id"),
                            "name": n.get("alliance_name", "None"),
                        }

                return nations
    except Exception as e:
        logger.error(f"_fetch_all_nations_local error: {e}", exc_info=True)
        return []


# ── DB helpers for beige alerts ───────────────────────────────────────────────

def _compute_beige_expiry_utc(beige_turns: int, created_at: str) -> datetime:
    """
    Compute the exact UTC datetime when a nation's beige expires.

    PnW turn schedule:
      - Turn 0 (day change) fires at 00:00 UTC each day.
      - Subsequent turns fire every 2 hours: 02:00, 04:00, … 22:00 UTC.
      - So there are 12 turns per day, at hours 0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22.

    Algorithm:
      1. Find the most recent turn boundary at or before `created_at`.
      2. Add `beige_turns` × 2 hours to get the expiry turn boundary.
    """
    try:
        ref = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        # SQLite stores naive datetimes — treat them as UTC
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
    except Exception:
        ref = datetime.now(timezone.utc)

    # Snap ref back to the most recent 2-hour boundary (turn boundary)
    hour_snapped = (ref.hour // 2) * 2
    last_turn = ref.replace(hour=hour_snapped, minute=0, second=0, microsecond=0)

    # Expiry = last_turn + beige_turns * 2 hours
    expiry = last_turn + timedelta(hours=beige_turns * 2)
    return expiry


async def _ensure_beige_table():
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS beige_alerts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         TEXT    NOT NULL,
                nation_id       TEXT    NOT NULL,
                nation_name     TEXT    NOT NULL,
                beige_turns     INTEGER NOT NULL,
                projected_loot  REAL    NOT NULL DEFAULT 0,
                accumulated_rev REAL    NOT NULL DEFAULT 0,
                warned_turn     INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                UNIQUE(user_id, nation_id)
            )
        """)
        # Migrate existing tables that lack columns
        for col, definition in [
            ("projected_loot",  "REAL NOT NULL DEFAULT 0"),
            ("accumulated_rev", "REAL NOT NULL DEFAULT 0"),
            ("warned_turn",     "INTEGER NOT NULL DEFAULT 0"),
        ]:
            try:
                await conn.execute(f"ALTER TABLE beige_alerts ADD COLUMN {col} {definition}")
            except Exception:
                pass  # column already exists
        await conn.commit()


async def _get_beige_alerts_for_user(user_id: str) -> List[dict]:
    await _ensure_beige_table()
    async with aiosqlite.connect(ALERTS_DB) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM beige_alerts WHERE user_id=? ORDER BY beige_turns ASC",
            (user_id,)
        )
        rows = [dict(r) for r in await cur.fetchall()]

    # Attach computed expiry timestamp (ISO UTC) for the frontend countdown
    now = datetime.now(timezone.utc)
    for row in rows:
        expiry = _compute_beige_expiry_utc(int(row.get("beige_turns") or 0), row.get("created_at") or "")
        row["expiry_utc"] = expiry.isoformat()
        # Remaining seconds (can be negative if already expired)
        row["seconds_remaining"] = int((expiry - now).total_seconds())

    return rows


async def _upsert_beige_alert(user_id: str, nation_id: str, nation_name: str, beige_turns: int, projected_loot: float = 0.0, accumulated_rev: float = 0.0):
    await _ensure_beige_table()
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("""
            INSERT INTO beige_alerts (user_id, nation_id, nation_name, beige_turns, projected_loot, accumulated_rev)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, nation_id)
            DO UPDATE SET nation_name=excluded.nation_name, beige_turns=excluded.beige_turns,
                          projected_loot=excluded.projected_loot, accumulated_rev=excluded.accumulated_rev,
                          warned_turn=0,
                          created_at=datetime('now')
        """, (user_id, nation_id, nation_name, beige_turns, projected_loot, accumulated_rev))
        await conn.commit()


async def _delete_beige_alert(user_id: str, nation_id: str) -> bool:
    await _ensure_beige_table()
    async with aiosqlite.connect(ALERTS_DB) as conn:
        cur = await conn.execute(
            "DELETE FROM beige_alerts WHERE user_id=? AND nation_id=?",
            (user_id, nation_id)
        )
        await conn.commit()
        return cur.rowcount > 0


async def _get_all_beige_alerts() -> List[dict]:
    await _ensure_beige_table()
    async with aiosqlite.connect(ALERTS_DB) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM beige_alerts")
        return [dict(r) for r in await cur.fetchall()]


async def _delete_beige_alert_by_id(alert_id: int):
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("DELETE FROM beige_alerts WHERE id=?", (alert_id,))
        await conn.commit()


async def _mark_beige_alert_warned(alert_id: int):
    """Mark that the 1-turn (2-hour) warning has been sent for this alert."""
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("UPDATE beige_alerts SET warned_turn=1 WHERE id=?", (alert_id,))
        await conn.commit()


async def _update_beige_alert_turns(alert_id: int, beige_turns: int):
    """Refresh the stored beige_turns and reset the created_at anchor so that
    _compute_beige_expiry_utc continues to produce an accurate expiry time as
    turns tick down."""
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute(
            "UPDATE beige_alerts SET beige_turns=?, created_at=datetime('now') WHERE id=?",
            (beige_turns, alert_id)
        )
        await conn.commit()


async def _calc_with_data(
    n: Dict[str, Any],
    holdings_map: Dict[int, Dict[str, Any]],
    attacker_has_ape: bool,
    prices: Dict[str, float],
) -> tuple:
    """
    Calculate loot for a single nation using pre-fetched holdings data.
    No DB I/O — holdings_map is already loaded.
    """
    nation_id = int(n.get("id"))
    holdings  = holdings_map.get(nation_id)
    return n, await _calculate_loot(n, attacker_has_ape, prices, holdings=holdings)


# ── Main search endpoint ──────────────────────────────────────────────────────

@router.get("/raids/search")
async def raids_search(
    request:    Request,
    nation:     Optional[str]  = None,
    active:     bool           = True,
    weak:       bool           = False,
    min_loot:   Optional[str]  = None,
    beige:      bool           = False,
    targets:    int            = 50,
):
    """Run the raid target search and return JSON results."""
    await _require_access(request)
    try:
        attacker = None
        attacker_has_ape = False
        min_score = max_score = None

        if nation:
            from PnWHarvester.db.global_nations_db import GlobalNationsDB
            global_db = GlobalNationsDB(GLOBAL_NATIONS_DB_STR)
            clean = nation.strip().lower()
            # Try exact name match first, then ID
            if clean.isdigit():
                attacker = await global_db.get_nation(int(clean))
            else:
                attacker = await global_db.get_nation_by_name(clean)
            if attacker:
                attacker_has_ape = bool(attacker.get("advanced_pirate_economy", False))
                score = float(attacker.get("score", 0))
                if score > 0:
                    min_score = score * WAR_RANGE_MIN
                    max_score = score * WAR_RANGE_MAX

        min_loot_val = _parse_loot_str(min_loot)
        prices       = await _get_prices()
        all_nations  = await _fetch_all_nations_local(min_score, max_score)

        # ── Pre-filter: cheap checks before the expensive loot calculation ────
        candidates = []
        for n in all_nations:
            if n.get("vacation_mode_turns", 0) > 0:
                continue
            if attacker:
                a_score = float(attacker.get("score", 0))
                d_score = float(n.get("score", 0))
                if a_score > 0:
                    ratio = d_score / a_score
                    if not (WAR_RANGE_MIN <= ratio <= WAR_RANGE_MAX):
                        continue
                if weak:
                    a_str = _military_strength(attacker)
                    d_str = _military_strength(n)
                    if n.get("iron_dome"):
                        d_str *= 1.1
                    if n.get("vital_defense_system"):
                        d_str *= 1.15
                    if d_str >= a_str:
                        continue
            if active and _is_inactive(n):
                continue
            if not beige and (n.get("beige_turns", 0) or 0) > 0:
                continue
            if (n.get("defensive_wars_count", 0) or 0) >= 3:
                continue
            # "Lost last war" check — use loot.db: if we have a loot event for this
            # nation it means they were looted (lost), so they're a valid target.
            # Nations with no loot record are included (we don't know their war history).
            candidates.append(n)

        # ── Bulk-fetch holdings (1 query, not N×2) ───────────────────────────
        from PnWHarvester.db.holdings_db import HoldingsDB
        from Systems.Functions.db_paths  import HOLDINGS_DB_STR

        _holdings_db  = HoldingsDB(HOLDINGS_DB_STR)
        candidate_ids = [int(n["id"]) for n in candidates]
        holdings_map  = await _holdings_db.get_holdings_bulk(candidate_ids)

        # Attach pre-fetched holdings and calculate loot — pure CPU, no more I/O
        loot_results = await asyncio.gather(*[
            _calc_with_data(n, holdings_map, attacker_has_ape, prices)
            for n in candidates
        ])

        # Build a lightweight AllianceCalculator for unit limit lookups
        from Systems.PnW.Util.calc import AllianceCalculator
        from Systems.PnW.Util.query import create_v3_query_instance
        _calc = AllianceCalculator(create_v3_query_instance())

        results = []
        for n, loot_data in loot_results:
            proj        = loot_data["projected_loot"]
            total_est   = proj
            if total_est < min_loot_val:
                continue

            # Per-nation unit limits (daily purchase + max capacity)
            try:
                unit_limits = _calc.calculate_military_purchase_limits(n)
            except Exception:
                unit_limits = {
                    "soldiers_daily": 0, "tanks_daily": 0,
                    "aircraft_daily": 0, "ships_daily": 0,
                    "soldiers_max": 0, "tanks_max": 0,
                    "aircraft_max": 0, "ships_max": 0,
                }

            results.append({
                "id":            n.get("id"),
                "nation_name":   n.get("nation_name"),
                "leader_name":   n.get("leader_name"),
                "score":         n.get("score"),
                "num_cities":    n.get("num_cities"),
                "soldiers":      n.get("soldiers", 0),
                "tanks":         n.get("tanks", 0),
                "aircraft":      n.get("aircraft", 0),
                "ships":         n.get("ships", 0),
                "missiles":      n.get("missiles", 0),
                "nukes":         n.get("nukes", 0),
                "beige_turns":   n.get("beige_turns", 0),
                "war_policy":    n.get("war_policy"),
                "alliance_name": (n.get("alliance") or {}).get("name") or n.get("alliance_name") or "None",
                "alliance_id":   (n.get("alliance") or {}).get("id") or n.get("alliance_id"),
                "missile_launch_pad":         bool(n.get("missile_launch_pad")),
                "space_program":              bool(n.get("space_program")),
                "nuclear_research_facility":  bool(n.get("nuclear_research_facility")),
                "nuclear_launch_facility":    bool(n.get("nuclear_launch_facility")),
                "iron_dome":                  bool(n.get("iron_dome")),
                "vital_defense_system":       bool(n.get("vital_defense_system")),
                "projected_loot":      proj,
                "projected_cash":      loot_data.get("projected_cash", 0),
                "projected_resources": loot_data.get("projected_resources", {}),
                "proj_rss_value":      loot_data.get("proj_rss_value", 0),
                "accumulated_rev":     loot_data["accumulated_rev"],
                "remaining_loot":      loot_data["remaining_loot"],
                "bankrec_net":         loot_data["bankrec_net"],
                "cash_pool":           loot_data.get("cash_pool", 0),
                "rss_pool":            loot_data.get("rss_pool", {}),
                "rss_pool_value":      loot_data.get("rss_pool_value", 0),
                "total_pool_value":    loot_data.get("total_pool_value", 0),
                "total_est_loot":      total_est,
                "prev_loot_value":     loot_data["previous_loot_value"],
                "last_active":         n.get("last_active"),
                # Unit limits for the Units box
                "soldiers_daily":  unit_limits.get("soldiers_daily", 0),
                "tanks_daily":     unit_limits.get("tanks_daily", 0),
                "aircraft_daily":  unit_limits.get("aircraft_daily", 0),
                "ships_daily":     unit_limits.get("ships_daily", 0),
                "soldiers_max":    unit_limits.get("soldiers_max", 0),
                "tanks_max":       unit_limits.get("tanks_max", 0),
                "aircraft_max":    unit_limits.get("aircraft_max", 0),
                "ships_max":       unit_limits.get("ships_max", 0),
            })

        results.sort(key=lambda x: x["total_est_loot"], reverse=True)
        return JSONResponse({"ok": True, "results": results[:targets]})

    except Exception as e:
        logger.error(f"raids_search error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── Beige alert endpoints ─────────────────────────────────────────────────────

class BeigeAlertPayload(BaseModel):
    nation_id:      str
    nation_name:    str
    beige_turns:    int
    projected_loot: float = 0.0
    accumulated_rev: float = 0.0


@router.get("/raids/beige-alerts")
async def get_beige_alerts(request: Request):
    user = _get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in.")
    await _require_access(request)
    alerts = await _get_beige_alerts_for_user(str(user["id"]))
    return JSONResponse(alerts)


@router.post("/raids/beige-alerts")
async def add_beige_alert(request: Request, payload: BeigeAlertPayload):
    user = _get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in.")
    await _require_access(request)
    await _upsert_beige_alert(
        str(user["id"]), payload.nation_id, payload.nation_name,
        payload.beige_turns, payload.projected_loot, payload.accumulated_rev,
    )
    logger.info(
        f"Beige alert set: user={user['id']} nation={payload.nation_id} "
        f"({payload.nation_name}) turns={payload.beige_turns} "
        f"loot=${payload.projected_loot:,.0f} rev=${payload.accumulated_rev:,.0f}"
    )
    return JSONResponse({"ok": True})


@router.delete("/raids/beige-alerts/{nation_id}")
async def remove_beige_alert(request: Request, nation_id: str):
    user = _get_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in.")
    await _require_access(request)
    removed = await _delete_beige_alert(str(user["id"]), nation_id)
    return JSONResponse({"ok": removed})


# ── NW nation autocomplete for the nation field ───────────────────────────────

@router.get("/raids/nations_ac")
async def raids_nations_ac(request: Request, q: str = ""):
    await _require_access(request)
    try:
        from PnWHarvester.db.global_nations_db import GlobalNationsDB

        db  = GlobalNationsDB(GLOBAL_NATIONS_DB_STR)
        low = q.strip().lower()

        if low:
            rows = await db.search_nations(low, limit=25)
            out = [
                {"id": r["id"], "nation_name": r["nation_name"], "leader_name": r.get("leader_name", "")}
                for r in rows
                if r.get("nation_name")
            ]
        else:
            # No query — return NW nations sorted by score as default suggestions
            all_nations = await db.get_nations_by_alliance(14225)
            out = [
                {"id": n["id"], "nation_name": n["nation_name"], "leader_name": n.get("leader_name", "")}
                for n in all_nations
                if n.get("nation_name")
            ]

        return JSONResponse(out)
    except Exception as e:
        logger.error(f"raids_nations_ac error: {e}", exc_info=True)
        return JSONResponse([])

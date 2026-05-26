"""
NewsAPI — FastAPI endpoints for the PnW News page.

Endpoints:
  GET /news/events          — paginated event feed
  GET /news/alliance-stats  — alliance leaderboard
  GET /news/nation-stats    — nation leaderboard
  GET /news/meta            — period metadata (start date, event count)
  GET /news/years           — available yearly DB years
  GET /news/available       — which prev DBs exist + available years
  GET /news/summary         — high-level summary for dashboard cards

Query params:
  period   : "weekly" | "prev_weekly" | "monthly" | "prev_monthly" | "yearly"
  year     : int (only for period=yearly)
  scope    : "nw" | "world"  (default: world — NW = alliance_id=10259 only)
  type     : comma-separated event types to filter
  limit    : int (default 100, max 500)
  offset   : int (default 0)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

router = APIRouter()
logger = logging.getLogger("Reaper.WebServer.NewsAPI")

NW_ALLIANCE_ID = 10259

_VALID_PERIODS = {"weekly", "prev_weekly", "monthly", "prev_monthly", "yearly"}

# ── Lazy DB singleton ─────────────────────────────────────────────────────────
_news_db = None

def _get_db():
    global _news_db
    if _news_db is None:
        try:
            from PnWHarvester.db.news_db import get_news_db
            _news_db = get_news_db()
        except Exception as e:
            logger.error(f"NewsAPI: failed to load NewsDB: {e}", exc_info=True)
    return _news_db


def _clamp(val: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, val))


def _validate_period(period: str) -> str:
    return period if period in _VALID_PERIODS else "weekly"


# ── Events feed ───────────────────────────────────────────────────────────────

@router.get("/news/events")
async def get_news_events(
    period: str = Query("weekly"),
    year: Optional[int] = Query(None),
    scope: str = Query("world"),   # "nw" | "world"  — default ALL events
    type: Optional[str] = Query(None),
    nation_id: Optional[int] = Query(None),
    filter_alliance_id: Optional[int] = Query(None, alias="filter_alliance_id"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    db = _get_db()
    if db is None:
        return JSONResponse({"events": [], "error": "News database unavailable"}, status_code=503)

    event_types = [t.strip() for t in type.split(",")] if type else None
    # scope param is ignored — always world (all alliances)
    # filter_alliance_id is the explicit search-bar filter
    if filter_alliance_id:
        alliance_id = filter_alliance_id
    else:
        alliance_id = None  # no filter = all events

    try:
        events = db.get_events(
            period=_validate_period(period),
            year=year,
            event_types=event_types,
            alliance_id=alliance_id,
            nation_id=nation_id,
            limit=_clamp(limit, 1, 500),
            offset=offset,
        )
        # Include period meta so the frontend can show the true total event count
        meta = db.get_period_meta(period=_validate_period(period), year=year)
        return JSONResponse({"events": events, "count": len(events), "meta": meta})
    except Exception as e:
        logger.error(f"get_news_events: {e}", exc_info=True)
        return JSONResponse({"events": [], "error": str(e)}, status_code=500)


# ── Alliance stats leaderboard ────────────────────────────────────────────────

@router.get("/news/alliance-stats")
async def get_news_alliance_stats(
    period: str = Query("weekly"),
    year: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    db = _get_db()
    if db is None:
        return JSONResponse({"alliances": [], "error": "News database unavailable"}, status_code=503)

    try:
        stats = db.get_alliance_stats(
            period=_validate_period(period),
            year=year,
            alliance_id=None,   # always world — no scope filter
            limit=_clamp(limit, 1, 200),
        )
        return JSONResponse({"alliances": stats, "count": len(stats)})
    except Exception as e:
        logger.error(f"get_news_alliance_stats: {e}", exc_info=True)
        return JSONResponse({"alliances": [], "error": str(e)}, status_code=500)


# ── Nation stats leaderboard ──────────────────────────────────────────────────

@router.get("/news/nation-stats")
async def get_news_nation_stats(
    period: str = Query("weekly"),
    year: Optional[int] = Query(None),
    alliance_id: Optional[int] = Query(None),
    nation_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    db = _get_db()
    if db is None:
        return JSONResponse({"nations": [], "error": "News database unavailable"}, status_code=503)

    # Support filtering by alliance_id or nation_id
    try:
        stats = db.get_nation_stats(
            period=_validate_period(period),
            year=year,
            alliance_id=alliance_id,
            nation_id=nation_id,
            limit=_clamp(limit, 1, 500),
        )
        return JSONResponse({"nations": stats, "count": len(stats)})
    except Exception as e:
        logger.error(f"get_news_nation_stats: {e}", exc_info=True)
        return JSONResponse({"nations": [], "error": str(e)}, status_code=500)


# ── Period metadata ───────────────────────────────────────────────────────────

@router.get("/news/meta")
async def get_news_meta(
    period: str = Query("weekly"),
    year: Optional[int] = Query(None),
):
    db = _get_db()
    if db is None:
        return JSONResponse({"error": "News database unavailable"}, status_code=503)

    try:
        meta = db.get_period_meta(period=_validate_period(period), year=year)
        years = db.get_available_years()
        return JSONResponse({"meta": meta, "available_years": years})
    except Exception as e:
        logger.error(f"get_news_meta: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Available periods (which prev DBs exist) ──────────────────────────────────

@router.get("/news/available")
async def get_news_available():
    """Returns which prev DBs exist and available yearly DBs."""
    db = _get_db()
    if db is None:
        return JSONResponse({"error": "News database unavailable"}, status_code=503)
    try:
        return JSONResponse(db.get_available_periods())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Available years ───────────────────────────────────────────────────────────

@router.get("/news/years")
async def get_news_years():
    db = _get_db()
    if db is None:
        return JSONResponse({"years": []})
    try:
        return JSONResponse({"years": db.get_available_years()})
    except Exception as e:
        return JSONResponse({"years": [], "error": str(e)})


# ── Name resolver ─────────────────────────────────────────────────────────────

@router.get("/news/resolve-names")
async def resolve_names(
    nation_ids: Optional[str] = Query(None),    # comma-separated nation IDs
    alliance_ids: Optional[str] = Query(None),  # comma-separated alliance IDs
):
    """
    Resolve nation and alliance IDs to names from GlobalNations.db.
    Returns { nations: {id: {name, alliance_id, alliance_name}}, alliances: {id: name} }
    Used by the news page to replace "Nation #ID" / "Alliance #ID" tokens with real names.
    """
    import sqlite3
    from Systems.Functions.db_paths import GLOBAL_NATIONS_DB_STR

    n_ids = [int(x) for x in nation_ids.split(",") if x.strip().isdigit()] if nation_ids else []
    a_ids = [int(x) for x in alliance_ids.split(",") if x.strip().isdigit()] if alliance_ids else []

    nations_map: Dict[str, Any] = {}
    alliances_map: Dict[str, str] = {}

    if not n_ids and not a_ids:
        return JSONResponse({"nations": {}, "alliances": {}})

    try:
        conn = sqlite3.connect(GLOBAL_NATIONS_DB_STR)
        conn.row_factory = sqlite3.Row

        if n_ids:
            ph = ",".join("?" * len(n_ids))
            rows = conn.execute(
                f"SELECT id, nation_name, alliance_id, alliance_name FROM nations WHERE id IN ({ph})",
                n_ids
            ).fetchall()
            for row in rows:
                nations_map[str(row["id"])] = {
                    "name":          row["nation_name"],
                    "alliance_id":   row["alliance_id"],
                    "alliance_name": row["alliance_name"],
                }
                # Also populate alliances_map from nation rows (saves a separate query)
                if row["alliance_id"] and row["alliance_name"]:
                    alliances_map[str(row["alliance_id"])] = row["alliance_name"]

        if a_ids:
            # Fill any alliance IDs not already resolved from nation rows
            missing_a = [aid for aid in a_ids if str(aid) not in alliances_map]
            if missing_a:
                ph = ",".join("?" * len(missing_a))
                rows = conn.execute(
                    f"SELECT DISTINCT alliance_id, alliance_name FROM nations "
                    f"WHERE alliance_id IN ({ph}) AND alliance_name IS NOT NULL",
                    missing_a
                ).fetchall()
                for row in rows:
                    alliances_map[str(row["alliance_id"])] = row["alliance_name"]

        conn.close()
    except Exception as e:
        logger.error(f"resolve_names: {e}", exc_info=True)
        return JSONResponse({"nations": {}, "alliances": {}, "error": str(e)}, status_code=500)

    return JSONResponse({"nations": nations_map, "alliances": alliances_map})


@router.get("/news/summary")
async def get_news_summary(
    period: str = Query("weekly"),
    year: Optional[int] = Query(None),
):
    """Returns high-level summary numbers for the news page header cards."""
    db = _get_db()
    if db is None:
        return JSONResponse({"error": "News database unavailable"}, status_code=503)

    p = _validate_period(period)

    try:
        # World stats = all alliances (no filter)
        world_stats = db.get_alliance_stats(period=p, year=year, limit=500)

        world_totals: Dict[str, Any] = {
            "cities_built":    sum(a.get("cities_built", 0)    for a in world_stats),
            "projects_bought": sum(a.get("projects_bought", 0) for a in world_stats),
            "total_spent":     sum(a.get("total_spent", 0)     for a in world_stats),
            "wars_declared":   sum(a.get("wars_declared", 0)   for a in world_stats),
            "wars_won":        sum(a.get("wars_won", 0)        for a in world_stats),
            "loot_gained":     sum(a.get("loot_gained", 0)     for a in world_stats),
            "nukes_used":      sum(a.get("nukes_used", 0)      for a in world_stats),
            "missiles_used":   sum(a.get("missiles_used", 0)   for a in world_stats),
            "alliance_count":  len(world_stats),
        }

        meta = db.get_period_meta(period=p, year=year)
        available = db.get_available_periods()

        return JSONResponse({
            "world":    world_totals,
            "meta":     meta,
            "period":   p,
            "available": available,
        })
    except Exception as e:
        logger.error(f"get_news_summary: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Search: nations + alliances from GlobalNations.db ────────────────────────

@router.get("/news/search")
async def news_search(q: str = Query("", min_length=0)):
    """
    Live search across ALL nations and alliances in GlobalNations.db.
    Returns up to 10 nations and 10 alliances matching the query.
    Response: { nations: [{id, name, alliance_name, flag}], alliances: [{id, name, flag}] }
    """
    import sqlite3
    from Systems.Functions.db_paths import GLOBAL_NATIONS_DB_STR

    query = (q or "").strip()
    if not query:
        return JSONResponse({"nations": [], "alliances": []})

    like = f"%{query}%"
    try:
        conn = sqlite3.connect(GLOBAL_NATIONS_DB_STR)
        conn.execute("PRAGMA query_only=1")
        conn.row_factory = sqlite3.Row

        # Nations: match by nation_name, ordered by score desc
        nation_rows = conn.execute(
            """
            SELECT id, nation_name, alliance_id, alliance_name, flag
            FROM nations
            WHERE nation_name LIKE ?
              AND nation_name IS NOT NULL AND nation_name != ''
            ORDER BY score DESC
            LIMIT 10
            """,
            (like,)
        ).fetchall()

        # Alliances: one row per alliance_id, match by alliance_name
        alliance_rows = conn.execute(
            """
            SELECT alliance_id, alliance_name, alliance_flag,
                   COUNT(*) as member_count
            FROM nations
            WHERE alliance_name LIKE ?
              AND alliance_id IS NOT NULL AND alliance_id != 0
              AND alliance_name IS NOT NULL AND alliance_name != ''
              AND alliance_name != '0'
            GROUP BY alliance_id
            ORDER BY member_count DESC
            LIMIT 10
            """,
            (like,)
        ).fetchall()

        conn.close()

        nations = [
            {
                "id":            r["id"],
                "name":          r["nation_name"],
                "alliance_name": r["alliance_name"] or "",
                "flag":          r["flag"] or None,
            }
            for r in nation_rows
        ]
        alliances = [
            {
                "id":   r["alliance_id"],
                "name": r["alliance_name"],
                "flag": r["alliance_flag"] or None,
            }
            for r in alliance_rows
        ]
        return JSONResponse({"nations": nations, "alliances": alliances})
    except Exception as e:
        logger.error(f"news_search: {e}", exc_info=True)
        return JSONResponse({"nations": [], "alliances": [], "error": str(e)}, status_code=500)


# ── Single-war cost breakdown (NW wars only) ──────────────────────────────────

@router.get("/news/resource-prices")
async def get_news_resource_prices():
    """
    Returns current best-sell resource prices from the DB cache.
    Used by the news page to show per-resource loot value breakdowns.
    Response: { prices: { coal: 1234, oil: 2345, ... }, timestamp: "..." }
    """
    try:
        import sqlite3
        from Systems.Functions.db_paths import REAPER_DB_STR
        conn = sqlite3.connect(REAPER_DB_STR)
        rows = conn.execute(
            """
            SELECT resource, best_sell_price FROM resource_prices
            WHERE timestamp = (SELECT MAX(timestamp) FROM resource_prices)
            """
        ).fetchall()
        ts_row = conn.execute(
            "SELECT MAX(timestamp) FROM resource_prices"
        ).fetchone()
        conn.close()
        prices = {r.lower(): float(p) for r, p in rows if p and float(p) > 0} if rows else {}
        return JSONResponse({"prices": prices, "timestamp": ts_row[0] if ts_row else None})
    except Exception as e:
        logger.error(f"get_news_resource_prices: {e}", exc_info=True)
        # Return fallback prices so the page still works
        return JSONResponse({
            "prices": {
                "coal": 2000, "oil": 2000, "uranium": 4000, "iron": 2000,
                "bauxite": 2000, "lead": 2000, "gasoline": 3000, "munitions": 2000,
                "steel": 3000, "aluminum": 2000, "food": 150,
            },
            "timestamp": None,
            "fallback": True,
        })


@router.get("/news/war-costs/{war_id}")
async def get_news_war_costs(war_id: int):
    """
    Returns cost breakdown for both sides of a single NW war.
    Used by the news feed to show war costs when toggled on a war_ended event.
    """
    try:
        from Systems.Functions.irs_wars_db import IRSWarsDB
        from Systems.Functions.db_paths import IRS_WARS_DB_STR
        from Systems.PnW.Util.war_calc import get_resource_prices, calculate_war_costs
        from web.api.watch_api import _attach_war_attacks, _normalize_attack

        db = IRSWarsDB(IRS_WARS_DB_STR)
        war = await db.get_war(war_id)
        if not war:
            return JSONResponse({"error": f"War {war_id} not found in IRS database"}, status_code=404)

        resource_prices = await get_resource_prices()

        # Attach attacks so calculate_war_costs has full data
        wars_with_attacks = await _attach_war_attacks(db, [war])
        war_data = wars_with_attacks[0]

        att_id = war_data.get("att_id")
        def_id = war_data.get("def_id")

        team1_id_set = {int(att_id)} if att_id else None
        team2_id_set = {int(def_id)} if def_id else None

        costs = await calculate_war_costs(
            [war_data], resource_prices,
            team1_id_set=team1_id_set,
            team2_id_set=team2_id_set,
        )

        def _fmt_side(side_costs: dict) -> dict:
            """Flatten the nested cost dict into a simple display-friendly structure."""
            if not side_costs:
                return {}
            units = side_costs.get("units", {})
            return {
                "gross_cost":        side_costs.get("gross", 0),
                "net_damage":        side_costs.get("net", 0),
                "infra_lost_value":  side_costs.get("infra_lost_value", 0),
                "infra_lost_levels": side_costs.get("infra_lost_levels", 0),
                "units_cost":        side_costs.get("units_cost", 0),
                "soldiers_lost":     (units.get("soldiers") or {}).get("lost", 0),
                "tanks_lost":        (units.get("tanks")    or {}).get("lost", 0),
                "aircraft_lost":     (units.get("aircraft") or {}).get("lost", 0),
                "ships_lost":        (units.get("ships")    or {}).get("lost", 0),
                "missiles_lost":     (units.get("missiles") or {}).get("lost", 0),
                "nukes_lost":        (units.get("nukes")    or {}).get("lost", 0),
                "gas_used":          side_costs.get("gas_used", 0),
                "mun_used":          side_costs.get("mun_used", 0),
                "loot_net":          side_costs.get("loot_net", 0),
            }

        return JSONResponse({
            "war_id":    war_id,
            "att_id":    att_id,
            "def_id":    def_id,
            "att_name":  war_data.get("att_nation_name") or war_data.get("att_name", f"Nation #{att_id}"),
            "def_name":  war_data.get("def_nation_name") or war_data.get("def_name", f"Nation #{def_id}"),
            "attacker":  _fmt_side(costs.get("team1", {})),
            "defender":  _fmt_side(costs.get("team2", {})),
        })
    except Exception as e:
        logger.error(f"get_news_war_costs({war_id}): {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

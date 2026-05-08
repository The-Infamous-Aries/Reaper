"""Rev Optimizer API — runs analyze_revenue for a nation or all nations in an alliance."""

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
import asyncio
import logging
import math
from typing import Optional

from Systems.PnW.EA.rev_optimizer import analyze_revenue
from Systems.PnW.Util.rev_correct import calculate_nation_modifiers
from PnWHarvester.db.global_nations_db import GlobalNationsDB
from Systems.Functions.db_paths import (
    GLOBAL_NATIONS_DB as GLOBAL_NATIONS_DB_PATH,
)
from Systems.PnW.Util.query import create_v3_query_instance
from Systems.Functions.database_manager import (
    get_latest_resource_prices, get_latest_game_data,
    get_latest_game_info, get_latest_radiation_data,
)

router = APIRouter()
logger = logging.getLogger("Reaper.WebServer.RevOptimizerAPI")
WATCH_ALLIANCE_ID = 14225
EP_KEYWORDS = {"nights watch", "nightswatch", "nw", str(WATCH_ALLIANCE_ID)}


def _clean(v):
    if isinstance(v, float):
        if math.isinf(v) or math.isnan(v):
            return None
    return v


def _clean_suggestion(s: dict) -> dict:
    return {k: _clean(v) for k, v in s.items()}


async def _load_game_context() -> dict:
    prices = {}
    try:
        pd = await get_latest_resource_prices()
        if pd:
            prices = {r: p['sell'] for r, p in pd.items()}
    except Exception:
        pass

    colors = {}
    try:
        cd = await get_latest_game_data("colors")
        if cd:
            colors = {c['color'].lower(): float(c.get('turn_bonus', 0)) for c in cd}
    except Exception:
        pass

    radiation = {k: 0.0 for k in ('na', 'sa', 'eu', 'as', 'af', 'au', 'an')}
    try:
        rd = await get_latest_radiation_data()
        if rd:
            g = rd.get('global', 0)
            for k, rk in [('na', 'north_america'), ('sa', 'south_america'), ('eu', 'europe'),
                           ('as', 'asia'), ('af', 'africa'), ('au', 'australia'), ('an', 'antarctica')]:
                radiation[k] = (rd.get(rk, 0) + g) / -1000
    except Exception:
        pass

    seasonal_mod = {'na': 1, 'sa': 1, 'eu': 1, 'as': 1, 'af': 1, 'au': 1, 'an': 0.5}
    try:
        gi = await get_latest_game_info()
        if gi and gi.get('game_date'):
            month = int(gi['game_date'][5:7])
            if month in (6, 7, 8):
                seasonal_mod.update({'na': 1.2, 'as': 1.2, 'eu': 1.2, 'sa': 0.8, 'af': 0.8, 'au': 0.8})
            elif month in (12, 1, 2):
                seasonal_mod.update({'na': 0.8, 'as': 0.8, 'eu': 0.8, 'sa': 1.2, 'af': 1.2, 'au': 1.2})
    except Exception:
        pass

    return {'prices': prices, 'colors': colors, 'radiation': radiation, 'seasonal_mod': seasonal_mod}


def _serialize_result(nation: dict, result: dict, prices: dict) -> dict:
    modifiers = calculate_nation_modifiers(nation)
    city_analyses = []
    for ca in result.get('city_analyses', []):
        city_analyses.append({
            'name':  ca['name'],
            'infra': ca['infra'],
            'land':  ca['land'],
            'stats': {k: _clean(v) for k, v in ca['stats'].items()},
            'suggestions': [_clean_suggestion(s) for s in ca['suggestions']],
        })

    return {
        'nation_id':        nation.get('id'),
        'nation_name':      nation.get('nation_name', 'Unknown'),
        'leader_name':      nation.get('leader_name', ''),
        'flag':             nation.get('flag', ''),
        'num_cities':       nation.get('num_cities', 0),
        'current_net':      _clean(result.get('current_net', 0)),
        'current_monetary': _clean(result.get('current_monetary', 0)),
        'max_commerce':     modifiers.get('max_commerce', 100),
        'city_analyses':    city_analyses,
        'project_suggestions': [_clean_suggestion(p) for p in result.get('project_suggestions', [])],
        'top_suggestions':  [_clean_suggestion(s) for s in result.get('top_suggestions', [])[:20]],
        'prices':           prices,
    }


def _global_db() -> GlobalNationsDB:
    return GlobalNationsDB(str(GLOBAL_NATIONS_DB_PATH))


async def _get_nation_with_cities(query: str, query_instance) -> Optional[dict]:
    """
    Fetch nation + cities, checking GlobalNations.db first (single source of truth
    for all nations including Nights Watch), then falling back to the live PnW API.
    """
    clean = query.strip()

    # ── 1. GlobalNations.db (all game nations, including NW) ───────────────
    if GLOBAL_NATIONS_DB_PATH.exists():
        try:
            gdb = _global_db()
            n = (await gdb.get_nation(int(clean))
                 if clean.isdigit()
                 else await gdb.get_nation_by_name(clean))
            if n:
                n['cities'] = await gdb.get_cities_for_nation(int(n['id']))
                if n['cities']:
                    return n
        except Exception as e:
            logger.warning(f"GlobalNationsDB lookup failed for '{clean}': {e}")

    # ── 2. Live PnW API fallback ───────────────────────────────────────────
    try:
        n = (await query_instance.get_nation_by_id(clean)
             if clean.isdigit()
             else await query_instance.get_nation_by_name(clean))
        return n
    except Exception as e:
        logger.error(f"API lookup failed for '{clean}': {e}")
        return None


def _run_analyze_revenue(nation: dict, prices: dict, colors: dict, seasonal_mod: dict, radiation: dict) -> dict:
    """Synchronous wrapper — runs in a thread to avoid blocking the event loop."""
    return analyze_revenue(
        nation=nation,
        prices=prices,
        colors=colors,
        seasonal_mod=seasonal_mod,
        radiation=radiation,
        treasures=[],
    )


@router.get("/revopt/ep_nations")
async def get_ep_nations():
    """Return a lightweight list of NW (Nights Watch) nations for the frontend dropdown."""
    try:
        db = _global_db()
        nations = await db.get_nations_by_alliance(WATCH_ALLIANCE_ID)
        return [
            {'id': n.get('id'), 'nation_name': n.get('nation_name', ''), 'leader_name': n.get('leader_name', '')}
            for n in nations if n.get('nation_name')
        ]
    except Exception as e:
        logger.error(f"ep_nations error: {e}")
        return []


@router.get("/revopt/analyze")
async def rev_opt_analyze(
    query: str = Query(..., description="Nation name/ID or alliance name/ID"),
    type: str = Query("auto", description="'nation', 'alliance', or 'auto'"),
    refresh: bool = Query(False),
):
    """
    Run the full revenue optimizer for a nation or every nation in an alliance.
    Returns a list of nation result objects.
    """
    try:
        ctx = await _load_game_context()
        prices = ctx['prices']
        qi = create_v3_query_instance()

        q = query.strip()
        is_alliance = False

        # ── Determine if this is an alliance query ─────────────────────────
        if type == 'alliance':
            is_alliance = True
        elif type == 'auto':
            if q.lower() in EP_KEYWORDS or q.lower().startswith('alliance:'):
                is_alliance = True
                q = q.replace('alliance:', '').strip()

        # ── Alliance path ──────────────────────────────────────────────────
        if is_alliance:
            nations = []

            # Resolve alliance_id: NW keywords → hardcoded ID, else look up in GlobalNations.db
            alliance_id_to_fetch = None
            if q.lower() in EP_KEYWORDS or q == str(WATCH_ALLIANCE_ID):
                alliance_id_to_fetch = WATCH_ALLIANCE_ID
            elif q.isdigit():
                alliance_id_to_fetch = int(q)

            # Try GlobalNations.db first
            if GLOBAL_NATIONS_DB_PATH.exists():
                try:
                    gdb = _global_db()
                    if alliance_id_to_fetch is None:
                        # Resolve alliance name → ID
                        alliances = await gdb.get_distinct_alliances(q)
                        for a in alliances:
                            if (a.get('alliance_name') or '').lower() == q.lower():
                                alliance_id_to_fetch = a['alliance_id']
                                break
                        if alliance_id_to_fetch is None and alliances:
                            alliance_id_to_fetch = alliances[0]['alliance_id']

                    if alliance_id_to_fetch:
                        gdb_nations = await gdb.get_nations_by_alliance(alliance_id_to_fetch)
                        if gdb_nations:
                            for n in gdb_nations:
                                n['cities'] = await gdb.get_cities_for_nation(int(n['id']))
                            nations = gdb_nations
                except Exception as e:
                    logger.warning(f"GlobalNationsDB alliance lookup failed: {e}")

            if not nations:
                # Fallback to API for alliances not in GlobalNations.db
                try:
                    aid = alliance_id_to_fetch
                    if not aid:
                        resolved = await qi.resolve_alliance(q)
                        aid = resolved.get('id') if resolved else None
                    if aid:
                        nations = await qi.get_alliance_nations(str(aid))
                except Exception as e:
                    logger.error(f"Alliance API lookup failed: {e}")
                    return JSONResponse({'error': f'Alliance not found: {q}'}, status_code=404)

            if not nations:
                return JSONResponse({'error': 'No nations found for that alliance.'}, status_code=404)

            # Run all analyze_revenue calls in a thread pool — they do blocking SQLite I/O
            async def _analyze_one(nation: dict) -> Optional[dict]:
                if not nation.get('cities'):
                    return None
                try:
                    result = await asyncio.to_thread(
                        _run_analyze_revenue, nation, prices,
                        ctx['colors'], ctx['seasonal_mod'], ctx['radiation']
                    )
                    return _serialize_result(nation, result, prices)
                except Exception as e:
                    logger.warning(f"analyze_revenue failed for {nation.get('nation_name')}: {e}")
                    return None

            analyzed = await asyncio.gather(*[_analyze_one(n) for n in nations])
            results = [r for r in analyzed if r is not None]
            results.sort(key=lambda x: (x.get('current_monetary') or 0), reverse=True)
            return {'type': 'alliance', 'query': query, 'nations': results, 'prices': prices}

        # ── Single nation path ─────────────────────────────────────────────
        nation = await _get_nation_with_cities(q, qi)
        if not nation:
            return JSONResponse({'error': f'Nation not found: {q}'}, status_code=404)
        if not nation.get('cities'):
            return JSONResponse({'error': 'No city data found for this nation.'}, status_code=404)

        result = await asyncio.to_thread(
            _run_analyze_revenue, nation, prices,
            ctx['colors'], ctx['seasonal_mod'], ctx['radiation']
        )
        serialized = _serialize_result(nation, result, prices)
        return {'type': 'nation', 'query': query, 'nations': [serialized], 'prices': prices}

    except Exception as e:
        logger.error(f"rev_opt_analyze error: {e}", exc_info=True)
        return JSONResponse({'error': str(e)}, status_code=500)

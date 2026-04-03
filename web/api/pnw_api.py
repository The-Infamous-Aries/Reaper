
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union, cast, Sequence

from Systems.Functions.utils import get_web_public_url
from Systems.PnW.Util.calc import AllianceCalculator
from Systems.PnW.Util.Graphs.compare_graph import create_interactive_comparison_page
from Systems.PnW.Util.query import create_v3_query_instance


router = APIRouter()
logger = logging.getLogger("Reaper.WebServer.PnWAPI")


def _parse_alliance_identifier(text: str) -> Tuple[Optional[int], Optional[str]]:
    """Parse user input for alliance ID from numeric string or PnW link."""
    if not text:
        return (None, None)
    s = (text or '').strip()
    m = re.search(r"id\\s*=\\s*(\\d+)", s)
    if m:
        try:
            return (int(m.group(1)), None)
        except Exception:
            pass
    if s.isdigit():
        try:
            return (int(s), None)
        except Exception:
            pass
    return (None, s)

async def _resolve_alliance_id_from_api(name_or_acr: str, query_instance) -> Tuple[Optional[int], Optional[str]]:
    """Resolve an alliance ID by exact name or acronym using the PnW GraphQL API."""
    try:
        result = await query_instance.resolve_alliance(name_or_acr)
        if result and result.get('id'):
            alliance_id = result.get('id')
            if alliance_id is not None:
                return (int(alliance_id), result.get('name') or name_or_acr)
    except Exception as e:
        logger.warning(f"_resolve_alliance_id_from_api failed for '{name_or_acr}': {e}")
    return (None, None)

async def _resolve_targets(text: str, query_instance) -> List[Tuple[Optional[int], Optional[str]]]:
    """Resolve a comma-separated list of alliance identifiers."""
    out: List[Tuple[Optional[int], Optional[str]]] = []
    if not text:
        return out
    parts = [p.strip() for p in str(text).split(',') if p.strip()]
    for part in parts:
        aid, name = _parse_alliance_identifier(part)
        if isinstance(aid, int) and aid > 0:
            out.append((aid, name or f"Alliance {aid}"))
            continue
        r_id, r_name = await _resolve_alliance_id_from_api(name or part, query_instance)
        if isinstance(r_id, int) and r_id > 0:
            out.append((r_id, r_name or name or part))
        else:
            out.append((None, name or part))
    return out

@router.get("/pnw/compare", response_class=HTMLResponse)
async def get_compare_graph(home: str, away: str):
    query_instance = create_v3_query_instance()
    calculator = AllianceCalculator(query_instance)

    home_targets = await _resolve_targets(home, query_instance)
    away_targets = await _resolve_targets(away, query_instance)

    valid_home = [t for t in home_targets if t[0] is not None]
    valid_away = [t for t in away_targets if t[0] is not None]

    if not valid_home or not valid_away:
        return HTMLResponse(content="<h1>Error</h1><p>Could not resolve one or both sides.</p>", status_code=400)

    home_ids = [str(t[0]) for t in valid_home]
    away_ids = [str(t[0]) for t in valid_away]

    home_nations_map = await calculator.get_nations_batched(home_ids)
    away_nations_map = await calculator.get_nations_batched(away_ids)

    all_home_nations = [n for nations in home_nations_map.values() for n in nations]
    all_away_nations = [n for nations in away_nations_map.values() for n in nations]

    home_stats = await calculator.calculate_alliance_statistics(all_home_nations)
    away_stats = await calculator.calculate_alliance_statistics(all_away_nations)

    home_name = ", ".join([t[1] for t in valid_home]) if len(valid_home) > 1 else valid_home[0][1]
    away_name = ", ".join([t[1] for t in valid_away]) if len(valid_away) > 1 else valid_away[0][1]

    html_content = create_interactive_comparison_page(
        home_stats=home_stats,
        away_stats=away_stats,
        home_name=home_name,
        away_name=away_name,
        home_nations=all_home_nations,
        away_nations=all_away_nations
    )

    return HTMLResponse(content=html_content)

@router.get("/pnw/war_costs", response_class=HTMLResponse)
async def get_war_costs_graph(alliance: str, time: str, force_refresh: bool = False, opps_view: bool = False):
    from Systems.PnW.MA.war_costs_bd import WarsBD
    from Systems.PnW.Util.Graphs.war_graph import war_graph_generator

    cog = WarsBD(bot=None)
    after_datetime = cog._parse_time_to_utc_datetime(time)
    if not after_datetime:
        return HTMLResponse(content="<h1>Error</h1><p>Invalid time format.</p>", status_code=400)

    query_instance = create_v3_query_instance()
    resolved_alliance_ids = await query_instance.resolve_entities([alliance], 'alliance')
    if not resolved_alliance_ids:
        return HTMLResponse(content=f"<h1>Error</h1><p>Could not find an alliance named '{alliance}'.</p>", status_code=400)
    alliance_id = resolved_alliance_ids[0]

    all_wars = await query_instance.get_wars(alliance_id=[alliance_id], active=False, status="ALL", after=after_datetime, before=datetime.now(timezone.utc), force_refresh=force_refresh)
    if not all_wars:
        return HTMLResponse(content=f"<h1>No Wars Found</h1><p>No wars found for alliance '{alliance}' in the last {time}.</p>", status_code=404)

    from Systems.PnW.Util.war_calc import get_resource_prices
    resource_prices = await get_resource_prices()
    nation_breakdown = await cog._get_nation_breakdown(all_wars, alliance_id, opps_view, resource_prices)

    if not nation_breakdown:
        return HTMLResponse(content=f"<h1>Error</h1><p>No war costs could be calculated for alliance '{alliance}' in the last {time}.</p>", status_code=400)

    html_content = war_graph_generator.generate_interactive_breakdown(nation_breakdown, alliance, resource_prices)
    return HTMLResponse(content=html_content)

@router.get("/pnw/war_net", response_class=HTMLResponse)
async def get_war_net_graph(alliance: str, time: str, force_refresh: bool = False, opps_view: bool = False):
    from Systems.PnW.MA.war_net_bd import WarsNetBD
    from Systems.PnW.Util.Graphs.war_graph_net_bd import war_net_breakdown_graph_generator

    cog = WarsNetBD(bot=None)
    after_datetime = cog._parse_time_to_utc_datetime(time)
    if not after_datetime:
        return HTMLResponse(content="<h1>Error</h1><p>Invalid time format.</p>", status_code=400)

    query_instance = create_v3_query_instance()
    resolved_alliance_ids = await query_instance.resolve_entities([alliance], 'alliance')
    if not resolved_alliance_ids:
        return HTMLResponse(content=f"<h1>Error</h1><p>Could not find an alliance named '{alliance}'.</p>", status_code=400)
    alliance_id = resolved_alliance_ids[0]

    all_wars = await query_instance.get_wars(alliance_id=[alliance_id], active=False, status="ALL", after=after_datetime, before=datetime.now(timezone.utc), force_refresh=force_refresh)
    if not all_wars:
        return HTMLResponse(content=f"<h1>No Wars Found</h1><p>No wars found for alliance '{alliance}' in the last {time}.</p>", status_code=404)

    from Systems.PnW.Util.war_calc import get_resource_prices
    resource_prices = await get_resource_prices()
    nation_breakdown = await cog._get_nation_breakdown(all_wars, alliance_id, opps_view, resource_prices)

    if not nation_breakdown:
        return HTMLResponse(content=f"<h1>Error</h1><p>No war costs could be calculated for alliance '{alliance}' in the last {time}.</p>", status_code=400)

    enemy_relationships = cog._calculate_enemy_relationships(all_wars, nation_breakdown, str(alliance_id))
    html_content = war_net_breakdown_graph_generator.generate_interactive_net_breakdown(nation_breakdown, alliance, resource_prices, enemy_relationships)
    return HTMLResponse(content=html_content)

@router.get("/pnw/universe", response_class=HTMLResponse)
async def get_universe_graph(timeframe: Optional[str] = None):
    from Systems.PnW.FA.universe import TreatyUniverse, UniverseCog # Have to import here to avoid circular dependency
    query_instance = create_v3_query_instance()
    universe = TreatyUniverse(query_instance)
    cog = UniverseCog(bot=None, query_instance=query_instance)

    if timeframe:
        all_treaties = cog.load_treaties_from_file(timeframe)
    else:
        all_treaties = await universe.get_all_treaties()

    if not all_treaties:
        return HTMLResponse(content="<h1>Error</h1><p>Could not load treaty data.</p>", status_code=400)

    treaty_graph_data = universe.treaty_graph.build_treaty_graph(all_treaties)
    blocs = universe.treaty_graph.find_blocs(all_treaties)

    html_content = universe.treaty_graph.create_interactive_map(treaty_graph_data, all_treaties, blocs)

    return HTMLResponse(content=html_content)
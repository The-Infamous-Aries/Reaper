
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
import logging
import re
from datetime import datetime, timezone
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
            # Resolve the actual name from the API even for numeric IDs
            r_id, r_name = await _resolve_alliance_id_from_api(str(aid), query_instance)
            out.append((aid, r_name or name or f"Alliance {aid}"))
            continue
        r_id, r_name = await _resolve_alliance_id_from_api(name or part, query_instance)
        if isinstance(r_id, int) and r_id > 0:
            out.append((r_id, r_name or name or part))
        else:
            out.append((None, name or part))
    return out

@router.get("/pnw/nation/{nation_id}")
async def get_nation_info(nation_id: str, request: Request):
    """Lightweight nation lookup — returns name and flag for sidebar display."""
    if not nation_id.isdigit():
        raise HTTPException(status_code=400, detail="Nation ID must be numeric.")
    query_instance = create_v3_query_instance()
    nation = await query_instance.get_nation_by_id(nation_id)
    if not nation:
        raise HTTPException(status_code=404, detail="Nation not found.")
    return JSONResponse({
        "id": nation.get("id"),
        "nation_name": nation.get("nation_name"),
        "flag": nation.get("flag"),
        "leader_name": nation.get("leader_name"),
    })
@router.get("/pnw/compare", response_class=HTMLResponse)
async def get_compare_graph(home_alliance_ids: str, away_alliance_ids: str):
    query_instance = create_v3_query_instance()
    calculator = AllianceCalculator(query_instance)

    home_targets = await _resolve_targets(home_alliance_ids, query_instance)
    away_targets = await _resolve_targets(away_alliance_ids, query_instance)

    valid_home = [t for t in home_targets if t[0] is not None]
    valid_away = [t for t in away_targets if t[0] is not None]

    if not valid_home or not valid_away:
        return HTMLResponse(content="<h1>Error</h1><p>Could not resolve one or both sides.</p>", status_code=400)

    # Get nations for each alliance
    home_alliance_stats = []
    away_alliance_stats = []

    for alliance_id, alliance_name in valid_home:
        try:
            nations = await query_instance.get_alliance_nations(str(alliance_id))
            if nations:
                stats = await calculator.calculate_alliance_statistics(nations)
                mil = stats['total_military']
                alliance_data = {
                    'name': alliance_name,
                    'stats': {
                        'total_score': stats['total_score'],
                        'total_nations': stats['total_nations'],
                        'daily_military': {
                            'current_soldiers': mil['soldiers'],
                            'current_tanks': mil['tanks'],
                            'current_aircraft': mil['aircraft'],
                            'current_ships': mil['ships'],
                            'current_missiles': mil['missiles'],
                            'current_nukes': mil['nukes'],
                            'daily_soldiers': mil['soldiers'],
                            'daily_tanks': mil['tanks'],
                            'daily_aircraft': mil['aircraft'],
                            'daily_ships': mil['ships'],
                            'daily_missiles': mil['missiles'],
                            'daily_nukes': mil['nukes'],
                        },
                        'city_counts': {}
                    }
                }
                home_alliance_stats.append(alliance_data)
        except Exception as e:
            logger.error(f"Error getting nations for home alliance {alliance_id}: {e}")

    for alliance_id, alliance_name in valid_away:
        try:
            nations = await query_instance.get_alliance_nations(str(alliance_id))
            if nations:
                stats = await calculator.calculate_alliance_statistics(nations)
                mil = stats['total_military']
                alliance_data = {
                    'name': alliance_name,
                    'stats': {
                        'total_score': stats['total_score'],
                        'total_nations': stats['total_nations'],
                        'daily_military': {
                            'current_soldiers': mil['soldiers'],
                            'current_tanks': mil['tanks'],
                            'current_aircraft': mil['aircraft'],
                            'current_ships': mil['ships'],
                            'current_missiles': mil['missiles'],
                            'current_nukes': mil['nukes'],
                            'daily_soldiers': mil['soldiers'],
                            'daily_tanks': mil['tanks'],
                            'daily_aircraft': mil['aircraft'],
                            'daily_ships': mil['ships'],
                            'daily_missiles': mil['missiles'],
                            'daily_nukes': mil['nukes'],
                        },
                        'city_counts': {}
                    }
                }
                away_alliance_stats.append(alliance_data)
        except Exception as e:
            logger.error(f"Error getting nations for away alliance {alliance_id}: {e}")

    if not home_alliance_stats or not away_alliance_stats:
        return HTMLResponse(content="<h1>Error</h1><p>Could not load nation data for one or both sides.</p>", status_code=400)

    html_content = create_interactive_comparison_page(
        home_individual_stats=home_alliance_stats,
        away_individual_stats=away_alliance_stats
    )

    return HTMLResponse(content=html_content)

WATCH_DB_PATH = "c:\\Users\\codyr\\DiscordBots\\Reaper\\Databases\\NightWatchWars.db"
WATCH_ALLIANCE_ID = 14225
NIGHTS_WATCH_ALIASES = {"nights watch", "night's watch", "nightswatch", "nw", "14225"}

def _is_nights_watch(alliance: str) -> bool:
    return alliance.strip().lower() in NIGHTS_WATCH_ALIASES

def _normalize_nw_wars(wars: list) -> list:
    """Inject nested 'attacker'/'defender' dicts into flat NightsWatch DB war rows
    so they match the structure expected by _get_nation_breakdown."""
    normalized = []
    for war in wars:
        w = dict(war)
        if 'attacker' not in w:
            w['attacker'] = {'nation_name': w.get('att_nation_name'), 'leader_name': w.get('att_leader_name')}
        if 'defender' not in w:
            w['defender'] = {'nation_name': w.get('def_nation_name'), 'leader_name': w.get('def_leader_name')}
        normalized.append(w)
    return normalized

@router.get("/pnw/war_costs", response_class=HTMLResponse)
async def get_war_costs_graph(alliance: str, time: str, force_refresh: bool = False, opps_view: bool = False):
    from Systems.PnW.MA.war_costs_bd import WarsBD
    from Systems.PnW.Util.Graphs.war_graph import war_graph_generator
    from Systems.PnW.Util.war_calc import get_resource_prices

    cog = WarsBD(bot=None)
    after_datetime = cog._parse_time_to_utc_datetime(time)
    if not after_datetime:
        return HTMLResponse(content="<h1>Error</h1><p>Invalid time format.</p>", status_code=400)

    resource_prices = await get_resource_prices()

    if _is_nights_watch(alliance):
        from Systems.PnW.MA.night_watch_wars_db import NightWatchWarsDB
        from web.api.watch_api import _attach_war_attacks
        from datetime import date as date_type
        db = NightWatchWarsDB(WATCH_DB_PATH)
        start_date = after_datetime.date()
        end_date = datetime.now(timezone.utc).date()
        att_wars = await db.get_wars_by_alliance_in_range(WATCH_ALLIANCE_ID, role='attacker', start_date=start_date, end_date=end_date)
        def_wars = await db.get_wars_by_alliance_in_range(WATCH_ALLIANCE_ID, role='defender', start_date=start_date, end_date=end_date)
        all_wars = list({w['id']: w for w in (att_wars + def_wars)}.values())
        if not all_wars:
            return HTMLResponse(content=f"<h1>No Wars Found</h1><p>No Night's Watch wars found in the last {time}.</p>", status_code=404)
        all_wars = await _attach_war_attacks(db, all_wars)
        all_wars = _normalize_nw_wars(all_wars)
        alliance_id = WATCH_ALLIANCE_ID
        alliance_display = "Night's Watch"
    else:
        query_instance = create_v3_query_instance()
        resolved_alliance_ids = await query_instance.resolve_entities([alliance], 'alliance')
        if not resolved_alliance_ids:
            return HTMLResponse(content=f"<h1>Error</h1><p>Could not find an alliance named '{alliance}'.</p>", status_code=400)
        alliance_id = resolved_alliance_ids[0]
        all_wars = await query_instance.get_wars(alliance_id=[alliance_id], active=False, status="ALL", after=after_datetime, before=datetime.now(timezone.utc), force_refresh=force_refresh)
        if not all_wars:
            return HTMLResponse(content=f"<h1>No Wars Found</h1><p>No wars found for alliance '{alliance}' in the last {time}.</p>", status_code=404)
        alliance_display = alliance

    nation_breakdown = await cog._get_nation_breakdown(all_wars, alliance_id, opps_view, resource_prices)
    if not nation_breakdown:
        return HTMLResponse(content=f"<h1>Error</h1><p>No war costs could be calculated for alliance '{alliance}' in the last {time}.</p>", status_code=400)

    html_content = war_graph_generator.generate_interactive_breakdown(nation_breakdown, alliance_display, resource_prices)
    return HTMLResponse(content=html_content)

@router.get("/pnw/war_net", response_class=HTMLResponse)
async def get_war_net_graph(alliance: str, time: str, force_refresh: bool = False, opps_view: bool = False):
    from Systems.PnW.MA.war_net_bd import WarsNetBD
    from Systems.PnW.Util.Graphs.war_graph_net_bd import war_net_breakdown_graph_generator
    from Systems.PnW.Util.war_calc import get_resource_prices

    cog = WarsNetBD(bot=None)
    after_datetime = cog._parse_time_to_utc_datetime(time)
    if not after_datetime:
        return HTMLResponse(content="<h1>Error</h1><p>Invalid time format.</p>", status_code=400)

    resource_prices = await get_resource_prices()

    if _is_nights_watch(alliance):
        from Systems.PnW.MA.night_watch_wars_db import NightWatchWarsDB
        from web.api.watch_api import _attach_war_attacks
        db = NightWatchWarsDB(WATCH_DB_PATH)
        start_date = after_datetime.date()
        end_date = datetime.now(timezone.utc).date()
        att_wars = await db.get_wars_by_alliance_in_range(WATCH_ALLIANCE_ID, role='attacker', start_date=start_date, end_date=end_date)
        def_wars = await db.get_wars_by_alliance_in_range(WATCH_ALLIANCE_ID, role='defender', start_date=start_date, end_date=end_date)
        all_wars = list({w['id']: w for w in (att_wars + def_wars)}.values())
        if not all_wars:
            return HTMLResponse(content=f"<h1>No Wars Found</h1><p>No Night's Watch wars found in the last {time}.</p>", status_code=404)
        all_wars = await _attach_war_attacks(db, all_wars)
        all_wars = _normalize_nw_wars(all_wars)
        alliance_id = WATCH_ALLIANCE_ID
        alliance_display = "Night's Watch"
    else:
        query_instance = create_v3_query_instance()
        resolved_alliance_ids = await query_instance.resolve_entities([alliance], 'alliance')
        if not resolved_alliance_ids:
            return HTMLResponse(content=f"<h1>Error</h1><p>Could not find an alliance named '{alliance}'.</p>", status_code=400)
        alliance_id = resolved_alliance_ids[0]
        all_wars = await query_instance.get_wars(alliance_id=[alliance_id], active=False, status="ALL", after=after_datetime, before=datetime.now(timezone.utc), force_refresh=force_refresh)
        if not all_wars:
            return HTMLResponse(content=f"<h1>No Wars Found</h1><p>No wars found for alliance '{alliance}' in the last {time}.</p>", status_code=404)
        alliance_display = alliance

    nation_breakdown = await cog._get_nation_breakdown(all_wars, alliance_id, opps_view, resource_prices)
    if not nation_breakdown:
        return HTMLResponse(content=f"<h1>Error</h1><p>No war costs could be calculated for alliance '{alliance}' in the last {time}.</p>", status_code=400)

    enemy_relationships = cog._calculate_enemy_relationships(all_wars, nation_breakdown, str(alliance_id))
    html_content = war_net_breakdown_graph_generator.generate_interactive_net_breakdown(nation_breakdown, alliance_display, resource_prices, enemy_relationships)
    return HTMLResponse(content=html_content)

@router.get("/pnw/universe", response_class=HTMLResponse)
async def get_universe_graph(alliance: Optional[str] = None, alliance_ids: Optional[str] = None):
    from Systems.PnW.FA.universe import TreatyUniverse

    query_instance = create_v3_query_instance()
    universe = TreatyUniverse(query_instance)

    # Resolve the center alliance ID
    center_input = alliance or alliance_ids
    if not center_input or not center_input.strip():
        return HTMLResponse(content="<h1>Error</h1><p>Please provide an alliance name or ID.</p>", status_code=400)

    center_input = center_input.strip()
    if center_input.isdigit():
        center_id = int(center_input)
    else:
        resolved = await query_instance.resolve_entities([center_input], 'alliance')
        if not resolved:
            return HTMLResponse(content=f"<h1>Error</h1><p>Could not find alliance '{center_input}'.</p>", status_code=400)
        center_id = resolved[0]

    try:
        focused_data = await query_instance.get_focused_treaties(center_id)
    except Exception as e:
        logger.error(f"Error fetching focused treaties for {center_id}: {e}", exc_info=True)
        return HTMLResponse(content="<h1>Error</h1><p>Failed to fetch treaty data.</p>", status_code=500)

    if not focused_data.get('treaties'):
        return HTMLResponse(content="<h1>No Data</h1><p>No treaties found for this alliance.</p>", status_code=404)

    html_content = universe.treaty_graph.create_focused_map(focused_data)
    if not html_content:
        return HTMLResponse(content="<h1>Error</h1><p>Failed to generate treaty map.</p>", status_code=500)

    return HTMLResponse(content=html_content)


@router.get("/pnw/resource-prices")
async def get_resource_prices_endpoint():
    """Return current buy/sell resource prices for the cost calculator."""
    from Systems.PnW.Util.war_calc import get_resource_prices
    prices = await get_resource_prices()
    return JSONResponse({"sell": prices.get("sell", {}), "buy": prices.get("buy", {})})

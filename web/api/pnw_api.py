
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
        # Short-circuit Night's Watch — it lives in a local DB, not the PnW API
        if _is_nights_watch(part):
            out.append((WATCH_ALLIANCE_ID, "Night's Watch"))
            continue
        aid, name = _parse_alliance_identifier(part)
        if isinstance(aid, int) and aid > 0:
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
@router.get("/pnw/compare_data")
async def get_compare_data(home_alliance_ids: str, away_alliance_ids: str):
    """Returns rich JSON comparison data matching the Discord embed output."""
    import asyncio as _asyncio
    query_instance = create_v3_query_instance()
    calculator = AllianceCalculator(query_instance)

    home_targets = await _resolve_targets(home_alliance_ids, query_instance)
    away_targets = await _resolve_targets(away_alliance_ids, query_instance)

    valid_home = [t for t in home_targets if t[0] is not None]
    valid_away = [t for t in away_targets if t[0] is not None]

    if not valid_home or not valid_away:
        unresolved = [name for _, name in (home_targets + away_targets) if _ is None]
        raise HTTPException(status_code=400, detail=f"Could not resolve: {', '.join(str(u) for u in unresolved)}")

    async def _build_data(alliance_id: int, alliance_name: str) -> Optional[dict]:
        try:
            nations = await query_instance.get_alliance_nations(str(alliance_id))
            if not nations:
                logger.warning(f"No nations found for alliance {alliance_id} ({alliance_name})")
                return None

            # Same filtering as Discord embed: ALL - VM - APPLICANT
            active = [n for n in nations if
                      int(n.get('vacation_mode_turns', 0) or 0) == 0 and
                      (n.get('alliance_position', '') or '').strip().upper() != 'APPLICANT']
            apps = [n for n in nations if (n.get('alliance_position', '') or '').strip().upper() == 'APPLICANT']
            vm   = [n for n in nations if int(n.get('vacation_mode_turns', 0) or 0) > 0 and
                    (n.get('alliance_position', '') or '').strip().upper() != 'APPLICANT']

            # Run all calcs concurrently
            mill_data, stats, nation_stats, improvements, city_buckets = await _asyncio.gather(
                calculator.calculate_full_mill_data(active),
                calculator.calculate_alliance_statistics(active),
                calculator.calculate_nation_statistics(nations),
                calculator.calculate_improvements_data(active),
                calculator.bucket_city_counts(active),
            )

            return {
                'name': alliance_name,
                'id': alliance_id,
                'total_nations': len(nations),
                'active_nations': len(active),
                'applicant_nations': len(apps),
                'vacation_nations': len(vm),
                'grey_nations': nation_stats.get('grey_nations', 0),
                'beige_nations': nation_stats.get('beige_nations', 0),
                'inactive_7_days': nation_stats.get('inactive_7_days', 0),
                'inactive_14_days': nation_stats.get('inactive_14_days', 0),
                'total_score': round(stats['total_score'], 2),
                'avg_score': round(stats['total_score'] / len(active), 2) if active else 0,
                'total_cities': stats['total_cities'],
                'avg_cities': round(stats['total_cities'] / len(active), 2) if active else 0,
                # Military: current / max / gap (same as Discord FullMill embed)
                'military': {
                    'current_soldiers': mill_data['current_soldiers'],
                    'current_tanks':    mill_data['current_tanks'],
                    'current_aircraft': mill_data['current_aircraft'],
                    'current_ships':    mill_data['current_ships'],
                    'current_missiles': mill_data['current_missiles'],
                    'current_nukes':    mill_data['current_nukes'],
                    'max_soldiers':     mill_data['max_soldiers'],
                    'max_tanks':        mill_data['max_tanks'],
                    'max_aircraft':     mill_data['max_aircraft'],
                    'max_ships':        mill_data['max_ships'],
                    'soldier_gap':      mill_data['soldier_gap'],
                    'tank_gap':         mill_data['tank_gap'],
                    'aircraft_gap':     mill_data['aircraft_gap'],
                    'ship_gap':         mill_data['ship_gap'],
                },
                # Daily production
                'production': {
                    'daily_soldiers': mill_data['daily_soldiers'],
                    'daily_tanks':    mill_data['daily_tanks'],
                    'daily_aircraft': mill_data['daily_aircraft'],
                    'daily_ships':    mill_data['daily_ships'],
                    'daily_missiles': mill_data['daily_missiles'],
                    'daily_nukes':    mill_data['daily_nukes'],
                },
                # Projects — ALL from PROJECT_FIELD_MAPPING, counted per active nation
                'projects': {k: sum(1 for n in active if n.get(v, False)) for k, v in {
                    'missile_launch_pad': 'missile_launch_pad',
                    'nuclear_research_facility': 'nuclear_research_facility',
                    'nuclear_launch_facility': 'nuclear_launch_facility',
                    'vital_defense_system': 'vital_defense_system',
                    'iron_dome': 'iron_dome',
                    'propaganda_bureau': 'propaganda_bureau',
                    'military_research_center': 'military_research_center',
                    'space_program': 'space_program',
                    'military_doctrine': 'military_doctrine',
                    'military_salvage': 'military_salvage',
                    'international_trade_center': 'international_trade_center',
                    'bureau_of_domestic_affairs': 'bureau_of_domestic_affairs',
                    'arable_land_agency': 'arable_land_agency',
                    'mass_irrigation': 'mass_irrigation',
                    'green_technologies': 'green_technologies',
                    'recycling_initiative': 'recycling_initiative',
                    'center_for_civil_engineering': 'center_for_civil_engineering',
                    'clinical_research_center': 'clinical_research_center',
                    'specialized_police_training_program': 'specialized_police_training_program',
                    'government_support_agency': 'government_support_agency',
                    'activity_center': 'activity_center',
                    'advanced_engineering_corps': 'advanced_engineering_corps',
                    'bauxite_works': 'bauxite_works',
                    'iron_works': 'iron_works',
                    'emergency_gasoline_reserve': 'emergency_gasoline_reserve',
                    'uranium_enrichment_program': 'uranium_enrichment_program',
                    'arms_stockpile': 'arms_stockpile',
                    'advanced_pirate_economy': 'advanced_pirate_economy',
                    'pirate_economy': 'pirate_economy',
                    'research_and_development_center': 'research_and_development_center',
                    'spy_satellite': 'spy_satellite',
                    'surveillance_network': 'surveillance_network',
                    'telecommunications_satellite': 'telecommunications_satellite',
                    'guiding_satellite': 'guiding_satellite',
                    'moon_landing': 'moon_landing',
                    'mars_landing': 'mars_landing',
                    'central_intelligence_agency': 'central_intelligence_agency',
                    'fallout_shelter': 'fallout_shelter',
                }.items()},
                # Improvements — ALL from IMPROVEMENT_KEYS
                'improvements': {
                    'coalpower':       improvements.get('coalpower', 0),
                    'oilpower':        improvements.get('oilpower', 0),
                    'nuclearpower':    improvements.get('nuclearpower', 0),
                    'windpower':       improvements.get('windpower', 0),
                    'oilwell':         improvements.get('oilwell', 0),
                    'coalmine':        improvements.get('coalmine', 0),
                    'uramine':         improvements.get('uramine', 0),
                    'ironmine':        improvements.get('ironmine', 0),
                    'bauxitemine':     improvements.get('bauxitemine', 0),
                    'leadmine':        improvements.get('leadmine', 0),
                    'farm':            improvements.get('farm', 0),
                    'gasrefinery':     improvements.get('gasrefinery', 0),
                    'steelmill':       improvements.get('steelmill', 0),
                    'aluminumrefinery':improvements.get('aluminumrefinery', 0),
                    'munitionsfactory':improvements.get('munitionsfactory', 0),
                    'factory':         improvements.get('factory', 0),
                    'policestation':   improvements.get('policestation', 0),
                    'hospital':        improvements.get('hospital', 0),
                    'recyclingcenter': improvements.get('recyclingcenter', 0),
                    'subway':          improvements.get('subway', 0),
                    'supermarket':     improvements.get('supermarket', 0),
                    'bank':            improvements.get('bank', 0),
                    'shopping_mall':   improvements.get('shopping_mall', 0),
                    'stadium':         improvements.get('stadium', 0),
                    'barracks':        improvements.get('barracks', 0),
                    'hangar':          improvements.get('hangar', 0),
                    'drydock':         improvements.get('drydock', 0),
                    'total_cities':    improvements.get('total_cities', 0),
                    'avg_per_city':    round(improvements.get('avg_per_city', 0), 2),
                },
                'city_distribution': {label: count for label, count in city_buckets},
            }
        except Exception as e:
            logger.error(f"Error building compare data for alliance {alliance_id} ({alliance_name}): {e}", exc_info=True)
            return None

    home_results = await _asyncio.gather(*[_build_data(aid, aname) for aid, aname in valid_home])
    away_results = await _asyncio.gather(*[_build_data(aid, aname) for aid, aname in valid_away])

    home_data = [r for r in home_results if r is not None]
    away_data  = [r for r in away_results if r is not None]

    if not home_data or not away_data:
        raise HTTPException(status_code=400, detail="Could not load nation data for one or both sides.")

    return JSONResponse({"home": home_data, "away": away_data})


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

    async def _build_alliance_data(alliance_id: int, alliance_name: str) -> Optional[dict]:
        try:
            nations = await query_instance.get_alliance_nations(str(alliance_id))
            if not nations:
                return None
            stats = await calculator.calculate_alliance_statistics(nations)
            nation_stats = await calculator.calculate_nation_statistics(nations)
            city_buckets = await calculator.bucket_city_counts(nations)
            mil = stats['total_military']
            prod = stats['production_capacity']
            return {
                'name': alliance_name,
                'id': alliance_id,
                'stats': {
                    'total_score': stats['total_score'],
                    'total_nations': stats['total_nations'],
                    'total_cities': stats['total_cities'],
                    'active_nations': nation_stats.get('active_nations', 0),
                    'vacation_nations': nation_stats.get('vacation_nations', 0),
                    'applicant_nations': nation_stats.get('applicant_nations', 0),
                    'grey_nations': nation_stats.get('grey_nations', 0),
                    'beige_nations': nation_stats.get('beige_nations', 0),
                    'inactive_7_days': nation_stats.get('inactive_7_days', 0),
                    'inactive_14_days': nation_stats.get('inactive_14_days', 0),
                    'missile_capable': stats.get('missile_capable', 0),
                    'nuclear_capable': stats.get('nuclear_capable', 0),
                    'vital_defense_system': stats.get('vital_defense_system', 0),
                    'iron_dome': stats.get('iron_dome', 0),
                    'propaganda_bureau': stats.get('propaganda_bureau', 0),
                    'military_research_center': stats.get('military_research_center', 0),
                    'space_program': stats.get('space_program', 0),
                    'missile_launch_pad': stats.get('missile_launch_pad', 0),
                    'nuclear_research_facility': stats.get('nuclear_research_facility', 0),
                    'nuclear_launch_facility': stats.get('nuclear_launch_facility', 0),
                    'daily_military': {
                        'current_soldiers': mil['soldiers'],
                        'current_tanks': mil['tanks'],
                        'current_aircraft': mil['aircraft'],
                        'current_ships': mil['ships'],
                        'current_missiles': mil['missiles'],
                        'current_nukes': mil['nukes'],
                        'daily_soldiers': prod['daily_soldiers'],
                        'daily_tanks': prod['daily_tanks'],
                        'daily_aircraft': prod['daily_aircraft'],
                        'daily_ships': prod['daily_ships'],
                        'daily_missiles': prod['daily_missiles'],
                        'daily_nukes': prod['daily_nukes'],
                        'max_soldiers': prod['max_soldiers'],
                        'max_tanks': prod['max_tanks'],
                        'max_aircraft': prod['max_aircraft'],
                        'max_ships': prod['max_ships'],
                        'max_missiles': prod.get('max_missiles', 0),
                        'max_nukes': prod.get('max_nukes', 0),
                        'total_barracks': prod['total_barracks'],
                        'total_factories': prod['total_factories'],
                        'total_hangars': prod['total_hangars'],
                        'total_drydocks': prod['total_drydocks'],
                    },
                    'city_counts': {label: count for label, count in city_buckets},
                }
            }
        except Exception as e:
            logger.error(f"Error getting nations for alliance {alliance_id}: {e}")
            return None

    import asyncio as _asyncio
    home_tasks = [_build_alliance_data(aid, aname) for aid, aname in valid_home]
    away_tasks = [_build_alliance_data(aid, aname) for aid, aname in valid_away]
    home_results = await _asyncio.gather(*home_tasks)
    away_results = await _asyncio.gather(*away_tasks)
    home_alliance_stats = [r for r in home_results if r is not None]
    away_alliance_stats = [r for r in away_results if r is not None]

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
        from Systems.Functions.night_watch_wars_db import NightWatchWarsDB
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
        from Systems.Functions.night_watch_wars_db import NightWatchWarsDB
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

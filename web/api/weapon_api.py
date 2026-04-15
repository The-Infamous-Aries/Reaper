"""
Weapon Efficiency API — Theory and Targeted modes.
Mirrors the /weapon_eff Discord command logic for the web dashboard.

Nation and alliance targeted queries are cached in WeaponCache.db for 1 hour
so repeated page loads don't hammer the PnW API.
"""
import math
import logging
from typing import Optional
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from Systems.PnW.Util.war_calc import get_resource_prices, calculate_unit_cost
from Systems.PnW.Util.query import create_v3_query_instance
from Systems.PnW.MA.weapon_eff import (
    get_weapon_damage,
    calc_infra_value,
    find_required_infra,
)
from Systems.Functions.weapon_cache_db import get_cache

router = APIRouter()
logger = logging.getLogger("Reaper.WebServer.WeaponAPI")


# ── Shared helpers ────────────────────────────────────────────────────────────

def _city_population_and_density(city: dict) -> tuple[float, float]:
    infra = city.get('infrastructure', 0) or 0
    land  = city.get('land', 0) or 0
    if land <= 0:
        land = 1

    base_pop = infra * 100

    commerce = 0.0
    if city.get('powered', True):
        commerce += city.get('subway', 0) * 8
        commerce += city.get('supermarket', 0) * 4
        commerce += city.get('bank', 0) * 6
        commerce += city.get('shopping_mall', 0) * 8
        commerce += city.get('stadium', 0) * 10
    commerce = min(commerce, 100)

    pollution = 0.0
    if city.get('powered', True):
        pollution += city.get('police_station', 0)
        pollution += city.get('hospital', 0) * 4
        pollution -= city.get('recycling_center', 0) * 70
        pollution -= city.get('subway', 0) * 45
        pollution += city.get('shopping_mall', 0) * 2
        pollution += city.get('stadium', 0) * 5
    pollution = max(pollution, 0)

    police_stations = city.get('police_station', 0) if city.get('powered', True) else 0
    hospitals       = city.get('hospital', 0)       if city.get('powered', True) else 0

    crime_rate_raw = (math.pow(103 - commerce, 2) + base_pop) / 111111 - police_stations * 2.5
    crime_rate   = max(crime_rate_raw, 0)
    crime_deaths = max((crime_rate / 10) * base_pop - 25, 0)

    base_pop_density = base_pop / land
    disease_rate_raw = (
        ((base_pop_density ** 2) * 0.01 - 25) / 100
        + (base_pop / 100000)
        + pollution * 0.05
        - hospitals * 2.5
    )
    disease_rate   = max(0.0, min(disease_rate_raw, 100.0))
    disease_deaths = max(base_pop * (disease_rate / 100), 0)

    from datetime import datetime
    date_str = city.get('date', '')
    try:
        city_age = (datetime.utcnow() - datetime.strptime(
            date_str.split(" ")[0].split("T")[0], "%Y-%m-%d")).days
    except Exception:
        city_age = 365
    city_age  = max(city_age, 1)
    age_bonus = 1 + math.log(city_age) / 15

    actual_pop        = (base_pop - disease_deaths - crime_deaths) * age_bonus
    displayed_density = actual_pop / land
    return actual_pop, max(displayed_density, 1.0)


def _impact_chance(nation: dict, weapon: str) -> float:
    if weapon == "missile":
        return 0.70 if nation.get('iron_dome') else 1.0
    return 0.75 if nation.get('vital_defense_system') else 1.0


def _score_city(city: dict, nation: dict, weapon: str, weapon_cost: float) -> dict:
    infra = city.get('infrastructure', 0) or 0
    actual_pop, pd = _city_population_and_density(city)
    hit_chance = _impact_chance(nation, weapon)

    avg_dmg = get_weapon_damage(infra, weapon, pd, 'average')
    min_dmg = get_weapon_damage(infra, weapon, pd, 'min')
    max_dmg = get_weapon_damage(infra, weapon, pd, 'max')

    avg_val = calc_infra_value(infra - avg_dmg, infra)
    min_val = calc_infra_value(infra - min_dmg, infra)
    max_val = calc_infra_value(infra - max_dmg, infra)

    return {
        'city': city,
        'infra': infra,
        'pop_density': pd,
        'actual_pop': actual_pop,
        'hit_chance': hit_chance,
        'avg_dmg': avg_dmg, 'min_dmg': min_dmg, 'max_dmg': max_dmg,
        'avg_val': avg_val, 'min_val': min_val, 'max_val': max_val,
        'expected_val': avg_val * hit_chance,
        'avg_mult': avg_val / weapon_cost if weapon_cost else 0,
        'max_mult': max_val / weapon_cost if weapon_cost else 0,
    }


def _score_all_cities(nation: dict, weapon: str, weapon_cost: float) -> list[dict]:
    cities = nation.get('cities', [])
    if not cities:
        return []
    return sorted(
        [_score_city(c, nation, weapon, weapon_cost) for c in cities],
        key=lambda s: s['avg_dmg'],
        reverse=True,
    )


def _city_score_payload(score: dict, weapon_cost: float) -> dict:
    c = score['city']
    return {
        'city_id':     c.get('id'),
        'city_name':   c.get('name', f"City {c.get('id')}"),
        'infra':       round(score['infra'], 2),
        'pop_density': round(score['pop_density'], 2),
        'actual_pop':  round(score['actual_pop']),
        'hit_chance':  score['hit_chance'],
        'min_dmg':     round(score['min_dmg'], 2),
        'max_dmg':     round(score['max_dmg'], 2),
        'avg_dmg':     round(score['avg_dmg'], 2),
        'min_val':     round(score['min_val']),
        'max_val':     round(score['max_val']),
        'avg_val':     round(score['avg_val']),
        'expected_val': round(score['expected_val']),
        'avg_mult':    round(score['avg_mult'], 2),
        'max_mult':    round(score['max_mult'], 2),
        'powered':     c.get('powered', True),
        'land':        c.get('land', 0),
    }


def _build_nation_payload(nation: dict, missile_cost: float, nuke_cost: float) -> dict:
    """Compute the full scored payload for a single nation."""
    has_iron_dome  = bool(nation.get('iron_dome'))
    has_vds        = bool(nation.get('vital_defense_system'))
    missile_chance = 0.70 if has_iron_dome else 1.0
    nuke_chance    = 0.75 if has_vds       else 1.0

    missile_scores = _score_all_cities(nation, 'missile', missile_cost)
    nuke_scores    = _score_all_cities(nation, 'nuke',    nuke_cost)

    city_map: dict[str, dict] = {}
    for s in missile_scores:
        cid = str(s['city'].get('id'))
        city_map.setdefault(cid, {'city': s['city']})
        city_map[cid]['missile'] = _city_score_payload(s, missile_cost)
    for s in nuke_scores:
        cid = str(s['city'].get('id'))
        city_map.setdefault(cid, {'city': s['city']})
        city_map[cid]['nuke'] = _city_score_payload(s, nuke_cost)

    cities_out = []
    for cid, entry in city_map.items():
        c = entry['city']
        cities_out.append({
            'city_id':   c.get('id'),
            'city_name': c.get('name', f"City {c.get('id')}"),
            'infra':     round(c.get('infrastructure', 0) or 0, 2),
            'land':      round(c.get('land', 0) or 0, 2),
            'powered':   c.get('powered', True),
            'missile':   entry.get('missile', {}),
            'nuke':      entry.get('nuke', {}),
        })
    cities_out.sort(key=lambda x: x['missile'].get('avg_dmg', 0), reverse=True)

    return {
        'mode':          'nation',
        'nation_id':     nation.get('id'),
        'nation_name':   nation.get('nation_name', 'Unknown'),
        'leader_name':   nation.get('leader_name', ''),
        'flag':          nation.get('flag', ''),
        'has_iron_dome': has_iron_dome,
        'has_vds':       has_vds,
        'missile_chance': missile_chance,
        'nuke_chance':    nuke_chance,
        'nuke_cost':     round(nuke_cost),
        'missile_cost':  round(missile_cost),
        'cities':        cities_out,
    }


def _build_alliance_nation_entry(nation: dict, missile_cost: float, nuke_cost: float) -> Optional[dict]:
    """Score one nation for the alliance list. Returns None if no cities."""
    if not nation.get('cities'):
        return None

    has_iron_dome  = bool(nation.get('iron_dome'))
    has_vds        = bool(nation.get('vital_defense_system'))
    missile_chance = 0.70 if has_iron_dome else 1.0
    nuke_chance    = 0.75 if has_vds       else 1.0

    missile_scores = _score_all_cities(nation, 'missile', missile_cost)
    nuke_scores    = _score_all_cities(nation, 'nuke',    nuke_cost)

    city_map: dict[str, dict] = {}
    for s in missile_scores:
        cid = str(s['city'].get('id'))
        city_map.setdefault(cid, {'city': s['city']})
        city_map[cid]['missile'] = _city_score_payload(s, missile_cost)
    for s in nuke_scores:
        cid = str(s['city'].get('id'))
        city_map.setdefault(cid, {'city': s['city']})
        city_map[cid]['nuke'] = _city_score_payload(s, nuke_cost)

    cities_out = []
    for cid, entry in city_map.items():
        c = entry['city']
        cities_out.append({
            'city_id':   c.get('id'),
            'city_name': c.get('name', f"City {c.get('id')}"),
            'infra':     round(c.get('infrastructure', 0) or 0, 2),
            'land':      round(c.get('land', 0) or 0, 2),
            'powered':   c.get('powered', True),
            'missile':   entry.get('missile', {}),
            'nuke':      entry.get('nuke', {}),
        })
    cities_out.sort(key=lambda x: x['missile'].get('avg_dmg', 0), reverse=True)

    best_m = max(missile_scores, key=lambda s: s['avg_dmg']) if missile_scores else None
    best_n = max(nuke_scores,    key=lambda s: s['avg_dmg']) if nuke_scores    else None

    return {
        'nation_id':   nation.get('id'),
        'nation_name': nation.get('nation_name', 'Unknown'),
        'leader_name': nation.get('leader_name', ''),
        'flag':        nation.get('flag', ''),
        'num_cities':  nation.get('num_cities', len(cities_out)),
        'has_iron_dome': has_iron_dome,
        'has_vds':       has_vds,
        'missile_chance': missile_chance,
        'nuke_chance':    nuke_chance,
        'best_missile_min_dmg': round(best_m['min_dmg'], 2) if best_m else 0,
        'best_missile_max_dmg': round(best_m['max_dmg'], 2) if best_m else 0,
        'best_missile_avg_dmg': round(best_m['avg_dmg'], 2) if best_m else 0,
        'best_missile_min_val': round(best_m['min_val'])    if best_m else 0,
        'best_missile_max_val': round(best_m['max_val'])    if best_m else 0,
        'best_missile_avg_val': round(best_m['avg_val'])    if best_m else 0,
        'best_nuke_min_dmg': round(best_n['min_dmg'], 2) if best_n else 0,
        'best_nuke_max_dmg': round(best_n['max_dmg'], 2) if best_n else 0,
        'best_nuke_avg_dmg': round(best_n['avg_dmg'], 2) if best_n else 0,
        'best_nuke_min_val': round(best_n['min_val'])    if best_n else 0,
        'best_nuke_max_val': round(best_n['max_val'])    if best_n else 0,
        'best_nuke_avg_val': round(best_n['avg_val'])    if best_n else 0,
        'cities': cities_out,
    }


# ── Theory endpoint ───────────────────────────────────────────────────────────

@router.get("/weapons/theory")
async def weapon_theory(infra: Optional[float] = None, pop_density: Optional[float] = None):
    """Theory mode — no caching needed, pure calculation."""
    try:
        resource_prices = await get_resource_prices()
        if not resource_prices or 'sell' not in resource_prices:
            return JSONResponse({"error": "Unable to fetch resource prices."}, status_code=503)

        nuke_cost    = calculate_unit_cost('nukes',    resource_prices['sell'])
        missile_cost = calculate_unit_cost('missiles', resource_prices['sell'])

        thresholds = {}
        for mult in [1, 2, 3, 5, 10, 15, 20]:
            thresholds[mult] = {
                'nuke_infra':    round(find_required_infra(nuke_cost    * mult, 'nuke',    60, 'average'), 0),
                'missile_infra': round(find_required_infra(missile_cost * mult, 'missile', 60, 'average'), 0),
            }

        chart = {'nuke': {'min': [], 'max': []}, 'missile': {'min': [], 'max': []}}
        for m in range(1, 21):
            for wt, cost in [('nuke', nuke_cost), ('missile', missile_cost)]:
                for key, pd in [('min', 10.0), ('max', 150.0)]:
                    infra_needed = find_required_infra(m * cost, wt, pd, key)
                    dmg = get_weapon_damage(infra_needed, wt, pd, key)
                    val = calc_infra_value(infra_needed - dmg, infra_needed)
                    chart[wt][key].append({
                        'mult': m,
                        'infra': round(infra_needed, 0),
                        'dmg':   round(dmg, 2),
                        'val':   round(val, 0),
                    })

        result = {
            'nuke_cost':    round(nuke_cost),
            'missile_cost': round(missile_cost),
            'thresholds':   thresholds,
            'chart':        chart,
        }

        if infra is not None and pop_density is not None:
            city_detail = {}
            for wt, cost in [('nuke', nuke_cost), ('missile', missile_cost)]:
                min_dmg = get_weapon_damage(infra, wt, pop_density, 'min')
                max_dmg = get_weapon_damage(infra, wt, pop_density, 'max')
                avg_dmg = get_weapon_damage(infra, wt, pop_density, 'average')
                city_detail[wt] = {
                    'min_dmg': round(min_dmg, 2),
                    'max_dmg': round(max_dmg, 2),
                    'avg_dmg': round(avg_dmg, 2),
                    'min_val': round(calc_infra_value(infra - min_dmg, infra)),
                    'max_val': round(calc_infra_value(infra - max_dmg, infra)),
                    'avg_val': round(calc_infra_value(infra - avg_dmg, infra)),
                    'min_mult': round(calc_infra_value(infra - min_dmg, infra) / cost, 2) if cost else 0,
                    'max_mult': round(calc_infra_value(infra - max_dmg, infra) / cost, 2) if cost else 0,
                    'cost': round(cost),
                }
            result['city_input']  = {'infra': infra, 'pop_density': pop_density}
            result['city_detail'] = city_detail

        return JSONResponse(result)

    except Exception as e:
        logger.error(f"weapon_theory error: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Targeted — Nation endpoint ────────────────────────────────────────────────

@router.get("/weapons/targeted/nation")
async def weapon_targeted_nation(target: str, force_refresh: bool = False):
    """
    Targeted mode for a single nation.
    Cached for 1 hour in WeaponCache.db. Pass force_refresh=true to bust.
    """
    try:
        cache = get_cache()
        cache_key = target.lower().strip()

        if not force_refresh:
            cached = await cache.get('nation', cache_key)
            if cached:
                logger.info("WeaponAPI nation cache HIT: %s", target)
                return JSONResponse(cached)

        resource_prices = await get_resource_prices()
        if not resource_prices or 'sell' not in resource_prices:
            return JSONResponse({"error": "Unable to fetch resource prices."}, status_code=503)

        nuke_cost    = calculate_unit_cost('nukes',    resource_prices['sell'])
        missile_cost = calculate_unit_cost('missiles', resource_prices['sell'])

        query = create_v3_query_instance()
        nation = (await query.get_nation_by_id(target)
                  if target.isdigit()
                  else await query.get_nation_by_name(target))
        if not nation:
            return JSONResponse({"error": f"Nation '{target}' not found."}, status_code=404)

        payload = _build_nation_payload(nation, missile_cost, nuke_cost)
        await cache.set('nation', cache_key, payload)
        logger.info("WeaponAPI nation cache SET: %s (%d cities)", target, len(payload['cities']))
        return JSONResponse(payload)

    except Exception as e:
        logger.error(f"weapon_targeted_nation error: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Targeted — Alliance endpoint ──────────────────────────────────────────────

@router.get("/weapons/targeted/alliance")
async def weapon_targeted_alliance(target: str, force_refresh: bool = False):
    """
    Targeted mode for an alliance.
    Cached for 1 hour in WeaponCache.db. Pass force_refresh=true to bust.
    """
    try:
        cache = get_cache()
        cache_key = target.lower().strip()

        if not force_refresh:
            cached = await cache.get('alliance', cache_key)
            if cached:
                logger.info("WeaponAPI alliance cache HIT: %s (%d nations)", target, cached.get('nation_count', 0))
                return JSONResponse(cached)

        resource_prices = await get_resource_prices()
        if not resource_prices or 'sell' not in resource_prices:
            return JSONResponse({"error": "Unable to fetch resource prices."}, status_code=503)

        nuke_cost    = calculate_unit_cost('nukes',    resource_prices['sell'])
        missile_cost = calculate_unit_cost('missiles', resource_prices['sell'])

        query = create_v3_query_instance()
        resolved = await query.resolve_alliance(target)
        if not resolved or not resolved.get('id'):
            return JSONResponse({"error": f"Alliance '{target}' not found."}, status_code=404)

        alliance_id   = str(resolved['id'])
        alliance_name = resolved.get('name', target)

        nations = await query.get_alliance_nations(alliance_id, force_refresh=True)
        if not nations:
            return JSONResponse({"error": f"No nations found in '{alliance_name}'."}, status_code=404)

        nations_out = []
        for nation in nations:
            entry = _build_alliance_nation_entry(nation, missile_cost, nuke_cost)
            if entry:
                nations_out.append(entry)

        nations_out.sort(key=lambda n: n['best_missile_avg_dmg'], reverse=True)

        payload = {
            'mode':          'alliance',
            'alliance_id':   alliance_id,
            'alliance_name': alliance_name,
            'nation_count':  len(nations_out),
            'nuke_cost':     round(nuke_cost),
            'missile_cost':  round(missile_cost),
            'nations':       nations_out,
        }

        await cache.set('alliance', cache_key, payload)
        logger.info("WeaponAPI alliance cache SET: %s (%d nations)", alliance_name, len(nations_out))
        return JSONResponse(payload)

    except Exception as e:
        logger.error(f"weapon_targeted_alliance error: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Cache status endpoint ─────────────────────────────────────────────────────

@router.get("/weapons/cache/stats")
async def weapon_cache_stats():
    """Returns cache stats — useful for debugging."""
    stats = await get_cache().stats()
    return JSONResponse(stats)


@router.delete("/weapons/cache/{cache_type}/{key}")
async def weapon_cache_invalidate(cache_type: str, key: str):
    """Manually invalidate a specific cache entry."""
    ok = await get_cache().invalidate(cache_type, key)
    return JSONResponse({"ok": ok})

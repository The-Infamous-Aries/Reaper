from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from starlette.requests import Request
import asyncio
import logging
import time
from typing import Dict, Any
import re
from datetime import date

from Systems.Functions.irs_wars_db import IRSWarsDB
from Systems.Functions.db_paths import IRS_WARS_DB_STR as WATCH_DB_PATH, IRS_NATIONS_DB_STR as NATIONS_DB_PATH
from Systems.PnW.Util.war_calc import get_resource_prices, calculate_unit_cost, calculate_war_costs
from Systems.PnW.MA.war_net_bd import WarsNetBD

router = APIRouter()
logger = logging.getLogger("Reaper.WebServer.WatchAPI")
WATCH_ALLIANCE_ID = 14225
LOOT_RESOURCES = ("coal", "oil", "uranium", "iron", "bauxite", "lead", "gasoline", "munitions", "steel", "aluminum", "food")

# ── Module-level singletons ───────────────────────────────────────────────────
# Reuse a single DB instance instead of re-initialising on every request.
_watch_db: IRSWarsDB | None = None

def _get_watch_db() -> IRSWarsDB:
    global _watch_db
    if _watch_db is None:
        _watch_db = IRSWarsDB(WATCH_DB_PATH)
    return _watch_db

# ── Simple TTL response cache ─────────────────────────────────────────────────
# Keyed by (start_date_iso, end_date_iso).  Entries expire after CACHE_TTL_SECS.
_WARS_CACHE_TTL = 120  # seconds
_wars_cache: Dict[tuple, tuple] = {}  # key → (timestamp, payload)

def _cache_get(key: tuple) -> Any | None:
    entry = _wars_cache.get(key)
    if entry and (time.monotonic() - entry[0]) < _WARS_CACHE_TTL:
        return entry[1]
    return None

def _cache_set(key: tuple, value: Any) -> None:
    _wars_cache[key] = (time.monotonic(), value)

def invalidate_wars_cache() -> None:
    """Call this whenever new war data is written so the next request is fresh."""
    _wars_cache.clear()
    global _watch_db
    _watch_db = None  # also reset the DB singleton so it re-opens on next request


def _current_user_id(request: Request) -> str | None:
    discord_user = request.session.get("discord_user")
    if discord_user and isinstance(discord_user, dict):
        uid = discord_user.get("id")
        if uid:
            return str(uid)
    uid = request.session.get("user_id")
    return str(uid) if uid else None


async def _require_access(request: Request):
    """Raise 403 if the session user does not have restricted-page access."""
    from Systems.Functions.page_access import has_access
    uid = _current_user_id(request)
    if not uid or not await has_access(uid):
        raise HTTPException(status_code=403, detail="Access denied. You are not authorised to view this page.")


def _as_number(value: Any) -> float:
    if isinstance(value, (int, float)):
        return value
    return 0


def _sum_numeric_mapping_values(value: Any) -> float:
    if not isinstance(value, dict):
        return 0
    return sum(_as_number(item) for item in value.values())


def _build_watch_response(
    nations: Dict[Any, Dict[str, Any]],
    error: str | None = None,
    resource_prices: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    normalized_nations: Dict[str, Dict[str, Any]] = {}
    buy_prices = (resource_prices or {}).get("buy", {})
    sell_prices = (resource_prices or {}).get("sell", {})

    for nation_id, nation_data in nations.items():
        gross_cost = _as_number(nation_data.get("gross_cost"))
        net_damage = _as_number(nation_data.get("net_damage"))
        total_gains = _as_number(nation_data.get("total_gains"))
        consumption_data = nation_data.get("consumption", {}) if isinstance(nation_data.get("consumption"), dict) else {}
        gas_used = _as_number(nation_data.get("gas_used", consumption_data.get("gasoline")))
        mun_used = _as_number(nation_data.get("mun_used", consumption_data.get("munitions")))
        gasoline_sell_value = gas_used * sell_prices.get("gasoline", 0)
        munitions_sell_value = mun_used * sell_prices.get("munitions", 0)
        consumption = gasoline_sell_value + munitions_sell_value
        infra_net = _as_number(nation_data.get("infra_net", nation_data.get("infra_destroyed_value")))
        infra_levels_lost = _as_number(nation_data.get("infra_levels_lost", nation_data.get("infra_destroyed")))
        improvements = _as_number(nation_data.get("improvements", nation_data.get("improvements_cost")))
        improvements_destroyed = nation_data.get("improvements_destroyed", {})
        improvements_count = _as_number(nation_data.get("improvements_count"))
        if not improvements_count:
            improvements_count = _sum_numeric_mapping_values(improvements_destroyed)
        loot_net = _as_number(nation_data.get("loot_net"))
        units_net = _as_number(nation_data.get("units_net"))
        units_total_cost = _as_number(nation_data.get("units_total_cost"))
        soldiers_lost = _as_number(nation_data.get("soldiers_lost"))
        tanks_lost = _as_number(nation_data.get("tanks_lost"))
        aircraft_lost = _as_number(nation_data.get("aircraft_lost"))
        ships_lost = _as_number(nation_data.get("ships_lost"))
        missiles_lost = _as_number(nation_data.get("missiles_lost"))
        nukes_lost = _as_number(nation_data.get("nukes_lost"))

        if not units_net:
            units_net = soldiers_lost + tanks_lost + aircraft_lost + ships_lost + missiles_lost + nukes_lost

        if not loot_net:
            loot_net = (
                _as_number(nation_data.get("loot_received"))
                + _as_number(nation_data.get("resource_loot_value"))
                - _as_number(nation_data.get("loot_lost"))
                - _as_number(nation_data.get("resource_loot_lost_value"))
            )

        # Build per-resource loot breakdown with monetary values
        resource_loot_gained = nation_data.get("resource_loot_gained", {}) or {}
        loot_breakdown: Dict[str, Any] = {
            "cash": _as_number(nation_data.get("loot_received")),
            "resources": {
                res: {
                    "amount": _as_number(amt),
                    "value": _as_number(amt) * sell_prices.get(res, 0),
                }
                for res, amt in resource_loot_gained.items()
                if _as_number(amt) > 0
            },
        }

        # Build wars_with: list of opponents this nation fought, with per-opponent stats
        per_opp = nation_data.get("_per_opp", {})
        wars_with = []
        seen_opps: set = set()
        for w in nation_data.get("_nation_wars", []):
            nid_str = str(nation_id)
            if str(w.get("att_id")) == nid_str:
                opp_id = str(w.get("def_id", ""))
                role = "attacker"
            else:
                opp_id = str(w.get("att_id", ""))
                role = "defender"
            if opp_id and opp_id not in seen_opps:
                seen_opps.add(opp_id)
                stats = per_opp.get(opp_id, {})
                wars_with.append({
                    "id": opp_id,
                    "name": stats.get("name", f"Nation {opp_id}"),
                    "stats": stats,
                })

        normalized_nations[str(nation_id)] = {
            **{k: v for k, v in nation_data.items() if k not in ("_nation_wars", "_per_opp")},
            "name": nation_data.get("name") or f"Unknown {nation_id}",
            "wars_with": wars_with,
            "gross_cost": gross_cost,
            "net_damage": net_damage,
            "total_damages": _as_number(nation_data.get("total_damages")),
            "total_gains": total_gains,
            "soldiers_lost": soldiers_lost,
            "tanks_lost": tanks_lost,
            "aircraft_lost": aircraft_lost,
            "ships_lost": ships_lost,
            "missiles_lost": missiles_lost,
            "nukes_lost": nukes_lost,
            "soldiers_lost_cost": soldiers_lost * calculate_unit_cost("soldiers", buy_prices),
            "tanks_lost_cost": tanks_lost * calculate_unit_cost("tanks", buy_prices),
            "aircraft_lost_cost": aircraft_lost * calculate_unit_cost("aircraft", buy_prices),
            "ships_lost_cost": ships_lost * calculate_unit_cost("ships", buy_prices),
            "missiles_lost_cost": missiles_lost * calculate_unit_cost("missiles", buy_prices),
            "nukes_lost_cost": nukes_lost * calculate_unit_cost("nukes", buy_prices),
            "units_net": units_net,
            "units_total_cost": units_total_cost,
            "gas_used": gas_used,
            "mun_used": mun_used,
            "gasoline_sell_value": gasoline_sell_value,
            "munitions_sell_value": munitions_sell_value,
            "consumption": consumption,
            "infra_net": infra_net,
            "infra_levels_lost": infra_levels_lost,
            "improvements": improvements,
            "improvements_count": improvements_count,
            "loot_net": loot_net,
            "loot": _as_number(nation_data.get("loot", total_gains)),
            "net": _as_number(nation_data.get("net", net_damage)),
            "offense_wars_count": _as_number(nation_data.get("offense_wars_count")),
            "defense_wars_count": _as_number(nation_data.get("defense_wars_count")),
            "raid_wars_count": _as_number(nation_data.get("raid_wars_count")),
            "attrition_wars_count": _as_number(nation_data.get("attrition_wars_count")),
            "wins_count": _as_number(nation_data.get("wins_count")),
            "losses_count": _as_number(nation_data.get("losses_count")),
            "peace_count": _as_number(nation_data.get("peace_count")),
            "draws_count": _as_number(nation_data.get("draws_count")),
            "damages": _as_number(nation_data.get("damages")),
            "loot_breakdown": loot_breakdown,
            "missiles_eaten": _as_number(nation_data.get("missiles_eaten")),
            "missiles_blocked": _as_number(nation_data.get("missiles_blocked")),
            "missiles_missed": _as_number(nation_data.get("missiles_missed")),
            "missiles_hit": _as_number(nation_data.get("missiles_hit")),
            "nukes_eaten": _as_number(nation_data.get("nukes_eaten")),
            "nukes_blocked": _as_number(nation_data.get("nukes_blocked")),
            "nukes_missed": _as_number(nation_data.get("nukes_missed")),
            "nukes_hit": _as_number(nation_data.get("nukes_hit")),
            "enemy_soldiers_killed": _as_number(nation_data.get("enemy_soldiers_killed")),
            "enemy_tanks_killed": _as_number(nation_data.get("enemy_tanks_killed")),
            "enemy_aircraft_killed": _as_number(nation_data.get("enemy_aircraft_killed")),
            "enemy_ships_killed": _as_number(nation_data.get("enemy_ships_killed")),
        }

    response: Dict[str, Any] = {"nations": normalized_nations}
    if error:
        response["error"] = error

    # ── Alliance totals row ───────────────────────────────────────────────────
    if normalized_nations:
        def _sum(key: str) -> float:
            return sum(_as_number(n.get(key)) for n in normalized_nations.values())

        total_gross      = _sum("gross_cost")
        total_net        = _sum("net_damage")
        total_gains      = _sum("total_gains")
        total_damages    = _sum("total_damages")
        total_soldiers   = _sum("soldiers_lost")
        total_tanks      = _sum("tanks_lost")
        total_aircraft   = _sum("aircraft_lost")
        total_ships      = _sum("ships_lost")
        total_missiles   = _sum("missiles_lost")
        total_nukes      = _sum("nukes_lost")
        total_units_cost = _sum("units_total_cost")
        total_gas        = _sum("gas_used")
        total_mun        = _sum("mun_used")
        total_gas_val    = _sum("gasoline_sell_value")
        total_mun_val    = _sum("munitions_sell_value")
        total_infra_lvl  = _sum("infra_levels_lost")
        total_infra_val  = _sum("infra_net")
        total_imp_cnt    = _sum("improvements_count")
        total_imp_val    = _sum("improvements")
        total_off        = _sum("offense_wars_count")
        total_def        = _sum("defense_wars_count")
        total_wins       = _sum("wins_count")
        total_losses     = _sum("losses_count")
        total_peace      = _sum("peace_count")
        total_draws      = _sum("draws_count")
        total_loot_lost  = _sum("loot_net") * -1  # loot_net = gained - lost; we want just lost
        # money_destroyed is not separately tracked in normalized output, derive from gross
        # gross = units + consumption(buy) + infra + improvements + loot_lost + res_loot_lost + money_destroyed
        # We expose what we have; money_destroyed is embedded in gross already

        # Aggregate loot breakdown across all nations
        total_loot_cash = sum(
            _as_number(n.get("loot_breakdown", {}).get("cash"))
            for n in normalized_nations.values()
        )
        total_loot_resources: Dict[str, Any] = {}
        for n in normalized_nations.values():
            for res, rdata in (n.get("loot_breakdown", {}).get("resources") or {}).items():
                if res not in total_loot_resources:
                    total_loot_resources[res] = {"amount": 0.0, "value": 0.0}
                total_loot_resources[res]["amount"] += _as_number(rdata.get("amount"))
                total_loot_resources[res]["value"]  += _as_number(rdata.get("value"))

        response["totals"] = {
            "name": "Nights Watch",
            "gross_cost":         total_gross,
            "net_damage":         total_net,
            "total_gains":        total_gains,
            "total_damages":      total_damages,
            "soldiers_lost":      total_soldiers,
            "tanks_lost":         total_tanks,
            "aircraft_lost":      total_aircraft,
            "ships_lost":         total_ships,
            "missiles_lost":      total_missiles,
            "nukes_lost":         total_nukes,
            "units_net":          total_soldiers + total_tanks + total_aircraft + total_ships + total_missiles + total_nukes,
            "units_total_cost":   total_units_cost,
            "soldiers_lost_cost": total_soldiers * calculate_unit_cost("soldiers", buy_prices),
            "tanks_lost_cost":    total_tanks    * calculate_unit_cost("tanks",    buy_prices),
            "aircraft_lost_cost": total_aircraft * calculate_unit_cost("aircraft", buy_prices),
            "ships_lost_cost":    total_ships    * calculate_unit_cost("ships",    buy_prices),
            "missiles_lost_cost": total_missiles * calculate_unit_cost("missiles", buy_prices),
            "nukes_lost_cost":    total_nukes    * calculate_unit_cost("nukes",    buy_prices),
            "gas_used":           total_gas,
            "mun_used":           total_mun,
            "gasoline_sell_value":total_gas_val,
            "munitions_sell_value":total_mun_val,
            "consumption":        total_gas_val + total_mun_val,
            "infra_levels_lost":  total_infra_lvl,
            "infra_net":          total_infra_val,
            "improvements_count": total_imp_cnt,
            "improvements":       total_imp_val,
            "offense_wars_count": total_off,
            "defense_wars_count": total_def,
            "wins_count":         total_wins,
            "losses_count":       total_losses,
            "peace_count":        total_peace,
            "draws_count":        total_draws,
            "damages":            total_damages,
            "loot_breakdown": {
                "cash":      total_loot_cash,
                "resources": total_loot_resources,
            },
            "wars_with": [],
            "nation_count": len(normalized_nations),
        }

    return response


def _parse_api_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _clamp_date_window(
    available_start: date,
    available_end: date,
    requested_start: date | None,
    requested_end: date | None,
) -> tuple[date, date]:
    start = requested_start or available_start
    end = requested_end or available_end

    if start < available_start:
        start = available_start
    if end > available_end:
        end = available_end
    if start > end:
        start, end = end, start

    return start, end


def _parse_loot_info(loot_info: Any) -> Dict[str, float]:
    parsed = {"money_looted": 0.0}

    if not isinstance(loot_info, str) or not loot_info.strip():
        return parsed

    money_match = re.search(r"\$([\d,]+)", loot_info)
    if money_match:
        parsed["money_looted"] = float(money_match.group(1).replace(",", ""))

    for resource in LOOT_RESOURCES:
        resource_match = re.search(rf"([\d,]+(?:\.\d+)?)\s+{resource.title()}\b", loot_info, re.IGNORECASE)
        if resource_match:
            parsed[f"{resource}_looted"] = float(resource_match.group(1).replace(",", ""))

    return parsed


def _normalize_attack(attack: Dict[str, Any], war: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(attack)
    attacker_id = attack.get("attacker_id")
    defender_id = attack.get("defender_id")

    normalized["att_id"] = attacker_id
    normalized["def_id"] = defender_id

    if str(attacker_id) == str(war.get("att_id")):
        normalized["att_alliance_id"] = war.get("att_alliance_id")
    elif str(attacker_id) == str(war.get("def_id")):
        normalized["att_alliance_id"] = war.get("def_alliance_id")

    if str(defender_id) == str(war.get("att_id")):
        normalized["def_alliance_id"] = war.get("att_alliance_id")
    elif str(defender_id) == str(war.get("def_id")):
        normalized["def_alliance_id"] = war.get("def_alliance_id")

    parsed_loot = _parse_loot_info(attack.get("loot_info"))
    for key, value in parsed_loot.items():
        if not normalized.get(key):
            normalized[key] = value
    return normalized


async def _attach_war_attacks(db: IRSWarsDB, wars: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    """Bulk-fetch all attacks in a single query instead of one query per war."""
    war_ids = [war["id"] for war in wars]
    attacks_by_war = await db.get_attacks_for_wars(war_ids)
    return [
        {
            **war,
            "attacks": [_normalize_attack(a, war) for a in attacks_by_war.get(war["id"], [])],
        }
        for war in wars
    ]

@router.get("/watch/wars")
async def get_watch_wars_data(request: Request, start_date: str | None = None, end_date: str | None = None):
    await _require_access(request)
    try:
        db = _get_watch_db()
        bounds = await db.get_alliance_war_date_bounds(WATCH_ALLIANCE_ID)

        if not bounds:
            return {
                **_build_watch_response({}, "No Nights Watch wars were found in the local database."),
                "meta": {
                    "available_start_date": None,
                    "available_end_date": None,
                    "selected_start_date": None,
                    "selected_end_date": None,
                    "war_count": 0,
                },
            }

        available_start = date.fromisoformat(bounds["min_date"])
        available_end = date.fromisoformat(bounds["max_date"])

        try:
            selected_start, selected_end = _clamp_date_window(
                available_start,
                available_end,
                _parse_api_date(start_date),
                _parse_api_date(end_date),
            )
        except ValueError:
            return {
                **_build_watch_response({}, "The selected Watch date range is invalid."),
                "meta": {
                    "available_start_date": available_start.isoformat(),
                    "available_end_date": available_end.isoformat(),
                    "selected_start_date": available_start.isoformat(),
                    "selected_end_date": available_end.isoformat(),
                    "war_count": 0,
                },
            }

        # Check cache before doing any heavy work
        cache_key = (selected_start.isoformat(), selected_end.isoformat())
        cached = _cache_get(cache_key)
        if cached is not None:
            logger.debug("watch/wars cache hit for %s – %s", selected_start, selected_end)
            return cached

        # Single query for both attacker + defender roles (avoids duplicate round-trip)
        unique_wars = await db.get_all_wars_for_alliance_in_range(
            WATCH_ALLIANCE_ID,
            start_date=selected_start,
            end_date=selected_end,
        )

        response_meta = {
            "available_start_date": available_start.isoformat(),
            "available_end_date": available_end.isoformat(),
            "selected_start_date": selected_start.isoformat(),
            "selected_end_date": selected_end.isoformat(),
            "war_count": len(unique_wars),
        }

        if not unique_wars:
            return {
                **_build_watch_response({}, "No Nights Watch wars were found in the selected date range."),
                "meta": response_meta,
            }

        # Fetch prices
        try:
            resource_prices = await get_resource_prices()
        except Exception as price_error:
            logger.error("Error fetching resource prices for watch page: %s", price_error, exc_info=True)
            return {
                **_build_watch_response({}, "Nights Watch war data is unavailable right now because resource pricing could not be loaded."),
                "meta": response_meta,
            }

        # Bulk-fetch all attacks in one query
        unique_wars = await _attach_war_attacks(db, unique_wars)

        # 2. Get the breakdown from the "correct" logic in WarsNetBD
        war_net_bd_cog = WarsNetBD(bot=None)
        nation_breakdown = await war_net_bd_cog._get_nation_breakdown(unique_wars, str(WATCH_ALLIANCE_ID), False, resource_prices)

        # Attach the raw wars list to each nation so _build_watch_response can build wars_with
        for nation_id, nation_data in nation_breakdown.items():
            nation_wars = [
                w for w in unique_wars
                if str(w.get("att_id")) == str(nation_id) or str(w.get("def_id")) == str(nation_id)
            ]
            # Compute per-opponent stats
            opp_stats: Dict[str, Any] = {}
            opp_names: Dict[str, str] = {}
            for w in nation_wars:
                nid_str = str(nation_id)
                if str(w.get("att_id")) == nid_str:
                    opp_id = str(w.get("def_id", ""))
                    opp_name = (w.get("defender") or {}).get("nation_name") or w.get("def_nation_name") or f"Nation {opp_id}"
                else:
                    opp_id = str(w.get("att_id", ""))
                    opp_name = (w.get("attacker") or {}).get("nation_name") or w.get("att_nation_name") or f"Nation {opp_id}"
                if opp_id:
                    opp_names[opp_id] = opp_name
                    opp_stats.setdefault(opp_id, []).append(w)

            per_opp: Dict[str, Any] = {}
            for opp_id, opp_wars in opp_stats.items():
                try:
                    c = await calculate_war_costs(opp_wars, resource_prices, team1_id_set={int(nation_id)})
                    t1 = c.get("team1", {})  # alliance nation's costs/gains
                    t2 = c.get("team2", {})  # opponent's costs/gains
                    sp = resource_prices.get("sell", {})
                    bp = resource_prices.get("buy", {})

                    # What WE (alliance nation) looted FROM the opponent
                    we_looted_cash = _as_number(t1.get("loot_received"))
                    we_looted_res: Dict[str, Any] = {}
                    for res, val in t1.get("resource_loot", {}).items():
                        price = sp.get(res, 0)
                        we_looted_res[res] = {"amount": val / price if price else 0, "value": val}

                    # What THEY (opponent) looted FROM us
                    they_looted_cash = _as_number(t2.get("loot_received"))
                    they_looted_res: Dict[str, Any] = {}
                    for res, val in t2.get("resource_loot", {}).items():
                        price = sp.get(res, 0)
                        they_looted_res[res] = {"amount": val / price if price else 0, "value": val}
                    they_looted_total = they_looted_cash + sum(t2.get("resource_loot", {}).values())

                    # Opponent's actual stats (t2 perspective)
                    opp_gross = _as_number(t2.get("gross"))
                    opp_gas_u = _as_number(t2.get("consumption", {}).get("gasoline"))
                    opp_mun_u = _as_number(t2.get("consumption", {}).get("munitions"))
                    opp_salvage = (t2.get("salvage", {}).get("aluminum", 0) * bp.get("aluminum", 0) +
                                   t2.get("salvage", {}).get("steel", 0) * bp.get("steel", 0))
                    # Opponent net = their gross cost - what they looted from us - their salvage
                    # Positive = they spent more than they gained = good for us
                    # Negative = they looted more than they spent = bad for us
                    opp_net = opp_gross - they_looted_total - opp_salvage

                    off_count = sum(1 for w in opp_wars if str(w.get("att_id")) == str(nation_id))
                    def_count = len(opp_wars) - off_count
                    per_opp[opp_id] = {
                        "name": opp_names[opp_id],
                        "offense_wars_count": off_count,
                        "defense_wars_count": def_count,
                        "gross_cost": opp_gross,
                        "net_damage": opp_net,
                        "total_gains": they_looted_total,
                        "damages": _as_number(t1.get("gross")),  # damage they dealt to us = our gross cost
                        "soldiers_lost": t2.get("units", {}).get("soldiers", {}).get("lost", 0),
                        "tanks_lost": t2.get("units", {}).get("tanks", {}).get("lost", 0),
                        "aircraft_lost": t2.get("units", {}).get("aircraft", {}).get("lost", 0),
                        "ships_lost": t2.get("units", {}).get("ships", {}).get("lost", 0),
                        "missiles_lost": t2.get("units", {}).get("missiles", {}).get("lost", 0),
                        "nukes_lost": t2.get("units", {}).get("nukes", {}).get("lost", 0),
                        "units_net": sum(t2.get("units", {}).get(u, {}).get("lost", 0) for u in ("soldiers","tanks","aircraft","ships","missiles","nukes")),
                        "units_total_cost": sum(t2.get("units", {}).get(u, {}).get("cost", 0) for u in ("soldiers","tanks","aircraft","ships","missiles","nukes")),
                        "gas_used": opp_gas_u,
                        "mun_used": opp_mun_u,
                        "gasoline_sell_value": opp_gas_u * sp.get("gasoline", 0),
                        "munitions_sell_value": opp_mun_u * sp.get("munitions", 0),
                        "consumption": opp_gas_u * sp.get("gasoline", 0) + opp_mun_u * sp.get("munitions", 0),
                        "infra_net": _as_number(t2.get("infra_lost_value")),
                        "infra_levels_lost": _as_number(t2.get("infra_destroyed")),
                        "improvements": _as_number(t2.get("improvements_lost")),
                        "improvements_count": _sum_numeric_mapping_values(t2.get("improvements_destroyed", {})),
                        "soldiers_lost_cost": t2.get("units", {}).get("soldiers", {}).get("cost", 0),
                        "tanks_lost_cost": t2.get("units", {}).get("tanks", {}).get("cost", 0),
                        "aircraft_lost_cost": t2.get("units", {}).get("aircraft", {}).get("cost", 0),
                        "ships_lost_cost": t2.get("units", {}).get("ships", {}).get("cost", 0),
                        "missiles_lost_cost": t2.get("units", {}).get("missiles", {}).get("cost", 0),
                        "nukes_lost_cost": t2.get("units", {}).get("nukes", {}).get("cost", 0),
                        # loot_breakdown = what THEY looted from us (shown in gains cell, red = bad for us)
                        "loot_breakdown": {
                            "cash": they_looted_cash,
                            "resources": they_looted_res,
                        },
                        # opp_loot_breakdown = what WE looted from them (shown in gains cell, green = good for us)
                        "opp_loot_breakdown": {
                            "cash": we_looted_cash,
                            "resources": we_looted_res,
                        },
                    }
                except Exception as opp_err:
                    logger.warning("per-opp stats error nation=%s opp=%s: %s", nation_id, opp_id, opp_err)
                    per_opp[opp_id] = {"name": opp_names[opp_id]}

            nation_data["_nation_wars"] = nation_wars
            nation_data["_per_opp"] = per_opp

        result = {
            **_build_watch_response(nation_breakdown, resource_prices=resource_prices),
            "meta": response_meta,
        }
        _cache_set(cache_key, result)
        return result

    except Exception as e:
        logger.error(f"Error getting war data: {e}", exc_info=True)
        return {
            **_build_watch_response({}, "Failed to retrieve Nights Watch war data."),
            "meta": {
                "available_start_date": None,
                "available_end_date": None,
                "selected_start_date": None,
                "selected_end_date": None,
                "war_count": 0,
            },
        }


@router.get("/watch/wars/all-nations")
async def get_watch_wars_all_nations(request: Request, start_date: str | None = None, end_date: str | None = None):
    """Return war stats for NW nations covering ALL their wars (not just NW-tagged wars)."""
    await _require_access(request)
    try:
        from Systems.Functions.irs_nations_db import IRSNationsDB

        # ── Load NW nation IDs from the nations DB ────────────────────────────
        nations_db = IRSNationsDB(NATIONS_DB_PATH)
        nw_nations = await nations_db.get_all_nations()
        nw_nation_ids = [int(n["id"]) for n in nw_nations if n.get("id")]

        if not nw_nation_ids:
            return {
                **_build_watch_response({}, "No Nights Watch nations found in the database."),
                "meta": {
                    "available_start_date": None,
                    "available_end_date": None,
                    "selected_start_date": None,
                    "selected_end_date": None,
                    "war_count": 0,
                },
            }

        db = _get_watch_db()
        bounds = await db.get_wars_for_nations_date_bounds(nw_nation_ids)

        if not bounds:
            return {
                **_build_watch_response({}, "No wars were found for NW nations in the local database."),
                "meta": {
                    "available_start_date": None,
                    "available_end_date": None,
                    "selected_start_date": None,
                    "selected_end_date": None,
                    "war_count": 0,
                },
            }

        available_start = date.fromisoformat(bounds["min_date"])
        available_end = date.fromisoformat(bounds["max_date"])

        try:
            selected_start, selected_end = _clamp_date_window(
                available_start,
                available_end,
                _parse_api_date(start_date),
                _parse_api_date(end_date),
            )
        except ValueError:
            return {
                **_build_watch_response({}, "The selected date range is invalid."),
                "meta": {
                    "available_start_date": available_start.isoformat(),
                    "available_end_date": available_end.isoformat(),
                    "selected_start_date": available_start.isoformat(),
                    "selected_end_date": available_end.isoformat(),
                    "war_count": 0,
                },
            }

        cache_key = ("all_nations", selected_start.isoformat(), selected_end.isoformat())
        cached = _cache_get(cache_key)
        if cached is not None:
            logger.debug("watch/wars/all-nations cache hit for %s – %s", selected_start, selected_end)
            return cached

        # Fetch all wars involving any NW nation (regardless of alliance tag)
        unique_wars = await db.get_wars_for_nations_in_range(
            nw_nation_ids,
            start_date=selected_start,
            end_date=selected_end,
        )

        response_meta = {
            "available_start_date": available_start.isoformat(),
            "available_end_date": available_end.isoformat(),
            "selected_start_date": selected_start.isoformat(),
            "selected_end_date": selected_end.isoformat(),
            "war_count": len(unique_wars),
        }

        if not unique_wars:
            return {
                **_build_watch_response({}, "No wars were found for NW nations in the selected date range."),
                "meta": response_meta,
            }

        try:
            resource_prices = await get_resource_prices()
        except Exception as price_error:
            logger.error("Error fetching resource prices for all-nations watch: %s", price_error, exc_info=True)
            return {
                **_build_watch_response({}, "War data is unavailable because resource pricing could not be loaded."),
                "meta": response_meta,
            }

        unique_wars = await _attach_war_attacks(db, unique_wars)

        # _get_nation_breakdown discovers nations by matching att/def_alliance_id.
        # Wars fought outside NW won't have that tag, so we patch a sentinel alliance
        # ID onto each war side that belongs to a NW nation, then strip it after.
        NW_SENTINEL = str(WATCH_ALLIANCE_ID)
        nw_nation_id_strs = {str(nid) for nid in nw_nation_ids}

        patched_wars = []
        for w in unique_wars:
            pw = dict(w)
            if str(pw.get("att_id")) in nw_nation_id_strs:
                pw["att_alliance_id"] = WATCH_ALLIANCE_ID
            if str(pw.get("def_id")) in nw_nation_id_strs:
                pw["def_alliance_id"] = WATCH_ALLIANCE_ID
            patched_wars.append(pw)

        # Build breakdown treating NW as the alliance (so costs/gains are from NW perspective)
        war_net_bd_cog = WarsNetBD(bot=None)
        nation_breakdown = await war_net_bd_cog._get_nation_breakdown(
            patched_wars, str(WATCH_ALLIANCE_ID), False, resource_prices
        )

        # Only keep rows for NW nations (filter out opponents that slipped in)
        nation_breakdown = {k: v for k, v in nation_breakdown.items() if str(k) in nw_nation_id_strs}

        for nation_id, nation_data in nation_breakdown.items():
            nation_wars = [
                w for w in patched_wars
                if str(w.get("att_id")) == str(nation_id) or str(w.get("def_id")) == str(nation_id)
            ]
            opp_stats: Dict[str, Any] = {}
            opp_names: Dict[str, str] = {}
            for w in nation_wars:
                nid_str = str(nation_id)
                if str(w.get("att_id")) == nid_str:
                    opp_id = str(w.get("def_id", ""))
                    opp_name = (w.get("defender") or {}).get("nation_name") or w.get("def_nation_name") or f"Nation {opp_id}"
                else:
                    opp_id = str(w.get("att_id", ""))
                    opp_name = (w.get("attacker") or {}).get("nation_name") or w.get("att_nation_name") or f"Nation {opp_id}"
                if opp_id:
                    opp_names[opp_id] = opp_name
                    opp_stats.setdefault(opp_id, []).append(w)

            per_opp: Dict[str, Any] = {}
            for opp_id, opp_wars in opp_stats.items():
                try:
                    c = await calculate_war_costs(opp_wars, resource_prices, team1_id_set={int(nation_id)})
                    t1 = c.get("team1", {})
                    t2 = c.get("team2", {})
                    sp = resource_prices.get("sell", {})
                    bp = resource_prices.get("buy", {})
                    we_looted_cash = _as_number(t1.get("loot_received"))
                    we_looted_res: Dict[str, Any] = {}
                    for res, val in t1.get("resource_loot", {}).items():
                        price = sp.get(res, 0)
                        we_looted_res[res] = {"amount": val / price if price else 0, "value": val}
                    they_looted_cash = _as_number(t2.get("loot_received"))
                    they_looted_res: Dict[str, Any] = {}
                    for res, val in t2.get("resource_loot", {}).items():
                        price = sp.get(res, 0)
                        they_looted_res[res] = {"amount": val / price if price else 0, "value": val}
                    they_looted_total = they_looted_cash + sum(t2.get("resource_loot", {}).values())
                    opp_gross = _as_number(t2.get("gross"))
                    opp_gas_u = _as_number(t2.get("consumption", {}).get("gasoline"))
                    opp_mun_u = _as_number(t2.get("consumption", {}).get("munitions"))
                    opp_salvage = (t2.get("salvage", {}).get("aluminum", 0) * bp.get("aluminum", 0) +
                                   t2.get("salvage", {}).get("steel", 0) * bp.get("steel", 0))
                    opp_net = opp_gross - they_looted_total - opp_salvage
                    off_count = sum(1 for w in opp_wars if str(w.get("att_id")) == str(nation_id))
                    def_count = len(opp_wars) - off_count
                    per_opp[opp_id] = {
                        "name": opp_names[opp_id],
                        "offense_wars_count": off_count,
                        "defense_wars_count": def_count,
                        "gross_cost": opp_gross,
                        "net_damage": opp_net,
                        "total_gains": they_looted_total,
                        "damages": _as_number(t1.get("gross")),
                        "soldiers_lost": t2.get("units", {}).get("soldiers", {}).get("lost", 0),
                        "tanks_lost": t2.get("units", {}).get("tanks", {}).get("lost", 0),
                        "aircraft_lost": t2.get("units", {}).get("aircraft", {}).get("lost", 0),
                        "ships_lost": t2.get("units", {}).get("ships", {}).get("lost", 0),
                        "missiles_lost": t2.get("units", {}).get("missiles", {}).get("lost", 0),
                        "nukes_lost": t2.get("units", {}).get("nukes", {}).get("lost", 0),
                        "units_net": sum(t2.get("units", {}).get(u, {}).get("lost", 0) for u in ("soldiers","tanks","aircraft","ships","missiles","nukes")),
                        "units_total_cost": sum(t2.get("units", {}).get(u, {}).get("cost", 0) for u in ("soldiers","tanks","aircraft","ships","missiles","nukes")),
                        "gas_used": opp_gas_u,
                        "mun_used": opp_mun_u,
                        "gasoline_sell_value": opp_gas_u * sp.get("gasoline", 0),
                        "munitions_sell_value": opp_mun_u * sp.get("munitions", 0),
                        "consumption": opp_gas_u * sp.get("gasoline", 0) + opp_mun_u * sp.get("munitions", 0),
                        "infra_net": _as_number(t2.get("infra_lost_value")),
                        "infra_levels_lost": _as_number(t2.get("infra_destroyed")),
                        "improvements": _as_number(t2.get("improvements_lost")),
                        "improvements_count": _sum_numeric_mapping_values(t2.get("improvements_destroyed", {})),
                        "soldiers_lost_cost": t2.get("units", {}).get("soldiers", {}).get("cost", 0),
                        "tanks_lost_cost": t2.get("units", {}).get("tanks", {}).get("cost", 0),
                        "aircraft_lost_cost": t2.get("units", {}).get("aircraft", {}).get("cost", 0),
                        "ships_lost_cost": t2.get("units", {}).get("ships", {}).get("cost", 0),
                        "missiles_lost_cost": t2.get("units", {}).get("missiles", {}).get("cost", 0),
                        "nukes_lost_cost": t2.get("units", {}).get("nukes", {}).get("cost", 0),
                        "loot_breakdown": {"cash": they_looted_cash, "resources": they_looted_res},
                        "opp_loot_breakdown": {"cash": we_looted_cash, "resources": we_looted_res},
                    }
                except Exception as opp_err:
                    logger.warning("per-opp stats error nation=%s opp=%s: %s", nation_id, opp_id, opp_err)
                    per_opp[opp_id] = {"name": opp_names[opp_id]}

            nation_data["_nation_wars"] = nation_wars
            nation_data["_per_opp"] = per_opp

        result = {
            **_build_watch_response(nation_breakdown, resource_prices=resource_prices),
            "meta": response_meta,
        }
        _cache_set(cache_key, result)
        return result

    except Exception as e:
        logger.error(f"Error getting all-nations war data: {e}", exc_info=True)
        return {
            **_build_watch_response({}, "Failed to retrieve war data."),
            "meta": {
                "available_start_date": None,
                "available_end_date": None,
                "selected_start_date": None,
                "selected_end_date": None,
                "war_count": 0,
            },
        }


# ── Nation rank helper ────────────────────────────────────────────────────────

RANK_CATEGORIES = [
    {"id": "lowest_cost",        "label": "Lowest Cost",               "field": "gross_cost",                "asc": True,  "prefix": "c"},
    {"id": "highest_cost",       "label": "Highest Cost",              "field": "gross_cost",                "asc": False, "prefix": "c"},
    {"id": "best_net",           "label": "Best Net",                  "field": "net_damage",                "asc": True,  "prefix": "n"},
    {"id": "most_damage",        "label": "Most Damage Dealt",         "field": "total_damages",             "asc": False, "prefix": "n"},
    {"id": "most_off_wars",      "label": "Most Offensive Wars",       "field": "offense_wars_count",        "asc": False, "prefix": "c"},
    {"id": "most_def_wars",      "label": "Most Defensive Wars",       "field": "defense_wars_count",        "asc": False, "prefix": "c"},
    {"id": "most_raid_wars",     "label": "Most Raid Wars",            "field": "raid_wars_count",           "asc": False, "prefix": "w"},
    {"id": "most_attrition_wars","label": "Most Attrition Wars",       "field": "attrition_wars_count",      "asc": False, "prefix": "w"},
    {"id": "most_wins",          "label": "Most Wins",                 "field": "wins_count",                "asc": False, "prefix": "d"},
    {"id": "most_losses",        "label": "Most Losses",               "field": "losses_count",              "asc": False, "prefix": "p"},
    {"id": "most_draws",         "label": "Most Draws",                "field": "draws_count",               "asc": False, "prefix": "d"},
    {"id": "most_peace",         "label": "Most Peace",                "field": "peace_count",               "asc": False, "prefix": "p"},
    {"id": "most_money_loot",    "label": "Most Money Looted",         "field": "gains_cash",                "asc": False, "prefix": "m"},
    {"id": "most_res_loot",      "label": "Most Resource Value Looted","field": "gains_res_total",           "asc": False, "prefix": "m"},
    {"id": "most_infra_lvl",     "label": "Most Infra Levels Destroyed","field": "enemy_infra_destroyed",    "asc": False, "prefix": "r"},
    {"id": "most_infra_val",     "label": "Most Infra Value Destroyed", "field": "enemy_infra_destroyed_value","asc": False,"prefix": "r"},
    {"id": "most_soldiers_killed",  "label": "Most Soldiers Killed",      "field": "enemy_soldiers_killed",     "asc": False, "prefix": "k"},
    {"id": "most_tanks_killed",     "label": "Most Tanks Killed",         "field": "enemy_tanks_killed",        "asc": False, "prefix": "k"},
    {"id": "most_aircraft_killed",  "label": "Most Aircraft Killed",      "field": "enemy_aircraft_killed",     "asc": False, "prefix": "k"},
    {"id": "most_ships_killed",     "label": "Most Ships Killed",         "field": "enemy_ships_killed",        "asc": False, "prefix": "k"},
    {"id": "most_soldiers_lost",    "label": "Most Soldiers Lost",        "field": "soldiers_lost",             "asc": False, "prefix": "l"},
    {"id": "most_tanks_lost",       "label": "Most Tanks Lost",           "field": "tanks_lost",                "asc": False, "prefix": "l"},
    {"id": "most_aircraft_lost",    "label": "Most Aircraft Lost",        "field": "aircraft_lost",             "asc": False, "prefix": "l"},
    {"id": "most_ships_lost",       "label": "Most Ships Lost",           "field": "ships_lost",                "asc": False, "prefix": "l"},
    {"id": "most_missiles_sent",    "label": "Most Missiles Sent",        "field": "missiles_hit",              "asc": False, "prefix": "a"},
    {"id": "most_missiles_miss",    "label": "Most Missiles Missed",      "field": "missiles_missed",           "asc": False, "prefix": "a"},
    {"id": "most_missiles_eat",     "label": "Most Missiles Eaten",       "field": "missiles_eaten",            "asc": False, "prefix": "a"},
    {"id": "most_missiles_blk",     "label": "Most Missiles Blocked",     "field": "missiles_blocked",          "asc": False, "prefix": "a"},
    {"id": "most_nukes_sent",       "label": "Most Nukes Sent",           "field": "nukes_hit",                 "asc": False, "prefix": "a"},
    {"id": "most_nukes_miss",       "label": "Most Nukes Missed",         "field": "nukes_missed",              "asc": False, "prefix": "a"},
    {"id": "most_nukes_eat",        "label": "Most Nukes Eaten",          "field": "nukes_eaten",               "asc": False, "prefix": "a"},
    {"id": "most_nukes_blk",        "label": "Most Nukes Blocked",        "field": "nukes_blocked",             "asc": False, "prefix": "a"},
]

LOOT_RES_KEYS = ("coal","oil","uranium","iron","bauxite","lead","gasoline","munitions","steel","aluminum","food")


def _enrich_nation_for_rank(n: Dict[str, Any]) -> Dict[str, Any]:
    lb = n.get("loot_breakdown") or {}
    n["gains_cash"] = lb.get("cash") or 0
    res = (lb.get("resources") or {})
    n["gains_res_total"] = sum((res.get(r) or {}).get("value", 0) for r in LOOT_RES_KEYS)
    return n


def _get_period_dates(period: str):
    from datetime import datetime, timedelta
    now = datetime.utcnow().date()
    y, m = now.year, now.month
    dow = now.weekday()  # Monday=0
    if period == "this_month":
        import calendar
        start = date(y, m, 1)
        end = date(y, m, calendar.monthrange(y, m)[1])
    elif period == "last_month":
        import calendar
        lm = m - 1 if m > 1 else 12
        ly = y if m > 1 else y - 1
        start = date(ly, lm, 1)
        end = date(ly, lm, calendar.monthrange(ly, lm)[1])
    elif period == "this_week":
        days_since_sunday = (dow + 1) % 7  # Sunday=0
        start = now - timedelta(days=days_since_sunday)
        end = start + timedelta(days=6)
    elif period == "last_week":
        days_since_sunday = (dow + 1) % 7
        start = now - timedelta(days=days_since_sunday + 7)
        end = start + timedelta(days=6)
    else:
        return None, None
    return start, end


async def _get_nation_ranks_for_period(nation_name: str, period: str, start: date = None, end: date = None) -> list:
    """Return list of {category, rank, total, prefix} for a nation in a given period (rank ≤ 3 only)."""
    if start is None or end is None:
        start, end = _get_period_dates(period)
    if not start:
        return []

    try:
        db = _get_watch_db()
        unique_wars = await db.get_all_wars_for_alliance_in_range(WATCH_ALLIANCE_ID, start_date=start, end_date=end)
        if not unique_wars:
            return []

        resource_prices = await get_resource_prices()
        unique_wars = await _attach_war_attacks(db, unique_wars)
        war_net_bd_cog = WarsNetBD(bot=None)
        nation_breakdown = await war_net_bd_cog._get_nation_breakdown(unique_wars, str(WATCH_ALLIANCE_ID), False, resource_prices)

        nations = {k: _enrich_nation_for_rank(dict(v)) for k, v in nation_breakdown.items()}
        name_lower = nation_name.lower()
        from collections import defaultdict

        results = []
        for cat in RANK_CATEGORIES:
            field = cat["field"]
            asc = cat["asc"]
            ranked = sorted(
                [(k, v) for k, v in nations.items() if v.get(field) not in (None, 0)],
                key=lambda x: x[1].get(field, 0),
                reverse=not asc,
            )
            total = len(ranked)

            # Assign dense ranks (ties share the same rank)
            dense_ranks = []  # list of (k, v, dense_rank)
            for i, (k, v) in enumerate(ranked):
                if i > 0 and v.get(field) == ranked[i - 1][1].get(field):
                    dense_ranks.append((k, v, dense_ranks[-1][2]))
                else:
                    dense_ranks.append((k, v, i + 1))

            # Build a map: dense_rank → list of names at that rank
            rank_names: dict = defaultdict(list)
            for k, v, r in dense_ranks:
                rank_names[r].append(v.get("name") or k)

            for k, v, rank in dense_ranks:
                if (v.get("name") or k).lower() == name_lower:
                    if rank <= 3:
                        tied_names = rank_names[rank]
                        tied_count = len(tied_names)
                        results.append({
                            "category_id": cat["id"],
                            "category_label": cat["label"],
                            "prefix": cat["prefix"],
                            "rank": rank,
                            "total": total,
                            "value": v.get(field),
                            "tied_count": tied_count,
                            "tied_names": tied_names,
                        })
                    break
        return results
    except Exception as e:
        logger.warning("nation-ranks error for %s/%s: %s", nation_name, period, e)
        return []


@router.get("/watch/nation-ranks/{nation_name}")
async def get_nation_ranks(request: Request, nation_name: str):
    """Return all periods (current + historical) where the nation ranked top 3."""
    await _require_access(request)
    import sqlite3, calendar as _cal
    import datetime as _datetime_mod
    from datetime import date as _date

    # ── Compute canonical week/month bounds (identical logic to get_available_periods) ──
    today = _date.today()
    days_since_sunday = (today.weekday() + 1) % 7   # Mon=0…Sun=6 → 0 on Sun
    cur_week_sun = today - _datetime_mod.timedelta(days=days_since_sunday)
    cur_week_sat = cur_week_sun + _datetime_mod.timedelta(days=6)
    cur_month_key = today.strftime("%Y-%m")

    # Current periods use the exact same date windows as get_available_periods
    this_week_task  = _get_nation_ranks_for_period(
        nation_name, "custom",
        start=cur_week_sun,
        end=cur_week_sat,
    )
    this_month_task = _get_nation_ranks_for_period(nation_name, "this_month")

    # ── Historical periods from DB ────────────────────────────────────────────
    db = _get_watch_db()
    try:
        def _fetch_periods():
            import sqlite3 as _sq
            with _sq.connect(db.db_path) as conn:
                return conn.execute(
                    """
                    SELECT DISTINCT
                        date(substr(date, 1, 10)) AS d,
                        strftime('%Y-%m', substr(date, 1, 10)) AS month_key,
                        strftime('%Y-%m-01', substr(date, 1, 10)) AS month_start
                    FROM wars
                    WHERE att_alliance_id = ? OR def_alliance_id = ?
                    ORDER BY date DESC
                    """,
                    (WATCH_ALLIANCE_ID, WATCH_ALLIANCE_ID),
                ).fetchall()
        rows = await asyncio.to_thread(_fetch_periods)
    except Exception as e:
        logger.warning("nation-ranks: failed to fetch periods: %s", e)
        rows = []

    # Deduplicate and build period list using Sunday–Saturday weeks (matching leaderboard page)
    seen_weeks: dict = {}
    seen_months: dict = {}
    for d_str, month_key, month_start in rows:
        if not d_str:
            continue
        d = _datetime_mod.date.fromisoformat(d_str)
        # Compute Sunday–Saturday week for this date
        dsun = (d.weekday() + 1) % 7
        week_sun = d - _datetime_mod.timedelta(days=dsun)
        week_sat = week_sun + _datetime_mod.timedelta(days=6)
        week_key = week_sun.isoformat()  # use Sunday date as unique key
        if week_key not in seen_weeks and week_sun != cur_week_sun:
            def _fmt_week(iso: str) -> str:
                d2 = _datetime_mod.date.fromisoformat(iso)
                return f"{d2.month}/{d2.day:02d}/{str(d2.year)[2:]}"
            seen_weeks[week_key] = {"start": week_sun.isoformat(), "end": week_sat.isoformat(),
                                    "label": f"{_fmt_week(week_sun.isoformat())} - {_fmt_week(week_sat.isoformat())}"}
        if month_key and month_key not in seen_months and month_key != cur_month_key:
            y2, m2 = int(month_key[:4]), int(month_key[5:7])
            last_day = _cal.monthrange(y2, m2)[1]
            seen_months[month_key] = {
                "start": month_start,
                "end": f"{y2:04d}-{m2:02d}-{last_day:02d}",
                "label": __import__('datetime').date(y2, m2, 1).strftime("%B %Y"),
            }

    # Build async tasks for all historical periods
    hist_week_tasks  = [(info, _get_nation_ranks_for_period(nation_name, "custom",
                          start=date.fromisoformat(info["start"]),
                          end=date.fromisoformat(info["end"])))
                        for info in seen_weeks.values()]
    hist_month_tasks = [(info, _get_nation_ranks_for_period(nation_name, "custom",
                          start=date.fromisoformat(info["start"]),
                          end=date.fromisoformat(info["end"])))
                        for info in seen_months.values()]

    # Gather everything concurrently
    all_tasks = [this_week_task, this_month_task] + \
                [t for _, t in hist_week_tasks] + \
                [t for _, t in hist_month_tasks]
    results = await asyncio.gather(*all_tasks)

    this_week_ranks  = results[0]
    this_month_ranks = results[1]
    offset = 2

    periods = []
    if this_week_ranks:
        periods.append({"label": "This Week", "ranks": this_week_ranks})
    if this_month_ranks:
        periods.append({"label": "This Month", "ranks": this_month_ranks})

    for i, (info, _) in enumerate(hist_week_tasks):
        ranks = results[offset + i]
        if ranks:
            periods.append({"label": info["label"], "ranks": ranks})
    offset += len(hist_week_tasks)

    for i, (info, _) in enumerate(hist_month_tasks):
        ranks = results[offset + i]
        if ranks:
            periods.append({"label": info["label"], "ranks": ranks})

    return {"nation_name": nation_name, "periods": periods}


@router.post("/watch/invalidate-cache")
async def invalidate_watch_cache(request: Request):
    """Clear the wars response cache and reset the DB singleton.
    Call this after syncing new war data so the next page load is fresh.
    """
    await _require_access(request)
    invalidate_wars_cache()
    logger.info("watch cache invalidated via API")
    return {"ok": True, "message": "Watch cache cleared."}


@router.get("/watch/periods")
async def get_available_periods(request: Request):
    """Return all distinct Sun–Sat weeks and calendar months that have war data in the DB.

    Each entry is tagged with `is_current` so the frontend can highlight the
    current week/month without doing its own timezone-sensitive date math.
    """
    await _require_access(request)
    db = _get_watch_db()
    try:
        import calendar
        from datetime import date as _date, timedelta

        def _fetch_dates():
            import sqlite3 as _sq
            with _sq.connect(db.db_path) as conn:
                return [r[0] for r in conn.execute(
                    "SELECT DISTINCT date(substr(date, 1, 10)) AS d FROM wars "
                    "WHERE att_alliance_id = ? OR def_alliance_id = ? ORDER BY d ASC",
                    (WATCH_ALLIANCE_ID, WATCH_ALLIANCE_ID),
                ).fetchall() if r[0]]
        all_dates = await asyncio.to_thread(_fetch_dates)

        if not all_dates:
            return {"weeks": [], "months": [], "dates": [],
                    "current_week_key": None, "current_month_key": None}

        # ── Determine today's Sun–Sat week and calendar month (server-side) ──
        today = _date.today()
        days_since_sunday = (today.weekday() + 1) % 7   # Mon=0…Sun=6 → 0 on Sun
        current_week_sun  = today - timedelta(days=days_since_sunday)
        current_week_key  = current_week_sun.isoformat()          # "YYYY-MM-DD" of Sunday
        current_month_key = today.strftime("%Y-%m")               # "YYYY-MM"

        # ── Build Sun–Sat week buckets ────────────────────────────────────────
        seen_weeks: dict  = {}   # sunday-ISO → {start, end}
        seen_months: dict = {}   # "YYYY-MM"  → {start}

        for ds in all_dates:
            d = _date.fromisoformat(ds)

            # Sun–Sat week — key is the Sunday date string
            dsun = (d.weekday() + 1) % 7
            week_sun = d - timedelta(days=dsun)
            week_sat = week_sun + timedelta(days=6)
            wk = week_sun.isoformat()
            if wk not in seen_weeks:
                seen_weeks[wk] = {"start": week_sun.isoformat(), "end": week_sat.isoformat()}

            # Calendar month
            mk = d.strftime("%Y-%m")
            if mk not in seen_months:
                seen_months[mk] = {"start": d.strftime("%Y-%m-01")}

        # ── Format helpers ────────────────────────────────────────────────────
        def _fmt_date(iso: str) -> str:
            d = _date.fromisoformat(iso)
            return f"{d.month}/{d.day:02d}/{str(d.year)[2:]}"

        # ── Weeks — newest first, tag current ────────────────────────────────
        weeks = sorted(
            [
                {
                    "key":        wk,
                    "start":      wv["start"],
                    "end":        wv["end"],
                    "label":      f"{_fmt_date(wv['start'])} – {_fmt_date(wv['end'])}",
                    "is_current": wk == current_week_key,
                }
                for wk, wv in seen_weeks.items()
            ],
            key=lambda x: x["start"],
            reverse=True,
        )

        # ── Months — newest first, tag current ───────────────────────────────
        months = []
        for mk, mv in seen_months.items():
            y, m = int(mk[:4]), int(mk[5:7])
            last_day = calendar.monthrange(y, m)[1]
            months.append({
                "key":        mk,
                "start":      mv["start"],
                "end":        f"{y:04d}-{m:02d}-{last_day:02d}",
                "label":      _date(y, m, 1).strftime("%B %Y"),
                "is_current": mk == current_month_key,
            })
        months.sort(key=lambda x: x["start"], reverse=True)

        return {
            "weeks":              weeks,
            "months":             months,
            "dates":              all_dates,
            "current_week_key":   current_week_key,
            "current_month_key":  current_month_key,
        }

    except Exception as e:
        logger.error(f"Error fetching available periods: {e}")
        return {"weeks": [], "months": [], "error": str(e)}


# ── Nations DB endpoints ──────────────────────────────────────────────────────

@router.get("/watch/nations")
async def get_watch_nations(request: Request):
    """Return all nations from the NW Nations DB with their city aggregates."""
    await _require_access(request)
    try:
        from Systems.Functions.irs_nations_db import IRSNationsDB
        import sqlite3

        db = IRSNationsDB(NATIONS_DB_PATH)
        nations = await db.get_all_nations()

        # Aggregate city improvements per nation — run in thread (blocking SQLite)
        def _fetch_city_agg():
            import sqlite3 as _sq
            with _sq.connect(NATIONS_DB_PATH) as conn:
                conn.row_factory = _sq.Row
                return conn.execute("""
                    SELECT nation_id,
                        COUNT(*) as city_count,
                        SUM(infrastructure) as total_infra,
                        AVG(infrastructure) as avg_infra,
                        SUM(land) as total_land,
                        AVG(land) as avg_land,
                        SUM(coal_power+oil_power+nuclear_power+wind_power) as total_power,
                        SUM(coal_mine+oil_well+uranium_mine+lead_mine+iron_mine+bauxite_mine+farm) as raw_resources,
                        SUM(oil_refinery+aluminum_refinery+steel_mill+munitions_factory+factory) as manufacturing,
                        SUM(police_station+hospital+recycling_center+subway) as civil,
                        SUM(supermarket+bank+shopping_mall+stadium) as commerce,
                        SUM(barracks+hangar+drydock) as mil_buildings,
                        SUM(barracks) as barracks,
                        AVG(barracks) as avg_barracks,
                        SUM(hangar) as hangars,
                        AVG(hangar) as avg_hangars,
                        SUM(drydock) as drydocks,
                        AVG(drydock) as avg_drydocks,
                        SUM(factory) as factories,
                        AVG(factory) as avg_factories,
                        SUM(barracks+hangar+drydock+factory+oil_refinery+aluminum_refinery+steel_mill+munitions_factory+coal_power+oil_power+nuclear_power+wind_power+coal_mine+oil_well+uranium_mine+lead_mine+iron_mine+bauxite_mine+farm+police_station+hospital+recycling_center+subway+supermarket+bank+shopping_mall+stadium) as total_improvements
                    FROM cities GROUP BY nation_id
                """).fetchall()
        city_rows = await asyncio.to_thread(_fetch_city_agg)

        city_map = {r["nation_id"]: dict(r) for r in city_rows}

        # Fetch active war counts (off/def) per nation from wars DB
        # Used as a fallback only — the nation record's offensive/defensive_wars_count
        # fields (from the PnW API) are authoritative for all wars, not just NW wars.
        active_war_counts: dict = {}
        try:
            wars_db = _get_watch_db()
            active_war_counts = await wars_db.get_active_war_counts()
        except Exception as _e:
            logger.warning(f"Could not load active war counts: {_e}")

        result = []
        for n in nations:
            nid = n["id"]
            agg = city_map.get(nid, {})
            # Calculate MMR: avg barracks/factories/hangars/drydocks per city, rounded to 1dp
            city_count = agg.get("city_count") or 1
            avg_b = round((agg.get('barracks') or 0)/city_count, 1)
            avg_f = round((agg.get('factories') or 0)/city_count, 1)
            avg_h = round((agg.get('hangars') or 0)/city_count, 1)
            avg_d = round((agg.get('drydocks') or 0)/city_count, 1)
            mmr = f"{avg_b:g}/{avg_f:g}/{avg_h:g}/{avg_d:g}"
            # MMR score: distance from full MMR (5/5/5/3) — lower = closer to full
            # Use sum of deficits so 0 = perfect full MMR
            FULL_MMR = (5, 5, 5, 3)
            mmr_deficit = (
                max(0, FULL_MMR[0] - avg_b) +
                max(0, FULL_MMR[1] - avg_f) +
                max(0, FULL_MMR[2] - avg_h) +
                max(0, FULL_MMR[3] - avg_d)
            )
            # Count owned projects
            project_fields = [
                'iron_dome','vital_defense_system','missile_launch_pad','nuclear_research_facility',
                'nuclear_launch_facility','propaganda_bureau','military_research_center','space_program',
                'spy_satellite','surveillance_network','guiding_satellite','telecommunications_satellite',
                'central_intelligence_agency','fallout_shelter','military_doctrine','military_salvage',
                'pirate_economy','advanced_pirate_economy','arms_stockpile','bauxite_works','iron_works',
                'emergency_gasoline_reserve','uranium_enrichment_program','green_technologies',
                'recycling_initiative','mass_irrigation','arable_land_agency','international_trade_center',
                'clinical_research_center','specialized_police_training_program','bureau_of_domestic_affairs',
                'government_support_agency','center_for_civil_engineering','advanced_engineering_corps',
                'activity_center','research_and_development_center','moon_landing','mars_landing',
            ]
            total_projects = sum(1 for f in project_fields if n.get(f))
            avg_improvements = round((agg.get("total_improvements") or 0) / city_count, 1) if city_count else 0
            # Status sort order: 0=Active, 1=Beige, 2=VM, 3=Grey, 4=Applicant
            color = (n.get("color") or "").lower()
            raw_pos = (n.get("alliance_position") or "")
            # Strip enum prefix e.g. "AlliancePositionEnum.APPLICANT" → "APPLICANT"
            clean_pos = raw_pos.split(".")[-1].upper() if "." in raw_pos else raw_pos.upper()
            if clean_pos == "APPLICANT":
                status_order = 4
            elif (n.get("vacation_mode_turns") or 0) > 0:
                status_order = 2
            elif (n.get("beige_turns") or 0) > 0:
                status_order = 1
            elif color in ("gray", "grey"):
                status_order = 3
            else:
                status_order = 0
            # War counts: prefer the API-sourced fields on the nation record
            # (offensive_wars_count / defensive_wars_count) — these reflect ALL
            # active wars, not just NW wars. Fall back to the wars DB count only
            # when the nation record doesn't have them (e.g. very stale data).
            api_off = n.get("offensive_wars_count")
            api_def = n.get("defensive_wars_count")
            db_counts = active_war_counts.get(nid, {"off": 0, "def": 0})
            war_counts = {
                "off": int(api_off) if api_off is not None else db_counts["off"],
                "def": int(api_def) if api_def is not None else db_counts["def"],
            }
            result.append({**n, "city_agg": {**agg, "mmr": mmr, "mmr_deficit": mmr_deficit, "avg_improvements": avg_improvements}, "total_projects": total_projects, "status_order": status_order, "active_war_counts": war_counts})

        return {"nations": result, "count": len(result)}

    except Exception as e:
        logger.error(f"get_watch_nations error: {e}", exc_info=True)
        return {"nations": [], "count": 0, "error": str(e)}


@router.get("/watch/nations/{nation_id}")
async def get_watch_nation_detail(request: Request, nation_id: int):
    """Return full nation detail including all cities."""
    await _require_access(request)
    try:
        from Systems.Functions.irs_nations_db import IRSNationsDB

        db = IRSNationsDB(NATIONS_DB_PATH)
        nation = await db.get_nation(nation_id)
        if not nation:
            return {"error": "Nation not found"}
        cities = await db.get_cities_for_nation(nation_id)
        return {"nation": nation, "cities": cities}

    except Exception as e:
        logger.error(f"get_watch_nation_detail({nation_id}) error: {e}", exc_info=True)
        return {"error": str(e)}


@router.get("/watch/revenue")
async def get_watch_revenue(request: Request):
    """Calculate and return revenue for all NW nations.
    
    Uses the same calculate_full_revenue_with_query logic as the Discord rev command.
    All upkeeps (military, improvement, power, resource) are pre-deducted.
    Alliance tax is informational only — not deducted from displayed revenue.
    """
    await _require_access(request)
    try:
        from Systems.Functions.irs_nations_db import IRSNationsDB
        from Systems.PnW.Util.rev_correct import calculate_full_revenue_with_query
        from Systems.Functions.database_manager import get_latest_resource_prices, get_latest_game_data, get_latest_game_info
        from datetime import datetime, timezone

        logger.info("Starting revenue calculation for all nations")

        db = IRSNationsDB(NATIONS_DB_PATH)
        nations = await db.get_all_nations()
        logger.info(f"Loaded {len(nations)} nations from database")

        # ── Shared context (DB-first, no API calls) ───────────────────────────
        market_prices = None
        try:
            price_data = await get_latest_resource_prices()
            if price_data:
                market_prices = {res: p['sell'] for res, p in price_data.items()}
        except Exception as e:
            logger.warning(f"Could not load prices from DB: {e}")

        color_map = {}
        try:
            colors = await get_latest_game_data("colors")
            if colors:
                color_map = {c['color'].lower(): float(c.get('turn_bonus', 0)) for c in colors}
        except Exception as e:
            logger.warning(f"Could not load colors from DB: {e}")

        game_date = None
        try:
            gi = await get_latest_game_info()
            if gi:
                raw = gi.get('game_date')
                if raw:
                    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    game_date = parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
        except Exception as e:
            logger.warning(f"Could not load game_info from DB: {e}")

        # ── Active war lookup (single bulk query, authoritative source) ──────────
        active_war_nation_ids: set = set()
        try:
            wars_db = _get_watch_db()
            active_war_nation_ids = await wars_db.get_active_war_nation_ids()
            logger.info(f"Active war nation IDs loaded: {len(active_war_nation_ids)} nations at war")
        except Exception as e:
            logger.warning(f"Could not load active war nation IDs from wars DB, falling back to counts: {e}")

        # ── Per-nation calculation ─────────────────────────────────────────────
        revenue_results = []
        alliance_total_turn = 0.0
        alliance_total_day  = 0.0
        failed_calculations = 0
        TAX_RATE = 0.10

        for i, nation in enumerate(nations):
            try:
                nation['cities'] = await db.get_cities_for_nation(int(nation['id']))
                nation_id = int(nation['id'])
                # Use wars DB (turns_left > 0) as the authoritative source.
                # Fall back to the nation's war counts only if the wars DB query failed.
                if active_war_nation_ids:
                    at_war = nation_id in active_war_nation_ids
                else:
                    at_war = (nation.get('offensive_wars_count', 0) > 0 or
                              nation.get('defensive_wars_count', 0) > 0)
                color = nation.get('color', 'beige').lower()
                color_bonus = color_map.get(color, 0.0)

                rev = await calculate_full_revenue_with_query(
                    nation_data=nation,
                    query_instance=None,
                    is_war=at_war,
                    color_bonus=color_bonus,
                    market_prices=market_prices,
                    game_date=game_date,
                )

                # gross_income = net_cash_num = cash after ALL upkeeps, before tax
                # monetary_net_num = gross_income + net resource monetary value
                gross_income   = rev.get('gross_income', 0)          # net cash (no tax)
                total_mon      = rev.get('monetary_net_num', 0)       # cash + resources
                alliance_tax   = max(0.0, gross_income * TAX_RATE)
                net_after_tax  = gross_income - alliance_tax

                # turn_revenue = net cash (what the nation keeps, before tax)
                # matches Discord embed "Net Income (Gross)"
                turn_revenue = gross_income
                day_revenue  = turn_revenue * 12
                alliance_total_turn += turn_revenue
                alliance_total_day  += day_revenue

                revenue_results.append({
                    'nation_id':            nation['id'],
                    'nation_name':          nation.get('nation_name', 'Unknown'),
                    'leader_name':          nation.get('leader_name', ''),
                    'flag':                 nation.get('flag', ''),
                    'color':                color,
                    'num_cities':           nation.get('num_cities', 0),
                    'score':                nation.get('score', 0),
                    # Revenue fields — mirrors Discord embed exactly
                    'turn_revenue':         turn_revenue,
                    'day_revenue':          day_revenue,
                    'gross_income':         gross_income,
                    'total_monetary_value': total_mon,
                    'net_after_tax':        net_after_tax,
                    # Upkeep breakdown
                    'military_upkeep':      rev.get('military_upkeep_turn', 0),
                    'improvement_upkeep':   rev.get('improvement_upkeep_turn', 0),
                    'power_upkeep':         rev.get('power_upkeep_turn', 0),
                    'rss_upkeep':           rev.get('rss_upkeep_turn', 0),
                    # Tax (informational only)
                    'alliance_tax':         alliance_tax,
                    'alliance_tax_rate':    TAX_RATE,
                    # War status (from wars DB turns_left > 0)
                    'at_war':               at_war,
                    # Other
                    'color_bonus':          color_bonus,
                    'population':           rev.get('nationpop', 0),
                    'resources':            rev.get('resources', {}),
                    'prices':               rev.get('prices', market_prices or {}),
                })

                if (i + 1) % 10 == 0:
                    logger.info(f"Processed {i + 1}/{len(nations)} nations")

            except Exception as e:
                failed_calculations += 1
                logger.warning(f"Revenue calc failed for {nation.get('nation_name', '?')}: {e}")
                continue

        revenue_results.sort(key=lambda x: x['turn_revenue'], reverse=True)
        logger.info(f"Revenue done: {len(revenue_results)} ok, {failed_calculations} failed. "
                    f"Alliance total: ${alliance_total_turn:,.2f}/t")

        return {
            "nations":             revenue_results,
            "alliance_total_turn": alliance_total_turn,
            "alliance_total_day":  alliance_total_day,
            "count":               len(revenue_results),
            "last_updated":        datetime.now(timezone.utc).isoformat(),
            "debug_info": {
                "total_nations_in_db":     len(nations),
                "successful_calculations": len(revenue_results),
                "failed_calculations":     failed_calculations,
                "has_market_prices":       market_prices is not None,
                "has_color_data":          len(color_map) > 0,
                "has_game_date":           game_date is not None,
            }
        }

    except Exception as e:
        logger.error(f"get_watch_revenue error: {e}", exc_info=True)
        return {"nations": [], "alliance_total_turn": 0, "alliance_total_day": 0, "count": 0, "error": str(e)}

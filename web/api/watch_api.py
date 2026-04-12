from fastapi import APIRouter
import asyncio
import logging
from typing import Dict, Any
import re
from datetime import date

from Systems.PnW.MA.night_watch_wars_db import NightWatchWarsDB
from Systems.PnW.Util.war_calc import get_resource_prices, calculate_unit_cost
from Systems.PnW.MA.war_net_bd import WarsNetBD

router = APIRouter()
logger = logging.getLogger("Reaper.WebServer.WatchAPI")

WATCH_DB_PATH = "c:\\Users\\codyr\\DiscordBots\\Reaper\\Databases\\NightWatchWars.db"
WATCH_ALLIANCE_ID = 14225
LOOT_RESOURCES = ("coal", "oil", "uranium", "iron", "bauxite", "lead", "gasoline", "munitions", "steel", "aluminum", "food")


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

        normalized_nations[str(nation_id)] = {
            **nation_data,
            "name": nation_data.get("name") or f"Unknown {nation_id}",
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


async def _attach_war_attacks(db: NightWatchWarsDB, wars: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    enriched_wars = []

    for war in wars:
        attacks = await db.get_war_attacks(war["id"])
        enriched_wars.append(
            {
                **war,
                "attacks": [_normalize_attack(attack, war) for attack in attacks],
            }
        )

    return enriched_wars

@router.get("/watch/wars")
async def get_watch_wars_data(start_date: str | None = None, end_date: str | None = None):
    try:
        db = NightWatchWarsDB(WATCH_DB_PATH)
        bounds = await db.get_alliance_war_date_bounds(WATCH_ALLIANCE_ID)

        if not bounds:
            return {
                **_build_watch_response({}, "No Night Watch wars were found in the local database."),
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
        
        # 1. Fetch wars and remove duplicates (prevents double-counting internal wars)
        att_wars = await db.get_wars_by_alliance_in_range(
            WATCH_ALLIANCE_ID,
            role='attacker',
            start_date=selected_start,
            end_date=selected_end,
        )
        def_wars = await db.get_wars_by_alliance_in_range(
            WATCH_ALLIANCE_ID,
            role='defender',
            start_date=selected_start,
            end_date=selected_end,
        )
        
        # Use a dictionary keyed by war ID to ensure uniqueness
        wars_dict = {war['id']: war for war in (att_wars + def_wars)}
        unique_wars = list(wars_dict.values())

        response_meta = {
            "available_start_date": available_start.isoformat(),
            "available_end_date": available_end.isoformat(),
            "selected_start_date": selected_start.isoformat(),
            "selected_end_date": selected_end.isoformat(),
            "war_count": len(unique_wars),
        }

        if not unique_wars:
            return {
                **_build_watch_response({}, "No Night Watch wars were found in the selected date range."),
                "meta": response_meta,
            }

        # Fetch prices
        try:
            resource_prices = await get_resource_prices()
        except Exception as price_error:
            logger.error("Error fetching resource prices for watch page: %s", price_error, exc_info=True)
            return {
                **_build_watch_response({}, "Night Watch data is unavailable right now because resource pricing could not be loaded."),
                "meta": response_meta,
            }

        unique_wars = await _attach_war_attacks(db, unique_wars)

        # 2. Get the breakdown from the "correct" logic in WarsNetBD
        war_net_bd_cog = WarsNetBD(bot=None)
        nation_breakdown = await war_net_bd_cog._get_nation_breakdown(unique_wars, str(WATCH_ALLIANCE_ID), False, resource_prices)

        return {
            **_build_watch_response(nation_breakdown, resource_prices=resource_prices),
            "meta": response_meta,
        }

    except Exception as e:
        logger.error(f"Error getting war data: {e}", exc_info=True)
        return {
            **_build_watch_response({}, "Failed to retrieve Night Watch war data."),
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
        start = now - timedelta(days=dow)
        end = start + timedelta(days=6)
    elif period == "last_week":
        start = now - timedelta(days=dow + 7)
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
        db = NightWatchWarsDB(WATCH_DB_PATH)
        att_wars = await db.get_wars_by_alliance_in_range(WATCH_ALLIANCE_ID, role='attacker', start_date=start, end_date=end)
        def_wars = await db.get_wars_by_alliance_in_range(WATCH_ALLIANCE_ID, role='defender', start_date=start, end_date=end)
        unique_wars = list({w['id']: w for w in (att_wars + def_wars)}.values())
        if not unique_wars:
            return []

        resource_prices = await get_resource_prices()
        unique_wars = await _attach_war_attacks(db, unique_wars)
        war_net_bd_cog = WarsNetBD(bot=None)
        nation_breakdown = await war_net_bd_cog._get_nation_breakdown(unique_wars, str(WATCH_ALLIANCE_ID), False, resource_prices)

        nations = {k: _enrich_nation_for_rank(dict(v)) for k, v in nation_breakdown.items()}
        name_lower = nation_name.lower()

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
            for i, (k, v) in enumerate(ranked):
                if (v.get("name") or k).lower() == name_lower:
                    rank = i + 1
                    if rank <= 3:
                        results.append({
                            "category_id": cat["id"],
                            "category_label": cat["label"],
                            "prefix": cat["prefix"],
                            "rank": rank,
                            "total": total,
                            "value": v.get(field),
                        })
                    break
        return results
    except Exception as e:
        logger.warning("nation-ranks error for %s/%s: %s", nation_name, period, e)
        return []


@router.get("/watch/nation-ranks/{nation_name}")
async def get_nation_ranks(nation_name: str):
    """Return all periods (current + historical) where the nation ranked top 3."""
    import sqlite3, calendar as _cal
    from datetime import datetime as _dt

    # ── Current periods ───────────────────────────────────────────────────────
    this_week_task  = _get_nation_ranks_for_period(nation_name, "this_week")
    this_month_task = _get_nation_ranks_for_period(nation_name, "this_month")

    # ── Historical periods from DB ────────────────────────────────────────────
    db = NightWatchWarsDB(WATCH_DB_PATH)
    try:
        async with db._lock:
            with sqlite3.connect(db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT DISTINCT
                        strftime('%Y-%W', substr(date, 1, 10)) AS week_key,
                        strftime('%Y-%m', substr(date, 1, 10)) AS month_key,
                        date(substr(date, 1, 10), 'weekday 0', '-6 days') AS week_start,
                        date(substr(date, 1, 10), 'weekday 0') AS week_end,
                        strftime('%Y-%m-01', substr(date, 1, 10)) AS month_start
                    FROM wars
                    WHERE att_alliance_id = ? OR def_alliance_id = ?
                    ORDER BY date DESC
                    """,
                    (WATCH_ALLIANCE_ID, WATCH_ALLIANCE_ID),
                )
                rows = cursor.fetchall()
    except Exception as e:
        logger.warning("nation-ranks: failed to fetch periods: %s", e)
        rows = []

    # Deduplicate and build period list, skipping current week/month
    now = _dt.utcnow().date()
    cur_month_key = now.strftime("%Y-%m")
    cur_week_start = (now - __import__('datetime').timedelta(days=now.weekday())).isoformat()

    seen_weeks: dict = {}
    seen_months: dict = {}
    for week_key, month_key, week_start, week_end, month_start in rows:
        if week_key and week_key not in seen_weeks and week_start != cur_week_start:
            def _fmt_week(iso: str) -> str:
                d = __import__('datetime').date.fromisoformat(iso)
                return f"{d.month}/{d.day:02d}/{str(d.year)[2:]}"
            seen_weeks[week_key] = {"start": week_start, "end": week_end,
                                    "label": f"{_fmt_week(week_start)} - {_fmt_week(week_end)}"}
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


@router.get("/watch/periods")
async def get_available_periods():
    """Return all distinct weeks and months that have war data in the DB."""
    db = NightWatchWarsDB(WATCH_DB_PATH)
    try:
        import sqlite3
        async with db._lock:
            with sqlite3.connect(db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT DISTINCT
                        strftime('%Y-%W', substr(date, 1, 10)) AS week_key,
                        strftime('%Y-%m', substr(date, 1, 10)) AS month_key,
                        date(substr(date, 1, 10), 'weekday 0', '-6 days') AS week_start,
                        date(substr(date, 1, 10), 'weekday 0') AS week_end,
                        strftime('%Y-%m-01', substr(date, 1, 10)) AS month_start
                    FROM wars
                    WHERE att_alliance_id = ? OR def_alliance_id = ?
                    ORDER BY date DESC
                    """,
                    (WATCH_ALLIANCE_ID, WATCH_ALLIANCE_ID),
                )
                rows = cursor.fetchall()

                cursor.execute(
                    """
                    SELECT DISTINCT date(substr(date, 1, 10))
                    FROM wars
                    WHERE att_alliance_id = ? OR def_alliance_id = ?
                    ORDER BY 1 ASC
                    """,
                    (WATCH_ALLIANCE_ID, WATCH_ALLIANCE_ID),
                )
                all_dates = [r[0] for r in cursor.fetchall() if r[0]]

        seen_weeks: dict = {}
        seen_months: dict = {}

        for week_key, month_key, week_start, week_end, month_start in rows:
            if week_key and week_key not in seen_weeks:
                seen_weeks[week_key] = {"start": week_start, "end": week_end}
            if month_key and month_key not in seen_months:
                seen_months[month_key] = {"start": month_start}

        # Build month end dates
        import calendar
        from datetime import date as _date
        months = []
        for mk, mv in seen_months.items():
            y, m = int(mk[:4]), int(mk[5:7])
            last_day = calendar.monthrange(y, m)[1]
            months.append({
                "key": mk,
                "start": mv["start"],
                "end": f"{y:04d}-{m:02d}-{last_day:02d}",
                "label": _date(y, m, 1).strftime("%B %Y"),
            })

        def _fmt_w2(iso: str) -> str:
            from datetime import date as _d3
            d = _d3.fromisoformat(iso)
            return f"{d.month}/{d.day:02d}/{str(d.year)[2:]}"

        weeks = [
            {
                "key": wk,
                "start": wv["start"],
                "end": wv["end"],
                "label": f"{_fmt_w2(wv['start'])} - {_fmt_w2(wv['end'])}",
            }
            for wk, wv in seen_weeks.items()
        ]

        return {"weeks": weeks, "months": months, "dates": all_dates}
    except Exception as e:
        logger.error(f"Error fetching available periods: {e}")
        return {"weeks": [], "months": [], "error": str(e)}

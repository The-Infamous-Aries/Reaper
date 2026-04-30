import logging
from typing import List, Optional
from Systems.PnW.Util.query import get_trade_resource_values
from Systems.Functions.database_manager import get_latest_resource_prices

WAR_SUMMARY_THRESHOLD = 5

# Unit costs
UNIT_COSTS = {
    "soldiers": {"cash": 5},
    "tanks": {"cash": 60, "steel": 0.5},
    "aircraft": {"cash": 4000, "aluminum": 10},
    "ships": {"cash": 50000, "steel": 30},
    "missiles": {"cash": 150000, "gasoline": 100, "munitions": 100, "aluminum": 150},
    "nukes": {"cash": 1750000, "uranium": 500, "gasoline": 500, "aluminum": 1000},
}

IMPROVEMENT_COSTS = {
    "coal_mine": {"cash": 1000},
    "oil_well": {"cash": 1500},
    "bauxite_mine": {"cash": 9500},
    "iron_mine": {"cash": 9500},
    "lead_mine": {"cash": 7500},
    "uranium_mine": {"cash": 25000},
    "farm": {"cash": 1000},
    "coal_power_plant": {"cash": 5000},
    "oil_power_plant": {"cash": 7000},
    "nuclear_power_plant": {"cash": 500000, "steel": 100},
    "wind_power_plant": {"cash": 30000, "aluminum": 30},
    "oil_refinery": {"cash": 45000},
    "steel_mill": {"cash": 45000},
    "aluminum_refinery": {"cash": 30000},
    "munitions_factory": {"cash": 35000},
    "police_station": {"cash": 75000, "steel": 20},
    "hospital": {"cash": 100000, "aluminum": 25},
    "recycling_center": {"cash": 125000},
    "subway": {"cash": 250000, "steel": 50, "aluminum": 25},
    "supermarket": {"cash": 5000},
    "bank": {"cash": 15000, "steel": 5, "aluminum": 10},
    "shopping_mall": {"cash": 45000, "steel": 20, "aluminum": 25},
    "stadium": {"cash": 100000, "steel": 40, "aluminum": 50},
    "barracks": {"cash": 3000},
    "factory": {"cash": 15000, "aluminum": 5},
    "hangar": {"cash": 100000, "steel": 10},
    "drydock": {"cash": 250000, "aluminum": 20},
}

async def get_resource_prices() -> dict:
    """Get current resource prices from the timed-query DB cache (updated every 15 min).
    Falls back to a live API call only if the DB has no data yet."""
    try:
        db_prices = await get_latest_resource_prices()
        if db_prices:
            prices = {"sell": {}, "buy": {}}
            for resource, data in db_prices.items():
                prices["sell"][resource.lower()] = data.get("sell", 0)
                prices["buy"][resource.lower()] = data.get("buy", 0)
            return prices
    except Exception as e:
        logging.warning(f"Could not read resource prices from DB, falling back to API: {e}")

    # Fallback — DB empty or unavailable
    try:
        trade_data = await get_trade_resource_values()
        prices = {"sell": {}, "buy": {}}
        if trade_data:
            for resource in trade_data:
                prices["sell"][resource['resource'].lower()] = resource.get('best_sell_offer', {}).get('price', 0)
                prices["buy"][resource['resource'].lower()] = resource.get('best_buy_offer', {}).get('price', 0)
        return prices
    except Exception as e:
        logging.error(f"Error fetching resource prices from API: {e}")
        return {"sell": {}, "buy": {}}

def calculate_unit_cost(unit_type: str, resource_prices: dict) -> float:
    """Calculate the total cost of a unit including resources."""
    if unit_type not in UNIT_COSTS:
        return 0
    
    cost = UNIT_COSTS[unit_type]["cash"]
    
    # Add resource costs
    for resource, amount in UNIT_COSTS[unit_type].items():
        if resource != "cash":
            cost += amount * resource_prices.get(resource, 0)
    
    return cost

def calculate_improvement_cost(improvement_name: str, resource_prices: dict) -> float:
    """Calculate the total cost of an improvement including resources."""
    if improvement_name not in IMPROVEMENT_COSTS:
        return 0
    
    cost = IMPROVEMENT_COSTS[improvement_name].get("cash", 0)
    sell_prices = resource_prices.get('sell', {})
    
    # Add resource costs
    for resource, amount in IMPROVEMENT_COSTS[improvement_name].items():
        if resource != "cash":
            price = sell_prices.get(resource, 0)
            cost += amount * price
    
    return cost

async def calculate_single_war_costs(war: dict, resource_prices: dict, team1_id_set: Optional[set] = None, team2_id_set: Optional[set] = None) -> dict:
    """Calculate the costs for a single war."""
    return await calculate_war_costs([war], resource_prices, team1_id_set=team1_id_set, team2_id_set=team2_id_set)


def _get_war_unit_total(war: dict, prefix: str, unit: str) -> float:
    """Return the war-level total for a unit, falling back to missiles/nukes used when losses are not stored separately."""
    lost_value = war.get(f"{prefix}{unit}_lost", 0)
    if lost_value:
        return lost_value

    if unit == "missiles":
        return war.get(f"{prefix}missiles_used", 0) or 0
    if unit == "nukes":
        return war.get(f"{prefix}nukes_used", 0) or 0

    return 0

async def calculate_war_costs(wars_data: List[dict], resource_prices: dict, team1_id_set: Optional[set] = None, team2_id_set: Optional[set] = None) -> dict:
    """Calculate total war costs for team1 and team2."""
    costs = {
        "team1": {
            "gross": 0, "net": 0, "units": {}, "consumption": {"munitions": 0, "gasoline": 0},
            "infra_lost_value": 0, "infra_lost_levels": 0, "improvements_lost": 0,
            "improvements_destroyed": {}, "loot_received": 0, "resource_loot": {},
            "loot_lost": 0, "resource_loot_lost": {}, "salvage": {"aluminum": 0, "steel": 0},
            "money_destroyed": 0
        },
        "team2": {
            "gross": 0, "net": 0, "units": {}, "consumption": {"munitions": 0, "gasoline": 0},
            "infra_lost_value": 0, "infra_lost_levels": 0, "improvements_lost": 0,
            "improvements_destroyed": {}, "loot_received": 0, "resource_loot": {},
            "loot_lost": 0, "resource_loot_lost": {}, "salvage": {"aluminum": 0, "steel": 0},
            "money_destroyed": 0
        }
    }

    str_team1_ids = {str(i) for i in team1_id_set} if team1_id_set else set()
    str_team2_ids = {str(i) for i in team2_id_set} if team2_id_set else set()

    for war in wars_data:
        per_war_detailed_units = {
            "team1": {"missiles": 0, "nukes": 0},
            "team2": {"missiles": 0, "nukes": 0},
        }
        per_war_detailed_infra = {
            "team1": {"levels": 0, "value": 0},
            "team2": {"levels": 0, "value": 0},
        }

        # Determine which side of the war corresponds to Team1 and Team2
        war_att_ids = {int(war[key]) for key in ('att_id', 'att_alliance_id') if war.get(key)}
        war_def_ids = {int(war[key]) for key in ('def_id', 'def_alliance_id') if war.get(key)}

        team1_is_attacker = team1_id_set and not team1_id_set.isdisjoint(war_att_ids)
        team1_is_defender = team1_id_set and not team1_id_set.isdisjoint(war_def_ids)
        team2_is_attacker = team2_id_set and not team2_id_set.isdisjoint(war_att_ids)
        team2_is_defender = team2_id_set and not team2_id_set.isdisjoint(war_def_ids)

        team1_prefix = None
        team2_prefix = None

        if team1_is_attacker and (team2_is_defender or not team2_id_set):
            team1_prefix = "att_"
            team2_prefix = "def_"
        elif team1_is_defender and (team2_is_attacker or not team2_id_set):
            team1_prefix = "def_"
            team2_prefix = "att_"
        else:
            continue

        if not team1_prefix or not team2_prefix:
            continue

        # Process missile strikes
        for strike in war.get('missile_strikes', []):
            strike_attacker_id = str(strike.get('attacker_id'))
            missiles_used = strike.get('missiles_used', 0)
            if not strike_attacker_id or not missiles_used > 0:
                continue

            bucket = None
            is_striker_on_team1 = False
            is_striker_on_team2 = False

            # Direct nation match
            if strike_attacker_id in str_team1_ids:
                is_striker_on_team1 = True
            elif str_team2_ids and strike_attacker_id in str_team2_ids:
                is_striker_on_team2 = True
            else:
                # Alliance-based inference
                war_att_alliance_id_str = str(war.get('att_alliance_id'))
                war_def_alliance_id_str = str(war.get('def_alliance_id'))
                war_att_id_str = str(war.get('att_id'))
                war_def_id_str = str(war.get('def_id'))

                # Check against team 1
                if war_att_alliance_id_str in str_team1_ids and strike_attacker_id != war_def_id_str:
                    is_striker_on_team1 = True
                elif war_def_alliance_id_str in str_team1_ids and strike_attacker_id != war_att_id_str:
                    is_striker_on_team1 = True

                # Check against team 2
                if str_team2_ids:
                    if war_att_alliance_id_str in str_team2_ids and strike_attacker_id != war_def_id_str:
                        is_striker_on_team2 = True
                    elif war_def_alliance_id_str in str_team2_ids and strike_attacker_id != war_att_id_str:
                        is_striker_on_team2 = True
            
            if is_striker_on_team1:
                bucket = 'team1'
            elif is_striker_on_team2:
                bucket = 'team2'
            elif not team2_id_set:
                bucket = 'team2'  # If team2 is not defined, anyone not on team1 is on team2
            else:
                continue # Striker is on neither team, skip

            if bucket:
                cost = calculate_unit_cost('missiles', resource_prices["buy"]) * missiles_used
                costs[bucket]["units"]['missiles'] = costs[bucket]["units"].get('missiles', {'lost': 0, 'cost': 0})
                costs[bucket]["units"]['missiles']['lost'] += missiles_used
                costs[bucket]["units"]['missiles']['cost'] += cost
                per_war_detailed_units[bucket]['missiles'] += missiles_used

        # Process nuclear strikes
        for strike in war.get('nuclear_strikes', []):
            strike_attacker_id = str(strike.get('attacker_id'))
            nukes_used = strike.get('nukes_used', 0)
            if not strike_attacker_id or not nukes_used > 0:
                continue

            bucket = None
            is_striker_on_team1 = False
            is_striker_on_team2 = False

            # Direct nation match
            if strike_attacker_id in str_team1_ids:
                is_striker_on_team1 = True
            elif str_team2_ids and strike_attacker_id in str_team2_ids:
                is_striker_on_team2 = True
            else:
                # Alliance-based inference
                war_att_alliance_id_str = str(war.get('att_alliance_id'))
                war_def_alliance_id_str = str(war.get('def_alliance_id'))
                war_att_id_str = str(war.get('att_id'))
                war_def_id_str = str(war.get('def_id'))

                # Check against team 1
                if war_att_alliance_id_str in str_team1_ids and strike_attacker_id != war_def_id_str:
                    is_striker_on_team1 = True
                elif war_def_alliance_id_str in str_team1_ids and strike_attacker_id != war_att_id_str:
                    is_striker_on_team1 = True

                # Check against team 2
                if str_team2_ids:
                    if war_att_alliance_id_str in str_team2_ids and strike_attacker_id != war_def_id_str:
                        is_striker_on_team2 = True
                    elif war_def_alliance_id_str in str_team2_ids and strike_attacker_id != war_att_id_str:
                        is_striker_on_team2 = True
            
            if is_striker_on_team1:
                bucket = 'team1'
            elif is_striker_on_team2:
                bucket = 'team2'
            elif not team2_id_set:
                bucket = 'team2'  # If team2 is not defined, anyone not on team1 is on team2
            else:
                continue

            if bucket:
                cost = calculate_unit_cost('nukes', resource_prices["buy"]) * nukes_used
                costs[bucket]["units"]['nukes'] = costs[bucket]["units"].get('nukes', {'lost': 0, 'cost': 0})
                costs[bucket]["units"]['nukes']['lost'] += nukes_used
                costs[bucket]["units"]['nukes']['cost'] += cost
                per_war_detailed_units[bucket]['nukes'] += nukes_used

        # Process ground battle loot and destruction
        for attack in war.get('attacks', []):
            attack_attacker_id_set = {str(id) for id in [attack.get('att_id'), attack.get('att_alliance_id')] if id}
            is_attack_from_team1 = not attack_attacker_id_set.isdisjoint(str_team1_ids)
            is_attack_from_team2 = not attack_attacker_id_set.isdisjoint(str_team2_ids)

            pov_bucket = None
            opp_bucket = None

            if is_attack_from_team1:
                pov_bucket = 'team1'
                opp_bucket = 'team2'
            elif is_attack_from_team2:
                pov_bucket = 'team2'
                opp_bucket = 'team1'
            elif not team2_id_set:
                # If only team1 is specified, any non-team1 attacker is the opponent (team2)
                pov_bucket = 'team2'
                opp_bucket = 'team1'
            else:
                # If both teams are specified, and the attacker is in neither, we skip this attack.
                continue
            
            # Process loot
            # Per user request, ensure money_stolen is included in total loot
            money_stolen = attack.get('money_stolen') or 0
            money_looted = attack.get('money_looted') or 0
            total_money_looted = money_stolen + money_looted
            # Exclude intra-team loot from being counted as lost
            if is_attack_from_team1 and any(str(def_id) in str_team1_ids for def_id in [attack.get('def_id'), attack.get('def_alliance_id')]):
                # This is an intra-team attack, so don't count it as a loss
                pass
            else:
                if total_money_looted > 0:
                    costs[opp_bucket]["loot_lost"] += total_money_looted
                    costs[pov_bucket]["loot_received"] += total_money_looted

                for res in ['coal', 'oil', 'uranium', 'iron', 'bauxite', 'lead', 'gasoline', 'munitions', 'steel', 'aluminum', 'food']:
                    looted = attack.get(f'{res}_looted') or 0
                    if looted > 0:
                        value = looted * resource_prices["sell"].get(res, 0)
                        costs[opp_bucket]["resource_loot_lost"][res] = costs[opp_bucket]["resource_loot_lost"].get(res, 0) + value
                        costs[pov_bucket]["resource_loot"][res] = costs[pov_bucket]["resource_loot"].get(res, 0) + value
            
            # Process salvage
            costs[pov_bucket]["salvage"]["aluminum"] += attack.get('military_salvage_aluminum', 0)
            costs[pov_bucket]["salvage"]["steel"] += attack.get('military_salvage_steel', 0)

            # Process money destroyed
            money_destroyed = attack.get('money_destroyed', 0)
            if money_destroyed > 0:
                costs[opp_bucket]['money_destroyed'] += money_destroyed

            # Process missile losses
            att_missiles_lost = attack.get('att_missiles_lost') or 0
            if att_missiles_lost > 0:
                cost = calculate_unit_cost('missiles', resource_prices["buy"]) * att_missiles_lost
                costs[pov_bucket]["units"]['missiles'] = costs[pov_bucket]["units"].get('missiles', {'lost': 0, 'cost': 0})
                costs[pov_bucket]["units"]['missiles']['lost'] += att_missiles_lost
                costs[pov_bucket]["units"]['missiles']['cost'] += cost
                per_war_detailed_units[pov_bucket]['missiles'] += att_missiles_lost

            def_missiles_lost = attack.get('def_missiles_lost') or 0
            if def_missiles_lost > 0:
                cost = calculate_unit_cost('missiles', resource_prices["buy"]) * def_missiles_lost
                costs[opp_bucket]["units"]['missiles'] = costs[opp_bucket]["units"].get('missiles', {'lost': 0, 'cost': 0})
                costs[opp_bucket]["units"]['missiles']['lost'] += def_missiles_lost
                costs[opp_bucket]["units"]['missiles']['cost'] += cost
                per_war_detailed_units[opp_bucket]['missiles'] += def_missiles_lost

            # Process nuke losses
            att_nukes_lost = attack.get('att_nukes_lost') or 0
            if att_nukes_lost > 0:
                cost = calculate_unit_cost('nukes', resource_prices["buy"]) * att_nukes_lost
                costs[pov_bucket]["units"]['nukes'] = costs[pov_bucket]["units"].get('nukes', {'lost': 0, 'cost': 0})
                costs[pov_bucket]["units"]['nukes']['lost'] += att_nukes_lost
                costs[pov_bucket]["units"]['nukes']['cost'] += cost
                per_war_detailed_units[pov_bucket]['nukes'] += att_nukes_lost
            
            def_nukes_lost = attack.get('def_nukes_lost') or 0
            if def_nukes_lost > 0:
                cost = calculate_unit_cost('nukes', resource_prices["buy"]) * def_nukes_lost
                costs[opp_bucket]["units"]['nukes'] = costs[opp_bucket]["units"].get('nukes', {'lost': 0, 'cost': 0})
                costs[opp_bucket]["units"]['nukes']['lost'] += def_nukes_lost
                costs[opp_bucket]["units"]['nukes']['cost'] += cost
                per_war_detailed_units[opp_bucket]['nukes'] += def_nukes_lost

            # Process improvement destruction
            if attack.get('improvements_destroyed'):
                for imp_raw in attack['improvements_destroyed']:
                    imp = imp_raw.lower().replace(' ', '_')
                    costs[opp_bucket]['improvements_destroyed'][imp] = costs[opp_bucket]['improvements_destroyed'].get(imp, 0) + 1

            # Attack-level infra fields represent the defender's infra loss from this attack.
            infra_destroyed = attack.get('infra_destroyed') or 0
            infra_destroyed_value = attack.get('infra_destroyed_value') or 0
            if infra_destroyed or infra_destroyed_value:
                costs[opp_bucket]["infra_lost_levels"] += infra_destroyed
                costs[opp_bucket]["infra_lost_value"] += infra_destroyed_value
                per_war_detailed_infra[opp_bucket]["levels"] += infra_destroyed
                per_war_detailed_infra[opp_bucket]["value"] += infra_destroyed_value

        
        # Process overall war-level stats for Team 1
        for unit in ["soldiers", "tanks", "aircraft", "ships", "missiles", "nukes"]:
            units_lost = _get_war_unit_total(war, team1_prefix, unit)
            if unit in {"missiles", "nukes"}:
                units_lost = max(units_lost - per_war_detailed_units["team1"][unit], 0)

            if units_lost > 0:
                cost = calculate_unit_cost(unit, resource_prices["buy"]) * units_lost
                costs['team1']["units"][unit] = costs['team1']["units"].get(unit, {'lost': 0, 'cost': 0})
                costs['team1']["units"][unit]['lost'] += units_lost
                costs['team1']["units"][unit]['cost'] += cost

        costs['team1']["consumption"]["munitions"] += war.get(f"{team1_prefix}mun_used", 0)
        costs['team1']["consumption"]["gasoline"] += war.get(f"{team1_prefix}gas_used", 0)

        team1_war_infra_levels = war.get(f"{team2_prefix}infra_destroyed", 0) or 0
        team1_war_infra_value = war.get(f"{team2_prefix}infra_destroyed_value", 0) or 0
        costs['team1']["infra_lost_levels"] += max(team1_war_infra_levels - per_war_detailed_infra["team1"]["levels"], 0)
        costs['team1']["infra_lost_value"] += max(team1_war_infra_value - per_war_detailed_infra["team1"]["value"], 0)


        # Process overall war-level stats for Team 2
        for unit in ["soldiers", "tanks", "aircraft", "ships", "missiles", "nukes"]:
            units_lost = _get_war_unit_total(war, team2_prefix, unit)
            if unit in {"missiles", "nukes"}:
                units_lost = max(units_lost - per_war_detailed_units["team2"][unit], 0)

            if units_lost > 0:
                cost = calculate_unit_cost(unit, resource_prices["buy"]) * units_lost
                costs['team2']["units"][unit] = costs['team2']["units"].get(unit, {'lost': 0, 'cost': 0})
                costs['team2']["units"][unit]['lost'] += units_lost
                costs['team2']["units"][unit]['cost'] += cost

        costs['team2']["consumption"]["munitions"] += war.get(f"{team2_prefix}mun_used", 0)
        costs['team2']["consumption"]["gasoline"] += war.get(f"{team2_prefix}gas_used", 0)

        team2_war_infra_levels = war.get(f"{team1_prefix}infra_destroyed", 0) or 0
        team2_war_infra_value = war.get(f"{team1_prefix}infra_destroyed_value", 0) or 0
        costs['team2']["infra_lost_levels"] += max(team2_war_infra_levels - per_war_detailed_infra["team2"]["levels"], 0)
        costs['team2']["infra_lost_value"] += max(team2_war_infra_value - per_war_detailed_infra["team2"]["value"], 0)


    # Calculate total improvement costs from aggregated counts
    for side in ["team1", "team2"]:
        total_improvements_cost = 0
        if costs[side]["improvements_destroyed"]:
            for imp, count in costs[side]["improvements_destroyed"].items():
                total_improvements_cost += calculate_improvement_cost(imp, resource_prices) * count
        costs[side]["improvements_lost"] = total_improvements_cost

    # Final aggregation
    for side in ["team1", "team2"]:
        gross_cost = (
            sum(d['cost'] for d in costs[side]["units"].values()) + 
            (costs[side]["consumption"]["munitions"] * resource_prices["buy"].get("munitions", 0)) + 
            (costs[side]["consumption"]["gasoline"] * resource_prices["buy"].get("gasoline", 0)) + 
            costs[side]["infra_lost_value"] + 
            costs[side]["improvements_lost"] + 
            costs[side]["loot_lost"] + 
            sum(costs[side]["resource_loot_lost"].values()) +
            costs[side]["money_destroyed"]
        )

        net_cost = (
            gross_cost - 
            costs[side]["loot_received"] - 
            sum(costs[side]["resource_loot"].values()) - 
            (costs[side]["salvage"]["aluminum"] * resource_prices["buy"].get("aluminum", 0)) - 
            (costs[side]["salvage"]["steel"] * resource_prices["buy"].get("steel", 0))
        )

        costs[side]["gross"] = gross_cost
        costs[side]["net"] = net_cost

    return costs

import random
import math
from .calc import has_project

MAP_COSTS = {
    'ground': 3,
    'airstrike': 4,
    'naval': 4,
    'missile': 8,
    'nuke': 12,
    'fortify': 3,
}



VICTORY_TYPES = {
    'utter_failure': 0,
    'pyrrhic_victory': 1,
    'moderate_success': 2,
    'immense_triumph': 3
}

WAR_TYPES_MODIFIERS = {
    'ordinary': {'loot': 0.5, 'infra': 0.5},
    'attrition': {'loot': 0.25, 'infra': 1.0},
    'raid': {'loot': 1.0, 'infra': 0.25}
}

class GroundBattleCalculator:
    """Calculates the outcome of a ground battle."""
    SOLDIER_VALUE_ARMED = 1.75
    SOLDIER_VALUE_UNARMED = 1.0
    TANK_VALUE = 40.0



    def _perform_battle_rolls(self, attacker_value, defender_value):
        rolls_won = 0
        for _ in range(3):
            attacker_roll = random.uniform(0.4, 1.0) * attacker_value
            defender_roll = random.uniform(0.4, 1.0) * defender_value
            if attacker_roll > defender_roll:
                rolls_won += 1
        return rolls_won

    def _determine_victory_type(self, rolls_won):
        if rolls_won == 3: return VICTORY_TYPES['immense_triumph']
        if rolls_won == 2: return VICTORY_TYPES['moderate_success']
        if rolls_won == 1: return VICTORY_TYPES['pyrrhic_victory']
        return VICTORY_TYPES['utter_failure']

    def calculate_loot(self, attacking_soldiers, attacking_tanks, victory_type, war_type, attacker_policy, defender_policy, defender_cash):
        """Calculates the amount of money looted from the defender."""
        base_loot = (attacking_soldiers * 1.1) + (attacking_tanks * 25.15)
        
        war_type_mod = WAR_TYPES_MODIFIERS.get(war_type, {}).get('loot', 0.5)
        policy_mod = 1.0
        if attacker_policy == 'pirate': policy_mod *= 1.4
        if defender_policy == 'moneybags': policy_mod *= 0.6
        if defender_policy == 'turtle': policy_mod *= 1.2

        max_loot = base_loot * (victory_type / 3) * war_type_mod * policy_mod * random.uniform(0.8, 1.1)

        return {'actual_loot': max_loot}

    def calculate_casualties(self, attacker_value, defender_value, attacking_soldiers, attacking_tanks, defending_soldiers, defending_tanks, victory_type, defender_fortified):
        """Calculates the number of casualties for both the attacker and defender."""
        if attacker_value == 0 and defender_value == 0: return {k: 0 for k in ['attacker_soldier_casualties', 'attacker_tank_casualties', 'defender_soldier_casualties', 'defender_tank_casualties']}

        # Base casualty rates
        attacker_cas_rate = 0.1
        defender_cas_rate = 0.1

        # Adjust casualty rates based on the ratio of army values
        if defender_value > 0:
            ratio = attacker_value / defender_value
            attacker_cas_rate /= ratio
            defender_cas_rate *= ratio

        # Apply victory type modifier
        victory_mod = 1 - (victory_type / 3) # Higher victory type means lower casualties for attacker
        attacker_cas_rate *= victory_mod
        defender_cas_rate *= (1 + (1 - victory_mod))

        # Apply fortification modifier
        if defender_fortified:
            attacker_cas_rate *= 1.25

        results = {}
        results['attacker_soldier_casualties'] = min(attacking_soldiers, attacking_soldiers * attacker_cas_rate * random.uniform(0.8, 1.2))
        results['attacker_tank_casualties'] = min(attacking_tanks, attacking_tanks * attacker_cas_rate * 0.2 * random.uniform(0.8, 1.2))
        results['defender_soldier_casualties'] = min(defending_soldiers, defending_soldiers * defender_cas_rate * random.uniform(0.8, 1.2))
        results['defender_tank_casualties'] = min(defending_tanks, defending_tanks * defender_cas_rate * 0.2 * random.uniform(0.8, 1.2))

        for k, v in results.items():
            results[k] = math.ceil(v)

        return results

    def calculate_infrastructure_damage(self, attacking_soldiers, attacking_tanks, defending_soldiers, defending_tanks, victory_type, city_infrastructure, war_type, attacker_policy, defender_policy):
        """Calculates the amount of infrastructure damage inflicted on the defender."""
        base_damage = max(0, (attacking_soldiers - defending_soldiers * 0.5) * 0.0006 + (attacking_tanks - defending_tanks * 0.5) * 0.01)
        
        war_mod = WAR_TYPES_MODIFIERS.get(war_type, {}).get('infra', 0.5)
        victory_mod = victory_type / 3.0
        random_mod = random.uniform(0.85, 1.05)

        policy_mod = 1.0
        if attacker_policy == 'piracy': policy_mod *= 1.1
        if defender_policy == 'fortress': policy_mod *= 0.8
        if attacker_policy == 'fortress': policy_mod *= 0.9
        
        infra_destroyed = base_damage * random_mod * victory_mod * war_mod * policy_mod
        return max(0, min(infra_destroyed, city_infrastructure * 0.2 + 25))

    def _calculate_army_value(self, soldiers, tanks, soldier_type='armed'):
        """Calculates the army value based on the number of soldiers and tanks."""
        soldier_mult = self.SOLDIER_VALUE_ARMED if soldier_type == 'armed' else self.SOLDIER_VALUE_UNARMED
        return (soldiers * soldier_mult) + (tanks * self.TANK_VALUE)

    def simulate_ground_battle(self, **params):
        attacker_val = self._calculate_army_value(params['attacking_soldiers'], params['attacking_tanks'], params['soldier_type'])
        
        defender_soldier_type = 'unarmed'
        if params['defending_munitions'] >= (params['defending_soldiers'] * 0.0002):
            defender_soldier_type = 'armed'

        defender_val = self._calculate_army_value(params['defending_soldiers'], params['defending_tanks'], defender_soldier_type)
        
        rolls_won = self._perform_battle_rolls(attacker_val, defender_val)
        victory_type = self._determine_victory_type(rolls_won)

        loot = self.calculate_loot(params['attacking_soldiers'], params['attacking_tanks'], victory_type, params['war_type'], params['attacker_policy'], params['defender_policy'], params['defender_cash'])
        cas = self.calculate_casualties(attacker_val, defender_val, params['attacking_soldiers'], params['attacking_tanks'], params['defending_soldiers'], params['defending_tanks'], victory_type, params['defender_fortified'])
        infra_dmg = self.calculate_infrastructure_damage(params['attacking_soldiers'], params['attacking_tanks'], params['defending_soldiers'], params['defending_tanks'], victory_type, params['city_infrastructure'], params['war_type'], params['attacker_policy'], params['defender_policy'])

        gains_gc = victory_type == VICTORY_TYPES['immense_triumph']
        breaks_gc = victory_type > VICTORY_TYPES['utter_failure'] and params['defender_has_gc']

        resistance_loss = (attacker_val / defender_val) * 2.5 if defender_val > 0 else 5.0

        return {
            'loot': loot,
            'infrastructure_damage': infra_dmg,
            'casualties': cas,
            'ground_control': {'gains_ground_control': gains_gc, 'breaks_ground_control': breaks_gc},
            'resistance_loss': resistance_loss,
            'victory_type': victory_type
        }

class AirstrikeCalculator:

    def _perform_battle_rolls(self, attacker_value, defender_value):
        rolls_won = 0
        for _ in range(3):
            attacker_roll = random.uniform(0.4, 1.0) * attacker_value
            defender_roll = random.uniform(0.4, 1.0) * defender_value
            if attacker_roll > defender_roll:
                rolls_won += 1
        return rolls_won

    def _determine_victory_type(self, rolls_won):
        if rolls_won == 3: return VICTORY_TYPES['immense_triumph']
        if rolls_won == 2: return VICTORY_TYPES['moderate_success']
        if rolls_won == 1: return VICTORY_TYPES['pyrrhic_victory']
        return VICTORY_TYPES['utter_failure']

    def calculate_casualties(self, attacking_aircraft, defending_aircraft, victory_type, defender_fortified):
        if attacking_aircraft == 0 and defending_aircraft == 0: return {'attacker_casualties': 0, 'defender_casualties': 0}

        ratio = (attacking_aircraft / defending_aircraft) if defending_aircraft > 0 else 2.0

        attacker_cas = (1 / ratio) * 0.02 * attacking_aircraft * random.uniform(0.8, 1.2)
        defender_cas = ratio * 0.02 * defending_aircraft * random.uniform(0.8, 1.2)

        if defender_fortified:
            attacker_cas *= 1.25

        return {
            'attacker_casualties': min(attacking_aircraft, math.ceil(attacker_cas)),
            'defender_casualties': min(defending_aircraft, math.ceil(defender_cas))
        }

    def calculate_infrastructure_damage(self, attacking_aircraft, defending_aircraft, victory_type, city_infrastructure, war_type, attacker_policy, defender_policy):
        base_damage = max(0, (attacking_aircraft - defending_aircraft * 0.5) * 0.35)
        
        war_mod = WAR_TYPES_MODIFIERS.get(war_type, {}).get('infra', 0.5)
        victory_mod = victory_type / 3.0
        random_mod = random.uniform(0.85, 1.05)

        policy_mod = 1.0
        if attacker_policy == 'piracy': policy_mod *= 1.1
        if defender_policy == 'fortress': policy_mod *= 0.8
        if attacker_policy == 'fortress': policy_mod *= 0.9

        infra_destroyed = base_damage * random_mod * victory_mod * war_mod * policy_mod
        return max(0, min(infra_destroyed, city_infrastructure * 0.5 + 100))

    def simulate_airstrike(self, **params):
        attacker_val = params['attacking_aircraft'] * 100
        defender_val = params['defending_aircraft'] * 100

        rolls_won = self._perform_battle_rolls(attacker_val, defender_val)
        victory_type = self._determine_victory_type(rolls_won)

        cas = self.calculate_casualties(params['attacking_aircraft'], params['defending_aircraft'], victory_type, params['defender_fortified'])
        infra_dmg = self.calculate_infrastructure_damage(params['attacking_aircraft'], params['defending_aircraft'], victory_type, params['city_infrastructure'], params['war_type'], params['attacker_policy'], params['defender_policy'])

        gains_as = victory_type == VICTORY_TYPES['immense_triumph']
        breaks_as = victory_type > VICTORY_TYPES['utter_failure'] and params['defender_has_as']

        ratio = (params['attacking_aircraft'] / params['defending_aircraft']) if params['defending_aircraft'] > 0 else 2.0
        resistance_loss = ratio * 3

        return {
            'aircraft_casualties': cas,
            'infrastructure_damage': infra_dmg,
            'air_superiority': {'gains_air_superiority': gains_as, 'breaks_air_superiority': breaks_as},
            'resistance_loss': resistance_loss,
            'victory_type': victory_type
        }

class NavalBattleCalculator:

    def _perform_naval_rolls(self, attacker_value, defender_value):
        rolls_won = 0
        for _ in range(3):
            attacker_roll = random.uniform(0.4, 1.0) * attacker_value
            defender_roll = random.uniform(0.4, 1.0) * defender_value
            if attacker_roll > defender_roll:
                rolls_won += 1
        return rolls_won

    def _determine_victory_type(self, rolls_won):
        if rolls_won == 3: return VICTORY_TYPES['immense_triumph']
        if rolls_won == 2: return VICTORY_TYPES['moderate_success']
        if rolls_won == 1: return VICTORY_TYPES['pyrrhic_victory']
        return VICTORY_TYPES['utter_failure']

    def calculate_casualties(self, attacking_ships, defending_ships, victory_type, defender_fortified):
        if attacking_ships == 0 and defending_ships == 0: return {'attacker_casualties': 0, 'defender_casualties': 0}

        ratio = (attacking_ships / defending_ships) if defending_ships > 0 else 2.0

        attacker_cas = (1 / ratio) * 0.01 * attacking_ships * random.uniform(0.8, 1.2)
        defender_cas = ratio * 0.01 * defending_ships * random.uniform(0.8, 1.2)

        if defender_fortified:
            attacker_cas *= 1.25

        return {
            'attacker_casualties': min(attacking_ships, math.ceil(attacker_cas)),
            'defender_casualties': min(defending_ships, math.ceil(defender_cas))
        }

    def calculate_infrastructure_damage(self, attacking_ships, defending_ships, victory_type, city_infrastructure, war_type, attacker_policy, defender_policy):
        base_damage = max(0, (attacking_ships - defending_ships * 0.5) * 2.625)
        
        war_mod = WAR_TYPES_MODIFIERS.get(war_type, {}).get('infra', 0.5)
        victory_mod = victory_type / 3.0
        random_mod = random.uniform(0.85, 1.05)

        policy_mod = 1.0
        if attacker_policy == 'piracy': policy_mod *= 1.1
        if defender_policy == 'fortress': policy_mod *= 0.8
        if attacker_policy == 'fortress': policy_mod *= 0.9

        infra_destroyed = base_damage * random_mod * victory_mod * war_mod * policy_mod
        return max(0, min(infra_destroyed, city_infrastructure * 0.5 + 25))

    def simulate_naval_battle(self, **params):
        attacker_val = params['attacking_ships'] * 200
        defender_val = params['defending_ships'] * 200

        rolls_won = self._perform_naval_rolls(attacker_val, defender_val)
        victory_type = self._determine_victory_type(rolls_won)

        cas = self.calculate_casualties(params['attacking_ships'], params['defending_ships'], victory_type, params['defender_fortified'])
        infra_dmg = self.calculate_infrastructure_damage(params['attacking_ships'], params['defending_ships'], victory_type, params['city_infrastructure'], params['war_type'], params['attacker_policy'], params['defender_policy'])

        establishes_blockade = victory_type == VICTORY_TYPES['immense_triumph']
        breaks_blockade = victory_type > VICTORY_TYPES['utter_failure'] and params['defender_has_blockade']

        ratio = (params['attacking_ships'] / params['defending_ships']) if params['defending_ships'] > 0 else 2.0
        resistance_loss = ratio * 3.5

        return {
            'ship_casualties': cas,
            'infrastructure_damage': infra_dmg,
            'blockade_effects': {'establishes_blockade': establishes_blockade, 'breaks_blockade': breaks_blockade},
            'resistance_loss': resistance_loss,
            'victory_type': victory_type
        }


from Systems.PnW.MA.weapon_eff import get_weapon_damage

class MissileStrikeCalculator:
    def simulate_missile_strike(self, defender_nation, defender_fortified, has_iron_dome):
        if has_iron_dome and random.random() < 0.30:
            return {'blocked': True, 'infrastructure_damage': 0, 'casualties': {}, 'resistance_loss': 0, 'victory_type': 0}

        cities = defender_nation.get('cities', {})
        if not cities: return {'error': 'Defender has no cities.'}

        highest_infra_city = max(cities.values(), key=lambda c: c.get('infrastructure', 0), default={})
        infra_to_damage = highest_infra_city.get('infrastructure', 0)
        total_land = sum(c.get('land', 1) for c in cities.values()) or 1
        pop_density = defender_nation.get('population', 0) / total_land

        infra_destroyed = get_weapon_damage(infra_to_damage, 'missile', pop_density)
        if defender_fortified: infra_destroyed *= 0.75

        return {
            'infrastructure_damage': infra_destroyed,
            'casualties': { 'defender_soldier_casualties': (defender_nation.get('population', 0) / (len(cities) or 1)) * 0.05 },
            'resistance_loss': 18,
            'victory_type': 3,
            'blocked': False
        }

class FortifyCalculator:
    def simulate_fortification(self, **params):
        return {
            'infrastructure_damage': 0,
            'casualties': {},
            'resistance_loss': 0,
            'victory_type': 3, # Always a success
        }

class NukeStrikeCalculator:
    def simulate_nuke_strike(self, defender_nation, defender_fortified, has_vds):
        if has_vds and random.random() < 0.25:
            return {'blocked': True, 'infrastructure_damage': 0, 'casualties': {}, 'resistance_loss': 0, 'victory_type': 0}

        cities = defender_nation.get('cities', {})
        if not cities: return {'error': 'Defender has no cities.'}

        highest_infra_city = max(cities.values(), key=lambda c: c.get('infrastructure', 0), default={})
        infra_to_damage = highest_infra_city.get('infrastructure', 0)
        total_land = sum(c.get('land', 1) for c in cities.values()) or 1
        pop_density = defender_nation.get('population', 0) / total_land

        infra_destroyed = get_weapon_damage(infra_to_damage, 'nuke', pop_density)
        if defender_fortified: infra_destroyed *= 0.75

        return {
            'infrastructure_damage': infra_destroyed,
            'casualties': { 'defender_soldier_casualties': (defender_nation.get('population', 0) / (len(cities) or 1)) * 0.20 },
            'resistance_loss': 25,
            'victory_type': 3,
            'blocked': False
        }

class WarManager:
    def __init__(self):
        self.calculators = {
            'ground': GroundBattleCalculator(),
            'airstrike': AirstrikeCalculator(),
            'naval': NavalBattleCalculator(),
            'missile': MissileStrikeCalculator(),
            'nuke': NukeStrikeCalculator(),
            'fortify': FortifyCalculator()
        }

    def _get_nation_params(self, nation, additional_params):
        params = {
            'attacking_soldiers': nation.get('soldiers', 0),
            'attacking_tanks': nation.get('tanks', 0),
            'attacking_aircraft': nation.get('aircraft', 0),
            'attacking_ships': nation.get('ships', 0),
            'defending_soldiers': nation.get('soldiers', 0),
            'defending_tanks': nation.get('tanks', 0),
            'defending_aircraft': nation.get('aircraft', 0),
            'defending_ships': nation.get('ships', 0),
            'defending_munitions': nation.get('munitions', 0),
            'defender_population': nation.get('population', 0),
            'defender_cash': nation.get('money', 0),
            'attacker_policy': nation.get('war_policy', 'none'),
            'defender_policy': nation.get('war_policy', 'none'),
            'soldier_type': additional_params.get('soldier_type', 'armed'),
            'attacker_has_gc': additional_params.get('attacker_has_gc', False),
            'defender_has_gc': additional_params.get('defender_has_gc', False),
            'defender_has_as': additional_params.get('defender_has_as', False),
            'defender_has_blockade': additional_params.get('defender_has_blockade', False),
            'defender_fortified': additional_params.get('defender_fortified', False),
        }
        cities = nation.get('cities', {})
        params['city_infrastructure'] = max(c.get('infrastructure', 0) for c in cities.values()) if cities else 0
        return params

    def simulate_battle(self, battle_type, attacker_nation, defender_nation, war_type, additional_params=None):
        if battle_type not in self.calculators:
            print(f"Invalid battle type: {battle_type}")
            return {"error": "Invalid battle type"}
        
        if additional_params is None: additional_params = {}

        # Prepare parameters — use `or 0` to guard against explicit None values in nation dicts
        params = {
            'war_type': war_type,
            'attacker_policy': attacker_nation.get('war_policy') or 'none',
            'defender_policy': defender_nation.get('war_policy') or 'none',
            'soldier_type': additional_params.get('soldier_type', 'armed'),
            'attacker_has_gc': additional_params.get('attacker_has_gc', False),
            'defender_has_gc': additional_params.get('defender_has_gc', False),
            'defender_has_as': additional_params.get('defender_has_as', False),
            'defender_has_blockade': additional_params.get('defender_has_blockade', False),
            'defender_fortified': additional_params.get('defender_fortified', False),

            'attacking_soldiers': attacker_nation.get('soldiers') or 0,
            'attacking_tanks': attacker_nation.get('tanks') or 0,
            'attacking_aircraft': attacker_nation.get('aircraft') or 0,
            'attacking_ships': attacker_nation.get('ships') or 0,

            'defending_soldiers': defender_nation.get('soldiers') or 0,
            'defending_tanks': defender_nation.get('tanks') or 0,
            'defending_aircraft': defender_nation.get('aircraft') or 0,
            'defending_ships': defender_nation.get('ships') or 0,
            'defending_munitions': defender_nation.get('munitions') or 0,

            'defender_population': defender_nation.get('population') or 0,
            'defender_cash': defender_nation.get('money') or 0,
        }

        cities = defender_nation.get('cities') or {}
        if isinstance(cities, dict):
            params['city_infrastructure'] = max((c.get('infrastructure') or 0 for c in cities.values()), default=0)
        elif isinstance(cities, list):
            params['city_infrastructure'] = max((c.get('infrastructure') or 0 for c in cities), default=0)
        else:
            params['city_infrastructure'] = 0

        # Special params for missile/nuke
        if battle_type in ['missile', 'nuke']:
            params['defender_nation'] = defender_nation
            params['has_iron_dome'] = has_project(defender_nation, 'Iron Dome')
            params['has_vds'] = has_project(defender_nation, 'Vital Defense System')

        # Simulate
        calculator = self.calculators[battle_type]

        # Selectively pass parameters based on battle type
        if battle_type == 'ground':
            return calculator.simulate_ground_battle(**params)
        elif battle_type == 'airstrike':
            return calculator.simulate_airstrike(**params)
        elif battle_type == 'naval':
            return calculator.simulate_naval_battle(**params)
        elif battle_type == 'missile':
            return calculator.simulate_missile_strike(defender_nation=params['defender_nation'], defender_fortified=params['defender_fortified'], has_iron_dome=params['has_iron_dome'])
        elif battle_type == 'nuke':
            return calculator.simulate_nuke_strike(defender_nation=params['defender_nation'], defender_fortified=params['defender_fortified'], has_vds=params['has_vds'])
        elif battle_type == 'fortify':
            return calculator.simulate_fortification(**params)
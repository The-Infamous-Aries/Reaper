import logging
import random
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import copy
from datetime import datetime, timezone, timedelta

from .attacks_calc import (
    WarManager,
    MAP_COSTS,
    get_weapon_damage
)
from .calc import AllianceCalculator, has_project
from .war_calc import UNIT_COSTS

def calc_total_infra_cost(infra_level: float) -> float:
    """Calculates the total cost for a given infrastructure level based on the PnW formula."""
    if infra_level <= 0:
        return 0
    # Formula: Cost = 25 * (I^2 + I) / 2
    return 25 * (infra_level ** 2 + infra_level) / 2

def calc_infra_value(infra_before: float, infra_after: float) -> float:
    """Calculates the value of infrastructure destroyed between two levels."""
    cost_before = calc_total_infra_cost(infra_before)
    cost_after = calc_total_infra_cost(infra_after)
    return max(0, cost_before - cost_after)

class WarBrainAllianceCalculator(AllianceCalculator):
    """An extension of AllianceCalculator that includes the has_project method."""
    def has_project(self, nation: Dict[str, Any], project_name: str) -> bool:
        return has_project(nation, project_name)


class AttackType(Enum):
    GROUND_BATTLE = "ground"
    AIRSTRIKE = "airstrike"
    NAVAL_BATTLE = "naval"
    MISSILE_STRIKE = "missile"
    NUCLEAR_STRIKE = "nuke"
    FORTIFY = "fortify"
    NO_ATTACK = "none"


class AttackPriority(Enum):
    HIGH = 3
    MEDIUM = 2
    LOW = 1
    NONE = 0


@dataclass
class AttackRecommendation:
    attack_type: AttackType
    priority: AttackPriority
    reasoning: str
    expected_damage: float
    expected_cost: float
    success_probability: float
    map_cost: int
    economic_efficiency: float
    use_munitions_for_soldiers: bool = False

@dataclass
class WarTurnResult:
    turn: int
    attacker_side: str
    attack_type: str
    attacker_casualties: Dict[str, int] = field(default_factory=dict)
    defender_casualties: Dict[str, int] = field(default_factory=dict)
    infra_damage: float = 0.0
    infra_damage_cost: float = 0.0
    resistance_change: float = 0.0
    loot: Dict[str, float] = field(default_factory=dict)
    consumption: Dict[str, float] = field(default_factory=dict)
    purchases: Dict[str, Any] = field(default_factory=dict)
    attacker_resistance: float = 100.0
    defender_resistance: float = 100.0
    attacker_maps: int = 6
    defender_maps: int = 6
    attacker_ground_control: bool = False
    defender_ground_control: bool = False
    attacker_air_superiority: bool = False
    defender_air_superiority: bool = False
    attacker_blockade: bool = False
    defender_blockade: bool = False
    attacker_fortified: bool = False
    defender_fortified: bool = False

@dataclass
class WarSimulation:
    attacker_nation: Dict[str, Any]
    defender_nation: Dict[str, Any]
    war_type: str
    winner: str
    total_turns: int
    initial_attacker_resistance: int
    initial_defender_resistance: int
    final_attacker_resistance: float
    final_defender_resistance: float
    turn_results: List[WarTurnResult] = field(default_factory=list)
    total_infra_destroyed: float = 0.0
    total_infra_damage_cost: float = 0.0
    total_attacker_casualties: Dict[str, int] = field(default_factory=dict)
    total_defender_casualties: Dict[str, int] = field(default_factory=dict)
    total_consumption: Dict[str, float] = field(default_factory=dict)
    total_loot: Dict[str, float] = field(default_factory=dict)


class WarBrain:
    """The main class for simulating a full war between two nations."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.war_manager = WarManager()
        self.calc = WarBrainAllianceCalculator()


    def _convert_nation_for_calc(self, nation: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure nation data is in dict format (city names as keys) for consistency."""
        converted_nation = nation.copy()
        cities_data = nation.get('cities', [])
        
        self.logger.debug(f"Pre-conversion cities type: {type(cities_data)}")
        
        if isinstance(cities_data, list):
            self.logger.debug(f"Converting cities list to dict format.")
            converted_nation['cities'] = {city.get('name', f'city_{i}'): city for i, city in enumerate(cities_data)}
        else:
            self.logger.debug("Cities data is already a dict, no conversion needed.")
        
        return converted_nation

    _NUMERIC_NATION_FIELDS = [
        'soldiers', 'tanks', 'aircraft', 'ships', 'missiles', 'nukes',
        'munitions', 'gasoline', 'money', 'food', 'coal', 'oil', 'uranium',
        'lead', 'iron', 'bauxite', 'steel', 'aluminum', 'population',
        'num_cities', 'score', 'infrastructure', 'land',
    ]

    def _normalize_nation(self, nation: Dict[str, Any]) -> None:
        """Ensure all numeric nation fields are actual numbers (not None) in-place."""
        for field in self._NUMERIC_NATION_FIELDS:
            if nation.get(field) is None:
                nation[field] = 0

    def simulate_full_war(self, attacker_orig: Dict[str, Any], defender_orig: Dict[str, Any], 
                         market_prices: Dict[str, float], war_type: str, 
                         spy_data: Optional[Dict[str, Any]] = None, max_turns: int = 60) -> WarSimulation:
        """Simulates a full war between two nations, turn by turn."""
        
        try:
            attacker = copy.deepcopy(attacker_orig)
            defender = copy.deepcopy(defender_orig)

            # Sanitize: replace any None numeric fields with 0
            self._normalize_nation(attacker)
            self._normalize_nation(defender)

            if spy_data:
                for resource, amount in spy_data.items():
                    if resource in defender:
                        defender[resource] = amount if amount is not None else 0

            state = {
                'attacker': {
                    'nation': attacker, 'resistance': 100.0, 'maps': 6,
                    'status': {'gc': False, 'as': False, 'blockade': False, 'fortified': False},
                    'attack_counts': {'naval': 0, 'ground': 0, 'airstrike': 0, 'missile': 0, 'nuke': 0}
                },
                'defender': {
                    'nation': defender, 'resistance': 100.0, 'maps': 6,
                    'status': {'gc': False, 'as': False, 'blockade': False, 'fortified': False},
                    'attack_counts': {'naval': 0, 'ground': 0, 'airstrike': 0, 'missile': 0, 'nuke': 0}
                }
            }

            self._apply_policy_effects(state)

            simulation = WarSimulation(
                attacker_nation=attacker_orig, defender_nation=defender_orig, war_type=war_type,
                winner='ongoing', total_turns=0,
                initial_attacker_resistance=100.0, initial_defender_resistance=100.0,
                final_attacker_resistance=100.0, final_defender_resistance=100.0
            )

            for turn in range(1, max_turns + 1):
                if state['defender']['resistance'] <= 0:
                    simulation.winner = 'attacker'
                    break
                if state['attacker']['resistance'] <= 0:
                    simulation.winner = 'defender'
                    break

                self._process_turn(turn, state, market_prices, war_type, simulation)

            simulation.total_turns = turn  # Use actual turn number, not count of results
            simulation.final_attacker_resistance = state['attacker']['resistance']
            simulation.final_defender_resistance = state['defender']['resistance']

            if simulation.winner == 'ongoing':
                simulation.winner = 'attacker' if simulation.final_defender_resistance < simulation.final_attacker_resistance else 'defender'

            self._summarize_simulation(simulation)
            return simulation

        except Exception as e:
            self.logger.error(f"Error during full war simulation: {e}", exc_info=True)
            # Return a valid but errored simulation object
            return WarSimulation(
                attacker_nation=attacker_orig,
                defender_nation=defender_orig,
                war_type=war_type,
                initial_attacker_resistance=100.0,
                initial_defender_resistance=100.0,
                winner='error',
                total_turns=0,
                final_attacker_resistance=100.0,
                final_defender_resistance=100.0
            )

    def _apply_policy_effects(self, state: Dict[str, Any]):
        defender_policy = state['defender']['nation'].get('war_policy', '').lower()
        if defender_policy == 'blitzkrieg':
            state['attacker']['maps'] = 7
        elif defender_policy == 'fortress':
            state['attacker']['maps'] = state['defender']['maps'] = 5

    def _process_turn(self, turn: int, state: Dict[str, Any], market_prices: Dict[str, float], 
                     war_type: str, simulation: WarSimulation):
        
        # Store MAPs before turn processing for accurate display
        attacker_maps_before = state['attacker']['maps']
        defender_maps_before = state['defender']['maps']
        
        state['attacker']['maps'] = min(12, state['attacker']['maps'] + 1)
        state['defender']['maps'] = min(12, state['defender']['maps'] + 1)
        
        # Store MAPs after replenishment but before attack
        attacker_maps_after_replenish = state['attacker']['maps']
        defender_maps_after_replenish = state['defender']['maps']

        actor_side, target_side = self._determine_actor(state)
        actor, target = state[actor_side]['nation'], state[target_side]['nation']

        purchases = self._purchasing_phase(actor, turn, state[actor_side]['status']['blockade'], 
                                           state[actor_side]['resistance'] > state[target_side]['resistance'],
                                           self.analyze_war_capabilities(target))

        attack_rec = self.determine_optimal_attack(
            actor, target, market_prices, state[target_side]['resistance'], 
            state[actor_side]['maps'], state[actor_side]['status'], 
            'attacker' if actor_side == 'attacker' else 'defender', 
            state[actor_side]['resistance'] > state[target_side]['resistance'], 
            state[actor_side]['status']['blockade'], war_type,
            state[actor_side]['attack_counts']
        )

        # Debug: Check MAP availability
        current_maps = state[actor_side]['maps']
        required_maps = attack_rec.map_cost
        self.logger.debug(f"Turn {turn}: {actor_side} has {current_maps} MAPs, needs {required_maps} for {attack_rec.attack_type.value}")
        
        if not self._can_execute_attack(attack_rec, state[actor_side]['maps']):
            self.logger.debug(f"Turn {turn}: {actor_side} cannot execute {attack_rec.attack_type.value} - insufficient MAPs")
            simulation.turn_results.append(self._create_pass_turn_result(turn, actor_side, state, attacker_maps_before, defender_maps_before))
            return

        # Targeting logic
        target_cities = list(state[target_side]['nation'].get('cities', {}).values())
        if not target_cities:
            simulation.turn_results.append(self._create_pass_turn_result(turn, actor_side, state, attacker_maps_before, defender_maps_before))
            return

        target_city = None
        if attack_rec.attack_type in [AttackType.MISSILE_STRIKE, AttackType.NUCLEAR_STRIKE]:
            # Strategic targeting for missiles and nukes
            target_city = max(target_cities, key=lambda c: c.get('infrastructure', 0) * c.get('population', 0))
        else:
            # Random targeting for conventional attacks
            target_city = random.choice(target_cities)

        # Optimize unit usage based on defender's military
        defender_analysis = self.analyze_war_capabilities(target)
        optimized_units = self._optimize_attack_units(attack_rec, actor, defender_analysis)

        self._execute_attack(turn, actor_side, target_side, attack_rec, state, war_type, simulation, purchases, target_city, optimized_units, attacker_maps_after_replenish, defender_maps_after_replenish)

    def _optimize_attack_units(self, attack_rec: AttackRecommendation, actor: Dict[str, Any], defender_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Optimize unit usage based on defender's military capabilities."""
        defender_units = defender_analysis['units']
        optimized = {}
        
        # For naval attacks: if defender has no ships, only send 1 ship for immense triumph
        if attack_rec.attack_type == AttackType.NAVAL_BATTLE and defender_units['ships'] == 0:
            optimized['ships'] = min(actor.get('ships', 0), 1)
        
        # For ground attacks: if defender has no soldiers and no tanks, don't use tanks or ammo for soldiers
        if attack_rec.attack_type == AttackType.GROUND_BATTLE:
            if defender_units['soldiers'] == 0 and defender_units['tanks'] == 0:
                # Don't use tanks
                optimized['tanks'] = 0
                # Don't use munitions for soldiers (save resources)
                optimized['use_munitions_for_soldiers'] = False
        
        return optimized

    def _determine_actor(self, state: Dict[str, Any]) -> Tuple[str, str]:
        attacker_military = (state['attacker']['nation'].get('soldiers', 0) + 
                           state['attacker']['nation'].get('tanks', 0) + 
                           state['attacker']['nation'].get('aircraft', 0) + 
                           state['attacker']['nation'].get('ships', 0))
        defender_military = (state['defender']['nation'].get('soldiers', 0) + 
                           state['defender']['nation'].get('tanks', 0) + 
                           state['defender']['nation'].get('aircraft', 0) + 
                           state['defender']['nation'].get('ships', 0))
        
        # If one side has no military, the other side always gets the turn (if they have MAPs)
        if attacker_military == 0 and defender_military > 0:
            return 'defender', 'attacker'
        if defender_military == 0 and attacker_military > 0:
            return 'attacker', 'defender'
        
        # Otherwise, use MAP comparison
        if state['attacker']['maps'] >= state['defender']['maps']:
            return 'attacker', 'defender'
        return 'defender', 'attacker'

    def _can_execute_attack(self, attack_rec: AttackRecommendation, maps: int) -> bool:
        return attack_rec.attack_type != AttackType.NO_ATTACK and maps >= attack_rec.map_cost

    def _execute_attack(self, turn: int, actor_side: str, target_side: str, attack_rec: AttackRecommendation,
                       state: Dict[str, Any], war_type: str, simulation: WarSimulation, purchases: Dict[str, Any], target_city: Dict[str, Any], optimized_units: Dict[str, Any] = None, attacker_maps_after_replenish: int = 6, defender_maps_after_replenish: int = 6):
        
        actor, target = state[actor_side]['nation'], state[target_side]['nation']
        
        # Store original values for rollback in case of error
        original_missiles = actor.get('missiles') or 0
        original_nukes = actor.get('nukes') or 0
        original_maps = state[actor_side]['maps']
        original_munitions = actor.get('munitions') or 0
        original_gasoline = actor.get('gasoline') or 0
        original_ships = actor.get('ships') or 0
        original_tanks = actor.get('tanks') or 0
        original_use_munitions = attack_rec.use_munitions_for_soldiers
        
        # Apply unit optimizations if provided
        if optimized_units:
            if 'ships' in optimized_units:
                actor['ships'] = optimized_units['ships']
            if 'tanks' in optimized_units:
                actor['tanks'] = optimized_units['tanks']
            if 'use_munitions_for_soldiers' in optimized_units:
                attack_rec.use_munitions_for_soldiers = optimized_units['use_munitions_for_soldiers']
        
        if attack_rec.attack_type == AttackType.MISSILE_STRIKE:
            actor['missiles'] = (actor.get('missiles') or 0) - 1
        elif attack_rec.attack_type == AttackType.NUCLEAR_STRIKE:
            actor['nukes'] = (actor.get('nukes') or 0) - 1

        state[actor_side]['maps'] -= attack_rec.map_cost

        # Calculate and deduct consumption costs
        # Consumption should be based on the units actually sent into battle (after optimization)
        consumption = self._calculate_attack_cost(attack_rec.attack_type.value, actor, attack_rec.use_munitions_for_soldiers)
        
        # Debug: Log consumption calculation
        self.logger.debug(f"Turn {turn}: Attack type: {attack_rec.attack_type.value}, Actor units: soldiers={actor.get('soldiers', 0)}, tanks={actor.get('tanks', 0)}, ships={actor.get('ships', 0)}, aircraft={actor.get('aircraft', 0)}, use_munitions={attack_rec.use_munitions_for_soldiers}, Consumption: {consumption}")
        
        for resource, amount in consumption.items():
            actor[resource] = (actor.get(resource) or 0) - amount

        battle_results = self.war_manager.simulate_battle(
            attack_rec.attack_type.value, actor, target, war_type,
            additional_params={
                'defender_air_superiority': state[target_side]['status']['as'],
                'attacker_has_gc': state[actor_side]['status']['gc'],
                'defender_has_gc': state[target_side]['status']['gc'],
                'defender_has_as': state[target_side]['status']['as'],
                'defender_has_blockade': state[target_side]['status']['blockade'],
                'defender_fortified': state[target_side]['status']['fortified'],
                'soldier_type': 'armed' if attack_rec.use_munitions_for_soldiers else 'unarmed'
            }
        )
        
        # Restore original unit values after battle (optimizations only apply to this attack)
        if optimized_units:
            actor['ships'] = original_ships
            actor['tanks'] = original_tanks
        
        # Increment attack count
        state[actor_side]['attack_counts'][attack_rec.attack_type.value] = state[actor_side]['attack_counts'].get(attack_rec.attack_type.value, 0) + 1

        if 'error' in battle_results:
            self.logger.error(f"Turn {turn}: Error during battle sim by {actor_side}: {battle_results['error']}")
            # Rollback resource deductions
            if attack_rec.attack_type == AttackType.MISSILE_STRIKE:
                actor['missiles'] = original_missiles
            elif attack_rec.attack_type == AttackType.NUCLEAR_STRIKE:
                actor['nukes'] = original_nukes
            state[actor_side]['maps'] = original_maps
            actor['munitions'] = original_munitions
            actor['gasoline'] = original_gasoline
            actor['ships'] = original_ships
            actor['tanks'] = original_tanks
            attack_rec.use_munitions_for_soldiers = original_use_munitions
            return

        resistance_damage = self._calculate_resistance_damage(attack_rec.attack_type.value, battle_results.get('victory_type', 0))
        state[target_side]['resistance'] -= resistance_damage
        battle_results['resistance_loss'] = resistance_damage
        self._update_war_statuses(battle_results, state, actor_side, target_side, attack_rec.attack_type.value)

        turn_result = self._process_turn_results(turn, actor_side, attack_rec.attack_type.value,
                                                 battle_results, actor, target, war_type, purchases, state, simulation, target_city)
        turn_result.consumption = consumption
        
        # Set MAPs to show remaining values AFTER this turn's attack
        # This should show what MAPs each nation has left at the end of the turn
        turn_result.attacker_maps = state['attacker']['maps']
        turn_result.defender_maps = state['defender']['maps']
        
        self._append_turn_to_simulation(simulation, turn_result, state)

    def _purchasing_phase(self, nation: Dict[str, Any], turn: int, is_blockaded: bool, 
                         is_winning: bool, enemy_analysis: Dict[str, Any]) -> Dict[str, Any]:
        
        if not self._is_nation_active(nation):
            return {}

        # Convert nation data to list format for calc functions
        nation_for_calc = self._convert_nation_for_calc(nation)
        purchase_limits = self.calc.calculate_military_purchase_limits(nation_for_calc)
        is_pre_dc = (turn % 12 == 11)
        purchase_multiplier = 1.0 if (is_pre_dc and (is_winning or is_blockaded)) else 0.25

        priorities = self._determine_purchase_priorities(nation, enemy_analysis, is_blockaded)
        total_weight = sum(priorities.values())
        
        if total_weight == 0:
            return {}

        budget_allocation = {unit: priorities[unit] / total_weight for unit in priorities}
        units_to_buy = {}
        purchases = {'units': {}, 'cost': {'money': 0}}
        
        for unit, allocation in budget_allocation.items():
            daily_limit = purchase_limits.get(f'{unit}_daily', 0)
            units_to_buy[unit] = int(daily_limit * purchase_multiplier * allocation)

        for unit, quantity in units_to_buy.items():
            if quantity <= 0:
                continue

            cost = UNIT_COSTS.get(unit, {})
            if self._can_afford_units(nation, cost, quantity):
                for resource, amount in cost.items():
                    nation[resource.lower()] = (nation.get(resource.lower()) or 0) - amount * quantity
                nation[unit] = (nation.get(unit) or 0) + quantity
                purchases['units'][unit] = purchases['units'].get(unit, 0) + quantity
                for res, amt in cost.items():
                    purchases['cost'][res.lower()] = purchases['cost'].get(res.lower(), 0) + amt * quantity
        return purchases

    def _is_nation_active(self, nation: Dict[str, Any]) -> bool:
        try:
            last_active_str = nation.get('last_active', '')
            last_active_dt = datetime.fromisoformat(last_active_str.replace('Z', '+00:00'))
            return (datetime.now(timezone.utc) - last_active_dt) <= timedelta(days=7)
        except (ValueError, TypeError):
            return False

    def _can_afford_units(self, nation: Dict[str, Any], cost: Dict[str, float], quantity: int) -> bool:
        for resource, amount in cost.items():
            if (nation.get(resource.lower()) or 0) < amount * quantity:
                return False
        return True

    def _determine_purchase_priorities(self, nation: Dict[str, Any], enemy_analysis: Dict[str, Any], 
                                      is_blockaded: bool) -> Dict[str, float]:
        priorities = {'soldiers': 1.0, 'tanks': 1.0, 'aircraft': 1.0, 'ships': 1.0}

        if is_blockaded:
            priorities['ships'] *= 2.0

        our_analysis = self.analyze_war_capabilities(nation)

        # Counter enemy strengths
        enemy_strengths = enemy_analysis['strengths']
        if enemy_strengths['ground'] > our_analysis['strengths']['ground']:
            priorities['tanks'] *= 1.5
            priorities['soldiers'] *= 1.2
        if enemy_strengths['air'] > our_analysis['strengths']['air']:
            priorities['aircraft'] *= 1.5
        if enemy_strengths['naval'] > our_analysis['strengths']['naval']:
            priorities['ships'] *= 1.5

        # Reinforce our strengths
        if our_analysis['strengths']['ground'] > enemy_strengths['ground']:
            priorities['tanks'] *= 1.2
        if our_analysis['strengths']['air'] > enemy_strengths['air']:
            priorities['aircraft'] *= 1.2
        if our_analysis['strengths']['naval'] > enemy_strengths['naval']:
            priorities['ships'] *= 1.2

        # If we are losing, focus on defense
        if our_analysis['raw_power'] < enemy_analysis['raw_power'] * 0.8:
            priorities['soldiers'] *= 1.5
            priorities['tanks'] *= 1.2

        return priorities

    def _update_war_statuses(self, battle_results: Dict[str, Any], state: Dict[str, Any], 
                           actor_side: str, target_side: str, attack_type: str):
        
        if 'ground_control' in battle_results:
            gc_result = battle_results['ground_control']
            if gc_result.get('gains_ground_control'):
                state[actor_side]['status']['gc'] = True
                state[target_side]['status']['gc'] = False
            elif gc_result.get('breaks_ground_control'):
                state[target_side]['status']['gc'] = False
        
        if 'air_superiority' in battle_results:
            as_result = battle_results['air_superiority']
            if as_result.get('gains_air_superiority'):
                state[actor_side]['status']['as'] = True
                state[target_side]['status']['as'] = False
            elif as_result.get('breaks_air_superiority'):
                state[target_side]['status']['as'] = False

        if 'blockade_effects' in battle_results:
            blockade_result = battle_results['blockade_effects']
            if blockade_result.get('establishes_blockade'):
                state[actor_side]['status']['blockade'] = True
                state[target_side]['status']['blockade'] = False
            elif blockade_result.get('breaks_blockade'):
                state[target_side]['status']['blockade'] = False

        if attack_type == 'fortify':
            state[actor_side]['status']['fortified'] = True
        elif attack_type == 'ground':
            # Fortify is only reset by ground battles
            state[actor_side]['status']['fortified'] = False

    def _create_pass_turn_result(self, turn: int, actor_side: str, state: Dict[str, Any], 
                                attacker_maps_before: int, defender_maps_before: int) -> WarTurnResult:
        return WarTurnResult(
            turn=turn, 
            attacker_side=actor_side, 
            attack_type='pass',
            attacker_resistance=state['attacker']['resistance'],
            defender_resistance=state['defender']['resistance'],
            attacker_maps=state['attacker']['maps'],  # Show MAPs after replenishment
            defender_maps=state['defender']['maps'],  # Show MAPs after replenishment
            attacker_ground_control=state['attacker']['status']['gc'],
            defender_ground_control=state['defender']['status']['gc'],
            attacker_air_superiority=state['attacker']['status']['as'],
            defender_air_superiority=state['defender']['status']['as'],
            attacker_blockade=state['attacker']['status']['blockade'],
            defender_blockade=state['defender']['status']['blockade'],
            attacker_fortified=state['attacker']['status']['fortified'],
            defender_fortified=state['defender']['status']['fortified']
        )

    def _process_turn_results(self, turn: int, actor_side: str, attack_type: str, 
                               battle_results: Dict[str, Any], actor: Dict[str, Any], 
                               target: Dict[str, Any], war_type: str, purchases: Dict[str, Any], 
                               state: Dict[str, Any], simulation: WarSimulation, target_city: Dict[str, Any]) -> WarTurnResult:
        
        cas = battle_results.get('casualties', {})
        loot = battle_results.get('loot', {})

        infra_damage = battle_results.get('infrastructure_damage', 0.0)
        infra_damage_cost = 0.0
        if infra_damage > 0 and target_city:
            infra_before = target_city.get('infrastructure', 0)
            infra_after = infra_before - infra_damage
            infra_damage_cost = calc_infra_value(infra_before, max(0, infra_after))
        else:
            infra_damage = 0.0

        turn_result = WarTurnResult(
            turn=turn, 
            attacker_side=actor_side, 
            attack_type=attack_type,
            infra_damage=infra_damage,
            infra_damage_cost=infra_damage_cost,
            resistance_change=battle_results.get('resistance_loss', 0.0),
            purchases=purchases
        )

        turn_result.attacker_casualties = {
            'soldiers': cas.get('attacker_soldier_casualties', 0),
            'tanks': cas.get('attacker_tank_casualties', 0),
            'aircraft': battle_results.get('aircraft_casualties', {}).get('attacker_casualties', 0),
            'ships': battle_results.get('ship_casualties', {}).get('attacker_casualties', 0)
        }
        
        turn_result.defender_casualties = {
            'soldiers': cas.get('defender_soldier_casualties', 0),
            'tanks': cas.get('defender_tank_casualties', 0),
            'aircraft': battle_results.get('aircraft_casualties', {}).get('defender_casualties', 0),
            'ships': battle_results.get('ship_casualties', {}).get('defender_casualties', 0)
        }

        if actor_side == 'defender':
            # Swap casualties if defender was the actor
            turn_result.attacker_casualties, turn_result.defender_casualties = turn_result.defender_casualties, turn_result.attacker_casualties

        self._update_nation_states(actor, target, turn_result, actor_side, target_city)

        turn_result.loot = {
            'money': loot.get('actual_loot', 0),
            **self._calculate_resource_loot(actor, target, war_type)
        }

        return turn_result

    def _update_nation_states(self, attacker: Dict[str, Any], defender: Dict[str, Any], 
                            turn_result: WarTurnResult, actor_side: str, target_city: Dict[str, Any]):
        
        target_city['infrastructure'] = target_city.get('infrastructure', 0) - turn_result.infra_damage
        
        # Loot is gained by the actor of the turn (whoever attacked)
        actor_nation = attacker if actor_side == 'attacker' else defender
        target_nation = defender if actor_side == 'attacker' else attacker
        
        target_nation['money'] = (target_nation.get('money') or 0) - turn_result.loot.get('money', 0)
        actor_nation['money'] = (actor_nation.get('money') or 0) + turn_result.loot.get('money', 0)
        for res, amount in turn_result.loot.items():
            if res != 'money':
                target_nation[res] = (target_nation.get(res) or 0) - amount
                actor_nation[res] = (actor_nation.get(res) or 0) + amount

        for unit, num in turn_result.attacker_casualties.items():
            attacker[unit] = (attacker.get(unit) or 0) - num
        for unit, num in turn_result.defender_casualties.items():
            defender[unit] = (defender.get(unit) or 0) - num

    def _append_turn_to_simulation(self, simulation: WarSimulation, turn_result: WarTurnResult, state: Dict[str, Any]):
        # Update resistance values
        turn_result.attacker_resistance = state['attacker']['resistance']
        turn_result.defender_resistance = state['defender']['resistance']
        
        # Update war statuses
        turn_result.attacker_ground_control = state['attacker']['status']['gc']
        turn_result.defender_ground_control = state['defender']['status']['gc']
        turn_result.attacker_air_superiority = state['attacker']['status']['as']
        turn_result.defender_air_superiority = state['defender']['status']['as']
        turn_result.attacker_blockade = state['attacker']['status']['blockade']
        turn_result.defender_blockade = state['defender']['status']['blockade']
        turn_result.attacker_fortified = state['attacker']['status']['fortified']
        turn_result.defender_fortified = state['defender']['status']['fortified']
        
        # Note: MAPs are already set correctly in _process_turn to show values after the turn
        simulation.turn_results.append(turn_result)

    def _summarize_simulation(self, simulation: WarSimulation):
        for turn in simulation.turn_results:
            simulation.total_infra_destroyed += turn.infra_damage
            
            for unit, num in turn.attacker_casualties.items():
                simulation.total_attacker_casualties[unit] = simulation.total_attacker_casualties.get(unit, 0) + num
            for unit, num in turn.defender_casualties.items():
                simulation.total_defender_casualties[unit] = simulation.total_defender_casualties.get(unit, 0) + num
            for res, num in turn.consumption.items():
                simulation.total_consumption[res] = simulation.total_consumption.get(res, 0) + num
            for res, num in turn.loot.items():
                simulation.total_loot[res] = simulation.total_loot.get(res, 0) + num

    def _calculate_resistance_damage(self, attack_type: str, victory_type: int) -> float:
        """Calculates the resistance damage based on the attack type and victory type."""
        base_damage = {
            'ground': 10.0,
            'airstrike': 12.0,
            'naval': 14.0,
            'missile': 18.0,
            'nuke': 25.0,
            'fortify': 0.0
        }.get(attack_type, 0.0)

        victory_multiplier = {
            3: 1.0,  # immense_triumph
            2: 0.6,  # moderate_success
            1: 0.3,  # pyrrhic_victory
            0: 0.0   # utter_failure
        }.get(victory_type, 0.0)

        return base_damage * victory_multiplier


    def _calculate_resource_loot(self, attacker: dict, defender: dict, war_type: str) -> Dict[str, float]:
        lootable_resources = ['food', 'coal', 'oil', 'uranium', 'lead', 'iron', 'bauxite', 'gasoline', 'munitions', 'steel', 'aluminum']
        base_percentage = {'raid': 0.15, 'ordinary': 0.10, 'attrition': 0.05}.get(war_type, 0.10)

        attacker_policy = attacker.get('war_policy', '').lower()
        defender_policy = defender.get('war_policy', '').lower()

        multiplier = 1.0
        if attacker_policy == 'piracy':
            multiplier *= 1.4
        if defender_policy == 'moneybags':
            multiplier *= 0.6
        if defender_policy == 'turtle':
            multiplier *= 1.2
        if has_project(attacker, 'Advanced Piracy Economics'):
            multiplier *= 1.1

        looted = {}
        for res in lootable_resources:
            available = defender.get(res) or 0
            if available > 0:
                looted[res] = available * base_percentage * multiplier
        return looted

    def _calculate_attack_cost(self, attack_type: str, attacker: Dict[str, Any], use_munitions_for_soldiers: bool = False) -> Dict[str, float]:
        costs = {'munitions': 0.0, 'gasoline': 0.0}
        
        if attack_type == 'ground':
            if use_munitions_for_soldiers:
                costs['munitions'] = (attacker.get('soldiers') or 0) / 5000
            costs['munitions'] += (attacker.get('tanks') or 0) / 100
            costs['gasoline'] = (attacker.get('tanks') or 0) / 100
        elif attack_type == 'airstrike':
            costs['munitions'] = (attacker.get('aircraft') or 0) * 0.25
            costs['gasoline'] = (attacker.get('aircraft') or 0) * 0.25
        elif attack_type == 'naval':
            costs['munitions'] = (attacker.get('ships') or 0) * 1.75
            costs['gasoline'] = (attacker.get('ships') or 0) * 1.0
        
        # Debug: Log cost calculation
        self.logger.debug(f"Cost calculation: attack_type={attack_type}, soldiers={attacker.get('soldiers', 0)}, tanks={attacker.get('tanks', 0)}, ships={attacker.get('ships', 0)}, aircraft={attacker.get('aircraft', 0)}, use_munitions={use_munitions_for_soldiers}, costs={costs}")
        
        return costs

    def analyze_war_capabilities(self, nation: Dict[str, Any]) -> Dict[str, Any]:
        try:
            units = {
                'soldiers': nation.get('soldiers') or 0,
                'tanks': nation.get('tanks') or 0,
                'aircraft': nation.get('aircraft') or 0,
                'ships': nation.get('ships') or 0,
                'missiles': nation.get('missiles') or 0,
                'nukes': nation.get('nukes') or 0
            }
            
            can_missile = has_project(nation, 'Missile Launch Pad')
            can_nuke = has_project(nation, 'Nuclear Research Facility')
            
            ground_strength = self._calculate_ground_strength(units['soldiers'], units['tanks'])
            air_strength = self._calculate_air_strength(units['aircraft'])
            naval_strength = self._calculate_naval_strength(units['ships'])
            
            avg_infrastructure = self._calculate_average_infrastructure(nation)
            population_density = self._calculate_population_density(nation)
            
            return {
                'nation': nation,
                'units': units,
                'capabilities': {
                    'can_missile': can_missile,
                    'can_nuke': can_nuke,
                    'has_ground': units['soldiers'] > 0 or units['tanks'] > 0,
                    'has_air': units['aircraft'] > 0,
                    'has_naval': units['ships'] > 0
                },
                'strengths': {
                    'ground': ground_strength,
                    'air': air_strength,
                    'naval': naval_strength
                },
                'economic': {
                    'avg_infrastructure': avg_infrastructure,
                    'population_density': population_density,
                    'total_infra': nation.get('infrastructure', 0)
                },
                'raw_power': ground_strength + air_strength + naval_strength
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing war capabilities: {e}")
            return self._get_default_capabilities()

    def determine_optimal_attack(self, attacker: Dict[str, Any], defender: Dict[str, Any], 
                                market_prices: Dict[str, float], current_resistance: int = 100, 
                                attacker_maps: int = 6, attacker_status: Dict[str, bool] = {},
                                initial_role: str = 'attacker', is_winning: bool = True, 
                                is_blockaded: bool = False, war_type: str = 'ordinary',
                                attack_counts: Dict[str, int] = None) -> AttackRecommendation:
        """Determines the optimal attack for the current turn based on a cost-benefit analysis."""
        
        try:
            attacker_analysis = self.analyze_war_capabilities(attacker)
            defender_analysis = self.analyze_war_capabilities(defender)
            
            best_attack = None
            best_score = -1
            
            for attack_type in [AttackType.GROUND_BATTLE, AttackType.AIRSTRIKE, AttackType.NAVAL_BATTLE, 
                              AttackType.MISSILE_STRIKE, AttackType.NUCLEAR_STRIKE, AttackType.FORTIFY]:
                
                if not self._can_perform_attack(attack_type, attacker_analysis, attacker_maps):
                    continue
                
                recommendation = self._evaluate_attack(attack_type, attacker_analysis, defender_analysis, 
                                                     market_prices, current_resistance, attacker_status, 
                                                     initial_role, is_winning, is_blockaded, war_type, attack_counts)
                
                score = recommendation.priority.value * 10 + recommendation.economic_efficiency
                
                if score > best_score:
                    best_score = score
                    best_attack = recommendation
            
            return best_attack if best_attack else self._get_fallback_recommendation()
            
        except Exception as e:
            self.logger.error(f"Error determining optimal attack: {e}")
            return self._get_fallback_recommendation()

    def _evaluate_attack(self, attack_type: AttackType, attacker_analysis: Dict[str, Any], 
                        defender_analysis: Dict[str, Any], market_prices: Dict[str, float], 
                        current_resistance: int, attacker_status: Dict[str, bool], initial_role: str, 
                        is_winning: bool, is_blockaded: bool, war_type: str, attack_counts: Dict[str, int] = None) -> AttackRecommendation:
        
        effectiveness = self._calculate_attack_effectiveness(attack_type, attacker_analysis, defender_analysis)
        
        # Apply project-based defense reductions early so they affect all calculations
        attacker_nation = attacker_analysis['nation']
        defender_nation = defender_analysis['nation']
        if attack_type == AttackType.MISSILE_STRIKE and self._has_project(defender_nation, 'Iron Dome'):
            effectiveness *= 0.7  # 30% reduction
        if attack_type == AttackType.NUCLEAR_STRIKE and self._has_project(defender_nation, 'Vital Defense System'):
            effectiveness *= 0.75  # 25% reduction
        
        # Apply war type modifiers early
        if initial_role == 'attacker':
            if war_type == 'raid':
                if attack_type == AttackType.GROUND_BATTLE:
                    effectiveness *= 1.5
                else:
                    effectiveness *= 0.8
            elif war_type == 'attrition':
                if attack_type in [AttackType.AIRSTRIKE, AttackType.MISSILE_STRIKE, AttackType.NUCLEAR_STRIKE]:
                    effectiveness *= 1.5
                else:
                    effectiveness *= 0.8
        
        expected_damage = self._calculate_expected_damage(attack_type, defender_analysis, effectiveness)
        
        use_munitions_for_soldiers = False
        if attack_type == AttackType.GROUND_BATTLE:
            armed_value = attacker_analysis['units']['soldiers'] * 1.75 + attacker_analysis['units']['tanks'] * 40
            unarmed_value = attacker_analysis['units']['soldiers'] * 1.0 + attacker_analysis['units']['tanks'] * 40
            defender_value = (defender_analysis['units']['soldiers'] * 1.75 + defender_analysis['units']['tanks'] * 40 + 
                            defender_analysis['nation'].get('population', 0) / 400)
            
            if unarmed_value < defender_value * 0.8:
                use_munitions_for_soldiers = True
        
        cost_dict = self._calculate_attack_cost(attack_type.value, attacker_analysis['nation'], use_munitions_for_soldiers)
        expected_cost = sum(cost_dict.get(res, 0) * market_prices.get(res, 0) for res in cost_dict)
        success_probability = self._calculate_success_probability(attack_type, attacker_analysis, defender_analysis)
        
        economic_efficiency = (expected_damage * 1000) / max(expected_cost, 1.0) if expected_damage > 0 else 0.0
        
        priority = self._determine_attack_priority(
            attack_type, attacker_analysis, defender_analysis, effectiveness, 
            expected_damage, expected_cost, success_probability, current_resistance, 
            attacker_status, initial_role, is_winning, is_blockaded, war_type, economic_efficiency, attack_counts
        )
        reasoning = self._generate_attack_reasoning(attack_type, effectiveness, expected_damage, success_probability, priority)
        
        return AttackRecommendation(
            attack_type=attack_type,
            priority=priority,
            reasoning=reasoning,
            expected_damage=expected_damage,
            expected_cost=expected_cost,
            success_probability=success_probability,
            map_cost=MAP_COSTS.get(attack_type.value, 0),
            economic_efficiency=economic_efficiency,
            use_munitions_for_soldiers=use_munitions_for_soldiers
        )

    def _can_perform_attack(self, attack_type: AttackType, attacker_analysis: Dict[str, Any], attacker_maps: int) -> bool:
        capabilities = attacker_analysis['capabilities']
        units = attacker_analysis['units']
        map_cost = MAP_COSTS.get(attack_type.value, 999)

        if attacker_maps < map_cost:
            return False
        
        if attack_type == AttackType.GROUND_BATTLE:
            return capabilities['has_ground'] and units['soldiers'] >= 100
        elif attack_type == AttackType.AIRSTRIKE:
            return capabilities['has_air'] and units['aircraft'] >= 1
        elif attack_type == AttackType.NAVAL_BATTLE:
            return capabilities['has_naval'] and units['ships'] >= 1
        elif attack_type == AttackType.MISSILE_STRIKE:
            return capabilities['can_missile'] and units['missiles'] >= 1
        elif attack_type == AttackType.NUCLEAR_STRIKE:
            return capabilities['can_nuke'] and units['nukes'] >= 1
        elif attack_type == AttackType.FORTIFY:
            # Cannot fortify without military units
            total_military = units['soldiers'] + units['tanks'] + units['aircraft'] + units['ships']
            return total_military > 0
        return False

    def _calculate_attack_effectiveness(self, attack_type: AttackType, attacker_analysis: Dict[str, Any], 
                                       defender_analysis: Dict[str, Any]) -> float:
        attacker_strengths = attacker_analysis['strengths']
        defender_strengths = defender_analysis['strengths']
        
        if attack_type == AttackType.GROUND_BATTLE:
            # If defender has no ground units, effectiveness is based on having ground units
            if defender_strengths['ground'] == 0:
                return 1.0 if attacker_strengths['ground'] > 0 else 0.0
            return self._calculate_relative_strength(attacker_strengths['ground'], defender_strengths['ground'])
        elif attack_type == AttackType.AIRSTRIKE:
            return self._calculate_relative_strength(attacker_strengths['air'], defender_strengths['air'])
        elif attack_type == AttackType.NAVAL_BATTLE:
            # If defender has no naval, effectiveness is based on having naval units
            if defender_strengths['naval'] == 0:
                return 1.0 if attacker_strengths['naval'] > 0 else 0.0
            return self._calculate_relative_strength(attacker_strengths['naval'], defender_strengths['naval'])
        elif attack_type == AttackType.MISSILE_STRIKE:
            avg_infra = defender_analysis['economic']['avg_infrastructure']
            return min(avg_infra / 2000, 1.0)
        elif attack_type == AttackType.NUCLEAR_STRIKE:
            avg_infra = defender_analysis['economic']['avg_infrastructure']
            pop_density = defender_analysis['economic']['population_density']
            infra_factor = min(avg_infra / 3000, 1.0)
            density_factor = min(pop_density / 100, 1.0)
            return (infra_factor + density_factor) / 2
        return 0.0

    def _calculate_expected_damage(self, attack_type: AttackType, defender_analysis: Dict[str, Any], 
                                  effectiveness: float) -> float:
        defender_nation = defender_analysis.get('nation', {})
        avg_infra = defender_analysis['economic']['avg_infrastructure']

        if attack_type == AttackType.GROUND_BATTLE:
            return effectiveness * 50 * (avg_infra / 1000)
        elif attack_type == AttackType.AIRSTRIKE:
            return effectiveness * 75 * (avg_infra / 1000)
        elif attack_type == AttackType.NAVAL_BATTLE:
            return effectiveness * 60 * (avg_infra / 1000)
        elif attack_type in [AttackType.MISSILE_STRIKE, AttackType.NUCLEAR_STRIKE]:
            cities = defender_nation.get('cities', {})
            if not cities:
                return 0
            highest_infra_city = max(cities.values(), key=lambda c: c.get('infrastructure', 0))
            infra_to_damage = highest_infra_city.get('infrastructure', 0)
            pop_density = defender_nation.get('population', 0) / sum(c.get('land', 1) for c in cities.values()) if cities else 0
            return get_weapon_damage(infra_to_damage, attack_type.value, pop_density)
        return 0.0

    def _calculate_success_probability(self, attack_type: AttackType, attacker_analysis: Dict[str, Any], 
                                    defender_analysis: Dict[str, Any]) -> float:
        attacker_strengths = attacker_analysis['strengths']
        defender_strengths = defender_analysis['strengths']
        
        if attack_type == AttackType.GROUND_BATTLE:
            ratio = attacker_strengths['ground'] / max(defender_strengths['ground'], 1)
        elif attack_type == AttackType.AIRSTRIKE:
            ratio = attacker_strengths['air'] / max(defender_strengths['air'], 1)
        elif attack_type == AttackType.NAVAL_BATTLE:
            ratio = attacker_strengths['naval'] / max(defender_strengths['naval'], 1)
        else:
            return 0.85 if attack_type == AttackType.MISSILE_STRIKE else 0.95
        
        return min(ratio / (ratio + 1), 0.95)

    def _determine_attack_priority(self, attack_type: AttackType, attacker_analysis: Dict[str, Any], defender_analysis: Dict[str, Any], effectiveness: float, 
                                 expected_damage: float, expected_cost: float, 
                                 success_probability: float, current_resistance: int, 
                                 attacker_status: Dict[str, bool], initial_role: str, 
                                 is_winning: bool, is_blockaded: bool, war_type: str, economic_efficiency: float, attack_counts: Dict[str, int] = None) -> AttackPriority:
        
        attacker_nation = attacker_analysis['nation']
        defender_nation = defender_analysis['nation']
        defender_units = defender_analysis['units']
        
        # WAR-TYPE-SPECIFIC STRATEGIES
        if war_type == 'raid':
            return self._raid_strategy_priority(attack_type, attacker_analysis, defender_analysis, effectiveness, 
                                              expected_damage, expected_cost, success_probability, current_resistance,
                                              attacker_status, is_winning, is_blockaded, attack_counts)
        elif war_type == 'attrition':
            return self._attrition_strategy_priority(attack_type, attacker_analysis, defender_analysis, effectiveness,
                                                    expected_damage, expected_cost, success_probability, current_resistance,
                                                    attacker_status, is_winning, is_blockaded, economic_efficiency)
        elif war_type == 'ordinary':
            return self._ordinary_strategy_priority(attack_type, attacker_analysis, defender_analysis, effectiveness,
                                                   expected_damage, expected_cost, success_probability, current_resistance,
                                                   attacker_status, is_winning, is_blockaded, defender_units)
        
        # Fallback to generic logic
        return self._generic_strategy_priority(attack_type, attacker_analysis, defender_analysis, effectiveness,
                                              expected_damage, expected_cost, success_probability, current_resistance,
                                              attacker_status, initial_role, is_winning, is_blockaded, war_type,
                                              economic_efficiency, attack_counts, defender_units)

    def _raid_strategy_priority(self, attack_type: AttackType, attacker_analysis: Dict[str, Any], defender_analysis: Dict[str, Any], 
                               effectiveness: float, expected_damage: float, expected_cost: float,
                               success_probability: float, current_resistance: int, attacker_status: Dict[str, bool],
                               is_winning: bool, is_blockaded: bool, attack_counts: Dict[str, int]) -> AttackPriority:
        """RAID: Speed + least cost - Quick wins with minimal resource usage"""
        defender_units = defender_analysis['units']
        
        # Priority 1: Naval with 1 ship if defender has no ships (fastest resistance damage)
        if attack_type == AttackType.NAVAL_BATTLE and defender_units['ships'] == 0 and attacker_analysis['units']['ships'] > 0:
            return AttackPriority.HIGH
        
        # Priority 2: Ground with soldiers only if defender has no ground units (fastest resistance damage)
        if attack_type == AttackType.GROUND_BATTLE and defender_units['soldiers'] == 0 and defender_units['tanks'] == 0:
            return AttackPriority.HIGH
        
        # Priority 3: Break blockade if blockaded
        if attack_type == AttackType.NAVAL_BATTLE and is_blockaded:
            return AttackPriority.HIGH
        
        # Priority 4: Establish blockade (but limit naval attacks)
        if attack_type == AttackType.NAVAL_BATTLE and not attacker_status.get('blockade', False):
            if attack_counts and attack_counts.get('naval', 0) >= 5:
                return AttackPriority.LOW  # After 5 naval, deprioritize
            return AttackPriority.HIGH
        
        # Priority 5: Ground attacks (limit to 3 for efficiency)
        if attack_type == AttackType.GROUND_BATTLE:
            if attack_counts and attack_counts.get('ground', 0) >= 3:
                return AttackPriority.LOW
            return AttackPriority.HIGH
        
        # Deprioritize expensive attacks (missiles/nukes) for raids
        if attack_type in [AttackType.MISSILE_STRIKE, AttackType.NUCLEAR_STRIKE]:
            return AttackPriority.LOW
        
        return AttackPriority.LOW

    def _attrition_strategy_priority(self, attack_type: AttackType, attacker_analysis: Dict[str, Any], defender_analysis: Dict[str, Any],
                                    effectiveness: float, expected_damage: float, expected_cost: float,
                                    success_probability: float, current_resistance: int, attacker_status: Dict[str, bool],
                                    is_winning: bool, is_blockaded: bool, economic_efficiency: float) -> AttackPriority:
        """ATTRITION: Max infrastructure destruction with least cost"""
        defender_units = defender_analysis['units']
        
        # Priority 1: Use cheapest attacks first (naval with 1 ship, ground with soldiers only)
        if attack_type == AttackType.NAVAL_BATTLE and defender_units['ships'] == 0 and attacker_analysis['units']['ships'] > 0:
            return AttackPriority.HIGH
        
        if attack_type == AttackType.GROUND_BATTLE and defender_units['soldiers'] == 0 and defender_units['tanks'] == 0:
            return AttackPriority.HIGH
        
        # Priority 2: Conventional attacks with good efficiency
        if attack_type in [AttackType.NAVAL_BATTLE, AttackType.GROUND_BATTLE, AttackType.AIRSTRIKE]:
            if economic_efficiency > 5:  # Very cost-effective conventional
                return AttackPriority.HIGH
            elif economic_efficiency > 2:
                return AttackPriority.MEDIUM
        
        # Priority 3: Missiles/Nukes - ONLY if extremely cost-effective (efficiency > 20)
        # This ensures they're only used when they're 4x+ more efficient than conventional
        if attack_type in [AttackType.MISSILE_STRIKE, AttackType.NUCLEAR_STRIKE]:
            if economic_efficiency > 20:
                return AttackPriority.HIGH
            elif economic_efficiency > 10:
                return AttackPriority.MEDIUM
            else:
                return AttackPriority.LOW  # Not cost-effective enough to use
        
        return AttackPriority.LOW

    def _ordinary_strategy_priority(self, attack_type: AttackType, attacker_analysis: Dict[str, Any], defender_analysis: Dict[str, Any],
                                   effectiveness: float, expected_damage: float, expected_cost: float,
                                   success_probability: float, current_resistance: int, attacker_status: Dict[str, bool],
                                   is_winning: bool, is_blockaded: bool, defender_units: Dict[str, int]) -> AttackPriority:
        """ORDINARY: Destroy units (if any) with least cost"""
        
        # Priority 1: If defender has units, target them specifically
        total_defender_units = sum(defender_units.values())
        
        if total_defender_units > 0:
            # Naval to destroy ships
            if attack_type == AttackType.NAVAL_BATTLE and defender_units['ships'] > 0:
                return AttackPriority.HIGH
            
            # Ground to destroy soldiers/tanks
            if attack_type == AttackType.GROUND_BATTLE and (defender_units['soldiers'] > 0 or defender_units['tanks'] > 0):
                return AttackPriority.HIGH
            
            # Air to destroy aircraft
            if attack_type == AttackType.AIRSTRIKE and defender_units['aircraft'] > 0:
                return AttackPriority.HIGH
        
        # Priority 2: If no units left, focus on resistance with cheapest attacks
        if total_defender_units == 0:
            # Naval with 1 ship (cheapest high resistance damage)
            if attack_type == AttackType.NAVAL_BATTLE and defender_units['ships'] == 0 and attacker_analysis['units']['ships'] > 0:
                return AttackPriority.HIGH
            
            # Ground with soldiers only (cheapest resistance damage)
            if attack_type == AttackType.GROUND_BATTLE and defender_units['soldiers'] == 0 and defender_units['tanks'] == 0:
                return AttackPriority.HIGH
        
        # Priority 3: Break blockade if blockaded
        if attack_type == AttackType.NAVAL_BATTLE and is_blockaded:
            return AttackPriority.HIGH
        
        # Deprioritize expensive attacks when cheaper options available
        if attack_type in [AttackType.MISSILE_STRIKE, AttackType.NUCLEAR_STRIKE]:
            return AttackPriority.LOW
        
        return AttackPriority.MEDIUM

    def _generic_strategy_priority(self, attack_type: AttackType, attacker_analysis: Dict[str, Any], defender_analysis: Dict[str, Any],
                                    effectiveness: float, expected_damage: float, expected_cost: float,
                                    success_probability: float, current_resistance: int, attacker_status: Dict[str, bool],
                                    initial_role: str, is_winning: bool, is_blockaded: bool, war_type: str,
                                    economic_efficiency: float, attack_counts: Dict[str, int], defender_units: Dict[str, int]) -> AttackPriority:
        """Generic fallback strategy"""
        attacker_nation = attacker_analysis['nation']
        
        # OPTIMAL STRATEGY: 5 naval with 1 ship, then 3 ground with soldiers only
        # Priority 1: Naval battles to establish blockade (if not blockaded)
        if attack_type == AttackType.NAVAL_BATTLE and not attacker_status.get('blockade', False):
            # If defender has no ships, this is extremely efficient
            if defender_units['ships'] == 0 and attacker_analysis['units']['ships'] > 0:
                return AttackPriority.HIGH
            # If blockaded, break blockade immediately
            if is_blockaded:
                return AttackPriority.HIGH
            # Otherwise, still prioritize naval for optimal strategy
            return AttackPriority.HIGH
        
        # Priority 2: Ground battles after blockade established (limit to 3 for optimal strategy)
        if attack_type == AttackType.GROUND_BATTLE and attacker_status.get('blockade', False):
            # Use attack_counts to limit to 3 ground attacks after blockade
            if attack_counts and attack_counts.get('ground', 0) >= 3:
                return AttackPriority.NONE  # Completely block after optimal 3 attacks
            # If defender has no ground units, this is extremely efficient
            if defender_units['soldiers'] == 0 and defender_units['tanks'] == 0:
                return AttackPriority.HIGH
            return AttackPriority.HIGH
        
        # Priority 3: Take Air Superiority if needed for weakening
        if attack_type == AttackType.AIRSTRIKE and not attacker_status.get('as', False):
            if defender_units['aircraft'] > 0:
                return AttackPriority.MEDIUM
        
        # Priority 4: Take Ground Control if needed
        if attack_type == AttackType.GROUND_BATTLE and not attacker_status.get('gc', False):
            if defender_units['soldiers'] > 0 or defender_units['tanks'] > 0:
                return AttackPriority.MEDIUM
        
        # If we have optimal setup (blockade + ground control), focus on resistance
        if attacker_status.get('blockade', False) and attacker_status.get('gc', False):
            if effectiveness > 0.8 and expected_damage > 100:
                return AttackPriority.HIGH

        if initial_role == 'attacker' and attack_type in [AttackType.AIRSTRIKE, AttackType.GROUND_BATTLE]:
            effectiveness *= 1.1

        if not is_winning and attack_type in [AttackType.MISSILE_STRIKE, AttackType.NUCLEAR_STRIKE]:
            return AttackPriority.MEDIUM

        if attack_type == AttackType.FORTIFY:
            fortify_priority = AttackPriority.NONE
            
            # Cannot fortify without military units
            total_military = (attacker_nation.get('soldiers', 0) + 
                            attacker_nation.get('tanks', 0) + 
                            attacker_nation.get('aircraft', 0) + 
                            attacker_nation.get('ships', 0))
            if total_military == 0:
                return AttackPriority.NONE
            
            # Fortify if losing and outmatched
            if not is_winning and attacker_analysis['raw_power'] < defender_analysis['raw_power'] * 0.75:
                fortify_priority = AttackPriority.LOW
            
            # Fortify if enemy has nukes/missiles and we have no defense
            if defender_analysis['capabilities']['can_missile'] and not self._has_project(attacker_nation, 'Iron Dome'):
                fortify_priority = AttackPriority.MEDIUM
            if defender_analysis['capabilities']['can_nuke'] and not self._has_project(attacker_nation, 'Vital Defense System'):
                fortify_priority = AttackPriority.MEDIUM

            if attacker_status.get('fortified', False):
                return AttackPriority.NONE

            return fortify_priority

        if effectiveness > 0.8 and expected_damage > 100 and success_probability > 0.7:
            priority = AttackPriority.HIGH
        elif effectiveness > 0.5 and expected_damage > 50 and success_probability > 0.5:
            priority = AttackPriority.MEDIUM
        elif effectiveness > 0.3 and expected_damage > 25 and success_probability > 0.3:
            priority = AttackPriority.LOW
        else:
            return AttackPriority.NONE
        
        if current_resistance < 20 and attack_type in [AttackType.MISSILE_STRIKE, AttackType.NUCLEAR_STRIKE]:
            priority = AttackPriority.HIGH
        elif current_resistance < 50 and effectiveness > 0.6:
            priority = AttackPriority.HIGH
        
        if economic_efficiency > 10:
            priority = AttackPriority.HIGH
        elif economic_efficiency < 1 and priority.value > 1:
            priority = AttackPriority(priority.value - 1)
        
        return priority

    def _generate_attack_reasoning(self, attack_type: AttackType, effectiveness: float, 
                                 expected_damage: float, success_probability: float, 
                                 priority: AttackPriority) -> str:
        
        parts = []
        attack_name = attack_type.value.title()
        
        if effectiveness > 0.8:
            parts.append(f"{attack_name} is highly effective")
        elif effectiveness > 0.5:
            parts.append(f"{attack_name} is moderately effective")
        else:
            parts.append(f"{attack_name} has limited effectiveness")
        
        if expected_damage > 200:
            parts.append(f"can deal massive damage ({expected_damage:,.0f} infra)")
        elif expected_damage > 100:
            parts.append(f"can deal significant damage ({expected_damage:,.0f} infra)")
        elif expected_damage > 50:
            parts.append(f"can deal moderate damage ({expected_damage:,.0f} infra)")
        
        if success_probability > 0.8:
            parts.append(f"with very high success rate ({success_probability:.1%})")
        elif success_probability > 0.6:
            parts.append(f"with good success rate ({success_probability:.1%})")
        
        if priority == AttackPriority.HIGH:
            parts.append("- STRONG RECOMMENDATION")
        elif priority == AttackPriority.MEDIUM:
            parts.append("- viable option")
        
        return " ".join(parts) if parts else "No specific reasoning available"

    def _has_project(self, nation: Dict[str, Any], project_name: str) -> bool:
        return has_project(nation, project_name)

    def _calculate_average_infrastructure(self, nation: Dict[str, Any]) -> float:
        cities = nation.get('cities', {})
        if not cities:
            return 0.0
        total_infra = sum(city.get('infrastructure', 0) for city in cities.values())
        return total_infra / len(cities) if cities else 0.0

    def _calculate_population_density(self, nation: Dict[str, Any]) -> float:
        population = nation.get('population', 0)
        cities = nation.get('cities', {})
        if not cities or population <= 0:
            return 0.0
        total_land = sum(city.get('land', 0) for city in cities.values())
        return population / total_land if total_land > 0 else 0.0

    def _calculate_ground_strength(self, soldiers: int, tanks: int) -> float:
        return soldiers * 1.75 + tanks * 40

    def _calculate_air_strength(self, aircraft: int) -> float:
        return aircraft * 100

    def _calculate_naval_strength(self, ships: int) -> float:
        return ships * 200

    def _calculate_relative_strength(self, attacker_strength: float, defender_strength: float) -> float:
        if defender_strength == 0:
            return 1.0 if attacker_strength > 0 else 0.0
        return min(attacker_strength / defender_strength, 2.0)

    def _get_default_capabilities(self) -> Dict[str, Any]:
        return {
            'units': {'soldiers': 0, 'tanks': 0, 'aircraft': 0, 'ships': 0, 'missiles': 0, 'nukes': 0},
            'capabilities': {'can_missile': False, 'can_nuke': False, 'has_ground': False, 'has_air': False, 'has_naval': False},
            'strengths': {'ground': 0, 'air': 0, 'naval': 0},
            'economic': {'avg_infrastructure': 0, 'population_density': 0, 'total_infra': 0},
            'raw_power': 0
        }

    def _get_fallback_recommendation(self) -> AttackRecommendation:
        return AttackRecommendation(AttackType.NO_ATTACK, AttackPriority.NONE, "Error in attack analysis", 0.0, 0.0, 0.0, 0, 0.0)
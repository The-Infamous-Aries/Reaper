import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
import re
import json
import math
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timezone, timedelta
import sys
import logging
import traceback

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from Systems.PnW.Util.query import create_v3_query_instance, V3GraphQuery

from Systems.Functions.emoji import SPY_EMOJI, SOLDIER_EMOJI, TANK_EMOJI, JET_EMOJI, SHIP_EMOJI, mention
from Systems.Functions.config import PANDW_API_KEY
from Systems.Functions.user_data_manager import UserDataManager
from Systems.Functions.db_paths import GLOBAL_NATIONS_DB
from Systems.PnW.MA.weapon_eff import get_weapon_damage, calc_infra_value, infra_price
from Systems.PnW.Util.war_calc import get_resource_prices, calculate_unit_cost
from Systems.PnW.Util.attacks_calc import GroundBattleCalculator
from Systems.PnW.Util.rev_correct import calculate_population_effects

AllianceManager = None

# ── Module-level autocomplete functions ───────────────────────────────────────
# Must be defined at module level so @app_commands.autocomplete can bind them
# before the Cog class is instantiated.

async def _destroy_target_autocomplete(
    interaction: discord.Interaction, current: str
) -> List[app_commands.Choice[str]]:
    """Autocomplete for the destroy command's target (nation) parameter."""
    try:
        from Systems.Functions.autocomplete_utils import nation_autocomplete
        return await nation_autocomplete(current, nw_only=False, limit=25)
    except Exception as e:
        logging.getLogger(__name__).error(f"destroy target autocomplete error: {e}")
        return []


async def _destroy_attackers_autocomplete(
    interaction: discord.Interaction, current: str
) -> List[app_commands.Choice[str]]:
    """Autocomplete for the destroy command's attackers (alliance) parameter.

    Supports comma-separated input — autocompletes the last token so users can
    keep typing additional alliances after a comma.
    """
    try:
        from Systems.Functions.autocomplete_utils import alliance_autocomplete

        # If the user has typed multiple comma-separated values, only autocomplete
        # the portion after the last comma so existing selections are preserved.
        if "," in current:
            prefix = current[: current.rfind(",") + 1]  # everything up to & including last comma
            partial = current[current.rfind(",") + 1 :].strip()
        else:
            prefix = ""
            partial = current

        raw_choices = await alliance_autocomplete(partial, include_nw=True, limit=25)

        if prefix:
            # Re-prefix each choice value so the full string is preserved
            return [
                app_commands.Choice(name=choice.name, value=f"{prefix}{choice.value}")
                for choice in raw_choices
            ]
        return raw_choices
    except Exception as e:
        logging.getLogger(__name__).error(f"destroy attackers autocomplete error: {e}")
        return []

class DestroyCog(commands.Cog):
    """Cog for managing war destruction commands."""
    
    def __init__(self, bot: commands.Bot):
        try:
            self.bot = bot
            self.api_key = PANDW_API_KEY
            self.user_data_manager = UserDataManager()
            self.home_alliance_id = None
            self.logger = logging.getLogger(__name__)
            if not self.logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)
                self.logger.setLevel(logging.INFO)
            self.error_count = 0
            self.max_errors = 100
            # pnwkit disabled; rely solely on centralized query instance
            self.query_instance: Optional[V3GraphQuery] = None
            self.calculator = self  # Reference to self for military calculations
            try:
                self.query_instance = create_v3_query_instance()
                self.logger.info("Centralized query instance initialized successfully")
                if hasattr(self.query_instance, 'cache_ttl_seconds'):
                    self.query_instance.cache_ttl_seconds = 3600
            except Exception as e:
                self.logger.error(f"Failed to initialize query instance: {e}")
                self.query_instance = None
        except Exception as e:
            print(f"Error initializing DestroyCog: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            self.bot = bot
            self.api_key = PANDW_API_KEY
            self.user_data_manager = UserDataManager()
            self.home_alliance_id = None
            self.error_count = 0
            self.max_errors = 100
            self.query_instance = None

    def _log_error(self, error_msg: str, exception: Optional[Exception] = None, context: str = ""):
        """Log error messages with optional exception details."""
        full_msg = error_msg
        if context:
            full_msg = f"{context}: {error_msg}"
        
        if exception:
            self.logger.error(f"{full_msg} - {str(exception)}")
            self.logger.debug(f"Traceback: {traceback.format_exc()}")
        else:
            self.logger.error(full_msg)

    def _extract_nation_id_from_link(self, text: str) -> Optional[str]:
        """Extract nation ID from various formats (link, ID, name)."""
        if not text:
            return None
        
        text = str(text).strip()
        
        # Check if it's a pure numeric ID
        if text.isdigit():
            return text
        
        # Extract from URL patterns
        patterns = [
            r"nation_id=(\d+)",
            r"id=(\d+)",
            r"/nations/(\d+)",
            r"/nation/id=(\d+)"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        
        return None

    def _seconds_since_last_active(self, nation: Dict[str, Any]) -> Optional[int]:
        """Calculate seconds since last active."""
        try:
            last_active = nation.get('last_active')
            if not last_active:
                return None
            
            # Parse timestamp
            if isinstance(last_active, (int, float)):
                last_active_dt = datetime.fromtimestamp(last_active, tz=timezone.utc)
            elif isinstance(last_active, str):
                # Handle ISO format
                if last_active.endswith('Z'):
                    last_active = last_active[:-1] + '+00:00'
                try:
                    last_active_dt = datetime.fromisoformat(last_active).replace(tzinfo=timezone.utc)
                except ValueError:
                    try:
                        # Try parsing as timestamp string
                        ts = float(last_active)
                        last_active_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    except (ValueError, TypeError):
                        return None
            else:
                return None
            
            now = datetime.now(timezone.utc)
            delta = now - last_active_dt
            return int(delta.total_seconds())
        except Exception:
            return None

    async def _fetch_nation_holdings_from_db(self, nation_id: int) -> Optional[Dict[str, Any]]:
        """Fetch nation holdings from GlobalNationsDB."""
        try:
            from PnWHarvester.db.global_nations_db import GlobalNationsDB
            
            db = GlobalNationsDB(str(GLOBAL_NATIONS_DB))
            nation = await db.get_nation(nation_id)
            
            if nation:
                return {
                    'money': nation.get('money', 0) or 0,
                    'gasoline': nation.get('gasoline', 0) or 0,
                    'munitions': nation.get('munitions', 0) or 0,
                    'coal': nation.get('coal', 0) or 0,
                    'oil': nation.get('oil', 0) or 0,
                    'uranium': nation.get('uranium', 0) or 0,
                    'iron': nation.get('iron', 0) or 0,
                    'bauxite': nation.get('bauxite', 0) or 0,
                    'lead': nation.get('lead', 0) or 0,
                    'steel': nation.get('steel', 0) or 0,
                    'aluminum': nation.get('aluminum', 0) or 0,
                    'food': nation.get('food', 0) or 0,
                }
            return None
        except Exception as e:
            self._log_error(f"Error fetching holdings from DB: {e}", e, "_fetch_nation_holdings_from_db")
            return None

    def _warchest_level(self, nation: Dict[str, Any]) -> int:
        """Calculate warchest level based on resources."""
        try:
            gasoline = nation.get('gasoline', 0) or 0
            munitions = nation.get('munitions', 0) or 0
            min_resource = min(gasoline, munitions)
            
            if min_resource >= 10000:
                return 4  # Stacked
            elif min_resource >= 5000:
                return 3  # Full
            elif min_resource >= 3750:
                return 2  # 3/4
            elif min_resource >= 2500:
                return 1  # 1/2
            elif min_resource >= 1250:
                return 0  # 1/4
            else:
                return -1  # No warchest
        except Exception:
            return -1

    def has_project(self, nation: Dict[str, Any], project_name: str) -> bool:
        """Check if a nation has a specific project."""
        try:
            if not isinstance(nation, dict):
                return False
            
            # Project field mapping (normalized to snake_case)
            project_mapping = {
                'Missile Launch Pad': 'missile_launch_pad',
                'Nuclear Research Facility': 'nuclear_research_facility',
                'Iron Dome': 'iron_dome',
                'Vital Defense System': 'vital_defense_system',
                'Propaganda Bureau': 'propaganda_bureau',
                'Military Research Center': 'military_research_center',
                'Space Program': 'space_program',
                'Nuclear Launch Facility': 'nuclear_launch_facility',
                'Activity Center': 'activity_center',
                'Advanced Engineering Corps': 'advanced_engineering_corps',
                'Advanced Pirate Economy': 'advanced_pirate_economy',
                'Arable Land Agency': 'arable_land_agency',
                'Arms Stockpile': 'arms_stockpile',
                'Bauxite Works': 'bauxite_works',
                'Bureau of Domestic Affairs': 'bureau_of_domestic_affairs',
                'Center for Civil Engineering': 'center_for_civil_engineering',
                'Clinical Research Center': 'clinical_research_center',
                'Emergency Gasoline Reserve': 'emergency_gasoline_reserve',
                'Fallout Shelter': 'fallout_shelter',
                'Green Technologies': 'green_technologies',
                'Government Support Agency': 'government_support_agency',
                'Guiding Satellite': 'guiding_satellite',
                'Central Intelligence Agency': 'central_intelligence_agency',
                'International Trade Center': 'international_trade_center',
                'Iron Works': 'iron_works',
                'Mass Irrigation': 'mass_irrigation',
                'Military Doctrine': 'military_doctrine',
                'Military Salvage': 'military_salvage',
                'Mars Landing': 'mars_landing',
                'Moon Landing': 'moon_landing',
                'Pirate Economy': 'pirate_economy',
                'Recycling Initiative': 'recycling_initiative',
                'Research & Development Center': 'research_and_development_center',
                'Specialized Police Training Program': 'specialized_police_training_program',
                'Spy Satellite': 'spy_satellite',
                'Surveillance Network': 'surveillance_network',
                'Telecommunications Satellite': 'telecommunications_satellite',
                'Uranium Enrichment Program': 'uranium_enrichment_program'
            }
            
            field_name = project_mapping.get(project_name)
            if field_name:
                value = nation.get(field_name)
                return bool(value)
            
            # Also check if project_name is already a field
            if project_name in nation:
                return bool(nation[project_name])
            
            return False
        except Exception:
            return False

    async def _get_live_weapon_costs(self) -> Dict[str, float]:
        """Live missile/nuke costs, using the same market logic as /weapon_eff."""
        fallback = {'missile': 150000.0, 'nuke': 1750000.0, 'source': 'fallback'}
        try:
            resource_prices = await get_resource_prices()
            if not resource_prices or 'sell' not in resource_prices:
                return fallback
            missile_cost = calculate_unit_cost('missiles', resource_prices['sell'])
            nuke_cost = calculate_unit_cost('nukes', resource_prices['sell'])
            if missile_cost <= 0 or nuke_cost <= 0:
                return fallback
            return {'missile': float(missile_cost), 'nuke': float(nuke_cost), 'source': 'live'}
        except Exception as e:
            self._log_error("Error fetching live weapon costs", e, "_get_live_weapon_costs")
            return fallback

    def _weapon_city_population_and_density(self, city: Dict[str, Any]) -> Tuple[float, float]:
        """Weapon Eff population and displayed density calculation."""
        infra = city.get('infrastructure', 0) or 0
        land = max(city.get('land', 0) or 0, 1)
        base_pop = infra * 100

        powered = city.get('powered', True)
        commerce = 0.0
        if powered:
            commerce += city.get('subway', 0) * 8
            commerce += city.get('supermarket', 0) * 4
            commerce += city.get('bank', 0) * 6
            commerce += city.get('shopping_mall', 0) * 8
            commerce += city.get('stadium', 0) * 10
        commerce = min(commerce, 100)

        pollution = 0.0
        if powered:
            pollution += city.get('police_station', 0)
            pollution += city.get('hospital', 0) * 4
            pollution -= city.get('recycling_center', 0) * 70
            pollution -= city.get('subway', 0) * 45
            pollution += city.get('shopping_mall', 0) * 2
            pollution += city.get('stadium', 0) * 5
        pollution = max(pollution, 0)

        police_stations = city.get('police_station', 0) if powered else 0
        hospitals = city.get('hospital', 0) if powered else 0
        modifiers = {'pol_cri_red': 2.5, 'hos_dis_red': 2.5}
        if city.get('clinical_research_center'):
            modifiers['hos_dis_red'] = 3.5
        if city.get('specialized_police_training_program'):
            modifiers['pol_cri_red'] = 3.5

        city_for_calc = dict(city)
        city_for_calc['infrastructure'] = infra
        city_for_calc['land'] = land
        pop_result = calculate_population_effects(
            city_for_calc, modifiers, base_pop, commerce, police_stations, hospitals, pollution
        )
        actual_pop = float(pop_result['population'])
        return actual_pop, max(actual_pop / land, 1.0)

    def _weapon_impact_chance(self, nation: Dict[str, Any], weapon: str) -> float:
        if weapon == 'missile':
            return 0.70 if self.has_project(nation, 'Iron Dome') else 1.0
        return 0.75 if self.has_project(nation, 'Vital Defense System') else 1.0

    def _weapon_city_score(
        self,
        city: Dict[str, Any],
        nation: Dict[str, Any],
        weapon: str,
        weapon_cost: float,
    ) -> Dict[str, Any]:
        infra = city.get('infrastructure', 0) or 0
        actual_pop, pop_density = self._weapon_city_population_and_density(city)
        hit_chance = self._weapon_impact_chance(nation, weapon)

        avg_dmg = get_weapon_damage(infra, weapon, pop_density, 'average')
        min_dmg = get_weapon_damage(infra, weapon, pop_density, 'min')
        max_dmg = get_weapon_damage(infra, weapon, pop_density, 'max')

        avg_val = calc_infra_value(infra - avg_dmg, infra)
        min_val = calc_infra_value(infra - min_dmg, infra)
        max_val = calc_infra_value(infra - max_dmg, infra)

        return {
            'city': city,
            'infra': infra,
            'pop_density': pop_density,
            'actual_pop': actual_pop,
            'hit_chance': hit_chance,
            'avg_dmg': avg_dmg,
            'min_dmg': min_dmg,
            'max_dmg': max_dmg,
            'avg_val': avg_val,
            'min_val': min_val,
            'max_val': max_val,
            'expected_val': avg_val * hit_chance,
            'avg_mult': avg_val / weapon_cost if weapon_cost else 0,
            'expected_mult': (avg_val * hit_chance) / weapon_cost if weapon_cost else 0,
            'max_mult': max_val / weapon_cost if weapon_cost else 0,
        }

    def _best_weapon_city(
        self,
        nation: Dict[str, Any],
        weapon: str,
        weapon_cost: float,
    ) -> Optional[Dict[str, Any]]:
        scores = [
            self._weapon_city_score(city, nation, weapon, weapon_cost)
            for city in (nation.get('cities') or [])
            if isinstance(city, dict)
        ]
        if not scores:
            return None
        return max(scores, key=lambda s: s['expected_val'])

    def _analyze_weapon_optimal_for_target(
        self,
        target_nation: Dict[str, Any],
        weapon_costs: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Analyze whether missiles or nukes are optimal against this target.
        
        Returns:
            Dict with:
            - optimal_weapon: 'missile', 'nuke', or 'ground'
            - best_city: city dict with highest infra
            - missile_analysis: damage, cost, efficiency
            - nuke_analysis: damage, cost, efficiency
            - requires_missile_capable: bool
            - requires_nuke_capable: bool
        """
        try:
            cities = target_nation.get('cities', [])
            if not cities:
                return {'optimal_weapon': 'ground', 'reason': 'No cities'}

            missile_cost = float((weapon_costs or {}).get('missile') or 150000)
            nuke_cost = float((weapon_costs or {}).get('nuke') or 1750000)
            cost_source = (weapon_costs or {}).get('source', 'fallback')
            has_iron_dome = self.has_project(target_nation, 'Iron Dome')
            has_vds = self.has_project(target_nation, 'Vital Defense System')

            missile_score = self._best_weapon_city(target_nation, 'missile', missile_cost)
            nuke_score = self._best_weapon_city(target_nation, 'nuke', nuke_cost)
            if not missile_score and not nuke_score:
                return {'optimal_weapon': 'ground', 'reason': 'No scorable cities'}

            missile_mult = float((missile_score or {}).get('avg_mult', 0) or 0)
            nuke_mult = float((nuke_score or {}).get('avg_mult', 0) or 0)

            min_weapon_mult = 2.0
            if missile_mult >= min_weapon_mult and missile_mult >= nuke_mult:
                optimal = 'missile'
                best_score = missile_score
            elif nuke_mult >= min_weapon_mult and nuke_mult > missile_mult:
                optimal = 'nuke'
                best_score = nuke_score
            else:
                optimal = 'ground'
                best_score = missile_score if missile_mult >= nuke_mult else nuke_score

            def _analysis_payload(score: Optional[Dict[str, Any]], cost: float) -> Dict[str, Any]:
                if not score:
                    return {
                        'damage': 0,
                        'min_damage': 0,
                        'max_damage': 0,
                        'value': 0,
                        'min_value': 0,
                        'max_value': 0,
                        'cost': cost,
                        'efficiency': 0,
                        'expected_value': 0,
                        'expected_efficiency': 0,
                        'hit_chance': 0,
                        'city': None,
                    }
                return {
                    'damage': score['avg_dmg'],
                    'min_damage': score['min_dmg'],
                    'max_damage': score['max_dmg'],
                    'value': score['avg_val'],
                    'min_value': score['min_val'],
                    'max_value': score['max_val'],
                    'cost': cost,
                    # Weapon Eff ratio shown in web tables is avg infra value / weapon cost.
                    'efficiency': score['avg_mult'],
                    'expected_value': score['expected_val'],
                    'expected_efficiency': score['expected_mult'],
                    'hit_chance': score['hit_chance'],
                    'pop_density': score['pop_density'],
                    'actual_pop': score['actual_pop'],
                    'city': score['city'],
                }
            
            return {
                'optimal_weapon': optimal,
                'best_city': best_score.get('city') if best_score else {},
                'best_city_infra': best_score.get('infra', 0) if best_score else 0,
                'pop_density': best_score.get('pop_density', 0) if best_score else 0,
                'weapon_cost_source': cost_source,
                'missile_analysis': _analysis_payload(missile_score, missile_cost),
                'nuke_analysis': _analysis_payload(nuke_score, nuke_cost),
                'requires_missile_capable': optimal == 'missile',
                'requires_nuke_capable': optimal == 'nuke',
                'has_iron_dome': has_iron_dome,
                'has_vds': has_vds
            }
        except Exception as e:
            self._log_error(f"Error analyzing weapon optimal: {e}", e, "_analyze_weapon_optimal_for_target")
            return {'optimal_weapon': 'ground', 'reason': f'Error: {e}'}

    def _simulate_ground_battle_outcome(
        self,
        attacker: Dict[str, Any],
        defender: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Simulate a ground battle to determine if attacker can win.
        
        Returns:
            Dict with:
            - can_win: bool
            - victory_type: int (0-3)
            - expected_casualties: dict
            - expected_loot: float
            - ground_control_gain: bool
        """
        try:
            calculator = GroundBattleCalculator()
            
            # Munitions determine whether each side's soldiers fight armed.
            atk_munitions = attacker.get('munitions', 0) or 0
            atk_soldiers = attacker.get('soldiers', 0) or 0
            def_munitions = defender.get('munitions', 0) or 0
            def_soldiers = defender.get('soldiers', 0) or 0
            soldier_type = 'armed' if atk_munitions >= (atk_soldiers * 0.0002) else 'unarmed'
            
            # Get city infrastructure for damage calc
            cities = defender.get('cities', [])
            city_infra = 0
            if cities:
                city_infra = max((c.get('infrastructure', 0) or 0 for c in cities if isinstance(c, dict)), default=0)
            
            # Simulate battle
            result = calculator.simulate_ground_battle(
                war_type='ordinary',  # Default to ordinary
                soldier_type=soldier_type,
                attacker_has_gc=False,  # Would need to check actual GC status
                defender_has_gc=False,
                defender_has_as=False,
                defender_has_blockade=False,
                defender_fortified=False,  # Would need to check fortification
                
                attacking_soldiers=atk_soldiers,
                attacking_tanks=attacker.get('tanks', 0) or 0,
                attacking_aircraft=attacker.get('aircraft', 0) or 0,
                attacking_ships=attacker.get('ships', 0) or 0,
                
                defending_soldiers=def_soldiers,
                defending_tanks=defender.get('tanks', 0) or 0,
                defending_aircraft=defender.get('aircraft', 0) or 0,
                defending_ships=defender.get('ships', 0) or 0,
                defending_munitions=def_munitions,
                
                city_infrastructure=city_infra,
                defender_cash=defender.get('money', 0) or 0,
                
                attacker_policy=attacker.get('war_policy') or 'none',
                defender_policy=defender.get('war_policy') or 'none'
            )
            
            # Determine if attacker can win (victory_type > 0 means not utter failure)
            can_win = result.get('victory_type', 0) > 0
            
            return {
                'can_win': can_win,
                'victory_type': result.get('victory_type', 0),
                'casualties': result.get('casualties', {}),
                'loot': result.get('loot', {}).get('actual_loot', 0),
                'infra_damage': result.get('infrastructure_damage', 0),
                'ground_control': result.get('ground_control', {}),
                'resistance_loss': result.get('resistance_loss', 0)
            }
        except Exception as e:
            self._log_error(f"Error simulating ground battle: {e}", e, "_simulate_ground_battle_outcome")
            return {'can_win': False, 'error': str(e)}

    def _calculate_combat_score(
        self,
        attacker: Dict[str, Any],
        defender: Dict[str, Any]
    ) -> float:
        """
        Calculate a combat score based on simulated battle outcome.
        
        Higher score = better attacker.
        """
        try:
            return float(self._combat_simulation_analysis(attacker, defender).get('combat_score', 0) or 0)
        except Exception as e:
            self._log_error(f"Error calculating combat score: {e}", e, "_calculate_combat_score")
            return 0

    def calculate_military_purchase_limits(self, nation: Dict[str, Any]) -> Dict[str, int]:
        """Calculate military purchase limits based on nation's cities and research."""
        try:
            cities_data = nation.get('cities', [])
            num_cities = nation.get('num_cities', 0)
            
            total_barracks = 0
            total_factories = 0
            total_hangars = 0
            total_drydocks = 0
            
            if isinstance(cities_data, list) and len(cities_data) > 0:
                for city in cities_data:
                    total_barracks += city.get('barracks', 0)
                    total_factories += city.get('factory', 0)
                    total_hangars += city.get('hangar', 0)
                    total_drydocks += city.get('drydock', 0)
            else:
                avg_improvements = 2
                total_barracks = num_cities * avg_improvements
                total_factories = num_cities * avg_improvements
                total_hangars = num_cities * avg_improvements
                total_drydocks = num_cities * avg_improvements

            # Military Research capacity levels
            # Handle both dict (from API) and string (from DB JSON)
            mr = nation.get('military_research')
            if isinstance(mr, str):
                # Parse JSON string from DB
                try:
                    mr = json.loads(mr)
                except:
                    mr = {}
            elif not isinstance(mr, dict):
                mr = {}
            
            ground_cap_lvl = int(mr.get('ground_capacity', 0) or nation.get('ground_capacity', 0) or 0)
            air_cap_lvl    = int(mr.get('air_capacity',    0) or nation.get('air_capacity',    0) or 0)
            naval_cap_lvl  = int(mr.get('naval_capacity',  0) or nation.get('naval_capacity',  0) or 0)

            # Cap at max 20 levels each
            ground_cap_lvl = min(ground_cap_lvl, 20)
            air_cap_lvl    = min(air_cap_lvl,    20)
            naval_cap_lvl  = min(naval_cap_lvl,  20)

            soldier_cap_bonus  = ground_cap_lvl * 3000
            tank_cap_bonus     = ground_cap_lvl * 250
            aircraft_cap_bonus = air_cap_lvl    * 15
            ship_cap_bonus     = naval_cap_lvl  * 5

            # Base daily limits
            soldier_daily = total_barracks * 1000
            tank_daily    = total_factories * 50
            aircraft_daily = total_hangars * 3
            ship_daily    = total_drydocks * 1

            # Apply capacity bonuses to daily limits — only if nation has at least 1 of the improvement type
            if total_barracks > 0:
                soldier_daily  += soldier_cap_bonus
            if total_factories > 0:
                tank_daily     += tank_cap_bonus
            if total_hangars > 0:
                aircraft_daily += aircraft_cap_bonus
            if total_drydocks > 0:
                ship_daily     += ship_cap_bonus

            # Propaganda Bureau bonus
            if self.has_project(nation, 'Propaganda Bureau'):
                soldier_daily  = int(soldier_daily  * 1.10)
                tank_daily     = int(tank_daily     * 1.10)
                aircraft_daily = int(aircraft_daily * 1.10)
                ship_daily     = int(ship_daily     * 1.10)

            # Max capacities
            soldier_max  = total_barracks * 3000
            tank_max     = total_factories * 250
            aircraft_max = total_hangars * 15
            ship_max     = total_drydocks * 5

            # Max capacity — same improvement-type gating
            if total_barracks > 0:
                soldier_max  += soldier_cap_bonus
            if total_factories > 0:
                tank_max     += tank_cap_bonus
            if total_hangars > 0:
                aircraft_max += aircraft_cap_bonus
            if total_drydocks > 0:
                ship_max     += ship_cap_bonus

            # Missile and nuke limits
            missile_limit = 0
            nuke_limit = 0
            
            if self.has_project(nation, 'Missile Launch Pad'):
                missile_limit = 2
                if self.has_project(nation, 'Space Program'):
                    missile_limit = 3
            
            if self.has_project(nation, 'Nuclear Research Facility'):
                nuke_limit = 1
                if (self.has_project(nation, 'Nuclear Launch Facility') and 
                    self.has_project(nation, 'Missile Launch Pad') and
                    self.has_project(nation, 'Space Program')):
                    nuke_limit = 2
            
            return {
                'soldiers_daily': soldier_daily,
                'tanks_daily':    tank_daily,
                'aircraft_daily': aircraft_daily,
                'ships_daily':    ship_daily,
                'missiles':       missile_limit,
                'nukes':          nuke_limit,
                'soldiers_max':   soldier_max,
                'tanks_max':      tank_max,
                'aircraft_max':   aircraft_max,
                'ships_max':      ship_max,
                'total_barracks': total_barracks,
                'total_factories': total_factories,
                'total_hangars':  total_hangars,
                'total_drydocks': total_drydocks
            }
        except Exception as e:
            self._log_error(f"Error calculating military purchase limits: {e}", e, "calculate_military_purchase_limits")
            return {
                'soldiers_daily': 0, 'tanks_daily': 0, 'aircraft_daily': 0, 'ships_daily': 0,
                'missiles': 0, 'nukes': 0,
                'soldiers_max': 0, 'tanks_max': 0, 'aircraft_max': 0, 'ships_max': 0,
                'total_barracks': 0, 'total_factories': 0, 'total_hangars': 0, 'total_drydocks': 0
            }

    def validate_attack_range(self, attacker_score: float, defender_score: float) -> bool:
        """Validate if attacker can war defender based on score range."""
        try:
            if attacker_score <= 0 or defender_score <= 0:
                return False
            
            min_score = attacker_score * 0.75  # -25%
            max_score = attacker_score * 2.5   # +150%
            
            return min_score <= defender_score <= max_score
        except Exception:
            return False

    def _check_war_range_compatibility(self, nation1: Dict[str, Any], nation2: Dict[str, Any]) -> bool:
        """Check if two nations can war each other based on score range (-25% to 150%)"""
        try:
            score1 = nation1.get('score', 0)
            score2 = nation2.get('score', 0)
            
            if score1 <= 0 or score2 <= 0:
                return False
            
            # War range: -25% to +150% of their score
            min_range = score1 * 0.75  # -25%
            max_range = score1 * 2.5   # +150%
            
            return min_range <= score2 <= max_range
            
        except Exception as e:
            self._log_error("Error checking war range compatibility", e)
            return False

    def _analyze_party(self, party: List[Dict[str, Any]], target_nation: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a party for unit coverage and calculate a score using combat simulation."""
        try:
            if len(party) < 1:
                return {'is_valid': False, 'error': 'Party must have at least 1 member'}
            
            # Check unit coverage
            has_ground = False
            has_air = False
            has_navy = False
            has_missile_or_nuke = False
            
            total_infra = 0
            total_combat_score = 0
            unit_coverage_count = 0
            
            for member in party:
                # Calculate combat score against target
                combat_score = self._calculate_combat_score(member, target_nation)
                total_combat_score += combat_score
                
                # Get current military units
                soldiers = member.get('soldiers', 0)
                tanks = member.get('tanks', 0)
                aircraft = member.get('aircraft', 0)
                ships = member.get('ships', 0)
                
                if soldiers > 0 or tanks > 0:
                    has_ground = True
                if aircraft > 0:
                    has_air = True
                if ships > 0:
                    has_navy = True
                
                # Check missile/nuke capability
                if (member.get('missiles', 0) > 0 or 
                    member.get('nukes', 0) > 0 or
                    self.has_project(member, 'Missile Launch Pad') or
                    self.has_project(member, 'Nuclear Research Facility')):
                    has_missile_or_nuke = True
                
                # Calculate infrastructure
                total_infra += member.get('infra_average', member.get('infrastructure', 0))
            
            # Count unit coverage types
            unit_coverage_count = sum([has_ground, has_air, has_navy])
            
            # Must have at least 1 unit type for single attacker, 2 for multiple
            min_coverage = 1 if len(party) == 1 else 2
            if unit_coverage_count < min_coverage:
                return {'is_valid': False, 'error': f'Insufficient unit coverage (need {min_coverage})'}
            
            # Calculate scores
            avg_infra = total_infra / len(party)
            
            # Infrastructure score (lower is better for attackers)
            infra_score = 1000 / (avg_infra + 1)
            
            # Combat strength score (from simulation)
            combat_score = total_combat_score / 100
            
            # Strategic bonus for missile/nuke capability
            strategic_bonus = 200 if has_missile_or_nuke else 0
            
            # Unit coverage bonus (more coverage = better)
            unit_coverage_bonus = unit_coverage_count * 50
            
            # Final score
            final_score = infra_score + combat_score + unit_coverage_bonus + strategic_bonus
            
            return {
                'is_valid': True,
                'score': final_score,
                'total_infrastructure': total_infra,
                'avg_infrastructure': avg_infra,
                'total_combat_score': total_combat_score,
                'unit_coverage': {
                    'ground': has_ground,
                    'air': has_air,
                    'navy': has_navy,
                    'unit_types_count': unit_coverage_count
                },
                'strategic_capabilities': {
                    'missile_or_nuke': has_missile_or_nuke
                }
            }
            
        except Exception as e:
            self._log_error("Error analyzing party", e)
            return {'is_valid': False, 'error': str(e)}

    def _max_offensive_slots(self, nation: Dict[str, Any]) -> int:
        """PnW offensive slots: 5 base, +1 PE, +1 APE."""
        try:
            return 5 + int(bool(nation.get('pirate_economy'))) + int(bool(nation.get('advanced_pirate_economy')))
        except Exception:
            return 5

    def _slot_state(
        self,
        nation: Dict[str, Any],
        active_war_counts: Optional[Dict[int, Dict[str, int]]] = None,
    ) -> Dict[str, int]:
        """Return current/open offensive and defensive war slots for a nation."""
        try:
            nation_id = int(nation.get('id') or nation.get('nation_id') or 0)
        except Exception:
            nation_id = 0

        live = (active_war_counts or {}).get(nation_id, {}) if nation_id else {}
        offensive_current = int(live.get('off') if live.get('off') is not None else nation.get('offensive_wars_count', 0) or 0)
        defensive_current = int(live.get('def') if live.get('def') is not None else nation.get('defensive_wars_count', 0) or 0)
        offensive_max = self._max_offensive_slots(nation)
        defensive_max = 3
        return {
            'offensive_current': max(0, offensive_current),
            'offensive_max': offensive_max,
            'offensive_open': max(0, offensive_max - offensive_current),
            'defensive_current': max(0, defensive_current),
            'defensive_max': defensive_max,
            'defensive_open': max(0, defensive_max - defensive_current),
        }

    def _attach_slot_state(
        self,
        nation: Dict[str, Any],
        active_war_counts: Optional[Dict[int, Dict[str, int]]] = None,
    ) -> Dict[str, Any]:
        state = self._slot_state(nation, active_war_counts)
        nation['active_war_counts'] = {
            'off': state['offensive_current'],
            'def': state['defensive_current'],
        }
        nation['offensive_slots_current'] = state['offensive_current']
        nation['offensive_slots_max'] = state['offensive_max']
        nation['offensive_slots_open'] = state['offensive_open']
        nation['defensive_slots_current'] = state['defensive_current']
        nation['defensive_slots_max'] = state['defensive_max']
        nation['defensive_slots_open'] = state['defensive_open']
        return nation

    def _weighted_unit_power(self, nation: Dict[str, Any]) -> float:
        """Shared weighted unit power for optimizer ranking and web explanations."""
        return (
            (nation.get('soldiers', 0) or 0) * 0.01 +
            (nation.get('tanks', 0) or 0) * 0.6 +
            (nation.get('aircraft', 0) or 0) * 18 +
            (nation.get('ships', 0) or 0) * 45
        )

    def _visible_unit_total(self, nation: Dict[str, Any]) -> int:
        return sum(int(nation.get(k, 0) or 0) for k in (
            'soldiers', 'tanks', 'aircraft', 'ships', 'spies', 'missiles', 'nukes'
        ))

    def _solo_power_margin(self, attacker_power: float, target_power: float) -> bool:
        """A near-even unit matchup should get backup when target slots allow it."""
        if target_power <= 0:
            return True
        return attacker_power >= target_power * 1.15

    def _recommended_attacker_count(
        self,
        sorted_attackers: List[Dict[str, Any]],
        target_nation: Dict[str, Any],
        max_attackers: int,
    ) -> int:
        """Use as many attackers as needed, without leaving a weaker nation alone."""
        max_attackers = max(0, min(int(max_attackers or 0), 3))
        if max_attackers <= 0 or not sorted_attackers:
            return 0
        if self._visible_unit_total(target_nation) <= 0:
            return 1

        target_power = self._weighted_unit_power(target_nation)
        if target_power <= 0:
            return 1

        first_power = self._weighted_unit_power(sorted_attackers[0])
        if first_power >= target_power and self._solo_power_margin(first_power, target_power):
            return 1
        if max_attackers <= 1 or len(sorted_attackers) <= 1:
            return 1 if first_power >= target_power else 0

        combined_power = first_power
        usable = min(max_attackers, len(sorted_attackers))
        for count in range(2, usable + 1):
            combined_power += self._weighted_unit_power(sorted_attackers[count - 1])
            if combined_power >= target_power * 1.15:
                return count
        return 0

    def _daily_unit_power(self, nation: Dict[str, Any]) -> float:
        limits = self.calculate_military_purchase_limits(nation)
        return (
            limits.get('soldiers_daily', 0) * 0.01 +
            limits.get('tanks_daily', 0) * 0.6 +
            limits.get('aircraft_daily', 0) * 18 +
            limits.get('ships_daily', 0) * 45
        )

    def _combat_simulation_analysis(self, attacker: Dict[str, Any], defender: Dict[str, Any]) -> Dict[str, Any]:
        """Ground war simulation used as a hard viability gate for destroy targeting."""
        try:
            attacker_units = (
                (attacker.get('soldiers', 0) or 0) +
                (attacker.get('tanks', 0) or 0) +
                (attacker.get('aircraft', 0) or 0) +
                (attacker.get('ships', 0) or 0)
            )
            defender_units = (
                (defender.get('soldiers', 0) or 0) +
                (defender.get('tanks', 0) or 0) +
                (defender.get('aircraft', 0) or 0) +
                (defender.get('ships', 0) or 0)
            )
            attacker_ground = (attacker.get('soldiers', 0) or 0) + (attacker.get('tanks', 0) or 0)

            base = {
                'can_win': False,
                'victory_type': 0,
                'combat_score': 0,
                'loot': 0,
                'infra_damage': 0,
                'resistance_loss': 0,
                'attacker_soldier_casualties': 0,
                'attacker_tank_casualties': 0,
                'defender_soldier_casualties': 0,
                'defender_tank_casualties': 0,
                'reason': '',
            }

            if attacker_units <= 0:
                base['reason'] = 'No military units'
                return base
            if attacker_ground <= 0:
                base['reason'] = 'No soldiers or tanks for ground victory'
                return base
            if defender_units <= 0:
                base.update({
                    'can_win': True,
                    'victory_type': 3,
                    'combat_score': 300,
                    'reason': 'Defender has no military units',
                })
                return base

            battle_result = self._simulate_ground_battle_outcome(attacker, defender)
            casualties = battle_result.get('casualties', {}) or {}
            can_win = bool(battle_result.get('can_win')) and int(battle_result.get('victory_type', 0) or 0) > 0

            victory_type = int(battle_result.get('victory_type', 0) or 0)
            base_score = victory_type * 100
            loot = float(battle_result.get('loot', 0) or 0)
            infra_damage = float(battle_result.get('infra_damage', 0) or 0)
            loot_bonus = min(loot / 1000, 50)
            infra_bonus = min(infra_damage / 10, 30)
            att_soldier_loss = float(casualties.get('attacker_soldier_casualties', 0) or 0)
            att_tank_loss = float(casualties.get('attacker_tank_casualties', 0) or 0)
            casualty_penalty = (att_soldier_loss * 0.1) + (att_tank_loss * 5)
            combat_score = max(0, base_score + loot_bonus + infra_bonus - casualty_penalty) if can_win else 0

            return {
                'can_win': can_win,
                'victory_type': victory_type,
                'combat_score': round(float(combat_score), 2),
                'loot': round(float(loot), 2),
                'infra_damage': round(float(infra_damage), 2),
                'resistance_loss': round(float(battle_result.get('resistance_loss', 0) or 0), 2),
                'attacker_soldier_casualties': round(att_soldier_loss, 2),
                'attacker_tank_casualties': round(att_tank_loss, 2),
                'defender_soldier_casualties': round(float(casualties.get('defender_soldier_casualties', 0) or 0), 2),
                'defender_tank_casualties': round(float(casualties.get('defender_tank_casualties', 0) or 0), 2),
                'reason': 'Can win simulated ground attack' if can_win else 'Ground sim cannot win',
            }
        except Exception as e:
            self._log_error("Error calculating combat simulation analysis", e)
            return {
                'can_win': False,
                'victory_type': 0,
                'combat_score': 0,
                'loot': 0,
                'infra_damage': 0,
                'resistance_loss': 0,
                'attacker_soldier_casualties': 0,
                'attacker_tank_casualties': 0,
                'defender_soldier_casualties': 0,
                'defender_tank_casualties': 0,
                'reason': str(e),
            }

    def _attacker_rank_breakdown(self, attacker: Dict[str, Any], target_nation: Dict[str, Any]) -> Dict[str, float]:
        """Composite optimizer score and the parts that explain it."""
        try:
            sim = self._combat_simulation_analysis(attacker, target_nation)
            combat_score = sim.get('combat_score', 0)
            target_score = float(target_nation.get('score', 0) or 0)
            attacker_score = float(attacker.get('score', 0) or 0)
            if target_score > 0:
                score_fit = max(0.0, 1.0 - (abs(attacker_score - target_score) / max(target_score, 1.0))) * 160
            else:
                score_fit = 0

            target_power = self._weighted_unit_power(target_nation)
            attacker_power = self._weighted_unit_power(attacker)
            current_unit_score = min(260, (attacker_power / max(target_power, 1)) * 120)

            daily_power = self._daily_unit_power(attacker)
            daily_score = min(140, daily_power / 20)

            secs = attacker.get('last_active_seconds')
            if secs is None:
                secs = self._seconds_since_last_active(attacker)
            activity_score = max(0, 120 - ((secs or 0) / 3600) * 4) if secs is not None else 0

            warchest_score = max(0, attacker.get('warchest_level', self._warchest_level(attacker)) or 0) * 30
            slot_score = (attacker.get('offensive_slots_open', 0) or 0) * 35
            infra_penalty = max(0, (attacker.get('infra_average', 0) or 0) - 2000) / 10

            total = combat_score + score_fit + current_unit_score + daily_score + activity_score + warchest_score + slot_score - infra_penalty
            return {
                'combat_score': round(float(combat_score), 2),
                'score_fit': round(float(score_fit), 2),
                'current_unit_score': round(float(current_unit_score), 2),
                'daily_score': round(float(daily_score), 2),
                'activity_score': round(float(activity_score), 2),
                'warchest_score': round(float(warchest_score), 2),
                'slot_score': round(float(slot_score), 2),
                'infra_penalty': round(float(infra_penalty), 2),
                'attacker_unit_power': round(float(attacker_power), 2),
                'target_unit_power': round(float(target_power), 2),
                'daily_unit_power': round(float(daily_power), 2),
                'unit_power_ratio': round(float(attacker_power / max(target_power, 1)), 3),
                'sim_can_win': bool(sim.get('can_win')),
                'sim_victory_type': int(sim.get('victory_type', 0) or 0),
                'sim_resistance_loss': round(float(sim.get('resistance_loss', 0) or 0), 2),
                'sim_infra_damage': round(float(sim.get('infra_damage', 0) or 0), 2),
                'sim_loot': round(float(sim.get('loot', 0) or 0), 2),
                'sim_attacker_soldier_casualties': round(float(sim.get('attacker_soldier_casualties', 0) or 0), 2),
                'sim_attacker_tank_casualties': round(float(sim.get('attacker_tank_casualties', 0) or 0), 2),
                'sim_defender_soldier_casualties': round(float(sim.get('defender_soldier_casualties', 0) or 0), 2),
                'sim_defender_tank_casualties': round(float(sim.get('defender_tank_casualties', 0) or 0), 2),
                'sim_reason': sim.get('reason', ''),
                'total': round(float(total), 2),
            }
        except Exception as e:
            self._log_error("Error calculating attacker rank breakdown", e)
            return {
                'combat_score': 0,
                'score_fit': 0,
                'current_unit_score': 0,
                'daily_score': 0,
                'activity_score': 0,
                'warchest_score': 0,
                'slot_score': 0,
                'infra_penalty': 0,
                'attacker_unit_power': 0,
                'target_unit_power': 0,
                'daily_unit_power': 0,
                'unit_power_ratio': 0,
                'sim_can_win': False,
                'sim_victory_type': 0,
                'sim_resistance_loss': 0,
                'sim_infra_damage': 0,
                'sim_loot': 0,
                'sim_attacker_soldier_casualties': 0,
                'sim_attacker_tank_casualties': 0,
                'sim_defender_soldier_casualties': 0,
                'sim_defender_tank_casualties': 0,
                'sim_reason': str(e),
                'total': 0,
            }

    def _attacker_rank_score(self, attacker: Dict[str, Any], target_nation: Dict[str, Any]) -> float:
        """Composite optimizer score for a single attacker against one target."""
        return float(self._attacker_rank_breakdown(attacker, target_nation).get('total', 0) or 0)

    def _find_optimal_attackers_sync(
        self,
        alliance_nations: List[Dict[str, Any]],
        target_nation: Dict[str, Any],
        max_groups: int,
        exclude_unoptimal: bool,
        num_attackers: int = 3,
        active_war_counts: Optional[Dict[int, Dict[str, int]]] = None,
        weapon_costs: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """
        Synchronous worker for finding optimal attackers.
        Executes heavy filtering, sorting, and group finding logic.
        
        Args:
            alliance_nations: List of nations to search through
            target_nation: Target nation data
            max_groups: Maximum number of groups to return
            num_attackers: Number of attackers per group (1-3)
            exclude_unoptimal: Whether to exclude unoptimal nations
        """
        try:
            # Analyze optimal weapon for target
            weapon_analysis = self._analyze_weapon_optimal_for_target(target_nation, weapon_costs)
            optimal_weapon = weapon_analysis.get('optimal_weapon', 'ground')
            
            target_nation = self._attach_slot_state(target_nation, active_war_counts)
            target_defensive_open = int(target_nation.get('defensive_slots_open', 0) or 0)
            if target_defensive_open <= 0:
                return {
                    'optimal_groups': [],
                    'all_attackers': [],
                    'total_found': 0,
                    'target_slots_full': True,
                    'message': 'Target has no open defensive slots.',
                }

            max_attackers = max(1, min(int(num_attackers or 3), 3, target_defensive_open))
            eligible_members = []
            target_score = target_nation.get('score', 0) if target_nation else 0
            
            # 1. Filter by war range
            for nation in alliance_nations:
                if isinstance(nation, dict):
                    if target_nation:
                        member_score = nation.get('score', 0)
                        if self.validate_attack_range(member_score, target_score):
                            eligible_members.append(nation)
                    else:
                        eligible_members.append(nation)
            
            # 2. Filter members with military data, apply optional filters, and calculate stats
            members_with_military = []
            for member in eligible_members:
                if (member.get('soldiers') is not None and 
                    member.get('tanks') is not None and 
                    member.get('aircraft') is not None and 
                    member.get('ships') is not None and
                    member.get('score') is not None):
                    member = self._attach_slot_state(member, active_war_counts)
                    if int(member.get('offensive_slots_open', 0) or 0) <= 0:
                        continue
                    
                    secs = self._seconds_since_last_active(member)
                    member['last_active_seconds'] = secs if secs is not None else None
                    if secs is None or secs >= 7 * 24 * 3600:
                        continue
                    
                    # Exclude unoptimal: zero units or >2000 avg infra
                    soldiers = (member.get('soldiers', 0) or 0)
                    tanks = (member.get('tanks', 0) or 0)
                    aircraft = (member.get('aircraft', 0) or 0)
                    ships = (member.get('ships', 0) or 0)
                    if exclude_unoptimal and soldiers == 0 and tanks == 0 and aircraft == 0 and ships == 0:
                        continue
                    
                    # Filter by weapon capability if optimal weapon is missile/nuke
                    if optimal_weapon == 'missile':
                        if not (member.get('missiles', 0) > 0 or 
                                self.has_project(member, 'Missile Launch Pad')):
                            continue
                    elif optimal_weapon == 'nuke':
                        if not (member.get('nukes', 0) > 0 or 
                                self.has_project(member, 'Nuclear Research Facility')):
                            continue
                    
                    # Calculate infrastructure average
                    cities = member.get('cities', [])
                    if cities:
                        total_infra = sum((city.get('infrastructure', 0) or 0) for city in cities if isinstance(city, dict))
                        member['infra_average'] = total_infra / len(cities)
                    else:
                        member['infra_average'] = member.get('infrastructure', 0) or 0
                    
                    if exclude_unoptimal and member.get('infra_average', 0) > 2000:
                        continue
                    
                    # Compute total military units for sorting
                    member['total_units'] = (
                        soldiers + tanks + aircraft + ships
                    )
                    
                    # Compute warchest level for prioritization
                    member['warchest_level'] = self._warchest_level(member)
                    member['destroy_rank_details'] = self._attacker_rank_breakdown(member, target_nation)
                    if not member['destroy_rank_details'].get('sim_can_win'):
                        continue
                    member['destroy_rank_score'] = member['destroy_rank_details'].get('total', 0)
                    
                    members_with_military.append(member)
            
            # 3. Build all attackers in range, prioritized by the destroy optimizer score,
            # then activity, warchest, and current units.
            def _sort_key(x: Dict[str, Any]):
                secs = x.get('last_active_seconds')
                if secs is None:
                    secs = float('inf')
                wl = x.get('warchest_level', 0)
                units = x.get('total_units', 0)
                rank = x.get('destroy_rank_score', 0)
                return (-rank, secs, -wl, -units)
            all_attackers_sorted = sorted(members_with_military, key=_sort_key)
            num_attackers = self._recommended_attacker_count(all_attackers_sorted, target_nation, max_attackers)
            if num_attackers <= 0:
                return {
                    'optimal_groups': [],
                    'all_attackers': [],
                    'total_found': len(all_attackers_sorted),
                    'effective_num_attackers': 0,
                    'message': 'No safe attacker set found for target unit power.',
                }
            
            # 4. Create optimal groups using efficient approach when enough members exist
            optimal_groups = []
            if len(members_with_military) >= num_attackers:
                used_nations = set()
                
                # Sort by the same single-attacker optimizer score used for the flat list.
                members_for_groups = sorted(
                    members_with_military,
                    key=lambda x: (-x.get('destroy_rank_score', 0), x.get('infra_average', 0))
                )
                
                for i, nation in enumerate(members_for_groups):
                    nation_id = nation.get('nation_id') or nation.get('id')
                    if nation_id in used_nations:
                        continue
                    
                    # Find compatible nations for a party
                    party = [nation]
                    used_nations.add(nation_id)
                    
                    # Look for compatible nations (within war range and good unit coverage)
                    for potential_nation in members_for_groups[i+1:]:
                        potential_id = potential_nation.get('nation_id') or potential_nation.get('id')
                        if potential_id in used_nations or len(party) >= num_attackers:
                            continue
                        
                        # Check if this nation is compatible with all current party members
                        is_compatible = True
                        for party_member in party:
                            if not self._check_war_range_compatibility(party_member, potential_nation):
                                is_compatible = False
                                break
                        
                        if is_compatible and len(party) < num_attackers:
                            party.append(potential_nation)
                            used_nations.add(potential_id)
                    
                    # Only keep parties of exactly num_attackers
                    if len(party) == num_attackers:
                        # Analyze the party
                        group_analysis = self._analyze_party(party, target_nation)
                        if group_analysis.get('is_valid'):
                            optimal_groups.append({
                                'attackers': party,
                                'score': group_analysis['score'],
                                'analysis': group_analysis
                            })
                    
                    # Stop if we have enough groups
                    if len(optimal_groups) >= max_groups:
                        break
                
                # Sort groups by score (highest first)
                optimal_groups.sort(key=lambda x: x['score'], reverse=True)
            
            return {
                'optimal_groups': optimal_groups,
                'all_attackers': all_attackers_sorted,
                'total_found': len(all_attackers_sorted),
                'effective_num_attackers': num_attackers,
                'target_slot_state': {
                    'defensive_open': target_nation.get('defensive_slots_open', 0),
                    'defensive_current': target_nation.get('defensive_slots_current', target_nation.get('defensive_wars_count', 0)),
                    'defensive_max': 3,
                }
            }
        except Exception as e:
            self._log_error(f"Error in _find_optimal_attackers_sync: {str(e)}", e, "_find_optimal_attackers_sync")
            return {'error': f'Error processing attackers: {str(e)}'}

    async def find_optimal_attackers(
        self,
        target_nation: Optional[Dict[str, Any]] = None,
        max_groups: int = 10,
        attackers_alliance_ids: Optional[List[str]] = None,
        num_attackers: int = 3,
        exclude_unoptimal: bool = False,
    ) -> Dict[str, Any]:
        """
        Find optimal alliance members for war targeting from multiple alliances.
        
        Args:
            target_nation: Target nation data to check war range against
            max_groups: Maximum number of optimal groups to return
            attackers_alliance_ids: List of alliance IDs to search through
            num_attackers: Number of attackers per group (1-3)
            exclude_unoptimal: Whether to exclude unoptimal nations
            
        Returns:
            Dictionary containing optimal attacker groups, and a sorted list of all attackers in range
        """
        try:
            if target_nation is None:
                return {'error': 'Target nation data is missing.'}
            
            # If no alliance IDs provided, return error
            if not attackers_alliance_ids:
                return {'error': 'No attacker alliances specified.'}
            
            all_nations = []
            
            # Fetch data from all specified alliances
            for alliance_id in attackers_alliance_ids:
                try:
                    aid = str(alliance_id)
                    self.logger.info(f"Fetching nations for alliance ID: {aid}")
                    alliance_nations = await self.get_alliance_nations(aid, force_refresh=False)
                    
                    if alliance_nations and isinstance(alliance_nations, list):
                        all_nations.extend(alliance_nations)
                        self.logger.info(f"Fetched {len(alliance_nations)} nations from alliance {aid}")
                    else:
                        self.logger.warning(f"No nations found for alliance: {aid}")
                except Exception as e:
                    self.logger.warning(f"Error fetching alliance data for {aid}: {e}")
                    continue
            
            active_war_counts = {}
            try:
                from PnWHarvester.db.global_wars_db import GlobalWarsDB
                from Systems.Functions.db_paths import GLOBAL_WARS_DB_STR
                wars_db = GlobalWarsDB(GLOBAL_WARS_DB_STR)
                active_war_counts = await wars_db.get_active_war_counts()
            except Exception as e:
                self.logger.warning(f"Could not load active war counts for destroy optimizer: {e}")

            # Offload heavy processing to thread
            return await asyncio.to_thread(
                self._find_optimal_attackers_sync,
                all_nations,
                target_nation,
                max_groups,
                exclude_unoptimal,
                num_attackers,
                active_war_counts,
                await self._get_live_weapon_costs(),
            )
            
        except Exception as e:
            self._log_error(f"Error finding optimal attackers: {str(e)}", e, "find_optimal_attackers")
            return {'error': f'Error finding optimal attackers: {str(e)}'}

    async def get_alliance_nations(self, alliance_id: str, force_refresh: bool = False) -> Optional[List[Dict[str, Any]]]:
        """Get all nations from an alliance."""
        try:
            try:
                from PnWHarvester.db.global_nations_db import GlobalNationsDB
                from Systems.Functions.db_paths import GLOBAL_NATIONS_DB
                db = GlobalNationsDB(str(GLOBAL_NATIONS_DB))
                nations = await db.get_nations_by_alliance(int(alliance_id))
                if nations:
                    for nation in nations:
                        nid = nation.get('id')
                        if nid:
                            nation['cities'] = await db.get_cities_for_nation(int(nid))
                    return nations
            except Exception as db_err:
                self.logger.warning(f"GlobalNations.db alliance load failed for {alliance_id}: {db_err}")

            if not self.query_instance:
                self.logger.error("No query instance available")
                return None
            
            nations = await self.query_instance.get_alliance_nations(alliance_id, force_refresh=force_refresh)
            return nations
        except Exception as e:
            self._log_error(f"Error getting alliance nations: {e}", e, "get_alliance_nations")
            return None

    async def fetch_target_nation(self, target_data: str, input_type: str) -> Optional[Dict[str, Any]]:
        """Fetch target nation based on input type.

        Tries GlobalNations.db first (fast, no API quota) and falls back to the
        live API only when the local DB has no match.
        """
        try:
            # ── 1. Try GlobalNations.db first ─────────────────────────────────
            try:
                from PnWHarvester.db.global_nations_db import GlobalNationsDB
                from Systems.Functions.db_paths import GLOBAL_NATIONS_DB
                from Systems.Functions.nation_emoji_store import strip_emoji_prefix

                db = GlobalNationsDB(str(GLOBAL_NATIONS_DB))
                nation: Optional[Dict[str, Any]] = None

                clean = strip_emoji_prefix(target_data).strip()

                if input_type == 'nation_id':
                    nation = await db.get_nation(int(clean))
                elif input_type == 'nation_name':
                    nation = await db.get_nation_by_name(clean)
                    # Also try leader name if nation_name lookup misses
                    if not nation and hasattr(db, 'get_nation_by_leader_name'):
                        nation = await db.get_nation_by_leader_name(clean)

                if nation:
                    # Attach cities so downstream callers have full data
                    nation['cities'] = await db.get_cities_for_nation(int(nation['id']))
                    self.logger.info(
                        f"fetch_target_nation: resolved '{target_data}' from GlobalNations.db "
                        f"(id={nation.get('id')})"
                    )
                    return nation
            except Exception as db_err:
                self.logger.warning(f"fetch_target_nation: GlobalNations.db lookup failed, falling back to API: {db_err}")

            # ── 2. Fall back to live API ───────────────────────────────────────
            if not self.query_instance:
                self.logger.error("No query instance available")
                return None

            nation = None
            if input_type == 'nation_id':
                nation = await self.query_instance.get_nation_by_id(target_data)
            elif input_type == 'nation_name':
                nation = await self.query_instance.get_nation_by_name(target_data)
            elif input_type == 'leader_name':
                nation = await self.query_instance.get_nation_by_leader(target_data)

            return nation
        except Exception as e:
            self._log_error(f"Error fetching target nation: {e}", e, "fetch_target_nation")
            return None

    @app_commands.command(name='destroy', description='Find optimal attackers for a target nation with analysis')
    @app_commands.describe(
        target='Enter Nation Name, Leader Name, or Nation Link/ID',
        attackers='Enter Alliance Name(s) or ID(s), comma-separated for multiple (defaults to Darkstar)',
        num_attackers='Number of attackers to find (1-3)',
        exclude_unoptimal='Exclude nations with >2000 avg infra or zero units'
    )
    @app_commands.choices(
        num_attackers=[
            app_commands.Choice(name="1", value=1),
            app_commands.Choice(name="2", value=2),
            app_commands.Choice(name="3", value=3),
        ]
    )
    @app_commands.autocomplete(target=_destroy_target_autocomplete, attackers=_destroy_attackers_autocomplete)
    async def destroy(
        self,
        interaction: discord.Interaction,
        target: str,
        attackers: Optional[str] = "10259",
        num_attackers: int = 3,
        exclude_unoptimal: bool = False,
    ) -> None:
        """
        Find optimal attackers for a target nation with comprehensive analysis.
        
        Args:
            interaction: Discord interaction
            target: Target nation name, leader name, or nation link/ID
            attackers: Comma-separated alliance names/IDs (optional)
            num_attackers: Number of attackers to find (1-3)
            exclude_unoptimal: Whether to exclude unoptimal nations
        """
        try:
            # Defer the interaction to prevent timeout
            await interaction.response.defer()

            if not target or not target.strip():
                await interaction.followup.send("❌ **Missing Target Info**\nPlease provide a valid value for 'Target Info'.")
                return

            # Parse Target string into input_type
            target_data = None
            input_type = None
            display_name = None
            raw = target.strip()

            # Strip any emoji prefix that autocomplete may have prepended
            try:
                from Systems.Functions.nation_emoji_store import strip_emoji_prefix
                raw = strip_emoji_prefix(raw).strip()
            except Exception:
                pass

            nid = self._extract_nation_id_from_link(raw)
            if nid:
                target_data = nid
                input_type = 'nation_id'
                display_name = f"Nation ID: {nid}"
            elif raw.isdigit():
                target_data = raw
                input_type = 'nation_id'
                display_name = f"Nation ID: {target_data}"
            else:
                target_data = raw
                input_type = 'nation_name'
                display_name = f"Nation: {target_data}"

            # Send initial loading message
            loading_message: Optional[discord.Message] = await interaction.followup.send(f"🔍 **Searching for Target...**\nLooking up: **{display_name}**")
            
            # Parse attackers parameter - support comma-separated list
            attackers_ids = []
            attackers_identifiers = []
            if attackers and attackers.strip():
                # Strip any emoji prefix that autocomplete may have prepended
                try:
                    from Systems.Functions.nation_emoji_store import strip_emoji_prefix
                    attackers = strip_emoji_prefix(attackers)
                except Exception:
                    pass

                # Split by comma and strip whitespace
                identifiers = [a.strip() for a in attackers.split(',') if a.strip()]
                if identifiers:
                    attackers_identifiers = identifiers
                    self.logger.info(f"Resolving {len(identifiers)} attacker alliances: {identifiers}")

                    # Load GlobalNations.db once for fast alliance ID lookups
                    _global_db = None
                    try:
                        from PnWHarvester.db.global_nations_db import GlobalNationsDB
                        from Systems.Functions.db_paths import GLOBAL_NATIONS_DB
                        _global_db = GlobalNationsDB(str(GLOBAL_NATIONS_DB))
                    except Exception as _db_init_err:
                        self.logger.warning(f"Could not open GlobalNations.db for alliance resolution: {_db_init_err}")

                    # Resolve each alliance identifier
                    for identifier in identifiers:
                        try:
                            resolved_id: Optional[str] = None

                            # ── Try GlobalNations.db first ────────────────────
                            if _global_db is not None:
                                try:
                                    if identifier.isdigit():
                                        # Numeric ID — verify it exists in the DB
                                        rows = await _global_db.get_nations_by_alliance(int(identifier))
                                        if rows:
                                            resolved_id = identifier
                                    else:
                                        # Name search via get_distinct_alliances
                                        matches = await _global_db.get_distinct_alliances(identifier)
                                        if matches:
                                            # Pick the closest match (first result is highest member count)
                                            resolved_id = str(matches[0]['alliance_id'])
                                            self.logger.info(
                                                f"Resolved alliance '{identifier}' → "
                                                f"'{matches[0].get('alliance_name')}' (id={resolved_id}) via GlobalNations.db"
                                            )
                                except Exception as _db_lookup_err:
                                    self.logger.warning(f"GlobalNations.db alliance lookup failed for '{identifier}': {_db_lookup_err}")

                            # ── Fall back to live API if DB missed ────────────
                            if not resolved_id:
                                if not self.query_instance:
                                    self.query_instance = create_v3_query_instance()
                                alliance_item = await self.query_instance.resolve_alliance(identifier)
                                if alliance_item and alliance_item.get('id'):
                                    resolved_id = str(alliance_item['id'])
                                    self.logger.info(f"Resolved alliance '{identifier}' to ID {resolved_id} via API")

                            if resolved_id and resolved_id not in attackers_ids:
                                attackers_ids.append(resolved_id)
                            else:
                                self.logger.warning(f"Could not resolve alliance: {identifier}")
                        except Exception as e:
                            self.logger.warning(f"Failed to resolve alliance '{identifier}': {e}")
            
            # If no valid alliances resolved, return error
            if not attackers_ids:
                if loading_message:
                    await loading_message.edit(content="❌ **No Valid Alliances**\nCould not resolve any of the provided alliance names/IDs.\n\nPlease provide at least one valid alliance name or ID.")
                return None
            
            # Fetch target nation data
            target_nation = await self.fetch_target_nation(target_data, input_type)
            
            if not target_nation:
                message = f"❌ **Target Not Found**\nCould not find nation: **{display_name}**\n\n"
                message += "**Try:**\n"
                message += "- Check the spelling of the nation name\n"
                message += "- Check the spelling of the leader name\n"
                message += "- Verify the nation link or ID is correct\n"
                message += "- Check if the nation exists"
                if loading_message:
                    await loading_message.edit(content=message)
                return None
            
            # Fetch Discord username for target nation
            try:
                if self.query_instance:
                    await self.query_instance._fetch_discord_usernames([target_nation], self.bot)
            except Exception as e:
                self.logger.warning(f"Failed to fetch Discord username for target: {e}")
            
            # Analyze weapon optimal for target using the same live costs/formulas as /weapon_eff.
            weapon_costs = await self._get_live_weapon_costs()
            weapon_analysis = self._analyze_weapon_optimal_for_target(target_nation, weapon_costs)
            optimal_weapon = weapon_analysis.get('optimal_weapon', 'ground')
            
            # Update loading message with weapon analysis
            if loading_message:
                alliance_count = len(attackers_ids)
                weapon_emoji = '🚀' if optimal_weapon == 'missile' else '☢️' if optimal_weapon == 'nuke' else '⚔️'
                await loading_message.edit(
                    content=f"⚔️ **Finding Optimal Attackers...**\n"
                    f"Target: **{target_nation.get('nation_name', 'Unknown')}**\n"
                    f"Optimal Weapon: {weapon_emoji} {optimal_weapon.title()}\n"
                    f"Searching across {alliance_count} alliance{'s' if alliance_count != 1 else ''}..."
                )
            
            # Find optimal attackers for specified alliances with optional exclusion
            optimal_attackers = await self.find_optimal_attackers(
                target_nation,
                max_groups=10,
                attackers_alliance_ids=attackers_ids,
                num_attackers=num_attackers,
                exclude_unoptimal=exclude_unoptimal,
            )
            
            if 'error' in optimal_attackers:
                if loading_message:
                    await loading_message.edit(content=f"❌ **Error Finding Attackers**\n{optimal_attackers['error']}")
                return
            
            # Build attacker list (all in-range attackers sorted, or fallback to groups)
            attackers_list = optimal_attackers.get('all_attackers') or []
            if not attackers_list:
                # Fallback to flatten groups if provided
                for group in optimal_attackers.get('optimal_groups', []):
                    if group and group.get('attackers'):
                        attackers_list.extend(group['attackers'])
            
            # Limit to the requested number of attackers
            effective_num_attackers = int(optimal_attackers.get('effective_num_attackers') or num_attackers or 3)
            if attackers_list and len(attackers_list) > effective_num_attackers:
                attackers_list = attackers_list[:effective_num_attackers]
            
            # If no attackers at all, inform user and stop
            if not attackers_list:
                message = "❌ **No Attackers Found In Range**\nCould not find any alliance members within war range for this target.\n\n"
                message += "**Possible Reasons:**\n"
                message += "- No one in range!\n"
                if loading_message:
                    await loading_message.edit(content=message)
                return
            
            # Fetch Discord usernames for attackers
            try:
                if self.query_instance:
                    await self.query_instance._fetch_discord_usernames(attackers_list, self.bot)
            except Exception as e:
                self.logger.warning(f"Failed to fetch Discord usernames for attackers: {e}")
            
            # Build attacker display without interactive buttons (warchest disabled by default)
            view = self.create_optimal_attackers_view(interaction, target_nation, optimal_attackers, show_warchest=False, weapon_analysis=weapon_analysis, num_attackers=num_attackers)
            
            if not view:
                if loading_message:
                    await loading_message.edit(content="❌ **Error Creating View**\nFailed to build the attacker display.")
                return None
            
            # Build the target summary
            target_message = view.create_target_message()
            
            # Delete the loading message
            try:
                if loading_message:
                    await loading_message.delete()
            except:
                pass
            
            # Send the target message first (no buttons) and suppress link previews
            try:
                await interaction.followup.send(target_message, suppress_embeds=True)
            except Exception:
                # If sending fails, try once more with embed suppression
                try:
                    await interaction.followup.send(target_message, suppress_embeds=True)
                except Exception:
                    # If it still fails, give up
                    return None
            
            # Send all attacker pages as plain messages (no buttons/pagination)
            if view.attacker_pages:
                for idx, page in enumerate(view.attacker_pages):
                    attacker_message = view.create_attacker_page_message(page, idx)
                    try:
                        await interaction.followup.send(attacker_message, suppress_embeds=True)
                    except Exception:
                        # If sending fails, try once more with embed suppression
                        try:
                            await interaction.followup.send(attacker_message, suppress_embeds=True)
                        except Exception:
                            # If it still fails, give up
                            return None
            else:
                # If no attacker pages, send a message indicating no attackers found
                await interaction.followup.send("❌ **No Attackers Found**\nCould not find any optimal attackers for this target.")
                return None
            
            self.logger.info(
                f"Destroy slash command completed successfully for target: {target_nation.get('nation_name', 'Unknown')} "
                f"by user {interaction.user.name}#{interaction.user.discriminator} "
                f"with {len(attackers_ids)} alliance(s)"
            )
            return None

        except Exception as e:
            self._log_error(f"Error in destroy slash command: {str(e)}", e, "destroy")
            error_message = "❌ **Command Error**\nAn unexpected error occurred while processing the destroy command.\n\n"
            error_message += f"**Error:** {str(e)}"
            
            try:
                await interaction.followup.send(error_message)
            except:
                # If followup fails, try to send a new message
                try:
                    if interaction.channel and isinstance(interaction.channel, (discord.TextChannel, discord.DMChannel, discord.GroupChannel, discord.Thread)):
                        await interaction.channel.send(error_message)
                except:
                    pass
            return None

    def create_optimal_attackers_view(self, interaction: discord.Interaction, target_nation: Dict[str, Any], optimal_attackers: Any, show_warchest: bool = False, weapon_analysis: Optional[Dict[str, Any]] = None, num_attackers: int = 3) -> Optional[Any]:
        """Create a view for displaying optimal attackers."""
        try:
            return OptimalAttackersView(interaction, target_nation, optimal_attackers, self, show_warchest, weapon_analysis, num_attackers)
        except Exception as e:
            self._log_error(f"Error creating optimal attackers view: {e}", e, "create_optimal_attackers_view")
            return None


class OptimalAttackersView:
    """Formatter for displaying target and attacker information as plain text messages."""
    
    def __init__(self, interaction: discord.Interaction, target_nation: Dict[str, Any], optimal_groups: List[Dict[str, Any]], cog: DestroyCog, show_warchest: bool = False, weapon_analysis: Optional[Dict[str, Any]] = None, num_attackers: int = 3):
        try:
            self.interaction = interaction
            self.target_nation = target_nation or {}
            self.cog = cog
            self.current_page = 0
            self.show_warchest = bool(show_warchest)
            self.weapon_analysis = weapon_analysis
            self.num_attackers = num_attackers
            
            # Build attacker list: handle both list inputs and dict result from find_optimal_attackers
            all_attackers = []
            if isinstance(optimal_groups, dict):
                # If a dict is passed (e.g., from find_optimal_attackers), extract attacker data
                if 'all_attackers' in optimal_groups:
                    all_attackers = optimal_groups.get('all_attackers') or []
                elif 'optimal_groups' in optimal_groups:
                    # Flatten groups
                    for group in optimal_groups.get('optimal_groups', []):
                        if group and group.get('attackers'):
                            all_attackers.extend(group['attackers'])
                else:
                    all_attackers = []
            else:
                # Original logic for list input
                if optimal_groups and isinstance(optimal_groups, list) and len(optimal_groups) > 0 and isinstance(optimal_groups[0], dict) and 'attackers' in optimal_groups[0]:
                    # Provided as groups; flatten attackers
                    for group in (optimal_groups or []):
                        if group and group.get('attackers'):
                            all_attackers.extend(group['attackers'])
                else:
                    # Provided directly as a list of attackers
                    all_attackers = optimal_groups or []
            
            # Limit to the requested number of attackers
            if all_attackers and len(all_attackers) > num_attackers:
                all_attackers = all_attackers[:num_attackers]
            
            # Ensure we have a list before sorting
            if not isinstance(all_attackers, list):
                all_attackers = []
            
            # Sort attackers by activity recency, warchest level, then total units
            def _sort_key(n: Dict[str, Any]):
                if not isinstance(n, dict):
                    return (float('inf'), 0, 0)
                # Activity: prefer most recent (fewest seconds since last active)
                secs = n.get('last_active_seconds')
                if secs is None and hasattr(self.cog, '_seconds_since_last_active'):
                    secs = self.cog._seconds_since_last_active(n)
                if secs is None:
                    secs = float('inf')
                # Warchest level: prefer higher
                wl = n.get('warchest_level')
                if wl is None and hasattr(self.cog, '_warchest_level'):
                    wl = self.cog._warchest_level(n)
                wl = wl or 0
                # Total units: prefer higher
                units = n.get('total_units')
                if units is None:
                    units = ((n.get('soldiers', 0) or 0) + (n.get('tanks', 0) or 0) + (n.get('aircraft', 0) or 0) + (n.get('ships', 0) or 0))
                return (secs, -wl, -units)
            all_attackers.sort(key=_sort_key)
            
            # Dynamically chunk attackers to fit Discord's 2000-char limit
            self.attacker_pages: List[Dict[str, Any]] = []
            DISCORD_LIMIT = 2000
            SAFETY_MARGIN = 25  # small buffer to avoid hitting hard limit
            current_chunk: List[Dict[str, Any]] = []
            current_length = 0

            for attacker in all_attackers:
                try:
                    block = self._format_attacker_block(attacker)
                except Exception:
                    block = ""
                if not block:
                    continue
                # Blocks include their own trailing newlines; no extra separator needed
                additional_len = len(block)
                if current_length + additional_len <= (DISCORD_LIMIT - SAFETY_MARGIN):
                    current_chunk.append(attacker)
                    current_length += additional_len
                else:
                    if current_chunk:
                        self.attacker_pages.append({
                            'attackers': current_chunk,
                            'page_num': len(self.attacker_pages) + 1
                        })
                    # Start a new chunk with the current attacker
                    current_chunk = [attacker]
                    current_length = len(block)

            # Append any remaining attackers
            if current_chunk:
                self.attacker_pages.append({
                    'attackers': current_chunk,
                    'page_num': len(self.attacker_pages) + 1
                })
            
        except Exception as e:
            if cog and hasattr(cog, '_log_error'):
                cog._log_error(f"Error initializing OptimalAttackersView: {e}", e, "OptimalAttackersView.__init__")
            else:
                logging.error(f"Error initializing OptimalAttackersView: {e}")
            self.interaction = interaction
            self.cog = cog
            self.target_nation = {}
            self.attacker_pages = []
            self.current_page = 0
            self.back_button = None
            self.main_button = None
            self.next_button = None
            self.show_warchest = bool(show_warchest)

    def create_target_message(self) -> str:
        """Create text message for target nation information with enhanced query data utilization."""
        try:
            if not self.target_nation:
                return "❌ **Error**\nNo target nation data available"
            
            safe_soldiers = self.target_nation.get('soldiers', 0) or 0
            safe_tanks = self.target_nation.get('tanks', 0) or 0
            safe_aircraft = self.target_nation.get('aircraft', 0) or 0
            safe_ships = self.target_nation.get('ships', 0) or 0
            safe_spies = self.target_nation.get('spies', 0) or 0
            nation_name = self.target_nation.get('nation_name', 'Unknown')
            num_cities = self.target_nation.get('num_cities', 0) or 0
            espionage_available = self.target_nation.get('espionage_available', False)
            cities = self.target_nation.get('cities', [])
            total_infra = 0
            if cities:
                total_infra = sum((city.get('infrastructure', 0) or 0) for city in cities if isinstance(city, dict))
            avg_infra_per_city = total_infra / num_cities if num_cities > 0 else 0
            
            # Calculate military purchase limits
            try:
                full_purchase_limits = {}
                if self.cog.calculator:
                    full_purchase_limits = self.cog.calculator.calculate_military_purchase_limits(self.target_nation)
            except Exception:
                full_purchase_limits = {
                    'soldiers_daily': 0, 'tanks_daily': 0, 'aircraft_daily': 0, 'ships_daily': 0,
                    'missiles': 0, 'nukes': 0,
                    'soldiers_max': 0, 'tanks_max': 0, 'aircraft_max': 0, 'ships_max': 0
                }
            
            # Get building ratios (MMR) - only include if valid
            mmr_string = None
            try:
                # Get calculator from AllianceManager cog
                alliance_cog = self.cog.bot.get_cog("AllianceManager")
                if alliance_cog and hasattr(alliance_cog, 'calc_system'):
                    building_ratios = alliance_cog.calc_system.calculate_building_ratios(self.target_nation)
                    if building_ratios and isinstance(building_ratios, dict):
                        mmr = building_ratios.get('mmr_string')
                        if mmr and mmr != '0/0/0/0' and mmr != '0.0/0.0/0.0/0.0':
                            mmr_string = mmr
            except Exception:
                pass
            
            projects_info = []
            has_missile_launch = self.cog.has_project(self.target_nation, 'Missile Launch Pad')
            has_space_program = self.cog.has_project(self.target_nation, 'Space Program')
            has_nuke_research = self.cog.has_project(self.target_nation, 'Nuclear Research Facility')
            has_nuke_launch = self.cog.has_project(self.target_nation, 'Nuclear Launch Facility')
            has_iron_dome = self.cog.has_project(self.target_nation, 'Iron Dome')
            has_vital_defense = self.cog.has_project(self.target_nation, 'Vital Defense System')

            # Format Dome and Vital Defense
            dome_status = mention('Approve') if has_iron_dome else mention('Deny')
            vital_status = mention('Approve') if has_vital_defense else mention('Deny')
            projects_info.append(f"{mention('dome')} Iron Dome {dome_status}")
            projects_info.append(f"{mention('vital')} Vital Defense System {vital_status}")

            # Format Missiles
            if has_missile_launch:
                missile_emojis = mention('missile') * 3 if has_space_program else mention('missile') * 2
                projects_info.append(missile_emojis)

            # Format Nukes
            if has_nuke_research:
                nuke_emojis = mention('bomb') * 2 if has_nuke_launch else mention('bomb')
                projects_info.append(nuke_emojis)            
            nation_id = self.target_nation.get('nation_id') or self.target_nation.get('id')
            nation_url = f"https://politicsandwar.com/nation/id={nation_id}" if nation_id else None
            header_name = f"[{nation_name}]({nation_url})" if nation_url else nation_name
            discord_username = self.target_nation.get('discord_username')
            discord_display_name = self.target_nation.get('discord_display_name')
            discord_text = None
            if discord_display_name and discord_username and discord_display_name != discord_username:
                discord_text = f"{discord_display_name} (@{discord_username})"
            elif discord_username:
                discord_text = f"@{discord_username}"
            elif discord_display_name:
                discord_text = f"{discord_display_name}"
            else:
                discord_text = None
            message = f"{header_name}" + (f" ({discord_text})" if discord_text else "") + "\n"
            message += f"**c{num_cities:,}** with **{avg_infra_per_city:,.0f}** Infra\n"
            message += f"Can Spy: {'✅' if espionage_available else '❌'}\n"
            message += f"Projects: {' '.join(projects_info) or 'None'}\n"
            message += f"**{SPY_EMOJI} Spies:** {safe_spies:,}\n"
            message += "**Units (Current/Max):**\n"
            message += (
                f"{SOLDIER_EMOJI}{safe_soldiers:,}/{full_purchase_limits.get('soldiers_max', 0):,}  "
                f"{TANK_EMOJI}{safe_tanks:,}/{full_purchase_limits.get('tanks_max', 0):,}  "
                f"{JET_EMOJI}{safe_aircraft:,}/{full_purchase_limits.get('aircraft_max', 0):,}  "
                f"{SHIP_EMOJI}{safe_ships:,}/{full_purchase_limits.get('ships_max', 0):,}\n"
            )
            message += "**Daily Purchase Limits**\n"
            message += (
                f"{SOLDIER_EMOJI}{full_purchase_limits.get('soldiers_daily', 0):,}/day  "
                f"{TANK_EMOJI}{full_purchase_limits.get('tanks_daily', 0):,}/day  "
                f"{JET_EMOJI}{full_purchase_limits.get('aircraft_daily', 0):,}/day  "
                f"{SHIP_EMOJI}{full_purchase_limits.get('ships_daily', 0):,}/day\n"
            )
            
            # Add weapon analysis if available
            weapon_analysis = getattr(self, 'weapon_analysis', None)
            if weapon_analysis:
                optimal_weapon = weapon_analysis.get('optimal_weapon', 'ground')
                weapon_emoji = '🚀' if optimal_weapon == 'missile' else '☢️' if optimal_weapon == 'nuke' else '⚔️'
                
                missile_eff = weapon_analysis.get('missile_analysis', {}).get('efficiency', 0)
                nuke_eff = weapon_analysis.get('nuke_analysis', {}).get('efficiency', 0)
                
                message += f"**Optimal Weapon:** {weapon_emoji} {optimal_weapon.title()}\n"
                if optimal_weapon == 'missile':
                    message += f"Missile Efficiency: {missile_eff:.2f}×\n"
                elif optimal_weapon == 'nuke':
                    message += f"Nuke Efficiency: {nuke_eff:.2f}×\n"
            
            return message
            
        except Exception as e:
            if self.cog and hasattr(self.cog, '_log_error'):
                self.cog._log_error(f"Error creating target message: {e}", e, "OptimalAttackersView.create_target_message")
            else:
                logging.error(f"Error creating target message: {e}")
            return "❌ **Error**\nFailed to create target message"
    
    def create_attacker_page_message(self, page_data: Dict[str, Any], page_index: int) -> str:
        """Create text message for an attacker page showing up to 3 attackers."""
        try:
            if not page_data or not page_data.get('attackers'):
                return "❌ **Error**\nNo attacker data available"
            
            attackers = page_data['attackers']
            # Assemble message from pre-formatted attacker blocks
            message_blocks = [self._format_attacker_block(a) for a in attackers if isinstance(a, dict)]
            return "".join(message_blocks)
            
        except Exception as e:
            if self.cog and hasattr(self.cog, '_log_error'):
                self.cog._log_error(f"Error creating attacker page: {e}", e, "OptimalAttackersView.create_attacker_page_message")
            else:
                logging.error(f"Error creating attacker page: {e}")
            return "❌ **Error**\nFailed to create attacker page"

    def _format_attacker_block(self, attacker: Dict[str, Any]) -> str:
        """Format a single attacker into a text block without Score, MMR, Specialty, Total Infra."""
        try:
            nation_name = attacker.get('nation_name', 'Unknown')
            leader_name = attacker.get('leader_name', 'Unknown')
            attacker_cities = attacker.get('cities', [])
            total_infra = 0
            if attacker_cities:
                total_infra = sum((city.get('infrastructure', 0) or 0) for city in attacker_cities if isinstance(city, dict))
            num_cities = len(attacker_cities) if attacker_cities else 0
            avg_infra_per_city = total_infra / num_cities if num_cities > 0 else 0
            soldiers = attacker.get('soldiers', 0) or 0
            tanks = attacker.get('tanks', 0) or 0
            aircraft = attacker.get('aircraft', 0) or 0
            ships = attacker.get('ships', 0) or 0
            has_missile_launch = self.cog.has_project(attacker, 'Missile Launch Pad')
            has_nuke_research = self.cog.has_project(attacker, 'Nuclear Research Facility')

            # Warchest status (gasoline + munitions only)
            gasoline = attacker.get('gasoline', 0) or 0
            munitions = attacker.get('munitions', 0) or 0
            min_resource = min([gasoline, munitions])
            if min_resource >= 10000:
                warchest_emoji, warchest_status = "🤑", "Stacked"
            elif min_resource >= 5000:
                warchest_emoji, warchest_status = "🌝", "Full"
            elif min_resource >= 3750:
                warchest_emoji, warchest_status = "🌖", "3/4"
            elif min_resource >= 2500:
                warchest_emoji, warchest_status = "🌗", "1/2"
            elif min_resource >= 1250:
                warchest_emoji, warchest_status = "🌘", "1/4"
            else:
                warchest_emoji, warchest_status = "🌚", "No"

            # Purchase limits
            try:
                full_purchase_limits = {}
                if self.cog.calculator:
                    full_purchase_limits = self.cog.calculator.calculate_military_purchase_limits(attacker)
            except Exception:
                full_purchase_limits = {
                    'soldiers_daily': 0, 'tanks_daily': 0, 'aircraft_daily': 0, 'ships_daily': 0,
                    'soldiers_max': 0, 'tanks_max': 0, 'aircraft_max': 0, 'ships_max': 0
                }

            # Header: Nation Name (masked link) with Discord in parentheses
            nation_id = attacker.get('nation_id') or attacker.get('id')
            nation_url = f"https://politicsandwar.com/nation/id={nation_id}" if nation_id else None
            header_name = f"[{nation_name}]({nation_url})" if nation_url else nation_name
            discord_username = attacker.get('discord_username')
            discord_display_name = attacker.get('discord_display_name')
            discord_text = None
            if discord_display_name and discord_username and discord_display_name != discord_username:
                discord_text = f"{discord_display_name} (@{discord_username})"
            elif discord_username:
                discord_text = f"@{discord_username}"
            elif discord_display_name:
                discord_text = f"{discord_display_name}"
            header_line = f"{header_name}" + (f" ({discord_text})" if discord_text else "")
            field_value = ""

            # Last login
            last_active = attacker.get('last_active', 0)
            if last_active:
                from datetime import datetime
                dt = None
                try:
                    if isinstance(last_active, (int, float)):
                        dt = datetime.fromtimestamp(last_active)
                    elif isinstance(last_active, str):
                        s = last_active.strip()
                        if s.isdigit():
                            dt = datetime.fromtimestamp(int(s))
                        else:
                            try:
                                dt = datetime.fromtimestamp(float(s))
                            except Exception:
                                try:
                                    dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
                                except Exception:
                                    dt = None
                except Exception:
                    dt = None
                if dt:
                    try:
                        now = datetime.utcnow() if dt.tzinfo is None else datetime.now(dt.tzinfo)
                        delta = now - dt
                        secs = max(0, int(delta.total_seconds()))
                        if secs < 60:
                            rel = "just now"
                        elif secs < 3600:
                            m = secs // 60
                            rel = f"{m}m ago"
                        elif secs < 86400:
                            h = secs // 3600
                            m = (secs % 3600) // 60
                            rel = f"{h}h {m}m ago"
                        else:
                            d = secs // 86400
                            h = (secs % 86400) // 3600
                            rel = f"{d}d {h}h ago"
                        field_value += f"**Last Login:** {rel}\n"
                    except Exception:
                        field_value += f"**Last Login:** unknown\n"

            # Required fields only (removed Score, MMR, Specialty, Total Infra)
            field_value += f"**Avg Infra/City:** {avg_infra_per_city:,.0f}\n"
            if self.show_warchest:
                field_value += f"**Has Warchest:** {warchest_emoji} ({warchest_status})\n"
            field_value += f"**Strategic:** {'🚀' if has_missile_launch else ''}{'☢️' if has_nuke_research else ''}\n"
            field_value += f"**Units (Current/Max):**\n"
            field_value += (
                f"{SOLDIER_EMOJI}{soldiers:,}/{full_purchase_limits.get('soldiers_max', 0):,}  "
                f"{TANK_EMOJI}{tanks:,}/{full_purchase_limits.get('tanks_max', 0):,}  "
                f"{JET_EMOJI}{aircraft:,}/{full_purchase_limits.get('aircraft_max', 0):,}  "
                f"{SHIP_EMOJI}{ships:,}/{full_purchase_limits.get('ships_max', 0):,}\n"
            )
            field_value += f"**Daily Purchase Limits**\n"
            field_value += (
                f"{SOLDIER_EMOJI}{full_purchase_limits.get('soldiers_daily', 0):,}/day  "
                f"{TANK_EMOJI}{full_purchase_limits.get('tanks_daily', 0):,}/day  "
                f"{JET_EMOJI}{full_purchase_limits.get('aircraft_daily', 0):,}/day  "
                f"{SHIP_EMOJI}{full_purchase_limits.get('ships_daily', 0):,}/day"
            )

            return f"{header_line}\n{field_value}\n\n"
        except Exception:
            return "👤 Unknown (Unknown)\n**Leader:** Unknown"
    
async def setup(bot):
    """
    Setup function to add the cog to the bot.
    
    Args:
        bot: Discord bot instance
    """
    try:
        await bot.add_cog(DestroyCog(bot))
        
        # Avoid duplicate registration of hybrid slash command
        cog = bot.get_cog("DestroyCog")
        if cog and hasattr(cog, 'destroy'):
            try:
                existing_cmd = bot.tree.get_command('destroy')
            except Exception:
                existing_cmd = None
            if existing_cmd is None:
                bot.tree.add_command(cog.destroy)
                logging.info("Destroy slash command added to tree")
            else:
                logging.info("Destroy slash command already registered; skipping manual add")
        
        logging.info("DestroyCog loaded successfully")
    except Exception as e:
        logging.error(f"Error loading DestroyCog: {e}")
        logging.error(traceback.format_exc())

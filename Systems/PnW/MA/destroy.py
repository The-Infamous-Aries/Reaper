import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
import re
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

AllianceManager = None

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
            mr = nation.get('military_research') or {}
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

            # Apply capacity bonuses to daily limits
            soldier_daily  += soldier_cap_bonus
            tank_daily     += tank_cap_bonus
            aircraft_daily += aircraft_cap_bonus
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

            soldier_max  += soldier_cap_bonus
            tank_max     += tank_cap_bonus
            aircraft_max += aircraft_cap_bonus
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
        """Analyze a party for unit coverage and calculate a score"""
        try:
            if len(party) != 3:
                return {'is_valid': False, 'error': 'Party must have exactly 3 members'}
            
            # Check unit coverage
            has_ground = False
            has_air = False
            has_navy = False
            has_missile_or_nuke = False
            
            # Target's military for comparison
            target_soldiers = target_nation.get('soldiers', 0) if target_nation else 0
            target_tanks = target_nation.get('tanks', 0) if target_nation else 0
            target_aircraft = target_nation.get('aircraft', 0) if target_nation else 0
            target_ships = target_nation.get('ships', 0) if target_nation else 0
            
            total_infra = 0
            total_military_score = 0
            unit_coverage_count = 0
            
            for member in party:
                # Get current military units
                soldiers = member.get('soldiers', 0)
                tanks = member.get('tanks', 0)
                aircraft = member.get('aircraft', 0)
                ships = member.get('ships', 0)
                
                # Check if this member has more units than target (good indicator)
                member_has_advantage = (
                    (soldiers + tanks * 10) > (target_soldiers + target_tanks * 10) or
                    aircraft > target_aircraft or
                    ships > target_ships
                )
                
                # Check unit types (including daily purchase capacity)
                try:
                    purchase_limits = self.calculate_military_purchase_limits(member)
                    soldiers += purchase_limits.get('soldiers_max', 0)
                    tanks += purchase_limits.get('tanks_max', 0)
                    aircraft += purchase_limits.get('aircraft_max', 0)
                    ships += purchase_limits.get('ships_max', 0)
                except:
                    pass

                if soldiers > 0 or tanks > 0:
                    has_ground = True
                if aircraft > 0:
                    has_air = True
                if ships > 0:
                    has_navy = True
                
                # Check missile/nuke capability
                if (member.get('missiles', 0) > 0 or 
                    member.get('nukes', 0) > 0 or
                    self.has_project(member, 'missile_pad') or
                    self.has_project(member, 'nuclear_facility')):
                    has_missile_or_nuke = True
                
                # Calculate infrastructure
                total_infra += member.get('infra_average', member.get('infrastructure', 0))
                
                # Calculate military score
                total_military_score += (
                    soldiers * 0.1 +
                    tanks * 5 +
                    aircraft * 50 +
                    ships * 100
                )
            
            # Count unit coverage types
            unit_coverage_count = sum([has_ground, has_air, has_navy])
            
            # Must have at least 2 unit types for basic coverage
            if unit_coverage_count < 2:
                return {'is_valid': False, 'error': 'Insufficient unit coverage'}
            
            # Calculate scores
            avg_infra = total_infra / 3
            
            # Infrastructure score (lower is better for attackers)
            infra_score = 1000 / (avg_infra + 1)
            
            # Military strength score
            military_score = total_military_score / 1000
            
            # Strategic bonus for missile/nuke capability
            strategic_bonus = 200 if has_missile_or_nuke else 0
            
            # Unit coverage bonus (more coverage = better)
            unit_coverage_bonus = unit_coverage_count * 50
            
            # Final score
            final_score = infra_score + military_score + unit_coverage_bonus + strategic_bonus
            
            return {
                'is_valid': True,
                'score': final_score,
                'total_infrastructure': total_infra,
                'avg_infrastructure': avg_infra,
                'total_military_score': total_military_score,
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

    def _find_optimal_attackers_sync(
        self,
        alliance_nations: List[Dict[str, Any]],
        target_nation: Dict[str, Any],
        max_groups: int,
        exclude_unoptimal: bool
    ) -> Dict[str, Any]:
        """
        Synchronous worker for finding optimal attackers.
        Executes heavy filtering, sorting, and group finding logic.
        """
        try:
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
                    
                    secs = self._seconds_since_last_active(member)
                    member['last_active_seconds'] = secs if secs is not None else None
                    if exclude_unoptimal and secs is not None and secs >= 7 * 24 * 3600:
                        continue
                    
                    # Exclude unoptimal: zero units or >2000 avg infra
                    soldiers = (member.get('soldiers', 0) or 0)
                    tanks = (member.get('tanks', 0) or 0)
                    aircraft = (member.get('aircraft', 0) or 0)
                    ships = (member.get('ships', 0) or 0)
                    if exclude_unoptimal and soldiers == 0 and tanks == 0 and aircraft == 0 and ships == 0:
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
                    
                    members_with_military.append(member)
            
            # 3. Build all attackers in range, prioritized by activity, warchest, then units
            def _sort_key(x: Dict[str, Any]):
                secs = x.get('last_active_seconds')
                if secs is None:
                    secs = float('inf')
                wl = x.get('warchest_level', 0)
                units = x.get('total_units', 0)
                return (secs, -wl, -units)
            all_attackers_sorted = sorted(members_with_military, key=_sort_key)
            
            # 4. Create optimal groups using efficient approach when enough members exist
            optimal_groups = []
            if len(members_with_military) >= 3:
                used_nations = set()
                
                # Sort by lowest infrastructure to try better coverage for groups
                members_for_groups = sorted(members_with_military, key=lambda x: x.get('infra_average', 0))
                
                for i, nation in enumerate(members_for_groups):
                    nation_id = nation.get('nation_id') or nation.get('id')
                    if nation_id in used_nations:
                        continue
                    
                    # Find 2 compatible nations for a party
                    party = [nation]
                    used_nations.add(nation_id)
                    
                    # Look for compatible nations (within war range and good unit coverage)
                    for potential_nation in members_for_groups[i+1:]:
                        potential_id = potential_nation.get('nation_id') or potential_nation.get('id')
                        if potential_id in used_nations or len(party) >= 3:
                            continue
                        
                        # Check if this nation is compatible with all current party members
                        is_compatible = True
                        for party_member in party:
                            if not self._check_war_range_compatibility(party_member, potential_nation):
                                is_compatible = False
                                break
                        
                        if is_compatible and len(party) < 3:
                            party.append(potential_nation)
                            used_nations.add(potential_id)
                    
                    # Only keep parties of exactly 3
                    if len(party) == 3:
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
                'total_found': len(all_attackers_sorted)
            }
        except Exception as e:
            self._log_error(f"Error in _find_optimal_attackers_sync: {str(e)}", e, "_find_optimal_attackers_sync")
            return {'error': f'Error processing attackers: {str(e)}'}

    async def find_optimal_attackers(
        self,
        target_nation: Optional[Dict[str, Any]] = None,
        max_groups: int = 10,
        attackers_alliance_ids: Optional[List[str]] = None,
        exclude_unoptimal: bool = False,
    ) -> Dict[str, Any]:
        """
        Find optimal alliance members for war targeting from multiple alliances.
        
        Args:
            target_nation: Target nation data to check war range against
            max_groups: Maximum number of optimal groups to return
            attackers_alliance_ids: List of alliance IDs to search through
            
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
            
            # Offload heavy processing to thread
            return await asyncio.to_thread(
                self._find_optimal_attackers_sync,
                all_nations,
                target_nation,
                max_groups,
                exclude_unoptimal
            )
            
        except Exception as e:
            self._log_error(f"Error finding optimal attackers: {str(e)}", e, "find_optimal_attackers")
            return {'error': f'Error finding optimal attackers: {str(e)}'}

    async def get_alliance_nations(self, alliance_id: str, force_refresh: bool = False) -> Optional[List[Dict[str, Any]]]:
        """Get all nations from an alliance."""
        try:
            if not self.query_instance:
                self.logger.error("No query instance available")
                return None
            
            nations = await self.query_instance.get_alliance_nations(alliance_id, force_refresh=force_refresh)
            return nations
        except Exception as e:
            self._log_error(f"Error getting alliance nations: {e}", e, "get_alliance_nations")
            return None

    async def fetch_target_nation(self, target_data: str, input_type: str) -> Optional[Dict[str, Any]]:
        """Fetch target nation based on input type."""
        try:
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
        attackers='Enter Alliance Name(s) or ID(s), comma-separated for multiple',
        exclude_unoptimal='Exclude nations with >2000 avg infra or zero units'
    )
    async def destroy(
        self,
        interaction: discord.Interaction,
        target: str,
        attackers: Optional[str] = None,
        exclude_unoptimal: bool = False,
    ) -> None:
        """
        Find optimal attackers for a target nation with comprehensive analysis.
        
        Args:
            interaction: Discord interaction
            target: Target nation name, leader name, or nation link/ID
            attackers: Comma-separated alliance names/IDs (optional)
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
                # Split by comma and strip whitespace
                identifiers = [a.strip() for a in attackers.split(',') if a.strip()]
                if identifiers:
                    attackers_identifiers = identifiers
                    self.logger.info(f"Resolving {len(identifiers)} attacker alliances: {identifiers}")
                    
                    # Resolve each alliance identifier
                    for identifier in identifiers:
                        try:
                            if not self.query_instance:
                                self.query_instance = create_v3_query_instance()
                            alliance_item = await self.query_instance.resolve_alliance(identifier)
                            if alliance_item and alliance_item.get('id'):
                                alliance_id = str(alliance_item['id'])
                                if alliance_id not in attackers_ids:
                                    attackers_ids.append(alliance_id)
                                    self.logger.info(f"Resolved alliance '{identifier}' to ID {alliance_id}")
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
            
            # Update loading message
            if loading_message:
                alliance_count = len(attackers_ids)
                await loading_message.edit(content=f"⚔️ **Finding Optimal Attackers...**\nTarget: **{target_nation.get('nation_name', 'Unknown')}**\nSearching across {alliance_count} alliance{'s' if alliance_count != 1 else ''}...")
            
            # Find optimal attackers for specified alliances with optional exclusion
            optimal_attackers = await self.find_optimal_attackers(
                target_nation,
                max_groups=10,
                attackers_alliance_ids=attackers_ids,
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
            view = self.create_optimal_attackers_view(interaction, target_nation, optimal_attackers, show_warchest=False)
            
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

    def create_optimal_attackers_view(self, interaction: discord.Interaction, target_nation: Dict[str, Any], optimal_attackers: Any, show_warchest: bool = False) -> Optional[Any]:
        """Create a view for displaying optimal attackers."""
        try:
            return OptimalAttackersView(interaction, target_nation, optimal_attackers, self, show_warchest)
        except Exception as e:
            self._log_error(f"Error creating optimal attackers view: {e}", e, "create_optimal_attackers_view")
            return None


class OptimalAttackersView:
    """Formatter for displaying target and attacker information as plain text messages."""
    
    def __init__(self, interaction: discord.Interaction, target_nation: Dict[str, Any], optimal_groups: List[Dict[str, Any]], cog: DestroyCog, show_warchest: bool = False):
        try:
            self.interaction = interaction
            self.target_nation = target_nation or {}
            self.cog = cog
            self.current_page = 0
            self.show_warchest = bool(show_warchest)
            
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
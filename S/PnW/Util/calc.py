import re
from typing import Dict, List, Any, Optional, Tuple, Union, Set, TypedDict, cast
from datetime import datetime, timezone, timedelta
import logging
import traceback
import sys
import os
import asyncio
from Systems.PnW.Util.query import PNWAPIQuery

class MilitaryStats(TypedDict):
    soldiers: int
    tanks: int
    aircraft: int
    ships: int
    missiles: int
    nukes: int

class ProductionCapacityStats(TypedDict):
    total_barracks: int
    total_factories: int
    total_hangars: int
    total_drydocks: int
    daily_soldiers: int
    daily_tanks: int
    daily_aircraft: int
    daily_ships: int
    daily_missiles: int
    daily_nukes: int
    max_soldiers: int
    max_tanks: int
    max_aircraft: int
    max_ships: int
    max_missiles: int
    max_nukes: int

class AllianceStats(TypedDict):
    total_nations: int
    total_score: float
    total_cities: int
    missile_capable: int
    nuclear_capable: int
    vital_defense_system: int
    iron_dome: int
    propaganda_bureau: int
    military_research_center: int
    space_program: int
    missile_launch_pad: int
    nuclear_research_facility: int
    nuclear_launch_facility: int
    total_military: MilitaryStats
    production_capacity: ProductionCapacityStats

class ImprovementsStats(TypedDict):
    coalpower: int
    oilpower: int
    nuclearpower: int
    windpower: int
    oilwell: int
    coalmine: int
    uramine: int
    ironmine: int
    bauxitemine: int
    leadmine: int
    farm: int
    gasrefinery: int
    steelmill: int
    aluminumrefinery: int
    munitionsfactory: int
    factory: int
    policestation: int
    hospital: int
    bank: int
    supermarket: int
    shopping_mall: int
    stadium: int
    subway: int
    recyclingcenter: int
    barracks: int
    hangar: int
    drydock: int
    total_power: float
    total_improvements: int
    total_cities: int
    avg_per_city: float
    active_nations: int

class NationImprovementsStats(TypedDict):
    total_power: int
    total_improvements: int
    num_cities: int
    avg_improvements_per_city: float
    coal_power: int
    oil_power: int
    nuclear_power: int
    wind_power: int
    coal_mine: int
    oil_well: int
    uranium_mine: int
    iron_mine: int
    bauxite_mine: int
    lead_mine: int
    farm: int
    steel_mill: int
    aluminum_refinery: int
    munitions_factory: int
    gasrefinery: int
    police_station: int
    hospital: int
    recycling_center: int
    subway: int
    supermarket: int
    bank: int
    shopping_mall: int
    stadium: int
    barracks: int
    factory: int
    hangar: int
    drydock: int


class BuildingRatios(TypedDict):
    barracks_ratio: float
    factories_ratio: float
    airforcebase_ratio: float
    drydock_ratio: float
    mmr_string: str


IMPROVEMENT_KEYS = [
    'coalpower', 'oilpower', 'nuclearpower', 'windpower',
    'oilwell', 'coalmine', 'uramine', 'ironmine', 'bauxitemine', 'leadmine', 'farm',
    'gasrefinery', 'steelmill', 'aluminumrefinery', 'munitionsfactory', 'factory',
    'policestation', 'hospital', 'bank', 'supermarket',
    'shopping_mall', 'stadium', 'subway', 'recyclingcenter',
    'barracks', 'hangar', 'drydock'
]

# Add parent directory to path for config import
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

class AllianceCalculator:
    def __init__(self, query_instance: Optional[PNWAPIQuery] = None):
        if query_instance is None:
            query_instance = PNWAPIQuery()
        self.query_system = query_instance
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG) # Explicitly set level for debugging
        self._debug_project_logging = False  # Disable verbose project logging by default

    def _log_message(self, message: str, level: int = logging.DEBUG, context: str = ""):
        if context:
            message = f"{context}: {message}"
        self.logger.log(level, message)

    def _log_error(self, error_msg: str, exception: Optional[Exception] = None, context: str = ""):
        full_msg = error_msg
        if context:
            full_msg = f"{context}: {error_msg}"

        if exception:
            self.logger.error(f"{full_msg} - {str(exception)}")
            self.logger.debug(f"Traceback: {traceback.format_exc()}")
        else:
            self.logger.error(full_msg)
    
    def _validate_input(self, data: Any, expected_type: type, field_name: str = "data") -> bool:
        if not isinstance(data, expected_type):
            self.logger.warning(f"Input validation failed: {field_name} expected {expected_type}, got {type(data)}")
            return False
        return True
    
    def _safe_get(self, data: dict, key: str, default: Any = None, expected_type: Optional[type] = None) -> Any:
        try:
            military_data: Dict[str, Any] = {}
            value = data.get(key, default)
            if expected_type and value is not None:
                if not isinstance(value, expected_type):
                    try:
                        value = expected_type(value)
                    except (ValueError, TypeError):
                        return default
            return value
        except (AttributeError, TypeError):
            return default
             
    def _calculate_improvements_data_sync(self, nations: List[Dict[str, Any]]) -> ImprovementsStats:
        """Synchronous implementation of improvement calculations."""
        try:
            # Filter only VM/APPLICANT, include 14+ inactive
            active_nations = [n for n in nations if (self._safe_get(n, 'vacation_mode_turns', 0, int) == 0 and self._safe_get(n, 'alliance_position', '', str).upper() != 'APPLICANT')]
            improvements: ImprovementsStats = {
                'coalpower': 0, 'oilpower': 0, 'nuclearpower': 0, 'windpower': 0,
                'oilwell': 0, 'coalmine': 0, 'uramine': 0, 'ironmine': 0, 'bauxitemine': 0, 'leadmine': 0, 'farm': 0,
                'gasrefinery': 0, 'steelmill': 0, 'aluminumrefinery': 0, 'munitionsfactory': 0, 'factory': 0,
                'policestation': 0, 'hospital': 0, 'bank': 0, 'supermarket': 0,
                'shopping_mall': 0, 'stadium': 0, 'subway': 0, 'recyclingcenter': 0,
                'barracks': 0, 'hangar': 0, 'drydock': 0,
                'total_power': 0.0,
                'total_improvements': 0,
                'total_cities': 0,
                'avg_per_city': 0.0,
                'active_nations': 0
             }         
            total_cities = 0
            for nation in active_nations:
                try:
                    cities = nation.get('cities', [])
                    if not cities:
                        continue                    
                    total_cities += len(cities)
                    for city in cities:
                        if not isinstance(city, dict):
                            continue
                        improvements['coalpower'] += self._safe_get(city, 'coal_power', 0, int)
                        improvements['oilpower'] += self._safe_get(city, 'oil_power', 0, int)
                        improvements['nuclearpower'] += self._safe_get(city, 'nuclear_power', 0, int)
                        improvements['windpower'] += self._safe_get(city, 'wind_power', 0, int)
                        improvements['oilwell'] += self._safe_get(city, 'oil_well', 0, int)
                        improvements['coalmine'] += self._safe_get(city, 'coal_mine', 0, int)
                        improvements['uramine'] += self._safe_get(city, 'uranium_mine', 0, int)
                        improvements['ironmine'] += self._safe_get(city, 'iron_mine', 0, int)
                        improvements['bauxitemine'] += self._safe_get(city, 'bauxite_mine', 0, int)
                        improvements['leadmine'] += self._safe_get(city, 'lead_mine', 0, int)
                        improvements['farm'] += self._safe_get(city, 'farm', 0, int)
                        improvements['gasrefinery'] += self._safe_get(city, 'gasrefinery', 0, int)
                        improvements['steelmill'] += self._safe_get(city, 'steel_mill', 0, int)
                        improvements['aluminumrefinery'] += self._safe_get(city, 'aluminum_refinery', 0, int)
                        improvements['munitionsfactory'] += self._safe_get(city, 'munitions_factory', 0, int)
                        improvements['factory'] += self._safe_get(city, 'factory', 0, int)
                        improvements['policestation'] += self._safe_get(city, 'police_station', 0, int)
                        improvements['hospital'] += self._safe_get(city, 'hospital', 0, int)
                        improvements['bank'] += self._safe_get(city, 'bank', 0, int)
                        improvements['supermarket'] += self._safe_get(city, 'supermarket', 0, int)
                        improvements['shopping_mall'] += self._safe_get(city, 'shopping_mall', 0, int)
                        improvements['stadium'] += self._safe_get(city, 'stadium', 0, int)
                        improvements['subway'] += self._safe_get(city, 'subway', 0, int)
                        improvements['recyclingcenter'] += self._safe_get(city, 'recycling_center', 0, int)
                        improvements['barracks'] += self._safe_get(city, 'barracks', 0, int)
                        improvements['hangar'] += self._safe_get(city, 'airforcebase', 0, int)
                        improvements['drydock'] += self._safe_get(city, 'drydock', 0, int)             
                except Exception as e:
                    self._log_error(f"Error processing improvements for nation: {e}", e, "_calculate_improvements_data_sync")
                    continue
            total_power = (improvements['coalpower'] + improvements['oilpower'] + 
                          improvements['nuclearpower'] + improvements['windpower'])           
            improvements['total_power'] = total_power
            improvements['total_improvements'] = sum(int(v) for v in improvements.values() if isinstance(v, int))
            improvements['total_cities'] = total_cities
            improvements['avg_per_city'] = improvements['total_improvements'] / improvements['total_cities'] if improvements['total_cities'] > 0 else 0.0
            improvements['active_nations'] = len(active_nations)
            self.logger.info(f"Improvements calculated: {improvements['barracks']} barracks, {improvements['factory']} factories, "
                           f"{improvements['hangar']} hangars, {improvements['drydock']} drydocks across {improvements['total_cities']} cities "
                           f"({improvements['active_nations']} active nations)")
            return improvements           
        except Exception as e:
            self._log_error(f"Error calculating improvements data: {e}", e, "_calculate_improvements_data_sync")
            return {
                 'coalpower': 0, 'oilpower': 0, 'nuclearpower': 0, 'windpower': 0,
                 'oilwell': 0, 'coalmine': 0, 'uramine': 0, 'ironmine': 0, 'bauxitemine': 0, 'leadmine': 0, 'farm': 0,
                'gasrefinery': 0, 'steelmill': 0, 'aluminumrefinery': 0, 'munitionsfactory': 0, 'factory': 0,
                'policestation': 0, 'hospital': 0, 'bank': 0, 'supermarket': 0, 'shopping_mall': 0, 'stadium': 0, 'subway': 0, 'recyclingcenter': 0,
                'barracks': 0, 'hangar': 0, 'drydock': 0,
                'total_power': 0.0, 'total_improvements': 0, 'total_cities': 0, 'avg_per_city': 0.0, 'active_nations': 0
            }

    async def calculate_improvements_data(self, nations: List[Dict[str, Any]]) -> ImprovementsStats:
        """Async wrapper for calculating improvements data."""
        return await asyncio.to_thread(self._calculate_improvements_data_sync, nations)

    async def calculate_improvements_data_multi_alliance(self, alliance_data: Dict[str, List[Dict[str, Any]]], selected_alliances: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Calculate comprehensive improvements data for multiple alliances efficiently.
        Uses thread offloading for heavy calculations.
        """
        try:
            if not alliance_data:
                self.logger.warning("calculate_improvements_data_multi_alliance: No alliance data provided")
                return {}
            
            # Determine which alliances to process
            alliances_to_process = selected_alliances if selected_alliances else list(alliance_data.keys())
            
            # Run calculations concurrently? 
            # Or just sequentially in a loop but inside this async function.
            # Since calculate_improvements_data offloads to thread, we can await them.
            
            # Initialize total improvements
            total_improvements: ImprovementsStats = {
                'coalpower': 0, 'oilpower': 0, 'nuclearpower': 0, 'windpower': 0,
                'oilwell': 0, 'coalmine': 0, 'uramine': 0, 'ironmine': 0, 'bauxitemine': 0, 'leadmine': 0, 'farm': 0,
                'gasrefinery': 0, 'steelmill': 0, 'aluminumrefinery': 0, 'munitionsfactory': 0, 'factory': 0,
                'policestation': 0, 'hospital': 0, 'bank': 0, 'supermarket': 0, 'shopping_mall': 0, 'stadium': 0, 'subway': 0, 'recyclingcenter': 0,
                'barracks': 0, 'hangar': 0, 'drydock': 0,
                'total_power': 0.0, 'total_improvements': 0, 'total_cities': 0, 'avg_per_city': 0.0, 'active_nations': 0
            }
            
            alliance_breakdown = {}
            total_nations_processed = 0
            
            # Process each alliance
            for alliance_key in alliances_to_process:
                nations = alliance_data.get(alliance_key, [])
                if not nations:
                    continue
                
                # Calculate improvements for this alliance (awaits the threaded calculation)
                alliance_improvements = await self.calculate_improvements_data(nations)
                alliance_breakdown[alliance_key] = alliance_improvements
                
                # Add to totals (excluding metadata fields)
                for improvement_key in IMPROVEMENT_KEYS:
                    if improvement_key in alliance_improvements:
                        total_improvements[improvement_key] += alliance_improvements[improvement_key] # type: ignore[literal-required]
                
                # Count active nations for this alliance
                total_nations_processed += alliance_improvements.get('active_nations', 0)
            
            # Recalculate totals and averages
            total_improvements['total_power'] = (total_improvements['coalpower'] + total_improvements['oilpower'] + 
                                               total_improvements['nuclearpower'] + total_improvements['windpower'])
            total_improvements['total_improvements'] = sum(total_improvements[key] for key in IMPROVEMENT_KEYS) # type: ignore[literal-required]
            total_improvements['avg_per_city'] = (total_improvements['total_improvements'] / total_improvements['total_cities'] 
                                                if total_improvements['total_cities'] > 0 else 0)
            total_improvements['active_nations'] = total_nations_processed
            
            result = {
                'total': total_improvements,
                'by_alliance': alliance_breakdown,
                'alliances_processed': len(alliances_to_process)
            }
            
            self.logger.info(f"calculate_improvements_data_multi_alliance: Processed {total_nations_processed} nations from {len(alliances_to_process)} alliances")
            return result
            
        except Exception as e:
            self._log_error("Error calculating multi-alliance improvements data", e, "calculate_improvements_data_multi_alliance")
            return {}

    async def calculate_alliance_statistics_multi_alliance(self, alliance_data: Dict[str, List[Dict[str, Any]]], selected_alliances: Optional[List[str]] = None) -> Dict[str, AllianceStats]:
        """
        Calculate comprehensive alliance statistics for multiple alliances efficiently.
        """
        try:
            if not alliance_data:
                self.logger.warning("calculate_alliance_statistics_multi_alliance: No alliance data provided")
                return {}

            results: Dict[str, AllianceStats] = {}
            alliances_to_process = selected_alliances if selected_alliances else list(alliance_data.keys())

            for alliance_id in alliances_to_process:
                nations_in_alliance = alliance_data.get(alliance_id)
                if nations_in_alliance:
                    # Calculate statistics for each alliance individually
                    alliance_stats = await self.calculate_alliance_statistics(nations_in_alliance)
                    results[alliance_id] = alliance_stats
                else:
                    self.logger.warning(f"calculate_alliance_statistics_multi_alliance: No nations found for alliance_id {alliance_id}")

            return results

        except Exception as e:
            self._log_error("Error calculating multi-alliance statistics", e, "calculate_alliance_statistics_multi_alliance")
            return {} # Return an empty dictionary on error

    def _combine_alliance_nations_for_calc_sync(self, alliance_data: Dict[str, List[Dict[str, Any]]], selected_alliances: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Efficiently combine nations from multiple alliances for calculations, removing duplicates.
        """
        try:
            combined_nations = []
            seen_nation_ids = set()
            
            # Determine which alliances to process
            alliances_to_process = selected_alliances if selected_alliances else list(alliance_data.keys())
            
            for alliance_key in alliances_to_process:
                nations = alliance_data.get(alliance_key, [])
                if not nations:
                    continue
                
                # Add nations, avoiding duplicates by nation_id
                for nation in nations:
                    nation_id = self._safe_get(nation, 'nation_id') or self._safe_get(nation, 'id')
                    if nation_id and nation_id not in seen_nation_ids:
                        seen_nation_ids.add(nation_id)
                        combined_nations.append(nation)
            
            self.logger.debug(f"_combine_alliance_nations_for_calc: Combined {len(combined_nations)} unique nations from {len(alliances_to_process)} alliances")
            return combined_nations
            
        except Exception as e:
            self._log_error("Error combining alliance nations for calculation", e, "_combine_alliance_nations_for_calc_sync")
            return []
    
    def has_project(self, nation: Dict[str, Any], project_name: str) -> bool:
        if not self._validate_input(nation, dict, "nation"):
            # self.logger.warning("has_project: Invalid nation input")
            return False    
        if not self._validate_input(project_name, str, "project_name"):
            # self.logger.warning("has_project: Invalid project_name input")
            return False       
        if not project_name.strip():
            # self.logger.warning("has_project: Empty project_name provided")
            return False        
        try:
            # self.logger.debug(f"has_project: Checking project '{project_name}'")
            project_field_mapping = {
                # Strategic Military Projects
                'Iron Dome': 'iron_dome',
                'Missile Launch Pad': 'missile_launch_pad',
                'Nuclear Research Facility': 'nuclear_research_facility',
                'Nuclear Launch Facility': 'nuclear_launch_facility',
                'Vital Defense System': 'vital_defense_system',
                'Propaganda Bureau': 'propaganda_bureau',
                'Military Research Center': 'military_research_center',
                'Space Program': 'space_program',
                'Activity Center': 'activity_center',
                'Advanced Engineering Corps': 'advanced_engineering_corps',
                'Advanced Pirate Economy': 'advanced_pirate_economy',
                'Arable Land Agency': 'arable_land_agency',
                'Arms Stockpile': 'arms_stockpile',
                'Bauxite Works': 'bauxite_works',
                'Bureau of Domestic Affairs': 'bureau_of_domestic_affairs',
                'Center Civil Engineering': 'center_for_civil_engineering',
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
            field_name = project_field_mapping.get(project_name)
            if field_name:
                project_value = self._safe_get(nation, field_name, False, bool)
                return project_value
            else:
                self.logger.warning(f"has_project: Unknown project name '{project_name}'")
                return False        
        except Exception as e:
            self._log_error(f"Unexpected error checking project '{project_name}'", e, "has_project")
            return False
    
    def _get_active_nations_sync(self, nations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self._validate_input(nations, list, "nations"):
            self.logger.warning("get_active_nations: Invalid nations input, returning empty list")
            return []        
        if not nations:
            self.logger.debug("get_active_nations: Empty nations list provided")
            return []        
        try:
            active_nations = []
            
            for i, nation in enumerate(nations):
                try:
                    if not isinstance(nation, dict):
                        continue
                    
                    # Exclude vacation mode and applicants
                    vacation_turns = self._safe_get(nation, 'vacation_mode_turns', 0, int)
                    if vacation_turns > 0:
                        continue
                    
                    alliance_position = self._safe_get(nation, 'alliance_position', '', str)
                    if alliance_position.upper() == 'APPLICANT':
                        continue
                    
                    active_nations.append(nation)
                except (AttributeError, TypeError) as e:
                    self._log_error(f"Error processing nation at index {i}", e, "_get_active_nations_sync")
                    continue           
            return active_nations            
        except Exception as e:
            self._log_error("Unexpected error in get_active_nations", e, "_get_active_nations_sync")
            return []
    
    async def get_active_nations(self, nations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Async wrapper for getting active nations."""
        return await asyncio.to_thread(self._get_active_nations_sync, nations)

    def analyze_nation_military(self, nation: Dict[str, Any]) -> Dict[str, Any]:
        """Analyzes a single nation's military and returns a structured dictionary."""
        self.logger.debug(f"Nation data received by analyze_nation_military: {nation}")
        if not self._validate_input(nation, dict, "nation"):
            return {}

        try:
            purchase_limits = self.calculate_military_purchase_limits(nation)
            daily_soldiers = purchase_limits.get('soldiers_daily', 0.0)
            daily_tanks = purchase_limits.get('tanks_daily', 0.0)
            daily_aircraft = purchase_limits.get('aircraft_daily', 0.0)
            daily_ships = purchase_limits.get('ships_daily', 0.0)
            daily_missiles = purchase_limits.get('missiles', 0.0)
            daily_nukes = purchase_limits.get('nukes', 0.0)
            soldiers = self._safe_get(nation, 'soldiers', 0, int)
            tanks = self._safe_get(nation, 'tanks', 0, int)
            aircraft = self._safe_get(nation, 'aircraft', 0, int)
            ships = self._safe_get(nation, 'ships', 0, int)
            missiles = self._safe_get(nation, 'missiles', 0, int)
            nukes = self._safe_get(nation, 'nukes', 0, int)
            can_missile = self.has_project(nation, 'Missile Launch Pad')
            can_nuke = self.has_project(nation, 'Nuclear Research Facility')
            num_cities = self._safe_get(nation, 'num_cities', 1, int)
            if num_cities == 0: 
                num_cities = 1 # Prevent division by zero
            avg_b = purchase_limits.get('total_barracks', 0) / num_cities
            avg_f = purchase_limits.get('total_factories', 0) / num_cities
            avg_h = purchase_limits.get('total_hangars', 0) / num_cities
            avg_d = purchase_limits.get('total_drydocks', 0) / num_cities

            analysis_string = f"{round(avg_b, 1):g}/{round(avg_f, 1):g}/{round(avg_h, 1):g}/{round(avg_d, 1):g}"

            military_data = {
                "daily_production": {
                    "soldiers": daily_soldiers,
                    "tanks": daily_tanks,
                    "aircraft": daily_aircraft,
                    "ships": daily_ships,
                    "missiles": daily_missiles,
                    "nukes": daily_nukes,
                },
                "current_units": {
                    "soldiers": soldiers,
                    "tanks": tanks,
                    "aircraft": aircraft,
                    "ships": ships,
                    "missiles": missiles,
                    "nukes": nukes,
                },
                "capabilities": {
                    "can_missile": can_missile,
                    "can_nuke": can_nuke,
                },
                "analysis": {
                    "string_representation": analysis_string,
                    "purchase_limits": purchase_limits,
                },
                "mmr_string": analysis_string # Updated this so it matches the average instead of the totals!
            }
            return military_data # Added return statement
        except Exception as e:
            self._log_error("Error analyzing nation military", e, "analyze_nation_military")
            return {}
        finally:
            self.logger.debug(f"Military data produced by analyze_nation_military: {military_data}")

    def _format_last_active_time(self, last_active_str: str) -> str:
        """Format last active time into human-readable format."""
        if not last_active_str or last_active_str == 'Unknown':
            return 'Unknown'        
        try:
            from datetime import datetime, timezone
            last_active_dt = datetime.fromisoformat(last_active_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            diff = now - last_active_dt
            total_days = diff.days
            months = total_days // 30
            remaining_days = total_days % 30
            weeks = remaining_days // 7
            days = remaining_days % 7
            hours = diff.seconds // 3600
            minutes = (diff.seconds % 3600) // 60
            parts = []       
            if months > 0:
                parts.append(f"{months} month{'s' if months != 1 else ''}")           
            if weeks > 0:
                parts.append(f"{weeks} week{'s' if weeks != 1 else ''}")            
            if days > 0:
                parts.append(f"{days} day{'s' if days != 1 else ''}")           
            if hours > 0 and not months and not weeks: 
                parts.append(f"{hours} hour{'s' if hours != 1 else ''}")           
            if minutes > 0 and not months and not weeks and not days: 
                parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")           
            if not parts: 
                return "Just now"            
            return " ".join(parts)            
        except (ValueError, AttributeError):
            return last_active_str

    def _is_city_powered(self, city: Dict[str, Any]) -> bool:
        """Robustly determine whether a city is powered."""
        try:
            val = city.get('powered', None)
            if val is None:
                coal = int(city.get('coal_power', 0) or 0)
                oil = int(city.get('oil_power', 0) or 0)
                nuclear = int(city.get('nuclear_power', 0) or 0)
                wind = int(city.get('wind_power', 0) or 0)
                return (coal + oil + nuclear + wind) > 0
            if isinstance(val, bool):
                return val
            if isinstance(val, (int, float)):
                return int(val) != 0
            if isinstance(val, str):
                s = val.strip().lower()
                return s in {"1", "true", "yes", "y", "t"}
            return False
        except Exception:
            try:
                coal = int(city.get('coal_power', 0) or 0)
                oil = int(city.get('oil_power', 0) or 0)
                nuclear = int(city.get('nuclear_power', 0) or 0)
                wind = int(city.get('wind_power', 0) or 0)
                return (coal + oil + nuclear + wind) > 0
            except Exception:
                return False

    def summarize_nation_stats(self, nation: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate and summarize key statistics for a single nation."""
        if not self._validate_input(nation, dict, "nation"):
            return {}

        try:
            self.logger.debug(f"summarize_nation_stats: Incoming nation data: {nation}")

            # Basic info
            nation_id = self._safe_get(nation, 'id') or self._safe_get(nation, 'nation_id')
            last_active_raw = self._safe_get(nation, 'last_active', 'Unknown')
            
            # Cooldowns
            turns_since_city = self._safe_get(nation, 'turns_since_last_city', 0, int)
            turns_since_project = self._safe_get(nation, 'turns_since_last_project', 0, int)
            self.logger.debug(f"summarize_nation_stats: turns_since_last_city: {turns_since_city}, turns_since_last_project: {turns_since_project}")
            city_cooldown_remaining = max(0, 120 - turns_since_city)
            project_cooldown_remaining = max(0, 120 - turns_since_project)
            self.logger.debug(f"summarize_nation_stats: city_cooldown_remaining: {city_cooldown_remaining}, project_cooldown_remaining: {project_cooldown_remaining}")

            # War stats
            wars_won = self._safe_get(nation, 'wars_won', 0, int)
            wars_lost = self._safe_get(nation, 'wars_lost', 0, int)
            total_wars = wars_won + wars_lost
            war_win_ratio = (wars_won / total_wars * 100) if total_wars > 0 else 0

            # City & Infra stats
            cities = self._safe_get(nation, 'cities', [], list)
            total_infra = 0
            avg_city_infra: float = 0.0
            powered_cities_count = 0
            if cities:
                total_infra = sum(self._safe_get(c, 'infrastructure', 0, int) for c in cities if isinstance(c, dict))
                avg_city_infra = total_infra / len(cities) if cities else 0
                powered_cities_count = sum(1 for c in cities if isinstance(c, dict) and self._is_city_powered(c))

            infra_tier = self.get_infrastructure_tier(avg_city_infra)

            # Discord info
            discord_username = self._safe_get(nation, 'discord_username')
            discord_id = self._safe_get(nation, 'discord_id')
            discord_info = discord_username or (f"<@{discord_id}>" if discord_id else "Not linked")

            return {
                'nation_id': nation_id,
                'nation_name': self._safe_get(nation, 'nation_name', 'Unknown Nation'),
                'leader_name': self._safe_get(nation, 'leader_name', 'Unknown Leader'),
                'alliance_name': self._safe_get(nation, 'alliance_name', 'None'),
                'alliance_position': self._safe_get(nation, 'alliance_position', 'Unknown').title(),
                'flag_url': self._safe_get(nation, 'flag'),
                'is_vacation': self._safe_get(nation, 'vacation_mode_turns', 0, int) > 0,
                'is_beige': self._safe_get(nation, 'color', '').lower() == 'beige',
                'beige_turns': self._safe_get(nation, 'beige_turns', 0, int),
                'last_active_formatted': self._format_last_active_time(last_active_raw),
                'discord_info': discord_info,
                'city_cooldown_remaining': city_cooldown_remaining,
                'project_cooldown_remaining': project_cooldown_remaining,
                'num_cities': self._safe_get(nation, 'num_cities', 0, int),
                'powered_cities_count': powered_cities_count,
                'total_cities': len(cities),
                'infra_tier': infra_tier,
                'total_infra': total_infra,
                'avg_city_infra': avg_city_infra,
                'domestic_policy': self._safe_get(nation, 'domestic_policy', 'Unknown'),
                'wars_won': wars_won,
                'wars_lost': wars_lost,
                'total_wars': total_wars,
                'war_win_ratio': war_win_ratio,
                'commendations': self._safe_get(nation, 'commendations', 0, int),
                'denouncements': self._safe_get(nation, 'denouncements', 0, int),
                'money': self._safe_get(nation, 'money', 0, float),
                'credits': self._safe_get(nation, 'credits', 0, int),
                'money_looted': self._safe_get(nation, 'money_looted', 0, float),
                'spies': self._safe_get(nation, 'spies', 0, int),
                'soldiers': self._safe_get(nation, 'soldiers', 0, int),
                'tanks': self._safe_get(nation, 'tanks', 0, int),
                'aircraft': self._safe_get(nation, 'aircraft', 0, int),
                'ships': self._safe_get(nation, 'ships', 0, int),
                'missiles': self._safe_get(nation, 'missiles', 0, int),
                'nukes': self._safe_get(nation, 'nukes', 0, int),
                'ground_capacity': self._safe_get(nation, 'ground_capacity', 0, float),
                'air_capacity': self._safe_get(nation, 'air_capacity', 0, float),
                'naval_capacity': self._safe_get(nation, 'naval_capacity', 0, float),
                'color': self._safe_get(nation, 'color', 'Unknown'),
                'city_cooldown_remaining': city_cooldown_remaining,
                'project_cooldown_remaining': project_cooldown_remaining,
                'mmr_string': self._safe_get(nation, 'mmr_string', ''),
                'war_policy': self._safe_get(nation, 'war_policy', 'Unknown'),
            }
        except Exception as e:
            self._log_error("Error summarizing nation stats", e, "summarize_nation_stats")
            return {}


    def calculate_nation_improvements(self, nation: Dict[str, Any]) -> NationImprovementsStats:
        """Calculates and aggregates improvement counts for a single nation."""
        if not self._validate_input(nation, dict, "nation"):
            return {
                'total_power': 0,
                'total_improvements': 0,
                'num_cities': 0,
                'avg_improvements_per_city': 0.0
            }

        cities = self._safe_get(nation, 'cities', [], list)
        if not cities:
            return {
                'total_power': 0,
                'total_improvements': 0,
                'num_cities': 0,
                'avg_improvements_per_city': 0.0
            }

        improvements_raw = {
            'coal_power': 0, 'oil_power': 0, 'nuclear_power': 0, 'wind_power': 0,
            'coal_mine': 0, 'oil_well': 0, 'uranium_mine': 0, 'iron_mine': 0, 'bauxite_mine': 0, 'lead_mine': 0, 'farm': 0,
            'steel_mill': 0, 'aluminum_refinery': 0, 'munitions_factory': 0, 'gasrefinery': 0,
            'police_station': 0, 'hospital': 0, 'recycling_center': 0, 'subway': 0,
            'supermarket': 0, 'bank': 0, 'shopping_mall': 0, 'stadium': 0,
            'barracks': 0, 'factory': 0, 'hangar': 0, 'drydock': 0
        }

        for city in cities:
            if not isinstance(city, dict):
                continue
            for key in improvements_raw:
                improvements_raw[key] += self._safe_get(city, key, 0, int)
        
        # Compatibility for hangar key
        if 'airforcebase' in cities[0]:
             for city in cities:
                if not isinstance(city, dict):
                    continue
                improvements_raw['hangar'] += self._safe_get(city, 'airforcebase', 0, int)


        total_power = improvements_raw['coal_power'] + improvements_raw['oil_power'] + improvements_raw['nuclear_power'] + improvements_raw['wind_power']
        total_improvements = sum(improvements_raw.values())
        
        results: NationImprovementsStats = {
            **improvements_raw,  # Unpack all individual improvement counts
            'total_power': total_power,
            'total_improvements': total_improvements,
            'num_cities': len(cities),
            'avg_improvements_per_city': total_improvements / len(cities) if cities else 0.0
        }
        return results




    def get_infrastructure_tier(self, avg_infra: float) -> str:
        """Returns the infrastructure tier based on average infrastructure."""
        return self._get_infrastructure_tier(avg_infra)

    def get_nation_specializations(self, nation: Dict[str, Any]) -> List[Tuple[str, str]]:
        """
        Get a list of nation specializations based on various criteria.
        Returns a list of tuples (emoji_name, specialization_name).
        """
        specializations = []

        # Project-based
        if self.has_project(nation, 'Missile Launch Pad'):
            specializations.append(('Missile', 'Missile'))
        if self.has_project(nation, 'Nuclear Research Facility'):
            specializations.append(('Nuke', 'Nuke'))

        # Spy-based
        spies = nation.get('spies', 0) or 0
        if spies >= 50:
            specializations.append(('Spy', 'Master Spy'))

        # Supremacy-based
        supremacy = self.calculate_military_advantage(nation).get('type', 'none')
        if supremacy == 'land':
            specializations.append(('LandSup', 'Land Supremacy'))
        elif supremacy == 'air':
            specializations.append(('AirSup', 'Air Supremacy'))
        elif supremacy == 'naval':
            specializations.append(('NavySup', 'Naval Supremacy'))

        # Commendation-based
        commendations = nation.get('commendations', 0) or 0
        if commendations >= 1000:
            specializations.append(('Like4', 'Saint'))
        elif commendations >= 500:
            specializations.append(('Like3', 'Idolized'))
        elif commendations >= 100:
            specializations.append(('Like2', 'Beloved'))
        elif commendations >= 25:
            specializations.append(('Like1', 'Respected'))

        # Denouncement-based
        denouncements = nation.get('denouncements', 0) or 0
        if denouncements >= 1000:
            specializations.append(('Dislike4', 'Hated'))
        elif denouncements >= 500:
            specializations.append(('Dislike3', 'Disgraced'))
        elif denouncements >= 100:
            specializations.append(('Dislike2', 'Disliked'))
        elif denouncements >= 25:
            specializations.append(('Dislike1', 'Troublemaker'))
            
        # Pirate-based (money looted)
        money_looted = nation.get('money_looted', 0) or 0
        if money_looted >= 1_000_000_000:
            specializations.append(('Pirate5', 'Act of God'))
        elif money_looted >= 500_000_000:
            specializations.append(('Pirate4', 'Legendary Pirate'))
        elif money_looted >= 100_000_000:
            specializations.append(('Pirate3', 'Master Pirate'))
        elif money_looted >= 25_000_000:
            specializations.append(('Pirate2', 'Pirate'))
        elif money_looted >= 5_000_000:
            specializations.append(('Pirate1', 'Thief'))
            
        return specializations

    def parse_time_window(self, time_str: str, default_days: int = 30) -> Optional[datetime]:
        """Parses a time limit argument like '2w', '14d', '3m' into a datetime object."""
        if not time_str:
            return datetime.utcnow() - timedelta(days=default_days)

        time_str = time_str.lower().strip()
        match = re.match(r"(\d+)([wdmh])", time_str)
        if not match:
            self.logger.warning(f"Invalid time_str format: {time_str}")
            return datetime.utcnow() - timedelta(days=default_days)

        value = int(match.group(1))
        unit = match.group(2)

        now = datetime.utcnow()
        if unit == 'w':
            return now - timedelta(weeks=value)
        elif unit == 'd':
            return now - timedelta(days=value)
        elif unit == 'm':
            return now - timedelta(days=value * 30)  # Approximation
        elif unit == 'h':
            return now - timedelta(hours=value)
        return datetime.utcnow() - timedelta(days=default_days)

    def _bucket_city_counts_sync(self, nations: List[Dict[str, Any]]) -> List[Tuple[str, int]]:
        """Synchronous implementation of city count bucketing."""
        try:
            active = self._get_active_nations_sync(nations)
            ranges = [(1,4),(5,9),(10,14),(15,19),(20,24),(25,29),(30,34),(35,39),(40,44),(45,49),(50,54),(55,59),(60,64)]
            counts = []
            
            # Pre-calculate city counts to avoid repeated lookups
            city_counts = []
            for n in active:
                cities_val = self._safe_get(n, 'cities', [])
                if isinstance(cities_val, list):
                    c = len(cities_val)
                else:
                    try:
                        c = int(cities_val or 0)
                    except (ValueError, TypeError):
                        c = 0
                city_counts.append(c)
            
            for low, high in ranges:
                cnt = sum(1 for c in city_counts if low <= c <= high)
                counts.append((f"{low}-{high}", cnt))
            return counts
        except Exception as e:
            self._log_error("Error bucketing city counts", e, "_bucket_city_counts_sync")
            return []

    async def bucket_city_counts(self, nations: List[Dict[str, Any]]) -> List[Tuple[str, int]]:
        """Async wrapper for city count bucketing."""
        return await asyncio.to_thread(self._bucket_city_counts_sync, nations)

    def _calculate_nation_statistics_sync(self, nations: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not nations:
            return {
                'total_nations': 0, 'active_nations': 0, 'applicant_nations': 0,
                'vacation_nations': 0, 'grey_nations': 0, 'beige_nations': 0,
                'inactive_7_days': 0, 'inactive_14_days': 0
            }       
        try:
            total_nations = len(nations)
            active_nations = 0
            applicant_nations = 0
            vacation_nations = 0
            grey_nations = 0
            beige_nations = 0
            inactive_7_days = 0
            inactive_14_days = 0
            now = datetime.now(timezone.utc)
            seven_days_ago = now - timedelta(days=7)
            fourteen_days_ago = now - timedelta(days=14)           
            for nation in nations:
                if not isinstance(nation, dict):
                    continue
                vacation_turns = self._safe_get(nation, 'vacation_mode_turns', 0, int)
                alliance_position = self._safe_get(nation, 'alliance_position', '', str)
                color = self._safe_get(nation, 'color', '', str).upper()
                last_active_str = self._safe_get(nation, 'last_active', '', str)
                is_active = (vacation_turns == 0 and alliance_position.upper() != 'APPLICANT')
                last_active = None
                if last_active_str:
                    try:
                        if last_active_str.endswith('+00:00'):
                            last_active = datetime.fromisoformat(last_active_str.replace('+00:00', '')).replace(tzinfo=timezone.utc)
                        else:
                            last_active = datetime.fromisoformat(last_active_str).replace(tzinfo=timezone.utc)
                    except (ValueError, TypeError):
                        last_active = None
                if alliance_position.upper() == 'APPLICANT':
                    applicant_nations += 1
                    continue  # Skip APPs for vacation and inactive counts
                
                if vacation_turns > 0:
                    vacation_nations += 1
                
                if is_active and last_active:
                    if last_active < fourteen_days_ago:
                        inactive_14_days += 1
                    elif last_active < seven_days_ago:
                        inactive_7_days += 1                
                if is_active:
                    active_nations += 1
                    if color == 'GREY' or color == 'GRAY':
                        grey_nations += 1
                    elif color == 'BEIGE':
                        beige_nations += 1           
            return {
                'total_nations': total_nations,
                'active_nations': active_nations,
                'applicant_nations': applicant_nations,
                'vacation_nations': vacation_nations,
                'grey_nations': grey_nations,
                'beige_nations': beige_nations,
                'inactive_7_days': inactive_7_days,
                'inactive_14_days': inactive_14_days
            }           
        except Exception as e:
            self._log_error("Error calculating nation statistics", e, "_calculate_nation_statistics_sync")
            return {
                'total_nations': 0, 'active_nations': 0, 'applicant_nations': 0,
                'vacation_nations': 0, 'grey_nations': 0, 'beige_nations': 0,
                'inactive_7_days': 0, 'inactive_14_days': 0
            }

    async def calculate_nation_statistics(self, nations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Async wrapper for calculating nation statistics."""
        return await asyncio.to_thread(self._calculate_nation_statistics_sync, nations)

    def _calculate_alliance_statistics_sync(self, nations: List[Dict[str, Any]]) -> AllianceStats:
        stats: AllianceStats = {
            'total_nations': len(nations),
            'total_score': sum(float(nation.get('score', 0) or 0) for nation in nations),
            'total_cities': sum(int((nation.get('num_cities', nation.get('cities', 0))) or 0) for nation in nations),
            'missile_capable': 0, 'nuclear_capable': 0, 'vital_defense_system': 0,
            'iron_dome': 0, 'propaganda_bureau': 0, 'military_research_center': 0,
            'space_program': 0, 'missile_launch_pad': 0, 'nuclear_research_facility': 0,
            'nuclear_launch_facility': 0,
            'total_military': {
                'soldiers': 0, 'tanks': 0, 'aircraft': 0, 'ships': 0, 'missiles': 0, 'nukes': 0
            },
            'production_capacity': {
                'total_barracks': 0, 'total_factories': 0, 'total_hangars': 0, 'total_drydocks': 0,
                'daily_soldiers': 0, 'daily_tanks': 0, 'daily_aircraft': 0, 'daily_ships': 0,
                'daily_missiles': 0, 'daily_nukes': 0,
                'max_soldiers': 0, 'max_tanks': 0, 'max_aircraft': 0, 'max_ships': 0,
                'max_missiles': 0, 'max_nukes': 0
            }
        }       
        for nation in nations:
            if self.has_project(nation, 'Missile Launch Pad'):
                stats['missile_capable'] += 1
                stats['missile_launch_pad'] += 1
            if self.has_project(nation, 'Nuclear Research Facility'):
                stats['nuclear_capable'] += 1
                stats['nuclear_research_facility'] += 1
            if self.has_project(nation, 'Vital Defense System'):
                stats['vital_defense_system'] += 1
            if self.has_project(nation, 'Iron Dome'):
                stats['iron_dome'] += 1
            if self.has_project(nation, 'Propaganda Bureau'):
                stats['propaganda_bureau'] += 1
            if self.has_project(nation, 'Military Research Center'):
                stats['military_research_center'] += 1
            if self.has_project(nation, 'Space Program'):
                stats['space_program'] += 1
            if self.has_project(nation, 'Nuclear Launch Facility'):
                stats['nuclear_launch_facility'] += 1
            
            military = nation.get('military', {}) or {}
            stats['total_military']['soldiers'] += (military.get('soldiers', 0) if 'soldiers' in military else nation.get('soldiers', 0))
            stats['total_military']['tanks'] += (military.get('tanks', 0) if 'tanks' in military else nation.get('tanks', 0))
            stats['total_military']['aircraft'] += (military.get('aircraft', 0) if 'aircraft' in military else nation.get('aircraft', 0))
            stats['total_military']['ships'] += (military.get('ships', 0) if 'ships' in military else nation.get('ships', 0))
            stats['total_military']['missiles'] += (military.get('missiles', 0) if 'missiles' in military else nation.get('missiles', 0))
            stats['total_military']['nukes'] += (military.get('nukes', 0) if 'nukes' in military else nation.get('nukes', 0))
            
            production_data: Dict[str, int] = self.calculate_military_purchase_limits(nation)
            stats['production_capacity']['total_barracks'] += production_data.get('total_barracks', 0) # type: ignore
            stats['production_capacity']['total_factories'] += production_data.get('total_factories', 0) # type: ignore
            stats['production_capacity']['total_hangars'] += production_data.get('total_hangars', 0) # type: ignore
            stats['production_capacity']['total_drydocks'] += production_data.get('total_drydocks', 0) # type: ignore
            stats['production_capacity']['daily_soldiers'] += production_data.get('soldiers_daily', 0) # type: ignore
            stats['production_capacity']['daily_tanks'] += production_data.get('tanks_daily', 0) # type: ignore
            stats['production_capacity']['daily_aircraft'] += production_data.get('aircraft_daily', 0) # type: ignore
            stats['production_capacity']['daily_ships'] += production_data.get('ships_daily', 0) # type: ignore
            stats['production_capacity']['daily_missiles'] += production_data.get('missiles', 0) # type: ignore
            stats['production_capacity']['daily_nukes'] += production_data.get('nukes', 0) # type: ignore
            stats['production_capacity']['max_soldiers'] += production_data.get('soldiers_max', 0) # type: ignore
            stats['production_capacity']['max_tanks'] += production_data.get('tanks_max', 0) # type: ignore
            stats['production_capacity']['max_aircraft'] += production_data.get('aircraft_max', 0) # type: ignore
            stats['production_capacity']['max_ships'] += production_data.get('ships_max', 0) # type: ignore
            
            if self.has_project(nation, 'Missile Launch Pad'):
                stats['production_capacity']['max_missiles'] += 50           
            if self.has_project(nation, 'Nuclear Research Facility'):
                stats['production_capacity']['max_nukes'] += 50        
        return stats
    
    async def calculate_alliance_statistics(self, nations: List[Dict[str, Any]]) -> AllianceStats:
        """Async wrapper for calculating alliance statistics."""
        return await asyncio.to_thread(self._calculate_alliance_statistics_sync, nations)

    def _calculate_resource_totals_sync(self, nations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Synchronous implementation of resource total calculations."""
        try:
            totals = {
                'money': 0, 'credits': 0, 'gasoline': 0, 'munitions': 0,
                'steel': 0, 'aluminum': 0, 'food': 0, 'coal': 0,
                'oil': 0, 'uranium': 0, 'iron': 0, 'bauxite': 0, 'lead': 0
            }
            
            for n in nations:
                totals['money'] += (n.get('money', 0) or 0)
                totals['credits'] += (n.get('credits', 0) or 0)
                totals['gasoline'] += (n.get('gasoline', 0) or 0)
                totals['munitions'] += (n.get('munitions', 0) or 0)
                totals['steel'] += (n.get('steel', 0) or 0)
                totals['aluminum'] += (n.get('aluminum', 0) or 0)
                totals['food'] += (n.get('food', 0) or 0)
                totals['coal'] += (n.get('coal', 0) or 0)
                totals['oil'] += (n.get('oil', 0) or 0)
                totals['uranium'] += (n.get('uranium', 0) or 0)
                totals['iron'] += (n.get('iron', 0) or 0)
                totals['bauxite'] += (n.get('bauxite', 0) or 0)
                totals['lead'] += (n.get('lead', 0) or 0)
            
            return totals
        except Exception as e:
            self._log_error("Error calculating resource totals", e, "_calculate_resource_totals_sync")
            return {k: 0 for k in ['money', 'credits', 'gasoline', 'munitions', 'steel', 'aluminum', 'food', 'coal', 'oil', 'uranium', 'iron', 'bauxite', 'lead']}

    async def calculate_resource_totals(self, nations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Async wrapper for calculating resource totals."""
        return await asyncio.to_thread(self._calculate_resource_totals_sync, nations)

    def _calculate_full_mill_data_sync(self, nations: List[Dict[str, Any]]) -> Dict[str, Any]:
        try:
            # Filter only VM/APPLICANT, include 14+ inactive
            active_nations = [n for n in nations if (self._safe_get(n, 'vacation_mode_turns', 0, int) == 0 and self._safe_get(n, 'alliance_position', '', str).upper() != 'APPLICANT')]
            
            data: Dict[str, Any] = {
                'current_soldiers': 0, 'current_tanks': 0, 'current_aircraft': 0, 'current_ships': 0,
                'current_missiles': 0, 'current_nukes': 0,
                'max_soldiers': 0, 'max_tanks': 0, 'max_aircraft': 0, 'max_ships': 0,
                'daily_soldiers': 0, 'daily_tanks': 0, 'daily_aircraft': 0, 'daily_ships': 0,
                'daily_missiles': 0, 'daily_nukes': 0,
                'total_cities': 0, 'total_score': 0,
                'max_soldier_days': 0.0, 'max_tank_days': 0.0, 'max_aircraft_days': 0.0, 'max_ship_days': 0.0,
                'max_soldier_nation': "", 'max_tank_nation': "", 'max_aircraft_nation': "", 'max_ship_nation': "",
                'soldier_gap': 0, 'tank_gap': 0, 'aircraft_gap': 0, 'ship_gap': 0,
                'soldier_days': 0.0, 'tank_days': 0.0, 'aircraft_days': 0.0, 'ship_days': 0.0,
                'total_nations': 0, 'active_nations': 0
            }
            
            for nation in active_nations:
                military = nation.get('military', {}) or {}
                data['current_soldiers'] += (military.get('soldiers', 0) if 'soldiers' in military else nation.get('soldiers', 0))
                data['current_tanks'] += (military.get('tanks', 0) if 'tanks' in military else nation.get('tanks', 0))
                data['current_aircraft'] += (military.get('aircraft', 0) if 'aircraft' in military else nation.get('aircraft', 0))
                data['current_ships'] += (military.get('ships', 0) if 'ships' in military else nation.get('ships', 0))
                data['current_missiles'] += (military.get('missiles', 0) if 'missiles' in military else nation.get('missiles', 0))
                data['current_nukes'] += (military.get('nukes', 0) if 'nukes' in military else nation.get('nukes', 0))
                data['total_cities'] += nation.get('num_cities', 0)
                data['total_score'] += nation.get('score', 0)
                
                # Calculate individual nation limits and days
                limits = self.calculate_military_purchase_limits(nation)
                
                nation_current = {
                    'soldiers': (military.get('soldiers', 0) if 'soldiers' in military else nation.get('soldiers', 0)),
                    'tanks': (military.get('tanks', 0) if 'tanks' in military else nation.get('tanks', 0)),
                    'aircraft': (military.get('aircraft', 0) if 'aircraft' in military else nation.get('aircraft', 0)),
                    'ships': (military.get('ships', 0) if 'ships' in military else nation.get('ships', 0))
                }
                
                nation_max = {
                    'soldiers': limits.get('soldiers_max', 0),
                    'tanks': limits.get('tanks_max', 0),
                    'aircraft': limits.get('aircraft_max', 0),
                    'ships': limits.get('ships_max', 0)
                }
                
                nation_daily = {
                    'soldiers': limits.get('soldiers_daily', 0),
                    'tanks': limits.get('tanks_daily', 0),
                    'aircraft': limits.get('aircraft_daily', 0),
                    'ships': limits.get('ships_daily', 0)
                }
                
                # Define a maximum days constant to avoid infinity values
                MAX_DAYS = 999999
                
                for unit in ['soldiers', 'tanks', 'aircraft', 'ships']:
                    gap = max(0, nation_max[unit] - nation_current[unit])
                    daily = nation_daily[unit]
                    days = gap / daily if daily > 0 else MAX_DAYS if gap > 0 else 0
                    
                    # Update max days if this nation takes longer
                    key_days = f'max_{unit.rstrip("s")}_days'
                    key_nation = f'max_{unit.rstrip("s")}_nation'
                    
                    if days > data[key_days]:  # type: ignore[literal-required]
                        data[key_days] = days # type: ignore[literal-required]
                        data[key_nation] = nation.get('nation_name', 'Unknown') # type: ignore[literal-required]
                        
                    data[f'daily_{unit}'] += daily # type: ignore[literal-required]
                    data[f'max_{unit}'] += nation_max[unit] # type: ignore[literal-required]

                data['daily_missiles'] += limits.get('missiles', 0)
                data['daily_nukes'] += limits.get('nukes', 0)
            
            # Calculate gaps
            data['soldier_gap'] = max(0, data['max_soldiers'] - data['current_soldiers'])
            data['tank_gap'] = max(0, data['max_tanks'] - data['current_tanks'])
            data['aircraft_gap'] = max(0, data['max_aircraft'] - data['current_aircraft'])
            data['ship_gap'] = max(0, data['max_ships'] - data['current_ships'])
            
            # Legacy fields for compatibility
            data['soldier_days'] = data['max_soldier_days']
            data['tank_days'] = data['max_tank_days']
            data['aircraft_days'] = data['max_aircraft_days']
            data['ship_days'] = data['max_ship_days']
            
            data['total_nations'] = len(active_nations)
            data['active_nations'] = len(active_nations)
            
            return data
        except Exception as e:
            self._log_error(f"Error calculating full mill data: {e}", e, "_calculate_full_mill_data_sync")
            return {
                'total_nations': 0, 'active_nations': 0, 'total_cities': 0, 'total_score': 0,
                'current_soldiers': 0, 'current_tanks': 0, 'current_aircraft': 0, 'current_ships': 0,
                'max_soldiers': 0, 'max_tanks': 0, 'max_aircraft': 0, 'max_ships': 0,
                'daily_soldiers': 0, 'daily_tanks': 0, 'daily_aircraft': 0, 'daily_ships': 0,
                'soldier_gap': 0, 'tank_gap': 0, 'aircraft_gap': 0, 'ship_gap': 0,
                'soldier_days': 0, 'tank_days': 0, 'aircraft_days': 0, 'ship_days': 0,
                'max_soldier_days': 0, 'max_tank_days': 0, 'max_aircraft_days': 0, 'max_ship_days': 0,
            }

    async def calculate_full_mill_data(self, nations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Async wrapper for calculating full military data."""
        return await asyncio.to_thread(self._calculate_full_mill_data_sync, nations)

    def calculate_military_purchase_limits(self, nation: Dict[str, Any]) -> Dict[str, int]:
        self._log_message(
            f"Nation data for military purchase limits: num_cities={nation.get('num_cities', 0)}, air_research={nation.get('air_research', 0)}, air_capacity={nation.get('air_capacity', 0)}, military_research={nation.get('military_research', {})}, cities_sample={[c.get('airforcebase', 0) for c in nation.get('cities', [])[:5]]}",
            level=logging.DEBUG,
            context="calculate_military_purchase_limits"
        )
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
            avg_improvements_per_city = 2 
            total_barracks = num_cities * avg_improvements_per_city
            total_factories = num_cities * avg_improvements_per_city
            total_hangars = num_cities * avg_improvements_per_city
            total_drydocks = num_cities * avg_improvements_per_city
        soldier_daily_limit = total_barracks * 1000 
        tank_daily_limit = total_factories * 50    
        aircraft_daily_limit = total_hangars * 3   
        ship_daily_limit = total_drydocks * 1
        ground_research = nation.get('ground_research', 0)
        air_research = nation.get('air_research', 0)
        naval_research = nation.get('naval_research', 0)
        aircraft_daily_limit += air_research * 15 
        tank_daily_limit += ground_research * 250 
        soldier_daily_limit += ground_research * 3000  
        ship_daily_limit += naval_research * 5        
        if self.has_project(nation, 'Propaganda Bureau'):
            soldier_daily_limit = int(soldier_daily_limit * 1.10)
            tank_daily_limit = int(tank_daily_limit * 1.10)
            aircraft_daily_limit = int(aircraft_daily_limit * 1.10)
            ship_daily_limit = int(ship_daily_limit * 1.10)
        soldier_max_capacity = total_barracks * 3000 
        tank_max_capacity = total_factories * 250    
        aircraft_max_capacity = total_hangars * 15  
        ship_max_capacity = total_drydocks * 5    
        aircraft_max_capacity += air_research * 15 
        tank_max_capacity += ground_research * 250  
        soldier_max_capacity += ground_research * 3000  
        ship_max_capacity += naval_research * 5  
        ground_bonus = nation.get('ground_capacity', 0) or 0
        air_bonus = nation.get('air_capacity', 0) or 0
        naval_bonus = nation.get('naval_capacity', 0) or 0
        if not ground_bonus and not air_bonus and not naval_bonus:
            military_research = nation.get('military_research', {})
            ground_bonus = military_research.get('ground_capacity', 0) or 0
            air_bonus = military_research.get('air_capacity', 0) or 0
            naval_bonus = military_research.get('naval_capacity', 0) or 0
        soldier_max_capacity += ground_bonus
        tank_max_capacity += ground_bonus 
        aircraft_max_capacity += air_bonus
        ship_max_capacity += naval_bonus
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
        self._log_message(
            f"Aircraft Limits - total_hangars: {total_hangars}, air_research: {air_research}, air_bonus: {air_bonus}, aircraft_daily_limit: {aircraft_daily_limit}, aircraft_max_capacity: {aircraft_max_capacity}",
            level=logging.DEBUG,
            context="calculate_military_purchase_limits"
        )
        return {
            'soldiers_daily': soldier_daily_limit,
            'tanks_daily': tank_daily_limit,
            'aircraft_daily': aircraft_daily_limit,
            'ships_daily': ship_daily_limit,
            'missiles': missile_limit,
            'nukes': nuke_limit,
            'soldiers_max': soldier_max_capacity,
            'tanks_max': tank_max_capacity,
            'aircraft_max': aircraft_max_capacity,
            'ships_max': ship_max_capacity,
            'total_barracks': total_barracks,
            'total_factories': total_factories,
            'total_hangars': total_hangars,
            'total_drydocks': total_drydocks
        }
    
    def get_nation_specialty(self, nation: Dict[str, Any]) -> str:
        try:
            military_advantages = self.calculate_military_advantage(nation)
            advantages = military_advantages.get('advantages', [])
            ground_advantage = 'Ground Advantage' in advantages
            air_advantage = 'Air Advantage' in advantages
            naval_advantage = 'Naval Advantage' in advantages
            if ground_advantage or air_advantage or naval_advantage:
                advantage_count = sum([ground_advantage, air_advantage, naval_advantage])
                if advantage_count == 1:
                    if ground_advantage:
                        return "Ground"
                    elif air_advantage:
                        return "Air"
                    else:
                        return "Naval"
                if advantage_count == 3:
                    return "Generalist"
                military = nation.get('military', {})                
                if military:
                    soldiers = military.get('soldiers', 0)
                    tanks = military.get('tanks', 0)
                    aircraft = military.get('aircraft', 0)
                    ships = nation.get('ships', 0) 
                else:
                    soldiers = nation.get('soldiers', 0)
                    tanks = nation.get('tanks', 0)
                    aircraft = nation.get('aircraft', 0)
                    ships = nation.get('ships', 0)               
                total_units = soldiers + tanks + aircraft + ships
                if total_units > 0:
                    ground_units = soldiers + tanks
                    air_units = aircraft
                    naval_units = ships
                    if ground_advantage and air_advantage:
                        return "Ground" if ground_units >= air_units else "Air"
                    elif ground_advantage and naval_advantage:
                        return "Ground" if ground_units >= naval_units else "Naval"
                    elif air_advantage and naval_advantage:
                        return "Air" if air_units >= naval_units else "Naval"
                if ground_advantage:
                    return "Ground"
                elif air_advantage:
                    return "Air"
                else:
                    return "Naval"           
            military = nation.get('military', {})            
            if military:
                soldiers = military.get('soldiers', 0)
                tanks = military.get('tanks', 0)
                aircraft = military.get('aircraft', 0)
                ships = military.get('ships', 0)
            else:
                soldiers = nation.get('soldiers', 0)
                tanks = nation.get('tanks', 0)
                aircraft = nation.get('aircraft', 0)
                ships = nation.get('ships', 0)
            
            total_units = soldiers + tanks + aircraft + ships
            if total_units == 0:
                return "Generalist"
            ground_percent = (soldiers + tanks) / total_units
            air_percent = aircraft / total_units
            naval_percent = ships / total_units
            if ground_percent >= air_percent and ground_percent >= naval_percent:
                return "Ground"
            elif air_percent >= naval_percent:
                return "Air"
            else:
                return "Naval"               
        except Exception as e:
            self._log_error(f"Error getting nation specialty: {e}", e, "get_nation_specialty")
            return 'Generalist'
    
    def calculate_combat_score(self, nation: Dict[str, Any]) -> float:
        """Calculate a normalized combat score (1-100) based on infrastructure, military build quality, and projects."""
        try:
            # Get infrastructure stats
            infra_stats = self.calculate_infrastructure_stats(nation)
            avg_infra = infra_stats.get('average_infrastructure', 1000)
            
            # Get current military units
            soldiers = nation.get('soldiers', 0)
            tanks = nation.get('tanks', 0)
            aircraft = nation.get('aircraft', 0)
            ships = nation.get('ships', 0)
            missiles = nation.get('missiles', 0)
            nukes = nation.get('nukes', 0)
            
            # Get number of cities for normalization
            num_cities = nation.get('num_cities', 1)
            if num_cities == 0:
                num_cities = 1
            
            # Infrastructure score (lower infra = higher war focus = higher score)
            # Perfect score at 500 infra, decreasing as infra increases
            if avg_infra <= 500:
                infra_score = 100.0
            elif avg_infra >= 3000:
                infra_score = 1.0
            else:
                # Exponential decay: higher infra = much lower score
                infra_score = max(1.0, 100.0 * (1 - (avg_infra - 500) / 2500) ** 2)
            
            # Military build quality score (5/5/5/3 optimal build)
            # Calculate ratios per city
            soldiers_per_city = soldiers / num_cities
            tanks_per_city = tanks / num_cities
            aircraft_per_city = aircraft / num_cities
            ships_per_city = ships / num_cities
            
            # Optimal ratios for 5/5/5/3 build
            optimal_soldiers = 15000  # 5 barracks * 3000
            optimal_tanks = 1250    # 5 factories * 250
            optimal_aircraft = 75   # 5 hangars * 15
            optimal_ships = 15      # 3 drydocks * 5
            
            # Calculate build quality (0-100)
            soldier_quality = min(100.0, (soldiers_per_city / optimal_soldiers) * 100)
            tank_quality = min(100.0, (tanks_per_city / optimal_tanks) * 100)
            aircraft_quality = min(100.0, (aircraft_per_city / optimal_aircraft) * 100)
            ship_quality = min(100.0, (ships_per_city / optimal_ships) * 100)
            
            # Weighted average (aircraft and ships more important)
            build_score = (
                soldier_quality * 0.15 +
                tank_quality * 0.20 +
                aircraft_quality * 0.35 +
                ship_quality * 0.30
            )
            
            # Strategic projects score
            strategic_projects = [
                'Missile Launch Pad', 'Nuclear Research Facility', 'Iron Dome',
                'Vital Defense System', 'Military Research Center', 'Space Program',
                'Nuclear Launch Facility', 'Propaganda Bureau'
            ]
            
            project_count = 0
            for project in strategic_projects:
                if self.has_project(nation, project):
                    project_count += 1
            
            # Project score (each project adds points, with diminishing returns)
            if project_count == 0:
                project_score = 1.0
            else:
                # First few projects give more points, then diminishing returns
                base_project_score = project_count * 12.5  # 8 projects = 100 points max
                project_score = min(100.0, base_project_score)
            
            # Special weapons bonus (missiles and nukes)
            special_weapons_score = 0.0
            if missiles > 0:
                special_weapons_score += 10.0
            if nukes > 0:
                special_weapons_score += 15.0
            
            final_score = (
                infra_score * 0.30 +
                build_score * 0.40 +
                project_score * 0.25 +
                special_weapons_score * 0.05
            )
            
            # Ensure score is between 1-100
            return max(1.0, min(100.0, final_score))
            
        except Exception as e:
            self._log_error(f"Error calculating combat score: {e}", e, "calculate_combat_score")
            return 50.0  # Return middle score on error
    
    def _get_default_military_limits(self) -> Dict[str, int]:
        """Return default military purchase limits."""
        return {
            'soldiers': 250,
            'tanks': 25,
            'aircraft': 5,
            'ships': 2,
            'soldiers_max': 1000,
            'tanks_max': 100,
            'aircraft_max': 20,
            'ships_max': 10
        }
    
    def calculate_infrastructure_stats(self, nation: Dict[str, Any]) -> Dict[str, float]:
        cities_data = nation.get('cities', [])
        num_cities = nation.get('num_cities', 0)       
        if not isinstance(cities_data, list) or len(cities_data) == 0:
            estimated_avg_infra = max(50, (nation.get('score', 0) / num_cities) * 12) if num_cities > 0 else 50
            return {
                'average_infrastructure': estimated_avg_infra,
                'total_infrastructure': estimated_avg_infra * num_cities,
                'min_infrastructure': estimated_avg_infra * 0.8,  # Estimate range
                'max_infrastructure': estimated_avg_infra * 1.2,
                'infrastructure_range': estimated_avg_infra * 0.4,
                'infrastructure_tier': self._get_infrastructure_tier(estimated_avg_infra),
                'has_detailed_data': False
            }
        infrastructure_levels = []
        for city in cities_data:
            infra = city.get('infrastructure', 0)
            if infra > 0:
                infrastructure_levels.append(infra)       
        if not infrastructure_levels:
            estimated_avg_infra = max(50, (nation.get('score', 0) / num_cities) * 12) if num_cities > 0 else 50
            return {
                'average_infrastructure': estimated_avg_infra,
                'total_infrastructure': estimated_avg_infra * num_cities,
                'min_infrastructure': estimated_avg_infra,
                'max_infrastructure': estimated_avg_infra,
                'infrastructure_range': 0,
                'infrastructure_tier': self._get_infrastructure_tier(estimated_avg_infra),
                'has_detailed_data': False
            }       
        avg_infra = sum(infrastructure_levels) / len(infrastructure_levels)
        min_infra = min(infrastructure_levels)
        max_infra = max(infrastructure_levels)
        infra_range = max_infra - min_infra
        total_infra = sum(infrastructure_levels)        
        return {
            'average_infrastructure': avg_infra,
            'total_infrastructure': total_infra,
            'min_infrastructure': min_infra,
            'max_infrastructure': max_infra,
            'infrastructure_range': infra_range,
            'infrastructure_tier': self._get_infrastructure_tier(avg_infra),
            'has_detailed_data': True
        }

    def _get_infrastructure_tier(self, avg_infrastructure: float) -> str:
        if avg_infrastructure < 500:
            return "Perfect"  
        elif avg_infrastructure < 1000:
            return "Great"    
        elif avg_infrastructure < 1500:
            return "Good" 
        elif avg_infrastructure < 2000:
            return "Average"
        elif avg_infrastructure < 2500:
            return "Bad"  
        elif avg_infrastructure < 3000:
            return "Horrible"  
        else:
            return "Terrible" 
    
    def _calculate_infrastructure_compatibility(self, nation1: Dict[str, Any], nation2: Dict[str, Any]) -> float:
        infra1 = nation1.get('infrastructure_stats', {})
        infra2 = nation2.get('infrastructure_stats', {})       
        avg1 = infra1.get('average_infrastructure', 0)
        avg2 = infra2.get('average_infrastructure', 0)        
        if avg1 == 0 or avg2 == 0:
            return 0.5        
        higher = max(avg1, avg2)
        lower = min(avg1, avg2)
        percentage_diff = (higher - lower) / higher
        compatibility = max(0.0, 1.0 - (percentage_diff * 2))        
        return compatibility
    
    def calculate_building_ratios(self, nation: Dict[str, Any]) -> BuildingRatios:
        cities_data = nation.get('cities', [])
        num_cities = nation.get('num_cities', len(cities_data))        
        if not cities_data or num_cities == 0:
            return {
                'barracks_ratio': 0.0,
                'factories_ratio': 0.0,
                'airforcebase_ratio': 0.0,
                'drydock_ratio': 0.0,
                'mmr_string': '0/0/0/0'
            }        
        total_barracks = 0
        total_factories = 0
        total_airforcebases = 0
        total_drydocks = 0        
        for city in cities_data:
            total_barracks += city.get('barracks', 0)
            total_factories += city.get('factory', 0)
            total_airforcebases += city.get('airforcebase', 0)
            total_drydocks += city.get('drydock', 0)
        barracks_ratio = total_barracks / num_cities
        factories_ratio = total_factories / num_cities
        airforcebase_ratio = total_airforcebases / num_cities
        drydock_ratio = total_drydocks / num_cities
        mmr_string = f"{barracks_ratio:.1f}/{factories_ratio:.1f}/{airforcebase_ratio:.1f}/{drydock_ratio:.1f}"       
        return {
            'barracks_ratio': barracks_ratio,
            'factories_ratio': factories_ratio,
            'airforcebase_ratio': airforcebase_ratio,
            'drydock_ratio': drydock_ratio,
            'mmr_string': mmr_string
        }
    
    def validate_attack_range(self, attacker_score: float, defender_score: float) -> bool:
        min_score = attacker_score * 0.75 
        max_score = attacker_score * 2.5  
        return min_score <= defender_score <= max_score
    
    def calculate_party_war_range(self, party_members: List[Dict[str, Any]]) -> Dict[str, float]:
        if not party_members:
            return {'min_range': 0, 'max_range': 0, 'avg_score': 0, 'overlapping_min': 0, 'overlapping_max': 0, 'has_overlap': False}
        scores = [member.get('score', 0) for member in party_members]
        individual_ranges = []
        for score in scores:
            min_attack = score * 0.75 
            max_attack = score * 2.5   
            individual_ranges.append((min_attack, max_attack))
        overlapping_min = max(range[0] for range in individual_ranges)
        overlapping_max = min(range[1] for range in individual_ranges)
        has_overlap = overlapping_min <= overlapping_max
        if not has_overlap:
            overlapping_min = 0
            overlapping_max = 0
        total_score = sum(scores)
        avg_score = total_score / len(scores) if scores else 0
        return {
            'min_range': min(r[0] for r in individual_ranges) if individual_ranges else 0,
            'max_range': max(r[1] for r in individual_ranges) if individual_ranges else 0,
            'avg_score': avg_score,
            'overlapping_min': overlapping_min,
            'overlapping_max': overlapping_max,
            'has_overlap': has_overlap
        }

    def _aggregate_war_costs_by_party_sync(self, wars: List[Dict[str, Any]], home_ids: Set[int], away_ids: Set[int]) -> Dict[str, float]:
        """Aggregate numeric cost fields across wars, attributing to Home/Away parties.

        Home/Away are explicit party sets (attackers vs defenders input), not initial war sides.
        Returns keys like 'home_gas_used', 'away_gas_used', etc. Missing fields default to 0.
        """
        fields = [
            'gas_used', 'mun_used', 'alum_used', 'steel_used',
            'infra_destroyed', 'infra_destroyed_value', 'money_looted',
            'soldiers_lost', 'tanks_lost', 'aircraft_lost', 'ships_lost',
            'missiles_lost', 'nukes_lost',
            'gas_looted', 'mun_looted', 'alum_looted', 'steel_looted', 'food_looted',
            'coal_looted', 'oil_looted', 'uran_looted', 'iron_looted', 'baux_looted', 'lead_looted'
        ]
        totals: Dict[str, float] = {}
        for prefix in ('home', 'away'):
            for f in fields:
                totals[f"{prefix}_{f}"] = 0.0

        for w in wars or []:
            attacks = w.get('attacks') or []
            use_attacks = isinstance(attacks, list) and len(attacks) > 0

            try:
                war_att_id = int(w.get('att_id') or w.get('attid') or 0)
            except Exception:
                war_att_id = 0
            try:
                war_def_id = int(w.get('def_id') or w.get('defid') or 0)
            except Exception:
                war_def_id = 0
            try:
                war_att_alliance_id = int(w.get('att_alliance_id') or (w.get('attacker') or {}).get('alliance_id') or 0)
            except Exception:
                war_att_alliance_id = 0
            try:
                war_def_alliance_id = int(w.get('def_alliance_id') or (w.get('defender') or {}).get('alliance_id') or 0)
            except Exception:
                war_def_alliance_id = 0

            if use_attacks:
                for a in attacks:
                    try:
                        atk_id = int(a.get('att_id') or a.get('attid') or 0)
                    except Exception:
                        atk_id = 0
                    if atk_id and war_att_id and atk_id == war_att_id:
                        atk_alliance = war_att_alliance_id
                        def_alliance = war_def_alliance_id
                    elif atk_id and war_def_id and atk_id == war_def_id:
                        atk_alliance = war_def_alliance_id
                        def_alliance = war_att_alliance_id
                    else:
                        atk_alliance = war_att_alliance_id
                        def_alliance = war_def_alliance_id
                    atk_party = 'home' if atk_alliance in home_ids else ('away' if atk_alliance in away_ids else None)
                    def_party = 'home' if def_alliance in home_ids else ('away' if def_alliance in away_ids else None)
                    att_gas = float(a.get('att_gas_used', 0) or 0)
                    def_gas = float(a.get('def_gas_used', 0) or 0)
                    att_mun = float(a.get('att_mun_used', 0) or 0)
                    def_mun = float(a.get('def_mun_used', 0) or 0)
                    infra_lvl = float((a.get('infra_destroyed') if a.get('infra_destroyed') is not None else a.get('infradestroyed')) or 0)
                    infra_val = float(a.get('infra_destroyed_value', 0) or 0)
                    money_loot = float(
                        (a.get('money_stolen') if a.get('money_stolen') is not None else a.get('moneystolen'))
                        or a.get('money_looted') or 0
                    )
                    att_soldiers_lost = float(a.get('att_soldiers_lost', 0) or 0)
                    def_soldiers_lost = float(a.get('def_soldiers_lost', 0) or 0)
                    att_tanks_lost = float(a.get('att_tanks_lost', 0) or 0)
                    def_tanks_lost = float(a.get('def_tanks_lost', 0) or 0)
                    att_aircraft_lost = float(a.get('att_aircraft_lost', 0) or 0)
                    def_aircraft_lost = float(a.get('def_aircraft_lost', 0) or 0)
                    att_ships_lost = float(a.get('att_ships_lost', 0) or 0)
                    def_ships_lost = float(a.get('def_ships_lost', 0) or 0)
                    att_missiles_lost = float(a.get('att_missiles_lost', 0) or 0)
                    def_missiles_lost = float(a.get('def_missiles_lost', 0) or 0)
                    att_nukes_lost = float(a.get('att_nukes_lost', 0) or 0)
                    def_nukes_lost = float(a.get('def_nukes_lost', 0) or 0)
                    loot_gas = float(a.get('gasoline_looted', 0) or 0)
                    loot_mun = float(a.get('munitions_looted', 0) or 0)
                    loot_alum = float(a.get('aluminum_looted', 0) or 0)
                    loot_steel = float(a.get('steel_looted', 0) or 0)
                    loot_food = float(a.get('food_looted', 0) or 0)
                    loot_coal = float(a.get('coal_looted', 0) or 0)
                    loot_oil = float(a.get('oil_looted', 0) or 0)
                    loot_uran = float(a.get('uranium_looted', 0) or 0)
                    loot_iron = float(a.get('iron_looted', 0) or 0)
                    loot_baux = float(a.get('bauxite_looted', 0) or 0)
                    loot_lead = float(a.get('lead_looted', 0) or 0)
                    if atk_party:
                        totals[f"{atk_party}_gas_used"] += att_gas
                        totals[f"{atk_party}_mun_used"] += att_mun
                        totals[f"{atk_party}_money_looted"] += money_loot
                        totals[f"{atk_party}_gas_looted"] += loot_gas
                        totals[f"{atk_party}_mun_looted"] += loot_mun
                        totals[f"{atk_party}_alum_looted"] += loot_alum
                        totals[f"{atk_party}_steel_looted"] += loot_steel
                        totals[f"{atk_party}_food_looted"] += loot_food
                        totals[f"{atk_party}_coal_looted"] += loot_coal
                        totals[f"{atk_party}_oil_looted"] += loot_oil
                        totals[f"{atk_party}_uran_looted"] += loot_uran
                        totals[f"{atk_party}_iron_looted"] += loot_iron
                        totals[f"{atk_party}_baux_looted"] += loot_baux
                        totals[f"{atk_party}_lead_looted"] += loot_lead
                        totals[f"{atk_party}_soldiers_lost"] += att_soldiers_lost
                        totals[f"{atk_party}_tanks_lost"] += att_tanks_lost
                        totals[f"{atk_party}_aircraft_lost"] += att_aircraft_lost
                        totals[f"{atk_party}_ships_lost"] += att_ships_lost
                        totals[f"{atk_party}_missiles_lost"] += att_missiles_lost
                        totals[f"{atk_party}_nukes_lost"] += att_nukes_lost
                    if def_party:
                        totals[f"{def_party}_gas_used"] += def_gas
                        totals[f"{def_party}_mun_used"] += def_mun
                        totals[f"{def_party}_infra_destroyed"] += infra_lvl
                        totals[f"{def_party}_infra_destroyed_value"] += infra_val
                        totals[f"{def_party}_soldiers_lost"] += def_soldiers_lost
                        totals[f"{def_party}_tanks_lost"] += def_tanks_lost
                        totals[f"{def_party}_aircraft_lost"] += def_aircraft_lost
                        totals[f"{def_party}_ships_lost"] += def_ships_lost
                        totals[f"{def_party}_missiles_lost"] += def_missiles_lost
                        totals[f"{def_party}_nukes_lost"] += def_nukes_lost
            else:
                pass

        totals['war_count'] = float(len(wars or []))
        return totals

    async def aggregate_war_costs_by_party(self, wars: List[Dict[str, Any]], home_ids: Set[int], away_ids: Set[int]) -> Dict[str, float]:
        """Async wrapper for aggregating war costs."""
        return await asyncio.to_thread(self._aggregate_war_costs_by_party_sync, wars, home_ids, away_ids)

    def _calculate_nation_improvements_sync(self, nation: Dict[str, Any]) -> Dict[str, int]:
        improvements = {
            'coalpower': 0,
            'oilpower': 0,
            'nuclearpower': 0,
            'windpower': 0,
            'bauxitemine': 0,
            'coalmine': 0,
            'ironmine': 0,
            'leadmine': 0,
            'oilwell': 0,
            'uramine': 0,
            'farm': 0,
            'aluminumrefinery': 0,
            'steelmill': 0,
            'gasrefinery': 0,
            'munitionsfactory': 0,
            'barracks': 0,
            'factory': 0,
            'hangar': 0,
            'drydock': 0,
            'subway': 0,
            'supermarket': 0,
            'bank': 0,
            'shopping_mall': 0,
            'stadium': 0,
            'policestation': 0,
            'hospital': 0,
            'recyclingcenter': 0,
        }

        cities = nation.get('cities', [])
        for city in cities:
            if not isinstance(city, dict):
                continue

            improvements['coalpower'] += int(city.get('coal_power', 0) or 0)
            improvements['oilpower'] += int(city.get('oil_power', 0) or 0)
            improvements['nuclearpower'] += int(city.get('nuclear_power', 0) or 0)
            improvements['windpower'] += int(city.get('wind_power', 0) or 0)

            improvements['bauxitemine'] += int(city.get('bauxite_mine', 0) or 0)
            improvements['coalmine'] += int(city.get('coal_mine', 0) or 0)
            improvements['ironmine'] += int(city.get('iron_mine', 0) or 0)
            improvements['leadmine'] += int(city.get('lead_mine', 0) or 0)
            improvements['oilwell'] += int(city.get('oil_well', 0) or 0)
            improvements['uramine'] += int(city.get('uranium_mine', 0) or 0)
            improvements['farm'] += int(city.get('farm', 0) or 0)

            improvements['aluminumrefinery'] += int(city.get('aluminum_refinery', 0) or 0)
            improvements['steelmill'] += int(city.get('steel_mill', 0) or 0)
            improvements['gasrefinery'] += int(city.get('oil_refinery', 0) or 0)
            improvements['munitionsfactory'] += int(city.get('munitions_factory', 0) or 0)

            improvements['barracks'] += int(city.get('barracks', 0) or 0)
            improvements['factory'] += int(city.get('factory', 0) or 0)
            improvements['hangar'] += int(city.get('hangar', 0) or 0)
            improvements['drydock'] += int(city.get('drydock', 0) or 0)

            improvements['subway'] += int(city.get('subway', 0) or 0)
            improvements['supermarket'] += int(city.get('supermarket', 0) or 0)
            improvements['bank'] += int(city.get('bank', 0) or 0)
            improvements['shopping_mall'] += int(city.get('shopping_mall', 0) or 0)
            improvements['stadium'] += int(city.get('stadium', 0) or 0)
            improvements['policestation'] += int(city.get('police_station', 0) or 0)
            improvements['hospital'] += int(city.get('hospital', 0) or 0)
            improvements['recyclingcenter'] += int(city.get('recycling_center', 0) or 0)

        improvements['total_power'] = improvements['coalpower'] + improvements['oilpower'] + improvements['nuclearpower'] + improvements['windpower']
        improvements['total_improvements'] = sum(v for v in improvements.values() if isinstance(v, int))
        return improvements

    def _calculate_days_inactive_sync(self, last_active_str: str) -> int:
        """Synchronously calculates the number of days a nation has been inactive."""
        if not last_active_str or not isinstance(last_active_str, str):
            return 0
        try:
            # Handle different timestamp formats, assuming UTC
            if last_active_str.endswith('+00:00'):
                last_active = datetime.fromisoformat(last_active_str.replace('+00:00', '')).replace(tzinfo=timezone.utc)
            else:
                last_active = datetime.fromisoformat(last_active_str).replace(tzinfo=timezone.utc)
            
            delta = datetime.now(timezone.utc) - last_active
            return delta.days
        except (ValueError, TypeError):
            self.logger.warning(f"Could not parse date string: {last_active_str}")
            return 0

    async def calculate_days_inactive(self, last_active_str: str) -> int:
        """Async wrapper to calculate days of inactivity from a timestamp string."""
        return await asyncio.to_thread(self._calculate_days_inactive_sync, last_active_str)
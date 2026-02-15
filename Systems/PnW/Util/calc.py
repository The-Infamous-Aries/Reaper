from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime, timezone, timedelta
import logging
import sys
import os
import asyncio

# Add parent directory to path for config import
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

class AllianceCalculator:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._debug_project_logging = False  # Disable verbose project logging by default

    def _log_error(self, error_msg: str, exception: Exception = None, context: str = ""):
        if exception:
            self.logger.error(f"{context}: {error_msg} - {str(exception)}")
        else:
            self.logger.error(f"{context}: {error_msg}")
    
    def _validate_input(self, data: Any, expected_type: type, field_name: str = "data") -> bool:
        if not isinstance(data, expected_type):
            self.logger.warning(f"Input validation failed: {field_name} expected {expected_type}, got {type(data)}")
            return False
        return True
    
    def _safe_get(self, data: dict, key: str, default: Any = None, expected_type: type = None) -> Any:
        try:
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
             
    def _calculate_improvements_data_sync(self, nations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Synchronous implementation of improvement calculations."""
        try:
            # Filter only VM/APPLICANT, include 14+ inactive
            active_nations = [n for n in nations if (self._safe_get(n, 'vacation_mode_turns', 0, int) == 0 and self._safe_get(n, 'alliance_position', '', str).upper() != 'APPLICANT')]
            improvements = {
                'coalpower': 0, 'oilpower': 0, 'nuclearpower': 0, 'windpower': 0,
                'oilwell': 0, 'coalmine': 0, 'uramine': 0, 'ironmine': 0, 'bauxitemine': 0, 'leadmine': 0, 'farm': 0,
                'gasrefinery': 0, 'steelmill': 0, 'aluminumrefinery': 0, 'munitionsfactory': 0,
                'policestation': 0, 'hospital': 0, 'bank': 0, 'supermarket': 0,
                'shopping_mall': 0, 'stadium': 0, 'subway': 0, 'recyclingcenter': 0,
                'barracks': 0, 'factory': 0, 'hangar': 0, 'drydock': 0
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
            total_improvements = sum(improvements.values())
            avg_per_city = total_improvements / total_cities if total_cities > 0 else 0
            self.logger.info(f"Improvements calculated: {improvements['barracks']} barracks, {improvements['factory']} factories, "
                           f"{improvements['hangar']} hangars, {improvements['drydock']} drydocks across {total_cities} cities "
                           f"({len(active_nations)} active nations)")
            improvements.update({
                'total_power': total_power,
                'total_improvements': total_improvements,
                'total_cities': total_cities,
                'avg_per_city': avg_per_city,
                'active_nations': len(active_nations)
            })            
            return improvements           
        except Exception as e:
            self._log_error(f"Error calculating improvements data: {e}", e, "_calculate_improvements_data_sync")
            return {
                'coalpower': 0, 'oilpower': 0, 'nuclearpower': 0, 'windpower': 0,
                'oilwell': 0, 'coalmine': 0, 'uramine': 0, 'ironmine': 0, 'bauxitemine': 0, 'leadmine': 0, 'farm': 0,
                'gasrefinery': 0, 'steelmill': 0, 'aluminumrefinery': 0, 'munitionsfactory': 0, 'factory': 0,
                'policestation': 0, 'hospital': 0, 'bank': 0, 'supermarket': 0, 'shopping_mall': 0, 'stadium': 0, 'subway': 0, 'recyclingcenter': 0,
                'barracks': 0, 'hangar': 0, 'drydock': 0,
                'total_power': 0, 'total_improvements': 0, 'total_cities': 0, 'avg_per_city': 0, 'active_nations': 0
            }

    async def calculate_improvements_data(self, nations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Async wrapper for calculating improvements data."""
        return await asyncio.to_thread(self._calculate_improvements_data_sync, nations)

    async def calculate_improvements_data_multi_alliance(self, alliance_data: Dict[str, List[Dict[str, Any]]], selected_alliances: List[str] = None) -> Dict[str, Any]:
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
            total_improvements = {
                'coalpower': 0, 'oilpower': 0, 'nuclearpower': 0, 'windpower': 0,
                'oilwell': 0, 'coalmine': 0, 'uramine': 0, 'ironmine': 0, 'bauxitemine': 0, 'leadmine': 0, 'farm': 0,
                'gasrefinery': 0, 'steelmill': 0, 'aluminumrefinery': 0, 'munitionsfactory': 0, 'factory': 0,
                'policestation': 0, 'hospital': 0, 'bank': 0, 'supermarket': 0, 'shopping_mall': 0, 'stadium': 0, 'subway': 0, 'recyclingcenter': 0,
                'barracks': 0, 'hangar': 0, 'drydock': 0,
                'total_power': 0, 'total_improvements': 0, 'total_cities': 0, 'avg_per_city': 0, 'active_nations': 0
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
                for improvement, count in alliance_improvements.items():
                    if improvement in total_improvements:
                        total_improvements[improvement] += count
                
                # Count active nations for this alliance
                total_nations_processed += alliance_improvements.get('active_nations', 0)
            
            # Recalculate totals and averages
            total_improvements['total_power'] = (total_improvements['coalpower'] + total_improvements['oilpower'] + 
                                               total_improvements['nuclearpower'] + total_improvements['windpower'])
            total_improvements['total_improvements'] = sum(v for k, v in total_improvements.items() 
                                                         if k not in ['total_power', 'total_improvements', 'total_cities', 'avg_per_city', 'active_nations'])
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

    async def calculate_alliance_statistics_multi_alliance(self, alliance_data: Dict[str, List[Dict[str, Any]]], selected_alliances: List[str] = None) -> Dict[str, Any]:
        """
        Calculate comprehensive alliance statistics for multiple alliances efficiently.
        """
        try:
            if not alliance_data:
                self.logger.warning("calculate_alliance_statistics_multi_alliance: No alliance data provided")
                return {}
            
            # Combine nations from selected alliances (avoiding duplicates)
            # Offload the combination logic if it's heavy (iterating thousands of nations)
            combined_nations = await asyncio.to_thread(self._combine_alliance_nations_for_calc_sync, alliance_data, selected_alliances)
            
            if not combined_nations:
                self.logger.warning("calculate_alliance_statistics_multi_alliance: No nations found in selected alliances")
                return {}
            
            # Use async alliance statistics calculation
            return await self.calculate_alliance_statistics(combined_nations)
            
        except Exception as e:
            self._log_error("Error calculating multi-alliance statistics", e, "calculate_alliance_statistics_multi_alliance")
            return {}

    def _combine_alliance_nations_for_calc_sync(self, alliance_data: Dict[str, List[Dict[str, Any]]], selected_alliances: List[str] = None) -> List[Dict[str, Any]]:
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

    def _calculate_alliance_statistics_sync(self, nations: List[Dict[str, Any]]) -> Dict[str, Any]:
        stats = {
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
            
            production_data = self.calculate_military_purchase_limits(nation)
            stats['production_capacity']['total_barracks'] += production_data.get('total_barracks', 0)
            stats['production_capacity']['total_factories'] += production_data.get('total_factories', 0)
            stats['production_capacity']['total_hangars'] += production_data.get('total_hangars', 0)
            stats['production_capacity']['total_drydocks'] += production_data.get('total_drydocks', 0)
            stats['production_capacity']['daily_soldiers'] += production_data.get('soldiers', 0)
            stats['production_capacity']['daily_tanks'] += production_data.get('tanks', 0)
            stats['production_capacity']['daily_aircraft'] += production_data.get('aircraft', 0)
            stats['production_capacity']['daily_ships'] += production_data.get('ships', 0)
            stats['production_capacity']['daily_missiles'] += production_data.get('missiles', 0)
            stats['production_capacity']['daily_nukes'] += production_data.get('nukes', 0)
            stats['production_capacity']['max_soldiers'] += production_data.get('soldiers_max', 0)
            stats['production_capacity']['max_tanks'] += production_data.get('tanks_max', 0)
            stats['production_capacity']['max_aircraft'] += production_data.get('aircraft_max', 0)
            stats['production_capacity']['max_ships'] += production_data.get('ships_max', 0)
            
            if self.has_project(nation, 'Missile Launch Pad'):
                stats['production_capacity']['max_missiles'] += 50           
            if self.has_project(nation, 'Nuclear Research Facility'):
                stats['production_capacity']['max_nukes'] += 50        
        return stats
    
    async def calculate_alliance_statistics(self, nations: List[Dict[str, Any]]) -> Dict[str, Any]:
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
            
            data = {
                'current_soldiers': 0, 'current_tanks': 0, 'current_aircraft': 0, 'current_ships': 0,
                'current_missiles': 0, 'current_nukes': 0,
                'max_soldiers': 0, 'max_tanks': 0, 'max_aircraft': 0, 'max_ships': 0,
                'daily_soldiers': 0, 'daily_tanks': 0, 'daily_aircraft': 0, 'daily_ships': 0,
                'daily_missiles': 0, 'daily_nukes': 0,
                'total_cities': 0, 'total_score': 0,
                'max_soldier_days': 0, 'max_tank_days': 0, 'max_aircraft_days': 0, 'max_ship_days': 0,
                'max_soldier_nation': "", 'max_tank_nation': "", 'max_aircraft_nation': "", 'max_ship_nation': ""
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
                    
                    if days > data[key_days]:
                        data[key_days] = days
                        data[key_nation] = nation.get('nation_name', 'Unknown')
                        
                    data[f'daily_{unit}'] += daily
                    data[f'max_{unit}'] += nation_max[unit]

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
                total_hangars += city.get('airforcebase', 0)
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
    
    def calculate_building_ratios(self, nation: Dict[str, Any]) -> Dict[str, float]:
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

    def calculate_military_advantage(self, nation: Dict[str, Any]) -> Dict[str, Any]:
        purchase_limits = self.calculate_military_purchase_limits(nation)
        current_military = {
            'soldiers': nation.get('soldiers', 0),
            'tanks': nation.get('tanks', 0),
            'aircraft': nation.get('aircraft', 0),
            'ships': nation.get('ships', 0),
            'missiles': nation.get('missiles', 0),
            'nukes': nation.get('nukes', 0)
        }
        cities_list = nation.get('cities', [])
        if isinstance(cities_list, list):
            num_cities = nation.get('num_cities', len(cities_list))
        else:
            num_cities = nation.get('num_cities', 0)       
        max_soldiers_per_city = 5 * 3000
        max_tanks_per_city = 5 * 250   
        max_aircraft_per_city = 5 * 15  
        max_ships_per_city = 3 * 5        
        theoretical_max_soldiers = num_cities * max_soldiers_per_city
        theoretical_max_tanks = num_cities * max_tanks_per_city
        theoretical_max_aircraft = num_cities * max_aircraft_per_city
        theoretical_max_ships = num_cities * max_ships_per_city
        soldier_percentage = (current_military['soldiers'] / theoretical_max_soldiers * 100) if theoretical_max_soldiers > 0 else 0
        tank_percentage = (current_military['tanks'] / theoretical_max_tanks * 100) if theoretical_max_tanks > 0 else 0
        aircraft_percentage = (current_military['aircraft'] / theoretical_max_aircraft * 100) if theoretical_max_aircraft > 0 else 0
        ship_percentage = (current_military['ships'] / theoretical_max_ships * 100) if theoretical_max_ships > 0 else 0
        current_ground_score = current_military['soldiers'] + (current_military['tanks'] * 2)
        theoretical_max_ground_score = theoretical_max_soldiers + (theoretical_max_tanks * 2)
        ground_percentage = (current_ground_score / theoretical_max_ground_score * 100) if theoretical_max_ground_score > 0 else 0
        heavy_threshold_percentage = 80.0   
        is_heavy_ground = ground_percentage > heavy_threshold_percentage
        is_heavy_air = aircraft_percentage > heavy_threshold_percentage
        is_heavy_naval = ship_percentage > heavy_threshold_percentage
        cities_data = nation.get('cities', [])
        num_cities = len(cities_data) if cities_data else nation.get('num_cities', 0)      
        high_ground_build = False
        high_air_build = False
        high_naval_build = False        
        if num_cities > 0 and cities_data:
            total_barracks = sum(city.get('barracks', 0) for city in cities_data)
            total_factories = sum(city.get('factory', 0) for city in cities_data)
            total_airforcebases = sum(city.get('airforcebase', 0) for city in cities_data)
            total_drydocks = sum(city.get('drydock', 0) for city in cities_data)
            avg_barracks = total_barracks / num_cities
            avg_factories = total_factories / num_cities
            avg_airforcebases = total_airforcebases / num_cities
            avg_drydocks = total_drydocks / num_cities
            high_ground_build = avg_barracks >= 4.5 and avg_factories >= 4.5
            high_air_build = avg_airforcebases >= 4.5
            high_naval_build = avg_drydocks >= 2.5       
        high_ground_purchase = high_ground_build
        high_air_purchase = high_air_build
        high_naval_purchase = high_naval_build
        advantages = []
        has_ground_advantage = high_ground_purchase
        has_air_advantage = high_air_purchase
        has_naval_advantage = high_naval_purchase        
        if has_ground_advantage:
            advantages.append("Ground Advantage")
        if has_air_advantage:
            advantages.append("Air Advantage")
        if has_naval_advantage:
            advantages.append("Naval Advantage")
        can_missile = self.has_project(nation, 'Missile Launch Pad')
        can_nuke = self.has_project(nation, 'Nuclear Research Facility')        
        if can_missile:
            advantages.append("Missile Capable")
        if can_nuke:
            advantages.append("Nuclear Capable")
        
        nation_id = nation.get('nation_id') or nation.get('id', '')
        nation_score = nation.get('score', 0)
        min_attack_score = nation_score * 0.75 
        max_attack_score = nation_score * 2.5       
        return {
            'advantages': advantages,
            'purchase_limits': purchase_limits,
            'current_military': current_military,
            'can_missile': can_missile,
            'can_nuke': can_nuke,
            'has_ground_advantage': has_ground_advantage,
            'has_air_advantage': has_air_advantage,
            'has_naval_advantage': has_naval_advantage,
            'attack_range': {
                'min_score': min_attack_score,
                'max_score': max_attack_score,
                'nation_score': nation_score
            },
            'military_composition': {
                'current_soldiers': current_military['soldiers'],
                'current_tanks': current_military['tanks'],
                'current_aircraft': current_military['aircraft'],
                'current_ships': current_military['ships'],
                'theoretical_max_soldiers': theoretical_max_soldiers,
                'theoretical_max_tanks': theoretical_max_tanks,
                'theoretical_max_aircraft': theoretical_max_aircraft,
                'theoretical_max_ships': theoretical_max_ships,
                'soldier_percentage': soldier_percentage,
                'tank_percentage': tank_percentage,
                'aircraft_percentage': aircraft_percentage,
                'ship_percentage': ship_percentage,
                'ground_percentage': ground_percentage,
                'current_ground_score': current_ground_score,
                'theoretical_max_ground_score': theoretical_max_ground_score,
                'is_heavy_ground': is_heavy_ground,
                'is_heavy_air': is_heavy_air,
                'is_heavy_naval': is_heavy_naval,
                'high_ground_purchase': high_ground_purchase,
                'high_air_purchase': high_air_purchase,
                'high_naval_purchase': high_naval_purchase,
                'heavy_threshold_percentage': heavy_threshold_percentage,
                'is_psycho': "🪓 Psycho" in advantages,
                'is_scary': "💀 Scary" in advantages,
                'is_primal': "👑 Primal" in advantages
            }
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

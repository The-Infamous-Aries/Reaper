import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
import re
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
import sys
import logging
import traceback

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from Systems.PnW.Util.query import create_query_instance
from config import PANDW_API_KEY, HOME_ALLIANCE_ID
from Systems.Functions.user_data_manager import UserDataManager

from Systems.PnW.Util.calc import AllianceCalculator

# Import AllianceManager to refresh bloc data prior to fetching attackers
AllianceManager = None

# Role checks removed: allow all users to run commands without gating

class DestroyCog(commands.Cog):
    """Cog for managing war destruction commands."""
    
    def __init__(self, bot: commands.Bot):
        try:
            self.bot = bot
            self.api_key = PANDW_API_KEY
            self.user_data_manager = UserDataManager()
            self.home_alliance_id = HOME_ALLIANCE_ID
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
            try:
                self.query_instance = create_query_instance()
                self.logger.info("Centralized query instance initialized successfully")
                if hasattr(self.query_instance, 'cache_ttl_seconds'):
                    self.query_instance.cache_ttl_seconds = 3600
            except Exception as e:
                self.logger.error(f"Failed to initialize query instance: {e}")
                self.query_instance = None

            try:
                self.calculator = AllianceCalculator()
                self.logger.info("AllianceCalculator initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize AllianceCalculator: {e}")
                self.calculator = None
        except Exception as e:
            print(f"Error initializing DestroyCog: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            self.bot = bot
            self.api_key = PANDW_API_KEY
            self.user_data_manager = UserDataManager()
            self.home_alliance_id = HOME_ALLIANCE_ID
            self.error_count = 0
            self.max_errors = 100
            self.query_instance = None
            self.calculator = None 
                
    async def get_alliance_nations(self, alliance_id: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Get alliance nations data from individual alliance files or API.
        
        Args:
            alliance_id: The alliance ID to fetch data for
            force_refresh: Whether to force refresh from API
            
        Returns:
            List of nation dictionaries or empty list if not found
        """
        try:
            alliance_key = f"alliance_{alliance_id}"
            
            # Try to get from individual alliance file first
            alliance_data = await self.user_data_manager.get_json_data(alliance_key, {})
            
            # Support new dict format and legacy list format
            cached_nations: List[Dict[str, Any]] = []
            if isinstance(alliance_data, dict):
                cached_nations = alliance_data.get('nations', []) or []
            elif isinstance(alliance_data, list):
                cached_nations = alliance_data
            
            if cached_nations and not force_refresh:
                self.logger.info(f"get_alliance_nations: Retrieved {len(cached_nations)} nations from file for alliance {alliance_id}")
                return cached_nations
            
            # If we get here, file is missing or we need to refresh
            self.logger.info(f"get_alliance_nations: File missing or refresh needed for alliance {alliance_id}, fetching from API")
            
            # Try to use query instance if available
            if self.query_instance:
                nations = await self.query_instance.get_alliance_nations(alliance_id, bot=self.bot, force_refresh=force_refresh)
                
                # Store in individual alliance file for future use
                if nations:
                    try:
                        save_payload = {
                            'nations': nations,
                            'alliance_id': str(alliance_id),
                            'last_updated': datetime.now().isoformat(),
                            'total_nations': len(nations)
                        }
                        await self.user_data_manager.save_json_data(alliance_key, save_payload)
                        self.logger.info(f"get_alliance_nations: Stored {len(nations)} nations in file for alliance {alliance_id}")
                    except Exception as file_error:
                        self.logger.error(f"Error storing alliance data in file: {file_error}")
                
                return nations or []
            
            # Fallback to empty list if all methods fail
            self.logger.warning(f"get_alliance_nations: Failed to get nations for alliance {alliance_id}")
            return []
            
        except Exception as e:
            self._log_error(f"Error in get_alliance_nations for alliance {alliance_id}", e, "get_alliance_nations")
            return []
    
    def _log_error(self, error_msg: str, exception: Exception = None, context: str = ""):
        """
        Centralized error logging with tracking.
        
        Args:
            error_msg: Error message to log
            exception: Optional exception object
            context: Optional context information
        """
        try:
            self.error_count += 1
            
            # Reset error count if it gets too high
            if self.error_count > self.max_errors:
                self.error_count = 1
                self.logger.warning(f"Error count reset after reaching {self.max_errors}")
            
            # Format error message
            full_msg = f"[Error #{self.error_count}] {error_msg}"
            if context:
                full_msg += f" (Context: {context})"
            
            # Log the error
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(full_msg)
                if exception:
                    self.logger.error(f"Exception details: {str(exception)}")
                    self.logger.error(f"Traceback: {traceback.format_exc()}")
            else:
                # Fallback to print if logger not available
                print(full_msg)
                if exception:
                    print(f"Exception details: {str(exception)}")
                    print(f"Traceback: {traceback.format_exc()}")
                    
        except Exception as log_error:
            # Last resort error handling
            print(f"Error in error logging: {log_error}")
            print(f"Original error: {error_msg}")
    
    def _validate_input(self, data: Any, expected_type: type, field_name: str = "data") -> bool:
        """
        Validate input data type and log errors if invalid.
        
        Args:
            data: Data to validate
            expected_type: Expected data type
            field_name: Name of the field for error messages
            
        Returns:
            True if valid, False otherwise
        """
        try:
            if not isinstance(data, expected_type):
                self._log_error(f"Invalid {field_name} type. Expected {expected_type.__name__}, got {type(data).__name__}")
                return False
            return True
        except Exception as e:
            self._log_error(f"Error validating {field_name}", e)
            return False
    
    def _safe_get(self, data: Dict[str, Any], key: str, default: Any = None, expected_type: type = None) -> Any:
        """
        Safely get value from dictionary with type checking.
        
        Args:
            data: Dictionary to get value from
            key: Key to retrieve
            default: Default value if key not found
            expected_type: Expected type for validation
            
        Returns:
            Value from dictionary or default
        """
        try:
            if not isinstance(data, dict):
                self._log_error(f"Expected dict for _safe_get, got {type(data).__name__}")
                return default
            
            value = data.get(key, default)
            
            if expected_type and value is not None and not isinstance(value, expected_type):
                self._log_error(f"Invalid type for key '{key}'. Expected {expected_type.__name__}, got {type(value).__name__}")
                return default
            
            return value
            
        except Exception as e:
            self._log_error(f"Error in _safe_get for key '{key}'", e)
            return default

    async def parse_target_input(self, target_data: str) -> Tuple[Optional[str], str]:
        """
        Parse target input and determine the type and value.
        
        Args:
            target_data: Input string containing nation name, leader name, nation ID, or nation link
            
        Returns:
            Tuple of (nation_id, input_type) where input_type is one of:
            'nation_id', 'nation_name', 'leader_name', 'nation_link'
        """
        try:
            target_data = target_data.strip()
            
            # Check if it's a nation link
            link_patterns = [
                r'https?://politicsandwar\.com/nation/id=(\d+)',
                r'https?://www\.politicsandwar\.com/nation/id=(\d+)',
                r'politicsandwar\.com/nation/id=(\d+)',
                r'www\.politicsandwar\.com/nation/id=(\d+)'
            ]
            
            for pattern in link_patterns:
                try:
                    match = re.search(pattern, target_data)
                    if match:
                        return match.group(1), 'nation_link'
                except Exception as e:
                    self.logger.warning(f"Error processing link pattern {pattern}: {str(e)}")
                    continue
            
            # Check if it's a pure nation ID (numeric)
            if target_data.isdigit():
                return target_data, 'nation_id'
            
            # If it contains spaces or special characters, likely a nation name
            if ' ' in target_data or any(char in target_data for char in ['-', '_', '.', "'"]):
                return None, 'nation_name'
            
            # Otherwise, assume it's a leader name
            return None, 'leader_name'
        except Exception as e:
            self._log_error(f"Error in parse_target_input: {str(e)}", e, "parse_target_input")
            return None, 'leader_name'

    async def fetch_target_nation(self, target_data: str, input_type: str) -> Optional[Dict[str, Any]]:
        """
        Fetch comprehensive target nation data from P&W API with military analysis and enhanced query utilization.
        
        Args:
            target_data: The target identifier
            input_type: Type of input ('nation_id', 'nation_name', 'leader_name', 'nation_link')
            
        Returns:
            Nation data dictionary with comprehensive military analysis or None if not found
        """
        try:
            # Input validation
            if not self._validate_input(target_data, str, "target_data"):
                return None
            
            if not self._validate_input(input_type, str, "input_type"):
                return None
            
            if not target_data.strip():
                self._log_error("Empty target_data provided", context="fetch_target_nation")
                return None
            
            valid_input_types = ['nation_id', 'nation_name', 'leader_name', 'nation_link']
            if input_type not in valid_input_types:
                self._log_error(f"Invalid input_type: {input_type}. Must be one of {valid_input_types}", context="fetch_target_nation")
                return None
            
            # Use centralized query instance
            if not hasattr(self, 'query_instance') or self.query_instance is None:
                self._log_error("Query instance not available", context="fetch_target_nation")
                return None
            
            self.logger.info(f"Fetching target nation data for {input_type}: {target_data}")
            
            # Use appropriate method from query instance based on input type
            target_nation = None
            try:
                if input_type == 'nation_id' or input_type == 'nation_link':
                    # For nation ID, we already have the ID from parsing
                    if input_type == 'nation_link':
                        nation_id = target_data  # This is already extracted from the link
                    else:
                        nation_id = target_data
                    target_nation = await self.query_instance.get_nation_by_id(nation_id)
                elif input_type == 'nation_name':
                    target_nation = await self.query_instance.get_nation_by_name(target_data)
                elif input_type == 'leader_name':
                    target_nation = await self.query_instance.get_nation_by_leader(target_data)
                
                if not target_nation:
                    self.logger.info(f"No nation found for {input_type}: {target_data}")
                    return None
                
                # Enhanced data utilization - extract and process war history data
                try:
                    # Process war data for strategic insights
                    offensive_wars = target_nation.get('offensive_wars', [])
                    defensive_wars = target_nation.get('defensive_wars', [])
                    
                    # Calculate war activity metrics
                    total_wars = len(offensive_wars) + len(defensive_wars)
                    recent_wars = [war for war in (offensive_wars + defensive_wars) 
                                  if war.get('date', '') and self._is_recent_war(war.get('date', ''))]
                    
                    target_nation['war_activity'] = {
                        'total_wars': total_wars,
                        'recent_wars': len(recent_wars),
                        'offensive_wars': len(offensive_wars),
                        'defensive_wars': len(defensive_wars),
                        'war_activity_score': min(10, len(recent_wars))  # 0-10 scale
                    }
                    
                    # Extract casualty data for military assessment
                    casualty_data = {
                        'soldier_casualties': target_nation.get('soldier_casualties', 0) or 0,
                        'tank_casualties': target_nation.get('tank_casualties', 0) or 0,
                        'aircraft_casualties': target_nation.get('aircraft_casualties', 0) or 0,
                        'ship_casualties': target_nation.get('ship_casualties', 0) or 0,
                        'total_casualties': (target_nation.get('soldier_casualties', 0) or 0) +
                                           (target_nation.get('tank_casualties', 0) or 0) +
                                           (target_nation.get('aircraft_casualties', 0) or 0) +
                                           (target_nation.get('ship_casualties', 0) or 0)
                    }
                    target_nation['casualty_analysis'] = casualty_data
                    
                except Exception as e:
                    self._log_error("Error processing war history data", e, "fetch_target_nation")
                    target_nation['war_activity'] = {'total_wars': 0, 'recent_wars': 0, 'war_activity_score': 0}
                    target_nation['casualty_analysis'] = {}
                
                # Add comprehensive military analysis
                try:
                    target_nation['military_analysis'] = self.calculate_target_military_analysis(target_nation)
                    self.logger.info(f"Successfully fetched and analyzed nation: {target_nation.get('nation_name', 'Unknown')}")
                except Exception as e:
                    self._log_error("Error calculating military analysis", e, "fetch_target_nation")
                    target_nation['military_analysis'] = {}
                
                return target_nation
                
            except Exception as e:
                self._log_error("Error fetching nation data from query instance", e, "fetch_target_nation")
                return None
                
        except Exception as e:
            self._log_error("Unexpected error in fetch_target_nation", e, "fetch_target_nation")
            return None

    def load_blitz_parties(self) -> List[Dict[str, Any]]:
        """
        Load the most recent blitz party data from user_data_manager.
        
        Returns:
            List of blitz party dictionaries
        """
        try:
            return self.user_data_manager.get_saved_blitz_parties()
        except Exception as e:
            self._log_error(f"Error loading blitz parties: {str(e)}", e, "load_blitz_parties")
            return []

    def calculate_target_military_analysis(self, nation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate comprehensive military analysis for a target nation using calc.py logic.
        
        Args:
            nation: Nation data dictionary
            
        Returns:
            Military analysis dictionary matching blitz.py structure
        """
        try:
            # Use AllianceCalculator from calc.py to calculate military analysis
            if not self.calculator:
                self._log_error("AllianceCalculator not available for military analysis calculation", context="calculate_target_military_analysis")
                return self._get_default_target_military_analysis()
            
            # Get military analysis from calc.py
            military_analysis = self.calculator.calculate_military_advantage(nation)
            
            # Transform the data to match the expected format for destroy.py
            # The calc.py function returns a more comprehensive structure, so we need to extract the relevant parts
            
            return {
                'advantages': military_analysis.get('advantages', []),
                'purchase_limits': military_analysis.get('purchase_limits', {}),
                'current_military': military_analysis.get('current_military', {}),
                'can_missile': military_analysis.get('can_missile', False),
                'can_nuke': military_analysis.get('can_nuke', False),
                'has_ground_advantage': military_analysis.get('has_ground_advantage', False),
                'has_air_advantage': military_analysis.get('has_air_advantage', False),
                'has_naval_advantage': military_analysis.get('has_naval_advantage', False),
                'attack_range': military_analysis.get('attack_range', {}),
                'military_composition': military_analysis.get('military_composition', {}),
                'strategic_capabilities': military_analysis.get('strategic_capabilities', {
                    'missiles': False,
                    'nukes': False,
                    'projects': {}
                }),
                'military_research': military_analysis.get('military_research', {})
            }
            
        except Exception as e:
            self._log_error("Unexpected error in target military analysis calculation", e, "calculate_target_military_analysis")
            return self._get_default_target_military_analysis()
    
    def _get_default_target_military_analysis(self) -> Dict[str, Any]:
        """Return default target military analysis structure for error cases"""
        return {
            'advantages': [],
            'purchase_limits': {},
            'current_military': {},
            'can_missile': False,
            'can_nuke': False,
            'has_ground_advantage': False,
            'has_air_advantage': False,
            'has_naval_advantage': False,
            'attack_range': {},
            'military_composition': {},
            'strategic_capabilities': {
                'missiles': False,
                'nukes': False,
                'projects': {}
            },
            'military_research': {}
        }
    
    def _extract_nation_id_from_link(self, link_or_id: str) -> Optional[str]:
        """
        Extract nation ID from a Politics and War nation link.
        
        Args:
            link_or_id: String that might be a nation link or just an ID
            
        Returns:
            Nation ID if found in link, None if not a link or invalid
        """
        try:
            link_or_id = link_or_id.strip()
            
            # If it's just digits, assume it's already an ID
            if link_or_id.isdigit():
                return link_or_id
            
            # Check if it's a nation link and extract ID
            link_patterns = [
                r'https?://politicsandwar\.com/nation/id=(\d+)',
                r'https?://www\.politicsandwar\.com/nation/id=(\d+)',
                r'politicsandwar\.com/nation/id=(\d+)',
                r'www\.politicsandwar\.com/nation/id=(\d+)'
            ]
            
            for pattern in link_patterns:
                try:
                    match = re.search(pattern, link_or_id)
                    if match:
                        return match.group(1)
                except Exception as e:
                    self.logger.warning(f"Error processing link pattern {pattern}: {str(e)}")
                    continue
            
            # If no patterns matched, return None
            return None
            
        except Exception as e:
            self._log_error(f"Error extracting nation ID from link: {str(e)}", e, "_extract_nation_id_from_link")
            return None

    def _is_recent_war(self, war_date: str) -> bool:
        """Check if a war date is within the last 30 days."""
        try:
            from datetime import datetime, timedelta
            
            # Parse the war date (assuming ISO format or similar)
            war_datetime = datetime.fromisoformat(war_date.replace('Z', '+00:00'))
            current_time = datetime.now(war_datetime.timezone if hasattr(war_datetime, 'timezone') else None)
            
            # Check if war is within last 30 days
            thirty_days_ago = current_time - timedelta(days=30)
            return war_datetime >= thirty_days_ago
            
        except Exception as e:
            self.logger.warning(f"Error parsing war date '{war_date}': {e}")
            # If we can't parse the date, assume it's not recent to avoid false positives
            return False

    def calculate_combat_score(self, nation: Dict[str, Any]) -> float:
        """
        Calculate combat score for a nation.
        
        Args:
            nation: Nation data dictionary
            
        Returns:
            Combat score as float
        """
        try:
            # Basic combat score calculation
            soldiers = nation.get('soldiers', 0)
            tanks = nation.get('tanks', 0) * 3
            aircraft = nation.get('aircraft', 0) * 4
            ships = nation.get('ships', 0) * 6
            
            return soldiers + tanks + aircraft + ships
            
        except Exception as e:
            self._log_error(f"Error calculating combat score: {str(e)}", e, "calculate_combat_score")
            return 0.0

    def has_project(self, nation: Dict[str, Any], project_name: str) -> bool:
        """Check if a nation has a specific project.
        Supports both human-readable names (e.g., 'Missile Launch Pad') and
        API field names (e.g., 'missile_launch_pad'). Prefers boolean fields
        returned by our GraphQL queries and falls back to scanning the
        projects list if present.
        """
        try:
            # Map display names to API boolean fields
            name_to_field = {
                'Iron Dome': 'iron_dome',
                'Missile Launch Pad': 'missile_launch_pad',
                'Nuclear Research Facility': 'nuclear_research_facility',
                'Nuclear Launch Facility': 'nuclear_launch_facility',
                'Vital Defense System': 'vital_defense_system',
                'Propaganda Bureau': 'propaganda_bureau',
                'Military Research Center': 'military_research_center',
                'Space Program': 'space_program',
            }
            field_set = set(name_to_field.values())

            # Determine the API field key to check
            if project_name in name_to_field:
                field_key = name_to_field[project_name]
                display_name = project_name
            elif project_name in field_set:
                field_key = project_name
                # Recover a reasonable display name from mapping or fallback
                display_name = next((k for k, v in name_to_field.items() if v == project_name), project_name.replace('_', ' ').title())
            else:
                # Unknown project identifier; try fallback only
                field_key = None
                display_name = project_name

            # Prefer boolean field on the nation (from GraphQL)
            if field_key is not None:
                value = nation.get(field_key, False)
                if isinstance(value, bool):
                    return value

            # Fallback: scan the projects list if provided as names/objects
            projects = nation.get('projects', [])
            if isinstance(projects, list):
                for project in projects:
                    if isinstance(project, str):
                        if display_name.lower() in project.lower():
                            return True
                    elif isinstance(project, dict):
                        project_obj_name = str(project.get('name', ''))
                        if display_name.lower() in project_obj_name.lower():
                            return True

            # If projects is an int or anything else, we cannot reliably infer
            return False
        except Exception as e:
            self._log_error(f"Error checking project {project_name}: {str(e)}", e, "has_project")
            return False


    def _seconds_since_last_active(self, nation: Dict[str, Any]) -> Optional[int]:
        try:
            last_active = nation.get('last_active')
            if not last_active:
                return None
            from datetime import datetime
            dt = None
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
                            return None
            if not dt:
                return None
            now = datetime.utcnow() if dt.tzinfo is None else datetime.now(dt.tzinfo)
            delta = now - dt
            secs = int(delta.total_seconds())
            if secs < 0:
                return 0
            return secs
        except Exception:
            return None

    def _warchest_level(self, nation: Dict[str, Any]) -> int:
        gasoline = nation.get('gasoline', 0) or 0
        munitions = nation.get('munitions', 0) or 0
        min_resource = min(gasoline, munitions)
        if min_resource >= 10000:
            return 5
        elif min_resource >= 5000:
            return 4
        elif min_resource >= 3750:
            return 3
        elif min_resource >= 2500:
            return 2
        elif min_resource >= 1250:
            return 1
        else:
            return 0
 
    def validate_attack_range(self, attacker_score: float, defender_score: float) -> bool:
        """Validate if attacker can attack defender based on score range (-25% to +150%)."""
        try:
            # Correct war range: attacker can hit targets from 75% to 250% of their score
            # (-25% to +150% relative to attacker)
            if attacker_score <= 0:
                return False

            min_range = attacker_score * 0.75  # -25%
            max_range = attacker_score * 2.5   # +150%

            return min_range <= defender_score <= max_range

        except Exception as e:
            self._log_error(f"Error validating attack range: {str(e)}", e, "validate_attack_range")
            return False
    
    def calculate_military_purchase_limits(self, nation: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate military purchase limits for a nation."""
        try:
            # Use the AllianceCalculator from calc.py
            if not self.calculator:
                self._log_error("AllianceCalculator not available for military purchase limits calculation", context="calculate_military_purchase_limits")
                return {'soldiers': 0, 'tanks': 0, 'aircraft': 0, 'ships': 0}
            
            return self.calculator.calculate_military_purchase_limits(nation)
        except Exception as e:
            self._log_error(f"Error calculating military purchase limits: {str(e)}", e, "calculate_military_purchase_limits")
            return {'soldiers': 0, 'tanks': 0, 'aircraft': 0, 'ships': 0}

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
        target_nation: Dict[str, Any] = None,
        max_groups: int = 10,
        attackers_alliance_id: Optional[str] = None,
        exclude_unoptimal: bool = False,
    ) -> Dict[str, Any]:
        """
        Find optimal alliance members for war targeting and also return all in-range attackers sorted by total units.
        
        Args:
            target_nation: Target nation data to check war range against
            max_groups: Maximum number of optimal groups to return
            
        Returns:
            Dictionary containing optimal attacker groups, and a sorted list of all attackers in range
        """
        try:
            # Determine alliance to fetch
            alliance_id = str(attackers_alliance_id or self.home_alliance_id)
            alliances_to_fetch = [('selected', {'id': alliance_id, 'name': 'Selected Alliance'})]
            if str(alliance_id) == str(self.home_alliance_id):
                alliances_to_fetch = [('home', {'id': str(self.home_alliance_id), 'name': 'Death Before Dishonor'})]
            
            all_nations = []
            
            # Fetch data from selected alliances
            for _, alliance_config in alliances_to_fetch:
                try:
                    aid = str(alliance_config['id'])
                    self.logger.info(f"Fetching nations for alliance ID: {aid}")
                    alliance_nations = await self.get_alliance_nations(aid, force_refresh=False)
                    
                    if alliance_nations and isinstance(alliance_nations, list):
                        all_nations.extend(alliance_nations)
                        self.logger.info(f"Fetched {len(alliance_nations)} nations from {alliance_config['name']}")
                    else:
                        self.logger.warning(f"No nations found for alliance: {alliance_config['name']}")
                except Exception as e:
                    self.logger.warning(f"Error fetching alliance data for {alliance_config['name']}: {e}")
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
                    pass  # If purchase limits fail, use current values
                
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

    def create_optimal_attackers_view(self, interaction: discord.Interaction, target_nation: Dict[str, Any], optimal_attackers: Dict[str, Any], show_warchest: bool = False) -> 'OptimalAttackersView':
        """Create an OptimalAttackersView instance for displaying optimal attacker groups."""
        try:
            attackers_list = optimal_attackers.get('all_attackers') or optimal_attackers.get('optimal_groups', [])
            return OptimalAttackersView(interaction, target_nation, attackers_list, self, show_warchest=show_warchest)
        except Exception as e:
            self._log_error(f"Error creating optimal attackers view: {str(e)}", e, "create_optimal_attackers_view")
            return None

    async def destroy_target_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """
        Autocomplete function for destroy command target input.
        
        Args:
            interaction: Discord interaction
            current: Current input string
            
        Returns:
            List of autocomplete choices
        """
        try:
            if not current or len(current.strip()) < 2:
                return []
            
            # Get nations from DB4D alliance for autocomplete
            all_nations = []
            try:
                alliance_id = str(self.home_alliance_id)
                alliance_nations = await self.get_alliance_nations(alliance_id, force_refresh=False)
                if alliance_nations and isinstance(alliance_nations, list):
                    all_nations.extend(alliance_nations)
            except Exception as e:
                self.logger.warning(f"Error fetching DB4D alliance data for autocomplete: {e}")
            
            # Filter nations by current input
            current_lower = current.lower().strip()
            matches = []
            
            for nation in all_nations:
                if isinstance(nation, dict):
                    nation_name = nation.get('nation_name', '') or ''
                    leader_name = nation.get('leader_name', '') or ''
                    nation_id = str(nation.get('nation_id', '')) or ''
                    
                    # Check if nation matches search criteria
                    if (current_lower in nation_name.lower() or 
                        current_lower in leader_name.lower() or 
                        current_lower in nation_id):
                        
                        # Create display name with nation name and leader name
                        display_name = f"{nation_name} ({leader_name})"
                        if len(display_name) > 100:  # Discord choice limit
                            display_name = display_name[:97] + "..."
                        
                        # Use nation ID as the value for uniqueness
                        value = nation_id
                        
                        matches.append({
                            'display': display_name,
                            'value': value,
                            'nation_name': nation_name,
                            'leader_name': leader_name,
                            'nation_id': nation_id
                        })
            
            # Sort matches by relevance (prefer exact matches, then nation name matches)
            def sort_key(match):
                score = 0
                nation_name_lower = match['nation_name'].lower()
                leader_name_lower = match['leader_name'].lower()
                
                # Exact nation name match gets highest score
                if nation_name_lower == current_lower:
                    score += 1000
                # Starts with current input
                elif nation_name_lower.startswith(current_lower):
                    score += 500
                # Contains current input
                elif current_lower in nation_name_lower:
                    score += 200
                
                # Leader name matches
                if leader_name_lower == current_lower:
                    score += 300
                elif leader_name_lower.startswith(current_lower):
                    score += 150
                elif current_lower in leader_name_lower:
                    score += 50
                
                # Nation ID exact match
                if match['nation_id'] == current_lower:
                    score += 400
                
                return -score  # Negative for descending sort
            
            matches.sort(key=sort_key)
            
            # Limit to 25 choices (Discord limit)
            matches = matches[:25]
            
            # Convert to Discord choices
            choices = []
            for match in matches:
                choices.append(app_commands.Choice(
                    name=match['display'],
                    value=match['value']
                ))
            
            return choices
            
        except Exception as e:
            self._log_error(f"Error in destroy_target_autocomplete: {str(e)}", e, "destroy_target_autocomplete")
            return []

    @app_commands.command(name='destroy', description='Find optimal attackers for a target nation with analysis')
    @app_commands.describe(
        target='Enter Nation Name, Leader Name, or Nation Link/ID',
        attackers='Enter Alliance Name or Alliance ID (defaults to DB4D if omitted)',
        exclude_unoptimal='Exclude nations with >2000 avg infra or zero units'
    )
    async def destroy(
        self,
        interaction: discord.Interaction,
        target: str,
        attackers: Optional[str] = None,
        exclude_unoptimal: bool = False,
    ):
        """
        Find optimal attackers for a target nation with comprehensive analysis.
        
        Args:
            interaction: Discord interaction
            nation_name: Target nation name
            nation_leader: Target nation leader name  
            nation_link_or_id: Target nation link or nation ID
            alliance_filter: Filter attackers by alliance
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
            loading_message = await interaction.followup.send(f"🔍 **Searching for Target...**\nLooking up: **{display_name}**")
            
            # Resolve attackers alliance (defaults to DB4D)
            attackers_identifier = (attackers or '').strip()
            attackers_item = None
            attackers_id = None
            if attackers_identifier:
                try:
                    if not self.query_instance:
                        self.query_instance = PNWAPIQuery()
                    attackers_item = await self.query_instance.resolve_alliance(attackers_identifier)
                    attackers_id = str((attackers_item or {}).get('id') or '').strip() or None
                except Exception as e:
                    self.logger.warning(f"Failed to resolve attackers alliance: {e}")
                    attackers_item = None
                    attackers_id = None
            if not attackers_id:
                attackers_id = str(self.home_alliance_id)
                attackers_item = {'id': attackers_id, 'name': 'Death Before Dishonor', 'acronym': 'DB4D'}
            show_warchest = (str(attackers_id) == str(self.home_alliance_id))

            # Pre-refresh alliance data if using DB4D
            try:
                if self.query_instance and show_warchest:
                    await self.query_instance.get_alliance_nations(
                        str(self.home_alliance_id), bot=self.bot, force_refresh=True
                    )
            except Exception as e:
                self.logger.warning(f"Alliance refresh before target fetch failed: {e}")
            
            # Fetch target nation data
            target_nation = await self.fetch_target_nation(target_data, input_type)
            
            if not target_nation:
                message = f"❌ **Target Not Found**\nCould not find nation: **{display_name}**\n\n"
                message += "**Try:**\n"
                message += "- Check the spelling of the nation name\n"
                message += "- Check the spelling of the leader name\n"
                message += "- Verify the nation link or ID is correct\n"
                message += "- Check if the nation exists"
                await loading_message.edit(content=message)
                return
            
            # Fetch Discord username for target nation
            try:
                await self.query_instance._fetch_discord_usernames([target_nation], self.bot)
            except Exception as e:
                self.logger.warning(f"Failed to fetch Discord username for target: {e}")
            
            # Update loading message
            await loading_message.edit(content=f"⚔️ **Finding Optimal Attackers...**\nTarget: **{target_nation.get('nation_name', 'Unknown')}**\nSearching for optimal attacker groups...")
            
            # Find optimal attackers for specified alliance with optional exclusion
            optimal_attackers = await self.find_optimal_attackers(
                target_nation,
                max_groups=10,
                attackers_alliance_id=attackers_id,
                exclude_unoptimal=exclude_unoptimal,
            )
            
            if 'error' in optimal_attackers:
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
                await loading_message.edit(content=message)
                return
            
            # Fetch Discord usernames for attackers
            try:
                await self.query_instance._fetch_discord_usernames(attackers_list, self.bot)
            except Exception as e:
                self.logger.warning(f"Failed to fetch Discord usernames for attackers: {e}")
            
            # Build attacker display without interactive buttons
            view = self.create_optimal_attackers_view(interaction, target_nation, optimal_attackers, show_warchest=show_warchest)
            
            if not view:
                await loading_message.edit(content="❌ **Error Creating View**\nFailed to build the attacker display.")
                return
            
            # Build the target summary
            target_message = view.create_target_message()
            
            # Delete the loading message
            try:
                await loading_message.delete()
            except:
                pass
            
            # Send the target message first (no buttons) and suppress link previews
            try:
                sent_target = await interaction.followup.send(target_message)
                try:
                    await sent_target.suppress_embeds()
                except Exception:
                    # If suppression isn't supported or fails, continue without blocking
                    pass
            except Exception:
                await interaction.followup.send(target_message)
            
            # Send all attacker pages as plain messages (no buttons/pagination)
            if view.attacker_pages:
                for idx, page in enumerate(view.attacker_pages):
                    attacker_message = view.create_attacker_page_message(page, idx)
                    try:
                        sent_attacker = await interaction.followup.send(attacker_message)
                        try:
                            await sent_attacker.suppress_embeds()
                        except Exception:
                            # If suppression isn't supported or fails, continue without blocking
                            pass
                    except Exception:
                        await interaction.followup.send(attacker_message)
            else:
                # If no attacker pages, send a message indicating no attackers found
                await interaction.followup.send("❌ **No Attackers Found**\nCould not find any optimal attackers for this target.")
            
            self.logger.info(
                f"Destroy slash command completed successfully for target: {target_nation.get('nation_name', 'Unknown')} "
                f"by user {interaction.user.name}#{interaction.user.discriminator}"
            )
            
        except Exception as e:
            self._log_error(f"Error in destroy slash command: {str(e)}", e, "destroy")
            error_message = "❌ **Command Error**\nAn unexpected error occurred while processing the destroy command.\n\n"
            error_message += f"**Error:** {str(e)}"
            
            try:
                await interaction.followup.send(error_message)
            except:
                # If followup fails, try to send a new message
                try:
                    await interaction.channel.send(error_message)
                except:
                    pass

class OptimalAttackersView:
    """Formatter for displaying target and attacker information as plain text messages."""
    
    def __init__(self, interaction: discord.Interaction, target_nation: Dict[str, Any], optimal_groups: List[Dict[str, Any]], cog: DestroyCog, show_warchest: bool = False):
        try:
            self.interaction = interaction
            self.target_nation = target_nation or {}
            self.cog = cog
            self.current_page = 0
            self.show_warchest = bool(show_warchest)
            
            # Build attacker list: either a flat list of attackers or flattened groups
            all_attackers = []
            if optimal_groups and isinstance(optimal_groups, list) and len(optimal_groups) > 0 and isinstance(optimal_groups[0], dict) and 'attackers' in optimal_groups[0]:
                # Provided as groups; flatten attackers
                for group in (optimal_groups or []):
                    if group and group.get('attackers'):
                        all_attackers.extend(group['attackers'])
            else:
                # Provided directly as a list of attackers
                all_attackers = optimal_groups or []
            
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
            self.attacker_pages = []
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
            try:
                full_purchase_limits = self.cog.calculator.calculate_military_purchase_limits(self.target_nation)
            except Exception:
                full_purchase_limits = {
                    'soldiers_daily': 0, 'tanks_daily': 0, 'aircraft_daily': 0, 'ships_daily': 0,
                    'missiles': 0, 'nukes': 0,
                    'soldiers_max': 0, 'tanks_max': 0, 'aircraft_max': 0, 'ships_max': 0
                }
            try:
                building_ratios = self.cog.calculator.calculate_building_ratios(self.target_nation)
                mmr_string = building_ratios.get('mmr_string', '0/0/0/0')
            except Exception:
                mmr_string = '0/0/0/0'
            try:
                _mmr_parts = [p.strip() for p in str(mmr_string).split('/')]
                mmr_1dp = '/'.join(f"{float(p):.1f}" for p in _mmr_parts if p != '') if _mmr_parts else '0.0/0.0/0.0/0.0'
            except Exception:
                mmr_1dp = '0.0/0.0/0.0/0.0'

            projects_info = []
            has_missile_launch = self.cog.has_project(self.target_nation, 'Missile Launch Pad')
            has_nuke_research = self.cog.has_project(self.target_nation, 'Nuclear Research Facility')
            has_iron_dome = self.cog.has_project(self.target_nation, 'Iron Dome')
            has_vital_defense = self.cog.has_project(self.target_nation, 'Vital Defense System')            
            if has_missile_launch:
                projects_info.append("🚀 Missile Launch Pad")
            if has_nuke_research:
                projects_info.append("☢️ Nuclear Research Facility")
            if has_iron_dome:
                projects_info.append("🛡️ Iron Dome")
            if has_vital_defense:
                projects_info.append("🔒 Vital Defense System")            
            projects_text = "\n".join(projects_info) if projects_info else "No strategic projects"
            nation_id = self.target_nation.get('nation_id') or self.target_nation.get('id')
            nation_url = f"https://politicsandwar.com/nation/id={nation_id}" if nation_id else None
            header_name = f"[{nation_name}]({nation_url})" if nation_url else nation_name
            discord_username = self.target_nation.get('discord_username')
            discord_display_name = self.target_nation.get('discord_display_name')
            if discord_display_name and discord_username and discord_display_name != discord_username:
                discord_text = f"{discord_display_name} (@{discord_username})"
            elif discord_username:
                discord_text = f"@{discord_username}"
            elif discord_display_name:
                discord_text = f"{discord_display_name}"
            else:
                discord_text = None
            message = f"{header_name}" + (f" ({discord_text})" if discord_text else "") + "\n"
            message += f"**c{num_cities:,}** with **{avg_infra_per_city:,.0f}** Infra on **{mmr_1dp}**\n"
            message += f"Can be Spied: {'✅' if espionage_available else '❌'}\n"
            strategic_flags = ""
            if has_missile_launch:
                strategic_flags += "🚀"
            if has_nuke_research:
                strategic_flags += "☢️"
            if has_iron_dome:
                strategic_flags += " **ID**"
            if has_vital_defense:
                strategic_flags += " **VDS**"
            message += f"Projects: {strategic_flags.strip() or 'None'}\n"
            message += f"**🕵️ Spies:** {safe_spies:,}\n"
            message += "**Units (Current/Max):**\n"
            message += (
                f"🪖{safe_soldiers:,}/{full_purchase_limits.get('soldiers_max', 0):,}  "
                f"🚙{safe_tanks:,}/{full_purchase_limits.get('tanks_max', 0):,}  "
                f"🛩️{safe_aircraft:,}/{full_purchase_limits.get('aircraft_max', 0):,}  "
                f"⚓{safe_ships:,}/{full_purchase_limits.get('ships_max', 0):,}\n"
            )
            message += "**Daily Purchase Limits**\n"
            message += (
                f"🪖{full_purchase_limits.get('soldiers_daily', 0):,}/day  "
                f"🚙{full_purchase_limits.get('tanks_daily', 0):,}/day  "
                f"🛩️{full_purchase_limits.get('aircraft_daily', 0):,}/day  "
                f"⚓{full_purchase_limits.get('ships_daily', 0):,}/day\n"
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
                f"🪖{soldiers:,}/{full_purchase_limits.get('soldiers_max', 0):,}  "
                f"🚙{tanks:,}/{full_purchase_limits.get('tanks_max', 0):,}  "
                f"🛩️{aircraft:,}/{full_purchase_limits.get('aircraft_max', 0):,}  "
                f"⚓{ships:,}/{full_purchase_limits.get('ships_max', 0):,}\n"
            )
            field_value += f"**Daily Purchase Limits**\n"
            field_value += (
                f"🪖{full_purchase_limits.get('soldiers_daily', 0):,}/day  "
                f"🚙{full_purchase_limits.get('tanks_daily', 0):,}/day  "
                f"🛩️{full_purchase_limits.get('aircraft_daily', 0):,}/day  "
                f"⚓{full_purchase_limits.get('ships_daily', 0):,}/day"
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

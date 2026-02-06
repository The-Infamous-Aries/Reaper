import discord
from discord.ext import commands
from discord import app_commands
import os
import re
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
import sys
import logging
import traceback
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from Systems.PnW.Util.query import create_query_instance
from config import PANDW_API_KEY, HOME_ALLIANCE_ID
from Systems.Functions.user_data_manager import UserDataManager
from Systems.PnW.Util.calc import AllianceCalculator

# Top-level autocomplete wrapper to bind correctly without relying on Cog method binding
async def autocomplete_show_target(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    """Module-level autocomplete function that delegates to the ShowCog method."""
    try:
        bot = interaction.client
        cog = getattr(bot, 'get_cog', lambda name: None)("ShowCog")
        if cog and hasattr(cog, 'show_target_autocomplete'):
            return await cog.show_target_autocomplete(interaction, current)
        return []
    except Exception:
        return []


class ShowCog(commands.Cog):
    """Cog for showing and displaying nation information."""
    
    def __init__(self, bot: commands.Bot):
        try:
            self.bot = bot
            self.api_key = PANDW_API_KEY
            self.user_data_manager = UserDataManager()
            self.logger = logging.getLogger(__name__)
            if not self.logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)
                self.logger.setLevel(logging.INFO)
            self.error_count = 0
            self.max_errors = 100
            # Simple in-memory cache for searched nations (15 minutes TTL)
            self.SEARCH_CACHE_TTL_SECONDS = 900
            self.search_cache: Dict[str, Dict[str, Any]] = {}
            
            # Initialize query instance
            try:
                self.query_instance = create_query_instance()
                self.logger.info("Centralized query instance initialized successfully")
                if hasattr(self.query_instance, 'cache_ttl_seconds'):
                    self.query_instance.cache_ttl_seconds = 3600
            except Exception as e:
                self.logger.error(f"Failed to initialize query instance: {e}")
                self.query_instance = None

            # Initialize calculator
            try:
                self.calculator = AllianceCalculator()
                self.logger.info("AllianceCalculator initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize AllianceCalculator: {e}")
                self.calculator = None
                
        except Exception as e:
            print(f"Error initializing ShowCog: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            self.bot = bot
            self.api_key = PANDW_API_KEY
            self.user_data_manager = UserDataManager()
            self.error_count = 0
            self.max_errors = 100
            self.query_instance = None
            self.calculator = None
            # Fallback cache init
            self.SEARCH_CACHE_TTL_SECONDS = 900
            self.search_cache = {}

    def _cache_key_for_target(self, target_data: str, input_type: str) -> str:
        """Create a stable cache key for target lookups."""
        try:
            norm = (target_data or '').strip().lower()
            return f"{input_type}:{norm}"
        except Exception:
            return f"{input_type}:{target_data}"

    def _prune_search_cache(self) -> None:
        """Remove expired items from the search cache."""
        try:
            now = time.time()
            expired_keys = [k for k, v in (self.search_cache or {}).items() if v.get('expires_at', 0) <= now]
            for k in expired_keys:
                self.search_cache.pop(k, None)
        except Exception as e:
            self._log_error("Error pruning search cache", e, "_prune_search_cache")

    def _get_cached_nation(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached nation data if not expired."""
        try:
            self._prune_search_cache()
            entry = self.search_cache.get(cache_key)
            if not entry:
                return None
            if entry.get('expires_at', 0) <= time.time():
                # Expired
                self.search_cache.pop(cache_key, None)
                return None
            return entry.get('data')
        except Exception as e:
            self._log_error("Error accessing search cache", e, "_get_cached_nation")
            return None

    def _set_cached_nation(self, cache_key: str, nation_data: Dict[str, Any]) -> None:
        """Store nation data in cache with TTL."""
        try:
            expires_at = time.time() + float(self.SEARCH_CACHE_TTL_SECONDS or 900)
            self.search_cache[cache_key] = {'data': nation_data, 'expires_at': expires_at}
        except Exception as e:
            self._log_error("Error setting search cache", e, "_set_cached_nation")

    def _log_error(self, error_msg: str, exception: Exception = None, context: str = ""):
        """Centralized error logging with tracking."""
        try:
            self.error_count += 1
            
            if self.error_count > self.max_errors:
                self.error_count = 1
                self.logger.warning(f"Error count reset after reaching {self.max_errors}")
            
            full_msg = f"[Error #{self.error_count}] {error_msg}"
            if context:
                full_msg += f" (Context: {context})"
            
            if hasattr(self, 'logger') and self.logger:
                self.logger.error(full_msg)
                if exception:
                    self.logger.error(f"Exception details: {str(exception)}")
                    self.logger.error(f"Traceback: {traceback.format_exc()}")
            else:
                print(full_msg)
                if exception:
                    print(f"Exception details: {str(exception)}")
                    print(f"Traceback: {traceback.format_exc()}")
                    
        except Exception as log_error:
            print(f"Error in error logging: {log_error}")
            print(f"Original error: {error_msg}")

    def _validate_input(self, data: Any, expected_type: type, field_name: str = "data") -> bool:
        """Validate input data type and log errors if invalid."""
        try:
            if not isinstance(data, expected_type):
                self._log_error(f"Invalid {field_name} type. Expected {expected_type.__name__}, got {type(data).__name__}")
                return False
            return True
        except Exception as e:
            self._log_error(f"Error validating {field_name}", e)
            return False

    async def get_alliance_nations(self, alliance_id: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Get alliance nations data directly from the API (no file caching).
        Used for autocomplete suggestions without reading/writing alliance files.
        """
        try:
            if not self.query_instance:
                self.logger.warning("get_alliance_nations: Query instance unavailable")
                return []
            nations = await self.query_instance.get_alliance_nations(alliance_id, bot=self.bot, force_refresh=True)
            self.logger.info(f"get_alliance_nations: Retrieved {len(nations or [])} nations from API for alliance {alliance_id}")
            return nations or []
        except Exception as e:
            self._log_error(f"Error in get_alliance_nations for alliance {alliance_id}", e, "get_alliance_nations")
            return []

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
        Fetch comprehensive target nation data from P&W API.
        
        Args:
            target_data: The target identifier
            input_type: Type of input ('nation_id', 'nation_name', 'leader_name', 'nation_link')
            
        Returns:
            Nation data dictionary or None if not found
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

            # Cache lookup
            cache_key = self._cache_key_for_target(target_data, input_type)
            cached = self._get_cached_nation(cache_key)
            if cached:
                self.logger.info("Returning nation data from search cache")
                return cached
            
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
                
                self.logger.info(f"Successfully fetched nation: {target_nation.get('nation_name', 'Unknown')}")
                # Set cache under both the original key and nation_id key (if available)
                try:
                    self._set_cached_nation(cache_key, target_nation)
                    nid = str(target_nation.get('id') or target_nation.get('nation_id') or '').strip()
                    if nid:
                        id_key = self._cache_key_for_target(nid, 'nation_id')
                        self._set_cached_nation(id_key, target_nation)
                except Exception as e_set:
                    self._log_error("Error caching fetched nation", e_set, "fetch_target_nation.cache")
                return target_nation
                
            except Exception as e:
                self._log_error("Error fetching nation data from query instance", e, "fetch_target_nation")
                return None
                
        except Exception as e:
            self._log_error("Unexpected error in fetch_target_nation", e, "fetch_target_nation")
            return None

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

    def calculate_nation_improvements(self, nation: Dict[str, Any]) -> Dict[str, int]:
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

    def _is_city_powered(self, city: Dict[str, Any]) -> bool:
        """Robustly determine whether a city is powered.

        Handles boolean, numeric, and string representations of the 'powered' field.
        Falls back to checking for presence of any power plant improvements when the field is missing.
        """
        try:
            val = city.get('powered', None)
            if val is None:
                # Fallback: consider powered if the city has any power plant improvements
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

    async def create_comprehensive_nation_embed(self, nation: Dict[str, Any]) -> discord.Embed:
        """Create a comprehensive nation embed similar to blitz.py's nation list view."""
        # Validate nation input
        if not isinstance(nation, dict):
            embed = discord.Embed(
                title="⚠️ Invalid Nation Data",
                description=f"Expected dictionary for nation, got {type(nation).__name__}: {str(nation)[:100]}",
                color=discord.Color.red()
            )
            return embed
        
        nation_name = nation.get('nation_name', 'Unknown Nation')
        leader_name = nation.get('leader_name', 'Unknown Leader')
        nation_id = nation.get('id') or nation.get('nation_id')
        vacation_turns = nation.get('vacation_mode_turns', 0)
        beige_turns = nation.get('beige_turns', 0)
        last_active_raw = nation.get('last_active', 'Unknown')
        last_active = self._format_last_active_time(last_active_raw)
        safe_spies = nation.get('spies', 0) or 0
        safe_ground_capacity = nation.get('ground_capacity') or 0
        safe_air_capacity = nation.get('air_capacity') or 0
        safe_naval_capacity = nation.get('naval_capacity') or 0
        safe_ground_cost = nation.get('ground_cost') or 0
        safe_air_cost = nation.get('air_cost') or 0
        safe_naval_cost = nation.get('naval_cost') or 0
        wars_won = nation.get('wars_won', 0)
        wars_lost = nation.get('wars_lost', 0)
        total_wars = wars_won + wars_lost
        war_ratio = (wars_won / total_wars * 100) if total_wars > 0 else 0
        safe_money_looted = nation.get('money_looted') or 0
        safe_money = nation.get('money', 0) or 0
        safe_credits = nation.get('credits', 0) or 0
        nation_improvements = self.calculate_nation_improvements(nation)
        # Cleaned unused resource/power variables; power and resources will be shown in dedicated views
        
        # Calculate building ratios using calculator if available
        building_ratios = {}
        mmr_string = 'Unknown'
        if self.calculator:
            try:
                # Offload heavy calculation
                building_ratios = await asyncio.to_thread(self.calculator.calculate_building_ratios, nation) or {}
                mmr_string = building_ratios.get('mmr_string', 'Unknown')
            except Exception as e:
                self._log_error("Error calculating building ratios", e)
        
        cities = nation.get('cities', [])
        flag_url = nation.get('flag')
        total_infra = 0
        avg_city_infra = 0
        powered_cities = 0
        infra_tier = 'Unknown'
        if cities:
            total_infra = sum((city.get('infrastructure', 0) or 0) for city in cities if isinstance(city, dict))
            avg_city_infra = total_infra / len(cities) if cities else 0
            powered_cities = sum(1 for city in cities if isinstance(city, dict) and self._is_city_powered(city))
            if self.calculator:
                try:
                    infra_tier = self.calculator._get_infrastructure_tier(avg_city_infra)
                except Exception:
                    infra_tier = 'Unknown'

        embed = discord.Embed(
            title=f"🏛️ {nation_name}",
            description=f"**Leader:** {leader_name}",
            color=discord.Color.from_rgb(0, 150, 255)
        )
        if nation_id:
            embed.url = f"https://politicsandwar.com/nation/id={nation_id}"
            if flag_url:
                embed.set_thumbnail(url=flag_url)
            else:
                embed.set_thumbnail(url=f"https://politicsandwar.com/nation/id={nation_id}/image")
        
        # Discord info
        discord_info = ""
        discord_username = nation.get('discord_username')
        if discord_username:
            discord_info = discord_username
        elif nation.get('discord_id'):
            discord_info = f"<@{nation.get('discord_id')}>"
        else:
            discord_info = "Not linked"
        
        # Cooldown calculations
        turns_since_city = nation.get('turns_since_last_city', 0)
        turns_since_project = nation.get('turns_since_last_project', 0)
        city_cooldown_remaining = max(0, 120 - turns_since_city)
        project_cooldown_remaining = max(0, 120 - turns_since_project)       
        city_status = "✅ Available" if city_cooldown_remaining == 0 else f"❌ {city_cooldown_remaining} turns"
        project_status = "✅ Available" if project_cooldown_remaining == 0 else f"❌ {project_cooldown_remaining} turns"

        basic_stats = (
            f"**Alliance:** {nation.get('alliance_name', 'None')}\n"
            f"**Position:** {nation.get('alliance_position', 'Unknown').title()}\n"
            f"**Vacation Mode:** {'Yes' if vacation_turns > 0 else 'No'}\n"
            f"**Color:** {nation.get('color', 'Unknown')}\n"
            f"{'**Beige Turns:** ' + str(beige_turns) + chr(10) if nation.get('color', '').lower() == 'beige' else ''}"
            f"**Discord:** {discord_info}\n"
            f"**Last Active:** {last_active}\n"
            f"**New Project:** {project_status}\n"            
            f"**New City:** {city_status}\n"
            f"**Cities:** {nation.get('num_cities', 0)}\n"
            f"**Powered Cities:** {powered_cities}/{len(cities)}\n"
            f"**Infra Tier:** {infra_tier}\n"
            f"**Total Infrastructure:** {total_infra:,.0f}\n"
            f"**Avg Infrastructure/City:** {avg_city_infra:,.0f}\n"
            f"**Domestic Policy:** {nation.get('domestic_policy', 'Unknown')}"
        )
        embed.add_field(name="📊 Basic Statistics", value=basic_stats, inline=False)
        
        # Resource display removed per requirements: do not include holdings in embed

        # Specializations (similar to blitz.py logic)
        specializations = []
        if self.calculator:
            try:
                if self.calculator.has_project(nation, 'Missile Launch Pad'):
                    specializations.append(f"🚀 Missile")
                if self.calculator.has_project(nation, 'Nuclear Research Facility'):
                    specializations.append(f"☢️ Nuke")
            except Exception:
                pass
        
        # Special nation checks removed
        
        # Money looted specializations
        if safe_money_looted >= 2_500_000_000:
            specializations.append("🏴‍☠️ Taxman")
        elif safe_money_looted >= 1_000_000_000:
            specializations.append("🏴 Pirate")
        elif safe_money_looted >= 750_000_000:
            specializations.append("☠️ Pillager")
        elif safe_money_looted >= 500_000_000:
            specializations.append("💀 Bandit")
        elif safe_money_looted >= 250_000_000:
            specializations.append("💰 Thief")
        elif safe_money_looted >= 100_000_000:
            specializations.append("💳 Scammer")
        
        # War specializations
        if wars_won >= 500:
            specializations.append("🪦 Reaper")
        elif wars_won >= 250:
            specializations.append("⚰️ Murderer")
        elif wars_won >= 100:
            specializations.append("⚱️ Fighter")
        
        # Credit specializations
        if safe_credits >= 5:
            specializations.append("🧠 Planner")
        elif safe_credits >= 1:
            specializations.append("🤔 Thinker")
        
        # Spy specializations
        if safe_spies >= 60:
            specializations.append("🥷 Shadow")
        
        # Reputation specializations
        commendations = nation.get('commendations', 0)
        if commendations >= 500:
            specializations.append("🙇 Worshipped")
        elif commendations >= 200:
            specializations.append("🦸 Idolized")
        elif commendations >= 100:
            specializations.append("❤️ Loved")
        elif commendations >= 50:
            specializations.append("👍 Liked")
        
        denouncements = nation.get('denouncements', 0)
        if denouncements >= 500:
            specializations.append("🖕 Despised")
        elif denouncements >= 200:
            specializations.append("🦹 Nemesis")
        elif denouncements >= 100:
            specializations.append("💔 Hated")
        elif denouncements >= 50:
            specializations.append("👎 Disliked")
        
        # Military advantage specializations
        if self.calculator:
            try:
                military_analysis = self.calculator.calculate_military_advantage(nation)
                if military_analysis:
                    if military_analysis.get('has_ground_advantage', False):
                        specializations.append("🪖 Ground")
                    if military_analysis.get('has_air_advantage', False):
                        specializations.append("✈️ Air")
                    if military_analysis.get('has_naval_advantage', False):
                        specializations.append("🚢 Naval")
            except Exception:
                pass
        
        specialization_text = "\n".join(specializations) if specializations else "⚔️ Standard"
        embed.add_field(name="⚜️ Specializations", value=specialization_text, inline=False)

        military_info = (
            f"**War Policy:** {nation.get('war_policy', 'Unknown')}\n"
            f"**Score:** {nation.get('score', 0):,}\n"
            f"**MMR:** {mmr_string}\n"
            f"**Espionage Available:** {'✅ Yes' if nation.get('espionage_available', False) else '❌ No'}\n"
            f"**Money Looted:** ${safe_money_looted:,}\n"
            f"**Wars Won:** {wars_won}\n"
            f"**Wars Lost:** {wars_lost}\n"
            f"**Win Rate:** {war_ratio:.1f}%\n"
            f"**Ground Capacity:** {safe_ground_capacity:,}\n"
            f"**Air Capacity:** {safe_air_capacity:,}\n"
            f"**Naval Capacity:** {safe_naval_capacity:,}\n"
            f"**Ground Cost:** {safe_ground_cost:,}\n"
            f"**Air Cost:** {safe_air_cost:,}\n"
            f"**Naval Cost:** {safe_naval_cost:,}"
        )
        embed.add_field(name="⚔️ War Stats", value=military_info, inline=False)

        limits = self.calculator.calculate_military_purchase_limits(nation) if self.calculator else {}
        soldiers_cur = int(nation.get('soldiers', 0) or 0)
        tanks_cur = int(nation.get('tanks', 0) or 0)
        aircraft_cur = int(nation.get('aircraft', 0) or 0)
        ships_cur = int(nation.get('ships', 0) or 0)

        embed.add_field(
            name="⚔️ Military Units",
            value=(
                f"🪖 **Soldiers:** {soldiers_cur:,}/{limits.get('soldiers_max', 0):,}\n"
                f"🚙 **Tanks:** {tanks_cur:,}/{limits.get('tanks_max', 0):,}\n"
                f"🛩️ **Aircraft:** {aircraft_cur:,}/{limits.get('aircraft_max', 0):,}\n"
                f"⚓ **Ships:** {ships_cur:,}/{limits.get('ships_max', 0):,}"
            ),
            inline=False
        )

        embed.add_field(
            name="🏭 Daily Production",
            value=(
                f"🪖 **Soldiers:** {limits.get('soldiers_daily', 0):,}/day\n"
                f"🚙 **Tanks:** {limits.get('tanks_daily', 0):,}/day\n"
                f"🛩️ **Aircraft:** {limits.get('aircraft_daily', 0):,}/day\n"
                f"⚓ **Ships:** {limits.get('ships_daily', 0):,}/day\n"
                f"🚀 **Missiles:** {limits.get('missiles', 0):,}/day\n"
                f"☢️ **Nukes:** {limits.get('nukes', 0):,}/day"
            ),
            inline=False
        )

        # Strategic Projects section (grouped by category with initials)
        try:
            if self.calculator:
                project_categories = {
                    '⚔️ War': [
                        ('Advanced Pirate Economy', 'advanced_pirate_economy'),
                        ('Central Intelligence Agency', 'central_intelligence_agency'),
                        ('Fallout Shelter', 'fallout_shelter'),
                        ('Guiding Satellite', 'guiding_satellite'),
                        ('Iron Dome', 'iron_dome'),
                        ('Military Doctrine', 'military_doctrine'),
                        ('Military Research Center', 'military_research_center'),
                        ('Military Salvage', 'military_salvage'),
                        ('Missile Launch Pad', 'missile_launch_pad'),
                        ('Nuclear Launch Facility', 'nuclear_launch_facility'),
                        ('Nuclear Research Facility', 'nuclear_research_facility'),
                        ('Pirate Economy', 'pirate_economy'),
                        ('Propaganda Bureau', 'propaganda_bureau'),
                        ('Space Program', 'space_program'),
                        ('Spy Satellite', 'spy_satellite'),
                        ('Surveillance Network', 'surveillance_network'),
                        ('Vital Defense System', 'vital_defense_system')
                    ],
                    '🏭 Industry': [
                        ('Arms Stockpile', 'arms_stockpile'),
                        ('Bauxite Works', 'bauxite_works'),
                        ('Clinical Research Center', 'clinical_research_center'),
                        ('Emergency Gasoline Reserve', 'emergency_gasoline_reserve'),
                        ('Green Technologies', 'green_technologies'),
                        ('International Trade Center', 'international_trade_center'),
                        ('Iron Works', 'iron_works'),
                        ('Mass Irrigation', 'mass_irrigation'),
                        ('Recycling Initiative', 'recycling_initiative'),
                        ('Specialized Police Training Program', 'specialized_police_training_program'),
                        ('Telecommunications Satellite', 'telecommunications_satellite'),
                        ('Uranium Enrichment Program', 'uranium_enrichment_program')
                    ],
                    '🏛️ Government': [
                        ('Activity Center', 'activity_center'),
                        ('Advanced Engineering Corps', 'advanced_engineering_corps'),
                        ('Arable Land Agency', 'arable_land_agency'),
                        ('Bureau of Domestic Affairs', 'bureau_of_domestic_affairs'),
                        ('Center Civil Engineering', 'center_for_civil_engineering'),
                        ('Government Support Agency', 'government_support_agency'),
                        ('Research & Development Center', 'research_and_development_center')
                    ],
                    '👽 Alien': [
                        ('Mars Landing', 'mars_landing'),
                        ('Moon Landing', 'moon_landing')
                    ]
                }

                strategic_parts = []
                for category_key, projects in project_categories.items():
                    category_projects = []
                    for project_name, _ in projects:
                        try:
                            if self.calculator.has_project(nation, project_name):
                                initials = ''.join(word[0] for word in project_name.split())
                                category_projects.append(initials)
                        except Exception:
                            continue

                    if category_projects:
                        projects_str = ', '.join(category_projects)
                        category_mapping = {'⚔️': 'War', '🏭': 'Industry', '🏛️': 'Government', '👽': 'Alien'}
                        category_emoji = category_key.split()[0] if ' ' in category_key else category_key
                        category_name = category_mapping.get(category_emoji, 'Unknown')
                        strategic_parts.append(f"**{category_name}:**\n{projects_str}")

                strategic_text = "\n".join(strategic_parts) if strategic_parts else "❌ None"
                embed.add_field(name="🏗️ Strategic Projects", value=strategic_text, inline=False)
        except Exception as e:
            self._log_error("Error building Strategic Projects section", e, "create_comprehensive_nation_embed")

        # Add footer with search info
        embed.set_footer(text=f"Nation ID: {nation_id} | Searched at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        
        return embed

    @commands.hybrid_command(name='show', description='Show a nation by name, leader, ID, or link and display detailed information')
    @app_commands.describe(target='Nation name, leader name, nation ID, or P&W link')
    @app_commands.autocomplete(target=autocomplete_show_target)
    async def show_command(self, ctx: commands.Context, *, target: str):
        """
        Show a nation and display comprehensive information.
        
        Args:
            target: Nation name, leader name, nation ID, or nation link
        """
        try:
            interaction = getattr(ctx, 'interaction', None)
            is_slash = isinstance(interaction, discord.Interaction)
            if is_slash and hasattr(interaction, 'response') and not interaction.response.is_done():
                await interaction.response.defer()
            
            nation_id, input_type = await self.parse_target_input(target)
            nation_data = await self.fetch_target_nation(target if input_type in ['nation_name', 'leader_name'] else nation_id, input_type)
            
            if not nation_data:
                embed = discord.Embed(
                    title="❌ Nation Not Found",
                    description=(
                        f"Could not find a nation matching: `{target}`\n\n"
                        "Try searching with:\n"
                        "• Nation name (e.g., 'Example Nation')\n"
                        "• Leader name (e.g., 'Optimus Prime')\n"
                        "• Nation ID (e.g., '12345')\n"
                        "• Nation link (e.g., 'https://politicsandwar.com/nation/id=12345')"
                    ),
                    color=discord.Color.red()
                )
                if is_slash and hasattr(interaction, 'followup'):
                    await interaction.followup.send(embed=embed)
                else:
                    await ctx.send(embed=embed)
                return
            
            embed = await self.create_comprehensive_nation_embed(nation_data)
            view = NationSearchView(ctx.author.id, self.bot, self, nation_data)
            if is_slash and hasattr(interaction, 'followup'):
                await interaction.followup.send(embed=embed, view=view)
            else:
                await ctx.send(embed=embed, view=view)

        except Exception as e:
            self._log_error("Error in show command", e, "show_command")
            embed = discord.Embed(
                title="❌ Show Error",
                description=(
                    f"An error occurred while showing: `{target}`\n\n"
                    "Please try again or contact an administrator if the issue persists."
                ),
                color=discord.Color.red()
            )
            if is_slash and interaction and hasattr(interaction, 'followup'):
                await interaction.followup.send(embed=embed)
            else:
                await ctx.send(embed=embed)

class NationSearchView(discord.ui.View):
    """View for a single nation search result with navigation to Military/Improvements."""

    def __init__(self, author_id: int, bot: commands.Bot, search_cog: 'ShowCog', nation: Dict[str, Any]):
        super().__init__()
        self.author_id = author_id
        self.bot = bot
        self.search_cog = search_cog
        self.nation = nation

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You are not authorized to use this menu.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Military", style=discord.ButtonStyle.secondary, emoji="🏭")
    async def military_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
            view = SearchNationMilitaryView(self.author_id, self.bot, self.search_cog, self.nation)
            embed = await view.generate_nation_military_embed()
            await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)
        except Exception as e:
            self.search_cog._log_error("Error opening Military view", e, "NationSearchView.military_button")
            await interaction.followup.send(embed=discord.Embed(title="❌ Error", description=str(e), color=discord.Color.red()))

    @discord.ui.button(label="Improvements", style=discord.ButtonStyle.secondary, emoji="🏗️")
    async def improvements_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
            view = SearchNationImprovementsView(self.author_id, self.bot, self.search_cog, self.nation)
            embed = await view.generate_nation_improvements_embed()
            await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)
        except Exception as e:
            self.search_cog._log_error("Error opening Improvements view", e, "NationSearchView.improvements_button")
            await interaction.followup.send(embed=discord.Embed(title="❌ Error", description=str(e), color=discord.Color.red()))


class SearchNationMilitaryView(discord.ui.View):
    """View for displaying military analysis for a single nation (search context)."""

    def __init__(self, author_id: int, bot: commands.Bot, search_cog: 'ShowCog', nation: Dict[str, Any]):
        super().__init__()
        self.author_id = author_id
        self.bot = bot
        self.search_cog = search_cog
        self.nation = nation

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You are not authorized to use this menu.", ephemeral=True)
            return False
        return True

    async def generate_nation_military_embed(self):
        try:
            calc = self.search_cog.calculator
            combat_score = calc.calculate_combat_score(self.nation) if calc else 0
            specialty = calc.get_nation_specialty(self.nation) if calc else "Standard"
            analysis = calc.calculate_military_analysis(self.nation) if calc else {}

            embed = discord.Embed(
                title=f"🏭 Military Analysis - {self.nation.get('nation_name', 'Unknown')}",
                description=f"**{specialty}** • Score: {combat_score:,.0f}",
                color=discord.Color.from_rgb(255, 140, 0)
            )

            current = analysis.get('current_military', {})
            limits = analysis.get('purchase_limits', {})

            soldiers_cur = int(current.get('soldiers', self.nation.get('soldiers', 0) or 0))
            tanks_cur = int(current.get('tanks', self.nation.get('tanks', 0) or 0))
            aircraft_cur = int(current.get('aircraft', self.nation.get('aircraft', 0) or 0))
            ships_cur = int(current.get('ships', self.nation.get('ships', 0) or 0))

            embed.add_field(
                name="⚔️ Military Units",
                value=(
                    f"🪖 **Soldiers:** {soldiers_cur:,}/{limits.get('soldiers_max', 0):,}\n"
                    f"🛡️ **Tanks:** {tanks_cur:,}/{limits.get('tanks_max', 0):,}\n"
                    f"✈️ **Aircraft:** {aircraft_cur:,}/{limits.get('aircraft_max', 0):,}\n"
                    f"🚢 **Ships:** {ships_cur:,}/{limits.get('ships_max', 0):,}"
                ),
                inline=False
            )

            embed.add_field(
                name="🏭 Daily Production",
                value=(
                    f"🪖 **Soldiers:** {limits.get('soldiers_daily', 0):,}/day\n"
                    f"🛡️ **Tanks:** {limits.get('tanks_daily', 0):,}/day\n"
                    f"✈️ **Aircraft:** {limits.get('aircraft_daily', 0):,}/day\n"
                    f"🚢 **Ships:** {limits.get('ships_daily', 0):,}/day\n"
                    f"� **Missiles:** {limits.get('missiles', 0):,}/day\n"
                    f"☢️ **Nukes:** {limits.get('nukes', 0):,}/day"
                ),
                inline=False
            )

            missiles_cur = int(self.nation.get('missiles', 0) or 0)
            nukes_cur = int(self.nation.get('nukes', 0) or 0)
            can_missile = analysis.get('can_missile', False)
            can_nuke = analysis.get('can_nuke', False)
            adv_value = (
                f"🚀 **Missiles:** {missiles_cur:,} {'(Project)' if can_missile else ''}\n"
                f"☢️ **Nukes:** {nukes_cur:,} {'(Project)' if can_nuke else ''}"
            )
            embed.add_field(name="🚀 Advanced Military", value=adv_value, inline=False)

            advantages = analysis.get('advantages', [])
            attack_range = analysis.get('attack_range', {})
            adv_text_parts = []
            if advantages:
                adv_text_parts.append("**Advantages:** " + ", ".join(advantages))
            if attack_range:
                min_r = attack_range.get('min_range') or attack_range.get('min_attack')
                max_r = attack_range.get('max_range') or attack_range.get('max_attack')
                cur_s = attack_range.get('current_score') or attack_range.get('nation_score') or self.nation.get('score', 0)
                adv_text_parts.append(f"**Range:** {min_r:,.0f}–{max_r:,.0f} (Score {cur_s:,.0f})")
            if adv_text_parts:
                embed.add_field(name="🎯 Military Advantage", value="\n".join(adv_text_parts), inline=False)

            nation_name = self.nation.get('nation_name', 'Unknown Nation')
            cities_list = self.nation.get('cities', [])
            cities = len(cities_list) if isinstance(cities_list, list) else 0
            score = self.nation.get('score', 0)
            if len(str(nation_name)) > 50:
                nation_name = str(nation_name)[:47] + "..."
            footer_text = f"{nation_name} • Cities: {cities} • Score: {score:,.2f}"
            embed.set_footer(text=footer_text)
            return embed
        except Exception as e:
            self.search_cog._log_error("Error generating nation military embed", e, "SearchNationMilitaryView.generate_nation_military_embed")
            return discord.Embed(title="❌ Military Error", description=f"Failed to generate military analysis: {str(e)}", color=discord.Color.red())

    @discord.ui.button(label="Back to Nation", style=discord.ButtonStyle.primary, emoji="🏠")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
            view = NationSearchView(self.author_id, self.bot, self.search_cog, self.nation)
            embed = self.search_cog.create_comprehensive_nation_embed(self.nation)
            await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)
        except Exception as e:
            self.search_cog._log_error("Error in back_button (Military)", e, "SearchNationMilitaryView.back_button")
            await interaction.followup.send(embed=discord.Embed(title="❌ Error", description=str(e), color=discord.Color.red()))


class SearchNationImprovementsView(discord.ui.View):
    """View for displaying improvements breakdown for a single nation (search context)."""

    def __init__(self, author_id: int, bot: commands.Bot, search_cog: 'ShowCog', nation: Dict[str, Any]):
        super().__init__()
        self.author_id = author_id
        self.bot = bot
        self.search_cog = search_cog
        self.nation = nation

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You are not authorized to use this menu.", ephemeral=True)
            return False
        return True

    async def generate_nation_improvements_embed(self):
        try:
            improvements_data = self.search_cog.calculate_nation_improvements(self.nation)
            embed = discord.Embed(
                title=f"🏗️ Improvements Breakdown - {self.nation.get('nation_name', 'Unknown Nation')}",
                description=f"**Total Improvements:** {improvements_data.get('total_improvements', 0):,}",
                color=discord.Color.green()
            )

            power_value = f"Power Plants: {improvements_data.get('total_power', 0):,}"
            if improvements_data.get('total_power', 0) > 0:
                power_value += f" ({improvements_data.get('total_power', 0) * 500:,} MW)"
            embed.add_field(name="⚡ Power", value=power_value, inline=True)

            resource_improvements = []
            for key, label in [
                ('oilwell', 'Oil Well'),
                ('coalmine', 'Coal Mine'),
                ('uramine', 'Uranium Mine'),
                ('ironmine', 'Iron Mine'),
                ('bauxitemine', 'Bauxite Mine'),
                ('leadmine', 'Lead Mine'),
                ('farm', 'Farm'),
            ]:
                if improvements_data.get(key, 0) > 0:
                    resource_improvements.append(f"{label}: {improvements_data.get(key, 0):,}")
            if resource_improvements:
                embed.add_field(name="⛏️ Resources", value="\n".join(resource_improvements), inline=False)

            manufacturing_improvements = []
            for key, label in [
                ('gasrefinery', 'Gas Refinery'),
                ('steelmill', 'Steel Mill'),
                ('aluminumrefinery', 'Aluminum Refinery'),
                ('munitionsfactory', 'Munitions Factory'),
            ]:
                if improvements_data.get(key, 0) > 0:
                    manufacturing_improvements.append(f"{label}: {improvements_data.get(key, 0):,}")
            if manufacturing_improvements:
                embed.add_field(name="🏭 Manufacturing", value="\n".join(manufacturing_improvements), inline=False)

            military_improvements = []
            for key, label in [
                ('barracks', 'Barracks'),
                ('factory', 'Factory'),
                ('hangar', 'Hangar'),
                ('drydock', 'Drydock'),
            ]:
                if improvements_data.get(key, 0) > 0:
                    military_improvements.append(f"{label}: {improvements_data.get(key, 0):,}")
            if military_improvements:
                embed.add_field(name="⚔️ Military", value="\n".join(military_improvements), inline=False)

            civil_improvements = []
            for key, label in [
                ('policestation', 'Police Station'),
                ('hospital', 'Hospital'),
                ('subway', 'Subway'),
                ('recyclingcenter', 'Recycling Center'),
                ('bank', 'Bank'),
                ('supermarket', 'Supermarket'),
                ('shopping_mall', 'Shopping Mall'),
                ('stadium', 'Stadium'),
            ]:
                if improvements_data.get(key, 0) > 0:
                    civil_improvements.append(f"{label}: {improvements_data.get(key, 0):,}")
            if civil_improvements:
                embed.add_field(name="🏢 Civil", value="\n".join(civil_improvements), inline=False)

            nation_name = str(self.nation.get('nation_name', 'Unknown Nation'))
            cities_list = self.nation.get('cities', [])
            cities = len(cities_list) if isinstance(cities_list, list) else 0
            score = self.nation.get('score', 0)
            if len(nation_name) > 50:
                nation_name = nation_name[:47] + "..."
            footer_text = f"{nation_name} • Cities: {cities} • Score: {score:,.2f}"
            embed.set_footer(text=footer_text)
            return embed
        except Exception as e:
            self.search_cog._log_error("Error generating nation improvements embed", e, "SearchNationImprovementsView.generate_nation_improvements_embed")
            return discord.Embed(title="❌ Improvements Error", description=f"Failed to generate improvements breakdown: {str(e)}", color=discord.Color.red())

    @discord.ui.button(label="Back to Nation", style=discord.ButtonStyle.primary, emoji="🏠")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
            view = NationSearchView(self.author_id, self.bot, self.search_cog, self.nation)
            embed = await self.search_cog.create_comprehensive_nation_embed(self.nation)
            await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)
        except Exception as e:
            self.search_cog._log_error("Error in back_button (Improvements)", e, "SearchNationImprovementsView.back_button")
            await interaction.followup.send(embed=discord.Embed(title="❌ Error", description=str(e), color=discord.Color.red()))

async def setup(bot: commands.Bot):
    """Setup function to add the ShowCog to the bot."""
    try:
        await bot.add_cog(ShowCog(bot))
    except Exception as e:
        logging.getLogger(__name__).warning(f"show.py setup: failed to add cog: {e}")
    # Ensure slash command is registered in the tree
    try:
        # Avoid duplicates; register if not present
        existing = [cmd for cmd in bot.tree.get_commands() if getattr(cmd, 'name', '') == 'show']
        if not existing:
            cog = bot.get_cog('ShowCog')
            if cog:
                # Prefer the cog's hybrid command attribute when available
                if hasattr(cog, 'show_command'):
                    try:
                        bot.tree.add_command(cog.show_command)
                        logging.getLogger(__name__).info("show.py setup: 'show' command added to tree")
                    except Exception:
                        # Fallback: search cog's app commands list
                        for maybe_cmd in getattr(cog, '__cog_app_commands__', []):
                            try:
                                if isinstance(maybe_cmd, app_commands.Command) and maybe_cmd.name == 'show':
                                    bot.tree.add_command(maybe_cmd)
                                    logging.getLogger(__name__).info("show.py setup: 'show' app command added to tree (fallback)")
                                    break
                            except Exception:
                                continue
        # Global sync handled elsewhere; avoid redundant per-cog sync here
    except Exception as e:
        logging.getLogger(__name__).warning(f"show.py setup: command registration/sync issue: {e}")

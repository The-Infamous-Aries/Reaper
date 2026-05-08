import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import os
import re
from typing import List, Dict, Any, Optional, Tuple, cast
from datetime import datetime
import sys
import logging
import traceback
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from Systems.PnW.Util.query import create_v3_query_instance, V3GraphQuery
from Systems.Functions.config import PANDW_API_KEY
from Systems.Functions.user_data_manager import UserDataManager
from Systems.PnW.Util.calc import AllianceCalculator
from Systems.Functions import emoji as emoji_mod
from Systems.Functions.emoji import improvement_emoji_map, mention
from Systems.Functions.nation_emoji_store import get_nation_emoji, strip_emoji_prefix
from pathlib import Path

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
                self.logger.setLevel(logging.DEBUG)
            self.error_count = 0
            self.max_errors = 100
            self.query_instance: Optional[V3GraphQuery] = None
            self.calculator: Optional[AllianceCalculator] = None
            self._cached_military_analysis: Optional[Dict[str, Any]] = None
            self._cached_nation_id_for_military: Optional[str] = None
            
            # Cache for autocomplete performance
            self._nations_cache: List[Dict[str, Any]] = []
            self._cache_timestamp: float = 0
            self._cache_ttl: float = 300  # 5 minutes
            
            # Initialize query instance
            try:
                self.query_instance = create_v3_query_instance()
                self.logger.info("Centralized query instance initialized successfully")
                if hasattr(self.query_instance, 'cache_ttl_seconds'):
                    self.query_instance.cache_ttl_seconds = 3600
            except Exception as e:
                self.logger.error(f"Failed to initialize query instance: {e}")
                self.query_instance = None

            # Initialize calculator
            try:
                self.calculator = AllianceCalculator(self.query_instance)
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


    async def _get_nights_watch_nations(self) -> List[Dict[str, Any]]:
        """Get all NW nations from GlobalNations.db with caching."""
        import time
        current_time = time.time()

        # Return cached data if still valid
        if (self._nations_cache and
                current_time - self._cache_timestamp < self._cache_ttl):
            return self._nations_cache

        try:
            from PnWHarvester.db.global_nations_db import GlobalNationsDB
            from Systems.Functions.db_paths import GLOBAL_NATIONS_DB, NW_ALLIANCE_ID
            db = GlobalNationsDB(str(GLOBAL_NATIONS_DB))
            nations = await db.get_nations_by_alliance(NW_ALLIANCE_ID)

            # Update cache
            self._nations_cache = nations
            self._cache_timestamp = current_time

            return nations
        except Exception as e:
            self.logger.error(f"Error getting NW nations: {e}")
            # Return cached data if available, even if expired
            return self._nations_cache if self._nations_cache else []

    async def refresh_nations_cache(self):
        """Force refresh the nations cache."""
        try:
            from PnWHarvester.db.global_nations_db import GlobalNationsDB
            from Systems.Functions.db_paths import GLOBAL_NATIONS_DB, NW_ALLIANCE_ID
            db = GlobalNationsDB(str(GLOBAL_NATIONS_DB))
            nations = await db.get_nations_by_alliance(NW_ALLIANCE_ID)

            import time
            self._nations_cache = nations
            self._cache_timestamp = time.time()

            self.logger.info(f"Nations cache refreshed with {len(nations)} NW nations")
        except Exception as e:
            self.logger.error(f"Error refreshing nations cache: {e}")

    async def _get_nation_from_db(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Look up a nation from GlobalNations.db by name, leader name, or ID.
        GlobalNations.db is the single source of truth — it contains all nations
        including Nights Watch members.
        """
        try:
            from PnWHarvester.db.global_nations_db import GlobalNationsDB
            from Systems.Functions.db_paths import GLOBAL_NATIONS_DB

            db = GlobalNationsDB(str(GLOBAL_NATIONS_DB))

            async def _attach_cities(nation):
                nation['cities'] = await db.get_cities_for_nation(int(nation['id']))
                return nation

            if query.isdigit():
                nation = await db.get_nation(int(query))
                if nation:
                    return await _attach_cities(nation)
                return None

            # Name search — GlobalNationsDB has an indexed get_nation_by_name
            nation = await db.get_nation_by_name(query)
            if nation:
                return await _attach_cities(nation)

            return None
        except Exception as e:
            self.logger.error(f"Error getting nation from DB: {e}")
            return None

    async def show_target_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Optimized autocomplete for show command — All nations from local databases."""
        try:
            from Systems.Functions.autocomplete_utils import nation_autocomplete
            return await nation_autocomplete(current, nw_only=False, limit=25)
        except Exception as e:
            self.logger.error(f"Error in show autocomplete: {e}")
            return []

    def _log_error(self, error_msg: str, exception: Optional[Exception] = None, context: str = ""):
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
            
            # For single-word inputs, try nation name first (more common case)
            # Single words could be either nation names or leader names
            return None, 'nation_name'
        except Exception as e:
            self._log_error(f"Error in parse_target_input: {str(e)}", e, "parse_target_input")
            return None, 'leader_name'

    async def fetch_external_nation_with_wars(self, target_data: str, input_type: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a non-EP nation from the P&W API including their last inactive war
        and all attacks so loot can be calculated.  Marks the result with
        _is_external=True so the view knows to show the Loot button.
        """
        if not self.query_instance:
            return None
        try:
            nation_fields = self.query_instance._nation_fields()
            war_attack_fields = (
                "id date type att_id def_id "
                "money_looted coal_looted oil_looted uranium_looted iron_looted "
                "bauxite_looted lead_looted gasoline_looted munitions_looted "
                "steel_looted aluminum_looted food_looted"
            )
            war_fields = (
                "id date end_date war_type winner_id att_id def_id "
                "att_money_looted def_money_looted "
                f"attacks {{ {war_attack_fields} }}"
            )

            bankrec_fields = (
                "id date sender_id sender_type receiver_id receiver_type "
                "money coal oil uranium iron bauxite lead "
                "gasoline munitions steel aluminum food"
            )
            bankrecs_fragment = (
                f"bankrecs(limit:30 orderBy:{{column:DATE order:DESC}}) "
                f"{{ {bankrec_fields} }}"
            )

            if input_type in ('nation_id', 'nation_link'):
                gql = (
                    f"{{ nations(first:1 id:{target_data}) "
                    f"{{ data {{ {nation_fields} "
                    f"wars(limit:1 status:INACTIVE orderBy:{{column:DATE order:DESC}}) "
                    f"{{ {war_fields} }} "
                    f"{bankrecs_fragment} }} }} }}"
                )
            elif input_type == 'nation_name':
                safe = target_data.replace('"', '\\"')
                gql = (
                    f'{{ nations(first:1 nation_name:"{safe}") '
                    f"{{ data {{ {nation_fields} "
                    f"wars(limit:1 status:INACTIVE orderBy:{{column:DATE order:DESC}}) "
                    f"{{ {war_fields} }} "
                    f"{bankrecs_fragment} }} }} }}"
                )
            else:  # leader_name
                safe = target_data.replace('"', '\\"')
                gql = (
                    f'{{ nations(first:1 leader_name:"{safe}") '
                    f"{{ data {{ {nation_fields} "
                    f"wars(limit:1 status:INACTIVE orderBy:{{column:DATE order:DESC}}) "
                    f"{{ {war_fields} }} "
                    f"{bankrecs_fragment} }} }} }}"
                )

            raw = await self.query_instance._request_with_retries(gql, timeout=30)
            nations = (raw or {}).get('data', {}).get('nations', {}).get('data', [])
            if not nations:
                return None
            nation = nations[0]
            nation['_is_external'] = True
            return nation
        except Exception as e:
            self._log_error("Error fetching external nation with wars", e, "fetch_external_nation_with_wars")
            return None

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

            # Use appropriate method from query instance based on input type
            target_nation = None
            try:
                if input_type == 'nation_id' or input_type == 'nation_link':
                    # For nation ID, we already have the ID from parsing
                    if input_type == 'nation_link':
                        nation_id = int(target_data)  # This is already extracted from the link
                    else:
                        nation_id = int(target_data)
                    target_nation = await self.query_instance.get_nation_by_id(str(nation_id))
                elif input_type == 'nation_name':
                    target_nation = await self.query_instance.get_nation_by_name(target_data)
                    # If nation name search fails and it's a single word, try leader name
                    if not target_nation and ' ' not in target_data:
                        self.logger.info(f"No nation found by name '{target_data}', trying as leader name")
                        target_nation = await self.query_instance.get_nation_by_leader(target_data)
                elif input_type == 'leader_name':
                    target_nation = await self.query_instance.get_nation_by_leader(target_data)
                    # If leader name search fails and it's a single word, try nation name
                    if not target_nation and ' ' not in target_data:
                        self.logger.info(f"No nation found by leader name '{target_data}', trying as nation name")
                        target_nation = await self.query_instance.get_nation_by_name(target_data)
                
                if not target_nation:
                    # More specific logging for single-word inputs
                    if ' ' not in target_data and input_type in ['nation_name', 'leader_name']:
                        self.logger.info(f"No nation found for '{target_data}' as {input_type} (and tried alternative)")
                    else:
                        self.logger.info(f"No nation found for {input_type}: {target_data}")
                    return None
                
                self.logger.info(f"Successfully fetched nation: {target_nation.get('nation_name', 'Unknown')}")
                return target_nation
                
            except Exception as e:
                self._log_error("Error fetching nation data from query instance", e, "fetch_target_nation")
                return None
                
        except Exception as e:
            self._log_error("Unexpected error in fetch_target_nation", e, "fetch_target_nation")
            return None

    def _get_nation_achievements(self, nation_stats: Dict[str, Any]) -> List[str]:
        """Determine nation achievements based on stats."""
        achievements = []
        
        alliance_pos = nation_stats.get('alliance_position', '').upper()
        if alliance_pos in ['MEMBER', 'LEADER', 'HEIR', 'OFFICER']:
            achievements.append(emoji_mod.mention('Mem') or '')
        elif alliance_pos == 'APPLICANT':
            achievements.append(emoji_mod.mention('App') or '')

        if nation_stats.get('is_vacation'):
            achievements.append(emoji_mod.mention('VM') or '')
            
        wars_won = nation_stats.get('wars_won', 0)
        if wars_won >= 1000:
            achievements.append(emoji_mod.mention('Rank6') or '')
        elif wars_won >= 750:
            achievements.append(emoji_mod.mention('Rank5') or '')
        elif wars_won >= 500:
            achievements.append(emoji_mod.mention('Rank4') or '')
        elif wars_won >= 250:
            achievements.append(emoji_mod.mention('Rank3') or '')
        elif wars_won >= 100:
            achievements.append(emoji_mod.mention('Rank2') or '')
        elif wars_won >= 50:
            achievements.append(emoji_mod.mention('Rank1') or '')

        commendations = nation_stats.get('commendations', 0)
        if commendations >= 500:
            achievements.append(emoji_mod.mention('Like4') or '')
        elif commendations >= 250:
            achievements.append(emoji_mod.mention('Like3') or '')
        elif commendations >= 100:
            achievements.append(emoji_mod.mention('Like2') or '')
        elif commendations >= 50:
            achievements.append(emoji_mod.mention('Like1') or '')

        denouncements = nation_stats.get('denouncements', 0)
        if denouncements >= 500:
            achievements.append(emoji_mod.mention('Dislike4') or '')
        elif denouncements >= 250:
            achievements.append(emoji_mod.mention('Dislike3') or '')
        elif denouncements >= 100:
            achievements.append(emoji_mod.mention('Dislike2') or '')
        elif denouncements >= 50:
            achievements.append(emoji_mod.mention('Dislike1') or '')

        money_looted = nation_stats.get('money_looted', 0)
        if money_looted >= 25000000000:
            achievements.append(emoji_mod.mention('Pirate5') or '')
        elif money_looted >= 10000000000:
            achievements.append(emoji_mod.mention('Pirate4') or '')
        elif money_looted >= 5000000000:
            achievements.append(emoji_mod.mention('Pirate3') or '')
        elif money_looted >= 2500000000:
            achievements.append(emoji_mod.mention('Pirate2') or '')
        elif money_looted >= 1000000000:
            achievements.append(emoji_mod.mention('Pirate1') or '')

        # You can add a condition for inactivity here, for example:
        # if nation_stats.get('days_inactive', 0) > 14:
        #     achievements.append(emoji_mod.mention('Inactive') or '')
        return [ach for ach in achievements if ach] # Filter out empty strings

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
        
        nation_id = nation.get('nation_id') or nation.get('id')
        flag_url = nation.get('flag_url') or nation.get('flag')

        stats = {}
        military_analysis = {}
        if self.calculator:
            try:
                stats = await asyncio.to_thread(self.calculator.summarize_nation_stats, nation)
                military_analysis = await asyncio.to_thread(self.calculator.analyze_nation_military, nation)
                self._cached_military_analysis = military_analysis
                self._cached_nation_id_for_military = str(nation_id)
            except Exception as e:
                self._log_error(f"Error in show command (Context: create_comprehensive_nation_embed)", e, "create_comprehensive_nation_embed")

        embed = discord.Embed(
            title=f"🏛️ {nation.get('nation_name', 'Unknown Nation')}",
            description=f"**Leader:** {nation.get('leader_name', 'Unknown Leader')}",
            color=discord.Color.from_rgb(0, 150, 255)
        )
        if nation_id:
            embed.url = f"https://politicsandwar.com/nation/id={nation_id}"
            if flag_url:
                embed.set_thumbnail(url=flag_url)
            else:
                embed.set_thumbnail(url=f"https://politicsandwar.com/nation/id={nation_id}/image")

        # Cooldowns
        city_status = "✅ Available" if stats.get('city_cooldown_remaining', 1) == 0 else f"❌ {stats.get('city_cooldown_remaining')} turns"
        project_status = "✅ Available" if stats.get('project_cooldown_remaining', 1) == 0 else f"❌ {stats.get('project_cooldown_remaining')} turns"

        # Format policy/color values — strip enum prefix (e.g. "DomesticPolicy.OPEN_MARKETS" → "Open Markets")
        def _fmt_enum(raw: str) -> str:
            if not raw or raw.lower() == 'unknown':
                return 'Unknown'
            # Strip any "EnumClass." prefix
            if '.' in raw:
                raw = raw.split('.', 1)[-1]
            return raw.replace('_', ' ').title()

        raw_domestic = stats.get('domestic_policy', 'Unknown') or 'Unknown'
        domestic_policy_fmt = _fmt_enum(raw_domestic)
        raw_color = stats.get('color', 'Unknown') or 'Unknown'
        color_fmt = raw_color.replace('_', ' ').title()

        # Project slot calculation
        total_infra_val = stats.get('total_infra', 0) or 0
        infra_slots = int(total_infra_val // 4000)
        base_slots = 1 + infra_slots

        wars_won_val = stats.get('wars_won', 0) or 0
        wars_lost_val = stats.get('wars_lost', 0) or 0
        war_bonus = 1 if (wars_won_val + wars_lost_val) >= 100 else 0

        rdc_bonus = 0
        mrc_bonus = 0
        if nation.get('research_and_development_center'):
            rdc_bonus = 2  # adds 2 slots, costs 1 = net +1
        if nation.get('military_research_center'):
            mrc_bonus = 2  # adds 2 slots, costs 1 = net +1

        total_project_slots = base_slots + war_bonus + rdc_bonus + mrc_bonus

        # Count currently used project slots directly from nation dict fields
        all_project_fields = [
            'advanced_pirate_economy', 'central_intelligence_agency', 'fallout_shelter',
            'guiding_satellite', 'iron_dome', 'military_doctrine', 'military_research_center',
            'military_salvage', 'missile_launch_pad', 'nuclear_launch_facility',
            'nuclear_research_facility', 'pirate_economy', 'propaganda_bureau', 'space_program',
            'spy_satellite', 'surveillance_network', 'vital_defense_system',
            'arms_stockpile', 'bauxite_works', 'clinical_research_center',
            'emergency_gasoline_reserve', 'green_technologies', 'international_trade_center',
            'iron_works', 'mass_irrigation', 'recycling_initiative',
            'specialized_police_training_program', 'telecommunications_satellite',
            'uranium_enrichment_program', 'activity_center', 'advanced_engineering_corps',
            'arable_land_agency', 'bureau_of_domestic_affairs', 'center_for_civil_engineering',
            'government_support_agency', 'research_and_development_center',
            'mars_landing', 'moon_landing'
        ]
        used_slots = sum(1 for f in all_project_fields if nation.get(f))

        # Resolve alliance name — API nested object → DB flat field → alliance_id fallback
        alliance_obj = nation.get('alliance') or {}
        _raw_alliance_name = (
            (alliance_obj.get('name') if isinstance(alliance_obj, dict) else None)
            or stats.get('alliance_name')
            or nation.get('alliance_name')
        )
        if not _raw_alliance_name:
            _aid = nation.get('alliance_id') or (alliance_obj.get('id') if isinstance(alliance_obj, dict) else None)
            if str(_aid or '') == '14225':
                _raw_alliance_name = 'Nights Watch'
        alliance_name = _raw_alliance_name or 'None'

        # Strip enum prefix from alliance_position (e.g. "AlliancePositionEnum.MEMBER" → "Member")
        raw_pos = stats.get('alliance_position', 'Unknown') or 'Unknown'
        alliance_position_fmt = _fmt_enum(raw_pos)

        # Nights Watch emoji for NW members
        _ep_prefix = '🌙 ' if alliance_name == 'Nights Watch' else ''

        basic_stats_list = [
            f"**Alliance:** {_ep_prefix}{alliance_name}",
        ]
        if alliance_name and alliance_name.lower() not in ('none', 'no alliance', ''):
            basic_stats_list.append(f"**Position:** {alliance_position_fmt}")
        # Only show vacation mode line if actually in VM
        if stats.get('is_vacation'):
            vm_turns = stats.get('vacation_mode_turns', 0)
            basic_stats_list.append(f"**Vacation Mode:** {vm_turns} turns")
        basic_stats_list.append(f"**Color:** {color_fmt}")
        if stats.get('is_beige'):
            basic_stats_list.append(f"**Beige Turns:** {stats.get('beige_turns')}")
        avg_infra = stats.get('avg_city_infra', 0)
        total_infra_disp = stats.get('total_infra', 0)
        basic_stats_list.extend([
            f"**Discord:** {stats.get('discord_info', 'Not linked')}",
            f"**Last Active:** {stats.get('last_active_formatted', 'Unknown')}",
            f"**New Project:** {project_status}",
            f"**New City:** {city_status}",
            f"**Cities:** {stats.get('num_cities', 0)}",
            f"**Powered Cities:** {stats.get('powered_cities_count', 0)}/{stats.get('total_cities', 0)}",
            f"**Infra:** {avg_infra:,.0f} / {total_infra_disp:,.0f}",
            f"**Domestic Policy:** {domestic_policy_fmt}",
            f"**Project Slots:** {used_slots}/{total_project_slots}",
        ])
        embed.add_field(name=f"{emoji_mod.mention('Info') or '📊'} Basic Statistics", value="\n".join(basic_stats_list), inline=False)

        # War Stats are shown on the Military page — not on the main embed

        try:
            if self.calculator:
                project_categories = {
                    f"⚔️ War": [
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
                    f"🏭 Industry": [
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
                    f"🏛️ Government": [
                        ('Activity Center', 'activity_center'),
                        ('Advanced Engineering Corps', 'advanced_engineering_corps'),
                        ('Arable Land Agency', 'arable_land_agency'),
                        ('Bureau of Domestic Affairs', 'bureau_of_domestic_affairs'),
                        ('Center Civil Engineering', 'center_for_civil_engineering'),
                        ('Government Support Agency', 'government_support_agency'),
                        ('Research & Development Center', 'research_and_development_center')
                    ],
                    f"👽 Alien": [
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
                        category_mapping = {
                            '⚔️': 'War',
                            '🏭': 'Industry',
                            '🏛️': 'Government',
                            '👽': 'Alien'
                        }
                        # Extract the emoji part from category_key
                        category_emoji = category_key.split()[0] if ' ' in category_key else category_key
                        category_name = category_mapping.get(category_emoji, 'Unknown')
                        strategic_parts.append(f"**{category_name}:**\n{projects_str}")

                strategic_text = "\n".join(strategic_parts) if strategic_parts else "❌ None"
                embed.add_field(name=f"{emoji_mod.mention('Infra') or '🏗️'} Strategic Projects", value=strategic_text, inline=False)
        except Exception as e:
            self._log_error("Error building Strategic Projects section", e, "create_comprehensive_nation_embed")

        achievements = self._get_nation_achievements(stats)
        if achievements:
            embed.add_field(name=f"{emoji_mod.mention('awards') or '🏆'} Achievements", value=' '.join(achievements), inline=False)

        embed.set_footer(text=f"Nation ID: {nation_id} | Searched at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        
        return embed

    @commands.hybrid_command(name='show', description='Show a nation by name, leader, ID, or link and display detailed information')  # type: ignore
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
            if is_slash and interaction is not None and hasattr(interaction, 'response') and not interaction.response.is_done():
                await interaction.response.defer()
            
            nation_id, input_type = await self.parse_target_input(target)
            
            # Strip any emoji prefix from autocomplete selection
            clean_target = strip_emoji_prefix(target)

            db_nation = await self._get_nation_from_db(clean_target)
            if db_nation:
                embed = await self.create_comprehensive_nation_embed(db_nation)
                view = NationSearchView(ctx.author.id, self.bot, self, db_nation)
                if is_slash and interaction is not None and hasattr(interaction, 'followup'):
                    await interaction.followup.send(embed=embed, view=view)
                else:
                    await ctx.send(embed=embed, view=view)
                return

            # Ensure nation_id is a string if it's used as target_data
            target_data_for_fetch = target if input_type in ['nation_name', 'leader_name'] else (str(nation_id) if nation_id is not None else None)

            if target_data_for_fetch is None:
                if interaction and interaction.response: # Ensure interaction and its response are not None
                    await interaction.response.send_message("Could not parse target. Please provide a valid nation name, leader name, nation ID, or P&W link.", ephemeral=True)
                else:
                    await ctx.send("Could not parse target. Please provide a valid nation name, leader name, nation ID, or P&W link.")
                return

            nation_data = await self.fetch_external_nation_with_wars(target_data_for_fetch, input_type)
            # Fallback to standard fetch if the war-enriched query fails
            if not nation_data:
                nation_data = await self.fetch_target_nation(target_data_for_fetch, input_type)

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
                if is_slash and interaction is not None and hasattr(interaction, 'followup'):
                    await interaction.followup.send(embed=embed)
                else:
                    await ctx.send(embed=embed)
                return
            
            embed = await self.create_comprehensive_nation_embed(nation_data)
            view = NationSearchView(ctx.author.id, self.bot, self, nation_data)
            if is_slash and interaction is not None and hasattr(interaction, 'followup'):
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
            if interaction.message: # Check if message is not None
                if embed is not None:
                    await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)
                else:
                    await interaction.followup.edit_message(message_id=interaction.message.id, content="Could not generate military embed.", view=view)
            else:
                # Handle the case where interaction.message is None, perhaps by sending a new message
                if embed is not None:
                    await interaction.followup.send(embed=embed, view=view)
                else:
                    # Fallback if embed is also None
                    await interaction.followup.send("Could not generate military embed.", ephemeral=True)
        except Exception as e:
            self.search_cog._log_error("Error opening Military view", e, "NationSearchView.military_button")
            error_embed = discord.Embed(title="❌ Error", description=str(e), color=discord.Color.red())
            await interaction.followup.send(embed=error_embed, ephemeral=True) # type: ignore

    @discord.ui.button(label="Improvements", style=discord.ButtonStyle.secondary, emoji="🏗️")
    async def improvements_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
            view = SearchNationImprovementsView(self.author_id, self.bot, self.search_cog, self.nation)
            embed = await view.generate_nation_improvements_embed()
            if interaction.message: # Check if message is not None
                if embed is not None:
                    await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)
                else:
                    await interaction.followup.edit_message(message_id=interaction.message.id, content="Could not generate improvements embed.", view=view)
            else:
                # Handle the case where interaction.message is None, perhaps by sending a new message
                if embed is not None:
                    await interaction.followup.send(embed=embed, view=view)
                else:
                    # Fallback if embed is also None
                    await interaction.followup.send("Could not generate improvements embed.", ephemeral=True)
        except Exception as e:
            self.search_cog._log_error("Error opening Improvements view", e, "NationSearchView.improvements_button")
            error_embed = discord.Embed(title="❌ Error", description=str(e), color=discord.Color.red())
            await interaction.followup.send(embed=error_embed, ephemeral=True) # type: ignore

    @discord.ui.button(label="Revenue", style=discord.ButtonStyle.success, emoji="💰")
    async def revenue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
            view = SearchNationRevenueView(self.author_id, self.bot, self.search_cog, self.nation)
            embed = await view.generate_nation_revenue_embed()
            if interaction.message:
                if embed is not None:
                    await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)
                else:
                    await interaction.followup.edit_message(message_id=interaction.message.id, content="Could not generate revenue embed.", view=view)
            else:
                if embed is not None:
                    await interaction.followup.send(embed=embed, view=view)
                else:
                    await interaction.followup.send("Could not generate revenue embed.", ephemeral=True)
        except Exception as e:
            self.search_cog._log_error("Error opening Revenue view", e, "NationSearchView.revenue_button")
            error_embed = discord.Embed(title="❌ Error", description=str(e), color=discord.Color.red())
            await interaction.followup.send(embed=error_embed, ephemeral=True) # type: ignore

    @discord.ui.button(label="Loot", style=discord.ButtonStyle.danger, emoji="⚔️")
    async def loot_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
            nation = self.nation
            # If the nation was loaded from the local DB it won't have war/bankrec data.
            # Fetch it from the API now so the loot calculation has everything it needs.
            if not nation.get('_is_external'):
                nation_id = nation.get('nation_id') or nation.get('id')
                if nation_id:
                    enriched = await self.search_cog.fetch_external_nation_with_wars(
                        str(nation_id), 'nation_id'
                    )
                    if enriched:
                        nation = enriched
                    else:
                        # Fallback: mark as external so loot view still attempts calculation
                        nation = dict(nation)
                        nation['_is_external'] = True
            view = SearchNationLootView(self.author_id, self.bot, self.search_cog, nation)
            prices = await view._get_prices()
            embed = await view.generate_loot_embed(prices)
            if interaction.message:
                await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed, view=view)
        except Exception as e:
            self.search_cog._log_error("Error opening Loot view", e, "NationSearchView.loot_button")
            error_embed = discord.Embed(title="❌ Error", description=str(e), color=discord.Color.red())
            await interaction.followup.send(embed=error_embed, ephemeral=True) # type: ignore


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

    async def generate_nation_military_embed(self) -> Optional[discord.Embed]:
        """Generates an embed for nation military by calling the calculator."""
        if not self.nation or not isinstance(self.nation, dict) or not self.search_cog.calculator:
            return discord.Embed(title="❌ Error", description="Missing nation data or calculator.", color=discord.Color.red())

        try:
            nation_name = self.nation.get('nation_name', 'Unknown Nation')
            nation_id = self.nation.get('nation_id') or self.nation.get('id')

            military_data = None
            if self.search_cog._cached_military_analysis and self.search_cog._cached_nation_id_for_military == str(nation_id):
                military_data = self.search_cog._cached_military_analysis
            else:
                # Offload the analysis to the calculator
                military_data = await asyncio.to_thread(self.search_cog.calculator.analyze_nation_military, self.nation)
                # Cache the result
                self.search_cog._cached_military_analysis = military_data
                self.search_cog._cached_nation_id_for_military = str(nation_id)

            if not military_data:
                return discord.Embed(title="❌ Military Error", description="Failed to analyze military data.", color=discord.Color.red())

            embed = discord.Embed(
                title=f"{emoji_mod.mention('Military') or '⚔️'} {nation_name} - Military",
                color=discord.Color.dark_red()
            )

            # ── War Stats (top of military page) ──────────────────────────────
            def _fmt_enum(raw: str) -> str:
                if not raw or raw.lower() == 'unknown':
                    return 'Unknown'
                if '.' in raw:
                    raw = raw.split('.', 1)[-1]
                return raw.replace('_', ' ').title()

            raw_war_policy = self.nation.get('war_policy', 'Unknown') or 'Unknown'
            war_policy_fmt = _fmt_enum(raw_war_policy)
            money_looted_raw = float(self.nation.get('money_looted', 0) or 0)
            wars_won_n = int(self.nation.get('wars_won', 0) or 0)
            wars_lost_n = int(self.nation.get('wars_lost', 0) or 0)
            total_wars_n = wars_won_n + wars_lost_n
            win_rate_n = (wars_won_n / total_wars_n * 100) if total_wars_n > 0 else 0.0
            mmr_str = military_data.get('mmr_string', None) or 'N/A'
            war_stats_value = (
                f"**War Policy:** {war_policy_fmt}\n"
                f"**Score:** {self.nation.get('score', 0):,}\n"
                f"**MMR:** {mmr_str}\n"
                f"**Espionage Available:** {'✅ Yes' if self.nation.get('espionage_available', False) else '❌ No'}\n"
                f"**Money Looted:** ${money_looted_raw:,.2f}\n"
                f"**Wars Won:** {wars_won_n}\n"
                f"**Wars Lost:** {wars_lost_n}\n"
                f"**Win Rate:** {win_rate_n:.1f}%"
            )
            embed.add_field(name=f"{emoji_mod.mention('wars') or '⚔️'} War Stats", value=war_stats_value, inline=False)

            # Extract relevant data from military_data
            current_units = military_data.get('current_units', {})
            daily_production = military_data.get('daily_production', {})
            analysis = military_data.get('analysis', {})
            purchase_limits = analysis.get('purchase_limits', {})
            military_composition = analysis.get('military_composition', {})
            attack_range = analysis.get('attack_range', {})
            
            military_analysis_parts = []
            if attack_range:
                min_r = attack_range.get('min_score', 0)
                max_r = attack_range.get('max_score', 0)
                cur_s = attack_range.get('nation_score', 0)
                military_analysis_parts.append(f"**Range:** {min_r:,.0f}–{max_r:,.0f} (Score {cur_s:,.0f})")
            military_analysis_text = "\n".join(military_analysis_parts) if military_analysis_parts else "No detailed military analysis available."
            embed.add_field(name="🛡️ Military Analysis", value=military_analysis_text, inline=False)

            # Military Research
            war_research = analysis.get('war_research', {})

            ground_value = (
                f"{emoji_mod.mention('soldier') or '🪖'} **Soldiers:** {current_units.get('soldiers', 0):,}/{purchase_limits.get('soldiers_max', 0):,}\n"
                f"{emoji_mod.mention('soldier') or '🪖'} **Soldiers/Day:** {daily_production.get('soldiers', 0):,}\n"
                f"{emoji_mod.mention('tank') or '🚙'} **Tanks:** {current_units.get('tanks', 0):,}/{purchase_limits.get('tanks_max', 0):,}\n"
                f"{emoji_mod.mention('tank') or '🚙'} **Tanks/Day:** {daily_production.get('tanks', 0):,}\n"
            )
            air_value = (
                f"{emoji_mod.mention('jet') or '🛩️'} **Aircraft:** {current_units.get('aircraft', 0):,}/{purchase_limits.get('aircraft_max', 0):,}\n"
                f"{emoji_mod.mention('jet') or '🛩️'} **Aircraft/Day:** {daily_production.get('aircraft', 0):,}\n"
            )
            sea_value = (
                f"{emoji_mod.mention('ship') or '⚓'} **Ships:** {current_units.get('ships', 0):,}/{purchase_limits.get('ships_max', 0):,}\n"
                f"{emoji_mod.mention('ship') or '⚓'} **Ships/Day:** {daily_production.get('ships', 0):,}\n"
            )
            embed.add_field(name=f"{emoji_mod.mention('LandSup') or '🌎'} Ground Forces", value=ground_value, inline=False)
            embed.add_field(name=f"{emoji_mod.mention('AirSup') or '💨'} Air Forces", value=air_value, inline=False)
            embed.add_field(name=f"{emoji_mod.mention('NavySup') or '🌊'} Naval Forces", value=sea_value, inline=False)

            bomb_value = (
                f"{emoji_mod.mention('missile') or '🚀'} **Missiles:** {current_units.get('missiles', 0):,}\n"
                f"{emoji_mod.mention('missile') or '🚀'} **Missiles/Day:** {daily_production.get('missiles', 0):,}\n"
                f"{emoji_mod.mention('bomb') or '☢️'} **Nukes:** {current_units.get('nukes', 0):,}\n"                
                f"{emoji_mod.mention('bomb') or '☢️'} **Nukes/Day:** {daily_production.get('nukes', 0):,}"
            )
            embed.add_field(name=f"💣 Bombardment", value=bomb_value, inline=False)

            # Military Research
            military_research_text = "No military research data available."
            if war_research:
                    research_parts = []
                    if war_research.get('ground_capacity') is not None:
                        research_parts.append(f"**Ground Capacity:** {war_research['ground_capacity']:,}")
                    if war_research.get('air_capacity') is not None:
                        research_parts.append(f"**Air Capacity:** {war_research['air_capacity']:,}")
                    if war_research.get('naval_capacity') is not None:
                        research_parts.append(f"**Naval Capacity:** {war_research['naval_capacity']:,}")
                    if war_research.get('ground_cost') is not None:
                        research_parts.append(f"**Ground Cost:** {war_research['ground_cost']:,}")
                    if war_research.get('air_cost') is not None:
                        research_parts.append(f"**Air Cost:** {war_research['air_cost']:,}")
                    if war_research.get('naval_cost') is not None:
                        research_parts.append(f"**Naval Cost:** {war_research['naval_cost']:,}")
                    if research_parts:
                        military_research_text = "\n".join(research_parts)

            if military_research_text != "No military research data available.":
                embed.add_field(name=f"🔬 Military Research", value=military_research_text, inline=False)

            cities = len(self.nation.get('cities', []))
            score = self.nation.get('score', 0)
            footer_text = f"{nation_name} • Cities: {cities} • Score: {score:,.2f}"
            embed.set_footer(text=footer_text)

            return embed
        except Exception as e:
            self.search_cog._log_error("Error generating nation military embed", e)
            return discord.Embed(title="❌ Military Error", description=f"Failed to generate military analysis: {str(e)}", color=discord.Color.red())

    @discord.ui.button(label="Back to Nation", style=discord.ButtonStyle.primary, emoji=emoji_mod.get_partial('Home') or "🏠")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
            view = NationSearchView(self.author_id, self.bot, self.search_cog, self.nation)
            embed = await self.search_cog.create_comprehensive_nation_embed(self.nation)
            if interaction.message: # Check if message is not None
                if embed is not None:
                    await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)
                else:
                    await interaction.followup.edit_message(message_id=interaction.message.id, content="Could not generate nation embed.", view=view)
            else:
                # Handle the case where interaction.message is None, perhaps by sending a new message
                if embed is not None:
                    await interaction.followup.send(embed=embed, view=view)
                else:
                    await interaction.followup.send("Could not generate nation embed.", ephemeral=True)
        except Exception as e:
            self.search_cog._log_error("Error in back_button (Military)", e, "SearchNationMilitaryView.back_button")
            error_embed = discord.Embed(title="❌ Error", description=str(e), color=discord.Color.red())
            await interaction.followup.send(embed=error_embed, ephemeral=True) # type: ignore


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

    async def generate_nation_improvements_embed(self) -> Optional[discord.Embed]:
        """Generates an embed for nation improvements by calling the calculator."""
        if not self.nation or not isinstance(self.nation, dict) or not self.search_cog.calculator:
            return None

        try:
            nation_name = self.nation.get('nation_name', 'Unknown Nation')
            
            # Offload the calculation to a separate thread using the calculator
            improvements = await asyncio.to_thread(self.search_cog.calculator.calculate_nation_improvements, self.nation)
            
            if not improvements:
                return None

            embed = discord.Embed(
                title=f"🔧 {nation_name} - Improvements",
                color=discord.Color.blue()
            )
            
            # Summary Improvements
            summary_improvements = [
                f"**Total Improvements:** {improvements.get('total_improvements', 0):,}",
                f"**Number of Cities:** {improvements.get('num_cities', 0):,}",
                f"**Avg Improvements/City:** {improvements.get('avg_improvements_per_city', 0.0):,.2f}"
            ]
            embed.add_field(name=f"📊 Summary", value="\n".join(summary_improvements), inline=False)
            
            improvement_emojis = improvement_emoji_map()
            
            # Power Improvements - Extract from improvements dict
            coal_power = improvements.get('coal_power', 0)
            oil_power = improvements.get('oil_power', 0)
            nuclear_power = improvements.get('uranium_power', 0)
            wind_power = improvements.get('wind_power', 0)
            
            # Build power improvements list, only showing non-zero values
            power_improvements = []
            
            if coal_power > 0:
                power_improvements.append(f"{mention(improvement_emojis.get('coal_power_plant'))} **Coal Power:** {coal_power:,}")
            if oil_power > 0:
                power_improvements.append(f"{mention(improvement_emojis.get('oil_power_plant'))} **Oil Power:** {oil_power:,}")
            if nuclear_power > 0:
                power_improvements.append(f"{mention(improvement_emojis.get('nuclear_power_plant'))} **Nuclear Power:** {nuclear_power:,}")
            if wind_power > 0:
                power_improvements.append(f"{mention(improvement_emojis.get('wind_power_plant'))} **Wind Power:** {wind_power:,}")
            
            # Only add the Power field if there are power plants
            if power_improvements:
                embed.add_field(name=f"Power", value="\n".join(power_improvements), inline=False)

            # Military Improvements
            barracks = improvements.get('barracks', 0)
            factory = improvements.get('factory', 0)
            hangar = improvements.get('hangar', 0)
            drydock = improvements.get('drydock', 0)
            
            # Build military improvements list, only showing non-zero values
            military_improvements = []
            
            if barracks > 0:
                military_improvements.append(f"{mention(improvement_emojis.get('barracks'))} **Barracks:** {barracks:,}")
            if factory > 0:
                military_improvements.append(f"{mention(improvement_emojis.get('factory'))} **Factories:** {factory:,}")
            if hangar > 0:
                military_improvements.append(f"{mention(improvement_emojis.get('hangar'))} **Hangars:** {hangar:,}")
            if drydock > 0:
                military_improvements.append(f"{mention(improvement_emojis.get('drydock'))} **Drydocks:** {drydock:,}")
            
            # Only add the Military field if there are military improvements
            if military_improvements:
                embed.add_field(name=f"Military", value="\n".join(military_improvements), inline=False)

            # Resource Improvements
            coal_mine = improvements.get('coal_mine', 0)
            oil_well = improvements.get('oil_well', 0)
            uranium_mine = improvements.get('uranium_mine', 0)
            iron_mine = improvements.get('iron_mine', 0)
            bauxite_mine = improvements.get('bauxite_mine', 0)
            lead_mine = improvements.get('lead_mine', 0)
            farm = improvements.get('farm', 0)
            steel_mill = improvements.get('steel_mill', 0)
            aluminum_refinery = improvements.get('aluminum_refinery', 0)
            munitions_factory = improvements.get('munitions_factory', 0)
            oil_refinery = improvements.get('oil_refinery', 0)
            
            # Build resource improvements list, only showing non-zero values
            resource_improvements = []
            
            if coal_mine > 0:
                resource_improvements.append(f"{mention(improvement_emojis.get('coal_mine'))} **Coal Mines:** {coal_mine:,}")
            if oil_well > 0:
                resource_improvements.append(f"{mention(improvement_emojis.get('oil_well'))} **Oil Wells:** {oil_well:,}")
            if uranium_mine > 0:
                resource_improvements.append(f"{mention(improvement_emojis.get('uranium_mine'))} **Uranium Mines:** {uranium_mine:,}")
            if iron_mine > 0:
                resource_improvements.append(f"{mention(improvement_emojis.get('iron_mine'))} **Iron Mines:** {iron_mine:,}")
            if bauxite_mine > 0:
                resource_improvements.append(f"{mention(improvement_emojis.get('bauxite_mine'))} **Bauxite Mines:** {bauxite_mine:,}")
            if lead_mine > 0:
                resource_improvements.append(f"{mention(improvement_emojis.get('lead_mine'))} **Lead Mines:** {lead_mine:,}")
            if farm > 0:
                resource_improvements.append(f"{mention(improvement_emojis.get('farm'))} **Farms:** {farm:,}")
            if steel_mill > 0:
                resource_improvements.append(f"{mention(improvement_emojis.get('steel_mill'))} **Steel Mills:** {steel_mill:,}")
            if aluminum_refinery > 0:
                resource_improvements.append(f"{mention(improvement_emojis.get('aluminum_refinery'))} **Aluminum Refineries:** {aluminum_refinery:,}")
            if munitions_factory > 0:
                resource_improvements.append(f"{mention(improvement_emojis.get('munitions_factory'))} **Munitions Factories:** {munitions_factory:,}")
            if oil_refinery > 0:
                resource_improvements.append(f"{mention(improvement_emojis.get('oil_refinery'))} **Oil Refineries:** {oil_refinery:,}")
            
            # Only add the Resources field if there are resource improvements
            if resource_improvements:
                embed.add_field(name=f"Resources", value="\n".join(resource_improvements), inline=False)

            # Civil Improvements
            police_station = improvements.get('police_station', 0)
            hospital = improvements.get('hospital', 0)
            recycling_center = improvements.get('recycling_center', 0)
            subway = improvements.get('subway', 0)
            supermarket = improvements.get('supermarket', 0)
            bank = improvements.get('bank', 0)
            shopping_mall = improvements.get('shopping_mall', 0)
            stadium = improvements.get('stadium', 0)
            
            # Build civil improvements list, only showing non-zero values
            civil_improvements = []
            
            if police_station > 0:
                civil_improvements.append(f"{mention(improvement_emojis.get('police_station'))} **Police Stations:** {police_station:,}")
            if hospital > 0:
                civil_improvements.append(f"{mention(improvement_emojis.get('hospital'))} **Hospitals:** {hospital:,}")
            if recycling_center > 0:
                civil_improvements.append(f"{mention(improvement_emojis.get('recycling_center'))} **Recycling Centers:** {recycling_center:,}")
            if subway > 0:
                civil_improvements.append(f"{mention(improvement_emojis.get('subway'))} **Subways:** {subway:,}")
            if supermarket > 0:
                civil_improvements.append(f"{mention(improvement_emojis.get('supermarket'))} **Supermarkets:** {supermarket:,}")
            if bank > 0:
                civil_improvements.append(f"{mention(improvement_emojis.get('bank'))} **Banks:** {bank:,}")
            if shopping_mall > 0:
                civil_improvements.append(f"{mention(improvement_emojis.get('shopping_mall'))} **Shopping Malls:** {shopping_mall:,}")
            if stadium > 0:
                civil_improvements.append(f"{mention(improvement_emojis.get('stadium'))} **Stadiums:** {stadium:,}")
            
            # Only add the Econ field if there are civil improvements
            if civil_improvements:
                embed.add_field(name=f"Econ", value="\n".join(civil_improvements), inline=False)

            return embed

        except Exception as e:
            self.search_cog._log_error("Error generating nation improvements embed", e, "generate_nation_improvements_embed")
            return None

    @discord.ui.button(label="Back to Nation", style=discord.ButtonStyle.primary, emoji=emoji_mod.get_partial('Home') or "🏠")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
            view = NationSearchView(self.author_id, self.bot, self.search_cog, self.nation)
            embed = await self.search_cog.create_comprehensive_nation_embed(self.nation)
            if interaction.message: # Check if message is not None
                if embed is not None:
                    await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)
                else:
                    await interaction.followup.edit_message(message_id=interaction.message.id, content="Could not generate nation embed.", view=view)
            else:
                # Handle the case where interaction.message is None, perhaps by sending a new message
                if embed is not None:
                    await interaction.followup.send(embed=embed, view=view)
                else:
                    await interaction.followup.send("Could not generate nation embed.", ephemeral=True)
        except Exception as e:
            self.search_cog._log_error("Error in back_button (Improvements)", e, "SearchNationImprovementsView.back_button")
            error_embed = discord.Embed(title="❌ Error", description=str(e), color=discord.Color.red())
            await interaction.followup.send(embed=error_embed, ephemeral=True) # type: ignore

class SearchNationRevenueView(discord.ui.View):
    """View for displaying revenue breakdown for a single nation (reuses already-loaded nation data)."""

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

    async def generate_nation_revenue_embed(self) -> Optional[discord.Embed]:
        """Generate a revenue embed using the existing nation data — no extra API/DB queries."""
        try:
            from Systems.PnW.EA.rev import RevenueCommand
            from Systems.PnW.Util.rev_correct import calculate_full_revenue_with_query
            from Systems.Functions.database_manager import get_latest_resource_prices, get_latest_game_data, get_latest_game_info
            from datetime import timezone

            nation_name = self.nation.get('nation_name', 'Unknown Nation')
            nation_id = self.nation.get('nation_id') or self.nation.get('id')
            flag_url = self.nation.get('flag_url') or self.nation.get('flag')
            color_name = (self.nation.get('color') or 'beige').lower()

            # Load context from DB (no API calls)
            market_prices: Dict[str, float] = {}
            color_map: Dict[str, float] = {}
            game_date = None
            try:
                price_data = await get_latest_resource_prices()
                if price_data:
                    market_prices = {res: p['sell'] for res, p in price_data.items()}
            except Exception:
                pass
            try:
                colors = await get_latest_game_data("colors")
                if colors:
                    color_map = {c['color'].lower(): float(c.get('turn_bonus', 0)) for c in colors}
            except Exception:
                pass
            try:
                from datetime import datetime
                gi = await get_latest_game_info()
                if gi and gi.get('game_date'):
                    parsed = datetime.fromisoformat(gi['game_date'].replace("Z", "+00:00"))
                    game_date = parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
            except Exception:
                pass

            color_bonus = color_map.get(color_name, 0.0)

            # War detection
            at_war = (
                (self.nation.get('offensive_wars_count') or 0) > 0 or
                (self.nation.get('defensive_wars_count') or 0) > 0
            )
            wars = self.nation.get('wars') or []
            if wars:
                at_war = any(w.get('turnsleft', 0) > 0 for w in wars)

            rev_data = await calculate_full_revenue_with_query(
                nation_data=self.nation,
                query_instance=None,
                is_war=at_war,
                radiation_index=self.nation.get('radiation_index', 1000.0),
                domestic_policy=self.nation.get('domestic_policy', ''),
                color_bonus=color_bonus,
                market_prices=market_prices or None,
                game_date=game_date,
            )

            gross_cash_t = rev_data.get('gross_income', 0)
            gross_cash_d = gross_cash_t * 12
            mil_upkeep_t = rev_data.get('military_upkeep_turn', 0)
            imp_upkeep_t = rev_data.get('improvement_upkeep_turn', 0)
            alliance_tax_t = rev_data.get('alliance_tax_money_turn', 0)
            alliance_tax_r = rev_data.get('alliance_tax_rate', 0)
            net_after_tax_t = rev_data.get('net_income', 0)
            resources = rev_data.get('resources', {})
            prices = rev_data.get('prices', {})
            population = rev_data.get('nationpop', 0)
            color_bonus_t = rev_data.get('color_bonus_turn', 0)
            total_mon_t = rev_data.get('monetary_net_num', gross_cash_t)

            _COLOR_HEX = {
                "beige": 0xDDDDDD, "white": 0xFFFFFF, "grey": 0x808080, "black": 0x000000,
                "gold": 0xFFD700, "pink": 0xFFC0CB, "brown": 0xA52A2A, "mint": 0x98FF98,
                "green": 0x00FF00, "aqua": 0x00FFFF, "lavender": 0xE6E6FA, "lime": 0x00FF00,
                "maroon": 0x800000, "olive": 0x808000, "yellow": 0xFFFF00, "turquoise": 0x40E0D0,
                "red": 0xFF0000, "purple": 0x800080, "orange": 0xFFA500, "blue": 0x0000FF,
            }
            embed_color = _COLOR_HEX.get(color_name, 0x2B2D31)

            embed = discord.Embed(
                title=f"Revenue: {nation_name}",
                url=f"https://politicsandwar.com/nation/id={nation_id}" if nation_id else None,
                color=embed_color,
            )
            if flag_url:
                embed.set_thumbnail(url=flag_url)

            def ftd(per_turn: float, prefix: str = '') -> str:
                return f"{prefix}{per_turn:,.2f}/t\u2002|\u2002{prefix}{per_turn*12:,.2f}/d"

            embed.description = (
                f"**Population:** {population:,}\n"
                f"**Color Bonus:** {ftd(color_bonus_t, '$')}"
            )

            embed.add_field(
                name="Upkeep",
                value=(
                    f"**Military:** {ftd(-mil_upkeep_t, '$')}\n"
                    f"**Improvement:** {ftd(-imp_upkeep_t, '$')}"
                ),
                inline=False,
            )

            tax_note = ""
            if alliance_tax_r > 0:
                tax_note = (
                    f"\n*Tax ({alliance_tax_r*100:.0f}%): "
                    f"-${alliance_tax_t:,.2f}/t "
                    f"→ ${net_after_tax_t:,.2f}/t after tax*"
                )
            embed.add_field(
                name="Net Income (Gross)",
                value=f"**${gross_cash_t:,.2f}/t**\u2002|\u2002**${gross_cash_d:,.2f}/d**{tax_note}",
                inline=False,
            )

            RESOURCE_ORDER = ['food', 'coal', 'oil', 'uranium', 'lead', 'iron', 'bauxite',
                               'gasoline', 'munitions', 'steel', 'aluminum']
            rss_lines = []
            for rss in RESOURCE_ORDER:
                amt_t = resources.get(rss, 0.0)
                if amt_t == 0.0:
                    continue
                sign = "+" if amt_t >= 0 else ""
                rss_emoji = emoji_mod.resource_emoji(rss) or rss.title()
                rss_lines.append(f"{rss_emoji} {sign}{amt_t:,.2f}/t\u2002|\u2002{sign}{amt_t*12:,.2f}/d")
            if rss_lines:
                embed.add_field(name="Resource Net Income", value="\n".join(rss_lines), inline=False)

            embed.add_field(
                name="Total Monetary Value",
                value=f"**${total_mon_t:,.2f}/t**\u2002|\u2002**${total_mon_t*12:,.2f}/d**",
                inline=False,
            )
            embed.set_footer(text="Revenue shown gross (before alliance tax). Tax shown as informational only.")
            return embed

        except Exception as e:
            self.search_cog._log_error("Error generating nation revenue embed", e, "SearchNationRevenueView.generate_nation_revenue_embed")
            return discord.Embed(title="❌ Revenue Error", description=f"Failed to calculate revenue: {str(e)}", color=discord.Color.red())

    @discord.ui.button(label="Back to Nation", style=discord.ButtonStyle.primary, emoji=emoji_mod.get_partial('Home') or "🏠")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
            view = NationSearchView(self.author_id, self.bot, self.search_cog, self.nation)
            embed = await self.search_cog.create_comprehensive_nation_embed(self.nation)
            if interaction.message:
                if embed is not None:
                    await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)
                else:
                    await interaction.followup.edit_message(message_id=interaction.message.id, content="Could not generate nation embed.", view=view)
            else:
                if embed is not None:
                    await interaction.followup.send(embed=embed, view=view)
                else:
                    await interaction.followup.send("Could not generate nation embed.", ephemeral=True)
        except Exception as e:
            self.search_cog._log_error("Error in back_button (Revenue)", e, "SearchNationRevenueView.back_button")
            error_embed = discord.Embed(title="❌ Error", description=str(e), color=discord.Color.red())
            await interaction.followup.send(embed=error_embed, ephemeral=True) # type: ignore


# ── Loot estimation view (external / non-EP nations only) ─────────────────────

_LOOT_MULTIPLIERS = {
    "war_type": {
        "ordinary_war": 0.10,
        "raid":         0.075,
        "attrition_war":0.12,
        "blockade":     0.05,
    },
    "offense": {"pirate": 1.4, "ape": 1.1},
    "defense":  {"fortress": 0.9, "moneybags": 0.6, "turtle": 1.2, "pirate": 1.1},
}
_LOOT_RESOURCES = ["coal", "oil", "uranium", "iron", "bauxite", "lead",
                   "gasoline", "munitions", "steel", "aluminum", "food"]
_TURNS_PER_DAY  = 12


def _loot_turns_since_last_looted(nation: Dict[str, Any]) -> int:
    """Fallback: estimate turns since last loot from war data (used when no holdings row)."""
    from datetime import timezone as _tz
    nation_id = str(nation.get("id", ""))
    for war in sorted(nation.get("wars") or [], key=lambda w: w.get("date") or "", reverse=True):
        if str(war.get("def_id")) != nation_id or str(war.get("winner_id")) == nation_id:
            continue
        for dk in ("end_date", "date"):
            raw = war.get(dk)
            if raw:
                try:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=_tz.utc)
                    return max(0, int((datetime.now(_tz.utc) - dt).total_seconds() / 7200))
                except Exception:
                    pass
        break
    return 0


def _loot_calc_pct(war_policy_def: str, att_pirate: bool, att_ape: bool) -> float:
    """Calculate loot percentage for a raid given attacker/defender policies."""
    base = 0.075  # raid base
    att_mult = 1.4 if att_pirate else 1.0
    if att_ape:
        att_mult *= 1.1
    def_mult = _LOOT_MULTIPLIERS["defense"].get((war_policy_def or "").lower(), 1.0)
    return base * att_mult * def_mult


async def _loot_calculate(nation: Dict[str, Any], prices: Dict[str, float]) -> Dict[str, Any]:
    """
    Holdings-only loot projection.

    Reads holdings.db for the nation's current cash and resources.
    Holdings are already net of all spending and transfers — no revenue
    accumulation is added on top (that would double-count since deduct_spending
    already tracks purchases).

    Falls back to revenue-based estimation ONLY if no holdings row exists.
    """
    from Systems.Functions.db_paths import HOLDINGS_DB_STR
    from PnWHarvester.db.holdings_db import HoldingsDB

    nation_id  = int(nation.get("id") or nation.get("nation_id") or 0)
    def_policy = (nation.get("war_policy") or "").lower()
    if "." in def_policy:
        def_policy = def_policy.rsplit(".", 1)[-1].lower()

    holdings = None
    if nation_id:
        try:
            hdb = HoldingsDB(HOLDINGS_DB_STR)
            holdings = await hdb.get_holdings(nation_id)
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).warning(f"_loot_calculate: holdings lookup failed for {nation_id}: {e}")

    if holdings:
        cash_pool      = max(0.0, float(holdings.get("money_held") or 0))
        rss_pool       = {r: max(0.0, float(holdings.get(f"{r}_held") or 0)) for r in _LOOT_RESOURCES}
        confidence     = holdings.get("confidence", "tracked")
        last_loot_date = holdings.get("last_loot_date")
    else:
        # Fallback: revenue accumulation (no holdings row)
        cash_pt = 0.0
        rss_pt  = {r: 0.0 for r in _LOOT_RESOURCES}
        if nation.get("cities"):
            try:
                from Systems.PnW.Util.rev_correct import calculate_full_revenue_with_query
                rev     = await calculate_full_revenue_with_query(nation_data=nation, is_war=False)
                cash_pt = float(rev.get("gross_income") or 0.0)
                rss_pt  = {r: float((rev.get("resources") or {}).get(r) or 0.0) for r in _LOOT_RESOURCES}
            except Exception:
                pass
        turns = _loot_turns_since_last_looted(nation)
        if turns == 0:
            turns = 7 * _TURNS_PER_DAY
        eff_turns  = min(turns, 30 * _TURNS_PER_DAY)
        cash_pool  = max(0.0, cash_pt * eff_turns)
        rss_pool   = {r: max(0.0, rss_pt.get(r, 0) * eff_turns) for r in _LOOT_RESOURCES}
        confidence = "estimated"
        last_loot_date = None

    rss_pool_value = sum(rss_pool[r] * prices.get(r, 0) for r in _LOOT_RESOURCES)
    total_pool     = cash_pool + rss_pool_value

    def _project(att_pirate: bool, att_ape: bool) -> Dict[str, float]:
        pct       = _loot_calc_pct(def_policy, att_pirate, att_ape)
        p_cash    = cash_pool * pct
        p_rss     = {r: rss_pool[r] * pct for r in _LOOT_RESOURCES}
        p_rss_val = sum(p_rss[r] * prices.get(r, 0) for r in _LOOT_RESOURCES)
        return {
            "pct":       pct,
            "cash":      p_cash,
            "rss":       p_rss,
            "rss_value": p_rss_val,
            "total":     p_cash + p_rss_val,
        }

    return {
        "holdings":        holdings,
        "confidence":      confidence,
        "last_loot_date":  last_loot_date,
        "cash_pool":       cash_pool,
        "rss_pool":        rss_pool,
        "rss_pool_value":  rss_pool_value,
        "total_pool":      total_pool,
        "def_policy":      def_policy,
        "pirate_ape":      _project(True,  True),
        "pirate_only":     _project(True,  False),
        "no_pirate":       _project(False, False),
    }


class SearchNationLootView(discord.ui.View):
    """Loot estimation view for non-EP nations (requires war+attack data from API)."""

    def __init__(self, author_id: int, bot: commands.Bot, search_cog: 'ShowCog', nation: Dict[str, Any]):
        super().__init__()
        self.author_id = author_id
        self.bot = bot
        self.search_cog = search_cog
        self.nation = nation
        self._prices: Dict[str, float] = {}   # populated lazily

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("You are not authorized to use this menu.", ephemeral=True)
            return False
        return True

    async def _get_prices(self) -> Dict[str, float]:
        if self._prices:
            return self._prices
        try:
            import Systems.Functions.database_manager as db_manager
            raw = await db_manager.get_latest_resource_prices()
            if raw:
                self._prices = {k.lower(): v.get("sell", 0) for k, v in raw.items() if v.get("sell", 0) > 0}
        except Exception:
            pass
        return self._prices

    async def generate_loot_embed(self, prices: Optional[Dict[str, float]] = None) -> discord.Embed:
        """Build the loot embed from holdings.db — shows actual holdings and loot scenarios."""
        nation      = self.nation
        nation_name = nation.get('nation_name', 'Unknown Nation')
        nation_id   = nation.get('nation_id') or nation.get('id')
        flag_url    = nation.get('flag_url') or nation.get('flag')

        p      = prices or self._prices or {}
        result = await _loot_calculate(nation, p)

        holdings       = result["holdings"]
        confidence     = result["confidence"]
        last_loot_date = result["last_loot_date"]
        cash_pool      = result["cash_pool"]
        rss_pool       = result["rss_pool"]
        rss_pool_value = result["rss_pool_value"]
        total_pool     = result["total_pool"]
        def_policy_raw = result["def_policy"]
        pirate_ape     = result["pirate_ape"]
        pirate_only    = result["pirate_only"]
        no_pirate      = result["no_pirate"]

        def _fmt_policy(raw: str) -> str:
            if not raw:
                return "Unknown"
            if "." in raw:
                raw = raw.rsplit(".", 1)[-1]
            return raw.replace("_", " ").title()

        def_policy_str = _fmt_policy(def_policy_raw)

        embed = discord.Embed(
            title=f"⚔️ Loot Estimate: {nation_name}",
            url=f"https://politicsandwar.com/nation/id={nation_id}" if nation_id else None,
            color=discord.Color.dark_gold(),
        )
        if flag_url:
            embed.set_thumbnail(url=flag_url)

        # ── Holdings snapshot ─────────────────────────────────────────────────
        if holdings:
            conf_label = {"fresh": "🟢 Fresh", "tracked": "🟡 Tracked", "estimated": "⚪ Estimated"}.get(confidence, confidence)
            last_loot_str = "Unknown"
            if last_loot_date:
                try:
                    from datetime import timezone as _tz
                    ld = datetime.fromisoformat(str(last_loot_date).replace(" ", "T").replace("Z", "+00:00"))
                    if ld.tzinfo is None:
                        ld = ld.replace(tzinfo=_tz.utc)
                    days_ago = (datetime.now(_tz.utc) - ld).days
                    last_loot_str = f"{ld.strftime('%Y-%m-%d')} ({days_ago}d ago)"
                except Exception:
                    last_loot_str = str(last_loot_date)

            embed.add_field(
                name=f"🏦 Holdings ({conf_label})",
                value=(
                    f"**Cash:** ${cash_pool:,.2f}\n"
                    f"**Resources:** ${rss_pool_value:,.2f}\n"
                    f"**Total:** ${total_pool:,.2f}\n"
                    f"**Last loot reset:** {last_loot_str}"
                ),
                inline=False,
            )

            # Resource breakdown — only show non-zero resources
            rss_lines = []
            for r in _LOOT_RESOURCES:
                amt = rss_pool.get(r, 0)
                if amt > 0.01:
                    val = amt * p.get(r, 0)
                    rss_lines.append(f"**{r.title()}:** {amt:,.2f} (${val:,.0f})")
            if rss_lines:
                embed.add_field(
                    name="📦 Resource Holdings",
                    value="\n".join(rss_lines) or "None",
                    inline=False,
                )
        else:
            embed.add_field(
                name="🏦 Holdings",
                value=f"⚪ No holdings data — using revenue estimate\n**Est. Cash Pool:** ${cash_pool:,.2f}\n**Est. Resource Pool:** ${rss_pool_value:,.2f}\n**Total:** ${total_pool:,.2f}",
                inline=False,
            )

        # ── Loot scenarios ────────────────────────────────────────────────────
        embed.add_field(
            name=f"💰 Projected Loot (Defender: {def_policy_str})",
            value=(
                f"**Pirate + APE** ({pirate_ape['pct']*100:.1f}%): **${pirate_ape['total']:,.2f}**\n"
                f"  ↳ Cash: ${pirate_ape['cash']:,.2f} | Resources: ${pirate_ape['rss_value']:,.2f}\n"
                f"**Pirate only** ({pirate_only['pct']*100:.1f}%): **${pirate_only['total']:,.2f}**\n"
                f"  ↳ Cash: ${pirate_only['cash']:,.2f} | Resources: ${pirate_only['rss_value']:,.2f}\n"
                f"**No Pirate** ({no_pirate['pct']*100:.1f}%): **${no_pirate['total']:,.2f}**\n"
                f"  ↳ Cash: ${no_pirate['cash']:,.2f} | Resources: ${no_pirate['rss_value']:,.2f}"
            ),
            inline=False,
        )

        # ── Nation context ────────────────────────────────────────────────────
        score    = nation.get('score', 0)
        cities   = nation.get('num_cities', 0)
        def_wars = nation.get('defensive_wars_count', 0)
        embed.add_field(
            name="🏛️ Nation Info",
            value=(
                f"**Score:** {score:,}\n"
                f"**Cities:** {cities}\n"
                f"**War Policy:** {def_policy_str}\n"
                f"**Active Def. Wars:** {def_wars}/3"
            ),
            inline=False,
        )

        source = "holdings.db + revenue" if holdings else "revenue estimate (no holdings row)"
        embed.set_footer(text=f"Source: {source} | Loot % = base 7.5% × attacker policy × defender policy")
        return embed

    @discord.ui.button(label="Back to Nation", style=discord.ButtonStyle.primary, emoji=emoji_mod.get_partial('Home') or "🏠")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
            view = NationSearchView(self.author_id, self.bot, self.search_cog, self.nation)
            embed = await self.search_cog.create_comprehensive_nation_embed(self.nation)
            if interaction.message:
                await interaction.followup.edit_message(message_id=interaction.message.id, embed=embed, view=view)
            else:
                await interaction.followup.send(embed=embed, view=view)
        except Exception as e:
            self.search_cog._log_error("Error in back_button (Loot)", e, "SearchNationLootView.back_button")
            error_embed = discord.Embed(title="❌ Error", description=str(e), color=discord.Color.red())
            await interaction.followup.send(embed=error_embed, ephemeral=True) # type: ignore


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

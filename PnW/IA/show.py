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
from Systems.PnW.Util.query import create_query_instance, PNWAPIQuery
from config import PANDW_API_KEY, HOME_ALLIANCE_ID
from Systems.Functions.user_data_manager import UserDataManager
from Systems.PnW.Util.calc import AllianceCalculator
from Systems.Functions import emoji as emoji_mod

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
            self.query_instance: Optional[PNWAPIQuery] = None
            self.calculator: Optional[AllianceCalculator] = None
            
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


    def _log_error(self, error_msg: str, exception: Optional[Exception] = None, context: str = ""):
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
                elif input_type == 'leader_name':
                    target_nation = await self.query_instance.get_nation_by_leader(target_data)
                
                if not target_nation:
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
        
        nation_id = nation.get('nation_id')
        flag_url = nation.get('flag_url')

        stats = {}
        military_analysis = {}
        if self.calculator:
            try:
                stats = await asyncio.to_thread(self.calculator.summarize_nation_stats, nation)
                military_analysis = await asyncio.to_thread(self.calculator.analyze_nation_military, nation)
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

        basic_stats_list = [
            f"**Alliance:** {stats.get('alliance_name', 'None')}",
            f"**Position:** {stats.get('alliance_position', 'Unknown')}",
            f"**Vacation Mode:** {'Yes' if stats.get('is_vacation') else 'No'}",
            f"**Color:** {stats.get('color', 'Unknown')}"
        ]
        if stats.get('is_beige'):
            basic_stats_list.append(f"**Beige Turns:** {stats.get('beige_turns')}")
        basic_stats_list.extend([
            f"**Discord:** {stats.get('discord_info', 'Not linked')}",
            f"**Last Active:** {stats.get('last_active_formatted', 'Unknown')}",
            f"**New Project:** {project_status}",
            f"**New City:** {city_status}",
            f"**Cities:** {stats.get('num_cities', 0)}",
            f"**Powered Cities:** {stats.get('powered_cities_count', 0)}/{stats.get('total_cities', 0)}",
            f"**Infra Tier:** {stats.get('infra_tier', 'Unknown')}",
            f"**Total Infrastructure:** {stats.get('total_infra', 0):,.0f}",
            f"**Avg Infrastructure/City:** {stats.get('avg_city_infra', 0):,.0f}",
            f"**Domestic Policy:** {stats.get('domestic_policy', 'Unknown')}"
        ])
        embed.add_field(name=f"{emoji_mod.mention('Info') or '📊'} Basic Statistics", value="\n".join(basic_stats_list), inline=False)


        safe_money_looted = stats.get('money_looted', 0)
        wars_won = stats.get('wars_won', 0)
        wars_lost = stats.get('wars_lost', 0)
        war_ratio = stats.get('war_win_ratio', 0.0) # Assuming war_ratio can be float
        mmr_string = (stats.get('mmr_string', None) or 'N/A') # Changed default to 'N/A'

        military_info = (
            f"**War Policy:** {stats.get('war_policy', 'Unknown')}\n"
            f"**Score:** {nation.get('score', 0):,}\n"
            f"**MMR:** {mmr_string}\n"
            f"**Espionage Available:** {'✅ Yes' if nation.get('espionage_available', False) else '❌ No'}\n"
            f"**Money Looted:** ${safe_money_looted:,}\n"
            f"**Wars Won:** {wars_won}\n"
            f"**Wars Lost:** {wars_lost}\n"
            f"**Win Rate:** {war_ratio:.1f}%"
        )
        embed.add_field(name=f"⚔️ War Stats", value=military_info, inline=False)

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

        # Add footer with search info
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
            
            # Ensure nation_id is a string if it's used as target_data
            target_data_for_fetch = target if input_type in ['nation_name', 'leader_name'] else (str(nation_id) if nation_id is not None else None)

            if target_data_for_fetch is None:
                if interaction and interaction.response: # Ensure interaction and its response are not None
                    await interaction.response.send_message("Could not parse target. Please provide a valid nation name, leader name, nation ID, or P&W link.", ephemeral=True)
                else:
                    await ctx.send("Could not parse target. Please provide a valid nation name, leader name, nation ID, or P&W link.")
                return

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

    async def generate_nation_military_embed(self) -> discord.Embed:
        """Generates an embed for nation military by calling the calculator."""
        if not self.nation or not isinstance(self.nation, dict) or not self.search_cog.calculator:
            return discord.Embed(title="❌ Error", description="Missing nation data or calculator.", color=discord.Color.red())

        try:
            nation_name = self.nation.get('nation_name', 'Unknown Nation')
            
            # Offload the analysis to the calculator
            military_data = await asyncio.to_thread(self.search_cog.calculator.analyze_nation_military, self.nation)

            if not military_data:
                return discord.Embed(title="❌ Military Error", description="Failed to analyze military data.", color=discord.Color.red())

            embed = discord.Embed(
                title=f"{emoji_mod.mention('Military') or '⚔️'} {nation_name} - Military",
                color=discord.Color.dark_red()
            )

            # Extract relevant data from military_data
            current_units = military_data.get('current_units', {})
            daily_production = military_data.get('daily_production', {})
            analysis = military_data.get('analysis', {})
            purchase_limits = analysis.get('purchase_limits', {})
            military_composition = analysis.get('military_composition', {})
            attack_range = analysis.get('attack_range', {})
            military_analysis_parts = []
            if attack_range:
                min_r = attack_range.get('min_range', 0)
                max_r = attack_range.get('max_range', 0)
                cur_s = attack_range.get('current_score', 0)
                military_analysis_parts.append(f"**Range:** {min_r:,.0f}–{max_r:,.0f} (Score {cur_s:,.0f})")
            military_analysis_text = "\n".join(military_analysis_parts) if military_analysis_parts else "No detailed military analysis available."
            embed.add_field(name="🛡️ Military Analysis", value=military_analysis_text, inline=False)

            # Military Research
            war_research = analysis.get('war_research', {})

            ground_value = (
                f"{emoji_mod.mention('soldier') or '🪖'} **Soldiers:** {current_units.get('soldiers', 0):,}/{purchase_limits.get('soldiers_max', 0):,}\n"
                f"{emoji_mod.mention('soldier') or '🪖'} **Soldiers:** {daily_production.get('soldiers', 0):,}/day\n"
                f"{emoji_mod.mention('tank') or '🚙'} **Tanks:** {current_units.get('tanks', 0):,}/{purchase_limits.get('tanks_max', 0):,}\n"
                f"{emoji_mod.mention('tank') or '🚙'} **Tanks:** {daily_production.get('tanks', 0):,}/day\n"
            )
            air_value = (
                f"{emoji_mod.mention('jet') or '🛩️'} **Aircraft:** {current_units.get('aircraft', 0):,}/{purchase_limits.get('aircraft_max', 0):,}\n"
                f"{emoji_mod.mention('jet') or '🛩️'} **Aircraft:** {daily_production.get('aircraft', 0):,}/day\n"
            )
            sea_value = (
                f"{emoji_mod.mention('ship') or '⚓'} **Ships:** {current_units.get('ships', 0):,}/{purchase_limits.get('ships_max', 0):,}\n"
                f"{emoji_mod.mention('ship') or '⚓'} **Ships:** {daily_production.get('ships', 0):,}/day\n"
            )
            embed.add_field(name=f"{emoji_mod.mention('LandSup') or '🌎'} Ground Forces", value=ground_value, inline=False)
            embed.add_field(name=f"{emoji_mod.mention('AirSup') or '💨'} Air Forces", value=air_value, inline=False)
            embed.add_field(name=f"{emoji_mod.mention('NavySup') or '�'} Naval Forces", value=sea_value, inline=False)

            bomb_value = (
                f"{emoji_mod.mention('missile') or '🚀'} **Missiles:** {current_units.get('missiles', 0):,}\n"
                f"{emoji_mod.mention('missile') or '🚀'} **Missiles:** {daily_production.get('missiles', 0):,}/day\n"
                f"{emoji_mod.mention('bomb') or '☢️'} **Nukes:** {current_units.get('nukes', 0):,}\n"                
                f"{emoji_mod.mention('bomb') or '☢️'} **Nukes:** {daily_production.get('nukes', 0):,}/day"
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
                        military_research_text = "\\n".join(research_parts)

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
            
            # Offload the calculation to a separate thread
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
            # Power Improvements
            power_improvements = [
                f"**Coal Power:** {improvements.get('coal_power', 0):,}",
                f"**Oil Power:** {improvements.get('oil_power', 0):,}",
                f"**Nuclear Power:** {improvements.get('nuclear_power', 0):,}",
                f"**Wind Power:** {improvements.get('wind_power', 0):,}",
                f"**Total Power:** {improvements.get('total_power', 0):,}"
            ]
            embed.add_field(name=f"⚡ Power", value="\n".join(power_improvements), inline=False)

            # Military Improvements
            military_improvements = [
                f"**Barracks:** {improvements.get('barracks', 0):,}",
                f"**Factories:** {improvements.get('factory', 0):,}"
                f"**Hangars:** {improvements.get('hangar', 0):,}",
                f"**Drydocks:** {improvements.get('drydock', 0):,}"
            ]
            embed.add_field(name=f"🛡️ Military", value="\n".join(military_improvements), inline=False)

            # Resource Improvements
            resource_improvements = [
                f"**Coal Mines:** {improvements.get('coal_mine', 0):,}",
                f"**Oil Wells:** {improvements.get('oil_well', 0):,}",
                f"**Uranium Mines:** {improvements.get('uranium_mine', 0):,}",
                f"**Iron Mines:** {improvements.get('iron_mine', 0):,}",
                f"**Bauxite Mines:** {improvements.get('bauxite_mine', 0):,}",
                f"**Lead Mines:** {improvements.get('lead_mine', 0):,}",
                f"**Farms:** {improvements.get('farm', 0):,}"
                f"**Steel Mills:** {improvements.get('steel_mill', 0):,}",
                f"**Aluminum Refineries:** {improvements.get('aluminum_refinery', 0):,}",
                f"**Munitions Factories:** {improvements.get('munitions_factory', 0):,}",
                f"**Gas Refineries:** {improvements.get('gasrefinery', 0):,}",
            ]
            embed.add_field(name=f"⛏️ Resources", value="\n".join(resource_improvements), inline=False)

            # Civil Improvements
            civil_improvements = [
                f"**Police Stations:** {improvements.get('police_station', 0):,}",
                f"**Hospitals:** {improvements.get('hospital', 0):,}",
                f"**Recycling Centers:** {improvements.get('recycling_center', 0):,}",
                f"**Subways:** {improvements.get('subway', 0):,}",
                f"**Supermarkets:** {improvements.get('supermarket', 0):,}",
                f"**Banks:** {improvements.get('bank', 0):,}",
                f"**Shopping Malls:** {improvements.get('shopping_mall', 0):,}",
                f"**Stadiums:** {improvements.get('stadium', 0):,}"
            ]
            embed.add_field(name=f"🏢 Econ", value="\n".join(civil_improvements), inline=False)

            return embed

        except Exception as e:
            self.search_cog._log_error("Error generating nation improvements embed", e)
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

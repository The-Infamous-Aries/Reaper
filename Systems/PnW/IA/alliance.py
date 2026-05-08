import discord
from discord.ext import commands
from discord import app_commands
import os
import aiofiles
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Any, Optional, Union
from Systems.Functions.emoji import mention
import asyncio
import random
import logging
import traceback
import sys
import time
from pathlib import Path
from types import ModuleType

# Try to import pnwkit, handle gracefully if not available
pnwkit: Optional[ModuleType] = None
try:
    import pnwkit as pnwkit_module # type: ignore
    pnwkit = pnwkit_module
    PNWKIT_AVAILABLE: bool = True
    PNWKIT_ERROR: Optional[str] = None
    PNWKIT_SOURCE: str = "system"
except ImportError as e:
    # Try to use local pnwkit if system version is not available
    try:
        import sys
        import os
        local_packages_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'local_packages')
        if local_packages_dir not in sys.path:
            sys.path.insert(0, local_packages_dir)

        import pnwkit as pnwkit_local
        pnwkit = pnwkit_local
        PNWKIT_AVAILABLE = True
        PNWKIT_ERROR = None
        PNWKIT_SOURCE = "local"
    except ImportError as local_e:
        pnwkit = None
        PNWKIT_AVAILABLE = False
        PNWKIT_ERROR = f"System: {str(e)}, Local: {str(local_e)}"
        PNWKIT_SOURCE = "none"
    except Exception as local_e:
        pnwkit = None
        PNWKIT_AVAILABLE = False
        PNWKIT_ERROR = f"System: {str(e)}, Local unexpected error: {str(local_e)}"
        PNWKIT_SOURCE = "none"
except Exception as e:
    pnwkit = None
    PNWKIT_AVAILABLE = False
    PNWKIT_ERROR = f"Unexpected error: {str(e)}"
    PNWKIT_SOURCE = "none"

# Import json for cache reading
import json

# Import config for API keys and settings
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from Systems.Functions.config import PANDW_API_KEY
from Systems.Functions import emoji as emoji_mod
from Systems.Functions.user_data_manager import UserDataManager

from Systems.PnW.Util.calc import AllianceCalculator, AllianceStats, ImprovementsStats
from Systems.PnW.Util.query import V3GraphQuery
from Systems.Functions.db_paths import GLOBAL_NATIONS_DB

BlocAllianceManager = None

# Define constants for default alliance (can be configured)
DEFAULT_ALLIANCE_ID = os.getenv("DEFAULT_ALLIANCE_ID", "14635")
DEFAULT_ALLIANCE_NAME = os.getenv("DEFAULT_ALLIANCE_NAME", "Death Before Dishonor")
NIGHTS_WATCH_ALLIANCE_ID = "14225"
NIGHTS_WATCH_ALLIANCE_NAME = "Nights Watch"


def _get_global_nations_db():
    """Lazy-load GlobalNationsDB — avoids import errors if harvester isn't installed."""
    try:
        from PnWHarvester.db.global_nations_db import GlobalNationsDB
        if GLOBAL_NATIONS_DB.exists():
            return GlobalNationsDB(str(GLOBAL_NATIONS_DB))
    except Exception:
        pass
    return None

class FullMillView(discord.ui.View):
    """View for displaying Full Mill calculations and alliance data."""

    def __init__(self, author_id: int, bot: commands.Bot, query_instance: V3GraphQuery, calc_instance: AllianceCalculator, nations: List[Dict] = [], target_alliance_id: Optional[str] = None, target_alliance_name: Optional[str] = None):
        super().__init__(timeout=300)  # 5 minute timeout
        self.author_id = author_id
        self.bot = bot
        self.query = query_instance
        self.calc = calc_instance
        self.current_data = None
        self.current_nations = nations or []
        self.target_alliance_id = target_alliance_id or DEFAULT_ALLIANCE_ID
        self.target_alliance_name = target_alliance_name or DEFAULT_ALLIANCE_NAME

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if the interaction is from the command author."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(f"{emoji_mod.mention('Deny')} You cannot use this menu.")
            return False
        return True

    async def generate_full_mill_embed(self, nations: List[Dict] = []) -> discord.Embed:
        """Generate the full mill embed without handling interaction."""
        try:
            # Use provided nations or current nations
            current_nations = nations or self.current_nations

            if not current_nations:
                # Get alliance data based on guild
                guild_alliance_id = self.target_alliance_id
                guild_nations = await self.query.get_alliance_nations(guild_alliance_id)

                current_nations = guild_nations or []
                if not current_nations:
                    return discord.Embed(
                        title=f"{emoji_mod.mention('Deny')} No Alliance Data",
                        description="Failed to retrieve alliance data.",
                        color=discord.Color.red()
                    )
                self.current_nations = current_nations

            # Use ALL − Vacation Mode − APPLICANT for totals
            total_nations = len(current_nations)
            non_vm_non_app = [n for n in current_nations if (((n.get('vacation_mode_turns', 0) or 0) == 0) and ((n.get('alliance_position','') or '').strip().upper() != 'APPLICANT'))]

            # Calculate full mill data for ALL − VM − APPS
            full_mill_data = await self.calc.calculate_full_mill_data(non_vm_non_app)

            # Create Full Mill embed
            embed = discord.Embed(
                title=f"{emoji_mod.mention('IA') or '🏭'} {self.target_alliance_name} Military Analysis",
                description="Alliance military capacity and production analysis (ALL − Vacation Mode − APPS)",
                color=discord.Color.from_rgb(255, 140, 0)
            )

            # Overall statistics
            embed.add_field(
                name=f"📊 Overall Statistics",
                value=(
                    f"**Total Nations:** {total_nations}\n"
                    f"**Active Nations:** {full_mill_data['active_nations']}\n"
                    f"**Total Cities:** {full_mill_data['total_cities']:,}\n"
                    f"**Total Score:** {full_mill_data['total_score']:,}"
                ),
                inline=False
            )

            # Military Units - Current/Max
            embed.add_field(
                name=f"⚔️ Military Units",
                value=(
                    f"{mention('soldier')} **Soldiers:** {full_mill_data['current_soldiers']:,}/{full_mill_data['max_soldiers']:,}\n"
                    f"{mention('tank')} **Tanks:** {full_mill_data['current_tanks']:,}/{full_mill_data['max_tanks']:,}\n"
                    f"{mention('jet')} **Aircraft:** {full_mill_data['current_aircraft']:,}/{full_mill_data['max_aircraft']:,}\n"
                    f"{mention('ship')} **Ships:** {full_mill_data['current_ships']:,}/{full_mill_data['max_ships']:,}"
                ),
                inline=False
            )

            # Daily Production
            embed.add_field(
                name=f"🏭 Daily Production",
                value=(
                    f"{mention('soldier')} **Soldiers:** {full_mill_data['daily_soldiers']:,}/day\n"
                    f"{mention('tank')} **Tanks:** {full_mill_data['daily_tanks']:,}/day\n"
                    f"{mention('jet')} **Aircraft:** {full_mill_data['daily_aircraft']:,}/day\n"
                    f"{mention('ship')} **Ships:** {full_mill_data['daily_ships']:,}/day\n"
                    f"{mention('missile')} **Missiles:** {full_mill_data['daily_missiles']:,}/day\n"
                    f"{mention('bomb')} **Nukes:** {full_mill_data['daily_nukes']:,}/day"
                ),
                inline=False
            )

            # Military unit gaps
            embed.add_field(
                name=f"⚔️ Units Needed",
                value=(
                    f"{mention('soldier')} **Soldiers:** {full_mill_data['soldier_gap']:,}\n"
                    f"{mention('tank')} **Tanks:** {full_mill_data['tank_gap']:,}\n"
                    f"{mention('jet')} **Aircraft:** {full_mill_data['aircraft_gap']:,}\n"
                    f"{mention('ship')} **Ships:** {full_mill_data['ship_gap']:,}"
                ),
                inline=False
            )

            import math
            embed.add_field(
                name=f"⏱️ Time to Max",
                value=(
                    f"{mention('soldier')} **Soldiers:** {math.ceil(full_mill_data['max_soldier_days'])} days ({full_mill_data['max_soldier_nation']})\n"
                    f"{mention('tank')} **Tanks:** {math.ceil(full_mill_data['max_tank_days'])} days ({full_mill_data['max_tank_nation']})\n"
                    f"{mention('jet')} **Aircraft:** {math.ceil(full_mill_data['max_aircraft_days'])} days ({full_mill_data['max_aircraft_nation']})\n"
                    f"{mention('ship')} **Ships:** {math.ceil(full_mill_data['max_ship_days'])} days ({full_mill_data['max_ship_nation']})"
                ),
                inline=False
            )

            embed.set_footer(text=f"Generated at {datetime.now().strftime('%H:%M:%S')} | Use Alliance Totals button to refresh data")

            return embed

        except Exception as e:
            logging.getLogger(__name__).error(f"Error in generate_full_mill_embed: {e}", exc_info=True)
            return discord.Embed(
                title=f"{emoji_mod.mention('Deny')} Full Mill Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )

    @discord.ui.button(label="Improvements", style=discord.ButtonStyle.secondary, emoji='🏗️')
    async def improvements_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show improvements breakdown for all alliance nations."""
        try:
            await interaction.response.defer()

            if not self.current_nations:
                # Fetch alliance data based on guild
                guild_alliance_id = self.target_alliance_id
                nations = await self.query.get_alliance_nations(guild_alliance_id)
                if not nations:
                    embed = discord.Embed(
                        title=f"{emoji_mod.mention('Deny')} No Alliance Data",
                        description="Failed to retrieve alliance data.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                self.current_nations = nations

            # Create ImprovementsView and use its generator method
            view = ImprovementsView(self.author_id, self.bot, self.query, self.calc, self.current_nations or [], target_alliance_id=self.target_alliance_id, target_alliance_name=self.target_alliance_name)
            embed = await view.generate_improvements_embed(self.current_nations or [])

            # Update the message with Improvements embed and switch to ImprovementsView
            if interaction.message is not None:
                message = interaction.message
                await interaction.followup.edit_message(
                    message_id=message.id,
                    embed=embed,
                    view=view
                )
            else:
                await interaction.followup.send(embed=embed, view=view)

        except Exception as e:
            logging.getLogger(__name__).error(f"Error in improvements_button: {e}", exc_info=True)
            embed = discord.Embed(
                title=f"{emoji_mod.mention('Deny')} Improvements Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

    @discord.ui.button(label="Project Totals", style=discord.ButtonStyle.secondary, emoji='🏛️')
    async def project_totals_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show project totals for active nations only (excludes Applicants & VM)."""
        try:
            await interaction.response.defer()

            if not self.current_nations:
                # Fetch alliance data based on guild
                nations = await self.query.get_alliance_nations(self.target_alliance_id)
                if not nations:
                    embed = discord.Embed(
                        title=f"{emoji_mod.mention('Deny')} No Alliance Data",
                        description="Failed to retrieve alliance data.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                self.current_nations = nations

            view = ProjectTotalsView(self.author_id, self.bot, self.query, self.calc, self.current_nations, target_alliance_id=self.target_alliance_id, target_alliance_name=self.target_alliance_name)
            embed = await view.generate_project_totals_embed(self.current_nations)

            if interaction.message is not None:
                message = interaction.message
                await interaction.followup.edit_message(
                    message_id=message.id,
                    embed=embed,
                    view=view
                )
            else:
                await interaction.followup.send(embed=embed, view=view)
        except Exception as e:
            logging.getLogger(__name__).error(f"Error in project_totals_button: {e}", exc_info=True)
            await interaction.followup.send(f"{emoji_mod.mention('Deny')} An error occurred: {str(e)}")

    @discord.ui.button(label="Alliance Totals", style=discord.ButtonStyle.secondary, emoji='🧮')
    async def alliance_totals_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show alliance totals and statistics."""
        try:
            await interaction.response.defer()

            if not self.current_nations:
                # Fetch alliance data based on guild
                nations = await self.query.get_alliance_nations(self.target_alliance_id)
                if not nations:
                    embed = discord.Embed(
                        title=f"{emoji_mod.mention('Deny')} No Alliance Data",
                        description="Failed to retrieve alliance data.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                self.current_nations = nations

            # Create AllianceTotalsView and use its generator method
            view = AllianceTotalsView(self.author_id, self.bot, self.query, self.calc, self.current_nations or [], target_alliance_id=self.target_alliance_id, target_alliance_name=self.target_alliance_name)
            embed = await view.generate_alliance_totals_embed(self.current_nations or [])

            # Update the message with Alliance Totals embed and switch to AllianceTotalsView
            if interaction.message is not None:
                message = interaction.message
                await interaction.followup.edit_message(
                    message_id=message.id,
                    embed=embed,
                    view=view
                )
            else:
                await interaction.followup.send(embed=embed, view=view)

        except Exception as e:
            logging.getLogger(__name__).error(f"Error in alliance_totals_button: {e}", exc_info=True)
            embed = discord.Embed(
                title=f"{emoji_mod.mention('Deny')} Alliance Totals Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

from typing import List, Dict, Optional, Any, Union

class AllianceTotalsView(discord.ui.View):
    """View for displaying Alliance Totals with Full Mill button."""

    def __init__(self, author_id: int, bot: commands.Bot, query_instance: V3GraphQuery, calc_instance: AllianceCalculator, nations: List[Dict] = [], target_alliance_id: Optional[str] = None, target_alliance_name: Optional[str] = None):
        super().__init__(timeout=300)  # 5 minute timeout
        self.author_id = author_id
        self.bot = bot
        self.query = query_instance
        self.calc = calc_instance
        self.current_nations = nations or []
        self.target_alliance_id = target_alliance_id or DEFAULT_ALLIANCE_ID
        self.target_alliance_name = target_alliance_name or DEFAULT_ALLIANCE_NAME
        # Ensure compatibility with bloc-level components that may access bloc_data
        self.bloc_data: Dict[str, Any] = {}

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if the interaction is from the command author."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(f"{emoji_mod.mention('Deny')} You cannot use this menu.")
            return False
        return True

    async def generate_alliance_totals_embed(self, nations: List[Dict] = []) -> discord.Embed:
        """Generate the alliance totals embed without handling interaction."""
        try:
            current_nations = nations or self.current_nations
            if not current_nations:
                # Get alliance data based on guild
                guild_nations = await self.query.get_alliance_nations(self.target_alliance_id)

                current_nations = guild_nations or []
                if not current_nations:
                    return discord.Embed(
                        title=f"{emoji_mod.mention('Deny')} No Alliance Data",
                        description="Failed to retrieve alliance data.",
                        color=discord.Color.red()
                    )
                self.current_nations = current_nations

            is_default_alliance = str(self.target_alliance_id) == str(DEFAULT_ALLIANCE_ID)

            # Calculate resource totals for active nations (excluding vacation mode, applicants, and 14+ days inactive)
            filtered_nations = await self.calc.get_active_nations(current_nations)

            totals = await self.calc.calculate_resource_totals(filtered_nations)

            resources_held = (
                f"💲 **Money:** ${totals['money']:,}\n"
                f"{emoji_mod.mention('credit_1') or '💰'} **Credits:** {totals['credits']:,}\n"
                f"{emoji_mod.mention('gasoline_1') or '⛽'} **Gasoline:** {totals['gasoline']:,}\n"
                f"{emoji_mod.mention('munitions_1') or '🚀'} **Munitions:** {totals['munitions']:,}\n"
                f"{emoji_mod.mention('steel_1') or '🧱'} **Steel:** {totals['steel']:,}\n"
                f"{emoji_mod.mention('aluminum_1') or '📎'} **Aluminum:** {totals['aluminum']:,}\n"
                f"{emoji_mod.mention('food_1') or '🍱'} **Food:** {totals['food']:,}\n"
                f"{emoji_mod.mention('coal_1') or '🌑'} **Coal:** {totals['coal']:,}\n"
                f"{emoji_mod.mention('oil_2') or '🛢️'} **Oil:** {totals['oil']:,}\n"
                f"{emoji_mod.mention('uranium_1') or '☢️'} **Uranium:** {totals['uranium']:,}\n"
                f"{emoji_mod.mention('iron_1') or '⛓️'} **Iron:** {totals['iron']:,}\n"
                f"{emoji_mod.mention('bauxite_1') or '🪨'} **Bauxite:** {totals['bauxite']:,}\n"
                f"{emoji_mod.mention('lead_1') or '🔋'} **Lead:** {totals['lead']:,}"
            )

            if is_default_alliance:
                embed = discord.Embed(
                    title=f"{emoji_mod.mention('credit') or '💰'} {self.target_alliance_name} Resources",
                    description="Current resources held by active members",
                    color=discord.Color.from_rgb(0, 150, 255)
                )
                embed.add_field(name="Resources Held", value=resources_held, inline=False)
                return embed

            # Non-default alliance: full fields view
            # Get active nations for statistics
            active_nations = filtered_nations # Re-use filtered_nations which is active_nations
            # Build simplified active set: ALL - Vacation Mode - APPLICANT
            apps = [n for n in current_nations if ((n.get('alliance_position','') or '').strip().upper() == 'APPLICANT')]
            non_vm_non_app = [n for n in current_nations if (((n.get('vacation_mode_turns', 0) or 0) == 0) and ((n.get('alliance_position','') or '').strip().upper() != 'APPLICANT'))]
            stats_simple: AllianceStats = await self.calc.calculate_alliance_statistics(non_vm_non_app)

            # Calculate averages manually based on simplified active set
            avg_score = stats_simple['total_score'] / stats_simple['total_nations'] if stats_simple['total_nations'] > 0 else 0
            avg_cities = stats_simple['total_cities'] / stats_simple['total_nations'] if stats_simple['total_nations'] > 0 else 0

            embed = discord.Embed(
                title=f"{emoji_mod.mention('Stat') or '📊'} {self.target_alliance_name} Totals",
                description="Comprehensive alliance statistics and capabilities",
                color=discord.Color.from_rgb(0, 150, 255)
            )

            embed.add_field(
                name=f"{emoji_mod.mention('Stat') or '📊'} Nation Counts",
                value=(
                    f"📇 **Total:** {len(current_nations)}\n"
                    f"✅ **Active:** {len(non_vm_non_app)}\n"
                    f"📝 **Applicants:** {len(apps)}\n"
                    f"🧮 **Total Score:** {stats_simple['total_score']:,}\n"
                    f"⚖️ **Average Score:** {avg_score:,.0f}\n"
                    f"🌇 **Total Cities:** {stats_simple['total_cities']:,}\n"
                    f"🌆 **Average Cities:** {avg_cities:.1f}"
                ),
                inline=False
            )

            # Do not show resources for non-default alliances

            # Add categories directly to main embed (replacing old buttons)
            from datetime import datetime as _dt_dt, timedelta as _dt_td, timezone as _dt_tz
            now = _dt_dt.now(_dt_tz.utc)

            async def _make_links(items, with_days=False):
                links = []
                for n in items:
                    nid = n.get('id')
                    name = n.get('nation_name', 'Unknown')

                    if nid:
                        # Add nation link with optional days inactive (no Discord info)
                        if with_days:
                            d = await self.calc.calculate_days_inactive(n.get('last_active'))
                            if isinstance(d, int):
                                links.append(f"[{name}](https://politicsandwar.com/nation/id={nid}) ({d}d)")
                            else:
                                links.append(f"[{name}](https://politicsandwar.com/nation/id={nid})")
                        else:
                            links.append(f"[{name}](https://politicsandwar.com/nation/id={nid})")

                links.sort(key=lambda x: x.lower())
                value = ""
                used = 0
                for link in links:
                    add = ("\n" if value else "") + link  # Single newline for proper spacing between nations
                    if len(value) + len(add) > 1000:
                        remaining = len(links) - used
                        if remaining > 0:
                            value = value + ("\n" if value else "") + f"... and {remaining} more"
                        break
                    value += add
                    used += 1
                if not value:
                    value = "None"
                return value

            # Compute categories - exclude Vacation Mode, APPLICANT nations, and 14+ days inactive
            filtered_nations = await self.calc.get_active_nations(current_nations)
            grey = [n for n in filtered_nations if (n.get('color', '') or '').strip().upper() in ('GREY', 'GRAY')]
            beige = [n for n in filtered_nations if (n.get('color', '') or '').strip().upper() == 'BEIGE']
            vm = [n for n in current_nations if (n.get('vacation_mode_turns', 0) or 0) > 0 and ((n.get('alliance_position', '') or '').strip().upper() != 'APPLICANT')]

            seven_to_thirteen = []
            fourteen_plus = []
            for n in non_vm_non_app:
                last_active_str = n.get('last_active')
                if last_active_str is not None:
                    d = await self.calc.calculate_days_inactive(str(last_active_str))
                else:
                    d = None
                if isinstance(d, int):
                    if 7 <= d < 14:
                        seven_to_thirteen.append(n)
                    elif d >= 14:
                        fourteen_plus.append(n)

            non_applicants = [n for n in current_nations if ((n.get('alliance_position','') or '').strip().upper() != 'APPLICANT')]
            embed.add_field(name=f"⏲️ GREY Nations - Total: {len(grey)}", value=await _make_links(grey), inline=False)
            embed.add_field(name=f"🩼 BEIGE Nations - Total: {len(beige)}", value=await _make_links(beige), inline=False)
            embed.add_field(name=f"🏖️ Vacation Mode - Total: {len(vm)}", value=await _make_links(vm), inline=False)
            embed.add_field(name=f"⏰ Inactive 7–13 Days - Total: {len(seven_to_thirteen)}", value=await _make_links(seven_to_thirteen, with_days=True), inline=False)
            embed.add_field(name=f"📅 Inactive 14+ Days - Total: {len(fourteen_plus)}", value=await _make_links(fourteen_plus, with_days=True), inline=False)

            embed.set_footer(text=f"Generated at {datetime.now().strftime('%H:%M:%S')} | Use other buttons to view different data")

            return embed

        except Exception as e:
            logging.getLogger(__name__).error(f"Error in generate_alliance_totals_embed: {e}", exc_info=True)
            return discord.Embed(
                title=f"{emoji_mod.mention('Deny')} Alliance Totals Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )

    @discord.ui.button(label="Military", style=discord.ButtonStyle.primary, emoji='⚔️')
    async def full_mill_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show full military capacity analysis."""
        try:
            await interaction.response.defer()

            if not self.current_nations:
                # Fetch alliance data if not already loaded
                nations = await self.query.get_alliance_nations(self.target_alliance_id)
                if not nations:
                    embed = discord.Embed(
                        title=f"{emoji_mod.mention('Deny')} No Alliance Data",
                        description="Failed to retrieve alliance data.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                self.current_nations = nations

            # Create FullMillView and generate the embed
            view = FullMillView(self.author_id, self.bot, self.query, self.calc, self.current_nations or [], target_alliance_id=self.target_alliance_id, target_alliance_name=self.target_alliance_name)
            embed = await view.generate_full_mill_embed(self.current_nations or [])

            # Update the message with Full Mill embed and switch to FullMillView
            if interaction.message is not None:
                message = interaction.message
                await interaction.followup.edit_message(
                    message_id=message.id,
                    embed=embed,
                    view=view
                )
            else:
                await interaction.followup.send(embed=embed, view=view)

        except Exception as e:
            logging.getLogger(__name__).error(f"Error in full_mill_button: {e}", exc_info=True)
            embed = discord.Embed(
                title=f"{emoji_mod.mention('Deny')} Full Mill Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

    @discord.ui.button(label="Improvements", style=discord.ButtonStyle.secondary, emoji='🏗️')
    async def improvements_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show improvements breakdown for all alliance nations."""
        try:
            await interaction.response.defer()

            if not self.current_nations:
                # Fetch alliance data if not already loaded
                nations = await self.query.get_alliance_nations(self.target_alliance_id)
                if not nations:
                    embed = discord.Embed(
                        title=f"{emoji_mod.mention('Deny')} No Alliance Data",
                        description="Failed to retrieve alliance data.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                self.current_nations = nations

            # Create ImprovementsView and use its generator method
            view = ImprovementsView(self.author_id, self.bot, self.query, self.calc, self.current_nations, target_alliance_id=self.target_alliance_id, target_alliance_name=self.target_alliance_name)
            embed = await view.generate_improvements_embed(self.current_nations or [])

            # Update the message with Improvements embed and add navigation buttons
            if interaction.message is not None:
                message = interaction.message
                await interaction.followup.edit_message(
                    message_id=message.id,
                    embed=embed,
                    view=view
                )
            else:
                await interaction.followup.send(embed=embed, view=view)

        except Exception as e:
            logging.getLogger(__name__).error(f"Error in improvements_button: {e}", exc_info=True)
            embed = discord.Embed(
                title=f"{emoji_mod.mention('Deny')} Improvements Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

    @discord.ui.button(label="Project Totals", style=discord.ButtonStyle.secondary, emoji='🏛️')
    async def project_totals_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show project totals for active nations only (excludes Applicants & VM)."""
        try:
            await interaction.response.defer()

            if not self.current_nations:
                nations = await self.query.get_alliance_nations(self.target_alliance_id)
                if not nations:
                    embed = discord.Embed(
                        title=f"{emoji_mod.mention('Deny')} No Alliance Data",
                        description="Failed to retrieve alliance data.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                self.current_nations = nations

            view = ProjectTotalsView(self.author_id, self.bot, self.query, self.calc, self.current_nations, target_alliance_id=self.target_alliance_id, target_alliance_name=self.target_alliance_name)
            embed = await view.generate_project_totals_embed(self.current_nations)

            if interaction.message:
                await interaction.followup.edit_message(
                    message_id=interaction.message.id,
                    embed=embed,
                    view=view
                )
        except Exception as e:
            logging.getLogger(__name__).error(f"Error in project_totals_button: {e}", exc_info=True)
            await interaction.followup.send(f"{emoji_mod.mention('Deny')} An error occurred: {str(e)}")

class ImprovementsView(discord.ui.View):
    """View for displaying Improvements Breakdown with navigation buttons."""

    def __init__(self, author_id: int, bot: commands.Bot, query_instance: V3GraphQuery, calc_instance: AllianceCalculator, alliance_cog, nations: Optional[List[Dict]] = None, target_alliance_id: Optional[str] = None, target_alliance_name: Optional[str] = None):
        super().__init__(timeout=300)  # 5 minute timeout
        self.author_id = author_id
        self.bot = bot
        self.query = query_instance
        self.calc = calc_instance
        self.alliance_cog = alliance_cog
        self.current_nations = nations
        self.target_alliance_id = target_alliance_id or DEFAULT_ALLIANCE_ID
        self.target_alliance_name = target_alliance_name or DEFAULT_ALLIANCE_NAME

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if the interaction is from the command author."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(f"{emoji_mod.mention('Deny')} You cannot use this menu.")
            return False
        return True

    async def generate_improvements_embed(self, nations: List[Dict] = []) -> discord.Embed:
        """Generate the improvements breakdown embed without handling interaction."""
        try:
            current_nations = nations or self.current_nations
            if not current_nations:
                # Get alliance data based on guild
                guild_alliance_id = self.target_alliance_id
                guild_nations = await self.query.get_alliance_nations(guild_alliance_id)

                # Fetch alliance data
                current_nations = guild_nations or []
                if not current_nations:
                    return discord.Embed(
                        title=f"{emoji_mod.mention('Deny')} No Alliance Data",
                        description="Failed to retrieve alliance data.",
                        color=discord.Color.red()
                    )
                self.current_nations = current_nations

            # Use ALL − Vacation Mode − APPLICANT for totals
            active_nations = [n for n in current_nations if (((n.get('vacation_mode_turns', 0) or 0) == 0) and ((n.get('alliance_position','') or '').strip().upper() != 'APPLICANT'))]

            # Calculate improvements data for ALL − VM − APPS
            improvements_data = await self.calc.calculate_improvements_data(active_nations)

            # Create Improvements Breakdown embed
            embed = discord.Embed(
                title=f"{emoji_mod.mention('IA') or '🏗️'} {self.target_alliance_name} Improvements Breakdown",
                description="Total improvements across ALL − Vacation Mode − APPS",
                color=discord.Color.from_rgb(34, 139, 34)
            )

            # Power Plants
            embed.add_field(
                name="⚡ Power Plants",
                value=(
                    f"**Coal Power Plant:** {improvements_data['coalpower']:,}\n"
                    f"**Oil Power Plant:** {improvements_data['oilpower']:,}\n"
                    f"**Nuclear Power Plant:** {improvements_data['nuclearpower']:,}\n"
                    f"**Wind Power Plant:** {improvements_data['windpower']:,}\n"
                    f"**Total:** {improvements_data['total_power']:,}"
                ),
                inline=False
            )

            # Raw Resources
            embed.add_field(
                name=f"⛏️ Raw Resources",
                value=(
                    f"**Oil Well:** {improvements_data['oilwell']:,}\n"
                    f"**Coal Mine:** {improvements_data['coalmine']:,}\n"
                    f"**Uranium Mine:** {improvements_data['uramine']:,}\n"
                    f"**Iron Mine:** {improvements_data['ironmine']:,}\n"
                    f"**Bauxite Mine:** {improvements_data['bauxitemine']:,}\n"
                    f"**Lead Mine:** {improvements_data['leadmine']:,}\n"
                    f"**Farm:** {improvements_data['farm']:,}"
                ),
                inline=False
            )

            # Manufacturing
            embed.add_field(
                name=f"🏭 Manufacturing",
                value=(
                    f"**Gas Refinery:** {improvements_data['gasrefinery']:,}\n"
                    f"**Steel Mill:** {improvements_data['steelmill']:,}\n"
                    f"**Aluminum Refinery:** {improvements_data['aluminumrefinery']:,}\n"
                    f"**Munitions Factory:** {improvements_data['munitionsfactory']:,}"
                ),
                inline=False
            )

            # Civil
            embed.add_field(
                name=f"🏛️ Civil",
                value=(
                    f"**Police Station:** {improvements_data['policestation']:,}\n"
                    f"**Hospital:** {improvements_data['hospital']:,}\n"
                    f"**Subway:** {improvements_data['subway']:,}\n"
                    f"**Recycling Center:** {improvements_data['recyclingcenter']:,}"
                ),
                inline=False
            )

            # Commerce
            embed.add_field(
                name=f"💰 Commerce",
                value=(
                    f"**Bank:** {improvements_data['bank']:,}\n"
                    f"**Supermarket:** {improvements_data['supermarket']:,}\n"
                    f"**Shopping Mall:** {improvements_data['shopping_mall']:,}\n"
                    f"**Stadium:** {improvements_data['stadium']:,}"
                ),
                inline=False
            )

            # Military
            embed.add_field(
                name=f"⚔️ Military",
                value=(
                    f"**Barracks:** {improvements_data['barracks']:,}\n"
                    f"**Factory:** {improvements_data['factory']:,}\n"
                    f"**Hangar:** {improvements_data['hangar']:,}\n"
                    f"**Drydock:** {improvements_data['drydock']:,}"
                ),
                inline=False
            )

            # Summary Statistics
            embed.add_field(
                name=f"{emoji_mod.mention('Stat') or '📊'} Summary",
                value=(
                    f"**Total Improvements:** {improvements_data['total_improvements']:,}\n"
                    f"**Total Cities:** {improvements_data['total_cities']:,}\n"
                    f"**Avg per City:** {improvements_data['avg_per_city']:.1f}\n"
                    f"**Active Nations:** {improvements_data['active_nations']:,}"
                ),
                inline=False
            )

            embed.set_footer(text=f"Generated at {datetime.now().strftime('%H:%M:%S')} | Use other buttons to view different data")

            return embed

        except Exception as e:
            self.alliance_cog._log_error(f"Error in generate_improvements_embed: {e}", e, "ImprovementsView.generate_improvements_embed")
            return discord.Embed(
                title=f"{emoji_mod.mention('Deny')} Improvements Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )

    @discord.ui.button(label="Alliance Totals", style=discord.ButtonStyle.secondary, emoji='🧮')
    async def alliance_totals_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show alliance totals and statistics."""
        try:
            await interaction.response.defer()

            if not self.current_nations:
                # Fetch alliance data if not already loaded
                nations = await self.query.get_alliance_nations(self.target_alliance_id)
                if not nations:
                    embed = discord.Embed(
                        title=f"{emoji_mod.mention('Deny')} No Alliance Data",
                        description="Failed to retrieve alliance data.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                self.current_nations = nations

            # Create AllianceTotalsView and use its generator method
            view = AllianceTotalsView(self.author_id, self.bot, self.query, self.calc, self.current_nations or [], target_alliance_id=self.target_alliance_id, target_alliance_name=self.target_alliance_name)
            embed = await view.generate_alliance_totals_embed(self.current_nations or [])

            # Update the message with Alliance Totals embed and switch to AllianceTotalsView
            if interaction.message is not None:
                message = interaction.message
                await interaction.followup.edit_message(
                    message_id=message.id,
                    embed=embed,
                    view=view
                )
            else:
                await interaction.followup.send(embed=embed, view=view)

        except Exception as e:
            logging.getLogger(__name__).error(f"Error in alliance_totals_button: {e}", exc_info=True)
            embed = discord.Embed(
                title=f"{emoji_mod.mention('Deny')} Alliance Totals Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

    @discord.ui.button(label="Project Totals", style=discord.ButtonStyle.secondary, emoji='🏛️')
    async def project_totals_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show project totals for active nations only (excludes Applicants & VM)."""
        try:
            await interaction.response.defer()

            if not self.current_nations:
                nations = await self.query.get_alliance_nations(self.target_alliance_id)
                if not nations:
                    embed = discord.Embed(
                        title=f"{emoji_mod.mention('Deny')} No Alliance Data",
                        description="Failed to retrieve alliance data.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                self.current_nations = nations

            view = ProjectTotalsView(self.author_id, self.bot, self.query, self.calc, self.current_nations, target_alliance_id=self.target_alliance_id, target_alliance_name=self.target_alliance_name)
            embed = await view.generate_project_totals_embed(self.current_nations)

            if interaction.message:
                await interaction.followup.edit_message(
                    message_id=interaction.message.id,
                    embed=embed,
                    view=view
                )
        except Exception as e:
            logging.getLogger(__name__).error(f"Error in project_totals_button: {e}", exc_info=True)
            await interaction.followup.send(f"{emoji_mod.mention('Deny')} An error occurred: {str(e)}")

    @discord.ui.button(label="Military", style=discord.ButtonStyle.secondary, emoji='⚔️')
    async def full_mill_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show full military capacity analysis."""
        try:
            await interaction.response.defer()

            if not self.current_nations:
                # Fetch alliance data if not already loaded
                nations = await self.query.get_alliance_nations(self.target_alliance_id)
                if not nations:
                    embed = discord.Embed(
                        title=f"{emoji_mod.mention('Deny')} No Alliance Data",
                        description="Failed to retrieve alliance data.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                self.current_nations = nations

            # Create FullMillView and generate the embed
            view = FullMillView(self.author_id, self.bot, self.query, self.calc, self.current_nations or [], target_alliance_id=self.target_alliance_id, target_alliance_name=self.target_alliance_name)
            embed = await view.generate_full_mill_embed(self.current_nations or [])

            # Update the message with Full Mill embed and switch to FullMillView
            if interaction.message:
                await interaction.followup.edit_message(
                    message_id=interaction.message.id,
                    embed=embed,
                    view=view
                )

        except Exception as e:
            logging.getLogger(__name__).error(f"Error in full_mill_button: {e}", exc_info=True)
            embed = discord.Embed(
                title=f"{emoji_mod.mention('Deny')} Full Mill Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

class ProjectTotalsView(discord.ui.View):
    """View for displaying Project Totals (active nations only)."""

    def __init__(self, author_id: int, bot: commands.Bot, query_instance: V3GraphQuery, calc_instance: AllianceCalculator, nations: Optional[List[Dict]] = None, target_alliance_id: Optional[str] = None, target_alliance_name: Optional[str] = None):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.bot = bot
        self.query = query_instance
        self.calc = calc_instance
        self.current_nations = nations
        self.target_alliance_id = target_alliance_id or DEFAULT_ALLIANCE_ID
        self.target_alliance_name = target_alliance_name or DEFAULT_ALLIANCE_NAME

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(f"{emoji_mod.mention('Deny')} You cannot use this menu.")
            return False
        return True

    async def generate_project_totals_embed(self, nations: List[Dict] = []) -> discord.Embed:
        try:
            current_nations = nations or self.current_nations
            if not current_nations:
                # Get alliance data dynamically based on guild
                guild_alliance_id = self.target_alliance_id
                if not guild_alliance_id:
                    return discord.Embed(
                        title=f"{emoji_mod.mention('Deny')} No Alliance Data",
                        description="Failed to determine alliance ID for this guild.",
                        color=discord.Color.red()
                    )

                # Get main alliance nations
                current_nations = await self.query.get_alliance_nations(guild_alliance_id)
                current_nations = current_nations or []

            # Use home alliance only by default

                if not current_nations:
                    return discord.Embed(
                        title=f"{emoji_mod.mention('Deny')} No Alliance Data",
                        description="Failed to retrieve alliance data.",
                        color=discord.Color.red()
                    )
                self.current_nations = current_nations

            # Count nations for project totals using ALL − Vacation Mode − APPLICANT
            total_nations = [n for n in current_nations if (((n.get('vacation_mode_turns', 0) or 0) == 0) and ((n.get('alliance_position','') or '').strip().upper() != 'APPLICANT'))]

            def count_project(field: str, group: List[Dict[str, Any]]) -> int:
                try:
                    return sum(1 for n in group if bool(n.get(field, False)))
                except Exception:
                    return 0

            project_categories = {
                f"⚔️ War": [
                    ("Advanced Pirate Economy", "advanced_pirate_economy"),
                    ("Central Intelligence Agency", "central_intelligence_agency"),
                    ("Fallout Shelter", "fallout_shelter"),
                    ("Guiding Satellite", "guiding_satellite"),
                    ("Iron Dome", "iron_dome"),
                    ("Military Doctrine", "military_doctrine"),
                    ("Military Research Center", "military_research_center"),
                    ("Military Salvage", "military_salvage"),
                    ("Missile Launch Pad", "missile_launch_pad"),
                    ("Nuclear Launch Facility", "nuclear_launch_facility"),
                    ("Nuclear Research Facility", "nuclear_research_facility"),
                    ("Pirate Economy", "pirate_economy"),
                    ("Propaganda Bureau", "propaganda_bureau"),
                    ("Space Program", "space_program"),
                    ("Spy Satellite", "spy_satellite"),
                    ("Surveillance Network", "surveillance_network"),
                    ("Vital Defense System", "vital_defense_system")
                ],
                f"🏭 Industry": [
                    ("Arms Stockpile", "arms_stockpile"),
                    ("Bauxite Works", "bauxite_works"),
                    ("Clinical Research Center", "clinical_research_center"),
                    ("Emergency Gasoline Reserve", "emergency_gasoline_reserve"),
                    ("Green Technologies", "green_technologies"),
                    ("International Trade Center", "international_trade_center"),
                    ("Iron Works", "iron_works"),
                    ("Mass Irrigation", "mass_irrigation"),
                    ("Recycling Initiative", "recycling_initiative"),
                    ("Specialized Police Training Program", "specialized_police_training_program"),
                    ("Telecommunications Satellite", "telecommunications_satellite"),
                    ("Uranium Enrichment Program", "uranium_enrichment_program")
                ],
                f"🏛️ Government": [
                    ("Activity Center", "activity_center"),
                    ("Advanced Engineering Corps", "advanced_engineering_corps"),
                    ("Arable Land Agency", "arable_land_agency"),
                    ("Bureau of Domestic Affairs", "bureau_of_domestic_affairs"),
                    ("Center for Civil Engineering", "center_for_civil_engineering"),
                    ("Government Support Agency", "government_support_agency"),
                    ("Research & Development Center", "research_and_development_center")
                ],
                f"👽 Alien": [
                    ("Mars Landing", "mars_landing"),
                    ("Moon Landing", "moon_landing")
                ]
            }

            embed = discord.Embed(
                title=f"🏛️ {self.target_alliance_name} Project Totals",
                description="Total projects across ALL − Vacation Mode − APPS",
                color=discord.Color.from_rgb(100, 181, 246)
            )

            # Add fields with totals for all groups, no emojis
            def add_chunked_field(embed_obj: discord.Embed, base_name: str, line_items: List[str], inline: bool = False):
                """Add one or more embed fields ensuring each value <= 1024 chars.
                Splits by lines and appends an index suffix when chunked."""
                if not line_items:
                    embed_obj.add_field(name=base_name, value="None", inline=inline)
                    return
                chunks = []
                current: List[str] = []
                current_len = 0
                for line in line_items:
                    # +1 for newline separator
                    line_len = len(line) + 1
                    if current_len + line_len > 1024:
                        chunks.append("\n".join(current))
                        current = [line]
                        current_len = line_len
                    else:
                        current.append(line)
                        current_len += line_len
                if current:
                    chunks.append("\n".join(current))
                # Add chunks with suffixes when needed
                if len(chunks) == 1:
                    embed_obj.add_field(name=base_name, value=chunks[0], inline=inline)
                else:
                    for idx, chunk in enumerate(chunks, start=1):
                        embed_obj.add_field(name=f"{base_name} ({idx})", value=chunk, inline=inline)

            lines = []
            # Process projects by category
            for category_name, project_list in project_categories.items():
                category_lines = []
                for display, field in project_list:
                    total = count_project(field, total_nations)
                    category_lines.append(f"**{display}**: {total}")

                if category_lines:  # Only add if category has projects
                    lines.append(f"\n**{category_name}**")
                    lines.extend(category_lines)

            # Auto-chunk into multiple fields named "Projects (n)"
            add_chunked_field(embed, "Projects", lines, inline=False)

            embed.set_footer(text=f"Generated at {datetime.now().strftime('%H:%M:%S')} | Total Nations: {len(total_nations)}")
            return embed
        except Exception as e:
            logging.getLogger(__name__).error(f"Error generating project totals embed: {e}", exc_info=True)
            return discord.Embed(
                title=f"{emoji_mod.mention('Deny')} Project Totals Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )

    @discord.ui.button(label="Alliance Totals", style=discord.ButtonStyle.secondary, emoji='🧮')
    async def alliance_totals_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()

            # Create AllianceTotalsView and use its generator method
            view = AllianceTotalsView(self.author_id, self.bot, self.query, self.calc, self.current_nations or [], target_alliance_id=self.target_alliance_id, target_alliance_name=self.target_alliance_name)
            embed = await view.generate_alliance_totals_embed(self.current_nations or [])

            # Update the message with Alliance Totals embed and switch to AllianceTotalsView
            if interaction.message:
                await interaction.followup.edit_message(
                    message_id=interaction.message.id,
                    embed=embed,
                    view=view
                )
        except Exception as e:
            logging.getLogger(__name__).error(f"Error in alliance_totals_button: {e}", exc_info=True)
            await interaction.followup.send(f"{emoji_mod.mention('Deny')} An error occurred: {str(e)}")

    @discord.ui.button(label="Improvements", style=discord.ButtonStyle.secondary, emoji='🏗️')
    async def improvements_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()

            # Create ImprovementsView and use its generator method
            view = ImprovementsView(self.author_id, self.bot, self.query, self.calc, self.current_nations, target_alliance_id=self.target_alliance_id, target_alliance_name=self.target_alliance_name)
            embed = await view.generate_improvements_embed(self.current_nations or [])

            # Update the message with Improvements embed and switch to ImprovementsView
            if interaction.message:
                await interaction.followup.edit_message(
                    message_id=interaction.message.id,
                    embed=embed,
                    view=view
                )
        except Exception as e:
            logging.getLogger(__name__).error(f"Error in improvements_button: {e}", exc_info=True)
            await interaction.followup.send(f"{emoji_mod.mention('Deny')} An error occurred: {str(e)}")

    @discord.ui.button(label="Military", style=discord.ButtonStyle.secondary, emoji='⚔️')
    async def full_mill_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
            view = FullMillView(self.author_id, self.bot, self.query, self.calc, self.current_nations or [], target_alliance_id=self.target_alliance_id, target_alliance_name=self.target_alliance_name)
            embed = await view.generate_full_mill_embed(self.current_nations or [])
            if interaction.message:
                await interaction.followup.edit_message(
                    message_id=interaction.message.id,
                    embed=embed,
                    view=view
                )
        except Exception as e:
            logging.getLogger(__name__).error(f"Error in full_mill_button: {e}", exc_info=True)
            await interaction.followup.send(f"{emoji_mod.mention('Deny')} An error occurred: {str(e)}")

class AllianceManager(commands.Cog):
    """Alliance Management System for DB4D."""

    def __init__(self, bot: commands.Bot, query_instance: V3GraphQuery, calc_instance: AllianceCalculator):
        self.bot = bot

        # Setup logging
        self.logger = logging.getLogger(f"{__name__}.AllianceManager")
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

        # Error tracking
        self.error_count = 0

        # Initialize UserDataManager (no longer used for cache access)
        self.user_data_manager = UserDataManager()

        self.query_system = query_instance
        self.calc_system = calc_instance

        self.logger.info("AllianceManager initialized successfully")

    def _log_error(self, error_msg: str, exception: Optional[Exception] = None, context: str = ""):
        """Centralized error logging with tracking."""
        self.error_count += 1
        full_msg = f"[Error #{self.error_count}] {error_msg}"
        if context:
            full_msg += f" | Context: {context}"

        if exception:
            full_msg += f" | Exception: {str(exception)}"
            self.logger.error(full_msg)
            self.logger.debug(f"Traceback: {traceback.format_exc()}")
        else:
            self.logger.error(full_msg)

    def _validate_input(self, data: Any, expected_type: type, field_name: str = "data") -> bool:
        """Validate input data type."""
        if not isinstance(data, expected_type):
            self._log_error(f"Invalid {field_name} type. Expected {expected_type.__name__}, got {type(data).__name__}")
            return False
        return True

    def _safe_get(self, data: dict, key: str, default: Any = None, expected_type: Optional[type] = None) -> Any:
        """Safely get value from dictionary with type checking."""
        try:
            value = data.get(key, default)
            if expected_type and value is not None:
                if expected_type in (int, float):
                    return expected_type(value) if value != "" else default
                elif not isinstance(value, expected_type):
                    self._log_error(f"Type mismatch for key '{key}'. Expected {expected_type.__name__}, got {type(value).__name__}")
                    return default
            return value
        except (ValueError, TypeError) as e:
            self._log_error(f"Error getting key '{key}' from data", e)
            return default

    def _get_default_alliance_statistics(self) -> Dict[str, Any]:
        """Return default alliance statistics structure."""
        return {
            'total_nations': 0,
            'total_score': 0,
            'total_cities': 0,
            'avg_score': 0,
            'avg_cities': 0,
            'propaganda_bureau': 0,
            'missile_capable': 0,
            'space_program': 0,
            'iron_dome': 0,
            'nuclear_capable': 0,
            'nuclear_launch_facility': 0,
            'vital_defense_system': 0,
            'military_research_center': 0,
            'total_military': {
                'soldiers': 0, 'tanks': 0, 'aircraft': 0, 'ships': 0, 'missiles': 0, 'nukes': 0
            },
            'production_capacity': {
                'daily_soldiers': 0, 'daily_tanks': 0, 'daily_aircraft': 0, 'daily_ships': 0,
                'max_soldiers': 0, 'max_tanks': 0, 'max_aircraft': 0, 'max_ships': 0
            }
        }

    async def get_alliance_nations(self, alliance_id: Optional[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        if alliance_id is None:
            self.logger.warning("get_alliance_nations: No alliance_id provided, returning empty list.")
            return []
        aid = str(alliance_id)
        nations: List[Dict[str, Any]] = []
        try:
            if self.query_system:
                result = await self.query_system.get_alliance_nations(aid, bot=self.bot, force_refresh=force_refresh)
                nations = result if result is not None else []
                return nations
            self.logger.warning("get_alliance_nations: query_system unavailable")
            return []
        except Exception as e:
            self._log_error(f"Error fetching alliance nations for {aid}", e, "get_alliance_nations")
            return []

    async def get_alliance_id_for_guild(self, guild: Union[discord.Guild, int, str]) -> str:
        """Get the configured alliance ID for a specific guild."""
        # For now, we default to the DB4D alliance ID as multi-tenancy isn't fully implemented
        # In the future, this would query a database or config file
        return DEFAULT_ALLIANCE_ID

    async def get_active_nations(self, nations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter nations to exclude vacation mode and applicant members using centralized logic."""
        return await self.calc_system.get_active_nations(nations)

    async def calculate_nation_statistics(self, nations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate comprehensive nation statistics using centralized logic."""
        return await self.calc_system.calculate_nation_statistics(nations)

    async def calculate_alliance_statistics(self, nations: List[Dict[str, Any]]) -> AllianceStats:
        """Calculate alliance statistics using centralized logic."""
        return await self.calc_system.calculate_alliance_statistics(nations)

    async def calculate_resource_totals(self, nations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate resource totals using centralized logic."""
        return await self.calc_system.calculate_resource_totals(nations)

    async def calculate_full_mill_data(self, nations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate full mill data using centralized logic."""
        return await self.calc_system.calculate_full_mill_data(nations)

    async def calculate_military_purchase_limits(self, nation: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate military purchase limits using centralized logic."""
        return self.calc_system.calculate_military_purchase_limits(nation)

    def get_nation_specialty(self, nation: Dict[str, Any]) -> str:
        """Get nation specialty using centralized logic."""
        return self.calc_system.get_nation_specialty(nation)

    def calculate_combat_score(self, nation: Dict[str, Any]) -> float:
        """Calculate combat score using centralized logic."""
        return self.calc_system.calculate_combat_score(nation)

    def has_project(self, nation: Dict[str, Any], project_name: str) -> bool:
        """Check if nation has a specific project using centralized logic."""
        return self.calc_system.has_project(nation, project_name)

    async def calculate_improvements_data(self, nations: List[Dict[str, Any]]) -> ImprovementsStats:
        """Calculate improvements data using centralized logic."""
        return await self.calc_system.calculate_improvements_data(nations)

    # testalliance command removed

    async def alliance_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for alliance command — All alliances from local databases."""
        try:
            from Systems.Functions.autocomplete_utils import alliance_autocomplete
            return await alliance_autocomplete(current, include_nw=True, limit=25)
        except Exception as e:
            logger.error(f"Error in alliance autocomplete: {e}")
            # Fallback to just IRS
            if not current or current.lower() in NIGHTS_WATCH_ALLIANCE_NAME.lower():
                return [app_commands.Choice(name=f"💰 {NIGHTS_WATCH_ALLIANCE_NAME}", value=NIGHTS_WATCH_ALLIANCE_NAME)]
            return []

    @commands.hybrid_command(name='alliance', description='Display alliance overview')  # type: ignore
    @app_commands.describe(alliance='Alliance name or ID')
    @app_commands.autocomplete(alliance=alliance_autocomplete)
    async def alliance(self, ctx: commands.Context, alliance: Optional[str] = None):
        """Show alliance overview; DB4D shows resources-only, others show full fields."""
        try:
            # Send initial loading message to be edited later
            initial_msg = await ctx.send("🔄 Loading Alliance Data...")

            # Resolve target alliance id
            target_id = None
            target_name = None
            arg = (alliance or "").strip()

            if not arg:
                embed = discord.Embed(
                    title="Alliance Command Usage",
                    description="Please provide an alliance name or ID. Example: `/alliance DB4D` or `/alliance 14635`",
                    color=discord.Color.blue()
                )
                await initial_msg.edit(content=None, embed=embed)
                return

            if arg.isdigit():
                try:
                    target_id = str(int(arg))
                except ValueError:
                    target_id = arg
            else:
                # IRS shortcut — no API call needed
                if arg.lower() in ("Nights Watch", "nights watch", "nw"):
                    target_id = NIGHTS_WATCH_ALLIANCE_ID
                    target_name = NIGHTS_WATCH_ALLIANCE_NAME
                else:
                    try:
                        if self.query_system:
                            resolved = await self.query_system.resolve_alliance(arg)
                            if resolved and isinstance(resolved, dict) and resolved.get('id'):
                                target_id = str(resolved.get('id'))
                                if resolved.get('name'):
                                    target_name = resolved.get('name')
                    except Exception as e:
                        self.logger.error(f"Error resolving alliance '{arg}': {e}", exc_info=True)
                        target_id = None

            if not target_id:
                embed = discord.Embed(
                    title="Alliance Not Found",
                    description=f"Could not find an alliance matching '{arg}'. Please check the name/ID and try again.",
                    color=discord.Color.red()
                )
                await initial_msg.edit(content=None, embed=embed)
                return

            # Fetch nations — use GlobalNations.db for all alliances (NW included)
            nations: List[Dict] = []
            if target_id == NIGHTS_WATCH_ALLIANCE_ID:
                try:
                    from PnWHarvester.db.global_nations_db import GlobalNationsDB
                    db = GlobalNationsDB(str(GLOBAL_NATIONS_DB))
                    db_nations = await db.get_nations_by_alliance(int(NIGHTS_WATCH_ALLIANCE_ID))
                    for nation in db_nations:
                        nation['cities'] = await db.get_cities_for_nation(int(nation['id']))
                    nations = db_nations
                    self.logger.info(f"Loaded {len(nations)} NW nations from GlobalNationsDB")
                except Exception as e:
                    self.logger.error(f"GlobalNationsDB NW load failed, falling back to API: {e}")
                    nations = await self.get_alliance_nations(target_id, force_refresh=False)
            else:
                # Try GlobalNations.db first — no API call needed
                global_db = _get_global_nations_db()
                if global_db:
                    try:
                        db_nations = await global_db.get_nations_by_alliance(int(target_id))
                        if db_nations:
                            for nation in db_nations:
                                nation['cities'] = await global_db.get_cities_for_nation(int(nation['id']))
                                # Ensure alliance name is set for embed
                                if not nation.get('alliance') and nation.get('alliance_name'):
                                    nation['alliance'] = nation['alliance_name']
                            nations = db_nations
                            if not target_name and nations:
                                target_name = nations[0].get('alliance_name') or target_name
                            self.logger.info(f"Loaded {len(nations)} nations from GlobalNationsDB for alliance {target_id}")
                    except Exception as e:
                        self.logger.error(f"GlobalNationsDB load failed, falling back to API: {e}")

                # Fall back to API if DB had nothing
                if not nations:
                    nations = await self.get_alliance_nations(target_id, force_refresh=False)

            if not nations:
                await initial_msg.edit(content="❌ No alliance data available.")
                return

            if not target_name and nations and nations[0].get('alliance'):
                target_name = nations[0].get('alliance')

            # Build initial view and embed for Alliance Totals
            view = AllianceTotalsView(
                author_id=ctx.author.id,
                bot=self.bot,
                query_instance=self.query_system,
                calc_instance=self.calc_system,
                nations=nations,
                target_alliance_id=str(target_id),
                target_alliance_name=target_name
            )
            embed = await view.generate_alliance_totals_embed(nations)

            # Edit the initial message to display the embed and attach the interactive view
            await initial_msg.edit(content=None, embed=embed, view=view)

        except Exception as e:
            self._log_error(f"Error in alliance command: {e}", e, "AllianceManager.alliance")
            await ctx.send(f"❌ An error occurred: {str(e)}")

    async def generate_alliance_totals_embed(self, nations: List[Dict[str, Any]], target_alliance_name: Optional[str] = None) -> discord.Embed:
        """Generate the alliance totals embed."""
        try:
            if not nations:
                return discord.Embed(
                    title="❌ No Alliance Data",
                    description="Failed to retrieve alliance data.",
                    color=discord.Color.red()
                )

            # Create a temporary AllianceTotalsView to use its embed generation method
            view = AllianceTotalsView(self.bot.user.id if self.bot.user else 0, self.bot, self.query_system, self.calc_system, nations, target_alliance_id=str(DEFAULT_ALLIANCE_ID), target_alliance_name=target_alliance_name)
            return await view.generate_alliance_totals_embed(nations)

        except Exception as e:
            self._log_error(f"Error in generate_alliance_totals_embed: {e}", e, "AllianceManager.generate_alliance_totals_embed")
            return discord.Embed(
                title="❌ Alliance Totals Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )

from Systems.PnW.Util.query import create_v3_query_instance

async def setup(bot: commands.Bot):
    """Setup function for loading the cog."""
    try:
        logger = logging.getLogger(f"{__name__}")
        query_instance = create_v3_query_instance(api_key=PANDW_API_KEY, logger=logger)
        calc_instance = AllianceCalculator(query_instance)
        await bot.add_cog(AllianceManager(bot, query_instance, calc_instance))
        logging.info("Alliance Management System loaded successfully!")
    except Exception as e:
        logging.error(f"Failed to load Alliance Management System: {e}")
        logging.error(traceback.format_exc())
        raise

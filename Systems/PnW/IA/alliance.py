import discord
from discord.ext import commands
import os
import aiofiles
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Any, Optional, Union
import asyncio
import random
import logging
import traceback
import sys
import time
from pathlib import Path

# Try to import pnwkit, handle gracefully if not available
try:
    import pnwkit
    PNWKIT_AVAILABLE = True
    PNWKIT_ERROR = None
    PNWKIT_SOURCE = "system"
except ImportError as e:
    # Try to use local pnwkit if system version is not available
    try:
        import sys
        import os
        local_packages_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'local_packages')
        if local_packages_dir not in sys.path:
            sys.path.insert(0, local_packages_dir)
        
        import pnwkit
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
from config import PANDW_API_KEY, HOME_ALLIANCE_ID
from Systems.Functions import emoji as emoji_mod
from Systems.Functions.user_data_manager import UserDataManager

# Import calculation utilities
from Systems.PnW.Util.calc import AllianceCalculator

# Import centralized query system for direct API access
from Systems.PnW.Util.query import create_query_instance

# Bloc AllianceManager removed; set placeholder for references
BlocAllianceManager = None



class FullMillView(discord.ui.View):
    """View for displaying Full Mill calculations and alliance data."""
    
    def __init__(self, author_id: int, bot: commands.Bot, alliance_cog: 'AllianceManager', nations: List[Dict] = None):
        super().__init__(timeout=300)  # 5 minute timeout
        self.author_id = author_id
        self.bot = bot
        self.alliance_cog = alliance_cog
        self.current_data = None
        self.current_nations = nations
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if the interaction is from the command author."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(f"{emoji_mod.mention('Deny')} You cannot use this menu.")
            return False
        return True

    async def generate_full_mill_embed(self, nations: List[Dict] = None) -> discord.Embed:
        """Generate the full mill embed without handling interaction."""
        try:
            # Use provided nations or current nations
            current_nations = nations or self.current_nations
            
            if not current_nations:
                # Get alliance data based on guild
                guild_alliance_id = await self.alliance_cog.get_alliance_id_for_guild(self.guild)
                guild_nations = await self.alliance_cog.get_alliance_nations(guild_alliance_id)
                
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
            full_mill_data = await self.alliance_cog.calculate_full_mill_data(non_vm_non_app)
            
            # Create Full Mill embed
            embed = discord.Embed(
                title=f"{emoji_mod.mention('IA') or '🏭'} DB4D Military Analysis",
                description="Alliance military capacity and production analysis (ALL − Vacation Mode − APPS)",
                color=discord.Color.from_rgb(255, 140, 0)
            )
            
            # Overall statistics
            embed.add_field(
                name=f"{emoji_mod.mention('Stat') or '📊'} Overall Statistics",
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
                name=f"{emoji_mod.mention('MA') or '⚔️'} Military Units",
                value=(
                    f"{emoji_mod.mention('LandSup') or '🪖'} **Soldiers:** {full_mill_data['current_soldiers']:,}/{full_mill_data['max_soldiers']:,}\n"
                    f"{emoji_mod.mention('LandSup') or '🚙'} **Tanks:** {full_mill_data['current_tanks']:,}/{full_mill_data['max_tanks']:,}\n"
                    f"{emoji_mod.mention('AirSup') or '🛩️'} **Aircraft:** {full_mill_data['current_aircraft']:,}/{full_mill_data['max_aircraft']:,}\n"
                    f"{emoji_mod.mention('NavySup') or '⚓'} **Ships:** {full_mill_data['current_ships']:,}/{full_mill_data['max_ships']:,}"
                ),
                inline=False
            )
            
            # Daily Production
            embed.add_field(
                name=f"{emoji_mod.mention('IA') or '🏭'} Daily Production",
                value=(
                    f"{emoji_mod.mention('LandSup') or '🪖'} **Soldiers:** {full_mill_data['daily_soldiers']:,}/day\n"
                    f"{emoji_mod.mention('LandSup') or '🚙'} **Tanks:** {full_mill_data['daily_tanks']:,}/day\n"
                    f"{emoji_mod.mention('AirSup') or '🛩️'} **Aircraft:** {full_mill_data['daily_aircraft']:,}/day\n"
                    f"{emoji_mod.mention('NavySup') or '⚓'} **Ships:** {full_mill_data['daily_ships']:,}/day\n"
                    f"{emoji_mod.mention('munitions') or '🚀'} **Missiles:** {full_mill_data['daily_missiles']:,}/day\n"
                    f"{emoji_mod.mention('uranium') or '☢️'} **Nukes:** {full_mill_data['daily_nukes']:,}/day"
                ),
                inline=False
            )
            
            # Military unit gaps
            embed.add_field(
                name=f"{emoji_mod.mention('MA') or '⚔️'} Units Needed",
                value=(
                    f"{emoji_mod.mention('LandSup') or '🪖'} **Soldiers:** {full_mill_data['soldier_gap']:,}\n"
                    f"{emoji_mod.mention('LandSup') or '🚙'} **Tanks:** {full_mill_data['tank_gap']:,}\n"
                    f"{emoji_mod.mention('AirSup') or '🛩️'} **Aircraft:** {full_mill_data['aircraft_gap']:,}\n"
                    f"{emoji_mod.mention('NavySup') or '⚓'} **Ships:** {full_mill_data['ship_gap']:,}"
                ),
                inline=False
            )
            
            import math
            embed.add_field(
                name=f"{emoji_mod.mention('Info') or '⏱️'} Time to Max",
                value=(
                    f"{emoji_mod.mention('LandSup') or '🪖'} **Soldiers:** {math.ceil(full_mill_data['max_soldier_days'])} days ({full_mill_data['max_soldier_nation']})\n"
                    f"{emoji_mod.mention('LandSup') or '🚙'} **Tanks:** {math.ceil(full_mill_data['max_tank_days'])} days ({full_mill_data['max_tank_nation']})\n"
                    f"{emoji_mod.mention('AirSup') or '🛩️'} **Aircraft:** {math.ceil(full_mill_data['max_aircraft_days'])} days ({full_mill_data['max_aircraft_nation']})\n"
                    f"{emoji_mod.mention('NavySup') or '⚓'} **Ships:** {math.ceil(full_mill_data['max_ship_days'])} days ({full_mill_data['max_ship_nation']})"
                ),
                inline=False
            )
            
            embed.set_footer(text=f"Generated at {datetime.now().strftime('%H:%M:%S')} | Use Alliance Totals button to refresh data")
            
            return embed
            
        except Exception as e:
            self.alliance_cog._log_error(f"Error in generate_full_mill_embed: {e}", e, "FullMillView.generate_full_mill_embed")
            return discord.Embed(
                title=f"{emoji_mod.mention('Deny')} Full Mill Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
    
    @discord.ui.button(label="Improvements", style=discord.ButtonStyle.secondary, emoji=emoji_mod.get_partial('IA'))
    async def improvements_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show improvements breakdown for all alliance nations."""
        try:
            await interaction.response.defer()
            
            if not self.current_nations:
                # Fetch alliance data based on guild
                guild_alliance_id = await self.alliance_cog.get_alliance_id_for_guild(self.guild)
                nations = await self.alliance_cog.get_alliance_nations(guild_alliance_id)
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
            view = ImprovementsView(self.author_id, self.bot, self.alliance_cog, self.current_nations)
            embed = await view.generate_improvements_embed(self.current_nations)
            
            # Update the message with Improvements embed and switch to ImprovementsView
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=view
            )
            
        except Exception as e:
            self.alliance_cog._log_error(f"Error in improvements_button: {e}", e, "FullMillView.improvements_button")
            embed = discord.Embed(
                title=f"{emoji_mod.mention('Deny')} Improvements Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

    @discord.ui.button(label="Project Totals", style=discord.ButtonStyle.secondary, emoji=emoji_mod.get_partial('Codex'))
    async def project_totals_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show project totals for active nations only (excludes Applicants & VM)."""
        try:
            await interaction.response.defer()

            if not self.current_nations:
                # Fetch alliance data based on guild
                guild_alliance_id = await self.alliance_cog.get_alliance_id_for_guild(self.guild)
                nations = await self.alliance_cog.get_alliance_nations(guild_alliance_id)
                if not nations:
                    embed = discord.Embed(
                        title=f"{emoji_mod.mention('Deny')} No Alliance Data",
                        description="Failed to retrieve alliance data.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                self.current_nations = nations

            view = ProjectTotalsView(self.author_id, self.bot, self.alliance_cog, self.current_nations)
            embed = await view.generate_project_totals_embed(self.current_nations)

            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=view
            )
        except Exception as e:
            self.alliance_cog._log_error(f"Error in project_totals_button: {e}", e, "FullMillView.project_totals_button")
            await interaction.followup.send(f"{emoji_mod.mention('Deny')} An error occurred: {str(e)}")
    
    @discord.ui.button(label="Alliance Totals", style=discord.ButtonStyle.secondary, emoji=emoji_mod.get_partial('Stat'))
    async def alliance_totals_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show alliance totals and statistics."""
        try:
            await interaction.response.defer()
            
            if not self.current_nations:
                # Fetch alliance data based on guild
                guild_alliance_id = await self.alliance_cog.get_alliance_id_for_guild(self.guild)
                nations = await self.alliance_cog.get_alliance_nations(guild_alliance_id)
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
            view = AllianceTotalsView(self.author_id, self.bot, self.alliance_cog, self.current_nations)
            embed = await view.generate_alliance_totals_embed(self.current_nations)
            
            # Update the message with Alliance Totals embed and switch to AllianceTotalsView
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=view
            )
            
        except Exception as e:
            self.alliance_cog._log_error(f"Error in alliance_totals_button: {e}", e, "FullMillView.alliance_totals_button")
            embed = discord.Embed(
                title=f"{emoji_mod.mention('Deny')} Alliance Totals Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

class AllianceTotalsView(discord.ui.View):
    """View for displaying Alliance Totals with Full Mill button."""
    
    def __init__(self, author_id: int, bot: commands.Bot, alliance_cog: 'AllianceManager', nations: List[Dict] = None, target_alliance_id: Optional[str] = None):
        super().__init__(timeout=300)  # 5 minute timeout
        self.author_id = author_id
        self.bot = bot
        self.alliance_cog = alliance_cog
        self.current_nations = nations
        self.target_alliance_id = target_alliance_id
        # Ensure compatibility with bloc-level components that may access bloc_data
        self.bloc_data = {}
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if the interaction is from the command author."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(f"{emoji_mod.mention('Deny')} You cannot use this menu.")
            return False
        return True
        
    async def generate_alliance_totals_embed(self, nations: List[Dict] = None) -> discord.Embed:
        """Generate the alliance totals embed without handling interaction."""
        try:
            current_nations = nations or self.current_nations
            if not current_nations:
                # Get alliance data based on guild
                guild_nations = await self.alliance_cog.get_alliance_nations(self.alliance_cog.db4d_alliance_id)
                
                current_nations = guild_nations or []
                if not current_nations:
                    return discord.Embed(
                        title=f"{emoji_mod.mention('Deny')} No Alliance Data",
                        description="Failed to retrieve alliance data.",
                        color=discord.Color.red()
                    )
                self.current_nations = current_nations
            
            is_db4d = str(self.target_alliance_id or self.alliance_cog.db4d_alliance_id) == '14635'
            
            # Calculate resource totals for active nations (excluding vacation mode, applicants, and 14+ days inactive)
            filtered_nations = await self.alliance_cog.get_active_nations(current_nations)
            
            totals = await self.alliance_cog.calculate_resource_totals(filtered_nations)
            
            resources_held = (
                f"{emoji_mod.mention('credit') or '💰'} **Money:** ${totals['money']:,}\n"
                f"{emoji_mod.mention('credit') or '💰'} **Credits:** {totals['credits']:,}\n"
                f"{emoji_mod.mention('gasoline') or '⛽'} **Gasoline:** {totals['gasoline']:,}\n"
                f"{emoji_mod.mention('munitions') or '🚀'} **Munitions:** {totals['munitions']:,}\n"
                f"{emoji_mod.mention('steel') or '🧱'} **Steel:** {totals['steel']:,}\n"
                f"{emoji_mod.mention('aluminum') or '📎'} **Aluminum:** {totals['aluminum']:,}\n"
                f"{emoji_mod.mention('food') or '🍱'} **Food:** {totals['food']:,}\n"
                f"{emoji_mod.mention('coal') or '🌑'} **Coal:** {totals['coal']:,}\n"
                f"{emoji_mod.mention('oil_1') or '🛢️'} **Oil:** {totals['oil']:,}\n"
                f"{emoji_mod.mention('uranium') or '☢️'} **Uranium:** {totals['uranium']:,}\n"
                f"{emoji_mod.mention('iron') or '⛓️'} **Iron:** {totals['iron']:,}\n"
                f"{emoji_mod.mention('bauxite') or '🪨'} **Bauxite:** {totals['bauxite']:,}\n"
                f"{emoji_mod.mention('lead') or '🔋'} **Lead:** {totals['lead']:,}"
            )
            
            if is_db4d:
                embed = discord.Embed(
                    title=f"{emoji_mod.mention('credit') or '💰'} DB4D Resources",
                    description="Current resources held by active members",
                    color=discord.Color.from_rgb(0, 150, 255)
                )
                embed.add_field(name="Resources Held", value=resources_held, inline=False)
                return embed
            
            # Non-DB4D: full fields view
            # Get active nations for statistics
            active_nations = filtered_nations # Re-use filtered_nations which is active_nations
            # Build simplified active set: ALL - Vacation Mode - APPLICANT
            apps = [n for n in current_nations if ((n.get('alliance_position','') or '').strip().upper() == 'APPLICANT')]
            non_vm_non_app = [n for n in current_nations if (((n.get('vacation_mode_turns', 0) or 0) == 0) and ((n.get('alliance_position','') or '').strip().upper() != 'APPLICANT'))]
            stats_simple = await self.alliance_cog.calculate_alliance_statistics(non_vm_non_app)
            
            # Calculate averages manually based on simplified active set
            avg_score = stats_simple['total_score'] / stats_simple['total_nations'] if stats_simple['total_nations'] > 0 else 0
            avg_cities = stats_simple['total_cities'] / stats_simple['total_nations'] if stats_simple['total_nations'] > 0 else 0
            
            embed = discord.Embed(
                title=f"{emoji_mod.mention('Stat') or '📊'} Alliance Totals",
                description="Comprehensive alliance statistics and capabilities",
                color=discord.Color.from_rgb(0, 150, 255)
            )
            
            embed.add_field(
                name=f"{emoji_mod.mention('Stat') or '📊'} Nation Counts",
                value=(
                    f"{emoji_mod.mention('Codex') or '📇'} **Total:** {len(current_nations)}\n"
                    f"{emoji_mod.mention('Yes') or '✅'} **Active:** {len(non_vm_non_app)}\n"
                    f"{emoji_mod.mention('Codex') or '📝'} **Applicants:** {len(apps)}\n"
                    f"{emoji_mod.mention('Stat') or '🧮'} **Total Score:** {stats_simple['total_score']:,}\n"
                    f"{emoji_mod.mention('Stat') or '⚖️'} **Average Score:** {avg_score:,.0f}\n"
                    f"{emoji_mod.mention('IA') or '🌇'} **Total Cities:** {stats_simple['total_cities']:,}\n"
                    f"{emoji_mod.mention('IA') or '🌆'} **Average Cities:** {avg_cities:.1f}"
                ),
                inline=False
            )
            
            # Do not show resources for non-DB4D alliances
            
            # Add categories directly to main embed (replacing old buttons)
            from datetime import datetime as _dt_dt, timedelta as _dt_td, timezone as _dt_tz
            now = _dt_dt.now(_dt_tz.utc)

            def _days_inactive(n):
                s = n.get('last_active')
                if not s:
                    return None
                try:
                    if isinstance(s, str):
                        la = s.strip()
                        if la.endswith('Z'):
                            la = la.replace('Z', '+00:00')
                        dt = _dt_dt.fromisoformat(la)
                    else:
                        dt = s
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=_dt_tz.utc)
                    else:
                        dt = dt.astimezone(_dt_tz.utc)
                    return (now - dt).days
                except Exception:
                    return None

            def _make_links(items, with_days=False):
                links = []
                for n in items:
                    nid = n.get('id')
                    name = n.get('nation_name', 'Unknown')
                    
                    if nid:
                        # Add nation link with optional days inactive (no Discord info)
                        if with_days:
                            d = _days_inactive(n)
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
            filtered_nations = await self.alliance_cog.get_active_nations(current_nations)
            grey = [n for n in filtered_nations if (n.get('color', '') or '').strip().upper() in ('GREY', 'GRAY')]
            beige = [n for n in filtered_nations if (n.get('color', '') or '').strip().upper() == 'BEIGE']
            vm = [n for n in current_nations if (n.get('vacation_mode_turns', 0) or 0) > 0 and ((n.get('alliance_position', '') or '').strip().upper() != 'APPLICANT')]

            seven_to_thirteen = []
            fourteen_plus = []
            for n in non_vm_non_app:
                d = _days_inactive(n)
                if isinstance(d, int):
                    if 7 <= d < 14:
                        seven_to_thirteen.append(n)
                    elif d >= 14:
                        fourteen_plus.append(n)

            non_applicants = [n for n in current_nations if ((n.get('alliance_position','') or '').strip().upper() != 'APPLICANT')]
            embed.add_field(name=f"{emoji_mod.mention('Info') or '⏲️'} GREY Nations - Total: {len(grey)}", value=_make_links(grey), inline=False)
            embed.add_field(name=f"{emoji_mod.mention('Deny') or '🩼'} BEIGE Nations - Total: {len(beige)}", value=_make_links(beige), inline=False)
            embed.add_field(name=f"{emoji_mod.mention('Info') or '🏖️'} Vacation Mode - Total: {len(vm)}", value=_make_links(vm), inline=False)
            embed.add_field(name=f"{emoji_mod.mention('Info') or '⏰'} Inactive 7–13 Days - Total: {len(seven_to_thirteen)}", value=_make_links(seven_to_thirteen, with_days=True), inline=False)
            embed.add_field(name=f"{emoji_mod.mention('Info') or '📅'} Inactive 14+ Days - Total: {len(fourteen_plus)}", value=_make_links(fourteen_plus, with_days=True), inline=False)
            
            embed.set_footer(text=f"Generated at {datetime.now().strftime('%H:%M:%S')} | Use other buttons to view different data")
            
            return embed
            
        except Exception as e:
            self.alliance_cog._log_error(f"Error in generate_alliance_totals_embed: {e}", e, "AllianceTotalsView.generate_alliance_totals_embed")
            return discord.Embed(
                title=f"{emoji_mod.mention('Deny')} Alliance Totals Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
    
    @discord.ui.button(label="Military", style=discord.ButtonStyle.primary, emoji=emoji_mod.get_partial('MA'))
    async def full_mill_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show full military capacity analysis."""
        try:
            await interaction.response.defer()
            
            if not self.current_nations:
                # Fetch alliance data based on guild
                guild_alliance_id = await self.alliance_cog.get_alliance_id_for_guild(self.guild)
                nations = await self.alliance_cog.get_alliance_nations(guild_alliance_id)
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
            view = FullMillView(self.author_id, self.bot, self.alliance_cog, self.current_nations)
            embed = await view.generate_full_mill_embed(self.current_nations)
            
            # Update the message with Full Mill embed and switch to FullMillView
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=view
            )
            
        except Exception as e:
            self.alliance_cog._log_error(f"Error in full_mill_button: {e}", e, "AllianceTotalsView.full_mill_button")
            embed = discord.Embed(
                title=f"{emoji_mod.mention('Deny')} Full Mill Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
    
    @discord.ui.button(label="Improvements", style=discord.ButtonStyle.secondary, emoji=emoji_mod.get_partial('IA'))
    async def improvements_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show improvements breakdown for all alliance nations."""
        try:
            await interaction.response.defer()
            
            if not self.current_nations:
                # Fetch alliance data based on guild
                guild_alliance_id = await self.alliance_cog.get_alliance_id_for_guild(self.guild)
                nations = await self.alliance_cog.get_alliance_nations(guild_alliance_id)
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
            view = ImprovementsView(self.author_id, self.bot, self.alliance_cog, self.current_nations)
            embed = await view.generate_improvements_embed(self.current_nations)
            
            # Update the message with Improvements embed and add navigation buttons
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=view
            )
            
        except Exception as e:
            self.alliance_cog._log_error(f"Error in improvements_button: {e}", e, "AllianceTotalsView.improvements_button")
            embed = discord.Embed(
                title=f"{emoji_mod.mention('Deny')} Improvements Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

    @discord.ui.button(label="Project Totals", style=discord.ButtonStyle.secondary, emoji=emoji_mod.get_partial('Codex'))
    async def project_totals_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show project totals for active nations only (excludes Applicants & VM)."""
        try:
            await interaction.response.defer()

            if not self.current_nations:
                # Fetch alliance data based on guild
                guild_alliance_id = await self.alliance_cog.get_alliance_id_for_guild(self.guild)
                nations = await self.alliance_cog.get_alliance_nations(guild_alliance_id)
                if not nations:
                    embed = discord.Embed(
                        title=f"{emoji_mod.mention('Deny')} No Alliance Data",
                        description="Failed to retrieve alliance data.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                self.current_nations = nations

            view = ProjectTotalsView(self.author_id, self.bot, self.alliance_cog, self.current_nations)
            embed = await view.generate_project_totals_embed(self.current_nations)

            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=view
            )
        except Exception as e:
            self.alliance_cog._log_error(f"Error in project_totals_button: {e}", e, "AllianceTotalsView.project_totals_button")
            await interaction.followup.send(f"{emoji_mod.mention('Deny')} An error occurred: {str(e)}")

    

class ImprovementsView(discord.ui.View):
    """View for displaying Improvements Breakdown with navigation buttons."""
    
    def __init__(self, author_id: int, bot: commands.Bot, alliance_cog: 'AllianceManager', nations: List[Dict] = None):
        super().__init__(timeout=300)  # 5 minute timeout
        self.author_id = author_id
        self.bot = bot
        self.alliance_cog = alliance_cog
        self.current_nations = nations
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Check if the interaction is from the command author."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(f"{emoji_mod.mention('Deny')} You cannot use this menu.")
            return False
        return True
        
    async def generate_improvements_embed(self, nations: List[Dict] = None) -> discord.Embed:
        """Generate the improvements breakdown embed without handling interaction."""
        try:
            current_nations = nations or self.current_nations
            if not current_nations:
                # Get alliance data based on guild
                guild_alliance_id = await self.alliance_cog.get_alliance_id_for_guild(self.guild)
                guild_nations = await self.alliance_cog.get_alliance_nations(guild_alliance_id)
                
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
            improvements_data = await self.alliance_cog.calculate_improvements_data(active_nations)
            
            # Create Improvements Breakdown embed
            embed = discord.Embed(
                title=f"{emoji_mod.mention('IA') or '🏗️'} DB4D Improvements Breakdown",
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
                name=f"{emoji_mod.mention('IA') or '⛏️'} Raw Resources",
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
                name=f"{emoji_mod.mention('IA') or '🏭'} Manufacturing",
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
                name=f"{emoji_mod.mention('IA') or '🏛️'} Civil",
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
                name=f"{emoji_mod.mention('credit') or '💰'} Commerce",
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
                name=f"{emoji_mod.mention('MA') or '⚔️'} Military",
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
    
    @discord.ui.button(label="Alliance Totals", style=discord.ButtonStyle.secondary, emoji=emoji_mod.get_partial('Stat'))
    async def alliance_totals_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show alliance totals and statistics."""
        try:
            await interaction.response.defer()
            
            if not self.current_nations:
                # Fetch alliance data if not already loaded
                nations = await self.alliance_cog.get_alliance_nations(self.alliance_cog.db4d_alliance_id)
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
            view = AllianceTotalsView(self.author_id, self.bot, self.alliance_cog, self.current_nations)
            embed = await view.generate_alliance_totals_embed(self.current_nations)
            
            # Update the message with Alliance Totals embed and switch to AllianceTotalsView
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=view
            )
            
        except Exception as e:
            self.alliance_cog._log_error(f"Error in alliance_totals_button: {e}", e, "ImprovementsView.alliance_totals_button")
            embed = discord.Embed(
                title=f"{emoji_mod.mention('Deny')} Alliance Totals Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

    @discord.ui.button(label="Project Totals", style=discord.ButtonStyle.secondary, emoji=emoji_mod.get_partial('Codex'))
    async def project_totals_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show project totals for active nations only (excludes Applicants & VM)."""
        try:
            await interaction.response.defer()

            if not self.current_nations:
                nations = await self.alliance_cog.get_alliance_nations(self.alliance_cog.db4d_alliance_id)
                if not nations:
                    embed = discord.Embed(
                        title=f"{emoji_mod.mention('Deny')} No Alliance Data",
                        description="Failed to retrieve alliance data.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                self.current_nations = nations

            view = ProjectTotalsView(self.author_id, self.bot, self.alliance_cog, self.current_nations)
            embed = await view.generate_project_totals_embed(self.current_nations)

            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=view
            )
        except Exception as e:
            self.alliance_cog._log_error(f"Error in project_totals_button: {e}", e, "ImprovementsView.project_totals_button")
            await interaction.followup.send(f"{emoji_mod.mention('Deny')} An error occurred: {str(e)}")
    
    @discord.ui.button(label="Military", style=discord.ButtonStyle.secondary, emoji=emoji_mod.get_partial('MA'))
    async def full_mill_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Show full military capacity analysis."""
        try:
            await interaction.response.defer()
            
            if not self.current_nations:
                # Fetch alliance data if not already loaded
                nations = await self.alliance_cog.get_alliance_nations(self.alliance_cog.db4d_alliance_id)
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
            view = FullMillView(self.author_id, self.bot, self.alliance_cog, self.current_nations)
            embed = await view.generate_full_mill_embed(self.current_nations)
            
            # Update the message with Full Mill embed and switch to FullMillView
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=view
            )
            
        except Exception as e:
            self.alliance_cog._log_error(f"Error in full_mill_button: {e}", e, "ImprovementsView.full_mill_button")
            embed = discord.Embed(
                title=f"{emoji_mod.mention('Deny')} Full Mill Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

class ProjectTotalsView(discord.ui.View):
    """View for displaying Project Totals (active nations only)."""

    def __init__(self, author_id: int, bot: commands.Bot, alliance_cog: 'AllianceManager', nations: List[Dict] = None):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.bot = bot
        self.alliance_cog = alliance_cog
        self.current_nations = nations

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(f"{emoji_mod.mention('Deny')} You cannot use this menu.")
            return False
        return True

    async def generate_project_totals_embed(self, nations: List[Dict] = None) -> discord.Embed:
        try:
            current_nations = nations or self.current_nations
            if not current_nations:
                # Get alliance data dynamically based on guild
                guild_alliance_id = await self.alliance_cog.get_alliance_id_for_guild(self.guild_id)
                if not guild_alliance_id:
                    return discord.Embed(
                        title=f"{emoji_mod.mention('Deny')} No Alliance Data",
                        description="Failed to determine alliance ID for this guild.",
                        color=discord.Color.red()
                    )
                
                # Get main alliance nations
                current_nations = await self.alliance_cog.get_alliance_nations(guild_alliance_id)
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
                f"{emoji_mod.mention('MA') or '⚔️'} War": [
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
                f"{emoji_mod.mention('IA') or '🏭'} Industry": [
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
                f"{emoji_mod.mention('IA') or '🏛️'} Government": [
                    ("Activity Center", "activity_center"),
                    ("Advanced Engineering Corps", "advanced_engineering_corps"),
                    ("Arable Land Agency", "arable_land_agency"),
                    ("Bureau of Domestic Affairs", "bureau_of_domestic_affairs"),
                    ("Center for Civil Engineering", "center_for_civil_engineering"),
                    ("Government Support Agency", "government_support_agency"),
                    ("Research & Development Center", "research_and_development_center")
                ],
                f"{emoji_mod.mention('Info') or '👽'} Alien": [
                    ("Mars Landing", "mars_landing"),
                    ("Moon Landing", "moon_landing")
                ]
            }

            embed = discord.Embed(
                title=f"{emoji_mod.mention('Codex') or '🧩'} DB4D Project Totals",
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
                current = []
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
            self.alliance_cog._log_error(f"Error generating project totals embed: {e}", e, "ProjectTotalsView.generate_project_totals_embed")
            return discord.Embed(
                title=f"{emoji_mod.mention('Deny')} Project Totals Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )

    @discord.ui.button(label="Alliance Totals", style=discord.ButtonStyle.secondary, emoji=emoji_mod.get_partial('Stat'))
    async def alliance_totals_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
            
            # Create AllianceTotalsView and use its generator method
            view = AllianceTotalsView(self.author_id, self.bot, self.alliance_cog, self.current_nations)
            embed = await view.generate_alliance_totals_embed(self.current_nations)
            
            # Update the message with Alliance Totals embed and switch to AllianceTotalsView
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=view
            )
        except Exception as e:
            self.alliance_cog._log_error(f"Error in alliance_totals_button: {e}", e, "ProjectTotalsView.alliance_totals_button")
            await interaction.followup.send(f"{emoji_mod.mention('Deny')} An error occurred: {str(e)}")

    @discord.ui.button(label="Improvements", style=discord.ButtonStyle.secondary, emoji=emoji_mod.get_partial('IA'))
    async def improvements_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
            
            # Create ImprovementsView and use its generator method
            view = ImprovementsView(self.author_id, self.bot, self.alliance_cog, self.current_nations)
            embed = await view.generate_improvements_embed(self.current_nations)
            
            # Update the message with Improvements embed and switch to ImprovementsView
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=view
            )
        except Exception as e:
            self.alliance_cog._log_error(f"Error in improvements_button: {e}", e, "ProjectTotalsView.improvements_button")
            await interaction.followup.send(f"{emoji_mod.mention('Deny')} An error occurred: {str(e)}")

    @discord.ui.button(label="Military", style=discord.ButtonStyle.secondary, emoji=emoji_mod.get_partial('MA'))
    async def full_mill_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
            view = FullMillView(self.author_id, self.bot, self.alliance_cog, self.current_nations)
            embed = await view.generate_full_mill_embed(self.current_nations)
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=view
            )
        except Exception as e:
            self.alliance_cog._log_error(f"Error in full_mill_button: {e}", e, "ProjectTotalsView.full_mill_button")
            await interaction.followup.send(f"{emoji_mod.mention('Deny')} An error occurred: {str(e)}")

class AllianceManager(commands.Cog):
    """Alliance Management System for DB4D."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db4d_alliance_id = '14635'
        
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
        
        # Initialize query system for fetching nations directly from API
        # This is now the primary and only data source
        self.query_system = None
        if create_query_instance is not None:
            try:
                self.query_system = create_query_instance(api_key=PANDW_API_KEY, logger=self.logger)
                self.logger.info("AllianceManager query_system initialized successfully")
            except Exception as e:
                self._log_error("Failed to initialize query system", e, "__init__")
                raise RuntimeError("Query system initialization failed - required for current data fetching")
        else:
            error_msg = "AllianceManager: create_query_instance not available; API queries disabled"
            self.logger.error(error_msg)
            raise ImportError(error_msg)
        
        self._nations_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl_seconds = 3600
        
        # Initialize Calculator
        self.calculator = AllianceCalculator()
        
        self.logger.info("AllianceManager initialized successfully")
    
    def _log_error(self, error_msg: str, exception: Exception = None, context: str = ""):
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
    
    def _safe_get(self, data: dict, key: str, default: Any = None, expected_type: type = None) -> Any:
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
        aid = str(alliance_id or self.db4d_alliance_id)
        now = time.time()
        cached = self._nations_cache.get(aid)
        if cached and not force_refresh and (now - (cached.get('ts') or 0) < self._cache_ttl_seconds):
            return cached.get('nations') or []
        nations: List[Dict[str, Any]] = []
        try:
            if self.query_system:
                fetch_fresh = force_refresh or (cached is None) or (now - (cached.get('ts') or 0) >= self._cache_ttl_seconds)
                nations = await self.query_system.get_alliance_nations(aid, bot=self.bot, force_refresh=fetch_fresh)
                nations = nations or []
                self._nations_cache[aid] = {'ts': now, 'nations': nations}
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
        return self.db4d_alliance_id

    async def get_active_nations(self, nations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter nations to exclude vacation mode and applicant members using centralized logic."""
        return await self.calculator.get_active_nations(nations)

    async def calculate_nation_statistics(self, nations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate comprehensive nation statistics using centralized logic."""
        return await self.calculator.calculate_nation_statistics(nations)

    async def calculate_alliance_statistics(self, nations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate alliance statistics using centralized logic."""
        return await self.calculator.calculate_alliance_statistics(nations)

    async def calculate_resource_totals(self, nations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate resource totals using centralized logic."""
        return await self.calculator.calculate_resource_totals(nations)

    async def calculate_full_mill_data(self, nations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate full mill data using centralized logic."""
        return await self.calculator.calculate_full_mill_data(nations)

    async def calculate_military_purchase_limits(self, nation: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate military purchase limits using centralized logic."""
        return await self.calculator.calculate_military_purchase_limits(nation)

    def get_nation_specialty(self, nation: Dict[str, Any]) -> str:
        """Get nation specialty using centralized logic."""
        return self.calculator.get_nation_specialty(nation)

    def calculate_combat_score(self, nation: Dict[str, Any]) -> float:
        """Calculate combat score using centralized logic."""
        return self.calculator.calculate_combat_score(nation)

    def has_project(self, nation: Dict[str, Any], project_name: str) -> bool:
        """Check if nation has a specific project using centralized logic."""
        return self.calculator.has_project(nation, project_name)

    async def calculate_improvements_data(self, nations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate improvements data using centralized logic."""
        return await self.calculator.calculate_improvements_data(nations)

    # testalliance command removed

    @commands.hybrid_command(name='alliance', description='Display alliance overview')
    @commands.guild_only()
    async def alliance(self, ctx: commands.Context, alliance: Optional[str] = None):
        """Show alliance overview; DB4D shows resources-only, others show full fields."""
        try:
            # Send initial loading message to be edited later
            initial_msg = await ctx.send("🔄 Loading Alliance Data...")

            # Resolve target alliance id
            target_id = None
            arg = (alliance or "").strip()
            if arg:
                if arg.isdigit():
                    try:
                        target_id = str(int(arg))
                    except Exception:
                        target_id = arg
                else:
                    try:
                        if self.query_system:
                            resolved = await self.query_system.resolve_alliance(arg)
                            if resolved and isinstance(resolved, dict) and resolved.get('id'):
                                target_id = str(resolved.get('id'))
                    except Exception:
                        target_id = None
            if not target_id:
                target_id = str(self.db4d_alliance_id)

            # Fetch nations via TTL cache
            nations: List[Dict] = await self.get_alliance_nations(target_id, force_refresh=False)

            if not nations:
                await initial_msg.edit(content="❌ No alliance data available.")
                return

            # Build initial view and embed for Alliance Totals
            view = AllianceTotalsView(
                author_id=ctx.author.id,
                bot=self.bot,
                alliance_cog=self,
                nations=nations,
                target_alliance_id=str(target_id)
            )
            embed = await view.generate_alliance_totals_embed(nations)

            # Edit the initial message to display the embed and attach the interactive view
            await initial_msg.edit(content=None, embed=embed, view=view)
        
        except Exception as e:
            self._log_error(f"Error in alliance command: {e}", e, "AllianceManager.alliance")
            await ctx.send(f"❌ An error occurred: {str(e)}")

    async def generate_alliance_totals_embed(self, nations: List[Dict[str, Any]]) -> discord.Embed:
        """Generate the alliance totals embed."""
        try:
            if not nations:
                return discord.Embed(
                    title="❌ No Alliance Data",
                    description="Failed to retrieve alliance data.",
                    color=discord.Color.red()
                )
            
            # Create a temporary AllianceTotalsView to use its embed generation method
            view = AllianceTotalsView(None, self.bot, self, nations, target_alliance_id=str(self.db4d_alliance_id))
            return await view.generate_alliance_totals_embed(nations)
            
        except Exception as e:
            self._log_error(f"Error in generate_alliance_totals_embed: {e}", e, "AllianceManager.generate_alliance_totals_embed")
            return discord.Embed(
                title="❌ Alliance Totals Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )

    _active_nations_cache = {}

async def setup(bot: commands.Bot):
    """Setup function for loading the cog."""
    try:
        await bot.add_cog(AllianceManager(bot))
        logging.info("Alliance Management System loaded successfully!")
    except Exception as e:
        logging.error(f"Failed to load Alliance Management System: {e}")
        logging.error(traceback.format_exc())
        raise

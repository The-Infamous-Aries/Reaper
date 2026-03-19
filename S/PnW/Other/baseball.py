import discord
from discord.ext import commands
from discord import app_commands
import os
import sys
import logging
import traceback
from typing import Dict, Any, Optional
from datetime import datetime

# Add parent directories to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from Systems.Functions.config import PANDW_API_KEY
from Systems.PnW.Util.query import create_v3_query_instance, V3GraphQuery

from Systems.Functions import emoji as emoji_mod

# Setup logging
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

class BaseballCog(commands.Cog):
    """Baseball team information commands for Politics & War."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.query_instance: Optional[V3GraphQuery] = None
        self.error_count = 0
        self.max_errors = 100
        
        # Initialize query instance
        try:
            self.query_instance = create_v3_query_instance(api_key=PANDW_API_KEY, logger=logger)
            logger.info("Baseball query instance initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize baseball query instance: {e}")
            self.query_instance = None

    def _log_error(self, error_msg: str, exception: Optional[Exception] = None, context: str = ""):
        """Centralized error logging with tracking."""
        self.error_count += 1
        if self.error_count > self.max_errors:
            self.error_count = 1
            logger.warning(f"Error count reset after reaching {self.max_errors}")
        
        full_msg = f"[Error #{self.error_count}] {error_msg}"
        if context:
            full_msg += f" (Context: {context})"
        
        if exception:
            full_msg += f" | Exception: {str(exception)}"
            logger.error(full_msg)
            logger.debug(f"Traceback: {traceback.format_exc()}")
        else:
            logger.error(full_msg)

    def _get_baseball_stars(self, quality: int, seating: int) -> str:
        """Calculate star rating based on quality and seating (both out of 100)."""
        total_score = quality + seating
        if total_score >= 180:
            return emoji_mod.mention('5star')
        elif total_score >= 160:
            return emoji_mod.mention('4star')
        elif total_score >= 140:
            return emoji_mod.mention('3star')
        elif total_score >= 120:
            return emoji_mod.mention('2star')
        elif total_score >= 100:
            return emoji_mod.mention('1star')
        else:
            return emoji_mod.mention('1star')

    def _get_win_percentage(self, wins: int, glosses: int) -> float:
        """Calculate win percentage."""
        total_games = wins + glosses
        if total_games == 0:
            return 0.0
        return (wins / total_games) * 100

    async def _fetch_nation_with_baseball_team(self, nation_query: str) -> Optional[Dict[str, Any]]:
        """Fetch nation data with baseball team information."""
        if not self.query_instance:
            self._log_error("Query instance not available", context="_fetch_nation_with_baseball_team")
            return None
        
        try:
            # Try different methods to resolve the nation
            nation_data = None
            
            # Check if it's a numeric ID
            if nation_query.isdigit():
                nation_data = await self.query_instance.get_nation_by_id(nation_query)
            else:
                # Try to resolve by nation name first
                nation_data = await self.query_instance.get_nation_by_name(nation_query)
                if not nation_data:
                    # Try leader name
                    nation_data = await self.query_instance.get_nation_by_leader(nation_query)
            
            if not nation_data:
                self._log_error(f"Could not resolve nation query: {nation_query}", context="_fetch_nation_with_baseball_team")
                return None
            
            return nation_data
                
        except Exception as e:
            self._log_error(f"Error fetching nation with baseball team for query: {nation_query}", e, "_fetch_nation_with_baseball_team")
            return None

    def _create_baseball_team_embed(self, nation_data: Dict[str, Any]) -> discord.Embed:
        """Create a rich embed for the baseball team data."""
        try:
            nation_name = nation_data.get('nation_name', 'Unknown Nation')
            leader_name = nation_data.get('leader_name', 'Unknown Leader')
            baseball_team = nation_data.get('baseball_team')
            
            if not baseball_team:
                embed = discord.Embed(
                    title="⚾ No Baseball Team",
                    description=f"{nation_name} does not have a baseball team.",
                    color=discord.Color.orange()
                )
                embed.set_footer(text=f"Nation: {nation_name} | Leader: {leader_name}")
                return embed
            
            team_name = baseball_team.get('name', 'Unnamed Team')
            team_id = baseball_team.get('id')
            logo = baseball_team.get('logo')
            stadium = baseball_team.get('stadium', 'Unknown Stadium')
            quality = baseball_team.get('quality', 0)
            seating = baseball_team.get('seating', 0)
            rating = baseball_team.get('rating', 0.0)
            wins = baseball_team.get('wins', 0)
            glosses = baseball_team.get('glosses', 0)
            runs = baseball_team.get('runs', 0)
            homers = baseball_team.get('homers', 0)
            strikeouts = baseball_team.get('strikeouts', 0)
            games_played = baseball_team.get('games_played', 0)
            
            # Calculate win percentage
            win_percentage = self._get_win_percentage(wins, glosses)
            
            # Get star rating
            star_rating = self._get_baseball_stars(quality, seating)
            
            # Create the embed
            possessive_suffix = "'" if nation_name.endswith('s') else "'s"
            embed = discord.Embed(
                title=f"⚾ {nation_name}{possessive_suffix} Baseball Team",
                url=f"https://politicsandwar.com/obl/team/id={team_id}",
                color=discord.Color.green()
            )
            
            # Set logo as thumbnail if available
            if logo:
                embed.set_thumbnail(url=logo)
            
            # Main description with team info
            embed.description = (
                f"**{rating:.1f}** {team_name} playing out of {star_rating} {emoji_mod.mention('field')} {stadium}\n"
                f"**Wins:** {wins}\n"
                f"**Losses:** {glosses}\n"
                f"**Win Rate:** {win_percentage:.1f}% ({games_played} games)"
            )
            
            # Statistics field
            stats_field = (
                f"{emoji_mod.mention('homerun')} **Homeruns:** {homers}\n"
                f"{emoji_mod.mention('run')} **Runs:** {runs}\n"
                f"{emoji_mod.mention('out')} **Strikeouts:** {strikeouts}"
            )
            embed.add_field(name=f"{emoji_mod.mention('ratio')} Career Statistics", value=stats_field, inline=False)
            
            # Team details field
            details_field = (
                f"**Quality:** {quality}/100\n"
                f"**Seating:** {seating}/100\n"
                f"**Rating:** {star_rating}"
            )
            embed.add_field(name=f"{emoji_mod.mention('field')} {stadium} Details", value=details_field, inline=False)
            
            # Footer with nation info
            embed.set_footer(
                text=f"Nation: {nation_name} | Leader: {leader_name} | Team ID: {team_id}",
                icon_url="https://politicsandwar.com/img/flags/1.png"  # Default flag icon
            )
            
            # Set timestamp
            embed.timestamp = datetime.now()
            
            return embed
            
        except Exception as e:
            self._log_error("Error creating baseball team embed", e, "_create_baseball_team_embed")
            return discord.Embed(
                title="❌ Baseball Team Error",
                description="An error occurred while creating the baseball team embed.",
                color=discord.Color.red()
            )

    @app_commands.command(name='baseball', description='Show baseball team information for a nation')
    @app_commands.describe(team='Nation name, leader name, or nation ID to query')
    async def baseball_team(self, interaction: discord.Interaction, team: str):
        """Show baseball team information for a nation."""
        try:
            # Defer the response to avoid timeout
            await interaction.response.defer()
            
            if not self.query_instance:
                embed = discord.Embed(
                    title="❌ Service Unavailable",
                    description="The baseball query service is currently unavailable. Please try again later.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Fetch nation data with baseball team
            nation_data = await self._fetch_nation_with_baseball_team(team)
            
            if not nation_data:
                embed = discord.Embed(
                    title="❌ Nation Not Found",
                    description=(
                        f"Could not find a nation matching: `{team}`\n\n"
                        "Please try searching with:\n"
                        "• Nation name (e.g., 'Example Nation')\n"
                        "• Leader name (e.g., 'Optimus Prime')\n"
                        "• Nation ID (e.g., '12345')"
                    ),
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Create and send the baseball team embed
            embed = self._create_baseball_team_embed(nation_data)
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            self._log_error(f"Error in baseball team command for query: {team}", e, "baseball_team")
            embed = discord.Embed(
                title="❌ Baseball Team Error",
                description=f"An error occurred while fetching baseball team data: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    """Setup function for loading the cog."""
    try:
        await bot.add_cog(BaseballCog(bot))
        logger.info("Baseball Cog loaded successfully!")
    except Exception as e:
        logger.error(f"Failed to load Baseball Cog: {e}")
        logger.error(traceback.format_exc())
        raise
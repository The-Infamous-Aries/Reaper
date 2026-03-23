import discord
from discord.ext import commands
from discord import app_commands
import os
import sys
import logging
import traceback
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, timezone
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from io import BytesIO
import numpy as np

# Add parent directories to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from Systems.Functions.config import PANDW_API_V3_KEY
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

class Activity(commands.Cog):
    """Activity statistics commands for Politics & War."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.query_instance: Optional[V3GraphQuery] = None
        self.error_count = 0
        self.max_errors = 100
        
        # Activity type mapping
        self.activity_types = {
            'All': 'total',
            'New': 'new',
            '1 Day': '1day',
            '2 Days': '2day', 
            '3 Days': '3day',
            '1 Week': '7day',
            '1 Month': '30day'
        }
        
        # Emoji mapping for activity types
        self.activity_emojis = {
            'total': emoji_mod.mention('total') or '📊',
            'new': emoji_mod.mention('new') or '🆕',
            '1day': emoji_mod.mention('1day') or '📅',
            '2day': emoji_mod.mention('2day') or '📅',
            '3day': emoji_mod.mention('3day') or '📅',
            '7day': emoji_mod.mention('7day') or '📅',
            '30day': emoji_mod.mention('30day') or '📅'
        }
        
        # Graph colors for each activity type
        self.graph_colors = {
            'new': '#0066CC',      # Blue
            '1day': '#00AA00',     # Green
            '2day': '#FFCC00',     # Yellow
            '3day': '#FF9900',     # Orange
            '7day': '#CC0000',     # Red
            '30day': '#9900CC'     # Purple
        }
        
        # Initialize query instance
        try:
            self.query_instance = create_v3_query_instance(api_key=PANDW_API_V3_KEY, logger=logger)
            logger.info("Activity query instance initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize activity query instance: {e}")
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

    def _parse_time_input(self, time_str: str) -> timedelta:
        """Parse time input like '2d', '4w', '1m' into timedelta."""
        time_str = time_str.lower().strip()
        
        if time_str.endswith('d'):
            days = int(time_str[:-1])
            return timedelta(days=days)
        elif time_str.endswith('w'):
            weeks = int(time_str[:-1])
            return timedelta(weeks=weeks)
        elif time_str.endswith('m'):
            months = int(time_str[:-1])
            return timedelta(days=months * 30)  # Approximate months as 30 days
        else:
            # Default to days if no suffix
            try:
                days = int(time_str)
                return timedelta(days=days)
            except ValueError:
                raise ValueError(f"Invalid time format: {time_str}. Use format like '2d', '4w', or '1m'")

    def _format_activity_line(self, activity_type: str, first_value: int, last_value: int) -> str:
        """Format a single activity line with emoji and change calculation."""
        emoji = self.activity_emojis.get(activity_type, emoji_mod.mention('piechart') or '📊')
        
        if first_value == 0:
            change_percent = 0 if last_value == 0 else 100
        else:
            change_percent = ((last_value - first_value) / first_value) * 100
        
        # Use proper up/down emojis from Stocks category
        if change_percent >= 0:
            change_emoji = emoji_mod.mention('perup')
        else:
            change_emoji = emoji_mod.mention('perdown')
        
        change_sign = '+' if change_percent >= 0 else ''
        
        # Format the type name
        if activity_type == '1day':
            type_name = '1 Day'
        elif activity_type == '2day':
            type_name = '2 Days'
        elif activity_type == '3day':
            type_name = '3 Days'
        elif activity_type == '7day':
            type_name = '1 Week'
        elif activity_type == '30day':
            type_name = '1 Month'
        elif activity_type == 'new':
            type_name = 'New Nations'
        else:
            type_name = 'Total Nations'
        
        return f"{emoji} **{type_name}:**\nStart- {first_value:,} | End- {last_value:,} | Change- {change_sign}{change_percent:.1f}% {change_emoji}"

    def _create_activity_embed(self, activity_data: List[Dict[str, Any]], activity_type: str, time_range: str) -> discord.Embed:
        """Create an embed for activity statistics."""
        try:
            if not activity_data:
                embed = discord.Embed(
                    title=f"{emoji_mod.mention('piechart')} No Activity Data",
                    description="No activity data available for the specified time range.",
                    color=discord.Color.orange()
                )
                return embed
            
            # Get first and last entries
            first_entry = activity_data[0]
            last_entry = activity_data[-1]
            
            # Create embed
            embed = discord.Embed(
                title=f"{emoji_mod.mention('piechart')} Politics & War Activity Statistics",
                description=f"**Time Range:** {time_range} | **Type:** {activity_type}",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            # Add activity statistics based on type
            if activity_type == 'All':
                # Show all types
                embed.add_field(
                    name=f"{emoji_mod.mention('total')} Total Nations",
                    value=self._format_activity_line('total', first_entry['total_nations'], last_entry['total_nations']),
                    inline=False
                )
                embed.add_field(
                    name=f"{emoji_mod.mention('new')} New Nations",
                    value=self._format_activity_line('new', first_entry['nations_created'], last_entry['nations_created']),
                    inline=False
                )
                embed.add_field(
                    name="📅 Activity Breakdown",
                    value=(
                        f"{self._format_activity_line('1day', first_entry['active_1_day'], last_entry['active_1_day'])}\n"
                        f"{self._format_activity_line('2day', first_entry['active_2_days'], last_entry['active_2_days'])}\n"
                        f"{self._format_activity_line('3day', first_entry['active_3_days'], last_entry['active_3_days'])}\n"
                        f"{self._format_activity_line('7day', first_entry['active_1_week'], last_entry['active_1_week'])}\n"
                        f"{self._format_activity_line('30day', first_entry['active_1_month'], last_entry['active_1_month'])}"
                    ),
                    inline=False
                )
            else:
                # Show specific type
                type_key = self.activity_types.get(activity_type, 'total')
                
                if type_key == 'total':
                    value = self._format_activity_line('total', first_entry['total_nations'], last_entry['total_nations'])
                    embed.add_field(name=f"{emoji_mod.mention('total')} Total Nations", value=value, inline=False)
                elif type_key == 'new':
                    value = self._format_activity_line('new', first_entry['nations_created'], last_entry['nations_created'])
                    embed.add_field(name=f"{emoji_mod.mention('new')} New Nations", value=value, inline=False)
                elif type_key == '1day':
                    value = self._format_activity_line('1day', first_entry['active_1_day'], last_entry['active_1_day'])
                    embed.add_field(name=f"{emoji_mod.mention('1day')} Active (1 Day)", value=value, inline=False)
                elif type_key == '2day':
                    value = self._format_activity_line('2day', first_entry['active_2_days'], last_entry['active_2_days'])
                    embed.add_field(name=f"{emoji_mod.mention('2day')} Active (2 Days)", value=value, inline=False)
                elif type_key == '3day':
                    value = self._format_activity_line('3day', first_entry['active_3_days'], last_entry['active_3_days'])
                    embed.add_field(name=f"{emoji_mod.mention('3day')} Active (3 Days)", value=value, inline=False)
                elif type_key == '7day':
                    value = self._format_activity_line('7day', first_entry['active_1_week'], last_entry['active_1_week'])
                    embed.add_field(name=f"{emoji_mod.mention('7day')} Active (1 Week)", value=value, inline=False)
                elif type_key == '30day':
                    value = self._format_activity_line('30day', first_entry['active_1_month'], last_entry['active_1_month'])
                    embed.add_field(name=f"{emoji_mod.mention('30day')} Active (1 Month)", value=value, inline=False)
            
            # Add date range info
            start_date = datetime.fromisoformat(first_entry['date'].replace('Z', '+00:00')).strftime('%Y-%m-%d')
            end_date = datetime.fromisoformat(last_entry['date'].replace('Z', '+00:00')).strftime('%Y-%m-%d')
            embed.add_field(
                name=f"{emoji_mod.mention('targetdate')} Date Range",
                value=f"From: {start_date}\nTo: {end_date}",
                inline=True
            )
            
            embed.set_footer(text=f"Data points: {len(activity_data)} | Powered by Politics & War API v3")
            
            return embed
            
        except Exception as e:
            self._log_error("Error creating activity embed", e, "_create_activity_embed")
            return discord.Embed(
                title="❌ Activity Embed Error",
                description="An error occurred while creating the activity embed.",
                color=discord.Color.red()
            )

    def _create_activity_graph(self, activity_data: List[Dict[str, Any]], activity_type: str) -> BytesIO:
        """Create a PIL graph for activity statistics."""
        try:
            plt.style.use('dark_background')
            fig, ax = plt.subplots(figsize=(12, 8))
            
            # Extract dates and convert to datetime objects
            dates = []
            for entry in activity_data:
                try:
                    date_str = entry['date'].replace('Z', '+00:00')
                    dates.append(datetime.fromisoformat(date_str))
                except:
                    continue
            
            if not dates:
                raise ValueError("No valid dates found in activity data")
            
            # Plot different activity types based on the selected type
            if activity_type == 'All':
                # Plot all types
                types_to_plot = ['new', '1day', '2day', '3day', '7day', '30day']
                labels = ['New Nations', 'Active (1 Day)', 'Active (2 Days)', 'Active (3 Days)', 'Active (1 Week)', 'Active (1 Month)']
                
                for i, (type_key, label) in enumerate(zip(types_to_plot, labels)):
                    if type_key == 'new':
                        values = [entry['nations_created'] for entry in activity_data]
                    elif type_key == '1day':
                        values = [entry['active_1_day'] for entry in activity_data]
                    elif type_key == '2day':
                        values = [entry['active_2_days'] for entry in activity_data]
                    elif type_key == '3day':
                        values = [entry['active_3_days'] for entry in activity_data]
                    elif type_key == '7day':
                        values = [entry['active_1_week'] for entry in activity_data]
                    elif type_key == '30day':
                        values = [entry['active_1_month'] for entry in activity_data]
                    
                    color = self.graph_colors[type_key]
                    ax.plot(dates, values, marker='o', linewidth=2, markersize=4, label=label, color=color)
                    
            else:
                # Plot specific type
                type_key = self.activity_types.get(activity_type, 'total')
                
                if type_key == 'total':
                    values = [entry['total_nations'] for entry in activity_data]
                    label = 'Total Nations'
                    color = '#FFFFFF'  # White for total
                elif type_key == 'new':
                    values = [entry['nations_created'] for entry in activity_data]
                    label = 'New Nations'
                    color = self.graph_colors['new']
                elif type_key == '1day':
                    values = [entry['active_1_day'] for entry in activity_data]
                    label = 'Active (1 Day)'
                    color = self.graph_colors['1day']
                elif type_key == '2day':
                    values = [entry['active_2_days'] for entry in activity_data]
                    label = 'Active (2 Days)'
                    color = self.graph_colors['2day']
                elif type_key == '3day':
                    values = [entry['active_3_days'] for entry in activity_data]
                    label = 'Active (3 Days)'
                    color = self.graph_colors['3day']
                elif type_key == '7day':
                    values = [entry['active_1_week'] for entry in activity_data]
                    label = 'Active (1 Week)'
                    color = self.graph_colors['7day']
                elif type_key == '30day':
                    values = [entry['active_1_month'] for entry in activity_data]
                    label = 'Active (1 Month)'
                    color = self.graph_colors['30day']
                else:
                    values = [entry['total_nations'] for entry in activity_data]
                    label = 'Total Nations'
                    color = '#FFFFFF'
                
                ax.plot(dates, values, marker='o', linewidth=3, markersize=5, label=label, color=color)
            
            # Customize the graph
            ax.set_xlabel('Date', fontsize=12, color='white')
            ax.set_ylabel('Number of Nations', fontsize=12, color='white')
            ax.set_title(f'Politics & War Activity Statistics - {activity_type}', fontsize=14, color='white', pad=20)
            
            # Format x-axis as dates
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(dates) // 10)))
            plt.xticks(rotation=45, ha='right')
            
            # Add grid
            ax.grid(True, alpha=0.3, color='gray')
            
            # Add legend
            ax.legend(loc='best', facecolor='black', edgecolor='white', fontsize=10)
            
            # Set background color
            fig.patch.set_facecolor('black')
            ax.set_facecolor('black')
            
            # Adjust layout
            plt.tight_layout()
            
            # Save to BytesIO
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor='black')
            buffer.seek(0)
            plt.close()
            
            return buffer
            
        except Exception as e:
            self._log_error("Error creating activity graph", e, "_create_activity_graph")
            plt.close()
            return None

    @app_commands.command(name='activity', description='Show Politics & War activity statistics')
    @app_commands.describe(
        type='Type of activity to display',
        time='Time range to display (e.g., 2d, 4w, 1m)'
    )
    @app_commands.choices(
        type=[
            app_commands.Choice(name='All', value='All'),
            app_commands.Choice(name='New', value='New'),
            app_commands.Choice(name='1 Day', value='1 Day'),
            app_commands.Choice(name='2 Days', value='2 Days'),
            app_commands.Choice(name='3 Days', value='3 Days'),
            app_commands.Choice(name='1 Week', value='1 Week'),
            app_commands.Choice(name='1 Month', value='1 Month')
        ]
    )
    async def activity_command(
        self, 
        interaction: discord.Interaction, 
        type: app_commands.Choice[str] = 'All',
        time: str = '30d'
    ):
        """Show Politics & War activity statistics with graph."""
        try:
            # Defer the response to avoid timeout
            await interaction.response.defer()
            
            if not self.query_instance:
                embed = discord.Embed(
                    title="❌ Service Unavailable",
                    description="The activity query service is currently unavailable. Please try again later.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Get the actual value from the Choice object
            type_value = type.value if hasattr(type, 'value') else type
            
            # Validate activity type
            if type_value not in self.activity_types and type_value != 'All':
                valid_types = ', '.join(['All'] + list(self.activity_types.keys()))
                embed = discord.Embed(
                    title="❌ Invalid Activity Type",
                    description=f"Please choose from: {valid_types}",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Parse time range
            try:
                time_delta = self._parse_time_input(time)
                end_date = datetime.now(timezone.utc)
                start_date = end_date - time_delta
                
                # Convert to API format (YYYY-MM-DD HH:MM:SS)
                after_str = start_date.strftime('%Y-%m-%d %H:%M:%S')
                before_str = end_date.strftime('%Y-%m-%d %H:%M:%S')
                
            except ValueError as e:
                embed = discord.Embed(
                    title="❌ Invalid Time Format",
                    description=str(e),
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Fetch activity data
            try:
                activity_response = await self.query_instance.get_activity_stats(
                    before=before_str,
                    after=after_str,
                    first=1000,  # Get up to 1000 data points
                    order_by=['DATE']
                )
                
                if not activity_response or not activity_response.get('data'):
                    embed = discord.Embed(
                        title="📊 No Activity Data",
                        description="No activity data available for the specified time range.",
                        color=discord.Color.orange()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                
                activity_data = activity_response['data']
                
            except Exception as e:
                self._log_error("Error fetching activity data", e, "activity_command")
                embed = discord.Embed(
                    title="❌ API Error",
                    description="An error occurred while fetching activity data from the API.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Create embed
            embed = self._create_activity_embed(activity_data, type_value, time)
            
            # Create graph
            graph_buffer = self._create_activity_graph(activity_data, type_value)
            
            # Send response
            if graph_buffer:
                file = discord.File(graph_buffer, filename='activity_graph.png')
                embed.set_image(url='attachment://activity_graph.png')
                await interaction.followup.send(embed=embed, file=file)
            else:
                await interaction.followup.send(embed=embed)
                
        except Exception as e:
            self._log_error(f"Error in activity command", e, "activity_command")
            embed = discord.Embed(
                title="❌ Activity Command Error",
                description=f"An error occurred while processing the activity command: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    """Setup function for loading the cog."""
    try:
        await bot.add_cog(Activity(bot))
        logger.info("Activity Cog loaded successfully!")
    except Exception as e:
        logger.error(f"Failed to load Activity Cog: {e}")
        logger.error(traceback.format_exc())
        raise
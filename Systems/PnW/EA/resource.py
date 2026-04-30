import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import os
import sys
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timedelta, timezone
import logging
import traceback
import io
import re

try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from Systems.PnW.Util.query import create_v3_query_instance, V3GraphQuery, NationResourceStat
from Systems.Functions.config import PANDW_API_KEY
from Systems.Functions.database_manager import get_latest_resource_prices
import Systems.Functions.emoji as emoji_mod

class ResourceCog(commands.Cog):
    """Cog for displaying nation resource statistics and game resource information."""
    
    def __init__(self, bot: commands.Bot):

        try:
            self.bot = bot
            self.api_key = PANDW_API_KEY
            self.logger = logging.getLogger(__name__)
            if not self.logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)
                self.logger.setLevel(logging.DEBUG)
            
            self.query_instance: Optional[V3GraphQuery] = None
            try:
                # Initialize query instance
                self.query_instance = create_v3_query_instance()
                self.logger.info("ResourceCog: Centralized query instance initialized successfully")
            except Exception as e:
                self.logger.error(f"ResourceCog: Failed to initialize query instance: {e}")
                self.query_instance = None

            if MATPLOTLIB_AVAILABLE:
                try:
                    plt.switch_backend('Agg')
                except Exception as e:
                    self.logger.warning(f"Failed to switch matplotlib backend to Agg: {e}")
                
        except Exception as e:
            print(f"ResourceCog: Error initializing ResourceCog: {e}")
            print(f"ResourceCog: Traceback: {traceback.format_exc()}")
            self.bot = bot
            self.api_key = PANDW_API_KEY
            self.query_instance = None

    def _log_error(self, error_msg: str, exception: Optional[Exception] = None, context: str = ""):
        """Centralized error logging with tracking."""
        try:
            full_msg = f"[ResourceCog] {error_msg}"
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
            print(f"ResourceCog: Error in error logging: {log_error}")

    def _format_resource_value(self, value: str) -> str:
        """Format resource value for display."""
        try:
            # Convert to float and format with commas
            num_value = float(value)
            if num_value >= 1_000_000:
                return f"{num_value/1_000_000:.2f}M"
            elif num_value >= 1_000:
                return f"{num_value/1_000:.1f}K"
            else:
                return f"{num_value:,.0f}"
        except (ValueError, TypeError):
            return str(value) if value else "0"

    def _get_resource_emoji(self, resource: str) -> str:
        """Get emoji for a resource type using the emoji module, with a fallback to Unicode."""
        if resource.lower() == 'money':
            return '💲'

        resource_mapping = {
            'food': 'food_1',
            'steel': 'steel_1',
            'aluminum': 'aluminum_1',
            'gasoline': 'gasoline_1',
            'munitions': 'munitions_1',
            'uranium': 'uranium_1',
            'coal': 'coal_1',
            'oil': 'oil_2',
            'iron': 'iron_1',
            'bauxite': 'bauxite_1',
            'lead': 'lead_1'
        }
        mapped_resource_name = resource_mapping.get(resource.lower())

        if mapped_resource_name:
            # Use the mention function, which handles whether the bot has the emoji
            emoji_str = emoji_mod.mention(mapped_resource_name)
            if emoji_str:
                return emoji_str

        # Fallback to Unicode if emoji not found
        fallback_emojis = {
            'food': '🍞',
            'steel': '🔩',
            'aluminum': '⚙️',
            'gasoline': '⛽',
            'munitions': '💣',
            'uranium': '☢️',
            'coal': '⚫',
            'oil': '🛢️',
            'iron': '🔧',
            'bauxite': '🟤',
            'lead': '🔫'
        }
        return fallback_emojis.get(resource.lower(), '📊')

    def _filter_stats_by_date(self, stats: List[NationResourceStat], 
                             start_date: Optional[datetime] = None, 
                             end_date: Optional[datetime] = None) -> List[NationResourceStat]:
        """Filter resource stats by date range."""
        if not stats:
            return []
        
        filtered_stats = []
        
        for stat in stats:
            try:
                # Parse the date from the stat
                stat_date = datetime.fromisoformat(stat['date'].replace('Z', '+00:00'))
                
                # Apply filters
                if start_date and stat_date < start_date:
                    continue
                if end_date and stat_date > end_date:
                    continue
                    
                filtered_stats.append(stat)
                
            except (ValueError, KeyError):
                # Skip entries with invalid dates
                continue
        
        return filtered_stats

    def get_dynamic_ylim(self, series_dict: Dict[str, List[float]], buffer_percent: float = 0.02) -> tuple[float, float]:
        """Calculate dynamic Y-axis limits with a buffer."""
        min_val = float('inf')
        max_val = float('-inf')

        for values in series_dict.values():
            if not values:
                continue
            min_val = min(min_val, min(values))
            max_val = max(max_val, max(values))

        if min_val == float('inf') or max_val == float('-inf'):
            return 0, 1  # Default range if no data

        # Add buffer
        if max_val == min_val:
            buffer = abs(max_val * buffer_percent)
        else:
            buffer = (max_val - min_val) * buffer_percent

        return min_val - buffer, max_val + buffer

    def _render_resource_graph_sync(self, history: List[NationResourceStat], selected_types: List[str], selected_individuals: List[str]) -> Optional[io.BytesIO]:
        """Synchronous graph rendering operation for resource stats showing absolute values."""
        if not MATPLOTLIB_AVAILABLE or not history or len(history) < 2:
            return None # Need at least 2 points to show trend

        # Define resource groups and colors (manufacturing theme)
        money_resource = {'money': '#008000'}     # Normal Green
        food_resource = {'food': 'silver'}
        manufactured_resources = {
            'steel': '#4B0082',        # Dark Purple
            'aluminum': '#00008B',     # Dark Blue
            'gasoline': '#B8860B',     # Dark Yellow
            'munitions': '#8B0000',    # Dark Red
        }
        raw_resources = {
            'uranium': '#32CD32',      # Lime Green
            'coal': '#9370DB',         # Light Purple
            'oil': '#FFFFE0',           # Light Yellow
            'iron': '#DDA0DD',         # Light Purple
            'bauxite': '#87CEEB',      # Light Blue
            'lead': '#CD5C5C'          # Light Red
        }
        all_resource_colors = {**money_resource, **food_resource, **manufactured_resources, **raw_resources}

        # Prepare Data - get absolute values (ensure chronological order)
        def get_series_values(resource_list, data):
            series = {}
            # Sort data by date to ensure chronological order
            sorted_data = sorted(data, key=lambda x: datetime.fromisoformat(x['date'].replace('Z', '+00:00')))
            for res in resource_list:
                values = []
                for entry in sorted_data:
                    val = float(entry.get(res, 0))
                    values.append(val)
                series[res] = values
            return series

        money_series = get_series_values(money_resource.keys(), history)
        food_series = get_series_values(food_resource.keys(), history)
        manufactured_series = get_series_values(manufactured_resources.keys(), history)
        raw_series = get_series_values(raw_resources.keys(), history)
        custom_series = get_series_values(selected_individuals, history)

        plot_configs = {
            "money": {"data": money_series, "colors": money_resource, "title": "Money", "formatter": lambda x, p: f'{x/1e9:.1f}B' if x >= 1e9 else f'{x/1e6:.0f}M'},
            "food": {"data": food_series, "colors": food_resource, "title": "Food", "formatter": lambda x, p: f'{x/1e6:.2f}M' if x >= 1e6 else f'{x/1e3:.0f}K'},
            "manufactured": {"data": manufactured_series, "colors": manufactured_resources, "title": "Manufactured Resources", "formatter": lambda x, p: f'{x/1e6:.2f}M' if x >= 1e6 else f'{x/1e3:.0f}K'},
            "raws": {"data": raw_series, "colors": raw_resources, "title": "Raw Resources", "formatter": lambda x, p: f'{x/1e6:.2f}M' if x >= 1e6 else f'{x/1e3:.0f}K'},
            "custom": {"data": custom_series, "colors": all_resource_colors, "title": "Custom Selection", "formatter": lambda x, p: f'{x/1e6:.2f}M' if x >= 1e6 else f'{x/1e3:.0f}K'},
        }

        active_plot_types = [ptype for ptype in ['money', 'food', 'manufactured', 'raws', 'custom'] if ptype in selected_types]
        if not active_plot_types:
            return None

        num_plots = len(active_plot_types)

        try:
            plt.style.use('dark_background')
            fig, axes = plt.subplots(
                num_plots, 1, figsize=(24, 8 * num_plots), sharex=True, gridspec_kw={'hspace': 0.5}
            )
            if num_plots == 1:
                axes = [axes]  # Make it iterable

            # Create informative title with date range (use sorted data)
            sorted_history = sorted(history, key=lambda x: datetime.fromisoformat(x['date'].replace('Z', '+00:00')))
            start_date = datetime.fromisoformat(sorted_history[0]['date'].replace('Z', '+00:00'))
            end_date = datetime.fromisoformat(sorted_history[-1]['date'].replace('Z', '+00:00'))
            date_range = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
            
            fig.suptitle(f"Resource Values Over Time\n{date_range}", fontsize=24, fontweight='bold')

            for i, plot_type in enumerate(active_plot_types):
                ax = axes[i]
                config = plot_configs[plot_type]
                series_data = config["data"]
                color_map = config["colors"]
                
                for res, values in series_data.items():
                    ax.plot(values, label=res.title(), color=color_map[res], linewidth=2.0, marker='o', markersize=5, linestyle='-', markerfacecolor='white', markeredgewidth=1, drawstyle='steps-post')
                    for j, value in enumerate(values):
                        offset_y = 12 if j % 2 == 0 else -22
                        ax.annotate(f'{self._format_resource_value(str(int(value)))}', 
                                          xy=(j, value), 
                                          xytext=(0, offset_y),
                                          textcoords='offset points', 
                                          ha='center', 
                                          fontsize=8,
                                          bbox=dict(boxstyle='round,pad=0.2', facecolor=color_map[res], alpha=0.75),
                                          arrowprops=dict(arrowstyle='-', lw=0.4, color='white', alpha=0.6))
                
                ax.set_title(config["title"], fontsize=18, fontweight='bold')
                ax.set_ylabel("Amount", fontsize=16)
                ax.set_ylim(self.get_dynamic_ylim(series_data))
                ax.yaxis.set_major_formatter(plt.FuncFormatter(config["formatter"]))
                ax.grid(True, which="both", ls="--", alpha=0.2)
                ax.tick_params(axis='both', which='major', labelsize=14)
                if plot_type in ["manufactured", "raws"]:
                    ax.legend(loc='upper right', bbox_to_anchor=(1.15, 1), borderaxespad=0., fontsize=14)

            # --- Configure Shared X-Axis (on the bottom plot) ---
            ax_bottom = axes[-1]
            # Use the already sorted data for consistent X-axis
            dates = [datetime.fromisoformat(entry['date'].replace('Z', '+00:00')) for entry in sorted_history]
            num_days = len(dates)

            if num_days > 1:
                # Calculate time span in days
                time_span_days = (dates[-1] - dates[0]).days
                
                tick_positions = []
                tick_labels = []
                
                if time_span_days <= 7:
                    # Daily ticks for short periods
                    tick_spacing = max(1, num_days // 7)
                    tick_positions = list(range(0, num_days, tick_spacing))
                    tick_labels = [dates[i].strftime('%b %d') for i in tick_positions]
                    ax_bottom.set_xlabel(f"Date (Starting {dates[0].strftime('%Y-%m-%d')})")
                elif time_span_days <= 31:
                    # Weekly ticks for monthly periods
                    tick_spacing = max(1, num_days // 4)
                    tick_positions = list(range(0, num_days, tick_spacing))
                    tick_labels = [dates[i].strftime('%b %d') for i in tick_positions]
                    ax_bottom.set_xlabel(f"Date (Starting {dates[0].strftime('%Y-%m-%d')})")
                elif time_span_days <= 365:
                    # Monthly ticks for yearly periods
                    tick_spacing = max(7, num_days // 12)
                    tick_positions = list(range(0, num_days, tick_spacing))
                    tick_labels = [dates[i].strftime('%b %Y') if i == 0 or dates[i].month != dates[i-1].month else dates[i].strftime('%b %d') for i in tick_positions]
                    ax_bottom.set_xlabel("Date")
                else:
                    # Quarterly ticks for multi-year periods
                    tick_spacing = max(30, num_days // 8)
                    tick_positions = list(range(0, num_days, tick_spacing))
                    tick_labels = [dates[i].strftime('%b %Y') for i in tick_positions]
                    ax_bottom.set_xlabel("Date")

                if tick_positions:
                    ax_bottom.set_xticks(tick_positions)
                    ax_bottom.set_xticklabels(tick_labels, rotation=30, ha='right')

            ax_bottom.set_xlim(0, len(history) - 1 if len(history) > 1 else 1)
            
            plt.tight_layout(rect=[0, 0.03, 0.9, 0.95])

            buf = io.BytesIO()
            fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
            buf.seek(0)
            plt.close(fig)
            return buf
            
        except Exception as e:
            self.logger.error(f"Error rendering multi-plot resource graph: {e}")
            return None

    async def _render_resource_graph(self, history: List[NationResourceStat], selected_types: List[str], selected_individuals: List[str]) -> Optional[discord.File]:
        """Asynchronous wrapper for resource graph rendering."""
        if not MATPLOTLIB_AVAILABLE:
            return None
            
        buf = await asyncio.to_thread(self._render_resource_graph_sync, history, selected_types, selected_individuals)
        if buf:
            return discord.File(buf, filename="resource_graph.png")
        return None

    async def create_resource_stats_embed(self, resource_stats: List[NationResourceStat], 
                                        selected_types: List[str],
                                        selected_individuals: List[str],
                                        start_date_obj: Optional[datetime] = None, 
                                        end_date_obj: Optional[datetime] = None) -> discord.Embed:
        """Create a rich embed for nation resource statistics."""
        try:
            world_emojis = {
                'globe': emoji_mod.mention('globe') or '🌍'
            }
            
            if not resource_stats or len(resource_stats) < 2:
                embed = discord.Embed(
                    title="📊 Nation Resource Statistics",
                    description="Not enough data to generate a trend. Please select a wider time range.",
                    color=discord.Color.orange()
                )
                if start_date_obj and end_date_obj:
                    embed.description = f"No data available for the requested range: **{start_date_obj.strftime('%Y-%m-%d')}** to **{end_date_obj.strftime('%Y-%m-%d')}**."

                if resource_stats:
                    latest_stats = resource_stats[0]
                    embed.description = "Only one data point available. Showing latest stats:"
                    for res_key, res_name in [('money', 'Money'), ('food', 'Food'), ('steel', 'Steel'), ('aluminum', 'Aluminum'), ('gasoline', 'Gasoline'), ('munitions', 'Munitions'), ('uranium', 'Uranium'), ('coal', 'Coal'), ('oil', 'Oil'), ('iron', 'Iron'), ('bauxite', 'Bauxite'), ('lead', 'Lead')]:
                        if res_key in latest_stats and latest_stats[res_key]:
                            value = self._format_resource_value(latest_stats[res_key])
                            emoji = self._get_resource_emoji(res_key)
                            embed.add_field(name=f"{emoji} {res_name}", value=f"**{value}**", inline=True)
                return embed

            start_stats = resource_stats[0]
            end_stats = resource_stats[-1]

            # Determine date range for description
            start_str = start_date_obj.strftime('%Y-%m-%d') if start_date_obj else start_stats['date'][:10]
            end_str = end_date_obj.strftime('%Y-%m-%d') if end_date_obj else end_stats['date'][:10]
            
            days_diff_str = ""
            if start_date_obj and end_date_obj:
                delta = end_date_obj - start_date_obj
                num_days = round(delta.total_seconds() / 86400)
                days_diff_str = f" ({num_days} days)"
            else:
                # Fallback to calculating from data if no objects passed
                s_date = datetime.fromisoformat(start_stats['date'].replace('Z', '+00:00'))
                e_date = datetime.fromisoformat(end_stats['date'].replace('Z', '+00:00'))
                delta = e_date - s_date
                num_days = round(delta.total_seconds() / 86400)
                days_diff_str = f" ({num_days} days)"

            embed = discord.Embed(
                title=f"{world_emojis['globe']} Game Resource/Nation Trend",
                description=f"Showing trend from **{start_str}** to **{end_str}**{days_diff_str}.",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )

            # Add resource fields with change calculation
            resource_groups = {
                'money': [('money', 'Money')],
                'food': [('food', 'Food')],
                'manufactured': [('steel', 'Steel'), ('aluminum', 'Aluminum'), ('gasoline', 'Gasoline'), ('munitions', 'Munitions')],
                'raws': [('uranium', 'Uranium'), ('coal', 'Coal'), ('oil', 'Oil'), ('iron', 'Iron'), ('bauxite', 'Bauxite'), ('lead', 'Lead')]
            }

            all_individual_resources = {
                res[0]: res[1] for group in resource_groups.values() for res in group
            }
            
            resources_to_show_set = set()

            # Add resources from selected groups
            for r_type in selected_types:
                if r_type in resource_groups:
                    for res_key, _ in resource_groups[r_type]:
                        resources_to_show_set.add(res_key)
            
            # Add individual resources
            for res_key in selected_individuals:
                resources_to_show_set.add(res_key)

            # Create the final list, maintaining a reasonable order
            ordered_resource_keys = ['money', 'food', 'steel', 'aluminum', 'gasoline', 'munitions', 'uranium', 'coal', 'oil', 'iron', 'bauxite', 'lead']
            resources_to_show = [(key, all_individual_resources[key]) for key in ordered_resource_keys if key in resources_to_show_set]

            for key, name in resources_to_show:
                start_val = float(start_stats.get(key, 0))
                end_val = float(end_stats.get(key, 0))
                
                if start_val > 0:
                    percent_change = ((end_val - start_val) / start_val) * 100
                    change_str = f"**{percent_change:+.2f}%**"
                else:
                    change_str = "_N/A_"

                emoji = self._get_resource_emoji(key)
                
                value_str = (
                    f"Start: **{self._format_resource_value(str(start_val))}**\n"
                    f"End:   **{self._format_resource_value(str(end_val))}**\n"
                    f"Change: {change_str}"
                )

                embed.add_field(
                    name=f"{emoji} {name}",
                    value=value_str,
                    inline=False
                )

            embed.set_footer(text="Data from Politics & War API")
            return embed

        except Exception as e:
            self._log_error("Error creating resource stats embed", e, "create_resource_stats_embed")
            embed = discord.Embed(
                title="❌ Resource Statistics Error",
                description="An error occurred while creating the resource statistics embed.",
                color=discord.Color.red()
            )
            return embed

    def _parse_date_input(self, date_input: Optional[str]) -> Optional[datetime]:
        """Parse date input string into a timezone-aware datetime object (UTC)."""
        if date_input is None:
            return None
        
        date_input_lower = date_input.lower().strip()
        if date_input_lower == 'now':
            return datetime.now(timezone.utc)

        date_input = date_input.lower().strip()
        dt: Optional[datetime] = None
        
        try:
            # Short format parsing (e.g., 7d, 9w, 3m)
            match = re.match(r'^(\d+)\s*(d|w|m)$', date_input)
            if match:
                value = int(match.group(1))
                unit = match.group(2)
                if unit == 'd':
                    dt = datetime.now(timezone.utc) - timedelta(days=value)
                elif unit == 'w':
                    dt = datetime.now(timezone.utc) - timedelta(weeks=value)
                elif unit == 'm':
                    dt = datetime.now(timezone.utc) - timedelta(days=value * 30)  # Approximate
            # "X days/weeks/months ago" format
            elif 'days ago' in date_input or 'day ago' in date_input:
                days_match = re.search(r'(\d+)\s*days?\s*ago', date_input)
                if days_match:
                    days = int(days_match.group(1))
                    dt = datetime.now(timezone.utc) - timedelta(days=days)
            elif 'weeks ago' in date_input or 'week ago' in date_input:
                weeks_match = re.search(r'(\d+)\s*weeks?\s*ago', date_input)
                if weeks_match:
                    weeks = int(weeks_match.group(1))
                    dt = datetime.now(timezone.utc) - timedelta(weeks=weeks)
            elif 'months ago' in date_input or 'month ago' in date_input:
                months_match = re.search(r'(\d+)\s*months?\s*ago', date_input)
                if months_match:
                    months = int(months_match.group(1))
                    dt = datetime.now(timezone.utc) - timedelta(days=months * 30)
            # ISO format with timezone
            elif 't' in date_input:
                dt = datetime.fromisoformat(date_input.replace('z', '+00:00'))
            # YYYY-MM-DD format
            elif len(date_input) == 10 and '-' in date_input:
                dt = datetime.strptime(date_input, '%Y-%m-%d')
            # Legacy formats (backward compatibility)
            elif 'day' in date_input:
                days = int(''.join(filter(str.isdigit, date_input)))
                dt = datetime.now(timezone.utc) - timedelta(days=days)
            elif 'week' in date_input:
                weeks = int(''.join(filter(str.isdigit, date_input)))
                dt = datetime.now(timezone.utc) - timedelta(weeks=weeks)
            elif 'month' in date_input:
                months = int(''.join(filter(str.isdigit, date_input)))
                dt = datetime.now(timezone.utc) - timedelta(days=months * 30)
        except (ValueError, TypeError) as e:
            self.logger.error(f"Date parsing error for input '{date_input}': {e}")
            return None

        # Ensure the datetime is timezone-aware
        if dt and dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        
        return dt

    @commands.hybrid_command(name='game_resources', description='Display nation resource statistics for a given time window')  # type: ignore
    @app_commands.describe(start='Start date (how far back to go, e.g., "7 days ago", "2024-01-01")', 
                          finish='End date (when to end time window, e.g., "now", "2024-01-31")',
                          types='Select graphs to display. Can be groups (Manufactured, Raws) or individual resources. Defaults to "All".')
    async def game_resources_command(self, ctx: commands.Context, start: Optional[str] = None, finish: Optional[str] = None, types: str = "All"):
        try:
            interaction = getattr(ctx, 'interaction', None)
            is_slash = isinstance(interaction, discord.Interaction)
            if is_slash and interaction is not None and hasattr(interaction, 'response') and not interaction.response.is_done():
                await interaction.response.defer()

            if not self.query_instance:
                embed = discord.Embed(
                    title="❌ API Error",
                    description="Resource statistics service is currently unavailable.",
                    color=discord.Color.red()
                )
                if is_slash and interaction is not None and hasattr(interaction, 'followup'):
                    await interaction.followup.send(embed=embed)
                else:
                    await ctx.send(embed=embed)
                return

            # Parse date parameters
            start_date = self._parse_date_input(start)
            end_date = self._parse_date_input(finish)

            # If no end date is specified, default to now to prevent future data
            if end_date is None:
                end_date = datetime.now(timezone.utc)

            # Parse types
            raw_types = types.lower()
            
            # Define valid groups and individual resources
            valid_groups = {'manufactured', 'raws', 'money', 'food'}
            all_resources = {
                'steel', 'aluminum', 'gasoline', 'munitions', 'uranium', 'coal', 
                'oil', 'iron', 'bauxite', 'lead', 'money', 'food'
            }

            if raw_types == 'all':
                selected_groups = list(valid_groups)
                selected_individuals = []
            else:
                user_selections = [t.strip() for t in raw_types.split(',')]
                selected_groups = [s for s in user_selections if s in valid_groups]
                selected_individuals = [s for s in user_selections if s in all_resources and s not in valid_groups]

            # If no valid selections, default to all
            if not selected_groups and not selected_individuals:
                selected_groups = list(valid_groups)
            
            # This will be passed to the rendering functions
            active_graphs = selected_groups.copy()
            if selected_individuals:
                active_graphs.append('custom')

            # Get all resource statistics (API returns all historical data)
            all_resource_stats = await self.query_instance.get_nation_resource_stats()
            
            if not all_resource_stats:
                embed = discord.Embed(
                    title="❌ No Data",
                    description="Unable to retrieve resource statistics from the API.",
                    color=discord.Color.red()
                )
                if is_slash and interaction is not None and hasattr(interaction, 'followup'):
                    await interaction.followup.send(embed=embed)
                else:
                    await ctx.send(embed=embed)
                return

            # Filter by date range if specified
            filtered_stats = self._filter_stats_by_date(all_resource_stats, start_date, end_date)
            
            if not filtered_stats:
                # If no stats in range, show latest available
                embed = discord.Embed(title="<:search:1234567890> No Data", description=f"No data found for the specified time range (`{start}` to `{finish}`).\nPlease try a different range.", color=discord.Color.orange())
                if is_slash and interaction is not None and hasattr(interaction, 'followup'):
                    await interaction.followup.send(embed=embed)
                else:
                    await ctx.send(embed=embed)
                return

            # Generate graph
            graph_file = await self._render_resource_graph(filtered_stats, active_graphs, selected_individuals)

            # Create and send embed
            embed = await self.create_resource_stats_embed(
                filtered_stats, 
                active_graphs,
                selected_individuals,
                start_date, 
                end_date
            )
            
            if graph_file:
                embed.set_image(url="attachment://resource_graph.png")
            
            if is_slash and interaction is not None and hasattr(interaction, 'followup'):
                await interaction.followup.send(embed=embed, file=graph_file or discord.utils.MISSING)
            else:
                await ctx.send(embed=embed, file=graph_file or discord.utils.MISSING)

        except Exception as e:
            self._log_error("Error in game_resources command", e, "game_resources_command")
            embed = discord.Embed(
                title="❌ Resource Statistics Error",
                description=(
                    f"An error occurred while retrieving resource statistics.\n\n"
                    f"Please try again with different date parameters or contact an administrator if the issue persists."
                ),
                color=discord.Color.red()
            )
            if is_slash and interaction and hasattr(interaction, 'followup'):
                await interaction.followup.send(embed=embed)
            else:
                await ctx.send(embed=embed)

    async def _build_trade_embed(
        self,
        data: List[Dict[str, Any]],
        display_mode: str,
        amounts_map: Dict[str, Optional[float]],
        emoji_map: Dict[str, str],
        prefer_emoji: bool,
        price_type: str = "average"
    ) -> discord.Embed:
        """Synchronous helper to build the trade values embed."""
        raw_resources = {"FOOD", "COAL", "OIL", "URANIUM", "LEAD", "IRON", "BAUXITE"}
        refined_resources = {"GASOLINE", "MUNITIONS", "STEEL", "ALUMINUM"}
        special_resources = {"CREDIT"}

        # Build price_map from data (used for non-conversion modes; conversion uses pre-built price_map passed in)
        price_map = {}
        if price_type == "selling":  # User is selling → use best_buy_price (highest buyer offer)
            price_map = {str(item.get("resource") or "").upper(): float(item.get("best_buy_offer", {}).get("price") or 0) for item in data}
        elif price_type == "buying":  # User is buying → use best_sell_price (lowest seller offer)
            price_map = {str(item.get("resource") or "").upper(): float(item.get("best_sell_offer", {}).get("price") or 0) for item in data}
        else:  # average or fallback
            price_map = {str(item.get("resource") or "").upper(): float(item.get("average_price") or 0) for item in data}

        def fmt_name(r: str) -> str:
            return r.capitalize() if r else r

        # Mode logic
        mode_key = (display_mode or "average").strip().lower()

        if mode_key == "conversion":
            provided = [(k, float(v)) for k, v in amounts_map.items() if v is not None and float(v) > 0]
            if not provided:
                return discord.Embed(description="No resources provided for conversion.", color=discord.Color.red())

            # Determine label for price type
            if price_type == "selling":
                price_label = "Best Buy Offer (you're selling)"
            elif price_type == "buying":
                price_label = "Best Sell Offer (you're buying)"
            else:
                price_label = "Average Price"

            # Build conversion embed with per-resource breakdown and totals
            embed = discord.Embed(
                description=f"Convert resource units into money using {price_label}",
                color=discord.Color.blurple(),
            )
            try:
                embed.set_author(name="Resource Conversion")
            except Exception:
                embed.title = "Resource Conversion"

            grand_total = 0.0
            money_emoji = '$'
            for res_key, amt in provided:
                unit_price = float(price_map.get(res_key, 0) or 0)
                total_value = unit_price * amt
                grand_total += total_value
                emoji = emoji_map.get(res_key)
                name_disp = f"{emoji} {fmt_name(res_key)}" if prefer_emoji and emoji else fmt_name(res_key)
                embed.add_field(name=name_disp, value=f"Units: {amt:,.2f} • Unit: {money_emoji}{unit_price:,.2f} • Total: {money_emoji}{total_value:,.2f}", inline=False)

            embed.add_field(name="Grand Total", value=f"{money_emoji}{grand_total:,.2f}", inline=False)
            embed.set_footer(text="Data source: P&W GraphQL API")
            return embed
        elif mode_key == "average":
            title_name = "Average Prices"
            description_text = "Average daily prices for each resource"
            color = discord.Color.blue()
            price_key_root = "average_price"
            price_key_nested = None
            no_offer_text = "N/A"
        elif mode_key == "best buy offer":
            title_name = "Best Buy Offers"
            description_text = "Highest Listed (Best Buy Offer) for each resource"
            color = discord.Color.green()
            price_key_root = "best_buy_offer"
            price_key_nested = "price"
            no_offer_text = "No Active Buy Offers"
        elif mode_key == "best sell offer":
            title_name = "Best Sell Offers"
            description_text = "Lowest Listed (Best Sell Offer) for each resource"
            color = discord.Color.gold()
            price_key_root = "best_sell_offer"
            price_key_nested = "price"
            no_offer_text = "No Active Sell Offers"
        elif mode_key == "margin":
            title_name = "Trade Margins"
            description_text = "Difference between Best Sell and Best Buy offers"
            color = discord.Color.purple()
            price_key_root = None  # Handled separately
            price_key_nested = None # Handled separately
            no_offer_text = "N/A"
        else: # Fallback for unknown modes
            title_name = "Average Prices"
            description_text = "Average daily prices for each resource"
            color = discord.Color.blue()
            price_key_root = "average_price"
            price_key_nested = None
            no_offer_text = "N/A"

        # Logic for 'All' (Average Prices), 'Best Buy Offer', 'Best Sell Offer' and 'Average' modes
        raw_lines = []
        ref_lines = []
        spec_lines = []
        for item in sorted(data, key=lambda x: x.get("resource", "")):
            res = (item.get("resource") or "").upper()
            margin = None

            # Get price based on price_key_root and price_key_nested
            if mode_key == "margin":
                best_buy_price = item.get("best_buy_offer", {}).get("price")
                best_sell_price = item.get("best_sell_offer", {}).get("price")

                if best_buy_price is not None and best_sell_price is not None:
                    margin = best_sell_price - best_buy_price
                    if best_buy_price != 0:
                        percent_margin = (margin / best_buy_price) * 100
                        display_price = f"Buy: ${best_buy_price:,.2f} | Sell: ${best_sell_price:,.2f} | Margin: ${margin:,.2f} ({percent_margin:.2f}%)"
                    else:
                        display_price = f"Buy: ${best_buy_price:,.2f} | Sell: ${best_sell_price:,.2f} | Margin: ${margin:,.2f} (N/A%)"
                else:
                    display_price = "No sufficient offers for margin calculation"
            else:
                # Existing logic for other modes (average, best buy, best sell)
                price = None
                if price_key_nested and price_key_root:
                    price = item.get(price_key_root, {}).get(price_key_nested)
                elif price_key_root:
                    price = item.get(price_key_root)
                display_price = f"${price:,.2f}" if price else no_offer_text

            emoji = emoji_map.get(res)
            line = f"{emoji} {fmt_name(res)}: {display_price}" if prefer_emoji and emoji else f"{fmt_name(res)}: {display_price}"

            if mode_key == "margin" and margin is not None and margin < 0:
                line = f"**{line}**"

            if res in raw_resources:
                raw_lines.append(line)
            elif res in refined_resources:
                ref_lines.append(line)
            elif res in special_resources:
                spec_lines.append(line)
            else:
                ref_lines.append(line)

        embed = discord.Embed(
            description=description_text,
            color=color,
        )
        try:
            embed.set_author(name=title_name)
        except Exception:
            embed.title = title_name
        if raw_lines:
            embed.add_field(name="Raw Materials", value="\n".join(raw_lines), inline=False)
        if ref_lines:
            embed.add_field(name="Refined Materials", value="\n".join(ref_lines), inline=False)
        if spec_lines:
            embed.add_field(name="Special", value="\n".join(spec_lines), inline=False)

        embed.set_footer(text="Data source: P&W GraphQL API")
        return embed

    @commands.hybrid_group(  # type: ignore
        name="trade",
        description="Trade related commands"
    )
    async def trade(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @trade.command(  # type: ignore
        name="values",
        description="Show average resource prices"
    )
    @app_commands.describe(
        mode="Choose 'Average' for average prices, 'Best Buy', 'Best Sell', or 'Margin'",
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Average", value="average"),
            app_commands.Choice(name="Best Sell", value="best sell offer"),
            app_commands.Choice(name="Best Buy", value="best buy offer"),
            app_commands.Choice(name="Margin", value="margin"),
        ]
    )
    async def values(self, ctx: commands.Context, mode: str = "average"):
        """Display resource prices."""
        try:
            if not self.query_instance:
                await ctx.send("Trade query is unavailable. Please try again later.")
                return

            data = await self.query_instance.get_trade_resource_values()
            if not data:
                await ctx.send("Could not fetch trade values from the API.") 
                return

            emoji_map = emoji_mod.resource_codes()
            prefer_emoji = True

            embed = await self._build_trade_embed(
                data,
                mode,
                {},  # No amounts for this mode
                emoji_map,
                prefer_emoji
            )

            if embed is None:
                await ctx.send("Could not generate the trade values embed.")
                return

            await ctx.send(embed=embed)
        except Exception:
            await ctx.send("An unexpected error occurred while building the trade values embed.")

    @trade.command(  # type: ignore
        name="convert",
        description="Convert resource units to value"
    )
    @app_commands.describe(
        food="Units of Food to convert",
        coal="Units of Coal to convert",
        oil="Units of Oil to convert",
        uranium="Units of Uranium to convert",
        lead="Units of Lead to convert",
        iron="Units of Iron to convert",
        bauxite="Units of Bauxite to convert",
        gasoline="Units of Gasoline to convert",
        munitions="Units of Munitions to convert",
        steel="Units of Steel to convert",
        aluminum="Units of Aluminum to convert",
        credit="Units of Credit to convert"
    )
    @app_commands.describe(
        price_type="Choose 'I'm Selling' (best buy offer) or 'I'm Buying' (best sell offer)"
    )
    @app_commands.choices(
        price_type=[
            app_commands.Choice(name="I'm Selling (Best Buy Offer)", value="selling"),
            app_commands.Choice(name="I'm Buying (Best Sell Offer)", value="buying"),
            app_commands.Choice(name="Average Price", value="average"),
        ]
    )
    async def convert(
        self,
        ctx: commands.Context,
        food: Optional[float] = None,
        coal: Optional[float] = None,
        oil: Optional[float] = None,
        uranium: Optional[float] = None,
        lead: Optional[float] = None,
        iron: Optional[float] = None,
        bauxite: Optional[float] = None,
        gasoline: Optional[float] = None,
        munitions: Optional[float] = None,
        steel: Optional[float] = None,
        aluminum: Optional[float] = None,
        credit: Optional[float] = None,
        price_type: str = "average",
    ):
        """Convert a resource amount to its value."""
        # Defer immediately to prevent Discord interaction timeout
        if hasattr(ctx, 'interaction') and ctx.interaction is not None:
            await ctx.interaction.response.defer()

        try:
            # Build price_map from DB (fast, updated every 15 min), fallback to API
            db_prices = await get_latest_resource_prices()
            if db_prices:
                # Build normalized price_map_data from DB regardless of price_type
                # (price_type selection happens inside _build_trade_embed)
                price_map_data = [
                    {
                        "resource": res.upper(),
                        "best_buy_offer": {"price": vals.get("buy", 0)},
                        "best_sell_offer": {"price": vals.get("sell", 0)},
                        "average_price": vals.get("avg", 0),
                    }
                    for res, vals in db_prices.items()
                ]
            else:
                # Fallback to live API
                if not self.query_instance:
                    await ctx.send("Trade query is unavailable. Please try again later.")
                    return
                price_map_data = await self.query_instance.get_trade_resource_values()
                if not price_map_data:
                    await ctx.send("Could not fetch trade values.")
                    return

            emoji_map = emoji_mod.resource_codes()
            prefer_emoji = True

            amounts_map = {
                "FOOD": food,
                "COAL": coal,
                "OIL": oil,
                "URANIUM": uranium,
                "LEAD": lead,
                "IRON": iron,
                "BAUXITE": bauxite,
                "GASOLINE": gasoline,
                "MUNITIONS": munitions,
                "STEEL": steel,
                "ALUMINUM": aluminum,
                "CREDIT": credit,
            }

            embed = await self._build_trade_embed(
                price_map_data,
                "conversion",
                amounts_map,
                emoji_map,
                prefer_emoji,
                price_type
            )

            if embed is None:
                await ctx.send("Provide units for any resource fields to convert, e.g., /trade convert iron:200 oil:50")
                return

            if hasattr(ctx, 'interaction') and ctx.interaction is not None:
                await ctx.interaction.followup.send(embed=embed)
            else:
                await ctx.send(embed=embed)
        except Exception as e:
            err_msg = "An unexpected error occurred while building the trade values embed."
            try:
                if hasattr(ctx, 'interaction') and ctx.interaction is not None:
                    await ctx.interaction.followup.send(err_msg)
                else:
                    await ctx.send(err_msg)
            except Exception:
                pass

async def setup(bot: commands.Bot):
    """Setup function to add the ResourceCog to the bot."""
    try:
        await bot.add_cog(ResourceCog(bot))
        logging.getLogger(__name__).info("ResourceCog: Successfully added to bot")
    except Exception as e:
        logging.getLogger(__name__).error(f"ResourceCog: Failed to add cog: {e}")
    
    # Ensure slash command is registered in the tree
    try:
        # Avoid duplicates; register if not present
        existing = [cmd for cmd in bot.tree.get_commands() if getattr(cmd, 'name', '') == 'game_resources']
        if not existing:
            cog = bot.get_cog('ResourceCog')
            if cog:
                # Prefer the cog's hybrid command attribute when available
                if hasattr(cog, 'game_resources_command'):
                    try:
                        bot.tree.add_command(cog.game_resources_command)
                        logging.getLogger(__name__).info("ResourceCog: 'game_resources' command added to tree")
                    except Exception:
                        # Fallback: search cog's app commands list
                        for maybe_cmd in getattr(cog, '__cog_app_commands__', []):
                            try:
                                if isinstance(maybe_cmd, app_commands.Command) and maybe_cmd.name == 'game_resources':
                                    bot.tree.add_command(maybe_cmd)
                                    logging.getLogger(__name__).info("ResourceCog: 'game_resources' app command added to tree (fallback)")
                                    break
                            except Exception:
                                continue
    except Exception as e:
        logging.getLogger(__name__).error(f"ResourceCog: Command registration/sync issue: {e}")
import discord
from discord import app_commands, ui
from discord.ext import commands, tasks
import time
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Optional, Tuple
import io
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import asyncio
import json
import os
from PIL import Image, ImageDraw, ImageFont
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_agg import FigureCanvasAgg
import numpy as np
import Systems.Functions.json_database as db
import Systems.Functions.emoji as emoji_mod

def _prepare_dataframe(raw_data: List[Tuple[int, str, float]]) -> pd.DataFrame:
    """Converts raw price data into a prepared pandas DataFrame."""
    if not raw_data:
        return pd.DataFrame()
    
    df = pd.DataFrame(raw_data, columns=['timestamp', 'resource', 'price'])
    df['date'] = pd.to_datetime(df['timestamp'], unit='s')
    df = df.drop_duplicates(subset=['date', 'resource'], keep='last').sort_values('date')
    return df

def _render_graph_process(price_data, title, single_resource, with_indicators, scale, width, height, start_ts=None, end_ts=None):
    """
    Generates a graph image from price data in a separate process.
    Optimized version that focuses on rendering, not data processing.
    """
    import pandas as pd
    import plotly.graph_objects as go
    import plotly.io as pio
    from plotly import colors
    from itertools import cycle
    from datetime import datetime

    # --- Constants (re-defined for the separate process) ---
    import Systems.Functions.json_database as db

    # --- Plotly Setup (re-defined for the separate process) ---
    pio.templates.default = "reaper_dark"
    
    # Fast data prep - assume data is already optimized
    if not isinstance(price_data, pd.DataFrame):
        df = _prepare_dataframe(price_data)
    else:
        df = price_data
    df = df.set_index('date')

    fig = go.Figure()
    color_cycle = cycle(colors.qualitative.Plotly)
    
    # Efficient plotting - data should already be optimized
    if single_resource:
        groups = [(df['resource'].iloc[0], df)] if not df.empty else []
    else:
        fig.update_layout(legend_title_text='Toggle Resources')
        groups = df.groupby('resource')

    for resource_name, res_df in groups:
        resource_name_upper = resource_name.upper()
        color = RESOURCE_COLORS.get(resource_name_upper, next(color_cycle))

        if len(res_df) > 1:
            fig.add_trace(go.Scatter(
                x=res_df.index, y=res_df['price'], mode='lines', 
                name=resource_name_upper.title(), line=dict(color=color, width=2),
                connectgaps=False
            ))
    
    fig.update_layout(
        title=title, xaxis_title='Date', yaxis_title='Price (PPU)', 
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), 
        height=height, width=width, uirevision='true', hovermode='x unified'
    )

    if start_ts and end_ts:
        fig.update_xaxes(range=[datetime.fromtimestamp(start_ts), datetime.fromtimestamp(end_ts)])
    
    # Use faster image generation settings
    return pio.to_image(fig, format='png', scale=scale, engine='kaleido')


# --- Constants ---
RESOURCE_COLORS = {
    "FOOD": "#2ecc71", "COAL": "#34495e", "OIL": "#f39c12", "URANIUM": "#27ae60",
    "LEAD": "#e74c3c", "IRON": "#8e44ad", "BAUXITE": "#e67e22", "GASOLINE": "#f1c40f",
    "MUNITIONS": "#c0392b", "STEEL": "#9b59b6", "ALUMINUM": "#d35400", "CREDIT": "#3498db"
}
RESOURCES = [
    "FOOD", "COAL", "OIL", "URANIUM", "LEAD", "IRON", "BAUXITE",
    "GASOLINE", "MUNITIONS", "STEEL", "ALUMINUM", "CREDIT"
]
RAW_RESOURCES = {"COAL": "blue", "OIL": "goldenrod", "LEAD": "red", "URANIUM": "green", "IRON": "purple", "BAUXITE": "orange"}
MAN_RESOURCES = {"GASOLINE": "goldenrod", "MUNITIONS": "red", "STEEL": "purple", "ALUMINUM": "orange"}
FOOD_RESOURCES = {"FOOD": "green"}
CREDIT_RESOURCES = {"CREDIT": "blue"}

# --- Plotly Setup ---
pio.templates["reaper_dark"] = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor='#2f3136',
        plot_bgcolor='#2f3136',
        font=dict(color='#ffffff'),
        title_font=dict(size=24, color='#ffffff'),
        xaxis=dict(gridcolor='#44474c', linecolor='#44474c'),
        yaxis=dict(gridcolor='#44474c', linecolor='#44474c'),
        legend=dict(bgcolor='#2f3136', bordercolor='#44474c')
    )
)
pio.templates.default = "reaper_dark"


# --- UI Elements ---
class DateRangeModal(ui.Modal, title='Select Date Range'):
    start_date_input = ui.TextInput(label='Start Date (YYYY-MM-DD)', placeholder='e.g., 2023-01-01', required=True)
    end_date_input = ui.TextInput(label='End Date (YYYY-MM-DD)', placeholder='e.g., 2023-12-31', required=True)

    def __init__(self, cog_instance: 'ResourceStocks'):
        super().__init__()
        self.cog = cog_instance

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            start_date_str = self.start_date_input.value
            end_date_str = self.end_date_input.value
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)

            if start_date >= end_date:
                await interaction.followup.send("Start date must be before the end date.", ephemeral=True)
                return

            start_ts = int(start_date.timestamp())
            end_ts = int(end_date.timestamp())

            # Get raw data from database
            raw_data = await db.get_prices_for_range(start_ts, end_ts)
            if not raw_data:
                await interaction.followup.send("No data found for the selected date range.", ephemeral=True)
                return
            
            # Convert to DataFrame for graphing
            df = _prepare_dataframe(raw_data)
            
            # Optimize data for graphing (custom range gets higher limit)
            prices_data = self.cog._optimize_price_data(df, max_points=1200)
            
            embed = discord.Embed(title="Historical Market Data", color=discord.Color.blue())
            graph_file = await self.cog._create_graph(prices_data, f"Market History: {start_date_str} to {end_date_str}")
            
            if graph_file:
                embed.set_image(url=f"attachment://{graph_file.filename}")
                await interaction.followup.send(embed=embed, file=graph_file, ephemeral=True)
            else:
                footer_text = self.cog._get_graph_failure_reason()
                embed.description = "Could not generate graph."
                embed.set_footer(text=footer_text)
                await interaction.followup.send(embed=embed, ephemeral=True)

        except ValueError:
            await interaction.followup.send("Invalid date format. Please use YYYY-MM-DD.", ephemeral=True)
        except Exception as e:
            self.cog.logger.error(f"Error in DateRangeModal: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.followup.send("An error occurred while processing your request.", ephemeral=True)
            else:
                # If interaction is already done, try to send a new message
                try:
                    await interaction.channel.send("An error occurred while processing your date range request. Please check the logs.")
                except:
                    pass

class StocksView(ui.View):
    def __init__(self, cog_instance: 'ResourceStocks'):
        super().__init__(timeout=None)
        self.cog = cog_instance

    @ui.button(label="Refresh", style=discord.ButtonStyle.primary, custom_id="stocks:refresh", emoji="🔄")
    async def refresh_button(self, interaction: discord.Interaction, button: ui.Button):
        self.cog.logger.info(f"Manual refresh triggered by {interaction.user} in guild {interaction.guild_id}")
        await interaction.response.defer(thinking=True)

        refreshed = await self.cog.update_market_data()
        if not refreshed:
            await interaction.followup.send("Failed to fetch new data from the API.", ephemeral=True)
            return

        self.cog.hourly_update.restart()
        self.cog.logger.info(f"Hourly update task restarted. Next run in 1 hour.")
        
        timestamp = int(time.time())
        latest_prices = await db.get_latest_prices()
        comparison_prices = await db.get_comparison_prices(hours_ago=2)
        raw_data = await db.get_historical_prices(days=30, min_entries=24)
        rolling_data = self._optimize_price_data(_prepare_dataframe(raw_data), max_points=600)

        embed = self.cog._build_market_embed(latest_prices, comparison_prices, timestamp)
        graph_file = await self.cog._create_graph(rolling_data, "30-Day Market Trend")

        if rolling_data.empty:
            embed.set_footer(text="📈 Not enough data for a 30-day trend graph yet.")
        elif not graph_file:
            embed.set_footer(text=self.cog._get_graph_failure_reason())
        
        attachments = []
        if graph_file:
            embed.set_image(url=f"attachment://{graph_file.filename}")
            attachments.append(graph_file)

        # Delete the old message and send a new one
        try:
            await interaction.message.delete()
            self.cog.logger.info(f"Deleted old refresh message in guild {interaction.guild_id}")
        except (discord.NotFound, discord.Forbidden):
            self.cog.logger.warning(f"Could not delete old refresh message in guild {interaction.guild_id}")
        
        # Send new message with the updated embed
        new_message = await interaction.channel.send(embed=embed, files=attachments)
        
        # Update the database with the new message ID (this is the main live message)
        await db.add_live_message(interaction.guild_id, interaction.channel_id, new_message.id)
        
        await interaction.followup.send("Market data refreshed!", ephemeral=True)

async def resource_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=resource, value=resource)
        for resource in RESOURCES if current.lower() in resource.lower()
    ][:25]

class ResourceStocks(commands.Cog):
    def __init__(self, bot, query_instance, calc_instance):
        self.bot = bot
        self.logger = logging.getLogger("ResourceStocks")
        self.query = query_instance
        self.calc = calc_instance
        self.kaleido_installed = False
        self.graph_cache: Dict[str, bytes] = {}
        self.bot.add_view(StocksView(self)) # Register the persistent view
        super().__init__()

    def _get_cache_key(self, data: List[Tuple[int, str, float]], title: str, with_indicators: bool = True) -> str:
        """Creates a unique cache key from the data and title."""
        # Use the first and last timestamp, and the hash of all data points
        if not data:
            return f"{title}-{with_indicators}"
        
        # A simple but effective way to represent the data's state
        return f"{title}-{data[0][0]}-{data[-1][0]}-{len(data)}-{hash(tuple(data))}-{with_indicators}"

    # --- Setup & Teardown ---
    async def cog_load(self):
        self.logger.info("Loading ResourceStocks Cog...")
        self._check_kaleido()
        if not hasattr(self.bot, 'process_executor'):
            from concurrent.futures import ProcessPoolExecutor
            # Using a process pool to run blocking image generation off the main thread
            self.bot.process_executor = ProcessPoolExecutor(max_workers=2)
        await db.setup_json_database()
        self.hourly_update.start()
        self.weekly_cleanup.start()
        self.logger.info("ResourceStocks Cog loaded and update tasks started.")

    def cog_unload(self):
        self.hourly_update.cancel()
        self.weekly_cleanup.cancel()
        if hasattr(self.bot, 'process_executor'):
            self.bot.process_executor.shutdown(wait=True)
            del self.bot.process_executor
        self.logger.info("ResourceStocks Cog unloaded.")

    def _check_kaleido(self):
        try:
            import kaleido
            self.kaleido_installed = True
            self.logger.info("Kaleido package found. Graph image generation is enabled.")
        except ImportError:
            self.logger.warning("Kaleido package not found. Image generation will be disabled. Run `pip install kaleido`.")
            self.kaleido_installed = False

    def _get_graph_failure_reason(self) -> str:
        """Returns a user-friendly string explaining why graph generation might have failed."""
        if not self.kaleido_installed:
            return "⚠️ Graph generation failed. The `kaleido` package is missing. Ask an admin to install it."
        return "📈 Graph could not be generated. Check logs for more details."


    def _optimize_price_data(self, price_data: pd.DataFrame, max_points: int = 1000) -> pd.DataFrame:
        """Optimizes price data by reducing points using the LTTB algorithm."""
        if price_data.empty or len(price_data) <= max_points:
            return price_data

        from collections import defaultdict
        import lttb
        import numpy as np

        # Group by resource
        resource_groups = price_data.groupby('resource')
        
        optimized_data = []
        num_resources = len(resource_groups)
        points_per_resource = max(2, max_points // num_resources) if num_resources > 0 else max_points

        for resource_name, res_df in resource_groups:
            if len(res_df) <= points_per_resource:
                optimized_data.append(res_df)
            else:
                # LTTB requires a 2D numpy array of [x, y]
                np_data = res_df[['timestamp', 'price']].values.astype(np.float64)
                downsampled_data = lttb.downsample(np_data, n_out=points_per_resource)
                
                # Create new DataFrame for downsampled data
                downsampled_df = pd.DataFrame({
                    'timestamp': downsampled_data[:, 0].astype(int),
                    'resource': resource_name,
                    'price': downsampled_data[:, 1]
                })
                optimized_data.append(downsampled_df)
        
        # Concatenate all optimized data
        if optimized_data:
            result_df = pd.concat(optimized_data, ignore_index=True)
            result_df['date'] = pd.to_datetime(result_df['timestamp'], unit='s')
            result_df = result_df.sort_values('date').set_index('date')
            self.logger.info(f"Optimized price data from {len(price_data)} to {len(result_df)} points using LTTB.")
            return result_df
        
        return price_data

    # --- Background Tasks & Helpers ---
    async def update_market_data(self) -> Optional[Dict[str, float]]:
        """Fetches new market data from API, saves it, and returns the new prices."""
        self.logger.info("Fetching fresh market data from API.")
        latest_prices = await self._fetch_and_parse_prices()
        if latest_prices:
            self.graph_cache.clear() # Invalidate cache
            self.logger.info("Graph cache cleared due to new market data.")
            timestamp = int(time.time())
            await db.add_prices(timestamp, latest_prices)
            await db.set_global_config("last_stock_update", str(timestamp))
            self.logger.info("Successfully updated market data.")
            return latest_prices
        
        self.logger.warning("Failed to fetch or parse prices from API during update.")
        return None

    def _get_next_game_turn_time(self) -> datetime:
        """Calculate the next game turn time (every 2 hours, 15 minutes after the hour)."""
        now = datetime.utcnow()
        current_hour = now.hour
        current_minute = now.minute

        if current_hour % 2 == 0:
            if current_minute < 15:
                # Turn is this hour
                next_hour = current_hour
            else:
                # Turn is in 2 hours
                next_hour = current_hour + 2
        else:
            # Turn is in the next hour (which will be even)
            next_hour = current_hour + 1

        # Calculate the next turn datetime, handling day changes
        if next_hour >= 24:
            next_day = now + timedelta(days=1)
            return next_day.replace(hour=next_hour % 24, minute=15, second=0, microsecond=0)
        else:
            return now.replace(hour=next_hour, minute=15, second=0, microsecond=0)

    @tasks.loop(hours=2)
    async def hourly_update(self):
        self.logger.info("Running bi-hourly market update check...")
        
        # Wait until 15 minutes past the hour (game turn time)
        next_turn = self._get_next_game_turn_time()
        wait_seconds = (next_turn - datetime.utcnow()).total_seconds()
        
        if wait_seconds > 0:
            self.logger.info(f"Waiting {wait_seconds:.0f} seconds until next game turn at {next_turn.strftime('%H:%M')} UTC")
            await asyncio.sleep(wait_seconds)
        
        self.logger.info("Proceeding with market data refresh after game turn.")
        
        # Get prices from before the update for comparison
        comparison_prices = await db.get_latest_prices()

        # Fetch and save new prices
        new_prices = await self.update_market_data()
        if not new_prices:
            self.logger.warning("Update_market_data failed, will retry next game turn.")
            return

        live_messages = await db.get_all_live_messages()
        if not live_messages:
            self.logger.info("No live message boards to update.")
            return

        self.logger.info(f"Found {len(live_messages)} live message boards to update.")
        
        timestamp = int(float(await db.get_global_config("last_stock_update")))
        raw_data = await db.get_historical_prices(days=30, min_entries=24)
        rolling_data = self._optimize_price_data(_prepare_dataframe(raw_data), max_points=600)
        
        # Build embed with the old and new prices
        base_embed = self._build_market_embed(new_prices, comparison_prices, timestamp)
        graph_file_obj = await self._create_graph(rolling_data, "30-Day Market Trend")
        
        graph_bytes = None
        if graph_file_obj:
            graph_bytes = graph_file_obj.fp.read()
            graph_file_obj.fp.seek(0) # Reset pointer for reuse

        for guild_id, channel_id, message_id in live_messages:
            embed = base_embed.copy()
            attachments = []
            if rolling_data.empty:
                embed.set_footer(text="📈 Not enough data for a 30-day trend graph yet.")
            elif not graph_bytes:
                embed.set_footer(text=self._get_graph_failure_reason())
            
            if graph_bytes:
                embed.set_image(url="attachment://market_graph.png")
                # Use a fresh BytesIO object for each message
                attachments.append(discord.File(io.BytesIO(graph_bytes), filename="market_graph.png"))

            try:
                channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                if not channel:
                    self.logger.warning(f"Could not find channel {channel_id} for guild {guild_id}.")
                    await db.remove_live_message(guild_id)
                    continue
                
                # Fetch the old message to delete it
                try:
                    old_message = await channel.fetch_message(message_id)
                    await old_message.delete()
                    self.logger.info(f"Deleted old live message in guild {guild_id}")
                except (discord.NotFound, discord.Forbidden):
                    self.logger.warning(f"Could not delete old message in guild {guild_id}, but will still send new one.")
                
                # Send new message with the updated embed
                new_message = await channel.send(embed=embed, files=attachments)
                
                # Update the database with the new message ID
                await db.add_live_message(guild_id, channel_id, new_message.id)
                self.logger.info(f"Successfully sent new live message in guild {guild_id}")
                
            except discord.NotFound:
                self.logger.warning(f"Live message/channel/guild not found. Removing from DB for guild {guild_id}.")
                await db.remove_live_message(guild_id)
            except discord.Forbidden:
                self.logger.warning(f"Missing permissions to send message in guild {guild_id}. Removing.")
                await db.remove_live_message(guild_id)
            except Exception as e:
                self.logger.error(f"Failed to update live message in guild {guild_id}: {e}", exc_info=True)

    @hourly_update.before_loop
    async def before_hourly_update(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=24)
    async def weekly_cleanup(self):
        """Clean up old weekly files to prevent excessive storage usage."""
        self.logger.info("Running weekly cleanup of old data files...")
        try:
            await db.cleanup_old_weekly_files(weeks_to_keep=12)  # Keep 12 weeks of data
            self.logger.info("Weekly cleanup completed.")
        except Exception as e:
            self.logger.error(f"Error during weekly cleanup: {e}")

    @weekly_cleanup.before_loop
    async def before_weekly_cleanup(self):
        await self.bot.wait_until_ready()
        # Wait until 2 AM UTC to run cleanup
        now = datetime.utcnow()
        next_cleanup = now.replace(hour=2, minute=0, second=0, microsecond=0)
        if next_cleanup <= now:
            next_cleanup += timedelta(days=1)
        
        wait_seconds = (next_cleanup - now).total_seconds()
        if wait_seconds > 0:
            self.logger.info(f"Waiting {wait_seconds:.0f} seconds until next cleanup at 02:00 UTC")
            await asyncio.sleep(wait_seconds)

    async def _create_graph(
        self,
        price_data: pd.DataFrame,
        title: str,
        single_resource: bool = False,
        with_indicators: bool = True,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None
    ) -> Optional[discord.File]:
        """Creates a historical price graph and returns it as a discord.File."""
        start_time = time.time()
        self.logger.info(f"Starting graph creation process for '{title}'...")

        if price_data.empty:
            self.logger.warning("Graph creation skipped: No data available.")
            return None
        
        if isinstance(price_data, pd.DataFrame):
            resource_counts = price_data.groupby('resource').size()
            if not any(resource_counts >= 2):
                self.logger.warning("Graph creation skipped: No resource has enough data points (>= 2).")
                return None

        try:
            # Ensure the DataFrame has the correct columns and types
            price_data['timestamp'] = pd.to_datetime(price_data['timestamp'], unit='s')
            price_data['price'] = pd.to_numeric(price_data['price'])
            price_data = price_data.sort_values('timestamp')

            # Prepare data for the render function
            if isinstance(price_data, pd.DataFrame):
                # Convert DataFrame to list format for the process function
                data_list = []
                for _, row in price_data.iterrows():
                    data_list.append([
                        int(row['timestamp'].timestamp()),
                        row['resource'],
                        float(row['price'])
                    ])
                price_data = data_list

            # Use Plotly render function
            img_bytes = await asyncio.get_event_loop().run_in_executor(
                self.bot.process_executor,
                _render_graph_process,
                price_data,
                title,
                single_resource,
                with_indicators,
                1.0,  # scale
                1200,  # width
                800,    # height
                start_ts,
                end_ts
            )

            if img_bytes is None:
                self.logger.error(f"Render function returned None for graph '{title}'")
                return None

            buffer = io.BytesIO(img_bytes)
            buffer.seek(0)
            
            self.logger.info(f"Graph '{title}' created successfully in {time.time() - start_time:.2f}s.")
            return discord.File(buffer, filename=f"{title.replace(' ', '_').lower()}_graph.png")

        except Exception as e:
            self.logger.error(f"Failed to create graph '{title}': {e}", exc_info=True)
            return None

    async def _fetch_and_parse_prices(self) -> Optional[Dict[str, float]]:
        """Fetches and validates prices from the API."""
        try:
            prices_list = await self.query.get_trade_resource_values()
            if not prices_list or not isinstance(prices_list, list):
                self.logger.warning("API returned no or invalid data for trade prices.")
                return None

            current_prices = {}
            for item in prices_list:
                resource_name = item.get('resource')
                if not resource_name or resource_name.upper() not in RESOURCES:
                    continue
                
                # Safely extract price, defaulting to None if not found
                price_str = (item.get('best_sell_offer') or {}).get('price')
                
                if price_str is not None:
                    try:
                        current_prices[resource_name.upper()] = float(price_str)
                    except (ValueError, TypeError):
                        self.logger.warning(f"Invalid price format for {resource_name}: {price_str}. Skipping.")
                else:
                    self.logger.warning(f"Missing price for {resource_name}. Skipping.")

            # Allow partial data and log warning instead of failing completely
            if len(current_prices) != len(RESOURCES):
                self.logger.warning(f"API data is incomplete. Fetched {len(current_prices)}/{len(RESOURCES)} prices. Continuing with available data.")

            return current_prices

        except Exception as e:
            self.logger.error(f"Failed to fetch/parse prices from API: {e}", exc_info=True)
            return None
    
    # --- Embed Builders ---
    def _build_market_embed(self, current_prices: Dict[str, float], prev_prices: Dict[str, float], timestamp: int) -> discord.Embed:
        description = f"Last Updated: <t:{timestamp}:R>"
        embed = discord.Embed(title=f"{emoji_mod.mention('data') or '📈'} PnW Market Prices", description=description, color=discord.Color.gold())
        if not current_prices:
            embed.description += "\n\nMarket data not yet available. Please try again shortly."
            return embed

        # Group resources into columns for better display
        resource_groups = [
            ["FOOD", "COAL", "OIL", "URANIUM"],      # Column 1
            ["LEAD", "IRON", "BAUXITE", "GASOLINE"],  # Column 2  
            ["MUNITIONS", "STEEL", "ALUMINUM", "CREDIT"]  # Column 3
        ]
        
        for col_idx, group in enumerate(resource_groups):
            for res in group:
                price = current_prices.get(res, 0.0)
                prev = prev_prices.get(res, 0.0)
                
                # Check if price exists in current data
                if res in current_prices:
                    # Strip cents by converting to int
                    price_int = int(price)
                    price_str = f"${price_int:,}"
                    
                    if prev > 0 and prev != price:
                        diff = price - prev
                        pct = (diff / prev) * 100 if prev != 0 else 0
                        
                        # Determine price change emoji - FIXED: Use correct emoji names
                        if diff > 0:
                            price_emoji = emoji_mod.mention('dollarup') or '📈'
                        elif diff < 0:
                            price_emoji = emoji_mod.mention('dollardown') or '📉'
                        else:
                            price_emoji = emoji_mod.mention('dollarsame') or '➖'
                        
                        # Determine percentage change emoji - FIXED: Use correct emoji names
                        if pct > 0:
                            pct_emoji = emoji_mod.mention('perup') or '📈'
                        elif pct < 0:
                            pct_emoji = emoji_mod.mention('perdown') or '📉'
                        else:
                            pct_emoji = emoji_mod.mention('persame') or '➖'
                        
                        # Format diff as integer (strip cents)
                        diff_int = int(diff)
                        change_str = f"{price_emoji} ${diff_int:+d}"
                        pct_str = f"{pct_emoji} {pct:+.1f}%"
                        value = f"{price_str} ({change_str}) {pct_str}"
                    else:
                        value = f"🆕 ${price_int:,}"
                else:
                    value = "❌ No Data"

                emoji_key = emoji_mod.RESOURCE_EMOJI_NAMES.get(res)
                resource_emoji = emoji_mod.mention(emoji_key) if emoji_key else ''
                
                # Use inline=True for columns, but add blank fields to create proper spacing
                if col_idx < len(resource_groups) - 1:  # Not the last column
                    embed.add_field(name=f"{resource_emoji} {res.title()}", value=value, inline=True)
                else:  # Last column - add extra spacing
                    embed.add_field(name=f"{resource_emoji} {res.title()}", value=value, inline=True)
            
            # Add spacing between columns (except after last column)
            if col_idx < len(resource_groups) - 1:
                embed.add_field(name="\u200b", value="\u200b", inline=True)  # Zero-width space for spacing
            
        return embed

    @app_commands.command(name="stocks", description="Display P&W market prices and trends.")
    @app_commands.describe(graph_type="Choose the type of graph to display")
    @app_commands.choices(graph_type=[
        app_commands.Choice(name="All Resources", value="all"),
        app_commands.Choice(name="Raw Resources", value="raw"),
        app_commands.Choice(name="Manufactured Resources", value="man"),
        app_commands.Choice(name="Food", value="food"),
        app_commands.Choice(name="Credit", value="credit"),
    ])
    async def stocks(self, interaction: discord.Interaction, graph_type: str = 'all'):
        """Main command to display market prices and graphs."""
        await interaction.response.defer()

        try:
            # Fetch latest prices
            latest_prices = await self._fetch_and_parse_prices()
            if not latest_prices:
                await interaction.followup.send("Could not fetch latest market prices. Please try again later.", ephemeral=True)
                return

            # Get historical data for comparison and graphing
            raw_data = await db.get_historical_prices(days=30, min_entries=24)
            price_history = self._optimize_price_data(_prepare_dataframe(raw_data), max_points=600)
            comparison_prices = await get_comparison_prices(hours_ago=2)
            timestamp = int(datetime.now().timestamp())

            # Build the embed
            embed = self._build_market_embed(latest_prices, comparison_prices, timestamp)

            # Filter data for the graph
            if graph_type == 'raw':
                graph_data = price_history[price_history['resource'].isin(RAW_RESOURCES)]
            elif graph_type == 'man':
                graph_data = price_history[price_history['resource'].isin(MAN_RESOURCES)]
            elif graph_type == 'food':
                graph_data = price_history[price_history['resource'].isin(FOOD_RESOURCES)]
            elif graph_type == 'credit':
                graph_data = price_history[price_history['resource'].isin(CREDIT_RESOURCES)]
            else:
                graph_data = price_history

            # Create and attach graph
            graph_file = await self._create_graph(graph_data, f"{graph_type.title()} Resources Price Trend")
            if graph_file:
                embed.set_image(url=f"attachment://{graph_file.filename}")
                await interaction.followup.send(embed=embed, file=graph_file)
            else:
                embed.set_footer(text="📈 Not enough data for a 30-day trend graph yet.")
                await interaction.followup.send(embed=embed)

        except Exception as e:
            self.logger.error(f"Error in stocks command: {e}", exc_info=True)
            await interaction.followup.send("An error occurred while fetching stock data. Please try again later.", ephemeral=True)

    # --- App Commands ---
    stocks_group = app_commands.Group(name="livestocks", description="Manages the live market data embed.", default_permissions=discord.Permissions(manage_guild=True))

    @stocks_group.command(name="create", description="Create the live stocks embed in this channel.")
    async def live_stocks_create(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            if await db.get_live_message(interaction.guild_id):
                return await interaction.followup.send("A live stocks embed already exists in this server. Use `/livestocks remove` first.", ephemeral=True)

            latest_prices = await db.get_latest_prices()
            if not latest_prices:
                if not await self.update_market_data():
                    return await interaction.followup.send("Could not fetch initial market data from the API.", ephemeral=True)
                latest_prices = await db.get_latest_prices()

            timestamp = int(float(await db.get_global_config("last_stock_update") or time.time()))
            comparison_prices = await db.get_comparison_prices(hours_ago=2)
            raw_data = await db.get_historical_prices(days=30, min_entries=24)
            rolling_data = self._optimize_price_data(_prepare_dataframe(raw_data), max_points=600)

            embed = self._build_market_embed(latest_prices, comparison_prices, timestamp)
            graph_file = await self._create_graph(rolling_data, "30-Day Market Trend")

            if rolling_data.empty:
                embed.set_footer(text="📈 Not enough data for a 30-day trend graph yet.")
            elif not graph_file:
                embed.set_footer(text=self._get_graph_failure_reason())

            if graph_file:
                embed.set_image(url=f"attachment://{graph_file.filename}")

            # Only pass graph_file if it exists, otherwise pass None
            file_to_send = graph_file if graph_file else None
            live_message = await interaction.channel.send(embed=embed, file=file_to_send, view=StocksView(self))
            await db.add_live_message(interaction.guild_id, live_message.channel.id, live_message.id)
            
            await interaction.followup.send(f"Live stocks embed created in {interaction.channel.mention}.", ephemeral=True)

        except Exception as e:
            self.logger.error(f"Error in /livestocks create command: {e}", exc_info=True)
            if not interaction.response.is_done():
                await interaction.followup.send("An error occurred. Please check the logs.", ephemeral=True)
            else:
                # If interaction is already done, try to send a new message
                try:
                    await interaction.channel.send("An error occurred while creating the live stocks embed. Please check the logs.")
                except:
                    pass

    @stocks_group.command(name="remove", description="Removes the live stocks embed from this server.")
    async def live_stocks_remove(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        live_message_data = await db.get_live_message(interaction.guild_id)
        if not live_message_data:
            return await interaction.followup.send("No live stocks embed found for this server.", ephemeral=True)
            
        _, channel_id, message_id = live_message_data
        
        await db.remove_live_message(interaction.guild_id)
        await interaction.followup.send("Live stocks embed has been removed. Deleting original message...")

        try:
            channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
            message = await channel.fetch_message(message_id)
            await message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass
        except Exception as e:
            self.logger.error(f"Error deleting live stocks message in guild {interaction.guild_id}: {e}", exc_info=True)
            # Don't fail the command if we can't delete the message, since we already removed it from DB
    
    @app_commands.command(name="history", description="Show historical market data for a custom date range")
    async def history(self, interaction: discord.Interaction):
        min_ts, max_ts = await db.get_all_time_price_range()
        if not min_ts:
            await interaction.response.send_message("No historical data available yet.", ephemeral=True)
            return
        await interaction.response.send_modal(DateRangeModal(self))

async def setup(bot):
    if not (alliance_cog := bot.get_cog('AllianceManager')):
        return logging.error("Failed to add ResourceStocks cog: AllianceManager cog not found.")
    if not (query_instance := getattr(alliance_cog, 'query_system', None)) or not (calc_instance := getattr(alliance_cog, 'calc_system', None)):
        return logging.error("Failed to add ResourceStocks: Could not find query_system or calc_system in AllianceManager.")
    await bot.add_cog(ResourceStocks(bot, query_instance, calc_instance))
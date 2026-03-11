import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import time
from datetime import datetime
import logging
from typing import Dict, List, Any, Optional
import io
import asyncio
import functools

try:
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

import Systems.Functions.emoji as emoji_mod

# Path to the resources.json file
# Support for containerized environments (CasaOS/Docker) via DATA_DIR
DATA_DIR = os.getenv('DATA_DIR')
if DATA_DIR:
    if not os.path.exists(DATA_DIR):
        try:
            os.makedirs(DATA_DIR)
        except Exception as e:
            logging.getLogger("ResourceStocks").error(f"Failed to create DATA_DIR: {e}")
    RESOURCES_FILE = os.path.join(DATA_DIR, 'resources.json')
else:
    RESOURCES_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Util', 'resources.json'))

class ResourceStocks(commands.GroupCog, name="resource"):
    def __init__(self, bot, query_instance, calc_instance):
        self.bot = bot
        self.logger = logging.getLogger("ResourceStocks")
        self.query = query_instance
        self.calc = calc_instance
        self.data_lock = asyncio.Lock()
        
        # Ensure Agg backend for headless environments
        if MATPLOTLIB_AVAILABLE:
            try:
                plt.switch_backend('Agg')
            except Exception as e:
                self.logger.warning(f"Failed to switch matplotlib backend to Agg: {e}")
                
        super().__init__()

    def cog_unload(self):
        self.stock_updater.cancel()

    def _load_history_sync(self) -> Dict[str, Any]:
        """Synchronous file load operation."""
        if not os.path.exists(RESOURCES_FILE):
            return {"config": {}, "history": []}
        try:
            with open(RESOURCES_FILE, 'r') as f:
                data = json.load(f)
                if "config" not in data:
                    data["config"] = {}
                if "history" not in data:
                    data["history"] = []
                return data
        except Exception as e:
            self.logger.error(f"Failed to load resources.json: {e}")
            return {"config": {}, "history": []}

    async def _load_history(self) -> Dict[str, Any]:
        """Asynchronous wrapper for loading history."""
        return await asyncio.to_thread(self._load_history_sync)

    def _save_history_sync(self, data: Dict[str, Any]):
        """Synchronous file save operation."""
        try:
            with open(RESOURCES_FILE, 'w') as f:
                json.dump(data, f, separators=(',', ':')) # Compact JSON
        except Exception as e:
            self.logger.error(f"Failed to save resources.json: {e}")

    async def _save_history(self, data: Dict[str, Any]):
        """Asynchronous wrapper for saving history."""
        await asyncio.to_thread(self._save_history_sync, data)

    def _render_rolling_graph_sync(self, history: List[Dict[str, Any]]) -> Optional[io.BytesIO]:
        """Synchronous graph rendering operation."""
        if not MATPLOTLIB_AVAILABLE:
            return None
        
        # Limit to last 28 entries (7 days * 4 updates/day)
        data_points = history[-28:]
        if not data_points:
            return None
        
        # Define Categories and Colors
        raw_resources = {
            "COAL": "tab:blue",
            "OIL": "gold",
            "LEAD": "tab:red",
            "URANIUM": "tab:green",
            "IRON": "tab:purple",
            "BAUXITE": "tab:orange"
        }
        
        manufactured_resources = {
            "CREDIT": "tab:blue",
            "GASOLINE": "gold",
            "MUNITIONS": "tab:red",
            "FOOD": "tab:green",
            "STEEL": "tab:purple",
            "ALUMINUM": "tab:orange"
        }

        # Prepare Data
        def get_series(resource_list, data):
            series = {}
            for res in resource_list:
                values = []
                for entry in data:
                    val = entry.get("prices", {}).get(res, 0.0)
                    values.append(val)
                
                if not values:
                    series[res] = []
                    continue
                
                start_val = values[0]
                if start_val == 0:
                    pct_values = [0.0 for _ in values]
                else:
                    pct_values = [((v - start_val) / start_val) * 100.0 for v in values]
                series[res] = pct_values
            return series

        raw_series = get_series(raw_resources.keys(), data_points)
        man_series = get_series(manufactured_resources.keys(), data_points)
        
        # Setup Matplotlib
        try:
            plt.style.use('dark_background')
            # Create a new figure explicitly to avoid thread conflicts
            fig = plt.figure(figsize=(12, 10))
            ax1 = fig.add_subplot(211)
            ax2 = fig.add_subplot(212)
            
            # Helper to plot on axis
            def plot_category(ax, series_data, color_map, title):
                for res, values in series_data.items():
                    if not values: continue
                    color = color_map.get(res, "white")
                    line, = ax.plot(values, label=res.title(), color=color, linewidth=2)
                    # Dot at end
                    if values:
                        ax.scatter(len(values)-1, values[-1], s=40, color=color, zorder=5)
                
                ax.set_title(title, fontsize=14, fontweight='bold', pad=10)
                ax.set_ylabel("% Change", fontsize=10)
                ax.grid(True, alpha=0.2)
                ax.legend(loc='upper left', bbox_to_anchor=(1.01, 1), borderaxespad=0.)
                
                all_vals = [v for vals in series_data.values() for v in vals]
                if all_vals:
                    max_val = max(all_vals)
                    min_val = min(all_vals)
                    limit = max(100, abs(max_val), abs(min_val))
                    limit = limit * 1.1
                    ax.set_ylim(-limit, limit)
                    
                    if limit <= 120:
                        ticks = [-100, -75, -50, -25, 0, 25, 50, 75, 100]
                        ax.set_yticks(ticks)
                
                ax.axhline(0, color='white', alpha=0.5, linestyle='--')
                ax.set_xlim(0, 27)
                
            plot_category(ax1, raw_series, raw_resources, "Raw Resources (7-Day Trend)")
            plot_category(ax2, man_series, manufactured_resources, "Manufactured Resources (7-Day Trend)")
            
            ax2.set_xlabel("Time (6h intervals)", fontsize=10)
            
            fig.tight_layout()
            
            # Save
            buf = io.BytesIO()
            fig.savefig(buf, format='png', dpi=100)
            buf.seek(0)
            plt.close(fig) # Explicitly close the figure
            return buf
            
        except Exception as e:
            self.logger.error(f"Error rendering graph: {e}")
            return None

    async def render_rolling_graph(self, history: List[Dict[str, Any]]) -> Optional[discord.File]:
        """Asynchronous wrapper for graph rendering."""
        if not MATPLOTLIB_AVAILABLE:
            return None
            
        buf = await asyncio.to_thread(self._render_rolling_graph_sync, history)
        if buf:
            return discord.File(buf, filename="market_live.png")
        return None

    @tasks.loop(hours=6)
    async def stock_updater(self):
        self.logger.info("Updating resource stocks...")
        try:
            # Fetch current prices
            prices_list = await self.query.get_trade_resource_values()
            if not prices_list:
                self.logger.warning("No trade values returned.")
                return

            # Convert to dict for storage: {"FOOD": 123.45, ...}
            current_prices = {item['resource']: item['average_price'] for item in prices_list}
            self.bot.market_prices = current_prices
            
            # Create snapshot
            snapshot = {
                "ts": int(time.time()),
                "prices": current_prices
            }

            # Update History with Lock
            async with self.data_lock:
                data = await self._load_history()
                history = data.get("history", [])
                history.append(snapshot)
                data["history"] = history # Update ref
                
                # Save Data
                await self._save_history(data)

            # Generate Graph (Compute heavy, done outside lock but history is local copy)
            graph_file = await self.render_rolling_graph(history)
            
            # Generate Embed
            embed = self._build_market_embed(current_prices, history)
            
            if graph_file:
                embed.set_image(url="attachment://market_live.png")
            
            # Update Persistent Message
            config = data.get("config", {})
            channel_id = config.get("channel_id")
            msg_id = config.get("message_id")
            
            if channel_id:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        if msg_id:
                            try:
                                msg = await channel.fetch_message(msg_id)
                                await msg.edit(embed=embed, attachments=[graph_file] if graph_file else [])
                            except discord.NotFound:
                                # Resend
                                msg = await channel.send(embed=embed, file=graph_file)
                                # Update message ID in config
                                async with self.data_lock:
                                    # Reload to ensure no overwrite
                                    data = await self._load_history()
                                    if "config" not in data: data["config"] = {}
                                    data["config"]["message_id"] = msg.id
                                    await self._save_history(data)
                        else:
                            msg = await channel.send(embed=embed, file=graph_file)
                            async with self.data_lock:
                                data = await self._load_history()
                                if "config" not in data: data["config"] = {}
                                data["config"]["message_id"] = msg.id
                                await self._save_history(data)
                    except Exception as e:
                        self.logger.error(f"Failed to update market message: {e}")
                else:
                     self.logger.warning(f"Market channel {channel_id} not found.")

            self.logger.info("Resource stocks updated successfully.")

        except Exception as e:
            self.logger.error(f"Error in stock_updater: {e}")

    def _build_market_embed(self, current_prices: Dict[str, float], history: List[Dict[str, Any]]) -> discord.Embed:
        """Helper to build the market embed"""
        latest_ts = int(time.time())
        if history:
            latest_ts = history[-1].get("ts", latest_ts)
            
        # Determine Color (Global Average Up/Down)
        color = discord.Color.gold() # Default
        if len(history) > 1:
            prev_prices = history[-2].get("prices", {})
            curr_sum = sum(current_prices.values())
            prev_sum = sum(prev_prices.values())
            if curr_sum > prev_sum:
                color = discord.Color.green()
            elif curr_sum < prev_sum:
                color = discord.Color.red()
                
        embed = discord.Embed(
            title=f"{emoji_mod.mention('LevelUp') or '📈'} Live PnW Market Ticker",
            description=f"Last Updated: <t:{latest_ts}:R>\nUpdates every 6 hours.",
            color=color
        )
        
        # Add Ticker Text (Price List)
        # Using the order from emoji.py's RESOURCE_EMOJI_NAMES keys if available
        resource_order = ["FOOD", "COAL", "OIL", "URANIUM", "LEAD", "IRON", "BAUXITE", "GASOLINE", "MUNITIONS", "STEEL", "ALUMINUM", "CREDIT"]
        
        for res in resource_order:
            price = current_prices.get(res, 0)
            prev = 0
            if len(history) > 1:
                prev = history[-2]["prices"].get(res, 0)
            
            price_str = f"${price:,.2f}"
            if prev > 0:
                diff = price - prev
                pct = (diff / prev) * 100
                if diff > 0:
                    change_str = f"{emoji_mod.mention('LevelUp') or '📈'} +{pct:.2f}%"
                elif diff < 0:
                    change_str = f"{emoji_mod.mention('LevelDown') or '📉'} {pct:.2f}%"
                else:
                    change_str = f"{emoji_mod.mention('Neutral') or '➖'} 0.00%"
            else:
                change_str = "🆕 New"

            emoji_key = emoji_mod.RESOURCE_EMOJI_NAMES.get(res)
            emoji_str = emoji_mod.mention(emoji_key) if emoji_key else ""
            
            embed.add_field(name=f"{emoji_str} {res.title()}", value=f"**{price_str}**\n{change_str}", inline=True)
            
        return embed

    @stock_updater.before_loop
    async def before_stock_updater(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="stocks", description="Show current resource values and market trends")
    async def stocks(self, interaction: discord.Interaction, live: bool = False):
        """
        Displays the current resource market.
        :param live: If True, sets this channel as the live dashboard that updates automatically.
        """
        await interaction.response.defer(ephemeral=live)

        # Load history safely
        async with self.data_lock:
            data = await self._load_history()
        
        history = data.get("history", [])

        # Get latest data
        if not history:
            # If no history, try to fetch now
            prices_list = await self.query.get_trade_resource_values()
            if not prices_list:
                await interaction.followup.send("Could not fetch resource data.", ephemeral=True)
                return
            current_prices = {item['resource']: item['average_price'] for item in prices_list}
        else:
            latest_snapshot = history[-1]
            current_prices = latest_snapshot["prices"]
            
        # Build Embed
        embed = self._build_market_embed(current_prices, history)
        
        # Generate Graph (Only if history exists)
        graph_file = await self.render_rolling_graph(history)
        if graph_file:
            embed.set_image(url="attachment://market_live.png")

        if live:
            async with self.data_lock:
                # Reload to be safe
                data = await self._load_history()
                if "config" not in data:
                    data["config"] = {}
                data["config"]["channel_id"] = interaction.channel_id
                # Reset message_id so a new one is sent
                data["config"]["message_id"] = None
                await self._save_history(data)
            
            await interaction.followup.send("✅ Market Dashboard Initialized! The ticker will appear shortly and update every 6 hours.", ephemeral=True)
            
            # Restart the loop to trigger an immediate update
            self.stock_updater.restart()
        else:
            await interaction.followup.send(embed=embed, file=graph_file if graph_file else discord.utils.MISSING)

async def setup(bot):
    alliance_cog = bot.get_cog('AllianceManager')
    if alliance_cog:
        query_instance = getattr(alliance_cog, 'query_system', None)
        calc_instance = getattr(alliance_cog, 'calc_system', None)
        if query_instance and calc_instance:
            await bot.add_cog(ResourceStocks(bot, query_instance, calc_instance))

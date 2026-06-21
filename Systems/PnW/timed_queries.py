import discord
from discord.ext import commands, tasks
import time
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
import logging
from typing import Dict, List, Optional, Any
import asyncio
import Systems.Functions.database_manager as db_manager
from Systems.PnW.EA.rss_alerts import check_price_alerts


RESOURCES = [
    "FOOD", "COAL", "OIL", "URANIUM", "LEAD", "IRON", "BAUXITE",
    "GASOLINE", "MUNITIONS", "STEEL", "ALUMINUM", "CREDIT"
]

class TimedQueries(commands.Cog):
    def __init__(self, bot, query_instance):
        self.bot = bot
        self.logger = logging.getLogger("TimedQueries")
        self.query = query_instance

    async def cog_load(self):
        """Set up the TimedQueries Cog and start the update loop."""
        self.logger.info("Loading TimedQueries Cog...")
        await db_manager.setup_databases()
        self.master_update.start()
        self.logger.info("TimedQueries Cog loaded and update task started.")

    def cog_unload(self):
        self.master_update.cancel()
        self.bot.remove_listener(self.on_ready_timed_queries, 'on_ready')
        self.logger.info("TimedQueries Cog unloaded.")



    @tasks.loop(minutes=15)
    async def master_update(self):
        """Master update task that runs every 15 minutes, fetching all data in a single query."""
        self.logger.info("Running 15-minute master update...")
        timestamp = int(time.time())
        
        try:
            # Fetch all data in a single batch query
            master_data = await self.query.get_master_update_data()

            if not master_data:
                self.logger.error("Master update failed: No data received from the API.")
                return

            # Process and save game data (colors)
            colors_info = master_data.get('colors')
            if colors_info:
                await db_manager.add_game_data("colors", timestamp, colors_info)
                self.logger.info("Successfully saved color data.")

            # Process and save game_info (game_date, city_average, radiation)
            game_info = master_data.get('gameInfo')
            if game_info:
                game_date_str = game_info.get('game_date') or ''
                city_average = float(game_info.get('city_average') or 0.0)
                await db_manager.add_game_info(timestamp, game_date_str, city_average)
                self.logger.info(f"Successfully saved game_info (game_date={game_date_str}, city_average={city_average}).")
                
                # Save radiation data if available
                radiation_info = game_info.get('radiation')
                if radiation_info:
                    await db_manager.add_radiation_data(timestamp, radiation_info)
                    self.logger.info(f"Successfully saved radiation data.")
                else:
                    self.logger.warning("No radiation data found in game_info response.")

            # Process and save resource data (best sell, best buy, and average prices)
            trade_info = master_data.get('tradeInfo')
            if trade_info:
                resource_list = trade_info.get('resources', [])
                if resource_list:
                    resource_data = {}
                    found_resources = []
                    for item in resource_list:
                        if item.get('resource') and item['resource'].upper() in RESOURCES:
                            resource_name = item['resource'].lower()
                            best_sell = float((item.get('best_sell_offer') or {}).get('price', 0))
                            best_buy = float((item.get('best_buy_offer') or {}).get('price', 0))
                            
                            avg_price = (best_buy + best_sell) / 2 if (best_buy > 0 and best_sell > 0) else (best_buy or best_sell)

                            resource_data[resource_name] = {
                                'best_sell': best_sell,
                                'best_buy': best_buy,
                                'avg': avg_price
                            }
                            found_resources.append(resource_name)
                    
                    self.logger.info(f"Fetched resources from API: {found_resources}")
                    
                    if len(resource_data) < len(RESOURCES):
                         missing_resources = [res for res in [r.lower() for r in RESOURCES] if res not in resource_data]
                         self.logger.warning(f"API data is incomplete. Fetched {len(resource_data)}/{len(RESOURCES)} resources. Missing: {missing_resources}")
                    
                    await db_manager.add_resource_data(timestamp, resource_data)
                    self.logger.info("Successfully saved resource price data (best sell, best buy, average).")

                    # Check price alerts using the freshly-fetched data (no extra query needed)
                    await check_price_alerts(self.bot, resource_data)

        except Exception as e:
            self.logger.error(f"Master update failed: {e}", exc_info=True)


    @master_update.before_loop
    async def before_master_update(self):
        """Wait until the bot is ready before the first run."""
        await self.bot.wait_until_ready()
        self.logger.info("Bot is ready, TimedQueries update loop will now begin.")


async def setup(bot):
    if not (alliance_cog := bot.get_cog('AllianceManager')):
        return logging.error("Failed to add TimedQueries cog: AllianceManager cog not found.")
    if not (query_instance := getattr(alliance_cog, 'query_system', None)):
        return logging.error("Failed to add TimedQueries: Could not find query_system in AllianceManager.")
    await bot.add_cog(TimedQueries(bot, query_instance))

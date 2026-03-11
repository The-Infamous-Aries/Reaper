import asyncio
import discord
import logging
import importlib
from discord.ext import commands

from Systems.Functions import emoji as emoji_mod
from Systems.PnW.Util.query import create_query_instance, PNWAPIQuery
from Systems.PnW.Util.calc import AllianceCalculator

# Configure logger
logger = logging.getLogger("Reaper.PnWHopper")

# Central configuration for PnW Cogs
# Format: (module_path, class_name)
PNW_COGS = [
    ("Systems.PnW.IA.alliance", "AllianceManager"),
    ("Systems.PnW.MA.destroy", "DestroyCog"),
    ("Systems.PnW.MA.loot", "Loot"),
    ("Systems.PnW.MA.finder", "Finder"),
    ("Systems.PnW.IA.costs", "CostsCommand"),
    ("Systems.PnW.IA.snipe", "SnipeGuide"),
    ("Systems.PnW.IA.show", "ShowCog"),
    ("Systems.PnW.IA.compare", "CompareCog"),
    ("Systems.PnW.IA.audit", "AuditManager"),
    ("Systems.PnW.IA.stocks", "ResourceStocks"),
    ("Systems.PnW.IA.colors", "Colors"),
    ("Systems.PnW.IA.colors", "GameInfoCog"),
    ("Systems.PnW.IA.resource", "ResourceCog")
]

async def setup(bot: commands.Bot):
    """
    Optimized setup for loading all Politics & War system cogs.
    This acts as a 'hopper/splicer' to neatly import and register all PnW components.
    """
    logger.info("Initializing Politics & War System Hopper...")
    
    # --- Step 1: Create shared instances ---
    query_instance = create_query_instance(logger=logger)
    calc_instance = AllianceCalculator(query_instance)
    
    # --- Step 2: Load cogs with specific dependency injection ---
    loaded_count = 0
    for module_path, class_name in PNW_COGS:
        try:
            module = importlib.import_module(module_path)
            cog_class = getattr(module, class_name)

            if class_name == "AllianceManager":
                instance = cog_class(bot, query_instance, calc_instance)
                # Store instances on the cog itself for others to find
                instance.query_system = query_instance
                instance.calc_system = calc_instance
                await bot.add_cog(instance)

            elif class_name in ["SnipeGuide", "Finder", "AuditManager", "ResourceStocks", "GameInfoCog"]:
                alliance_cog = bot.get_cog("AllianceManager")
                if not alliance_cog:
                    raise Exception("AllianceManager cog not loaded, cannot inject dependencies.")

                if class_name == "Finder":
                    instance = cog_class(bot, alliance_cog.query_system)
                elif class_name == "GameInfoCog":
                    instance = cog_class(bot, alliance_cog.query_system)
                else:
                    instance = cog_class(bot, alliance_cog.query_system, alliance_cog.calc_system)
                await bot.add_cog(instance)

            else:
                # For all other cogs with no special dependencies
                instance = cog_class(bot)
                await bot.add_cog(instance)
            
            logger.info(f"Successfully loaded PnW cog: {class_name}")
            loaded_count += 1

        except Exception as e:
            logger.error(f"Failed to load PnW cog '{class_name}' from '{module_path}': {e}", exc_info=True)

    logger.info(f"PnW System Hopper complete. {loaded_count}/{len(PNW_COGS)} components loaded.")


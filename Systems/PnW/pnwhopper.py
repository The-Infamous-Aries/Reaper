import asyncio
import discord
import logging
import importlib
from discord.ext import commands

from Systems.Functions import emoji as emoji_mod
from Systems.PnW.EA.colors import TempEmojiMod
from Systems.PnW.Util.query import create_v3_query_instance, V3GraphQuery
from Systems.PnW.Util.calc import AllianceCalculator
from Systems.Functions.utils import initialize_service_ports, cleanup_service_ports

# Configure logger
logger = logging.getLogger("Reaper.PnWHopper")

# Central configuration for PnW Cogs organized by categories
# Format: (module_path, class_name, category)
PNW_COGS = {
    # IA (Internal Affairs) Cogs
    "IA": [
        ("Systems.PnW.IA.alliance", "AllianceManager"),
        ("Systems.PnW.IA.costs", "CostsCommand"),
        ("Systems.PnW.IA.show", "ShowCog"),
        ("Systems.PnW.IA.audit", "AuditManager"),
        ("Systems.PnW.IA.guide", "SnipeGuide"),
    ],
    # EA (Economic Affairs) Cogs
    "EA": [
        ("Systems.PnW.EA.stocks", "ResourceStocks"),
        ("Systems.PnW.EA.colors", "Colors"),
        ("Systems.PnW.EA.colors", "GameInfoCog"),
        ("Systems.PnW.EA.resource", "ResourceCog"),
        ("Systems.PnW.EA.rev", "RevenueCommand"),
        ("Systems.PnW.EA.rss_alerts", "RssAlerts"),
        ("Systems.PnW.EA.rev_optimizer", "RevenueOptimizer"),
    ],
    # FA (Foreign Affairs) Cogs
    "FA": [
        ("Systems.PnW.FA.compare", "CompareCog"),
        ("Systems.PnW.FA.treaties", "TreatiesManager"),
        ("Systems.PnW.FA.universe", "UniverseCog"),
    ],
    # MA (Military Affairs) Cogs
    "MA": [
        ("Systems.PnW.MA.destroy", "DestroyCog"),
        ("Systems.PnW.MA.finder", "Finder"),
        ("Systems.PnW.MA.wars", "Wars"),
        ("Systems.PnW.MA.war_costs_bd", "WarsBD"),
        ("Systems.PnW.MA.war_net_bd", "WarsNetBD"),
        ("Systems.PnW.MA.units", "Units"),
        ("Systems.PnW.MA.weapon_eff", "WeaponEfficiency"),
        ("Systems.PnW.MA.war_sim", "WarSimCog"),
        ("Systems.PnW.MA.raids", "Raids"),
        ("Systems.PnW.MA.offshore", "Offshore"),
        ("Systems.PnW.MA.rankings", "Rankings"),
        ("Systems.PnW.MA.compare_wars", "CompareWars"),
    ],
    # Other Cogs
    "Other": [
        ("Systems.PnW.Other.baseball", "BaseballCog"),
        ("Systems.PnW.Other.loot", "Loot"),
        ("Systems.PnW.Other.activity", "Activity"),
        ("Systems.PnW.timed_queries", "TimedQueries"),
        ("Systems.PnW.Other.theme", "ThemeCog")
    ]
}

async def setup(bot: commands.Bot):
    """
    Optimized setup for loading all Politics & War system cogs.
    This acts as a 'hopper/splicer' to neatly import and register all PnW components.
    """
    logger.info("Initializing Politics & War System Hopper...")
    
    # --- Step 1: Initialize service ports ---
    initialize_service_ports()
    
    # --- Step 2: Create shared instances ---
    query_instance = create_v3_query_instance(logger=logger)
    calc_instance = AllianceCalculator(query_instance)
    
    # --- Step 2: Load cogs by category with specific dependency injection ---
    loaded_count = 0
    total_cogs = sum(len(cogs) for cogs in PNW_COGS.values())
    
    # First, load AllianceManager as it's a dependency for many other cogs
    alliance_manager_path = "Systems.PnW.IA.alliance"
    alliance_manager_class = "AllianceManager"
    try:
        module = importlib.import_module(alliance_manager_path)
        cog_class = getattr(module, alliance_manager_class)
        instance = cog_class(bot, query_instance, calc_instance)
        # Store instances on the cog itself for others to find
        instance.query_system = query_instance
        instance.calc_system = calc_instance
        await bot.add_cog(instance)
        logger.info(f"Successfully loaded PnW cog: {alliance_manager_class} (IA)")
        loaded_count += 1
    except Exception as e:
        logger.error(f"Failed to load critical PnW cog '{alliance_manager_class}' from '{alliance_manager_path}': {e}", exc_info=True)
        # Continue loading other cogs even if AllianceManager fails
    
    # Load all other cogs by category
    for category, cogs in PNW_COGS.items():
        for module_path, class_name in cogs:
            # Skip AllianceManager as it's already loaded
            if class_name == "AllianceManager":
                continue
                
            try:
                module = importlib.import_module(module_path)
                cog_class = getattr(module, class_name)

                # Handle dependency injection based on category and class
                if category == "IA":
                    # IA cogs that need AllianceManager dependencies
                    if class_name in ["SnipeGuide", "AuditManager", "TreatiesManager"]:
                        alliance_cog = bot.get_cog("AllianceManager")
                        if alliance_cog:
                            instance = cog_class(bot, alliance_cog.query_system, alliance_cog.calc_system)
                        else:
                            logger.warning(f"AllianceManager not found, loading {class_name} without dependencies")
                            instance = cog_class(bot)
                    else:
                        # Other IA cogs
                        instance = cog_class(bot)

                elif category == "EA":
                    # EA cogs that need AllianceManager dependencies
                    if class_name in ["ResourceStocks", "GameInfoCog"]:
                        alliance_cog = bot.get_cog("AllianceManager")
                        if alliance_cog:
                            if class_name == "ResourceStocks":
                                instance = cog_class(bot, alliance_cog.query_system, alliance_cog.calc_system)
                            else:
                                emoji_mod_instance = TempEmojiMod(bot)
                                instance = cog_class(bot, emoji_mod=emoji_mod_instance, query_instance=alliance_cog.query_system)
                        else:
                            logger.warning(f"AllianceManager not found, loading {class_name} without dependencies")
                            instance = cog_class(bot)
                    else:
                        # Other EA cogs
                        instance = cog_class(bot)

                elif category == "FA":
                    # FA cogs that need AllianceManager dependencies
                    if class_name in ["CompareCog", "TreatiesManager", "UniverseCog"]:
                        alliance_cog = bot.get_cog("AllianceManager")
                        if alliance_cog:
                            if class_name == "TreatiesManager":
                                instance = cog_class(bot, alliance_cog.query_system, alliance_cog.calc_system)
                            elif class_name == "CompareCog":
                                instance = cog_class(bot)
                            else:
                                instance = cog_class(bot, alliance_cog.query_system)
                        else:
                            logger.warning(f"AllianceManager not found, loading {class_name} without dependencies")
                            instance = cog_class(bot)
                    else:
                        # Other FA cogs
                        instance = cog_class(bot)

                elif category == "MA":
                    # MA cogs that need AllianceManager dependencies
                    if class_name in ["Finder", "Loot", "Units", "WeaponsEfficiency", "Raids"]:
                        alliance_cog = bot.get_cog("AllianceManager")
                        if alliance_cog:
                            if class_name in ["Finder", "Raids"]:
                                instance = cog_class(bot, alliance_cog.query_system)
                            else:
                                instance = cog_class(bot, alliance_cog.query_system, alliance_cog.calc_system)
                        else:
                            logger.warning(f"AllianceManager not found, loading {class_name} without dependencies")
                            instance = cog_class(bot)
                    else:
                        # Other MA cogs (DestroyCog, Wars, WarsBD)
                        instance = cog_class(bot)

                elif category == "Other":
                    if class_name == "TimedQueries":
                        alliance_cog = bot.get_cog("AllianceManager")
                        if alliance_cog:
                            instance = cog_class(bot, alliance_cog.query_system)
                        else:
                            logger.warning(f"AllianceManager not found, loading {class_name} without dependencies")
                            instance = cog_class(bot)
                    else:
                        instance = cog_class(bot)

                await bot.add_cog(instance)
                logger.info(f"Successfully loaded PnW cog: {class_name} ({category})")
                loaded_count += 1

            except Exception as e:
                logger.error(f"Failed to load PnW cog '{class_name}' from '{module_path}' ({category}): {e}", exc_info=True)

    logger.info(f"PnW System Hopper complete. {loaded_count}/{total_cogs} components loaded across categories: {', '.join(PNW_COGS.keys())}")


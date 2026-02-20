import asyncio
import discord
import logging
import importlib
from discord.ext import commands

from Systems.Functions import emoji as emoji_mod
from Systems.PnW.Util.query import create_query_instance, PNWAPIQuery # Added import
from Systems.PnW.Util.calc import AllianceCalculator # Added import

# Configure logger
logger = logging.getLogger("Allspark.PnWHopper")

# Mapping for Politics & War color strings to Discord hex colors
PNW_COLORS = {
    "black": 0x111111,
    "blue": 0x0074D9,
    "brown": 0x85144b,
    "gray": 0xAAAAAA,
    "green": 0x2ECC40,
    "lime": 0x01FF70,
    "maroon": 0x85144b,
    "olive": 0x3D9970,
    "orange": 0xFF851B,
    "pink": 0xF012BE,
    "purple": 0xB10DC9,
    "red": 0xFF4136,
    "white": 0xFFFFFF,
    "yellow": 0xFFDC00,
    "beige": 0xDDDDDD,
    "aqua": 0x7FDBFF
}

async def build_alliance_mini_embed(full_mill_data: dict, total_nations: int) -> discord.Embed:
    """
    Optimized async utility for building compact alliance overview embeds.
    """
    embed = discord.Embed(
        title=f"{emoji_mod.mention('Defend') or '🛡️'} Alliance Overview", 
        color=discord.Color.blue(),
        timestamp=discord.utils.utcnow()
    )
    
    # Header Statistics
    active_nations = full_mill_data.get('active_nations', 0)
    activity_pct = (active_nations / total_nations * 100) if total_nations > 0 else 0
    
    stats_value = (
        f"{emoji_mod.mention('NPC') or '📊'} **Total Nations:** `{total_nations}`\n"
        f"{emoji_mod.mention('GreenCircle') or '🟢'} **Active Nations:** `{active_nations}` ({activity_pct:.1f}%)\n"
        f"{emoji_mod.mention('City') or '🏙️'} **Total Cities:** `{int(full_mill_data.get('total_cities', 0)):,}`\n"
        f"{emoji_mod.mention('Trophy') or '🏆'} **Total Score:** `{int(full_mill_data.get('total_score', 0)):,}`"
    )
    embed.add_field(name=f"{emoji_mod.mention('Note') or '📊'} Overall Statistics", value=stats_value, inline=False)
    
    # Military Capacity (if available)
    if 'current_soldiers' in full_mill_data:
        mil_value = (
            f"{emoji_mod.mention('Soldier') or '🪖'} **Soldiers:** `{full_mill_data['current_soldiers']:,}`\n"
            f"{emoji_mod.mention('Tank') or '🚙'} **Tanks:** `{full_mill_data['current_tanks']:,}`\n"
            f"{emoji_mod.mention('Plane') or '🛩️'} **Aircraft:** `{full_mill_data['current_aircraft']:,}`\n"
            f"{emoji_mod.mention('Ship') or '⚓'} **Ships:** `{full_mill_data['current_ships']:,}`"
        )
        embed.add_field(name=f"{emoji_mod.mention('Attack') or '⚔️'} Military Strength", value=mil_value, inline=True)

    embed.set_footer(text="DB4D PnW Intelligence System")
    return embed

async def build_nation_mini_embed(
    nation: dict,
    vacation_turns: int,
    beige_turns: int,
    discord_info: str,
    last_active: str,
    project_status: str,
    city_status: str,
    cities: list,
    powered_cities: int,
    infra_tier: str,
    total_infra: float,
    avg_city_infra: float
) -> discord.Embed:
    """
    Optimized async utility for building detailed nation dossier embeds.
    """
    # Dynamic Color based on PnW nation color
    color_str = str(nation.get('color', 'white')).lower()
    embed_color = PNW_COLORS.get(color_str, 0x3498db)
    
    embed = discord.Embed(
        title=f"{emoji_mod.mention('City') or '🏛️'} {nation.get('nation_name', 'Unknown Nation')} Dossier",
        description=f"Information for **{nation.get('leader_name', 'Unknown Leader')}**'s nation.",
        color=embed_color,
        url=f"https://politicsandwar.com/nation/id={nation.get('id')}",
        timestamp=discord.utils.utcnow()
    )
    
    # Thumbnail: Nation Flag
    if nation.get('flag'):
        embed.set_thumbnail(url=nation.get('flag'))
    
    beige_line = f"**Beige Turns:** `{beige_turns}`\n" if color_str == 'beige' else ''
    
    basic_stats = (
        f"🚩 **Alliance:** {nation.get('alliance_name', 'None')}\n"
        f"🎖️ **Position:** {str(nation.get('alliance_position', 'Unknown')).title()}\n"
        f"🏖️ **Vacation Mode:** {'Yes' if int(vacation_turns or 0) > 0 else 'No'}\n"
        f"🎨 **Color:** {color_str.title()}\n"
        f"{beige_line}"
        f"💬 **Discord:** `{discord_info}`\n"
        f"🕒 **Last Active:** {last_active}"
    )
    embed.add_field(name=f"{emoji_mod.mention('Note') or '📊'} Basic Statistics", value=basic_stats, inline=False)
    
    growth_stats = (
        f"🏗️ **New Project:** {project_status}\n"
        f"🏙️ **New City:** {city_status}\n"
        f"🏢 **Total Cities:** `{int(nation.get('num_cities', 0))}`\n"
        f"⚡ **Powered:** `{int(powered_cities)}/{len(cities)}`"
    )
    embed.add_field(name=f"{emoji_mod.mention('Chart') or '📈'} Growth & Development", value=growth_stats, inline=True)
    
    infra_stats = (
        f"🪜 **Tier:** {infra_tier}\n"
        f"📐 **Total Infra:** `{float(total_infra):,.0f}`\n"
        f"📏 **Avg/City:** `{float(avg_city_infra):,.0f}`\n"
        f"⚖️ **Policy:** {nation.get('domestic_policy', 'Unknown')}"
    )
    embed.add_field(name=f"{emoji_mod.mention('Hammer') or '🏗️'} Infrastructure", value=infra_stats, inline=True)

    embed.set_footer(text=f"Nation ID: {nation.get('id')} • Allspark PnW System")
    return embed

# Central configuration for PnW Cogs
# Format: (module_path, class_name)
PNW_COGS = [
    ("Systems.PnW.MA.destroy", "DestroyCog"),
    ("Systems.PnW.IA.rev", "RevenueCommand"),
    ("Systems.PnW.MA.war_cost", "WarsCostCog"),
    ("Systems.PnW.IA.alliance", "AllianceManager"),
    ("Systems.PnW.IA.snipe", "SnipeGuide"),
    ("Systems.PnW.IA.show", "ShowCog"),
    ("Systems.PnW.IA.compare", "CompareCog"),
    ("Systems.PnW.IA.audit", "AuditManager"),
    ("Systems.PnW.IA.stocks", "ResourceStocks"),
    ("Systems.Welcome.welcome_system", "WelcomeSystem"),
]

async def setup(bot: commands.Bot):
    """
    Optimized setup for loading all Politics & War system cogs.
    This acts as a 'hopper/splicer' to neatly import and register all PnW components.
    """
    logger.info("Initializing Politics & War System Hopper...")
    
    loaded_count = 0
    for module_path, class_name in PNW_COGS:
        try:
            # Check if already loaded
            if bot.get_cog(class_name):
                logger.debug(f"Cog '{class_name}' is already loaded. Skipping.")
                continue

            # Try to use the module's own setup function first (standard d.py pattern)
            try:
                module = importlib.import_module(module_path)
                if hasattr(module, "setup"):
                    if asyncio.iscoroutinefunction(module.setup):
                        await module.setup(bot)
                    else:
                        module.setup(bot)
                    logger.info(f"Successfully loaded PnW module: {module_path}")
                    loaded_count += 1
                    continue
            except Exception as e:
                logger.debug(f"Module-level setup failed for {module_path}, falling back to manual cog addition: {e}")

            # Fallback: Manually instantiate and add the cog
            module = importlib.import_module(module_path)
            cog_class = getattr(module, class_name)
            
            # Special handling for SnipeGuide which requires query_instance and calc_instance
            if class_name == "SnipeGuide":
                query_instance = None
                calc_instance = None
                
                # Try to get instances from AllianceManager if it's already loaded
                alliance_cog = bot.get_cog('AllianceManager')
                if alliance_cog and hasattr(alliance_cog, 'query_system') and hasattr(alliance_cog, 'calc_system'):
                    query_instance = alliance_cog.query_system
                    calc_instance = alliance_cog.calc_system
                    logger.debug("SnipeGuide using query and calc instances from AllianceManager.")
                else:
                    # Fallback to creating new instances
                    # (PANDW_API_KEY needs to be available in the environment or config for this to work)
                    query_instance = create_query_instance(logger=logger)
                    calc_instance = AllianceCalculator()
                    logger.warning("AllianceManager not found or missing instances. SnipeGuide creating new query/calc instances.")

                if query_instance and calc_instance:
                    await bot.add_cog(cog_class(bot, query_instance, calc_instance))
                    logger.info(f"Successfully loaded PnW cog: {class_name} from {module_path}")
                    loaded_count += 1
                else:
                    logger.error(f"Failed to initialize query_instance or calc_instance for {class_name}.")
            else:
                # General fallback for other cogs
                await bot.add_cog(cog_class(bot))
                logger.info(f"Successfully loaded PnW cog: {class_name} from {module_path}")
                loaded_count += 1

        except Exception as e:
            logger.error(f"Failed to load PnW cog '{class_name}' from '{module_path}': {e}", exc_info=True)

    logger.info(f"PnW System Hopper complete. {loaded_count}/{len(PNW_COGS)} components loaded.")


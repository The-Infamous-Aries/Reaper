import asyncio
from discord.ext import commands
import discord

def build_alliance_mini_embed(full_mill_data: dict, total_nations: int) -> discord.Embed:
    embed = discord.Embed(title="Alliance Overview")
    embed.add_field(
        name="📊 Overall Statistics",
        value=(
            f"**Total Nations:** {total_nations}\n"
            f"**Active Nations:** {full_mill_data.get('active_nations', 0)}\n"
            f"**Total Cities:** {int(full_mill_data.get('total_cities', 0)):,}\n"
            f"**Total Score:** {int(full_mill_data.get('total_score', 0)):,}"
        ),
        inline=False
    )
    return embed

def build_nation_mini_embed(
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
    embed = discord.Embed(title="Nation Overview")
    beige_line = f"**Beige Turns:** {beige_turns}\n" if str(nation.get('color', '')).lower() == 'beige' else ''
    basic_stats = (
        f"**Alliance:** {nation.get('alliance_name', 'None')}\n"
        f"**Position:** {str(nation.get('alliance_position', 'Unknown')).title()}\n"
        f"**Vacation Mode:** {'Yes' if int(vacation_turns or 0) > 0 else 'No'}\n"
        f"**Color:** {nation.get('color', 'Unknown')}\n"
        f"{beige_line}"
        f"**Discord:** {discord_info}\n"
        f"**Last Active:** {last_active}\n"
        f"**New Project:** {project_status}\n"
        f"**New City:** {city_status}\n"
        f"**Cities:** {int(nation.get('num_cities', 0))}\n"
        f"**Powered Cities:** {int(powered_cities)}/{len(cities)}\n"
        f"**Infra Tier:** {infra_tier}\n"
        f"**Total Infrastructure:** {float(total_infra):,.0f}\n"
        f"**Avg Infrastructure/City:** {float(avg_city_infra):,.0f}\n"
        f"**Domestic Policy:** {nation.get('domestic_policy', 'Unknown')}"
    )
    embed.add_field(name="📊 Basic Statistics", value=basic_stats, inline=False)
    return embed


async def setup(bot: commands.Bot):
    try:
        from Systems.PnW.MA.destroy import setup as setup_destroy
        await setup_destroy(bot)
    except Exception:
        try:
            from Systems.PnW.MA.destroy import DestroyCog
            if bot.get_cog("DestroyCog") is None:
                await bot.add_cog(DestroyCog(bot))
        except Exception:
            pass
    try:
        from Systems.PnW.IA.rev import setup as setup_rev
        await setup_rev(bot)
    except Exception:
        try:
            from Systems.PnW.IA.rev import RevenueCommand
            if bot.get_cog("RevenueCommand") is None:
                await bot.add_cog(RevenueCommand(bot))
        except Exception:
            pass
    try:
        from Systems.PnW.MA.war_cost import WarsCostCog
        if bot.get_cog("WarsCostCog") is None:
            await bot.add_cog(WarsCostCog(bot))
    except Exception:
        pass
    try:
        from Systems.PnW.IA.snipe import SnipeGuide
        if bot.get_cog("SnipeGuide") is None:
            await bot.add_cog(SnipeGuide(bot))
    except Exception:
        pass
    try:
        from Systems.PnW.IA.show import ShowCog
        if bot.get_cog("ShowCog") is None:
            await bot.add_cog(ShowCog(bot))
    except Exception:
        pass
    try:
        from Systems.PnW.IA.compare import CompareCog
        if bot.get_cog("CompareCog") is None:
            await bot.add_cog(CompareCog(bot))
    except Exception:
        pass
    try:
        from Systems.PnW.IA.audit import AuditManager
        if bot.get_cog("AuditManager") is None:
            await bot.add_cog(AuditManager(bot))
    except Exception:
        pass
    try:
        from Systems.PnW.IA.alliance import AllianceManager
        if bot.get_cog("AllianceManager") is None:
            await bot.add_cog(AllianceManager(bot))
    except Exception:
        pass
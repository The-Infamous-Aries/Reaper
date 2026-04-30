"""
NationsManagerCog — Slash commands for managing the IRS nations database.

Commands:
    /nations sync       — upsert all current members (safe, keeps history)
    /nations repopulate — wipe + full rebuild from scratch
    /nations status     — show DB stats and subscription health
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging
from datetime import datetime, timezone

from Systems.Functions.irs_nations_manager import (
    sync_nations,
    DATABASE_FILE,
    ALLIANCE_ID,
)
from Systems.Functions.irs_nations_db import IRSNationsDB

logger = logging.getLogger(__name__)


class NationsManagerCog(commands.Cog):
    """Manage the IRS nations database."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    nations = app_commands.Group(name="nations", description="IRS nations database management")

    @nations.command(name="sync", description="Upsert all current EP members into the DB (safe — keeps existing data)")
    async def nations_sync(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            start = datetime.now(timezone.utc)
            result = await sync_nations(force=False)
            elapsed = (datetime.now(timezone.utc) - start).total_seconds()

            embed = discord.Embed(title="✅ Nations Sync Complete", color=discord.Color.green())
            embed.add_field(name="Nations Saved",    value=f"{result['nations_saved']:,}",  inline=True)
            embed.add_field(name="Cities Saved",     value=f"{result['cities_saved']:,}",   inline=True)
            embed.add_field(name="DB Total Nations", value=f"{result['total_nations']:,}",  inline=True)
            embed.add_field(name="DB Total Cities",  value=f"{result['total_cities']:,}",   inline=True)
            embed.set_footer(text=f"Alliance {ALLIANCE_ID} | Took {elapsed:.1f}s")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"nations sync error: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Sync failed: {e}")

    @nations.command(name="repopulate", description="WIPE and fully rebuild the nations DB from scratch")
    async def nations_repopulate(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            start = datetime.now(timezone.utc)
            result = await sync_nations(force=True)
            elapsed = (datetime.now(timezone.utc) - start).total_seconds()

            embed = discord.Embed(
                title="🔄 Nations Repopulate Complete",
                description="Tables were wiped and fully rebuilt from the PnW API.",
                color=discord.Color.orange(),
            )
            embed.add_field(name="Nations Saved",    value=f"{result['nations_saved']:,}",  inline=True)
            embed.add_field(name="Cities Saved",     value=f"{result['cities_saved']:,}",   inline=True)
            embed.add_field(name="DB Total Nations", value=f"{result['total_nations']:,}",  inline=True)
            embed.add_field(name="DB Total Cities",  value=f"{result['total_cities']:,}",   inline=True)
            embed.set_footer(text=f"Alliance {ALLIANCE_ID} | Took {elapsed:.1f}s")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"nations repopulate error: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Repopulate failed: {e}")

    @nations.command(name="status", description="Show nations DB stats and subscription status")
    async def nations_status(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            db = IRSNationsDB(str(DATABASE_FILE))
            stats = await db.get_stats()

            embed = discord.Embed(title="📊 Nations DB Status", color=discord.Color.blurple())
            embed.add_field(name="Nations in DB", value=f"{stats['nations']:,}", inline=True)
            embed.add_field(name="Cities in DB",  value=f"{stats['cities']:,}",  inline=True)
            embed.add_field(name="Alliance ID",   value=str(ALLIANCE_ID),        inline=True)
            embed.add_field(name="DB File",       value=f"`{DATABASE_FILE.name}`", inline=False)
            embed.set_footer(text="Use /nations sync to update • /nations repopulate to rebuild")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"nations status error: {e}", exc_info=True)
            await interaction.followup.send(f"❌ Status check failed: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(NationsManagerCog(bot))
    logger.info("NationsManagerCog loaded")

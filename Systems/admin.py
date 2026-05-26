"""
Admin Cog - Houses the administrative commands for the bot.
"""

import discord
from discord.ext import commands
from discord import app_commands
from typing import List

from Systems.Functions.config import ARIES_USER_ID, ADMIN_USER_ID
from Systems.Functions.utils import cleanup_service_ports
from Systems.info import UsagePaginatorView


class Admin(commands.Cog):
    """Administrative commands for bot management."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="shutdown", description="Securely shuts down the bot.")
    @commands.is_owner()
    async def shutdown(self, ctx: commands.Context):
        """Securely shuts down the bot, can only be used by the bot owner."""
        if ctx.author.id != ARIES_USER_ID:
            await ctx.send("You do not have permission to use this command.", ephemeral=True)
            return

        await ctx.send("Shutting down...", ephemeral=True)
        self.bot.logger.info(f"Shutdown command initiated by {ctx.author} (ID: {ctx.author.id})")
        cleanup_service_ports()
        await self.bot.close()

    @commands.hybrid_command(name="usage", description="Shows bot usage statistics and allows for management.")
    @commands.is_owner()
    async def usage(self, ctx: commands.Context):
        """Shows bot usage and allows for server/user management."""
        if ctx.author.id != ADMIN_USER_ID:
            await ctx.send("You do not have permission to use this command.", ephemeral=True)
            return

        try:
            view = UsagePaginatorView(self.bot, ADMIN_USER_ID)
            await view._init_data()
            embed = view.get_embed()
            message = await ctx.send(embed=embed, view=view, ephemeral=True)
            view.message = message
        except Exception as e:
            await ctx.send(f"Error loading usage view: {e}", ephemeral=True)

    @commands.hybrid_command(name="servers", description="Lists all servers the bot is in.")
    @commands.is_owner()
    async def servers(self, ctx: commands.Context):
        """Lists all servers the bot is currently in."""
        if ctx.author.id != ADMIN_USER_ID:
            await ctx.send("You do not have permission to use this command.", ephemeral=True)
            return

        guilds = self.bot.guilds
        guild_count = len(guilds)

        if guild_count == 0:
            await ctx.send("The bot is not in any servers.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Bot Server List ({guild_count} servers)",
            color=discord.Color.blue()
        )

        for guild in guilds:
            member_count = guild.member_count
            embed.add_field(
                name=guild.name,
                value=f"ID: {guild.id}\nMembers: {member_count:,}",
                inline=False
            )

        await ctx.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    """Add the Admin cog to the bot."""
    await bot.add_cog(Admin(bot))

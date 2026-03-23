
import asyncio
import logging
import discord
from discord.ext import commands, tasks

class ConnectionManager(commands.Cog):
    """Handles bot connection, latency, and automatic reconnections."""

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("Reaper.ConnectionManager")
        self.check_latency.start()

    def cog_unload(self):
        self.check_latency.cancel()

    @tasks.loop(minutes=5.0)
    async def check_latency(self):
        """Periodically checks bot latency and logs if it's high."""
        if self.bot.is_ready():
            latency = self.bot.latency
            self.logger.info(f"Current latency: {latency * 1000:.2f}ms")
            if latency > 0.5:
                self.logger.warning(f"High latency detected: {latency * 1000:.2f}ms")

    @commands.Cog.listener()
    async def on_connect(self):
        self.logger.info("Bot connected to Discord.")

    @commands.Cog.listener()
    async def on_disconnect(self):
        self.logger.warning("Bot disconnected from Discord. Monitoring for reconnection...")

    @commands.Cog.listener()
    async def on_resumed(self):
        self.logger.info("Bot has resumed its session.")

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Handle connection-related command errors."""
        if isinstance(error, (discord.errors.ConnectionClosed, discord.errors.GatewayNotFound)):
            self.logger.error(f"Connection error during command execution: {error}")
            try:
                await ctx.send("⚠️ Connection issue detected. The bot will attempt to reconnect automatically.")
            except:
                pass  # Can't send message due to connection issue

async def setup(bot):
    await bot.add_cog(ConnectionManager(bot))

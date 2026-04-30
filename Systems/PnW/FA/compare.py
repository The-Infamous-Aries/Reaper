import discord
from discord import app_commands
from discord.ext import commands
from Systems.Functions.emoji import mention

import re
import logging
from typing import Any, Dict, List, Optional, Tuple, Union, cast, Sequence
from io import BytesIO
import asyncio
import time

from Systems.Functions.utils import get_web_public_url
from Systems.PnW.Util.query import create_v3_query_instance

class CompareCog(commands.Cog):
    """Provides a /compare slash command to compare alliances."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)

    @app_commands.command(name="compare", description="Compare two alliances or sets of alliances.")
    @app_commands.describe(
        home="The 'home' alliance(s) to compare. Use IDs or names, comma-separated.",
        away="The 'away' alliance(s) to compare. Use IDs or names, comma-separated."
    )
    async def compare(self, interaction: discord.Interaction, home: str, away: str):
        await interaction.response.defer()

        # Sanitize input to prevent injection issues, although it's just going into a URL.
        safe_home = home.replace("\"", "").replace("'", "")
        safe_away = away.replace("\"", "").replace("'", "")

        # We need to URL encode the parameters
        from urllib.parse import quote_plus

        public_url = get_web_public_url()
        url = f"{public_url}/api/pnw/compare?home={quote_plus(safe_home)}&away={quote_plus(safe_away)}"

        embed = discord.Embed(
            title="Alliance Comparison",
            description=f"An interactive comparison has been generated for **{home}** vs **{away}**.",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Interactive Graph", value=f"[Click here to view]({url})")
        embed.set_footer(text="This link provides a detailed, interactive breakdown of the two sides.")

        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    # Add the cog
    try:
        await bot.add_cog(CompareCog(bot))
    except Exception as e:
        logging.getLogger(__name__).warning(f"compare.py setup: failed to add cog: {e}")
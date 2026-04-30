import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import discord
from discord.ext import commands
import logging
import os
import socket
import math
import sys
import pathlib
from PIL import Image, ImageDraw, ImageFont
import io
import aiohttp

sys.path.append(str(pathlib.Path(__file__).parent.parent))
from Util.Graphs.treaty_graph import TreatyGraph

from Systems.Functions.utils import get_web_public_url
from collections import defaultdict
import urllib.request
import concurrent.futures
import shutil
import json

class TreatyUniverse:
    def __init__(self, query_instance):
        self.query_instance = query_instance
        self.treaty_graph = TreatyGraph()

    async def get_all_treaties(self) -> List[Dict[str, Any]]:
        try:
            all_treaties = await self.query_instance.get_all_treaties_paginated(force_refresh=True)
            return all_treaties
        except Exception as e:
            print(f"Error fetching all treaties: {e}")
            return []

class UniverseCog(commands.Cog):
    def __init__(self, bot: commands.Bot, query_instance):
        self.bot = bot
        self.query_instance = query_instance
        self.logger = logging.getLogger(self.__class__.__name__)

    @commands.hybrid_command(name='treaty_universe', aliases=['treaty_map', 'universe'], description='Shows an interactive treaty map centered on an alliance')
    @discord.app_commands.describe(alliance='Alliance name or ID to center the map on')
    async def game_treaties(self, ctx, alliance: str):
        await ctx.interaction.response.defer()

        public_url = get_web_public_url()
        from urllib.parse import quote_plus
        url = f"{public_url}/api/pnw/universe?alliance={quote_plus(alliance)}"

        embed = discord.Embed(
            title="Interactive Treaty Universe",
            description=f"Treaty map centered on **{alliance}** has been generated.",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Interactive Map", value=f"[Click here to view]({url})")
        embed.set_footer(text="Shows direct treaty partners and their connections.")

        await ctx.interaction.followup.send(embed=embed)

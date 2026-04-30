"""
theme.py — /theme commands for customising nation emojis in autocomplete dropdowns.

Commands
--------
/theme emoji set <nation> <emoji>   — assign an emoji to a nation
/theme emoji remove <nation>        — revert a nation to the default 🏛️
/theme emoji list                   — show all custom emojis
/theme emoji reload                 — reload the emoji store from disk
"""

from __future__ import annotations

import logging
from typing import List

import discord
from discord import app_commands
from discord.ext import commands

from Systems.Functions.nation_emoji_store import (
    get_all,
    get_nation_emoji,
    reload,
    remove_nation_emoji,
    set_nation_emoji,
)
from Systems.Functions.db_paths import EP_NATIONS_DB
from Systems.Functions.irs_nations_db import IRSNationsDB

logger = logging.getLogger(__name__)


async def _get_ep_nation_names() -> List[str]:
    """Return all nation names currently in the EP nations DB."""
    try:
        db = IRSNationsDB(str(EP_NATIONS_DB))
        nations = await db.get_all_nations()
        return sorted(
            n["nation_name"]
            for n in nations
            if n.get("nation_name")
        )
    except Exception as e:
        logger.error(f"theme: could not load EP nations: {e}")
        return []


class ThemeCog(commands.Cog):
    """Customise how nations appear in autocomplete dropdowns."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    theme = app_commands.Group(name="theme", description="Customise bot appearance")
    emoji_group = app_commands.Group(
        name="emoji", description="Manage nation emojis in dropdowns", parent=theme
    )

    # ── /theme emoji set ──────────────────────────────────────────────────────

    @emoji_group.command(name="set", description="Set an emoji for a nation in autocomplete dropdowns")
    @app_commands.describe(
        nation="Nation name (from the EP nations database)",
        emoji="The emoji to show next to this nation",
    )
    async def emoji_set(
        self,
        interaction: discord.Interaction,
        nation: str,
        emoji: str,
    ):
        await interaction.response.defer(ephemeral=True)

        nation = nation.strip()
        emoji = emoji.strip()

        if not nation:
            await interaction.followup.send("❌ Nation name cannot be empty.", ephemeral=True)
            return

        if not emoji:
            await interaction.followup.send("❌ Emoji cannot be empty.", ephemeral=True)
            return

        # Validate the nation exists in the DB
        names = await _get_ep_nation_names()
        if names and nation not in names:
            # Soft warning — still allow it in case DB is stale
            warning = f"⚠️ **{nation}** wasn't found in the EP nations DB (may be stale). Saving anyway.\n"
        else:
            warning = ""

        set_nation_emoji(nation, emoji)
        await interaction.followup.send(
            f"{warning}✅ Set **{nation}** → {emoji}",
            ephemeral=True,
        )

    @emoji_set.autocomplete("nation")
    async def _nation_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        names = await _get_ep_nation_names()
        low = current.lower()
        matches = [n for n in names if low in n.lower()] if current else names
        return [
            app_commands.Choice(name=f"{get_nation_emoji(n)} {n}", value=n)
            for n in matches[:25]
        ]

    # ── /theme emoji remove ───────────────────────────────────────────────────

    @emoji_group.command(name="remove", description="Remove a custom emoji (reverts to default 🏛️)")
    @app_commands.describe(nation="Nation name to reset")
    async def emoji_remove(self, interaction: discord.Interaction, nation: str):
        await interaction.response.defer(ephemeral=True)
        nation = nation.strip()
        if remove_nation_emoji(nation):
            await interaction.followup.send(f"✅ Removed custom emoji for **{nation}** (now 🏛️)", ephemeral=True)
        else:
            await interaction.followup.send(f"ℹ️ **{nation}** had no custom emoji set.", ephemeral=True)

    @emoji_remove.autocomplete("nation")
    async def _remove_nation_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        store = get_all()
        low = current.lower()
        matches = [n for n in store if low in n.lower()] if current else list(store.keys())
        return [
            app_commands.Choice(name=f"{store[n]} {n}", value=n)
            for n in matches[:25]
        ]

    # ── /theme emoji list ─────────────────────────────────────────────────────

    @emoji_group.command(name="list", description="Show all custom nation emojis")
    async def emoji_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        store = get_all()
        if not store:
            await interaction.followup.send("No custom nation emojis set. Use `/theme emoji set` to add some.", ephemeral=True)
            return

        lines = [f"{emoji}  {name}" for name, emoji in sorted(store.items())]
        # Chunk into pages of 20
        pages = [lines[i : i + 20] for i in range(0, len(lines), 20)]
        for i, page in enumerate(pages):
            header = f"**Nation Emojis** (page {i+1}/{len(pages)})\n" if len(pages) > 1 else "**Nation Emojis**\n"
            await interaction.followup.send(header + "\n".join(page), ephemeral=True)

    # ── /theme emoji reload ───────────────────────────────────────────────────

    @emoji_group.command(name="reload", description="Reload the emoji store from disk")
    async def emoji_reload(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        reload()
        store = get_all()
        await interaction.followup.send(
            f"✅ Emoji store reloaded — {len(store)} custom emoji(s) loaded.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ThemeCog(bot))

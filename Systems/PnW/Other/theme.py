"""
theme.py — /theme commands for customising nation and alliance emojis.

Commands
--------
/theme emoji set <type> <name> <emoji>   — assign an emoji to a nation or alliance
/theme emoji remove <type> <name>        — revert to default emoji
/theme emoji list                        — show all custom emojis (nations + alliances)
/theme emoji reload                      — reload emoji stores from disk

<type> is a required choice: "nation" or "alliance"
"""

from __future__ import annotations

import logging
from typing import List, Literal

import discord
from discord import app_commands
from discord.ext import commands

from Systems.Functions.nation_emoji_store import (
    get_all,
    get_all_alliances,
    get_alliance_emoji,
    get_nation_emoji,
    reload,
    remove_alliance_emoji,
    remove_nation_emoji,
    set_alliance_emoji,
    set_nation_emoji,
)

logger = logging.getLogger(__name__)


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _get_all_nation_names() -> List[str]:
    """Return ALL nation names from GlobalNations.db (not just one alliance)."""
    try:
        from PnWHarvester.db.global_nations_db import GlobalNationsDB
        from Systems.Functions.db_paths import GLOBAL_NATIONS_DB as _GNDB
        db = GlobalNationsDB(str(_GNDB))
        nations = await db.get_all_nations()
        return sorted(
            n["nation_name"]
            for n in nations
            if n.get("nation_name")
        )
    except Exception as e:
        logger.error(f"theme: could not load all nations: {e}")
        return []


async def _search_nation_names(current: str) -> List[str]:
    """Search nation names in GlobalNations.db for autocomplete (all nations)."""
    try:
        from PnWHarvester.db.global_nations_db import GlobalNationsDB
        from Systems.Functions.db_paths import GLOBAL_NATIONS_DB as _GNDB
        db = GlobalNationsDB(str(_GNDB))
        results = await db.search_nations(current, limit=25)
        return [n["nation_name"] for n in results if n.get("nation_name")]
    except Exception as e:
        logger.error(f"theme: could not search nations: {e}")
        return []


async def _get_all_alliance_names() -> List[str]:
    """Return all distinct alliance names from GlobalNations.db."""
    try:
        from PnWHarvester.db.global_nations_db import GlobalNationsDB
        from Systems.Functions.db_paths import GLOBAL_NATIONS_DB as _GNDB
        db = GlobalNationsDB(str(_GNDB))
        alliances = await db.get_distinct_alliances()
        return [
            a["alliance_name"]
            for a in alliances
            if a.get("alliance_name")
        ]
    except Exception as e:
        logger.error(f"theme: could not load alliances: {e}")
        return []


async def _search_alliance_names(current: str) -> List[str]:
    """Search alliance names in GlobalNations.db for autocomplete."""
    try:
        from PnWHarvester.db.global_nations_db import GlobalNationsDB
        from Systems.Functions.db_paths import GLOBAL_NATIONS_DB as _GNDB
        db = GlobalNationsDB(str(_GNDB))
        alliances = await db.get_distinct_alliances(current)
        return [
            a["alliance_name"]
            for a in alliances
            if a.get("alliance_name")
        ][:25]
    except Exception as e:
        logger.error(f"theme: could not search alliances: {e}")
        return []


# ── Cog ───────────────────────────────────────────────────────────────────────

class ThemeCog(commands.Cog):
    """Customise how nations and alliances appear in autocomplete dropdowns."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    theme = app_commands.Group(name="theme", description="Customise bot appearance")
    emoji_group = app_commands.Group(
        name="emoji", description="Manage nation/alliance emojis in dropdowns", parent=theme
    )

    # ── /theme emoji set ──────────────────────────────────────────────────────

    @emoji_group.command(
        name="set",
        description="Set an emoji for a nation or alliance in autocomplete dropdowns",
    )
    @app_commands.describe(
        type="Whether to theme a nation or an alliance",
        name="Nation or alliance name",
        emoji="The emoji to show next to this nation/alliance",
    )
    async def emoji_set(
        self,
        interaction: discord.Interaction,
        type: Literal["nation", "alliance"],
        name: str,
        emoji: str,
    ):
        await interaction.response.defer(ephemeral=True)

        name = name.strip()
        emoji = emoji.strip()

        if not name:
            await interaction.followup.send("❌ Name cannot be empty.", ephemeral=True)
            return
        if not emoji:
            await interaction.followup.send("❌ Emoji cannot be empty.", ephemeral=True)
            return

        if type == "nation":
            set_nation_emoji(name, emoji)
            await interaction.followup.send(f"✅ Set nation **{name}** → {emoji}", ephemeral=True)
        else:
            set_alliance_emoji(name, emoji)
            await interaction.followup.send(f"✅ Set alliance **{name}** → {emoji}", ephemeral=True)

    @emoji_set.autocomplete("name")
    async def _set_name_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        # Determine which type was selected so we can show the right list.
        # Discord passes already-filled options in interaction.namespace.
        selected_type = getattr(interaction.namespace, "type", "nation")

        if selected_type == "alliance":
            names = await _search_alliance_names(current) if current else await _get_all_alliance_names()
            return [
                app_commands.Choice(
                    name=f"{get_alliance_emoji(n)} {n}"[:100],
                    value=n,
                )
                for n in names[:25]
            ]
        else:
            # nation (default)
            names = await _search_nation_names(current) if current else []
            if not names and not current:
                # Fallback: return nations that already have custom emojis first
                store = get_all()
                names = list(store.keys())[:25]
            return [
                app_commands.Choice(
                    name=f"{get_nation_emoji(n)} {n}"[:100],
                    value=n,
                )
                for n in names[:25]
            ]

    # ── /theme emoji remove ───────────────────────────────────────────────────

    @emoji_group.command(
        name="remove",
        description="Remove a custom emoji (reverts to default)",
    )
    @app_commands.describe(
        type="Whether to remove from a nation or an alliance",
        name="Nation or alliance name to reset",
    )
    async def emoji_remove(
        self,
        interaction: discord.Interaction,
        type: Literal["nation", "alliance"],
        name: str,
    ):
        await interaction.response.defer(ephemeral=True)
        name = name.strip()

        if type == "nation":
            if remove_nation_emoji(name):
                await interaction.followup.send(
                    f"✅ Removed custom emoji for nation **{name}** (now 🏛️)", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"ℹ️ Nation **{name}** had no custom emoji set.", ephemeral=True
                )
        else:
            if remove_alliance_emoji(name):
                await interaction.followup.send(
                    f"✅ Removed custom emoji for alliance **{name}** (now 🤝)", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"ℹ️ Alliance **{name}** had no custom emoji set.", ephemeral=True
                )

    @emoji_remove.autocomplete("name")
    async def _remove_name_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        selected_type = getattr(interaction.namespace, "type", "nation")
        low = current.lower()

        if selected_type == "alliance":
            store = get_all_alliances()
            matches = [n for n in store if low in n.lower()] if current else list(store.keys())
            return [
                app_commands.Choice(name=f"{store[n]} {n}"[:100], value=n)
                for n in matches[:25]
            ]
        else:
            store = get_all()
            matches = [n for n in store if low in n.lower()] if current else list(store.keys())
            return [
                app_commands.Choice(name=f"{store[n]} {n}"[:100], value=n)
                for n in matches[:25]
            ]

    # ── /theme emoji list ─────────────────────────────────────────────────────

    @emoji_group.command(name="list", description="Show all custom nation and alliance emojis")
    async def emoji_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        nation_store = get_all()
        alliance_store = get_all_alliances()

        if not nation_store and not alliance_store:
            await interaction.followup.send(
                "No custom emojis set. Use `/theme emoji set` to add some.",
                ephemeral=True,
            )
            return

        lines: List[str] = []

        if nation_store:
            lines.append("**Nations**")
            lines.extend(
                f"  {emoji}  {name}"
                for name, emoji in sorted(nation_store.items())
            )

        if alliance_store:
            if lines:
                lines.append("")
            lines.append("**Alliances**")
            lines.extend(
                f"  {emoji}  {name}"
                for name, emoji in sorted(alliance_store.items())
            )

        # Chunk into pages of 20 entries
        pages = [lines[i : i + 20] for i in range(0, len(lines), 20)]
        for i, page in enumerate(pages):
            header = f"**Emoji Themes** (page {i+1}/{len(pages)})\n" if len(pages) > 1 else ""
            await interaction.followup.send(header + "\n".join(page), ephemeral=True)

    # ── /theme emoji reload ───────────────────────────────────────────────────

    @emoji_group.command(name="reload", description="Reload the emoji stores from disk")
    async def emoji_reload(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        reload()
        nation_store = get_all()
        alliance_store = get_all_alliances()
        await interaction.followup.send(
            f"✅ Emoji stores reloaded — "
            f"{len(nation_store)} nation emoji(s), "
            f"{len(alliance_store)} alliance emoji(s).",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ThemeCog(bot))

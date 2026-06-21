"""
/track — manage which alliances / nations the harvester saves full war data for.
"""

from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from Systems.Functions.config import ARIES_USER_ID
from Systems.Functions.tracking_db import get_tracking_db

logger = logging.getLogger("Reaper.TrackCMD")

# ── autocomplete helpers ─────────────────────────────────────────────────────

async def _alliance_autocomplete(interaction: discord.Interaction, current: str):
    from Systems.Functions.autocomplete_utils import alliance_autocomplete
    return await alliance_autocomplete(current, include_nw=True, limit=25)


async def _nation_autocomplete(interaction: discord.Interaction, current: str):
    from Systems.Functions.autocomplete_utils import nation_autocomplete
    return await nation_autocomplete(current, nw_only=False, limit=25)


async def _who_autocomplete(interaction: discord.Interaction, current: str):
    """Route to alliance or nation autocomplete based on the `type` choice."""
    # Read the `type` option from the interaction
    entity_type = None
    for opt in (interaction.data or {}).get("options", []):
        if opt.get("type") == 1:  # Subcommand group
            for sub in opt.get("options", []):
                for arg in sub.get("options", []):
                    if arg.get("name") == "type":
                        entity_type = arg.get("value")
                        break
        elif opt.get("name") == "type":
            entity_type = opt.get("value")
            break

    if entity_type == "nation":
        return await _nation_autocomplete(interaction, current)
    return await _alliance_autocomplete(interaction, current)


# ── cog ──────────────────────────────────────────────────────────────────────

class TrackCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tracking_db = get_tracking_db()

    # ── /track add ────────────────────────────────────────────────────────────
    @commands.hybrid_command(name="track", description="Track an alliance or nation for full war data")
    @app_commands.describe(
        type="Whether to track an Alliance or a Nation",
        who="Name or ID of the alliance / nation (autocomplete searches)",
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="Alliance", value="alliance"),
        app_commands.Choice(name="Nation", value="nation"),
    ])
    @app_commands.autocomplete(who=_who_autocomplete)
    async def track_add(
        self,
        ctx: commands.Context,
        type: str,
        who: str,
    ):
        """Add an alliance or nation to war tracking."""
        if ctx.author.id != ARIES_USER_ID:
            await ctx.send("❌ Only ARIES can use this command.", ephemeral=True)
            return
        await ctx.defer(ephemeral=True)

        entity_type = type.lower()
        if entity_type not in ("alliance", "nation"):
            await ctx.send("❌ Type must be `Alliance` or `Nation`.", ephemeral=True)
            return

        # resolve the input to an ID and name
        resolved_id, resolved_name = await self._resolve_entity(entity_type, who)
        if resolved_id is None:
            await ctx.send(
                f"❌ Could not find a {entity_type} matching `{who}`.",
                ephemeral=True,
            )
            return

        added_by = str(ctx.author)
        ok = await self.tracking_db.add_entity(
            entity_type, resolved_id, resolved_name, added_by,
        )
        if ok:
            await ctx.send(
                f"✅ Now tracking **{resolved_name}** ({entity_type} ID `{resolved_id}`). "
                f"The harvester will save full war data for this {entity_type}.",
                ephemeral=True,
            )
        else:
            await ctx.send(
                f"ℹ️ **{resolved_name}** is already being tracked.",
                ephemeral=True,
            )

    # ── /track remove ─────────────────────────────────────────────────────────
    @commands.hybrid_command(name="untrack", description="Stop tracking an alliance or nation")
    @app_commands.describe(
        type="Whether to stop tracking an Alliance or a Nation",
        who="Name or ID of the alliance / nation",
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="Alliance", value="alliance"),
        app_commands.Choice(name="Nation", value="nation"),
    ])
    @app_commands.autocomplete(who=_who_autocomplete)
    async def track_remove(
        self,
        ctx: commands.Context,
        type: str,
        who: str,
    ):
        """Remove an alliance or nation from war tracking."""
        if ctx.author.id != ARIES_USER_ID:
            await ctx.send("❌ Only ARIES can use this command.", ephemeral=True)
            return
        await ctx.defer(ephemeral=True)

        entity_type = type.lower()
        if entity_type not in ("alliance", "nation"):
            await ctx.send("❌ Type must be `Alliance` or `Nation`.", ephemeral=True)
            return

        resolved_id, resolved_name = await self._resolve_entity(entity_type, who)
        if resolved_id is None:
            await ctx.send(
                f"❌ Could not find a {entity_type} matching `{who}`.",
                ephemeral=True,
            )
            return

        ok = await self.tracking_db.remove_entity(entity_type, resolved_id)
        if ok:
            await ctx.send(
                f"✅ Stopped tracking **{resolved_name}** ({entity_type} ID `{resolved_id}`).",
                ephemeral=True,
            )
        else:
            await ctx.send(
                f"ℹ️ **{resolved_name}** was not being tracked.",
                ephemeral=True,
            )

    # ── /track list ───────────────────────────────────────────────────────────
    @commands.hybrid_command(name="tracked", description="List all tracked alliances and nations")
    async def track_list(self, ctx: commands.Context):
        """Show all entities being tracked for war data."""
        if ctx.author.id != ARIES_USER_ID:
            await ctx.send("❌ Only ARIES can use this command.", ephemeral=True)
            return
        await ctx.defer(ephemeral=True)

        entities = await self.tracking_db.get_all_entities()
        if not entities:
            await ctx.send("📭 No alliances or nations are currently being tracked.", ephemeral=True)
            return

        lines = ["**Tracked Entities**\n"]
        for e in entities:
            lines.append(
                f"• **{e['entity_name'] or 'Unknown'}** "
                f"(`{e['entity_type']}` ID `{e['entity_id']}`) "
                f"— added by {e['added_by'] or '?'}"
            )

        await ctx.send("\n".join(lines), ephemeral=True)

    # ── resolver ──────────────────────────────────────────────────────────────
    async def _resolve_entity(
        self, entity_type: str, query: str,
    ) -> tuple[Optional[int], str]:
        """Turn a user-supplied name/ID into (entity_id, entity_name).

        Returns (None, "") if resolution fails.
        """
        from Systems.PnW.Util.query import create_v3_query_instance

        query = query.strip()

        # If it's purely numeric, try ID lookup first
        if query.isdigit():
            qid = int(query)
            if entity_type == "alliance":
                return qid, f"Alliance {qid}"
            else:
                return qid, f"Nation {qid}"

        qi = create_v3_query_instance()
        try:
            if entity_type == "alliance":
                # 1. Look up in local DB first (same source as autocomplete)
                try:
                    from PnWHarvester.db.global_nations_db import GlobalNationsDB
                    from Systems.Functions.db_paths import GLOBAL_NATIONS_DB
                    global_db = GlobalNationsDB(str(GLOBAL_NATIONS_DB))
                    matches = await global_db.get_distinct_alliances(query)
                    if matches:
                        query_lower = query.lower()
                        for a in matches:
                            if a.get("alliance_name", "").lower() == query_lower:
                                return int(a["alliance_id"]), a["alliance_name"]
                        a = matches[0]
                        return int(a["alliance_id"]), a.get("alliance_name", f"Alliance {a['alliance_id']}")
                except Exception as e:
                    logger.debug(f"Local DB lookup failed for alliance '{query}': {e}")

                # 2. Fall back to API with correct query
                result = await qi.resolve_alliance(query)
                if result:
                    return int(result["id"]), result.get("name", f"Alliance {result['id']}")
            else:
                nation = await qi.get_nation_by_id(query)
                if not nation:
                    nation = await qi.get_nation_by_name(query)
                if nation:
                    return int(nation["id"]), nation.get("nation_name", f"Nation {nation['id']}")
        except Exception as e:
            logger.warning(f"Entity resolution failed for {entity_type} '{query}': {e}")

        return None, ""


async def setup(bot: commands.Bot):
    await bot.add_cog(TrackCog(bot))

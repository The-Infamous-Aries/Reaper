"""
Ticket System — Darkstar
Guild: 1445703450263420938

Commands:
    /info            — Post the welcome embed with Membership / Embassy buttons
    /verify          — Accept or Reject the current ticket (staff)
    /delete_ticket   — Delete a ticket by name (autocomplete from DB)
    /resort_members  — Re-query PnW and rename all open member tickets
"""

from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from Systems.Functions.config import PANDW_API_V3_KEY
from Systems.Functions.db_paths import TICKETS_DB
from Systems.PnW.Util.query import create_v3_query_instance

# ShowCog is imported lazily inside the modal to avoid circular imports

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

GUILD_ID             = 1445703450263420938
INFO_CHANNEL_ID      = 1445703670057537700   # channel where /info embed is posted
TICKET_CATEGORY_ID   = 1498368211899383919   # open tickets category
MEMBER_ACCEPTED_CAT  = 1448558098888265778   # accepted member tickets category
EMBASSY_ACCEPTED_CAT = 1448558162054615091   # accepted embassy tickets category
MEMBER_ROLE_ID       = 1445983648988921997   # "Member" role
DIPLOMAT_ROLE_ID     = 1445983384873730069   # "Diplomat" role given to embassy applicants

PNW_BASE = "https://politicsandwar.com"


# ── DB Layer ──────────────────────────────────────────────────────────────────

class TicketsDB:
    """SQLite store for all ticket records."""

    def __init__(self, path: Path = TICKETS_DB):
        self.path = str(path)
        self._init()

    def _init(self):
        with sqlite3.connect(self.path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tickets (
                    channel_id      INTEGER PRIMARY KEY,
                    guild_id        INTEGER NOT NULL,
                    applicant_id    INTEGER NOT NULL,
                    ticket_type     TEXT    NOT NULL,   -- 'membership' | 'embassy'
                    status          TEXT    NOT NULL DEFAULT 'open',  -- 'open' | 'accepted' | 'rejected'
                    channel_name    TEXT    NOT NULL,
                    subject         TEXT    NOT NULL,   -- nation name or alliance name
                    nation_id       INTEGER,            -- set for membership tickets
                    alliance_id     INTEGER,            -- set for embassy tickets
                    city_count      INTEGER,            -- latest city count (membership)
                    color_hex       TEXT,               -- alliance color (embassy)
                    created_at      TEXT    NOT NULL,
                    updated_at      TEXT    NOT NULL
                )
            """)
            # Roles that are always added to every new ticket channel
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ticket_roles (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id    INTEGER NOT NULL,
                    role_id     INTEGER NOT NULL,
                    label       TEXT    NOT NULL,   -- friendly name for display
                    UNIQUE(guild_id, role_id)
                )
            """)
            conn.commit()

    # ── writes ────────────────────────────────────────────────────────────────

    def upsert(self, **kwargs):
        now = datetime.now(timezone.utc).isoformat()
        kwargs.setdefault("created_at", now)
        kwargs["updated_at"] = now
        cols = ", ".join(kwargs.keys())
        placeholders = ", ".join("?" * len(kwargs))
        updates = ", ".join(f"{k}=excluded.{k}" for k in kwargs if k != "channel_id")
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                f"INSERT INTO tickets ({cols}) VALUES ({placeholders}) "
                f"ON CONFLICT(channel_id) DO UPDATE SET {updates}",
                list(kwargs.values()),
            )
            conn.commit()

    def set_status(self, channel_id: int, status: str):
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "UPDATE tickets SET status=?, updated_at=? WHERE channel_id=?",
                (status, now, channel_id),
            )
            conn.commit()

    def update_channel_name(self, channel_id: int, new_name: str):
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "UPDATE tickets SET channel_name=?, updated_at=? WHERE channel_id=?",
                (new_name, now, channel_id),
            )
            conn.commit()

    def delete(self, channel_id: int):
        with sqlite3.connect(self.path) as conn:
            conn.execute("DELETE FROM tickets WHERE channel_id=?", (channel_id,))
            conn.commit()

    # ── reads ─────────────────────────────────────────────────────────────────

    def get(self, channel_id: int) -> Optional[dict]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM tickets WHERE channel_id=?", (channel_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_open(self, guild_id: int) -> List[dict]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM tickets WHERE guild_id=? AND status='open' ORDER BY created_at DESC",
                (guild_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_member_open(self, guild_id: int) -> List[dict]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM tickets WHERE guild_id=? AND ticket_type='membership' AND status='open'",
                (guild_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_all(self, guild_id: int) -> List[dict]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM tickets WHERE guild_id=? ORDER BY created_at DESC",
                (guild_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── ticket_roles ──────────────────────────────────────────────────────────

    def add_ticket_role(self, guild_id: int, role_id: int, label: str) -> bool:
        """Add a role to the ticket roles list. Returns False if already exists."""
        try:
            with sqlite3.connect(self.path) as conn:
                conn.execute(
                    "INSERT INTO ticket_roles (guild_id, role_id, label) VALUES (?, ?, ?)",
                    (guild_id, role_id, label),
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_ticket_role(self, guild_id: int, role_id: int) -> bool:
        """Remove a role from the ticket roles list. Returns False if not found."""
        with sqlite3.connect(self.path) as conn:
            cur = conn.execute(
                "DELETE FROM ticket_roles WHERE guild_id=? AND role_id=?",
                (guild_id, role_id),
            )
            conn.commit()
        return cur.rowcount > 0

    def list_ticket_roles(self, guild_id: int) -> List[dict]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM ticket_roles WHERE guild_id=? ORDER BY label",
                (guild_id,),
            ).fetchall()
        return [dict(r) for r in rows]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hex_to_color(hex_str: str) -> discord.Color:
    hex_str = (hex_str or "").strip().lstrip("#")
    try:
        return discord.Color(int(hex_str, 16))
    except (ValueError, TypeError):
        return discord.Color.blurple()


def _pnw_color_to_hex(color_name: str) -> str:
    mapping = {
        "beige": "#d4b483", "gray": "#808080", "white": "#f0f0f0",
        "black": "#1a1a1a", "red": "#cc0000", "orange": "#ff8800",
        "yellow": "#ffcc00", "green": "#00aa00", "lime": "#88cc00",
        "blue": "#0055cc", "aqua": "#00aacc", "purple": "#8800cc",
        "maroon": "#880000", "brown": "#8b4513", "pink": "#ff69b4",
        "olive": "#808000",
    }
    return mapping.get((color_name or "").lower(), "#5865f2")


def _safe_channel_name(text: str, max_len: int = 80) -> str:
    """Lowercase, replace spaces/special chars with hyphens, trim to max_len."""
    name = text.lower().strip()
    name = re.sub(r"[^a-z0-9\-]", "-", name)
    name = re.sub(r"-{2,}", "-", name).strip("-")
    return name[:max_len]


def _member_channel_name(nation_name: str, city_count: int) -> str:
    """Format: c{cities}-{nation-name}"""
    return _safe_channel_name(f"c{city_count}-{nation_name}")


async def _lookup_nation(identifier: str) -> Optional[dict]:
    q = create_v3_query_instance(api_key=PANDW_API_V3_KEY, logger=logger)
    identifier = identifier.strip()
    if identifier.isdigit():
        return await q.get_nation_by_id(identifier)
    return await q.get_nation_by_name(identifier)


async def _lookup_alliance(identifier: str) -> Optional[dict]:
    q = create_v3_query_instance(api_key=PANDW_API_V3_KEY, logger=logger)
    return await q.resolve_alliance(identifier.strip())


async def _send_show_in_channel(
    channel: discord.TextChannel,
    nation: dict,
    applicant_id: int,
    bot: commands.Bot,
) -> None:
    """
    Run the full /show output (embed + NationSearchView) for a nation
    and post it directly into the given channel.
    """
    try:
        from Systems.PnW.IA.show import ShowCog, NationSearchView

        show_cog: Optional[ShowCog] = bot.cogs.get("ShowCog")  # type: ignore
        if show_cog is None:
            # Fallback: instantiate a temporary one (no caching benefits but works)
            show_cog = ShowCog(bot)

        embed = await show_cog.create_comprehensive_nation_embed(nation)
        view = NationSearchView(applicant_id, bot, show_cog, nation)
        await channel.send(embed=embed, view=view)
    except Exception as e:
        logger.error(f"_send_show_in_channel failed: {e}", exc_info=True)
        # Fallback to the simple embed so the ticket still works
        await channel.send(embed=_build_nation_embed(nation, None))


def _alliance_channel_name(alliance_name: str, acronym: str) -> str:
    """
    Return a safe Discord channel name for an alliance.
    If the name is >10 chars, prefer the in-game acronym (if present),
    otherwise derive initials from the name words.
    """
    if len(alliance_name) <= 10:
        return _safe_channel_name(alliance_name)

    # Use the PnW acronym if it's short enough and non-empty
    if acronym and len(acronym) <= 10:
        return _safe_channel_name(acronym)

    # Derive initials from each word
    initials = "".join(w[0] for w in alliance_name.split() if w)
    return _safe_channel_name(initials) or _safe_channel_name(alliance_name[:10])


async def _send_alliance_in_channel(
    channel: discord.TextChannel,
    alliance_id: str,
    alliance_name: str,
    applicant_id: int,
    bot: commands.Bot,
) -> None:
    """
    Run the full /alliance output (AllianceTotalsView embed + interactive view)
    and post it directly into the given channel.
    """
    try:
        from Systems.PnW.IA.alliance import AllianceManager, AllianceTotalsView
        from Systems.Functions.irs_nations_db import IRSNationsDB
        from Systems.Functions.db_paths import IRS_NATIONS_DB
        from Systems.Functions.config import PANDW_API_KEY
        from Systems.PnW.Util.query import create_v3_query_instance
        from Systems.PnW.Util.calc import AllianceCalculator

        loading_msg = await channel.send("🔄 Loading Alliance Data...")

        alliance_cog: Optional[AllianceManager] = bot.cogs.get("AllianceManager")  # type: ignore

        if alliance_cog is not None:
            query_instance = alliance_cog.query_system
            calc_instance  = alliance_cog.calc_system
        else:
            _logger = logging.getLogger(__name__)
            query_instance = create_v3_query_instance(api_key=PANDW_API_KEY, logger=_logger)
            calc_instance  = AllianceCalculator(query_instance)

        # Fetch nations for the alliance
        NW_ALLIANCE_ID_STR = "10259"
        if str(alliance_id) == NW_ALLIANCE_ID_STR:
            try:
                from PnWHarvester.db.global_nations_db import GlobalNationsDB
                from Systems.Functions.db_paths import GLOBAL_NATIONS_DB as _GNDB, NW_ALLIANCE_ID
                db = GlobalNationsDB(str(_GNDB))
                nations = await db.get_nations_by_alliance(NW_ALLIANCE_ID)
                for n in nations:
                    n["cities"] = await db.get_cities_for_nation(int(n["id"]))
            except Exception:
                nations = await query_instance.get_alliance_nations(alliance_id, force_refresh=False) or []
        else:
            nations = await query_instance.get_alliance_nations(alliance_id, force_refresh=False) or []

        if not nations:
            await loading_msg.edit(content="❌ No alliance data available.")
            return

        view = AllianceTotalsView(
            author_id=applicant_id,
            bot=bot,
            query_instance=query_instance,
            calc_instance=calc_instance,
            nations=nations,
            target_alliance_id=str(alliance_id),
            target_alliance_name=alliance_name,
        )
        embed = await view.generate_alliance_totals_embed(nations)
        await loading_msg.edit(content=None, embed=embed, view=view)

    except Exception as e:
        logger.error(f"_send_alliance_in_channel failed: {e}", exc_info=True)
        await channel.send("⚠️ Could not load full alliance data.")


# ── Modals ────────────────────────────────────────────────────────────────────

class MembershipModal(discord.ui.Modal, title="Membership Application"):
    nation_input = discord.ui.TextInput(
        label="Nation Name or ID",
        placeholder="e.g. 'Reaperland' or '123456'",
        required=True,
        max_length=100,
    )

    def __init__(self, cog: "TicketsCog"):
        super().__init__(timeout=300)
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        identifier = self.nation_input.value.strip()

        nation = await _lookup_nation(identifier)
        if not nation:
            await interaction.followup.send(
                f"❌ Could not find a nation matching **{identifier}**. "
                "Check the name/ID and try again.",
                ephemeral=True,
            )
            return

        nation_name = nation.get("nation_name") or identifier
        city_count  = int(nation.get("num_cities") or 0)
        nation_id   = nation.get("id")
        channel_name = _member_channel_name(nation_name, city_count)

        channel = await self.cog._create_ticket_channel(
            interaction.guild,
            interaction.user,
            channel_name=channel_name,
            ticket_type="membership",
        )
        if not channel:
            await interaction.followup.send("❌ Failed to create ticket channel.", ephemeral=True)
            return

        # Save to DB
        self.cog.db.upsert(
            channel_id=channel.id,
            guild_id=interaction.guild.id,
            applicant_id=interaction.user.id,
            ticket_type="membership",
            status="open",
            channel_name=channel_name,
            subject=nation_name,
            nation_id=int(nation_id) if nation_id else None,
            city_count=city_count,
        )

        # Opening message
        await channel.send(
            content=f"{interaction.user.mention} — your membership ticket has been opened."
        )

        # Run the full /show output for this nation
        await _send_show_in_channel(channel, nation, interaction.user.id, self.cog.bot)

        await interaction.followup.send(
            f"✅ Ticket created: {channel.mention}", ephemeral=True
        )


class EmbassyModal(discord.ui.Modal, title="Embassy Application"):
    alliance_input = discord.ui.TextInput(
        label="Alliance Name or ID",
        placeholder="e.g. 'Rose' or '7452'",
        required=True,
        max_length=100,
    )

    def __init__(self, cog: "TicketsCog"):
        super().__init__(timeout=300)
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        identifier = self.alliance_input.value.strip()

        alliance = await _lookup_alliance(identifier)
        if not alliance:
            await interaction.followup.send(
                f"❌ Could not find an alliance matching **{identifier}**. "
                "Check the name/ID and try again.",
                ephemeral=True,
            )
            return

        alliance_name = alliance.get("name") or identifier
        alliance_id   = alliance.get("id")
        acronym       = alliance.get("acronym") or ""
        pnw_color     = alliance.get("color", "")
        color_hex     = _pnw_color_to_hex(pnw_color)
        channel_name  = _alliance_channel_name(alliance_name, acronym)

        channel = await self.cog._create_ticket_channel(
            interaction.guild,
            interaction.user,
            channel_name=channel_name,
            ticket_type="embassy",
        )
        if not channel:
            await interaction.followup.send("❌ Failed to create ticket channel.", ephemeral=True)
            return

        # Save to DB
        self.cog.db.upsert(
            channel_id=channel.id,
            guild_id=interaction.guild.id,
            applicant_id=interaction.user.id,
            ticket_type="embassy",
            status="open",
            channel_name=channel_name,
            subject=alliance_name,
            alliance_id=int(alliance_id) if alliance_id else None,
            color_hex=color_hex,
        )

        # Opening message
        await channel.send(
            content=f"{interaction.user.mention} — your embassy ticket has been opened."
        )

        # Run the full /alliance output for this alliance
        await _send_alliance_in_channel(
            channel,
            alliance_id=str(alliance_id) if alliance_id else identifier,
            alliance_name=alliance_name,
            applicant_id=interaction.user.id,
            bot=self.cog.bot,
        )

        await interaction.followup.send(
            f"✅ Ticket created: {channel.mention}", ephemeral=True
        )


# ── Embed builders ────────────────────────────────────────────────────────────

def _build_nation_embed(nation: dict, applicant: Optional[discord.Member]) -> discord.Embed:
    name   = nation.get("nation_name", "Unknown")
    leader = nation.get("leader_name", "Unknown")
    nid    = nation.get("id", "?")
    score  = nation.get("score", 0)
    cities = nation.get("num_cities", 0)
    flag   = nation.get("flag") or ""
    url    = f"{PNW_BASE}/nation/id={nid}"

    embed = discord.Embed(
        title=f"🏳️ Membership Application — {name}",
        url=url,
        color=discord.Color.gold(),
    )
    embed.add_field(name="Nation",    value=f"[{name}]({url})", inline=True)
    embed.add_field(name="Leader",    value=leader,             inline=True)
    embed.add_field(name="Cities",    value=str(cities),        inline=True)
    embed.add_field(name="Score",     value=f"{score:,.2f}",    inline=True)
    embed.add_field(name="Nation ID", value=str(nid),           inline=True)
    embed.set_author(name=str(applicant), icon_url=applicant.display_avatar.url if applicant else None)
    if flag:
        embed.set_thumbnail(url=flag)
    embed.set_footer(text="Use /verify to accept or reject this ticket.")
    return embed


def _build_alliance_embed(alliance: dict, applicant: discord.Member) -> discord.Embed:
    name    = alliance.get("name", "Unknown")
    acronym = alliance.get("acronym", "")
    aid     = alliance.get("id", "?")
    color   = alliance.get("color", "")
    url     = f"{PNW_BASE}/alliance/id={aid}"

    embed = discord.Embed(
        title=f"🏛️ Embassy Application — {name}",
        url=url,
        color=_hex_to_color(_pnw_color_to_hex(color)),
    )
    embed.add_field(name="Alliance",    value=f"[{name}]({url})", inline=True)
    if acronym:
        embed.add_field(name="Acronym", value=acronym,            inline=True)
    embed.add_field(name="Alliance ID", value=str(aid),           inline=True)
    embed.add_field(name="PnW Color",   value=color.capitalize() if color else "N/A", inline=True)
    embed.set_author(name=str(applicant), icon_url=applicant.display_avatar.url)
    embed.set_footer(text="Use /verify to accept or reject this ticket.")
    return embed


# ── Persistent Views ──────────────────────────────────────────────────────────

class TicketTypeView(discord.ui.View):
    """Buttons in the #info channel — persistent across restarts."""

    def __init__(self, cog: "TicketsCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="📋 Membership",
        style=discord.ButtonStyle.primary,
        custom_id="ticket:membership",
    )
    async def membership_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MembershipModal(self.cog))

    @discord.ui.button(
        label="🏛️ Embassy",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket:embassy",
    )
    async def embassy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbassyModal(self.cog))


# ── Main Cog ──────────────────────────────────────────────────────────────────

class TicketsCog(commands.Cog):
    """IRS Ticket System."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db  = TicketsDB()
        bot.add_view(TicketTypeView(self))

    # ── /info ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="info", description="Post the IRS welcome & ticket embed.")
    async def info_command(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        channel = interaction.guild.get_channel(INFO_CHANNEL_ID)
        if not channel:
            await interaction.followup.send("❌ Info channel not found.", ephemeral=True)
            return

        embed = discord.Embed(
            title="⭐ Welcome to Darkstar",
            description=(
                "**Darkstar** is the official Discord server for our "
                "Politics & War alliance.\n\n"
                "To receive your roles you must open a ticket below:\n\n"
                "📋 **Membership** — for nations wishing to join Darkstar\n"
                "🏛️ **Embassy** — for alliances wishing to establish diplomatic relations\n\n"
                "Click the appropriate button below to get started. "
                "A staff member will review your application shortly."
            ),
            color=discord.Color.dark_red(),
        )
        embed.set_footer(text="Darkstar")

        await channel.send(embed=embed, view=TicketTypeView(self))
        await interaction.followup.send(f"✅ Info embed posted in {channel.mention}.", ephemeral=True)

    # ── /verify ───────────────────────────────────────────────────────────────

    @app_commands.command(name="verify", description="Accept or reject the current ticket.")
    @app_commands.describe(action="Accept or Reject this ticket")
    @app_commands.choices(action=[
        app_commands.Choice(name="Accept", value="accept"),
        app_commands.Choice(name="Reject", value="reject"),
    ])
    async def verify_command(self, interaction: discord.Interaction, action: str):
        await interaction.response.defer(ephemeral=True)

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("❌ Run this inside a ticket channel.", ephemeral=True)
            return

        record = self.db.get(channel.id)
        if not record:
            await interaction.followup.send(
                "❌ This channel isn't tracked as a ticket. "
                "Make sure you're inside a ticket channel.",
                ephemeral=True,
            )
            return

        if record["status"] != "open":
            await interaction.followup.send(
                f"❌ This ticket is already **{record['status']}**.", ephemeral=True
            )
            return

        applicant = interaction.guild.get_member(record["applicant_id"])

        if action == "reject":
            await self._reject_ticket(interaction, channel, applicant, record)
        else:
            await self._accept_ticket(interaction, channel, applicant, record)

    # ── /delete_ticket ────────────────────────────────────────────────────────

    @app_commands.command(name="delete_ticket", description="Delete a ticket by name.")
    @app_commands.describe(ticket="The ticket to delete (type to search)")
    async def delete_ticket_command(self, interaction: discord.Interaction, ticket: str):
        await interaction.response.defer(ephemeral=True)

        # ticket value is the channel_id stored as string in autocomplete
        try:
            channel_id = int(ticket)
        except ValueError:
            await interaction.followup.send("❌ Invalid ticket selection.", ephemeral=True)
            return

        record = self.db.get(channel_id)
        if not record:
            await interaction.followup.send("❌ Ticket not found in database.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(channel_id)
        if channel:
            try:
                await channel.delete(reason=f"Manually deleted by {interaction.user}")
            except discord.HTTPException as e:
                logger.error(f"Failed to delete ticket channel {channel_id}: {e}")
                await interaction.followup.send(f"⚠️ Could not delete channel: {e}", ephemeral=True)
                return

        self.db.delete(channel_id)
        await interaction.followup.send(
            f"🗑️ Ticket **{record['channel_name']}** deleted.", ephemeral=True
        )

    @delete_ticket_command.autocomplete("ticket")
    async def _delete_ticket_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        tickets = self.db.list_all(interaction.guild_id)
        choices = []
        for t in tickets:
            label = f"[{t['status'].upper()}] {t['channel_name']} ({t['ticket_type']})"
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label[:100], value=str(t["channel_id"])))
            if len(choices) == 25:
                break
        return choices

    # ── /resort_members ───────────────────────────────────────────────────────

    @app_commands.command(
        name="resort_members",
        description="Re-query PnW and rename all open membership tickets with updated city count & nation name.",
    )
    async def resort_members_command(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        open_members = self.db.list_member_open(interaction.guild_id)
        if not open_members:
            await interaction.followup.send("ℹ️ No open membership tickets to update.", ephemeral=True)
            return

        updated = 0
        skipped = 0
        errors  = 0

        for record in open_members:
            nation_id = record.get("nation_id")
            if not nation_id:
                skipped += 1
                continue

            try:
                nation = await _lookup_nation(str(nation_id))
                if not nation:
                    skipped += 1
                    continue

                nation_name = nation.get("nation_name") or record["subject"]
                city_count  = int(nation.get("num_cities") or 0)
                new_name    = _member_channel_name(nation_name, city_count)

                channel = interaction.guild.get_channel(record["channel_id"])
                if channel and channel.name != new_name:
                    await channel.edit(name=new_name, reason="resort_members refresh")
                    self.db.update_channel_name(record["channel_id"], new_name)
                    # Also update subject + city_count in DB
                    self.db.upsert(
                        channel_id=record["channel_id"],
                        guild_id=record["guild_id"],
                        applicant_id=record["applicant_id"],
                        ticket_type=record["ticket_type"],
                        status=record["status"],
                        channel_name=new_name,
                        subject=nation_name,
                        nation_id=nation_id,
                        city_count=city_count,
                    )
                    updated += 1
                else:
                    skipped += 1

                # Avoid hitting Discord rate limits
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"resort_members error for nation {nation_id}: {e}")
                errors += 1

        await interaction.followup.send(
            f"✅ Resort complete — **{updated}** renamed, **{skipped}** unchanged, **{errors}** errors.",
            ephemeral=True,
        )


    # ── /ticket_role ──────────────────────────────────────────────────────────

    ticket_role = app_commands.Group(
        name="ticket_role",
        description="Manage roles that are added to every new ticket channel.",
    )

    @ticket_role.command(name="add", description="Add a role to all new ticket channels.")
    @app_commands.describe(role="The role to add", label="Friendly label (e.g. 'Staff')")
    async def ticket_role_add(
        self, interaction: discord.Interaction, role: discord.Role, label: str = ""
    ):
        await interaction.response.defer(ephemeral=True)
        friendly = label.strip() or role.name
        added = self.db.add_ticket_role(interaction.guild_id, role.id, friendly)
        if added:
            await interaction.followup.send(
                f"✅ {role.mention} (`{friendly}`) will now be added to all new ticket channels.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"⚠️ {role.mention} is already in the ticket roles list.", ephemeral=True
            )

    @ticket_role.command(name="remove", description="Remove a role from new ticket channels.")
    @app_commands.describe(role_id="The role to remove (type to search)")
    async def ticket_role_remove(self, interaction: discord.Interaction, role_id: str):
        await interaction.response.defer(ephemeral=True)
        try:
            rid = int(role_id)
        except ValueError:
            await interaction.followup.send("❌ Invalid role selection.", ephemeral=True)
            return
        removed = self.db.remove_ticket_role(interaction.guild_id, rid)
        if removed:
            role = interaction.guild.get_role(rid)
            name = role.mention if role else f"<@&{rid}>"
            await interaction.followup.send(
                f"🗑️ {name} removed from ticket roles.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "❌ That role wasn't in the ticket roles list.", ephemeral=True
            )

    @ticket_role_remove.autocomplete("role_id")
    async def _ticket_role_remove_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        rows = self.db.list_ticket_roles(interaction.guild_id)
        choices = []
        for r in rows:
            role = interaction.guild.get_role(r["role_id"])
            display = f"{r['label']} ({role.name if role else 'deleted role'})"
            if current.lower() in display.lower():
                choices.append(app_commands.Choice(name=display[:100], value=str(r["role_id"])))
            if len(choices) == 25:
                break
        return choices

    @ticket_role.command(name="list", description="List all roles added to new ticket channels.")
    async def ticket_role_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        rows = self.db.list_ticket_roles(interaction.guild_id)
        if not rows:
            await interaction.followup.send(
                "ℹ️ No ticket roles configured yet. Use `/ticket_role add` to add one.",
                ephemeral=True,
            )
            return
        lines = []
        for r in rows:
            role = interaction.guild.get_role(r["role_id"])
            mention = role.mention if role else f"~~<@&{r['role_id']}> (deleted)~~"
            lines.append(f"• {mention} — `{r['label']}`")
        embed = discord.Embed(
            title="🎭 Ticket Roles",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="These roles can see and talk in every new ticket channel.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _create_ticket_channel(
        self,
        guild: discord.Guild,
        applicant: discord.Member,
        channel_name: str,
        ticket_type: str,
    ) -> Optional[discord.TextChannel]:
        category = guild.get_channel(TICKET_CATEGORY_ID)
        if not category or not isinstance(category, discord.CategoryChannel):
            logger.error(f"Ticket category {TICKET_CATEGORY_ID} not found.")
            return None

        # Full set of perms the applicant needs to use the ticket
        applicant_overwrite = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
            use_application_commands=True,
        )

        overwrites: dict = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            applicant: applicant_overwrite,
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True,
                read_message_history=True,
                embed_links=True,
                attach_files=True,
            ),
        }

        # Add any configured ticket roles (read/write access)
        staff_overwrite = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_messages=True,
            embed_links=True,
            attach_files=True,
        )
        for row in self.db.list_ticket_roles(guild.id):
            role = guild.get_role(row["role_id"])
            if role:
                overwrites[role] = staff_overwrite

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Ticket opened by {applicant} ({ticket_type})",
            )
            # Explicitly break category sync so our overwrites are authoritative
            await channel.edit(sync_permissions=False)
            return channel
        except discord.HTTPException as e:
            logger.error(f"Failed to create ticket channel '{channel_name}': {e}")
            return None

    async def _reject_ticket(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        applicant: Optional[discord.Member],
        record: dict,
    ):
        mention = applicant.mention if applicant else "Applicant"
        try:
            await channel.send(
                f"❌ {mention} — your ticket has been **rejected** by "
                f"{interaction.user.mention}. This channel will be deleted shortly."
            )
        except Exception:
            pass

        self.db.set_status(channel.id, "rejected")
        await interaction.followup.send("🗑️ Ticket rejected — deleting in 5s.", ephemeral=True)
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Ticket rejected by {interaction.user}")
        except discord.HTTPException as e:
            logger.error(f"Failed to delete rejected ticket: {e}")
        self.db.delete(channel.id)

    async def _accept_ticket(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        applicant: Optional[discord.Member],
        record: dict,
    ):
        if record["ticket_type"] == "membership":
            await self._accept_membership(interaction, channel, applicant, record)
        else:
            await self._accept_embassy(interaction, channel, applicant, record)

    async def _accept_membership(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        applicant: Optional[discord.Member],
        record: dict,
    ):
        guild = interaction.guild

        # Give Member role
        if applicant:
            member_role = guild.get_role(MEMBER_ROLE_ID)
            if member_role:
                try:
                    await applicant.add_roles(member_role, reason="Membership ticket accepted")
                except discord.HTTPException as e:
                    logger.error(f"Failed to assign Member role: {e}")
                    await interaction.followup.send(f"⚠️ Could not assign Member role: {e}", ephemeral=True)
                    return

        # Move to accepted category AND lock permissions so only the applicant
        # (+ bot + ticket roles) can see it — not every other member.
        accepted_cat = guild.get_channel(MEMBER_ACCEPTED_CAT)
        if accepted_cat and isinstance(accepted_cat, discord.CategoryChannel):
            try:
                # Build explicit overwrites that survive the category move
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    guild.me: discord.PermissionOverwrite(
                        view_channel=True, send_messages=True, manage_channels=True,
                        manage_messages=True, read_message_history=True,
                        embed_links=True, attach_files=True,
                    ),
                }
                if applicant:
                    overwrites[applicant] = discord.PermissionOverwrite(
                        view_channel=True, send_messages=True,
                        read_message_history=True, attach_files=True,
                        embed_links=True, use_application_commands=True,
                    )
                # Re-add ticket roles
                staff_ow = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True,
                    read_message_history=True, manage_messages=True,
                    embed_links=True, attach_files=True,
                )
                for row in self.db.list_ticket_roles(guild.id):
                    role = guild.get_role(row["role_id"])
                    if role:
                        overwrites[role] = staff_ow

                await channel.edit(
                    category=accepted_cat,
                    overwrites=overwrites,
                    sync_permissions=False,
                    reason="Membership accepted",
                )
            except discord.HTTPException as e:
                logger.error(f"Failed to move membership ticket: {e}")

        self.db.set_status(channel.id, "accepted")
        mention = applicant.mention if applicant else "Applicant"
        await channel.send(
            f"✅ {mention} — your membership has been **accepted** by "
            f"{interaction.user.mention}! Welcome to IRS! 🏴‍☠️"
        )
        await interaction.followup.send("✅ Membership accepted.", ephemeral=True)

    async def _accept_embassy(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        applicant: Optional[discord.Member],
        record: dict,
    ):
        guild         = interaction.guild
        alliance_name = record["subject"]
        color_hex     = record.get("color_hex") or "#5865f2"

        # Create or find the alliance role
        alliance_role = await self._get_or_create_alliance_role(guild, alliance_name, color_hex)

        # Assign alliance role + Diplomat role to the applicant
        if applicant:
            roles_to_add = [r for r in [alliance_role, guild.get_role(DIPLOMAT_ROLE_ID)] if r]
            if roles_to_add:
                try:
                    await applicant.add_roles(*roles_to_add, reason="Embassy ticket accepted")
                except discord.HTTPException as e:
                    logger.error(f"Failed to assign embassy roles: {e}")
                    await interaction.followup.send(f"⚠️ Could not assign roles: {e}", ephemeral=True)
                    return

        # Move to accepted category with explicit overwrites so:
        #   - @everyone cannot see it
        #   - the applicant can still see it
        #   - the alliance role can see it (so the whole alliance can use the channel)
        #   - ticket roles (staff) can see it
        accepted_cat = guild.get_channel(EMBASSY_ACCEPTED_CAT)
        if accepted_cat and isinstance(accepted_cat, discord.CategoryChannel):
            try:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    guild.me: discord.PermissionOverwrite(
                        view_channel=True, send_messages=True, manage_channels=True,
                        manage_messages=True, read_message_history=True,
                        embed_links=True, attach_files=True,
                    ),
                }
                if applicant:
                    overwrites[applicant] = discord.PermissionOverwrite(
                        view_channel=True, send_messages=True,
                        read_message_history=True, attach_files=True,
                        embed_links=True, use_application_commands=True,
                    )
                # Alliance role — everyone with this role can see the embassy channel
                if alliance_role:
                    overwrites[alliance_role] = discord.PermissionOverwrite(
                        view_channel=True, send_messages=True,
                        read_message_history=True, attach_files=True,
                        embed_links=True, use_application_commands=True,
                    )
                # Staff ticket roles
                staff_ow = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True,
                    read_message_history=True, manage_messages=True,
                    embed_links=True, attach_files=True,
                )
                for row in self.db.list_ticket_roles(guild.id):
                    role = guild.get_role(row["role_id"])
                    if role:
                        overwrites[role] = staff_ow

                await channel.edit(
                    category=accepted_cat,
                    overwrites=overwrites,
                    sync_permissions=False,
                    reason="Embassy accepted",
                )
            except discord.HTTPException as e:
                logger.error(f"Failed to move embassy ticket: {e}")

        self.db.set_status(channel.id, "accepted")

        diplomat_role = guild.get_role(DIPLOMAT_ROLE_ID)
        role_mentions = " ".join(
            r.mention for r in [alliance_role, diplomat_role] if r
        )
        mention = applicant.mention if applicant else "Applicant"
        await channel.send(
            f"✅ {mention} — your embassy has been **accepted** by "
            f"{interaction.user.mention}! You've been given the {role_mentions} role(s). 🏛️"
        )
        await interaction.followup.send("✅ Embassy accepted.", ephemeral=True)

    async def _get_or_create_alliance_role(
        self, guild: discord.Guild, name: str, color_hex: str
    ) -> Optional[discord.Role]:
        existing = discord.utils.get(guild.roles, name=name)
        if existing:
            return existing
        try:
            return await guild.create_role(
                name=name,
                color=_hex_to_color(color_hex),
                reason=f"Embassy role for {name}",
            )
        except discord.HTTPException as e:
            logger.error(f"Failed to create alliance role '{name}': {e}")
            return None

    # ── Welcome new members ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild.id != GUILD_ID:
            return

        ticket_channel = member.guild.get_channel(INFO_CHANNEL_ID)  # 1445703670057537700

        # <#channel_id> syntax renders as a clickable channel link inside embeds.
        # member.mention renders correctly in the plain `content` field (triggers the ping).
        # Inside embed description it shows the name visually but does NOT ping — that's fine,
        # the actual ping lives in `content` below.
        ticket_link  = f"<#{INFO_CHANNEL_ID}>"
        botspam_link = "<#1498353294127534141>"

        embed = discord.Embed(
            title=f"⭐  Welcome to Darkstar, {member.display_name}.",
            description=(
                f"Congratulations {member.mention} — you've found your way to **Darkstar**.\n"
                "Whether you wandered in by accident or actually meant to be here, you're stuck with us now.\n\n"

                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

                f"📋 **Tickets & Membership**\n"
                f"Head over to {ticket_link} to open an **Embassy** or **Membership** ticket.\n"
                "Want to join Darkstar? Membership ticket. Representing another alliance? Embassy ticket.\n"
                "Don't know what you want? Open both and figure it out.\n\n"

                f"🤖 **Bot Spam**\n"
                f"All your bot commands, gambling addictions, and general degeneracy belong in {botspam_link}.\n"
                "Spam your slash commands in any other channel and you will be judged. Harshly.\n\n"

                "🌐 **Website**\n"
                "Check out our corner of the internet at <https://reaper.qzz.io> — "
                "yes, it's real, yes it works, no we're not sorry about the name.\n\n"

                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

                "⚠️ **A Word on the Perimeter**\n"
                "We have one rule that is non-negotiable, carved in stone, blessed by the ancients:\n\n"
                "**Fornication with the perimeter will not be tolerated under any circumstance.**\n\n"
                "We don't care who you are, how many cities you have, or how long you've been in the game — "
                "you do NOT mess with the perimeter. Don't fuck around, because you **will** find out. 🔫\n\n"

                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "Now get in there, open a ticket, and make yourself useful. 🌙"
            ),
            color=discord.Color.dark_red(),
        )
        embed.set_footer(text="Darkstar  •  You've been warned.")
        if member.guild.icon:
            embed.set_thumbnail(url=member.guild.icon.url)

        # content pings the user (renders the mention + triggers notification).
        # The embed title/description uses display_name so it reads naturally.
        if ticket_channel:
            try:
                await ticket_channel.send(
                    content=f"👀 Everyone look — {member.mention} just walked in.",
                    embed=embed,
                )
            except discord.HTTPException as e:
                logger.error(f"Failed to send welcome message for {member}: {e}")


# ── Setup ─────────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsCog(bot))
    logger.info("TicketsCog loaded")

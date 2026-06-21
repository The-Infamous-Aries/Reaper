"""
Ticket System — Per-server ticket management for Politics & War.

Commands:
    /info                  — Set up tickets for this server (embed + buttons)
    /make_categories       — Create pending/accepted categories + sort sub-categories
    /link_ticket           — Manually create a ticket + verify user in Verified.db
    /join_message_config   — Configure the join welcome message
    /ticket_roles make     — Auto-create Applicant/Member/Diplomat/Raider/Farmer roles
    /ticket_roles link     — Link existing roles to the ticket system
    /ticket_roles list     — Show currently linked ticket roles
    /ticket_add add/remove/list — Manage staff roles in ticket channels
    /ticket_audit set/remove/view — Manage the audit log channel
    /verify                — Accept or Reject the current ticket (staff)
    /close_ticket          — Request closure of your own ticket (user)
    /delete_ticket         — Delete a ticket by name (autocomplete from DB)
    /resort_members        — Re-query PnW and rename all open member tickets
    /view_config           — View current guild ticket configuration
    /ticket_admin_grant    — Aries: grant TICKET_ADMIN to a user
    /ticket_admin_revoke   — Aries: revoke TICKET_ADMIN from a user
"""

from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from Systems.Functions.config import ARIES_USER_ID, PANDW_API_V3_KEY
from Systems.Functions.db_paths import TICKETS_DB
from Systems.PnW.Util.query import create_v3_query_instance
from Systems.Functions.autocomplete_utils import nation_autocomplete, alliance_autocomplete

# ShowCog is imported lazily inside the modal to avoid circular imports

logger = logging.getLogger(__name__)

PNW_BASE = "https://politicsandwar.com"


# ── DB Layer ──────────────────────────────────────────────────────────────────

class TicketsDB:
    """SQLite store for all ticket records — thread-safe via Lock."""

    def __init__(self, path: Path = TICKETS_DB):
        self.path = str(path)
        self._lock = threading.Lock()
        self._init()

    def _init(self):
        with self._lock:
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
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS ticket_admins (
                        user_id      INTEGER PRIMARY KEY,
                        username     TEXT,
                        display_name TEXT,
                        granted_by   INTEGER NOT NULL,
                        granted_at   TEXT    NOT NULL,
                        updated_at   TEXT    NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS ticket_admin_history (
                        id           INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id      INTEGER NOT NULL,
                        username     TEXT,
                        action       TEXT    NOT NULL,
                        actor_id     INTEGER NOT NULL,
                        created_at   TEXT    NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS guild_config (
                        guild_id                INTEGER PRIMARY KEY,
                        info_channel_id         INTEGER,
                        alliance_name           TEXT,
                        alliance_id             INTEGER,
                        ticket_category_id      INTEGER,
                        member_accepted_cat_id  INTEGER,
                        embassy_accepted_cat_id INTEGER,
                        applicant_role_id       INTEGER,
                        member_role_id          INTEGER,
                        diplomat_role_id        INTEGER,
                        sort_type               TEXT,
                        raider_role_id          INTEGER,
                        farmer_role_id          INTEGER,
                        join_message_type       TEXT    DEFAULT 'original',
                        join_message_custom     TEXT,
                        join_alliance_name      TEXT,
                        join_alliance_id        INTEGER,
                        created_at              TEXT NOT NULL,
                        updated_at              TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sort_categories (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        guild_id    INTEGER NOT NULL,
                        label       TEXT    NOT NULL,
                        channel_id  INTEGER NOT NULL,
                        sort_order  INTEGER NOT NULL DEFAULT 0,
                        UNIQUE(guild_id, label),
                        UNIQUE(guild_id, channel_id)
                    )
                """)
                # Migrate existing guild_config — add columns that may not exist
                for col_sql in [
                    "sort_type TEXT",
                    "raider_role_id INTEGER",
                    "farmer_role_id INTEGER",
                    "join_message_type TEXT DEFAULT 'original'",
                    "join_message_custom TEXT",
                    "join_alliance_name TEXT",
                    "join_alliance_id INTEGER",
                    "pending_members_cat_id INTEGER",
                    "pending_diplomats_cat_id INTEGER",
                    "audit_channel_id INTEGER",
                    "applicant_role_id INTEGER",
                ]:
                    try:
                        conn.execute(f"ALTER TABLE guild_config ADD COLUMN {col_sql}")
                    except sqlite3.OperationalError:
                        pass
                try:
                    conn.execute("ALTER TABLE tickets ADD COLUMN member_type TEXT")
                except sqlite3.OperationalError:
                    pass
                try:
                    conn.execute("ALTER TABLE tickets ADD COLUMN resolved_by INTEGER")
                except sqlite3.OperationalError:
                    pass
                try:
                    conn.execute("ALTER TABLE tickets ADD COLUMN resolved_at TEXT")
                except sqlite3.OperationalError:
                    pass
                # Index for fast lookups by guild + status
                try:
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_guild_status ON tickets(guild_id, status)")
                except sqlite3.OperationalError:
                    pass
                conn.commit()

    # ── writes ────────────────────────────────────────────────────────────────

    def upsert(self, **kwargs):
        now = datetime.now(timezone.utc).isoformat()
        kwargs.setdefault("created_at", now)
        kwargs["updated_at"] = now
        cols = ", ".join(kwargs.keys())
        placeholders = ", ".join("?" * len(kwargs))
        updates = ", ".join(f"{k}=excluded.{k}" for k in kwargs if k != "channel_id")
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                conn.execute(
                    f"INSERT INTO tickets ({cols}) VALUES ({placeholders}) "
                    f"ON CONFLICT(channel_id) DO UPDATE SET {updates}",
                    list(kwargs.values()),
                )
                conn.commit()

    def set_status(self, channel_id: int, status: str):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                conn.execute(
                    "UPDATE tickets SET status=?, updated_at=? WHERE channel_id=?",
                    (status, now, channel_id),
                )
                conn.commit()

    def set_resolved(self, channel_id: int, resolved_by: int, status: str):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                conn.execute(
                    "UPDATE tickets SET status=?, resolved_by=?, resolved_at=?, updated_at=? WHERE channel_id=?",
                    (status, resolved_by, now, now, channel_id),
                )
                conn.commit()

    def update_channel_name(self, channel_id: int, new_name: str):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                conn.execute(
                    "UPDATE tickets SET channel_name=?, updated_at=? WHERE channel_id=?",
                    (new_name, now, channel_id),
                )
                conn.commit()

    def delete(self, channel_id: int):
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                conn.execute("DELETE FROM tickets WHERE channel_id=?", (channel_id,))
                conn.commit()

    # ── reads ─────────────────────────────────────────────────────────────────

    def get(self, channel_id: int) -> Optional[dict]:
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM tickets WHERE channel_id=?", (channel_id,)
                ).fetchone()
        return dict(row) if row else None

    def list_open(self, guild_id: int) -> List[dict]:
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM tickets WHERE guild_id=? AND status='open' ORDER BY created_at DESC",
                    (guild_id,),
                ).fetchall()
        return [dict(r) for r in rows]

    def list_member_open(self, guild_id: int) -> List[dict]:
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM tickets WHERE guild_id=? AND ticket_type='membership' AND status='open'",
                    (guild_id,),
                ).fetchall()
        return [dict(r) for r in rows]

    def list_all(self, guild_id: int) -> List[dict]:
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM tickets WHERE guild_id=? ORDER BY created_at DESC",
                    (guild_id,),
                ).fetchall()
        return [dict(r) for r in rows]

    def has_open_ticket(self, guild_id: int, applicant_id: int) -> bool:
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                row = conn.execute(
                    "SELECT 1 FROM tickets WHERE guild_id=? AND applicant_id=? AND status='open' LIMIT 1",
                    (guild_id, applicant_id),
                ).fetchone()
        return row is not None

    # ── ticket_roles ──────────────────────────────────────────────────────────

    def add_ticket_role(self, guild_id: int, role_id: int, label: str) -> bool:
        """Add a role to the ticket roles list. Returns False if already exists."""
        try:
            with self._lock:
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
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                cur = conn.execute(
                    "DELETE FROM ticket_roles WHERE guild_id=? AND role_id=?",
                    (guild_id, role_id),
                )
                conn.commit()
        return cur.rowcount > 0

    def list_ticket_roles(self, guild_id: int) -> List[dict]:
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM ticket_roles WHERE guild_id=? ORDER BY label",
                    (guild_id,),
                ).fetchall()
        return [dict(r) for r in rows]

    # ── ticket_admins ─────────────────────────────────────────────────────────

    def grant_ticket_admin(
        self,
        user_id: int,
        username: str,
        display_name: str,
        granted_by: int,
    ) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                conn.row_factory = sqlite3.Row
                existing = conn.execute(
                    "SELECT granted_at FROM ticket_admins WHERE user_id=?",
                    (int(user_id),),
                ).fetchone()
                granted_at = existing["granted_at"] if existing else now
                conn.execute(
                    """
                    INSERT INTO ticket_admins (
                        user_id, username, display_name, granted_by, granted_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username = excluded.username,
                        display_name = excluded.display_name,
                        granted_by = excluded.granted_by,
                        updated_at = excluded.updated_at
                    """,
                    (int(user_id), username, display_name, int(granted_by), granted_at, now),
                )
                conn.execute(
                    """
                    INSERT INTO ticket_admin_history (
                        user_id, username, action, actor_id, created_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (int(user_id), username, "grant", int(granted_by), now),
                )
                row = conn.execute(
                    "SELECT * FROM ticket_admins WHERE user_id=?",
                    (int(user_id),),
                ).fetchone()
                conn.commit()
        return dict(row)

    def revoke_ticket_admin(self, user_id: int, revoked_by: int) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                conn.row_factory = sqlite3.Row
                existing = conn.execute(
                    "SELECT * FROM ticket_admins WHERE user_id=?",
                    (int(user_id),),
                ).fetchone()
                if not existing:
                    return False
                conn.execute("DELETE FROM ticket_admins WHERE user_id=?", (int(user_id),))
                conn.execute(
                    """
                    INSERT INTO ticket_admin_history (
                        user_id, username, action, actor_id, created_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (int(user_id), existing["username"], "revoke", int(revoked_by), now),
                )
                conn.commit()
        return True

    def is_ticket_admin(self, user_id: int) -> bool:
        if int(user_id) == int(ARIES_USER_ID):
            return True
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                row = conn.execute(
                    "SELECT 1 FROM ticket_admins WHERE user_id=? LIMIT 1",
                    (int(user_id),),
                ).fetchone()
        return row is not None

    # ── guild_config ───────────────────────────────────────────────────────────

    def get_guild_config(self, guild_id: int) -> Optional[dict]:
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM guild_config WHERE guild_id=?",
                    (int(guild_id),),
                ).fetchone()
        return dict(row) if row else None

    def set_guild_config(self, guild_id: int, **kwargs) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        kwargs.setdefault("created_at", now)
        kwargs["updated_at"] = now
        kwargs["guild_id"] = int(guild_id)
        cols = ", ".join(kwargs.keys())
        placeholders = ", ".join("?" * len(kwargs))
        updates = ", ".join(
            f"{k}=excluded.{k}" for k in kwargs if k not in ("guild_id", "created_at")
        )
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                conn.execute(
                    f"INSERT INTO guild_config ({cols}) VALUES ({placeholders}) "
                    f"ON CONFLICT(guild_id) DO UPDATE SET {updates}",
                    list(kwargs.values()),
                )
                conn.commit()
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM guild_config WHERE guild_id=?", (int(guild_id),)
                ).fetchone()
        return dict(row)

    # ── sort_categories ──────────────────────────────────────────────────────

    def set_sort_categories(self, guild_id: int, categories: list) -> list:
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                conn.execute("DELETE FROM sort_categories WHERE guild_id=?", (int(guild_id),))
                for order, (label, channel_id) in enumerate(categories):
                    conn.execute(
                        "INSERT INTO sort_categories (guild_id, label, channel_id, sort_order) "
                        "VALUES (?, ?, ?, ?)",
                        (int(guild_id), label, int(channel_id), order),
                    )
                conn.commit()
        return self.get_sort_categories(guild_id)

    def get_sort_categories(self, guild_id: int) -> list:
        with self._lock:
            with sqlite3.connect(self.path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM sort_categories WHERE guild_id=? ORDER BY sort_order",
                    (int(guild_id),),
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
    name = name[:max_len]
    return name or "ticket"


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
        from Systems.Functions.db_paths import GLOBAL_NATIONS_DB as _GNDB, NW_ALLIANCE_ID
        from Systems.Functions.config import PANDW_API_V3_KEY as PANDW_API_KEY
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
        if str(alliance_id) == str(NW_ALLIANCE_ID):
            try:
                from PnWHarvester.db.global_nations_db import GlobalNationsDB
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
        try:
            await loading_msg.edit(content="⚠️ Could not load full alliance data.")
        except (discord.HTTPException, UnboundLocalError):
            await channel.send("⚠️ Could not load full alliance data.")


# ── Modals ────────────────────────────────────────────────────────────────────

class MembershipModal(discord.ui.Modal, title="Membership Application"):
    nation_input = discord.ui.TextInput(
        label="Nation Name or ID",
        placeholder="e.g. 'Reaperland' or '123456'",
        required=True,
        max_length=100,
    )

    def __init__(self, cog: "TicketsCog", sort_type: Optional[str] = None):
        super().__init__(timeout=300)
        self.cog = cog
        self.sort_type = sort_type
        self.member_type_select: Optional[discord.ui.Select] = None
        if sort_type == "farm_raider":
            self.member_type_select = discord.ui.Select(
                options=[
                    discord.SelectOption(label="Farm", value="farm", description="I am a farmer-type nation"),
                    discord.SelectOption(label="Raider", value="raider", description="I am a raider-type nation"),
                ],
                placeholder="Select your nation type...",
            )
            self.add_item(self.member_type_select)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)
        identifier = self.nation_input.value.strip()

        # Duplicate check
        if self.cog.db.has_open_ticket(interaction.guild_id, interaction.user.id):
            await interaction.followup.send(
                "❌ You already have an open ticket. Please wait for it to be resolved.",
                ephemeral=True,
            )
            return

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
        score       = float(nation.get("score") or 0)
        channel_name = _member_channel_name(nation_name, city_count)

        member_type = None
        if self.sort_type == "farm_raider":
            member_type = self.member_type_select.values[0] if self.member_type_select.values else None

        channel = await self.cog._create_ticket_channel(
            interaction.guild,
            interaction.user,
            channel_name=channel_name,
            ticket_type="membership",
            score=score,
            city_count=city_count,
            member_type=member_type,
        )
        if not channel:
            await interaction.followup.send("❌ Failed to create ticket channel.", ephemeral=True)
            return

        # Save to DB — delete channel if DB write fails (Fix #5)
        try:
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
                member_type=member_type,
            )
        except Exception:
            logger.exception("Failed to upsert ticket record, deleting channel")
            try:
                await channel.delete(reason="DB write failed")
            except discord.HTTPException:
                pass
            await interaction.followup.send("❌ Failed to save ticket. Please try again.", ephemeral=True)
            return

        # Give the Applicants role to the user
        cfg = self.cog._get_config(interaction.guild.id)
        applicant_role_id = cfg.get("applicant_role_id")
        if applicant_role_id and isinstance(interaction.user, discord.Member):
            role = interaction.guild.get_role(int(applicant_role_id))
            if role:
                try:
                    await interaction.user.add_roles(role, reason="Membership ticket created")
                except discord.HTTPException as e:
                    logger.warning(f"Failed to assign Applicants role: {e}")

        # Opening message
        await channel.send(
            content=f"{interaction.user.mention} — your membership ticket has been opened."
        )

        # Run the full /show output for this nation
        await _send_show_in_channel(channel, nation, interaction.user.id, self.cog.bot)

        # Audit log
        await self.cog._log_ticket_action(
            guild=interaction.guild,
            action="created (membership)",
            channel=channel,
            actor=interaction.user,
            applicant=interaction.user,
            details=f"Nation: {nation_name}",
        )

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

        # Duplicate check
        if self.cog.db.has_open_ticket(interaction.guild_id, interaction.user.id):
            await interaction.followup.send(
                "❌ You already have an open ticket. Please wait for it to be resolved.",
                ephemeral=True,
            )
            return

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

        # Save to DB — delete channel if DB write fails (Fix #5)
        try:
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
        except Exception:
            logger.exception("Failed to upsert embassy ticket record, deleting channel")
            try:
                await channel.delete(reason="DB write failed")
            except discord.HTTPException:
                pass
            await interaction.followup.send("❌ Failed to save ticket. Please try again.", ephemeral=True)
            return

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

        # Audit log
        await self.cog._log_ticket_action(
            guild=interaction.guild,
            action="created (embassy)",
            channel=channel,
            actor=interaction.user,
            applicant=interaction.user,
            details=f"Alliance: {alliance_name}",
        )

        await interaction.followup.send(
            f"✅ Ticket created: {channel.mention}", ephemeral=True
        )


# ── Join Message Modal ─────────────────────────────────────────────────────────

class JoinMessageModal(discord.ui.Modal, title="Custom Welcome Message"):
    welcome_input = discord.ui.TextInput(
        label="Welcome Message",
        style=discord.TextStyle.long,
        placeholder="Enter your custom welcome message... Use {user} for the new member mention and {alliance} for the alliance name.",
        required=True,
        max_length=2000,
    )

    def __init__(self, cog: "TicketsCog", alliance_name: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.alliance_name = alliance_name

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        self.cog.db.set_guild_config(
            guild_id=interaction.guild_id,
            join_message_type="custom",
            join_message_custom=self.welcome_input.value,
            join_alliance_name=self.alliance_name,
        )

        await interaction.followup.send(
            f"✅ Custom welcome message saved for **{self.alliance_name}**.",
            ephemeral=True,
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
    embed.set_author(name=str(applicant) if applicant else "Unknown", icon_url=applicant.display_avatar.url if applicant else None)
    if flag:
        embed.set_thumbnail(url=flag)
    embed.set_footer(text="Use /verify to accept or reject this ticket.")
    return embed


def _build_alliance_embed(alliance: dict, applicant: Optional[discord.Member]) -> discord.Embed:
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
    embed.set_author(name=str(applicant) if applicant else "Unknown", icon_url=applicant.display_avatar.url if applicant else None)
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
        cfg = self.cog._get_config(interaction.guild_id)
        await interaction.response.send_modal(MembershipModal(self.cog, cfg.get("sort_type")))

    @discord.ui.button(
        label="🏛️ Embassy",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket:embassy",
    )
    async def embassy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbassyModal(self.cog))


# ── Main Cog ──────────────────────────────────────────────────────────────────

class TicketsCog(commands.Cog):
    """Per-server ticket management system."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db  = TicketsDB()
        bot.add_view(TicketTypeView(self))

    def _is_aries(self, user_id: int) -> bool:
        return int(user_id) == int(ARIES_USER_ID)

    def _is_ticket_admin(self, user_id: int) -> bool:
        return self.db.is_ticket_admin(int(user_id))

    async def _require_ticket_admin(self, interaction: discord.Interaction) -> bool:
        if self._is_ticket_admin(interaction.user.id):
            return True
        await interaction.followup.send(
            "❌ You need TICKETS_ADMIN access to use this command.",
            ephemeral=True,
        )
        return False

    async def _log_ticket_action(
        self,
        guild: discord.Guild,
        action: str,
        channel: discord.TextChannel,
        actor: discord.User,
        applicant: Optional[discord.Member] = None,
        details: Optional[str] = None,
    ):
        cfg = self._get_config(guild.id)
        audit_channel_id = cfg.get("audit_channel_id")
        if not audit_channel_id:
            return
        audit_channel = guild.get_channel(int(audit_channel_id))
        if not audit_channel or not isinstance(audit_channel, discord.TextChannel):
            return

        embed = discord.Embed(
            title=f"📋 Ticket {action.title()}",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Channel", value=channel.mention, inline=True)
        embed.add_field(name="Actor", value=actor.mention, inline=True)
        if applicant:
            embed.add_field(name="Applicant", value=applicant.mention, inline=True)
        if details:
            embed.add_field(name="Details", value=details, inline=False)
        embed.set_footer(text=f"Channel ID: {channel.id}")
        try:
            await audit_channel.send(embed=embed)
        except discord.HTTPException as e:
            logger.warning(f"Failed to send audit log: {e}")

    def _get_config(self, guild_id: int) -> dict:
        cfg = self.db.get_guild_config(guild_id) or {}
        return {
            "info_channel_id": cfg.get("info_channel_id"),
            "alliance_name": cfg.get("alliance_name", ""),
            "alliance_id": cfg.get("alliance_id"),
            "ticket_category_id": cfg.get("ticket_category_id"),
            "pending_members_cat_id": cfg.get("pending_members_cat_id"),
            "pending_diplomats_cat_id": cfg.get("pending_diplomats_cat_id"),
            "member_accepted_cat_id": cfg.get("member_accepted_cat_id"),
            "embassy_accepted_cat_id": cfg.get("embassy_accepted_cat_id"),
            "applicant_role_id": cfg.get("applicant_role_id"),
            "member_role_id": cfg.get("member_role_id"),
            "diplomat_role_id": cfg.get("diplomat_role_id"),
            "sort_type": cfg.get("sort_type"),
            "raider_role_id": cfg.get("raider_role_id"),
            "farmer_role_id": cfg.get("farmer_role_id"),
            "join_message_type": cfg.get("join_message_type", "original"),
            "join_message_custom": cfg.get("join_message_custom"),
            "join_alliance_name": cfg.get("join_alliance_name"),
            "join_alliance_id": cfg.get("join_alliance_id"),
            "audit_channel_id": cfg.get("audit_channel_id"),
        }

    @app_commands.command(name="ticket_admin_grant", description="Aries: grant TICKETS_ADMIN access.")
    @app_commands.describe(user="Discord server member to grant ticket admin access")
    async def ticket_admin_grant_command(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
    ):
        await interaction.response.defer(ephemeral=True)

        if not self._is_aries(interaction.user.id):
            await interaction.followup.send("❌ Only Aries can grant TICKETS_ADMIN access.", ephemeral=True)
            return

        row = self.db.grant_ticket_admin(
            user_id=user.id,
            username=str(user),
            display_name=getattr(user, "display_name", ""),
            granted_by=interaction.user.id,
        )

        embed = discord.Embed(
            title="TICKETS_ADMIN Granted",
            description=f"{user.mention} can now use ticket admin commands.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="User ID", value=str(row["user_id"]), inline=True)
        embed.add_field(name="Granted By", value=interaction.user.mention, inline=True)
        embed.set_footer(text="Stored in Databases/Tickets.db")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="ticket_admin_revoke", description="Aries: revoke TICKETS_ADMIN access.")
    @app_commands.describe(user="Discord server member to revoke ticket admin access from")
    async def ticket_admin_revoke_command(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
    ):
        await interaction.response.defer(ephemeral=True)

        if not self._is_aries(interaction.user.id):
            await interaction.followup.send("❌ Only Aries can revoke TICKETS_ADMIN access.", ephemeral=True)
            return

        if self._is_aries(user.id):
            await interaction.followup.send("❌ Aries always has TICKETS_ADMIN access.", ephemeral=True)
            return

        removed = self.db.revoke_ticket_admin(user.id, interaction.user.id)
        if not removed:
            await interaction.followup.send(f"ℹ️ {user.mention} was not a saved ticket admin.", ephemeral=True)
            return

        embed = discord.Embed(
            title="TICKETS_ADMIN Revoked",
            description=f"{user.mention} can no longer use ticket admin commands.",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="User ID", value=str(user.id), inline=True)
        embed.add_field(name="Revoked By", value=interaction.user.mention, inline=True)
        embed.set_footer(text="Stored in Databases/Tickets.db")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /info ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="info", description="Set up tickets for this server.")
    @app_commands.describe(
        channel="Channel to post the ticket embed in",
        alliance="Politics & War alliance name this server is for",
    )
    async def info_command(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        alliance: str,
    ):
        await interaction.response.defer(ephemeral=True)
        if not await self._require_ticket_admin(interaction):
            return

        guild = interaction.guild
        cfg = self._get_config(guild.id)

        # Validate categories exist
        missing = []
        if not guild.get_channel(cfg.get("pending_members_cat_id") or 0):
            missing.append("Pending Members category (run `/make_categories` first)")
        if not guild.get_channel(cfg.get("pending_diplomats_cat_id") or 0):
            missing.append("Pending Diplomats category (run `/make_categories` first)")
        if not guild.get_channel(cfg.get("member_accepted_cat_id") or 0):
            missing.append("Accepted Members category (run `/make_categories` first)")
        if not guild.get_channel(cfg.get("embassy_accepted_cat_id") or 0):
            missing.append("Accepted Diplomats category (run `/make_categories` first)")

        # Validate roles exist
        if not guild.get_role(cfg.get("applicant_role_id") or 0):
            missing.append("Applicants role (run `/ticket_roles make` or `/ticket_roles link`)")
        if not guild.get_role(cfg.get("member_role_id") or 0):
            missing.append("Member role (run `/ticket_roles make` or `/ticket_roles link`)")
        if not guild.get_role(cfg.get("diplomat_role_id") or 0):
            missing.append("Diplomat role (run `/ticket_roles make` or `/ticket_roles link`)")

        if missing:
            await interaction.followup.send(
                "❌ Please set up the following before running `/info`:\n"
                + "\n".join(f"• {m}" for m in missing),
                ephemeral=True,
            )
            return

        # Try to resolve alliance ID from the name
        alliance_obj = await _lookup_alliance(alliance.strip())
        alliance_id = alliance_obj.get("id") if alliance_obj else None

        self.db.set_guild_config(
            guild_id=interaction.guild_id,
            info_channel_id=channel.id,
            alliance_name=alliance.strip(),
            alliance_id=alliance_id,
        )

        embed = discord.Embed(
            title=f"⭐ Welcome to {interaction.guild.name}",
            description=(
                f"**{interaction.guild.name}** is the official Discord server for our "
                f"**{alliance}** Politics & War alliance.\n\n"
                "To receive your roles you must open a ticket below:\n\n"
                "📋 **Membership** — for nations wishing to join\n"
                "🏛️ **Embassy** — for alliances wishing to establish diplomatic relations\n\n"
                "Click the appropriate button below to get started. "
                "A staff member will review your application shortly."
            ),
            color=discord.Color.dark_red(),
        )
        embed.set_footer(text=alliance.strip())

        await channel.send(embed=embed, view=TicketTypeView(self))
        await interaction.followup.send(
            f"✅ Tickets configured for **{alliance}**. Info embed posted in {channel.mention}.",
            ephemeral=True,
        )

    # ── /make_categories ──────────────────────────────────────────────────────

    @app_commands.command(
        name="make_categories",
        description="Create pending/accepted categories + sorting for tickets.",
    )
    @app_commands.describe(
        sort_type="How to sort pending membership tickets into sub-categories",
    )
    @app_commands.choices(sort_type=[
        app_commands.Choice(name="Score", value="score"),
        app_commands.Choice(name="City Count", value="cities"),
        app_commands.Choice(name="Farm / Raider", value="farm_raider"),
        app_commands.Choice(name="None (single pending category)", value="none"),
    ])
    async def make_categories_command(
        self,
        interaction: discord.Interaction,
        sort_type: str,
    ):
        await interaction.response.defer(ephemeral=True)
        if not await self._require_ticket_admin(interaction):
            return

        guild = interaction.guild

        # Delete old Discord categories for this guild (both sort + pending/accepted)
        old_cats = self.db.get_sort_categories(guild.id)
        for oc in old_cats:
            cat = guild.get_channel(oc["channel_id"])
            if cat and isinstance(cat, discord.CategoryChannel):
                try:
                    await cat.delete(reason="Replacing categories")
                except discord.HTTPException as e:
                    logger.warning(f"Failed to delete old sort category {oc['channel_id']}: {e}")

        # Also delete old pending/accepted categories stored in guild_config
        old_cfg = self.db.get_guild_config(guild.id) or {}
        for old_key in ("pending_members_cat_id", "pending_diplomats_cat_id",
                         "member_accepted_cat_id", "embassy_accepted_cat_id"):
            cid = old_cfg.get(old_key)
            if cid:
                cat = guild.get_channel(int(cid))
                if cat and isinstance(cat, discord.CategoryChannel):
                    try:
                        await cat.delete(reason="Replacing categories")
                    except discord.HTTPException as e:
                        logger.warning(f"Failed to delete old {old_key} {cid}: {e}")

        created = []

        # 1. Pending Members (main or parent category)
        pending_members_cat = await guild.create_category(
            name="Pending Members",
            reason="Ticket pending members category",
        )
        pending_members_id = pending_members_cat.id
        created.append(("Pending Members", pending_members_id))
        await asyncio.sleep(0.5)

        # 2. Pending Diplomats
        pending_diplomats_cat = await guild.create_category(
            name="Pending Diplomats",
            reason="Ticket pending diplomats category",
        )
        pending_diplomats_id = pending_diplomats_cat.id
        created.append(("Pending Diplomats", pending_diplomats_id))
        await asyncio.sleep(0.5)

        # 3. Accepted Members
        accepted_members_cat = await guild.create_category(
            name="Accepted Members",
            reason="Ticket accepted members category",
        )
        accepted_members_id = accepted_members_cat.id
        created.append(("Accepted Members", accepted_members_id))
        await asyncio.sleep(0.5)

        # 4. Accepted Diplomats
        accepted_diplomats_cat = await guild.create_category(
            name="Accepted Diplomats",
            reason="Ticket accepted diplomats category",
        )
        accepted_diplomats_id = accepted_diplomats_cat.id
        created.append(("Accepted Diplomats", accepted_diplomats_id))

        # 5. Sort sub-categories under Pending Members (if not "none")
        sort_ranges = []
        if sort_type == "score":
            sort_ranges = [(f"{i}-{i+1000}", f"{i}–{i+1000} Score") for i in range(0, 20000, 1000)]
        elif sort_type == "cities":
            sort_ranges = [(f"{i+1}-{i+10}", f"Cities {i+1}–{i+10}") for i in range(0, 60, 10)]
        elif sort_type == "farm_raider":
            sort_ranges = [("Farm", "Farm"), ("Raider", "Raider")]

        sort_entries = []
        for label, cat_name in sort_ranges:
            cat = await guild.create_category(
                name=cat_name,
                reason=f"Ticket sorting category ({sort_type})",
            )
            sort_entries.append((label, cat.id))
            await asyncio.sleep(0.5)  # avoid rate limits

        # Save all to DB
        self.db.set_sort_categories(guild.id, sort_entries)
        self.db.set_guild_config(
            guild_id=guild.id,
            sort_type=sort_type if sort_type != "none" else None,
            pending_members_cat_id=pending_members_id,
            pending_diplomats_cat_id=pending_diplomats_id,
            member_accepted_cat_id=accepted_members_id,
            embassy_accepted_cat_id=accepted_diplomats_id,
        )

        lines = [f"• Pending Members" if not sort_entries else f"• Pending Members (with {len(sort_entries)} sub-categories)"]
        lines.append(f"• Pending Diplomats")
        lines.append(f"• Accepted Members")
        lines.append(f"• Accepted Diplomats")
        if sort_entries:
            lines.append(f"  Sort: {', '.join(s for s, _ in sort_ranges)}")

        await interaction.followup.send(
            f"✅ Created **{len(created)}** categories (`{sort_type}`).\n" + "\n".join(lines),
            ephemeral=True,
        )

    # ── /link_ticket ──────────────────────────────────────────────────────────

    async def _link_ticket_nation_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        if not self._is_ticket_admin(interaction.user.id):
            return []
        try:
            return await nation_autocomplete(current, nw_only=False, limit=25)
        except Exception as e:
            logger.error(f"link_ticket autocomplete error: {e}")
            return []

    @app_commands.command(
        name="link_ticket",
        description="Link a Discord user to a nation and create a ticket.",
    )
    @app_commands.describe(
        nation="Nation name to link",
        user="Discord member to link the ticket to",
        member_type="Nation type (for Farm/Raider sorting)",
    )
    @app_commands.choices(member_type=[
        app_commands.Choice(name="Farm", value="farm"),
        app_commands.Choice(name="Raider", value="raider"),
    ])
    @app_commands.autocomplete(nation=_link_ticket_nation_autocomplete)
    async def link_ticket_command(
        self,
        interaction: discord.Interaction,
        nation: str,
        user: discord.Member,
        member_type: Optional[str] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        if not await self._require_ticket_admin(interaction):
            return

        # Duplicate check
        if self.db.has_open_ticket(interaction.guild_id, user.id):
            await interaction.followup.send(
                "❌ That user already has an open ticket.", ephemeral=True,
            )
            return

        nation_data = await _lookup_nation(nation)
        if not nation_data:
            await interaction.followup.send(
                f"❌ Could not find a nation matching **{nation}**.", ephemeral=True
            )
            return

        nation_name = nation_data.get("nation_name") or nation
        nation_id   = nation_data.get("id")
        city_count  = int(nation_data.get("num_cities") or 0)
        score       = float(nation_data.get("score") or 0)
        channel_name = _member_channel_name(nation_name, city_count)

        channel = await self._create_ticket_channel(
            interaction.guild,
            user,
            channel_name=channel_name,
            ticket_type="membership",
            score=score,
            city_count=city_count,
            member_type=member_type,
        )
        if not channel:
            await interaction.followup.send("❌ Failed to create ticket channel.", ephemeral=True)
            return

        # Save to DB — atomic: delete channel if DB write fails
        try:
            self.db.upsert(
                channel_id=channel.id,
                guild_id=interaction.guild.id,
                applicant_id=user.id,
                ticket_type="membership",
                status="open",
                channel_name=channel_name,
                subject=nation_name,
                nation_id=int(nation_id) if nation_id else None,
                city_count=city_count,
                member_type=member_type,
            )
        except Exception:
            logger.exception("Failed to upsert ticket record in link_ticket, deleting channel")
            try:
                await channel.delete(reason="DB write failed")
            except discord.HTTPException:
                pass
            await interaction.followup.send("❌ Failed to save ticket. Please try again.", ephemeral=True)
            return

        # Give the Applicants role
        cfg = self._get_config(interaction.guild.id)
        applicant_role_id = cfg.get("applicant_role_id")
        if applicant_role_id and isinstance(user, discord.Member):
            role = interaction.guild.get_role(int(applicant_role_id))
            if role:
                try:
                    await user.add_roles(role, reason="Membership ticket created (link_ticket)")
                except discord.HTTPException as e:
                    logger.warning(f"Failed to assign Applicants role: {e}")

        await channel.send(
            content=f"{user.mention} — a ticket has been opened for you by {interaction.user.mention}."
        )

        await _send_show_in_channel(channel, nation_data, user.id, self.bot)

        verified_ok = True
        try:
            from Systems.PnW.Util.reaper_verify import get_verified_db

            vdb = get_verified_db()
            await vdb.upsert_user(
                discord_id=str(user.id),
                nation=nation_data,
                discord_username=str(user),
                discord_display_name=getattr(user, "display_name", None),
                source="ticket_link",
            )
        except Exception as e:
            logger.error(f"Failed to verify user in link_ticket: {e}")
            verified_ok = False

        # Audit log
        await self._log_ticket_action(
            guild=interaction.guild,
            action="created (link_ticket)",
            channel=channel,
            actor=interaction.user,
            applicant=user,
            details=f"Nation: {nation_name}, Verified: {verified_ok}",
        )

        await interaction.followup.send(
            f"✅ Ticket created: {channel.mention}\n"
            f"• **Nation:** {nation_name}\n"
            f"• **User:** {user.mention}\n"
            f"• **Verified** in Verified.db{' ⚠️ (failed)' if not verified_ok else ''}",
            ephemeral=True,
        )

    # ── /join_message_config ──────────────────────────────────────────────────

    async def _join_alliance_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        if not self._is_ticket_admin(interaction.user.id):
            return []
        try:
            return await alliance_autocomplete(current, include_nw=True, limit=25)
        except Exception as e:
            logger.error(f"join_message_config autocomplete error: {e}")
            return []

    @app_commands.command(
        name="join_message_config",
        description="Configure the welcome message shown when a new member joins.",
    )
    @app_commands.describe(
        alliance="Politics & War alliance for the welcome message",
        message="Choose the welcome message style",
    )
    @app_commands.choices(message=[
        app_commands.Choice(name="Original", value="original"),
        app_commands.Choice(name="Custom", value="custom"),
    ])
    @app_commands.autocomplete(alliance=_join_alliance_autocomplete)
    async def join_message_config_command(
        self,
        interaction: discord.Interaction,
        alliance: str,
        message: str,
    ):
        if not await self._require_ticket_admin(interaction):
            return

        if message == "custom":
            await interaction.response.send_modal(JoinMessageModal(self, alliance))
            return

        await interaction.response.defer(ephemeral=True)

        self.db.set_guild_config(
            guild_id=interaction.guild_id,
            join_message_type="original",
            join_message_custom=None,
            join_alliance_name=alliance,
        )

        await interaction.followup.send(
            f"✅ Welcome message set to **Original** for **{alliance}**.",
            ephemeral=True,
        )

    # ── /ticket_roles ─────────────────────────────────────────────────────────

    ticket_roles = app_commands.Group(
        name="ticket_roles",
        description="Manage roles used by the ticket system.",
    )

    @ticket_roles.command(name="make", description="Create Applicant, Member, Diplomat, Raider & Farmer roles.")
    async def ticket_roles_make(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self._require_ticket_admin(interaction):
            return

        guild = interaction.guild
        role_specs = [
            ("Applicants", "Applicants"),
            ("Member", "Member"),
            ("Diplomat", "Diplomat"),
            ("Raider", "Raider"),
            ("Farmer", "Farmer"),
        ]
        created_roles = {}
        for name, _ in role_specs:
            existing = discord.utils.get(guild.roles, name=name)
            if existing:
                created_roles[name.lower()] = existing.id
            else:
                try:
                    role = await guild.create_role(
                        name=name,
                        reason="Ticket system auto-created role",
                    )
                    created_roles[name.lower()] = role.id
                except discord.HTTPException as e:
                    await interaction.followup.send(
                        f"❌ Failed to create **{name}** role: {e}", ephemeral=True
                    )
                    return

        # Set permissions on sort categories
        sort_cats = self.db.get_sort_categories(guild.id)
        for cat_row in sort_cats:
            cat = guild.get_channel(cat_row["channel_id"])
            if not cat or not isinstance(cat, discord.CategoryChannel):
                continue
            overwrites = dict(cat.overwrites) if cat.overwrites else {}
            for role_name in ("Applicants", "Member", "Diplomat", "Raider", "Farmer"):
                rid = created_roles.get(role_name.lower())
                if rid:
                    role = guild.get_role(rid)
                    if role:
                        overwrites[role] = discord.PermissionOverwrite(
                            view_channel=True,
                            send_messages=True,
                            read_message_history=True,
                        )
            try:
                await cat.edit(overwrites=overwrites)
            except discord.HTTPException:
                pass

        # Save to guild_config
        self.db.set_guild_config(
            guild_id=guild.id,
            applicant_role_id=created_roles.get("applicants"),
            member_role_id=created_roles.get("member"),
            diplomat_role_id=created_roles.get("diplomat"),
            raider_role_id=created_roles.get("raider"),
            farmer_role_id=created_roles.get("farmer"),
        )

        await interaction.followup.send(
            "✅ Created / linked roles:\n"
            f"• **Applicants** → <@&{created_roles['applicants']}>\n"
            f"• **Member** → <@&{created_roles['member']}>\n"
            f"• **Diplomat** → <@&{created_roles['diplomat']}>\n"
            f"• **Raider** → <@&{created_roles['raider']}>\n"
            f"• **Farmer** → <@&{created_roles['farmer']}>\n"
            "Permissions set on sorting categories.",
            ephemeral=True,
        )

    @ticket_roles.command(name="link", description="Link existing roles to ticket system.")
    @app_commands.describe(
        applicant="Role given when a membership ticket is created",
        member="Role given when a membership ticket is accepted",
        diplomat="Role given when an embassy is accepted",
        raider="Role for raider-type members",
        farmer="Role for farmer-type members",
    )
    async def ticket_roles_link(
        self,
        interaction: discord.Interaction,
        applicant: Optional[discord.Role] = None,
        member: Optional[discord.Role] = None,
        diplomat: Optional[discord.Role] = None,
        raider: Optional[discord.Role] = None,
        farmer: Optional[discord.Role] = None,
    ):
        await interaction.response.defer(ephemeral=True)
        if not await self._require_ticket_admin(interaction):
            return

        kwargs = {}
        lines = []
        mapping = [("applicant_role_id", applicant), ("member_role_id", member),
                   ("diplomat_role_id", diplomat), ("raider_role_id", raider), ("farmer_role_id", farmer)]
        for name, role in mapping:
            if role is not None:
                kwargs[name] = role.id
                label = name.replace("_role_id", "").replace("_", " ").title()
                lines.append(f"• **{label}** → {role.mention}")

        if not kwargs:
            await interaction.followup.send("ℹ️ No roles specified — nothing changed.", ephemeral=True)
            return

        self.db.set_guild_config(guild_id=interaction.guild_id, **kwargs)

        await interaction.followup.send(
            "✅ Roles linked:\n" + "\n".join(lines), ephemeral=True
        )

    @ticket_roles.command(name="list", description="Show currently linked ticket roles.")
    async def ticket_roles_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self._require_ticket_admin(interaction):
            return
        cfg = self._get_config(interaction.guild_id)
        lines = []
        for key, label in [("applicant_role_id", "Applicants"), ("member_role_id", "Member"),
                           ("diplomat_role_id", "Diplomat"), ("raider_role_id", "Raider"),
                           ("farmer_role_id", "Farmer")]:
            rid = cfg.get(key)
            if rid:
                role = interaction.guild.get_role(int(rid))
                lines.append(f"• **{label}** → {role.mention if role else 'deleted role'}")
            else:
                lines.append(f"• **{label}** — Not set")
        embed = discord.Embed(
            title="🎭 Ticket Roles",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Use /ticket_roles link to change or /ticket_roles make to create.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="verify", description="Accept or reject the current ticket.")
    @app_commands.describe(action="Accept or Reject this ticket")
    @app_commands.choices(action=[
        app_commands.Choice(name="Accept", value="accept"),
        app_commands.Choice(name="Reject", value="reject"),
    ])
    async def verify_command(self, interaction: discord.Interaction, action: str):
        await interaction.response.defer(ephemeral=True)
        if not await self._require_ticket_admin(interaction):
            return

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

    # ── /close_ticket ──────────────────────────────────────────────────────────

    @app_commands.command(name="close_ticket", description="Request closure of your own ticket.")
    async def close_ticket_command(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("❌ Run this inside a ticket channel.", ephemeral=True)
            return

        record = self.db.get(channel.id)
        if not record:
            await interaction.followup.send("❌ This channel isn't tracked as a ticket.", ephemeral=True)
            return

        if record["status"] != "open":
            await interaction.followup.send(
                f"❌ This ticket is already **{record['status']}**.", ephemeral=True
            )
            return

        if record["applicant_id"] != interaction.user.id:
            await interaction.followup.send(
                "❌ Only the ticket creator can close this ticket.", ephemeral=True
            )
            return

        self.db.set_resolved(channel.id, interaction.user.id, "closed")
        try:
            await channel.send(
                f"🔒 {interaction.user.mention} has requested this ticket be closed. "
                "Deleting in 10s…"
            )
        except Exception:
            pass
        await interaction.followup.send("✅ Ticket closed — deleting shortly.", ephemeral=True)

        await self._log_ticket_action(
            guild=interaction.guild,
            action="closed by user",
            channel=channel,
            actor=interaction.user,
            applicant=interaction.user,
            details=f"Type: {record['ticket_type']}, Subject: {record['subject']}",
        )

        await asyncio.sleep(10)
        try:
            await channel.delete(reason=f"Ticket closed by {interaction.user}")
        except discord.HTTPException as e:
            logger.error(f"Failed to delete closed ticket: {e}")

    # ── /delete_ticket ────────────────────────────────────────────────────────

    @app_commands.command(name="delete_ticket", description="Delete a ticket by name.")
    @app_commands.describe(ticket="The ticket to delete (type to search)")
    async def delete_ticket_command(self, interaction: discord.Interaction, ticket: str):
        await interaction.response.defer(ephemeral=True)
        if not await self._require_ticket_admin(interaction):
            return

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
        if not self._is_ticket_admin(interaction.user.id):
            return []
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
        if not await self._require_ticket_admin(interaction):
            return

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
                    # Also update subject + city_count in DB (preserve member_type)
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
                        member_type=record.get("member_type"),
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


    # ── /view_config ──────────────────────────────────────────────────────────

    @app_commands.command(
        name="view_config",
        description="View the current ticket configuration for this server.",
    )
    async def view_config_command(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self._require_ticket_admin(interaction):
            return

        cfg = self._get_config(interaction.guild_id)

        embed = discord.Embed(
            title="Ticket Configuration",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc),
        )

        def fmt(val):
            return str(val) if val else "Not set"

        def fmt_channel(cid):
            ch = interaction.guild.get_channel(int(cid))
            return ch.mention if ch else f"`{cid}` (deleted)"

        def fmt_role(rid):
            r = interaction.guild.get_role(int(rid))
            return r.mention if r else f"`{rid}` (deleted)"

        embed.add_field(name="Info Channel", value=fmt_channel(cfg.get("info_channel_id")), inline=False)
        embed.add_field(name="Alliance Name", value=fmt(cfg.get("alliance_name")), inline=True)
        embed.add_field(name="Alliance ID", value=fmt(cfg.get("alliance_id")), inline=True)
        embed.add_field(name="Pending Members Cat", value=fmt_channel(cfg.get("pending_members_cat_id")), inline=False)
        embed.add_field(name="Pending Diplomats Cat", value=fmt_channel(cfg.get("pending_diplomats_cat_id")), inline=True)
        embed.add_field(name="Member Accepted Cat", value=fmt_channel(cfg.get("member_accepted_cat_id")), inline=True)
        embed.add_field(name="Embassy Accepted Cat", value=fmt_channel(cfg.get("embassy_accepted_cat_id")), inline=True)
        embed.add_field(name="Applicant Role", value=fmt_role(cfg.get("applicant_role_id")), inline=True)
        embed.add_field(name="Member Role", value=fmt_role(cfg.get("member_role_id")), inline=True)
        embed.add_field(name="Diplomat Role", value=fmt_role(cfg.get("diplomat_role_id")), inline=True)
        embed.add_field(
            name="Farm / Raider Roles",
            value=f"Raider: {fmt_role(cfg.get('raider_role_id'))}\nFarmer: {fmt_role(cfg.get('farmer_role_id'))}",
            inline=True,
        )
        embed.add_field(name="Sort Type", value=fmt(cfg.get("sort_type")), inline=True)
        embed.add_field(name="Join Msg Type", value=cfg.get("join_message_type", "original"), inline=True)
        embed.add_field(name="Join Alliance", value=fmt(cfg.get("join_alliance_name")), inline=True)

        # Show sort categories
        cats = self.db.get_sort_categories(interaction.guild_id)
        if cats:
            lines = []
            for c in cats:
                ch = interaction.guild.get_channel(c["channel_id"])
                lines.append(f"• {c['label']}: {ch.mention if ch else 'deleted'}")
            embed.add_field(name="Sort Categories", value="\n".join(lines), inline=False)

        embed.set_footer(text=f"Guild ID: {interaction.guild_id}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /ticket_info ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="ticket_info",
        description="View details of any ticket, including who resolved it.",
    )
    @app_commands.describe(ticket="The ticket to look up (type to search)")
    async def ticket_info_command(self, interaction: discord.Interaction, ticket: str):
        await interaction.response.defer(ephemeral=True)
        if not await self._require_ticket_admin(interaction):
            return

        try:
            channel_id = int(ticket)
        except ValueError:
            await interaction.followup.send("❌ Invalid ticket selection.", ephemeral=True)
            return

        record = self.db.get(channel_id)
        if not record:
            await interaction.followup.send("❌ Ticket not found in database.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🎫 Ticket Info — {record['channel_name']}",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Channel Name", value=record["channel_name"], inline=True)
        embed.add_field(name="Ticket Type", value=record["ticket_type"].capitalize(), inline=True)
        embed.add_field(name="Status", value=record["status"].upper(), inline=True)
        embed.add_field(name="Subject", value=record["subject"], inline=False)

        applicant = interaction.guild.get_member(record["applicant_id"])
        embed.add_field(
            name="Applicant",
            value=applicant.mention if applicant else f"<@{record['applicant_id']}> (left)",
            inline=True,
        )

        resolved_by_id = record.get("resolved_by")
        resolved_at = record.get("resolved_at")
        if resolved_by_id:
            resolver = interaction.guild.get_member(resolved_by_id)
            embed.add_field(
                name="Resolved By",
                value=resolver.mention if resolver else f"<@{resolved_by_id}> (left)",
                inline=True,
            )
        if resolved_at:
            embed.add_field(name="Resolved At", value=resolved_at, inline=True)

        embed.add_field(name="Created At", value=record.get("created_at", "Unknown"), inline=True)
        if record.get("nation_id"):
            embed.add_field(name="Nation ID", value=str(record["nation_id"]), inline=True)
        if record.get("alliance_id"):
            embed.add_field(name="Alliance ID", value=str(record["alliance_id"]), inline=True)
        if record.get("member_type"):
            embed.add_field(name="Member Type", value=record["member_type"].capitalize(), inline=True)

        embed.set_footer(text=f"Channel ID: {channel_id}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @ticket_info_command.autocomplete("ticket")
    async def _ticket_info_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        if not self._is_ticket_admin(interaction.user.id):
            return []
        tickets = self.db.list_all(interaction.guild_id)
        choices = []
        for t in tickets:
            label = f"[{t['status'].upper()}] {t['channel_name']} ({t['ticket_type']})"
            if current.lower() in label.lower():
                choices.append(app_commands.Choice(name=label[:100], value=str(t["channel_id"])))
            if len(choices) == 25:
                break
        return choices

    # ── /ticket_add ───────────────────────────────────────────────────────────

    ticket_add = app_commands.Group(
        name="ticket_add",
        description="Manage roles that are added to every new ticket channel.",
    )

    @ticket_add.command(name="add", description="Add a role to all new ticket channels.")
    @app_commands.describe(role="The role to add", label="Friendly label (e.g. 'Staff')")
    async def ticket_add_add(
        self, interaction: discord.Interaction, role: discord.Role, label: str = ""
    ):
        await interaction.response.defer(ephemeral=True)
        if not await self._require_ticket_admin(interaction):
            return

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

    @ticket_add.command(name="remove", description="Remove a role from new ticket channels.")
    @app_commands.describe(role_id="The role to remove (type to search)")
    async def ticket_add_remove(self, interaction: discord.Interaction, role_id: str):
        await interaction.response.defer(ephemeral=True)
        if not await self._require_ticket_admin(interaction):
            return

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

    @ticket_add_remove.autocomplete("role_id")
    async def _ticket_add_remove_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        if not self._is_ticket_admin(interaction.user.id):
            return []
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

    @ticket_add.command(name="list", description="List all roles added to new ticket channels.")
    async def ticket_add_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self._require_ticket_admin(interaction):
            return

        rows = self.db.list_ticket_roles(interaction.guild_id)
        if not rows:
            await interaction.followup.send(
                "ℹ️ No ticket roles configured yet. Use `/ticket_add add` to add one.",
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


    # ── /ticket_audit ─────────────────────────────────────────────────────────

    ticket_audit = app_commands.Group(
        name="ticket_audit",
        description="Manage the audit log channel for ticket actions.",
    )

    @ticket_audit.command(name="set", description="Set the channel where ticket actions are logged.")
    @app_commands.describe(channel="The channel to send audit logs to")
    async def ticket_audit_set(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        if not await self._require_ticket_admin(interaction):
            return
        self.db.set_guild_config(guild_id=interaction.guild_id, audit_channel_id=channel.id)
        await interaction.followup.send(f"✅ Audit logs will be sent to {channel.mention}.", ephemeral=True)

    @ticket_audit.command(name="remove", description="Remove the audit log channel.")
    async def ticket_audit_remove(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self._require_ticket_admin(interaction):
            return
        self.db.set_guild_config(guild_id=interaction.guild_id, audit_channel_id=None)
        await interaction.followup.send("✅ Audit logging disabled.", ephemeral=True)

    @ticket_audit.command(name="view", description="Show the current audit log channel.")
    async def ticket_audit_view(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self._require_ticket_admin(interaction):
            return
        cfg = self._get_config(interaction.guild_id)
        cid = cfg.get("audit_channel_id")
        if cid:
            ch = interaction.guild.get_channel(int(cid))
            await interaction.followup.send(f"📋 Audit log channel: {ch.mention if ch else 'deleted'}.", ephemeral=True)
        else:
            await interaction.followup.send("ℹ️ No audit log channel configured.", ephemeral=True)


    # ── Internal helpers ──────────────────────────────────────────────────────
    def _pick_sort_category(
        self,
        guild_id: int,
        score: float = 0,
        city_count: int = 0,
        member_type: Optional[str] = None,
    ) -> Optional[int]:
        cfg = self._get_config(guild_id)
        sort_type = cfg.get("sort_type")
        if not sort_type:
            return None

        cats = self.db.get_sort_categories(guild_id)
        if not cats:
            return None

        if sort_type == "score":
            bracket = int(score / 1000) * 1000
            if score >= 20000:
                # Use last category for overflow
                return cats[-1]["channel_id"]
            label = f"{bracket}-{bracket + 1000}"
            for c in cats:
                if c["label"] == label:
                    return c["channel_id"]

        elif sort_type == "cities":
            if city_count >= 60:
                # Use last category for overflow
                return cats[-1]["channel_id"]
            bracket = int((city_count - 1) / 10) * 10
            label = f"{bracket + 1}-{bracket + 10}"
            for c in cats:
                if c["label"] == label:
                    return c["channel_id"]

        elif sort_type == "farm_raider" and member_type:
            for c in cats:
                if c["label"].lower() == member_type.lower():
                    return c["channel_id"]

        return None

    async def _create_ticket_channel(
        self,
        guild: discord.Guild,
        applicant: discord.Member,
        channel_name: str,
        ticket_type: str,
        score: float = 0,
        city_count: int = 0,
        member_type: Optional[str] = None,
    ) -> Optional[discord.TextChannel]:
        cfg = self._get_config(guild.id)

        if ticket_type == "membership":
            # Try sort sub-category first, then fall back to pending_members
            sort_cat_id = self._pick_sort_category(guild.id, score, city_count, member_type)
            ticket_cat_id = sort_cat_id or cfg.get("pending_members_cat_id")
            if not ticket_cat_id:
                logger.error(f"No pending_members_cat_id configured for guild {guild.id}.")
                return None
        else:
            ticket_cat_id = cfg.get("pending_diplomats_cat_id")
            if not ticket_cat_id:
                logger.error(f"No pending_diplomats_cat_id configured for guild {guild.id}.")
                return None

        if not guild.me.guild_permissions.manage_channels:
            logger.error(f"Bot lacks manage_channels permission in guild {guild.id}.")
            return None

        category = guild.get_channel(ticket_cat_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            logger.error(f"Ticket category {ticket_cat_id} not found for guild {guild.id}.")
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

        await self._log_ticket_action(
            guild=interaction.guild,
            action="rejected",
            channel=channel,
            actor=interaction.user,
            applicant=applicant,
            details=f"Type: {record['ticket_type']}, Subject: {record['subject']}",
        )

        # Persist rejection in DB before deleting the channel
        self.db.set_resolved(channel.id, interaction.user.id, "rejected")

        await self._try_dm(
            record["applicant_id"],
            f"❌ Your **{record['ticket_type']}** ticket ({record['subject']}) in "
            f"**{interaction.guild.name}** has been rejected.",
        )

        await interaction.followup.send("🗑️ Ticket rejected — deleting in 5s.", ephemeral=True)
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Ticket rejected by {interaction.user}")
        except discord.HTTPException as e:
            logger.error(f"Failed to delete rejected ticket: {e}")

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
        cfg = self._get_config(guild.id)

        # Remove Applicants role, give Member role + optional Raider/Farmer role
        roles_to_remove = []
        roles_to_add = []
        if applicant:
            applicant_role = guild.get_role(cfg["applicant_role_id"]) if cfg.get("applicant_role_id") else None
            if applicant_role:
                roles_to_remove.append(applicant_role)

            member_role = guild.get_role(cfg["member_role_id"])
            if member_role:
                roles_to_add.append(member_role)

            member_type = record.get("member_type")
            if member_type == "raider":
                raider_role = guild.get_role(cfg["raider_role_id"])
                if raider_role:
                    roles_to_add.append(raider_role)
            elif member_type == "farm":
                farmer_role = guild.get_role(cfg["farmer_role_id"])
                if farmer_role:
                    roles_to_add.append(farmer_role)

            if roles_to_remove:
                try:
                    await applicant.remove_roles(*roles_to_remove, reason="Membership ticket accepted")
                except discord.HTTPException as e:
                    logger.warning(f"Failed to remove Applicants role: {e}")

            if roles_to_add:
                try:
                    await applicant.add_roles(*roles_to_add, reason="Membership ticket accepted")
                except discord.HTTPException as e:
                    logger.error(f"Failed to assign membership roles: {e}")
                    await interaction.followup.send(
                        f"⚠️ Could not assign roles: {e}\nTicket was still accepted — assign roles manually.",
                        ephemeral=True,
                    )

        # Move to accepted category AND lock permissions so only the applicant
        # (+ bot + ticket roles) can see it — not every other member.
        accepted_cat = guild.get_channel(cfg["member_accepted_cat_id"])
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

        self.db.set_resolved(channel.id, interaction.user.id, "accepted")
        mention = applicant.mention if applicant else "Applicant"
        alliance_name = cfg.get("alliance_name") or guild.name
        await channel.send(
            f"✅ {mention} — your membership has been **accepted** by "
            f"{interaction.user.mention}! Welcome to {alliance_name}! 🏴‍☠️"
        )
        await interaction.followup.send("✅ Membership accepted.", ephemeral=True)

        await self._log_ticket_action(
            guild=guild,
            action="accepted (membership)",
            channel=channel,
            actor=interaction.user,
            applicant=applicant,
            details=f"Roles: {', '.join(r.name for r in roles_to_add) if roles_to_add else 'none'}",
        )

        await self._try_dm(
            record["applicant_id"],
            f"✅ Your **membership** ticket in **{guild.name}** has been accepted! "
            f"Welcome to {alliance_name or guild.name}!",
        )

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
        cfg           = self._get_config(guild.id)

        # Create or find the alliance role
        alliance_role = await self._get_or_create_alliance_role(guild, alliance_name, color_hex)

        # Assign alliance role + Diplomat role to the applicant
        if applicant:
            roles_to_add = [r for r in [alliance_role, guild.get_role(cfg["diplomat_role_id"])] if r]
            if roles_to_add:
                try:
                    await applicant.add_roles(*roles_to_add, reason="Embassy ticket accepted")
                except discord.HTTPException as e:
                    logger.error(f"Failed to assign embassy roles: {e}")
                    await interaction.followup.send(
                        f"⚠️ Could not assign roles: {e}\nTicket was still accepted — assign roles manually.",
                        ephemeral=True,
                    )

        # Move to accepted category with explicit overwrites so:
        #   - @everyone cannot see it
        #   - the applicant can still see it
        #   - the alliance role can see it (so the whole alliance can use the channel)
        #   - ticket roles (staff) can see it
        accepted_cat = guild.get_channel(cfg["embassy_accepted_cat_id"])
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

        self.db.set_resolved(channel.id, interaction.user.id, "accepted")

        diplomat_role = guild.get_role(cfg.get("diplomat_role_id"))
        role_mentions = " ".join(
            r.mention for r in [alliance_role, diplomat_role] if r
        )
        mention = applicant.mention if applicant else "Applicant"
        await channel.send(
            f"✅ {mention} — your embassy has been **accepted** by "
            f"{interaction.user.mention}! You've been given the {role_mentions} role(s). 🏛️"
        )
        await interaction.followup.send("✅ Embassy accepted.", ephemeral=True)

        await self._log_ticket_action(
            guild=guild,
            action="accepted (embassy)",
            channel=channel,
            actor=interaction.user,
            applicant=applicant,
            details=f"Alliance: {alliance_name}",
        )

        await self._try_dm(
            record["applicant_id"],
            f"✅ Your **embassy** ticket for **{alliance_name}** in "
            f"**{guild.name}** has been accepted!",
        )

    # ── DM notification helper ────────────────────────────────────────────────

    async def _try_dm(self, user_id: int, content: str, *, embed: discord.Embed = None) -> None:
        """Try to send a DM to a user; silently ignore if blocked/DMs closed."""
        user = self.bot.get_user(user_id)
        if not user:
            return
        try:
            await user.send(content, embed=embed)
        except discord.Forbidden:
            pass
        except discord.HTTPException as e:
            logger.warning(f"Failed to DM {user_id}: {e}")

    async def _get_or_create_alliance_role(
        self, guild: discord.Guild, name: str, color_hex: str
    ) -> Optional[discord.Role]:
        existing = discord.utils.get(guild.roles, name=name)
        if existing:
            return existing
        # Truncate names longer than 100 chars (Discord limit)
        role_name = name[:100]
        try:
            return await guild.create_role(
                name=role_name,
                color=_hex_to_color(color_hex),
                reason=f"Embassy role for {role_name}",
            )
        except discord.HTTPException as e:
            logger.error(f"Failed to create alliance role '{name}': {e}")
            return None

    # ── Welcome new members ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        cfg = self._get_config(member.guild.id)
        info_channel_id = cfg.get("info_channel_id")
        if not info_channel_id:
            return

        ticket_channel = member.guild.get_channel(info_channel_id)
        if not ticket_channel:
            return

        alliance_name = cfg.get("join_alliance_name") or cfg.get("alliance_name") or member.guild.name
        ticket_link   = f"<#{info_channel_id}>"

        if cfg.get("join_message_type") == "custom" and cfg.get("join_message_custom"):
            custom = cfg["join_message_custom"]
            custom = custom.replace("{user}", member.mention).replace("{alliance}", alliance_name)
            embed = discord.Embed(
                title=f"⭐  Welcome to {member.guild.name}, {member.display_name}.",
                description=custom,
                color=discord.Color.dark_red(),
            )
            embed.set_footer(text=f"{alliance_name}")
            if member.guild.icon:
                embed.set_thumbnail(url=member.guild.icon.url)
        else:
            embed = discord.Embed(
                title=f"⭐  Welcome to {member.guild.name}, {member.display_name}.",
                description=(
                    f"Congratulations {member.mention} — you've found your way to **{member.guild.name}**.\n"
                    "Whether you wandered in by accident or actually meant to be here, you're stuck with us now.\n\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"📋 **Tickets & Membership**\n"
                    f"Head over to {ticket_link} to open an **Embassy** or **Membership** ticket.\n"
                    f"Want to join {alliance_name}? Membership ticket. Representing another alliance? Embassy ticket.\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "Click the button below to get started. "
                    "A staff member will review your application shortly."
                ),
                color=discord.Color.dark_red(),
            )
            embed.set_footer(text=f"{alliance_name}  •  You've been warned.")
            if member.guild.icon:
                embed.set_thumbnail(url=member.guild.icon.url)

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

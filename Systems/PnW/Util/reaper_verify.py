from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from PnWHarvester.db.global_nations_db import GlobalNationsDB
from Systems.Functions.config import ARIES_USER_ID
from Systems.Functions.db_paths import GLOBAL_NATIONS_DB, VERIFIED_DB_STR
from Systems.Functions.nation_emoji_store import strip_emoji_prefix

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_nation_query(value: str) -> str:
    return strip_emoji_prefix(str(value or "").strip())


class VerifiedDB:
    """SQLite helper for Discord user -> PnW nation verification mappings."""

    def __init__(self, db_path: str = VERIFIED_DB_STR):
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=15000")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS verified_users (
                    discord_id           TEXT    PRIMARY KEY,
                    nation_id            INTEGER NOT NULL UNIQUE,
                    nation_name          TEXT    NOT NULL,
                    leader_name          TEXT,
                    alliance_id          INTEGER,
                    alliance_name        TEXT,
                    discord_username     TEXT,
                    discord_display_name TEXT,
                    pnw_discord_id       TEXT,
                    source               TEXT    NOT NULL DEFAULT 'reaper_verify',
                    verified_at          TEXT    NOT NULL,
                    updated_at           TEXT    NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS verification_history (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    discord_id           TEXT    NOT NULL,
                    nation_id            INTEGER NOT NULL,
                    nation_name          TEXT    NOT NULL,
                    previous_discord_id  TEXT,
                    action               TEXT    NOT NULL,
                    created_at           TEXT    NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pnw_admins (
                    discord_id           TEXT    PRIMARY KEY,
                    discord_username     TEXT,
                    discord_display_name TEXT,
                    granted_by           TEXT    NOT NULL,
                    granted_at           TEXT    NOT NULL,
                    updated_at           TEXT    NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pnw_admin_history (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    discord_id           TEXT    NOT NULL,
                    discord_username     TEXT,
                    action               TEXT    NOT NULL,
                    actor_discord_id     TEXT    NOT NULL,
                    created_at           TEXT    NOT NULL
                )
                """
            )
            # ── Pending verification challenges (TTL: 30 minutes) ──────────
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_verifications (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    discord_id   TEXT    NOT NULL,
                    nation_id    INTEGER NOT NULL,
                    nation_name  TEXT    NOT NULL,
                    passphrase   TEXT    NOT NULL,
                    created_at   TEXT    NOT NULL,
                    expires_at   TEXT    NOT NULL,
                    last_send_at TEXT,
                    attempts     INTEGER NOT NULL DEFAULT 0,
                    used         INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            # ── Approved alliances (members may access protected web pages) ─
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS approved_alliances (
                    alliance_id   INTEGER PRIMARY KEY,
                    alliance_name TEXT    NOT NULL,
                    granted_by    TEXT    NOT NULL,
                    granted_at    TEXT    NOT NULL,
                    note          TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_verified_nation_id "
                "ON verified_users(nation_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_verified_alliance_id "
                "ON verified_users(alliance_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pnw_admin_history_discord_id "
                "ON pnw_admin_history(discord_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pending_discord "
                "ON pending_verifications(discord_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_pending_expires "
                "ON pending_verifications(expires_at)"
            )
            conn.commit()

    async def _run(self, work):
        async with self._lock:
            return await asyncio.to_thread(work)

    async def upsert_user(
        self,
        *,
        discord_id: str,
        nation: Dict[str, Any],
        discord_username: Optional[str] = None,
        discord_display_name: Optional[str] = None,
        source: str = "reaper_verify",
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """Save a current one-to-one Discord <-> nation mapping.

        If another Discord user was linked to this nation, that stale row is
        replaced so nation lookups always return one mention target.
        """

        nation_id = int(nation["id"])
        nation_name = str(nation.get("nation_name") or f"Nation {nation_id}")
        now = _utc_now()

        def _work() -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
            with self._connect() as conn:
                previous_row = conn.execute(
                    """
                    SELECT * FROM verified_users
                    WHERE nation_id = ? AND discord_id != ?
                    """,
                    (nation_id, discord_id),
                ).fetchone()
                previous = dict(previous_row) if previous_row else None

                existing_row = conn.execute(
                    "SELECT * FROM verified_users WHERE discord_id = ?",
                    (discord_id,),
                ).fetchone()
                verified_at = (
                    str(existing_row["verified_at"])
                    if existing_row and existing_row["verified_at"]
                    else now
                )

                if previous:
                    conn.execute(
                        "DELETE FROM verified_users WHERE discord_id = ?",
                        (previous["discord_id"],),
                    )

                conn.execute(
                    """
                    INSERT INTO verified_users (
                        discord_id, nation_id, nation_name, leader_name,
                        alliance_id, alliance_name, discord_username,
                        discord_display_name, pnw_discord_id, source,
                        verified_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(discord_id) DO UPDATE SET
                        nation_id = excluded.nation_id,
                        nation_name = excluded.nation_name,
                        leader_name = excluded.leader_name,
                        alliance_id = excluded.alliance_id,
                        alliance_name = excluded.alliance_name,
                        discord_username = excluded.discord_username,
                        discord_display_name = excluded.discord_display_name,
                        pnw_discord_id = excluded.pnw_discord_id,
                        source = excluded.source,
                        updated_at = excluded.updated_at
                    """,
                    (
                        discord_id,
                        nation_id,
                        nation_name,
                        nation.get("leader_name"),
                        nation.get("alliance_id"),
                        nation.get("alliance_name"),
                        discord_username,
                        discord_display_name,
                        str(nation.get("discord_id") or "") or None,
                        source,
                        verified_at,
                        now,
                    ),
                )

                conn.execute(
                    """
                    INSERT INTO verification_history (
                        discord_id, nation_id, nation_name,
                        previous_discord_id, action, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        discord_id,
                        nation_id,
                        nation_name,
                        previous["discord_id"] if previous else None,
                        "upsert",
                        now,
                    ),
                )

                current = conn.execute(
                    "SELECT * FROM verified_users WHERE discord_id = ?",
                    (discord_id,),
                ).fetchone()
                conn.commit()
                return dict(current), previous

        return await self._run(_work)

    async def get_by_discord_id(self, discord_id: str) -> Optional[Dict[str, Any]]:
        def _work() -> Optional[Dict[str, Any]]:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM verified_users WHERE discord_id = ?",
                    (str(discord_id),),
                ).fetchone()
                return dict(row) if row else None

        return await self._run(_work)

    async def get_by_nation_id(self, nation_id: int) -> Optional[Dict[str, Any]]:
        def _work() -> Optional[Dict[str, Any]]:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM verified_users WHERE nation_id = ?",
                    (int(nation_id),),
                ).fetchone()
                return dict(row) if row else None

        return await self._run(_work)

    async def get_all_verified(self) -> List[Dict[str, Any]]:
        def _work() -> List[Dict[str, Any]]:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM verified_users ORDER BY updated_at DESC"
                ).fetchall()
                return [dict(row) for row in rows]

        return await self._run(_work)

    async def get_mention_for_nation(self, nation_id: int) -> Optional[str]:
        row = await self.get_by_nation_id(nation_id)
        if not row or not row.get("discord_id"):
            return None
        return f"<@{row['discord_id']}>"

    async def grant_pnw_admin(
        self,
        *,
        discord_id: str,
        granted_by: str,
        discord_username: Optional[str] = None,
        discord_display_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = _utc_now()

        def _work() -> Dict[str, Any]:
            with self._connect() as conn:
                existing_row = conn.execute(
                    "SELECT granted_at FROM pnw_admins WHERE discord_id = ?",
                    (str(discord_id),),
                ).fetchone()
                granted_at = (
                    str(existing_row["granted_at"])
                    if existing_row and existing_row["granted_at"]
                    else now
                )
                conn.execute(
                    """
                    INSERT INTO pnw_admins (
                        discord_id, discord_username, discord_display_name,
                        granted_by, granted_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(discord_id) DO UPDATE SET
                        discord_username = excluded.discord_username,
                        discord_display_name = excluded.discord_display_name,
                        granted_by = excluded.granted_by,
                        updated_at = excluded.updated_at
                    """,
                    (
                        str(discord_id),
                        discord_username,
                        discord_display_name,
                        str(granted_by),
                        granted_at,
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO pnw_admin_history (
                        discord_id, discord_username, action,
                        actor_discord_id, created_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (str(discord_id), discord_username, "grant", str(granted_by), now),
                )
                row = conn.execute(
                    "SELECT * FROM pnw_admins WHERE discord_id = ?",
                    (str(discord_id),),
                ).fetchone()
                conn.commit()
                return dict(row)

        return await self._run(_work)

    async def revoke_pnw_admin(self, discord_id: str, revoked_by: str) -> bool:
        now = _utc_now()

        def _work() -> bool:
            with self._connect() as conn:
                existing = conn.execute(
                    "SELECT * FROM pnw_admins WHERE discord_id = ?",
                    (str(discord_id),),
                ).fetchone()
                if not existing:
                    return False
                conn.execute(
                    "DELETE FROM pnw_admins WHERE discord_id = ?",
                    (str(discord_id),),
                )
                conn.execute(
                    """
                    INSERT INTO pnw_admin_history (
                        discord_id, discord_username, action,
                        actor_discord_id, created_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        str(discord_id),
                        existing["discord_username"],
                        "revoke",
                        str(revoked_by),
                        now,
                    ),
                )
                conn.commit()
                return True

        return await self._run(_work)

    async def is_pnw_admin(self, discord_id: str) -> bool:
        if str(discord_id) == str(ARIES_USER_ID):
            return True

        def _work() -> bool:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT 1 FROM pnw_admins WHERE discord_id = ? LIMIT 1",
                    (str(discord_id),),
                ).fetchone()
                return row is not None

        return await self._run(_work)

    async def get_pnw_admin(self, discord_id: str) -> Optional[Dict[str, Any]]:
        def _work() -> Optional[Dict[str, Any]]:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM pnw_admins WHERE discord_id = ?",
                    (str(discord_id),),
                ).fetchone()
                return dict(row) if row else None

        return await self._run(_work)

    # ── Pending Verifications ──────────────────────────────────────────────

    async def create_pending_verification(
        self,
        *,
        discord_id: str,
        nation_id: int,
        nation_name: str,
        passphrase: str,
    ) -> None:
        """Insert a new pending verification row with a 30-minute TTL."""
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        expires_iso = (now + timedelta(minutes=30)).isoformat()

        def _work() -> None:
            with self._connect() as conn:
                # Expire any prior pending rows for this user first
                conn.execute(
                    "UPDATE pending_verifications SET used = 1 WHERE discord_id = ?",
                    (discord_id,),
                )
                conn.execute(
                    """
                    INSERT INTO pending_verifications
                        (discord_id, nation_id, nation_name, passphrase,
                         created_at, expires_at, last_send_at, attempts, used)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0)
                    """,
                    (discord_id, nation_id, nation_name, passphrase,
                     now_iso, expires_iso, now_iso),
                )
                conn.commit()

        await self._run(_work)

    async def expire_pending_verifications(self, discord_id: str) -> None:
        """Mark all pending verifications for a discord_id as used/expired."""
        def _work() -> None:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE pending_verifications SET used = 1 WHERE discord_id = ?",
                    (discord_id,),
                )
                conn.commit()

        await self._run(_work)

    async def get_pending_verification(self, discord_id: str) -> Optional[Dict[str, Any]]:
        """Return the most recent unexpired, unused pending verification for a user."""
        now_iso = datetime.now(timezone.utc).isoformat()

        def _work() -> Optional[Dict[str, Any]]:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT * FROM pending_verifications
                    WHERE discord_id = ? AND used = 0 AND expires_at > ?
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (discord_id, now_iso),
                ).fetchone()
                return dict(row) if row else None

        return await self._run(_work)

    async def get_last_send_at(self, discord_id: str) -> Optional[str]:
        """Return the last_send_at timestamp from the most recent pending verification.
        
        Uses a 1-hour cutoff to ensure the 5-minute cooldown is enforced for the entire
        verification session (30-minute expiry window). The 24-hour cutoff was too long
        and allowed cooldown bypass if user waited >24 hours between attempts.
        """
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        def _work() -> Optional[str]:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT last_send_at FROM pending_verifications
                    WHERE discord_id = ? AND created_at > ?
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (discord_id, cutoff),
                ).fetchone()
                return str(row["last_send_at"]) if row and row["last_send_at"] else None

        return await self._run(_work)

    async def consume_pending_verification(
        self,
        *,
        discord_id: str,
        passphrase: str,
    ) -> Dict[str, Any]:
        """
        Validate the passphrase, mark the pending verification used if correct,
        and return a status dict:
            'success'         — correct; call upsert_user separately
            'expired'         — no valid pending row found
            'wrong_passphrase'— passphrase didn't match
            'max_attempts'    — exceeded 5 attempts; row invalidated
        On 'success', also returns 'nation_id' and 'nation_name'.
        """
        MAX_ATTEMPTS = 5
        now_iso = datetime.now(timezone.utc).isoformat()

        def _work() -> Dict[str, Any]:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT * FROM pending_verifications
                    WHERE discord_id = ? AND used = 0 AND expires_at > ?
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (discord_id, now_iso),
                ).fetchone()

                if not row:
                    return {"status": "expired"}

                row = dict(row)

                if row["passphrase"].strip().lower() != passphrase.strip().lower():
                    new_attempts = row["attempts"] + 1
                    if new_attempts >= MAX_ATTEMPTS:
                        conn.execute(
                            "UPDATE pending_verifications SET used = 1, attempts = ? WHERE id = ?",
                            (new_attempts, row["id"]),
                        )
                        conn.commit()
                        logger.warning(
                            "Verification lockout: discord_id=%s, nation_id=%d, attempts=%d",
                            discord_id, row["nation_id"], new_attempts,
                        )
                        return {"status": "max_attempts"}
                    conn.execute(
                        "UPDATE pending_verifications SET attempts = ? WHERE id = ?",
                        (new_attempts, row["id"]),
                    )
                    conn.commit()
                    return {
                        "status": "wrong_passphrase",
                        "attempts_remaining": MAX_ATTEMPTS - new_attempts,
                    }

                # Correct — mark used
                conn.execute(
                    "UPDATE pending_verifications SET used = 1 WHERE id = ?",
                    (row["id"],),
                )
                conn.commit()
                return {
                    "status": "success",
                    "nation_id": row["nation_id"],
                    "nation_name": row["nation_name"],
                }

        return await self._run(_work)

    async def cleanup_expired_pending(self) -> int:
        """Delete all expired or used pending verifications. Returns rows deleted."""
        now_iso = datetime.now(timezone.utc).isoformat()

        def _work() -> int:
            with self._connect() as conn:
                cur = conn.execute(
                    "DELETE FROM pending_verifications WHERE used = 1 OR expires_at <= ?",
                    (now_iso,),
                )
                conn.commit()
                return cur.rowcount

        return await self._run(_work)

    # ── Approved Alliances ─────────────────────────────────────────────────

    async def grant_alliance_access(
        self,
        *,
        alliance_id: int,
        alliance_name: str,
        granted_by: str,
        note: Optional[str] = None,
    ) -> None:
        """Upsert an approved alliance."""
        now_iso = _utc_now()

        def _work() -> None:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO approved_alliances
                        (alliance_id, alliance_name, granted_by, granted_at, note)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(alliance_id) DO UPDATE SET
                        alliance_name = excluded.alliance_name,
                        granted_by    = excluded.granted_by,
                        granted_at    = excluded.granted_at,
                        note          = excluded.note
                    """,
                    (alliance_id, alliance_name, granted_by, now_iso, note),
                )
                conn.commit()

        await self._run(_work)

    async def revoke_alliance_access(self, alliance_id: int) -> bool:
        """Remove an approved alliance. Returns True if a row was deleted."""
        def _work() -> bool:
            with self._connect() as conn:
                cur = conn.execute(
                    "DELETE FROM approved_alliances WHERE alliance_id = ?",
                    (int(alliance_id),),
                )
                conn.commit()
                return cur.rowcount > 0

        return await self._run(_work)

    async def is_alliance_approved(self, alliance_id: int) -> bool:
        """Return True if the alliance is in the approved list."""
        def _work() -> bool:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT 1 FROM approved_alliances WHERE alliance_id = ? LIMIT 1",
                    (int(alliance_id),),
                ).fetchone()
                return row is not None

        return await self._run(_work)

    async def get_approved_alliances(self) -> List[Dict[str, Any]]:
        """Return all approved alliances ordered by most recently granted."""
        def _work() -> List[Dict[str, Any]]:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM approved_alliances ORDER BY granted_at DESC"
                ).fetchall()
                return [dict(r) for r in rows]

        return await self._run(_work)


_verified_db: Optional[VerifiedDB] = None


def get_verified_db() -> VerifiedDB:
    global _verified_db
    if _verified_db is None:
        _verified_db = VerifiedDB()
    return _verified_db


async def get_verified_by_discord_id(discord_id: str) -> Optional[Dict[str, Any]]:
    return await get_verified_db().get_by_discord_id(str(discord_id))


async def get_verified_by_nation_id(nation_id: int) -> Optional[Dict[str, Any]]:
    return await get_verified_db().get_by_nation_id(int(nation_id))


async def get_verified_mention_for_nation(nation_id: int) -> Optional[str]:
    return await get_verified_db().get_mention_for_nation(int(nation_id))


async def resolve_verified_discord_id(nation_id: int) -> Optional[str]:
    row = await get_verified_by_nation_id(nation_id)
    return str(row["discord_id"]) if row and row.get("discord_id") else None


async def is_pnw_admin(discord_id: int | str) -> bool:
    return await get_verified_db().is_pnw_admin(str(discord_id))


async def resolve_nation_from_global_db(nation_query: str) -> Optional[Dict[str, Any]]:
    clean_query = _clean_nation_query(nation_query)
    if not clean_query:
        return None

    db = GlobalNationsDB(str(GLOBAL_NATIONS_DB))
    if clean_query.isdigit():
        return await db.get_nation(int(clean_query))

    nation = await db.get_nation_by_name(clean_query)
    if nation:
        return nation

    def _leader_lookup() -> Optional[Dict[str, Any]]:
        with sqlite3.connect(str(GLOBAL_NATIONS_DB), timeout=15) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT * FROM nations
                WHERE leader_name = ? COLLATE NOCASE
                LIMIT 1
                """,
                (clean_query,),
            ).fetchone()
            return dict(row) if row else None

    return await asyncio.to_thread(_leader_lookup)


class ReaperVerify(commands.Cog):
    """User-facing command for saving Reaper-owned verification mappings."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.verified_db = get_verified_db()

    async def _is_pnw_admin(self, user_id: int) -> bool:
        return await self.verified_db.is_pnw_admin(str(user_id))

    def _is_aries(self, user_id: int) -> bool:
        return str(user_id) == str(ARIES_USER_ID)

    async def _nation_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        try:
            from Systems.Functions.autocomplete_utils import nation_autocomplete

            return await nation_autocomplete(current, nw_only=False, limit=25)
        except Exception as e:
            logger.error(f"Error in reaper_verify nation autocomplete: {e}")
            return []

    @commands.hybrid_command(
        name="reaper_verify",
        description="Link your Discord account to a P&W nation for Reaper reminders.",
    )
    @app_commands.describe(nation="Nation name or ID")
    @app_commands.autocomplete(nation=_nation_autocomplete)
    async def reaper_verify_command(
        self,
        ctx: commands.Context,
        nation: str,
    ) -> None:
        await ctx.defer(ephemeral=True)

        clean_query = _clean_nation_query(nation)
        nation_data = await resolve_nation_from_global_db(clean_query)
        if not nation_data:
            await ctx.send(
                f"Could not find a nation matching `{clean_query}` in GlobalNations.db.",
                ephemeral=True,
            )
            return

        user = ctx.author
        row, previous = await self.verified_db.upsert_user(
            discord_id=str(user.id),
            nation=nation_data,
            discord_username=str(user),
            discord_display_name=getattr(user, "display_name", None),
        )

        nation_id = int(row["nation_id"])
        nation_name = row["nation_name"]
        nation_url = f"https://politicsandwar.com/nation/id={nation_id}"

        embed = discord.Embed(
            title="Reaper verification saved",
            description=(
                f"{user.mention} is linked to "
                f"[{nation_name}]({nation_url})."
            ),
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Discord ID", value=str(user.id), inline=True)
        embed.add_field(name="Nation ID", value=str(nation_id), inline=True)
        if row.get("leader_name"):
            embed.add_field(name="Leader", value=str(row["leader_name"]), inline=True)
        if row.get("alliance_name") or row.get("alliance_id"):
            alliance = row.get("alliance_name") or "Unknown"
            if row.get("alliance_id"):
                alliance = f"{alliance} ({row['alliance_id']})"
            embed.add_field(name="Alliance", value=str(alliance), inline=False)
        if previous:
            embed.add_field(
                name="Updated stale mapping",
                value=(
                    f"Nation {nation_id} was previously linked to "
                    f"<@{previous['discord_id']}> and now points to you."
                ),
                inline=False,
            )
        embed.set_footer(text="Stored in Databases/PnW/Verified.db")

        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(
        name="reaper_verify_others",
        description="Admin: link a Discord user to a P&W nation for Reaper reminders.",
    )
    @app_commands.describe(
        nation="Nation name or ID",
        user="Discord server member to link to the nation",
    )
    @app_commands.autocomplete(nation=_nation_autocomplete)
    async def reaper_verify_others_command(
        self,
        ctx: commands.Context,
        nation: str,
        user: discord.Member,
    ) -> None:
        await ctx.defer(ephemeral=True)

        if not await self._is_pnw_admin(ctx.author.id):
            await ctx.send(
                "You do not have permission to use `/reaper_verify_others`.",
                ephemeral=True,
            )
            return

        clean_query = _clean_nation_query(nation)
        nation_data = await resolve_nation_from_global_db(clean_query)
        if not nation_data:
            await ctx.send(
                f"Could not find a nation matching `{clean_query}` in GlobalNations.db.",
                ephemeral=True,
            )
            return

        row, previous = await self.verified_db.upsert_user(
            discord_id=str(user.id),
            nation=nation_data,
            discord_username=str(user),
            discord_display_name=getattr(user, "display_name", None),
            source="reaper_verify_others",
        )

        nation_id = int(row["nation_id"])
        nation_name = row["nation_name"]
        nation_url = f"https://politicsandwar.com/nation/id={nation_id}"

        embed = discord.Embed(
            title="Reaper verification saved for user",
            description=(
                f"{user.mention} is linked to "
                f"[{nation_name}]({nation_url})."
            ),
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Discord ID", value=str(user.id), inline=True)
        embed.add_field(name="Nation ID", value=str(nation_id), inline=True)
        if row.get("leader_name"):
            embed.add_field(name="Leader", value=str(row["leader_name"]), inline=True)
        if row.get("alliance_name") or row.get("alliance_id"):
            alliance = row.get("alliance_name") or "Unknown"
            if row.get("alliance_id"):
                alliance = f"{alliance} ({row['alliance_id']})"
            embed.add_field(name="Alliance", value=str(alliance), inline=False)
        if previous:
            embed.add_field(
                name="Updated stale mapping",
                value=(
                    f"Nation {nation_id} was previously linked to "
                    f"<@{previous['discord_id']}> and now points to {user.mention}."
                ),
                inline=False,
            )
        embed.set_footer(text="Stored in Databases/PnW/Verified.db")

        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(
        name="pnw_admin_grant",
        description="Aries: grant PnW admin access for Reaper verification commands.",
    )
    @app_commands.describe(user="Discord server member to grant PnW admin access")
    async def pnw_admin_grant_command(
        self,
        ctx: commands.Context,
        user: discord.Member,
    ) -> None:
        await ctx.defer(ephemeral=True)

        if not self._is_aries(ctx.author.id):
            await ctx.send("Only Aries can grant PnW admin access.", ephemeral=True)
            return

        row = await self.verified_db.grant_pnw_admin(
            discord_id=str(user.id),
            granted_by=str(ctx.author.id),
            discord_username=str(user),
            discord_display_name=getattr(user, "display_name", None),
        )

        embed = discord.Embed(
            title="PnW admin granted",
            description=f"{user.mention} can now use PnW admin verification commands.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Discord ID", value=str(row["discord_id"]), inline=True)
        embed.add_field(name="Granted By", value=f"<@{row['granted_by']}>", inline=True)
        embed.set_footer(text="Stored in Databases/PnW/Verified.db")
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(
        name="pnw_admin_revoke",
        description="Aries: revoke PnW admin access for Reaper verification commands.",
    )
    @app_commands.describe(user="Discord server member to revoke PnW admin access from")
    async def pnw_admin_revoke_command(
        self,
        ctx: commands.Context,
        user: discord.Member,
    ) -> None:
        await ctx.defer(ephemeral=True)

        if not self._is_aries(ctx.author.id):
            await ctx.send("Only Aries can revoke PnW admin access.", ephemeral=True)
            return

        if str(user.id) == str(ARIES_USER_ID):
            await ctx.send("Aries is always a PnW admin and cannot be revoked.", ephemeral=True)
            return

        removed = await self.verified_db.revoke_pnw_admin(
            discord_id=str(user.id),
            revoked_by=str(ctx.author.id),
        )
        if not removed:
            await ctx.send(f"{user.mention} was not a saved PnW admin.", ephemeral=True)
            return

        embed = discord.Embed(
            title="PnW admin revoked",
            description=f"{user.mention} can no longer use PnW admin verification commands.",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Discord ID", value=str(user.id), inline=True)
        embed.add_field(name="Revoked By", value=ctx.author.mention, inline=True)
        embed.set_footer(text="Stored in Databases/PnW/Verified.db")
        await ctx.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReaperVerify(bot))
    logger.info("ReaperVerify cog loaded successfully")

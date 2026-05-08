"""
beige_alerts_db.py — Shared beige alert DB helpers.

Imported by both the harvester (turn_revenue_loop, nations_subscription,
wars_subscription) and the reaper (raids_api, _beige_notification_loop).

All functions are async and use aiosqlite so they are safe to call from any
asyncio context.  SQLite WAL mode is enabled on every connection so concurrent
readers/writers from two separate processes (harvester + reaper) don't block
each other.

Schema managed here:
  beige_alerts          — one row per (user_id, nation_id) alert
  beige_early_exit_queue — pending "left beige early" notifications for reaper
                           to send as Discord DMs
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import aiosqlite

from Systems.Functions.db_paths import ALERTS_DB_STR as ALERTS_DB

logger = logging.getLogger(__name__)

# ── Schema ────────────────────────────────────────────────────────────────────

_ENSURE_DONE = False  # module-level flag so we only migrate once per process


async def ensure_schema() -> None:
    """Create / migrate both tables.  Safe to call multiple times."""
    global _ENSURE_DONE
    if _ENSURE_DONE:
        return
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        # ── beige_alerts ──────────────────────────────────────────────────────
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS beige_alerts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         TEXT    NOT NULL,
                nation_id       TEXT    NOT NULL,
                nation_name     TEXT    NOT NULL,
                beige_turns     INTEGER NOT NULL,
                projected_loot  REAL    NOT NULL DEFAULT 0,
                accumulated_rev REAL    NOT NULL DEFAULT 0,
                warned_turn     INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                UNIQUE(user_id, nation_id)
            )
        """)
        for col, typedef in [
            ("projected_loot",  "REAL NOT NULL DEFAULT 0"),
            ("accumulated_rev", "REAL NOT NULL DEFAULT 0"),
            ("warned_turn",     "INTEGER NOT NULL DEFAULT 0"),
        ]:
            try:
                await conn.execute(f"ALTER TABLE beige_alerts ADD COLUMN {col} {typedef}")
            except Exception:
                pass

        # ── beige_early_exit_queue ────────────────────────────────────────────
        # Written by the harvester when it detects a nation left beige early.
        # Read + deleted by the reaper's notification loop to send Discord DMs.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS beige_early_exit_queue (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         TEXT    NOT NULL,
                nation_id       TEXT    NOT NULL,
                nation_name     TEXT    NOT NULL,
                projected_loot  REAL    NOT NULL DEFAULT 0,
                queued_at       TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await conn.commit()
    _ENSURE_DONE = True


# ── beige_alerts helpers ──────────────────────────────────────────────────────

async def get_all_beige_alerts() -> List[Dict[str, Any]]:
    await ensure_schema()
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM beige_alerts")
        return [dict(r) for r in await cur.fetchall()]


async def get_beige_alerts_for_nation(nation_id: int) -> List[Dict[str, Any]]:
    """Return all alerts (across all users) for a specific nation."""
    await ensure_schema()
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM beige_alerts WHERE nation_id=?",
            (str(nation_id),),
        )
        return [dict(r) for r in await cur.fetchall()]


async def update_beige_alert_turns(alert_id: int, beige_turns: int) -> None:
    """Update beige_turns for a single alert row."""
    await ensure_schema()
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute(
            "UPDATE beige_alerts SET beige_turns=? WHERE id=?",
            (beige_turns, alert_id),
        )
        await conn.commit()


async def update_beige_alert_turns_and_loot(
    alert_id: int,
    beige_turns: int,
    projected_loot: float,
) -> None:
    """Update beige_turns + projected_loot for a single alert row."""
    await ensure_schema()
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute(
            "UPDATE beige_alerts SET beige_turns=?, projected_loot=? WHERE id=?",
            (beige_turns, projected_loot, alert_id),
        )
        await conn.commit()


async def delete_beige_alert_by_id(alert_id: int) -> None:
    await ensure_schema()
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("DELETE FROM beige_alerts WHERE id=?", (alert_id,))
        await conn.commit()


async def delete_beige_alerts_for_nation(nation_id: int) -> int:
    """Delete ALL alerts for a nation (all users).  Returns rows deleted."""
    await ensure_schema()
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        cur = await conn.execute(
            "DELETE FROM beige_alerts WHERE nation_id=?",
            (str(nation_id),),
        )
        await conn.commit()
        return cur.rowcount


async def mark_beige_alert_warned(alert_id: int) -> None:
    await ensure_schema()
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute(
            "UPDATE beige_alerts SET warned_turn=1 WHERE id=?",
            (alert_id,),
        )
        await conn.commit()


async def upsert_beige_alert(
    user_id: str,
    nation_id: str,
    nation_name: str,
    beige_turns: int,
    projected_loot: float = 0.0,
    accumulated_rev: float = 0.0,
) -> None:
    await ensure_schema()
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("""
            INSERT INTO beige_alerts
                (user_id, nation_id, nation_name, beige_turns, projected_loot, accumulated_rev)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, nation_id)
            DO UPDATE SET
                nation_name     = excluded.nation_name,
                beige_turns     = excluded.beige_turns,
                projected_loot  = excluded.projected_loot,
                accumulated_rev = excluded.accumulated_rev,
                warned_turn     = 0,
                created_at      = datetime('now')
        """, (user_id, nation_id, nation_name, beige_turns, projected_loot, accumulated_rev))
        await conn.commit()


async def batch_update_beige_alerts(
    to_update: List[tuple],   # (beige_turns, projected_loot, alert_id)
    to_delete: List[int],     # alert_ids to remove
) -> None:
    """Apply bulk beige_turns + projected_loot updates and deletions in one connection."""
    if not to_update and not to_delete:
        return
    await ensure_schema()
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        if to_update:
            await conn.executemany(
                "UPDATE beige_alerts SET beige_turns=?, projected_loot=? WHERE id=?",
                to_update,
            )
        if to_delete:
            await conn.executemany(
                "DELETE FROM beige_alerts WHERE id=?",
                [(aid,) for aid in to_delete],
            )
        await conn.commit()


# ── beige_early_exit_queue helpers ────────────────────────────────────────────

async def enqueue_early_exit(
    user_id: str,
    nation_id: str,
    nation_name: str,
    projected_loot: float = 0.0,
) -> None:
    """
    Called by the harvester when it detects a nation left beige early.
    The reaper's notification loop drains this queue and sends Discord DMs.
    """
    await ensure_schema()
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("""
            INSERT INTO beige_early_exit_queue
                (user_id, nation_id, nation_name, projected_loot)
            VALUES (?, ?, ?, ?)
        """, (user_id, nation_id, nation_name, projected_loot))
        await conn.commit()
    logger.info(
        f"beige_early_exit_queue: enqueued early-exit for nation {nation_id} "
        f"({nation_name}) user={user_id}"
    )


async def drain_early_exit_queue() -> List[Dict[str, Any]]:
    """
    Atomically read and delete all pending early-exit notifications.
    Called by the reaper's notification loop.
    Returns the rows that were removed (so the caller can send DMs).
    """
    await ensure_schema()
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM beige_early_exit_queue ORDER BY id ASC")
        rows = [dict(r) for r in await cur.fetchall()]
        if rows:
            ids = [r["id"] for r in rows]
            ph  = ",".join("?" * len(ids))
            await conn.execute(f"DELETE FROM beige_early_exit_queue WHERE id IN ({ph})", ids)
            await conn.commit()
    return rows


# ── Expiry helper (shared between harvester and reaper) ───────────────────────

def compute_beige_expiry_utc(beige_turns: int) -> datetime:
    """
    Compute the UTC datetime when a nation's beige expires.

    Expiry = current_turn_boundary + beige_turns × 2 hours.

    PnW turns fire at 00:00, 02:00, 04:00 … 22:00 UTC (every 2 hours).
    beige_turns is the live value from GlobalNations.db, so anchoring to the
    current turn boundary is always accurate.
    """
    now = datetime.now(timezone.utc)
    hour_snapped = (now.hour // 2) * 2
    current_turn_start = now.replace(hour=hour_snapped, minute=0, second=0, microsecond=0)
    return current_turn_start + timedelta(hours=beige_turns * 2)

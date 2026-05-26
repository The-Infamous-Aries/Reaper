"""
beige_alerts_db.py — Shared beige alert DB helpers.

Imported by both the harvester (turn_revenue_loop, nations_subscription,
wars_subscription) and the reaper (raids_api, _beige_notification_loop).

Now uses BeigeAlertDB class inheriting from BaseDB for unified locking
and connection management. Module-level functions are provided for backward
compatibility.

Schema managed here:
  beige_alerts          — one row per (user_id, nation_id) alert
  beige_early_exit_queue — pending "left beige early" notifications for reaper
                           to send as Discord DMs
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import aiosqlite

from Systems.Functions.db_paths import ALERTS_DB_STR as ALERTS_DB

logger = logging.getLogger(__name__)

# ── Shared loot constants (used by harvester + reaper without web dependency) ─
# These mirror LOOT_MULTIPLIERS / RESOURCES in web/api/raids_api.py.
# Keep in sync if the raid loot formula changes.
LOOT_MULTIPLIERS: Dict[str, Any] = {
    "war_type": {
        "ordinary_war":  0.10,
        "raid":          0.075,
        "attrition_war": 0.12,
        "blockade":      0.05,
    },
    "offense": {"pirate": 1.4, "ape": 1.1},
    "defense": {"fortress": 0.9, "moneybags": 0.6, "turtle": 1.2, "pirate": 1.1},
}

RESOURCES: tuple = (
    "coal", "oil", "uranium", "iron", "bauxite", "lead",
    "gasoline", "munitions", "steel", "aluminum", "food",
)

# ── BeigeAlertDB Class (inherits from BaseDB) ───────────────────────────────────

try:
    from PnWHarvester.db.base_db import BaseDB, AsyncMode
    
    class BeigeAlertDB(BaseDB):
        """
        Beige alert database handler inheriting from BaseDB.
        
        Provides unified locking and connection management for beige alerts
        and early exit queue.
        """
        
        def __init__(self, db_path: str = ALERTS_DB):
            """
            Initialize BeigeAlertDB.
            
            Args:
                db_path: Path to the alerts database file
            """
            super().__init__(
                db_path=db_path,
                async_mode=AsyncMode.THREAD_POOL,
                wal_mode=True,
                synchronous="NORMAL",
                busy_timeout=15000,
                wal_autocheckpoint=1000,
                enable_locking=True,
                use_lock_manager=True,
            )
            self._init_beige_alert_schema()
        
        def _init_beige_alert_schema(self):
            """Initialize the beige alert schema."""
            try:
                with self._get_connection() as conn:
                    c = conn.cursor()
                    
                    # ── beige_alerts ──────────────────────────────────────────
                    c.execute("""
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
                    
                    # Add columns if they don't exist (migration)
                    for col, typedef in [
                        ("projected_loot",  "REAL NOT NULL DEFAULT 0"),
                        ("accumulated_rev", "REAL NOT NULL DEFAULT 0"),
                        ("warned_turn",     "INTEGER NOT NULL DEFAULT 0"),
                    ]:
                        self._ensure_column(c, "beige_alerts", col, typedef)
                    
                    # ── beige_early_exit_queue ────────────────────────────────────
                    c.execute("""
                        CREATE TABLE IF NOT EXISTS beige_early_exit_queue (
                            id              INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id         TEXT    NOT NULL,
                            nation_id       TEXT    NOT NULL,
                            nation_name     TEXT    NOT NULL,
                            projected_loot  REAL    NOT NULL DEFAULT 0,
                            queued_at       TEXT    NOT NULL DEFAULT (datetime('now'))
                        )
                    """)
                    
                    conn.commit()
                    logger.info("BeigeAlertDB schema initialized")
            except Exception as e:
                logger.error(f"BeigeAlertDB schema init error: {e}", exc_info=True)
                raise
        
        async def get_all_beige_alerts(self) -> List[Dict[str, Any]]:
            """Get all beige alerts."""
            async with self._get_lock():
                return await self._run_sync(self._get_all_beige_alerts_sync)
        
        def _get_all_beige_alerts_sync(self) -> List[Dict[str, Any]]:
            """Synchronous implementation of get_all_beige_alerts."""
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute("SELECT * FROM beige_alerts")
                return [dict(r) for r in cur.fetchall()]
        
        async def get_beige_alerts_for_nation(self, nation_id: int) -> List[Dict[str, Any]]:
            """Get all alerts for a specific nation."""
            async with self._get_lock():
                return await self._run_sync(
                    lambda: self._get_beige_alerts_for_nation_sync(nation_id)
                )
        
        def _get_beige_alerts_for_nation_sync(self, nation_id: int) -> List[Dict[str, Any]]:
            """Synchronous implementation of get_beige_alerts_for_nation."""
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    "SELECT * FROM beige_alerts WHERE nation_id=?",
                    (str(nation_id),),
                )
                return [dict(r) for r in cur.fetchall()]
        
        async def update_beige_alert_turns(self, alert_id: int, beige_turns: int) -> None:
            """Update beige_turns for a single alert."""
            async with self._get_lock():
                await self._run_sync(
                    lambda: self._update_beige_alert_turns_sync(alert_id, beige_turns)
                )
        
        def _update_beige_alert_turns_sync(self, alert_id: int, beige_turns: int) -> None:
            """Synchronous implementation of update_beige_alert_turns."""
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE beige_alerts SET beige_turns=? WHERE id=?",
                    (beige_turns, alert_id),
                )
                conn.commit()
        
        async def update_beige_alert_turns_and_loot(
            self, alert_id: int, beige_turns: int, projected_loot: float
        ) -> None:
            """Update beige_turns + projected_loot for a single alert."""
            async with self._get_lock():
                await self._run_sync(
                    lambda: self._update_beige_alert_turns_and_loot_sync(
                        alert_id, beige_turns, projected_loot
                    )
                )
        
        def _update_beige_alert_turns_and_loot_sync(
            self, alert_id: int, beige_turns: int, projected_loot: float
        ) -> None:
            """Synchronous implementation of update_beige_alert_turns_and_loot."""
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE beige_alerts SET beige_turns=?, projected_loot=? WHERE id=?",
                    (beige_turns, projected_loot, alert_id),
                )
                conn.commit()
        
        async def delete_beige_alert_by_id(self, alert_id: int) -> None:
            """Delete a single alert by ID."""
            async with self._get_lock():
                await self._run_sync(lambda: self._delete_beige_alert_by_id_sync(alert_id))
        
        def _delete_beige_alert_by_id_sync(self, alert_id: int) -> None:
            """Synchronous implementation of delete_beige_alert_by_id."""
            with self._get_connection() as conn:
                conn.execute("DELETE FROM beige_alerts WHERE id=?", (alert_id,))
                conn.commit()
        
        async def delete_beige_alerts_for_nation(self, nation_id: int) -> int:
            """Delete all alerts for a nation. Returns rows deleted."""
            async with self._get_lock():
                return await self._run_sync(
                    lambda: self._delete_beige_alerts_for_nation_sync(nation_id)
                )
        
        def _delete_beige_alerts_for_nation_sync(self, nation_id: int) -> int:
            """Synchronous implementation of delete_beige_alerts_for_nation."""
            with self._get_connection() as conn:
                cur = conn.execute(
                    "DELETE FROM beige_alerts WHERE nation_id=?",
                    (str(nation_id),),
                )
                conn.commit()
                return cur.rowcount
        
        async def mark_beige_alert_warned(self, alert_id: int) -> None:
            """Mark an alert as warned."""
            async with self._get_lock():
                await self._run_sync(lambda: self._mark_beige_alert_warned_sync(alert_id))
        
        def _mark_beige_alert_warned_sync(self, alert_id: int) -> None:
            """Synchronous implementation of mark_beige_alert_warned."""
            with self._get_connection() as conn:
                conn.execute(
                    "UPDATE beige_alerts SET warned_turn=1 WHERE id=?",
                    (alert_id,),
                )
                conn.commit()
        
        async def upsert_beige_alert(
            self,
            user_id: str,
            nation_id: str,
            nation_name: str,
            beige_turns: int,
            projected_loot: float = 0.0,
            accumulated_rev: float = 0.0,
        ) -> None:
            """Upsert a beige alert."""
            async with self._get_lock():
                await self._run_sync(
                    lambda: self._upsert_beige_alert_sync(
                        user_id, nation_id, nation_name, beige_turns,
                        projected_loot, accumulated_rev
                    )
                )
        
        def _upsert_beige_alert_sync(
            self,
            user_id: str,
            nation_id: str,
            nation_name: str,
            beige_turns: int,
            projected_loot: float,
            accumulated_rev: float,
        ) -> None:
            """Synchronous implementation of upsert_beige_alert."""
            with self._get_connection() as conn:
                conn.execute("""
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
                conn.commit()
        
        async def batch_update_beige_alerts(
            self, to_update: List[tuple], to_delete: List[int]
        ) -> None:
            """Apply bulk updates and deletions."""
            async with self._get_lock():
                await self._run_sync(
                    lambda: self._batch_update_beige_alerts_sync(to_update, to_delete)
                )
        
        def _batch_update_beige_alerts_sync(
            self, to_update: List[tuple], to_delete: List[int]
        ) -> None:
            """Synchronous implementation of batch_update_beige_alerts."""
            if not to_update and not to_delete:
                return
            with self._get_connection() as conn:
                if to_update:
                    conn.executemany(
                        "UPDATE beige_alerts SET beige_turns=?, projected_loot=? WHERE id=?",
                        to_update,
                    )
                if to_delete:
                    conn.executemany(
                        "DELETE FROM beige_alerts WHERE id=?",
                        [(aid,) for aid in to_delete],
                    )
                conn.commit()
        
        async def enqueue_early_exit(
            self,
            user_id: str,
            nation_id: str,
            nation_name: str,
            projected_loot: float = 0.0,
        ) -> None:
            """Enqueue an early exit notification."""
            async with self._get_lock():
                await self._run_sync(
                    lambda: self._enqueue_early_exit_sync(
                        user_id, nation_id, nation_name, projected_loot
                    )
                )
        
        def _enqueue_early_exit_sync(
            self, user_id: str, nation_id: str, nation_name: str, projected_loot: float
        ) -> None:
            """Synchronous implementation of enqueue_early_exit."""
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO beige_early_exit_queue
                        (user_id, nation_id, nation_name, projected_loot)
                    VALUES (?, ?, ?, ?)
                """, (user_id, nation_id, nation_name, projected_loot))
                conn.commit()
            logger.info(
                f"beige_early_exit_queue: enqueued early-exit for nation {nation_id} "
                f"({nation_name}) user={user_id}"
            )
        
        async def drain_early_exit_queue(self) -> List[Dict[str, Any]]:
            """Drain the early exit queue."""
            async with self._get_lock():
                return await self._run_sync(self._drain_early_exit_queue_sync)
        
        def _drain_early_exit_queue_sync(self) -> List[Dict[str, Any]]:
            """Synchronous implementation of drain_early_exit_queue."""
            with self._get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute("SELECT * FROM beige_early_exit_queue ORDER BY id ASC")
                rows = [dict(r) for r in cur.fetchall()]
                if rows:
                    ids = [r["id"] for r in rows]
                    ph = ",".join("?" * len(ids))
                    conn.execute(f"DELETE FROM beige_early_exit_queue WHERE id IN ({ph})", ids)
                    conn.commit()
                return rows
    
    # Global instance
    _beige_alert_db: Optional[BeigeAlertDB] = None
    
    def get_beige_alert_db() -> BeigeAlertDB:
        """Get the global BeigeAlertDB instance."""
        global _beige_alert_db
        if _beige_alert_db is None:
            _beige_alert_db = BeigeAlertDB()
        return _beige_alert_db

except ImportError:
    # Fallback to old implementation if BaseDB is not available
    logger.warning("BaseDB not available, using fallback implementation")
    BeigeAlertDB = None
    get_beige_alert_db = None


# ── Backward compatibility: module-level functions ───────────────────────────

_ENSURE_DONE = False  # module-level flag for fallback implementation

async def ensure_schema() -> None:
    """
    Create / migrate both tables. Safe to call multiple times.
    
    This is a fallback for when BaseDB is not available.
    """
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


# ── beige_alerts helpers (backward compatibility) ─────────────────────────────

async def get_all_beige_alerts() -> List[Dict[str, Any]]:
    """Get all beige alerts (backward compatibility wrapper)."""
    if get_beige_alert_db:
        db = get_beige_alert_db()
        return await db.get_all_beige_alerts()
    # Fallback
    await ensure_schema()
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM beige_alerts")
        return [dict(r) for r in await cur.fetchall()]


async def get_beige_alerts_for_nation(nation_id: int) -> List[Dict[str, Any]]:
    """Return all alerts (across all users) for a specific nation."""
    if get_beige_alert_db:
        db = get_beige_alert_db()
        return await db.get_beige_alerts_for_nation(nation_id)
    # Fallback
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
    if get_beige_alert_db:
        db = get_beige_alert_db()
        return await db.update_beige_alert_turns(alert_id, beige_turns)
    # Fallback
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
    if get_beige_alert_db:
        db = get_beige_alert_db()
        return await db.update_beige_alert_turns_and_loot(
            alert_id, beige_turns, projected_loot
        )
    # Fallback
    await ensure_schema()
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute(
            "UPDATE beige_alerts SET beige_turns=?, projected_loot=? WHERE id=?",
            (beige_turns, projected_loot, alert_id),
        )
        await conn.commit()


async def delete_beige_alert_by_id(alert_id: int) -> None:
    if get_beige_alert_db:
        db = get_beige_alert_db()
        return await db.delete_beige_alert_by_id(alert_id)
    # Fallback
    await ensure_schema()
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("DELETE FROM beige_alerts WHERE id=?", (alert_id,))
        await conn.commit()


async def delete_beige_alerts_for_nation(nation_id: int) -> int:
    """Delete ALL alerts for a nation (all users). Returns rows deleted."""
    if get_beige_alert_db:
        db = get_beige_alert_db()
        return await db.delete_beige_alerts_for_nation(nation_id)
    # Fallback
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
    if get_beige_alert_db:
        db = get_beige_alert_db()
        return await db.mark_beige_alert_warned(alert_id)
    # Fallback
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
    if get_beige_alert_db:
        db = get_beige_alert_db()
        return await db.upsert_beige_alert(
            user_id, nation_id, nation_name, beige_turns,
            projected_loot, accumulated_rev
        )
    # Fallback
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
    """Apply bulk beige_turns + projected_loot updates and deletions."""
    if get_beige_alert_db:
        db = get_beige_alert_db()
        return await db.batch_update_beige_alerts(to_update, to_delete)
    # Fallback
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


# ── beige_early_exit_queue helpers (backward compatibility) ───────────────────

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
    if get_beige_alert_db:
        db = get_beige_alert_db()
        return await db.enqueue_early_exit(user_id, nation_id, nation_name, projected_loot)
    # Fallback
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
    if get_beige_alert_db:
        db = get_beige_alert_db()
        return await db.drain_early_exit_queue()
    # Fallback
    await ensure_schema()
    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM beige_early_exit_queue ORDER BY id ASC")
        rows = [dict(r) for r in await cur.fetchall()]
        if rows:
            ids = [r["id"] for r in rows]
            ph = ",".join("?" * len(ids))
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

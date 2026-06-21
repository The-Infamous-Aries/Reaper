"""
TrackingDB — which alliances / nations the harvester saves full war data for.

Stored in Databases/PnW/Tracking.db
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from Systems.Functions.db_paths import TRACKING_DB_STR

logger = logging.getLogger("Reaper.TrackingDB")


class TrackingDB:
    _instance: Optional["TrackingDB"] = None

    def __new__(cls, db_path: str | None = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, db_path: str | None = None):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True
        self.db_path = db_path or TRACKING_DB_STR
        self._lock = asyncio.Lock()
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ── sync helpers ──────────────────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tracked_entities (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type  TEXT    NOT NULL CHECK(entity_type IN ('alliance','nation')),
                    entity_id    INTEGER NOT NULL,
                    entity_name  TEXT,
                    added_by     TEXT,
                    added_at     TEXT    DEFAULT (datetime('now')),
                    UNIQUE(entity_type, entity_id)
                );
                CREATE INDEX IF NOT EXISTS idx_tracked_type
                    ON tracked_entities(entity_type);
            """)
            conn.commit()
        finally:
            conn.close()

    # ── public API ────────────────────────────────────────────────────────────
    async def add_entity(
        self, entity_type: str, entity_id: int, entity_name: str = "",
        added_by: str = "",
    ) -> bool:
        """Add an alliance or nation to the tracking list.  Returns True if new."""
        async with self._lock:
            def work():
                conn = self._connect()
                try:
                    cur = conn.execute(
                        "INSERT OR IGNORE INTO tracked_entities "
                        "(entity_type, entity_id, entity_name, added_by, added_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (entity_type, entity_id, entity_name, added_by,
                         datetime.now(timezone.utc).isoformat()),
                    )
                    conn.commit()
                    return cur.rowcount > 0
                finally:
                    conn.close()
            return await asyncio.to_thread(work)

    async def remove_entity(self, entity_type: str, entity_id: int) -> bool:
        """Remove an alliance or nation from the tracking list."""
        async with self._lock:
            def work():
                conn = self._connect()
                try:
                    cur = conn.execute(
                        "DELETE FROM tracked_entities "
                        "WHERE entity_type = ? AND entity_id = ?",
                        (entity_type, entity_id),
                    )
                    conn.commit()
                    return cur.rowcount > 0
                finally:
                    conn.close()
            return await asyncio.to_thread(work)

    async def is_tracking(self, entity_type: str, entity_id: int) -> bool:
        """Check if a specific entity is being tracked."""
        def work():
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT 1 FROM tracked_entities "
                    "WHERE entity_type = ? AND entity_id = ?",
                    (entity_type, entity_id),
                ).fetchone()
                return row is not None
            finally:
                conn.close()
        return await asyncio.to_thread(work)

    async def get_tracked_alliance_ids(self) -> set[int]:
        """Return the set of alliance IDs currently tracked."""
        def work():
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT entity_id FROM tracked_entities WHERE entity_type = 'alliance'"
                ).fetchall()
                return {int(r["entity_id"]) for r in rows}
            finally:
                conn.close()
        return await asyncio.to_thread(work)

    async def get_tracked_nation_ids(self) -> set[int]:
        """Return the set of nation IDs currently tracked."""
        def work():
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT entity_id FROM tracked_entities WHERE entity_type = 'nation'"
                ).fetchall()
                return {int(r["entity_id"]) for r in rows}
            finally:
                conn.close()
        return await asyncio.to_thread(work)

    async def get_all_entities(self) -> list[dict]:
        """Return all tracked entities (for display)."""
        def work():
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM tracked_entities ORDER BY entity_type, entity_name"
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()
        return await asyncio.to_thread(work)


# singleton factory
_tracking_db_instance: TrackingDB | None = None


def get_tracking_db(db_path: str | None = None) -> TrackingDB:
    global _tracking_db_instance
    if _tracking_db_instance is None:
        _tracking_db_instance = TrackingDB(db_path)
    return _tracking_db_instance

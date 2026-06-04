"""
TreatiesDB — SQLite store for PnW alliance treaties.

Tracks every active treaty in Orbis: create, update (treaty type / URL changes),
and delete (treaty cancelled / expired).

Schema mirrors the pnwkit Treaty model:
    id, date, treaty_type, treaty_url, turns_left,
    alliance1_id, alliance1_name, alliance1_flag,
    alliance2_id, alliance2_name, alliance2_flag,
    active (1=live, 0=cancelled/expired)
"""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_db import BaseDB

logger = logging.getLogger(__name__)


class TreatiesDB(BaseDB):
    """SQLite database for PnW treaties."""

    def __init__(self, db_path: str):
        super().__init__(db_path)
        self._init_db()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS treaties (
                    id              INTEGER PRIMARY KEY,
                    date            TEXT,
                    treaty_type     TEXT,
                    treaty_url      TEXT,
                    turns_left      INTEGER DEFAULT 0,
                    alliance1_id    INTEGER,
                    alliance1_name  TEXT,
                    alliance1_flag  TEXT,
                    alliance2_id    INTEGER,
                    alliance2_name  TEXT,
                    alliance2_flag  TEXT,
                    active          INTEGER DEFAULT 1,
                    updated_at      TEXT
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_treaties_alliance1 ON treaties(alliance1_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_treaties_alliance2 ON treaties(alliance2_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_treaties_active ON treaties(active)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_treaties_type ON treaties(treaty_type)")
            conn.commit()

    # ── Write helpers ─────────────────────────────────────────────────────────

    def _extract(self, treaty: Dict[str, Any]) -> Dict[str, Any]:
        """Pull all fields out of a raw treaty dict, handling nested alliance objects."""
        a1 = treaty.get("alliance1") or {}
        a2 = treaty.get("alliance2") or {}
        if not isinstance(a1, dict):
            a1 = {}
        if not isinstance(a2, dict):
            a2 = {}

        def _str(v: Any) -> Optional[str]:
            return str(v) if v is not None else None

        def _int(v: Any) -> Optional[int]:
            try:
                return int(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        date = treaty.get("date")
        if hasattr(date, "isoformat"):
            date = date.isoformat()

        return {
            "id":             _int(treaty.get("id")),
            "date":           _str(date),
            "treaty_type":    _str(treaty.get("treaty_type")),
            "treaty_url":     _str(treaty.get("treaty_url")),
            "turns_left":     _int(treaty.get("turns_left")) or 0,
            "alliance1_id":   _int(treaty.get("alliance1_id") or a1.get("id")),
            "alliance1_name": _str(treaty.get("alliance1_name") or a1.get("name")),
            "alliance1_flag": _str(treaty.get("alliance1_flag") or a1.get("flag")),
            "alliance2_id":   _int(treaty.get("alliance2_id") or a2.get("id")),
            "alliance2_name": _str(treaty.get("alliance2_name") or a2.get("name")),
            "alliance2_flag": _str(treaty.get("alliance2_flag") or a2.get("flag")),
        }

    def _save_treaty_sync(self, treaty: Dict[str, Any], active: int = 1) -> bool:
        f = self._extract(treaty)
        if not f["id"]:
            return False
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO treaties
                    (id, date, treaty_type, treaty_url, turns_left,
                     alliance1_id, alliance1_name, alliance1_flag,
                     alliance2_id, alliance2_name, alliance2_flag,
                     active, updated_at)
                VALUES
                    (:id, :date, :treaty_type, :treaty_url, :turns_left,
                     :alliance1_id, :alliance1_name, :alliance1_flag,
                     :alliance2_id, :alliance2_name, :alliance2_flag,
                     :active, :now)
                ON CONFLICT(id) DO UPDATE SET
                    date            = COALESCE(:date,          date),
                    treaty_type     = COALESCE(:treaty_type,   treaty_type),
                    treaty_url      = COALESCE(:treaty_url,    treaty_url),
                    turns_left      = COALESCE(:turns_left,    turns_left),
                    alliance1_id    = COALESCE(:alliance1_id,  alliance1_id),
                    alliance1_name  = COALESCE(:alliance1_name,alliance1_name),
                    alliance1_flag  = COALESCE(:alliance1_flag,alliance1_flag),
                    alliance2_id    = COALESCE(:alliance2_id,  alliance2_id),
                    alliance2_name  = COALESCE(:alliance2_name,alliance2_name),
                    alliance2_flag  = COALESCE(:alliance2_flag,alliance2_flag),
                    active          = :active,
                    updated_at      = :now
            """, {**f, "active": active, "now": now})
            conn.commit()
        return True

    # ── Public async API ──────────────────────────────────────────────────────

    async def save_treaty(self, treaty: Dict[str, Any]) -> bool:
        """Upsert a treaty as active."""
        try:
            return await self._run_sync(lambda: self._save_treaty_sync(treaty, active=1))
        except Exception as e:
            logger.error(f"TreatiesDB.save_treaty: {e}", exc_info=True)
            return False

    async def delete_treaty(self, treaty_id: int) -> bool:
        """Mark a treaty as inactive (cancelled / expired)."""
        try:
            def _do():
                now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                with self._get_connection() as conn:
                    conn.execute(
                        "UPDATE treaties SET active=0, updated_at=? WHERE id=?",
                        (now, treaty_id)
                    )
                    conn.commit()
                return True
            return await self._run_sync(_do)
        except Exception as e:
            logger.error(f"TreatiesDB.delete_treaty({treaty_id}): {e}", exc_info=True)
            return False

    async def save_treaties_bulk(self, treaties: List[Dict[str, Any]]) -> int:
        """Upsert a list of treaties. Returns count saved."""
        saved = 0
        for t in treaties:
            if await self.save_treaty(t):
                saved += 1
        return saved

    async def get_treaty(self, treaty_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a single treaty by ID."""
        try:
            def _do():
                with self._get_connection() as conn:
                    row = conn.execute(
                        "SELECT * FROM treaties WHERE id=?", (treaty_id,)
                    ).fetchone()
                    if row:
                        cols = [d[0] for d in conn.execute(
                            "SELECT * FROM treaties WHERE id=?", (treaty_id,)
                        ).description or []]
                        return dict(zip(cols, row))
                    return None
            return await self._run_sync(_do)
        except Exception as e:
            logger.error(f"TreatiesDB.get_treaty({treaty_id}): {e}", exc_info=True)
            return None

    async def get_active_treaties(self) -> List[Dict[str, Any]]:
        """Return all active treaties."""
        try:
            def _do():
                with self._get_connection() as conn:
                    rows = conn.execute(
                        "SELECT * FROM treaties WHERE active=1 ORDER BY date DESC"
                    ).fetchall()
                    cols = [d[0] for d in conn.execute(
                        "SELECT * FROM treaties WHERE active=1"
                    ).description or []] if rows else []
                    return [dict(zip(cols, r)) for r in rows]
            return await self._run_sync(_do)
        except Exception as e:
            logger.error(f"TreatiesDB.get_active_treaties: {e}", exc_info=True)
            return []

    async def get_treaties_for_alliance(self, alliance_id: int) -> List[Dict[str, Any]]:
        """Return all active treaties for a specific alliance (as alliance1 or alliance2)."""
        try:
            def _do():
                with self._get_connection() as conn:
                    rows = conn.execute(
                        "SELECT * FROM treaties WHERE active=1 AND (alliance1_id=? OR alliance2_id=?) ORDER BY date DESC",
                        (alliance_id, alliance_id)
                    ).fetchall()
                    cols = [d[0] for d in conn.execute(
                        "SELECT * FROM treaties WHERE active=1 LIMIT 1"
                    ).description or []] if rows else []
                    return [dict(zip(cols, r)) for r in rows]
            return await self._run_sync(_do)
        except Exception as e:
            logger.error(f"TreatiesDB.get_treaties_for_alliance({alliance_id}): {e}", exc_info=True)
            return []

    def get_stats(self) -> Dict[str, int]:
        """Return basic counts synchronously."""
        try:
            with self._get_connection() as conn:
                total   = conn.execute("SELECT COUNT(*) FROM treaties").fetchone()[0]
                active  = conn.execute("SELECT COUNT(*) FROM treaties WHERE active=1").fetchone()[0]
                return {"total": total, "active": active, "inactive": total - active}
        except Exception as e:
            logger.error(f"TreatiesDB.get_stats: {e}", exc_info=True)
            return {"total": 0, "active": 0, "inactive": 0}

    async def get_distinct_alliances(self) -> List[Dict[str, Any]]:
        """Return distinct alliances that appear in active treaties."""
        try:
            def _do():
                with self._get_connection() as conn:
                    # First, get all unique alliance IDs and names from both sides of active treaties
                    alliances1 = conn.execute(
                        "SELECT DISTINCT alliance1_id, alliance1_name FROM treaties WHERE active = 1 AND alliance1_id IS NOT NULL AND alliance1_name IS NOT NULL"
                    ).fetchall()
                    alliances2 = conn.execute(
                        "SELECT DISTINCT alliance2_id, alliance2_name FROM treaties WHERE active = 1 AND alliance2_id IS NOT NULL AND alliance2_name IS NOT NULL"
                    ).fetchall()
                    
                    # Combine and create a unique set of (id, name) tuples
                    unique_alliances = set()
                    for aid, aname in alliances1:
                        if aid and aname:
                            unique_alliances.add((aid, aname))
                    for aid, aname in alliances2:
                        if aid and aname:
                            unique_alliances.add((aid, aname))
                    
                    # Now, for each unique alliance, count their total treaties
                    results = []
                    for aid, aname in unique_alliances:
                        treaty_count_row = conn.execute(
                            "SELECT COUNT(*) FROM treaties WHERE active = 1 AND (alliance1_id = ? OR alliance2_id = ?)",
                            (aid, aid)
                        ).fetchone()
                        treaty_count = treaty_count_row[0] if treaty_count_row else 0
                        
                        results.append({
                            'alliance_id': aid,
                            'alliance_name': aname,
                            'treaty_count': treaty_count
                        })
                    
                    # Sort by alliance name
                    results.sort(key=lambda x: (x['alliance_name'] or '').lower())
                    return results

            return await self._run_sync(_do)
        except Exception as e:
            logger.error(f"TreatiesDB.get_distinct_alliances: {e}", exc_info=True)
            return []

"""
MyNationsDB — SQLite storage for personal nation goals and snapshots.

Tables:
  nation_goals      — user-defined upgrade/build goals with estimated costs and
                      auto-completion tracking.
  nation_snapshots  — point-in-time snapshots of a nation + its cities, used as
                      a baseline for cost estimation.

Inherits from BaseDB with THREAD_POOL async mode and WAL enabled.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .base_db import AsyncMode, BaseDB

logger = logging.getLogger(__name__)


class MyNationsDB(BaseDB):
    """Personal nation goals and snapshot database."""

    def __init__(self, db_path: str) -> None:
        super().__init__(
            db_path=db_path,
            async_mode=AsyncMode.THREAD_POOL,
            wal_mode=True,
            synchronous="NORMAL",
            busy_timeout=5000,
            # Lightweight DB — no need for the full lock-manager overhead
            enable_locking=True,
            use_lock_manager=False,
        )
        self._init_schema()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        """Create tables and indexes if they don't exist yet."""
        try:
            with self._get_connection() as conn:
                c = conn.cursor()

                c.execute("""
                    CREATE TABLE IF NOT EXISTS nation_goals (
                        id              INTEGER PRIMARY KEY AUTOINCREMENT,
                        nation_id       INTEGER NOT NULL,
                        goal_type       TEXT NOT NULL,
                        goal_label      TEXT NOT NULL,
                        target_value    TEXT,
                        estimated_cost  TEXT,
                        notes           TEXT,
                        completed       INTEGER DEFAULT 0,
                        completed_at    TEXT,
                        created_at      TEXT NOT NULL,
                        updated_at      TEXT NOT NULL
                    )
                """)

                c.execute("""
                    CREATE TABLE IF NOT EXISTS nation_snapshots (
                        nation_id     INTEGER PRIMARY KEY,
                        snapshot_json TEXT NOT NULL,
                        cities_json   TEXT NOT NULL,
                        captured_at   TEXT NOT NULL
                    )
                """)

                c.execute("""
                    CREATE TABLE IF NOT EXISTS nation_plans (
                        id            INTEGER PRIMARY KEY AUTOINCREMENT,
                        nation_id     INTEGER NOT NULL UNIQUE,
                        plan_name     TEXT NOT NULL,
                        plan_data     TEXT NOT NULL,
                        status        TEXT DEFAULT 'active',
                        created_at    TEXT NOT NULL,
                        updated_at    TEXT NOT NULL
                    )
                """)

                c.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ng_nation_id
                        ON nation_goals(nation_id)
                """)
                c.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ng_completed
                        ON nation_goals(completed)
                """)
                c.execute("""
                    CREATE INDEX IF NOT EXISTS idx_plans_nation
                        ON nation_plans(nation_id)
                """)

                conn.commit()
                logger.info("MyNationsDB schema initialised successfully")
        except Exception as e:
            logger.error(f"MyNationsDB._init_schema error: {e}", exc_info=True)
            raise

    # ── Goals ─────────────────────────────────────────────────────────────────

    async def get_goals(self, nation_id: int) -> List[Dict[str, Any]]:
        """Return all goals for a nation ordered by completed ASC, created_at DESC."""
        return await self._run_sync(lambda: self._get_goals_sync(nation_id))

    def _get_goals_sync(self, nation_id: int) -> List[Dict[str, Any]]:
        try:
            with self._get_connection() as conn:
                c = conn.cursor()
                c.execute(
                    """
                    SELECT * FROM nation_goals
                    WHERE nation_id = ?
                    ORDER BY completed ASC, created_at DESC
                    """,
                    (nation_id,),
                )
                rows = c.fetchall()
                return [self._row_to_goal(row) for row in rows]
        except Exception as e:
            logger.error(f"MyNationsDB.get_goals({nation_id}): {e}", exc_info=True)
            return []

    async def save_goal(self, goal: Dict[str, Any]) -> int:
        """INSERT a new goal and return its new id (or -1 on failure)."""
        return await self._run_sync(lambda: self._save_goal_sync(goal))

    def _save_goal_sync(self, goal: Dict[str, Any]) -> int:
        try:
            now = _utcnow()
            with self._get_connection() as conn:
                c = conn.cursor()
                c.execute(
                    """
                    INSERT INTO nation_goals
                        (nation_id, goal_type, goal_label, target_value,
                         estimated_cost, notes, completed, completed_at,
                         created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 0, NULL, ?, ?)
                    """,
                    (
                        goal["nation_id"],
                        goal["goal_type"],
                        goal["goal_label"],
                        _encode(goal.get("target_value")),
                        _encode(goal.get("estimated_cost")),
                        goal.get("notes"),
                        now,
                        now,
                    ),
                )
                conn.commit()
                return c.lastrowid  # type: ignore[return-value]
        except Exception as e:
            logger.error(f"MyNationsDB.save_goal error: {e}", exc_info=True)
            return -1

    async def update_goal(self, goal_id: int, updates: Dict[str, Any]) -> bool:
        """Apply a dict of column→value updates to a goal. Returns True on success."""
        return await self._run_sync(lambda: self._update_goal_sync(goal_id, updates))

    def _update_goal_sync(self, goal_id: int, updates: Dict[str, Any]) -> bool:
        if not updates:
            return False
        # Serialise any dict/list values and stamp updated_at
        safe: Dict[str, Any] = {}
        for k, v in updates.items():
            safe[k] = _encode(v) if isinstance(v, (dict, list)) else v
        safe["updated_at"] = _utcnow()

        # Only allow updating known columns to prevent SQL injection
        _ALLOWED = frozenset({
            "goal_type", "goal_label", "target_value", "estimated_cost",
            "notes", "completed", "completed_at", "updated_at",
        })
        safe = {k: v for k, v in safe.items() if k in _ALLOWED}
        if not safe:
            return False

        try:
            with self._get_connection() as conn:
                set_clause = ", ".join(f"{k} = ?" for k in safe)
                conn.execute(
                    f"UPDATE nation_goals SET {set_clause} WHERE id = ?",
                    list(safe.values()) + [goal_id],
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"MyNationsDB.update_goal({goal_id}): {e}", exc_info=True)
            return False

    async def delete_goal(self, goal_id: int) -> bool:
        """Delete a goal by id. Returns True if a row was deleted."""
        return await self._run_sync(lambda: self._delete_goal_sync(goal_id))

    def _delete_goal_sync(self, goal_id: int) -> bool:
        try:
            with self._get_connection() as conn:
                cur = conn.execute(
                    "DELETE FROM nation_goals WHERE id = ?", (goal_id,)
                )
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"MyNationsDB.delete_goal({goal_id}): {e}", exc_info=True)
            return False

    async def complete_goal(self, goal_id: int) -> bool:
        """Mark a goal as completed (completed=1, completed_at=utcnow). Returns True on success."""
        return await self._run_sync(lambda: self._complete_goal_sync(goal_id))

    def _complete_goal_sync(self, goal_id: int) -> bool:
        try:
            now = _utcnow()
            with self._get_connection() as conn:
                cur = conn.execute(
                    """
                    UPDATE nation_goals
                    SET completed = 1, completed_at = ?, updated_at = ?
                    WHERE id = ? AND completed = 0
                    """,
                    (now, now, goal_id),
                )
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"MyNationsDB.complete_goal({goal_id}): {e}", exc_info=True)
            return False

    # ── Plans ─────────────────────────────────────────────────────────────────

    async def get_plan(self, nation_id: int) -> Optional[Dict[str, Any]]:
        """Return the active plan for a nation, or None if none exists."""
        return await self._run_sync(lambda: self._get_plan_sync(nation_id))

    def _get_plan_sync(self, nation_id: int) -> Optional[Dict[str, Any]]:
        try:
            with self._get_connection() as conn:
                c = conn.cursor()
                c.execute(
                    """
                    SELECT * FROM nation_plans 
                    WHERE nation_id = ? AND status = 'active'
                    """,
                    (nation_id,),
                )
                row = c.fetchone()
                if row is None:
                    return None
                return {
                    "id": row["id"],
                    "nation_id": row["nation_id"],
                    "plan_name": row["plan_name"],
                    "plan_data": _decode(row["plan_data"]),
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
        except Exception as e:
            logger.error(f"MyNationsDB.get_plan({nation_id}): {e}", exc_info=True)
            return None

    async def save_plan(
        self, nation_id: int, plan_name: str, plan_data: Dict[str, Any]
    ) -> int:
        """Insert or update a plan. Returns plan id (or -1 on failure)."""
        return await self._run_sync(
            lambda: self._save_plan_sync(nation_id, plan_name, plan_data)
        )

    def _save_plan_sync(
        self, nation_id: int, plan_name: str, plan_data: Dict[str, Any]
    ) -> int:
        try:
            now = _utcnow()
            plan_json = json.dumps(plan_data)
            with self._get_connection() as conn:
                c = conn.cursor()
                c.execute(
                    """
                    INSERT INTO nation_plans 
                        (nation_id, plan_name, plan_data, status, created_at, updated_at)
                    VALUES (?, ?, ?, 'active', ?, ?)
                    ON CONFLICT(nation_id) DO UPDATE SET
                        plan_name = excluded.plan_name,
                        plan_data = excluded.plan_data,
                        updated_at = excluded.updated_at
                    """,
                    (nation_id, plan_name, plan_json, now, now),
                )
                # Get the plan id
                if c.lastrowid:
                    plan_id = c.lastrowid
                else:
                    # Was an update, fetch existing id
                    c.execute(
                        "SELECT id FROM nation_plans WHERE nation_id = ?",
                        (nation_id,),
                    )
                    row = c.fetchone()
                    plan_id = row[0] if row else -1
                conn.commit()
                return plan_id
        except Exception as e:
            logger.error(f"MyNationsDB.save_plan({nation_id}): {e}", exc_info=True)
            return -1

    async def delete_plan(self, nation_id: int) -> bool:
        """Delete a nation's plan. Returns True if a row was deleted."""
        return await self._run_sync(lambda: self._delete_plan_sync(nation_id))

    def _delete_plan_sync(self, nation_id: int) -> bool:
        try:
            with self._get_connection() as conn:
                cur = conn.execute(
                    "DELETE FROM nation_plans WHERE nation_id = ?", (nation_id,)
                )
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"MyNationsDB.delete_plan({nation_id}): {e}", exc_info=True)
            return False

    # ── Snapshots ─────────────────────────────────────────────────────────────

    async def get_snapshot(self, nation_id: int) -> Optional[Dict[str, Any]]:
        """Return the stored snapshot for a nation, or None if none exists."""
        return await self._run_sync(lambda: self._get_snapshot_sync(nation_id))

    def _get_snapshot_sync(self, nation_id: int) -> Optional[Dict[str, Any]]:
        try:
            with self._get_connection() as conn:
                c = conn.cursor()
                c.execute(
                    "SELECT * FROM nation_snapshots WHERE nation_id = ?",
                    (nation_id,),
                )
                row = c.fetchone()
                if row is None:
                    return None
                return {
                    "nation_id":   row["nation_id"],
                    "nation":      _decode(row["snapshot_json"]),
                    "cities":      _decode(row["cities_json"]),
                    "captured_at": row["captured_at"],
                }
        except Exception as e:
            logger.error(f"MyNationsDB.get_snapshot({nation_id}): {e}", exc_info=True)
            return None

    async def save_snapshot(
        self,
        nation_id: int,
        nation: Dict[str, Any],
        cities: List[Dict[str, Any]],
    ) -> bool:
        """UPSERT a nation snapshot. Returns True on success."""
        return await self._run_sync(
            lambda: self._save_snapshot_sync(nation_id, nation, cities)
        )

    def _save_snapshot_sync(
        self,
        nation_id: int,
        nation: Dict[str, Any],
        cities: List[Dict[str, Any]],
    ) -> bool:
        try:
            now = _utcnow()
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO nation_snapshots
                        (nation_id, snapshot_json, cities_json, captured_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(nation_id) DO UPDATE SET
                        snapshot_json = excluded.snapshot_json,
                        cities_json   = excluded.cities_json,
                        captured_at   = excluded.captured_at
                    """,
                    (nation_id, json.dumps(nation), json.dumps(cities), now),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(
                f"MyNationsDB.save_snapshot({nation_id}): {e}", exc_info=True
            )
            return False

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_goal(row: sqlite3.Row) -> Dict[str, Any]:
        """Convert a nation_goals sqlite3.Row to a plain dict."""
        d = dict(row)
        # Deserialise JSON TEXT columns
        for col in ("target_value", "estimated_cost"):
            raw = d.get(col)
            if isinstance(raw, str):
                try:
                    d[col] = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    pass  # leave as-is if not valid JSON
        return d


# ── Private utilities ─────────────────────────────────────────────────────────

def _utcnow() -> str:
    """Return the current UTC time as an ISO-8601 string (no microseconds)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _encode(value: Any) -> Optional[str]:
    """Serialise a value to a JSON string if it is a dict or list, else return as-is."""
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value  # type: ignore[return-value]


def _decode(raw: Optional[str]) -> Any:
    """Deserialise a JSON string, returning None on failure."""
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw

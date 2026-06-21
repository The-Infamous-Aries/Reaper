"""
Persistent cooldown storage.

Table: activity_cooldowns
  user_id   TEXT  — Discord user ID
  command   TEXT  — action name (train, mission, play, quest, …)
  expires_at REAL — Unix timestamp (UTC) when the cooldown expires

Primary key is (user_id, command).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, Optional

import aiosqlite
from Systems.Functions.database_manager import DB_FILE

logger = logging.getLogger(__name__)

_lock = asyncio.Lock()
_ready = False


async def _ensure_table() -> None:
    global _ready
    if _ready:
        return
    async with _lock:
        if _ready:
            return
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS activity_cooldowns (
                    user_id    TEXT NOT NULL,
                    command    TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    PRIMARY KEY (user_id, command)
                )
            """)
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_cd_user ON activity_cooldowns(user_id)"
            )
            await db.commit()
        _ready = True


async def check(command: str, user_id: str) -> tuple[bool, int]:
    """
    Return (on_cooldown, seconds_remaining).
    Automatically removes expired rows.
    """
    await _ensure_table()
    now = time.time()
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT expires_at FROM activity_cooldowns WHERE user_id=? AND command=?",
            (user_id, command),
        ) as cur:
            row = await cur.fetchone()

    if row is None:
        return False, 0

    expires_at: float = row[0]
    remaining = expires_at - now
    if remaining <= 0:
        # Expired — clean up lazily
        asyncio.create_task(_delete(user_id, command))
        return False, 0

    return True, int(remaining)


async def set_cooldown(command: str, user_id: str, duration_secs: int = 5) -> None:
    """Record a fresh cooldown that expires in duration_secs seconds."""
    await _ensure_table()
    expires_at = time.time() + duration_secs
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            INSERT INTO activity_cooldowns (user_id, command, expires_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, command) DO UPDATE SET expires_at=excluded.expires_at
            """,
            (user_id, command, expires_at),
        )
        await db.commit()


async def get_all(user_id: str) -> Dict[str, int]:
    """
    Return {command: seconds_remaining} for all active cooldowns for a user.
    Expired entries are excluded (and lazily deleted).
    """
    await _ensure_table()
    now = time.time()
    result: Dict[str, int] = {}
    expired: list[str] = []

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT command, expires_at FROM activity_cooldowns WHERE user_id=?",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()

    for command, expires_at in rows:
        remaining = expires_at - now
        if remaining > 0:
            result[command] = int(remaining)
        else:
            expired.append(command)

    if expired:
        asyncio.create_task(_delete_many(user_id, expired))

    return result


async def _delete(user_id: str, command: str) -> None:
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "DELETE FROM activity_cooldowns WHERE user_id=? AND command=?",
                (user_id, command),
            )
            await db.commit()
    except Exception as e:
        logger.debug(f"cooldown_db _delete error: {e}")


async def _delete_many(user_id: str, commands: list[str]) -> None:
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.executemany(
                "DELETE FROM activity_cooldowns WHERE user_id=? AND command=?",
                [(user_id, c) for c in commands],
            )
            await db.commit()
    except Exception as e:
        logger.debug(f"cooldown_db _delete_many error: {e}")

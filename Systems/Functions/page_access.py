"""
Page Access Control — per-page access for restricted dashboard pages.

Schema: page_access(user_id, page, granted_by, granted_at)
  - One row per (user, page) pair.
  - page = 'nations' | 'watch' | 'leaderboard' | 'raids' | '*' (all pages)
  - Aries always has full access regardless of the table.

Migration: old single-row schema (user_id PRIMARY KEY) is detected and
upgraded — existing rows are expanded to one row per page.
"""

import logging
import aiosqlite
from Systems.Functions.db_paths import ACCESS_DB_STR as _DB_PATH

logger = logging.getLogger("Reaper.PageAccess")

ALL_PAGES = frozenset(["nations", "watch", "leaderboard", "raids"])


async def _ensure_table() -> None:
    async with aiosqlite.connect(_DB_PATH) as db:
        # Check if old single-row schema exists (user_id is PRIMARY KEY with no 'page' col)
        cur = await db.execute("PRAGMA table_info(page_access)")
        cols = {row[1] for row in await cur.fetchall()}

        if not cols:
            # Fresh install — create new schema
            await db.execute("""
                CREATE TABLE page_access (
                    user_id    TEXT NOT NULL,
                    page       TEXT NOT NULL,
                    granted_by TEXT NOT NULL,
                    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, page)
                )
            """)
            await db.commit()
            return

        if "page" not in cols:
            # Old schema detected — migrate
            logger.info("Migrating page_access to per-page schema…")
            cur = await db.execute("SELECT user_id, granted_by FROM page_access")
            old_rows = await cur.fetchall()
            await db.execute("DROP TABLE page_access")
            await db.execute("""
                CREATE TABLE page_access (
                    user_id    TEXT NOT NULL,
                    page       TEXT NOT NULL,
                    granted_by TEXT NOT NULL,
                    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, page)
                )
            """)
            for uid, gby in old_rows:
                for page in ALL_PAGES:
                    await db.execute(
                        "INSERT OR IGNORE INTO page_access (user_id, page, granted_by) VALUES (?,?,?)",
                        (uid, page, gby),
                    )
            await db.commit()
            logger.info("Migration complete — %d users expanded to per-page rows.", len(old_rows))


async def has_access(user_id: str | int, page: str | None = None) -> bool:
    """
    Return True if the user can view the given page (or any restricted page if page=None).
    """
    uid = str(user_id)
    try:
        await _ensure_table()
        async with aiosqlite.connect(_DB_PATH) as db:
            if page:
                cur = await db.execute(
                    "SELECT 1 FROM page_access WHERE user_id=? AND page=?", (uid, page)
                )
            else:
                cur = await db.execute(
                    "SELECT 1 FROM page_access WHERE user_id=? LIMIT 1", (uid,)
                )
            return (await cur.fetchone()) is not None
    except Exception as e:
        logger.error("has_access error for %s: %s", uid, e)
        return False


async def get_allowed_pages(user_id: str | int) -> set[str]:
    """Return the set of page names this user is allowed to view."""
    uid = str(user_id)
    try:
        await _ensure_table()
        async with aiosqlite.connect(_DB_PATH) as db:
            cur = await db.execute(
                "SELECT page FROM page_access WHERE user_id=?", (uid,)
            )
            rows = await cur.fetchall()
            return {r[0] for r in rows}
    except Exception as e:
        logger.error("get_allowed_pages error for %s: %s", uid, e)
        return set()


async def grant_access(user_id: str | int, granted_by: str | int, pages: set[str] | None = None) -> bool:
    """
    Grant access to the given pages (defaults to ALL_PAGES).
    Returns True on success.
    """
    uid  = str(user_id)
    gby  = str(granted_by)
    target_pages = pages if pages is not None else set(ALL_PAGES)
    try:
        await _ensure_table()
        async with aiosqlite.connect(_DB_PATH) as db:
            for page in target_pages:
                await db.execute(
                    """INSERT INTO page_access (user_id, page, granted_by)
                       VALUES (?, ?, ?)
                       ON CONFLICT(user_id, page) DO UPDATE SET
                           granted_by = excluded.granted_by,
                           granted_at = CURRENT_TIMESTAMP""",
                    (uid, page, gby),
                )
            await db.commit()
        logger.info("Access granted to %s for pages %s by %s", uid, target_pages, gby)
        return True
    except Exception as e:
        logger.error("grant_access error for %s: %s", uid, e)
        return False


async def revoke_access(user_id: str | int, pages: set[str] | None = None) -> bool:
    """
    Revoke access for the given pages (defaults to ALL_PAGES).
    Returns True on success.
    """
    uid = str(user_id)
    target_pages = pages if pages is not None else set(ALL_PAGES)
    try:
        await _ensure_table()
        async with aiosqlite.connect(_DB_PATH) as db:
            for page in target_pages:
                await db.execute(
                    "DELETE FROM page_access WHERE user_id=? AND page=?", (uid, page)
                )
            await db.commit()
        logger.info("Access revoked for %s on pages %s", uid, target_pages)
        return True
    except Exception as e:
        logger.error("revoke_access error for %s: %s", uid, e)
        return False


async def list_access() -> list[dict]:
    """Return all access rows grouped by user."""
    try:
        await _ensure_table()
        async with aiosqlite.connect(_DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT user_id, page, granted_by, granted_at FROM page_access ORDER BY granted_at DESC"
            )
            return [dict(r) for r in await cur.fetchall()]
    except Exception as e:
        logger.error("list_access error: %s", e)
        return []

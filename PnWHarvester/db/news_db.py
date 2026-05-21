"""
NewsDB — Three-tier SQLite news tracking for PnW progress events.

Three separate databases, each with identical schema:
  WeeklyNews.db   — current week only; auto-reset at Monday 00:00 UTC
  MonthlyNews.db  — current month only; auto-reset at 1st of month 00:00 UTC
  YearlyNews{YYYY}.db — full year; new file each calendar year (never reset)

Every event written to NewsDB is written to ALL THREE simultaneously.
All writes are automatically enriched from GlobalNations.db for any
missing nation_name, nation_flag, alliance_id, or alliance_name.

Now inherits from BaseDB for unified async patterns and connection management.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from .base_db import BaseDB, AsyncMode

logger = logging.getLogger(__name__)

# ── DB paths ──────────────────────────────────────────────────────────────────
_DB_ROOT          = Path(__file__).resolve().parent.parent.parent / "Databases" / "PnW"
_GLOBAL_NATIONS_DB = _DB_ROOT / "GlobalNations.db"

def _weekly_db_path(offset: int = 0) -> Path:
    if offset == 0:
        return _DB_ROOT / "WeeklyNews.db"
    return _DB_ROOT / "WeeklyNews_prev.db"

def _monthly_db_path(offset: int = 0) -> Path:
    if offset == 0:
        return _DB_ROOT / "MonthlyNews.db"
    return _DB_ROOT / "MonthlyNews_prev.db"

def _yearly_db_path(year: Optional[int] = None) -> Path:
    y = year or datetime.now(timezone.utc).year
    return _DB_ROOT / f"YearlyNews{y}.db"

# ── Period boundary helpers ───────────────────────────────────────────────────

def _week_start_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

def _month_start_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

def _year_start_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

# ── Schema ────────────────────────────────────────────────────────────────────

_CREATE_EVENTS = """
CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,
    nation_id       INTEGER,
    nation_name     TEXT,
    nation_flag     TEXT,
    alliance_id     INTEGER,
    alliance_name   TEXT,
    alliance_flag   TEXT,
    sec_nation_id   INTEGER,
    sec_nation_name TEXT,
    sec_alliance_id INTEGER,
    sec_alliance_name TEXT,
    value           REAL DEFAULT 0,
    value2          REAL DEFAULT 0,
    headline        TEXT,
    detail          TEXT,
    event_date      TEXT NOT NULL,
    recorded_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_type     ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_alliance ON events(alliance_id);
CREATE INDEX IF NOT EXISTS idx_events_nation   ON events(nation_id);
CREATE INDEX IF NOT EXISTS idx_events_date     ON events(event_date);
"""

_CREATE_ALLIANCE_STATS = """
CREATE TABLE IF NOT EXISTS alliance_stats (
    alliance_id        INTEGER PRIMARY KEY,
    alliance_name      TEXT,
    alliance_flag      TEXT,
    cities_built       INTEGER DEFAULT 0,
    projects_bought    INTEGER DEFAULT 0,
    infra_spent        REAL DEFAULT 0,
    land_spent         REAL DEFAULT 0,
    improvements_spent REAL DEFAULT 0,
    military_spent     REAL DEFAULT 0,
    wars_declared      INTEGER DEFAULT 0,
    wars_won           INTEGER DEFAULT 0,
    wars_lost          INTEGER DEFAULT 0,
    wars_drawn         INTEGER DEFAULT 0,
    loot_gained        REAL DEFAULT 0,
    loot_lost          REAL DEFAULT 0,
    infra_destroyed    REAL DEFAULT 0,
    nukes_used         INTEGER DEFAULT 0,
    missiles_used      INTEGER DEFAULT 0,
    bank_deposits      REAL DEFAULT 0,
    bank_withdrawals   REAL DEFAULT 0,
    total_spent        REAL DEFAULT 0,
    updated_at         TEXT
);
"""

_CREATE_NATION_STATS = """
CREATE TABLE IF NOT EXISTS nation_stats (
    nation_id          INTEGER PRIMARY KEY,
    nation_name        TEXT,
    nation_flag        TEXT,
    alliance_id        INTEGER,
    alliance_name      TEXT,
    cities_built       INTEGER DEFAULT 0,
    projects_bought    INTEGER DEFAULT 0,
    infra_spent        REAL DEFAULT 0,
    land_spent         REAL DEFAULT 0,
    improvements_spent REAL DEFAULT 0,
    military_spent     REAL DEFAULT 0,
    wars_declared      INTEGER DEFAULT 0,
    wars_won           INTEGER DEFAULT 0,
    wars_lost          INTEGER DEFAULT 0,
    loot_gained        REAL DEFAULT 0,
    loot_lost          REAL DEFAULT 0,
    bank_deposits      REAL DEFAULT 0,
    bank_withdrawals   REAL DEFAULT 0,
    total_spent        REAL DEFAULT 0,
    updated_at         TEXT
);
CREATE INDEX IF NOT EXISTS idx_nstats_alliance ON nation_stats(alliance_id);
"""

_CREATE_META = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

# Valid stat columns — used to whitelist delta keys before building SQL
_ALLIANCE_STAT_COLS = frozenset((
    "cities_built", "projects_bought", "infra_spent", "land_spent",
    "improvements_spent", "military_spent", "wars_declared", "wars_won",
    "wars_lost", "wars_drawn", "loot_gained", "loot_lost",
    "infra_destroyed", "nukes_used", "missiles_used",
    "bank_deposits", "bank_withdrawals", "total_spent",
))
_NATION_STAT_COLS = frozenset((
    "cities_built", "projects_bought", "infra_spent", "land_spent",
    "improvements_spent", "military_spent", "wars_declared", "wars_won",
    "wars_lost", "loot_gained", "loot_lost",
    "bank_deposits", "bank_withdrawals", "total_spent",
))


def _open_conn(path: Path) -> sqlite3.Connection:
    """Open a connection with WAL mode and safe pragmas."""
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA wal_autocheckpoint=1000")
    return conn


# ── GlobalNations enrichment cache ───────────────────────────────────────────

class _NationCache:
    """
    Lightweight read-only cache over GlobalNations.db.

    Loaded once at first use and refreshed every REFRESH_SECS seconds.
    Used by NewsDB.record_event to fill in any missing nation_name,
    nation_flag, alliance_id, or alliance_name before writing to the
    news DBs — so every event has complete, human-readable data.

    Thread/async safety: reads are synchronous and happen inside the
    NewsDB asyncio lock, so no additional locking is needed here.
    """

    REFRESH_SECS = 300  # re-read GlobalNations.db every 5 minutes

    def __init__(self):
        # nation_id → {name, flag, alliance_id, alliance_name, alliance_flag}
        self._nations:        Dict[int, Dict[str, Any]] = {}
        # alliance_id → alliance_name
        self._alliances:      Dict[int, str] = {}
        # alliance_id → alliance_flag URL
        self._alliance_flags: Dict[int, str] = {}
        self._loaded_at: float = 0.0

    def _needs_refresh(self) -> bool:
        return time.monotonic() - self._loaded_at > self.REFRESH_SECS

    def _load(self) -> None:
        """Read nation + alliance data from GlobalNations.db into memory."""
        if not _GLOBAL_NATIONS_DB.exists():
            return
        try:
            with sqlite3.connect(str(_GLOBAL_NATIONS_DB)) as conn:
                conn.execute("PRAGMA query_only=1")
                # alliance_flag column may not exist on older DBs — use a
                # safe fallback query that handles missing columns gracefully.
                try:
                    rows = conn.execute(
                        "SELECT id, nation_name, flag, alliance_id, alliance_name, alliance_flag "
                        "FROM nations "
                        "WHERE nation_name IS NOT NULL AND nation_name != ''"
                    ).fetchall()
                    has_aflag = True
                except sqlite3.OperationalError:
                    rows = conn.execute(
                        "SELECT id, nation_name, flag, alliance_id, alliance_name "
                        "FROM nations "
                        "WHERE nation_name IS NOT NULL AND nation_name != ''"
                    ).fetchall()
                    has_aflag = False
            nations: Dict[int, Dict[str, Any]] = {}
            alliances: Dict[int, str] = {}
            alliance_flags: Dict[int, str] = {}
            for row in rows:
                nid   = int(row[0])
                nname = row[1]
                flag  = row[2]
                aid   = row[3]
                aname = row[4]
                aflag = row[5] if has_aflag else None
                nations[nid] = {
                    "name":           nname,
                    "flag":           flag,
                    "alliance_id":    int(aid) if aid else None,
                    "alliance_name":  aname if (aname and aname != '0') else None,
                    "alliance_flag":  aflag if aflag else None,
                }
                # Only store alliance name if it's a real name (not '0', '', or None)
                if aid and aname and aname != '0':
                    alliances[int(aid)] = aname
                if aid and aflag:
                    alliance_flags[int(aid)] = aflag
            self._nations        = nations
            self._alliances      = alliances
            self._alliance_flags = alliance_flags
            self._loaded_at = time.monotonic()
            logger.debug(
                f"NationCache: loaded {len(nations):,} nations, "
                f"{len(alliances):,} alliances from GlobalNations.db"
            )
        except Exception as e:
            logger.warning(f"NationCache._load: {e}")

    def _ensure_loaded(self) -> None:
        if self._needs_refresh():
            self._load()

    def enrich(
        self,
        nation_id:    Optional[int],
        nation_name:  Optional[str],
        nation_flag:  Optional[str],
        alliance_id:  Optional[int],
        alliance_name: Optional[str],
        alliance_flag: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Return a dict with the best available values for all six fields.

        Alliance name/flag are ALWAYS taken from GlobalNations.db when we have
        a known alliance_id — the subscription payload can carry stale names
        from recycled alliance IDs (e.g. an old alliance's name still attached
        to an ID that now belongs to a different alliance).  GlobalNations is
        the authoritative source for the current name of any alliance_id.

        Nation name/flag still prefer the caller-supplied value (those don't
        get recycled the same way).
        """
        self._ensure_loaded()

        out_nation_name   = nation_name
        out_nation_flag   = nation_flag
        out_alliance_id   = alliance_id
        # Treat '0' as no alliance name (PnW uses '0' for unaffiliated nations)
        out_alliance_name = alliance_name if (alliance_name and alliance_name != '0') else None
        out_alliance_flag = alliance_flag

        # Look up nation record if we have a nation_id
        if nation_id:
            ni = self._nations.get(int(nation_id))
            if ni:
                if not out_nation_name:
                    out_nation_name = ni["name"]
                if not out_nation_flag:
                    out_nation_flag = ni["flag"]
                # Fill alliance_id from nation record if still missing
                if not out_alliance_id and ni["alliance_id"]:
                    out_alliance_id = ni["alliance_id"]
                # Always prefer GlobalNations alliance name/flag for the nation's
                # current alliance — overrides any stale name from the subscription
                if ni["alliance_id"] and ni["alliance_name"]:
                    out_alliance_name = ni["alliance_name"]
                if ni["alliance_id"] and ni.get("alliance_flag"):
                    out_alliance_flag = ni["alliance_flag"]

        # If we have an alliance_id, always resolve name/flag from the canonical
        # GlobalNations cache — this is the single source of truth for current names
        if out_alliance_id and int(out_alliance_id) != 0:
            canonical_name = self._alliances.get(int(out_alliance_id))
            canonical_flag = self._alliance_flags.get(int(out_alliance_id))
            if canonical_name:
                out_alliance_name = canonical_name   # always override stale names
            if canonical_flag:
                out_alliance_flag = canonical_flag

        # Treat alliance_id=0 as no alliance
        if out_alliance_id == 0:
            out_alliance_id   = None
            out_alliance_name = None
            out_alliance_flag = None

        return {
            "nation_name":   out_nation_name,
            "nation_flag":   out_nation_flag,
            "alliance_id":   out_alliance_id,
            "alliance_name": out_alliance_name,
            "alliance_flag": out_alliance_flag,
        }

    def get_alliance_name(self, alliance_id: Optional[int]) -> Optional[str]:
        """Quick alliance name lookup without a full nation record."""
        if not alliance_id:
            return None
        self._ensure_loaded()
        return self._alliances.get(int(alliance_id))


# Module-level cache instance — shared across all NewsDB writes
_nation_cache = _NationCache()


def _init_db(path: Path, period_start: str) -> None:
    """Create tables, indexes, and set period_start meta if not already set."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with _open_conn(path) as conn:
        for stmt in _CREATE_EVENTS.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(s)
        for stmt in _CREATE_ALLIANCE_STATS.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(s)
        for stmt in _CREATE_NATION_STATS.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(s)
        for stmt in _CREATE_META.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(s)
        conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES ('period_start', ?)",
            (period_start,),
        )
        # ── Migrate existing DBs: add new columns if they don't exist yet ────
        _migrate_add_columns(conn)
        conn.commit()


def _migrate_add_columns(conn: sqlite3.Connection) -> None:
    """Add any new columns to existing tables without dropping data."""
    _safe_add_column(conn, "alliance_stats", "bank_deposits",    "REAL DEFAULT 0")
    _safe_add_column(conn, "alliance_stats", "bank_withdrawals", "REAL DEFAULT 0")
    _safe_add_column(conn, "nation_stats",   "bank_deposits",    "REAL DEFAULT 0")
    _safe_add_column(conn, "nation_stats",   "bank_withdrawals", "REAL DEFAULT 0")
    # Secondary-party columns for two-sided events (loot, war, etc.)
    _safe_add_column(conn, "events", "sec_nation_id",    "INTEGER")
    _safe_add_column(conn, "events", "sec_nation_name",  "TEXT")
    _safe_add_column(conn, "events", "sec_alliance_id",  "INTEGER")
    _safe_add_column(conn, "events", "sec_alliance_name","TEXT")
    # Add indexes for new columns (silently ignored if already present)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_sec_alliance ON events(sec_alliance_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_sec_nation   ON events(sec_nation_id)")
    except Exception:
        pass


def _safe_add_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    """Add a column to a table if it doesn't already exist. Silently skips if present."""
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    except sqlite3.OperationalError:
        pass  # Column already exists


# ── NewsDB class ──────────────────────────────────────────────────────────────

class NewsDB:
    """
    Manages all three news databases (weekly, monthly, yearly).
    All writes go to all three simultaneously.
    Handles period resets automatically.
    Uses LockManager for unified locking across all DB files.
    """

    def __init__(self):
        # Use LockManager for unified locking
        from PnWHarvester.core.lock_manager import get_lock_manager
        self._lock_manager = get_lock_manager()
        
        # Cache the expected period starts so _check_and_reset_if_needed
        # doesn't hit the DB on every single write — only recalculates
        # when the cached value is more than 60 seconds old.
        self._last_period_check: float = 0.0
        self._cached_week_start: str = ""
        self._cached_month_start: str = ""
        self._ensure_dbs()

    def _ensure_dbs(self) -> None:
        """Create/verify all three DBs for the current period."""
        now = datetime.now(timezone.utc)
        _init_db(_weekly_db_path(0),  _week_start_utc().isoformat())
        _init_db(_monthly_db_path(0), _month_start_utc().isoformat())
        _init_db(_yearly_db_path(now.year), _year_start_utc().isoformat())
        self._do_period_check()
        # Correct any stale alliance names on startup
        self._refresh_alliance_names()

    def _refresh_alliance_names(self) -> None:
        """
        Correct stale alliance names in all active news DBs by comparing
        against the GlobalNations canonical map.

        Alliance IDs get recycled in PnW — an ID that belonged to "Weebunism"
        may now belong to "Nights Watch".  This pass ensures every row in
        alliance_stats, nation_stats, and events reflects the current name.
        """
        _nation_cache._ensure_loaded()
        canonical = _nation_cache._alliances        # alliance_id -> name
        canon_flags = _nation_cache._alliance_flags  # alliance_id -> flag

        if not canonical:
            return  # GlobalNations not available yet — skip silently

        now = datetime.now(timezone.utc)
        paths = [
            _weekly_db_path(0),
            _monthly_db_path(0),
            _yearly_db_path(now.year),
        ]

        for path in paths:
            if not path.exists():
                continue
            try:
                with _open_conn(path) as conn:
                    col_names = {r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()}
                    has_sec = "sec_alliance_id" in col_names
                    for aid, canon_name in canonical.items():
                        canon_flag = canon_flags.get(aid)
                        # alliance_stats
                        if canon_flag:
                            conn.execute(
                                "UPDATE alliance_stats SET alliance_name=?, alliance_flag=? "
                                "WHERE alliance_id=? AND (alliance_name != ? OR alliance_flag != ?)",
                                (canon_name, canon_flag, aid, canon_name, canon_flag),
                            )
                        else:
                            conn.execute(
                                "UPDATE alliance_stats SET alliance_name=? "
                                "WHERE alliance_id=? AND alliance_name != ?",
                                (canon_name, aid, canon_name),
                            )
                        # nation_stats
                        conn.execute(
                            "UPDATE nation_stats SET alliance_name=? "
                            "WHERE alliance_id=? AND alliance_name != ? "
                            "AND alliance_name IS NOT NULL AND alliance_name != ''",
                            (canon_name, aid, canon_name),
                        )
                        # events — primary party
                        conn.execute(
                            "UPDATE events SET alliance_name=? "
                            "WHERE alliance_id=? AND alliance_name != ? "
                            "AND alliance_name IS NOT NULL AND alliance_name != '' AND alliance_name != '0'",
                            (canon_name, aid, canon_name),
                        )
                        # events — secondary party
                        if has_sec:
                            conn.execute(
                                "UPDATE events SET sec_alliance_name=? "
                                "WHERE sec_alliance_id=? AND sec_alliance_name != ? "
                                "AND sec_alliance_name IS NOT NULL AND sec_alliance_name != '' AND sec_alliance_name != '0'",
                                (canon_name, aid, canon_name),
                            )
                    conn.commit()
            except Exception as e:
                logger.warning(f"NewsDB._refresh_alliance_names({path.name}): {e}")

    def _do_period_check(self) -> None:
        """
        Check if weekly/monthly DBs are stale (period has rolled over).
        If so:
          1. Copy the current DB to *_prev.db (preserving last week/month data).
          2. Wipe events + stats tables and update period_start.
        Yearly DB is never reset — a new file is created each year.

        This is called at startup and then at most once per minute during writes.
        """
        now = datetime.now(timezone.utc)
        expected_week  = _week_start_utc().isoformat()
        expected_month = _month_start_utc().isoformat()

        # Update cache
        self._cached_week_start  = expected_week
        self._cached_month_start = expected_month
        self._last_period_check  = time.monotonic()

        for path, prev_path, expected_start in [
            (_weekly_db_path(0),  _weekly_db_path(-1),  expected_week),
            (_monthly_db_path(0), _monthly_db_path(-1), expected_month),
        ]:
            if not path.exists():
                _init_db(path, expected_start)
                continue
            try:
                with _open_conn(path) as conn:
                    row = conn.execute(
                        "SELECT value FROM meta WHERE key = 'period_start'"
                    ).fetchone()
                    stored = row[0] if row else None
                    if stored != expected_start:
                        logger.info(
                            f"NewsDB: rolling over {path.name} "
                            f"(stored={stored}, expected={expected_start})"
                        )
                        try:
                            import shutil
                            shutil.copy2(str(path), str(prev_path))
                            logger.info(f"NewsDB: archived {path.name} → {prev_path.name}")
                        except Exception as copy_err:
                            logger.warning(f"NewsDB: archive copy failed: {copy_err}")

                        conn.execute("DELETE FROM events")
                        conn.execute("DELETE FROM alliance_stats")
                        conn.execute("DELETE FROM nation_stats")
                        conn.execute(
                            "INSERT OR REPLACE INTO meta(key, value) VALUES ('period_start', ?)",
                            (expected_start,),
                        )
                        conn.commit()
            except Exception as e:
                logger.error(f"NewsDB._do_period_check({path.name}): {e}", exc_info=True)

        # Ensure yearly DB for current year exists
        yearly = _yearly_db_path(now.year)
        if not yearly.exists():
            _init_db(yearly, _year_start_utc().isoformat())
        # Refresh alliance names after any rollover
        self._refresh_alliance_names()

    def _check_period_if_stale(self) -> None:
        """
        Rate-limited period check — runs at most once per 60 seconds.
        Called inside record_event (while holding the lock) so it must be fast.
        """
        if time.monotonic() - self._last_period_check > 60.0:
            self._do_period_check()

    def _get_all_paths(self) -> List[Path]:
        """Return paths for all three active DBs (current period only)."""
        now = datetime.now(timezone.utc)
        return [
            _weekly_db_path(0),
            _monthly_db_path(0),
            _yearly_db_path(now.year),
        ]

    # ── Write helpers ─────────────────────────────────────────────────────────

    def _upsert_alliance_stats(
        self,
        conn: sqlite3.Connection,
        alliance_id: int,
        alliance_name: str,
        alliance_flag: Optional[str],
        delta: Dict[str, Any],
    ) -> None:
        """
        Upsert alliance_stats row and increment all delta counters in a
        single UPDATE statement instead of one per column.

        Always resolves the canonical name/flag from GlobalNations before
        writing — this prevents stale names from recycled alliance IDs from
        being persisted into the stats table.
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # Always prefer the canonical name/flag from GlobalNations
        canonical_name = _nation_cache._alliances.get(int(alliance_id))
        canonical_flag = _nation_cache._alliance_flags.get(int(alliance_id))
        write_name = canonical_name or (alliance_name if alliance_name and alliance_name != '0' else None)
        write_flag = canonical_flag or alliance_flag

        conn.execute(
            """
            INSERT INTO alliance_stats (alliance_id, alliance_name, alliance_flag, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(alliance_id) DO UPDATE SET
                alliance_name = CASE WHEN excluded.alliance_name IS NOT NULL AND excluded.alliance_name != ''
                                     THEN excluded.alliance_name ELSE alliance_name END,
                alliance_flag = COALESCE(excluded.alliance_flag, alliance_flag),
                updated_at    = excluded.updated_at
            """,
            (alliance_id, write_name, write_flag, now_str),
        )
        # Build a single UPDATE for all non-zero delta columns
        updates = {
            col: val for col, val in delta.items()
            if col in _ALLIANCE_STAT_COLS and val != 0 and val is not None
        }
        if updates:
            set_clause = ", ".join(f"{col} = {col} + ?" for col in updates)
            conn.execute(
                f"UPDATE alliance_stats SET {set_clause} WHERE alliance_id = ?",
                list(updates.values()) + [alliance_id],
            )

    def _upsert_nation_stats(
        self,
        conn: sqlite3.Connection,
        nation_id: int,
        nation_name: str,
        nation_flag: Optional[str],
        alliance_id: Optional[int],
        alliance_name: Optional[str],
        delta: Dict[str, Any],
    ) -> None:
        """
        Upsert nation_stats row and increment all delta counters in a
        single UPDATE statement instead of one per column.

        Always resolves the canonical alliance name from GlobalNations before
        writing — prevents stale names from recycled alliance IDs.
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # Always prefer the canonical alliance name from GlobalNations
        if alliance_id and int(alliance_id) != 0:
            canonical_name = _nation_cache._alliances.get(int(alliance_id))
            write_alliance_name = canonical_name or (alliance_name if alliance_name and alliance_name != '0' else None)
        else:
            write_alliance_name = None

        conn.execute(
            """
            INSERT INTO nation_stats (
                nation_id, nation_name, nation_flag, alliance_id, alliance_name, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(nation_id) DO UPDATE SET
                nation_name   = CASE WHEN excluded.nation_name IS NOT NULL AND excluded.nation_name != ''
                                     THEN excluded.nation_name ELSE nation_name END,
                nation_flag   = COALESCE(excluded.nation_flag, nation_flag),
                alliance_id   = COALESCE(excluded.alliance_id, alliance_id),
                alliance_name = CASE WHEN excluded.alliance_name IS NOT NULL AND excluded.alliance_name != ''
                                     THEN excluded.alliance_name ELSE alliance_name END,
                updated_at    = excluded.updated_at
            """,
            (nation_id, nation_name or None, nation_flag, alliance_id, write_alliance_name, now_str),
        )
        updates = {
            col: val for col, val in delta.items()
            if col in _NATION_STAT_COLS and val != 0 and val is not None
        }
        if updates:
            set_clause = ", ".join(f"{col} = {col} + ?" for col in updates)
            conn.execute(
                f"UPDATE nation_stats SET {set_clause} WHERE nation_id = ?",
                list(updates.values()) + [nation_id],
            )

    # ── Public write API ──────────────────────────────────────────────────────

    async def record_event(
        self,
        event_type: str,
        nation_id: Optional[int],
        nation_name: Optional[str],
        nation_flag: Optional[str],
        alliance_id: Optional[int],
        alliance_name: Optional[str],
        alliance_flag: Optional[str],
        value: float,
        value2: float,
        headline: str,
        detail: Dict[str, Any],
        event_date: str,
        alliance_delta: Optional[Dict[str, Any]] = None,
        nation_delta: Optional[Dict[str, Any]] = None,
        # Secondary party (for two-sided events: loot, war, etc.)
        sec_nation_id: Optional[int] = None,
        sec_nation_name: Optional[str] = None,
        sec_alliance_id: Optional[int] = None,
        sec_alliance_name: Optional[str] = None,
        sec_alliance_delta: Optional[Dict[str, Any]] = None,
        sec_nation_delta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Write a single event row to all three news DBs simultaneously.
        Primary party (nation_id / alliance_id) is the main subject.
        Secondary party (sec_*) is the other side of two-sided events.
        Both parties' stats are updated in the same DB transaction.
        """
        # ── Enrich primary party from GlobalNations.db ────────────────────────
        enriched = _nation_cache.enrich(
            nation_id=nation_id,
            nation_name=nation_name,
            nation_flag=nation_flag,
            alliance_id=alliance_id,
            alliance_name=alliance_name,
            alliance_flag=alliance_flag,
        )
        nation_name   = enriched["nation_name"]
        nation_flag   = enriched["nation_flag"]
        alliance_id   = enriched["alliance_id"]
        alliance_name = enriched["alliance_name"]
        alliance_flag = enriched["alliance_flag"]

        # ── Enrich secondary party ────────────────────────────────────────────
        if sec_nation_id or sec_alliance_id:
            sec_enriched = _nation_cache.enrich(
                nation_id=sec_nation_id,
                nation_name=sec_nation_name,
                nation_flag=None,
                alliance_id=sec_alliance_id,
                alliance_name=sec_alliance_name,
                alliance_flag=None,
            )
            sec_nation_name   = sec_enriched["nation_name"]
            sec_alliance_id   = sec_enriched["alliance_id"]
            sec_alliance_name = sec_enriched["alliance_name"]

        # Acquire locks for all three news DB files using LockManager
        paths = self._get_all_paths()
        async with self._lock_manager.acquire_lock(str(paths[0])), \
                     self._lock_manager.acquire_lock(str(paths[1])), \
                     self._lock_manager.acquire_lock(str(paths[2])):
            self._check_period_if_stale()

            now_str     = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            detail_json = json.dumps(detail, default=str)

            for path in paths:
                try:
                    with _open_conn(path) as conn:
                        conn.execute(
                            """
                            INSERT INTO events (
                                event_type, nation_id, nation_name, nation_flag,
                                alliance_id, alliance_name, alliance_flag,
                                sec_nation_id, sec_nation_name,
                                sec_alliance_id, sec_alliance_name,
                                value, value2, headline, detail, event_date, recorded_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                event_type, nation_id, nation_name, nation_flag,
                                alliance_id, alliance_name, alliance_flag,
                                sec_nation_id, sec_nation_name,
                                sec_alliance_id, sec_alliance_name,
                                value, value2, headline, detail_json,
                                event_date, now_str,
                            ),
                        )
                        # Primary party stats
                        if alliance_id and alliance_delta:
                            self._upsert_alliance_stats(
                                conn, alliance_id, alliance_name or "", alliance_flag,
                                alliance_delta,
                            )
                        if nation_id and nation_delta:
                            self._upsert_nation_stats(
                                conn, nation_id, nation_name or "", nation_flag,
                                alliance_id, alliance_name, nation_delta,
                            )
                        # Secondary party stats
                        if sec_alliance_id and sec_alliance_delta:
                            self._upsert_alliance_stats(
                                conn, sec_alliance_id, sec_alliance_name or "", None,
                                sec_alliance_delta,
                            )
                        if sec_nation_id and sec_nation_delta:
                            self._upsert_nation_stats(
                                conn, sec_nation_id, sec_nation_name or "", None,
                                sec_alliance_id, sec_alliance_name, sec_nation_delta,
                            )
                        conn.commit()
                except Exception as e:
                    logger.error(f"NewsDB.record_event({path.name}): {e}", exc_info=True)

    def checkpoint(self) -> None:
        """
        Run a TRUNCATE WAL checkpoint on all three active news DBs.
        Call periodically (e.g. every 5 minutes) from the harvester loop.
        Safe to call while the asyncio lock is NOT held.
        """
        for path in self._get_all_paths():
            if not path.exists():
                continue
            try:
                with sqlite3.connect(str(path)) as conn:
                    result = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                    logger.debug(f"NewsDB checkpoint {path.name}: {result}")
            except Exception as e:
                logger.warning(f"NewsDB.checkpoint({path.name}): {e}")

    async def update_stats_only(
        self,
        nation_id: Optional[int],
        nation_name: Optional[str],
        nation_flag: Optional[str],
        alliance_id: Optional[int],
        alliance_name: Optional[str],
        alliance_flag: Optional[str],
        alliance_delta: Optional[Dict[str, Any]] = None,
        nation_delta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Update alliance_stats and nation_stats without inserting an event row.
        Used for sub-threshold loot events that should affect totals but not
        appear in the news feed.
        """
        if not alliance_delta and not nation_delta:
            return

        enriched = _nation_cache.enrich(
            nation_id=nation_id,
            nation_name=nation_name,
            nation_flag=nation_flag,
            alliance_id=alliance_id,
            alliance_name=alliance_name,
            alliance_flag=alliance_flag,
        )
        nation_name   = enriched["nation_name"]
        nation_flag   = enriched["nation_flag"]
        alliance_id   = enriched["alliance_id"]
        alliance_name = enriched["alliance_name"]
        alliance_flag = enriched["alliance_flag"]

        # Acquire locks for all three news DB files using LockManager
        paths = self._get_all_paths()
        async with self._lock_manager.acquire_lock(str(paths[0])), \
                     self._lock_manager.acquire_lock(str(paths[1])), \
                     self._lock_manager.acquire_lock(str(paths[2])):
            self._check_period_if_stale()
            for path in paths:
                try:
                    with _open_conn(path) as conn:
                        if alliance_id and alliance_delta:
                            self._upsert_alliance_stats(
                                conn, alliance_id, alliance_name or "", alliance_flag,
                                alliance_delta,
                            )
                        if nation_id and nation_delta:
                            self._upsert_nation_stats(
                                conn, nation_id, nation_name or "", nation_flag,
                                alliance_id, alliance_name, nation_delta,
                            )
                        conn.commit()
                except Exception as e:
                    logger.error(f"NewsDB.update_stats_only({path.name}): {e}", exc_info=True)

    # ── Read API ──────────────────────────────────────────────────────────────

    def _read_events(
        self,
        path: Path,
        event_types: Optional[List[str]] = None,
        alliance_id: Optional[int] = None,
        nation_id: Optional[int] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        if not path.exists():
            return []
        try:
            with sqlite3.connect(str(path)) as conn:
                conn.row_factory = sqlite3.Row
                where_clauses: List[str] = []
                params: List[Any] = []
                if event_types:
                    ph = ",".join("?" * len(event_types))
                    where_clauses.append(f"event_type IN ({ph})")
                    params.extend(event_types)
                if alliance_id is not None:
                    # Match either primary or secondary alliance (one row covers both sides)
                    where_clauses.append("(alliance_id = ? OR sec_alliance_id = ?)")
                    params.extend([alliance_id, alliance_id])
                if nation_id is not None:
                    # Match either primary or secondary nation
                    where_clauses.append("(nation_id = ? OR sec_nation_id = ?)")
                    params.extend([nation_id, nation_id])
                where = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

                rows = conn.execute(
                    f"SELECT * FROM events {where} ORDER BY datetime(event_date) DESC LIMIT ? OFFSET ?",
                    params + [limit, offset],
                ).fetchall()

                result = []
                for r in rows:
                    d = dict(r)
                    try:
                        d["detail"] = json.loads(d["detail"]) if d.get("detail") else {}
                    except Exception:
                        d["detail"] = {}
                    result.append(d)
                return result
        except Exception as e:
            logger.error(f"NewsDB._read_events({path.name}): {e}", exc_info=True)
            return []

    def _read_alliance_stats(
        self,
        path: Path,
        alliance_id: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        if not path.exists():
            return []
        try:
            with sqlite3.connect(str(path)) as conn:
                conn.row_factory = sqlite3.Row
                if alliance_id is not None:
                    # Fetch the exact row first, then also fetch any rows that share
                    # the same alliance_name so we can merge them all together.
                    exact = conn.execute(
                        "SELECT * FROM alliance_stats WHERE alliance_id = ?",
                        (alliance_id,),
                    ).fetchone()
                    if exact is None:
                        return []
                    alliance_name = exact["alliance_name"]
                    if alliance_name:
                        rows = conn.execute(
                            "SELECT * FROM alliance_stats WHERE alliance_name = ?",
                            (alliance_name,),
                        ).fetchall()
                    else:
                        rows = [exact]
                    return [self._merge_alliance_rows([dict(r) for r in rows])]
                else:
                    # Fetch all rows, then group by alliance_name and merge duplicates.
                    rows = conn.execute(
                        "SELECT * FROM alliance_stats",
                    ).fetchall()
                    raw = [dict(r) for r in rows]
                    merged = self._group_and_merge_alliance_stats(raw)
                    # Sort by total_spent descending and apply limit
                    merged.sort(key=lambda r: r.get("total_spent") or 0, reverse=True)
                    return merged[:limit]
        except Exception as e:
            logger.error(f"NewsDB._read_alliance_stats({path.name}): {e}", exc_info=True)
            return []

    # ── Alliance stats grouping helpers ───────────────────────────────────────

    _ALLIANCE_SUM_COLS = (
        "cities_built", "projects_bought", "infra_spent", "land_spent",
        "improvements_spent", "military_spent", "wars_declared", "wars_won",
        "wars_lost", "wars_drawn", "loot_gained", "loot_lost",
        "infra_destroyed", "nukes_used", "missiles_used",
        "bank_deposits", "bank_withdrawals", "total_spent",
    )

    def _merge_alliance_rows(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Merge multiple alliance_stats rows (same alliance name, different IDs)
        into a single aggregated row.  The canonical alliance_id and alliance_flag
        are taken from the row with the highest |total_spent|.
        """
        if len(rows) == 1:
            return rows[0]
        # Pick the most active row as the canonical identity
        canonical = max(rows, key=lambda r: abs(r.get("total_spent") or 0))
        merged: Dict[str, Any] = dict(canonical)
        for col in self._ALLIANCE_SUM_COLS:
            merged[col] = sum(r.get(col) or 0 for r in rows)
        # Keep the most recent updated_at
        updated_ats = [r.get("updated_at") for r in rows if r.get("updated_at")]
        if updated_ats:
            merged["updated_at"] = max(updated_ats)
        return merged

    def _group_and_merge_alliance_stats(
        self, rows: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Group alliance_stats rows by alliance_name and merge duplicates.
        Rows with a NULL/empty name are kept as-is (grouped by alliance_id).
        """
        named: Dict[str, List[Dict[str, Any]]] = {}
        unnamed: List[Dict[str, Any]] = []
        for row in rows:
            name = (row.get("alliance_name") or "").strip()
            if name:
                named.setdefault(name, []).append(row)
            else:
                unnamed.append(row)
        result: List[Dict[str, Any]] = []
        for group in named.values():
            result.append(self._merge_alliance_rows(group))
        result.extend(unnamed)
        return result

    def _read_nation_stats(
        self,
        path: Path,
        alliance_id: Optional[int] = None,
        nation_id: Optional[int] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        if not path.exists():
            return []
        try:
            with sqlite3.connect(str(path)) as conn:
                conn.row_factory = sqlite3.Row
                if nation_id is not None:
                    rows = conn.execute(
                        "SELECT * FROM nation_stats WHERE nation_id = ?",
                        (nation_id,),
                    ).fetchall()
                elif alliance_id is not None:
                    rows = conn.execute(
                        "SELECT * FROM nation_stats WHERE alliance_id = ? ORDER BY total_spent DESC LIMIT ?",
                        (alliance_id, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM nation_stats ORDER BY total_spent DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"NewsDB._read_nation_stats({path.name}): {e}", exc_info=True)
            return []

    def _get_period_meta(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with sqlite3.connect(str(path)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT key, value FROM meta").fetchall()
                meta = {r["key"]: r["value"] for r in rows}
                cnt = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
                meta["event_count"] = cnt
                return meta
        except Exception as e:
            logger.error(f"NewsDB._get_period_meta({path.name}): {e}", exc_info=True)
            return {}

    # ── Public read API ───────────────────────────────────────────────────────

    def get_events(
        self,
        period: str = "weekly",
        year: Optional[int] = None,
        event_types: Optional[List[str]] = None,
        alliance_id: Optional[int] = None,
        nation_id: Optional[int] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        return self._read_events(
            self._period_path(period, year),
            event_types, alliance_id, nation_id, limit, offset,
        )

    def get_alliance_stats(
        self,
        period: str = "weekly",
        year: Optional[int] = None,
        alliance_id: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return self._read_alliance_stats(self._period_path(period, year), alliance_id, limit)

    def get_nation_stats(
        self,
        period: str = "weekly",
        year: Optional[int] = None,
        alliance_id: Optional[int] = None,
        nation_id: Optional[int] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        return self._read_nation_stats(self._period_path(period, year), alliance_id, nation_id, limit)

    def get_period_meta(self, period: str = "weekly", year: Optional[int] = None) -> Dict[str, Any]:
        return self._get_period_meta(self._period_path(period, year))

    def _period_path(self, period: str, year: Optional[int] = None) -> Path:
        if period == "monthly":
            return _monthly_db_path(0)
        if period == "prev_monthly":
            return _monthly_db_path(-1)
        if period == "prev_weekly":
            return _weekly_db_path(-1)
        if period == "yearly":
            return _yearly_db_path(year)
        return _weekly_db_path(0)

    def get_available_years(self) -> List[int]:
        years = []
        for p in _DB_ROOT.glob("YearlyNews*.db"):
            try:
                y = int(p.stem.replace("YearlyNews", ""))
                years.append(y)
            except ValueError:
                pass
        return sorted(years, reverse=True)

    def get_available_periods(self) -> Dict[str, Any]:
        return {
            "has_prev_weekly":   _weekly_db_path(-1).exists(),
            "has_prev_monthly":  _monthly_db_path(-1).exists(),
            "prev_weekly_meta":  self._get_period_meta(_weekly_db_path(-1))  if _weekly_db_path(-1).exists()  else {},
            "prev_monthly_meta": self._get_period_meta(_monthly_db_path(-1)) if _monthly_db_path(-1).exists() else {},
            "available_years":   self.get_available_years(),
        }


# ── Module-level singleton ────────────────────────────────────────────────────
_news_db: Optional[NewsDB] = None

def get_news_db() -> NewsDB:
    global _news_db
    if _news_db is None:
        _news_db = NewsDB()
    return _news_db

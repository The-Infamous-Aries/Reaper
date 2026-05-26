"""
BankrecsDB — SQLite storage for ALL bank records in the game.

Stores every bankrec/create event from the PnW WebSocket subscription.
This allows fast lookups of "what was sent to/from nation X" without
querying the PnW API.

Schema:
  - id: unique bankrec ID (from PnW)
  - date: transaction timestamp
  - sender_id: entity that sent the transfer
  - sender_type: 1=nation, 2=alliance
  - receiver_id: entity that received the transfer
  - receiver_type: 1=nation, 2=alliance
  - banker_id: nation that initiated the transfer (for alliance sends)
  - note: optional note on the transfer
  - money, coal, oil, ...: amounts transferred (11 resources + money)
  - tax_id: tax bracket ID if this was a tax collection
  - created_at: when we recorded it

Now inherits from BaseDB for unified async patterns and connection management.
"""

import sqlite3
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import asyncio
from .base_db import BaseDB, AsyncMode

logger = logging.getLogger(__name__)

BANKREC_RESOURCE_COLUMNS = (
    "coal", "oil", "uranium", "iron", "bauxite", "lead",
    "gasoline", "munitions", "steel", "aluminum", "food",
)


class BankrecsDB(BaseDB):
    def __init__(self, db_path: str):
        """
        Initialize BankrecsDB with BaseDB infrastructure.
        
        Args:
            db_path: Path to the SQLite database file
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
        self._init_bankrecs_schema()

    def _init_bankrecs_schema(self):
        """Initialize the BankrecsDB-specific schema (bankrecs table)."""
        try:
            with self._get_connection() as conn:
                c = conn.cursor()

                c.execute("""
                    CREATE TABLE IF NOT EXISTS bankrecs (
                        id              INTEGER PRIMARY KEY,
                        date            TEXT NOT NULL,
                        sender_id       INTEGER,
                        sender_type     INTEGER,
                        receiver_id     INTEGER,
                        receiver_type   INTEGER,
                        banker_id       INTEGER,
                        note            TEXT,
                        money           REAL DEFAULT 0,
                        coal            REAL DEFAULT 0,
                        oil             REAL DEFAULT 0,
                        uranium         REAL DEFAULT 0,
                        iron            REAL DEFAULT 0,
                        bauxite         REAL DEFAULT 0,
                        lead            REAL DEFAULT 0,
                        gasoline        REAL DEFAULT 0,
                        munitions       REAL DEFAULT 0,
                        steel           REAL DEFAULT 0,
                        aluminum        REAL DEFAULT 0,
                        food            REAL DEFAULT 0,
                        tax_id          INTEGER,
                        created_at      TEXT NOT NULL
                    )
                """)

                # Indexes for the most common query patterns
                c.execute("CREATE INDEX IF NOT EXISTS idx_br_sender   ON bankrecs(sender_id,   sender_type,   date DESC)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_br_receiver ON bankrecs(receiver_id, receiver_type, date DESC)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_br_date     ON bankrecs(date DESC)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_br_banker   ON bankrecs(banker_id)")

                conn.commit()
                logger.info("BankrecsDB initialized successfully")
        except Exception as e:
            logger.error(f"BankrecsDB init error: {e}", exc_info=True)
            raise

    def _ensure_schema(self):
        """Re-run schema creation if the bankrecs table is missing. Self-heals a 0-byte or wiped DB."""
        try:
            with self._get_connection() as conn:
                exists = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='bankrecs'"
                ).fetchone()
                if not exists:
                    logger.warning("BankrecsDB: bankrecs table missing — re-initialising schema")
                    self._init_bankrecs_schema()
        except Exception as e:
            logger.error(f"BankrecsDB._ensure_schema: {e}", exc_info=True)

    async def save_bankrec(self, rec: Dict[str, Any]) -> bool:
        """
        Save a bank record. Uses INSERT OR IGNORE so duplicate IDs are silently skipped.
        
        Args:
            rec: Bankrec dict with id, date, sender_id, sender_type, receiver_id,
                 receiver_type, banker_id, note, money, *resource* fields, tax_id
        """
        rec_id = rec.get("id")
        if not rec_id:
            return False

        # Normalize date to consistent format (space separator, no T)
        date_val = rec.get("date")
        if date_val is not None:
            rec = dict(rec)
            rec["date"] = str(date_val).replace("T", " ")

        async with self._get_lock():
            try:
                with self._get_connection() as conn:
                    c = conn.cursor()
                    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

                    c.execute("""
                        INSERT OR IGNORE INTO bankrecs (
                            id, date, sender_id, sender_type, receiver_id, receiver_type,
                            banker_id, note, money,
                            coal, oil, uranium, iron, bauxite, lead,
                            gasoline, munitions, steel, aluminum, food,
                            tax_id, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        rec_id,
                        rec.get("date"),
                        rec.get("sender_id"),
                        rec.get("sender_type"),
                        rec.get("receiver_id"),
                        rec.get("receiver_type"),
                        rec.get("banker_id"),
                        rec.get("note"),
                        float(rec.get("money") or 0),
                        float(rec.get("coal") or 0),
                        float(rec.get("oil") or 0),
                        float(rec.get("uranium") or 0),
                        float(rec.get("iron") or 0),
                        float(rec.get("bauxite") or 0),
                        float(rec.get("lead") or 0),
                        float(rec.get("gasoline") or 0),
                        float(rec.get("munitions") or 0),
                        float(rec.get("steel") or 0),
                        float(rec.get("aluminum") or 0),
                        float(rec.get("food") or 0),
                        rec.get("tax_id"),
                        now,
                    ))
                    conn.commit()
                    return c.rowcount > 0
            except sqlite3.OperationalError as e:
                if "no such table" in str(e):
                    # DB was wiped or created empty — rebuild schema and retry once
                    logger.warning(f"BankrecsDB.save_bankrec: schema missing, rebuilding and retrying")
                    self._init_bankrecs_schema()
                    return await self._save_bankrec_direct(rec, rec_id)
                logger.error(f"BankrecsDB.save_bankrec({rec_id}): {e}", exc_info=True)
                return False
            except Exception as e:
                logger.error(f"BankrecsDB.save_bankrec({rec_id}): {e}", exc_info=True)
                return False

    async def _save_bankrec_direct(self, rec: Dict[str, Any], rec_id: Any) -> bool:
        """Retry insert after schema rebuild — called only from save_bankrec error path."""
        try:
            with self._get_connection() as conn:
                now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                conn.execute("""
                    INSERT OR IGNORE INTO bankrecs (
                        id, date, sender_id, sender_type, receiver_id, receiver_type,
                        banker_id, note, money,
                        coal, oil, uranium, iron, bauxite, lead,
                        gasoline, munitions, steel, aluminum, food,
                        tax_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    rec_id,
                    rec.get("date"),
                    rec.get("sender_id"),
                    rec.get("sender_type"),
                    rec.get("receiver_id"),
                    rec.get("receiver_type"),
                    rec.get("banker_id"),
                    rec.get("note"),
                    float(rec.get("money") or 0),
                    float(rec.get("coal") or 0),
                    float(rec.get("oil") or 0),
                    float(rec.get("uranium") or 0),
                    float(rec.get("iron") or 0),
                    float(rec.get("bauxite") or 0),
                    float(rec.get("lead") or 0),
                    float(rec.get("gasoline") or 0),
                    float(rec.get("munitions") or 0),
                    float(rec.get("steel") or 0),
                    float(rec.get("aluminum") or 0),
                    float(rec.get("food") or 0),
                    rec.get("tax_id"),
                    now,
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"BankrecsDB._save_bankrec_direct({rec_id}): {e}", exc_info=True)
            return False

    async def save_bankrecs_bulk(self, recs: List[Dict[str, Any]]) -> int:
        """Bulk insert bank records. Returns count of new records inserted."""
        if not recs:
            return 0
        saved = 0
        async with self._get_lock():
            try:
                with self._get_connection() as conn:
                    c = conn.cursor()
                    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    for rec in recs:
                        rec_id = rec.get("id")
                        if not rec_id:
                            continue
                        # Normalize date to consistent format (space separator, no T)
                        date_val = rec.get("date")
                        if date_val is not None:
                            rec["date"] = str(date_val).replace("T", " ")
                        c.execute("""
                            INSERT OR IGNORE INTO bankrecs (
                                id, date, sender_id, sender_type, receiver_id, receiver_type,
                                banker_id, note, money,
                                coal, oil, uranium, iron, bauxite, lead,
                                gasoline, munitions, steel, aluminum, food,
                                tax_id, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            rec_id,
                            rec.get("date"),
                            rec.get("sender_id"),
                            rec.get("sender_type"),
                            rec.get("receiver_id"),
                            rec.get("receiver_type"),
                            rec.get("banker_id"),
                            rec.get("note"),
                            float(rec.get("money") or 0),
                            float(rec.get("coal") or 0),
                            float(rec.get("oil") or 0),
                            float(rec.get("uranium") or 0),
                            float(rec.get("iron") or 0),
                            float(rec.get("bauxite") or 0),
                            float(rec.get("lead") or 0),
                            float(rec.get("gasoline") or 0),
                            float(rec.get("munitions") or 0),
                            float(rec.get("steel") or 0),
                            float(rec.get("aluminum") or 0),
                            float(rec.get("food") or 0),
                            rec.get("tax_id"),
                            now,
                        ))
                        if c.rowcount > 0:
                            saved += 1
                    conn.commit()
            except sqlite3.OperationalError as e:
                if "no such table" in str(e):
                    logger.warning("BankrecsDB.save_bankrecs_bulk: schema missing, rebuilding")
                    self._init_bankrecs_schema()
                    # Retry the whole batch after rebuild
                    return await self._save_bankrecs_bulk_direct(recs)
                logger.error(f"BankrecsDB.save_bankrecs_bulk: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"BankrecsDB.save_bankrecs_bulk: {e}", exc_info=True)
        return saved

    async def _save_bankrecs_bulk_direct(self, recs: List[Dict[str, Any]]) -> int:
        """Retry bulk insert after schema rebuild."""
        saved = 0
        try:
            with self._get_connection() as conn:
                c = conn.cursor()
                now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                for rec in recs:
                    rec_id = rec.get("id")
                    if not rec_id:
                        continue
                    date_val = rec.get("date")
                    if date_val is not None:
                        rec["date"] = str(date_val).replace("T", " ")
                    c.execute("""
                        INSERT OR IGNORE INTO bankrecs (
                            id, date, sender_id, sender_type, receiver_id, receiver_type,
                            banker_id, note, money,
                            coal, oil, uranium, iron, bauxite, lead,
                            gasoline, munitions, steel, aluminum, food,
                            tax_id, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        rec_id, rec.get("date"),
                        rec.get("sender_id"), rec.get("sender_type"),
                        rec.get("receiver_id"), rec.get("receiver_type"),
                        rec.get("banker_id"), rec.get("note"),
                        float(rec.get("money") or 0),
                        float(rec.get("coal") or 0), float(rec.get("oil") or 0),
                        float(rec.get("uranium") or 0), float(rec.get("iron") or 0),
                        float(rec.get("bauxite") or 0), float(rec.get("lead") or 0),
                        float(rec.get("gasoline") or 0), float(rec.get("munitions") or 0),
                        float(rec.get("steel") or 0), float(rec.get("aluminum") or 0),
                        float(rec.get("food") or 0), rec.get("tax_id"), now,
                    ))
                    if c.rowcount > 0:
                        saved += 1
                conn.commit()
        except Exception as e:
            logger.error(f"BankrecsDB._save_bankrecs_bulk_direct: {e}", exc_info=True)
        return saved

    async def get_bankrecs_for_nation(
        self,
        nation_id: int,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get all bankrecs where nation_id was sender or receiver (type=1)."""
        async with self._get_lock():
            try:
                with self._get_connection() as conn:
                    conn.row_factory = sqlite3.Row
                    params: list = [nation_id, nation_id]
                    since_clause = ""
                    if since:
                        since_str = since.strftime("%Y-%m-%d %H:%M:%S")
                        since_clause = "AND date >= ?"
                        params.append(since_str)
                    params.append(limit)
                    rows = conn.execute(
                        f"""SELECT * FROM bankrecs
                            WHERE ((sender_id = ? AND sender_type = 1)
                               OR  (receiver_id = ? AND receiver_type = 1))
                            {since_clause}
                            ORDER BY date DESC LIMIT ?""",
                        params
                    ).fetchall()
                    return [dict(r) for r in rows]
            except Exception as e:
                logger.error(f"BankrecsDB.get_bankrecs_for_nation({nation_id}): {e}")
                return []

    async def get_bankrecs_for_alliance(
        self,
        alliance_id: int,
        since: Optional[datetime] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """Get all bankrecs where alliance_id was sender or receiver (type=2)."""
        async with self._get_lock():
            try:
                with self._get_connection() as conn:
                    conn.row_factory = sqlite3.Row
                    params: list = [alliance_id, alliance_id]
                    since_clause = ""
                    if since:
                        since_str = since.strftime("%Y-%m-%d %H:%M:%S")
                        since_clause = "AND date >= ?"
                        params.append(since_str)
                    params.append(limit)
                    rows = conn.execute(
                        f"""SELECT * FROM bankrecs
                            WHERE ((sender_id = ? AND sender_type = 2)
                               OR  (receiver_id = ? AND receiver_type = 2))
                            {since_clause}
                            ORDER BY date DESC LIMIT ?""",
                        params
                    ).fetchall()
                    return [dict(r) for r in rows]
            except Exception as e:
                logger.error(f"BankrecsDB.get_bankrecs_for_alliance({alliance_id}): {e}")
                return []

    async def get_bankrecs_for_nations_bulk(
        self,
        nation_ids: List[int],
        since: Optional[datetime] = None,
        limit_per_nation: int = 30,
    ) -> Dict[int, List[Dict[str, Any]]]:
        """
        Fetch bankrecs for multiple nations in a single query.
        Returns a dict keyed by nation_id, each value a list of records
        sorted by date DESC, capped at limit_per_nation per nation.

        Matches the same logic as get_bankrecs_for_nation:
          - nation was sender (sender_id=id, sender_type=1)
          - nation was receiver (receiver_id=id, receiver_type=1)
        """
        if not nation_ids:
            return {}
        async with self._get_lock():
            try:
                with self._get_connection() as conn:
                    conn.row_factory = sqlite3.Row
                    placeholders = ",".join("?" * len(nation_ids))

                    params: list = list(nation_ids) + list(nation_ids)
                    since_clause = ""
                    if since:
                        since_str = since.strftime("%Y-%m-%d %H:%M:%S")
                        since_clause = "AND date >= ?"
                        params.append(since_str)

                    # Fetch all matching rows in one shot — we cap per-nation in Python
                    rows = conn.execute(
                        f"""SELECT * FROM bankrecs
                            WHERE (
                                (sender_id   IN ({placeholders}) AND sender_type   = 1)
                             OR (receiver_id IN ({placeholders}) AND receiver_type = 1)
                            )
                            {since_clause}
                            ORDER BY date DESC""",
                        params,
                    ).fetchall()

                    # Group by nation_id, respecting limit_per_nation
                    result: Dict[int, List[Dict[str, Any]]] = {nid: [] for nid in nation_ids}
                    for row in rows:
                        rec = dict(row)
                        sid   = int(rec.get("sender_id")   or 0)
                        stype = int(rec.get("sender_type")  or 0)
                        rid   = int(rec.get("receiver_id")  or 0)
                        rtype = int(rec.get("receiver_type") or 0)

                        if rtype == 1 and rid in result:
                            if len(result[rid]) < limit_per_nation:
                                result[rid].append(rec)
                        if stype == 1 and sid in result:
                            if len(result[sid]) < limit_per_nation:
                                result[sid].append(rec)

                    return result
            except Exception as e:
                logger.error(f"BankrecsDB.get_bankrecs_for_nations_bulk: {e}")
                return {}

    async def get_newest_date(self) -> Optional[str]:
        """Return the most recent `date` value stored, or None if the table is empty."""
        async with self._get_lock():
            try:
                with self._get_connection() as conn:
                    row = conn.execute(
                        "SELECT MAX(date) as newest FROM bankrecs"
                    ).fetchone()
                    return row[0] if row else None
            except Exception as e:
                logger.error(f"BankrecsDB.get_newest_date: {e}")
                return None

    async def cleanup_old_bankrecs(self, days: int = 30):
        """Delete bankrecs older than N days."""
        async with self._get_lock():
            try:
                with self._get_connection() as conn:
                    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
                    c = conn.cursor()
                    c.execute("DELETE FROM bankrecs WHERE date < ?", (cutoff,))
                    deleted = c.rowcount
                    conn.commit()
                    logger.info(f"BankrecsDB: cleaned up {deleted} records older than {days} days")
                    return deleted
            except Exception as e:
                logger.error(f"BankrecsDB.cleanup_old_bankrecs: {e}")
                return 0

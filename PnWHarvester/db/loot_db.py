"""
LootDB — one row per nation, tracking the most recent loot event.

Only the LATEST loot event per defender is kept. When a newer event arrives
for the same nation, the existing row is replaced. This keeps the table small
and ensures the raids page always sees the freshest data.

Schema (keyed on defender_id, not attack_id):
  - defender_id     : PRIMARY KEY — the nation that was looted
  - defender_name   : nation name (denormalized for display)
  - attacker_id     : nation that looted
  - attacker_name   : nation name
  - attack_id       : the specific attack ID
  - war_id          : parent war
  - date            : attack timestamp (used to decide newer vs older)
  - war_type        : 'raid', 'ordinary', 'attrition' — for loot % calculation
  - att_war_policy  : attacker's war policy — for loot % calculation
  - def_war_policy  : defender's war policy — for loot % calculation
  - money_looted    : cash looted
  - coal_looted ... : resource loot (11 resources)
  - updated_at      : when we recorded it
"""

import sqlite3
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import asyncio

logger = logging.getLogger(__name__)

LOOT_RESOURCE_COLUMNS = (
    "coal", "oil", "uranium", "iron", "bauxite", "lead",
    "gasoline", "munitions", "steel", "aluminum", "food",
)


class LootDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self._init_database()

    def _init_database(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()

                c.execute("""
                    CREATE TABLE IF NOT EXISTS loot_events (
                        defender_id      INTEGER PRIMARY KEY,
                        defender_name    TEXT,
                        attacker_id      INTEGER NOT NULL,
                        attacker_name    TEXT,
                        attack_id        INTEGER NOT NULL,
                        war_id           INTEGER NOT NULL,
                        date             TEXT NOT NULL,
                        war_type         TEXT,
                        att_war_policy   TEXT,
                        def_war_policy   TEXT,
                        money_looted     REAL DEFAULT 0,
                        coal_looted      REAL DEFAULT 0,
                        oil_looted       REAL DEFAULT 0,
                        uranium_looted   REAL DEFAULT 0,
                        iron_looted      REAL DEFAULT 0,
                        bauxite_looted   REAL DEFAULT 0,
                        lead_looted      REAL DEFAULT 0,
                        gasoline_looted  REAL DEFAULT 0,
                        munitions_looted REAL DEFAULT 0,
                        steel_looted     REAL DEFAULT 0,
                        aluminum_looted  REAL DEFAULT 0,
                        food_looted      REAL DEFAULT 0,
                        updated_at       TEXT NOT NULL
                    )
                """)

                c.execute("CREATE INDEX IF NOT EXISTS idx_loot_date ON loot_events(date DESC)")

                # Add new columns to existing DBs that predate this schema
                for col, col_type in [
                    ("war_type",       "TEXT"),
                    ("att_war_policy", "TEXT"),
                    ("def_war_policy", "TEXT"),
                ]:
                    try:
                        c.execute(f"ALTER TABLE loot_events ADD COLUMN {col} {col_type}")
                    except Exception:
                        pass  # column already exists

                conn.commit()
                logger.info("LootDB initialized successfully")
        except Exception as e:
            logger.error(f"LootDB init error: {e}", exc_info=True)
            raise

    async def save_loot_event(
        self,
        attack: Dict[str, Any],
        defender_name: Optional[str] = None,
        attacker_name: Optional[str] = None,
        war_type: Optional[str] = None,
        att_war_policy: Optional[str] = None,
        def_war_policy: Optional[str] = None,
    ) -> bool:
        """
        Upsert a loot event for a nation.
        Only replaces the existing row if this event is NEWER than what's stored.
        One row per defender — always reflects the most recent loot.
        """
        defender_id = attack.get("def_id") or attack.get("defender_id")
        attacker_id = attack.get("att_id") or attack.get("attacker_id")
        attack_id   = attack.get("id")
        war_id      = attack.get("war_id")
        date        = attack.get("date")

        if not defender_id or not attacker_id or not date:
            return False

        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    c = conn.cursor()
                    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

                    # Only update if this event is newer than what we have
                    c.execute("SELECT date FROM loot_events WHERE defender_id = ?", (defender_id,))
                    existing = c.fetchone()
                    if existing:
                        existing_date = existing[0] or ""
                        if str(date) <= existing_date:
                            return False  # Already have a newer or equal event

                    c.execute("""
                        INSERT OR REPLACE INTO loot_events (
                            defender_id, defender_name, attacker_id, attacker_name,
                            attack_id, war_id, date,
                            war_type, att_war_policy, def_war_policy,
                            money_looted,
                            coal_looted, oil_looted, uranium_looted, iron_looted,
                            bauxite_looted, lead_looted, gasoline_looted, munitions_looted,
                            steel_looted, aluminum_looted, food_looted,
                            updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        defender_id,
                        defender_name,
                        attacker_id,
                        attacker_name,
                        attack_id,
                        war_id,
                        date,
                        war_type,
                        att_war_policy,
                        def_war_policy,
                        float(attack.get("money_looted") or 0),
                        float(attack.get("coal_looted") or 0),
                        float(attack.get("oil_looted") or 0),
                        float(attack.get("uranium_looted") or 0),
                        float(attack.get("iron_looted") or 0),
                        float(attack.get("bauxite_looted") or 0),
                        float(attack.get("lead_looted") or 0),
                        float(attack.get("gasoline_looted") or 0),
                        float(attack.get("munitions_looted") or 0),
                        float(attack.get("steel_looted") or 0),
                        float(attack.get("aluminum_looted") or 0),
                        float(attack.get("food_looted") or 0),
                        now,
                    ))
                    conn.commit()
                    return True
            except Exception as e:
                logger.error(f"LootDB.save_loot_event(defender={defender_id}): {e}", exc_info=True)
                return False

    async def get_loot_for_nation(self, nation_id: int) -> Optional[Dict[str, Any]]:
        """Get the most recent loot event for a nation (single row)."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute(
                        "SELECT * FROM loot_events WHERE defender_id = ?",
                        (nation_id,)
                    ).fetchone()
                    return dict(row) if row else None
            except Exception as e:
                logger.error(f"LootDB.get_loot_for_nation({nation_id}): {e}")
                return None

    # Alias used by raids_api.py
    async def get_latest_loot_for_nation(self, nation_id: int) -> Optional[Dict[str, Any]]:
        return await self.get_loot_for_nation(nation_id)

    async def get_loot_for_nations_bulk(
        self, nation_ids: List[int]
    ) -> Dict[int, Dict[str, Any]]:
        """
        Fetch loot events for multiple nations in a single query.
        Returns a dict keyed by defender_id.
        """
        if not nation_ids:
            return {}
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    placeholders = ",".join("?" * len(nation_ids))
                    rows = conn.execute(
                        f"SELECT * FROM loot_events WHERE defender_id IN ({placeholders})",
                        nation_ids,
                    ).fetchall()
                    return {int(r["defender_id"]): dict(r) for r in rows}
            except Exception as e:
                logger.error(f"LootDB.get_loot_for_nations_bulk: {e}")
                return {}

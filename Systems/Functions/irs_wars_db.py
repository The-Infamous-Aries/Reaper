import sqlite3
import json
import logging
from datetime import datetime, timezone, date
from typing import Dict, List, Any, Optional
from pathlib import Path
import asyncio

logger = logging.getLogger(__name__)
LOOT_RESOURCE_COLUMNS = (
    "coal",
    "oil",
    "uranium",
    "iron",
    "bauxite",
    "lead",
    "gasoline",
    "munitions",
    "steel",
    "aluminum",
    "food",
)

class IRSWarsDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self._init_database()
    
    def _init_database(self):
        """Initialize the database with required tables."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Wars table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS wars (
                        id INTEGER PRIMARY KEY,
                        date TEXT,
                        end_date TEXT,
                        reason TEXT,
                        war_type INTEGER,
                        ground_control INTEGER,
                        air_superiority INTEGER,
                        naval_blockade INTEGER,
                        winner_id INTEGER,
                        turns_left INTEGER,
                        att_id INTEGER,
                        def_id INTEGER,
                        att_alliance_id INTEGER,
                        att_alliance_position INTEGER,
                        def_alliance_id INTEGER,
                        def_alliance_position INTEGER,
                        att_alliance_name TEXT,
                        def_alliance_name TEXT,
                        att_nation_name TEXT,
                        att_leader_name TEXT,
                        def_nation_name TEXT,
                        def_leader_name TEXT,
                        att_points REAL,
                        def_points REAL,
                        att_peace INTEGER,
                        def_peace INTEGER,
                        att_resistance INTEGER,
                        def_resistance INTEGER,
                        att_fortify INTEGER,
                        def_fortify INTEGER,
                        att_gas_used REAL,
                        def_gas_used REAL,
                        att_mun_used REAL,
                        def_mun_used REAL,
                        att_infra_destroyed REAL,
                        def_infra_destroyed REAL,
                        att_infra_destroyed_value REAL,
                        def_infra_destroyed_value REAL,
                        att_soldiers_lost INTEGER,
                        def_soldiers_lost INTEGER,
                        att_tanks_lost INTEGER,
                        def_tanks_lost INTEGER,
                        att_aircraft_lost INTEGER,
                        def_aircraft_lost INTEGER,
                        att_ships_lost INTEGER,
                        def_ships_lost INTEGER,
                        att_missiles_used INTEGER,
                        def_missiles_used INTEGER,
                        att_nukes_used INTEGER,
                        def_nukes_used INTEGER,
                        created_at TEXT,
                        updated_at TEXT
                    )
                ''')
                
                # War attacks table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS war_attacks (
                        id INTEGER PRIMARY KEY,
                        war_id INTEGER,
                        date TEXT,
                        attacker_id INTEGER,
                        defender_id INTEGER,
                        type INTEGER,
                        attack_type INTEGER,
                        victor INTEGER,
                        success INTEGER,
                        attcas1 REAL,
                        defcas1 REAL,
                        attcas2 REAL,
                        defcas2 REAL,
                        city_infra_before REAL,
                        infra_destroyed REAL,
                        infra_destroyed_value REAL,
                        improvements_destroyed TEXT,
                        money_stolen REAL,
                        money_destroyed REAL,
                        military_salvage_aluminum REAL,
                        military_salvage_steel REAL,
                        money_looted REAL,
                        coal_looted REAL,
                        oil_looted REAL,
                        uranium_looted REAL,
                        iron_looted REAL,
                        bauxite_looted REAL,
                        lead_looted REAL,
                        gasoline_looted REAL,
                        munitions_looted REAL,
                        steel_looted REAL,
                        aluminum_looted REAL,
                        food_looted REAL,
                        loot_info TEXT,
                        resistance_war INTEGER,
                        resistance_lost INTEGER,
                        city_id INTEGER,
                        infra_maps INTEGER,
                        note TEXT,
                        created_at TEXT,
                        att_missiles_lost INTEGER,
                        def_missiles_lost INTEGER,
                        att_nukes_lost INTEGER,
                        def_nukes_lost INTEGER,
                        FOREIGN KEY (war_id) REFERENCES wars (id)
                    )
                ''')
                
                # Subscription war attacks table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS subscription_war_attacks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        attack_id INTEGER,
                        war_id INTEGER,
                        date TEXT,
                        attacker_id INTEGER,
                        defender_id INTEGER,
                        type INTEGER,
                        attack_type INTEGER,
                        victor INTEGER,
                        success INTEGER,
                        attcas1 REAL,
                        defcas1 REAL,
                        attcas2 REAL,
                        defcas2 REAL,
                        city_infra_before REAL,
                        infra_destroyed REAL,
                        infra_destroyed_value REAL,
                        improvements_destroyed TEXT,
                        money_stolen REAL,
                        money_looted REAL,
                        coal_looted REAL,
                        oil_looted REAL,
                        uranium_looted REAL,
                        iron_looted REAL,
                        bauxite_looted REAL,
                        lead_looted REAL,
                        gasoline_looted REAL,
                        munitions_looted REAL,
                        steel_looted REAL,
                        aluminum_looted REAL,
                        food_looted REAL,
                        loot_info TEXT,
                        resistance_war INTEGER,
                        resistance_lost INTEGER,
                        city_id INTEGER,
                        infra_maps INTEGER,
                        note TEXT,
                        processed BOOLEAN DEFAULT FALSE,
                        created_at TEXT,
                        att_missiles_lost INTEGER,
                        def_missiles_lost INTEGER,
                        att_nukes_lost INTEGER,
                        def_nukes_lost INTEGER
                    )
                ''')

                self._ensure_column(cursor, 'war_attacks', 'att_missiles_lost', 'INTEGER')
                self._ensure_column(cursor, 'war_attacks', 'def_missiles_lost', 'INTEGER')
                self._ensure_column(cursor, 'war_attacks', 'att_nukes_lost', 'INTEGER')
                self._ensure_column(cursor, 'war_attacks', 'def_nukes_lost', 'INTEGER')
                self._ensure_column(cursor, 'war_attacks', 'money_looted', 'REAL')
                self._ensure_column(cursor, 'war_attacks', 'infra_destroyed_value', 'REAL')
                self._ensure_column(cursor, 'war_attacks', 'money_destroyed', 'REAL')
                self._ensure_column(cursor, 'war_attacks', 'military_salvage_aluminum', 'REAL')
                self._ensure_column(cursor, 'war_attacks', 'military_salvage_steel', 'REAL')
                for resource in LOOT_RESOURCE_COLUMNS:
                    self._ensure_column(cursor, 'war_attacks', f'{resource}_looted', 'REAL')
                self._ensure_column(cursor, 'subscription_war_attacks', 'att_missiles_lost', 'INTEGER')
                self._ensure_column(cursor, 'subscription_war_attacks', 'def_missiles_lost', 'INTEGER')
                self._ensure_column(cursor, 'subscription_war_attacks', 'att_nukes_lost', 'INTEGER')
                self._ensure_column(cursor, 'subscription_war_attacks', 'def_nukes_lost', 'INTEGER')
                self._ensure_column(cursor, 'subscription_war_attacks', 'money_looted', 'REAL')
                self._ensure_column(cursor, 'subscription_war_attacks', 'infra_destroyed_value', 'REAL')
                self._ensure_column(cursor, 'wars', 'att_infra_destroyed_value', 'REAL')
                self._ensure_column(cursor, 'wars', 'def_infra_destroyed_value', 'REAL')
                self._ensure_column(cursor, 'wars', 'att_alliance_name', 'TEXT')
                self._ensure_column(cursor, 'wars', 'def_alliance_name', 'TEXT')
                for resource in LOOT_RESOURCE_COLUMNS:
                    self._ensure_column(cursor, 'subscription_war_attacks', f'{resource}_looted', 'REAL')
                
                # Create indexes
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_wars_att_alliance_id ON wars(att_alliance_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_wars_def_alliance_id ON wars(def_alliance_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_war_attacks_war_id ON war_attacks(war_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscription_attacks_processed ON subscription_war_attacks(processed)')
                # Composite indexes for date-range queries (avoids full table scan + string substr)
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_wars_att_alliance_date ON wars(att_alliance_id, date)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_wars_def_alliance_date ON wars(def_alliance_id, date)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_wars_date ON wars(date)')
                
                conn.commit()
                logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise

    @staticmethod
    def _ensure_column(cursor: sqlite3.Cursor, table_name: str, column_name: str, column_type: str):
        cursor.execute(f"PRAGMA table_info({table_name})")
        existing_columns = {row[1] for row in cursor.fetchall()}
        if column_name not in existing_columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")

    @staticmethod
    def _coerce_attack_id(attack_data: Dict[str, Any], primary_key: str, fallback_key: str) -> Any:
        value = attack_data.get(primary_key)
        if value is None:
            value = attack_data.get(fallback_key)
        return value
    
    @staticmethod
    def _coerce_enum(value: Any) -> Any:
        return value.value if hasattr(value, "value") else value

    async def save_war(self, war_data: Dict[str, Any]) -> bool:
        """Upsert a war record — never overwrites an existing non-null column with NULL."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    attacker = war_data.get("attacker") or {}
                    defender = war_data.get("defender") or {}
                    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

                    fields = {
                        "date": war_data.get("date"),
                        "end_date": war_data.get("end_date"),
                        "reason": war_data.get("reason"),
                        "war_type": self._coerce_enum(war_data.get("war_type")),
                        "ground_control": war_data.get("ground_control"),
                        "air_superiority": war_data.get("air_superiority"),
                        "naval_blockade": war_data.get("naval_blockade"),
                        "winner_id": war_data.get("winner_id"),
                        "turns_left": war_data.get("turns_left"),
                        "att_id": war_data.get("att_id"),
                        "def_id": war_data.get("def_id"),
                        "att_alliance_id": war_data.get("att_alliance_id"),
                        "att_alliance_position": self._coerce_enum(war_data.get("att_alliance_position")),
                        "def_alliance_id": war_data.get("def_alliance_id"),
                        "def_alliance_position": self._coerce_enum(war_data.get("def_alliance_position")),
                        "att_nation_name": attacker.get("nation_name") or war_data.get("att_nation_name"),
                        "att_leader_name": attacker.get("leader_name") or war_data.get("att_leader_name"),
                        "def_nation_name": defender.get("nation_name") or war_data.get("def_nation_name"),
                        "def_leader_name": defender.get("leader_name") or war_data.get("def_leader_name"),
                        # Alliance names — pulled from nested attacker/defender.alliance.name if present
                        "att_alliance_name": (attacker.get("alliance") or {}).get("name") or war_data.get("att_alliance_name"),
                        "def_alliance_name": (defender.get("alliance") or {}).get("name") or war_data.get("def_alliance_name"),
                        "att_points": war_data.get("att_points"),
                        "def_points": war_data.get("def_points"),
                        "att_peace": war_data.get("att_peace"),
                        "def_peace": war_data.get("def_peace"),
                        "att_resistance": war_data.get("att_resistance"),
                        "def_resistance": war_data.get("def_resistance"),
                        "att_fortify": war_data.get("att_fortify"),
                        "def_fortify": war_data.get("def_fortify"),
                        "att_gas_used": war_data.get("att_gas_used"),
                        "def_gas_used": war_data.get("def_gas_used"),
                        "att_mun_used": war_data.get("att_mun_used"),
                        "def_mun_used": war_data.get("def_mun_used"),
                        "att_infra_destroyed": war_data.get("att_infra_destroyed"),
                        "def_infra_destroyed": war_data.get("def_infra_destroyed"),
                        "att_infra_destroyed_value": war_data.get("att_infra_destroyed_value"),
                        "def_infra_destroyed_value": war_data.get("def_infra_destroyed_value"),
                        "att_soldiers_lost": war_data.get("att_soldiers_lost"),
                        "def_soldiers_lost": war_data.get("def_soldiers_lost"),
                        "att_tanks_lost": war_data.get("att_tanks_lost"),
                        "def_tanks_lost": war_data.get("def_tanks_lost"),
                        "att_aircraft_lost": war_data.get("att_aircraft_lost"),
                        "def_aircraft_lost": war_data.get("def_aircraft_lost"),
                        "att_ships_lost": war_data.get("att_ships_lost"),
                        "def_ships_lost": war_data.get("def_ships_lost"),
                        "att_missiles_used": war_data.get("att_missiles_used"),
                        "def_missiles_used": war_data.get("def_missiles_used"),
                        "att_nukes_used": war_data.get("att_nukes_used"),
                        "def_nukes_used": war_data.get("def_nukes_used"),
                        "updated_at": now,
                    }

                    war_id = war_data.get("id")
                    cursor.execute("SELECT id FROM wars WHERE id = ?", (war_id,))
                    exists = cursor.fetchone()

                    if not exists:
                        fields["created_at"] = now
                        cols = ", ".join(["id"] + list(fields.keys()))
                        placeholders = ", ".join(["?"] * (1 + len(fields)))
                        cursor.execute(
                            f"INSERT INTO wars ({cols}) VALUES ({placeholders})",
                            [war_id] + list(fields.values()),
                        )
                    else:
                        # Only update columns where the incoming value is not None
                        update_fields = {k: v for k, v in fields.items() if v is not None}
                        if update_fields:
                            set_clause = ", ".join(f"{k} = ?" for k in update_fields)
                            cursor.execute(
                                f"UPDATE wars SET {set_clause} WHERE id = ?",
                                list(update_fields.values()) + [war_id],
                            )

                    conn.commit()
                    return True
            except Exception as e:
                logger.error(f"Error saving war {war_data.get('id')}: {e}", exc_info=True)
                return False
    
    async def save_war_attack(self, attack_data: Dict[str, Any]) -> bool:
        """Upsert a war attack — never overwrites an existing non-null column with NULL."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    improvements_destroyed = attack_data.get("improvements_destroyed")
                    if isinstance(improvements_destroyed, list):
                        improvements_destroyed = json.dumps(improvements_destroyed)

                    loot_info = attack_data.get("loot_info")
                    if isinstance(loot_info, dict):
                        loot_info = json.dumps(loot_info)

                    attacker_id = self._coerce_attack_id(attack_data, "attacker_id", "att_id")
                    defender_id = self._coerce_attack_id(attack_data, "defender_id", "def_id")
                    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

                    fields = {
                        "war_id": attack_data.get("war_id"),
                        "date": attack_data.get("date"),
                        "attacker_id": attacker_id,
                        "defender_id": defender_id,
                        "type": self._coerce_enum(attack_data.get("type")),
                        "attack_type": attack_data.get("attack_type"),
                        "victor": attack_data.get("victor"),
                        "success": attack_data.get("success"),
                        "attcas1": attack_data.get("attcas1"),
                        "defcas1": attack_data.get("defcas1"),
                        "attcas2": attack_data.get("attcas2"),
                        "defcas2": attack_data.get("defcas2"),
                        "city_infra_before": attack_data.get("city_infra_before"),
                        "infra_destroyed": attack_data.get("infra_destroyed"),
                        "infra_destroyed_value": attack_data.get("infra_destroyed_value"),
                        "improvements_destroyed": improvements_destroyed,
                        "money_stolen": attack_data.get("money_stolen"),
                        "money_destroyed": attack_data.get("money_destroyed"),
                        "military_salvage_aluminum": attack_data.get("military_salvage_aluminum"),
                        "military_salvage_steel": attack_data.get("military_salvage_steel"),
                        "money_looted": attack_data.get("money_looted"),
                        "coal_looted": attack_data.get("coal_looted"),
                        "oil_looted": attack_data.get("oil_looted"),
                        "uranium_looted": attack_data.get("uranium_looted"),
                        "iron_looted": attack_data.get("iron_looted"),
                        "bauxite_looted": attack_data.get("bauxite_looted"),
                        "lead_looted": attack_data.get("lead_looted"),
                        "gasoline_looted": attack_data.get("gasoline_looted"),
                        "munitions_looted": attack_data.get("munitions_looted"),
                        "steel_looted": attack_data.get("steel_looted"),
                        "aluminum_looted": attack_data.get("aluminum_looted"),
                        "food_looted": attack_data.get("food_looted"),
                        "loot_info": loot_info,
                        "resistance_war": attack_data.get("resistance_war"),
                        "resistance_lost": attack_data.get("resistance_lost"),
                        "city_id": attack_data.get("city_id"),
                        "infra_maps": attack_data.get("infra_maps"),
                        "note": attack_data.get("note"),
                        "att_missiles_lost": attack_data.get("att_missiles_lost"),
                        "def_missiles_lost": attack_data.get("def_missiles_lost"),
                        "att_nukes_lost": attack_data.get("att_nukes_lost"),
                        "def_nukes_lost": attack_data.get("def_nukes_lost"),
                    }

                    attack_id = attack_data.get("id")
                    cursor.execute("SELECT id FROM war_attacks WHERE id = ?", (attack_id,))
                    exists = cursor.fetchone()

                    if not exists:
                        fields["created_at"] = now
                        cols = ", ".join(["id"] + list(fields.keys()))
                        placeholders = ", ".join(["?"] * (1 + len(fields)))
                        cursor.execute(
                            f"INSERT INTO war_attacks ({cols}) VALUES ({placeholders})",
                            [attack_id] + list(fields.values()),
                        )
                    else:
                        # Only update columns where the incoming value is not None
                        update_fields = {k: v for k, v in fields.items() if v is not None}
                        if update_fields:
                            set_clause = ", ".join(f"{k} = ?" for k in update_fields)
                            cursor.execute(
                                f"UPDATE war_attacks SET {set_clause} WHERE id = ?",
                                list(update_fields.values()) + [attack_id],
                            )

                    conn.commit()
                    return True
            except Exception as e:
                logger.error(f"Error saving war attack {attack_data.get('id')}: {e}", exc_info=True)
                return False
    
    async def save_subscription_war_attack(self, attack_data: Dict[str, Any]) -> bool:
        """Save a subscription war attack directly to the main war_attacks table."""
        # Simply route to the main save_war_attack method to keep everything in one table
        return await self.save_war_attack(attack_data)
    
    async def get_war(self, war_id: int) -> Optional[Dict[str, Any]]:
        """Get a war record by ID."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT * FROM wars WHERE id = ?', (war_id,))
                    row = cursor.fetchone()
                    
                    if row:
                        columns = [desc[0] for desc in cursor.description]
                        return dict(zip(columns, row))
                    return None
            except Exception as e:
                logger.error(f"Error getting war {war_id}: {e}")
                return None
    
    async def get_wars_by_alliance(self, alliance_id: int, role: str = 'attacker') -> List[Dict[str, Any]]:
        """Get wars by alliance ID."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    if role == 'attacker':
                        cursor.execute('SELECT * FROM wars WHERE att_alliance_id = ? ORDER BY date DESC', (alliance_id,))
                    else:
                        cursor.execute('SELECT * FROM wars WHERE def_alliance_id = ? ORDER BY date DESC', (alliance_id,))
                    
                    rows = cursor.fetchall()
                    columns = [desc[0] for desc in cursor.description]
                    
                    return [dict(zip(columns, row)) for row in rows]
            except Exception as e:
                logger.error(f"Error getting wars for alliance {alliance_id}: {e}")
                return []

    async def get_wars_by_alliance_in_range(
        self,
        alliance_id: int,
        role: str = 'attacker',
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """Get wars by alliance ID constrained to an inclusive UTC date window."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    alliance_column = 'att_alliance_id' if role == 'attacker' else 'def_alliance_id'
                    query = f'SELECT * FROM wars WHERE {alliance_column} = ?'
                    params: List[Any] = [alliance_id]

                    if start_date:
                        query += " AND date(substr(date, 1, 10)) >= date(?)"
                        params.append(start_date.isoformat())

                    if end_date:
                        query += " AND date(substr(date, 1, 10)) <= date(?)"
                        params.append(end_date.isoformat())

                    query += ' ORDER BY date DESC'
                    cursor.execute(query, params)

                    rows = cursor.fetchall()
                    columns = [desc[0] for desc in cursor.description]
                    return [dict(zip(columns, row)) for row in rows]
            except Exception as e:
                logger.error(f"Error getting ranged wars for alliance {alliance_id}: {e}")
                return []

    async def get_all_wars_for_alliance_in_range(
        self,
        alliance_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch all wars (attacker OR defender) for an alliance in one query, deduped by id."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    query = 'SELECT * FROM wars WHERE (att_alliance_id = ? OR def_alliance_id = ?)'
                    params: List[Any] = [alliance_id, alliance_id]

                    if start_date:
                        query += " AND date(substr(date, 1, 10)) >= date(?)"
                        params.append(start_date.isoformat())

                    if end_date:
                        query += " AND date(substr(date, 1, 10)) <= date(?)"
                        params.append(end_date.isoformat())

                    query += ' ORDER BY date DESC'
                    cursor.execute(query, params)

                    rows = cursor.fetchall()
                    columns = [desc[0] for desc in cursor.description]
                    return [dict(zip(columns, row)) for row in rows]
            except Exception as e:
                logger.error(f"Error getting all ranged wars for alliance {alliance_id}: {e}")
                return []

    async def get_alliance_war_date_bounds(self, alliance_id: int) -> Optional[Dict[str, str]]:
        """Return the earliest and latest UTC war dates recorded for an alliance."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        '''
                        SELECT MIN(date(substr(date, 1, 10))), MAX(date(substr(date, 1, 10)))
                        FROM wars
                        WHERE att_alliance_id = ? OR def_alliance_id = ?
                        ''',
                        (alliance_id, alliance_id),
                    )
                    row = cursor.fetchone()
                    if not row or not row[0] or not row[1]:
                        return None
                    return {"min_date": row[0], "max_date": row[1]}
            except Exception as e:
                logger.error(f"Error getting war date bounds for alliance {alliance_id}: {e}")
                return None
    
    async def get_all_wars_date_bounds(self) -> Optional[Dict[str, str]]:
        """Return the earliest and latest UTC war dates across ALL wars in the DB."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        '''
                        SELECT MIN(date(substr(date, 1, 10))), MAX(date(substr(date, 1, 10)))
                        FROM wars
                        '''
                    )
                    row = cursor.fetchone()
                    if not row or not row[0] or not row[1]:
                        return None
                    return {"min_date": row[0], "max_date": row[1]}
            except Exception as e:
                logger.error(f"Error getting global war date bounds: {e}")
                return None

    async def get_all_wars_in_range(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch ALL wars in the DB (no alliance filter) within an optional date window."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    query = 'SELECT * FROM wars WHERE 1=1'
                    params: List[Any] = []

                    if start_date:
                        query += " AND date(substr(date, 1, 10)) >= date(?)"
                        params.append(start_date.isoformat())

                    if end_date:
                        query += " AND date(substr(date, 1, 10)) <= date(?)"
                        params.append(end_date.isoformat())

                    query += ' ORDER BY date DESC'
                    cursor.execute(query, params)

                    rows = cursor.fetchall()
                    columns = [desc[0] for desc in cursor.description]
                    return [dict(zip(columns, row)) for row in rows]
            except Exception as e:
                logger.error(f"Error getting all wars in range: {e}")
                return []

    async def get_wars_for_nations_in_range(
        self,
        nation_ids: List[int],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch all wars where any of the given nation IDs appear as attacker or defender,
        regardless of alliance tag. Deduped by war id."""
        if not nation_ids:
            return []
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    placeholders = ",".join("?" * len(nation_ids))
                    query = (
                        f"SELECT * FROM wars WHERE (att_id IN ({placeholders}) OR def_id IN ({placeholders}))"
                    )
                    params: List[Any] = list(nation_ids) + list(nation_ids)

                    if start_date:
                        query += " AND date(substr(date, 1, 10)) >= date(?)"
                        params.append(start_date.isoformat())

                    if end_date:
                        query += " AND date(substr(date, 1, 10)) <= date(?)"
                        params.append(end_date.isoformat())

                    query += " ORDER BY date DESC"
                    cursor.execute(query, params)

                    rows = cursor.fetchall()
                    columns = [desc[0] for desc in cursor.description]
                    return [dict(zip(columns, row)) for row in rows]
            except Exception as e:
                logger.error(f"Error getting wars for nations in range: {e}")
                return []

    async def get_wars_for_nations_date_bounds(
        self,
        nation_ids: List[int],
    ) -> Optional[Dict[str, str]]:
        """Return min/max war dates for a specific set of nation IDs."""
        if not nation_ids:
            return None
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    placeholders = ",".join("?" * len(nation_ids))
                    cursor.execute(
                        f"""
                        SELECT MIN(date(substr(date, 1, 10))), MAX(date(substr(date, 1, 10)))
                        FROM wars
                        WHERE att_id IN ({placeholders}) OR def_id IN ({placeholders})
                        """,
                        list(nation_ids) + list(nation_ids),
                    )
                    row = cursor.fetchone()
                    if not row or not row[0] or not row[1]:
                        return None
                    return {"min_date": row[0], "max_date": row[1]}
            except Exception as e:
                logger.error(f"Error getting war date bounds for nations: {e}")
                return None

    async def get_war_attacks(self, war_id: int) -> List[Dict[str, Any]]:
        """Get war attacks for a specific war."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT * FROM war_attacks WHERE war_id = ? ORDER BY date DESC', (war_id,))
                    
                    rows = cursor.fetchall()
                    columns = [desc[0] for desc in cursor.description]
                    
                    attacks = []
                    for row in rows:
                        attack = dict(zip(columns, row))
                        # Deserialize improvements_destroyed if it's JSON
                        if attack.get('improvements_destroyed'):
                            try:
                                attack['improvements_destroyed'] = json.loads(attack['improvements_destroyed'])
                            except (json.JSONDecodeError, TypeError):
                                pass
                        # Deserialize loot_info if it's JSON
                        if attack.get('loot_info'):
                            try:
                                attack['loot_info'] = json.loads(attack['loot_info'])
                            except (json.JSONDecodeError, TypeError):
                                pass
                        attacks.append(attack)
                    
                    return attacks
            except Exception as e:
                logger.error(f"Error getting war attacks for war {war_id}: {e}")
                return []
    
    async def get_unprocessed_subscription_attacks(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get unprocessed subscription war attacks."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT * FROM subscription_war_attacks 
                        WHERE processed = FALSE 
                        ORDER BY created_at ASC 
                        LIMIT ?
                    ''', (limit,))
                    
                    rows = cursor.fetchall()
                    columns = [desc[0] for desc in cursor.description]
                    
                    attacks = []
                    for row in rows:
                        attack = dict(zip(columns, row))
                        # Deserialize improvements_destroyed if it's JSON
                        if attack.get('improvements_destroyed'):
                            try:
                                attack['improvements_destroyed'] = json.loads(attack['improvements_destroyed'])
                            except (json.JSONDecodeError, TypeError):
                                pass
                        # Deserialize loot_info if it's JSON
                        if attack.get('loot_info'):
                            try:
                                attack['loot_info'] = json.loads(attack['loot_info'])
                            except (json.JSONDecodeError, TypeError):
                                pass
                        attacks.append(attack)
                    
                    return attacks
            except Exception as e:
                logger.error(f"Error getting unprocessed subscription attacks: {e}")
                return []

    async def get_watch_wars_with_incomplete_attacks(self, alliance_id: int, since: datetime) -> List[int]:
        """Return war ids for alliance wars that still have attack rows missing participant ids."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        '''
                        SELECT DISTINCT wa.war_id
                        FROM war_attacks wa
                        JOIN wars w ON w.id = wa.war_id
                        WHERE (w.att_alliance_id = ? OR w.def_alliance_id = ?)
                          AND datetime(replace(w.date, 'T', ' ')) >= datetime(?)
                          AND (wa.attacker_id IS NULL OR wa.defender_id IS NULL)
                        ORDER BY wa.war_id
                        ''',
                        (alliance_id, alliance_id, since.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')),
                    )
                    return [row[0] for row in cursor.fetchall()]
            except Exception as e:
                logger.error(f"Error getting incomplete attack wars for alliance {alliance_id}: {e}")
                return []
    
    async def mark_subscription_attack_processed(self, attack_id: int) -> bool:
        """Mark a subscription war attack as processed."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE subscription_war_attacks 
                        SET processed = TRUE 
                        WHERE id = ?
                    ''', (attack_id,))
                    
                    conn.commit()
                    return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Error marking subscription attack {attack_id} as processed: {e}")
                return False
    
    async def get_database_stats(self) -> Dict[str, int]:
        """Get database statistics."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute('SELECT COUNT(*) FROM wars')
                    war_count = cursor.fetchone()[0]
                    
                    cursor.execute('SELECT COUNT(*) FROM war_attacks')
                    attack_count = cursor.fetchone()[0]
                    
                    cursor.execute('SELECT COUNT(*) FROM subscription_war_attacks')
                    subscription_count = cursor.fetchone()[0]
                    
                    cursor.execute('SELECT COUNT(*) FROM subscription_war_attacks WHERE processed = FALSE')
                    unprocessed_count = cursor.fetchone()[0]
                    
                    return {
                        'wars': war_count,
                        'war_attacks': attack_count,
                        'subscription_attacks': subscription_count,
                        'unprocessed_attacks': unprocessed_count
                    }
            except Exception as e:
                logger.error(f"Error getting database stats: {e}")
                return {'wars': 0, 'war_attacks': 0, 'subscription_attacks': 0, 'unprocessed_attacks': 0}

    async def get_active_war_nation_ids(self) -> set:
        """Return the set of nation IDs that are currently in an active war (turns_left > 0).

        A single bulk query — call once before the revenue loop and use the
        returned set for O(1) per-nation lookups instead of relying on the
        potentially-stale offensive/defensive_wars_count columns.
        """
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT att_id, def_id
                        FROM wars
                        WHERE turns_left > 0
                          AND (att_id IS NOT NULL OR def_id IS NOT NULL)
                        """
                    )
                    active_ids: set = set()
                    for att_id, def_id in cursor.fetchall():
                        if att_id:
                            active_ids.add(int(att_id))
                        if def_id:
                            active_ids.add(int(def_id))
                    return active_ids
            except Exception as e:
                logger.error(f"Error fetching active war nation IDs: {e}")
                return set()

    async def get_active_war_counts(self) -> dict:
        """Return {nation_id: {'off': int, 'def': int}} for all nations in active wars (turns_left > 0)."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT att_id, def_id
                        FROM wars
                        WHERE turns_left > 0
                          AND (att_id IS NOT NULL OR def_id IS NOT NULL)
                        """
                    )
                    counts: dict = {}
                    for att_id, def_id in cursor.fetchall():
                        if att_id:
                            nid = int(att_id)
                            counts.setdefault(nid, {'off': 0, 'def': 0})['off'] += 1
                        if def_id:
                            nid = int(def_id)
                            counts.setdefault(nid, {'off': 0, 'def': 0})['def'] += 1
                    return counts
            except Exception as e:
                logger.error(f"Error fetching active war counts: {e}")
                return {}
        """Return the set of nation IDs that are currently in an active war (turns_left > 0).

        A single bulk query — call once before the revenue loop and use the
        returned set for O(1) per-nation lookups instead of relying on the
        potentially-stale offensive/defensive_wars_count columns.
        """
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT att_id, def_id
                        FROM wars
                        WHERE turns_left > 0
                          AND (att_id IS NOT NULL OR def_id IS NOT NULL)
                        """
                    )
                    active_ids: set = set()
                    for att_id, def_id in cursor.fetchall():
                        if att_id:
                            active_ids.add(int(att_id))
                        if def_id:
                            active_ids.add(int(def_id))
                    return active_ids
            except Exception as e:
                logger.error(f"Error fetching active war nation IDs: {e}")
                return set()

    async def delete_war(self, war_id: int) -> Dict[str, int]:
        """Delete a war and all its attacks by war ID. Returns counts of deleted rows."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('DELETE FROM war_attacks WHERE war_id = ?', (war_id,))
                    attacks_deleted = cursor.rowcount
                    cursor.execute('DELETE FROM subscription_war_attacks WHERE war_id = ?', (war_id,))
                    sub_deleted = cursor.rowcount
                    cursor.execute('DELETE FROM wars WHERE id = ?', (war_id,))
                    wars_deleted = cursor.rowcount
                    conn.commit()
                    return {
                        'wars_deleted': wars_deleted,
                        'attacks_deleted': attacks_deleted,
                        'subscription_attacks_deleted': sub_deleted,
                    }
            except Exception as e:
                logger.error(f"Error deleting war {war_id}: {e}", exc_info=True)
                return {'wars_deleted': 0, 'attacks_deleted': 0, 'subscription_attacks_deleted': 0}

    async def get_completed_war_ids_in_range(self, alliance_id: int, since: datetime) -> set:
        """Return IDs of wars that are already complete (end_date set) within the given window.

        Used by sync_missing to skip re-fetching wars that are fully settled.
        """
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        '''
                        SELECT id FROM wars
                        WHERE (att_alliance_id = ? OR def_alliance_id = ?)
                          AND end_date IS NOT NULL
                          AND end_date != ''
                          AND datetime(replace(date, 'T', ' ')) >= datetime(?)
                        ''',
                        (
                            alliance_id,
                            alliance_id,
                            since.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                        ),
                    )
                    return {row[0] for row in cursor.fetchall()}
            except Exception as e:
                logger.error(f"Error fetching completed war IDs: {e}", exc_info=True)
                return set()

    async def get_opponent_nation_names(self, alliance_id: int, current: str = "") -> List[str]:
        """Return distinct opponent nation names for autocomplete.

        For wars where *alliance_id* is the attacker, returns def_nation_name values.
        For wars where *alliance_id* is the defender, returns att_nation_name values.
        Optionally filters by *current* (case-insensitive prefix/substring match).
        """
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        '''
                        SELECT DISTINCT def_nation_name FROM wars
                        WHERE att_alliance_id = ? AND def_nation_name IS NOT NULL AND def_nation_name != ''
                        UNION
                        SELECT DISTINCT att_nation_name FROM wars
                        WHERE def_alliance_id = ? AND att_nation_name IS NOT NULL AND att_nation_name != ''
                        ORDER BY 1
                        ''',
                        (alliance_id, alliance_id),
                    )
                    names = [row[0] for row in cursor.fetchall() if row[0]]
                    if current:
                        low = current.lower()
                        names = [n for n in names if low in n.lower()]
                    return names
            except Exception as e:
                logger.error(f"Error getting opponent nation names: {e}")
                return []

    async def get_opponent_nation_names_for_nation(self, nation_id: int, current: str = "") -> List[str]:
        """Return distinct opponent nation names for a specific NW member nation (for autocomplete)."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        '''
                        SELECT DISTINCT def_nation_name FROM wars
                        WHERE att_id = ? AND def_nation_name IS NOT NULL AND def_nation_name != ''
                        UNION
                        SELECT DISTINCT att_nation_name FROM wars
                        WHERE def_id = ? AND att_nation_name IS NOT NULL AND att_nation_name != ''
                        ORDER BY 1
                        ''',
                        (nation_id, nation_id),
                    )
                    names = [row[0] for row in cursor.fetchall() if row[0]]
                    if current:
                        low = current.lower()
                        names = [n for n in names if low in n.lower()]
                    return names
            except Exception as e:
                logger.error(f"Error getting opponent nation names for nation {nation_id}: {e}")
                return []

    async def get_opponent_alliance_ids(self, alliance_id: int, current: str = "") -> List[Dict[str, int]]:
        """Return distinct opponent alliances (id + name) for autocomplete.
        Uses att_alliance_name / def_alliance_name columns added alongside the existing IDs.
        """
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        '''
                        SELECT def_alliance_id, def_alliance_name
                        FROM wars
                        WHERE att_alliance_id = ?
                          AND def_alliance_id IS NOT NULL AND def_alliance_id != 0
                        UNION
                        SELECT att_alliance_id, att_alliance_name
                        FROM wars
                        WHERE def_alliance_id = ?
                          AND att_alliance_id IS NOT NULL AND att_alliance_id != 0
                          AND att_alliance_id != ?
                        ORDER BY 2
                        ''',
                        (alliance_id, alliance_id, alliance_id),
                    )
                    rows = cursor.fetchall()
                    # Deduplicate by alliance_id, keeping the first non-null name
                    seen: dict[int, str] = {}
                    for aid, name in rows:
                        if aid not in seen or (not seen[aid] and name):
                            seen[aid] = name or ''
                    results = [{'alliance_id': aid, 'alliance_name': name} for aid, name in seen.items()]
                    if current:
                        low = current.lower()
                        results = [r for r in results if low in (r['alliance_name'] or '').lower() or low in str(r['alliance_id'])]
                    return results
            except Exception as e:
                logger.error(f"Error getting opponent alliance IDs: {e}")
                return []

    async def get_opponent_alliance_ids_for_nation(self, nation_id: int, current: str = "") -> List[Dict[str, int]]:
        """Return distinct opponent alliances (id + name) for a specific NW member nation."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        '''
                        SELECT def_alliance_id, def_alliance_name
                        FROM wars
                        WHERE att_id = ?
                          AND def_alliance_id IS NOT NULL AND def_alliance_id != 0
                        UNION
                        SELECT att_alliance_id, att_alliance_name
                        FROM wars
                        WHERE def_id = ?
                          AND att_alliance_id IS NOT NULL AND att_alliance_id != 0
                        ORDER BY 2
                        ''',
                        (nation_id, nation_id),
                    )
                    rows = cursor.fetchall()
                    seen: dict[int, str] = {}
                    for aid, name in rows:
                        if aid not in seen or (not seen[aid] and name):
                            seen[aid] = name or ''
                    results = [{'alliance_id': aid, 'alliance_name': name} for aid, name in seen.items()]
                    if current:
                        low = current.lower()
                        results = [r for r in results if low in (r['alliance_name'] or '').lower() or low in str(r['alliance_id'])]
                    return results
            except Exception as e:
                logger.error(f"Error getting opponent alliance IDs for nation {nation_id}: {e}")
                return []

    async def get_attacks_for_wars(self, war_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
        """Bulk-fetch all attacks for a list of war IDs in a single query.
        Returns a dict mapping war_id → list of attack dicts.
        """
        if not war_ids:
            return {}
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    placeholders = ','.join('?' * len(war_ids))
                    cursor.execute(
                        f'SELECT * FROM war_attacks WHERE war_id IN ({placeholders}) ORDER BY war_id, date',
                        war_ids,
                    )
                    rows = cursor.fetchall()
                    columns = [desc[0] for desc in cursor.description]
                    result: Dict[int, List[Dict[str, Any]]] = {wid: [] for wid in war_ids}
                    for row in rows:
                        attack = dict(zip(columns, row))
                        if attack.get('improvements_destroyed'):
                            try:
                                attack['improvements_destroyed'] = json.loads(attack['improvements_destroyed'])
                            except (json.JSONDecodeError, TypeError):
                                pass
                        if attack.get('loot_info'):
                            try:
                                attack['loot_info'] = json.loads(attack['loot_info'])
                            except (json.JSONDecodeError, TypeError):
                                pass
                        wid = attack.get('war_id')
                        if wid in result:
                            result[wid].append(attack)
                    return result
            except Exception as e:
                logger.error(f"Error bulk-fetching attacks for wars: {e}")
                return {}

"""
GlobalWarsDB — SQLite storage for ALL PnW wars (game-wide).

Schema is identical to IRSWarsDB. No alliance filter applied.
"""

import sqlite3
import json
import logging
from datetime import datetime, timezone, date
from typing import Dict, List, Any, Optional
import asyncio

logger = logging.getLogger(__name__)

LOOT_RESOURCE_COLUMNS = (
    "coal", "oil", "uranium", "iron", "bauxite", "lead",
    "gasoline", "munitions", "steel", "aluminum", "food",
)


class GlobalWarsDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self._init_database()

    def _init_database(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

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

                # Ensure columns exist on older DBs
                for col in ('att_infra_destroyed_value', 'def_infra_destroyed_value',
                            'att_alliance_name', 'def_alliance_name'):
                    self._ensure_column(cursor, 'wars', col, 'TEXT' if 'name' in col else 'REAL')
                for col in ('att_missiles_lost', 'def_missiles_lost', 'att_nukes_lost', 'def_nukes_lost'):
                    self._ensure_column(cursor, 'war_attacks', col, 'INTEGER')
                for col in ('money_looted', 'infra_destroyed_value', 'money_destroyed',
                            'military_salvage_aluminum', 'military_salvage_steel'):
                    self._ensure_column(cursor, 'war_attacks', col, 'REAL')
                for resource in LOOT_RESOURCE_COLUMNS:
                    self._ensure_column(cursor, 'war_attacks', f'{resource}_looted', 'REAL')

                cursor.execute('CREATE INDEX IF NOT EXISTS idx_gw_att_alliance ON wars(att_alliance_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_gw_def_alliance ON wars(def_alliance_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_gw_att_id       ON wars(att_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_gw_def_id       ON wars(def_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_gwa_war_id      ON war_attacks(war_id)')

                conn.commit()
                logger.info("GlobalWarsDB initialized successfully")
        except Exception as e:
            logger.error(f"GlobalWarsDB init error: {e}")
            raise

    @staticmethod
    def _ensure_column(cursor: sqlite3.Cursor, table: str, col: str, col_type: str):
        cursor.execute(f"PRAGMA table_info({table})")
        if col not in {r[1] for r in cursor.fetchall()}:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")

    @staticmethod
    def _coerce_enum(value: Any) -> Any:
        return value.value if hasattr(value, "value") else value

    @staticmethod
    def _coerce_attack_id(attack_data: Dict[str, Any], primary: str, fallback: str) -> Any:
        v = attack_data.get(primary)
        return v if v is not None else attack_data.get(fallback)

    async def save_war(self, war_data: Dict[str, Any]) -> bool:
        """Upsert a war record — never overwrites non-null with NULL."""
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
                    if not cursor.fetchone():
                        fields["created_at"] = now
                        cols = ", ".join(["id"] + list(fields.keys()))
                        ph   = ", ".join(["?"] * (1 + len(fields)))
                        cursor.execute(f"INSERT INTO wars ({cols}) VALUES ({ph})", [war_id] + list(fields.values()))
                    else:
                        upd = {k: v for k, v in fields.items() if v is not None}
                        if upd:
                            set_clause = ", ".join(f"{k} = ?" for k in upd)
                            cursor.execute(f"UPDATE wars SET {set_clause} WHERE id = ?",
                                           list(upd.values()) + [war_id])
                    conn.commit()
                    return True
            except Exception as e:
                logger.error(f"GlobalWarsDB.save_war({war_data.get('id')}): {e}", exc_info=True)
                return False

    async def save_war_attack(self, attack_data: Dict[str, Any]) -> bool:
        """Upsert a war attack — never overwrites non-null with NULL."""
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
                    if not cursor.fetchone():
                        fields["created_at"] = now
                        cols = ", ".join(["id"] + list(fields.keys()))
                        ph   = ", ".join(["?"] * (1 + len(fields)))
                        cursor.execute(f"INSERT INTO war_attacks ({cols}) VALUES ({ph})",
                                       [attack_id] + list(fields.values()))
                    else:
                        upd = {k: v for k, v in fields.items() if v is not None}
                        if upd:
                            set_clause = ", ".join(f"{k} = ?" for k in upd)
                            cursor.execute(f"UPDATE war_attacks SET {set_clause} WHERE id = ?",
                                           list(upd.values()) + [attack_id])
                    conn.commit()
                    return True
            except Exception as e:
                logger.error(f"GlobalWarsDB.save_war_attack({attack_data.get('id')}): {e}", exc_info=True)
                return False

    async def get_war(self, war_id: int) -> Optional[Dict[str, Any]]:
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT * FROM wars WHERE id = ?', (war_id,))
                    row = cursor.fetchone()
                    if row:
                        return dict(zip([d[0] for d in cursor.description], row))
                    return None
            except Exception as e:
                logger.error(f"get_war({war_id}): {e}")
                return None

    async def get_wars_by_alliance(self, alliance_id: int) -> List[Dict[str, Any]]:
        """Return all wars where alliance_id is attacker or defender."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        'SELECT * FROM wars WHERE att_alliance_id = ? OR def_alliance_id = ? ORDER BY date DESC',
                        (alliance_id, alliance_id)
                    )
                    rows = cursor.fetchall()
                    cols = [d[0] for d in cursor.description]
                    return [dict(zip(cols, r)) for r in rows]
            except Exception as e:
                logger.error(f"get_wars_by_alliance({alliance_id}): {e}")
                return []

    async def get_wars_by_alliance_in_range(
        self,
        alliance_id: int,
        role: str = 'either',
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    if role == 'attacker':
                        where = 'att_alliance_id = ?'
                        params: List[Any] = [alliance_id]
                    elif role == 'defender':
                        where = 'def_alliance_id = ?'
                        params = [alliance_id]
                    else:
                        where = '(att_alliance_id = ? OR def_alliance_id = ?)'
                        params = [alliance_id, alliance_id]

                    if start_date:
                        where += " AND date(substr(date, 1, 10)) >= date(?)"
                        params.append(start_date.isoformat())
                    if end_date:
                        where += " AND date(substr(date, 1, 10)) <= date(?)"
                        params.append(end_date.isoformat())

                    cursor.execute(f'SELECT * FROM wars WHERE {where} ORDER BY date DESC', params)
                    rows = cursor.fetchall()
                    cols = [d[0] for d in cursor.description]
                    return [dict(zip(cols, r)) for r in rows]
            except Exception as e:
                logger.error(f"get_wars_by_alliance_in_range({alliance_id}): {e}")
                return []

    async def get_war_attacks(self, war_id: int) -> List[Dict[str, Any]]:
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT * FROM war_attacks WHERE war_id = ? ORDER BY date', (war_id,))
                    rows = cursor.fetchall()
                    cols = [d[0] for d in cursor.description]
                    attacks = []
                    for row in rows:
                        a = dict(zip(cols, row))
                        for field in ('improvements_destroyed', 'loot_info'):
                            if a.get(field):
                                try:
                                    a[field] = json.loads(a[field])
                                except (json.JSONDecodeError, TypeError):
                                    pass
                        attacks.append(a)
                    return attacks
            except Exception as e:
                logger.error(f"get_war_attacks({war_id}): {e}")
                return []

    async def get_stats(self) -> Dict[str, int]:
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    c = conn.cursor()
                    wars    = c.execute("SELECT COUNT(*) FROM wars").fetchone()[0]
                    attacks = c.execute("SELECT COUNT(*) FROM war_attacks").fetchone()[0]
                    return {"wars": wars, "war_attacks": attacks}
            except Exception as e:
                logger.error(f"get_stats: {e}")
                return {"wars": 0, "war_attacks": 0}

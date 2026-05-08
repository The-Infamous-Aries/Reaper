"""
GlobalNationsDB — SQLite storage for ALL PnW nations (game-wide).

Schema is identical to IRSNationsDB with one addition:
  - alliance_name TEXT column on nations (populated from subscription payload)

Extra query methods:
  - get_distinct_alliances()        → [(alliance_id, alliance_name)] for autocomplete
  - get_nations_by_alliance(id)     → replaces query_instance.get_alliance_nations()
  - get_nation_by_name(name)        → lookup by nation_name
  - get_nation_by_id(nation_id)     → lookup by id
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


class GlobalNationsDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self._init_database()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _init_database(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()

                # ── WAL mode + performance pragmas ────────────────────────────
                # journal_mode=WAL is persisted in the DB header after first set.
                # synchronous=NORMAL is safe with WAL and much faster than FULL.
                # busy_timeout prevents immediate SQLITE_BUSY errors under load.
                # wal_autocheckpoint=1000 allows WAL to grow to ~4MB before auto-checkpoint.
                # We also run manual checkpoints every 5 minutes in the harvester loop.
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA busy_timeout=15000")
                conn.execute("PRAGMA wal_autocheckpoint=1000")

                c.execute("""
                    CREATE TABLE IF NOT EXISTS nations (
                        id                          INTEGER PRIMARY KEY,
                        nation_name                 TEXT,
                        leader_name                 TEXT,
                        continent                   TEXT,
                        color                       TEXT,
                        flag                        TEXT,
                        discord                     TEXT,
                        discord_id                  TEXT,
                        war_policy                  TEXT,
                        domestic_policy             TEXT,
                        social_policy               TEXT,
                        government_type             TEXT,
                        economic_policy             TEXT,
                        update_tz                   INTEGER,
                        vacation_mode_turns         INTEGER DEFAULT 0,
                        beige_turns                 INTEGER DEFAULT 0,
                        alliance_id                 INTEGER,
                        alliance_name               TEXT,
                        alliance_position           TEXT,
                        alliance_seniority          INTEGER,
                        tax_id                      INTEGER,
                        num_cities                  INTEGER DEFAULT 0,
                        score                       REAL DEFAULT 0,
                        population                  INTEGER DEFAULT 0,
                        gross_national_income       REAL DEFAULT 0,
                        gross_domestic_product      REAL DEFAULT 0,
                        espionage_available         INTEGER DEFAULT 0,
                        date                        TEXT,
                        last_active                 TEXT,
                        turns_since_last_city       INTEGER DEFAULT 0,
                        turns_since_last_project    INTEGER DEFAULT 0,
                        soldiers                    INTEGER DEFAULT 0,
                        tanks                       INTEGER DEFAULT 0,
                        aircraft                    INTEGER DEFAULT 0,
                        ships                       INTEGER DEFAULT 0,
                        missiles                    INTEGER DEFAULT 0,
                        nukes                       INTEGER DEFAULT 0,
                        spies                       INTEGER DEFAULT 0,
                        wars_won                    INTEGER DEFAULT 0,
                        wars_lost                   INTEGER DEFAULT 0,
                        offensive_wars_count        INTEGER DEFAULT 0,
                        defensive_wars_count        INTEGER DEFAULT 0,
                        iron_dome                   INTEGER DEFAULT 0,
                        vital_defense_system        INTEGER DEFAULT 0,
                        missile_launch_pad          INTEGER DEFAULT 0,
                        nuclear_research_facility   INTEGER DEFAULT 0,
                        nuclear_launch_facility     INTEGER DEFAULT 0,
                        propaganda_bureau           INTEGER DEFAULT 0,
                        military_research_center    INTEGER DEFAULT 0,
                        space_program               INTEGER DEFAULT 0,
                        spy_satellite               INTEGER DEFAULT 0,
                        surveillance_network        INTEGER DEFAULT 0,
                        guiding_satellite           INTEGER DEFAULT 0,
                        telecommunications_satellite INTEGER DEFAULT 0,
                        central_intelligence_agency INTEGER DEFAULT 0,
                        fallout_shelter             INTEGER DEFAULT 0,
                        military_doctrine           INTEGER DEFAULT 0,
                        military_salvage            INTEGER DEFAULT 0,
                        pirate_economy              INTEGER DEFAULT 0,
                        advanced_pirate_economy     INTEGER DEFAULT 0,
                        arms_stockpile              INTEGER DEFAULT 0,
                        bauxite_works               INTEGER DEFAULT 0,
                        iron_works                  INTEGER DEFAULT 0,
                        emergency_gasoline_reserve  INTEGER DEFAULT 0,
                        uranium_enrichment_program  INTEGER DEFAULT 0,
                        green_technologies          INTEGER DEFAULT 0,
                        recycling_initiative        INTEGER DEFAULT 0,
                        mass_irrigation             INTEGER DEFAULT 0,
                        arable_land_agency          INTEGER DEFAULT 0,
                        international_trade_center  INTEGER DEFAULT 0,
                        clinical_research_center    INTEGER DEFAULT 0,
                        specialized_police_training_program INTEGER DEFAULT 0,
                        bureau_of_domestic_affairs  INTEGER DEFAULT 0,
                        government_support_agency   INTEGER DEFAULT 0,
                        center_for_civil_engineering INTEGER DEFAULT 0,
                        advanced_engineering_corps  INTEGER DEFAULT 0,
                        activity_center             INTEGER DEFAULT 0,
                        research_and_development_center INTEGER DEFAULT 0,
                        moon_landing                INTEGER DEFAULT 0,
                        mars_landing                INTEGER DEFAULT 0,
                        snapshot_at                 TEXT,
                        updated_at                  TEXT
                    )
                """)

                c.execute("""
                    CREATE TABLE IF NOT EXISTS cities (
                        id              INTEGER PRIMARY KEY,
                        nation_id       INTEGER NOT NULL,
                        name            TEXT,
                        date            TEXT,
                        infrastructure  REAL DEFAULT 0,
                        land            REAL DEFAULT 0,
                        powered         INTEGER DEFAULT 0,
                        coal_power      INTEGER DEFAULT 0,
                        oil_power       INTEGER DEFAULT 0,
                        nuclear_power   INTEGER DEFAULT 0,
                        wind_power      INTEGER DEFAULT 0,
                        coal_mine       INTEGER DEFAULT 0,
                        oil_well        INTEGER DEFAULT 0,
                        uranium_mine    INTEGER DEFAULT 0,
                        lead_mine       INTEGER DEFAULT 0,
                        iron_mine       INTEGER DEFAULT 0,
                        bauxite_mine    INTEGER DEFAULT 0,
                        oil_refinery    INTEGER DEFAULT 0,
                        aluminum_refinery INTEGER DEFAULT 0,
                        steel_mill      INTEGER DEFAULT 0,
                        munitions_factory INTEGER DEFAULT 0,
                        factory         INTEGER DEFAULT 0,
                        farm            INTEGER DEFAULT 0,
                        police_station  INTEGER DEFAULT 0,
                        hospital        INTEGER DEFAULT 0,
                        recycling_center INTEGER DEFAULT 0,
                        subway          INTEGER DEFAULT 0,
                        supermarket     INTEGER DEFAULT 0,
                        bank            INTEGER DEFAULT 0,
                        shopping_mall   INTEGER DEFAULT 0,
                        stadium         INTEGER DEFAULT 0,
                        barracks        INTEGER DEFAULT 0,
                        hangar          INTEGER DEFAULT 0,
                        drydock         INTEGER DEFAULT 0,
                        updated_at      TEXT,
                        FOREIGN KEY (nation_id) REFERENCES nations(id)
                    )
                """)

                # Ensure alliance_name and military_research columns exist on older DBs
                self._ensure_column(c, "nations", "alliance_name", "TEXT")
                self._ensure_column(c, "nations", "alliance_flag", "TEXT")
                self._ensure_column(c, "nations", "military_research", "TEXT")

                c.execute("CREATE INDEX IF NOT EXISTS idx_gn_alliance_id   ON nations(alliance_id)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_gn_alliance_name ON nations(alliance_name)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_gn_nation_name   ON nations(nation_name)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_gn_last_active   ON nations(last_active)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_gc_nation_id     ON cities(nation_id)")

                conn.commit()
                logger.info("GlobalNationsDB initialized successfully")
        except Exception as e:
            logger.error(f"GlobalNationsDB init error: {e}", exc_info=True)
            raise

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _ensure_column(cursor: sqlite3.Cursor, table: str, col: str, col_type: str):
        cursor.execute(f"PRAGMA table_info({table})")
        if col not in {r[1] for r in cursor.fetchall()}:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")

    def checkpoint(self):
        """
        Run a TRUNCATE WAL checkpoint synchronously.
        Call this periodically (e.g. every 5 minutes) from the harvester loop
        to keep the WAL file small.  Safe to call while the asyncio lock is NOT held.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                result = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                # result = (busy, log_pages, checkpointed_pages)
                # busy=1 means a reader blocked the checkpoint — not an error
                if result and result[0] == 0:
                    logger.debug(f"GlobalNationsDB checkpoint: {result[1]} pages checkpointed")
                else:
                    logger.debug(f"GlobalNationsDB checkpoint (busy): {result}")
        except Exception as e:
            logger.warning(f"GlobalNationsDB.checkpoint: {e}")

    @staticmethod
    def _bool_opt(nation: Dict[str, Any], key: str):
        if key not in nation:
            return None
        v = nation[key]
        if isinstance(v, bool): return int(v)
        if isinstance(v, int):  return int(bool(v))
        if isinstance(v, str):  return 1 if v.lower() in ('true', '1', 'yes') else 0
        return 0

    @staticmethod
    def _norm_enum(val: Any) -> Optional[str]:
        """
        Normalise a pnwkit enum value to a plain lowercase string.

        pnwkit returns enum objects whose str() is 'ClassName.VALUE'
        (e.g. 'WarPolicy.MONEYBAGS').  We want just 'moneybags'.
        Plain strings that are already clean pass through unchanged.
        """
        if val is None:
            return None
        s = str(val)
        # Strip 'ClassName.' prefix if present (e.g. 'WarPolicy.MONEYBAGS' → 'MONEYBAGS')
        if "." in s:
            s = s.rsplit(".", 1)[-1]
        return s.lower() if s else None

    @staticmethod
    def _serialize_military_research(val: Any) -> Optional[str]:
        """Serialize military_research to a JSON string for storage.
        Accepts a dict (from API) or a string (already serialized) or None."""
        import json as _json
        if val is None:
            return None
        if isinstance(val, dict):
            return _json.dumps(val)
        if isinstance(val, str):
            # Validate it's parseable JSON, then store as-is
            try:
                _json.loads(val)
                return val
            except Exception:
                return None
        return None

    # ── Nation upsert ─────────────────────────────────────────────────────────

    async def save_nation(self, nation: Dict[str, Any]) -> bool:
        """Upsert a nation. Never overwrites non-null with NULL.
        Only INSERTs if payload has nation_name (full record).
        SQLite I/O runs in a thread-pool executor so the event loop is never blocked."""
        nation_id = nation.get("id")
        if not nation_id:
            return False

        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, self._save_nation_sync, nation)
        except Exception as e:
            logger.error(f"GlobalNationsDB.save_nation({nation_id}): {e}", exc_info=True)
            return False

    def _save_nation_sync(self, nation: Dict[str, Any]) -> bool:
        """Synchronous implementation of save_nation — runs in thread-pool executor."""
        nation_id = nation.get("id")
        if not nation_id:
            return False
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA busy_timeout=15000")
                c = conn.cursor()
                now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

                # Extract alliance_name and alliance_flag from nested alliance object if present
                alliance_obj = nation.get("alliance") or {}
                alliance_name = (
                    alliance_obj.get("name")
                    if isinstance(alliance_obj, dict)
                    else nation.get("alliance_name")
                ) or nation.get("alliance_name")
                alliance_flag = (
                    alliance_obj.get("flag")
                    if isinstance(alliance_obj, dict)
                    else nation.get("alliance_flag")
                ) or nation.get("alliance_flag")
                if alliance_name == '0':
                    alliance_name = None

                fields: Dict[str, Any] = {
                    "nation_name":          nation.get("nation_name"),
                    "leader_name":          nation.get("leader_name"),
                    "continent":            nation.get("continent"),
                    "color":                nation.get("color"),
                    "flag":                 nation.get("flag"),
                    "discord":              nation.get("discord"),
                    "discord_id":           nation.get("discord_id"),
                    "war_policy":           self._norm_enum(nation["war_policy"]) if "war_policy" in nation else None,
                    "domestic_policy":      self._norm_enum(nation["domestic_policy"]) if "domestic_policy" in nation else None,
                    "social_policy":        self._norm_enum(nation["social_policy"]) if "social_policy" in nation else None,
                    "government_type":      self._norm_enum(nation["government_type"]) if "government_type" in nation else None,
                    "economic_policy":      self._norm_enum(nation["economic_policy"]) if "economic_policy" in nation else None,
                    "update_tz":            nation.get("update_tz"),
                    "vacation_mode_turns":  nation.get("vacation_mode_turns"),
                    "beige_turns":          nation.get("beige_turns"),
                    "alliance_id":          nation.get("alliance_id"),
                    "alliance_name":        alliance_name,
                    "alliance_flag":        alliance_flag,
                    "alliance_position":    self._norm_enum(nation["alliance_position"]) if "alliance_position" in nation else None,
                    "alliance_seniority":   nation.get("alliance_seniority"),
                    "tax_id":               nation.get("tax_id"),
                    "num_cities":           nation.get("num_cities"),
                    "score":                nation.get("score"),
                    "population":           nation.get("population"),
                    "gross_national_income": nation.get("gross_national_income"),
                    "gross_domestic_product": nation.get("gross_domestic_product"),
                    "espionage_available":  self._bool_opt(nation, "espionage_available"),
                    "date":                 nation.get("date"),
                    "last_active":          nation.get("last_active"),
                    "turns_since_last_city":    nation.get("turns_since_last_city"),
                    "turns_since_last_project": nation.get("turns_since_last_project"),
                    # NOTE: wars_won, wars_lost, offensive_wars_count, defensive_wars_count
                    # are intentionally EXCLUDED from save_nation updates.
                    # These columns are managed exclusively by update_war_counts() which
                    # applies real-time increments/decrements from war/create and war/update
                    # subscription events.  Including them here would overwrite those
                    # real-time values with stale API snapshot values from nation/update
                    # events (which lag behind the actual war state by up to one turn).
                    # On INSERT (new nation) they are set to 0 via the default path below.
                    "iron_dome":                          self._bool_opt(nation, "iron_dome"),
                    "vital_defense_system":               self._bool_opt(nation, "vital_defense_system"),
                    "missile_launch_pad":                 self._bool_opt(nation, "missile_launch_pad"),
                    "nuclear_research_facility":          self._bool_opt(nation, "nuclear_research_facility"),
                    "nuclear_launch_facility":            self._bool_opt(nation, "nuclear_launch_facility"),
                    "propaganda_bureau":                  self._bool_opt(nation, "propaganda_bureau"),
                    "military_research_center":           self._bool_opt(nation, "military_research_center"),
                    "space_program":                      self._bool_opt(nation, "space_program"),
                    "spy_satellite":                      self._bool_opt(nation, "spy_satellite"),
                    "surveillance_network":               self._bool_opt(nation, "surveillance_network"),
                    "guiding_satellite":                  self._bool_opt(nation, "guiding_satellite"),
                    "telecommunications_satellite":       self._bool_opt(nation, "telecommunications_satellite"),
                    "central_intelligence_agency":        self._bool_opt(nation, "central_intelligence_agency"),
                    "fallout_shelter":                    self._bool_opt(nation, "fallout_shelter"),
                    "military_doctrine":                  self._bool_opt(nation, "military_doctrine"),
                    "military_salvage":                   self._bool_opt(nation, "military_salvage"),
                    "pirate_economy":                     self._bool_opt(nation, "pirate_economy"),
                    "advanced_pirate_economy":            self._bool_opt(nation, "advanced_pirate_economy"),
                    "arms_stockpile":                     self._bool_opt(nation, "arms_stockpile"),
                    "bauxite_works":                      self._bool_opt(nation, "bauxite_works"),
                    "iron_works":                         self._bool_opt(nation, "iron_works"),
                    "emergency_gasoline_reserve":         self._bool_opt(nation, "emergency_gasoline_reserve"),
                    "uranium_enrichment_program":         self._bool_opt(nation, "uranium_enrichment_program"),
                    "green_technologies":                 self._bool_opt(nation, "green_technologies"),
                    "recycling_initiative":               self._bool_opt(nation, "recycling_initiative"),
                    "mass_irrigation":                    self._bool_opt(nation, "mass_irrigation"),
                    "arable_land_agency":                 self._bool_opt(nation, "arable_land_agency"),
                    "international_trade_center":         self._bool_opt(nation, "international_trade_center"),
                    "clinical_research_center":           self._bool_opt(nation, "clinical_research_center"),
                    "specialized_police_training_program": self._bool_opt(nation, "specialized_police_training_program"),
                    "bureau_of_domestic_affairs":         self._bool_opt(nation, "bureau_of_domestic_affairs"),
                    "government_support_agency":          self._bool_opt(nation, "government_support_agency"),
                    "center_for_civil_engineering":       self._bool_opt(nation, "center_for_civil_engineering"),
                    "advanced_engineering_corps":         self._bool_opt(nation, "advanced_engineering_corps"),
                    "activity_center":                    self._bool_opt(nation, "activity_center"),
                    "research_and_development_center":    self._bool_opt(nation, "research_and_development_center"),
                    "moon_landing":                       self._bool_opt(nation, "moon_landing"),
                    "mars_landing":                       self._bool_opt(nation, "mars_landing"),
                    "military_research":                  self._serialize_military_research(nation.get("military_research")),
                    "snapshot_at": now if nation.get("nation_name") else nation.get("snapshot_at"),
                    "updated_at":  now,
                }

                # Holdings columns — included in INSERT (seed) but NEVER in UPDATE.
                # On INSERT: use the API value as the initial seed (best available baseline).
                # On UPDATE: HoldingsDB owns these; overwriting would corrupt tracked values.
                _HOLDINGS_SEED: Dict[str, Any] = {}
                for _hcol in ("money", "coal", "oil", "uranium", "iron", "bauxite", "lead",
                              "gasoline", "munitions", "steel", "aluminum", "food"):
                    _v = nation.get(_hcol)
                    _HOLDINGS_SEED[_hcol] = float(_v) if _v is not None else 0.0
                for _hcol in ("soldiers", "tanks", "aircraft", "ships",
                              "missiles", "nukes", "spies"):
                    _v = nation.get(_hcol)
                    _HOLDINGS_SEED[_hcol] = int(_v) if _v is not None else 0

                c.execute("SELECT id FROM nations WHERE id = ?", (nation_id,))
                exists = c.fetchone()
                if not exists:
                    if not nation.get("nation_name"):
                        return False
                    _TEXT_COLS = frozenset((
                        "nation_name", "leader_name", "continent", "color", "flag",
                        "discord", "discord_id", "war_policy", "domestic_policy",
                        "social_policy", "government_type", "economic_policy",
                        "alliance_name", "alliance_flag", "alliance_position",
                        "date", "last_active",
                        "military_research", "snapshot_at", "updated_at",
                    ))
                    # Merge holdings seed into insert — new nations get real API values
                    insert_fields = {**fields, **_HOLDINGS_SEED}
                    insert_vals = [
                        v if v is not None else (None if k in _TEXT_COLS else 0)
                        for k, v in insert_fields.items()
                    ]
                    snap_idx = list(insert_fields.keys()).index("snapshot_at")
                    if insert_vals[snap_idx] is None:
                        insert_vals[snap_idx] = now
                    cols = ", ".join(["id"] + list(insert_fields.keys()))
                    ph   = ", ".join(["?"] * (1 + len(insert_fields)))
                    c.execute(f"INSERT INTO nations ({cols}) VALUES ({ph})", [nation_id] + insert_vals)
                else:
                    # UPDATE: never touch holdings columns — HoldingsDB owns them
                    upd = {k: v for k, v in fields.items() if v is not None}
                    if upd:
                        set_clause = ", ".join(f"{k} = ?" for k in upd)
                        c.execute(f"UPDATE nations SET {set_clause} WHERE id = ?",
                                  list(upd.values()) + [nation_id])

                conn.commit()
                return True
        except Exception as e:
            logger.error(f"GlobalNationsDB._save_nation_sync({nation_id}): {e}", exc_info=True)
            return False

    # ── City upsert ───────────────────────────────────────────────────────────

    async def increment_num_cities(self, nation_id: int) -> None:
        """Increment num_cities by 1 for a nation. Called on city/create events
        so the count stays accurate without waiting for the next nation/update."""
        loop = asyncio.get_event_loop()
        def _work():
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("PRAGMA busy_timeout=15000")
                    conn.execute(
                        "UPDATE nations SET num_cities = MAX(0, COALESCE(num_cities, 0) + 1) WHERE id = ?",
                        (nation_id,),
                    )
                    conn.commit()
            except Exception as e:
                logger.warning(f"increment_num_cities(nation={nation_id}): {e}")
        await loop.run_in_executor(None, _work)

    async def update_war_counts(
        self,
        nation_id: int,
        off_delta: int = 0,
        def_delta: int = 0,
        won_delta: int = 0,
        lost_delta: int = 0,
    ) -> None:
        """
        Increment or decrement war stat columns for a nation.
        Uses MAX(0, ...) so counts never go negative.
        Only touches the columns that have a non-zero delta — no other data affected.
        """
        if off_delta == 0 and def_delta == 0 and won_delta == 0 and lost_delta == 0:
            return
        loop = asyncio.get_event_loop()
        def _work():
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("PRAGMA busy_timeout=15000")
                    parts = []
                    vals  = []
                    if off_delta != 0:
                        parts.append("offensive_wars_count = MAX(0, COALESCE(offensive_wars_count, 0) + ?)")
                        vals.append(off_delta)
                    if def_delta != 0:
                        parts.append("defensive_wars_count = MAX(0, COALESCE(defensive_wars_count, 0) + ?)")
                        vals.append(def_delta)
                    if won_delta != 0:
                        parts.append("wars_won = MAX(0, COALESCE(wars_won, 0) + ?)")
                        vals.append(won_delta)
                    if lost_delta != 0:
                        parts.append("wars_lost = MAX(0, COALESCE(wars_lost, 0) + ?)")
                        vals.append(lost_delta)
                    vals.append(nation_id)
                    conn.execute(
                        f"UPDATE nations SET {', '.join(parts)} WHERE id = ?",
                        vals,
                    )
                    conn.commit()
            except Exception as e:
                logger.warning(
                    f"update_war_counts(nation={nation_id}, off={off_delta}, def={def_delta}, "
                    f"won={won_delta}, lost={lost_delta}): {e}"
                )
        await loop.run_in_executor(None, _work)

    async def upsert_city(self, nation_id: int, city: Dict[str, Any]) -> bool:
        """Upsert a single city row. Only writes fields present in the event."""
        city_id = city.get("id")
        if not city_id:
            return False
        loop = asyncio.get_event_loop()
        def _work():
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("PRAGMA synchronous=NORMAL")
                    conn.execute("PRAGMA busy_timeout=15000")
                    c = conn.cursor()
                    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    _powered_raw = city.get("powered")
                    fields: Dict[str, Any] = {
                        "nation_id":         nation_id,
                        "name":              city.get("name"),
                        "date":              city.get("date"),
                        "infrastructure":    city.get("infrastructure"),
                        "land":              city.get("land"),
                        "powered":           int(bool(_powered_raw)) if _powered_raw is not None else None,
                        "coal_power":        city.get("coal_power"),
                        "oil_power":         city.get("oil_power"),
                        "nuclear_power":     city.get("nuclear_power"),
                        "wind_power":        city.get("wind_power"),
                        "coal_mine":         city.get("coal_mine"),
                        "oil_well":          city.get("oil_well"),
                        "uranium_mine":      city.get("uranium_mine"),
                        "lead_mine":         city.get("lead_mine"),
                        "iron_mine":         city.get("iron_mine"),
                        "bauxite_mine":      city.get("bauxite_mine"),
                        "oil_refinery":      city.get("oil_refinery"),
                        "aluminum_refinery": city.get("aluminum_refinery"),
                        "steel_mill":        city.get("steel_mill"),
                        "munitions_factory": city.get("munitions_factory"),
                        "factory":           city.get("factory"),
                        "farm":              city.get("farm"),
                        "police_station":    city.get("police_station"),
                        "hospital":          city.get("hospital"),
                        "recycling_center":  city.get("recycling_center"),
                        "subway":            city.get("subway"),
                        "supermarket":       city.get("supermarket"),
                        "bank":              city.get("bank"),
                        "shopping_mall":     city.get("shopping_mall"),
                        "stadium":           city.get("stadium"),
                        "barracks":          city.get("barracks"),
                        "hangar":            city.get("hangar"),
                        "drydock":           city.get("drydock"),
                        "updated_at":        now,
                    }
                    c.execute("SELECT id FROM cities WHERE id = ?", (city_id,))
                    if not c.fetchone():
                        insert_fields = {
                            k: (0 if v is None and k not in ("name", "date", "updated_at", "nation_id") else v)
                            for k, v in fields.items()
                        }
                        cols = ", ".join(["id"] + list(insert_fields.keys()))
                        ph   = ", ".join(["?"] * (1 + len(insert_fields)))
                        c.execute(f"INSERT INTO cities ({cols}) VALUES ({ph})",
                                  [city_id] + list(insert_fields.values()))
                    else:
                        upd = {k: v for k, v in fields.items() if v is not None}
                        if upd:
                            set_clause = ", ".join(f"{k} = ?" for k in upd)
                            c.execute(f"UPDATE cities SET {set_clause} WHERE id = ?",
                                      list(upd.values()) + [city_id])
                    conn.commit()
                    return True
            except Exception as e:
                logger.error(f"GlobalNationsDB.upsert_city({city_id}): {e}", exc_info=True)
                return False
        return await loop.run_in_executor(None, _work)

    async def save_cities(self, nation_id: int, cities: List[Dict[str, Any]]) -> int:
        """Bulk upsert cities for a nation. Returns count saved."""
        saved = 0
        for city in cities:
            if await self.upsert_city(nation_id, city):
                saved += 1
        return saved

    # ── Queries ───────────────────────────────────────────────────────────────

    async def get_nation(self, nation_id: int) -> Optional[Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        def _work():
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    conn.execute("PRAGMA busy_timeout=15000")
                    row = conn.execute("SELECT * FROM nations WHERE id = ?", (nation_id,)).fetchone()
                    return dict(row) if row else None
            except Exception as e:
                logger.error(f"get_nation({nation_id}): {e}")
                return None
        return await loop.run_in_executor(None, _work)

    async def get_nation_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        def _work():
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    conn.execute("PRAGMA busy_timeout=15000")
                    row = conn.execute(
                        "SELECT * FROM nations WHERE nation_name = ? COLLATE NOCASE LIMIT 1",
                        (name,)
                    ).fetchone()
                    return dict(row) if row else None
            except Exception as e:
                logger.error(f"get_nation_by_name({name}): {e}")
                return None
        return await loop.run_in_executor(None, _work)

    async def get_cities_for_nation(self, nation_id: int) -> List[Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        def _work():
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    conn.execute("PRAGMA busy_timeout=15000")
                    rows = conn.execute("SELECT * FROM cities WHERE nation_id = ?", (nation_id,)).fetchall()
                    return [dict(r) for r in rows]
            except Exception as e:
                logger.error(f"get_cities_for_nation({nation_id}): {e}")
                return []
        return await loop.run_in_executor(None, _work)

    async def get_all_cities_bulk(self) -> Dict[int, List[Dict[str, Any]]]:
        """Return all cities grouped by nation_id in a single query.

        Used by the revenue endpoint to avoid N individual city lookups.
        Returns: {nation_id: [city_dict, ...]}
        """
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute("SELECT * FROM cities").fetchall()
                    result: Dict[int, List[Dict[str, Any]]] = {}
                    for row in rows:
                        d = dict(row)
                        nid = int(d.get("nation_id") or 0)
                        if nid:
                            result.setdefault(nid, []).append(d)
                    return result
            except Exception as e:
                logger.error(f"get_all_cities_bulk: {e}")
                return {}

    async def get_cities_bulk_for_alliance(self, alliance_id: int) -> Dict[int, List[Dict[str, Any]]]:
        """Return cities grouped by nation_id, filtered to a single alliance.

        Much faster than get_all_cities_bulk when only one alliance is needed.
        Returns: {nation_id: [city_dict, ...]}
        """
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        """
                        SELECT c.* FROM cities c
                        INNER JOIN nations n ON n.id = c.nation_id
                        WHERE n.alliance_id = ?
                        """,
                        (alliance_id,),
                    ).fetchall()
                    result: Dict[int, List[Dict[str, Any]]] = {}
                    for row in rows:
                        d = dict(row)
                        nid = int(d.get("nation_id") or 0)
                        if nid:
                            result.setdefault(nid, []).append(d)
                    return result
            except Exception as e:
                logger.error(f"get_cities_bulk_for_alliance({alliance_id}): {e}")
                return {}

    async def get_nations_by_alliance(self, alliance_id: int) -> List[Dict[str, Any]]:
        """Return all nations for a given alliance_id. Used to replace API calls."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    # id < 900000 excludes test/synthetic nation IDs written by test scripts
                    rows = conn.execute(
                        "SELECT * FROM nations "
                        "WHERE alliance_id = ? AND nation_name IS NOT NULL AND nation_name != '' "
                        "AND id < 900000 "
                        "ORDER BY score DESC",
                        (alliance_id,)
                    ).fetchall()
                    return [dict(r) for r in rows]
            except Exception as e:
                logger.error(f"get_nations_by_alliance({alliance_id}): {e}")
                return []

    async def get_distinct_alliances(self, current: str = "") -> List[Dict[str, Any]]:
        """Return distinct (alliance_id, alliance_name) pairs for autocomplete dropdowns.
        Filters by current search string if provided."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        """
                        SELECT alliance_id, alliance_name, COUNT(*) as member_count
                        FROM nations
                        WHERE alliance_id IS NOT NULL AND alliance_id != 0
                          AND nation_name IS NOT NULL AND nation_name != ''
                        GROUP BY alliance_id
                        ORDER BY member_count DESC
                        """
                    ).fetchall()
                    results = [dict(r) for r in rows]
                    if current:
                        low = current.lower()
                        results = [
                            r for r in results
                            if low in (r.get("alliance_name") or "").lower()
                            or low in str(r.get("alliance_id", ""))
                        ]
                    return results
            except Exception as e:
                logger.error(f"get_distinct_alliances: {e}")
                return []

    async def search_nations(self, current: str, limit: int = 25) -> List[Dict[str, Any]]:
        """Search nations by name for autocomplete."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        "SELECT id, nation_name, leader_name, alliance_id, alliance_name, score "
                        "FROM nations "
                        "WHERE nation_name LIKE ? AND nation_name IS NOT NULL AND nation_name != '' "
                        "ORDER BY score DESC LIMIT ?",
                        (f"%{current}%", limit)
                    ).fetchall()
                    return [dict(r) for r in rows]
            except Exception as e:
                logger.error(f"search_nations({current}): {e}")
                return []

    async def get_all_nations(self) -> List[Dict[str, Any]]:
        """Return all nations in the database."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    c = conn.cursor()
                    c.execute("SELECT * FROM nations")
                    rows = c.fetchall()
                    return [dict(row) for row in rows]
            except Exception as e:
                logger.error(f"Error getting all nations: {e}")
                return []

    async def get_all_nation_ids(self) -> List[int]:
        """Return all nation IDs in the database (fast — no full row fetch)."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    rows = conn.execute(
                        "SELECT id FROM nations WHERE nation_name IS NOT NULL AND nation_name != ''"
                    ).fetchall()
                    return [int(r[0]) for r in rows]
            except Exception as e:
                logger.error(f"get_all_nation_ids: {e}")
                return []

    async def get_nation_names_by_ids(self, nation_ids: List[int]) -> Dict[int, str]:
        """Return a mapping of nation_id → nation_name for the given IDs (bulk lookup)."""
        if not nation_ids:
            return {}
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    placeholders = ",".join("?" * len(nation_ids))
                    rows = conn.execute(
                        f"SELECT id, nation_name FROM nations WHERE id IN ({placeholders}) AND nation_name IS NOT NULL AND nation_name != ''",
                        nation_ids,
                    ).fetchall()
                    return {int(r[0]): r[1] for r in rows}
            except Exception as e:
                logger.error(f"get_nation_names_by_ids: {e}")
                return {}

    async def get_nations_by_alliance_name(self, alliance_name: str) -> List[Dict[str, Any]]:
        """Return all nations for a given alliance_name (case-insensitive)."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        "SELECT * FROM nations "
                        "WHERE alliance_name LIKE ? AND nation_name IS NOT NULL AND nation_name != '' "
                        "AND id < 900000 "
                        "ORDER BY score DESC",
                        (f"%{alliance_name}%",)
                    ).fetchall()
                    return [dict(r) for r in rows]
            except Exception as e:
                logger.error(f"get_nations_by_alliance_name({alliance_name}): {e}")
                return []

    async def get_alliance_summary(self) -> List[Dict[str, Any]]:
        """Return summary statistics for all alliances with member counts and average scores."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        """
                        SELECT 
                            alliance_id, 
                            alliance_name, 
                            COUNT(*) as member_count,
                            AVG(score) as avg_score,
                            MAX(score) as max_score,
                            MIN(score) as min_score,
                            SUM(num_cities) as total_cities
                        FROM nations
                        WHERE alliance_id IS NOT NULL AND alliance_id != 0
                          AND nation_name IS NOT NULL AND nation_name != ''
                        GROUP BY alliance_id, alliance_name
                        ORDER BY member_count DESC, avg_score DESC
                        """
                    ).fetchall()
                    return [dict(r) for r in rows]
            except Exception as e:
                logger.error(f"get_alliance_summary: {e}")
                return []
    async def bulk_upsert_nations_and_cities(
        self,
        nations: List[Dict[str, Any]],
    ) -> tuple:
        """
        Upsert nations and their cities in a single transaction.
        Schema-driven: reads actual DB columns at runtime so it never
        breaks when columns are added via ALTER TABLE migrations.
        Returns (nations_saved, cities_saved).

        IMPORTANT: Uses INSERT OR IGNORE + UPDATE (not INSERT OR REPLACE) so
        that HoldingsDB-tracked money/resource/military values are never wiped
        by a full-snapshot re-insert. Holdings columns are excluded from the UPDATE.
        """
        import json as _json

        if not nations:
            return 0, 0

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # Columns owned by HoldingsDB — never overwrite with API snapshot values
        _HOLDINGS_COLS = frozenset((
            "money", "coal", "oil", "uranium", "iron", "bauxite", "lead",
            "gasoline", "munitions", "steel", "aluminum", "food",
            "soldiers", "tanks", "aircraft", "ships", "missiles", "nukes", "spies",
            # HoldingsDB tracking columns
            "confidence", "last_loot_date", "last_bankrec_date",
            "last_revenue_date", "last_event_date",
        ))

        # ── helpers ───────────────────────────────────────────────────────────
        def _b(nd, key):
            v = nd.get(key)
            if v is None:           return None
            if isinstance(v, bool): return int(v)
            if isinstance(v, int):  return int(bool(v))
            if isinstance(v, str):  return 1 if v.lower() in ("true","1","yes") else 0
            return 0

        def _e(nd, key):
            v = nd.get(key)
            if v is None: return None
            s = str(v)
            return s.rsplit(".", 1)[-1].lower() if "." in s else s.lower()

        def _mr(nd):
            v = nd.get("military_research")
            if isinstance(v, dict):
                return _json.dumps(v)
            if isinstance(v, str):
                try: _json.loads(v); return v
                except Exception: return None
            return None

        BOOL_PROJECTS = (
            "iron_dome","vital_defense_system","missile_launch_pad",
            "nuclear_research_facility","nuclear_launch_facility",
            "propaganda_bureau","military_research_center","space_program",
            "spy_satellite","surveillance_network","guiding_satellite",
            "telecommunications_satellite","central_intelligence_agency",
            "fallout_shelter","military_doctrine","military_salvage",
            "pirate_economy","advanced_pirate_economy","arms_stockpile",
            "bauxite_works","iron_works","emergency_gasoline_reserve",
            "uranium_enrichment_program","green_technologies","recycling_initiative",
            "mass_irrigation","arable_land_agency","international_trade_center",
            "clinical_research_center","specialized_police_training_program",
            "bureau_of_domestic_affairs","government_support_agency",
            "center_for_civil_engineering","advanced_engineering_corps",
            "activity_center","research_and_development_center",
            "moon_landing","mars_landing",
        )
        ENUM_FIELDS = (
            "war_policy","domestic_policy","social_policy",
            "government_type","economic_policy","alliance_position",
        )
        INT_FIELDS = (
            "update_tz","vacation_mode_turns","beige_turns","alliance_id",
            "alliance_seniority","tax_id","num_cities","population",
            "espionage_available","turns_since_last_city","turns_since_last_project",
            "soldiers","tanks","aircraft","ships","missiles","nukes","spies",
            "wars_won","wars_lost","offensive_wars_count","defensive_wars_count",
        )
        # War count columns are seeded on INSERT but never overwritten on UPDATE.
        # update_war_counts() owns these columns for real-time tracking; overwriting
        # them with stale API snapshot values would corrupt the live war counts.
        _WAR_COUNT_COLS = frozenset((
            "wars_won", "wars_lost", "offensive_wars_count", "defensive_wars_count",
        ))
        REAL_FIELDS = (
            "score","gross_national_income","gross_domestic_product",
            "money","coal","oil","uranium","iron","bauxite","lead",
            "gasoline","munitions","steel","aluminum","food",
        )

        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA synchronous=NORMAL")
                    conn.execute("PRAGMA wal_autocheckpoint=1000")
                    conn.execute("PRAGMA busy_timeout=15000")

                    db_city_cols = [
                        r[1] for r in conn.execute("PRAGMA table_info(cities)").fetchall()
                    ]

                    nations_saved = 0
                    city_rows: list = []

                    for nd in nations:
                        nid = nd.get("id")
                        if not nid or not nd.get("nation_name"):
                            continue

                        alliance_obj  = nd.get("alliance") or {}
                        alliance_name = (
                            alliance_obj.get("name") if isinstance(alliance_obj, dict) else None
                        ) or nd.get("alliance_name")
                        # PnW API returns '0' as alliance_name for nations with no alliance
                        # or when alliance data wasn't populated. Treat it as NULL so we
                        # never overwrite a real name with '0'.
                        if alliance_name == '0':
                            alliance_name = None

                        # Build full value dict
                        vd: dict = {
                            "id": int(nid),
                            "alliance_name": alliance_name,
                            "military_research": _mr(nd),
                            "snapshot_at": now,
                            "updated_at": now,
                        }
                        for k in ENUM_FIELDS:
                            vd[k] = _e(nd, k)
                        for k in BOOL_PROJECTS:
                            vd[k] = _b(nd, k)
                        for k in INT_FIELDS:
                            v = nd.get(k)
                            vd[k] = int(v) if v is not None else 0
                        for k in REAL_FIELDS:
                            v = nd.get(k)
                            vd[k] = float(v) if v is not None else 0.0
                        for k in ("nation_name","leader_name","continent","color","flag",
                                  "discord","discord_id","date","last_active"):
                            vd[k] = nd.get(k)

                        # ── INSERT OR IGNORE (new nations only) ───────────────
                        # For new nations, include money/resources/military from the
                        # API snapshot as the initial seed value. These are the best
                        # available starting point before subscription events arrive.
                        # On UPDATE (existing rows), holdings cols are still excluded
                        # so HoldingsDB-tracked values are never overwritten.
                        insert_cols = [k for k in vd if k != "id"]
                        ph = ",".join("?" * (1 + len(insert_cols)))
                        conn.execute(
                            f"INSERT OR IGNORE INTO nations (id,{','.join(insert_cols)}) VALUES ({ph})",
                            [int(nid)] + [vd[k] for k in insert_cols],
                        )

                        # ── UPDATE existing rows, skipping holdings + war-count columns ──
                        # War count columns (wars_won, wars_lost, offensive_wars_count,
                        # defensive_wars_count) are managed exclusively by update_war_counts()
                        # for real-time tracking. Overwriting them here with stale API
                        # snapshot values would corrupt live war counts.
                        update_cols = [
                            k for k in vd
                            if k != "id"
                            and k not in _HOLDINGS_COLS
                            and k not in _WAR_COUNT_COLS
                            and vd[k] is not None
                        ]
                        if update_cols:
                            set_clause = ", ".join(f"{k}=?" for k in update_cols)
                            conn.execute(
                                f"UPDATE nations SET {set_clause} WHERE id=?",
                                [vd[k] for k in update_cols] + [int(nid)],
                            )

                        nations_saved += 1

                        for city in (nd.get("cities") or []):
                            cid = city.get("id")
                            if not cid:
                                continue
                            powered_raw = city.get("powered")
                            cv: dict = {
                                "id": int(cid), "nation_id": int(nid),
                                "name": city.get("name"), "date": city.get("date"),
                                "infrastructure": city.get("infrastructure") or 0,
                                "land": city.get("land") or 0,
                                "powered": int(bool(powered_raw)) if powered_raw is not None else 0,
                                "updated_at": now,
                            }
                            for k in ("coal_power","oil_power","nuclear_power","wind_power",
                                      "coal_mine","oil_well","uranium_mine","lead_mine",
                                      "iron_mine","bauxite_mine","oil_refinery",
                                      "aluminum_refinery","steel_mill","munitions_factory",
                                      "factory","farm","police_station","hospital",
                                      "recycling_center","subway","supermarket","bank",
                                      "shopping_mall","stadium","barracks","hangar","drydock"):
                                cv[k] = city.get(k) or 0
                            city_rows.append(tuple(cv.get(c) for c in db_city_cols))

                    if city_rows:
                        ph_c   = ",".join("?" * len(db_city_cols))
                        cols_c = ",".join(db_city_cols)
                        # Cities don't have holdings data — INSERT OR REPLACE is safe
                        conn.executemany(
                            f"INSERT OR REPLACE INTO cities ({cols_c}) VALUES ({ph_c})",
                            city_rows,
                        )

                    conn.commit()
                    return nations_saved, len(city_rows)

            except Exception as e:
                logger.error(f"bulk_upsert_nations_and_cities: {e}", exc_info=True)
                return 0, 0

    async def get_stats(self) -> Dict[str, int]:
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    c = conn.cursor()
                    nations  = c.execute("SELECT COUNT(*) FROM nations WHERE nation_name IS NOT NULL AND nation_name != ''").fetchone()[0]
                    cities   = c.execute("SELECT COUNT(*) FROM cities").fetchone()[0]
                    alliances = c.execute("SELECT COUNT(DISTINCT alliance_id) FROM nations WHERE alliance_id IS NOT NULL AND alliance_id != 0").fetchone()[0]
                    return {"nations": nations, "cities": cities, "alliances": alliances}
            except Exception as e:
                logger.error(f"get_stats: {e}")
                return {"nations": 0, "cities": 0, "alliances": 0}

    # ── NW-manager compatibility methods ─────────────────────────────────────
    # Called by irs_nations_manager.sync_nations — safe no-ops or simple queries
    # now that everything lives in one DB.

    async def purge_skeleton_rows(self) -> int:
        """Remove rows that have no nation_name (skeleton rows from partial events)."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cur = conn.execute(
                        "DELETE FROM nations WHERE nation_name IS NULL OR nation_name = ''"
                    )
                    conn.commit()
                    removed = cur.rowcount
                    if removed:
                        logger.info(f"purge_skeleton_rows: removed {removed} skeleton rows")
                    return removed
            except Exception as e:
                logger.error(f"purge_skeleton_rows: {e}")
                return 0

    async def remove_departed_nations(self, current_ids: set) -> int:
        """
        Remove NW-member rows whose nation ID is no longer in current_ids.
        Only removes rows that have alliance_id == NW alliance — non-NW nations
        are never touched (they belong in GlobalNations.db regardless).
        """
        from Systems.Functions.db_paths import NW_ALLIANCE_ID as _NW_AID
        if not current_ids:
            return 0
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    placeholders = ",".join("?" * len(current_ids))
                    cur = conn.execute(
                        f"DELETE FROM nations WHERE alliance_id = ? AND id NOT IN ({placeholders})",
                        [_NW_AID] + list(current_ids),
                    )
                    conn.commit()
                    removed = cur.rowcount
                    if removed:
                        logger.info(f"remove_departed_nations: removed {removed} departed NW nations")
                    return removed
            except Exception as e:
                logger.error(f"remove_departed_nations: {e}")
                return 0

    async def remove_single_nation(self, nation_id: int) -> bool:
        """
        Called when a nation leaves NW (nation/update subscription).
        In the single-DB model we do NOT delete the nation — it still exists
        in the game and belongs in GlobalNations.db. We just clear its
        alliance_id so it's no longer counted as an NW member.
        The next nation/update event will set the correct new alliance_id.
        """
        # No-op: the nation stays in GlobalNations.db with its updated alliance_id.
        # The subscription already updates alliance_id via _save_nation.
        logger.debug(f"remove_single_nation({nation_id}): no-op in single-DB mode")
        return True

    async def save_tax_brackets(self, alliance_id: int, tax_brackets: list) -> int:
        """Stub — tax bracket storage not implemented in GlobalNationsDB."""
        return 0

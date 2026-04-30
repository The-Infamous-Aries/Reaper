"""
IRSNationsDB — SQLite storage for Nights Watch alliance member snapshots.

Schema mirrors the nation fields fetched by V3GraphQuery._nation_fields() so
every column maps 1-to-1 to a PnW API field.  The table is upserted on every
sync/subscription event so it always reflects the latest known state.
"""

import sqlite3
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
import asyncio

logger = logging.getLogger(__name__)

ALLIANCE_ID = 14225


class IRSNationsDB:
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

                # ── nations ───────────────────────────────────────────────────
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
                        -- Military
                        soldiers                    INTEGER DEFAULT 0,
                        tanks                       INTEGER DEFAULT 0,
                        aircraft                    INTEGER DEFAULT 0,
                        ships                       INTEGER DEFAULT 0,
                        missiles                    INTEGER DEFAULT 0,
                        nukes                       INTEGER DEFAULT 0,
                        spies                       INTEGER DEFAULT 0,
                        -- Resources
                        money                       REAL DEFAULT 0,
                        coal                        REAL DEFAULT 0,
                        oil                         REAL DEFAULT 0,
                        uranium                     REAL DEFAULT 0,
                        iron                        REAL DEFAULT 0,
                        bauxite                     REAL DEFAULT 0,
                        lead                        REAL DEFAULT 0,
                        gasoline                    REAL DEFAULT 0,
                        munitions                   REAL DEFAULT 0,
                        steel                       REAL DEFAULT 0,
                        aluminum                    REAL DEFAULT 0,
                        food                        REAL DEFAULT 0,
                        -- War stats
                        wars_won                    INTEGER DEFAULT 0,
                        wars_lost                   INTEGER DEFAULT 0,
                        offensive_wars_count        INTEGER DEFAULT 0,
                        defensive_wars_count        INTEGER DEFAULT 0,
                        -- Projects (boolean flags)
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
                        -- Military research levels (JSON: {ground_capacity, air_capacity, naval_capacity, ground_cost, air_cost, naval_cost})
                        military_research           TEXT DEFAULT NULL,
                        -- Snapshot metadata
                        snapshot_at                 TEXT,
                        updated_at                  TEXT
                    )
                """)

                # ── cities ────────────────────────────────────────────────────
                c.execute("""
                    CREATE TABLE IF NOT EXISTS cities (
                        id              INTEGER PRIMARY KEY,
                        nation_id       INTEGER NOT NULL,
                        name            TEXT,
                        date            TEXT,
                        infrastructure  REAL DEFAULT 0,
                        land            REAL DEFAULT 0,
                        powered         INTEGER DEFAULT 0,
                        -- Power
                        coal_power      INTEGER DEFAULT 0,
                        oil_power       INTEGER DEFAULT 0,
                        nuclear_power   INTEGER DEFAULT 0,
                        wind_power      INTEGER DEFAULT 0,
                        -- Resources
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
                        -- Civil
                        police_station  INTEGER DEFAULT 0,
                        hospital        INTEGER DEFAULT 0,
                        recycling_center INTEGER DEFAULT 0,
                        subway          INTEGER DEFAULT 0,
                        -- Commerce
                        supermarket     INTEGER DEFAULT 0,
                        bank            INTEGER DEFAULT 0,
                        shopping_mall   INTEGER DEFAULT 0,
                        stadium         INTEGER DEFAULT 0,
                        -- Military
                        barracks        INTEGER DEFAULT 0,
                        hangar          INTEGER DEFAULT 0,
                        drydock         INTEGER DEFAULT 0,
                        updated_at      TEXT,
                        FOREIGN KEY (nation_id) REFERENCES nations(id)
                    )
                """)

                # ── tax_brackets ──────────────────────────────────────────────
                c.execute("""
                    CREATE TABLE IF NOT EXISTS tax_brackets (
                        id              INTEGER PRIMARY KEY,
                        alliance_id     INTEGER NOT NULL,
                        name            TEXT,
                        tax_rate        REAL DEFAULT 0,
                        resource_tax_rate REAL DEFAULT 0,
                        updated_at      TEXT
                    )
                """)

                # ── indexes ───────────────────────────────────────────────────
                c.execute("CREATE INDEX IF NOT EXISTS idx_nations_alliance_id  ON nations(alliance_id)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_nations_last_active   ON nations(last_active)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_cities_nation_id      ON cities(nation_id)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_tax_brackets_alliance ON tax_brackets(alliance_id)")

                # ── migrations for existing DBs ───────────────────────────────
                self._ensure_column(c, "nations", "military_research", "TEXT")

                conn.commit()
                logger.info("IRSNationsDB initialized successfully")
        except Exception as e:
            logger.error(f"IRSNationsDB init error: {e}", exc_info=True)
            raise

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _bool(v: Any) -> int:
        if isinstance(v, bool): return int(v)
        if isinstance(v, int):  return int(bool(v))
        if isinstance(v, str):  return 1 if v.lower() in ('true', '1', 'yes') else 0
        return 0

    @staticmethod
    def _bool_opt(nation: Dict[str, Any], key: str):
        """Return int(bool) if key is present in the dict, else None (skip on UPDATE)."""
        if key not in nation:
            return None
        v = nation[key]
        if isinstance(v, bool): return int(v)
        if isinstance(v, int):  return int(bool(v))
        if isinstance(v, str):  return 1 if v.lower() in ('true', '1', 'yes') else 0
        return 0

    @staticmethod
    def _ensure_column(cursor: sqlite3.Cursor, table: str, col: str, col_type: str):
        cursor.execute(f"PRAGMA table_info({table})")
        if col not in {r[1] for r in cursor.fetchall()}:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")

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
        if "." in s:
            s = s.rsplit(".", 1)[-1]
        return s.lower() if s else None

    # ── Nation upsert ─────────────────────────────────────────────────────────

    async def save_nation(self, nation: Dict[str, Any]) -> bool:
        """Upsert a nation record. Never overwrites a non-null column with NULL.
        Only INSERTs a new row if the payload contains nation_name (full record).
        Patch-only payloads (e.g. from account/update) only UPDATE existing rows."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    c = conn.cursor()
                    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    nation_id = nation.get("id")
                    if not nation_id:
                        return False

                    b = self._bool  # kept for any future use
                    # Use None as default so missing fields are excluded from UPDATE
                    # (the upd filter below skips None values, preserving existing DB data)
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
                        "alliance_position":    self._norm_enum(nation["alliance_position"]) if "alliance_position" in nation else None,
                        "alliance_seniority":   nation.get("alliance_seniority"),
                        "tax_id":               nation.get("tax_id"),
                        "num_cities":           nation.get("num_cities"),
                        "score":                nation.get("score"),
                        "population":           nation.get("population"),
                        "gross_national_income": nation.get("gross_national_income"),
                        "gross_domestic_product": nation.get("gross_domestic_product"),
                        "espionage_available":  nation.get("espionage_available"),
                        "date":                 nation.get("date"),
                        "last_active":          nation.get("last_active"),
                        "turns_since_last_city":    nation.get("turns_since_last_city"),
                        "turns_since_last_project": nation.get("turns_since_last_project"),
                        # Military
                        "soldiers":  nation.get("soldiers"),
                        "tanks":     nation.get("tanks"),
                        "aircraft":  nation.get("aircraft"),
                        "ships":     nation.get("ships"),
                        "missiles":  nation.get("missiles"),
                        "nukes":     nation.get("nukes"),
                        "spies":     nation.get("spies"),
                        # Resources
                        "money":     nation.get("money"),
                        "coal":      nation.get("coal"),
                        "oil":       nation.get("oil"),
                        "uranium":   nation.get("uranium"),
                        "iron":      nation.get("iron"),
                        "bauxite":   nation.get("bauxite"),
                        "lead":      nation.get("lead"),
                        "gasoline":  nation.get("gasoline"),
                        "munitions": nation.get("munitions"),
                        "steel":     nation.get("steel"),
                        "aluminum":  nation.get("aluminum"),
                        "food":      nation.get("food"),
                        # War stats
                        "wars_won":               nation.get("wars_won"),
                        "wars_lost":              nation.get("wars_lost"),
                        "offensive_wars_count":   nation.get("offensive_wars_count"),
                        "defensive_wars_count":   nation.get("defensive_wars_count"),
                        # Projects
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
                        "military_research":                  json.dumps(nation["military_research"]) if isinstance(nation.get("military_research"), dict) else None,
                        "snapshot_at": nation.get("snapshot_at", now),
                        "updated_at":  now,
                    }

                    c.execute("SELECT id FROM nations WHERE id = ?", (nation_id,))
                    exists = c.fetchone()
                    if not exists:
                        # Only INSERT if this is a full record (has nation_name).
                        # Patch payloads from account/update only have id + last_active
                        # etc. — don't create skeleton rows for those.
                        if not nation.get("nation_name"):
                            return False
                        # For INSERT, replace None with 0 for numeric fields so DB defaults are sane
                        insert_vals = [v if v is not None else 0 for v in fields.values()]
                        cols = ", ".join(["id"] + list(fields.keys()))
                        ph   = ", ".join(["?"] * (1 + len(fields)))
                        c.execute(f"INSERT INTO nations ({cols}) VALUES ({ph})",
                                  [nation_id] + insert_vals)
                    else:
                        upd = {k: v for k, v in fields.items() if v is not None}
                        if upd:
                            set_clause = ", ".join(f"{k} = ?" for k in upd)
                            c.execute(f"UPDATE nations SET {set_clause} WHERE id = ?",
                                      list(upd.values()) + [nation_id])

                    conn.commit()
                    return True
            except Exception as e:
                logger.error(f"save_nation({nation.get('id')}): {e}", exc_info=True)
                return False

    # ── City upsert ───────────────────────────────────────────────────────────

    async def save_cities(self, nation_id: int, cities: List[Dict[str, Any]]) -> int:
        """Upsert all cities for a nation. Returns count saved."""
        if not cities:
            return 0
        saved = 0
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    c = conn.cursor()
                    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    for city in cities:
                        city_id = city.get("id")
                        if not city_id:
                            continue

                        # Use None as sentinel for fields not present in the event.
                        # This ensures UPDATE only touches fields that were actually
                        # provided — partial subscription events (e.g. land purchase)
                        # won't zero-out improvements that weren't included.
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
                            # INSERT: replace None with 0 for numeric columns so the
                            # new row has sensible defaults rather than NULL.
                            insert_fields = {
                                k: (0 if v is None and k not in ("name", "date", "updated_at", "nation_id") else v)
                                for k, v in fields.items()
                            }
                            cols = ", ".join(["id"] + list(insert_fields.keys()))
                            ph   = ", ".join(["?"] * (1 + len(insert_fields)))
                            c.execute(f"INSERT INTO cities ({cols}) VALUES ({ph})",
                                      [city_id] + list(insert_fields.values()))
                        else:
                            # UPDATE: only set fields that were present in the event
                            # (non-None). This prevents partial events from wiping
                            # out existing improvement/infra/land data.
                            upd = {k: v for k, v in fields.items() if v is not None}
                            if upd:
                                set_clause = ", ".join(f"{k} = ?" for k in upd)
                                c.execute(f"UPDATE cities SET {set_clause} WHERE id = ?",
                                          list(upd.values()) + [city_id])
                        saved += 1
                    conn.commit()
            except Exception as e:
                logger.error(f"save_cities(nation={nation_id}): {e}", exc_info=True)
        return saved

    # ── Single-city upsert (used by subscriptions) ────────────────────────────

    async def upsert_city(self, nation_id: int, city: Dict[str, Any]) -> bool:
        """
        Upsert exactly ONE city row from a subscription event.
        Only the fields present in `city` are written — every other city for
        this nation is completely untouched.  This is the correct handler for
        city/update and city/create subscription events.
        """
        city_id = city.get("id")
        if not city_id:
            return False

        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
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
                        # Brand-new city — INSERT with 0 defaults for missing numerics
                        insert_fields = {
                            k: (0 if v is None and k not in ("name", "date", "updated_at", "nation_id") else v)
                            for k, v in fields.items()
                        }
                        cols = ", ".join(["id"] + list(insert_fields.keys()))
                        ph   = ", ".join(["?"] * (1 + len(insert_fields)))
                        c.execute(f"INSERT INTO cities ({cols}) VALUES ({ph})",
                                  [city_id] + list(insert_fields.values()))
                    else:
                        # Existing city — only update fields that were in the event
                        upd = {k: v for k, v in fields.items() if v is not None}
                        if upd:
                            set_clause = ", ".join(f"{k} = ?" for k in upd)
                            c.execute(f"UPDATE cities SET {set_clause} WHERE id = ?",
                                      list(upd.values()) + [city_id])

                    conn.commit()
                    return True
            except Exception as e:
                logger.error(f"upsert_city(city={city_id}, nation={nation_id}): {e}", exc_info=True)
                return False

    # ── Tax brackets ──────────────────────────────────────────────────────────

    async def save_tax_brackets(self, alliance_id: int, brackets: List[Dict[str, Any]]) -> int:
        """Upsert all tax brackets for an alliance. Returns count saved."""
        if not brackets:
            return 0
        saved = 0
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    c = conn.cursor()
                    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    for bracket in brackets:
                        bracket_id = bracket.get("id")
                        if not bracket_id:
                            continue
                        fields = {
                            "alliance_id":        alliance_id,
                            "name":               bracket.get("name"),
                            "tax_rate":           float(bracket.get("tax_rate", 0)),
                            "resource_tax_rate":  float(bracket.get("resource_tax_rate", bracket.get("tax_rate", 0))),
                            "updated_at":         now,
                        }
                        c.execute("SELECT id FROM tax_brackets WHERE id = ?", (bracket_id,))
                        if not c.fetchone():
                            cols = ", ".join(["id"] + list(fields.keys()))
                            ph   = ", ".join(["?"] * (1 + len(fields)))
                            c.execute(f"INSERT INTO tax_brackets ({cols}) VALUES ({ph})",
                                      [bracket_id] + list(fields.values()))
                        else:
                            set_clause = ", ".join(f"{k} = ?" for k in fields)
                            c.execute(f"UPDATE tax_brackets SET {set_clause} WHERE id = ?",
                                      list(fields.values()) + [bracket_id])
                        saved += 1
                    conn.commit()
            except Exception as e:
                logger.error(f"save_tax_brackets(alliance={alliance_id}): {e}", exc_info=True)
        return saved

    async def get_tax_brackets(self, alliance_id: int) -> List[Dict[str, Any]]:
        """Return all tax brackets for an alliance."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        "SELECT * FROM tax_brackets WHERE alliance_id = ? ORDER BY id",
                        (alliance_id,)
                    ).fetchall()
                    return [dict(r) for r in rows]
            except Exception as e:
                logger.error(f"get_tax_brackets({alliance_id}): {e}")
                return []

    async def get_tax_bracket_for_nation(self, alliance_id: int, tax_id: Optional[int]) -> Optional[Dict[str, Any]]:
        """Return the specific tax bracket a nation is assigned to, or the first bracket as fallback."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    if tax_id is not None:
                        row = conn.execute(
                            "SELECT * FROM tax_brackets WHERE alliance_id = ? AND id = ?",
                            (alliance_id, tax_id)
                        ).fetchone()
                        if row:
                            return dict(row)
                    # Fallback: first bracket
                    row = conn.execute(
                        "SELECT * FROM tax_brackets WHERE alliance_id = ? ORDER BY id LIMIT 1",
                        (alliance_id,)
                    ).fetchone()
                    return dict(row) if row else None
            except Exception as e:
                logger.error(f"get_tax_bracket_for_nation({alliance_id}, {tax_id}): {e}")
                return None

    # ── Queries ───────────────────────────────────────────────────────────────

    @staticmethod
    def _deserialize_nation(row: dict) -> dict:
        """Post-process a raw DB row: deserialize JSON fields."""
        mr = row.get("military_research")
        if isinstance(mr, str):
            try:
                row["military_research"] = json.loads(mr)
            except (json.JSONDecodeError, TypeError):
                row["military_research"] = None
        return row

    async def get_all_nations(self) -> List[Dict[str, Any]]:
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        "SELECT * FROM nations "
                        "WHERE nation_name IS NOT NULL AND nation_name != '' "
                        "  AND alliance_id = ? "
                        "ORDER BY score DESC",
                        (ALLIANCE_ID,)
                    ).fetchall()
                    return [self._deserialize_nation(dict(r)) for r in rows]
            except Exception as e:
                logger.error(f"get_all_nations: {e}")
                return []

    async def get_nation(self, nation_id: int) -> Optional[Dict[str, Any]]:
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute("SELECT * FROM nations WHERE id = ?", (nation_id,)).fetchone()
                    return self._deserialize_nation(dict(row)) if row else None
            except Exception as e:
                logger.error(f"get_nation({nation_id}): {e}")
                return None

    async def get_cities_for_nation(self, nation_id: int) -> List[Dict[str, Any]]:
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute("SELECT * FROM cities WHERE nation_id = ?", (nation_id,)).fetchall()
                    return [dict(r) for r in rows]
            except Exception as e:
                logger.error(f"get_cities_for_nation({nation_id}): {e}")
                return []

    async def get_stats(self) -> Dict[str, int]:
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    c = conn.cursor()
                    nations = c.execute("SELECT COUNT(*) FROM nations WHERE nation_name IS NOT NULL AND nation_name != ''").fetchone()[0]
                    cities  = c.execute("SELECT COUNT(*) FROM cities").fetchone()[0]
                    return {"nations": nations, "cities": cities}
            except Exception as e:
                logger.error(f"get_stats: {e}")
                return {"nations": 0, "cities": 0}

    async def remove_departed_nations(self, current_ids: set) -> int:
        """Delete nations (and their cities) that are no longer in the alliance."""
        if not current_ids:
            return 0
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    c = conn.cursor()
                    # Find IDs in DB that aren't in the current member list
                    c.execute("SELECT id FROM nations WHERE nation_name IS NOT NULL AND nation_name != ''")
                    db_ids = {row[0] for row in c.fetchall()}
                    departed = db_ids - current_ids
                    if not departed:
                        return 0
                    placeholders = ",".join("?" * len(departed))
                    c.execute(f"DELETE FROM cities  WHERE nation_id IN ({placeholders})", list(departed))
                    c.execute(f"DELETE FROM nations WHERE id        IN ({placeholders})", list(departed))
                    conn.commit()
                    logger.info(f"remove_departed_nations: removed {len(departed)} nations: {departed}")
                    return len(departed)
            except Exception as e:
                logger.error(f"remove_departed_nations: {e}", exc_info=True)
                return 0

    async def purge_skeleton_rows(self) -> int:
        """Remove any rows that were created without a nation_name (patch-only inserts)."""
        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    c = conn.cursor()
                    c.execute("DELETE FROM nations WHERE nation_name IS NULL OR nation_name = ''")
                    deleted = c.rowcount
                    conn.commit()
                    if deleted:
                        logger.info(f"purge_skeleton_rows: removed {deleted} skeleton nation rows")
                    return deleted
            except Exception as e:
                logger.error(f"purge_skeleton_rows: {e}")
                return 0

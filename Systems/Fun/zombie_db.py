"""
ZombieDB — SQLite persistence for the Zombie Survival game.

Tables:
  zombie_game      — single-row active game state (id=1 always)
  zombie_survivors — one row per survivor (keyed by user_id)
  zombie_history   — one row per resolved round (last 5 kept)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional
from Systems.Functions.db_paths import ZOMBIE_DB, ZOMBIE_DB_STR

import aiosqlite

logger = logging.getLogger(__name__)

DB_FILE = ZOMBIE_DB_STR
os.makedirs(str(ZOMBIE_DB.parent), exist_ok=True)


class ZombieDB:
    _instance: Optional["ZombieDB"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_ready", False):
            return
        self._ready = False
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    # ── Schema ────────────────────────────────────────────────────────────────

    async def ensure_ready(self):
        if self._ready:
            return
        async with self._get_lock():
            if self._ready:
                return
            await self._init_schema()
            self._ready = True

    async def _init_schema(self):
        async with aiosqlite.connect(DB_FILE) as db:
            await db.executescript("""
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS zombie_game (
                    id               INTEGER PRIMARY KEY CHECK (id = 1),
                    active           INTEGER NOT NULL DEFAULT 0,
                    channel_id       INTEGER,
                    message_id       INTEGER,
                    round            INTEGER NOT NULL DEFAULT 0,
                    current_event    TEXT    NOT NULL DEFAULT '',
                    choices          TEXT    NOT NULL DEFAULT '[]',
                    choice_odds      TEXT    NOT NULL DEFAULT '[50,50,50,50]',
                    votes            TEXT    NOT NULL DEFAULT '{}',
                    voters           TEXT    NOT NULL DEFAULT '[]',
                    world_impact     TEXT    NOT NULL DEFAULT '{}',
                    last_update      REAL    NOT NULL DEFAULT 0,
                    updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS zombie_survivors (
                    user_id         TEXT    PRIMARY KEY,
                    health          INTEGER NOT NULL DEFAULT 100,
                    stamina         INTEGER NOT NULL DEFAULT 100,
                    morale          INTEGER NOT NULL DEFAULT 75,
                    status          TEXT    NOT NULL DEFAULT 'Normal',
                    revolver_loaded INTEGER NOT NULL DEFAULT 6,
                    revolver_spare  INTEGER NOT NULL DEFAULT 6,
                    rifle_loaded    INTEGER NOT NULL DEFAULT 12,
                    rifle_spare     INTEGER NOT NULL DEFAULT 0,
                    melee           TEXT    NOT NULL DEFAULT 'Crowbar',
                    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS zombie_history (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    round_num    INTEGER NOT NULL,
                    event_text   TEXT    NOT NULL DEFAULT '',
                    outcome_text TEXT    NOT NULL DEFAULT '',
                    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
                );
            """)
            # Migrations: add new columns if they don't exist yet (handles existing DBs)
            for col_def in [
                "ALTER TABLE zombie_game ADD COLUMN choice_odds TEXT NOT NULL DEFAULT '[50,50,50,50]'",
                "ALTER TABLE zombie_survivors ADD COLUMN revolver_loaded INTEGER NOT NULL DEFAULT 6",
                "ALTER TABLE zombie_survivors ADD COLUMN revolver_spare  INTEGER NOT NULL DEFAULT 6",
                "ALTER TABLE zombie_survivors ADD COLUMN rifle_loaded    INTEGER NOT NULL DEFAULT 12",
                "ALTER TABLE zombie_survivors ADD COLUMN rifle_spare     INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE zombie_survivors ADD COLUMN melee           TEXT    NOT NULL DEFAULT 'Crowbar'",
            ]:
                try:
                    await db.execute(col_def)
                except Exception:
                    pass   # column already exists
            await db.commit()
        logger.info("ZombieDB ready at %s", DB_FILE)

    # ── Load ──────────────────────────────────────────────────────────────────

    async def load_state(self) -> Dict[str, Any]:
        """Load full game state from DB. Returns default if nothing saved."""
        await self.ensure_ready()
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = aiosqlite.Row

            async with db.execute("SELECT * FROM zombie_game WHERE id = 1") as cur:
                row = await cur.fetchone()

            if row is None:
                return self._default_state()

            state: Dict[str, Any] = {
                "active":        bool(row["active"]),
                "channel_id":    row["channel_id"],
                "message_id":    row["message_id"],
                "round":         row["round"],
                "current_event": row["current_event"],
                "choices":       json.loads(row["choices"]),
                "choice_odds":   json.loads(row["choice_odds"]),
                "votes":         json.loads(row["votes"]),
                "voters":        json.loads(row["voters"]),
                "world_impact":  json.loads(row["world_impact"]),
                "last_update":   row["last_update"],
            }

            survivors: Dict[str, Any] = {}
            async with db.execute("SELECT * FROM zombie_survivors") as cur:
                async for srow in cur:
                    survivors[srow["user_id"]] = {
                        "health":          srow["health"],
                        "stamina":         srow["stamina"],
                        "morale":          srow["morale"],
                        "status":          srow["status"],
                        "revolver_loaded": srow["revolver_loaded"],
                        "revolver_spare":  srow["revolver_spare"],
                        "rifle_loaded":    srow["rifle_loaded"],
                        "rifle_spare":     srow["rifle_spare"],
                        "melee":           srow["melee"],
                    }
            state["survivors"] = survivors

            # History — load ordered oldest→newest
            history: List[Dict[str, str]] = []
            async with db.execute(
                "SELECT round_num, event_text, outcome_text "
                "FROM zombie_history ORDER BY id ASC"
            ) as cur:
                async for hrow in cur:
                    history.append({
                        "round":        hrow["round_num"],
                        "event":        hrow["event_text"],
                        "outcome_text": hrow["outcome_text"],
                    })
            state["history"] = history

        return state

    # ── Save game row + survivors (called on every vote / state change) ───────

    async def save_game(self, state: Dict[str, Any]):
        """Persist game row and all survivors. Does NOT touch history."""
        await self.ensure_ready()
        async with self._get_lock():
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute("""
                    INSERT INTO zombie_game
                        (id, active, channel_id, message_id, round,
                         current_event, choices, choice_odds, votes, voters,
                         world_impact, last_update, updated_at)
                    VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(id) DO UPDATE SET
                        active        = excluded.active,
                        channel_id    = excluded.channel_id,
                        message_id    = excluded.message_id,
                        round         = excluded.round,
                        current_event = excluded.current_event,
                        choices       = excluded.choices,
                        choice_odds   = excluded.choice_odds,
                        votes         = excluded.votes,
                        voters        = excluded.voters,
                        world_impact  = excluded.world_impact,
                        last_update   = excluded.last_update,
                        updated_at    = excluded.updated_at
                """, (
                    1 if state.get("active") else 0,
                    state.get("channel_id"),
                    state.get("message_id"),
                    state.get("round", 0),
                    state.get("current_event", ""),
                    json.dumps(state.get("choices", [])),
                    json.dumps(state.get("choice_odds", [50, 50, 50, 50])),
                    json.dumps(state.get("votes", {})),
                    json.dumps(state.get("voters", [])),
                    json.dumps(state.get("world_impact", {})),
                    state.get("last_update", 0),
                ))

                for user_id, s in state.get("survivors", {}).items():
                    await db.execute("""
                        INSERT INTO zombie_survivors
                            (user_id, health, stamina, morale, status,
                             revolver_loaded, revolver_spare,
                             rifle_loaded, rifle_spare, melee, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                        ON CONFLICT(user_id) DO UPDATE SET
                            health          = excluded.health,
                            stamina         = excluded.stamina,
                            morale          = excluded.morale,
                            status          = excluded.status,
                            revolver_loaded = excluded.revolver_loaded,
                            revolver_spare  = excluded.revolver_spare,
                            rifle_loaded    = excluded.rifle_loaded,
                            rifle_spare     = excluded.rifle_spare,
                            melee           = excluded.melee,
                            updated_at      = excluded.updated_at
                    """, (
                        user_id,
                        s.get("health",          100),
                        s.get("stamina",         100),
                        s.get("morale",           75),
                        s.get("status",       "Normal"),
                        s.get("revolver_loaded",   6),
                        s.get("revolver_spare",    6),
                        s.get("rifle_loaded",     12),
                        s.get("rifle_spare",       0),
                        s.get("melee",       "Crowbar"),
                    ))

                await db.commit()

    # ── Append a resolved round to history (called once per round) ────────────

    async def append_history(self, round_num: int, event_text: str, outcome_text: str):
        """Insert one history row and trim to last 5."""
        await self.ensure_ready()
        async with self._get_lock():
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute(
                    "INSERT INTO zombie_history (round_num, event_text, outcome_text) VALUES (?, ?, ?)",
                    (round_num, event_text, outcome_text),
                )
                await db.execute("""
                    DELETE FROM zombie_history
                    WHERE id NOT IN (
                        SELECT id FROM zombie_history ORDER BY id DESC LIMIT 5
                    )
                """)
                await db.commit()

    # ── Reset ─────────────────────────────────────────────────────────────────

    async def reset(self):
        """Wipe all game data for a fresh start."""
        await self.ensure_ready()
        async with self._get_lock():
            async with aiosqlite.connect(DB_FILE) as db:
                await db.execute("DELETE FROM zombie_game")
                await db.execute("DELETE FROM zombie_survivors")
                await db.execute("DELETE FROM zombie_history")
                await db.commit()

    # ── Default ───────────────────────────────────────────────────────────────

    @staticmethod
    def _default_state() -> Dict[str, Any]:
        return {
            "active": False, "history": [], "current_event": "",
            "choices": [], "choice_odds": [50, 50, 50, 50],
            "votes": {}, "voters": [],
            "last_update": 0, "channel_id": None, "message_id": None,
            "round": 0, "survivors": {}, "world_impact": {},
        }

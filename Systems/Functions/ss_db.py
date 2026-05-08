"""
Survivor Series Database
Dedicated SQLite persistence for all SS game data:
  - ss_games        : one row per game (metadata + final state JSON)
  - ss_rounds       : one row per round per game (actions + eliminations feed)
  - ss_participants : one row per participant per game (placement, kills, is_npc)
  - ss_pet_stats    : cumulative per-user stats (games, wins, kills, placements)
  - ss_active       : single-row active game state (replaces the old ss_state table)

All writes are async (aiosqlite). The module exposes a singleton SsDatabase.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiosqlite
from Systems.Functions.db_paths import SURVIVOR_DB, SURVIVOR_DB_STR

logger = logging.getLogger(__name__)

SS_DB_FILE = SURVIVOR_DB_STR
os.makedirs(str(SURVIVOR_DB.parent), exist_ok=True)


class SsDatabase:
    _instance: Optional["SsDatabase"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_ready", False):
            return
        self._ready = False
        self._lock: Optional[asyncio.Lock] = None  # created lazily inside event loop

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    # ── Init ─────────────────────────────────────────────────────────────────

    async def ensure_ready(self):
        if self._ready:
            return
        async with self._get_lock():
            if self._ready:
                return
            await self._init_schema()
            self._ready = True

    async def _init_schema(self):
        async with aiosqlite.connect(SS_DB_FILE) as db:
            await db.executescript("""
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS ss_active (
                    id          INTEGER PRIMARY KEY CHECK (id = 1),
                    state_json  TEXT    NOT NULL,
                    updated_at  INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ss_games (
                    game_id      TEXT    PRIMARY KEY,
                    status       TEXT    NOT NULL DEFAULT 'lobby',
                    started_by   TEXT,
                    created_at   TEXT    NOT NULL,
                    start_time   TEXT,
                    finished_at  TEXT,
                    total_rounds INTEGER NOT NULL DEFAULT 0,
                    winner_id    TEXT,
                    winner_name  TEXT,
                    winner_pet   TEXT,
                    participant_count INTEGER NOT NULL DEFAULT 0,
                    npc_count    INTEGER NOT NULL DEFAULT 0,
                    meta_json    TEXT    NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS ss_rounds (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id     TEXT    NOT NULL REFERENCES ss_games(game_id),
                    round_index INTEGER NOT NULL,
                    actions     TEXT    NOT NULL DEFAULT '[]',
                    eliminations TEXT   NOT NULL DEFAULT '[]',
                    remaining_count INTEGER NOT NULL DEFAULT 0,
                    timestamp   TEXT    NOT NULL,
                    UNIQUE(game_id, round_index)
                );

                CREATE TABLE IF NOT EXISTS ss_feed (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id     TEXT    NOT NULL REFERENCES ss_games(game_id),
                    round_index INTEGER NOT NULL DEFAULT 0,
                    event_type  TEXT    NOT NULL DEFAULT 'action',
                    text        TEXT    NOT NULL,
                    ts          INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ss_participants (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id     TEXT    NOT NULL REFERENCES ss_games(game_id),
                    user_id     TEXT    NOT NULL,
                    username    TEXT    NOT NULL DEFAULT '',
                    pet_name    TEXT    NOT NULL DEFAULT '',
                    species     TEXT    NOT NULL DEFAULT 'Cat',
                    element     TEXT    NOT NULL DEFAULT 'basic',
                    is_npc      INTEGER NOT NULL DEFAULT 0,
                    placement   INTEGER,
                    kills       INTEGER NOT NULL DEFAULT 0,
                    eliminated_round INTEGER,
                    UNIQUE(game_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS ss_pet_stats (
                    user_id         TEXT    PRIMARY KEY,
                    games_played    INTEGER NOT NULL DEFAULT 0,
                    games_won       INTEGER NOT NULL DEFAULT 0,
                    total_kills     INTEGER NOT NULL DEFAULT 0,
                    best_placement  INTEGER,
                    last_played_at  TEXT,
                    last_won_at     TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_ss_rounds_game   ON ss_rounds(game_id);
                CREATE INDEX IF NOT EXISTS idx_ss_feed_game     ON ss_feed(game_id);
                CREATE INDEX IF NOT EXISTS idx_ss_parts_game    ON ss_participants(game_id);
                CREATE INDEX IF NOT EXISTS idx_ss_parts_user    ON ss_participants(user_id);
            """)
            await db.commit()
        logger.info("SS database schema ready")

    # ── Active game state (replaces ss_state in reaper.db) ───────────────────

    async def save_active(self, game: Optional[Dict[str, Any]]):
        await self.ensure_ready()
        async with aiosqlite.connect(SS_DB_FILE) as db:
            if game is None:
                await db.execute("DELETE FROM ss_active WHERE id = 1")
            else:
                # Use a custom encoder that converts sets to sorted lists so the
                # game state (which may contain set() values like _env_damaged)
                # serialises cleanly without raising TypeError.
                class _SetEncoder(json.JSONEncoder):
                    def default(self, o: Any) -> Any:
                        if isinstance(o, set):
                            return sorted(o, key=str)
                        return super().default(o)
                await db.execute(
                    "INSERT OR REPLACE INTO ss_active (id, state_json, updated_at) VALUES (1, ?, ?)",
                    (json.dumps(game, cls=_SetEncoder), int(time.time()))
                )
            await db.commit()

    async def load_active(self) -> Optional[Dict[str, Any]]:
        await self.ensure_ready()
        async with aiosqlite.connect(SS_DB_FILE) as db:
            async with db.execute("SELECT state_json FROM ss_active WHERE id = 1") as cur:
                row = await cur.fetchone()
        if not row:
            return None
        return json.loads(row[0])

    # ── Game lifecycle ────────────────────────────────────────────────────────

    async def upsert_game(self, game: Dict[str, Any]):
        """Create or update the ss_games row for this game."""
        await self.ensure_ready()
        gid    = game.get("game_id", "")
        status = game.get("status", "lobby")
        parts  = game.get("participants", [])
        npcs   = sum(1 for p in parts if p.get("is_npc"))
        winner = game.get("winner") or {}
        async with aiosqlite.connect(SS_DB_FILE) as db:
            await db.execute("""
                INSERT INTO ss_games
                    (game_id, status, started_by, created_at, start_time, finished_at,
                     total_rounds, winner_id, winner_name, winner_pet,
                     participant_count, npc_count, meta_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(game_id) DO UPDATE SET
                    status          = excluded.status,
                    start_time      = excluded.start_time,
                    finished_at     = excluded.finished_at,
                    total_rounds    = excluded.total_rounds,
                    winner_id       = excluded.winner_id,
                    winner_name     = excluded.winner_name,
                    winner_pet      = excluded.winner_pet,
                    participant_count = excluded.participant_count,
                    npc_count       = excluded.npc_count,
                    meta_json       = excluded.meta_json
            """, (
                gid,
                status,
                game.get("started_by"),
                game.get("created_at", datetime.now().isoformat()),
                game.get("start_time"),
                game.get("finished_at"),
                game.get("round_index", 0),
                winner.get("user_id") if winner else None,
                winner.get("username") if winner else None,
                winner.get("pet_name") if winner else None,
                len(parts),
                npcs,
                json.dumps(game),
            ))
            await db.commit()

    async def save_round(self, game_id: str, round_snapshot: Dict[str, Any]):
        """Persist a round's actions/eliminations."""
        await self.ensure_ready()
        async with aiosqlite.connect(SS_DB_FILE) as db:
            await db.execute("""
                INSERT OR REPLACE INTO ss_rounds
                    (game_id, round_index, actions, eliminations, remaining_count, timestamp)
                VALUES (?,?,?,?,?,?)
            """, (
                game_id,
                round_snapshot.get("round_index", 0),
                json.dumps(round_snapshot.get("actions", [])),
                json.dumps(round_snapshot.get("eliminations", [])),
                round_snapshot.get("remaining_count", 0),
                round_snapshot.get("timestamp", datetime.now().isoformat()),
            ))
            # Also write each line to the feed table
            ts = int(time.time())
            rnd = round_snapshot.get("round_index", 0)
            feed_rows = []
            for a in round_snapshot.get("actions", []):
                feed_rows.append((game_id, rnd, "action", str(a), ts))
            for e in round_snapshot.get("eliminations", []):
                feed_rows.append((game_id, rnd, "elimination", str(e), ts))
            if feed_rows:
                await db.executemany(
                    "INSERT INTO ss_feed (game_id, round_index, event_type, text, ts) VALUES (?,?,?,?,?)",
                    feed_rows
                )
            await db.commit()

    async def save_participants(self, game_id: str, participants: List[Dict[str, Any]],
                                 eliminated: List[Dict[str, Any]], alive_ids: List[str],
                                 kill_counts: Optional[Dict[str, int]] = None):
        """Upsert participant rows with placement/kills."""
        await self.ensure_ready()
        kill_counts = kill_counts or {}
        # Build placement map: alive = 1st, then eliminated in reverse order
        placement_map: Dict[str, int] = {}
        total = len(participants)
        for i, uid in enumerate(alive_ids):
            placement_map[uid] = i + 1
        for i, e in enumerate(reversed(eliminated)):
            uid = e.get("user_id", "")
            if uid not in placement_map:
                placement_map[uid] = len(alive_ids) + i + 1

        rows = []
        for p in participants:
            uid = p.get("user_id", "")
            rows.append((
                game_id,
                uid,
                p.get("username", ""),
                p.get("pet_name", ""),
                p.get("species", "Cat"),
                p.get("element", "basic"),
                1 if p.get("is_npc") else 0,
                placement_map.get(uid),
                kill_counts.get(uid, 0),
                next((e.get("round") for e in eliminated if e.get("user_id") == uid), None),
            ))

        async with aiosqlite.connect(SS_DB_FILE) as db:
            await db.executemany("""
                INSERT INTO ss_participants
                    (game_id, user_id, username, pet_name, species, element,
                     is_npc, placement, kills, eliminated_round)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(game_id, user_id) DO UPDATE SET
                    placement        = excluded.placement,
                    kills            = excluded.kills,
                    eliminated_round = excluded.eliminated_round
            """, rows)
            await db.commit()

    async def update_pet_stats(self, user_id: str, won: bool, kills: int, placement: int):
        """Increment cumulative per-pet SS stats."""
        await self.ensure_ready()
        now = datetime.now().isoformat()
        async with aiosqlite.connect(SS_DB_FILE) as db:
            await db.execute("""
                INSERT INTO ss_pet_stats (user_id, games_played, games_won, total_kills, best_placement, last_played_at, last_won_at)
                VALUES (?, 1, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    games_played   = games_played + 1,
                    games_won      = games_won + excluded.games_won,
                    total_kills    = total_kills + excluded.total_kills,
                    best_placement = CASE
                        WHEN best_placement IS NULL THEN excluded.best_placement
                        WHEN excluded.best_placement < best_placement THEN excluded.best_placement
                        ELSE best_placement
                    END,
                    last_played_at = excluded.last_played_at,
                    last_won_at    = CASE WHEN excluded.games_won > 0 THEN excluded.last_won_at ELSE last_won_at END
            """, (user_id, 1 if won else 0, kills, placement, now, now if won else None))
            await db.commit()

    # ── Feed helper ───────────────────────────────────────────────────────────

    async def add_feed_event(self, game_id: str, round_index: int, event_type: str, text: str):
        await self.ensure_ready()
        async with aiosqlite.connect(SS_DB_FILE) as db:
            await db.execute(
                "INSERT INTO ss_feed (game_id, round_index, event_type, text, ts) VALUES (?,?,?,?,?)",
                (game_id, round_index, event_type, text, int(time.time()))
            )
            await db.commit()

    # ── Query helpers ─────────────────────────────────────────────────────────

    async def get_pet_stats(self, user_id: str) -> Optional[Dict[str, Any]]:
        await self.ensure_ready()
        async with aiosqlite.connect(SS_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM ss_pet_stats WHERE user_id = ?", (str(user_id),)
            ) as cur:
                row = await cur.fetchone()
        if not row:
            return None
        return dict(row)

    async def get_game_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        await self.ensure_ready()
        async with aiosqlite.connect(SS_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM ss_games ORDER BY created_at DESC LIMIT ?", (limit,)
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def get_game_rounds(self, game_id: str) -> List[Dict[str, Any]]:
        await self.ensure_ready()
        async with aiosqlite.connect(SS_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM ss_rounds WHERE game_id = ? ORDER BY round_index", (game_id,)
            ) as cur:
                rows = await cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["actions"]      = json.loads(d.get("actions", "[]"))
            d["eliminations"] = json.loads(d.get("eliminations", "[]"))
            result.append(d)
        return result

    async def get_game_feed(self, game_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        await self.ensure_ready()
        async with aiosqlite.connect(SS_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM ss_feed WHERE game_id = ? ORDER BY id DESC LIMIT ?",
                (game_id, limit)
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in reversed(rows)]

    async def get_game_participants(self, game_id: str) -> List[Dict[str, Any]]:
        await self.ensure_ready()
        async with aiosqlite.connect(SS_DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM ss_participants WHERE game_id = ? ORDER BY placement ASC NULLS LAST",
                (game_id,)
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def load_last_finished(self) -> Optional[Dict[str, Any]]:
        """Return the most recently finished game's complete data, or None."""
        await self.ensure_ready()
        async with aiosqlite.connect(SS_DB_FILE) as db:
            # First try to get the complete data from meta_json
            async with db.execute(
                "SELECT meta_json FROM ss_games WHERE status = 'finished' ORDER BY finished_at DESC LIMIT 1"
            ) as cur:
                row = await cur.fetchone()
            
            if row and row[0]:
                try:
                    meta_data = json.loads(row[0])
                    # Check if this is complete game data (has winner, participants, etc.)
                    if 'winner' in meta_data and 'participants' in meta_data:
                        return meta_data
                except Exception:
                    pass
            
            # Fallback: reconstruct from individual columns + related tables
            async with db.execute("""
                SELECT game_id, winner_id, winner_name, winner_pet, 
                       participant_count, total_rounds, finished_at, meta_json
                FROM ss_games 
                WHERE status = 'finished' 
                ORDER BY finished_at DESC LIMIT 1
            """) as cur:
                game_row = await cur.fetchone()
            
            if not game_row:
                return None
                
            game_id = game_row[0]
            
            # Get participants (we don't store them in ss_participants for old games, so create minimal data)
            participants = []
            participant_count = game_row[4] or 0  # Use stored participant count
            npc_count = 0
            
            if game_row[1]:  # winner_id exists
                winner_participant = {
                    "user_id": game_row[1],
                    "username": game_row[2] or "Unknown",
                    "pet_name": game_row[3] or "Unknown",
                    "species": "Cat",  # Default since we don't store this
                    "element": "basic",  # Default since we don't store this
                    "is_npc": game_row[2] and game_row[2].startswith("NPC "),
                }
                participants.append(winner_participant)
                if winner_participant["is_npc"]:
                    npc_count = 1
            
            # For display purposes, create placeholder participants to match the stored count
            # This ensures the participant count in the UI is accurate
            remaining_count = max(0, participant_count - len(participants))
            for i in range(remaining_count):
                is_npc = i < (participant_count - (participant_count // 4))  # Assume most were NPCs
                participants.append({
                    "user_id": f"unknown_{i}",
                    "username": f"Participant {i+2}",
                    "pet_name": f"Pet {i+2}",
                    "species": "Cat",
                    "element": "basic",
                    "is_npc": is_npc,
                })
                if is_npc:
                    npc_count += 1
            
            # Get rounds data
            rounds = []
            async with db.execute(
                "SELECT round_index, actions, eliminations, remaining_count, timestamp FROM ss_rounds WHERE game_id = ? ORDER BY round_index",
                (game_id,)
            ) as cur:
                round_rows = await cur.fetchall()
            
            for round_row in round_rows:
                try:
                    rounds.append({
                        "round_index": round_row[0],
                        "actions": json.loads(round_row[1]) if round_row[1] else [],
                        "eliminations": json.loads(round_row[2]) if round_row[2] else [],
                        "remaining_count": round_row[3],
                        "timestamp": round_row[4],
                    })
                except Exception:
                    continue
            
            # Reconstruct the game data
            return {
                "winner": {
                    "user_id": game_row[1],
                    "username": game_row[2] or "Unknown",
                    "pet_name": game_row[3] or "Unknown",
                    "species": "Cat",
                    "element": "basic",
                    "is_npc": game_row[2] and game_row[2].startswith("NPC "),
                } if game_row[1] else {},
                "participants": participants,
                "eliminated": [],  # We don't have this data for old games
                "rounds": rounds,
                "round_index": game_row[5] or 0,
                "finished_at": game_row[6],
            }


# Singleton
ss_db = SsDatabase()

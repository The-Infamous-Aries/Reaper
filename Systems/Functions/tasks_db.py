"""
Tasks database — stores per-user task slots, progress, cooldowns, and DM preferences.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from datetime import datetime, timezone, date
from typing import Any, Dict, List, Optional
from Systems.Functions.db_paths import TASKS_DB, TASKS_DB_STR

import aiosqlite

logger = logging.getLogger("tasks_db")

# ── UTC day helpers ───────────────────────────────────────────────────────────

def _utc_today() -> str:
    """Return today's UTC date as YYYY-MM-DD string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def _utc_yesterday() -> str:
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

def _next_utc_midnight_ts() -> float:
    """Unix timestamp of the next UTC midnight."""
    now = datetime.now(timezone.utc)
    tomorrow = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    from datetime import timedelta
    tomorrow += timedelta(days=1)
    return tomorrow.timestamp()

# ── Chest progression ─────────────────────────────────────────────────────────
# Streak 0 = no previous day completed → chest1
# Streak 1 = completed yesterday → chest2, etc., capped at chest4
CHEST_PROGRESSION = ["chest1", "chest2", "chest3", "chest4"]

def _goal_chest_for_streak(streak: int) -> str:
    idx = min(max(streak, 0), len(CHEST_PROGRESSION) - 1)
    return CHEST_PROGRESSION[idx]

# ── Task generation constants ─────────────────────────────────────────────────

TASK_ACTIONS = [
    # (action_key, label_template, count_range, reward_tier)
    ("play",           "Play with your pet {n} time(s)",          (1, 3), 1),
    ("play",           "Play with your pet {n} time(s)",          (1, 3), 1),
    ("train",          "Train your pet {n} time(s)",              (1, 3), 1),
    ("train",          "Train your pet {n} time(s)",              (1, 3), 1),
    ("mission",        "Complete {n} mission(s)",                 (1, 2), 2),
    ("mission",        "Complete {n} mission(s)",                 (1, 2), 2),
    ("battle_npc",     "Win {n} NPC battle(s)",                   (1, 2), 2),
    ("battle_npc",     "Win {n} NPC battle(s)",                   (1, 2), 2),
    ("quest",          "Complete {n} quest(s)",                   (1, 2), 3),
    ("quest",          "Complete {n} quest(s)",                   (1, 2), 3),
    ("gift",           "Gift an item to another pet",             (1, 1), 2),
    ("boss",           "Win a boss battle",                       (1, 1), 4),
    ("rename",         "Pet is tired of {action} — rename it",    (1, 1), 2),
    ("potion",         "Use {n} potion(s) on your pet",           (1, 2), 1),
    ("loot",           "Open {n} chest(s)",                       (1, 2), 2),
    ("equip",          "Equip {n} item(s) to your pet",           (1, 2), 1),
    ("consume",        "Consume {n} item(s)",                     (1, 2), 1),
    ("buy_token",      "Buy {n} pet stock token(s)",              (1, 3), 2),
    ("sell_token",     "Sell {n} pet stock token(s)",             (1, 3), 2),
    ("play_slots",     "Play the slot machine {n} time(s)",       (1, 3), 2),
    ("play_keno",      "Play Mega Keno {n} time(s)",              (1, 10), None),  # scaled reward by n
    ("post_item",      "Post an item on the Item Board",          (1, 1), 1),
    ("coin_flip",      "Flip a coin {n} time(s)",                 (1, 5), None),  # random key reward
    ("get_horoscope",  "Get your daily horoscope",                 (1, 1), None),  # random chest reward
    ("race_play",      "Race your pet {n} time(s)",               (1, 10), None),  # scaled reward
    ("race_win",       "Win {n} race(s)",                         (1, 10), None),  # scaled reward
    ("ss_join",        "Join a Survivor Series game",             (1, 1), 2),
    ("ss_eliminate",   "Eliminate {n} pet(s) in Survive (today)", (1, 5), None),   # reward scaled by n
    ("ss_rounds",      "Survive {n} round(s) in Survive (today)", (1, 10), None),  # reward scaled by n
    ("buy_powerball",  "Buy a Powerball Ticket",                  (1, 1),  3),
    ("scratch_card",   "Scratch {n} Ticket(s)",                   (1, 5), None),  # random key reward
]

BATTLE_ACTIONS = ["Attack", "Defense", "Charge"]

KEY_TYPES = ["Key1", "Key2", "Key3"]
CHEST_TYPES = ["chest1", "chest2", "chest3", "chest4"]

# Reward tiers: list of (weight, reward_dict)
REWARD_TIERS = {
    1: [
        (60, {"type": "key",   "item": "Key1",   "count": 1}),
        (30, {"type": "key",   "item": "Key2",   "count": 1}),
        (10, {"type": "key",   "item": "Key3",   "count": 1}),
    ],
    2: [
        (40, {"type": "key",   "item": "Key1",   "count": 2}),
        (35, {"type": "key",   "item": "Key2",   "count": 1}),
        (20, {"type": "key",   "item": "Key3",   "count": 1}),
        (5,  {"type": "chest", "item": "chest1", "count": 1}),
    ],
    3: [
        (30, {"type": "key",   "item": "Key1",   "count": 3}),
        (30, {"type": "key",   "item": "Key2",   "count": 2}),
        (25, {"type": "key",   "item": "Key3",   "count": 1}),
        (10, {"type": "chest", "item": "chest2", "count": 1}),
        (5,  {"type": "chest", "item": "chest3", "count": 1}),
    ],
    4: [
        (20, {"type": "key",   "item": "Key1",   "count": 3}),
        (20, {"type": "key",   "item": "Key2",   "count": 2}),
        (20, {"type": "key",   "item": "Key3",   "count": 2}),
        (20, {"type": "chest", "item": "chest2", "count": 1}),
        (15, {"type": "chest", "item": "chest3", "count": 1}),
        (5,  {"type": "chest", "item": "chest4", "count": 1}),
    ],
}


def _weighted_choice(options: list) -> dict:
    weights = [w for w, _ in options]
    total = sum(weights)
    r = random.uniform(0, total)
    cumulative = 0
    for w, item in options:
        cumulative += w
        if r <= cumulative:
            return item
    return options[-1][1]


def _scaled_ss_reward(n: int, max_n: int) -> dict:
    """Scale reward from Key1 (n=1) up to chest4 (n=max_n) linearly."""
    ratio = (n - 1) / max(max_n - 1, 1)
    if ratio < 0.2:
        return {"type": "key",   "item": "Key1",   "count": 1}
    elif ratio < 0.4:
        return {"type": "key",   "item": "Key2",   "count": 1}
    elif ratio < 0.6:
        return {"type": "key",   "item": "Key3",   "count": 1}
    elif ratio < 0.8:
        return {"type": "chest", "item": "chest2", "count": 1}
    elif ratio < 0.95:
        return {"type": "chest", "item": "chest3", "count": 1}
    else:
        return {"type": "chest", "item": "chest4", "count": 1}


def _scaled_race_reward(n: int, max_n: int) -> dict:
    """Scale reward from Key1 (n=1) up to Key3 (n=max_n) linearly."""
    ratio = (n - 1) / max(max_n - 1, 1)
    if ratio < 0.4:
        return {"type": "key", "item": "Key1", "count": 1}
    elif ratio < 0.75:
        return {"type": "key", "item": "Key2", "count": 1}
    else:
        return {"type": "key", "item": "Key3", "count": 1}


def generate_task(exclude_actions: Optional[List[str]] = None) -> Dict[str, Any]:
    """Generate a single random task with reward.

    Args:
        exclude_actions: List of action keys to avoid (used to prevent giving the
                         same task that was just completed/dismissed).  If the pool
                         would be exhausted after exclusion the constraint is relaxed.
    """
    pool = TASK_ACTIONS
    if exclude_actions:
        filtered = [t for t in TASK_ACTIONS if t[0] not in exclude_actions]
        if filtered:
            pool = filtered
        # else: all actions excluded — fall back to full pool

    action_key, label_tmpl, count_range, tier = random.choice(pool)
    n = random.randint(*count_range)

    if action_key == "rename":
        battle_action = random.choice(BATTLE_ACTIONS)
        label = label_tmpl.format(action=battle_action)
        meta = {"battle_action": battle_action}
    elif "{n}" in label_tmpl:
        label = label_tmpl.format(n=n)
        meta = {}
    else:
        label = label_tmpl
        meta = {}

    # Scaled rewards for SS tasks
    if action_key == "ss_eliminate":
        reward = _scaled_ss_reward(n, 5)
    elif action_key == "ss_rounds":
        reward = _scaled_ss_reward(n, 10)
    elif action_key in ("race_play", "race_win"):
        reward = _scaled_race_reward(n, count_range[1])
    elif action_key == "play_keno":
        reward = _scaled_race_reward(n, count_range[1])  # same scale: Key1→Key3 over 1-10
    elif action_key == "coin_flip":
        # Random key (Key1/Key2/Key3 equally weighted)
        reward = _weighted_choice(REWARD_TIERS[1]).copy()
    elif action_key == "scratch_card":
        # Random key reward scaled by n (1-5 tickets)
        reward = _scaled_race_reward(n, 5)
    elif action_key == "get_horoscope":
        # Random chest (chest1-chest4 equally weighted)
        reward = {"type": "chest", "item": random.choice(["chest1", "chest2", "chest3", "chest4"]), "count": 1}
    else:
        reward = _weighted_choice(REWARD_TIERS[tier]).copy()

    return {
        "action":    action_key,
        "label":     label,
        "required":  n,
        "progress":  0,
        "meta":      meta,
        "reward":    reward,
        "completed": False,
    }


def generate_daily_goal(streak: int) -> Dict[str, Any]:
    """Generate the Daily Goal task for today based on the user's current streak."""
    chest = _goal_chest_for_streak(streak)
    chest_labels = {
        "chest1": "Common Chest",
        "chest2": "Rare Chest",
        "chest3": "Epic Chest",
        "chest4": "Mythic Chest",
    }
    return {
        "action":    "daily_goal",
        "label":     "Complete 10 Daily Tasks",
        "required":  10,
        "progress":  0,
        "meta":      {"streak": streak, "utc_date": _utc_today()},
        "reward":    {"type": "chest", "item": chest, "count": 1},
        "completed": False,
        "is_daily_goal": True,
    }


# ── Database class ────────────────────────────────────────────────────────────

class TasksDB:
    _instance: Optional["TasksDB"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True
        from Systems.Functions.db_paths import TASKS_DB_STR
        import os
        os.makedirs(str(TASKS_DB.parent), exist_ok=True)
        self.db_path = TASKS_DB_STR
        self._lock = None
        self._ready = False

    def _get_lock(self):
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def ensure_ready(self):
        if self._ready:
            return
        async with self._get_lock():
            if self._ready:
                return
            await self._init_tables()
            self._ready = True

    async def _init_tables(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_tasks (
                    user_id        TEXT NOT NULL,
                    slot           INTEGER NOT NULL,
                    task_data      TEXT NOT NULL,
                    assigned_at    REAL NOT NULL DEFAULT 0,
                    cooldown_until REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, slot)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS task_dm_prefs (
                    user_id    TEXT PRIMARY KEY,
                    dm_enabled INTEGER NOT NULL DEFAULT 0,
                    dm_mode    TEXT NOT NULL DEFAULT 'all'
                )
            """)
            # Daily goal streak tracking
            # last_reset_date tracks when regular slots (1-6) were last wiped at midnight
            await db.execute("""
                CREATE TABLE IF NOT EXISTS daily_goal (
                    user_id         TEXT PRIMARY KEY,
                    streak          INTEGER NOT NULL DEFAULT 0,
                    last_completed  TEXT NOT NULL DEFAULT '',
                    last_issued     TEXT NOT NULL DEFAULT '',
                    last_reset_date TEXT NOT NULL DEFAULT ''
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user ON user_tasks(user_id)")
            await db.commit()
        logger.info("Tasks tables ready")
        await self._migrate_db()
        await self._migrate_goal_required()

    async def _migrate_db(self):
        """
        Add any missing columns to existing tables (safe to run on every startup).
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Add last_reset_date to daily_goal if it doesn't exist yet
                async with db.execute("PRAGMA table_info(daily_goal)") as cur:
                    cols = {row[1] for row in await cur.fetchall()}
                if "last_reset_date" not in cols:
                    await db.execute(
                        "ALTER TABLE daily_goal ADD COLUMN last_reset_date TEXT NOT NULL DEFAULT ''"
                    )
                    await db.commit()
                    logger.info("_migrate_db: added last_reset_date column to daily_goal")
        except Exception as e:
            logger.warning(f"_migrate_db failed (non-fatal): {e}")

    async def _migrate_goal_required(self):
        """
        One-time migration: patch any stored daily-goal tasks that still have
        required != 10 or are missing is_daily_goal. Runs at startup.
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT user_id, task_data FROM user_tasks WHERE slot=0"
                ) as cur:
                    rows = await cur.fetchall()

                patched = 0
                for row in rows:
                    task = json.loads(row["task_data"])
                    if (task.get("required") != 10
                            or task.get("label") != "Complete 10 Daily Tasks"
                            or not task.get("is_daily_goal")):
                        task["required"]      = 10
                        task["label"]         = "Complete 10 Daily Tasks"
                        task["is_daily_goal"] = True
                        task["progress"]      = min(task.get("progress", 0), 10)
                        if task["progress"] >= 10 and not task.get("completed"):
                            task["completed"]      = True
                            task["reward_claimed"] = False
                        await db.execute(
                            "UPDATE user_tasks SET task_data=? WHERE user_id=? AND slot=0",
                            (json.dumps(task), row["user_id"])
                        )
                        patched += 1

                if patched:
                    await db.commit()
                    logger.info(f"_migrate_goal_required: patched {patched} stale daily-goal row(s)")
        except Exception as e:
            logger.warning(f"_migrate_goal_required failed (non-fatal): {e}")

    # ── Daily goal helpers ────────────────────────────────────────────────────

    async def _get_goal_row(self, db, user_id: str) -> Dict[str, Any]:
        """Fetch or create the daily_goal row for a user (within an open db connection)."""
        async with db.execute(
            "SELECT streak, last_completed, last_issued, last_reset_date FROM daily_goal WHERE user_id=?",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
        if row:
            return {
                "streak": row[0],
                "last_completed": row[1],
                "last_issued": row[2],
                "last_reset_date": row[3] if row[3] else "",
            }
        # First time — insert defaults
        await db.execute(
            "INSERT OR IGNORE INTO daily_goal(user_id, streak, last_completed, last_issued, last_reset_date) VALUES(?,0,'','','')",
            (user_id,)
        )
        await db.commit()
        return {"streak": 0, "last_completed": "", "last_issued": "", "last_reset_date": ""}

    async def _get_or_refresh_daily_goal_slot(self, user_id: str, now: float) -> Dict[str, Any]:
        """
        Returns the current daily goal slot data, refreshing it if it's a new UTC day.
        Must be called inside self._get_lock().
        """
        today = _utc_today()
        yesterday = _utc_yesterday()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            goal_row = await self._get_goal_row(db, user_id)

            # Check if we already have a goal slot for today
            async with db.execute(
                "SELECT task_data, cooldown_until FROM user_tasks WHERE user_id=? AND slot=0",
                (user_id,)
            ) as cur:
                existing = await cur.fetchone()

            last_issued = goal_row["last_issued"]
            streak = goal_row["streak"]
            last_completed = goal_row["last_completed"]

            # If goal was already issued today, return it as-is — but patch stale fields
            if last_issued == today and existing:
                task = json.loads(existing["task_data"])
                cooldown_until = existing["cooldown_until"]

                # ── Migration: fix any stale goal that has wrong required/label ──
                needs_patch = (
                    task.get("required") != 10
                    or task.get("label") != "Complete 10 Daily Tasks"
                    or not task.get("is_daily_goal")
                )
                if needs_patch:
                    # Preserve progress and completed state, just fix the target
                    task["required"]      = 10
                    task["label"]         = "Complete 10 Daily Tasks"
                    task["is_daily_goal"] = True
                    # If progress somehow exceeds new required, cap it
                    task["progress"] = min(task.get("progress", 0), 10)
                    if task["progress"] >= 10 and not task.get("completed"):
                        task["completed"]      = True
                        task["reward_claimed"] = False
                    async with aiosqlite.connect(self.db_path) as _db:
                        await _db.execute(
                            "UPDATE user_tasks SET task_data=? WHERE user_id=? AND slot=0",
                            (json.dumps(task), user_id)
                        )
                        await _db.commit()

                return {
                    "slot": 0,
                    "task": task,
                    "cooldown_until": cooldown_until,
                    "on_cooldown": False,
                    "resets_at": _next_utc_midnight_ts(),
                }

            # New day — calculate streak
            if last_completed == yesterday:
                # Completed yesterday → streak continues
                new_streak = streak + 1
            else:
                # Missed a day (or first time) → reset streak
                new_streak = 0

            # Generate fresh goal for today
            task = generate_daily_goal(new_streak)

            await db.execute(
                "INSERT OR REPLACE INTO user_tasks(user_id,slot,task_data,assigned_at,cooldown_until) VALUES(?,0,?,?,0)",
                (user_id, json.dumps(task), now)
            )
            await db.execute(
                "INSERT OR REPLACE INTO daily_goal(user_id,streak,last_completed,last_issued,last_reset_date) VALUES(?,?,?,?,?)",
                (user_id, new_streak, last_completed, today, today)
            )
            await db.commit()

        return {
            "slot": 0,
            "task": task,
            "cooldown_until": 0,
            "on_cooldown": False,
            "resets_at": _next_utc_midnight_ts(),
        }

    # ── Slot management ───────────────────────────────────────────────────────

    async def _reset_regular_slots_for_user(self, user_id: str, now: float):
        """
        Wipe all regular task slots (1-6) for a user and mark today as reset.
        Must be called inside self._get_lock().
        This is called at UTC midnight so every slot gets a fresh task with no cooldown.
        """
        today = _utc_today()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM user_tasks WHERE user_id=? AND slot > 0",
                (user_id,)
            )
            # Upsert so new users get the row created too
            await db.execute(
                "INSERT INTO daily_goal(user_id, last_reset_date) VALUES(?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET last_reset_date=excluded.last_reset_date",
                (user_id, today)
            )
            await db.commit()
        logger.info(f"Midnight reset: wiped regular slots for user {user_id}")

    async def midnight_reset_all_users(self):
        """
        Called by the scheduled midnight loop in tasks_api.py.
        Resets regular slots (1-6) for every known user so they get fresh tasks
        and all cooldowns are cleared — regardless of whether they're online.
        """
        await self.ensure_ready()
        today = _utc_today()
        async with self._get_lock():
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT DISTINCT user_id FROM daily_goal") as cur:
                    users = [r["user_id"] for r in await cur.fetchall()]

            reset_count = 0
            for user_id in users:
                try:
                    await self._reset_regular_slots_for_user(user_id, time.time())
                    reset_count += 1
                except Exception as e:
                    logger.error(f"midnight_reset_all_users: failed for {user_id}: {e}")

        logger.info(f"midnight_reset_all_users: reset {reset_count} users for {today}")

    async def get_slots(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Return all task slots for a user.
        Slot 0 is always the Daily Goal (resets at UTC midnight).
        Slots 1-6 are regular tasks (also reset at UTC midnight).
        """
        await self.ensure_ready()
        now = time.time()
        today = _utc_today()
        async with self._get_lock():
            # ── UTC midnight reset for regular slots ──────────────────────────
            # Check if regular slots need to be wiped for today
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT last_reset_date FROM daily_goal WHERE user_id=?",
                    (user_id,)
                ) as cur:
                    reset_row = await cur.fetchone()
            last_reset = reset_row["last_reset_date"] if reset_row else ""
            if last_reset != today:
                await self._reset_regular_slots_for_user(user_id, now)

            # ── Slot 0: Daily Goal ────────────────────────────────────────────
            goal_slot = await self._get_or_refresh_daily_goal_slot(user_id, now)

            # ── Slots 1-4: Regular tasks ──────────────────────────────────────
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT slot, task_data, assigned_at, cooldown_until FROM user_tasks "
                    "WHERE user_id=? AND slot > 0 ORDER BY slot",
                    (user_id,)
                ) as cur:
                    rows = {r["slot"]: r for r in await cur.fetchall()}

            # Collect actions that are currently active (not on cooldown, not done)
            # so newly generated tasks avoid duplicating them.
            active_actions: List[str] = []
            for i in range(1, 7):
                row = rows.get(i)
                if row and row["cooldown_until"] <= now:
                    try:
                        t = json.loads(row["task_data"])
                        if not t.get("completed") and not t.get("dismissed") and t.get("action"):
                            active_actions.append(t["action"])
                    except Exception:
                        pass

            regular_slots = []
            for i in range(1, 7):
                row = rows.get(i)
                if row:
                    cooldown_until = row["cooldown_until"]
                    if cooldown_until > now:
                        regular_slots.append({
                            "slot": i,
                            "task": None,
                            "cooldown_until": cooldown_until,
                            "on_cooldown": True,
                            "seconds_remaining": max(0, int(cooldown_until - now)),
                        })
                        continue
                    task = json.loads(row["task_data"])
                    # Need a fresh task when:
                    #   • reward was claimed (4h cooldown just expired), OR
                    #   • slot was dismissed (1h cooldown just expired)
                    needs_new = (
                        (task.get("completed") and task.get("reward_claimed"))
                        or task.get("dismissed")
                    )
                    if needs_new:
                        # Exclude the old action plus all currently active actions
                        exclude = list(active_actions)
                        old_action = task.get("action")
                        if old_action and old_action not in exclude:
                            exclude.append(old_action)
                        task = generate_task(exclude_actions=exclude)
                        # Track this new action so subsequent slots in the same
                        # loop iteration don't duplicate it either.
                        if task.get("action"):
                            active_actions.append(task["action"])
                        async with aiosqlite.connect(self.db_path) as db:
                            await db.execute(
                                "INSERT OR REPLACE INTO user_tasks(user_id,slot,task_data,assigned_at,cooldown_until) VALUES(?,?,?,?,0)",
                                (user_id, i, json.dumps(task), now)
                            )
                            await db.commit()
                    regular_slots.append({
                        "slot": i,
                        "task": task,
                        "cooldown_until": 0,
                        "on_cooldown": False,
                        "seconds_remaining": 0,
                    })
                else:
                    # Brand-new slot — exclude already-active actions
                    task = generate_task(exclude_actions=list(active_actions))
                    if task.get("action"):
                        active_actions.append(task["action"])
                    async with aiosqlite.connect(self.db_path) as db:
                        await db.execute(
                            "INSERT OR REPLACE INTO user_tasks(user_id,slot,task_data,assigned_at,cooldown_until) VALUES(?,?,?,?,0)",
                            (user_id, i, json.dumps(task), now)
                        )
                        await db.commit()
                    regular_slots.append({
                        "slot": i,
                        "task": task,
                        "cooldown_until": 0,
                        "on_cooldown": False,
                        "seconds_remaining": 0,
                    })

        # Goal slot always first
        goal_slot["seconds_remaining"] = 0
        return [goal_slot] + regular_slots

    async def update_progress(self, user_id: str, action: str, meta: Optional[Dict] = None) -> List[int]:
        """
        Increment progress on matching regular tasks (slots 1-6).
        When a task reaches required, marks it completed but does NOT start the cooldown
        or deliver the reward — that happens when the user claims it.
        Returns list of slot indices that just completed (newly reached required).
        """
        await self.ensure_ready()
        now = time.time()
        completed_slots: List[int] = []

        async with self._get_lock():
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT slot, task_data, cooldown_until FROM user_tasks WHERE user_id=? AND slot > 0",
                    (user_id,)
                ) as cur:
                    rows = await cur.fetchall()

                for row in rows:
                    if row["cooldown_until"] > now:
                        continue
                    task = json.loads(row["task_data"])
                    # Skip if already completed (claimed or unclaimed)
                    if task.get("completed"):
                        continue
                    if task["action"] != action:
                        continue

                    if action == "rename" and meta:
                        expected = task.get("meta", {}).get("battle_action", "")
                        provided = meta.get("battle_action", "")
                        if expected and provided and expected.lower() != provided.lower():
                            continue

                    task["progress"] = min(task["progress"] + 1, task["required"])
                    if task["progress"] >= task["required"]:
                        task["completed"] = True
                        task["reward_claimed"] = False  # waiting for user to claim
                        completed_slots.append(row["slot"])
                        # No cooldown yet — cooldown starts on claim

                    await db.execute(
                        "UPDATE user_tasks SET task_data=? WHERE user_id=? AND slot=?",
                        (json.dumps(task), user_id, row["slot"])
                    )

                await db.commit()

        # NOTE: daily goal is NOT ticked here — it ticks when the user claims the reward
        return completed_slots

    async def update_progress_by(self, user_id: str, action: str, amount: int) -> List[int]:
        """
        Add `amount` progress to matching tasks (used for SS rounds/eliminations).
        Marks completed but does NOT deliver reward or start cooldown — user must claim.
        Returns list of slot indices that just completed.
        """
        if amount <= 0:
            return []
        await self.ensure_ready()
        now = time.time()
        completed_slots: List[int] = []

        async with self._get_lock():
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT slot, task_data, cooldown_until FROM user_tasks WHERE user_id=? AND slot > 0",
                    (user_id,)
                ) as cur:
                    rows = await cur.fetchall()

                for row in rows:
                    if row["cooldown_until"] > now:
                        continue
                    task = json.loads(row["task_data"])
                    if task.get("completed") or task["action"] != action:
                        continue

                    task["progress"] = min(task["progress"] + amount, task["required"])
                    if task["progress"] >= task["required"]:
                        task["completed"] = True
                        task["reward_claimed"] = False
                        completed_slots.append(row["slot"])
                        # No cooldown yet — starts on claim

                    await db.execute(
                        "UPDATE user_tasks SET task_data=? WHERE user_id=? AND slot=?",
                        (json.dumps(task), user_id, row["slot"])
                    )

                await db.commit()

        # Daily goal ticks on claim, not here
        return completed_slots

    async def _tick_daily_goal(self, user_id: str, now: float):
        """
        Increment the daily goal progress by 1 (called when a regular task is claimed).
        Must be called inside self._get_lock().
        Does NOT mark the goal completed or deliver its reward — user must claim that too.
        """
        today = _utc_today()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT task_data, cooldown_until FROM user_tasks WHERE user_id=? AND slot=0",
                (user_id,)
            ) as cur:
                row = await cur.fetchone()
            if not row:
                return

            task = json.loads(row["task_data"])
            # Only tick if it's today's goal and not already completed
            if task.get("completed") or not task.get("is_daily_goal"):
                return
            if task.get("meta", {}).get("utc_date") != today:
                return

            task["progress"] = min(task["progress"] + 1, task["required"])
            if task["progress"] >= task["required"]:
                task["completed"] = True
                task["reward_claimed"] = False  # user must claim the goal reward too

            await db.execute(
                "UPDATE user_tasks SET task_data=? WHERE user_id=? AND slot=0",
                (json.dumps(task), user_id)
            )
            await db.commit()

    async def claim_task(self, user_id: str, slot: int) -> Optional[Dict[str, Any]]:
        """
        Claim the reward for a completed task in the given slot.
        - Delivers the reward to the user's inventory
        - Marks reward_claimed = True
        - Starts the 4h cooldown
        - Ticks the daily goal bar
        Returns the reward dict on success, None if not claimable.
        """
        if slot < 1:
            return None
        await self.ensure_ready()
        now = time.time()

        async with self._get_lock():
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT task_data, cooldown_until FROM user_tasks WHERE user_id=? AND slot=?",
                    (user_id, slot)
                ) as cur:
                    row = await cur.fetchone()

                if not row:
                    return None

                task = json.loads(row["task_data"])
                if not task.get("completed"):
                    return None  # not done yet
                if task.get("reward_claimed"):
                    return None  # already claimed

                # Mark claimed and start cooldown
                task["reward_claimed"] = True
                cooldown_until = now + 4 * 3600

                await db.execute(
                    "UPDATE user_tasks SET task_data=?, cooldown_until=? WHERE user_id=? AND slot=?",
                    (json.dumps(task), cooldown_until, user_id, slot)
                )
                await db.commit()

            # Tick the daily goal bar now that this task is claimed
            await self._tick_daily_goal(user_id, now)

        return task.get("reward", {})

    async def claim_daily_goal(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Claim the daily goal reward.
        Returns the reward dict on success, None if not claimable.
        """
        await self.ensure_ready()
        async with self._get_lock():
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT task_data FROM user_tasks WHERE user_id=? AND slot=0",
                    (user_id,)
                ) as cur:
                    row = await cur.fetchone()

                if not row:
                    return None

                task = json.loads(row["task_data"])
                if not task.get("completed"):
                    return None
                if task.get("reward_delivered"):
                    return None  # already claimed

                task["reward_delivered"] = True
                await db.execute(
                    "UPDATE user_tasks SET task_data=? WHERE user_id=? AND slot=0",
                    (json.dumps(task), user_id)
                )
                # Record streak completion
                today = _utc_today()
                await db.execute(
                    "UPDATE daily_goal SET last_completed=? WHERE user_id=?",
                    (today, user_id)
                )
                await db.commit()

        return task.get("reward", {})

    async def dismiss_task(self, user_id: str, slot: int) -> bool:
        """
        Dismiss a regular task (slots 1-4) — sets 1h cooldown.
        The daily goal (slot 0) cannot be dismissed.
        """
        if slot == 0:
            return False  # Daily goal is not dismissable
        await self.ensure_ready()
        now = time.time()
        cooldown_until = now + 3600
        async with self._get_lock():
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO user_tasks(user_id,slot,task_data,assigned_at,cooldown_until) VALUES(?,?,?,?,?)",
                    (user_id, slot, json.dumps({"dismissed": True}), now, cooldown_until)
                )
                await db.commit()
        return True

    async def get_task_for_slot(self, user_id: str, slot: int) -> Optional[Dict[str, Any]]:
        """Get raw task data for a specific slot."""
        await self.ensure_ready()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT task_data, cooldown_until FROM user_tasks WHERE user_id=? AND slot=?",
                (user_id, slot)
            ) as cur:
                row = await cur.fetchone()
        if not row:
            return None
        return {"task": json.loads(row["task_data"]), "cooldown_until": row["cooldown_until"]}

    # ── DM preferences ────────────────────────────────────────────────────────

    async def get_dm_prefs(self, user_id: str) -> Dict[str, Any]:
        await self.ensure_ready()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT dm_enabled, dm_mode FROM task_dm_prefs WHERE user_id=?",
                (user_id,)
            ) as cur:
                row = await cur.fetchone()
        if not row:
            return {"dm_enabled": False, "dm_mode": "all"}
        return {"dm_enabled": bool(row["dm_enabled"]), "dm_mode": row["dm_mode"]}

    async def set_dm_prefs(self, user_id: str, dm_enabled: bool, dm_mode: str) -> bool:
        await self.ensure_ready()
        if dm_mode not in ("each", "all"):
            dm_mode = "all"
        async with self._get_lock():
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO task_dm_prefs(user_id,dm_enabled,dm_mode) VALUES(?,?,?)",
                    (user_id, int(dm_enabled), dm_mode)
                )
                await db.commit()
        return True

    async def mark_goal_reward_delivered(self, user_id: str):
        """Mark the daily goal reward as delivered so it isn't given twice."""
        await self.ensure_ready()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT task_data FROM user_tasks WHERE user_id=? AND slot=0",
                (user_id,)
            ) as cur:
                row = await cur.fetchone()
            if not row:
                return
            task = json.loads(row["task_data"])
            task["reward_delivered"] = True
            await db.execute(
                "UPDATE user_tasks SET task_data=? WHERE user_id=? AND slot=0",
                (json.dumps(task), user_id)
            )
            await db.commit()

    async def deliver_reward(self, user_id: str, reward: Dict[str, Any]) -> str:
        """Add reward (key or chest) to user's pet inventory. Returns message."""
        from Systems.Functions.user_data_manager import user_data_manager
        from Systems.Pets.Logic.pet_brain import LootCalculator

        pet = await user_data_manager.get_pet_data_async(user_id)
        if not pet:
            return "No pet found to receive reward."

        item_type = "Key" if reward["type"] == "key" else "Chest"
        item = {
            "name":  reward["item"],
            "type":  item_type,
            "count": reward.get("count", 1),
        }
        added, msg = await LootCalculator.add_item_to_inventory(int(user_id), item, pet)
        if added:
            return msg.strip() or f"Received {item['count']}x {item['name']}!"
        return f"Could not add {item['name']} to inventory."


tasks_db = TasksDB()

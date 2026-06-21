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
    # Pet care
    ("play",           "Play with your pet {n} time(s)",              (1, 3),  1),
    ("play",           "Play with your pet {n} time(s)",              (1, 3),  1),
    ("train",          "Train your pet {n} time(s)",                  (1, 3),  1),
    ("train",          "Train your pet {n} time(s)",                  (1, 3),  1),
    ("mission",        "Complete {n} mission(s)",                     (1, 2),  2),
    ("mission",        "Complete {n} mission(s)",                     (1, 2),  2),
    ("battle_npc",     "Win {n} NPC battle(s)",                       (1, 2),  2),
    ("battle_npc",     "Win {n} NPC battle(s)",                       (1, 2),  2),

    ("gift",           "Gift an item to another pet",                 (1, 1),  2),
    ("boss",           "Win a boss battle",                           (1, 1),  4),
    ("rename",         "Pet is tired of {action} — rename it",        (1, 1),  2),
    ("potion",         "Use {n} potion(s) on your pet",               (1, 2),  1),
    ("loot",           "Open {n} chest(s)",                           (1, 2),  2),
    ("equip",          "Equip {n} item(s) to your pet",               (1, 2),  1),
    ("consume",        "Consume {n} item(s)",                         (1, 2),  1),
    # Casino — existing
    ("buy_token",      "Buy {n} pet stock token(s)",                  (1, 3),  2),
    ("sell_token",     "Sell {n} pet stock token(s)",                 (1, 3),  2),
    ("play_slots",     "Play the slot machine {n} time(s)",           (1, 3),  2),
    ("play_keno",      "Play Mega Keno {n} time(s)",                  (1, 10), None),
    ("post_item",      "Post an item on the Item Board",              (1, 1),  1),
    ("coin_flip",      "Flip a coin {n} time(s)",                     (1, 5),  None),
    ("get_horoscope",  "Get your daily horoscope",                    (1, 1),  None),
    ("race_play",      "Race your pet {n} time(s)",                   (1, 5),  None),
    ("race_win",       "Win {n} race(s)",                             (1, 3),  None),
    ("ss_join",        "Join a Survivor Series game",                 (1, 1),  2),
    ("ss_eliminate",   "Eliminate {n} pet(s) in Survive (today)",     (1, 5),  None),
    ("ss_rounds",      "Survive {n} round(s) in Survive (today)",     (1, 10), None),
    ("buy_powerball",  "Buy a Powerball Ticket",                      (1, 1),  3),
    ("scratch_card",   "Scratch {n} Ticket(s)",                       (1, 5),  None),
    # Casino — newly tracked
    ("blackjack",      "Play {n} round(s) of Blackjack",              (1, 5),  2),
    ("holdem",         "Play {n} round(s) of Hold'em Poker",          (1, 5),  2),
    ("craps",          "Roll the dice {n} time(s) in Craps",          (1, 5),  2),
    ("wheel_of_pets",  "Spin the Wheel of Pets {n} time(s)",          (1, 5),  2),
    ("rps",            "Play Rock Paper Scissors {n} time(s)",        (1, 5),  1),
    # Dungeon & Colosseum
    ("dungeon_run",    "Complete {n} dungeon run(s)",                  (1, 3),  3),
    ("dungeon_win",    "Win {n} dungeon battle(s)",                    (1, 5),  3),
    ("colosseum",      "Enter the Colosseum {n} time(s)",              (1, 3),  3),
    # Fun pages
    ("wyr_weirdness",  "Answer {n} Weird Would You Rather(s)",         (1, 2),  2),
    ("wyr_moral",      "Answer {n} Moral Would You Rather(s)",         (1, 2),  2),
    ("wyr_pnw",        "Answer {n} PnW Would You Rather(s)",           (1, 2),  2),
    ("generator_lab",  "Generate in the Generator Lab {n} time(s)",    (1, 3),  2),
    ("fortune_cookie", "Open {n} fortune cookie(s)",                   (1, 3),  2),
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


# ── Weekly task reward tiers ───────────────────────────────────────────────────
# Weekly tasks use the same action pool but require 3-10× more completions
# and give much better rewards (chest2-chest4 range)
WEEKLY_REWARD_TIERS = {
    "low": [
        (40, {"type": "chest", "item": "chest2", "count": 1}),
        (35, {"type": "chest", "item": "chest3", "count": 1}),
        (20, {"type": "chest", "item": "chest3", "count": 2}),
        (5,  {"type": "chest", "item": "chest4", "count": 1}),
    ],
    "mid": [
        (30, {"type": "chest", "item": "chest3", "count": 1}),
        (35, {"type": "chest", "item": "chest3", "count": 2}),
        (25, {"type": "chest", "item": "chest4", "count": 1}),
        (10, {"type": "chest", "item": "chest4", "count": 2}),
    ],
    "high": [
        (20, {"type": "chest", "item": "chest3", "count": 2}),
        (40, {"type": "chest", "item": "chest4", "count": 1}),
        (30, {"type": "chest", "item": "chest4", "count": 2}),
        (10, {"type": "chest", "item": "chest4", "count": 3}),
    ],
}

# Weekly goal reward — always chest4 ×2 or ×3 depending on streak
WEEKLY_GOAL_REWARDS = [
    {"type": "chest", "item": "chest4", "count": 2},  # streak 0-1
    {"type": "chest", "item": "chest4", "count": 3},  # streak 2+
]

# Multiplier applied to daily task count_range for weekly tasks (min 3×, max 10×)
WEEKLY_TASK_MULTIPLIER = (3, 10)

# Number of weekly task slots (not counting the weekly goal which is slot 10)
WEEKLY_SLOTS = 6

# Weekly goal requires completing 10 weekly tasks (same cadence as daily goal)
WEEKLY_GOAL_REQUIRED = 10

# ── Monthly task reward tiers ──────────────────────────────────────────────────
# Monthly tasks use the same action pool but require 15-50× more completions
# and give the best rewards — chest4 ×2-6
MONTHLY_REWARD_TIERS = {
    "low": [
        (30, {"type": "chest", "item": "chest4", "count": 2}),
        (40, {"type": "chest", "item": "chest4", "count": 3}),
        (20, {"type": "chest", "item": "chest4", "count": 4}),
        (10, {"type": "chest", "item": "chest4", "count": 5}),
    ],
    "mid": [
        (20, {"type": "chest", "item": "chest4", "count": 3}),
        (35, {"type": "chest", "item": "chest4", "count": 4}),
        (30, {"type": "chest", "item": "chest4", "count": 5}),
        (15, {"type": "chest", "item": "chest4", "count": 6}),
    ],
    "high": [
        (15, {"type": "chest", "item": "chest4", "count": 4}),
        (30, {"type": "chest", "item": "chest4", "count": 5}),
        (35, {"type": "chest", "item": "chest4", "count": 6}),
        (20, {"type": "chest", "item": "chest4", "count": 7}),
    ],
}

# Monthly goal reward — escalates with streak
MONTHLY_GOAL_REWARDS = [
    {"type": "chest", "item": "chest4", "count": 5},   # streak 0
    {"type": "chest", "item": "chest4", "count": 7},   # streak 1+
    {"type": "chest", "item": "chest4", "count": 10},  # streak 3+
]

# Multiplier applied to daily task count_range for monthly tasks (min 15×, max 50×)
MONTHLY_TASK_MULTIPLIER = (15, 50)

# Number of monthly task slots (not counting the monthly goal which is slot 20)
MONTHLY_SLOTS = 6

# Monthly goal requires completing 10 monthly tasks
MONTHLY_GOAL_REQUIRED = 10

DISMISS_COOLDOWN_HOURS = {
    "daily": 1,
    "weekly": 6,
    "monthly": 24,
}

COMPLETION_COOLDOWN_HOURS = {
    "daily": 3,
    "weekly": 18,
    "monthly": 72,
}


def _hours_to_seconds(hours: int) -> int:
    return hours * 3600


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


def _single_reward(reward_type: str, item: str, count: int) -> Dict[str, Any]:
    return {"type": reward_type, "item": item, "count": count}


def _bundle_reward(reward_type: str, items: List[str], count: int) -> Dict[str, Any]:
    return {
        "type": "bundle",
        "items": [_single_reward(reward_type, item, count) for item in items],
    }


def _daily_task_reward() -> Dict[str, Any]:
    return _single_reward("key", random.choice(KEY_TYPES), random.randint(1, 3))


def _weekly_task_reward() -> Dict[str, Any]:
    return _single_reward("chest", random.choice(["chest1", "chest2"]), random.randint(1, 3))


def _monthly_task_reward() -> Dict[str, Any]:
    return _single_reward("chest", random.choice(["chest3", "chest4"]), random.randint(1, 3))


def _daily_goal_reward(streak: int) -> Dict[str, Any]:
    return _bundle_reward("key", KEY_TYPES, 5 + (2 * max(streak, 0)))


def _weekly_goal_reward(streak: int) -> Dict[str, Any]:
    return _bundle_reward("chest", ["chest1", "chest2"], 5 + (2 * max(streak, 0)))


def _monthly_goal_reward(streak: int) -> Dict[str, Any]:
    return _bundle_reward("chest", ["chest3", "chest4"], 5 + (2 * max(streak, 0)))


def _reward_items(reward: Dict[str, Any]) -> List[Dict[str, Any]]:
    if reward.get("type") == "bundle":
        return [item for item in reward.get("items", []) if item.get("item")]
    return [reward]


def _is_single_reward(reward: Dict[str, Any], reward_type: str, items: List[str]) -> bool:
    try:
        count = int(reward.get("count", 0))
    except (TypeError, ValueError):
        count = 0
    return (
        reward.get("type") == reward_type
        and reward.get("item") in items
        and 1 <= count <= 3
    )


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


def _utc_week_start() -> str:
    """Return the most recent Sunday (UTC) as YYYY-MM-DD string (weekly window starts Sunday)."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    # weekday(): Mon=0 … Sun=6
    days_since_sunday = (now.weekday() + 1) % 7
    sunday = now - timedelta(days=days_since_sunday)
    return sunday.strftime("%Y-%m-%d")


def _utc_next_sunday_ts() -> float:
    """Unix timestamp of the next Sunday 00:00 UTC (end of current weekly window)."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    days_since_sunday = (now.weekday() + 1) % 7
    next_sunday = now - timedelta(days=days_since_sunday) + timedelta(days=7)
    next_sunday = datetime(next_sunday.year, next_sunday.month, next_sunday.day, tzinfo=timezone.utc)
    return next_sunday.timestamp()


def generate_weekly_task(exclude_actions: Optional[List[str]] = None) -> Dict[str, Any]:
    """Generate a single weekly task with much larger requirements and better rewards."""
    pool = TASK_ACTIONS
    if exclude_actions:
        filtered = [t for t in TASK_ACTIONS if t[0] not in exclude_actions]
        if filtered:
            pool = filtered

    action_key, label_tmpl, count_range, tier = random.choice(pool)

    # Scale count range up significantly for weekly tasks
    low_mult  = WEEKLY_TASK_MULTIPLIER[0]
    high_mult = WEEKLY_TASK_MULTIPLIER[1]
    n_min = count_range[0] * low_mult
    n_max = count_range[1] * high_mult
    # Cap very large ranges at sensible weekly maximums per action type
    cap_map = {
        "play": 20, "train": 20, "mission": 15, "battle_npc": 15,
        "quest": 12, "boss": 5, "loot": 15, "equip": 15, "consume": 15,
        "potion": 15, "gift": 5, "rename": 3,
        "play_slots": 30, "play_keno": 50, "coin_flip": 40, "race_play": 30,
        "race_win": 20, "scratch_card": 25, "buy_powerball": 5,
        "buy_token": 20, "sell_token": 20, "post_item": 5,
        "ss_join": 5, "ss_eliminate": 20, "ss_rounds": 40,
        "blackjack": 30, "holdem": 30, "craps": 30,
        "wheel_of_pets": 30, "rps": 30,
        "dungeon_run": 15, "dungeon_win": 20, "colosseum": 15,
        "wyr_weirdness": 10, "wyr_moral": 10, "wyr_pnw": 10,
        "generator_lab": 30, "fortune_cookie": 30,
    }
    cap = cap_map.get(action_key, n_max)
    n_max = min(n_max, cap)
    n_min = min(n_min, n_max)
    n = random.randint(n_min, n_max)

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

    reward = _weekly_task_reward()

    return {
        "action":      action_key,
        "label":       label,
        "required":    n,
        "progress":    0,
        "meta":        meta,
        "reward":      reward,
        "completed":   False,
        "is_weekly":   True,
        "week_start":  _utc_week_start(),
    }


def generate_weekly_goal(weekly_streak: int) -> Dict[str, Any]:
    """Generate the Weekly Goal task — complete 10 weekly tasks."""
    reward = _weekly_goal_reward(weekly_streak)
    return {
        "action":         "weekly_goal",
        "label":          "Complete 10 Weekly Tasks",
        "required":       WEEKLY_GOAL_REQUIRED,
        "progress":       0,
        "meta":           {"weekly_streak": weekly_streak, "week_start": _utc_week_start()},
        "reward":         reward,
        "completed":      False,
        "is_weekly_goal": True,
        "week_start":     _utc_week_start(),
    }


def _utc_month_start() -> str:
    """Return the first day of the current UTC month as YYYY-MM-DD."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-01")


def _utc_next_month_ts() -> float:
    """Unix timestamp of the first day of next UTC month at 00:00."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
    return next_month.timestamp()


def _prev_month_start(from_month_start: str) -> str:
    """Return the YYYY-MM-01 string for the month before from_month_start."""
    dt = datetime.strptime(from_month_start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if dt.month == 1:
        prev = datetime(dt.year - 1, 12, 1, tzinfo=timezone.utc)
    else:
        prev = datetime(dt.year, dt.month - 1, 1, tzinfo=timezone.utc)
    return prev.strftime("%Y-%m-%d")


def generate_monthly_task(exclude_actions: Optional[List[str]] = None) -> Dict[str, Any]:
    """Generate a single monthly task — very high requirements, best rewards."""
    pool = TASK_ACTIONS
    if exclude_actions:
        filtered = [t for t in TASK_ACTIONS if t[0] not in exclude_actions]
        if filtered:
            pool = filtered

    action_key, label_tmpl, count_range, tier = random.choice(pool)

    low_mult  = MONTHLY_TASK_MULTIPLIER[0]
    high_mult = MONTHLY_TASK_MULTIPLIER[1]
    n_min = count_range[0] * low_mult
    n_max = count_range[1] * high_mult
    cap_map = {
        "play": 80, "train": 80, "mission": 60, "battle_npc": 60,
        "boss": 15, "loot": 60, "equip": 60, "consume": 60,
        "potion": 60, "gift": 20, "rename": 10,
        "play_slots": 120, "play_keno": 150, "coin_flip": 150, "race_play": 120,
        "race_win": 80, "scratch_card": 100, "buy_powerball": 20,
        "buy_token": 80, "sell_token": 80, "post_item": 20,
        "ss_join": 15, "ss_eliminate": 80, "ss_rounds": 150,
        "blackjack": 120, "holdem": 120, "craps": 120,
        "wheel_of_pets": 120, "rps": 120,
        "dungeon_run": 50, "dungeon_win": 80, "colosseum": 50,
        "wyr_weirdness": 40, "wyr_moral": 40, "wyr_pnw": 40,
        "generator_lab": 120, "fortune_cookie": 120,
    }
    cap = cap_map.get(action_key, n_max)
    n_max = min(n_max, cap)
    n_min = min(n_min, n_max)
    n = random.randint(n_min, n_max)

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

    reward = _monthly_task_reward()

    return {
        "action":       action_key,
        "label":        label,
        "required":     n,
        "progress":     0,
        "meta":         meta,
        "reward":       reward,
        "completed":    False,
        "is_monthly":   True,
        "month_start":  _utc_month_start(),
    }


def generate_monthly_goal(monthly_streak: int) -> Dict[str, Any]:
    """Generate the Monthly Goal task — complete 10 monthly tasks."""
    reward = _monthly_goal_reward(monthly_streak)
    return {
        "action":          "monthly_goal",
        "label":           "Complete 10 Monthly Tasks",
        "required":        MONTHLY_GOAL_REQUIRED,
        "progress":        0,
        "meta":            {"monthly_streak": monthly_streak, "month_start": _utc_month_start()},
        "reward":          reward,
        "completed":       False,
        "is_monthly_goal": True,
        "month_start":     _utc_month_start(),
    }


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

    reward = _daily_task_reward()

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
        "reward":    _daily_goal_reward(streak),
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
            # Weekly tasks
            await db.execute("""
                CREATE TABLE IF NOT EXISTS weekly_tasks (
                    user_id        TEXT NOT NULL,
                    slot           INTEGER NOT NULL,
                    task_data      TEXT NOT NULL,
                    assigned_at    REAL NOT NULL DEFAULT 0,
                    cooldown_until REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, slot)
                )
            """)
            # Weekly goal streak tracking
            await db.execute("""
                CREATE TABLE IF NOT EXISTS weekly_goal (
                    user_id          TEXT PRIMARY KEY,
                    streak           INTEGER NOT NULL DEFAULT 0,
                    last_completed   TEXT NOT NULL DEFAULT '',
                    last_week_start  TEXT NOT NULL DEFAULT ''
                )
            """)
            # Monthly tasks
            await db.execute("""
                CREATE TABLE IF NOT EXISTS monthly_tasks (
                    user_id        TEXT NOT NULL,
                    slot           INTEGER NOT NULL,
                    task_data      TEXT NOT NULL,
                    assigned_at    REAL NOT NULL DEFAULT 0,
                    cooldown_until REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, slot)
                )
            """)
            # Monthly goal streak tracking
            await db.execute("""
                CREATE TABLE IF NOT EXISTS monthly_goal (
                    user_id           TEXT PRIMARY KEY,
                    streak            INTEGER NOT NULL DEFAULT 0,
                    last_completed    TEXT NOT NULL DEFAULT '',
                    last_month_start  TEXT NOT NULL DEFAULT ''
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user ON user_tasks(user_id)")
            await db.commit()
        logger.info("Tasks tables ready")
        await self._migrate_db()
        await self._migrate_goal_required()
        await self._migrate_reward_rules()

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
                # Create weekly tables if missing
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS weekly_tasks (
                        user_id        TEXT NOT NULL,
                        slot           INTEGER NOT NULL,
                        task_data      TEXT NOT NULL,
                        assigned_at    REAL NOT NULL DEFAULT 0,
                        PRIMARY KEY (user_id, slot)
                    )
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS weekly_goal (
                        user_id          TEXT PRIMARY KEY,
                        streak           INTEGER NOT NULL DEFAULT 0,
                        last_completed   TEXT NOT NULL DEFAULT '',
                        last_week_start  TEXT NOT NULL DEFAULT ''
                    )
                """)
                # Create monthly tables if missing
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS monthly_tasks (
                        user_id        TEXT NOT NULL,
                        slot           INTEGER NOT NULL,
                        task_data      TEXT NOT NULL,
                        assigned_at    REAL NOT NULL DEFAULT 0,
                        PRIMARY KEY (user_id, slot)
                    )
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS monthly_goal (
                        user_id           TEXT PRIMARY KEY,
                        streak            INTEGER NOT NULL DEFAULT 0,
                        last_completed    TEXT NOT NULL DEFAULT '',
                        last_month_start  TEXT NOT NULL DEFAULT ''
                    )
                """)
                await db.commit()
                async with db.execute("PRAGMA table_info(weekly_tasks)") as cur:
                    cols = {row[1] for row in await cur.fetchall()}
                if "cooldown_until" not in cols:
                    await db.execute(
                        "ALTER TABLE weekly_tasks ADD COLUMN cooldown_until REAL NOT NULL DEFAULT 0"
                    )
                    await db.commit()
                    logger.info("_migrate_db: added cooldown_until column to weekly_tasks")

                async with db.execute("PRAGMA table_info(monthly_tasks)") as cur:
                    cols = {row[1] for row in await cur.fetchall()}
                if "cooldown_until" not in cols:
                    await db.execute(
                        "ALTER TABLE monthly_tasks ADD COLUMN cooldown_until REAL NOT NULL DEFAULT 0"
                    )
                    await db.commit()
                    logger.info("_migrate_db: added cooldown_until column to monthly_tasks")
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

    async def _migrate_reward_rules(self):
        """
        Bring existing stored task rewards onto the current reward table.
        Regular-task rewards are only rerolled when they are outside the new
        allowed pool; goal rewards are deterministic from their current streak.
        """
        async def patch_table(table: str, goal_slot: int, regular_kind: str):
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(f"SELECT user_id, slot, task_data FROM {table}") as cur:
                    rows = await cur.fetchall()

                patched = 0
                for row in rows:
                    task = json.loads(row["task_data"])
                    if task.get("dismissed"):
                        continue

                    reward = task.get("reward", {})
                    slot = row["slot"]
                    if slot == goal_slot:
                        if regular_kind == "daily":
                            task["reward"] = _daily_goal_reward(int(task.get("meta", {}).get("streak", 0)))
                        elif regular_kind == "weekly":
                            task["reward"] = _weekly_goal_reward(int(task.get("meta", {}).get("weekly_streak", 0)))
                        else:
                            task["reward"] = _monthly_goal_reward(int(task.get("meta", {}).get("monthly_streak", 0)))
                    elif task.get("reward_claimed"):
                        continue
                    elif regular_kind == "daily":
                        if _is_single_reward(reward, "key", KEY_TYPES):
                            continue
                        task["reward"] = _daily_task_reward()
                    elif regular_kind == "weekly":
                        if _is_single_reward(reward, "chest", ["chest1", "chest2"]):
                            continue
                        task["reward"] = _weekly_task_reward()
                    else:
                        if _is_single_reward(reward, "chest", ["chest3", "chest4"]):
                            continue
                        task["reward"] = _monthly_task_reward()

                    await db.execute(
                        f"UPDATE {table} SET task_data=? WHERE user_id=? AND slot=?",
                        (json.dumps(task), row["user_id"], slot)
                    )
                    patched += 1

                if patched:
                    await db.commit()
                    logger.info(f"_migrate_reward_rules: patched {patched} row(s) in {table}")

        try:
            await patch_table("user_tasks", 0, "daily")
            await patch_table("weekly_tasks", 10, "weekly")
            await patch_table("monthly_tasks", 20, "monthly")
        except Exception as e:
            logger.warning(f"_migrate_reward_rules failed (non-fatal): {e}")

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
                    #   • slot was dismissed and its cooldown just expired
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
                cooldown_until = now + _hours_to_seconds(COMPLETION_COOLDOWN_HOURS["daily"])

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
        Dismiss a regular task (slots 1-6) and starts the daily dismissal cooldown.
        The daily goal (slot 0) cannot be dismissed.
        """
        if slot == 0:
            return False  # Daily goal is not dismissable
        await self.ensure_ready()
        now = time.time()
        cooldown_until = now + _hours_to_seconds(DISMISS_COOLDOWN_HOURS["daily"])
        async with self._get_lock():
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO user_tasks(user_id,slot,task_data,assigned_at,cooldown_until) VALUES(?,?,?,?,?)",
                    (user_id, slot, json.dumps({"dismissed": True}), now, cooldown_until)
                )
                await db.commit()
        return True

    async def dismiss_weekly_task(self, user_id: str, slot: int) -> bool:
        """
        Dismiss a weekly task and starts the weekly dismissal cooldown.
        """
        if not (11 <= slot < 11 + WEEKLY_SLOTS):
            return False
        await self.ensure_ready()
        now = time.time()
        cooldown_until = now + _hours_to_seconds(DISMISS_COOLDOWN_HOURS["weekly"])
        async with self._get_lock():
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO weekly_tasks(user_id,slot,task_data,assigned_at,cooldown_until) VALUES(?,?,?,?,?)",
                    (user_id, slot, json.dumps({"dismissed": True}), now, cooldown_until)
                )
                await db.commit()
        return True

    async def dismiss_monthly_task(self, user_id: str, slot: int) -> bool:
        """
        Dismiss a monthly task and starts the monthly dismissal cooldown.
        """
        if not (21 <= slot < 21 + MONTHLY_SLOTS):
            return False
        await self.ensure_ready()
        now = time.time()
        cooldown_until = now + _hours_to_seconds(DISMISS_COOLDOWN_HOURS["monthly"])
        async with self._get_lock():
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO monthly_tasks(user_id,slot,task_data,assigned_at,cooldown_until) VALUES(?,?,?,?,?)",
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

    # ── Weekly task helpers ───────────────────────────────────────────────────

    async def get_weekly_slots(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Return all weekly task slots for a user (slots 10=goal, 11-13=tasks).
        Weekly window runs Sun–Sat UTC. If it's a new week, generate fresh tasks.
        """
        await self.ensure_ready()
        now = time.time()
        week_start = _utc_week_start()

        async with self._get_lock():
            # ── Load or create weekly goal row ────────────────────────────────
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT streak, last_completed, last_week_start FROM weekly_goal WHERE user_id=?",
                    (user_id,)
                ) as cur:
                    wg_row = await cur.fetchone()

            if wg_row:
                weekly_streak = wg_row["streak"]
                last_week_start = wg_row["last_week_start"]
                last_completed_week = wg_row["last_completed"]
            else:
                weekly_streak = 0
                last_week_start = ""
                last_completed_week = ""
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        "INSERT OR IGNORE INTO weekly_goal(user_id,streak,last_completed,last_week_start) VALUES(?,0,'','')",
                        (user_id,)
                    )
                    await db.commit()

            # Check if we need to reset (new week)
            is_new_week = last_week_start != week_start

            if is_new_week:
                # Calculate new streak: did they complete the goal last week?
                # The previous week started 7 days before the current week_start
                from datetime import timedelta
                prev_week_dt = datetime.strptime(week_start, "%Y-%m-%d").replace(tzinfo=timezone.utc) - timedelta(days=7)
                prev_week_start = prev_week_dt.strftime("%Y-%m-%d")
                if last_completed_week == prev_week_start:
                    new_streak = weekly_streak + 1
                else:
                    new_streak = 0
                weekly_streak = new_streak

                # Wipe old weekly tasks
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute("DELETE FROM weekly_tasks WHERE user_id=?", (user_id,))
                    await db.execute(
                        "INSERT OR REPLACE INTO weekly_goal(user_id,streak,last_completed,last_week_start) VALUES(?,?,?,?)",
                        (user_id, new_streak, last_completed_week, week_start)
                    )
                    await db.commit()

            # ── Load existing weekly tasks ────────────────────────────────────
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT slot, task_data, assigned_at, cooldown_until FROM weekly_tasks WHERE user_id=? ORDER BY slot",
                    (user_id,)
                ) as cur:
                    rows = {r["slot"]: r for r in await cur.fetchall()}

            # Slot 10 = weekly goal
            if 10 not in rows:
                goal_task = generate_weekly_goal(weekly_streak)
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        "INSERT OR REPLACE INTO weekly_tasks(user_id,slot,task_data,assigned_at,cooldown_until) VALUES(?,10,?,?,0)",
                        (user_id, json.dumps(goal_task), now)
                    )
                    await db.commit()
                goal_slot = {"slot": 10, "task": goal_task, "resets_at": _utc_next_sunday_ts()}
            else:
                task = json.loads(rows[10]["task_data"])
                goal_slot = {"slot": 10, "task": task, "resets_at": _utc_next_sunday_ts()}

            # Slots 11-16 = weekly tasks
            weekly_slots = [goal_slot]
            active_actions: List[str] = []
            for i in range(11, 11 + WEEKLY_SLOTS):
                row = rows.get(i)
                if row:
                    cooldown_until = row["cooldown_until"]
                    if cooldown_until > now:
                        weekly_slots.append({
                            "slot": i,
                            "task": None,
                            "cooldown_until": cooldown_until,
                            "on_cooldown": True,
                            "seconds_remaining": max(0, int(cooldown_until - now)),
                        })
                        continue

                    task = json.loads(row["task_data"])
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
                        task = generate_weekly_task(exclude_actions=exclude)
                        # Track this new action so subsequent slots in the same
                        # loop iteration don't duplicate it either.
                        if task.get("action"):
                            active_actions.append(task["action"])
                        async with aiosqlite.connect(self.db_path) as db:
                            await db.execute(
                                "INSERT OR REPLACE INTO weekly_tasks(user_id,slot,task_data,assigned_at,cooldown_until) VALUES(?,?,?,?,0)",
                                (user_id, i, json.dumps(task), now)
                            )
                            await db.commit()

                    if task.get("action") and not needs_new:
                        active_actions.append(task["action"])

                    weekly_slots.append({
                        "slot": i,
                        "task": task,
                        "cooldown_until": 0,
                        "on_cooldown": False,
                        "seconds_remaining": 0,
                        "resets_at": _utc_next_sunday_ts(),
                    })
                else:
                    # Brand-new slot — exclude already-active actions
                    task = generate_weekly_task(exclude_actions=list(active_actions))
                    if task.get("action"):
                        active_actions.append(task["action"])
                    async with aiosqlite.connect(self.db_path) as db:
                        await db.execute(
                            "INSERT OR REPLACE INTO weekly_tasks(user_id,slot,task_data,assigned_at,cooldown_until) VALUES(?,?,?,?,0)",
                            (user_id, i, json.dumps(task), now)
                        )
                        await db.commit()
                    weekly_slots.append({
                        "slot": i,
                        "task": task,
                        "cooldown_until": 0,
                        "on_cooldown": False,
                        "seconds_remaining": 0,
                        "resets_at": _utc_next_sunday_ts(),
                    })

        return weekly_slots

    async def update_weekly_progress(self, user_id: str, action: str, meta: Optional[Dict] = None) -> List[int]:
        """
        Increment progress on matching weekly tasks.
        Returns list of slot indices that just completed.
        """
        await self.ensure_ready()
        now = time.time()
        completed_slots: List[int] = []

        async with self._get_lock():
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT slot, task_data, cooldown_until FROM weekly_tasks WHERE user_id=? AND slot > 10",
                    (user_id,)
                ) as cur:
                    rows = await cur.fetchall()

                for row in rows:
                    if row["cooldown_until"] > now:
                        continue
                    task = json.loads(row["task_data"])
                    if task.get("completed"):
                        continue
                    if task.get("action") != action:
                        continue
                    if action == "rename" and meta:
                        expected = task.get("meta", {}).get("battle_action", "")
                        provided = meta.get("battle_action", "")
                        if expected and provided and expected.lower() != provided.lower():
                            continue

                    task["progress"] = min(task["progress"] + 1, task["required"])
                    if task["progress"] >= task["required"]:
                        task["completed"] = True
                        task["reward_claimed"] = False
                        completed_slots.append(row["slot"])

                    await db.execute(
                        "UPDATE weekly_tasks SET task_data=? WHERE user_id=? AND slot=?",
                        (json.dumps(task), user_id, row["slot"])
                    )

                await db.commit()

        return completed_slots

    async def update_weekly_progress_by(self, user_id: str, action: str, amount: int, meta: Optional[Dict] = None) -> List[int]:
        """Add amount progress to matching weekly tasks. Returns completed slot indices."""
        if amount <= 0:
            return []
        await self.ensure_ready()
        now = time.time()
        completed_slots: List[int] = []

        async with self._get_lock():
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT slot, task_data, cooldown_until FROM weekly_tasks WHERE user_id=? AND slot > 10",
                    (user_id,)
                ) as cur:
                    rows = await cur.fetchall()

                for row in rows:
                    if row["cooldown_until"] > now:
                        continue
                    task = json.loads(row["task_data"])
                    if task.get("completed") or task.get("action") != action:
                        continue
                    if action == "rename" and meta:
                        expected = task.get("meta", {}).get("battle_action", "")
                        provided = meta.get("battle_action", "")
                        if expected and provided and expected.lower() != provided.lower():
                            continue

                    task["progress"] = min(task["progress"] + amount, task["required"])
                    if task["progress"] >= task["required"]:
                        task["completed"] = True
                        task["reward_claimed"] = False
                        completed_slots.append(row["slot"])

                    await db.execute(
                        "UPDATE weekly_tasks SET task_data=? WHERE user_id=? AND slot=?",
                        (json.dumps(task), user_id, row["slot"])
                    )

                await db.commit()

        return completed_slots

    async def _tick_weekly_goal(self, user_id: str):
        """Increment weekly goal progress when a weekly task is claimed. Must be in lock."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT task_data FROM weekly_tasks WHERE user_id=? AND slot=10",
                (user_id,)
            ) as cur:
                row = await cur.fetchone()
            if not row:
                return
            task = json.loads(row["task_data"])
            if task.get("completed") or not task.get("is_weekly_goal"):
                return
            if task.get("meta", {}).get("week_start") != _utc_week_start():
                return
            task["progress"] = min(task["progress"] + 1, task["required"])
            if task["progress"] >= task["required"]:
                task["completed"] = True
                task["reward_claimed"] = False
            await db.execute(
                "UPDATE weekly_tasks SET task_data=? WHERE user_id=? AND slot=10",
                (json.dumps(task), user_id)
            )
            await db.commit()

    async def claim_weekly_task(self, user_id: str, slot: int) -> Optional[Dict[str, Any]]:
        """
        Claim a completed weekly task reward (slots 11-16, 6 slots).
        Ticks the weekly goal. Returns reward dict or None.
        """
        if not (11 <= slot < 11 + WEEKLY_SLOTS):
            return None
        await self.ensure_ready()
        now = time.time()

        async with self._get_lock():
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT task_data FROM weekly_tasks WHERE user_id=? AND slot=?",
                    (user_id, slot)
                ) as cur:
                    row = await cur.fetchone()
                if not row:
                    return None
                task = json.loads(row["task_data"])
                if not task.get("completed") or task.get("reward_claimed"):
                    return None

                task["reward_claimed"] = True
                cooldown_until = now + _hours_to_seconds(COMPLETION_COOLDOWN_HOURS["weekly"])

                await db.execute(
                    "UPDATE weekly_tasks SET task_data=?, cooldown_until=? WHERE user_id=? AND slot=?",
                    (json.dumps(task), cooldown_until, user_id, slot)
                )
                await db.commit()

            await self._tick_weekly_goal(user_id)

        return task.get("reward", {})

    async def claim_weekly_goal(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Claim the weekly goal reward (slot 10) once all 3 weekly tasks are claimed.
        Returns reward dict or None.
        """
        await self.ensure_ready()
        async with self._get_lock():
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT task_data FROM weekly_tasks WHERE user_id=? AND slot=10",
                    (user_id,)
                ) as cur:
                    row = await cur.fetchone()
                if not row:
                    return None
                task = json.loads(row["task_data"])
                if not task.get("completed") or task.get("reward_delivered"):
                    return None
                task["reward_delivered"] = True
                await db.execute(
                    "UPDATE weekly_tasks SET task_data=? WHERE user_id=? AND slot=10",
                    (json.dumps(task), user_id)
                )
                # Record weekly streak
                week_start = _utc_week_start()
                await db.execute(
                    "UPDATE weekly_goal SET last_completed=? WHERE user_id=?",
                    (week_start, user_id)
                )
                await db.commit()

        return task.get("reward", {})

    async def weekly_reset_all_users(self):
        """
        Called at Sunday 00:00 UTC. Wipes all weekly task rows so every user
        gets fresh weekly tasks on their next visit.
        """
        await self.ensure_ready()
        async with self._get_lock():
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM weekly_tasks")
                await db.commit()
        logger.info("weekly_reset_all_users: wiped all weekly task rows")

    # ── Monthly task helpers ───────────────────────────────────────────────────

    async def get_monthly_slots(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Return all monthly task slots for a user (slot 20=goal, 21-26=tasks).
        Monthly window runs from the 1st of each UTC month.
        """
        await self.ensure_ready()
        now = time.time()
        month_start = _utc_month_start()

        async with self._get_lock():
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT streak, last_completed, last_month_start FROM monthly_goal WHERE user_id=?",
                    (user_id,)
                ) as cur:
                    mg_row = await cur.fetchone()

            if mg_row:
                monthly_streak    = mg_row["streak"]
                last_month_start  = mg_row["last_month_start"]
                last_completed_mo = mg_row["last_completed"]
            else:
                monthly_streak    = 0
                last_month_start  = ""
                last_completed_mo = ""
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        "INSERT OR IGNORE INTO monthly_goal(user_id,streak,last_completed,last_month_start) VALUES(?,0,'','')",
                        (user_id,)
                    )
                    await db.commit()

            is_new_month = last_month_start != month_start

            if is_new_month:
                prev_month = _prev_month_start(month_start)
                if last_completed_mo == prev_month:
                    new_streak = monthly_streak + 1
                else:
                    new_streak = 0
                monthly_streak = new_streak
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute("DELETE FROM monthly_tasks WHERE user_id=?", (user_id,))
                    await db.execute(
                        "INSERT OR REPLACE INTO monthly_goal(user_id,streak,last_completed,last_month_start) VALUES(?,?,?,?)",
                        (user_id, new_streak, last_completed_mo, month_start)
                    )
                    await db.commit()

            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT slot, task_data, assigned_at, cooldown_until FROM monthly_tasks WHERE user_id=? ORDER BY slot",
                    (user_id,)
                ) as cur:
                    rows = {r["slot"]: r for r in await cur.fetchall()}

            # Slot 20 = monthly goal
            if 20 not in rows:
                goal_task = generate_monthly_goal(monthly_streak)
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        "INSERT OR REPLACE INTO monthly_tasks(user_id,slot,task_data,assigned_at,cooldown_until) VALUES(?,20,?,?,0)",
                        (user_id, json.dumps(goal_task), now)
                    )
                    await db.commit()
                goal_slot = {"slot": 20, "task": goal_task, "resets_at": _utc_next_month_ts()}
            else:
                task = json.loads(rows[20]["task_data"])
                goal_slot = {"slot": 20, "task": task, "resets_at": _utc_next_month_ts()}

            # Slots 21-26 = monthly tasks
            monthly_slots = [goal_slot]
            active_actions: List[str] = []
            for i in range(21, 21 + MONTHLY_SLOTS):
                row = rows.get(i)
                if row:
                    cooldown_until = row["cooldown_until"]
                    if cooldown_until > now:
                        monthly_slots.append({
                            "slot": i,
                            "task": None,
                            "cooldown_until": cooldown_until,
                            "on_cooldown": True,
                            "seconds_remaining": max(0, int(cooldown_until - now)),
                        })
                        continue

                    task = json.loads(row["task_data"])
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
                        task = generate_monthly_task(exclude_actions=exclude)
                        # Track this new action so subsequent slots in the same
                        # loop iteration don't duplicate it either.
                        if task.get("action"):
                            active_actions.append(task["action"])
                        async with aiosqlite.connect(self.db_path) as db:
                            await db.execute(
                                "INSERT OR REPLACE INTO monthly_tasks(user_id,slot,task_data,assigned_at,cooldown_until) VALUES(?,?,?,?,0)",
                                (user_id, i, json.dumps(task), now)
                            )
                            await db.commit()

                    if task.get("action") and not needs_new:
                        active_actions.append(task["action"])

                    monthly_slots.append({
                        "slot": i,
                        "task": task,
                        "cooldown_until": 0,
                        "on_cooldown": False,
                        "seconds_remaining": 0,
                        "resets_at": _utc_next_month_ts(),
                    })
                else:
                    # Brand-new slot — exclude already-active actions
                    task = generate_monthly_task(exclude_actions=list(active_actions))
                    if task.get("action"):
                        active_actions.append(task["action"])
                    async with aiosqlite.connect(self.db_path) as db:
                        await db.execute(
                            "INSERT OR REPLACE INTO monthly_tasks(user_id,slot,task_data,assigned_at,cooldown_until) VALUES(?,?,?,?,0)",
                            (user_id, i, json.dumps(task), now)
                        )
                        await db.commit()
                    monthly_slots.append({
                        "slot": i,
                        "task": task,
                        "cooldown_until": 0,
                        "on_cooldown": False,
                        "seconds_remaining": 0,
                        "resets_at": _utc_next_month_ts(),
                    })

        return monthly_slots

    async def update_monthly_progress(self, user_id: str, action: str, meta: Optional[Dict] = None) -> List[int]:
        """Increment progress on matching monthly tasks. Returns completed slot indices."""
        await self.ensure_ready()
        now = time.time()
        completed_slots: List[int] = []

        async with self._get_lock():
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT slot, task_data, cooldown_until FROM monthly_tasks WHERE user_id=? AND slot > 20",
                    (user_id,)
                ) as cur:
                    rows = await cur.fetchall()

                for row in rows:
                    if row["cooldown_until"] > now:
                        continue
                    task = json.loads(row["task_data"])
                    if task.get("completed") or task.get("action") != action:
                        continue
                    if action == "rename" and meta:
                        expected = task.get("meta", {}).get("battle_action", "")
                        provided = meta.get("battle_action", "")
                        if expected and provided and expected.lower() != provided.lower():
                            continue
                    task["progress"] = min(task["progress"] + 1, task["required"])
                    if task["progress"] >= task["required"]:
                        task["completed"] = True
                        task["reward_claimed"] = False
                        completed_slots.append(row["slot"])
                    await db.execute(
                        "UPDATE monthly_tasks SET task_data=? WHERE user_id=? AND slot=?",
                        (json.dumps(task), user_id, row["slot"])
                    )
                await db.commit()

        return completed_slots

    async def update_monthly_progress_by(self, user_id: str, action: str, amount: int, meta: Optional[Dict] = None) -> List[int]:
        """Add amount progress to matching monthly tasks. Returns completed slot indices."""
        if amount <= 0:
            return []
        await self.ensure_ready()
        now = time.time()
        completed_slots: List[int] = []

        async with self._get_lock():
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT slot, task_data, cooldown_until FROM monthly_tasks WHERE user_id=? AND slot > 20",
                    (user_id,)
                ) as cur:
                    rows = await cur.fetchall()

                for row in rows:
                    if row["cooldown_until"] > now:
                        continue
                    task = json.loads(row["task_data"])
                    if task.get("completed") or task.get("action") != action:
                        continue
                    if action == "rename" and meta:
                        expected = task.get("meta", {}).get("battle_action", "")
                        provided = meta.get("battle_action", "")
                        if expected and provided and expected.lower() != provided.lower():
                            continue

                    task["progress"] = min(task["progress"] + amount, task["required"])
                    if task["progress"] >= task["required"]:
                        task["completed"] = True
                        task["reward_claimed"] = False
                        completed_slots.append(row["slot"])

                    await db.execute(
                        "UPDATE monthly_tasks SET task_data=? WHERE user_id=? AND slot=?",
                        (json.dumps(task), user_id, row["slot"])
                    )

                await db.commit()

        return completed_slots

    async def _tick_monthly_goal(self, user_id: str):
        """Increment monthly goal progress when a monthly task is claimed. Must be in lock."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT task_data FROM monthly_tasks WHERE user_id=? AND slot=20",
                (user_id,)
            ) as cur:
                row = await cur.fetchone()
            if not row:
                return
            task = json.loads(row["task_data"])
            if task.get("completed") or not task.get("is_monthly_goal"):
                return
            if task.get("meta", {}).get("month_start") != _utc_month_start():
                return
            task["progress"] = min(task["progress"] + 1, task["required"])
            if task["progress"] >= task["required"]:
                task["completed"] = True
                task["reward_claimed"] = False
            await db.execute(
                "UPDATE monthly_tasks SET task_data=? WHERE user_id=? AND slot=20",
                (json.dumps(task), user_id)
            )
            await db.commit()

    async def claim_monthly_task(self, user_id: str, slot: int) -> Optional[Dict[str, Any]]:
        """Claim a completed monthly task reward (slots 21-26). Returns reward dict or None."""
        if not (21 <= slot < 21 + MONTHLY_SLOTS):
            return None
        await self.ensure_ready()
        now = time.time()

        async with self._get_lock():
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT task_data FROM monthly_tasks WHERE user_id=? AND slot=?",
                    (user_id, slot)
                ) as cur:
                    row = await cur.fetchone()
                if not row:
                    return None
                task = json.loads(row["task_data"])
                if not task.get("completed") or task.get("reward_claimed"):
                    return None

                task["reward_claimed"] = True
                cooldown_until = now + _hours_to_seconds(COMPLETION_COOLDOWN_HOURS["monthly"])

                await db.execute(
                    "UPDATE monthly_tasks SET task_data=?, cooldown_until=? WHERE user_id=? AND slot=?",
                    (json.dumps(task), cooldown_until, user_id, slot)
                )
                await db.commit()
            await self._tick_monthly_goal(user_id)
        return task.get("reward", {})

    async def claim_monthly_goal(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Claim the monthly goal reward (slot 20). Returns reward dict or None."""
        await self.ensure_ready()
        async with self._get_lock():
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT task_data FROM monthly_tasks WHERE user_id=? AND slot=20",
                    (user_id,)
                ) as cur:
                    row = await cur.fetchone()
                if not row:
                    return None
                task = json.loads(row["task_data"])
                if not task.get("completed") or task.get("reward_delivered"):
                    return None
                task["reward_delivered"] = True
                await db.execute(
                    "UPDATE monthly_tasks SET task_data=? WHERE user_id=? AND slot=20",
                    (json.dumps(task), user_id)
                )
                month_start = _utc_month_start()
                await db.execute(
                    "UPDATE monthly_goal SET last_completed=? WHERE user_id=?",
                    (month_start, user_id)
                )
                await db.commit()
        return task.get("reward", {})

    async def monthly_reset_all_users(self):
        """
        Called at the 1st of each month 00:00 UTC. Wipes all monthly task rows
        so every user gets fresh monthly tasks on their next visit.
        """
        await self.ensure_ready()
        async with self._get_lock():
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM monthly_tasks")
                await db.commit()
        logger.info("monthly_reset_all_users: wiped all monthly task rows")

    async def deliver_reward(self, user_id: str, reward: Dict[str, Any]) -> str:
        """Add one reward item or a reward bundle to user's pet inventory."""
        from Systems.Functions.user_data_manager import user_data_manager
        from Systems.Pets.Logic.pet_brain import LootCalculator

        pet = await user_data_manager.get_pet_data_async(user_id)
        if not pet:
            return "No pet found to receive reward."

        messages: List[str] = []
        failures: List[str] = []
        for reward_item in _reward_items(reward):
            item_type = "Key" if reward_item["type"] == "key" else "Chest"
            item = {
                "name":  reward_item["item"],
                "type":  item_type,
                "count": reward_item.get("count", 1),
            }
            added, msg = await LootCalculator.add_item_to_inventory(int(user_id), item, pet)
            if added:
                messages.append(msg.strip() or f"Received {item['count']}x {item['name']}!")
            else:
                failures.append(f"Could not add {item['name']} to inventory.")

        if messages and not failures:
            return " ".join(messages)
        if messages:
            return " ".join(messages + failures)
        return " ".join(failures) or "No reward items to deliver."


tasks_db = TasksDB()

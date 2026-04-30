"""
Pet Stock Engine
Manages a simulated stock market for Pet Tokens, priced in Pet XP.
Tokens are grouped by Pet Type (Land, Swimming, Flying) and Element.
Prices update every 15 minutes with randomness, buy/sell pressure, and market events.

Market Dynamics:
- Random drift: Elements ±20%, Types ±12% per tick
- Momentum spikes: 10% chance of extra ±12% volatility
- Circulation pressure: More tokens held → price rises
- Trade pressure: Recent buys push up, sells push down
- Events: Holiday (100% when active), Major (75% chance), Minor (85% chance)

XP Transactions:
- Buying: Deducts XP from pet (may cause level-down)
- Selling: Adds XP to pet (may cause level-up)
- Ledger tracks all transactions for P&L calculation
"""

import asyncio
import logging
import math
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite

from Systems.Functions.pet_stock_events import MAJOR_EVENTS, MINOR_EVENTS
from Systems.Functions.db_paths import REAPER_DB

logger = logging.getLogger(__name__)

DB_FILE = REAPER_DB

PET_TYPES = ["land", "swimming", "flying"]
ELEMENTS = [
    "basic", "fire", "water", "electric", "ice",
    "plant", "rock", "air", "magic", "holy", "necro", "psychic", "fighting",
]

TYPE_EMOJIS = {
    "land":     "/static/Emojis/Pets/Deco/Land.png",
    "swimming": "/static/Emojis/Pets/Deco/Swimming.png",
    "flying":   "/static/Emojis/Pets/Deco/Flying.png",
}

ELEMENT_EMOJIS = {
    "basic":    "/static/Emojis/Pets/Deco/Basic.png",
    "fire":     "/static/Emojis/Pets/Deco/Fire.png",
    "water":    "/static/Emojis/Pets/Deco/Water.png",
    "electric": "/static/Emojis/Pets/Deco/Electric.png",
    "ice":      "/static/Emojis/Pets/Deco/Ice.png",
    "plant":    "/static/Emojis/Pets/Deco/Plant.png",
    "rock":     "/static/Emojis/Pets/Deco/Rock.png",
    "air":      "/static/Emojis/Pets/Deco/Air.png",
    "magic":    "/static/Emojis/Pets/Deco/Magic.png",
    "holy":     "/static/Emojis/Pets/Deco/Holy.png",
    "necro":    "/static/Emojis/Pets/Deco/Necro.png",
    "psychic":  "/static/Emojis/Pets/Deco/Psychic.png",
    "fighting": "/static/Emojis/Pets/Deco/Fighting.png",
}

# Base prices (XP) for each token
BASE_PRICES: Dict[str, int] = {
    # Types — stable, lower base
    "land": 250, "swimming": 250, "flying": 250,
    # Elements — volatile, higher base
    "basic": 500, "fire": 500, "water": 500, "electric": 500,
    "ice": 500, "plant": 500, "rock": 500, "air": 500,
    "magic": 500, "holy": 500, "necro": 500, "psychic": 500, "fighting": 500,
}

# Per-token drift scale: types move at ~half the speed of elements
# Applied as a multiplier on the random drift and pressure components
DRIFT_SCALE: Dict[str, float] = {
    "land": 0.6, "swimming": 0.6, "flying": 0.6,
    # Elements all at full scale
    **{e: 1.0 for e in [
        "basic", "fire", "water", "electric", "ice",
        "plant", "rock", "air", "magic", "holy", "necro", "psychic", "fighting",
    ]},
}

# Hard absolute price limits
PRICE_MIN = 1.0
PRICE_MAX = 50_000_000.0

# Update interval in seconds (15 minutes)
UPDATE_INTERVAL = 900

# Max history entries kept per token (15-min ticks: 4/hr × 24hr × 7days = 672)
MAX_HISTORY = 672

# ── Event weight tables ───────────────────────────────────────────────────────

def _build_weights(events: List[Dict]) -> Tuple[List[Dict], List[float]]:
    """Filter out holiday entries and build parallel weight list."""
    filtered = [e for e in events if "holiday" not in e]
    weights  = [float(e.get("weight", 1)) for e in filtered]
    return filtered, weights


# Major events eligible for random-day selection (no holiday key)
_RAND_MAJOR_EVENTS, _RAND_MAJOR_WEIGHTS = _build_weights(MAJOR_EVENTS)
# Minor events (none have holiday keys)
_MINOR_EVENTS, _MINOR_WEIGHTS = _build_weights(MINOR_EVENTS)


def _get_holiday_major(now: datetime) -> Optional[Dict]:
    """Return the holiday Major event for today, or None."""
    month, day = now.month, now.day
    for e in MAJOR_EVENTS:
        if e.get("holiday") == (month, day):
            return e
    return None


def _apply_event(prices: Dict[str, float], event: Dict) -> Tuple[Dict[str, float], str]:
    """Apply a market event to the current prices. Returns updated prices and event description."""
    etype = event["type"]
    desc  = f"📢 {event['name']}: {event['desc']}"

    if etype == "global":
        mult = event["mult"]
        prices = {k: v * mult for k, v in prices.items()}

    elif etype == "elements":
        mult = event["mult"]
        for t in event["targets"]:
            if t in prices:
                prices[t] *= mult

    elif etype == "types":
        # Types move slower — compress the multiplier toward 1.0 by 50%
        raw_mult = event["mult"]
        mult = 1.0 + (raw_mult - 1.0) * 0.5
        for t in event["targets"]:
            if t in prices:
                prices[t] *= mult

    elif etype == "mixed":
        raw_mult = event["mult"]
        elem_mult = raw_mult
        # Type side gets compressed toward 1.0 by 50%
        type_mult = 1.0 + (raw_mult - 1.0) * 0.5
        for t in event.get("elem_targets", []):
            if t in prices:
                prices[t] *= elem_mult
        for t in event.get("type_targets", []):
            if t in prices:
                prices[t] *= type_mult

    elif etype == "random_boost":
        count = event["count"]
        mult  = event["mult"]
        keys  = random.sample(list(prices.keys()), min(count, len(prices)))
        for k in keys:
            prices[k] *= mult
        desc += f" ({', '.join(k.title() for k in keys)})"

    elif etype == "random_dump":
        count = event["count"]
        mult  = event["mult"]
        keys  = random.sample(list(prices.keys()), min(count, len(prices)))
        for k in keys:
            prices[k] *= mult
        desc += f" ({', '.join(k.title() for k in keys)})"

    elif etype == "rivalry":
        targets = event["targets"]
        winner  = random.choice(targets)
        loser   = [t for t in targets if t != winner][0]
        # Major rivalry events carry a "mult" for the winner; derive loser penalty
        win_mult  = event.get("mult", 1.30)
        lose_mult = 2.0 - win_mult  # e.g. 1.55 win → 0.45 loss; 1.30 win → 0.70 loss
        lose_mult = max(0.45, lose_mult)  # floor the loss
        prices[winner] = prices.get(winner, 500) * win_mult
        prices[loser]  = prices.get(loser,  500) * lose_mult
        desc += f" ({winner.title()} wins, {loser.title()} loses)"

    elif etype == "type_rivalry":
        winner = random.choice(PET_TYPES)
        loser  = random.choice([t for t in PET_TYPES if t != winner])
        # Types move slower — compress rivalry swings; Major events carry "mult"
        raw_win  = event.get("mult", 1.28)
        win_mult  = 1.0 + (raw_win - 1.0) * 0.5
        lose_mult = 1.0 - (raw_win - 1.0) * 0.5
        lose_mult = max(0.70, lose_mult)
        prices[winner] = prices.get(winner, 250) * win_mult
        prices[loser]  = prices.get(loser,  250) * lose_mult
        desc += f" ({winner.title()} wins, {loser.title()} loses)"

    elif etype == "chaos":
        for k in prices:
            prices[k] *= random.uniform(0.60, 1.60)
        desc += " (total chaos!)"

    return prices, desc


# ── Database helpers ──────────────────────────────────────────────────────────

async def _ensure_tables(db: aiosqlite.Connection):
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_stock_prices (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            token     TEXT    NOT NULL,
            price     REAL    NOT NULL,
            timestamp TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS idx_psp_token ON pet_stock_prices(token)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_psp_ts    ON pet_stock_prices(timestamp)")

    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_stock_events (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            event_msg TEXT    NOT NULL,
            timestamp TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)

    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_stock_holdings (
            user_id   TEXT NOT NULL,
            token     TEXT NOT NULL,
            quantity  INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, token)
        )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS idx_psh_user ON pet_stock_holdings(user_id)")

    # Ledger: tracks every buy/sell for P&L calculation
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_stock_ledger (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    TEXT    NOT NULL,
            token      TEXT    NOT NULL,
            action     TEXT    NOT NULL,  -- 'buy' or 'sell'
            quantity   INTEGER NOT NULL,
            xp_amount  INTEGER NOT NULL,  -- positive = XP spent (buy), positive = XP received (sell)
            timestamp  TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS idx_psl_user  ON pet_stock_ledger(user_id)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_psl_token ON pet_stock_ledger(user_id, token)")

    # Tracks the active non-holiday Major event for the current calendar day
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_stock_major_event (
            date_key       TEXT PRIMARY KEY,  -- 'YYYY-MM-DD'
            event_json     TEXT NOT NULL,
            is_holiday     INTEGER NOT NULL DEFAULT 0,
            start_hour     INTEGER NOT NULL DEFAULT 0,
            duration_hours INTEGER NOT NULL DEFAULT 24
        )
    """)
    # Tracks the active Holiday event separately so both can fire at once
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_stock_holiday_event (
            date_key   TEXT PRIMARY KEY,  -- 'YYYY-MM-DD'
            event_json TEXT NOT NULL
        )
    """)
    # Migration: add columns to existing major event table if missing
    for col_sql in [
        "ALTER TABLE pet_stock_major_event ADD COLUMN start_hour INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE pet_stock_major_event ADD COLUMN duration_hours INTEGER NOT NULL DEFAULT 24",
    ]:
        try:
            await db.execute(col_sql)
        except Exception:
            pass

    await db.commit()


async def get_latest_prices() -> Dict[str, float]:
    """Return the most recent price for every token."""
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await _ensure_tables(db)
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT token, price FROM pet_stock_prices
                WHERE id IN (
                    SELECT MAX(id) FROM pet_stock_prices GROUP BY token
                )
            """) as cur:
                rows = await cur.fetchall()
            if not rows:
                return dict(BASE_PRICES)
            return {r["token"]: r["price"] for r in rows}
    except Exception as e:
        logger.error(f"get_latest_prices error: {e}")
        return dict(BASE_PRICES)


async def get_price_history(hours: int = 48) -> Dict[str, List[Dict]]:
    """Return price history for all tokens over the last N hours."""
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await _ensure_tables(db)
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT token, price, timestamp FROM pet_stock_prices
                WHERE timestamp >= datetime('now', ?)
                ORDER BY timestamp ASC
            """, (f"-{hours} hours",)) as cur:
                rows = await cur.fetchall()
        history: Dict[str, List] = {}
        for r in rows:
            history.setdefault(r["token"], []).append({
                "price": r["price"],
                "timestamp": r["timestamp"],
            })
        return history
    except Exception as e:
        logger.error(f"get_price_history error: {e}")
        return {}


async def get_recent_events(limit: int = 10) -> List[Dict]:
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await _ensure_tables(db)
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT event_msg, timestamp FROM pet_stock_events
                ORDER BY id DESC LIMIT ?
            """, (limit,)) as cur:
                rows = await cur.fetchall()
        return [{"msg": r["event_msg"], "timestamp": r["timestamp"]} for r in rows]
    except Exception as e:
        logger.error(f"get_recent_events error: {e}")
        return []


async def get_active_events() -> List[Dict]:
    """Return currently active events: Holiday (if today), Major (if active), Minor (last tick)."""
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await _ensure_tables(db)
            now      = datetime.now(timezone.utc)
            date_key = now.strftime("%Y-%m-%d")
            db.row_factory = aiosqlite.Row
            active   = []

            # ── Holiday event (active all day) ────────────────────────────────
            holiday = _get_holiday_major(now)
            if holiday:
                active.append({
                    "msg": f"🎉 HOLIDAY {holiday['name']}: {holiday['desc']}",
                    "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "tier": "holiday",
                })

            # ── Non-holiday Major event (active during its window) ────────────
            async with db.execute(
                "SELECT event_json, start_hour, duration_hours FROM pet_stock_major_event WHERE date_key=?",
                (date_key,)
            ) as cur:
                major_row = await cur.fetchone()

            if major_row:
                event_data   = _json.loads(major_row["event_json"])
                start_hour   = major_row["start_hour"]
                dur_hours    = major_row["duration_hours"]
                if event_data.get("name") != "__none__" and start_hour >= 0:
                    active_hours = {(start_hour + i) % 24 for i in range(dur_hours)}
                    if now.hour in active_hours:
                        end_hour = (start_hour + dur_hours) % 24
                        active.append({
                            "msg": f"🌟 MAJOR {event_data['name']}: {event_data['desc']} (Until {end_hour:02d}:00 UTC)",
                            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                            "tier": "major",
                        })

            # ── Most recent Minor event (from last tick log) ──────────────────
            async with db.execute(
                "SELECT event_msg, timestamp FROM pet_stock_events ORDER BY id DESC LIMIT 1"
            ) as cur:
                last_row = await cur.fetchone()

            if last_row:
                msg = last_row["event_msg"]
                # Pull out just the MINOR portion if it's a combined log line
                if "⚡ MINOR" in msg:
                    parts      = msg.split("|")
                    minor_part = next((p.strip() for p in parts if "⚡ MINOR" in p), msg)
                    active.append({"msg": minor_part, "timestamp": last_row["timestamp"], "tier": "minor"})
                elif "🎉 HOLIDAY" not in msg and "🌟 MAJOR" not in msg:
                    active.append({"msg": msg, "timestamp": last_row["timestamp"], "tier": "minor"})

            return active
    except Exception as e:
        logger.error(f"get_active_events error: {e}")
        return []


def get_price_multiplier(token: str, pet_data: Dict) -> float:
    """
    Returns the XP price multiplier for a token based on pet affinity.
    - Matching token (type or element): 1x
    - Non-matching, pet has 1 element: 2x
    - Non-matching, pet has 2 elements: 3x
    """
    pet_type  = (pet_data.get("category") or "").lower()
    pet_elem1 = (pet_data.get("element")  or "").lower()
    pet_elem2 = (pet_data.get("element2") or "").lower()
    allowed   = {pet_type, pet_elem1, pet_elem2} - {""}

    if token in allowed:
        return 1.0

    elem_count = sum(1 for e in [pet_elem1, pet_elem2] if e)
    return 3.0 if elem_count >= 2 else 2.0


async def get_user_holdings(user_id: str) -> Dict[str, int]:
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await _ensure_tables(db)
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT token, quantity FROM pet_stock_holdings WHERE user_id=? AND quantity>0",
                (user_id,)
            ) as cur:
                rows = await cur.fetchall()
        return {r["token"]: r["quantity"] for r in rows}
    except Exception as e:
        logger.error(f"get_user_holdings error: {e}")
        return {}


async def get_user_pnl(user_id: str) -> Dict[str, Any]:
    """
    Returns per-token and total P&L.
    All XP spent on buys counts as a loss until offset by sell proceeds.
    Unrealised value of held tokens is included in net.
    """
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await _ensure_tables(db)
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT token,
                       SUM(CAST(CASE WHEN action='buy'  THEN xp_amount ELSE 0 END AS REAL)) AS total_spent,
                       SUM(CAST(CASE WHEN action='sell' THEN xp_amount ELSE 0 END AS REAL)) AS total_received
                FROM pet_stock_ledger
                WHERE user_id=?
                GROUP BY token
            """, (user_id,)) as cur:
                rows = await cur.fetchall()

            async with db.execute(
                "SELECT token, quantity FROM pet_stock_holdings WHERE user_id=? AND quantity>0",
                (user_id,)
            ) as cur:
                hold_rows = await cur.fetchall()

        holdings = {r["token"]: r["quantity"] for r in hold_rows}
        prices   = await get_latest_prices()

        per_token: Dict[str, Dict] = {}
        total_spent    = 0
        total_received = 0

        for r in rows:
            tok      = r["token"]
            spent    = r["total_spent"]    or 0
            received = r["total_received"] or 0
            qty      = holdings.get(tok, 0)
            cur_val  = round(prices.get(tok, BASE_PRICES.get(tok, 0)) * qty)
            realised = received - spent
            per_token[tok] = {
                "spent":      spent,
                "received":   received,
                "realised":   realised,
                "held_qty":   qty,
                "held_value": cur_val,
                "net":        realised + cur_val,
            }
            total_spent    += spent
            total_received += received

        for tok, qty in holdings.items():
            if tok not in per_token:
                cur_val = round(prices.get(tok, BASE_PRICES.get(tok, 0)) * qty)
                per_token[tok] = {
                    "spent": 0, "received": 0, "realised": 0,
                    "held_qty": qty, "held_value": cur_val, "net": cur_val,
                }

        total_realised  = total_received - total_spent
        total_held_val  = sum(v["held_value"] for v in per_token.values())

        return {
            "per_token":        per_token,
            "total_spent":      total_spent,
            "total_received":   total_received,
            "total_realised":   total_realised,
            "total_held_value": total_held_val,
            "total_net":        total_realised + total_held_val,
        }
    except Exception as e:
        logger.error(f"get_user_pnl error: {e}", exc_info=True)
        return {"per_token": {}, "total_spent": 0, "total_received": 0,
                "total_realised": 0, "total_held_value": 0, "total_net": 0}


async def _get_holding(db: aiosqlite.Connection, user_id: str, token: str) -> int:
    async with db.execute(
        "SELECT quantity FROM pet_stock_holdings WHERE user_id=? AND token=?",
        (user_id, token)
    ) as cur:
        row = await cur.fetchone()
    return row[0] if row else 0


async def buy_token(user_id: str, token: str, quantity: int, pet_data: Dict) -> Dict:
    """
    Deduct XP from pet and add tokens to holdings.
    Non-matching tokens cost 2x (1-element pet) or 3x (2-element pet).
    Uses add_pet_experience(-cost) so level-down logic is handled correctly.
    
    XP Tracking:
    - XP is deducted from the pet's total XP pool (across all levels)
    - If XP drops below current level threshold, pet levels down automatically
    - Ledger records the XP cost for P&L calculation
    - Buy pressure is recorded to influence next price tick
    """
    if token not in {**{t: 1 for t in PET_TYPES}, **{e: 1 for e in ELEMENTS}}:
        return {"ok": False, "error": "Unknown token"}
    if quantity < 1:
        return {"ok": False, "error": "Quantity must be at least 1"}
    # Removed per-transaction limit since we have per-token holding limits

    mult   = get_price_multiplier(token, pet_data)
    prices = await get_latest_prices()
    price  = prices.get(token, BASE_PRICES.get(token, 100))
    cost   = int(price * mult * quantity)

    # Compute total spendable XP across all levels
    from Systems.Pets.Logic.pet_brain import LootCalculator
    lvl = int(pet_data.get("level", 1))
    rem = int(pet_data.get("experience", 0))
    total_xp = int(LootCalculator.get_total_experience_for_level(lvl)) + rem

    if total_xp < cost:
        return {"ok": False, "error": f"Not enough XP (need {cost:,}, have {total_xp:,})"}

    try:
        from Systems.Functions.user_data_manager import user_data_manager

        MAX_HOLDING = 100_000

        async with aiosqlite.connect(DB_FILE) as db:
            await _ensure_tables(db)
            cur_qty = await _get_holding(db, user_id, token)
            new_qty = cur_qty + quantity
            if new_qty > MAX_HOLDING:
                return {"ok": False, "error": f"Cannot hold more than {MAX_HOLDING:,} tokens of one type (you have {cur_qty:,})"}
            await db.execute("""
                INSERT INTO pet_stock_holdings (user_id, token, quantity)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, token) DO UPDATE SET quantity=excluded.quantity
            """, (user_id, token, new_qty))
            await db.execute(
                "INSERT INTO pet_stock_ledger (user_id, token, action, quantity, xp_amount) VALUES (?,?,?,?,?)",
                (user_id, token, "buy", quantity, cost)
            )
            # Record buy pressure so the price engine picks it up next tick
            await db.execute(
                "INSERT INTO pet_stock_prices (token, price) VALUES (?, ?)",
                (f"__buy__{token}", float(quantity))
            )
            await db.commit()

        # add_pet_experience returns (has_level_changed, change_data).
        # (False, None) is the normal result when XP changes but no level change occurs —
        # it does NOT indicate failure. Only a raised exception means failure (caught below).
        _has_changed, change_data = await user_data_manager.add_pet_experience(user_id, -cost, source="pet_stock")

        # Reload pet to get accurate new XP for response
        updated_pet = await user_data_manager.get_pet_data_async(user_id)
        new_lvl = int(updated_pet.get("level", 1)) if updated_pet else lvl
        new_rem = int(updated_pet.get("experience", 0)) if updated_pet else 0
        new_total = int(LootCalculator.get_total_experience_for_level(new_lvl)) + new_rem

        result: Dict[str, Any] = {"ok": True, "new_xp": new_total, "new_qty": new_qty, "cost": cost, "mult": mult}
        if _has_changed and change_data:
            result["level_change"] = change_data
        return result
    except Exception as e:
        logger.error(f"buy_token error: {e}", exc_info=True)
        return {"ok": False, "error": "Transaction failed"}


async def sell_token(user_id: str, token: str, quantity: int, pet_data: Dict) -> Dict:
    """
    Remove tokens from holdings and add XP to pet.
    Non-matching tokens pay out at 1/2x (1-element pet) or 1/3x (2-element pet) of market price.
    
    XP Tracking:
    - XP is added to the pet's total XP pool
    - Pet may level up if XP crosses threshold
    - Ledger records the XP payout for P&L calculation
    - Sell pressure is recorded to influence next price tick
    """
    if quantity < 1:
        return {"ok": False, "error": "Quantity must be at least 1"}

    mult   = get_price_multiplier(token, pet_data)
    prices = await get_latest_prices()
    price  = prices.get(token, BASE_PRICES.get(token, 100))
    payout = round(price * quantity / mult)

    try:
        from Systems.Functions.user_data_manager import user_data_manager

        async with aiosqlite.connect(DB_FILE) as db:
            await _ensure_tables(db)
            cur_qty = await _get_holding(db, user_id, token)
            if cur_qty < quantity:
                return {"ok": False, "error": f"Not enough tokens (have {cur_qty}, selling {quantity})"}

            new_qty = cur_qty - quantity
            await db.execute("""
                INSERT INTO pet_stock_holdings (user_id, token, quantity)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, token) DO UPDATE SET quantity=excluded.quantity
            """, (user_id, token, new_qty))
            await db.execute(
                "INSERT INTO pet_stock_prices (token, price) VALUES (?, ?)",
                (f"__sell__{token}", float(quantity))
            )
            await db.execute(
                "INSERT INTO pet_stock_ledger (user_id, token, action, quantity, xp_amount) VALUES (?,?,?,?,?)",
                (user_id, token, "sell", quantity, payout)
            )
            await db.commit()

        _has_changed, change_data = await user_data_manager.add_pet_experience(user_id, payout, source="pet_stock")

        # Check if XP addition was successful (for sells, we're more lenient since the user already lost tokens)
        if not _has_changed and change_data is None:
            logger.warning(f"sell_token: XP addition failed for user {user_id}, but tokens were already sold")

        updated_pet = await user_data_manager.get_pet_data_async(user_id)
        from Systems.Pets.Logic.pet_brain import LootCalculator
        new_lvl = int(updated_pet.get("level", 1)) if updated_pet else 1
        new_rem = int(updated_pet.get("experience", 0)) if updated_pet else 0
        new_total = int(LootCalculator.get_total_experience_for_level(new_lvl)) + new_rem

        result: Dict[str, Any] = {"ok": True, "new_xp": new_total, "new_qty": new_qty, "payout": payout, "mult": mult}
        if _has_changed and change_data:
            result["level_change"] = change_data
        return result
    except Exception as e:
        logger.error(f"sell_token error: {e}", exc_info=True)
        return {"ok": False, "error": "Transaction failed"}


async def buy_all_token(user_id: str, token: str, pet_data: Dict) -> Dict:
    """
    Buy as many tokens as possible up to MAX_HOLDING (100,000), limited by available XP.
    Respects the per-token cap — buys exactly (cap - current_holdings) or as many as XP allows.
    """
    logger.info(f"buy_all_token: user_id={user_id}, token='{token}', pet_data keys: {list(pet_data.keys()) if pet_data else 'None'}")
    
    if token not in {**{t: 1 for t in PET_TYPES}, **{e: 1 for e in ELEMENTS}}:
        logger.error(f"buy_all_token: Unknown token '{token}'. Valid tokens: {PET_TYPES + ELEMENTS}")
        return {"ok": False, "error": "Unknown token"}

    MAX_HOLDING = 100_000

    from Systems.Pets.Logic.pet_brain import LootCalculator
    lvl = int(pet_data.get("level", 1))
    rem = int(pet_data.get("experience", 0))
    total_xp = int(LootCalculator.get_total_experience_for_level(lvl)) + rem

    mult   = get_price_multiplier(token, pet_data)
    prices = await get_latest_prices()
    price  = prices.get(token, BASE_PRICES.get(token, 100))
    cost_each = int(price * mult)

    if cost_each < 1:
        return {"ok": False, "error": "Token price too low to calculate"}

    async with aiosqlite.connect(DB_FILE) as db:
        await _ensure_tables(db)
        cur_qty = await _get_holding(db, user_id, token)

    room = MAX_HOLDING - cur_qty
    if room <= 0:
        return {"ok": False, "error": f"Already at the cap of {MAX_HOLDING:,} tokens"}

    can_afford = total_xp // cost_each
    quantity   = min(room, can_afford)

    if quantity <= 0:
        return {"ok": False, "error": f"Not enough XP to buy even 1 token (need {cost_each:,} XP each, have {total_xp:,})"}

    return await buy_token(user_id, token, quantity, pet_data)


async def sell_all_token(user_id: str, token: str, pet_data: Dict) -> Dict:
    """Sell all held tokens of a given type."""
    async with aiosqlite.connect(DB_FILE) as db:
        await _ensure_tables(db)
        cur_qty = await _get_holding(db, user_id, token)

    if cur_qty <= 0:
        return {"ok": False, "error": "You don't hold any of this token"}

    return await sell_token(user_id, token, cur_qty, pet_data)


# ── Price Update ─────────────────────────────────────────────────────────────

import json as _json  # local alias to avoid shadowing

async def _get_or_set_day_major(db: aiosqlite.Connection, now: datetime) -> Optional[Dict]:
    """
    Return the non-holiday Major event active RIGHT NOW, or None.

    Rules:
    - Holidays are handled separately in _get_holiday_event — NOT here.
    - 85% of days have a major event (up from 67% for more market activity)
    - Each tick has a 75% chance to trigger the major event application (up from 33%)
    - The day's major event is decided once (random pick + random 2-8 hr window)
    - If no major event was scheduled for today, returns None.
    - Returns the event dict only when the current hour is inside its window.
    """
    date_key     = now.strftime("%Y-%m-%d")
    current_hour = now.hour

    # ── Decide today's major event once ──────────────────────────────────────
    async with db.execute(
        "SELECT event_json, start_hour, duration_hours FROM pet_stock_major_event WHERE date_key=?",
        (date_key,)
    ) as cur:
        row = await cur.fetchone()

    if row is None:
        # First tick of the day — 85% chance a major event is scheduled today
        if random.random() < 0.15:
            # No major event today — store sentinel
            await db.execute(
                """INSERT OR REPLACE INTO pet_stock_major_event
                   (date_key, event_json, is_holiday, start_hour, duration_hours)
                   VALUES (?,?,0,-1,0)""",
                (date_key, _json.dumps({"name": "__none__", "type": "none"}))
            )
        else:
            major          = random.choices(_RAND_MAJOR_EVENTS, weights=_RAND_MAJOR_WEIGHTS, k=1)[0]
            start_hour     = random.randint(0, 23)
            duration_hours = random.randint(2, 8)  # Longer event windows (2-8 hours instead of 1-6)
            await db.execute(
                """INSERT OR REPLACE INTO pet_stock_major_event
                   (date_key, event_json, is_holiday, start_hour, duration_hours)
                   VALUES (?,?,0,?,?)""",
                (date_key, _json.dumps(major), start_hour, duration_hours)
            )
        await db.commit()
        async with db.execute(
            "SELECT event_json, start_hour, duration_hours FROM pet_stock_major_event WHERE date_key=?",
            (date_key,)
        ) as cur:
            row = await cur.fetchone()

    event_data, start_hour, duration_hours = (
        _json.loads(row[0]), row[1], row[2]
    )

    if event_data.get("name") == "__none__" or start_hour < 0:
        return None

    active_hours = {(start_hour + i) % 24 for i in range(duration_hours)}
    if current_hour not in active_hours:
        return None

    return event_data


async def run_price_update():
    """
    15-minute price update — real stock market behaviour:

      1.  Load current prices
      2.  Fetch buy/sell pressure from last 15 min (actual trade volume)
      3.  Fetch total circulation per token (all held quantities)
      4.  Apply random drift  (elements ±20%, types ±12%)
      5.  Apply circulation pressure  (more held = price up, less = price down)
      6.  Apply buy/sell pressure from recent trades
      7.  Apply HOLIDAY event every tick it is active (100% chance, all day)
      8.  Apply non-holiday MAJOR event on 75% of ticks while its window is active (2-8 hour windows)
      9.  Apply MINOR event on 85% of ticks (almost always fires for constant market movement)
      10. Hard-clamp [0.01, 999_999_999]
      11. Persist + log
      
    Event Frequency:
    - Major events: 85% of days have one (up from 67%)
    - Major event windows: 2-8 hours (up from 1-6 hours)
    - Major event application: 75% chance per tick (up from 33%)
    - Minor event application: 85% chance per tick (up from 50%)
    - Result: Much more dynamic market with frequent price movements
    """
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            await _ensure_tables(db)
            db.row_factory = aiosqlite.Row
            now = datetime.now(timezone.utc)
            ts  = now.strftime("%Y-%m-%d %H:%M:%S")

            # ── 1. Current prices ─────────────────────────────────────────────
            async with db.execute("""
                SELECT token, price FROM pet_stock_prices
                WHERE id IN (SELECT MAX(id) FROM pet_stock_prices GROUP BY token)
                  AND token NOT LIKE '__buy__%' AND token NOT LIKE '__sell__%'
            """) as cur:
                rows = await cur.fetchall()

            prices: Dict[str, float] = {}
            for r in rows:
                prices[r["token"]] = r["price"]
            for t in PET_TYPES + ELEMENTS:
                if t not in prices:
                    prices[t] = float(BASE_PRICES[t])

            # ── 2. Buy/sell pressure (trade volume last 15 min) ───────────────
            async with db.execute("""
                SELECT token, SUM(price) AS total FROM pet_stock_prices
                WHERE timestamp >= datetime('now', '-15 minutes')
                  AND (token LIKE '__buy__%' OR token LIKE '__sell__%')
                GROUP BY token
            """) as cur:
                pressure_rows = await cur.fetchall()

            buy_pressure:  Dict[str, float] = {}
            sell_pressure: Dict[str, float] = {}
            for r in pressure_rows:
                tok = r["token"]
                if tok.startswith("__buy__"):
                    buy_pressure[tok[7:]] = r["total"]
                elif tok.startswith("__sell__"):
                    sell_pressure[tok[8:]] = r["total"]

            # ── 3. Total circulation per token (all holdings) ─────────────────
            async with db.execute("""
                SELECT token, SUM(quantity) AS total
                FROM pet_stock_holdings
                WHERE quantity > 0
                GROUP BY token
            """) as cur:
                circ_rows = await cur.fetchall()

            circulation: Dict[str, int] = {r["token"]: r["total"] for r in circ_rows}

            # ── 4 + 5 + 6. Drift + circulation + trade pressure ───────────────
            for token in list(prices.keys()):
                current = prices[token]
                scale   = DRIFT_SCALE.get(token, 1.0)
                base    = float(BASE_PRICES.get(token, 500))

                # Random drift: elements ±20%, types ±12%
                max_drift = 0.20 * scale
                drift     = random.uniform(-max_drift, max_drift)

                # Momentum spike: 10% chance of extra ±12%
                if random.random() < 0.10:
                    drift += random.uniform(-0.12, 0.12) * scale

                # Circulation pressure: tokens in circulation vs base reference (500/250)
                # More tokens held → price rises; fewer → price drifts back toward base
                circ       = circulation.get(token, 0)
                circ_ref   = base * 2.0          # "neutral" circulation level
                circ_delta = (circ - circ_ref) / max(circ_ref, 1.0)
                # Cap circulation effect at ±15% per tick
                circ_effect = max(-0.15, min(0.15, circ_delta * 0.05)) * scale

                # Trade pressure: recent buys push up, recent sells push down
                bp              = buy_pressure.get(token, 0)
                sp              = sell_pressure.get(token, 0)
                net_volume      = bp - sp
                # Normalise against current price so large prices don't dominate
                trade_effect    = (net_volume * 0.004 / max(1.0, current)) * scale

                # Mean-reversion: prevents complete bottom-outs and runaway tops.
                # Uses log-ratio so the pull is proportional to how far off base we are.
                # At 1/10th of base → ~+23% pull; at 10x base → ~-23% pull.
                # Scaled down to ±8% max per tick so it doesn't override real moves.
                log_ratio = math.log(max(0.0001, current) / max(0.0001, base))
                reversion = max(-0.08, min(0.08, -log_ratio * 0.08))

                prices[token] = current * (1.0 + drift + circ_effect + trade_effect + reversion)

            # ── 7. Holiday event — fires every tick all day ───────────────────
            holiday     = _get_holiday_major(now)
            holiday_desc: Optional[str] = None
            if holiday:
                prices, holiday_desc = _apply_event(prices, holiday)
                logger.info(f"Applied holiday event: {holiday['name']}")

            # ── 8. Non-holiday Major event — 75% chance per tick while active ─
            major      = await _get_or_set_day_major(db, now)
            major_desc: Optional[str] = None
            if major is not None and random.random() < 0.75:
                prices, major_desc = _apply_event(prices, major)
                logger.info(f"Applied major event: {major['name']}")

            # ── 9. Minor event — 85% chance (almost always fires) ────────────
            minor      = random.choices(_MINOR_EVENTS, weights=_MINOR_WEIGHTS, k=1)[0]
            minor_desc: Optional[str] = None
            if random.random() < 0.85:
                prices, minor_desc = _apply_event(prices, minor)

            # ── 10. Hard clamp ────────────────────────────────────────────────
            for token in prices:
                prices[token] = max(PRICE_MIN, min(PRICE_MAX, prices[token]))

            # ── 11. Persist prices ────────────────────────────────────────────
            await db.executemany(
                "INSERT INTO pet_stock_prices (token, price, timestamp) VALUES (?, ?, ?)",
                [(tok, round(p, 2), ts) for tok, p in prices.items()]
            )

            # Build event log line
            parts = []
            if holiday_desc:
                parts.append(f"🎉 HOLIDAY {holiday_desc}")
            if major_desc:
                parts.append(f"🌟 MAJOR {major_desc}")
            if minor_desc:
                parts.append(f"⚡ MINOR {minor_desc}")
            if not parts:
                parts.append("📉 Quiet tick — no events fired")

            combined = "  |  ".join(parts)
            await db.execute(
                "INSERT INTO pet_stock_events (event_msg, timestamp) VALUES (?, ?)",
                (combined, ts)
            )

            # Prune old history per token
            for token in prices:
                await db.execute("""
                    DELETE FROM pet_stock_prices
                    WHERE token=? AND id NOT IN (
                        SELECT id FROM pet_stock_prices WHERE token=?
                        ORDER BY id DESC LIMIT ?
                    )
                """, (token, token, MAX_HISTORY))

            await db.commit()

            active_names = []
            if holiday:
                active_names.append(f"Holiday:{holiday['name']}")
            if major_desc:
                active_names.append(f"Major:{major['name']}")
            if minor_desc:
                active_names.append(f"Minor:{minor['name']}")
            logger.info(f"Pet stock update — {', '.join(active_names) if active_names else 'no events'}")

    except Exception as e:
        logger.error(f"run_price_update error: {e}", exc_info=True)


# Keep old name as alias so any external callers don't break
run_hourly_update = run_price_update


async def start_stock_loop():
    """Background task: run price update every 15 minutes."""
    prices = await get_latest_prices()
    if not prices or all(prices.get(t) == BASE_PRICES.get(t) for t in PET_TYPES):
        await run_price_update()

    while True:
        await asyncio.sleep(UPDATE_INTERVAL)
        await run_price_update()

async def buy_max_all_tokens(user_id: str, pet_data: Dict) -> Dict:
    """
    Buy 100,000 of each token type (up to 1,600,000 total tokens).
    Returns summary of what was bought and total cost.
    """
    logger.info(f"buy_max_all_tokens: user_id={user_id}")
    
    all_tokens = PET_TYPES + ELEMENTS
    results = []
    total_cost = 0
    total_bought = 0
    
    for token in all_tokens:
        # Get current holdings first
        current_qty = await _get_holding_for_token(user_id, token)
        
        # Try to buy up to 100,000 of this token
        result = await buy_all_token(user_id, token, pet_data)
        if result.get("ok"):
            new_qty = result.get("new_qty", 0)
            bought = new_qty - current_qty
            cost = result.get("cost", 0)
            total_cost += cost
            total_bought += bought
            results.append({
                "token": token,
                "bought": bought,
                "cost": cost,
                "new_qty": new_qty
            })
        else:
            # If we can't buy this token, still record it
            results.append({
                "token": token,
                "bought": 0,
                "cost": 0,
                "new_qty": current_qty,
                "error": result.get("error", "Unknown error")
            })
    
    return {
        "ok": True,
        "total_bought": total_bought,
        "total_cost": total_cost,
        "results": results
    }

async def sell_max_all_tokens(user_id: str, pet_data: Dict) -> Dict:
    """
    Sell all held tokens of all types.
    Returns summary of what was sold and total payout.
    """
    logger.info(f"sell_max_all_tokens: user_id={user_id}")
    
    all_tokens = PET_TYPES + ELEMENTS
    results = []
    total_payout = 0
    total_sold = 0
    
    for token in all_tokens:
        # Get current holdings first
        current_qty = await _get_holding_for_token(user_id, token)
        
        if current_qty > 0:
            # Try to sell all of this token
            result = await sell_all_token(user_id, token, pet_data)
            if result.get("ok"):
                sold = current_qty  # We know we sold all of them
                payout = result.get("payout", 0)
                total_payout += payout
                total_sold += sold
                results.append({
                    "token": token,
                    "sold": sold,
                    "payout": payout,
                    "new_qty": 0
                })
            else:
                # If we can't sell this token, still record it
                results.append({
                    "token": token,
                    "sold": 0,
                    "payout": 0,
                    "new_qty": current_qty,
                    "error": result.get("error", "Unknown error")
                })
        else:
            # No holdings to sell
            results.append({
                "token": token,
                "sold": 0,
                "payout": 0,
                "new_qty": 0
            })
    
    return {
        "ok": True,
        "total_sold": total_sold,
        "total_payout": total_payout,
        "results": results
    }

async def _get_holding_for_token(user_id: str, token: str) -> int:
    """Helper function to get current holdings for a specific token."""
    async with aiosqlite.connect(DB_FILE) as db:
        await _ensure_tables(db)
        return await _get_holding(db, user_id, token)
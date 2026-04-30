import json
import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import aiofiles
import aiosqlite
import logging

logger = logging.getLogger(__name__)

# --- Configuration ---
from Systems.Functions.db_paths import REAPER_DB, REAPER_DB_STR
DB_DIR  = str(REAPER_DB.parent)
DB_FILE = REAPER_DB_STR

# --- Old JSON file paths for migration ---
GAME_DB_FILE_OLD = os.path.join(DB_DIR, "game_data.json")
RESOURCE_DB_FILE_OLD = os.path.join(DB_DIR, "resource_data.json")

# Ensure base directory exists
os.makedirs(DB_DIR, exist_ok=True)

# --- Database Schema ---
# CREATE TABLE IF NOT EXISTS resource_prices (
#     timestamp INTEGER,
#     resource TEXT,
#     price REAL,
#     PRIMARY KEY (timestamp, resource)
# );
# CREATE TABLE IF NOT EXISTS colors (
#     timestamp INTEGER,
#     color TEXT,
#     turn_bonus INTEGER,
#     bloc_name TEXT,
#     PRIMARY KEY (timestamp, color)
# );
# CREATE TABLE IF NOT EXISTS radiation (
#     timestamp INTEGER PRIMARY KEY,
#     level REAL
# );
# CREATE TABLE IF NOT EXISTS schema_version (
#     version INTEGER PRIMARY KEY
# );
# CREATE TABLE IF NOT EXISTS pets (
#     user_id TEXT PRIMARY KEY,
#     pet_data TEXT NOT NULL,
#     created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
#     updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
# );
# CREATE TABLE IF NOT EXISTS users (
#     user_id TEXT PRIMARY KEY,
#     username TEXT,
#     created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
#     last_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
# );

# --- Internal Functions ---
async def _get_db_connection() -> aiosqlite.Connection:
    """Establishes a connection to the SQLite database."""
    conn = await aiosqlite.connect(DB_FILE)
    conn.row_factory = aiosqlite.Row  # Access columns by name
    return conn



# --- Public API ---
async def setup_databases():
    """Initializes the database and creates tables if they don't exist."""
    conn = await _get_db_connection()
    try:
        # Ensure tables are created with the correct schema without dropping them
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS resource_prices (
                timestamp INTEGER,
                resource TEXT,
                avg_price REAL,
                best_buy_price REAL,
                best_sell_price REAL,
                PRIMARY KEY (timestamp, resource)
            )
        """)
        logger.info("Ensured 'resource_prices' table exists.")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS colors (
                timestamp INTEGER,
                color TEXT,
                turn_bonus INTEGER,
                bloc_name TEXT,
                PRIMARY KEY (timestamp, color)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pets (
                user_id TEXT PRIMARY KEY,
                pet_data TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_pets_updated_at
            AFTER UPDATE ON pets
            FOR EACH ROW
            BEGIN
                UPDATE pets SET updated_at = CURRENT_TIMESTAMP WHERE user_id = OLD.user_id;
            END;
        """)
        await conn.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_users_updated_at
            AFTER UPDATE ON users
            FOR EACH ROW
            BEGIN
                UPDATE users SET last_updated = CURRENT_TIMESTAMP WHERE user_id = OLD.user_id;
            END;
        """)
        
        # Create resource supply data table for tracking global resource amounts
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS resource_supply (
                timestamp INTEGER,
                resource TEXT,
                total_amount REAL,
                PRIMARY KEY (timestamp, resource)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS game_info (
                timestamp INTEGER PRIMARY KEY,
                game_date TEXT,
                city_average REAL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS radiation (
                timestamp INTEGER PRIMARY KEY,
                global_level REAL,
                north_america REAL,
                south_america REAL,
                europe REAL,
                africa REAL,
                asia REAL,
                australia REAL,
                antarctica REAL
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_pets_user_id ON pets(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)")
        
        cursor = await conn.execute("SELECT version FROM schema_version WHERE version = 1")
        if await cursor.fetchone() is None:
            # This is where migration from an old schema would go if needed in the future.
            await conn.execute("INSERT INTO schema_version (version) VALUES (1)")
        
        await conn.commit()
    finally:
        await conn.close()

async def add_game_data(data_type: str, timestamp: int, data: Any):
    """
    Adds a new entry to the game data database.
    `data_type` should be 'colors'.
    """
    if data_type not in ["colors"]:
        raise ValueError("data_type must be 'colors'")

    conn = await _get_db_connection()
    try:
        if data_type == "colors":
            if isinstance(data, list):
                to_insert = []
                for item in data:
                    to_insert.append((
                        timestamp,
                        item.get('color'),
                        item.get('turn_bonus'),
                        item.get('bloc_name')
                    ))
                await conn.executemany(
                    "INSERT OR REPLACE INTO colors (timestamp, color, turn_bonus, bloc_name) VALUES (?, ?, ?, ?)",
                    to_insert
                )
            else:
                await conn.execute(
                    "INSERT OR REPLACE INTO colors (timestamp, color, turn_bonus, bloc_name) VALUES (?, ?, ?, ?)",
                    (timestamp, data.get('color'), data.get('turn_bonus'), data.get('bloc_name'))
                )
        await conn.commit()
    finally:
        await conn.close()

async def add_resource_data(timestamp: int, prices: Dict[str, Dict[str, float]]):
    """Adds a new price entry to the resource database."""
    to_insert = [
        (timestamp, resource, price_data.get('avg', 0), price_data.get('best_buy', 0), price_data.get('best_sell', 0))
        for resource, price_data in prices.items()
    ]
    
    logger.info(f"Adding resource data for {len(prices)} resources: {list(prices.keys())}")
    
    conn = await _get_db_connection()
    try:
        await conn.executemany(
            "INSERT OR REPLACE INTO resource_prices (timestamp, resource, avg_price, best_buy_price, best_sell_price) VALUES (?, ?, ?, ?, ?)",
            to_insert
        )
        await conn.commit()
        logger.info(f"Successfully saved {len(to_insert)} resource price records")
    finally:
        await conn.close()

async def add_resource_supply_data(timestamp: int, supply_data: Dict[str, float]):
    """Adds a new supply entry to the resource database."""
    to_insert = [(timestamp, resource, amount) for resource, amount in supply_data.items()]
    conn = await _get_db_connection()
    try:
        await conn.executemany(
            "INSERT OR REPLACE INTO resource_supply (timestamp, resource, total_amount) VALUES (?, ?, ?)",
            to_insert
        )
        await conn.commit()
    finally:
        await conn.close()

async def get_latest_game_data(data_type: str) -> Optional[Any]:
    """
    Gets the most recent entry for a given data type from the game database.
    """
    if data_type not in ["colors"]:
        raise ValueError("data_type must be 'colors'")

    conn = await _get_db_connection()
    try:
        cursor = await conn.execute("SELECT timestamp FROM colors ORDER BY timestamp DESC LIMIT 1")
        latest_timestamp = await cursor.fetchone()
        if not latest_timestamp:
            return []
        
        cursor = await conn.execute(
            "SELECT color, turn_bonus, bloc_name FROM colors WHERE timestamp = ?",
            (latest_timestamp['timestamp'],)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await conn.close()

async def get_latest_resource_prices() -> Optional[Dict[str, Dict[str, float]]]:
    """Gets the most recent price entry from the resource database."""
    conn = await _get_db_connection()
    try:
        cursor = await conn.execute("SELECT timestamp FROM resource_prices ORDER BY timestamp DESC LIMIT 1")
        latest_timestamp = await cursor.fetchone()
        if not latest_timestamp:
            return None

        cursor = await conn.execute(
            "SELECT resource, avg_price, best_buy_price, best_sell_price FROM resource_prices WHERE timestamp = ?",
            (latest_timestamp['timestamp'],)
        )
        rows = await cursor.fetchall()
        return {
            row['resource']: {
                'avg': row['avg_price'],
                'buy': row['best_buy_price'],
                'sell': row['best_sell_price']
            } for row in rows
        }
    finally:
        await conn.close()

async def get_latest_resource_supply() -> Optional[Dict[str, float]]:
    """Gets the most recent resource supply data from the database."""
    conn = await _get_db_connection()
    try:
        cursor = await conn.execute("SELECT timestamp FROM resource_supply ORDER BY timestamp DESC LIMIT 1")
        latest_timestamp = await cursor.fetchone()
        if not latest_timestamp:
            return None

        cursor = await conn.execute(
            "SELECT resource, total_amount FROM resource_supply WHERE timestamp = ?",
            (latest_timestamp['timestamp'],)
        )
        rows = await cursor.fetchall()
        return {row['resource']: row['total_amount'] for row in rows}
    finally:
        await conn.close()

async def get_resource_prices_comparison() -> Dict[str, Any]:
    """Gets the latest and historical resource prices for comparison."""
    conn = await _get_db_connection()
    try:
        # Get the last 288 distinct timestamps (3 days of 15-minute intervals)
        cursor = await conn.execute("SELECT DISTINCT timestamp FROM resource_prices ORDER BY timestamp DESC LIMIT 288")
        timestamps = [row['timestamp'] for row in await cursor.fetchall()]
        
        logger.info(f"Found {len(timestamps)} distinct timestamps in resource_prices table")
        
        if len(timestamps) < 1:
            logger.warning("No timestamps found in resource_prices table")
            return {"current": {}, "previous": {}, "history": {}, "has_comparison_data": False}

        # Fetch all prices for these timestamps
        placeholders = ', '.join('?' * len(timestamps))
        cursor = await conn.execute(f"""
            SELECT timestamp, resource, avg_price, best_buy_price, best_sell_price 
            FROM resource_prices 
            WHERE timestamp IN ({placeholders})
        """, timestamps)
        rows = await cursor.fetchall()
        
        logger.info(f"Fetched {len(rows)} total price records from database")

        # Process into a dictionary keyed by timestamp
        prices_by_ts = {}
        for row in rows:
            ts = row['timestamp']
            if ts not in prices_by_ts:
                prices_by_ts[ts] = {}
            prices_by_ts[ts][row['resource']] = {
                'avg': row['avg_price'],
                'buy': row['best_buy_price'],
                'sell': row['best_sell_price']
            }

        latest_ts = timestamps[0]
        current_prices = prices_by_ts.get(latest_ts, {})
        previous_prices = {}
        
        if len(timestamps) > 1:
            previous_ts = timestamps[1]
            previous_prices = prices_by_ts.get(previous_ts, {})
        
        # Build historical data for each resource (including buy and sell prices)
        historical_data = {}
        if current_prices:
            for resource in current_prices.keys():
                resource_history = []
                # Iterate from oldest to newest timestamp
                for ts in reversed(timestamps):
                    if ts in prices_by_ts and resource in prices_by_ts[ts]:
                        price_data = prices_by_ts[ts][resource]
                        resource_history.append({
                            'avg': price_data['avg'],
                            'buy': price_data['buy'],
                            'sell': price_data['sell'],
                            'timestamp': ts
                        })
                historical_data[resource] = resource_history
        
        logger.info(f"Current prices: {len(current_prices)} resources, Previous prices: {len(previous_prices)} resources, Historical data: {len(historical_data)} resources")

        return {
            "current": current_prices,
            "previous": previous_prices,
            "history": historical_data,
            "has_comparison_data": len(timestamps) > 1
        }
    finally:
        await conn.close()

async def get_full_resource_price_history(resource: str) -> List[Dict[str, Any]]:
    """Gets the complete buy/sell price history for a single resource, oldest first."""
    conn = await _get_db_connection()
    try:
        cursor = await conn.execute(
            """
            SELECT timestamp, best_buy_price, best_sell_price
            FROM resource_prices
            WHERE resource = ?
            ORDER BY timestamp ASC
            """,
            (resource.lower(),)
        )
        rows = await cursor.fetchall()
        return [
            {"timestamp": row["timestamp"], "buy": row["best_buy_price"], "sell": row["best_sell_price"]}
            for row in rows
        ]
    finally:
        await conn.close()

async def get_resource_supply_comparison() -> Dict[str, Any]:
    """Gets the latest and historical resource supply data for comparison."""
    conn = await _get_db_connection()
    try:
        # Get the last 48 distinct timestamps
        cursor = await conn.execute("SELECT DISTINCT timestamp FROM resource_supply ORDER BY timestamp DESC LIMIT 48")
        timestamps = [row['timestamp'] for row in await cursor.fetchall()]
        
        if len(timestamps) < 1:
            return {"current": {}, "previous": {}, "history": {}}

        # Fetch all supply data for these timestamps
        placeholders = ', '.join('?' * len(timestamps))
        cursor = await conn.execute(f"""
            SELECT timestamp, resource, total_amount 
            FROM resource_supply 
            WHERE timestamp IN ({placeholders})
        """, timestamps)
        rows = await cursor.fetchall()

        # Process into a dictionary keyed by timestamp
        supply_by_ts = {}
        for row in rows:
            ts = row['timestamp']
            if ts not in supply_by_ts:
                supply_by_ts[ts] = {}
            supply_by_ts[ts][row['resource']] = row['total_amount']

        latest_ts = timestamps[0]
        previous_ts = timestamps[1] if len(timestamps) > 1 else latest_ts
        
        current_supply = supply_by_ts.get(latest_ts, {})
        previous_supply = supply_by_ts.get(previous_ts, {})
        
        # Build historical data for each resource
        historical_data = {}
        if current_supply:
            for resource in current_supply.keys():
                resource_history = []
                # Iterate from oldest to newest timestamp
                for ts in reversed(timestamps):
                    if ts in supply_by_ts and resource in supply_by_ts[ts]:
                        resource_history.append(supply_by_ts[ts][resource])
                historical_data[resource] = resource_history

        return {
            "current": current_supply,
            "previous": previous_supply,
            "history": historical_data
        }
    finally:
        await conn.close()

async def get_colors_comparison() -> Dict[str, Any]:
    """Gets the latest and second-to-latest color bonuses."""
    conn = await _get_db_connection()
    try:
        cursor = await conn.execute("SELECT DISTINCT timestamp FROM colors ORDER BY timestamp DESC LIMIT 2")
        timestamps = [row['timestamp'] for row in await cursor.fetchall()]

        if len(timestamps) < 2:
            latest_colors_list = await get_latest_game_data("colors") or []
            return {"current": {item['color']: item for item in latest_colors_list}, "previous": {item['color']: item for item in latest_colors_list}}

        latest_ts, previous_ts = timestamps

        # Fetch data for both timestamps in one query
        cursor = await conn.execute(
            "SELECT timestamp, color, turn_bonus, bloc_name FROM colors WHERE timestamp IN (?, ?)",
            (latest_ts, previous_ts)
        )
        rows = await cursor.fetchall()

        current_colors = {r['color']: {'bonus': r['turn_bonus'], 'bloc': r['bloc_name']} for r in rows if r['timestamp'] == latest_ts}
        previous_colors = {r['color']: {'bonus': r['turn_bonus'], 'bloc': r['bloc_name']} for r in rows if r['timestamp'] == previous_ts}

        return {
            "current": current_colors,
            "previous": previous_colors
        }
    finally:
        await conn.close()

async def get_resource_prices_for_range(start_ts: int, end_ts: int) -> List[Tuple[int, str, float]]:
    """Gets resource prices for a given time range."""
    conn = await _get_db_connection()
    try:
        cursor = await conn.execute(
            "SELECT timestamp, resource, avg_price FROM resource_prices WHERE timestamp BETWEEN ? AND ? ORDER BY timestamp",
            (start_ts, end_ts)
        )
        rows = await cursor.fetchall()
        return [(row['timestamp'], row['resource'], row['avg_price']) for row in rows]
    finally:
        await conn.close()

async def get_historical_resource_prices(days: int, min_entries: int) -> List[Tuple[int, str, float]]:
    """Gets historical resource prices for a given number of days."""
    end_ts = int(datetime.now().timestamp())
    start_ts = int((datetime.now() - timedelta(days=days)).timestamp())
    
    # This function can be expanded to extend the search period if needed.
    return await get_resource_prices_for_range(start_ts, end_ts)

async def get_comparison_resource_prices(hours_ago: int = 2) -> Dict[str, Dict[str, float]]:
    """Get prices from approximately N hours ago."""
    target_ts = int(datetime.now().timestamp()) - (hours_ago * 3600)
    conn = await _get_db_connection()
    try:
        # Find the timestamp closest to the target time
        cursor = await conn.execute(
            "SELECT timestamp FROM resource_prices ORDER BY ABS(timestamp - ?) ASC LIMIT 1",
            (target_ts,)
        )
        closest_ts_row = await cursor.fetchone()
        if not closest_ts_row:
            return {}

        # Fetch all prices for that timestamp
        cursor = await conn.execute(
            "SELECT resource, avg_price, best_buy_price, best_sell_price FROM resource_prices WHERE timestamp = ?",
            (closest_ts_row['timestamp'],)
        )
        rows = await cursor.fetchall()
        return {
            row['resource']: {
                'avg': row['avg_price'],
                'buy': row['best_buy_price'],
                'sell': row['best_sell_price']
            } for row in rows
        }
    finally:
        await conn.close()

async def get_all_time_resource_price_range() -> Tuple[Optional[int], Optional[int]]:
    """Get the min and max timestamp from the resource price data."""
    conn = await _get_db_connection()
    try:
        cursor = await conn.execute("SELECT MIN(timestamp), MAX(timestamp) FROM resource_prices")
        row = await cursor.fetchone()
        if row:
            return row[0], row[1]
        return None, None
    finally:
        await conn.close()

async def get_latest_resource_timestamp() -> int:
    """Gets the most recent timestamp from the resource_prices table."""
    conn = await _get_db_connection()
    try:
        cursor = await conn.execute("SELECT MAX(timestamp) as ts FROM resource_prices")
        row = await cursor.fetchone()
        return row['ts'] if row and row['ts'] else 0
    finally:
        await conn.close()

async def add_game_info(timestamp: int, game_date: str, city_average: float):
    """Saves game_date and city_average from the timed query."""
    conn = await _get_db_connection()
    try:
        await conn.execute(
            "INSERT OR REPLACE INTO game_info (timestamp, game_date, city_average) VALUES (?, ?, ?)",
            (timestamp, game_date, city_average)
        )
        await conn.commit()
    finally:
        await conn.close()

async def get_latest_game_info() -> Optional[Dict[str, Any]]:
    """Returns the most recent game_date and city_average from the DB."""
    conn = await _get_db_connection()
    try:
        cursor = await conn.execute(
            "SELECT game_date, city_average FROM game_info ORDER BY timestamp DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await conn.close()


async def add_radiation_data(timestamp: int, radiation_data: Dict[str, float]):
    """Add radiation data to the database.
    
    Args:
        timestamp: Unix timestamp
        radiation_data: Dict with keys: global, north_america, south_america, europe, africa, asia, australia, antarctica
    """
    conn = await _get_db_connection()
    try:
        await conn.execute("""
            INSERT OR REPLACE INTO radiation 
            (timestamp, global_level, north_america, south_america, europe, africa, asia, australia, antarctica)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            timestamp,
            radiation_data.get('global', 0.0),
            radiation_data.get('north_america', 0.0),
            radiation_data.get('south_america', 0.0),
            radiation_data.get('europe', 0.0),
            radiation_data.get('africa', 0.0),
            radiation_data.get('asia', 0.0),
            radiation_data.get('australia', 0.0),
            radiation_data.get('antarctica', 0.0)
        ))
        await conn.commit()
        logger.info(f"Added radiation data for timestamp {timestamp}")
    except Exception as e:
        logger.error(f"Error adding radiation data: {e}")
        raise
    finally:
        await conn.close()


async def get_latest_radiation_data() -> Optional[Dict[str, float]]:
    """Get the latest radiation data from the database.
    
    Returns:
        Dict with radiation levels by continent, or None if no data found
    """
    conn = await _get_db_connection()
    try:
        cursor = await conn.execute("""
            SELECT global_level, north_america, south_america, europe, africa, asia, australia, antarctica
            FROM radiation 
            ORDER BY timestamp DESC 
            LIMIT 1
        """)
        row = await cursor.fetchone()
        if row:
            return {
                'global': row[0],
                'north_america': row[1],
                'south_america': row[2],
                'europe': row[3],
                'africa': row[4],
                'asia': row[5],
                'australia': row[6],
                'antarctica': row[7]
            }
        return None
    except Exception as e:
        logger.error(f"Error getting latest radiation data: {e}")
        return None
    finally:
        await conn.close()

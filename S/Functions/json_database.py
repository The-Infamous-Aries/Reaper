import json
import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import aiofiles
import glob

# Base directory for JSON files
BASE_DATA_DIR = os.getenv("DATA_DIR", ".") + "/Systems/Data/ResourceStocks"
CONFIG_FILE = os.path.join(BASE_DATA_DIR, "config.json")
LIVE_MESSAGES_FILE = os.path.join(BASE_DATA_DIR, "live_messages.json")

# Ensure base directory exists
os.makedirs(BASE_DATA_DIR, exist_ok=True)

# File lock for thread-safe operations
_file_lock = asyncio.Lock()

async def _read_json_file(file_path: str) -> dict:
    """Read and parse a JSON file."""
    try:
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            return json.loads(content) if content else {}
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {file_path}: {e}")
        return {}
    except FileNotFoundError:
        return {}

async def _write_json_file(file_path: str, data: dict):
    """Write data to a JSON file."""
    async with _file_lock:
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(data, indent=2))

async def _get_weekly_filename(timestamp: int = None) -> str:
    """Get the filename for a weekly data file based on timestamp."""
    if timestamp is None:
        timestamp = int(datetime.now().timestamp())
    
    dt = datetime.fromtimestamp(timestamp)
    # Get the start of the week (Monday)
    week_start = dt - timedelta(days=dt.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    
    filename = f"resources_{week_start.strftime('%Y_%m_%d')}.json"
    return os.path.join(BASE_DATA_DIR, filename)

async def setup_json_database():
    """Initialize the JSON database system."""
    # Create config file if it doesn't exist
    await _write_json_file(CONFIG_FILE, await _read_json_file(CONFIG_FILE))
    
    # Create live messages file if it doesn't exist
    await _write_json_file(LIVE_MESSAGES_FILE, await _read_json_file(LIVE_MESSAGES_FILE))

async def add_prices(timestamp: int, prices: Dict[str, float]):
    """Add a new set of prices to the current week's JSON file."""
    filename = await _get_weekly_filename(timestamp)
    
    # Read existing data
    data = await _read_json_file(filename)
    
    # Create a formatted entry key from the timestamp
    entry_dt = datetime.fromtimestamp(timestamp)
    entry_key = entry_dt.strftime('%Y_%m_%d_%H_%M')
    
    # Add new prices
    data[entry_key] = prices
    
    # Write back to file
    await _write_json_file(filename, data)

async def get_prices_for_range(start_ts: int, end_ts: int, resource: Optional[str] = None) -> List[Tuple[int, str, float]]:
    """Get prices for a given time range and optional resource."""
    results = []
    
    # Get all weekly files in the range
    current_week = datetime.fromtimestamp(start_ts)
    end_week = datetime.fromtimestamp(end_ts)
    
    while current_week <= end_week:
        filename = await _get_weekly_filename(int(current_week.timestamp()))
        
        if os.path.exists(filename):
            data = await _read_json_file(filename)
            
            for entry_key, prices in data.items():
                # Parse entry key to get timestamp
                try:
                    entry_dt = datetime.strptime(entry_key, '%Y_%m_%d_%H_%M')
                    entry_ts = int(entry_dt.timestamp())
                    
                    # Check if in range
                    if start_ts <= entry_ts <= end_ts:
                        if resource:
                            if resource.lower() in prices:
                                results.append((entry_ts, resource.lower(), prices[resource.lower()]))
                        else:
                            for res_name, price in prices.items():
                                results.append((entry_ts, res_name, float(price)))
                except ValueError:
                    continue  # Skip invalid entry keys
        
        # Move to next week
        current_week += timedelta(weeks=1)
    
    return sorted(results)

async def get_historical_prices(days: int, min_entries: int) -> List[Tuple[int, str, float]]:
    """
    Gets historical prices for a given number of days, ensuring a minimum number of entries.
    It extends the search period if the initial fetch returns too little data.
    """
    end_ts = int(datetime.now().timestamp())
    start_ts = int((datetime.now() - timedelta(days=days)).timestamp())
    
    results = await get_prices_for_range(start_ts, end_ts)

    if len(results) < min_entries:
        for i in range(2, 5):
            extended_days = days * i
            extended_start_ts = int((datetime.now() - timedelta(days=extended_days)).timestamp())
            results = await get_prices_for_range(extended_start_ts, end_ts)
            if len(results) >= min_entries:
                break
    
    if len(results) < min_entries:
        min_ts, _ = await get_all_time_price_range()
        if min_ts:
            results = await get_prices_for_range(min_ts, end_ts)
            
    return results

async def get_latest_prices() -> Dict[str, float]:
    """Get the most recent prices from the latest weekly file."""
    # Get current week's file
    filename = await _get_weekly_filename()
    
    if not os.path.exists(filename):
        return {}
    
    data = await _read_json_file(filename)
    
    if not data:
        return {}
    
    # Get the most recent entry
    latest_entry = max(data.keys())
    return data.get(latest_entry, {})

async def get_comparison_prices(hours_ago: int = 2) -> Dict[str, float]:
    """Get prices from approximately N hours ago."""
    target_ts = int(datetime.now().timestamp()) - (hours_ago * 3600)
    
    # Get all prices around the target time
    # Look for entries within a 30-minute window
    window_start = target_ts - 1800  # 30 minutes before
    window_end = target_ts + 1800    # 30 minutes after
    
    prices = await get_prices_for_range(window_start, window_end)
    
    if not prices:
        return {}
    
    # Find the closest entry to target_ts
    closest_entry = None
    closest_diff = float('inf')
    
    for ts, resource, price in prices:
        diff = abs(ts - target_ts)
        if diff < closest_diff:
            closest_diff = diff
            closest_entry = ts
    
    # Return all prices from the closest entry
    result = {}
    for ts, resource, price in prices:
        if ts == closest_entry:
            result[resource] = price
    
    return result

async def set_global_config(key: str, value: str):
    """Set a global configuration value."""
    config = await _read_json_file(CONFIG_FILE)
    config[key] = value
    await _write_json_file(CONFIG_FILE, config)

async def get_global_config(key: str) -> Optional[str]:
    """Get a global configuration value."""
    config = await _read_json_file(CONFIG_FILE)
    return config.get(key)

async def _get_stats() -> dict:
    """Get cached stats, or recalculate if not present."""
    stats_str = await get_global_config("stats")
    if stats_str:
        return json.loads(stats_str)
    
    await _update_stats()
    stats_str = await get_global_config("stats")
    return json.loads(stats_str) if stats_str else {}

async def get_all_time_price_range() -> Tuple[Optional[int], Optional[int]]:
    """Get the min and max timestamp from all JSON files."""
    stats = await _get_stats()
    return (stats.get("min_ts"), stats.get("max_ts"))

async def add_live_message(guild_id: int, channel_id: int, message_id: int):
    """Add or update a live dashboard message for a guild."""
    messages = await _read_json_file(LIVE_MESSAGES_FILE)
    messages[str(guild_id)] = {
        "channel_id": channel_id,
        "message_id": message_id
    }
    await _write_json_file(LIVE_MESSAGES_FILE, messages)

async def remove_live_message(guild_id: int):
    """Remove the live dashboard message for a guild."""
    messages = await _read_json_file(LIVE_MESSAGES_FILE)
    if str(guild_id) in messages:
        del messages[str(guild_id)]
        await _write_json_file(LIVE_MESSAGES_FILE, messages)

async def get_all_live_messages() -> List[Tuple[int, int, int]]:
    """Get all configured live dashboard messages."""
    messages = await _read_json_file(LIVE_MESSAGES_FILE)
    return [(int(guild_id), data["channel_id"], data["message_id"]) for guild_id, data in messages.items()]

async def get_live_message(guild_id: int) -> Optional[Tuple[int, int, int]]:
    """Get the live dashboard message for a specific guild."""
    messages = await _read_json_file(LIVE_MESSAGES_FILE)
    data = messages.get(str(guild_id))
    if data:
        return (guild_id, data["channel_id"], data["message_id"])
    return None

async def cleanup_old_weekly_files(weeks_to_keep: int = 12):
    """Clean up old weekly files, keeping only the specified number of weeks."""
    pattern = os.path.join(BASE_DATA_DIR, "resources_*.json")
    files = glob.glob(pattern)
    
    if len(files) <= weeks_to_keep:
        return
    
    # Sort files by date (newest first)
    files.sort(reverse=True)
    
    # Remove old files
    for filename in files[weeks_to_keep:]:
        try:
            os.remove(filename)
            print(f"Removed old weekly file: {filename}")
        except Exception as e:
            print(f"Failed to remove {filename}: {e}")
    await _update_stats()

async def _update_stats():
    """Recalculate and cache stats about the data files."""
    pattern = os.path.join(BASE_DATA_DIR, "resources_*.json")
    files = glob.glob(pattern)
    
    total_files = len(files)
    total_entries = 0
    min_ts = None
    max_ts = None
    oldest_file = None
    newest_file = None
    
    for filename in files:
        data = await _read_json_file(filename)
        total_entries += len(data)
        
        try:
            basename = os.path.basename(filename)
            date_str = basename.replace("resources_", "").replace(".json", "")
            file_date = datetime.strptime(date_str, '%Y_%m_%d')
            
            if oldest_file is None or file_date < oldest_file:
                oldest_file = file_date
            if newest_file is None or file_date > newest_file:
                newest_file = file_date
        except ValueError:
            continue

        for entry_key in data.keys():
            try:
                entry_dt = datetime.strptime(entry_key, '%Y_%m_%d_%H_%M')
                entry_ts = int(entry_dt.timestamp())
                
                if min_ts is None or entry_ts < min_ts:
                    min_ts = entry_ts
                if max_ts is None or entry_ts > max_ts:
                    max_ts = entry_ts
            except ValueError:
                continue

    stats = {
        "total_files": total_files,
        "total_entries": total_entries,
        "min_ts": min_ts,
        "max_ts": max_ts,
        "oldest_file": oldest_file.strftime('%Y-%m-%d') if oldest_file else None,
        "newest_file": newest_file.strftime('%Y-%m-%d') if newest_file else None,
        "average_entries_per_file": total_entries / total_files if total_files > 0 else 0
    }
    await set_global_config("stats", json.dumps(stats))

async def get_weekly_stats() -> Dict[str, any]:
    """Get statistics about the weekly data files."""
    return await _get_stats()
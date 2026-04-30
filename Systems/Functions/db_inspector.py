"""
Database Inspector Tool

Allows for querying and viewing historical data from the Reaper database.

Usage:
    python db_inspector.py <resource_name> [--hours <hours>] [--limit <limit>]

Arguments:
    resource_name: The name of the resource to query (e.g., 'food', 'coal').
    --hours: Optional. The number of hours of data to retrieve.
    --limit: Optional. The maximum number of records to return.
"""
import asyncio
import argparse
from datetime import datetime, timedelta
import os
import sys

# Add project root to path to allow importing project modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import Systems.Functions.database_manager as db

async def inspect_data(resource: str, hours: int, limit: int):
    """Fetches and prints historical data for a given resource."""
    print(f"--- Querying data for '{resource.upper()}' ---")
    
    end_ts = int(datetime.now().timestamp())
    start_ts = int((datetime.now() - timedelta(hours=hours)).timestamp())
    
    try:
        conn = await db._get_db_connection()
        
        query = """
            SELECT timestamp, avg_price, best_buy_price, best_sell_price
            FROM resource_prices
            WHERE resource = ? AND timestamp BETWEEN ? AND ?
            ORDER BY timestamp DESC
        """
        params = [resource.lower(), start_ts, end_ts]
        
        if limit:
            query += " LIMIT ?"
            params.append(limit)
            
        cursor = await conn.execute(query, tuple(params))
        rows = await cursor.fetchall()
        
        if not rows:
            print("No data found for the specified criteria.")
            return
            
        print(f"Found {len(rows)} records:")
        print("{:<20} | {:>12} | {:>12} | {:>12}".format("Timestamp", "Avg Price", "Best Buy", "Best Sell"))
        print("-" * 62)
        
        for row in rows:
            ts_str = datetime.fromtimestamp(row['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
            print("{:<20} | {:>12.2f} | {:>12.2f} | {:>12.2f}".format(
                ts_str,
                row['avg_price'],
                row['best_buy_price'],
                row['best_sell_price']
            ))
            
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if conn:
            await conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Database Inspector Tool")
    parser.add_argument("resource", type=str, help="The name of the resource to query.")
    parser.add_argument("--hours", type=int, default=24, help="The number of hours of data to retrieve.")
    parser.add_argument("--limit", type=int, default=None, help="The maximum number of records to return.")
    
    args = parser.parse_args()
    
    asyncio.run(inspect_data(args.resource, args.hours, args.limit))

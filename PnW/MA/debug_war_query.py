import asyncio
import logging
import os
import re
import sys
from datetime import datetime, timedelta
from typing import Optional

# Add parent directory to path for config import and PnW.Util
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from Systems.PnW.Util.query import create_query_instance

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Re-implement _parse_time_limit_arg for standalone testing
def _parse_time_limit_arg(time_str: str) -> Optional[datetime]:
    """Parses a time limit argument like '2w', '14d', '3m' into a datetime object."""
    if not time_str:
        return None

    time_str = time_str.lower().strip()
    match = re.match(r"(\d+)([wdmh])", time_str)
    if not match:
        logger.warning(f"Invalid time_str format: {time_str}")
        return None

    value = int(match.group(1))
    unit = match.group(2)

    now = datetime.utcnow()
    if unit == 'w':
        return now - timedelta(weeks=value)
    elif unit == 'd':
        return now - timedelta(days=value)
    elif unit == 'm': # Assuming 'm' means months, but the original only mentions 'w' and 'd'
        # Approximating months as 30 days for simplicity, can be more precise if needed
        return now - timedelta(days=value * 30)
    elif unit == 'h': # Assuming 'h' means hours
        return now - timedelta(hours=value)
    return None

async def main():
    query_instance = create_query_instance(logger=logger)

    home_name = "Death Before Dishonor"
    away_name = "United Nations of TFL"
    time_arg = "2w"

    logger.info(f"Attempting to query war data for home: {home_name}, away: {away_name}, time_str: {time_arg}")

    # Resolve home alliance ID
    home_alliance_data = await query_instance.resolve_alliance(home_name)
    home_party_id = home_alliance_data['id'] if home_alliance_data else None
    logger.info(f"Resolved Home Alliance ({home_name}): ID = {home_party_id}")

    # Resolve away alliance ID
    away_alliance_data = await query_instance.resolve_alliance(away_name)
    away_party_id = away_alliance_data['id'] if away_alliance_data else None
    logger.info(f"Resolved Away Alliance ({away_name}): ID = {away_party_id}")

    if not home_party_id or not away_party_id:
        logger.error("Could not resolve one or both alliance IDs. Cannot proceed with war query.")
        return

    # Parse time limit
    time_limit = _parse_time_limit_arg(time_arg)
    logger.info(f"Parsed time limit for '{time_arg}': {time_limit}")

    # Call get_wars_between_parties
    logger.info(f"Calling get_wars_between_parties with home_party_id={home_party_id}, away_party_id={away_party_id}, before_date={time_limit}")
    war_data = await query_instance.get_wars_between_parties(
            home_alliance_ids=[int(home_party_id)],
            away_alliance_ids=[int(away_party_id)],
            cutoff_dt=time_limit,
            active_mode='inactive',
        )

    logger.info(f"Raw war data received (count: {len(war_data) if war_data else 0}):")
    for war in war_data:
        logger.info(f"  War ID: {war.get('id')}, Attacker: {war.get('att_name')}, Defender: {war.get('def_name')}, Date: {war.get('date')}")
        # Optionally print more details for a few wars
        # logger.info(f"    Details: {war}")

if __name__ == "__main__":
    asyncio.run(main())

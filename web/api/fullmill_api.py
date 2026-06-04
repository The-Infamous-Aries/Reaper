from fastapi import APIRouter, HTTPException
import logging
import asyncio
from typing import Dict, Any, List

from Systems.Functions.db_paths import GLOBAL_NATIONS_DB_STR
from PnWHarvester.db.global_nations_db import GlobalNationsDB
from Systems.PnW.Util.calc import AllianceCalculator
from Systems.PnW.Util.query import create_v3_query_instance

router = APIRouter()
logger = logging.getLogger("Reaper.WebServer.FullMillAPI")

# Cache for alliance mill data (TTL: 10 minutes)
_mill_cache: Dict[str, tuple] = {}
_CACHE_TTL = 600  # seconds

def _get_cache_key() -> str:
    """Generate cache key based on current time window."""
    import time
    return f"mill_{int(time.time() // _CACHE_TTL)}"

def _get_cached_data(cache_key: str) -> List[Dict[str, Any]] | None:
    """Get cached mill data if available and not expired."""
    import time
    if cache_key in _mill_cache:
        timestamp, data = _mill_cache[cache_key]
        if time.time() - timestamp < _CACHE_TTL:
            return data
    return None

def _set_cached_data(cache_key: str, data: List[Dict[str, Any]]) -> None:
    """Cache mill data with timestamp."""
    import time
    _mill_cache[cache_key] = (time.time(), data)

@router.get("/fullmill/rankings")
async def get_full_mill_rankings():
    """
    Return all game alliances ranked by their MAX MILL percent.
    
    MAX MILL percent is calculated as the percentage of current units vs buy caps
    across all active members (excluding APPS and Vacation Mode).
    
    Optimized to load all data in 2 database calls instead of thousands.
    """
    try:
        cache_key = _get_cache_key()
        cached = _get_cached_data(cache_key)
        if cached is not None:
            logger.info("Returning cached Full Mill rankings")
            return {"alliances": cached, "cached": True}
        
        logger.info("Building Full Mill rankings from scratch (optimized bulk load)")
        
        # Get GlobalNationsDB instance
        gn_db = GlobalNationsDB(GLOBAL_NATIONS_DB_STR)
        
        # OPTIMIZATION: Load all nations and all cities in just 2 database calls
        logger.info("Loading all nations from GlobalNationsDB...")
        all_nations = await gn_db.get_all_nations()
        logger.info(f"Loaded {len(all_nations)} nations")
        
        logger.info("Loading all cities in bulk...")
        cities_by_nation = await gn_db.get_all_cities_bulk()
        logger.info(f"Loaded cities for {len(cities_by_nation)} nations")
        
        # Attach cities to nations in memory (much faster than individual DB calls)
        for nation in all_nations:
            nation_id = nation.get('id')
            if nation_id and nation_id in cities_by_nation:
                nation['cities'] = cities_by_nation[nation_id]
            else:
                nation['cities'] = []
        
        # Group nations by alliance
        nations_by_alliance = {}
        for nation in all_nations:
            alliance_id = nation.get('alliance_id')
            if alliance_id:
                if alliance_id not in nations_by_alliance:
                    nations_by_alliance[alliance_id] = []
                nations_by_alliance[alliance_id].append(nation)
        
        logger.info(f"Grouped nations into {len(nations_by_alliance)} alliances")
        
        # Initialize calculator
        calculator = AllianceCalculator()
        
        # Process each alliance
        alliance_rankings = []
        
        for alliance_id, nations in nations_by_alliance.items():
            try:
                # Get alliance name from first nation
                alliance_name = nations[0].get('alliance_name') or f"Alliance {alliance_id}"
                
                # Calculate full mill data (automatically filters APPS and VM)
                mill_data = await calculator.calculate_full_mill_data(nations)
                
                # Skip alliances with no active nations
                if mill_data.get('active_nations', 0) == 0:
                    continue
                
                # Calculate max mill percentage for each unit type
                soldier_pct = (mill_data['current_soldiers'] / mill_data['max_soldiers'] * 100) if mill_data['max_soldiers'] > 0 else 0
                tank_pct = (mill_data['current_tanks'] / mill_data['max_tanks'] * 100) if mill_data['max_tanks'] > 0 else 0
                aircraft_pct = (mill_data['current_aircraft'] / mill_data['max_aircraft'] * 100) if mill_data['max_aircraft'] > 0 else 0
                ship_pct = (mill_data['current_ships'] / mill_data['max_ships'] * 100) if mill_data['max_ships'] > 0 else 0
                
                # Overall max mill percent (average of the 4 main unit types)
                overall_pct = (soldier_pct + tank_pct + aircraft_pct + ship_pct) / 4
                
                # Get alliance flag from nations (stored in alliance_flag field)
                flag = None
                for nation in nations:
                    if nation.get('alliance_flag'):
                        flag = nation.get('alliance_flag')
                        break
                
                alliance_rankings.append({
                    "id": alliance_id,
                    "name": alliance_name,
                    "flag": flag,
                    "total_nations": mill_data.get('total_nations', 0),
                    "active_nations": mill_data.get('active_nations', 0),
                    "total_cities": mill_data.get('total_cities', 0),
                    "total_score": mill_data.get('total_score', 0),
                    # Current units
                    "current_soldiers": mill_data.get('current_soldiers', 0),
                    "current_tanks": mill_data.get('current_tanks', 0),
                    "current_aircraft": mill_data.get('current_aircraft', 0),
                    "current_ships": mill_data.get('current_ships', 0),
                    "current_missiles": mill_data.get('current_missiles', 0),
                    "current_nukes": mill_data.get('current_nukes', 0),
                    # Max units (buy caps)
                    "max_soldiers": mill_data.get('max_soldiers', 0),
                    "max_tanks": mill_data.get('max_tanks', 0),
                    "max_aircraft": mill_data.get('max_aircraft', 0),
                    "max_ships": mill_data.get('max_ships', 0),
                    # Percentages
                    "soldier_percent": round(soldier_pct, 2),
                    "tank_percent": round(tank_pct, 2),
                    "aircraft_percent": round(aircraft_pct, 2),
                    "ship_percent": round(ship_pct, 2),
                    "overall_percent": round(overall_pct, 2),
                    # Daily production
                    "daily_soldiers": mill_data.get('daily_soldiers', 0),
                    "daily_tanks": mill_data.get('daily_tanks', 0),
                    "daily_aircraft": mill_data.get('daily_aircraft', 0),
                    "daily_ships": mill_data.get('daily_ships', 0),
                    "daily_missiles": mill_data.get('daily_missiles', 0),
                    "daily_nukes": mill_data.get('daily_nukes', 0),
                    # Gaps
                    "soldier_gap": mill_data.get('soldier_gap', 0),
                    "tank_gap": mill_data.get('tank_gap', 0),
                    "aircraft_gap": mill_data.get('aircraft_gap', 0),
                    "ship_gap": mill_data.get('ship_gap', 0),
                })
            except Exception as e:
                logger.warning(f"Error processing alliance {alliance_id}: {e}")
                continue
        
        # Sort by overall percent descending
        alliance_rankings.sort(key=lambda x: x.get('overall_percent', 0), reverse=True)
        
        # Cache the results
        _set_cached_data(cache_key, alliance_rankings)
        
        logger.info(f"Built Full Mill rankings for {len(alliance_rankings)} alliances (optimized)")
        return {"alliances": alliance_rankings, "cached": False}
        
    except Exception as e:
        logger.error(f"Error building Full Mill rankings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to build Full Mill rankings: {str(e)}")

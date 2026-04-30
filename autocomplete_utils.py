"""
Centralized autocomplete utilities for nations and alliances.
All autocomplete functions should use these to ensure consistent database usage.
"""

import logging
from typing import List, Optional, Dict, Any
from discord import app_commands

from Systems.Functions.db_paths import NW_NATIONS_DB, GLOBAL_NATIONS_DB
from Systems.Functions.irs_nations_db import IRSNationsDB
from PnWHarvester.db.global_nations_db import GlobalNationsDB
from Systems.Functions.nation_emoji_store import get_nation_emoji, strip_emoji_prefix

logger = logging.getLogger(__name__)

# Cache for performance
_nations_cache: List[Dict[str, Any]] = []
_alliances_cache: List[Dict[str, Any]] = []
_cache_timestamp: float = 0
_cache_ttl: float = 300  # 5 minutes

async def get_all_nations_from_db() -> List[Dict[str, Any]]:
    """Get all nations from both NW and Global databases."""
    import time
    global _nations_cache, _cache_timestamp
    
    current_time = time.time()
    if _nations_cache and current_time - _cache_timestamp < _cache_ttl:
        return _nations_cache
    
    nations = []
    try:
        # Get NW nations
        nw_db = IRSNationsDB(str(NW_NATIONS_DB))
        nw_nations = await nw_db.get_all_nations()
        nations.extend(nw_nations)
        
        # Get Global nations
        global_db = GlobalNationsDB(str(GLOBAL_NATIONS_DB))
        global_nations = await global_db.get_all_nations()
        nations.extend(global_nations)
        
        # Update cache
        _nations_cache = nations
        _cache_timestamp = current_time
        
        logger.debug(f"Loaded {len(nations)} nations from databases ({len(nw_nations)} NW, {len(global_nations)} Global)")
        
    except Exception as e:
        logger.error(f"Error loading nations from databases: {e}")
        # Return cached data if available
        return _nations_cache if _nations_cache else []
    
    return nations

async def get_all_alliances_from_db() -> List[Dict[str, Any]]:
    """Get all unique alliances from both NW and Global databases."""
    import time
    global _alliances_cache, _cache_timestamp
    
    current_time = time.time()
    if _alliances_cache and current_time - _cache_timestamp < _cache_ttl:
        return _alliances_cache
    
    alliances = {}  # Use dict to deduplicate by alliance_id
    try:
        # Get alliances from NW nations
        nw_db = IRSNationsDB(str(NW_NATIONS_DB))
        nw_nations = await nw_db.get_all_nations()
        for nation in nw_nations:
            aid = nation.get('alliance_id')
            if aid and aid not in alliances:
                alliance_name = nation.get('alliance', {}).get('name') if isinstance(nation.get('alliance'), dict) else None
                if not alliance_name:
                    # Try to get from nation data
                    alliance_name = nation.get('alliance_name')
                
                if alliance_name:
                    alliances[aid] = {
                        'alliance_id': aid,
                        'alliance_name': alliance_name,
                        'member_count': 1  # Will be updated below
                    }
        
        # Get alliances from Global nations
        global_db = GlobalNationsDB(str(GLOBAL_NATIONS_DB))
        try:
            # Try to use the get_distinct_alliances method if available
            if hasattr(global_db, 'get_distinct_alliances'):
                global_alliances = await global_db.get_distinct_alliances("")
                for alliance in global_alliances:
                    aid = alliance.get('alliance_id')
                    if aid and aid not in alliances:
                        alliances[aid] = alliance
            else:
                # Fallback: get all nations and extract alliances
                global_nations = await global_db.get_all_nations()
                for nation in global_nations:
                    aid = nation.get('alliance_id')
                    if aid and aid not in alliances:
                        alliance_name = nation.get('alliance', {}).get('name') if isinstance(nation.get('alliance'), dict) else None
                        if not alliance_name:
                            alliance_name = nation.get('alliance_name')
                        
                        if alliance_name:
                            alliances[aid] = {
                                'alliance_id': aid,
                                'alliance_name': alliance_name,
                                'member_count': 1
                            }
        except Exception as e:
            logger.debug(f"Could not get alliances from Global DB: {e}")
        
        # Convert to list and update cache
        _alliances_cache = list(alliances.values())
        _cache_timestamp = current_time
        
        logger.debug(f"Loaded {len(_alliances_cache)} unique alliances from databases")
        
    except Exception as e:
        logger.error(f"Error loading alliances from databases: {e}")
        return _alliances_cache if _alliances_cache else []
    
    return _alliances_cache

async def nation_autocomplete(current: str, nw_only: bool = False, limit: int = 25) -> List[app_commands.Choice[str]]:
    """
    Standard nation autocomplete using local databases.
    Returns up to `limit` choices from both IRSNations and GlobalNations DBs.
    When `current` is empty, returns the first `limit` nations alphabetically.
    
    Args:
        current: Current input text
        nw_only: If True, only show IRS nations
        limit: Maximum number of choices to return
    """
    current_lower = current.lower().strip() if current else ""
    choices = []
    seen_names: set = set()
    
    try:
        if nw_only:
            # Only NW nations
            nw_db = IRSNationsDB(str(NW_NATIONS_DB))
            nations = await nw_db.get_all_nations()
        else:
            # All nations from both DBs
            nations = await get_all_nations_from_db()
        
        for nation in nations:
            if len(choices) >= limit:
                break
            
            nation_name = nation.get('nation_name', '')
            leader_name = nation.get('leader_name', '')
            
            if not nation_name:
                continue
            
            # Deduplicate across the two DBs
            name_key = nation_name.lower()
            if name_key in seen_names:
                continue
            
            # If no input yet, show all (up to limit); otherwise filter by substring
            if current_lower:
                if not (current_lower in nation_name.lower() or
                        (leader_name and current_lower in leader_name.lower())):
                    continue
            
            seen_names.add(name_key)
            
            # Add emoji for this nation from the store
            emoji = get_nation_emoji(nation_name)
            display_name = f"{emoji} {nation_name}"
            if leader_name and leader_name != nation_name:
                display_name += f" ({leader_name})"
            
            choices.append(app_commands.Choice(
                name=display_name[:100],  # Discord limit
                value=nation_name
            ))
    
    except Exception as e:
        logger.error(f"Error in nation_autocomplete: {e}")
    
    return choices


async def alliance_autocomplete(current: str, include_nw: bool = True, limit: int = 25) -> List[app_commands.Choice[str]]:
    """
    Standard alliance autocomplete using local databases.
    
    Args:
        current: Current input text
        include_nw: If True, include IRS in results
        limit: Maximum number of choices to return
    """
    choices = []
    
    try:
        # Always add NW first if it matches
        if include_nw and (not current or current.lower() in "nights watch"):
            choices.append(app_commands.Choice(
                name="🌙 Nights Watch",
                value="Nights Watch"
            ))
        
        if not current or len(current.strip()) < 2:
            return choices
        
        current_lower = current.lower().strip()
        alliances = await get_all_alliances_from_db()
        
        for alliance in alliances:
            if len(choices) >= limit:
                break
            
            alliance_name = alliance.get('alliance_name', '')
            alliance_id = alliance.get('alliance_id')
            member_count = alliance.get('member_count', 0)
            
            # Skip NW if already added
            if str(alliance_id) == '14225':
                continue
            
            if alliance_name and current_lower in alliance_name.lower():
                display_name = f"🏛️ {alliance_name}"
                if member_count > 0:
                    display_name += f" ({member_count})"
                
                choices.append(app_commands.Choice(
                    name=display_name[:100],  # Discord limit
                    value=alliance_name
                ))
    
    except Exception as e:
        logger.error(f"Error in alliance_autocomplete: {e}")
    
    return choices

def clear_cache():
    """Clear the autocomplete cache to force refresh."""
    global _nations_cache, _alliances_cache, _cache_timestamp
    _nations_cache = []
    _alliances_cache = []
    _cache_timestamp = 0
    logger.info("Autocomplete cache cleared")

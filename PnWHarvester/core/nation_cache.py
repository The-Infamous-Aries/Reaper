"""
Nation and City Cache Manager

Provides a persistent in-memory cache for nation and city data to reduce
database load and improve performance for operations that need repeated access
to nation data (like revenue processing).
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class NationCache:
    """Persistent cache for nation and city data."""
    
    def __init__(self, global_nations_db):
        """
        Initialize the nation cache.
        
        Args:
            global_nations_db: GlobalNationsDB instance
        """
        self.global_nations_db = global_nations_db
        self._nations_cache: Dict[int, Dict[str, Any]] = {}
        self._cities_cache: Dict[int, List[Dict[str, Any]]] = {}
        self._cache_loaded = False
        self._last_refresh: Optional[datetime] = None
        self._refresh_interval = timedelta(hours=24)  # Refresh daily
        
    async def load_cache(self):
        """Load all nations and cities into cache."""
        logger.info("Loading nation and city cache...")
        start_time = datetime.now(timezone.utc)
        
        try:
            # Load all nations
            logger.info("Loading all nations into cache...")
            all_nations = await self.global_nations_db.get_all_nations()
            for nation in all_nations:
                nation_id = nation.get('id')
                if nation_id:
                    self._nations_cache[nation_id] = nation
            
            logger.info(f"Loaded {len(self._nations_cache)} nations into cache")
            
            # Load all cities in bulk (more efficient)
            logger.info("Loading all cities into cache (bulk)...")
            all_cities_bulk = await self.global_nations_db.get_all_cities_bulk()
            self._cities_cache = all_cities_bulk
            
            total_cities = sum(len(cities) for cities in self._cities_cache.values())
            logger.info(f"Loaded {total_cities} cities for {len(self._cities_cache)} nations")
            
            self._cache_loaded = True
            self._last_refresh = datetime.now(timezone.utc)
            
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(f"Cache loaded successfully in {elapsed:.1f}s")
            
        except Exception as e:
            logger.error(f"Failed to load cache: {e}", exc_info=True)
            raise
    
    async def refresh_cache(self):
        """Refresh the cache if it's stale."""
        if not self._cache_loaded:
            await self.load_cache()
            return
        
        if self._last_refresh and (datetime.now(timezone.utc) - self._last_refresh) < self._refresh_interval:
            logger.info("Cache is fresh, skipping refresh")
            return
        
        logger.info("Refreshing cache...")
        await self.load_cache()
    
    async def force_refresh(self):
        """Force an immediate cache refresh regardless of refresh interval."""
        logger.info("Forcing cache refresh...")
        await self.load_cache()
    
    def invalidate_nation(self, nation_id: int):
        """Invalidate a specific nation from cache (for single nation updates)."""
        if nation_id in self._nations_cache:
            del self._nations_cache[nation_id]
        if nation_id in self._cities_cache:
            del self._cities_cache[nation_id]
    
    def invalidate_all(self):
        """Invalidate the entire cache (force reload on next access)."""
        self._cache_loaded = False
        self._nations_cache.clear()
        self._cities_cache.clear()
        logger.info("Cache invalidated")
    
    def get_nation(self, nation_id: int) -> Optional[Dict[str, Any]]:
        """Get nation data from cache."""
        return self._nations_cache.get(nation_id)
    
    def get_cities(self, nation_id: int) -> List[Dict[str, Any]]:
        """Get cities for a nation from cache."""
        return self._cities_cache.get(nation_id, [])
    
    def get_nation_with_cities(self, nation_id: int) -> Optional[Dict[str, Any]]:
        """Get nation data with cities attached from cache."""
        nation = self._nations_cache.get(nation_id)
        if nation:
            nation_copy = nation.copy()
            nation_copy['cities'] = self._cities_cache.get(nation_id, [])
            return nation_copy
        return None
    
    def get_all_nation_ids(self) -> List[int]:
        """Get all cached nation IDs."""
        return list(self._nations_cache.keys())
    
    def is_loaded(self) -> bool:
        """Check if cache is loaded."""
        return self._cache_loaded
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_cities = sum(len(cities) for cities in self._cities_cache.values())
        return {
            'nations_count': len(self._nations_cache),
            'cities_count': total_cities,
            'loaded': self._cache_loaded,
            'last_refresh': self._last_refresh.isoformat() if self._last_refresh else None,
        }

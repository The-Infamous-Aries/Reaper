"""
Nation and City Cache Manager

Provides a persistent in-memory cache for nation and city data to reduce
database load and improve performance for operations that need repeated access
to nation data (like revenue processing).
"""

import asyncio
import logging
import copy
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

    def upsert_nation(self, nation: Dict[str, Any], merge: bool = True) -> bool:
        """Insert or merge a nation snapshot into the cache."""
        nation_id = nation.get("id")
        if not nation_id:
            return False

        nation_id = int(nation_id)
        cached = self._nations_cache.get(nation_id, {}) if merge else {}
        merged = dict(cached)
        merged.update({k: copy.deepcopy(v) for k, v in nation.items() if k != "cities"})
        merged["id"] = nation_id
        self._nations_cache[nation_id] = merged

        if "cities" in nation and isinstance(nation["cities"], list):
            self.replace_cities(nation_id, nation["cities"])
        return True

    def delete_nation(self, nation_id: int) -> None:
        """Remove a nation and all cached cities for it."""
        self._nations_cache.pop(int(nation_id), None)
        self._cities_cache.pop(int(nation_id), None)

    def upsert_city(self, nation_id: int, city: Dict[str, Any]) -> bool:
        """Insert or merge a city snapshot into the cache by city id."""
        city_id = city.get("id")
        if not city_id:
            return False

        nation_id = int(nation_id)
        city_id = int(city_id)
        cached_cities = list(self._cities_cache.get(nation_id, []))
        city_copy = {k: copy.deepcopy(v) for k, v in city.items()}
        city_copy["id"] = city_id
        city_copy["nation_id"] = nation_id

        for index, cached_city in enumerate(cached_cities):
            if int(cached_city.get("id") or 0) == city_id:
                merged = dict(cached_city)
                merged.update(city_copy)
                cached_cities[index] = merged
                break
        else:
            cached_cities.append(city_copy)

        self._cities_cache[nation_id] = cached_cities
        return True

    def delete_city(self, nation_id: int, city_id: int) -> bool:
        """Remove one city from the cached city list for a nation."""
        nation_id = int(nation_id)
        city_id = int(city_id)
        cached_cities = list(self._cities_cache.get(nation_id, []))
        filtered = [
            city for city in cached_cities
            if int(city.get("id") or 0) != city_id
        ]
        self._cities_cache[nation_id] = filtered
        return len(filtered) != len(cached_cities)

    def replace_cities(self, nation_id: int, cities: List[Dict[str, Any]]) -> None:
        """Replace the full cached city list for one nation."""
        nation_id = int(nation_id)
        self._cities_cache[nation_id] = [
            {**copy.deepcopy(city), "nation_id": int(city.get("nation_id") or nation_id)}
            for city in cities
            if city.get("id")
        ]

    def increment_num_cities(self, nation_id: int, amount: int = 1) -> None:
        """Increment cached num_cities for a nation if it is cached."""
        nation = self._nations_cache.get(int(nation_id))
        if not nation:
            return
        nation["num_cities"] = max(0, int(nation.get("num_cities") or 0) + int(amount))

    def update_alliance_info(
        self,
        alliance_id: int,
        alliance_name: Optional[str] = None,
        alliance_flag: Optional[str] = None,
    ) -> int:
        """Update cached alliance fields for all nations in an alliance."""
        updated = 0
        alliance_id = int(alliance_id)
        for nation in self._nations_cache.values():
            if int(nation.get("alliance_id") or 0) != alliance_id:
                continue
            if alliance_name is not None:
                nation["alliance_name"] = alliance_name
            if alliance_flag is not None:
                nation["alliance_flag"] = alliance_flag
            updated += 1
        return updated

    def clear_alliance_info(self, alliance_id: int) -> int:
        """Clear cached alliance fields for nations in a deleted alliance."""
        updated = 0
        alliance_id = int(alliance_id)
        for nation in self._nations_cache.values():
            if int(nation.get("alliance_id") or 0) != alliance_id:
                continue
            nation["alliance_id"] = 0
            nation["alliance_name"] = None
            nation["alliance_flag"] = None
            nation["alliance_position"] = None
            nation["alliance_seniority"] = None
            updated += 1
        return updated
    
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

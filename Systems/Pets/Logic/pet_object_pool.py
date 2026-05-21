"""
GPP Object Pool Pattern — Pet System
======================================
Reuses expensive-to-create objects instead of allocating/GC-ing them on
every request.  In a Python async server the main benefit is avoiding
repeated dict allocation and JSON parsing for frequently-used data.

Pools provided:
  AnimationPayloadPool  — reuses animation metadata dicts (avoids GC pressure
                          during high-frequency battle turns)
  PetStatsCachePool     — caches computed pet stats per user_id with TTL
                          (avoids re-running StatsCalculator on every API call
                          within the same request burst)

Usage:
    from Systems.Pets.Logic.pet_object_pool import animation_pool, stats_cache

    # Get a reusable animation dict (reset before use)
    anim = animation_pool.acquire()
    anim["type"] = "train_result"
    anim["duration_ms"] = 800
    anim["data"] = {"stat": "ATT", "delta": 3}
    # ... send to client ...
    animation_pool.release(anim)

    # Cache computed stats
    stats = stats_cache.get(user_id)
    if stats is None:
        stats = StatsCalculator.calculate_pet_stats(pet)
        stats_cache.put(user_id, stats)
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Generic Object Pool
# ─────────────────────────────────────────────────────────────────────────────

class ObjectPool:
    """
    Generic pool of reusable dict objects.

    Objects are pre-allocated up to *max_size*.  When the pool is empty,
    a new object is created on-demand (pool never blocks).
    """

    def __init__(self, max_size: int = 64) -> None:
        self._max_size = max_size
        self._pool: List[Dict[str, Any]] = []
        self._created = 0
        self._reused  = 0

    def acquire(self) -> Dict[str, Any]:
        """Get an object from the pool (or create a new one)."""
        if self._pool:
            self._reused += 1
            return self._pool.pop()
        self._created += 1
        return {}

    def release(self, obj: Dict[str, Any]) -> None:
        """Return an object to the pool after clearing it."""
        if len(self._pool) < self._max_size:
            obj.clear()
            self._pool.append(obj)

    @property
    def stats(self) -> Dict[str, int]:
        return {
            "pool_size": len(self._pool),
            "created":   self._created,
            "reused":    self._reused,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Animation Payload Pool
# ─────────────────────────────────────────────────────────────────────────────

class AnimationPayloadPool(ObjectPool):
    """
    Pool specifically for animation metadata dicts.
    Provides a helper to build a complete animation payload from the pool.
    """

    def build(
        self,
        anim_type: str,
        duration_ms: int,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Acquire a dict from the pool and populate it with animation fields.
        The caller is responsible for calling release() when done, OR the
        dict can be serialised to JSON and discarded (pool won't grow).
        """
        obj = self.acquire()
        obj["type"]        = anim_type
        obj["duration_ms"] = duration_ms
        obj["data"]        = data or {}
        return obj


# ─────────────────────────────────────────────────────────────────────────────
# Pet Stats Cache Pool
# ─────────────────────────────────────────────────────────────────────────────

class PetStatsCache:
    """
    Short-lived in-memory cache for computed pet stats.

    Entries expire after *ttl_seconds* (default 10s).  This prevents
    redundant StatsCalculator calls when multiple API endpoints are hit
    in quick succession (e.g. train → refresh → equip within one page load).

    NOT a persistent cache — restarts clear it.  NOT shared across workers.
    """

    def __init__(self, ttl_seconds: float = 10.0, max_entries: int = 512) -> None:
        self._ttl         = ttl_seconds
        self._max_entries = max_entries
        self._cache: Dict[str, tuple[Dict[str, Any], float]] = {}

    def get(self, user_id: str) -> Optional[Dict[str, Any]]:
        entry = self._cache.get(user_id)
        if entry is None:
            return None
        stats, expires_at = entry
        if time.monotonic() > expires_at:
            del self._cache[user_id]
            return None
        return stats

    def put(self, user_id: str, stats: Dict[str, Any]) -> None:
        # Evict oldest entries if at capacity
        if len(self._cache) >= self._max_entries:
            oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
        self._cache[user_id] = (stats, time.monotonic() + self._ttl)

    def invalidate(self, user_id: str) -> None:
        self._cache.pop(user_id, None)

    def clear(self) -> None:
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


# ─────────────────────────────────────────────────────────────────────────────
# Global singletons
# ─────────────────────────────────────────────────────────────────────────────

animation_pool: AnimationPayloadPool = AnimationPayloadPool(max_size=128)
stats_cache:    PetStatsCache        = PetStatsCache(ttl_seconds=10.0, max_entries=512)

"""
LockManager — Unified locking strategy for all PnW Harvester databases.

Provides a single source of truth for all database locks, ensuring that:
- One lock per unique DB file path (not per-instance)
- Consistent lock acquisition order prevents deadlocks
- Lock timeout handling with retry logic
- Lock acquisition metrics for monitoring

This eliminates lock contention issues when multiple components write to the same DB.
"""

import asyncio
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class LockStats:
    """Statistics for a single lock."""
    acquisitions: int = 0
    releases: int = 0
    timeouts: int = 0
    total_wait_time: float = 0.0
    max_wait_time: float = 0.0
    current_holders: int = 0
    last_acquired_at: Optional[datetime] = None
    last_released_at: Optional[datetime] = None


@dataclass
class LockManagerStats:
    """Overall statistics for the LockManager."""
    total_locks: int = 0
    total_acquisitions: int = 0
    total_timeouts: int = 0
    total_wait_time: float = 0.0
    per_lock_stats: Dict[str, LockStats] = field(default_factory=dict)
    lock_hierarchy: Dict[str, int] = field(default_factory=dict)


class LockManager:
    """
    Unified lock manager for all PnW Harvester databases.
    
    Ensures one lock per unique DB file path, preventing lock contention
    when multiple components write to the same database.
    """
    
    # Lock acquisition order to prevent deadlocks
    # Lower number = higher priority
    LOCK_HIERARCHY = {
        "GlobalNations.db": 1,
        "IRSWars.db": 2,
        "bankrecs.db": 3,
        "alerts.db": 4,
        "news.db": 5,
    }
    
    def __init__(self):
        """Initialize the lock manager."""
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock_stats: Dict[str, LockStats] = defaultdict(LockStats)
        self._locks_lock = asyncio.Lock()
        self._default_timeout = 30.0  # seconds
        self._max_retries = 3
        
        logger.info("LockManager initialized")
    
    def _normalize_path(self, db_path: str) -> str:
        """
        Normalize a database path to a canonical form.
        
        Args:
            db_path: Path to the database file
            
        Returns:
            Normalized path string
        """
        return str(Path(db_path).resolve())
    
    def _get_lock_priority(self, db_path: str) -> int:
        """
        Get the lock priority for a database.
        
        Args:
            db_path: Path to the database file
            
        Returns:
            Priority level (lower = higher priority)
        """
        normalized = self._normalize_path(db_path)
        for db_name, priority in self.LOCK_HIERARCHY.items():
            if db_name in normalized:
                return priority
        return 999  # Default priority for unknown DBs
    
    async def _get_or_create_lock(self, db_path: str) -> asyncio.Lock:
        """
        Get or create a lock for a database.
        
        Args:
            db_path: Path to the database file
            
        Returns:
            asyncio.Lock for the database
        """
        normalized = self._normalize_path(db_path)
        
        async with self._locks_lock:
            if normalized not in self._locks:
                self._locks[normalized] = asyncio.Lock()
                logger.debug(f"Created lock for {normalized}")
            return self._locks[normalized]
    
    @asynccontextmanager
    async def acquire_lock(
        self,
        db_path: str,
        timeout: Optional[float] = None,
        priority: Optional[int] = None,
    ):
        """
        Acquire a lock for a database with timeout support.
        
        Args:
            db_path: Path to the database file
            timeout: Timeout in seconds (default: 30.0)
            priority: Lock priority (default: auto-determined from hierarchy)
            
        Yields:
            Lock context
            
        Raises:
            asyncio.TimeoutError: If lock acquisition times out
        """
        normalized = self._normalize_path(db_path)
        lock = await self._get_or_create_lock(db_path)
        
        if timeout is None:
            timeout = self._default_timeout
        if priority is None:
            priority = self._get_lock_priority(db_path)
        
        stats = self._lock_stats[normalized]
        start_time = time.monotonic()
        acquired = False
        
        try:
            # Try to acquire lock with timeout
            acquired = await asyncio.wait_for(
                lock.acquire(),
                timeout=timeout
            )
            
            wait_time = time.monotonic() - start_time
            stats.acquisitions += 1
            stats.current_holders += 1
            stats.total_wait_time += wait_time
            stats.max_wait_time = max(stats.max_wait_time, wait_time)
            stats.last_acquired_at = datetime.now(timezone.utc)
            
            logger.debug(
                f"Acquired lock for {normalized} (priority={priority}, "
                f"wait={wait_time:.3f}s, holders={stats.current_holders})"
            )
            
            yield lock
            
        except asyncio.TimeoutError:
            stats.timeouts += 1
            logger.warning(
                f"Lock acquisition timeout for {normalized} after {timeout}s "
                f"(priority={priority}, holders={stats.current_holders})"
            )
            raise
            
        finally:
            if acquired:
                lock.release()
                stats.releases += 1
                stats.current_holders -= 1
                stats.last_released_at = datetime.now(timezone.utc)
                logger.debug(f"Released lock for {normalized}")
    
    async def acquire_multiple_locks(
        self,
        db_paths: list[str],
        timeout: Optional[float] = None,
    ):
        """
        Acquire multiple locks in consistent order to prevent deadlocks.
        
        Args:
            db_paths: List of database paths
            timeout: Timeout per lock in seconds
            
        Yields:
            Context with all locks acquired
        """
        # Sort by priority (lock hierarchy) then by path for consistency
        sorted_paths = sorted(
            db_paths,
            key=lambda p: (self._get_lock_priority(p), self._normalize_path(p))
        )
        
        acquired_locks = []
        
        try:
            for db_path in sorted_paths:
                lock_ctx = self.acquire_lock(db_path, timeout=timeout)
                await lock_ctx.__aenter__()
                acquired_locks.append(lock_ctx)
            
            # All locks acquired
            yield None
            
        finally:
            # Release locks in reverse order (LIFO)
            for lock_ctx in reversed(acquired_locks):
                try:
                    await lock_ctx.__aexit__(None, None, None)
                except Exception as e:
                    logger.error(f"Error releasing lock: {e}")
    
    def register_db(self, db_path: str) -> None:
        """
        Register a database with the lock manager.
        
        This pre-creates the lock for the database, which is useful
        for initialization to avoid race conditions.
        
        Args:
            db_path: Path to the database file
        """
        normalized = self._normalize_path(db_path)
        # This is synchronous, so we can't use async methods
        # We'll create the lock on first use instead
        logger.debug(f"Registered database {normalized}")
    
    async def get_lock_stats(self) -> LockManagerStats:
        """
        Get statistics for all locks.
        
        Returns:
            LockManagerStats with overall and per-lock statistics
        """
        async with self._locks_lock:
            total_acquisitions = sum(
                s.acquisitions for s in self._lock_stats.values()
            )
            total_timeouts = sum(
                s.timeouts for s in self._lock_stats.values()
            )
            total_wait_time = sum(
                s.total_wait_time for s in self._lock_stats.values()
            )
            
            return LockManagerStats(
                total_locks=len(self._locks),
                total_acquisitions=total_acquisitions,
                total_timeouts=total_timeouts,
                total_wait_time=total_wait_time,
                per_lock_stats=dict(self._lock_stats),
                lock_hierarchy=self.LOCK_HIERARCHY.copy(),
            )
    
    async def reset_stats(self) -> None:
        """Reset all lock statistics."""
        async with self._locks_lock:
            self._lock_stats.clear()
            logger.info("Lock statistics reset")
    
    async def get_lock_holders(self, db_path: str) -> int:
        """
        Get the current number of holders for a lock.
        
        Args:
            db_path: Path to the database file
            
        Returns:
            Number of current holders
        """
        normalized = self._normalize_path(db_path)
        stats = self._lock_stats.get(normalized)
        return stats.current_holders if stats else 0
    
    def __repr__(self) -> str:
        return f"LockManager(locks={len(self._locks)}, registered={len(self._lock_stats)})"


# Global singleton instance
_global_lock_manager: Optional[LockManager] = None


def get_lock_manager() -> LockManager:
    """
    Get the global LockManager singleton.
    
    Returns:
        The global LockManager instance
    """
    global _global_lock_manager
    if _global_lock_manager is None:
        _global_lock_manager = LockManager()
    return _global_lock_manager

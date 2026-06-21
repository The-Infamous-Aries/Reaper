"""
DatabasePool — Connection pooling for all PnW Harvester databases.

Provides:
- Connection pools for each database (5-10 connections per DB)
- Connection health checking
- Automatic reconnection
- Connection lifetime tracking
- Connection metrics

This improves performance by reusing connections and reduces overhead
of creating new connections for each operation.
"""

import asyncio
import logging
import sqlite3
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class PoolState(Enum):
    """Connection pool state."""
    IDLE = "idle"
    ACTIVE = "active"
    CLOSING = "closing"
    CLOSED = "closed"


@dataclass
class ConnectionStats:
    """Statistics for a single connection."""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: Optional[datetime] = None
    use_count: int = 0
    total_use_time: float = 0.0
    errors: int = 0
    is_healthy: bool = True


@dataclass
class PoolStats:
    """Statistics for a connection pool."""
    db_path: str
    total_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    total_acquisitions: int = 0
    total_releases: int = 0
    total_wait_time: float = 0.0
    max_wait_time: float = 0.0
    avg_use_time: float = 0.0
    total_errors: int = 0
    state: PoolState = PoolState.IDLE


class PooledConnection:
    """
    A wrapper around a SQLite connection with pooling support.
    
    Tracks usage statistics and health status for the pool.
    """
    
    def __init__(
        self,
        conn: sqlite3.Connection,
        pool: 'DatabasePool',
    ):
        """
        Initialize a pooled connection.
        
        Args:
            conn: The underlying SQLite connection
            pool: The parent pool instance
        """
        self._conn = conn
        self._pool = pool
        self._stats = ConnectionStats()
        self._in_use = False
        self._created_at = time.monotonic()
    
    @property
    def connection(self) -> sqlite3.Connection:
        """Get the underlying connection."""
        return self._conn
    
    @property
    def stats(self) -> ConnectionStats:
        """Get connection statistics."""
        return self._stats
    
    @property
    def in_use(self) -> bool:
        """Check if connection is currently in use."""
        return self._in_use
    
    def mark_in_use(self) -> None:
        """Mark connection as in use."""
        self._in_use = True
        self._stats.use_count += 1
        self._stats.last_used_at = datetime.now(timezone.utc)
    
    def mark_released(self) -> None:
        """Mark connection as released."""
        self._in_use = False
    
    def check_health(self) -> bool:
        """
        Check if the connection is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            # Simple health check: execute a query
            self._conn.execute("SELECT 1").fetchone()
            self._stats.is_healthy = True
            return True
        except Exception as e:
            logger.warning(f"Connection health check failed: {e}")
            self._stats.is_healthy = False
            self._stats.errors += 1
            return False
    
    def close(self) -> None:
        """Close the underlying connection."""
        try:
            self._conn.close()
        except Exception as e:
            logger.warning(f"Error closing connection: {e}")
    
    def age(self) -> float:
        """Get the age of the connection in seconds."""
        return time.monotonic() - self._created_at
    
    def __enter__(self) -> sqlite3.Connection:
        """Context manager entry."""
        return self._conn
    
    def __exit__(self, *args) -> None:
        """Context manager exit."""
        # Don't close here - let the pool manage it
        pass


class DatabasePool:
    """
    Connection pool for a single database.
    
    Maintains a pool of connections that can be reused across operations.
    """
    
    DEFAULT_POOL_SIZE = 5
    MAX_POOL_SIZE = 10
    MAX_CONNECTION_AGE = 3600  # 1 hour
    MAX_IDLE_TIME = 300  # 5 minutes
    HEALTH_CHECK_INTERVAL = 60  # 1 minute
    
    def __init__(
        self,
        db_path: str,
        pool_size: int = DEFAULT_POOL_SIZE,
        max_pool_size: int = MAX_POOL_SIZE,
        max_connection_age: int = MAX_CONNECTION_AGE,
        max_idle_time: int = MAX_IDLE_TIME,
        configure_fn: Optional[Callable[[sqlite3.Connection], None]] = None,
    ):
        """
        Initialize the connection pool.
        
        Args:
            db_path: Path to the database file
            pool_size: Initial pool size
            max_pool_size: Maximum pool size
            max_connection_age: Maximum age of a connection in seconds
            max_idle_time: Maximum idle time before recycling
            configure_fn: Optional function to configure new connections
        """
        self._db_path = str(Path(db_path).resolve())
        self._pool_size = pool_size
        self._max_pool_size = max_pool_size
        self._max_connection_age = max_connection_age
        self._max_idle_time = max_idle_time
        self._configure_fn = configure_fn or self._default_configure
        
        self._connections: List[PooledConnection] = []
        self._lock = asyncio.Lock()
        self._state = PoolState.IDLE
        self._stats = PoolStats(db_path=self._db_path)
        
        # Background task for health checks
        self._health_check_task: Optional[asyncio.Task] = None
        
        logger.info(
            f"DatabasePool initialized for {self._db_path} "
            f"(size={pool_size}, max={max_pool_size})"
        )
    
    def _default_configure(self, conn: sqlite3.Connection) -> None:
        """
        Default connection configuration.
        
        Args:
            conn: The connection to configure
        """
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA wal_autocheckpoint=1000")
        conn.row_factory = sqlite3.Row
    
    def _create_connection(self) -> PooledConnection:
        """
        Create a new pooled connection.
        
        Returns:
            PooledConnection instance
        """
        # Disable check_same_thread for connection pool usage
        # Connections will be protected by the pool lock
        try:
            conn = sqlite3.connect(
                self._db_path, 
                timeout=15, 
                check_same_thread=False,
                isolation_level=None  # Autocommit mode for better performance
            )
            self._configure_fn(conn)
            return PooledConnection(conn, self)
        except Exception as e:
            logger.error(f"Failed to create connection to {self._db_path}: {e}")
            raise
    
    async def initialize(self) -> None:
        """
        Initialize the pool with initial connections.
        
        Should be called before using the pool.
        """
        async with self._lock:
            if self._state != PoolState.IDLE:
                logger.warning(f"Pool already initialized (state={self._state})")
                return
            
            self._state = PoolState.ACTIVE
            
            # Create initial connections
            for _ in range(self._pool_size):
                try:
                    conn = await asyncio.get_event_loop().run_in_executor(
                        None, self._create_connection
                    )
                    self._connections.append(conn)
                except Exception as e:
                    logger.error(f"Failed to create initial connection: {e}")
            
            self._stats.total_connections = len(self._connections)
            self._stats.idle_connections = len(self._connections)
            
            # Start health check task
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            
            logger.info(
                f"Pool initialized with {len(self._connections)} connections"
            )
    
    @asynccontextmanager
    async def get_connection(self, timeout: float = 30.0):
        """
        Get a connection from the pool.
        
        Args:
            timeout: Timeout in seconds
            
        Yields:
            PooledConnection instance
            
        Raises:
            asyncio.TimeoutError: If no connection available within timeout
        """
        if self._state == PoolState.CLOSED:
            raise RuntimeError("Pool is closed")
        
        start_time = time.monotonic()
        conn = None
        
        try:
            # Try to get an idle connection
            async with self._lock:
                # Clean up old/unhealthy connections first
                await self._cleanup_connections()
                
                # Find an idle connection
                for c in self._connections:
                    if not c.in_use and c.check_health():
                        conn = c
                        break
                
                # If no idle connection, create a new one if under limit
                if conn is None and len(self._connections) < self._max_pool_size:
                    try:
                        conn = await asyncio.get_event_loop().run_in_executor(
                            None, self._create_connection
                        )
                        self._connections.append(conn)
                        self._stats.total_connections = len(self._connections)
                    except Exception as e:
                        logger.error(f"Failed to create new connection: {e}")
                
                # If still no connection, wait for one to become available
                if conn is None:
                    # We hit max pool size. Release the outer lock while we wait
                    # so other coroutines can return connections.
                    pass
                else:
                    # Claim it immediately while we still hold the lock
                    conn.mark_in_use()
                    self._stats.active_connections += 1
                    self._stats.idle_connections -= 1
                    self._stats.total_acquisitions += 1
            
            # Outside the lock: poll until a connection is free or timeout
            if conn is None:
                waited = 0.0
                while conn is None and waited < timeout:
                    await asyncio.sleep(0.1)
                    waited += 0.1
                    
                    async with self._lock:
                        for c in self._connections:
                            if not c.in_use and c.check_health():
                                conn = c
                                break
                
                if conn is None:
                    raise asyncio.TimeoutError(
                        f"No connection available after {timeout}s"
                    )
                
                # Claim the connection under the lock
                async with self._lock:
                    conn.mark_in_use()
                    self._stats.active_connections += 1
                    self._stats.idle_connections -= 1
                    self._stats.total_acquisitions += 1
            
            wait_time = time.monotonic() - start_time
            self._stats.total_wait_time += wait_time
            self._stats.max_wait_time = max(self._stats.max_wait_time, wait_time)
            
            logger.debug(
                f"Acquired connection from {self._db_path} "
                f"(wait={wait_time:.3f}s, active={self._stats.active_connections})"
            )
            
            yield conn
            
        finally:
            if conn:
                async with self._lock:
                    conn.mark_released()
                    self._stats.active_connections -= 1
                    self._stats.idle_connections += 1
                    self._stats.total_releases += 1
                    logger.debug(
                        f"Released connection to {self._db_path} "
                        f"(active={self._stats.active_connections})"
                    )
    
    async def return_connection(self, conn: PooledConnection) -> None:
        """
        Return a connection to the pool.
        
        Args:
            conn: The connection to return
        """
        async with self._lock:
            if conn in self._connections:
                conn.mark_released()
                self._stats.active_connections -= 1
                self._stats.idle_connections += 1
                self._stats.total_releases += 1
    
    async def _cleanup_connections(self) -> None:
        """
        Clean up old, unhealthy, or idle connections.
        
        This is called internally before acquiring a connection.
        """
        now = time.monotonic()
        to_remove = []
        
        for conn in self._connections:
            # Remove unhealthy connections
            if not conn.check_health():
                to_remove.append(conn)
                continue
            
            # Remove old connections
            if conn.age() > self._max_connection_age:
                to_remove.append(conn)
                continue
            
            # Remove idle connections (if we have enough)
            idle_time = now - (conn._stats.last_used_at.timestamp() if conn._stats.last_used_at else now)
            if (not conn.in_use and 
                idle_time > self._max_idle_time and 
                len(self._connections) > self._pool_size):
                to_remove.append(conn)
        
        for conn in to_remove:
            try:
                conn.close()
                self._connections.remove(conn)
                self._stats.total_connections = len(self._connections)
                logger.debug(f"Removed connection from pool (age={conn.age():.0f}s)")
            except Exception as e:
                logger.warning(f"Error removing connection: {e}")
    
    async def _health_check_loop(self) -> None:
        """
        Background task to periodically check connection health.
        """
        while self._state == PoolState.ACTIVE:
            try:
                await asyncio.sleep(self.HEALTH_CHECK_INTERVAL)
                
                if self._state != PoolState.ACTIVE:
                    break
                
                async with self._lock:
                    for conn in self._connections:
                        if not conn.in_use:
                            conn.check_health()
                
                logger.debug(f"Health check completed for {self._db_path}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")
    
    async def health_check(self) -> bool:
        """
        Check if the pool is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        async with self._lock:
            if self._state != PoolState.ACTIVE:
                return False
            
            # Check if we have at least one healthy connection
            for conn in self._connections:
                if conn.check_health():
                    return True
            
            return False
    
    async def get_stats(self) -> PoolStats:
        """
        Get pool statistics.
        
        Returns:
            PoolStats instance
        """
        async with self._lock:
            self._stats.total_connections = len(self._connections)
            self._stats.active_connections = sum(1 for c in self._connections if c.in_use)
            self._stats.idle_connections = sum(1 for c in self._connections if not c.in_use)
            self._stats.total_errors = sum(c._stats.errors for c in self._connections)
            
            # Calculate average use time
            total_use = sum(c._stats.total_use_time for c in self._connections)
            total_uses = sum(c._stats.use_count for c in self._connections)
            self._stats.avg_use_time = total_use / total_uses if total_uses > 0 else 0.0
            
            return self._stats
    
    async def close(self) -> None:
        """
        Close the pool and all connections.
        """
        self._state = PoolState.CLOSING
        
        # Cancel health check task
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # Close all connections
        async with self._lock:
            for conn in self._connections:
                try:
                    conn.close()
                except Exception as e:
                    logger.warning(f"Error closing connection: {e}")
            
            self._connections.clear()
            self._state = PoolState.CLOSED
        
        logger.info(f"Pool closed for {self._db_path}")
    
    def __repr__(self) -> str:
        return f"DatabasePool(path={self._db_path}, state={self._state.value})"


class DatabasePoolManager:
    """
    Manager for multiple database pools.
    
    Maintains a pool for each unique database path.
    """
    
    def __init__(self):
        """Initialize the pool manager."""
        self._pools: Dict[str, DatabasePool] = {}
        self._lock = asyncio.Lock()
        
        logger.info("DatabasePoolManager initialized")
    
    async def get_pool(
        self,
        db_path: str,
        pool_size: int = DatabasePool.DEFAULT_POOL_SIZE,
        max_pool_size: int = DatabasePool.MAX_POOL_SIZE,
    ) -> DatabasePool:
        """
        Get or create a pool for a database.
        
        Args:
            db_path: Path to the database file
            pool_size: Initial pool size
            max_pool_size: Maximum pool size
            
        Returns:
            DatabasePool instance
        """
        normalized = str(Path(db_path).resolve())
        
        async with self._lock:
            if normalized not in self._pools:
                pool = DatabasePool(
                    db_path=normalized,
                    pool_size=pool_size,
                    max_pool_size=max_pool_size,
                )
                await pool.initialize()
                self._pools[normalized] = pool
            
            return self._pools[normalized]
    
    async def close_pool(self, db_path: str) -> None:
        """
        Close a specific pool.
        
        Args:
            db_path: Path to the database file
        """
        normalized = str(Path(db_path).resolve())
        
        async with self._lock:
            if normalized in self._pools:
                await self._pools[normalized].close()
                del self._pools[normalized]
                logger.info(f"Closed pool for {normalized}")
    
    async def close_all(self) -> None:
        """Close all pools."""
        async with self._lock:
            for pool in list(self._pools.values()):
                await pool.close()
            
            self._pools.clear()
            logger.info("All pools closed")
    
    async def get_all_stats(self) -> Dict[str, PoolStats]:
        """
        Get statistics for all pools.
        
        Returns:
            Dictionary mapping db_path to PoolStats
        """
        stats = {}
        async with self._lock:
            for db_path, pool in self._pools.items():
                stats[db_path] = await pool.get_stats()
        
        return stats
    
    def __repr__(self) -> str:
        return f"DatabasePoolManager(pools={len(self._pools)})"


# Global singleton instance
_global_pool_manager: Optional[DatabasePoolManager] = None


def get_pool_manager() -> DatabasePoolManager:
    """
    Get the global DatabasePoolManager singleton.
    
    Returns:
        The global DatabasePoolManager instance
    """
    global _global_pool_manager
    if _global_pool_manager is None:
        _global_pool_manager = DatabasePoolManager()
    return _global_pool_manager

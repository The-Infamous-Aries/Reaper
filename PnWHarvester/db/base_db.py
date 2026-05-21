"""
BaseDB — Unified database component for all PnW Harvester databases.

Provides:
- Unified async connection management (configurable: aiosqlite vs thread-pool executor)
- Standardized locking strategy using LockManager (per-DB file locks)
- Common WAL/synchronous/busy_timeout configuration
- Shared _run_sync executor pattern
- Standardized error handling and logging
- Migration helper methods
- Backup/verification capabilities

This eliminates code duplication across GlobalNationsDB, HoldingsDB, BankrecsDB,
GlobalWarsDB, NewsDB, and IRSWarsDB while preserving ALL existing functionality.
"""

import sqlite3
import logging
import asyncio
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, TypeVar, Union
from enum import Enum

logger = logging.getLogger(__name__)

T = TypeVar('T')


class AsyncMode(Enum):
    """Async execution mode for database operations."""
    THREAD_POOL = "thread_pool"  # Use loop.run_in_executor with sqlite3
    AIOSQLITE = "aiosqlite"      # Use native aiosqlite (if available)


class BaseDB:
    """
    Base database component with unified async patterns and connection management.
    
    All PnW Harvester databases should inherit from this class to ensure consistent
    behavior, eliminate code duplication, and provide data integrity guarantees.
    
    Features:
    - Configurable async mode (thread_pool or aiosqlite)
    - Standardized WAL mode, synchronous, busy_timeout settings
    - Automatic schema migration support
    - Backup/verification before destructive operations
    - Comprehensive error handling and logging
    - Checkpoint management for WAL files
    """
    
    def __init__(
        self,
        db_path: str,
        async_mode: AsyncMode = AsyncMode.THREAD_POOL,
        wal_mode: bool = True,
        synchronous: str = "NORMAL",
        busy_timeout: int = 15000,
        wal_autocheckpoint: int = 1000,
        enable_locking: bool = True,
        use_lock_manager: bool = True,
    ):
        """
        Initialize the base database component.
        
        Args:
            db_path: Path to the SQLite database file
            async_mode: Async execution mode (thread_pool or aiosqlite)
            wal_mode: Enable WAL journal mode for better concurrency
            synchronous: Synchronous setting (FULL, NORMAL, OFF)
            busy_timeout: Timeout in milliseconds for busy database
            wal_autocheckpoint: WAL auto-checkpoint interval
            enable_locking: Enable asyncio.Lock for database operations
            use_lock_manager: Use global LockManager for unified locking
        """
        self.db_path = db_path
        self.async_mode = async_mode
        self.wal_mode = wal_mode
        self.synchronous = synchronous
        self.busy_timeout = busy_timeout
        self.wal_autocheckpoint = wal_autocheckpoint
        self.enable_locking = enable_locking
        self.use_lock_manager = use_lock_manager
        
        # Lock management - use LockManager if enabled
        if use_lock_manager and enable_locking:
            try:
                from ..core.lock_manager import get_lock_manager
                self._lock_manager = get_lock_manager()
                self._lock = None  # LockManager handles locking
                logger.debug(f"Using LockManager for {db_path}")
            except ImportError:
                logger.warning("LockManager not available, falling back to local lock")
                self._lock_manager = None
                self._lock = asyncio.Lock()
        else:
            self._lock_manager = None
            self._lock = asyncio.Lock() if enable_locking else None
        
        self._key_locks: Dict[str, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()
        
        # Ensure parent directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self._init_database()
        
        logger.info(
            f"BaseDB initialized: {db_path} "
            f"(mode={async_mode.value}, wal={wal_mode}, sync={synchronous}, "
            f"lock_manager={use_lock_manager})"
        )
    
    def _get_lock(self, key: Optional[str] = None) -> Any:
        """
        Get the appropriate lock for an operation.
        
        Args:
            key: Optional key for per-key locking. If None, returns the global lock.
        
        Returns:
            The appropriate lock context manager for the operation
        """
        if not self.enable_locking:
            # Return a no-op lock if locking is disabled
            class NoOpLock:
                async def __aenter__(self): pass
                async def __aexit__(self, *args): pass
            return NoOpLock()
        
        # Use LockManager if available
        if self._lock_manager:
            # LockManager returns an async context manager
            return self._lock_manager.acquire_lock(self.db_path)
        
        # Fall back to local lock
        if key is None:
            return self._lock if self._lock else self._no_op_lock()
        
        # Per-key locking (local fallback)
        async def _get_key_lock():
            async with self._locks_lock:
                if key not in self._key_locks:
                    self._key_locks[key] = asyncio.Lock()
                return self._key_locks[key]
        
        # For now, return global lock if key provided (TODO: proper async per-key locking)
        return self._lock if self._lock else self._no_op_lock()
    
    def _no_op_lock(self) -> Any:
        """Return a no-op lock context manager."""
        class NoOpLock:
            async def __aenter__(self): pass
            async def __aexit__(self, *args): pass
        return NoOpLock()
    
    def _configure_connection(self, conn: sqlite3.Connection) -> None:
        """
        Configure a SQLite connection with standard settings.
        
        Args:
            conn: The SQLite connection to configure
        """
        if self.wal_mode:
            conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA synchronous={self.synchronous}")
        conn.execute(f"PRAGMA busy_timeout={self.busy_timeout}")
        if self.wal_mode:
            conn.execute(f"PRAGMA wal_autocheckpoint={self.wal_autocheckpoint}")
        conn.row_factory = sqlite3.Row
    
    def _get_connection(self) -> sqlite3.Connection:
        """
        Get a configured SQLite connection.
        
        Returns:
            A configured SQLite connection
        """
        conn = sqlite3.connect(self.db_path, timeout=self.busy_timeout // 1000)
        self._configure_connection(conn)
        return conn
    
    def _init_database(self) -> None:
        """
        Initialize the database schema. Override in subclasses.
        
        This base implementation ensures the database file exists and is configured.
        Subclasses should override this to create their specific tables.
        """
        try:
            with self._get_connection() as conn:
                # Just verify the connection works
                conn.execute("SELECT 1").fetchone()
        except Exception as e:
            logger.error(f"BaseDB._init_database error: {e}", exc_info=True)
            raise
    
    async def _run_sync(self, fn: Callable[[], T]) -> T:
        """
        Run a synchronous SQLite function in the thread-pool executor.
        
        This ensures the event loop is never blocked by SQLite I/O.
        
        Args:
            fn: A synchronous function that performs SQLite operations
        
        Returns:
            The result of the function
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, fn)
    
    def checkpoint(self) -> None:
        """
        Run a WAL TRUNCATE checkpoint synchronously.
        
        Call this periodically (e.g., every 5 minutes) from the harvester loop
        to keep the WAL file small. Safe to call while the asyncio lock is NOT held.
        """
        if not self.wal_mode:
            return
        
        try:
            with self._get_connection() as conn:
                result = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                # result = (busy, log_pages, checkpointed_pages)
                if result and result[0] == 0:
                    logger.debug(f"BaseDB checkpoint: {result[1]} pages checkpointed")
                else:
                    logger.debug(f"BaseDB checkpoint (busy): {result}")
        except Exception as e:
            logger.warning(f"BaseDB.checkpoint error: {e}")
    
    async def checkpoint_async(self) -> None:
        """
        Run a WAL checkpoint asynchronously.
        
        Returns:
            None
        """
        await self._run_sync(self.checkpoint)
    
    def backup_database(self, backup_path: Optional[str] = None) -> str:
        """
        Create a backup of the database file.
        
        Args:
            backup_path: Optional path for the backup. If None, generates a timestamped backup.
        
        Returns:
            Path to the backup file
        """
        if backup_path is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            backup_path = f"{self.db_path}.backup_{timestamp}"
        
        try:
            # Ensure source exists
            source_path = Path(self.db_path)
            if not source_path.exists():
                logger.warning(f"Source database does not exist: {self.db_path}")
                # Create empty database
                source_path.touch()
            
            # Copy the database file
            shutil.copy2(self.db_path, backup_path)
            
            # Also copy WAL files if they exist
            wal_path = f"{self.db_path}-wal"
            if Path(wal_path).exists():
                shutil.copy2(wal_path, f"{backup_path}-wal")
            
            shm_path = f"{self.db_path}-shm"
            if Path(shm_path).exists():
                shutil.copy2(shm_path, f"{backup_path}-shm")
            
            logger.info(f"Database backed up to: {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"BaseDB.backup_database error: {e}", exc_info=True)
            raise
    
    async def backup_database_async(self, backup_path: Optional[str] = None) -> str:
        """
        Create a backup of the database file asynchronously.
        
        Args:
            backup_path: Optional path for the backup. If None, generates a timestamped backup.
        
        Returns:
            Path to the backup file
        """
        return await self._run_sync(lambda: self.backup_database(backup_path))
    
    def verify_database(self) -> Dict[str, Any]:
        """
        Verify database integrity and return status information.
        
        Returns:
            Dictionary with verification results
        """
        result = {
            "path": self.db_path,
            "exists": Path(self.db_path).exists(),
            "size_bytes": 0,
            "tables": [],
            "integrity_check": None,
            "wal_size_bytes": 0,
            "shm_size_bytes": 0,
        }
        
        try:
            if not result["exists"]:
                return result
            
            result["size_bytes"] = Path(self.db_path).stat().st_size
            
            wal_path = Path(f"{self.db_path}-wal")
            if wal_path.exists():
                result["wal_size_bytes"] = wal_path.stat().st_size
            
            shm_path = Path(f"{self.db_path}-shm")
            if shm_path.exists():
                result["shm_size_bytes"] = shm_path.stat().st_size
            
            with self._get_connection() as conn:
                # Get list of tables
                tables = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
                result["tables"] = [t[0] for t in tables]
                
                # Run integrity check
                integrity = conn.execute("PRAGMA integrity_check").fetchone()
                result["integrity_check"] = integrity[0] if integrity else None
                
        except Exception as e:
            logger.error(f"BaseDB.verify_database error: {e}", exc_info=True)
            result["error"] = str(e)
        
        return result
    
    async def verify_database_async(self) -> Dict[str, Any]:
        """
        Verify database integrity asynchronously.
        
        Returns:
            Dictionary with verification results
        """
        return await self._run_sync(self.verify_database)
    
    def _ensure_column(self, cursor: sqlite3.Cursor, table: str, col: str, col_type: str) -> None:
        """
        Ensure a column exists in a table, adding it if necessary.
        
        Args:
            cursor: SQLite cursor
            table: Table name
            col: Column name
            col_type: Column type (e.g., "TEXT", "INTEGER")
        """
        cursor.execute(f"PRAGMA table_info({table})")
        if col not in {r[1] for r in cursor.fetchall()}:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            logger.info(f"Added column {col} to table {table}")
    
    async def close(self) -> None:
        """
        Close the database and release resources.
        
        This is a no-op in the base implementation since connections are
        created per-operation. Subclasses with persistent connections
        should override this.
        """
        logger.info(f"BaseDB closed: {self.db_path}")
    
    def __repr__(self) -> str:
        return f"BaseDB(path={self.db_path}, mode={self.async_mode.value})"

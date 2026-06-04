"""
WriteQueue — Buffered write operations for all PnW Harvester databases.

Provides:
- Write buffering for bulk operations
- Multiple flush policies (timeout, size, manual, hybrid)
- Duplicate write merging (last writer wins)
- Write priority handling
- Flush metrics

This improves performance by batching writes and reduces lock contention
by minimizing the time locks are held.
"""

import asyncio
import logging
import time
from collections import defaultdict, OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Tuple
from hashlib import sha256

logger = logging.getLogger(__name__)


class FlushPolicy(Enum):
    """Flush policy for write queues."""
    TIMEOUT = "timeout"  # Flush every N seconds
    SIZE = "size"  # Flush when queue reaches N items
    MANUAL = "manual"  # Flush on demand only
    HYBRID = "hybrid"  # Combination of timeout and size


class WritePriority(Enum):
    """Write priority levels."""
    CRITICAL = 0  # Highest priority (immediate flush)
    HIGH = 1
    NORMAL = 2
    LOW = 3  # Lowest priority (deferred)


@dataclass
class WriteOperation:
    """A single write operation."""
    db_path: str
    operation: Callable
    args: Tuple = field(default_factory=tuple)
    kwargs: Dict = field(default_factory=dict)
    priority: WritePriority = WritePriority.NORMAL
    queued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    key: Optional[str] = None  # For deduplication
    
    def __hash__(self) -> int:
        """Hash based on db_path and key for deduplication."""
        if self.key:
            return hash((self.db_path, self.key))
        return hash((self.db_path, id(self.operation)))
    
    def __eq__(self, other) -> bool:
        """Equality based on db_path and key for deduplication."""
        if not isinstance(other, WriteOperation):
            return False
        if self.key and other.key:
            return self.db_path == other.db_path and self.key == other.key
        return self is other


@dataclass
class QueueStats:
    """Statistics for a write queue."""
    db_path: str
    total_enqueued: int = 0
    total_flushed: int = 0
    total_merged: int = 0
    total_dropped: int = 0
    total_errors: int = 0
    current_size: int = 0
    max_size: int = 0
    total_flush_time: float = 0.0
    avg_flush_time: float = 0.0
    last_flush_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    last_error_message: Optional[str] = None


class WriteQueue:
    """
    Write queue for a single database.
    
    Buffers write operations and flushes them according to the configured policy.
    """
    
    DEFAULT_FLUSH_TIMEOUT = 5.0  # seconds
    DEFAULT_FLUSH_SIZE = 100
    DEFAULT_MAX_SIZE = 1000
    
    def __init__(
        self,
        db_path: str,
        flush_policy: FlushPolicy = FlushPolicy.HYBRID,
        flush_timeout: float = DEFAULT_FLUSH_TIMEOUT,
        flush_size: int = DEFAULT_FLUSH_SIZE,
        max_size: int = DEFAULT_MAX_SIZE,
    ):
        """
        Initialize the write queue.
        
        Args:
            db_path: Path to the database file
            flush_policy: Flush policy to use
            flush_timeout: Timeout in seconds for TIMEOUT/HYBRID policies
            flush_size: Size threshold for SIZE/HYBRID policies
            max_size: Maximum queue size (drops writes if exceeded)
        """
        self._db_path = str(Path(db_path).resolve())
        self._flush_policy = flush_policy
        self._flush_timeout = flush_timeout
        self._flush_size = flush_size
        self._max_size = max_size
        
        # OrderedDict for deduplication (key-based)
        self._queue: OrderedDict[str, WriteOperation] = OrderedDict()
        self._lock = asyncio.Lock()
        self._stats = QueueStats(db_path=self._db_path)
        
        # Background flush task
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Lock manager for acquiring locks during flush
        self._lock_manager = None  # Will be set via set_lock_manager
        
        logger.info(
            f"WriteQueue initialized for {self._db_path} "
            f"(policy={flush_policy.value}, timeout={flush_timeout}s, size={flush_size})"
        )
    
    def set_lock_manager(self, lock_manager) -> None:
        """
        Set the lock manager for acquiring locks during flush.
        
        Args:
            lock_manager: LockManager instance
        """
        self._lock_manager = lock_manager
        logger.debug(f"LockManager set for {self._db_path}")
    
    async def start(self) -> None:
        """Start the write queue background task."""
        if self._running:
            logger.warning(f"WriteQueue already running for {self._db_path}")
            return
        
        self._running = True
        
        if self._flush_policy in (FlushPolicy.TIMEOUT, FlushPolicy.HYBRID):
            self._flush_task = asyncio.create_task(self._flush_loop())
            logger.info(f"WriteQueue started for {self._db_path}")
        else:
            logger.info(f"WriteQueue started (manual flush) for {self._db_path}")
    
    async def stop(self) -> None:
        """Stop the write queue and flush remaining writes."""
        self._running = False
        
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        
        # Flush remaining writes
        await self.flush()
        
        logger.info(f"WriteQueue stopped for {self._db_path}")
    
    async def enqueue(
        self,
        operation: Callable,
        *args,
        priority: WritePriority = WritePriority.NORMAL,
        key: Optional[str] = None,
        **kwargs,
    ) -> bool:
        """
        Enqueue a write operation.
        
        Args:
            operation: The function to execute
            *args: Arguments for the operation
            priority: Write priority
            key: Optional key for deduplication
            **kwargs: Keyword arguments for the operation
            
        Returns:
            True if enqueued, False if dropped
        """
        write_op = WriteOperation(
            db_path=self._db_path,
            operation=operation,
            args=args,
            kwargs=kwargs,
            priority=priority,
            key=key,
        )
        
        async with self._lock:
            # Check max size
            if len(self._queue) >= self._max_size:
                self._stats.total_dropped += 1
                logger.warning(
                    f"WriteQueue full for {self._db_path}, dropping write "
                    f"(size={len(self._queue)}, max={self._max_size})"
                )
                return False
            
            # Deduplicate: replace existing write with same key
            if key and key in self._queue:
                self._stats.total_merged += 1
                logger.debug(f"Merged duplicate write for {self._db_path} (key={key})")
            
            self._queue[key or str(id(write_op))] = write_op
            self._stats.total_enqueued += 1
            self._stats.current_size = len(self._queue)
            self._stats.max_size = max(self._stats.max_size, len(self._queue))
            
            logger.debug(
                f"Enqueued write for {self._db_path} "
                f"(priority={priority.value}, size={len(self._queue)})"
            )
            
            # Check if we should flush immediately
            if priority == WritePriority.CRITICAL:
                # Critical writes flush immediately (but in background)
                asyncio.create_task(self._flush_unlocked())
            elif self._flush_policy == FlushPolicy.SIZE and len(self._queue) >= self._flush_size:
                asyncio.create_task(self._flush_unlocked())
            elif self._flush_policy == FlushPolicy.HYBRID and len(self._queue) >= self._flush_size:
                asyncio.create_task(self._flush_unlocked())
        
        return True
    
    async def _flush_loop(self) -> None:
        """
        Background loop for timeout-based flushing.
        """
        while self._running:
            try:
                await asyncio.sleep(self._flush_timeout)
                
                if self._running:
                    await self.flush()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Flush loop error: {e}")
    
    async def _flush_unlocked(self) -> None:
        """
        Flush the queue without acquiring the internal lock.
        
        This is called from within an already-locked context or from a background task.
        """
        if not self._queue:
            return
        
        # Acquire DB lock for the flush
        if self._lock_manager:
            async with self._lock_manager.acquire_lock(self._db_path):
                await self._execute_flush()
        else:
            # No lock manager - flush directly (not recommended)
            await self._execute_flush()
    
    async def _execute_flush(self) -> None:
        """
        Execute the flush operation.
        
        This assumes the appropriate locks are already held.
        """
        if not self._queue:
            return
        
        start_time = time.monotonic()
        operations = list(self._queue.values())
        self._queue.clear()
        
        errors = []
        
        for write_op in operations:
            try:
                # Execute the operation
                if asyncio.iscoroutinefunction(write_op.operation):
                    await write_op.operation(*write_op.args, **write_op.kwargs)
                else:
                    # Run synchronous operations in executor
                    await asyncio.get_event_loop().run_in_executor(
                        None, write_op.operation, *write_op.args, **write_op.kwargs
                    )
                self._stats.total_flushed += 1
            except Exception as e:
                errors.append(str(e))
                self._stats.total_errors += 1
                logger.error(f"Write operation failed: {e}")
        
        flush_time = time.monotonic() - start_time
        self._stats.total_flush_time += flush_time
        self._stats.avg_flush_time = (
            self._stats.total_flush_time / self._stats.total_flushed
            if self._stats.total_flushed > 0
            else 0.0
        )
        self._stats.last_flush_at = datetime.now(timezone.utc)
        
        if errors:
            self._stats.last_error_at = datetime.now(timezone.utc)
            self._stats.last_error_message = errors[-1]
        
        # Update current_size without acquiring self._lock here.
        # _execute_flush is always called without holding self._lock
        # (either from _flush_loop or from a create_task'd _flush_unlocked),
        # but taking the lock would deadlock if a caller holds it while
        # dispatching the flush task (e.g. enqueue's create_task path).
        self._stats.current_size = len(self._queue)
        
        logger.info(
            f"Flushed {len(operations)} writes for {self._db_path} "
            f"(time={flush_time:.3f}s, errors={len(errors)})"
        )
    
    async def flush(self) -> int:
        """
        Manually flush the queue.
        
        Returns:
            Number of writes flushed
        """
        async with self._lock:
            size = len(self._queue)
        
        if size > 0:
            await self._flush_unlocked()
        
        return size
    
    async def get_stats(self) -> QueueStats:
        """
        Get queue statistics.
        
        Returns:
            QueueStats instance
        """
        async with self._lock:
            self._stats.current_size = len(self._queue)
            return self._stats
    
    def set_flush_policy(self, policy: FlushPolicy) -> None:
        """
        Change the flush policy.
        
        Args:
            policy: New flush policy
        """
        self._flush_policy = policy
        logger.info(f"Flush policy changed to {policy.value} for {self._db_path}")
    
    def __len__(self) -> int:
        """Get current queue size."""
        return len(self._queue)
    
    def __repr__(self) -> str:
        return f"WriteQueue(path={self._db_path}, size={len(self._queue)}, policy={self._flush_policy.value})"


class WriteQueueManager:
    """
    Manager for multiple write queues.
    
    Maintains a queue for each unique database path.
    """
    
    def __init__(self):
        """Initialize the queue manager."""
        self._queues: Dict[str, WriteQueue] = {}
        self._lock = asyncio.Lock()
        
        logger.info("WriteQueueManager initialized")
    
    async def get_queue(
        self,
        db_path: str,
        flush_policy: FlushPolicy = FlushPolicy.HYBRID,
        flush_timeout: float = WriteQueue.DEFAULT_FLUSH_TIMEOUT,
        flush_size: int = WriteQueue.DEFAULT_FLUSH_SIZE,
    ) -> WriteQueue:
        """
        Get or create a queue for a database.
        
        Args:
            db_path: Path to the database file
            flush_policy: Flush policy to use
            flush_timeout: Timeout in seconds
            flush_size: Size threshold
            
        Returns:
            WriteQueue instance
        """
        normalized = str(Path(db_path).resolve())
        
        async with self._lock:
            if normalized not in self._queues:
                queue = WriteQueue(
                    db_path=normalized,
                    flush_policy=flush_policy,
                    flush_timeout=flush_timeout,
                    flush_size=flush_size,
                )
                await queue.start()
                self._queues[normalized] = queue
            
            return self._queues[normalized]
    
    async def enqueue(
        self,
        db_path: str,
        operation: Callable,
        *args,
        priority: WritePriority = WritePriority.NORMAL,
        key: Optional[str] = None,
        **kwargs,
    ) -> bool:
        """
        Enqueue a write operation for a database.
        
        Args:
            db_path: Path to the database file
            operation: The function to execute
            *args: Arguments for the operation
            priority: Write priority
            key: Optional key for deduplication
            **kwargs: Keyword arguments for the operation
            
        Returns:
            True if enqueued, False if dropped
        """
        queue = await self.get_queue(db_path)
        return await queue.enqueue(operation, *args, priority=priority, key=key, **kwargs)
    
    async def flush(self, db_path: str) -> int:
        """
        Flush the queue for a specific database.
        
        Args:
            db_path: Path to the database file
            
        Returns:
            Number of writes flushed
        """
        normalized = str(Path(db_path).resolve())
        
        async with self._lock:
            if normalized in self._queues:
                return await self._queues[normalized].flush()
        
        return 0
    
    async def flush_all(self) -> Dict[str, int]:
        """
        Flush all queues.
        
        Returns:
            Dictionary mapping db_path to number of writes flushed
        """
        results = {}
        
        async with self._lock:
            for db_path, queue in self._queues.items():
                results[db_path] = await queue.flush()
        
        return results
    
    async def close_queue(self, db_path: str) -> None:
        """
        Close a specific queue.
        
        Args:
            db_path: Path to the database file
        """
        normalized = str(Path(db_path).resolve())
        
        async with self._lock:
            if normalized in self._queues:
                await self._queues[normalized].stop()
                del self._queues[normalized]
                logger.info(f"Closed queue for {normalized}")
    
    async def close_all(self) -> None:
        """Close all queues."""
        async with self._lock:
            for queue in list(self._queues.values()):
                await queue.stop()
            
            self._queues.clear()
            logger.info("All queues closed")
    
    async def get_all_stats(self) -> Dict[str, QueueStats]:
        """
        Get statistics for all queues.
        
        Returns:
            Dictionary mapping db_path to QueueStats
        """
        stats = {}
        async with self._lock:
            for db_path, queue in self._queues.items():
                stats[db_path] = await queue.get_stats()
        
        return stats
    
    def set_lock_manager(self, lock_manager) -> None:
        """
        Set the lock manager for all queues.
        
        Args:
            lock_manager: LockManager instance
        """
        for queue in self._queues.values():
            queue.set_lock_manager(lock_manager)
        
        logger.info("LockManager set for all queues")
    
    def __repr__(self) -> str:
        return f"WriteQueueManager(queues={len(self._queues)})"
    
    async def __aenter__(self):
        """Context manager entry."""
        return self
    
    async def __aexit__(self, *args):
        """Context manager exit."""
        await self.close_all()


# Global singleton instance
_global_queue_manager: Optional[WriteQueueManager] = None


def get_queue_manager() -> WriteQueueManager:
    """
    Get the global WriteQueueManager singleton.
    
    Returns:
        The global WriteQueueManager instance
    """
    global _global_queue_manager
    if _global_queue_manager is None:
        _global_queue_manager = WriteQueueManager()
    return _global_queue_manager

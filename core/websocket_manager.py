"""
SharedWebSocketManager — Centralized WebSocket connection management with reliability features.

Implements industry-best practices for WebSocket reliability:
- Single connection with multiplexed subscriptions
- Circuit breaker pattern for failure handling
- Application-level heartbeat monitoring
- Connection state machine
- Event buffering for replay during disconnections
- Active health probing
- Graceful degradation to polling
"""

import asyncio
import logging
import os
import random
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import aiohttp
import pnwkit
from pnwkit.new import QueryKit
from PnWHarvester.core.pnwkit_compat import close_querykit, patch_pnwkit

patch_pnwkit()

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """WebSocket connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    CIRCUIT_OPEN = "circuit_open"


@dataclass
class SubscriptionInfo:
    """Information about a subscription."""
    resource: str
    action: str
    filters: Dict[str, Any]
    callback: Callable
    required: bool = True
    active: bool = False
    subscription_obj: Optional[Any] = None
    disabled: bool = False
    last_error: Optional[str] = None
    next_retry_at: float = 0.0
    event_queue: Optional[asyncio.Queue] = None
    worker_task: Optional[asyncio.Task] = None


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""
    pass


class WebSocketIdleTimeout(ConnectionError):
    """Raised when an open WebSocket stops delivering events."""
    pass


class CircuitBreaker:
    """
    Circuit breaker pattern for connection failure handling.
    
    Prevents hammering a failing server by stopping reconnection attempts
    after consecutive failures, then entering half-open state to test recovery.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: int = 300,
        half_open_max_calls: int = 3
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of consecutive failures before opening circuit
            timeout: Seconds to wait before attempting half-open state
            half_open_max_calls: Number of calls allowed in half-open state
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.half_open_max_calls = half_open_max_calls
        
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.half_open_calls = 0
        
    def can_attempt(self) -> bool:
        """Check if connection attempt is allowed."""
        if self.state == "CLOSED":
            return True
        
        if self.state == "OPEN":
            if self.last_failure_time and (time.time() - self.last_failure_time) > self.timeout:
                self.state = "HALF_OPEN"
                self.half_open_calls = 0
                logger.info("Circuit breaker entering HALF_OPEN state")
                return True
            return False
        
        if self.state == "HALF_OPEN":
            return self.half_open_calls < self.half_open_max_calls
        
        return False
    
    def record_success(self):
        """Record a successful connection."""
        self.failure_count = 0
        if self.state == "HALF_OPEN":
            self.half_open_calls += 1
            if self.half_open_calls >= self.half_open_max_calls:
                self.state = "CLOSED"
                logger.info("Circuit breaker returning to CLOSED state")
        elif self.state == "OPEN":
            self.state = "CLOSED"
            logger.info("Circuit breaker returning to CLOSED state")
    
    def record_failure(self):
        """Record a failed connection."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            if self.state != "OPEN":
                self.state = "OPEN"
                logger.warning(f"Circuit breaker opened after {self.failure_count} failures")
    
    def get_state(self) -> str:
        """Get current circuit breaker state."""
        return self.state


class HeartbeatMonitor:
    """
    Application-level heartbeat monitoring for connection health.
    
    Sends periodic pings and expects pongs within timeout to detect
    zombie connections that are technically connected but not working.
    """
    
    def __init__(self, ping_interval: int = 30, pong_timeout: int = 10):
        """
        Initialize heartbeat monitor.
        
        Args:
            ping_interval: Seconds between ping attempts
            pong_timeout: Seconds to wait for pong before declaring failure
        """
        self.ping_interval = ping_interval
        self.pong_timeout = pong_timeout
        self.last_pong_time: Optional[float] = None
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._pong_event = asyncio.Event()
        
    async def start(self, send_ping_callback: Callable):
        """
        Start heartbeat monitoring.
        
        Args:
            send_ping_callback: Async function to send ping
        """
        self.running = True
        self.last_pong_time = time.time()
        self._task = asyncio.create_task(self._heartbeat_loop(send_ping_callback))
        logger.info("Heartbeat monitor started")
        
    async def stop(self):
        """Stop heartbeat monitoring."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Heartbeat monitor stopped")
        
    def record_pong(self):
        """Record receipt of a pong."""
        self.last_pong_time = time.time()
        self._pong_event.set()
        self._pong_event.clear()
        
    async def _heartbeat_loop(self, send_ping_callback: Callable):
        """Main heartbeat loop."""
        while self.running:
            try:
                await asyncio.sleep(self.ping_interval)
                await send_ping_callback()
                
                # Wait for pong with timeout
                try:
                    await asyncio.wait_for(self._pong_event.wait(), timeout=self.pong_timeout)
                except asyncio.TimeoutError:
                    logger.error("Heartbeat timeout - no pong received")
                    # Signal connection failure by raising ConnectionError
                    raise ConnectionError("Heartbeat timeout")
                    
            except asyncio.CancelledError:
                break
            except ConnectionError:
                # Let ConnectionError propagate to trigger reconnection
                raise
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                # Don't raise here - let the connection manager handle it
                await asyncio.sleep(self.ping_interval)
    
    def is_healthy(self) -> bool:
        """Check if heartbeat is healthy."""
        if self.last_pong_time is None:
            return False
        return (time.time() - self.last_pong_time) < (self.ping_interval + self.pong_timeout)


class EventBuffer:
    """
    Buffer events for replay during reconnection.
    
    Stores recent events to allow replay of missed events during
    brief disconnections, ensuring no data loss.
    """
    
    def __init__(self, max_size: int = 1000):
        """
        Initialize event buffer.
        
        Args:
            max_size: Maximum number of events to buffer
        """
        self.buffer = deque(maxlen=max_size)
        self.sequence_counter = 0
        
    def add_event(self, event: Any, subscription_key: str) -> int:
        """
        Add an event to the buffer.
        
        Args:
            event: The event to buffer
            subscription_key: Key identifying the subscription
            
        Returns:
            Sequence number for this event
        """
        sequence = self.sequence_counter
        self.buffer.append({
            'event': event,
            'subscription_key': subscription_key,
            'timestamp': time.time(),
            'sequence': sequence
        })
        self.sequence_counter += 1
        return sequence
        
    def get_events_since(self, sequence: int) -> List[Dict[str, Any]]:
        """
        Get all events since a given sequence number.
        
        Args:
            sequence: Sequence number to start from
            
        Returns:
            List of buffered events
        """
        return [e for e in self.buffer if e['sequence'] > sequence]
    
    def get_latest_sequence(self) -> int:
        """Get the latest sequence number."""
        return self.sequence_counter - 1 if self.sequence_counter > 0 else 0


class HealthProber:
    """
    Active health probing for WebSocket connections.
    
    Periodically sends test queries to actively verify connection health
    rather than relying solely on passive message monitoring.
    """
    
    def __init__(self, probe_interval: int = 60):
        """
        Initialize health prober.
        
        Args:
            probe_interval: Seconds between health probes
        """
        self.probe_interval = probe_interval
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._last_probe_success = True
        
    async def start(self, probe_callback: Callable):
        """
        Start health probing.
        
        Args:
            probe_callback: Async function that performs health check
        """
        self.running = True
        self._task = asyncio.create_task(self._probe_loop(probe_callback))
        logger.info("Health prober started")
        
    async def stop(self):
        """Stop health probing."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Health prober stopped")
        
    async def _probe_loop(self, probe_callback: Callable):
        """Main health probe loop."""
        while self.running:
            try:
                await asyncio.sleep(self.probe_interval)
                
                healthy = await probe_callback()
                self._last_probe_success = healthy
                
                if not healthy:
                    logger.warning("Health probe failed - connection may be unhealthy")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health probe error: {e}")
                self._last_probe_success = False
    
    def is_healthy(self) -> bool:
        """Check if last probe was successful."""
        return self._last_probe_success


class SharedWebSocketManager:
    """
    Centralized WebSocket connection manager with reliability features.
    
    Manages a single WebSocket connection with multiplexed subscriptions,
    implementing industry-best practices for reliability:
    - Circuit breaker for failure handling
    - Application-level heartbeat
    - Connection state machine
    - Event buffering for replay
    - Active health probing
    - Automatic reconnection with exponential backoff
    """
    
    def __init__(self, api_key: str):
        """
        Initialize shared WebSocket manager.
        
        Args:
            api_key: PnW API key for authentication
        """
        self.api_key = api_key
        self.kit: Optional[QueryKit] = None
        
        # Connection state
        self.connection_state = ConnectionState.DISCONNECTED
        self.state_listeners: Set[Callable] = set()
        self.running = False
        
        # Subscriptions
        self.subscriptions: Dict[str, SubscriptionInfo] = {}
        self._subscription_lock = asyncio.Lock()
        self._listener_tasks: Dict[str, asyncio.Task] = {}
        self._subscription_changed = asyncio.Event()
        self.dispatch_queue_size = int(self._env_float(
            "HARVESTER_WS_DISPATCH_QUEUE_SIZE", 500.0
        ))
        
        # Reliability components
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=300)
        # Heartbeat monitor disabled - pnwkit has built-in heartbeat (ping_pong_task, _heartbeat_task)
        # self.heartbeat_monitor = HeartbeatMonitor(ping_interval=30, pong_timeout=10)
        self.event_buffer = EventBuffer(max_size=1000)
        self.health_prober = HealthProber(probe_interval=60)
        
        # Reconnection config
        self.base_delay = 10
        self.max_delay = 300
        self.retry_count = 0
        self.idle_reconnect_seconds = self._env_float(
            "HARVESTER_WS_IDLE_RECONNECT_SECONDS", 60.0
        )
        self.initial_idle_reconnect_seconds = self._env_float(
            "HARVESTER_WS_INITIAL_IDLE_RECONNECT_SECONDS",
            max(self.idle_reconnect_seconds * 2, 120.0),
        )
        self.connected_at: Optional[datetime] = None
        self.last_event_at: Optional[datetime] = None
        self._last_forced_reconnect_at: Optional[float] = None
        self._force_reconnect_requested = False
        
        # Connection task
        self._connection_task: Optional[asyncio.Task] = None

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        """Read a positive float from the environment."""
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            value = float(raw)
            return value if value > 0 else default
        except ValueError:
            logger.warning("Invalid %s=%r; using %.1f", name, raw, default)
            return default
        
    def add_state_listener(self, listener: Callable):
        """Add a listener for connection state changes."""
        self.state_listeners.add(listener)
        
    def remove_state_listener(self, listener: Callable):
        """Remove a state listener."""
        self.state_listeners.discard(listener)
        
    def _set_state(self, new_state: ConnectionState):
        """Set connection state and notify listeners."""
        old_state = self.connection_state
        self.connection_state = new_state
        logger.info(f"Connection state: {old_state.value} -> {new_state.value}")
        
        for listener in self.state_listeners:
            try:
                listener(new_state, old_state)
            except Exception as e:
                logger.error(f"State listener error: {e}")
    
    async def initialize(self):
        """Initialize the WebSocket manager."""
        logger.info("SharedWebSocketManager initializing")
        self.kit = QueryKit(self.api_key)
        
    async def start(self):
        """Start the WebSocket connection manager."""
        if self.running:
            logger.warning("SharedWebSocketManager already running")
            return
            
        self.running = True
        self._connection_task = asyncio.create_task(self._connection_loop())
        logger.info("SharedWebSocketManager started")
        
    async def stop(self):
        """Stop the WebSocket connection manager."""
        self.running = False
        
        # Stop reliability components
        # await self.heartbeat_monitor.stop()
        await self.health_prober.stop()
        
        # Cancel connection task
        if self._connection_task:
            self._connection_task.cancel()
            try:
                await self._connection_task
            except asyncio.CancelledError:
                pass

        await self._cancel_listener_tasks()
        
        # Close WebSocket and underlying HTTP sessions.
        await close_querykit(self.kit)
        self.kit = None
        
        self._set_state(ConnectionState.DISCONNECTED)
        logger.info("SharedWebSocketManager stopped")

    async def force_reconnect(self, reason: str) -> None:
        """Tear down the current connection so the connection loop rebuilds it."""
        if not self.running:
            return

        if self.connection_state != ConnectionState.CONNECTED:
            logger.debug(
                "Ignoring force_reconnect (state=%s): %s",
                self.connection_state.value, reason,
            )
            return

        now = time.monotonic()
        if (
            self._last_forced_reconnect_at is not None
            and now - self._last_forced_reconnect_at < 10.0
        ):
            logger.debug("Shared WebSocket reconnect already requested recently: %s", reason)
            return
        self._last_forced_reconnect_at = now

        logger.warning("Forcing shared WebSocket reconnect: %s", reason)
        self._force_reconnect_requested = True
        await self._cancel_listener_tasks()
        await close_querykit(self.kit)
        self.kit = None
        self._subscription_changed.set()

    async def _cancel_listener_tasks(self) -> None:
        """Cancel tracked listeners and reset subscription runtime state."""
        tasks = list(self._listener_tasks.values())
        self._listener_tasks.clear()

        async with self._subscription_lock:
            tasks.extend(
                sub_info.worker_task
                for sub_info in self.subscriptions.values()
                if sub_info.worker_task is not None
            )
            for sub_info in self.subscriptions.values():
                sub_info.worker_task = None
                sub_info.event_queue = None

        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        async with self._subscription_lock:
            for sub_info in self.subscriptions.values():
                sub_info.active = False
                sub_info.subscription_obj = None
        
    async def _connection_loop(self):
        """Main connection loop with auto-reconnect."""
        while self.running:
            try:
                if not self.circuit_breaker.can_attempt():
                    self._set_state(ConnectionState.CIRCUIT_OPEN)
                    wait_time = self.circuit_breaker.timeout - (time.time() - (self.circuit_breaker.last_failure_time or 0))
                    await asyncio.sleep(max(wait_time, 1))
                    continue
                    
                await self._connect()
                
                # Reset retry count on successful connection
                self.retry_count = 0
                
            except asyncio.CancelledError:
                logger.info("Connection loop cancelled")
                break
            except Exception as e:
                self.circuit_breaker.record_failure()
                self.retry_count += 1
                
                # Calculate delay with exponential backoff and jitter
                delay = min(self.base_delay * (2 ** min(self.retry_count - 1, 5)), self.max_delay)
                jitter = random.uniform(0.8, 1.2)
                actual_delay = delay * jitter
                
                logger.warning(
                    f"Connection failed ({e}) - retry {self.retry_count}, "
                    f"reconnecting in {actual_delay:.1f}s (circuit: {self.circuit_breaker.get_state()})"
                )
                
                await asyncio.sleep(actual_delay)
                
    async def _connect_legacy_disabled(self):
        """Establish WebSocket connection and start subscriptions."""
        self._set_state(ConnectionState.RECONNECTING if self.retry_count > 0 else ConnectionState.CONNECTING)
        
        try:
            # Close existing connection if any
            await self._cancel_listener_tasks()
            await close_querykit(self.kit)
            self.kit = QueryKit(self.api_key)

            # Start reliability components
            if not self.health_prober.running:
                await self.health_prober.start(self._probe_health)
            
            # Establish all subscriptions
            listener_tasks = []
            async with self._subscription_lock:
                for key, sub_info in self.subscriptions.items():
                    if not sub_info.active:
                        await self._start_subscription_legacy_disabled(
                            sub_info, listener_tasks
                        )
            
            self._set_state(ConnectionState.CONNECTED)
            self.circuit_breaker.record_success()
            
            if not listener_tasks:
                # No subscriptions yet — just wait until stopped
                while self.running and self.connection_state == ConnectionState.CONNECTED:
                    await asyncio.sleep(1)
                return
            
            # Wait for the FIRST listener to finish — any disconnect/crash triggers reconnect
            done, pending = await asyncio.wait(
                listener_tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            # Re-raise the first exception so _connection_loop retries
            for t in done:
                exc = t.exception() if not t.cancelled() else None
                if exc:
                    raise exc
            
        except Exception as e:
            if isinstance(e, WebSocketIdleTimeout):
                logger.warning(str(e))
            else:
                logger.error(f"Connection error: {e}", exc_info=True)
            await self._cancel_listener_tasks()
            await close_querykit(self.kit)
            self.kit = None
            if self.running:
                self._set_state(ConnectionState.DISCONNECTED)
            raise
            
    async def _start_subscription_legacy_disabled(self, sub_info: SubscriptionInfo, listener_tasks: list):
        """Start a single subscription and add its listener task to listener_tasks."""
        try:
            subscription = await self.kit.subscribe(
                sub_info.resource,
                sub_info.action,
                sub_info.filters
            )
            sub_info.subscription_obj = subscription
            sub_info.active = True
            logger.info(f"Subscription active: {sub_info.resource}/{sub_info.action}")
            
            # Create a tracked listener task so its exceptions surface to _connect
            task = asyncio.create_task(
                self._listen_to_subscription(sub_info),
                name=f"ws_listen_{sub_info.resource}_{sub_info.action}"
            )
            listener_tasks.append(task)
            
        except Exception as e:
            logger.error(f"Failed to start subscription {sub_info.resource}/{sub_info.action}: {e}")
            sub_info.active = False
            raise
            
    async def _connect(self):
        """Establish WebSocket connection and keep every listener supervised."""
        self._force_reconnect_requested = False
        self._set_state(ConnectionState.RECONNECTING if self.retry_count > 0 else ConnectionState.CONNECTING)

        try:
            await self._cancel_listener_tasks()
            await close_querykit(self.kit)
            self.kit = QueryKit(self.api_key)

            if not self.health_prober.running:
                await self.health_prober.start(self._probe_health)

            self.connected_at = datetime.now(timezone.utc)
            self.last_event_at = None

            async with self._subscription_lock:
                for sub_info in self.subscriptions.values():
                    if not sub_info.active:
                        await self._start_subscription(sub_info)

            self._set_state(ConnectionState.CONNECTED)
            self.circuit_breaker.record_success()

            while self.running and self.connection_state == ConnectionState.CONNECTED:
                if self._force_reconnect_requested:
                    self._force_reconnect_requested = False
                    raise ConnectionError("Force reconnect requested")
                self._raise_if_idle()
                await self._retry_disabled_optional_subscriptions()

                listener_tasks = {
                    task for task in self._listener_tasks.values()
                    if task and not task.done()
                }

                if not listener_tasks:
                    try:
                        await asyncio.wait_for(self._subscription_changed.wait(), timeout=1.0)
                    except asyncio.TimeoutError:
                        pass
                    self._subscription_changed.clear()
                    continue

                change_task = asyncio.create_task(self._subscription_changed.wait())
                done, pending = await asyncio.wait(
                    listener_tasks | {change_task},
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=5.0,
                )

                if not done:
                    change_task.cancel()
                    await asyncio.gather(change_task, return_exceptions=True)
                    continue

                if change_task in done:
                    self._subscription_changed.clear()
                    continue

                change_task.cancel()
                await asyncio.gather(change_task, return_exceptions=True)

                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

                async with self._subscription_lock:
                    for sub_info in self.subscriptions.values():
                        sub_info.active = False
                        sub_info.subscription_obj = None
                self._listener_tasks.clear()

                for task in done:
                    exc = task.exception() if not task.cancelled() else None
                    if exc:
                        raise exc
                raise ConnectionError("Subscription listener ended")

        except Exception as e:
            if isinstance(e, WebSocketIdleTimeout):
                logger.warning(str(e))
            else:
                logger.error(f"Connection error: {e}", exc_info=True)
            await self._cancel_listener_tasks()
            await close_querykit(self.kit)
            self.kit = None
            if self.running:
                self._set_state(ConnectionState.DISCONNECTED)
            raise

    def _active_subscription_count(self) -> int:
        return sum(1 for info in self.subscriptions.values() if info.active)

    def _seconds_since_stream_activity(self) -> Optional[float]:
        reference = self.last_event_at or self.connected_at
        if reference is None:
            return None
        return (datetime.now(timezone.utc) - reference).total_seconds()

    def _raise_if_idle(self) -> None:
        """Force reconnect when the shared stream is open but no events arrive."""
        if self.idle_reconnect_seconds <= 0:
            return
        if self._active_subscription_count() == 0:
            return

        idle_seconds = self._seconds_since_stream_activity()
        if idle_seconds is None:
            return

        limit = (
            self.idle_reconnect_seconds
            if self.last_event_at is not None
            else self.initial_idle_reconnect_seconds
        )
        if idle_seconds >= limit:
            source = "last event" if self.last_event_at is not None else "connection start"
            raise WebSocketIdleTimeout(
                f"No WebSocket events received for {idle_seconds:.0f}s since {source}; "
                f"forcing reconnect (limit {limit:.0f}s)"
            )

    async def _start_subscription(self, sub_info: SubscriptionInfo, *_unused):
        """Start a single subscription and track its listener task."""
        key = f"{sub_info.resource}/{sub_info.action}"
        if sub_info.disabled and not sub_info.required:
            logger.debug("Skipping disabled optional subscription: %s", key)
            return False
        try:
            subscription = await self.kit.subscribe(
                sub_info.resource,
                sub_info.action,
                sub_info.filters,
            )
            sub_info.subscription_obj = subscription
            sub_info.active = True
            sub_info.event_queue = asyncio.Queue(maxsize=self.dispatch_queue_size)
            logger.info(f"Subscription active: {key}")

            task = asyncio.create_task(
                self._listen_to_subscription(sub_info),
                name=f"ws_listen_{sub_info.resource}_{sub_info.action}",
            )
            self._listener_tasks[key] = task
            sub_info.worker_task = asyncio.create_task(
                self._dispatch_subscription_events(sub_info),
                name=f"ws_dispatch_{sub_info.resource}_{sub_info.action}",
            )
            sub_info.disabled = False
            sub_info.last_error = None
            sub_info.next_retry_at = 0.0
            return True

        except (pnwkit.errors.Unauthorized, pnwkit.errors.SubscribeError) as e:
            sub_info.active = False
            sub_info.subscription_obj = None
            sub_info.last_error = f"{type(e).__name__}: {e}"
            if not sub_info.required:
                sub_info.disabled = True
                # Exponential backoff for retries: 5min, 15min, 45min, 2h, 6h, max 24h
                retry_count = getattr(sub_info, '_retry_count', 0) + 1
                sub_info._retry_count = retry_count
                backoff = min(300 * (3 ** (retry_count - 1)), 86400)
                sub_info.next_retry_at = time.monotonic() + backoff
                if retry_count <= 3:
                    logger.warning(
                        "Optional subscription unavailable (attempt %d/%d), retry in %.1fm: %s (%s)",
                        retry_count, 6, backoff / 60, key, sub_info.last_error,
                    )
                else:
                    logger.info(
                        "Optional subscription permanently disabled after %d failures: %s (%s)",
                        retry_count, key, sub_info.last_error,
                    )
                return False
            logger.error(f"Failed to start required subscription {key}: {e}")
            raise
        except Exception as e:
            sub_info.active = False
            sub_info.subscription_obj = None
            sub_info.last_error = f"{type(e).__name__}: {e}"
            if not sub_info.required:
                sub_info.disabled = True
                retry_count = getattr(sub_info, '_retry_count', 0) + 1
                sub_info._retry_count = retry_count
                backoff = min(300 * (3 ** (retry_count - 1)), 86400)
                sub_info.next_retry_at = time.monotonic() + backoff
                if retry_count <= 3:
                    logger.warning(
                        "Optional subscription startup failed (attempt %d/%d), retry in %.1fm: %s (%s)",
                        retry_count, 6, backoff / 60, key, sub_info.last_error,
                    )
                else:
                    logger.info(
                        "Optional subscription permanently disabled after %d failures: %s (%s)",
                        retry_count, key, sub_info.last_error,
                    )
                return False
            logger.error(f"Failed to start subscription {key}: {e}")
            raise

    async def _retry_disabled_optional_subscriptions(self) -> None:
        """Retry optional subscriptions that were parked after subscribe/auth failures."""
        now = time.monotonic()
        async with self._subscription_lock:
            for sub_info in self.subscriptions.values():
                if (
                    sub_info.required
                    or sub_info.active
                    or not sub_info.disabled
                    or sub_info.next_retry_at > now
                ):
                    continue

                key = f"{sub_info.resource}/{sub_info.action}"
                logger.info("Retrying parked optional subscription: %s", key)
                sub_info.disabled = False
                await self._start_subscription(sub_info)

    async def _listen_to_subscription(self, sub_info: SubscriptionInfo):
        """Listen to events from a subscription."""
        key = f"{sub_info.resource}/{sub_info.action}"
        
        try:
            async for event in sub_info.subscription_obj:
                if not self.running:
                    break
                    
                try:
                    self.last_event_at = datetime.now(timezone.utc)

                    # Buffer event for potential replay
                    self.event_buffer.add_event(event, key)

                    owner = getattr(sub_info.callback, "__self__", None)
                    tracker = getattr(owner, "activity_tracker", None)
                    if tracker:
                        tracker.record_message(key)

                    if sub_info.event_queue is None:
                        raise RuntimeError(f"Dispatch queue not initialized for {key}")
                    await sub_info.event_queue.put(event)
                    
                except Exception as e:
                    owner = getattr(sub_info.callback, "__self__", None)
                    tracker = getattr(owner, "activity_tracker", None)
                    if tracker:
                        tracker.record_error(key)
                    logger.error(f"Error processing event from {key}: {e}", exc_info=True)
                    
        except asyncio.CancelledError:
            logger.info(f"Subscription listener cancelled: {key}")
        except Exception as e:
            logger.error(f"Subscription error {key}: {e}")
            sub_info.active = False
            raise
        finally:
            sub_info.active = False
            sub_info.subscription_obj = None

    async def _dispatch_subscription_events(self, sub_info: SubscriptionInfo):
        """Process queued events for one subscription without blocking socket reads."""
        key = f"{sub_info.resource}/{sub_info.action}"

        try:
            while self.running:
                queue = sub_info.event_queue
                if queue is None:
                    break

                event = await queue.get()
                try:
                    await sub_info.callback(event)
                except Exception as e:
                    owner = getattr(sub_info.callback, "__self__", None)
                    tracker = getattr(owner, "activity_tracker", None)
                    if tracker:
                        tracker.record_error(key)
                    logger.error(f"Error processing event from {key}: {e}", exc_info=True)
                finally:
                    queue.task_done()

        except asyncio.CancelledError:
            logger.info(f"Subscription dispatch cancelled: {key}")
            
    async def subscribe(
        self,
        resource: str,
        action: str,
        filters: Dict[str, Any],
        callback: Callable,
        required: bool = True,
    ) -> str:
        """
        Subscribe to a WebSocket event.
        
        Args:
            resource: Resource type (e.g., "nation", "war")
            action: Action type (e.g., "create", "update")
            filters: Subscription filters
            callback: Async callback function for events
            
        Returns:
            Subscription key
        """
        key = f"{resource}/{action}"
        
        async with self._subscription_lock:
            if key in self.subscriptions:
                sub_info = self.subscriptions[key]
                sub_info.filters = filters
                sub_info.callback = callback
                sub_info.required = required
                if required:
                    sub_info.disabled = False
                if (
                    self.connection_state == ConnectionState.CONNECTED
                    and not sub_info.active
                ):
                    await self._start_subscription(sub_info)
                    self._subscription_changed.set()
                logger.info(f"Subscription updated: {key}")
                return key
                
            sub_info = SubscriptionInfo(
                resource=resource,
                action=action,
                filters=filters,
                callback=callback,
                required=required,
                active=False
            )
            
            self.subscriptions[key] = sub_info
            
            # If already connected, start this subscription immediately
            if self.connection_state == ConnectionState.CONNECTED:
                _tasks: list = []
                await self._start_subscription(sub_info, _tasks)
                self._subscription_changed.set()
                
            logger.info(f"Subscription registered: {key}")
            return key
            
    async def unsubscribe(self, resource: str, action: str):
        """
        Unsubscribe from a WebSocket event.
        
        Args:
            resource: Resource type
            action: Action type
        """
        key = f"{resource}/{action}"
        
        async with self._subscription_lock:
            if key not in self.subscriptions:
                logger.warning(f"Subscription not found: {key}")
                return
                
            sub_info = self.subscriptions[key]
            sub_info.active = False
            
            # Note: pnwkit doesn't have an explicit unsubscribe method
            # We just stop listening to the subscription
            del self.subscriptions[key]
            logger.info(f"Subscription removed: {key}")
            
    async def _send_ping(self):
        """Send application-level ping."""
        # This is a placeholder - implement actual ping logic
        # For now, we rely on pnwkit's internal heartbeat
        pass
        
    async def _probe_health(self) -> bool:
        """Probe connection health with a test query."""
        try:
            self._raise_if_idle()
            return True
        except WebSocketIdleTimeout as e:
            logger.warning(f"Health probe failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Health probe failed: {e}")
            return False
            
    def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        return {
            "connection_state": self.connection_state.value,
            "circuit_breaker_state": self.circuit_breaker.get_state(),
            "circuit_breaker_failures": self.circuit_breaker.failure_count,
            "retry_count": self.retry_count,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None,
            "seconds_since_stream_activity": self._seconds_since_stream_activity(),
            "idle_reconnect_seconds": self.idle_reconnect_seconds,
            "initial_idle_reconnect_seconds": self.initial_idle_reconnect_seconds,
            "subscriptions": {
                key: {
                    "active": info.active,
                    "required": info.required,
                    "disabled": info.disabled,
                    "last_error": info.last_error,
                }
                for key, info in self.subscriptions.items()
            },
            # "heartbeat_healthy": self.heartbeat_monitor.is_healthy(),
            "health_probe_healthy": self.health_prober.is_healthy(),
            "buffer_size": len(self.event_buffer.buffer),
            "latest_sequence": self.event_buffer.get_latest_sequence(),
        }


# Singleton instance
_shared_websocket_manager: Optional[SharedWebSocketManager] = None


def get_shared_websocket_manager(api_key: str) -> SharedWebSocketManager:
    """
    Get the global shared WebSocket manager singleton.
    
    Args:
        api_key: PnW API key
        
    Returns:
        SharedWebSocketManager instance
    """
    global _shared_websocket_manager
    if _shared_websocket_manager is None:
        _shared_websocket_manager = SharedWebSocketManager(api_key)
    return _shared_websocket_manager

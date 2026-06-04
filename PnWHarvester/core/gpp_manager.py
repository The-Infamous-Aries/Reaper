"""
GPPManager — Orchestrator for all GPP components.

Provides:
- Component lifecycle management (start/stop)
- Health monitoring and status reporting
- Graceful degradation on component failure
- Centralized configuration and initialization
- Lock manager, database pool, and write queue coordination

This is the central orchestrator that manages all PnW Harvester components.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
import traceback

logger = logging.getLogger(__name__)


class ComponentState(Enum):
    """Component state."""
    INITIALIZED = "initialized"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class HealthStatus(Enum):
    """Health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health information for a component."""
    name: str
    state: ComponentState = ComponentState.INITIALIZED
    health: HealthStatus = HealthStatus.UNKNOWN
    last_check: Optional[datetime] = None
    error_count: int = 0
    last_error: Optional[str] = None
    stats: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "state": self.state.value,
            "health": self.health.value,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "stats": self.stats,
        }


@dataclass
class GPPManagerStats:
    """Overall GPPManager statistics."""
    total_components: int = 0
    running_components: int = 0
    healthy_components: int = 0
    degraded_components: int = 0
    unhealthy_components: int = 0
    uptime_seconds: float = 0.0
    total_errors: int = 0
    start_time: Optional[datetime] = None
    component_health: Dict[str, ComponentHealth] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_components": self.total_components,
            "running_components": self.running_components,
            "healthy_components": self.healthy_components,
            "degraded_components": self.degraded_components,
            "unhealthy_components": self.unhealthy_components,
            "uptime_seconds": self.uptime_seconds,
            "total_errors": self.total_errors,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "component_health": {
                k: v.to_dict() for k, v in self.component_health.items()
            },
        }


class GPPManager:
    """
    Orchestrator for all GPP components.
    
    Manages component lifecycle, health monitoring, and provides
    centralized coordination for the PnW Harvester system.
    """
    
    def __init__(
        self,
        global_nations_db=None,
        global_wars_db=None,
        irs_wars_db=None,
        bankrecs_db=None,
        holdings_db=None,
        beige_alerts_db=None,
        news_db=None,
        treaties_db=None,
        api_key: str = "",
        query_instance=None,
        websocket_manager=None,
        nation_cache=None,
    ):
        """
        Initialize the GPPManager.

        Args:
            global_nations_db: GlobalNationsDB instance
            global_wars_db: GlobalWarsDB instance
            irs_wars_db: IRSWarsDB instance
            bankrecs_db: BankrecsDB instance
            holdings_db: HoldingsDB instance
            beige_alerts_db: BeigeAlertDB instance
            news_db: NewsDB instance
            treaties_db: TreatiesDB instance
            api_key: PnW API v3 key
            query_instance: Query instance for timed queries
            websocket_manager: SharedWebSocketManager instance (optional)
            nation_cache: NationCache instance for fast nation/city data access
        """
        self.global_nations_db = global_nations_db
        self.global_wars_db = global_wars_db
        self.irs_wars_db = irs_wars_db
        self.bankrecs_db = bankrecs_db
        self.holdings_db = holdings_db
        self.beige_alerts_db = beige_alerts_db
        self.news_db = news_db
        self.treaties_db = treaties_db
        self.api_key = api_key
        self.query_instance = query_instance
        self.websocket_manager = websocket_manager
        self.nation_cache = nation_cache
        
        # Core infrastructure
        from .lock_manager import get_lock_manager
        from .database_pool import get_pool_manager
        from .write_queue import get_queue_manager
        
        self.lock_manager = get_lock_manager()
        self.pool_manager = get_pool_manager()
        self.queue_manager = get_queue_manager()
        
        # Configure queue manager with lock manager
        self.queue_manager.set_lock_manager(self.lock_manager)
        
        # Components
        self._components: Dict[str, Any] = {}
        self._component_health: Dict[str, ComponentHealth] = {}
        self._component_tasks: Dict[str, asyncio.Task] = {}
        
        # State
        self._running = False
        self._start_time: Optional[datetime] = None
        self._health_check_task: Optional[asyncio.Task] = None
        self._health_check_interval = 30.0  # seconds
        
        # Restart tracking to prevent loops
        self._restart_counts: Dict[str, int] = {}
        self._last_restart: Dict[str, datetime] = {}
        self._max_restarts_per_hour = 30  # Increased to handle predictable revenue stalls
        
        # Configurable silence threshold (seconds)
        import os
        self._max_silence_seconds = float(os.getenv("HARVESTER_MAX_SILENCE", "120"))
        
        logger.info(f"GPPManager initialized (max_silence={self._max_silence_seconds}s)")
    
    async def initialize(self):
        """
        Initialize all components.
        
        This should be called before start().
        """
        logger.info("Initializing GPPManager components...")
        
        # Initialize SharedWebSocketManager if not provided
        if self.websocket_manager is None:
            from .websocket_manager import get_shared_websocket_manager
            self.websocket_manager = get_shared_websocket_manager(self.api_key)
            await self.websocket_manager.initialize()
            logger.info("SharedWebSocketManager initialized")
        
        # Initialize core components
        await self._init_core_components()
        
        # Initialize GPP components
        await self._init_gpp_components()
        
        # Initialize health tracking
        self._update_health_summary()
        
        logger.info(f"GPPManager initialized with {len(self._components)} components")
    
    async def _init_core_components(self):
        """Initialize core infrastructure components."""
        # Lock manager is already initialized (singleton)
        # Pool manager - initialize pools for each DB
        if self.global_nations_db:
            await self.pool_manager.get_pool(self.global_nations_db.db_path)
        if self.irs_wars_db:
            await self.pool_manager.get_pool(self.irs_wars_db.db_path)
        if self.bankrecs_db:
            await self.pool_manager.get_pool(self.bankrecs_db.db_path)
        if self.beige_alerts_db:
            await self.pool_manager.get_pool(self.beige_alerts_db.db_path)
        if self.treaties_db:
            await self.pool_manager.get_pool(self.treaties_db.db_path)
        
        # NewsDB manages 3 DB files (weekly, monthly, yearly)
        # Initialize pools for all three
        if self.news_db:
            from PnWHarvester.db.news_db import _weekly_db_path, _monthly_db_path, _yearly_db_path
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            await self.pool_manager.get_pool(str(_weekly_db_path(0)))
            await self.pool_manager.get_pool(str(_monthly_db_path(0)))
            await self.pool_manager.get_pool(str(_yearly_db_path(now.year)))
        
        # Queue manager - initialize queues for each DB
        if self.global_nations_db:
            await self.queue_manager.get_queue(self.global_nations_db.db_path)
        if self.irs_wars_db:
            await self.queue_manager.get_queue(self.irs_wars_db.db_path)
        if self.bankrecs_db:
            await self.queue_manager.get_queue(self.bankrecs_db.db_path)
        if self.beige_alerts_db:
            await self.queue_manager.get_queue(self.beige_alerts_db.db_path)
        if self.treaties_db:
            await self.queue_manager.get_queue(self.treaties_db.db_path)
    
    async def _init_gpp_components(self):
        """Initialize GPP application components."""
        from PnWHarvester.components import (
            NationComponent,
            WarComponent,
            BankrecComponent,
            RevenueComponent,
            BeigeAlertComponent,
            TradeComponent,
            TreatyComponent,
            TimedQueriesComponent,
        )
        from PnWHarvester.components.news_component import NewsComponent
        
        # BeigeAlertComponent - create first as other components depend on it
        beige_component = BeigeAlertComponent()
        await beige_component.initialize()
        self._components["beige"] = beige_component
        self._component_health["beige"] = ComponentHealth(name="beige")
        
        # NewsComponent - create early as subscriptions depend on it
        if self.news_db:
            news_component = NewsComponent(
                news_db=self.news_db,
                global_nations_db=self.global_nations_db,
            )
            await news_component.initialize()
            self._components["news"] = news_component
            self._component_health["news"] = ComponentHealth(name="news")
        
        # NationComponent
        if self.global_nations_db:
            nation_component = NationComponent(
                global_db=self.global_nations_db,
                holdings_db=self.holdings_db,
                beige_component=beige_component,
                news_component=self._components.get("news"),
                websocket_manager=self.websocket_manager,
                api_key=self.api_key,  # Keep for backward compatibility
            )
            await nation_component.initialize()
            self._components["nation"] = nation_component
            self._component_health["nation"] = ComponentHealth(name="nation")
        
        # WarComponent
        if self.irs_wars_db:
            war_component = WarComponent(
                nw_db=self.irs_wars_db,
                holdings_db=self.holdings_db,
                global_nations_db=self.global_nations_db,
                global_wars_db=self.global_wars_db,
                websocket_manager=self.websocket_manager,
                api_key=self.api_key,  # Keep for backward compatibility
                news_component=self._components.get("news"),
            )
            await war_component.initialize()
            self._components["war"] = war_component
            self._component_health["war"] = ComponentHealth(name="war")
        
        # BankrecComponent
        if self.bankrecs_db:
            bankrec_component = BankrecComponent(
                bankrecs_db=self.bankrecs_db,
                holdings_db=self.holdings_db,
                news_component=self._components.get("news"),
                websocket_manager=self.websocket_manager,
                api_key=self.api_key,  # Keep for backward compatibility
            )
            await bankrec_component.initialize()
            self._components["bankrec"] = bankrec_component
            self._component_health["bankrec"] = ComponentHealth(name="bankrec")
        
        # TradeComponent
        if self.holdings_db:
            trade_component = TradeComponent(
                holdings_db=self.holdings_db,
                news_component=self._components.get("news"),
                websocket_manager=self.websocket_manager,
                api_key=self.api_key,  # Keep for backward compatibility
            )
            await trade_component.initialize()
            self._components["trade"] = trade_component
            self._component_health["trade"] = ComponentHealth(name="trade")

        # TreatyComponent
        if self.treaties_db:
            treaty_component = TreatyComponent(
                treaties_db=self.treaties_db,
                news_component=self._components.get("news"),
                websocket_manager=self.websocket_manager,
                api_key=self.api_key,  # Keep for backward compatibility
            )
            await treaty_component.initialize()
            self._components["treaty"] = treaty_component
            self._component_health["treaty"] = ComponentHealth(name="treaty")
        
        # RevenueComponent
        if self.global_nations_db and self.irs_wars_db:
            revenue_component = RevenueComponent(
                global_nations_db=self.global_nations_db,
                irs_wars_db=self.irs_wars_db,
                holdings_db=self.holdings_db,
                beige_component=beige_component,
                interval_seconds=7200,  # 2 hours
                nation_cache=self.nation_cache,
            )
            await revenue_component.initialize()
            self._components["revenue"] = revenue_component
            self._component_health["revenue"] = ComponentHealth(name="revenue")
        
        # TimedQueriesComponent
        if self.query_instance:
            timed_queries_component = TimedQueriesComponent(
                query_instance=self.query_instance,
                holdings_db=self.holdings_db,
                news_component=self._components.get("news"),
                interval_seconds=900,  # 15 minutes
            )
            await timed_queries_component.initialize()
            self._components["timed_queries"] = timed_queries_component
            self._component_health["timed_queries"] = ComponentHealth(name="timed_queries")
    
    async def start(self):
        """Start all components."""
        if self._running:
            logger.warning("GPPManager already running")
            return
        
        logger.info("Starting GPPManager...")
        self._running = True
        self._start_time = datetime.now(timezone.utc)
        
        # Start SharedWebSocketManager
        if self.websocket_manager:
            await self.websocket_manager.start()
            logger.info("SharedWebSocketManager started")
        
        # Start components
        # Subscription components use run_forever() for auto-restart
        # Background loop components (revenue, timed_queries) use _run_loop() for their loops
        # Helper components (beige, news) don't need start methods
        subscription_components = ["nation", "war", "bankrec", "trade", "treaty"]
        background_loop_components = ["revenue", "timed_queries"]
        
        for name, component in self._components.items():
            try:
                health = self._component_health[name]
                health.state = ComponentState.STARTING
                
                if name in subscription_components and hasattr(component, 'run_forever'):
                    # Launch subscription components as background tasks with auto-restart
                    task = asyncio.create_task(component.run_forever(), name=f"{name}_run_forever")
                    self._component_tasks[name] = task
                    health.state = ComponentState.RUNNING
                    health.health = HealthStatus.HEALTHY
                    health.last_check = datetime.now(timezone.utc)
                    logger.info(f"Component {name} started (run_forever)")
                elif name in background_loop_components and hasattr(component, '_run_loop'):
                    # Start background loop components by running their loop directly.
                    # This creates a tracked task that the manager can monitor and restart.
                    component.running = True
                    task = asyncio.create_task(self._run_background_loop(component, name), name=f"{name}_loop")
                    self._component_tasks[name] = task
                    health.state = ComponentState.RUNNING
                    health.health = HealthStatus.HEALTHY
                    health.last_check = datetime.now(timezone.utc)
                    logger.info(f"Component {name} started (background loop)")
                elif hasattr(component, 'start'):
                    # Start components with start method
                    await component.start()
                    health.state = ComponentState.RUNNING
                    health.health = HealthStatus.HEALTHY
                    health.last_check = datetime.now(timezone.utc)
                    logger.info(f"Component {name} started")
                else:
                    # Helper components don't need start
                    health.state = ComponentState.RUNNING
                    health.health = HealthStatus.HEALTHY
                    health.last_check = datetime.now(timezone.utc)
                    logger.info(f"Component {name} ready (no start method)")
            except Exception as e:
                logger.error(f"Failed to start component {name}: {e}", exc_info=True)
                health.state = ComponentState.ERROR
                health.health = HealthStatus.UNHEALTHY
                health.last_error = str(e)
                health.error_count += 1
        
        # Start health check loop
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        
        self._update_health_summary()
        logger.info("GPPManager started")
    
    async def stop(self):
        """Stop all components."""
        if not self._running:
            return
        
        logger.info("Stopping GPPManager...")
        self._running = False
        
        # Stop SharedWebSocketManager
        if self.websocket_manager:
            await self.websocket_manager.stop()
            logger.info("SharedWebSocketManager stopped")
        
        # Stop health check task
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # Stop component tasks (subscription components)
        for name, task in self._component_tasks.items():
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                logger.info(f"Component {name} task cancelled")
        self._component_tasks.clear()
        
        # Stop components
        for name, component in self._components.items():
            try:
                health = self._component_health[name]
                health.state = ComponentState.STOPPING
                
                # Stop component if it has a stop method
                if hasattr(component, 'stop'):
                    await component.stop()
                
                health.state = ComponentState.STOPPED
                logger.info(f"Component {name} stopped")
            except Exception as e:
                logger.error(f"Failed to stop component {name}: {e}", exc_info=True)
        
        # Flush all queues
        await self.queue_manager.flush_all()
        
        # Close all pools
        await self.pool_manager.close_all()
        
        self._update_health_summary()
        logger.info("GPPManager stopped")
    
    async def _run_background_loop(self, component, name: str):
        """
        Run a background loop component with auto-restart on failure.
        
        This wraps the component's _run_loop() method with proper exception
        handling and restart logic, similar to how run_forever() works for
        subscription components.
        
        Args:
            component: The component with a _run_loop() method
            name: Component name for logging
        """
        retry_count = 0
        max_retry_delay = 300  # 5 minutes max
        base_delay = 10  # Start with 10 seconds
        
        while self._running:
            try:
                # Ensure component is marked as running
                component.running = True
                
                # Run the component's loop
                await component._run_loop()
                
                # If loop exits normally while manager is still running, restart it
                if self._running:
                    logger.warning(f"Background loop {name} exited normally, restarting...")
                    retry_count = 0
                    await asyncio.sleep(base_delay)
                    
            except asyncio.CancelledError:
                logger.info(f"Background loop {name} cancelled")
                break
            except Exception as e:
                retry_count += 1
                delay = min(base_delay * (2 ** min(retry_count - 1, 5)), max_retry_delay)
                
                logger.error(
                    f"Background loop {name} crashed ({e}) — "
                    f"retry {retry_count}, restarting in {delay:.1f}s",
                    exc_info=True
                )
                
                # Mark component as not running
                component.running = False
                
                # Wait before restart
                await asyncio.sleep(delay)
        
        logger.info(f"Background loop {name} stopped")

    async def _health_check_loop(self):
        """Background health check loop."""
        # Initial delay to give components time to receive first messages
        await asyncio.sleep(60)  # 1 minute delay before first health check
        
        while self._running:
            try:
                await self._check_component_health()
                await asyncio.sleep(self._health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}", exc_info=True)
    
    async def _check_component_health(self):
        """Check health of all components with stall detection."""
        # Skip restarts if shutdown is in progress
        if not self._running:
            return

        for name, component in self._components.items():
            restart_triggered = False
            try:
                health = self._component_health[name]
                
                # Get component stats if available
                if hasattr(component, 'get_component_stats'):
                    try:
                        stats = await component.get_component_stats()
                        health.stats = stats
                    except Exception as e:
                        logger.debug(f"Failed to get stats for {name}: {e}")
                
                # Check ActivityTracker for subscription stalls (subscription components)
                if hasattr(component, 'activity_tracker') and hasattr(component, 'running'):
                    # Only check if component has an activity_tracker (subscription-based)
                    if component.running:
                        tracker = component.activity_tracker
                        
                        # Sync tracker threshold with manager config for subscription components only
                        # Background loop components (timed_queries, revenue) have their own thresholds
                        background_loop_components = ["revenue", "timed_queries"]
                        if name not in background_loop_components and tracker.max_silence != self._max_silence_seconds:
                            tracker.max_silence = self._max_silence_seconds
                        
                        unhealthy = tracker.get_unhealthy_subscriptions()
                        
                        logger.debug(f"Component {name} unhealthy subscriptions: {unhealthy}")
                        
                        # Check if all subscriptions have never received messages (normal for infrequent subscriptions)
                        # If so, don't restart the component
                        all_no_messages = True
                        for sub_health in tracker.get_all_health().values():
                            if sub_health.seconds_since_last_message() is not None:
                                all_no_messages = False
                                break
                        
                        if all_no_messages:
                            logger.debug(f"Component {name}: all subscriptions have never received messages - skipping stall check")
                            continue
                        
                        if unhealthy:
                            # Get detailed stall info for logging
                            stall_details = []
                            for sub_name in unhealthy:
                                sub_health = tracker.get_health(sub_name)
                                if sub_health:
                                    seconds = sub_health.seconds_since_last_message()
                                    if seconds is not None:
                                        stall_details.append(f"{sub_name}({seconds:.0f}s)")
                                    else:
                                        stall_details.append(f"{sub_name}(no-msgs)")
                                else:
                                    stall_details.append(sub_name)

                            health.health = HealthStatus.UNHEALTHY
                            health.last_error = f"Stalled: {', '.join(stall_details)}"
                            health.error_count += 1
                            logger.warning(
                                f"Component {name} stalled: {', '.join(stall_details)} "
                                f"[threshold={self._max_silence_seconds}s]"
                            )

                            # Trigger restart
                            restart_triggered = True
                            await self._restart_component(name)
                        else:
                            # Healthy - update status
                            restart_triggered = False
                            if health.state == ComponentState.RUNNING:
                                health.health = HealthStatus.HEALTHY
                                # Reset error count on sustained health
                                if health.error_count > 0:
                                    health.error_count = 0
                                    health.last_error = None
                
                # Check WebSocket connection health for subscription components with kit
                elif hasattr(component, 'kit') and hasattr(component, 'running') and component.running:
                    kit = getattr(component, 'kit', None)
                    if kit and hasattr(kit, 'socket'):
                        socket = getattr(kit, 'socket', None)
                        if socket and hasattr(socket, 'ws'):
                            ws = getattr(socket, 'ws', None)
                            if ws and ws.closed:
                                health.health = HealthStatus.UNHEALTHY
                                health.last_error = "WebSocket connection closed"
                                health.error_count += 1
                                logger.warning(f"Component {name} WebSocket closed - triggering restart")
                                restart_triggered = True
                                await self._restart_component(name)
                
                health.last_check = datetime.now(timezone.utc)
                
                # Determine health based on state and errors (skip if restart just triggered)
                if not restart_triggered and health.state == ComponentState.RUNNING:
                    if health.error_count == 0:
                        health.health = HealthStatus.HEALTHY
                    elif health.error_count < 5:
                        health.health = HealthStatus.DEGRADED
                    else:
                        health.health = HealthStatus.UNHEALTHY
                elif not restart_triggered:
                    health.health = HealthStatus.UNKNOWN
                    
            except Exception as e:
                logger.error(f"Health check failed for component {name}: {e}", exc_info=True)
                health = self._component_health[name]
                health.health = HealthStatus.UNHEALTHY
                health.last_error = str(e)
                health.error_count += 1
        
        self._update_health_summary()
    
    async def _restart_component(self, name: str):
        """Restart a specific component with rate limiting."""
        component = self._components.get(name)
        if not component:
            logger.error(f"Cannot restart {name}: component not found")
            return
        
        # Check restart rate limit
        now = datetime.now(timezone.utc)
        last_restart = self._last_restart.get(name)
        restart_count = self._restart_counts.get(name, 0)

        # Check if component has been running healthy for 5+ minutes since last restart - reset counter
        health = self._component_health[name]
        if last_restart and health.state == ComponentState.RUNNING:
            minutes_since_restart = (now - last_restart).total_seconds() / 60
            if minutes_since_restart >= 5:
                # Component ran healthy for 5+ min since last restart, reset restart budget
                if restart_count > 0:
                    logger.info(f"Component {name} ran healthy for {minutes_since_restart:.0f}m since last restart - resetting restart counter")
                    self._restart_counts[name] = 0
                    restart_count = 0

        if last_restart:
            hours_since = (now - last_restart).total_seconds() / 3600
            if hours_since < 1 and restart_count >= self._max_restarts_per_hour:
                logger.error(
                    f"Component {name} exceeded max restarts ({self._max_restarts_per_hour}/hour). "
                    f"Manual intervention required."
                )
                health.health = HealthStatus.UNHEALTHY
                health.last_error = f"Max restarts exceeded ({self._max_restarts_per_hour}/hour)"
                return
            elif hours_since >= 1:
                # Reset counter after 1 hour
                self._restart_counts[name] = 0
        
        health = self._component_health[name]
        health.state = ComponentState.STOPPING
        
        try:
            # Cancel existing task if any
            if name in self._component_tasks:
                task = self._component_tasks[name]
                if task and not task.done():
                    task.cancel()
                    try:
                        await asyncio.wait_for(task, timeout=10.0)
                    except asyncio.TimeoutError:
                        logger.warning(f"Component {name} task did not cancel cleanly")
                    except asyncio.CancelledError:
                        pass
                del self._component_tasks[name]
            
            # Stop the component
            if hasattr(component, 'stop'):
                await component.stop()
            
            health.state = ComponentState.STOPPED
            logger.info(f"Component {name} stopped for restart")
            
            # Brief pause to ensure clean teardown
            await asyncio.sleep(2)
            
            # Restart the component
            health.state = ComponentState.STARTING
            
            subscription_components = ["nation", "war", "bankrec", "trade", "treaty"]
            background_loop_components = ["revenue", "timed_queries"]
            
            if name in subscription_components and hasattr(component, 'run_forever'):
                # Add jitter to prevent thundering herd
                import random
                jitter = random.uniform(0, 2)
                await asyncio.sleep(jitter)
                
                task = asyncio.create_task(component.run_forever(), name=f"{name}_run_forever")
                self._component_tasks[name] = task
                health.state = ComponentState.RUNNING
                health.health = HealthStatus.HEALTHY
                health.last_check = datetime.now(timezone.utc)
                logger.info(f"Component {name} restarted (run_forever, jitter={jitter:.1f}s)")
            elif name in background_loop_components and hasattr(component, '_run_loop'):
                # Restart background loop component via _run_background_loop wrapper
                import random
                jitter = random.uniform(0, 2)
                await asyncio.sleep(jitter)
                
                component.running = True
                task = asyncio.create_task(self._run_background_loop(component, name), name=f"{name}_loop")
                self._component_tasks[name] = task
                health.state = ComponentState.RUNNING
                health.health = HealthStatus.HEALTHY
                health.last_check = datetime.now(timezone.utc)
                logger.info(f"Component {name} restarted (background loop, jitter={jitter:.1f}s)")
            elif hasattr(component, 'start'):
                await component.start()
                health.state = ComponentState.RUNNING
                health.health = HealthStatus.HEALTHY
                health.last_check = datetime.now(timezone.utc)
                logger.info(f"Component {name} restarted")
            
            # Update restart tracking only for successful starts
            # (component is now running and healthy)
            self._last_restart[name] = now
            self._restart_counts[name] = self._restart_counts.get(name, 0) + 1
            
            # Reset error count on successful restart
            health.error_count = 0
            health.last_error = None
            
        except Exception as e:
            logger.error(f"Failed to restart component {name}: {e}", exc_info=True)
            health.state = ComponentState.ERROR
            health.health = HealthStatus.UNHEALTHY
            health.last_error = str(e)
            health.error_count += 1
    
    def _update_health_summary(self):
        """Update overall health summary."""
        total = len(self._components)
        running = sum(
            1 for h in self._component_health.values()
            if h.state == ComponentState.RUNNING
        )
        healthy = sum(
            1 for h in self._component_health.values()
            if h.health == HealthStatus.HEALTHY
        )
        degraded = sum(
            1 for h in self._component_health.values()
            if h.health == HealthStatus.DEGRADED
        )
        unhealthy = sum(
            1 for h in self._component_health.values()
            if h.health == HealthStatus.UNHEALTHY
        )
        total_errors = sum(h.error_count for h in self._component_health.values())
        
        uptime = 0.0
        if self._start_time:
            uptime = (datetime.now(timezone.utc) - self._start_time).total_seconds()
    
    async def get_stats(self) -> GPPManagerStats:
        """
        Get overall statistics.
        
        Returns:
            GPPManagerStats with comprehensive statistics
        """
        # Update component health
        await self._check_component_health()
        
        total = len(self._components)
        running = sum(
            1 for h in self._component_health.values()
            if h.state == ComponentState.RUNNING
        )
        healthy = sum(
            1 for h in self._component_health.values()
            if h.health == HealthStatus.HEALTHY
        )
        degraded = sum(
            1 for h in self._component_health.values()
            if h.health == HealthStatus.DEGRADED
        )
        unhealthy = sum(
            1 for h in self._component_health.values()
            if h.health == HealthStatus.UNHEALTHY
        )
        total_errors = sum(h.error_count for h in self._component_health.values())
        
        uptime = 0.0
        if self._start_time:
            uptime = (datetime.now(timezone.utc) - self._start_time).total_seconds()
        
        return GPPManagerStats(
            total_components=total,
            running_components=running,
            healthy_components=healthy,
            degraded_components=degraded,
            unhealthy_components=unhealthy,
            uptime_seconds=uptime,
            total_errors=total_errors,
            start_time=self._start_time,
            component_health=dict(self._component_health),
        )
    
    def get_component(self, name: str) -> Optional[Any]:
        """
        Get a component by name.
        
        Args:
            name: Component name (nation, war, bankrec, revenue, beige)
            
        Returns:
            Component instance or None
        """
        return self._components.get(name)
    
    def is_running(self) -> bool:
        """Check if GPPManager is running."""
        return self._running
    
    def __repr__(self) -> str:
        return f"GPPManager(components={len(self._components)}, running={self._running})"


# Global singleton instance
_global_gpp_manager: Optional[GPPManager] = None


def get_gpp_manager(
    global_nations_db=None,
    global_wars_db=None,
    irs_wars_db=None,
    bankrecs_db=None,
    holdings_db=None,
    beige_alerts_db=None,
    news_db=None,
    treaties_db=None,
    api_key: str = "",
    query_instance=None,
    websocket_manager=None,
    nation_cache=None,
) -> GPPManager:
    """
    Get the global GPPManager singleton.

    Args:
        global_nations_db: GlobalNationsDB instance
        global_wars_db: GlobalWarsDB instance
        irs_wars_db: IRSWarsDB instance
        bankrecs_db: BankrecsDB instance
        holdings_db: HoldingsDB instance
        beige_alerts_db: BeigeAlertDB instance
        news_db: NewsDB instance
        treaties_db: TreatiesDB instance
        api_key: PnW API v3 key
        query_instance: Query instance for timed queries
        websocket_manager: SharedWebSocketManager instance (optional)

    Returns:
        The global GPPManager instance
    """
    global _global_gpp_manager
    if _global_gpp_manager is None:
        _global_gpp_manager = GPPManager(
            global_nations_db=global_nations_db,
            global_wars_db=global_wars_db,
            irs_wars_db=irs_wars_db,
            bankrecs_db=bankrecs_db,
            holdings_db=holdings_db,
            beige_alerts_db=beige_alerts_db,
            news_db=news_db,
            treaties_db=treaties_db,
            api_key=api_key,
            query_instance=query_instance,
            websocket_manager=websocket_manager,
            nation_cache=nation_cache,
        )
    return _global_gpp_manager

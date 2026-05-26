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
        api_key: str = "",
        query_instance=None,
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
            api_key: PnW API v3 key
            query_instance: Query instance for timed queries
        """
        self.global_nations_db = global_nations_db
        self.global_wars_db = global_wars_db
        self.irs_wars_db = irs_wars_db
        self.bankrecs_db = bankrecs_db
        self.holdings_db = holdings_db
        self.beige_alerts_db = beige_alerts_db
        self.news_db = news_db
        self.api_key = api_key
        self.query_instance = query_instance
        
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
        
        logger.info("GPPManager initialized")
    
    async def initialize(self):
        """
        Initialize all components.
        
        This should be called before start().
        """
        logger.info("Initializing GPPManager components...")
        
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
    
    async def _init_gpp_components(self):
        """Initialize GPP application components."""
        from PnWHarvester.components import (
            NationComponent,
            WarComponent,
            BankrecComponent,
            RevenueComponent,
            BeigeAlertComponent,
            TradeComponent,
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
                api_key=self.api_key,
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
                api_key=self.api_key,
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
                api_key=self.api_key,
            )
            await bankrec_component.initialize()
            self._components["bankrec"] = bankrec_component
            self._component_health["bankrec"] = ComponentHealth(name="bankrec")
        
        # TradeComponent
        if self.holdings_db:
            trade_component = TradeComponent(
                holdings_db=self.holdings_db,
                news_component=self._components.get("news"),
                api_key=self.api_key,
            )
            await trade_component.initialize()
            self._components["trade"] = trade_component
            self._component_health["trade"] = ComponentHealth(name="trade")
        
        # RevenueComponent
        if self.global_nations_db and self.irs_wars_db:
            revenue_component = RevenueComponent(
                global_nations_db=self.global_nations_db,
                irs_wars_db=self.irs_wars_db,
                holdings_db=self.holdings_db,
                beige_component=beige_component,
                interval_seconds=7200,  # 2 hours
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
        
        # Start components
        # Subscription components (nation, war, bankrec, trade) use run_forever() for auto-restart
        # Background loop components (revenue, timed_queries) use start() for their loops
        # Helper components (beige, news) don't need start methods
        subscription_components = ["nation", "war", "bankrec", "trade"]
        background_loop_components = ["revenue", "timed_queries"]
        
        for name, component in self._components.items():
            try:
                health = self._component_health[name]
                health.state = ComponentState.STARTING
                
                if name in subscription_components and hasattr(component, 'run_forever'):
                    # Launch subscription components as background tasks with auto-restart
                    task = asyncio.create_task(component.run_forever())
                    self._component_tasks[name] = task
                    health.state = ComponentState.RUNNING
                    health.health = HealthStatus.HEALTHY
                    health.last_check = datetime.now(timezone.utc)
                    logger.info(f"Component {name} started (run_forever)")
                elif name in background_loop_components and hasattr(component, 'start'):
                    # Start background loop components (e.g., revenue, timed_queries)
                    task = asyncio.create_task(component.start())
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
    
    async def _health_check_loop(self):
        """Background health check loop."""
        while self._running:
            try:
                await self._check_component_health()
                await asyncio.sleep(self._health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}", exc_info=True)
    
    async def _check_component_health(self):
        """Check health of all components."""
        for name, component in self._components.items():
            try:
                health = self._component_health[name]
                
                # Get component stats if available
                if hasattr(component, 'get_component_stats'):
                    stats = await component.get_component_stats()
                    health.stats = stats
                
                # Check WebSocket connection health for subscription components
                if hasattr(component, 'kit') and hasattr(component, 'running') and component.running:
                    kit = getattr(component, 'kit', None)
                    if kit and hasattr(kit, 'socket'):
                        socket = getattr(kit, 'socket', None)
                        if socket and hasattr(socket, 'ws'):
                            ws = getattr(socket, 'ws', None)
                            if ws and ws.closed:
                                health.health = HealthStatus.UNHEALTHY
                                health.last_error = "WebSocket connection closed"
                                health.error_count += 1
                                logger.warning(f"Component {name} WebSocket connection is closed")
                
                health.last_check = datetime.now(timezone.utc)
                
                # Determine health based on state and errors
                if health.state == ComponentState.RUNNING:
                    if health.error_count == 0:
                        health.health = HealthStatus.HEALTHY
                    elif health.error_count < 5:
                        health.health = HealthStatus.DEGRADED
                    else:
                        health.health = HealthStatus.UNHEALTHY
                else:
                    health.health = HealthStatus.UNKNOWN
                    
            except Exception as e:
                logger.error(f"Health check failed for component {name}: {e}", exc_info=True)
                health = self._component_health[name]
                health.health = HealthStatus.UNHEALTHY
                health.last_error = str(e)
                health.error_count += 1
        
        self._update_health_summary()
    
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
    api_key: str = "",
    query_instance=None,
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
        api_key: PnW API v3 key
        query_instance: Query instance for timed queries

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
            api_key=api_key,
            query_instance=query_instance,
        )
    return _global_gpp_manager

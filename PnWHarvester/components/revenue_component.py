"""
RevenueComponent — GPP component for turn revenue processing.

Handles:
- Turn revenue calculation and application for all tracked nations
- Bulk updates to HoldingsDB and GlobalNationsDB
- Beige alert updates

This component writes to HoldingsDB, GlobalNationsDB, and beige_alerts_db.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RevenueProcessor:
    """Processes turn revenue for nations."""
    
    def __init__(self, global_nations_db, irs_wars_db, holdings_db=None):
        """
        Initialize the revenue processor.
        
        Args:
            global_nations_db: GlobalNationsDB instance
            irs_wars_db: IRSWarsDB instance
            holdings_db: HoldingsDB instance (optional)
        """
        self.global_nations_db = global_nations_db
        self.irs_wars_db = irs_wars_db
        self.holdings_db = holdings_db
    
    async def calculate_turn_revenue(self, nation_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate turn revenue for a nation.
        
        Args:
            nation_data: Nation data from GlobalNationsDB
            
        Returns:
            Dictionary with revenue breakdown
        """
        # Base revenue formula (simplified)
        # Revenue = GNI * (1 - tax_rate) + city_revenue
        
        gni = float(nation_data.get("gross_national_income") or 0)
        tax_bracket = nation_data.get("tax_id", 0)
        num_cities = int(nation_data.get("num_cities") or 0)
        
        # Tax rate from bracket (simplified)
        tax_rates = {0: 0.0, 1: 0.05, 2: 0.10, 3: 0.15, 4: 0.20, 5: 0.25}
        tax_rate = tax_rates.get(tax_bracket, 0.15)
        
        # Net after tax
        net_income = gni * (1 - tax_rate)
        
        # City revenue (simplified)
        city_revenue = num_cities * 100  # Base per city
        
        total_revenue = net_income + city_revenue
        
        return {
            "total": total_revenue,
            "net_income": net_income,
            "city_revenue": city_revenue,
            "tax_rate": tax_rate,
        }
    
    async def apply_turn_revenue(self, nation_id: int, revenue: Dict[str, float]):
        """
        Apply turn revenue to a nation.
        
        Args:
            nation_id: Nation ID
            revenue: Revenue breakdown from calculate_turn_revenue
        """
        if self.holdings_db:
            await self.holdings_db.apply_turn_revenue(
                nation_id=nation_id,
                money_delta=revenue["total"],
                resource_deltas={
                    "coal": revenue.get("coal", 0),
                    "oil": revenue.get("oil", 0),
                    "uranium": revenue.get("uranium", 0),
                    "iron": revenue.get("iron", 0),
                    "bauxite": revenue.get("bauxite", 0),
                    "lead": revenue.get("lead", 0),
                    "gasoline": revenue.get("gasoline", 0),
                    "munitions": revenue.get("munitions", 0),
                    "steel": revenue.get("steel", 0),
                    "aluminum": revenue.get("aluminum", 0),
                    "food": revenue.get("food", 0),
                },
                turn_date=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            )


class BeigeAlertUpdater:
    """Updates beige alerts based on nation state."""
    
    def __init__(self, global_nations_db, beige_component=None):
        """
        Initialize the beige alert updater.
        
        Args:
            global_nations_db: GlobalNationsDB instance
            beige_component: BeigeAlertComponent instance (optional)
        """
        self.global_nations_db = global_nations_db
        self.beige_component = beige_component
    
    async def update_beige_alerts(self, nation_id: int, nation_data: Dict[str, Any]):
        """
        Update beige alerts for a nation.
        
        Args:
            nation_id: Nation ID
            nation_data: Nation data from GlobalNationsDB
        """
        try:
            # Use BeigeAlertComponent if available, otherwise fall back to direct calls
            if self.beige_component:
                alerts = await self.beige_component.get_alerts_for_nation(nation_id)
            else:
                from Systems.Functions.beige_alerts_db import get_beige_alerts_for_nation
                alerts = await get_beige_alerts_for_nation(nation_id)
            
            if not alerts:
                return
            
            beige_turns = int(nation_data.get("beige_turns") or 0)
            
            # Calculate projected loot
            from Systems.Functions.beige_alerts_db import LOOT_MULTIPLIERS, RESOURCES
            war_type = "ordinary_war"  # Simplified
            loot_multiplier = LOOT_MULTIPLIERS["war_type"].get(war_type, 0.10)
            
            # Get nation resources for loot calculation
            resources = {r: float(nation_data.get(r) or 0) for r in RESOURCES}
            total_loot = sum(resources.values()) * loot_multiplier
            
            # Update alerts
            to_update = []
            to_delete = []
            
            for alert in alerts:
                alert_id = alert["id"]
                if beige_turns == 0:
                    to_delete.append(alert_id)
                else:
                    to_update.append((beige_turns, total_loot, alert_id))
            
            if to_update or to_delete:
                if self.beige_component:
                    # Update via component
                    for alert_id in to_delete:
                        await self.beige_component.delete_alert(alert_id)
                    for (beige_turns_val, total_loot_val, alert_id) in to_update:
                        await self.beige_component.update_alert(alert_id, beige_turns_val, total_loot_val)
                else:
                    # Fallback to direct batch update
                    from Systems.Functions.beige_alerts_db import batch_update_beige_alerts
                    await batch_update_beige_alerts(to_update, to_delete)
                logger.debug(f"Updated {len(to_update)} beige alerts, deleted {len(to_delete)}")
        
        except Exception as e:
            logger.error(f"Failed to update beige alerts for nation {nation_id}: {e}")


class RevenueComponent:
    """
    GPP component for turn revenue processing.
    
    Orchestrates the sub-components for processing turn revenue.
    """
    
    def __init__(
        self,
        global_nations_db,
        irs_wars_db,
        holdings_db=None,
        beige_component=None,
        interval_seconds: int = 7200,  # 2 hours
    ):
        """
        Initialize the RevenueComponent.
        
        Args:
            global_nations_db: GlobalNationsDB instance
            irs_wars_db: IRSWarsDB instance
            holdings_db: HoldingsDB instance (optional)
            beige_component: BeigeAlertComponent instance (optional)
            interval_seconds: Revenue processing interval (default: 2 hours)
        """
        self.global_nations_db = global_nations_db
        self.irs_wars_db = irs_wars_db
        self.holdings_db = holdings_db
        self.beige_component = beige_component
        self.interval_seconds = interval_seconds
        self.running = False
        self._task: Optional[asyncio.Task] = None
        
        # Sub-components
        self.revenue_processor = RevenueProcessor(global_nations_db, irs_wars_db, holdings_db)
        self.beige_updater = BeigeAlertUpdater(global_nations_db, beige_component)
    
    async def initialize(self):
        """Initialize the component."""
        logger.info("RevenueComponent initialized")
    
    async def process_turn_revenue_batch(self):
        """Process turn revenue for all tracked nations."""
        if not self.global_nations_db:
            return
        
        try:
            # Get all nations with active wars or tracked status
            nations = await self.global_nations_db.get_all_nations()
            
            processed = 0
            for nation in nations:
                nation_id = nation.get("id")
                if not nation_id:
                    continue
                
                # Calculate revenue
                revenue = await self.revenue_processor.calculate_turn_revenue(nation)
                
                # Apply revenue
                await self.revenue_processor.apply_turn_revenue(nation_id, revenue)
                
                # Update beige alerts
                await self.beige_updater.update_beige_alerts(nation_id, nation)
                
                processed += 1
            
            logger.info(f"Turn revenue processed for {processed} nations")
            
        except Exception as e:
            logger.error(f"Failed to process turn revenue: {e}", exc_info=True)
    
    async def start(self):
        """Start the revenue processing loop."""
        if self.running:
            logger.warning("RevenueComponent already running")
            return
        
        self.running = True
        self._task = asyncio.create_task(self._revenue_loop())
        logger.info("RevenueComponent started")
    
    async def stop(self):
        """Stop the revenue processing loop."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("RevenueComponent stopped")
    
    async def _revenue_loop(self):
        """Revenue processing loop."""
        while self.running:
            try:
                await self.process_turn_revenue_batch()
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Revenue loop error: {e}", exc_info=True)
                await asyncio.sleep(self.interval_seconds)
    
    async def get_component_stats(self) -> Dict[str, Any]:
        """Get component statistics."""
        return {
            "type": "RevenueComponent",
            "running": self.running,
            "interval_seconds": self.interval_seconds,
            "global_nations_db_path": self.global_nations_db.db_path if self.global_nations_db else None,
            "irs_wars_db_path": self.irs_wars_db.db_path if self.irs_wars_db else None,
            "holdings_db_path": self.holdings_db.db_path if self.holdings_db else None,
        }

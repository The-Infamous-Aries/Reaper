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
    
    def __init__(self, global_nations_db, irs_wars_db, holdings_db=None, reaper_db_path=None):
        """
        Initialize the revenue processor.
        
        Args:
            global_nations_db: GlobalNationsDB instance
            irs_wars_db: IRSWarsDB instance
            holdings_db: HoldingsDB instance (optional)
            reaper_db_path: Path to reaper.db for colors/radiation data (optional)
        """
        self.global_nations_db = global_nations_db
        self.irs_wars_db = irs_wars_db
        self.holdings_db = holdings_db
        self._reaper_db_path = reaper_db_path
        self._reaper_db_conn = None
        self._colors_data = None
        self._radiation_data = {'na': 0, 'sa': 0, 'eu': 0, 'as': 0, 'af': 0, 'au': 0, 'an': 0}
    
    async def initialize(self):
        """Initialize the reaper DB connection and load colors/radiation data once."""
        if self._reaper_db_path:
            import aiosqlite
            self._reaper_db_conn = await aiosqlite.connect(self._reaper_db_path)
            
            # Load colors data once from the colors table
            try:
                cursor = await self._reaper_db_conn.execute(
                    "SELECT color, turn_bonus FROM colors ORDER BY timestamp DESC LIMIT 100"
                )
                rows = await cursor.fetchall()
                await cursor.close()
                # Get the latest entry for each color
                color_map = {}
                for row in rows:
                    color_map[row[0]] = row[1]
                self._colors_data = color_map
                logger.info(f"Loaded {len(self._colors_data)} color entries")
            except Exception as e:
                logger.warning(f"Could not load colors from Reaper DB: {e}")
            
            # Load radiation data once from the radiation table
            try:
                cursor = await self._reaper_db_conn.execute(
                    "SELECT * FROM radiation ORDER BY timestamp DESC LIMIT 1"
                )
                row = await cursor.fetchone()
                await cursor.close()
                if row:
                    # row structure: timestamp, global_level, north_america, south_america, europe, africa, asia, australia, antarctica
                    global_rad = row[1] if len(row) > 1 else 0
                    self._radiation_data = {
                        'na': (row[2] if len(row) > 2 else 0 + global_rad) / -1000,
                        'sa': (row[3] if len(row) > 3 else 0 + global_rad) / -1000,
                        'eu': (row[4] if len(row) > 4 else 0 + global_rad) / -1000,
                        'as': (row[5] if len(row) > 5 else 0 + global_rad) / -1000,
                        'af': (row[6] if len(row) > 6 else 0 + global_rad) / -1000,
                        'au': (row[7] if len(row) > 7 else 0 + global_rad) / -1000,
                        'an': (row[8] if len(row) > 8 else 0 + global_rad) / -1000
                    }
                    logger.info("Loaded radiation data")
            except Exception as e:
                logger.warning(f"Could not load radiation from Reaper DB: {e}")
        else:
            logger.info("No reaper_db_path provided, using default values")
    
    def get_colors_data(self):
        """Get the loaded colors data."""
        return self._colors_data
    
    def get_radiation_data(self):
        """Get the loaded radiation data."""
        return self._radiation_data
    
    async def close(self):
        """Close the Reaper DB connection if open."""
        if self._reaper_db_conn:
            await self._reaper_db_conn.close()
            self._reaper_db_conn = None
    
    async def calculate_turn_revenue(self, nation_data: Dict[str, Any], colors_data: Optional[Dict[str, float]] = None, radiation_data: Optional[Dict[str, float]] = None, color_bonus: float = 0.0, is_war: bool = False) -> Dict[str, float]:
        """
        Calculate turn revenue for a nation using the full calculation.
        
        Args:
            nation_data: Nation data from GlobalNationsDB (must include cities)
            colors_data: Colors data loaded once for all nations
            radiation_data: Radiation data loaded once for all nations
            color_bonus: Color bonus for the nation
            is_war: Whether the nation is at war
            
        Returns:
            Dictionary with revenue breakdown
        """
        try:
            from Systems.PnW.Util.rev_correct import revenue_calc
            from datetime import datetime, timezone
            
            # Use the actual revenue calculation function directly without any DB fallbacks
            # All context must be provided - no fallback to DB calls
            dummy_prices = {
                'coal': 1.0, 'oil': 1.0, 'uranium': 1.0, 'iron': 1.0, 'bauxite': 1.0,
                'lead': 1.0, 'gasoline': 1.0, 'munitions': 1.0, 'steel': 1.0, 'aluminum': 1.0, 'food': 1.0
            }
            
            # Seasonal modifiers based on current time
            seasonal_mod = {'na': 1, 'sa': 1, 'eu': 1, 'as': 1, 'af': 1, 'au': 1, 'an': 0.5}
            current_month = datetime.now(timezone.utc).month
            if current_month in (6, 7, 8):  # Summer in Northern Hemisphere
                seasonal_mod.update({'na': 1.2, 'as': 1.2, 'eu': 1.2, 'sa': 0.8, 'af': 0.8, 'au': 0.8})
            elif current_month in (12, 1, 2):  # Winter in Northern Hemisphere
                seasonal_mod.update({'na': 0.8, 'as': 0.8, 'eu': 0.8, 'sa': 1.2, 'af': 1.2, 'au': 1.2})
            
            # Call the actual revenue calculation function directly
            # This avoids all DB fallback logic in calculate_full_revenue_with_query
            revenue_data = await revenue_calc(
                message=None,
                nation=nation_data,
                radiation=radiation_data or {'na': 0, 'sa': 0, 'eu': 0, 'as': 0, 'af': 0, 'au': 0, 'an': 0},
                treasures=[],  # Treasures are included in nation_data if present
                prices=dummy_prices,
                colors=colors_data or {},
                seasonal_mod=seasonal_mod,
                build=None,
                single_city=False,
                include_spies=True,
                is_war=is_war if is_war else None,
            )
            
            # Extract the key values for holdings update
            return {
                "total": revenue_data.get("net_income", 0.0),  # Net income after tax
                "gross_income": revenue_data.get("gross_income", 0.0),
                "resources": {
                    "coal": revenue_data.get("coal", 0.0),
                    "oil": revenue_data.get("oil", 0.0),
                    "uranium": revenue_data.get("uranium", 0.0),
                    "iron": revenue_data.get("iron", 0.0),
                    "bauxite": revenue_data.get("bauxite", 0.0),
                    "lead": revenue_data.get("lead", 0.0),
                    "gasoline": revenue_data.get("gasoline", 0.0),
                    "munitions": revenue_data.get("munitions", 0.0),
                    "steel": revenue_data.get("steel", 0.0),
                    "aluminum": revenue_data.get("aluminum", 0.0),
                    "food": revenue_data.get("food", 0.0),
                },
                "full_data": revenue_data,  # Keep full data for debugging
            }
            
        except Exception as e:
            logger.error(f"Error calculating revenue: {e}", exc_info=True)
            return self._get_zero_revenue()
    
    async def _get_nation_with_cached_cities(self, nation_id: int) -> Optional[Dict[str, Any]]:
        """Get nation data with cities from database cache and transform format."""
        try:
            # Get basic nation data
            nation_data = await self.global_nations_db.get_nation(nation_id)
            if not nation_data:
                return None
            
            # Get cached city data
            cities = await self.global_nations_db.get_cities_for_nation(nation_id)
            if not cities:
                logger.warning(f"No cached cities found for nation {nation_id}")
                return None
            
            # Transform city data format to match revenue calculation expectations
            transformed_cities = []
            for city in cities:
                transformed_city = {
                    'id': city.get('id'),
                    'name': city.get('name'),
                    'infrastructure': city.get('infrastructure'),
                    'land': city.get('land'),
                    'powered': bool(city.get('powered')),
                    'date': city.get('date'),
                    
                    # Revenue calculation expects improvement counts as direct properties
                    'coal_power': city.get('coal_power', 0),
                    'oil_power': city.get('oil_power', 0),
                    'nuclear_power': city.get('nuclear_power', 0),
                    'wind_power': city.get('wind_power', 0),
                    'coal_mine': city.get('coal_mine', 0),
                    'oil_well': city.get('oil_well', 0),
                    'uranium_mine': city.get('uranium_mine', 0),
                    'lead_mine': city.get('lead_mine', 0),
                    'iron_mine': city.get('iron_mine', 0),
                    'bauxite_mine': city.get('bauxite_mine', 0),
                    'oil_refinery': city.get('oil_refinery', 0),
                    'aluminum_refinery': city.get('aluminum_refinery', 0),
                    'steel_mill': city.get('steel_mill', 0),
                    'munitions_factory': city.get('munitions_factory', 0),
                    'factory': city.get('factory', 0),
                    'farm': city.get('farm', 0),
                    'police_station': city.get('police_station', 0),
                    'hospital': city.get('hospital', 0),
                    'recycling_center': city.get('recycling_center', 0),
                    'subway': city.get('subway', 0),
                    'supermarket': city.get('supermarket', 0),
                    'bank': city.get('bank', 0),
                    'shopping_mall': city.get('shopping_mall', 0),
                    'stadium': city.get('stadium', 0),
                    'barracks': city.get('barracks', 0),
                    'hangar': city.get('hangar', 0),
                    'drydock': city.get('drydock', 0),
                }
                
                transformed_cities.append(transformed_city)
            
            # Add transformed cities to nation data
            nation_data['cities'] = transformed_cities
            return nation_data
            
        except Exception as e:
            logger.error(f"Failed to get cached city data for nation {nation_id}: {e}")
            return None
    
    def _get_zero_revenue(self) -> Dict[str, float]:
        """Return zero revenue structure."""
        return {
            "total": 0.0,
            "net_income": 0.0,
            "city_revenue": 0.0,
            "resource_revenue": 0.0,
            "tax_rate": 0.15,
            "resources": {r: 0.0 for r in ["coal", "oil", "uranium", "iron", "bauxite", "lead", 
                                           "gasoline", "munitions", "steel", "aluminum", "food"]},
            "gross_income": 0.0,
        }
    
    def _calculate_simplified_revenue(self, nation_data: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate simplified turn revenue based on available nation data.
        
        This is a fallback when detailed city data is not available.
        """
        # Basic revenue calculation based on cities and nation score
        num_cities = int(nation_data.get("num_cities") or 0)
        score = float(nation_data.get("score") or 0)
        
        # Simplified revenue: base amount per city + score-based bonus
        # This is much more reasonable than the GNI-based calculation
        base_city_revenue = 15000  # $15,000 per city per turn (reasonable estimate)
        score_bonus = score * 0.5   # $0.50 per score point per turn
        
        total_revenue = (base_city_revenue * num_cities) + score_bonus
        
        # Apply basic tax (assuming 15% average)
        net_revenue = total_revenue * 0.85
        
        # Small resource production based on city count
        resource_production = {
            "coal": num_cities * 5.0,
            "oil": num_cities * 3.0,
            "uranium": num_cities * 0.1,
            "iron": num_cities * 4.0,
            "bauxite": num_cities * 3.5,
            "lead": num_cities * 2.5,
            "gasoline": num_cities * 1.0,
            "munitions": num_cities * 2.0,
            "steel": num_cities * 4.0,
            "aluminum": num_cities * 3.0,
            "food": num_cities * 10.0,
        }
        
        return {
            "total": net_revenue,
            "net_income": net_revenue,
            "city_revenue": base_city_revenue * num_cities,
            "resource_revenue": sum(resource_production.values()),
            "tax_rate": 0.15,
            "resources": resource_production,
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
                resource_deltas=revenue.get("resources", {
                    "coal": 0.0, "oil": 0.0, "uranium": 0.0, "iron": 0.0, "bauxite": 0.0, "lead": 0.0,
                    "gasoline": 0.0, "munitions": 0.0, "steel": 0.0, "aluminum": 0.0, "food": 0.0,
                }),
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
        reaper_db_path=None,
        nation_cache=None,
    ):
        """
        Initialize the RevenueComponent.
        
        Args:
            global_nations_db: GlobalNationsDB instance
            irs_wars_db: IRSWarsDB instance
            holdings_db: HoldingsDB instance (optional)
            beige_component: BeigeAlertComponent instance (optional)
            interval_seconds: Revenue processing interval (default: 2 hours)
            reaper_db_path: Path to reaper.db for colors/radiation data (optional)
            nation_cache: NationCache instance for fast nation/city data access (optional)
        """
        self.global_nations_db = global_nations_db
        self.irs_wars_db = irs_wars_db
        self.holdings_db = holdings_db
        self.beige_component = beige_component
        self.interval_seconds = interval_seconds
        self.nation_cache = nation_cache
        self.running = False
        self._task: Optional[asyncio.Task] = None
        
        # Sub-components
        self.revenue_processor = RevenueProcessor(global_nations_db, irs_wars_db, holdings_db, reaper_db_path)
        self.beige_updater = BeigeAlertUpdater(global_nations_db, beige_component)
    
    async def initialize(self):
        """Initialize the component."""
        await self.revenue_processor.initialize()
        logger.info("RevenueComponent initialized")
    
    async def process_turn_revenue_batch(self):
        """Process turn revenue and beige alert updates for the current turn.
        
        Revenue is applied only if holdings_db is available.
        Beige alerts are updated only for nations that actually have alerts,
        not for all ~40k nations in GlobalNations.db.
        """
        if not self.global_nations_db:
            return
        
        try:
            # ── Get game context loaded once during initialization ───────────────
            # Use the colors and radiation data loaded once during initialize()
            colors_data = self.revenue_processor.get_colors_data()
            radiation_data = self.revenue_processor.get_radiation_data()
            
            # ── Load color bonuses (hardcoded to prevent DB calls) ─────────────
            # Color bonuses are static: beige 0%, green 1%, gray 2%, orange 3%, red 4%, purple 5%
            color_bonuses = {
                'beige': 0.0,
                'green': 0.01,
                'gray': 0.02,
                'orange': 0.03,
                'red': 0.04,
                'purple': 0.05,
            }
            
            # ── Load active war IDs once for all nations ───────────────────────
            active_war_ids = None
            if self.irs_wars_db:
                try:
                    active_war_ids = await self.irs_wars_db.get_active_war_nation_ids()
                except Exception as e:
                    logger.warning(f"Could not load active war IDs: {e}")
            
            # ── Revenue application for holdings ──────────────────────────────
            if self.holdings_db:
                try:
                    # Get all nations that have holdings (tracked nations)
                    tracked_nations = await self.holdings_db.get_all_tracked_nation_ids()
                    if tracked_nations:
                        revenue_processed = 0
                        total_nations = len(tracked_nations)
                        start_time = datetime.now(timezone.utc)
                        logger.info(f"Starting revenue processing for {total_nations} tracked nations...")
                        
                        # Use cache if available, otherwise pre-load data
                        if self.nation_cache and self.nation_cache.is_loaded():
                            logger.info("Using nation cache for fast data access")
                            # Calculate revenue for all nations using cache
                            logger.info("Calculating revenue for all nations (from cache)...")
                            revenue_updates = []
                            for nation_id in tracked_nations:
                                try:
                                    # Get nation with cities from cache
                                    nation = self.nation_cache.get_nation_with_cities(nation_id)
                                    if not nation:
                                        continue
                                    
                                    # Calculate revenue using simplified calculation
                                    revenue = await self.revenue_processor.calculate_turn_revenue(nation_data=nation)
                                    revenue_updates.append((nation_id, revenue))
                                    revenue_processed += 1
                                    
                                except Exception as e:
                                    logger.warning(f"Revenue calculation failed for nation {nation_id}: {e}")
                        else:
                            logger.info("Cache not available, pre-loading data...")
                            # Pre-load all nation data in bulk to reduce DB calls
                            all_nations = {}
                            for nation_id in tracked_nations:
                                nation = await self.global_nations_db.get_nation(nation_id)
                                if nation:
                                    all_nations[nation_id] = nation
                            
                            # Pre-load all cities in bulk to reduce DB calls
                            all_cities = {}
                            for nation_id in tracked_nations:
                                cities = await self.global_nations_db.get_cities_for_nation(nation_id)
                                all_cities[nation_id] = cities
                            
                            # Calculate revenue for all nations (CPU-bound, no DB calls)
                            logger.info("Calculating revenue for all nations...")
                            revenue_updates = []
                            for nation_id in tracked_nations:
                                try:
                                    nation = all_nations.get(nation_id)
                                    if not nation:
                                        continue
                                    
                                    nation['cities'] = all_cities.get(nation_id, [])
                                    
                                    # Calculate revenue using simplified calculation
                                    revenue = await self.revenue_processor.calculate_turn_revenue(nation_data=nation)
                                    revenue_updates.append((nation_id, revenue))
                                    revenue_processed += 1
                                    
                                except Exception as e:
                                    logger.warning(f"Revenue calculation failed for nation {nation_id}: {e}")
                        
                        # Apply all revenue updates in batch
                        logger.info(f"Applying {len(revenue_updates)} revenue updates...")
                        for nation_id, revenue in revenue_updates:
                            try:
                                await self.revenue_processor.apply_turn_revenue(nation_id, revenue)
                            except Exception as e:
                                logger.warning(f"Revenue application failed for nation {nation_id}: {e}")
                        
                        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                        logger.info(f"Turn: revenue applied to {revenue_processed}/{total_nations} tracked nations in {elapsed:.1f}s")
                        
                except Exception as e:
                    logger.error(f"Failed to apply revenue to holdings: {e}", exc_info=True)
            
            # ── Beige alert updates ──────────────────────────────────────────
            # Fetch only the nation IDs that have active beige alerts, then
            # load those nations individually — avoids scanning all nations.
            try:
                from Systems.Functions.beige_alerts_db import get_all_beige_alerts
                all_alerts = await get_all_beige_alerts()
            except Exception as e:
                logger.warning(f"Could not fetch beige alerts for turn processing: {e}")
                all_alerts = []
            
            alerted_nation_ids: set = {int(a["nation_id"]) for a in all_alerts if a.get("nation_id")}
            
            beige_processed = 0
            for nation_id in alerted_nation_ids:
                try:
                    nation = await self.global_nations_db.get_nation(nation_id)
                    if not nation:
                        continue
                    await self.beige_updater.update_beige_alerts(nation_id, nation)
                    beige_processed += 1
                except Exception as e:
                    logger.warning(f"Beige alert update failed for nation {nation_id}: {e}")
            
            if alerted_nation_ids:
                logger.info(f"Turn: beige alerts updated for {beige_processed}/{len(alerted_nation_ids)} alerted nations")
            
        except Exception as e:
            logger.error(f"Failed to process turn revenue: {e}", exc_info=True)
    
    async def start(self):
        """Start the revenue processing loop.
        
        NOTE: GPPManager calls _run_loop() directly after setting running=True.
        This method is kept for standalone use only.
        """
        if self.running:
            logger.warning("RevenueComponent already running")
            return
        
        self.running = True
        self._task = asyncio.create_task(self._revenue_loop(), name="revenue_loop")
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
    
    def _seconds_until_next_turn(self) -> float:
        """Return seconds until the next PnW game turn boundary.
        
        PnW turns roll every 2 real hours at :00 UTC (00:00, 02:00, 04:00, …).
        We wait until 30 seconds *after* the boundary to let nation subscription
        events propagate before we read beige_turns from the DB.
        """
        now = datetime.now(timezone.utc)
        # How far through the current 2-hour block are we (in seconds)?
        seconds_into_block = (now.hour % 2) * 3600 + now.minute * 60 + now.second
        seconds_until_boundary = self.interval_seconds - seconds_into_block
        # Add 30s buffer so nation/update events have time to arrive and be saved
        return seconds_until_boundary + 30.0

    async def _run_loop(self):
        """Revenue processing loop — fires once per PnW game turn (every 2 real hours).
        
        Aligns to actual turn boundaries (:00 UTC on even hours) with a 30-second
        buffer, then waits for the next boundary after processing.
        
        NOTE: This is aliased as _run_loop() for GPPManager compatibility.
        """
        # On first start, sleep until the next turn boundary rather than firing
        # immediately (which would process a half-turn worth of stale data).
        initial_wait = self._seconds_until_next_turn()
        logger.info(f"RevenueComponent: first turn in {initial_wait:.0f}s")
        try:
            await asyncio.sleep(initial_wait)
        except asyncio.CancelledError:
            return
        
        while self.running:
            try:
                await self.process_turn_revenue_batch()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Revenue loop error: {e}", exc_info=True)
            
            if not self.running:
                break
            
            # Sleep until the next 2-hour boundary (recalculated after processing)
            wait = self._seconds_until_next_turn()
            logger.debug(f"RevenueComponent: next turn in {wait:.0f}s")
            try:
                await asyncio.sleep(wait)
            except asyncio.CancelledError:
                break

    # Alias for backward compatibility
    _revenue_loop = _run_loop
    
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

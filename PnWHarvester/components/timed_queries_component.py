"""
TimedQueriesComponent — GPP component for periodic data fetching.

Handles:
- Resource price tracking (every 15 minutes)
- Game data tracking (colors, game_date, city_average, radiation)
- Completed trade tracking (every 15 minutes)
- Trade news generation

This component writes to HoldingsDB and generates news.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from PnWHarvester.core.activity_tracker import ActivityTracker
from PnWHarvester.components.trade_utils import (
    normalize_trade_event,
    normalized_trade_to_news_payload,
)

logger = logging.getLogger(__name__)

RESOURCES = [
    "food", "coal", "oil", "uranium", "lead", "iron", "bauxite",
    "gasoline", "munitions", "steel", "aluminum", "credit"
]


def _obj_to_dict(obj: Any) -> Dict[str, Any]:
    """Convert objects to dictionaries safely."""
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return dict(obj)
    return vars(obj)


class TimedQueriesProcessor:
    """Processes timed query data."""
    
    def __init__(self, query_instance, holdings_db=None, news_component=None):
        """
        Initialize the timed queries processor.
        
        Args:
            query_instance: Query instance for API calls
            holdings_db: HoldingsDB instance (optional)
            news_component: NewsComponent instance (optional)
        """
        self.query = query_instance
        self.holdings_db = holdings_db
        self.news_component = news_component
        self._last_trade_id = 0  # Track last processed trade to avoid duplicates
    
    async def fetch_game_data(self) -> Optional[Dict[str, Any]]:
        """
        Fetch colors, game_info, radiation from API.
        
        Returns:
            Dictionary with game data or None if failed
        """
        try:
            # Fetch game data using the query instance
            # This reuses the existing logic from Systems/PnW/timed_queries.py
            # but adapted to work without Discord dependency
            
            # For now, we'll use the database_manager functions directly
            # since they're already working
            import Systems.Functions.database_manager as db_manager
            
            # Fetch master data from API
            master_data = await self.query.get_master_update_data()
            
            if not master_data:
                logger.error("Game data fetch failed: No data received from API")
                return None
            
            timestamp = int(time.time())
            
            # Process and save game data (colors)
            colors_info = master_data.get('colors')
            if colors_info:
                await db_manager.add_game_data("colors", timestamp, colors_info)
                logger.info("Successfully saved color data")
            
            # Process and save game_info (game_date, city_average, radiation)
            game_info = master_data.get('gameInfo')
            if game_info:
                game_date_str = game_info.get('game_date') or ''
                city_average = float(game_info.get('city_average') or 0.0)
                await db_manager.add_game_info(timestamp, game_date_str, city_average)
                logger.info(f"Successfully saved game_info (game_date={game_date_str}, city_average={city_average})")
                
                # Save radiation data if available
                radiation_info = game_info.get('radiation')
                if radiation_info:
                    await db_manager.add_radiation_data(timestamp, radiation_info)
                    logger.info("Successfully saved radiation data")
                else:
                    logger.warning("No radiation data found in game_info response")
            
            return master_data
            
        except Exception as e:
            logger.error(f"Failed to fetch game data: {e}", exc_info=True)
            return None
    
    async def fetch_resource_prices(self, master_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Fetch resource prices from API.
        
        Args:
            master_data: Pre-fetched master data (optional)
            
        Returns:
            Dictionary with resource prices or None if failed
        """
        try:
            import Systems.Functions.database_manager as db_manager
            
            if not master_data:
                master_data = await self.query.get_master_update_data()
                if not master_data:
                    logger.error("Resource prices fetch failed: No data received from API")
                    return None
            
            timestamp = int(time.time())
            
            # Process and save resource data (best sell, best buy, and average prices)
            trade_info = master_data.get('tradeInfo')
            if trade_info:
                resource_list = trade_info.get('resources', [])
                if resource_list:
                    resource_data = {}
                    found_resources = []
                    for item in resource_list:
                        if item.get('resource') and item['resource'].upper() in [r.upper() for r in RESOURCES]:
                            resource_name = item['resource'].lower()
                            best_sell = float((item.get('best_sell_offer') or {}).get('price', 0))
                            best_buy = float((item.get('best_buy_offer') or {}).get('price', 0))
                            
                            avg_price = (best_buy + best_sell) / 2 if (best_buy > 0 and best_sell > 0) else (best_buy or best_sell)

                            resource_data[resource_name] = {
                                'best_sell': best_sell,
                                'best_buy': best_buy,
                                'avg': avg_price
                            }
                            found_resources.append(resource_name)
                    
                    logger.info(f"Fetched resources from API: {found_resources}")
                    
                    if len(resource_data) < len(RESOURCES):
                        missing_resources = [res for res in [r.lower() for r in RESOURCES] if res not in resource_data]
                        logger.warning(f"API data is incomplete. Fetched {len(resource_data)}/{len(RESOURCES)} resources. Missing: {missing_resources}")
                    
                    await db_manager.add_resource_data(timestamp, resource_data)
                    logger.info("Successfully saved resource price data (best sell, best buy, average)")
                    
                    return resource_data
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to fetch resource prices: {e}", exc_info=True)
            return None
    
    async def fetch_completed_trades(self, minutes_back: int = 15) -> List[Dict[str, Any]]:
        """
        Fetch completed trades from the last N minutes.
        
        Args:
            minutes_back: How many minutes back to query
            
        Returns:
            List of completed trade dictionaries
        """
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes_back)
            cutoff_timestamp = int(cutoff.timestamp())
            filtered_trades = []
            all_seen = 0
            page = 1
            max_pages = 20
            reached_cutoff = False

            while page <= max_pages and not reached_cutoff:
                gql = f"""
                query {{
                  trades(
                    first: 500
                    page: {page}
                    accepted: true
                    orderBy: {{ column: ID, order: DESC }}
                  ) {{
                    paginatorInfo {{ hasMorePages currentPage lastPage total }}
                    data {{
                      id
                      date
                      sender_id
                      receiver_id
                      offer_resource
                      offer_amount
                      buy_or_sell
                      price
                      accepted
                      date_accepted
                      sender {{
                        id
                        nation_name
                        flag
                        alliance {{ id name flag }}
                      }}
                      receiver {{
                        id
                        nation_name
                        flag
                        alliance {{ id name flag }}
                      }}
                    }}
                  }}
                }}
                """

                raw = await self.query._make_graphql_request(gql, timeout=60)
                block = (raw or {}).get("trades") or {}
                page_trades = block.get("data") or []
                all_seen += len(page_trades)

                for trade in page_trades:
                    date_accepted = trade.get("date_accepted")
                    if not date_accepted:
                        continue
                    from datetime import datetime as dt
                    try:
                        accepted_dt = dt.fromisoformat(str(date_accepted).replace("Z", "+00:00"))
                        if accepted_dt.tzinfo is None:
                            accepted_dt = accepted_dt.replace(tzinfo=timezone.utc)
                        accepted_timestamp = int(accepted_dt.timestamp())
                    except (ValueError, AttributeError):
                        continue

                    if accepted_timestamp >= cutoff_timestamp:
                        filtered_trades.append(trade)
                    else:
                        reached_cutoff = True

                paginator = block.get("paginatorInfo") or {}
                if not paginator.get("hasMorePages"):
                    break
                page += 1
            
            logger.info(
                f"Fetched {len(filtered_trades)} completed trades accepted in the last "
                f"{minutes_back} minutes (scanned {all_seen} accepted trades across {page} page(s))"
            )
            return filtered_trades
            
        except Exception as e:
            logger.error(f"Failed to fetch completed trades: {e}", exc_info=True)
            return []
    
    async def _convert_trade_for_news(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert GraphQL trade data to TradeNewsGenerator format.
        
        Args:
            trade: Trade data from GraphQL query
            
        Returns:
            Trade data in format expected by TradeNewsGenerator
        """
        normalized = normalize_trade_event(trade)
        if not normalized:
            raise ValueError(f"Unable to normalize trade {trade.get('id')}")
        return normalized_trade_to_news_payload(normalized)
    
    async def _process_trade_holdings(self, trade: Dict[str, Any]) -> bool:
        """
        Update holdings database for a completed trade.
        
        Args:
            trade: Trade dictionary from GraphQL query
        """
        if not self.holdings_db:
            return False
        
        try:
            normalized = normalize_trade_event(trade)
            if not normalized or not normalized.get("completed"):
                logger.debug(f"Trade {trade.get('id')} is not a completed trade, skipping holdings update")
                return False

            buyer = normalized.get("buyer") or {}
            seller = normalized.get("seller") or {}
            return await self.holdings_db.apply_trade_completion(
                buyer_id=int(normalized["buyer_id"]),
                seller_id=int(normalized["seller_id"]),
                money_amount=float(normalized.get("money_amount") or 0),
                resources=normalized.get("resources_traded") or {},
                trade_date=normalized.get("date_accepted") or normalized.get("date"),
                buyer_name=buyer.get("name"),
                seller_name=seller.get("name"),
            )
            
        except Exception as e:
            logger.error(f"Failed to process trade holdings for trade {trade.get('id')}: {e}", exc_info=True)
            return False
    
    async def _generate_trade_news(self, trades: List[Dict[str, Any]]):
        """
        Generate news events for completed trades and update holdings.
        
        Args:
            trades: List of trade dictionaries from GraphQL query
        """
        if not trades:
            logger.debug("No trades to generate news for")
            return
        
        generator = None
        if self.news_component:
            from PnWHarvester.subscriptions.trade_news_components import TradeNewsGenerator
            generator = TradeNewsGenerator(self.news_component)
        else:
            logger.debug("No news component available; timed trades will update holdings only")
        
        generated_count = 0
        holdings_updated = 0
        for trade in sorted(trades, key=lambda t: int(t.get("id") or 0)):
            try:
                trade_id = trade.get("id")
                if not trade_id:
                    continue
                    
                trade_id_int = int(trade_id)
                
                normalized = normalize_trade_event(trade)
                if not normalized or not normalized.get("completed"):
                    logger.debug(f"Trade {trade_id} is not a valid completed trade, skipping")
                    continue

                legacy_processed = False
                if self.holdings_db and hasattr(self.holdings_db, "is_processed_event"):
                    legacy_processed = await self.holdings_db.is_processed_event(
                        "trade_completed", trade_id_int
                    )

                if not legacy_processed and self.holdings_db:
                    holdings_claimed = True
                    if hasattr(self.holdings_db, "claim_processed_event"):
                        holdings_claimed = await self.holdings_db.claim_processed_event(
                            "trade_holdings_applied", trade_id_int
                        )
                    if holdings_claimed:
                        if await self._process_trade_holdings(trade):
                            holdings_updated += 1
                        elif hasattr(self.holdings_db, "unclaim_processed_event"):
                            await self.holdings_db.unclaim_processed_event(
                                "trade_holdings_applied", trade_id_int
                            )
                    else:
                        logger.debug(f"Trade {trade_id} holdings already processed, skipping holdings")
                elif legacy_processed:
                    logger.debug(f"Trade {trade_id} has legacy trade_completed claim, skipping holdings")

                if not generator:
                    if trade_id_int > self._last_trade_id:
                        self._last_trade_id = trade_id_int
                    continue

                news_claimed = True
                if self.holdings_db and hasattr(self.holdings_db, "claim_processed_event"):
                    news_claimed = await self.holdings_db.claim_processed_event(
                        "trade_news_generated", trade_id_int
                    )
                if not news_claimed:
                    if trade_id_int > self._last_trade_id:
                        self._last_trade_id = trade_id_int
                    logger.debug(f"Trade {trade_id} news already generated, skipping news")
                    continue

                trade_dict = await self._convert_trade_for_news(trade)
                result = await generator.generate_trade_completed_news(trade_dict)
                if not result.get("generated") and self.holdings_db and hasattr(self.holdings_db, "unclaim_processed_event"):
                    await self.holdings_db.unclaim_processed_event(
                        "trade_news_generated", trade_id_int
                    )

                if result.get("generated"):
                    if trade_id_int > self._last_trade_id:
                        self._last_trade_id = trade_id_int
                    generated_count += 1
                    logger.info(f"Trade news generated for trade {trade_id}")
                    
            except Exception as e:
                logger.error(f"Failed to generate trade news for trade {trade.get('id')}: {e}", exc_info=True)
        
        logger.info(f"Generated {generated_count} trade news events from {len(trades)} trades, updated {holdings_updated} holdings")


class TimedQueriesComponent:
    """
    GPP component for timed queries.
    
    Orchestrates periodic data fetching including:
    - Game data (colors, game_date, city_average, radiation)
    - Resource prices
    - Completed trades
    - Trade news generation
    """
    
    def __init__(
        self,
        query_instance,
        holdings_db=None,
        news_component=None,
        interval_seconds: int = 900,  # 15 minutes
    ):
        """
        Initialize the TimedQueriesComponent.
        
        Args:
            query_instance: Query instance for API calls
            holdings_db: HoldingsDB instance (optional)
            news_component: NewsComponent instance (optional)
            interval_seconds: Update interval in seconds (default: 900 = 15 minutes)
        """
        self.query = query_instance
        self.holdings_db = holdings_db
        self.news_component = news_component
        self.interval_seconds = interval_seconds
        
        # Sub-component
        self.processor = TimedQueriesProcessor(query_instance, holdings_db, news_component)
        
        # Activity tracking for health monitoring
        self.activity_tracker = ActivityTracker(max_silence_seconds=3600.0)  # 60 minutes (4x interval)
        
        # Subscription state
        self.running = False
        self._task = None
    
    async def initialize(self):
        """Initialize the component."""
        # Register subscription for activity tracking
        self.activity_tracker.register_subscription("timed_queries/update")
        logger.info("TimedQueriesComponent initialized")
        logger.info(f"TimedQueriesComponent config: holdings_db={self.holdings_db is not None}, news_component={self.news_component is not None}, interval_seconds={self.interval_seconds}")
    
    async def get_component_stats(self) -> Dict[str, Any]:
        """Get component statistics."""
        return {
            "type": "TimedQueriesComponent",
            "holdings_db_path": self.holdings_db.db_path if self.holdings_db else None,
            "running": self.running,
            "interval_seconds": self.interval_seconds,
            "last_trade_id": self.processor._last_trade_id,
            "activity": self.activity_tracker.to_dict(),
        }
    
    async def start(self):
        """Start the background loop.
        
        NOTE: GPPManager calls _run_loop() directly after setting running=True.
        This method is kept for standalone use only.
        """
        if self.running:
            logger.warning("TimedQueriesComponent already running")
            return
        
        self.running = True
        logger.info("Starting TimedQueriesComponent")
        
        self._task = asyncio.create_task(self._run_loop(), name="timed_queries_loop")
    
    async def stop(self):
        """Stop the background loop."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("TimedQueriesComponent stopped")
    
    async def _run_loop(self):
        """Main loop - runs indefinitely until stopped."""
        logger.info("TimedQueriesComponent main loop starting")
        
        while self.running:
            try:
                await self._process_update()
                
                # Check if we should continue before sleeping
                if not self.running:
                    logger.info("TimedQueriesComponent stopping after update cycle")
                    break
                    
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                logger.info("TimedQueriesComponent loop cancelled")
                break
            except Exception as e:
                logger.error(f"TimedQueriesComponent loop error: {e}", exc_info=True)
                await asyncio.sleep(30)  # Wait before retry
        
        logger.warning("TimedQueriesComponent main loop exited (self.running=False or cancelled)")
    
    async def _process_update(self):
        """Process one update cycle."""
        logger.info("TimedQueriesComponent: Starting update cycle")
        
        try:
            # Record activity for health monitoring
            self.activity_tracker.record_message("timed_queries/update")
            
            # Fetch game data and resource prices
            master_data = await self.processor.fetch_game_data()
            
            # Fetch resource prices (uses master_data if available)
            await self.processor.fetch_resource_prices(master_data)
            
            # Fetch completed trades
            trades = await self.processor.fetch_completed_trades(minutes_back=self.interval_seconds // 60)
            
            # Generate trade news
            await self.processor._generate_trade_news(trades)
            
            logger.info("TimedQueriesComponent: Update cycle complete")
            
        except Exception as e:
            self.activity_tracker.record_error("timed_queries/update")
            logger.error(f"TimedQueriesComponent update cycle failed: {e}", exc_info=True)
    
    async def run_forever(self):
        """Run the component indefinitely with auto-restart.
        
        NOTE: GPPManager calls _run_loop() directly. This method exists only for
        standalone use; _run_loop() already handles errors internally.
        """
        while True:
            try:
                if not self.running:
                    self.running = True
                await self._run_loop()
            except asyncio.CancelledError:
                logger.info("TimedQueriesComponent cancelled")
                break
            except Exception as e:
                logger.error(f"TimedQueriesComponent crashed ({e}) — restarting in 30s", exc_info=True)
            finally:
                self.running = False
            
            await asyncio.sleep(30)

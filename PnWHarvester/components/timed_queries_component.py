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
            after_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
            
            # Use date_accepted filter to only get trades accepted in the last N minutes
            # This ensures we don't re-process old trades on restart
            gql = f"""
            query {{
              trades(
                first: 100
                accepted: true
              ) {{
                data {{
                  id
                  date
                  sender_id
                  receiver_id
                  offer_resource
                  offer_amount
                  buy_or_sell
                  price
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
            all_trades = block.get("data") or []
            
            # Filter to only trades accepted in the last N minutes
            cutoff_timestamp = int(cutoff.timestamp())
            filtered_trades = []
            for trade in all_trades:
                date_accepted = trade.get("date_accepted")
                if date_accepted:
                    # Parse ISO format datetime
                    from datetime import datetime as dt
                    try:
                        accepted_dt = dt.fromisoformat(date_accepted.replace('Z', '+00:00'))
                        accepted_timestamp = int(accepted_dt.timestamp())
                        if accepted_timestamp >= cutoff_timestamp:
                            filtered_trades.append(trade)
                    except (ValueError, AttributeError):
                        # If we can't parse the date, skip this trade
                        continue
            
            logger.info(f"Fetched {len(filtered_trades)} completed trades accepted in the last {minutes_back} minutes (from {len(all_trades)} total)")
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
        # Extract basic trade info
        trade_id = trade.get("id")
        date_str = trade.get("date")
        date_accepted_str = trade.get("date_accepted")
        offer_resource = trade.get("offer_resource")
        offer_amount = trade.get("offer_amount")
        buy_or_sell = trade.get("buy_or_sell")
        price = trade.get("price")
        
        # Extract sender (poster) info
        sender = trade.get("sender") or {}
        sender_id = sender.get("id")
        sender_name = sender.get("nation_name")
        sender_flag = sender.get("flag")
        sender_alliance = sender.get("alliance") or {}
        sender_alliance_id = sender_alliance.get("id")
        sender_alliance_name = sender_alliance.get("name")
        sender_alliance_flag = sender_alliance.get("flag")
        
        # Extract receiver (buyer) info
        receiver = trade.get("receiver") or {}
        receiver_id = receiver.get("id")
        receiver_name = receiver.get("nation_name")
        receiver_flag = receiver.get("flag")
        receiver_alliance = receiver.get("alliance") or {}
        receiver_alliance_id = receiver_alliance.get("id")
        receiver_alliance_name = receiver_alliance.get("name")
        receiver_alliance_flag = receiver_alliance.get("flag")
        
        # Determine direction and construct trade dict
        # In the API, sender is always the poster, receiver is the buyer
        # buy_or_sell indicates what the poster is doing
        
        if buy_or_sell == "sell":
            # Poster is selling, receiver is buying
            seller_id = sender_id
            seller_name = sender_name
            seller_flag = sender_flag
            seller_alliance_id = sender_alliance_id
            seller_alliance_name = sender_alliance_name
            seller_alliance_flag = sender_alliance_flag
            
            buyer_id = receiver_id
            buyer_name = receiver_name
            buyer_flag = receiver_flag
            buyer_alliance_id = receiver_alliance_id
            buyer_alliance_name = receiver_alliance_name
            buyer_alliance_flag = receiver_alliance_flag
        else:
            # Poster is buying, receiver is selling
            buyer_id = sender_id
            buyer_name = sender_name
            buyer_flag = sender_flag
            buyer_alliance_id = sender_alliance_id
            buyer_alliance_name = sender_alliance_name
            buyer_alliance_flag = sender_alliance_flag
            
            seller_id = receiver_id
            seller_name = receiver_name
            seller_flag = receiver_flag
            seller_alliance_id = receiver_alliance_id
            seller_alliance_name = receiver_alliance_name
            seller_alliance_flag = receiver_alliance_flag
        
        # Calculate money amount
        money_amount = float(offer_amount or 0) * float(price or 0)
        
        # Build resource dict
        resources_traded = {r: 0.0 for r in RESOURCES}
        if offer_resource:
            resources_traded[offer_resource.lower()] = float(offer_amount or 0)
        
        # Calculate price per unit
        total_resources = sum(resources_traded.values())
        price_per_unit = money_amount / total_resources if total_resources > 0 else 0
        
        # Construct trade dict in TradeNewsGenerator format
        # TradeNewsGenerator expects:
        # - For buying trades: nation is the buyer, seller_nation is the seller
        # - For selling trades: nation is the seller, buyer_nation is the buyer
        
        if buy_or_sell == "buy":
            # Poster is buying: nation is buyer, seller_nation is seller
            trade_dict = {
                "id": trade_id,
                "date": date_str,
                "accept_date": date_accepted_str,
                "buying": True,
                "selling": False,
                "money": money_amount,
                "nation": {
                    "id": buyer_id,
                    "nation_name": buyer_name,
                    "flag": buyer_flag,
                    "alliance": {
                        "id": buyer_alliance_id,
                        "name": buyer_alliance_name,
                        "flag": buyer_alliance_flag,
                    } if buyer_alliance_id else None,
                },
                "seller_nation": {
                    "id": seller_id,
                    "nation_name": seller_name,
                    "flag": seller_flag,
                    "alliance": {
                        "id": seller_alliance_id,
                        "name": seller_alliance_name,
                        "flag": seller_alliance_flag,
                    } if seller_alliance_id else None,
                },
            }
        else:
            # Poster is selling: nation is seller, buyer_nation is buyer
            trade_dict = {
                "id": trade_id,
                "date": date_str,
                "accept_date": date_accepted_str,
                "buying": False,
                "selling": True,
                "money": money_amount,
                "nation": {
                    "id": seller_id,
                    "nation_name": seller_name,
                    "flag": seller_flag,
                    "alliance": {
                        "id": seller_alliance_id,
                        "name": seller_alliance_name,
                        "flag": seller_alliance_flag,
                    } if seller_alliance_id else None,
                },
                "buyer_nation": {
                    "id": buyer_id,
                    "nation_name": buyer_name,
                    "flag": buyer_flag,
                    "alliance": {
                        "id": buyer_alliance_id,
                        "name": buyer_alliance_name,
                        "flag": buyer_alliance_flag,
                    } if buyer_alliance_id else None,
                },
            }
        
        # Add resource fields
        for r in RESOURCES:
            trade_dict[r] = resources_traded[r]
        
        return trade_dict
    
    async def _generate_trade_news(self, trades: List[Dict[str, Any]]):
        """
        Generate news events for completed trades.
        
        Args:
            trades: List of trade dictionaries from GraphQL query
        """
        if not self.news_component:
            logger.debug("No news component available, skipping trade news generation")
            return
        
        if not trades:
            logger.debug("No trades to generate news for")
            return
        
        from PnWHarvester.subscriptions.trade_news_components import TradeNewsGenerator
        generator = TradeNewsGenerator(self.news_component)
        
        generated_count = 0
        for trade in trades:
            try:
                # Skip trades we've already processed
                trade_id = trade.get("id")
                if not trade_id:
                    continue
                    
                trade_id_int = int(trade_id)
                
                # Always update last trade ID to highest seen BEFORE filtering
                # This ensures we don't skip trades in the same batch
                if trade_id_int > self._last_trade_id:
                    self._last_trade_id = trade_id_int
                
                # Now check if we've already processed this trade
                # Use a small buffer (1000) to handle out-of-order trades
                if trade_id_int <= self._last_trade_id - 1000:
                    continue
                
                # Convert trade data to format expected by TradeNewsGenerator
                trade_dict = await self._convert_trade_for_news(trade)
                result = await generator.generate_trade_completed_news(trade_dict)
                
                if result.get("generated"):
                    generated_count += 1
                    logger.info(f"Trade news generated for trade {trade_id}")
                    
            except Exception as e:
                logger.error(f"Failed to generate trade news for trade {trade.get('id')}: {e}", exc_info=True)
        
        logger.info(f"Generated {generated_count} trade news events from {len(trades)} trades")


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
        
        # Subscription state
        self.running = False
        self._task = None
    
    async def initialize(self):
        """Initialize the component."""
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
        }
    
    async def start(self):
        """Start the background loop."""
        if self.running:
            logger.warning("TimedQueriesComponent already running")
            return
        
        self.running = True
        logger.info("Starting TimedQueriesComponent")
        
        self._task = asyncio.create_task(self._run_loop())
    
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
        """Main loop."""
        while self.running:
            try:
                await self._process_update()
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                logger.info("TimedQueriesComponent loop cancelled")
                break
            except Exception as e:
                logger.error(f"TimedQueriesComponent loop error: {e}", exc_info=True)
                await asyncio.sleep(30)  # Wait before retry
    
    async def _process_update(self):
        """Process one update cycle."""
        logger.info("TimedQueriesComponent: Starting update cycle")
        
        try:
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
            logger.error(f"TimedQueriesComponent update cycle failed: {e}", exc_info=True)
    
    async def run_forever(self):
        """Run the component indefinitely with auto-restart."""
        while True:
            try:
                await self.start()
                await self._task  # Wait for task to complete
            except asyncio.CancelledError:
                logger.info("TimedQueriesComponent cancelled")
                break
            except Exception as e:
                logger.error(f"TimedQueriesComponent crashed ({e}) — restarting in 30s", exc_info=True)
            finally:
                self.running = False
                await self.stop()
            
            await asyncio.sleep(30)

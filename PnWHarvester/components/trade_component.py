"""
TradeComponent — GPP component for trade event processing.

Sub-components:
- TradeEventProcessor: Handles trade/update events (only completed trades)
- TradeNewsGenerator: Generates news events for completed trades

This component writes to HoldingsDB and generates news for trade completions.
Only processes trades that are actually completed (have accept_date), not when posted.
"""

import asyncio
import logging
from collections import deque
from typing import Any, Dict, Optional

import aiohttp
from pnwkit.new import QueryKit

logger = logging.getLogger(__name__)

_RESOURCES = (
    "coal", "oil", "uranium", "iron", "bauxite", "lead",
    "gasoline", "munitions", "steel", "aluminum", "food",
)


def _obj_to_dict(obj: Any) -> Dict[str, Any]:
    """Convert objects to dictionaries safely."""
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return dict(obj)
    return vars(obj)


class TradeEventProcessor:
    """Processes trade/update events for completed trades only."""
    
    def __init__(self, holdings_db=None, news_component=None):
        """
        Initialize the trade event processor.
        
        Args:
            holdings_db: HoldingsDB instance (optional)
            news_component: NewsComponent instance (optional)
        """
        self.holdings_db = holdings_db
        self.news_component = news_component
        self._processed_ids: deque = deque(maxlen=5000)
    
    def _is_duplicate(self, trade_id: int) -> bool:
        """Check if trade ID was already processed."""
        return trade_id in self._processed_ids
    
    def _mark_processed(self, trade_id: int):
        """Mark trade ID as processed."""
        self._processed_ids.append(trade_id)
    
    def _is_trade_completed(self, trade: Dict[str, Any]) -> bool:
        """
        Check if a trade is actually completed.
        
        With the buy_or_sell=1 subscription filter, we only receive completed trades
        (actual marketplace transactions). We still validate to ensure data integrity.
        
        A trade is completed if:
        - It is not rejected
        - It is not seller_cancelled
        """
        not_rejected = not trade.get("rejected", False)
        not_cancelled = not trade.get("seller_cancelled", False)
        
        # Log why trade is being skipped (should rarely happen with filter)
        if not not_rejected:
            logger.warning(f"Trade {trade.get('id')} skipped: rejected (unexpected with buy_or_sell filter)")
        if not not_cancelled:
            logger.warning(f"Trade {trade.get('id')} skipped: seller_cancelled (unexpected with buy_or_sell filter)")
        
        return not_rejected and not_cancelled
    
    async def process_trade_update(self, event: Any) -> Dict[str, Any]:
        """
        Process a trade/update event.
        
        With the buy_or_sell=1 subscription filter, we only receive completed trades
        (actual marketplace transactions). All received events are processed for
        holdings updates and news generation.
        
        Args:
            event: The pnwkit event object
            
        Returns:
            Processing statistics
        """
        trade = _obj_to_dict(event)
        trade_id = trade.get("id")
        
        if not trade_id:
            return {"processed": 0, "skipped": 1, "reason": "no_id"}
        
        trade_id_int = int(trade_id)
        
        # Check for duplicates
        if self._is_duplicate(trade_id_int):
            logger.debug(f"trade/update → duplicate {trade_id}, skipping")
            return {"processed": 0, "skipped": 1, "duplicate": True}
        
        # Check if trade is completed (should always be true with buy_or_sell filter)
        is_completed = self._is_trade_completed(trade)
        
        if is_completed:
            # Update HoldingsDB for completed trades
            if self.holdings_db:
                await self._update_holdings_for_trade(trade)
            
            # Generate news event for completed trades
            await self._generate_trade_news(trade)
            
            logger.info(f"trade/update → {trade_id} → Holdings updated + News generated")
        else:
            # Should rarely happen with buy_or_sell filter
            logger.warning(f"trade/update → {trade_id} → Skipped (rejected or cancelled)")
        
        self._mark_processed(trade_id_int)
        
        return {"processed": 1, "skipped": 0, "completed": is_completed}
    
    async def _update_holdings_for_trade(self, trade: Dict[str, Any]):
        """Update holdings for a completed trade."""
        try:
            # Determine trade direction
            is_buying = trade.get("buying", False)
            is_selling = trade.get("selling", False)
            
            # Extract nation data
            nation_obj = trade.get("nation") or {}
            if not isinstance(nation_obj, dict):
                nation_obj = {}
            
            nation_id = nation_obj.get("id")
            nation_name = nation_obj.get("nation_name")
            
            if not nation_id:
                logger.warning(f"Trade {trade.get('id')} has no nation_id, skipping holdings update")
                return
            
            # Extract money and resources
            money_amount = float(trade.get("money") or 0)
            resources_traded = {r: float(trade.get(r) or 0) for r in _RESOURCES}
            
            # Get trade date
            trade_date = trade.get("accept_date") or trade.get("date")
            
            if is_buying:
                # Nation is buying - extract seller info
                seller_obj = trade.get("seller_nation") or {}
                if isinstance(seller_obj, dict):
                    seller_id = seller_obj.get("id")
                    seller_name = seller_obj.get("nation_name")
                    
                    if seller_id:
                        await self.holdings_db.apply_trade_completion(
                            buyer_id=int(nation_id),
                            seller_id=int(seller_id),
                            money_amount=money_amount,
                            resources=resources_traded,
                            trade_date=trade_date,
                            buyer_name=nation_name,
                            seller_name=seller_name,
                        )
                else:
                    logger.warning(f"Trade {trade.get('id')} is buying but has no seller_nation")
                    
            elif is_selling:
                # Nation is selling - extract buyer info
                buyer_obj = trade.get("buyer_nation") or {}
                if isinstance(buyer_obj, dict):
                    buyer_id = buyer_obj.get("id")
                    buyer_name = buyer_obj.get("nation_name")
                    
                    if buyer_id:
                        await self.holdings_db.apply_trade_completion(
                            buyer_id=int(buyer_id),
                            seller_id=int(nation_id),
                            money_amount=money_amount,
                            resources=resources_traded,
                            trade_date=trade_date,
                            buyer_name=buyer_name,
                            seller_name=nation_name,
                        )
                else:
                    logger.warning(f"Trade {trade.get('id')} is selling but has no buyer_nation")
            else:
                logger.warning(f"Trade {trade.get('id')} has no buying/selling flag")
                
        except Exception as e:
            logger.error(f"Failed to update holdings for trade {trade.get('id')}: {e}", exc_info=True)
    
    async def _generate_trade_news(self, trade: Dict[str, Any]):
        """Generate news event for completed trade."""
        if self.news_component:
            try:
                from PnWHarvester.subscriptions.trade_news_components import TradeNewsGenerator
                generator = TradeNewsGenerator(self.news_component)
                result = await generator.generate_trade_completed_news(trade)
                logger.info(f"trade/update → {trade.get('id')} → News generation result: {result}")
            except Exception as e:
                logger.error(f"news trade_completed error: {e}", exc_info=True)


class TradeComponent:
    """
    GPP component for trade event processing.
    
    Orchestrates the trade event processor and manages WebSocket subscription
    for trade/update events. Uses buy_or_sell=1 filter to receive only completed
    marketplace transactions (actual buys/sells), not posted offers.
    """
    
    def __init__(
        self,
        holdings_db=None,
        news_component=None,
        api_key: str = "",
    ):
        """
        Initialize the TradeComponent.
        
        Args:
            holdings_db: HoldingsDB instance (optional)
            news_component: NewsComponent instance (optional)
            api_key: PnW API v3 key
        """
        self.holdings_db = holdings_db
        self.news_component = news_component
        self.api_key = api_key
        self.kit = QueryKit(api_key)
        
        # Sub-component
        self.trade_processor = TradeEventProcessor(holdings_db, news_component)
        
        # Subscription state
        self.running = False
        self._tasks: list[asyncio.Task] = []
    
    async def initialize(self):
        """Initialize the component."""
        logger.info("TradeComponent initialized")
        logger.info(f"TradeComponent config: holdings_db={self.holdings_db is not None}, news_component={self.news_component is not None}, api_key={'*' * len(self.api_key) if self.api_key else 'None'}")
    
    async def process_trade_update(self, event: Any) -> Dict[str, Any]:
        """Process a trade/update event."""
        return await self.trade_processor.process_trade_update(event)
    
    async def get_component_stats(self) -> Dict[str, Any]:
        """Get component statistics."""
        return {
            "type": "TradeComponent",
            "holdings_db_path": self.holdings_db.db_path if self.holdings_db else None,
            "running": self.running,
            "processed_trades": len(self.trade_processor._processed_ids),
        }
    
    # ── WebSocket subscription listener ───────────────────────────────────────
    
    async def _listen_trade_updates(self):
        """Listen for trade/update events."""
        try:
            logger.info("Attempting to subscribe to trade/update with buy_or_sell=1 filter...")
            subscription = await self.kit.subscribe("trade", "update", {"buy_or_sell": 1})
            logger.info("trade/update subscription active (completed trades only → Holdings.db + News)")

            event_count = 0
            async for event in subscription:
                if not self.running:
                    break
                try:
                    event_count += 1
                    trade = _obj_to_dict(event)
                    trade_id = trade.get("id")
                    is_buying = trade.get("buying", False)
                    is_selling = trade.get("selling", False)
                    
                    if event_count % 100 == 0:
                        logger.info(f"trade/update: received {event_count} events (last: id={trade_id}, buying={is_buying}, selling={is_selling})")
                    else:
                        logger.debug(f"trade/update received: id={trade_id}, buying={is_buying}, selling={is_selling}")
                    
                    await self.process_trade_update(event)
                except Exception as e:
                    logger.error(f"Error processing trade/update event: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("trade/update listener cancelled")
        except Exception as e:
            logger.error(f"trade/update listener error: {e}", exc_info=True)
            raise
    
    # ── Lifecycle ─────────────────────────────────────────────────────────────
    
    async def start(self):
        """Start the WebSocket subscription for trade events."""
        if self.running:
            logger.warning("TradeComponent already running")
            return
        
        # Recreate QueryKit for fresh connection on each start
        self.kit = QueryKit(self.api_key)
        
        self.running = True
        logger.info("Starting TradeComponent subscription")
        
        self._tasks = [
            asyncio.create_task(self._listen_trade_updates()),
        ]
        
        # Wait for the FIRST task to finish (any disconnect/crash triggers restart)
        done, pending = await asyncio.wait(
            self._tasks, return_when=asyncio.FIRST_COMPLETED
        )
        # Cancel all remaining listeners immediately
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        # Re-raise the first exception
        for t in done:
            if t.exception():
                raise t.exception()
    
    async def stop(self):
        """Stop the subscription."""
        self.running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        
        # Close pnwkit socket
        await self._close_kit_socket()
        logger.info("TradeComponent stopped")
    
    async def run_forever(self):
        """Run subscription indefinitely with automatic restart on disconnect/crash."""
        retry_count = 0
        max_retry_delay = 300  # 5 minutes max
        base_delay = 10  # Start with 10 seconds
        
        while True:
            try:
                await self.start()
                # Reset retry count on successful start
                retry_count = 0
            except asyncio.CancelledError:
                logger.info("TradeComponent cancelled")
                break
            except (aiohttp.ClientError, ConnectionResetError, OSError, ConnectionError) as e:
                retry_count += 1
                # Exponential backoff with jitter
                delay = min(base_delay * (2 ** min(retry_count - 1, 5)), max_retry_delay)
                # Add jitter to prevent thundering herd
                import random
                jitter = random.uniform(0.8, 1.2)
                actual_delay = delay * jitter
                
                logger.warning(f"TradeComponent disconnected ({e}) — retry {retry_count}, restarting in {actual_delay:.1f}s")
            except Exception as e:
                retry_count += 1
                delay = min(base_delay * (2 ** min(retry_count - 1, 5)), max_retry_delay)
                import random
                jitter = random.uniform(0.8, 1.2)
                actual_delay = delay * jitter
                
                logger.error(f"TradeComponent crashed ({e}) — retry {retry_count}, restarting in {actual_delay:.1f}s", exc_info=True)
            finally:
                self.running = False
                await self.stop()
            
            await asyncio.sleep(actual_delay)
    
    async def _close_kit_socket(self):
        """Close the pnwkit socket to avoid pending task warnings."""
        if not hasattr(self, 'kit') or self.kit is None:
            return
            
        socket = getattr(self.kit, "socket", None)
        if socket is None:
            return
            
        tasks_to_cancel = []
        for attr in ("task", "ping_pong_task", "_heartbeat_task"):
            t = getattr(socket, attr, None)
            if t is not None and not t.done():
                tasks_to_cancel.append(t)
                t.cancel()
                
        if tasks_to_cancel:
            try:
                await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
            except Exception as e:
                logger.warning(f"Error cancelling socket tasks: {e}")
                
        try:
            # Close WebSocket connection if it exists
            if hasattr(socket, 'ws') and socket.ws and not socket.ws.closed:
                await socket.ws.close()
            # Close HTTP session if it exists
            if hasattr(socket, 'session') and socket.session:
                await socket.session.close()
        except Exception as e:
            logger.debug(f"Error closing socket connection: {e}")
            
        # Clear references
        self.kit.socket = None
        self.kit = None

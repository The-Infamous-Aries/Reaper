"""
TradeComponent — GPP component for trade event processing.

Sub-components:
- TradeEventProcessor: Handles trade/update events and processes accepted trades
- TradeNewsGenerator: Generates news events for completed trades

This component writes to HoldingsDB and generates news for trade completions.
Only processes trades that are actually completed (accepted/date_accepted), not posted offers.
"""

import asyncio
import logging
from collections import deque
from typing import Any, Dict, Optional

import aiohttp
import pnwkit
from pnwkit.new import QueryKit

from PnWHarvester.core.activity_tracker import ActivityTracker
from PnWHarvester.core.pnwkit_compat import close_querykit, patch_pnwkit
from PnWHarvester.components.trade_utils import (
    normalize_trade_event,
    normalized_trade_to_news_payload,
    obj_to_dict,
)

patch_pnwkit()

logger = logging.getLogger(__name__)

_obj_to_dict = obj_to_dict

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
        
        Live code below overrides this legacy helper with accepted/date_accepted
        validation; this block is retained only for compatibility during import.
        
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
        
        Live code below overrides this legacy method with canonical
        buy_or_sell/accepted normalization.
        
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
            if self.holdings_db and hasattr(self.holdings_db, "claim_processed_event"):
                claimed = await self.holdings_db.claim_processed_event("trade_completed", trade_id_int)
                if not claimed:
                    self._mark_processed(trade_id_int)
                    logger.debug(f"trade/update → duplicate persisted {trade_id}, skipping")
                    return {"processed": 0, "skipped": 1, "duplicate": True}

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


    def _is_trade_completed(self, trade: Dict[str, Any]) -> bool:
        """
        Check if a trade is actually completed.

        trade/update can fire for any row update. A completed trade has
        accepted/date_accepted and is not rejected/cancelled.
        """
        normalized = normalize_trade_event(trade)
        return bool(normalized and normalized.get("completed"))

    async def _normalize_and_enrich_trade(self, trade: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        normalized = normalize_trade_event(trade)
        if not normalized:
            return None

        if self.holdings_db and hasattr(self.holdings_db, "get_trade_identities"):
            identities = await self.holdings_db.get_trade_identities(
                [normalized.get("buyer_id"), normalized.get("seller_id")]
            )
            normalized = normalize_trade_event(trade, identities)
        return normalized

    async def _already_legacy_processed(self, trade_id: int) -> bool:
        if not self.holdings_db or not hasattr(self.holdings_db, "is_processed_event"):
            return False
        return await self.holdings_db.is_processed_event("trade_completed", trade_id)

    async def _claim(self, event_type: str, trade_id: int) -> bool:
        if not self.holdings_db or not hasattr(self.holdings_db, "claim_processed_event"):
            return True
        return await self.holdings_db.claim_processed_event(event_type, trade_id)

    async def _unclaim(self, event_type: str, trade_id: int) -> None:
        if self.holdings_db and hasattr(self.holdings_db, "unclaim_processed_event"):
            await self.holdings_db.unclaim_processed_event(event_type, trade_id)

    async def process_trade_update(self, event: Any) -> Dict[str, Any]:
        """Process a completed trade/update event using canonical buyer/seller mapping."""
        trade = obj_to_dict(event)
        trade_id = trade.get("id")
        if not trade_id:
            return {"processed": 0, "skipped": 1, "reason": "no_id"}

        trade_id_int = int(trade_id)
        if self._is_duplicate(trade_id_int):
            logger.debug(f"trade/update -> duplicate {trade_id}, skipping")
            return {"processed": 0, "skipped": 1, "duplicate": True}

        normalized = await self._normalize_and_enrich_trade(trade)
        if not normalized:
            logger.debug(f"trade/update -> {trade_id} skipped: unable to normalize payload")
            self._mark_processed(trade_id_int)
            return {"processed": 0, "skipped": 1, "reason": "invalid_trade"}

        if not normalized.get("completed"):
            logger.debug(f"trade/update -> {trade_id} skipped: not completed")
            self._mark_processed(trade_id_int)
            return {"processed": 0, "skipped": 1, "completed": False}

        if not normalized.get("buyer_id") or not normalized.get("seller_id"):
            logger.warning(
                f"trade/update -> {trade_id} skipped: completed trade missing "
                "buyer/seller identity; timed query backfill will retry from GraphQL"
            )
            return {
                "processed": 0,
                "skipped": 1,
                "completed": True,
                "reason": "missing_buyer_seller_identity",
            }

        if await self._already_legacy_processed(trade_id_int):
            self._mark_processed(trade_id_int)
            logger.debug(f"trade/update -> duplicate legacy trade_completed {trade_id}, skipping")
            return {"processed": 0, "skipped": 1, "duplicate": True, "legacy": True}

        holdings_updated = False
        news_generated = False

        if self.holdings_db and await self._claim("trade_holdings_applied", trade_id_int):
            holdings_updated = await self._update_holdings_for_trade(normalized)
            if not holdings_updated:
                await self._unclaim("trade_holdings_applied", trade_id_int)
        elif self.holdings_db:
            logger.debug(f"trade/update -> holdings already applied for trade {trade_id}")

        if self.news_component and await self._claim("trade_news_generated", trade_id_int):
            news_generated = await self._generate_trade_news(normalized)
            if not news_generated:
                await self._unclaim("trade_news_generated", trade_id_int)
        elif self.news_component:
            logger.debug(f"trade/update -> news already generated for trade {trade_id}")

        logger.info(
            f"trade/update -> {trade_id} -> completed "
            f"holdings_updated={holdings_updated} news_generated={news_generated}"
        )
        self._mark_processed(trade_id_int)
        return {
            "processed": 1,
            "skipped": 0,
            "completed": True,
            "holdings_updated": holdings_updated,
            "news_generated": news_generated,
        }

    async def _update_holdings_for_trade(self, trade: Dict[str, Any]) -> bool:
        """Update holdings for a completed trade."""
        if not self.holdings_db:
            return False
        try:
            buyer = trade.get("buyer") or {}
            seller = trade.get("seller") or {}
            buyer_id = trade.get("buyer_id")
            seller_id = trade.get("seller_id")
            if not buyer_id or not seller_id:
                logger.warning(f"Trade {trade.get('id')} missing buyer/seller ids, skipping holdings update")
                return False

            return await self.holdings_db.apply_trade_completion(
                buyer_id=int(buyer_id),
                seller_id=int(seller_id),
                money_amount=float(trade.get("money_amount") or 0),
                resources=trade.get("resources_traded") or {},
                trade_date=trade.get("date_accepted") or trade.get("date"),
                buyer_name=buyer.get("name"),
                seller_name=seller.get("name"),
            )
        except Exception as e:
            logger.error(f"Failed to update holdings for trade {trade.get('id')}: {e}", exc_info=True)
            return False

    async def _generate_trade_news(self, trade: Dict[str, Any]) -> bool:
        """Generate news event for a completed trade."""
        if not self.news_component:
            return False
        try:
            from PnWHarvester.subscriptions.trade_news_components import TradeNewsGenerator
            generator = TradeNewsGenerator(self.news_component)
            result = await generator.generate_trade_completed_news(
                normalized_trade_to_news_payload(trade)
            )
            logger.info(f"trade/update -> {trade.get('id')} -> News generation result: {result}")
            return bool(result.get("generated"))
        except Exception as e:
            logger.error(f"news trade_completed error: {e}", exc_info=True)
            return False


class TradeComponent:
    """
    GPP component for trade event processing.
    
    Orchestrates the trade event processor and manages WebSocket subscription
    for trade/update events. The subscription receives trade row updates and
    this component processes only accepted marketplace transactions.
    """
    
    def __init__(
        self,
        holdings_db=None,
        news_component=None,
        websocket_manager=None,
        api_key: str = "",
    ):
        """
        Initialize the TradeComponent.
        
        Args:
            holdings_db: HoldingsDB instance (optional)
            news_component: NewsComponent instance (optional)
            websocket_manager: SharedWebSocketManager instance (optional)
            api_key: PnW API v3 key
        """
        self.holdings_db = holdings_db
        self.news_component = news_component
        self.websocket_manager = websocket_manager
        self.api_key = api_key
        
        # Use shared websocket manager if provided, otherwise fallback to own QueryKit
        if self.websocket_manager:
            self.kit = None  # Will use shared manager's kit
        else:
            self.kit = QueryKit(api_key)
        
        # Sub-component
        self.trade_processor = TradeEventProcessor(holdings_db, news_component)
        
        # Activity tracking for health monitoring
        self.activity_tracker = ActivityTracker(max_silence_seconds=120.0)
        
        # Subscription state
        self.running = False
        self._tasks: list[asyncio.Task] = []
    
    async def initialize(self):
        """Initialize the component."""
        # Register subscriptions for activity tracking
        self.activity_tracker.register_subscription("trade/update")
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
            "activity": self.activity_tracker.to_dict(),
        }
    
    # ── WebSocket subscription listener ───────────────────────────────────────
    
    async def _listen_trade_updates(self):
        """Listen for trade/update events."""
        subscription_name = "trade/update"
        try:
            logger.info("Attempting to subscribe to trade/update...")
            subscription = await self.kit.subscribe("trade", "update")
            logger.info("trade/update subscription active (accepted trades -> Holdings.db + News)")

            event_count = 0
            async for event in subscription:
                if not self.running:
                    break
                try:
                    self.activity_tracker.record_message(subscription_name)
                    event_count += 1
                    trade = obj_to_dict(event)
                    trade_id = trade.get("id")
                    buy_or_sell = trade.get("buy_or_sell")
                    accepted = trade.get("accepted")
                    date_accepted = trade.get("date_accepted") or trade.get("accept_date")
                    
                    if event_count % 100 == 0:
                        logger.info(
                            f"trade/update: received {event_count} events "
                            f"(last: id={trade_id}, buy_or_sell={buy_or_sell}, "
                            f"accepted={accepted}, date_accepted={date_accepted})"
                        )
                    else:
                        logger.debug(
                            f"trade/update received: id={trade_id}, "
                            f"buy_or_sell={buy_or_sell}, accepted={accepted}, "
                            f"date_accepted={date_accepted}"
                        )
                    
                    await self.process_trade_update(event)
                except Exception as e:
                    self.activity_tracker.record_error(subscription_name)
                    logger.error(f"Error processing trade/update event: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("trade/update listener cancelled")
        except pnwkit.errors.SubscribeError as e:
            self.activity_tracker.record_error(subscription_name)
            logger.warning(f"trade/update subscription error: {e} — will restart")
            raise
        except Exception as e:
            self.activity_tracker.record_error(subscription_name)
            logger.error(f"trade/update listener error: {e}", exc_info=True)
            raise
    
    # ── Lifecycle ─────────────────────────────────────────────────────────────
    
    async def start(self):
        """Start the WebSocket subscription for trade events."""
        if self.running:
            logger.warning("TradeComponent already running")
            return

        self.running = True
        
        # Use SharedWebSocketManager if available, otherwise use own QueryKit
        if self.websocket_manager:
            # Register subscription with shared manager
            await self.websocket_manager.subscribe(
                "trade", "update", {},
                self.process_trade_update
            )
            logger.info("TradeComponent started (using SharedWebSocketManager)")
            
            # Keep running until stopped
            while self.running:
                await asyncio.sleep(1)
        else:
            # Fallback to own QueryKit
            self.kit = QueryKit(self.api_key)
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
        actual_delay = base_delay  # Ensure defined before first loop iteration
        
        while True:
            try:
                await self.start()
                # Reset retry count on successful start
                retry_count = 0
            except asyncio.CancelledError:
                logger.info("TradeComponent cancelled")
                break
            except (aiohttp.ClientError, ConnectionResetError, OSError, ConnectionError, pnwkit.errors.SubscribeError) as e:
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
        await close_querykit(getattr(self, "kit", None))
        self.kit = None

"""
BankrecComponent — GPP component for bank record event processing.

Handles:
- bankrec/create events
- Updates to HoldingsDB for nation-type parties
- News event generation for bank transfers

This component writes to BankrecsDB and HoldingsDB.
"""

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp
from pnwkit.new import QueryKit

logger = logging.getLogger(__name__)


def _obj_to_dict(obj: Any) -> Dict[str, Any]:
    """Convert objects to dictionaries safely."""
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return dict(obj)
    return vars(obj)


class BankrecEventProcessor:
    """Processes bankrec/create events."""
    
    def __init__(self, bankrecs_db, holdings_db=None, news_component=None):
        """
        Initialize the bankrec event processor.
        
        Args:
            bankrecs_db: BankrecsDB instance
            holdings_db: HoldingsDB instance (optional)
            news_component: NewsComponent instance (optional)
        """
        self.bankrecs_db = bankrecs_db
        self.holdings_db = holdings_db
        self.news_component = news_component
        self._processed_ids: deque = deque(maxlen=5000)
    
    def _is_duplicate(self, bankrec_id: int) -> bool:
        """Check if bankrec ID was already processed."""
        return bankrec_id in self._processed_ids
    
    def _mark_processed(self, bankrec_id: int):
        """Mark bankrec ID as processed."""
        self._processed_ids.append(bankrec_id)
    
    async def process_bankrec_create(self, event: Any) -> Dict[str, Any]:
        """
        Process a bankrec/create event.
        
        Args:
            event: The pnwkit event object
            
        Returns:
            Processing statistics
        """
        bankrec = _obj_to_dict(event)
        bankrec_id = bankrec.get("id")
        
        if not bankrec_id:
            return {"processed": 0, "skipped": 1}
        
        bankrec_id_int = int(bankrec_id)
        
        # Check for duplicates
        if self._is_duplicate(bankrec_id_int):
            logger.debug(f"bankrec/create → duplicate {bankrec_id}, skipping")
            return {"processed": 0, "skipped": 1, "duplicate": True}
        
        # Save to BankrecsDB
        if self.bankrecs_db:
            await self.bankrecs_db.save_bankrec(bankrec)
        
        # Update HoldingsDB for nation-type parties
        if self.holdings_db:
            party_type = bankrec.get("party_type")
            if party_type == "nation":
                await self._update_holdings_for_bankrec(bankrec)
        
        # Generate news event
        await self._generate_bankrec_news(bankrec)
        
        self._mark_processed(bankrec_id_int)
        
        logger.debug(f"bankrec/create → {bankrec_id} → Bankrecs.db")
        
        return {"processed": 1, "skipped": 0}
    
    async def _update_holdings_for_bankrec(self, bankrec: Dict[str, Any]):
        """Update holdings for a nation-type bank record."""
        nation_id = bankrec.get("party_id")
        if not nation_id:
            return
        
        # Extract resources
        _RESOURCES = (
            "coal", "oil", "uranium", "iron", "bauxite", "lead",
            "gasoline", "munitions", "steel", "aluminum", "food",
        )
        
        money = float(bankrec.get("money") or 0)
        resources = {r: float(bankrec.get(r) or 0) for r in _RESOURCES}
        
        # Determine if this is a deposit or withdrawal
        # Positive values = money/resources leaving the bank (withdrawal)
        # Negative values = money/resources entering the bank (deposit)
        # For holdings tracking, we need to invert this logic
        # Withdrawal from bank = gain for nation
        # Deposit to bank = loss for nation
        
        # Check if money is positive (withdrawal) or negative (deposit)
        if money > 0:
            # Withdrawal - nation gains money
            await self.holdings_db.apply_bank_withdrawal(
                nation_id=int(nation_id),
                money_withdrawn=money,
                resources_withdrawn={r: v for r, v in resources.items() if v > 0},
                event_date=bankrec.get("date"),
                nation_name=bankrec.get("party_name"),
            )
        elif money < 0:
            # Deposit - nation loses money
            await self.holdings_db.apply_bank_deposit(
                nation_id=int(nation_id),
                money_deposited=abs(money),
                resources_deposited={r: abs(v) for r, v in resources.items() if v < 0},
                event_date=bankrec.get("date"),
                nation_name=bankrec.get("party_name"),
            )
    
    async def _generate_bankrec_news(self, bankrec: Dict[str, Any]):
        """Generate news event for bank transfer."""
        if self.news_component:
            try:
                resources = {r: float(bankrec.get(r) or 0) for r in (
                    "coal", "oil", "uranium", "iron", "bauxite", "lead",
                    "gasoline", "munitions", "steel", "aluminum", "food",
                )}
                money = float(bankrec.get("money") or 0)
                
                # Determine event type and headline based on transfer type
                sender_type = bankrec.get("sender_type")
                receiver_type = bankrec.get("receiver_type")
                
                if sender_type == 2 and receiver_type == 1:  # Alliance -> Nation (withdrawal)
                    event_type = "bank_withdrawal"
                    headline = f"{bankrec.get('receiver_name')} withdrew money from alliance bank"
                elif sender_type == 1 and receiver_type == 2:  # Nation -> Alliance (deposit)
                    event_type = "bank_deposit"
                    headline = f"{bankrec.get('sender_name')} deposited money to alliance bank"
                elif sender_type == 1 and receiver_type == 1:  # Nation -> Nation (transfer)
                    event_type = "bank_transfer"
                    headline = f"{bankrec.get('sender_name')} sent money to {bankrec.get('receiver_name')}"
                else:
                    event_type = "bank_other"
                    headline = "Bank transfer"
                
                await self.news_component.record_event(
                    event_type=event_type,
                    nation_id=int(bankrec.get("sender_id") or 0),
                    nation_name=bankrec.get("sender_name"),
                    alliance_id=int(bankrec.get("receiver_id") or 0) if receiver_type == 2 else None,
                    alliance_name=bankrec.get("receiver_name") if receiver_type == 2 else None,
                    value=money,
                    headline=headline,
                    detail={
                        "bankrec_id": int(bankrec.get("id") or 0),
                        "sender_type": sender_type,
                        "receiver_type": receiver_type,
                        "receiver_id": int(bankrec.get("receiver_id") or 0),
                        "receiver_name": bankrec.get("receiver_name"),
                        "note": bankrec.get("note"),
                        "resources": resources,
                    },
                    event_date=bankrec.get("date"),
                )
            except Exception as _ne:
                logger.debug(f"news bankrec: {_ne}")


class BankrecComponent:
    """
    GPP component for bank record event processing.
    
    Orchestrates the sub-components for processing bank record events.
    Also manages WebSocket subscription for bankrec/create events.
    """
    
    def __init__(
        self,
        bankrecs_db,
        holdings_db=None,
        news_component=None,
        api_key: str = "",
    ):
        """
        Initialize the BankrecComponent.
        
        Args:
            bankrecs_db: BankrecsDB instance
            holdings_db: HoldingsDB instance (optional)
            news_component: NewsComponent instance (optional)
            api_key: PnW API v3 key
        """
        self.bankrecs_db = bankrecs_db
        self.holdings_db = holdings_db
        self.news_component = news_component
        self.api_key = api_key
        self.kit = QueryKit(api_key)
        
        # Sub-components
        self.bankrec_processor = BankrecEventProcessor(bankrecs_db, holdings_db, news_component)
        
        # Subscription state
        self.running = False
        self._tasks: list[asyncio.Task] = []
    
    async def initialize(self):
        """Initialize the component."""
        logger.info("BankrecComponent initialized")
    
    async def process_bankrec_create(self, event: Any) -> Dict[str, Any]:
        """Process a bankrec/create event."""
        return await self.bankrec_processor.process_bankrec_create(event)
    
    async def get_component_stats(self) -> Dict[str, Any]:
        """Get component statistics."""
        return {
            "type": "BankrecComponent",
            "processed_count": len(self.bankrec_processor._processed_ids),
            "bankrecs_db_path": self.bankrecs_db.db_path if self.bankrecs_db else None,
            "holdings_db_path": self.holdings_db.db_path if self.holdings_db else None,
            "running": self.running,
        }
    
    # ── WebSocket subscription listener ────────────────────────────────────────
    
    async def _listen_bankrec_creates(self):
        """Listen for bankrec/create events."""
        try:
            subscription = await self.kit.subscribe("bankrec", "create")
            logger.info("bankrec/create subscription active")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    await self.process_bankrec_create(event)
                except Exception as e:
                    logger.error(f"Error processing bankrec/create event: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("bankrec/create listener cancelled")
        except Exception as e:
            logger.error(f"bankrec/create listener error: {e}", exc_info=True)
            raise
    
    # ── Lifecycle ─────────────────────────────────────────────────────────────
    
    async def start(self):
        """Start WebSocket subscription for bankrec/create events."""
        if self.running:
            logger.warning("BankrecComponent already running")
            return
        
        self.running = True
        logger.info("Starting BankrecComponent subscription")
        
        self._tasks = [
            asyncio.create_task(self._listen_bankrec_creates()),
        ]
        
        # Wait for the task to complete (disconnect/crash triggers restart)
        await asyncio.gather(*self._tasks, return_exceptions=True)
    
    async def stop(self):
        """Stop subscription."""
        self.running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        
        # Close pnwkit socket
        await self._close_kit_socket()
        logger.info("BankrecComponent stopped")
    
    async def run_forever(self):
        """Run subscription indefinitely with automatic restart on disconnect/crash."""
        while True:
            try:
                await self.start()
            except asyncio.CancelledError:
                logger.info("BankrecComponent cancelled")
                break
            except (aiohttp.ClientError, ConnectionResetError, OSError) as e:
                logger.warning(f"BankrecComponent disconnected ({e}) — restarting in 30s")
            except Exception as e:
                logger.error(f"BankrecComponent crashed ({e}) — restarting in 30s", exc_info=True)
            finally:
                self.running = False
                await self.stop()
            
            await asyncio.sleep(30)
    
    async def _close_kit_socket(self):
        """Close the pnwkit socket to avoid pending task warnings."""
        socket = getattr(self.kit, "socket", None)
        if socket is None:
            return
        tasks_to_cancel = []
        for attr in ("task", "ping_pong_task"):
            t = getattr(socket, attr, None)
            if t is not None and not t.done():
                tasks_to_cancel.append(t)
                t.cancel()
        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
        try:
            if not socket.closed:
                await socket.ws.close()
        except Exception:
            pass
        self.kit.socket = None

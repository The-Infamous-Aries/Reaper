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
        
        # Two types of war-related bank recs:
        # 1. Nation loot (stype=1, rtype=1): attacker loots from defender nation - handled by war subscription
        # 2. Alliance bank loot (stype=2, rtype=1): attacker loots from alliance bank - handled here
        stype = int(bankrec.get("sender_type") or 0)
        rtype = int(bankrec.get("receiver_type") or 0)
        note = bankrec.get("note") or ""
        _note_lower = note.lower()
        
        # More flexible war note detection - check for various loot indicators
        _is_war_note = (
            ("defeated" in _note_lower and "captured" in _note_lower)
            or "looted from war" in _note_lower
            or "war loot" in _note_lower
            or ("war #" in _note_lower and "captured" in _note_lower)
            or ("defeated" in _note_lower and "resources" in _note_lower)
        )
        
        is_nation_loot = (stype == 1 and rtype == 1 and _is_war_note)  # handled by war subscription
        is_alliance_loot = (stype == 2 and rtype == 1 and _is_war_note)  # alliance bank looted
        
        # Log detection for debugging
        if _is_war_note:
            logger.info(f"bankrec/create → {bankrec_id} → War note detected: stype={stype}, rtype={rtype}, note='{note}'")
            logger.info(f"bankrec/create → {bankrec_id} → is_nation_loot={is_nation_loot}, is_alliance_loot={is_alliance_loot}")
        
        # Save to BankrecsDB
        if self.bankrecs_db:
            await self.bankrecs_db.save_bankrec(bankrec)
        
        # Update HoldingsDB
        if self.holdings_db:
            if is_alliance_loot:
                # Alliance loot: only add to winner (receiver), don't affect loser
                await self._update_holdings_for_alliance_loot(bankrec)
            elif not is_nation_loot:
                # Normal bank transfer: apply standard bankrec logic
                # Skip nation loot (stype=1,rtype=1 war recs) - war subscription handles holdings
                await self._update_holdings_for_bankrec(bankrec)
        
        # Generate news event
        # nation loot news is handled by the war subscription - skip here
        if not is_nation_loot:
            await self._generate_bankrec_news(bankrec, is_alliance_loot)
        
        self._mark_processed(bankrec_id_int)
        
        logger.debug(f"bankrec/create → {bankrec_id} → Bankrecs.db (alliance_loot={is_alliance_loot}, nation_loot={is_nation_loot})")
        
        return {"processed": 1, "skipped": 0}
    
    async def _update_holdings_for_bankrec(self, bankrec: Dict[str, Any]):
        """Update holdings for a bank record using apply_bankrec."""
        # apply_bankrec handles both sender and receiver in one call
        # It checks sender_type/receiver_type to determine which are nations
        # and correctly adds/deducts from each party's holdings
        await self.holdings_db.apply_bankrec(bankrec)
    
    async def _update_holdings_for_alliance_loot(self, bankrec: Dict[str, Any]):
        """
        Update holdings for alliance loot events.
        
        Alliance loot only adds to the winner's holdings (receiver).
        It does NOT affect the loser's holdings since the loot comes from
        the alliance bank, not the loser's personal holdings.
        """
        receiver_id = bankrec.get("receiver_id")
        if not receiver_id:
            logger.warning(f"Alliance loot bankrec {bankrec.get('id')} has no receiver_id")
            return
        
        # Get current holdings for receiver
        current = await self.holdings_db.get_holdings(int(receiver_id))
        if not current:
            logger.warning(f"Alliance loot bankrec {bankrec.get('id')}: nation {receiver_id} not found in holdings")
            return
        
        # Extract loot resources
        money = float(bankrec.get("money") or 0)
        resources = {r: float(bankrec.get(r) or 0) for r in (
            "coal", "oil", "uranium", "iron", "bauxite", "lead",
            "gasoline", "munitions", "steel", "aluminum", "food",
        )}
        
        # Add loot to current holdings
        new_money = current.get("money", 0) + money
        new_resources = {r: current.get(r, 0) + resources.get(r, 0) for r in resources}
        
        # Update holdings
        await self.holdings_db.set_complete_holdings(
            nation_id=int(receiver_id),
            money=new_money,
            resources=new_resources,
            military={m: current.get(m, 0) for m in (
                "soldiers", "tanks", "aircraft", "ships", "missiles", "nukes", "spies"
            )},
            confidence=current.get("confidence", "fresh"),
            event_date=bankrec.get("date"),
            nation_name=bankrec.get("receiver_name"),
            description="alliance_loot",
        )
        
        logger.debug(f"Alliance loot added to nation {receiver_id}: money={money}, resources={resources}")
    
    async def _generate_bankrec_news(self, bankrec: Dict[str, Any], is_alliance_loot: bool = False):
        """Generate news event for bank transfer."""
        if self.news_component:
            try:
                resources = {r: float(bankrec.get(r) or 0) for r in (
                    "coal", "oil", "uranium", "iron", "bauxite", "lead",
                    "gasoline", "munitions", "steel", "aluminum", "food",
                )}
                money = float(bankrec.get("money") or 0)
                
                if is_alliance_loot:
                    # Alliance loot event - use news_writer for proper formatting with loot table
                    from PnWHarvester.db.news_writer import record_loot_attack
                    
                    receiver_id = int(bankrec.get("receiver_id") or 0)
                    receiver_name = bankrec.get("receiver_name") or f"nation {receiver_id}"
                    sender_name = bankrec.get("sender_name") or "alliance bank"
                    sender_id = int(bankrec.get("sender_id") or 0)
                    
                    logger.info(f"bankrec/create → {bankrec_id} → Processing alliance loot: receiver={receiver_name} ({receiver_id}), sender={sender_name} ({sender_id})")
                    
                    # Look up attacker's alliance info from database
                    att_alliance_id = None
                    att_alliance_name = None
                    if receiver_id > 0:
                        try:
                            import sqlite3 as _sqlite3
                            from Systems.Functions.db_paths import GLOBAL_NATIONS_DB_STR
                            _conn = _sqlite3.connect(GLOBAL_NATIONS_DB_STR)
                            row = _conn.execute(
                                "SELECT alliance_id, alliance_name FROM nations WHERE id = ?",
                                (receiver_id,)
                            ).fetchone()
                            _conn.close()
                            if row:
                                att_alliance_id = row[0]
                                att_alliance_name = row[1]
                                logger.info(f"bankrec/create → {bankrec_id} → Attacker alliance: {att_alliance_name} ({att_alliance_id})")
                        except Exception as e:
                            logger.warning(f"Failed to lookup attacker alliance: {e}")
                    
                    # Calculate total value
                    total_value = money
                    if resources:
                        # Get resource prices from reaper.db
                        try:
                            import sqlite3 as _sqlite3
                            from Systems.Functions.db_paths import REAPER_DB_STR
                            _conn = _sqlite3.connect(REAPER_DB_STR)
                            rows = _conn.execute(
                                "SELECT resource, best_sell_price FROM resource_prices "
                                "WHERE timestamp = (SELECT MAX(timestamp) FROM resource_prices)"
                            ).fetchall()
                            _conn.close()
                            prices = {r.lower(): float(p) for r, p in rows if p and float(p) > 0}
                            for r, amt in resources.items():
                                if amt > 0 and r in prices:
                                    total_value += amt * prices[r]
                        except Exception as e:
                            logger.warning(f"Failed to get resource prices for alliance loot: {e}")
                    
                    logger.info(f"bankrec/create → {bankrec_id} → Alliance loot value: ${total_value:,.2f} (money=${money:,.2f})")
                    
                    # Use record_loot_attack to generate proper news with loot table
                    # Treat alliance bank as "defender" with no nation
                    await record_loot_attack(
                        att_nation_id=receiver_id,
                        att_nation_name=receiver_name,
                        att_nation_flag=None,
                        att_alliance_id=att_alliance_id,
                        att_alliance_name=att_alliance_name,
                        att_alliance_flag=None,
                        def_nation_id=0,  # Alliance bank has no nation
                        def_nation_name=sender_name,  # Alliance bank name
                        def_nation_flag=None,
                        def_alliance_id=sender_id,  # Alliance ID
                        def_alliance_name=sender_name,
                        money_looted=money,
                        total_loot_value=total_value,
                        event_date=bankrec.get("date"),
                        resources_looted=resources,
                        improvements_destroyed=None,
                        infra_destroyed_value=0.0,
                    )
                    logger.info(f"bankrec/create → {bankrec_id} → Alliance loot news generated")
                    return
                
                # Use news_writer.record_bank_transfer for proper formatting with resource breakdown
                from PnWHarvester.db.news_writer import record_bank_transfer
                
                # Extract IDs and names based on sender/receiver types
                stype = bankrec.get("sender_type")
                rtype = bankrec.get("receiver_type")
                
                # Convert empty strings to None so database lookup triggers
                def _clean_name(val):
                    return val if val and val != "0" else None
                
                def _clean_id(val):
                    return int(val) if val and int(val) > 0 else None
                
                await record_bank_transfer(
                    rec=bankrec,
                    sender_nation_id=_clean_id(bankrec.get("sender_id")) if stype == 1 else None,
                    sender_nation_name=_clean_name(bankrec.get("sender_name")) if stype == 1 else None,
                    sender_nation_flag=None,
                    sender_alliance_id=_clean_id(bankrec.get("sender_id")) if stype == 2 else None,
                    sender_alliance_name=_clean_name(bankrec.get("sender_name")) if stype == 2 else None,
                    receiver_nation_id=_clean_id(bankrec.get("receiver_id")) if rtype == 1 else None,
                    receiver_nation_name=_clean_name(bankrec.get("receiver_name")) if rtype == 1 else None,
                    receiver_nation_flag=None,
                    receiver_alliance_id=_clean_id(bankrec.get("receiver_id")) if rtype == 2 else None,
                    receiver_alliance_name=_clean_name(bankrec.get("receiver_name")) if rtype == 2 else None,
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
        
        # Recreate QueryKit for fresh connection on each start
        self.kit = QueryKit(self.api_key)
        
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
        retry_count = 0
        max_retry_delay = 300  # 5 minutes max
        base_delay = 10  # Start with 10 seconds
        
        while True:
            try:
                await self.start()
                # Reset retry count on successful start
                retry_count = 0
            except asyncio.CancelledError:
                logger.info("BankrecComponent cancelled")
                break
            except (aiohttp.ClientError, ConnectionResetError, OSError, ConnectionError) as e:
                retry_count += 1
                # Exponential backoff with jitter
                delay = min(base_delay * (2 ** min(retry_count - 1, 5)), max_retry_delay)
                # Add jitter to prevent thundering herd
                import random
                jitter = random.uniform(0.8, 1.2)
                actual_delay = delay * jitter
                
                logger.warning(f"BankrecComponent disconnected ({e}) — retry {retry_count}, restarting in {actual_delay:.1f}s")
            except Exception as e:
                retry_count += 1
                delay = min(base_delay * (2 ** min(retry_count - 1, 5)), max_retry_delay)
                import random
                jitter = random.uniform(0.8, 1.2)
                actual_delay = delay * jitter
                
                logger.error(f"BankrecComponent crashed ({e}) — retry {retry_count}, restarting in {actual_delay:.1f}s", exc_info=True)
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

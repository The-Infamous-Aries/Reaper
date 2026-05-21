"""
NationComponent — GPP component for nation and city event processing.

Sub-components:
- NationEventProcessor: Handles nation/create, nation/update events
- CityEventProcessor: Handles city/create, city/update events
- SpendingDetector: Detects and records spending (cities, projects, military, upgrades)
- BeigeEarlyExitDetector: Detects early beige exits and enqueues notifications

This component writes to GlobalNationsDB, HoldingsDB, and beige_alerts_db.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

import aiohttp
from pnwkit.new import QueryKit

logger = logging.getLogger(__name__)

NW_ALLIANCE_ID = 14225


def _obj_to_dict(obj: Any) -> Dict[str, Any]:
    """Convert pnwkit objects to dictionaries."""
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return dict(obj)
    return vars(obj)


class NationEventProcessor:
    """Processes nation/create and nation/update events."""
    
    def __init__(self, global_db, holdings_db=None, news_component=None):
        """
        Initialize the nation event processor.
        
        Args:
            global_db: GlobalNationsDB instance
            holdings_db: HoldingsDB instance (optional)
            news_component: NewsComponent instance (optional)
        """
        self.global_db = global_db
        self.holdings_db = holdings_db
        self.news_component = news_component
        self._nw_nation_ids: Set[int] = set()
    
    async def seed_nw_set(self):
        """Seed the in-memory NW set from GlobalNations.db."""
        if not self.global_db:
            return
        try:
            import sqlite3
            async with self.global_db._get_lock():
                with sqlite3.connect(self.global_db.db_path) as conn:
                    rows = conn.execute(
                        "SELECT id FROM nations WHERE alliance_id = ?",
                        (NW_ALLIANCE_ID,),
                    ).fetchall()
                    self._nw_nation_ids = {r[0] for r in rows}
            logger.info(f"NW nation set seeded: {len(self._nw_nation_ids)} members")
        except Exception as e:
            logger.error(f"Failed to seed NW nation set: {e}", exc_info=True)
    
    def is_nw_by_alliance(self, nation: Dict[str, Any]) -> bool:
        """Check if nation is in NW by alliance_id."""
        return int(nation.get("alliance_id") or 0) == NW_ALLIANCE_ID
    
    def is_nw_id(self, nation_id: int) -> bool:
        """Check if nation_id is in NW set."""
        return nation_id in self._nw_nation_ids
    
    @staticmethod
    def extract_alliance(nation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Flatten nested alliance object into top-level fields.
        """
        alliance_obj = nation.get("alliance") or {}
        if isinstance(alliance_obj, dict):
            if alliance_obj.get("id"):
                nation["alliance_id"] = alliance_obj["id"]
            if alliance_obj.get("name"):
                nation["alliance_name"] = alliance_obj["name"]
            if alliance_obj.get("flag"):
                nation["alliance_flag"] = alliance_obj["flag"]
        if nation.get("alliance_name") == '0':
            nation["alliance_name"] = None
        return nation
    
    async def get_existing_nation(self, nation_id: int) -> Optional[Dict[str, Any]]:
        """Get existing nation from database."""
        if not self.global_db:
            return None
        try:
            return await self.global_db.get_nation(nation_id)
        except Exception as e:
            logger.debug(f"get_existing_nation({nation_id}): {e}")
            return None
    
    async def process_nation_event(
        self,
        event: Any,
        event_type: str,
    ) -> Dict[str, Any]:
        """
        Process a nation event (create or update).
        
        Args:
            event: The pnwkit event object
            event_type: Either "create" or "update"
            
        Returns:
            Processing statistics
        """
        nation = _obj_to_dict(event)
        nation_id = nation.get("id")
        if not nation_id:
            return {"processed": 0, "skipped": 1}
        
        nation_id_int = int(nation_id)
        
        # Extract alliance
        self.extract_alliance(nation)
        is_nw = self.is_nw_by_alliance(nation)
        
        # Update NW set
        if is_nw:
            self._nw_nation_ids.add(nation_id_int)
        elif nation_id_int in self._nw_nation_ids:
            self._nw_nation_ids.discard(nation_id_int)
            logger.info(
                f"nation/{event_type} → nation {nation_id} left NW "
                f"(alliance_id now {nation.get('alliance_id')})"
            )
        
        # Get old state for diffing
        old_nation: Optional[Dict[str, Any]] = None
        if event_type == "update" and self.global_db:
            old_nation = await self.get_existing_nation(nation_id_int)
            if old_nation:
                old_aid = old_nation.get("alliance_id")
                new_aid = nation.get("alliance_id")
                if old_aid != new_aid:
                    logger.info(
                        f"nation/{event_type} → nation {nation_id} alliance change: "
                        f"{old_aid} ({old_nation.get('alliance_name','?')}) → "
                        f"{new_aid} ({nation.get('alliance_name','?')})"
                    )
                    # News: alliance change
                    if self.news_component:
                        try:
                            asyncio.create_task(self.news_component.record_event(
                                event_type="alliance_change",
                                nation_id=nation_id_int,
                                nation_name=nation.get("nation_name"),
                                nation_flag=nation.get("flag"),
                                alliance_id=int(new_aid) if new_aid else None,
                                alliance_name=nation.get("alliance_name"),
                                alliance_flag=nation.get("alliance_flag"),
                                headline=f"{nation.get('nation_name')} joins {nation.get('alliance_name')}",
                                detail={
                                    "old_alliance_id": int(old_aid) if old_aid else None,
                                    "old_alliance_name": old_nation.get("alliance_name"),
                                    "new_alliance_id": int(new_aid) if new_aid else None,
                                    "new_alliance_name": nation.get("alliance_name"),
                                },
                                event_date=nation.get("last_active"),
                            ))
                        except Exception as _ne:
                            logger.debug(f"news alliance_change: {_ne}")
        
        # Save nation
        await self._save_nation(nation, old_nation=old_nation)
        
        logger.debug(
            f"nation/{event_type} → {nation_id} → GlobalNations.db"
            + (" [NW]" if is_nw else "")
        )
        
        return {"processed": 1, "skipped": 0}
    
    async def _save_nation(
        self,
        nation: Dict[str, Any],
        old_nation: Optional[Dict[str, Any]] = None,
    ):
        """Save nation to database with spending detection."""
        nation_id = nation.get("id")
        if not nation_id:
            return
        
        nation_id_int = int(nation_id)
        
        # Detect spending before overwriting
        if self.holdings_db and self.global_db:
            if old_nation is None:
                old_nation = await self.get_existing_nation(nation_id_int)
            if old_nation:
                from .spending_detector import SpendingDetector
                detector = SpendingDetector(self.holdings_db)
                await detector.detect_nation_spending(
                    nation_id=nation_id_int,
                    old_nation=old_nation,
                    new_nation=nation,
                    event_date=nation.get("last_active"),
                )
        
        # Strip holdings columns on update
        _HOLDINGS_COLS = frozenset((
            "money", "coal", "oil", "uranium", "iron", "bauxite", "lead",
            "gasoline", "munitions", "steel", "aluminum", "food",
            "soldiers", "tanks", "aircraft", "ships", "missiles", "nukes", "spies",
        ))
        if self.global_db:
            if old_nation is not None:
                nation_for_db = {k: v for k, v in nation.items() if k not in _HOLDINGS_COLS}
            else:
                nation_for_db = dict(nation)
            await self.global_db.save_nation(nation_for_db)


class CityEventProcessor:
    """Processes city/create and city/update events."""
    
    def __init__(self, global_db, holdings_db=None):
        """
        Initialize the city event processor.
        
        Args:
            global_db: GlobalNationsDB instance
            holdings_db: HoldingsDB instance (optional)
        """
        self.global_db = global_db
        self.holdings_db = holdings_db
    
    async def get_existing_city(self, city_id: int) -> Optional[Dict[str, Any]]:
        """Get existing city from database."""
        if not self.global_db:
            return None
        try:
            import sqlite3
            async with self.global_db._get_lock():
                with sqlite3.connect(self.global_db.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute(
                        "SELECT * FROM cities WHERE id = ?", (city_id,)
                    ).fetchone()
                    return dict(row) if row else None
        except Exception as e:
            logger.debug(f"get_existing_city({city_id}): {e}")
            return None
    
    async def get_existing_nation(self, nation_id: int) -> Optional[Dict[str, Any]]:
        """Get existing nation from database."""
        if not self.global_db:
            return None
        try:
            return await self.global_db.get_nation(nation_id)
        except Exception as e:
            logger.debug(f"get_existing_nation({nation_id}): {e}")
            return None
    
    async def process_city_event(
        self,
        event: Any,
        event_type: str,
    ) -> Dict[str, Any]:
        """
        Process a city event (create or update).
        
        Args:
            event: The pnwkit event object
            event_type: Either "create" or "update"
            
        Returns:
            Processing statistics
        """
        city = _obj_to_dict(event)
        city_id = city.get("id")
        nation_id = city.get("nation_id")
        if not city_id or not nation_id:
            return {"processed": 0, "skipped": 1}
        
        await self._save_city(int(nation_id), city)
        
        logger.debug(f"city/{event_type} → city {city_id} nation {nation_id}")
        
        return {"processed": 1, "skipped": 0}
    
    async def _save_city(self, nation_id: int, city: Dict[str, Any]):
        """Save city to database with spending detection."""
        city_id = city.get("id")
        if not city_id:
            return
        
        is_new_city = False
        if self.holdings_db and self.global_db:
            old_city = await self.get_existing_city(int(city_id))
            if old_city:
                nation_data = await self.get_existing_nation(nation_id)
                from .spending_detector import SpendingDetector
                detector = SpendingDetector(self.holdings_db)
                await detector.detect_city_spending(
                    nation_id=nation_id,
                    old_city=old_city,
                    new_city=city,
                    nation_data=nation_data,
                    event_date=self._now_str(),
                )
            else:
                is_new_city = True
        
        if self.global_db:
            await self.global_db.upsert_city(nation_id, city)
            if is_new_city:
                await self.global_db.increment_num_cities(nation_id)
    
    @staticmethod
    def _now_str() -> str:
        """Get current UTC time as string."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class AccountEventProcessor:
    """Processes account/update events."""
    
    def __init__(self, global_db):
        """
        Initialize the account event processor.
        
        Args:
            global_db: GlobalNationsDB instance
        """
        self.global_db = global_db
    
    async def process_account_event(self, event: Any) -> Dict[str, Any]:
        """
        Process an account/update event.
        
        Args:
            event: The pnwkit event object
            
        Returns:
            Processing statistics
        """
        account = _obj_to_dict(event)
        nation_id = account.get("id") or account.get("nation_id")
        if not nation_id:
            return {"processed": 0, "skipped": 1}
        
        # Only patch fields this event carries
        patch: Dict[str, Any] = {"id": nation_id}
        if account.get("last_active") is not None:
            patch["last_active"] = account["last_active"]
        if account.get("discord_id") is not None:
            patch["discord_id"] = account["discord_id"]
        
        if len(patch) > 1 and self.global_db:
            await self.global_db.save_nation(patch)
        
        logger.debug(f"account/update → patched nation {nation_id}")
        
        return {"processed": 1, "skipped": 0}


class NationComponent:
    """
    GPP component for nation and city event processing.
    
    Orchestrates the sub-components for processing nation, city, and account events.
    Also manages WebSocket subscriptions for nation, city, and account events.
    """
    
    def __init__(
        self,
        global_db,
        holdings_db=None,
        beige_component=None,
        news_component=None,
        api_key: str = "",
    ):
        """
        Initialize the NationComponent.
        
        Args:
            global_db: GlobalNationsDB instance
            holdings_db: HoldingsDB instance (optional)
            beige_component: BeigeAlertComponent instance (optional)
            news_component: NewsComponent instance (optional)
            api_key: PnW API v3 key
        """
        self.global_db = global_db
        self.holdings_db = holdings_db
        self.beige_component = beige_component
        self.news_component = news_component
        self.api_key = api_key
        self.kit = QueryKit(api_key)
        
        # Sub-components
        self.nation_processor = NationEventProcessor(global_db, holdings_db, news_component)
        self.city_processor = CityEventProcessor(global_db, holdings_db)
        self.account_processor = AccountEventProcessor(global_db)
        
        # Beige early-exit detector
        from .beige_early_exit_detector import BeigeEarlyExitDetector
        self.beige_detector = BeigeEarlyExitDetector(beige_component)
        
        # Subscription state
        self.running = False
        self._tasks: list[asyncio.Task] = []
    
    async def initialize(self):
        """Initialize the component (seed NW set, etc.)."""
        await self.nation_processor.seed_nw_set()
        logger.info("NationComponent initialized")
    
    async def process_nation_update(self, event: Any) -> Dict[str, Any]:
        """Process a nation/update event."""
        stats = await self.nation_processor.process_nation_event(event, "update")
        
        # Check for beige early exit
        nation = _obj_to_dict(event)
        old_nation = await self.nation_processor.get_existing_nation(int(nation.get("id")))
        await self.beige_detector.check_early_exit(nation, old_nation)
        
        return stats
    
    async def process_nation_create(self, event: Any) -> Dict[str, Any]:
        """Process a nation/create event."""
        return await self.nation_processor.process_nation_event(event, "create")
    
    async def process_city_update(self, event: Any) -> Dict[str, Any]:
        """Process a city/update event."""
        return await self.city_processor.process_city_event(event, "update")
    
    async def process_city_create(self, event: Any) -> Dict[str, Any]:
        """Process a city/create event."""
        return await self.city_processor.process_city_event(event, "create")
    
    async def process_account_update(self, event: Any) -> Dict[str, Any]:
        """Process an account/update event."""
        return await self.account_processor.process_account_event(event)
    
    async def get_component_stats(self) -> Dict[str, Any]:
        """Get component statistics."""
        return {
            "type": "NationComponent",
            "nw_nation_count": len(self.nation_processor._nw_nation_ids),
            "global_db_path": self.global_db.db_path if self.global_db else None,
            "holdings_db_path": self.holdings_db.db_path if self.holdings_db else None,
            "running": self.running,
        }
    
    # ── WebSocket subscription listeners ───────────────────────────────────────
    
    async def _listen_nation_updates(self):
        """Listen for nation/update events."""
        try:
            subscription = await self.kit.subscribe("nation", "update")
            logger.info("nation/update subscription active (all nations → GlobalNations.db)")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    await self.process_nation_update(event)
                except Exception as e:
                    logger.error(f"Error processing nation/update event: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("nation/update listener cancelled")
        except Exception as e:
            logger.error(f"nation/update listener error: {e}", exc_info=True)
            raise
    
    async def _listen_nation_creates(self):
        """Listen for nation/create events."""
        try:
            subscription = await self.kit.subscribe("nation", "create")
            logger.info("nation/create subscription active (all nations → GlobalNations.db)")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    await self.process_nation_create(event)
                except Exception as e:
                    logger.error(f"Error processing nation/create event: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("nation/create listener cancelled")
        except Exception as e:
            logger.error(f"nation/create listener error: {e}", exc_info=True)
            raise
    
    async def _listen_account_updates(self):
        """Listen for account/update events."""
        try:
            subscription = await self.kit.subscribe("account", "update")
            logger.info("account/update subscription active")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    await self.process_account_update(event)
                except Exception as e:
                    logger.error(f"Error processing account/update event: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("account/update listener cancelled")
        except Exception as e:
            logger.error(f"account/update listener error: {e}", exc_info=True)
            raise
    
    async def _listen_city_updates(self):
        """Listen for city/update events."""
        try:
            subscription = await self.kit.subscribe("city", "update")
            logger.info("city/update subscription active (all cities → GlobalNations.db)")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    await self.process_city_update(event)
                except Exception as e:
                    logger.error(f"Error processing city/update event: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("city/update listener cancelled")
        except Exception as e:
            logger.error(f"city/update listener error: {e}", exc_info=True)
            raise
    
    async def _listen_city_creates(self):
        """Listen for city/create events."""
        try:
            subscription = await self.kit.subscribe("city", "create")
            logger.info("city/create subscription active (all cities → GlobalNations.db)")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    await self.process_city_create(event)
                except Exception as e:
                    logger.error(f"Error processing city/create event: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("city/create listener cancelled")
        except Exception as e:
            logger.error(f"city/create listener error: {e}", exc_info=True)
            raise
    
    # ── Lifecycle ─────────────────────────────────────────────────────────────
    
    async def start(self):
        """Start all WebSocket subscriptions for nation, city, and account events."""
        if self.running:
            logger.warning("NationComponent already running")
            return
        
        self.running = True
        logger.info("Starting NationComponent subscriptions")
        
        self._tasks = [
            asyncio.create_task(self._listen_nation_updates()),
            asyncio.create_task(self._listen_nation_creates()),
            asyncio.create_task(self._listen_account_updates()),
            asyncio.create_task(self._listen_city_updates()),
            asyncio.create_task(self._listen_city_creates()),
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
        """Stop all subscriptions."""
        self.running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        
        # Close pnwkit socket
        await self._close_kit_socket()
        logger.info("NationComponent stopped")
    
    async def run_forever(self):
        """Run subscriptions indefinitely with automatic restart on disconnect/crash."""
        while True:
            try:
                await self.start()
            except asyncio.CancelledError:
                logger.info("NationComponent cancelled")
                break
            except (aiohttp.ClientError, ConnectionResetError, OSError) as e:
                logger.warning(f"NationComponent disconnected ({e}) — restarting in 30s")
            except Exception as e:
                logger.error(f"NationComponent crashed ({e}) — restarting in 30s", exc_info=True)
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

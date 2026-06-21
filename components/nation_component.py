"""
NationComponent — GPP component for nation, city, and alliance event processing.

Sub-components:
- NationEventProcessor: Handles nation/create, nation/update events
- CityEventProcessor: Handles city/create, city/update events
- AllianceEventProcessor: Handles alliance/create, alliance/update events
- SpendingDetector: Detects and records spending (cities, projects, military, upgrades)
- BeigeEarlyExitDetector: Detects early beige exits and enqueues notifications

This component writes to GlobalNationsDB, HoldingsDB, and beige_alerts_db.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

import aiohttp
import pnwkit
from pnwkit.new import QueryKit

from PnWHarvester.core.activity_tracker import ActivityTracker
from PnWHarvester.core.pnwkit_compat import close_querykit, patch_pnwkit

patch_pnwkit()
from .spending_detector import SpendingDetector
from .beige_early_exit_detector import BeigeEarlyExitDetector

logger = logging.getLogger(__name__)

NW_ALLIANCE_ID = 10259


def _obj_to_dict(obj: Any) -> Dict[str, Any]:
    """Convert pnwkit objects to dictionaries."""
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return dict(obj)
    return vars(obj)


class NationEventProcessor:
    """Processes nation/create and nation/update events."""
    
    def __init__(self, global_db, holdings_db=None, news_component=None, nation_cache=None):
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
        self.nation_cache = nation_cache
        self._nw_nation_ids: Set[int] = set()

    async def _claim_news(self, event_type: str, event_id: int) -> bool:
        if not self.holdings_db or not hasattr(self.holdings_db, "claim_processed_event"):
            return True
        return await self.holdings_db.claim_processed_event(event_type, event_id)

    async def _unclaim_news(self, event_type: str, event_id: int) -> None:
        if self.holdings_db and hasattr(self.holdings_db, "unclaim_processed_event"):
            await self.holdings_db.unclaim_processed_event(event_type, event_id)
    
    async def seed_nw_set(self):
        """Seed the in-memory NW set from GlobalNations.db."""
        if not self.global_db:
            return
        try:
            def _work():
                import sqlite3
                with sqlite3.connect(self.global_db.db_path) as conn:
                    rows = conn.execute(
                        "SELECT id FROM nations WHERE alliance_id = ?",
                        (NW_ALLIANCE_ID,),
                    ).fetchall()
                    return {r[0] for r in rows}
            self._nw_nation_ids = await self.global_db._run_sync(_work)
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
    
    async def process_nation_delete(
        self,
        event: Any,
    ) -> Dict[str, Any]:
        """
        Process a nation/delete event.

        The PnW API sends a Nation object for delete events; in practice only
        ``id`` is guaranteed to be populated (the nation no longer exists in
        the game so the API cannot return full data).  We therefore look up the
        nation in our own DB first to capture the name/alliance for the news
        article, then hard-delete the row.

        Returns:
            Processing statistics
        """
        nation_evt = _obj_to_dict(event)
        nation_id = nation_evt.get("id")
        if not nation_id:
            return {"processed": 0, "skipped": 1}

        nation_id_int = int(nation_id)

        # Enrich from the event payload (may have partial data)
        self.extract_alliance(nation_evt)

        # Pull the full snapshot from our DB *before* deleting it so we can
        # include the nation name, alliance, score, cities, etc. in the news
        # article.
        existing: Optional[Dict[str, Any]] = await self.get_existing_nation(nation_id_int)

        # Prefer our DB data; fall back to whatever the event carried
        nation_name: Optional[str]   = (existing or nation_evt).get("nation_name")
        leader_name: Optional[str]   = (existing or nation_evt).get("leader_name")
        nation_flag: Optional[str]   = (existing or nation_evt).get("flag")
        alliance_id: Optional[int]   = None
        alliance_name: Optional[str] = None
        alliance_flag: Optional[str] = None
        num_cities: Optional[int]    = None
        score: Optional[float]       = None

        if existing:
            raw_aid = existing.get("alliance_id")
            alliance_id   = int(raw_aid)   if raw_aid  else None
            alliance_name = existing.get("alliance_name")
            alliance_flag = existing.get("alliance_flag")
            raw_nc        = existing.get("num_cities")
            num_cities    = int(raw_nc)    if raw_nc   else None
            raw_sc        = existing.get("score")
            score         = float(raw_sc)  if raw_sc   else None
        elif nation_evt.get("alliance_id"):
            alliance_id   = int(nation_evt["alliance_id"])
            alliance_name = nation_evt.get("alliance_name")
            alliance_flag = nation_evt.get("alliance_flag")

        # Remove from in-memory NW set if present
        if nation_id_int in self._nw_nation_ids:
            self._nw_nation_ids.discard(nation_id_int)
            logger.info(f"nation/delete → NW nation {nation_id_int} ({nation_name}) removed from NW set")

        # Hard-delete from GlobalNations.db (nations + cities)
        if self.global_db:
            deleted = await self.global_db.delete_nation(nation_id_int)
            if deleted and self.nation_cache:
                self.nation_cache.delete_nation(nation_id_int)

        logger.info(
            f"nation/delete → {nation_id_int} ({nation_name or 'unknown'}) "
            f"alliance={alliance_id} cities={num_cities} score={score}"
        )

        # Fire news article
        if self.news_component and await self._claim_news("nation_deleted_news_generated", nation_id_int):
            try:
                from PnWHarvester.db.news_writer import record_nation_deleted
                recorded = await record_nation_deleted(
                    nation_id=nation_id_int,
                    nation_name=nation_name,
                    leader_name=leader_name,
                    nation_flag=nation_flag,
                    alliance_id=alliance_id,
                    alliance_name=alliance_name,
                    alliance_flag=alliance_flag,
                    num_cities=num_cities,
                    score=score,
                    event_date=self._now_str(),
                )
                if not recorded:
                    await self._unclaim_news("nation_deleted_news_generated", nation_id_int)
            except Exception as _ne:
                await self._unclaim_news("nation_deleted_news_generated", nation_id_int)
                logger.debug(f"news nation_deleted: {_ne}")
        elif self.news_component:
            logger.debug(f"nation/delete news already generated for nation {nation_id_int}")

        return {"processed": 1, "skipped": 0}

    @staticmethod
    def _now_str() -> str:
        """Get current UTC time as string."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

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
                            from PnWHarvester.db.news_writer import record_alliance_change
                            await record_alliance_change(
                                nation_id=nation_id_int,
                                nation_name=nation.get("nation_name"),
                                nation_flag=nation.get("flag"),
                                old_alliance_id=int(old_aid) if old_aid else None,
                                old_alliance_name=old_nation.get("alliance_name"),
                                new_alliance_id=int(new_aid) if new_aid else None,
                                new_alliance_name=nation.get("alliance_name"),
                                new_alliance_flag=nation.get("alliance_flag"),
                                event_date=nation.get("last_active"),
                            )
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
            saved = await self.global_db.save_nation(nation_for_db)
            if saved and self.nation_cache:
                self.nation_cache.upsert_nation(nation_for_db, merge=True)


class CityEventProcessor:
    """Processes city/create and city/update events."""
    
    def __init__(self, global_db, holdings_db=None, news_component=None, nation_cache=None):
        """
        Initialize the city event processor.
        
        Args:
            global_db: GlobalNationsDB instance
            holdings_db: HoldingsDB instance (optional)
        """
        self.global_db = global_db
        self.holdings_db = holdings_db
        self.news_component = news_component
        self.nation_cache = nation_cache

    async def _claim_news(self, event_type: str, event_id: int) -> bool:
        if not self.holdings_db or not hasattr(self.holdings_db, "claim_processed_event"):
            return True
        return await self.holdings_db.claim_processed_event(event_type, event_id)

    async def _unclaim_news(self, event_type: str, event_id: int) -> None:
        if self.holdings_db and hasattr(self.holdings_db, "unclaim_processed_event"):
            await self.holdings_db.unclaim_processed_event(event_type, event_id)
    
    async def get_existing_city(self, city_id: int) -> Optional[Dict[str, Any]]:
        """Get existing city from database."""
        if not self.global_db:
            return None
        try:
            def _work():
                import sqlite3
                with sqlite3.connect(self.global_db.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute(
                        "SELECT * FROM cities WHERE id = ?", (city_id,)
                    ).fetchone()
                    return dict(row) if row else None
            return await self.global_db._run_sync(_work)
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

    async def process_city_delete(self, event: Any) -> Dict[str, Any]:
        """Process a city/delete event."""
        city_evt = _obj_to_dict(event)
        city_id = city_evt.get("id") or city_evt.get("city_id")
        if not city_id:
            return {"processed": 0, "skipped": 1}

        city_id_int = int(city_id)
        existing = await self.get_existing_city(city_id_int)
        city_snapshot: Dict[str, Any] = dict(existing or city_evt)
        nation_id = city_snapshot.get("nation_id") or city_evt.get("nation_id")
        nation_id_int = int(nation_id) if nation_id else None

        nation_data: Optional[Dict[str, Any]] = None
        if nation_id_int:
            nation_data = await self.get_existing_nation(nation_id_int)

        deleted = False
        if self.global_db:
            deleted = await self.global_db.delete_city(city_id_int)
            if deleted and nation_id_int:
                await self.global_db.increment_num_cities(nation_id_int, amount=-1)
                if self.nation_cache:
                    self.nation_cache.delete_city(nation_id_int, city_id_int)
                    self.nation_cache.increment_num_cities(nation_id_int, amount=-1)

        logger.info(
            f"city/delete -> city {city_id_int} "
            f"nation {nation_id_int if nation_id_int else 'unknown'} "
            f"deleted={deleted}"
        )

        if self.news_component and await self._claim_news("city_deleted_news_generated", city_id_int):
            try:
                from PnWHarvester.db.news_writer import record_city_deleted
                recorded = await record_city_deleted(
                    city_id=city_id_int,
                    city_name=city_snapshot.get("name"),
                    nation_id=nation_id_int,
                    nation_name=(nation_data or {}).get("nation_name"),
                    nation_flag=(nation_data or {}).get("flag"),
                    alliance_id=(nation_data or {}).get("alliance_id"),
                    alliance_name=(nation_data or {}).get("alliance_name"),
                    alliance_flag=(nation_data or {}).get("alliance_flag"),
                    old_num_cities=(nation_data or {}).get("num_cities"),
                    infrastructure=city_snapshot.get("infrastructure"),
                    land=city_snapshot.get("land"),
                    event_date=self._now_str(),
                )
                if not recorded:
                    await self._unclaim_news("city_deleted_news_generated", city_id_int)
            except Exception as _ne:
                await self._unclaim_news("city_deleted_news_generated", city_id_int)
                logger.debug(f"news city_deleted: {_ne}")
        elif self.news_component:
            logger.debug(f"city/delete news already generated for city {city_id_int}")

        return {"processed": 1, "skipped": 0}
    
    async def _save_city(self, nation_id: int, city: Dict[str, Any]):
        """Save city to database with spending detection."""
        city_id = city.get("id")
        if not city_id:
            return
        
        is_new_city = False
        old_city = await self.get_existing_city(int(city_id)) if self.global_db else None
        if old_city is None:
            is_new_city = True

        if self.holdings_db and self.global_db:
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
                # New city purchased - detect and deduct cost
                nation_data = await self.get_existing_nation(nation_id)
                if nation_data:
                    from .spending_detector import SpendingDetector
                    detector = SpendingDetector(self.holdings_db)
                    old_num_cities = int(nation_data.get("num_cities") or 0)
                    new_num_cities = old_num_cities + 1
                    await detector.detect_city_purchase(
                        nation_id=nation_id,
                        old_nation=nation_data,
                        new_num_cities=new_num_cities,
                        event_date=self._now_str(),
                    )
        
        if self.global_db:
            saved = await self.global_db.upsert_city(nation_id, city)
            if saved and self.nation_cache:
                self.nation_cache.upsert_city(nation_id, city)
            if saved and is_new_city:
                await self.global_db.increment_num_cities(nation_id)
                if self.nation_cache:
                    self.nation_cache.increment_num_cities(nation_id)
    
    @staticmethod
    def _now_str() -> str:
        """Get current UTC time as string."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class AccountEventProcessor:
    """Processes account/update events."""
    
    def __init__(self, global_db, nation_cache=None):
        """
        Initialize the account event processor.
        
        Args:
            global_db: GlobalNationsDB instance
        """
        self.global_db = global_db
        self.nation_cache = nation_cache
    
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
            saved = await self.global_db.save_nation(patch)
            if saved and self.nation_cache:
                self.nation_cache.upsert_nation(patch, merge=True)
        
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
        websocket_manager=None,
        api_key: str = "",
        nation_cache=None,
    ):
        """
        Initialize the NationComponent.
        
        Args:
            global_db: GlobalNationsDB instance
            holdings_db: HoldingsDB instance
            beige_component: BeigeAlertComponent instance
            news_component: NewsComponent instance
            websocket_manager: SharedWebSocketManager instance
            api_key: PnW API v3 key
            nation_cache: NationCache instance for live nation/city cache updates
        """
        self.global_db = global_db
        self.holdings_db = holdings_db
        self.beige_component = beige_component
        self.news_component = news_component
        self.websocket_manager = websocket_manager
        self.api_key = api_key
        self.nation_cache = nation_cache
        
        # Use shared websocket manager if provided, otherwise fallback to own QueryKit
        if self.websocket_manager:
            self.kit = None  # Will use shared manager's kit
        else:
            self.kit = QueryKit(api_key)
        
        # Initialize sub-components
        self.nation_processor = NationEventProcessor(global_db, holdings_db, news_component, nation_cache)
        self.city_processor = CityEventProcessor(global_db, holdings_db, news_component, nation_cache)
        self.account_processor = AccountEventProcessor(global_db, nation_cache)
        self.beige_detector = BeigeEarlyExitDetector(beige_component)
        
        self.activity_tracker = ActivityTracker(max_silence_seconds=120.0)
        
        self.running = False
        self._tasks: list[asyncio.Task] = []

    async def _claim_news(self, event_type: str, event_id: int) -> bool:
        if not self.holdings_db or not hasattr(self.holdings_db, "claim_processed_event"):
            return True
        return await self.holdings_db.claim_processed_event(event_type, event_id)

    async def _unclaim_news(self, event_type: str, event_id: int) -> None:
        if self.holdings_db and hasattr(self.holdings_db, "unclaim_processed_event"):
            await self.holdings_db.unclaim_processed_event(event_type, event_id)
    
    async def initialize(self):
        """Initialize the component (seed NW set, etc.)."""
        # Register subscriptions for activity tracking
        self.activity_tracker.register_subscription("nation/create")
        self.activity_tracker.register_subscription("nation/update")
        self.activity_tracker.register_subscription("nation/delete")
        self.activity_tracker.register_subscription("city/create")
        self.activity_tracker.register_subscription("city/update")
        self.activity_tracker.register_subscription("city/delete")
        self.activity_tracker.register_subscription("account/update")
        self.activity_tracker.register_subscription("alliance/create")
        self.activity_tracker.register_subscription("alliance/update")
        self.activity_tracker.register_subscription("alliance/delete")
        
        await self.nation_processor.seed_nw_set()
        logger.info("NationComponent initialized")
    
    async def process_nation_update(self, event: Any) -> Dict[str, Any]:
        """Process a nation/update event."""
        # Fetch old_nation BEFORE saving so beige_detector sees the pre-update state.
        nation = _obj_to_dict(event)
        nation_id = nation.get("id")
        old_nation = await self.nation_processor.get_existing_nation(int(nation_id)) if nation_id else None
        
        stats = await self.nation_processor.process_nation_event(event, "update")
        
        # Check for beige early exit using the pre-save snapshot
        await self.beige_detector.check_early_exit(nation, old_nation)
        
        return stats
    
    async def process_nation_create(self, event: Any) -> Dict[str, Any]:
        """Process a nation/create event."""
        return await self.nation_processor.process_nation_event(event, "create")

    async def process_nation_delete(self, event: Any) -> Dict[str, Any]:
        """Process a nation/delete event — removes the nation from GlobalNations.db and writes a news article."""
        return await self.nation_processor.process_nation_delete(event)

    async def process_city_update(self, event: Any) -> Dict[str, Any]:
        """Process a city/update event."""
        return await self.city_processor.process_city_event(event, "update")
    
    async def process_city_create(self, event: Any) -> Dict[str, Any]:
        """Process a city/create event."""
        return await self.city_processor.process_city_event(event, "create")

    async def process_city_delete(self, event: Any) -> Dict[str, Any]:
        """Process a city/delete event."""
        return await self.city_processor.process_city_delete(event)
    
    async def process_account_update(self, event: Any) -> Dict[str, Any]:
        """Process an account/update event."""
        return await self.account_processor.process_account_event(event)
    
    async def process_alliance_create(self, event: Any) -> Dict[str, Any]:
        """Process an alliance/create event."""
        alliance = _obj_to_dict(event)
        alliance_id = alliance.get("id")
        alliance_name = alliance.get("name")
        
        logger.info(f"alliance/create → {alliance_id} ({alliance_name})")
        
        # Update alliance info in nations that belong to this alliance
        if self.global_db and alliance_id:
            try:
                # Alliance creation doesn't require immediate action
                # Nations will update their alliance info via nation/update
                pass
            except Exception as e:
                logger.error(f"Error processing alliance/create: {e}", exc_info=True)
        
        return {"processed": 1, "skipped": 0}
    
    async def process_alliance_update(self, event: Any) -> Dict[str, Any]:
        """Process an alliance/update event."""
        alliance = _obj_to_dict(event)
        alliance_id = alliance.get("id")
        alliance_name = alliance.get("name")
        
        logger.info(f"alliance/update → {alliance_id} ({alliance_name})")
        
        # Update alliance name/flag for all nations in this alliance
        if self.global_db and alliance_id:
            try:
                updated = await self.global_db.update_alliance_info(
                    alliance_id=alliance_id,
                    alliance_name=alliance.get("name"),
                    alliance_flag=alliance.get("flag"),
                )
                if updated and self.nation_cache:
                    self.nation_cache.update_alliance_info(
                        alliance_id=alliance_id,
                        alliance_name=alliance.get("name"),
                        alliance_flag=alliance.get("flag"),
                    )
            except Exception as e:
                logger.error(f"Error processing alliance/update: {e}", exc_info=True)
        
        return {"processed": 1, "skipped": 0}

    async def process_alliance_delete(self, event: Any) -> Dict[str, Any]:
        """Process an alliance/delete event."""
        alliance = _obj_to_dict(event)
        alliance_id = alliance.get("id")
        if not alliance_id:
            return {"processed": 0, "skipped": 1}

        alliance_id_int = int(alliance_id)
        snapshot: Dict[str, Any] = {}
        if self.global_db:
            snapshot = await self.global_db.get_alliance_snapshot(alliance_id_int)

        alliance_name = alliance.get("name") or snapshot.get("alliance_name")
        alliance_flag = alliance.get("flag") or snapshot.get("alliance_flag")
        member_count = int(snapshot.get("member_count") or 0)
        city_count = int(snapshot.get("city_count") or 0)
        score_total = float(snapshot.get("score_total") or 0.0)

        cleared = 0
        if self.global_db:
            cleared = await self.global_db.clear_alliance_info(alliance_id_int)
            if cleared and self.nation_cache:
                self.nation_cache.clear_alliance_info(alliance_id_int)

        logger.info(
            f"alliance/delete -> {alliance_id_int} ({alliance_name or 'unknown'}) "
            f"members={member_count} cleared={cleared}"
        )

        if self.news_component and await self._claim_news("alliance_deleted_news_generated", alliance_id_int):
            try:
                from PnWHarvester.db.news_writer import record_alliance_deleted
                recorded = await record_alliance_deleted(
                    alliance_id=alliance_id_int,
                    alliance_name=alliance_name,
                    alliance_flag=alliance_flag,
                    member_count=member_count,
                    city_count=city_count,
                    score_total=score_total,
                    cleared_nations=cleared,
                    event_date=self._now_str(),
                )
                if not recorded:
                    await self._unclaim_news("alliance_deleted_news_generated", alliance_id_int)
            except Exception as _ne:
                await self._unclaim_news("alliance_deleted_news_generated", alliance_id_int)
                logger.debug(f"news alliance_deleted: {_ne}")
        elif self.news_component:
            logger.debug(f"alliance/delete news already generated for alliance {alliance_id_int}")

        return {"processed": 1, "skipped": 0}
    
    async def get_component_stats(self) -> Dict[str, Any]:
        """Get component statistics."""
        return {
            "type": "NationComponent",
            "nw_nation_count": len(self.nation_processor._nw_nation_ids),
            "global_db_path": self.global_db.db_path if self.global_db else None,
            "holdings_db_path": self.holdings_db.db_path if self.holdings_db else None,
            "running": self.running,
            "activity": self.activity_tracker.to_dict(),
        }

    @staticmethod
    def _now_str() -> str:
        """Get current UTC time as string."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    # ── WebSocket subscription listeners ───────────────────────────────────────
    
    async def _park_optional_subscription(self, subscription_name: str, exc: Exception) -> None:
        """
        Keep fallback mode alive when PnW refuses an optional channel.

        In shared-manager mode optional subscription failures are handled by
        SharedWebSocketManager. This helper prevents the legacy/fallback
        listener task from completing and causing the component to restart all
        working subscriptions.
        """
        logger.warning(
            "Optional subscription unavailable and disabled: %s (%s: %s)",
            subscription_name,
            type(exc).__name__,
            exc,
        )
        while self.running:
            await asyncio.sleep(60)

    async def _listen_nation_updates(self):
        """Listen for nation/update events."""
        subscription_name = "nation/update"
        try:
            subscription = await self.kit.subscribe("nation", "update")
            logger.info("nation/update subscription active (all nations → GlobalNations.db)")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    self.activity_tracker.record_message(subscription_name)
                    await self.process_nation_update(event)
                except Exception as e:
                    self.activity_tracker.record_error(subscription_name)
                    logger.error(f"Error processing nation/update event: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("nation/update listener cancelled")
        except pnwkit.errors.SubscribeError as e:
            self.activity_tracker.record_error(subscription_name)
            logger.warning(f"nation/update subscription error: {e} — will restart")
            raise
        except Exception as e:
            self.activity_tracker.record_error(subscription_name)
            logger.error(f"nation/update listener error: {e}", exc_info=True)
            raise
    
    async def _listen_nation_creates(self):
        """Listen for nation/create events."""
        subscription_name = "nation/create"
        try:
            subscription = await self.kit.subscribe("nation", "create")
            logger.info("nation/create subscription active (all nations → GlobalNations.db)")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    self.activity_tracker.record_message(subscription_name)
                    await self.process_nation_create(event)
                except Exception as e:
                    self.activity_tracker.record_error(subscription_name)
                    logger.error(f"Error processing nation/create event: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("nation/create listener cancelled")
        except pnwkit.errors.SubscribeError as e:
            self.activity_tracker.record_error(subscription_name)
            logger.warning(f"nation/create subscription error: {e} — will restart")
            raise
        except Exception as e:
            self.activity_tracker.record_error(subscription_name)
            logger.error(f"nation/create listener error: {e}", exc_info=True)
            raise

    async def _listen_nation_deletes(self):
        """Listen for nation/delete events — fires when a nation is deleted in-game."""
        subscription_name = "nation/delete"
        try:
            subscription = await self.kit.subscribe("nation", "delete")
            logger.info("nation/delete subscription active (deleted nations → GlobalNations.db removal)")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    self.activity_tracker.record_message(subscription_name)
                    await self.process_nation_delete(event)
                except Exception as e:
                    self.activity_tracker.record_error(subscription_name)
                    logger.error(f"Error processing nation/delete event: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("nation/delete listener cancelled")
        except pnwkit.errors.SubscribeError as e:
            self.activity_tracker.record_error(subscription_name)
            logger.warning(f"nation/delete subscription error: {e} — will restart")
            raise
        except Exception as e:
            self.activity_tracker.record_error(subscription_name)
            logger.error(f"nation/delete listener error: {e}", exc_info=True)
            raise
    
    async def _listen_account_updates(self):
        """Listen for account/update events."""
        subscription_name = "account/update"
        try:
            subscription = await self.kit.subscribe("account", "update")
            logger.info("account/update subscription active")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    self.activity_tracker.record_message(subscription_name)
                    await self.process_account_update(event)
                except Exception as e:
                    self.activity_tracker.record_error(subscription_name)
                    logger.error(f"Error processing account/update event: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("account/update listener cancelled")
        except pnwkit.errors.SubscribeError as e:
            self.activity_tracker.record_error(subscription_name)
            logger.warning(f"account/update subscription error: {e} — will restart")
            raise
        except Exception as e:
            self.activity_tracker.record_error(subscription_name)
            logger.error(f"account/update listener error: {e}", exc_info=True)
            raise
    
    async def _listen_city_updates(self):
        """Listen for city/update events."""
        subscription_name = "city/update"
        try:
            subscription = await self.kit.subscribe("city", "update")
            logger.info("city/update subscription active (all cities → GlobalNations.db)")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    self.activity_tracker.record_message(subscription_name)
                    await self.process_city_update(event)
                except Exception as e:
                    self.activity_tracker.record_error(subscription_name)
                    logger.error(f"Error processing city/update event: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("city/update listener cancelled")
        except pnwkit.errors.SubscribeError as e:
            self.activity_tracker.record_error(subscription_name)
            logger.warning(f"city/update subscription error: {e} — will restart")
            raise
        except Exception as e:
            self.activity_tracker.record_error(subscription_name)
            logger.error(f"city/update listener error: {e}", exc_info=True)
            raise
    
    async def _listen_city_creates(self):
        """Listen for city/create events."""
        subscription_name = "city/create"
        try:
            subscription = await self.kit.subscribe("city", "create")
            logger.info("city/create subscription active (all cities → GlobalNations.db)")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    self.activity_tracker.record_message(subscription_name)
                    await self.process_city_create(event)
                except Exception as e:
                    self.activity_tracker.record_error(subscription_name)
                    logger.error(f"Error processing city/create event: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("city/create listener cancelled")
        except pnwkit.errors.SubscribeError as e:
            self.activity_tracker.record_error(subscription_name)
            logger.warning(f"city/create subscription error: {e} — will restart")
            raise
        except Exception as e:
            self.activity_tracker.record_error(subscription_name)
            logger.error(f"city/create listener error: {e}", exc_info=True)
            raise

    async def _listen_city_deletes(self):
        """Listen for city/delete events."""
        subscription_name = "city/delete"
        try:
            subscription = await self.kit.subscribe("city", "delete")
            logger.info("city/delete subscription active (deleted cities -> GlobalNations.db removal)")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    self.activity_tracker.record_message(subscription_name)
                    await self.process_city_delete(event)
                except Exception as e:
                    self.activity_tracker.record_error(subscription_name)
                    logger.error(f"Error processing city/delete event: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("city/delete listener cancelled")
        except pnwkit.errors.Unauthorized as e:
            await self._park_optional_subscription(subscription_name, e)
        except pnwkit.errors.SubscribeError as e:
            await self._park_optional_subscription(subscription_name, e)
        except Exception as e:
            self.activity_tracker.record_error(subscription_name)
            logger.error(f"city/delete listener error: {e}", exc_info=True)
            raise
    
    async def _listen_alliance_creates(self):
        """Listen for alliance/create events."""
        subscription_name = "alliance/create"
        try:
            subscription = await self.kit.subscribe("alliance", "create")
            logger.info("alliance/create subscription active")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    self.activity_tracker.record_message(subscription_name)
                    await self.process_alliance_create(event)
                except Exception as e:
                    self.activity_tracker.record_error(subscription_name)
                    logger.error(f"Error processing alliance/create event: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("alliance/create listener cancelled")
        except pnwkit.errors.Unauthorized as e:
            await self._park_optional_subscription(subscription_name, e)
        except pnwkit.errors.SubscribeError as e:
            await self._park_optional_subscription(subscription_name, e)
        except Exception as e:
            self.activity_tracker.record_error(subscription_name)
            logger.error(f"alliance/create listener error: {e}", exc_info=True)
            raise
    
    async def _listen_alliance_updates(self):
        """Listen for alliance/update events."""
        subscription_name = "alliance/update"
        try:
            subscription = await self.kit.subscribe("alliance", "update")
            logger.info("alliance/update subscription active")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    self.activity_tracker.record_message(subscription_name)
                    await self.process_alliance_update(event)
                except Exception as e:
                    self.activity_tracker.record_error(subscription_name)
                    logger.error(f"Error processing alliance/update event: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("alliance/update listener cancelled")
        except pnwkit.errors.Unauthorized as e:
            await self._park_optional_subscription(subscription_name, e)
        except pnwkit.errors.SubscribeError as e:
            await self._park_optional_subscription(subscription_name, e)
        except Exception as e:
            self.activity_tracker.record_error(subscription_name)
            logger.error(f"alliance/update listener error: {e}", exc_info=True)
            raise

    async def _listen_alliance_deletes(self):
        """Listen for alliance/delete events."""
        subscription_name = "alliance/delete"
        try:
            subscription = await self.kit.subscribe("alliance", "delete")
            logger.info("alliance/delete subscription active")

            async for event in subscription:
                if not self.running:
                    break
                try:
                    self.activity_tracker.record_message(subscription_name)
                    await self.process_alliance_delete(event)
                except Exception as e:
                    self.activity_tracker.record_error(subscription_name)
                    logger.error(f"Error processing alliance/delete event: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("alliance/delete listener cancelled")
        except pnwkit.errors.Unauthorized as e:
            await self._park_optional_subscription(subscription_name, e)
        except pnwkit.errors.SubscribeError as e:
            await self._park_optional_subscription(subscription_name, e)
        except Exception as e:
            self.activity_tracker.record_error(subscription_name)
            logger.error(f"alliance/delete listener error: {e}", exc_info=True)
            raise
    
    # ── Lifecycle ─────────────────────────────────────────────────────────────
    
    async def start(self):
        """Start all WebSocket subscriptions for nation, city, account, and alliance events."""
        if self.running:
            logger.warning("NationComponent already running")
            return

        self.running = True
        
        # Use SharedWebSocketManager if available, otherwise use own QueryKit
        if self.websocket_manager:
            # Register subscriptions with shared manager
            await self.websocket_manager.subscribe(
                "nation", "update", {},
                self.process_nation_update
            )
            await self.websocket_manager.subscribe(
                "nation", "create", {},
                self.process_nation_create
            )
            await self.websocket_manager.subscribe(
                "nation", "delete", {},
                self.process_nation_delete
            )
            await self.websocket_manager.subscribe(
                "city", "update", {},
                self.process_city_update
            )
            await self.websocket_manager.subscribe(
                "city", "create", {},
                self.process_city_create
            )
            await self.websocket_manager.subscribe(
                "city", "delete", {},
                self.process_city_delete,
                required=False,
            )
            await self.websocket_manager.subscribe(
                "account", "update", {},
                self.process_account_update,
                required=False,
            )
            await self.websocket_manager.subscribe(
                "alliance", "create", {},
                self.process_alliance_create,
                required=False,
            )
            await self.websocket_manager.subscribe(
                "alliance", "update", {},
                self.process_alliance_update,
                required=False,
            )
            await self.websocket_manager.subscribe(
                "alliance", "delete", {},
                self.process_alliance_delete,
                required=False,
            )
            logger.info("NationComponent started (using SharedWebSocketManager)")
            
            # Keep running until stopped
            while self.running:
                await asyncio.sleep(1)
        else:
            # Fallback to own QueryKit
            self.kit = QueryKit(self.api_key)
            logger.info("Starting NationComponent subscriptions")
            
            self._tasks = [
                asyncio.create_task(self._listen_nation_updates()),
                asyncio.create_task(self._listen_nation_creates()),
                asyncio.create_task(self._listen_nation_deletes()),
                asyncio.create_task(self._listen_account_updates()),
                asyncio.create_task(self._listen_city_updates()),
                asyncio.create_task(self._listen_city_creates()),
                asyncio.create_task(self._listen_city_deletes()),
                asyncio.create_task(self._listen_alliance_creates()),
                asyncio.create_task(self._listen_alliance_updates()),
                asyncio.create_task(self._listen_alliance_deletes()),
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
                logger.info("NationComponent cancelled")
                break
            except (aiohttp.ClientError, ConnectionResetError, OSError, ConnectionError, pnwkit.errors.SubscribeError) as e:
                retry_count += 1
                # Exponential backoff with jitter
                delay = min(base_delay * (2 ** min(retry_count - 1, 5)), max_retry_delay)
                # Add jitter to prevent thundering herd
                import random
                jitter = random.uniform(0.8, 1.2)
                actual_delay = delay * jitter
                
                logger.warning(f"NationComponent disconnected ({e}) — retry {retry_count}, restarting in {actual_delay:.1f}s")
            except Exception as e:
                retry_count += 1
                delay = min(base_delay * (2 ** min(retry_count - 1, 5)), max_retry_delay)
                import random
                jitter = random.uniform(0.8, 1.2)
                actual_delay = delay * jitter
                
                logger.error(f"NationComponent crashed ({e}) — retry {retry_count}, restarting in {actual_delay:.1f}s", exc_info=True)
            finally:
                self.running = False
                await self.stop()
            
            await asyncio.sleep(actual_delay)
    
    async def _close_kit_socket(self):
        """Close the pnwkit socket to avoid pending task warnings."""
        await close_querykit(getattr(self, "kit", None))
        self.kit = None

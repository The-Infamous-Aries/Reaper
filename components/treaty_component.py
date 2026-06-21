"""
TreatyComponent — GPP component for treaty event processing.

Handles:
- treaty/create  → save to TreatiesDB + news (treaty signed)
- treaty/update  → save to TreatiesDB + news (treaty updated)
- treaty/delete  → mark inactive in TreatiesDB + news (treaty cancelled)

Monitored by the GPPManager health check (ActivityTracker).
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import pnwkit
from pnwkit.new import QueryKit

from PnWHarvester.core.activity_tracker import ActivityTracker
from PnWHarvester.core.pnwkit_compat import close_querykit, patch_pnwkit

patch_pnwkit()

logger = logging.getLogger(__name__)

NW_ALLIANCE_ID = 10259


def _obj_to_dict(obj: Any) -> Dict[str, Any]:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return dict(obj)
    return vars(obj)


def _nested_alliance(treaty: Dict[str, Any], key: str) -> Dict[str, Any]:
    """Extract nested alliance dict safely."""
    val = treaty.get(key)
    if isinstance(val, dict):
        return val
    if val is not None and hasattr(val, "to_dict"):
        return val.to_dict()
    return {}


def _get_alliance_fields(treaty: Dict[str, Any]) -> Dict[str, Any]:
    """Pull flat + nested alliance fields out of a raw treaty dict."""
    a1 = _nested_alliance(treaty, "alliance1")
    a2 = _nested_alliance(treaty, "alliance2")

    def _int(v: Any) -> Optional[int]:
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    def _str(v: Any) -> Optional[str]:
        return str(v) if v is not None else None

    return {
        "alliance1_id":   _int(treaty.get("alliance1_id") or a1.get("id")),
        "alliance1_name": _str(treaty.get("alliance1_name") or a1.get("name")),
        "alliance1_flag": _str(treaty.get("alliance1_flag") or a1.get("flag")),
        "alliance2_id":   _int(treaty.get("alliance2_id") or a2.get("id")),
        "alliance2_name": _str(treaty.get("alliance2_name") or a2.get("name")),
        "alliance2_flag": _str(treaty.get("alliance2_flag") or a2.get("flag")),
    }


def _event_date(treaty: Dict[str, Any]) -> Optional[str]:
    d = treaty.get("date")
    if d is None:
        return None
    if hasattr(d, "isoformat"):
        return d.isoformat()
    return str(d)


class TreatyEventProcessor:
    """Processes treaty/create, treaty/update, treaty/delete events."""

    def __init__(self, treaties_db, news_component=None, holdings_db=None):
        self.treaties_db = treaties_db
        self.news_component = news_component
        self.holdings_db = holdings_db
        self.stats = {
            "creates_received": 0,
            "updates_received": 0,
            "deletes_received": 0,
            "news_generated": 0,
            "news_failed": 0,
            "news_skipped_claimed": 0,
            "news_skipped_no_component": 0,
        }

    async def _claim(self, event_type: str, treaty_id: int) -> bool:
        if not self.holdings_db or not hasattr(self.holdings_db, "claim_processed_event"):
            return True
        return await self.holdings_db.claim_processed_event(event_type, treaty_id)

    async def _unclaim(self, event_type: str, treaty_id: int) -> None:
        if self.holdings_db and hasattr(self.holdings_db, "unclaim_processed_event"):
            await self.holdings_db.unclaim_processed_event(event_type, treaty_id)

    async def process_create(self, event: Any) -> Dict[str, Any]:
        self.stats["creates_received"] += 1
        treaty = _obj_to_dict(event)
        tid = treaty.get("id")
        if not tid:
            logger.warning("treaty/create skipped: missing id in event payload %r", treaty)
            return {"processed": 0, "skipped": 1}

        af = _get_alliance_fields(treaty)
        treaty_type = str(treaty.get("treaty_type") or "Unknown")
        treaty_url  = treaty.get("treaty_url") or None
        edate       = _event_date(treaty)

        logger.debug(
            f"treaty/create id={tid} type={treaty_type} "
            f"a1={af['alliance1_name']}({af['alliance1_id']}) "
            f"a2={af['alliance2_name']}({af['alliance2_id']})"
        )

        if self.treaties_db:
            await self.treaties_db.save_treaty({**treaty, **af})

        if self.news_component:
            claimed = await self._claim("treaty_signed_news_generated", int(tid))
            if not claimed:
                self.stats["news_skipped_claimed"] += 1
                logger.info(f"treaty/create id={tid} news already claimed, skipping")
            else:
                try:
                    from PnWHarvester.db import news_writer as nw
                    recorded = await nw.record_treaty_signed(
                        treaty_id=int(tid),
                        treaty_type=treaty_type,
                        treaty_url=treaty_url,
                        alliance1_id=af["alliance1_id"],
                        alliance1_name=af["alliance1_name"],
                        alliance1_flag=af["alliance1_flag"],
                        alliance2_id=af["alliance2_id"],
                        alliance2_name=af["alliance2_name"],
                        alliance2_flag=af["alliance2_flag"],
                        event_date=edate,
                    )
                    if recorded:
                        self.stats["news_generated"] += 1
                        logger.info(f"treaty/create id={tid} news article generated")
                    else:
                        self.stats["news_failed"] += 1
                        await self._unclaim("treaty_signed_news_generated", int(tid))
                        logger.error(f"treaty/create id={tid} news recording returned False")
                except Exception as e:
                    self.stats["news_failed"] += 1
                    await self._unclaim("treaty_signed_news_generated", int(tid))
                    logger.error(f"treaty/create id={tid} news failed: {e}", exc_info=True)
        else:
            self.stats["news_skipped_no_component"] += 1
            logger.warning(f"treaty/create id={tid} news skipped: news_component is None")

        return {"processed": 1, "skipped": 0}

    async def process_update(self, event: Any) -> Dict[str, Any]:
        self.stats["updates_received"] += 1
        treaty = _obj_to_dict(event)
        tid = treaty.get("id")
        if not tid:
            logger.warning("treaty/update skipped: missing id in event payload %r", treaty)
            return {"processed": 0, "skipped": 1}

        af = _get_alliance_fields(treaty)
        treaty_type = str(treaty.get("treaty_type") or "Unknown")

        if self.treaties_db:
            await self.treaties_db.save_treaty({**treaty, **af})

        if self.news_component:
            claimed = await self._claim("treaty_updated_news_generated", int(tid))
            if not claimed:
                self.stats["news_skipped_claimed"] += 1
                logger.info(f"treaty/update id={tid} news already claimed, skipping")
            else:
                try:
                    from PnWHarvester.db import news_writer as nw
                    recorded = await nw.record_treaty_signed(
                        treaty_id=int(tid),
                        treaty_type=treaty_type,
                        treaty_url=treaty.get("treaty_url") or None,
                        alliance1_id=af["alliance1_id"],
                        alliance1_name=af["alliance1_name"],
                        alliance1_flag=af["alliance1_flag"],
                        alliance2_id=af["alliance2_id"],
                        alliance2_name=af["alliance2_name"],
                        alliance2_flag=af["alliance2_flag"],
                        event_date=_event_date(treaty),
                    )
                    if recorded:
                        self.stats["news_generated"] += 1
                        logger.info(f"treaty/update id={tid} news article generated")
                    else:
                        self.stats["news_failed"] += 1
                        await self._unclaim("treaty_updated_news_generated", int(tid))
                        logger.error(f"treaty/update id={tid} news recording returned False")
                except Exception as e:
                    self.stats["news_failed"] += 1
                    await self._unclaim("treaty_updated_news_generated", int(tid))
                    logger.error(f"treaty/update id={tid} news failed: {e}", exc_info=True)
        else:
            self.stats["news_skipped_no_component"] += 1
            logger.warning(f"treaty/update id={tid} news skipped: news_component is None")

        return {"processed": 1, "skipped": 0}

    async def process_delete(self, event: Any) -> Dict[str, Any]:
        self.stats["deletes_received"] += 1
        treaty = _obj_to_dict(event)
        tid = treaty.get("id")
        if not tid:
            logger.warning("treaty/delete skipped: missing id in event payload %r", treaty)
            return {"processed": 0, "skipped": 1}

        af = _get_alliance_fields(treaty)
        treaty_type = str(treaty.get("treaty_type") or "Unknown")
        edate       = _event_date(treaty)

        logger.debug(
            f"treaty/delete id={tid} type={treaty_type} "
            f"a1={af['alliance1_name']}({af['alliance1_id']}) "
            f"a2={af['alliance2_name']}({af['alliance2_id']})"
        )

        if self.treaties_db:
            await self.treaties_db.delete_treaty(int(tid))

        if self.news_component:
            claimed = await self._claim("treaty_cancelled_news_generated", int(tid))
            if not claimed:
                self.stats["news_skipped_claimed"] += 1
                logger.info(f"treaty/delete id={tid} news already claimed, skipping")
            else:
                try:
                    from PnWHarvester.db import news_writer as nw
                    recorded = await nw.record_treaty_cancelled(
                        treaty_id=int(tid),
                        treaty_type=treaty_type,
                        alliance1_id=af["alliance1_id"],
                        alliance1_name=af["alliance1_name"],
                        alliance1_flag=af["alliance1_flag"],
                        alliance2_id=af["alliance2_id"],
                        alliance2_name=af["alliance2_name"],
                        alliance2_flag=af["alliance2_flag"],
                        event_date=edate,
                    )
                    if recorded:
                        self.stats["news_generated"] += 1
                        logger.info(f"treaty/delete id={tid} news article generated")
                    else:
                        self.stats["news_failed"] += 1
                        await self._unclaim("treaty_cancelled_news_generated", int(tid))
                        logger.error(f"treaty/delete id={tid} news recording returned False")
                except Exception as e:
                    self.stats["news_failed"] += 1
                    await self._unclaim("treaty_cancelled_news_generated", int(tid))
                    logger.error(f"treaty/delete id={tid} news failed: {e}", exc_info=True)
        else:
            self.stats["news_skipped_no_component"] += 1
            logger.warning(f"treaty/delete id={tid} news skipped: news_component is None")

        return {"processed": 1, "skipped": 0}


class TreatyComponent:
    """
    GPP component for treaty event processing.

    Subscribes to treaty/create, treaty/update, and treaty/delete.
    Monitored by the GPPManager health check via ActivityTracker.
    """

    def __init__(
        self,
        treaties_db,
        news_component=None,
        holdings_db=None,
        websocket_manager=None,
        api_key: str = "",
    ):
        self.treaties_db = treaties_db
        self.news_component = news_component
        self.holdings_db = holdings_db
        self.websocket_manager = websocket_manager
        self.api_key = api_key
        
        # Use shared websocket manager if provided, otherwise fallback to own QueryKit
        if self.websocket_manager:
            self.kit = None  # Will use shared manager's kit
        else:
            self.kit = QueryKit(api_key)

        self.processor = TreatyEventProcessor(treaties_db, news_component, holdings_db)

        # Treaties change much less frequently than other game data (nations, wars, etc.)
        # Set a very long silence timeout to prevent unnecessary restarts
        self.activity_tracker = ActivityTracker(max_silence_seconds=86400.0)  # 24 hours
        self.processor.activity_tracker = self.activity_tracker

        self.running = False
        self._tasks: list[asyncio.Task] = []

    async def initialize(self):
        # Register subscriptions for activity tracking
        self.activity_tracker.register_subscription("treaty/create")
        self.activity_tracker.register_subscription("treaty/update")
        self.activity_tracker.register_subscription("treaty/delete")
        logger.info("TreatyComponent initialized")

    async def get_component_stats(self) -> Dict[str, Any]:
        stats: Dict[str, Any] = {
            "type": "TreatyComponent",
            "running": self.running,
            "processor_stats": dict(self.processor.stats),
        }
        if self.activity_tracker:
            stats["subscription_health"] = self.activity_tracker.to_dict()
        if self.treaties_db:
            stats["db_stats"] = self.treaties_db.get_stats()
        return stats

    # ── Subscription listeners ────────────────────────────────────────────────

    async def _listen_treaty_create(self):
        sub_name = "treaty/create"
        try:
            subscription = await self.kit.subscribe("treaty", "create")
            logger.info("treaty/create subscription active")
            async for event in subscription:
                if not self.running:
                    break
                try:
                    self.activity_tracker.record_message(sub_name)
                    await self.processor.process_create(event)
                except Exception as e:
                    self.activity_tracker.record_error(sub_name)
                    logger.error(f"Error processing treaty/create: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("treaty/create listener cancelled")
        except pnwkit.errors.SubscribeError as e:
            self.activity_tracker.record_error(sub_name)
            logger.warning(f"treaty/create subscription error: {e} — will restart")
            raise
        except Exception as e:
            self.activity_tracker.record_error(sub_name)
            logger.error(f"treaty/create listener error: {e}", exc_info=True)
            raise

    async def _listen_treaty_update(self):
        sub_name = "treaty/update"
        try:
            subscription = await self.kit.subscribe("treaty", "update")
            logger.info("treaty/update subscription active")
            async for event in subscription:
                if not self.running:
                    break
                try:
                    self.activity_tracker.record_message(sub_name)
                    await self.processor.process_update(event)
                except Exception as e:
                    self.activity_tracker.record_error(sub_name)
                    logger.error(f"Error processing treaty/update: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("treaty/update listener cancelled")
        except pnwkit.errors.SubscribeError as e:
            self.activity_tracker.record_error(sub_name)
            logger.warning(f"treaty/update subscription error: {e} — will restart")
            raise
        except Exception as e:
            self.activity_tracker.record_error(sub_name)
            logger.error(f"treaty/update listener error: {e}", exc_info=True)
            raise

    async def _listen_treaty_delete(self):
        sub_name = "treaty/delete"
        try:
            subscription = await self.kit.subscribe("treaty", "delete")
            logger.info("treaty/delete subscription active")
            async for event in subscription:
                if not self.running:
                    break
                try:
                    self.activity_tracker.record_message(sub_name)
                    await self.processor.process_delete(event)
                except Exception as e:
                    self.activity_tracker.record_error(sub_name)
                    logger.error(f"Error processing treaty/delete: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("treaty/delete listener cancelled")
        except pnwkit.errors.SubscribeError as e:
            self.activity_tracker.record_error(sub_name)
            logger.warning(f"treaty/delete subscription error: {e} — will restart")
            raise
        except Exception as e:
            self.activity_tracker.record_error(sub_name)
            logger.error(f"treaty/delete listener error: {e}", exc_info=True)
            raise

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self):
        if self.running:
            logger.warning("TreatyComponent already running")
            return

        self.running = True
        
        # Use SharedWebSocketManager if available, otherwise use own QueryKit
        if self.websocket_manager:
            # Register subscriptions with shared manager
            logger.info("TreatyComponent registering treaty subscriptions with SharedWebSocketManager...")
            ws_state = getattr(self.websocket_manager, "connection_state", None)
            logger.info(f"TreatyComponent: websocket_manager state={ws_state}")
            
            await self.websocket_manager.subscribe(
                "treaty", "create", {},
                self.processor.process_create
            )
            await self.websocket_manager.subscribe(
                "treaty", "update", {},
                self.processor.process_update
            )
            await self.websocket_manager.subscribe(
                "treaty", "delete", {},
                self.processor.process_delete
            )
            
            # Check if subscriptions were registered
            ws_subs = getattr(self.websocket_manager, "subscriptions", {})
            for key in ("treaty/create", "treaty/update", "treaty/delete"):
                sub = ws_subs.get(key)
                if sub:
                    logger.info(f"TreatyComponent: {key} subscribed (active={sub.active})")
                else:
                    logger.warning(f"TreatyComponent: {key} NOT found in websocket_manager subscriptions!")
            
            logger.info("TreatyComponent started (using SharedWebSocketManager)")
            
            # Keep running until stopped
            while self.running:
                await asyncio.sleep(1)
        else:
            # Fallback to own QueryKit
            self.kit = QueryKit(self.api_key)
            self._tasks = [
                asyncio.create_task(self._listen_treaty_create(), name="treaty_create"),
                asyncio.create_task(self._listen_treaty_update(), name="treaty_update"),
                asyncio.create_task(self._listen_treaty_delete(), name="treaty_delete"),
            ]
            logger.info("TreatyComponent started (using own QueryKit)")

    async def stop(self):
        self.running = False
        for t in self._tasks:
            if not t.done():
                t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        await self._close_kit_socket()
        logger.info("TreatyComponent stopped")

    async def _close_kit_socket(self):
        await close_querykit(getattr(self, "kit", None))
        self.kit = None

    async def run_forever(self):
        """Run with auto-restart on disconnect — called by GPPManager."""
        retry = 0
        base_delay = 10.0
        max_delay  = 300.0
        actual_delay = base_delay  # ensure defined before first loop iteration

        while True:
            try:
                await self.start()
                if self._tasks:
                    done, pending = await asyncio.wait(
                        self._tasks,
                        return_when=asyncio.FIRST_EXCEPTION,
                    )
                    for t in done:
                        exc = t.exception() if not t.cancelled() else None
                        if exc:
                            raise exc
                retry = 0
                actual_delay = base_delay
            except asyncio.CancelledError:
                logger.info("TreatyComponent cancelled")
                break
            except Exception as e:
                actual_delay = min(base_delay * (2 ** retry), max_delay)
                retry += 1
                logger.warning(
                    f"TreatyComponent disconnected ({e}) — "
                    f"retry {retry}, restarting in {actual_delay:.1f}s"
                )
            finally:
                await self.stop()

            await asyncio.sleep(actual_delay)

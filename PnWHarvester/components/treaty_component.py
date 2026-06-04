"""
TreatyComponent — GPP component for treaty event processing.

Handles:
- treaty/create  → save to TreatiesDB + news (treaty signed)
- treaty/update  → upsert to TreatiesDB (treaty type / URL change, no news)
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

    def __init__(self, treaties_db, news_component=None):
        self.treaties_db = treaties_db
        self.news_component = news_component

    async def process_create(self, event: Any) -> Dict[str, Any]:
        treaty = _obj_to_dict(event)
        tid = treaty.get("id")
        if not tid:
            return {"processed": 0, "skipped": 1}

        af = _get_alliance_fields(treaty)
        treaty_type = str(treaty.get("treaty_type") or "Unknown")
        treaty_url  = treaty.get("treaty_url") or None
        edate       = _event_date(treaty)

        if self.treaties_db:
            await self.treaties_db.save_treaty({**treaty, **af})

        if self.news_component:
            try:
                from PnWHarvester.db import news_writer as nw
                await nw.record_treaty_signed(
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
            except Exception as e:
                logger.debug(f"treaty/create news: {e}")

        logger.info(
            f"treaty/create → id={tid} type={treaty_type} "
            f"{af['alliance1_name']} <-> {af['alliance2_name']}"
        )
        return {"processed": 1, "skipped": 0}

    async def process_update(self, event: Any) -> Dict[str, Any]:
        treaty = _obj_to_dict(event)
        tid = treaty.get("id")
        if not tid:
            return {"processed": 0, "skipped": 1}

        af = _get_alliance_fields(treaty)
        if self.treaties_db:
            await self.treaties_db.save_treaty({**treaty, **af})

        logger.debug(f"treaty/update → id={tid}")
        return {"processed": 1, "skipped": 0}

    async def process_delete(self, event: Any) -> Dict[str, Any]:
        treaty = _obj_to_dict(event)
        tid = treaty.get("id")
        if not tid:
            return {"processed": 0, "skipped": 1}

        af = _get_alliance_fields(treaty)
        treaty_type = str(treaty.get("treaty_type") or "Unknown")
        edate       = _event_date(treaty)

        if self.treaties_db:
            await self.treaties_db.delete_treaty(int(tid))

        if self.news_component:
            try:
                from PnWHarvester.db import news_writer as nw
                await nw.record_treaty_cancelled(
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
            except Exception as e:
                logger.debug(f"treaty/delete news: {e}")

        logger.info(
            f"treaty/delete → id={tid} type={treaty_type} "
            f"{af['alliance1_name']} <-> {af['alliance2_name']}"
        )
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
        websocket_manager=None,
        api_key: str = "",
    ):
        self.treaties_db = treaties_db
        self.news_component = news_component
        self.websocket_manager = websocket_manager
        self.api_key = api_key
        
        # Use shared websocket manager if provided, otherwise fallback to own QueryKit
        if self.websocket_manager:
            self.kit = None  # Will use shared manager's kit
        else:
            self.kit = QueryKit(api_key)

        self.processor = TreatyEventProcessor(treaties_db, news_component)

        # Treaties change much less frequently than other game data (nations, wars, etc.)
        # Set a very long silence timeout to prevent unnecessary restarts
        self.activity_tracker = ActivityTracker(max_silence_seconds=86400.0)  # 24 hours

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
        }
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
        if not hasattr(self, "kit") or self.kit is None:
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
            if hasattr(socket, "ws") and socket.ws and not socket.ws.closed:
                await socket.ws.close()
        except Exception as e:
            logger.debug(f"Error closing WebSocket: {e}")

        # Do NOT close kit.aiohttp_session here. pnwkit spawns untracked
        # handle_socket_close() tasks that hold a reference to the session and
        # call reconnect() on it. Closing the session races with those tasks
        # causing RuntimeError('Session is closed'). The session will be
        # garbage-collected harmlessly once those tasks finish.

        # Clear references
        self.kit.socket = None
        self.kit = None

    async def run_forever(self):
        """Run with auto-restart on disconnect — called by GPPManager."""
        retry = 0
        base_delay = 10.0
        max_delay  = 300.0

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
            except asyncio.CancelledError:
                logger.info("TreatyComponent cancelled")
                break
            except Exception as e:
                delay = min(base_delay * (2 ** retry), max_delay)
                retry += 1
                logger.warning(
                    f"TreatyComponent disconnected ({e}) — "
                    f"retry {retry}, restarting in {delay:.1f}s"
                )
            finally:
                await self.stop()

            await asyncio.sleep(delay if retry > 0 else base_delay)

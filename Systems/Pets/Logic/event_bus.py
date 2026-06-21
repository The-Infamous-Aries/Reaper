"""
GPP Observer / Event Queue Pattern — Pet System
================================================
Two complementary patterns:

  EventBus   — synchronous publish/subscribe (Observer pattern).
               Listeners register for named events and are called immediately
               when the event fires.  Good for in-process side-effects like
               logging, task tracking, and stat updates.

  EventQueue — asynchronous queue that batches events and processes them in
               order.  Prevents cascading issues (e.g. a level-up triggering
               another level-up mid-handler) and gives the caller control over
               when side-effects run.

Usage:
    from Systems.Pets.Logic.event_bus import event_bus, EventQueue

    # Subscribe (Observer)
    @event_bus.on("pet_trained")
    async def on_trained(payload):
        await tasks_db.record("train", payload["user_id"])

    # Publish (fires all listeners immediately)
    await event_bus.emit("pet_trained", {"user_id": "123", "stat": "ATT", "delta": 3})

    # Queue (batch, then flush)
    queue = EventQueue()
    queue.push("pet_trained", {...})
    queue.push("xp_gained",   {...})
    await queue.flush()          # processes in order, no cascading
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger("pet_event_bus")


# ─────────────────────────────────────────────────────────────────────────────
# EventBus  (Observer pattern)
# ─────────────────────────────────────────────────────────────────────────────

Handler = Callable[[Dict[str, Any]], Awaitable[None]]


class EventBus:
    """
    Lightweight async pub/sub bus.

    Listeners are async callables that receive a single payload dict.
    Errors in listeners are caught and logged so one bad listener cannot
    break the rest of the pipeline.
    """

    def __init__(self) -> None:
        self._listeners: Dict[str, List[Handler]] = defaultdict(list)

    # ── Registration ──────────────────────────────────────────────────────────

    def on(self, event: str) -> Callable[[Handler], Handler]:
        """Decorator: @event_bus.on("pet_trained")"""
        def decorator(fn: Handler) -> Handler:
            self._listeners[event].append(fn)
            return fn
        return decorator

    def subscribe(self, event: str, handler: Handler) -> None:
        """Programmatic subscription."""
        self._listeners[event].append(handler)

    def unsubscribe(self, event: str, handler: Handler) -> None:
        try:
            self._listeners[event].remove(handler)
        except ValueError:
            pass

    # ── Publishing ────────────────────────────────────────────────────────────

    async def emit(self, event: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """
        Fire all listeners for *event* with *payload*.
        Listeners run sequentially; errors are caught and logged.
        """
        if payload is None:
            payload = {}
        for handler in list(self._listeners.get(event, [])):
            try:
                await handler(payload)
            except Exception as exc:
                logger.error(
                    "EventBus handler error for event '%s': %s",
                    event, exc, exc_info=True
                )

    def emit_sync(self, event: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """
        Fire listeners from a synchronous context.
        Creates a task if a running loop exists, otherwise runs synchronously.
        """
        if payload is None:
            payload = {}
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.emit(event, payload))
        except RuntimeError:
            # No running loop — run synchronously (test / startup context)
            asyncio.run(self.emit(event, payload))

    # ── Introspection ─────────────────────────────────────────────────────────

    def listener_count(self, event: str) -> int:
        return len(self._listeners.get(event, []))

    def clear(self, event: Optional[str] = None) -> None:
        if event:
            self._listeners.pop(event, None)
        else:
            self._listeners.clear()


# ─────────────────────────────────────────────────────────────────────────────
# EventQueue  (Event Queue pattern)
# ─────────────────────────────────────────────────────────────────────────────

class EventQueue:
    """
    Collects events during a request/action and flushes them in order
    after the main logic completes.

    This prevents cascading issues: e.g. a level-up handler that awards
    a chest cannot accidentally trigger another level-up mid-flush because
    the queue is drained sequentially and new events pushed during flush
    are appended to the *end* of the queue (breadth-first).

    Example:
        queue = EventQueue()
        queue.push("pet_trained", {"user_id": uid, "stat": "ATT"})
        queue.push("xp_gained",   {"user_id": uid, "amount": 50})
        await queue.flush(event_bus)
    """

    def __init__(self) -> None:
        self._queue: List[tuple[str, Dict[str, Any]]] = []

    def push(self, event: str, payload: Optional[Dict[str, Any]] = None) -> None:
        self._queue.append((event, payload or {}))

    def clear(self) -> None:
        self._queue.clear()

    def __len__(self) -> int:
        return len(self._queue)

    async def flush(self, bus: Optional[EventBus] = None) -> List[tuple[str, Dict[str, Any]]]:
        """
        Process all queued events in order using *bus* (defaults to the
        global event_bus).  Returns the list of processed (event, payload)
        pairs for inspection / testing.
        """
        target = bus or event_bus
        processed: List[tuple[str, Dict[str, Any]]] = []
        # Drain breadth-first: new events pushed during flush go to the end
        while self._queue:
            event, payload = self._queue.pop(0)
            processed.append((event, payload))
            await target.emit(event, payload)
        return processed


# ─────────────────────────────────────────────────────────────────────────────
# Global singleton bus
# ─────────────────────────────────────────────────────────────────────────────

event_bus: EventBus = EventBus()


# ─────────────────────────────────────────────────────────────────────────────
# Built-in listeners — wired up at import time
# ─────────────────────────────────────────────────────────────────────────────

@event_bus.on("pet_trained")
async def _on_pet_trained(payload: Dict[str, Any]) -> None:
    """Record train action for daily tasks."""
    try:
        from web.api.tasks_api import record_action as _record
        user_id = str(payload.get("user_id", ""))
        if user_id:
            await _record(user_id, "train")
    except Exception:
        pass


@event_bus.on("mission_completed")
async def _on_mission_completed(payload: Dict[str, Any]) -> None:
    """Record mission action for daily tasks."""
    try:
        from web.api.tasks_api import record_action as _record
        user_id = str(payload.get("user_id", ""))
        if user_id:
            await _record(user_id, "mission")
    except Exception:
        pass


@event_bus.on("play_completed")
async def _on_play_completed(payload: Dict[str, Any]) -> None:
    """Record play action for daily tasks."""
    try:
        from web.api.tasks_api import record_action as _record
        user_id = str(payload.get("user_id", ""))
        if user_id:
            await _record(user_id, "play")
    except Exception:
        pass


@event_bus.on("item_equipped")
async def _on_item_equipped(payload: Dict[str, Any]) -> None:
    """Record equip action for daily tasks."""
    try:
        from web.api.tasks_api import record_action as _record
        user_id = str(payload.get("user_id", ""))
        if user_id:
            await _record(user_id, "equip")
    except Exception:
        pass


@event_bus.on("potion_used")
async def _on_potion_used(payload: Dict[str, Any]) -> None:
    """Record potion use for daily tasks."""
    try:
        from web.api.tasks_api import record_action as _record
        user_id = str(payload.get("user_id", ""))
        if user_id:
            await _record(user_id, "potion")
    except Exception:
        pass


@event_bus.on("chest_opened")
async def _on_chest_opened(payload: Dict[str, Any]) -> None:
    """Record loot open for daily tasks."""
    try:
        from web.api.tasks_api import record_action as _record
        user_id = str(payload.get("user_id", ""))
        amount  = int(payload.get("amount", 1))
        if user_id:
            for _ in range(amount):
                await _record(user_id, "loot")
    except Exception:
        pass


@event_bus.on("item_consumed")
async def _on_item_consumed(payload: Dict[str, Any]) -> None:
    """Record consume for daily tasks."""
    try:
        from web.api.tasks_api import record_action as _record
        user_id = str(payload.get("user_id", ""))
        count   = int(payload.get("count", 1))
        if user_id:
            for _ in range(count):
                await _record(user_id, "consume")
    except Exception:
        pass


@event_bus.on("item_gifted")
async def _on_item_gifted(payload: Dict[str, Any]) -> None:
    """Record gift for daily tasks."""
    try:
        from web.api.tasks_api import record_action as _record
        user_id = str(payload.get("sender_id", ""))
        if user_id:
            await _record(user_id, "gift")
    except Exception:
        pass


@event_bus.on("npc_battle_ended")
async def _on_npc_battle_ended(payload: Dict[str, Any]) -> None:
    """Record NPC battle result for daily tasks."""
    try:
        from web.api.tasks_api import record_action as _record
        user_id = str(payload.get("user_id", ""))
        won     = bool(payload.get("won", False))
        if user_id:
            await _record(user_id, "battle_npc", won=won)
    except Exception:
        pass


@event_bus.on("pet_renamed")
async def _on_pet_renamed(payload: Dict[str, Any]) -> None:
    """Record rename for daily tasks."""
    try:
        from web.api.tasks_api import record_action as _record
        user_id = str(payload.get("user_id", ""))
        actions = payload.get("actions", {})
        if user_id:
            if actions:
                for key in ("Attack", "Defense", "Charge"):
                    if (actions.get(key) or "").strip():
                        await _record(user_id, "rename", meta={"battle_action": key})
            else:
                await _record(user_id, "rename", meta=None)
    except Exception:
        pass


@event_bus.on("pet_adopted")
async def _on_pet_adopted(payload: Dict[str, Any]) -> None:
    """Generate tasks for a newly adopted pet."""
    try:
        from web.api.tasks_api import tasks_db
        user_id = str(payload.get("user_id", ""))
        if user_id:
            await tasks_db.get_slots(user_id)
    except Exception:
        pass


@event_bus.on("boss_battle_ended")
async def _on_boss_battle_ended(payload: Dict[str, Any]) -> None:
    """Record boss battle win for daily tasks."""
    try:
        from web.api.tasks_api import record_action as _record
        user_id = str(payload.get("user_id", ""))
        won     = bool(payload.get("won", False))
        if user_id and won:
            await _record(user_id, "boss", won=True)
    except Exception:
        pass


@event_bus.on("ss_joined")
async def _on_ss_joined(payload: Dict[str, Any]) -> None:
    """Record Survivor Series join for daily tasks."""
    try:
        from web.api.tasks_api import record_action as _record
        user_id = str(payload.get("user_id", ""))
        if user_id:
            await _record(user_id, "ss_join")
    except Exception:
        pass

"""Compatibility helpers for pnwkit websocket quirks."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_PATCHED = False


def patch_pnwkit() -> None:
    """Make pnwkit tolerant of already-decoded websocket payloads."""
    global _PATCHED
    if _PATCHED:
        return

    try:
        from pnwkit.new import QueryKit
    except Exception as exc:
        logger.debug("pnwkit compatibility patch skipped: %s", exc)
        return

    original_loads = QueryKit.loads

    def loads(self: Any, text: Any) -> Any:
        if isinstance(text, (dict, list)):
            return text
        if isinstance(text, (bytes, bytearray)):
            text = text.decode("utf-8")
        if text in ("", None):
            return {}
        try:
            return original_loads(self, text)
        except TypeError:
            return json.loads(text, parse_int=self.parse_int, parse_float=self.parse_float)

    QueryKit.loads = loads
    _PATCHED = True


async def close_querykit(kit: Any) -> None:
    """Close a pnwkit QueryKit socket and sessions without leaking aiohttp resources."""
    if kit is None:
        return

    socket = getattr(kit, "socket", None)
    if socket is not None:
        setattr(socket, "close_code", 1000)
        setattr(socket, "reconnecting", True)

        tasks_to_cancel = []
        for attr in ("task", "ping_pong_task", "_heartbeat_task"):
            task = getattr(socket, attr, None)
            if task is not None and not task.done():
                task.cancel()
                tasks_to_cancel.append(task)
        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)

        ws = getattr(socket, "ws", None)
        if ws is not None and not getattr(ws, "closed", True):
            with contextlib.suppress(Exception):
                await ws.close(code=1000)

    session = getattr(kit, "aiohttp_session", None)
    if session is not None and not getattr(session, "closed", True):
        with contextlib.suppress(Exception):
            await session.close()
    kit.aiohttp_session = None

    requests_session = getattr(kit, "requests_session", None)
    if requests_session is not None:
        with contextlib.suppress(Exception):
            requests_session.close()
    kit.requests_session = None
    kit.socket = None

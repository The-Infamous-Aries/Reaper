from __future__ import annotations

import logging
import random
import re
from typing import Any, Dict

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from Systems.Pets.Logic.event_bus import EventQueue

logger = logging.getLogger("Reaper.FortuneCookieAPI")
router = APIRouter()

REAPER_WHISPER_FALLBACKS = [
    "Is there any chocolate in the fridge?",
    "Your shoe is untied.",
    "The spoon knows what you did.",
    "I moved your bookmark three pages forward.",
    "The hallway is pretending not to listen.",
    "Your left pocket seems unusually confident.",
    "Someone taught the toaster your middle name.",
    "The cold pizza has accepted its destiny.",
    "Your chair squeaked in Morse code.",
    "The fridge light blinked twice for you.",
    "Your shadow is standing a little too straight.",
    "The napkin folded itself for legal reasons.",
    "There is a crumb with management experience nearby.",
    "Your keyboard misses the old typo.",
    "The moon asked about your socks.",
    "A tiny bell rang inside the wall.",
    "The last ice cube has opinions.",
    "Your ceiling fan is keeping score.",
    "The drawer refuses to say who opened it.",
    "Your reflection arrived three seconds early.",
]


def _clean_reaper_whisper(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value or "").strip().strip("\"'`")
    cleaned = re.sub(r"^(reaper whispers?:|the reaper whispers?:)\s*", "", cleaned, flags=re.I).strip()
    match = re.match(r"^(.{4,160}?[.!?])(?:\s|$)", cleaned)
    if match:
        cleaned = match.group(1).strip()
    else:
        cleaned = cleaned[:120].strip()
        if cleaned and cleaned[-1] not in ".!?":
            cleaned += "."
    if not cleaned or len(cleaned.split()) > 22:
        return random.choice(REAPER_WHISPER_FALLBACKS)
    return cleaned


async def _generate_reaper_whisper_text() -> tuple[str, str]:
    try:
        import asyncio
        from Systems.Functions.local_ai import chat_complete

        prompt = (
            "Generate exactly one short strange sentence the Reaper would whisper directly to a user. "
            "It should be mundane, surreal, and oddly funny, like 'Is there any chocolate in the fridge?' "
            "or 'Your shoe is untied.' Keep it safe, non-threatening, no slurs, no explanation, no quotes, "
            "22 words maximum."
        )
        result = await asyncio.wait_for(
            chat_complete(
                messages=[{"role": "user", "content": prompt}],
                system="You write tiny eerie-comic Reaper whispers. Return one sentence only.",
                temperature=0.95,
                max_tokens=48,
            ),
            timeout=12,
        )
        if result:
            return _clean_reaper_whisper(result), "ai"
    except Exception as e:
        logger.debug(f"AI Reaper whisper generation failed: {e}")

    return random.choice(REAPER_WHISPER_FALLBACKS), "fallback"


@router.get("/fortune-cookie/reaper-whisper")
async def reaper_whisper():
    text, source = await _generate_reaper_whisper_text()
    return JSONResponse({
        "id": f"reaper_whisper_{source}",
        "text": text,
        "source": source,
    })


@router.post("/fortune-cookie/opened")
async def fortune_cookie_opened(request: Request, data: Dict[str, Any] = Body(default_factory=dict)):
    """
    Listener endpoint for Fortune Cookies Opened.

    The page can be used while signed out, but signed-in users get task progress
    for the daily, weekly, and monthly `fortune_cookie` task action.
    """
    category = str(data.get("category", "unknown"))[:80]
    fortune_id = str(data.get("fortune_id", ""))[:120]

    user = request.session.get("discord_user")
    user_id = str(user.get("id")) if user and user.get("id") else ""

    try:
        queue = EventQueue()
        queue.push("fortune_cookie_opened", {
            "user_id": user_id or None,
            "category": category,
            "fortune_id": fortune_id or None,
        })
        await queue.flush()
    except Exception as e:
        logger.debug(f"Fortune cookie event queue failed: {e}")

    if user_id:
        try:
            from web.api.tasks_api import record_action
            await record_action(user_id, "fortune_cookie", {
                "category": category,
                "fortune_id": fortune_id,
            })
        except Exception as e:
            logger.debug(f"Fortune cookie task progress failed for {user_id}: {e}")

    return JSONResponse({
        "success": True,
        "event": "fortune_cookie_opened",
        "task_recorded": bool(user_id),
    })

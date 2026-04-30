"""
Tarot API Endpoint
Handles server-side tarot reading generation including AI summaries via Groq.
"""

import json
import logging
import random
from pathlib import Path
from typing import List, Optional

import aiohttp
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("Reaper.TarotAPI")
router = APIRouter()

TAROT_JSON_PATH = Path(__file__).parent.parent.parent / "Systems" / "Astrology" / "Tarot" / "tarot-images.json"

# Lazy-loaded deck cache — loaded once in a thread, never blocks the event loop again
_deck_cache: Optional[list] = None

def _load_deck_sync() -> list:
    with open(TAROT_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["cards"]

async def _get_deck() -> list:
    global _deck_cache
    if _deck_cache is None:
        import asyncio
        _deck_cache = await asyncio.to_thread(_load_deck_sync)
    return _deck_cache


SPREAD_POSITIONS = {
    "1 Card": ["The Message"],
    "3 Card (Past/Present/Future)": ["Past", "Present", "Future"],
    "5 Card (Traditional)": ["Theme", "Obstacle", "Advice", "Hidden Influence", "Outcome"],
}

SPREAD_PROMPTS = {
    "1 Card": lambda cards: f"""You are a wise and intuitive tarot reader. The universe has drawn one card for a seeker.

Card: {cards[0]['name']}
Position: The Message
Core Meaning: {cards[0]['meaning']}

Provide a profound and personalized message from the universe to the seeker. Be encouraging, insightful, and directly related to the card's energy. Keep the response under 150 words.""",

    "3 Card (Past/Present/Future)": lambda cards: f"""You are an experienced tarot reader interpreting a three-card spread for a seeker.

Cards:
1. Past: {cards[0]['name']} — {cards[0]['meaning']}
2. Present: {cards[1]['name']} — {cards[1]['meaning']}
3. Future: {cards[2]['name']} — {cards[2]['meaning']}

Explain what each card in its position means, then provide a combined interpretation of how these three cards tell a cohesive story. Be insightful and offer guidance. Keep the total response under 250 words.""",

    "5 Card (Traditional)": lambda cards: f"""You are a master tarot reader providing a detailed five-card spread reading for a seeker.

Cards:
1. Theme: {cards[0]['name']} — {cards[0]['meaning']}
2. Obstacle: {cards[1]['name']} — {cards[1]['meaning']}
3. Advice: {cards[2]['name']} — {cards[2]['meaning']}
4. Hidden Influence: {cards[3]['name']} — {cards[3]['meaning']}
5. Outcome: {cards[4]['name']} — {cards[4]['meaning']}

Weave these elements into a cohesive and insightful narrative covering the theme, obstacle, advice, hidden influence, and likely outcome. Keep the response under 300 words.""",
}


class TarotRequest(BaseModel):
    spread: str
    cards: List[dict]  # [{name, position, meaning, isReversed, imageKey}]


async def _call_groq(prompt: str, groq_api_key: str) -> Optional[str]:
    """Call Groq API and return the response text, or None on failure."""
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {groq_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a wise and intuitive tarot reader. Provide profound, insightful, and personalized messages based on the cards drawn.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.8,
                    "max_tokens": 400,
                    "top_p": 0.9,
                },
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                logger.warning(f"Groq API returned status {resp.status}")
                return None
    except Exception as e:
        logger.error(f"Groq API call failed: {e}")
        return None


def _basic_summary(spread: str, cards: list) -> str:
    """Fallback summary when AI is unavailable."""
    positions = SPREAD_POSITIONS.get(spread, ["Card"] * len(cards))
    lines = [f"**Your {spread} Reading**\n"]
    for i, card in enumerate(cards):
        pos = positions[i] if i < len(positions) else f"Card {i+1}"
        lines.append(f"**{pos}: {card['name']}**\n{card['meaning']}\n")
    return "\n".join(lines)


@router.post("/tarot/reading")
async def generate_tarot_reading(request: TarotRequest):
    """
    Generate an AI-powered tarot reading summary server-side.
    Accepts the already-drawn cards from the frontend and returns an AI summary.
    """
    spread = request.spread
    cards = request.cards

    if spread not in SPREAD_POSITIONS:
        return JSONResponse({"error": f"Unknown spread: {spread}"}, status_code=400)

    expected = len(SPREAD_POSITIONS[spread])
    if len(cards) != expected:
        return JSONResponse(
            {"error": f"Expected {expected} cards for '{spread}', got {len(cards)}"},
            status_code=400,
        )

    # Try AI summary
    try:
        from Systems.Functions.config import GROQ_API_KEY
    except Exception:
        GROQ_API_KEY = None

    summary = None
    if GROQ_API_KEY:
        prompt_fn = SPREAD_PROMPTS.get(spread)
        if prompt_fn:
            prompt = prompt_fn(cards)
            summary = await _call_groq(prompt, GROQ_API_KEY)

    if not summary:
        summary = _basic_summary(spread, cards)
        ai_powered = False
    else:
        ai_powered = True

    return JSONResponse({"summary": summary, "ai_powered": ai_powered})


@router.get("/tarot/deck")
async def get_tarot_deck():
    """Return the full tarot deck JSON (same as static file, but via API)."""
    try:
        deck = await _get_deck()
        return JSONResponse({"cards": deck})
    except Exception as e:
        logger.error(f"Failed to load tarot deck: {e}")
        return JSONResponse({"error": "Could not load tarot deck"}, status_code=500)

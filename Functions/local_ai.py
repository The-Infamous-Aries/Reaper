"""
local_ai.py — Unified local AI client for Reaper Bot
=====================================================
Uses Ollama (localhost:11434) as the primary LLM backend.
Falls back to Groq automatically if Ollama is unavailable or returns an error.

All calls use the OpenAI-compatible REST API that Ollama exposes, so zero
prompt changes are needed — the same messages/system prompts work as-is.

Usage:
    from Systems.Functions.local_ai import chat_complete, chat_complete_json

    # Plain text response
    text = await chat_complete(messages=[...], system="You are...")

    # JSON-mode response (returns parsed dict or None)
    data = await chat_complete_json(messages=[...], system="You are...")
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Optional

import aiohttp

logger = logging.getLogger("Reaper.LocalAI")

# ── Configuration ─────────────────────────────────────────────────────────────

# Ollama settings — llama3.2:3b uses ~2 GB VRAM, leaves plenty of headroom
# Ollama's OpenAI-compatible endpoint lives under /v1
OLLAMA_BASE_URL  = "http://localhost:11434/v1"
OLLAMA_MODEL     = "llama3.2:3b"

# Health check uses the native Ollama API (not the /v1 compat layer)
OLLAMA_HEALTH_URL = "http://localhost:11434"

# Groq fallback settings (uses existing key from config)
GROQ_BASE_URL    = "https://api.groq.com/openai/v1"
GROQ_MODEL       = "llama-3.1-8b-instant"

# Timeouts
OLLAMA_TIMEOUT   = 120   # seconds — local inference can be slow on first call
GROQ_TIMEOUT     = 60    # seconds

# ── Health check cache ────────────────────────────────────────────────────────
# We cache whether Ollama is reachable so we don't probe on every single call.
# Cache expires after 60 s so a restart of Ollama is picked up quickly.
_ollama_available: Optional[bool] = None
_ollama_checked_at: float = 0.0
_OLLAMA_CACHE_TTL = 60.0   # seconds


async def _check_ollama() -> bool:
    """Return True if Ollama is running and the model is available."""
    import time
    global _ollama_available, _ollama_checked_at

    now = time.monotonic()
    if _ollama_available is not None and (now - _ollama_checked_at) < _OLLAMA_CACHE_TTL:
        return _ollama_available

    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{OLLAMA_HEALTH_URL}/api/tags") as resp:
                if resp.status != 200:
                    _ollama_available = False
                    _ollama_checked_at = now
                    return False
                data = await resp.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                # Accept exact match or name-without-tag match
                base = OLLAMA_MODEL.split(":")[0]
                available = any(
                    m == OLLAMA_MODEL or m.startswith(base + ":") or m == base
                    for m in models
                )
                if not available:
                    logger.warning(
                        f"Ollama is running but model '{OLLAMA_MODEL}' is not pulled. "
                        f"Run: ollama pull {OLLAMA_MODEL}"
                    )
                _ollama_available = available
                _ollama_checked_at = now
                return available
    except Exception as e:
        logger.debug(f"Ollama health check failed: {e}")
        _ollama_available = False
        _ollama_checked_at = now
        return False


def _invalidate_ollama_cache() -> None:
    """Force re-check on next call (e.g. after a connection error)."""
    global _ollama_available
    _ollama_available = None


# ── Core request helpers ──────────────────────────────────────────────────────

async def _call_openai_compat(
    base_url: str,
    api_key: Optional[str],
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    json_mode: bool,
    timeout: int,
) -> Optional[str]:
    """
    POST to an OpenAI-compatible /chat/completions endpoint.
    Returns the assistant message content string, or None on failure.
    """
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    url = f"{base_url}/chat/completions"
    client_timeout = aiohttp.ClientTimeout(total=timeout)

    try:
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(f"AI endpoint {base_url} returned {resp.status}: {body[:200]}")
                    return None
                data = await resp.json()
                return data["choices"][0]["message"]["content"].strip()
    except asyncio.TimeoutError:
        logger.warning(f"AI endpoint {base_url} timed out after {timeout}s")
        return None
    except Exception as e:
        logger.warning(f"AI endpoint {base_url} error: {e}")
        return None


# ── Public API ────────────────────────────────────────────────────────────────

async def chat_complete(
    messages: list[dict],
    system: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 512,
) -> Optional[str]:
    """
    Send a chat completion request. Returns the response text or None.

    Args:
        messages:    List of {"role": ..., "content": ...} dicts.
                     If `system` is provided it is prepended automatically.
        system:      Optional system prompt string (convenience shortcut).
        temperature: Sampling temperature (0.0–1.0).
        max_tokens:  Maximum tokens to generate.

    Returns:
        The assistant's response as a plain string, or None if both
        Ollama and Groq fail.
    """
    full_messages = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)

    # ── Try Ollama first ──────────────────────────────────────────────────────
    if await _check_ollama():
        result = await _call_openai_compat(
            base_url=OLLAMA_BASE_URL,
            api_key=None,
            model=OLLAMA_MODEL,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=False,
            timeout=OLLAMA_TIMEOUT,
        )
        if result is not None:
            logger.debug(f"LocalAI: served by Ollama ({OLLAMA_MODEL})")
            return result
        # Connection worked but request failed — invalidate cache
        _invalidate_ollama_cache()

    # ── Fall back to Groq ─────────────────────────────────────────────────────
    try:
        from Systems.Functions.config import GROQ_API_KEY
    except ImportError:
        GROQ_API_KEY = None

    if GROQ_API_KEY:
        result = await _call_openai_compat(
            base_url=GROQ_BASE_URL,
            api_key=GROQ_API_KEY,
            model=GROQ_MODEL,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=False,
            timeout=GROQ_TIMEOUT,
        )
        if result is not None:
            logger.debug("LocalAI: served by Groq fallback")
            return result

    logger.error("LocalAI: both Ollama and Groq failed — no AI response available")
    return None


async def chat_complete_json(
    messages: list[dict],
    system: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 512,
) -> Optional[dict]:
    """
    Like chat_complete() but requests JSON mode and returns a parsed dict.

    Falls back to regex-based JSON extraction if the model wraps the JSON
    in markdown code fences (common with smaller models).

    Returns:
        Parsed dict, or None if parsing fails or both backends fail.
    """
    full_messages = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)

    raw: Optional[str] = None

    # ── Try Ollama first ──────────────────────────────────────────────────────
    if await _check_ollama():
        raw = await _call_openai_compat(
            base_url=OLLAMA_BASE_URL,
            api_key=None,
            model=OLLAMA_MODEL,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
            timeout=OLLAMA_TIMEOUT,
        )
        if raw is None:
            _invalidate_ollama_cache()

    # ── Fall back to Groq ─────────────────────────────────────────────────────
    if raw is None:
        try:
            from Systems.Functions.config import GROQ_API_KEY
        except ImportError:
            GROQ_API_KEY = None

        if GROQ_API_KEY:
            raw = await _call_openai_compat(
                base_url=GROQ_BASE_URL,
                api_key=GROQ_API_KEY,
                model=GROQ_MODEL,
                messages=full_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=True,
                timeout=GROQ_TIMEOUT,
            )

    if raw is None:
        logger.error("LocalAI JSON: both Ollama and Groq failed")
        return None

    # ── Parse JSON ────────────────────────────────────────────────────────────
    # Strip JS-style comments (// ...) that some models emit
    cleaned = re.sub(r"//[^\n]*", "", raw)
    # Strip markdown code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Last resort: find the first {...} block
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        logger.error(f"LocalAI JSON: failed to parse response: {raw[:200]}")
        return None


# ── Convenience: sync wrapper for legacy sync callers ─────────────────────────

def chat_complete_sync(
    messages: list[dict],
    system: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 512,
) -> Optional[str]:
    """
    Synchronous wrapper around chat_complete().
    Use this only from non-async contexts (e.g. quests.py which calls
    _generate_quest_from_groq synchronously).
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an async context — use asyncio.run_coroutine_threadsafe
            import concurrent.futures
            future = asyncio.run_coroutine_threadsafe(
                chat_complete(messages, system, temperature, max_tokens), loop
            )
            return future.result(timeout=OLLAMA_TIMEOUT + 10)
        else:
            return loop.run_until_complete(
                chat_complete(messages, system, temperature, max_tokens)
            )
    except Exception as e:
        logger.error(f"chat_complete_sync error: {e}")
        return None


def chat_complete_json_sync(
    messages: list[dict],
    system: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 512,
) -> Optional[dict]:
    """Synchronous wrapper around chat_complete_json()."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            future = asyncio.run_coroutine_threadsafe(
                chat_complete_json(messages, system, temperature, max_tokens), loop
            )
            return future.result(timeout=OLLAMA_TIMEOUT + 10)
        else:
            return loop.run_until_complete(
                chat_complete_json(messages, system, temperature, max_tokens)
            )
    except Exception as e:
        logger.error(f"chat_complete_json_sync error: {e}")
        return None

"""
nation_emoji_store.py — Centralised nation emoji registry.

Emojis are persisted in Systems/Data/nation_emojis.json as
    { "Nation Name": "emoji", ... }

All autocomplete dropdowns import get_nation_emoji() from here so
a single /theme emoji set command updates every dropdown at once.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_STORE_PATH = Path(__file__).resolve().parents[1] / "Data" / "nation_emojis.json"
_DEFAULT_EMOJI = "🏛️"

# In-memory cache — reloaded on every write, read on every get
_cache: Dict[str, str] = {}
_loaded = False


def _load() -> None:
    global _cache, _loaded
    try:
        if _STORE_PATH.exists():
            _cache = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
        else:
            _cache = {}
    except Exception as e:
        logger.error(f"nation_emoji_store: failed to load {_STORE_PATH}: {e}")
        _cache = {}
    _loaded = True


def _save() -> None:
    try:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STORE_PATH.write_text(
            json.dumps(_cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        logger.error(f"nation_emoji_store: failed to save {_STORE_PATH}: {e}")


def get_nation_emoji(nation_name: str) -> str:
    """Return the stored emoji for a nation, or the default '🏛️'."""
    if not _loaded:
        _load()
    return _cache.get(nation_name, _DEFAULT_EMOJI)


def set_nation_emoji(nation_name: str, emoji: str) -> None:
    """Persist an emoji for a nation."""
    if not _loaded:
        _load()
    _cache[nation_name] = emoji
    _save()


def remove_nation_emoji(nation_name: str) -> bool:
    """Remove a custom emoji (reverts to default). Returns True if it existed."""
    if not _loaded:
        _load()
    if nation_name in _cache:
        del _cache[nation_name]
        _save()
        return True
    return False


def get_all() -> Dict[str, str]:
    """Return a copy of the full emoji map."""
    if not _loaded:
        _load()
    return dict(_cache)


def reload() -> None:
    """Force a reload from disk (useful after external edits)."""
    global _loaded
    _loaded = False
    _load()


def strip_emoji_prefix(text: str) -> str:
    """
    Strip any known emoji prefix and optional leader-name suffix from an
    autocomplete value.

    Handles all forms that Discord may pass through:
      '🐟 Mauryan Empire'                    → 'Mauryan Empire'
      '🏛️ Flim Flam Fugazies (The Infamous Aries)' → 'Flim Flam Fugazies'
      '🏛 Flim Flam Fugazies (The Infamous Aries)'  → 'Flim Flam Fugazies'
      'Flim Flam Fugazies'                   → 'Flim Flam Fugazies'

    The leader-name suffix is the trailing ' (…)' appended by nation_autocomplete
    when leader_name differs from nation_name.
    """
    import re

    if not _loaded:
        _load()

    text = text.strip()

    # ── 1. Strip leading emoji prefix ────────────────────────────────────────
    # Try known stored emojis first (longest match wins to avoid partial strips)
    all_emojis = set(_cache.values()) | {_DEFAULT_EMOJI}
    # Also add the variant without the variation selector (U+FE0F) so that
    # '🏛 ' (no VS-16) is matched when the store has '🏛️' (with VS-16).
    expanded = set()
    for e in all_emojis:
        expanded.add(e)
        expanded.add(e.rstrip("\ufe0f"))   # strip trailing variation selector
    all_emojis = expanded

    for emoji in sorted(all_emojis, key=len, reverse=True):  # longest first
        prefix = f"{emoji} "
        if text.startswith(prefix):
            text = text[len(prefix):]
            break

    # ── 2. Strip trailing ' (leader name)' suffix ────────────────────────────
    # nation_autocomplete appends ' (leader_name)' when leader differs from nation.
    # We strip it so the lookup uses only the bare nation name.
    text = re.sub(r"\s+\([^)]+\)\s*$", "", text).strip()

    return text

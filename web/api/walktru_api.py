from __future__ import annotations

import copy
import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger("Reaper.WalktruAPI")
router = APIRouter()

ROOT_DIR = Path(__file__).resolve().parents[2]
WALKTRU_DIR = ROOT_DIR / "Systems" / "Fun" / "Walk Tru"

STORY_CONFIGS: Dict[str, Dict[str, Any]] = {
    "horror": {"filename": "Horror.json", "icon": "/static/Emojis/Walkthru/horror.png"},
    "ganster": {"filename": "Ganster.json", "icon": "/static/Emojis/Walkthru/gangster.png"},
    "knight": {"filename": "Knight.json", "icon": "/static/Emojis/Walkthru/knight.png"},
    "robot": {"filename": "Robot.json", "icon": "/static/Emojis/Walkthru/robot.png"},
    "western": {"filename": "Western.json", "icon": "/static/Emojis/Walkthru/western.png"},
    "wizard": {"filename": "Wizard.json", "icon": "/static/Emojis/Walkthru/wizard.png"},
    "pirate": {"filename": "Pirate.json", "icon": "/static/Emojis/Walkthru/pirate.png"},
    "cyberpunk": {"filename": "Cyberpunk.json", "icon": "/static/Emojis/Walkthru/cyberpunk.png"},
    "spy": {"filename": "Spy.json", "icon": "/static/Emojis/Walkthru/spy.png"},
    "carnival": {"filename": "Carnival.json", "icon": "/static/Emojis/Walkthru/carnival.png"},
    "deepsea": {"filename": "DeepSea.json", "icon": "/static/Emojis/Walkthru/deepsea.png"},
    "origin": {"filename": "Origin.json", "icon": "/static/Emojis/Walkthru/origin.png"},
}

STORY_ORDER = list(STORY_CONFIGS.keys())

STAT_BOUNDS: Dict[str, Dict[str, int]] = {
    "horror": {"min": 0, "max": 100},
    "ganster": {"min": 0, "max": 100},
    "knight": {"min": -50, "max": 150},
    "robot": {"min": 0, "max": 100},
    "western": {"min": 0, "max": 100},
    "wizard": {"min": 0, "max": 150},
    "pirate": {"min": 0, "max": 150},
    "cyberpunk": {"min": 0, "max": 100},
    "spy": {"min": 0, "max": 100},
    "carnival": {"min": 0, "max": 100},
    "deepsea": {"min": 0, "max": 100},
    "origin": {"min": -100, "max": 100},
}


def _read_json(filename: str) -> Dict[str, Any]:
    path = WALKTRU_DIR / filename
    if not path.exists():
        raise FileNotFoundError(str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{filename} did not contain a JSON object")
    return data


def _merge_story_fragment(story_data: Dict[str, Any], fragment: Dict[str, Any]) -> None:
    for event_key in ("events", "story_map"):
        fragment_events = fragment.get(event_key)
        if isinstance(fragment_events, dict):
            story_data.setdefault("events", {}).update(fragment_events)

    for key, value in fragment.items():
        if key not in ("events", "story_map", "additional_files") and key not in story_data:
            story_data[key] = value


def _text_value(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value)


def _title_from_stage_id(stage_id: str) -> str:
    if stage_id == "event_start":
        return "Opening Move"
    return stage_id.replace("_", " ").title()


def _normalize_choice(choice: Dict[str, Any], mechanic: str) -> Dict[str, Any]:
    normalized = dict(choice)
    normalized.setdefault("label", normalized.get("text", "Continue"))
    normalized.setdefault("success_chance", 100)

    if not isinstance(normalized.get("success"), dict):
        normalized["success"] = {
            "text": _text_value(normalized.get("success_text", "You move forward.")),
            "mechanic_change": normalized.get(
                f"success_{mechanic}_change",
                normalized.get("success_mechanic_change", 0),
            ),
            "next_stage": normalized.get("success_next_stage", normalized.get("next_stage")),
        }

    if not isinstance(normalized.get("failure"), dict):
        normalized["failure"] = {
            "text": _text_value(normalized.get("failure_text", "The attempt goes badly, but you keep moving.")),
            "mechanic_change": normalized.get(f"{mechanic}_change", normalized.get("mechanic_change", 0)),
            "next_stage": normalized.get("failure_next_stage", normalized.get("next_stage")),
        }

    return normalized


def _normalize_choices(choices: Any, mechanic: str) -> list[Dict[str, Any]]:
    if isinstance(choices, dict):
        iterable = []
        for label, raw_choice in choices.items():
            if isinstance(raw_choice, dict):
                choice = dict(raw_choice)
                choice.setdefault("label", label)
                iterable.append(choice)
        choices = iterable

    if not isinstance(choices, list):
        return []

    return [_normalize_choice(choice, mechanic) for choice in choices if isinstance(choice, dict)]


def _normalize_story_data(story_key: str, story_data: Dict[str, Any]) -> Dict[str, Any]:
    mechanic = str(story_data.get("mechanic") or story_key)
    events = story_data.get("events")
    if not isinstance(events, dict):
        events = story_data.get("story_map", {})
        story_data["events"] = events if isinstance(events, dict) else {}

    normalized_events: Dict[str, Dict[str, Any]] = {}
    for stage_id, stage in story_data["events"].items():
        if not isinstance(stage, dict):
            continue
        normalized_stage = dict(stage)
        normalized_stage.setdefault("id", stage_id)
        normalized_stage.setdefault("title", _title_from_stage_id(stage_id))
        if "description" not in normalized_stage and "text" in normalized_stage:
            normalized_stage["description"] = normalized_stage.get("text", "")
        normalized_stage.setdefault("description", "")
        normalized_stage["choices"] = _normalize_choices(normalized_stage.get("choices", []), mechanic)
        normalized_events[stage_id] = normalized_stage

    story_data["events"] = normalized_events
    story_data.setdefault("story_key", story_key)
    story_data.setdefault("start_stage", "event_start")
    story_data.setdefault("starting_value", 0)
    story_data["bounds"] = STAT_BOUNDS.get(story_key, {"min": 0, "max": 100})

    secondary_stats = story_data.get("secondary_stats")
    mechanics = story_data.get("mechanics")
    if not isinstance(mechanics, dict):
        mechanics = {}
    if isinstance(secondary_stats, dict):
        mechanics["secondary_stats"] = secondary_stats
    story_data["mechanics"] = mechanics
    return story_data


@lru_cache(maxsize=16)
def load_story_bundle(story_key: str) -> Dict[str, Any]:
    if story_key not in STORY_CONFIGS:
        raise KeyError(story_key)

    config = STORY_CONFIGS[story_key]
    story_data = _read_json(config["filename"])

    additional_files = []
    additional_files.extend(story_data.get("additional_files", []))
    seen_files = set()
    for filename in additional_files:
        if filename in seen_files:
            continue
        seen_files.add(filename)
        _merge_story_fragment(story_data, _read_json(filename))

    return _normalize_story_data(story_key, story_data)


@lru_cache(maxsize=32)
def load_story_meta(story_key: str) -> Dict[str, Any]:
    if story_key not in STORY_CONFIGS:
        raise KeyError(story_key)

    config = STORY_CONFIGS[story_key]
    story_data = _normalize_story_data(story_key, _read_json(config["filename"]))
    events = story_data.get("events", {})
    secondary_stats = story_data.get("mechanics", {}).get("secondary_stats", {})
    return {
        "key": story_key,
        "title": story_data.get("title", story_key.title()),
        "description": story_data.get("description", ""),
        "mechanic": story_data.get("mechanic", story_key),
        "starting_value": story_data.get("starting_value", 0),
        "start_stage": story_data.get("start_stage", "event_start"),
        "bounds": STAT_BOUNDS.get(story_key, {"min": 0, "max": 100}),
        "secondary_stats": secondary_stats if isinstance(secondary_stats, dict) else {},
        "icon": config["icon"],
        "stage_count": len(events),
        "branching": "1-3-9-27-81-243-729-2187",
    }


def _stage_number_from_id(stage_id: str) -> int:
    if stage_id == "event_start":
        return 1
    match = re.search(r"_s(\d+)_", stage_id)
    if match:
        return int(match.group(1))
    return 1


def _filename_for_stage(story_key: str, stage_id: str) -> str:
    config = STORY_CONFIGS[story_key]
    stage_number = _stage_number_from_id(stage_id)
    if stage_number <= 5:
        return config["filename"]

    base_data = _read_json(config["filename"])
    for filename in base_data.get("additional_files", []):
        if f"_stage{stage_number}" in filename.lower():
            return filename
    raise FileNotFoundError(f"No Walkthru file found for {story_key} stage {stage_number}")


@lru_cache(maxsize=64)
def load_stage_events(story_key: str, stage_id: str) -> Dict[str, Any]:
    if story_key not in STORY_CONFIGS:
        raise KeyError(story_key)
    data = _normalize_story_data(story_key, _read_json(_filename_for_stage(story_key, stage_id)))
    return data.get("events", {})


def _render_stage(story_key: str, stage: Dict[str, Any], alignment: Optional[str]) -> Dict[str, Any]:
    if story_key != "origin":
        return stage

    variants = stage.get("alignment_variants", {})
    if not isinstance(variants, dict):
        return stage

    variant = variants.get(alignment or "")
    if not isinstance(variant, dict):
        return stage

    rendered = copy.deepcopy(stage)
    for key in ("title", "description", "choices"):
        if key in variant:
            rendered[key] = variant[key]
    return rendered


@router.get("/walktru/stories")
async def walktru_stories():
    stories = []
    for story_key in STORY_ORDER:
        try:
            stories.append(load_story_meta(story_key))
        except Exception as exc:
            logger.exception("Failed to load Walkthru story metadata for %s", story_key)
            stories.append({
                "key": story_key,
                "title": story_key.title(),
                "description": f"Could not load story metadata: {exc}",
                "error": True,
                "icon": STORY_CONFIGS[story_key]["icon"],
            })
    return JSONResponse({"stories": stories})


@router.get("/walktru/stories/{story_key}")
async def walktru_story(story_key: str):
    try:
        meta = load_story_meta(story_key)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown Walkthru story")
    except Exception as exc:
        logger.exception("Failed to load Walkthru story metadata %s", story_key)
        raise HTTPException(status_code=500, detail=f"Could not load story metadata: {exc}") from exc

    event_count = 0
    try:
        base = _read_json(STORY_CONFIGS[story_key]["filename"])
        files = [STORY_CONFIGS[story_key]["filename"]] + list(base.get("additional_files", []))
        for filename in files:
            events = _read_json(filename).get("events", {})
            if isinstance(events, dict):
                event_count += len(events)
    except Exception as exc:
        logger.debug("Could not count Walkthru events for %s: %s", story_key, exc)

    payload = dict(meta)
    payload["event_count"] = event_count
    return JSONResponse(payload)


@router.get("/walktru/stories/{story_key}/stage/{stage_id}")
async def walktru_story_stage(
    story_key: str,
    stage_id: str,
    alignment: Optional[str] = Query(default=None),
):
    if alignment not in (None, "", "hero", "villain"):
        raise HTTPException(status_code=422, detail="alignment must be hero or villain")
    try:
        stage = load_stage_events(story_key, stage_id).get(stage_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown Walkthru story")
    except Exception as exc:
        logger.exception("Failed to load Walkthru story stage %s / %s", story_key, stage_id)
        raise HTTPException(status_code=500, detail=f"Could not load story stage: {exc}") from exc

    if not isinstance(stage, dict):
        raise HTTPException(status_code=404, detail="Walkthru stage not found")

    return JSONResponse({
        "story": load_story_meta(story_key),
        "stage": _render_stage(story_key, stage, alignment),
    })

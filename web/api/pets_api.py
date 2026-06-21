from fastapi import APIRouter, HTTPException, Request, Body, UploadFile, File
from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.pet_brain import StatsCalculator, LootCalculator
from Systems.Pets.Logic.ability_tree import (
    get_tree_state, spend_stat_mastery, spend_advantage_mastery,
    unlock_ability, purchase_ability_point, STATS, ADVANTAGE_MASTERY_KEYS
)
from Systems.Pets.Logic.battle_skills import (
    draw_initial_skill_choices, draw_skill_choices, equip_skill,
    get_skill_state, get_equipped_skills, SKILL_BY_ID, ALL_ELEMENTS
)
# ── GPP patterns ──────────────────────────────────────────────────────────────
from Systems.Pets.Logic.pet_components import (
    StatsComponent, AnimationComponent, StateComponent,
    InventoryComponent, CombatComponent,
)
from Systems.Pets.Logic.event_bus import event_bus, EventQueue
from Systems.Pets.Logic.pet_object_pool import stats_cache
# ─────────────────────────────────────────────────────────────────────────────
from fastapi.responses import JSONResponse
import asyncio
import base64
import io
import json
import os
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Dict, Any
from datetime import datetime
from PIL import Image
from Systems.Functions import cooldown_db
from Systems.Pets.Logic.pet_badge import (
    build_pet_prompt,
    build_pet_prompt_identity,
    generate_pet_badge_image,
)

logger = logging.getLogger(__name__)

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

router = APIRouter()

BADGE_STATIC_ROOT = Path(project_root) / "web" / "static" / "pet_badges"
LEGACY_BADGE_ROOT = Path(project_root) / "Systems" / "Data" / "Badges"
BADGE_CACHE_TTL_SECS = 30 * 60
MAX_BADGE_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_BADGE_MIME = {"image/jpeg", "image/png", "image/webp"}
_BADGE_CANDIDATE_CACHE: dict[str, dict[str, dict[str, Any]]] = {}


def _badge_user_dir(user_id: str) -> Path:
    safe_user_id = re.sub(r"[^0-9A-Za-z_-]", "", str(user_id))
    return BADGE_STATIC_ROOT / safe_user_id


def _badge_url(user_id: str, filename: str) -> str:
    safe_user_id = re.sub(r"[^0-9A-Za-z_-]", "", str(user_id))
    return f"/static/pet_badges/{safe_user_id}/{filename}?v={int(time.time())}"


def _selected_badge_url(user_id: str) -> str:
    selected = _badge_user_dir(user_id) / "selected.png"
    if not selected.exists():
        return ""
    safe_user_id = re.sub(r"[^0-9A-Za-z_-]", "", str(user_id))
    return f"/static/pet_badges/{safe_user_id}/selected.png?v={int(selected.stat().st_mtime)}"


def _candidate_badges(user_id: str) -> list[dict]:
    _prune_badge_cache()
    user_cache = _BADGE_CANDIDATE_CACHE.get(str(user_id), {})
    choices = sorted(user_cache.values(), key=lambda item: item["created_at"], reverse=True)
    return [{"id": item["id"], "url": item["data_url"]} for item in choices[:16]]


def _prune_badge_cache() -> None:
    now = time.time()
    for user_id in list(_BADGE_CANDIDATE_CACHE.keys()):
        user_cache = _BADGE_CANDIDATE_CACHE[user_id]
        for badge_id in list(user_cache.keys()):
            if now - float(user_cache[badge_id].get("created_at", 0)) > BADGE_CACHE_TTL_SECS:
                user_cache.pop(badge_id, None)
        if not user_cache:
            _BADGE_CANDIDATE_CACHE.pop(user_id, None)


def _cache_badge_candidate(user_id: str, image) -> dict:
    _prune_badge_cache()
    badge_id = f"candidate_{uuid.uuid4().hex}.png"
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    png_bytes = buffer.getvalue()
    data_url = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
    user_cache = _BADGE_CANDIDATE_CACHE.setdefault(str(user_id), {})
    user_cache[badge_id] = {
        "id": badge_id,
        "bytes": png_bytes,
        "data_url": data_url,
        "created_at": time.time(),
    }
    if len(user_cache) > 16:
        oldest = sorted(user_cache.values(), key=lambda item: item["created_at"])[:-16]
        for item in oldest:
            user_cache.pop(item["id"], None)
    return {"id": badge_id, "url": data_url}


def _default_badge_prompt(pet: dict) -> str:
    return build_pet_prompt(pet)[0]


async def _enrich_user_pet(user_id: str, pet: dict) -> dict:
    enriched = _enrich_pet(pet)
    selected_url = _selected_badge_url(user_id)
    if selected_url:
        enriched["badge_url"] = selected_url
        enriched.setdefault("badge", {})
        enriched["badge"]["selected_url"] = selected_url
    return enriched


async def _persist_selected_badge(user_id: str, png_bytes: bytes) -> str:
    user_dir = _badge_user_dir(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    target = user_dir / "selected.png"
    await asyncio.to_thread(target.write_bytes, png_bytes)

    legacy_dir = LEGACY_BADGE_ROOT
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy_target = legacy_dir / f"{user_id}_badge.png"
    try:
        await asyncio.to_thread(legacy_target.write_bytes, png_bytes)
    except Exception:
        logger.debug("Legacy badge copy failed for %s", legacy_target, exc_info=True)

    return str(target)


async def _clear_selected_badge(user_id: str) -> None:
    user_dir = _badge_user_dir(user_id)
    for target in (user_dir / "selected.png", LEGACY_BADGE_ROOT / f"{user_id}_badge.png"):
        try:
            if target.exists():
                await asyncio.to_thread(target.unlink)
        except OSError:
            logger.debug("Badge cleanup failed for %s", target, exc_info=True)


def _detect_badge_image_type(data: bytes) -> str | None:
    if len(data) < 12:
        return None
    header = data[:12]
    if header[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if header[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    return None


async def _uploaded_badge_to_png_bytes(file: UploadFile) -> bytes:
    content_type = (file.content_type or "").lower().split(";", 1)[0].strip()
    if content_type not in ALLOWED_BADGE_MIME:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG and WebP images are allowed.")

    data = await file.read()
    if len(data) > MAX_BADGE_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds the 5 MB limit.")

    detected = _detect_badge_image_type(data)
    if detected is None:
        raise HTTPException(status_code=400, detail="File does not appear to be a valid image.")

    try:
        image = Image.open(io.BytesIO(data)).convert("RGBA")
        image.thumbnail((512, 512), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        x = (512 - image.width) // 2
        y = (512 - image.height) // 2
        canvas.alpha_composite(image, (x, y))
        buffer = io.BytesIO()
        canvas.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception as exc:
        logger.warning("Uploaded badge image could not be processed: %s", exc)
        raise HTTPException(status_code=400, detail="Could not process that image.")

# ── Arena NPC battle skill sessions (server-side state between turns) ─────────
# Keyed by user_id. Cleared when a new battle starts or the battle ends.
_arena_battle_sessions: Dict[str, Any] = {}

# ── Cooldown helpers (DB-backed, survives restarts) ───────────────────────────
_ACTIVITY_COOLDOWN_SECS = 5  # 5 seconds

def _acheck_cooldown(command: str, user_id: str):
    """Sync-friendly shim — callers must await the real async version."""
    raise RuntimeError("Use _acheck_cooldown instead")

async def _acheck_cooldown(command: str, user_id: str) -> tuple[bool, int]:
    """Return (on_cooldown, seconds_remaining)."""
    return await cooldown_db.check(command, user_id)

async def _aset_cooldown(command: str, user_id: str) -> None:
    """Persist a fresh 5-second cooldown for user_id."""
    await cooldown_db.set_cooldown(command, user_id, _ACTIVITY_COOLDOWN_SECS)

def _level_scaled_xp(base_xp: int, pet_level: int) -> int:
    """Scale XP by pet level: +10% per level above 1, so higher levels stay rewarding."""
    return int(base_xp * (1.0 + (pet_level - 1) * 0.1))


def _enrich_pet(pet: dict) -> dict:
    """
    Add computed_stats, xp_for_next_level, and total_xp to a raw pet dict.
    Uses the GPP Object Pool stats cache to avoid redundant StatsCalculator
    calls within the same request burst.
    """
    if not pet:
        return pet

    user_id = str(pet.get("id") or "")

    # Try the short-lived stats cache first (Object Pool pattern)
    cached = stats_cache.get(user_id) if user_id else None
    if cached is None:
        cached = StatsCalculator.calculate_pet_stats(pet)
        if user_id:
            stats_cache.put(user_id, cached)

    lvl               = int(pet.get("level", 1))
    rem               = int(pet.get("experience", 0))
    xp_for_next_level = LootCalculator.get_next_level_xp(lvl)
    total_xp          = int(LootCalculator.get_total_experience_for_level(lvl)) + rem
    return {
        **pet,
        "computed_stats":    cached,
        "xp_for_next_level": xp_for_next_level,
        "total_xp":          total_xp,
    }


def _invalidate_stats_cache(pet: dict) -> None:
    """Invalidate the stats cache entry for this pet after a mutation."""
    user_id = str(pet.get("id") or "")
    if user_id:
        stats_cache.invalidate(user_id)


def _track(user: dict, action: str, *, detail: str = "") -> None:
    """Log a user activity event for audit/informational purposes."""
    uid      = user.get("id", "?") if user else "?"
    username = user.get("username", "?") if user else "?"
    msg = f"[activity] user={username}({uid}) | {action}"
    if detail:
        msg += f" | {detail}"
    logger.info(msg)


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# Cache for JSON files loaded by _load_json — avoids repeated disk reads
_json_file_cache: dict = {}

async def _load_json_cached(path: str) -> Any:
    """Load a JSON file, caching the result in memory after first read."""
    if path not in _json_file_cache:
        _json_file_cache[path] = await asyncio.to_thread(_load_json, path)
    return _json_file_cache[path]


def validate_pet_name(name: str) -> tuple[bool, str]:
    if not name or not name.strip():
        return False, "Pet name is required"
    if len(name) < 1 or len(name) > 32:
        return False, "Pet name must be 1-32 characters"
    if not re.match(r"^[a-zA-Z0-9 \-_.,!?']+$", name):
        return False, "Only alphanumeric characters, spaces, and basic punctuation allowed"
    if re.search(r"<[/a-zA-Z]", name) or re.search(r"javascript:", name, re.IGNORECASE):
        return False, "Invalid characters detected"
    return True, ""


@router.get("/pets/cooldowns")
async def get_cooldowns(request: Request):
    """Return remaining cooldown seconds for all active actions for the current user."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"cooldowns": {}})
    user_id = str(user.get("id"))
    cds = await cooldown_db.get_all(user_id)
    return JSONResponse(content={"cooldowns": cds})


@router.get("/pets/test")
async def test_pets_endpoint():
    """Test endpoint to verify pets API is working"""
    return JSONResponse(content={
        "status": "ok",
        "message": "Pets API is working",
        "timestamp": str(datetime.now())
    })


@router.get("/pets/my-pet")
async def get_my_pet(request: Request):
    """Get the current user's pet data"""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    
    user_id = str(user.get("id"))
    try:
        pet = await user_data_manager.get_pet_data_async(user_id)
        if not pet:
            raise HTTPException(status_code=404, detail="No pet found")
        
        # Enrich with computed stats and XP info
        enriched_pet = await _enrich_user_pet(user_id, pet)
        return JSONResponse(content=enriched_pet)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_my_pet error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── Pet species / equipment data ─────────────────────────────────────────────

@router.get("/pets-data")
async def get_pets_data():
    try:
        path = os.path.join(project_root, "Systems", "Pets", "Logic", "info.json")
        return JSONResponse(content=await _load_json_cached(path))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Pets data file not found")
    except Exception as e:
        logger.error(f"get_pets_data error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch pets data")


@router.get("/equipment-data")
async def get_equipment_data():
    try:
        path = os.path.join(project_root, "Systems", "Pets", "Logic", "equipment.json")
        return JSONResponse(content=await _load_json_cached(path))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Equipment data file not found")
    except Exception as e:
        logger.error(f"get_equipment_data error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch equipment data")


@router.get("/pets/available")
async def get_available_pets():
    try:
        path = os.path.join(project_root, "Systems", "Pets", "Logic", "info.json")
        pets_data = await _load_json_cached(path)
        species_list = []
        for species_key, species_data in pets_data.get("Pets", {}).items():
            base_stats = species_data.get("Stats", {})
            species_list.append({
                "name": species_key,
                "category": species_data.get("Type", species_data.get("type", "land")),
                "element": species_data.get("Element", species_data.get("element", "basic")),
                "stats": {k: base_stats.get(k, 0) for k in ("ATT", "DEF", "INT", "DEX", "HAP", "ENE")},
                "spec": species_data.get("Spec", species_data.get("specializations", [])),
                "description": species_data.get("Descriptions", species_data.get("description", "")),
                "actions": species_data.get("Actions", species_data.get("actions", {})),
            })
        return JSONResponse(content={"species": species_list})
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Pets data file not found")
    except Exception as e:
        logger.error(f"get_available_pets error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch available pets")


# ── User pet ──────────────────────────────────────────────────────────────────

@router.get("/user/pet")
async def get_user_pet(request: Request):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = user.get("id")
    if not user_id:
        return JSONResponse(content={"error": "User ID not found in session"}, status_code=401)

    try:
        pet_data = await user_data_manager.get_pet_data_async(user_id)
        if not pet_data:
            # 204 = no content / no pet — JS checks for this
            return JSONResponse(content={"has_pet": False}, status_code=200)

        return JSONResponse(content={"has_pet": True, **(await _enrich_user_pet(user_id, pet_data))})
    except Exception as e:
        logger.error(f"get_user_pet error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch user pet data")


@router.get("/pets/badges")
async def get_pet_badges(request: Request):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)

    user_id = str(user.get("id") or "")
    if not user_id:
        return JSONResponse(content={"error": "User ID not found in session"}, status_code=401)

    pet_data = await user_data_manager.get_pet_data_async(user_id)
    if not pet_data:
        return JSONResponse(content={"ok": True, "has_pet": False, "selected": "", "badges": []})

    return JSONResponse(content={
        "ok": True,
        "has_pet": True,
        "selected": _selected_badge_url(user_id),
        "badges": _candidate_badges(user_id),
        "default_prompt": _default_badge_prompt(pet_data),
        "pet": await _enrich_user_pet(user_id, pet_data),
    })


@router.post("/pets/badges/generate")
async def generate_pet_badges(request: Request, data: dict = Body(default=None)):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)

    user_id = str(user.get("id") or "")
    if not user_id:
        return JSONResponse(content={"error": "User ID not found in session"}, status_code=401)

    pet = await user_data_manager.get_pet_data_async(user_id)
    if not pet:
        raise HTTPException(status_code=404, detail="No pet found")

    try:
        count = int((data or {}).get("count", 4))
    except (TypeError, ValueError):
        count = 4
    if count < 1 or count > 4:
        raise HTTPException(status_code=400, detail="Badge count must be between 1 and 4")

    user_prompt = str((data or {}).get("prompt") or "").strip()
    if len(user_prompt) > 3500:
        raise HTTPException(status_code=400, detail="Badge prompt is too long")

    required_identity = build_pet_prompt_identity(pet)
    if user_prompt:
        normalized_prompt = user_prompt.lower()
        for line in required_identity.splitlines():
            if line.lower() not in normalized_prompt:
                user_prompt = f"{required_identity}\n\n{user_prompt}"
                break

    generated = []
    for _ in range(count):
        image, _ = await generate_pet_badge_image(pet, user_id, user_prompt)
        generated.append(_cache_badge_candidate(user_id, image))

    return JSONResponse(content={
        "ok": True,
        "badges": generated,
        "selected": _selected_badge_url(user_id),
        "default_prompt": _default_badge_prompt(pet),
        "pet": await _enrich_user_pet(user_id, pet),
    })


@router.post("/pets/badges/save")
async def save_pet_badge(request: Request, data: dict = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)

    user_id = str(user.get("id") or "")
    if not user_id:
        return JSONResponse(content={"error": "User ID not found in session"}, status_code=401)

    badge_id = str((data or {}).get("id") or (data or {}).get("badge_id") or "").strip()
    if not badge_id:
        raise HTTPException(status_code=400, detail="Badge id is required")
    if "/" in badge_id or "\\" in badge_id or ".." in badge_id:
        raise HTTPException(status_code=400, detail="Invalid badge id")

    _prune_badge_cache()
    cached_badge = _BADGE_CANDIDATE_CACHE.get(user_id, {}).get(badge_id)
    if not cached_badge:
        raise HTTPException(status_code=404, detail="Badge image not found")

    await _persist_selected_badge(user_id, cached_badge["bytes"])

    pet = await user_data_manager.get_pet_data_async(user_id)
    if not pet:
        raise HTTPException(status_code=404, detail="No pet found")

    pet["badge"] = {
        "id": badge_id,
        "selected_url": _selected_badge_url(user_id),
        "updated_at": int(time.time()),
    }
    pet["badge_url"] = _selected_badge_url(user_id)
    await user_data_manager.save_pet_data(user_id, pet.get("name", "Pet"), pet)

    return JSONResponse(content={
        "ok": True,
        "selected": _selected_badge_url(user_id),
        "pet": await _enrich_user_pet(user_id, pet),
    })


@router.post("/pets/badges/upload")
async def upload_pet_badge(request: Request, file: UploadFile = File(...)):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)

    user_id = str(user.get("id") or "")
    if not user_id:
        return JSONResponse(content={"error": "User ID not found in session"}, status_code=401)

    pet = await user_data_manager.get_pet_data_async(user_id)
    if not pet:
        raise HTTPException(status_code=404, detail="No pet found")

    png_bytes = await _uploaded_badge_to_png_bytes(file)
    await _persist_selected_badge(user_id, png_bytes)

    pet["badge"] = {
        "id": "uploaded",
        "selected_url": _selected_badge_url(user_id),
        "source": "upload",
        "updated_at": int(time.time()),
    }
    pet["badge_url"] = _selected_badge_url(user_id)
    await user_data_manager.save_pet_data(user_id, pet.get("name", "Pet"), pet)

    return JSONResponse(content={
        "ok": True,
        "selected": _selected_badge_url(user_id),
        "pet": await _enrich_user_pet(user_id, pet),
    })


@router.delete("/pets/badges")
async def delete_pet_badges(request: Request):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)

    user_id = str(user.get("id") or "")
    if not user_id:
        return JSONResponse(content={"error": "User ID not found in session"}, status_code=401)

    pet = await user_data_manager.get_pet_data_async(user_id)
    if not pet:
        raise HTTPException(status_code=404, detail="No pet found")

    await _clear_selected_badge(user_id)
    _BADGE_CANDIDATE_CACHE.pop(user_id, None)

    pet.pop("badge_url", None)
    pet.pop("badge", None)
    await user_data_manager.save_pet_data(user_id, pet.get("name", "Pet"), pet)

    return JSONResponse(content={
        "ok": True,
        "selected": "",
        "badges": [],
        "pet": await _enrich_user_pet(user_id, pet),
    })


@router.get("/pets/all")
async def get_all_pets(request: Request):
    """Get all pets for Pet Survive start menu selection"""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    
    try:
        from Systems.Functions.pets_db import pets_db
        all_user_ids = await pets_db.get_user_ids_with_pets()
        
        pets = []
        for user_id in all_user_ids:
            try:
                pet_data = await user_data_manager.get_pet_data_async(str(user_id))
                if pet_data:
                    # Get username from pet data or use fallback
                    username = pet_data.get("username") or f"User_{user_id}"
                    
                    pets.append({
                        "user_id": str(user_id),
                        "username": username,
                        "pet_name": pet_data.get("name", "Unnamed Pet"),
                        "species": pet_data.get("species", "Cat"),
                        "level": pet_data.get("level", 1),
                        "element": pet_data.get("element", "basic"),
                        "element2": pet_data.get("element2"),
                    })
            except Exception as e:
                logger.debug(f"Error loading pet for user {user_id}: {e}")
                continue
        
        return JSONResponse(content={"pets": pets})
    except Exception as e:
        logger.error(f"get_all_pets error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch pets data")


# ── Adoption ──────────────────────────────────────────────────────────────────

@router.post("/pets/adopt")
async def adopt_pet(request: Request, adoption_data: Dict[str, Any] = Body(...)):
    logger.info(f"Pet adoption request received: {adoption_data}")
    
    user = request.session.get("discord_user")
    if not user:
        logger.error("Pet adoption failed: User not logged in")
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    
    user_id = user.get("id")
    if not user_id:
        logger.error("Pet adoption failed: User ID not found in session")
        return JSONResponse(content={"error": "User ID not found in session"}, status_code=401)

    logger.info(f"Pet adoption for user {user_id} ({user.get('username', 'Unknown')})")

    try:
        # Validate required fields
        required_fields = ["category", "species", "element1", "element2", "customName"]
        for field in required_fields:
            if field not in adoption_data:
                logger.error(f"Pet adoption failed: Missing required field: {field}")
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        pet_name = adoption_data.get("customName", "").strip()
        logger.info(f"Validating pet name: '{pet_name}'")
        
        is_valid, error_msg = validate_pet_name(pet_name)
        if not is_valid:
            logger.error(f"Pet adoption failed: Invalid pet name: {error_msg}")
            raise HTTPException(status_code=400, detail=error_msg)

        # Check if user already has a pet
        existing_pet = await user_data_manager.get_pet_data_async(str(user_id))
        if existing_pet:
            logger.error(f"Pet adoption failed: User {user_id} already has a pet")
            raise HTTPException(status_code=400, detail="You already have a pet")

        # Lazy-init PetSystem (web server may start without the Discord bot)
        pet_system = getattr(request.app.state, "pet_system", None)
        if pet_system is None:
            logger.info("Initializing PetSystem for adoption")
            from Systems.Pets.pets_system import PetSystem
            pet_system = PetSystem(bot=None)
            request.app.state.pet_system = pet_system

        logger.info(f"Processing adoption with PetSystem: {adoption_data}")
        result = await pet_system.process_adoption(
            user_id=user_id,
            user_name=user.get("username", "Unknown"),
            category=adoption_data["category"],
            species_input=adoption_data["species"],
            element1=adoption_data["element1"],
            element2=adoption_data["element2"],
            custom_name=adoption_data["customName"],
        )

        logger.info(f"Adoption result: {result}")

        if result["success"]:
            pet_data = await user_data_manager.get_pet_data_async(str(user_id))
            logger.info(f"Pet adoption successful for user {user_id}: {pet_data.get('name') if pet_data else 'Unknown'}")

            # Apply the chosen battle skill if provided
            chosen_skill_id = adoption_data.get("battleSkillId", "")
            if chosen_skill_id and pet_data:
                if chosen_skill_id in SKILL_BY_ID:
                    equip_skill(pet_data, chosen_skill_id, 0)
                    await user_data_manager.save_pet_data(str(user_id), pet_data.get("name", "Pet"), pet_data)
                    logger.info(f"Equipped starting battle skill '{chosen_skill_id}' for user {user_id}")
                else:
                    logger.warning(f"Unknown battleSkillId '{chosen_skill_id}' during adoption for user {user_id}")

            # Re-fetch after potential skill save
            pet_data = await user_data_manager.get_pet_data_async(str(user_id))

            # ── GPP: emit adoption event (Observer pattern) ───────────────────
            queue = EventQueue()
            queue.push("pet_adopted", {"user_id": str(user_id), "pet_name": pet_data.get("name") if pet_data else ""})
            await queue.flush()
            # Invalidate any stale cache entry for this new pet
            if pet_data:
                _invalidate_stats_cache(pet_data)

            # ── GPP: build animation metadata (Component pattern) ─────────────
            animation = AnimationComponent.for_level_up(0, int(pet_data.get("level", 1)), {})

            _track(user, f"Adopted a new pet", detail=f"{adoption_data.get('species')} named {adoption_data.get('customName')} ({adoption_data.get('element1')}/{adoption_data.get('element2')})")
            return JSONResponse(content={"success": True, "pet": pet_data, "animation": animation})
        else:
            logger.error(f"Pet adoption failed: {result.get('message', 'Unknown error')}")
            raise HTTPException(status_code=400, detail=result.get("message", "Adoption failed"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pet adoption error for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Adoption failed. Please try again.")


# ── Rename ────────────────────────────────────────────────────────────────────

@router.post("/pets/rename")
async def rename_pet(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = user.get("id")

    try:
        new_name = (data.get("name") or "").strip()
        is_valid, err = validate_pet_name(new_name)
        if not is_valid:
            raise HTTPException(status_code=400, detail=err)

        pet = await user_data_manager.get_pet_data_async(str(user_id))
        if not pet:
            raise HTTPException(status_code=404, detail="No pet found")

        # Update name
        pet["name"] = new_name

        # Update battle actions if provided
        actions = data.get("actions", {})
        if actions:
            if "action_labels" not in pet:
                pet["action_labels"] = {}
            for key in ("Attack", "Defense", "Charge"):
                val = (actions.get(key) or "").strip()
                if val:
                    pet["action_labels"][key.lower()] = val

        await user_data_manager.save_pet_data(str(user_id), user.get("username", "Unknown"), pet)
        logger.info(f"Pet renamed for user {user_id}: {new_name}")
        _invalidate_stats_cache(pet)

        # ── GPP: emit rename event (Observer pattern handles task tracking) ───
        queue = EventQueue()
        queue.push("pet_renamed", {
            "user_id": str(user_id),
            "new_name": new_name,
            "actions": actions,
        })
        await queue.flush()

        # ── GPP: build animation metadata (Component pattern) ─────────────
        animation = AnimationComponent.for_ui_update("flash", 400)

        return JSONResponse(content={"success": True, "name": new_name, "animation": animation})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"rename_pet error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Rename failed.")


# ── Kill (delete) ─────────────────────────────────────────────────────────────

@router.delete("/pets/kill")
async def kill_pet(request: Request):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = user.get("id")

    try:
        pet = await user_data_manager.get_pet_data_async(str(user_id))
        if not pet:
            raise HTTPException(status_code=404, detail="No pet found")

        # ── GPP: invalidate stats cache before deletion ───────────────────────
        _invalidate_stats_cache(pet)

        success = await user_data_manager.delete_pet_data(str(user_id))
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete pet")

        logger.info(f"Pet killed for user {user_id}")

        # ── GPP: emit pet_released event (Observer pattern) ───────────────────
        queue = EventQueue()
        queue.push("pet_released", {"user_id": str(user_id), "pet_name": pet.get("name")})
        await queue.flush()

        # ── GPP: build animation metadata (Component pattern) ─────────────
        animation = AnimationComponent.for_ui_update("fade_out", 600)

        return JSONResponse(content={"success": True, "animation": animation})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"kill_pet error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to release pet.")


# ── Train ─────────────────────────────────────────────────────────────────────

@router.post("/pets/train")
async def train_pet(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    # ── Cooldown check ────────────────────────────────────────────────────────
    on_cd, remaining = await _acheck_cooldown("train", user_id)
    if on_cd:
        return JSONResponse(
            content={"error": f"⏳ Training is on cooldown. Try again in {remaining}s."},
            status_code=429,
        )

    try:
        pet = await user_data_manager.get_pet_data_async(user_id)
        if not pet:
            raise HTTPException(status_code=404, detail="No pet found")

        difficulty = data.get("difficulty", "Easy")
        stat       = data.get("stat", "").upper()

        if difficulty not in ("Easy", "Average", "Hard"):
            raise HTTPException(status_code=400, detail="Invalid difficulty")

        valid_stats = ("ATT", "DEF", "INT", "DEX", "HAP", "ENE")
        if stat not in valid_stats:
            raise HTTPException(status_code=400, detail="Invalid stat. Choose ATT, DEF, INT, DEX, HAP, or ENE.")

        # Difficulty config: (success_chance, stat_multiplier)
        diff_cfg = {
            "Easy":    (0.75, 1),
            "Average": (0.60, 3),
            "Hard":    (0.45, 5),
        }
        success_chance, stat_mult = diff_cfg[difficulty]

        # Equipment multiplier scales the stat change
        equip_mult = int(StatsCalculator.get_equipment_xp_multiplier(pet))
        equip_mult = max(1, equip_mult)
        change_amount = stat_mult * equip_mult

        # ── Ability: Training Scholar (int_train_xp) ──────────────────────────
        # On success: adds bonus stat points gained.
        # On failure: blocks that many points from being lost.
        from Systems.Pets.Logic.ability_tree import get_ability_effect as _get_ability_effect
        train_bonus = int(_get_ability_effect(pet, "train_bonus"))

        import random
        success = random.random() < success_chance

        current_val = int(pet.get(stat, 0))
        if success:
            total_gain = change_amount + train_bonus
            pet[stat] = current_val + total_gain
            bonus_str = f" (+{train_bonus} Training Scholar bonus)" if train_bonus else ""
            outcome = (
                f"💪 Training successful! **{stat}** increased by **+{total_gain}**"
                f" ({stat_mult} × {equip_mult}x equipment{bonus_str}).\n"
                f"**{stat}**: {current_val} → {pet[stat]}"
            )
            actual_delta = total_gain
        else:
            effective_loss = max(0, change_amount - train_bonus)
            new_val = max(1, current_val - effective_loss)
            actual_loss = current_val - new_val
            pet[stat] = new_val
            block_str = f" (Training Scholar blocked {train_bonus})" if train_bonus else ""
            outcome = (
                f"😓 Training failed. **{stat}** decreased by **-{actual_loss}**"
                f" ({stat_mult} × {equip_mult}x equipment{block_str}).\n"
                f"**{stat}**: {current_val} → {pet[stat]}"
            )
            actual_delta = -actual_loss

        await user_data_manager.save_pet_data(user_id, pet.get("name", "Pet"), pet)
        await _aset_cooldown("train", user_id)

        # ── GPP: emit event via EventBus (Observer pattern) ───────────────────
        queue = EventQueue()
        queue.push("pet_trained", {"user_id": user_id, "stat": stat, "delta": actual_delta})
        await queue.flush()

        # ── GPP: invalidate stats cache (Object Pool pattern) ─────────────────
        _invalidate_stats_cache(pet)

        # ── GPP: build animation metadata (Component pattern) ─────────────────
        animation = AnimationComponent.for_train(stat, success, actual_delta)

        result = {
            "success": success,
            "outcome": outcome,
            "stat": stat,
            "change": actual_delta,
            "new_value": int(pet.get(stat, 0)),
            "animation": animation,
        }
        result["pet"] = _enrich_pet(await user_data_manager.get_pet_data_async(user_id))
        return JSONResponse(content=result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"train_pet error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Training failed.")


# ── Mission ───────────────────────────────────────────────────────────────────

@router.post("/pets/mission")
async def run_mission(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    # ── Cooldown check ────────────────────────────────────────────────────────
    on_cd, remaining = await _acheck_cooldown("mission", user_id)
    if on_cd:
        return JSONResponse(
            content={"error": f"⏳ Mission is on cooldown. Try again in {remaining}s."},
            status_code=429,
        )

    try:
        pet = await user_data_manager.get_pet_data_async(user_id)
        if not pet:
            raise HTTPException(status_code=404, detail="No pet found")

        difficulty = data.get("difficulty", "Easy")
        gamble_xp  = int(data.get("gamble_xp", 0) or 0)
        if difficulty not in ("Easy", "Average", "Hard"):
            raise HTTPException(status_code=400, detail="Invalid difficulty")

        import random
        from Systems.Pets.Logic.pet_brain import LootCalculator
        from Systems.Pets.pets_system import add_experience

        success_chance = {"Easy": 0.7, "Average": 0.5, "Hard": 0.3}[difficulty]
        base_xp_map    = {"Easy": 100, "Average": 250, "Hard": 500}

        pet_level = int(pet.get("level", 1))
        outcome_lines = []
        level_up = None

        # Cooldown is consumed regardless of success/failure
        await _aset_cooldown("mission", user_id)

        if random.random() < success_chance:
            scaled_xp = _level_scaled_xp(base_xp_map[difficulty], pet_level)

            # ── Ability: Mission Expert (int_mission_xp) — xp_multiplier ─────
            from Systems.Pets.Logic.ability_tree import get_ability_effect as _get_ability_effect
            mission_xp_mult = _get_ability_effect(pet, "xp_multiplier", source="mission")
            if mission_xp_mult != 1.0:
                scaled_xp = int(scaled_xp * mission_xp_mult)

            xp = scaled_xp + gamble_xp
            outcome_lines.append(f"✅ Mission successful! Gained {xp} XP (Lv.{pet_level} bonus applied).")

            # Key loot
            keys = LootCalculator.get_key_loot(difficulty)
            for k in keys:
                added, msg = await LootCalculator.add_item_to_inventory(int(user_id), k, pet)
                if added and msg:
                    outcome_lines.append(msg.strip())

            _, lvl_data = await add_experience(int(user_id), xp, "mission")
            if lvl_data and lvl_data.get("new_level", 0) > lvl_data.get("old_level", 0):
                level_up = lvl_data
                outcome_lines.append(f"🎉 Level Up! Now level {lvl_data['new_level']}!")

            # ── GPP: emit event + animation ───────────────────────────────────
            queue = EventQueue()
            queue.push("mission_completed", {"user_id": user_id, "difficulty": difficulty, "xp": xp})
            await queue.flush()
            _invalidate_stats_cache(pet)
            animation = AnimationComponent.for_mission(True, xp, difficulty)

            result = {"success": True, "outcome": "\n".join(outcome_lines), "xp": xp, "level_up": level_up, "animation": animation}
        else:
            outcome_lines.append("❌ Mission failed.")
            level_down = None
            if gamble_xp > 0:
                _, res = await LootCalculator.apply_xp_change(int(user_id), -gamble_xp, "mission_fail")
                outcome_lines.append(f"Lost {gamble_xp} XP.")
                if res and res.get("new_level", 0) < res.get("old_level", 0):
                    level_down = res
                    outcome_lines.append(f"📉 Level Down! Now level {res['new_level']}.")

            # ── GPP: emit event + animation ───────────────────────────────────
            _invalidate_stats_cache(pet)
            animation = AnimationComponent.for_mission(False, -gamble_xp, difficulty)

            result = {"success": False, "outcome": "\n".join(outcome_lines), "xp": -gamble_xp, "level_up": None, "level_down": level_down, "animation": animation}

        result["pet"] = _enrich_pet(await user_data_manager.get_pet_data_async(user_id))
        return JSONResponse(content=result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"run_mission error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Mission failed.")


# ── Play ──────────────────────────────────────────────────────────────────────

PLAY_LOCATIONS = ["Camp","Bonfire","Beach","Forest","Hot Air Balloon","Cruiseship","Mountain","Gym","Graveyard","Festival","Glacier","Pyramids"]

@router.post("/pets/play")
async def play_pet(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    # ── Cooldown check ────────────────────────────────────────────────────────
    on_cd, remaining = await _acheck_cooldown("play", user_id)
    if on_cd:
        return JSONResponse(
            content={"error": f"⏳ Play is on cooldown. Try again in {remaining}s."},
            status_code=429,
        )

    try:
        pet = await user_data_manager.get_pet_data_async(user_id)
        if not pet:
            raise HTTPException(status_code=404, detail="No pet found")

        location = data.get("location", "")
        if location not in PLAY_LOCATIONS:
            raise HTTPException(status_code=400, detail="Invalid location")

        from Systems.Pets.Logic.pet_brain import LootCalculator
        from Systems.Pets.pets_system import add_experience
        import json as _json, os as _os

        # Load locations data (cached after first read)
        loc_path = _os.path.join(project_root, "Systems", "Pets", "Logic", "locations_play.json")
        loc_data = await _load_json_cached(loc_path)

        loc_info       = loc_data.get("locations", {}).get(location, {})
        place_specials = loc_info.get("Special", {})
        pet_e1         = (pet.get("element") or "basic").lower()
        pet_e2         = (pet.get("element2") or "").lower()
        level          = int(pet.get("level", 1))

        xp, key_names = LootCalculator.calculate_play_loot(pet_e1, pet_e2, place_specials, level)

        # ── Ability: Playful Learner (int_play_xp) — xp_multiplier for play ──
        from Systems.Pets.Logic.ability_tree import get_ability_effect as _get_ability_effect
        play_xp_mult = _get_ability_effect(pet, "xp_multiplier", source="play")
        if play_xp_mult != 1.0:
            xp = int(xp * play_xp_mult)

        outcome_lines = [f"🎮 {pet['name']} played at {location}!"]

        # Award keys
        for kn in key_names:
            k = {"name": kn, "type": "Key", "count": 1}
            added, msg = await LootCalculator.add_item_to_inventory(int(user_id), k, pet)
            if added and msg:
                outcome_lines.append(msg.strip())

        # Award XP and set cooldown
        _, lvl_data = await add_experience(int(user_id), xp, "play")
        await _aset_cooldown("play", user_id)
        outcome_lines.append(f"✨ Gained {xp} XP.")
        level_up = None
        if lvl_data and lvl_data.get("new_level", 0) > lvl_data.get("old_level", 0):
            level_up = lvl_data
            outcome_lines.append(f"🎉 Level Up! Now level {lvl_data['new_level']}!")

        # ── GPP: emit event + animation ───────────────────────────────────────
        queue = EventQueue()
        queue.push("play_completed", {"user_id": user_id, "location": location, "xp": xp})
        await queue.flush()
        _invalidate_stats_cache(pet)
        animation = AnimationComponent.for_play(
            location, xp,
            (pet.get("element") or "basic").lower(),
            (pet.get("element2") or None),
        )

        result = {
            "success": True,
            "outcome": "\n".join(outcome_lines),
            "xp": xp,
            "level_up": level_up,
            "animation": animation,
            "pet": _enrich_pet(await user_data_manager.get_pet_data_async(user_id))
        }
        _track(user, f"Pet played at {location}", detail=f"+{xp} XP | {pet.get('name','?')}")
        return JSONResponse(content=result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"play_pet error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Play failed.")


# ── Quest ─────────────────────────────────────────────────────────────────────

QUEST_LOCATIONS   = ["Camp","Bonfire","Beach","Forest","Hot Air Balloon","Cruiseship","Mountain","Gym","Graveyard","Festival","Glacier","Pyramids"]
QUEST_DIFFICULTIES = ["Apprentice","Journeyman","Senior"]

# In-memory quest sessions keyed by user_id
_quest_sessions: dict = {}

def _strip_hints(text: str) -> str:
    import re
    return re.sub(r'\s*\(.*?\)\s*', '', text).strip()

def _next_stage_payload(session: dict, next_idx: int, outcome_msg: str = "") -> dict:
    """Build the JSON payload for the next quest stage."""
    stages = session["stages"]
    stage  = stages[next_idx]
    return {
        "stage_idx":       next_idx,
        "total_stages":    len(stages),
        "stage_name":      stage["stage_name"],
        "event":           _strip_hints(stage["event"]),
        "choices":         {k: _strip_hints(v) for k, v in stage["choices"].items()},
        "outcome_msg":     outcome_msg,
        "xp_so_far":       session["xp"],
        "done":            False,
        "battle_required": False,
    }

@router.post("/pets/quest/start")
async def quest_start(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    # ── Cooldown check ────────────────────────────────────────────────────────
    on_cd, remaining = await _acheck_cooldown("quest", user_id)
    if on_cd:
        return JSONResponse(
            content={"error": f"⏳ Quest is on cooldown. Try again in {remaining}s."},
            status_code=429,
        )

    try:
        pet = await user_data_manager.get_pet_data_async(user_id)
        if not pet:
            raise HTTPException(status_code=404, detail="No pet found")

        location   = data.get("location", "")
        difficulty = data.get("difficulty", "Apprentice")
        if location not in QUEST_LOCATIONS:
            raise HTTPException(status_code=400, detail="Invalid location")
        if difficulty not in QUEST_DIFFICULTIES:
            raise HTTPException(status_code=400, detail="Invalid difficulty")

        from Systems.Pets.PetGames.quests import generate_or_load_quest
        import random as _random

        quest_data = generate_or_load_quest(location, difficulty)
        if not quest_data or not quest_data.get("stages"):
            raise HTTPException(status_code=503, detail="Could not generate quest. Please try again.")

        # Build ordered stage list (same logic as QuestView.__init__)
        all_stages = quest_data["stages"]
        ordered = []
        ordered.append(next((s for s in all_stages if s["stage_name"] == "Entering Location"), None))
        ordered.append(next((s for s in all_stages if s["stage_name"] == "Avoiding Hostile Pets" and s.get("sub_type") == "scare_off"), None))
        ordered.append(next((s for s in all_stages if s["stage_name"] == "Looking Around"), None))
        loot_stages = [s for s in all_stages if s["stage_name"] == "Locating a FREE to open Loot Chest"]
        if loot_stages:
            ordered.append(_random.choice(loot_stages))
        ordered.append(next((s for s in all_stages if s["stage_name"] == "Avoiding Hostile Pets" and s.get("sub_type") == "evade"), None))
        ordered.append(next((s for s in all_stages if s["stage_name"] == "Exiting Location"), None))
        stages = [s for s in ordered if s is not None]

        # Generate hostile pet for the encounter stages
        from Systems.Pets.Logic.pet_brain import LootCalculator
        hostile_pet = LootCalculator.generate_hostile_pet(pet, difficulty)

        # Replace placeholder in all stages
        boss_name = f"{location} {hostile_pet['species']}"
        for s in stages:
            if "%%HOSTILE_PET%%" in s.get("event", ""):
                s["event"] = s["event"].replace("%%HOSTILE_PET%%", boss_name)

        session = {
            "pet":          pet,
            "pet_level":    int(pet.get("level", 1)),
            "stages":       stages,
            "stage_idx":    0,
            "difficulty":   difficulty,
            "location":     location,
            "hostile_pet":  hostile_pet,
            "hostile_defeated": False,
            "xp":           0,
            "loot":         [],
            "event_log":    [],
            "done":         False,
            "success":      False,
        }
        _quest_sessions[user_id] = session
        await _aset_cooldown("quest", user_id)

        # ── GPP: invalidate stats cache + emit event ──────────────────────────
        _invalidate_stats_cache(pet)
        queue = EventQueue()
        queue.push("quest_started", {"user_id": user_id, "location": location, "difficulty": difficulty})
        await queue.flush()

        stage = stages[0]

        # ── GPP: build animation metadata (Component pattern) ─────────────
        animation = AnimationComponent.for_ui_update("quest_start", 600)

        return JSONResponse(content={
            "stage_idx":       0,
            "total_stages":    len(stages),
            "stage_name":      stage["stage_name"],
            "event":           _strip_hints(stage["event"]),
            "choices":         {k: _strip_hints(v) for k, v in stage["choices"].items()},
            "outcome_msg":     "",
            "xp_so_far":       0,
            "done":            False,
            "battle_required": False,
            "hostile_pet": {
                "name":    hostile_pet.get("name", "Wild Creature"),
                "species": hostile_pet.get("species", "Creature"),
                "level":   hostile_pet.get("level", 1),
            },
            "animation": animation,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"quest_start error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pets/quest/choice")
async def quest_choice(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    session = _quest_sessions.get(user_id)
    if not session or session.get("done"):
        raise HTTPException(status_code=400, detail="No active quest. Start a new one.")

    if session.get("pending_battle"):
        raise HTTPException(status_code=400, detail="A battle is in progress. Resolve it first.")

    try:
        choice_num = int(data.get("choice", 1))
        import random as _random
        from Systems.Pets.Logic.pet_brain import LootCalculator

        stages   = session["stages"]
        idx      = session["stage_idx"]
        pet      = session["pet"]
        diff     = session["difficulty"]
        location = session["location"]

        if idx >= len(stages):
            return await _quest_finish(user_id, session, True)

        stage      = stages[idx]
        stage_name = stage["stage_name"]
        sub_type   = stage.get("sub_type")

        # Auto-skip evade if hostile already defeated
        if stage_name == "Avoiding Hostile Pets" and sub_type == "evade" and session["hostile_defeated"]:
            session["stage_idx"] += 1
            idx += 1
            if idx >= len(stages):
                return await _quest_finish(user_id, session, True)
            stage      = stages[idx]
            stage_name = stage["stage_name"]
            sub_type   = stage.get("sub_type")

        # Stat check - Updated mapping for better thematic coherence
        stat_map = {1: ("ATT","DEF"), 2: ("DEX","INT"), 3: ("ENE","HAP")}
        stat1, stat2 = stat_map.get(choice_num, ("ATT","DEF"))
        pet_skill    = (pet.get(stat1, 0) + pet.get(stat2, 0)) / 2

        diff_mult    = {"Apprentice": 0.8, "Journeyman": 1.0, "Senior": 1.2}[diff]
        stage_mod    = stage.get("difficulty_modifier", 1.0)
        required     = 10 * diff_mult * stage_mod
        success_rate = min(95, max(5, int((pet_skill / max(1, required)) * 50)))
        success      = _random.randint(1, 100) <= success_rate

        outcome_msg  = ""
        xp_gain      = 0
        loot_gained  = []
        quest_failed = False

        # ── Stage-specific logic ──────────────────────────────────────────────
        if stage_name == "Entering Location":
            success      = True
            success_rate = 100
            xp_gain      = 5
            outcome_msg  = f"You enter {location} and begin your quest."

        elif stage_name == "Avoiding Hostile Pets":
            boss_name  = f"{location} {session['hostile_pet']['species']}"
            skill_inf  = ((pet_skill - required) / max(1, required)) * 15
            if sub_type == "scare_off":
                success_rate = min(95, max(5, 65 + skill_inf))
            else:
                success_rate = min(95, max(5, 50 + skill_inf))
            success = _random.randint(1, 100) <= success_rate

            if success:
                xp_gain = max(10, int(pet_skill * 1.5))
                if sub_type == "scare_off":
                    outcome_msg = f"✅ You scared off the {boss_name}! +{xp_gain} XP"
                    session["hostile_defeated"] = True
                else:
                    outcome_msg = f"✅ You evaded the {boss_name}! +{xp_gain} XP"
            else:
                # Signal the frontend to run a real battle
                session["pending_battle"]   = True
                session["pending_sub_type"] = sub_type
                session["stage_idx"] += 1   # advance past this stage — battle resolves it
                session["event_log"].append({
                    "stage":        stage_name,
                    "choice":       _strip_hints(stage["choices"].get(str(choice_num), "")),
                    "success":      False,
                    "success_rate": round(success_rate, 1),
                    "outcome":      f"Failed to {'scare off' if sub_type=='scare_off' else 'evade'} the {boss_name} — battle triggered!",
                })
                return JSONResponse(content={
                    "done":            False,
                    "battle_required": True,
                    "boss_name":       boss_name,
                    "hostile_pet":     session["hostile_pet"],
                    "outcome_msg":     f"⚔️ You failed to {'scare off' if sub_type=='scare_off' else 'evade'} the {boss_name}! Prepare to fight!",
                    "xp_so_far":       session["xp"],
                })

        elif stage_name == "Locating a FREE to open Loot Chest":
            success_rate = min(95, max(5, int((pet_skill / max(1, required)) * 60)))
            success      = _random.randint(1, 100) <= success_rate
            if not success:
                outcome_msg = "⚠️ You fumbled and couldn't open the chest."
            else:
                loot_mult = {"Apprentice": 1, "Journeyman": 2, "Senior": 3}[diff]
                base_amt  = _random.randint(1, 3) * loot_mult
                if sub_type == "mimic":
                    if choice_num == 1:  # ATT/DEF choice - best for fighting mimics
                        loot_amt    = base_amt * 2
                        outcome_msg = "⚔️ Your forceful approach revealed the chest's true nature - it was a disguised creature! You defeated it and claimed double loot!"
                    else:
                        loot_amt    = 0
                        outcome_msg = "🪤 The chest suddenly snapped shut with rows of teeth! You barely escaped the creature's jaws but found no treasure."
                else:  # real_chest
                    double_choice = stage.get("double_loot_choice", -1)
                    loot_amt      = base_amt * 2 if choice_num == double_choice else base_amt
                    if choice_num == double_choice:
                        outcome_msg = f"📦 Your skillful approach paid off! You found a hidden compartment with double loot!"
                    else:
                        outcome_msg = f"📦 You successfully opened the chest and found treasure inside!"

                if loot_amt > 0:
                    loot_gained = _generate_quest_loot_web(loot_amt, diff)
                    session["loot"].extend(loot_gained)
                    session["loot_earned"] = True
                    names = [f"{i.get('count',1)}x {i['name']}" for i in loot_gained]
                    outcome_msg += f" Got: {', '.join(names)}"

        else:  # Looking Around, Exiting Location, etc.
            if success:
                xp_gain     = max(10, int(pet_skill * 0.5 + 5))
                outcome_msg = f"✅ Success! +{xp_gain} XP"
            else:
                xp_gain     = 3
                outcome_msg = "⚠️ You struggled but made it through."

        session["xp"] += xp_gain
        session["event_log"].append({
            "stage":        stage_name,
            "choice":       _strip_hints(stage["choices"].get(str(choice_num), "")),
            "success":      success,
            "success_rate": round(success_rate, 1),
            "outcome":      outcome_msg,
        })
        session["stage_idx"] += 1

        if quest_failed:
            return await _quest_finish(user_id, session, False)

        next_idx = session["stage_idx"]
        if next_idx >= len(stages):
            return await _quest_finish(user_id, session, True)

        next_stage = stages[next_idx]
        if (next_stage["stage_name"] == "Avoiding Hostile Pets"
                and next_stage.get("sub_type") == "evade"
                and session["hostile_defeated"]):
            session["stage_idx"] += 1
            next_idx += 1
            if next_idx >= len(stages):
                return await _quest_finish(user_id, session, True)
            next_stage = stages[next_idx]

        # ── GPP: invalidate stats cache + emit event ──────────────────────────
        _invalidate_stats_cache(pet)
        queue = EventQueue()
        queue.push("quest_choice", {"user_id": user_id, "stage": stage_name, "success": success, "xp": xp_gain})
        await queue.flush()

        # ── GPP: build animation metadata (Component pattern) ─────────────
        animation = AnimationComponent.for_ui_update("choice_result", 500, {"success": success})

        return JSONResponse(content={
            "stage_idx":       next_idx,
            "total_stages":    len(stages),
            "stage_name":      next_stage["stage_name"],
            "event":           _strip_hints(next_stage["event"]),
            "choices":         {k: _strip_hints(v) for k, v in next_stage["choices"].items()},
            "outcome_msg":     outcome_msg,
            "xp_so_far":       session["xp"],
            "done":            False,
            "battle_required": False,
            "animation": animation,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"quest_choice error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pets/quest/battle_result")
async def quest_battle_result(request: Request, data: Dict[str, Any] = Body(...)):
    """Called after the web battle resolves to continue the quest."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    session = _quest_sessions.get(user_id)
    if not session or session.get("done"):
        raise HTTPException(status_code=400, detail="No active quest.")
    if not session.get("pending_battle"):
        raise HTTPException(status_code=400, detail="No battle pending.")

    try:
        won      = bool(data.get("won", False))
        xp_bonus = int(data.get("xp_gained", 0))
        sub_type = session.pop("pending_sub_type", "scare_off")
        session["pending_battle"] = False

        if won:
            session["hostile_defeated"] = True
            session["xp"] += xp_bonus
            outcome_msg = f"⚔️ You defeated the enemy and earned {xp_bonus} XP!"
        else:
            session["event_log"].append({
                "stage":        "Battle",
                "choice":       "Fight",
                "success":      False,
                "success_rate": 50,
                "outcome":      "💀 You were defeated in battle. Quest failed.",
            })
            return await _quest_finish(user_id, session, False)

        next_idx = session["stage_idx"]
        stages   = session["stages"]

        if next_idx >= len(stages):
            return await _quest_finish(user_id, session, True)

        next_stage = stages[next_idx]
        if (next_stage["stage_name"] == "Avoiding Hostile Pets"
                and next_stage.get("sub_type") == "evade"
                and session["hostile_defeated"]):
            session["stage_idx"] += 1
            next_idx += 1
            if next_idx >= len(stages):
                return await _quest_finish(user_id, session, True)
            next_stage = stages[next_idx]

        # ── GPP: invalidate stats cache + emit event ──────────────────────────
        pet = session.get("pet", {})
        _invalidate_stats_cache(pet)
        queue = EventQueue()
        queue.push("quest_battle_result", {"user_id": user_id, "won": won, "xp": xp_bonus})
        await queue.flush()

        # ── GPP: build animation metadata (Component pattern) ─────────────
        animation = AnimationComponent.for_battle_action("attack", xp_bonus, True, 1.0)

        return JSONResponse(content={
            "stage_idx":       next_idx,
            "total_stages":    len(stages),
            "stage_name":      next_stage["stage_name"],
            "event":           _strip_hints(next_stage["event"]),
            "choices":         {k: _strip_hints(v) for k, v in next_stage["choices"].items()},
            "outcome_msg":     outcome_msg,
            "xp_so_far":       session["xp"],
            "done":            False,
            "battle_required": False,
            "animation": animation,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"quest_battle_result error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pets/quest/abandon")
async def quest_abandon(request: Request):
    """Abandon the current quest, awarding any XP/loot already earned."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))
    session = _quest_sessions.pop(user_id, None)
    if session and not session.get("done"):
        xp   = session.get("xp", 0)
        loot = session.get("loot", []) if session.get("loot_earned") else []
        if xp > 0:
            from Systems.Pets.pets_system import add_experience
            await add_experience(int(user_id), xp, "quest_partial")
        if loot:
            from Systems.Pets.Logic.pet_brain import LootCalculator
            pet = session.get("pet", {})
            for item in loot:
                await LootCalculator.add_item_to_inventory(int(user_id), item, pet)

    # ── GPP: emit quest_abandoned event (Observer pattern) ───────────────────
    queue = EventQueue()
    queue.push("quest_abandoned", {"user_id": user_id})
    await queue.flush()

    # ── GPP: build animation metadata (Component pattern) ─────────────
    animation = AnimationComponent.for_ui_update("fade_out", 400)

    return JSONResponse(content={"ok": True, "animation": animation})


def _generate_quest_loot_web(amount: int, difficulty: str) -> list:
    import random as _random
    from Systems.Pets.Logic.pet_brain import LootCalculator
    loot = []
    types = ["Material","Gem","Monster","Potion"]
    for _ in range(amount):
        t    = _random.choice(types)
        item = None
        if t == "Material": item = LootCalculator.get_material_loot_item(difficulty, bypass_chance=True)
        elif t == "Gem":    item = LootCalculator.get_gem_loot_item(difficulty, bypass_chance=True)
        elif t == "Monster":item = LootCalculator.get_monster_loot_item(difficulty, bypass_chance=True)
        elif t == "Potion": item = LootCalculator.get_potion_loot(difficulty, bypass_chance=True)
        if item:
            found = next((x for x in loot if x["name"] == item["name"] and x["type"] == item["type"]), None)
            if found: found["count"] = found.get("count", 1) + 1
            else:     item["count"] = 1; loot.append(item)
    return loot


async def _quest_finish(user_id: str, session: dict, success: bool):
    from Systems.Pets.Logic.pet_brain import LootCalculator
    from Systems.Pets.pets_system import add_experience

    session["done"]    = True
    session["success"] = success

    raw_xp = session["xp"]
    loot   = session["loot"] if session.get("loot_earned") else []
    pet    = session["pet"]

    # Apply level-based scaling to the total quest XP earned
    pet_level  = session.get("pet_level", int(pet.get("level", 1)))
    xp         = _level_scaled_xp(raw_xp, pet_level) if raw_xp > 0 else 0

    if xp > 0:
        await add_experience(int(user_id), xp, "quest")

    if loot:
        for item in loot:
            await LootCalculator.add_item_to_inventory(int(user_id), item, pet)

    # ── GPP: emit quest event + invalidate cache ──────────────────────────────
    pet_after = await user_data_manager.get_pet_data_async(user_id)
    if pet_after:
        _invalidate_stats_cache(pet_after)
    if success:
        queue = EventQueue()
        queue.push("quest_completed", {"user_id": user_id, "xp": xp, "loot_count": len(loot)})
        await queue.flush()

    refreshed  = _enrich_pet(await user_data_manager.get_pet_data_async(user_id))
    loot_names = [f"{i.get('count',1)}x {i['name']}" for i in loot]

    return JSONResponse(content={
        "done":      True,
        "success":   success,
        "xp":        xp,
        "raw_xp":    raw_xp,
        "loot":      loot_names,
        "event_log": session["event_log"],
        "pet":       refreshed,
    })


# ── Loot Market ───────────────────────────────────────────────────────────────

@router.post("/pets/loot/open")
async def loot_open(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    try:
        pet = await user_data_manager.get_pet_data_async(user_id)
        if not pet:
            raise HTTPException(status_code=404, detail="No pet found")

        chest_type    = data.get("chest", "")
        amount        = max(1, min(10, int(data.get("amount", 1) or 1)))
        selected_type = data.get("selected_type") or None

        if chest_type not in ("chest1", "chest2", "chest3", "chest4"):
            raise HTTPException(status_code=400, detail="Invalid chest type")

        if chest_type == "chest4" and selected_type not in (
            "Material", "Gem", "Monster", "Potion",
            "Ring", "Helmet", "Armor", "Boots", "Shield",
            "Dagger", "Katana", "Sword", "Axe", "Hammer", "Bow"
        ):
            raise HTTPException(status_code=400, detail="Chest 4 requires a valid item type selection")

        # chest4 can only be opened 1 at a time (costs all 3 key types)
        if chest_type == "chest4":
            amount = 1

        from Systems.Pets.Logic.pet_brain import LootCalculator

        messages, awarded_items = await LootCalculator.open_chest(
            int(user_id),
            chest_type,
            amount,
            selected_type
        )

        # Check for error messages (errors are the first entry when no items)
        if messages and not awarded_items:
            first = messages[0]
            if any(first.startswith(p) for p in ("Not enough", "Invalid", "You don't have", "Error:")):
                raise HTTPException(status_code=400, detail=first)

        # ── GPP: invalidate stats cache + emit event ──────────────────────────
        pet_after = await user_data_manager.get_pet_data_async(user_id)
        if pet_after:
            _invalidate_stats_cache(pet_after)
        queue = EventQueue()
        queue.push("chest_opened", {"user_id": user_id, "chest_type": chest_type, "amount": amount, "items": awarded_items})
        await queue.flush()

        # ── GPP: build loot animation metadata ───────────────────────────────
        animation = AnimationComponent.for_loot(awarded_items)

        # Re-fetch pet to get updated inventory/XP for the response
        refreshed = _enrich_pet(await user_data_manager.get_pet_data_async(user_id))

        logger.info(f"Loot opened for user {user_id}: {chest_type} x{amount} -> {[i.get('name') for i in awarded_items]}")
        return JSONResponse(content={
            "success": True,
            "chest":   chest_type,
            "amount":  amount,
            "items":   awarded_items,
            "messages": messages,
            "animation": animation,
            "pet":     refreshed,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"loot_open error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to open chest.")


# ── Open chest from inventory (no keys required) ──────────────────────────────

@router.post("/pets/inventory/open-chest")
async def inventory_open_chest(request: Request, data: Dict[str, Any] = Body(...)):
    """
    Open a chest that is already in the user's inventory (e.g. task reward).
    Does NOT require keys — the chest itself is consumed from inventory.
    chest4 requires selected_type.
    """
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    try:
        chest_type    = data.get("chest", "")
        selected_type = data.get("selected_type") or None

        if chest_type not in ("chest1", "chest2", "chest3", "chest4"):
            raise HTTPException(status_code=400, detail="Invalid chest type")
        if chest_type == "chest4" and selected_type not in (
            "Material", "Gem", "Monster", "Potion",
            "Ring", "Helmet", "Armor", "Boots", "Shield",
            "Dagger", "Katana", "Sword", "Axe", "Hammer", "Bow"
        ):
            raise HTTPException(status_code=400, detail="Chest 4 requires a valid item type selection")

        pet = await user_data_manager.get_pet_data_async(user_id)
        if not pet:
            raise HTTPException(status_code=404, detail="No pet found")

        inventory = pet.get("inventory", [])
        inventory = user_data_manager._consolidate_inventory(inventory)

        # Map chest_type to item name
        chest_name_map = {"chest1": "Chest1", "chest2": "Chest2", "chest3": "Chest3", "chest4": "Chest4"}
        chest_item_name = chest_name_map[chest_type]

        # Find chest in inventory (case-insensitive name match)
        chest_item = next(
            (it for it in inventory if it.get("type") == "Chest" and it.get("name", "").lower() == chest_item_name.lower()),
            None
        )
        if not chest_item or chest_item.get("count", 0) < 1:
            raise HTTPException(status_code=400, detail=f"You don't have a {chest_item_name} in your inventory.")

        # Deduct 1 chest from inventory
        if chest_item.get("count", 1) <= 1:
            inventory = [it for it in inventory if not (it.get("type") == "Chest" and it.get("name", "").lower() == chest_item_name.lower())]
        else:
            chest_item["count"] -= 1

        pet["inventory"] = inventory
        await user_data_manager.save_pet_data(user_id, pet.get("name", "Pet"), pet)

        # Generate loot (same rarity tiers as open_chest, but no key cost)
        items_to_add = []
        if chest_type == "chest1":
            item = LootCalculator.get_item_by_rarity(["Common", "Uncommon"])
            if item: items_to_add.append(item)
        elif chest_type == "chest2":
            item = LootCalculator.get_item_by_rarity(["Rare"])
            if item: items_to_add.append(item)
        elif chest_type == "chest3":
            item = LootCalculator.get_item_by_rarity(["Epic"])
            if item: items_to_add.append(item)
        elif chest_type == "chest4":
            sel_item = LootCalculator.get_item_by_rarity(
                ["Common", "Uncommon", "Rare", "Epic", "Mythic"], item_type=selected_type
            )
            if sel_item: items_to_add.append(sel_item)
            # Bonus random item: any rarity Common–Mythic, no Hats
            bonus = LootCalculator.get_item_by_rarity(["Common", "Uncommon", "Rare", "Epic", "Mythic"])
            if bonus: items_to_add.append(bonus)

        awarded_items = []
        messages = []
        for item in items_to_add:
            added, msg = await LootCalculator.add_item_to_inventory(int(user_id), item, None)
            if added:
                awarded_items.append(item)
                if msg:
                    messages.append(msg.strip())

        refreshed = _enrich_pet(await user_data_manager.get_pet_data_async(user_id))
        logger.info(f"Inventory chest opened for {user_id}: {chest_type} -> {[i.get('name') for i in awarded_items]}")

        # ── GPP: invalidate stats cache + emit event + animation ──────────────
        pet_after = await user_data_manager.get_pet_data_async(user_id)
        if pet_after:
            _invalidate_stats_cache(pet_after)
        queue = EventQueue()
        queue.push("chest_opened", {"user_id": user_id, "chest_type": chest_type, "amount": 1, "items": awarded_items})
        await queue.flush()
        animation = AnimationComponent.for_loot(awarded_items)

        return JSONResponse(content={
            "success":   True,
            "chest":     chest_type,
            "items":     awarded_items,
            "messages":  messages,
            "animation": animation,
            "pet":       refreshed,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"inventory_open_chest error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to open chest from inventory.")


# ── Equip item ────────────────────────────────────────────────────────────────

@router.post("/pets/equip")
async def equip_item(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    try:
        item_name = (data.get("name") or "").strip()
        item_type = (data.get("type") or "").strip()
        if not item_name or not item_type:
            raise HTTPException(status_code=400, detail="item name and type required")

        # Reforged identity — default to matching plain items if not specified
        item_reforged = bool(data.get("reforged", False))
        item_reforge_level = int(data.get("reforge_level", 0))

        from Systems.Pets.Logic.pet_brain import LootCalculator

        # Map item type to the correct equip_items kwarg
        WEAPON_TYPES = {'Dagger', 'Katana', 'Sword', 'Axe', 'Hammer', 'Bow'}
        type_map = {
            "Helmet":   dict(helmet_name=item_name),
            "Armor":    dict(armor_name=item_name),
            "Boots":    dict(boots_name=item_name),
            "Ring":     dict(ring_name=item_name),
            "Shield":   dict(shield_name=item_name),
            "Material": dict(material_names=item_name),
            "Gem":      dict(gem_names=item_name),
            "Monster":  dict(monster_names=item_name),
        }
        # Weapon types all route to weapon_name
        if item_type in WEAPON_TYPES:
            kwargs = dict(weapon_name=item_name)
        elif item_type in type_map:
            kwargs = type_map[item_type]
        else:
            raise HTTPException(status_code=400, detail=f"Cannot equip item type: {item_type}")

        # Pass reforged identity so the correct stack is used
        kwargs["reforged"] = item_reforged
        kwargs["reforge_level"] = item_reforge_level

        success, msg = await LootCalculator.equip_items(
            user_id, user.get("username", "Unknown"), **kwargs
        )

        # ── GPP: invalidate stats cache + emit event ──────────────────────────
        pet_after = await user_data_manager.get_pet_data_async(user_id)
        if pet_after:
            _invalidate_stats_cache(pet_after)
        if success:
            queue = EventQueue()
            queue.push("item_equipped", {"user_id": user_id, "item_name": item_name, "item_type": item_type})
            await queue.flush()

        refreshed = _enrich_pet(await user_data_manager.get_pet_data_async(user_id))

        # ── GPP: build animation metadata (Component pattern) ─────────────
        animation = AnimationComponent.for_ui_update("equip_flash", 500)

        return JSONResponse(content={"success": success, "message": msg, "pet": refreshed, "animation": animation})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"equip_item error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Equip failed.")


# ── Use potion ────────────────────────────────────────────────────────────────

@router.post("/pets/use-potion")
async def use_potion(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    try:
        potion_name = (data.get("name") or "").strip()
        if not potion_name:
            raise HTTPException(status_code=400, detail="Potion name required")

        quantity = max(1, int(data.get("quantity") or 1))

        from Systems.Pets.Logic.pet_brain import LootCalculator

        messages = []
        success = False
        for _ in range(quantity):
            ok, msg = await LootCalculator.use_potion(int(user_id), potion_name)
            if ok:
                success = True
                messages.append(msg)
            else:
                if not success:
                    refreshed = _enrich_pet(await user_data_manager.get_pet_data_async(user_id))
                    return JSONResponse(content={"success": False, "message": msg, "pet": refreshed})
                break

        # ── GPP: invalidate stats cache + emit event ──────────────────────────
        if success:
            pet_after = await user_data_manager.get_pet_data_async(user_id)
            if pet_after:
                _invalidate_stats_cache(pet_after)
            queue = EventQueue()
            queue.push("potion_used", {"user_id": user_id, "potion_name": potion_name, "quantity": len(messages)})
            await queue.flush()

        refreshed = _enrich_pet(await user_data_manager.get_pet_data_async(user_id))
        combined = "; ".join(messages) if messages else "Used!"

        # ── GPP: build animation metadata (Component pattern) ─────────────
        animation = AnimationComponent.for_ui_update("potion_use", 600)

        return JSONResponse(content={"success": success, "message": combined, "pet": refreshed, "animation": animation})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"use_potion error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Potion use failed.")


# ── Unequip ───────────────────────────────────────────────────────────────────

@router.post("/pets/unequip")
async def unequip_item(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    try:
        slot = (data.get("slot") or "").strip()
        VALID_SLOTS = {"Helmet","Armor","Boots","Ring","Shield","Weapon",
                       "Material","Gems","Monsters","Hat"}
        if slot not in VALID_SLOTS:
            raise HTTPException(status_code=400, detail=f"Invalid slot: {slot}")

        from Systems.Pets.Logic.pet_brain import LootCalculator
        success, msg = await LootCalculator.unequip_items(user_id, slot)
        # ── GPP: invalidate stats cache + emit event ──────────────────────────
        pet_after = await user_data_manager.get_pet_data_async(user_id)
        if pet_after:
            _invalidate_stats_cache(pet_after)
        if success:
            queue = EventQueue()
            queue.push("item_unequipped", {"user_id": user_id, "slot": slot})
            await queue.flush()
        refreshed = _enrich_pet(await user_data_manager.get_pet_data_async(user_id))

        # ── GPP: build animation metadata (Component pattern) ─────────────
        animation = AnimationComponent.for_ui_update("unequip_flash", 500)

        return JSONResponse(content={"success": success, "message": msg, "pet": refreshed, "animation": animation})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"unequip_item error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Unequip failed.")


# ── Consume item ──────────────────────────────────────────────────────────────

RARITY_LEVELS = {"Common": 1, "Uncommon": 2, "Rare": 3, "Epic": 4, "Mythic": 5}

@router.post("/pets/consume")
async def consume_item(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    try:
        item_name = (data.get("name") or "").strip()
        if not item_name:
            raise HTTPException(status_code=400, detail="Item name required.")

        # Full identity for matching — default to name+type only if not specified
        item_type = (data.get("type") or "").strip() or None
        item_reforged = bool(data.get("reforged", False))
        item_reforge_level = int(data.get("reforge_level", 0)) if item_reforged else 0

        pet = await user_data_manager.get_pet_data_async(user_id)
        if not pet:
            raise HTTPException(status_code=404, detail="No pet found.")

        inventory = pet.get("inventory", [])
        pet_level = int(pet.get("level", 1))

        # Find the item using full identity key so reforged/plain stacks are never confused
        idx = None
        for i, it in enumerate(inventory):
            if isinstance(it, dict) and it.get("name", "").lower() == item_name.lower():
                if item_type and it.get("type", "") != item_type:
                    continue
                if bool(it.get("reforged", False)) != item_reforged:
                    continue
                if item_reforged and int(it.get("reforge_level", 0)) != item_reforge_level:
                    continue
                idx = i
                break
        if idx is None:
            raise HTTPException(status_code=404, detail=f"{item_name} not found in inventory.")

        item = inventory[idx]
        available = int(item.get("count", 1))
        rarity = item.get("rarity", "Common")
        rarity_level = RARITY_LEVELS.get(rarity, 1)

        # Base XP scaled by rarity and pet level
        xp_per = 10 * rarity_level * pet_level

        # Apply equipment/level multiplier so higher-geared pets get more value
        from Systems.Pets.Logic.pet_brain import StatsCalculator
        equip_mult = StatsCalculator.get_equipment_xp_multiplier(pet)
        xp_per = int(xp_per * equip_mult)

        # Respect requested quantity, capped at what's available
        requested = int(data.get("quantity") or available)
        count = max(1, min(requested, available))
        total_xp = xp_per * count

        # Deduct consumed quantity or remove stack entirely
        if count >= available:
            inventory.pop(idx)
        else:
            inventory[idx]["count"] = available - count
        pet["inventory"] = inventory
        await user_data_manager.save_pet_data(user_id, pet.get("name", "Pet"), pet)

        # Award XP through the proper channel so leveling is handled correctly
        from Systems.Pets.Logic.pet_brain import StatsCalculator as _SC
        from Systems.Pets.pets_system import add_experience
        _, lvl_data = await add_experience(int(user_id), total_xp, "consume")

        # ── GPP: invalidate stats cache + emit event ──────────────────────────
        pet_after = await user_data_manager.get_pet_data_async(user_id)
        if pet_after:
            _invalidate_stats_cache(pet_after)
        queue = EventQueue()
        queue.push("item_consumed", {"user_id": user_id, "item_name": item_name, "count": count, "xp": total_xp})
        await queue.flush()

        refreshed = _enrich_pet(await user_data_manager.get_pet_data_async(user_id))
        leveled_up = lvl_data and lvl_data.get("new_level", 0) > lvl_data.get("old_level", 0)
        mult_str = f" (×{equip_mult:.0f})" if equip_mult > 1.0 else ""
        msg = f"Consumed {count}x {item_name} ({rarity}) for +{total_xp:,} XP{mult_str}"
        if leveled_up:
            msg += f" · Level Up! Now Lv.{lvl_data['new_level']} 🎉"

        # ── GPP: build animation metadata (Component pattern) ─────────────
        animation = AnimationComponent.for_xp_change(0, int(pet_after.get("experience", 0)) if pet_after else 0,
                                                    LootCalculator.get_next_level_xp(int(pet_after.get("level", 1))) if pet_after else 100)

        return JSONResponse(content={"success": True, "message": msg, "xp_gained": total_xp,
                                     "equip_multiplier": equip_mult,
                                     "level_up": lvl_data if leveled_up else None, "pet": refreshed, "animation": animation})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"consume_item error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Consume failed.")


# ── Gift item to another pet ──────────────────────────────────────────────────

@router.post("/pets/gift")
async def gift_item(request: Request, data: Dict[str, Any] = Body(...)):
    """
    Gift one item from your inventory to another user's pet.
    Body: { item_name: str, recipient_user_id: str }
    """
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    sender_id = str(user.get("id"))

    item_name    = (data.get("item_name") or "").strip()
    recipient_id = str(data.get("recipient_user_id") or "").strip()

    if not item_name:
        return JSONResponse(content={"error": "item_name is required"}, status_code=400)
    if not recipient_id:
        return JSONResponse(content={"error": "recipient_user_id is required"}, status_code=400)
    if recipient_id == sender_id:
        return JSONResponse(content={"error": "You cannot gift to yourself"}, status_code=400)

    try:
        # Load sender pet
        sender_pet = await user_data_manager.get_pet_data_async(sender_id)
        if not sender_pet:
            return JSONResponse(content={"error": "You don't have a pet"}, status_code=400)

        # Load recipient pet
        recipient_pet = await user_data_manager.get_pet_data_async(recipient_id)
        if not recipient_pet:
            return JSONResponse(content={"error": "Recipient doesn't have a pet"}, status_code=400)

        # Find item in sender's inventory
        inventory = sender_pet.get("inventory", [])
        item_idx  = next((i for i, it in enumerate(inventory)
                          if it["name"].lower() == item_name.lower()), None)
        if item_idx is None:
            return JSONResponse(content={"error": f"'{item_name}' not found in your inventory"}, status_code=400)

        item = inventory[item_idx]
        count = int(item.get("count", 1))

        # Remove 1 from sender
        if count <= 1:
            inventory.pop(item_idx)
        else:
            inventory[item_idx] = {**item, "count": count - 1}
        sender_pet["inventory"] = inventory
        await user_data_manager.save_pet_data(sender_id, user.get("username", "Unknown"), sender_pet)
        # ── GPP: invalidate sender's stats cache ──────────────────────────────
        _invalidate_stats_cache(sender_pet)

        # Add 1 to recipient
        gift_item_obj = {**item, "count": 1}
        from Systems.Pets.Logic.pet_brain import LootCalculator
        await LootCalculator.add_item_to_inventory(int(recipient_id), gift_item_obj, recipient_pet)

        logger.info(f"Gift: {sender_id} → {recipient_id}: {item_name}")

        # ── GPP: emit gift event (Observer pattern handles task tracking) ─────
        queue = EventQueue()
        queue.push("item_gifted", {"sender_id": sender_id, "recipient_id": recipient_id, "item_name": item_name})
        await queue.flush()

        # ── GPP: build animation metadata (Component pattern) ─────────────
        animation = AnimationComponent.for_ui_update("gift_send", 600)

        return JSONResponse(content={
            "success": True,
            "gifted":  item_name,
            "to":      recipient_pet.get("name", "Unknown"),
            "animation": animation,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"gift_item error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Gift failed.")


# ── NPC Battle (turn-based) ───────────────────────────────────────────────────

@router.post("/pets/battle/npc/start")
async def battle_npc_start(request: Request, data: Dict[str, Any] = Body(...)):
    """Initialize a turn-based NPC battle. Returns initial battle state (no turns processed)."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    try:
        import random as _random
        from Systems.Pets.Logic.pet_brain import StatsCalculator, DamageCalculator, NPCBrain

        pet = await user_data_manager.get_pet_data_async(user_id)
        if not pet:
            raise HTTPException(status_code=404, detail="No pet found")

        difficulty = (data.get("difficulty") or "easy").lower()
        if difficulty not in ("easy", "average", "hard", "quest"):
            raise HTTPException(status_code=400, detail="Invalid difficulty")

        # Quest battles pass a pre-built hostile_pet — use it directly
        hostile_pet_override = data.get("hostile_pet") if difficulty == "quest" else None

        stats = StatsCalculator.calculate_pet_stats(pet)
        p_atk  = int(stats.get("attack",  10))
        p_def  = int(stats.get("defense",  5))
        p_hp   = int(stats.get("max_health", 500))
        p_type = str(pet.get("category", "land")).lower()
        p_elem = str(pet.get("element",  "basic")).lower()
        p_elem2= str(pet.get("element2", "") or "").lower() or None
        p_spec = str(pet.get("species",  "")).strip()

        if hostile_pet_override:
            # Use the quest-generated hostile pet stats directly
            hp_raw = hostile_pet_override
            e_atk  = max(1, int(hp_raw.get("ATT", p_atk * 0.8)))
            e_def  = max(1, int(hp_raw.get("DEF", p_def * 0.8)))
            e_hp   = max(50, int((hp_raw.get("HAP", 50) + hp_raw.get("ENE", 50)) * (hp_raw.get("equipment_multiplier", 1) * 4)))
            e_type = str(hp_raw.get("category", "land")).lower()
            e_elem = str(hp_raw.get("element", "basic")).lower()
            e_species = str(hp_raw.get("species", "Creature"))
            enemy_name = str(hp_raw.get("name", "Wild Creature"))
            # Use "average" scaling for action label purposes
            difficulty = "average"
        else:
            scale = {"easy": (0.70, 0.70, 0.85), "average": (1.10, 1.10, 1.10), "hard": (1.50, 1.50, 1.35)}
            s_atk, s_def, s_hp = scale[difficulty]
            e_atk  = max(1, int(p_atk * s_atk * _random.uniform(0.9, 1.1)))
            e_def  = max(1, int(p_def * s_def * _random.uniform(0.9, 1.1)))
            e_hp   = max(50, int(p_hp  * s_hp  * _random.uniform(0.95, 1.15)))
            e_atk  = min(e_atk, max(10, p_hp // 12))

            all_types    = list(DamageCalculator.CATEGORY_ADVANTAGES.keys())
            all_elements = list(DamageCalculator.ELEMENT_EFFECTIVENESS.keys())
            if difficulty == "easy":
                cand_types = [t for t in all_types if DamageCalculator.compute_type_bonus(p_type, t) > 1.0] or all_types
                cand_elems = [e for e in all_elements if DamageCalculator.compute_element_bonus(p_elem, e) > 1.0] or all_elements
            elif difficulty == "hard":
                cand_types = [t for t in all_types if DamageCalculator.compute_type_bonus(t, p_type) > 1.0] or all_types
                cand_elems = [e for e in all_elements if DamageCalculator.compute_element_bonus(e, p_elem) > 1.0] or all_elements
            else:
                cand_types = all_types
                cand_elems = all_elements

            e_type = _random.choice(cand_types)
            e_elem = _random.choice(cand_elems)

            e_species = ""
            try:
                _info = await _load_json_cached(os.path.join(project_root, "Systems", "Pets", "Logic", "info.json"))
                _all_species = list(_info.get("Pets", {}).keys())
                if _all_species:
                    e_species = _random.choice(_all_species)
            except Exception as _e:
                logger.warning(f"battle_npc_start: could not pick enemy species: {_e}")
                e_species = ""

            try:
                from Systems.Functions.optimal_file_manager import OptimalFileManager
                _base = OptimalFileManager().get_data("base")
                adj  = _random.choice(_base.get("element_bases", {}).get(e_elem, ["Mysterious"]))
                noun = _random.choice(_base.get("category_bases", {}).get(e_type, ["Creature"]))
                enemy_name = f"{adj} {noun}"
            except Exception:
                enemy_name = f"{e_elem.title()} {e_type.title()} Foe"

        action_labels = DamageCalculator.get_action_labels(p_type, p_elem, p_spec, custom_labels=pet.get("action_labels", {}))

        # Build flat ordered equipment list for display: Monster, Gem, Material, Hat, Material, Gem, Monster
        def _equip_items(pet: dict) -> list:
            eq = pet.get("equipment") or {}
            slots = []
            mons  = eq.get("Monsters", [])
            gems  = eq.get("Gems", [])
            mats  = eq.get("Material", [])
            hat   = eq.get("Hat")
            if isinstance(mons, dict): mons = [mons]
            if isinstance(gems, dict): gems = [gems]
            if isinstance(mats, dict): mats = [mats]
            def _item(i): return {"name": i.get("name",""), "emoji_file": i.get("emoji_file", i.get("name","") + ".png"), "rarity": i.get("rarity","Common"), "type": i.get("type","")}
            # Left side: first monster, first gem, first material
            if len(mons) > 0: slots.append(_item(mons[0]))
            if len(gems) > 0: slots.append(_item(gems[0]))
            if len(mats) > 0: slots.append(_item(mats[0]))
            # Center: hat
            if hat and isinstance(hat, dict): slots.append(_item(hat))
            # Right side: second material, second gem, second monster
            if len(mats) > 1: slots.append(_item(mats[1]))
            if len(gems) > 1: slots.append(_item(gems[1]))
            if len(mons) > 1: slots.append(_item(mons[1]))
            return slots

        # ── Initialise server-side skill state for this battle ────────────────
        from Systems.Pets.Logic.battle_skills import (
            init_battle_skill_state, get_equipped_skills, get_max_skill_slots, SKILL_BY_ID
        )
        from Systems.Pets.Logic.ability_tree import (
            get_ability_effect, get_starting_charge_bonus
        )

        # Apply battle_health_bonus (HAP/ENE branches)
        health_bonus = get_ability_effect(pet, "battle_health_bonus")
        if health_bonus > 0:
            p_hp = int(p_hp * (1.0 + health_bonus))

        # Apply charge_limit_bonus (ENE branch)
        charge_limit_val = int(get_ability_effect(pet, "charge_limit_bonus"))
        p_charge_limit = int(DamageCalculator.get_max_charge(pet))  # base 5 + bonus

        # Apply starting_charge_bonus (ENE branch — Charged + Overcharged)
        p_starting_charge = 1.0 + int(get_starting_charge_bonus(pet))
        p_starting_charge = min(p_starting_charge, float(p_charge_limit))

        skill_state: Dict[str, Any] = {
            "pet": pet,
            "total_attack": p_atk,
            "max_hp": p_hp,          # already includes battle_health_bonus
            "active_effects": [],
            "skill_cooldowns": {},
            "equipped_skills": [],
        }
        init_battle_skill_state(skill_state)
        # Enemy skill state (for DoT/stun/debuff applied by player skills)
        enemy_skill_state: Dict[str, Any] = {
            "element": e_elem,
            "active_effects": [],
            "max_hp": e_hp,
        }
        # Store in the module-level session dict keyed by user_id
        _arena_battle_sessions[user_id] = {
            "skill_state": skill_state,
            "enemy_skill_state": enemy_skill_state,
            "e_atk_base": e_atk,
            "e_def_base": e_def,
            "p_charge_limit": p_charge_limit,
        }

        # Build equipped skills display list — one entry per unlocked slot.
        # Slots with a skill get full data; unlocked-but-empty slots get null.
        max_slots = get_max_skill_slots(pet)
        equipped_ids = skill_state.get("equipped_skills", [])
        equipped_skills_display = []
        for slot_idx in range(max_slots):
            sid = equipped_ids[slot_idx] if slot_idx < len(equipped_ids) else None
            sk = SKILL_BY_ID.get(sid) if sid else None
            if sk:
                equipped_skills_display.append({
                    "id": sid,
                    "name": sk["name"],
                    "description": sk["description"],
                    "element": sk.get("element", ""),
                    "unlocked": True,
                })
            else:
                # Slot is unlocked but no skill equipped
                equipped_skills_display.append(None)

        # ── GPP: invalidate stats cache + emit event ──────────────────────────
        _invalidate_stats_cache(pet)
        queue = EventQueue()
        queue.push("battle_npc_started", {"user_id": user_id, "difficulty": difficulty, "enemy_name": enemy_name})
        await queue.flush()

        # ── GPP: build animation metadata (Component pattern) ─────────────
        animation = AnimationComponent.for_ui_update("battle_start", 800)

        # Determine if the player has a pet badge to display
        player_badge_url = _selected_badge_url(user_id)

        return JSONResponse(content={
            "success": True,
            "difficulty": difficulty,
            "player": {
                "name": pet["name"],
                "max_hp": p_hp,
                "cur_hp": p_hp,
                "attack": p_atk,
                "defense": p_def,
                "type": p_type,
                "element": p_elem,
                "element2": p_elem2 or "",
                "species": p_spec,
                "badge_url": player_badge_url or None,
                "charge": p_starting_charge,
                "charge_limit": p_charge_limit,
                "last_action": None,
                "equipment": _equip_items(pet),
                "equipped_skills": equipped_skills_display,
                "skill_cooldowns": {str(k): v for k, v in skill_state.get("skill_cooldowns", {}).items()},
            },
            "enemy": {
                "name": enemy_name,
                "max_hp": e_hp,
                "cur_hp": e_hp,
                "attack": e_atk,
                "defense": e_def,
                "type": e_type,
                "element": e_elem,
                "species": e_species,
                "charge": 1.0,
                "last_action": None,
            },
            "turn": 0,
            "over": False,
            "won": None,
            "action_labels": action_labels,
            "animation": animation,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"battle_npc_start error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to start battle.")


@router.post("/pets/battle/npc/turn")
async def battle_npc_turn(request: Request, data: Dict[str, Any] = Body(...)):
    """Process one turn of a turn-based NPC battle. Client sends full state + player action."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    try:
        from Systems.Pets.Logic.pet_brain import DamageCalculator, LootCalculator, NPCBrain
        from Systems.Pets.Logic.battle_skills import (
            apply_skill, tick_battle_effects, tick_monster_effects,
            is_stunned, consume_stun,
            get_atk_multiplier, get_def_multiplier, get_damage_reduction,
            absorb_damage_through_shield, get_reflect_value, can_use_skill,
            SKILL_BY_ID,
        )

        p_action = (data.get("action") or "attack").lower()
        slot_index = int(data.get("slot_index", 0))
        if p_action not in ("attack", "defend", "charge", "skill"):
            p_action = "attack"

        # Unpack state sent from client
        ps = data["player"]
        es = data["enemy"]
        turn_num = int(data.get("turn", 0)) + 1
        difficulty = (data.get("difficulty") or "easy").lower()

        p_atk    = int(ps["attack"])
        p_def    = int(ps["defense"])
        p_type   = str(ps.get("type", "land"))
        p_elem   = str(ps.get("element", "basic"))
        p_elem2  = str(ps.get("element2") or "") or None
        p_spec   = str(ps.get("species", ""))
        p_hp     = int(ps["max_hp"])
        cur_p_hp = int(ps["cur_hp"])
        p_charge = float(ps.get("charge", 1.0))

        e_atk    = int(es["attack"])
        e_def    = int(es["defense"])
        e_type   = str(es.get("type", "land"))
        e_elem   = str(es.get("element", "basic"))
        e_hp     = int(es["max_hp"])
        cur_e_hp = int(es["cur_hp"])
        e_charge = float(es.get("charge", 1.0))
        e_last   = es.get("last_action")
        enemy_name = str(es.get("name", "Enemy"))
        pet_name   = str(ps.get("name", "Your Pet"))

        # ── Retrieve server-side skill session ────────────────────────────────
        session = _arena_battle_sessions.get(user_id, {})
        skill_state       = session.get("skill_state", {})
        enemy_skill_state = session.get("enemy_skill_state", {"element": e_elem, "active_effects": [], "max_hp": e_hp})

        # Sync current HP into skill state so heal/lifesteal caps correctly
        skill_state["max_hp"] = p_hp
        skill_state["total_attack"] = p_atk
        enemy_skill_state["max_hp"] = e_hp
        enemy_skill_state["element"] = e_elem

        extra_lines: list = []  # skill/effect log lines to append to `lines`

        # ── Tick active effects (DoT/HoT, cooldowns) ─────────────────────────
        if skill_state:
            p_net_delta, p_tick_lines = tick_battle_effects(skill_state, p_atk)
            if p_net_delta != 0:
                cur_p_hp = max(0, min(p_hp, cur_p_hp + p_net_delta))
            extra_lines.extend(p_tick_lines)

        e_net_delta, e_tick_lines = tick_monster_effects(enemy_skill_state)
        if e_net_delta != 0:
            cur_e_hp = max(0, cur_e_hp + e_net_delta)
        extra_lines.extend(e_tick_lines)

        # ── Stun check on player ──────────────────────────────────────────────
        if skill_state and is_stunned(skill_state):
            consume_stun(skill_state)
            p_action = "defend"
            extra_lines.append(f"💫 {pet_name} is stunned and cannot act!")

        # ── Apply stat multipliers from active effects ────────────────────────
        p_atk_mult = get_atk_multiplier(skill_state) if skill_state else 1.0
        p_def_mult = get_def_multiplier(skill_state) if skill_state else 1.0
        e_atk_mult = get_atk_multiplier(enemy_skill_state)
        e_def_mult = get_def_multiplier(enemy_skill_state)
        effective_p_atk = int(p_atk * p_atk_mult)
        effective_e_atk = int(e_atk * e_atk_mult)
        effective_e_def = int(e_def * e_def_mult)

        # ── Skill action ──────────────────────────────────────────────────────
        skill_hp_delta_p = 0   # net HP change on player from skill
        skill_hp_delta_e = 0   # net HP change on enemy from skill
        skill_used = False

        if p_action == "skill" and skill_state:
            equipped = skill_state.get("equipped_skills", [])
            if slot_index < len(equipped) and can_use_skill(skill_state, slot_index):
                skill_id = equipped[slot_index]
                # Inject charge so charge_boost can read it
                skill_state["charge"] = p_charge
                skill_state["charge_limit"] = float(session.get("p_charge_limit", 5.0))
                skill_state["max_charge_limit"] = float(session.get("p_charge_limit", 5.0))
                result = apply_skill(skill_id, skill_state, enemy_skill_state,
                                     battle_type="npc", slot_index=slot_index)
                if result["ok"]:
                    skill_hp_delta_p = result.get("hp_delta_user", 0)
                    skill_hp_delta_e = result.get("hp_delta_target", 0)
                    # Apply damage to enemy
                    if skill_hp_delta_e < 0:
                        cur_e_hp = max(0, cur_e_hp + skill_hp_delta_e)
                    # Apply heal/lifesteal to player
                    if skill_hp_delta_p > 0:
                        cur_p_hp = min(p_hp, cur_p_hp + skill_hp_delta_p)
                    elif skill_hp_delta_p < 0:
                        cur_p_hp = max(0, cur_p_hp + skill_hp_delta_p)
                    # Sync charge_boost
                    if "_charge_boost_result" in skill_state:
                        p_charge = float(skill_state.pop("_charge_boost_result"))
                    extra_lines.append(f"✨ {result.get('message', result.get('skill_name', 'Skill used'))}")
                    skill_used = True
                else:
                    extra_lines.append(f"❌ {result.get('message', 'Skill failed')}")
            if not skill_used:
                p_action = "attack"
                extra_lines.append(f"⏳ Skill on cooldown — attacking instead!")

        # ── NPC decides ───────────────────────────────────────────────────────
        npc_brain = NPCBrain()
        # Check if enemy is stunned
        e_stunned = is_stunned(enemy_skill_state)
        if e_stunned:
            consume_stun(enemy_skill_state)
            e_action = "defend"
            extra_lines.append(f"💫 {enemy_name} is stunned and cannot act!")
        else:
            monster_state = {
                "hp": cur_e_hp, "max_hp": e_hp, "prev_hp": cur_e_hp,
                "charge_multiplier": e_charge, "last_action": e_last,
                "attack_stat": float(e_atk), "defense_stat": float(e_def),
                "seed": turn_num
            }
            player_state_for_brain = [{"alive": cur_p_hp > 0, "hp": cur_p_hp, "max_hp": p_hp, "charging": p_action == "charge"}]
            e_action = npc_brain.decide_action(monster_state, player_state_for_brain).get("action", "attack")

        # ── Charge accumulation ───────────────────────────────────────────────
        p_pet_data_for_charge = session.get("skill_state", {}).get("pet") if session else None
        if p_action == "charge":
            p_charge = DamageCalculator.get_next_charge_multiplier(p_charge, p_pet_data_for_charge)
        if e_action == "charge":
            e_charge = DamageCalculator.get_next_charge_multiplier(e_charge)

        # ── Resolve combat (only for non-skill actions) ───────────────────────
        p_dmg_dealt = 0
        e_dmg_dealt = 0
        p_parry = 0
        e_parry = 0

        if p_action != "skill":
            # Retrieve the raw pet from the skill session so DamageCalculator can apply
            # ability effects (battle_damage_mult, critical_hit_chance, advantage_mastery, etc.)
            p_pet_data = session.get("skill_state", {}).get("pet") if session else None
            p_result = DamageCalculator.calculate_battle_action(
                attacker_attack=effective_p_atk, target_defense=effective_e_def,
                charge_multiplier=p_charge if p_action in ("attack", "defend") else 1.0,
                target_charge_multiplier=e_charge if e_action == "defend" else 1.0,
                attacker_action_type=p_action, target_action_type=e_action,
                attacker_type=p_type, attacker_element=p_elem, attacker_element2=p_elem2,
                defender_type=e_type, defender_element=e_elem,
                attacker_species=p_spec,
                attacker_pet_data=p_pet_data,
                battle_type="npc",
            )
            p_dmg_dealt = p_result["final_damage"]
            p_parry     = p_result["parry_damage"]
        else:
            p_result = {"attack_roll": None, "attack_result": "", "parry_damage": 0,
                        "type_element_bonus_mult_attack": 1.0, "final_attack": 0, "final_defense": 0}

        if e_action != "defend" or p_action != "defend":
            p_pet_data = session.get("skill_state", {}).get("pet") if session else None
            e_result = DamageCalculator.calculate_battle_action(
                attacker_attack=effective_e_atk, target_defense=int(p_def * p_def_mult),
                charge_multiplier=e_charge if e_action in ("attack", "defend") else 1.0,
                target_charge_multiplier=p_charge if p_action == "defend" else 1.0,
                attacker_action_type=e_action, target_action_type=p_action,
                attacker_type=e_type, attacker_element=e_elem,
                defender_type=p_type, defender_element=p_elem, defender_element2=p_elem2,
                defender_species=p_spec,
                defender_pet_data=p_pet_data,
                defender_current_hp=cur_p_hp,
                defender_max_hp=p_hp,
                battle_type="npc",
            )
            e_dmg_dealt = e_result["final_damage"]
            e_parry     = e_result["parry_damage"]
        else:
            e_result = {"attack_roll": None, "attack_result": "", "parry_damage": 0,
                        "type_element_bonus_mult_attack": 1.0, "final_attack": 0, "final_defense": 0}

        # Both defend: stalemate
        if p_action == "defend" and e_action == "defend":
            p_dmg_dealt = 0; e_dmg_dealt = 0; p_parry = 0; e_parry = 0

        # ── Apply skill-based damage reduction / shield / reflect on player ───
        if e_dmg_dealt > 0 and skill_state:
            dr = get_damage_reduction(skill_state)
            e_dmg_dealt = max(1, int(e_dmg_dealt * (1.0 - dr))) if dr > 0 else e_dmg_dealt
            e_dmg_dealt, _absorbed, shield_log = absorb_damage_through_shield(skill_state, e_dmg_dealt)
            extra_lines.extend(shield_log)
            reflect_frac = get_reflect_value(skill_state)
            if reflect_frac > 0 and e_dmg_dealt > 0:
                reflect_dmg = max(1, int(e_dmg_dealt * reflect_frac))
                cur_e_hp = max(0, cur_e_hp - reflect_dmg)
                extra_lines.append(f"🔄 {pet_name} reflects {reflect_dmg} damage!")

        # ── Apply HP changes ──────────────────────────────────────────────────
        cur_e_hp = max(0, cur_e_hp - p_dmg_dealt - e_parry)
        cur_p_hp = max(0, cur_p_hp - e_dmg_dealt - p_parry)

        # Reset charge after use
        if p_action in ("attack", "defend"): p_charge = 1.0
        if e_action in ("attack", "defend"): e_charge = 1.0

        action_labels = data.get("action_labels", {})
        p_action_label = action_labels.get(p_action, p_action.title())
        p_charge_used = float(data.get("player", {}).get("charge", 1.0))
        e_charge_used = float(data.get("enemy", {}).get("charge", 1.0))

        # ── Build combat dict ─────────────────────────────────────────────────
        p_is_critical = p_result.get("is_critical", False) if p_action in ("attack", "defend") else False
        e_is_critical = e_result.get("is_critical", False) if e_action in ("attack", "defend") else False
        combat = {
            "p_action": p_action,
            "p_action_label": p_action_label,
            "p_dmg": p_dmg_dealt,
            "p_parry": p_parry,
            "p_is_critical": p_is_critical,
            "p_critical_mult": p_result.get("critical_multiplier", 1.0) if p_is_critical else 1.0,
            "p_charge_mult": p_charge_used if p_action == "attack" else (p_charge if p_action == "charge" else (p_charge_used if p_action == "defend" else 1.0)),
            "p_attack_roll": p_result.get("attack_roll"),
            "p_attack_result": p_result.get("attack_result", ""),
            "p_defense_roll": e_result.get("defense_roll") if p_action == "defend" else None,
            "p_defense_result": e_result.get("defense_result", "") if p_action == "defend" else "",
            "p_final_attack": p_result.get("final_attack", 0),
            "p_final_defense": e_result.get("final_defense", 0),
            "p_type_elem_mult": round(p_result.get("type_element_bonus_mult_attack", 1.0), 2),
            "e_action": e_action,
            "e_dmg": e_dmg_dealt,
            "e_parry": e_parry,
            "e_is_critical": e_is_critical,
            "e_critical_mult": e_result.get("critical_multiplier", 1.0) if e_is_critical else 1.0,
            "e_charge_mult": e_charge_used if e_action == "attack" else (e_charge if e_action == "charge" else (e_charge_used if e_action == "defend" else 1.0)),
            "e_attack_roll": e_result.get("attack_roll"),
            "e_attack_result": e_result.get("attack_result", ""),
            "e_defense_roll": p_result.get("defense_roll") if e_action == "defend" else None,
            "e_defense_result": p_result.get("defense_result", "") if e_action == "defend" else "",
            "e_final_attack": e_result.get("final_attack", 0),
            "e_final_defense": p_result.get("final_defense", 0),
            "e_type_elem_mult": round(e_result.get("type_element_bonus_mult_attack", 1.0), 2),
            "p_charge_after": p_charge,
            "e_charge_after": e_charge,
            "both_defend": p_action == "defend" and e_action == "defend",
        }

        # ── Build log lines ───────────────────────────────────────────────────
        lines = list(extra_lines)
        if p_action == "charge":
            lines.append(f"⚡ {pet_name} charges up! (x{p_charge:.0f})")
        elif p_action == "skill":
            pass  # already in extra_lines
        elif p_dmg_dealt > 0:
            mult = p_result.get("type_element_bonus_mult_attack", 1.0)
            bonus = " 🔥 Super effective!" if mult > 1.0 else (" 💨 Not very effective..." if mult < 1.0 else "")
            charge_tag = f" [x{p_charge_used:.0f} charge]" if p_charge_used > 1.0 else ""
            lines.append(f"⚔️ {pet_name} uses {p_action_label}{charge_tag} → {p_dmg_dealt} dmg{bonus}")
        elif p_action == "defend":
            if e_parry > 0:
                lines.append(f"🛡️ {pet_name} defends and parries {e_parry} dmg back!")
            else:
                lines.append(f"🛡️ {pet_name} defends.")
        elif p_dmg_dealt == 0 and p_action == "attack":
            lines.append(f"⚔️ {pet_name} uses {p_action_label} → blocked!")

        if e_action == "charge":
            lines.append(f"⚡ {enemy_name} charges up! (x{e_charge:.0f})")
        elif e_dmg_dealt > 0:
            charge_tag = f" [x{e_charge_used:.0f} charge]" if e_charge_used > 1.0 else ""
            lines.append(f"💥 {enemy_name} attacks{charge_tag} → {e_dmg_dealt} dmg")
        elif e_action == "defend":
            if p_parry > 0:
                lines.append(f"🛡️ {enemy_name} defends and parries {p_parry} dmg back!")
            else:
                lines.append(f"🛡️ {enemy_name} defends.")
        elif e_dmg_dealt == 0 and e_action == "attack":
            lines.append(f"💥 {enemy_name} attacks → blocked!")

        over = cur_p_hp <= 0 or cur_e_hp <= 0
        player_won = cur_p_hp > 0 and cur_e_hp <= 0

        # ── Live spectator log ─────────────────────────────────────────────────
        room_id = data.get("room_id")
        if room_id is not None:
            try:
                from web.api.arena_api import _rooms, ArenaRoom
                rid = int(room_id)
                if rid in _rooms:
                    room = _rooms[rid]
                    # Keep last 10 log lines for spectators
                    log_entry = f"[T{turn_num}] {lines[-1] if lines else '...'}"
                    room.battle_log = (room.battle_log or [])[-9:] + [log_entry]
                    room.updated_at = time.time()
            except Exception:
                pass

        # Clean up session on battle end
        if over:
            _arena_battle_sessions.pop(user_id, None)

        # If battle is over, apply XP/loot
        loot_result = None
        level_change = None
        refreshed_pet = None
        if over:
            pet = await user_data_manager.get_pet_data_async(user_id)
            if pet:
                old_level = int(pet.get("level", 1))
                loot_result = await LootCalculator.calculate_loot(
                    user_id=int(user_id), pet_data=pet, source="npc_battle",
                    difficulty=difficulty, winner_level=old_level, is_winner=player_won
                )
                await user_data_manager.update_pet_battle_stats(
                    user_id, "npc",
                    wins=1 if player_won else 0, losses=0 if player_won else 1,
                    xp_earned=loot_result["xp_gained"], damage_dealt=0, damage_taken=0
                )
                # ── GPP: invalidate stats cache + emit battle event ───────────
                _invalidate_stats_cache(pet)
                queue = EventQueue()
                queue.push("npc_battle_ended", {
                    "user_id":    user_id,
                    "won":        player_won,
                    "difficulty": difficulty,
                    "xp_gained":  loot_result["xp_gained"],
                })
                await queue.flush()

                refreshed_pet = _enrich_pet(await user_data_manager.get_pet_data_async(user_id))
                new_level = int(refreshed_pet.get("level", 1)) if refreshed_pet else old_level
                level_change = loot_result.get("level_change")
                if level_change is None and new_level != old_level:
                    level_change = {"old_level": old_level, "new_level": new_level, "gains": {}}

        # Build per-slot cooldown map for the frontend
        skill_cooldowns = {str(k): v for k, v in skill_state.get("skill_cooldowns", {}).items()} if skill_state else {}

        # ── GPP: build per-action animation metadata (Component pattern) ──────
        p_anim = AnimationComponent.for_battle_action(
            p_action, p_dmg_dealt, True,
            p_result.get("type_element_bonus_mult_attack", 1.0),
        )
        e_anim = AnimationComponent.for_battle_action(
            e_action, e_dmg_dealt, False,
            e_result.get("type_element_bonus_mult_attack", 1.0),
        )

        # ── GPP: invalidate stats cache + emit event ──────────────────────────
        pet = await user_data_manager.get_pet_data_async(user_id)
        if pet:
            _invalidate_stats_cache(pet)
        queue = EventQueue()
        queue.push("battle_npc_turn", {"user_id": user_id, "turn": turn_num, "player_action": p_action, "enemy_action": e_action, "won": player_won if over else None})
        await queue.flush()

        return JSONResponse(content={
            "success": True,
            "turn": turn_num,
            "lines": lines,
            "combat": combat,
            "player_action": p_action,
            "enemy_action": e_action,
            "player": {
                **ps,
                "cur_hp": cur_p_hp,
                "charge": p_charge,
                "last_action": p_action,
                "skill_cooldowns": skill_cooldowns,
            },
            "enemy": {
                **es,
                "cur_hp": cur_e_hp,
                "charge": e_charge,
                "last_action": e_action,
            },
            "over": over,
            "won": player_won if over else None,
            "xp_gained": loot_result["xp_gained"] if loot_result else 0,
            "messages": loot_result["messages"] if loot_result else [],
            "level_change": level_change,
            "pet": refreshed_pet,
            "skill_cooldowns": skill_cooldowns,
            "animations": [p_anim, e_anim],
            "animation": p_anim,
        })

    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"battle_npc_turn bad input: {e}")
        raise HTTPException(status_code=400, detail="Invalid battle state.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"battle_npc_turn error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Battle turn failed.")


# ── Tournament turn helper ────────────────────────────────────────────────────
async def _run_tournament_turn(user_id: str, session_key: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process one battle turn for a tournament match.
    Works exactly like battle_npc_turn but uses a custom session_key
    so multiple simultaneous tournament matches don't collide.
    """
    from Systems.Pets.Logic.pet_brain import DamageCalculator, LootCalculator, NPCBrain
    from Systems.Pets.Logic.battle_skills import (
        apply_skill, tick_battle_effects, tick_monster_effects,
        is_stunned, consume_stun,
        get_atk_multiplier, get_def_multiplier, get_damage_reduction,
        absorb_damage_through_shield, get_reflect_value, can_use_skill,
        SKILL_BY_ID,
    )

    p_action   = (data.get("action") or "attack").lower()
    slot_index = int(data.get("slot_index", 0))
    if p_action not in ("attack","defend","charge","skill"):
        p_action = "attack"

    ps         = data["player"]
    es         = data["enemy"]
    turn_num   = int(data.get("turn", 0)) + 1
    difficulty = "average"

    p_atk    = int(ps["attack"]);  p_def  = int(ps["defense"])
    p_type   = str(ps.get("type","land")); p_elem = str(ps.get("element","basic"))
    p_elem2  = str(ps.get("element2") or "") or None
    p_spec   = str(ps.get("species",""))
    p_hp     = int(ps["max_hp"]);  cur_p_hp = int(ps["cur_hp"])
    p_charge = float(ps.get("charge",1.0))

    e_atk    = int(es["attack"]);  e_def  = int(es["defense"])
    e_type   = str(es.get("type","land")); e_elem = str(es.get("element","basic"))
    e_hp     = int(es["max_hp"]);  cur_e_hp = int(es["cur_hp"])
    e_charge = float(es.get("charge",1.0)); e_last = es.get("last_action")
    enemy_name = str(es.get("name","Enemy")); pet_name = str(ps.get("name","Your Pet"))

    session         = _arena_battle_sessions.get(session_key, {})
    skill_state     = session.get("skill_state", {})
    enemy_skill_state = session.get("enemy_skill_state",
                                    {"element": e_elem, "active_effects": [], "max_hp": e_hp})

    skill_state["max_hp"]       = p_hp
    skill_state["total_attack"] = p_atk
    enemy_skill_state["max_hp"] = e_hp
    enemy_skill_state["element"] = e_elem

    extra_lines: list = []

    # Tick active effects
    if skill_state:
        p_net, p_ticks = tick_battle_effects(skill_state, p_atk)
        if p_net != 0:
            cur_p_hp = max(0, min(p_hp, cur_p_hp + p_net))
        extra_lines.extend(p_ticks)

    e_net, e_ticks = tick_monster_effects(enemy_skill_state)
    if e_net != 0:
        cur_e_hp = max(0, cur_e_hp + e_net)
    extra_lines.extend(e_ticks)

    # Stun check
    if skill_state and is_stunned(skill_state):
        consume_stun(skill_state)
        p_action = "defend"
        extra_lines.append(f"💫 {pet_name} is stunned!")

    p_atk_mult = get_atk_multiplier(skill_state) if skill_state else 1.0
    p_def_mult = get_def_multiplier(skill_state) if skill_state else 1.0
    e_atk_mult = get_atk_multiplier(enemy_skill_state)
    e_def_mult = get_def_multiplier(enemy_skill_state)
    effective_p_atk = int(p_atk * p_atk_mult)
    effective_e_atk = int(e_atk * e_atk_mult)
    effective_e_def = int(e_def * e_def_mult)

    skill_hp_p = 0; skill_hp_e = 0; skill_used = False
    if p_action == "skill" and skill_state:
        equipped = skill_state.get("equipped_skills", [])
        if slot_index < len(equipped) and can_use_skill(skill_state, slot_index):
            sid = equipped[slot_index]
            skill_state["charge"]          = p_charge
            skill_state["charge_limit"]    = float(session.get("p_charge_limit", 5.0))
            skill_state["max_charge_limit"] = skill_state["charge_limit"]
            res = apply_skill(sid, skill_state, enemy_skill_state, battle_type="pvp", slot_index=slot_index)
            if res["ok"]:
                skill_hp_p = res.get("hp_delta_user", 0)
                skill_hp_e = res.get("hp_delta_target", 0)
                if skill_hp_e < 0: cur_e_hp = max(0, cur_e_hp + skill_hp_e)
                if skill_hp_p > 0: cur_p_hp = min(p_hp, cur_p_hp + skill_hp_p)
                elif skill_hp_p < 0: cur_p_hp = max(0, cur_p_hp + skill_hp_p)
                if "_charge_boost_result" in skill_state:
                    p_charge = float(skill_state.pop("_charge_boost_result"))
                extra_lines.append(f"✨ {res.get('message', sid)}")
                skill_used = True
            else:
                extra_lines.append(f"❌ {res.get('message','Skill failed')}")
        if not skill_used:
            p_action = "attack"
            extra_lines.append("⏳ Skill on cooldown — attacking instead!")

    # NPC / stun check on enemy
    e_stunned = is_stunned(enemy_skill_state)
    if e_stunned:
        consume_stun(enemy_skill_state)
        e_action = "defend"
        extra_lines.append(f"💫 {enemy_name} is stunned!")
    else:
        npc_brain = NPCBrain()
        ms = {
            "hp": cur_e_hp, "max_hp": e_hp, "prev_hp": cur_e_hp,
            "charge_multiplier": e_charge, "last_action": e_last,
            "attack_stat": float(e_atk), "defense_stat": float(e_def), "seed": turn_num,
        }
        e_action = npc_brain.decide_action(ms, [{"alive": cur_p_hp > 0, "hp": cur_p_hp,
                                                   "max_hp": p_hp, "charging": p_action=="charge"}]).get("action","attack")

    p_pet_data = session.get("skill_state",{}).get("pet") if session else None
    if p_action == "charge":
        p_charge = DamageCalculator.get_next_charge_multiplier(p_charge, p_pet_data)
    if e_action == "charge":
        e_charge = DamageCalculator.get_next_charge_multiplier(e_charge)

    p_dmg = e_dmg = p_parry = e_parry = 0
    if p_action != "skill":
        pr = DamageCalculator.calculate_battle_action(
            attacker_attack=effective_p_atk, target_defense=effective_e_def,
            charge_multiplier=p_charge if p_action in ("attack","defend") else 1.0,
            target_charge_multiplier=e_charge if e_action == "defend" else 1.0,
            attacker_action_type=p_action, target_action_type=e_action,
            attacker_type=p_type, attacker_element=p_elem, attacker_element2=p_elem2,
            defender_type=e_type, defender_element=e_elem,
            attacker_species=p_spec, attacker_pet_data=p_pet_data, battle_type="pvp",
        )
        p_dmg   = pr["final_damage"]; p_parry = pr["parry_damage"]
    else:
        pr = {"attack_roll":None,"attack_result":"","parry_damage":0,
              "type_element_bonus_mult_attack":1.0,"final_attack":0,"final_defense":0,
              "is_critical":False,"critical_multiplier":1.0}

    er = DamageCalculator.calculate_battle_action(
        attacker_attack=effective_e_atk, target_defense=int(p_def * p_def_mult),
        charge_multiplier=e_charge if e_action in ("attack","defend") else 1.0,
        target_charge_multiplier=p_charge if p_action == "defend" else 1.0,
        attacker_action_type=e_action, target_action_type=p_action,
        attacker_type=e_type, attacker_element=e_elem,
        defender_type=p_type, defender_element=p_elem, defender_element2=p_elem2,
        defender_species=p_spec, defender_pet_data=p_pet_data,
        defender_current_hp=cur_p_hp, defender_max_hp=p_hp, battle_type="pvp",
    )
    e_dmg = er["final_damage"]; e_parry = er["parry_damage"]

    if p_action == "defend" and e_action == "defend":
        p_dmg = e_dmg = p_parry = e_parry = 0

    if e_dmg > 0 and skill_state:
        dr = get_damage_reduction(skill_state)
        e_dmg = max(1, int(e_dmg * (1.0 - dr))) if dr > 0 else e_dmg
        e_dmg, _, sl = absorb_damage_through_shield(skill_state, e_dmg)
        extra_lines.extend(sl)
        rf = get_reflect_value(skill_state)
        if rf > 0 and e_dmg > 0:
            rdmg = max(1, int(e_dmg * rf))
            cur_e_hp = max(0, cur_e_hp - rdmg)
            extra_lines.append(f"🔄 {pet_name} reflects {rdmg}!")

    cur_e_hp = max(0, cur_e_hp - p_dmg - e_parry)
    cur_p_hp = max(0, cur_p_hp - e_dmg - p_parry)
    if p_action in ("attack","defend"): p_charge = 1.0
    if e_action in ("attack","defend"): e_charge = 1.0

    action_labels = data.get("action_labels", {})
    p_label = action_labels.get(p_action, p_action.title())

    lines: list = list(extra_lines)
    if p_action == "charge":
        lines.append(f"⚡ {pet_name} charges! (x{p_charge:.0f})")
    elif p_action == "skill":
        pass
    elif p_dmg > 0:
        mult = pr.get("type_element_bonus_mult_attack",1.0)
        bonus = " 🔥 Super!" if mult > 1.0 else (" 💨 Weak…" if mult < 1.0 else "")
        ctag  = f" [x{float(ps.get('charge',1.0)):.0f}]" if float(ps.get('charge',1.0)) > 1.0 else ""
        lines.append(f"⚔️ {pet_name} {p_label}{ctag} → {p_dmg} dmg{bonus}")
    elif p_action == "defend":
        lines.append(f"🛡️ {pet_name} defends" + (f" — parries {e_parry}!" if e_parry else "."))

    if e_action == "charge":
        lines.append(f"⚡ {enemy_name} charges! (x{e_charge:.0f})")
    elif e_dmg > 0:
        lines.append(f"💥 {enemy_name} → {e_dmg} dmg")
    elif e_action == "defend":
        lines.append(f"🛡️ {enemy_name} defends" + (f" — parries {p_parry}!" if p_parry else "."))

    over       = cur_p_hp <= 0 or cur_e_hp <= 0
    player_won = cur_p_hp > 0 and cur_e_hp <= 0

    loot_result = None
    if over:
        _arena_battle_sessions.pop(session_key, None)
        player_pet_obj = session.get("skill_state",{}).get("pet")
        if player_pet_obj:
            loot_result = await LootCalculator.calculate_loot(
                user_id=int(user_id), pet_data=player_pet_obj, source="pvp_battle",
                difficulty="average", winner_level=int(player_pet_obj.get("level",1)),
                is_winner=player_won,
            )
            await user_data_manager.update_pet_battle_stats(
                user_id, "pvp",
                wins=1 if player_won else 0, losses=0 if player_won else 1,
                xp_earned=loot_result["xp_gained"], damage_dealt=0, damage_taken=0,
            )

    skill_cds = {str(k):v for k,v in skill_state.get("skill_cooldowns",{}).items()} if skill_state else {}

    return {
        "success": True, "turn": turn_num, "lines": lines,
        "combat": {
            "p_action": p_action, "p_dmg": p_dmg, "p_parry": p_parry,
            "p_is_critical": pr.get("is_critical",False),
            "p_charge_mult": float(ps.get("charge",1.0)),
            "p_charge_after": p_charge,
            "e_action": e_action, "e_dmg": e_dmg, "e_parry": e_parry,
            "e_is_critical": er.get("is_critical",False),
            "e_charge_mult": float(es.get("charge",1.0)),
            "e_charge_after": e_charge,
            "both_defend": p_action=="defend" and e_action=="defend",
        },
        "player": {**ps, "cur_hp": cur_p_hp, "charge": p_charge,
                   "last_action": p_action, "skill_cooldowns": skill_cds},
        "enemy":  {**es, "cur_hp": cur_e_hp, "charge": e_charge, "last_action": e_action},
        "over": over, "won": player_won if over else None,
        "xp_gained":   (loot_result or {}).get("xp_gained", 0),
        "messages":    (loot_result or {}).get("messages", []),
        "skill_cooldowns": skill_cds,
    }

# ── NPC Battle (legacy full-simulation) ──────────────────────────────────────

@router.post("/pets/battle/npc")
async def battle_npc(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    try:
        import random as _random
        from Systems.Pets.Logic.pet_brain import StatsCalculator, DamageCalculator, LootCalculator, NPCBrain
        from Systems.Pets.pets_system import add_experience

        pet = await user_data_manager.get_pet_data_async(user_id)
        if not pet:
            raise HTTPException(status_code=404, detail="No pet found")

        difficulty = (data.get("difficulty") or "easy").lower()
        if difficulty not in ("easy", "average", "hard"):
            raise HTTPException(status_code=400, detail="Invalid difficulty")

        # ── Compute player stats ──────────────────────────────────────────────
        stats = StatsCalculator.calculate_pet_stats(pet)
        p_atk  = int(stats.get("attack",  10))
        p_def  = int(stats.get("defense",  5))
        p_hp   = int(stats.get("max_health", 500))
        p_type = str(pet.get("category", "land")).lower()
        p_elem = str(pet.get("element",  "basic")).lower()
        p_elem2= str(pet.get("element2", "") or "").lower() or None
        p_spec = str(pet.get("species",  "")).strip()

        # ── Generate enemy scaled to player ──────────────────────────────────
        scale = {"easy": (0.70, 0.70, 0.85), "average": (1.10, 1.10, 1.10), "hard": (1.50, 1.50, 1.35)}
        s_atk, s_def, s_hp = scale[difficulty]
        e_atk  = max(1, int(p_atk * s_atk * _random.uniform(0.9, 1.1)))
        e_def  = max(1, int(p_def * s_def * _random.uniform(0.9, 1.1)))
        e_hp   = max(50, int(p_hp  * s_hp  * _random.uniform(0.95, 1.15)))
        # Cap attack so it can't one-shot
        e_atk  = min(e_atk, max(10, p_hp // 12))

        # Pick enemy type/element based on difficulty
        all_types    = list(DamageCalculator.CATEGORY_ADVANTAGES.keys())
        all_elements = list(DamageCalculator.ELEMENT_EFFECTIVENESS.keys())
        if difficulty == "easy":
            cand_types = [t for t in all_types if DamageCalculator.compute_type_bonus(p_type, t) > 1.0] or all_types
            cand_elems = [e for e in all_elements if DamageCalculator.compute_element_bonus(p_elem, e) > 1.0] or all_elements
        elif difficulty == "hard":
            cand_types = [t for t in all_types if DamageCalculator.compute_type_bonus(t, p_type) > 1.0] or all_types
            cand_elems = [e for e in all_elements if DamageCalculator.compute_element_bonus(e, p_elem) > 1.0] or all_elements
        else:
            cand_types = all_types
            cand_elems = all_elements

        e_type = _random.choice(cand_types)
        e_elem = _random.choice(cand_elems)

        # Build a readable enemy name
        try:
            from Systems.Functions.optimal_file_manager import OptimalFileManager
            _base = OptimalFileManager().get_data("base")
            adj  = _random.choice(_base.get("element_bases", {}).get(e_elem, ["Mysterious"]))
            noun = _random.choice(_base.get("category_bases", {}).get(e_type, ["Creature"]))
            enemy_name = f"{adj} {noun}"
        except Exception:
            enemy_name = f"{e_elem.title()} {e_type.title()} Foe"

        # ── Battle simulation ─────────────────────────────────────────────────
        npc_brain   = NPCBrain()
        MAX_TURNS   = 30
        turns       = []

        cur_p_hp = p_hp
        cur_e_hp = e_hp
        p_charge = 1.0
        e_charge = 1.0
        p_last_action = None
        e_last_action = None

        # Action labels for the player's pet
        action_labels = DamageCalculator.get_action_labels(p_type, p_elem, p_spec, custom_labels=pet.get("action_labels", {}))

        for turn_num in range(1, MAX_TURNS + 1):
            if cur_p_hp <= 0 or cur_e_hp <= 0:
                break

            # ── Player action (from request, or default attack on turn 1) ────
            # The client sends one action per call; for simulation we use the
            # submitted action for turn 1 and let the NPC brain drive the enemy.
            # For a full auto-sim we just pick "attack" for the player each turn.
            p_action = (data.get("action") or "attack").lower()
            if p_action not in ("attack", "defend", "charge"):
                p_action = "attack"

            # ── NPC decides ──────────────────────────────────────────────────
            monster_state = {
                "hp": cur_e_hp, "max_hp": e_hp, "prev_hp": cur_e_hp,
                "charge_multiplier": e_charge, "last_action": e_last_action,
                "attack_stat": float(e_atk), "defense_stat": float(e_def),
                "seed": turn_num
            }
            player_state = [{
                "alive": cur_p_hp > 0, "hp": cur_p_hp, "max_hp": p_hp,
                "charging": p_action == "charge"
            }]
            e_decision  = npc_brain.decide_action(monster_state, player_state)
            e_action    = e_decision.get("action", "attack")

            # ── Charge accumulation ──────────────────────────────────────────
            if p_action == "charge":
                p_charge = DamageCalculator.get_next_charge_multiplier(p_charge)
            if e_action == "charge":
                e_charge = DamageCalculator.get_next_charge_multiplier(e_charge)

            # ── Player attacks enemy ─────────────────────────────────────────
            p_result = DamageCalculator.calculate_battle_action(
                attacker_attack=p_atk, target_defense=e_def,
                charge_multiplier=p_charge if p_action == "attack" else 1.0,
                target_charge_multiplier=e_charge if e_action == "defend" else 1.0,
                attacker_action_type=p_action, target_action_type=e_action,
                attacker_type=p_type, attacker_element=p_elem, attacker_element2=p_elem2,
                defender_type=e_type, defender_element=e_elem,
                attacker_species=p_spec
            )

            # ── Enemy attacks player ─────────────────────────────────────────
            e_result = DamageCalculator.calculate_battle_action(
                attacker_attack=e_atk, target_defense=p_def,
                charge_multiplier=e_charge if e_action == "attack" else 1.0,
                target_charge_multiplier=p_charge if p_action == "defend" else 1.0,
                attacker_action_type=e_action, target_action_type=p_action,
                attacker_type=e_type, attacker_element=e_elem,
                defender_type=p_type, defender_element=p_elem, defender_element2=p_elem2,
                defender_species=p_spec
            )

            # ── Apply damage ─────────────────────────────────────────────────
            p_dmg_dealt  = p_result["final_damage"]
            e_dmg_dealt  = e_result["final_damage"]
            p_parry      = p_result["parry_damage"]   # enemy takes parry if player defends
            e_parry      = e_result["parry_damage"]   # player takes parry if enemy defends

            cur_e_hp = max(0, cur_e_hp - p_dmg_dealt - e_parry)
            cur_p_hp = max(0, cur_p_hp - e_dmg_dealt - p_parry)

            # Reset charge after use
            if p_action == "attack":
                p_charge = 1.0
            if e_action == "attack":
                e_charge = 1.0

            p_last_action = p_action
            e_last_action = e_action

            # ── Build turn log entry ─────────────────────────────────────────
            p_action_label = action_labels.get(p_action, p_action.title())
            e_action_label = e_action.title()

            turn_lines = []
            if p_action == "charge":
                turn_lines.append(f"⚡ {pet['name']} charges up! (x{p_charge:.0f})")
            elif p_dmg_dealt > 0:
                bonus = ""
                mult = p_result.get("type_element_bonus_mult_attack", 1.0)
                if mult > 1.0: bonus = " 🔥 Super effective!"
                elif mult < 1.0: bonus = " 💨 Not very effective..."
                turn_lines.append(f"⚔️ {pet['name']} uses {p_action_label} → {p_dmg_dealt} dmg{bonus}")
            elif p_action == "defend":
                if e_parry > 0:
                    turn_lines.append(f"🛡️ {pet['name']} defends and parries {e_parry} dmg back!")
                else:
                    turn_lines.append(f"🛡️ {pet['name']} defends.")

            if e_action == "charge":
                turn_lines.append(f"⚡ {enemy_name} charges up! (x{e_charge:.0f})")
            elif e_dmg_dealt > 0:
                turn_lines.append(f"💥 {enemy_name} attacks → {e_dmg_dealt} dmg")
            elif e_action == "defend":
                if p_parry > 0:
                    turn_lines.append(f"🛡️ {enemy_name} defends and parries {p_parry} dmg back!")
                else:
                    turn_lines.append(f"🛡️ {enemy_name} defends.")

            turns.append({
                "turn": turn_num,
                "lines": turn_lines,
                "player_hp": cur_p_hp,
                "player_max_hp": p_hp,
                "enemy_hp": cur_e_hp,
                "enemy_max_hp": e_hp,
                "player_action": p_action,
                "enemy_action": e_action,
            })

            if cur_p_hp <= 0 or cur_e_hp <= 0:
                break

        # ── Determine outcome ─────────────────────────────────────────────────
        player_won = cur_p_hp > 0 and cur_e_hp <= 0

        # ── Apply XP and loot via LootCalculator ─────────────────────────────
        loot_result = await LootCalculator.calculate_loot(
            user_id=int(user_id),
            pet_data=pet,
            source="npc_battle",
            difficulty=difficulty,
            winner_level=int(pet.get("level", 1)),
            is_winner=player_won
        )

        # ── Update battle_stats ───────────────────────────────────────────────
        total_dealt = sum(
            t["player_max_hp"] - t["enemy_hp"] for t in turns[:1]
        )
        # Simpler: just count from turns
        total_p_dealt = sum(
            max(0, (turns[i-1]["enemy_hp"] if i > 0 else e_hp) - t["enemy_hp"])
            for i, t in enumerate(turns)
        )
        total_e_dealt = sum(
            max(0, (turns[i-1]["player_hp"] if i > 0 else p_hp) - t["player_hp"])
            for i, t in enumerate(turns)
        )

        await user_data_manager.update_pet_battle_stats(
            user_id, "npc",
            wins=1 if player_won else 0,
            losses=0 if player_won else 1,
            xp_earned=loot_result["xp_gained"],
            damage_dealt=total_p_dealt,
            damage_taken=total_e_dealt
        )

        # ── Level change data for popup ───────────────────────────────────────
        refreshed = _enrich_pet(await user_data_manager.get_pet_data_async(user_id))
        old_level = int(pet.get("level", 1))
        new_level = int(refreshed.get("level", 1)) if refreshed else old_level
        level_change = loot_result.get("level_change")
        if level_change is None and new_level != old_level:
            level_change = {"old_level": old_level, "new_level": new_level, "gains": {}}

        # ── GPP: invalidate stats cache + emit event ──────────────────────────
        _invalidate_stats_cache(pet)
        queue = EventQueue()
        queue.push("battle_npc_completed", {"user_id": user_id, "won": player_won, "difficulty": difficulty, "xp_gained": loot_result["xp_gained"]})
        await queue.flush()

        # ── GPP: build animation metadata (Component pattern) ─────────────
        animation = AnimationComponent.for_mission(player_won, loot_result["xp_gained"], difficulty)

        return JSONResponse(content={
            "success": True,
            "won": player_won,
            "turns": turns,
            "enemy": {
                "name": enemy_name,
                "type": e_type,
                "element": e_elem,
                "max_hp": e_hp,
                "attack": e_atk,
                "defense": e_def,
            },
            "player": {
                "name": pet["name"],
                "max_hp": p_hp,
                "attack": p_atk,
                "defense": p_def,
            },
            "xp_gained": loot_result["xp_gained"],
            "messages": loot_result["messages"],
            "level_change": level_change,
            "pet": refreshed,
            "animation": animation,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"battle_npc error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Battle failed.")


# ── Shared battle simulation helpers (used by arena_api) ─────────────────────

async def _run_npc_battle_sim(user_id: str, difficulty: str) -> dict:
    """
    Runs a full NPC battle simulation for the given user and returns the result dict.
    Extracted so arena_api can reuse it without duplicating logic.
    """
    import random as _random
    from Systems.Pets.Logic.pet_brain import StatsCalculator, DamageCalculator, LootCalculator, NPCBrain
    from Systems.Functions.optimal_file_manager import OptimalFileManager

    pet = await user_data_manager.get_pet_data_async(user_id)
    if not pet:
        raise ValueError("No pet found")

    stats  = StatsCalculator.calculate_pet_stats(pet)
    p_atk  = int(stats.get("attack",  10))
    p_def  = int(stats.get("defense",  5))
    p_hp   = int(stats.get("max_health", 500))
    p_type = str(pet.get("category", "land")).lower()
    p_elem = str(pet.get("element",  "basic")).lower()
    p_elem2= str(pet.get("element2", "") or "").lower() or None
    p_spec = str(pet.get("species",  "")).strip()

    scale = {"easy": (0.70, 0.70, 0.85), "average": (1.10, 1.10, 1.10), "hard": (1.50, 1.50, 1.35)}
    s_atk, s_def, s_hp = scale.get(difficulty, scale["easy"])
    e_atk  = max(1, int(p_atk * s_atk * _random.uniform(0.9, 1.1)))
    e_def  = max(1, int(p_def * s_def * _random.uniform(0.9, 1.1)))
    e_hp   = max(50, int(p_hp  * s_hp  * _random.uniform(0.95, 1.15)))
    e_atk  = min(e_atk, max(10, p_hp // 12))

    all_types    = list(DamageCalculator.CATEGORY_ADVANTAGES.keys())
    all_elements = list(DamageCalculator.ELEMENT_EFFECTIVENESS.keys())
    if difficulty == "easy":
        cand_types = [t for t in all_types if DamageCalculator.compute_type_bonus(p_type, t) > 1.0] or all_types
        cand_elems = [e for e in all_elements if DamageCalculator.compute_element_bonus(p_elem, e) > 1.0] or all_elements
    elif difficulty == "hard":
        cand_types = [t for t in all_types if DamageCalculator.compute_type_bonus(t, p_type) > 1.0] or all_types
        cand_elems = [e for e in all_elements if DamageCalculator.compute_element_bonus(e, p_elem) > 1.0] or all_elements
    else:
        cand_types, cand_elems = all_types, all_elements

    e_type = _random.choice(cand_types)
    e_elem = _random.choice(cand_elems)

    try:
        _base = OptimalFileManager().get_data("base")
        adj  = _random.choice(_base.get("element_bases", {}).get(e_elem, ["Mysterious"]))
        noun = _random.choice(_base.get("category_bases", {}).get(e_type, ["Creature"]))
        enemy_name = f"{adj} {noun}"
    except Exception:
        enemy_name = f"{e_elem.title()} {e_type.title()} Foe"

    npc_brain = NPCBrain()
    MAX_TURNS = 30
    turns: list = []
    cur_p_hp, cur_e_hp = p_hp, e_hp
    p_charge, e_charge = 1.0, 1.0
    p_last_action = e_last_action = None
    action_labels = DamageCalculator.get_action_labels(p_type, p_elem, p_spec, custom_labels=pet.get("action_labels", {}))

    # Initialise skill state for web sim
    player_skill_state: dict = {"total_attack": p_atk, "max_hp": p_hp, "active_effects": [], "skill_cooldown": 0}
    try:
        from Systems.Pets.Logic.battle_skills import init_battle_skill_state
        init_battle_skill_state(player_skill_state)
    except Exception:
        pass

    for turn_num in range(1, MAX_TURNS + 1):
        if cur_p_hp <= 0 or cur_e_hp <= 0:
            break
        p_action = "attack"

        # Tick active skill effects for player
        try:
            from Systems.Pets.Logic.battle_skills import tick_battle_effects, is_stunned, consume_stun
            net_delta, tick_lines = tick_battle_effects(player_skill_state, p_atk)
            if net_delta != 0:
                cur_p_hp = max(0, min(p_hp, cur_p_hp + net_delta))
            if is_stunned(player_skill_state):
                consume_stun(player_skill_state)
                p_action = "defend"  # stunned = skip turn
        except Exception:
            pass
        monster_state = {
            "hp": cur_e_hp, "max_hp": e_hp, "prev_hp": cur_e_hp,
            "charge_multiplier": e_charge, "last_action": e_last_action,
            "attack_stat": float(e_atk), "defense_stat": float(e_def), "seed": turn_num,
        }
        e_decision = npc_brain.decide_action(monster_state, [{"alive": cur_p_hp > 0, "hp": cur_p_hp, "max_hp": p_hp, "charging": False}])
        e_action   = e_decision.get("action", "attack")

        if p_action == "charge": p_charge = DamageCalculator.get_next_charge_multiplier(p_charge)
        if e_action == "charge": e_charge = DamageCalculator.get_next_charge_multiplier(e_charge)

        p_result = DamageCalculator.calculate_battle_action(
            attacker_attack=p_atk, target_defense=e_def,
            charge_multiplier=p_charge if p_action == "attack" else 1.0,
            target_charge_multiplier=e_charge if e_action == "defend" else 1.0,
            attacker_action_type=p_action, target_action_type=e_action,
            attacker_type=p_type, attacker_element=p_elem, attacker_element2=p_elem2,
            defender_type=e_type, defender_element=e_elem, attacker_species=p_spec,
            attacker_pet_data=pet, attacker_user_id=str(user_id),
            battle_type="npc",
        )
        e_result = DamageCalculator.calculate_battle_action(
            attacker_attack=e_atk, target_defense=p_def,
            charge_multiplier=e_charge if e_action == "attack" else 1.0,
            target_charge_multiplier=p_charge if p_action == "defend" else 1.0,
            attacker_action_type=e_action, target_action_type=p_action,
            attacker_type=e_type, attacker_element=e_elem,
            defender_type=p_type, defender_element=p_elem, defender_element2=p_elem2, defender_species=p_spec,
            defender_pet_data=pet, defender_user_id=str(user_id),
            defender_current_hp=cur_p_hp, defender_max_hp=p_hp,
            battle_type="npc",
        )

        p_dmg_dealt = p_result["final_damage"]
        e_dmg_dealt = e_result["final_damage"]
        e_parry     = p_result["parry_damage"]
        p_parry     = e_result["parry_damage"]
        cur_e_hp    = max(0, cur_e_hp - p_dmg_dealt - e_parry)
        cur_p_hp    = max(0, cur_p_hp - e_dmg_dealt - p_parry)
        if p_action == "attack" or p_action == "defend": p_charge = 1.0
        if e_action == "attack" or e_action == "defend": e_charge = 1.0
        p_last_action = p_action
        e_last_action = e_action

        p_action_label = action_labels.get(p_action, p_action.title())
        p_crit_tag = " ⚡CRITICAL!" if p_result.get("is_critical") else ""
        e_crit_tag = " ⚡CRITICAL!" if e_result.get("is_critical") else ""
        turn_lines = []
        if p_dmg_dealt > 0:
            mult = p_result.get("type_element_bonus_mult_attack", 1.0)
            bonus = " 🔥" if mult > 1.0 else (" 💨" if mult < 1.0 else "")
            ct = f" [x{p_charge:.0f}]" if p_action == "attack" and p_charge > 1.0 else ""
            turn_lines.append(f"⚔️ {pet['name']} {p_action_label}{ct}{p_crit_tag} → {p_dmg_dealt} dmg{bonus}")
        elif p_action == "defend":
            dt = f" [def roll: {p_result.get('defense_roll', '?')}]" if p_result.get("defense_roll") else ""
            turn_lines.append(f"🛡️ {pet['name']} defends{dt}" + (f" — parries {e_parry}!" if e_parry else ""))
        elif p_action == "charge":
            turn_lines.append(f"⚡ {pet['name']} charges (x{p_charge:.0f})")
        if e_dmg_dealt > 0:
            ct = f" [x{e_charge:.0f}]" if e_action == "attack" and e_charge > 1.0 else ""
            turn_lines.append(f"💥 {enemy_name} attacks{ct}{e_crit_tag} → {e_dmg_dealt} dmg")
        elif e_action == "defend":
            dt = f" [def roll: {e_result.get('defense_roll', '?')}]" if e_result.get("defense_roll") else ""
            turn_lines.append(f"🛡️ {enemy_name} defends{dt}" + (f" — parries {p_parry}!" if p_parry else ""))
        elif e_action == "charge":
            turn_lines.append(f"⚡ {enemy_name} charges (x{e_charge:.0f})")

        turns.append({
            "turn": turn_num, "lines": turn_lines,
            "player_hp": cur_p_hp, "player_max_hp": p_hp,
            "enemy_hp": cur_e_hp,  "enemy_max_hp": e_hp,
            "player_action": p_action, "enemy_action": e_action,
            "player_dmg": p_dmg_dealt, "enemy_dmg": e_dmg_dealt,
            "player_parry": p_parry, "enemy_parry": e_parry,
            "player_charge": p_charge, "enemy_charge": e_charge,
            "player_crit": p_result.get("is_critical", False),
            "enemy_crit": e_result.get("is_critical", False),
            "player_type_elem": round(p_result.get("type_element_bonus_mult_attack", 1.0), 2),
            "enemy_type_elem": round(e_result.get("type_element_bonus_mult_attack", 1.0), 2),
        })
        if cur_p_hp <= 0 or cur_e_hp <= 0:
            break

    player_won = cur_p_hp > 0 and cur_e_hp <= 0
    loot_result = await LootCalculator.calculate_loot(
        user_id=int(user_id), pet_data=pet, source="npc_battle",
        difficulty=difficulty, winner_level=int(pet.get("level", 1)), is_winner=player_won,
    )
    await user_data_manager.update_pet_battle_stats(
        user_id, "npc",
        wins=1 if player_won else 0, losses=0 if player_won else 1,
        xp_earned=loot_result["xp_gained"], damage_dealt=0, damage_taken=0,
    )
    refreshed = _enrich_pet(await user_data_manager.get_pet_data_async(user_id))
    old_level  = int(pet.get("level", 1))
    new_level  = int(refreshed.get("level", 1)) if refreshed else old_level
    level_change = loot_result.get("level_change")
    if level_change is None and new_level != old_level:
        level_change = {"old_level": old_level, "new_level": new_level, "gains": {}}

    return {
        "won": player_won, "turns": turns,
        "enemy":  {"name": enemy_name, "type": e_type, "element": e_elem, "max_hp": e_hp, "attack": e_atk, "defense": e_def},
        "player": {"name": pet["name"], "max_hp": p_hp, "attack": p_atk, "defense": p_def},
        "xp_gained": loot_result["xp_gained"],
        "messages":  loot_result["messages"],
        "level_change": level_change,
        "pet": refreshed,
    }


async def _run_pvp_battle_sim(user_id: str, challenger_id: str) -> dict:
    """PvP simulation between two users' pets with relationship multipliers and proper battle logic."""
    import random as _random
    from Systems.Pets.Logic.pet_brain import StatsCalculator, DamageCalculator, LootCalculator
    from Systems.Pets.PetGames.pvp_system import get_relationship_multipliers

    pet_a = await user_data_manager.get_pet_data_async(user_id)
    pet_b = await user_data_manager.get_pet_data_async(challenger_id)
    if not pet_a or not pet_b:
        raise ValueError("One or both users have no pet")

    # Get relationship multipliers for PvP
    rel_mult_a, rel_mult_b = await get_relationship_multipliers(user_id, challenger_id)

    def _stats(pet):
        s = StatsCalculator.calculate_pet_stats(pet)
        return {
            "atk": int(s.get("attack", 10)), "def": int(s.get("defense", 5)),
            "hp":  int(s.get("max_health", 500)),
            "type": str(pet.get("category", "land")).lower(),
            "elem": str(pet.get("element", "basic")).lower(),
            "elem2": str(pet.get("element2", "") or "").lower() or None,
            "spec": str(pet.get("species", "")),
        }

    sa, sb = _stats(pet_a), _stats(pet_b)
    hp_a, hp_b = sa["hp"], sb["hp"]
    charge_a = charge_b = 1.0
    turns: list = []
    log: list = []

    for turn_num in range(1, 31):
        if hp_a <= 0 or hp_b <= 0:
            break
        act_a = _random.choice(["attack", "attack", "attack", "defend", "charge"])
        act_b = _random.choice(["attack", "attack", "attack", "defend", "charge"])

        if act_a == "charge": charge_a = DamageCalculator.get_next_charge_multiplier(charge_a)
        if act_b == "charge": charge_b = DamageCalculator.get_next_charge_multiplier(charge_b)

        # Apply charging vulnerability: target takes 1.25x damage when charging
        vuln_a = 1.25 if act_a == "charge" else 1.0
        vuln_b = 1.25 if act_b == "charge" else 1.0

        r_a = DamageCalculator.calculate_battle_action(
            attacker_attack=sa["atk"], target_defense=sb["def"],
            charge_multiplier=charge_a if act_a == "attack" else 1.0,
            target_charge_multiplier=charge_b if act_b == "defend" else 1.0,
            attacker_action_type=act_a, target_action_type=act_b,
            attacker_type=sa["type"], attacker_element=sa["elem"], attacker_element2=sa["elem2"],
            defender_type=sb["type"], defender_element=sb["elem"], defender_element2=sb["elem2"],
            attacker_species=sa["spec"],
            attacker_pet_data=pet_a, defender_pet_data=pet_b,
            attacker_user_id=str(user_id), defender_user_id=str(challenger_id),
            defender_current_hp=hp_b, defender_max_hp=sb["hp"],
            battle_type="pvp",
        )
        r_b = DamageCalculator.calculate_battle_action(
            attacker_attack=sb["atk"], target_defense=sa["def"],
            charge_multiplier=charge_b if act_b == "attack" else 1.0,
            target_charge_multiplier=charge_a if act_a == "defend" else 1.0,
            attacker_action_type=act_b, target_action_type=act_a,
            attacker_type=sb["type"], attacker_element=sb["elem"], attacker_element2=sb["elem2"],
            defender_type=sa["type"], defender_element=sa["elem"], defender_element2=sa["elem2"],
            attacker_species=sb["spec"],
            attacker_pet_data=pet_b, defender_pet_data=pet_a,
            attacker_user_id=str(challenger_id), defender_user_id=str(user_id),
            defender_current_hp=hp_a, defender_max_hp=sa["hp"],
            battle_type="pvp",
        )

        # Apply relationship multipliers AND charging vulnerability to damage
        dmg_a = int(r_a["final_damage"] * rel_mult_a * vuln_b)
        dmg_b = int(r_b["final_damage"] * rel_mult_b * vuln_a)
        parry_a = int(r_a["parry_damage"] * rel_mult_a)
        parry_b = int(r_b["parry_damage"] * rel_mult_b)

        hp_b = max(0, hp_b - dmg_a - parry_b)
        hp_a = max(0, hp_a - dmg_b - parry_a)
        if act_a == "attack": charge_a = 1.0
        if act_b == "attack": charge_b = 1.0

        lines = []
        # Build combat data for frontend rendering
        def _action_text(name, action, result, dmg, charge, parry, vuln):
            parts = []
            if action == "charge":
                parts.append(f"⚡ {name} charges (x{charge:.0f})")
            elif action == "defend":
                parts.append(f"🛡️ {name} defends")
            elif action == "attack":
                a = []
                a.append(f"⚔️ {name} attacks")
                if result.get("is_critical"):
                    a.append("⚡CRITICAL!")
                if charge > 1:
                    a.append(f"(x{charge:.0f})")
                a.append(f"→ {dmg} dmg")
                if dmg > 0:
                    te = result.get("type_element_bonus_mult_attack", 1.0)
                    if te > 1.05:
                        a.append("(super effective)")
                    elif te < 0.95:
                        a.append("(not very effective)")
                    a.append(f"[x{result.get('critical_multiplier',1):.1f}]" if result.get("is_critical") else "")
                if parry > 0:
                    a.append(f"parried {parry}")
                parts.append(" ".join(filter(None, a)))
            return " ".join(parts)

        ta = _action_text(pet_a['name'], act_a, r_a, dmg_a, charge_a, parry_a, vuln_a)
        tb = _action_text(pet_b['name'], act_b, r_b, dmg_b, charge_b, parry_b, vuln_b)
        if ta:
            # Add relationship multiplier if relevant
            rel_tag = f" (rel x{rel_mult_a:.1f})" if rel_mult_a != 1.0 else ""
            lines.append(f"{ta}{rel_tag}")
        if tb:
            rel_tag = f" (rel x{rel_mult_b:.1f})" if rel_mult_b != 1.0 else ""
            lines.append(f"{tb}{rel_tag}")

        # Attack rolls for info
        if act_a == "attack":
            ar = r_a.get("attack_roll")
            if ar: lines.append(f"  [atk roll: {ar}]")
        if act_b == "attack":
            ar = r_b.get("attack_roll")
            if ar: lines.append(f"  [atk roll: {ar}]")

        turns.append({
            "turn": turn_num,
            "lines": lines,
            "hp_a": hp_a, "hp_b": hp_b,
            "p_action": act_a, "e_action": act_b,
            "p_dmg": dmg_a, "e_dmg": dmg_b,
            "p_charge": charge_a, "e_charge": charge_b,
            "p_parry": parry_a, "e_parry": parry_b,
            "p_crit": r_a.get("is_critical", False), "e_crit": r_b.get("is_critical", False),
            "p_type_elem": round(r_a.get("type_element_bonus_mult_attack", 1.0), 2),
            "e_type_elem": round(r_b.get("type_element_bonus_mult_attack", 1.0), 2),
        })
        log.extend(lines)
        if hp_a <= 0 or hp_b <= 0:
            break

    winner_id   = user_id if hp_a > 0 else challenger_id
    loser_id    = challenger_id if hp_a > 0 else user_id
    winner_pet  = pet_a if hp_a > 0 else pet_b
    loser_pet   = pet_b if hp_a > 0 else pet_a

    win_loot  = await LootCalculator.calculate_loot(int(winner_id), winner_pet, "pvp_battle", "normal", int(winner_pet.get("level",1)), int(loser_pet.get("level",1)), True)
    loss_loot = await LootCalculator.calculate_loot(int(loser_id),  loser_pet,  "pvp_battle", "normal", int(winner_pet.get("level",1)), int(loser_pet.get("level",1)), False)

    # Save battle stats for both players
    await user_data_manager.update_pet_battle_stats(winner_id, "pvp", wins=1, losses=0, xp_earned=win_loot["xp_gained"], damage_dealt=0, damage_taken=0)
    await user_data_manager.update_pet_battle_stats(loser_id, "pvp", wins=0, losses=1, xp_earned=loss_loot["xp_gained"], damage_dealt=0, damage_taken=0)

    log.append(f"🏆 {winner_pet['name']} wins! +{win_loot['xp_gained']} XP")
    log.append(f"💀 {loser_pet['name']} defeated. +{loss_loot['xp_gained']} XP")

    return {
        "winner_id": winner_id, "loser_id": loser_id,
        "winner_name": winner_pet["name"], "loser_name": loser_pet["name"],
        "player_name": pet_a["name"], "enemy_name": pet_b["name"],
        "start_hp_a": sa["hp"], "start_hp_b": sb["hp"],
        "turns": turns, "log": log,
        "winner_xp": win_loot["xp_gained"], "loser_xp": loss_loot["xp_gained"],
        "level_change": win_loot.get("level_change"),
    }


# ── Ability & Stat Mastery Tree ───────────────────────────────────────────────

@router.get("/pets/ability-tree")
async def get_ability_tree(request: Request):
    """Return the full ability tree state for the current user's pet."""
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    user_id = str(user.get("id"))
    pet = await user_data_manager.get_pet_data_async(user_id)
    if not pet:
        raise HTTPException(status_code=404, detail="No pet found")
    # initialize_ability_tree may add fields to pet; save if anything was added
    had_tree = "ability_points" in pet and "stat_mastery" in pet and "abilities" in pet
    state = get_tree_state(pet)  # calls initialize_ability_tree internally
    if not had_tree:
        await user_data_manager.save_pet_data(user_id, pet.get("name", "Pet"), pet)
    return JSONResponse(content=state)


@router.post("/pets/ability-tree/mastery")
async def spend_mastery_points(request: Request, data: Dict[str, Any] = Body(...)):
    """
    Spend ability points on stat mastery.
    Body: { "stat": "ATT", "points": 1 }
    """
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    user_id = str(user.get("id"))

    stat   = str(data.get("stat", "")).upper()
    points = int(data.get("points", 1))

    if stat not in STATS:
        raise HTTPException(status_code=400, detail=f"Invalid stat: {stat}")
    if points < 1:
        raise HTTPException(status_code=400, detail="Points must be >= 1")

    pet = await user_data_manager.get_pet_data_async(user_id)
    if not pet:
        raise HTTPException(status_code=404, detail="No pet found")

    success, message = spend_stat_mastery(pet, stat, points)
    if not success:
        return JSONResponse(content={"ok": False, "message": message}, status_code=400)

    await user_data_manager.save_pet_data(user_id, pet.get("name", "Pet"), pet)
    _invalidate_stats_cache(pet)

    # ── GPP: emit event + animation ────────────────────────────────────────
    queue = EventQueue()
    queue.push("stat_mastery_spent", {"user_id": user_id, "stat": stat, "points": points})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("mastery_gain", 500)

    return JSONResponse(content={"ok": True, "message": message, "tree": get_tree_state(pet), "animation": animation})


@router.post("/pets/ability-tree/advantage-mastery")
async def spend_advantage_mastery_points(request: Request, data: Dict[str, Any] = Body(...)):
    """
    Spend ability points on advantage mastery (type or element).
    Body: { "key": "type", "points": 1 }
    """
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    user_id = str(user.get("id"))

    key    = str(data.get("key", "")).lower()
    points = int(data.get("points", 1))

    if key not in ADVANTAGE_MASTERY_KEYS:
        raise HTTPException(status_code=400, detail=f"Invalid advantage mastery key: {key}. Valid: {ADVANTAGE_MASTERY_KEYS}")
    if points < 1:
        raise HTTPException(status_code=400, detail="Points must be >= 1")

    pet = await user_data_manager.get_pet_data_async(user_id)
    if not pet:
        raise HTTPException(status_code=404, detail="No pet found")

    success, message = spend_advantage_mastery(pet, key, points)
    if not success:
        return JSONResponse(content={"ok": False, "message": message}, status_code=400)

    await user_data_manager.save_pet_data(user_id, pet.get("name", "Pet"), pet)
    _invalidate_stats_cache(pet)

    # ── GPP: emit event + animation ────────────────────────────────────────
    queue = EventQueue()
    queue.push("advantage_mastery_spent", {"user_id": user_id, "key": key, "points": points})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("mastery_gain", 500)

    return JSONResponse(content={"ok": True, "message": message, "tree": get_tree_state(pet), "animation": animation})


@router.post("/pets/ability-tree/unlock")
async def unlock_ability_endpoint(request: Request, data: Dict[str, Any] = Body(...)):
    """
    Unlock an ability.
    Body: { "ability_id": "att_strike" }
    """
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    user_id = str(user.get("id"))

    ability_id = str(data.get("ability_id", ""))
    if not ability_id:
        raise HTTPException(status_code=400, detail="ability_id is required")

    pet = await user_data_manager.get_pet_data_async(user_id)
    if not pet:
        raise HTTPException(status_code=404, detail="No pet found")

    success, message = unlock_ability(pet, ability_id)
    if not success:
        return JSONResponse(content={"ok": False, "message": message}, status_code=400)

    await user_data_manager.save_pet_data(user_id, pet.get("name", "Pet"), pet)
    _invalidate_stats_cache(pet)

    # ── GPP: emit event + animation ────────────────────────────────────────
    queue = EventQueue()
    queue.push("ability_unlocked", {"user_id": user_id, "ability_id": ability_id})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("ability_unlock", 600)

    return JSONResponse(content={"ok": True, "message": message, "tree": get_tree_state(pet), "animation": animation})


@router.post("/pets/ability-tree/purchase")
async def purchase_ability_point_endpoint(request: Request):
    """
    Purchase 1 ability point by spending 500 levels.
    """
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    user_id = str(user.get("id"))

    pet = await user_data_manager.get_pet_data_async(user_id)
    if not pet:
        raise HTTPException(status_code=404, detail="No pet found")

    success, message = purchase_ability_point(pet)
    if not success:
        return JSONResponse(content={"ok": False, "message": message}, status_code=400)

    await user_data_manager.save_pet_data(user_id, pet.get("name", "Pet"), pet)
    _invalidate_stats_cache(pet)

    # ── GPP: emit event + animation ────────────────────────────────────────
    queue = EventQueue()
    queue.push("ability_point_purchased", {"user_id": user_id})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("point_purchase", 500)

    return JSONResponse(content={"ok": True, "message": message, "tree": get_tree_state(pet), "animation": animation})


# ── Battle Skills ─────────────────────────────────────────────────────────────

@router.get("/pets/skills")
async def get_pet_skills(request: Request):
    """Return the current skill state for the user's pet."""
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    user_id = str(user.get("id"))
    pet = await user_data_manager.get_pet_data_async(user_id)
    if not pet:
        raise HTTPException(status_code=404, detail="No pet found")
    return JSONResponse(content=get_skill_state(pet))


@router.post("/pets/skills/draw")
async def draw_skill_choices_endpoint(request: Request, data: Dict[str, Any] = Body(default={})):
    """
    Draw 5 skill choices from the pet's element pool for a given slot.
    Costs 1 ability point per draw. The point is spent immediately on draw,
    not on equip — so choose carefully.
    Body: { "slot": 0, "cross_element": false }
    """
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    user_id = str(user.get("id"))
    pet = await user_data_manager.get_pet_data_async(user_id)
    if not pet:
        raise HTTPException(status_code=404, detail="No pet found")

    cross = bool(data.get("cross_element", False))

    # Check ability point balance
    available_points = int(pet.get("ability_points") or 0)
    if available_points < 1:
        return JSONResponse(
            content={"ok": False, "message": "Not enough ability points. Drawing costs 1 ability point."},
            status_code=400,
        )

    # Deduct the point before returning choices
    pet["ability_points"] = available_points - 1
    await user_data_manager.save_pet_data(user_id, pet.get("name", "Pet"), pet)
    _invalidate_stats_cache(pet)

    # ── GPP: emit event + animation ────────────────────────────────────────
    queue = EventQueue()
    queue.push("skill_choices_drawn", {"user_id": user_id, "cross_element": cross, "count": 5})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("skill_draw", 600)

    choices = draw_skill_choices(pet, count=5, cross_element=cross)
    return JSONResponse(content={"ok": True, "choices": choices, "ability_points": pet["ability_points"], "animation": animation})


@router.post("/pets/skills/equip")
async def equip_skill_endpoint(request: Request, data: Dict[str, Any] = Body(...)):
    """
    Equip a skill into a slot.
    Body: { "skill_id": "fire_001", "slot": 0 }
    """
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    user_id = str(user.get("id"))

    skill_id   = str(data.get("skill_id", ""))
    slot_index = int(data.get("slot", 0))

    if not skill_id:
        raise HTTPException(status_code=400, detail="skill_id is required")
    if skill_id not in SKILL_BY_ID:
        raise HTTPException(status_code=400, detail=f"Unknown skill: {skill_id}")

    pet = await user_data_manager.get_pet_data_async(user_id)
    if not pet:
        raise HTTPException(status_code=404, detail="No pet found")

    success, message = equip_skill(pet, skill_id, slot_index)
    if not success:
        return JSONResponse(content={"ok": False, "message": message}, status_code=400)

    await user_data_manager.save_pet_data(user_id, pet.get("name", "Pet"), pet)
    _invalidate_stats_cache(pet)

    # ── GPP: emit event + animation ────────────────────────────────────────
    queue = EventQueue()
    queue.push("skill_equipped", {"user_id": user_id, "skill_id": skill_id, "slot": slot_index})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("skill_equip", 500)

    return JSONResponse(content={"ok": True, "message": message, "skills": get_skill_state(pet), "animation": animation})


@router.post("/pets/skills/migrate")
async def migrate_pet_skills(request: Request):
    """
    One-time migration for existing pets that have no battle skill.
    Assigns a random skill from their element pool and grants 1 free ability point.
    Safe to call multiple times — only acts if the pet has no battle_skills set.
    """
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    user_id = str(user.get("id"))

    pet = await user_data_manager.get_pet_data_async(user_id)
    if not pet:
        raise HTTPException(status_code=404, detail="No pet found")

    existing = get_equipped_skills(pet)
    if existing:
        return JSONResponse(content={
            "ok": True,
            "already_migrated": True,
            "message": "Your pet already has a battle skill.",
            "skills": get_skill_state(pet),
        })

    # Assign a random skill from the pet's element pool(s)
    element1 = str(pet.get("element", "basic")).lower()
    element2 = str(pet.get("element2") or "").lower() or None
    choices = draw_initial_skill_choices(element1, element2, count=5)
    if not choices:
        raise HTTPException(status_code=500, detail="Could not draw skill choices for this pet's elements.")

    import random as _random
    chosen = _random.choice(choices)
    equip_skill(pet, chosen["id"], 0)

    # Grant 1 free ability point so they can reroll if they want
    pet["ability_points"] = int(pet.get("ability_points") or 0) + 1

    await user_data_manager.save_pet_data(user_id, pet.get("name", "Pet"), pet)
    _invalidate_stats_cache(pet)

    # ── GPP: emit event + animation ────────────────────────────────────────
    queue = EventQueue()
    queue.push("skills_migrated", {"user_id": user_id, "skill_id": chosen["id"]})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("migration_complete", 600)

    return JSONResponse(content={
        "ok": True,
        "already_migrated": False,
        "message": f"Assigned **{chosen['name']}** as your starting battle skill and granted 1 free ability point to reroll if you'd like.",
        "assigned_skill": chosen,
        "skills": get_skill_state(pet),
        "animation": animation,
    })


@router.post("/pets/skills/adopt-draw")
async def draw_adoption_skills(request: Request, data: Dict[str, Any] = Body(...)):
    """
    Draw 5 skill choices for a new pet during adoption (before the pet is created).
    Body: { "element1": "fire", "element2": "water" }
    Returns 5 skill choices from the combined element pool.
    """
    user = request.session.get("discord_user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    element1 = str(data.get("element1", "basic")).lower()
    element2 = str(data.get("element2") or "").lower() or None

    if element1 not in ALL_ELEMENTS:
        element1 = "basic"
    if element2 and element2 not in ALL_ELEMENTS:
        element2 = None

    choices = draw_initial_skill_choices(element1, element2, count=5)

    # ── GPP: emit skill_draw event (Observer pattern) ───────────────────────
    queue = EventQueue()
    queue.push("skill_draw", {"user_id": str(user.get("id")), "elements": [element1, element2], "count": len(choices)})
    await queue.flush()

    # ── GPP: build animation metadata (Component pattern) ─────────────
    animation = AnimationComponent.for_ui_update("skill_draw", 500)

    return JSONResponse(content={"choices": choices, "animation": animation})

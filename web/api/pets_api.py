from fastapi import APIRouter, HTTPException, Request, Body
from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.pet_brain import StatsCalculator, LootCalculator
from fastapi.responses import JSONResponse
import json
import os
import logging
import re
from typing import Dict, Any
from datetime import datetime
from Systems.Functions import cooldown_db

logger = logging.getLogger(__name__)

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

router = APIRouter()

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
    """Add computed_stats, xp_for_next_level, and total_xp to a raw pet dict.
    Call this on every pet dict before returning it to the frontend so the
    XP bar and stats always have the data they need."""
    if not pet:
        return pet
    computed_stats    = StatsCalculator.calculate_pet_stats(pet)
    lvl               = int(pet.get("level", 1))
    rem               = int(pet.get("experience", 0))
    xp_for_next_level = LootCalculator.get_next_level_xp(lvl)
    total_xp          = int(LootCalculator.get_total_experience_for_level(lvl)) + rem
    return {
        **pet,
        "computed_stats":    computed_stats,
        "xp_for_next_level": xp_for_next_level,
        "total_xp":          total_xp,
    }


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


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


# ── Pet species / equipment data ─────────────────────────────────────────────

@router.get("/pets-data")
async def get_pets_data():
    try:
        path = os.path.join(project_root, "Systems", "Pets", "Logic", "info.json")
        return JSONResponse(content=_load_json(path))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Pets data file not found")
    except Exception as e:
        logger.error(f"get_pets_data error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch pets data")


@router.get("/equipment-data")
async def get_equipment_data():
    try:
        path = os.path.join(project_root, "Systems", "Pets", "Logic", "equipment.json")
        return JSONResponse(content=_load_json(path))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Equipment data file not found")
    except Exception as e:
        logger.error(f"get_equipment_data error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch equipment data")


@router.get("/pets/available")
async def get_available_pets():
    try:
        path = os.path.join(project_root, "Systems", "Pets", "Logic", "info.json")
        pets_data = _load_json(path)
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

        return JSONResponse(content={"has_pet": True, **_enrich_pet(pet_data)})
    except Exception as e:
        logger.error(f"get_user_pet error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch user pet data")


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
            
            # Automatically generate tasks for the new pet owner
            try:
                from web.api.tasks_api import tasks_db
                await tasks_db.get_slots(str(user_id))  # This will create tasks if they don't exist
                logger.info(f"Tasks generated for new pet owner {user_id}")
            except Exception as e:
                logger.error(f"Error generating tasks for new pet owner {user_id}: {e}")
            
            return JSONResponse(content={"success": True, "pet": pet_data})
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

        # Task tracking — figure out which battle action was renamed (if any)
        try:
            from web.api.tasks_api import record_action as _task_record
            renamed_action = None
            if actions:
                for key in ("Attack", "Defense", "Charge"):
                    if (actions.get(key) or "").strip():
                        renamed_action = key
                        break
            await _task_record(str(user_id), "rename", meta={"battle_action": renamed_action} if renamed_action else None)
        except Exception:
            pass

        return JSONResponse(content={"success": True, "name": new_name})

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

        success = await user_data_manager.delete_pet_data(str(user_id))
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete pet")

        logger.info(f"Pet killed for user {user_id}")
        return JSONResponse(content={"success": True})

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
        if difficulty not in ("Easy", "Average", "Hard"):
            raise HTTPException(status_code=400, detail="Invalid difficulty")

        import random
        success_chance = {"Easy": 0.9, "Average": 0.7, "Hard": 0.5}[difficulty]
        base_xp_map    = {"Easy": 50,  "Average": 100, "Hard": 200}

        pet_level = int(pet.get("level", 1))

        if random.random() < success_chance:
            xp = _level_scaled_xp(base_xp_map[difficulty], pet_level)
            from Systems.Pets.pets_system import add_experience
            _, lvl_data = await add_experience(int(user_id), xp, "training")
            await _aset_cooldown("train", user_id)
            result = {
                "success": True,
                "outcome": f"🏋️ Training successful! Gained {xp} XP (Lv.{pet_level} bonus applied).",
                "xp": xp,
                "level_up": lvl_data if (lvl_data and lvl_data.get("new_level", 0) > lvl_data.get("old_level", 0)) else None,
            }
            try:
                from web.api.tasks_api import record_action as _task_record
                await _task_record(user_id, "train")
            except Exception:
                pass
        else:
            await _aset_cooldown("train", user_id)
            result = {"success": False, "outcome": "❌ Training failed — your pet got away safely.", "xp": 0, "level_up": None}

        # Return refreshed pet
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

            result = {"success": True, "outcome": "\n".join(outcome_lines), "xp": xp, "level_up": level_up}
            try:
                from web.api.tasks_api import record_action as _task_record
                await _task_record(user_id, "mission")
            except Exception:
                pass
        else:
            outcome_lines.append("❌ Mission failed.")
            level_down = None
            if gamble_xp > 0:
                _, res = await LootCalculator.apply_xp_change(int(user_id), -gamble_xp, "mission_fail")
                outcome_lines.append(f"Lost {gamble_xp} XP.")
                if res and res.get("new_level", 0) < res.get("old_level", 0):
                    level_down = res
                    outcome_lines.append(f"📉 Level Down! Now level {res['new_level']}.")
            result = {"success": False, "outcome": "\n".join(outcome_lines), "xp": -gamble_xp, "level_up": None, "level_down": level_down}

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

        # Load locations data
        loc_path = _os.path.join(project_root, "Systems", "Pets", "Logic", "locations_play.json")
        with open(loc_path) as f:
            loc_data = _json.load(f)

        loc_info       = loc_data.get("locations", {}).get(location, {})
        place_specials = loc_info.get("Special", {})
        pet_e1         = (pet.get("element") or "basic").lower()
        pet_e2         = (pet.get("element2") or "").lower()
        level          = int(pet.get("level", 1))

        xp, key_names = LootCalculator.calculate_play_loot(pet_e1, pet_e2, place_specials, level)

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

        result = {
            "success": True,
            "outcome": "\n".join(outcome_lines),
            "xp": xp,
            "level_up": level_up,
            "pet": _enrich_pet(await user_data_manager.get_pet_data_async(user_id))
        }
        try:
            from web.api.tasks_api import record_action as _task_record
            await _task_record(user_id, "play")
        except Exception:
            pass
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

        stage = stages[0]
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

        # Stat check
        stat_map = {1: ("ATT","DEF"), 2: ("INT","DEX"), 3: ("HAP","ENE")}
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
                    if choice_num == 1:
                        loot_amt    = base_amt * 2
                        outcome_msg = "⚔️ You overpowered the mimic and found double loot!"
                    else:
                        loot_amt    = 0
                        outcome_msg = "🪤 It was a mimic! You barely escaped."
                else:
                    double_choice = stage.get("double_loot_choice", -1)
                    loot_amt      = base_amt * 2 if choice_num == double_choice else base_amt
                    outcome_msg   = f"📦 You opened the chest and found {'double ' if choice_num == double_choice else ''}loot!"

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
    return JSONResponse(content={"ok": True})


def _generate_quest_loot_web(amount: int, difficulty: str) -> list:
    import random as _random
    from Systems.Pets.Logic.pet_brain import LootCalculator
    loot = []
    types = ["Material","Gem","Monster","Potion","Hat"]
    for _ in range(amount):
        t    = _random.choice(types)
        item = None
        if t == "Material": item = LootCalculator.get_material_loot_item(difficulty, bypass_chance=True)
        elif t == "Gem":    item = LootCalculator.get_gem_loot_item(difficulty, bypass_chance=True)
        elif t == "Monster":item = LootCalculator.get_monster_loot_item(difficulty, bypass_chance=True)
        elif t == "Potion": item = LootCalculator.get_potion_loot(difficulty, bypass_chance=True)
        elif t == "Hat":    item = LootCalculator.get_hat_loot_item(difficulty, bypass_chance=True)
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

    # Task tracking
    if success:
        try:
            from web.api.tasks_api import record_action as _task_record
            await _task_record(user_id, "quest")
        except Exception:
            pass

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

        if chest_type == "chest4" and selected_type not in ("Material", "Gem", "Monster", "Potion", "Hat"):
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

        # Re-fetch pet to get updated inventory/XP for the response
        refreshed = _enrich_pet(await user_data_manager.get_pet_data_async(user_id))

        logger.info(f"Loot opened for user {user_id}: {chest_type} x{amount} -> {[i.get('name') for i in awarded_items]}")

        try:
            from web.api.tasks_api import record_action as _task_record
            for _ in range(amount):
                await _task_record(user_id, "loot")
        except Exception:
            pass

        return JSONResponse(content={
            "success": True,
            "chest":   chest_type,
            "amount":  amount,
            "items":   awarded_items,
            "messages": messages,
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
        if chest_type == "chest4" and selected_type not in ("Material", "Gem", "Monster", "Potion", "Hat"):
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
            bonus = LootCalculator.get_item_by_rarity(["Uncommon", "Rare", "Epic", "Mythic"])
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

        return JSONResponse(content={
            "success":  True,
            "chest":    chest_type,
            "items":    awarded_items,
            "messages": messages,
            "pet":      refreshed,
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

        from Systems.Pets.Logic.pet_brain import LootCalculator

        # Route to the correct equip_items parameter based on type
        type_map = {
            "Material": dict(material_names=item_name),
            "Gem":      dict(gem_names=item_name),
            "Monster":  dict(monster_names=item_name),
            "Hat":      dict(hat_name=item_name),
        }
        if item_type not in type_map:
            raise HTTPException(status_code=400, detail=f"Cannot equip item type: {item_type}")

        success, msg = await LootCalculator.equip_items(
            user_id, user.get("username", "Unknown"), **type_map[item_type]
        )

        refreshed = _enrich_pet(await user_data_manager.get_pet_data_async(user_id))
        if success:
            try:
                from web.api.tasks_api import record_action as _task_record
                await _task_record(user_id, "equip")
            except Exception:
                pass
        return JSONResponse(content={"success": success, "message": msg, "pet": refreshed})

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
                # Stop early if we run out or hit an error
                if not success:
                    # Failed on first use — return the error
                    refreshed = _enrich_pet(await user_data_manager.get_pet_data_async(user_id))
                    return JSONResponse(content={"success": False, "message": msg, "pet": refreshed})
                break

        refreshed = _enrich_pet(await user_data_manager.get_pet_data_async(user_id))
        # Merge messages: combine all stat changes into one summary
        combined = "; ".join(messages) if messages else "Used!"
        if success:
            try:
                from web.api.tasks_api import record_action as _task_record
                for _ in range(len(messages)):
                    await _task_record(user_id, "potion")
            except Exception:
                pass
        return JSONResponse(content={"success": success, "message": combined, "pet": refreshed})

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
        if slot not in ("Material", "Gems", "Monsters", "Hat"):
            raise HTTPException(status_code=400, detail=f"Invalid slot: {slot}")

        from Systems.Pets.Logic.pet_brain import LootCalculator
        success, msg = await LootCalculator.unequip_items(user_id, slot)
        refreshed = _enrich_pet(await user_data_manager.get_pet_data_async(user_id))
        return JSONResponse(content={"success": success, "message": msg, "pet": refreshed})

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

        pet = await user_data_manager.get_pet_data_async(user_id)
        if not pet:
            raise HTTPException(status_code=404, detail="No pet found.")

        inventory = pet.get("inventory", [])
        pet_level = int(pet.get("level", 1))

        # Find the item in inventory
        idx = next((i for i, it in enumerate(inventory)
                    if isinstance(it, dict) and it.get("name", "").lower() == item_name.lower()), None)
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
        from Systems.Pets.pets_system import add_experience
        _, lvl_data = await add_experience(int(user_id), total_xp, "consume")

        refreshed = _enrich_pet(await user_data_manager.get_pet_data_async(user_id))
        leveled_up = lvl_data and lvl_data.get("new_level", 0) > lvl_data.get("old_level", 0)
        mult_str = f" (×{equip_mult:.0f})" if equip_mult > 1.0 else ""
        msg = f"Consumed {count}x {item_name} ({rarity}) for +{total_xp:,} XP{mult_str}"
        if leveled_up:
            msg += f" · Level Up! Now Lv.{lvl_data['new_level']} 🎉"
        try:
            from web.api.tasks_api import record_action as _task_record
            for _ in range(count):
                await _task_record(user_id, "consume")
        except Exception:
            pass
        return JSONResponse(content={"success": True, "message": msg, "xp_gained": total_xp,
                                     "equip_multiplier": equip_mult,
                                     "level_up": lvl_data if leveled_up else None, "pet": refreshed})

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

        # Add 1 to recipient
        gift_item_obj = {**item, "count": 1}
        from Systems.Pets.Logic.pet_brain import LootCalculator
        await LootCalculator.add_item_to_inventory(int(recipient_id), gift_item_obj, recipient_pet)

        logger.info(f"Gift: {sender_id} → {recipient_id}: {item_name}")

        # Task tracking
        try:
            from web.api.tasks_api import record_action as _task_record
            await _task_record(sender_id, "gift")
        except Exception:
            pass

        return JSONResponse(content={
            "success": True,
            "gifted":  item_name,
            "to":      recipient_pet.get("name", "Unknown"),
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
            e_hp   = max(50, int((hp_raw.get("HAP", 50) + hp_raw.get("ENE", 50)) * 3))
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
                _info = _load_json(os.path.join(project_root, "Systems", "Pets", "Logic", "info.json"))
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

        action_labels = DamageCalculator.get_action_labels(p_type, p_elem, p_spec)

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
                "charge": 1.0,
                "last_action": None,
                "equipment": _equip_items(pet),
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

        p_action = (data.get("action") or "attack").lower()
        if p_action not in ("attack", "defend", "charge"):
            p_action = "attack"

        # Unpack state sent from client
        ps = data["player"]
        es = data["enemy"]
        turn_num = int(data.get("turn", 0)) + 1
        difficulty = (data.get("difficulty") or "easy").lower()

        p_atk   = int(ps["attack"])
        p_def   = int(ps["defense"])
        p_type  = str(ps.get("type", "land"))
        p_elem  = str(ps.get("element", "basic"))
        p_elem2 = str(ps.get("element2") or "") or None
        p_spec  = str(ps.get("species", ""))
        p_hp    = int(ps["max_hp"])
        cur_p_hp = int(ps["cur_hp"])
        p_charge = float(ps.get("charge", 1.0))
        p_last   = ps.get("last_action")

        e_atk   = int(es["attack"])
        e_def   = int(es["defense"])
        e_type  = str(es.get("type", "land"))
        e_elem  = str(es.get("element", "basic"))
        e_hp    = int(es["max_hp"])
        cur_e_hp = int(es["cur_hp"])
        e_charge = float(es.get("charge", 1.0))
        e_last   = es.get("last_action")
        enemy_name = str(es.get("name", "Enemy"))
        pet_name   = str(ps.get("name", "Your Pet"))

        # NPC decides
        npc_brain = NPCBrain()
        monster_state = {
            "hp": cur_e_hp, "max_hp": e_hp, "prev_hp": cur_e_hp,
            "charge_multiplier": e_charge, "last_action": e_last,
            "attack_stat": float(e_atk), "defense_stat": float(e_def),
            "seed": turn_num
        }
        player_state = [{"alive": cur_p_hp > 0, "hp": cur_p_hp, "max_hp": p_hp, "charging": p_action == "charge"}]
        e_action = npc_brain.decide_action(monster_state, player_state).get("action", "attack")

        # Charge accumulation
        if p_action == "charge":
            p_charge = DamageCalculator.get_next_charge_multiplier(p_charge)
        if e_action == "charge":
            e_charge = DamageCalculator.get_next_charge_multiplier(e_charge)

        # Resolve combat
        # p_result = player attacking enemy (player is attacker, enemy is target)
        # e_result = enemy attacking player (enemy is attacker, player is target)
        p_result = DamageCalculator.calculate_battle_action(
            attacker_attack=p_atk, target_defense=e_def,
            charge_multiplier=p_charge if p_action in ("attack", "defend") else 1.0,
            target_charge_multiplier=e_charge if e_action == "defend" else 1.0,
            attacker_action_type=p_action, target_action_type=e_action,
            attacker_type=p_type, attacker_element=p_elem, attacker_element2=p_elem2,
            defender_type=e_type, defender_element=e_elem,
            attacker_species=p_spec
        )
        e_result = DamageCalculator.calculate_battle_action(
            attacker_attack=e_atk, target_defense=p_def,
            charge_multiplier=e_charge if e_action in ("attack", "defend") else 1.0,
            target_charge_multiplier=p_charge if p_action == "defend" else 1.0,
            attacker_action_type=e_action, target_action_type=p_action,
            attacker_type=e_type, attacker_element=e_elem,
            defender_type=p_type, defender_element=p_elem, defender_element2=p_elem2,
            defender_species=p_spec
        )

        p_dmg_dealt = p_result["final_damage"]
        e_dmg_dealt = e_result["final_damage"]
        p_parry     = p_result["parry_damage"]   # player defended → parry back at enemy
        e_parry     = e_result["parry_damage"]   # enemy defended → parry back at player

        # Both defend: no damage, no parry — stalemate
        if p_action == "defend" and e_action == "defend":
            p_dmg_dealt = 0
            e_dmg_dealt = 0
            p_parry     = 0
            e_parry     = 0

        cur_e_hp = max(0, cur_e_hp - p_dmg_dealt - e_parry)
        cur_p_hp = max(0, cur_p_hp - e_dmg_dealt - p_parry)

        # Reset charge after it's spent (attack or defend consumes it)
        if p_action in ("attack", "defend"): p_charge = 1.0
        if e_action in ("attack", "defend"): e_charge = 1.0
        action_labels = data.get("action_labels", {})
        p_action_label = action_labels.get(p_action, p_action.title())

        # ── Structured combat data for rich frontend rendering ────────────────
        p_charge_used = float(data.get("player", {}).get("charge", 1.0))  # charge BEFORE reset
        e_charge_used = float(data.get("enemy", {}).get("charge", 1.0))

        combat = {
            # Player → Enemy
            "p_action": p_action,
            "p_action_label": p_action_label,
            "p_dmg": p_dmg_dealt,
            "p_parry": p_parry,
            "p_charge_mult": p_charge_used if p_action == "attack" else (p_charge if p_action == "charge" else (p_charge_used if p_action == "defend" else 1.0)),
            "p_attack_roll": p_result.get("attack_roll"),
            "p_attack_result": p_result.get("attack_result", ""),
            # Player's own defense roll is in e_result (enemy attacks player, player defends)
            "p_defense_roll": e_result.get("defense_roll") if p_action == "defend" else None,
            "p_defense_result": e_result.get("defense_result", "") if p_action == "defend" else "",
            "p_final_attack": p_result.get("final_attack", 0),
            "p_final_defense": e_result.get("final_defense", 0),
            "p_type_elem_mult": round(p_result.get("type_element_bonus_mult_attack", 1.0), 2),
            # Enemy → Player
            "e_action": e_action,
            "e_dmg": e_dmg_dealt,
            "e_parry": e_parry,
            "e_charge_mult": e_charge_used if e_action == "attack" else (e_charge if e_action == "charge" else (e_charge_used if e_action == "defend" else 1.0)),
            "e_attack_roll": e_result.get("attack_roll"),
            "e_attack_result": e_result.get("attack_result", ""),
            # Enemy's own defense roll is in p_result (player attacks enemy, enemy defends)
            "e_defense_roll": p_result.get("defense_roll") if e_action == "defend" else None,
            "e_defense_result": p_result.get("defense_result", "") if e_action == "defend" else "",
            "e_final_attack": e_result.get("final_attack", 0),
            "e_final_defense": p_result.get("final_defense", 0),
            "e_type_elem_mult": round(e_result.get("type_element_bonus_mult_attack", 1.0), 2),
            "p_charge_after": p_charge,
            "e_charge_after": e_charge,
            "both_defend": p_action == "defend" and e_action == "defend",
        }

        lines = []
        if p_action == "charge":
            lines.append(f"⚡ {pet_name} charges up! (x{p_charge:.0f})")
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

        # If battle is over, apply XP/loot
        loot_result = None
        level_change = None
        refreshed_pet = None
        if over:
            pet = await user_data_manager.get_pet_data_async(user_id)
            if pet:
                old_level = int(pet.get("level", 1))
                loot_result = await LootCalculator.calculate_loot(
                    user_id=int(user_id), pet_data=pet, source="battle",
                    difficulty=difficulty, winner_level=old_level, is_winner=player_won
                )
                await user_data_manager.update_pet_battle_stats(
                    user_id, "npc",
                    wins=1 if player_won else 0, losses=0 if player_won else 1,
                    xp_earned=loot_result["xp_gained"], damage_dealt=0, damage_taken=0
                )
                refreshed_pet = _enrich_pet(await user_data_manager.get_pet_data_async(user_id))
                new_level = int(refreshed_pet.get("level", 1)) if refreshed_pet else old_level
                if new_level != old_level:
                    level_change = {"old_level": old_level, "new_level": new_level, "gains": {}}
                # Task tracking
                try:
                    from web.api.tasks_api import record_action as _task_record
                    await _task_record(user_id, "battle_npc", won=player_won)
                except Exception:
                    pass

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
        })

    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"battle_npc_turn bad input: {e}")
        raise HTTPException(status_code=400, detail="Invalid battle state.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"battle_npc_turn error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Battle turn failed.")


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
        action_labels = DamageCalculator.get_action_labels(p_type, p_elem, p_spec)

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
            source="battle",
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
        level_change = None
        for msg in loot_result.get("messages", []):
            pass  # messages already contain level info
        # Re-fetch to get updated pet
        refreshed = _enrich_pet(await user_data_manager.get_pet_data_async(user_id))
        old_level = int(pet.get("level", 1))
        new_level = int(refreshed.get("level", 1)) if refreshed else old_level
        if new_level != old_level:
            level_change = {"old_level": old_level, "new_level": new_level, "gains": {}}

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
    action_labels = DamageCalculator.get_action_labels(p_type, p_elem, p_spec)

    for turn_num in range(1, MAX_TURNS + 1):
        if cur_p_hp <= 0 or cur_e_hp <= 0:
            break
        p_action = "attack"
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
        )
        e_result = DamageCalculator.calculate_battle_action(
            attacker_attack=e_atk, target_defense=p_def,
            charge_multiplier=e_charge if e_action == "attack" else 1.0,
            target_charge_multiplier=p_charge if p_action == "defend" else 1.0,
            attacker_action_type=e_action, target_action_type=p_action,
            attacker_type=e_type, attacker_element=e_elem,
            defender_type=p_type, defender_element=p_elem, defender_element2=p_elem2, defender_species=p_spec,
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
        turn_lines = []
        if p_dmg_dealt > 0:
            mult = p_result.get("type_element_bonus_mult_attack", 1.0)
            bonus = " 🔥" if mult > 1.0 else (" 💨" if mult < 1.0 else "")
            turn_lines.append(f"⚔️ {pet['name']} {p_action_label} → {p_dmg_dealt} dmg{bonus}")
        elif p_action == "defend":
            turn_lines.append(f"🛡️ {pet['name']} defends" + (f" — parries {e_parry}!" if e_parry else ""))
        elif p_action == "charge":
            turn_lines.append(f"⚡ {pet['name']} charges (x{p_charge:.0f})")
        if e_dmg_dealt > 0:
            turn_lines.append(f"💥 {enemy_name} attacks → {e_dmg_dealt} dmg")
        elif e_action == "defend":
            turn_lines.append(f"🛡️ {enemy_name} defends" + (f" — parries {p_parry}!" if p_parry else ""))
        elif e_action == "charge":
            turn_lines.append(f"⚡ {enemy_name} charges (x{e_charge:.0f})")

        turns.append({
            "turn": turn_num, "lines": turn_lines,
            "player_hp": cur_p_hp, "player_max_hp": p_hp,
            "enemy_hp": cur_e_hp,  "enemy_max_hp": e_hp,
            "player_action": p_action, "enemy_action": e_action,
        })
        if cur_p_hp <= 0 or cur_e_hp <= 0:
            break

    player_won = cur_p_hp > 0 and cur_e_hp <= 0
    loot_result = await LootCalculator.calculate_loot(
        user_id=int(user_id), pet_data=pet, source="battle",
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
    level_change = {"old_level": old_level, "new_level": new_level} if new_level != old_level else None

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
    """Simple PvP simulation between two users' pets."""
    import random as _random
    from Systems.Pets.Logic.pet_brain import StatsCalculator, DamageCalculator, LootCalculator

    pet_a = await user_data_manager.get_pet_data_async(user_id)
    pet_b = await user_data_manager.get_pet_data_async(challenger_id)
    if not pet_a or not pet_b:
        raise ValueError("One or both users have no pet")

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

        r_a = DamageCalculator.calculate_battle_action(
            attacker_attack=sa["atk"], target_defense=sb["def"],
            charge_multiplier=charge_a if act_a == "attack" else 1.0,
            target_charge_multiplier=charge_b if act_b == "defend" else 1.0,
            attacker_action_type=act_a, target_action_type=act_b,
            attacker_type=sa["type"], attacker_element=sa["elem"], attacker_element2=sa["elem2"],
            defender_type=sb["type"], defender_element=sb["elem"], defender_element2=sb["elem2"],
            attacker_species=sa["spec"],
        )
        r_b = DamageCalculator.calculate_battle_action(
            attacker_attack=sb["atk"], target_defense=sa["def"],
            charge_multiplier=charge_b if act_b == "attack" else 1.0,
            target_charge_multiplier=charge_a if act_a == "defend" else 1.0,
            attacker_action_type=act_b, target_action_type=act_a,
            attacker_type=sb["type"], attacker_element=sb["elem"], attacker_element2=sb["elem2"],
            defender_type=sa["type"], defender_element=sa["elem"], defender_element2=sa["elem2"],
            attacker_species=sb["spec"],
        )

        hp_b = max(0, hp_b - r_a["final_damage"] - r_b["parry_damage"])
        hp_a = max(0, hp_a - r_b["final_damage"] - r_a["parry_damage"])
        if act_a == "attack": charge_a = 1.0
        if act_b == "attack": charge_b = 1.0

        lines = []
        if r_a["final_damage"] > 0: lines.append(f"⚔️ {pet_a['name']} → {r_a['final_damage']} dmg")
        if r_b["final_damage"] > 0: lines.append(f"⚔️ {pet_b['name']} → {r_b['final_damage']} dmg")
        turns.append({"turn": turn_num, "lines": lines, "hp_a": hp_a, "hp_b": hp_b})
        log.extend(lines)
        if hp_a <= 0 or hp_b <= 0:
            break

    winner_id   = user_id if hp_a > 0 else challenger_id
    loser_id    = challenger_id if hp_a > 0 else user_id
    winner_pet  = pet_a if hp_a > 0 else pet_b
    loser_pet   = pet_b if hp_a > 0 else pet_a

    win_loot  = await LootCalculator.calculate_loot(int(winner_id), winner_pet, "pvp", "normal", int(winner_pet.get("level",1)), int(loser_pet.get("level",1)), True)
    loss_loot = await LootCalculator.calculate_loot(int(loser_id),  loser_pet,  "pvp", "normal", int(winner_pet.get("level",1)), int(loser_pet.get("level",1)), False)

    log.append(f"🏆 {winner_pet['name']} wins! +{win_loot['xp_gained']} XP")
    log.append(f"💀 {loser_pet['name']} defeated. +{loss_loot['xp_gained']} XP")

    return {
        "winner_id": winner_id, "loser_id": loser_id,
        "winner_name": winner_pet["name"], "loser_name": loser_pet["name"],
        "turns": turns, "log": log,
        "winner_xp": win_loot["xp_gained"], "loser_xp": loss_loot["xp_gained"],
    }

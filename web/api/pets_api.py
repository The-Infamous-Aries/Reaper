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

logger = logging.getLogger(__name__)

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

router = APIRouter()


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

        computed_stats = StatsCalculator.calculate_pet_stats(pet_data)
        xp_for_next_level = LootCalculator.get_next_level_xp(pet_data.get("level", 1))
        return JSONResponse(content={
            "has_pet": True,
            **pet_data,
            "computed_stats": computed_stats,
            "xp_for_next_level": xp_for_next_level,
        })
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

    try:
        pet = await user_data_manager.get_pet_data_async(user_id)
        if not pet:
            raise HTTPException(status_code=404, detail="No pet found")

        difficulty = data.get("difficulty", "Easy")
        if difficulty not in ("Easy", "Average", "Hard"):
            raise HTTPException(status_code=400, detail="Invalid difficulty")

        import random
        success_chance = {"Easy": 0.9, "Average": 0.7, "Hard": 0.5}[difficulty]
        xp_map         = {"Easy": 50,  "Average": 100, "Hard": 200}

        if random.random() < success_chance:
            xp = xp_map[difficulty]
            from Systems.Pets.pets_system import add_experience
            _, lvl_data = await add_experience(int(user_id), xp, "training")
            result = {
                "success": True,
                "outcome": f"🏋️ Training successful! Gained {xp} XP.",
                "xp": xp,
                "level_up": lvl_data if (lvl_data and lvl_data.get("new_level", 0) > lvl_data.get("old_level", 0)) else None
            }
        else:
            result = {"success": False, "outcome": "❌ Training failed — your pet got away safely.", "xp": 0, "level_up": None}

        # Return refreshed pet
        result["pet"] = await user_data_manager.get_pet_data_async(user_id)
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

        outcome_lines = []
        level_up = None

        if random.random() < success_chance:
            xp = base_xp_map[difficulty] + gamble_xp
            outcome_lines.append(f"✅ Mission successful! Gained {xp} XP.")

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
        else:
            outcome_lines.append("❌ Mission failed.")
            if gamble_xp > 0:
                _, res = await LootCalculator.apply_xp_change(int(user_id), -gamble_xp, "mission_fail")
                outcome_lines.append(f"Lost {gamble_xp} XP.")
            result = {"success": False, "outcome": "\n".join(outcome_lines), "xp": -gamble_xp, "level_up": None}

        result["pet"] = await user_data_manager.get_pet_data_async(user_id)
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

        loc_info     = loc_data.get("locations", {}).get(location, {})
        place_specials = loc_info.get("Special", {})
        pet_e1       = (pet.get("element") or "basic").lower()
        pet_e2       = (pet.get("element2") or "").lower()
        level        = int(pet.get("level", 1))

        xp_mult, key_names = LootCalculator.calculate_play_loot(pet_e1, pet_e2, place_specials)
        base_xp = 5 * level
        xp = base_xp * xp_mult

        outcome_lines = [f"🎮 {pet['name']} played at {location}!"]

        # Award keys
        for kn in key_names:
            k = {"name": kn, "type": "Key", "count": 1}
            added, msg = await LootCalculator.add_item_to_inventory(int(user_id), k, pet)
            if added and msg:
                outcome_lines.append(msg.strip())

        # Award XP
        _, lvl_data = await add_experience(int(user_id), xp, "play")
        outcome_lines.append(f"✨ Gained {xp} XP (x{xp_mult} element bonus).")
        level_up = None
        if lvl_data and lvl_data.get("new_level", 0) > lvl_data.get("old_level", 0):
            level_up = lvl_data
            outcome_lines.append(f"🎉 Level Up! Now level {lvl_data['new_level']}!")

        result = {
            "success": True,
            "outcome": "\n".join(outcome_lines),
            "xp": xp,
            "xp_mult": xp_mult,
            "level_up": level_up,
            "pet": await user_data_manager.get_pet_data_async(user_id)
        }
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

@router.post("/pets/quest/start")
async def quest_start(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

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

        stage = stages[0]
        return JSONResponse(content={
            "stage_idx":   0,
            "total_stages": len(stages),
            "stage_name":  stage["stage_name"],
            "event":       _strip_hints(stage["event"]),
            "choices":     {k: _strip_hints(v) for k, v in stage["choices"].items()},
            "done":        False,
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

    try:
        choice_num = int(data.get("choice", 1))
        import random as _random
        from Systems.Pets.Logic.pet_brain import LootCalculator
        from Systems.Pets.pets_system import add_experience

        stages    = session["stages"]
        idx       = session["stage_idx"]
        pet       = session["pet"]
        diff      = session["difficulty"]
        location  = session["location"]

        if idx >= len(stages):
            # All stages done
            return await _quest_finish(user_id, session, True)

        stage      = stages[idx]
        stage_name = stage["stage_name"]
        sub_type   = stage.get("sub_type")

        # Skip evade if hostile already defeated
        if stage_name == "Avoiding Hostile Pets" and sub_type == "evade" and session["hostile_defeated"]:
            session["stage_idx"] += 1
            idx += 1
            if idx >= len(stages):
                return await _quest_finish(user_id, session, True)
            stage      = stages[idx]
            stage_name = stage["stage_name"]
            sub_type   = stage.get("sub_type")

        stat_map = {1: ("ATT","DEF"), 2: ("INT","DEX"), 3: ("HAP","ENE")}
        stat1, stat2 = stat_map.get(choice_num, ("ATT","DEF"))
        pet_skill = (pet.get(stat1, 0) + pet.get(stat2, 0)) / 2

        diff_mult = {"Apprentice": 0.8, "Journeyman": 1.0, "Senior": 1.2}[diff]
        stage_mod = stage.get("difficulty_modifier", 1.0)
        required  = 10 * diff_mult * stage_mod
        success_rate = min(95, max(5, int((pet_skill / max(1, required)) * 50)))
        success = _random.randint(1, 100) <= success_rate

        outcome_msg = ""
        xp_gain     = 0
        loot_gained = []
        quest_failed = False

        # ── Stage-specific logic ──────────────────────────────────────────────
        if stage_name == "Entering Location":
            success = True
            outcome_msg = "You enter the area and begin your quest."

        elif stage_name == "Avoiding Hostile Pets":
            boss_name = f"{location} {session['hostile_pet']['species']}"
            skill_inf = ((pet_skill - required) / max(1, required)) * 15
            if sub_type == "scare_off":
                success_rate = min(95, max(5, 65 + skill_inf))
            else:
                success_rate = min(95, max(5, 50 + skill_inf))
            success = _random.randint(1, 100) <= success_rate

            if success:
                xp_gain = max(10, int(pet_skill * 1.5))
                outcome_msg = f"✅ You {'scared off' if sub_type=='scare_off' else 'evaded'} the {boss_name}! +{xp_gain} XP"
                if sub_type == "scare_off":
                    session["hostile_defeated"] = True
            else:
                # Simulate battle outcome (no real Discord battle on web — use stat check)
                battle_chance = min(90, max(10, int(pet_skill * 2)))
                battle_won = _random.randint(1, 100) <= battle_chance
                if battle_won:
                    xp_gain = max(15, int(pet_skill * 2))
                    outcome_msg = f"⚔️ You fought the {boss_name} and won! +{xp_gain} XP"
                    session["hostile_defeated"] = True
                else:
                    outcome_msg = f"💀 You were defeated by the {boss_name}. Quest failed."
                    quest_failed = True

        elif stage_name == "Locating a FREE to open Loot Chest":
            success_rate = min(95, max(5, int((pet_skill / max(1, required)) * 60)))
            success = _random.randint(1, 100) <= success_rate
            if not success:
                outcome_msg = "You fumbled and couldn't open the chest."
            else:
                loot_mult = {"Apprentice": 1, "Journeyman": 2, "Senior": 3}[diff]
                base_amt  = _random.randint(1, 3) * loot_mult
                if sub_type == "mimic":
                    if choice_num == 1:
                        loot_amt = base_amt * 2
                        outcome_msg = "⚔️ You overpowered the mimic and found double loot!"
                    else:
                        loot_amt = 0
                        outcome_msg = "🪤 It was a mimic! You barely escaped."
                else:
                    double_choice = stage.get("double_loot_choice", -1)
                    loot_amt = base_amt * 2 if choice_num == double_choice else base_amt
                    outcome_msg = f"📦 You opened the chest and found {'double ' if choice_num==double_choice else ''}loot!"

                if loot_amt > 0:
                    loot_gained = _generate_quest_loot_web(loot_amt, diff)
                    session["loot"].extend(loot_gained)
                    names = [f"{i.get('count',1)}x {i['name']}" for i in loot_gained]
                    outcome_msg += f" Got: {', '.join(names)}"

        else:  # Looking Around, Exiting Location, etc.
            if success:
                xp_gain = max(10, int((pet_skill - required) * 5))
                outcome_msg = f"✅ Success! +{xp_gain} XP"
            else:
                outcome_msg = "⚠️ You struggled but made it through."

        session["xp"] += xp_gain
        session["event_log"].append({
            "stage": stage_name,
            "choice": _strip_hints(stage["choices"].get(str(choice_num), "")),
            "success": success,
            "success_rate": round(success_rate, 1),
            "outcome": outcome_msg,
        })
        session["stage_idx"] += 1

        if quest_failed:
            return await _quest_finish(user_id, session, False)

        # Move to next stage
        next_idx = session["stage_idx"]
        if next_idx >= len(stages):
            return await _quest_finish(user_id, session, True)

        next_stage = stages[next_idx]
        # Skip evade if hostile defeated
        if next_stage["stage_name"] == "Avoiding Hostile Pets" and next_stage.get("sub_type") == "evade" and session["hostile_defeated"]:
            session["stage_idx"] += 1
            next_idx += 1
            if next_idx >= len(stages):
                return await _quest_finish(user_id, session, True)
            next_stage = stages[next_idx]

        return JSONResponse(content={
            "stage_idx":    next_idx,
            "total_stages": len(stages),
            "stage_name":   next_stage["stage_name"],
            "event":        _strip_hints(next_stage["event"]),
            "choices":      {k: _strip_hints(v) for k, v in next_stage["choices"].items()},
            "outcome_msg":  outcome_msg,
            "xp_so_far":    session["xp"],
            "done":         False,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"quest_choice error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _generate_quest_loot_web(amount: int, difficulty: str) -> list:
    import random as _random
    from Systems.Pets.Logic.pet_brain import LootCalculator
    loot = []
    types = ["Material","Gem","Monster","Potion","Hat"]
    for _ in range(amount):
        t = _random.choice(types)
        item = None
        if t == "Material": item = LootCalculator.get_material_loot_item(difficulty, bypass_chance=True)
        elif t == "Gem":    item = LootCalculator.get_gem_loot_item(difficulty, bypass_chance=True)
        elif t == "Monster":item = LootCalculator.get_monster_loot_item(difficulty, bypass_chance=True)
        elif t == "Potion": item = LootCalculator.get_potion_loot(difficulty, bypass_chance=True)
        elif t == "Hat":    item = LootCalculator.get_hat_loot_item(difficulty, bypass_chance=True)
        if item:
            found = next((x for x in loot if x["name"]==item["name"] and x["type"]==item["type"]), None)
            if found: found["count"] = found.get("count",1) + 1
            else:     item["count"] = 1; loot.append(item)
    return loot


async def _quest_finish(user_id: str, session: dict, success: bool):
    from Systems.Pets.Logic.pet_brain import LootCalculator
    from Systems.Pets.pets_system import add_experience

    session["done"]    = True
    session["success"] = success

    xp   = session["xp"]
    loot = session["loot"]
    pet  = session["pet"]

    # Award XP
    if xp > 0:
        await add_experience(int(user_id), xp, "quest")

    # Award loot
    keep_loot = success or (session["stage_idx"] >= 3 and loot)
    if keep_loot and loot:
        for item in loot:
            await LootCalculator.add_item_to_inventory(int(user_id), item, pet)

    refreshed = await user_data_manager.get_pet_data_async(user_id)

    loot_names = [f"{i.get('count',1)}x {i['name']}" for i in loot] if keep_loot else []

    return JSONResponse(content={
        "done":      True,
        "success":   success,
        "xp":        xp,
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

        messages = await LootCalculator.open_chest(
            int(user_id),
            chest_type,
            amount,
            selected_type
        )

        # open_chest returns a list of strings — first entry is an error if it starts with "Not enough" or "Invalid"
        if messages and (messages[0].startswith("Not enough") or messages[0].startswith("Invalid") or messages[0] == "You don't have a pet!"):
            raise HTTPException(status_code=400, detail=messages[0])

        # Re-fetch pet to get updated inventory
        refreshed = await user_data_manager.get_pet_data_async(user_id)

        # Build item list from the refreshed inventory diff — easier: just parse the messages
        # messages are like "🎁 Looted <emoji> **ItemName** x1 (stats)!"
        # We'll also return the raw messages and the full refreshed inventory
        items_awarded = []
        if refreshed:
            inv = refreshed.get("inventory", [])
            # Return items that match what was just opened — use messages to extract names
            import re as _re
            for msg in messages:
                m = _re.search(r'\*\*(.+?)\*\*', msg)
                if m:
                    name = m.group(1)
                    item = next((i for i in inv if i.get("name") == name), None)
                    if item:
                        items_awarded.append(item)
                    else:
                        items_awarded.append({"name": name, "type": "Item", "rarity": "Common"})

        logger.info(f"Loot opened for user {user_id}: {chest_type} x{amount} -> {[i.get('name') for i in items_awarded]}")

        return JSONResponse(content={
            "success": True,
            "chest":   chest_type,
            "amount":  amount,
            "items":   items_awarded,
            "messages": messages,
            "pet":     refreshed,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"loot_open error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to open chest.")


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

        refreshed = await user_data_manager.get_pet_data_async(user_id)
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

        from Systems.Pets.Logic.pet_brain import LootCalculator

        success, msg = await LootCalculator.use_potion(int(user_id), potion_name)
        refreshed = await user_data_manager.get_pet_data_async(user_id)
        return JSONResponse(content={"success": success, "message": msg, "pet": refreshed})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"use_potion error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Potion use failed.")

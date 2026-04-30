"""
Pet Connector World API
Returns all users who have pets for the Pet Connector card grid.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from Systems.Functions.user_data_manager import user_data_manager
from Systems.Functions.pets_db import pets_db
from Systems.Pets.Logic.pet_brain import StatsCalculator, LootCalculator

logger = logging.getLogger(__name__)
router = APIRouter()


class RelationshipRequest(BaseModel):
    target_user_id: str
    relationship_type: str  # 'best_friend', 'friend', 'foe', 'enemy'


class GiftRequest(BaseModel):
    target_user_id: str
    item_name: str
    quantity: int = 1


def _enrich_pet(pet: dict) -> dict:
    if not pet:
        return pet
    try:
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
    except Exception:
        return pet


def _current_user_id(request: Request) -> str | None:
    """Extract the logged-in Discord user ID from the session (handles both session shapes)."""
    # Primary shape used by pets_api and auth: {"discord_user": {"id": "..."}}
    discord_user = request.session.get("discord_user")
    if discord_user and isinstance(discord_user, dict):
        uid = discord_user.get("id")
        if uid:
            return str(uid)
    # Fallback shape (legacy): {"user_id": "..."}
    uid = request.session.get("user_id")
    if uid:
        return str(uid)
    return None


@router.get("/world/pets")
async def world_pets(request: Request):
    """
    Return all users who have pets for the Pet Connector card grid.
    Each entry includes enriched pet data, username, Discord avatar URL, and relationship info.
    """
    try:
        current_user_id = _current_user_id(request)

        # Load all pet data in one DB call (no lock held during subsequent queries)
        all_pets: Dict[str, Dict[str, Any]] = await pets_db.get_all_pet_data()

        if not all_pets:
            return JSONResponse({"users": []})

        # Batch-load all usernames, display names, AND avatars in one query
        import aiosqlite
        usernames: Dict[str, str] = {}
        display_names: Dict[str, str] = {}
        db_avatars: Dict[str, str] = {}
        try:
            async with aiosqlite.connect(pets_db.db_path) as db:
                # Ensure optional columns exist
                for col in ("avatar TEXT", "global_name TEXT"):
                    try:
                        await db.execute(f"ALTER TABLE users ADD COLUMN {col}")
                        await db.commit()
                    except Exception:
                        pass  # column already exists
                try:
                    async with db.execute("SELECT user_id, username, avatar, global_name FROM users") as cur:
                        for row in await cur.fetchall():
                            uid_str = str(row[0]) if row[0] else None
                            if not uid_str:
                                continue
                            if row[1]:
                                usernames[uid_str] = row[1]
                            if row[2]:
                                db_avatars[uid_str] = row[2]
                            if row[3]:
                                display_names[uid_str] = row[3]
                except Exception as e:
                    logger.warning(f"world_pets: could not read users table: {e}")
        except Exception as e:
            logger.warning(f"world_pets: could not batch-load usernames: {e}")

        # Try to fill in missing avatar/display-name from the bot's Discord cache
        try:
            from Systems.Functions.web_server import get_bot_instance
            bot = get_bot_instance()
        except Exception:
            bot = None

        # Get current user's relationships if logged in
        user_relationships: Dict[str, str] = {}
        if current_user_id:
            try:
                user_relationships = await pets_db.get_user_relationships(current_user_id)
            except Exception:
                pass

        result: List[Dict[str, Any]] = []

        for uid, pet_raw in all_pets.items():
            if not pet_raw or not uid:
                continue

            uid_str = str(uid)
            pet = _enrich_pet(dict(pet_raw))

            # Build Discord avatar URL — prefer pet-stored hash, then users table, then bot cache, then default
            avatar_hash = (
                pet.get("discord_avatar") or
                pet.get("avatar_hash") or
                db_avatars.get(uid_str) or
                ""
            )

            # Display name: prefer global_name (Discord display name), fall back to username
            display_name = display_names.get(uid_str, "")
            username = display_name or usernames.get(uid_str, "")

            # If we're still missing avatar or display name, try fresh sync then bot cache
            if bot and (not avatar_hash or not username or username == "Unknown"):
                try:
                    # First try to sync fresh data from Discord
                    from Systems.Functions.discord_user_sync import sync_user_from_bot
                    fresh_data = await sync_user_from_bot(uid_str, bot)
                    if fresh_data:
                        if not avatar_hash:
                            avatar_hash = fresh_data.get('avatar') or ""
                        if not username or username == "Unknown":
                            username = fresh_data.get('global_name') or fresh_data.get('username') or username
                except Exception as e:
                    logger.warning(f"Failed to sync user data for {uid_str}: {e}")
                
                # Fallback to bot's in-memory cache
                if not avatar_hash or not username or username == "Unknown":
                    try:
                        discord_user = bot.get_user(int(uid_str))
                        if discord_user:
                            if not avatar_hash and discord_user.avatar:
                                avatar_hash = discord_user.avatar.key
                            if not username or username == "Unknown":
                                username = getattr(discord_user, "global_name", None) or discord_user.name or "Unknown"
                            elif not display_name:
                                # Prefer global_name over stored username
                                gn = getattr(discord_user, "global_name", None)
                                if gn:
                                    username = gn
                    except Exception:
                        pass

            if not username:
                username = "Unknown"

            if avatar_hash:
                from Systems.Functions.discord_utils import get_discord_avatar_url
                avatar_url = get_discord_avatar_url(uid_str, avatar_hash, size=64)
            else:
                from Systems.Functions.discord_utils import get_discord_avatar_url
                avatar_url = get_discord_avatar_url(uid_str, None, size=64)

            # Relationship info (only for other users)
            relationship_to_user = user_relationships.get(str(uid))
            mutual_relationship = None
            if current_user_id and str(uid) != current_user_id:
                try:
                    u2t, t2u = await pets_db.get_mutual_relationship(current_user_id, str(uid))
                    mutual_relationship = {"user_to_target": u2t, "target_to_user": t2u}
                except Exception:
                    pass

            result.append({
                "user_id":            str(uid),
                "username":           username,
                "avatar_url":         avatar_url,
                "pet":                pet,
                "relationship":       relationship_to_user,
                "mutual_relationship": mutual_relationship,
                "is_current_user":    str(uid) == current_user_id,
            })

        return JSONResponse({"users": result})

    except Exception as e:
        logger.error(f"world_pets error: {e}", exc_info=True)
        return JSONResponse({"users": []})


@router.get("/world/debug-pet/{user_id}")
async def debug_pet(request: Request, user_id: str):
    """Debug: return raw pet data for a user (shows exactly what's in the DB)."""
    pet_raw = await pets_db.get_pet_data(user_id)
    if not pet_raw:
        return JSONResponse({"error": "no pet found"})
    pet = _enrich_pet(dict(pet_raw))
    return JSONResponse({
        "raw_ATT": pet_raw.get("ATT"),
        "raw_DEF": pet_raw.get("DEF"),
        "raw_INT": pet_raw.get("INT"),
        "raw_DEX": pet_raw.get("DEX"),
        "raw_HAP": pet_raw.get("HAP"),
        "raw_ENE": pet_raw.get("ENE"),
        "discord_avatar": pet_raw.get("discord_avatar"),
        "computed_stats": pet.get("computed_stats"),
        "all_keys": sorted(pet_raw.keys()),
    })


@router.get("/world/my-relationships")
async def my_relationships(request: Request):
    """Return the current user's outgoing and incoming relationships."""
    current_user_id = _current_user_id(request)
    if not current_user_id:
        return JSONResponse({"relationships": [], "incoming_relationships": []})

    try:
        import aiosqlite

        order = {"best_friend": 0, "friend": 1, "foe": 2, "enemy": 3}

        # ── Outgoing: relationships this user has set ──────────────────────────
        out_rows = []
        async with aiosqlite.connect(pets_db.db_path) as db:
            async with db.execute(
                "SELECT target_user_id, relationship_type FROM user_relationships WHERE user_id=?",
                (current_user_id,)
            ) as cur:
                out_rows = await cur.fetchall()

        # ── Incoming: relationships others have set pointing at this user ──────
        in_rows = []
        async with aiosqlite.connect(pets_db.db_path) as db:
            async with db.execute(
                "SELECT user_id, relationship_type FROM user_relationships WHERE target_user_id=?",
                (current_user_id,)
            ) as cur:
                in_rows = await cur.fetchall()

        # Batch-load all needed usernames in one query
        all_ids = list({r[0] for r in out_rows} | {r[0] for r in in_rows})
        usernames: dict = {}
        if all_ids:
            placeholders = ",".join("?" * len(all_ids))
            async with aiosqlite.connect(pets_db.db_path) as db:
                async with db.execute(
                    f"SELECT user_id, username FROM users WHERE user_id IN ({placeholders})",
                    all_ids
                ) as cur:
                    for row in await cur.fetchall():
                        usernames[str(row[0])] = row[1] or "Unknown"

        # Build outgoing result with mutual info (what the target set back for us)
        out_result = []
        for target_id, rel_type in out_rows:
            mutual_type = None
            try:
                _, t2u = await pets_db.get_mutual_relationship(current_user_id, str(target_id))
                mutual_type = t2u
            except Exception:
                pass
            out_result.append({
                "user_id":     str(target_id),
                "username":    usernames.get(str(target_id), "Unknown"),
                "type":        rel_type,
                "mutual_type": mutual_type,
            })
        out_result.sort(key=lambda x: (order.get(x["type"], 9), x["username"].lower()))

        # Build incoming result with mutual info (what we set for them)
        in_result = []
        for source_id, rel_type in in_rows:
            mutual_type = None
            try:
                u2t, _ = await pets_db.get_mutual_relationship(current_user_id, str(source_id))
                mutual_type = u2t
            except Exception:
                pass
            in_result.append({
                "user_id":     str(source_id),
                "username":    usernames.get(str(source_id), "Unknown"),
                "type":        rel_type,
                "mutual_type": mutual_type,
            })
        in_result.sort(key=lambda x: (order.get(x["type"], 9), x["username"].lower()))

        return JSONResponse({"relationships": out_result, "incoming_relationships": in_result})

    except Exception as e:
        logger.error(f"my_relationships error: {e}", exc_info=True)
        return JSONResponse({"relationships": [], "incoming_relationships": []})


@router.post("/world/relationship")
async def set_relationship(request: Request, data: RelationshipRequest):
    """Set relationship with another user"""
    try:
        current_user_id = _current_user_id(request)
        if not current_user_id:
            raise HTTPException(status_code=401, detail="Not logged in")
        
        if current_user_id == data.target_user_id:
            raise HTTPException(status_code=400, detail="Cannot set relationship with yourself")
        
        if data.relationship_type not in ['best_friend', 'friend', 'foe', 'enemy']:
            raise HTTPException(status_code=400, detail="Invalid relationship type")
        
        # Check if target user exists
        target_pet = await pets_db.get_pet_data(data.target_user_id)
        if not target_pet:
            raise HTTPException(status_code=404, detail="Target user not found")
        
        success = await pets_db.set_user_relationship(current_user_id, data.target_user_id, data.relationship_type)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to set relationship")
        
        return JSONResponse({"success": True, "message": f"Relationship set to {data.relationship_type}"})
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"set_relationship error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/world/relationship/{target_user_id}")
async def remove_relationship(request: Request, target_user_id: str):
    """Remove relationship with another user"""
    try:
        current_user_id = _current_user_id(request)
        if not current_user_id:
            raise HTTPException(status_code=401, detail="Not logged in")
        
        success = await pets_db.remove_user_relationship(current_user_id, target_user_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to remove relationship")
        
        return JSONResponse({"success": True, "message": "Relationship removed"})
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"remove_relationship error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/world/gift")
async def gift_item(request: Request, data: GiftRequest):
    """Gift an item from your pet's inventory to another user"""
    try:
        current_user_id = _current_user_id(request)
        if not current_user_id:
            raise HTTPException(status_code=401, detail="Not logged in")

        if current_user_id == data.target_user_id:
            raise HTTPException(status_code=400, detail="Cannot gift to yourself")

        qty = max(1, int(data.quantity or 1))

        # Get current user's pet
        current_pet = await pets_db.get_pet_data(current_user_id)
        if not current_pet:
            raise HTTPException(status_code=404, detail="You don't have a pet")

        # Get target user's pet
        target_pet = await pets_db.get_pet_data(data.target_user_id)
        if not target_pet:
            raise HTTPException(status_code=404, detail="Target user doesn't have a pet")

        # Find item in sender's inventory (uses "count" field)
        inventory = current_pet.get("inventory", [])
        item_idx = next(
            (i for i, it in enumerate(inventory)
             if it.get("name", "").lower() == data.item_name.lower()),
            None,
        )
        if item_idx is None:
            raise HTTPException(status_code=404, detail=f"Item '{data.item_name}' not found in your inventory")

        item = inventory[item_idx]
        available = int(item.get("count", 1))
        if available < qty:
            raise HTTPException(status_code=400, detail=f"Not enough {data.item_name} (have {available}, want {qty})")

        # Snapshot item template before modifying inventory
        gift_item_data = {**item, "count": qty}

        # Deduct from sender
        if available == qty:
            inventory.pop(item_idx)
        else:
            inventory[item_idx] = {**item, "count": available - qty}
        current_pet["inventory"] = inventory
        await pets_db.save_pet_data(current_user_id, current_pet)

        # Add to recipient via LootCalculator so stacking/limits are respected
        from Systems.Pets.Logic.pet_brain import LootCalculator
        await LootCalculator.add_item_to_inventory(int(data.target_user_id), gift_item_data, target_pet)

        logger.info(f"Gift: {current_user_id} → {data.target_user_id}: {qty}x {data.item_name}")

        # Task tracking — fire once per gift action (not per item count)
        try:
            from web.api.tasks_api import record_action as _task_record
            await _task_record(current_user_id, "gift")
        except Exception as exc:
            logger.warning(f"gift task tracking failed: {exc}")

        return JSONResponse({
            "success": True,
            "message": f"Gifted {qty}x {data.item_name} successfully",
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"gift_item error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

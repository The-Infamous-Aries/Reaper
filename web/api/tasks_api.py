"""
Tasks API — per-user daily tasks with progress tracking, rewards, and DM notifications.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse

from Systems.Functions.tasks_db import (
    COMPLETION_COOLDOWN_HOURS,
    DISMISS_COOLDOWN_HOURS,
    MONTHLY_SLOTS,
    WEEKLY_SLOTS,
    tasks_db,
)
from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.event_bus import EventQueue
from Systems.Pets.Logic.pet_components import AnimationComponent
from web.api.pets.gpp_helpers import _invalidate_stats_cache

logger = logging.getLogger("tasks_api")
router = APIRouter()


def _hours_to_seconds(hours: int) -> int:
    return hours * 3600


def _apply_cooldown_seconds(slots: list[Dict[str, Any]], now: float) -> None:
    for slot in slots:
        if slot.get("on_cooldown"):
            slot["seconds_remaining"] = max(0, int(slot.get("cooldown_until", 0) - now))
        else:
            slot["seconds_remaining"] = 0


def _reward_animation_items(reward: Dict[str, Any], rarity: str) -> list[Dict[str, str]]:
    reward_items = reward.get("items", []) if reward.get("type") == "bundle" else [reward]
    return [
        {"name": str(item.get("item", item.get("name", "Reward"))), "rarity": rarity}
        for item in reward_items
    ]


def _get_bot():
    try:
        from Systems.Functions.web_server import get_bot_instance
        return get_bot_instance()
    except Exception:
        return None


async def _send_dm(user_id: str, content: str):
    """Send a DM to a user via the Discord bot. Silently fails if unavailable."""
    try:
        bot = _get_bot()
        if not bot:
            return
        user = bot.get_user(int(user_id))
        if user is None:
            user = await bot.fetch_user(int(user_id))
        if user:
            await user.send(content)
    except Exception as e:
        logger.debug(f"DM to {user_id} failed: {e}")


async def _notify_slot_refresh(user_id: str, slot: int):
    """Send DM notification when a task slot refreshes, respecting user prefs."""
    try:
        prefs = await tasks_db.get_dm_prefs(user_id)
        if not prefs.get("dm_enabled"):
            return
        mode = prefs.get("dm_mode", "all")
        if mode == "each":
            await _send_dm(user_id, f"🗡️ **Task Refreshed!** Slot {slot} has a new task waiting for you.")
        elif mode == "all":
            # Check if ALL regular slots (1-6) are now refreshed
            slots = await tasks_db.get_slots(user_id)
            regular_slots = [s for s in slots if s.get("slot", 0) > 0]
            all_ready = all(
                not s.get("on_cooldown") and s.get("task") and not s["task"].get("completed")
                for s in regular_slots
            )
            if all_ready:
                await _send_dm(user_id, "🗡️ **All Tasks Refreshed!** All 6 of your task slots have new tasks ready.")
    except Exception as e:
        logger.debug(f"_notify_slot_refresh error: {e}")


# ── Endpoints ─────────────────────────────────────────────────────────────────

async def ensure_all_pet_owners_have_tasks():
    """Ensure all users with pets have tasks generated"""
    try:
        # Get all pet owners from the dedicated pets database
        from Systems.Functions.pets_db import pets_db
        
        all_pets = await pets_db.get_all_pet_data()
        pet_owners = list(all_pets.keys())
        
        logger.info(f"Found {len(pet_owners)} pet owners: {pet_owners}")
        
        # Ensure each pet owner has tasks
        for user_id in pet_owners:
            try:
                slots = await tasks_db.get_slots(user_id)
                logger.info(f"User {user_id} has {len(slots)} task slots")
            except Exception as e:
                logger.error(f"Error ensuring tasks for user {user_id}: {e}")
        
        return pet_owners
        
    except Exception as e:
        logger.error(f"Error in ensure_all_pet_owners_have_tasks: {e}")
        return []


async def periodic_task_maintenance():
    """Periodically ensure all pet owners have tasks (runs every hour)"""
    while True:
        try:
            await asyncio.sleep(3600)  # Wait 1 hour
            await ensure_all_pet_owners_have_tasks()
        except Exception as e:
            logger.error(f"Error in periodic_task_maintenance: {e}")


async def midnight_reset_loop():
    """
    Fires once at the next UTC midnight, then every 24 hours after that.
    Resets all regular task slots (1-6) and clears any active cooldowns for
    every known user — so the reset happens even if users are offline.
    Also triggers the daily Pet Powerball draw.
    """
    import time as _time
    from datetime import datetime, timezone, timedelta

    while True:
        try:
            now_dt = datetime.now(timezone.utc)
            next_midnight = datetime(now_dt.year, now_dt.month, now_dt.day,
                                     tzinfo=timezone.utc) + timedelta(days=1)
            sleep_secs = (next_midnight - now_dt).total_seconds()
            logger.info(f"midnight_reset_loop: sleeping {sleep_secs:.0f}s until next UTC midnight")
            await asyncio.sleep(sleep_secs)
            logger.info("midnight_reset_loop: UTC midnight reached — resetting all users")
            await tasks_db.midnight_reset_all_users()

            # ── Weekly task reset (Sundays only) ──────────────────────────
            try:
                now_dt_after = datetime.now(timezone.utc)
                if now_dt_after.weekday() == 6:  # Sunday (weekday 6 = Sunday)
                    await tasks_db.weekly_reset_all_users()
                    logger.info("midnight_reset_loop: Weekly task reset complete (Sunday)")
            except Exception as we:
                logger.error(f"midnight_reset_loop: weekly reset failed: {we}", exc_info=True)

            # ── Monthly task reset (1st of each month only) ───────────────
            try:
                now_dt_after = datetime.now(timezone.utc)
                if now_dt_after.day == 1:
                    await tasks_db.monthly_reset_all_users()
                    logger.info("midnight_reset_loop: Monthly task reset complete (1st of month)")
            except Exception as me:
                logger.error(f"midnight_reset_loop: monthly reset failed: {me}", exc_info=True)

            # ── Pet Powerball daily draw ──────────────────────────────────
            try:
                from web.api.powerball_api import run_daily_draw
                draw_result = await run_daily_draw()
                logger.info(f"midnight_reset_loop: Powerball draw complete — "
                            f"{draw_result.get('winner_count', 0)} winner(s), "
                            f"pot {draw_result.get('pot_before', 0)} → {draw_result.get('pot_after', 0)}")
            except Exception as pb_err:
                logger.error(f"midnight_reset_loop: Powerball draw failed: {pb_err}", exc_info=True)

        except Exception as e:
            logger.error(f"midnight_reset_loop error: {e}", exc_info=True)
            await asyncio.sleep(60)  # back off briefly on error, then retry


@router.get("/tasks")
async def get_tasks(request: Request):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = user.get("id")
    if not user_id:
        return JSONResponse({"error": "User ID not found in session"}, status_code=401)
    user_id = str(user_id)  # Ensure user_id is string

    try:
        # Check if user has a pet first
        from Systems.Functions.user_data_manager import user_data_manager
        pet = await user_data_manager.get_pet_data_async(user_id)
        if not pet:
            return JSONResponse({"error": "no_pet", "message": "You need a pet to receive tasks"}, status_code=200)

        slots = await tasks_db.get_slots(user_id)
        prefs = await tasks_db.get_dm_prefs(user_id)
        now = time.time()
        for s in slots:
            if s.get("on_cooldown"):
                s["seconds_remaining"] = max(0, int(s["cooldown_until"] - now))
            else:
                s["seconds_remaining"] = 0
        return JSONResponse({"slots": slots, "prefs": prefs})
    except Exception as e:
        logger.error(f"get_tasks error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load tasks.")


@router.post("/tasks/ensure-all")
async def ensure_all_tasks(request: Request):
    """Admin endpoint to ensure all pet owners have tasks"""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    
    try:
        pet_owners = await ensure_all_pet_owners_have_tasks()
        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("tasks_ensure_all", {"pet_owners_count": len(pet_owners)})
        await queue.flush()

        animation = AnimationComponent.for_ui_update("tasks_ensured", 400)

        return JSONResponse({
            "success": True,
            "pet_owners": pet_owners,
            "message": f"Ensured tasks for {len(pet_owners)} pet owners",
            "animation": animation
        })
    except Exception as e:
        logger.error(f"ensure_all_tasks error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to ensure tasks for all pet owners.")


@router.post("/tasks/dismiss")
async def dismiss_task(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = user.get("id")
    if not user_id:
        return JSONResponse({"error": "User ID not found in session"}, status_code=401)
    user_id = str(user_id)  # Ensure user_id is string

    slot = int(data.get("slot", -1))
    if slot < 1 or slot > 6:  # Only regular slots can be dismissed
        raise HTTPException(status_code=400, detail="Invalid slot.")

    try:
        await tasks_db.dismiss_task(user_id, slot)
        # Schedule DM notification after the dismissal cooldown expires.
        asyncio.create_task(_delayed_notify(user_id, slot, _hours_to_seconds(DISMISS_COOLDOWN_HOURS["daily"])))
        # Return full slot list including goal
        slots = await tasks_db.get_slots(user_id)
        _apply_cooldown_seconds(slots, time.time())

        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("tasks_dismiss", {"user_id": user_id, "slot": slot})
        await queue.flush()

        animation = AnimationComponent.for_ui_update("task_dismissed", 300)

        return JSONResponse({"success": True, "slots": slots, "animation": animation})
    except Exception as e:
        logger.error(f"dismiss_task error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to dismiss task.")


@router.post("/tasks/dismiss-weekly")
async def dismiss_weekly_task(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = user.get("id")
    if not user_id:
        return JSONResponse({"error": "User ID not found in session"}, status_code=401)
    user_id = str(user_id)

    slot = int(data.get("slot", -1))
    if not (11 <= slot < 11 + WEEKLY_SLOTS):
        raise HTTPException(status_code=400, detail="Invalid weekly task slot.")

    try:
        await tasks_db.dismiss_weekly_task(user_id, slot)
        # Return full slot list
        slots = await tasks_db.get_weekly_slots(user_id)
        _apply_cooldown_seconds(slots, time.time())
        
        return JSONResponse({"success": True, "slots": slots})
    except Exception as e:
        logger.error(f"dismiss_weekly_task error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to dismiss weekly task.")


@router.post("/tasks/dismiss-monthly")
async def dismiss_monthly_task(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = user.get("id")
    if not user_id:
        return JSONResponse({"error": "User ID not found in session"}, status_code=401)
    user_id = str(user_id)

    slot = int(data.get("slot", -1))
    if not (21 <= slot < 21 + MONTHLY_SLOTS):
        raise HTTPException(status_code=400, detail="Invalid monthly task slot.")

    try:
        await tasks_db.dismiss_monthly_task(user_id, slot)
        # Return full slot list
        slots = await tasks_db.get_monthly_slots(user_id)
        _apply_cooldown_seconds(slots, time.time())

        return JSONResponse({"success": True, "slots": slots})
    except Exception as e:
        logger.error(f"dismiss_monthly_task error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to dismiss monthly task.")


async def _delayed_notify(user_id: str, slot: int, delay: float):
    await asyncio.sleep(delay)
    await _notify_slot_refresh(user_id, slot)


@router.get("/tasks/dm-prefs")
async def get_dm_prefs(request: Request):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = user.get("id")
    if not user_id:
        return JSONResponse({"error": "User ID not found in session"}, status_code=401)
    user_id = str(user_id)  # Ensure user_id is string
    prefs = await tasks_db.get_dm_prefs(user_id)
    return JSONResponse(prefs)


@router.post("/tasks/dm-prefs")
async def set_dm_prefs(request: Request, data: Dict[str, Any] = Body(...)):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = user.get("id")
    if not user_id:
        return JSONResponse({"error": "User ID not found in session"}, status_code=401)
    user_id = str(user_id)  # Ensure user_id is string

    dm_enabled = bool(data.get("dm_enabled", False))
    dm_mode = str(data.get("dm_mode", "all"))
    await tasks_db.set_dm_prefs(user_id, dm_enabled, dm_mode)

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("tasks_dm_prefs", {"user_id": user_id, "dm_enabled": dm_enabled, "dm_mode": dm_mode})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("dm_prefs_updated", 300)

    return JSONResponse({"success": True, "dm_enabled": dm_enabled, "dm_mode": dm_mode, "animation": animation})


# ── Internal progress hook (called by pets_api after each action) ─────────────

@router.get("/tasks/debug")
async def debug_session(request: Request):
    """Debug endpoint to check session data"""
    session_data = dict(request.session)
    user = request.session.get("discord_user")
    
    debug_info = {
        "session_keys": list(session_data.keys()),
        "discord_user": user,
        "user_id": user.get("id") if user else None,
        "user_id_str": str(user.get("id")) if user and user.get("id") else None,
        "full_session": session_data
    }
    
    return JSONResponse(debug_info)


async def record_action(user_id: str, action: str, meta: Optional[Dict] = None, won: bool = True):
    """
    Called by game endpoints after a successful action.
    Increments progress on daily, weekly, and monthly matching tasks.
    """
    try:
        if action in ("battle_npc", "boss") and not won:
            return

        await tasks_db.update_progress(user_id, action, meta)

        try:
            await tasks_db.update_weekly_progress(user_id, action, meta)
        except Exception as we:
            logger.debug(f"weekly progress update error for {user_id}/{action}: {we}")

        try:
            await tasks_db.update_monthly_progress(user_id, action, meta)
        except Exception as me:
            logger.debug(f"monthly progress update error for {user_id}/{action}: {me}")

    except Exception as e:
        logger.error(f"record_action error for {user_id}/{action}: {e}", exc_info=True)


async def record_action_by(user_id: str, action: str, amount: int, meta: Optional[Dict] = None, won: bool = True):
    """
    Called by endpoints where one action can count multiple units.
    Increments daily, weekly, and monthly matching tasks by the provided amount.
    """
    try:
        if amount <= 0:
            return
        if action in ("battle_npc", "boss") and not won:
            return

        await tasks_db.update_progress_by(user_id, action, amount)

        try:
            await tasks_db.update_weekly_progress_by(user_id, action, amount, meta)
        except Exception as we:
            logger.debug(f"weekly progress-by update error for {user_id}/{action}: {we}")

        try:
            await tasks_db.update_monthly_progress_by(user_id, action, amount, meta)
        except Exception as me:
            logger.debug(f"monthly progress-by update error for {user_id}/{action}: {me}")

    except Exception as e:
        logger.error(f"record_action_by error for {user_id}/{action}/{amount}: {e}", exc_info=True)


async def _check_and_deliver_daily_goal(user_id: str, completed_slots: list):
    """Kept for compatibility — no longer auto-delivers. Goal is claimed manually."""
    pass


@router.post("/tasks/claim")
async def claim_task(request: Request, data: Dict[str, Any] = Body(...)):
    """
    Claim the reward for a completed regular task slot.
    Delivers the reward, starts the 4h cooldown, and ticks the daily goal bar.
    """
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id", ""))
    if not user_id:
        return JSONResponse({"error": "User ID not found"}, status_code=401)

    slot = int(data.get("slot", -1))
    if slot < 1 or slot > 6:
        raise HTTPException(status_code=400, detail="Invalid slot.")

    try:
        reward = await tasks_db.claim_task(user_id, slot)
        if reward is None:
            return JSONResponse({"error": "Task not claimable (not complete or already claimed)"}, status_code=400)

        # Deliver the reward to inventory
        reward_msg = await tasks_db.deliver_reward(user_id, reward)
        logger.info(f"Task claimed for {user_id} slot {slot}: {reward_msg}")

        # Schedule DM when the slot refreshes after cooldown
        asyncio.create_task(_delayed_notify(user_id, slot, _hours_to_seconds(COMPLETION_COOLDOWN_HOURS["daily"])))

        # Check if daily goal just completed so we can notify
        goal_data = await tasks_db.get_task_for_slot(user_id, 0)
        goal_just_completed = (
            goal_data and
            goal_data["task"].get("completed") and
            not goal_data["task"].get("reward_delivered")
        )

        # Return updated slots
        slots = await tasks_db.get_slots(user_id)
        _apply_cooldown_seconds(slots, time.time())

        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("tasks_claim", {"user_id": user_id, "slot": slot, "reward": reward})
        await queue.flush()

        animation = AnimationComponent.for_loot(_reward_animation_items(reward, "Common"))

        return JSONResponse({
            "success": True,
            "reward": reward,
            "reward_msg": reward_msg,
            "goal_ready_to_claim": goal_just_completed,
            "slots": slots,
            "animation": animation
        })
    except Exception as e:
        logger.error(f"claim_task error for {user_id} slot {slot}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to claim task.")


@router.get("/tasks/weekly")
async def get_weekly_tasks(request: Request):
    """Return the user's weekly tasks (slots 10-13)."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id", ""))
    if not user_id:
        return JSONResponse({"error": "User ID not found"}, status_code=401)
    try:
        pet = await user_data_manager.get_pet_data_async(user_id)
        if not pet:
            return JSONResponse({"error": "no_pet"}, status_code=200)
        weekly = await tasks_db.get_weekly_slots(user_id)
        _apply_cooldown_seconds(weekly, time.time())
        return JSONResponse({"weekly": weekly})
    except Exception as e:
        logger.error(f"get_weekly_tasks error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load weekly tasks.")


@router.post("/tasks/weekly/claim")
async def claim_weekly_task(request: Request, data: Dict[str, Any] = Body(...)):
    """Claim a completed weekly task reward (slot 11-13)."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id", ""))
    slot = int(data.get("slot", -1))
    if not (11 <= slot < 11 + WEEKLY_SLOTS):
        raise HTTPException(status_code=400, detail="Invalid weekly slot.")
    try:
        reward = await tasks_db.claim_weekly_task(user_id, slot)
        if reward is None:
            return JSONResponse({"error": "Not claimable"}, status_code=400)
        reward_msg = await tasks_db.deliver_reward(user_id, reward)
        logger.info(f"Weekly task claimed for {user_id} slot {slot}: {reward_msg}")
        weekly = await tasks_db.get_weekly_slots(user_id)
        _apply_cooldown_seconds(weekly, time.time())

        queue = EventQueue()
        queue.push("weekly_task_claim", {"user_id": user_id, "slot": slot, "reward": reward})
        await queue.flush()
        animation = AnimationComponent.for_loot(_reward_animation_items(reward, "Uncommon"))

        return JSONResponse({
            "success": True, "reward": reward, "reward_msg": reward_msg,
            "weekly": weekly, "animation": animation
        })
    except Exception as e:
        logger.error(f"claim_weekly_task error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to claim weekly task.")


@router.post("/tasks/weekly/claim-goal")
async def claim_weekly_goal(request: Request):
    """Claim the weekly goal reward once all 3 weekly tasks are claimed."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id", ""))
    try:
        reward = await tasks_db.claim_weekly_goal(user_id)
        if reward is None:
            return JSONResponse({"error": "Not claimable"}, status_code=400)
        reward_msg = await tasks_db.deliver_reward(user_id, reward)
        logger.info(f"Weekly goal claimed for {user_id}: {reward_msg}")
        weekly = await tasks_db.get_weekly_slots(user_id)
        _apply_cooldown_seconds(weekly, time.time())

        queue = EventQueue()
        queue.push("weekly_goal_claim", {"user_id": user_id, "reward": reward})
        await queue.flush()
        animation = AnimationComponent.for_loot(_reward_animation_items(reward, "Rare"))

        return JSONResponse({
            "success": True, "reward": reward, "reward_msg": reward_msg,
            "weekly": weekly, "animation": animation
        })
    except Exception as e:
        logger.error(f"claim_weekly_goal error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to claim weekly goal.")


# ── Monthly task endpoints ────────────────────────────────────────────────────

@router.get("/tasks/monthly")
async def get_monthly_tasks(request: Request):
    """Return the user's monthly tasks (slots 20-26)."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id", ""))
    if not user_id:
        return JSONResponse({"error": "User ID not found"}, status_code=401)
    try:
        pet = await user_data_manager.get_pet_data_async(user_id)
        if not pet:
            return JSONResponse({"error": "no_pet"}, status_code=200)
        monthly = await tasks_db.get_monthly_slots(user_id)
        _apply_cooldown_seconds(monthly, time.time())
        return JSONResponse({"monthly": monthly})
    except Exception as e:
        logger.error(f"get_monthly_tasks error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load monthly tasks.")


@router.post("/tasks/monthly/claim")
async def claim_monthly_task(request: Request, data: Dict[str, Any] = Body(...)):
    """Claim a completed monthly task reward (slots 21-26)."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id", ""))
    slot = int(data.get("slot", -1))
    if not (21 <= slot < 21 + MONTHLY_SLOTS):
        raise HTTPException(status_code=400, detail="Invalid monthly slot.")
    try:
        reward = await tasks_db.claim_monthly_task(user_id, slot)
        if reward is None:
            return JSONResponse({"error": "Not claimable"}, status_code=400)
        reward_msg = await tasks_db.deliver_reward(user_id, reward)
        logger.info(f"Monthly task claimed for {user_id} slot {slot}: {reward_msg}")
        monthly = await tasks_db.get_monthly_slots(user_id)
        _apply_cooldown_seconds(monthly, time.time())

        queue = EventQueue()
        queue.push("monthly_task_claim", {"user_id": user_id, "slot": slot, "reward": reward})
        await queue.flush()
        animation = AnimationComponent.for_loot(_reward_animation_items(reward, "Uncommon"))

        return JSONResponse({
            "success": True, "reward": reward, "reward_msg": reward_msg,
            "monthly": monthly, "animation": animation
        })
    except Exception as e:
        logger.error(f"claim_monthly_task error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to claim monthly task.")


@router.post("/tasks/monthly/claim-goal")
async def claim_monthly_goal(request: Request):
    """Claim the monthly goal reward once all 10 monthly tasks are claimed."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id", ""))
    try:
        reward = await tasks_db.claim_monthly_goal(user_id)
        if reward is None:
            return JSONResponse({"error": "Not claimable"}, status_code=400)
        reward_msg = await tasks_db.deliver_reward(user_id, reward)
        logger.info(f"Monthly goal claimed for {user_id}: {reward_msg}")
        monthly = await tasks_db.get_monthly_slots(user_id)
        _apply_cooldown_seconds(monthly, time.time())

        queue = EventQueue()
        queue.push("monthly_goal_claim", {"user_id": user_id, "reward": reward})
        await queue.flush()
        animation = AnimationComponent.for_loot(_reward_animation_items(reward, "Rare"))

        return JSONResponse({
            "success": True, "reward": reward, "reward_msg": reward_msg,
            "monthly": monthly, "animation": animation
        })
    except Exception as e:
        logger.error(f"claim_monthly_goal error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to claim monthly goal.")


@router.post("/tasks/claim-goal")
async def claim_daily_goal(request: Request):
    """
    Claim the daily goal reward once all 10 tasks have been claimed.
    """
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse({"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id", ""))
    if not user_id:
        return JSONResponse({"error": "User ID not found"}, status_code=401)

    try:
        reward = await tasks_db.claim_daily_goal(user_id)
        if reward is None:
            return JSONResponse({"error": "Goal not claimable (not complete or already claimed)"}, status_code=400)

        reward_msg = await tasks_db.deliver_reward(user_id, reward)
        logger.info(f"Daily goal claimed for {user_id}: {reward_msg}")

        slots = await tasks_db.get_slots(user_id)
        now = time.time()
        for s in slots:
            if s.get("on_cooldown"):
                s["seconds_remaining"] = max(0, int(s["cooldown_until"] - now))
            else:
                s["seconds_remaining"] = 0

        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("tasks_claim_goal", {"user_id": user_id, "reward": reward})
        await queue.flush()

        animation = AnimationComponent.for_loot(_reward_animation_items(reward, "Uncommon"))

        return JSONResponse({
            "success": True,
            "reward": reward,
            "reward_msg": reward_msg,
            "slots": slots,
            "animation": animation
        })
    except Exception as e:
        logger.error(f"claim_daily_goal error for {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to claim daily goal.")

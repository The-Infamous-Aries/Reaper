"""Zombie Survival web API.

The web page is a synced controller/viewer for the Discord Zombie Survival cog.
State reads can fall back to SQLite, but mutating actions require the live cog so
Discord messages, votes, and the browser never split into separate games.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from starlette.requests import Request

from Systems.Fun.zombie_db import ZombieDB
from Systems.Functions.config import ARIES_USER_ID

router = APIRouter()


def _session_user(request: Request) -> Dict[str, Any]:
    user = request.session.get("discord_user")
    if not user or not user.get("id"):
        raise HTTPException(status_code=401, detail="Discord login required")
    return user


def _get_bot():
    try:
        from Systems.Functions.web_server import get_bot_instance
        return get_bot_instance()
    except Exception:
        return None


def _get_cog():
    bot = _get_bot()
    if not bot:
        return None
    return bot.get_cog("ZombieSurvival")


def _display_name(user_id: str, user: Optional[Dict[str, Any]] = None) -> str:
    if user and str(user.get("id")) == str(user_id):
        return user.get("global_name") or user.get("username") or f"Survivor {user_id[-4:]}"

    bot = _get_bot()
    if bot:
        try:
            discord_user = bot.get_user(int(user_id))
            if discord_user:
                return discord_user.display_name
        except (TypeError, ValueError):
            pass
    return f"Survivor {str(user_id)[-4:]}"


def _avatar_url(user: Dict[str, Any]) -> Optional[str]:
    user_id = user.get("id")
    avatar = user.get("avatar")
    if user_id and avatar:
        ext = "gif" if str(avatar).startswith("a_") else "png"
        return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.{ext}?size=128"
    return None


async def _is_admin(user_id: str) -> bool:
    if str(user_id) == str(ARIES_USER_ID):
        return True
    cog = _get_cog()
    if cog and hasattr(cog, "is_zombie_admin_id"):
        return await cog.is_zombie_admin_id(user_id)
    return await ZombieDB().is_admin(str(user_id))


def _choice_images(round_num: int) -> Dict[str, str]:
    set_idx = ((max(1, int(round_num)) - 1) % 2) + 1
    return {
        "A": f"/static/Emojis/Zombie/a{set_idx}.png",
        "B": f"/static/Emojis/Zombie/b{set_idx}.png",
        "C": f"/static/Emojis/Zombie/c{set_idx}.png",
        "D": f"/static/Emojis/Zombie/d{set_idx}.png",
    }


def _choice_preview(cog, state: Dict[str, Any], index: int, choice: str) -> str:
    if cog and getattr(cog, "state", None) is state:
        try:
            return cog._choice_preview(cog._get_choice_plan(index, choice))
        except Exception:
            pass
    odds = state.get("choice_odds", [50, 50, 50, 50])
    base = odds[index] if index < len(odds) else 50
    return f"Base {base}%"


async def _load_state() -> Dict[str, Any]:
    cog = _get_cog()
    if cog:
        return cog.state
    return await ZombieDB().load_state()


async def _serialize_state(state: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    user_id = str(user["id"])
    cog = _get_cog()
    is_admin = await _is_admin(user_id)
    choices = state.get("choices", [])[:4]
    votes = {str(k): int(v) for k, v in state.get("votes", {}).items()}
    voter_choices = {str(k): int(v) for k, v in state.get("voter_choices", {}).items()}
    survivors = state.get("survivors", {})

    round_num = int(state.get("round") or 0)
    deadline_ts = int(float(state.get("last_update") or 0) + 2 * 3600) if state.get("active") else 0
    now_ts = int(time.time())

    web_choices = []
    images = _choice_images(round_num or 1)
    for index, choice in enumerate(choices):
        label = "ABCD"[index]
        web_choices.append({
            "index": index,
            "label": label,
            "text": str(choice),
            "votes": votes.get(str(index), 0),
            "image": images[label],
            "preview": _choice_preview(cog, state, index, str(choice)),
        })

    survivor_rows = []
    for uid, survivor in survivors.items():
        survivor_rows.append({
            "user_id": str(uid),
            "display_name": _display_name(str(uid), user),
            "health": int(survivor.get("health", 0)),
            "stamina": int(survivor.get("stamina", 0)),
            "morale": int(survivor.get("morale", 0)),
            "status": survivor.get("status", "Normal"),
            "revolver_loaded": int(survivor.get("revolver_loaded", 0)),
            "revolver_spare": int(survivor.get("revolver_spare", 0)),
            "rifle_loaded": int(survivor.get("rifle_loaded", 0)),
            "rifle_spare": int(survivor.get("rifle_spare", 0)),
            "melee": survivor.get("melee", "Crowbar"),
            "melee_condition": int(survivor.get("melee_condition", 100)),
            "is_me": str(uid) == user_id,
        })
    survivor_rows.sort(key=lambda s: (s["status"] == "Deceased", not s["is_me"], s["display_name"].lower()))

    return {
        "active": bool(state.get("active")),
        "round": round_num,
        "channel_id": state.get("channel_id"),
        "message_id": state.get("message_id"),
        "current_event": state.get("current_event", ""),
        "choices": web_choices,
        "votes_total": sum(votes.values()),
        "voters_total": len(state.get("voters", [])),
        "has_voted": user_id in [str(v) for v in state.get("voters", [])],
        "my_vote": voter_choices.get(user_id),
        "deadline_ts": deadline_ts,
        "seconds_remaining": max(0, deadline_ts - now_ts) if deadline_ts else 0,
        "history": state.get("history", [])[-5:],
        "survivors": survivor_rows,
        "my_character": survivors.get(user_id),
        "is_admin": is_admin,
        "user": {
            "id": user_id,
            "username": user.get("username"),
            "display_name": user.get("global_name") or user.get("username"),
            "avatar_url": _avatar_url(user),
        },
    }


@router.get("/zombie/state")
async def zombie_state(request: Request):
    user = _session_user(request)
    state = await _load_state()
    return JSONResponse(await _serialize_state(state, user))


@router.post("/zombie/vote")
async def zombie_vote(request: Request):
    user = _session_user(request)
    body = await request.json()
    try:
        choice_index = int(body.get("choice_index"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="choice_index is required")

    cog = _get_cog()
    if not cog:
        raise HTTPException(status_code=503, detail="Zombie Survival Discord cog is not loaded")

    ok, message, _choice = await cog.cast_vote(str(user["id"]), choice_index)
    state = cog.state
    payload = await _serialize_state(state, user)
    payload["ok"] = ok
    payload["message"] = message
    status = 200 if ok else 400
    return JSONResponse(payload, status_code=status)


@router.post("/zombie/start")
async def zombie_start(request: Request):
    user = _session_user(request)
    if not await _is_admin(str(user["id"])):
        raise HTTPException(status_code=403, detail="Zombie admin access required")

    body = await request.json()
    channel_id = body.get("channel_id")
    if not channel_id:
        raise HTTPException(status_code=400, detail="channel_id is required to start from the webpage")

    cog = _get_cog()
    bot = _get_bot()
    if not cog or not bot:
        raise HTTPException(status_code=503, detail="Zombie Survival Discord cog is not loaded")
    if cog.state.get("active"):
        raise HTTPException(status_code=409, detail="A Zombie Survival game is already active")

    try:
        channel = bot.get_channel(int(channel_id))
    except (TypeError, ValueError):
        channel = None
    if not channel:
        raise HTTPException(status_code=404, detail="Discord channel was not found in the bot cache")

    ok, message = await cog.start_new_game(channel, str(user["id"]))
    payload = await _serialize_state(cog.state, user)
    payload["ok"] = ok
    payload["message"] = message
    return JSONResponse(payload, status_code=200 if ok else 400)


@router.post("/zombie/stop")
async def zombie_stop(request: Request):
    user = _session_user(request)
    if not await _is_admin(str(user["id"])):
        raise HTTPException(status_code=403, detail="Zombie admin access required")

    cog = _get_cog()
    if not cog:
        raise HTTPException(status_code=503, detail="Zombie Survival Discord cog is not loaded")

    ok, message = await cog.stop_game(str(user["id"]))
    payload = await _serialize_state(cog.state, user)
    payload["ok"] = ok
    payload["message"] = message
    return JSONResponse(payload, status_code=200 if ok else 400)

"""
Settings API — user preferences, theme customization, nation linking, and auto-fill settings.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from Systems.Functions.pets_db import pets_db

logger = logging.getLogger("Reaper.WebServer.SettingsAPI")

router = APIRouter()

# ── Upload config ──────────────────────────────────────────────────────────────
_BG_DIR = Path("web/static/user_backgrounds")
_BG_DIR.mkdir(parents=True, exist_ok=True)
_MAX_BG_BYTES = 5 * 1024 * 1024   # 5 MB
_ALLOWED_MIME  = {"image/jpeg", "image/png", "image/webp"}
_EXT_MAP = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
# Magic bytes for validation (first 12 bytes)
_MAGIC = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"RIFF": "image/webp",   # checked more carefully below
}


# Pydantic models for request validation (following existing pattern)
class SettingsUpdateRequest(BaseModel):
    linked_nation_id: Optional[int] = None
    linked_nation_name: Optional[str] = None
    linked_alliance_id: Optional[int] = None
    linked_alliance_name: Optional[str] = None
    theme_bg_color: Optional[str] = None
    theme_bg_secondary: Optional[str] = None
    theme_bg_tertiary: Optional[str] = None
    theme_gold_primary: Optional[str] = None
    theme_gold_secondary: Optional[str] = None
    theme_text_primary: Optional[str] = None
    theme_text_secondary: Optional[str] = None
    theme_use_custom_image: Optional[bool] = None
    theme_custom_image_url: Optional[str] = None
    theme_custom_bg_url: Optional[str] = None
    theme_hide_bg_image: Optional[int] = None
    auto_fill_nations: Optional[str] = None
    auto_fill_alliances: Optional[str] = None
    auto_fill_nation_raids: Optional[int] = None
    auto_fill_nation_revopt: Optional[int] = None
    auto_fill_nation_calc: Optional[int] = None
    auto_fill_alliances_raids_exclude: Optional[str] = None
    auto_fill_alliances_compare_home: Optional[str] = None
    # Watch page home alliance
    watch_home_alliance_id: Optional[int] = None
    watch_home_alliance_name: Optional[str] = None
    # Privacy toggles (1 = visible/default, 0 = hidden)
    privacy_show_pet_leaderboard: Optional[int] = None
    privacy_show_nations_leaderboard: Optional[int] = None
    privacy_show_watch_nations: Optional[int] = None
    privacy_show_nations_rankings: Optional[int] = None
    # Language / locale (e.g. 'en', 'es', 'fr', ...)
    language: Optional[str] = None
    # Menu layout customization (JSON string of page order)
    menu_layout: Optional[str] = None


_VALID_LOCALES = {'en', 'es', 'fr', 'de', 'pt', 'zh', 'ja', 'ko', 'ru', 'ar'}


@router.get("/settings")
async def get_settings(request: Request):
    """Get all settings for the current user."""
    user = request.session.get('discord_user')
    if not user:
        # Return a minimal response so the frontend can still render
        # the "not logged in" state without crashing
        return JSONResponse(content={
            "logged_in": False,
            "discord_user": None,
            "linked_nation_id": None,
            "linked_nation_name": None,
        }, status_code=200)
    
    user_id = str(user.get('id'))
    logger.info(f"Getting settings for user_id: {user_id}")
    
    settings = await pets_db.get_user_settings(user_id)
    logger.info(f"Settings from DB: {settings}")
    
    # Merge with session-based linked_nation if not in DB yet
    session_nation = request.session.get("linked_nation")
    logger.info(f"Session nation: {session_nation}")
    
    if session_nation and not settings.get("linked_nation_id"):
        settings["linked_nation_id"] = session_nation.get("nation_id")
        settings["linked_nation_name"] = session_nation.get("nation_name")
        settings["linked_nation_leader"] = session_nation.get("leader_name", "")
        settings["linked_nation_flag"] = session_nation.get("flag", "")
        logger.info(f"Merged session nation into settings")
    
    # Add Discord user info to response
    settings["discord_user"] = {
        "id": user.get("id"),
        "username": user.get("username"),
        "global_name": user.get("global_name"),
        "discriminator": user.get("discriminator"),
        "avatar": user.get("avatar")
    }
    settings["logged_in"] = True
    
    logger.info(f"Final settings to return: {settings}")
    return JSONResponse(content=settings)


@router.post("/settings")
async def update_settings(request: Request, data: SettingsUpdateRequest):
    """Update user settings."""
    user = request.session.get('discord_user')
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    user_id = str(user.get('id'))
    
    # Convert to dict, filtering out None values
    body = data.model_dump(exclude_none=True)
    
    # Validate theme colors (hex format)
    color_fields = [
        'theme_bg_color', 'theme_bg_secondary', 'theme_bg_tertiary',
        'theme_gold_primary', 'theme_gold_secondary',
        'theme_text_primary', 'theme_text_secondary'
    ]
    for field in color_fields:
        if field in body:
            if not body[field].startswith('#') or len(body[field]) != 7:
                raise HTTPException(status_code=400, detail=f"Invalid color format for {field}")
    
    # Validate JSON arrays
    if 'auto_fill_nations' in body:
        try:
            json.loads(body['auto_fill_nations'])
        except:
            raise HTTPException(status_code=400, detail="auto_fill_nations must be valid JSON array")
    
    if 'auto_fill_alliances' in body:
        try:
            json.loads(body['auto_fill_alliances'])
        except:
            raise HTTPException(status_code=400, detail="auto_fill_alliances must be valid JSON array")
    
    if 'auto_fill_alliances_raids_exclude' in body:
        try:
            json.loads(body['auto_fill_alliances_raids_exclude'])
        except:
            raise HTTPException(status_code=400, detail="auto_fill_alliances_raids_exclude must be valid JSON array")
    
    if 'auto_fill_alliances_compare_home' in body:
        try:
            json.loads(body['auto_fill_alliances_compare_home'])
        except:
            raise HTTPException(status_code=400, detail="auto_fill_alliances_compare_home must be valid JSON array")

    # Validate language code
    if 'language' in body:
        if body['language'] not in _VALID_LOCALES:
            raise HTTPException(status_code=400, detail=f"Invalid language code: {body['language']}")

    # Validate privacy integers (must be 0 or 1)
    privacy_fields = [
        'privacy_show_pet_leaderboard', 'privacy_show_nations_leaderboard',
        'privacy_show_watch_nations', 'privacy_show_nations_rankings',
    ]
    for field in privacy_fields:
        if field in body and body[field] not in (0, 1):
            raise HTTPException(status_code=400, detail=f"{field} must be 0 or 1")

    success = await pets_db.update_user_settings(user_id, body)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update settings")
    
    return JSONResponse(content={"success": True})


@router.post("/settings/link-nation")
async def persist_link_nation(request: Request):
    """Link a nation and persist to database."""
    user = request.session.get('discord_user')
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    user_id = str(user.get('id'))
    body = await request.json()
    nation_id = str(body.get("nation_id", "")).strip()
    
    if not nation_id.isdigit():
        raise HTTPException(status_code=400, detail="nation_id must be numeric")
    
    # Fetch nation details from PnW API/DB
    from PnWHarvester.db.global_nations_db import GlobalNationsDB
    from Systems.Functions.db_paths import GLOBAL_NATIONS_DB_STR
    
    gdb = GlobalNationsDB(GLOBAL_NATIONS_DB_STR)
    nation = await gdb.get_nation(int(nation_id))
    
    if not nation:
        raise HTTPException(status_code=404, detail="Nation not found")
    
    # Update session
    request.session["linked_nation"] = {
        "nation_id": nation_id,
        "nation_name": nation.get("nation_name", ""),
        "leader_name": nation.get("leader_name", ""),
        "flag": nation.get("flag", "")
    }
    
    # Persist to database
    await pets_db.update_user_settings(user_id, {
        "linked_nation_id": nation_id,
        "linked_nation_name": nation.get("nation_name", ""),
        "linked_nation_leader": nation.get("leader_name", ""),
        "linked_nation_flag": nation.get("flag", "")
    })
    
    return JSONResponse(content={
        "success": True,
        "nation_id": nation_id,
        "nation_name": nation.get("nation_name", ""),
        "leader_name": nation.get("leader_name", ""),
        "flag": nation.get("flag", "")
    })


@router.delete("/settings/link-nation")
async def persist_unlink_nation(request: Request):
    """Unlink nation and remove from database."""
    user = request.session.get('discord_user')
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    user_id = str(user.get('id'))
    
    # Clear session
    request.session.pop("linked_nation", None)
    
    # Clear from database
    await pets_db.update_user_settings(user_id, {
        "linked_nation_id": None,
        "linked_nation_name": None,
        "linked_nation_leader": None,
        "linked_nation_flag": None
    })
    
    return JSONResponse(content={"success": True})


@router.post("/settings/upload-background")
async def upload_background(request: Request, file: UploadFile = File(...)):
    """Upload a custom background image for the logged-in user."""
    user = request.session.get('discord_user')
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    user_id = str(user.get('id'))

    # Content-type header check (first gate)
    ct = (file.content_type or "").lower().split(";")[0].strip()
    if ct not in _ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG and WebP images are allowed.")

    # Read entire file into memory for size + magic-byte checks
    data = await file.read()

    if len(data) > _MAX_BG_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds the 5 MB limit.")

    if len(data) < 12:
        raise HTTPException(status_code=400, detail="File too small to be a valid image.")

    # Magic-byte validation
    header = data[:12]
    detected = None
    if header[:3] == b"\xff\xd8\xff":
        detected = "image/jpeg"
    elif header[:8] == b"\x89PNG\r\n\x1a\n":
        detected = "image/png"
    elif header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        detected = "image/webp"

    if detected is None:
        raise HTTPException(status_code=400, detail="File does not appear to be a valid image.")

    # Use the detected type, not the claimed content-type
    ext = _EXT_MAP[detected]

    # Remove any previous background for this user
    for old in _BG_DIR.glob(f"{user_id}.*"):
        try:
            old.unlink()
        except OSError:
            pass

    dest = _BG_DIR / f"{user_id}{ext}"
    dest.write_bytes(data)

    bg_url = f"/static/user_backgrounds/{user_id}{ext}"
    logger.info(f"Background uploaded for {user_id} → {dest} ({len(data)} bytes)")

    # Persist URL to user settings
    await pets_db.update_user_settings(user_id, {"theme_custom_bg_url": bg_url})

    return JSONResponse(content={"success": True, "url": bg_url})


@router.delete("/settings/upload-background")
async def remove_background(request: Request):
    """Remove the user's custom background image."""
    user = request.session.get('discord_user')
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    user_id = str(user.get('id'))

    # Delete file(s)
    for old in _BG_DIR.glob(f"{user_id}.*"):
        try:
            old.unlink()
        except OSError:
            pass

    await pets_db.update_user_settings(user_id, {"theme_custom_bg_url": None})
    return JSONResponse(content={"success": True})


@router.delete("/settings")
async def delete_all_settings(request: Request):
    """Delete all settings for the current user (theme, nation link, privacy, language, auto-fill).
    Pet data and casino balance are stored separately and are not affected.
    """
    user = request.session.get('discord_user')
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")

    user_id = str(user.get('id'))

    # Also remove any uploaded background file
    for old in _BG_DIR.glob(f"{user_id}.*"):
        try:
            old.unlink()
        except OSError:
            pass

    success = await pets_db.delete_user_settings(user_id)
    if not success:
        # No row found is fine — settings were already gone
        logger.debug(f"No settings row found to delete for user {user_id}")

    return JSONResponse(content={"success": True})


# IMPORTANT: This router must be registered in web_server.py
# Add to the import section:
# from web.api.settings_api import router as settings_api
# Add to the app.include_router section:
# app.include_router(settings_api, prefix="/api")

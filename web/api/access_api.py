"""
access_api.py — Alliance-based website access control.

Endpoint:
  GET /api/access/check-alliance
      Returns whether the current session user has verified + approved-alliance access.
      Used by access_guard.js on every protected page load.

Response schemas:
  Allowed:  { "allowed": true,  "nation_name": str, "alliance_name": str, "is_admin": bool }
  Denied:   { "allowed": false, "reason": str, "alliance_name": str | null }

  Reason values:
    "not_logged_in"         — no Discord session
    "not_verified"          — logged in but nation not verified via /self_verify
    "alliance_not_approved" — verified but alliance not in approved list
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("Reaper.WebServer.AccessAPI")

router = APIRouter()


async def _get_live_alliance(nation_id: int) -> tuple[Optional[int], Optional[str]]:
    """
    Look up the nation's CURRENT alliance from GlobalNations.db.
    Returns (alliance_id, alliance_name).  Falls back to (None, None) on error.
    This prevents stale cached data in Verified.db from granting/denying wrong access
    when a user switches alliances after verifying.
    """
    try:
        import asyncio
        import sqlite3
        from Systems.Functions.db_paths import GLOBAL_NATIONS_DB_STR

        def _sync() -> tuple[Optional[int], Optional[str]]:
            with sqlite3.connect(GLOBAL_NATIONS_DB_STR, timeout=10) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT alliance_id, alliance_name FROM nations WHERE id = ? LIMIT 1",
                    (nation_id,),
                ).fetchone()
                if row:
                    return (
                        int(row["alliance_id"]) if row["alliance_id"] else None,
                        str(row["alliance_name"]) if row["alliance_name"] else None,
                    )
                return (None, None)

        return await asyncio.to_thread(_sync)
    except Exception as exc:
        logger.warning("_get_live_alliance(%d) failed: %s", nation_id, exc)
        return (None, None)


@router.get("/access/check-alliance")
async def check_alliance_access(request: Request) -> JSONResponse:
    """
    Check whether the current session user is allowed to access protected pages.

    Access is granted when ALL of the following are true:
      1. The user is logged in via Discord OAuth (session has 'discord_user')
      2. Their Discord ID exists in Verified.db (verified via /self_verify or /reaper_verify)
      3. Their current nation's alliance_id is in the approved_alliances table

    ARIES (hardcoded super-admin) bypasses the alliance check entirely.
    """
    # ── Step 1: Discord login check ───────────────────────────────────────
    discord_user = request.session.get("discord_user")
    if not discord_user:
        return JSONResponse(
            {"allowed": False, "reason": "not_logged_in", "alliance_name": None}
        )

    discord_id = str(discord_user.get("id", ""))
    if not discord_id:
        return JSONResponse(
            {"allowed": False, "reason": "not_logged_in", "alliance_name": None}
        )

    # ── ARIES bypass ──────────────────────────────────────────────────────
    from Systems.Functions.config import ARIES_USER_ID
    if discord_id == str(ARIES_USER_ID):
        return JSONResponse(
            {
                "allowed": True,
                "nation_name": "ARIES",
                "alliance_name": "Reaper Admin",
                "is_admin": True,
            }
        )

    # ── Step 2: Verified check ────────────────────────────────────────────
    from Systems.PnW.Util.reaper_verify import get_verified_db

    vdb = get_verified_db()
    verified = await vdb.get_by_discord_id(discord_id)

    if not verified:
        return JSONResponse(
            {"allowed": False, "reason": "not_verified", "alliance_name": None}
        )

    nation_id = verified.get("nation_id")
    nation_name = verified.get("nation_name", "Unknown")

    # ── Step 3: Live alliance lookup (prevents stale cache issues) ────────
    if nation_id:
        live_alliance_id, live_alliance_name = await _get_live_alliance(int(nation_id))
    else:
        live_alliance_id, live_alliance_name = None, None

    # Fall back to cached values if live lookup returned nothing
    alliance_id = live_alliance_id if live_alliance_id is not None else verified.get("alliance_id")
    alliance_name = live_alliance_name if live_alliance_name is not None else verified.get("alliance_name", "Unknown")

    if not alliance_id:
        return JSONResponse(
            {
                "allowed": False,
                "reason": "alliance_not_approved",
                "alliance_name": alliance_name,
            }
        )

    # ── Step 4: Alliance approval check ──────────────────────────────────
    is_approved = await vdb.is_alliance_approved(int(alliance_id))
    if not is_approved:
        return JSONResponse(
            {
                "allowed": False,
                "reason": "alliance_not_approved",
                "alliance_name": alliance_name,
            }
        )

    return JSONResponse(
        {
            "allowed": True,
            "nation_name": nation_name,
            "alliance_name": alliance_name,
            "is_admin": False,
        }
    )

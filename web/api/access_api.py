"""
Access Control API — exposes endpoints for the frontend to check which
restricted pages the current session user is allowed to view.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.requests import Request
import logging

router = APIRouter()
logger = logging.getLogger("Reaper.AccessAPI")


def _current_user_id(request: Request) -> str | None:
    discord_user = request.session.get("discord_user")
    if discord_user and isinstance(discord_user, dict):
        uid = discord_user.get("id")
        if uid:
            return str(uid)
    uid = request.session.get("user_id")
    return str(uid) if uid else None


@router.get("/access/check")
async def check_access(request: Request):
    """
    Return which restricted pages the current session user may view.

    Response shape:
      {
        "authenticated": bool,
        "has_access": bool,          # true if at least one page is allowed
        "allowed_pages": [str, ...]  # list of page keys the user can see
      }
    """
    uid = _current_user_id(request)
    if not uid:
        return JSONResponse({"has_access": False, "authenticated": False, "allowed_pages": []})

    from Systems.Functions.page_access import get_allowed_pages
    pages = await get_allowed_pages(uid)
    return JSONResponse({
        "has_access":    len(pages) > 0,
        "authenticated": True,
        "user_id":       uid,
        "allowed_pages": sorted(pages),
    })

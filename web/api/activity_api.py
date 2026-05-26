"""
Activity API Endpoint
Provides real-time activity feed for the homepage dashboard.
Tracks Discord command completions and web page interactions.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import logging

router = APIRouter()
logger = logging.getLogger("Reaper.ActivityAPI")

# In-memory activity storage (ring buffer — newest first)
_recent_activities: List[Dict[str, Any]] = []
MAX_ACTIVITIES = 100


def add_activity(
    activity_type: str,
    message: str,
    user: str = None,
    detail: str = None,
    source: str = "discord",
):
    """
    Add a new activity to the feed.

    Args:
        activity_type: Category — 'pnw', 'pets', 'fun', 'astrology', 'system'
        message:       Short human-readable headline
        user:          Display name of the user (Discord name or 'Web User')
        detail:        Optional extra context line (target nation, alliance, etc.)
        source:        'discord' or 'web'
    """
    activity = {
        "type": activity_type,
        "message": message,
        "detail": detail or "",
        "source": source,
        "user": user or "Unknown",
        "timestamp": datetime.utcnow(),
    }
    _recent_activities.insert(0, activity)
    if len(_recent_activities) > MAX_ACTIVITIES:
        _recent_activities.pop()
    logger.debug(f"[activity] {source}/{activity_type}: {message}")


def format_time(timestamp: datetime) -> str:
    """Format timestamp as relative time string."""
    diff = datetime.utcnow() - timestamp
    if diff < timedelta(minutes=1):
        return "Just now"
    elif diff < timedelta(hours=1):
        m = int(diff.total_seconds() / 60)
        return f"{m}m ago"
    elif diff < timedelta(days=1):
        h = int(diff.total_seconds() / 3600)
        return f"{h}h ago"
    else:
        return f"{diff.days}d ago"


@router.get("/activity/recent")
async def get_recent_activities(limit: int = 20):
    """Return recent activities with formatted relative timestamps."""
    try:
        out = []
        for a in _recent_activities[:limit]:
            entry = {k: v for k, v in a.items() if k != "timestamp"}
            entry["time"] = format_time(a["timestamp"])
            out.append(entry)
        return JSONResponse(content={"activities": out}, status_code=200)
    except Exception as e:
        logger.error(f"Error serving activities: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error serving activities")


@router.post("/activity/add")
async def add_activity_endpoint(data: Dict[str, Any]):
    """Add a new activity (internal systems call this)."""
    try:
        msg = data.get("message", "")
        if not msg:
            raise HTTPException(status_code=400, detail="message is required")
        add_activity(
            activity_type=data.get("type", "system"),
            message=msg,
            user=data.get("user"),
            detail=data.get("detail"),
            source=data.get("source", "discord"),
        )
        return JSONResponse(content={"status": "ok"}, status_code=200)
    except Exception as e:
        logger.error(f"Error adding activity: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error adding activity")

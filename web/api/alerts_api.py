"""
API routes for resource price alerts.
Reads/writes to the same alerts.db used by the Discord bot — one truth source.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from starlette.requests import Request
from pydantic import BaseModel
import aiosqlite
import logging

router = APIRouter()
logger = logging.getLogger("Reaper.AlertsAPI")

from Systems.Functions.db_paths import ALERTS_DB_STR as ALERTS_DB

VALID_RESOURCES = {
    "food", "coal", "oil", "uranium", "lead", "iron",
    "bauxite", "gasoline", "munitions", "steel", "aluminum", "credit"
}


def _get_user_id(request: Request) -> str | None:
    user = request.session.get("discord_user")
    return str(user["id"]) if user and user.get("id") else None


class AlertPayload(BaseModel):
    resource:   str
    price_type: str   # 'buy' or 'sell'
    direction:  str   # 'above' or 'below'
    threshold:  float


@router.get("/alerts")
async def get_alerts(request: Request):
    """Return all active alerts for the logged-in user."""
    user_id = _get_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not logged in.")

    async with aiosqlite.connect(ALERTS_DB) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT resource, price_type, direction, threshold
               FROM rss_alerts WHERE user_id=?
               ORDER BY resource, price_type, direction""",
            (user_id,)
        )
        rows = await cur.fetchall()

    return JSONResponse([dict(r) for r in rows])


@router.post("/alerts")
async def set_alert(request: Request, payload: AlertPayload):
    """Create or update an alert for the logged-in user."""
    user_id = _get_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not logged in.")

    resource = payload.resource.lower()
    if resource not in VALID_RESOURCES:
        raise HTTPException(status_code=400, detail=f"Invalid resource: {resource}")
    if payload.price_type not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail="price_type must be 'buy' or 'sell'")
    if payload.direction not in ("above", "below"):
        raise HTTPException(status_code=400, detail="direction must be 'above' or 'below'")
    if payload.threshold <= 0:
        raise HTTPException(status_code=400, detail="threshold must be > 0")

    async with aiosqlite.connect(ALERTS_DB) as conn:
        await conn.execute("""
            INSERT INTO rss_alerts (user_id, resource, price_type, direction, threshold)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, resource, price_type, direction)
            DO UPDATE SET threshold = excluded.threshold
        """, (user_id, resource, payload.price_type, payload.direction, payload.threshold))
        await conn.commit()

    logger.info(f"Alert set: user={user_id} {resource} {payload.price_type} {payload.direction} @ {payload.threshold}")
    return JSONResponse({"ok": True})


@router.delete("/alerts")
async def delete_alert(request: Request, resource: str, price_type: str, direction: str):
    """Remove a specific alert for the logged-in user."""
    user_id = _get_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not logged in.")

    async with aiosqlite.connect(ALERTS_DB) as conn:
        cur = await conn.execute(
            "DELETE FROM rss_alerts WHERE user_id=? AND resource=? AND price_type=? AND direction=?",
            (user_id, resource.lower(), price_type, direction)
        )
        await conn.commit()

    return JSONResponse({"ok": cur.rowcount > 0})

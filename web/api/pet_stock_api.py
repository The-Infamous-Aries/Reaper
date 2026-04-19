"""Pet Stock API routes."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import logging
from typing import Any, Dict

from Systems.Functions import pet_stock_engine as engine

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/pet-stock/market")
async def get_market(request: Request):
    """Return current prices, 48h history, active events, and per-token multipliers for the logged-in user."""
    try:
        prices  = await engine.get_latest_prices()
        history = await engine.get_price_history(hours=168)  # 7 days
        events  = await engine.get_active_events()  # Only currently active events

        # Build per-token % change vs previous entry
        changes: Dict[str, float] = {}
        for token, hist in history.items():
            if len(hist) >= 2:
                prev  = hist[-2]["price"]
                curr  = hist[-1]["price"]
                changes[token] = round(((curr - prev) / max(1, prev)) * 100, 2)
            else:
                changes[token] = 0.0

        # Per-token price multipliers for the logged-in user's pet
        multipliers: Dict[str, float] = {}
        user = request.session.get("discord_user")
        if user:
            from Systems.Functions.user_data_manager import user_data_manager
            pet_data = await user_data_manager.get_pet_data_async(str(user.get("id")))
            if pet_data:
                all_tokens = engine.PET_TYPES + engine.ELEMENTS
                for tok in all_tokens:
                    multipliers[tok] = engine.get_price_multiplier(tok, pet_data)

        return JSONResponse(content={
            "prices":       {k: round(v, 2) for k, v in prices.items()},
            "changes":      changes,
            "history":      history,
            "events":       events,
            "multipliers":  multipliers,
            "type_emojis":    engine.TYPE_EMOJIS,
            "element_emojis": engine.ELEMENT_EMOJIS,
            "base_prices":    engine.BASE_PRICES,
        })
    except Exception as e:
        logger.error(f"get_market error: {e}", exc_info=True)
        return JSONResponse(content={"error": "Failed to load market"}, status_code=500)


@router.get("/pet-stock/holdings")
async def get_holdings(request: Request):
    """Return the logged-in user's token holdings."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id  = str(user.get("id"))
    holdings = await engine.get_user_holdings(user_id)
    return JSONResponse(content={"holdings": holdings})


@router.get("/pet-stock/pnl")
async def get_pnl(request: Request):
    """Return the logged-in user's P&L stats."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))
    pnl = await engine.get_user_pnl(user_id)
    return JSONResponse(content=pnl)


@router.post("/pet-stock/buy")
async def buy_token(request: Request):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    try:
        body: Dict[str, Any] = await request.json()
        token    = str(body.get("token", "")).lower()
        quantity = int(body.get("quantity", 1))
    except Exception:
        return JSONResponse(content={"error": "Invalid request body"}, status_code=400)

    from Systems.Functions.user_data_manager import user_data_manager
    pet_data = await user_data_manager.get_pet_data_async(user_id)
    if not pet_data:
        return JSONResponse(content={"error": "You don't have a pet"}, status_code=400)

    result = await engine.buy_token(user_id, token, quantity, pet_data)
    status = 200 if result.get("ok") else 400
    if result.get("ok"):
        try:
            from web.api.tasks_api import record_action as _task_record
            for _ in range(quantity):
                await _task_record(user_id, "buy_token")
        except Exception:
            pass
    return JSONResponse(content=result, status_code=status)


@router.post("/pet-stock/sell")
async def sell_token(request: Request):
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    try:
        body: Dict[str, Any] = await request.json()
        token    = str(body.get("token", "")).lower()
        quantity = int(body.get("quantity", 1))
    except Exception:
        return JSONResponse(content={"error": "Invalid request body"}, status_code=400)

    from Systems.Functions.user_data_manager import user_data_manager
    pet_data = await user_data_manager.get_pet_data_async(user_id)
    if not pet_data:
        return JSONResponse(content={"error": "You don't have a pet"}, status_code=400)

    result = await engine.sell_token(user_id, token, quantity, pet_data)
    status = 200 if result.get("ok") else 400
    if result.get("ok"):
        try:
            from web.api.tasks_api import record_action as _task_record
            for _ in range(quantity):
                await _task_record(user_id, "sell_token")
        except Exception:
            pass
    return JSONResponse(content=result, status_code=status)

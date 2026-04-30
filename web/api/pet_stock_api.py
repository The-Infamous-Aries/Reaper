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
            from web.api.tasks_api import tasks_db as _tasks_db
            await _tasks_db.update_progress_by(user_id, "buy_token", quantity)
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
            from web.api.tasks_api import tasks_db as _tasks_db
            await _tasks_db.update_progress_by(user_id, "sell_token", quantity)
        except Exception:
            pass
    return JSONResponse(content=result, status_code=status)


@router.post("/pet-stock/buy-all")
async def buy_all_token(request: Request):
    """Buy as many tokens as possible up to the 100,000 cap."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    try:
        body: Dict[str, Any] = await request.json()
        token = str(body.get("token", "")).lower()
        logger.info(f"buy_all_token: user_id={user_id}, token='{token}', body={body}")
    except Exception as e:
        logger.error(f"buy_all_token: Invalid request body: {e}")
        return JSONResponse(content={"error": "Invalid request body"}, status_code=400)

    from Systems.Functions.user_data_manager import user_data_manager
    pet_data = await user_data_manager.get_pet_data_async(user_id)
    if not pet_data:
        logger.error(f"buy_all_token: User {user_id} has no pet")
        return JSONResponse(content={"error": "You don't have a pet"}, status_code=400)

    logger.info(f"buy_all_token: Calling engine.buy_all_token for user {user_id}, token '{token}'")
    result = await engine.buy_all_token(user_id, token, pet_data)
    logger.info(f"buy_all_token: Engine result: {result}")
    status = 200 if result.get("ok") else 400
    if result.get("ok"):
        try:
            from web.api.tasks_api import tasks_db as _tasks_db
            await _tasks_db.update_progress_by(user_id, "buy_token", result.get("new_qty", 0))
        except Exception:
            pass
    return JSONResponse(content=result, status_code=status)


@router.post("/pet-stock/buy-max")
async def buy_max_all_tokens(request: Request):
    """Buy 100,000 of each token type (up to 1,600,000 total tokens)."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    from Systems.Functions.user_data_manager import user_data_manager
    pet_data = await user_data_manager.get_pet_data_async(user_id)
    if not pet_data:
        return JSONResponse(content={"error": "You don't have a pet"}, status_code=400)

    result = await engine.buy_max_all_tokens(user_id, pet_data)
    status = 200 if result.get("ok") else 400
    if result.get("ok"):
        try:
            from web.api.tasks_api import tasks_db as _tasks_db
            await _tasks_db.update_progress_by(user_id, "buy_token", result.get("total_bought", 0))
        except Exception:
            pass
    return JSONResponse(content=result, status_code=status)


@router.post("/pet-stock/sell-max")
async def sell_max_all_tokens(request: Request):
    """Sell all held tokens of all types."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    from Systems.Functions.user_data_manager import user_data_manager
    pet_data = await user_data_manager.get_pet_data_async(user_id)
    if not pet_data:
        return JSONResponse(content={"error": "You don't have a pet"}, status_code=400)

    result = await engine.sell_max_all_tokens(user_id, pet_data)
    status = 200 if result.get("ok") else 400
    if result.get("ok"):
        try:
            from web.api.tasks_api import tasks_db as _tasks_db
            await _tasks_db.update_progress_by(user_id, "sell_token", result.get("total_payout", 0))
        except Exception:
            pass
    return JSONResponse(content=result, status_code=status)


@router.post("/pet-stock/sell-all")
async def sell_all_token(request: Request):
    """Sell all held tokens of a given type."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))

    try:
        body: Dict[str, Any] = await request.json()
        token = str(body.get("token", "")).lower()
    except Exception:
        return JSONResponse(content={"error": "Invalid request body"}, status_code=400)

    from Systems.Functions.user_data_manager import user_data_manager
    pet_data = await user_data_manager.get_pet_data_async(user_id)
    if not pet_data:
        return JSONResponse(content={"error": "You don't have a pet"}, status_code=400)

    result = await engine.sell_all_token(user_id, token, pet_data)
    status = 200 if result.get("ok") else 400
    if result.get("ok"):
        try:
            from web.api.tasks_api import tasks_db as _tasks_db
            await _tasks_db.update_progress_by(user_id, "sell_token", result.get("payout", 0))
        except Exception:
            pass
    return JSONResponse(content=result, status_code=status)
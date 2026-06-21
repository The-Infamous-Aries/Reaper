"""Pet Stock API routes."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import logging
from typing import Any, Dict

from Systems.Functions.user_data_manager import user_data_manager
from Systems.Pets.Logic.event_bus import EventQueue
from Systems.Pets.Logic.pet_components import AnimationComponent
from web.api.pets.gpp_helpers import _invalidate_stats_cache

logger = logging.getLogger("pet_stock_api")
router = APIRouter()

# ── Pet Stock Engine ─────────────────────────────────────────────────────────────
import Systems.Functions.pet_stock_engine as pet_stock_engine_module


async def _record_stock_task_progress(user_id: str, action: str, amount: int) -> None:
    """Record stock task progress without letting task errors break trades."""
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        amount = 0
    if amount <= 0:
        return

    try:
        from web.api.tasks_api import record_action_by
        await record_action_by(user_id, action, amount)
    except Exception:
        logger.debug(
            "stock task progress update failed for %s/%s/%s",
            user_id,
            action,
            amount,
            exc_info=True,
        )


@router.get("/pet-stock/market")
async def get_market(request: Request):
    """Return current market state."""
    try:
        prices  = await pet_stock_engine_module.get_latest_prices()
        history = await pet_stock_engine_module.get_price_history(hours=168)  # 7 days
        events  = await pet_stock_engine_module.get_active_events()  # Only currently active events

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
                all_tokens = pet_stock_engine_module.PET_TYPES + pet_stock_engine_module.ELEMENTS
                for tok in all_tokens:
                    multipliers[tok] = pet_stock_engine_module.get_price_multiplier(tok, pet_data)

        return JSONResponse(content={
            "prices":       {k: round(v, 2) for k, v in prices.items()},
            "changes":      changes,
            "history":      history,
            "events":       events,
            "multipliers":  multipliers,
            "type_emojis":    pet_stock_engine_module.TYPE_EMOJIS,
            "element_emojis": pet_stock_engine_module.ELEMENT_EMOJIS,
            "base_prices":    pet_stock_engine_module.BASE_PRICES,        })
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
    holdings = await pet_stock_engine_module.get_user_holdings(user_id)
    return JSONResponse(content={"holdings": holdings})


@router.get("/pet-stock/pnl")
async def get_pnl(request: Request):
    """Return the logged-in user's P&L stats."""
    user = request.session.get("discord_user")
    if not user:
        return JSONResponse(content={"error": "Not logged in"}, status_code=401)
    user_id = str(user.get("id"))
    pnl = await pet_stock_engine_module.get_user_pnl(user_id)
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

    result = await pet_stock_engine_module.buy_token(user_id, token, quantity, pet_data)
    status = 200 if result.get("ok") else 400
    if result.get("ok"):
        await _record_stock_task_progress(user_id, "buy_token", quantity)

        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("pet_stock_buy", {"user_id": user_id, "token": token, "quantity": quantity})
        await queue.flush()

        animation = AnimationComponent.for_ui_update("stock_buy", 300)
        result["animation"] = animation

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

    result = await pet_stock_engine_module.sell_token(user_id, token, quantity, pet_data)
    status = 200 if result.get("ok") else 400
    if result.get("ok"):
        await _record_stock_task_progress(user_id, "sell_token", quantity)

        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("pet_stock_sell", {"user_id": user_id, "token": token, "quantity": quantity})
        await queue.flush()

        animation = AnimationComponent.for_ui_update("stock_sell", 300)
        result["animation"] = animation

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

    before_qty = int((await pet_stock_engine_module.get_user_holdings(user_id)).get(token, 0))
    logger.info(f"buy_all_token: Calling pet_stock_engine_module.buy_all_token for user {user_id}, token '{token}'")
    result = await pet_stock_engine_module.buy_all_token(user_id, token, pet_data)
    logger.info(f"buy_all_token: Engine result: {result}")
    status = 200 if result.get("ok") else 400
    if result.get("ok"):
        bought_qty = max(0, int(result.get("new_qty", 0)) - before_qty)
        await _record_stock_task_progress(user_id, "buy_token", bought_qty)

        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("pet_stock_buy_all", {"user_id": user_id, "token": token, "quantity": bought_qty})
        await queue.flush()

        animation = AnimationComponent.for_ui_update("stock_buy_all", 400)
        result["animation"] = animation

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

    result = await pet_stock_engine_module.buy_max_all_tokens(user_id, pet_data)
    status = 200 if result.get("ok") else 400
    if result.get("ok"):
        await _record_stock_task_progress(user_id, "buy_token", result.get("total_bought", 0))

        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("pet_stock_buy_max", {"user_id": user_id, "total_bought": result.get("total_bought", 0)})
        await queue.flush()

        animation = AnimationComponent.for_ui_update("stock_buy_max", 500)
        result["animation"] = animation

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

    result = await pet_stock_engine_module.sell_max_all_tokens(user_id, pet_data)
    status = 200 if result.get("ok") else 400
    if result.get("ok"):
        await _record_stock_task_progress(user_id, "sell_token", result.get("total_sold", 0))

        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("pet_stock_sell_max", {"user_id": user_id, "total_payout": result.get("total_payout", 0)})
        await queue.flush()

        animation = AnimationComponent.for_ui_update("stock_sell_max", 500)
        result["animation"] = animation

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

    before_qty = int((await pet_stock_engine_module.get_user_holdings(user_id)).get(token, 0))
    result = await pet_stock_engine_module.sell_all_token(user_id, token, pet_data)
    status = 200 if result.get("ok") else 400
    if result.get("ok"):
        await _record_stock_task_progress(user_id, "sell_token", before_qty)

        # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
        queue = EventQueue()
        queue.push("pet_stock_sell_all", {"user_id": user_id, "token": token, "quantity": before_qty, "payout": result.get("payout", 0)})
        await queue.flush()

        animation = AnimationComponent.for_ui_update("stock_sell_all", 400)
        result["animation"] = animation

    return JSONResponse(content=result, status_code=status)

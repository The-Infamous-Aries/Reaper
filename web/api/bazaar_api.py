from fastapi import APIRouter, Request, Body, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from Systems.Functions.user_data_manager import user_data_manager
from Systems.Functions.pets_db import pets_db
from Systems.Pets.Logic.event_bus import EventQueue
from Systems.Pets.Logic.pet_components import AnimationComponent
from web.api.pets.gpp_helpers import _invalidate_stats_cache
import logging
from typing import Dict, Any, List, Set
import asyncio
import discord

logger = logging.getLogger(__name__)
router = APIRouter()

# --- WebSocket broadcast hub ---
_ws_clients: Set[WebSocket] = set()

async def _broadcast(payload: dict):
    """Push a JSON message to all connected bazaar WebSocket clients."""
    dead = set()
    for ws in list(_ws_clients):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.add(ws)
    _ws_clients.difference_update(dead)


@router.websocket("/bazaar/ws")
async def bazaar_ws(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.add(websocket)
    try:
        # Send current board immediately on connect
        listings = await pets_db.bazaar_get_active_listings()
        await websocket.send_json({"type": "board", "listings": listings})
        # Keep alive — client sends pings, we just wait for disconnect
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(websocket)


# ── REST helpers ──────────────────────────────────────────────────────────────

def _auth(request: Request):
    user = request.session.get("discord_user")
    if not user:
        return None, None, JSONResponse({"error": "Not logged in"}, status_code=401)
    uid = user.get("id")
    uname = user.get("username", "Unknown")
    if not uid:
        return None, None, JSONResponse({"error": "No user ID in session"}, status_code=401)
    return uid, uname, None


async def _send_purchase_dm(
    seller_id: str,
    seller_pet: Dict[str, Any],
    listing: Dict[str, Any],
    buyer_name: str,
    xp_before: int,
    level_before: int,
):
    """DM the seller on Discord when their Item Board listing is purchased."""
    try:
        from Systems.Functions.web_server import get_bot_instance
        bot = get_bot_instance()
        if not bot:
            return

        user = await bot.fetch_user(int(seller_id))
        if not user:
            return

        xp_after = int(seller_pet.get("experience", 0))
        level_after = int(seller_pet.get("level", 1))
        leveled_up = level_after > level_before

        price_type = listing.get("price_type", "xp")
        item_name  = listing.get("item_name", "Unknown Item")
        item_rarity = listing.get("item_rarity", "Common")
        quantity   = listing.get("quantity", 1)
        pet_name   = seller_pet.get("name", "Your Pet")

        # Rarity colour map
        rarity_colours = {
            "Common": 0xAAAAAA,
            "Uncommon": 0x57D9A3,
            "Rare": 0x5865F2,
            "Epic": 0xA855F7,
            "Legendary": 0xF59E0B,
        }
        colour = rarity_colours.get(item_rarity, 0x5865F2)

        embed = discord.Embed(
            title="🛒 Item Sold on the Item Board!",
            colour=colour,
        )
        embed.add_field(name="Item", value=f"{item_name} x{quantity} ({item_rarity})", inline=False)
        embed.add_field(name="Bought by", value=buyer_name, inline=True)

        if price_type == "xp":
            xp_gained = listing.get("xp_price", xp_after - xp_before)
            embed.add_field(name="XP Earned", value=f"+{xp_gained:,} XP", inline=True)

        embed.add_field(
            name=f"{pet_name}'s XP",
            value=f"**Before:** {xp_before:,} XP (Lv {level_before})\n**After:** {xp_after:,} XP (Lv {level_after})",
            inline=False,
        )

        if leveled_up:
            embed.add_field(
                name="🎉 Level Up!",
                value=f"{pet_name} reached **Level {level_after}**!",
                inline=False,
            )

        embed.set_footer(text="Item Board • Reaper Bot")

        await user.send(embed=embed)
    except discord.Forbidden:
        logger.warning(f"Cannot DM seller {seller_id} — DMs may be disabled.")
    except Exception as e:
        logger.error(f"Failed to send purchase DM to seller {seller_id}: {e}", exc_info=True)


# ── GET active listings ───────────────────────────────────────────────────────

@router.get("/bazaar/listings")
async def get_listings(request: Request):
    listings = await pets_db.bazaar_get_active_listings()
    return JSONResponse({"listings": listings})


# ── POST a new listing ────────────────────────────────────────────────────────

@router.post("/bazaar/post")
async def post_listing(request: Request, data: Dict[str, Any] = Body(...)):
    uid, uname, err = _auth(request)
    if err:
        return err

    item_name  = (data.get("item_name") or "").strip()
    quantity   = int(data.get("quantity", 1))
    price_type = data.get("price_type", "xp")   # "xp" | "trade"
    xp_price   = data.get("xp_price")
    trade_item = (data.get("trade_item_name") or "").strip() or None
    trade_qty  = int(data.get("trade_item_quantity") or 1)

    if not item_name:
        return JSONResponse({"error": "item_name is required"}, status_code=400)
    if quantity < 1:
        return JSONResponse({"error": "quantity must be >= 1"}, status_code=400)
    if price_type == "xp":
        if not xp_price or int(xp_price) < 1:
            return JSONResponse({"error": "xp_price must be >= 1"}, status_code=400)
        xp_price = int(xp_price)
        trade_item = None
        trade_qty  = None
    elif price_type == "trade":
        if not trade_item:
            return JSONResponse({"error": "trade_item_name is required for trade listings"}, status_code=400)
        xp_price = None
    else:
        return JSONResponse({"error": "price_type must be 'xp' or 'trade'"}, status_code=400)

    pet_data = await user_data_manager.get_pet_data_async(uid)
    if not pet_data:
        return JSONResponse({"error": "You don't have a pet"}, status_code=400)

    # Find item metadata from inventory
    inventory = pet_data.get("inventory", [])
    item_meta = next((it for it in inventory if it["name"].lower() == item_name.lower()), None)
    if not item_meta:
        return JSONResponse({"error": f"'{item_name}' not found in your inventory"}, status_code=400)
    if item_meta.get("count", 1) < quantity:
        return JSONResponse({"error": f"You only have {item_meta.get('count',1)}x {item_name}"}, status_code=400)

    listing_id = await pets_db.bazaar_post_listing(
        seller_id=uid,
        seller_name=uname,
        seller_pet_name=pet_data.get("name"),
        seller_pet_emoji=pet_data.get("emoji_name") or pet_data.get("species"),
        item_name=item_meta["name"],
        item_type=item_meta.get("type", "Material"),
        item_rarity=item_meta.get("rarity", "Common"),
        quantity=quantity,
        price_type=price_type,
        xp_price=xp_price,
        trade_item_name=trade_item,
        trade_item_quantity=trade_qty,
        pet_data=pet_data,
    )
    if listing_id is None:
        return JSONResponse({"error": "Failed to post listing — check your inventory"}, status_code=400)

    # Task tracking — posting to Item Board
    try:
        from web.api.tasks_api import record_action as _task_record
        await _task_record(str(uid), "post_item")
    except Exception:
        pass

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("bazaar_post", {"user_id": uid, "item_name": item_name, "quantity": quantity, "listing_id": listing_id})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("listing_posted", 400)

    listings = await pets_db.bazaar_get_active_listings()
    await _broadcast({"type": "board", "listings": listings})
    return JSONResponse({"ok": True, "listing_id": listing_id, "animation": animation})


# ── BUY a listing ─────────────────────────────────────────────────────────────

@router.post("/bazaar/buy/{listing_id}")
async def buy_listing(listing_id: int, request: Request):
    uid, uname, err = _auth(request)
    if err:
        return err

    buyer_pet = await user_data_manager.get_pet_data_async(uid)
    if not buyer_pet:
        return JSONResponse({"error": "You don't have a pet"}, status_code=400)

    # Get listing to find seller
    listings = await pets_db.bazaar_get_active_listings()
    listing = next((l for l in listings if l["listing_id"] == listing_id), None)
    if not listing:
        return JSONResponse({"error": "Listing not found or already sold"}, status_code=404)

    seller_pet = await user_data_manager.get_pet_data_async(str(listing["seller_id"]))
    if not seller_pet:
        return JSONResponse({"error": "Seller no longer has a pet"}, status_code=400)

    # Snapshot seller XP/level before the transaction
    seller_xp_before    = int(seller_pet.get("experience", 0))
    seller_level_before = int(seller_pet.get("level", 1))

    result = await pets_db.bazaar_buy_listing(
        listing_id=listing_id,
        buyer_id=uid,
        buyer_name=uname,
        buyer_pet=buyer_pet,
        seller_pet=seller_pet,
    )
    if not result.get("ok"):
        return JSONResponse({"error": result.get("error", "Purchase failed")}, status_code=400)

    # Re-fetch both pets after transaction to get accurate updated state
    updated_seller_pet = await user_data_manager.get_pet_data_async(str(listing["seller_id"])) or seller_pet
    updated_buyer_pet  = await user_data_manager.get_pet_data_async(uid) or buyer_pet

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("bazaar_buy", {"buyer_id": uid, "seller_id": str(listing["seller_id"]), "listing_id": listing_id, "item_name": listing.get("item_name")})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("listing_purchased", 400)

    listings = await pets_db.bazaar_get_active_listings()
    await _broadcast({"type": "board", "listings": listings})

    # Fire-and-forget DM to seller
    asyncio.create_task(_send_purchase_dm(
        seller_id=str(listing["seller_id"]),
        seller_pet=updated_seller_pet,
        listing=listing,
        buyer_name=uname,
        xp_before=seller_xp_before,
        level_before=seller_level_before,
    ))

    return JSONResponse({"ok": True, "animation": animation})


# ── CANCEL a listing ──────────────────────────────────────────────────────────

@router.post("/bazaar/cancel/{listing_id}")
async def cancel_listing(listing_id: int, request: Request):
    uid, uname, err = _auth(request)
    if err:
        return err

    # Pass an empty fallback — bazaar_cancel_listing now fetches fresh pet data internally
    result = await pets_db.bazaar_cancel_listing(
        listing_id=listing_id,
        seller_id=uid,
        seller_pet={},
    )
    if not result.get("ok"):
        return JSONResponse({"error": result.get("error", "Cancel failed")}, status_code=400)

    # ── GPP: emit event + animation (Observer pattern + Component pattern) ─────────
    queue = EventQueue()
    queue.push("bazaar_cancel", {"user_id": uid, "listing_id": listing_id})
    await queue.flush()

    animation = AnimationComponent.for_ui_update("listing_cancelled", 300)

    listings = await pets_db.bazaar_get_active_listings()
    await _broadcast({"type": "board", "listings": listings})
    return JSONResponse({"ok": True, "animation": animation})

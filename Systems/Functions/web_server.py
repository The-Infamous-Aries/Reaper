# Standard Library Imports
import asyncio
import io
import logging
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import json

# Third-Party Imports
import discord
import httpx
import psutil
import uvicorn
from discord.ext import commands
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect

# Version marker - homepage routing fix v1.1
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse, Response, StreamingResponse)
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

# Add project root to path to allow for clean imports
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

# Local Application Imports
import Systems.Functions.database_manager as db
from Systems.Astrology import reading
from Systems.Functions.ai_brain import get_ai_choice

from Systems.Functions.utils import (SERVICE_WEB_SERVER, get_service_port,
                                     kill_process_on_port, start_cloudflare_tunnel_async,
                                     stop_cloudflare_tunnel_async, monitor_tunnel_and_server,
                                     get_web_public_url, is_web_tunnel_running, initialize_service_ports)

from Systems.PnW.Util.query import (create_v3_query_instance,
                                    get_all_treaties, get_game_info,
                                    get_nation_by_id, get_nation_by_name)
from Systems.PnW.Util.war_calc import calculate_war_costs, get_resource_prices
from web.api.astrology_api import router as astrology_api
from web.api.bot_info import router as bot_info_api
from web.api.stats_api import router as stats_api
from web.api.docs import router as docs_api
from web.api.casino_api import casino_api
from web.api.blackjack_api import router as blackjack_api
from web.api.craps_api import router as craps_api
from web.api.holdem_api import router as holdem_api
from web.api.races_api import router as races_api
from web.api.minigames_api import router as minigames_api
from web.api.casino_lobby_api import router as casino_lobby_api
from web.api.library import router as library_api
from web.api.pets_api import router as pets_api
from web.api.absorb_api import router as absorb_api
from web.api.pnw_api import router as pnw_api
from web.api.discord_auth import router as discord_auth_api
from web.api.watch_api import router as watch_api
from web.api.alerts_api import router as alerts_api
from web.api.arena_api import router as arena_api
from web.api.weapon_api import router as weapon_api
from web.api.bazaar_api import router as bazaar_api
from web.api.pet_stock_api import router as pet_stock_api
from web.api.ss_api import router as ss_api
from web.api.world_api import router as world_api
from web.api.tasks_api import router as tasks_api
from web.api.powerball_api import router as powerball_api
from web.api.scratch_api import router as scratch_api
from web.api.cache_api import router as cache_api
from web.api.rev_optimizer_api import router as rev_optimizer_api
from web.api.raids_api import router as raids_api
from web.api.image_proxy import router as image_proxy_api
from web.api.news_api import router as news_api
from web.api.colosseum_api import router as colosseum_api
from web.api.dungeon_api import router as dungeon_api
from web.api.forge_api import router as forge_api

from Systems.Functions.database_manager import get_resource_prices_comparison, get_colors_comparison, get_resource_supply_comparison

# Global variable to hold the bot instance
_bot_instance: Optional[commands.Bot] = None

# Development mode toggle for caching
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"

def set_bot_instance(bot: commands.Bot):
    """Sets the global bot instance for the web server to use."""
    global _bot_instance
    _bot_instance = bot
    logger.info(f"Bot instance set in web_server module: {_bot_instance.user.name if _bot_instance and _bot_instance.user else 'None'}")

def get_bot_instance() -> Optional[commands.Bot]:
    """Returns the global bot instance, or None if not yet set."""
    return _bot_instance


# Request models
class AstrologyRequest(BaseModel):
    month: int
    day: int
    year: int

app = FastAPI()

# CORS must be outermost middleware (added first = outermost in Starlette's reverse stack).
# allow_credentials=True is incompatible with allow_origins=["*"], so use explicit origin.
# WebSocket upgrade requests don't send CORS preflight, but the initial HTTP upgrade
# request must not be rejected by the CORS layer.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://reaper.qzz.io", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add session middleware
# IMPORTANT: This key should be a secret and loaded from environment variables in a real application
app.add_middleware(
    SessionMiddleware,
    secret_key="your-secret-key-here",
    session_cookie="session",
    same_site="lax",
    https_only=False,  # Cloudflare terminates SSL; server receives plain HTTP
    max_age=86400,     # 24 hours
)

# Include all API routers FIRST - before any static file mounting
app.include_router(casino_api, prefix="/api", tags=["casino"])
app.include_router(blackjack_api, prefix="/api", tags=["blackjack"])
app.include_router(craps_api, prefix="/api", tags=["craps"])
app.include_router(holdem_api, prefix="/api", tags=["holdem"])
app.include_router(races_api, prefix="/api", tags=["races"])
app.include_router(minigames_api, prefix="/api", tags=["minigames"])
app.include_router(casino_lobby_api, prefix="/api", tags=["casino-lobby"])
app.include_router(bot_info_api, prefix="/api", tags=["bot-info"])
app.include_router(stats_api, prefix="/api", tags=["stats"])
app.include_router(docs_api, prefix="/api", tags=["docs"])
app.include_router(library_api, prefix="/api", tags=["library"])
app.include_router(pets_api, prefix="/api", tags=["pets"])
app.include_router(absorb_api, prefix="/api", tags=["absorb"])
app.include_router(pnw_api, prefix="/api", tags=["pnw-graphs"])
app.include_router(discord_auth_api, prefix="/api", tags=["discord-auth"])
app.include_router(watch_api, prefix="/api", tags=["watch"])
app.include_router(alerts_api, prefix="/api", tags=["alerts"])
app.include_router(arena_api, prefix="/api", tags=["arena"])
app.include_router(weapon_api, prefix="/api", tags=["weapons"])
app.include_router(bazaar_api, prefix="/api", tags=["bazaar"])
app.include_router(pet_stock_api, prefix="/api", tags=["pet-stock"])
app.include_router(ss_api, prefix="/api", tags=["survivor-series"])
app.include_router(world_api, prefix="/api", tags=["world"])
app.include_router(tasks_api, prefix="/api", tags=["tasks"])
app.include_router(powerball_api, prefix="/api", tags=["powerball"])
app.include_router(scratch_api, prefix="/api", tags=["scratch"])
app.include_router(cache_api, prefix="/api", tags=["cache"])
app.include_router(rev_optimizer_api, prefix="/api", tags=["rev-optimizer"])
app.include_router(raids_api, prefix="/api", tags=["raids"])
app.include_router(image_proxy_api, prefix="/api", tags=["image-proxy"])
app.include_router(news_api, prefix="/api", tags=["news"])
app.include_router(colosseum_api, prefix="/api", tags=["colosseum"])
app.include_router(dungeon_api, prefix="/api", tags=["dungeon"])
app.include_router(forge_api, prefix="/api", tags=["forge"])


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(broadcast_updates())
    # Initialize PetSystem on app state so the adopt endpoint can use it
    from Systems.Pets.pets_system import PetSystem
    app.state.pet_system = PetSystem(bot=None)
    # Start pet stock hourly loop
    from Systems.Functions.pet_stock_engine import start_stock_loop
    asyncio.create_task(start_stock_loop())
    # Restore SS game state from database (keeps pets in lobby/game across restarts)
    from web.api.ss_api import _load_state as _ss_load_state
    asyncio.create_task(_ss_load_state())
    # Ensure all pet owners have tasks
    from web.api.tasks_api import ensure_all_pet_owners_have_tasks, periodic_task_maintenance, midnight_reset_loop
    asyncio.create_task(ensure_all_pet_owners_have_tasks())
    asyncio.create_task(periodic_task_maintenance())
    asyncio.create_task(midnight_reset_loop())
    # Initialise Powerball DB on startup
    from web.api.powerball_api import _ensure_db as _pb_ensure_db
    asyncio.create_task(_pb_ensure_db())
    # Start Colosseum hourly battle loop
    from web.api.colosseum_api import start_colosseum_loop
    asyncio.create_task(start_colosseum_loop())
    # NOTE: Revenue pre-warm disabled - turn revenue is now handled by harvester's RevenueComponent
    # which runs independently and applies revenue directly to GlobalNations.db holdings.
    # The watch API will use the pre-calculated holdings values from the database.

app.include_router(astrology_api, prefix="/api", tags=["astrology"])

# Mount static files AFTER API routes to ensure API takes precedence
app.mount("/static", StaticFiles(directory="web/static"), name="static")
app.mount("/css", StaticFiles(directory="web/css"), name="css")
app.mount("/js", StaticFiles(directory="web/js"), name="js")
app.mount("/Pages", StaticFiles(directory="web/Pages"), name="pages")
app.mount("/Systems", StaticFiles(directory="Systems"), name="systems")
app.mount("/node_modules", StaticFiles(directory="node_modules"), name="node_modules")

@app.get("/api/access/check")
async def access_check_stub():
    """Stub for removed access control system — always returns full access."""
    return JSONResponse(content={"allowed_pages": []})

@app.get("/api/game-info/resource-prices")
async def get_game_info_resource_prices():
    """Get latest resource prices for game info page."""
    try:
        prices = await db.get_latest_resource_prices()
        if prices is None:
            raise HTTPException(status_code=404, detail="No resource price data found.")
        return JSONResponse(content=prices)
    except Exception as e:
        logger.error(f"Error getting resource prices for game info: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve resource prices.")

@app.get("/api/game-info/debug/resource-count")
async def get_resource_debug_info():
    """Debug endpoint to check resource data in database."""
    try:
        import aiosqlite
        from Systems.Functions.db_paths import REAPER_DB_STR
        DB_FILE = REAPER_DB_STR
        
        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row
            
            # Get total count of records
            cursor = await conn.execute("SELECT COUNT(*) as total FROM resource_prices")
            total_records = (await cursor.fetchone())['total']
            
            # Get distinct resources
            cursor = await conn.execute("SELECT DISTINCT resource FROM resource_prices")
            resources = [row['resource'] for row in await cursor.fetchall()]
            
            # Get latest timestamp
            cursor = await conn.execute("SELECT MAX(timestamp) as latest FROM resource_prices")
            latest_timestamp = (await cursor.fetchone())['latest']
            
            # Get count per resource
            cursor = await conn.execute("""
                SELECT resource, COUNT(*) as count 
                FROM resource_prices 
                GROUP BY resource 
                ORDER BY count DESC
            """)
            resource_counts = {row['resource']: row['count'] for row in await cursor.fetchall()}
            
            return JSONResponse(content={
                "total_records": total_records,
                "distinct_resources": resources,
                "resource_counts": resource_counts,
                "latest_timestamp": latest_timestamp,
                "expected_resources": [r.lower() for r in ["FOOD", "COAL", "OIL", "URANIUM", "LEAD", "IRON", "BAUXITE", "GASOLINE", "MUNITIONS", "STEEL", "ALUMINUM", "CREDIT"]]
            })
    except Exception as e:
        logger.error(f"Error getting debug info: {e}", exc_info=True)
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/api/game-info/resource-prices-comparison")
async def get_game_info_resource_prices_comparison():
    """Get latest and previous resource prices for comparison."""
    try:
        prices = await db.get_resource_prices_comparison()
        if not prices or not prices.get("current"):
            logger.warning("No resource price comparison data found in database.")
            raise HTTPException(status_code=404, detail="No comparison data available.")
        
        # Log the fetched data for debugging
        current_count = len(prices.get('current', {}))
        history_count = len(prices.get('history', {}))
        logger.info(f"Sending resource price data to frontend. Current prices count: {current_count}, History resources: {history_count}")
        
        # Log which resources are available
        current_resources = list(prices.get('current', {}).keys())
        history_resources = list(prices.get('history', {}).keys())
        logger.info(f"Current resources: {current_resources}")
        logger.info(f"History resources: {history_resources}")
        
        return JSONResponse(content=prices)
    except Exception as e:
        logger.error(f"Error getting resource price comparison: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve price comparison data.")

@app.get("/api/game-info/resource-history/{resource}")
async def get_resource_full_history(resource: str):
    """Get the complete buy/sell price history for a single resource (on-demand for chart zoom)."""
    try:
        valid = {"credit","food","uranium","oil","gasoline","lead","munitions","bauxite","aluminum","coal","iron","steel"}
        if resource.lower() not in valid:
            raise HTTPException(status_code=400, detail="Unknown resource.")
        history = await db.get_full_resource_price_history(resource.lower())
        return JSONResponse(content={"resource": resource.lower(), "history": history})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting full resource history for {resource}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve resource history.")

@app.get("/api/game-info/colors-comparison")
async def get_game_info_colors_comparison():
    """Get latest and previous color bonuses for comparison."""
    try:
        colors = await db.get_colors_comparison()
        if not colors:
            raise HTTPException(status_code=404, detail="No color comparison data available.")
        return JSONResponse(content=colors)
    except Exception as e:
        logger.error(f"Error getting color comparison: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve color comparison data.")

@app.get("/api/game-info/colors")
async def get_game_info_colors():
    """Get latest color data for game info page."""
    try:
        color_data = await db.get_latest_game_data("colors")
        if color_data is None:
            raise HTTPException(status_code=404, detail="No color data found.")
        return JSONResponse(content=color_data)
    except Exception as e:
        logger.error(f"Error getting color data for game info: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve color data.")

@app.get("/api/game-info/resource-supply-comparison")
async def get_game_info_resource_supply_comparison():
    """Get latest and previous resource supply data for comparison."""
    try:
        supply_data = await db.get_resource_supply_comparison()
        if not supply_data:
            raise HTTPException(status_code=404, detail="No supply comparison data available.")
        return JSONResponse(content=supply_data)
    except Exception as e:
        logger.error(f"Error getting resource supply comparison: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve supply comparison data.")

async def _get_resource_intelligence_data() -> dict:
    """Helper function to fetch and process resource intelligence data."""
    try:
        prices = await db.get_resource_prices_comparison()
        supply = await db.get_resource_supply_comparison()

        if not prices or not prices.get("current") or not supply or not supply.get("current"):
            return {}

        intelligence_data = {}
        price_ts = prices["current"].get("timestamp", 0)
        supply_ts = supply["current"].get("timestamp", 0)

        # Only proceed if the main timestamps match
        if price_ts == supply_ts:
            for resource, current_price in prices["current"].items():
                if resource == "timestamp": continue

                if resource in supply["current"]:
                    previous_price_data = prices.get("previous", {}).get(resource, {})
                    current_supply = supply["current"][resource]
                    previous_supply = supply.get("previous", {}).get(resource)

                    price_change = 0
                    if previous_price_data and previous_price_data.get('avg', 0) > 0:
                        price_change = (current_price.get('avg', 0) - previous_price_data.get('avg', 0)) / previous_price_data.get('avg', 0)

                    supply_change = 0
                    if previous_supply and previous_supply > 0:
                        supply_change = (previous_supply - current_supply) / previous_supply

                    # Inverted logic: Supply decreases + price increases = SELL (time to cash out)
                    # Supply increases + price decreases = BUY (time to accumulate)
                    intelligence_score = (-price_change * 0.35) + (-supply_change * 0.65)

                    if intelligence_score > 0.02:
                        recommendation, trend = "BUY", "bullish"
                    elif intelligence_score < -0.02:
                        recommendation, trend = "SELL", "bearish"
                    else:
                        recommendation, trend = "HOLD", "neutral"

                    intelligence_data[resource] = {
                "current_price": current_price.get('avg', 0),
                "buy_price": current_price.get('buy', 0),
                "sell_price": current_price.get('sell', 0),
                "previous_price": previous_price_data.get('avg', 0),
                "price_change_percent": price_change * 100,
                "current_supply": current_supply,
                "previous_supply": previous_supply,
                "supply_change_percent": supply_change * 100,
                "intelligence_score": intelligence_score * 100,
                "recommendation": recommendation,
                "trend": trend,
                "price_history": prices.get("history", {}).get(resource, []),
                "supply_history": supply.get("history", {}).get(resource, []),
            }

        return {
            "intelligence": intelligence_data,
            "last_updated": price_ts
        }
    except Exception as e:
        logger.error(f"Error generating resource intelligence data: {e}")
        return {}

@app.get("/api/game-info/resource-intelligence")
async def get_resource_intelligence():
    """Get comprehensive resource intelligence data including prices, supply, and predictions."""
    data = await _get_resource_intelligence_data()
    if not data or not data.get("intelligence"):
        raise HTTPException(status_code=404, detail="Insufficient data for intelligence analysis. Timestamps for price and supply may not match.")
    return JSONResponse(content=data)

# --- WebSocket for Live Updates ---

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws/resource-updates")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

async def broadcast_updates():
    """Periodically checks for new data and broadcasts it to all connected clients."""
    last_known_timestamp = 0
    while True:
        await asyncio.sleep(10) # Check every 10 seconds
        try:
            current_timestamp = await db.get_latest_resource_timestamp()
            if current_timestamp > last_known_timestamp:
                logger.info(f"New resource data found (timestamp: {current_timestamp}). Fetching and broadcasting update.")
                last_known_timestamp = current_timestamp
                
                intelligence_data = await _get_resource_intelligence_data()
                if intelligence_data and intelligence_data.get("intelligence"):
                    await manager.broadcast(json.dumps(intelligence_data))
        except Exception as e:
            logger.error(f"Error in broadcast_updates: {e}", exc_info=True)


import hashlib as _hashlib

# Pre-compute ETag cache — recomputed once per hour, not per request
_etag_cache: dict = {}

def _get_etag(path: str) -> str:
    hour = int(time.time() // 3600)
    key = (path, hour)
    if key not in _etag_cache:
        _etag_cache.clear()  # drop stale entries
        _etag_cache[key] = _hashlib.md5(f"{path}_{hour}".encode()).hexdigest()[:8]
    return _etag_cache[key]

# Pre-compute the static CSP header string once
_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' "
        "https://cdn.jsdelivr.net https://static.cloudflareinsights.com https://unpkg.com "
        "https://fonts.googleapis.com; worker-src 'self' blob:; style-src 'self' 'unsafe-inline' "
        "https://fonts.googleapis.com https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        "style-src-elem 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com "
        "https://cdnjs.cloudflare.com; font-src 'self' https://fonts.gstatic.com "
        "https://cdnjs.cloudflare.com; img-src 'self' data: https://cdn.discordapp.com "
        "https://media.discordapp.net https://reaper.qzz.io https://politicsandwar.com "
        "https://upload.wikimedia.org; connect-src 'self' https://reaper.qzz.io "
        "https://cdn.jsdelivr.net https://unpkg.com https://fonts.googleapis.com "
        "https://cdnjs.cloudflare.com https://api.groq.com;")

# Add request logging and security headers middleware
@app.middleware("http")
async def add_headers_and_log_requests(request, call_next):
    path = request.url.path
    is_static = path.startswith(("/static/", "/css/", "/js/", "/Pages/"))

    response = await call_next(request)

    # Security headers (always)
    h = response.headers
    h["Content-Security-Policy"] = _CSP
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["X-XSS-Protection"] = "1; mode=block"
    h["Strict-Transport-Security"] = "max-age=15768000; includeSubDomains"

    if path.endswith(".wasm"):
        h["Content-Type"] = "application/wasm"

    # Cache-control with DEV_MODE support
    pl = path.lower()
    
    # Development mode: bypass all caching
    if DEV_MODE:
        h["Cache-Control"] = "no-cache, no-store, must-revalidate"
        h["Pragma"] = "no-cache"
        h["Expires"] = "0"
        h["CF-Cache-Status"] = "BYPASS"
    else:
        # Production mode: optimal caching
        if pl.startswith(("/static/images/", "/static/fonts/", "/static/icons/")):
            h["Cache-Control"] = "public, max-age=3600, must-revalidate"
            h["CF-Cache-Tag"] = "static-assets"
        elif pl.startswith(("/css/", "/js/")) or pl.endswith((".css", ".js")):
            h["Cache-Control"] = "public, max-age=3600, must-revalidate"
            h["CF-Cache-Tag"] = "stylesheets-scripts"
            h["ETag"] = f'"{_get_etag(pl)}"'
        elif pl.startswith("/pages/") or pl.endswith(".html"):
            h["Cache-Control"] = "no-cache, no-store, must-revalidate"
            h["Pragma"] = "no-cache"
            h["Expires"] = "0"
            h["CF-Cache-Tag"] = "html-pages"
        elif pl.startswith("/api/"):
            h["Cache-Control"] = "no-cache, no-store, must-revalidate"
            h["Pragma"] = "no-cache"
            h["Expires"] = "0"
        elif pl in ("/", "/dashboard", "/dashboard.html"):
            h["Cache-Control"] = "no-cache, no-store, must-revalidate"
            h["Pragma"] = "no-cache"
            h["Expires"] = "0"
        elif is_static:
            h["Cache-Control"] = "public, max-age=300, must-revalidate"
            h["CF-Cache-Tag"] = "misc-static"

        if pl.startswith(("/api/", "/dashboard")) or pl.endswith(".html"):
            h["CF-Cache-Status"] = "BYPASS"

    return response

@app.exception_handler(404)
async def not_found_exception_handler(request, exc):
    """Custom 404 — JSON for API routes, HTML page for everything else."""
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Not found"}, status_code=404)
    return FileResponse("web/static/404.html", status_code=404)

@app.exception_handler(500)
async def internal_server_error_handler(request, exc):
    """Custom 500 — JSON for API routes, HTML page for everything else."""
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Internal server error"}, status_code=500)
    return FileResponse("web/static/500.html", status_code=500)


@app.get("/library", response_class=HTMLResponse)
async def get_library_page():
    """Serve the main library page."""
    return FileResponse("web/Pages/library.html")

@app.get("/news", response_class=HTMLResponse)
async def get_news_page():
    """Serve the PnW News page."""
    return FileResponse("web/Pages/news.html")

@app.get("/casino", response_class=HTMLResponse)
async def get_casino_page():
    """Serve the casino page."""
    return FileResponse("web/Pages/casino.html")


logger = logging.getLogger("Reaper.WebServer")

@app.get("/health")
async def health_check():
    """A simple health check endpoint to confirm the server is responsive."""
    return JSONResponse(content={"status": "ok"})

# Add request logging middleware
_server_instance: uvicorn.Server = None


# Cache dashboard HTML at module load time — no file I/O on every request
_DASHBOARD_PATH = os.path.abspath(os.path.join("web", "dashboard.html"))
_dashboard_html: str = ""
try:
    with open(_DASHBOARD_PATH, "r", encoding="utf-8", errors="replace") as _f:
        _dashboard_html = _f.read()
except Exception as _e:
    logger.warning(f"Could not pre-load dashboard.html: {_e}")

# Serve homepage at root path (highest priority)
@app.get("/", response_class=HTMLResponse)
async def read_root():
    if not _dashboard_html:
        return HTMLResponse(content="Dashboard not found", status_code=404)
    return HTMLResponse(content=_dashboard_html, status_code=200)

# Serve dashboard at /dashboard path
@app.get("/dashboard", response_class=HTMLResponse)
async def read_dashboard():
    if not _dashboard_html:
        return HTMLResponse(content="Dashboard not found", status_code=404)
    return HTMLResponse(content=_dashboard_html, status_code=200)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serves the favicon."""
    return FileResponse("web/static/Images/reaper.png")


@app.get("/.well-known/security.txt", include_in_schema=False)
async def security_txt():
    """Serves the security.txt file per RFC 9116."""
    content = (
        "Contact: mailto:cody.ray.inc@gmail.com\n"
        "Expires: 2027-01-01T00:00:00.000Z\n"
        "Preferred-Languages: en\n"
        "Canonical: https://reaper.qzz.io/.well-known/security.txt\n"
    )
    return Response(content=content, media_type="text/plain")


@app.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    """
    Serves robots.txt to control crawler access.
    - Blocks all bots from API endpoints and admin pages (no crawl value, saves bandwidth).
    - Allows legitimate search engines full access to public pages.
    - Everything not explicitly disallowed is crawlable so the site works normally.
    """
    content = (
        "# Reaper Bot — robots.txt\n"
        "# Block generic bots from internal/API paths\n"
        "User-agent: *\n"
        "Disallow: /api/\n"
        "Disallow: /admin\n"
        "Disallow: /admin/\n"
        "Disallow: /.well-known/\n"
        "Disallow: /ws\n"
        "Allow: /\n"
        "\n"
        "# Allow major search engines full access to public pages\n"
        "User-agent: Googlebot\n"
        "Allow: /\n"
        "\n"
        "User-agent: Bingbot\n"
        "Allow: /\n"
        "\n"
        "# Sitemap\n"
        "Sitemap: https://reaper.qzz.io/sitemap.xml\n"
    )
    return Response(content=content, media_type="text/plain")


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml():
    """Serves sitemap.xml for search engine crawlers and Cloudflare."""
    return FileResponse("sitemap.xml", media_type="application/xml")


# Serve individual HTML pages — Pages are served as static files via StaticFiles mount,
# but these routes handle {{PUBLIC_URL}} injection. Cache pages in memory.
_page_cache: dict = {}

def _read_page_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/{page_name}.html", response_class=HTMLResponse)
async def read_page(page_name: str):
    """Serve individual HTML pages from the web directory."""
    # Check web directory first
    file_path = os.path.join("web", f"{page_name}.html")
    if not os.path.exists(file_path):
        # Check Pages directory
        file_path = os.path.join("web", "Pages", f"{page_name}.html")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Page {page_name}.html not found")
    if file_path not in _page_cache:
        _page_cache[file_path] = _read_page_file(file_path)
    public_url = get_web_public_url()
    return HTMLResponse(content=_page_cache[file_path].replace("{{PUBLIC_URL}}", public_url))

@app.get("/Pages/{page_name}.html", response_class=HTMLResponse)
async def read_sub_page(page_name: str):
    """Serve individual HTML pages from the web/Pages directory."""
    file_path = os.path.join("web", "Pages", f"{page_name}.html")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Page {page_name}.html not found")
    if file_path not in _page_cache:
        _page_cache[file_path] = await asyncio.to_thread(_read_page_file, file_path)
    public_url = get_web_public_url()
    return HTMLResponse(content=_page_cache[file_path].replace("{{PUBLIC_URL}}", public_url))

# API routes
@app.get("/api/emoji-data")
async def get_emoji_data():
    """Get all emoji data for the fun page."""
    try:
        from Systems.Functions.emoji import EMOJI_IDS, ANIMATED_EMOJI_IDS, CATEGORIES, mention
        
        # Build emoji data dictionary with local file paths
        emoji_data = {}
        
        # Dice emojis - map directly to file paths
        dice_colors = ["Red", "Orange", "Blue", "Yellow", "Pink", "Green", "Purple"]
        for color in dice_colors:
            for num in range(1, 7):
                emoji_name = f"{color}{num}"
                emoji_data[emoji_name] = f"/static/Emojis/Dice/{emoji_name}.png"
        
        # Card emojis
        card_types = {
            "Hearts": ["H1","H2","H3","H4","H5","H6","H7","H8","H9","H10","HJ","HQ","HK"],
            "Diamonds": ["D1","D2","D3","D4","D5","D6","D7","D8","D9","D10","DJ","DQ","DK"],
            "Clubs": ["C1","C2","C3","C4","C5","C6","C7","C8","C9","C10","CJ","CQ","CK"],
            "Spades": ["S1","S2","S3","S4","S5","S6","S7","S8","S9","S10","SJ","SQ","SK"],
            "Jokers": ["LJ","BJ"]
        }
        for suit, cards in card_types.items():
            for card in cards:
                emoji_data[card] = f"/static/Emojis/Cards/{card}.png"
        
        # Coin emojis (using existing Discord emoji IDs if available, otherwise fallback)
        coin_emojis = ["Pirate", "Poop", "Future", "Retro", "Full", "Empty", "Plug", "Socket", "Open", "Close", "Day", "Night", "Hot", "Cold"]
        for coin in coin_emojis:
            if coin in EMOJI_IDS:
                emoji_data[coin] = f"/static/Emojis/Coins/{coin}.png"
        
        # Globe emojis
        globe_emojis = ["africa", "antarctica", "asia", "australia", "europe", "north", "south"]
        for globe in globe_emojis:
            emoji_data[globe] = f"/static/Emojis/Globe/{globe}.png"
        
        # Add all slot-relevant emojis
        slot_categories = {
            "Pets": "/static/Emojis/Pets/",
            "Pet Type": "/static/Emojis/Pets/Deco/",
            "Stats": "/static/Emojis/Pets/Deco/",
            "Elements": "/static/Emojis/Pets/Deco/",
            "Military": "/static/Emojis/Military/",
            "Hats": "/static/Emojis/Pets/Equipment/Hats/",
            "Gems": "/static/Emojis/Pets/Equipment/Gems/",
            "Materials": "/static/Emojis/Pets/Equipment/Materials/",
            "Monsters": "/static/Emojis/Pets/Equipment/Monsters/",
            "Loot": "/static/Emojis/Pets/Equipment/",
            "Potions": "/static/Emojis/Pets/Equipment/Potions/"
        }

        for category, path in slot_categories.items():
            if category in CATEGORIES:
                for emoji_name in CATEGORIES[category]:
                    emoji_data[emoji_name] = f"{path}{emoji_name}.png"
        
        # Add categories for reference
        emoji_categories = {}
        for category, names in CATEGORIES.items():
            emoji_categories[category] = names
        
        return JSONResponse(content={
            "emojis": emoji_data,
            "categories": emoji_categories
        })
    except Exception as e:
        logger.error(f"Error fetching emoji data: {e}")
        return JSONResponse(content={"error": "Failed to fetch emoji data"}, status_code=500)

@app.get("/api/fun/coin-flip")
async def coin_flip(theme: str):
    """Simulate a coin flip with the given theme."""
    try:
        import random
        
        # Define coin themes mapping (matching fun_system.py)
        coin_themes = {
            "Raider": {"heads": "Pirate", "tails": "Poop"},
            "Time": {"heads": "Future", "tails": "Retro"},
            "Battery": {"heads": "Full", "tails": "Empty"},
            "Electric": {"heads": "Plug", "tails": "Socket"},
            "Business": {"heads": "Open", "tails": "Close"},
            "Sky": {"heads": "Day", "tails": "Night"},
            "Tempature": {"heads": "Hot", "tails": "Cold"}
        }
        
        if theme not in coin_themes:
            return JSONResponse(content={"error": "Invalid theme"}, status_code=400)
        
        # Random flip
        is_heads = random.random() < 0.5
        theme_data = coin_themes[theme]
        result_emoji = f"/static/Emojis/Coins/{theme_data['heads'] if is_heads else theme_data['tails']}.png"
        
        return JSONResponse(content={
            "result": "heads" if is_heads else "tails",
            "emoji": result_emoji,
            "theme": theme
        })
    except Exception as e:
        logger.error(f"Error in coin flip: {e}")
        return JSONResponse(content={"error": "Failed to flip coin"}, status_code=500)



@app.get("/api/fun/card-draw")
async def card_draw(count: int):
    """Draw cards with given count."""
    try:
        import random
        
        # Validate count
        if count < 1 or count > 5:
            return JSONResponse(content={"error": "Count must be between 1-5"}, status_code=400)
        
        # Get all available cards
        all_cards = []
        suits = {
            "Hearts": ["H1","H2","H3","H4","H5","H6","H7","H8","H9","H10","HJ","HQ","HK"],
            "Diamonds": ["D1","D2","D3","D4","D5","D6","D7","D8","D9","D10","DJ","DQ","DK"],
            "Clubs": ["C1","C2","C3","C4","C5","C6","C7","C8","C9","C10","CJ","CQ","CK"],
            "Spades": ["S1","S2","S3","S4","S5","S6","S7","S8","S9","S10","SJ","SQ","SK"],
            "Jokers": ["LJ","BJ"]
        }
        
        for suit_name, cards in suits.items():
            for card in cards:
                all_cards.append({
                    "card": card,
                    "suit": suit_name,
                    "emoji": f"/static/Emojis/Cards/{card}.png"
                })
        
        # Shuffle and draw
        shuffled = random.sample(all_cards, len(all_cards))
        drawn = shuffled[:count]
        
        return JSONResponse(content={
            "cards": drawn,
            "count": count
        })
    except Exception as e:
        logger.error(f"Error in card draw: {e}")
        return JSONResponse(content={"error": "Failed to draw cards"}, status_code=500)

@app.get("/api/fun/rps")
async def rps_game(theme: str, player_choice: str):
    """Play Rock Paper Scissors with AI opponent."""
    try:
        import random
        
        # Define RPS themes mapping
        rps_themes = {
            "Traditional": {
                "rock_1": {"name": "Rock", "beats": "scissor", "emoji": "/static/Emojis/RPS/rock_1.png"},
                "paper": {"name": "Paper", "beats": "rock_1", "emoji": "/static/Emojis/RPS/paper.png"},
                "scissor": {"name": "Scissors", "beats": "paper", "emoji": "/static/Emojis/RPS/scissor.png"}
            },
            "Fantasy": {
                "knights": {"name": "Knight", "beats": "necromancer", "emoji": "/static/Emojis/RPS/knights.png"},
                "archer": {"name": "Archer", "beats": "knights", "emoji": "/static/Emojis/RPS/archer.png"},
                "necromancer": {"name": "Necromancer", "beats": "archer", "emoji": "/static/Emojis/RPS/necromancer.png"}
            },
            "War": {
                "tank": {"name": "Tank", "beats": "ship", "emoji": "/static/Emojis/RPS/tank.png"},
                "jet": {"name": "Jet", "beats": "tank", "emoji": "/static/Emojis/RPS/jet.png"},
                "ship": {"name": "Ship", "beats": "jet", "emoji": "/static/Emojis/RPS/ship.png"}
            }
        }
        
        # Validate theme
        if theme not in rps_themes:
            return JSONResponse(content={"error": "Invalid theme"}, status_code=400)
        
        # Validate player choice
        theme_choices = rps_themes[theme]
        if player_choice not in theme_choices:
            return JSONResponse(content={"error": "Invalid choice for theme"}, status_code=400)
        
        # AI makes random choice
        ai_choice = random.choice(list(theme_choices.keys()))
        
        # Determine winner
        player_data = theme_choices[player_choice]
        ai_data = theme_choices[ai_choice]
        
        if player_choice == ai_choice:
            result = "tie"
            outcome = "It's a tie!"
        elif player_data["beats"] == ai_choice:
            result = "win"
            outcome = "You win!"
        else:
            result = "lose"
            outcome = "AI wins!"
        
        return JSONResponse(content={
            "result": result,
            "outcome": outcome,
            "player_choice": player_choice,
            "player_emoji": player_data["emoji"],
            "player_name": player_data["name"],
            "ai_choice": ai_choice,
            "ai_emoji": ai_data["emoji"],
            "ai_name": ai_data["name"],
            "theme": theme
        })
    except Exception as e:
        logger.error(f"Error in RPS game: {e}")
        return JSONResponse(content={"error": "Failed to play RPS"}, status_code=500)


@app.get("/api/test")
async def test_endpoint():
    """Test endpoint to verify server is picking up changes."""
    return JSONResponse(content={"message": "Test endpoint working", "timestamp": str(datetime.now())})

@app.get("/api/commands", response_class=JSONResponse)
async def get_commands():
    """Provides a list of all application commands."""
    if not _bot_instance:
        logger.error("Command API called before bot instance was ready.")
        raise HTTPException(status_code=503, detail="Bot is not ready.")

    # Cache the command list — fetch_commands() hits Discord's API once per
    # global scope + once per guild. With no cache this fires N+1 API calls
    # on every single page load, which is a major source of rate limiting.
    import time as _time
    _cache = get_commands._cache  # type: ignore[attr-defined]
    if _cache["data"] is not None and (_time.monotonic() - _cache["fetched_at"]) < 300:
        return _cache["data"]

    try:
        commands_list = []
        seen_commands = set() # To avoid duplicates

        # Helper function to process a command and add it to the list
        def process_command(command, guild_name=None):
            # For hybrid commands, get the cog name from the underlying command object
            cog = command.cog if hasattr(command, 'cog') else None
            if isinstance(command, discord.ext.commands.HybridCommand):
                cog = command.app_command.cog

            command_id = f"{command.name}_{guild_name or 'global'}"
            if command_id in seen_commands:
                return # Skip duplicates
            seen_commands.add(command_id)

            command_info = {
                "name": command.name,
                "category": cog.qualified_name if cog else (guild_name or "General"),
            }
            # Handle different command types gracefully
            if isinstance(command, discord.app_commands.AppCommand):
                command_info.update({
                    "description": command.description or "(No description)",
                    "usage": f"/{command.name}",
                    "params": []
                })
                
                # Try to get parameters if available (some command types may not have them)
                try:
                    if hasattr(command, 'options') and command.options:
                        command_info["params"] = [
                            {
                                "name": option.name,
                                "description": option.description or "(No description)",
                                "required": option.required,
                                "default": str(option.default) if hasattr(option, 'default') and option.default is not None else None,
                                "choices": [choice.name for choice in option.choices] if hasattr(option, 'choices') and option.choices else []
                            } for option in command.options
                        ]
                    elif hasattr(command, 'parameters') and command.parameters:
                        command_info["params"] = [
                            {
                                "name": param.name,
                                "description": param.description or "(No description)",
                                "required": param.required,
                                "default": str(param.default) if param.default is not None else None,
                                "choices": [choice.name for choice in param.choices] if param.choices else []
                            } for param in command.parameters
                        ]
                except AttributeError:
                    # If we can't get parameters, just leave params as empty list
                    pass
            elif isinstance(command, discord.app_commands.ContextMenu):
                # Context menu commands don't have descriptions or parameters
                command_info.update({
                    "description": f"Context menu command ({command.type.name.title()})",
                    "usage": f"(Right-click on a {command.type.name.lower()}) -> Apps -> {command.name}",
                    "params": []
                })
            else:
                # Skip unknown command types
                return

            commands_list.append(command_info)

        # 1. Get Global Commands
        global_commands = await _bot_instance.tree.fetch_commands()
        for command in global_commands:
            process_command(command)

        # 2. Get Guild-specific Commands
        for guild in _bot_instance.guilds:
            try:
                guild_commands = await _bot_instance.tree.fetch_commands(guild=guild)
                for command in guild_commands:
                    process_command(command, guild.name)
            except discord.errors.Forbidden:
                logger.warning(f"Missing permissions to fetch commands for guild: {guild.name} (ID: {guild.id})")
            except Exception as e:
                logger.error(f"Error fetching commands for guild {guild.name} (ID: {guild.id}): {e}")

        logger.info(f"Successfully fetched {len(commands_list)} commands via API.")
        _cache["data"] = commands_list
        _cache["fetched_at"] = _time.monotonic()
        return commands_list

    except Exception as e:
        logger.error(f"Error fetching commands for API: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# Attach cache state directly to the function object so it persists across calls
get_commands._cache = {"data": None, "fetched_at": 0.0}  # type: ignore[attr-defined]

@app.get("/api/pnw/resource-prices")
async def get_pnw_resource_prices():
    """Get PnW resource prices from reaper.db."""
    try:
        import aiosqlite
        from Systems.Functions.db_paths import REAPER_DB_STR
        DB_FILE = REAPER_DB_STR

        async with aiosqlite.connect(DB_FILE) as conn:
            conn.row_factory = aiosqlite.Row

            # Get the most recent timestamp
            cursor = await conn.execute("SELECT timestamp FROM resource_prices ORDER BY timestamp DESC LIMIT 1")
            latest_timestamp = await cursor.fetchone()
            
            if not latest_timestamp:
                return JSONResponse(content={"error": "No resource price data available"}, status_code=404)
            
            # Get all resources for the latest timestamp
            cursor = await conn.execute(
                "SELECT resource, avg_price, best_buy_price, best_sell_price FROM resource_prices WHERE timestamp = ?",
                (latest_timestamp['timestamp'],)
            )
            rows = await cursor.fetchall()
            
            # Format the data to match what the web calculator expects
            data = {}
            for row in rows:
                data[row['resource']] = {
                    'avg': row['avg_price'],
                    'buy': row['best_buy_price'],
                    'sell': row['best_sell_price']
                }
            
            return JSONResponse(content={
                "data": data,
                "timestamp": latest_timestamp['timestamp']
            })
            
    except Exception as e:
        logger.error(f"Error getting resource prices from reaper.db: {e}")
        return JSONResponse(content={"error": "Failed to retrieve resource prices"}, status_code=500)

@app.get("/api/pnw/game-info")
async def get_pnw_game_info():
    """Get PnW game info."""
    try:
        query_instance = create_v3_query_instance()
        game_info = await query_instance.get_game_info()
        return JSONResponse(content=game_info)
    except Exception as e:
        logger.error(f"Error getting game info: {e}")
        return JSONResponse(content={"error": "Failed to retrieve game info"}, status_code=500)

@app.get("/api/discord/linked-nation")
async def get_linked_nation(request: Request):
    """Get the PnW nation linked to the current Discord user.
    Looks up the user's Discord ID in IRSNations.db and GlobalNations.db.
    """
    try:
        # Get Discord user from session
        discord_user = request.session.get('discord_user')
        if not discord_user:
            return JSONResponse(content={"linked": False, "error": "Not logged in"}, status_code=401)
        
        discord_id = str(discord_user.get('id'))
        if not discord_id:
            return JSONResponse(content={"linked": False, "error": "No Discord ID found"}, status_code=400)
        
        from Systems.Functions.db_paths import GLOBAL_NATIONS_DB_STR
        from PnWHarvester.db.global_nations_db import GlobalNationsDB

        # GlobalNations.db is the single source of truth — NW nations are stored here too
        def _search_by_discord_id(db_path: str, discord_id: str):
            import sqlite3 as _sq
            with _sq.connect(db_path) as conn:
                conn.row_factory = _sq.Row
                row = conn.execute(
                    "SELECT id, nation_name FROM nations WHERE discord_id = ?",
                    (discord_id,)
                ).fetchone()
                return dict(row) if row else None

        nation_data = await asyncio.to_thread(_search_by_discord_id, GLOBAL_NATIONS_DB_STR, discord_id)
        
        if nation_data:
            return JSONResponse(content={
                "linked": True,
                "nation_id": nation_data["id"],
                "nation_name": nation_data["nation_name"]
            })
        else:
            return JSONResponse(content={"linked": False, "message": "No nation linked to this Discord account"})
    
    except Exception as e:
        logger.error(f"Error getting linked nation: {e}", exc_info=True)
        return JSONResponse(content={"linked": False, "error": "Failed to retrieve linked nation"}, status_code=500)


@app.get("/api/pnw/nation-info/{nation_query}")
async def get_pnw_nation_info(nation_query: str):
    """Get PnW nation info for the calculator.
    Reads from GlobalNations.db (single source of truth — includes NW nations).
    Never queries the live API.
    """
    try:
        from Systems.Functions.db_paths import GLOBAL_NATIONS_DB_STR
        from PnWHarvester.db.global_nations_db import GlobalNationsDB

        nation_data = None
        cities = []

        global_db = GlobalNationsDB(GLOBAL_NATIONS_DB_STR)
        if nation_query.isdigit():
            nation_data = await global_db.get_nation(int(nation_query))
            if nation_data:
                cities = await global_db.get_cities_for_nation(int(nation_query))
        else:
            nation_data = await global_db.get_nation_by_name(nation_query)
            if nation_data:
                cities = await global_db.get_cities_for_nation(nation_data["id"])

        if nation_data:
            # Parse military_research JSON if it's a string
            mr = nation_data.get("military_research")
            if isinstance(mr, str):
                try:
                    import json as _json
                    nation_data["military_research"] = _json.loads(mr)
                except Exception:
                    nation_data["military_research"] = None

            nation_data["cities"] = cities
            nation_data["_source"] = "global_nations_db"
            return JSONResponse(content=nation_data)

        # --- Nation not found in DB ---
        return JSONResponse(content={"error": "Nation not found in database"}, status_code=404)

    except Exception as e:
        logger.error(f"Error getting nation info for '{nation_query}': {e}", exc_info=True)
        return JSONResponse(content={"error": "Failed to retrieve nation info"}, status_code=500)

# Catch-all route for any remaining paths
@app.get("/{path:path}", response_class=HTMLResponse)
async def catch_all(path: str):
    """Catch-all route that redirects to dashboard for unknown paths."""
    # Don't redirect API calls, static files, or Systems files
    if path.startswith("api/") or path.startswith("Systems/"):
        return HTMLResponse(content="Not found", status_code=404)
    
    # Also don't redirect if the path contains a dot (likely a file) or is empty
    if not path or "." in path:
        return HTMLResponse(content="Not found", status_code=404)
    
    # Don't redirect if path looks like an API endpoint (contains hyphens, underscores, or 'astrology')
    if '-' in path or '_' in path or 'astrology' in path.lower():
        return HTMLResponse(content="Not found", status_code=404)

    # Silently 404 numeric-only paths — these are scanner/bot probes, not real navigation
    if path.isdigit():
        return HTMLResponse(content="Not found", status_code=404)

    logger.info(f"Redirecting unknown path '/{path}' to dashboard")
    return RedirectResponse(url="/")



# Web server startup and shutdown functions
async def run_web_server(bot: commands.Bot):
    """Start the web server and optionally Cloudflare tunnel."""
    global _bot_instance, _server_instance
    _bot_instance = bot

    # Initialize service ports first
    from Systems.Functions.utils import initialize_service_ports
    initialize_service_ports()

    # Set bot instance in bot_info_api module before including router
    from web.api.bot_info import set_bot_instance as set_bot_info_instance
    set_bot_info_instance(bot)

    # Set bot instance in stats_api module
    from web.api.stats_api import set_bot_instance as set_stats_instance
    set_stats_instance(bot)

    port = get_service_port(SERVICE_WEB_SERVER)
    
    # Ensure the port is free before starting the server
    kill_process_on_port(port)

    # Multi-worker configuration for production (single worker in DEV_MODE)
    workers = 1 if DEV_MODE else 4
    config = uvicorn.Config(
        app, 
        host="0.0.0.0", 
        port=port, 
        log_level="info",
        workers=workers,
        limit_concurrency=1000,
        timeout_keep_alive=30
    )
    _server_instance = uvicorn.Server(config)
    
    logger.info(f"Starting web server on port {port} with {workers} worker(s)")

    # Start the server directly without creating additional tasks
    await _server_instance.serve()

async def shutdown_web_server():
    """Shutdown the web server and optionally Cloudflare tunnel gracefully."""
    global _server_instance
    if _server_instance:
        logger.info("Shutting down web server...")
        _server_instance.should_exit = True
        _server_instance = None
    
    # Stop Cloudflare tunnel if enabled
    from Systems.Functions.config import USE_CLOUDFLARE_TUNNEL
    if USE_CLOUDFLARE_TUNNEL:
        try:
            await stop_cloudflare_tunnel_async()
        except Exception as e:
            logger.error(f"Error stopping Cloudflare tunnel: {e}")

# Rock Paper Scissors API routes
class RPSRequest(BaseModel):
    theme: str
    playerChoice: str
    playerHistory: List[str] = []

def determine_rps_winner(player_choice: str, ai_choice: str, theme: str) -> str:
    """Determine the winner of RPS game."""
    if player_choice == ai_choice:
        return "tie"
    
    # Define winning combinations for each theme
    winning_combinations = {
        "Traditional": {
            "rock_1": "scissor",
            "paper": "rock_1", 
            "scissor": "paper"
        },
        "Fantasy": {
            "knights": "archer",
            "archer": "necromancer",
            "necromancer": "knights"
        },
        "War": {
            "tank": "ship",
            "jet": "tank",
            "ship": "jet"
        }
    }
    
    # Get the winning combinations for the current theme
    theme_combinations = winning_combinations.get(theme, winning_combinations["Traditional"])
    
    # Check if player's choice beats AI's choice
    if theme_combinations.get(player_choice) == ai_choice:
        return "player"
    else:
        return "ai"

@app.post("/api/fun/rps-play")
async def rps_play(request: RPSRequest):
    """Handle Rock Paper Scissors game play against AI."""
    try:
        # Get AI choice using the existing AI brain
        ai_choice = get_ai_choice(request.theme, request.playerHistory)
        
        # Determine winner
        winner = determine_rps_winner(request.playerChoice, ai_choice, request.theme)
        
        return JSONResponse({
            "aiChoice": ai_choice,
            "winner": winner,
            "theme": request.theme
        })
    except Exception as e:
        logger.error(f"Error in RPS play: {e}")
        return JSONResponse(
            content={"error": "Internal server error"},
            status_code=500
        )

# Main execution block for standalone server
if __name__ == "__main__":
    import asyncio
    
    async def run_standalone_server():
        """Run the web server without a bot instance."""
        port = get_service_port(SERVICE_WEB_SERVER)
        
        # Ensure the port is free
        kill_process_on_port(port)
        
        # Start Cloudflare tunnel
        await start_cloudflare_tunnel_async()

        config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
        server = uvicorn.Server(config)
        
        logger.info(f"Starting standalone web server on port {port}")
        await server.serve()
    
    # Run the standalone server
    try:
        asyncio.run(run_standalone_server())
    except KeyboardInterrupt:
        logger.info("Web server shut down by user.")

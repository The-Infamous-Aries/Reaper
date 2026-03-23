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

# Third-Party Imports
import discord
import httpx
import psutil
import uvicorn
from discord.ext import commands
from fastapi import FastAPI, HTTPException
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse, Response, StreamingResponse)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Add project root to path to allow for clean imports
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

# Local Application Imports
import Systems.Functions.json_database as db
from Systems.Astrology import reading
from Systems.Functions.ai_brain import get_ai_choice
from Systems.Functions.graph_utils import (CREDIT_RESOURCES, FOOD_RESOURCES,
                                           MAN_RESOURCES, RAW_RESOURCES,
                                           _prepare_dataframe,
                                           create_stock_graph)
from Systems.Functions.utils import (SERVICE_WEB_SERVER, get_service_port,
                                     kill_process_on_port)
from Systems.PnW.Util.Graphs.compare_graph import \
    create_interactive_comparison_page
from Systems.PnW.Util.Graphs.treaty_graph import TreatyGraph
from Systems.PnW.Util.Graphs.war_graph import war_graph_generator
from Systems.PnW.Util.Graphs.war_graph_net_bd import \
    war_net_breakdown_graph_generator
from Systems.PnW.Util.query import (create_v3_query_instance,
                                    get_all_treaties, get_game_info,
                                    get_nation_by_id, get_nation_by_name,
                                    get_wars)
from Systems.PnW.Util.war_calc import calculate_war_costs, get_resource_prices
from web.api.fun_slots import fun_slots_api


# Request models
class AstrologyRequest(BaseModel):
    month: int
    day: int
    year: int

app = FastAPI()

@app.exception_handler(404)
async def not_found_exception_handler(request, exc):
    """Custom 404 page."""
    return FileResponse("web/404.html", status_code=404)

@app.exception_handler(500)
async def internal_server_error_handler(request, exc):
    """Custom 500 page."""
    return FileResponse("web/500.html", status_code=500)
app.include_router(fun_slots_api)

# Mount static files to serve images, CSS, and JavaScript
app.mount("/web", StaticFiles(directory="web"), name="web")
app.mount("/Systems", StaticFiles(directory="Systems"), name="systems")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Reaper.WebServer")

# Add request logging middleware
@app.middleware("http")
async def log_requests(request, call_next):
    logger.info(f"Incoming request: {request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"Response: {response.status_code} for {request.method} {request.url.path}")
    return response
_bot_instance: commands.Bot = None
_server_instance: uvicorn.Server = None


# Serve dashboard at root path (highest priority)
@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the main dashboard at root path."""
    try:
        dashboard_path = os.path.join("web", "dashboard.html")
        if not os.path.exists(dashboard_path):
            logger.error(f"Dashboard file not found at {dashboard_path}")
            return HTMLResponse(content="Dashboard not found", status_code=404)
        
        with open(dashboard_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        
        logger.info("Successfully served dashboard at root path")
        return HTMLResponse(content=html_content, status_code=200)
    except Exception as e:
        logger.error(f"Error loading dashboard: {e}")
        return HTMLResponse(content=f"Error loading dashboard: {str(e)}", status_code=500)

# Redirect /dashboard to root
@app.get("/dashboard", response_class=HTMLResponse)
async def read_dashboard():
    """Redirect /dashboard to root path."""
    return RedirectResponse(url="/")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serves the favicon."""
    return FileResponse("web/reaper.png")


# Serve individual HTML pages
@app.get("/{page_name}.html", response_class=HTMLResponse)
async def read_page(page_name: str):
    """Serve individual HTML pages from the web directory."""
    try:
        file_path = os.path.join("web", f"{page_name}.html")
        if not os.path.exists(file_path):
            logger.warning(f"Page {page_name}.html not found at {file_path}")
            raise HTTPException(status_code=404, detail=f"Page {page_name}.html not found")
        
        with open(file_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        
        logger.info(f"Successfully served page: {page_name}.html")
        return HTMLResponse(content=html_content, status_code=200)
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}", exc_info=True)
        raise HTTPException(status_code=404, detail=f"Page {page_name}.html not found")
    except Exception as e:
        logger.error(f"Error loading page {page_name}.html: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error loading page: {page_name}.html")

# Serve pages from the Pages subdirectory
@app.get("/Pages/{page_name}.html", response_class=HTMLResponse)
async def read_sub_page(page_name: str):
    """Serve individual HTML pages from the web/Pages directory."""
    try:
        file_path = os.path.join("web", "Pages", f"{page_name}.html")
        if not os.path.exists(file_path):
            logger.warning(f"Page {page_name}.html not found in Pages directory at {file_path}")
            raise HTTPException(status_code=404, detail=f"Page {page_name}.html not found")
        
        with open(file_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        
        logger.info(f"Successfully served page from Pages directory: {page_name}.html")
        return HTMLResponse(content=html_content, status_code=200)
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}", exc_info=True)
        raise HTTPException(status_code=404, detail=f"Page {page_name}.html not found")
    except Exception as e:
        logger.error(f"Error loading page {page_name}.html from Pages directory: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error loading page: {page_name}.html")

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
                emoji_data[emoji_name] = f"/web/Emojis/Dice/{emoji_name}.png"
        
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
                emoji_data[card] = f"/web/Emojis/Cards/{card}.png"
        
        # Coin emojis (using existing Discord emoji IDs if available, otherwise fallback)
        coin_emojis = ["Pirate", "Poop", "Future", "Retro", "Full", "Empty", "Plug", "Socket", "Open", "Close", "Day", "Night", "Hot", "Cold"]
        for coin in coin_emojis:
            if coin in EMOJI_IDS:
                emoji_data[coin] = f"/web/Emojis/Coins/{coin}.png"
        
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
        result_emoji = f"/web/Emojis/Coins/{theme_data['heads'] if is_heads else theme_data['tails']}.png"
        
        return JSONResponse(content={
            "result": "heads" if is_heads else "tails",
            "emoji": result_emoji,
            "theme": theme
        })
    except Exception as e:
        logger.error(f"Error in coin flip: {e}")
        return JSONResponse(content={"error": "Failed to flip coin"}, status_code=500)

@app.get("/api/fun/dice-roll")
async def dice_roll(color: str, amount: int):
    """Roll dice with given color and amount."""
    try:
        import random
        
        # Validate inputs
        valid_colors = ["Red", "Orange", "Blue", "Yellow", "Pink", "Green", "Purple"]
        if color not in valid_colors:
            return JSONResponse(content={"error": "Invalid color"}, status_code=400)
        
        if amount < 1 or amount > 5:
            return JSONResponse(content={"error": "Amount must be between 1-5"}, status_code=400)
        
        # Roll dice
        rolls = []
        for _ in range(amount):
            roll = random.randint(1, 6)
            emoji_name = f"{color}{roll}"
            rolls.append({
                "value": roll,
                "emoji": f"/web/Emojis/Dice/{emoji_name}.png"
            })
        
        total = sum(roll["value"] for roll in rolls)
        
        return JSONResponse(content={
            "rolls": rolls,
            "total": total,
            "color": color,
            "amount": amount
        })
    except Exception as e:
        logger.error(f"Error in dice roll: {e}")
        return JSONResponse(content={"error": "Failed to roll dice"}, status_code=500)

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
                    "emoji": f"/web/Emojis/Cards/{card}.png"
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

@app.get("/api/bot-info")
async def get_bot_info():
    """Get comprehensive bot information including README and LICENSE data."""
    try:
        # Get bot information from Discord
        bot_info = {}
        
        if _bot_instance and _bot_instance.user:
            try:
                # Fetch the bot's user object to get the latest profile data, including the banner
                user = await _bot_instance.fetch_user(_bot_instance.user.id)
                banner_url = str(user.banner.url) if user.banner else None
            except Exception as e:
                logger.error(f"Failed to fetch bot user or banner: {e}")
                banner_url = None

            logger.info(f"Bot info requested. Name: {_bot_instance.user.name}, Banner URL: {banner_url}")
            
            bot_info.update({
                "name": _bot_instance.user.name,
                "avatar_url": str(_bot_instance.user.avatar.url) if _bot_instance.user.avatar else None,
                "banner_url": banner_url
            })
        else:
            logger.warning("/api/bot-info endpoint called but bot instance is not available.")
            # Use fallback information from README and LICENSE
            bot_info["name"] = "Reaper Bot"
            bot_info["avatar_url"] = None
            bot_info["banner_url"] = None
        
        # Get README information
        try:
            with open("README.md", "r", encoding="utf-8") as f:
                readme_content = f.read()
                # Extract bot description from README
                lines = readme_content.split('\n')
                for i, line in enumerate(lines):
                    if line.strip().startswith('> **') and 'bot' in line.lower():
                        bot_info["description"] = line.replace('> **', '').replace('**', '').strip()
                        break
                if "description" not in bot_info:
                    # Fallback to first paragraph after title
                    for i, line in enumerate(lines[1:], 1):
                        if line.strip() and not line.startswith('#') and not line.startswith('---'):
                            bot_info["description"] = line.strip().replace('> ', '').replace('**', '')
                            break
                bot_info["readme"] = readme_content
        except FileNotFoundError:
            bot_info["readme"] = "README.md not found"
            bot_info["description"] = "A comprehensive Discord bot"
        except Exception as e:
            logger.error(f"Error reading README: {e}")
            bot_info["readme"] = "Error reading README"
            bot_info["description"] = "A comprehensive Discord bot"
        
        # Get LICENSE information
        try:
            with open("LICENSE.txt", "r", encoding="utf-8") as f:
                license_content = f.read()
                # Extract license type
                if "END-USER LICENSE AGREEMENT" in license_content:
                    bot_info["license"] = "Custom EULA"
                else:
                    bot_info["license"] = "Custom License"
                bot_info["license_full"] = license_content
        except FileNotFoundError:
            bot_info["license"] = "License not found"
            bot_info["license_full"] = "LICENSE.txt not found"
        except Exception as e:
            logger.error(f"Error reading LICENSE: {e}")
            bot_info["license"] = "Error reading license"
            bot_info["license_full"] = "Error reading LICENSE"
        
        # Add GROQ API key for frontend use (safely - only indicate availability)
        from Systems.Functions.config import GROQ_API_KEY
        bot_info["groq_api_available"] = bool(GROQ_API_KEY)
        if GROQ_API_KEY:
            # Only expose a masked version for security
            bot_info["groq_api_key"] = GROQ_API_KEY[:8] + "..." + GROQ_API_KEY[-4:]
        else:
            bot_info["groq_api_key"] = None
        
        return JSONResponse(content=bot_info)
    except Exception as e:
        logger.error(f"Error fetching bot info: {e}", exc_info=True)
        return JSONResponse(content={"error": "Failed to fetch bot information"}, status_code=500)

@app.get("/api/pets-data")
async def get_pets_data():
    """Get comprehensive pets data from the Pets system."""
    try:
        import json
        # Load pets data from the info.json file
        pets_file_path = os.path.join(project_root, "Systems", "Pets", "Logic", "info.json")
        
        with open(pets_file_path, "r", encoding="utf-8") as f:
            pets_data = json.load(f)
        
        return JSONResponse(content=pets_data)
    except FileNotFoundError:
        logger.error("Pets info.json file not found")
        return JSONResponse(content={"error": "Pets data file not found"}, status_code=404)
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing pets JSON: {e}")
        return JSONResponse(content={"error": "Error parsing pets data"}, status_code=500)
    except Exception as e:
        logger.error(f"Error fetching pets data: {e}", exc_info=True)
        return JSONResponse(content={"error": "Failed to fetch pets data"}, status_code=500)


@app.get("/api/equipment-data")
async def get_equipment_data():
    """Get comprehensive equipment data from the Pets system."""
    try:
        import json
        # Load equipment data from the equipment.json file
        equipment_file_path = os.path.join(project_root, "Systems", "Pets", "Logic", "equipment.json")
        
        with open(equipment_file_path, "r", encoding="utf-8") as f:
            equipment_data = json.load(f)
        
        return JSONResponse(content=equipment_data)
    except FileNotFoundError:
        logger.error("Equipment equipment.json file not found")
        return JSONResponse(content={"error": "Equipment data file not found"}, status_code=404)
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing equipment JSON: {e}")
        return JSONResponse(content={"error": "Error parsing equipment data"}, status_code=500)
    except Exception as e:
        logger.error(f"Error fetching equipment data: {e}", exc_info=True)
        return JSONResponse(content={"error": "Failed to fetch equipment data"}, status_code=500)

def convert_markdown_to_html(text):
    """Convert Discord markdown to HTML for web display."""
    import re

    def slugify(s):
        s = s.lower().strip()
        s = re.sub(r'[\s-]+', '-', s)
        s = re.sub(r'[^a-z0-9-]', '', s)
        return s

    # Generate IDs for headers
    def add_header_ids(match):
        level = len(match.group(1))
        title = match.group(2).strip()
        id = slugify(title)
        return f'<h{level} id="{id}">{title}</h{level}>'

    text = re.sub(r'^(#+)(.+)$', add_header_ids, text, flags=re.MULTILINE)

    # Update ToC links to match slugified IDs
    def update_toc_links(match):
        link_text = match.group(1)
        link_target = match.group(2)
        slug = slugify(link_target.replace('#', ''))
        return f'<a href="#{slug}">{link_text}</a>'

    text = re.sub(r'\[([^\]]+)\]\((#[^\)]+)\)', update_toc_links, text)

    # Convert bold text (**text**)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    
    # Convert horizontal rules (---)
    text = re.sub(r'^---+$', r'<hr>', text, flags=re.MULTILINE)
    
    # Convert numbered lists (1. 2. 3.)
    text = re.sub(r'^(\d+\.) (.+)$', r'<li>\2</li>', text, flags=re.MULTILINE)
    
    # Convert bullet points (* text)
    text = re.sub(r'^(\*|-) (.+)$', r'<li>\2</li>', text, flags=re.MULTILINE)
    
    # Wrap consecutive list items in <ol> or <ul> tags
    text = re.sub(r'(<li>.+<\/li>\s*)+', lambda m: '<ol>\n' + m.group(0) + '</ol>\n' if m.group(0).strip().startswith('<li>') else '<ul>\n' + m.group(0) + '</ul>\n', text)

    # Convert inline code (`code`)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    
    # Convert code blocks (```code```)
    text = re.sub(r'```([a-z]*)\n([\s\S]*?)\n```', r'<pre><code class="language-\1">\2</code></pre>', text)
    
    # Convert general links [text](url)
    text = re.sub(r'\[([^\]]+)\]\((?!#)([^\)]+)\)', r'<a href="\2" target="_blank">\1</a>', text)
    
    # Convert line breaks to <br> tags for better formatting
    text = re.sub(r'\n', r'<br>', text)

    return text

@app.get("/api/readme")
async def get_readme():
    """Get README.md content converted to HTML."""
    try:
        with open("README.md", "r", encoding="utf-8") as f:
            readme_content = f.read()
        
        # Convert markdown to HTML
        html_content = convert_markdown_to_html(readme_content)
        return JSONResponse(content={"content": html_content})
    except FileNotFoundError:
        return JSONResponse(content={"error": "README.md not found"}, status_code=404)
    except Exception as e:
        logger.error(f"Error reading README: {e}")
        return JSONResponse(content={"error": "Failed to read README"}, status_code=500)

@app.get("/api/license")
async def get_license():
    """Get LICENSE.txt content."""
    try:
        with open("LICENSE.txt", "r", encoding="utf-8") as f:
            license_content = f.read()
        return JSONResponse(content={"content": license_content})
    except FileNotFoundError:
        return JSONResponse(content={"error": "LICENSE.txt not found"}, status_code=404)
    except Exception as e:
        logger.error(f"Error reading LICENSE: {e}")
        return JSONResponse(content={"error": "Failed to read LICENSE"}, status_code=500)

@app.get("/api/test")
async def test_endpoint():
    """Test endpoint to verify server is picking up changes."""
    return JSONResponse(content={"message": "Test endpoint working", "timestamp": str(datetime.now())})

@app.get("/api/commands")
async def get_commands():
    """Get all bot commands organized by category."""
    try:
        logger.info("API/commands endpoint called")
        
        if not _bot_instance:
            logger.warning("Bot instance not available for /api/commands")
            return JSONResponse(content={"error": "Bot not available"}, status_code=503)
        
        commands_data = []
        logger.info(f"Starting command extraction from {len(_bot_instance.cogs)} cogs")
        
        # Iterate through all cogs to get commands
        for cog_name, cog in _bot_instance.cogs.items():
            # Skip internal cogs
            if cog_name in ['OwnerCog']:
                continue
                
            logger.info(f"Processing cog: {cog_name}")
            
            # Get commands from this cog
            for command in cog.get_commands():
                # Skip hidden commands
                if command.hidden:
                    continue
                    
                # Determine category based on cog name or command module
                category = cog_name.replace('Cog', '').replace('_', ' ').strip()
                if not category:
                    category = 'General'
                
                # Get command parameters
                params = []
                if hasattr(command, 'params'):
                    for param_name, param in command.params.items():
                        if param_name in ['self', 'ctx', 'interaction']:
                            continue
                            
                        param_info = {
                            "name": param_name,
                            "description": getattr(param, 'description', None) or "No description available",
                            "required": getattr(param, 'required', True),
                            "default": str(param.default) if param.default is not None else None
                        }
                        
                        # Add choices if available
                        if hasattr(param, 'choices') and param.choices:
                            param_info["choices"] = [choice.name for choice in param.choices]
                        
                        params.append(param_info)
                
                command_data = {
                    "name": command.name,
                    "description": command.description or "No description available",
                    "usage": f"/{command.name}" + (f" {' '.join([f'<{p}>' for p in params])}" if params else ""),
                    "category": category,
                    "params": params
                }
                
                commands_data.append(command_data)
                logger.info(f"Added command: {command.name} in category {category}")
        
        # Also get slash commands from the bot's tree
        slash_commands = _bot_instance.tree.get_commands()
        logger.info(f"Processing {len(slash_commands)} slash commands")
        for app_command in slash_commands:
            # Determine category based on command name or module
            category = 'Slash Commands'
            
            # Get command parameters
            params = []
            if hasattr(app_command, 'parameters'):
                for param in app_command.parameters:
                    param_info = {
                        "name": param.name,
                        "description": param.description or "No description available",
                        "required": getattr(param, 'required', True),
                        "default": str(param.default) if hasattr(param, 'default') and param.default is not None else None
                    }
                    
                    # Add choices if available
                    if hasattr(param, 'choices') and param.choices:
                        param_info["choices"] = [choice.name for choice in param.choices]
                    
                    params.append(param_info)
            
            command_data = {
                "name": app_command.name,
                "description": app_command.description or "No description available",
                "usage": f"/{app_command.name}" + (f" {' '.join([f'<{p}>' for p in params])}" if params else ""),
                "category": category,
                "params": params
            }
            
            commands_data.append(command_data)
            logger.info(f"Added slash command: {app_command.name}")
        
        logger.info(f"Successfully retrieved {len(commands_data)} commands for API")
        return JSONResponse(content=commands_data)
        
    except Exception as e:
        logger.error(f"Error in /api/commands endpoint: {e}", exc_info=True)
        return JSONResponse(content={"error": "Failed to fetch commands", "details": str(e)}, status_code=500)

@app.get("/api/pnw/resource-prices")
async def get_pnw_resource_prices():
    """Get PnW resource prices."""
    try:
        prices = await get_resource_prices()
        return JSONResponse(content=prices)
    except Exception as e:
        logger.error(f"Error getting resource prices: {e}")
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

@app.get("/api/pnw/nation-info/{nation_query}")
async def get_pnw_nation_info(nation_query: str):
    """Get PnW nation info."""
    try:
        query_instance = create_v3_query_instance()
        if nation_query.isdigit():
            nation_data = await query_instance.get_nation_by_id(nation_query)
        else:
            nation_data = await query_instance.get_nation_by_name(nation_query)
        
        if not nation_data:
            return JSONResponse(content={"error": "Nation not found"}, status_code=404)
            
        return JSONResponse(content=nation_data)
    except Exception as e:
        logger.error(f"Error getting nation info: {e}")
        return JSONResponse(content={"error": "Failed to retrieve nation info"}, status_code=500)

async def _get_war_graph_data(alliance_name: str, time: str, force_refresh: bool, opps_view: bool) -> dict:
    """Helper function to get war graph data."""
    # Time parsing logic
    after_datetime = None
    match = re.match(r'(\d+)([dwm])', time.lower())
    if match:
        amount, unit = int(match.group(1)), match.group(2)
        delta = timedelta()
        if unit == 'd':
            delta = timedelta(days=amount)
        elif unit == 'w':
            delta = timedelta(weeks=amount)
        elif unit == 'm':
            delta = timedelta(days=amount * 30)
        after_datetime = datetime.now(timezone.utc) - delta
    
    if not after_datetime:
        raise ValueError("Invalid time format. Use formats like '2d', '3w', or '1m'.")

    query_instance = create_v3_query_instance()
    resolved_alliance_ids = await query_instance.resolve_entities([alliance_name], 'alliance')
    if not resolved_alliance_ids:
        raise ValueError(f"Could not find an alliance named '{alliance_name}'.")
    
    alliance_id = resolved_alliance_ids[0]

    all_wars = await get_wars(alliance_id=[alliance_id], active=False, status="ALL", after=after_datetime, before=datetime.now(timezone.utc), force_refresh=force_refresh)
    if not all_wars:
        raise ValueError(f"No wars found for alliance '{alliance_name}' in the last {time}.")

    resource_prices = await get_resource_prices()
    
    # Simplified nation collection logic for web view
    nation_ids = set()
    nation_names = {}
    for war in all_wars:
        if opps_view:
            if str(war.get('def_alliance_id')) == str(alliance_id):
                nid = war.get('att_id')
                nname = war.get('attacker', {}).get('nation_name')
                if nid and nname: nation_ids.add(nid); nation_names[nid] = nname
            if str(war.get('att_alliance_id')) == str(alliance_id):
                nid = war.get('def_id')
                nname = war.get('defender', {}).get('nation_name')
                if nid and nname: nation_ids.add(nid); nation_names[nid] = nname
        else:
            if str(war.get('att_alliance_id')) == str(alliance_id):
                nid = war.get('att_id')
                nname = war.get('attacker', {}).get('nation_name')
                if nid and nname: nation_ids.add(nid); nation_names[nid] = nname
            if str(war.get('def_alliance_id')) == str(alliance_id):
                nid = war.get('def_id')
                nname = war.get('defender', {}).get('nation_name')
                if nid and nname: nation_ids.add(nid); nation_names[nid] = nname

    nation_breakdown = {}
    for nation_id in nation_ids:
        nation_wars = [w for w in all_wars if str(w.get('att_id')) == str(nation_id) or str(w.get('def_id')) == str(nation_id)]
        if not nation_wars: continue
        costs = await calculate_war_costs(nation_wars, resource_prices, team1_id_set={int(nation_id)})
        team1_costs = costs.get('team1', {})
        total_gains = team1_costs.get('loot_received', 0) + sum(team1_costs.get('resource_loot', {}).values())
        if team1_costs.get('gross', 0) > 0 or total_gains > 0:
            # Correctly calculate resource loot values
            resource_loot_gained_value = sum(amount * resource_prices.get("sell", {}).get(res, 0) for res, amount in team1_costs.get('resource_loot_gained', {}).items())
            resource_loot_lost_value = sum(amount * resource_prices.get("sell", {}).get(res, 0) for res, amount in team1_costs.get('resource_loot_lost', {}).items())

            nation_breakdown[nation_id] = {
                'nation_id': nation_id,
                'name': nation_names.get(nation_id, f'Unknown {nation_id}'),
                'gross_cost': team1_costs.get('gross', 0),
                'net_damage': team1_costs.get('gross', 0) - costs.get('team2', {}).get('gross', 0),
                'total_gains': total_gains,
                'soldiers_lost': team1_costs.get('units', {}).get('soldiers', {}).get('lost', 0),
                'tanks_lost': team1_costs.get('units', {}).get('tanks', {}).get('lost', 0),
                'aircraft_lost': team1_costs.get('units', {}).get('aircraft', {}).get('lost', 0),
                'ships_lost': team1_costs.get('units', {}).get('ships', {}).get('lost', 0),
                'missiles_lost': team1_costs.get('units', {}).get('missiles', {}).get('lost', 0),
                'nukes_lost': team1_costs.get('units', {}).get('nukes', {}).get('lost', 0),
                'consumption_cost': (team1_costs.get('consumption', {}).get('munitions', 0) * resource_prices['buy'].get("munitions", 0)) + \
                                    (team1_costs.get('consumption', {}).get('gasoline', 0) * resource_prices['buy'].get("gasoline", 0)),
                'infra_destroyed_value': team1_costs.get('infra_lost_value', 0),
                'improvements_cost': team1_costs.get('improvements_lost', 0),
                'loot_lost': team1_costs.get('loot_lost', 0),
                'resource_loot_lost_value': resource_loot_lost_value,
            }

    if not nation_breakdown:
        raise ValueError(f"No war costs could be calculated for alliance '{alliance_name}' in the last {time}.")

    return {
        'nation_breakdown': nation_breakdown,
        'resource_prices': resource_prices,
        'all_wars': all_wars,
        'alliance_id': alliance_id
    }

@app.get("/api/graph/war", response_class=HTMLResponse)
async def get_war_graph(alliance_name: str, time: str, force_refresh: bool = False, opps_view: bool = False):
    try:
        logger.info(f"Received war graph request for alliance: {alliance_name}, time: {time}, force_refresh: {force_refresh}, opps_view: {opps_view}")
        data = await _get_war_graph_data(alliance_name, time, force_refresh, opps_view)
        html_filename = war_graph_generator.generate_interactive_breakdown(data['nation_breakdown'], alliance_name, data['resource_prices'])
        html_file_path = os.path.abspath(os.path.join("web", "Wars", html_filename))
        if os.path.exists(html_file_path):
            with open(html_file_path, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read(), status_code=200)
        else:
            return HTMLResponse(content="Failed to generate war breakdown graph: HTML file not created", status_code=500)
    except ValueError as e:
        return HTMLResponse(content=str(e), status_code=400)
    except Exception as e:
        logger.error(f"Error generating war graph: {e}", exc_info=True)
        return HTMLResponse(content=f"An error occurred: {e}", status_code=500)

@app.get("/api/graph/warnet", response_class=HTMLResponse)
async def get_war_net_graph(alliance_name: str, time: str, force_refresh: bool = False, opps_view: bool = False):
    try:
        logger.info(f"Received war net graph request for alliance: {alliance_name}, time: {time}, force_refresh: {force_refresh}, opps_view: {opps_view}")
        data = await _get_war_graph_data(alliance_name, time, force_refresh, opps_view)
        
        # Calculate enemy relationships
        nation_breakdown = data['nation_breakdown']
        all_wars = data['all_wars']
        alliance_id = data['alliance_id']
        
        enemy_relationships = {}
        nation_id_to_name = {nid: costs['name'] for nid, costs in nation_breakdown.items()}
        
        for war in all_wars:
            att_alliance_id = str(war.get('att_alliance_id'))
            def_alliance_id = str(war.get('def_alliance_id'))
            att_id = war.get('att_id')
            def_id = war.get('def_id')

            if att_alliance_id != str(alliance_id) and def_alliance_id != str(alliance_id):
                continue

            if att_alliance_id == str(alliance_id):
                alliance_member_id = att_id
                enemy_id = def_id
                enemy_obj = war.get('defender')
            else:
                alliance_member_id = def_id
                enemy_id = att_id
                enemy_obj = war.get('attacker')

            if alliance_member_id not in nation_id_to_name:
                continue

            if alliance_member_id not in enemy_relationships:
                enemy_relationships[alliance_member_id] = {}

            if enemy_id not in enemy_relationships[alliance_member_id]:
                enemy_name = 'Unknown Enemy'
                if enemy_obj and isinstance(enemy_obj, dict):
                    enemy_name = enemy_obj.get('nation_name', f'Enemy {enemy_id}')
                enemy_relationships[alliance_member_id][enemy_id] = {'name': enemy_name, 'net_damage': 0}

            # Simplified net damage calculation for web view
            att_infra_destroyed = war.get('att_infra_destroyed_value', 0)
            def_infra_destroyed = war.get('def_infra_destroyed_value', 0)
            net_damage = def_infra_destroyed - att_infra_destroyed if att_alliance_id == str(alliance_id) else att_infra_destroyed - def_infra_destroyed
            enemy_relationships[alliance_member_id][enemy_id]['net_damage'] += net_damage

        html_filename = war_net_breakdown_graph_generator.generate_interactive_net_breakdown(data['nation_breakdown'], alliance_name, data['resource_prices'], enemy_relationships)
        html_file_path = os.path.abspath(os.path.join("web", "Wars", html_filename))
        if os.path.exists(html_file_path):
            with open(html_file_path, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read(), status_code=200)
        else:
            return HTMLResponse(content="Failed to generate war net breakdown graph: HTML file not created", status_code=500)
    except ValueError as e:
        return HTMLResponse(content=str(e), status_code=400)
    except Exception as e:
        logger.error(f"Error generating war net graph: {e}", exc_info=True)
        return HTMLResponse(content=f"An error occurred: {e}", status_code=500)

@app.get("/api/graph/treaty", response_class=HTMLResponse)
async def get_treaty_graph(alliance_ids: str = None):
    try:
        logger.info(f"Received treaty graph request for alliances: {alliance_ids}")

        query_instance = create_v3_query_instance()
        all_treaties = await get_all_treaties()

        if not all_treaties:
            return HTMLResponse(content="Could not fetch any treaties.", status_code=404)

        treaty_graph = TreatyGraph()
        G = treaty_graph.build_treaty_graph(all_treaties)
        blocs = treaty_graph.find_blocs(all_treaties)
        
        html_content = treaty_graph.create_interactive_map(G, all_treaties, blocs)
        return HTMLResponse(content=html_content, status_code=200)

    except Exception as e:
        logger.error(f"Error generating treaty graph: {e}", exc_info=True)
        return HTMLResponse(content=f"An error occurred: {e}", status_code=500)


@app.get("/api/graph/compare", response_class=HTMLResponse)
async def get_compare_graph(home_alliance_ids: str, away_alliance_ids: str):
    try:
        logger.info(f"Received compare graph request for home alliances: {home_alliance_ids} and away alliances: {away_alliance_ids}")

        # Parse alliance IDs
        home_ids = [int(aid.strip()) for aid in home_alliance_ids.split(',') if aid.strip().isdigit()]
        away_ids = [int(aid.strip()) for aid in away_alliance_ids.split(',') if aid.strip().isdigit()]
        
        if not home_ids or not away_ids:
            return HTMLResponse(content="Invalid alliance IDs provided.", status_code=400)

        # Create filename with timestamp for caching
        today_str = datetime.now().strftime("%m-%d-%Y")
        home_names_str = "-".join([str(aid) for aid in sorted(home_ids)])
        away_names_str = "-".join([str(aid) for aid in sorted(away_ids)])
        html_filename = f"comparison_{home_names_str}_{away_names_str}_{today_str}.html"
        comparisons_dir = os.path.join("web", "Comparisons")
        html_filepath = os.path.join(comparisons_dir, html_filename)
        
        # Check if cached file exists
        if os.path.exists(html_filepath):
            logger.info(f"Using cached comparison file: {html_filename}")
            with open(html_filepath, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read(), status_code=200)

        # Import required modules from compare.py
        from Systems.PnW.Util.query import create_v3_query_instance
        from Systems.PnW.Util.calc import AllianceCalculator
        
        query_instance = create_v3_query_instance()
        calculator = AllianceCalculator(query_instance)

        async def get_alliance_stats(alliance_ids, side_label):
            all_stats = []
            
            # Fetch nations for all alliances in batch
            queries = {}
            for aid in alliance_ids:
                queries[f"a{aid}"] = f"""
                    nations(alliance_id: {aid}, first: 500) {{
                        paginatorInfo {{ hasMorePages }}
                        data {{
                            id
                            nation_name
                            alliance_position
                            vacation_mode_turns
                            score
                            num_cities
                            soldiers
                            tanks
                            aircraft
                            ships
                            missiles
                            nukes
                            military_research {{
                                ground_capacity
                                air_capacity
                                naval_capacity
                            }}
                            iron_dome
                            missile_launch_pad
                            nuclear_research_facility
                            vital_defense_system
                            propaganda_bureau
                            military_research_center
                            space_program
                            nuclear_launch_facility
                            cities {{
                                barracks
                                factory
                                hangar
                                drydock
                            }}
                        }}
                    }}
                """
            
            batch_results = await query_instance.execute_batch(queries)
            
            for aid in alliance_ids:
                alias = f"a{aid}"
                result = batch_results.get(alias, {})
                if result and isinstance(result, dict):
                    nations_data = result.get('data', [])
                    if nations_data:
                        # Filter active nations (not in VM, not Applicant)
                        active_nations = []
                        for n in nations_data:
                            vm_turns = int(n.get('vacation_mode_turns', 0) or 0)
                            position = str(n.get('alliance_position', '') or '').upper()
                            if vm_turns == 0 and position != 'APPLICANT':
                                active_nations.append(n)
                        
                        # Calculate statistics using AllianceCalculator
                        stats = await calculator.calculate_alliance_statistics(active_nations)
                        daily_military = await calculator.calculate_full_mill_data(active_nations)
                        
                        # Get city counts
                        city_counts = {}
                        for n in active_nations:
                            num_cities = n.get('num_cities', 0)
                            city_counts[num_cities] = city_counts.get(num_cities, 0) + 1
                        
                        # Get alliance name from first nation or use ID
                        alliance_name = f"Alliance {aid}"
                        if active_nations:
                            first_nation = active_nations[0]
                            if first_nation.get('alliance'):
                                alliance_name = first_nation['alliance'].get('name', alliance_name)
                        
                        all_stats.append({
                            'name': alliance_name,
                            'stats': {
                                **stats,
                                'daily_military': daily_military,
                                'city_counts': city_counts
                            }
                        })
            
            return all_stats

        # Get stats for both sides
        home_stats = await get_alliance_stats(home_ids, "Home")
        away_stats = await get_alliance_stats(away_ids, "Away")

        if not home_stats or not away_stats:
            return HTMLResponse(content="No data found for the specified alliances.", status_code=404)

        # Generate interactive comparison page
        html_content = create_interactive_comparison_page(home_stats, away_stats)
        
        # Ensure Comparisons directory exists
        os.makedirs(comparisons_dir, exist_ok=True)
        
        # Save the HTML file for caching
        with open(html_filepath, "w", encoding="utf-8") as f:
            f.write(html_content)
        
        logger.info(f"Generated and cached comparison file: {html_filename}")
        return HTMLResponse(content=html_content, status_code=200)

    except Exception as e:
        logger.error(f"Error generating compare graph: {e}", exc_info=True)
        return HTMLResponse(content=f"An error occurred: {e}", status_code=500)



# Astrology API endpoints
import json
from pathlib import Path

# Cache for astrology data
_astrology_cache = {}

async def _get_astrology_json_data(filename: str) -> List[Dict[str, Any]]:
    """Load astrology JSON data with caching."""
    cache_key = f"astrology_{filename}"
    if cache_key in _astrology_cache:
        return _astrology_cache[cache_key]
    
    # Construct an absolute path to the Zodiac directory
    base_path = Path(__file__).parent.parent / "Astrology" / "Zodiac"
    path = base_path / filename
    
    if not path.exists():
        logger.error(f"Astrology data file not found at {path}")
        return []
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            _astrology_cache[cache_key] = data
            logger.info(f"Sending equipment data for {len(data)} categories")
        return data
    except Exception as e:
        logger.error(f"Error loading astrology data from {filename}: {e}")
        return []

def _zodiac_for_date(bday: date) -> str:
    """Return the zodiac sign name for given date (month/day boundaries)."""
    m, d = bday.month, bday.day
    if (m == 12 and d >= 22) or (m == 1 and d <= 19):
        return "Capricorn"
    if (m == 1 and d >= 20) or (m == 2 and d <= 18):
        return "Aquarius"
    if (m == 2 and d >= 19) or (m == 3 and d <= 20):
        return "Pisces"
    if (m == 3 and d >= 21) or (m == 4 and d <= 19):
        return "Aries"
    if (m == 4 and d >= 20) or (m == 5 and d <= 20):
        return "Taurus"
    if (m == 5 and d >= 21) or (m == 6 and d <= 20):
        return "Gemini"
    if (m == 6 and d >= 21) or (m == 7 and d <= 22):
        return "Cancer"
    if (m == 7 and d >= 23) or (m == 8 and d <= 22):
        return "Leo"
    if (m == 8 and d >= 23) or (m == 9 and d <= 22):
        return "Virgo"
    if (m == 9 and d >= 23) or (m == 10 and d <= 22):
        return "Libra"
    if (m == 10 and d >= 23) or (m == 11 and d <= 21):
        return "Scorpio"
    return "Sagittarius"

async def _find_western_sign_data(sign_name: str) -> Optional[Dict[str, Any]]:
    """Find Western zodiac sign data."""
    logger.info(f"Looking for Western sign data: {sign_name}")
    data = await _get_astrology_json_data("astrology.json")
    logger.info(f"Loaded astrology.json with {len(data)} entries")
    for entry in data:
        if entry.get("name", "").lower() == sign_name.lower():
            logger.info(f"Found Western sign data for {sign_name}")
            return entry
    logger.warning(f"No Western sign data found for {sign_name}")
    return None

async def _find_chinese_sign_by_birthday(user_birthday: date) -> Optional[Dict[str, Any]]:
    """Determine Chinese zodiac sign accounting for actual Chinese New Year of that year."""
    logger.info(f"Looking for Chinese sign for birthday: {user_birthday}")
    # Chinese New Year dates (simplified for web version)
    CHINESE_NEW_YEAR_DATES = {
        1900: date(1900, 1, 31), 1901: date(1901, 2, 19), 1902: date(1902, 2, 8), 1903: date(1903, 1, 29),
        1904: date(1904, 2, 16), 1905: date(1905, 2, 4), 1906: date(1906, 1, 25), 1907: date(1907, 2, 13),
        1908: date(1908, 2, 2), 1909: date(1909, 1, 22), 1910: date(1910, 2, 10), 1911: date(1911, 1, 30),
        1912: date(1912, 2, 18), 1913: date(1913, 2, 6), 1914: date(1914, 1, 26), 1915: date(1915, 2, 14),
        1916: date(1916, 2, 3), 1917: date(1917, 1, 23), 1918: date(1918, 2, 11), 1919: date(1919, 2, 1),
        1920: date(1920, 2, 20), 1921: date(1921, 2, 8), 1922: date(1922, 1, 28), 1923: date(1923, 2, 16),
        1924: date(1924, 2, 5), 1925: date(1925, 1, 24), 1926: date(1926, 2, 13), 1927: date(1927, 2, 2),
        1928: date(1928, 1, 23), 1929: date(1929, 2, 10), 1930: date(1930, 1, 30), 1931: date(1931, 2, 17),
        1932: date(1932, 2, 6), 1933: date(1933, 1, 26), 1934: date(1934, 2, 14), 1935: date(1935, 2, 4),
        1936: date(1936, 1, 24), 1937: date(1937, 2, 11), 1938: date(1938, 1, 31), 1939: date(1939, 2, 19),
        1940: date(1940, 2, 8), 1941: date(1941, 1, 27), 1942: date(1942, 2, 15), 1943: date(1943, 2, 5),
        1944: date(1944, 1, 25), 1945: date(1945, 2, 13), 1946: date(1946, 2, 2), 1947: date(1947, 1, 22),
        1948: date(1948, 2, 10), 1949: date(1949, 1, 29), 1950: date(1950, 2, 17), 1951: date(1951, 2, 6),
        1952: date(1952, 1, 27), 1953: date(1953, 2, 14), 1954: date(1954, 2, 3), 1955: date(1955, 1, 24),
        1956: date(1956, 2, 12), 1957: date(1957, 1, 31), 1958: date(1958, 2, 18), 1959: date(1959, 2, 8),
        1960: date(1960, 1, 28), 1961: date(1961, 2, 15), 1962: date(1962, 2, 5), 1963: date(1963, 1, 25),
        1964: date(1964, 2, 13), 1965: date(1965, 2, 2), 1966: date(1966, 1, 21), 1967: date(1967, 2, 9),
        1968: date(1968, 1, 30), 1969: date(1969, 2, 17), 1970: date(1970, 2, 6), 1971: date(1971, 1, 27),
        1972: date(1972, 2, 15), 1973: date(1973, 2, 3), 1974: date(1974, 1, 23), 1975: date(1975, 2, 11),
        1976: date(1976, 1, 31), 1977: date(1977, 2, 18), 1978: date(1978, 2, 7), 1979: date(1979, 1, 28),
        1980: date(1980, 2, 16), 1981: date(1981, 2, 5), 1982: date(1982, 1, 25), 1983: date(1983, 2, 13),
        1984: date(1984, 2, 2), 1985: date(1985, 2, 20), 1986: date(1986, 2, 9), 1987: date(1987, 1, 29),
        1988: date(1988, 2, 17), 1989: date(1989, 2, 6), 1990: date(1990, 1, 27), 1991: date(1991, 2, 15),
        1992: date(1992, 2, 4), 1993: date(1993, 1, 23), 1994: date(1994, 2, 10), 1995: date(1995, 1, 31),
        1996: date(1996, 2, 19), 1997: date(1997, 2, 7), 1998: date(1998, 1, 28), 1999: date(1999, 2, 16),
        2000: date(2000, 2, 5), 2001: date(2001, 1, 24), 2002: date(2002, 2, 12), 2003: date(2003, 2, 1),
        2004: date(2004, 1, 22), 2005: date(2005, 2, 9), 2006: date(2006, 1, 29), 2007: date(2007, 2, 18),
        2008: date(2008, 2, 7), 2009: date(2009, 1, 26), 2010: date(2010, 2, 14), 2011: date(2011, 2, 3),
        2012: date(2012, 1, 23), 2013: date(2013, 2, 10), 2014: date(2014, 1, 31), 2015: date(2015, 2, 19),
        2016: date(2016, 2, 8), 2017: date(2017, 1, 28), 2018: date(2018, 2, 16), 2019: date(2019, 2, 5),
        2020: date(2020, 1, 25), 2021: date(2021, 2, 12), 2022: date(2022, 2, 1), 2023: date(2023, 1, 22),
        2024: date(2024, 2, 10), 2025: date(2025, 1, 29), 2026: date(2026, 2, 17), 2027: date(2027, 2, 6),
    }
    
    year = user_birthday.year
    cny = CHINESE_NEW_YEAR_DATES.get(year, date(year, 2, 4))
    chinese_year = year if user_birthday >= cny else year - 1
    
    # Calculate animal based on year
    animals = ["Rat", "Ox", "Tiger", "Rabbit", "Dragon", "Snake", "Horse", "Goat", "Monkey", "Rooster", "Dog", "Pig"]
    index = (chinese_year - 4) % 12
    animal_name = animals[index]
    
    data = await _get_astrology_json_data("chinese_astrology.json")
    for entry in data:
        if entry.get("Name", "").lower() == animal_name.lower():
            return entry
    
    logger.warning(f"Chinese animal '{animal_name}' not found in database, returning default")
    return {"Name": animal_name, "Emoji": "🔮", "Description": "Unknown"}

async def _find_primal_entry(western_sign: str, chinese_animal: str) -> Optional[Dict[str, Any]]:
    """Find Primal Astrology combination with more robust matching."""
    logger.info(f"Looking for primal entry: {western_sign} / {chinese_animal}")
    if not western_sign or not chinese_animal:
        logger.warning(f"Missing western_sign or chinese_animal: {western_sign}, {chinese_animal}")
        return None

    data = await _get_astrology_json_data("primal_astrology.json")
    if not data:
        logger.warning("primal_astrology.json is empty or could not be loaded.")
        return None

    # Normalize inputs
    western_sign = western_sign.strip()
    chinese_animal = chinese_animal.strip()

    # Define known alternate names for Chinese animals
    alternates = {
        "Goat": "Sheep", "Sheep": "Goat",
        "Rat": "Mouse", "Mouse": "Rat",
        "Ox": "Cow", "Cow": "Ox",
        "Rabbit": "Cat", "Cat": "Rabbit",
        "Rooster": "Chicken", "Chicken": "Rooster",
        "Pig": "Boar", "Boar": "Pig"
    }

    possible_chinese_names = {chinese_animal, alternates.get(chinese_animal)}
    possible_chinese_names.discard(None)

    # Iterate through all possible combinations
    for entry in data:
        sign_combination = entry.get("Sign Combination", "").strip()
        if not sign_combination:
            continue

        # Split the combination into parts (e.g., "Aries / Rat")
        parts = [part.strip() for part in re.split(r'[\/,-]', sign_combination)]
        if len(parts) != 2:
            continue

        # Check if the parts match the western and any of the possible Chinese names
        part1, part2 = parts
        for name in possible_chinese_names:
            if (part1.lower() == western_sign.lower() and part2.lower() == name.lower()) or \
               (part2.lower() == western_sign.lower() and part1.lower() == name.lower()):
                logger.info(f"Found primal match for {western_sign}/{chinese_animal} -> {sign_combination}")
                return entry

    logger.warning(f"No primal astrology match found for {western_sign} / {chinese_animal}")
    return None

async def _fetch_horoscope_data(sign: str, day: str = "today") -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Fetch horoscope data with fallback generation."""
    import random
    
    sign_slug = str(sign).strip().lower()
    
    # Fallback horoscope templates based on sign characteristics
    horoscope_templates = {
        "aries": [
            "Today brings new opportunities for leadership and action.",
            "Your natural courage will help you overcome challenges.",
            "Energy and enthusiasm are your allies today."
        ],
        "taurus": [
            "Stability and comfort are highlighted today.",
            "Your practical nature will serve you well.",
            "Focus on building solid foundations."
        ],
        "gemini": [
            "Communication is key today - express yourself clearly.",
            "Your adaptability will be an asset.",
            "New ideas and connections are favored."
        ],
        "cancer": [
            "Emotional connections are emphasized today.",
            "Trust your intuition in decision making.",
            "Home and family matters may require attention."
        ],
        "leo": [
            "Your natural charisma shines brightly today.",
            "Creative expression is favored.",
            "Leadership opportunities may arise."
        ],
        "virgo": [
            "Attention to detail brings rewards.",
            "Organization and planning are highlighted.",
            "Health and wellness matters may need focus."
        ],
        "libra": [
            "Balance and harmony are important today.",
            "Relationships may need attention and care.",
            "Aesthetic and artistic pursuits are favored."
        ],
        "scorpio": [
            "Transformation and renewal are themes today.",
            "Deep insights may come through introspection.",
            "Passion and intensity are your allies."
        ],
        "sagittarius": [
            "Adventure and exploration are calling.",
            "Your optimistic outlook attracts positive energy.",
            "Learning and growth opportunities abound."
        ],
        "capricorn": [
            "Hard work and discipline pay off today.",
            "Long-term planning is favored.",
            "Professional matters may come into focus."
        ],
        "aquarius": [
            "Innovation and originality are highlighted.",
            "Your unique perspective is valuable.",
            "Group activities and friendships are favored."
        ],
        "pisces": [
            "Intuition and creativity flow strongly.",
            "Compassion and empathy serve you well.",
            "Spiritual and artistic pursuits are favored."
        ]
    }
    
    templates = horoscope_templates.get(sign_slug, ["Today brings new opportunities and experiences."])
    text = random.choice(templates)
    
    # Generate some basic stats
    lucky_numbers = ["3", "7", "9", "11", "21", "27"]
    colors = ["Blue", "Red", "Green", "Purple", "Gold", "Silver"]
    moods = ["Energetic", "Calm", "Focused", "Creative", "Social", "Reflective"]
    
    # Get date range for sign
    date_ranges = {
        "aries": "March 21 - April 19",
        "taurus": "April 20 - May 20",
        "gemini": "May 21 - June 20",
        "cancer": "June 21 - July 22",
        "leo": "July 23 - August 22",
        "virgo": "August 23 - September 22",
        "libra": "September 23 - October 22",
        "scorpio": "October 23 - November 21",
        "sagittarius": "November 22 - December 21",
        "capricorn": "December 22 - January 19",
        "aquarius": "January 20 - February 18",
        "pisces": "February 19 - March 20",
    }
    
    stats = {
        "mood": random.choice(moods),
        "color": random.choice(colors),
        "lucky_number": random.choice(lucky_numbers),
        "lucky_time": f"{random.randint(1, 12)}:00 {'AM' if random.random() < 0.5 else 'PM'}",
        "compatibility": random.choice(list(horoscope_templates.keys())),
        "date_range": date_ranges.get(sign.lower(), "Unknown"),
        "current_date": datetime.now().strftime("%B %d, %Y")
    }
    
    return text, stats

@app.get("/api/horoscope-proxy")
async def horoscope_proxy(sign: str, day: str = "today"):
    """Proxy for the external horoscope API to avoid CORS issues."""
    try:
        # Validate sign
        valid_signs = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
                      "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
        sign_match = next((s for s in valid_signs if s.lower() == sign.lower()), None)
        if not sign_match:
            return JSONResponse(content={"error": "Invalid sign"}, status_code=400)

        # Validate day parameter
        valid_days = ["today", "yesterday", "tomorrow"]
        if day.lower() not in valid_days:
            day = "today"  # Default to today if invalid day provided

        # Use the new free horoscope API - note: this API only supports daily horoscopes
        # For yesterday/tomorrow, we'll use the current day's horoscope as a fallback
        url = f"https://freehoroscopeapi.com/api/v1/get-horoscope/daily?sign={sign_match.lower()}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
            
            api_data = response.json()
            logger.info(f"Successfully proxied horoscope for {sign_match} ({day})")
            
            # Transform the new API format to match the old format for compatibility
            if "data" in api_data:
                # Adjust date based on the day parameter
                from datetime import datetime, timedelta
                base_date = datetime.strptime(api_data["data"]["date"], "%Y-%m-%d")
                
                if day.lower() == "yesterday":
                    adjusted_date = base_date - timedelta(days=1)
                elif day.lower() == "tomorrow":
                    adjusted_date = base_date + timedelta(days=1)
                else:  # today
                    adjusted_date = base_date
                
                transformed_data = {
                    "date": adjusted_date.strftime("%Y-%m-%d"),
                    "horoscope": api_data["data"]["horoscope"],
                    "sunsign": api_data["data"]["sign"]
                }
                return JSONResponse(content=transformed_data)
            else:
                return JSONResponse(content=api_data)

    except httpx.RequestError as e:
        logger.error(f"Error fetching horoscope from external API for {sign}: {e}")
        return JSONResponse(content={"error": "Failed to fetch horoscope from the external source."}, status_code=502) # Bad Gateway
    except Exception as e:
        logger.error(f"Error in horoscope proxy endpoint: {e}", exc_info=True)
        return JSONResponse(content={"error": "Internal server error in proxy."}, status_code=500)


@app.post("/api/astrology/signs")
async def get_astrology_signs(request: AstrologyRequest):
    """Get Western, Eastern, and Spirit Animal signs for a birth date."""
    try:
        logger.info(f"Received astrology signs request: {request.month}/{request.day}/{request.year}")
        
        # Validate date
        try:
            user_birthday = date(request.year, request.month, request.day)
            logger.info(f"Validated birth date: {user_birthday}")
        except ValueError:
            logger.error(f"Invalid date provided: {request.month}/{request.day}/{request.year}")
            return JSONResponse(
                content={"error": "Invalid date. Please check the month/day combination."},
                status_code=400
            )
        
        if user_birthday > date.today():
            logger.error(f"Future date provided: {user_birthday}")
            return JSONResponse(
                content={"error": "Date cannot be in the future."},
                status_code=400
            )
        
        # Get Western sign
        western_sign = _zodiac_for_date(user_birthday)
        logger.info(f"Western sign: {western_sign}")
        western_data = await _find_western_sign_data(western_sign)
        
        if not western_data:
            logger.error(f"No Western zodiac data found for {western_sign}")
            return JSONResponse(
                content={"error": f"Could not find Western zodiac data for {western_sign}."},
                status_code=404
            )
        
        # Get Chinese sign
        chinese_data = await _find_chinese_sign_by_birthday(user_birthday)
        logger.info(f"Chinese data: {chinese_data}")
        
        # Get Spirit Animal (Primal Astrology)
        chinese_animal = chinese_data.get("Name", "") if chinese_data else ""
        logger.info(f"Chinese animal: {chinese_animal}")
        spirit_data = await _find_primal_entry(western_sign, chinese_animal)
        logger.info(f"Spirit data: {spirit_data}")
        
        # Format response
        response = {
            "western": western_data,
            "chinese": chinese_data,
            "spirit": spirit_data,
            "birth_date": user_birthday.isoformat()
        }
        
        logger.info(f"Returning astrology response: {response}")
        return JSONResponse(content=response)
        
    except Exception as e:
        logger.error(f"Error in astrology signs endpoint: {e}", exc_info=True)
        return JSONResponse(
            content={"error": "Internal server error"},
            status_code=500
        )

@app.get("/api/astrology/horoscope")
async def get_horoscope(sign: str, day: str = "today"):
    """Get daily horoscope for a zodiac sign."""
    try:
        # Validate sign
        valid_signs = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
                      "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]
        
        sign_match = next((s for s in valid_signs if s.lower() == sign.lower()), None)
        
        if not sign_match:
            return JSONResponse(
                content={"error": f"Invalid sign '{sign}'. Valid signs: {', '.join(valid_signs)}"},
                status_code=400
            )
        
        # Validate day
        valid_days = ["yesterday", "today", "tomorrow"]
        if day not in valid_days:
            return JSONResponse(
                content={"error": f"Invalid day '{day}'. Valid days: {', '.join(valid_days)}"},
                status_code=400
            )
        
        # Get horoscope text and stats
        text, stats = await _fetch_horoscope_data(sign_match, day)
        
        if not text:
            return JSONResponse(
                content={"error": f"Could not generate horoscope for {sign_match} for {day}."},
                status_code=500
            )
        
        # Get additional sign data
        sign_data = await _find_western_sign_data(sign_match)
        
        response = {
            "sign": sign_match,
            "day": day,
            "text": text,
            "stats": stats,
            "sign_data": sign_data
        }
        
        return JSONResponse(content=response)
        
    except Exception as e:
        logger.error(f"Error in horoscope endpoint: {e}", exc_info=True)
        return JSONResponse(
            content={"error": "Internal server error"},
            status_code=500
        )

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
    
    logger.info(f"Redirecting unknown path '/{path}' to dashboard")
    return RedirectResponse(url="/")

# Web server startup and shutdown functions
async def monitor_cloudflare_tunnel():
    """Periodically checks if the Cloudflare tunnel is active."""
    global _tunnel_process, _public_url
    while True:
        await asyncio.sleep(60)  # Check every 60 seconds
        
        if _tunnel_process and _tunnel_process.poll() is None:
            logger.info("Cloudflare tunnel is running normally")
        else:
            logger.warning("Cloudflare tunnel process is not running. Attempting to restart...")
            try:
                await start_cloudflare_tunnel()
            except Exception as e:
                logger.error(f"Failed to restart Cloudflare tunnel: {e}")

async def start_cloudflare_tunnel():
    """Start the Cloudflare tunnel process."""
    global _tunnel_process, _public_url
    
    try:
        # Kill any existing cloudflared processes
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] and 'cloudflared' in proc.info['name'].lower():
                logger.info(f"Killing existing cloudflared process: PID {proc.info['pid']}")
                proc.kill()
                proc.wait(timeout=5)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
        pass
    
    await asyncio.sleep(2)
    
    try:
        # Start Cloudflare tunnel
        config_path = os.path.join(project_root, 'cloudflared-config', 'config.yml')
        cmd = [
            'cloudflared.exe',
            'tunnel', 
            '--config', config_path,
            'run', 'discord-bot'
        ]
        
        logger.info("Starting Cloudflare tunnel...")
        _tunnel_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=project_root
        )
        
        # Wait a moment for tunnel to establish
        await asyncio.sleep(5)
        
        if _tunnel_process.poll() is None:
            _public_url = "https://reaper.qzz.io"
            logger.info(f"Cloudflare tunnel started successfully. Public URL: {_public_url}")
        else:
            stdout, stderr = _tunnel_process.communicate()
            logger.error(f"Cloudflare tunnel failed to start. stdout: {stdout}, stderr: {stderr}")
            _tunnel_process = None
            
    except Exception as e:
        logger.error(f"Error starting Cloudflare tunnel: {e}")
        _tunnel_process = None

async def run_web_server(bot: commands.Bot):
    """Start the web server and Cloudflare tunnel."""
    global _bot_instance, _server_instance, _tunnel_process, _public_url
    _bot_instance = bot
    port = get_service_port(SERVICE_WEB_SERVER)
    
    # Ensure the port is free before starting the server
    kill_process_on_port(port)
    
    # Start Cloudflare tunnel
    try:
        await start_cloudflare_tunnel()
    except Exception as e:
        logger.error(f"Failed to start Cloudflare tunnel: {e}")
        _public_url = None

    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    _server_instance = uvicorn.Server(config)
    
    logger.info(f"Starting web server on port {port}")
    
    # Run the server and the tunnel monitor concurrently
    server_task = asyncio.create_task(_server_instance.serve())
    monitor_task = asyncio.create_task(monitor_cloudflare_tunnel())
    
    await asyncio.gather(server_task, monitor_task)

async def shutdown_web_server():
    """Shutdown the web server and Cloudflare tunnel gracefully."""
    global _server_instance, _tunnel_process, _public_url
    if _server_instance:
        logger.info("Shutting down web server...")
        await _server_instance.shutdown()
        _server_instance = None
    
    # Stop Cloudflare tunnel
    if _tunnel_process:
        logger.info("Stopping Cloudflare tunnel...")
        try:
            _tunnel_process.terminate()
            _tunnel_process.wait(timeout=10)
            logger.info("Cloudflare tunnel stopped successfully")
        except subprocess.TimeoutExpired:
            logger.warning("Cloudflare tunnel did not stop gracefully, forcing kill...")
            _tunnel_process.kill()
            _tunnel_process.wait()
        except Exception as e:
            logger.error(f"Error stopping Cloudflare tunnel: {e}")
        _tunnel_process = None
    
    # Kill any remaining cloudflared processes
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] and 'cloudflared' in proc.info['name'].lower():
                logger.info(f"Killing remaining cloudflared process: PID {proc.info['pid']}")
                proc.kill()
                proc.wait(timeout=3)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
        pass
    
    _public_url = None

_public_url = None
_tunnel_process = None

def get_public_url():
    """Returns the Cloudflare tunnel public URL."""
    return _public_url

# Rock Paper Scissors API routes
class RPSRequest(BaseModel):
    theme: str
    playerChoice: str
    playerHistory: List[str] = []

# Main execution block for standalone server
if __name__ == "__main__":
    import asyncio
    
    async def run_standalone_server():
        """Run the web server without a bot instance."""
        port = get_service_port(SERVICE_WEB_SERVER)
        
        # Ensure the port is free
        kill_process_on_port(port)
        
        config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
        server = uvicorn.Server(config)
        
        logger.info(f"Starting standalone web server on port {port}")
        await server.serve()
    
    # Run the standalone server
    asyncio.run(run_standalone_server())
    playerHistory: List[str] = []

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

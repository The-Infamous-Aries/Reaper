#!/usr/bin/env python3
"""
Reaper Bot - Comprehensive Startup Sequence
Handles dependency checking, Discord bot initialization, and web server setup in the correct order.
"""

from __future__ import annotations

import os
import sys
import subprocess
import logging
import asyncio
import importlib
from datetime import datetime
from pathlib import Path
from Systems.Functions.irs_wars_manager import sync_wars
from Systems.Functions.irs_nations_manager import sync_nations
from Systems.Functions.last_seen import save_last_seen, get_last_seen

# Global bot instance reference for other modules
bot_instance = None

# Discord imports - will be available after dependency checking
commands = None
discord = None

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('reaper_startup.log', mode='w', encoding='utf-8')
    ]
)
logger = logging.getLogger("Reaper.Startup")

# Project pimaths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(SCRIPT_DIR, ".venv")
NODE_MODULES_DIR = os.path.join(SCRIPT_DIR, "node_modules")
REQUIREMENTS_FILE = os.path.join(SCRIPT_DIR, "requirements.txt")
PACKAGE_JSON = os.path.join(SCRIPT_DIR, "package.json")

# Virtual environment paths
if os.name == 'nt':
    PYTHON_EXECUTABLE = os.path.join(VENV_DIR, "Scripts", "python.exe")
    PIP_EXECUTABLE = os.path.join(VENV_DIR, "Scripts", "pip.exe")
else:
    PYTHON_EXECUTABLE = os.path.join(VENV_DIR, "bin", "python")
    PIP_EXECUTABLE = os.path.join(VENV_DIR, "bin", "pip")

def check_python_venv() -> bool:
    """Check if Python virtual environment exists and is valid."""
    logger.info("Checking Python virtual environment...")
    
    if not os.path.exists(VENV_DIR):
        logger.warning("❌ Virtual environment not found")
        return False
    
    if not os.path.exists(PYTHON_EXECUTABLE):
        logger.warning("❌ Python executable not found in virtual environment")
        return False
    
    try:
        # Test if we can import basic packages
        result = subprocess.run([
            PYTHON_EXECUTABLE, "-c", 
            "import sys; print(sys.version); import discord; print('discord.py:', discord.__version__)"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("✅ Python virtual environment is valid")
            logger.info(f"   Python version: {result.stdout.strip()}")
            return True
        else:
            logger.warning(f"❌ Virtual environment test failed: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"❌ Error checking virtual environment: {e}")
        return False

def check_node_modules() -> bool:
    """Check if Node.js dependencies are installed."""
    logger.info("Checking Node.js dependencies...")
    
    if not os.path.exists(NODE_MODULES_DIR):
        logger.warning("❌ node_modules not found")
        return False
    
    if not os.path.exists(PACKAGE_JSON):
        logger.warning("❌ package.json not found")
        return False
    
    try:
        # Check for key dependencies
        key_packages = ['bootstrap', 'three', 'gsap']
        missing_packages = []
        
        for package in key_packages:
            package_path = os.path.join(NODE_MODULES_DIR, package)
            if not os.path.exists(package_path):
                missing_packages.append(package)
        
        if missing_packages:
            logger.warning(f"❌ Missing Node.js packages: {missing_packages}")
            return False
        else:
            logger.info("✅ Node.js dependencies are installed")
            return True
    except Exception as e:
        logger.error(f"❌ Error checking Node.js dependencies: {e}")
        return False

def install_python_dependencies() -> bool:
    """Install Python dependencies from requirements.txt."""
    logger.info("Installing Python dependencies...")
    
    try:
        if not os.path.exists(REQUIREMENTS_FILE):
            logger.error(f"❌ Requirements file not found: {REQUIREMENTS_FILE}")
            return False
        
        # Create virtual environment if it doesn't exist
        if not os.path.exists(VENV_DIR):
            logger.info("Creating virtual environment...")
            result = subprocess.run([sys.executable, "-m", "venv", VENV_DIR], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"❌ Failed to create virtual environment: {result.stderr}")
                return False
        
        # Install requirements
        logger.info("Installing requirements from requirements.txt...")
        result = subprocess.run([
            PIP_EXECUTABLE, "install", "-r", REQUIREMENTS_FILE, "--upgrade"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("✅ Python dependencies installed successfully")
            return True
        else:
            logger.error(f"❌ Failed to install Python dependencies: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"❌ Error installing Python dependencies: {e}")
        return False

def install_node_dependencies() -> bool:
    """Install Node.js dependencies from package.json."""
    logger.info("Installing Node.js dependencies...")
    
    try:
        if not os.path.exists(PACKAGE_JSON):
            logger.error(f"❌ package.json not found: {PACKAGE_JSON}")
            return False
        
        # Check if npm is available
        result = subprocess.run(["npm", "--version"], capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("❌ npm not found. Please install Node.js and npm")
            return False
        
        # Install dependencies
        logger.info("Running npm install...")
        result = subprocess.run(["npm", "install"], 
                                cwd=SCRIPT_DIR, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("✅ Node.js dependencies installed successfully")
            return True
        else:
            logger.error(f"❌ Failed to install Node.js dependencies: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"❌ Error installing Node.js dependencies: {e}")
        return False

def setup_dependencies() -> bool:
    """Setup all dependencies in the correct order."""
    logger.info("🚀 Starting dependency setup...")
    
    # Check Python dependencies
    python_ok = check_python_venv()
    if not python_ok:
        logger.info("Python dependencies missing or invalid, installing...")
        if not install_python_dependencies():
            logger.error("❌ Failed to setup Python dependencies")
            return False
    
    # Check Node.js dependencies
    node_ok = check_node_modules()
    if not node_ok:
        logger.info("Node.js dependencies missing or invalid, installing...")
        if not install_node_dependencies():
            logger.error("❌ Failed to setup Node.js dependencies")
            return False
    
    logger.info("✅ All dependencies are ready")
    return True

# Discord Bot Setup
class ReaperBot:
    """Main bot class with proper startup sequence."""
    
    def __init__(self):
        self.bot: Optional['commands.Bot'] = None
        self.web_server_started = False
        self.pnw_queries_fetched = False
        
    async def create_bot_instance(self):
        """Create and configure the Discord bot instance."""
        logger.info("Creating Discord bot instance...")
        
        # Import required modules
        from Systems.Functions.user_data_manager import UserDataManager
        from Systems.Functions.config import DISCORD_TOKEN, OWNER_ID, ARIES_USER_ID, ADMIN_USER_ID
        
        # Configure intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        
        # Create bot instance
        bot = commands.Bot(
            command_prefix='r.',
            intents=intents,
            owner_id=OWNER_ID,
            help_command=None
        )
        
        # Add bot attributes
        bot.start_time = datetime.now()
        bot.logger = logging.getLogger("Reaper.Bot")
        bot.data_manager = UserDataManager()
        bot.market_prices: Dict[str, float] = {}
        
        self.bot = bot
        return bot

    async def load_cogs(self) -> int:
        """Load cogs from specific sets to better identify issues."""
        logger.info("Loading cogs from specified sets...")
        
        # Define cog sets as requested
        cog_sets = {
            "Admin": [
                "Systems.admin",
                "Systems.info"
            ],
            "Mythical": [
                "Systems.Astrology.signs",
                "Systems.Astrology.reading"
            ],
            "Fun": [
                "Systems.Fun.zombie",
                "Systems.Fun.goodevil", 
                "Systems.Fun.fun_system",
                "Systems.Fun.compete"
            ],
            "Pets": [
                # "Systems.Pets.pets_commands"  # Disabled: pet commands moved to web-only
            ],
            "PnW": [
                "Systems.PnW.pnwhopper",
            ],
            "Management": [
                "Systems.Functions.nations_manager_cog"
            ],
            "Tickets": [
                "Systems.Tickets.tickets"
            ]
        }
        
        total_loaded = 0
        
        # Load each set separately for better error tracking
        for set_name, cogs in cog_sets.items():
            logger.info(f"Loading {set_name} set...")
            set_loaded = 0
            
            for cog_path in cogs:
                try:
                    try:
                        await self.bot.load_extension(cog_path)
                        logger.info(f"  ✅ Loaded {set_name}: {cog_path}")
                    except commands.ExtensionAlreadyLoaded:
                        await self.bot.reload_extension(cog_path)
                        logger.info(f"  🔄 Reloaded {set_name}: {cog_path}")
                    set_loaded += 1
                except Exception as e:
                    logger.error(f"  ❌ Failed to load {set_name} cog {cog_path}: {e}")
            
            logger.info(f"  📊 {set_name} set: {set_loaded}/{len(cogs)} cogs loaded")
            total_loaded += set_loaded
        
        logger.info(f"✅ Total cogs loaded: {total_loaded}")
        return total_loaded
    
    async def sync_commands(self) -> bool:
        """Sync command tree with Discord."""
        logger.info("Syncing command tree with Discord...")
        
        try:
            synced = await self.bot.tree.sync()
            logger.info(f"✅ Synced {len(synced)} application commands")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to sync command tree: {e}")
            return False
    
    async def fetch_pnw_queries(self) -> bool:
        """Fetch all PnW queries that need to be loaded on startup."""
        logger.info("Fetching PnW queries...")
        
        try:
            # Import PnW query modules
            from Systems.PnW.Util.query import create_v3_query_instance, get_game_info
            
            # Initialize query instance
            query_instance = create_v3_query_instance()
            if not query_instance:
                logger.error("❌ Failed to create PnW query instance")
                return False
            
            # Fetch game info
            game_info = await get_game_info()
            if game_info:
                logger.info("✅ PnW game info fetched successfully")
            else:
                logger.warning("⚠️  Could not fetch PnW game info")
            
            self.pnw_queries_fetched = True
            return True
            
        except Exception as e:
            logger.error(f"❌ Error fetching PnW queries: {e}")
            return False
    
    async def start_web_server(self) -> bool:
        """Start the web server after Discord is fully ready."""
        if self.web_server_started:
            logger.info("Web server is already running")
            return True
            
        logger.info("Starting web server...")
        
        try:
            # Import web server module
            from Systems.Functions.web_server import run_web_server
            import Systems.Functions.web_server as web_server_module
            
            # Set bot instance in web server
            web_server_module.set_bot_instance(self.bot)
            
            # Start web server in background
            self.web_task = asyncio.create_task(run_web_server(self.bot))
            
            # Wait for uvicorn's own `started` flag — no HTTP round-trip needed.
            # This avoids the health-check loop starving under a busy event loop.
            max_wait = 30
            waited = 0
            while waited < max_wait:
                # Check if the task crashed before it could start
                if self.web_task.done():
                    try:
                        self.web_task.result()
                    except Exception:
                        logger.error("❌ Web server task failed:", exc_info=True)
                    return False

                # uvicorn.Server sets .started = True once it's bound and listening
                server = web_server_module._server_instance
                if server is not None and server.started:
                    logger.info("✅ Web server is up and listening")
                    self.web_server_started = True
                    return True

                await asyncio.sleep(0.25)
                waited += 0.25

            logger.error("❌ Web server failed to start within 30 seconds")
            return False
            
        except Exception as e:
            logger.error(f"❌ Failed to start web server: {e}")
            return False
    
    async def setup_hook(self):
        """Bot setup hook - runs before connecting to Discord."""
        logger.info("🚀 Starting bot setup hook...")
        
        # Load cogs — command tree sync happens in on_ready after all cogs
        # (including NationsManagerCog) are fully registered on the tree.
        cogs_loaded = await self.load_cogs()
        if cogs_loaded == 0:
            logger.warning("⚠️  No cogs were loaded")
        
        # Start user data sync task
        asyncio.create_task(self._periodic_user_sync())
        # Start beige notification checker
        asyncio.create_task(self._beige_notification_loop())
    
    async def on_ready(self):
        """Called when the bot is fully connected to Discord."""
        setup_runtime_logging()
        logger.info(f"✅ Bot is online as {self.bot.user} (ID: {self.bot.user.id})")
        logger.info(f"📡 Connected to {len(self.bot.guilds)} guilds")

        # ── Phase 1: Fast, non-blocking setup ────────────────────────────────
        # Set presence as a background task — no need to await a Discord API call
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"over PnW | {self.bot.command_prefix}help"
        )
        asyncio.create_task(self.bot.change_presence(activity=activity))

        # Sync command tree — only once, here, after all cogs are loaded
        await self.sync_commands()

        # ── Phase 2: Background data sync (non-blocking) ─────────────────────
        # Run war sync and nations sync concurrently in the background so they
        # don't delay the web server or subscriptions.
        last_seen = get_last_seen()

        async def _background_sync():
            tasks = []
            if last_seen:
                logger.info(f"Bot was last seen at {last_seen}. Syncing missed data in background...")
                tasks.append(sync_wars(since=last_seen))
            tasks.append(sync_nations())
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    logger.error(f"Background sync error: {r}")
                elif isinstance(r, dict):
                    logger.info(f"Nations sync complete: {r}")

        asyncio.create_task(_background_sync())

        # ── Phase 3: Start web server ─────────────────────────────────────────
        # Subscriptions are now handled by PnWHarvester (separate process).
        # Reaper is read-only against GlobalNations.db and GlobalWars.db.
        await self.start_web_server()

        # ── Phase 4: Cloudflare tunnel (background) ───────────────────────────
        from Systems.Functions.config import USE_CLOUDFLARE_TUNNEL
        if USE_CLOUDFLARE_TUNNEL:
            from Systems.Functions.utils import start_cloudflare_tunnel_async, monitor_tunnel_and_server
            try:
                await start_cloudflare_tunnel_async()
            except Exception as e:
                logger.error(f"Failed to start Cloudflare tunnel: {e}")
            self.monitor_task = asyncio.create_task(monitor_tunnel_and_server())

        logger.info(f"📊 Bot is in {len(self.bot.guilds)} servers")

    async def on_disconnect(self):
        """Called when the bot disconnects."""
        logger.info("Bot has disconnected. Saving last seen time.")
        save_last_seen()

    async def start_pnw_subscription(self):
        """Subscriptions are now handled by PnWHarvester (separate process)."""
        logger.info("PnW subscriptions are managed by PnWHarvester — skipping")

    async def _beige_notification_loop(self):
        """
        Every 2 minutes, check all beige alerts in alerts.db.

        Two-stage alert system based on *time remaining*, not just turn count:
          Stage 1 — 15 min < time_remaining <= 2h 15 min AND not yet warned
                    → "~2 hours left" warning DM (sent when entering the last turn).
                      Alert is kept; warned_turn flag set to 1.
          Stage 2 — time_remaining <= 15 min  → "leaving beige in ~15 min" final DM.
                      Alert is deleted.

        Also drains the beige_early_exit_queue written by the harvester when it
        detects a nation left beige early (color change / beige_turns → 0 via the
        nation/update WebSocket subscription).

        Using time-based thresholds (rather than raw beige_turns == 1/0) prevents
        the Stage 1 message from firing with a misleading "~2 hours" label when the
        nation is already deep into its last turn, and ensures Stage 2 always fires
        before the nation actually leaves beige.

        Only military units are queried from the API; projected loot comes from
        the saved projected_loot field set when the alert was created.
        """
        logger.info("🔔 Starting beige notification loop...")

        while True:
            try:
                await asyncio.sleep(120)  # check every 2 minutes

                if not self.bot or not self.bot.is_ready():
                    continue

                from web.api.raids_api import (
                    _get_all_beige_alerts,
                    _delete_beige_alert_by_id,
                    _mark_beige_alert_warned,
                    _update_beige_alert_turns,
                    _compute_beige_expiry_utc,
                )
                from datetime import datetime, timezone, timedelta
                from PnWHarvester.db.holdings_db import HoldingsDB
                from Systems.Functions.db_paths  import HOLDINGS_DB_STR
                from Systems.Functions.beige_alerts_db import drain_early_exit_queue

                # ── Drain early-exit queue (harvester → reaper DM bridge) ─────
                # The harvester writes here when it detects a nation left beige
                # early via the nation/update WebSocket subscription.
                try:
                    early_exits = await drain_early_exit_queue()
                    for ex in early_exits:
                        uid         = str(ex["user_id"])
                        nid         = str(ex["nation_id"])
                        nation_name = ex.get("nation_name") or f"nation {nid}"
                        proj_loot   = float(ex.get("projected_loot") or 0)
                        try:
                            discord_user = await self.bot.fetch_user(int(uid))
                            if discord_user:
                                embed = discord.Embed(
                                    title=f"⚠️ Beige Ended Early — {nation_name}",
                                    description=(
                                        f"**[{nation_name}](https://politicsandwar.com/nation/id={nid})**"
                                        f" has **left beige early** — they are now vulnerable!"
                                    ),
                                    color=0xFF4444,
                                )
                                embed.add_field(
                                    name="💰 Last Projected Loot",
                                    value=f"**${proj_loot:,.0f}**" if proj_loot > 0 else "Unknown",
                                    inline=True,
                                )
                                embed.set_footer(text="Reaper • Beige Alert — nation left beige before expected")
                                await discord_user.send(embed=embed)
                                logger.info(
                                    f"Sent early-exit beige DM to user {uid} for nation {nid} ({nation_name})"
                                )
                        except Exception as e:
                            logger.warning(f"Could not send early-exit beige DM to user {uid}: {e}")
                except Exception as e:
                    logger.warning(f"beige early-exit queue drain failed: {e}")

                alerts = await _get_all_beige_alerts()
                if not alerts:
                    continue

                # Only fetch nations that are close enough to need a check.
                # Use time-based relevance: within 2h 30min of expiry (gives a
                # comfortable buffer so we never miss the Stage 1 window).
                now_utc = datetime.now(timezone.utc)
                STAGE1_THRESHOLD = 2 * 3600 + 15 * 60   # 2h 15m in seconds
                STAGE2_THRESHOLD = 15 * 60               # 15 min in seconds

                def _seconds_remaining(alert: dict) -> int:
                    expiry = _compute_beige_expiry_utc(
                        int(alert.get("beige_turns") or 0),
                        alert.get("created_at") or "",
                    )
                    return int((expiry - now_utc).total_seconds())

                relevant = [a for a in alerts if _seconds_remaining(a) <= STAGE1_THRESHOLD]
                if not relevant:
                    continue

                nation_ids = list({str(a["nation_id"]) for a in relevant})

                # Read nation data from GlobalNationsDB — no API call needed.
                # The harvester keeps this DB current via WebSocket subscriptions.
                nation_cache: dict = {}
                try:
                    from PnWHarvester.db.global_nations_db import GlobalNationsDB
                    from Systems.Functions.db_paths import GLOBAL_NATIONS_DB_STR
                    _gdb = GlobalNationsDB(GLOBAL_NATIONS_DB_STR)
                    for nid in nation_ids:
                        try:
                            nation_row = await _gdb.get_nation(int(nid))
                            if nation_row:
                                nation_cache[nid] = nation_row
                        except Exception as e:
                            logger.warning(f"Could not read nation {nid} from GlobalNationsDB: {e}")
                except Exception as e:
                    logger.warning(f"Could not open GlobalNationsDB for beige check: {e}")

                # Refresh stored beige_turns for all relevant alerts so the
                # filter stays accurate on the next poll cycle.
                # Also reset warned_turn if beige_turns increased (alert was
                # re-added or nation gained turns) so Stage 1 fires again.
                for alert in relevant:
                    nid = str(alert["nation_id"])
                    if nid in nation_cache:
                        fresh_turns = int(nation_cache[nid].get("beige_turns") or 0)
                        stored_turns = int(alert.get("beige_turns") or 0)
                        if fresh_turns != stored_turns:
                            await _update_beige_alert_turns(alert["id"], fresh_turns)
                            # Patch the in-memory alert so the stage checks below
                            # use the fresh value without a second DB round-trip
                            alert["beige_turns"] = fresh_turns

                # Refresh projected_loot from holdings.db so alerts always show
                # the current estimate (reflects spending since alert was created).
                try:
                    _hdb = HoldingsDB(HOLDINGS_DB_STR)
                    _alert_nation_ids = [int(a["nation_id"]) for a in relevant]
                    _holdings_map = await _hdb.get_holdings_bulk(_alert_nation_ids)

                    from web.api.raids_api import LOOT_MULTIPLIERS as _LM, RESOURCES as _RES
                    from Systems.Functions.database_manager import get_latest_resource_prices as _get_prices_raw

                    _prices: dict = {}
                    try:
                        _raw_prices = await _get_prices_raw()
                        if _raw_prices:
                            _prices = {k.lower(): v.get("sell", 0) for k, v in _raw_prices.items() if v.get("sell", 0) > 0}
                    except Exception:
                        pass

                    for alert in relevant:
                        _nid = int(alert["nation_id"])
                        _h   = _holdings_map.get(_nid)
                        if not _h:
                            continue
                        # Recalculate projected loot using Pirate+APE vs the nation's war policy
                        _nation_in_cache = nation_cache.get(str(_nid)) or {}
                        _def_policy = (_nation_in_cache.get("war_policy") or "fortress").lower()
                        if "." in _def_policy:
                            _def_policy = _def_policy.rsplit(".", 1)[-1].lower()
                        _bp  = _LM["war_type"]["raid"]
                        _off = _LM["offense"]["pirate"] * _LM["offense"]["ape"]
                        _dfn = _LM["defense"].get(_def_policy, 1.0)
                        _pct = _bp * _off * _dfn
                        _cash = max(0.0, float(_h.get("money_held") or 0)) * _pct
                        _rss_val = sum(
                            max(0.0, float(_h.get(f"{r}_held") or 0)) * _pct * _prices.get(r, 0)
                            for r in _RES
                        )
                        alert["projected_loot"] = _cash + _rss_val
                except Exception as _he:
                    logger.warning(f"Holdings refresh for beige alerts failed: {_he}")

                for alert in relevant:
                    nid    = str(alert["nation_id"])
                    uid    = str(alert["user_id"])
                    nation = nation_cache.get(nid)

                    if not nation:
                        continue

                    warned_turn  = int(alert.get("warned_turn") or 0)
                    proj_loot    = float(alert.get("projected_loot") or 0)
                    nation_name  = nation.get("nation_name") or alert.get("nation_name")

                    # Compute actual seconds remaining from the live beige_turns
                    # value. We snap now_utc to the current turn boundary and add
                    # live_turns * 2h — this is equivalent to _compute_beige_expiry_utc
                    # but uses now_utc as the anchor so we don't depend on the
                    # (potentially stale) created_at field in the in-memory alert.
                    live_turns = int(nation.get("beige_turns") or 0)
                    hour_snapped = (now_utc.hour // 2) * 2
                    current_turn_start = now_utc.replace(hour=hour_snapped, minute=0, second=0, microsecond=0)
                    expiry = current_turn_start + timedelta(hours=live_turns * 2)
                    secs_left = int((expiry - now_utc).total_seconds())

                    def _mil_field(n: dict) -> str:
                        return (
                            f"Soldiers: **{int(n.get('soldiers') or 0):,}**\n"
                            f"Tanks: **{int(n.get('tanks') or 0):,}**\n"
                            f"Aircraft: **{int(n.get('aircraft') or 0):,}**\n"
                            f"Ships: **{int(n.get('ships') or 0):,}**\n"
                            f"Missiles: **{int(n.get('missiles') or 0):,}**\n"
                            f"Nukes: **{int(n.get('nukes') or 0):,}**"
                        )

                    def _nation_info_field(n: dict) -> str:
                        return (
                            f"Score: **{float(n.get('score') or 0):,.0f}**\n"
                            f"Cities: **{n.get('num_cities') or 0}**\n"
                            f"War Policy: **{n.get('war_policy') or 'Unknown'}**"
                        )

                    def _fmt_time(seconds: int) -> str:
                        """Human-readable time string for the notification message."""
                        if seconds <= 0:
                            return "any moment"
                        h = seconds // 3600
                        m = (seconds % 3600) // 60
                        if h > 0 and m > 0:
                            return f"~{h}h {m}m"
                        if h > 0:
                            return f"~{h}h"
                        return f"~{m}m"

                    # ── Stage 2: ≤ 15 min remaining — fire before Stage 1 check
                    # so a nation that skips straight from >2h to <15min still
                    # gets the final alert even if Stage 1 was never sent.
                    if secs_left <= STAGE2_THRESHOLD:
                        try:
                            discord_user = await self.bot.fetch_user(int(uid))
                            if discord_user:
                                time_str = _fmt_time(secs_left)
                                embed = discord.Embed(
                                    title=f"🚨 Beige Expiring — {nation_name}",
                                    description=(
                                        f"**[{nation_name}](https://politicsandwar.com/nation/id={nid})**"
                                        f" is leaving beige in **{time_str}**!"
                                    ),
                                    color=0xD2B48C,
                                )
                                embed.add_field(name="🪖 Current Military", value=_mil_field(nation), inline=True)
                                embed.add_field(
                                    name="💰 Projected Loot",
                                    value=f"**${proj_loot:,.0f}**" if proj_loot > 0 else "Unknown",
                                    inline=True,
                                )
                                embed.add_field(name="📊 Nation Info", value=_nation_info_field(nation), inline=True)
                                embed.set_footer(text="Reaper • Beige Alert — this alert has been removed")
                                await discord_user.send(embed=embed)
                                logger.info(f"Sent final beige DM to user {uid} for nation {nid} ({time_str} remaining)")
                        except Exception as e:
                            logger.warning(f"Could not send final beige DM to user {uid}: {e}")

                        await _delete_beige_alert_by_id(alert["id"])

                    # ── Stage 1: > 15 min but ≤ 2h 15 min remaining, not yet warned ─
                    elif secs_left <= STAGE1_THRESHOLD and not warned_turn:
                        try:
                            discord_user = await self.bot.fetch_user(int(uid))
                            if discord_user:
                                time_str = _fmt_time(secs_left)
                                embed = discord.Embed(
                                    title=f"⏰ Beige Warning — {nation_name}",
                                    description=(
                                        f"**[{nation_name}](https://politicsandwar.com/nation/id={nid})**"
                                        f" has **{time_str}** of beige remaining!"
                                    ),
                                    color=0xFFA500,
                                )
                                embed.add_field(name="🪖 Current Military", value=_mil_field(nation), inline=True)
                                embed.add_field(
                                    name="💰 Projected Loot",
                                    value=f"**${proj_loot:,.0f}**" if proj_loot > 0 else "Unknown",
                                    inline=True,
                                )
                                embed.add_field(name="📊 Nation Info", value=_nation_info_field(nation), inline=True)
                                embed.set_footer(text="Reaper • Beige Alert — final warning coming in ~15 min")
                                await discord_user.send(embed=embed)
                                logger.info(f"Sent beige warning to user {uid} for nation {nid} ({time_str} remaining)")
                            await _mark_beige_alert_warned(alert["id"])
                        except Exception as e:
                            logger.warning(f"Could not send beige warning to user {uid}: {e}")

            except Exception as e:
                logger.error(f"Error in beige notification loop: {e}", exc_info=True)
                await asyncio.sleep(60)
        
    async def _periodic_user_sync(self):
        """Periodically sync Discord user data for active users."""
        logger.info("🔄 Starting periodic user sync task...")
        
        while True:
            try:
                await asyncio.sleep(300)  # Wait 5 minutes between syncs
                
                if not self.bot or not self.bot.is_ready():
                    continue
                
                # Get list of recently active users (last 24 hours)
                from Systems.Functions.pets_db import pets_db
                import aiosqlite
                
                async with aiosqlite.connect(pets_db.db_path) as db:
                    # Get users who have been active recently or have stale data
                    async with db.execute("""
                        SELECT DISTINCT user_id FROM users 
                        WHERE last_updated IS NULL 
                           OR last_updated < datetime('now', '-1 day')
                        LIMIT 50
                    """) as cursor:
                        rows = await cursor.fetchall()
                        user_ids = [row[0] for row in rows]
                
                if user_ids:
                    logger.info(f"🔄 Syncing {len(user_ids)} users with stale data...")
                    from Systems.Functions.discord_user_sync import sync_multiple_users
                    results = await sync_multiple_users(user_ids, self.bot)
                    
                    synced_count = sum(1 for result in results.values() if result is not None)
                    logger.info(f"✅ Synced {synced_count}/{len(user_ids)} users")
                
            except Exception as e:
                logger.error(f"Error in periodic user sync: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying on error

def setup_runtime_logging():
    """Switch logging to the runtime log file."""
    root_logger = logging.getLogger()
    # Remove the startup file handler
    for handler in root_logger.handlers[:]:
        if isinstance(handler, logging.FileHandler) and "reaper_startup.log" in handler.baseFilename:
            root_logger.removeHandler(handler)
    # Add the runtime file handler
    runtime_handler = logging.FileHandler('reaper_bot.log', mode='w', encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    runtime_handler.setFormatter(formatter)
    root_logger.addHandler(runtime_handler)
    logger.info("Logging configured for runtime.")


async def main():
    """Main startup function."""
    global bot_instance
    logger.info("🚀 Starting Reaper Bot...")
    
    # Step 1: Check and install dependencies
    if not setup_dependencies():
        logger.error("❌ Failed to setup dependencies. Exiting.")
        return
    
    # Step 2: Create and setup Discord bot
    try:
        # Import Discord modules and make them globally available
        global discord, commands
        import discord
        from discord.ext import commands
        from Systems.Functions.config import DISCORD_TOKEN
        
        # Create bot instance
        reaper = ReaperBot()
        bot_instance = reaper  # Store globally for other modules
        bot = await reaper.create_bot_instance()
        
        # Make bot instance globally accessible for other modules
        import sys
        sys.modules[__name__].bot_instance = reaper
        
        # Set event handlers
        bot.setup_hook = reaper.setup_hook
        bot.on_ready = reaper.on_ready
        
        # Step 3: Start the bot with reconnect logic
        logger.info("Connecting to Discord...")
        max_retries = 5
        base_delay = 5  # seconds
        for attempt in range(1, max_retries + 1):
            try:
                await bot.start(DISCORD_TOKEN)
                break  # clean exit (e.g. KeyboardInterrupt propagated as SystemExit)
            except discord.HTTPException as e:
                if e.status == 429:
                    # IP-level rate limit — discord.py already waited internally,
                    # but our IP is still hot. Back off much longer before retrying.
                    rate_limit_delay = 60 * attempt  # 60s, 120s, 180s, ...
                    logger.warning(
                        f"⚠️  IP rate limited by Discord (attempt {attempt}/{max_retries}). "
                        f"Waiting {rate_limit_delay}s before retrying..."
                    )
                    try:
                        await bot.close()
                    except Exception:
                        pass
                    if attempt >= max_retries:
                        logger.error("❌ Max retries reached. Could not connect to Discord.")
                        break
                    await asyncio.sleep(rate_limit_delay)
                else:
                    logger.warning(f"⚠️  HTTP error (attempt {attempt}/{max_retries}): {e}")
                    if attempt >= max_retries:
                        logger.error("❌ Max retries reached. Could not connect to Discord.")
                        break
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.info(f"Retrying in {delay}s...")
                    try:
                        await bot.close()
                    except Exception:
                        pass
                    await asyncio.sleep(delay)
            except (discord.ConnectionClosed, discord.GatewayNotFound) as e:
                logger.warning(f"⚠️  Discord gateway error (attempt {attempt}/{max_retries}): {e}")
                if attempt >= max_retries:
                    logger.error("❌ Max retries reached. Could not connect to Discord.")
                    break
                delay = base_delay * (2 ** (attempt - 1))
                logger.info(f"Retrying in {delay}s...")
                try:
                    await bot.close()
                except Exception:
                    pass
                await asyncio.sleep(delay)
            except Exception as e:
                # Covers ClientConnectorError (DNS/network failures) and anything else
                logger.warning(f"⚠️  Connection failed (attempt {attempt}/{max_retries}): {e}")
                if attempt >= max_retries:
                    logger.error("❌ Max retries reached. Could not connect to Discord.")
                    break
                delay = base_delay * (2 ** (attempt - 1))
                logger.info(f"Retrying in {delay}s...")
                try:
                    await bot.close()
                except Exception:
                    pass
                await asyncio.sleep(delay)
            else:
                # bot.start() returned cleanly — no retry needed
                break

            # Close the old bot instance cleanly before creating a fresh one.
            # Reusing the same bot after a failed start() leaves aiohttp
            # ClientSessions open and the internal connector in a broken state.
            reaper = ReaperBot()
            bot_instance = reaper
            sys.modules[__name__].bot_instance = reaper
            bot = await reaper.create_bot_instance()
            bot.setup_hook = reaper.setup_hook
            bot.on_ready = reaper.on_ready

    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}")
        return

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot shutdown requested by user")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
import os
import sys
import logging
import time
import traceback
from datetime import datetime
from typing import Dict

import os
import sys
import logging
import time
import traceback
from datetime import datetime
from typing import Dict
import subprocess

# --- Dependency Management ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_PACKAGES_DIR = os.path.join(SCRIPT_DIR, "local_packages")
REQUIREMENTS_FILE = os.path.join(SCRIPT_DIR, "requirements.txt")

def ensure_local_packages():
    if not os.path.exists(LOCAL_PACKAGES_DIR):
        os.makedirs(LOCAL_PACKAGES_DIR)

    # Check for a few critical packages as a heuristic
    # A more robust check would involve parsing requirements.txt and checking each module
    # For now, let's check for 'discord' and 'aiohttp' as key indicators
    missing_critical_packages = False
    critical_modules = ['discord', 'aiohttp', 'pydantic']

    for module_name in critical_modules:
        module_path = os.path.join(LOCAL_PACKAGES_DIR, module_name)
        # For 'discord', its package is 'discord'
        # For 'aiohttp', its package is 'aiohttp'
        # For 'pydantic', its package is 'pydantic'
        if not os.path.exists(module_path) and not os.path.exists(module_path + '.py'):
            logging.warning(f"Critical package '{module_name}' not found in local_packages. Installation required.")
            missing_critical_packages = True
            break
    
    # Also check if local_packages directory is empty after creation
    if not os.listdir(LOCAL_PACKAGES_DIR):
        logging.warning("local_packages directory is empty. Installation required.")
        missing_critical_packages = True

    if missing_critical_packages:
        logging.info("Installing/updating dependencies to local_packages...")
        try:
            # Use sys.executable to ensure pip corresponds to the current Python interpreter
            # Added --upgrade to ensure packages are updated if versions change or they are outdated
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", 
                "-r", REQUIREMENTS_FILE, 
                "--target", LOCAL_PACKAGES_DIR, 
                "--upgrade", "--no-warn-script-location"
            ])
            logging.info("Dependencies installed successfully to local_packages.")
        except subprocess.CalledProcessError as e:
            logging.critical(f"Failed to install dependencies: {e}")
            sys.exit(1)
        except Exception as e:
            logging.critical(f"An unexpected error occurred during dependency installation: {e}")
            sys.exit(1)
    else:
        logging.info("Dependencies already present in local_packages. Skipping installation.")

# Ensure local_packages is in sys.path BEFORE any third-party imports
if LOCAL_PACKAGES_DIR not in sys.path:
    sys.path.insert(0, LOCAL_PACKAGES_DIR)

# Run the dependency check and installation
ensure_local_packages()

# Now, safe to import third-party libraries
import discord
from discord.ext import commands
import asyncio
import json
from datetime import datetime
import inspect
from Systems.Functions import emoji as emoji_mod

# Import UserDataManager for unified data storage
from Systems.Functions.user_data_manager import UserDataManager

# Runtime check: ensure critical dependencies are vendored in local_packages
def log_vendored_dependencies_status():
    """Log whether key third-party packages are loaded from local_packages.
    This helps ensure SparkedHost runs without external pip installs.
    """
    logger = logging.getLogger('VendoredDeps')
    def check_module(name, import_name=None, optional=False):
        mod_name = import_name or name
        try:
            mod = __import__(mod_name)
            path = getattr(mod, '__file__', '') or ''
            source = 'local_packages' if 'local_packages' in (path or '') else 'system'
            logger.info(f"{name}: OK (source={source}, path={path})")
        except Exception as e:
            level = logger.warning if optional else logger.error
            level(f"{name}: MISSING ({'optional' if optional else 'required'}) — {e}")

    logger.info("🔎 Checking vendored dependencies availability...")
    # Core
    check_module('discord')
    check_module('aiohttp')
    check_module('requests')
    check_module('dotenv', import_name='dotenv')
    check_module('tqdm')
    # AIOHTTP ecosystem
    check_module('multidict')
    check_module('frozenlist')
    check_module('async_timeout')
    # Data and typing
    check_module('attrs', import_name='attr')
    check_module('pydantic')
    # Google/Gemini stack (optional in production if disabled)
    check_module('grpc', optional=True)
    check_module('grpc_status', optional=True)
    check_module('protobuf', import_name='google.protobuf', optional=True)
    check_module('httplib2', optional=True)
    # Web scraping / parsing
    check_module('beautifulsoup4', import_name='bs4', optional=True)
    # PnW tooling
    check_module('pnwkit', optional=True)
    # Imaging (used for treaty image; optional fallback exists)
    try:
        from PIL import Image  # noqa: F401
        logger.info("Pillow: OK (source=unknown; check module path)")
    except Exception as e:
        logger.warning(f"Pillow: MISSING (optional) — {e}")

    logger.info("✅ Vendored dependency check completed.")

# Enhanced error handling and logging setup
class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for terminal output"""
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, '')
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)

# Configure logging to avoid duplicates
# Ensure UTF-8 encoding for console output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
elif hasattr(sys.stdout, 'buffer'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Create file handler
file_handler = logging.FileHandler('bot_debug.log', mode='a', encoding='utf-8')
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s | %(levelname)s | %(name)s | %(funcName)s:%(lineno)d | %(message)s'
))

# Create colored console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(ColoredFormatter(
    '%(asctime)s | %(levelname)s | %(name)s | %(funcName)s:%(lineno)d | %(message)s'
))

# Configure root logger to avoid basicConfig
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)

# Clear any existing handlers to prevent duplicates
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# Add our handlers
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# -----------------------------------------------------------------------------
# BOT INITIALIZATION
# -----------------------------------------------------------------------------
# Load configurations from config.py and .env
try:
    from config import DISCORD_TOKEN, COMMAND_PREFIX, OWNER_ID, DATA_DIR
except ImportError:
    logging.critical("❌ Failed to import configuration from config.py. Ensure the file exists.")
    sys.exit(1)

# Initialize bot with required intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True
intents.reactions = True  # Enable reactions intent for Translator
intents.guilds = True     # Enable guilds intent for message fetching

class ReaperBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=COMMAND_PREFIX,
            intents=intents,
            owner_id=OWNER_ID,
            help_command=None
        )
        self.start_time = datetime.now()
        self.logger = logging.getLogger("Reaper.Main")
        self.data_manager = UserDataManager()
        self.market_prices: Dict[str, float] = {}
        
    async def setup_hook(self):
        """Perform initial setup before the bot connects to Discord."""
        self.logger.info("🚀 Starting Bot Setup Hook...")
        log_vendored_dependencies_status()
        
        # Load core systems
        await self.load_extension("Systems.info")
        
        # Load PnW Hopper (Splicer for all PnW sub-modules)
        try:
            from Systems.PnW.pnwhopper import setup as setup_pnw
            await setup_pnw(self)
            self.logger.info("✅ Politics & War systems initialized.")
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize PnW systems: {e}", exc_info=True)
            
        # Load Fun & Utility Systems
        fun_cogs = [
            "Systems.Astrology.signs",
            "Systems.Astrology.reading",
            "Systems.Fun.fun_system", 
            "Systems.Fun.zombie", 
            "Systems.Fun.goodevil", 
            "Systems.Translator.translator",
            "Systems.Fun.compete"
        ]
        for cog in fun_cogs:
            try:
                await self.load_extension(cog)
                self.logger.info(f"✅ Loaded {cog}")
            except Exception as e:
                self.logger.error(f"❌ Failed to load {cog}: {e}")

        try:
            await self.load_extension("Systems.Pets.pets_commands")
            self.logger.info("✅ Pet system commands initialized.")
        except Exception as e:
            self.logger.error(f"❌ Failed to load Pet system: {e}", exc_info=True)

        try:
            synced = await self.tree.sync()
            self.logger.info(f"✅ Synced {len(synced)} application (slash) commands.")
        except Exception as e:
            self.logger.error(f"❌ Failed to sync slash commands: {e}")

    async def on_ready(self):
        self.logger.info(f"✅ Bot is online as {self.user} (ID: {self.user.id})")
        self.logger.info(f"📡 Connected to {len(self.guilds)} guilds.")
        
        # Set presence
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"over PnW | {COMMAND_PREFIX}help"
        )
        await self.change_presence(activity=activity)

bot = ReaperBot()

# Global error handler
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    logging.error(f"Global Command Error: {error}", exc_info=True)

if __name__ == "__main__":
    if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_DISCORD_TOKEN":
        logging.critical("❌ DISCORD_TOKEN is missing in .env file!")
        sys.exit(1)
    
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logging.critical(f"❌ Bot failed to start: {e}")
        traceback.print_exc()

import os
import sys
import logging
import subprocess
import time
import importlib
from datetime import datetime
from typing import Dict

# --- Dependency Management ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_PACKAGES_DIR = os.path.join(SCRIPT_DIR, "local_packages")
REQUIREMENTS_FILE = os.path.join(SCRIPT_DIR, "requirements.txt")

def parse_requirements(file_path):
    """Parses a requirements.txt file, returning a list of package names with versions."""
    package_names = []
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                package_names.append(line)
    return package_names

def check_all_requirements():
    """Comprehensive check of ALL requirements.txt packages."""
    if not os.path.exists(REQUIREMENTS_FILE):
        logging.critical(f"'{REQUIREMENTS_FILE}' not found. Cannot check dependencies.")
        return False
    
    try:
        required_packages = parse_requirements(REQUIREMENTS_FILE)
        logging.info(f"Checking {len(required_packages)} packages from requirements.txt...")
        
        missing_packages = []
        failed_imports = []
        
        for package_line in required_packages:
            # Extract package name for checking
            package_name = package_line.split('==')[0].split('>=')[0].split('<=')[0].split('<')[0].split('>')[0].split('~=')[0].strip()
            
            # Get the correct module import name
            module_name = get_module_name_for_package(package_name)
            
            # Check if package is in local_packages (installed)
            package_found = False
            if os.path.exists(LOCAL_PACKAGES_DIR):
                # Check multiple name variations
                name_variations = [
                    package_name.lower(),
                    package_name.replace('-', '_').lower(),
                    package_name.replace('_', '-').lower(),
                    package_name.replace('.py', '').lower()
                ]
                
                for item in os.listdir(LOCAL_PACKAGES_DIR):
                    if item.endswith('.dist-info'):
                        dist_name = item.replace('.dist-info', '').lower()
                        for variation in name_variations:
                            if variation in dist_name or dist_name in variation:
                                package_found = True
                                break
                        if package_found:
                            break
            
            if not package_found:
                missing_packages.append(package_line)
                continue
            
            # Try to import the module to verify it works
            try:
                if '.' in module_name:
                    # Handle nested modules
                    __import__(module_name, fromlist=[''])
                else:
                    __import__(module_name)
                logging.debug(f"✅ {package_line} - installed and importable")
            except ImportError as e:
                logging.warning(f"⚠️ {package_line} - installed but import failed: {e}")
                failed_imports.append(package_line)
            except Exception as e:
                logging.warning(f"⚠️ {package_line} - installed but error during import: {e}")
                failed_imports.append(package_line)
        
        if missing_packages:
            logging.warning(f"Missing packages: {missing_packages}")
            return False
            
        if failed_imports:
            logging.warning(f"Packages with import issues: {failed_imports}")
            return False
            
        logging.info("✅ All requirements.txt packages are properly installed and importable!")
        return True
        
    except Exception as e:
        logging.critical(f"Error checking requirements: {e}")
        return False

def ensure_local_packages():
    """Install missing packages to local_packages directory."""
    if not os.path.exists(LOCAL_PACKAGES_DIR):
        os.makedirs(LOCAL_PACKAGES_DIR)

    if not check_all_requirements():
        logging.info("Installing/updating dependencies to local_packages...")
        
        # Retry logic for pip install
        max_retries = 3
        retry_delay = 5  # seconds
        for i in range(max_retries):
            try:
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install",
                    "-r", REQUIREMENTS_FILE,
                    "--target", LOCAL_PACKAGES_DIR,
                    "--upgrade", "--no-warn-script-location",
                    "--timeout=30"  # Add a timeout to pip
                ])
                logging.info("Dependencies installed successfully to local_packages.")
                
                # Verify installation worked
                if check_all_requirements():
                    return True
                else:
                    logging.warning("Installation completed but verification failed.")
                    if i < max_retries - 1:
                        logging.info(f"Retrying verification in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        logging.error("Verification failed after installation.")
                        return False
                        
            except subprocess.CalledProcessError as e:
                logging.warning(f"Failed to install dependencies (attempt {i+1}/{max_retries}): {e}")
                if i < max_retries - 1:
                    logging.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logging.critical(f"Failed to install dependencies after multiple retries: {e}")
                    return False
            except Exception as e:
                logging.critical(f"An unexpected error occurred during dependency installation: {e}")
                return False
    else:
        logging.info("All dependencies are properly installed. Skipping installation.")
        return True

# Comprehensive package-to-module mapping for accurate import detection
PACKAGE_TO_MODULE_MAP = {
    # Common packages with non-standard import names
    'python-dotenv': 'dotenv',
    'pywin32': 'win32',
    'grpcio': 'grpc',
    'grpcio-status': 'grpc_status',
    'google-api-core': 'google.api_core',
    'google-auth': 'google.auth',
    'google-auth-httplib2': 'google.auth',
    'google-generativeai': 'google.generativeai',
    'google-resumable-media': 'google.resumable_media',
    'googleapis-common-protos': 'google.api',
    'protobuf': 'google.protobuf',
    'beautifulsoup4': 'bs4',
    'pillow': 'PIL',
    'discord.py': 'discord',
    'python-multipart': 'multipart',
    
    # Standard conversions (fallback)
    'attrs': 'attr',
    'charset-normalizer': 'charset_normalizer',
    'typing-extensions': 'typing_extensions',
    'async-timeout': 'async_timeout',
    'aiosqlite': 'aiosqlite',
    'aiofiles': 'aiofiles',
    'aiohttp': 'aiohttp',
    'matplotlib': 'matplotlib',
    'plotly': 'plotly',
    'pandas': 'pandas',
    'networkx': 'networkx',
    'pyngrok': 'pyngrok',
    'fastapi': 'fastapi',
    'uvicorn': 'uvicorn',
    'reportlab': 'reportlab',
    'lttb': 'lttb',
    'pnwkit': 'pnwkit',
    'psutil': 'psutil',
    'kaleido': 'kaleido',
    'click': 'click',
    'starlette': 'starlette',
    'typing-inspection': 'typing_inspection',
    'annotated-doc': 'annotated_doc',
    'groq': 'groq',
}

def get_module_name_for_package(package_name):
    """
    Convert package name to correct module import name.
    Handles complex naming conventions and special cases.
    """
    # Check if we have a direct mapping (case-insensitive)
    package_name_lower = package_name.lower()
    if package_name_lower in PACKAGE_TO_MODULE_MAP:
        return PACKAGE_TO_MODULE_MAP[package_name_lower]
    
    # Handle google packages with consistent pattern
    if package_name.startswith('google-') and 'google.' not in package_name:
        # Convert google-package-name to google.package_name
        module_name = package_name.replace('google-', 'google.')
        # Replace remaining hyphens with underscores
        module_name = module_name.replace('-', '_')
        return module_name
    
    # Handle standard conversions
    # Replace hyphens with underscores and remove .py extension
    module_name = package_name.replace('-', '_').replace('.py', '')
    
    # Special case: discord.py should import as discord
    if module_name == 'discord_py':
        return 'discord'
    
    return module_name

# Ensure local_packages is in sys.path BEFORE any third-party imports
if LOCAL_PACKAGES_DIR not in sys.path:
    sys.path.insert(0, LOCAL_PACKAGES_DIR)

# Run the dependency check and installation
if not ensure_local_packages():
    logging.critical("❌ Failed to ensure all dependencies are properly installed.")
    sys.exit(1)

# Now, safe to import third-party libraries
import discord
from discord.ext import commands
import asyncio

# Local Application Imports
from Systems.Functions.user_data_manager import UserDataManager
from Systems.Functions.utils import cleanup_service_ports
from Systems.Functions.web_server import run_web_server, shutdown_web_server

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
root_logger.setLevel(logging.INFO)

# Clear any existing handlers to prevent duplicates
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# Add our handlers
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# Set aiosqlite logger to WARNING to suppress DEBUG messages
logging.getLogger('aiosqlite').setLevel(logging.WARNING)

# ------------------------------------------------------------------------------
# BOT INITIALIZATION
# ------------------------------------------------------------------------------
# Load configurations from config.py and .env
try:
    from Systems.Functions.config import DISCORD_TOKEN, COMMAND_PREFIX, OWNER_ID, DATA_DIR, ARIES_USER_ID
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

        # Load core systems
        await self.load_extension("Systems.info")
        await self.load_extension("Systems.cogs.connection_manager")
        
        # Load PnW Hopper (Splicer for all PnW sub-modules)
        try:
            from Systems.PnW.pnwhopper import setup as setup_pnw
            await setup_pnw(self)
            self.logger.info("✅ Politics & War systems initialized.")
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize PnW systems: {e}", exc_info=True)
            
        # Load Fun & Utility Systems
        fun_cogs = [
            "Systems.Translator.translator",
            "Systems.Astrology.signs",
            "Systems.Astrology.reading",
            "Systems.Fun.fun_system", 
            "Systems.Fun.zombie", 
            "Systems.Fun.goodevil",
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

        # Retry logic for syncing slash commands
        max_retries = 5
        retry_delay = 10  # seconds
        for i in range(max_retries):
            try:
                synced = await self.tree.sync()
                self.logger.info(f"✅ Synced {len(synced)} application (slash) commands.")
                break  # Success, exit loop
            except (discord.errors.HTTPException, OSError) as e:
                self.logger.warning(f"⚠️ Failed to sync slash commands (attempt {i+1}/{max_retries}): {e}")
                if i < max_retries - 1:
                    self.logger.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                else:
                    self.logger.error("❌ Failed to sync slash commands after multiple retries.")

    async def close(self):
        """Gracefully closes the bot and its resources."""
        self.logger.info("🔌 Shutting down bot...")
        await super().close()

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

# Secure shutdown command
@bot.hybrid_command(name="shutdown", description="Securely shuts down the bot.")
@commands.is_owner()
async def shutdown(ctx: commands.Context):
    """Securely shuts down the bot, can only be used by the bot owner."""
    if ctx.author.id != ARIES_USER_ID:
        await ctx.send("You do not have permission to use this command.", ephemeral=True)
        return

    await ctx.send("Shutting down...", ephemeral=True)
    bot.logger.info(f"Shutdown command initiated by {ctx.author} (ID: {ctx.author.id})")
    
    # Cleanup resources
    cleanup_service_ports()
    shutdown_web_server()
    
    # Close the bot
    await bot.close()

# Global error handler
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    logging.error(f"Global Command Error: {error}", exc_info=True)

# Enhanced connection error handler
@bot.event
async def on_error(event, *args, **kwargs):
    """Handle any unhandled errors that occur during events."""
    logging.error(f"Unhandled error in {event}: {args}, {kwargs}", exc_info=True)

# Connection resilience
@bot.event
async def on_disconnect():
    """Handle bot disconnection with reconnection logic."""
    bot.logger.warning("Bot disconnected from Discord. Monitoring for reconnection...")
    
    # Wait up to 5 minutes for automatic reconnection
    for attempt in range(30):  # 30 attempts * 10 seconds = 5 minutes
        await asyncio.sleep(10)
        if bot.is_ready():
            bot.logger.info("Bot successfully reconnected!")
            return
    
    bot.logger.critical("Bot failed to reconnect after 5 minutes. Manual intervention may be required.")

# ------------------------------------------------------------------------------
# SEPARATE BOT AND CLOUDFLARE TUNNEL LAUNCHING
# ------------------------------------------------------------------------------

async def run_bot_only():
    """Run only the Discord bot without cloudflare tunnel."""
    max_reconnect_attempts = 10
    reconnect_delay = 30  # seconds
    
    for attempt in range(max_reconnect_attempts):
        try:
            bot.logger.info(f"Starting bot (attempt {attempt + 1}/{max_reconnect_attempts})...")
            await bot.start(DISCORD_TOKEN)
            break  # If we get here, bot closed normally
        except (discord.errors.ConnectionClosed, discord.errors.GatewayNotFound, 
                discord.errors.HTTPException, OSError) as e:
            bot.logger.error(f"Connection error (attempt {attempt + 1}): {e}")
            if attempt < max_reconnect_attempts - 1:
                bot.logger.info(f"Retrying in {reconnect_delay} seconds...")
                await asyncio.sleep(reconnect_delay)
            else:
                bot.logger.critical("Max reconnection attempts reached. Bot is shutting down.")
                break
        except Exception as e:
            bot.logger.critical(f"Unexpected error during bot startup: {e}", exc_info=True)
            break

async def run_tunnel_only():
    """Run only the cloudflare tunnel without the bot."""
    try:
        bot.logger.info("Starting cloudflare tunnel...")
        await run_web_server(bot)
    except Exception as e:
        bot.logger.error(f"Error running cloudflare tunnel: {e}", exc_info=True)

async def run_bot_and_tunnel():
    """Run both bot and cloudflare tunnel together (original behavior)."""
    try:
        await asyncio.gather(
            run_bot_only(),
            run_tunnel_only()
        )
    except Exception as e:
        bot.logger.critical(f"Critical error in main: {e}", exc_info=True)

# ------------------------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_DISCORD_TOKEN":
        logging.critical("❌ DISCORD_TOKEN is missing in .env file!")
        sys.exit(1)

    import argparse
    
    # Set up command line arguments
    parser = argparse.ArgumentParser(description='Reaper Bot Launcher')
    parser.add_argument('--mode', choices=['bot', 'tunnel', 'both'], default='both',
                       help='Launch mode: bot only, tunnel only, or both (default: both)')
    parser.add_argument('--check-deps', action='store_true',
                       help='Check all dependencies and exit')
    
    args = parser.parse_args()
    
    # Check dependencies if requested
    if args.check_deps:
        logging.info("🔍 Running dependency check...")
        if check_all_requirements():
            logging.info("✅ All dependencies are properly installed!")
            sys.exit(0)
        else:
            logging.error("❌ Some dependencies are missing or have issues.")
            sys.exit(1)
    
    async def main():
        try:
            if args.mode == 'bot':
                logging.info("🤖 Starting bot in BOT-ONLY mode...")
                await run_bot_only()
            elif args.mode == 'tunnel':
                logging.info("🚇 Starting bot in TUNNEL-ONLY mode...")
                await run_tunnel_only()
            else:  # both
                logging.info("🤖🚇 Starting bot in BOTH mode (bot + tunnel)...")
                # Initialize service ports before starting services
                from Systems.Functions.utils import initialize_service_ports
                initialize_service_ports()
                await run_bot_and_tunnel()
        except Exception as e:
            bot.logger.critical(f"Critical error in main: {e}", exc_info=True)
        finally:
            cleanup_service_ports()
            shutdown_web_server()
            try:
                await bot.close()
            except:
                pass

    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot shutdown requested by user.")
    finally:
        cleanup_service_ports()
        shutdown_web_server()
        try:
            asyncio.run(bot.close())
        except:
            pass
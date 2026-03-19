import os
import sys
import logging
import subprocess
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

def ensure_local_packages():
    if not os.path.exists(LOCAL_PACKAGES_DIR):
        os.makedirs(LOCAL_PACKAGES_DIR)

    try:
        required_packages = parse_requirements(REQUIREMENTS_FILE)
    except FileNotFoundError:
        logging.critical(f"'{REQUIREMENTS_FILE}' not found. Cannot check dependencies.")
        sys.exit(1)

    missing_packages = []
    # Get list of all installed packages from dist-info directories
    installed_packages = set()
    if os.path.exists(LOCAL_PACKAGES_DIR):
        for item in os.listdir(LOCAL_PACKAGES_DIR):
            if item.endswith('.dist-info'):
                # Extract package name from dist-info directory name
                # Format is usually "package-name-version.dist-info"
                package_name_from_dist = item.replace('.dist-info', '')
                # Remove version numbers (simplified approach)
                # This handles cases like "discord.py-2.3.2", "python_dotenv-1.0.1"
                base_name = package_name_from_dist.split('-')[0] if '-' in package_name_from_dist else package_name_from_dist
                installed_packages.add(base_name.lower())  # Store lowercase for case-insensitive comparison
                installed_packages.add(package_name_from_dist.lower())  # Keep full name too, lowercase
    
    for package_line in required_packages:
        # Extract package name from the line (e.g., "discord.py==2.3.2" -> "discord.py")
        package_name = package_line.split('==')[0].split('>=')[0].split('<=')[0].split('<')[0].split('>')[0].split('~=')[0].strip()
        
        # Normalize package name for checking (case-insensitive)
        normalized_name = package_name.replace('.py', '').replace('-', '_').lower()
        hyphenated_name = normalized_name.replace('_', '-')
        
        # Check if package is already installed using multiple name variations
        package_found = False
        name_variations = [
            package_name.lower(),           # Original name lowercase (e.g., "discord.py")
            normalized_name,                # Normalized lowercase (e.g., "discord")
            hyphenated_name,                # Hyphenated lowercase (e.g., "python-dotenv")
            package_name.replace('-', '_').lower(),  # Underscore version lowercase (e.g., "python_dotenv")
        ]
        
        for variation in name_variations:
            if variation in installed_packages:
                package_found = True
                break
        
        if not package_found:
            missing_packages.append(package_line)

    if not missing_packages and not os.listdir(LOCAL_PACKAGES_DIR):
        logging.warning("local_packages directory is empty but no packages detected as missing. This might be the first run.")
        missing_packages = required_packages

    if missing_packages:
        logging.info(f"Missing packages: {', '.join(missing_packages)}. Installing/updating dependencies to local_packages...")
        try:
            # Use a single pip install command with the full requirements file
            # This allows pip to resolve dependencies correctly
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
        logging.info("All dependencies already present in local_packages. Skipping installation.")

# Ensure local_packages is in sys.path BEFORE any third-party imports
if LOCAL_PACKAGES_DIR not in sys.path:
    sys.path.insert(0, LOCAL_PACKAGES_DIR)

# Run the dependency check and installation
ensure_local_packages()

# Now, safe to import third-party libraries
import discord
from discord.ext import commands
import asyncio

# Local Application Imports
from Systems.Functions.user_data_manager import UserDataManager
from Systems.Functions.utils import cleanup_service_ports

# Comprehensive package-to-module mapping for accurate import detection
PACKAGE_TO_MODULE_MAP = {
    # Common packages with non-standard import names
    'python-dotenv': 'dotenv',
    'pywin32': 'win32',
    'grpcio': 'grpc',
    'grpcio-status': 'grpc_status',
    'google-api-core': 'google.api_core',
    'google-auth': 'google.auth',
    'google-auth-httplib2': 'google.auth',  # This package doesn't have a separate import, it's used by google.auth
    'google-generativeai': 'google.generativeai',
    'google-resumable-media': 'google.resumable_media',
    'googleapis-common-protos': 'google.api',
    'protobuf': 'google.protobuf',
    'beautifulsoup4': 'bs4',
    'pillow': 'PIL',  # PIL is the correct import name, not Pillow
    'discord.py': 'discord',
    
    # Standard conversions (fallback)
    'attrs': 'attr',
    'charset-normalizer': 'charset_normalizer',
    'typing-extensions': 'typing_extensions',
    'async-timeout': 'async_timeout',
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

# Runtime check: ensure critical dependencies are vendored in local_packages
def log_vendored_dependencies_status():
    """Log whether key third-party packages are loaded from local_packages."""
    logger = logging.getLogger('VendoredDeps')
    logger.info("🔎 Checking vendored dependencies availability...")

    try:
        required_packages = parse_requirements(REQUIREMENTS_FILE)
    except FileNotFoundError:
        logger.critical(f"'{REQUIREMENTS_FILE}' not found. Cannot verify dependencies.")
        return

    # Get list of all installed packages from dist-info directories (same logic as ensure_local_packages)
    installed_packages = set()
    if os.path.exists(LOCAL_PACKAGES_DIR):
        for item in os.listdir(LOCAL_PACKAGES_DIR):
            if item.endswith('.dist-info'):
                package_name_from_dist = item.replace('.dist-info', '')
                base_name = package_name_from_dist.split('-')[0] if '-' in package_name_from_dist else package_name_from_dist
                installed_packages.add(base_name.lower())
                installed_packages.add(package_name_from_dist.lower())

    for package_line in required_packages:
        # Extract package name from the line (e.g., "discord.py==2.3.2" -> "discord.py")
        package_name = package_line.split('==')[0].split('>=')[0].split('<=')[0].split('<')[0].split('>')[0].split('~=')[0].strip()
        
        # Check if package is installed using the same logic as ensure_local_packages
        normalized_name = package_name.replace('.py', '').replace('-', '_').lower()
        hyphenated_name = normalized_name.replace('_', '-')
        
        # Check if package is already installed using multiple name variations
        package_found = False
        name_variations = [
            package_name.lower(),
            normalized_name,
            hyphenated_name,
            package_name.replace('-', '_').lower(),
        ]
        
        for variation in name_variations:
            if variation in installed_packages:
                package_found = True
                break
        
        if package_found:
            # Try to determine the source (local_packages vs system)
            try:
                # Get the correct module name for this package
                module_name = get_module_name_for_package(package_name)
                
                # Handle nested modules (e.g., google.generativeai)
                if '.' in module_name:
                    # Import the top-level module first
                    top_module = module_name.split('.')[0]
                    mod = __import__(top_module)
                    # For nested modules, we need to import the full path
                    if len(module_name.split('.')) > 1:
                        mod = __import__(module_name, fromlist=[''])
                else:
                    mod = __import__(module_name)
                
                path = getattr(mod, '__file__', '') or ''
                source = 'local_packages' if 'local_packages' in path else 'system'
                logger.info(f"{package_line}: OK (source={source})")
            except ImportError as e:
                # Package is installed but module can't be imported - provide detailed error
                logger.warning(f"{package_line}: Installed but module import failed (tried importing '{module_name}': {e})")
            except Exception as e:
                logger.warning(f"{package_line}: Installed but error during import check: {e}")
        else:
            logger.error(f"{package_line}: MISSING - Not found in local_packages")

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

# Set aiosqlite logger to WARNING to suppress DEBUG messages
logging.getLogger('aiosqlite').setLevel(logging.WARNING)

# -----------------------------------------------------------------------------
# BOT INITIALIZATION
# -----------------------------------------------------------------------------
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
    
    # Close the bot
    await bot.close()

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
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        cleanup_service_ports()
        asyncio.run(bot.close())

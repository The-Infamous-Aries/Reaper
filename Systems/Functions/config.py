import os
from dotenv import load_dotenv
from typing import Dict, List, Optional, Union, TYPE_CHECKING
if TYPE_CHECKING:
    import discord
    from discord.ext import commands

# Load .env from the current directory (Systems\Functions)
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '.env')
load_dotenv(env_path)

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
COMMAND_PREFIX = os.getenv('COMMAND_PREFIX', '!')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
PANDW_API_KEY = os.getenv('PANDW_API_KEY')
PANDW_API_V3_KEY = os.getenv('PANDW_API_V3_KEY')
PANDW_BOT_KEY = os.getenv('PANDW_BOT_KEY')
HORSCOPE_API = os.getenv('HORSCOPE_API')
GIPHY_KEY = os.getenv('GIPHY_KEY')
PIXABAY_KEY = os.getenv('PIXABAY_KEY')
OWNER_ID = int(os.getenv('ADMIN_USER_ID', '0'))
DATA_DIR = os.getenv('DATA_DIR', os.getcwd())
ARIES_USER_ID = 1344242023577817098
ADMIN_USER_ID = ARIES_USER_ID
CF_ACCOUNT_ID = os.getenv('CF_ACCOUNT_ID')
CF_TUNNEL_ID = os.getenv('CF_TUNNEL_ID')
CF_API_TOKEN = os.getenv('CF_API_TOKEN')
CF_TUNNEL_TOKEN = os.getenv('CF_TUNNEL_TOKEN')
CF_CREDENTIALS_FILE = os.getenv('CF_CREDENTIALS_FILE')

# Custom domain configuration
CUSTOM_DOMAIN = os.getenv('CUSTOM_DOMAIN', 'https://reaper.qzz.io')
USE_CLOUDFLARE_TUNNEL = os.getenv('USE_CLOUDFLARE_TUNNEL', 'false').lower() == 'true'

def _get_results_channel_id() -> int:
    channel_from_env = os.getenv('RESULTS_CHANNEL_ID')
    if channel_from_env and channel_from_env != '0':
        return int(channel_from_env)
    return 0
RESULTS_CHANNEL_ID = _get_results_channel_id()
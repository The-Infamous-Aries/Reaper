import os
from dotenv import load_dotenv
from typing import Dict, List, Optional, Union, TYPE_CHECKING
if TYPE_CHECKING:
    import discord
    from discord.ext import commands
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
COMMAND_PREFIX = os.getenv('COMMAND_PREFIX', '!')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
PANDW_API_KEY = os.getenv('PANDW_API_KEY')
PANDW_BOT_KEY = os.getenv('PANDW_BOT_KEY')
HOME_ALLIANCE_ID = os.getenv('HOME_ALLIANCE_ID', '14635')
HORSCOPE_API = os.getenv('HORSCOPE_API')
OWNER_ID = int(os.getenv('ADMIN_USER_ID', '0'))
DATA_DIR = os.getenv('DATA_DIR', os.getcwd())
ARIES_USER_ID = 1344242023577817098

def _get_admin_user_id() -> int:
    admin_from_env = os.getenv('ADMIN_USER_ID')
    if admin_from_env and admin_from_env != '0':
        return int(admin_from_env)
    return 0
ADMIN_USER_ID = _get_admin_user_id()

def _get_results_channel_id() -> int:
    channel_from_env = os.getenv('RESULTS_CHANNEL_ID')
    if channel_from_env and channel_from_env != '0':
        return int(channel_from_env)
    return 0
RESULTS_CHANNEL_ID = _get_results_channel_id()

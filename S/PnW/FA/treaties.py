import discord
from discord.ext import commands
from discord import app_commands
from typing import List, Dict, Any, Optional, Callable, Literal, Union, cast
from types import ModuleType
from discord.ui import Button, View
from datetime import datetime, timezone, timedelta
import json
import logging
import os
import sys
import asyncio
import math
import random
import aiohttp
import io

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from Systems.Functions import emoji as emoji_mod

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'Data', 'Treaty')
PERSISTENT_VIEWS_FILE = os.path.join(DATA_DIR, "treaties_views.json")
AUTO_UPDATE_FILE = os.path.join(DATA_DIR, "treaties_auto_update.json")

AiohttpModule = Optional[ModuleType]
IoModule = Optional[ModuleType]
PillowImageModule = Optional[ModuleType]
PillowImageOpsModule = Optional[ModuleType]
PillowImageDrawModule = Optional[ModuleType]

try:
    _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    _local_packages = os.path.join(_project_root, 'local_packages')
    if os.path.isdir(_local_packages) and _local_packages not in sys.path:
        sys.path.insert(0, _local_packages)
    # Prevent user site-packages precedence over vendored copies
    os.environ.setdefault('PYTHONNOUSERSITE', '1')
except Exception as _vend_err:
    logging.getLogger('TreatiesManager').warning(f"Vendored path setup failed: {_vend_err}")

aiohttp: AiohttpModule = None
io: IoModule = None
ImageOps: PillowImageOpsModule = None
ImageDraw: PillowImageDrawModule = None

try:
    import aiohttp as _aiohttp
    import io as _io
    from PIL import Image as _Image, ImageOps as _ImageOps, ImageDraw as _ImageDraw
    aiohttp = _aiohttp
    io = _io
    Image = _Image
    ImageOps = _ImageOps
    ImageDraw = _ImageDraw
except Exception as _pillow_err:
    # Fallback: define minimal stubs so the module can load even if imaging is unavailable
    logging.getLogger('TreatiesManager').warning(f"Imaging libraries not available: {_pillow_err}")


class TreatiesRefreshView(discord.ui.View):
    def __init__(self, cog: 'TreatiesManager', alliance_id: int, timeout: Optional[float] = 300.0):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.alliance_id = alliance_id
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.label == "Refresh":
                item.custom_id = f"treaties_refresh_{alliance_id}"
                break

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.logger.info(f"Treaties refresh button clicked for alliance {self.alliance_id}")
        
        try:
            await interaction.response.defer()
        except Exception as defer_err:
            self.cog.logger.warning(f"Failed to defer interaction response: {defer_err}")
        
        try:
            # Fetch fresh treaty data
            treaties: List[Dict[str, Any]] = []
            try:
                alliance_cog = self.cog.bot.get_cog('AllianceManager')
                if alliance_cog and hasattr(alliance_cog, 'query_system') and alliance_cog.query_system:
                    res = await alliance_cog.query_system.get_alliance_treaties(str(self.alliance_id), force_refresh=True)
                    treaties = res or []
            except Exception as qerr:
                self.cog.logger.error(f"Refresh treaties query error: {qerr}")

            # Generate new embed and image
            treaty_file = await self.cog._compose_treaty_web_image(treaties, center_alliance_id=int(self.alliance_id))
            embed = await asyncio.to_thread(self.cog._format_treaties_embed_sync, treaties, center_alliance_id=int(self.alliance_id), center_name=None)
            
            files: List[discord.File] = []
            if treaty_file:
                embed.set_image(url=f"attachment://{treaty_file.filename}")
                files = [treaty_file]

            # Create new view for the refreshed message
            new_view = TreatiesRefreshView(self.cog, int(self.alliance_id))
            
            # Edit the existing message instead of deleting and reposting
            if interaction.message:
                try:
                    # Update the persistent views tracking
                    if interaction.message.id in self.cog.persistent_views:
                        self.cog.persistent_views[interaction.message.id] = int(self.alliance_id)
                        self.cog._save_persistent_views()

                    # --- Auto-update handling for refresh ---
                    if interaction.message.id in self.cog.auto_update_data:
                        # If it's an auto-update embed, just update the last_update time
                        self.cog.auto_update_data[interaction.message.id]['last_update'] = datetime.now(timezone.utc).isoformat()
                        self.cog._save_auto_update_data()
                        self.cog.logger.info(f"Refreshed auto-update embed {interaction.message.id}, next update time remains the same")
                    
                    # Edit the message with new content
                    if files:
                        await interaction.message.edit(embed=embed, view=new_view, attachments=files)
                    else:
                        await interaction.message.edit(embed=embed, view=new_view)
                    
                    # Update the message map
                    channel_id = getattr(interaction.channel, 'id', 0)
                    self.cog.treaties_message_map[channel_id] = interaction.message.id
                    
                    self.cog.logger.info(f"Successfully refreshed treaties for alliance {self.alliance_id} by editing message {interaction.message.id}")
                    
                except Exception as edit_err:
                    self.cog.logger.error(f"TreatiesRefreshView: edit failed: {edit_err}")
                    # Fallback: send new message if edit fails
                    if isinstance(interaction.channel, discord.abc.Messageable):
                        try:
                            new_msg = await interaction.channel.send(embed=embed, view=new_view, files=files if files else [])
                            
                            # Update tracking with new message
                            self.cog.persistent_views[new_msg.id] = int(self.alliance_id)
                            self.cog._save_persistent_views()

                            # --- Auto-update handling for fallback ---
                            if interaction.message.id in self.cog.auto_update_data:
                                # Transfer auto-update data to the new message
                                self.cog.auto_update_data[new_msg.id] = self.cog.auto_update_data.pop(interaction.message.id)
                                self.cog.auto_update_data[new_msg.id]['last_update'] = datetime.now(timezone.utc).isoformat()
                                self.cog._save_auto_update_data()
                                self.cog.logger.info(f"Transferred auto-update from old message {interaction.message.id} to new message {new_msg.id}")
                            
                            channel_id = getattr(interaction.channel, 'id', 0)
                            self.cog.treaties_message_map[channel_id] = new_msg.id
                            
                            # Delete the old message
                            await interaction.message.delete()
                            
                            self.cog.logger.info(f"Successfully refreshed treaties for alliance {self.alliance_id} by sending new message {new_msg.id}")
                            
                        except Exception as fallback_err:
                            self.cog.logger.error(f"TreatiesRefreshView: fallback send failed: {fallback_err}")
                            raise
            else:
                # No message to edit, send new message
                if isinstance(interaction.channel, discord.abc.Messageable):
                    new_msg = await interaction.channel.send(embed=embed, view=new_view, files=files if files else [])
                    
                    # Update tracking
                    self.cog.persistent_views[new_msg.id] = int(self.alliance_id)
                    self.cog._save_persistent_views()
                    
                    # --- Auto-update handling for new message ---
                    if new_msg.id in self.cog.auto_update_data:
                        # This should not happen, but handle it just in case
                        self.cog.auto_update_data[new_msg.id]['last_update'] = datetime.now(timezone.utc).isoformat()
                        self.cog._save_auto_update_data()
                        self.cog.logger.warning(f"Auto-update data already existed for new message {new_msg.id}")
                    
                    channel_id = getattr(interaction.channel, 'id', 0)
                    self.cog.treaties_message_map[channel_id] = new_msg.id
                    
                    self.cog.logger.info(f"Successfully refreshed treaties for alliance {self.alliance_id} by sending new message {new_msg.id}")
                    
        except Exception as e:
            self.cog.logger.error(f"TreatiesRefreshView refresh error: {e}")
            try:
                error_embed = discord.Embed(
                    title="❌ Refresh Failed",
                    description=f"Error: {str(e)}",
                    color=0xFF0000
                )
                await interaction.followup.send(embed=error_embed, ephemeral=True)
            except Exception:
                pass

    async def on_timeout(self):
        """Handle timeout by removing the view from the message and persistent storage."""
        self.cog.logger.info(f"TreatiesRefreshView for alliance {self.alliance_id} timed out.")
        if self.message:
            try:
                # Remove the view from the message to disable the button
                await self.message.edit(view=None)
                
                # Remove from persistent storage
                if self.message.id in self.cog.persistent_views:
                    del self.cog.persistent_views[self.message.id]
                    self.cog._save_persistent_views()
                    
                # Remove from message map
                channel_id = getattr(self.message.channel, 'id', None)
                if channel_id and channel_id in self.cog.treaties_message_map:
                    if self.cog.treaties_message_map[channel_id] == self.message.id:
                        del self.cog.treaties_message_map[channel_id]

                # --- Auto-update cleanup ---
                if self.message.id in self.cog.auto_update_data:
                    del self.cog.auto_update_data[self.message.id]
                    self.cog._save_auto_update_data()
                    self.cog.logger.info(f"Removed message {self.message.id} from auto-update on timeout")
                        
            except Exception as e:
                self.cog.logger.error(f"Error during on_timeout cleanup for alliance {self.alliance_id}: {e}")

class TreatiesManager(commands.Cog):
    """Cog to manage treaty commands and functionality."""

    # --- Layout Constants ---
    BASE_RADIUS = 150
    REGULAR_GAP = 100
    SMALL_GAP = 60
    IMAGE_WIDTH = 1600
    IMAGE_HEIGHT = 1200
    CENTER_X = IMAGE_WIDTH // 2
    CENTER_Y = IMAGE_HEIGHT // 2
    
    # Additional layout constants for enhanced treaty web
    IMMEDIATE_RADIUS = BASE_RADIUS                      # Protectorate/Extension
    M_RADIUS = IMMEDIATE_RADIUS + REGULAR_GAP           # MDP/MDoAP
    O_RADIUS = M_RADIUS + SMALL_GAP                     # ODP/ODoAP
    PEACE_RADIUS = O_RADIUS + REGULAR_GAP               # PIAT/NAP
    LINE_WIDTH = 3
    
    # --- Color Constants ---
    TREATY_COLORS = {
        'ODP': (255, 255, 150, 255),      # Light Yellow
        'ODoAP': (255, 215, 0, 255),      # Gold/Strong Yellow
        'MDP': (150, 150, 255, 255),      # Light Blue
        'MDoAP': (50, 50, 200, 255),      # Dark Blue
        'Protectorate': (255, 150, 150, 255), # Light Red
        'NAP': (150, 255, 150, 255),      # Light Green
        'PIAT': (100, 255, 100, 255),     # Light Green
        'Extension': (200, 50, 50, 255),   # Dark Red
    }

    def __init__(self, bot: commands.Bot, query_instance, calc_instance):
        self.bot = bot
        self.logger = logging.getLogger(self.__class__.__name__)
        self.query_instance = query_instance
        self.calc_instance = calc_instance
        self.default_alliance_id: Optional[int] = None
        self.default_alliance_name: Optional[str] = None
        # Track the last posted treaties message per channel to edit instead of posting new
        self.treaties_message_map: Dict[int, int] = {}
        self.persistent_views_file = PERSISTENT_VIEWS_FILE
        self.persistent_views: Dict[int, int] = {}
        self._load_persistent_views()
        
        # Auto-update tracking: message_id -> {alliance_id, channel_id, auto_update_enabled, last_update, next_update}
        self.auto_update_data: Dict[int, Dict[str, Any]] = {}
        self.auto_update_file = AUTO_UPDATE_FILE
        self._load_auto_update_data()
        
        # Background task for auto-updates
        self.auto_update_task: Optional[asyncio.Task] = None
        self.auto_update_running = False

    async def cog_load(self):
        """Called when the cog is loaded."""
        await self.start_auto_update_task()
        self.logger.info("TreatiesManager cog loaded successfully")

    async def cog_unload(self):
        """Called when the cog is unloaded."""
        await self.stop_auto_update_task()
        self.logger.info("TreatiesManager cog unloaded successfully")

    def _load_persistent_views(self):
        if os.path.exists(self.persistent_views_file):
            with open(self.persistent_views_file, 'r') as f:
                try:
                    data = json.load(f)
                    self.persistent_views = {int(k): int(v) for k, v in data.items()}
                except json.JSONDecodeError as e:
                    self.logger.error(f"Error decoding persistent views file: {e}")
                    self.persistent_views = {}
        else:
            self.persistent_views = {}

    def _save_persistent_views(self):
        with open(self.persistent_views_file, 'w') as f:
            json.dump(self.persistent_views, f)

    def _load_auto_update_data(self):
        """Load auto-update data from file."""
        if os.path.exists(self.auto_update_file):
            with open(self.auto_update_file, 'r') as f:
                try:
                    data = json.load(f)
                    # Convert string keys back to integers
                    self.auto_update_data = {}
                    for msg_id_str, data_dict in data.items():
                        msg_id = int(msg_id_str)
                        self.auto_update_data[msg_id] = {
                            'alliance_id': int(data_dict['alliance_id']),
                            'channel_id': int(data_dict['channel_id']),
                            'auto_update_enabled': bool(data_dict['auto_update_enabled']),
                            'last_update': data_dict.get('last_update'),
                            'next_update': data_dict.get('next_update')
                        }
                    self.logger.info(f"Loaded auto-update data for {len(self.auto_update_data)} messages")
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    self.logger.error(f"Error decoding auto-update file: {e}")
                    self.auto_update_data = {}
        else:
            self.auto_update_data = {}
            self.logger.info("No existing auto-update data found")

    def _save_auto_update_data(self):
        """Save auto-update data to file."""
        try:
            # Convert to serializable format (int keys to strings)
            serializable_data = {}
            for msg_id, data_dict in self.auto_update_data.items():
                serializable_data[str(msg_id)] = data_dict
            
            with open(self.auto_update_file, 'w') as f:
                json.dump(serializable_data, f, indent=2)
            self.logger.debug(f"Saved auto-update data for {len(self.auto_update_data)} messages")
        except Exception as e:
            self.logger.error(f"Error saving auto-update data: {e}")

    async def start_auto_update_task(self):
        """Start the background task for auto-updating treaties."""
        if self.auto_update_running:
            return
        
        self.auto_update_running = True
        self.auto_update_task = asyncio.create_task(self._auto_update_loop())
        self.logger.info("Started auto-update background task")

    async def stop_auto_update_task(self):
        """Stop the background task for auto-updating treaties."""
        if self.auto_update_task and not self.auto_update_task.done():
            self.auto_update_task.cancel()
            try:
                await self.auto_update_task
            except asyncio.CancelledError:
                pass
        
        self.auto_update_running = False
        self.logger.info("Stopped auto-update background task")

    async def _auto_update_loop(self):
        """Background loop for auto-updating treaties."""
        while self.auto_update_running:
            try:
                await self._process_auto_updates()
                # Wait 1 hour before next check
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in auto-update loop: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error

    async def _process_auto_updates(self):
        """Process auto-updates for all tracked messages."""
        current_time = datetime.now(timezone.utc).isoformat()
        messages_to_update = []
        
        # Find messages that need updating
        for msg_id, data in self.auto_update_data.items():
            if not data.get('auto_update_enabled'):
                continue
                
            next_update = data.get('next_update')
            if not next_update:
                # Set next update time if not set
                data['next_update'] = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
                continue
            
            if current_time >= next_update:
                messages_to_update.append(msg_id)
        
        # Update messages that need updating
        for msg_id in messages_to_update:
            try:
                await self._update_auto_message(msg_id)
            except Exception as e:
                self.logger.error(f"Failed to auto-update message {msg_id}: {e}")

    async def _update_auto_message(self, message_id: int):
        """Update a specific auto-update message with fresh data."""
        data = self.auto_update_data.get(message_id)
        if not data:
            return
        
        alliance_id = data['alliance_id']
        channel_id = data['channel_id']
        
        # Fetch fresh treaty data
        treaties: List[Dict[str, Any]] = []
        try:
            alliance_cog = self.bot.get_cog('AllianceManager')
            if alliance_cog and hasattr(alliance_cog, 'query_system') and alliance_cog.query_system:
                res = await alliance_cog.query_system.get_alliance_treaties(str(alliance_id), force_refresh=True)
                treaties = res or []
        except Exception as e:
            self.logger.error(f"Failed to fetch fresh treaties for auto-update: {e}")
            return
        
        # Generate new embed and image
        treaty_file = await self._compose_treaty_web_image(treaties, center_alliance_id=alliance_id)
        embed = await asyncio.to_thread(self._format_treaties_embed_sync, treaties, center_alliance_id=alliance_id, center_name=None)
        
        files: List[discord.File] = []
        if treaty_file:
            embed.set_image(url=f"attachment://{treaty_file.filename}")
            files = [treaty_file]
        
        # Get channel and message
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.abc.Messageable):
                self.logger.warning(f"Channel {channel_id} not found or not messageable for auto-update")
                return
            
            message = await channel.fetch_message(message_id)
            
            # Create new view for the updated message
            new_view = TreatiesRefreshView(self, alliance_id)
            
            # Update the message
            if files:
                await message.edit(embed=embed, view=new_view, attachments=files)
            else:
                await message.edit(embed=embed, view=new_view)
            
            # Update auto-update data
            now = datetime.now(timezone.utc)
            data['last_update'] = now.isoformat()
            data['next_update'] = (now + timedelta(hours=24)).isoformat()
            self._save_auto_update_data()
            
            self.logger.info(f"Successfully auto-updated treaties message {message_id} for alliance {alliance_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to update message {message_id} for auto-update: {e}")
            # Remove from auto-update if message no longer exists
            if "Unknown Message" in str(e) or "Not Found" in str(e):
                del self.auto_update_data[message_id]
                self._save_auto_update_data()
                self.logger.info(f"Removed message {message_id} from auto-update (message not found)")



    async def _fetch_flag_image(self, url: str) -> Optional[Image.Image]:
        """Download an image from URL and return a PIL Image, or None on failure."""
        self.logger.info(f"Attempting to fetch flag image from: {url}")
        try:
            if not url:
                self.logger.warning("Skipped fetching flag: URL is empty.")
                return None
            if aiohttp is None:
                self.logger.warning("aiohttp not available for flag fetching.")
                return None
            if io is None:
                self.logger.warning("io module not available for flag fetching.")
                return None
            timeout_obj = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout_obj) as session:
                headers = {"User-Agent": "Mozilla/5.0 (compatible; DiscordBot/1.0)"}
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        self.logger.warning(f"Flag fetch failed with status {resp.status} for URL: {url}")
                        return None
                    data = await resp.read()
            bio = io.BytesIO(data)
            img = Image.open(bio)
            self.logger.info(f"Successfully fetched and opened flag from: {url}")
            return img
        except Exception as e:
            self.logger.error(f"An exception occurred while fetching flag from {url}: {e}")
            return None

    async def _fetch_emoji_image(self, emoji_id: int, animated: bool = False) -> Optional[Image.Image]:
        """Download a Discord emoji image and return a PIL Image, or None on failure."""
        self.logger.info(f"Attempting to fetch emoji image for ID: {emoji_id}")
        try:
            if not emoji_id:
                self.logger.warning("Skipped fetching emoji: ID is empty.")
                return None
            if aiohttp is None:
                self.logger.warning("aiohttp not available for emoji fetching.")
                return None
            if io is None:
                self.logger.warning("io module not available for emoji fetching.")
                return None
            
            # Discord emoji URL format
            extension = "gif" if animated else "png"
            url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{extension}"
            
            timeout_obj = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout_obj) as session:
                headers = {"User-Agent": "Mozilla/5.0 (compatible; DiscordBot/1.0)"}
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        self.logger.warning(f"Emoji fetch failed with status {resp.status} for URL: {url}")
                        return None
                    data = await resp.read()
            bio = io.BytesIO(data)
            img = Image.open(bio)
            self.logger.info(f"Successfully fetched and opened emoji from: {url}")
            return img
        except Exception as e:
            self.logger.error(f"An exception occurred while fetching emoji {emoji_id}: {e}")
            return None

    def _normalize_treaty_type(self, ttype: str) -> str:
        """Normalize various treaty type labels/abbreviations to canonical keys.
        Returns one of: 'MDP', 'MDoAP', 'ODP', 'ODoAP', 'Protectorate', 'NAP', 'PIAT', 'Extension'.
        """
        s = (ttype or '').strip().lower()
        s_compact = s.replace(' ', '').replace('-', '')
        
        if s_compact in ['mdp', 'mutualdefensepact', 'mutualdefense']:
            return 'MDP'
        elif s_compact in ['mdoap', 'mutualdefenseoffensiveagreement', 'mdoapact']:
            return 'MDoAP'
        elif s_compact in ['odp', 'optionaldefensepact', 'optionaldefense']:
            return 'ODP'
        elif s_compact in ['odoap', 'optionaldefenseoffensiveagreement', 'odoapact']:
            return 'ODoAP'
        elif s_compact in ['protectorate', 'protect', 'prot']:
            return 'Protectorate'
        elif s_compact in ['nap', 'nonaggressionpact', 'nonaggression']:
            return 'NAP'
        elif s_compact in ['piat', 'peaceintelligenceagreement', 'intelligence']:
            return 'PIAT'
        elif s_compact in ['extension', 'extend']:
            return 'Extension'
        else:
            return 'MDP'  # fallback



    def _find_valid_line_path(self, start_pos, end_pos, flags_to_avoid, max_offset=120):
        """Find a curved path for a line that avoids intersecting flags."""
        if not flags_to_avoid:
            return None
        
        dx = end_pos[0] - start_pos[0]
        dy = end_pos[1] - start_pos[1]
        
        for offset in range(20, max_offset + 1, 20):
            for direction in [1, -1]:
                angle_rad = math.atan2(dy, dx) + (math.pi / 2) * direction
                
                control_offset_x = int(offset * math.cos(angle_rad))
                control_offset_y = int(offset * math.sin(angle_rad))
                
                mid_x = (start_pos[0] + end_pos[0]) // 2 + control_offset_x
                mid_y = (start_pos[1] + end_pos[1]) // 2 + control_offset_y
                
                steps = 40
                valid_path = True
                for i in range(steps + 1):
                    t = i / steps
                    x = int((1-t)**2 * start_pos[0] + 2*(1-t)*t * mid_x + t**2 * end_pos[0])
                    y = int((1-t)**2 * start_pos[1] + 2*(1-t)*t * mid_y + t**2 * end_pos[1])
                    
                    for flag_pos, flag_size in flags_to_avoid:
                        padding = 12
                        flag_left = flag_pos[0] - padding
                        flag_top = flag_pos[1] - padding
                        flag_right = flag_pos[0] + flag_size[0] + padding
                        flag_bottom = flag_pos[1] + flag_size[1] + padding
                        
                        if (flag_left <= x <= flag_right and 
                            flag_top <= y <= flag_bottom):
                            valid_path = False
                            break
                    
                    if not valid_path:
                        break
                
                if valid_path:
                    return (mid_x, mid_y)
        
        return None

    def _draw_treaty_line(self, draw, start_pos, end_pos, line_color, width=None, flags_to_avoid=None, curved=True):
        """Draw a curved treaty line, avoiding overlapping flags."""
        line_width = width or self.LINE_WIDTH
        
        control_point = None
        if flags_to_avoid:
            control_point = self._find_valid_line_path(start_pos, end_pos, flags_to_avoid)

        if curved and not control_point:
            mid_x = (start_pos[0] + end_pos[0]) // 2
            mid_y = (start_pos[1] + end_pos[1]) // 2
            dx = end_pos[0] - start_pos[0]
            dy = end_pos[1] - start_pos[1]
            perp_x = -dy
            perp_y = dx
            length = math.sqrt(perp_x*perp_x + perp_y*perp_y)
            if length > 0:
                perp_x = perp_x / length * 35
                perp_y = perp_y / length * 35
            control_point = (mid_x + int(perp_x), mid_y + int(perp_y))
        
        if control_point:
            steps = 30
            points = []
            for i in range(steps + 1):
                t = i / steps
                x = int((1-t)**2 * start_pos[0] + 2*(1-t)*t * control_point[0] + t**2 * end_pos[0])
                y = int((1-t)**2 * start_pos[1] + 2*(1-t)*t * control_point[1] + t**2 * end_pos[1])
                points.append((x, y))
            
            for i in range(len(points) - 1):
                draw.line([points[i], points[i+1]], fill=line_color, width=line_width)
        else:
            draw.line([start_pos, end_pos], fill=line_color, width=line_width)

    def _process_flag_image(self, img: Image.Image, size: tuple = (56, 56)) -> Image.Image:
        """Process flag image - optimized resize with minimal memory usage."""
        if img is None:
            return Image.new("RGBA", size, (40, 40, 40, 200))
        
        try:
            # Convert to RGBA for consistent output
            if img.mode not in ("RGBA", "LA"):
                img = img.convert("RGBA")
            
            # Resize to exact dimensions while maintaining aspect ratio
            img_ratio = img.width / img.height
            target_ratio = size[0] / size[1]
            
            if img_ratio > target_ratio:
                # Image is wider than target - fit to width
                new_width = size[0]
                new_height = int(size[0] / img_ratio)
            else:
                # Image is taller than target - fit to height
                new_height = size[1]
                new_width = int(size[1] * img_ratio)
            
            # Resize the image
            resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Create new image with exact size and center the resized image
            result = Image.new("RGBA", size, (0, 0, 0, 0))
            paste_x = (size[0] - new_width) // 2
            paste_y = (size[1] - new_height) // 2
            result.paste(resized, (paste_x, paste_y))
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error processing flag image: {e}")
            return Image.new("RGBA", size, (40, 40, 40, 200))

    def _draw_ring(self, draw, center_x, center_y, radius, color, width=3):
        """Draw a simple ring."""
        bbox = [center_x - radius, center_y - radius,
               center_x + radius, center_y + radius]
        draw.ellipse(bbox, outline=color, width=width)

    def _generate_treaty_web_image_sync(
        self,
        immediate_items: List[Dict[str, Any]],
        m_items: List[Dict[str, Any]],
        o_items: List[Dict[str, Any]],
        peace_items: List[Dict[str, Any]],
        cy_raw_img: Optional["Image.Image"],
        all_treaties: List[Dict[str, Any]],
        center_id: int,  # Add center_id parameter
        center_size: int = 96,  # Center flag largest size
        emoji_images: Dict[str, Optional["Image.Image"]] = None  # Emoji images for legend
    ) -> Optional[discord.File]:
        """Synchronous part of treaty web image generation with enhanced visuals and optimizations."""
        try:
            if Image is None or ImageDraw is None or io is None:
                return None

            # Define layout constants before using them
            IMMEDIATE_RADIUS = self.IMMEDIATE_RADIUS
            M_RADIUS = self.M_RADIUS
            O_RADIUS = self.O_RADIUS
            PEACE_RADIUS = self.PEACE_RADIUS
            LINE_WIDTH = self.LINE_WIDTH

            # Resize logic helper with caching - optimized for memory efficiency
            _flag_cache = {}
            
            def process_items(items: List[Dict[str, Any]], size: int, layer_radius: int) -> List[Dict[str, Any]]:
                out = []
                
                for item in items:
                    raw = item.get('img_raw')
                    resized = None
                    
                    # Get alliance color from item data
                    alliance_color = item.get('color', 'gray') or 'gray'
                    alliance_name = item.get('name', 'Unknown') or 'Unknown'
                    alliance_id = item.get('id', 'unknown') or 'unknown'
                    
                    if raw:
                        # Use cache key to avoid reprocessing same flags
                        cache_key = f"{alliance_id}_{size}_{alliance_color}"
                        if cache_key in _flag_cache:
                            resized = _flag_cache[cache_key]
                            self.logger.info(f"Using cached flag for {alliance_name} (ID: {alliance_id})")
                        else:
                            self.logger.info(f"Processing flag for {alliance_name} (ID: {alliance_id}) with size {size}")
                            resized = self._process_flag_image(raw, (size, size))
                            _flag_cache[cache_key] = resized
                    else:
                        # Simple placeholder without complex styling
                        self.logger.info(f"No flag image for {alliance_name} (ID: {alliance_id}), creating placeholder")
                        ph = Image.new("RGBA", (size, size), (60, 60, 80, 220))
                        d = ImageDraw.Draw(ph)
                        
                        text = (item.get('acr') or item.get('name') or "?")
                        text = (text[:3] or "?").upper()
                        
                        # Simple text rendering
                        try:
                            box = d.textbbox((0, 0), text)
                            tw, th = int(box[2] - box[0]), int(box[3] - box[1])
                        except Exception:
                            tw, th = (len(text) * 8, 12)
                        
                        d.text(((size - tw) // 2, (size - th) // 2), text, fill=(255, 255, 255, 220))
                        
                        # Simple border
                        d.rectangle([0, 0, size-1, size-1], outline=(128, 128, 128, 120), width=1)
                        resized = ph

                    new_item = dict(item)
                    new_item['img'] = resized
                    new_item['layer_radius'] = layer_radius
                    new_item['alliance_color'] = alliance_color
                    # Remove raw image to save memory
                    if 'img_raw' in new_item:
                        del new_item['img_raw']
                    out.append(new_item)
                
                self.logger.info(f"Processed {len(out)} items for layer with size {size}")
                return out
            # Process all groups with flag sizes based on distance from center
            # Center flag is largest (96px), then Protectorate/Extension (72px), 
            # then MDP/MDoAP (60px), then ODP/ODoAP (48px), then PIAT/NAP smallest (36px)
            immediate_placed = process_items(immediate_items, 72, IMMEDIATE_RADIUS)  # Protectorate/Extension - 2nd largest
            m_placed = process_items(m_items, 60, M_RADIUS)   # MDP/MDoAP - 3rd largest  
            o_placed = process_items(o_items, 48, O_RADIUS)   # ODP/ODoAP - 4th largest
            peace_placed = process_items(peace_items, 36, PEACE_RADIUS)  # PIAT/NAP - smallest

            cy_img = None
            if cy_raw_img:
                self.logger.info(f"Processing center flag with size {center_size}x{center_size}")
                cy_img = self._process_flag_image(cy_raw_img, size=(center_size, center_size))
            else:
                self.logger.warning("No center flag image available, creating placeholder")
                if Image is not None:
                    cy_img = Image.new("RGBA", (center_size, center_size), (40, 40, 40, 200))

            # Helper functions for layout
            used_angles: List[float] = []

            def _norm_angle(a: float) -> float:
                while a < 0:
                    a += 2 * math.pi
                while a >= 2 * math.pi:
                    a -= 2 * math.pi
                return a

            def _angle_diff(a: float, b: float) -> float:
                d = abs(a - b)
                while d > math.pi:
                    d = abs(d - 2 * math.pi)
                return d

            def assign_angles(items: List[Dict[str, Any]], offset: float = 0.0, avoid_angle: Optional[float] = None, avoid_range: float = 0.0) -> None:
                n = len(items)
                if n <= 0:
                    return
                step = (2 * math.pi) / n
                # Add a random starting offset to the angle calculation
                start_angle = random.uniform(0, 2 * math.pi)
                jitter = math.pi / 180 * 5
                min_gap = math.pi / 180 * 14
                for i, it in enumerate(items):
                    a = _norm_angle(start_angle + offset + step * i)
                    tries = 0
                    # Avoid placing flags on top of the legend emojis
                    while (any(_angle_diff(a, ua) < min_gap for ua in used_angles) or 
                           (avoid_angle is not None and _angle_diff(a, avoid_angle) < avoid_range)) and tries < 360:
                        a = _norm_angle(a + jitter)
                        tries += 1
                    used_angles.append(a)
                    it['angle'] = a

            def half_size(items: List[Dict[str, Any]]) -> int:
                try:
                    widths = []
                    for it in items:
                        img_obj = it.get('img')
                        if img_obj is not None:
                            widths.append(img_obj.width or 0)
                    return max((w // 2) for w in widths) if widths else 0
                except Exception:
                    return 0

            # Layout constants based on treaty closeness
            BASE_RADIUS = 150
            REGULAR_GAP = 100
            SMALL_GAP = 60
            IMMEDIATE_RADIUS = BASE_RADIUS                      # Protectorate/Extension
            M_RADIUS = IMMEDIATE_RADIUS + REGULAR_GAP           # MDP/MDoAP
            O_RADIUS = M_RADIUS + SMALL_GAP                     # ODP/ODoAP
            PEACE_RADIUS = O_RADIUS + REGULAR_GAP               # PIAT/NAP

            # Optimized margin calculation based on largest flag size
            MARGIN = 40  # Increased margin for better visual spacing
            max_extent = max([
                IMMEDIATE_RADIUS + half_size(immediate_placed),
                M_RADIUS         + half_size(m_placed),
                O_RADIUS         + half_size(o_placed),
                PEACE_RADIUS     + half_size(peace_placed),
            ])
            CANVAS_SIZE = max(1000, int(2 * (max_extent + MARGIN)))  # Increased minimum size
            CENTER_X, CENTER_Y = CANVAS_SIZE // 2, CANVAS_SIZE // 2

            def place_circle(items: List[Dict[str, Any]], radius: int) -> List[Dict[str, Any]]:
                n = len(items)
                placed: List[Dict[str, Any]] = []
                if n == 0:
                    return placed
                for i, it in enumerate(items):
                    angle_val = it.get('angle')
                    if angle_val is None:
                        angle = 2 * math.pi * i / n
                    else:
                        angle = float(angle_val)
                    img_obj = it.get('img')
                    img_width = img_obj.width if img_obj else 48
                    img_height = img_obj.height if img_obj else 48
                    x = CENTER_X + int(radius * math.cos(angle)) - img_width // 2
                    y = CENTER_Y + int(radius * math.sin(angle)) - img_height // 2
                    it['pos'] = (x, y)
                    it['angle'] = angle
                    placed.append(it)
                return placed

            assign_angles(immediate_placed, avoid_angle=-math.pi/2, avoid_range=math.pi/6)
            assign_angles(m_placed, avoid_angle=-math.pi/2, avoid_range=math.pi/6)
            assign_angles(o_placed, avoid_angle=-math.pi/2, avoid_range=math.pi/6)
            assign_angles(peace_placed, avoid_angle=-math.pi/2, avoid_range=math.pi/6)

            immediate_final = place_circle(immediate_placed, IMMEDIATE_RADIUS)
            m_final = place_circle(m_placed, M_RADIUS)
            o_final = place_circle(o_placed, O_RADIUS)
            peace_final = place_circle(peace_placed, PEACE_RADIUS)

            # Create enhanced background
            canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))  # Transparent background
            draw = ImageDraw.Draw(canvas)
            cy_center = (CENTER_X, CENTER_Y)
            
            # --- Draw emoji legend (true north of center) ---
            legend_positions = {}
            emoji_size = 48  # Standard size for all emoji legend icons
            legend_spacing = emoji_size + 20  # Space between emoji icons
            
            # Define treaty types and their positions (ON the rings, but drawn after rings)
            treaty_legend = [
                ('Peace', PEACE_RADIUS, 'PIAT'),      # ON the Peace ring
                ('ODP', O_RADIUS, 'ODP'),             # ON the ODP ring
                ('MDP', M_RADIUS, 'MDP'),             # ON the MDP ring
                ('Protectorate', IMMEDIATE_RADIUS, 'Protectorate')  # ON the Protectorate ring
            ]
            
            # Store emoji data for drawing after rings
            emoji_data = []
            
            for treaty_type, radius, color_key in treaty_legend:
                emoji_img = emoji_images.get(treaty_type) if emoji_images else None
                if emoji_img:
                    # Process emoji to standard size
                    processed_emoji = self._process_flag_image(emoji_img, (emoji_size, emoji_size))
                    
                    # Position at true north (top) of the center, ON the appropriate ring
                    # True north = -π/2 radians (top of the circle)
                    north_angle = -math.pi / 2  # Top of the circle
                    legend_x = CENTER_X + int(radius * math.cos(north_angle)) - emoji_size // 2
                    legend_y = CENTER_Y + int(radius * math.sin(north_angle)) - emoji_size // 2
                    
                    # Ensure emoji stays within canvas bounds
                    legend_x = max(10, min(legend_x, CANVAS_SIZE - emoji_size - 10))
                    legend_y = max(10, min(legend_y, CANVAS_SIZE - emoji_size - 10))
                    
                    # Store position for collision detection
                    legend_positions[treaty_type] = (legend_x, legend_y, emoji_size, emoji_size)
                    
                    # Store emoji data for drawing after rings
                    emoji_data.append((processed_emoji, legend_x, legend_y))
                    
                    self.logger.info(f"Prepared emoji legend for {treaty_type} ON ring at ({legend_x}, {legend_y})")
            
            # Define ring widths for each treaty type (thicker rings for closer treaties)
            ring_widths = {
                'PIAT': 1,      # PIAT/NAP - thinnest (furthest)
                'ODP': 3,       # ODP/ODoAP - thin
                'MDP': 4,       # MDP/MDoAP - medium
                'Protectorate': 6 # Protectorate/Extension - thickest (closest)
            }
            
            # Draw rings in order from furthest to closest with middle shades
            # Middle shade calculations between light and dark variants:
            # Red: (255,150,150) + (200,50,50) = (227,100,100)
            # Blue: (150,150,255) + (50,50,200) = (100,100,227)  
            # Yellow: (255,255,150) + (200,200,50) = (227,227,100)
            # Green: (150,255,150) + (100,200,100) = (125,227,125)
            
            # Ring colors - middle shades between light and dark treaty colors
            ring_colors = {
                'PIAT': (125, 227, 125, 200),     # Middle Green (PIAT/NAP)
                'MDP': (100, 100, 227, 200),      # Middle Blue (ODP/ODoAP)
                'ODP': (227, 227, 100, 200),      # Middle Yellow (MDP/MDoAP)
                'Protectorate': (227, 100, 100, 200)  # Middle Red (Protectorate/Extension)
            }
            
            self._draw_ring(draw, CENTER_X, CENTER_Y, PEACE_RADIUS, ring_colors.get('PIAT', (125, 227, 125, 200)), width=ring_widths.get('PIAT', 1))
            self._draw_ring(draw, CENTER_X, CENTER_Y, O_RADIUS, ring_colors.get('ODP', (227, 227, 100, 200)), width=ring_widths.get('ODP', 3))
            self._draw_ring(draw, CENTER_X, CENTER_Y, M_RADIUS, ring_colors.get('MDP', (100, 100, 227, 200)), width=ring_widths.get('MDP', 4))
            self._draw_ring(draw, CENTER_X, CENTER_Y, IMMEDIATE_RADIUS, ring_colors.get('Protectorate', (227, 100, 100, 200)), width=ring_widths.get('Protectorate', 6))

            # --- Draw emojis ON TOP of the rings (so rings don't go through them) ---
            for processed_emoji, legend_x, legend_y in emoji_data:
                canvas.paste(processed_emoji, (legend_x, legend_y), processed_emoji)
                self.logger.info(f"Drew emoji ON TOP of ring at ({legend_x}, {legend_y})")

            # --- Draw all lines (inter-alliance first, then center lines) ---
            all_placed_items = immediate_final + m_final + o_final + peace_final
            partner_positions = {int(p['id']): p['pos'] for p in all_placed_items if 'id' in p and 'pos' in p}
            partner_ids_set = set(partner_positions.keys())
            inter_alliance_lines_drawn = set()
            
            # Draw inter-alliance lines first (lowest priority)
            for treaty in all_treaties:
                a1_id_raw = treaty.get('alliance1_id')
                a2_id_raw = treaty.get('alliance2_id')
                
                if not a1_id_raw or not a2_id_raw:
                    continue
                
                try:
                    a1_id = int(a1_id_raw)
                    a2_id = int(a2_id_raw)
                except (ValueError, TypeError):
                    continue
                    
                if a1_id == center_id or a2_id == center_id:
                    continue
                
                treaty_key = tuple(sorted((a1_id, a2_id)))
                if treaty_key in inter_alliance_lines_drawn:
                    continue
                
                if a1_id in partner_ids_set and a2_id in partner_ids_set and a1_id != a2_id:
                    pos1 = partner_positions[a1_id]
                    pos2 = partner_positions[a2_id]

                    sample_img_obj = next((item.get('img') for item in all_placed_items if item.get('id') == a1_id), None)
                    img_width1 = sample_img_obj.width if sample_img_obj else 48
                    img_height1 = sample_img_obj.height if sample_img_obj else 48
                    
                    sample_img_obj = next((item.get('img') for item in all_placed_items if item.get('id') == a2_id), None)
                    img_width2 = sample_img_obj.width if sample_img_obj else 48
                    img_height2 = sample_img_obj.height if sample_img_obj else 48
                    
                    center1 = (pos1[0] + img_width1 // 2, pos1[1] + img_height1 // 2)
                    center2 = (pos2[0] + img_width2 // 2, pos2[1] + img_height2 // 2)
                    
                    # Create list of flags to avoid (all flags except the two we're connecting)
                    flags_to_avoid = []
                    for other_item in all_placed_items:
                        if other_item.get('id') not in [a1_id, a2_id]:
                            other_img = other_item.get('img')
                            other_pos = other_item.get('pos')
                            if other_img and other_pos:
                                flags_to_avoid.append((other_pos, (other_img.width, other_img.height)))
                    
                    # Also avoid the legend emojis
                    for leg_x, leg_y, leg_w, leg_h in legend_positions.values():
                        flags_to_avoid.append(((leg_x, leg_y), (leg_w, leg_h)))
                    
                    line_color = self.TREATY_COLORS.get(self._normalize_treaty_type(treaty.get('treaty_type')), (200, 200, 220, 180))
                    self._draw_treaty_line(draw, center1, center2, line_color, flags_to_avoid=flags_to_avoid)
                    inter_alliance_lines_drawn.add(treaty_key)

            # Draw center alliance lines to all layers (highest priority)
            if cy_img is not None:
                for layer_items, default_line_color_key in [
                    (peace_final, 'PIAT'),
                    (o_final, 'ODP'),
                    (m_final, 'MDP'),
                    (immediate_final, 'Protectorate')
                ]:
                    for it in layer_items:
                        img_obj = it.get('img')
                        if img_obj:
                            pos = it.get('pos')
                            partner_center_x = pos[0] + img_obj.width // 2
                            partner_center_y = pos[1] + img_obj.height // 2
                            
                            line_type = it.get('line_type', default_line_color_key)
                            line_color = self.TREATY_COLORS.get(line_type, (200, 200, 220, 180))
                            
                            # Create list of flags to avoid (all flags except the center and current partner)
                            flags_to_avoid = []
                            current_partner_id = it.get('id')
                            for other_item in all_placed_items:
                                if other_item.get('id') != current_partner_id:
                                    other_img = other_item.get('img')
                                    other_pos = other_item.get('pos')
                                    if other_img and other_pos:
                                        flags_to_avoid.append((other_pos, (other_img.width, other_img.height)))
                            
                            # Also avoid the legend emojis
                            for leg_x, leg_y, leg_w, leg_h in legend_positions.values():
                                flags_to_avoid.append(((leg_x, leg_y), (leg_w, leg_h)))
                            
                            self._draw_treaty_line(
                                draw, cy_center, (partner_center_x, partner_center_y),
                                line_color, flags_to_avoid=flags_to_avoid
                            )

            # Debug logging
            if all_treaties:
                self.logger.info(f"Drawing treaty web: {len(all_treaties)} total treaties, {len(inter_alliance_lines_drawn)} inter-alliance lines drawn, {len(partner_ids_set)} partner alliances")

            # --- Draw all flags in proper layer order (center first, then closest to furthest) ---
            # Draw center alliance flag first (largest, should be behind others)
            if cy_img is not None:
                center_pos = (CENTER_X - center_size // 2, CENTER_Y - center_size // 2)
                canvas.paste(cy_img, center_pos, cy_img)

            # Draw alliance flags in order (closest to furthest layers)
            for layer_items in [immediate_final, m_final, o_final, peace_final]:
                for it in layer_items:
                    img = it.get('img')
                    if img:
                        pos = it.get('pos', (0, 0))
                        canvas.paste(img, pos, img)

            if io is None:
                return None
            buf = io.BytesIO()
            canvas.save(buf, format='PNG')
            buf.seek(0)
            return discord.File(buf, filename="treaty_web.png")

        except Exception as e:
            self.logger.error(f"Error during treaty web image generation: {e}")
            self.logger.exception("Full traceback:")
            return None

    async def _compose_treaty_web_image(self, treaties: List[Dict[str, Any]], center_alliance_id: Optional[int] = None) -> Optional[discord.File]:
        if Image is None or ImageDraw is None or io is None:
            return None

        cy_flag_url: Optional[str] = None
        center_alliance_color: Optional[str] = None  # Remove default - will be determined from query
        partners: List[Dict[str, Any]] = []
        partner_types: Dict[int, set] = {}

        try:
            center_id = int(center_alliance_id if center_alliance_id is not None else int(self.default_alliance_id or 0))
        except Exception:
            center_id = int(self.default_alliance_id or 0)
        
        self.logger.info(f"Generating treaty web for center alliance ID: {center_id}")

        for t in treaties or []:
            a1 = t.get('alliance1') or {}
            a2 = t.get('alliance2') or {}
            a1_id = int(str(a1.get('id') or t.get('alliance1_id') or 0)) if (a1.get('id') or t.get('alliance1_id')) else 0
            a2_id = int(str(a2.get('id') or t.get('alliance2_id') or 0)) if (a2.get('id') or t.get('alliance2_id')) else 0

            if a1_id == center_id:
                if not cy_flag_url:
                    cy_flag_url = (a1.get('flag') or '').strip()
                if not center_alliance_color:
                    center_alliance_color = (a1.get('color') or 'gold').lower()
                
                partner_id = a2_id
                other = a2
            elif a2_id == center_id:
                if not cy_flag_url:
                    cy_flag_url = (a2.get('flag') or '').strip()
                if not center_alliance_color:
                    center_alliance_color = (a2.get('color') or 'gold').lower()
                
                partner_id = a1_id
                other = a1
            else:
                continue

            if partner_id not in partner_types:
                partner_types[partner_id] = set()
                partners.append(other)
            
            ttype = self._normalize_treaty_type(t.get('treaty_type', ''))
            partner_types[partner_id].add(ttype)

        immediate_partners: List[Dict[str, Any]] = []
        m_partners: List[Dict[str, Any]] = []
        o_partners: List[Dict[str, Any]] = []
        peace_partners: List[Dict[str, Any]] = []

        for p in partners:
            pid = int(p.get('id') or 0)
            types = partner_types.get(pid, set())
            
            # Determine the highest priority treaty type for the line color
            if 'Protectorate' in types:
                p['line_type'] = 'Protectorate'
            elif 'Extension' in types:
                p['line_type'] = 'Extension'
            elif 'MDoAP' in types:
                p['line_type'] = 'MDoAP'
            elif 'MDP' in types:
                p['line_type'] = 'MDP'
            elif 'ODoAP' in types:
                p['line_type'] = 'ODoAP'
            elif 'ODP' in types:
                p['line_type'] = 'ODP'
            elif 'PIAT' in types:
                p['line_type'] = 'PIAT'
            else:
                p['line_type'] = 'NAP'

            # Categorize partners based on their highest priority treaty
            if ('Protectorate' in types) or ('Extension' in types):
                immediate_partners.append(p)
            elif ('MDoAP' in types) or ('MDP' in types):
                m_partners.append(p)
            elif ('ODoAP' in types) or ('ODP' in types):
                o_partners.append(p)
            elif ('PIAT' in types) or ('NAP' in types):
                peace_partners.append(p)

        cy_img = await self._fetch_flag_image(cy_flag_url or '')
        
        # If we still don't have the center alliance color, try to get it from the alliance details
        if not center_alliance_color and center_id:  # Check if None instead of 'gold'
            try:
                center_details = await self.query_instance.resolve_alliance(center_id)
                if center_details and isinstance(center_details, dict):
                    center_alliance_color = (center_details.get('color') or 'gold').lower()
            except Exception as e:
                self.logger.warning(f"Could not resolve center alliance color: {e}")
        
        if not center_alliance_color:
            center_alliance_color = 'gold'
        
        self.logger.info(f"Center alliance color: {center_alliance_color}, flag URL: {cy_flag_url}")
        self.logger.info(f"Partners found: {len(partners)} (immediate: {len(immediate_partners)}, MDP: {len(m_partners)}, ODP: {len(o_partners)}, Peace: {len(peace_partners)})")

        async def fetch_raw_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            tasks = [self._fetch_flag_image(p.get('flag') or '') for p in items]
            raws = await asyncio.gather(*tasks) if tasks else []
            out: List[Dict[str, Any]] = []
            for i, raw in enumerate(raws):
                item = dict(items[i])
                item['img_raw'] = raw
                out.append(item)
            return out

        immediate_raw = await fetch_raw_items(immediate_partners)
        m_raw = await fetch_raw_items(m_partners)
        o_raw = await fetch_raw_items(o_partners)
        peace_raw = await fetch_raw_items(peace_partners)

        # --- Fetch emoji images for legend ---
        emoji_ids = {
            'Protectorate': 1449742838081257576,  # Prot
            'MDP': 1449742839364845588,           # MLevel
            'ODP': 1449742840316821504,           # OLevel
            'Peace': 1449742841642225664,         # Peace
        }
        
        emoji_tasks = {name: self._fetch_emoji_image(emoji_id) for name, emoji_id in emoji_ids.items()}
        emoji_results = await asyncio.gather(*emoji_tasks.values())
        emoji_images = dict(zip(emoji_tasks.keys(), emoji_results))
        
        self.logger.info(f"Fetched {len([img for img in emoji_images.values() if img])} emoji images for legend.")

        # Fetch treaties for all partners to find inter-bloc treaties
        partner_ids = [str(p['id']) for p in partners if p.get('id')]
        if partner_ids:
            try:
                all_treaties = await self.query_instance.get_alliances_treaties(partner_ids, force_refresh=True)
                # Also include the center alliance ID to get treaties between center and partners
                all_center_treaties = await self.query_instance.get_alliances_treaties([str(center_id)], force_refresh=True)
                # Combine both sets of treaties, avoiding duplicates
                seen_treaty_keys = set()
                combined_treaties = []
                
                def make_treaty_key(treaty):
                    a1 = treaty.get('alliance1_id') or treaty.get('alliance1', {}).get('id', 0)
                    a2 = treaty.get('alliance2_id') or treaty.get('alliance2', {}).get('id', 0)
                    return tuple(sorted((a1, a2)))

                for t in (all_treaties or []) + (all_center_treaties or []):
                    key = make_treaty_key(t)
                    if key not in seen_treaty_keys:
                        combined_treaties.append(t)
                        seen_treaty_keys.add(key)
                
                all_treaties = combined_treaties

            except Exception as e:
                self.logger.error(f"Failed to fetch inter-bloc treaties: {e}")
                all_treaties = treaties
        else:
            all_treaties = treaties

        try:
            return await asyncio.to_thread(
                self._generate_treaty_web_image_sync,
                immediate_raw, m_raw, o_raw, peace_raw, cy_img, all_treaties, 
                center_id, emoji_images=emoji_images
            )
        except Exception as e:
            self.logger.error(f"Error during treaty web image generation: {e}")
            self.logger.exception("Full traceback:")
            return None

    def _format_treaty_line(self, t: Dict[str, Any], alliance_id: int) -> str:
        """Format a single treaty line with a masked link to the treaty partner."""
        try:
            a1 = t.get('alliance1') or {}
            a2 = t.get('alliance2') or {}
            a1_id = int(str(a1.get('id') or t.get('alliance1_id') or 0)) if (a1.get('id') or t.get('alliance1_id')) else 0
            a2_id = int(str(a2.get('id') or t.get('alliance2_id') or 0)) if (a2.get('id') or t.get('alliance2_id')) else 0
            
            partner_name = ""
            partner_id = 0
            if a1_id and a1_id != alliance_id:
                partner_name = str(a1.get('name', '') or t.get('alliance1_name', '')).strip()
                partner_id = a1_id
            elif a2_id and a2_id != alliance_id:
                partner_name = str(a2.get('name', '') or t.get('alliance2_name', '')).strip()
                partner_id = a2_id
            
            if not partner_name:
                partner_name = "Unknown Alliance"
            
            treaty_type = self._normalize_treaty_type(t.get('treaty_type', ''))
            
            # Create a masked link to the partner alliance's PnW page
            if partner_id and partner_id > 0:
                partner_url = f"https://politicsandwar.com/alliance/id={partner_id}"
                return f"• [{partner_name}]({partner_url}) ({treaty_type})"
            else:
                return f"• {partner_name} ({treaty_type})"
        except Exception as e:
            self.logger.error(f"Error formatting treaty line: {e}")
            return "• Error formatting treaty"

    def _format_treaties_embed_sync(self, treaties: List[Dict[str, Any]], center_alliance_id: Optional[int] = None, center_name: Optional[str] = None) -> discord.Embed:
        """Format treaties into a rich Discord embed with proper categories and emojis."""
        # Determine center id and title
        try:
            if center_alliance_id and center_alliance_id > 0:
                title = f"🌐 Treaties for {center_name or f'Alliance #{center_alliance_id}'}"
            else:
                title = "🌐 Alliance Treaties"
            
            embed = discord.Embed(title=title, color=0x00AEFF)
            
            # Define treaty categories with specified emojis
            cat_emojis = { 
                'Immediate': f"{emoji_mod.mention('Prot') or 'Prot'} Protection & Extensions", 
                'M Level': f"{emoji_mod.mention('MLevel') or 'MLevel'} MDoAP & MDP", 
                'O Level': f"{emoji_mod.mention('OLevel') or 'OLevel'} ODoAP & ODP", 
                'Peace': f"{emoji_mod.mention('Peace') or 'Peace'} PIAT & NAP", 
            }
            
            # Categorize treaties by the new categories
            immediate_treaties = []      # Protectorate + Extension
            m_level_treaties = []        # MDP + MDoAP  
            o_level_treaties = []        # ODP + ODoAP
            peace_treaties = []          # PIAT + NAP
            
            for t in treaties:
                treaty_type = self._normalize_treaty_type(t.get('treaty_type', ''))
                line = self._format_treaty_line(t, center_alliance_id or 0)
                
                if treaty_type in ['Protectorate', 'Extension']:
                    immediate_treaties.append(line)
                elif treaty_type in ['MDP', 'MDoAP']:
                    m_level_treaties.append(line)
                elif treaty_type in ['ODP', 'ODoAP']:
                    o_level_treaties.append(line)
                elif treaty_type in ['PIAT', 'NAP']:
                    peace_treaties.append(line)
            
            # Add fields for each category with masked links
            def add_category_field(category_name, items, emoji_field_name):
                if items:
                    # Split long lists into chunks
                    chunks = []
                    current = ""
                    for item in items:
                        if len(current) + len(item) + 1 > 1024:
                            chunks.append(current)
                            current = item
                        else:
                            if current:
                                current += "\n" + item
                            else:
                                current = item
                    if current:
                        chunks.append(current)
                    
                    for i, chunk in enumerate(chunks):
                        field_name = f"{emoji_field_name}" if i == 0 else f"{emoji_field_name} (cont.)"
                        embed.add_field(name=field_name, value=chunk, inline=False)
            
            # Add the four main categories
            add_category_field("Immediate", immediate_treaties, cat_emojis['Immediate'])
            add_category_field("M Level", m_level_treaties, cat_emojis['M Level'])
            add_category_field("O Level", o_level_treaties, cat_emojis['O Level'])
            add_category_field("Peace", peace_treaties, cat_emojis['Peace'])
            
            if not any([immediate_treaties, m_level_treaties, o_level_treaties, peace_treaties]):
                embed.add_field(name="No Treaties", value="This alliance has no active treaties.", inline=False)
            
            # Add footer with timestamp
            embed.set_footer(text=f"Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC")
            
            return embed
            
        except Exception as e:
            self.logger.error(f"Error formatting treaties embed: {e}")
            # Return a fallback embed
            return discord.Embed(
                title="🌐 Treaty Information",
                description="Error loading treaty information.",
                color=0xFF0000
            )

    @commands.hybrid_command(name="treaties", description="Show treaties and treaty web for any alliance")  # type: ignore
    @app_commands.describe(alliance="Alliance name or ID", auto_update="Enable auto-updating this message daily (True/False)")
    async def treaties_command(self, ctx: commands.Context, alliance: Optional[str] = None, auto_update: bool = False):
        """Query alliance treaties and display them in a rich embed."""
        try:
            try:
                if hasattr(ctx, 'interaction') and ctx.interaction and not ctx.interaction.response.is_done():
                    await ctx.interaction.response.send_message("🔄 Refreshing treaties…", ephemeral=True, delete_after=1)
            except Exception:
                pass

            treaties: List[Dict[str, Any]] = []
            center_id: Optional[int] = None
            center_name: Optional[str] = None
            try:
                alliance_cog = self.bot.get_cog('AllianceManager')
                if alliance_cog and hasattr(alliance_cog, 'query_system') and alliance_cog.query_system:
                    arg = (alliance or "").strip()
                    if arg:
                        resolved = await alliance_cog.query_system.resolve_alliance(arg)
                        try:
                            if resolved and isinstance(resolved, dict) and resolved.get('id'):
                                center_id = int(str(resolved.get('id')))
                                center_name = (resolved.get('name') or '').strip() or None
                            elif arg.isdigit():
                                center_id = int(arg)
                            else:
                                center_id = None
                        except Exception:
                            center_id = None

                        if not center_id or int(center_id) <= 0:
                            msg = "❌ Could not resolve alliance. Enter a valid name or ID."
                            if hasattr(ctx, 'interaction') and ctx.interaction:
                                await ctx.interaction.followup.send(msg)
                            else:
                                await ctx.reply(msg)
                            return
                    else:
                        if self.default_alliance_id:
                            center_id = int(self.default_alliance_id)
                            center_name = self.default_alliance_name
                        else:
                            center_id = None
                            center_name = None

                    res = await alliance_cog.query_system.get_alliance_treaties(str(center_id), force_refresh=True)
                    treaties = res or []
                else:
                    treaties = []
            except Exception as qerr:
                self.logger.error(f"Error querying treaties: {qerr}")

            treaty_file = await self._compose_treaty_web_image(treaties, center_alliance_id=center_id or 0)
            embed = await asyncio.to_thread(self._format_treaties_embed_sync, treaties, center_id or 0, center_name)
            files: List[discord.File] = []
            if treaty_file:
                embed.set_image(url=f"attachment://{treaty_file.filename}")
                files = [treaty_file]

            view = None
            if center_id and int(center_id) == int(self.default_alliance_id or 0):
                view = TreatiesRefreshView(self, cast(int, center_id))

            try:
                channel_id = getattr(getattr(ctx, 'channel', None), 'id', None)
                has_new_file = bool(files)
                edited = False
                
                if channel_id and channel_id in self.treaties_message_map:
                    try:
                        last_msg_id = self.treaties_message_map[channel_id]
                        last_msg = await ctx.channel.fetch_message(last_msg_id)
                        
                        if has_new_file:
                            # Delete old message and send new one with files
                            await last_msg.delete()
                            sent = await ctx.send(embed=embed, view=view, files=files if files else [])
                            self.persistent_views[sent.id] = cast(int, center_id)
                            self._save_persistent_views()  # type: ignore
                            self.treaties_message_map[channel_id] = sent.id
                            edited = True  # Mark as handled
                        else:
                            # Edit existing message without files
                            await last_msg.edit(embed=embed, view=view, attachments=list(last_msg.attachments))
                            # Update persistent views for existing message
                            if last_msg.id in self.persistent_views:
                                self.persistent_views[last_msg.id] = cast(int, center_id)
                                self._save_persistent_views()
                            edited = True
                    except Exception:
                        edited = False
                        
                if not edited:
                            # Send new message
                        sent = await ctx.send(embed=embed, view=view, files=files if files else [])
                        self.persistent_views[sent.id] = cast(int, center_id)
                        self._save_persistent_views()  # type: ignore
                        try:
                            if channel_id:
                                self.treaties_message_map[channel_id] = sent.id
                        except Exception:
                            pass

                    # --- Auto-update handling ---
                        if auto_update:
                            now = datetime.now(timezone.utc)
                            self.auto_update_data[sent.id] = {
                                'alliance_id': cast(int, center_id),
                                'channel_id': channel_id,
                                'auto_update_enabled': True,
                                'last_update': now.isoformat(),
                                'next_update': (now + timedelta(hours=24)).isoformat()
                            }
                            self._save_auto_update_data()
                            self.logger.info(f"Enabled auto-update for message {sent.id}")

                try:
                    if hasattr(ctx, 'interaction') and ctx.interaction:
                        try:
                            await ctx.interaction.delete_original_response()
                        except Exception:
                            try:
                                await ctx.interaction.edit_original_response(content="", embed=None, view=None, attachments=[])
                            except Exception:
                                pass
                except Exception:
                    pass
            except Exception as send_error:
                self.logger.error(f"Error sending treaties embed: {send_error}")
                fallback_embed = discord.Embed(
                    title="❌ Error Loading Treaties",
                    description="An error occurred while loading treaty information.",
                    color=0xff0000
                )
                try:
                    if hasattr(ctx, 'interaction') and ctx.interaction:
                        await ctx.interaction.edit_original_response(embed=fallback_embed)
                    else:
                        await ctx.send(embed=fallback_embed)
                except Exception:
                    pass

        except Exception as e:
            self.logger.error(f"/treaties error: {e}")
            try:
                error_embed = discord.Embed(
                    title="❌ An error occurred",
                    description=str(e),
                    color=0xff0000
                )
                if hasattr(ctx, 'interaction') and ctx.interaction:
                    try:
                        await ctx.interaction.edit_original_response(content="", embed=None, view=None, attachments=[])
                    except Exception:
                        pass
                    await ctx.interaction.followup.send(embed=error_embed)
                else:
                    await ctx.reply(embed=error_embed)
            except Exception:
                pass

async def setup(bot: commands.Bot, query_instance=None, calc_instance=None) -> None:
    """Setup function for the TreatiesManager cog."""
    await bot.add_cog(TreatiesManager(bot, query_instance, calc_instance))
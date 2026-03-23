import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import discord
from discord.ext import commands
import logging
import os
import threading
import http.server
import socketserver
try:
    from pyngrok import ngrok
except ImportError:
    ngrok = None
import socket
import math
import sys
import pathlib
from PIL import Image, ImageDraw, ImageFont
import io
import aiohttp

# Add the Systems directory to Python path for imports
sys.path.append(str(pathlib.Path(__file__).parent.parent))
from Util.Graphs.treaty_graph import TreatyGraph

from Systems.Functions.utils import get_local_ip, get_service_port, SERVICE_UNIVERSE, release_port
from collections import defaultdict
import urllib.request
import concurrent.futures
import shutil
import json

COLOR_HEX_MAP = {
    "white": "#FFFFFF", "grey": "#808080", "black": "#000000",
    "gold": "#FFD700", "pink": "#FFC0CB", "brown": "#A52A2A",
    "mint": "#98FF98", "green": "#00FF00", "aqua": "#00FFFF",
    "lavender": "#E6E6FA", "lime": "#00FF00", "maroon": "#800000",
    "olive": "#808000", "yellow": "#FFFF00", "turquoise": "#40E0D0",
    "red": "#FF0000", "purple": "#800080", "orange": "#FFA500",
    "blue": "#0000FF", "beige": "#DDDDDD"
}

class TreatyUniverse:
    def __init__(self, query_instance):
        self.query_instance = query_instance
        self.treaty_graph = TreatyGraph()
        
        # Treaty colors for PIL image (RGBA)
        self.TREATY_COLORS = {
            'ODP': (255, 255, 150, 255),      # Light Yellow
            'ODoAP': (255, 215, 0, 255),      # Gold/Strong Yellow
            'MDP': (150, 150, 255, 255),      # Light Blue
            'MDoAP': (50, 50, 200, 255),      # Dark Blue
            'Protectorate': (255, 150, 150, 255), # Light Red
            'NAP': (150, 255, 150, 255),      # Light Green
            'PIAT': (100, 255, 100, 255),     # Light Green
            'Extension': (200, 50, 50, 255),   # Dark Red
        }

    async def get_all_treaties(self) -> List[Dict[str, Any]]:
        """
        Fetches all treaties from the game.
        """
        try:
            all_treaties = await self.query_instance.get_all_treaties_paginated(force_refresh=True)
            return all_treaties
        except Exception as e:
            print(f"Error fetching all treaties: {e}")
            return []

    def _normalize_treaty_type(self, ttype: str) -> str:
        """Normalize various treaty type labels/abbreviations to canonical keys."""
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

    async def _fetch_flag_image(self, url: str) -> Optional[Image.Image]:
        """Download an image from URL and return a PIL Image, or None on failure."""
        try:
            if not url:
                return None
            timeout_obj = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout_obj) as session:
                headers = {"User-Agent": "Mozilla/5.0 (compatible; DiscordBot/1.0)"}
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.read()
            bio = io.BytesIO(data)
            img = Image.open(bio)
            return img
        except Exception as e:
            print(f"Error fetching flag from {url}: {e}")
            return None

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
            print(f"Error processing flag image: {e}")
            return Image.new("RGBA", size, (40, 40, 40, 200))

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

    def _draw_treaty_line(self, draw, start_pos, end_pos, line_color, width=3, flags_to_avoid=None, curved=True):
        """Draw a curved treaty line, avoiding overlapping flags."""
        line_width = width or 3
        
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

    async def generate_universe_image(self, all_treaties: List[Dict[str, Any]], blocs: Dict[str, List[List[int]]]) -> Optional[discord.File]:
        """Generate a massive PIL image with alliance flags grouped by blocs and connected by treaty lines."""
        try:
            # Get treaty graph data
            treaty_graph = self.treaty_graph.build_treaty_graph(all_treaties)
            
            if not treaty_graph.nodes:
                return None

            # Build alliance data mapping
            alliance_data = {}
            for node_id, data in treaty_graph.nodes(data=True):
                alliance_data[node_id] = {
                    'name': data.get('name', str(node_id)),
                    'score': data.get('score', 0),
                    'color': data.get('color', '#888888'),
                    'flag_url': None  # Will be populated from treaties
                }

            # Extract flag URLs from treaties
            for treaty in all_treaties:
                a1_data = treaty.get('alliance1') or {}
                a2_data = treaty.get('alliance2') or {}
                a1_id = treaty.get('alliance1_id')
                a2_id = treaty.get('alliance2_id')
                
                if a1_id and a1_id in alliance_data:
                    alliance_data[a1_id]['flag_url'] = a1_data.get('flag')
                if a2_id and a2_id in alliance_data:
                    alliance_data[a2_id]['flag_url'] = a2_data.get('flag')

            # Get combined blocs
            combined_blocs = blocs.get('combined', []) if blocs else []
            
            # Calculate image dimensions based on number of blocs
            num_blocs = len(combined_blocs)
            if num_blocs == 0:
                return None
                
            # Calculate layout - arrange blocs in a grid
            cols = max(1, int(math.sqrt(num_blocs)))
            rows = (num_blocs + cols - 1) // cols
            
            # Dimensions for each bloc section
            bloc_width = 400
            bloc_height = 300
            flag_size = 48
            padding = 20
            
            # Total image dimensions
            total_width = cols * bloc_width + (cols + 1) * padding
            total_height = rows * bloc_height + (rows + 1) * padding + 100  # Extra space for title
            
            # Create canvas
            canvas = Image.new("RGBA", (total_width, total_height), (15, 15, 15, 255))
            draw = ImageDraw.Draw(canvas)
            
            # Fetch all flag images in parallel
            flag_tasks = []
            flag_urls = {}
            for alliance_id, data in alliance_data.items():
                if data['flag_url']:
                    flag_urls[alliance_id] = data['flag_url']
                    flag_tasks.append(self._fetch_flag_image(data['flag_url']))
            
            # Process flags
            flag_images = {}
            if flag_tasks:
                fetched_flags = await asyncio.gather(*flag_tasks)
                flag_list = list(flag_urls.keys())
                for i, alliance_id in enumerate(flag_list):
                    if i < len(fetched_flags) and fetched_flags[i]:
                        flag_images[alliance_id] = self._process_flag_image(fetched_flags[i], (flag_size, flag_size))
            
            # Create placeholder flags for missing ones
            for alliance_id in alliance_data:
                if alliance_id not in flag_images:
                    placeholder = Image.new("RGBA", (flag_size, flag_size), (60, 60, 80, 220))
                    d = ImageDraw.Draw(placeholder)
                    
                    # Add alliance acronym
                    name = alliance_data[alliance_id]['name']
                    acronym = ''.join(word[0] for word in name.split() if word).upper()[:3]
                    
                    try:
                        # Try to get text dimensions
                        bbox = d.textbbox((0, 0), acronym)
                        tw, th = int(bbox[2] - bbox[0]), int(bbox[3] - bbox[1])
                    except Exception:
                        tw, th = (len(acronym) * 8, 12)
                    
                    d.text(((flag_size - tw) // 2, (flag_size - th) // 2), acronym, fill=(255, 255, 255, 220))
                    d.rectangle([0, 0, flag_size-1, flag_size-1], outline=(128, 128, 128, 120), width=1)
                    
                    flag_images[alliance_id] = placeholder

            # Position and draw blocs
            bloc_positions = {}
            alliance_positions = {}
            
            for bloc_idx, bloc in enumerate(combined_blocs):
                # Calculate bloc position in grid
                row = bloc_idx // cols
                col = bloc_idx % cols
                
                bloc_x = col * bloc_width + (col + 1) * padding
                bloc_y = row * bloc_height + (row + 1) * padding + 100
                
                bloc_positions[bloc_idx] = (bloc_x, bloc_y)
                
                # Draw bloc background
                bloc_rect = [
                    bloc_x - padding//2, 
                    bloc_y - padding//2, 
                    bloc_x + bloc_width + padding//2, 
                    bloc_y + bloc_height + padding//2
                ]
                draw.rectangle(bloc_rect, fill=(25, 25, 25, 200), outline=(100, 100, 100, 255), width=2)
                
                # Draw bloc title
                bloc_title = f"Bloc {bloc_idx + 1} ({len(bloc)} alliances)"
                try:
                    draw.text((bloc_x, bloc_y - 30), bloc_title, fill=(200, 200, 200, 255))
                except Exception:
                    pass
                
                # Position alliances within bloc in a circle
                num_alliances = len(bloc)
                if num_alliances > 0:
                    center_x = bloc_x + bloc_width // 2
                    center_y = bloc_y + bloc_height // 2
                    radius = min(bloc_width, bloc_height) // 3
                    
                    for i, alliance_id in enumerate(bloc):
                        if alliance_id in alliance_data:
                            angle = 2 * math.pi * i / num_alliances
                            x = center_x + int(radius * math.cos(angle)) - flag_size // 2
                            y = center_y + int(radius * math.sin(angle)) - flag_size // 2
                            
                            alliance_positions[alliance_id] = (x + flag_size // 2, y + flag_size // 2)
                            
                            # Draw flag
                            if alliance_id in flag_images:
                                canvas.paste(flag_images[alliance_id], (x, y), flag_images[alliance_id])

            # Draw treaty lines between alliances in the same bloc
            for bloc in combined_blocs:
                bloc_alliances = set(bloc)
                
                for treaty in all_treaties:
                    a1_id = treaty.get('alliance1_id')
                    a2_id = treaty.get('alliance2_id')
                    
                    if (a1_id in bloc_alliances and a2_id in bloc_alliances and 
                        a1_id in alliance_positions and a2_id in alliance_positions and
                        a1_id != a2_id):
                        
                        treaty_type = self._normalize_treaty_type(treaty.get('treaty_type', ''))
                        line_color = self.TREATY_COLORS.get(treaty_type, (200, 200, 220, 180))
                        
                        start_pos = alliance_positions[a1_id]
                        end_pos = alliance_positions[a2_id]
                        
                        # Create list of flags to avoid (all flags in the bloc except these two)
                        flags_to_avoid = []
                        for other_id in bloc:
                            if other_id != a1_id and other_id != a2_id and other_id in alliance_positions:
                                flags_to_avoid.append((alliance_positions[other_id], (flag_size, flag_size)))
                        
                        self._draw_treaty_line(draw, start_pos, end_pos, line_color, 
                                             width=self._get_treaty_width(treaty_type),
                                             flags_to_avoid=flags_to_avoid)

            # Draw inter-bloc treaties (treaties between different blocs)
            for treaty in all_treaties:
                a1_id = treaty.get('alliance1_id')
                a2_id = treaty.get('alliance2_id')
                
                if (a1_id in alliance_positions and a2_id in alliance_positions and 
                    a1_id != a2_id):
                    
                    # Check if they're in different blocs
                    a1_bloc = None
                    a2_bloc = None
                    for bloc_idx, bloc in enumerate(combined_blocs):
                        if a1_id in bloc:
                            a1_bloc = bloc_idx
                        if a2_id in bloc:
                            a2_bloc = bloc_idx
                    
                    if a1_bloc is not None and a2_bloc is not None and a1_bloc != a2_bloc:
                        treaty_type = self._normalize_treaty_type(treaty.get('treaty_type', ''))
                        line_color = self.TREATY_COLORS.get(treaty_type, (200, 200, 220, 180))
                        
                        start_pos = alliance_positions[a1_id]
                        end_pos = alliance_positions[a2_id]
                        
                        # Create list of all flags to avoid
                        flags_to_avoid = []
                        for other_id, pos in alliance_positions.items():
                            if other_id != a1_id and other_id != a2_id:
                                flags_to_avoid.append((pos, (flag_size, flag_size)))
                        
                        self._draw_treaty_line(draw, start_pos, end_pos, line_color,
                                             width=self._get_treaty_width(treaty_type),
                                             flags_to_avoid=flags_to_avoid)

            # Add title and legend
            title = f"PnW Treaty Universe - {len(alliance_data)} Alliances, {len(all_treaties)} Treaties"
            try:
                draw.text((total_width // 2 - 200, 30), title, fill=(255, 255, 255, 255))
            except Exception:
                pass
            
            # Add treaty type legend
            legend_x = padding
            legend_y = total_height - 80
            legend_items = [
                ('MDP/MDoAP', self.TREATY_COLORS['MDP']),
                ('ODP/ODoAP', self.TREATY_COLORS['ODP']),
                ('Protectorate/Extension', self.TREATY_COLORS['Protectorate']),
                ('PIAT/NAP', self.TREATY_COLORS['PIAT'])
            ]
            
            for i, (label, color) in enumerate(legend_items):
                x = legend_x + i * 200
                # Draw colored line
                draw.line([(x, legend_y), (x + 30, legend_y)], fill=color, width=3)
                # Draw label
                try:
                    draw.text((x + 40, legend_y - 8), label, fill=(200, 200, 200, 255))
                except Exception:
                    pass

            # Convert to Discord file
            buf = io.BytesIO()
            canvas.save(buf, format='PNG')
            buf.seek(0)
            return discord.File(buf, filename="universe_map.png")
            
        except Exception as e:
            print(f"Error generating universe image: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _get_treaty_width(self, treaty_type: str) -> int:
        """Returns the line width for a treaty type based on its significance."""
        treaty_styles = {
            'Protectorate': 4,
            'Extension': 4,
            'MDoAP': 3,
            'MDP': 3,
            'ODoAP': 2,
            'ODP': 2,
            'PIAT': 1,
            'NAP': 1,
        }
        return treaty_styles.get(treaty_type, 1)

class UniverseCog(commands.Cog):
    def __init__(self, bot: commands.Bot, query_instance):
        self.bot = bot
        self.query_instance = query_instance
        self.logger = logging.getLogger(self.__class__.__name__)
        self.httpd = None
        self.server_thread = None
        self.port = get_service_port(SERVICE_UNIVERSE)  # Use port manager
        self.public_url = None
        self.treaty_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'Data', 'Treaty')

    def cog_unload(self):
        """Clean up when the cog is unloaded."""
        if self.httpd:
            self.logger.info("Shutting down web server...")
            self.httpd.shutdown()
            self.httpd.server_close()
            self.logger.info("Web server shut down.")
        # Release the allocated port
        release_port(SERVICE_UNIVERSE)

    def get_weekly_filename(self, date: Optional[datetime] = None) -> str:
        """Generate filename for weekly treaty data based on ISO week."""
        if date is None:
            date = datetime.now()
        
        # Get ISO week number and year
        year, week, _ = date.isocalendar()
        return f"treaties_week_{year}_{week:02d}.json"

    def get_treaty_files_list(self) -> List[Dict[str, Any]]:
        """Get list of all treaty files with their metadata."""
        try:
            files = []
            if os.path.exists(self.treaty_data_dir):
                for filename in os.listdir(self.treaty_data_dir):
                    if filename.startswith('treaties_week_') and filename.endswith('.json'):
                        filepath = os.path.join(self.treaty_data_dir, filename)
                        try:
                            stat = os.stat(filepath)
                            # Parse year and week from filename
                            parts = filename.replace('treaties_week_', '').replace('.json', '').split('_')
                            if len(parts) == 2:
                                year, week = int(parts[0]), int(parts[1])
                                files.append({
                                    'filename': filename,
                                    'filepath': filepath,
                                    'year': year,
                                    'week': week,
                                    'size': stat.st_size,
                                    'modified': stat.st_mtime,
                                    'date': datetime.fromtimestamp(stat.st_mtime)
                                })
                        except Exception as e:
                            self.logger.warning(f"Error processing file {filename}: {e}")
            
            # Sort by year and week (newest first)
            files.sort(key=lambda x: (x['year'], x['week']), reverse=True)
            return files
            
        except Exception as e:
            self.logger.error(f"Error getting treaty files list: {e}")
            return []

    def load_treaties_from_file(self, filename: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load treaties from a specific weekly file or the most recent one."""
        try:
            if filename:
                filepath = os.path.join(self.treaty_data_dir, filename)
                if os.path.exists(filepath):
                    with open(filepath, "r", encoding="utf-8") as f:
                        return json.load(f)
                else:
                    self.logger.warning(f"Treaty file not found: {filepath}")
                    return []
            else:
                # Get most recent file
                files = self.get_treaty_files_list()
                if files:
                    with open(files[0]['filepath'], "r", encoding="utf-8") as f:
                        return json.load(f)
                else:
                    self.logger.warning("No treaty files found")
                    return []
                    
        except Exception as e:
            self.logger.error(f"Error loading treaties from file: {e}")
            return []

    async def save_treaties_weekly(self, treaties: List[Dict[str, Any]], date: Optional[datetime] = None) -> str:
        """Save treaties to a weekly file, returns the filename."""
        try:
            # Ensure directory exists
            os.makedirs(self.treaty_data_dir, exist_ok=True)
            
            # Generate filename for current week
            filename = self.get_weekly_filename(date)
            filepath = os.path.join(self.treaty_data_dir, filename)
            
            # Save the file
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(treaties, f, ensure_ascii=False, indent=4)
            
            self.logger.info(f"Successfully saved {len(treaties)} treaties to {filename}")
            return filename
            
        except Exception as e:
            self.logger.error(f"Error saving treaties weekly: {e}")
            raise

    async def get_treaty_timeframe_autocomplete(self, interaction: discord.Interaction, current: str) -> List[discord.app_commands.Choice[str]]:
        """Autocomplete function for timeframe selection."""
        try:
            files = self.get_treaty_files_list()
            choices = []
            
            for file_info in files[:25]:  # Discord limits to 25 choices
                # Format: "Week XX, YYYY" or "Current Week" for most recent
                week_str = f"Week {file_info['week']:02d}, {file_info['year']}"
                if len(choices) == 0:  # Most recent file
                    week_str += " (Current)"
                
                # Add date range for clarity
                date = file_info['date']
                week_start = date - timedelta(days=date.weekday())
                week_end = week_start + timedelta(days=6)
                description = f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d')}"
                
                if current.lower() in week_str.lower() or current.lower() in description.lower():
                    choices.append(
                        discord.app_commands.Choice(
                            name=f"{week_str} - {description}",
                            value=file_info['filename']
                        )
                    )
            
            return choices
            
        except Exception as e:
            self.logger.error(f"Error in treaty timeframe autocomplete: {e}")
            return []

    def should_create_new_weekly_file(self) -> bool:
        """Check if we should create a new weekly file (if current week doesn't exist or is too old)."""
        try:
            current_week_file = self.get_weekly_filename()
            files = self.get_treaty_files_list()
            
            # Check if current week file exists
            for file_info in files:
                if file_info['filename'] == current_week_file:
                    # Check if file is less than 7 days old
                    if datetime.now() - file_info['date'] < timedelta(days=7):
                        return False  # Current week file exists and is recent
                    else:
                        return True  # Current week file exists but is too old
            
            # Current week file doesn't exist
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking if new weekly file should be created: {e}")
            return True

    def start_web_server(self):
        if self.server_thread and self.server_thread.is_alive():
            self.logger.info("Web server is already running.")
            return

        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))
        web_dir = os.path.join(project_root, 'web')
        data_dir = os.path.join(project_root, 'Systems', 'Data')
        os.makedirs(web_dir, exist_ok=True)
        os.makedirs(data_dir, exist_ok=True)

        class CustomHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)

            def do_GET(self):
                if self.path.startswith('/data/'):
                    try:
                        # Serve from data_dir
                        req_path = self.path[6:] # Strip '/data/'
                        full_path = os.path.join(data_dir, req_path)
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        with open(full_path, 'rb') as f:
                            self.wfile.write(f.read())
                        return
                    except FileNotFoundError:
                        self.send_error(404, 'File Not Found')
                        return
                # Default to serving from web_dir
                super().do_GET()

            def translate_path(self, path):
                # This ensures that the default handler serves from web_dir
                return os.path.join(web_dir, path.lstrip('/'))

    async def timeframe_autocomplete(self, interaction: discord.Interaction, current: str) -> List[discord.app_commands.Choice[str]]:
        """Autocomplete function for timeframe selection."""
        return await self.get_treaty_timeframe_autocomplete(interaction, current)

    @commands.hybrid_command(name='game_treaties', aliases=['treaty_map', 'universe', 'treaty_universe'], description='Shows an interactive treaty map of the game world')
    @discord.app_commands.describe(timeframe='Select a timeframe to view historical treaty data')
    @discord.app_commands.autocomplete(timeframe=timeframe_autocomplete)
    async def game_treaties(self, ctx, timeframe: Optional[str] = None):
        """Shows an interactive treaty map of the game world with PIL image generation."""
        
        # Handle both interaction and regular message contexts
        if ctx.interaction:
            # For slash commands, defer the response
            await ctx.interaction.response.defer()
            placeholder_message = await ctx.interaction.followup.send("🌐 Building the massive treaty universe map...")
        else:
            # For regular commands, send a regular message
            placeholder_message = await ctx.send("🌐 Building the massive treaty universe map...")
        
        try:
            universe = TreatyUniverse(self.query_instance)
            
            # Determine which treaties to use based on timeframe
            if timeframe:
                # Load specific timeframe
                all_treaties = self.load_treaties_from_file(timeframe)
                if not all_treaties:
                    error_msg = f"❌ No treaty data found for timeframe: {timeframe}"
                    if ctx.interaction:
                        await ctx.interaction.followup.send(error_msg)
                    else:
                        await placeholder_message.edit(content=error_msg)
                    return
            else:
                # Check if current week's file exists and is recent enough (within 7 days)
                current_week_file = self.get_weekly_filename()
                files = self.get_treaty_files_list()
                
                # Check if current week file exists and is less than 7 days old
                current_week_data = None
                for file_info in files:
                    if file_info['filename'] == current_week_file:
                        # Check if file is less than 7 days old
                        if datetime.now() - file_info['date'] < timedelta(days=7):
                            current_week_data = self.load_treaties_from_file(current_week_file)
                        break
                
                if current_week_data:
                    # Use current week's data
                    all_treaties = current_week_data
                    self.logger.info(f"Using existing current week data: {current_week_file}")
                else:
                    # Fetch fresh data and save to current week
                    all_treaties = await universe.get_all_treaties()
                    if all_treaties:
                        try:
                            saved_filename = await self.save_treaties_weekly(all_treaties)
                            self.logger.info(f"Saved fresh data to: {saved_filename}")
                        except Exception as e:
                            self.logger.error(f"Error saving weekly data: {e}")
            
            if not all_treaties:
                error_msg = "Could not fetch any treaties. The universe is empty."
                if ctx.interaction:
                    await ctx.interaction.followup.send(error_msg)
                else:
                    await placeholder_message.edit(content=error_msg)
                return

            # Save treaties to weekly file
            try:
                filename = await self.save_treaties_weekly(all_treaties)
                self.logger.info(f"Saved treaties to weekly file: {filename}")
            except Exception as e:
                self.logger.error(f"Error saving weekly treaty file: {e}")
            
            # Build the graph for visualization first
            treaty_graph = universe.treaty_graph.build_treaty_graph(all_treaties)
            
            if not treaty_graph.nodes:
                error_msg = "No alliances found in the treaty data."
                if ctx.interaction:
                    await ctx.interaction.followup.send(error_msg)
                else:
                    await placeholder_message.edit(content=error_msg)
                return

            # Find blocs according to the new logic
            blocs = universe.treaty_graph.find_blocs(all_treaties)
            
            # Generate the massive PIL image
            universe_image = await universe.generate_universe_image(all_treaties, blocs)
            
            if universe_image:
                # Create embed with the image
                timeframe_desc = ""
                if timeframe:
                    # Parse filename to get week info
                    parts = timeframe.replace('treaties_week_', '').replace('.json', '').split('_')
                    if len(parts) == 2:
                        year, week = parts
                        timeframe_desc = f" (Week {week}, {year})"
                else:
                    current_week = self.get_weekly_filename()
                    files = self.get_treaty_files_list()
                    if files and files[0]['filename'] == current_week:
                        timeframe_desc = " (Current Week)"
                
                embed = discord.Embed(
                    title="🌐 PnW Treaty Universe Map",
                    description=f"Showing {len(treaty_graph.nodes)} alliances in {len(blocs.get('combined', []))} blocs with {len(all_treaties)} treaties{timeframe_desc}\n\n[Click HERE for Interactive Treaty Universe](https://politicsandwar.com/alliances/treatyweb/)",
                    color=0x00AEFF
                )
                embed.set_image(url=f"attachment://{universe_image.filename}")
                embed.set_footer(text="Alliance flags are grouped by blocs and connected by treaty-colored lines")

                # Check if it's an interaction or a regular message context
                if ctx.interaction:
                    # For slash commands, send the embed and file together as a followup
                    await ctx.interaction.followup.send(embed=embed, file=universe_image)
                else:
                    # For regular commands, edit the message and attach the file
                    await placeholder_message.edit(content="", embed=embed, attachments=[universe_image], view=None)
            else:
                # Fallback to HTML version if PIL image generation fails
                html_content = universe.treaty_graph.create_interactive_map(treaty_graph, all_treaties, blocs)
                
                current_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = os.path.abspath(os.path.join(current_dir, '..', '..', '..'))
                web_dir = os.path.join(project_root, 'web')
                os.makedirs(web_dir, exist_ok=True)
                
                html_path = os.path.join(web_dir, "treaty_map.html")
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                
                self.start_web_server()

                if self.public_url:
                    message = f"Here is the interactive treaty map for everyone: {self.public_url}/treaty_map.html"
                else:
                    local_ip = get_local_ip()
                    
                    localhost_url = f"http://localhost:{self.port}/treaty_map.html"
                    message = f"Here is the interactive treaty map: {localhost_url}\n"

                    if local_ip and local_ip != '127.0.0.1':
                        lan_url = f"http://{local_ip}:{self.port}/treaty_map.html"
                        message += f"If you are on the same local network, you can use this address: `{lan_url}`\n"
                    
                    message += "\nTo make this link accessible to everyone, I need to use a tunneling service like ngrok. Please ask the bot owner to install `pyngrok` by running `pip install pyngrok` in their terminal, and then configure it with an authtoken from the ngrok dashboard."
                
                if ctx.interaction:
                    await ctx.interaction.followup.send(message)
                else:
                    await placeholder_message.edit(content=message, attachments=[], view=None)

        except Exception as e:
                self.logger.error(f"/game_treaties error: {e}", exc_info=True)
                error_message = f"❌ An error occurred: {str(e)}"
                try:
                    if ctx.interaction:
                        # For slash commands, send a followup message
                        await ctx.interaction.followup.send(error_message)
                    else:
                        # For regular commands, edit the placeholder message
                        if placeholder_message:
                            await placeholder_message.edit(content=error_message, view=None, attachments=[])
                        else:
                            await ctx.send(error_message)
                except Exception as e_inner:
                    self.logger.error(f"Error sending error message: {e_inner}", exc_info=True)

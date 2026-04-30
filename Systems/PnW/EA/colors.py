from discord.ext import commands
from discord import Embed, File
from Systems.PnW.Util.query import get_color_info as api_get_color_info
import discord
from datetime import datetime
from typing import Optional
from Systems.PnW.Util.query import create_v3_query_instance, V3GraphQuery
from Systems.Functions.config import PANDW_API_KEY
import logging
from PIL import Image, ImageDraw, ImageFont
import io
import os
import random
import colorsys
from Systems.Functions.emoji import category_mentions, mention


class TempEmojiMod:
    def __init__(self, bot):
        self.bot = bot

    def mention(self, emoji_name: str) -> Optional[str]:
        """Get proper emoji mention using the Systems.Functions.emoji module."""
        return mention(emoji_name)

class Colors(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.query_instance = None

    async def sync_color_data(self):
        """Sync color data from the PnW API"""
        if not self.query_instance:
            from Systems.PnW.Util.query import create_v3_query_instance
            self.query_instance = create_v3_query_instance()
        
        # Get fresh color data from API
        color_data = await self.query_instance.get_color_info()
        
        # Check if we have all 19 colors
        expected_colors = {
            "white", "grey", "black", "gold", "pink", "brown", "mint", "green",
            "aqua", "lavender", "lime", "maroon", "olive", "yellow", "turquoise",
            "red", "purple", "orange", "blue"
        }
        
        # If we don't have all colors, try to get them individually
        if not color_data or len(color_data) < 19:
            all_color_data = []
            for color in expected_colors:
                color_info = await self.query_instance.get_color_info(color=color)
                if color_info:
                    all_color_data.extend(color_info)
            return all_color_data
        
        return color_data

    @commands.hybrid_command(name="turn_bonuses", description="Shows turn bonuses for all color blocs")
    async def turn_bonuses(self, ctx):
        """Display turn bonuses for all color blocs in a rich embed"""
        await ctx.defer()
        # Sync color data from API
        color_data = await self.sync_color_data()
        
        if not color_data:
            await ctx.send("No color information found from the API.")
            return
        
        # Map full color names to abbreviated names from emoji module
        full_to_abbr_map = {
            "beige": "be",
            "aqua": "aq", 
            "black": "bla",
            "blue": "blu",
            "brown": "br",
            "gold": "go",
            "green": "gr",
            "lavender": "la",
            "maroon": "mar",
            "mint": "mi",
            "olive": "ol",
            "lime": "li",
            "orange": "or",
            "pink": "pi",
            "purple": "pu",
            "red": "re",
            "turquoise": "tu",
            "white": "wh",
            "yellow": "ye",
            "grey": "gra",  # Map grey to green abbreviation (gr)
            "gray": "gra"   # Map gray to green abbreviation (gr)
        }
        
        # Map abbreviated names to hex colors
        abbr_to_hex_map = {
            "be": 0xDDDDDD,  # beige
            "aq": 0x00FFFF,  # aqua
            "bla": 0x000000, # black
            "blu": 0x0000FF, # blue
            "br": 0xA52A2A,  # brown
            "go": 0xFFD700,  # gold
            "gr": 0x00FF00,  # green (also used for grey/gray)
            "la": 0xE6E6FA,  # lavender
            "mar": 0x800000, # maroon
            "mi": 0x98FF98,  # mint
            "ol": 0x808000,  # olive
            "li": 0x00FF00,  # lime
            "or": 0xFFA500,  # orange
            "pi": 0xFFC0CB,  # pink
            "pu": 0x800080,  # purple
            "re": 0xFF0000,  # red
            "tu": 0x40E0D0,  # turquoise
            "wh": 0xFFFFFF,  # white
            "ye": 0xFFFF00   # yellow
        }
        
        # Find the color with the highest turn bonus (for embed color)
        max_bonus = 0
        max_bonus_abbr = None
        for color_info in color_data:
            turn_bonus = color_info.get('turn_bonus', 0)
            if turn_bonus > max_bonus:
                max_bonus = turn_bonus
                full_color_name = color_info.get('color', '').lower()
                max_bonus_abbr = full_to_abbr_map.get(full_color_name, 'wh')  # Default to white
        
        # Get embed color based on the highest bonus color
        embed_color = abbr_to_hex_map.get(max_bonus_abbr, 0xFFFFFF)
        
        # Sort color_data by turn_bonus in descending order (highest first)
        color_data.sort(key=lambda x: x.get('turn_bonus', 0), reverse=True)
        
        # Get color emojis from emoji module
        color_emojis = category_mentions("Colors")
        
        # Create embed with color matching the highest bonus
        embed = Embed(
            title="Turn Bonuses",
            description="Here are the turn bonuses for each color bloc (sorted highest to lowest):",
            color=embed_color
        )
        
        for color_info in color_data:
            full_color_name = color_info.get('color', '').lower()
            abbr_color = full_to_abbr_map.get(full_color_name, 'wh')
            
            # Get the emoji directly using the mention function
            color_emoji = mention(abbr_color)
            
            if color_emoji:
                embed.add_field(
                    name=f"{color_emoji} {color_info.get('bloc_name', 'Unknown')}",
                    value=f"Turn Bonus: ${color_info.get('turn_bonus', 0)}",
                    inline=False
                )
            else:
                embed.add_field(
                    name=f"🎨 {color_info.get('bloc_name', 'Unknown')}",
                    value=f"Turn Bonus: ${color_info.get('turn_bonus', 0)}",
                    inline=False
                )

        await ctx.send(embed=embed)

class GameInfoCog(commands.Cog):
    """Cog for displaying Politics & War game information."""
    
    def __init__(self, bot: commands.Bot, *, emoji_mod, query_instance: Optional[V3GraphQuery] = None):
        self.bot = bot
        self.api_key = PANDW_API_KEY
        self.logger = logging.getLogger(__name__)
        self.emoji_mod = emoji_mod
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.DEBUG)
        
        # Use provided query instance or create new one
        self.query_instance = query_instance or create_v3_query_instance(logger=self.logger)
    
    def _adjust_brightness(self, hex_color, factor):
        # Convert hex to RGB
        r, g, b = tuple(int(hex_color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
        # Increase brightness
        r = int(min(255, r * factor))
        g = int(min(255, g * factor))
        b = int(min(255, b * factor))
        return f"#{r:02x}{g:02x}{b:02x}"

    def _generate_radiation_pie_chart(self, radiation_data: dict, continent_names: dict) -> io.BytesIO:
        # --- 1. Data and Color Preparation --- #
        continent_base_colors = {
            'north_america': '#d62728',  # Red
            'south_america': '#2ca02c',  # Green
            'europe': '#1f77b4',  # Blue
            'africa': '#ff7f0e',  # Orange
            'asia': '#9467bd',  # Purple
            'australia': '#8c564b',  # Brown
            'antarctica': '#7f7f7f'   # Gray
        }

        continent_data = []
        
        # Correctly calculate total_radiation, excluding 'global_' and any other non-continent keys
        total_radiation = sum(v for k, v in radiation_data.items() if k in continent_names and isinstance(v, (int, float)))

        # Prepare data for each continent
        for key, name in continent_names.items():
            value = radiation_data.get(key, 0.0)
            percentage = (value / total_radiation) * 100 if total_radiation > 0 else 0
            
            # Get base color
            base_color_hex = continent_base_colors.get(key, "#808080")
            
            # Convert to RGB
            r, g, b = tuple(int(base_color_hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
            
            # Convert to HSV and create a dark base
            h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            v_dark = 0.25 
            dark_r, dark_g, dark_b = [int(c * 255) for c in colorsys.hsv_to_rgb(h, s, v_dark)]
            base_dark_color = f"#{dark_r:02x}{dark_g:02x}{dark_b:02x}"
            
            # Brightness scales with contribution. 0% is darkest, 100% contribution brightens it by 4x.
            brightness_factor = 1.0 + (percentage / 100) * 3.0
            final_color = self._adjust_brightness(base_dark_color, brightness_factor)
            
            continent_data.append({"name": name, "percentage": percentage, "color": final_color})

        # --- 2. Image and Font Setup --- #
        img_size = (1200, 900)
        img = Image.new("RGBA", img_size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 28)
        except IOError:
            font = ImageFont.load_default()

        # --- 3. Pie Chart Drawing --- #
        pie_box = [50, 50, 800, 800]
        
        if total_radiation == 0:
            # If all radiation is zero, draw equal slices with dark base colors
            num_continents = len(continent_names)
            angle_per_continent = 360 / num_continents
            start_angle = -90
            for i, data in enumerate(continent_data):
                end_angle = start_angle + angle_per_continent
                # For the last slice, extend to the end to ensure a full circle
                if i == len(continent_data) - 1:
                    end_angle = 270
                draw.pieslice(pie_box, start_angle, end_angle, fill=data["color"], outline="#FFFFFF", width=3)
                start_angle = end_angle
        else:
            # Assign a minimal angle to 0% slices to make them visible
            min_angle = 1.0
            
            zero_percent_slices = [d for d in continent_data if d['percentage'] == 0]
            non_zero_percent_slices = [d for d in continent_data if d['percentage'] > 0]
            
            angle_for_zeros = len(zero_percent_slices) * min_angle
            angle_for_non_zeros = 360.0 - angle_for_zeros
            
            total_percentage_of_non_zeros = sum(d['percentage'] for d in non_zero_percent_slices)
            
            start_angle = -90.0
            
            # Draw all slices, ensuring a full circle
            all_slices = non_zero_percent_slices + zero_percent_slices
            for i, data in enumerate(all_slices):
                slice_angle = 0
                if data['percentage'] > 0 and total_percentage_of_non_zeros > 0:
                    slice_angle = (data['percentage'] / total_percentage_of_non_zeros) * angle_for_non_zeros
                elif data['percentage'] == 0:
                    slice_angle = min_angle
                
                end_angle = start_angle + slice_angle
                
                # For the very last slice, draw to 270 to close the circle perfectly
                if i == len(all_slices) - 1:
                    end_angle = 270

                draw.pieslice(pie_box, start_angle, end_angle, fill=data["color"], outline="#FFFFFF", width=3)
                start_angle = end_angle

        # --- 4. Ordered Legend --- #
        # Sort data by percentage for the legend
        continent_data.sort(key=lambda x: x['percentage'], reverse=True)
        
        legend_x = 870
        legend_y = 100
        for data in continent_data:
            draw.rectangle([legend_x, legend_y, legend_x + 30, legend_y + 30], fill=data["color"], outline="#FFFFFF")
            draw.text((legend_x + 40, legend_y), f"{data['name']} ({data['percentage']:.1f}%)", font=font, fill="#FFFFFF")
            legend_y += 45

        # --- 5. Save Image --- #
        buffer = io.BytesIO()
        img.save(buffer, "PNG")
        buffer.seek(0)
        return buffer

    @commands.hybrid_command(name="game_info", description="Show current P&W game information including date, radiation levels, and city averages")
    async def game_info_command(self, ctx: commands.Context):
        """Display current game information in a rich embed."""
        try:
            # Fetch game info from API
            game_info = await self.query_instance.get_game_info()
            
            if not game_info:
                embed = discord.Embed(
                    title="❌ Game Information Unavailable",
                    description="Unable to retrieve current game information from the API.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return

            radiation = game_info['radiation']
            continent_names = {
                'north_america': 'North America',
                'south_america': 'South America', 
                'europe': 'Europe',
                'africa': 'Africa',
                'asia': 'Asia',
                'australia': 'Australia',
                'antarctica': 'Antarctica'
            }
            
            # Generate the pie chart
            chart_buffer = self._generate_radiation_pie_chart(radiation, continent_names)
            file = discord.File(chart_buffer, filename="radiation_chart.png")
            
            # Get World category emojis from emoji module - use direct mention() calls for efficiency
            world_emojis = {
                'na': mention('na') or '🌎',
                'sa': mention('sa') or '🌍',
                'europe': mention('europe') or '🏰',
                'africa': mention('africa') or '🦁',
                'asia': mention('asia') or '🏯',
                'australia': mention('australia') or '🦘',
                'arctic': mention('arctic') or '🐧',
                'globe': mention('globe') or '🌍',
                'radioactive': mention('radioactive') or '☢️',
                'cities': mention('cities') or '🏙️'
            }
            
            # Format the game date for readability
            try:
                game_date_obj = datetime.fromisoformat(game_info['game_date'].replace('Z', '+00:00'))
                formatted_date = game_date_obj.strftime('%B %d, %Y')
            except (ValueError, TypeError):
                formatted_date = game_info['game_date'] # Fallback if format is unexpected

            # Create rich embed
            embed = discord.Embed(
                title=f"{world_emojis['globe']} Politics & War - Current Game Status",
                description=f"**Game Date:** {formatted_date}",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            embed.set_image(url="attachment://radiation_chart.png")
            
            # Add city average field
            city_avg = game_info['city_average']
            embed.add_field(
                name=f"{world_emojis['cities']} Top 20% City Average",
                value=f"**{city_avg:.2f}** cities",
                inline=False
            )
            
            # Add radiation levels
            radiation = game_info['radiation']
            embed.add_field(
                name=f"{world_emojis['radioactive']} Global Radiation",
                value=f"**{radiation['global_']:.3f}**",
                inline=True
            )
            
            # Map continent names to emoji keys
            continent_emoji_map = {
                'north_america': 'na',
                'south_america': 'sa', 
                'europe': 'europe',
                'africa': 'africa',
                'asia': 'asia',
                'australia': 'australia',
                'antarctica': 'arctic'
            }
            
            continent_names = {
                'north_america': 'North America',
                'south_america': 'South America', 
                'europe': 'Europe',
                'africa': 'Africa',
                'asia': 'Asia',
                'australia': 'Australia',
                'antarctica': 'Antarctica'
            }
            
            # Prepare continental radiation data for sorting
            continent_data = []
            for continent_key, continent_name in continent_names.items():
                if continent_key in radiation:
                    emoji_key = continent_emoji_map.get(continent_key)
                    emoji = world_emojis.get(emoji_key, '🌍') # Fallback emoji
                    value = radiation.get(continent_key, 0.0)
                    continent_data.append({
                        "name": continent_name,
                        "emoji": emoji,
                        "value": value
                    })

            # Sort continents by radiation value, descending
            continent_data.sort(key=lambda x: x['value'], reverse=True)

            # Create radiation details from sorted data
            radiation_details = [f"{data['emoji']} {data['name']}: **{data['value']:.3f}**" for data in continent_data]
            
            if radiation_details:
                embed.add_field(
                    name=f"{world_emojis['globe']} Continental Radiation Levels",
                    value="\n".join(radiation_details),
                    inline=False
                )
            
            # Add footer with update time
            embed.set_footer(text=f"Data provided by Politics & War API • Updated hourly")
            
            await ctx.send(embed=embed, file=file)
            
        except Exception as e:
            self.logger.error(f"Error in game_info command: {e}", exc_info=True)
            embed = discord.Embed(
                title="❌ Error",
                description=f"An error occurred while retrieving game information: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

async def setup(bot):
    emoji_mod = TempEmojiMod(bot)
    await bot.add_cog(Colors(bot))
    await bot.add_cog(GameInfoCog(bot, emoji_mod=emoji_mod))

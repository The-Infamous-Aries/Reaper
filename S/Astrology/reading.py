import discord
from discord.ext import commands
from discord import app_commands
from typing import Literal
import random
import json
import os
import io
import aiohttp
from PIL import Image
from Systems.Functions import emoji as emoji_mod

# --- PATH SETUP (Using your defined structure) ---
JSON_PATH = "Systems/Astrology/Tarot/tarot-images.json"
IMAGE_DIR = "Systems/Astrology/Tarot/cards/"

# --- Import API Key from Config ---
from config import GROQ_API_KEY

# --- HELPER FUNCTION: Calculate Reading Vibe ---
def get_dominant_energy(drawn_cards):
    suits = {"wands": 0, "cups": 0, "swords": 0, "pentacles": 0, "major": 0}
    for card in drawn_cards:
        if card.get('arcana', '').lower() == "major":
            suits["major"] += 1
        else:
            suit = card.get('suit', '').lower()
            if suit in suits:
                suits[suit] += 1
                
    threshold = len(drawn_cards) // 2 + 1
    for key, count in suits.items():
        if count >= threshold:
            if key == "major": return f"{emoji_mod.mention('exchange') or '⚠️'} **Karmic Shift:** Major life changes and spiritual lessons are at play."
            if key == "wands": return f"{emoji_mod.mention('fire1') or '🔥'} **Fire Dominant:** High passion, action, and ambition drive this situation."
            if key == "cups": return f"{emoji_mod.mention('water1') or '🌊'} **Water Dominant:** Emotions, intuition, and relationships are leading your path."
            if key == "swords": return f"{emoji_mod.mention('air1') or '🌪️'} **Air Dominant:** Mental conflict, logic, and critical decisions are heavily featured."
            if key == "pentacles": return f"{emoji_mod.mention('earth1') or '🌍'} **Earth Dominant:** Focus is on material wealth, career, and physical foundations."
    return f"{emoji_mod.mention('zodiac') or '⚖️'} **Balanced Energy:** A mix of emotional, physical, and mental forces are at play."

# --- AI TAROT SUMMARY GENERATOR ---
async def generate_tarot_summary(spread_type: str, cards: list, positions: list):
    """Generates an AI-powered tarot reading summary using the Groq API."""
    card_info = []
    for i, card in enumerate(cards):
        is_reversed = random.choice([True, False])
        orientation = " (Reversed)" if is_reversed else ""
        meaning_list = card['meanings']['shadow'] if is_reversed else card['meanings']['light']
        fortune = random.choice(card['fortune_telling'])
        
        card_details = {
            "name": card['name'] + orientation,
            "position": positions[i][0],
            "meaning": ', '.join(meaning_list[:3]),
            "fortune": fortune,
            "arcana": card.get('arcana', 'Minor')
        }
        card_info.append(card_details)
    
    if spread_type == "1 Card":
        prompt = f"""
        You are a wise and intuitive tarot reader. The universe has drawn one card for a seeker.
        
        Card: {card_info[0]['name']}
        Position: {card_info[0]['position']}
        Core Meaning: {card_info[0]['meaning']}
        Fortune: {card_info[0]['fortune']}
        
        Provide a profound and personalized message from the universe to the seeker. 
        The message should be encouraging, insightful, and directly related to the card's energy.
        Keep the response under 150 words.
        """
    elif spread_type == "3 Card (Past/Present/Future)":
        prompt = f"""
        You are an experienced tarot reader interpreting a three-card spread for a seeker.
        
        Cards:
        1. Past: {card_info[0]['name']} - {card_info[0]['meaning']}
        2. Present: {card_info[1]['name']} - {card_info[1]['meaning']}
        3. Future: {card_info[2]['name']} - {card_info[2]['meaning']}
        
        First, explain what each card in its position (Past, Present, Future) means for the seeker's situation.
        Then, provide a combined interpretation of how these three cards work together to tell a cohesive story.
        The reading should be insightful, clear, and offer guidance. Keep the total response under 250 words.
        """
    elif spread_type == "5 Card (Traditional)":
        prompt = f"""
        You are a master tarot reader providing a detailed five-card spread reading for a seeker.
        
        Cards:
        1. Theme: {card_info[0]['name']} - {card_info[0]['meaning']}
        2. Obstacle: {card_info[1]['name']} - {card_info[1]['meaning']}
        3. Advice: {card_info[2]['name']} - {card_info[2]['meaning']}
        4. Hidden Influence: {card_info[3]['name']} - {card_info[3]['meaning']}
        5. Outcome: {card_info[4]['name']} - {card_info[4]['meaning']}
        
        Provide a comprehensive summary that covers:
        - The core theme of the inquiry.
        - The main obstacle or challenge.
        - The advice or guidance from the universe.
        - The hidden influence affecting the situation.
        - The likely outcome if the seeker follows the guidance.
        
        Weave these elements into a cohesive and insightful narrative. Keep the response under 300 words.
        """
    
    try:
        if not GROQ_API_KEY:
            print("GROQ_API_KEY missing; skipping AI summary generation.")
            return "Unable to generate AI-powered summary at this time. Please try again later."
            
        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "llama-3.1-8b-instant",
                "messages": [
                    {"role": "system", "content": "You are a wise and intuitive tarot reader. Provide profound, insightful, and personalized messages from the universe based on the cards drawn. Keep responses concise and directly related to the card energies."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 300,
                "top_p": 0.9,
            }
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    try:
                        summary = data["choices"][0]["message"]["content"].strip()
                        return summary
                    except Exception:
                        return "Unable to generate AI-powered summary at this time. Please try again later."
                else:
                    print(f"Groq API error: {resp.status}")
                    return "Unable to generate AI-powered summary at this time. Please try again later."
    except Exception as e:
        print(f"Error generating AI summary: {e}")
        return "Unable to generate AI-powered summary at this time. Please try again later."

# --- PAGINATION VIEW ---
class TarotPaginationView(discord.ui.View):
    def __init__(self, reading_data: dict, stitched_image: discord.File = None):
        super().__init__(timeout=180)  # 3 minute timeout
        self.reading_data = reading_data
        self.stitched_image = stitched_image
        self.current_page = 0  # 0 = cards, 1 = summary
        
    def build_embed(self):
        if self.current_page == 0:
            return self.build_cards_embed()
        else:
            return self.build_summary_embed()
    
    def build_cards_embed(self):
        """Build embed showing all card details"""
        data = self.reading_data
        embed = discord.Embed(
            title=f"{emoji_mod.mention('tarot') or '🔮'} {data['spread']} Reading",
            description="*Concentrate on your path. The cards have spoken...*",
            color=discord.Color.dark_purple()
        )
        
        if data.get('dominant_energy'):
            embed.add_field(name="Reading Atmosphere", value=data['dominant_energy'], inline=False)
        
        for card_data in data['cards_info']:
            embed.add_field(
                name=f"Position {card_data['position_num']}: {card_data['position_name']}",
                value=card_data['description'],
                inline=False
            )
        
        embed.set_footer(text="Use the buttons below to switch between Cards and AI Summary.")
        return embed
    
    def build_summary_embed(self):
        """Build embed showing only the AI summary"""
        data = self.reading_data
        embed = discord.Embed(
            title=f"{emoji_mod.mention('tarot') or '🔮'} {data['spread']} - AI Summary",
            description="*Wisdom from the universe...*",
            color=discord.Color.gold()
        )
        
        summary = data.get('ai_summary', 'No summary available.')
        # Split summary if it's too long for a single field (1024 char limit)
        if len(summary) <= 1024:
            embed.add_field(name="✨ Summary ✨", value=summary, inline=False)
        else:
            # Split into chunks of 1024 characters
            chunks = []
            current_chunk = ""
            for line in summary.split('\n'):
                if len(current_chunk) + len(line) + 1 > 1024:
                    chunks.append(current_chunk)
                    current_chunk = line
                else:
                    if current_chunk:
                        current_chunk += "\n" + line
                    else:
                        current_chunk = line
            if current_chunk:
                chunks.append(current_chunk)
            
            for i, chunk in enumerate(chunks):
                field_name = "✨ Summary ✨" if i == 0 else f"Summary (cont.)"
                embed.add_field(name=field_name, value=chunk, inline=False)
        
        embed.set_footer(text="Use the buttons below to switch back to Cards view.")
        return embed
    
    @discord.ui.button(label='Cards', style=discord.ButtonStyle.primary, emoji='🃏')
    async def show_cards(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 0
        embed = self.build_embed()
        if self.stitched_image:
            embed.set_image(url="attachment://spread.png")
        else:
            embed.set_image(url=None)
        await interaction.response.edit_message(embed=embed, attachments=[self.stitched_image] if self.stitched_image else [], view=self)
    
    @discord.ui.button(label='Summary', style=discord.ButtonStyle.success, emoji='✨')
    async def show_summary(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 1
        embed = self.build_summary_embed()
        # Remove image for summary view to keep it clean
        embed.set_image(url=None)
        await interaction.response.edit_message(embed=embed, attachments=[], view=self)

# --- THE COG CLASS ---
class Tarot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="tarot", description="Perform a professional, fully enriched tarot reading")
    @app_commands.describe(spread="Choose the layout of your reading")
    async def tarot(self, ctx: commands.Context, spread: Literal["1 Card", "3 Card (Past/Present/Future)", "5 Card (Traditional)"] = "1 Card"):
        
        # Defer the response so Discord doesn't timeout while your phone stitches the images
        await ctx.defer()
        
        # 1. Load data safely
        try:
            with open(JSON_PATH, 'r') as f:
                data = json.load(f)
                deck = data['cards']
        except FileNotFoundError:
            await ctx.send(f"❌ **Error:** Could not find the JSON file at `{JSON_PATH}`. Please check your folder structure.")
            return

        # 2. Spread configurations & Storytelling transitions
        spread_config = {
            "1 Card": [("The Message", "The universe tells you...")],
            "3 Card (Past/Present/Future)": [
                ("Past", "The foundation of this situation is..."), 
                ("Present", "Where you currently stand..."), 
                ("Future", "The path ahead reveals...")
            ],
            "5 Card (Traditional)": [
                ("Theme", "The core energy of your inquiry..."), 
                ("Obstacle", "What blocks or challenges you..."), 
                ("Advice", "The universe suggests you..."), 
                ("Hidden Influence", "Underlying forces at play..."), 
                ("Outcome", "If you stay on this path, the destination is...")
            ]
        }
        
        positions = spread_config[spread]
        num_cards = len(positions)
        
        # 3. Pull unique cards
        drawn_cards = random.sample(deck, num_cards)
        
        # 4. Prepare card info for pagination
        cards_info = []
        images_to_stitch = []
        
        for i, card in enumerate(drawn_cards):
            pos_name, transition = positions[i]
            
            is_reversed = random.choice([True, False])
            orient_str = " (Reversed)" if is_reversed else ""
            
            meaning_list = card['meanings']['shadow'] if is_reversed else card['meanings']['light']
            fortune = random.choice(card['fortune_telling'])
            
            is_major = card.get('arcana', '').lower() == "major"
            card_title = f"✨ **{card['name']}{orient_str}** ✨" if is_major else f"**{card['name']}{orient_str}**"
            
            description = f"*{transition}*\n{card_title}\n**Meaning:** {', '.join(meaning_list[:3])}\n**Fortune:** {fortune}"
            
            cards_info.append({
                "position_num": i + 1,
                "position_name": pos_name,
                "description": description
            })
            
            # Load and prep image for stitching
            image_path = os.path.join(IMAGE_DIR, card['img'])
            try:
                with Image.open(image_path) as img:
                    img = img.convert("RGBA")
                    if is_reversed:
                        img = img.rotate(180, expand=True)
                    img.thumbnail((200, 342))
                    images_to_stitch.append(img)
            except Exception as e:
                print(f"Error loading image {image_path}: {e}")
        
        # 5. Calculate dominant energy
        dominant_energy = None
        if num_cards > 1:
            dominant_energy = get_dominant_energy(drawn_cards)
        
        # 6. Generate AI-powered summary
        ai_summary = await generate_tarot_summary(spread, drawn_cards, positions)
        
        # 7. Stitch images
        stitched_file = None
        if images_to_stitch:
            padding = 10
            total_width = sum(img.width for img in images_to_stitch) + (padding * (num_cards - 1))
            max_height = max(img.height for img in images_to_stitch)
            
            stitched_image = Image.new('RGBA', (total_width, max_height), (43, 45, 49, 255))
            x_offset = 0
            for img in images_to_stitch:
                stitched_image.paste(img, (x_offset, 0))
                x_offset += img.width + padding
                
            buffer = io.BytesIO()
            stitched_image.save(buffer, format="PNG")
            buffer.seek(0)
            stitched_file = discord.File(buffer, filename="spread.png")
        
        # 8. Prepare reading data for pagination
        reading_data = {
            'spread': spread,
            'cards_info': cards_info,
            'dominant_energy': dominant_energy,
            'ai_summary': ai_summary
        }
        
        # 9. Create pagination view
        view = TarotPaginationView(reading_data, stitched_file)
        initial_embed = view.build_cards_embed()
        
        if stitched_file:
            await ctx.send(file=stitched_file, embed=initial_embed, view=view)
        else:
            await ctx.send(embed=initial_embed, view=view)

async def setup(bot):
    await bot.add_cog(Tarot(bot))
import discord
from discord.ext import commands
import aiohttp
import random
import logging
import io
from Systems.Functions.config import GROQ_API_KEY, GIPHY_KEY, PIXABAY_KEY
from Systems.Functions import emoji as emoji_mod

THEME_CHOICES = [
    discord.app_commands.Choice(name="Mild", value="Mild"),
    discord.app_commands.Choice(name="Simple", value="Simple"),
    discord.app_commands.Choice(name="Standard", value="Standard"),
    discord.app_commands.Choice(name="Spicy", value="Spicy"),
    discord.app_commands.Choice(name="Wild", value="Wild"),
    discord.app_commands.Choice(name="NSFW", value="NSFW"),
    discord.app_commands.Choice(name="Explicit", value="Explicit"),
]

THEME_PROMPTS = {
    "Mild": {
        "roast": "Use gentle, playful teasing. Keep it light-hearted and friendly. Avoid any harsh language or personal attacks. Focus on harmless quirks.",
        "compliment": "Use warm, gentle, and sincere praise. Be kind and uplifting with simple, heartfelt language."
    },
    "Simple": {
        "roast": "Use basic, straightforward humor. Keep language simple and easy to understand. Light teasing without complexity.",
        "compliment": "Use clear, direct praise with simple language. Be genuinely nice and easy to understand."
    },
    "Standard": {
        "roast": "Use moderate humor with some edge. Include clever observations and witty remarks. Can be slightly sarcastic but stay playful.",
        "compliment": "Use creative and thoughtful praise. Include some flair and personality in the compliments."
    },
    "Spicy": {
        "roast": "Use sharper humor with more bite. Include clever insults and stronger language. Be bold and confident in the roasting.",
        "compliment": "Use passionate and enthusiastic praise. Be more expressive and vivid with compliments."
    },
    "Wild": {
        "roast": "Use intense, over-the-top humor. Go big with exaggerated insults and wild comparisons. Be dramatic and theatrical.",
        "compliment": "Use extravagant and over-the-top praise. Be dramatic and enthusiastic with grand comparisons."
    },
    "NSFW": {
        "roast": "Use sexual vulgarity and explicit adult content. Include graphic sexual references, innuendo, and erotic metaphors. Be sexually suggestive and use bedroom-related insults. Focus on sexual performance, body parts, and intimate activities.",
        "compliment": "Use sexual vulgarity and explicit adult praise. Include graphic sexual references and erotic metaphors. Be sexually suggestive with bedroom-related compliments. Focus on sexual appeal, body parts, and intimate desirability."
    },
    "Explicit": {
        "roast": "Use extreme profanity and harsh cursing. Include frequent f-bombs, shit, damn, and other explicit language. Be brutally direct with aggressive insults. Focus on general incompetence, stupidity, and worthlessness without sexual references.",
        "compliment": "Use extreme profanity and intense language. Include frequent f-bombs and explicit expressions. Be brutally direct with passionate praise. Focus on general awesomeness, badassery, and excellence without sexual references."
    }
}

THEME_EMOJIS = {
    "Mild": "mild",
    "Simple": "med",  # Using med as closest to Simple
    "Standard": "straight",  # Using med as closest to Standard
    "Spicy": "hot",
    "Wild": "wild",
    "NSFW": "nsfw",
    "Explicit": "explicit"
}

logger = logging.getLogger(__name__)

class GoodEvilSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _ensure_complete_message(self, text: str, max_length: int = 1900) -> str:
        return text
    
    def _chunk_text(self, text: str, max_length: int = 1900):
        parts = []
        s = text
        while len(s) > max_length:
            cut = s.rfind("\n", 0, max_length)
            if cut == -1:
                cut = max_length
            parts.append(s[:cut])
            s = s[cut:].lstrip("\n")
        if s:
            parts.append(s)
        return parts
    
    async def _send_with_overflow(self, ctx, text: str, max_length: int = 1900):
        send_method = ctx.interaction.followup.send if ctx.interaction else ctx.send
        chunks = self._chunk_text(text, max_length=max_length)
        first_message = None
        for i, chunk in enumerate(chunks):
            if i == 0:
                m = await send_method(chunk)
            else:
                m = await ctx.channel.send(chunk)
            
            if i == 0:
                first_message = m
        return first_message
    
    async def _get_user_bio(self, user: discord.Member) -> str:
        bio = None
        try:
            for obj in [user, getattr(user, 'user', None), getattr(user, '_user', None)]:
                if obj:
                    for attr in ('bio', 'about_me', 'about', 'description'):
                        val = getattr(obj, attr, None)
                        if isinstance(val, str) and val.strip():
                            bio = val.strip()
                            break
                if bio:
                    break
            if not bio:
                try:
                    fetched = await self.bot.fetch_user(user.id)
                    for attr in ('bio', 'about_me', 'about', 'description'):
                        val = getattr(fetched, attr, None)
                        if isinstance(val, str) and val.strip():
                            bio = val.strip()
                            break
                except Exception:
                    pass
        except Exception:
            bio = None
        return bio or ""

    def _get_theme_emoji(self, theme: str) -> str:
        emoji_name = THEME_EMOJIS.get(theme, "med")
        emoji_id = emoji_mod.EMOJI_IDS.get(emoji_name)
        if emoji_id:
            return f"<:{emoji_name}:{emoji_id}>"
        return "✨"

    async def _fetch_image_as_file(self, url: str, filename: str) -> discord.File | None:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        image_bytes = await response.read()
                        return discord.File(io.BytesIO(image_bytes), filename=filename)
                    else:
                        logger.error(f"Failed to fetch image from {url}, status: {response.status}")
                        return None
        except aiohttp.ClientError as e:
            logger.error(f"Aiohttp client error fetching image from {url}: {e}")
            return None

    @commands.hybrid_command(name='roast', description='Get roasted with different intensity levels! (Use at your own risk)')
    @discord.app_commands.describe(
        target="The user to roast (optional - defaults to yourself)",
        theme="Choose the intensity level for the roast"
    )
    @discord.app_commands.choices(theme=THEME_CHOICES)
    async def roast(self, ctx: commands.Context, target: discord.Member = None, theme: str = "Standard"):
        """Get roasted by the bot with different intensity levels"""
        
        try:
            # Defer the interaction to prevent timeout
            await ctx.defer()
            
            # Determine target
            if target is None:
                target = ctx.author
                
            target_name = target.display_name
            target_mention = target.mention
            
            # Get user bio for personalization
            user_bio = await self._get_user_bio(target)
            
            # Helper: Generate roast via GROQ Chat Completions
            async def generate_groq_roast(theme: str, subject_name: str, bio: str):
                api_key = GROQ_API_KEY
                if not api_key:
                    print("GROQ_API_KEY missing; skipping Groq roast generation.")
                    return None
                    
                theme_instructions = THEME_PROMPTS.get(theme, {}).get("roast", "Use moderate humor with some edge.")
                
                system_prompt = (
                    f"You are a roast bot using {theme} intensity level. "
                    "Output a creative roast matching the specified intensity. "
                    f"Instructions: {theme_instructions} "
                    "You MUST combine the intensity level with the User's personality or bio. "
                    "Twist their bio traits using appropriate intensity metaphors. "
                    "Be creative, thematic, and matching the intensity level requested."
                )
                
                user_prompt = (
                    f"Subject: {subject_name}\n"
                    f"Bio/Info: {bio}\n"
                    f"Write a {theme} intensity roast about the subject. "
                    "Address them by name. Output exactly 2-3 sentences. "
                    "Keep it concise (under 500 characters). Return only the roast text."
                )
                
                try:
                    timeout = aiohttp.ClientTimeout(total=45)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        url = "https://api.groq.com/openai/v1/chat/completions"
                        headers = {
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        }
                        payload = {
                            "model": "llama-3.1-8b-instant",
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            "temperature": 0.9,
                            "max_tokens": 150,
                            "top_p": 0.9,
                        }
                        async with session.post(url, headers=headers, json=payload) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                try:
                                    text = data["choices"][0]["message"]["content"].strip()
                                    return {"roast": text, "source": "Groq"}
                                except Exception:
                                    return None
                            else:
                                print(f"Groq roast request failed: HTTP {resp.status}")
                except Exception as e:
                    print(f"Groq roast request error: {e}")
                return None

            fallback_roasts = {
                "Mild": f"{target_name}, you're like a cozy blanket - maybe too comfortable sometimes!",
                "Simple": f"{target_name}, you're about as exciting as plain toast.",
                "Standard": f"{target_name}, you're the human equivalent of a loading screen.",
                "Spicy": f"{target_name}, you're like expired milk - you leave a bad taste.",
                "Wild": f"{target_name}, you're a whole circus act, and not the main attraction!",
                "NSFW": f"{target_name}, you're like a limp noodle - completely useless in the bedroom and disappointing in every way.",
                "Explicit": f"{target_name}, you're a fucking waste of space and everyone knows you're completely full of shit."
            }
            
            # Try the API
            roast_data = await generate_groq_roast(theme, target_name, user_bio)
            
            if not roast_data:
                roast_data = {
                    'roast': fallback_roasts.get(theme, random.choice(list(fallback_roasts.values()))),
                    'source': 'Fallback'
                }
            
            styled_text = roast_data['roast']
            
            # Create the roast message text
            theme_emoji = self._get_theme_emoji(theme)
            
            roast_message = f"**{target_mention}**\n\n{styled_text}\n\n"
            roast_message += f"*{theme_emoji} {theme} Roast*\n"
            roast_message += f"_Requested by {ctx.author.display_name}_"
            
            message = await self._send_with_overflow(ctx, roast_message)
            
        except Exception as e:
            await ctx.send(f"❌ Roast system error: {e}", ephemeral=True)

    @commands.hybrid_command(name='compliment', description='Get compliments with different intensity levels!')
    @discord.app_commands.describe(
        target="The user to compliment (optional - defaults to yourself)",
        theme="Choose the intensity level for the compliment"
    )
    @discord.app_commands.choices(theme=THEME_CHOICES)
    async def compliment(self, ctx: commands.Context, target: discord.Member = None, theme: str = "Standard"):
        """Get a tailored compliment with different intensity levels"""
        
        try:
            # Defer the interaction to prevent timeout
            await ctx.defer()
            
            # Determine target
            if target is None:
                target = ctx.author
                
            target_name = target.display_name
            target_mention = target.mention
            
            # Get user bio for personalization
            user_bio = await self._get_user_bio(target)
            
            # Helper: Generate compliment via GROQ Chat Completions
            async def generate_groq_compliment(theme: str, subject_name: str, bio: str):
                api_key = GROQ_API_KEY
                if not api_key:
                    print("GROQ_API_KEY missing; skipping Groq compliment generation.")
                    return None
                    
                theme_instructions = THEME_PROMPTS.get(theme, {}).get("compliment", "Use creative and thoughtful praise.")
                
                system_prompt = (
                    f"You are a compliment bot using {theme} intensity level. "
                    "Output a complete, detailed, and uplifting compliment matching the specified intensity. "
                    f"Instructions: {theme_instructions} "
                    "You MUST combine the intensity level with the User's personality or bio. "
                    "Highlight their positive traits using appropriate intensity metaphors. "
                    "Be positive, thematic, and matching the intensity level requested."
                )
                
                user_prompt = (
                    f"Subject: {subject_name}\n"
                    f"Bio/Info: {bio}\n"
                    f"Write a {theme} intensity compliment about the subject. "
                    "Address them by name. Output exactly 2-3 sentences. "
                    "Keep it concise (under 500 characters). Return only the compliment text."
                )
                
                try:
                    timeout = aiohttp.ClientTimeout(total=45)
                    async with aiohttp.ClientSession(timeout=timeout) as session:
                        url = "https://api.groq.com/openai/v1/chat/completions"
                        headers = {
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        }
                        payload = {
                            "model": "llama-3.1-8b-instant",
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            "temperature": 0.9,
                            "max_tokens": 150,
                            "top_p": 0.9,
                        }
                        async with session.post(url, headers=headers, json=payload) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                try:
                                    text = data["choices"][0]["message"]["content"].strip()
                                    return {"compliment": text, "source": "Groq"}
                                except Exception:
                                    return None
                            else:
                                print(f"Groq compliment request failed: HTTP {resp.status}")
                except Exception as e:
                    print(f"Groq compliment request error: {e}")
                return None

            fallback_compliments = {
                "Mild": f"{target_name}, you have a wonderful presence that makes everyone comfortable.",
                "Simple": f"{target_name}, you're genuinely nice and people appreciate that about you.",
                "Standard": f"{target_name}, your personality brightens up any room you enter.",
                "Spicy": f"{target_name}, you've got that irresistible spark that draws people to you.",
                "Wild": f"{target_name}, you're an absolute legend and your energy is contagious!",
                "NSFW": f"{target_name}, you've got that irresistible sexual magnetism that makes everyone fantasize about you.",
                "Explicit": f"{target_name}, you're fucking incredible and everyone knows you're the shit!"
            }

            # Try the API
            compliment_data = await generate_groq_compliment(theme, target_name, user_bio)
            
            if not compliment_data:
                compliment_data = {
                    'compliment': fallback_compliments.get(theme, random.choice(list(fallback_compliments.values()))),
                    'source': 'Fallback'
                }
                
            styled_text = compliment_data['compliment']
            
            # Create the message text
            theme_emoji = self._get_theme_emoji(theme)
            
            comp_message = f"**{target_mention}**\n\n{styled_text}\n\n"
            comp_message += f"*{theme_emoji} {theme} Compliment*\n"
            comp_message += f"_Requested by {ctx.author.display_name}_"
            
            message = await self._send_with_overflow(ctx, comp_message)
            
        except Exception as e:
            await ctx.send(f"❌ Compliment system error: {e}", ephemeral=True)

    @commands.hybrid_command(name="crow", description="Fetch a random crow photo or GIF")
    @discord.app_commands.describe(type="Choose JPG for a photo or GIF for an animation")
    @discord.app_commands.choices(type=[
        discord.app_commands.Choice(name="JPG", value="jpg"),
        discord.app_commands.Choice(name="GIF", value="gif")
    ])
    async def crow(self, ctx: commands.Context, type: str):
        await ctx.defer()
        send_method = ctx.interaction.followup.send if ctx.interaction else ctx.send

        async def get_pixabay_crow():
            if not PIXABAY_KEY:
                logger.warning("PIXABAY_KEY not set.")
                return None
            url = f"https://pixabay.com/api/?key={PIXABAY_KEY}&q=crow&image_type=photo&per_page=200&category=animals"
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get('hits'):
                                return random.choice(data['hits'])['webformatURL']
                            else:
                                logger.info(f"Pixabay API returned no hits for query: crow")
                                return None
                        else:
                            logger.error(f"Pixabay API request failed with status {response.status}: {await response.text()}")
                            return None
            except aiohttp.ClientError as e:
                logger.error(f"Aiohttp client error calling Pixabay API: {e}")
                return None
            return None

        async def get_giphy_crow():
            if not GIPHY_KEY:
                logger.warning("GIPHY_KEY not set.")
                return None

            search_queries = ["crow bird", "raven bird", "black bird"]
            
            for query in search_queries:
                url = f"https://api.giphy.com/v1/gifs/search?api_key={GIPHY_KEY}&q={query}&limit=50&rating=g"
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url) as response:
                            if response.status == 200:
                                data = await response.json()
                                if data.get('data'):
                                    gif = random.choice(data['data'])
                                    logger.info(f"Found Giphy GIF with query: '{query}'")
                                    return gif['images']['original']['url']
                                else:
                                    logger.info(f"Giphy API returned no data for query: {query}")
                            else:
                                logger.error(f"Giphy API request failed with status {response.status} for query '{query}': {await response.text()}")
                except aiohttp.ClientError as e:
                    logger.error(f"Aiohttp client error calling Giphy API for query '{query}': {e}")
            
            return None

        try:
            link = None
            if type == "jpg":
                link = await get_pixabay_crow()
            else:
                link = await get_giphy_crow()

            if link:
                file_extension = link.split('.')[-1].split('?')[0]
                filename = f"crow.{file_extension}"
                image_file = await self._fetch_image_as_file(link, filename)

                if image_file:
                    crow_emojis = emoji_mod.category_mentions("Crows")
                    random_crow_emoji = random.choice(crow_emojis) if crow_emojis else ""
                    message_text = f"# {random_crow_emoji}\n**Caw Caw!** Your crow {'picture' if type == 'jpg' else 'gif'} arrives."
                    await send_method(content=message_text, file=image_file)
                else:
                    await send_method("Sorry, I couldn't download the crow image. Please try again.")
            else:
                await send_method(f"The crows are being shy! I couldn't find a crow picture or gif. Please try again!")

        except Exception as e:
            logger.error(f"An unexpected error occurred in the crow command: {e}", exc_info=True)
            await send_method("Something went wrong while fetching your crow. The error has been logged.")

async def setup(bot):
    await bot.add_cog(GoodEvilSystem(bot))
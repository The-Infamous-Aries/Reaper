import discord
from discord.ext import commands
import aiohttp
import random
from config import GROQ_API_KEY
from Systems.Functions import emoji as emoji_mod

ELEMENT_CHOICES = [
    discord.app_commands.Choice(name="Air", value="Air"),
    discord.app_commands.Choice(name="Basic", value="Basic"),
    discord.app_commands.Choice(name="Electric", value="Electric"),
    discord.app_commands.Choice(name="Fire", value="Fire"),
    discord.app_commands.Choice(name="Holy", value="Holy"),
    discord.app_commands.Choice(name="Ice", value="Ice"),
    discord.app_commands.Choice(name="Magic", value="Magic"),
    discord.app_commands.Choice(name="Necro", value="Necro"),
    discord.app_commands.Choice(name="Plant", value="Plant"),
    discord.app_commands.Choice(name="Rock", value="Rock"),
    discord.app_commands.Choice(name="Water", value="Water"),
    discord.app_commands.Choice(name="Psychic", value="Psychic"),
    discord.app_commands.Choice(name="Fighting", value="Fighting"),
]

ELEMENT_PROMPTS = {
    "Air": "Use wind, storm, sky, and breath metaphors. Be breezy, volatile, and intangible.",
    "Basic": "Use simple, fundamental, plain, and normal metaphors. Be straightforward and unpretentious.",
    "Electric": "Use lightning, shock, voltage, circuit, and energy metaphors. Be flashy, shocking, and energetic.",
    "Fire": "Use heat, flame, burn, ash, and explosion metaphors. Be passionate, destructive, and warm.",
    "Holy": "Use light, divine, sacred, purity, and blessing metaphors. Be righteous, glowing, and sanctified.",
    "Ice": "Use cold, freeze, chill, frost, and shatter metaphors. Be cool, preserving, and sharp.",
    "Magic": "Use arcane, spell, rune, mystery, and mana metaphors. Be mystical, enchanting, and strange.",
    "Necro": "Use death, bone, decay, shadow, and grave metaphors. Be dark, morbid, and inevitable.",
    "Plant": "Use nature, growth, root, vine, and bloom metaphors. Be organic, flourishing, and grounded.",
    "Rock": "Use stone, mountain, earth, solid, and weight metaphors. Be heavy, unmovable, and hard.",
    "Water": "Use ocean, river, flow, tide, and depth metaphors. Be fluid, adaptable, and deep.",
    "Psychic": "Use mind, thought, brain, telepathy, and future metaphors. Be mental, knowing, and trippy.",
    "Fighting": "Use combat, muscle, punch, kick, and strength metaphors. Be physical, aggressive, and disciplined.",
}

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
        chunks = self._chunk_text(text, max_length=max_length)
        first_message = None
        for i, chunk in enumerate(chunks):
            m = await ctx.send(chunk)
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

    def _get_element_emoji(self, element: str) -> str:
        emoji_id = emoji_mod.EMOJI_IDS.get(element)
        if emoji_id:
            return f"<:{element}:{emoji_id}>"
        return "✨"

    @commands.hybrid_command(name='roast', description='Get an elementally roasted! (Use at your own risk)')
    @discord.app_commands.describe(
        target="The user to roast (optional - defaults to yourself)",
        element="Choose an element for the roast style"
    )
    @discord.app_commands.choices(element=ELEMENT_CHOICES)
    async def roast(self, ctx: commands.Context, target: discord.Member = None, element: str = "Fire"):
        """Get roasted by the bot with elemental fury"""
        
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
            async def generate_groq_roast(element: str, subject_name: str, bio: str):
                api_key = GROQ_API_KEY
                if not api_key:
                    print("GROQ_API_KEY missing; skipping Groq roast generation.")
                    return None
                    
                element_instructions = ELEMENT_PROMPTS.get(element, "Use fiery and aggressive metaphors.")
                
                system_prompt = (
                    f"You are a roast bot channeling the element of {element}. "
                    "Output a creative, savage roast. "
                    f"Instructions: {element_instructions} "
                    "You MUST combine the Elemental theme with the User's personality or bio. "
                    "Twist their bio traits using elemental metaphors. "
                    "Be creative, thematic, and biting."
                )
                
                user_prompt = (
                    f"Subject: {subject_name}\n"
                    f"Bio/Info: {bio}\n"
                    "Write a roast about the subject using the specified elemental theme. "
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

            fallback_roasts = [
                f"{target_name}, you're like a damp match - absolutely no spark.",
                f"{target_name}, your elemental affinity must be 'Disappointment'.",
                f"{target_name}, even the wind avoids you.",
            ]
            
            # Try the API
            roast_data = await generate_groq_roast(element, target_name, user_bio)
            
            if not roast_data:
                roast_data = {
                    'roast': random.choice(fallback_roasts),
                    'source': 'Fallback'
                }
            
            styled_text = roast_data['roast']
            
            # Create the roast message text
            element_emoji = self._get_element_emoji(element)
            
            roast_message = f"**{target_mention}**\n\n{styled_text}\n\n"
            roast_message += f"*{element_emoji} {element} Roast*\n"
            roast_message += f"_Requested by {ctx.author.display_name}_"
            
            message = await self._send_with_overflow(ctx, roast_message)
            
        except Exception as e:
            await ctx.send(f"❌ Roast system error: {e}", ephemeral=True)

    @commands.hybrid_command(name='compliment', description='Get an elementally empowered compliment!')
    @discord.app_commands.describe(
        target="The user to compliment (optional - defaults to yourself)",
        element="Choose an element for the compliment style"
    )
    @discord.app_commands.choices(element=ELEMENT_CHOICES)
    async def compliment(self, ctx: commands.Context, target: discord.Member = None, element: str = "Holy"):
        """Get a tailored elemental compliment"""
        
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
            async def generate_groq_compliment(element: str, subject_name: str, bio: str):
                api_key = GROQ_API_KEY
                if not api_key:
                    print("GROQ_API_KEY missing; skipping Groq compliment generation.")
                    return None
                    
                element_instructions = ELEMENT_PROMPTS.get(element, "Use bright and uplifting metaphors.")
                
                system_prompt = (
                    f"You are a compliment bot channeling the element of {element}. "
                    "Output a complete, detailed, and uplifting compliment. "
                    f"Instructions: {element_instructions} "
                    "You MUST combine the Elemental theme with the User's personality or bio. "
                    "Highlight their positive traits using elemental metaphors. "
                    "Be positive, thematic, and encouraging."
                )
                
                user_prompt = (
                    f"Subject: {subject_name}\n"
                    f"Bio/Info: {bio}\n"
                    "Write a compliment about the subject using the specified elemental theme. "
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

            fallback_compliments = [
                f"{target_name}, you shine brighter than the sun!",
                f"{target_name}, your spirit is as refreshing as a cool breeze.",
                f"{target_name}, you are as solid and reliable as the earth itself.",
            ]

            # Try the API
            compliment_data = await generate_groq_compliment(element, target_name, user_bio)
            
            if not compliment_data:
                compliment_data = {
                    'compliment': random.choice(fallback_compliments),
                    'source': 'Fallback'
                }
                
            styled_text = compliment_data['compliment']
            
            # Create the message text
            element_emoji = self._get_element_emoji(element)
            
            comp_message = f"**{target_mention}**\n\n{styled_text}\n\n"
            comp_message += f"*{element_emoji} {element} Compliment*\n"
            comp_message += f"_Requested by {ctx.author.display_name}_"
            
            message = await self._send_with_overflow(ctx, comp_message)
            
        except Exception as e:
            await ctx.send(f"❌ Compliment system error: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(GoodEvilSystem(bot))

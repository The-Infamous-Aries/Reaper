import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import logging

# Set up logging
logger = logging.getLogger(__name__)

# Comprehensive Mapping of Emoji Flags to Language Codes (ISO 639-1)
# Each emoji must be unique to avoid overwriting dictionary keys.
FLAG_MAPPING = {
    "🇺🇸": "en", # English
    "🇪🇸": "es", # Spanish
    "🇫🇷": "fr", # French
    "🇩🇪": "de", # German
    "🇮🇹": "it", # Italian
    "🇵🇹": "pt", # Portuguese
    "🇷🇺": "ru", # Russian
    "🇳🇱": "nl", # Dutch
    "🇵🇱": "pl", # Polish
    "🇺🇦": "uk", # Ukrainian
    "🇬🇷": "el", # Greek
    "🇹🇷": "tr", # Turkish
    "🇨🇿": "cs", # Czech
    "🇭🇺": "hu", # Hungarian
    "🇷🇴": "ro", # Romanian
    "🇧🇬": "bg", # Bulgarian
    "🇸🇪": "sv", # Swedish
    "🇳🇴": "no", # Norwegian
    "🇩🇰": "da", # Danish
    "🇫🇮": "fi", # Finnish
    "🇮🇸": "is", # Icelandic
    "🇪🇪": "et", # Estonian
    "🇱🇻": "lv", # Latvian
    "🇱🇹": "lt", # Lithuanian
    "🇸🇰": "sk", # Slovak
    "🇸🇮": "sl", # Slovenian
    "🇭🇷": "hr", # Croatian
    "🇷🇸": "sr", # Serbian
    "🇦🇱": "sq", # Albanian
    "🇲🇹": "mt", # Maltese
    "🇨🇳": "zh-CN", # Chinese (Simplified)
    "🇹🇼": "zh-TW", # Chinese (Traditional)
    "🇯🇵": "ja", # Japanese
    "🇰🇷": "ko", # Korean
    "🇮🇳": "hi", # Hindi
    "🇮🇩": "id", # Indonesian
    "🇲🇾": "ms", # Malay
    "🇻🇳": "vi", # Vietnamese
    "🇹🇭": "th", # Thai
    "🇵🇭": "tl", # Tagalog
    "🇮🇱": "he", # Hebrew
    "🇸🇦": "ar", # Arabic
    "🇮🇷": "fa", # Persian
    "🇵🇰": "ur", # Urdu
    "🇧🇩": "bn", # Bengali
    "🇰🇿": "kk", # Kazakh
    "🇺🇿": "uz", # Uzbek
    "🇦🇲": "hy", # Armenian
    "🇬🇪": "ka", # Georgian
    "🇦🇿": "az", # Azerbaijani
    "🇲🇳": "mn", # Mongolian
    "🇿🇦": "af", # Afrikaans
    "🇪🇹": "am", # Amharic
    "🇸🇴": "so", # Somali
    "🇸🇳": "wo", # Wolof
    "🇰🇪": "sw", # Swahili
    "🇳🇬": "ig", # Igbo
    "🇪🇴": "eo", # Esperanto
}

class TranslationView(discord.ui.View):
    """A view with a button that shows the translation ephemerally."""
    def __init__(self, translation_embed: discord.Embed, user_id: int):
        super().__init__(timeout=60)
        self.translation_embed = translation_embed
        self.user_id = user_id

    @discord.ui.button(label="Show Translation", style=discord.ButtonStyle.primary)
    async def show_translation(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This translation was requested by someone else. Please react to the message yourself!", ephemeral=True)
            return
        
        await interaction.response.send_message(embed=self.translation_embed, ephemeral=True)
        # Optional: delete the prompt message after showing the translation
        # await interaction.message.delete()

class TranslatorCog(commands.Cog):
    """
    A cog that translates messages when a user reacts with a flag emoji.
    Translations are sent via DM to the user who reacted.
    Designed to be fully asynchronous and non-blocking.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._session = None
        self._locks = {} # Prevents duplicate translations for the same user/message
        
        # Register Context Menu
        self.ctx_menu = app_commands.ContextMenu(
            name='Translate',
            callback=self.translate_context_menu,
        )
        self.bot.tree.add_command(self.ctx_menu)

    async def translate_context_menu(self, interaction: discord.Interaction, message: discord.Message):
        """Context menu command to translate a message to the user's default language (English)."""
        await interaction.response.defer(ephemeral=True)
        
        # Default to English for context menu translation
        target_lang = "en"
        
        if not message.content or len(message.content.strip()) == 0:
            await interaction.followup.send("This message has no text to translate!", ephemeral=True)
            return

        translated_text = await self.google_translate(message.content, target_lang)
        
        if not translated_text or translated_text.strip() == message.content.strip():
            await interaction.followup.send("Could not translate this message (it might already be in the target language).", ephemeral=True)
            return

        embed = discord.Embed(
            title="Translation Result",
            description=translated_text,
            color=0x4285F4 # Google Blue
        )
        
        channel_name = getattr(message.channel, 'name', 'Direct Message')
        preview = (message.content[:50] + "...") if len(message.content) > 50 else message.content
        embed.set_footer(text=f"Source: #{channel_name} | Original: \"{preview}\"")
        
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": "Mozilla/5.0 AllsparkBot/1.0"}
            )
        return self._session

    def cog_unload(self):
        # Remove Context Menu
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)
        if self._session and not self._session.closed:
            asyncio.create_task(self._session.close())

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """
        Listens for flag reactions on any message the bot can see.
        """
        # Quick pre-checks
        emoji_str = str(payload.emoji)
        if emoji_str not in FLAG_MAPPING:
            return

        if payload.user_id == self.bot.user.id:
            return

        # Spawn the actual processing in a background task
        asyncio.create_task(self._process_translation(payload, emoji_str))

    async def _process_translation(self, payload: discord.RawReactionActionEvent, emoji_str: str):
        """
        Internal method to handle the translation logic in the background.
        """
        user_id = payload.user_id
        message_id = payload.message_id
        lock_key = (user_id, message_id, emoji_str)

        # Basic debouncing
        if lock_key in self._locks:
            return
        
        self._locks[lock_key] = True
        try:
            target_lang = FLAG_MAPPING[emoji_str]

            # 1. Fetch context
            try:
                channel = self.bot.get_channel(payload.channel_id) or await self.bot.fetch_channel(payload.channel_id)
                message = await channel.fetch_message(payload.message_id)
            except (discord.NotFound, discord.Forbidden):
                return
            except Exception as e:
                logger.debug(f"Error fetching message context: {e}")
                return

            if not message.content or len(message.content.strip()) == 0:
                return

            # 2. Perform translation
            translated_text = await self.google_translate(message.content, target_lang)
            if not translated_text or translated_text.strip() == message.content.strip():
                return

            # 3. Send ephemeral via view
            try:
                embed = discord.Embed(
                    title=f"Translation Result {emoji_str}",
                    description=translated_text,
                    color=0x4285F4 # Google Blue
                )
                
                channel_name = getattr(channel, 'name', 'Direct Message')
                preview = (message.content[:50] + "...") if len(message.content) > 50 else message.content
                embed.set_footer(text=f"Source: #{channel_name} | Original: \"{preview}\"")

                view = TranslationView(embed, user_id)
                await channel.send(
                    f"Translation ready for {emoji_str}! (Click below to see it)",
                    view=view,
                    delete_after=60 # Auto-cleanup the prompt
                )
                logger.info(f"Sent translation prompt for message {message_id} to {target_lang}")
                
            except Exception as e:
                logger.error(f"Failed to send translation prompt: {e}")

        finally:
            # Clean up lock after a short delay to prevent spam but allow future reactions
            await asyncio.sleep(2)
            self._locks.pop(lock_key, None)

    async def google_translate(self, text: str, target_lang: str) -> str:
        """
        Uses the free 'gtx' endpoint used by the Google Translate browser extension.
        No API Key required.
        """
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "auto",       # Source Language: Auto-detect
            "tl": target_lang,  # Target Language
            "dt": "t",          # Return translation
            "q": text           # Query text
        }

        try:
            session = await self.get_session()
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.error(f"Google API Error: {resp.status}")
                    return None
                
                data = await resp.json()
                
                # The API returns a nested list. We need to combine the parts.
                # Structure: [[["Translated part 1", "Original part 1"], ["Translated part 2", ...]], ...]
                full_translation = ""
                if data and data[0]:
                    for sentence in data[0]:
                        if sentence and sentence[0]:
                            full_translation += sentence[0]
                
                return full_translation
        except Exception as e:
            logger.error(f"Translation logic error: {e}")
            return None

async def setup(bot: commands.Bot):
    """Setup function to add the TranslatorCog to the bot."""
    try:
        await bot.add_cog(TranslatorCog(bot))
        logger.info("TranslatorCog loaded successfully")
    except Exception as e:
        logger.error(f"Error loading TranslatorCog: {e}")

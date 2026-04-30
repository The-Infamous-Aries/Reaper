"""
Bot Info API Endpoint
Provides bot information for the dashboard and other pages.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import logging
import os

def _groq_available() -> bool:
    """Return True if a GROQ_API_KEY is configured."""
    try:
        from Systems.Functions.config import GROQ_API_KEY
        return bool(GROQ_API_KEY)
    except Exception:
        return False

router = APIRouter()
logger = logging.getLogger("Reaper.BotInfoAPI")

# Global variable to store bot instance (will be set by web server)
bot_instance = None

def set_bot_instance(bot):
    """Set the bot instance for this module."""
    global bot_instance
    bot_instance = bot
    logger.info(f"Bot instance set in bot_info module: {bot.user.name if bot and bot.user else 'None'}")

@router.get("/bot-info")
async def get_bot_info():
    """Get bot information for the dashboard."""
    try:
        bot_data = {}
        
        if bot_instance and bot_instance.user and hasattr(bot_instance.user, 'avatar'):
            # Get actual bot data from Discord
            try:
                # Fetch the bot's user object to get the latest profile data, including the banner
                user = await bot_instance.fetch_user(bot_instance.user.id)
                banner_url = str(user.banner.url) if user.banner else None
            except Exception as e:
                logger.error(f"Failed to fetch bot user or banner: {e}")
                banner_url = None

            logger.info(f"Bot info requested. Name: {bot_instance.user.name}, Banner URL: {banner_url}")
            
            # Validate avatar URL by checking if it exists and is accessible
            avatar_url = None
            if bot_instance.user.avatar:
                try:
                    avatar_url = str(bot_instance.user.avatar.url)
                    # Test if the avatar URL is valid by making a quick HEAD request
                    import httpx
                    async with httpx.AsyncClient() as client:
                        response = await client.head(avatar_url, timeout=2.0)
                        if response.status_code != 200:
                            avatar_url = None
                            logger.warning(f"Avatar URL returned status {response.status_code}, using fallback")
                except Exception as e:
                    logger.warning(f"Failed to validate avatar URL: {e}, using fallback")
                    avatar_url = None
            
            # Use local fallback if no valid avatar URL
            if not avatar_url:
                avatar_url = "/static/Images/reaper.png"
                logger.info("Using local fallback avatar image")
            
            bot_data.update({
                "name": bot_instance.user.name,
                "description": "A comprehensive Discord bot featuring advanced Pet systems, Politics & War tools, and interactive entertainment.",
                "license": "Custom EULA",
                "avatar_url": avatar_url,
                "banner_url": banner_url,
                "groq_api_available": _groq_available(),
                "groq_api_key": ""
            })
        else:
            logger.warning("Bot info requested but bot instance is not available. Using fallback data.")
            # Fallback data when bot is not available
            bot_data = {
                "name": "Reaper Bot",
                "description": "A comprehensive Discord bot featuring advanced Pet systems, Politics & War tools, and interactive entertainment.",
                "license": "Custom EULA",
                "avatar_url": "/static/Images/reaper.png",  # Use local image as fallback
                "banner_url": None,
                "groq_api_available": _groq_available(),
                "groq_api_key": ""
            }
        
        logger.info("Successfully served bot info")
        return JSONResponse(content=bot_data, status_code=200)
        
    except Exception as e:
        logger.error(f"Error serving bot info: {e}")
        raise HTTPException(status_code=500, detail="Error serving bot info")

@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return JSONResponse(content={"status": "healthy"}, status_code=200)
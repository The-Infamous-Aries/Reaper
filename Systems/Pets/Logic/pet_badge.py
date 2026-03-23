import io
import aiohttp
import discord
from PIL import Image
import os
import time
import logging
from Systems.Functions import emoji as emoji_mod

logger = logging.getLogger(__name__)

async def fetch_image(session: aiohttp.ClientSession, url: str) -> Image.Image:
    """
    Fetches an image from a Discord CDN URL.
    Returns a PIL Image in RGBA format.
    """
    try:
        async with session.get(url) as response:
            if response.status != 200:
                logger.warning(f"Failed to fetch image from {url}, status: {response.status}")
                return Image.new("RGBA", (512, 512), (0, 0, 0, 0))
            
            data = await response.read()
            return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception as e:
        logger.error(f"[Badge Maker] Failed to fetch image: {e}", exc_info=True)
        return Image.new("RGBA", (512, 512), (0, 0, 0, 0))


async def generate_pet_badge(pet_data: dict, user_id: int) -> discord.File:
    """
    Generates a 512x512 composite pet badge with a new design.
    - Background: Enlarged Pet Type emoji
    - Corners: Element emojis (element1 top-left/bottom-right, element2 top-right/bottom-left)
    - Center: Species emoji, positioned based on pet type (Flying, Land, Swimming)
    """
    try:
        pet_type = pet_data.get("type") or pet_data.get("category")
        if not pet_type:
            logger.error(f"Pet for user {user_id} has neither a 'type' nor a 'category', defaulting to 'Land'.")
            pet_type = "Land"

        element1 = pet_data.get("element")
        element2 = pet_data.get("element2")
        species = pet_data.get("species")

        if not all([pet_type, element1, species]):
            logger.error(f"Missing critical pet data for badge generation: Type={pet_type}, E1={element1}, Species={species}")
            return None

        pet_type_emoji = emoji_mod.get_partial(pet_type)
        element1_emoji = emoji_mod.get_partial(element1)
        element2_emoji = emoji_mod.get_partial(element2) if element2 else None
        species_emoji = emoji_mod.get_partial(species)

        if not species_emoji or not pet_type_emoji or not element1_emoji:
            logger.error(f"Could not find emoji partials for badge: Type={pet_type_emoji}, E1={element1_emoji}, Species={species_emoji}")
            return None

        async with aiohttp.ClientSession() as session:
            bg_img = await fetch_image(session, pet_type_emoji.url)
            el1_img = await fetch_image(session, element1_emoji.url)
            el2_img = await fetch_image(session, element2_emoji.url) if element2_emoji else None
            species_img = await fetch_image(session, species_emoji.url)

        canvas_size = (512, 512)
        badge = Image.new("RGBA", canvas_size, (0, 0, 0, 0))

        bg_resized = bg_img.resize(canvas_size, Image.Resampling.LANCZOS)
        badge.paste(bg_resized, (0, 0))

        corner_size = 128
        el1_resized = el1_img.resize((corner_size, corner_size), Image.Resampling.LANCZOS)
        badge.paste(el1_resized, (0, 0), el1_resized)
        badge.paste(el1_resized, (canvas_size[0] - corner_size, canvas_size[1] - corner_size), el1_resized)
        
        if el2_img:
            el2_resized = el2_img.resize((corner_size, corner_size), Image.Resampling.LANCZOS)
            badge.paste(el2_resized, (canvas_size[0] - corner_size, 0), el2_resized)
            badge.paste(el2_resized, (0, canvas_size[1] - corner_size), el2_resized)

        tint = Image.new("RGBA", canvas_size, (0, 0, 0, 80))
        badge = Image.alpha_composite(badge, tint)

        pet_size = 200
        pet_resized = species_img.resize((pet_size, pet_size), Image.Resampling.LANCZOS)
        
        offset_x = (canvas_size[0] - pet_size) // 2
        if pet_type and pet_type.lower() == 'flying':
            offset_y = 50
        elif pet_type and pet_type.lower() == 'swimming':
            offset_y = canvas_size[1] - pet_size - 50
        else:
            offset_y = (canvas_size[1] - pet_size) // 2

        badge.paste(pet_resized, (offset_x, offset_y), pet_resized)

        badge_dir = r"c:\Users\codyr\DiscordBots\Reaper\Systems\Data\Badges"
        if not os.path.exists(badge_dir):
            os.makedirs(badge_dir)
            
        file_path = os.path.join(badge_dir, f"{user_id}_badge.png")
        badge.save(file_path, format="PNG")

        buffer = io.BytesIO()
        badge.save(buffer, format="PNG")
        buffer.seek(0)
        
        filename = f"pet_badge_{int(time.time())}.png"
        return discord.File(fp=buffer, filename=filename)

    except Exception as e:
        logger.error(f"Failed to generate pet badge for user {user_id}: {e}", exc_info=True)
        return None
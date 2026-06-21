"""
Stats API Endpoint
Provides homepage statistics and creator information for the dashboard.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import json
import logging
import aiosqlite
import os

router = APIRouter()
logger = logging.getLogger("Reaper.StatsAPI")

# Global variable to store bot instance (will be set by web server)
bot_instance = None

def set_bot_instance(bot):
    """Set the bot instance for this module."""
    global bot_instance
    bot_instance = bot
    logger.info(f"Bot instance set in stats_api module: {bot.user.name if bot and bot.user else 'None'}")

@router.get("/stats")
async def get_stats():
    """Get homepage statistics."""
    stats = {
        "servers": 0,
        "users": 0,
        "alliances": 0,
        "nations": 0,
        "cities": 0,
        "pets": 0,
        "items": 0
    }

    try:
        # Always try to get bot instance from web_server module first
        bot_to_use = bot_instance
        if not bot_to_use:
            try:
                from Systems.Functions.web_server import get_bot_instance
                bot_to_use = get_bot_instance()
                logger.info(f"Got bot instance from web_server: {bot_to_use is not None}")
            except Exception as e:
                logger.warning(f"Failed to get bot instance from web_server: {e}")

        logger.info(f"Bot instance status: {bot_to_use is not None}")
        if bot_to_use:
            logger.info(f"Bot user: {bot_to_use.user.name if bot_to_use.user else 'Unknown'}")

        # Get server and user count from Discord bot
        if bot_to_use:
            try:
                stats["servers"] = len(bot_to_use.guilds)
                # Calculate total users across all servers
                stats["users"] = sum(guild.member_count for guild in bot_to_use.guilds)
                logger.info(f"Discord stats: {stats['servers']} servers, {stats['users']} users")
            except Exception as e:
                logger.warning(f"Failed to get Discord stats: {e}", exc_info=True)
        else:
            logger.warning("Bot instance is None, returning 0 for Discord stats")

        # Get alliance, nation, and city counts from GlobalNations.db
        try:
            nations_db_path = os.path.join(os.getcwd(), "Databases", "PnW", "GlobalNations.db")
            logger.info(f"Checking for nations DB at: {nations_db_path}")
            if os.path.exists(nations_db_path):
                async with aiosqlite.connect(nations_db_path) as db:
                    async with db.execute(
                        "SELECT COUNT(DISTINCT alliance_id) FROM nations "
                        "WHERE alliance_id IS NOT NULL AND alliance_id != 0"
                    ) as cur:
                        result = await cur.fetchone()
                        if result:
                            stats["alliances"] = result[0] or 0
                    async with db.execute(
                        "SELECT COUNT(*) FROM nations "
                        "WHERE nation_name IS NOT NULL AND nation_name != ''"
                    ) as cur:
                        result = await cur.fetchone()
                        if result:
                            stats["nations"] = result[0] or 0
                    async with db.execute("SELECT COUNT(*) FROM cities") as cur:
                        result = await cur.fetchone()
                        if result:
                            stats["cities"] = result[0] or 0
                    logger.info(
                        f"PnW stats: {stats['alliances']} alliances, "
                        f"{stats['nations']} nations, {stats['cities']} cities"
                    )
            else:
                logger.warning(f"Nations DB not found at {nations_db_path}")
                # Try to use the news database for nation count as fallback
                try:
                    from PnWHarvester.db.news_db import get_news_db
                    news_db = get_news_db()
                    if news_db:
                        # Get unique nations from events
                        stats["nations"] = len(news_db.get_all_nations())
                        logger.info(f"Nations count from news DB: {stats['nations']}")
                except Exception as e2:
                    logger.warning(f"Failed to get nation count from news DB: {e2}")
        except Exception as e:
            logger.warning(f"Failed to get nation count: {e}", exc_info=True)

        # Get pet and inventory item counts from Pets database
        try:
            from Systems.Functions.pets_db import pets_db
            all_pets = await pets_db.get_all_pet_data()
            stats["pets"] = len(all_pets) if all_pets else 0
            stats["items"] = _count_inventory_items(all_pets)
            logger.info(f"Pet stats: {stats['pets']} pets, {stats['items']} inventory items")
        except Exception as e:
            logger.warning(f"Failed to get pet count: {e}", exc_info=True)
            # Try fallback method
            try:
                pets_db_path = os.path.join(os.getcwd(), "Databases", "Pets", "pets.db")
                if os.path.exists(pets_db_path):
                    async with aiosqlite.connect(pets_db_path) as db:
                        async with db.execute("SELECT pet_data FROM pets") as cur:
                            rows = await cur.fetchall()
                            pet_payloads = {}
                            for index, row in enumerate(rows):
                                try:
                                    pet_payloads[str(index)] = json.loads(row[0])
                                except Exception:
                                    continue
                            stats["pets"] = len(pet_payloads)
                            stats["items"] = _count_inventory_items(pet_payloads)
                            logger.info(
                                f"Pet stats from fallback DB: "
                                f"{stats['pets']} pets, {stats['items']} inventory items"
                            )
                else:
                    legacy_pets_db_path = os.path.join(os.getcwd(), "Databases", "Pets", "absorb.db")
                    if os.path.exists(legacy_pets_db_path):
                        async with aiosqlite.connect(legacy_pets_db_path) as db:
                            async with db.execute("SELECT COUNT(*) FROM pets") as cur:
                                result = await cur.fetchone()
                                if result:
                                    stats["pets"] = result[0]
                                    logger.info(f"Pet count from legacy absorb DB: {stats['pets']}")
            except Exception as e2:
                logger.warning(f"Failed to get pet count from fallback: {e2}")

        logger.info(f"Final stats: {stats}")
        return JSONResponse(content=stats, status_code=200)

    except Exception as e:
        logger.error(f"Error serving stats: {e}", exc_info=True)
        # Return default stats even on error to ensure frontend always gets something
        return JSONResponse(content=stats, status_code=200)


def _count_inventory_items(all_pets):
    """Count every item quantity across all pet inventories."""
    total = 0
    if not all_pets:
        return total

    for pet in all_pets.values():
        if not isinstance(pet, dict):
            continue
        inventory = pet.get("inventory") or []
        if not isinstance(inventory, list):
            continue

        for item in inventory:
            if not isinstance(item, dict):
                continue
            try:
                total += max(0, int(item.get("count", 1) or 1))
            except (TypeError, ValueError):
                total += 1

    return total


@router.get("/creator")
async def get_creator():
    """Get creator information for the homepage."""
    try:
        creator_data = {
            "name": "The Digital Reaper",
            "avatar": "/static/Images/keeper.png",
            "github": "https://github.com/The-Infamous-Aries/Reaper",
            "pnw_nation": "https://politicsandwar.com/nation/id=680891",
            "email": "cody.ray.inc@gmail.com"
        }

        logger.info("Creator info requested")
        return JSONResponse(content=creator_data, status_code=200)

    except Exception as e:
        logger.error(f"Error serving creator info: {e}")
        raise HTTPException(status_code=500, detail="Error serving creator info")

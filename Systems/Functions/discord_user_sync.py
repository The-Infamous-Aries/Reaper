"""
Discord User Synchronization Utilities

This module provides functions to sync Discord user data (usernames, avatars, etc.)
from the Discord bot to the database, ensuring the dashboard shows current information.
"""

import logging
import asyncio
from typing import Optional, Dict, Any
import aiosqlite

logger = logging.getLogger("Reaper.DiscordUserSync")


async def sync_user_from_bot(user_id: str, bot_instance=None) -> Optional[Dict[str, Any]]:
    """
    Fetch fresh user data from Discord bot and update database.
    
    Args:
        user_id: Discord user ID as string
        bot_instance: Discord bot instance (if None, will try to get from reaper)
    
    Returns:
        Updated user data dict or None if failed
    """
    try:
        if not bot_instance:
            # Try to get bot instance from the main reaper module
            try:
                import sys
                if 'reaper' in sys.modules:
                    reaper_module = sys.modules['reaper']
                    if hasattr(reaper_module, 'bot_instance') and reaper_module.bot_instance:
                        # The bot_instance is a ReaperBot class, get the actual bot
                        if hasattr(reaper_module.bot_instance, 'bot') and reaper_module.bot_instance.bot:
                            bot_instance = reaper_module.bot_instance.bot
                        else:
                            logger.warning("ReaperBot instance found but no bot attribute")
                            return None
                    else:
                        logger.warning("No bot_instance found in reaper module")
                        return None
                else:
                    logger.warning("Reaper module not found in sys.modules")
                    return None
            except Exception as e:
                logger.warning(f"Could not get bot instance for user sync: {e}")
                return None
        
        if not bot_instance:
            logger.warning("No bot instance available for user sync")
            return None
            
        # Fetch user from Discord
        try:
            user_id_int = int(user_id)
            discord_user = bot_instance.get_user(user_id_int)
            if not discord_user:
                discord_user = await bot_instance.fetch_user(user_id_int)
        except Exception as e:
            logger.warning(f"Failed to fetch Discord user {user_id}: {e}")
            return None
            
        if not discord_user:
            logger.warning(f"Discord user {user_id} not found")
            return None
            
        # Convert to dict format matching Discord API
        user_data = {
            'id': str(discord_user.id),
            'username': discord_user.name,
            'global_name': discord_user.global_name,
            'discriminator': discord_user.discriminator,
            'avatar': discord_user.avatar.key if discord_user.avatar else None,
        }
        
        # Update database
        await update_user_in_database(user_data)
        
        logger.info(f"Synced user data from bot for {user_id}: {user_data['global_name'] or user_data['username']}")
        return user_data
        
    except Exception as e:
        logger.error(f"Error syncing user {user_id} from bot: {e}")
        return None


async def update_user_in_database(user_data: Dict[str, Any]) -> bool:
    """
    Update user data in both pets and users database tables.
    
    Args:
        user_data: Dict containing user info (id, username, global_name, avatar, etc.)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        uid = str(user_data.get("id", ""))
        avatar_hash = user_data.get("avatar") or ""
        username = user_data.get("username", "")
        global_name = user_data.get("global_name") or ""
        discriminator = user_data.get("discriminator", "0")
        
        if not uid:
            return False
            
        from Systems.Functions.pets_db import pets_db as _pets_db
        
        # 1. Update pet record
        pet = await _pets_db.get_pet_data(uid)
        if pet is not None:
            old_avatar = pet.get("discord_avatar")
            old_username = pet.get("username")
            
            # Update both avatar and username in pet data
            pet["discord_avatar"] = avatar_hash
            pet["username"] = global_name or username or "Unknown"
            
            if old_avatar != avatar_hash or old_username != pet["username"]:
                await _pets_db.save_pet_data(uid, pet)
                logger.info(f"Updated pet data for user {uid}")

        # 2. Update users table
        try:
            async with aiosqlite.connect(_pets_db.db_path) as db:
                # Ensure all optional columns exist
                columns_to_add = [
                    "avatar TEXT",
                    "global_name TEXT", 
                    "discriminator TEXT",
                    "last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                ]
                
                for col in columns_to_add:
                    try:
                        await db.execute(f"ALTER TABLE users ADD COLUMN {col}")
                        await db.commit()
                    except Exception:
                        pass  # Column already exists
                
                # Upsert comprehensive user data
                await db.execute(
                    """INSERT INTO users (user_id, username, avatar, global_name, discriminator, last_updated)
                       VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                       ON CONFLICT(user_id) DO UPDATE SET
                           username      = excluded.username,
                           avatar        = excluded.avatar,
                           global_name   = excluded.global_name,
                           discriminator = excluded.discriminator,
                           last_updated  = CURRENT_TIMESTAMP""",
                    (uid, username or "Unknown", avatar_hash or None, global_name or None, discriminator or "0")
                )
                await db.commit()
                logger.info(f"Updated users table for user {uid}")
        except Exception as e:
            logger.warning(f"Failed to update users table for {uid}: {e}")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Failed to update user data in database: {e}")
        return False


async def sync_multiple_users(user_ids: list, bot_instance=None) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Sync multiple users from Discord bot sequentially with a small delay between
    each fetch to avoid hammering Discord's rate limits.

    Args:
        user_ids: List of Discord user IDs as strings
        bot_instance: Discord bot instance

    Returns:
        Dict mapping user_id to user_data (or None if failed)
    """
    # Process users one at a time with a small delay — firing 50 parallel
    # fetch_user calls at once is the primary cause of 429s on this token.
    synced_users: Dict[str, Optional[Dict[str, Any]]] = {}
    for user_id in user_ids:
        try:
            result = await sync_user_from_bot(user_id, bot_instance)
            synced_users[user_id] = result
        except Exception as e:
            logger.warning(f"Failed to sync user {user_id}: {e}")
            synced_users[user_id] = None
        # Small delay between fetches to stay well within Discord's rate limits
        await asyncio.sleep(0.5)

    return synced_users


async def get_user_display_name(user_id: str, bot_instance=None) -> str:
    """
    Get the best display name for a user (global_name > username > user_id).
    Will try to fetch fresh data if not in database.
    
    Args:
        user_id: Discord user ID as string
        bot_instance: Discord bot instance
    
    Returns:
        Display name string
    """
    try:
        # First try database
        from Systems.Functions.pets_db import pets_db as _pets_db
        
        async with aiosqlite.connect(_pets_db.db_path) as db:
            async with db.execute(
                "SELECT username, global_name FROM users WHERE user_id = ?",
                (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    username, global_name = row
                    if global_name:
                        return global_name
                    if username:
                        return username
        
        # If not in database or no good name, try to sync from bot
        user_data = await sync_user_from_bot(user_id, bot_instance)
        if user_data:
            return user_data.get('global_name') or user_data.get('username') or user_id
        
        return user_id
        
    except Exception as e:
        logger.warning(f"Failed to get display name for user {user_id}: {e}")
        return user_id
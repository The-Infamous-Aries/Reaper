"""
Discord utility functions for consistent avatar URL handling.
"""

def get_discord_avatar_url(user_id: str, avatar_hash: str | None, size: int = 128) -> str:
    """
    Generate a proper Discord avatar URL with consistent formatting.
    
    Args:
        user_id: Discord user ID as string
        avatar_hash: Avatar hash from Discord API (can be None)
        size: Image size (16, 32, 64, 128, 256, 512, 1024, 2048, 4096)
    
    Returns:
        Complete Discord CDN avatar URL
    """
    if not avatar_hash:
        # Use default Discord avatar - calculate bucket correctly (0-5)
        try:
            bucket = (int(user_id) >> 22) % 6
        except (ValueError, TypeError):
            bucket = 0
        return f"https://cdn.discordapp.com/embed/avatars/{bucket}.png"
    
    # Check if avatar is animated (starts with 'a_')
    if avatar_hash.startswith('a_'):
        ext = 'gif'
    else:
        ext = 'webp'  # Use webp for better compression and quality
    
    return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}?size={size}"


def get_discord_avatar_url_png(user_id: str, avatar_hash: str | None, size: int = 128) -> str:
    """
    Generate a Discord avatar URL that always returns PNG format.
    Useful for contexts that specifically need PNG (like some canvas operations).
    
    Args:
        user_id: Discord user ID as string
        avatar_hash: Avatar hash from Discord API (can be None)
        size: Image size (16, 32, 64, 128, 256, 512, 1024, 2048, 4096)
    
    Returns:
        Complete Discord CDN avatar URL in PNG format
    """
    if not avatar_hash:
        # Use default Discord avatar
        try:
            bucket = (int(user_id) >> 22) % 6
        except (ValueError, TypeError):
            bucket = 0
        return f"https://cdn.discordapp.com/embed/avatars/{bucket}.png"
    
    # Always use PNG format (animated avatars will show first frame)
    return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png?size={size}"
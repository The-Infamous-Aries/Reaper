
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import RedirectResponse, JSONResponse, StreamingResponse
from starlette.requests import Request
import asyncio
import os
import logging
import time
import httpx
import io

# Load environment variables for Discord OAuth
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI")

# Validate that the environment variables are loaded
if not all([DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, DISCORD_REDIRECT_URI]):
    raise ImportError(
        "Discord OAuth credentials (DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, "
        "DISCORD_REDIRECT_URI) are not configured in the environment. "
        "Please set them in your .env file to proceed."
    )


API_ENDPOINT = 'https://discord.com/api/v10'
# Re-fetch profile from Discord at most once every 60 seconds (more frequent for better UX)
PROFILE_REFRESH_INTERVAL = 60

router = APIRouter()
logger = logging.getLogger("Reaper.DiscordAuthAPI")


async def _refresh_access_token(refresh_token: str) -> dict | None:
    """Exchange a refresh token for a new access token. Returns token data or None."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.post(
                f'{API_ENDPOINT}/oauth2/token',
                data={
                    'client_id': DISCORD_CLIENT_ID,
                    'client_secret': DISCORD_CLIENT_SECRET,
                    'grant_type': 'refresh_token',
                    'refresh_token': refresh_token,
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
            )
            r.raise_for_status()
            return r.json()
    except Exception as e:
        logger.warning("Failed to refresh Discord access token: %s", e)
        return None


async def _update_user_avatar_in_database(user_info: dict):
    """Update user avatar hash and profile info in both pets and users database tables."""
    try:
        uid = str(user_info.get("id", ""))
        avatar_hash = user_info.get("avatar") or ""
        username = user_info.get("username", "")
        global_name = user_info.get("global_name") or ""
        discriminator = user_info.get("discriminator", "0")
        
        if not uid:
            return
            
        from Systems.Functions.pets_db import pets_db as _pets_db
        import aiosqlite
        
        # 1. Update avatar hash and username in pet record
        pet = await _pets_db.get_pet_data(uid)
        if pet is not None:
            old_avatar = pet.get("discord_avatar")
            old_username = pet.get("username")
            
            # Update both avatar and username in pet data
            pet["discord_avatar"] = avatar_hash
            pet["username"] = global_name or username or "Unknown"
            
            if old_avatar != avatar_hash or old_username != pet["username"]:
                await _pets_db.save_pet_data(uid, pet)
                logger.info(f"Updated pet data for user {uid}: avatar {old_avatar} -> {avatar_hash}, username {old_username} -> {pet['username']}")

        # 2. Update comprehensive user info in users table
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
                logger.info(f"Updated users table for user {uid}: {global_name or username} (avatar: {avatar_hash})")
        except Exception as e:
            logger.warning(f"Failed to update users table for {uid}: {e}")
            
    except Exception as e:
        logger.warning(f"Failed to update user data in database: {e}")


async def _fetch_discord_user(access_token: str) -> dict | None:
    """Fetch the current user profile from Discord. Returns user dict or None."""
    try:
        logger.info(f"Fetching Discord user profile with access token: {access_token[:10]}...")
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                f'{API_ENDPOINT}/users/@me',
                headers={'Authorization': f'Bearer {access_token}'},
            )
            logger.info(f"Discord API response: {r.status_code}")
            if r.status_code == 401:
                logger.warning("Discord API returned 401 - access token expired or invalid")
                return None
            r.raise_for_status()
            user_data = r.json()
            logger.info(f"Successfully fetched user profile: {user_data.get('username')} (avatar: {user_data.get('avatar')})")
            return user_data
    except Exception as e:
        logger.warning("Failed to fetch Discord user profile: %s", e)
        return None


OAUTH_SCOPES = "identify email guilds"

def _build_oauth_params() -> str:
    """Return the query string shared by both the web and deep-link OAuth URLs."""
    from urllib.parse import urlencode
    return urlencode({
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": OAUTH_SCOPES,
    })

@router.get("/discord/oauth-url")
async def discord_oauth_url():
    """Returns the OAuth URLs so the frontend can attempt deep linking."""
    params = _build_oauth_params()
    return JSONResponse({
        "web_url":  f"https://discord.com/api/oauth2/authorize?{params}",
        "deep_url": f"discord://-/oauth2/authorize?{params}",
    })

@router.get("/discord/login")
async def discord_login():
    """Redirects the user to Discord's authorization page (web fallback)."""
    params = _build_oauth_params()
    return RedirectResponse(f"https://discord.com/api/oauth2/authorize?{params}")

@router.post("/discord/refresh-tokens")
async def refresh_tokens(request: Request):
    """
    Automatically refresh OAuth tokens without requiring user to re-login.
    Creates a new OAuth flow in the background and updates the session.
    """
    try:
        user = request.session.get('discord_user')
        if not user:
            return JSONResponse(content={'error': 'No user session found'}, status_code=401)
        
        user_id = user.get('id')
        logger.info(f"Attempting automatic token refresh for user {user_id}")
        
        # Try refresh token first if available
        refresh_token = request.session.get('discord_refresh_token')
        if refresh_token:
            logger.info(f"Attempting refresh token exchange for user {user_id}")
            new_tokens = await _refresh_access_token(refresh_token)
            if new_tokens:
                access_token = new_tokens['access_token']
                refresh_token = new_tokens.get('refresh_token', refresh_token)
                expires_in = int(new_tokens.get('expires_in', 604800))
                now = int(time.time())
                
                # Update session with new tokens
                request.session['discord_access_token'] = access_token
                request.session['discord_refresh_token'] = refresh_token
                request.session['discord_token_expires_at'] = now + expires_in
                
                logger.info(f"Token refresh successful for user {user_id}")
                
                # Now fetch fresh user data with new token
                fresh_user = await _fetch_discord_user(access_token)
                if fresh_user:
                    request.session['discord_user'] = fresh_user
                    request.session['discord_profile_fetched_at'] = now
                    
                    # Update database with fresh user data
                    try:
                        await _update_user_avatar_in_database(fresh_user)
                        logger.info(f"Updated database after token refresh for user {user_id}")
                    except Exception as e:
                        logger.warning(f"Failed to update database after token refresh: {e}")
                    
                    return JSONResponse(content={
                        'success': True,
                        'method': 'refresh_token',
                        'user': fresh_user,
                        'message': 'Tokens refreshed successfully'
                    })
        
        # If refresh token failed or not available, create a silent re-auth URL
        logger.info(f"Creating silent re-auth for user {user_id}")
        
        # Generate a state parameter to track this request
        import secrets
        state = secrets.token_urlsafe(32)
        request.session['oauth_state'] = state
        request.session['silent_reauth'] = True
        
        # Create OAuth URL with prompt=none for silent auth
        from urllib.parse import urlencode
        oauth_params = {
            "client_id": DISCORD_CLIENT_ID,
            "redirect_uri": DISCORD_REDIRECT_URI,
            "response_type": "code",
            "scope": "identify email guilds",
            "state": state,
            "prompt": "none"  # This attempts silent auth
        }
        
        oauth_url = f"https://discord.com/api/oauth2/authorize?{urlencode(oauth_params)}"
        
        return JSONResponse(content={
            'success': True,
            'method': 'silent_reauth',
            'oauth_url': oauth_url,
            'message': 'Silent re-authentication required',
            'instructions': 'Open the OAuth URL in a popup or iframe for seamless re-auth'
        })
        
    except Exception as e:
        logger.error(f"Error refreshing tokens for user {user.get('id') if user else 'unknown'}: {e}")
        return JSONResponse(content={'error': str(e)}, status_code=500)


@router.post("/discord/silent-reauth")
async def silent_reauth(request: Request):
    """
    Handle silent re-authentication by opening OAuth in a popup/iframe.
    This allows getting fresh tokens without disrupting the main page.
    """
    try:
        user = request.session.get('discord_user')
        if not user:
            return JSONResponse(content={'error': 'No user session found'}, status_code=401)
        
        user_id = user.get('id')
        logger.info(f"Starting silent re-auth for user {user_id}")
        
        # Generate state for security
        import secrets
        state = secrets.token_urlsafe(32)
        request.session['oauth_state'] = state
        request.session['silent_reauth'] = True
        request.session['original_user_id'] = user_id
        
        # Create OAuth URL for silent auth
        from urllib.parse import urlencode
        oauth_params = {
            "client_id": DISCORD_CLIENT_ID,
            "redirect_uri": DISCORD_REDIRECT_URI,
            "response_type": "code",
            "scope": "identify email guilds",
            "state": state,
            "prompt": "none"  # Attempt silent auth
        }
        
        oauth_url = f"https://discord.com/api/oauth2/authorize?{urlencode(oauth_params)}"
        
        return JSONResponse(content={
            'success': True,
            'oauth_url': oauth_url,
            'state': state,
            'message': 'Open this URL in a popup for silent re-authentication'
        })
        
    except Exception as e:
        logger.error(f"Error starting silent reauth: {e}")
        return JSONResponse(content={'error': str(e)}, status_code=500)


@router.get("/discord/callback")
async def discord_callback(request: Request, code: str, state: str = None):
    """Handles the callback from Discord after authorization."""
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code not provided.")

    # Check if this is a silent re-auth
    is_silent_reauth = request.session.get('silent_reauth', False)
    expected_state = request.session.get('oauth_state')
    
    if is_silent_reauth and state != expected_state:
        raise HTTPException(status_code=400, detail="Invalid state parameter for silent re-auth.")

    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.post(
            f'{API_ENDPOINT}/oauth2/token',
            data={
                'client_id': DISCORD_CLIENT_ID,
                'client_secret': DISCORD_CLIENT_SECRET,
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': DISCORD_REDIRECT_URI,
            },
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )
        r.raise_for_status()
        token_data = r.json()

    access_token = token_data['access_token']
    refresh_token = token_data.get('refresh_token')
    expires_in = int(token_data.get('expires_in', 604800))  # default 7 days

    user_info = await _fetch_discord_user(access_token)
    if not user_info:
        raise HTTPException(status_code=502, detail="Could not fetch Discord user info.")

    request.session['discord_user'] = user_info
    request.session['discord_access_token'] = access_token
    request.session['discord_refresh_token'] = refresh_token
    request.session['discord_token_expires_at'] = int(time.time()) + expires_in
    request.session['discord_profile_fetched_at'] = int(time.time())

    # Clear silent reauth flags
    request.session.pop('silent_reauth', None)
    request.session.pop('oauth_state', None)
    request.session.pop('original_user_id', None)

    # Update avatar in database immediately on login
    try:
        await _update_user_avatar_in_database(user_info)
        logger.info(f"Successfully updated user data for {user_info.get('id')}: {user_info.get('global_name') or user_info.get('username')} (avatar: {user_info.get('avatar')})")
    except Exception as e:
        logger.warning(f"Failed to update avatar on login: {e}")

    # If this was a silent re-auth, return a special response for the popup
    if is_silent_reauth:
        return """
        <html>
        <head><title>Re-authentication Complete</title></head>
        <body>
        <script>
        // Notify parent window that re-auth is complete
        if (window.opener) {
            window.opener.postMessage({type: 'discord_reauth_complete', success: true}, '*');
            window.close();
        } else if (window.parent !== window) {
            window.parent.postMessage({type: 'discord_reauth_complete', success: true}, '*');
        } else {
            // Fallback - redirect to dashboard
            window.location.href = '/dashboard.html';
        }
        </script>
        <p>Re-authentication complete! This window should close automatically.</p>
        </body>
        </html>
        """

    return RedirectResponse(url='/dashboard.html')


@router.get("/discord/me")
async def discord_me(request: Request):
    """Alias for /discord/user — returns the current session user's id/username."""
    user = request.session.get('discord_user')
    if not user:
        return JSONResponse(content={'error': 'Not logged in'}, status_code=401)
    return JSONResponse(content={"id": user.get("id"), "username": user.get("username", "")})


@router.get("/discord/user")
async def get_discord_user(request: Request):
    """
    Returns the current Discord user, refreshing their profile from Discord
    if the cached copy is older than PROFILE_REFRESH_INTERVAL seconds.
    Automatically refreshes the access token if it has expired.
    ALWAYS updates avatar hash in database when profile is refreshed.
    """
    user = request.session.get('discord_user')
    if not user:
        logger.warning("No user in session for /discord/user request")
        return JSONResponse(content={'error': 'Not logged in'}, status_code=401)

    access_token: str | None = request.session.get('discord_access_token')
    refresh_token: str | None = request.session.get('discord_refresh_token')
    expires_at: int = request.session.get('discord_token_expires_at', 0)
    last_fetched: int = request.session.get('discord_profile_fetched_at', 0)
    now = int(time.time())

    logger.info(f"User {user.get('id')} requesting profile, token expires: {expires_at}, now: {now}")

    # If last_fetched is 0 it means an old session that predates this field —
    # treat it as "just fetched" so we don't hammer Discord on every page load.
    if last_fetched == 0:
        request.session['discord_profile_fetched_at'] = now
        last_fetched = now

    # Refresh the access token if it has expired (or is about to in 60s)
    if access_token and expires_at and now >= expires_at - 60:
        logger.info(f"Token expired for user {user.get('id')}, attempting refresh")
        if refresh_token:
            new_tokens = await _refresh_access_token(refresh_token)
            if new_tokens:
                access_token = new_tokens['access_token']
                refresh_token = new_tokens.get('refresh_token', refresh_token)
                expires_in = int(new_tokens.get('expires_in', 604800))
                request.session['discord_access_token'] = access_token
                request.session['discord_refresh_token'] = refresh_token
                request.session['discord_token_expires_at'] = now + expires_in
                logger.info(f"Token refreshed for user {user.get('id')}")
            else:
                # Token refresh failed — serve cached user if we still have one,
                # only force re-auth if there's no cached user at all.
                if not user:
                    return JSONResponse(content={'error': 'Not logged in'}, status_code=401)
                logger.warning("Token refresh failed for user %s — serving cached session", user.get('id'))
                # Clear the stale token so we don't keep hammering Discord
                request.session.pop('discord_access_token', None)
                request.session.pop('discord_refresh_token', None)
                request.session.pop('discord_token_expires_at', None)
                return JSONResponse(content=user)

    # Re-fetch profile if stale OR if we have a valid token (to ensure fresh avatar)
    should_refresh = (now - last_fetched) >= PROFILE_REFRESH_INTERVAL
    
    if access_token and should_refresh:
        logger.info(f"Refreshing profile for user {user.get('id')} (age: {now - last_fetched}s)")
        fresh_user = await _fetch_discord_user(access_token)
        if fresh_user:
            # Check if avatar changed and update database immediately
            old_avatar = user.get('avatar')
            new_avatar = fresh_user.get('avatar')
            
            request.session['discord_user'] = fresh_user
            request.session['discord_profile_fetched_at'] = now
            user = fresh_user
            
            # Update avatar in database if it changed
            if old_avatar != new_avatar:
                logger.info(f"Avatar changed for user {fresh_user.get('id')}: {old_avatar} -> {new_avatar}")
                await _update_user_avatar_in_database(fresh_user)
            
        else:
            logger.warning("Profile refresh failed for user %s — serving cached copy", user.get('id'))

    return JSONResponse(content=user)


@router.get("/discord/avatar")
async def get_discord_avatar(request: Request):
    """
    Proxy the current user's Discord avatar through our server.
    Always fetches fresh avatar data from Discord API to ensure latest avatar.
    Updates database with new avatar hash if it changed.
    """
    user = request.session.get('discord_user')
    access_token = request.session.get('discord_access_token')
    refresh_token = request.session.get('discord_refresh_token')
    expires_at = request.session.get('discord_token_expires_at', 0)

    if not user:
        raise HTTPException(status_code=401, detail="Not logged in.")

    user_id = user.get('id')
    now = int(time.time())
    
    logger.info(f"Avatar request for user {user_id}, token expires: {expires_at}, now: {now}")
    
    # Refresh the access token if it has expired (or is about to in 60s)
    if access_token and expires_at and now >= expires_at - 60:
        logger.info(f"Token expired for user {user_id}, attempting refresh")
        if refresh_token:
            new_tokens = await _refresh_access_token(refresh_token)
            if new_tokens:
                access_token = new_tokens['access_token']
                refresh_token = new_tokens.get('refresh_token', refresh_token)
                expires_in = int(new_tokens.get('expires_in', 604800))
                request.session['discord_access_token'] = access_token
                request.session['discord_refresh_token'] = refresh_token
                request.session['discord_token_expires_at'] = now + expires_in
                logger.info(f"Token refreshed for user {user_id}")
            else:
                logger.warning(f"Token refresh failed for user {user_id}")
                # Clear the stale token
                request.session.pop('discord_access_token', None)
                request.session.pop('discord_refresh_token', None)
                request.session.pop('discord_token_expires_at', None)
                access_token = None
    
    # ALWAYS refresh profile when avatar is requested to ensure freshest data
    if access_token:
        logger.info(f"Refreshing profile for avatar request for user {user_id}")
        fresh = await _fetch_discord_user(access_token)
        if fresh:
            old_avatar = user.get('avatar')
            new_avatar = fresh.get('avatar')
            
            logger.info(f"Profile refresh result: old_avatar={old_avatar}, new_avatar={new_avatar}")
            
            # Update session with fresh data
            request.session['discord_user'] = fresh
            request.session['discord_profile_fetched_at'] = int(time.time())
            user = fresh
            
            # Update database if avatar changed
            if old_avatar != new_avatar:
                logger.info(f"Avatar updated for user {user_id}: {old_avatar} -> {new_avatar}")
                try:
                    await _update_user_avatar_in_database(fresh)
                except Exception as e:
                    logger.warning(f"Failed to update avatar in database: {e}")
        else:
            logger.warning(f"Profile refresh failed for user {user_id} - _fetch_discord_user returned None")
    else:
        logger.warning(f"No access token available for profile refresh for user {user_id}")
        # Try to get fresh data from bot as fallback
        try:
            from Systems.Functions.discord_user_sync import sync_user_from_bot
            logger.info(f"Attempting bot sync fallback for avatar request for user {user_id}")
            fresh_data = await sync_user_from_bot(user_id)
            if fresh_data:
                logger.info(f"Bot sync successful for avatar request: {fresh_data.get('username')} (avatar: {fresh_data.get('avatar')})")
                old_avatar = user.get('avatar')
                new_avatar = fresh_data.get('avatar')
                
                # Update session with bot data
                request.session['discord_user'] = fresh_data
                request.session['discord_profile_fetched_at'] = int(time.time())
                user = fresh_data
                
                if old_avatar != new_avatar:
                    logger.info(f"Avatar updated via bot sync for user {user_id}: {old_avatar} -> {new_avatar}")
            else:
                logger.warning(f"Bot sync also failed for user {user_id}")
        except Exception as e:
            logger.warning(f"Bot sync fallback failed for user {user_id}: {e}")

    async def _serve_avatar(avatar_hash: str | None) -> Response:
        if not avatar_hash:
            default_index = (int(user_id) >> 22) % 6 if user_id else 0
            url = f"https://cdn.discordapp.com/embed/avatars/{default_index}.png"
            response = RedirectResponse(url, status_code=302)
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        from Systems.Functions.discord_utils import get_discord_avatar_url
        # For auth endpoint, we want to preserve animated GIFs
        if avatar_hash and avatar_hash.startswith('a_'):
            cdn_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.gif?size=128"
        else:
            cdn_url = get_discord_avatar_url(user_id, avatar_hash, size=128)
        logger.info("Fetching avatar from CDN: %s", cdn_url)

        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(cdn_url)
            logger.info("CDN response: %s for %s", r.status_code, cdn_url)
            if r.status_code == 404:
                return None  # signal: hash is stale
            r.raise_for_status()
            # Determine content type based on URL
            if cdn_url.endswith('.gif'):
                content_type = 'image/gif'
            elif cdn_url.endswith('.webp'):
                content_type = 'image/webp'
            else:
                content_type = r.headers.get('content-type', 'image/png')
            
            # Add cache control headers to prevent stale avatar caching
            response = StreamingResponse(io.BytesIO(r.content), media_type=content_type)
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

    try:
        result = await _serve_avatar(user.get('avatar'))

        if result is None:
            # CDN 404 — hash is stale even after profile refresh.
            # Try once more with a forced re-fetch from Discord API.
            logger.warning(
                "Avatar hash stale for user %s (%s) — forcing second re-fetch from Discord API",
                user_id, user.get('avatar')
            )
            if access_token:
                logger.info(f"Attempting fresh Discord API fetch for user {user_id}")
                fresh = await _fetch_discord_user(access_token)
                if fresh:
                    logger.info(f"Fresh user data received: avatar {fresh.get('avatar')}")
                    if fresh.get('avatar') != user.get('avatar'):
                        logger.info(f"Avatar hash changed: {user.get('avatar')} -> {fresh.get('avatar')}")
                        request.session['discord_user'] = fresh
                        user = fresh
                        # Update database with the corrected avatar
                        try:
                            await _update_user_avatar_in_database(fresh)
                        except Exception as e:
                            logger.warning(f"Failed to update corrected avatar: {e}")
                        result = await _serve_avatar(fresh.get('avatar'))
                    else:
                        logger.warning(f"Fresh fetch returned same stale avatar hash: {fresh.get('avatar')}")
                else:
                    logger.warning(f"Fresh Discord API fetch failed for user {user_id} - access token may be expired")
            else:
                logger.warning(f"No access token available for fresh fetch for user {user_id}")

            # Still None (hash genuinely missing or still stale) — serve default
            if result is None:
                logger.info(f"Serving default avatar for user {user_id}")
                default_index = (int(user_id) >> 22) % 6 if user_id else 0
                result = RedirectResponse(
                    f"https://cdn.discordapp.com/embed/avatars/{default_index}.png",
                    status_code=302
                )
                result.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                result.headers["Pragma"] = "no-cache"
                result.headers["Expires"] = "0"

        return result

    except httpx.HTTPStatusError as e:
        logger.warning("Avatar CDN returned error %s: %s", e.response.status_code, e)
        raise HTTPException(status_code=502, detail="Could not fetch avatar.")
    except Exception as e:
        logger.warning("Avatar proxy failed: %s", e)
        raise HTTPException(status_code=502, detail="Could not fetch avatar.")


@router.post("/discord/refresh-profile")
async def refresh_discord_profile(request: Request):
    """
    Force refresh the current user's complete Discord profile from the API.
    Updates username, global_name, avatar, and all other profile data.
    """
    # Debug session data
    logger.info(f"Session keys: {list(request.session.keys())}")


@router.post("/discord/logout")
async def discord_logout(request: Request):
    """Log out the current user by clearing their session."""
    user = request.session.get('discord_user')
    if user:
        logger.info(f"User {user.get('id')} logging out")
    
    # Clear the session
    request.session.clear()
    
    return JSONResponse(content={'success': True, 'message': 'Logged out successfully'})
    user = request.session.get('discord_user')
    access_token = request.session.get('discord_access_token')
    
    logger.info(f"User in session: {bool(user)}, Access token: {bool(access_token)}")
    
    if not user:
        logger.warning("No user in session for refresh-profile request")
        return JSONResponse(content={'error': 'Not logged in'}, status_code=401)
    
    if not access_token:
        logger.warning(f"No access token for user {user.get('id', 'unknown')}")
        return JSONResponse(content={'error': 'No access token available'}, status_code=401)
    
    try:
        # Force fetch fresh user data
        fresh_user = await _fetch_discord_user(access_token)
        if not fresh_user:
            logger.warning(f"Failed to fetch fresh user data for {user.get('id')}")
            return JSONResponse(content={'error': 'Failed to fetch fresh user data'}, status_code=502)
        
        old_user = user.copy()
        
        # Update session with fresh data
        request.session['discord_user'] = fresh_user
        request.session['discord_profile_fetched_at'] = int(time.time())
        
        # Update database with all user info
        await _update_user_avatar_in_database(fresh_user)
        
        # Check what changed
        changes = {}
        if old_user.get('username') != fresh_user.get('username'):
            changes['username'] = {'old': old_user.get('username'), 'new': fresh_user.get('username')}
        if old_user.get('global_name') != fresh_user.get('global_name'):
            changes['global_name'] = {'old': old_user.get('global_name'), 'new': fresh_user.get('global_name')}
        if old_user.get('avatar') != fresh_user.get('avatar'):
            changes['avatar'] = {'old': old_user.get('avatar'), 'new': fresh_user.get('avatar')}
        if old_user.get('discriminator') != fresh_user.get('discriminator'):
            changes['discriminator'] = {'old': old_user.get('discriminator'), 'new': fresh_user.get('discriminator')}
        
        logger.info(f"Profile refreshed for user {fresh_user.get('id')}, changes: {changes}")
        
        return JSONResponse(content={
            'success': True,
            'changes': changes,
            'user': fresh_user
        })
        
    except Exception as e:
        logger.error(f"Error refreshing profile for user {user.get('id')}: {e}")
        return JSONResponse(content={'error': 'Failed to refresh profile'}, status_code=500)


@router.post("/discord/refresh-profile-fallback")
async def refresh_discord_profile_fallback(request: Request):
    """
    Fallback refresh method that tries to sync user data from the bot directly.
    If bot sync fails, falls back to using existing session data with timestamp update.
    """
    try:
        # Try to get user ID from various sources
        user_id = None
        
        # First try session
        user = request.session.get('discord_user')
        if user:
            user_id = str(user.get('id', ''))
        
        if not user_id:
            logger.warning("Cannot determine user ID for fallback refresh")
            return JSONResponse(content={'error': 'Cannot determine user ID'}, status_code=400)
        
        logger.info(f"Attempting fallback refresh for user {user_id}")
        
        # Try to sync from bot directly
        fresh_data = None
        bot_sync_error = None
        try:
            from Systems.Functions.discord_user_sync import sync_user_from_bot
            fresh_data = await sync_user_from_bot(user_id)
        except Exception as e:
            bot_sync_error = str(e)
            logger.warning(f"Bot sync failed for user {user_id}: {e}")
        
        if fresh_data:
            # Bot sync successful
            changes = {}
            if user:
                old_user = user.copy()
                request.session['discord_user'] = fresh_data
                request.session['discord_profile_fetched_at'] = int(time.time())
                
                # Check what changed
                if old_user.get('username') != fresh_data.get('username'):
                    changes['username'] = {'old': old_user.get('username'), 'new': fresh_data.get('username')}
                if old_user.get('global_name') != fresh_data.get('global_name'):
                    changes['global_name'] = {'old': old_user.get('global_name'), 'new': fresh_data.get('global_name')}
                if old_user.get('avatar') != fresh_data.get('avatar'):
                    changes['avatar'] = {'old': old_user.get('avatar'), 'new': fresh_data.get('avatar')}
            else:
                # No existing session, create new one
                request.session['discord_user'] = fresh_data
                request.session['discord_profile_fetched_at'] = int(time.time())
                changes = {'synced_from_bot': True}
            
            logger.info(f"Profile synced from bot for user {user_id}, changes: {changes}")
            
            return JSONResponse(content={
                'success': True,
                'changes': changes,
                'user': fresh_data,
                'method': 'bot_sync'
            })
        else:
            # Bot sync failed, use existing session data but update timestamp
            if user:
                logger.info(f"Bot sync failed for user {user_id}, using existing session data")
                request.session['discord_profile_fetched_at'] = int(time.time())
                
                return JSONResponse(content={
                    'success': True,
                    'changes': {'timestamp_updated': True},
                    'user': user,
                    'method': 'session_refresh',
                    'note': f'Bot sync unavailable: {bot_sync_error or "User not in bot cache"}'
                })
            else:
                # No session data and bot sync failed
                logger.error(f"No session data and bot sync failed for user {user_id}")
                return JSONResponse(content={
                    'error': f'No session data and bot sync failed: {bot_sync_error or "User not in bot cache"}'
                }, status_code=502)
        
    except Exception as e:
        logger.error(f"Error in fallback profile refresh: {e}")
        return JSONResponse(content={'error': f'Failed to refresh profile via fallback: {str(e)}'}, status_code=500)
    """
    Force refresh the current user's Discord avatar from the API.
    Useful when user knows they've updated their avatar and wants immediate refresh.
    """
    user = request.session.get('discord_user')
    access_token = request.session.get('discord_access_token')
    
    if not user:
        return JSONResponse(content={'error': 'Not logged in'}, status_code=401)
    
    if not access_token:
        return JSONResponse(content={'error': 'No access token available'}, status_code=401)
    
    try:
        # Force fetch fresh user data
        fresh_user = await _fetch_discord_user(access_token)
        if not fresh_user:
            return JSONResponse(content={'error': 'Failed to fetch fresh user data'}, status_code=502)
        
        old_avatar = user.get('avatar')
        new_avatar = fresh_user.get('avatar')
        
        # Update session
        request.session['discord_user'] = fresh_user
        request.session['discord_profile_fetched_at'] = int(time.time())
        
        # Update database
        await _update_user_avatar_in_database(fresh_user)
        
        return JSONResponse(content={
            'success': True,
            'avatar_changed': old_avatar != new_avatar,
            'old_avatar': old_avatar,
            'new_avatar': new_avatar,
            'user_id': fresh_user.get('id')
        })
        
    except Exception as e:
        logger.error(f"Error refreshing avatar for user {user.get('id')}: {e}")
        return JSONResponse(content={'error': 'Failed to refresh avatar'}, status_code=500)


@router.get("/discord/session-status")
async def discord_session_status(request: Request):
    """Check the current session status for debugging."""
    user = request.session.get('discord_user')
    access_token = request.session.get('discord_access_token')
    refresh_token = request.session.get('discord_refresh_token')
    expires_at = request.session.get('discord_token_expires_at', 0)
    last_fetched = request.session.get('discord_profile_fetched_at', 0)
    
    now = int(time.time())
    
    return JSONResponse(content={
        'has_user': bool(user),
        'user_id': user.get('id') if user else None,
        'username': user.get('username') if user else None,
        'global_name': user.get('global_name') if user else None,
        'avatar': user.get('avatar') if user else None,
        'has_access_token': bool(access_token),
        'has_refresh_token': bool(refresh_token),
        'token_expires_at': expires_at,
        'token_expired': expires_at > 0 and now >= expires_at,
        'last_profile_fetch': last_fetched,
        'profile_age_seconds': now - last_fetched if last_fetched > 0 else None,
        'session_keys': list(request.session.keys()),
        'current_time': now
    })


@router.get("/discord/debug-bot-access")
async def debug_bot_access(request: Request):
    """Debug endpoint to check if bot instance is accessible."""
    try:
        import sys
        
        debug_info = {
            'reaper_in_modules': 'reaper' in sys.modules,
            'bot_instance_exists': False,
            'bot_instance_type': None,
            'has_bot_attr': False,
            'bot_is_ready': False,
            'bot_user': None,
            'error': None
        }
        
        if 'reaper' in sys.modules:
            reaper_module = sys.modules['reaper']
            if hasattr(reaper_module, 'bot_instance'):
                debug_info['bot_instance_exists'] = True
                bot_instance = reaper_module.bot_instance
                debug_info['bot_instance_type'] = str(type(bot_instance))
                
                if hasattr(bot_instance, 'bot'):
                    debug_info['has_bot_attr'] = True
                    actual_bot = bot_instance.bot
                    if actual_bot:
                        debug_info['bot_is_ready'] = actual_bot.is_ready()
                        if actual_bot.user:
                            debug_info['bot_user'] = {
                                'id': str(actual_bot.user.id),
                                'name': actual_bot.user.name,
                                'discriminator': actual_bot.user.discriminator
                            }
        
        return JSONResponse(content=debug_info)
        
    except Exception as e:
        logger.error(f"Error in debug bot access: {e}")
        return JSONResponse(content={'error': str(e)}, status_code=500)


@router.post("/discord/force-avatar-refresh")
async def force_avatar_refresh(request: Request):
    """
    Force a complete avatar refresh by clearing cached data and fetching fresh from Discord.
    """
    try:
        user = request.session.get('discord_user')
        if not user:
            return JSONResponse(content={'error': 'Not logged in'}, status_code=401)
        
        user_id = user.get('id')
        logger.info(f"Force avatar refresh requested for user {user_id}")
        
        # First try the main refresh profile endpoint
        refresh_result = await refresh_discord_profile(request)
        
        if hasattr(refresh_result, 'body'):
            import json
            refresh_data = json.loads(refresh_result.body.decode())
            if refresh_data.get('success'):
                logger.info(f"Force refresh successful for user {user_id}")
                return JSONResponse(content={
                    'success': True,
                    'message': 'Avatar refreshed successfully',
                    'user': refresh_data.get('user'),
                    'changes': refresh_data.get('changes', {})
                })
        
        # If main refresh failed, try fallback
        logger.info(f"Main refresh failed, trying fallback for user {user_id}")
        fallback_result = await refresh_discord_profile_fallback(request)
        
        if hasattr(fallback_result, 'body'):
            import json
            fallback_data = json.loads(fallback_result.body.decode())
            if fallback_data.get('success'):
                logger.info(f"Fallback refresh successful for user {user_id}")
                return JSONResponse(content={
                    'success': True,
                    'message': 'Avatar refreshed via fallback',
                    'user': fallback_data.get('user'),
                    'changes': fallback_data.get('changes', {}),
                    'method': fallback_data.get('method', 'fallback')
                })
        
        return JSONResponse(content={'error': 'Both refresh methods failed'}, status_code=502)
        
    except Exception as e:
        logger.error(f"Error in force avatar refresh: {e}")
        return JSONResponse(content={'error': str(e)}, status_code=500)
    """Test endpoint to verify bot sync functionality."""
    try:
        user = request.session.get('discord_user')
        if not user:
            return JSONResponse(content={'error': 'Not logged in'}, status_code=401)
        
        user_id = str(user.get('id', ''))
        if not user_id:
            return JSONResponse(content={'error': 'No user ID in session'}, status_code=400)
        
        logger.info(f"Testing bot sync for user {user_id}")
        
        # Test the sync function directly
        from Systems.Functions.discord_user_sync import sync_user_from_bot
        result = await sync_user_from_bot(user_id)
        
        return JSONResponse(content={
            'success': result is not None,
            'user_data': result,
            'original_user': user
        })
        
    except Exception as e:
        logger.error(f"Error testing bot sync: {e}")
        return JSONResponse(content={'error': str(e)}, status_code=500)


@router.post("/discord/test-bot-sync")
async def test_bot_sync(request: Request):
    """Test endpoint to verify bot sync functionality."""
    try:
        user = request.session.get('discord_user')
        if not user:
            return JSONResponse(content={'error': 'Not logged in'}, status_code=401)
        
        user_id = str(user.get('id', ''))
        if not user_id:
            return JSONResponse(content={'error': 'No user ID in session'}, status_code=400)
        
        logger.info(f"Testing bot sync for user {user_id}")
        
        # Test the sync function directly
        from Systems.Functions.discord_user_sync import sync_user_from_bot
        result = await sync_user_from_bot(user_id)
        
        return JSONResponse(content={
            'success': result is not None,
            'user_data': result,
            'original_user': user
        })
        
    except Exception as e:
        logger.error(f"Error testing bot sync: {e}")
        return JSONResponse(content={'error': str(e)}, status_code=500)
    """Test endpoint to verify refresh functionality works correctly."""
    try:
        user = request.session.get('discord_user')
        if not user:
            return JSONResponse(content={'error': 'Not logged in'}, status_code=401)
        
        # Test main refresh
        main_result = None
        try:
            main_result = await refresh_discord_profile(request)
            if hasattr(main_result, 'body'):
                import json
                main_result = json.loads(main_result.body.decode())
        except Exception as e:
            main_result = {'error': str(e)}
        
        # Test fallback refresh
        fallback_result = None
        try:
            fallback_result = await refresh_discord_profile_fallback(request)
            if hasattr(fallback_result, 'body'):
                import json
                fallback_result = json.loads(fallback_result.body.decode())
        except Exception as e:
            fallback_result = {'error': str(e)}
        
        return JSONResponse(content={
            'main_refresh': main_result,
            'fallback_refresh': fallback_result,
            'current_user': request.session.get('discord_user')
        })
        
    except Exception as e:
        logger.error(f"Test refresh failed: {e}")
        return JSONResponse(content={'error': str(e)}, status_code=500)
@router.post("/discord/test-refresh")
async def test_refresh_functionality(request: Request):
    """Test endpoint to verify refresh functionality works correctly."""
    try:
        user = request.session.get('discord_user')
        if not user:
            return JSONResponse(content={'error': 'Not logged in'}, status_code=401)
        
        # Test main refresh
        main_result = None
        try:
            main_result = await refresh_discord_profile(request)
            if hasattr(main_result, 'body'):
                import json
                main_result = json.loads(main_result.body.decode())
        except Exception as e:
            main_result = {'error': str(e)}
        
        # Test fallback refresh
        fallback_result = None
        try:
            fallback_result = await refresh_discord_profile_fallback(request)
            if hasattr(fallback_result, 'body'):
                import json
                fallback_result = json.loads(fallback_result.body.decode())
        except Exception as e:
            fallback_result = {'error': str(e)}
        
        return JSONResponse(content={
            'main_refresh': main_result,
            'fallback_refresh': fallback_result,
            'current_user': request.session.get('discord_user')
        })
        
    except Exception as e:
        logger.error(f"Test refresh failed: {e}")
        return JSONResponse(content={'error': str(e)}, status_code=500)


@router.post("/discord/clear-stale-session")
async def clear_stale_session(request: Request):
    """
    Clear stale session data when OAuth tokens are expired.
    This forces the user to re-authenticate to get fresh tokens.
    """
    try:
        user = request.session.get('discord_user')
        if not user:
            return JSONResponse(content={'error': 'No session to clear'}, status_code=400)
        
        user_id = user.get('id')
        logger.info(f"Clearing stale session for user {user_id}")
        
        # Clear OAuth-related session data but keep user info temporarily
        request.session.pop('discord_access_token', None)
        request.session.pop('discord_refresh_token', None)
        request.session.pop('discord_token_expires_at', None)
        
        return JSONResponse(content={
            'success': True,
            'message': 'Stale session data cleared. Please refresh or re-login for fresh avatar.',
            'user_id': user_id
        })
        
    except Exception as e:
        logger.error(f"Error clearing stale session: {e}")
        return JSONResponse(content={'error': str(e)}, status_code=500)


@router.get("/discord/logout")
async def discord_logout(request: Request):
    """Logs the user out by clearing the session."""
    request.session.clear()
    return RedirectResponse(url='/dashboard.html')

@router.post("/discord/link-nation")
async def link_nation(request: Request):
    """Link a PnW nation ID to the current session (works with or without Discord login)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")
    nation_id = str(body.get("nation_id", "")).strip()
    if not nation_id.isdigit():
        raise HTTPException(status_code=400, detail="nation_id must be numeric.")
    nation_name = str(body.get("nation_name", "")).strip()
    flag = str(body.get("flag", "")).strip()
    request.session["linked_nation"] = {
        "nation_id": nation_id,
        "nation_name": nation_name,
        "flag": flag,
    }
    return JSONResponse({"ok": True, "nation_id": nation_id, "nation_name": nation_name, "flag": flag})

@router.get("/discord/linked-nation")
async def get_linked_nation(request: Request):
    """Return the nation linked to the current session, if any."""
    nation = request.session.get("linked_nation")
    if not nation:
        return JSONResponse({"linked": False})

    # Fetch fresh flag from GlobalNations.db to get latest updates
    nation_id = nation.get("nation_id")
    if nation_id and nation_id.isdigit():
        try:
            from PnWHarvester.db.global_nations_db import GlobalNationsDB
            from Systems.Functions.db_paths import GLOBAL_NATIONS_DB_STR
            gdb = GlobalNationsDB(GLOBAL_NATIONS_DB_STR)
            db_nation = await gdb.get_nation(int(nation_id))
            if db_nation and db_nation.get("flag"):
                nation["flag"] = db_nation["flag"]
                # Update session with fresh flag
                request.session["linked_nation"] = nation
        except Exception as e:
            logger.warning(f"Failed to fetch fresh flag from GlobalNations.db: {e}")

    return JSONResponse({"linked": True, **nation})

@router.delete("/discord/link-nation")
async def unlink_nation(request: Request):
    """Remove the linked nation from the current session."""
    request.session.pop("linked_nation", None)
    return JSONResponse({"ok": True})

@router.get("/discord/logout")
async def discord_logout(request: Request):
    """Logs the user out by clearing the session."""
    request.session.clear()
    return RedirectResponse(url='/dashboard.html')

@router.post("/discord/link-nation")
async def link_nation(request: Request):
    """Link a PnW nation ID to the current session (works with or without Discord login)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")
    nation_id = str(body.get("nation_id", "")).strip()
    if not nation_id.isdigit():
        raise HTTPException(status_code=400, detail="nation_id must be numeric.")
    nation_name = str(body.get("nation_name", "")).strip()
    flag = str(body.get("flag", "")).strip()
    request.session["linked_nation"] = {
        "nation_id": nation_id,
        "nation_name": nation_name,
        "flag": flag,
    }
    return JSONResponse({"ok": True, "nation_id": nation_id, "nation_name": nation_name, "flag": flag})

@router.get("/discord/linked-nation")
async def get_linked_nation(request: Request):
    """Return the nation linked to the current session, if any."""
    nation = request.session.get("linked_nation")
    if not nation:
        return JSONResponse({"linked": False})

    # Fetch fresh flag from GlobalNations.db to get latest updates
    nation_id = nation.get("nation_id")
    if nation_id and nation_id.isdigit():
        try:
            from PnWHarvester.db.global_nations_db import GlobalNationsDB
            from Systems.Functions.db_paths import GLOBAL_NATIONS_DB_STR
            gdb = GlobalNationsDB(GLOBAL_NATIONS_DB_STR)
            db_nation = await gdb.get_nation(int(nation_id))
            if db_nation and db_nation.get("flag"):
                nation["flag"] = db_nation["flag"]
                # Update session with fresh flag
                request.session["linked_nation"] = nation
        except Exception as e:
            logger.warning(f"Failed to fetch fresh flag from GlobalNations.db: {e}")

    return JSONResponse({"linked": True, **nation})

@router.delete("/discord/link-nation")
async def unlink_nation(request: Request):
    """Remove the linked nation from the current session."""
    request.session.pop("linked_nation", None)
    return JSONResponse({"ok": True})
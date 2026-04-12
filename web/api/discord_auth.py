
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import RedirectResponse, JSONResponse, StreamingResponse
from starlette.requests import Request
import asyncio
import os
import logging
import time
import requests
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
# Re-fetch profile from Discord at most once every 5 minutes
PROFILE_REFRESH_INTERVAL = 300

router = APIRouter()
logger = logging.getLogger("Reaper.DiscordAuthAPI")


def _refresh_access_token(refresh_token: str) -> dict | None:
    """Exchange a refresh token for a new access token. Returns token data or None."""
    try:
        r = requests.post(
            f'{API_ENDPOINT}/oauth2/token',
            data={
                'client_id': DISCORD_CLIENT_ID,
                'client_secret': DISCORD_CLIENT_SECRET,
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
            },
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=8,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning("Failed to refresh Discord access token: %s", e)
        return None


def _fetch_discord_user(access_token: str) -> dict | None:
    """Fetch the current user profile from Discord. Returns user dict or None."""
    try:
        r = requests.get(
            f'{API_ENDPOINT}/users/@me',
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=8,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning("Failed to fetch Discord user profile: %s", e)
        return None


@router.get("/discord/login")
async def discord_login():
    """Redirects the user to Discord's authorization page."""
    scopes = "identify email guilds"
    return RedirectResponse(
        f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={DISCORD_REDIRECT_URI}&response_type=code&scope={scopes}"
    )

@router.get("/discord/callback")
async def discord_callback(request: Request, code: str):
    """Handles the callback from Discord after authorization."""
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code not provided.")

    r = requests.post(
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

    user_info = _fetch_discord_user(access_token)
    if not user_info:
        raise HTTPException(status_code=502, detail="Could not fetch Discord user info.")

    request.session['discord_user'] = user_info
    request.session['discord_access_token'] = access_token
    request.session['discord_refresh_token'] = refresh_token
    request.session['discord_token_expires_at'] = int(time.time()) + expires_in
    request.session['discord_profile_fetched_at'] = int(time.time())

    return RedirectResponse(url='/dashboard.html')


@router.get("/discord/user")
async def get_discord_user(request: Request):
    """
    Returns the current Discord user, refreshing their profile from Discord
    if the cached copy is older than PROFILE_REFRESH_INTERVAL seconds.
    Automatically refreshes the access token if it has expired.
    """
    user = request.session.get('discord_user')
    if not user:
        return JSONResponse(content={'error': 'Not logged in'}, status_code=401)

    access_token: str | None = request.session.get('discord_access_token')
    refresh_token: str | None = request.session.get('discord_refresh_token')
    expires_at: int = request.session.get('discord_token_expires_at', 0)
    last_fetched: int = request.session.get('discord_profile_fetched_at', 0)
    now = int(time.time())

    # Refresh the access token if it has expired (or is about to in 60s)
    if access_token and expires_at and now >= expires_at - 60:
        if refresh_token:
            new_tokens = _refresh_access_token(refresh_token)
            if new_tokens:
                access_token = new_tokens['access_token']
                refresh_token = new_tokens.get('refresh_token', refresh_token)
                expires_in = int(new_tokens.get('expires_in', 604800))
                request.session['discord_access_token'] = access_token
                request.session['discord_refresh_token'] = refresh_token
                request.session['discord_token_expires_at'] = now + expires_in
            else:
                # Token refresh failed — clear session so user re-authenticates
                request.session.clear()
                return JSONResponse(content={'error': 'Not logged in'}, status_code=401)

    # Re-fetch profile if stale
    if access_token and (now - last_fetched) >= PROFILE_REFRESH_INTERVAL:
        fresh_user = _fetch_discord_user(access_token)
        if fresh_user:
            request.session['discord_user'] = fresh_user
            request.session['discord_profile_fetched_at'] = now
            user = fresh_user
        else:
            logger.warning("Profile refresh failed for user %s — serving cached copy", user.get('id'))

    return JSONResponse(content=user)


@router.get("/discord/avatar")
async def get_discord_avatar(request: Request):
    """
    Proxy the current user's Discord avatar through our server.
    Always uses the freshest avatar hash — re-fetches from Discord API
    if the CDN returns 404 (stale hash) before falling back to default.
    """
    user = request.session.get('discord_user')
    access_token = request.session.get('discord_access_token')

    if not user:
        raise HTTPException(status_code=401, detail="Not logged in.")

    # Refresh profile if we have a token — ensures hash is current
    if access_token:
        fresh = await asyncio.get_event_loop().run_in_executor(
            None, _fetch_discord_user, access_token
        )
        if fresh:
            request.session['discord_user'] = fresh
            request.session['discord_profile_fetched_at'] = int(time.time())
            user = fresh

    user_id = user.get('id')

    async def _serve_avatar(avatar_hash: str | None) -> Response:
        if not avatar_hash:
            default_index = (int(user_id) >> 22) % 6 if user_id else 0
            url = f"https://cdn.discordapp.com/embed/avatars/{default_index}.png"
            return RedirectResponse(url, status_code=302)

        ext = 'gif' if avatar_hash.startswith('a_') else 'png'
        cdn_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}?size=128"
        logger.info("Fetching avatar from CDN: %s", cdn_url)

        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(cdn_url)
            logger.info("CDN response: %s for %s", r.status_code, cdn_url)
            if r.status_code == 404:
                return None  # signal: hash is stale
            r.raise_for_status()
            content_type = r.headers.get('content-type', 'image/gif' if ext == 'gif' else 'image/png')
            return StreamingResponse(io.BytesIO(r.content), media_type=content_type)

    try:
        result = await _serve_avatar(user.get('avatar'))

        if result is None:
            # CDN 404 — hash is stale even after profile refresh.
            # Try once more with a forced re-fetch from Discord API.
            logger.warning(
                "Avatar hash stale for user %s (%s) — forcing re-fetch from Discord API",
                user_id, user.get('avatar')
            )
            if access_token:
                fresh = await asyncio.get_event_loop().run_in_executor(
                    None, _fetch_discord_user, access_token
                )
                if fresh and fresh.get('avatar') != user.get('avatar'):
                    request.session['discord_user'] = fresh
                    user = fresh
                    result = await _serve_avatar(fresh.get('avatar'))

            # Still None (hash genuinely missing) — serve default
            if result is None:
                default_index = (int(user_id) >> 22) % 6 if user_id else 0
                result = RedirectResponse(
                    f"https://cdn.discordapp.com/embed/avatars/{default_index}.png",
                    status_code=302
                )

        return result

    except httpx.HTTPStatusError as e:
        logger.warning("Avatar CDN returned error %s: %s", e.response.status_code, e)
        raise HTTPException(status_code=502, detail="Could not fetch avatar.")
    except Exception as e:
        logger.warning("Avatar proxy failed: %s", e)
        raise HTTPException(status_code=502, detail="Could not fetch avatar.")


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
    return JSONResponse({"linked": True, **nation})

@router.delete("/discord/link-nation")
async def unlink_nation(request: Request):
    """Remove the linked nation from the current session."""
    request.session.pop("linked_nation", None)
    return JSONResponse({"ok": True})

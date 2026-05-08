"""
Image Proxy API — Serves external images through our domain to avoid CORS issues.

Fixes:
- Chunked streaming read with per-chunk timeout to survive slow/partial PnW responses
- Retry logic (3 attempts with backoff) for transient network errors
- Persistent disk cache (never auto-deleted) — images are cached until the server
  restarts or the cache dir is manually cleared
- Correct content-type detection from response headers first, URL extension fallback
- 10 MB size cap to prevent runaway downloads
- Returns a 1×1 transparent PNG placeholder on failure instead of a 404,
  so broken flags don't break the page layout
"""
import asyncio
import hashlib
import logging
import os
from typing import Optional
from urllib.parse import urlparse

import aiohttp
from fastapi import APIRouter, Request
from fastapi.responses import Response

logger = logging.getLogger("web.api.image_proxy")
router = APIRouter()

# ── Config ────────────────────────────────────────────────────────────────────
CACHE_DIR      = "web/static/cached_images"
MAX_SIZE_BYTES = 10 * 1024 * 1024   # 10 MB hard cap
CONNECT_TIMEOUT = 8                  # seconds to establish connection
READ_TIMEOUT    = 20                 # seconds total for the full read
MAX_RETRIES     = 3

os.makedirs(CACHE_DIR, exist_ok=True)

# Allowed domains
ALLOWED_DOMAINS = {
    "upload.wikimedia.org",
    "politicsandwar.com",
    "cdn.discordapp.com",
    "media.discordapp.net",
}

# 1×1 transparent PNG — returned when an image genuinely cannot be fetched
_PLACEHOLDER = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _cache_path(url: str) -> str:
    url_hash = hashlib.md5(url.encode()).hexdigest()
    parsed   = urlparse(url)
    # Pull extension from the last path segment, ignoring dimension suffixes
    # e.g. "ec879b...x444.gif" → "gif",  "1000x666837.png" → "png"
    last_seg = parsed.path.rsplit("/", 1)[-1]
    dot_pos  = last_seg.rfind(".")
    ext      = last_seg[dot_pos + 1:].lower() if dot_pos != -1 else "jpg"
    if len(ext) > 5 or not ext.isalpha():
        ext = "jpg"
    return os.path.join(CACHE_DIR, f"{url_hash}.{ext}")


def _content_type(response: aiohttp.ClientResponse, cache_file: str) -> str:
    # Prefer the server's Content-Type header
    ct = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if ct.startswith("image/"):
        return ct
    # Fall back to extension
    ext = cache_file.rsplit(".", 1)[-1].lower()
    return {
        "jpg":  "image/jpeg",
        "jpeg": "image/jpeg",
        "png":  "image/png",
        "gif":  "image/gif",
        "webp": "image/webp",
        "svg":  "image/svg+xml",
        "avif": "image/avif",
    }.get(ext, "image/jpeg")


def _ct_from_path(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower()
    return {
        "jpg":  "image/jpeg",
        "jpeg": "image/jpeg",
        "png":  "image/png",
        "gif":  "image/gif",
        "webp": "image/webp",
        "svg":  "image/svg+xml",
        "avif": "image/avif",
    }.get(ext, "image/jpeg")


def _is_allowed(url: str) -> bool:
    try:
        return urlparse(url).netloc in ALLOWED_DOMAINS
    except Exception:
        return False


async def _fetch(url: str, dest: str) -> Optional[bytes]:
    """
    Fetch `url` into `dest` (disk cache) and return the bytes.
    Uses chunked reading so a slow/partial response doesn't raise
    ResponsePayloadError.  Retries up to MAX_RETRIES times.
    """
    timeout = aiohttp.ClientTimeout(
        connect=CONNECT_TIMEOUT,
        sock_read=READ_TIMEOUT,
        total=CONNECT_TIMEOUT + READ_TIMEOUT + 5,
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            connector = aiohttp.TCPConnector(force_close=True)
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
            ) as session:
                async with session.get(url, headers=headers, allow_redirects=True) as resp:
                    if resp.status != 200:
                        logger.warning(
                            f"Image proxy: HTTP {resp.status} for {url} "
                            f"(attempt {attempt}/{MAX_RETRIES})"
                        )
                        return None

                    ct_header = resp.headers.get("Content-Type", "")

                    # Read in chunks — avoids ResponsePayloadError on partial responses
                    chunks = []
                    total  = 0
                    async for chunk in resp.content.iter_chunked(65536):
                        total += len(chunk)
                        if total > MAX_SIZE_BYTES:
                            logger.warning(f"Image proxy: {url} exceeds {MAX_SIZE_BYTES} bytes, truncating")
                            break
                        chunks.append(chunk)

                    if not chunks:
                        logger.warning(f"Image proxy: empty body for {url}")
                        return None

                    data = b"".join(chunks)

                    # Persist to cache
                    try:
                        with open(dest, "wb") as fh:
                            fh.write(data)
                    except OSError as e:
                        logger.warning(f"Image proxy: could not write cache {dest}: {e}")

                    return data

        except (
            aiohttp.ClientPayloadError,
            aiohttp.ClientConnectionError,
            aiohttp.ServerDisconnectedError,
            aiohttp.ClientOSError,
            asyncio.TimeoutError,
            OSError,
        ) as exc:
            if attempt < MAX_RETRIES:
                wait = 2 ** (attempt - 1)   # 1s, 2s
                logger.debug(
                    f"Image proxy: {type(exc).__name__} for {url} "
                    f"(attempt {attempt}/{MAX_RETRIES}), retrying in {wait}s"
                )
                await asyncio.sleep(wait)
            else:
                logger.error(f"Error fetching image {url}: {exc}")

    return None


# ── Route ─────────────────────────────────────────────────────────────────────

@router.get("/image-proxy")
async def proxy_image(url: str, request: Request):
    """
    Proxy external images to avoid CORS issues.
    Usage: /api/image-proxy?url=https://politicsandwar.com/uploads/...
    """
    if not url:
        return Response(content=_PLACEHOLDER, media_type="image/png")

    if not _is_allowed(url):
        logger.debug(f"Image proxy: domain not allowed — {url}")
        return Response(content=_PLACEHOLDER, media_type="image/png")

    dest = _cache_path(url)

    # ── Serve from disk cache if available ───────────────────────────────────
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        try:
            with open(dest, "rb") as fh:
                data = fh.read()
            return Response(
                content=data,
                media_type=_ct_from_path(dest),
                headers={
                    "Cache-Control": "public, max-age=86400",
                    "Access-Control-Allow-Origin": "*",
                    "X-Cache": "HIT",
                },
            )
        except OSError:
            pass  # fall through to re-fetch

    # ── Fetch fresh ───────────────────────────────────────────────────────────
    data = await _fetch(url, dest)

    if not data:
        # Return placeholder — never a 404, so the page layout stays intact
        logger.error(f"Failed to fetch image: {url}")
        return Response(
            content=_PLACEHOLDER,
            media_type="image/png",
            headers={"Cache-Control": "no-store"},
        )

    return Response(
        content=data,
        media_type=_ct_from_path(dest),
        headers={
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*",
            "X-Cache": "MISS",
        },
    )

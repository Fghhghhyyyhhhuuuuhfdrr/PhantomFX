"""
bot/utils/shortlink.py
Wraps long stream/download URLs through a short-link API.
Currently supports: shareus.in, exe.io, gplinks.in (all share the same API shape).
"""

from __future__ import annotations

import logging
from typing import Optional

import aiohttp

from config.config import SHORTLINK_ENABLED, SHORTLINK_API, SHORTLINK_KEY

log = logging.getLogger(__name__)


async def shorten(url: str) -> str:
    """Return a shortened URL, or the original URL on failure/disabled."""
    if not SHORTLINK_ENABLED or not SHORTLINK_API or not SHORTLINK_KEY:
        return url

    api_url = f"https://{SHORTLINK_API}/api"
    params  = {"api": SHORTLINK_KEY, "url": url, "format": "json"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, params=params, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                data = await resp.json()
                # Most shortlink APIs return {"status":"success","shortenedUrl":"..."}
                if data.get("status") == "success":
                    return data.get("shortenedUrl") or data.get("short_url") or url
    except Exception as e:
        log.warning(f"Shortlink API error: {e}")

    return url

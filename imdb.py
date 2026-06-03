"""
bot/utils/imdb.py
Fetches movie/show details from IMDb using the `cinemagoer` library
(the maintained successor to IMDbPY).
"""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Optional, Dict, Any

log = logging.getLogger(__name__)

try:
    import imdb  # cinemagoer exposes itself as `imdb`
    _ia = imdb.Cinemagoer()
    IMDB_AVAILABLE = True
except ImportError:
    IMDB_AVAILABLE = False
    log.warning("cinemagoer not installed – IMDb lookups disabled. "
                "Install with:  pip install cinemagoer")


# ─────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────

async def fetch_imdb(title: str) -> Optional[Dict[str, Any]]:
    """
    Search IMDb for *title* and return a dict with the top hit's details,
    or None if nothing is found / cinemagoer not installed.
    Runs the blocking cinemagoer calls in a thread pool.
    """
    if not IMDB_AVAILABLE:
        return None
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, _blocking_search, title
        )
    except Exception as e:
        log.error(f"IMDb fetch error for '{title}': {e}")
        return None


def _blocking_search(title: str) -> Optional[Dict[str, Any]]:
    results = _ia.search_movie(title)
    if not results:
        return None

    movie = results[0]
    try:
        _ia.update(movie)  # fetch full details
    except Exception:
        pass

    def safe(key, default="N/A"):
        v = movie.get(key, default)
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v[:4])
        return v if v else default

    return {
        "title":     movie.get("title", title),
        "year":      movie.get("year", ""),
        "rating":    safe("rating"),
        "votes":     safe("votes"),
        "genres":    safe("genres"),
        "languages": safe("languages"),
        "runtime":   safe("runtimes"),
        "plot":      safe("plot outline") or safe("plot"),
        "poster":    _get_poster(movie),
        "imdb_id":   movie.movieID,
        "imdb_url":  f"https://www.imdb.com/title/tt{movie.movieID}/",
    }


def _get_poster(movie) -> Optional[str]:
    """Return the full-size cover URL if available."""
    try:
        return movie.get("full-size cover url") or movie.get("cover url")
    except Exception:
        return None

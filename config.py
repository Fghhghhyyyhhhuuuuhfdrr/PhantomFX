"""
MovieBot Configuration
All settings can be overridden via environment variables.
"""
import os
from typing import List

# ─────────────────────────────────────────────
#  REQUIRED – must be set before running
# ─────────────────────────────────────────────
API_ID: int         = int(os.environ.get("API_ID", 0))
API_HASH: str       = os.environ.get("API_HASH", "")
BOT_TOKEN: str      = os.environ.get("BOT_TOKEN", "")
MONGO_URI: str      = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
DATABASE_NAME: str  = os.environ.get("DATABASE_NAME", "MovieBot")
OWNER_ID: int       = int(os.environ.get("OWNER_ID", 0))

# ─────────────────────────────────────────────
#  CHANNELS / GROUPS
# ─────────────────────────────────────────────
# Space-separated list of channel/group IDs to index files from
FILE_CHANNELS: List[int] = [
    int(x) for x in os.environ.get("FILE_CHANNELS", "").split()
    if x.strip()
]

# Channel where all bot activity is logged
LOG_CHANNEL: int = int(os.environ.get("LOG_CHANNEL", 0))

# Admins (space-separated Telegram user IDs)
ADMINS: List[int] = [
    int(x) for x in os.environ.get("ADMINS", str(OWNER_ID)).split()
    if x.strip()
]

# ─────────────────────────────────────────────
#  FORCE SUBSCRIPTION
# ─────────────────────────────────────────────
FORCE_SUB_CHANNEL: int  = int(os.environ.get("FORCE_SUB_CHANNEL", 0))
FORCE_SUB_GROUP: int    = int(os.environ.get("FORCE_SUB_GROUP", 0))
FORCE_SUB_ENABLED: bool = bool(int(os.environ.get("FORCE_SUB_ENABLED", 0)))

# ─────────────────────────────────────────────
#  STREAMING / DOWNLOAD
# ─────────────────────────────────────────────
# Base URL of the web server used for streaming & fast-download links
# e.g. https://yourapp.onrender.com  or  http://your-vps-ip:8080
STREAM_BASE_URL: str = os.environ.get("STREAM_BASE_URL", "http://localhost:8080")
PORT: int            = int(os.environ.get("PORT", 8080))

# Whether to use the self-hosted local Telegram Bot API server
# Required for files > 2 GB
USE_LOCAL_API: bool       = bool(int(os.environ.get("USE_LOCAL_API", 0)))
LOCAL_API_URL: str        = os.environ.get("LOCAL_API_URL", "http://localhost:8081")

# ─────────────────────────────────────────────
#  IMDB
# ─────────────────────────────────────────────
IMDB_ENABLED: bool     = bool(int(os.environ.get("IMDB_ENABLED", 1)))
IMDB_TEMPLATE: str     = os.environ.get(
    "IMDB_TEMPLATE",
    "<b>{title}</b>  ({year})\n"
    "⭐ <b>IMDb:</b> <code>{rating}/10</code>  |  🗳 <b>Votes:</b> {votes}\n"
    "🎭 <b>Genre:</b> {genres}\n"
    "🌐 <b>Languages:</b> {languages}\n"
    "🕒 <b>Runtime:</b> {runtime} min\n\n"
    "📖 <b>Plot:</b> <i>{plot}</i>",
)

# ─────────────────────────────────────────────
#  AUTO-DELETE
# ─────────────────────────────────────────────
AUTO_DELETE_ENABLED: bool = bool(int(os.environ.get("AUTO_DELETE_ENABLED", 1)))
AUTO_DELETE_TIME: int     = int(os.environ.get("AUTO_DELETE_TIME", 300))   # seconds

# ─────────────────────────────────────────────
#  FILE PROTECTION (copy-protection)
# ─────────────────────────────────────────────
FILE_PROTECT: bool       = bool(int(os.environ.get("FILE_PROTECT", 1)))
FORWARD_RESTRICT: bool   = bool(int(os.environ.get("FORWARD_RESTRICT", 1)))

# ─────────────────────────────────────────────
#  SEARCH
# ─────────────────────────────────────────────
MAX_RESULTS: int       = int(os.environ.get("MAX_RESULTS", 10))
SPELL_CHECK: bool      = bool(int(os.environ.get("SPELL_CHECK", 1)))

# ─────────────────────────────────────────────
#  SHORTLINKS
# ─────────────────────────────────────────────
SHORTLINK_ENABLED: bool = bool(int(os.environ.get("SHORTLINK_ENABLED", 0)))
SHORTLINK_API: str      = os.environ.get("SHORTLINK_API", "")   # e.g. api.shareus.in
SHORTLINK_KEY: str      = os.environ.get("SHORTLINK_KEY", "")

# ─────────────────────────────────────────────
#  TUTORIAL VIDEO
# ─────────────────────────────────────────────
TUTORIAL_VIDEO: str = os.environ.get("TUTORIAL_VIDEO", "")  # Telegram file_id or URL

# ─────────────────────────────────────────────
#  WELCOME / START MESSAGE
# ─────────────────────────────────────────────
START_PIC: str = os.environ.get(
    "START_PIC",
    "https://telegra.ph/file/your-banner.jpg",   # Replace with your banner Telegraph URL
)
START_MSG: str = os.environ.get(
    "START_MSG",
    "👋 <b>Welcome to MovieBot!</b>\n\n"
    "🔍 Search for movies or series just by typing their name here or in any connected group.\n"
    "🍿 I'll find matching files from our collection and give you stream & download buttons.\n\n"
    "Use /help to see all commands.",
)

# ─────────────────────────────────────────────
#  PREMIUM
# ─────────────────────────────────────────────
PREMIUM_ENABLED: bool = bool(int(os.environ.get("PREMIUM_ENABLED", 1)))

# ─────────────────────────────────────────────
#  LOW-QUALITY FILE FILTER  (CAMRip, PreDVD …)
# ─────────────────────────────────────────────
BAD_QUALITY_TAGS: List[str] = [
    "camrip", "cam-rip", "cam rip", "hdcam",
    "predvd", "pre-dvd", "dvdscr", "scr",
    "ts-rip", "tsrip", "telesync", "ppvrip",
    "workprint", "wp", "r5", "hc hdrip",
]
AUTO_FILTER_BAD: bool = bool(int(os.environ.get("AUTO_FILTER_BAD", 0)))

# ─────────────────────────────────────────────
#  INLINE CACHE
# ─────────────────────────────────────────────
CACHE_TIME: int = int(os.environ.get("CACHE_TIME", 300))

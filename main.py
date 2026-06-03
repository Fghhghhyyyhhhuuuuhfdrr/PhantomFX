"""
main.py
MovieBot entry point.
Starts the Pyrogram client, the aiohttp stream server, and loads all handlers.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import os

# ── Logging setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("MovieBot")

# ── Config validation ─────────────────────────────────────────────────────────
from config.config import API_ID, API_HASH, BOT_TOKEN, MONGO_URI, OWNER_ID

_required = {
    "API_ID":    API_ID,
    "API_HASH":  API_HASH,
    "BOT_TOKEN": BOT_TOKEN,
    "MONGO_URI": MONGO_URI,
    "OWNER_ID":  OWNER_ID,
}
_missing = [k for k, v in _required.items() if not v]
if _missing:
    log.error(f"Missing required environment variables: {', '.join(_missing)}")
    sys.exit(1)

# ── Pyrogram client ───────────────────────────────────────────────────────────
from pyrogram import Client
from config.config import USE_LOCAL_API, LOCAL_API_URL

client_kwargs = dict(
    name        = "MovieBot",
    api_id      = API_ID,
    api_hash    = API_HASH,
    bot_token   = BOT_TOKEN,
    plugins     = {"root": "bot/handlers"},
    workers     = 4,
)

if USE_LOCAL_API:
    client_kwargs["api_server_address"] = LOCAL_API_URL

bot = Client(**client_kwargs)

# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    from bot.database import db as database
    from bot.utils.stream_server import start_server

    log.info("Connecting to MongoDB…")
    await database.connect()

    log.info("Starting stream server…")
    await start_server()

    log.info("Starting Telegram bot…")
    await bot.start()

    me = await bot.get_me()
    log.info(f"Bot started as @{me.username} (ID: {me.id})")

    # Notify owner
    try:
        await bot.send_message(OWNER_ID, f"✅ <b>MovieBot started!</b>\n@{me.username}")
    except Exception:
        pass

    # Keep running
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Bot stopped by user.")

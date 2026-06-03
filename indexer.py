"""
bot/handlers/indexer.py
Listens for new media posted to connected channels and indexes them in real time.
Also handles the channel_post event so forwarded files are captured automatically.
"""

from __future__ import annotations

import logging

from pyrogram import Client, filters
from pyrogram.types import Message

from config.config import FILE_CHANNELS
from bot.database import db
from bot.utils.helpers import file_from_message, log_activity

log = logging.getLogger(__name__)


def _is_file_channel(_, __, message: Message) -> bool:
    return message.chat.id in FILE_CHANNELS


file_channel_filter = filters.create(_is_file_channel)


@Client.on_message(
    (filters.video | filters.document | filters.audio)
    & file_channel_filter
    & ~filters.private
)
async def auto_index(client: Client, message: Message):
    fdata = file_from_message(message)
    if not fdata:
        return

    inserted = await db.save_file(fdata)
    action   = "📥 New file indexed" if inserted else "🔄 File updated"
    log.info(f"{action}: {fdata['file_name']}")
    await log_activity(
        client,
        f"{action}: <code>{fdata['file_name']}</code>\n"
        f"Size: {fdata['file_size'] / 1048576:.1f} MB | "
        f"Channel: <code>{message.chat.id}</code>"
    )

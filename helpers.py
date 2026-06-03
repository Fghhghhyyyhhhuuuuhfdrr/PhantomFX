"""
bot/utils/helpers.py
Shared utilities used across handlers.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from datetime import datetime
from typing import List, Optional, Dict, Any

from pyrogram import Client
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ChatMember,
)
from pyrogram.errors import (
    UserNotParticipant,
    ChatAdminRequired,
    PeerIdInvalid,
    FloodWait,
)

from config.config import (
    FORCE_SUB_ENABLED, FORCE_SUB_CHANNEL, FORCE_SUB_GROUP,
    AUTO_DELETE_ENABLED, AUTO_DELETE_TIME,
    FILE_PROTECT, FORWARD_RESTRICT,
    IMDB_TEMPLATE, BAD_QUALITY_TAGS,
    LOG_CHANNEL,
)
from bot.database import db
from bot.utils.imdb import fetch_imdb
from bot.utils.stream_server import make_stream_url, make_download_url
from bot.utils.shortlink import shorten

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
#  Force Subscription
# ─────────────────────────────────────────────────────────

async def check_force_sub(client: Client, user_id: int) -> Optional[str]:
    """
    Returns None if all good, or an invite URL string if the user
    still needs to subscribe.
    """
    if not FORCE_SUB_ENABLED:
        return None

    for chat_id in filter(None, [FORCE_SUB_CHANNEL, FORCE_SUB_GROUP]):
        try:
            member = await client.get_chat_member(chat_id, user_id)
            if member.status.name in ("LEFT", "BANNED", "KICKED"):
                raise UserNotParticipant
        except UserNotParticipant:
            try:
                link = await client.export_chat_invite_link(chat_id)
            except Exception:
                link = "https://t.me"
            return link
        except Exception:
            pass

    return None


async def send_force_sub_message(client: Client, message: Message, invite_url: str):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Join & Continue", url=invite_url),
    ]])
    await message.reply(
        "⚠️ <b>Access Restricted!</b>\n\n"
        "You must join our channel/group to use this bot.\n"
        "Click the button below, join, then try again.",
        reply_markup=keyboard,
    )


# ─────────────────────────────────────────────────────────
#  File Indexer
# ─────────────────────────────────────────────────────────

def extract_quality_tag(text: str) -> Optional[str]:
    text_l = text.lower()
    for tag in BAD_QUALITY_TAGS:
        if tag in text_l:
            return tag
    # known good tags
    for tag in ["2160p", "4k", "1080p", "720p", "480p", "360p",
                "bluray", "webrip", "web-dl", "hdtv", "dvdrip", "hdrip"]:
        if tag in text_l:
            return tag
    return None


def file_from_message(msg: Message) -> Optional[Dict[str, Any]]:
    """
    Extract a file document dict from a Pyrogram Message.
    Returns None if the message has no supported media.
    """
    media = msg.video or msg.document or msg.audio
    if not media:
        return None

    caption = msg.caption or ""
    file_name = getattr(media, "file_name", "") or caption or f"file_{media.file_id[:8]}"

    return {
        "file_id":    media.file_id,
        "file_ref":   media.file_unique_id,
        "file_name":  file_name,
        "file_size":  getattr(media, "file_size", 0) or 0,
        "file_type":  "video" if msg.video else ("audio" if msg.audio else "document"),
        "mime_type":  getattr(media, "mime_type", ""),
        "caption":    caption,
        "channel_id": msg.chat.id,
        "message_id": msg.id,
        "quality_tag": extract_quality_tag(file_name + " " + caption),
        "indexed_at": datetime.utcnow(),
    }


async def index_channel(client: Client, channel_id: int) -> tuple[int, int]:
    """
    Iterate the channel's history and index every media message.
    Returns (new_count, updated_count).
    """
    new_count = updated_count = 0
    async for msg in client.get_chat_history(channel_id):
        fdata = file_from_message(msg)
        if fdata:
            inserted = await db.save_file(fdata)
            if inserted:
                new_count += 1
            else:
                updated_count += 1
    return new_count, updated_count


# ─────────────────────────────────────────────────────────
#  Search Result Keyboards
# ─────────────────────────────────────────────────────────

async def make_file_buttons(
    file_id: str, file_size: int, file_name: str
) -> InlineKeyboardMarkup:
    stream_url   = await shorten(make_stream_url(file_id, file_size))
    download_url = await shorten(make_download_url(file_id, file_size))

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("▶️ Stream Online", url=stream_url),
            InlineKeyboardButton("⚡ Fast Download", url=download_url),
        ],
        [
            InlineKeyboardButton("ℹ️ File Info", callback_data=f"info#{file_id}"),
        ],
    ])


async def build_search_result_text(
    file_doc: Dict[str, Any], imdb_data: Optional[Dict] = None
) -> str:
    name      = html.escape(file_doc.get("file_name", "Unknown"))
    size_mb   = file_doc.get("file_size", 0) / (1024 * 1024)
    size_str  = f"{size_mb:.0f} MB" if size_mb < 1024 else f"{size_mb/1024:.2f} GB"
    q_tag     = file_doc.get("quality_tag") or "Unknown"

    lines = [f"🎬 <b>{name}</b>", f"📦 Size: <code>{size_str}</code>  |  🎞 Quality: <code>{q_tag}</code>"]

    if imdb_data:
        lines.append("")
        lines.append(IMDB_TEMPLATE.format(**{k: html.escape(str(v)) for k, v in imdb_data.items()}))

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────
#  Auto-delete
# ─────────────────────────────────────────────────────────

async def schedule_delete(client: Client, chat_id: int, message_ids: List[int]):
    if not AUTO_DELETE_ENABLED:
        return
    await asyncio.sleep(AUTO_DELETE_TIME)
    try:
        await client.delete_messages(chat_id, message_ids)
    except Exception as e:
        log.debug(f"Auto-delete failed: {e}")


# ─────────────────────────────────────────────────────────
#  Broadcast
# ─────────────────────────────────────────────────────────

async def broadcast_message(
    client: Client, message: Message, target: str = "users"
) -> Dict[str, int]:
    """
    target = 'users' | 'groups'
    Returns {"sent": n, "failed": n}
    """
    if target == "users":
        ids = await db.all_user_ids()
    else:
        ids = await db.all_group_ids()

    sent = failed = 0
    for chat_id in ids:
        try:
            await message.copy(chat_id)
            sent += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            try:
                await message.copy(chat_id)
                sent += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)   # ~20 msg/s – well within Telegram limits

    return {"sent": sent, "failed": failed}


# ─────────────────────────────────────────────────────────
#  Logging
# ─────────────────────────────────────────────────────────

async def log_activity(client: Client, text: str):
    if LOG_CHANNEL:
        try:
            await client.send_message(LOG_CHANNEL, text, disable_web_page_preview=True)
        except Exception as e:
            log.debug(f"Log channel error: {e}")


# ─────────────────────────────────────────────────────────
#  Misc
# ─────────────────────────────────────────────────────────

def human_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def clean_title(file_name: str) -> str:
    """Strip resolution/codec tags from a filename to get a clean search title."""
    name = re.sub(r"\.\w{2,4}$", "", file_name)           # remove extension
    name = re.sub(r"[\._\-]", " ", name)                   # separators → spaces
    name = re.sub(
        r"\b(480p|720p|1080p|2160p|4k|bluray|webrip|web-dl|hdtv|"
        r"dvdrip|hdrip|x264|x265|hevc|avc|aac|mp4|mkv|avi)\b",
        "", name, flags=re.IGNORECASE,
    )
    name = re.sub(r"\s{2,}", " ", name).strip()
    return name

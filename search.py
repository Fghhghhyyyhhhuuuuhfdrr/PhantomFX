"""
bot/handlers/search.py
Handles:
  - Group text messages → auto-filter search
  - Private /search command
  - Inline queries (@bot <title>)
"""

from __future__ import annotations

import asyncio
import html
import logging
from typing import List, Dict, Any

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    CallbackQuery,
)

from config.config import (
    MAX_RESULTS, IMDB_ENABLED, CACHE_TIME,
    FILE_PROTECT, ADMINS,
)
from bot.database import db
from bot.utils.helpers import (
    check_force_sub, send_force_sub_message,
    make_file_buttons, build_search_result_text,
    schedule_delete, clean_title, human_size, log_activity,
)
from bot.utils.imdb import fetch_imdb

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────
#  Group auto-filter
# ─────────────────────────────────────────────────────────

@Client.on_message(
    filters.text
    & ~filters.private
    & ~filters.bot
    & ~filters.command(["start", "help", "stats", "index", "broadcast",
                         "ban", "unban", "settings", "deletebad",
                         "addpremium", "removepremium", "addchannel",
                         "removechannel", "plan"])
)
async def group_search(client: Client, message: Message):
    query = message.text.strip()
    if len(query) < 2:
        return

    user_id = message.from_user.id if message.from_user else 0

    # Ban check
    if user_id and await db.is_banned(user_id):
        return

    # Force sub
    if user_id:
        invite = await check_force_sub(client, user_id)
        if invite:
            await send_force_sub_message(client, message, invite)
            return

    results, total = await db.search_files(query, limit=MAX_RESULTS)
    if not results:
        # Try fuzzy (already handled inside search_files fallback)
        pass

    if not results:
        return   # silent in groups – don't spam "not found"

    if user_id:
        await db.increment_search(user_id)

    await _send_results(client, message, results, total, query)


# ─────────────────────────────────────────────────────────
#  Private /search command
# ─────────────────────────────────────────────────────────

@Client.on_message(filters.command("search") & filters.private)
async def private_search(client: Client, message: Message):
    user = message.from_user

    if await db.is_banned(user.id):
        await message.reply("🚫 You are banned from using this bot.")
        return

    invite = await check_force_sub(client, user.id)
    if invite:
        await send_force_sub_message(client, message, invite)
        return

    args = message.command[1:]
    if not args:
        await message.reply("Usage: /search <movie title>")
        return

    query = " ".join(args)
    results, total = await db.search_files(query, limit=MAX_RESULTS)

    if not results:
        await message.reply(
            f"😕 No results found for <b>{html.escape(query)}</b>.\n"
            "Try a different spelling or a shorter title."
        )
        return

    await db.increment_search(user.id)
    await _send_results(client, message, results, total, query)


# ─────────────────────────────────────────────────────────
#  Inline query
# ─────────────────────────────────────────────────────────

@Client.on_inline_query()
async def inline_search(client: Client, query: InlineQuery):
    search = query.query.strip()
    if not search:
        await query.answer(
            [],
            switch_pm_text="Type a movie name to search…",
            switch_pm_parameter="start",
            cache_time=0,
        )
        return

    results, _ = await db.search_files(search, limit=8)
    if not results:
        await query.answer(
            [],
            switch_pm_text="No results – try a different title",
            switch_pm_parameter="start",
            cache_time=CACHE_TIME,
        )
        return

    inline_results = []
    for f in results:
        name     = f.get("file_name", "Unknown")
        size_str = human_size(f.get("file_size", 0))
        q_tag    = f.get("quality_tag") or "?"
        file_id  = f["file_id"]

        inline_results.append(
            InlineQueryResultArticle(
                title=name,
                description=f"{size_str} | {q_tag}",
                input_message_content=InputTextMessageContent(
                    f"🔍 Searching for: <b>{html.escape(name)}</b>\n"
                    f"📦 {size_str} | 🎞 {q_tag}"
                ),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        "📥 Get File",
                        url=f"https://t.me/{(await client.get_me()).username}?start=file_{file_id}",
                    )
                ]]),
            )
        )

    await query.answer(inline_results, cache_time=CACHE_TIME)


# ─────────────────────────────────────────────────────────
#  File info callback
# ─────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^info#(.+)$"))
async def file_info_callback(client: Client, query: CallbackQuery):
    file_id  = query.data.split("#", 1)[1]
    file_doc = await db.get_file(file_id)
    if not file_doc:
        await query.answer("File no longer available.", show_alert=True)
        return

    name     = file_doc.get("file_name", "N/A")
    size_str = human_size(file_doc.get("file_size", 0))
    mime     = file_doc.get("mime_type", "N/A")
    indexed  = file_doc.get("indexed_at", "N/A")
    if hasattr(indexed, "strftime"):
        indexed = indexed.strftime("%d %b %Y")

    text = (
        f"📄 <b>File Info</b>\n\n"
        f"📛 Name: <code>{html.escape(name)}</code>\n"
        f"📦 Size: {size_str}\n"
        f"🎞 Type: {mime}\n"
        f"📅 Indexed: {indexed}"
    )
    await query.answer(text, show_alert=True)


# ─────────────────────────────────────────────────────────
#  Pagination callback
# ─────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex(r"^page#(.+)#(\d+)$"))
async def page_callback(client: Client, query: CallbackQuery):
    _, search_query, page_str = query.data.split("#")
    page   = int(page_str)
    offset = page * MAX_RESULTS

    results, total = await db.search_files(search_query, offset=offset, limit=MAX_RESULTS)
    if not results:
        await query.answer("No more results.", show_alert=True)
        return

    await query.message.delete()
    await _send_results(client, query.message, results, total, search_query, page=page)
    await query.answer()


# ─────────────────────────────────────────────────────────
#  Internal: render search results
# ─────────────────────────────────────────────────────────

async def _send_results(
    client: Client,
    message: Message,
    results: List[Dict],
    total: int,
    query: str,
    page: int = 0,
):
    sent_ids = []

    # Header
    header = await message.reply(
        f"🔎 Found <b>{total}</b> result(s) for <b>{html.escape(query)}</b>"
    )
    sent_ids.append(header.id)

    for file_doc in results:
        file_name = file_doc.get("file_name", "Unknown")
        file_size = file_doc.get("file_size", 0)
        file_id   = file_doc["file_id"]

        # IMDb lookup for videos
        imdb_data = None
        if IMDB_ENABLED and file_doc.get("file_type") == "video":
            title     = clean_title(file_name)
            imdb_data = await fetch_imdb(title) if title else None

        caption  = await build_search_result_text(file_doc, imdb_data)
        keyboard = await make_file_buttons(file_id, file_size, file_name)

        try:
            sent = await client.send_cached_media(
                message.chat.id,
                file_id=file_id,
                caption=caption,
                reply_markup=keyboard,
                protect_content=FILE_PROTECT,
            )
            sent_ids.append(sent.id)
        except Exception as e:
            log.warning(f"Could not send cached media {file_id}: {e}")
            fallback = await message.reply(caption, reply_markup=keyboard)
            sent_ids.append(fallback.id)

    # Pagination
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Prev", callback_data=f"page#{query}#{page-1}"))
    if (page + 1) * MAX_RESULTS < total:
        nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"page#{query}#{page+1}"))

    if nav_buttons:
        nav = await message.reply(
            f"Page {page+1} / {(total // MAX_RESULTS) + 1}",
            reply_markup=InlineKeyboardMarkup([nav_buttons]),
        )
        sent_ids.append(nav.id)

    # Schedule auto-delete
    asyncio.create_task(schedule_delete(client, message.chat.id, sent_ids))

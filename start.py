"""
bot/handlers/start.py
/start, /help, /plan commands
"""

from __future__ import annotations

from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

from config.config import (
    START_MSG, START_PIC, TUTORIAL_VIDEO, ADMINS, OWNER_ID, PREMIUM_ENABLED
)
from bot.database import db
from bot.utils.helpers import check_force_sub, send_force_sub_message, log_activity


# ── /start ───────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user  = message.from_user
    await db.add_user(user.id, user.first_name, user.username or "")

    # Force sub check
    invite = await check_force_sub(client, user.id)
    if invite:
        await send_force_sub_message(client, message, invite)
        return

    # /start <deep-link token>  → file request
    args = message.command[1:]
    if args:
        await _handle_deep_link(client, message, args[0])
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔍 Search Files", switch_inline_query_current_chat=""),
            InlineKeyboardButton("📖 Help", callback_data="help"),
        ],
        [
            InlineKeyboardButton("👑 My Plan", callback_data="myplan"),
            InlineKeyboardButton("🎬 Tutorial", callback_data="tutorial"),
        ],
        [
            InlineKeyboardButton("➕ Add me to Group", url=f"https://t.me/{(await client.get_me()).username}?startgroup=true"),
        ],
    ])

    if START_PIC:
        await message.reply_photo(START_PIC, caption=START_MSG, reply_markup=keyboard)
    else:
        await message.reply(START_MSG, reply_markup=keyboard)

    await log_activity(client, f"#NEW_USER\n👤 {user.first_name} | `{user.id}`")


# ── Deep-link file delivery ───────────────────────────────────────────────────

async def _handle_deep_link(client: Client, message: Message, token: str):
    """Resolve a /start <file_id> deep-link and send the file to the user."""
    # Token format: "file_<file_id_hash>" – set in search handler
    file_id   = token.replace("file_", "")
    file_doc  = await db.get_file(file_id)
    if not file_doc:
        await message.reply("❌ File not found or has been removed.")
        return

    from bot.utils.helpers import make_file_buttons, build_search_result_text
    from bot.utils.imdb import fetch_imdb
    from bot.utils.helpers import clean_title

    imdb_data = None
    if file_doc.get("file_type") == "video":
        title     = clean_title(file_doc.get("file_name", ""))
        imdb_data = await fetch_imdb(title) if title else None

    caption   = await build_search_result_text(file_doc, imdb_data)
    keyboard  = await make_file_buttons(
        file_doc["file_id"],
        file_doc.get("file_size", 0),
        file_doc.get("file_name", ""),
    )

    from config.config import FILE_PROTECT
    sent = await client.send_cached_media(
        message.chat.id,
        file_id=file_doc["file_id"],
        caption=caption,
        reply_markup=keyboard,
        protect_content=FILE_PROTECT,
    )

    # Auto-delete
    from bot.utils.helpers import schedule_delete
    import asyncio
    asyncio.create_task(schedule_delete(client, message.chat.id, [sent.id]))


# ── /help ────────────────────────────────────────────────────────────────────

HELP_TEXT = """
<b>📚 MovieBot Commands</b>

<b>👤 User Commands</b>
/start – Start the bot
/help – Show this message
/plan – Check your subscription plan
/search &lt;title&gt; – Search for a movie/series

<b>🛡 Admin Commands</b>
/index – Index all files from connected channels
/addchannel &lt;id&gt; – Connect a new channel/group
/removechannel &lt;id&gt; – Disconnect a channel/group
/ban &lt;user_id&gt; [reason] – Ban a user
/unban &lt;user_id&gt; – Unban a user
/broadcast &lt;users|groups&gt; – Broadcast a message
/stats – Bot statistics
/settings – View/edit settings
/deletebad – Delete CAMRip/PreDVD files
/addpremium &lt;user_id&gt; &lt;days&gt; – Add premium
/removepremium &lt;user_id&gt; – Remove premium

<b>🔍 Search Tips</b>
• Type a movie name in any connected group
• Use inline mode: @BotName &lt;title&gt;
• Typos are handled automatically

<b>🔗 File Buttons</b>
▶️ Stream Online – Watch in browser instantly
⚡ Fast Download – Direct download link
"""


@Client.on_message(filters.command("help"))
async def help_handler(client: Client, message: Message):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Back", callback_data="start")
    ]])
    await message.reply(HELP_TEXT, reply_markup=kb, disable_web_page_preview=True)


# ── /plan ────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("plan") & filters.private)
async def plan_handler(client: Client, message: Message):
    user_id = message.from_user.id
    if not PREMIUM_ENABLED:
        await message.reply("ℹ️ Premium membership is not enabled on this bot.")
        return

    prem = await db.get_premium_info(user_id)
    if prem and prem["expiry"] > datetime.utcnow():
        days_left = (prem["expiry"] - datetime.utcnow()).days
        text = (
            "👑 <b>Premium Member</b>\n\n"
            f"📅 Expires: <code>{prem['expiry'].strftime('%d %b %Y')}</code>\n"
            f"⏳ Days Left: <b>{days_left}</b>\n\n"
            "✅ You have access to all premium features."
        )
    else:
        text = (
            "🆓 <b>Free Plan</b>\n\n"
            "You're currently on the Free plan.\n"
            "Contact an admin to upgrade to Premium."
        )
    await message.reply(text)


# ── Callback buttons ──────────────────────────────────────────────────────────

@Client.on_callback_query(filters.regex("^help$"))
async def cb_help(client: Client, query: CallbackQuery):
    await query.message.edit_text(HELP_TEXT, disable_web_page_preview=True)


@Client.on_callback_query(filters.regex("^start$"))
async def cb_start(client: Client, query: CallbackQuery):
    await query.message.edit_text(START_MSG)


@Client.on_callback_query(filters.regex("^myplan$"))
async def cb_plan(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    prem = await db.get_premium_info(user_id)
    if prem and prem["expiry"] > datetime.utcnow():
        days_left = (prem["expiry"] - datetime.utcnow()).days
        text = f"👑 <b>Premium Member</b>\n📅 Expires: {prem['expiry'].strftime('%d %b %Y')}\n⏳ {days_left} days left"
    else:
        text = "🆓 <b>Free Plan</b>\nContact an admin to upgrade."
    await query.answer(text, show_alert=True)


@Client.on_callback_query(filters.regex("^tutorial$"))
async def cb_tutorial(client: Client, query: CallbackQuery):
    if TUTORIAL_VIDEO:
        await query.message.reply_video(
            TUTORIAL_VIDEO,
            caption="🎬 <b>How to use MovieBot</b>",
        )
    else:
        await query.answer("Tutorial video not set up yet.", show_alert=True)

"""
bot/handlers/admin.py
All admin-only commands:
  /index, /addchannel, /removechannel
  /ban, /unban
  /broadcast
  /stats
  /settings
  /deletebad
  /addpremium, /removepremium
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)

from config.config import ADMINS, OWNER_ID, BAD_QUALITY_TAGS
from bot.database import db
from bot.utils.helpers import (
    index_channel, broadcast_message, log_activity, human_size
)

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
#  Admin filter
# ─────────────────────────────────────────────────────────

def is_admin(_, __, message: Message) -> bool:
    uid = message.from_user.id if message.from_user else 0
    return uid in ADMINS or uid == OWNER_ID


admin_filter = filters.create(is_admin)


# ─────────────────────────────────────────────────────────
#  /stats
# ─────────────────────────────────────────────────────────

@Client.on_message(filters.command("stats") & admin_filter)
async def stats_handler(client: Client, message: Message):
    users   = await db.total_users()
    groups  = await db.total_groups()
    files   = await db.total_files()
    premium = await db.total_premium()

    text = (
        "📊 <b>Bot Statistics</b>\n\n"
        f"👤 Total Users:   <b>{users:,}</b>\n"
        f"👥 Connected Groups: <b>{groups:,}</b>\n"
        f"🎬 Indexed Files: <b>{files:,}</b>\n"
        f"👑 Premium Users: <b>{premium:,}</b>\n"
    )
    await message.reply(text)


# ─────────────────────────────────────────────────────────
#  /index
# ─────────────────────────────────────────────────────────

@Client.on_message(filters.command("index") & admin_filter)
async def index_handler(client: Client, message: Message):
    from config.config import FILE_CHANNELS

    if not FILE_CHANNELS:
        await message.reply("⚠️ No FILE_CHANNELS configured.")
        return

    status = await message.reply("🔄 Indexing channels… this may take a while.")
    total_new = total_upd = 0

    for ch_id in FILE_CHANNELS:
        try:
            new, upd = await index_channel(client, ch_id)
            total_new += new
            total_upd += upd
            await status.edit_text(
                f"✅ Channel <code>{ch_id}</code>\n"
                f"   New: {new} | Updated: {upd}"
            )
        except Exception as e:
            await status.edit_text(f"❌ Error indexing {ch_id}: {e}")

    await status.edit_text(
        f"✅ <b>Indexing complete!</b>\n"
        f"New files: <b>{total_new}</b> | Updated: <b>{total_upd}</b>"
    )
    await log_activity(client, f"#INDEX ✅ New:{total_new} Updated:{total_upd} by `{message.from_user.id}`")


# ─────────────────────────────────────────────────────────
#  Channel management
# ─────────────────────────────────────────────────────────

@Client.on_message(filters.command("addchannel") & admin_filter)
async def add_channel_handler(client: Client, message: Message):
    args = message.command[1:]
    if not args:
        await message.reply("Usage: /addchannel <channel_id or @username>")
        return

    try:
        chat = await client.get_chat(args[0])
        # Save to settings
        channels = await db.get_setting("file_channels") or []
        if chat.id not in channels:
            channels.append(chat.id)
            await db.set_setting("file_channels", channels)
        await message.reply(
            f"✅ Channel <b>{chat.title}</b> (<code>{chat.id}</code>) added.\n"
            "Run /index to index its files."
        )
    except Exception as e:
        await message.reply(f"❌ Error: {e}")


@Client.on_message(filters.command("removechannel") & admin_filter)
async def remove_channel_handler(client: Client, message: Message):
    args = message.command[1:]
    if not args:
        await message.reply("Usage: /removechannel <channel_id>")
        return

    try:
        ch_id     = int(args[0])
        channels  = await db.get_setting("file_channels") or []
        if ch_id in channels:
            channels.remove(ch_id)
            await db.set_setting("file_channels", channels)
            await message.reply(f"✅ Channel <code>{ch_id}</code> removed.")
        else:
            await message.reply("ℹ️ Channel not found in the list.")
    except ValueError:
        await message.reply("❌ Invalid channel ID.")


# ─────────────────────────────────────────────────────────
#  Ban / Unban
# ─────────────────────────────────────────────────────────

@Client.on_message(filters.command("ban") & admin_filter)
async def ban_handler(client: Client, message: Message):
    args = message.command[1:]
    if not args:
        await message.reply("Usage: /ban <user_id> [reason]")
        return

    try:
        target_id = int(args[0])
        reason    = " ".join(args[1:]) or "No reason given"
        await db.ban_user(target_id, reason)
        await message.reply(f"🚫 User <code>{target_id}</code> banned.\nReason: {reason}")
        await log_activity(client, f"#BAN\nUser `{target_id}` banned by `{message.from_user.id}`\nReason: {reason}")
    except ValueError:
        await message.reply("❌ Invalid user ID.")


@Client.on_message(filters.command("unban") & admin_filter)
async def unban_handler(client: Client, message: Message):
    args = message.command[1:]
    if not args:
        await message.reply("Usage: /unban <user_id>")
        return

    try:
        target_id = int(args[0])
        await db.unban_user(target_id)
        await message.reply(f"✅ User <code>{target_id}</code> unbanned.")
        await log_activity(client, f"#UNBAN\nUser `{target_id}` unbanned by `{message.from_user.id}`")
    except ValueError:
        await message.reply("❌ Invalid user ID.")


# ─────────────────────────────────────────────────────────
#  Broadcast
# ─────────────────────────────────────────────────────────

@Client.on_message(filters.command("broadcast") & admin_filter)
async def broadcast_handler(client: Client, message: Message):
    args = message.command[1:]
    target = args[0].lower() if args else "users"
    if target not in ("users", "groups"):
        await message.reply("Usage: /broadcast <users|groups>\nThen reply to a message with that command.")
        return

    if not message.reply_to_message:
        await message.reply(
            f"ℹ️ Reply to the message you want to broadcast to all <b>{target}</b>.\n"
            f"Example: Reply to your message with <code>/broadcast {target}</code>"
        )
        return

    status = await message.reply(f"📢 Broadcasting to {target}…")
    result = await broadcast_message(client, message.reply_to_message, target=target)
    await status.edit_text(
        f"📢 <b>Broadcast complete!</b>\n"
        f"✅ Sent: {result['sent']}\n"
        f"❌ Failed: {result['failed']}"
    )
    await log_activity(
        client,
        f"#BROADCAST\nTarget: {target} | Sent: {result['sent']} | Failed: {result['failed']}\n"
        f"By: `{message.from_user.id}`"
    )


# ─────────────────────────────────────────────────────────
#  Delete bad-quality files
# ─────────────────────────────────────────────────────────

@Client.on_message(filters.command("deletebad") & admin_filter)
async def delete_bad_handler(client: Client, message: Message):
    args    = message.command[1:]
    tags    = args if args else BAD_QUALITY_TAGS
    status  = await message.reply(f"🗑 Deleting files with tags: {', '.join(tags)}…")
    count   = await db.delete_files_by_quality(tags)
    await status.edit_text(f"✅ Deleted <b>{count}</b> low-quality file(s).")
    await log_activity(client, f"#DELETEBAD\nDeleted {count} files | Tags: {tags}")


# ─────────────────────────────────────────────────────────
#  Premium management
# ─────────────────────────────────────────────────────────

@Client.on_message(filters.command("addpremium") & admin_filter)
async def add_premium_handler(client: Client, message: Message):
    args = message.command[1:]
    if len(args) < 2:
        await message.reply("Usage: /addpremium <user_id> <days>")
        return

    try:
        target_id = int(args[0])
        days      = int(args[1])
        expiry    = await db.add_premium(target_id, days, message.from_user.id)
        await message.reply(
            f"👑 Premium added for <code>{target_id}</code>\n"
            f"📅 Expires: <b>{expiry.strftime('%d %b %Y')}</b>"
        )
        # Notify the user if possible
        try:
            await client.send_message(
                target_id,
                f"🎉 <b>Congratulations!</b> You've been granted <b>{days} days</b> of Premium access!\n"
                f"📅 Valid until: <b>{expiry.strftime('%d %b %Y')}</b>"
            )
        except Exception:
            pass
        await log_activity(client, f"#PREMIUM_ADD\nUser `{target_id}` | {days} days by `{message.from_user.id}`")
    except ValueError:
        await message.reply("❌ Invalid user ID or days value.")


@Client.on_message(filters.command("removepremium") & admin_filter)
async def remove_premium_handler(client: Client, message: Message):
    args = message.command[1:]
    if not args:
        await message.reply("Usage: /removepremium <user_id>")
        return

    try:
        target_id = int(args[0])
        removed   = await db.remove_premium(target_id)
        if removed:
            await message.reply(f"✅ Premium removed for <code>{target_id}</code>.")
        else:
            await message.reply("ℹ️ User is not a premium member.")
        await log_activity(client, f"#PREMIUM_REMOVE\nUser `{target_id}` by `{message.from_user.id}`")
    except ValueError:
        await message.reply("❌ Invalid user ID.")


# ─────────────────────────────────────────────────────────
#  Settings panel
# ─────────────────────────────────────────────────────────

@Client.on_message(filters.command("settings") & admin_filter)
async def settings_handler(client: Client, message: Message):
    from config.config import (
        FORCE_SUB_ENABLED, AUTO_DELETE_ENABLED, AUTO_DELETE_TIME,
        FILE_PROTECT, SHORTLINK_ENABLED, IMDB_ENABLED, AUTO_FILTER_BAD,
    )

    text = (
        "⚙️ <b>Current Settings</b>\n\n"
        f"🔒 Force Subscribe:   {'✅' if FORCE_SUB_ENABLED else '❌'}\n"
        f"🗑 Auto Delete:       {'✅' if AUTO_DELETE_ENABLED else '❌'} ({AUTO_DELETE_TIME}s)\n"
        f"🛡 File Protection:  {'✅' if FILE_PROTECT else '❌'}\n"
        f"🔗 Shortlinks:       {'✅' if SHORTLINK_ENABLED else '❌'}\n"
        f"🎬 IMDb Details:     {'✅' if IMDB_ENABLED else '❌'}\n"
        f"🚫 Auto Filter Bad:  {'✅' if AUTO_FILTER_BAD else '❌'}\n\n"
        "To change settings, update your environment variables and redeploy."
    )
    await message.reply(text)


# ─────────────────────────────────────────────────────────
#  New member join request approval
# ─────────────────────────────────────────────────────────

@Client.on_chat_join_request()
async def join_request_handler(client: Client, update):
    """Auto-approve join requests for connected groups."""
    try:
        await client.approve_chat_join_request(update.chat.id, update.from_user.id)
        log.info(f"Approved join request: {update.from_user.id} → {update.chat.id}")
    except Exception as e:
        log.warning(f"Join request approval failed: {e}")

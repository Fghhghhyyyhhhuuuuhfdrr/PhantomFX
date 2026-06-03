"""
bot/handlers/groups.py
Tracks when the bot is added to / removed from groups.
"""

from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import Message, ChatMemberUpdated
from pyrogram.enums import ChatMemberStatus

from bot.database import db
from bot.utils.helpers import log_activity


@Client.on_message(filters.new_chat_members)
async def bot_added_to_group(client: Client, message: Message):
    me = await client.get_me()
    for member in message.new_chat_members:
        if member.id == me.id:
            chat    = message.chat
            adder   = message.from_user
            await db.add_group(chat.id, chat.title or "", adder.id if adder else 0)
            await log_activity(
                client,
                f"#BOT_ADDED\nGroup: <b>{chat.title}</b> (<code>{chat.id}</code>)\n"
                f"By: {adder.mention if adder else 'Unknown'}"
            )
            await message.reply(
                "👋 Thanks for adding me!\n\n"
                "Users can now search for movies/videos just by typing their title here. "
                "I'll find matching files and send stream + download links.\n\n"
                "📌 Tip: Use /help to see available commands."
            )
            break


@Client.on_message(filters.left_chat_member)
async def bot_removed_from_group(client: Client, message: Message):
    me = await client.get_me()
    if message.left_chat_member and message.left_chat_member.id == me.id:
        await db.remove_group(message.chat.id)
        await log_activity(
            client,
            f"#BOT_REMOVED\nGroup: <b>{message.chat.title}</b> (<code>{message.chat.id}</code>)"
        )

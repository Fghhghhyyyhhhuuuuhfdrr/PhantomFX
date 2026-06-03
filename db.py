"""
database/db.py
MongoDB interface using Motor (async pymongo driver).
Collections:
  - files        : indexed media files
  - users        : registered users
  - groups       : connected groups
  - settings     : per-group/global settings
  - premium      : premium memberships
  - broadcast    : broadcast task tracking
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import motor.motor_asyncio
from pymongo import ASCENDING, DESCENDING, TEXT
from bson import ObjectId

from config.config import MONGO_URI, DATABASE_NAME

log = logging.getLogger(__name__)

_client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
_db: Optional[motor.motor_asyncio.AsyncIOMotorDatabase] = None


# ─────────────────────────────────────────────────────────
#  Connection
# ─────────────────────────────────────────────────────────

async def connect():
    global _client, _db
    _client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    _db = _client[DATABASE_NAME]
    await _ensure_indexes()
    log.info("MongoDB connected.")


async def disconnect():
    if _client:
        _client.close()


async def _ensure_indexes():
    # Full-text search on file name + caption
    await _db.files.create_index(
        [("file_name", TEXT), ("caption", TEXT)],
        weights={"file_name": 10, "caption": 5},
        name="text_search",
    )
    await _db.files.create_index([("file_id", ASCENDING)], unique=True)
    await _db.files.create_index([("channel_id", ASCENDING)])
    await _db.files.create_index([("quality_tag", ASCENDING)])
    await _db.users.create_index([("user_id", ASCENDING)], unique=True)
    await _db.groups.create_index([("chat_id", ASCENDING)], unique=True)
    await _db.premium.create_index([("user_id", ASCENDING)], unique=True)


# ─────────────────────────────────────────────────────────
#  Files
# ─────────────────────────────────────────────────────────

async def save_file(file_data: Dict[str, Any]) -> bool:
    """Upsert a file document. Returns True if inserted, False if updated."""
    try:
        result = await _db.files.update_one(
            {"file_id": file_data["file_id"]},
            {"$set": file_data},
            upsert=True,
        )
        return result.upserted_id is not None
    except Exception as e:
        log.error(f"save_file error: {e}")
        return False


async def search_files(
    query: str,
    file_type: Optional[str] = None,
    offset: int = 0,
    limit: int = 10,
    exclude_bad_quality: bool = False,
) -> tuple[List[Dict], int]:
    """
    Text-search files, returns (results, total_count).
    Falls back to regex search if text index gives 0 results.
    """
    base_filter: Dict[str, Any] = {}

    if file_type:
        base_filter["file_type"] = file_type

    if exclude_bad_quality:
        from config.config import BAD_QUALITY_TAGS
        base_filter["quality_tag"] = {"$nin": BAD_QUALITY_TAGS}

    # 1️⃣ Try MongoDB full-text search
    text_filter = {"$text": {"$search": query}, **base_filter}
    total = await _db.files.count_documents(text_filter)
    if total > 0:
        cursor = (
            _db.files.find(text_filter, {"score": {"$meta": "textScore"}})
            .sort([("score", {"$meta": "textScore"})])
            .skip(offset)
            .limit(limit)
        )
        return await cursor.to_list(length=limit), total

    # 2️⃣ Fallback: case-insensitive regex (handles minor typos via fuzzy build)
    regex_parts = _build_regex(query)
    regex_filter = {"file_name": {"$regex": regex_parts, "$options": "i"}, **base_filter}
    total = await _db.files.count_documents(regex_filter)
    cursor = (
        _db.files.find(regex_filter)
        .sort([("_id", DESCENDING)])
        .skip(offset)
        .limit(limit)
    )
    return await cursor.to_list(length=limit), total


def _build_regex(query: str) -> str:
    """
    Build a forgiving regex: allows 1-char gaps between each word
    character so minor typos still match.
    e.g. "avngers" → still hits "avengers"
    """
    words = query.strip().split()
    parts = [".{0,2}".join(list(w)) for w in words]
    return ".*".join(parts)


async def get_file(file_id: str) -> Optional[Dict]:
    return await _db.files.find_one({"file_id": file_id})


async def delete_file(file_id: str) -> bool:
    result = await _db.files.delete_one({"file_id": file_id})
    return result.deleted_count > 0


async def delete_files_by_quality(tags: List[str]) -> int:
    result = await _db.files.delete_many({"quality_tag": {"$in": tags}})
    return result.deleted_count


async def total_files() -> int:
    return await _db.files.count_documents({})


async def get_all_files(batch_size: int = 500):
    """Async generator yielding file docs in batches."""
    cursor = _db.files.find({})
    async for doc in cursor:
        yield doc


# ─────────────────────────────────────────────────────────
#  Users
# ─────────────────────────────────────────────────────────

async def add_user(user_id: int, name: str, username: str = "") -> bool:
    result = await _db.users.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {
            "user_id": user_id,
            "name": name,
            "username": username,
            "joined": datetime.utcnow(),
            "banned": False,
            "total_searches": 0,
        }},
        upsert=True,
    )
    return result.upserted_id is not None


async def get_user(user_id: int) -> Optional[Dict]:
    return await _db.users.find_one({"user_id": user_id})


async def ban_user(user_id: int, reason: str = "") -> bool:
    result = await _db.users.update_one(
        {"user_id": user_id},
        {"$set": {"banned": True, "ban_reason": reason}},
        upsert=True,
    )
    return result.modified_count > 0


async def unban_user(user_id: int) -> bool:
    result = await _db.users.update_one(
        {"user_id": user_id},
        {"$set": {"banned": False, "ban_reason": ""}},
    )
    return result.modified_count > 0


async def is_banned(user_id: int) -> bool:
    doc = await _db.users.find_one({"user_id": user_id, "banned": True})
    return doc is not None


async def all_user_ids() -> List[int]:
    cursor = _db.users.find({"banned": {"$ne": True}}, {"user_id": 1})
    return [d["user_id"] async for d in cursor]


async def total_users() -> int:
    return await _db.users.count_documents({})


async def increment_search(user_id: int):
    await _db.users.update_one({"user_id": user_id}, {"$inc": {"total_searches": 1}})


# ─────────────────────────────────────────────────────────
#  Groups
# ─────────────────────────────────────────────────────────

async def add_group(chat_id: int, title: str, added_by: int) -> bool:
    result = await _db.groups.update_one(
        {"chat_id": chat_id},
        {"$setOnInsert": {
            "chat_id": chat_id,
            "title": title,
            "added_by": added_by,
            "joined": datetime.utcnow(),
            "active": True,
        }},
        upsert=True,
    )
    return result.upserted_id is not None


async def get_group(chat_id: int) -> Optional[Dict]:
    return await _db.groups.find_one({"chat_id": chat_id})


async def all_group_ids() -> List[int]:
    cursor = _db.groups.find({"active": True}, {"chat_id": 1})
    return [d["chat_id"] async for d in cursor]


async def total_groups() -> int:
    return await _db.groups.count_documents({"active": True})


async def remove_group(chat_id: int):
    await _db.groups.update_one({"chat_id": chat_id}, {"$set": {"active": False}})


# ─────────────────────────────────────────────────────────
#  Settings (per-group or global key/value store)
# ─────────────────────────────────────────────────────────

async def get_setting(key: str, scope: int = 0) -> Optional[Any]:
    doc = await _db.settings.find_one({"key": key, "scope": scope})
    return doc["value"] if doc else None


async def set_setting(key: str, value: Any, scope: int = 0):
    await _db.settings.update_one(
        {"key": key, "scope": scope},
        {"$set": {"value": value}},
        upsert=True,
    )


# ─────────────────────────────────────────────────────────
#  Premium
# ─────────────────────────────────────────────────────────

async def add_premium(user_id: int, days: int, added_by: int) -> datetime:
    expiry = datetime.utcnow() + timedelta(days=days)
    await _db.premium.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "expiry": expiry,
            "added_by": added_by,
            "updated": datetime.utcnow(),
        }},
        upsert=True,
    )
    return expiry


async def remove_premium(user_id: int) -> bool:
    result = await _db.premium.delete_one({"user_id": user_id})
    return result.deleted_count > 0


async def is_premium(user_id: int) -> bool:
    doc = await _db.premium.find_one({"user_id": user_id})
    if not doc:
        return False
    return doc["expiry"] > datetime.utcnow()


async def get_premium_info(user_id: int) -> Optional[Dict]:
    return await _db.premium.find_one({"user_id": user_id})


async def total_premium() -> int:
    return await _db.premium.count_documents({"expiry": {"$gt": datetime.utcnow()}})

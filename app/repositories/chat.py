from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.schemas.chat import MessageOut


def _msg_to_out(doc: dict) -> MessageOut:
    return MessageOut(
        id=str(doc["_id"]),
        conversation_id=doc["conversation_id"],
        sender_id=doc["sender_id"],
        text=doc.get("text", ""),
        created_at=doc["created_at"],
        read_at=doc.get("read_at"),
        deleted_at=doc.get("deleted_at"),
    )


async def insert_message(db: AsyncIOMotorDatabase, doc: dict) -> dict:
    result = await db.chat_messages.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def get_message_by_id(db: AsyncIOMotorDatabase, message_id: str) -> dict | None:
    try:
        oid = ObjectId(message_id)
    except Exception:
        return None
    return await db.chat_messages.find_one({"_id": oid})


async def get_message_or_404(db: AsyncIOMotorDatabase, message_id: str) -> dict:
    doc = await get_message_by_id(db, message_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Message not found")
    return doc


async def list_messages(
    db: AsyncIOMotorDatabase,
    conversation_id: int,
    before_id: str | None = None,
    limit: int = 50,
) -> list[MessageOut]:
    query: dict = {"conversation_id": conversation_id, "deleted_at": None}
    if before_id:
        try:
            query["_id"] = {"$lt": ObjectId(before_id)}
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid before_id")
    cursor = db.chat_messages.find(query).sort("_id", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    return [_msg_to_out(d) for d in docs]


async def get_last_message(db: AsyncIOMotorDatabase, conversation_id: int) -> MessageOut | None:
    doc = await db.chat_messages.find_one(
        {"conversation_id": conversation_id, "deleted_at": None},
        sort=[("_id", -1)],
    )
    return _msg_to_out(doc) if doc else None


async def count_unread(db: AsyncIOMotorDatabase, conversation_id: int, reader_id: int) -> int:
    return await db.chat_messages.count_documents(
        {
            "conversation_id": conversation_id,
            "sender_id": {"$ne": reader_id},
            "read_at": None,
            "deleted_at": None,
        }
    )


async def mark_read_up_to(
    db: AsyncIOMotorDatabase,
    conversation_id: int,
    reader_id: int,
    message_id: str,
) -> None:
    try:
        oid = ObjectId(message_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid message_id")
    now = datetime.now(timezone.utc)
    await db.chat_messages.update_many(
        {
            "conversation_id": conversation_id,
            "sender_id": {"$ne": reader_id},
            "_id": {"$lte": oid},
            "read_at": None,
        },
        {"$set": {"read_at": now}},
    )


async def soft_delete_message(
    db: AsyncIOMotorDatabase,
    message_id: str,
    sender_id: int,
) -> dict:
    doc = await get_message_or_404(db, message_id)
    if doc["sender_id"] != sender_id:
        raise HTTPException(status_code=403, detail="Cannot delete another user's message")
    if doc.get("deleted_at"):
        raise HTTPException(status_code=409, detail="Message already deleted")
    now = datetime.now(timezone.utc)
    await db.chat_messages.update_one(
        {"_id": doc["_id"]},
        {"$set": {"deleted_at": now}},
    )
    doc["deleted_at"] = now
    return doc


async def ensure_chat_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.chat_messages.create_index([("conversation_id", 1), ("_id", -1)])
    await db.chat_messages.create_index(
        [("conversation_id", 1), ("read_at", 1), ("sender_id", 1)]
    )

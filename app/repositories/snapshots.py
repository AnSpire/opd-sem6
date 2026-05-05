from datetime import datetime, timezone

from pymongo import ReturnDocument

from app.db.mongo import get_db


async def upsert_snapshot(widget_id: int, config: dict, reason: str) -> dict:
    db = get_db()
    doc = await db.widget_config_snapshots.find_one_and_update(
        {"widget_id": widget_id},
        {
            "$inc": {"version": 1},
            "$set": {
                "config": config,
                "reason": reason,
                "emitted_at": datetime.now(timezone.utc),
            },
            "$setOnInsert": {"widget_id": widget_id},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc

from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase


async def create_log(
    db: AsyncIOMotorDatabase,
    *,
    submission_id: str,
    assignment_id: int,
    widget_id: int,
    request_data: dict,
    response_data: dict,
    latency_ms: int,
    status: str,
    error: str | None,
) -> dict:
    doc = {
        "submission_id": submission_id,
        "assignment_id": assignment_id,
        "widget_id": widget_id,
        "request": request_data,
        "response": response_data,
        "latency_ms": latency_ms,
        "status": status,
        "error": error,
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.ai_logs.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc

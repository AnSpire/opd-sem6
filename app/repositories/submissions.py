from bson import ObjectId
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase


async def create_submission(db: AsyncIOMotorDatabase, doc: dict) -> dict:
    result = await db.submissions.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def get_by_id(db: AsyncIOMotorDatabase, submission_id: str) -> dict | None:
    try:
        oid = ObjectId(submission_id)
    except Exception:
        return None
    return await db.submissions.find_one({"_id": oid})


async def get_by_id_or_404(db: AsyncIOMotorDatabase, submission_id: str) -> dict:
    doc = await get_by_id(db, submission_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Submission not found")
    return doc


async def list_by_assignment(db: AsyncIOMotorDatabase, assignment_id: int) -> list[dict]:
    cursor = db.submissions.find({"assignment_id": assignment_id}).sort("submitted_at", -1)
    return await cursor.to_list(length=None)


async def list_by_student(db: AsyncIOMotorDatabase, student_user_id: int) -> list[dict]:
    cursor = db.submissions.find({"student_user_id": student_user_id}).sort("submitted_at", -1)
    return await cursor.to_list(length=None)


async def list_by_assignment_and_student(
    db: AsyncIOMotorDatabase, assignment_id: int, student_user_id: int
) -> list[dict]:
    cursor = db.submissions.find(
        {"assignment_id": assignment_id, "student_user_id": student_user_id}
    ).sort("submitted_at", -1)
    return await cursor.to_list(length=None)


async def count_attempts(
    db: AsyncIOMotorDatabase, assignment_id: int, student_user_id: int
) -> int:
    return await db.submissions.count_documents(
        {"assignment_id": assignment_id, "student_user_id": student_user_id}
    )


async def update_grading(
    db: AsyncIOMotorDatabase,
    submission_id: str,
    status: str,
    ai_grading: dict | None = None,
) -> None:
    fields: dict = {"status": status}
    if ai_grading is not None:
        fields["grading.ai"] = ai_grading
    await db.submissions.update_one(
        {"_id": ObjectId(submission_id)},
        {"$set": fields},
    )


async def set_final_grade(
    db: AsyncIOMotorDatabase,
    submission_id: str,
    final_grading: dict,
) -> None:
    await db.submissions.update_one(
        {"_id": ObjectId(submission_id)},
        {"$set": {"status": "graded", "grading.final": final_grading}},
    )


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.submissions.create_index(
        [("assignment_id", 1), ("student_user_id", 1), ("attempt_number", 1)],
        unique=True,
    )
    await db.submissions.create_index([("assignment_id", 1), ("status", 1)])
    await db.submissions.create_index([("student_user_id", 1), ("submitted_at", -1)])
    await db.submissions.create_index([("widget_id", 1), ("submitted_at", -1)])

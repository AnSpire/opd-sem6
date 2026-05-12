import uuid as _uuid
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import require_widget_owner
from app.db.mongo import get_db
from app.db.postgres import get_session
from app.deps import UserContext, get_current_user
from app.models.assignment import AssignmentType, FinalScoreStrategy
from app.repositories import submissions as sub_repo
from app.schemas.submission import SubmissionOut, TestSubmissionCreate
from app.services import assignments as assignment_service
from app.services import homework as hw_service
from app.services import questions as question_service
from app.services import storage
from app.services import widgets as widget_service
from app.services.auto_grader import grade_answers

router = APIRouter(tags=["submissions"])

_MIME_TO_KIND: dict[str, str] = {
    "application/pdf": "pdf",
    "image/jpeg": "image",
    "image/png": "image",
    "image/gif": "image",
    "image/webp": "image",
}

_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
_MAX_FILES = 5


def _mime_to_kind(mime: str) -> str | None:
    return _MIME_TO_KIND.get(mime.lower().split(";")[0].strip())


def _effective_score(attempts: list[dict], strategy: FinalScoreStrategy) -> int | None:
    scores = [
        a["grading"]["final"]["score"]
        for a in attempts
        if a.get("grading", {}).get("final") is not None
    ]
    if not scores:
        return None
    match strategy:
        case FinalScoreStrategy.last:
            return scores[0]
        case FinalScoreStrategy.best:
            return max(scores)
        case FinalScoreStrategy.average:
            return round(sum(scores) / len(scores))
    return None


def _to_out(doc: dict, effective_score: int | None) -> SubmissionOut:
    return SubmissionOut(
        id=str(doc["_id"]),
        assignment_id=doc["assignment_id"],
        widget_id=doc["widget_id"],
        board_id=doc["board_id"],
        student_user_id=doc["student_user_id"],
        type=doc["type"],
        attempt_number=doc["attempt_number"],
        submitted_at=doc["submitted_at"],
        is_late=doc["is_late"],
        status=doc["status"],
        payload=doc["payload"],
        grading=doc["grading"],
        effective_score=effective_score,
    )


async def _create_test_submission(
    body: TestSubmissionCreate,
    assignment_id: int,
    user: UserContext,
    session: AsyncSession,
    db: AsyncIOMotorDatabase,
) -> SubmissionOut:
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can submit")

    assignment = await assignment_service.get_assignment_or_404(session, assignment_id)

    if assignment.type != AssignmentType.test:
        raise HTTPException(status_code=422, detail="Only test submissions supported here")

    now = datetime.now(timezone.utc)
    is_late = bool(assignment.deadline and now > assignment.deadline.replace(tzinfo=timezone.utc))
    if is_late and not assignment.allow_late_submissions:
        raise HTTPException(status_code=409, detail="Deadline passed and late submissions are not allowed")

    count = await sub_repo.count_attempts(db, assignment_id, user.user_id)
    if assignment.max_attempts is not None and count >= assignment.max_attempts:
        raise HTTPException(status_code=409, detail="Maximum number of attempts reached")

    questions = await question_service.list_questions(session, assignment_id)
    graded_answers, total_score = grade_answers(questions, [a.model_dump() for a in body.answers])

    doc = {
        "assignment_id": assignment_id,
        "widget_id": assignment.widget_id,
        "board_id": user.board_id,
        "student_user_id": user.user_id,
        "type": "test",
        "attempt_number": count + 1,
        "submitted_at": now,
        "is_late": is_late,
        "status": "auto_graded",
        "payload": {"answers": graded_answers},
        "grading": {
            "ai": None,
            "final": {
                "score": total_score,
                "feedback": None,
                "teacher_user_id": None,
                "graded_at": now,
                "accepted_ai": False,
            },
        },
    }
    created = await sub_repo.create_submission(db, doc)

    all_attempts = await sub_repo.list_by_assignment_and_student(db, assignment_id, user.user_id)
    eff = _effective_score(all_attempts, assignment.final_score_strategy)
    return _to_out(created, eff)


async def _create_homework_submission(
    request: Request,
    assignment_id: int,
    user: UserContext,
    session: AsyncSession,
    db: AsyncIOMotorDatabase,
) -> SubmissionOut:
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can submit")

    assignment = await assignment_service.get_assignment_or_404(session, assignment_id)

    if assignment.type != AssignmentType.homework:
        raise HTTPException(status_code=422, detail="Use JSON body for test submissions")

    now = datetime.now(timezone.utc)
    is_late = bool(assignment.deadline and now > assignment.deadline.replace(tzinfo=timezone.utc))
    if is_late and not assignment.allow_late_submissions:
        raise HTTPException(status_code=409, detail="Deadline passed and late submissions are not allowed")

    count = await sub_repo.count_attempts(db, assignment_id, user.user_id)
    if assignment.max_attempts is not None and count >= assignment.max_attempts:
        raise HTTPException(status_code=409, detail="Maximum number of attempts reached")

    hw_details = await hw_service.get_homework_details_or_404(session, assignment_id)
    accepted = set(hw_details.accepted_formats)

    form = await request.form()
    text: str = form.get("text", "") or ""
    markdown: str = form.get("markdown", "") or ""
    files = form.getlist("files")

    if len(files) > _MAX_FILES:
        raise HTTPException(status_code=422, detail=f"Maximum {_MAX_FILES} files allowed")

    submission_oid = ObjectId()
    submission_id_str = str(submission_oid)

    attachments: list[dict] = []
    uploaded_keys: list[str] = []

    for f in files:
        raw_bytes = await f.read()

        if len(raw_bytes) > _MAX_FILE_SIZE:
            for key in uploaded_keys:
                await storage.delete_object(key)
            raise HTTPException(status_code=422, detail=f"File '{f.filename}' exceeds 10 MB limit")

        mime = (f.content_type or "application/octet-stream").lower().split(";")[0].strip()
        kind = _mime_to_kind(mime)

        if accepted and kind not in accepted:
            for key in uploaded_keys:
                await storage.delete_object(key)
            raise HTTPException(
                status_code=422,
                detail=f"File type '{mime}' is not accepted. Allowed: {sorted(accepted)}",
            )

        file_uuid = str(_uuid.uuid4())
        key = f"submissions/{assignment.widget_id}/{submission_id_str}/{file_uuid}_{f.filename}"
        await storage.upload_object(key, raw_bytes, mime)
        uploaded_keys.append(key)
        attachments.append({
            "kind": kind,
            "s3_key": key,
            "filename": f.filename,
            "mime": mime,
            "size": len(raw_bytes),
        })

    doc = {
        "_id": submission_oid,
        "assignment_id": assignment_id,
        "widget_id": assignment.widget_id,
        "board_id": user.board_id,
        "student_user_id": user.user_id,
        "type": "homework",
        "attempt_number": count + 1,
        "submitted_at": now,
        "is_late": is_late,
        "status": "pending_ai",
        "payload": {
            "text": text,
            "markdown": markdown,
            "attachments": attachments,
        },
        "grading": {"ai": None, "final": None},
    }
    created = await sub_repo.create_submission(db, doc)

    all_attempts = await sub_repo.list_by_assignment_and_student(db, assignment_id, user.user_id)
    eff = _effective_score(all_attempts, assignment.final_score_strategy)
    return _to_out(created, eff)


@router.post(
    "/assignments/{assignment_id}/submissions",
    response_model=SubmissionOut,
    status_code=201,
    summary="Сдать задание (тест — JSON, домашка — multipart/form-data)",
)
async def create_submission(
    assignment_id: int,
    request: Request,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ct = request.headers.get("content-type", "")
    if "application/json" in ct:
        raw = await request.json()
        body = TestSubmissionCreate.model_validate(raw)
        return await _create_test_submission(body, assignment_id, user, session, db)
    return await _create_homework_submission(request, assignment_id, user, session, db)


@router.get(
    "/assignments/{assignment_id}/submissions",
    response_model=list[SubmissionOut],
    summary="Список сдач по заданию (препод видит все, студент — только свои)",
)
async def list_submissions(
    assignment_id: int,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    assignment = await assignment_service.get_assignment_or_404(session, assignment_id)

    if user.role == "teacher":
        widget = await widget_service.get_widget_or_404(session, assignment.widget_id)
        require_widget_owner(widget, user)
        docs = await sub_repo.list_by_assignment(db, assignment_id)
    else:
        docs = await sub_repo.list_by_assignment_and_student(db, assignment_id, user.user_id)

    result = []
    for doc in docs:
        all_attempts = await sub_repo.list_by_assignment_and_student(
            db, assignment_id, doc["student_user_id"]
        )
        eff = _effective_score(all_attempts, assignment.final_score_strategy)
        result.append(_to_out(doc, eff))
    return result


@router.get(
    "/submissions/{submission_id}",
    response_model=SubmissionOut,
    summary="Получить сдачу по ID (препод-владелец или студент-автор)",
)
async def get_submission(
    submission_id: str,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    doc = await sub_repo.get_by_id_or_404(db, submission_id)

    if user.role == "teacher":
        assignment = await assignment_service.get_assignment_or_404(session, doc["assignment_id"])
        widget = await widget_service.get_widget_or_404(session, assignment.widget_id)
        require_widget_owner(widget, user)
    else:
        if doc["student_user_id"] != user.user_id:
            raise HTTPException(status_code=403, detail="Access denied")

    assignment = await assignment_service.get_assignment_or_404(session, doc["assignment_id"])
    all_attempts = await sub_repo.list_by_assignment_and_student(
        db, doc["assignment_id"], doc["student_user_id"]
    )
    eff = _effective_score(all_attempts, assignment.final_score_strategy)
    return _to_out(doc, eff)

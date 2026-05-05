from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
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
from app.services import questions as question_service
from app.services import widgets as widget_service
from app.services.auto_grader import grade_answers

router = APIRouter(tags=["submissions"])


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


@router.post("/assignments/{assignment_id}/submissions", response_model=SubmissionOut, status_code=201)
async def create_submission(
    assignment_id: int,
    body: TestSubmissionCreate,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
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


@router.get("/assignments/{assignment_id}/submissions", response_model=list[SubmissionOut])
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


@router.get("/submissions/{submission_id}", response_model=SubmissionOut)
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

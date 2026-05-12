from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import require_teacher, require_widget_owner
from app.db.postgres import get_session
from app.deps import UserContext, get_current_user
from app.schemas.question import QuestionCreate, QuestionOut, QuestionUpdate
from app.services import assignments as assignment_service
from app.services import questions as question_service
from app.services import widgets as widget_service

router = APIRouter(tags=["questions"])


async def _resolve_widget_for_assignment(session: AsyncSession, assignment_id: int):
    assignment = await assignment_service.get_assignment_or_404(session, assignment_id)
    widget = await widget_service.get_widget_or_404(session, assignment.widget_id)
    return assignment, widget


@router.post("/assignments/{assignment_id}/questions", response_model=QuestionOut, status_code=201,
             summary="Добавить вопрос к тесту (только владелец-препод)")
async def create_question(
    assignment_id: int,
    body: QuestionCreate,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    require_teacher(user)
    _, widget = await _resolve_widget_for_assignment(session, assignment_id)
    require_widget_owner(widget, user)
    return await question_service.create_question(session, assignment_id, body)


@router.get("/assignments/{assignment_id}/questions", response_model=list[QuestionOut],
            summary="Список вопросов теста (correct_answer скрыт для студентов)")
async def list_questions(
    assignment_id: int,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await assignment_service.get_assignment_or_404(session, assignment_id)
    questions = await question_service.list_questions(session, assignment_id)
    if user.role == "student":
        return [q.model_copy(update={"correct_answer": None}) for q in
                [QuestionOut.model_validate(q) for q in questions]]
    return questions


@router.patch("/questions/{question_id}", response_model=QuestionOut,
              summary="Обновить вопрос (только владелец-препод)")
async def update_question(
    question_id: int,
    body: QuestionUpdate,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    require_teacher(user)
    question = await question_service.get_question_or_404(session, question_id)
    _, widget = await _resolve_widget_for_assignment(session, question.assignment_id)
    require_widget_owner(widget, user)
    return await question_service.update_question(session, question, body)


@router.delete("/questions/{question_id}", status_code=204,
               summary="Удалить вопрос (только владелец-препод)")
async def delete_question(
    question_id: int,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    require_teacher(user)
    question = await question_service.get_question_or_404(session, question_id)
    _, widget = await _resolve_widget_for_assignment(session, question.assignment_id)
    require_widget_owner(widget, user)
    await question_service.delete_question(session, question)

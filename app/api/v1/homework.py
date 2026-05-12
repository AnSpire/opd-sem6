from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import require_teacher, require_widget_owner
from app.db.postgres import get_session
from app.deps import UserContext, get_current_user
from app.models.assignment import AssignmentType
from app.schemas.homework import HomeworkDetailsCreate, HomeworkDetailsOut
from app.services import assignments as assignment_service
from app.services import homework as hw_service
from app.services import widgets as widget_service
from fastapi import HTTPException

router = APIRouter(tags=["homework"])


@router.put(
    "/assignments/{assignment_id}/homework",
    response_model=HomeworkDetailsOut,
    summary="Создать или обновить детали домашнего задания (только учитель-владелец)",
)
async def upsert_homework(
    assignment_id: int,
    body: HomeworkDetailsCreate,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    require_teacher(user)
    assignment = await assignment_service.get_assignment_or_404(session, assignment_id)
    if assignment.type != AssignmentType.homework:
        raise HTTPException(status_code=422, detail="Assignment is not of type homework")
    widget = await widget_service.get_widget_or_404(session, assignment.widget_id)
    require_widget_owner(widget, user)
    return await hw_service.upsert_homework_details(session, assignment_id, body)


@router.get(
    "/assignments/{assignment_id}/homework",
    response_model=HomeworkDetailsOut,
    summary="Получить детали домашнего задания",
)
async def get_homework(
    assignment_id: int,
    _user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await assignment_service.get_assignment_or_404(session, assignment_id)
    return await hw_service.get_homework_details_or_404(session, assignment_id)

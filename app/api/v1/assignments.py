from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import require_teacher, require_widget_owner
from app.db.postgres import get_session
from app.deps import UserContext, get_current_user
from app.schemas.assignment import (
    AssignmentCreate,
    AssignmentOut,
    AssignmentUpdate,
    AssignmentWithConfigOut,
    ConfigOut,
)
from app.services import assignments as assignment_service
from app.services import widgets as widget_service
from app.services.widget_config import emit_widget_updated

router = APIRouter(tags=["assignments"])


@router.post("/widgets/{widget_id}/assignments", response_model=AssignmentWithConfigOut, status_code=201)
async def create_assignment(
    widget_id: int,
    body: AssignmentCreate,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    require_teacher(user)
    widget = await widget_service.get_widget_or_404(session, widget_id)
    require_widget_owner(widget, user)
    assignment = await assignment_service.create_assignment(session, widget_id, user.user_id, body)
    config = await emit_widget_updated(session, widget_id, "assignment_created")
    return AssignmentWithConfigOut(assignment=AssignmentOut.model_validate(assignment), config=config)


@router.get("/widgets/{widget_id}/assignments", response_model=list[AssignmentOut])
async def list_assignments(
    widget_id: int,
    _user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await widget_service.get_widget_or_404(session, widget_id)
    return await assignment_service.list_assignments(session, widget_id)


@router.get("/assignments/{assignment_id}", response_model=AssignmentOut)
async def get_assignment(
    assignment_id: int,
    _user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await assignment_service.get_assignment_or_404(session, assignment_id)


@router.patch("/assignments/{assignment_id}", response_model=AssignmentWithConfigOut)
async def update_assignment(
    assignment_id: int,
    body: AssignmentUpdate,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    require_teacher(user)
    assignment = await assignment_service.get_assignment_or_404(session, assignment_id)
    widget = await widget_service.get_widget_or_404(session, assignment.widget_id)
    require_widget_owner(widget, user)
    assignment = await assignment_service.update_assignment(session, assignment, body)
    config = await emit_widget_updated(session, assignment.widget_id, "assignment_updated")
    return AssignmentWithConfigOut(assignment=AssignmentOut.model_validate(assignment), config=config)


@router.delete("/assignments/{assignment_id}", response_model=ConfigOut)
async def delete_assignment(
    assignment_id: int,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    require_teacher(user)
    assignment = await assignment_service.get_assignment_or_404(session, assignment_id)
    widget = await widget_service.get_widget_or_404(session, assignment.widget_id)
    require_widget_owner(widget, user)
    widget_id = assignment.widget_id
    await assignment_service.delete_assignment(session, assignment)
    config = await emit_widget_updated(session, widget_id, "assignment_deleted")
    return ConfigOut(config=config)

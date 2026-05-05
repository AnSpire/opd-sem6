from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import require_teacher, require_widget_owner
from app.db.postgres import get_session
from app.deps import UserContext, get_current_user
from app.schemas.widget import WidgetCreate, WidgetOut
from app.services import widgets as widget_service
from app.services.widget_config import emit_widget_updated

router = APIRouter(prefix="/widgets", tags=["widgets"])


@router.post("", response_model=WidgetOut, status_code=201)
async def create_widget(
    body: WidgetCreate,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    require_teacher(user)
    widget, created = await widget_service.upsert_widget(session, body.id, body.board_id, user.user_id)
    if created:
        await emit_widget_updated(session, widget.id, "widget_created")
    return widget


@router.get("/{widget_id}", response_model=WidgetOut)
async def get_widget(
    widget_id: int,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await widget_service.get_widget_or_404(session, widget_id)


@router.post("/{widget_id}/info", response_model=WidgetOut)
async def set_info(
    widget_id: int,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await widget_service.get_widget_or_404(session, widget_id)


@router.delete("/{widget_id}", status_code=204)
async def delete_widget(
    widget_id: int,
    user: UserContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    require_teacher(user)
    widget = await widget_service.get_widget_or_404(session, widget_id)
    require_widget_owner(widget, user)
    await widget_service.delete_widget(session, widget_id)

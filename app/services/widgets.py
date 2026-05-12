from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.widget import Widget


async def upsert_widget(
    session: AsyncSession,
    widget_id: int,
    board_id: int,
    creator_user_id: int,
) -> tuple[Widget, bool]:
    """Return (widget, created). Idempotent by (board_id, creator_user_id)."""
    print("BOARD_ID: " + str(board_id))
    stmt = select(Widget).where(
        Widget.board_id == board_id,
        Widget.creator_user_id == creator_user_id,
    )
    widget = (await session.execute(stmt)).scalar_one_or_none()
    if widget:
        return widget, False

    widget = Widget(id=widget_id, board_id=board_id, creator_user_id=creator_user_id)
    session.add(widget)
    await session.commit()
    await session.refresh(widget)
    return widget, True


async def get_widget_or_404(session: AsyncSession, widget_id: int) -> Widget:
    stmt = select(Widget).where(Widget.id == widget_id)
    widget = (await session.execute(stmt)).scalar_one_or_none()
    if not widget:
        raise HTTPException(status_code=404, detail="Widget not found")
    return widget


async def delete_widget(session: AsyncSession, widget_id: int) -> None:
    widget = await get_widget_or_404(session, widget_id)
    await session.delete(widget)
    await session.commit()

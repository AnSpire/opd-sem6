from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assignment import Assignment
from app.repositories.snapshots import upsert_snapshot
from app.schemas.assignment import AssignmentPreview, WidgetConfigOut


async def build_config(session: AsyncSession, widget_id: int) -> WidgetConfigOut:
    count = (
        await session.execute(
            select(func.count()).select_from(Assignment).where(Assignment.widget_id == widget_id)
        )
    ).scalar_one()

    rows = (
        await session.execute(
            select(Assignment)
            .where(Assignment.widget_id == widget_id)
            .order_by(Assignment.created_at.desc())
            .limit(3)
        )
    ).scalars().all()

    return WidgetConfigOut(
        assignments_count=count,
        preview=[
            AssignmentPreview(
                id=a.id,
                title=a.title,
                type=a.type,
                deadline=a.deadline,
                created_at=a.created_at,
            )
            for a in rows
        ],
    )


async def emit_widget_updated(
    session: AsyncSession, widget_id: int, reason: str
) -> WidgetConfigOut:
    config = await build_config(session, widget_id)
    await upsert_snapshot(
        widget_id,
        config.model_dump(mode="json"),
        reason,
    )
    return config

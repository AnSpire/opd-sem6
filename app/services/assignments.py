from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assignment import Assignment
from app.schemas.assignment import AssignmentCreate, AssignmentUpdate


async def create_assignment(
    session: AsyncSession,
    widget_id: int,
    creator_user_id: int,
    data: AssignmentCreate,
) -> Assignment:
    assignment = Assignment(
        widget_id=widget_id,
        creator_user_id=creator_user_id,
        **data.model_dump(),
    )
    session.add(assignment)
    await session.commit()
    await session.refresh(assignment)
    return assignment


async def list_assignments(session: AsyncSession, widget_id: int) -> list[Assignment]:
    rows = await session.execute(
        select(Assignment)
        .where(Assignment.widget_id == widget_id)
        .order_by(Assignment.created_at.desc())
    )
    return list(rows.scalars().all())


async def get_assignment_or_404(session: AsyncSession, assignment_id: int) -> Assignment:
    row = (
        await session.execute(select(Assignment).where(Assignment.id == assignment_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return row


async def update_assignment(
    session: AsyncSession, assignment: Assignment, data: AssignmentUpdate
) -> Assignment:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(assignment, key, value)
    await session.commit()
    await session.refresh(assignment)
    return assignment


async def delete_assignment(session: AsyncSession, assignment: Assignment) -> None:
    await session.delete(assignment)
    await session.commit()

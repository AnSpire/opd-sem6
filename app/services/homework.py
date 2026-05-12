from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.homework_details import HomeworkDetails
from app.schemas.homework import HomeworkDetailsCreate


async def upsert_homework_details(
    session: AsyncSession,
    assignment_id: int,
    data: HomeworkDetailsCreate,
) -> HomeworkDetails:
    result = await session.execute(
        select(HomeworkDetails).where(HomeworkDetails.assignment_id == assignment_id)
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        hw = HomeworkDetails(
            assignment_id=assignment_id,
            prompt=data.prompt,
            reference_answer=data.reference_answer,
            grading_criteria=data.grading_criteria,
            accepted_formats=data.accepted_formats,
        )
        session.add(hw)
    else:
        existing.prompt = data.prompt
        existing.reference_answer = data.reference_answer
        existing.grading_criteria = data.grading_criteria
        existing.accepted_formats = data.accepted_formats
        hw = existing
    await session.commit()
    await session.refresh(hw)
    return hw


async def get_homework_details_or_404(
    session: AsyncSession,
    assignment_id: int,
) -> HomeworkDetails:
    result = await session.execute(
        select(HomeworkDetails).where(HomeworkDetails.assignment_id == assignment_id)
    )
    hw = result.scalar_one_or_none()
    if hw is None:
        raise HTTPException(status_code=404, detail="Homework details not found")
    return hw

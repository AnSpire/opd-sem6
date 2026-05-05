from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import Question
from app.schemas.question import QuestionCreate, QuestionUpdate


async def create_question(
    session: AsyncSession,
    assignment_id: int,
    data: QuestionCreate,
) -> Question:
    question = Question(assignment_id=assignment_id, **data.model_dump())
    session.add(question)
    await session.commit()
    await session.refresh(question)
    return question


async def list_questions(session: AsyncSession, assignment_id: int) -> list[Question]:
    rows = await session.execute(
        select(Question)
        .where(Question.assignment_id == assignment_id)
        .order_by(Question.order.asc())
    )
    return list(rows.scalars().all())


async def get_question_or_404(session: AsyncSession, question_id: int) -> Question:
    row = (
        await session.execute(select(Question).where(Question.id == question_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Question not found")
    return row


async def update_question(
    session: AsyncSession, question: Question, data: QuestionUpdate
) -> Question:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(question, key, value)
    await session.commit()
    await session.refresh(question)
    return question


async def delete_question(session: AsyncSession, question: Question) -> None:
    await session.delete(question)
    await session.commit()

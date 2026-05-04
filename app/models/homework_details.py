from sqlalchemy import ARRAY, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class HomeworkDetails(Base):
    __tablename__ = "homework_details"

    assignment_id: Mapped[int] = mapped_column(Integer, ForeignKey("assignments.id", ondelete="CASCADE"), primary_key=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    reference_answer: Mapped[str | None] = mapped_column(Text)
    grading_criteria: Mapped[str | None] = mapped_column(Text)
    accepted_formats: Mapped[list[str]] = mapped_column(ARRAY(String(20)), nullable=False, default=list)

    assignment: Mapped["Assignment"] = relationship(back_populates="homework_details")

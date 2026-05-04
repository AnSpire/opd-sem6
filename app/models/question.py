import enum

from sqlalchemy import Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class QuestionType(str, enum.Enum):
    single = "single"
    multi = "multi"
    bool = "bool"
    short_text = "short_text"


class ShortTextMatch(str, enum.Enum):
    exact = "exact"
    case_insensitive = "case_insensitive"


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assignment_id: Mapped[int] = mapped_column(Integer, ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[QuestionType] = mapped_column(Enum(QuestionType, name="question_type"), nullable=False)
    options: Mapped[dict | None] = mapped_column(JSONB)
    correct_answer: Mapped[dict] = mapped_column(JSONB, nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    short_text_match: Mapped[ShortTextMatch | None] = mapped_column(Enum(ShortTextMatch, name="short_text_match"))

    assignment: Mapped["Assignment"] = relationship(back_populates="questions")

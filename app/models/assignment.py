import enum
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class AssignmentType(str, enum.Enum):
    homework = "homework"
    test = "test"


class FinalScoreStrategy(str, enum.Enum):
    last = "last"
    best = "best"
    average = "average"


class Assignment(TimestampMixin, Base):
    __tablename__ = "assignments"
    __table_args__ = (
        Index("ix_assignments_widget_created", "widget_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    widget_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("widgets.id", ondelete="CASCADE"), nullable=False)
    creator_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    type: Mapped[AssignmentType] = mapped_column(Enum(AssignmentType, name="assignment_type"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    allow_late_submissions: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_attempts: Mapped[int | None] = mapped_column(Integer)
    final_score_strategy: Mapped[FinalScoreStrategy] = mapped_column(
        Enum(FinalScoreStrategy, name="final_score_strategy"),
        default=FinalScoreStrategy.best,
        nullable=False,
    )
    max_score: Mapped[int] = mapped_column(Integer, nullable=False)

    widget: Mapped["Widget"] = relationship(back_populates="assignments")
    questions: Mapped[list["Question"]] = relationship(  # noqa: F821
        back_populates="assignment", cascade="all, delete-orphan"
    )
    homework_details: Mapped["HomeworkDetails | None"] = relationship(  # noqa: F821
        back_populates="assignment", cascade="all, delete-orphan", uselist=False
    )

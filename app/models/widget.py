from sqlalchemy import BigInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Widget(TimestampMixin, Base):
    __tablename__ = "widgets"
    __table_args__ = (UniqueConstraint("board_id", "creator_user_id", name="uq_widget_board_creator"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    board_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    creator_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    assignments: Mapped[list["Assignment"]] = relationship(  # noqa: F821
        back_populates="widget", cascade="all, delete-orphan"
    )

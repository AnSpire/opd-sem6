from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class StatsModule(TimestampMixin, Base):
    __tablename__ = "stats_module"

    module_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    module_name: Mapped[str] = mapped_column(String(255), nullable=False)
    token: Mapped[str] = mapped_column(Text, nullable=False)
    token_expired: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

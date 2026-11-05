"""Key-value persistent system settings & worker runtime heartbeats."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.utils.time import utcnow


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    # general | retry | storage | security | backup | runtime
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="general", index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

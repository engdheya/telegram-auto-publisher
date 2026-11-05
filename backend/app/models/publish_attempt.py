"""Audit history of every execution/reconciliation attempt on a PublishJob."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.utils.time import utcnow


class PublishAttempt(Base):
    __tablename__ = "publish_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    publish_job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("publish_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_id: Mapped[str] = mapped_column(String(80), nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # IN_FLIGHT | PUBLISHED | RETRY_WAIT | FAILED | SKIPPED | UNKNOWN | RECONCILED_PUBLISHED | RECONCILED_CLEAR
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, default="IN_FLIGHT")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_response_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    publish_job = relationship("PublishJob", back_populates="attempts")

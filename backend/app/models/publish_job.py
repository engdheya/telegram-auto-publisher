"""Persistent per-target publish queue jobs with 7-state lifecycle and UNKNOWN reconciliation."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.utils.time import utcnow

JOB_STATES = ("QUEUED", "PROCESSING", "PUBLISHED", "RETRY_WAIT", "SKIPPED", "FAILED", "UNKNOWN")


class PublishJob(Base):
    __tablename__ = "publish_jobs"
    __table_args__ = (
        UniqueConstraint("message_event_id", "target_channel_id", name="uq_job_event_target"),
        Index("ix_jobs_poll", "status", "next_retry_at", "created_at"),
        Index("ix_jobs_target_status", "target_channel_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("message_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    route_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("publishing_routes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_channel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("source_channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_channel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("target_channels.id", ondelete="CASCADE"), nullable=False, index=True
    )

    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    # QUEUED | PROCESSING | PUBLISHED | RETRY_WAIT | SKIPPED | FAILED | UNKNOWN
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="QUEUED", index=True)

    transformed_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    transformed_entities_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    target_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    target_message_ids_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    attempts_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    locked_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    unknown_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reconciliation_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    message_event = relationship("MessageEvent", back_populates="publish_jobs")
    route = relationship("PublishingRoute", back_populates="publish_jobs")
    source_channel = relationship("SourceChannel")
    target_channel = relationship("TargetChannel")
    attempts = relationship(
        "PublishAttempt",
        back_populates="publish_job",
        cascade="all, delete-orphan",
        order_by="PublishAttempt.attempt_number.asc()",
    )

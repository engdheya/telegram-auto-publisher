"""Persisted incoming Telegram messages & album groups prior to queue dispatch."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.utils.time import utcnow


class MessageEvent(Base):
    __tablename__ = "message_events"
    __table_args__ = (
        UniqueConstraint("source_channel_id", "telegram_message_id", name="uq_event_source_msg_id"),
        Index("ix_events_source_grouped", "source_channel_id", "grouped_id"),
        Index("ix_events_album_collect", "album_status", "album_collect_until"),
        Index("ix_events_received_at", "received_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_channel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("source_channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    grouped_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    dedup_key: Mapped[str] = mapped_column(String(140), unique=True, nullable=False, index=True)

    # text | photo | video | document | audio | voice | album | unsupported
    content_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    entities_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    is_protected_content: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    protection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # SINGLE | COLLECTING | READY
    album_status: Mapped[str] = mapped_column(String(24), nullable=False, default="SINGLE", index=True)
    album_collect_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    album_item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source_channel = relationship("SourceChannel", back_populates="message_events")
    media_items = relationship(
        "MessageMedia",
        back_populates="message_event",
        cascade="all, delete-orphan",
        order_by="MessageMedia.position.asc()",
    )
    publish_jobs = relationship("PublishJob", back_populates="message_event", cascade="all, delete-orphan")

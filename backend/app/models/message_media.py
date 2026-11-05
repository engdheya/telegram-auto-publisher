"""Media items belonging to a single message or multi-item album (`grouped_id`)."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.utils.time import utcnow


class MessageMedia(Base):
    __tablename__ = "message_media"
    __table_args__ = (
        UniqueConstraint("source_channel_id", "telegram_message_id", name="uq_media_source_msg_id"),
        Index("ix_media_event_pos", "message_event_id", "position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("message_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_channel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("source_channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # photo | video | document | audio | voice
    media_type: Mapped[str] = mapped_column(String(32), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_ext: Mapped[str | None] = mapped_column(String(24), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    caption_entities_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    local_cache_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    # READY | PENDING_DOWNLOAD | DOWNLOAD_FAILED | PROTECTED
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="READY")
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    message_event = relationship("MessageEvent", back_populates="media_items")

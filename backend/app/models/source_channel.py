"""Source Telegram channels monitored for new posts (with documented baseline_message_id)."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.utils.time import utcnow


class SourceChannel(Base):
    __tablename__ = "source_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    identifier: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    telegram_peer_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True, index=True)
    invite_link: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    # ACTIVE | PAUSED | UNVERIFIED | ERROR
    monitoring_status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNVERIFIED", index=True)

    # Documented starting point so historical archive is NEVER imported on first run
    baseline_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_processed_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    noforwards_protected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    access_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    routes = relationship("PublishingRoute", back_populates="source_channel", cascade="all, delete-orphan")
    message_events = relationship("MessageEvent", back_populates="source_channel", cascade="all, delete-orphan")

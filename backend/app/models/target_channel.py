"""Target Telegram channels where processed posts are published."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.utils.time import utcnow


class TargetChannel(Base):
    __tablename__ = "target_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    identifier: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    telegram_peer_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True, index=True)
    invite_link: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    # VERIFIED | INSUFFICIENT_PERMISSIONS | UNVERIFIED | ERROR
    permission_status: Mapped[str] = mapped_column(String(40), nullable=False, default="UNVERIFIED", index=True)
    can_post_messages: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_post_media: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_post_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    routes = relationship("PublishingRoute", back_populates="target_channel", cascade="all, delete-orphan")

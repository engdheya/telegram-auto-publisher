"""Encrypted Telegram account & session model (session string is NEVER returned in plaintext)."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.utils.time import utcnow


class TelegramAccount(Base):
    __tablename__ = "telegram_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False, default="Primary Account")
    api_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_hash_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    encrypted_session: Mapped[str | None] = mapped_column(Text, nullable=True)
    pending_session_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone_code_hash_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    # States: UNCONFIGURED | DISCONNECTED | AWAITING_CODE | AWAITING_PASSWORD | CONNECTED | AUTH_ERROR
    auth_state: Mapped[str] = mapped_column(String(32), nullable=False, default="UNCONFIGURED", index=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    telegram_display_name: Mapped[str | None] = mapped_column(String(160), nullable=True)

    is_connected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_reconnect: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reconnect_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

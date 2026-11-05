"""Telegram account management schemas (never exposes session or api_hash)."""

from datetime import datetime

from pydantic import BaseModel, Field


class TelegramCredentialsRequest(BaseModel):
    label: str = Field(default="Primary Telegram Account", min_length=1, max_length=120)
    api_id: int = Field(..., gt=0, description="Telegram numeric API ID from my.telegram.org")
    api_hash: str = Field(..., min_length=16, max_length=128, description="Telegram API Hash")
    phone_number: str = Field(..., min_length=6, max_length=32, pattern=r"^\+?[0-9\s-]{6,30}$")
    auto_reconnect: bool = True


class TelegramVerifyCodeRequest(BaseModel):
    code: str = Field(..., min_length=3, max_length=16)
    password: str | None = Field(default=None, max_length=256, description="Optional 2FA Cloud Password")


class TelegramPasswordRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=256, description="Telegram 2FA Cloud Password")


class TelegramAutoReconnectUpdate(BaseModel):
    auto_reconnect: bool


class TelegramAccountStatusResponse(BaseModel):
    id: int
    label: str
    api_id: int | None = None
    has_api_hash: bool = False
    masked_phone: str | None = None
    has_saved_session: bool = False
    auth_state: str
    telegram_user_id: int | None = None
    telegram_username: str | None = None
    telegram_display_name: str | None = None
    is_connected: bool
    live_transport_connected: bool = False
    auto_reconnect: bool
    reconnect_attempts: int
    last_connected_at: datetime | None = None
    last_disconnected_at: datetime | None = None
    heartbeat_at: datetime | None = None
    last_error: str | None = None
    updated_at: datetime

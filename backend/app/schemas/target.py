"""Target channel management schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TargetChannelCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    identifier: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Channel @username, t.me link, or numeric peer ID",
    )
    invite_link: str | None = Field(default=None, max_length=255)
    is_enabled: bool = True


class TargetChannelUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    identifier: str | None = Field(default=None, min_length=2, max_length=200)
    invite_link: str | None = Field(default=None, max_length=255)
    is_enabled: bool | None = None


class TargetChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    identifier: str
    username: str | None = None
    telegram_peer_id: int | None = None
    invite_link: str | None = None
    is_enabled: bool
    permission_status: str
    can_post_messages: bool
    can_post_media: bool
    last_verified_at: datetime | None = None
    last_test_post_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class TargetTestPublishRequest(BaseModel):
    message: str = Field(
        default="✅ رسالة اختبار صلاحيات النشر من Telegram Auto Publisher / Test post",
        min_length=1,
        max_length=1000,
    )


class TargetVerifyResponse(BaseModel):
    ok: bool
    target: TargetChannelRead
    detail: str
    test_message_id: int | None = None

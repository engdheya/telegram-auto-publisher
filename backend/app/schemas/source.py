"""Source channel management schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SourceChannelCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    identifier: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Channel @username, t.me link, or numeric peer ID (e.g. -1001234567890)",
    )
    invite_link: str | None = Field(default=None, max_length=255)
    is_enabled: bool = True


class SourceChannelUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    identifier: str | None = Field(default=None, min_length=2, max_length=200)
    invite_link: str | None = Field(default=None, max_length=255)
    is_enabled: bool | None = None


class SourceChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    identifier: str
    username: str | None = None
    telegram_peer_id: int | None = None
    invite_link: str | None = None
    is_enabled: bool
    monitoring_status: str
    baseline_message_id: int | None = None
    last_processed_message_id: int | None = None
    last_processed_at: datetime | None = None
    noforwards_protected: bool
    access_verified_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class SourceVerifyResponse(BaseModel):
    accessible: bool
    source: SourceChannelRead
    detail: str

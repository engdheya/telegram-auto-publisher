"""Publishing routes & filter rule schemas supporting 1->N, N->1, and N->N topologies."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AllowedContentType = Literal["text", "photo", "video", "document", "audio", "voice", "album"]

ALL_CONTENT_TYPES: list[AllowedContentType] = [
    "text",
    "photo",
    "video",
    "document",
    "audio",
    "voice",
    "album",
]


class RouteFilterPayload(BaseModel):
    allowed_content_types: list[AllowedContentType] = Field(default_factory=lambda: list(ALL_CONTENT_TYPES))
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    allowed_extensions: list[str] = Field(default_factory=list)
    min_text_length: int | None = Field(default=None, ge=0, le=10000)
    max_text_length: int | None = Field(default=None, ge=1, le=20000)
    prefix_text: str | None = Field(default=None, max_length=1000)
    suffix_text: str | None = Field(default=None, max_length=1000)
    target_signature: str | None = Field(default=None, max_length=500)
    strip_urls: bool = False


class PublishingRouteCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    source_channel_id: int = Field(..., gt=0)
    target_channel_id: int = Field(..., gt=0)
    is_enabled: bool = True
    priority: int = Field(default=100, ge=1, le=1000)
    filters: RouteFilterPayload = Field(default_factory=RouteFilterPayload)


class BulkRouteCreateRequest(BaseModel):
    """Allows linking multiple sources to multiple targets in one atomic request."""

    name_prefix: str = Field(default="Route", min_length=1, max_length=120)
    source_channel_ids: list[int] = Field(..., min_length=1)
    target_channel_ids: list[int] = Field(..., min_length=1)
    is_enabled: bool = True
    filters: RouteFilterPayload = Field(default_factory=RouteFilterPayload)


class PublishingRouteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    is_enabled: bool | None = None
    priority: int | None = Field(default=None, ge=1, le=1000)
    filters: RouteFilterPayload | None = None


class PublishingRouteRead(BaseModel):
    id: int
    name: str
    description: str | None = None
    source_channel_id: int
    source_title: str
    source_identifier: str
    target_channel_id: int
    target_title: str
    target_identifier: str
    is_enabled: bool
    priority: int
    filters: RouteFilterPayload
    created_at: datetime
    updated_at: datetime

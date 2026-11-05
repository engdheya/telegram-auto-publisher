"""Message Event, Media, Publish Job, and Attempt read schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MessageMediaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_message_id: int
    position: int
    media_type: str
    file_name: str | None = None
    mime_type: str | None = None
    file_ext: str | None = None
    file_size: int | None = None
    duration_seconds: int | None = None
    width: int | None = None
    height: int | None = None
    caption: str | None = None
    status: str
    error_reason: str | None = None


class PublishAttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    attempt_number: int
    worker_id: str
    started_at: datetime
    finished_at: datetime | None = None
    outcome: str
    error_code: str | None = None
    error_message: str | None = None


class PublishJobSummaryRead(BaseModel):
    id: int
    message_event_id: int
    route_id: int
    route_name: str
    source_channel_id: int
    source_title: str
    target_channel_id: int
    target_title: str
    status: str
    transformed_text: str | None = None
    target_message_id: int | None = None
    target_message_ids: list[int] = []
    attempts_count: int
    max_attempts: int
    next_retry_at: datetime | None = None
    skip_reason: str | None = None
    last_error: str | None = None
    unknown_reason: str | None = None
    reconciliation_checked_at: datetime | None = None
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PublishJobDetailRead(PublishJobSummaryRead):
    content_type: str
    raw_text: str | None = None
    grouped_id: str | None = None
    album_item_count: int = 1
    attempts: list[PublishAttemptRead] = []


class MessageEventRead(BaseModel):
    id: int
    source_channel_id: int
    source_title: str
    telegram_message_id: int
    grouped_id: str | None = None
    content_type: str
    raw_text: str | None = None
    is_protected_content: bool
    protection_reason: str | None = None
    album_status: str
    album_item_count: int
    source_published_at: datetime | None = None
    received_at: datetime
    enqueued_at: datetime | None = None
    media_items: list[MessageMediaRead] = []
    jobs: list[PublishJobSummaryRead] = []


class PaginatedMessagesResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[MessageEventRead]


class PaginatedJobsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    counts_by_status: dict[str, int]
    items: list[PublishJobDetailRead]


class QueueActionResponse(BaseModel):
    ok: bool
    detail: str
    job: PublishJobDetailRead

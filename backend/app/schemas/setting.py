"""Audit log and System settings schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditLogRead(BaseModel):
    id: int
    level: str
    category: str
    action: str
    actor_user_id: int | None = None
    actor_username: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    message: str
    details: dict[str, Any]
    ip_address: str | None = None
    created_at: datetime


class PaginatedLogsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[AuditLogRead]


class SystemSettingUpdateItem(BaseModel):
    key: str = Field(..., min_length=2, max_length=100)
    value: Any


class SystemSettingsBulkUpdate(BaseModel):
    settings: list[SystemSettingUpdateItem]


class BackupCreateRequest(BaseModel):
    label: str | None = Field(default=None, max_length=32)


class BackupRestoreRequest(BaseModel):
    filename: str = Field(..., min_length=4, max_length=200)

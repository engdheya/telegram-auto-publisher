"""Dashboard overview statistics & system health response schema."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.setting import AuditLogRead


class DashboardOverviewResponse(BaseModel):
    telegram_connected: bool
    telegram_auth_state: str
    telegram_display_name: str | None = None
    telegram_username: str | None = None
    worker_alive: bool
    worker_last_heartbeat: datetime | None = None
    sources_total: int
    sources_active: int
    targets_total: int
    targets_verified: int
    routes_total: int
    routes_active: int
    messages_received_total: int
    jobs_published: int
    jobs_failed: int
    jobs_waiting: int
    jobs_processing: int
    jobs_skipped: int
    jobs_unknown: int
    database_health: dict[str, Any]
    recent_activities: list[AuditLogRead]

"""Dashboard summary statistics and system health endpoint."""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.integrity import validate_database_integrity
from app.database.session import get_db
from app.models import (
    MessageEvent,
    PublishingRoute,
    SourceChannel,
    TargetChannel,
    User,
)
from app.repositories.audit_repo import AuditRepository
from app.repositories.job_repo import JobRepository
from app.repositories.setting_repo import SettingRepository
from app.schemas.dashboard import DashboardOverviewResponse
from app.services.telegram_service import TelegramAccountService
from app.telegram.gateway import get_telegram_gateway
from app.utils.time import ensure_utc, utcnow

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/overview", response_model=DashboardOverviewResponse)
def get_dashboard_overview(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardOverviewResponse:
    gateway = get_telegram_gateway()
    tg_acc = TelegramAccountService.get_or_create_account(db)

    sources_total = int(db.execute(select(func.count(SourceChannel.id))).scalar() or 0)
    sources_active = int(
        db.execute(
            select(func.count(SourceChannel.id)).where(
                SourceChannel.is_enabled.is_(True), SourceChannel.monitoring_status == "ACTIVE"
            )
        ).scalar()
        or 0
    )

    targets_total = int(db.execute(select(func.count(TargetChannel.id))).scalar() or 0)
    targets_verified = int(
        db.execute(
            select(func.count(TargetChannel.id)).where(
                TargetChannel.is_enabled.is_(True), TargetChannel.permission_status == "VERIFIED"
            )
        ).scalar()
        or 0
    )

    routes_total = int(db.execute(select(func.count(PublishingRoute.id))).scalar() or 0)
    routes_active = int(
        db.execute(select(func.count(PublishingRoute.id)).where(PublishingRoute.is_enabled.is_(True))).scalar()
        or 0
    )

    messages_total = int(db.execute(select(func.count(MessageEvent.id))).scalar() or 0)
    counts = JobRepository.counts_by_status(db)

    hb_raw = SettingRepository.get_value(db, "runtime.worker_heartbeat")
    worker_alive = False
    worker_hb_dt: datetime | None = None
    if isinstance(hb_raw, dict) and hb_raw.get("timestamp"):
        try:
            worker_hb_dt = ensure_utc(datetime.fromisoformat(hb_raw["timestamp"]))
            if worker_hb_dt and (utcnow() - worker_hb_dt).total_seconds() < 25:
                worker_alive = True
        except Exception:
            pass

    _, recent_logs = AuditRepository.list_logs(db, page=1, page_size=12)
    db_health = validate_database_integrity(db)

    return DashboardOverviewResponse(
        telegram_connected=bool(tg_acc.is_connected or gateway.is_live_connected()),
        telegram_auth_state=tg_acc.auth_state,
        telegram_display_name=tg_acc.telegram_display_name,
        telegram_username=tg_acc.telegram_username,
        worker_alive=worker_alive,
        worker_last_heartbeat=worker_hb_dt,
        sources_total=sources_total,
        sources_active=sources_active,
        targets_total=targets_total,
        targets_verified=targets_verified,
        routes_total=routes_total,
        routes_active=routes_active,
        messages_received_total=messages_total,
        jobs_published=counts.get("PUBLISHED", 0),
        jobs_failed=counts.get("FAILED", 0),
        jobs_waiting=counts.get("QUEUED", 0) + counts.get("RETRY_WAIT", 0),
        jobs_processing=counts.get("PROCESSING", 0),
        jobs_skipped=counts.get("SKIPPED", 0),
        jobs_unknown=counts.get("UNKNOWN", 0),
        database_health=db_health,
        recent_activities=recent_logs,
    )

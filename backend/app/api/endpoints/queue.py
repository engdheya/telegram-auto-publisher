"""Queue Management endpoints: inspect jobs, safe manual retry, UNKNOWN reconciliation, and cancel."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.core.exceptions import AppError, ResourceNotFoundError
from app.database.session import get_db
from app.models import MessageEvent, PublishJob, User
from app.repositories.audit_repo import AuditRepository
from app.repositories.job_repo import JobRepository
from app.schemas.message import PaginatedJobsResponse, PublishJobDetailRead, QueueActionResponse
from app.services.publishing_engine import ReconciliationService
from app.telegram.gateway import get_telegram_gateway

router = APIRouter(prefix="/queue", tags=["Queue Management"])


def _load_job_detail_or_404(db: Session, job_id: int) -> PublishJob:
    job = (
        db.execute(
            select(PublishJob)
            .options(
                joinedload(PublishJob.message_event).joinedload(MessageEvent.media_items),
                joinedload(PublishJob.source_channel),
                joinedload(PublishJob.target_channel),
                joinedload(PublishJob.route),
                joinedload(PublishJob.attempts),
            )
            .where(PublishJob.id == job_id)
        )
        .scalars()
        .unique()
        .one_or_none()
    )
    if job is None:
        raise ResourceNotFoundError(f"Publish job #{job_id} not found.")
    return job


@router.get("/jobs", response_model=PaginatedJobsResponse)
def list_queue_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    status: str | None = Query(default=None),
    target_id: int | None = Query(default=None),
    source_id: int | None = Query(default=None),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedJobsResponse:
    stmt = select(PublishJob).options(
        joinedload(PublishJob.message_event).joinedload(MessageEvent.media_items),
        joinedload(PublishJob.source_channel),
        joinedload(PublishJob.target_channel),
        joinedload(PublishJob.route),
        joinedload(PublishJob.attempts),
    )
    count_stmt = select(func.count(PublishJob.id))

    if status:
        statuses = [s.strip().upper() for s in status.split(",") if s.strip()]
        if len(statuses) == 1:
            stmt = stmt.where(PublishJob.status == statuses[0])
            count_stmt = count_stmt.where(PublishJob.status == statuses[0])
        elif statuses:
            stmt = stmt.where(PublishJob.status.in_(statuses))
            count_stmt = count_stmt.where(PublishJob.status.in_(statuses))

    if target_id is not None:
        stmt = stmt.where(PublishJob.target_channel_id == target_id)
        count_stmt = count_stmt.where(PublishJob.target_channel_id == target_id)
    if source_id is not None:
        stmt = stmt.where(PublishJob.source_channel_id == source_id)
        count_stmt = count_stmt.where(PublishJob.source_channel_id == source_id)

    total = int(db.execute(count_stmt).scalar() or 0)
    offset = (page - 1) * page_size
    jobs = (
        db.execute(
            stmt.order_by(PublishJob.updated_at.desc(), PublishJob.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        .scalars()
        .unique()
        .all()
    )
    return PaginatedJobsResponse(
        total=total,
        page=page,
        page_size=page_size,
        counts_by_status=JobRepository.counts_by_status(db),
        items=[JobRepository.to_detail(j) for j in jobs],
    )


@router.get("/jobs/{job_id}", response_model=PublishJobDetailRead)
def get_queue_job(
    job_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PublishJobDetailRead:
    return JobRepository.to_detail(_load_job_detail_or_404(db, job_id))


@router.post("/jobs/{job_id}/retry", response_model=QueueActionResponse)
def retry_queue_job(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QueueActionResponse:
    job, detail = ReconciliationService.safe_manual_retry(db, job_id, actor_username=user.username)
    return QueueActionResponse(ok=True, detail=detail, job=JobRepository.to_detail(_load_job_detail_or_404(db, job.id)))


@router.post("/jobs/{job_id}/reconcile", response_model=QueueActionResponse)
async def reconcile_unknown_queue_job(
    job_id: int,
    requeue_if_missing: bool = Query(default=True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QueueActionResponse:
    gateway = get_telegram_gateway()
    job, detail = await ReconciliationService.reconcile_unknown_job(
        db,
        job_id,
        gateway=gateway,
        requeue_if_missing=requeue_if_missing,
        actor_username=user.username,
    )
    return QueueActionResponse(ok=True, detail=detail, job=JobRepository.to_detail(_load_job_detail_or_404(db, job.id)))


@router.post("/jobs/{job_id}/cancel", response_model=QueueActionResponse)
def cancel_waiting_job(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QueueActionResponse:
    job = _load_job_detail_or_404(db, job_id)
    if job.status in ("PUBLISHED", "PROCESSING"):
        raise AppError(f"Cannot cancel job in '{job.status}' state.")
    job.status = "SKIPPED"
    job.skip_reason = f"CANCELLED_BY_OPERATOR: Cancelled manually by {user.username}."
    job.next_retry_at = None
    job.locked_by = None
    AuditRepository.record(
        db,
        level="INFO",
        category="QUEUE",
        action="JOB_CANCELLED",
        actor_user_id=user.id,
        actor_username=user.username,
        entity_type="publish_job",
        entity_id=job.id,
        message=f"Cancelled job #{job.id}.",
    )
    db.commit()
    return QueueActionResponse(
        ok=True,
        detail=f"Job #{job.id} marked SKIPPED.",
        job=JobRepository.to_detail(_load_job_detail_or_404(db, job.id)),
    )

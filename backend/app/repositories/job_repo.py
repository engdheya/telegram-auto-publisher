"""Persistent queue & message history query/claiming repository."""

import json
from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import JOB_STATES, MessageEvent, PublishAttempt, PublishJob
from app.schemas.message import (
    MessageEventRead,
    MessageMediaRead,
    PublishAttemptRead,
    PublishJobDetailRead,
    PublishJobSummaryRead,
)
from app.utils.time import utcnow


class JobRepository:
    @staticmethod
    def to_summary(job: PublishJob) -> PublishJobSummaryRead:
        try:
            target_ids = json.loads(job.target_message_ids_json or "[]")
        except Exception:
            target_ids = []
        return PublishJobSummaryRead(
            id=job.id,
            message_event_id=job.message_event_id,
            route_id=job.route_id,
            route_name=job.route.name if job.route else f"Route #{job.route_id}",
            source_channel_id=job.source_channel_id,
            source_title=job.source_channel.title if job.source_channel else f"Source #{job.source_channel_id}",
            target_channel_id=job.target_channel_id,
            target_title=job.target_channel.title if job.target_channel else f"Target #{job.target_channel_id}",
            status=job.status,
            transformed_text=job.transformed_text,
            target_message_id=job.target_message_id,
            target_message_ids=target_ids if isinstance(target_ids, list) else [],
            attempts_count=job.attempts_count,
            max_attempts=job.max_attempts,
            next_retry_at=job.next_retry_at,
            skip_reason=job.skip_reason,
            last_error=job.last_error,
            unknown_reason=job.unknown_reason,
            reconciliation_checked_at=job.reconciliation_checked_at,
            published_at=job.published_at,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    @staticmethod
    def to_detail(job: PublishJob) -> PublishJobDetailRead:
        summary = JobRepository.to_summary(job)
        ev = job.message_event
        return PublishJobDetailRead(
            **summary.model_dump(),
            content_type=ev.content_type if ev else "text",
            raw_text=ev.raw_text if ev else None,
            grouped_id=ev.grouped_id if ev else None,
            album_item_count=ev.album_item_count if ev else 1,
            attempts=[PublishAttemptRead.model_validate(a) for a in (job.attempts or [])],
        )

    @staticmethod
    def event_to_read(ev: MessageEvent) -> MessageEventRead:
        return MessageEventRead(
            id=ev.id,
            source_channel_id=ev.source_channel_id,
            source_title=ev.source_channel.title if ev.source_channel else f"Source #{ev.source_channel_id}",
            telegram_message_id=ev.telegram_message_id,
            grouped_id=ev.grouped_id,
            content_type=ev.content_type,
            raw_text=ev.raw_text,
            is_protected_content=ev.is_protected_content,
            protection_reason=ev.protection_reason,
            album_status=ev.album_status,
            album_item_count=ev.album_item_count,
            source_published_at=ev.source_published_at,
            received_at=ev.received_at,
            enqueued_at=ev.enqueued_at,
            media_items=[MessageMediaRead.model_validate(m) for m in (ev.media_items or [])],
            jobs=[JobRepository.to_summary(j) for j in (ev.publish_jobs or [])],
        )

    @staticmethod
    def counts_by_status(db: Session) -> dict[str, int]:
        counts = {s: 0 for s in JOB_STATES}
        rows = db.execute(
            select(PublishJob.status, func.count(PublishJob.id)).group_by(PublishJob.status)
        ).fetchall()
        for st, cnt in rows:
            counts[str(st)] = int(cnt)
        return counts

    @staticmethod
    def claim_next_job(db: Session, worker_id: str) -> tuple[PublishJob, PublishAttempt] | None:
        """Atomically claim the oldest eligible QUEUED or due RETRY_WAIT job."""
        now = utcnow()
        stmt = (
            select(PublishJob)
            .options(
                joinedload(PublishJob.message_event).joinedload(MessageEvent.media_items),
                joinedload(PublishJob.source_channel),
                joinedload(PublishJob.target_channel),
                joinedload(PublishJob.route),
            )
            .where(
                or_(
                    PublishJob.status == "QUEUED",
                    (PublishJob.status == "RETRY_WAIT")
                    & (or_(PublishJob.next_retry_at.is_(None), PublishJob.next_retry_at <= now)),
                )
            )
            .order_by(PublishJob.created_at.asc(), PublishJob.id.asc())
            .limit(1)
        )
        job = db.execute(stmt).scalars().unique().first()
        if job is None:
            return None

        job.status = "PROCESSING"
        job.locked_by = worker_id
        job.locked_at = now
        job.heartbeat_at = now
        job.attempts_count = (job.attempts_count or 0) + 1
        job.updated_at = now

        attempt = PublishAttempt(
            publish_job_id=job.id,
            attempt_number=job.attempts_count,
            worker_id=worker_id,
            started_at=now,
            outcome="IN_FLIGHT",
        )
        db.add(attempt)
        db.commit()
        db.refresh(job)
        db.refresh(attempt)
        return job, attempt

    @staticmethod
    def recover_stale_processing_jobs(db: Session, stale_timeout_seconds: int = 180) -> list[PublishJob]:
        """
        Transition stale PROCESSING jobs (after process crash or abrupt restart) to UNKNOWN
        rather than blindly re-queuing them, preventing silent duplicate posts!
        """
        cutoff = utcnow() - timedelta(seconds=stale_timeout_seconds)
        stmt = select(PublishJob).where(
            PublishJob.status == "PROCESSING",
            or_(PublishJob.heartbeat_at.is_(None), PublishJob.heartbeat_at <= cutoff),
        )
        stale_jobs = list(db.execute(stmt).scalars().all())
        now = utcnow()
        for job in stale_jobs:
            job.status = "UNKNOWN"
            job.unknown_reason = (
                "Worker terminated or lost heartbeat while job was PROCESSING; "
                "reconciliation required before retrying to avoid duplicate Telegram post."
            )
            job.locked_by = None
            job.updated_at = now
            for att in job.attempts:
                if att.outcome == "IN_FLIGHT":
                    att.outcome = "UNKNOWN"
                    att.finished_at = now
                    att.error_code = "STALE_LOCK_RECOVERY"
                    att.error_message = job.unknown_reason
        if stale_jobs:
            db.commit()
        return stale_jobs

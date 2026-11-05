"""Independent per-target Publishing Engine & UNKNOWN State Reconciliation Service."""

import json
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.exceptions import (
    AmbiguousPublishError,
    AppError,
    PermanentPublishError,
    ResourceNotFoundError,
    TransientPublishError,
)
from app.models import MessageEvent, PublishAttempt, PublishJob
from app.repositories.audit_repo import AuditRepository
from app.repositories.job_repo import JobRepository
from app.repositories.setting_repo import SettingRepository
from app.telegram.gateway import TelegramGatewayProtocol
from app.utils.time import compute_backoff_seconds, ensure_utc, utcnow


class PublishingEngine:
    """
    Processes persistent queue jobs independently per target.
    Failure on Target B NEVER triggers republication on Target A.
    """

    @staticmethod
    async def process_next_job(
        db: Session, gateway: TelegramGatewayProtocol, worker_id: str | None = None
    ) -> PublishJob | None:
        wid = worker_id or get_settings().WORKER_ID
        claimed = JobRepository.claim_next_job(db, worker_id=wid)
        if claimed is None:
            return None

        job, attempt = claimed
        await PublishingEngine.execute_claimed_job(db, job, attempt, gateway)
        return job

    @staticmethod
    async def execute_claimed_job(
        db: Session,
        job: PublishJob,
        attempt: PublishAttempt,
        gateway: TelegramGatewayProtocol,
    ) -> PublishJob:
        now = utcnow()
        target = job.target_channel
        source = job.source_channel
        event = job.message_event

        if target is None or not target.is_enabled:
            job.status = "SKIPPED"
            job.skip_reason = "TARGET_DISABLED: Target channel was disabled before execution."
            job.locked_by = None
            attempt.outcome = "SKIPPED"
            attempt.finished_at = now
            attempt.error_code = "TARGET_DISABLED"
            attempt.error_message = job.skip_reason
            db.commit()
            return job

        if event is None or event.is_protected_content:
            job.status = "SKIPPED"
            job.skip_reason = (
                event.protection_reason
                if event and event.protection_reason
                else "PROTECTED_CONTENT_NOFORWARDS"
            )
            job.locked_by = None
            attempt.outcome = "SKIPPED"
            attempt.finished_at = now
            attempt.error_code = "PROTECTED_CONTENT"
            attempt.error_message = job.skip_reason
            db.commit()
            return job

        # Sort media deterministically by position / telegram_message_id
        sorted_media = sorted(
            event.media_items or [],
            key=lambda m: (m.position, m.telegram_message_id),
        )
        valid_media = [m for m in sorted_media if m.status != "DOWNLOAD_FAILED"]
        if event.content_type != "text" and len(valid_media) == 0:
            job.status = "FAILED"
            job.last_error = "MEDIA_PREPARATION_FAILED: No valid media items available for publishing."
            job.locked_by = None
            attempt.outcome = "FAILED"
            attempt.finished_at = now
            attempt.error_code = "MEDIA_PREPARATION_FAILED"
            attempt.error_message = job.last_error
            db.commit()
            return job

        source_ref: str | int = (
            source.telegram_peer_id if source and source.telegram_peer_id is not None else (source.identifier if source else "")
        )
        target_ref: str | int = (
            target.telegram_peer_id if target.telegram_peer_id is not None else target.identifier
        )
        source_msg_ids = (
            [m.telegram_message_id for m in valid_media]
            if valid_media
            else [event.telegram_message_id]
        )
        media_descriptors = [
            {
                "telegram_message_id": m.telegram_message_id,
                "media_type": m.media_type,
                "file_name": m.file_name,
                "mime_type": m.mime_type,
                "file_ext": m.file_ext,
                "local_cache_path": m.local_cache_path,
            }
            for m in valid_media
        ]

        try:
            sent_ids = await gateway.publish_job_payload(
                target_identifier=target_ref,
                source_identifier=source_ref,
                content_type=event.content_type,
                text=job.transformed_text or "",
                entities_json=job.transformed_entities_json or "[]",
                source_message_ids=source_msg_ids,
                media_descriptors=media_descriptors,
            )

            finished = utcnow()
            job.status = "PUBLISHED"
            job.target_message_id = sent_ids[0] if sent_ids else None
            job.target_message_ids_json = json.dumps(sent_ids)
            job.published_at = finished
            job.last_error = None
            job.unknown_reason = None
            job.locked_by = None
            job.updated_at = finished

            attempt.outcome = "PUBLISHED"
            attempt.finished_at = finished
            attempt.telegram_response_json = json.dumps({"target_message_ids": sent_ids})

            AuditRepository.record(
                db,
                level="INFO",
                category="PUBLISHER",
                action="JOB_PUBLISHED",
                entity_type="publish_job",
                entity_id=job.id,
                message=f"Published job #{job.id} ({event.content_type}) to '{target.title}' (msg_id={job.target_message_id}).",
                details={
                    "job_id": job.id,
                    "event_id": event.id,
                    "target_id": target.id,
                    "target_message_ids": sent_ids,
                },
            )
            db.commit()
            return job

        except TransientPublishError as exc:
            finished = utcnow()
            base_sec = int(
                SettingRepository.get_value(
                    db, "retry.base_seconds", get_settings().PUBLISH_RETRY_BASE_SECONDS
                )
            )
            max_sec = int(
                SettingRepository.get_value(
                    db, "retry.max_seconds", get_settings().PUBLISH_RETRY_MAX_SECONDS
                )
            )
            max_attempts = int(
                SettingRepository.get_value(
                    db, "retry.max_attempts", job.max_attempts or get_settings().PUBLISH_MAX_ATTEMPTS
                )
            )
            job.max_attempts = max_attempts
            job.locked_by = None
            job.last_error = exc.message

            if job.attempts_count < max_attempts:
                delay = (
                    exc.retry_after_seconds
                    if exc.retry_after_seconds is not None
                    else compute_backoff_seconds(job.attempts_count, base_sec, max_sec)
                )
                job.status = "RETRY_WAIT"
                job.next_retry_at = finished + timedelta(seconds=delay)
                attempt.outcome = "RETRY_WAIT"
                AuditRepository.record(
                    db,
                    level="WARNING",
                    category="PUBLISHER",
                    action="JOB_RETRY_SCHEDULED",
                    entity_type="publish_job",
                    entity_id=job.id,
                    message=f"Job #{job.id} scheduled for retry ({job.attempts_count}/{max_attempts}) in {delay}s: {exc.message}",
                )
            else:
                job.status = "FAILED"
                attempt.outcome = "FAILED"
                AuditRepository.record(
                    db,
                    level="ERROR",
                    category="PUBLISHER",
                    action="JOB_MAX_RETRIES_EXHAUSTED",
                    entity_type="publish_job",
                    entity_id=job.id,
                    message=f"Job #{job.id} failed permanently after {job.attempts_count} attempts: {exc.message}",
                )

            attempt.finished_at = finished
            attempt.error_code = exc.code
            attempt.error_message = exc.message
            db.commit()
            return job

        except PermanentPublishError as exc:
            finished = utcnow()
            job.locked_by = None
            if exc.code == "PROTECTED_CONTENT":
                job.status = "SKIPPED"
                job.skip_reason = exc.message
                attempt.outcome = "SKIPPED"
            else:
                job.status = "FAILED"
                job.last_error = exc.message
                target.last_error = exc.message
                attempt.outcome = "FAILED"

            attempt.finished_at = finished
            attempt.error_code = exc.code
            attempt.error_message = exc.message
            AuditRepository.record(
                db,
                level="ERROR" if job.status == "FAILED" else "WARNING",
                category="PUBLISHER",
                action=f"JOB_{job.status}",
                entity_type="publish_job",
                entity_id=job.id,
                message=f"Job #{job.id} -> {job.status} on '{target.title}': {exc.message}",
            )
            db.commit()
            return job

        except AmbiguousPublishError as exc:
            finished = utcnow()
            job.status = "UNKNOWN"
            job.unknown_reason = exc.message
            job.last_error = exc.message
            job.locked_by = None
            attempt.outcome = "UNKNOWN"
            attempt.finished_at = finished
            attempt.error_code = "AMBIGUOUS_DELIVERY"
            attempt.error_message = exc.message

            AuditRepository.record(
                db,
                level="WARNING",
                category="QUEUE",
                action="JOB_MARKED_UNKNOWN",
                entity_type="publish_job",
                entity_id=job.id,
                message=(
                    f"Job #{job.id} entered UNKNOWN state due to post-send network ambiguity; "
                    "automatic blind retry halted pending target channel reconciliation."
                ),
                details={"job_id": job.id, "target_id": target.id, "reason": exc.message},
            )
            db.commit()
            return job


class ReconciliationService:
    """
    Reconciles UNKNOWN jobs by inspecting recent target channel posts before allowing retry.
    Prevents duplicate posts when the app crashed or timed out after Telegram accepted the message.
    """

    @staticmethod
    async def reconcile_unknown_job(
        db: Session,
        job_id: int,
        gateway: TelegramGatewayProtocol,
        *,
        requeue_if_missing: bool = False,
        actor_username: str = "system",
    ) -> tuple[PublishJob, str]:
        job = (
            db.execute(
                select(PublishJob)
                .options(
                    joinedload(PublishJob.message_event).joinedload(MessageEvent.media_items),
                    joinedload(PublishJob.target_channel),
                    joinedload(PublishJob.source_channel),
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
            raise ResourceNotFoundError(f"Job #{job_id} not found.")
        if job.status != "UNKNOWN":
            raise AppError(f"Reconciliation only applies to UNKNOWN jobs (current status: {job.status}).")

        target = job.target_channel
        event = job.message_event
        if target is None or event is None:
            raise AppError("Job is missing target channel or source event metadata.")

        target_ref: str | int = (
            target.telegram_peer_id if target.telegram_peer_id is not None else target.identifier
        )
        recent_posts = await gateway.fetch_recent_target_posts(target_ref, limit=25)

        earliest_attempt_time = ensure_utc(job.created_at) - timedelta(seconds=10)
        if job.attempts:
            first_start = ensure_utc(job.attempts[-1].started_at)
            if first_start:
                earliest_attempt_time = first_start - timedelta(seconds=10)

        expected_text = (job.transformed_text or "").strip()
        expects_media = event.content_type != "text"
        expected_media_count = len(event.media_items) if event.content_type == "album" else (1 if expects_media else 0)

        matched_post = None
        for post in recent_posts:
            post_dt = ensure_utc(post.published_at)
            if post_dt and earliest_attempt_time and post_dt < earliest_attempt_time:
                continue
            if expects_media != post.has_media:
                continue
            if expected_text:
                if post.text == expected_text:
                    matched_post = post
                    break
            elif expects_media and post.media_count == expected_media_count:
                matched_post = post
                break

        now = utcnow()
        job.reconciliation_checked_at = now

        if matched_post is not None:
            job.status = "PUBLISHED"
            job.target_message_id = matched_post.message_id
            job.target_message_ids_json = json.dumps([matched_post.message_id])
            job.published_at = ensure_utc(matched_post.published_at) or now
            job.unknown_reason = None
            job.last_error = None

            db.add(
                PublishAttempt(
                    publish_job_id=job.id,
                    attempt_number=(job.attempts_count or 0) + 1,
                    worker_id=f"reconciler:{actor_username}",
                    started_at=now,
                    finished_at=now,
                    outcome="RECONCILED_PUBLISHED",
                    telegram_response_json=json.dumps({"reconciled_message_id": matched_post.message_id}),
                )
            )
            detail = (
                f"Reconciled as PUBLISHED: found matching post (msg_id={matched_post.message_id}) in '{target.title}'. "
                "Duplicate republication avoided."
            )
            AuditRepository.record(
                db,
                level="INFO",
                category="QUEUE",
                action="UNKNOWN_RECONCILED_PUBLISHED",
                actor_username=actor_username,
                entity_type="publish_job",
                entity_id=job.id,
                message=detail,
            )
            db.commit()
            db.refresh(job)
            return job, detail

        # Not found in target channel recent history
        db.add(
            PublishAttempt(
                publish_job_id=job.id,
                attempt_number=(job.attempts_count or 0) + 1,
                worker_id=f"reconciler:{actor_username}",
                started_at=now,
                finished_at=now,
                outcome="RECONCILED_CLEAR",
            )
        )
        if requeue_if_missing:
            job.status = "QUEUED"
            job.next_retry_at = None
            job.unknown_reason = None
            detail = (
                f"Verified post was NOT present in '{target.title}' recent history; "
                "job safely re-queued for publishing."
            )
            AuditRepository.record(
                db,
                level="INFO",
                category="QUEUE",
                action="UNKNOWN_RECONCILED_REQUEUED",
                actor_username=actor_username,
                entity_type="publish_job",
                entity_id=job.id,
                message=detail,
            )
        else:
            detail = (
                f"No matching post found in '{target.title}' recent messages. "
                "Safe to trigger Requeue & Retry if desired."
            )
            AuditRepository.record(
                db,
                level="INFO",
                category="QUEUE",
                action="UNKNOWN_RECONCILED_NOT_FOUND",
                actor_username=actor_username,
                entity_type="publish_job",
                entity_id=job.id,
                message=detail,
            )

        db.commit()
        db.refresh(job)
        return job, detail

    @staticmethod
    def safe_manual_retry(db: Session, job_id: int, actor_username: str) -> tuple[PublishJob, str]:
        """
        Manual retry strictly for safe states (FAILED, RETRY_WAIT).
        PUBLISHED jobs can NEVER be retried, and UNKNOWN jobs must go through reconcile first!
        """
        job = (
            db.execute(
                select(PublishJob)
                .options(
                    joinedload(PublishJob.message_event).joinedload(MessageEvent.media_items),
                    joinedload(PublishJob.target_channel),
                    joinedload(PublishJob.source_channel),
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
            raise ResourceNotFoundError(f"Job #{job_id} not found.")
        if job.status == "PUBLISHED":
            raise AppError("Cannot retry an already PUBLISHED job; this would duplicate the post.")
        if job.status == "PROCESSING":
            raise AppError("Job is currently PROCESSING.")
        if job.status == "UNKNOWN":
            raise AppError(
                "Job is in UNKNOWN state. Run 'Reconcile & Retry' first so the target channel is checked for duplicates."
            )
        if job.status == "SKIPPED" and job.message_event and job.message_event.is_protected_content:
            raise AppError("Cannot retry protected content (noforwards restriction).")

        job.status = "QUEUED"
        job.next_retry_at = None
        job.last_error = None
        job.locked_by = None
        if job.attempts_count >= job.max_attempts:
            job.max_attempts = job.attempts_count + 2

        detail = f"Job #{job.id} manually queued for retry by {actor_username}."
        AuditRepository.record(
            db,
            level="INFO",
            category="QUEUE",
            action="JOB_MANUAL_RETRY",
            actor_username=actor_username,
            entity_type="publish_job",
            entity_id=job.id,
            message=detail,
        )
        db.commit()
        db.refresh(job)
        return job, detail

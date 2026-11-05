"""Message ingestion, deduplication, album grouping (`grouped_id`), and route job creation."""

import json
from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models import (
    MessageEvent,
    MessageMedia,
    PublishJob,
    PublishingRoute,
    SourceChannel,
)
from app.repositories.audit_repo import AuditRepository
from app.repositories.setting_repo import SettingRepository
from app.services.filter_engine import FilterEngine
from app.telegram.gateway import IncomingTelegramEvent, TelegramGatewayProtocol
from app.utils.time import utcnow


def _canonical_channel_slug(identifier: str | None) -> str | None:
    if not identifier:
        return None
    s = identifier.strip()
    for p in ("https://t.me/", "http://t.me/", "t.me/"):
        if s.lower().startswith(p):
            s = "@" + s[len(p) :].strip("/")
            break
    return s.lower()


class IngestionService:
    @staticmethod
    def resolve_monitored_source(db: Session, incoming: IncomingTelegramEvent) -> SourceChannel | None:
        """Match an incoming Telegram event to an enabled, actively monitored SourceChannel."""
        conditions = []
        if incoming.source_peer_id is not None:
            conditions.append(SourceChannel.telegram_peer_id == incoming.source_peer_id)
            conditions.append(SourceChannel.identifier == str(incoming.source_peer_id))
        slug = _canonical_channel_slug(incoming.source_identifier)
        if slug:
            conditions.append(SourceChannel.identifier.ilike(slug))
            if slug.startswith("@"):
                conditions.append(SourceChannel.username.ilike(slug[1:]))
        if not conditions:
            return None

        stmt = select(SourceChannel).where(
            SourceChannel.is_enabled.is_(True),
            SourceChannel.monitoring_status == "ACTIVE",
            or_(*conditions),
        )
        return db.execute(stmt).scalars().first()

    @staticmethod
    def ingest_event(db: Session, incoming: IncomingTelegramEvent) -> dict[str, Any]:
        """
        Persist incoming message or album part atomically BEFORE queuing jobs.
        Strictly enforces:
        - No old archive import (msg_id <= baseline_message_id ignored)
        - No edit republication (incoming.is_edit ignored)
        - Idempotent deduplication on (source_channel_id, telegram_message_id)
        - Album aggregation via grouped_id
        """
        if incoming.is_edit:
            return {"status": "IGNORED_EDIT"}

        source = IngestionService.resolve_monitored_source(db, incoming)
        if source is None:
            return {"status": "IGNORED_UNMONITORED_SOURCE"}

        # Rule 1 & 2: Documented starting point — never import historical archive
        if source.baseline_message_id is not None and incoming.telegram_message_id <= source.baseline_message_id:
            return {"status": "IGNORED_ARCHIVE_BEFORE_BASELINE", "baseline": source.baseline_message_id}

        # Check duplicate message ID across both message_events and message_media (for album items)
        existing_event = db.execute(
            select(MessageEvent).where(
                MessageEvent.source_channel_id == source.id,
                MessageEvent.telegram_message_id == incoming.telegram_message_id,
            )
        ).scalar_one_or_none()
        if existing_event is not None:
            return {"status": "DUPLICATE_IGNORED", "message_event_id": existing_event.id}

        existing_media = db.execute(
            select(MessageMedia).where(
                MessageMedia.source_channel_id == source.id,
                MessageMedia.telegram_message_id == incoming.telegram_message_id,
            )
        ).scalar_one_or_none()
        if existing_media is not None:
            return {"status": "DUPLICATE_ALBUM_ITEM_IGNORED", "message_event_id": existing_media.message_event_id}

        now = utcnow()
        is_protected = bool(incoming.is_protected_content or source.noforwards_protected)
        protection_reason = incoming.protection_reason or (
            "PROTECTED_CONTENT_NOFORWARDS: Source channel restricts content forwarding/reuse."
            if is_protected
            else None
        )

        # === Album path (grouped_id present) ===
        if incoming.grouped_id:
            window_ms = int(
                SettingRepository.get_value(
                    db, "album.window_ms", get_settings().ALBUM_AGGREGATION_WINDOW_MS
                )
            )
            collect_until = now + timedelta(milliseconds=max(200, window_ms))

            parent_event = db.execute(
                select(MessageEvent)
                .options(joinedload(MessageEvent.media_items))
                .where(
                    MessageEvent.source_channel_id == source.id,
                    MessageEvent.grouped_id == str(incoming.grouped_id),
                )
            ).scalars().unique().first()

            if parent_event is not None:
                if parent_event.album_status == "READY":
                    # Late straggler after album already dispatched: log safely without re-publishing whole album!
                    AuditRepository.record(
                        db,
                        level="WARNING",
                        category="INGESTION",
                        action="ALBUM_LATE_ITEM_SKIPPED",
                        entity_type="message_event",
                        entity_id=parent_event.id,
                        message=f"Late album item msg#{incoming.telegram_message_id} arrived after grouped_id={incoming.grouped_id} was already queued; skipped to avoid duplicating album.",
                        commit=True,
                    )
                    return {"status": "LATE_ALBUM_ITEM_SKIPPED", "message_event_id": parent_event.id}

                if incoming.media:
                    media_row = MessageMedia(
                        message_event_id=parent_event.id,
                        source_channel_id=source.id,
                        telegram_message_id=incoming.telegram_message_id,
                        position=len(parent_event.media_items),
                        media_type=incoming.media.media_type,
                        file_name=incoming.media.file_name,
                        mime_type=incoming.media.mime_type,
                        file_ext=incoming.media.file_ext,
                        file_size=incoming.media.file_size,
                        duration_seconds=incoming.media.duration_seconds,
                        width=incoming.media.width,
                        height=incoming.media.height,
                        caption=incoming.media.caption,
                        caption_entities_json=json.dumps(incoming.media.caption_entities, ensure_ascii=False),
                        local_cache_path=incoming.media.local_cache_path,
                        status="PROTECTED" if is_protected else "READY",
                    )
                    db.add(media_row)

                parent_event.album_item_count = int(parent_event.album_item_count or 1) + 1
                parent_event.album_collect_until = collect_until
                if is_protected:
                    parent_event.is_protected_content = True
                    parent_event.protection_reason = protection_reason
                if (not parent_event.raw_text) and incoming.raw_text:
                    parent_event.raw_text = incoming.raw_text
                    parent_event.entities_json = json.dumps(incoming.entities, ensure_ascii=False)

                # Keep telegram_message_id as minimum of group for deterministic ordering
                if incoming.telegram_message_id < parent_event.telegram_message_id:
                    parent_event.telegram_message_id = incoming.telegram_message_id

                IngestionService._advance_source_cursor(source, incoming.telegram_message_id, now)
                db.commit()
                return {"status": "ALBUM_COLLECTING", "message_event_id": parent_event.id}

            # First item of a new album group
            dedup_key = f"src:{source.id}:grp:{incoming.grouped_id}"
            album_event = MessageEvent(
                source_channel_id=source.id,
                telegram_message_id=incoming.telegram_message_id,
                grouped_id=str(incoming.grouped_id),
                dedup_key=dedup_key,
                content_type="album",
                raw_text=incoming.raw_text or "",
                entities_json=json.dumps(incoming.entities, ensure_ascii=False),
                is_protected_content=is_protected,
                protection_reason=protection_reason,
                album_status="COLLECTING",
                album_collect_until=collect_until,
                album_item_count=1,
                source_published_at=incoming.published_at,
                received_at=now,
            )
            db.add(album_event)
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                return {"status": "DUPLICATE_IGNORED"}

            if incoming.media:
                db.add(
                    MessageMedia(
                        message_event_id=album_event.id,
                        source_channel_id=source.id,
                        telegram_message_id=incoming.telegram_message_id,
                        position=0,
                        media_type=incoming.media.media_type,
                        file_name=incoming.media.file_name,
                        mime_type=incoming.media.mime_type,
                        file_ext=incoming.media.file_ext,
                        file_size=incoming.media.file_size,
                        duration_seconds=incoming.media.duration_seconds,
                        width=incoming.media.width,
                        height=incoming.media.height,
                        caption=incoming.media.caption,
                        caption_entities_json=json.dumps(incoming.media.caption_entities, ensure_ascii=False),
                        local_cache_path=incoming.media.local_cache_path,
                        status="PROTECTED" if is_protected else "READY",
                    )
                )

            IngestionService._advance_source_cursor(source, incoming.telegram_message_id, now)
            db.commit()
            return {"status": "ALBUM_STARTED", "message_event_id": album_event.id}

        # === Single Message / Single Media Path ===
        dedup_key = f"src:{source.id}:msg:{incoming.telegram_message_id}"
        single_event = MessageEvent(
            source_channel_id=source.id,
            telegram_message_id=incoming.telegram_message_id,
            grouped_id=None,
            dedup_key=dedup_key,
            content_type=incoming.content_type,
            raw_text=incoming.raw_text or "",
            entities_json=json.dumps(incoming.entities, ensure_ascii=False),
            is_protected_content=is_protected,
            protection_reason=protection_reason,
            album_status="SINGLE",
            album_item_count=1,
            source_published_at=incoming.published_at,
            received_at=now,
        )
        db.add(single_event)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return {"status": "DUPLICATE_IGNORED"}

        if incoming.media:
            db.add(
                MessageMedia(
                    message_event_id=single_event.id,
                    source_channel_id=source.id,
                    telegram_message_id=incoming.telegram_message_id,
                    position=0,
                    media_type=incoming.media.media_type,
                    file_name=incoming.media.file_name,
                    mime_type=incoming.media.mime_type,
                    file_ext=incoming.media.file_ext,
                    file_size=incoming.media.file_size,
                    duration_seconds=incoming.media.duration_seconds,
                    width=incoming.media.width,
                    height=incoming.media.height,
                    caption=incoming.media.caption,
                    caption_entities_json=json.dumps(incoming.media.caption_entities, ensure_ascii=False),
                    local_cache_path=incoming.media.local_cache_path,
                    status="PROTECTED" if is_protected else "READY",
                )
            )
            db.flush()

        IngestionService._advance_source_cursor(source, incoming.telegram_message_id, now)
        # Step 1 complete: MessageEvent is durably persisted first!
        db.commit()
        db.refresh(single_event)

        # Step 2: Enqueue independent PublishJobs for all active routes of this source
        jobs_created = IngestionService.enqueue_jobs_for_event(db, single_event.id)
        return {
            "status": "ENQUEUED",
            "message_event_id": single_event.id,
            "jobs_created": jobs_created,
        }

    @staticmethod
    def _advance_source_cursor(source: SourceChannel, msg_id: int, ts) -> None:
        if source.baseline_message_id is None:
            # Documented first-seen baseline if source was enabled prior to online check
            source.baseline_message_id = msg_id - 1
        if source.last_processed_message_id is None or msg_id > source.last_processed_message_id:
            source.last_processed_message_id = msg_id
        source.last_processed_at = ts

    @staticmethod
    def finalize_ready_albums(db: Session, force_all: bool = False) -> int:
        """
        Finalize all COLLECTING albums whose aggregation window has elapsed:
        - Sort items strictly by telegram_message_id ASC (preserving original order)
        - Consolidate primary caption & entities
        - Dispatch independent per-route PublishJobs
        """
        now = utcnow()
        stmt = (
            select(MessageEvent)
            .options(joinedload(MessageEvent.media_items))
            .where(MessageEvent.album_status == "COLLECTING")
        )
        if not force_all:
            stmt = stmt.where(MessageEvent.album_collect_until <= now)

        albums = list(db.execute(stmt).scalars().unique().all())
        finalized = 0

        for album in albums:
            sorted_items = sorted(album.media_items, key=lambda m: m.telegram_message_id)
            valid_items = [m for m in sorted_items if m.status != "DOWNLOAD_FAILED"]

            for idx, item in enumerate(sorted_items):
                item.position = idx
                if not album.raw_text and item.caption:
                    album.raw_text = item.caption
                    album.entities_json = item.caption_entities_json

            album.album_item_count = len(sorted_items)
            if sorted_items:
                album.telegram_message_id = sorted_items[0].telegram_message_id

            # If only asingle valid item arrived with grouped_id, downgrade gracefully or keep album
            if len(valid_items) == 0 and not album.is_protected_content:
                album.album_status = "READY"
                album.enqueued_at = now
                AuditRepository.record(
                    db,
                    level="ERROR",
                    category="INGESTION",
                    action="ALBUM_ALL_ITEMS_INVALID",
                    entity_type="message_event",
                    entity_id=album.id,
                    message=f"Album grouped_id={album.grouped_id} had zero valid media items; no jobs queued.",
                )
                db.commit()
                continue

            album.album_status = "READY"
            db.commit()
            IngestionService.enqueue_jobs_for_event(db, album.id)
            finalized += 1

        return finalized

    @staticmethod
    def enqueue_jobs_for_event(db: Session, message_event_id: int) -> int:
        """Create independent PublishJob rows for every enabled route & target matching event's source."""
        event = (
            db.execute(
                select(MessageEvent)
                .options(joinedload(MessageEvent.media_items), joinedload(MessageEvent.source_channel))
                .where(MessageEvent.id == message_event_id)
            )
            .scalars()
            .unique()
            .one_or_none()
        )
        if event is None:
            return 0

        routes = (
            db.execute(
                select(PublishingRoute)
                .options(
                    joinedload(PublishingRoute.route_filter),
                    joinedload(PublishingRoute.target_channel),
                )
                .where(
                    PublishingRoute.source_channel_id == event.source_channel_id,
                    PublishingRoute.is_enabled.is_(True),
                )
                .order_by(PublishingRoute.priority.asc(), PublishingRoute.id.asc())
            )
            .scalars()
            .unique()
            .all()
        )

        max_attempts = int(
            SettingRepository.get_value(db, "retry.max_attempts", get_settings().PUBLISH_MAX_ATTEMPTS)
        )
        created = 0
        now = utcnow()

        for route in routes:
            target = route.target_channel
            if target is None or not target.is_enabled:
                continue

            idem_key = f"event:{event.id}:target:{target.id}"
            existing_job = db.execute(
                select(PublishJob).where(PublishJob.idempotency_key == idem_key)
            ).scalar_one_or_none()
            if existing_job is not None:
                continue

            decision = FilterEngine.evaluate(event, route.route_filter)
            status = "QUEUED" if decision.allowed else "SKIPPED"

            job = PublishJob(
                message_event_id=event.id,
                route_id=route.id,
                source_channel_id=event.source_channel_id,
                target_channel_id=target.id,
                idempotency_key=idem_key,
                status=status,
                transformed_text=decision.transformed_text if decision.allowed else (event.raw_text or ""),
                transformed_entities_json=decision.transformed_entities_json,
                skip_reason=decision.skip_reason,
                max_attempts=max_attempts,
            )
            db.add(job)
            created += 1

            if status == "SKIPPED":
                AuditRepository.record(
                    db,
                    level="INFO",
                    category="PUBLISHER",
                    action="JOB_SKIPPED_BY_POLICY",
                    entity_type="message_event",
                    entity_id=event.id,
                    message=f"Skipped route '{route.name}' -> '{target.title}': {decision.skip_reason}",
                    details={"route_id": route.id, "target_id": target.id, "reason": decision.skip_reason},
                )

        event.enqueued_at = now
        db.commit()
        return created

    @staticmethod
    async def catch_up_missed_messages(db: Session, gateway: TelegramGatewayProtocol) -> dict[str, int]:
        """
        Rule 3: After an outage/reconnect, recover posts published after `last_processed_message_id`
        for active sources that already have a documented baseline (never importing pre-baseline history).
        """
        if not gateway.is_live_connected():
            return {"sources_checked": 0, "events_recovered": 0}

        limit = get_settings().TELEGRAM_CATCHUP_LIMIT
        sources = (
            db.execute(
                select(SourceChannel).where(
                    SourceChannel.is_enabled.is_(True),
                    SourceChannel.monitoring_status == "ACTIVE",
                    SourceChannel.last_processed_message_id.is_not(None),
                )
            )
            .scalars()
            .all()
        )

        recovered_count = 0
        for src in sources:
            min_id = max(int(src.baseline_message_id or 0), int(src.last_processed_message_id or 0))
            ref: str | int = src.telegram_peer_id if src.telegram_peer_id is not None else src.identifier
            try:
                missed = await gateway.fetch_missed_messages(ref, min_message_id=min_id, limit=limit)
                for ev in missed:
                    res = IngestionService.ingest_event(db, ev)
                    if res.get("status") in ("ENQUEUED", "ALBUM_STARTED", "ALBUM_COLLECTING"):
                        recovered_count += 1
            except Exception as exc:
                src.last_error = f"Catch-up failed: {type(exc).__name__}: {exc}"
                db.commit()

        if recovered_count > 0:
            AuditRepository.record(
                db,
                level="INFO",
                category="INGESTION",
                action="RECONNECT_CATCHUP_COMPLETED",
                message=f"Recovered {recovered_count} missed event(s) across {len(sources)} source channel(s).",
                commit=True,
            )
        return {"sources_checked": len(sources), "events_recovered": recovered_count}

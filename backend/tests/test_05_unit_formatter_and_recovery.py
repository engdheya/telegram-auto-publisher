"""Unit tests for UTF-16 Telegram entity shifting, filter edge cases, and stale lock recovery."""

import json

from sqlalchemy.orm import Session

from app.models import MessageEvent, PublishAttempt, PublishJob, PublishingRoute, SourceChannel, TargetChannel
from app.repositories.job_repo import JobRepository
from app.telegram.formatter import deserialize_entities, serialize_entities, transform_text_and_entities
from app.utils.time import compute_backoff_seconds, utcnow


def test_utf16_emoji_prefix_entity_offset_shifting():
    # Emoji '📢' is a surrogate pair (2 UTF-16 code units!)
    raw = "Breaking News"
    entities = [{"type": "bold", "offset": 0, "length": 8}]
    transformed, shifted_json = transform_text_and_entities(
        raw,
        json.dumps(entities),
        prefix_text="📢 Alert:",
        suffix_text="Read more",
        target_signature="@channel",
    )
    shifted = json.loads(shifted_json)
    # "📢 Alert:\n\n" -> '📢'(2) + ' Alert:\n\n'(9) = 11 UTF-16 code units
    assert shifted[0]["offset"] == 11
    assert shifted[0]["length"] == 8
    tl_objs = deserialize_entities(shifted)
    reserialized = serialize_entities(tl_objs)
    assert reserialized == shifted
    assert transformed.startswith("📢 Alert:\n\nBreaking News")
    assert transformed.endswith("Read more\n@channel")


def test_exponential_backoff_bounds():
    assert compute_backoff_seconds(1, base_seconds=15, max_seconds=100) == 15
    assert compute_backoff_seconds(2, base_seconds=15, max_seconds=100) == 30
    assert compute_backoff_seconds(3, base_seconds=15, max_seconds=100) == 60
    assert compute_backoff_seconds(5, base_seconds=15, max_seconds=100) == 100


def test_worker_restart_recovers_stale_processing_jobs_to_unknown(db: Session):
    src = SourceChannel(title="S", identifier="@s_rec", is_enabled=True, monitoring_status="ACTIVE")
    tgt = TargetChannel(title="T", identifier="@t_rec", is_enabled=True, permission_status="VERIFIED")
    db.add_all([src, tgt])
    db.commit()
    rt = PublishingRoute(name="R", source_channel_id=src.id, target_channel_id=tgt.id, is_enabled=True)
    db.add(rt)
    db.commit()
    ev = MessageEvent(
        source_channel_id=src.id,
        telegram_message_id=10,
        dedup_key="src:1:msg:10",
        content_type="text",
        raw_text="In flight when server rebooted",
    )
    db.add(ev)
    db.commit()

    job = PublishJob(
        message_event_id=ev.id,
        route_id=rt.id,
        source_channel_id=src.id,
        target_channel_id=tgt.id,
        idempotency_key="ev:1:tgt:1",
        status="PROCESSING",
        locked_by="crashed-worker",
        locked_at=utcnow(),
        heartbeat_at=utcnow(),
        attempts_count=1,
    )
    db.add(job)
    db.flush()
    db.add(PublishAttempt(publish_job_id=job.id, attempt_number=1, worker_id="crashed-worker", outcome="IN_FLIGHT"))
    db.commit()

    recovered = JobRepository.recover_stale_processing_jobs(db, stale_timeout_seconds=0)
    assert len(recovered) == 1
    assert recovered[0].status == "UNKNOWN"
    assert recovered[0].attempts[0].outcome == "UNKNOWN"

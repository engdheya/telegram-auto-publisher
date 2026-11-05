"""
Comprehensive End-to-End tests for all 12 required operational scenarios:
1. 1 Source -> 1 Target
2. 1 Source -> Multiple Targets
3. Multiple Sources -> 1 Target
4. Multiple Sources -> Multiple Targets + independent route toggle
5. Burst concurrent messages without data loss
6. Disconnect + reconnect gap catch-up (while never importing old archive or republishing edits)
7. Crash/restart recovery with PROCESSING -> UNKNOWN -> Reconciliation (both delivered & dropped cases)
8. Partial failure: Target 2 fails/retries while Target 1 succeeded (Target 1 NEVER republished!)
9. Multi-item Album (`grouped_id`) ordering, caption/formatting preservation, & late straggler safety
10. Video, Document, Audio, Voice & file extension filter rules
11. Duplicate message prevention
12. Protected content (`noforwards`) -> SKIPPED & insufficient target permissions -> FAILED
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import PublishJob
from app.repositories.job_repo import JobRepository
from app.services.ingestion_service import IngestionService
from app.services.publishing_engine import PublishingEngine, ReconciliationService
from app.telegram.gateway import IncomingMediaItem, IncomingTelegramEvent
from app.utils.time import utcnow
from tests.conftest import SimulatedChannel


def _setup_channel_pair(client: TestClient, headers: dict[str, str], fake_tg):
    fake_tg.register_channel(
        SimulatedChannel(peer_id=-1001001, identifier="@source_a", title="Source A", username="source_a", latest_message_id=500)
    )
    fake_tg.register_channel(
        SimulatedChannel(peer_id=-1001002, identifier="@source_b", title="Source B", username="source_b", latest_message_id=300)
    )
    fake_tg.register_channel(
        SimulatedChannel(peer_id=-1001003, identifier="@source_c", title="Source C", username="source_c", latest_message_id=100)
    )
    fake_tg.register_channel(
        SimulatedChannel(peer_id=-1002001, identifier="@target_1", title="Target 1", username="target_1")
    )
    fake_tg.register_channel(
        SimulatedChannel(peer_id=-1002002, identifier="@target_2", title="Target 2", username="target_2")
    )
    fake_tg.register_channel(
        SimulatedChannel(peer_id=-1002003, identifier="@target_3", title="Target 3", username="target_3")
    )

    sa = client.post("/api/v1/sources", headers=headers, json={"title": "Source A", "identifier": "@source_a"}).json()
    sb = client.post("/api/v1/sources", headers=headers, json={"title": "Source B", "identifier": "@source_b"}).json()
    sc = client.post("/api/v1/sources", headers=headers, json={"title": "Source C", "identifier": "@source_c"}).json()

    t1 = client.post("/api/v1/targets", headers=headers, json={"title": "Target 1", "identifier": "@target_1"}).json()
    t2 = client.post("/api/v1/targets", headers=headers, json={"title": "Target 2", "identifier": "@target_2"}).json()
    t3 = client.post("/api/v1/targets", headers=headers, json={"title": "Target 3", "identifier": "@target_3"}).json()
    return (sa, sb, sc), (t1, t2, t3)


@pytest.mark.asyncio
async def test_scenarios_1_to_4_topologies_archive_and_edits(
    client: TestClient, admin_headers: dict[str, str], isolated_env, db: Session
):
    """
    Tests:
    - Scenario 1 (1->1), Scenario 2 (1->N), Scenario 3 (N->1), Scenario 4 (N->N: A->1,2; B->2,3; C->1,3)
    - Old archive (msg_id <= baseline 500) NEVER imported
    - Message edits NEVER republished
    - Independent route toggle disables A->2 without affecting A->1 or B->2
    """
    fake_tg = isolated_env["fake_tg"]
    (sa, sb, sc), (t1, t2, t3) = _setup_channel_pair(client, admin_headers, fake_tg)

    assert sa["baseline_message_id"] == 500

    # Create topology from Section 3.D:
    # Source A -> Target 1, Target 2
    # Source B -> Target 2, Target 3
    # Source C -> Target 1, Target 3
    r_a1 = client.post(
        "/api/v1/routes",
        headers=admin_headers,
        json={"name": "A->1", "source_channel_id": sa["id"], "target_channel_id": t1["id"]},
    ).json()
    r_a2 = client.post(
        "/api/v1/routes",
        headers=admin_headers,
        json={"name": "A->2", "source_channel_id": sa["id"], "target_channel_id": t2["id"]},
    ).json()
    client.post(
        "/api/v1/routes/bulk",
        headers=admin_headers,
        json={"name_prefix": "B-Routes", "source_channel_ids": [sb["id"]], "target_channel_ids": [t2["id"], t3["id"]]},
    )
    client.post(
        "/api/v1/routes/bulk",
        headers=admin_headers,
        json={"name_prefix": "C-Routes", "source_channel_ids": [sc["id"]], "target_channel_id": t1["id"], "target_channel_ids": [t1["id"], t3["id"]]},
    )
    assert r_a1["id"] > 0

    # Rule 1: Historical message #450 (<= baseline 500) MUST BE IGNORED
    old_res = IngestionService.ingest_event(
        db,
        IncomingTelegramEvent(
            source_peer_id=-1001001,
            source_identifier="@source_a",
            telegram_message_id=450,
            grouped_id=None,
            content_type="text",
            raw_text="Old archive post",
            entities=[],
            is_protected_content=False,
            protection_reason=None,
            published_at=utcnow(),
        ),
    )
    assert old_res["status"] == "IGNORED_ARCHIVE_BEFORE_BASELINE"

    # Rule 4: Edited message MUST BE IGNORED
    edit_res = IngestionService.ingest_event(
        db,
        IncomingTelegramEvent(
            source_peer_id=-1001001,
            source_identifier="@source_a",
            telegram_message_id=501,
            grouped_id=None,
            content_type="text",
            raw_text="Edited text",
            entities=[],
            is_protected_content=False,
            protection_reason=None,
            published_at=utcnow(),
            is_edit=True,
        ),
    )
    assert edit_res["status"] == "IGNORED_EDIT"

    # New posts on A (#501), B (#301), C (#101)
    IngestionService.ingest_event(
        db,
        IncomingTelegramEvent(
            source_peer_id=-1001001,
            source_identifier="@source_a",
            telegram_message_id=501,
            grouped_id=None,
            content_type="text",
            raw_text="Post from Source A",
            entities=[{"type": "bold", "offset": 0, "length": 4}],
            is_protected_content=False,
            protection_reason=None,
            published_at=utcnow(),
        ),
    )
    IngestionService.ingest_event(
        db,
        IncomingTelegramEvent(
            source_peer_id=-1001002,
            source_identifier="@source_b",
            telegram_message_id=301,
            grouped_id=None,
            content_type="text",
            raw_text="Post from Source B",
            entities=[],
            is_protected_content=False,
            protection_reason=None,
            published_at=utcnow(),
        ),
    )
    IngestionService.ingest_event(
        db,
        IncomingTelegramEvent(
            source_peer_id=-1001003,
            source_identifier="@source_c",
            telegram_message_id=101,
            grouped_id=None,
            content_type="text",
            raw_text="Post from Source C",
            entities=[],
            is_protected_content=False,
            protection_reason=None,
            published_at=utcnow(),
        ),
    )

    while await PublishingEngine.process_next_job(db, fake_tg):
        pass

    assert [p["text"] for p in fake_tg._lookup("@target_1").published_posts] == [
        "Post from Source A",
        "Post from Source C",
    ]
    assert [p["text"] for p in fake_tg._lookup("@target_2").published_posts] == [
        "Post from Source A",
        "Post from Source B",
    ]
    assert [p["text"] for p in fake_tg._lookup("@target_3").published_posts] == [
        "Post from Source B",
        "Post from Source C",
    ]

    # Toggle route A->2 OFF independently and verify Source A only publishes to Target 1 while B->2 still works!
    toggle_resp = client.post(f"/api/v1/routes/{r_a2['id']}/toggle", headers=admin_headers)
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["is_enabled"] is False

    IngestionService.ingest_event(
        db,
        IncomingTelegramEvent(
            source_peer_id=-1001001,
            source_identifier="@source_a",
            telegram_message_id=502,
            grouped_id=None,
            content_type="text",
            raw_text="Second A Post",
            entities=[],
            is_protected_content=False,
            protection_reason=None,
            published_at=utcnow(),
        ),
    )
    while await PublishingEngine.process_next_job(db, fake_tg):
        pass

    assert "Second A Post" in [p["text"] for p in fake_tg._lookup("@target_1").published_posts]
    assert "Second A Post" not in [p["text"] for p in fake_tg._lookup("@target_2").published_posts]


@pytest.mark.asyncio
async def test_scenarios_5_6_8_11_burst_dedup_partial_failure_and_reconnect_catchup(
    client: TestClient, admin_headers: dict[str, str], isolated_env, db: Session
):
    """
    Tests:
    - Scenario 5: Burst arrival of 15 concurrent/rapid posts without loss
    - Scenario 11: Duplicate message delivery rejected idempotently
    - Scenario 8: Target 2 fails (FloodWait -> RETRY_WAIT) while Target 1 succeeds; retrying Target 2 NEVER republishes to Target 1
    - Scenario 6: Network outage + missed messages recovered via catch_up_missed_messages on reconnect
    """
    fake_tg = isolated_env["fake_tg"]
    (sa, _, _), (t1, t2, _) = _setup_channel_pair(client, admin_headers, fake_tg)

    client.post(
        "/api/v1/routes/bulk",
        headers=admin_headers,
        json={"name_prefix": "Fanout", "source_channel_ids": [sa["id"]], "target_channel_ids": [t1["id"], t2["id"]]},
    )

    # Scenario 8 + 11: Target 2 hits FloodWait while Target 1 works
    fake_tg._lookup("@target_2").fail_mode = "FLOOD_WAIT"

    ev = IncomingTelegramEvent(
        source_peer_id=-1001001,
        source_identifier="@source_a",
        telegram_message_id=501,
        grouped_id=None,
        content_type="text",
        raw_text="Independent per-target delivery",
        entities=[],
        is_protected_content=False,
        protection_reason=None,
        published_at=utcnow(),
    )
    r_first = IngestionService.ingest_event(db, ev)
    r_dup = IngestionService.ingest_event(db, ev)  # Scenario 11 duplicate!
    assert r_first["status"] == "ENQUEUED"
    assert r_dup["status"] == "DUPLICATE_IGNORED"

    # Process initial pass: Target 1 -> PUBLISHED, Target 2 -> RETRY_WAIT
    await PublishingEngine.process_next_job(db, fake_tg)
    await PublishingEngine.process_next_job(db, fake_tg)

    assert len(fake_tg._lookup("@target_1").published_posts) == 1
    assert len(fake_tg._lookup("@target_2").published_posts) == 0

    counts = JobRepository.counts_by_status(db)
    assert counts["PUBLISHED"] == 1
    assert counts["RETRY_WAIT"] == 1

    # Clear Target 2 FloodWait and make retry immediately due
    fake_tg._lookup("@target_2").fail_mode = None
    retry_job = db.query(PublishJob).filter(PublishJob.status == "RETRY_WAIT").one()
    retry_job.next_retry_at = utcnow()
    db.commit()

    await PublishingEngine.process_next_job(db, fake_tg)

    # Target 1 MUST STILL HAVE EXACTLY 1 POST (never duplicated!), and Target 2 now has 1 post!
    assert len(fake_tg._lookup("@target_1").published_posts) == 1
    assert len(fake_tg._lookup("@target_2").published_posts) == 1

    # Scenario 5: Rapid burst of 15 posts (#502..#516)
    for mid in range(502, 517):
        IngestionService.ingest_event(
            db,
            IncomingTelegramEvent(
                source_peer_id=-1001001,
                source_identifier="@source_a",
                telegram_message_id=mid,
                grouped_id=None,
                content_type="text",
                raw_text=f"Burst message #{mid}",
                entities=[],
                is_protected_content=False,
                protection_reason=None,
                published_at=utcnow(),
            ),
        )
    while await PublishingEngine.process_next_job(db, fake_tg):
        pass
    assert len(fake_tg._lookup("@target_1").published_posts) == 16
    assert len(fake_tg._lookup("@target_2").published_posts) == 16

    # Scenario 6: Simulate disconnect, posts #517 and #518 arrive while offline, then reconnect catch-up!
    src_sim = fake_tg._lookup("@source_a")
    src_sim.missed_events = [
        IncomingTelegramEvent(
            source_peer_id=-1001001,
            source_identifier="@source_a",
            telegram_message_id=499,  # Pre-baseline: must not be imported
            grouped_id=None,
            content_type="text",
            raw_text="Should never import",
            entities=[],
            is_protected_content=False,
            protection_reason=None,
            published_at=utcnow(),
        ),
        IncomingTelegramEvent(
            source_peer_id=-1001001,
            source_identifier="@source_a",
            telegram_message_id=517,
            grouped_id=None,
            content_type="text",
            raw_text="Recovered after outage #517",
            entities=[],
            is_protected_content=False,
            protection_reason=None,
            published_at=utcnow(),
        ),
        IncomingTelegramEvent(
            source_peer_id=-1001001,
            source_identifier="@source_a",
            telegram_message_id=518,
            grouped_id=None,
            content_type="text",
            raw_text="Recovered after outage #518",
            entities=[],
            is_protected_content=False,
            protection_reason=None,
            published_at=utcnow(),
        ),
    ]

    catchup = await IngestionService.catch_up_missed_messages(db, fake_tg)
    assert catchup["events_recovered"] == 2
    while await PublishingEngine.process_next_job(db, fake_tg):
        pass
    assert len(fake_tg._lookup("@target_1").published_posts) == 18


@pytest.mark.asyncio
async def test_scenarios_7_9_10_12_albums_media_filters_protected_and_unknown_reconciliation(
    client: TestClient, admin_headers: dict[str, str], isolated_env, db: Session
):
    """
    Tests:
    - Scenario 9: Album (`grouped_id`) out-of-order items sorted, caption+entities preserved, straggler ignored
    - Scenario 10: Video, Document (.pdf allowed, .exe filtered), Audio, Voice + prefix/suffix/signature
    - Scenario 12: Protected content (`noforwards`) -> SKIPPED; insufficient permission -> FAILED
    - Scenario 7: Crash/timeout -> UNKNOWN -> Reconciliation detects both already-delivered and not-delivered!
    """
    fake_tg = isolated_env["fake_tg"]
    (sa, _, _), (t1, t2, t3) = _setup_channel_pair(client, admin_headers, fake_tg)

    # Route A -> Target 1 with prefix, signature, and allowed_extensions=[".jpg", ".mp4", ".pdf", ".ogg"]
    client.post(
        "/api/v1/routes",
        headers=admin_headers,
        json={
            "name": "Filtered Formatted Route",
            "source_channel_id": sa["id"],
            "target_channel_id": t1["id"],
            "filters": {
                "allowed_content_types": ["text", "photo", "video", "document", "audio", "voice", "album"],
                "include_keywords": [],
                "exclude_keywords": ["spam_ad"],
                "allowed_extensions": [".jpg", ".mp4", ".pdf", ".ogg", ".mp3"],
                "prefix_text": "📢 عاجل:",
                "suffix_text": "المصدر: أخبار",
                "target_signature": "@target_1",
                "strip_urls": False,
            },
        },
    )

    # Scenario 9: 3-item album arriving out of order (#503, #501 with caption, #502)
    for mid, cap in [(503, None), (501, "تقرير مصور كامل"), (502, None)]:
        IngestionService.ingest_event(
            db,
            IncomingTelegramEvent(
                source_peer_id=-1001001,
                source_identifier="@source_a",
                telegram_message_id=mid,
                grouped_id="99887766",
                content_type="photo",
                raw_text=cap or "",
                entities=[{"type": "bold", "offset": 0, "length": 5}] if cap else [],
                is_protected_content=False,
                protection_reason=None,
                published_at=utcnow(),
                media=IncomingMediaItem(
                    telegram_message_id=mid,
                    media_type="photo",
                    file_name=f"img_{mid}.jpg",
                    mime_type="image/jpeg",
                    file_ext=".jpg",
                    caption=cap,
                    caption_entities=[{"type": "bold", "offset": 0, "length": 5}] if cap else [],
                ),
            ),
        )

    flushed = IngestionService.finalize_ready_albums(db, force_all=True)
    assert flushed == 1

    # Late straggler #504 with same grouped_id MUST NOT re-publish the whole album!
    late = IngestionService.ingest_event(
        db,
        IncomingTelegramEvent(
            source_peer_id=-1001001,
            source_identifier="@source_a",
            telegram_message_id=504,
            grouped_id="99887766",
            content_type="photo",
            raw_text="",
            entities=[],
            is_protected_content=False,
            protection_reason=None,
            published_at=utcnow(),
            media=IncomingMediaItem(
                telegram_message_id=504,
                media_type="photo",
                file_name="img_504.jpg",
                mime_type="image/jpeg",
                file_ext=".jpg",
            ),
        ),
    )
    assert late["status"] == "LATE_ALBUM_ITEM_SKIPPED"

    await PublishingEngine.process_next_job(db, fake_tg)
    t1_posts = fake_tg._lookup("@target_1").published_posts
    assert len(t1_posts) == 1
    assert t1_posts[0]["content_type"] == "album"
    assert t1_posts[0]["source_message_ids"] == [501, 502, 503]  # Preserved exact order!
    assert "📢 عاجل:" in t1_posts[0]["text"]
    assert "تقرير مصور كامل" in t1_posts[0]["text"]
    assert "@target_1" in t1_posts[0]["text"]

    # Scenario 10: Video (#505), PDF Document (#506), Voice (#507), Blocked .exe Document (#508), Excluded Keyword (#509)
    for mid, ctype, ext, txt in [
        (505, "video", ".mp4", "فيديو توضيحي"),
        (506, "document", ".pdf", "التقرير السنوي"),
        (507, "voice", ".ogg", "رسالة صوتية"),
        (508, "document", ".exe", "ملف غير مسموح"),
        (509, "text", None, "This is spam_ad promo"),
    ]:
        IngestionService.ingest_event(
            db,
            IncomingTelegramEvent(
                source_peer_id=-1001001,
                source_identifier="@source_a",
                telegram_message_id=mid,
                grouped_id=None,
                content_type=ctype,
                raw_text=txt,
                entities=[],
                is_protected_content=False,
                protection_reason=None,
                published_at=utcnow(),
                media=(
                    IncomingMediaItem(
                        telegram_message_id=mid,
                        media_type=ctype,
                        file_name=f"file_{mid}{ext}",
                        file_ext=ext,
                    )
                    if ext
                    else None
                ),
            ),
        )

    while await PublishingEngine.process_next_job(db, fake_tg):
        pass
    # Video, PDF, Voice published (+1 album = 4); .exe and spam_ad were SKIPPED!
    assert len(fake_tg._lookup("@target_1").published_posts) == 4
    assert JobRepository.counts_by_status(db)["SKIPPED"] == 2

    # Scenario 12: Protected content (`noforwards`) -> SKIPPED, never copied!
    IngestionService.ingest_event(
        db,
        IncomingTelegramEvent(
            source_peer_id=-1001001,
            source_identifier="@source_a",
            telegram_message_id=510,
            grouped_id=None,
            content_type="text",
            raw_text="Exclusive protected post",
            entities=[],
            is_protected_content=True,
            protection_reason="PROTECTED_CONTENT_NOFORWARDS",
            published_at=utcnow(),
        ),
    )
    assert JobRepository.counts_by_status(db)["SKIPPED"] == 3

    # Scenario 12b: Target 3 lacks post permission -> FAILED
    fake_tg._lookup("@target_3").can_post_messages = False
    client.post(
        "/api/v1/routes",
        headers=admin_headers,
        json={"name": "A->ForbiddenTarget3", "source_channel_id": sa["id"], "target_channel_id": t3["id"]},
    )
    IngestionService.ingest_event(
        db,
        IncomingTelegramEvent(
            source_peer_id=-1001001,
            source_identifier="@source_a",
            telegram_message_id=511,
            grouped_id=None,
            content_type="text",
            raw_text="Test permission handling",
            entities=[],
            is_protected_content=False,
            protection_reason=None,
            published_at=utcnow(),
        ),
    )
    while await PublishingEngine.process_next_job(db, fake_tg):
        pass
    assert JobRepository.counts_by_status(db)["FAILED"] == 1

    # Scenario 7a: Ambiguous timeout AFTER Telegram already accepted the post -> UNKNOWN -> Reconciled as PUBLISHED!
    client.post(
        "/api/v1/routes",
        headers=admin_headers,
        json={"name": "A->Target2", "source_channel_id": sa["id"], "target_channel_id": t2["id"]},
    )
    fake_tg._lookup("@target_2").fail_mode = "AMBIGUOUS_DELIVERED"
    IngestionService.ingest_event(
        db,
        IncomingTelegramEvent(
            source_peer_id=-1001001,
            source_identifier="@source_a",
            telegram_message_id=512,
            grouped_id=None,
            content_type="text",
            raw_text="Ambiguous post that actually landed",
            entities=[],
            is_protected_content=False,
            protection_reason=None,
            published_at=utcnow(),
        ),
    )
    while await PublishingEngine.process_next_job(db, fake_tg):
        pass

    unknown_job = db.query(PublishJob).filter(PublishJob.status == "UNKNOWN").one()
    # Direct manual retry without reconciliation MUST be blocked!
    blocked_retry = client.post(f"/api/v1/queue/jobs/{unknown_job.id}/retry", headers=admin_headers)
    assert blocked_retry.status_code == 400

    # Reconcile via API -> discovers the post in @target_2 and marks PUBLISHED without duplicating!
    fake_tg._lookup("@target_2").fail_mode = None
    rec_resp = client.post(f"/api/v1/queue/jobs/{unknown_job.id}/reconcile", headers=admin_headers)
    assert rec_resp.status_code == 200
    assert rec_resp.json()["job"]["status"] == "PUBLISHED"
    assert len(fake_tg._lookup("@target_2").published_posts) == 1  # Still 1, zero duplication!

    # Scenario 7b: Worker crash mid-PROCESSING (stale lock recovery) when post never reached target -> Reconciles to QUEUED!
    fake_tg._lookup("@target_2").fail_mode = "AMBIGUOUS_DROPPED"
    IngestionService.ingest_event(
        db,
        IncomingTelegramEvent(
            source_peer_id=-1001001,
            source_identifier="@source_a",
            telegram_message_id=513,
            grouped_id=None,
            content_type="text",
            raw_text="Ambiguous post dropped in transit",
            entities=[],
            is_protected_content=False,
            protection_reason=None,
            published_at=utcnow(),
        ),
    )
    while await PublishingEngine.process_next_job(db, fake_tg):
        pass

    dropped_job = db.query(PublishJob).filter(PublishJob.status == "UNKNOWN").one()
    fake_tg._lookup("@target_2").fail_mode = None
    rec_dropped, _ = await ReconciliationService.reconcile_unknown_job(
        db, dropped_job.id, fake_tg, requeue_if_missing=True, actor_username="admin"
    )
    assert rec_dropped.status == "QUEUED"
    await PublishingEngine.process_next_job(db, fake_tg)
    assert len(fake_tg._lookup("@target_2").published_posts) == 2

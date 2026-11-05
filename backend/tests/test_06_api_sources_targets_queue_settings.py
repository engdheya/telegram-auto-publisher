"""API integration tests for Sources, Targets, Messages History, Queue Actions, Settings, and Backups."""

from fastapi.testclient import TestClient

from app.services.ingestion_service import IngestionService
from app.telegram.gateway import IncomingTelegramEvent
from app.utils.time import utcnow
from tests.conftest import SimulatedChannel


def test_sources_and_targets_lifecycle_and_permission_errors(
    client: TestClient, admin_headers: dict[str, str], isolated_env
):
    fake_tg = isolated_env["fake_tg"]
    fake_tg.register_channel(
        SimulatedChannel(
            peer_id=-1005001,
            identifier="@priv_src",
            title="Private Source",
            accessible=False,
        )
    )
    fake_tg.register_channel(
        SimulatedChannel(
            peer_id=-1005002,
            identifier="@pub_src",
            title="Public Tech News",
            username="pub_src",
            latest_message_id=42,
        )
    )
    fake_tg.register_channel(
        SimulatedChannel(
            peer_id=-1006001,
            identifier="@readonly_tgt",
            title="ReadOnly Target",
            can_post_messages=False,
        )
    )
    fake_tg.register_channel(
        SimulatedChannel(
            peer_id=-1006002,
            identifier="@writable_tgt",
            title="Writable Target",
            can_post_messages=True,
            can_post_media=True,
        )
    )

    # Source with access denied shows ERROR and last_error clearly
    s_priv = client.post(
        "/api/v1/sources",
        headers=admin_headers,
        json={"title": "Priv", "identifier": "@priv_src"},
    )
    assert s_priv.status_code == 201
    assert s_priv.json()["monitoring_status"] == "ERROR"
    assert s_priv.json()["last_error"] is not None

    # Accessible source sets baseline_message_id=42, pause/resume/edit/delete works
    s_pub = client.post(
        "/api/v1/sources",
        headers=admin_headers,
        json={"title": "Tech", "identifier": "https://t.me/pub_src"},
    )
    assert s_pub.status_code == 201
    sid = s_pub.json()["id"]
    assert s_pub.json()["identifier"] == "@pub_src"
    assert s_pub.json()["baseline_message_id"] == 42

    stopped = client.post(f"/api/v1/sources/{sid}/stop", headers=admin_headers).json()
    assert stopped["monitoring_status"] == "PAUSED"
    assert stopped["is_enabled"] is False

    started = client.post(f"/api/v1/sources/{sid}/start", headers=admin_headers).json()
    assert started["monitoring_status"] == "ACTIVE"
    assert started["is_enabled"] is True

    edited = client.patch(
        f"/api/v1/sources/{sid}", headers=admin_headers, json={"title": "Tech Updated"}
    ).json()
    assert edited["title"] == "Tech Updated"

    # Target without post permissions reports INSUFFICIENT_PERMISSIONS and fails test-publish clearly
    t_ro = client.post(
        "/api/v1/targets",
        headers=admin_headers,
        json={"title": "RO", "identifier": "@readonly_tgt"},
    ).json()
    assert t_ro["permission_status"] == "INSUFFICIENT_PERMISSIONS"
    tp_fail = client.post(
        f"/api/v1/targets/{t_ro['id']}/test-publish",
        headers=admin_headers,
        json={"message": "Hello"},
    ).json()
    assert tp_fail["ok"] is False
    assert "ChatWriteForbidden" in tp_fail["detail"]

    # Writable target verifies and test-publishes cleanly
    t_ok = client.post(
        "/api/v1/targets",
        headers=admin_headers,
        json={"title": "OK", "identifier": "@writable_tgt"},
    ).json()
    assert t_ok["permission_status"] == "VERIFIED"
    tp_ok = client.post(
        f"/api/v1/targets/{t_ok['id']}/test-publish",
        headers=admin_headers,
        json={"message": "Ping test"},
    ).json()
    assert tp_ok["ok"] is True
    assert tp_ok["test_message_id"] is not None


def test_messages_queue_cancel_settings_and_backup_endpoints(
    client: TestClient, admin_headers: dict[str, str], isolated_env, db
):
    fake_tg = isolated_env["fake_tg"]
    fake_tg.register_channel(SimulatedChannel(peer_id=-1007001, identifier="@s_api", title="S API", latest_message_id=10))
    fake_tg.register_channel(SimulatedChannel(peer_id=-1007002, identifier="@t_api", title="T API"))

    sa = client.post("/api/v1/sources", headers=admin_headers, json={"title": "S API", "identifier": "@s_api"}).json()
    ta = client.post("/api/v1/targets", headers=admin_headers, json={"title": "T API", "identifier": "@t_api"}).json()
    client.post(
        "/api/v1/routes",
        headers=admin_headers,
        json={"name": "API Route", "source_channel_id": sa["id"], "target_channel_id": ta["id"]},
    )

    IngestionService.ingest_event(
        db,
        IncomingTelegramEvent(
            source_peer_id=-1007001,
            source_identifier="@s_api",
            telegram_message_id=11,
            grouped_id=None,
            content_type="text",
            raw_text="Searchable headline 2026",
            entities=[],
            is_protected_content=False,
            protection_reason=None,
            published_at=utcnow(),
        ),
    )

    msgs = client.get("/api/v1/messages?search=Searchable", headers=admin_headers).json()
    assert msgs["total"] == 1
    assert msgs["items"][0]["raw_text"] == "Searchable headline 2026"

    jobs = client.get("/api/v1/queue/jobs?status=QUEUED", headers=admin_headers).json()
    assert jobs["total"] == 1
    job_id = jobs["items"][0]["id"]

    cancelled = client.post(f"/api/v1/queue/jobs/{job_id}/cancel", headers=admin_headers).json()
    assert cancelled["job"]["status"] == "SKIPPED"

    # Settings update + integrity + backup download
    upd = client.put(
        "/api/v1/settings",
        headers=admin_headers,
        json={"settings": [{"key": "retry.max_attempts", "value": 6}]},
    )
    assert upd.status_code == 200

    health = client.get("/api/v1/health").json()
    assert health["status"] == "ok"
    assert health["database"]["wal_enabled"] is True

    bk = client.post("/api/v1/settings/backups", headers=admin_headers, json={"label": "api_test"}).json()
    dl = client.get(f"/api/v1/settings/backups/{bk['filename']}/download", headers=admin_headers)
    assert dl.status_code == 200
    assert dl.content.startswith(b"SQLite format 3\x00")

    overview = client.get("/api/v1/dashboard/overview", headers=admin_headers).json()
    assert overview["sources_total"] == 1
    assert overview["targets_total"] == 1
    assert overview["routes_active"] == 1
    assert overview["messages_received_total"] == 1

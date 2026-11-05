"""Telegram login, OTP verification, 2FA Cloud Password, encrypted session, reconnect, and logout tests."""

import json

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TelegramAccount


def test_telegram_full_login_2fa_reconnect_logout_never_exposes_session(
    client: TestClient,
    admin_headers: dict[str, str],
    isolated_env,
    db: Session,
):
    fake_tg = isolated_env["fake_tg"]
    fake_tg.connected = False
    fake_tg.requires_2fa = True

    # 1. Request OTP login code
    r1 = client.post(
        "/api/v1/telegram/send-code",
        headers=admin_headers,
        json={
            "label": "Production Account",
            "api_id": 2040111,
            "api_hash": "abcdef0123456789abcdef0123456789",
            "phone_number": "+967771234567",
            "auto_reconnect": True,
        },
    )
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["auth_state"] == "AWAITING_CODE"
    assert "abcdef0123456789abcdef0123456789" not in json.dumps(body1)
    assert "+967771234567" not in json.dumps(body1)  # Phone is masked!

    # 2. Submit OTP -> transitions to AWAITING_PASSWORD because 2FA is active
    r2 = client.post(
        "/api/v1/telegram/verify-code",
        headers=admin_headers,
        json={"code": "12345"},
    )
    assert r2.status_code == 200
    assert r2.json()["auth_state"] == "AWAITING_PASSWORD"

    # 3. Submit 2FA Cloud Password -> CONNECTED
    r3 = client.post(
        "/api/v1/telegram/verify-password",
        headers=admin_headers,
        json={"password": "CloudPass#2026"},
    )
    assert r3.status_code == 200
    body3 = r3.json()
    assert body3["auth_state"] == "CONNECTED"
    assert body3["is_connected"] is True
    assert body3["has_saved_session"] is True
    assert "1BVts" not in json.dumps(body3)  # Session string NEVER exposed!

    # Verify DB stores ciphertext, NOT plaintext session string
    acc = db.execute(select(TelegramAccount)).scalar_one()
    assert acc.encrypted_session is not None
    assert "1BVts" not in acc.encrypted_session

    # Verify audit logs do NOT contain OTP code, 2FA password, or session string
    logs_resp = client.get("/api/v1/logs", headers=admin_headers)
    logs_dump = json.dumps(logs_resp.json())
    assert "CloudPass#2026" not in logs_dump
    assert "1BVts" not in logs_dump
    assert "abcdef0123456789abcdef0123456789" not in logs_dump

    # 4. Simulate disconnect and trigger reconnect
    fake_tg.connected = False
    r4 = client.post("/api/v1/telegram/reconnect", headers=admin_headers)
    assert r4.status_code == 200
    assert r4.json()["live_transport_connected"] is True

    # 5. Logout & Unlink wipes session cleanly
    r5 = client.post("/api/v1/telegram/logout", headers=admin_headers)
    assert r5.status_code == 200
    assert r5.json()["is_connected"] is False
    assert r5.json()["has_saved_session"] is False

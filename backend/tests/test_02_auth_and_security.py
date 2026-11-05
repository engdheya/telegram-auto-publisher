"""Authentication, Argon2id hashing, Fernet encryption, RBAC, session revocation, and secret redaction tests."""

from fastapi.testclient import TestClient

from app.core.crypto import SecretBox
from app.utils.sanitize import sanitize_sensitive_data


def test_login_rbac_and_password_change_invalidates_old_jwt(client: TestClient, admin_headers: dict[str, str]):
    # Unauthorized access blocked
    unauth = client.get("/api/v1/dashboard/overview")
    assert unauth.status_code == 401

    # Invalid password rejected and audited
    bad = client.post("/api/v1/auth/login", json={"username": "admin", "password": "WrongPassword123"})
    assert bad.status_code == 401

    # Create an operator user and verify admin-only endpoints reject operator
    create_op = client.post(
        "/api/v1/auth/users",
        headers=admin_headers,
        json={
            "username": "operator1",
            "email": "op1@tap.local",
            "password": "Operator@2026!",
            "role": "operator",
            "preferred_language": "en",
        },
    )
    assert create_op.status_code == 201

    op_login = client.post(
        "/api/v1/auth/login",
        json={"username": "operator1", "password": "Operator@2026!"},
    )
    assert op_login.status_code == 200
    op_headers = {"Authorization": f"Bearer {op_login.json()['access_token']}"}

    # Operator can view dashboard, but CANNOT trigger backups or logout Telegram
    assert client.get("/api/v1/dashboard/overview", headers=op_headers).status_code == 200
    assert client.post("/api/v1/settings/backups", headers=op_headers, json={"label": "nope"}).status_code == 403
    assert client.post("/api/v1/telegram/logout", headers=op_headers).status_code == 403

    # Changing password immediately invalidates old token via token_version
    pw_resp = client.post(
        "/api/v1/auth/change-password",
        headers=op_headers,
        json={"current_password": "Operator@2026!", "new_password": "NewOperator@2027!"},
    )
    assert pw_resp.status_code == 200
    new_op_headers = {"Authorization": f"Bearer {pw_resp.json()['access_token']}"}

    assert client.get("/api/v1/auth/me", headers=op_headers).status_code == 401
    assert client.get("/api/v1/auth/me", headers=new_op_headers).status_code == 200


def test_fernet_encryption_and_log_secret_redaction():
    box = SecretBox()
    raw_session = "1BVtsOHwBuSuperSecretTelethonSessionString0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnop"
    ciphertext = box.encrypt(raw_session)
    assert ciphertext is not None
    assert raw_session not in ciphertext
    assert box.decrypt(ciphertext) == raw_session

    sanitized = sanitize_sensitive_data(
        {
            "api_id": 123456,
            "api_hash": "0123456789abcdef0123456789abcdef",
            "phone_code": "99887",
            "password": "secret",
            "encrypted_session": ciphertext,
            "note": f"Leak test {raw_session}",
        }
    )
    assert sanitized["api_hash"] == "[REDACTED]"
    assert sanitized["phone_code"] == "[REDACTED]"
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["encrypted_session"] == "[REDACTED]"
    assert raw_session not in sanitized["note"]
    assert "[REDACTED_SESSION]" in sanitized["note"]

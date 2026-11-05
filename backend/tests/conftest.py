"""Pytest fixtures and realistic in-memory Telegram network simulator for full E2E verification."""

from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import (
    AmbiguousPublishError,
    PermanentPublishError,
    TelegramOperationError,
    TransientPublishError,
)
from app.database import session as db_session
from app.database.init_db import init_database
from app.main import create_app
from app.telegram.gateway import (
    IncomingTelegramEvent,
    TargetRecentPost,
    set_telegram_gateway,
)
from app.utils.time import utcnow


@dataclass
class SimulatedChannel:
    peer_id: int
    identifier: str
    title: str
    username: str | None = None
    accessible: bool = True
    noforwards: bool = False
    can_post_messages: bool = True
    can_post_media: bool = True
    latest_message_id: int = 500  # Existing archive up to 500!
    missed_events: list[IncomingTelegramEvent] = field(default_factory=list)
    published_posts: list[dict[str, Any]] = field(default_factory=list)
    fail_mode: str | None = None  # None | "FLOOD_WAIT" | "FORBIDDEN" | "AMBIGUOUS_DELIVERED" | "AMBIGUOUS_DROPPED"


class FakeTelegramGateway:
    """Deterministic Telegram MTProto simulator exercising every protocol path."""

    def __init__(self) -> None:
        self.connected: bool = False
        self.requires_2fa: bool = False
        self.expected_code: str = "12345"
        self.expected_2fa: str = "CloudPass#2026"
        self.channels: dict[str, SimulatedChannel] = {}
        self._next_target_msg_id: int = 9000

    def register_channel(self, ch: SimulatedChannel) -> SimulatedChannel:
        self.channels[ch.identifier.lower()] = ch
        self.channels[str(ch.peer_id)] = ch
        if ch.username:
            self.channels[f"@{ch.username.lower()}"] = ch
        return ch

    def _lookup(self, ref: str | int) -> SimulatedChannel:
        key = str(ref).strip().lower()
        ch = self.channels.get(key)
        if ch is None:
            raise TelegramOperationError(f"Channel '{ref}' not found.", code="CHANNEL_NOT_FOUND")
        return ch

    def is_live_connected(self) -> bool:
        return self.connected

    async def send_login_code(self, api_id: int, api_hash: str, phone_number: str) -> tuple[str, str]:
        if api_id <= 0 or len(api_hash) < 16:
            raise TelegramOperationError("Invalid API credentials", code="API_ID_INVALID")
        return f"pending-session-for-{phone_number}", "hash-abc-999"

    async def verify_code(
        self,
        api_id: int,
        api_hash: str,
        pending_session: str,
        phone_number: str,
        code: str,
        phone_code_hash: str,
        password: str | None = None,
    ) -> dict[str, Any]:
        if code.strip() != self.expected_code:
            raise TelegramOperationError("Invalid Telegram verification code.", code="CODE_INVALID")
        if self.requires_2fa and not password:
            return {"state": "AWAITING_PASSWORD", "pending_session": pending_session + "-2fa"}
        if self.requires_2fa and password != self.expected_2fa:
            raise TelegramOperationError("Invalid 2FA cloud password.", code="PASSWORD_INVALID")
        self.connected = True
        return {
            "state": "CONNECTED",
            "session_str": "1BVtsOHwBuSimulatedAuthorizedTelethonStringSessionSecretValueDoNotLeak0123456789ABCDEFG",
            "telegram_user_id": 777001,
            "telegram_username": "tap_publisher_account",
            "telegram_display_name": "TAP Publisher BotUser",
        }

    async def verify_2fa_password(
        self, api_id: int, api_hash: str, pending_session: str, password: str
    ) -> dict[str, Any]:
        if password != self.expected_2fa:
            raise TelegramOperationError("Invalid 2FA cloud password.", code="PASSWORD_INVALID")
        self.connected = True
        return {
            "state": "CONNECTED",
            "session_str": "1BVtsOHwBuSimulatedAuthorizedTelethonStringSession2FASecretValueDoNotLeak0123456789ABCDEF",
            "telegram_user_id": 777001,
            "telegram_username": "tap_publisher_account",
            "telegram_display_name": "TAP Publisher BotUser",
        }

    async def connect_saved_session(self, api_id: int, api_hash: str, session_str: str) -> dict[str, Any]:
        if "REVOKED" in session_str:
            raise TelegramOperationError("Saved session revoked", code="SESSION_REVOKED", status_code=401)
        self.connected = True
        return {
            "telegram_user_id": 777001,
            "telegram_username": "tap_publisher_account",
            "telegram_display_name": "TAP Publisher BotUser",
        }

    async def disconnect_and_logout(
        self, api_id: int | None, api_hash: str | None, session_str: str | None, revoke: bool = True
    ) -> None:
        self.connected = False

    async def inspect_source_channel(self, identifier: str) -> dict[str, Any]:
        if not self.connected:
            raise TelegramOperationError("Telegram client is not connected.", code="TELEGRAM_NOT_CONNECTED")
        ch = self._lookup(identifier)
        if not ch.accessible:
            raise TelegramOperationError("Account is not a member of private channel.", code="SOURCE_ACCESS_DENIED")
        return {
            "accessible": True,
            "peer_id": ch.peer_id,
            "title": ch.title,
            "username": ch.username,
            "noforwards": ch.noforwards,
            "latest_message_id": ch.latest_message_id,
        }

    async def inspect_target_channel(self, identifier: str) -> dict[str, Any]:
        if not self.connected:
            raise TelegramOperationError("Telegram client is not connected.", code="TELEGRAM_NOT_CONNECTED")
        ch = self._lookup(identifier)
        if not ch.accessible:
            raise TelegramOperationError("Target channel inaccessible.", code="TARGET_NOT_ACCESSIBLE")
        return {
            "peer_id": ch.peer_id,
            "title": ch.title,
            "username": ch.username,
            "can_post_messages": ch.can_post_messages,
            "can_post_media": ch.can_post_media,
        }

    async def send_target_test_message(self, identifier: str, text: str) -> int:
        ch = self._lookup(identifier)
        if not ch.can_post_messages:
            raise TelegramOperationError("ChatWriteForbiddenError", code="TARGET_WRITE_FORBIDDEN", status_code=403)
        self._next_target_msg_id += 1
        ch.published_posts.append(
            {
                "message_id": self._next_target_msg_id,
                "text": text.strip(),
                "content_type": "text",
                "media_count": 0,
                "published_at": utcnow(),
            }
        )
        return self._next_target_msg_id

    async def fetch_missed_messages(
        self, identifier_or_peer: str | int, min_message_id: int, limit: int = 100
    ) -> list[IncomingTelegramEvent]:
        ch = self._lookup(identifier_or_peer)
        return [ev for ev in ch.missed_events if ev.telegram_message_id > min_message_id][:limit]

    async def publish_job_payload(
        self,
        *,
        target_identifier: str | int,
        source_identifier: str | int,
        content_type: str,
        text: str,
        entities_json: str,
        source_message_ids: list[int],
        media_descriptors: list[dict[str, Any]],
    ) -> list[int]:
        if not self.connected:
            raise TransientPublishError("Telegram client disconnected", code="CLIENT_DISCONNECTED")

        ch = self._lookup(target_identifier)
        if not ch.can_post_messages or ch.fail_mode == "FORBIDDEN":
            raise PermanentPublishError("ChatWriteForbiddenError: admin post_messages required", code="CHATWRITEFORBIDDEN")
        if ch.fail_mode == "FLOOD_WAIT":
            raise TransientPublishError("FloodWaitError: wait 5s", retry_after_seconds=1, code="FLOOD_WAIT")
        if ch.fail_mode == "AMBIGUOUS_DELIVERED":
            # Simulate Telegram accepting the post BEFORE network timed out!
            self._next_target_msg_id += 1
            ch.published_posts.append(
                {
                    "message_id": self._next_target_msg_id,
                    "text": (text or "").strip(),
                    "content_type": content_type,
                    "has_media": content_type != "text",
                    "media_count": len(media_descriptors) if content_type == "album" else (1 if content_type != "text" else 0),
                    "published_at": utcnow(),
                }
            )
            raise AmbiguousPublishError("TimedOutError after MTProto send frame")
        if ch.fail_mode == "AMBIGUOUS_DROPPED":
            # Simulate network timeout where Telegram did NOT receive the post!
            raise AmbiguousPublishError("ConnectionError during send; message never reached server")

        ids: list[int] = []
        count = max(1, len(media_descriptors)) if content_type == "album" else 1
        for i in range(count):
            self._next_target_msg_id += 1
            ids.append(self._next_target_msg_id)

        ch.published_posts.append(
            {
                "message_id": ids[0],
                "message_ids": ids,
                "text": (text or "").strip(),
                "entities_json": entities_json,
                "content_type": content_type,
                "has_media": content_type != "text",
                "media_count": len(media_descriptors) if content_type == "album" else (1 if content_type != "text" else 0),
                "source_message_ids": list(source_message_ids),
                "media_descriptors": list(media_descriptors),
                "published_at": utcnow(),
            }
        )
        return ids

    async def fetch_recent_target_posts(
        self, target_identifier: str | int, limit: int = 20
    ) -> list[TargetRecentPost]:
        ch = self._lookup(target_identifier)
        recent = list(reversed(ch.published_posts))[:limit]
        return [
            TargetRecentPost(
                message_id=p["message_id"],
                text=p["text"],
                published_at=p["published_at"],
                has_media=bool(p.get("has_media", False)),
                media_count=int(p.get("media_count", 0)),
            )
            for p in recent
        ]


@pytest.fixture()
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_file = tmp_path / "test_tap.db"
    backup_dir = tmp_path / "backups"
    media_dir = tmp_path / "media_cache"
    log_dir = tmp_path / "logs"
    backup_dir.mkdir()
    media_dir.mkdir()
    log_dir.mkdir()

    db_url = f"sqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("BACKUP_DIR", str(backup_dir))
    monkeypatch.setenv("MEDIA_CACHE_DIR", str(media_dir))
    monkeypatch.setenv("LOG_DIR", str(log_dir))
    monkeypatch.setenv("INITIAL_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "admin@tap.local")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "AdminTest@2026!")

    get_settings.cache_clear()
    db_session.reset_engine(db_url)
    init_database()

    fake_tg = FakeTelegramGateway()
    fake_tg.connected = True
    set_telegram_gateway(fake_tg)

    yield {
        "db_url": db_url,
        "db_file": db_file,
        "backup_dir": backup_dir,
        "fake_tg": fake_tg,
    }

    db_session.engine.dispose()
    get_settings.cache_clear()


@pytest.fixture()
def db(isolated_env) -> Generator[Session, None, None]:
    session = db_session.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(isolated_env) -> Generator[TestClient, None, None]:
    app = create_app()
    with TestClient(app) as tc:
        yield tc


@pytest.fixture()
def admin_headers(client: TestClient) -> dict[str, str]:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "AdminTest@2026!"},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

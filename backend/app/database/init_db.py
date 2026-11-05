"""Database bootstrap: schema creation, default system settings, and initial admin user."""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import logger
from app.core.security import hash_password
from app.database import session as db_session
from app.models import Base, SystemSetting, TelegramAccount, User

DEFAULT_SYSTEM_SETTINGS = [
    ("ui.default_language", "ar", "general", "Default dashboard interface language (ar / en)"),
    ("retry.max_attempts", 4, "retry", "Maximum automatic retry attempts per publish job"),
    ("retry.base_seconds", 15, "retry", "Base exponential backoff delay in seconds"),
    ("retry.max_seconds", 900, "retry", "Maximum backoff cap in seconds"),
    ("album.window_ms", 2500, "general", "Quiet window (ms) to aggregate album items by grouped_id"),
    ("storage.media_retention_hours", 24, "storage", "Hours to retain temporary media cache files"),
    ("security.session_expire_minutes", 720, "security", "Dashboard JWT expiration duration in minutes"),
    ("backup.auto_before_restore", True, "backup", "Automatically create a safety snapshot before restore"),
]


def seed_defaults(db: Session) -> None:
    settings = get_settings()

    # 1. Bootstrap initial admin user if users table is empty
    existing_user = db.execute(select(User).limit(1)).scalar_one_or_none()
    if existing_user is None:
        admin = User(
            username=settings.INITIAL_ADMIN_USERNAME,
            email=settings.INITIAL_ADMIN_EMAIL,
            password_hash=hash_password(settings.INITIAL_ADMIN_PASSWORD),
            role="admin",
            is_active=True,
            preferred_language="ar",
            token_version=1,
        )
        db.add(admin)
        logger.info("Bootstrapped initial admin account: username=%s", settings.INITIAL_ADMIN_USERNAME)

    # 2. Bootstrap singleton TelegramAccount row if absent
    existing_tg = db.execute(select(TelegramAccount).limit(1)).scalar_one_or_none()
    if existing_tg is None:
        api_id_val = int(settings.TELEGRAM_DEFAULT_API_ID) if settings.TELEGRAM_DEFAULT_API_ID.isdigit() else None
        tg = TelegramAccount(
            label="Primary Telegram Account",
            api_id=api_id_val,
            auth_state="DISCONNECTED" if api_id_val else "UNCONFIGURED",
            is_connected=False,
            auto_reconnect=True,
        )
        db.add(tg)

    # 3. Bootstrap default system settings
    existing_keys = {
        row[0] for row in db.execute(select(SystemSetting.key)).fetchall()
    }
    for key, val, category, desc in DEFAULT_SYSTEM_SETTINGS:
        if key not in existing_keys:
            db.add(
                SystemSetting(
                    key=key,
                    value_json=json.dumps(val),
                    category=category,
                    description=desc,
                    updated_by="system",
                )
            )

    db.commit()


def init_database() -> None:
    """Ensure tables exist (for fast bootstrap/tests) and seed initial defaults."""
    Base.metadata.create_all(bind=db_session.engine)
    with db_session.SessionLocal() as db:
        seed_defaults(db)

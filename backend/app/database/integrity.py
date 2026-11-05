"""SQLite WAL, Foreign Key, and Integrity validation utilities."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

REQUIRED_TABLES = (
    "users",
    "telegram_accounts",
    "source_channels",
    "target_channels",
    "publishing_routes",
    "route_filters",
    "message_events",
    "message_media",
    "publish_jobs",
    "publish_attempts",
    "audit_logs",
    "system_settings",
)


def validate_database_integrity(db: Session) -> dict[str, Any]:
    """Run SQLite PRAGMA integrity_check, foreign_key_check, journal_mode, and table presence checks."""
    journal_mode = str(db.execute(text("PRAGMA journal_mode;")).scalar() or "").lower()
    fk_enabled = bool(db.execute(text("PRAGMA foreign_keys;")).scalar())
    integrity_rows = [row[0] for row in db.execute(text("PRAGMA integrity_check;")).fetchall()]
    fk_violations = [dict(row._mapping) for row in db.execute(text("PRAGMA foreign_key_check;")).fetchall()]

    existing_tables = {
        row[0]
        for row in db.execute(
            text("SELECT name FROM sqlite_master WHERE type='table';")
        ).fetchall()
    }
    missing_tables = [tbl for tbl in REQUIRED_TABLES if tbl not in existing_tables]

    integrity_ok = integrity_rows == ["ok"]
    fk_ok = len(fk_violations) == 0
    schema_ok = len(missing_tables) == 0
    healthy = integrity_ok and fk_ok and fk_enabled and schema_ok

    return {
        "healthy": healthy,
        "journal_mode": journal_mode,
        "wal_enabled": journal_mode == "wal",
        "foreign_keys_enabled": fk_enabled,
        "integrity_check": integrity_rows,
        "foreign_key_violations": fk_violations,
        "missing_tables": missing_tables,
        "tables_count": len(existing_tables),
    }

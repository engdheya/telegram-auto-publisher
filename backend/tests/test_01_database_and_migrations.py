"""Database integrity, WAL mode, Foreign Key enforcement, Alembic migrations, and Backup/Restore tests."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.backup import (
    create_database_backup,
    list_database_backups,
    restore_database_backup,
)
from app.database.integrity import REQUIRED_TABLES, validate_database_integrity
from app.models import PublishingRoute, SourceChannel, TargetChannel


def test_sqlite_wal_foreign_keys_and_all_12_tables(db: Session):
    report = validate_database_integrity(db)
    assert report["healthy"] is True
    assert report["wal_enabled"] is True
    assert report["journal_mode"] == "wal"
    assert report["foreign_keys_enabled"] is True
    assert report["missing_tables"] == []
    assert report["tables_count"] >= len(REQUIRED_TABLES)


def test_foreign_key_and_unique_constraints_enforced(db: Session):
    # Attempting to insert a route pointing to non-existent source/target must fail FK constraint
    bad_route = PublishingRoute(
        name="Invalid FK Route",
        source_channel_id=99999,
        target_channel_id=88888,
        is_enabled=True,
    )
    db.add(bad_route)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # Unique identifier constraint on SourceChannel
    s1 = SourceChannel(title="News 1", identifier="@breaking_news", is_enabled=True, monitoring_status="ACTIVE")
    s2 = SourceChannel(title="News Dup", identifier="@breaking_news", is_enabled=True, monitoring_status="ACTIVE")
    db.add_all([s1, s2])
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # Cascade delete when source channel is deleted
    src = SourceChannel(title="Src Cascade", identifier="@src_cascade", is_enabled=True, monitoring_status="ACTIVE")
    tgt = TargetChannel(title="Tgt Cascade", identifier="@tgt_cascade", is_enabled=True, permission_status="VERIFIED")
    db.add_all([src, tgt])
    db.commit()

    rt = PublishingRoute(name="Cascade Route", source_channel_id=src.id, target_channel_id=tgt.id, is_enabled=True)
    db.add(rt)
    db.commit()

    db.delete(src)
    db.commit()
    remaining_routes = db.execute(text("SELECT COUNT(*) FROM publishing_routes")).scalar()
    assert remaining_routes == 0


def test_alembic_upgrade_and_downgrade_cycle(tmp_path: Path):
    mig_db = tmp_path / "alembic_cycle.db"
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{mig_db}")

    command.upgrade(cfg, "head")
    assert mig_db.exists()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


def test_online_backup_checksum_and_verified_restore(isolated_env, db: Session):
    src = SourceChannel(title="Before Backup", identifier="@before_backup", is_enabled=True, monitoring_status="ACTIVE")
    db.add(src)
    db.commit()

    meta = create_database_backup(label="milestone")
    assert meta["filename"].endswith(".db")
    assert len(meta["sha256"]) == 64

    backups = list_database_backups()
    assert any(b["filename"] == meta["filename"] for b in backups)

    # Add another channel AFTER backup, then restore backup and verify state reverted cleanly
    after = SourceChannel(title="After Backup", identifier="@after_backup", is_enabled=True, monitoring_status="ACTIVE")
    db.add(after)
    db.commit()
    db.close()

    res = restore_database_backup(meta["filename"])
    assert res["restored_from"] == meta["filename"]
    assert res["pre_restore_backup"] is not None

    from app.database import session as db_session

    with db_session.SessionLocal() as fresh_db:
        identifiers = [
            r[0] for r in fresh_db.execute(text("SELECT identifier FROM source_channels")).fetchall()
        ]
        assert "@before_backup" in identifiers
        assert "@after_backup" not in identifiers

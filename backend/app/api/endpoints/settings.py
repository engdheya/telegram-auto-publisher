"""System settings, SQLite WAL integrity check, and Online Backup & Restore endpoints."""

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.database.backup import (
    create_database_backup,
    get_backup_path,
    list_database_backups,
    restore_database_backup,
)
from app.database.integrity import validate_database_integrity
from app.database.session import get_db
from app.models import User
from app.repositories.audit_repo import AuditRepository
from app.repositories.setting_repo import SettingRepository
from app.schemas.setting import (
    BackupCreateRequest,
    BackupRestoreRequest,
    SystemSettingsBulkUpdate,
)

router = APIRouter(prefix="/settings", tags=["System Settings & Backup"])


@router.get("")
def get_all_settings(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return {"items": SettingRepository.list_all(db, include_runtime=False)}


@router.put("")
def update_settings(
    payload: SystemSettingsBulkUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    for item in payload.settings:
        prefix = item.key.split(".")[0] if "." in item.key else "general"
        SettingRepository.set_value(
            db,
            item.key,
            item.value,
            category=prefix,
            updated_by=admin.username,
        )
    AuditRepository.record(
        db,
        level="INFO",
        category="SYSTEM",
        action="SETTINGS_UPDATED",
        actor_user_id=admin.id,
        actor_username=admin.username,
        message=f"Updated {len(payload.settings)} system setting(s).",
        details={"keys": [s.key for s in payload.settings]},
    )
    db.commit()
    return {"items": SettingRepository.list_all(db, include_runtime=False)}


@router.get("/integrity")
def check_database_integrity(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return validate_database_integrity(db)


@router.get("/backups")
def get_backups(_admin: User = Depends(require_admin)) -> dict[str, Any]:
    return {"items": list_database_backups()}


@router.post("/backups", status_code=201)
def create_backup(
    payload: BackupCreateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    meta = create_database_backup(label=payload.label)
    AuditRepository.record(
        db,
        level="INFO",
        category="BACKUP",
        action="BACKUP_CREATED",
        actor_user_id=admin.id,
        actor_username=admin.username,
        message=f"Created verified online SQLite backup '{meta['filename']}'.",
        details=meta,
        commit=True,
    )
    return meta


@router.get("/backups/{filename}/download")
def download_backup(
    filename: str,
    _admin: User = Depends(require_admin),
) -> FileResponse:
    path = get_backup_path(filename)
    return FileResponse(
        path=str(path),
        filename=path.name,
        media_type="application/x-sqlite3",
    )


@router.post("/backups/restore")
def restore_backup(
    payload: BackupRestoreRequest,
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    result = restore_database_backup(payload.filename)
    # Open a fresh session on the newly restored engine to record restore audit log
    from app.database import session as db_session

    with db_session.SessionLocal() as fresh_db:
        AuditRepository.record(
            fresh_db,
            level="WARNING",
            category="BACKUP",
            action="BACKUP_RESTORED",
            actor_user_id=admin.id,
            actor_username=admin.username,
            message=f"Restored SQLite database from backup '{payload.filename}'.",
            details=result,
            commit=True,
        )
    return result

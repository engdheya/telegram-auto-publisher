"""Online hot-safe SQLite Backup & Verified Restore using sqlite3.Connection.backup."""

import hashlib
import os
import sqlite3
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import AppError, ResourceNotFoundError
from app.database import session as db_session
from app.utils.time import utcnow

SQLITE_HEADER_MAGIC = b"SQLite format 3\x00"


def _resolve_sqlite_path(database_url: str | None = None) -> Path:
    url = database_url or get_settings().DATABASE_URL
    if not url.startswith("sqlite:///"):
        raise AppError("Online SQLite backup requires a file-backed sqlite:/// URL.")
    raw_path = url.replace("sqlite:///", "", 1)
    if not raw_path or raw_path == ":memory:":
        raise AppError("Cannot create file backup from an in-memory SQLite database.")
    return Path(raw_path).resolve()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_sqlite_backup_file(path: Path) -> None:
    if not path.exists() or path.stat().st_size < 100:
        raise AppError("Backup file is empty or invalid.")
    with path.open("rb") as f:
        header = f.read(16)
    if header != SQLITE_HEADER_MAGIC:
        raise AppError("File does not have a valid SQLite 3 header.")

    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        res = conn.execute("PRAGMA integrity_check;").fetchall()
        if res != [("ok",)]:
            raise AppError(f"Backup integrity_check failed: {res}")
    finally:
        conn.close()


def create_database_backup(
    *,
    label: str | None = None,
    database_url: str | None = None,
    backup_dir: str | None = None,
) -> dict[str, Any]:
    """Perform consistent online hot backup of the live WAL SQLite database."""
    src_path = _resolve_sqlite_path(database_url)
    if not src_path.exists():
        raise AppError(f"Source database does not exist at {src_path}")

    out_dir = Path(backup_dir or get_settings().BACKUP_DIR).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = utcnow().strftime("%Y%m%d_%H%M%S_%f")
    safe_label = ""
    if label:
        cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in label.strip())
        if cleaned:
            safe_label = f"_{cleaned[:32]}"

    filename = f"tap_backup_{ts}{safe_label}.db"
    dest_path = out_dir / filename

    src_conn = sqlite3.connect(str(src_path), timeout=15.0)
    dst_conn = sqlite3.connect(str(dest_path), timeout=15.0)
    try:
        with dst_conn:
            src_conn.backup(dst_conn, pages=250, sleep=0.01)
    finally:
        dst_conn.close()
        src_conn.close()

    # Restrict file permissions so non-owners cannot read encrypted credentials
    os.chmod(dest_path, 0o600)
    _verify_sqlite_backup_file(dest_path)

    checksum = _sha256_file(dest_path)
    checksum_path = dest_path.with_suffix(".db.sha256")
    checksum_path.write_text(f"{checksum}  {filename}\n", encoding="utf-8")
    os.chmod(checksum_path, 0o600)

    stat = dest_path.stat()
    return {
        "filename": filename,
        "size_bytes": stat.st_size,
        "sha256": checksum,
        "created_at": utcnow().isoformat(),
    }


def list_database_backups(backup_dir: str | None = None) -> list[dict[str, Any]]:
    out_dir = Path(backup_dir or get_settings().BACKUP_DIR).resolve()
    if not out_dir.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(out_dir.glob("tap_backup_*.db"), key=lambda p: p.stat().st_mtime, reverse=True):
        sha_file = path.with_suffix(".db.sha256")
        sha = None
        if sha_file.exists():
            sha = sha_file.read_text(encoding="utf-8").split()[0]
        stat = path.stat()
        items.append(
            {
                "filename": path.name,
                "size_bytes": stat.st_size,
                "sha256": sha,
                "created_at": utcnow().fromtimestamp(stat.st_mtime, tz=utcnow().tzinfo).isoformat(),
            }
        )
    return items


def get_backup_path(filename: str, backup_dir: str | None = None) -> Path:
    out_dir = Path(backup_dir or get_settings().BACKUP_DIR).resolve()
    safe_name = os.path.basename(filename)
    if safe_name != filename or not safe_name.endswith(".db"):
        raise AppError("Invalid backup filename.")
    candidate = (out_dir / safe_name).resolve()
    if candidate.parent != out_dir or not candidate.exists():
        raise ResourceNotFoundError(f"Backup '{safe_name}' not found.")
    return candidate


def restore_database_backup(
    filename: str,
    *,
    database_url: str | None = None,
    backup_dir: str | None = None,
) -> dict[str, Any]:
    """Validate backup integrity & checksum, take pre-restore safety snapshot, and restore atomically."""
    backup_path = get_backup_path(filename, backup_dir=backup_dir)
    _verify_sqlite_backup_file(backup_path)

    sha_file = backup_path.with_suffix(".db.sha256")
    actual_sha = _sha256_file(backup_path)
    if sha_file.exists():
        expected_sha = sha_file.read_text(encoding="utf-8").split()[0]
        if actual_sha != expected_sha:
            raise AppError("Backup SHA-256 checksum mismatch; refusing to restore corrupted file.")

    target_db_path = _resolve_sqlite_path(database_url)
    pre_snapshot = None
    if target_db_path.exists() and target_db_path.stat().st_size > 0:
        pre_snapshot = create_database_backup(
            label="pre_restore_auto", database_url=database_url, backup_dir=backup_dir
        )

    # Dispose active pool before copying pages into live DB
    db_session.engine.dispose()

    src_conn = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True, timeout=15.0)
    dst_conn = sqlite3.connect(str(target_db_path), timeout=15.0)
    try:
        with dst_conn:
            src_conn.backup(dst_conn)
        dst_conn.execute("PRAGMA journal_mode=WAL;")
    finally:
        dst_conn.close()
        src_conn.close()

    os.chmod(target_db_path, 0o600)
    db_session.reset_engine(database_url or get_settings().DATABASE_URL)
    return {
        "restored_from": filename,
        "sha256": actual_sha,
        "pre_restore_backup": pre_snapshot["filename"] if pre_snapshot else None,
        "restored_at": utcnow().isoformat(),
    }

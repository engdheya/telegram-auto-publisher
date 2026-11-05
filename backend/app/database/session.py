"""SQLite WAL-enabled SQLAlchemy engine and transactional session factory."""

from collections.abc import Generator
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _configure_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.execute("PRAGMA busy_timeout=15000;")
    cursor.close()


def build_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().DATABASE_URL
    connect_args: dict[str, Any] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        connect_args["timeout"] = 15.0

    eng = create_engine(
        url,
        connect_args=connect_args,
        pool_pre_ping=True,
        future=True,
    )
    if url.startswith("sqlite"):
        event.listen(eng, "connect", _configure_sqlite_pragmas)
    return eng


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def reset_engine(database_url: str) -> Engine:
    """Rebind global engine and SessionLocal (used during isolated tests or restore)."""
    global engine, SessionLocal
    engine.dispose()
    engine = build_engine(database_url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return engine


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

"""Application configuration loaded from environment variables / .env."""

from functools import lru_cache
from pathlib import Path
from typing import List

from cryptography.fernet import Fernet
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"

def _resolve_user_path(raw: str, default: Path) -> str:
    """Resolve a possibly relative storage path against the project root.

    `.env.example` ships repo-relative defaults (`./runtime/…`) so a fresh clone
    works for any user; production deployments override them with absolute
    paths such as `/opt/tap/runtime/…`.
    """
    if not raw or not raw.strip():
        return str(default)
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return str(candidate)
    return str((PROJECT_ROOT / candidate).resolve())


# Deterministic fallback ONLY for isolated automated tests when .env is absent
_TEST_FALLBACK_FERNET = Fernet.generate_key().decode()
_TEST_FALLBACK_JWT = "test-only-ephemeral-jwt-secret-key-do-not-use-in-production-0123456789"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(DEFAULT_ENV_FILE) if DEFAULT_ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_NAME: str = "Telegram Auto Publisher"
    APP_ENV: str = "development"
    APP_DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    CORS_ORIGINS: List[str] = ["*"]

    JWT_SECRET_KEY: str = _TEST_FALLBACK_JWT
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720
    SESSION_ENCRYPTION_KEY: str = _TEST_FALLBACK_FERNET

    INITIAL_ADMIN_USERNAME: str = "admin"
    INITIAL_ADMIN_EMAIL: str = "admin@tap.local"
    # Neutral placeholder only: the bootstrap admin password MUST come from the environment.
    INITIAL_ADMIN_PASSWORD: str = "CHANGE_ME_ADMIN_PASSWORD"

    DATABASE_URL: str = f"sqlite:///{PROJECT_ROOT / 'runtime' / 'tap.db'}"
    BACKUP_DIR: str = str(PROJECT_ROOT / "runtime" / "backups")
    MEDIA_CACHE_DIR: str = str(PROJECT_ROOT / "runtime" / "media_cache")
    LOG_DIR: str = str(PROJECT_ROOT / "runtime" / "logs")

    TELEGRAM_DEFAULT_API_ID: str = ""
    TELEGRAM_DEFAULT_API_HASH: str = ""
    TELEGRAM_CATCHUP_LIMIT: int = 100

    WORKER_ID: str = "tap-primary-worker"
    WORKER_POLL_INTERVAL_SECONDS: float = 1.5
    WORKER_STALE_LOCK_TIMEOUT_SECONDS: int = 180
    ALBUM_AGGREGATION_WINDOW_MS: int = 2500
    PUBLISH_MAX_ATTEMPTS: int = 4
    PUBLISH_RETRY_BASE_SECONDS: int = 15
    PUBLISH_RETRY_MAX_SECONDS: int = 900
    MEDIA_CACHE_RETENTION_HOURS: int = 24

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt_secret(cls, v: str, info) -> str:
        env = (info.data or {}).get("APP_ENV", "development")
        if env == "production" and ("CHANGE_ME" in v or len(v) < 32):
            raise ValueError("Production requires a strong JWT_SECRET_KEY (>= 32 chars).")
        return v

    @field_validator("INITIAL_ADMIN_PASSWORD")
    @classmethod
    def validate_admin_password(cls, v: str, info) -> str:
        env = (info.data or {}).get("APP_ENV", "development")
        if env == "production" and ("CHANGE_ME" in v or len(v) < 12):
            raise ValueError(
                "Production requires INITIAL_ADMIN_PASSWORD (>= 12 chars) supplied through the environment."
            )
        return v

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def resolve_database_url(cls, v: str) -> str:
        """Make relative SQLite URLs absolute against the project root.

        Without this, `sqlite:///./runtime/tap.db` would resolve against the
        process CWD (e.g. `backend/` for Alembic) instead of the repo root.
        """
        if not v.startswith("sqlite:///"):
            return v
        raw = v[len("sqlite:///") :]
        if not raw or raw == ":memory:" or raw.startswith("file:"):
            return v
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = (PROJECT_ROOT / path).resolve()
        return f"sqlite:///{path}"

    @field_validator("BACKUP_DIR", "MEDIA_CACHE_DIR", "LOG_DIR", mode="after")
    @classmethod
    def resolve_storage_dirs(cls, v: str, info) -> str:
        name = info.field_name
        mapping = {
            "BACKUP_DIR": PROJECT_ROOT / "runtime" / "backups",
            "MEDIA_CACHE_DIR": PROJECT_ROOT / "runtime" / "media_cache",
            "LOG_DIR": PROJECT_ROOT / "runtime" / "logs",
        }
        return _resolve_user_path(v, mapping[name])

    @field_validator("SESSION_ENCRYPTION_KEY")
    @classmethod
    def validate_encryption_key(cls, v: str, info) -> str:
        env = (info.data or {}).get("APP_ENV", "development")
        if env == "production" and "CHANGE_ME" in v:
            raise ValueError("Production requires a valid Fernet SESSION_ENCRYPTION_KEY.")
        # Validate Fernet format early
        Fernet(v.encode("utf-8"))
        return v

    def resolved_database_path(self) -> Path | None:
        """Return the SQLite file path, resolving relative URLs against the project root."""
        if not self.DATABASE_URL.startswith("sqlite:///"):
            return None
        raw = self.DATABASE_URL[len("sqlite:///") :]
        if not raw or raw == ":memory:":
            return None
        return Path(raw)

    def ensure_directories(self) -> None:
        for path_str in (self.BACKUP_DIR, self.MEDIA_CACHE_DIR, self.LOG_DIR):
            Path(path_str).mkdir(parents=True, exist_ok=True)
        db_path = self.resolved_database_path()
        if db_path is not None:
            db_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings

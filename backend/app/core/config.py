"""Application configuration loaded from environment variables / .env."""

from functools import lru_cache
from pathlib import Path
from typing import List

from cryptography.fernet import Fernet
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"

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
    INITIAL_ADMIN_PASSWORD: str = "Admin@2026!Secure"

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

    @field_validator("SESSION_ENCRYPTION_KEY")
    @classmethod
    def validate_encryption_key(cls, v: str, info) -> str:
        env = (info.data or {}).get("APP_ENV", "development")
        if env == "production" and "CHANGE_ME" in v:
            raise ValueError("Production requires a valid Fernet SESSION_ENCRYPTION_KEY.")
        # Validate Fernet format early
        Fernet(v.encode("utf-8"))
        return v

    def ensure_directories(self) -> None:
        for path_str in (self.BACKUP_DIR, self.MEDIA_CACHE_DIR, self.LOG_DIR):
            Path(path_str).mkdir(parents=True, exist_ok=True)
        if self.DATABASE_URL.startswith("sqlite:///"):
            db_path = self.DATABASE_URL.replace("sqlite:///", "", 1)
            if db_path and db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings

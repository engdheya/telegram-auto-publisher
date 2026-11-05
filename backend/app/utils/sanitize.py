"""Redaction and input sanitization helpers to guarantee zero secret leakage."""

import re
from typing import Any

SENSITIVE_KEY_SUBSTRINGS = (
    "password",
    "secret",
    "token",
    "session",
    "api_hash",
    "phone_code",
    "otp",
    "verification_code",
    "authorization",
    "cookie",
    "encryption_key",
)

# Matches JWTs (eyJ...) and long base64-like Telethon StringSession blobs (1BVts... / 1ApW...)
JWT_REGEX = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
LONG_SECRET_BLOB_REGEX = re.compile(r"\b1[A-Za-z0-9+/=_-]{80,}\b")


def mask_string(value: str) -> str:
    """Scrub embedded JWTs or Telethon session strings from arbitrary log text."""
    if not value:
        return value
    scrubbed = JWT_REGEX.sub("[REDACTED_JWT]", value)
    scrubbed = LONG_SECRET_BLOB_REGEX.sub("[REDACTED_SESSION]", scrubbed)
    return scrubbed


def is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in SENSITIVE_KEY_SUBSTRINGS)


def sanitize_sensitive_data(data: Any) -> Any:
    """Recursively scrub dictionaries, lists, and strings before logging or auditing."""
    if data is None:
        return None
    if isinstance(data, dict):
        sanitized: dict[str, Any] = {}
        for k, v in data.items():
            key_str = str(k)
            if is_sensitive_key(key_str):
                sanitized[key_str] = "[REDACTED]"
            else:
                sanitized[key_str] = sanitize_sensitive_data(v)
        return sanitized
    if isinstance(data, (list, tuple, set)):
        return [sanitize_sensitive_data(item) for item in data]
    if isinstance(data, str):
        return mask_string(data)
    return data


def mask_phone(phone: str | None) -> str | None:
    """Mask phone number for safe UI/log display while preserving country prefix and last 2 digits."""
    if not phone:
        return None
    cleaned = phone.strip()
    if len(cleaned) <= 5:
        return "***"
    return f"{cleaned[:4]}{'*' * max(3, len(cleaned) - 6)}{cleaned[-2:]}"

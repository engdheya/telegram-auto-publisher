"""Argon2id password hashing and signed JWT session tokens."""

import uuid
from datetime import timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.utils.time import utcnow

_password_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=65536,
    parallelism=2,
    hash_len=32,
    salt_len=16,
)


def hash_password(plain_password: str) -> str:
    """Hash user password using Argon2id."""
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify plain password against Argon2id hash in constant time."""
    try:
        return _password_hasher.verify(password_hash, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_access_token(
    *,
    user_id: int,
    username: str,
    role: str,
    token_version: int = 1,
    expires_minutes: int | None = None,
) -> str:
    settings = get_settings()
    now = utcnow()
    ttl = expires_minutes if expires_minutes is not None else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "ver": token_version,
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl)).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "exp", "iat", "ver"]},
        )
        return payload
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid or expired authentication token") from exc

"""FastAPI authentication, session validation, and RBAC dependencies."""

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import decode_access_token
from app.database.session import get_db
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Authentication required: missing Bearer token.")
    payload = decode_access_token(credentials.credentials)
    user_id = int(payload["sub"])
    token_ver = int(payload.get("ver", 1))

    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthenticationError("User account is inactive or no longer exists.")
    if user.token_version != token_ver:
        raise AuthenticationError("Session invalidated after security update; please log in again.")
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise PermissionDeniedError("Administrator role is required for this operation.")
    return current_user

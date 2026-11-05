"""Authentication, session management, password update, and user RBAC endpoints."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_client_ip, get_current_user, require_admin
from app.core.config import get_settings
from app.core.exceptions import AppError, AuthenticationError, ConflictError
from app.core.security import create_access_token, hash_password, verify_password
from app.database.session import get_db
from app.models import User
from app.repositories.audit_repo import AuditRepository
from app.repositories.setting_repo import SettingRepository
from app.schemas.auth import (
    LanguageUpdateRequest,
    LoginRequest,
    PasswordChangeRequest,
    TokenResponse,
    UserCreateRequest,
    UserRead,
)
from app.utils.time import utcnow

router = APIRouter(prefix="/auth", tags=["Authentication & Users"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    ip = get_client_ip(request)
    user = db.execute(
        select(User).where(User.username == payload.username.strip())
    ).scalar_one_or_none()

    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        AuditRepository.record(
            db,
            level="WARNING",
            category="AUTH",
            action="LOGIN_FAILED",
            actor_username=payload.username.strip(),
            message=f"Failed login attempt for username '{payload.username.strip()}'.",
            ip_address=ip,
            commit=True,
        )
        raise AuthenticationError("Invalid username or password.")

    ttl_min = int(
        SettingRepository.get_value(
            db, "security.session_expire_minutes", get_settings().ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )
    user.last_login_at = utcnow()
    token = create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role,
        token_version=user.token_version,
        expires_minutes=ttl_min,
    )
    AuditRepository.record(
        db,
        level="INFO",
        category="AUTH",
        action="LOGIN_SUCCESS",
        actor_user_id=user.id,
        actor_username=user.username,
        entity_type="user",
        entity_id=user.id,
        message=f"User '{user.username}' signed in successfully.",
        ip_address=ip,
        commit=True,
    )
    return TokenResponse(
        access_token=token,
        expires_in_seconds=ttl_min * 60,
        user=UserRead.model_validate(user),
    )


@router.get("/me", response_model=UserRead)
def get_me(current_user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user)


@router.post("/change-password", response_model=TokenResponse)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TokenResponse:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise AuthenticationError("Current password is incorrect.")
    if payload.current_password == payload.new_password:
        raise AppError("New password must differ from current password.")

    current_user.password_hash = hash_password(payload.new_password)
    current_user.token_version = (current_user.token_version or 1) + 1
    ttl_min = int(
        SettingRepository.get_value(
            db, "security.session_expire_minutes", get_settings().ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )
    new_token = create_access_token(
        user_id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        token_version=current_user.token_version,
        expires_minutes=ttl_min,
    )
    AuditRepository.record(
        db,
        level="INFO",
        category="SECURITY",
        action="PASSWORD_CHANGED",
        actor_user_id=current_user.id,
        actor_username=current_user.username,
        entity_type="user",
        entity_id=current_user.id,
        message=f"Password updated and prior sessions revoked for '{current_user.username}'.",
        ip_address=get_client_ip(request),
        commit=True,
    )
    return TokenResponse(
        access_token=new_token,
        expires_in_seconds=ttl_min * 60,
        user=UserRead.model_validate(current_user),
    )


@router.patch("/language", response_model=UserRead)
def update_preferred_language(
    payload: LanguageUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserRead:
    current_user.preferred_language = payload.preferred_language
    db.commit()
    db.refresh(current_user)
    return UserRead.model_validate(current_user)


@router.get("/users", response_model=list[UserRead])
def list_users(_admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[UserRead]:
    users = db.execute(select(User).order_by(User.id.asc())).scalars().all()
    return [UserRead.model_validate(u) for u in users]


@router.post("/users", response_model=UserRead, status_code=201)
def create_user(
    payload: UserCreateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserRead:
    dup = db.execute(
        select(User).where((User.username == payload.username) | (User.email == payload.email))
    ).scalar_one_or_none()
    if dup is not None:
        raise ConflictError("Username or email already exists.")

    new_user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
        preferred_language=payload.preferred_language,
    )
    db.add(new_user)
    AuditRepository.record(
        db,
        level="INFO",
        category="SECURITY",
        action="USER_CREATED",
        actor_user_id=admin.id,
        actor_username=admin.username,
        entity_type="user",
        message=f"Created user '{payload.username}' with role '{payload.role}'.",
    )
    db.commit()
    db.refresh(new_user)
    return UserRead.model_validate(new_user)

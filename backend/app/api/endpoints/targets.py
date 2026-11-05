"""Target channels CRUD, admin permission verification, and test post publishing."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.exceptions import ConflictError, ResourceNotFoundError, TelegramOperationError
from app.database.session import get_db
from app.models import TargetChannel, User
from app.repositories.audit_repo import AuditRepository
from app.schemas.target import (
    TargetChannelCreate,
    TargetChannelRead,
    TargetChannelUpdate,
    TargetTestPublishRequest,
    TargetVerifyResponse,
)
from app.telegram.gateway import get_telegram_gateway
from app.utils.time import utcnow

router = APIRouter(prefix="/targets", tags=["Target Channels"])


def _normalize_identifier(raw: str) -> str:
    s = raw.strip()
    for p in ("https://t.me/", "http://t.me/", "t.me/"):
        if s.lower().startswith(p):
            slug = s[len(p) :].strip("/")
            if slug and not slug.startswith("+") and not slug.startswith("joinchat"):
                return f"@{slug}"
            return s
    return s


@router.get("", response_model=list[TargetChannelRead])
def list_targets(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TargetChannelRead]:
    rows = db.execute(select(TargetChannel).order_by(TargetChannel.id.desc())).scalars().all()
    return [TargetChannelRead.model_validate(r) for r in rows]


@router.post("", response_model=TargetChannelRead, status_code=201)
async def create_target(
    payload: TargetChannelCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TargetChannelRead:
    ident = _normalize_identifier(payload.identifier)
    dup = db.execute(select(TargetChannel).where(TargetChannel.identifier == ident)).scalar_one_or_none()
    if dup is not None:
        raise ConflictError(f"Target channel '{ident}' is already registered.")

    target = TargetChannel(
        title=payload.title.strip(),
        identifier=ident,
        username=ident[1:] if ident.startswith("@") else None,
        invite_link=payload.invite_link,
        is_enabled=payload.is_enabled,
        permission_status="UNVERIFIED",
    )

    gateway = get_telegram_gateway()
    if gateway.is_live_connected():
        try:
            info = await gateway.inspect_target_channel(ident)
            target.telegram_peer_id = info["peer_id"]
            target.title = info.get("title") or target.title
            target.username = info.get("username") or target.username
            target.can_post_messages = bool(info.get("can_post_messages", False))
            target.can_post_media = bool(info.get("can_post_media", False))
            target.last_verified_at = utcnow()
            target.permission_status = (
                "VERIFIED" if target.can_post_messages else "INSUFFICIENT_PERMISSIONS"
            )
            if not target.can_post_messages:
                target.last_error = "Account lacks 'Post Messages' admin permission in this channel."
        except TelegramOperationError as exc:
            target.permission_status = "ERROR"
            target.last_error = exc.message

    db.add(target)
    AuditRepository.record(
        db,
        level="INFO",
        category="TARGET",
        action="TARGET_CREATED",
        actor_user_id=user.id,
        actor_username=user.username,
        entity_type="target_channel",
        message=f"Added target channel '{target.title}' ({target.identifier}).",
    )
    db.commit()
    db.refresh(target)
    return TargetChannelRead.model_validate(target)


@router.patch("/{target_id}", response_model=TargetChannelRead)
def update_target(
    target_id: int,
    payload: TargetChannelUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TargetChannelRead:
    target = db.execute(select(TargetChannel).where(TargetChannel.id == target_id)).scalar_one_or_none()
    if target is None:
        raise ResourceNotFoundError(f"Target channel #{target_id} not found.")

    if payload.title is not None:
        target.title = payload.title.strip()
    if payload.identifier is not None:
        ident = _normalize_identifier(payload.identifier)
        if ident != target.identifier:
            dup = db.execute(select(TargetChannel).where(TargetChannel.identifier == ident)).scalar_one_or_none()
            if dup is not None:
                raise ConflictError(f"Identifier '{ident}' is already in use.")
            target.identifier = ident
            target.username = ident[1:] if ident.startswith("@") else None
    if payload.invite_link is not None:
        target.invite_link = payload.invite_link
    if payload.is_enabled is not None:
        target.is_enabled = payload.is_enabled

    AuditRepository.record(
        db,
        level="INFO",
        category="TARGET",
        action="TARGET_UPDATED",
        actor_user_id=user.id,
        actor_username=user.username,
        entity_type="target_channel",
        entity_id=target.id,
        message=f"Updated target channel '{target.title}'.",
    )
    db.commit()
    db.refresh(target)
    return TargetChannelRead.model_validate(target)


@router.post("/{target_id}/verify", response_model=TargetVerifyResponse)
async def verify_target_permissions(
    target_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TargetVerifyResponse:
    target = db.execute(select(TargetChannel).where(TargetChannel.id == target_id)).scalar_one_or_none()
    if target is None:
        raise ResourceNotFoundError(f"Target channel #{target_id} not found.")

    gateway = get_telegram_gateway()
    try:
        info = await gateway.inspect_target_channel(target.identifier)
        target.telegram_peer_id = info["peer_id"]
        target.title = info.get("title") or target.title
        target.username = info.get("username") or target.username
        target.can_post_messages = bool(info.get("can_post_messages", False))
        target.can_post_media = bool(info.get("can_post_media", False))
        target.last_verified_at = utcnow()
        if target.can_post_messages:
            target.permission_status = "VERIFIED"
            target.last_error = None
            detail = f"Verified publishing permissions in '{target.title}'."
        else:
            target.permission_status = "INSUFFICIENT_PERMISSIONS"
            target.last_error = "Connected Telegram account does not have permission to post in this channel."
            detail = target.last_error

        AuditRepository.record(
            db,
            level="INFO" if target.can_post_messages else "WARNING",
            category="TARGET",
            action="TARGET_VERIFIED",
            actor_user_id=user.id,
            actor_username=user.username,
            entity_type="target_channel",
            entity_id=target.id,
            message=detail,
        )
        db.commit()
        db.refresh(target)
        return TargetVerifyResponse(
            ok=target.can_post_messages,
            target=TargetChannelRead.model_validate(target),
            detail=detail,
        )
    except TelegramOperationError as exc:
        target.permission_status = "ERROR"
        target.last_error = exc.message
        AuditRepository.record(
            db,
            level="ERROR",
            category="TARGET",
            action="TARGET_VERIFY_FAILED",
            actor_user_id=user.id,
            actor_username=user.username,
            entity_type="target_channel",
            entity_id=target.id,
            message=exc.message,
        )
        db.commit()
        db.refresh(target)
        return TargetVerifyResponse(
            ok=False,
            target=TargetChannelRead.model_validate(target),
            detail=exc.message,
        )


@router.post("/{target_id}/test-publish", response_model=TargetVerifyResponse)
async def test_publish_to_target(
    target_id: int,
    payload: TargetTestPublishRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TargetVerifyResponse:
    target = db.execute(select(TargetChannel).where(TargetChannel.id == target_id)).scalar_one_or_none()
    if target is None:
        raise ResourceNotFoundError(f"Target channel #{target_id} not found.")

    gateway = get_telegram_gateway()
    ref = str(target.telegram_peer_id) if target.telegram_peer_id is not None else target.identifier
    try:
        msg_id = await gateway.send_target_test_message(ref, payload.message)
        now = utcnow()
        target.permission_status = "VERIFIED"
        target.can_post_messages = True
        target.last_verified_at = now
        target.last_test_post_at = now
        target.last_error = None
        detail = f"Test post published successfully (message_id={msg_id})."
        AuditRepository.record(
            db,
            level="INFO",
            category="TARGET",
            action="TARGET_TEST_PUBLISHED",
            actor_user_id=user.id,
            actor_username=user.username,
            entity_type="target_channel",
            entity_id=target.id,
            message=detail,
        )
        db.commit()
        db.refresh(target)
        return TargetVerifyResponse(
            ok=True,
            target=TargetChannelRead.model_validate(target),
            detail=detail,
            test_message_id=msg_id,
        )
    except TelegramOperationError as exc:
        target.permission_status = "ERROR"
        target.last_error = exc.message
        AuditRepository.record(
            db,
            level="ERROR",
            category="TARGET",
            action="TARGET_TEST_FAILED",
            actor_user_id=user.id,
            actor_username=user.username,
            entity_type="target_channel",
            entity_id=target.id,
            message=exc.message,
        )
        db.commit()
        db.refresh(target)
        return TargetVerifyResponse(
            ok=False,
            target=TargetChannelRead.model_validate(target),
            detail=exc.message,
        )


@router.delete("/{target_id}", status_code=204)
def delete_target(
    target_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    target = db.execute(select(TargetChannel).where(TargetChannel.id == target_id)).scalar_one_or_none()
    if target is None:
        raise ResourceNotFoundError(f"Target channel #{target_id} not found.")
    title = target.title
    db.delete(target)
    AuditRepository.record(
        db,
        level="INFO",
        category="TARGET",
        action="TARGET_DELETED",
        actor_user_id=user.id,
        actor_username=user.username,
        entity_type="target_channel",
        entity_id=target_id,
        message=f"Deleted target channel '{title}'.",
    )
    db.commit()

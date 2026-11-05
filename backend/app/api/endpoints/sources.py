"""Source channels CRUD, access verification, baseline initialization, and start/stop monitoring."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.exceptions import ConflictError, ResourceNotFoundError, TelegramOperationError
from app.database.session import get_db
from app.models import SourceChannel, User
from app.repositories.audit_repo import AuditRepository
from app.schemas.source import (
    SourceChannelCreate,
    SourceChannelRead,
    SourceChannelUpdate,
    SourceVerifyResponse,
)
from app.telegram.gateway import get_telegram_gateway
from app.utils.time import utcnow

router = APIRouter(prefix="/sources", tags=["Source Channels"])


def _normalize_identifier(raw: str) -> str:
    s = raw.strip()
    for p in ("https://t.me/", "http://t.me/", "t.me/"):
        if s.lower().startswith(p):
            slug = s[len(p) :].strip("/")
            if slug and not slug.startswith("+") and not slug.startswith("joinchat"):
                return f"@{slug}"
            return s
    return s


@router.get("", response_model=list[SourceChannelRead])
def list_sources(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SourceChannelRead]:
    rows = db.execute(select(SourceChannel).order_by(SourceChannel.id.desc())).scalars().all()
    return [SourceChannelRead.model_validate(r) for r in rows]


@router.post("", response_model=SourceChannelRead, status_code=201)
async def create_source(
    payload: SourceChannelCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SourceChannelRead:
    ident = _normalize_identifier(payload.identifier)
    dup = db.execute(select(SourceChannel).where(SourceChannel.identifier == ident)).scalar_one_or_none()
    if dup is not None:
        raise ConflictError(f"Source channel '{ident}' is already registered.")

    source = SourceChannel(
        title=payload.title.strip(),
        identifier=ident,
        username=ident[1:] if ident.startswith("@") else None,
        invite_link=payload.invite_link,
        is_enabled=payload.is_enabled,
        monitoring_status="ACTIVE" if payload.is_enabled else "PAUSED",
    )

    gateway = get_telegram_gateway()
    if gateway.is_live_connected():
        try:
            info = await gateway.inspect_source_channel(ident)
            source.telegram_peer_id = info["peer_id"]
            source.title = info.get("title") or source.title
            source.username = info.get("username") or source.username
            source.noforwards_protected = bool(info.get("noforwards", False))
            # Document baseline so old archive posts are NEVER imported!
            latest_id = int(info.get("latest_message_id") or 0)
            source.baseline_message_id = latest_id
            source.last_processed_message_id = latest_id
            source.access_verified_at = utcnow()
            source.monitoring_status = "ACTIVE" if payload.is_enabled else "PAUSED"
        except TelegramOperationError as exc:
            source.monitoring_status = "ERROR"
            source.last_error = exc.message

    db.add(source)
    AuditRepository.record(
        db,
        level="INFO",
        category="SOURCE",
        action="SOURCE_CREATED",
        actor_user_id=user.id,
        actor_username=user.username,
        entity_type="source_channel",
        message=f"Added source channel '{source.title}' ({source.identifier}).",
    )
    db.commit()
    db.refresh(source)
    return SourceChannelRead.model_validate(source)


@router.patch("/{source_id}", response_model=SourceChannelRead)
def update_source(
    source_id: int,
    payload: SourceChannelUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SourceChannelRead:
    source = db.execute(select(SourceChannel).where(SourceChannel.id == source_id)).scalar_one_or_none()
    if source is None:
        raise ResourceNotFoundError(f"Source channel #{source_id} not found.")

    if payload.title is not None:
        source.title = payload.title.strip()
    if payload.identifier is not None:
        ident = _normalize_identifier(payload.identifier)
        if ident != source.identifier:
            dup = db.execute(select(SourceChannel).where(SourceChannel.identifier == ident)).scalar_one_or_none()
            if dup is not None:
                raise ConflictError(f"Identifier '{ident}' is already in use.")
            source.identifier = ident
            source.username = ident[1:] if ident.startswith("@") else None
    if payload.invite_link is not None:
        source.invite_link = payload.invite_link
    if payload.is_enabled is not None:
        source.is_enabled = payload.is_enabled
        if payload.is_enabled and source.monitoring_status == "PAUSED":
            source.monitoring_status = "ACTIVE"
        elif not payload.is_enabled:
            source.monitoring_status = "PAUSED"

    AuditRepository.record(
        db,
        level="INFO",
        category="SOURCE",
        action="SOURCE_UPDATED",
        actor_user_id=user.id,
        actor_username=user.username,
        entity_type="source_channel",
        entity_id=source.id,
        message=f"Updated source channel '{source.title}'.",
    )
    db.commit()
    db.refresh(source)
    return SourceChannelRead.model_validate(source)


@router.post("/{source_id}/verify", response_model=SourceVerifyResponse)
async def verify_source_access(
    source_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SourceVerifyResponse:
    source = db.execute(select(SourceChannel).where(SourceChannel.id == source_id)).scalar_one_or_none()
    if source is None:
        raise ResourceNotFoundError(f"Source channel #{source_id} not found.")

    gateway = get_telegram_gateway()
    try:
        info = await gateway.inspect_source_channel(source.identifier)
        now = utcnow()
        source.telegram_peer_id = info["peer_id"]
        source.title = info.get("title") or source.title
        source.username = info.get("username") or source.username
        source.noforwards_protected = bool(info.get("noforwards", False))
        latest_id = int(info.get("latest_message_id") or 0)
        if source.baseline_message_id is None:
            source.baseline_message_id = latest_id
            source.last_processed_message_id = latest_id
        source.access_verified_at = now
        source.last_error = None
        if source.is_enabled:
            source.monitoring_status = "ACTIVE"

        detail = (
            f"Access verified (peer_id={source.telegram_peer_id}, baseline_msg_id={source.baseline_message_id})."
        )
        if source.noforwards_protected:
            detail += " Warning: channel has content protection (noforwards); posts will be recorded as SKIPPED."

        AuditRepository.record(
            db,
            level="INFO",
            category="SOURCE",
            action="SOURCE_VERIFIED",
            actor_user_id=user.id,
            actor_username=user.username,
            entity_type="source_channel",
            entity_id=source.id,
            message=detail,
        )
        db.commit()
        db.refresh(source)
        return SourceVerifyResponse(
            accessible=True, source=SourceChannelRead.model_validate(source), detail=detail
        )
    except TelegramOperationError as exc:
        source.monitoring_status = "ERROR"
        source.last_error = exc.message
        AuditRepository.record(
            db,
            level="ERROR",
            category="SOURCE",
            action="SOURCE_VERIFY_FAILED",
            actor_user_id=user.id,
            actor_username=user.username,
            entity_type="source_channel",
            entity_id=source.id,
            message=exc.message,
        )
        db.commit()
        db.refresh(source)
        return SourceVerifyResponse(
            accessible=False, source=SourceChannelRead.model_validate(source), detail=exc.message
        )


@router.post("/{source_id}/start", response_model=SourceChannelRead)
async def start_source_monitoring(
    source_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SourceChannelRead:
    source = db.execute(select(SourceChannel).where(SourceChannel.id == source_id)).scalar_one_or_none()
    if source is None:
        raise ResourceNotFoundError(f"Source channel #{source_id} not found.")

    gateway = get_telegram_gateway()
    if source.baseline_message_id is None and gateway.is_live_connected():
        try:
            info = await gateway.inspect_source_channel(source.identifier)
            source.telegram_peer_id = info["peer_id"]
            source.baseline_message_id = int(info.get("latest_message_id") or 0)
            source.last_processed_message_id = source.baseline_message_id
            source.access_verified_at = utcnow()
        except Exception as exc:
            source.last_error = str(exc)

    source.is_enabled = True
    source.monitoring_status = "ACTIVE"
    source.last_error = None
    AuditRepository.record(
        db,
        level="INFO",
        category="SOURCE",
        action="SOURCE_MONITORING_STARTED",
        actor_user_id=user.id,
        actor_username=user.username,
        entity_type="source_channel",
        entity_id=source.id,
        message=f"Started monitoring source '{source.title}'.",
    )
    db.commit()
    db.refresh(source)
    return SourceChannelRead.model_validate(source)


@router.post("/{source_id}/stop", response_model=SourceChannelRead)
def stop_source_monitoring(
    source_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SourceChannelRead:
    source = db.execute(select(SourceChannel).where(SourceChannel.id == source_id)).scalar_one_or_none()
    if source is None:
        raise ResourceNotFoundError(f"Source channel #{source_id} not found.")

    source.is_enabled = False
    source.monitoring_status = "PAUSED"
    AuditRepository.record(
        db,
        level="INFO",
        category="SOURCE",
        action="SOURCE_MONITORING_STOPPED",
        actor_user_id=user.id,
        actor_username=user.username,
        entity_type="source_channel",
        entity_id=source.id,
        message=f"Paused monitoring for source '{source.title}'.",
    )
    db.commit()
    db.refresh(source)
    return SourceChannelRead.model_validate(source)


@router.delete("/{source_id}", status_code=204)
def delete_source(
    source_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    source = db.execute(select(SourceChannel).where(SourceChannel.id == source_id)).scalar_one_or_none()
    if source is None:
        raise ResourceNotFoundError(f"Source channel #{source_id} not found.")
    title = source.title
    db.delete(source)
    AuditRepository.record(
        db,
        level="INFO",
        category="SOURCE",
        action="SOURCE_DELETED",
        actor_user_id=user.id,
        actor_username=user.username,
        entity_type="source_channel",
        entity_id=source_id,
        message=f"Deleted source channel '{title}'.",
    )
    db.commit()

"""Messages & Publishing History endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.core.exceptions import ResourceNotFoundError
from app.database.session import get_db
from app.models import MessageEvent, PublishJob, User
from app.repositories.job_repo import JobRepository
from app.schemas.message import MessageEventRead, PaginatedMessagesResponse

router = APIRouter(prefix="/messages", tags=["Messages & Publishing History"])


@router.get("", response_model=PaginatedMessagesResponse)
def list_messages(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    source_id: int | None = Query(default=None),
    content_type: str | None = Query(default=None),
    search: str | None = Query(default=None),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedMessagesResponse:
    stmt = select(MessageEvent).options(
        joinedload(MessageEvent.source_channel),
        joinedload(MessageEvent.media_items),
        joinedload(MessageEvent.publish_jobs).joinedload(PublishJob.target_channel),
        joinedload(MessageEvent.publish_jobs).joinedload(PublishJob.source_channel),
        joinedload(MessageEvent.publish_jobs).joinedload(PublishJob.route),
    )
    count_stmt = select(func.count(MessageEvent.id))

    if source_id is not None:
        stmt = stmt.where(MessageEvent.source_channel_id == source_id)
        count_stmt = count_stmt.where(MessageEvent.source_channel_id == source_id)
    if content_type:
        stmt = stmt.where(MessageEvent.content_type == content_type)
        count_stmt = count_stmt.where(MessageEvent.content_type == content_type)
    if search:
        q = f"%{search.strip()}%"
        stmt = stmt.where(MessageEvent.raw_text.ilike(q))
        count_stmt = count_stmt.where(MessageEvent.raw_text.ilike(q))

    total = int(db.execute(count_stmt).scalar() or 0)
    offset = (page - 1) * page_size
    events = (
        db.execute(
            stmt.order_by(MessageEvent.received_at.desc(), MessageEvent.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        .scalars()
        .unique()
        .all()
    )
    return PaginatedMessagesResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[JobRepository.event_to_read(ev) for ev in events],
    )


@router.get("/{event_id}", response_model=MessageEventRead)
def get_message_detail(
    event_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageEventRead:
    ev = (
        db.execute(
            select(MessageEvent)
            .options(
                joinedload(MessageEvent.source_channel),
                joinedload(MessageEvent.media_items),
                joinedload(MessageEvent.publish_jobs).joinedload(PublishJob.target_channel),
                joinedload(MessageEvent.publish_jobs).joinedload(PublishJob.source_channel),
                joinedload(MessageEvent.publish_jobs).joinedload(PublishJob.route),
            )
            .where(MessageEvent.id == event_id)
        )
        .scalars()
        .unique()
        .one_or_none()
    )
    if ev is None:
        raise ResourceNotFoundError(f"Message event #{event_id} not found.")
    return JobRepository.event_to_read(ev)

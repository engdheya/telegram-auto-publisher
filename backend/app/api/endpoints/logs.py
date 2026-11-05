"""Operational, error, connection, and audit logs search & filter endpoint."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models import User
from app.repositories.audit_repo import AuditRepository
from app.schemas.setting import PaginatedLogsResponse

router = APIRouter(prefix="/logs", tags=["Logs & Audit"])


@router.get("", response_model=PaginatedLogsResponse)
def list_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    level: str | None = Query(default=None),
    category: str | None = Query(default=None),
    search: str | None = Query(default=None),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedLogsResponse:
    total, items = AuditRepository.list_logs(
        db,
        page=page,
        page_size=page_size,
        level=level,
        category=category,
        search=search,
    )
    return PaginatedLogsResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items,
    )

"""Sanitized audit & operational log repository."""

import json
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.models import AuditLog
from app.schemas.setting import AuditLogRead
from app.utils.sanitize import mask_string, sanitize_sensitive_data


class AuditRepository:
    @staticmethod
    def record(
        db: Session,
        *,
        level: str = "INFO",
        category: str = "SYSTEM",
        action: str,
        message: str,
        actor_user_id: int | None = None,
        actor_username: str | None = None,
        entity_type: str | None = None,
        entity_id: str | int | None = None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        commit: bool = False,
    ) -> AuditLog:
        safe_message = mask_string(message)
        safe_details = sanitize_sensitive_data(details or {})
        entry = AuditLog(
            level=level.upper(),
            category=category.upper(),
            action=action,
            actor_user_id=actor_user_id,
            actor_username=actor_username,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            message=safe_message,
            details_json=json.dumps(safe_details, ensure_ascii=False, default=str),
            ip_address=ip_address,
        )
        db.add(entry)
        if commit:
            db.commit()
            db.refresh(entry)
        log_fn = getattr(logger, level.lower(), logger.info)
        log_fn("[%s:%s] %s", category.upper(), action, safe_message)
        return entry

    @staticmethod
    def to_read(entry: AuditLog) -> AuditLogRead:
        try:
            parsed = json.loads(entry.details_json or "{}")
        except Exception:
            parsed = {}
        return AuditLogRead(
            id=entry.id,
            level=entry.level,
            category=entry.category,
            action=entry.action,
            actor_user_id=entry.actor_user_id,
            actor_username=entry.actor_username,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            message=entry.message,
            details=parsed if isinstance(parsed, dict) else {"value": parsed},
            ip_address=entry.ip_address,
            created_at=entry.created_at,
        )

    @staticmethod
    def list_logs(
        db: Session,
        *,
        page: int = 1,
        page_size: int = 30,
        level: str | None = None,
        category: str | None = None,
        search: str | None = None,
    ) -> tuple[int, list[AuditLogRead]]:
        stmt = select(AuditLog)
        count_stmt = select(func.count(AuditLog.id))

        if level:
            stmt = stmt.where(AuditLog.level == level.upper())
            count_stmt = count_stmt.where(AuditLog.level == level.upper())
        if category:
            stmt = stmt.where(AuditLog.category == category.upper())
            count_stmt = count_stmt.where(AuditLog.category == category.upper())
        if search:
            q = f"%{search.strip()}%"
            cond = or_(
                AuditLog.message.ilike(q),
                AuditLog.action.ilike(q),
                AuditLog.actor_username.ilike(q),
                AuditLog.entity_id.ilike(q),
            )
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = int(db.execute(count_stmt).scalar() or 0)
        offset = max(0, (page - 1) * page_size)
        rows = (
            db.execute(stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset(offset).limit(page_size))
            .scalars()
            .all()
        )
        return total, [AuditRepository.to_read(r) for r in rows]

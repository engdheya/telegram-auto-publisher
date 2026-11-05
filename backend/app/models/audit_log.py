"""Operational, security, connection, and user action audit logs (always sanitized)."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.utils.time import utcnow


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_category_level", "category", "level"),
        Index("ix_audit_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # INFO | WARNING | ERROR | CRITICAL
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="INFO", index=True)
    # AUTH | TELEGRAM | SOURCE | TARGET | ROUTE | INGESTION | PUBLISHER | QUEUE | SYSTEM | SECURITY | BACKUP
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="SYSTEM", index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)

    actor_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_username: Mapped[str | None] = mapped_column(String(64), nullable=True)

    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    message: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

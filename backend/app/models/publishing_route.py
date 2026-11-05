"""Many-to-many publishing routes mapping Source Channels to Target Channels independently."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.utils.time import utcnow


class PublishingRoute(Base):
    __tablename__ = "publishing_routes"
    __table_args__ = (
        UniqueConstraint("source_channel_id", "target_channel_id", name="uq_route_source_target"),
        Index("ix_routes_source_enabled", "source_channel_id", "is_enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_channel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("source_channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_channel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("target_channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    source_channel = relationship("SourceChannel", back_populates="routes")
    target_channel = relationship("TargetChannel", back_populates="routes")
    route_filter = relationship(
        "RouteFilter", back_populates="route", uselist=False, cascade="all, delete-orphan"
    )
    publish_jobs = relationship("PublishJob", back_populates="route", cascade="all, delete-orphan")

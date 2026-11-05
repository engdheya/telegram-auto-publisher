"""Per-route filtering, content restriction, and text transformation rules."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.utils.time import utcnow

DEFAULT_CONTENT_TYPES_JSON = '["text","photo","video","document","audio","voice","album"]'


class RouteFilter(Base):
    __tablename__ = "route_filters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    route_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("publishing_routes.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    # Stored as canonical JSON arrays of strings
    allowed_content_types_json: Mapped[str] = mapped_column(
        Text, nullable=False, default=DEFAULT_CONTENT_TYPES_JSON
    )
    include_keywords_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    exclude_keywords_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    allowed_extensions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    min_text_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_text_length: Mapped[int | None] = mapped_column(Integer, nullable=True)

    prefix_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    suffix_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    strip_urls: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    route = relationship("PublishingRoute", back_populates="route_filter")

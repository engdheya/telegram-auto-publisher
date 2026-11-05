"""PublishingRoute and RouteFilter serialization/repository helpers."""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import PublishingRoute, RouteFilter
from app.schemas.route import ALL_CONTENT_TYPES, PublishingRouteRead, RouteFilterPayload


class RouteRepository:
    @staticmethod
    def filter_to_payload(rf: RouteFilter | None) -> RouteFilterPayload:
        if rf is None:
            return RouteFilterPayload()
        try:
            ctypes = json.loads(rf.allowed_content_types_json or "[]")
        except Exception:
            ctypes = list(ALL_CONTENT_TYPES)
        try:
            inc = json.loads(rf.include_keywords_json or "[]")
        except Exception:
            inc = []
        try:
            exc = json.loads(rf.exclude_keywords_json or "[]")
        except Exception:
            exc = []
        try:
            exts = json.loads(rf.allowed_extensions_json or "[]")
        except Exception:
            exts = []
        return RouteFilterPayload(
            allowed_content_types=ctypes,
            include_keywords=inc,
            exclude_keywords=exc,
            allowed_extensions=exts,
            min_text_length=rf.min_text_length,
            max_text_length=rf.max_text_length,
            prefix_text=rf.prefix_text,
            suffix_text=rf.suffix_text,
            target_signature=rf.target_signature,
            strip_urls=rf.strip_urls,
        )

    @staticmethod
    def apply_filter_payload(rf: RouteFilter, payload: RouteFilterPayload) -> None:
        rf.allowed_content_types_json = json.dumps(list(payload.allowed_content_types), ensure_ascii=False)
        rf.include_keywords_json = json.dumps(
            [w.strip() for w in payload.include_keywords if w and w.strip()], ensure_ascii=False
        )
        rf.exclude_keywords_json = json.dumps(
            [w.strip() for w in payload.exclude_keywords if w and w.strip()], ensure_ascii=False
        )
        rf.allowed_extensions_json = json.dumps(
            [
                (e.strip().lower() if e.strip().startswith(".") else f".{e.strip().lower()}")
                for e in payload.allowed_extensions
                if e and e.strip()
            ],
            ensure_ascii=False,
        )
        rf.min_text_length = payload.min_text_length
        rf.max_text_length = payload.max_text_length
        rf.prefix_text = payload.prefix_text
        rf.suffix_text = payload.suffix_text
        rf.target_signature = payload.target_signature
        rf.strip_urls = payload.strip_urls

    @staticmethod
    def to_read(route: PublishingRoute) -> PublishingRouteRead:
        return PublishingRouteRead(
            id=route.id,
            name=route.name,
            description=route.description,
            source_channel_id=route.source_channel_id,
            source_title=route.source_channel.title if route.source_channel else f"Source #{route.source_channel_id}",
            source_identifier=route.source_channel.identifier if route.source_channel else "",
            target_channel_id=route.target_channel_id,
            target_title=route.target_channel.title if route.target_channel else f"Target #{route.target_channel_id}",
            target_identifier=route.target_channel.identifier if route.target_channel else "",
            is_enabled=route.is_enabled,
            priority=route.priority,
            filters=RouteRepository.filter_to_payload(route.route_filter),
            created_at=route.created_at,
            updated_at=route.updated_at,
        )

    @staticmethod
    def list_routes(db: Session, source_id: int | None = None, target_id: int | None = None) -> list[PublishingRoute]:
        stmt = (
            select(PublishingRoute)
            .options(
                joinedload(PublishingRoute.source_channel),
                joinedload(PublishingRoute.target_channel),
                joinedload(PublishingRoute.route_filter),
            )
            .order_by(PublishingRoute.priority.asc(), PublishingRoute.id.desc())
        )
        if source_id is not None:
            stmt = stmt.where(PublishingRoute.source_channel_id == source_id)
        if target_id is not None:
            stmt = stmt.where(PublishingRoute.target_channel_id == target_id)
        return list(db.execute(stmt).scalars().unique().all())

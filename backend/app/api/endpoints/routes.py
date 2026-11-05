"""Publishing Routes CRUD + Multi-Source / Multi-Target bulk builder + Independent Route Filters."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.database.session import get_db
from app.models import PublishingRoute, RouteFilter, SourceChannel, TargetChannel, User
from app.repositories.audit_repo import AuditRepository
from app.repositories.route_repo import RouteRepository
from app.schemas.route import (
    BulkRouteCreateRequest,
    PublishingRouteCreate,
    PublishingRouteRead,
    PublishingRouteUpdate,
)

router = APIRouter(prefix="/routes", tags=["Publishing Routes"])


def _load_route_or_404(db: Session, route_id: int) -> PublishingRoute:
    route = (
        db.execute(
            select(PublishingRoute)
            .options(
                joinedload(PublishingRoute.source_channel),
                joinedload(PublishingRoute.target_channel),
                joinedload(PublishingRoute.route_filter),
            )
            .where(PublishingRoute.id == route_id)
        )
        .scalars()
        .unique()
        .one_or_none()
    )
    if route is None:
        raise ResourceNotFoundError(f"Route #{route_id} not found.")
    return route


@router.get("", response_model=list[PublishingRouteRead])
def list_routes(
    source_id: int | None = Query(default=None),
    target_id: int | None = Query(default=None),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PublishingRouteRead]:
    routes = RouteRepository.list_routes(db, source_id=source_id, target_id=target_id)
    return [RouteRepository.to_read(r) for r in routes]


@router.post("", response_model=PublishingRouteRead, status_code=201)
def create_route(
    payload: PublishingRouteCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PublishingRouteRead:
    src = db.execute(select(SourceChannel).where(SourceChannel.id == payload.source_channel_id)).scalar_one_or_none()
    if src is None:
        raise ResourceNotFoundError(f"Source channel #{payload.source_channel_id} not found.")
    tgt = db.execute(select(TargetChannel).where(TargetChannel.id == payload.target_channel_id)).scalar_one_or_none()
    if tgt is None:
        raise ResourceNotFoundError(f"Target channel #{payload.target_channel_id} not found.")

    dup = db.execute(
        select(PublishingRoute).where(
            PublishingRoute.source_channel_id == src.id,
            PublishingRoute.target_channel_id == tgt.id,
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise ConflictError(f"A publishing route from '{src.title}' to '{tgt.title}' already exists.")

    route = PublishingRoute(
        name=payload.name.strip(),
        description=payload.description,
        source_channel_id=src.id,
        target_channel_id=tgt.id,
        is_enabled=payload.is_enabled,
        priority=payload.priority,
    )
    db.add(route)
    db.flush()

    rf = RouteFilter(route_id=route.id)
    RouteRepository.apply_filter_payload(rf, payload.filters)
    db.add(rf)

    AuditRepository.record(
        db,
        level="INFO",
        category="ROUTE",
        action="ROUTE_CREATED",
        actor_user_id=user.id,
        actor_username=user.username,
        entity_type="publishing_route",
        entity_id=route.id,
        message=f"Created route '{route.name}' ({src.title} -> {tgt.title}).",
    )
    db.commit()
    loaded = _load_route_or_404(db, route.id)
    return RouteRepository.to_read(loaded)


@router.post("/bulk", response_model=list[PublishingRouteRead], status_code=201)
def create_bulk_routes(
    payload: BulkRouteCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PublishingRouteRead]:
    """Create 1->N, N->1, or N->N routes in one operation, skipping existing pairs cleanly."""
    sources = {
        s.id: s
        for s in db.execute(select(SourceChannel).where(SourceChannel.id.in_(payload.source_channel_ids)))
        .scalars()
        .all()
    }
    targets = {
        t.id: t
        for t in db.execute(select(TargetChannel).where(TargetChannel.id.in_(payload.target_channel_ids)))
        .scalars()
        .all()
    }
    if not sources or not targets:
        raise ResourceNotFoundError("Valid source and target channels are required.")

    created_ids: list[int] = []
    for sid in payload.source_channel_ids:
        src = sources.get(sid)
        if not src:
            continue
        for tid in payload.target_channel_ids:
            tgt = targets.get(tid)
            if not tgt:
                continue
            existing = db.execute(
                select(PublishingRoute).where(
                    PublishingRoute.source_channel_id == sid,
                    PublishingRoute.target_channel_id == tid,
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue

            route = PublishingRoute(
                name=f"{payload.name_prefix}: {src.title} → {tgt.title}"[:200],
                source_channel_id=sid,
                target_channel_id=tid,
                is_enabled=payload.is_enabled,
                priority=100,
            )
            db.add(route)
            db.flush()
            rf = RouteFilter(route_id=route.id)
            RouteRepository.apply_filter_payload(rf, payload.filters)
            db.add(rf)
            created_ids.append(route.id)

    AuditRepository.record(
        db,
        level="INFO",
        category="ROUTE",
        action="ROUTES_BULK_CREATED",
        actor_user_id=user.id,
        actor_username=user.username,
        message=f"Bulk-created {len(created_ids)} publishing route(s).",
    )
    db.commit()
    return [RouteRepository.to_read(_load_route_or_404(db, rid)) for rid in created_ids]


@router.patch("/{route_id}", response_model=PublishingRouteRead)
def update_route(
    route_id: int,
    payload: PublishingRouteUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PublishingRouteRead:
    route = _load_route_or_404(db, route_id)
    if payload.name is not None:
        route.name = payload.name.strip()
    if payload.description is not None:
        route.description = payload.description
    if payload.is_enabled is not None:
        route.is_enabled = payload.is_enabled
    if payload.priority is not None:
        route.priority = payload.priority
    if payload.filters is not None:
        if route.route_filter is None:
            route.route_filter = RouteFilter(route_id=route.id)
            db.add(route.route_filter)
        RouteRepository.apply_filter_payload(route.route_filter, payload.filters)

    AuditRepository.record(
        db,
        level="INFO",
        category="ROUTE",
        action="ROUTE_UPDATED",
        actor_user_id=user.id,
        actor_username=user.username,
        entity_type="publishing_route",
        entity_id=route.id,
        message=f"Updated publishing route '{route.name}' (enabled={route.is_enabled}).",
    )
    db.commit()
    return RouteRepository.to_read(_load_route_or_404(db, route_id))


@router.post("/{route_id}/toggle", response_model=PublishingRouteRead)
def toggle_route(
    route_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PublishingRouteRead:
    route = _load_route_or_404(db, route_id)
    route.is_enabled = not route.is_enabled
    AuditRepository.record(
        db,
        level="INFO",
        category="ROUTE",
        action="ROUTE_TOGGLED",
        actor_user_id=user.id,
        actor_username=user.username,
        entity_type="publishing_route",
        entity_id=route.id,
        message=f"{'Enabled' if route.is_enabled else 'Disabled'} route '{route.name}' independently.",
    )
    db.commit()
    return RouteRepository.to_read(_load_route_or_404(db, route_id))


@router.delete("/{route_id}", status_code=204)
def delete_route(
    route_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    route = _load_route_or_404(db, route_id)
    name = route.name
    db.delete(route)
    AuditRepository.record(
        db,
        level="INFO",
        category="ROUTE",
        action="ROUTE_DELETED",
        actor_user_id=user.id,
        actor_username=user.username,
        entity_type="publishing_route",
        entity_id=route_id,
        message=f"Deleted publishing route '{name}'.",
    )
    db.commit()

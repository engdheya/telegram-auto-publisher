"""Primary API v1 router aggregating all domain endpoints."""

from fastapi import APIRouter

from app.api.endpoints import (
    auth,
    dashboard,
    logs,
    messages,
    queue,
    routes,
    settings,
    sources,
    targets,
    telegram,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(dashboard.router)
api_router.include_router(telegram.router)
api_router.include_router(sources.router)
api_router.include_router(targets.router)
api_router.include_router(routes.router)
api_router.include_router(messages.router)
api_router.include_router(queue.router)
api_router.include_router(logs.router)
api_router.include_router(settings.router)

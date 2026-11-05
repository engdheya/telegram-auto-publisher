"""FastAPI application entry point with OpenAPI/Swagger documentation, security headers, and exception handling."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.database.init_db import init_database
from app.database.integrity import validate_database_integrity
from app.database import session as db_session


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_database()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.APP_NAME,
        version=__version__,
        description=(
            "Production-ready automated Telegram multi-source to multi-target channel publishing platform "
            "with persistent SQLite WAL queue, grouped album aggregation, route filters, and UNKNOWN state reconciliation."
        ),
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "code": exc.code},
        )

    @app.get("/api/v1/health", tags=["Health"])
    def health_check():
        with db_session.SessionLocal() as db:
            integrity = validate_database_integrity(db)
        return {
            "status": "ok" if integrity["healthy"] else "degraded",
            "version": __version__,
            "database": integrity,
        }

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    return app


app = create_app()

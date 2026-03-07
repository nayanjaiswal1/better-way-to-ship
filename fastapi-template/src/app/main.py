"""Application factory — creates and configures the FastAPI instance."""
from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.v1 import router as v1_router
from app.core.config import get_settings
from app.core.exceptions import AppError, app_error_handler
from app.core.logging import configure_logging
from app.db.base import get_engine

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup and shutdown events."""
    settings = get_settings()
    configure_logging(json_logs=settings.LOG_JSON, log_level=settings.LOG_LEVEL)
    logger.info("Starting up", env=settings.APP_ENV, version=settings.APP_VERSION)

    # Verify DB connectivity on startup
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncConnection

    engine = get_engine()
    async with engine.connect() as conn:  # type: ignore[union-attr]
        await conn.execute(text("SELECT 1"))
    logger.info("Database connection verified")

    yield

    # Graceful shutdown
    logger.info("Shutting down")
    await engine.dispose()  # type: ignore[union-attr]


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url="/api/redoc" if not settings.is_production else None,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ---------------------------------------------------------------------------
    # Middleware (order matters — added in reverse call order)
    # ---------------------------------------------------------------------------
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(o) for o in settings.CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---------------------------------------------------------------------------
    # Exception handlers
    # ---------------------------------------------------------------------------
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]

    # ---------------------------------------------------------------------------
    # Routers
    # ---------------------------------------------------------------------------
    app.include_router(v1_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()

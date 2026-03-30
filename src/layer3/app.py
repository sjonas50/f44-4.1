"""Layer 3 FastAPI application — Provenance."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from src.layer3.pipeline.router import router as anchor_router
from src.layer3.sdk.router import router as sessions_router
from src.layer3.sdk.service import SessionService
from src.shared.config.settings import Settings
from src.shared.middleware.error_handling import register_exception_handlers
from src.shared.middleware.logging import LoggingMiddleware
from src.shared.redis_client.client import close_redis, init_redis

logger = structlog.get_logger()

# Module-level singleton — initialized in lifespan, accessed by router
_session_service: SessionService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan: initialize Redis and SessionService."""
    global _session_service

    settings = Settings()
    redis_client = None

    try:
        redis_client = await init_redis(settings)
        logger.info("layer3_redis_connected")
    except Exception:
        logger.warning("layer3_redis_unavailable", detail="Running without Redis — feedback pipeline disabled")

    _session_service = SessionService(
        redis_client=redis_client,
        settings=settings,
    )
    logger.info("layer3_started", session_service="initialized")

    yield

    _session_service = None
    await close_redis()
    logger.info("layer3_stopped")


app = FastAPI(
    title="Sovereign Agent — Layer 3: Provenance",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(LoggingMiddleware)
register_exception_handlers(app)

app.include_router(sessions_router)
app.include_router(anchor_router)


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    redis_ok = False

    try:
        from src.shared.redis_client.client import get_redis_client

        client = get_redis_client()
        await client.ping()
        redis_ok = True
    except Exception:
        pass

    return {
        "status": "healthy" if redis_ok else "degraded",
        "service": "layer3",
        "redis_connected": redis_ok,
        "db_connected": False,
        "active_sessions": _session_service.active_count if _session_service else 0,
    }

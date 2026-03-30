"""Layer 3 FastAPI application — Provenance."""

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from src.layer3.pipeline.router import router as anchor_router
from src.layer3.pipeline.scheduler import run_anchor_scheduler
from src.layer3.sdk.router import router as sessions_router
from src.layer3.sdk.service import SessionService
from src.shared.config.settings import Settings
from src.shared.middleware.error_handling import register_exception_handlers
from src.shared.middleware.logging import LoggingMiddleware
from src.shared.redis_client.client import close_redis, init_redis

logger = structlog.get_logger()

# Module-level singletons — initialized in lifespan, accessed by router
_session_service: SessionService | None = None
_anchor_scheduler_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan: initialize Redis, SessionService, and anchor scheduler."""
    global _session_service, _anchor_scheduler_task

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

    # Start the periodic anchor scheduler as a background task
    if redis_client and settings.ANCHOR_CONTRACT_ADDRESS and settings.DEPLOYER_PRIVATE_KEY:
        _anchor_scheduler_task = asyncio.create_task(run_anchor_scheduler(redis_client, settings))
        logger.info("anchor_scheduler_launched", interval=settings.ANCHOR_INTERVAL_SECONDS)
    else:
        logger.warning("anchor_scheduler_not_started", detail="Missing ANCHOR_CONTRACT_ADDRESS or DEPLOYER_PRIVATE_KEY")

    logger.info("layer3_started", session_service="initialized")

    yield

    # Shutdown
    if _anchor_scheduler_task and not _anchor_scheduler_task.done():
        _anchor_scheduler_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _anchor_scheduler_task

    _session_service = None
    _anchor_scheduler_task = None
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
        "anchor_scheduler_running": _anchor_scheduler_task is not None and not _anchor_scheduler_task.done()
        if _anchor_scheduler_task
        else False,
    }

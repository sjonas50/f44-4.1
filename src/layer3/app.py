"""Layer 3 FastAPI application — Provenance."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from src.layer3.pipeline.router import router as anchor_router
from src.layer3.sdk.router import router as sessions_router
from src.shared.middleware.error_handling import register_exception_handlers
from src.shared.middleware.logging import LoggingMiddleware

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan: initialize and cleanup resources."""
    logger.info("layer3_starting")
    yield
    logger.info("layer3_stopping")


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
    }

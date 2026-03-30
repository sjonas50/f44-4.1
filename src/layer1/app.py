"""Layer 1 FastAPI application — Trust & Identity."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from src.layer1.behavioral.router import router as behavioral_router
from src.layer1.circuit_breaker.router import router as circuit_breaker_router
from src.layer1.kya.router import router as kya_router
from src.layer1.trust.router import router as trust_router
from src.shared.middleware.error_handling import register_exception_handlers
from src.shared.middleware.logging import LoggingMiddleware

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan: initialize and cleanup resources."""
    logger.info("layer1_starting")
    yield
    logger.info("layer1_stopping")


app = FastAPI(
    title="Sovereign Agent — Layer 1: Trust & Identity",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(LoggingMiddleware)
register_exception_handlers(app)

app.include_router(kya_router)
app.include_router(trust_router)
app.include_router(behavioral_router)
app.include_router(circuit_breaker_router)


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    redis_ok = False
    db_ok = False

    try:
        from src.shared.redis_client.client import get_redis_client

        client = get_redis_client()
        await client.ping()
        redis_ok = True
    except Exception:
        pass

    return {
        "status": "healthy" if redis_ok else "degraded",
        "service": "layer1",
        "redis_connected": redis_ok,
        "db_connected": db_ok,
    }

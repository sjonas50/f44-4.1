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
    # Redis and DB pool initialization would go here in production
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
    return {"status": "healthy", "service": "layer1"}

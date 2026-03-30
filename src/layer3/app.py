"""Layer 3 FastAPI application — Provenance."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

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


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "healthy", "service": "layer3"}

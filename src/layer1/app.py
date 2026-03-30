"""Layer 1 FastAPI application — Trust & Identity."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from src.layer1.behavioral.router import router as behavioral_router
from src.layer1.behavioral.service import BehavioralService
from src.layer1.circuit_breaker.router import router as circuit_breaker_router
from src.layer1.circuit_breaker.service import CircuitBreakerService
from src.layer1.kya.router import router as kya_router
from src.layer1.kya.service import KYAService
from src.layer1.trust.router import router as trust_router
from src.layer1.trust.service import TrustService
from src.shared.config.settings import Settings
from src.shared.middleware.error_handling import register_exception_handlers
from src.shared.middleware.logging import LoggingMiddleware
from src.shared.redis_client.client import close_redis, init_redis

logger = structlog.get_logger()

# Module-level singletons — initialized in lifespan, accessed by routers
_kya_service: KYAService | None = None
_trust_service: TrustService | None = None
_behavioral_service: BehavioralService | None = None
_circuit_breaker_service: CircuitBreakerService | None = None
_db_pool = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan: initialize Redis, DB pool, and all services."""
    global _kya_service, _trust_service, _behavioral_service, _circuit_breaker_service, _db_pool

    settings = Settings()
    redis_client = None

    # Initialize Redis
    try:
        redis_client = await init_redis(settings)
        logger.info("layer1_redis_connected")
    except Exception:
        logger.warning("layer1_redis_unavailable")

    # Initialize DB pool
    try:
        import asyncpg

        _db_pool = await asyncpg.create_pool(
            settings.DATABASE_URL,
            min_size=2,
            max_size=10,
        )
        logger.info("layer1_db_connected")
    except Exception:
        logger.warning("layer1_db_unavailable", detail="Running without DB — KYA write operations will fail")

    # Initialize services
    _trust_service = TrustService(redis_client) if redis_client else None
    _behavioral_service = BehavioralService(redis_client) if redis_client else None
    _circuit_breaker_service = CircuitBreakerService(redis_client) if redis_client else None
    # KYA needs both DB and Redis — created per-request with a connection from the pool

    logger.info("layer1_started")
    yield

    # Shutdown
    _kya_service = None
    _trust_service = None
    _behavioral_service = None
    _circuit_breaker_service = None
    if _db_pool:
        await _db_pool.close()
    await close_redis()
    logger.info("layer1_stopped")


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

    db_ok = _db_pool is not None and not _db_pool._closed

    return {
        "status": "healthy" if (redis_ok and db_ok) else "degraded",
        "service": "layer1",
        "redis_connected": redis_ok,
        "db_connected": db_ok,
    }

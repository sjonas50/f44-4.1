from unittest.mock import AsyncMock

import pytest

from src.shared.config.settings import Settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Test settings with safe defaults."""
    return Settings(
        DATABASE_URL="postgresql://test:test@localhost:5432/test_db",
        REDIS_URL="redis://localhost:6379/1",
        ENVIRONMENT="test",
    )


@pytest.fixture
def redis_client() -> AsyncMock:
    """Mock async Redis client for unit tests."""
    return AsyncMock()


@pytest.fixture
def db_pool() -> AsyncMock:
    """Mock asyncpg connection pool for unit tests."""
    return AsyncMock()

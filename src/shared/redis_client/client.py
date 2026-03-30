import redis.asyncio as aioredis

from src.shared.config.settings import Settings

_client: aioredis.Redis | None = None


async def init_redis(settings: Settings) -> aioredis.Redis:
    """Initialize the async Redis client singleton.

    Args:
        settings: Application settings with REDIS_URL.

    Returns:
        Connected async Redis client.
    """
    global _client
    _client = aioredis.from_url(
        settings.REDIS_URL,
        max_connections=50,
        decode_responses=True,
    )
    return _client


async def close_redis() -> None:
    """Close the Redis client connection."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_redis_client() -> aioredis.Redis:
    """Get the singleton Redis client.

    Returns:
        The initialized async Redis client.

    Raises:
        RuntimeError: If init_redis() hasn't been called.
    """
    if _client is None:
        raise RuntimeError("Redis client not initialized. Call init_redis() first.")
    return _client

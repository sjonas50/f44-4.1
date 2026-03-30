"""Tests for CircuitBreaker service."""

from uuid import uuid4

import pytest


class TestCircuitBreakerService:
    @pytest.fixture
    def redis_client(self):
        import fakeredis.aioredis

        return fakeredis.aioredis.FakeRedis(decode_responses=True)

    @pytest.fixture
    def service(self, redis_client):
        from src.layer1.circuit_breaker.service import CircuitBreakerService

        return CircuitBreakerService(redis_client)

    @pytest.mark.asyncio
    async def test_activate(self, service, redis_client) -> None:
        await service.activate(reason="security incident")
        assert service.is_active
        assert await redis_client.get("circuit_breaker:active") == "1"

    @pytest.mark.asyncio
    async def test_deactivate(self, service, redis_client) -> None:
        await service.activate()
        await service.deactivate()
        assert not service.is_active
        assert await redis_client.get("circuit_breaker:active") is None

    @pytest.mark.asyncio
    async def test_bulk_revoke_publishes_events(self, service, redis_client) -> None:
        agent_ids = [uuid4() for _ in range(3)]
        count = await service.bulk_revoke(
            scope_type="trust_tier",
            scope_value="0",
            agent_ids=agent_ids,
            reason="compromised class",
        )
        assert count == 3

        # Verify events were published to the stream
        stream_info = await redis_client.xlen("stream:vc_revoke")
        # 1 CircuitBreakerActivated event + 3 individual revocation events
        assert stream_info == 4

    @pytest.mark.asyncio
    async def test_bulk_revoke_empty_list(self, service) -> None:
        count = await service.bulk_revoke(
            scope_type="agent_class",
            scope_value="test",
            agent_ids=[],
            reason="test",
        )
        assert count == 0

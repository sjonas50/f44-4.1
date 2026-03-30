"""Tests for trust tier system."""

from uuid import uuid4

import pytest

from src.layer1.trust.tier import TIER_DEFINITIONS, get_tier_weight


class TestTierDefinitions:
    def test_all_tiers_defined(self) -> None:
        assert set(TIER_DEFINITIONS.keys()) == {0, 1, 2, 3}

    def test_tier_0_highest_risk(self) -> None:
        assert get_tier_weight(0) == 1.5

    def test_tier_3_lowest_risk(self) -> None:
        assert get_tier_weight(3) == 0.6

    def test_tiers_decrease_monotonically(self) -> None:
        weights = [get_tier_weight(i) for i in range(4)]
        for i in range(len(weights) - 1):
            assert weights[i] > weights[i + 1], f"Tier {i} weight should be > tier {i + 1}"

    def test_invalid_tier_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid trust tier"):
            get_tier_weight(4)
        with pytest.raises(ValueError, match="Invalid trust tier"):
            get_tier_weight(-1)


class TestTrustService:
    """Test TrustService with fakeredis."""

    @pytest.fixture
    def redis_client(self):
        import fakeredis.aioredis

        return fakeredis.aioredis.FakeRedis(decode_responses=True)

    @pytest.fixture
    def service(self, redis_client):
        from src.layer1.trust.service import TrustService

        return TrustService(redis_client)

    @pytest.mark.asyncio
    async def test_get_tier_weight_cache_miss(self, service) -> None:
        agent_id = uuid4()
        weight = await service.get_tier_weight_cached(agent_id, fallback_tier=0)
        assert weight == 1.5

    @pytest.mark.asyncio
    async def test_get_tier_weight_cache_hit(self, service, redis_client) -> None:
        agent_id = uuid4()
        await redis_client.set(f"trust:tier:{agent_id}", "2", ex=300)
        weight = await service.get_tier_weight_cached(agent_id)
        assert weight == 0.9

    @pytest.mark.asyncio
    async def test_set_tier(self, service, redis_client) -> None:
        agent_id = uuid4()
        await service.set_tier(agent_id, 2)
        cached = await redis_client.get(f"trust:tier:{agent_id}")
        assert cached == "2"

    @pytest.mark.asyncio
    async def test_promote_tier(self, service) -> None:
        agent_id = uuid4()
        new_tier = await service.promote_tier(agent_id, current_tier=1, reason="good behavior")
        assert new_tier == 2
        weight = await service.get_tier_weight_cached(agent_id)
        assert weight == 0.9

    @pytest.mark.asyncio
    async def test_promote_at_max_raises(self, service) -> None:
        agent_id = uuid4()
        with pytest.raises(ValueError, match="maximum tier"):
            await service.promote_tier(agent_id, current_tier=3)

    @pytest.mark.asyncio
    async def test_demote_tier(self, service) -> None:
        agent_id = uuid4()
        new_tier = await service.demote_tier(agent_id, current_tier=2, reason="anomaly detected")
        assert new_tier == 1
        weight = await service.get_tier_weight_cached(agent_id)
        assert weight == 1.2

    @pytest.mark.asyncio
    async def test_demote_at_min_raises(self, service) -> None:
        agent_id = uuid4()
        with pytest.raises(ValueError, match="minimum tier"):
            await service.demote_tier(agent_id, current_tier=0)

    @pytest.mark.asyncio
    async def test_get_tier_info(self, service) -> None:
        agent_id = uuid4()
        await service.set_tier(agent_id, 3)
        info = await service.get_tier_info(agent_id)
        assert info["tier"] == 3
        assert info["weight_modifier"] == 0.6
        assert info["name"] == "Established"

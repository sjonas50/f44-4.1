"""Trust tier service with Redis caching.

Tier lookups are Redis-cached for sub-millisecond reads by the CPE risk scorer.
"""

from uuid import UUID

import redis.asyncio as aioredis
import structlog

from src.layer1.trust.tier import TIER_DEFINITIONS, get_tier_weight
from src.shared.models.events import TrustTierChanged
from src.shared.redis_client.streams import xadd

logger = structlog.get_logger()

TIER_CACHE_PREFIX = "trust:tier:"
TIER_CACHE_TTL = 300  # 5 minutes
TRUST_TIER_STREAM = "stream:trust_tier_change"


class TrustService:
    """Manages trust tier lookups, promotions, and demotions."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def get_tier_weight_cached(self, agent_id: UUID, fallback_tier: int = 0) -> float:
        """Get tier weight from Redis cache, falling back to provided tier.

        Args:
            agent_id: Agent UUID.
            fallback_tier: Tier to use if cache misses.

        Returns:
            Risk weight modifier.
        """
        cache_key = f"{TIER_CACHE_PREFIX}{agent_id}"
        cached = await self._redis.get(cache_key)
        if cached is not None:
            tier = int(cached)
            return get_tier_weight(tier)
        return get_tier_weight(fallback_tier)

    async def set_tier(self, agent_id: UUID, tier: int) -> None:
        """Set an agent's trust tier in the cache.

        Args:
            agent_id: Agent UUID.
            tier: Trust tier (0-3).
        """
        if tier not in TIER_DEFINITIONS:
            raise ValueError(f"Invalid trust tier: {tier}")
        cache_key = f"{TIER_CACHE_PREFIX}{agent_id}"
        await self._redis.set(cache_key, str(tier), ex=TIER_CACHE_TTL)

    async def promote_tier(self, agent_id: UUID, current_tier: int, reason: str = "") -> int:
        """Promote an agent's trust tier by one level.

        Args:
            agent_id: Agent UUID.
            current_tier: Current tier level.
            reason: Reason for promotion.

        Returns:
            New tier level.

        Raises:
            ValueError: If already at max tier.
        """
        if current_tier >= 3:
            raise ValueError(f"Agent {agent_id} already at maximum tier 3")

        new_tier = current_tier + 1
        await self.set_tier(agent_id, new_tier)

        event = TrustTierChanged(
            agent_id=agent_id,
            old_tier=current_tier,
            new_tier=new_tier,
            reason=reason,
        )
        await xadd(self._redis, TRUST_TIER_STREAM, event.model_dump(mode="json"))

        logger.info("trust_tier_promoted", agent_id=str(agent_id), old=current_tier, new=new_tier)
        return new_tier

    async def demote_tier(self, agent_id: UUID, current_tier: int, reason: str = "") -> int:
        """Demote an agent's trust tier by one level.

        Args:
            agent_id: Agent UUID.
            current_tier: Current tier level.
            reason: Reason for demotion.

        Returns:
            New tier level.

        Raises:
            ValueError: If already at min tier.
        """
        if current_tier <= 0:
            raise ValueError(f"Agent {agent_id} already at minimum tier 0")

        new_tier = current_tier - 1
        await self.set_tier(agent_id, new_tier)

        event = TrustTierChanged(
            agent_id=agent_id,
            old_tier=current_tier,
            new_tier=new_tier,
            reason=reason,
        )
        await xadd(self._redis, TRUST_TIER_STREAM, event.model_dump(mode="json"))

        logger.info("trust_tier_demoted", agent_id=str(agent_id), old=current_tier, new=new_tier)
        return new_tier

    async def get_tier_info(self, agent_id: UUID, fallback_tier: int = 0) -> dict:
        """Get full tier information for an agent.

        Args:
            agent_id: Agent UUID.
            fallback_tier: Tier to use if cache misses.

        Returns:
            Dict with tier, weight_modifier, and tier name.
        """
        cache_key = f"{TIER_CACHE_PREFIX}{agent_id}"
        cached = await self._redis.get(cache_key)
        tier = int(cached) if cached is not None else fallback_tier
        defn = TIER_DEFINITIONS[tier]
        return {
            "tier": tier,
            "weight_modifier": defn.weight_modifier,
            "name": defn.name,
        }

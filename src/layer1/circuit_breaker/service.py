"""CircuitBreaker service for bulk agent revocation.

Uses Redis Streams (not Pub/Sub) for durable event delivery — a missed
revocation event is a security incident.
"""

from typing import Literal
from uuid import UUID

import redis.asyncio as aioredis
import structlog

from src.shared.models.events import CircuitBreakerActivated
from src.shared.redis_client.streams import xadd

logger = structlog.get_logger()

VC_REVOKE_STREAM = "stream:vc_revoke"


class CircuitBreakerService:
    """Emergency bulk revocation controls."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

    async def activate(self, reason: str = "") -> None:
        """Activate platform-wide circuit breaker.

        Args:
            reason: Reason for activation.
        """
        self._active = True
        await self._redis.set("circuit_breaker:active", "1")
        logger.warning("circuit_breaker_activated", reason=reason)

    async def deactivate(self) -> None:
        """Deactivate the circuit breaker."""
        self._active = False
        await self._redis.delete("circuit_breaker:active")
        logger.info("circuit_breaker_deactivated")

    async def bulk_revoke(
        self,
        scope_type: Literal["agent_class", "trust_tier", "human_authorizer"],
        scope_value: str,
        agent_ids: list[UUID],
        reason: str = "",
    ) -> int:
        """Revoke credentials for a set of agents matching scope criteria.

        The caller is responsible for querying matching agents (via KYA repository)
        and passing their IDs. This service publishes the revocation event to
        the durable Redis Stream that ASOR's VC revocation system consumes.

        Args:
            scope_type: Type of scope filter used.
            scope_value: Value of the scope filter.
            agent_ids: List of agent UUIDs to revoke.
            reason: Reason for bulk revocation.

        Returns:
            Number of agents in the revocation batch.
        """
        event = CircuitBreakerActivated(
            agent_id=agent_ids[0] if agent_ids else UUID(int=0),
            scope_type=scope_type,
            scope_value=scope_value,
            affected_agent_count=len(agent_ids),
            reason=reason,
        )
        await xadd(self._redis, VC_REVOKE_STREAM, event.model_dump(mode="json"))

        # Publish individual revocation messages for each agent
        for aid in agent_ids:
            await xadd(
                self._redis,
                VC_REVOKE_STREAM,
                {"action": "revoke", "agent_id": str(aid), "scope_type": scope_type, "reason": reason},
            )

        logger.warning(
            "bulk_revocation",
            scope_type=scope_type,
            scope_value=scope_value,
            count=len(agent_ids),
            reason=reason,
        )
        return len(agent_ids)

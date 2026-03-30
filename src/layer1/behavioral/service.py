"""Behavioral analysis service (read-only, CPE-facing).

Returns pre-computed anomaly scores from Redis cache. Never computes
on the fly — the consumer worker handles all computation.
"""

import json
from datetime import UTC, datetime
from uuid import UUID

import redis.asyncio as aioredis
import structlog
from pydantic import BaseModel

from src.layer1.behavioral.scoring import cold_start_score

logger = structlog.get_logger()

SCORE_PREFIX = "behavioral:score:"
BASELINE_PREFIX = "behavioral:baseline:"


class AnomalyScoreResponse(BaseModel):
    """Response model for anomaly score queries."""

    anomaly_score: float
    factors: list[str]
    computed_at: datetime


class BehavioralService:
    """Read-only service for CPE risk scorer integration."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def get_anomaly_score(self, agent_id: UUID) -> AnomalyScoreResponse:
        """Get pre-computed anomaly score for an agent.

        Must return within 1ms from Redis. Never computes on the fly.

        Args:
            agent_id: Agent UUID.

        Returns:
            AnomalyScoreResponse with score, factors, and timestamp.
        """
        score_key = f"{SCORE_PREFIX}{agent_id}"
        cached = await self._redis.get(score_key)

        if cached is None:
            return AnomalyScoreResponse(
                anomaly_score=cold_start_score(),
                factors=["cold_start"],
                computed_at=datetime.now(UTC),
            )

        data = json.loads(cached)
        return AnomalyScoreResponse(
            anomaly_score=data["anomaly_score"],
            factors=data.get("factors", []),
            computed_at=datetime.now(UTC),
        )

    async def get_baseline(self, agent_id: UUID) -> dict | None:
        """Get full baseline stats for debugging.

        Args:
            agent_id: Agent UUID.

        Returns:
            Baseline dict or None if no data.
        """
        baseline_key = f"{BASELINE_PREFIX}{agent_id}"
        cached = await self._redis.get(baseline_key)
        if cached is None:
            return None
        return json.loads(cached)

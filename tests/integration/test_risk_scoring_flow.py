"""Integration test: risk scoring flow.

Register agent → push behavioral sessions → consumer processes → verify
anomaly score and trust tier are independently queryable.
"""

import json
from uuid import uuid4

import pytest

from src.layer1.behavioral.consumer import process_session_events
from src.layer1.behavioral.service import BehavioralService
from src.layer1.trust.service import TrustService


class TestRiskScoringFlow:
    @pytest.fixture
    def redis_client(self):
        import fakeredis.aioredis

        return fakeredis.aioredis.FakeRedis(decode_responses=True)

    @pytest.mark.asyncio
    async def test_both_risk_factors_queryable(self, redis_client) -> None:
        """After behavioral sessions, both trust tier and anomaly score are available."""
        agent_id = uuid4()

        # Set trust tier (simulating KYA registration)
        trust_svc = TrustService(redis_client)
        await trust_svc.set_tier(agent_id, 1)

        # Push 6 behavioral sessions with varying metrics
        for i in range(6):
            await redis_client.xadd(
                "stream:behavioral_session",
                {
                    "payload": json.dumps(
                        {
                            "agent_id": str(agent_id),
                            "metrics": {
                                "dead_end_count": 2 + i,
                                "tool_invocations": 4 + i,
                                "cost_usd": 0.03 + (i * 0.01),
                                "duration_ms": 10000 + (i * 1000),
                            },
                        }
                    )
                },
            )

        # Consumer processes all events
        processed = await process_session_events(redis_client)
        assert processed == 6

        # Verify trust tier is queryable
        tier_weight = await trust_svc.get_tier_weight_cached(agent_id)
        assert tier_weight == 1.2  # Tier 1

        # Verify anomaly score is queryable and not cold-start
        beh_svc = BehavioralService(redis_client)
        score_result = await beh_svc.get_anomaly_score(agent_id)
        assert score_result.anomaly_score is not None
        assert 0.0 <= score_result.anomaly_score <= 1.0
        assert "cold_start" not in score_result.factors

    @pytest.mark.asyncio
    async def test_cold_start_agent_gets_neutral_score(self, redis_client) -> None:
        """New agent with no sessions gets cold-start neutral score."""
        agent_id = uuid4()
        beh_svc = BehavioralService(redis_client)
        result = await beh_svc.get_anomaly_score(agent_id)
        assert result.anomaly_score == 0.5
        assert "cold_start" in result.factors

    @pytest.mark.asyncio
    async def test_tier_and_score_independent(self, redis_client) -> None:
        """Trust tier can be set independently of behavioral score."""
        agent_id = uuid4()

        trust_svc = TrustService(redis_client)
        await trust_svc.set_tier(agent_id, 3)

        beh_svc = BehavioralService(redis_client)
        tier_info = await trust_svc.get_tier_info(agent_id)
        score_result = await beh_svc.get_anomaly_score(agent_id)

        assert tier_info["tier"] == 3
        assert tier_info["weight_modifier"] == 0.6
        assert score_result.anomaly_score == 0.5  # Cold start — no sessions yet

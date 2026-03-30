"""Tests for Behavioral Analysis Engine."""

import json
from uuid import uuid4

import pytest

from src.layer1.behavioral.baselines import AgentBaseline, update_baseline
from src.layer1.behavioral.scoring import (
    COLD_START_SCORE,
    cold_start_score,
    compute_anomaly_score,
    compute_z_scores,
)


class TestBaselines:
    def test_first_session_initializes(self) -> None:
        metrics = {"dead_end_count": 3, "tool_invocations": 5, "cost_usd": 0.04, "duration_ms": 12000}
        baseline = update_baseline(None, metrics)
        assert baseline.total_sessions == 1
        assert baseline.metrics["dead_end_count"].mean == 3.0
        assert baseline.metrics["dead_end_count"].count == 1
        assert baseline.metrics["dead_end_count"].variance == 0.0

    def test_second_session_updates_ewma(self) -> None:
        metrics1 = {"dead_end_count": 2, "tool_invocations": 4, "cost_usd": 0.03, "duration_ms": 10000}
        metrics2 = {"dead_end_count": 6, "tool_invocations": 8, "cost_usd": 0.06, "duration_ms": 20000}

        b1 = update_baseline(None, metrics1)
        b2 = update_baseline(b1, metrics2)

        assert b2.total_sessions == 2
        # EWMA mean should be between first and second value, biased toward first (alpha ~0.095)
        assert b2.metrics["dead_end_count"].mean > 2.0
        assert b2.metrics["dead_end_count"].mean < 6.0

    def test_ten_sessions_converge(self) -> None:
        baseline = None
        for _ in range(10):
            metrics = {
                "dead_end_count": 3,
                "tool_invocations": 5,
                "cost_usd": 0.04,
                "duration_ms": 12000,
            }
            baseline = update_baseline(baseline, metrics)

        assert baseline is not None
        assert baseline.total_sessions == 10
        # With constant input, mean should converge to 3.0
        assert abs(baseline.metrics["dead_end_count"].mean - 3.0) < 0.5

    def test_tool_invocations_list(self) -> None:
        metrics = {
            "dead_end_count": 0,
            "tool_invocations": ["crm_lookup", "portfolio_query"],
            "cost_usd": 0,
            "duration_ms": 0,
        }
        baseline = update_baseline(None, metrics)
        assert baseline.metrics["tool_invocations"].mean == 2.0

    def test_missing_metrics_default_zero(self) -> None:
        baseline = update_baseline(None, {})
        assert baseline.metrics["dead_end_count"].mean == 0.0

    def test_immutability(self) -> None:
        metrics = {"dead_end_count": 3, "tool_invocations": 5, "cost_usd": 0.04, "duration_ms": 12000}
        b1 = update_baseline(None, metrics)
        b2 = update_baseline(b1, metrics)
        # b1 should not be mutated
        assert b1.total_sessions == 1
        assert b2.total_sessions == 2


class TestScoring:
    def test_cold_start_score(self) -> None:
        assert cold_start_score() == 0.5

    def test_z_scores_zero_for_new_agent(self) -> None:
        baseline = AgentBaseline()
        z = compute_z_scores(baseline, {"dead_end_count": 10})
        assert all(v == 0.0 for v in z.values())

    def test_z_scores_after_enough_sessions(self) -> None:
        import random

        random.seed(42)
        baseline = None
        # Use varied input so EWMA builds real variance
        for _ in range(20):
            baseline = update_baseline(baseline, {
                "dead_end_count": random.gauss(3, 1),
                "tool_invocations": max(0, random.gauss(5, 2)),
                "cost_usd": max(0, random.gauss(0.04, 0.01)),
                "duration_ms": max(0, random.gauss(12000, 3000)),
            })

        # Normal session — z-scores should be moderate
        z_normal = compute_z_scores(baseline, {
            "dead_end_count": 3,
            "tool_invocations": 5,
            "cost_usd": 0.04,
            "duration_ms": 12000,
        })
        for v in z_normal.values():
            assert abs(v) < 3.0, f"Expected moderate z-score for normal session, got {v}"

        # Highly anomalous session — at least one metric should flag
        z_anomalous = compute_z_scores(baseline, {
            "dead_end_count": 30,
            "tool_invocations": 50,
            "cost_usd": 0.40,
            "duration_ms": 120000,
        })
        assert any(abs(v) > 1.0 for v in z_anomalous.values())

    def test_anomaly_score_clamped(self) -> None:
        # Extreme z-scores
        z = {"a": 10.0, "b": 10.0, "c": 10.0}
        score = compute_anomaly_score(z)
        assert 0.0 <= score <= 1.0

    def test_anomaly_score_zero_for_normal(self) -> None:
        z = {"a": 0.0, "b": 0.0, "c": 0.0}
        score = compute_anomaly_score(z)
        assert score == 0.0

    def test_anomaly_score_empty_z_scores(self) -> None:
        score = compute_anomaly_score({})
        assert score == COLD_START_SCORE


class TestConsumer:
    @pytest.fixture
    def redis_client(self):
        import fakeredis.aioredis

        return fakeredis.aioredis.FakeRedis(decode_responses=True)

    @pytest.mark.asyncio
    async def test_process_updates_baseline_and_score(self, redis_client) -> None:
        from src.layer1.behavioral.consumer import process_session_events

        agent_id = str(uuid4())

        # Publish enough sessions to get past cold start
        for i in range(6):
            await redis_client.xadd(
                "stream:behavioral_session",
                {"payload": json.dumps({
                    "agent_id": agent_id,
                    "metrics": {
                        "dead_end_count": 3 + i,
                        "tool_invocations": 5,
                        "cost_usd": 0.04,
                        "duration_ms": 12000,
                    },
                })},
            )

        processed = await process_session_events(redis_client)
        assert processed == 6

        # Verify baseline was stored
        baseline_data = await redis_client.get(f"behavioral:baseline:{agent_id}")
        assert baseline_data is not None
        baseline = json.loads(baseline_data)
        assert baseline["total_sessions"] == 6

        # Verify score was cached
        score_data = await redis_client.get(f"behavioral:score:{agent_id}")
        assert score_data is not None
        score = json.loads(score_data)
        assert 0.0 <= score["anomaly_score"] <= 1.0


class TestBehavioralService:
    @pytest.fixture
    def redis_client(self):
        import fakeredis.aioredis

        return fakeredis.aioredis.FakeRedis(decode_responses=True)

    @pytest.fixture
    def service(self, redis_client):
        from src.layer1.behavioral.service import BehavioralService

        return BehavioralService(redis_client)

    @pytest.mark.asyncio
    async def test_cold_start_when_no_cache(self, service) -> None:
        result = await service.get_anomaly_score(uuid4())
        assert result.anomaly_score == 0.5
        assert "cold_start" in result.factors

    @pytest.mark.asyncio
    async def test_returns_cached_score(self, service, redis_client) -> None:
        agent_id = uuid4()
        await redis_client.set(
            f"behavioral:score:{agent_id}",
            json.dumps({"anomaly_score": 0.73, "factors": ["cost_usd:2.50"]}),
        )
        result = await service.get_anomaly_score(agent_id)
        assert result.anomaly_score == 0.73
        assert "cost_usd:2.50" in result.factors

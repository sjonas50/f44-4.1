"""Integration test: closed feedback loop (L3 → L1).

Session capture → feedback event → behavioral consumer → anomaly score updated.
"""

from uuid import uuid4

import pytest

from src.layer1.behavioral.consumer import process_session_events
from src.layer1.behavioral.service import BehavioralService
from src.layer3.feedback.emitter import emit_session_feedback
from src.layer3.sdk.session import SessionManager


class TestClosedLoop:
    @pytest.fixture
    def redis_client(self):
        import fakeredis.aioredis

        return fakeredis.aioredis.FakeRedis(decode_responses=True)

    @pytest.mark.asyncio
    async def test_session_to_anomaly_score(self, redis_client) -> None:
        """Full closed loop: session → feedback → consumer → score."""
        agent_id = uuid4()

        # L3: Run multiple sessions to build a baseline
        for i in range(6):
            sm = SessionManager(agent_id=agent_id, intent=f"Session {i}")
            sm.record_step("Analyzed data")
            sm.record_tool_invocation("crm_lookup", cost_usd=0.01)
            if i == 5:
                # Last session is anomalous
                for _ in range(10):
                    sm.record_dead_end("Unusual pattern")
                    sm.record_tool_invocation("sensitive_data_query", cost_usd=0.50)
            summary = sm.end_session()

            # L3 → L1: Emit feedback
            await emit_session_feedback(redis_client, sm.session_id, agent_id, summary, sm.capture)

        # L1: Consumer processes all events
        processed = await process_session_events(redis_client)
        assert processed == 6

        # L1: Check anomaly score is available
        service = BehavioralService(redis_client)
        result = await service.get_anomaly_score(agent_id)

        # Score should exist and not be cold-start
        assert result.anomaly_score is not None
        assert 0.0 <= result.anomaly_score <= 1.0

        # Baseline should be available
        baseline = await service.get_baseline(agent_id)
        assert baseline is not None
        assert baseline["total_sessions"] == 6

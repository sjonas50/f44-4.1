"""Integration test: closed feedback loop (L3 → L1).

Full pipeline: Session capture → artifacts stored → feedback emitted →
behavioral consumer processes → anomaly score updated in Redis.
"""

from uuid import uuid4

import pytest

from src.layer1.behavioral.consumer import process_session_events
from src.layer1.behavioral.service import BehavioralService
from src.layer3.sdk.service import SessionService
from src.shared.config.settings import Settings


class TestClosedLoop:
    @pytest.fixture
    def redis_client(self):
        import fakeredis.aioredis

        return fakeredis.aioredis.FakeRedis(decode_responses=True)

    @pytest.fixture
    def session_service(self, redis_client, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        settings = Settings(ENVIRONMENT="development")
        return SessionService(redis_client=redis_client, settings=settings)

    @pytest.mark.asyncio
    async def test_full_closed_loop(self, redis_client, session_service) -> None:
        """End-to-end: session → storage → feedback → consumer → anomaly score."""
        agent_id = uuid4()

        # Run 6 sessions through the wired SessionService
        for i in range(6):
            sm = session_service.start_session(agent_id, f"Session {i}")
            session_service.record_step(sm.session_id, "Analyzed data")
            session_service.record_tool_invocation(sm.session_id, "crm_lookup", cost_usd=0.01)
            if i == 5:
                # Last session is anomalous
                for _ in range(10):
                    session_service.record_dead_end(sm.session_id, "Unusual pattern")
                    session_service.record_tool_invocation(sm.session_id, "sensitive_query", cost_usd=0.50)

            summary = await session_service.end_session(sm.session_id)

            # Verify pipeline ran: artifacts stored, feedback emitted
            assert summary.storage_path, f"Session {i} should have storage path"
            assert summary.feedback_msg_id, f"Session {i} should have feedback msg id"
            assert summary.integrity_errors == [], f"Session {i} should have no integrity errors"

        # Verify all 6 feedback events are in the stream
        stream_len = await redis_client.xlen("stream:behavioral_session")
        assert stream_len == 6

        # L1: Consumer processes all events
        processed = await process_session_events(redis_client)
        assert processed == 6

        # L1: Check anomaly score is available and not cold-start
        beh_service = BehavioralService(redis_client)
        result = await beh_service.get_anomaly_score(agent_id)
        assert result.anomaly_score is not None
        assert 0.0 <= result.anomaly_score <= 1.0

        # Baseline should reflect all 6 sessions
        baseline = await beh_service.get_baseline(agent_id)
        assert baseline is not None
        assert baseline["total_sessions"] == 6

    @pytest.mark.asyncio
    async def test_session_artifacts_are_complete(self, session_service) -> None:
        """Verify 5W artifacts are written with correct structure."""
        import json
        from pathlib import Path

        agent_id = uuid4()
        sm = session_service.start_session(agent_id, "Completeness test")
        session_service.record_step(sm.session_id, "Step 1")
        session_service.record_tool_invocation(sm.session_id, "tool1", inputs={"data_source": "crm"}, cost_usd=0.01)
        session_service.record_decision(sm.session_id, "Decision 1", rationale="Because")
        session_service.record_dead_end(sm.session_id, "Hit a wall")

        summary = await session_service.end_session(sm.session_id)
        session_dir = Path(summary.storage_path)

        # All 5 artifacts present
        assert (session_dir / "manifest.json").exists()
        assert (session_dir / "intent.md").exists()
        assert (session_dir / "transcript.jsonl").exists()
        assert (session_dir / "operations.json").exists()
        assert (session_dir / "lineage.json").exists()

        # Manifest integrity
        manifest = json.loads((session_dir / "manifest.json").read_text())
        assert manifest["schema_version"] == "1.0"
        assert manifest["record_count"] == 4
        assert manifest["tool_invocation_count"] == 1
        assert manifest["dead_end_count"] == 1
        assert manifest["manifest_integrity_hash"]
        assert len(manifest["content_hashes"]) == 4

        # Transcript has all records in order
        lines = (session_dir / "transcript.jsonl").read_text().strip().split("\n")
        records = [json.loads(line) for line in lines]
        assert len(records) == 4
        assert records[0]["type"] == "step"
        assert records[1]["type"] == "tool_invocation"
        assert records[2]["type"] == "decision"
        assert records[3]["type"] == "dead_end"

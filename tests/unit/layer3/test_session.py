"""Tests for session manager — standalone and wired modes."""

from uuid import uuid4

import pytest


class TestSessionManagerStandalone:
    """Tests for standalone mode (no Redis/settings)."""

    @pytest.mark.asyncio
    async def test_start_and_end(self) -> None:
        from src.layer3.sdk.session import SessionManager

        sm = SessionManager(agent_id=uuid4(), intent="Test intent")
        sm.record_step("step 1")
        sm.record_tool_invocation("tool1", cost_usd=0.01)

        summary = await sm.end_session()
        assert summary.session_id == sm.session_id
        assert summary.artifact_count == 2
        assert summary.session_hash
        assert len(summary.session_hash) == 64
        assert summary.cost_usd == 0.01
        assert summary.tool_invocation_count == 1
        # Standalone: no storage, no batch, no feedback
        assert summary.storage_path == ""
        assert summary.batch_record_id == ""
        assert summary.feedback_msg_id == ""

    @pytest.mark.asyncio
    async def test_session_hash_deterministic(self) -> None:
        from src.layer3.sdk.session import SessionManager

        agent_id = uuid4()
        sm1 = SessionManager(agent_id=agent_id, intent="test")
        sm1.record_step("step 1")
        sm1.record_step("step 2")

        sm2 = SessionManager(agent_id=agent_id, intent="test")
        sm2.record_step("step 1")
        sm2.record_step("step 2")

        s1 = await sm1.end_session()
        s2 = await sm2.end_session()
        assert s1.session_hash == s2.session_hash

    @pytest.mark.asyncio
    async def test_cannot_record_after_end(self) -> None:
        from src.layer3.sdk.session import SessionManager

        sm = SessionManager(agent_id=uuid4(), intent="test")
        await sm.end_session()
        with pytest.raises(RuntimeError, match="already ended"):
            sm.record_step("too late")

    @pytest.mark.asyncio
    async def test_cannot_end_twice(self) -> None:
        from src.layer3.sdk.session import SessionManager

        sm = SessionManager(agent_id=uuid4(), intent="test")
        await sm.end_session()
        with pytest.raises(RuntimeError, match="already ended"):
            await sm.end_session()

    @pytest.mark.asyncio
    async def test_empty_session_gets_hash(self) -> None:
        from src.layer3.sdk.session import SessionManager

        sm = SessionManager(agent_id=uuid4(), intent="test")
        summary = await sm.end_session()
        assert summary.artifact_count == 0
        # Empty sessions now get a deterministic hash (not empty string)
        assert summary.session_hash
        assert len(summary.session_hash) == 64

    @pytest.mark.asyncio
    async def test_dead_end_tracking(self) -> None:
        from src.layer3.sdk.session import SessionManager

        sm = SessionManager(agent_id=uuid4(), intent="test")
        sm.record_dead_end("API timeout")
        sm.record_dead_end("Rate limited")
        summary = await sm.end_session()
        assert summary.dead_end_count == 2

    @pytest.mark.asyncio
    async def test_integrity_verification(self) -> None:
        from src.layer3.sdk.session import SessionManager

        sm = SessionManager(agent_id=uuid4(), intent="test")
        sm.record_step("step 1")
        sm.record_tool_invocation("tool1")
        summary = await sm.end_session()
        assert summary.integrity_errors == []


class TestSessionManagerWired:
    """Tests for wired mode (with Redis and settings)."""

    @pytest.fixture
    def redis_client(self):
        import fakeredis.aioredis

        return fakeredis.aioredis.FakeRedis(decode_responses=True)

    @pytest.fixture
    def settings(self):
        from src.shared.config.settings import Settings

        return Settings(ENVIRONMENT="development")

    @pytest.mark.asyncio
    async def test_end_session_writes_artifacts(self, redis_client, settings, tmp_path, monkeypatch) -> None:
        """Wired mode writes 5W artifacts to storage."""
        from src.layer3.sdk.session import SessionManager

        # Point storage to tmp dir
        monkeypatch.chdir(tmp_path)

        sm = SessionManager(agent_id=uuid4(), intent="Test wired", redis_client=redis_client, settings=settings)
        sm.record_step("Analyzed data")
        sm.record_tool_invocation("crm_lookup", cost_usd=0.02)
        sm.record_decision("Use CRM", rationale="Freshest data")

        summary = await sm.end_session()

        # Storage was written
        assert summary.storage_path
        assert (tmp_path / "provenance" / sm.session_id / "manifest.json").exists()
        assert (tmp_path / "provenance" / sm.session_id / "intent.md").exists()
        assert (tmp_path / "provenance" / sm.session_id / "transcript.jsonl").exists()
        assert (tmp_path / "provenance" / sm.session_id / "operations.json").exists()
        assert (tmp_path / "provenance" / sm.session_id / "lineage.json").exists()

        # Batch record was created
        assert summary.batch_record_id

        # Feedback was emitted to Redis stream
        assert summary.feedback_msg_id
        stream_len = await redis_client.xlen("stream:behavioral_session")
        assert stream_len == 1

    @pytest.mark.asyncio
    async def test_end_session_feedback_contains_metrics(self, redis_client, settings, tmp_path, monkeypatch) -> None:
        """Feedback event has the correct metrics for BAE consumption."""
        import json

        from src.layer3.sdk.session import SessionManager

        monkeypatch.chdir(tmp_path)

        sm = SessionManager(agent_id=uuid4(), intent="Test", redis_client=redis_client, settings=settings)
        sm.record_tool_invocation("crm", inputs={"data_source": "portfolio"})
        sm.record_tool_invocation("email", inputs={"data_source": "contacts"})
        sm.record_dead_end("Timeout")

        await sm.end_session()

        messages = await redis_client.xrange("stream:behavioral_session")
        payload = json.loads(messages[0][1]["payload"])
        metrics = payload["metrics"]

        assert metrics["dead_end_count"] == 1
        assert metrics["unique_tools"] == 2
        assert "portfolio" in metrics["data_access_patterns"]
        assert "contacts" in metrics["data_access_patterns"]

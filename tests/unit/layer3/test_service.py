"""Tests for SessionService — session lifecycle management."""

from uuid import uuid4

import pytest

from src.layer3.sdk.service import SessionAlreadyEndedError, SessionNotFoundError, SessionService
from src.shared.config.settings import Settings


class TestSessionService:
    @pytest.fixture
    def redis_client(self):
        import fakeredis.aioredis

        return fakeredis.aioredis.FakeRedis(decode_responses=True)

    @pytest.fixture
    def service(self, redis_client, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        settings = Settings(ENVIRONMENT="development")
        return SessionService(redis_client=redis_client, settings=settings)

    def test_start_session(self, service) -> None:
        sm = service.start_session(uuid4(), "Test intent")
        assert sm.session_id
        assert service.active_count == 1

    def test_get_active_session(self, service) -> None:
        sm = service.start_session(uuid4(), "Test")
        retrieved = service.get_session(sm.session_id)
        assert retrieved.session_id == sm.session_id

    def test_get_nonexistent_session_raises(self, service) -> None:
        with pytest.raises(SessionNotFoundError):
            service.get_session("nonexistent-id")

    def test_record_operations(self, service) -> None:
        sm = service.start_session(uuid4(), "Test")
        sid = sm.session_id

        service.record_step(sid, "Step 1", {"key": "value"})
        service.record_tool_invocation(sid, "crm_lookup", inputs={"id": "123"}, cost_usd=0.01)
        service.record_decision(sid, "Use CRM", alternatives_considered=["Use cache"], rationale="Fresher")
        service.record_dead_end(sid, "API timeout")

        assert len(sm.capture.records) == 4
        assert sm.capture.cost_usd == 0.01
        assert sm.capture.dead_end_count == 1

    @pytest.mark.asyncio
    async def test_end_session_runs_pipeline(self, service) -> None:
        sm = service.start_session(uuid4(), "Full pipeline test")
        sid = sm.session_id

        service.record_step(sid, "Analyzed data")
        service.record_tool_invocation(sid, "tool1", cost_usd=0.02)

        summary = await service.end_session(sid)

        assert summary.session_hash
        assert summary.artifact_count == 2
        assert summary.storage_path  # Artifacts written
        assert summary.feedback_msg_id  # Feedback emitted
        assert summary.integrity_errors == []

        # Session moved from active to completed
        assert service.active_count == 0
        assert service.get_summary(sid) is not None

    @pytest.mark.asyncio
    async def test_end_nonexistent_session_raises(self, service) -> None:
        with pytest.raises(SessionNotFoundError):
            await service.end_session("nonexistent-id")

    @pytest.mark.asyncio
    async def test_end_already_ended_session_raises(self, service) -> None:
        sm = service.start_session(uuid4(), "Test")
        await service.end_session(sm.session_id)
        with pytest.raises(SessionAlreadyEndedError):
            await service.end_session(sm.session_id)

    @pytest.mark.asyncio
    async def test_multiple_concurrent_sessions(self, service) -> None:
        sm1 = service.start_session(uuid4(), "Session 1")
        sm2 = service.start_session(uuid4(), "Session 2")

        service.record_step(sm1.session_id, "S1 step")
        service.record_step(sm2.session_id, "S2 step")

        assert service.active_count == 2

        s1 = await service.end_session(sm1.session_id)
        assert service.active_count == 1

        s2 = await service.end_session(sm2.session_id)
        assert service.active_count == 0

        # Different sessions have different hashes
        assert s1.session_hash != s2.session_hash

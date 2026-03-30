"""Tests for session manager."""

from uuid import uuid4

import pytest

from src.layer3.sdk.session import SessionManager


class TestSessionManager:
    def test_start_and_end_session(self) -> None:
        sm = SessionManager(agent_id=uuid4(), intent="Test intent")
        sm.record_step("step 1")
        sm.record_tool_invocation("tool1", cost_usd=0.01)

        summary = sm.end_session()
        assert summary.session_id == sm.session_id
        assert summary.artifact_count == 2
        assert summary.session_hash  # Non-empty Merkle root
        assert len(summary.session_hash) == 64
        assert summary.cost_usd == 0.01
        assert summary.tool_invocation_count == 1

    def test_session_hash_deterministic(self) -> None:
        # Same operations should produce same content hashes
        agent_id = uuid4()
        sm1 = SessionManager(agent_id=agent_id, intent="test")
        sm1.record_step("step 1")
        sm1.record_step("step 2")

        sm2 = SessionManager(agent_id=agent_id, intent="test")
        sm2.record_step("step 1")
        sm2.record_step("step 2")

        s1 = sm1.end_session()
        s2 = sm2.end_session()
        assert s1.session_hash == s2.session_hash

    def test_cannot_record_after_end(self) -> None:
        sm = SessionManager(agent_id=uuid4(), intent="test")
        sm.end_session()
        with pytest.raises(RuntimeError, match="already ended"):
            sm.record_step("too late")

    def test_cannot_end_twice(self) -> None:
        sm = SessionManager(agent_id=uuid4(), intent="test")
        sm.end_session()
        with pytest.raises(RuntimeError, match="already ended"):
            sm.end_session()

    def test_empty_session(self) -> None:
        sm = SessionManager(agent_id=uuid4(), intent="test")
        summary = sm.end_session()
        assert summary.artifact_count == 0
        assert summary.session_hash == ""

    def test_dead_end_tracking(self) -> None:
        sm = SessionManager(agent_id=uuid4(), intent="test")
        sm.record_dead_end("API timeout")
        sm.record_dead_end("Rate limited")
        summary = sm.end_session()
        assert summary.dead_end_count == 2

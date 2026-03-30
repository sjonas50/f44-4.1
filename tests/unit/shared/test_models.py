from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.shared.models.agent import AgentModel, AgentStatus
from src.shared.models.batch_record import BatchRecord
from src.shared.models.events import AgentRegistered, SessionComplete, TrustTierChanged


class TestAgentModel:
    def test_defaults(self) -> None:
        agent = AgentModel(agent_type="financial_advisor")
        assert agent.status == AgentStatus.UNREGISTERED
        assert agent.trust_tier == 0
        assert agent.human_authorizer_id is None
        assert agent.metadata == {}

    def test_full_construction(self) -> None:
        authorizer = uuid4()
        agent = AgentModel(
            agent_type="data_analyst",
            trust_tier=2,
            human_authorizer_id=authorizer,
            metadata={"department": "risk"},
        )
        assert agent.trust_tier == 2
        assert agent.human_authorizer_id == authorizer

    def test_trust_tier_too_high(self) -> None:
        with pytest.raises(ValidationError):
            AgentModel(agent_type="test", trust_tier=4)

    def test_trust_tier_negative(self) -> None:
        with pytest.raises(ValidationError):
            AgentModel(agent_type="test", trust_tier=-1)


class TestEventModels:
    def test_agent_registered_serialization(self) -> None:
        agent_id = uuid4()
        event = AgentRegistered(agent_id=agent_id, agent_type="advisor")
        data = event.model_dump()
        assert data["event_type"] == "AGENT_REGISTERED"
        assert data["agent_type"] == "advisor"
        roundtrip = AgentRegistered.model_validate(data)
        assert roundtrip.agent_id == agent_id

    def test_trust_tier_changed(self) -> None:
        event = TrustTierChanged(agent_id=uuid4(), old_tier=1, new_tier=2, reason="90-day clean history")
        data = event.model_dump()
        assert data["old_tier"] == 1
        assert data["new_tier"] == 2

    def test_session_complete(self) -> None:
        event = SessionComplete(
            agent_id=uuid4(),
            session_id="sess-123",
            metrics={"dead_end_count": 2, "cost_usd": 0.04},
        )
        data = event.model_dump()
        assert data["metrics"]["dead_end_count"] == 2
        roundtrip = SessionComplete.model_validate(data)
        assert roundtrip.session_id == "sess-123"


class TestBatchRecord:
    def test_audit_record(self) -> None:
        record = BatchRecord(
            hash="abc123",
            record_type="audit",
            layer=2,
            timestamp=datetime.now(UTC),
        )
        assert record.record_type == "audit"
        assert record.layer == 2

    def test_provenance_record(self) -> None:
        record = BatchRecord(
            hash="def456",
            record_type="provenance",
            layer=3,
            timestamp=datetime.now(UTC),
        )
        assert record.record_type == "provenance"

    def test_trust_event_record(self) -> None:
        record = BatchRecord(
            hash="ghi789",
            record_type="trust_event",
            layer=1,
            timestamp=datetime.now(UTC),
        )
        assert record.record_type == "trust_event"

    def test_invalid_record_type(self) -> None:
        with pytest.raises(ValidationError):
            BatchRecord(
                hash="xxx",
                record_type="invalid",
                layer=1,
                timestamp=datetime.now(UTC),
            )

    def test_invalid_layer(self) -> None:
        with pytest.raises(ValidationError):
            BatchRecord(
                hash="xxx",
                record_type="audit",
                layer=4,
                timestamp=datetime.now(UTC),
            )

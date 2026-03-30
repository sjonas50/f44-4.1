"""Tests for Reasoning Capture SDK — comprehensive agent decision capture."""

import pytest
from pydantic import ValidationError

from src.layer3.sdk.capture import (
    DataSensitivity,
    ProvenanceCapture,
    RecordType,
    ToolOutcome,
    _canonical_json,
)


class TestCanonicalJson:
    def test_sorted_keys(self) -> None:
        assert _canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'

    def test_deterministic_across_key_orders(self) -> None:
        d1 = {"tool_name": "crm", "inputs": {"id": 1}, "cost_usd": 0.01}
        d2 = {"cost_usd": 0.01, "tool_name": "crm", "inputs": {"id": 1}}
        assert _canonical_json(d1) == _canonical_json(d2)


class TestBasicCapture:
    def test_record_step(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        record = c.record_step("Analyzed data", {"source": "crm"})
        assert record.record_type == RecordType.STEP
        assert len(record.content_hash) == 64

    def test_append_only(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_step("step 1")
        c.record_step("step 2")
        c.record_step("step 3")
        assert len(c.records) == 3

    def test_records_returns_copy(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_step("step 1")
        records = c.records
        records.clear()
        assert len(c.records) == 1

    def test_record_is_frozen(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        record = c.record_step("step 1")
        with pytest.raises(ValidationError):
            record.content_hash = "tampered"

    def test_deterministic_hashing(self) -> None:
        c1 = ProvenanceCapture(agent_id="agent-1", intent="test")
        c2 = ProvenanceCapture(agent_id="agent-1", intent="test")
        r1 = c1.record_step("same step")
        r2 = c2.record_step("same step")
        assert r1.content_hash == r2.content_hash


class TestThoughtCapture:
    def test_record_thought(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        r = c.record_thought(
            "The client's portfolio shows high risk exposure", reasoning_type="analysis", confidence=0.85
        )
        assert r.record_type == RecordType.THOUGHT
        assert r.data["confidence"] == 0.85
        assert r.data["reasoning_type"] == "analysis"

    def test_confidence_clamped(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        r = c.record_thought("Very sure", confidence=1.5)
        assert r.data["confidence"] == 1.0

    def test_thought_without_confidence(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        r = c.record_thought("Exploring options")
        assert "confidence" not in r.data


class TestObservationCapture:
    def test_record_observation_with_sensitivity(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        r = c.record_observation(
            "Client has 3 active accounts",
            source="crm_lookup output",
            data_source="client_accounts",
            sensitivity=DataSensitivity.CONFIDENTIAL,
            data_accessed=["account_count", "account_ids"],
        )
        assert r.data["sensitivity"] == "confidential"
        assert r.data["data_accessed"] == ["account_count", "account_ids"]

    def test_data_access_patterns_tracked(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_observation("Data 1", data_source="portfolio_db", sensitivity=DataSensitivity.RESTRICTED)
        c.record_observation("Data 2", data_source="public_api", sensitivity=DataSensitivity.PUBLIC)
        assert c.data_access_patterns == ["portfolio_db", "public_api"]


class TestDecisionCapture:
    def test_decision_with_confidence_and_risks(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        r = c.record_decision(
            "Recommend portfolio rebalancing",
            alternatives_considered=["Hold current allocation", "Increase bond exposure"],
            rationale="Risk exposure exceeds client tolerance",
            confidence=0.72,
            risk_factors=["Market volatility", "Client risk profile change"],
        )
        assert r.data["confidence"] == 0.72
        assert len(r.data["risk_factors"]) == 2
        assert len(r.data["alternatives_considered"]) == 2


class TestToolInvocationCapture:
    def test_successful_invocation(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_tool_invocation(
            "crm_lookup",
            inputs={"client_id": "123"},
            outputs={"name": "Acme Corp"},
            outcome=ToolOutcome.SUCCESS,
            duration_ms=45,
            cost_usd=0.01,
        )
        assert c.cost_usd == 0.01
        assert c.tool_failure_count == 0

    def test_failed_invocation(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_tool_invocation(
            "payment_api",
            inputs={"amount": 1000},
            outcome=ToolOutcome.FAILURE,
            error_message="Insufficient funds",
        )
        assert c.tool_failure_count == 1
        assert c._tool_failures[0]["error_message"] == "Insufficient funds"

    def test_retried_invocation(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_tool_invocation(
            "api_call", outcome=ToolOutcome.TIMEOUT, retry_attempt=0, error_message="Timeout after 30s"
        )
        c.record_tool_invocation("api_call", outcome=ToolOutcome.SUCCESS, retry_attempt=1, outputs={"status": "ok"})
        assert c.tool_failure_count == 1
        assert len(c.tool_invocation_names) == 2

    def test_rate_limited_and_permission_denied(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_tool_invocation("api", outcome=ToolOutcome.RATE_LIMITED, error_message="429 Too Many Requests")
        c.record_tool_invocation("admin_api", outcome=ToolOutcome.PERMISSION_DENIED, error_message="403 Forbidden")
        assert c.tool_failure_count == 2


class TestErrorCapture:
    def test_recoverable_error(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        r = c.record_error(
            "api_error", "Connection reset", source="crm_api", recoverable=True, recovery_action="Retried with backoff"
        )
        assert r.data["recoverable"] is True
        assert c.error_count == 1

    def test_unrecoverable_error(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_error("permission", "Access denied to restricted dataset", recoverable=False)
        assert c.error_count == 1


class TestDeadEndCapture:
    def test_dead_end_with_reason(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        r = c.record_dead_end(
            "Tried to query archived data", reason="Data retention policy blocks access after 5 years"
        )
        assert r.record_type == RecordType.DEAD_END
        assert r.data["dead_end_index"] == 1
        assert c.dead_end_count == 1


class TestGuardrailCapture:
    def test_guardrail_block(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_guardrail_check(
            "data_access_policy",
            "pre_action",
            blocked=True,
            details="Agent tried to access PII without authorization",
            action_attempted="query_ssn",
        )
        assert c.guardrail_block_count == 1

    def test_guardrail_pass(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_guardrail_check("cost_limit", "pre_action", blocked=False, details="Cost within budget")
        assert c.guardrail_block_count == 0


class TestDelegationCapture:
    def test_delegation(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_delegation("agent-2", "Summarize quarterly report", result="Summary: Revenue up 15%", duration_ms=3500)
        assert len(c._delegations) == 1


class TestLLMCallCapture:
    def test_llm_call(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_llm_call(
            "claude-sonnet-4-20250514",
            prompt_tokens=500,
            completion_tokens=200,
            latency_ms=1200,
            cost_usd=0.003,
            purpose="reasoning",
        )
        assert c.total_tokens == 700
        assert c.cost_usd == 0.003

    def test_multiple_llm_calls_accumulate(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_llm_call("gpt-4", prompt_tokens=100, completion_tokens=50, cost_usd=0.01)
        c.record_llm_call("claude-sonnet-4-20250514", prompt_tokens=200, completion_tokens=100, cost_usd=0.005)
        assert c.total_tokens == 450
        assert c.cost_usd == pytest.approx(0.015)


class TestGoalCapture:
    def test_goal_hierarchy(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_goal("Analyze client portfolio risk", goal_type="primary")
        c.record_goal("Retrieve current holdings", goal_type="sub_goal", parent_goal="Analyze client portfolio risk")
        c.record_goal(
            "Retrieve current holdings",
            goal_type="sub_goal",
            parent_goal="Analyze client portfolio risk",
            status="completed",
        )
        assert len(c._goals) == 3


class TestFinalization:
    def test_finalize_blocks_all_record_types(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.finalize()
        with pytest.raises(RuntimeError, match="finalized"):
            c.record_step("nope")
        with pytest.raises(RuntimeError, match="finalized"):
            c.record_thought("nope")
        with pytest.raises(RuntimeError, match="finalized"):
            c.record_observation("nope")
        with pytest.raises(RuntimeError, match="finalized"):
            c.record_tool_invocation("nope")
        with pytest.raises(RuntimeError, match="finalized"):
            c.record_decision("nope")
        with pytest.raises(RuntimeError, match="finalized"):
            c.record_error("type", "msg")
        with pytest.raises(RuntimeError, match="finalized"):
            c.record_dead_end("nope")
        with pytest.raises(RuntimeError, match="finalized"):
            c.record_guardrail_check("g", "pre", False)
        with pytest.raises(RuntimeError, match="finalized"):
            c.record_delegation("a", "t")
        with pytest.raises(RuntimeError, match="finalized"):
            c.record_llm_call("m")
        with pytest.raises(RuntimeError, match="finalized"):
            c.record_goal("g")


class TestIntegrity:
    def test_clean_capture_passes(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_step("step")
        c.record_thought("thought")
        c.record_tool_invocation("tool")
        c.record_decision("decision")
        assert c.verify_integrity() == []

    def test_tampered_record_detected(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_step("step 1")
        c._records[0] = c._records[0].model_copy(update={"data": {"description": "tampered"}})
        errors = c.verify_integrity()
        assert len(errors) == 1
        assert "hash mismatch" in errors[0]


class TestFiveWArtifacts:
    def _make_comprehensive_capture(self) -> ProvenanceCapture:
        """Build a realistic capture session with all record types."""
        c = ProvenanceCapture(agent_id="agent-fin-001", intent="Analyze client portfolio and recommend rebalancing")

        c.record_goal("Analyze client portfolio risk", goal_type="primary")
        c.record_goal("Retrieve holdings", goal_type="sub_goal", parent_goal="Analyze client portfolio risk")

        c.record_thought(
            "Need to first pull the current holdings, then assess risk exposure", reasoning_type="planning"
        )

        c.record_llm_call(
            "claude-sonnet-4-20250514",
            prompt_tokens=500,
            completion_tokens=200,
            latency_ms=800,
            cost_usd=0.003,
            purpose="planning",
        )

        c.record_guardrail_check(
            "data_access_policy", "pre_action", blocked=False, details="Agent authorized for portfolio data"
        )

        c.record_tool_invocation(
            "portfolio_api",
            inputs={"client_id": "C-789", "data_source": "portfolio_db"},
            outputs={"holdings": 12},
            outcome=ToolOutcome.SUCCESS,
            duration_ms=120,
            cost_usd=0.001,
        )

        c.record_observation(
            "Client has 12 holdings with 60% equity concentration",
            source="portfolio_api",
            data_source="portfolio_db",
            sensitivity=DataSensitivity.CONFIDENTIAL,
            data_accessed=["holdings", "allocation"],
        )

        c.record_thought(
            "60% equity is above the 50% tolerance threshold — need to recommend rebalancing",
            reasoning_type="analysis",
            confidence=0.9,
        )

        c.record_tool_invocation(
            "risk_model",
            inputs={"portfolio_id": "P-456"},
            outcome=ToolOutcome.TIMEOUT,
            error_message="Model server timeout",
            retry_attempt=0,
        )
        c.record_error(
            "timeout",
            "Risk model timed out",
            source="risk_model",
            recoverable=True,
            recovery_action="Retried after 2s backoff",
        )
        c.record_tool_invocation(
            "risk_model",
            inputs={"portfolio_id": "P-456"},
            outputs={"risk_score": 0.72},
            outcome=ToolOutcome.SUCCESS,
            retry_attempt=1,
            duration_ms=3500,
        )

        c.record_dead_end("Tried to pull tax lot data", reason="Tax lot API deprecated — use new reporting service")

        c.record_guardrail_check(
            "cost_limit", "pre_action", blocked=False, details="Session cost $0.004 under $1.00 limit"
        )

        c.record_delegation(
            "agent-report-writer",
            "Generate risk assessment summary",
            result="Risk assessment complete",
            duration_ms=5000,
        )

        c.record_decision(
            "Recommend 10% equity reduction",
            alternatives_considered=["Hold current allocation", "Full bond pivot"],
            rationale="Client risk tolerance exceeded; gradual rebalancing minimizes tax impact",
            confidence=0.85,
            risk_factors=["Market timing risk", "Tax event generation"],
        )

        c.record_goal(
            "Retrieve holdings", goal_type="sub_goal", parent_goal="Analyze client portfolio risk", status="completed"
        )
        c.record_goal("Analyze client portfolio risk", goal_type="primary", status="completed")

        c.finalize()
        return c

    def test_all_five_artifacts_present(self) -> None:
        artifacts = self._make_comprehensive_capture().to_5w_artifacts()
        assert set(artifacts.keys()) == {
            "manifest.json",
            "intent.md",
            "transcript.jsonl",
            "operations.json",
            "lineage.json",
        }

    def test_manifest_comprehensive(self) -> None:
        m = self._make_comprehensive_capture().to_5w_artifacts()["manifest.json"]
        assert m["schema_version"] == "1.0"
        assert m["agent_id"] == "agent-fin-001"
        assert m["tool_invocation_count"] == 3
        assert m["tool_failure_count"] == 1
        assert m["decision_count"] == 1
        assert m["dead_end_count"] == 1
        assert m["error_count"] == 1
        assert m["guardrail_block_count"] == 0
        assert m["delegation_count"] == 1
        assert m["llm_call_count"] == 1
        assert m["total_tokens"] == 700
        assert m["manifest_integrity_hash"]
        # Record type counts
        assert m["record_type_counts"]["thought"] == 2
        assert m["record_type_counts"]["tool_invocation"] == 3
        assert m["record_type_counts"]["observation"] == 1

    def test_operations_includes_failure_details(self) -> None:
        ops = self._make_comprehensive_capture().to_5w_artifacts()["operations.json"]
        assert ops["tool_outcomes_summary"]["success"] == 2
        assert ops["tool_outcomes_summary"]["timeout"] == 1
        assert len(ops["failures"]) == 1
        assert ops["failures"][0]["error_message"] == "Model server timeout"
        assert ops["llm_summary"]["total_tokens"] == 700
        assert ops["data_sensitivity_summary"]["confidential"] == 1

    def test_lineage_includes_all_reasoning(self) -> None:
        lin = self._make_comprehensive_capture().to_5w_artifacts()["lineage.json"]
        assert len(lin["thoughts"]) == 2
        assert len(lin["decisions"]) == 1
        assert lin["decisions"][0]["confidence"] == 0.85
        assert len(lin["errors"]) == 1
        assert len(lin["guardrail_checks"]) == 2
        assert len(lin["goals"]) == 4

    def test_intent_md_readable(self) -> None:
        md = self._make_comprehensive_capture().to_5w_artifacts()["intent.md"]
        assert "agent-fin-001" in md
        assert "Analyze client portfolio" in md
        assert "Guardrail blocks:" in md
        assert "Goals" in md

    def test_transcript_complete_and_ordered(self) -> None:
        transcript = self._make_comprehensive_capture().to_5w_artifacts()["transcript.jsonl"]
        types = [t["type"] for t in transcript]
        # Verify all record types appear
        assert "goal" in types
        assert "thought" in types
        assert "llm_call" in types
        assert "guardrail" in types
        assert "tool_invocation" in types
        assert "observation" in types
        assert "error" in types
        assert "dead_end" in types
        assert "delegation" in types
        assert "decision" in types
        # Ordered by sequence
        assert transcript[0]["seq"] == 0
        assert transcript[-1]["seq"] == len(transcript) - 1

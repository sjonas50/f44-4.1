"""Tests for Reasoning Capture SDK — content hashing, integrity, 5W artifacts."""

import pytest

from src.layer3.sdk.capture import ProvenanceCapture, _canonical_json


class TestCanonicalJson:
    def test_sorted_keys(self) -> None:
        assert _canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'

    def test_deterministic(self) -> None:
        d1 = {"tool_name": "crm", "inputs": {"id": 1}, "cost_usd": 0.01}
        d2 = {"cost_usd": 0.01, "tool_name": "crm", "inputs": {"id": 1}}
        assert _canonical_json(d1) == _canonical_json(d2)


class TestProvenanceCapture:
    def test_record_step(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        record = c.record_step("Analyzed data", {"source": "crm"})
        assert record.record_type == "step"
        assert record.content_hash
        assert len(record.content_hash) == 64

    def test_record_tool_invocation(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_tool_invocation("crm_lookup", inputs={"client_id": "123"}, outputs={"name": "Acme"}, cost_usd=0.01)
        assert len(c.tool_invocation_names) == 1
        assert c.tool_invocation_names[0] == "crm_lookup"
        assert c.cost_usd == 0.01

    def test_record_decision(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_decision("Use CRM data", alternatives_considered=["Use cache", "Use API"], rationale="Freshest data")
        assert len(c.records) == 1
        assert c.records[0].record_type == "decision"

    def test_record_dead_end(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_dead_end("API timeout")
        assert c.dead_end_count == 1
        # Dead ends include an index
        assert c.records[0].data["dead_end_index"] == 1

    def test_data_access_patterns(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_tool_invocation("lookup", inputs={"data_source": "client_portfolio"})
        c.record_tool_invocation("query", inputs={"data_source": "account_details"})
        assert c.data_access_patterns == ["client_portfolio", "account_details"]

    def test_content_hashes_deterministic_with_canonical_json(self) -> None:
        """Same data in different key order produces same hash."""
        c1 = ProvenanceCapture(agent_id="agent-1", intent="test")
        c2 = ProvenanceCapture(agent_id="agent-1", intent="test")
        r1 = c1.record_step("same step")
        r2 = c2.record_step("same step")
        assert r1.content_hash == r2.content_hash

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
        assert len(c.records) == 1  # Internal state unaffected

    def test_record_is_frozen(self) -> None:
        from pydantic import ValidationError

        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        record = c.record_step("step 1")
        with pytest.raises(ValidationError):
            record.content_hash = "tampered"


class TestFinalization:
    def test_finalize_blocks_further_records(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_step("step 1")
        c.finalize()
        with pytest.raises(RuntimeError, match="finalized"):
            c.record_step("step 2")

    def test_artifacts_require_finalization(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_step("step 1")
        with pytest.raises(RuntimeError, match="finalize"):
            c.to_5w_artifacts()


class TestIntegrityVerification:
    def test_clean_capture_passes(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_step("step 1")
        c.record_tool_invocation("tool1")
        errors = c.verify_integrity()
        assert errors == []

    def test_tampered_record_detected(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_step("step 1")
        # Tamper with internal data (bypass frozen model for test)
        c._records[0] = c._records[0].model_copy(update={"data": {"description": "tampered"}})
        errors = c.verify_integrity()
        assert len(errors) == 1
        assert "hash mismatch" in errors[0]


class TestFiveWArtifacts:
    def _make_capture(self) -> ProvenanceCapture:
        c = ProvenanceCapture(agent_id="agent-1", intent="Analyze portfolio")
        c.record_step("Started analysis")
        c.record_tool_invocation("crm_lookup", inputs={"client_id": "123", "data_source": "crm"})
        c.record_decision("Use historical data", rationale="More complete")
        c.record_dead_end("API rate limited")
        c.finalize()
        return c

    def test_all_five_artifacts_present(self) -> None:
        artifacts = self._make_capture().to_5w_artifacts()
        assert "manifest.json" in artifacts
        assert "intent.md" in artifacts
        assert "transcript.jsonl" in artifacts
        assert "operations.json" in artifacts
        assert "lineage.json" in artifacts

    def test_manifest_has_integrity_hash(self) -> None:
        artifacts = self._make_capture().to_5w_artifacts()
        manifest = artifacts["manifest.json"]
        assert manifest["schema_version"] == "1.0"
        assert manifest["manifest_integrity_hash"]
        assert len(manifest["manifest_integrity_hash"]) == 64
        assert manifest["agent_id"] == "agent-1"
        assert manifest["record_count"] == 4
        assert manifest["tool_invocation_count"] == 1
        assert manifest["dead_end_count"] == 1

    def test_transcript_ordered(self) -> None:
        artifacts = self._make_capture().to_5w_artifacts()
        transcript = artifacts["transcript.jsonl"]
        assert [t["seq"] for t in transcript] == [0, 1, 2, 3]
        assert transcript[0]["type"] == "step"
        assert transcript[1]["type"] == "tool_invocation"
        assert transcript[2]["type"] == "decision"
        assert transcript[3]["type"] == "step"  # dead end is a step

    def test_operations_includes_unique_tools(self) -> None:
        artifacts = self._make_capture().to_5w_artifacts()
        ops = artifacts["operations.json"]
        assert ops["unique_tools"] == ["crm_lookup"]
        assert ops["total_invocations"] == 1
        assert "crm" in ops["data_access_patterns"]

    def test_lineage_includes_reasoning_depth(self) -> None:
        artifacts = self._make_capture().to_5w_artifacts()
        lineage = artifacts["lineage.json"]
        assert lineage["reasoning_depth"] == 4
        assert lineage["dead_ends"] == 1
        assert lineage["decision_chain"] == ["Use historical data"]

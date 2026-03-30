"""Tests for Reasoning Capture SDK."""

from src.layer3.sdk.capture import ProvenanceCapture


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

    def test_data_access_patterns(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_tool_invocation("lookup", inputs={"data_source": "client_portfolio"})
        c.record_tool_invocation("query", inputs={"data_source": "account_details"})
        assert c.data_access_patterns == ["client_portfolio", "account_details"]

    def test_content_hashes_deterministic(self) -> None:
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


class TestFiveWArtifacts:
    def test_all_five_artifacts_present(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="Analyze portfolio")
        c.record_step("Started analysis")
        c.record_tool_invocation("crm_lookup", inputs={"client_id": "123"})
        c.record_decision("Use historical data", rationale="More complete")

        artifacts = c.to_5w_artifacts()
        assert "manifest.json" in artifacts
        assert "intent.md" in artifacts
        assert "transcript.jsonl" in artifacts
        assert "operations.json" in artifacts
        assert "lineage.json" in artifacts

    def test_manifest_contains_session_info(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="Test intent")
        c.record_step("step 1")
        c.record_tool_invocation("tool1")

        artifacts = c.to_5w_artifacts()
        manifest = artifacts["manifest.json"]
        assert manifest["agent_id"] == "agent-1"
        assert manifest["intent"] == "Test intent"
        assert manifest["record_count"] == 2
        assert manifest["tool_invocation_count"] == 1
        assert len(manifest["content_hashes"]) == 2

    def test_transcript_ordered(self) -> None:
        c = ProvenanceCapture(agent_id="agent-1", intent="test")
        c.record_step("first")
        c.record_step("second")
        c.record_step("third")

        artifacts = c.to_5w_artifacts()
        transcript = artifacts["transcript.jsonl"]
        assert [t["seq"] for t in transcript] == [0, 1, 2]

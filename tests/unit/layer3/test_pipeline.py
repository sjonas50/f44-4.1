"""Tests for batch extension, anchor submitter, and feedback emitter."""

import json
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest

from src.layer3.pipeline.anchor_submitter import AnchorSubmissionError, submit_anchor
from src.layer3.pipeline.batch_extension import BatchExtension
from src.shared.crypto.hashing import sha256_hex
from src.shared.crypto.merkle import verify_proof
from src.shared.models.batch_record import BatchRecord


class TestBatchExtension:
    def _make_record(self, record_type: str, layer: int) -> BatchRecord:
        return BatchRecord(
            hash=sha256_hex(f"record-{uuid4()}"),
            record_type=record_type,
            layer=layer,
            timestamp=datetime.now(UTC),
        )

    def test_empty_batch_raises(self) -> None:
        ext = BatchExtension()
        with pytest.raises(ValueError, match="zero records"):
            ext.build_batch()

    def test_single_record(self) -> None:
        ext = BatchExtension()
        ext.add_record(self._make_record("audit", 2))
        result = ext.build_batch()
        assert result.merkle_root
        assert result.record_count == 1

    def test_mixed_type_batch(self) -> None:
        ext = BatchExtension()
        records = [
            self._make_record("audit", 2),
            self._make_record("audit", 2),
            self._make_record("trust_event", 1),
            self._make_record("trust_event", 1),
            self._make_record("provenance", 3),
            self._make_record("provenance", 3),
        ]
        for r in records:
            ext.add_record(r)

        result = ext.build_batch()
        assert result.record_count == 6
        assert len(result.inclusion_proofs) == 6

        # Verify each record's inclusion proof
        for record in records:
            proof = result.inclusion_proofs[str(record.id)]
            assert verify_proof(record.hash, proof, result.merkle_root)

    def test_deterministic_root(self) -> None:
        # Same records in same order → same root
        records = [
            BatchRecord(hash="aaa", record_type="audit", layer=2, timestamp=datetime(2026, 1, 1, tzinfo=UTC)),
            BatchRecord(hash="bbb", record_type="provenance", layer=3, timestamp=datetime(2026, 1, 1, tzinfo=UTC)),
        ]

        ext1 = BatchExtension()
        ext2 = BatchExtension()
        for r in records:
            ext1.add_record(r)
            ext2.add_record(r)

        assert ext1.build_batch().merkle_root == ext2.build_batch().merkle_root


class TestAnchorSubmitter:
    @pytest.fixture
    def settings(self):
        from src.shared.config.settings import Settings

        return Settings(
            BASE_L2_RPC_URL="https://primary.example.com",
            BASE_L2_RPC_FALLBACK_URL="https://fallback.example.com",
            ANCHOR_CONTRACT_ADDRESS="0x1234567890abcdef",
        )

    @pytest.fixture
    def batch_result(self):
        ext = BatchExtension()
        ext.add_record(BatchRecord(
            hash=sha256_hex("test"),
            record_type="audit",
            layer=2,
            timestamp=datetime.now(UTC),
        ))
        return ext.build_batch()

    @pytest.mark.asyncio
    async def test_primary_success(self, settings, batch_result) -> None:
        from src.layer3.pipeline.anchor_submitter import AnchorResult

        mock_result = AnchorResult(
            tx_hash="0xdeadbeef",
            block_number=100,
            chain_id=8453,
            contract_address="0x1234567890abcdef",
            anchored_at=datetime.now(UTC),
        )

        with patch("src.layer3.pipeline.anchor_submitter._send_anchor_tx", return_value=mock_result) as mock_send:
            result = await submit_anchor(batch_result, settings)
            assert result.tx_hash == "0xdeadbeef"
            assert result.contract_address == "0x1234567890abcdef"
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_on_primary_failure(self, settings, batch_result) -> None:
        from src.layer3.pipeline.anchor_submitter import AnchorResult

        mock_result = AnchorResult(
            tx_hash="0xfallback",
            block_number=101,
            chain_id=8453,
            contract_address="0x1234567890abcdef",
            anchored_at=datetime.now(UTC),
        )

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Primary failed")
            return mock_result

        with patch("src.layer3.pipeline.anchor_submitter._send_anchor_tx", side_effect=side_effect):
            result = await submit_anchor(batch_result, settings)
            assert result.tx_hash == "0xfallback"
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_both_rpcs_fail(self, settings, batch_result) -> None:
        with (
            patch(
                "src.layer3.pipeline.anchor_submitter._send_anchor_tx",
                side_effect=RuntimeError("Connection failed"),
            ),
            pytest.raises(AnchorSubmissionError, match="Both RPCs failed"),
        ):
            await submit_anchor(batch_result, settings)


class TestFeedbackEmitter:
    @pytest.fixture
    def redis_client(self):
        import fakeredis.aioredis

        return fakeredis.aioredis.FakeRedis(decode_responses=True)

    @pytest.mark.asyncio
    async def test_emits_correct_schema(self, redis_client) -> None:
        from src.layer3.feedback.emitter import emit_session_feedback
        from src.layer3.sdk.session import SessionManager

        agent_id = uuid4()
        sm = SessionManager(agent_id=agent_id, intent="test")
        sm.record_tool_invocation("crm_lookup", inputs={"data_source": "client_portfolio"})
        sm.record_tool_invocation("portfolio_query", inputs={"data_source": "account_details"})
        sm.record_dead_end("API timeout")
        summary = sm.end_session()

        msg_id = await emit_session_feedback(redis_client, sm.session_id, agent_id, summary, sm.capture)
        assert msg_id

        # Read from stream and verify payload
        messages = await redis_client.xrange("stream:behavioral_session")
        assert len(messages) == 1
        payload = json.loads(messages[0][1]["payload"])

        assert payload["event_type"] == "SESSION_COMPLETE"
        assert payload["agent_id"] == str(agent_id)
        assert payload["metrics"]["dead_end_count"] == 1
        assert payload["metrics"]["unique_tools"] == 2
        assert "client_portfolio" in payload["metrics"]["data_access_patterns"]

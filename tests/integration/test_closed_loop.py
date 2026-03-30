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


class TestMerkleAnchoring:
    """Integration test: mixed-type Merkle batch and proof verification."""

    def test_mixed_batch_with_cross_layer_proofs(self) -> None:
        from datetime import UTC, datetime

        from src.layer3.pipeline.batch_extension import BatchExtension
        from src.shared.crypto.hashing import sha256_hex
        from src.shared.crypto.merkle import verify_proof
        from src.shared.models.batch_record import BatchRecord

        ext = BatchExtension()

        # Add records from all three layers
        records = [
            BatchRecord(hash=sha256_hex("audit-1"), record_type="audit", layer=2, timestamp=datetime.now(UTC)),
            BatchRecord(hash=sha256_hex("audit-2"), record_type="audit", layer=2, timestamp=datetime.now(UTC)),
            BatchRecord(hash=sha256_hex("trust-1"), record_type="trust_event", layer=1, timestamp=datetime.now(UTC)),
            BatchRecord(hash=sha256_hex("trust-2"), record_type="trust_event", layer=1, timestamp=datetime.now(UTC)),
            BatchRecord(hash=sha256_hex("prov-1"), record_type="provenance", layer=3, timestamp=datetime.now(UTC)),
            BatchRecord(hash=sha256_hex("prov-2"), record_type="provenance", layer=3, timestamp=datetime.now(UTC)),
        ]

        for r in records:
            ext.add_record(r)

        result = ext.build_batch()

        # Verify: single Merkle root covers all three layers
        assert result.merkle_root
        assert result.record_count == 6

        # Verify: every record from every layer has a valid inclusion proof
        for record in records:
            proof = result.inclusion_proofs[str(record.id)]
            assert verify_proof(record.hash, proof, result.merkle_root), (
                f"Inclusion proof failed for {record.record_type} record (layer {record.layer})"
            )

        # Verify: root is deterministic
        ext2 = BatchExtension()
        for r in records:
            ext2.add_record(r)
        assert ext2.build_batch().merkle_root == result.merkle_root

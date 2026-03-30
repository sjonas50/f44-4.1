"""Integration test: Merkle anchoring flow.

Mixed BatchRecords from all three layers → single Merkle tree →
inclusion proofs verify for each record type → deterministic root.
"""

from datetime import UTC, datetime

from src.layer3.pipeline.batch_extension import BatchExtension
from src.shared.crypto.hashing import sha256_hex
from src.shared.crypto.merkle import verify_proof
from src.shared.models.batch_record import BatchRecord


class TestMerkleAnchoring:
    """Integration test: mixed-type Merkle batch and proof verification."""

    def test_mixed_batch_with_cross_layer_proofs(self) -> None:
        ext = BatchExtension()

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

        assert result.merkle_root
        assert result.record_count == 6

        for record in records:
            proof = result.inclusion_proofs[str(record.id)]
            assert verify_proof(record.hash, proof, result.merkle_root), (
                f"Inclusion proof failed for {record.record_type} record (layer {record.layer})"
            )

        # Deterministic root
        ext2 = BatchExtension()
        for r in records:
            ext2.add_record(r)
        assert ext2.build_batch().merkle_root == result.merkle_root

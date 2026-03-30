"""Extends ASOR's Merkle batch pipeline for multi-layer records.

Accepts BatchRecord items of any record_type (audit, trust_event, provenance)
and builds a single Merkle tree over all record hashes. Inclusion proofs
work identically for all record types.
"""

from uuid import uuid4

from pydantic import BaseModel

from src.shared.crypto.merkle import MerkleTree
from src.shared.models.batch_record import BatchRecord


class BatchResult(BaseModel):
    """Result of building a Merkle batch from mixed-type records."""

    batch_id: str
    merkle_root: str
    record_count: int
    records: list[BatchRecord]
    inclusion_proofs: dict[str, list[str]]


class BatchExtension:
    """Collects mixed-type BatchRecords and builds a Merkle batch."""

    def __init__(self) -> None:
        self._records: list[BatchRecord] = []

    @property
    def record_count(self) -> int:
        return len(self._records)

    def add_record(self, record: BatchRecord) -> None:
        """Add a record to the batch.

        Args:
            record: BatchRecord with hash, record_type, and layer.
        """
        self._records.append(record)

    def build_batch(self) -> BatchResult:
        """Build the Merkle tree and generate inclusion proofs.

        Returns:
            BatchResult with root, records, and per-record inclusion proofs.

        Raises:
            ValueError: If no records have been added.
        """
        if not self._records:
            raise ValueError("Cannot build batch from zero records")

        # Build Merkle tree over record hashes
        hashes = [r.hash for r in self._records]
        tree = MerkleTree(hashes)

        # Generate inclusion proof for each record
        proofs: dict[str, list[str]] = {}
        for i, record in enumerate(self._records):
            proofs[str(record.id)] = tree.get_proof(i)

        return BatchResult(
            batch_id=str(uuid4()),
            merkle_root=tree.root,
            record_count=len(self._records),
            records=list(self._records),
            inclusion_proofs=proofs,
        )

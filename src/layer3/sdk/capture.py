"""Reasoning capture — append-only, content-hashed session store.

Records agent reasoning steps, tool invocations, and decisions during a session.
Produces 5W forensic artifacts: manifest.json, intent.md, transcript.jsonl,
operations.json, lineage.json.

All records are content-hashed using canonical JSON serialization to ensure
deterministic hashes regardless of dict key ordering. Once appended, records
cannot be modified or deleted — the append-only invariant is enforced by the
class interface.
"""

import json
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from src.shared.crypto.hashing import sha256_hex


def _canonical_json(data: dict) -> str:
    """Produce a canonical JSON string with sorted keys for deterministic hashing."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


class CaptureRecord(BaseModel):
    """A single captured event within a session. Immutable after creation."""

    record_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content_hash: str = ""
    data: dict = Field(default_factory=dict)

    model_config = {"frozen": True}


class ProvenanceCapture:
    """Append-only session capture with content hashing.

    Every record is content-hashed on append using canonical JSON serialization.
    The record list is append-only — no update or delete operations exist.
    This guarantees that:
    1. The same logical data always produces the same hash
    2. Any tampering with record data invalidates the content hash
    3. The Merkle root over all content hashes provides session-level integrity
    """

    def __init__(self, agent_id: str, intent: str) -> None:
        self.agent_id = agent_id
        self.intent = intent
        self._records: list[CaptureRecord] = []
        self._tool_invocations: list[dict] = []
        self._decisions: list[dict] = []
        self._data_access_patterns: list[str] = []
        self._dead_end_count = 0
        self._cost_usd = 0.0
        self._finalized = False

    @property
    def records(self) -> list[CaptureRecord]:
        """Returns a copy of the record list. Cannot be used to mutate internal state."""
        return list(self._records)

    @property
    def dead_end_count(self) -> int:
        return self._dead_end_count

    @property
    def tool_invocation_names(self) -> list[str]:
        return [t["tool_name"] for t in self._tool_invocations]

    @property
    def cost_usd(self) -> float:
        return self._cost_usd

    @property
    def data_access_patterns(self) -> list[str]:
        return list(self._data_access_patterns)

    @property
    def is_finalized(self) -> bool:
        return self._finalized

    def record_step(self, description: str, metadata: dict | None = None) -> CaptureRecord:
        """Record a reasoning step.

        Args:
            description: What the agent did/decided.
            metadata: Optional additional data.

        Returns:
            The appended CaptureRecord.
        """
        self._check_not_finalized()
        data = {"description": description, **(metadata or {})}
        content_hash = sha256_hex(_canonical_json(data))
        record = CaptureRecord(record_type="step", content_hash=content_hash, data=data)
        self._records.append(record)
        return record

    def record_tool_invocation(
        self,
        tool_name: str,
        inputs: dict | None = None,
        outputs: dict | None = None,
        cost_usd: float = 0.0,
    ) -> CaptureRecord:
        """Record a tool invocation.

        Args:
            tool_name: Name of the tool invoked.
            inputs: Tool input parameters.
            outputs: Tool output data.
            cost_usd: Cost of this invocation in USD.

        Returns:
            The appended CaptureRecord.
        """
        self._check_not_finalized()
        invocation = {
            "tool_name": tool_name,
            "inputs": inputs or {},
            "outputs": outputs or {},
            "cost_usd": cost_usd,
        }
        self._tool_invocations.append(invocation)
        self._cost_usd += cost_usd

        # Track data access patterns for behavioral analysis
        if "data_source" in (inputs or {}):
            self._data_access_patterns.append(inputs["data_source"])

        content_hash = sha256_hex(_canonical_json(invocation))
        record = CaptureRecord(record_type="tool_invocation", content_hash=content_hash, data=invocation)
        self._records.append(record)
        return record

    def record_decision(
        self,
        decision: str,
        alternatives_considered: list[str] | None = None,
        rationale: str = "",
    ) -> CaptureRecord:
        """Record a decision point.

        Args:
            decision: The decision made.
            alternatives_considered: Other options evaluated.
            rationale: Why this decision was made.

        Returns:
            The appended CaptureRecord.
        """
        self._check_not_finalized()
        decision_data = {
            "decision": decision,
            "alternatives_considered": alternatives_considered or [],
            "rationale": rationale,
        }
        self._decisions.append(decision_data)

        content_hash = sha256_hex(_canonical_json(decision_data))
        record = CaptureRecord(record_type="decision", content_hash=content_hash, data=decision_data)
        self._records.append(record)
        return record

    def record_dead_end(self, description: str = "") -> CaptureRecord:
        """Record a dead-end in reasoning.

        Args:
            description: What went wrong / why the path was abandoned.

        Returns:
            The appended CaptureRecord.
        """
        self._check_not_finalized()
        self._dead_end_count += 1
        return self.record_step(f"Dead end: {description}", {"dead_end": True, "dead_end_index": self._dead_end_count})

    def finalize(self) -> None:
        """Mark the capture as finalized. No more records can be appended."""
        self._finalized = True

    def verify_integrity(self) -> list[str]:
        """Verify that all content hashes match their record data.

        Returns:
            List of error messages for any integrity violations. Empty = all good.
        """
        errors: list[str] = []
        for i, record in enumerate(self._records):
            expected_hash = sha256_hex(_canonical_json(record.data))
            if record.content_hash != expected_hash:
                errors.append(
                    f"Record {i} ({record.record_type}): hash mismatch — "
                    f"stored={record.content_hash[:16]}..., computed={expected_hash[:16]}..."
                )
        return errors

    def to_5w_artifacts(self) -> dict[str, object]:
        """Produce the 5W forensic artifacts.

        Returns:
            Dict with keys: manifest.json, intent.md, transcript.jsonl,
            operations.json, lineage.json — each as a Python object.

        Raises:
            RuntimeError: If capture has not been finalized.
        """
        if not self._finalized:
            raise RuntimeError("Cannot produce artifacts from an unfinalized capture. Call finalize() first.")

        content_hashes = [r.content_hash for r in self._records]

        # Compute a manifest hash over all content hashes for top-level integrity
        manifest_integrity_hash = sha256_hex(_canonical_json({"hashes": content_hashes}))

        manifest = {
            "schema_version": "1.0",
            "agent_id": self.agent_id,
            "intent": self.intent,
            "record_count": len(self._records),
            "tool_invocation_count": len(self._tool_invocations),
            "decision_count": len(self._decisions),
            "dead_end_count": self._dead_end_count,
            "total_cost_usd": self._cost_usd,
            "content_hashes": content_hashes,
            "manifest_integrity_hash": manifest_integrity_hash,
            "finalized_at": datetime.now(UTC).isoformat(),
        }

        intent_md = (
            f"# Agent Intent\n\n"
            f"**Agent:** {self.agent_id}\n\n"
            f"**Intent:** {self.intent}\n\n"
            f"**Records:** {len(self._records)}\n\n"
            f"**Cost:** ${self._cost_usd:.4f}\n"
        )

        transcript = [
            {
                "seq": i,
                "type": r.record_type,
                "timestamp": r.timestamp.isoformat(),
                "hash": r.content_hash,
                "data": r.data,
            }
            for i, r in enumerate(self._records)
        ]

        operations = {
            "tool_invocations": self._tool_invocations,
            "data_access_patterns": self._data_access_patterns,
            "unique_tools": list(set(self.tool_invocation_names)),
            "total_invocations": len(self._tool_invocations),
        }

        lineage = {
            "decisions": self._decisions,
            "dead_ends": self._dead_end_count,
            "decision_chain": [d["decision"] for d in self._decisions],
            "reasoning_depth": len(self._records),
        }

        return {
            "manifest.json": manifest,
            "intent.md": intent_md,
            "transcript.jsonl": transcript,
            "operations.json": operations,
            "lineage.json": lineage,
        }

    def _check_not_finalized(self) -> None:
        if self._finalized:
            raise RuntimeError("Capture is finalized — no more records can be appended")

"""Session manager for reasoning capture.

Manages session lifecycle: start → record steps/tools/decisions → end.
Produces a session hash (Merkle root over all artifact content hashes).
"""

import time
from uuid import UUID, uuid4

from pydantic import BaseModel

from src.layer3.sdk.capture import ProvenanceCapture
from src.shared.crypto.merkle import MerkleTree


class SessionSummary(BaseModel):
    """Summary produced when a session ends."""

    session_id: str
    agent_id: str
    session_hash: str
    artifact_count: int
    duration_ms: int
    dead_end_count: int
    tool_invocation_count: int
    cost_usd: float


class SessionManager:
    """Manages a single reasoning capture session."""

    def __init__(self, agent_id: UUID, intent: str) -> None:
        self.session_id = str(uuid4())
        self.agent_id = str(agent_id)
        self._capture = ProvenanceCapture(agent_id=self.agent_id, intent=intent)
        self._start_time = time.monotonic()
        self._ended = False

    @property
    def capture(self) -> ProvenanceCapture:
        return self._capture

    def record_step(self, description: str, metadata: dict | None = None) -> None:
        """Record a reasoning step."""
        self._check_active()
        self._capture.record_step(description, metadata)

    def record_tool_invocation(
        self,
        tool_name: str,
        inputs: dict | None = None,
        outputs: dict | None = None,
        cost_usd: float = 0.0,
    ) -> None:
        """Record a tool invocation."""
        self._check_active()
        self._capture.record_tool_invocation(tool_name, inputs, outputs, cost_usd)

    def record_decision(
        self,
        decision: str,
        alternatives_considered: list[str] | None = None,
        rationale: str = "",
    ) -> None:
        """Record a decision point."""
        self._check_active()
        self._capture.record_decision(decision, alternatives_considered, rationale)

    def record_dead_end(self, description: str = "") -> None:
        """Record a dead-end in reasoning."""
        self._check_active()
        self._capture.record_dead_end(description)

    def end_session(self) -> SessionSummary:
        """End the session and produce a summary.

        Returns:
            SessionSummary with Merkle root hash over all artifacts.

        Raises:
            RuntimeError: If session already ended.
        """
        self._check_active()
        self._ended = True

        duration_ms = int((time.monotonic() - self._start_time) * 1000)
        records = self._capture.records

        # Compute session hash as Merkle root over content hashes
        if records:
            content_hashes = [r.content_hash for r in records]
            tree = MerkleTree(content_hashes)
            session_hash = tree.root
        else:
            session_hash = ""

        return SessionSummary(
            session_id=self.session_id,
            agent_id=self.agent_id,
            session_hash=session_hash,
            artifact_count=len(records),
            duration_ms=duration_ms,
            dead_end_count=self._capture.dead_end_count,
            tool_invocation_count=len(self._capture.tool_invocation_names),
            cost_usd=self._capture.cost_usd,
        )

    def _check_active(self) -> None:
        if self._ended:
            raise RuntimeError(f"Session {self.session_id} has already ended")

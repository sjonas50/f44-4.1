"""Session manager for reasoning capture.

Manages session lifecycle: start → record steps/tools/decisions → end.
On end_session(), automatically:
1. Finalizes capture (no more records)
2. Computes session hash (Merkle root over content hashes)
3. Writes 5W artifacts to storage (local dev / S3 WORM prod)
4. Submits session hash to batch pipeline as provenance record
5. Emits feedback event to behavioral stream (L3 → L1 closed loop)
"""

import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

import redis.asyncio as aioredis
import structlog

from src.layer3.sdk.capture import ProvenanceCapture
from src.layer3.sdk.models import SessionSummary
from src.layer3.sdk.storage import StorageResult, write_session
from src.shared.config.settings import Settings
from src.shared.crypto.hashing import sha256_hex
from src.shared.crypto.merkle import MerkleTree
from src.shared.models.batch_record import BatchRecord

logger = structlog.get_logger()


class SessionManager:
    """Manages a single reasoning capture session.

    Can operate in two modes:
    - Standalone (no Redis/settings): end_session() returns summary only.
      Storage, batch, and feedback are skipped. For unit tests and SDK-only usage.
    - Wired (with Redis + settings): end_session() runs the full pipeline.
    """

    def __init__(
        self,
        agent_id: UUID,
        intent: str,
        redis_client: aioredis.Redis | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session_id = str(uuid4())
        self.agent_id = str(agent_id)
        self._capture = ProvenanceCapture(agent_id=self.agent_id, intent=intent)
        self._start_time = time.monotonic()
        self._ended = False
        self._redis = redis_client
        self._settings = settings

    @property
    def capture(self) -> ProvenanceCapture:
        return self._capture

    @property
    def is_ended(self) -> bool:
        return self._ended

    def record_step(self, description: str, metadata: dict | None = None) -> None:
        """Record a reasoning step."""
        self._check_active()
        self._capture.record_step(description, metadata)

    def record_tool_invocation(self, tool_name: str, **kwargs) -> None:
        """Record a tool invocation. Accepts all ProvenanceCapture.record_tool_invocation kwargs."""
        self._check_active()
        self._capture.record_tool_invocation(tool_name, **kwargs)

    def record_decision(self, decision: str, **kwargs) -> None:
        """Record a decision point. Accepts all ProvenanceCapture.record_decision kwargs."""
        self._check_active()
        self._capture.record_decision(decision, **kwargs)

    def record_dead_end(self, description: str = "", reason: str = "") -> None:
        """Record a dead-end in reasoning."""
        self._check_active()
        self._capture.record_dead_end(description, reason)

    def record_thought(self, thought: str, **kwargs) -> None:
        """Record the agent's internal reasoning/chain-of-thought."""
        self._check_active()
        self._capture.record_thought(thought, **kwargs)

    def record_observation(self, observation: str, **kwargs) -> None:
        """Record what the agent observed."""
        self._check_active()
        self._capture.record_observation(observation, **kwargs)

    def record_error(self, error_type: str, message: str, **kwargs) -> None:
        """Record an error encountered during reasoning."""
        self._check_active()
        self._capture.record_error(error_type, message, **kwargs)

    def record_guardrail_check(self, guardrail_name: str, check_type: str, blocked: bool, **kwargs) -> None:
        """Record a guardrail or policy check."""
        self._check_active()
        self._capture.record_guardrail_check(guardrail_name, check_type, blocked, **kwargs)

    def record_delegation(self, delegate_agent_id: str, task: str, **kwargs) -> None:
        """Record delegation to a sub-agent."""
        self._check_active()
        self._capture.record_delegation(delegate_agent_id, task, **kwargs)

    def record_llm_call(self, model: str, **kwargs) -> None:
        """Record an LLM API call."""
        self._check_active()
        self._capture.record_llm_call(model, **kwargs)

    def record_goal(self, goal: str, **kwargs) -> None:
        """Record a goal or sub-goal."""
        self._check_active()
        self._capture.record_goal(goal, **kwargs)

    async def end_session(self) -> SessionSummary:
        """End the session and execute the full provenance pipeline.

        Pipeline steps (when Redis and settings are available):
        1. Finalize capture → verify integrity
        2. Compute session hash (Merkle root over content hashes)
        3. Write 5W artifacts to storage
        4. Submit session hash as provenance BatchRecord to batch pipeline
        5. Emit feedback event to behavioral stream

        If Redis/settings are not wired, only steps 1-2 run (standalone mode).

        Returns:
            SessionSummary with hash, storage path, and pipeline status.

        Raises:
            RuntimeError: If session already ended.
        """
        self._check_active()
        self._ended = True

        duration_ms = int((time.monotonic() - self._start_time) * 1000)

        # Step 1: Finalize and verify integrity
        self._capture.finalize()
        integrity_errors = self._capture.verify_integrity()
        if integrity_errors:
            logger.error("session_integrity_violation", session_id=self.session_id, errors=integrity_errors)

        # Step 2: Compute session hash
        records = self._capture.records
        if records:
            content_hashes = [r.content_hash for r in records]
            tree = MerkleTree(content_hashes)
            session_hash = tree.root
        else:
            session_hash = sha256_hex(f"empty-session:{self.session_id}")

        summary = SessionSummary(
            session_id=self.session_id,
            agent_id=self.agent_id,
            session_hash=session_hash,
            artifact_count=len(records),
            duration_ms=duration_ms,
            dead_end_count=self._capture.dead_end_count,
            tool_invocation_count=len(self._capture.tool_invocation_names),
            cost_usd=self._capture.cost_usd,
            integrity_errors=integrity_errors,
        )

        # Steps 3-5: Only run if wired to infrastructure
        if self._settings is not None:
            summary = await self._run_pipeline(summary)

        logger.info(
            "session_ended",
            session_id=self.session_id,
            agent_id=self.agent_id,
            artifacts=len(records),
            hash=session_hash[:16],
            duration_ms=duration_ms,
            wired=self._settings is not None,
        )

        return summary

    async def _run_pipeline(self, summary: SessionSummary) -> SessionSummary:
        """Execute the storage, batch, and feedback pipeline steps."""
        assert self._settings is not None  # Caller checks this before calling

        # Step 3: Write 5W artifacts to storage
        try:
            artifacts = self._capture.to_5w_artifacts()
            storage_result: StorageResult = await write_session(self.session_id, artifacts, self._settings)
            summary.storage_path = storage_result.storage_path
            logger.info("session_artifacts_stored", session_id=self.session_id, path=storage_result.storage_path)
        except Exception:
            logger.exception("session_storage_failed", session_id=self.session_id)

        # Step 4: Create provenance BatchRecord for the Merkle batch pipeline
        try:
            batch_record = BatchRecord(
                hash=summary.session_hash,
                record_type="provenance",
                layer=3,
                timestamp=datetime.now(UTC),
            )
            summary.batch_record_id = str(batch_record.id)

            # Enqueue for the periodic anchor scheduler
            if self._redis is not None:
                from src.layer3.pipeline.scheduler import enqueue_batch_record

                await enqueue_batch_record(self._redis, batch_record)

            logger.info(
                "session_batch_record_enqueued",
                session_id=self.session_id,
                batch_record_id=str(batch_record.id),
                hash=summary.session_hash[:16],
            )
        except Exception:
            logger.exception("session_batch_record_failed", session_id=self.session_id)

        # Step 5: Emit feedback to behavioral stream (L3 → L1)
        if self._redis is not None:
            try:
                from src.layer3.feedback.emitter import emit_session_feedback

                msg_id = await emit_session_feedback(
                    self._redis,
                    self.session_id,
                    UUID(self.agent_id),
                    summary,
                    self._capture,
                )
                summary.feedback_msg_id = msg_id
            except Exception:
                logger.exception("session_feedback_failed", session_id=self.session_id)

        return summary

    def _check_active(self) -> None:
        if self._ended:
            raise RuntimeError(f"Session {self.session_id} has already ended")

"""Session service — manages active reasoning capture sessions.

Provides the stateful layer between the FastAPI router and SessionManager.
Active sessions are held in memory (one per session_id) and cleaned up on end.
"""

from uuid import UUID

import redis.asyncio as aioredis
import structlog

from src.layer3.sdk.models import SessionSummary
from src.layer3.sdk.session import SessionManager
from src.shared.config.settings import Settings

logger = structlog.get_logger()


class SessionNotFoundError(Exception):
    """Raised when a session_id does not match any active session."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"Session not found: {session_id}")


class SessionAlreadyEndedError(Exception):
    """Raised when attempting to record on a finalized session."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"Session already ended: {session_id}")


class SessionService:
    """Manages the lifecycle of active reasoning capture sessions.

    Thread-safety note: FastAPI runs in a single async event loop, so
    dict operations are safe. For multi-worker deployments, sessions are
    pinned to the worker that created them.
    """

    def __init__(self, redis_client: aioredis.Redis | None, settings: Settings) -> None:
        self._redis = redis_client
        self._settings = settings
        self._active_sessions: dict[str, SessionManager] = {}
        self._completed_summaries: dict[str, SessionSummary] = {}

    @property
    def active_count(self) -> int:
        return len(self._active_sessions)

    def start_session(self, agent_id: UUID, intent: str) -> SessionManager:
        """Start a new reasoning capture session.

        Args:
            agent_id: The agent performing the reasoning.
            intent: What the agent is trying to accomplish.

        Returns:
            SessionManager for recording steps.
        """
        sm = SessionManager(
            agent_id=agent_id,
            intent=intent,
            redis_client=self._redis,
            settings=self._settings,
        )
        self._active_sessions[sm.session_id] = sm
        logger.info("session_started", session_id=sm.session_id, agent_id=str(agent_id), intent=intent)
        return sm

    def get_session(self, session_id: str) -> SessionManager:
        """Get an active session by ID.

        Raises:
            SessionNotFoundError: If session doesn't exist.
        """
        sm = self._active_sessions.get(session_id)
        if sm is None:
            raise SessionNotFoundError(session_id)
        return sm

    async def end_session(self, session_id: str) -> SessionSummary:
        """End a session, run the full pipeline, and clean up.

        Args:
            session_id: Session to end.

        Returns:
            SessionSummary with hash, storage path, and pipeline results.

        Raises:
            SessionNotFoundError: If session doesn't exist.
        """
        sm = self._active_sessions.pop(session_id, None)
        if sm is None:
            # Check if it was already completed
            if session_id in self._completed_summaries:
                raise SessionAlreadyEndedError(session_id)
            raise SessionNotFoundError(session_id)

        summary = await sm.end_session()
        self._completed_summaries[session_id] = summary
        return summary

    def get_summary(self, session_id: str) -> SessionSummary | None:
        """Get the summary of a completed session."""
        return self._completed_summaries.get(session_id)

    def record_step(self, session_id: str, description: str, metadata: dict | None = None) -> None:
        """Record a step in an active session."""
        sm = self.get_session(session_id)
        sm.record_step(description, metadata)

    def record_tool_invocation(
        self,
        session_id: str,
        tool_name: str,
        inputs: dict | None = None,
        outputs: dict | None = None,
        cost_usd: float = 0.0,
        **kwargs,
    ) -> None:
        """Record a tool invocation in an active session."""
        sm = self.get_session(session_id)
        sm.record_tool_invocation(tool_name, inputs=inputs, outputs=outputs, cost_usd=cost_usd, **kwargs)

    def record_decision(
        self,
        session_id: str,
        decision: str,
        alternatives_considered: list[str] | None = None,
        rationale: str = "",
        **kwargs,
    ) -> None:
        """Record a decision in an active session."""
        sm = self.get_session(session_id)
        sm.record_decision(decision, alternatives_considered=alternatives_considered, rationale=rationale, **kwargs)

    def record_dead_end(self, session_id: str, description: str = "") -> None:
        """Record a dead end in an active session."""
        sm = self.get_session(session_id)
        sm.record_dead_end(description)

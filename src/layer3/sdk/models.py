"""Layer 3 SDK models — shared across session, service, emitter, and router."""

from pydantic import BaseModel


class SessionSummary(BaseModel):
    """Summary produced when a reasoning capture session ends."""

    session_id: str
    agent_id: str
    session_hash: str
    artifact_count: int
    duration_ms: int
    dead_end_count: int
    tool_invocation_count: int
    cost_usd: float
    storage_path: str = ""
    batch_record_id: str = ""
    feedback_msg_id: str = ""
    integrity_errors: list[str] = []

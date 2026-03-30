"""Behavioral feedback emitter — L3 → L1.

After a session ends, publishes session metrics to the behavioral stream
so the Behavioral Analysis Engine can update baselines and anomaly scores.
"""

from datetime import UTC, datetime
from uuid import UUID

import redis.asyncio as aioredis
import structlog

from src.layer3.sdk.capture import ProvenanceCapture
from src.layer3.sdk.models import SessionSummary
from src.shared.redis_client.streams import xadd

logger = structlog.get_logger()

BEHAVIORAL_STREAM = "stream:behavioral_session"


async def emit_session_feedback(
    redis_client: aioredis.Redis,
    session_id: str,
    agent_id: UUID,
    summary: SessionSummary,
    capture: ProvenanceCapture,
) -> str:
    """Publish session completion event to the behavioral stream.

    Event payload matches the integration map data contract:
    {event_type, agent_id, session_id, metrics: {dead_end_count,
    tool_invocations, unique_tools, cost_usd, duration_ms,
    data_access_patterns, timestamp}}

    Args:
        redis_client: Async Redis client.
        session_id: Session identifier.
        agent_id: Agent UUID.
        summary: Session summary with aggregated metrics.
        capture: ProvenanceCapture with detailed session data.

    Returns:
        Redis Stream message ID.
    """
    tool_names = capture.tool_invocation_names
    unique_tools = len(set(tool_names))

    event_data = {
        "event_type": "SESSION_COMPLETE",
        "agent_id": str(agent_id),
        "session_id": session_id,
        "metrics": {
            "dead_end_count": summary.dead_end_count,
            "tool_invocations": tool_names,
            "unique_tools": unique_tools,
            "cost_usd": summary.cost_usd,
            "duration_ms": summary.duration_ms,
            "data_access_patterns": capture.data_access_patterns,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    }

    msg_id = await xadd(redis_client, BEHAVIORAL_STREAM, event_data)

    logger.info(
        "session_feedback_emitted",
        session_id=session_id,
        agent_id=str(agent_id),
        dead_ends=summary.dead_end_count,
        tools=unique_tools,
    )
    return msg_id

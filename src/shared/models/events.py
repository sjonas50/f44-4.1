from datetime import UTC, datetime
from uuid import UUID

from pydantic import Field

from src.shared.models.base import BaseEntity


class BaseEvent(BaseEntity):
    """Base event model for cross-layer event streaming."""

    event_type: str
    agent_id: UUID
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentRegistered(BaseEvent):
    """Emitted when a new agent is registered in the KYA Engine."""

    event_type: str = "AGENT_REGISTERED"
    agent_type: str = ""
    human_authorizer_id: UUID | None = None


class TrustTierChanged(BaseEvent):
    """Emitted when an agent's trust tier is promoted or demoted."""

    event_type: str = "TRUST_TIER_CHANGED"
    old_tier: int = 0
    new_tier: int = 0
    reason: str = ""


class AgentRevoked(BaseEvent):
    """Emitted when an agent's credentials are revoked."""

    event_type: str = "AGENT_REVOKED"
    reason: str = ""
    revoked_by: str = ""


class CircuitBreakerActivated(BaseEvent):
    """Emitted when the CircuitBreaker performs bulk revocation."""

    event_type: str = "CIRCUIT_BREAKER_ACTIVATED"
    scope_type: str = ""
    scope_value: str = ""
    affected_agent_count: int = 0
    reason: str = ""


class SessionComplete(BaseEvent):
    """Emitted by Layer 3 when a reasoning session ends. Consumed by Layer 1 BAE."""

    event_type: str = "SESSION_COMPLETE"
    session_id: str = ""
    metrics: dict = Field(default_factory=dict)

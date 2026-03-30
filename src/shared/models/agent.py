from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from src.shared.models.base import BaseEntity


class AgentStatus(StrEnum):
    """Agent lifecycle states."""

    UNREGISTERED = "unregistered"
    REGISTERED = "registered"
    VERIFIED = "verified"
    ATTESTED = "attested"
    ESTABLISHED = "established"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class AgentModel(BaseEntity):
    """AI agent registered in the KYA Engine.

    Wraps/extends ASOR's existing agent registration model with trust tier,
    KYA verification, and human authorizer linkage.
    """

    agent_type: str
    status: AgentStatus = AgentStatus.UNREGISTERED
    trust_tier: int = Field(default=0, ge=0, le=3)
    human_authorizer_id: UUID | None = None
    kya_verified_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)

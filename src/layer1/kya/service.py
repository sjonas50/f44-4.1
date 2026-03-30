"""KYA Engine service layer.

Orchestrates agent lifecycle transitions, persistence, and event emission.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import asyncpg
import redis.asyncio as aioredis
import structlog

from src.layer1.kya.state_machine import AgentLifecycleMachine
from src.shared.models.agent import AgentModel, AgentStatus
from src.shared.models.events import AgentRegistered, AgentRevoked
from src.shared.redis_client.streams import xadd

logger = structlog.get_logger()

TRUST_EVENT_STREAM = "stream:trust_event"


class KYAService:
    """Manages agent registration, verification, and lifecycle transitions."""

    def __init__(self, conn: asyncpg.Connection, redis_client: aioredis.Redis) -> None:
        self._conn = conn
        self._redis = redis_client

    async def register_agent(
        self,
        agent_type: str,
        human_authorizer_id: UUID | None = None,
        metadata: dict | None = None,
    ) -> AgentModel:
        """Register a new agent in the KYA Engine.

        Args:
            agent_type: Type classification of the agent.
            human_authorizer_id: UUID of the human responsible for this agent.
            metadata: Optional agent metadata.

        Returns:
            The registered AgentModel.
        """
        sm = AgentLifecycleMachine()
        sm.send("register")

        agent = AgentModel(
            id=uuid4(),
            agent_type=agent_type,
            status=AgentStatus.REGISTERED,
            trust_tier=0,
            human_authorizer_id=human_authorizer_id,
            metadata=metadata or {},
        )

        from src.layer1.kya.repository import create_agent

        agent = await create_agent(self._conn, agent)

        event = AgentRegistered(
            agent_id=agent.id,
            agent_type=agent.agent_type,
            human_authorizer_id=human_authorizer_id,
        )
        await xadd(self._redis, TRUST_EVENT_STREAM, event.model_dump(mode="json"))

        logger.info("agent_registered", agent_id=str(agent.id), agent_type=agent_type)
        return agent

    async def verify_agent(self, agent_id: UUID) -> AgentModel:
        """Mark an agent as verified after KYA checks pass.

        Args:
            agent_id: Agent to verify.

        Returns:
            Updated AgentModel.

        Raises:
            ValueError: If agent not found.
            TransitionNotAllowed: If transition is invalid.
        """
        return await self._transition(agent_id, AgentStatus.REGISTERED, "verify", AgentStatus.VERIFIED)

    async def suspend_agent(self, agent_id: UUID, reason: str = "") -> AgentModel:
        """Suspend an agent.

        Args:
            agent_id: Agent to suspend.
            reason: Reason for suspension.

        Returns:
            Updated AgentModel.
        """
        agent = await self._get_or_raise(agent_id)
        sm = self._machine_at_state(agent.status)
        sm.send("suspend")

        from src.layer1.kya.repository import transition_status

        updated = await transition_status(self._conn, agent_id, AgentStatus.SUSPENDED)
        if updated is None:
            raise ValueError(f"Agent {agent_id} not found during update")

        logger.info("agent_suspended", agent_id=str(agent_id), reason=reason)
        return updated

    async def revoke_agent(self, agent_id: UUID, reason: str = "", revoked_by: str = "") -> AgentModel:
        """Revoke an agent's credentials.

        Args:
            agent_id: Agent to revoke.
            reason: Reason for revocation.
            revoked_by: Identity of the revoker.

        Returns:
            Updated AgentModel.
        """
        agent = await self._get_or_raise(agent_id)
        sm = self._machine_at_state(agent.status)
        sm.send("revoke")

        from src.layer1.kya.repository import transition_status

        updated = await transition_status(self._conn, agent_id, AgentStatus.REVOKED)
        if updated is None:
            raise ValueError(f"Agent {agent_id} not found during update")

        event = AgentRevoked(agent_id=agent_id, reason=reason, revoked_by=revoked_by)
        await xadd(self._redis, TRUST_EVENT_STREAM, event.model_dump(mode="json"))

        logger.info("agent_revoked", agent_id=str(agent_id), reason=reason)
        return updated

    async def _get_or_raise(self, agent_id: UUID) -> AgentModel:
        """Fetch agent or raise ValueError."""
        from src.layer1.kya.repository import get_agent

        agent = await get_agent(self._conn, agent_id)
        if agent is None:
            raise ValueError(f"Agent {agent_id} not found")
        return agent

    async def _transition(
        self,
        agent_id: UUID,
        expected_status: AgentStatus,
        event_name: str,
        target_status: AgentStatus,
    ) -> AgentModel:
        """Execute a forward lifecycle transition."""
        agent = await self._get_or_raise(agent_id)
        sm = self._machine_at_state(agent.status)
        sm.send(event_name)

        updates: dict = {"status": target_status.value}
        if target_status == AgentStatus.VERIFIED:
            updates["kya_verified_at"] = datetime.now(UTC)

        from src.layer1.kya.repository import update_agent

        updated = await update_agent(self._conn, agent_id, updates)
        if updated is None:
            raise ValueError(f"Agent {agent_id} not found during update")

        logger.info("agent_transition", agent_id=str(agent_id), to=target_status.value)
        return updated

    @staticmethod
    def _machine_at_state(status: AgentStatus) -> AgentLifecycleMachine:
        """Create a state machine initialized at the given state."""
        state_map = {
            AgentStatus.UNREGISTERED: "unregistered",
            AgentStatus.REGISTERED: "registered",
            AgentStatus.VERIFIED: "verified",
            AgentStatus.ATTESTED: "attested",
            AgentStatus.ESTABLISHED: "established",
            AgentStatus.SUSPENDED: "suspended",
            AgentStatus.REVOKED: "revoked",
        }
        sm = AgentLifecycleMachine(start_value=state_map[status])
        return sm

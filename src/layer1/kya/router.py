"""KYA Engine FastAPI router.

Provides the REST API that ASOR's CPE pre-check calls for agent lookup.
All endpoints are wired to KYAService with a DB connection from the pool.
"""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from statemachine.exceptions import TransitionNotAllowed

from src.shared.middleware.auth import require_auth
from src.shared.models.agent import AgentStatus

logger = structlog.get_logger()

router = APIRouter(prefix="/kya", tags=["kya"], dependencies=[Depends(require_auth)])


class RegisterAgentRequest(BaseModel):
    agent_type: str
    human_authorizer_id: UUID | None = None
    metadata: dict | None = None


class AgentStatusUpdate(BaseModel):
    action: str  # "verify", "attest", "establish", "suspend", "reactivate", "revoke"
    reason: str = ""


class AgentResponse(BaseModel):
    agent_id: UUID
    status: str
    trust_tier: int
    human_authorizer_id: UUID | None
    kya_verified_at: str | None
    registered_at: str
    agent_type: str


def _get_db_pool():
    """Get the DB pool singleton from the Layer 1 app."""
    from src.layer1.app import _db_pool

    if _db_pool is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return _db_pool


def _get_redis():
    """Get the Redis client singleton."""
    from src.shared.redis_client.client import get_redis_client

    try:
        return get_redis_client()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail="Redis not available") from e


def _agent_to_response(agent) -> AgentResponse:
    return AgentResponse(
        agent_id=agent.id,
        status=agent.status.value,
        trust_tier=agent.trust_tier,
        human_authorizer_id=agent.human_authorizer_id,
        kya_verified_at=agent.kya_verified_at.isoformat() if agent.kya_verified_at else None,
        registered_at=agent.created_at.isoformat(),
        agent_type=agent.agent_type,
    )


@router.post("/agents", status_code=201)
async def register_agent(request: RegisterAgentRequest) -> AgentResponse:
    """Register a new agent in the KYA Engine."""
    from src.layer1.kya.service import KYAService

    pool = _get_db_pool()
    redis = _get_redis()

    async with pool.acquire() as conn:
        svc = KYAService(conn, redis)
        agent = await svc.register_agent(
            agent_type=request.agent_type,
            human_authorizer_id=request.human_authorizer_id,
            metadata=request.metadata,
        )
    return _agent_to_response(agent)


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: UUID) -> AgentResponse:
    """Get agent details. This is the endpoint ASOR CPE pre-check calls."""
    from src.layer1.kya.repository import get_agent as repo_get_agent

    pool = _get_db_pool()

    async with pool.acquire() as conn:
        agent = await repo_get_agent(conn, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return _agent_to_response(agent)


@router.patch("/agents/{agent_id}/status")
async def update_agent_status(agent_id: UUID, update: AgentStatusUpdate) -> AgentResponse:
    """Transition agent status via lifecycle state machine."""
    from src.layer1.kya.service import KYAService

    pool = _get_db_pool()
    redis = _get_redis()

    action_map = {
        "verify": "verify_agent",
        "suspend": "suspend_agent",
        "revoke": "revoke_agent",
    }

    method_name = action_map.get(update.action)
    if method_name is None:
        raise HTTPException(status_code=400, detail=f"Unsupported action: {update.action}. Use: {list(action_map)}")

    async with pool.acquire() as conn:
        svc = KYAService(conn, redis)
        try:
            method = getattr(svc, method_name)
            if update.action in ("revoke", "suspend"):
                agent = await method(agent_id, reason=update.reason)
            else:
                agent = await method(agent_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except TransitionNotAllowed as e:
            raise HTTPException(status_code=409, detail=f"Invalid transition: {e}") from e

    return _agent_to_response(agent)


@router.get("/agents")
async def list_agents(
    status: str | None = None,
    trust_tier: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AgentResponse]:
    """List agents with optional filters."""
    from src.layer1.kya.repository import list_agents as repo_list_agents

    pool = _get_db_pool()
    agent_status = AgentStatus(status) if status else None

    async with pool.acquire() as conn:
        agents = await repo_list_agents(conn, status=agent_status, trust_tier=trust_tier, limit=limit, offset=offset)

    return [_agent_to_response(a) for a in agents]

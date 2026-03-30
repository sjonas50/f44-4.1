"""KYA Engine FastAPI router.

Provides the REST API that ASOR's CPE pre-check calls for agent lookup.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.shared.middleware.auth import require_auth

router = APIRouter(prefix="/kya", tags=["kya"], dependencies=[Depends(require_auth)])


class RegisterAgentRequest(BaseModel):
    agent_type: str
    human_authorizer_id: UUID | None = None
    metadata: dict | None = None


class AgentStatusUpdate(BaseModel):
    status: str
    reason: str = ""


class AgentResponse(BaseModel):
    agent_id: UUID
    status: str
    trust_tier: int
    human_authorizer_id: UUID | None
    kya_verified_at: str | None
    registered_at: str
    agent_type: str


@router.post("/agents", status_code=201)
async def register_agent(request: RegisterAgentRequest) -> AgentResponse:
    """Register a new agent. Placeholder — wired in app.py with real deps."""
    raise HTTPException(status_code=501, detail="Not wired to service layer yet")


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: UUID) -> AgentResponse:
    """Get agent details. This is the endpoint ASOR CPE pre-check calls."""
    raise HTTPException(status_code=501, detail="Not wired to service layer yet")


@router.patch("/agents/{agent_id}/status")
async def update_agent_status(agent_id: UUID, update: AgentStatusUpdate) -> AgentResponse:
    """Transition agent status."""
    raise HTTPException(status_code=501, detail="Not wired to service layer yet")


@router.get("/agents")
async def list_agents(
    status: str | None = None,
    trust_tier: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AgentResponse]:
    """List agents with optional filters."""
    raise HTTPException(status_code=501, detail="Not wired to service layer yet")

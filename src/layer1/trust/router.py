"""Trust tier FastAPI router.

GET /trust/tier/{agent_id} is the endpoint ASOR's risk scorer calls.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.shared.middleware.auth import require_auth

router = APIRouter(prefix="/trust", tags=["trust"], dependencies=[Depends(require_auth)])


class TierResponse(BaseModel):
    tier: int
    weight_modifier: float
    name: str


class TierChangeRequest(BaseModel):
    reason: str = ""


def _get_trust_service():
    from src.layer1.app import _trust_service

    if _trust_service is None:
        raise HTTPException(status_code=503, detail="Trust service not available")
    return _trust_service


def _get_db_pool():
    from src.layer1.app import _db_pool

    if _db_pool is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return _db_pool


@router.get("/tier/{agent_id}")
async def get_tier(agent_id: UUID) -> TierResponse:
    """Get trust tier and weight modifier. Called by ASOR risk scorer."""
    svc = _get_trust_service()
    info = await svc.get_tier_info(agent_id)
    return TierResponse(**info)


@router.post("/tier/{agent_id}/promote")
async def promote_tier(agent_id: UUID, request: TierChangeRequest) -> TierResponse:
    """Promote agent trust tier by one level."""
    svc = _get_trust_service()
    pool = _get_db_pool()

    # Get current tier from the agent record
    from src.layer1.kya.repository import get_agent

    async with pool.acquire() as conn:
        agent = await get_agent(conn, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    try:
        await svc.promote_tier(agent_id, agent.trust_tier, request.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    info = await svc.get_tier_info(agent_id)
    return TierResponse(**info)


@router.post("/tier/{agent_id}/demote")
async def demote_tier(agent_id: UUID, request: TierChangeRequest) -> TierResponse:
    """Demote agent trust tier by one level."""
    svc = _get_trust_service()
    pool = _get_db_pool()

    from src.layer1.kya.repository import get_agent

    async with pool.acquire() as conn:
        agent = await get_agent(conn, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    try:
        await svc.demote_tier(agent_id, agent.trust_tier, request.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    info = await svc.get_tier_info(agent_id)
    return TierResponse(**info)

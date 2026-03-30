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


@router.get("/tier/{agent_id}")
async def get_tier(agent_id: UUID) -> TierResponse:
    """Get trust tier and weight modifier. Called by ASOR risk scorer."""
    raise HTTPException(status_code=501, detail="Not wired to service layer yet")


@router.post("/tier/{agent_id}/promote")
async def promote_tier(agent_id: UUID, request: TierChangeRequest) -> TierResponse:
    """Promote agent trust tier by one level."""
    raise HTTPException(status_code=501, detail="Not wired to service layer yet")


@router.post("/tier/{agent_id}/demote")
async def demote_tier(agent_id: UUID, request: TierChangeRequest) -> TierResponse:
    """Demote agent trust tier by one level."""
    raise HTTPException(status_code=501, detail="Not wired to service layer yet")

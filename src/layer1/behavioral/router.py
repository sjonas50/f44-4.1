"""Behavioral analysis FastAPI router.

GET /behavioral/score/{agent_id} is the endpoint ASOR's risk scorer calls.
Must return within 1ms (Redis read only).
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/behavioral", tags=["behavioral"])


@router.get("/score/{agent_id}")
async def get_anomaly_score(agent_id: UUID) -> dict:
    """Get anomaly score. Called by ASOR risk scorer — must be < 1ms."""
    raise HTTPException(status_code=501, detail="Not wired to service layer yet")


@router.get("/baseline/{agent_id}")
async def get_baseline(agent_id: UUID) -> dict:
    """Debug endpoint: get full baseline stats for an agent."""
    raise HTTPException(status_code=501, detail="Not wired to service layer yet")

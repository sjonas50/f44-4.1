"""Behavioral analysis FastAPI router.

GET /behavioral/score/{agent_id} is the endpoint ASOR's risk scorer calls.
Must return within 1ms (Redis read only — never computes on the fly).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from src.shared.middleware.auth import require_auth

router = APIRouter(prefix="/behavioral", tags=["behavioral"], dependencies=[Depends(require_auth)])


def _get_behavioral_service():
    from src.layer1.app import _behavioral_service

    if _behavioral_service is None:
        raise HTTPException(status_code=503, detail="Behavioral service not available")
    return _behavioral_service


@router.get("/score/{agent_id}")
async def get_anomaly_score(agent_id: UUID) -> dict:
    """Get anomaly score. Called by ASOR risk scorer — must be < 1ms."""
    svc = _get_behavioral_service()
    result = await svc.get_anomaly_score(agent_id)
    return result.model_dump()


@router.get("/baseline/{agent_id}")
async def get_baseline(agent_id: UUID) -> dict:
    """Debug endpoint: get full baseline stats for an agent."""
    svc = _get_behavioral_service()
    baseline = await svc.get_baseline(agent_id)
    if baseline is None:
        raise HTTPException(status_code=404, detail=f"No baseline for agent {agent_id}")
    return baseline

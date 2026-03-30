"""CircuitBreaker FastAPI router.

Admin-only endpoints for emergency bulk revocation.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.shared.middleware.auth import require_admin

router = APIRouter(prefix="/circuit-breaker", tags=["circuit-breaker"], dependencies=[Depends(require_admin)])


class BulkRevokeRequest(BaseModel):
    scope_type: Literal["agent_class", "trust_tier", "human_authorizer"]
    scope_value: str
    reason: str = ""


class CircuitBreakerResponse(BaseModel):
    active: bool
    message: str


def _get_circuit_breaker_service():
    from src.layer1.app import _circuit_breaker_service

    if _circuit_breaker_service is None:
        raise HTTPException(status_code=503, detail="CircuitBreaker service not available")
    return _circuit_breaker_service


def _get_db_pool():
    from src.layer1.app import _db_pool

    if _db_pool is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return _db_pool


@router.post("/activate")
async def activate(reason: str = "") -> CircuitBreakerResponse:
    """Activate platform-wide circuit breaker."""
    svc = _get_circuit_breaker_service()
    await svc.activate(reason)
    return CircuitBreakerResponse(active=True, message=f"Circuit breaker activated: {reason}")


@router.post("/deactivate")
async def deactivate() -> CircuitBreakerResponse:
    """Deactivate the circuit breaker."""
    svc = _get_circuit_breaker_service()
    await svc.deactivate()
    return CircuitBreakerResponse(active=False, message="Circuit breaker deactivated")


@router.post("/bulk-revoke")
async def bulk_revoke(request: BulkRevokeRequest) -> dict:
    """Bulk revoke agents matching scope criteria.

    Queries agents by scope, then revokes each via the KYA service,
    and publishes revocation events to the durable Redis Stream.
    """
    svc = _get_circuit_breaker_service()
    pool = _get_db_pool()

    from src.layer1.kya.repository import list_agents
    from src.shared.models.agent import AgentStatus

    # Find matching agents based on scope
    async with pool.acquire() as conn:
        if request.scope_type == "trust_tier":
            agents = await list_agents(conn, trust_tier=int(request.scope_value), limit=10000)
        elif request.scope_type == "agent_class":
            # Filter by agent_type after retrieval (no direct DB filter for agent_type yet)
            all_agents = await list_agents(conn, limit=10000)
            agents = [a for a in all_agents if a.agent_type == request.scope_value]
        else:
            # human_authorizer scope
            all_agents = await list_agents(conn, limit=10000)
            agents = [a for a in all_agents if str(a.human_authorizer_id) == request.scope_value]

    # Filter out already-revoked agents
    active_agents = [a for a in agents if a.status != AgentStatus.REVOKED]
    agent_ids = [a.id for a in active_agents]

    if not agent_ids:
        return {"revoked_count": 0, "message": "No matching active agents found"}

    count = await svc.bulk_revoke(
        scope_type=request.scope_type,
        scope_value=request.scope_value,
        agent_ids=agent_ids,
        reason=request.reason,
    )

    return {
        "revoked_count": count,
        "scope_type": request.scope_type,
        "scope_value": request.scope_value,
        "message": f"Revoked {count} agents",
    }

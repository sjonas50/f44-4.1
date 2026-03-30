"""CircuitBreaker FastAPI router."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/circuit-breaker", tags=["circuit-breaker"])


class BulkRevokeRequest(BaseModel):
    scope_type: str
    scope_value: str
    reason: str = ""


class CircuitBreakerResponse(BaseModel):
    active: bool
    message: str


@router.post("/activate")
async def activate(reason: str = "") -> CircuitBreakerResponse:
    """Activate platform-wide circuit breaker."""
    raise HTTPException(status_code=501, detail="Not wired to service layer yet")


@router.post("/deactivate")
async def deactivate() -> CircuitBreakerResponse:
    """Deactivate the circuit breaker."""
    raise HTTPException(status_code=501, detail="Not wired to service layer yet")


@router.post("/bulk-revoke")
async def bulk_revoke(request: BulkRevokeRequest) -> dict:
    """Bulk revoke agents matching scope criteria."""
    raise HTTPException(status_code=501, detail="Not wired to service layer yet")

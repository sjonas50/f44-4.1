"""Anchor pipeline FastAPI router."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.shared.middleware.auth import require_auth

router = APIRouter(prefix="/anchor", tags=["anchor"], dependencies=[Depends(require_auth)])


class AnchorStatusResponse(BaseModel):
    last_batch_id: str | None
    last_tx_hash: str | None
    anchor_count: int


@router.get("/status")
async def anchor_status() -> AnchorStatusResponse:
    """Get current anchoring pipeline status."""
    raise HTTPException(status_code=501, detail="Not wired to service layer yet")


@router.post("/submit")
async def submit_batch() -> dict:
    """Manually trigger batch anchor submission."""
    raise HTTPException(status_code=501, detail="Not wired to service layer yet")

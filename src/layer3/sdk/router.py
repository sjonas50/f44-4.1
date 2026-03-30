"""Provenance session FastAPI router."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.shared.middleware.auth import require_auth

router = APIRouter(prefix="/sessions", tags=["sessions"], dependencies=[Depends(require_auth)])


class StartSessionRequest(BaseModel):
    agent_id: UUID
    intent: str


class RecordStepRequest(BaseModel):
    description: str
    metadata: dict | None = None


class RecordToolRequest(BaseModel):
    tool_name: str
    inputs: dict | None = None
    outputs: dict | None = None
    cost_usd: float = 0.0


class RecordDecisionRequest(BaseModel):
    decision: str
    alternatives_considered: list[str] | None = None
    rationale: str = ""


class SessionResponse(BaseModel):
    session_id: str
    status: str


@router.post("", status_code=201)
async def start_session(request: StartSessionRequest) -> SessionResponse:
    """Start a new reasoning capture session."""
    raise HTTPException(status_code=501, detail="Not wired to service layer yet")


@router.post("/{session_id}/steps")
async def record_step(session_id: str, request: RecordStepRequest) -> dict:
    """Record a reasoning step in an active session."""
    raise HTTPException(status_code=501, detail="Not wired to service layer yet")


@router.post("/{session_id}/tools")
async def record_tool(session_id: str, request: RecordToolRequest) -> dict:
    """Record a tool invocation in an active session."""
    raise HTTPException(status_code=501, detail="Not wired to service layer yet")


@router.post("/{session_id}/decisions")
async def record_decision(session_id: str, request: RecordDecisionRequest) -> dict:
    """Record a decision point in an active session."""
    raise HTTPException(status_code=501, detail="Not wired to service layer yet")


@router.post("/{session_id}/end")
async def end_session(session_id: str) -> dict:
    """End a session and produce summary with Merkle root."""
    raise HTTPException(status_code=501, detail="Not wired to service layer yet")


@router.get("/{session_id}")
async def get_session(session_id: str) -> dict:
    """Get session summary and artifacts."""
    raise HTTPException(status_code=501, detail="Not wired to service layer yet")

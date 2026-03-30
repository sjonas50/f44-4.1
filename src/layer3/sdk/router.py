"""Provenance session FastAPI router.

All endpoints are wired to SessionService. Sessions are stateful — start a
session, record steps/tools/decisions, then end it to trigger the full
provenance pipeline (storage → batch → feedback).
"""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.shared.middleware.auth import require_auth

logger = structlog.get_logger()

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
    agent_id: str | None = None
    intent: str | None = None


class SessionSummaryResponse(BaseModel):
    session_id: str
    agent_id: str
    session_hash: str
    artifact_count: int
    duration_ms: int
    dead_end_count: int
    tool_invocation_count: int
    cost_usd: float
    storage_path: str
    batch_record_id: str
    feedback_msg_id: str
    integrity_errors: list[str]


def _get_session_service():
    """Get the SessionService singleton. Set during app lifespan."""
    from src.layer3.app import _session_service

    if _session_service is None:
        raise HTTPException(status_code=503, detail="Session service not initialized")
    return _session_service


@router.post("", status_code=201)
async def start_session(request: StartSessionRequest) -> SessionResponse:
    """Start a new reasoning capture session."""
    svc = _get_session_service()
    sm = svc.start_session(request.agent_id, request.intent)
    return SessionResponse(
        session_id=sm.session_id,
        status="active",
        agent_id=sm.agent_id,
        intent=request.intent,
    )


@router.post("/{session_id}/steps")
async def record_step(session_id: str, request: RecordStepRequest) -> dict:
    """Record a reasoning step in an active session."""
    svc = _get_session_service()
    try:
        svc.record_step(session_id, request.description, request.metadata)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"status": "recorded", "session_id": session_id}


@router.post("/{session_id}/tools")
async def record_tool(session_id: str, request: RecordToolRequest) -> dict:
    """Record a tool invocation in an active session."""
    svc = _get_session_service()
    try:
        svc.record_tool_invocation(session_id, request.tool_name, request.inputs, request.outputs, request.cost_usd)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"status": "recorded", "session_id": session_id}


@router.post("/{session_id}/decisions")
async def record_decision(session_id: str, request: RecordDecisionRequest) -> dict:
    """Record a decision point in an active session."""
    svc = _get_session_service()
    try:
        svc.record_decision(session_id, request.decision, request.alternatives_considered, request.rationale)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"status": "recorded", "session_id": session_id}


@router.post("/{session_id}/dead-ends")
async def record_dead_end(session_id: str, description: str = "") -> dict:
    """Record a dead-end in reasoning."""
    svc = _get_session_service()
    try:
        svc.record_dead_end(session_id, description)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"status": "recorded", "session_id": session_id}


@router.post("/{session_id}/end")
async def end_session(session_id: str) -> SessionSummaryResponse:
    """End a session and execute the full provenance pipeline."""
    svc = _get_session_service()
    try:
        summary = await svc.end_session(session_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return SessionSummaryResponse(**summary.model_dump())


@router.get("/{session_id}")
async def get_session(session_id: str) -> dict:
    """Get session status or completed summary."""
    svc = _get_session_service()

    # Check active sessions first
    try:
        sm = svc.get_session(session_id)
        return {
            "session_id": sm.session_id,
            "agent_id": sm.agent_id,
            "status": "active",
            "record_count": len(sm.capture.records),
            "cost_usd": sm.capture.cost_usd,
        }
    except Exception:
        pass

    # Check completed sessions
    summary = svc.get_summary(session_id)
    if summary is not None:
        return {"status": "completed", **summary.model_dump()}

    raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

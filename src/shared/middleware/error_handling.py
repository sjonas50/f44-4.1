"""Global exception handlers for FastAPI."""

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from src.layer3.pipeline.anchor_submitter import AnchorSubmissionError

logger = structlog.get_logger()


class NotFoundError(Exception):
    """Raised when a requested resource is not found."""

    def __init__(self, detail: str = "Resource not found") -> None:
        self.detail = detail


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on a FastAPI app."""

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": exc.detail})

    @app.exception_handler(ValidationError)
    async def validation_handler(request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    @app.exception_handler(AnchorSubmissionError)
    async def anchor_error_handler(request: Request, exc: AnchorSubmissionError) -> JSONResponse:
        logger.error("anchor_submission_failed", error=str(exc))
        return JSONResponse(
            status_code=503,
            content={"detail": "Anchor submission failed", "error": str(exc)},
            headers={"Retry-After": "60"},
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        logger.exception("unhandled_error", error=str(exc), request_id=request_id)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )

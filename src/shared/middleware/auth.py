"""JWT authentication dependency for FastAPI.

Validates Bearer tokens using the JWT_SIGNING_KEY from settings.
Used on all endpoints; security-critical routes (circuit-breaker)
require additional role checks.
"""

import jwt
import structlog
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.shared.config.settings import Settings

logger = structlog.get_logger()

_bearer_scheme = HTTPBearer(auto_error=False)
_default_settings = Settings()


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),  # noqa: B008
    settings: Settings = Depends(lambda: _default_settings),  # noqa: B008
) -> dict:
    """Validate JWT Bearer token and return decoded claims.

    Returns:
        Decoded JWT payload dict with at minimum 'sub' claim.

    Raises:
        HTTPException 401: If token is missing or invalid.
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    if not settings.JWT_SIGNING_KEY:
        raise HTTPException(status_code=503, detail="Authentication not configured")

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SIGNING_KEY,
            algorithms=["HS256"],
        )
    except jwt.ExpiredSignatureError as err:
        raise HTTPException(status_code=401, detail="Token expired") from err
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}") from e

    return payload


async def require_admin(claims: dict = Depends(require_auth)) -> dict:  # noqa: B008
    """Require 'admin' role in JWT claims. For security-critical endpoints.

    Returns:
        Decoded JWT payload.

    Raises:
        HTTPException 403: If role is not 'admin'.
    """
    role = claims.get("role", "")
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return claims

"""Authentication dependency — validates JWT and injects current user."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.exceptions import UnauthorizedError
from app.core.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


async def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """Extract and validate JWT; return the subject (user ID) claim."""
    if credentials is None:
        raise UnauthorizedError()
    try:
        payload = decode_access_token(credentials.credentials)
        subject: str = payload["sub"]
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return subject


CurrentUserID = Annotated[str, Depends(get_current_user_id)]

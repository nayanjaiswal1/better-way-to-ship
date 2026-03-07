"""Health-check endpoint — used by load balancers and container orchestrators."""
from __future__ import annotations

from fastapi import APIRouter, status
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get(
    "",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check",
    description="Returns 200 when the service is ready to handle requests.",
)
async def health_check() -> HealthResponse:
    from app.core.config import get_settings

    settings = get_settings()
    return HealthResponse(status="ok", version=settings.APP_VERSION)

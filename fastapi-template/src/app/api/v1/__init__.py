"""API v1 router — register all v1 sub-routers here."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import health

router = APIRouter()
router.include_router(health.router, prefix="/health", tags=["health"])

"""Health check router — Phase 1."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from shared.schemas import HealthResponse

router = APIRouter(tags=["health"])

APP_VERSION = "1.0.0"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=APP_VERSION,
        time=datetime.now(timezone.utc).isoformat(),
    )

"""Model inventory. Reports availability without revealing configuration."""

from __future__ import annotations

from fastapi import APIRouter

from ..deps import services

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("")
def list_models() -> dict:
    svc = services()
    return {
        "external_enabled": svc.settings.external_models_enabled,
        "models": svc.models.available_models(),
    }

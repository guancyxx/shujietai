from __future__ import annotations
from fastapi import APIRouter, HTTPException

from app.schemas import SystemConfigResponse, SystemConfigUpdateRequest
from app.container import retry_counters, system_config_service

router = APIRouter(prefix="", tags=["system"])


@router.get("/api/v1/health")
def health() -> dict[str, object]:
    return {
        "status": "healthy",
        "service": "shujietai-backend",
        "metrics": {
            "ingest_success_total": retry_counters["ingest_success_total"],
            "ingest_retry_total": retry_counters["ingest_retry_total"],
            "ingest_dlq_total": retry_counters["ingest_dlq_total"],
        },
    }


@router.get("/api/v1/system/config", response_model=SystemConfigResponse)
def get_system_config() -> SystemConfigResponse:
    return system_config_service.get_config()


@router.put("/api/v1/system/config/github-token", response_model=SystemConfigResponse)
def update_github_token(payload: SystemConfigUpdateRequest) -> SystemConfigResponse:
    system_config_service.update_github_token(payload.github_token)
    return system_config_service.get_config()

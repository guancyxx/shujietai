from fastapi import APIRouter

router = APIRouter(tags=["health"])


def create_health_router(retry_counters: dict[str, int]) -> APIRouter:
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

    return router
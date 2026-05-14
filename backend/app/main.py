from __future__ import annotations
import asyncio
import os
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.container import (
    store, retry_service, retry_counters, ws_manager,
    dispatch_service, worker_pool, lifecycle_service,
)
from app.services.retry_worker import RetryWorkerConfig, run_retry_loop
from app.services.pending_execution_worker import PendingExecutionWorkerConfig, run_pending_execution_loop

from app.api.routes_hermes import router as hermes_router
from app.api.routes_skills import router as skills_router
from app.api.routes_system import router as system_router
from app.api.routes_projects import router as projects_router
from app.api.routes_task_board import router as task_board_router
from app.api.routes_sessions import router as sessions_router


def _build_retry_worker_config() -> RetryWorkerConfig:
    max_retries = int(os.getenv("INGEST_MAX_RETRIES", "3"))
    delays_raw = os.getenv("INGEST_RETRY_DELAYS", "1,3,10")
    backoff = [int(item.strip()) for item in delays_raw.split(",") if item.strip()]
    loop_interval_seconds = float(os.getenv("INGEST_RETRY_LOOP_INTERVAL_SECONDS", "1"))
    return RetryWorkerConfig(
        enabled=True,
        loop_interval_seconds=loop_interval_seconds,
        max_retries=max_retries,
        backoff_seconds=backoff,
    )


def _build_pending_execution_worker_config() -> PendingExecutionWorkerConfig:
    return PendingExecutionWorkerConfig(
        enabled=os.getenv("PENDING_EXECUTION_WORKER_ENABLED", "true").lower() == "true",
        loop_interval_seconds=float(os.getenv("PENDING_EXECUTION_WORKER_INTERVAL_SECONDS", "2")),
        batch_size=int(os.getenv("PENDING_EXECUTION_WORKER_BATCH_SIZE", "20")),
    )


def _build_retry_tick_hook(counters: dict[str, int]):
    def tick_hook(result) -> None:
        counters["ingest_retry_total"] += result.retried_count
        counters["ingest_success_total"] += result.succeeded_count
        counters["ingest_dlq_total"] += result.dead_letter_count

    return tick_hook


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    # Crash recovery: mark any orphaned 'running' tasks as 'paused'
    if dispatch_service is not None:
        recovered = dispatch_service.recover_running_tasks()
        if recovered > 0:
            import logging
            logging.getLogger(__name__).warning(
                "Recovered %d orphaned dispatch tasks (set to paused)", recovered,
            )

    # Attach singletons to app.state for route access
    app_instance.state.dispatch_service = dispatch_service
    app_instance.state.worker_pool = worker_pool
    app_instance.state.task_lifecycle_service = lifecycle_service
    app_instance.state.ws_manager = ws_manager

    retry_task = None
    if retry_service is not None:
        retry_enabled = os.getenv("INGEST_RETRY_ENABLED", "true").lower() == "true"
        if retry_enabled:
            config = _build_retry_worker_config()
            retry_task = asyncio.create_task(
                run_retry_loop(
                    retry_service=retry_service,
                    ingest_callable=store.ingest,
                    config=config,
                    on_tick=_build_retry_tick_hook(retry_counters),
                )
            )
            app_instance.state.retry_task = retry_task

    pending_execution_task = None
    if dispatch_service is not None and worker_pool is not None:
        pending_config = _build_pending_execution_worker_config()
        if pending_config.enabled:
            pending_execution_task = asyncio.create_task(
                run_pending_execution_loop(
                    dispatch_service=dispatch_service,
                    worker_pool=worker_pool,
                    config=pending_config,
                    ingest_fn=store.ingest,
                ),
                name="pending-execution-worker",
            )
            app_instance.state.pending_execution_task = pending_execution_task

    cleanup_task = None
    if lifecycle_service is not None:
        async def _run_cleanup_loop() -> None:
            while True:
                try:
                    lifecycle_service.cleanup_cancelled_tasks()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception("Task lifecycle cleanup failed")
                await asyncio.sleep(60)

        cleanup_task = asyncio.create_task(_run_cleanup_loop(), name="task-lifecycle-cleanup")
        app_instance.state.task_lifecycle_cleanup_task = cleanup_task

    try:
        yield
    finally:
        existing_pending_task = getattr(app_instance.state, "pending_execution_task", None)
        if existing_pending_task is not None:
            existing_pending_task.cancel()
            try:
                await existing_pending_task
            except asyncio.CancelledError:
                pass

        existing_cleanup_task = getattr(app_instance.state, "task_lifecycle_cleanup_task", None)
        if existing_cleanup_task is not None:
            existing_cleanup_task.cancel()
            try:
                await existing_cleanup_task
            except asyncio.CancelledError:
                pass

        # Cancel dispatch worker pool tasks
        if worker_pool is not None:
            worker_pool.cancel_all()

        existing_retry_task = getattr(app_instance.state, "retry_task", None)
        if existing_retry_task is not None:
            existing_retry_task.cancel()
            try:
                await existing_retry_task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="ShuJieTai API", version="0.1.0", lifespan=lifespan)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dispatch orchestration routes (ADR-0004)
from app.api.routes_dispatch import router as dispatch_router
from app.api.routes_ws import router as ws_router

app.include_router(dispatch_router)
app.include_router(ws_router)
app.include_router(hermes_router)
app.include_router(skills_router)
app.include_router(system_router)
app.include_router(projects_router)
app.include_router(task_board_router)
app.include_router(sessions_router)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid4()))
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response

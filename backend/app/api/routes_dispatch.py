"""REST API routes for dispatch orchestration layer (ADR-0004)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.schemas import (
    DispatchCreateRequest,
    DispatchEventListResponse,
    DispatchResumeRequest,
    DispatchTaskItem,
    DispatchTaskListResponse,
    EmergencyStopResponse,
    InterruptRequest,
)
from app.services.dispatch_service import DispatchService
from app.services.dispatch_worker import DispatchWorkerPool

router = APIRouter(prefix="/api/v1/dispatch", tags=["dispatch"])


def _get_dispatch_service() -> DispatchService:
    from app.main import app
    svc = getattr(app.state, "dispatch_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="dispatch_service_unavailable")
    return svc


def _get_worker_pool() -> DispatchWorkerPool:
    from app.main import app
    pool = getattr(app.state, "worker_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="worker_pool_unavailable")
    return pool


@router.get("", response_model=DispatchTaskListResponse)
def list_dispatch_tasks(
    status: str | None = Query(default=None, description="Filter by status"),
) -> DispatchTaskListResponse:
    svc = _get_dispatch_service()
    items = svc.list_tasks(status=status)
    return DispatchTaskListResponse(items=items)


@router.post("", response_model=DispatchTaskItem, status_code=201)
async def create_dispatch_task(payload: DispatchCreateRequest) -> DispatchTaskItem:
    svc = _get_dispatch_service()
    pool = _get_worker_pool()

    task = svc.create_task(payload)

    updated = svc.transition_task(task.id, "running")
    if updated is None:
        raise HTTPException(status_code=500, detail="dispatch_transition_failed")

    # Start the async worker for this task (must be in async context for event loop)
    pool.start_task(updated)
    return updated


@router.get("/{task_id}", response_model=DispatchTaskItem)
def get_dispatch_task(task_id: str) -> DispatchTaskItem:
    svc = _get_dispatch_service()
    task = svc.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="dispatch_task_not_found")
    return task


@router.get("/{task_id}/events", response_model=DispatchEventListResponse)
def list_dispatch_events(
    task_id: str,
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
) -> DispatchEventListResponse:
    svc = _get_dispatch_service()
    task = svc.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="dispatch_task_not_found")
    items = svc.list_events(task_id, limit=limit, offset=offset)
    return DispatchEventListResponse(items=items)


@router.post("/{task_id}/resume", response_model=DispatchTaskItem)
async def resume_dispatch_task(task_id: str, payload: DispatchResumeRequest) -> DispatchTaskItem:
    svc = _get_dispatch_service()
    pool = _get_worker_pool()

    task = svc.resume_task(task_id, payload)
    if task is None:
        raise HTTPException(status_code=409, detail="dispatch_task_not_resumable")

    pool.start_task(task)
    return task


@router.post("/{task_id}/interrupt", response_model=DispatchTaskItem)
async def interrupt_dispatch_task(task_id: str, payload: InterruptRequest) -> DispatchTaskItem:
    svc = _get_dispatch_service()
    pool = _get_worker_pool()

    task = svc.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="dispatch_task_not_found")
    if task.status not in ("queued", "running"):
        raise HTTPException(status_code=409, detail="dispatch_task_not_interruptible")

    ok = pool.interrupt_task(task_id, payload.user_message)
    if not ok:
        raise HTTPException(status_code=409, detail="dispatch_task_interrupt_failed")

    # Return fresh task state
    updated = svc.get_task(task_id)
    return updated or task


@router.post("/{task_id}/cancel", response_model=DispatchTaskItem)
def cancel_dispatch_task(task_id: str) -> DispatchTaskItem:
    svc = _get_dispatch_service()
    pool = _get_worker_pool()

    pool.cancel_task(task_id)

    task = svc.cancel_task(task_id)
    if task is None:
        raise HTTPException(status_code=409, detail="dispatch_task_not_cancellable")
    return task


@router.post("/{task_id}/abort", response_model=DispatchTaskItem)
def abort_dispatch_task(task_id: str) -> DispatchTaskItem:
    svc = _get_dispatch_service()
    pool = _get_worker_pool()

    pool.cancel_task(task_id)

    task = svc.abort_task(task_id)
    if task is None:
        raise HTTPException(status_code=409, detail="dispatch_task_not_abortable")
    return task


@router.post("/emergency-stop", response_model=EmergencyStopResponse)
def emergency_stop(request: Request) -> EmergencyStopResponse:
    # Audit log: record caller IP and timestamp
    client_ip = request.client.host if request.client else "unknown"
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f"[AUDIT] emergency-stop called from {client_ip}")

    svc = _get_dispatch_service()
    pool = _get_worker_pool()

    pool.cancel_all()
    cancelled_count = svc.emergency_stop()
    logger.warning(f"[AUDIT] emergency-stop completed, cancelled {cancelled_count} tasks")
    return EmergencyStopResponse(cancelled_count=cancelled_count)

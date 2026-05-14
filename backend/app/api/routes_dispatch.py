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
    WorkSessionResponse,
)
from app.services.dispatch_service import DispatchService
from app.services.dispatch_worker import DispatchWorkerPool
from app.services.task_lifecycle import TaskLifecycleService

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


def _get_task_lifecycle_service() -> TaskLifecycleService:
    from app.main import app
    lifecycle = getattr(app.state, "task_lifecycle_service", None)
    if lifecycle is None:
        raise HTTPException(status_code=503, detail="task_lifecycle_service_unavailable")
    return lifecycle


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
    lifecycle = _get_task_lifecycle_service()

    if payload.task_board_item_id:
        active = svc.get_active_task_for_task_board_item(payload.task_board_item_id)
        if active is not None:
            return active

    task = svc.create_task(payload)

    updated = svc.transition_task(task.id, "running")
    if updated is None:
        raise HTTPException(status_code=500, detail="dispatch_transition_failed")

    if not lifecycle.start_task_safe(updated, task_board_item_id=payload.task_board_item_id):
        active = svc.get_active_task_for_task_board_item(payload.task_board_item_id or "")
        if active is not None:
            return active
        raise HTTPException(status_code=409, detail="dispatch_task_duplicate_active")
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
    lifecycle = _get_task_lifecycle_service()

    task = svc.resume_task(task_id, payload)
    if task is None:
        raise HTTPException(status_code=409, detail="dispatch_task_not_resumable")

    lifecycle.start_task_safe(task, task_board_item_id=task.task_board_item_id)
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


@router.get("/task-board/{task_board_item_id}/work-session", response_model=WorkSessionResponse)
def resolve_task_board_work_session(task_board_item_id: str) -> WorkSessionResponse:
    """Resolve the canonical work session for a task-board item.

    Returns the recommended action (resume/view_history/create_new) together
    with the active and latest dispatch tasks for this task-board item.
    Use this before creating a new dispatch to avoid duplicate execution.
    """
    svc = _get_dispatch_service()
    result = svc.resolve_work_session(task_board_item_id)
    active = result.get("active_dispatch_task")
    latest = result.get("latest_dispatch_task")
    return WorkSessionResponse(
        task_board_item_id=result["task_board_item_id"],
        recommended_action=result["recommended_action"],
        active_dispatch_task=active if isinstance(active, DispatchTaskItem) else None,
        latest_dispatch_task=latest if isinstance(latest, DispatchTaskItem) else None,
    )

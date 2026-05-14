from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query, Request

from app.schemas import (
    TaskBoardCreateRequest,
    TaskBoardListResponse,
    TaskBoardUpdateRequest,
)
from app.container import store

router = APIRouter(prefix="", tags=["task-board"])


@router.get("/api/v1/task-board", response_model=TaskBoardListResponse)
def list_task_board_items(
    project_id: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
) -> TaskBoardListResponse:
    return TaskBoardListResponse(items=store.list_task_board_items(project_id=project_id, keyword=keyword))


@router.post("/api/v1/task-board")
def create_task_board_item(payload: TaskBoardCreateRequest):
    try:
        return store.create_task_board_item(payload)
    except ValueError as exc:
        detail = str(exc)
        if detail in {
            "project_not_found",
            "upstream_task_not_found",
            "parent_task_not_found",
            "task_status_reason_required",
        }:
            raise HTTPException(status_code=422, detail=detail) from exc
        raise


@router.patch("/api/v1/task-board/{task_id}")
def update_task_board_item(task_id: str, payload: TaskBoardUpdateRequest):
    try:
        item = store.update_task_board_item(task_id, payload)
    except ValueError as exc:
        detail = str(exc)
        if detail in {
            "project_not_found",
            "upstream_task_not_found",
            "parent_task_not_found",
            "upstream_task_cannot_be_self",
            "parent_task_cannot_be_self",
            "task_status_reason_required",
        }:
            raise HTTPException(status_code=422, detail=detail) from exc
        raise
    if item is None:
        raise HTTPException(status_code=404, detail="task_board_item_not_found")
    return item


@router.patch("/api/v1/task-board/{task_id}/archive")
def archive_task_board_item(task_id: str, request: Request):
    lifecycle = getattr(request.app.state, "task_lifecycle_service", None)
    if lifecycle is None:
        raise HTTPException(status_code=503, detail="lifecycle_service_unavailable")
    ok = lifecycle.archive_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="task_board_item_not_found")
    return {"archived": 1, "task_id": task_id}


@router.patch("/api/v1/task-board/{task_id}/unarchive")
def unarchive_task_board_item(task_id: str):
    """Restore an archived task back to the active board."""
    item = store.update_task_board_item(task_id, TaskBoardUpdateRequest(archived=False))
    if item is None:
        raise HTTPException(status_code=404, detail="task_board_item_not_found")
    return item


@router.get("/api/v1/task-board/archived", response_model=TaskBoardListResponse)
def list_archived_task_board_items(
    project_id: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> TaskBoardListResponse:
    return TaskBoardListResponse(
        items=store.list_archived_task_board_items(
            project_id=project_id,
            keyword=keyword,
            status=status,
        )
    )

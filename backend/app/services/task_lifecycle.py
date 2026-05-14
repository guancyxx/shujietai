"""Task lifecycle coordination across task board and dispatch workers."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models import DispatchTaskEntity, TaskBoardEntity
from app.schemas import DispatchTaskItem
from app.services.dispatch_service import ACTIVE_DISPATCH_STATUSES, DispatchService, _entity_to_item

logger = logging.getLogger(__name__)

_CANCELLED_REVIEW_REASON = "Dispatch was cancelled; user review is required."


class WorkerPoolProtocol(Protocol):
    def cancel_task(self, task_id: str) -> bool: ...

    def start_task(self, task: DispatchTaskItem) -> None: ...


class TaskLifecycleService:
    """Coordinate task-board lifecycle rules with dispatch execution state."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker,
        dispatch_service: DispatchService,
        worker_pool: WorkerPoolProtocol,
    ) -> None:
        self._session_factory = session_factory
        self._dispatch_service = dispatch_service
        self._worker_pool = worker_pool

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    def _find_active_dispatch(self, task_board_item_id: str) -> DispatchTaskItem | None:
        try:
            return self._dispatch_service.get_active_task_for_task_board_item(task_board_item_id)
        except Exception:
            logger.warning(
                "Multiple active dispatch tasks detected for task_board_item=%s",
                task_board_item_id,
                exc_info=True,
            )
            with self._session_factory() as db:
                row = db.execute(
                    select(DispatchTaskEntity)
                    .where(
                        DispatchTaskEntity.task_board_item_id == task_board_item_id,
                        DispatchTaskEntity.status.in_(ACTIVE_DISPATCH_STATUSES),
                    )
                    .order_by(DispatchTaskEntity.created_at.asc())
                    .limit(1)
                ).scalar_one_or_none()
                return _entity_to_item(row) if row is not None else None

    def archive_task(self, task_board_item_id: str) -> bool:
        """Archive a task-board item and cancel any linked active dispatch task."""
        active = self._find_active_dispatch(task_board_item_id)
        if active is not None:
            self._worker_pool.cancel_task(active.id)
            self._dispatch_service.cancel_task(active.id)
            logger.info(
                "Archived task_board_item=%s after cancelling dispatch_task=%s",
                task_board_item_id,
                active.id,
            )

        with self._session_factory.begin() as db:
            entity = db.get(TaskBoardEntity, task_board_item_id)
            if entity is None:
                return False
            entity.archived = True
            entity.archived_at = self._now()
            entity.updated_at = self._now()
            return True

    def start_task_safe(self, task: DispatchTaskItem, *, task_board_item_id: str | None = None) -> bool:
        """Start a dispatch task only when no sibling active task is already running."""
        item_id = (task_board_item_id or task.task_board_item_id or "").strip()
        if item_id:
            active = self._find_active_dispatch(item_id)
            if active is not None and active.id != task.id:
                logger.info(
                    "Skip dispatch_task=%s because task_board_item=%s already has active dispatch_task=%s",
                    task.id,
                    item_id,
                    active.id,
                )
                return False
        self._worker_pool.start_task(task)
        return True

    def cleanup_cancelled_tasks(self) -> int:
        """Reconcile cancelled dispatch tasks to blocked task-board state for review."""
        with self._session_factory() as db:
            rows = db.execute(
                select(DispatchTaskEntity).where(DispatchTaskEntity.status == "cancelled")
            ).scalars().all()
            candidates = [(row.id, row.task_board_item_id) for row in rows if row.task_board_item_id]

        reconciled = 0
        for dispatch_task_id, item_id in candidates:
            with self._session_factory.begin() as db:
                task_board_item = db.get(TaskBoardEntity, item_id)
                if task_board_item is None or task_board_item.archived:
                    continue
                if task_board_item.status in {"completed", "blocked"}:
                    continue
                task_board_item.status = "blocked"
                task_board_item.status_reason = _CANCELLED_REVIEW_REASON
                task_board_item.updated_at = self._now()
                reconciled += 1
                logger.info(
                    "Reconciled cancelled dispatch_task=%s to blocked task_board_item=%s",
                    dispatch_task_id,
                    item_id,
                )
        return reconciled

    def has_active_dispatch_for_task_board_item(self, task_board_item_id: str) -> bool:
        """Return whether a task-board item currently has active dispatch execution."""
        return self._find_active_dispatch(task_board_item_id) is not None

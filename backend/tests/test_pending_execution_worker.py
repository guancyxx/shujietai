from __future__ import annotations

from app.schemas import TaskBoardCreateRequest
from app.services.dispatch_service import DispatchService
from app.services.pending_execution_worker import process_pending_execution_once
from app.services.sqlalchemy_store import SqlAlchemySessionStore


class _FakeWorkerPool:
    def __init__(self) -> None:
        self.started_task_ids: list[str] = []

    def start_task(self, task) -> None:
        self.started_task_ids.append(task.id)


def _make_services() -> tuple[SqlAlchemySessionStore, DispatchService]:
    store = SqlAlchemySessionStore("sqlite+pysqlite:///:memory:")
    return store, DispatchService(store.session_factory)


def test_pending_execution_worker_starts_dispatch_once_and_marks_in_progress() -> None:
    store, dispatch_service = _make_services()
    task_board_item = store.create_task_board_item(
        TaskBoardCreateRequest(
            name="Implement drawing fix",
            description="AI should respond after a completed drawing reply.",
            status="pending_execution",
            priority=1,
        )
    )
    pool = _FakeWorkerPool()

    first_count = process_pending_execution_once(dispatch_service=dispatch_service, worker_pool=pool)
    second_count = process_pending_execution_once(dispatch_service=dispatch_service, worker_pool=pool)

    assert first_count == 1
    assert second_count == 0
    assert len(dispatch_service.list_tasks()) == 1
    assert len(pool.started_task_ids) == 1
    updated = store.list_task_board_items()[0]
    assert str(updated.id) == str(task_board_item.id)
    assert updated.status == "in_progress"


def test_pending_execution_worker_reuses_existing_active_dispatch() -> None:
    store, dispatch_service = _make_services()
    task_board_item = store.create_task_board_item(
        TaskBoardCreateRequest(
            name="Continue existing task",
            description="Do not duplicate active dispatch.",
            status="pending_execution",
        )
    )
    existing = dispatch_service.create_task_for_task_board_item(str(task_board_item.id))
    assert existing is not None
    pool = _FakeWorkerPool()

    started_count = process_pending_execution_once(dispatch_service=dispatch_service, worker_pool=pool)

    assert started_count == 0
    assert pool.started_task_ids == [existing.id]
    assert len(dispatch_service.list_tasks()) == 1
    assert store.list_task_board_items()[0].status == "in_progress"

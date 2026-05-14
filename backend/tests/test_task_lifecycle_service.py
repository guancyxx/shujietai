from __future__ import annotations

from app.schemas import TaskBoardCreateRequest
from app.services.dispatch_service import DispatchService
from app.services.sqlalchemy_store import SqlAlchemySessionStore
from app.services.task_lifecycle import TaskLifecycleService


class _FakeWorkerPool:
    def __init__(self) -> None:
        self.cancelled_task_ids: list[str] = []
        self.started_task_ids: list[str] = []

    def cancel_task(self, task_id: str) -> bool:
        self.cancelled_task_ids.append(task_id)
        return True

    def start_task(self, task) -> None:
        self.started_task_ids.append(task.id)


def _make_services() -> tuple[SqlAlchemySessionStore, DispatchService, _FakeWorkerPool, TaskLifecycleService]:
    store = SqlAlchemySessionStore("sqlite+pysqlite:///:memory:")
    dispatch_service = DispatchService(store.session_factory)
    worker_pool = _FakeWorkerPool()
    lifecycle = TaskLifecycleService(
        session_factory=store.session_factory,
        dispatch_service=dispatch_service,
        worker_pool=worker_pool,
    )
    return store, dispatch_service, worker_pool, lifecycle


def test_archive_task_cancels_active_dispatch_and_hides_task_board_item() -> None:
    store, dispatch_service, worker_pool, lifecycle = _make_services()
    item = store.create_task_board_item(
        TaskBoardCreateRequest(
            name="Running task",
            description="Should cancel before archive.",
            status="in_progress",
        )
    )
    task = dispatch_service.create_task_for_task_board_item(str(item.id))
    assert task is not None
    dispatch_service.transition_task(task.id, "running")

    result = lifecycle.archive_task(str(item.id))

    assert result is True
    assert worker_pool.cancelled_task_ids == [task.id]
    assert dispatch_service.get_task(task.id).status == "cancelled"
    assert store.list_task_board_items() == []
    archived = store.list_archived_task_board_items()
    assert len(archived) == 1
    assert archived[0].id == item.id
    assert archived[0].archived is True


def test_archive_task_without_active_dispatch_only_archives() -> None:
    store, _dispatch_service, worker_pool, lifecycle = _make_services()
    item = store.create_task_board_item(
        TaskBoardCreateRequest(
            name="Draft task",
            description="Archive only.",
            status="draft",
        )
    )

    assert lifecycle.archive_task(str(item.id)) is True
    assert worker_pool.cancelled_task_ids == []
    assert store.list_task_board_items() == []
    assert len(store.list_archived_task_board_items()) == 1


def test_start_task_safe_skips_duplicate_active_dispatch_for_same_task_board_item() -> None:
    store, dispatch_service, worker_pool, lifecycle = _make_services()
    item = store.create_task_board_item(
        TaskBoardCreateRequest(
            name="Duplicate risk",
            description="Do not start second active dispatch.",
            status="in_progress",
        )
    )
    existing = dispatch_service.create_task_for_task_board_item(str(item.id))
    assert existing is not None
    dispatch_service.transition_task(existing.id, "running")
    duplicate = dispatch_service.create_task_for_task_board_item(str(item.id))
    assert duplicate is not None

    assert lifecycle.start_task_safe(duplicate, task_board_item_id=str(item.id)) is False
    assert worker_pool.started_task_ids == []


def test_start_task_safe_starts_when_no_duplicate_active_dispatch() -> None:
    store, dispatch_service, worker_pool, lifecycle = _make_services()
    item = store.create_task_board_item(
        TaskBoardCreateRequest(
            name="Safe start",
            description="No duplicate.",
            status="pending_execution",
        )
    )
    task = dispatch_service.create_task_for_task_board_item(str(item.id))
    assert task is not None

    assert lifecycle.start_task_safe(task, task_board_item_id=str(item.id)) is True
    assert worker_pool.started_task_ids == [task.id]


def test_cleanup_cancelled_tasks_marks_linked_task_blocked() -> None:
    store, dispatch_service, _worker_pool, lifecycle = _make_services()
    item = store.create_task_board_item(
        TaskBoardCreateRequest(
            name="Cancelled task",
            description="Should become blocked for review.",
            status="cancelled",
            status_reason="User cancelled test task.",
        )
    )
    task = dispatch_service.create_task_for_task_board_item(str(item.id))
    assert task is not None
    dispatch_service.transition_task(task.id, "running")
    dispatch_service.cancel_task(task.id)

    assert lifecycle.cleanup_cancelled_tasks() == 1
    updated = [entry for entry in store.list_task_board_items() if entry.status == "blocked"][0]
    assert updated.id == item.id
    assert updated.status_reason == "Dispatch was cancelled; user review is required."

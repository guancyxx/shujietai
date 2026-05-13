"""Background worker for task-board items waiting for automatic AI execution."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.schemas import IngestEventRequest, normalize_platform
from app.services.dispatch_service import DispatchService
from app.services.dispatch_worker import DispatchWorkerPool

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PendingExecutionWorkerConfig:
    enabled: bool = True
    loop_interval_seconds: float = 2.0
    batch_size: int = 20


async def run_pending_execution_loop(
    *,
    dispatch_service: DispatchService,
    worker_pool: DispatchWorkerPool,
    config: PendingExecutionWorkerConfig,
    ingest_fn: Callable[..., object] | None = None,
) -> None:
    """Scan task-board pending_execution rows and start exactly one dispatch run for each."""
    if not config.enabled:
        return

    while True:
        try:
            process_pending_execution_once(
                dispatch_service=dispatch_service,
                worker_pool=worker_pool,
                limit=config.batch_size,
                ingest_fn=ingest_fn,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Pending-execution worker tick failed: %s", exc)
        await asyncio.sleep(config.loop_interval_seconds)


def _ingest_session_for_task(
    *,
    ingest_fn: Callable[..., object],
    dispatch_task_item,
    task_board_item,
    prompt: str,
) -> None:
    """Create a session record so the conversation appears in the chat session list."""
    external_session_id = (
        dispatch_task_item.external_session_id or dispatch_task_item.id
    )
    try:
        ingest_fn(
            IngestEventRequest(
                platform=normalize_platform(task_board_item.ai_platform),
                event_id=f"evt_init_{dispatch_task_item.id}",
                event_type="session_started",
                external_session_id=external_session_id,
                title=task_board_item.name,
                payload_json={
                    "source": "pending_execution_worker",
                    "task_board_item_id": str(task_board_item.id),
                    "dispatch_task_id": dispatch_task_item.id,
                },
                message={"role": "user", "content": prompt},
            )
        )
        ingest_fn(
            IngestEventRequest(
                platform=normalize_platform(task_board_item.ai_platform),
                event_id=f"evt_progress_{dispatch_task_item.id}",
                event_type="dispatch_created",
                external_session_id=external_session_id,
                title=task_board_item.name,
                payload_json={
                    "source": "pending_execution_worker",
                    "status": "running",
                    "dispatch_task_id": dispatch_task_item.id,
                },
                message={
                    "role": "system",
                    "content": "🔄 已提交 Dispatch 任务，等待 AI Agent 处理中...",
                },
            )
        )
    except Exception as exc:
        logger.exception(
            "Failed to ingest session for task_board_item=%s: %s",
            task_board_item.id,
            exc,
        )


def process_pending_execution_once(
    *,
    dispatch_service: DispatchService,
    worker_pool: DispatchWorkerPool,
    limit: int = 20,
    ingest_fn: Callable[..., object] | None = None,
) -> int:
    """Start dispatch tasks for pending task-board items and return start count."""
    started_count = 0
    pending_items = dispatch_service.list_pending_execution_task_board_items(limit=limit)
    for item in pending_items:
        item_id = str(item.id)
        existing = dispatch_service.get_active_task_for_task_board_item(item_id)
        if existing is not None:
            dispatch_service.mark_task_board_item_status(item_id, "in_progress")
            # Ensure session exists for this existing dispatch task
            if ingest_fn is not None:
                prompt = item.description or f"Continue task: {item.name}"
                _ingest_session_for_task(
                    ingest_fn=ingest_fn,
                    dispatch_task_item=existing,
                    task_board_item=item,
                    prompt=prompt,
                )
            worker_pool.start_task(existing)
            continue

        task = dispatch_service.create_task_for_task_board_item(item_id)
        if task is None:
            continue
        dispatch_service.mark_task_board_item_status(item_id, "in_progress")

        # Create session record so the conversation appears in the chat list
        if ingest_fn is not None:
            prompt = item.description or f"Execute task: {item.name}"
            _ingest_session_for_task(
                ingest_fn=ingest_fn,
                dispatch_task_item=task,
                task_board_item=item,
                prompt=prompt,
            )

        worker_pool.start_task(task)
        started_count += 1
    return started_count

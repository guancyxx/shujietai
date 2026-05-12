"""Background worker for task-board items waiting for automatic AI execution."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

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
) -> None:
    """Scan task-board pending_execution rows and start exactly one dispatch run for each."""
    if not config.enabled:
        return

    while True:
        try:
            await process_pending_execution_once(
                dispatch_service=dispatch_service,
                worker_pool=worker_pool,
                limit=config.batch_size,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Pending-execution worker tick failed: %s", exc)
        await asyncio.sleep(config.loop_interval_seconds)


def process_pending_execution_once(
    *,
    dispatch_service: DispatchService,
    worker_pool: DispatchWorkerPool,
    limit: int = 20,
) -> int:
    """Start dispatch tasks for pending task-board items and return start count."""
    started_count = 0
    pending_items = dispatch_service.list_pending_execution_task_board_items(limit=limit)
    for item in pending_items:
        item_id = str(item.id)
        existing = dispatch_service.get_active_task_for_task_board_item(item_id)
        if existing is not None:
            dispatch_service.mark_task_board_item_status(item_id, "in_progress")
            worker_pool.start_task(existing)
            continue

        task = dispatch_service.create_task_for_task_board_item(item_id)
        if task is None:
            continue
        dispatch_service.mark_task_board_item_status(item_id, "in_progress")
        worker_pool.start_task(task)
        started_count += 1
    return started_count

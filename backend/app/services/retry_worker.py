from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from app.services.ingest_retry_service import IngestRetryService, RetryProcessingResult


@dataclass
class RetryWorkerConfig:
    enabled: bool
    loop_interval_seconds: float
    max_retries: int
    backoff_seconds: list[int]


async def run_retry_loop(
    retry_service: IngestRetryService,
    ingest_callable,
    config: RetryWorkerConfig,
    on_tick=None,
) -> None:
    if not config.enabled:
        return

    while True:
        tick_result = retry_service.process_due_retries(
            ingest_callable=ingest_callable,
            now=datetime.now(UTC),
            max_retries=config.max_retries,
            backoff_seconds=config.backoff_seconds,
        )
        if on_tick is not None:
            on_tick(tick_result)
        await asyncio.sleep(config.loop_interval_seconds)


def default_tick_hook(_: RetryProcessingResult) -> None:
    return

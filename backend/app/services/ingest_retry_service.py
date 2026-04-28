from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import DeadLetterEventEntity, IngestRetryEntity
from app.schemas import DeadLetterItem, IngestEventRequest


@dataclass
class DeadLetterQuery:
    limit: int = 50
    only_unreplayed: bool = False
    platform: str | None = None
    since: datetime | None = None


@dataclass
class RetryProcessingResult:
    retried_count: int = 0
    succeeded_count: int = 0
    dead_letter_count: int = 0


@dataclass
class RetryQueueStats:
    pending_count: int
    dead_letter_count: int


@dataclass
class DeadLetterReplayResult:
    status: str
    detail: str


class IngestRetryService:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    def enqueue_failed_ingest(self, payload: IngestEventRequest, request_id: str, error_message: str) -> None:
        now = self._now()
        with self._session_factory.begin() as db:
            existing = db.get(IngestRetryEntity, payload.event_id)
            if existing is not None:
                existing.last_error = error_message[:2000]
                existing.updated_at = now
                existing.status = "pending"
                return

            db.add(
                IngestRetryEntity(
                    event_id=payload.event_id,
                    platform=payload.platform,
                    external_session_id=payload.external_session_id,
                    event_type=payload.event_type,
                    title=payload.title,
                    payload_json=payload.payload_json,
                    message_json=payload.message.model_dump() if payload.message is not None else None,
                    task_json=payload.task.model_dump() if payload.task is not None else None,
                    request_id=request_id,
                    attempt_count=0,
                    status="pending",
                    last_error=error_message[:2000],
                    next_retry_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )

    def process_due_retries(
        self,
        ingest_callable,
        now: datetime | None = None,
        max_retries: int = 3,
        backoff_seconds: list[int] | None = None,
    ) -> RetryProcessingResult:
        run_time = now or self._now()
        backoff = backoff_seconds or [1, 3, 10]
        result = RetryProcessingResult()

        with self._session_factory.begin() as db:
            due_rows = db.execute(
                select(IngestRetryEntity)
                .where(IngestRetryEntity.status == "pending")
                .where(IngestRetryEntity.next_retry_at <= run_time)
                .order_by(IngestRetryEntity.created_at.asc())
            ).scalars().all()

            for row in due_rows:
                payload = self._build_ingest_payload(
                    platform=row.platform,
                    event_id=row.event_id,
                    event_type=row.event_type,
                    external_session_id=row.external_session_id,
                    title=row.title,
                    payload_json=row.payload_json,
                    message_json=row.message_json,
                    task_json=row.task_json,
                )
                try:
                    ingest_callable(payload)
                    row.status = "succeeded"
                    row.updated_at = run_time
                    result.succeeded_count += 1
                except Exception as exc:  # noqa: BLE001
                    row.attempt_count += 1
                    row.last_error = str(exc)[:2000]
                    row.updated_at = run_time
                    if row.attempt_count >= max_retries:
                        self._move_to_dead_letter(db=db, row=row, error_message=row.last_error or "retry_failed")
                        db.delete(row)
                        result.dead_letter_count += 1
                        continue

                    delay_idx = min(row.attempt_count - 1, len(backoff) - 1)
                    row.next_retry_at = run_time + timedelta(seconds=backoff[delay_idx])
                    row.status = "pending"
                    result.retried_count += 1

        return result

    def _move_to_dead_letter(self, db: Session, row: IngestRetryEntity, error_message: str) -> None:
        db.add(
            DeadLetterEventEntity(
                id=f"dlq_{uuid4().hex[:12]}",
                event_id=row.event_id,
                platform=row.platform,
                external_session_id=row.external_session_id,
                event_type=row.event_type,
                request_id=row.request_id,
                payload_json=row.payload_json or {},
                message_json=row.message_json,
                task_json=row.task_json,
                error_message=error_message,
                attempt_count=row.attempt_count,
                created_at=self._now(),
            )
        )

    def inspect_stats(self) -> RetryQueueStats:
        with self._session_factory() as db:
            pending_count = db.execute(
                select(func.count()).select_from(IngestRetryEntity).where(IngestRetryEntity.status == "pending")
            ).scalar_one()
            dead_letter_count = db.execute(select(func.count()).select_from(DeadLetterEventEntity)).scalar_one()
            return RetryQueueStats(pending_count=int(pending_count), dead_letter_count=int(dead_letter_count))

    def list_dead_letters(self, query: DeadLetterQuery) -> list[DeadLetterItem]:
        safe_limit = max(1, min(query.limit, 200))
        with self._session_factory() as db:
            stmt = select(DeadLetterEventEntity).order_by(DeadLetterEventEntity.created_at.desc())
            if query.only_unreplayed:
                stmt = stmt.where(DeadLetterEventEntity.replayed_at.is_(None))
            if query.platform:
                stmt = stmt.where(DeadLetterEventEntity.platform == query.platform)
            if query.since is not None:
                stmt = stmt.where(DeadLetterEventEntity.created_at >= query.since)

            rows = db.execute(stmt.limit(safe_limit)).scalars().all()
            return [self._dead_letter_entity_to_item(row) for row in rows]

    def replay_dead_letter(self, dlq_id: str, ingest_callable, replayed_by: str, force: bool = False) -> DeadLetterReplayResult:
        with self._session_factory.begin() as db:
            row = db.get(DeadLetterEventEntity, dlq_id)
            if row is None:
                return DeadLetterReplayResult(status="failed", detail="dead_letter_not_found")
            if row.replayed_at is not None and not force:
                return DeadLetterReplayResult(status="failed", detail="dead_letter_already_replayed")

            payload = self._build_ingest_payload(
                platform=row.platform,
                event_id=row.event_id,
                event_type=row.event_type,
                external_session_id=row.external_session_id,
                title=None,
                payload_json=row.payload_json,
                message_json=row.message_json,
                task_json=row.task_json,
            )

            try:
                ingest_callable(payload)
            except Exception as exc:  # noqa: BLE001
                return DeadLetterReplayResult(status="failed", detail=str(exc)[:2000])

            row.replay_count += 1
            row.replayed_at = self._now()
            row.replayed_by = replayed_by[:128]
            return DeadLetterReplayResult(status="replayed", detail="ok")

    @staticmethod
    def _build_ingest_payload(
        platform: str,
        event_id: str,
        event_type: str,
        external_session_id: str,
        title: str | None,
        payload_json: dict | None,
        message_json: dict | None,
        task_json: dict | None,
    ) -> IngestEventRequest:
        return IngestEventRequest(
            platform=platform,
            event_id=event_id,
            event_type=event_type,
            external_session_id=external_session_id,
            title=title,
            payload_json=payload_json or {},
            message=message_json,
            task=task_json,
        )

    @staticmethod
    def _dead_letter_entity_to_item(entity: DeadLetterEventEntity) -> DeadLetterItem:
        return DeadLetterItem(
            id=entity.id,
            event_id=entity.event_id,
            platform=entity.platform,
            external_session_id=entity.external_session_id,
            event_type=entity.event_type,
            request_id=entity.request_id,
            payload_json=entity.payload_json or {},
            message_json=entity.message_json,
            task_json=entity.task_json,
            error_message=entity.error_message,
            attempt_count=entity.attempt_count,
            replay_count=entity.replay_count,
            replayed_at=entity.replayed_at,
            replayed_by=entity.replayed_by,
            created_at=entity.created_at,
        )

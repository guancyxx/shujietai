from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.schemas import IngestEventRequest
from app.services.ingest_retry_service import DeadLetterQuery, IngestRetryService
from app.services.sqlalchemy_store import SqlAlchemySessionStore


class _AlwaysFailIngest:
    def __call__(self, payload: IngestEventRequest):
        raise RuntimeError("transient_fail")


def _sample_payload(event_id: str) -> IngestEventRequest:
    return IngestEventRequest(
        platform="hermes",
        event_id=event_id,
        event_type="message_created",
        external_session_id=f"ext_{event_id}",
        title="retry",
        payload_json={"source": "retry-test"},
        message={"role": "user", "content": "hello"},
    )


def _seed_one_dlq(service: IngestRetryService, event_id: str) -> str:
    payload = _sample_payload(event_id)
    service.enqueue_failed_ingest(payload=payload, request_id=f"req_{event_id}", error_message="boom")

    fail_ingest = _AlwaysFailIngest()
    base_now = datetime.now(UTC)
    schedule = [base_now, base_now + timedelta(seconds=2), base_now + timedelta(seconds=6)]
    for tick in schedule:
        service.process_due_retries(ingest_callable=fail_ingest, now=tick, max_retries=3, backoff_seconds=[1, 3, 10])

    return service.list_dead_letters(query=DeadLetterQuery(limit=1))[0].id


def test_replay_not_found() -> None:
    store = SqlAlchemySessionStore("sqlite+pysqlite:///:memory:")
    service = IngestRetryService(store.session_factory)

    result = service.replay_dead_letter(
        dlq_id="missing",
        ingest_callable=store.ingest,
        replayed_by="ops",
    )
    assert result.status == "failed"
    assert result.detail == "dead_letter_not_found"


def test_replay_fail_then_success_then_already_then_force(tmp_path) -> None:
    db_url = f"sqlite+pysqlite:///{tmp_path / 'retry_replay_semantics.db'}"
    store = SqlAlchemySessionStore(db_url)
    service = IngestRetryService(store.session_factory)

    dlq_id = _seed_one_dlq(service, "evt_replay_semantics")

    def always_fail(_: IngestEventRequest):
        raise RuntimeError("replay_boom")

    replay_fail = service.replay_dead_letter(
        dlq_id=dlq_id,
        ingest_callable=always_fail,
        replayed_by="ops",
    )
    assert replay_fail.status == "failed"
    assert "replay_boom" in replay_fail.detail

    replay_ok = service.replay_dead_letter(
        dlq_id=dlq_id,
        ingest_callable=store.ingest,
        replayed_by="ops",
    )
    assert replay_ok.status == "replayed"

    already = service.replay_dead_letter(
        dlq_id=dlq_id,
        ingest_callable=store.ingest,
        replayed_by="ops",
    )
    assert already.status == "failed"
    assert already.detail == "dead_letter_already_replayed"

    force_again = service.replay_dead_letter(
        dlq_id=dlq_id,
        ingest_callable=store.ingest,
        replayed_by="ops",
        force=True,
    )
    assert force_again.status == "replayed"

    row = service.list_dead_letters(query=DeadLetterQuery(limit=1))[0]
    assert row.replay_count == 2
    assert row.replayed_at is not None
    assert row.replayed_by == "ops"

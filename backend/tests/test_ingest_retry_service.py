from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.schemas import IngestEventRequest
from app.services.ingest_retry_service import DeadLetterQuery, IngestRetryService
from app.services.sqlalchemy_store import SqlAlchemySessionStore


class _FlakyIngest:
    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls = 0

    def __call__(self, payload: IngestEventRequest) -> tuple[str, bool]:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("transient_fail")
        return "sess_ok", False


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


def test_retry_service_retries_then_succeeds(tmp_path) -> None:
    db_url = f"sqlite+pysqlite:///{tmp_path / 'retry_success.db'}"
    store = SqlAlchemySessionStore(db_url)
    service = IngestRetryService(store.session_factory)

    payload = _sample_payload("evt_retry_success")
    service.enqueue_failed_ingest(payload=payload, request_id="req-1", error_message="boom")

    flaky = _FlakyIngest(fail_times=1)
    base_now = datetime.now(UTC)
    first = service.process_due_retries(ingest_callable=flaky, now=base_now, max_retries=3, backoff_seconds=[1, 3, 10])
    assert first.retried_count == 1
    assert first.succeeded_count == 0
    assert first.dead_letter_count == 0

    second = service.process_due_retries(
        ingest_callable=flaky,
        now=base_now + timedelta(seconds=2),
        max_retries=3,
        backoff_seconds=[1, 3, 10],
    )
    assert second.retried_count == 0
    assert second.succeeded_count == 1
    assert second.dead_letter_count == 0


def test_retry_service_moves_to_dlq_after_max_retries(tmp_path) -> None:
    db_url = f"sqlite+pysqlite:///{tmp_path / 'retry_dlq.db'}"
    store = SqlAlchemySessionStore(db_url)
    service = IngestRetryService(store.session_factory)

    payload = _sample_payload("evt_retry_dlq")
    service.enqueue_failed_ingest(payload=payload, request_id="req-2", error_message="boom")

    flaky = _FlakyIngest(fail_times=99)
    base_now = datetime.now(UTC)
    schedule = [base_now, base_now + timedelta(seconds=2), base_now + timedelta(seconds=6)]
    for tick in schedule:
        service.process_due_retries(ingest_callable=flaky, now=tick, max_retries=3, backoff_seconds=[1, 3, 10])

    stats = service.inspect_stats()
    assert stats.pending_count == 0
    assert stats.dead_letter_count == 1


def test_retry_service_lists_dead_letters_and_replays_success(tmp_path) -> None:
    db_url = f"sqlite+pysqlite:///{tmp_path / 'retry_dlq_replay_ok.db'}"
    store = SqlAlchemySessionStore(db_url)
    service = IngestRetryService(store.session_factory)

    payload = _sample_payload("evt_retry_replay_ok")
    service.enqueue_failed_ingest(payload=payload, request_id="req-3", error_message="boom")

    flaky = _FlakyIngest(fail_times=99)
    base_now = datetime.now(UTC)
    schedule = [base_now, base_now + timedelta(seconds=2), base_now + timedelta(seconds=6)]
    for tick in schedule:
        service.process_due_retries(ingest_callable=flaky, now=tick, max_retries=3, backoff_seconds=[1, 3, 10])

    items = service.list_dead_letters(query=DeadLetterQuery(limit=10))
    assert len(items) == 1
    dlq_id = items[0].id

    replay_result = service.replay_dead_letter(dlq_id=dlq_id, ingest_callable=store.ingest, replayed_by="test-user")
    assert replay_result.status == "replayed"
    assert replay_result.detail == "ok"

    after_replay = service.list_dead_letters(query=DeadLetterQuery(limit=10))
    assert len(after_replay) == 1
    assert after_replay[0].id == dlq_id
    assert after_replay[0].replay_count == 1
    assert after_replay[0].replayed_at is not None
    assert after_replay[0].replayed_by == "test-user"


def test_retry_service_list_dead_letters_filters(tmp_path) -> None:
    db_url = f"sqlite+pysqlite:///{tmp_path / 'retry_dlq_filters.db'}"
    store = SqlAlchemySessionStore(db_url)
    service = IngestRetryService(store.session_factory)

    payload1 = _sample_payload("evt_dlq_filter_1")
    payload2 = IngestEventRequest(
        platform="discord",
        event_id="evt_dlq_filter_2",
        event_type="message_created",
        external_session_id="ext_evt_dlq_filter_2",
        title="retry",
        payload_json={"source": "retry-test"},
        message={"role": "user", "content": "hello"},
    )
    service.enqueue_failed_ingest(payload=payload1, request_id="req-f1", error_message="boom")
    service.enqueue_failed_ingest(payload=payload2, request_id="req-f2", error_message="boom")

    flaky = _FlakyIngest(fail_times=99)
    base_now = datetime.now(UTC)
    schedule = [base_now, base_now + timedelta(seconds=2), base_now + timedelta(seconds=6)]
    for tick in schedule:
        service.process_due_retries(ingest_callable=flaky, now=tick, max_retries=3, backoff_seconds=[1, 3, 10])

    all_items = service.list_dead_letters(query=DeadLetterQuery(limit=10))
    assert len(all_items) == 2

    hermes_only = service.list_dead_letters(query=DeadLetterQuery(limit=10, platform="hermes"))
    assert len(hermes_only) == 1
    assert hermes_only[0].platform == "hermes"

    since_future = service.list_dead_letters(
        query=DeadLetterQuery(limit=10, since=base_now + timedelta(days=1))
    )
    assert since_future == []

    replayed_id = hermes_only[0].id
    replay_result = service.replay_dead_letter(
        dlq_id=replayed_id,
        ingest_callable=store.ingest,
        replayed_by="ops",
    )
    assert replay_result.status == "replayed"

    unreplayed = service.list_dead_letters(query=DeadLetterQuery(limit=10, only_unreplayed=True))
    assert len(unreplayed) == 1
    assert unreplayed[0].platform == "discord"

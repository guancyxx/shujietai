from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import DeadLetterItem, IngestEventRequest
from app.services.ingest_retry_service import DeadLetterReplayResult

client = TestClient(app)


class _DlqRow:
    def __init__(self, row_id: str) -> None:
        self.id = row_id
        self.event_id = "evt_dlq_1"
        self.platform = "hermes"
        self.external_session_id = "ext_dlq_1"
        self.event_type = "message_created"
        self.request_id = "req_dlq_1"
        self.payload_json = {"source": "test"}
        self.message_json = {"role": "user", "content": "hello"}
        self.task_json = None
        self.error_message = "final_fail"
        self.attempt_count = 3
        self.replay_count = 0
        self.replayed_at = None
        self.replayed_by = None
        self.created_at = datetime.now(UTC)


class _RetryServiceStub:
    def __init__(self) -> None:
        self.last_query = None

    def list_dead_letters(self, query):
        self.last_query = query
        return [
            DeadLetterItem(**_DlqRow("dlq_1").__dict__),
            DeadLetterItem(**_DlqRow("dlq_2").__dict__),
        ][:query.limit]

    def replay_dead_letter(self, dlq_id: str, ingest_callable, replayed_by: str, force: bool = False):
        if dlq_id == "missing":
            return DeadLetterReplayResult(status="failed", detail="dead_letter_not_found")
        if dlq_id == "already" and not force:
            return DeadLetterReplayResult(status="failed", detail="dead_letter_already_replayed")
        if dlq_id == "conflict":
            return DeadLetterReplayResult(status="failed", detail="ingest_conflict")
        payload = IngestEventRequest(
            platform="hermes",
            event_id=f"evt_{dlq_id}",
            event_type="message_created",
            external_session_id=f"ext_{dlq_id}",
            title="replay",
            payload_json={},
            message={"role": "user", "content": "x"},
        )
        ingest_callable(payload)
        return DeadLetterReplayResult(status="replayed", detail="ok")


class _StoreStub:
    def __init__(self) -> None:
        self.ingest_calls = 0

    def ingest(self, payload: IngestEventRequest):
        self.ingest_calls += 1
        return "sess_stub", False


def test_dlq_list_success(monkeypatch) -> None:
    stub = _RetryServiceStub()
    monkeypatch.setattr("app.main.retry_service", stub)

    response = client.get(
        "/api/v1/dlq",
        params={
            "limit": 2,
            "only_unreplayed": "true",
            "platform": "hermes",
            "since": "2026-01-01T00:00:00Z",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 2
    assert payload["items"][0]["id"] == "dlq_1"
    assert stub.last_query.limit == 2
    assert stub.last_query.only_unreplayed is True
    assert stub.last_query.platform == "hermes"
    assert stub.last_query.since is not None


def test_dlq_replay_success(monkeypatch) -> None:
    store_stub = _StoreStub()
    monkeypatch.setattr("app.main.store", store_stub)
    monkeypatch.setattr("app.main.retry_service", _RetryServiceStub())

    response = client.post("/api/v1/dlq/dlq_ok/replay", headers={"x-replayed-by": "ops-user"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "dlq_ok"
    assert payload["status"] == "replayed"
    assert store_stub.ingest_calls == 1


def test_dlq_replay_not_found(monkeypatch) -> None:
    monkeypatch.setattr("app.main.retry_service", _RetryServiceStub())

    response = client.post("/api/v1/dlq/missing/replay")
    assert response.status_code == 404
    assert response.json()["detail"] == "dead_letter_not_found"


def test_dlq_replay_conflict(monkeypatch) -> None:
    monkeypatch.setattr("app.main.retry_service", _RetryServiceStub())

    response = client.post("/api/v1/dlq/conflict/replay")
    assert response.status_code == 409
    assert response.json()["detail"] == "ingest_conflict"


def test_dlq_replay_already_replayed(monkeypatch) -> None:
    monkeypatch.setattr("app.main.retry_service", _RetryServiceStub())

    response = client.post("/api/v1/dlq/already/replay")
    assert response.status_code == 409
    assert response.json()["detail"] == "dead_letter_already_replayed"


def test_dlq_replay_force_allows_rerun(monkeypatch) -> None:
    store_stub = _StoreStub()
    monkeypatch.setattr("app.main.store", store_stub)
    monkeypatch.setattr("app.main.retry_service", _RetryServiceStub())

    response = client.post(
        "/api/v1/dlq/already/replay",
        json={"force": True},
        headers={"x-replayed-by": "ops-user"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "replayed"
    assert store_stub.ingest_calls == 1


def test_dlq_list_invalid_since(monkeypatch) -> None:
    monkeypatch.setattr("app.main.retry_service", _RetryServiceStub())

    response = client.get("/api/v1/dlq", params={"since": "not-a-datetime"})
    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_since"

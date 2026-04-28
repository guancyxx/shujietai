from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import IngestEventRequest

client = TestClient(app)


def test_ingest_failure_enqueues_retry(monkeypatch) -> None:
    class _BoomStore:
        def ingest(self, payload: IngestEventRequest):
            raise RuntimeError("boom")

        def list_sessions(self):
            return []

        def get_session(self, session_id: str):
            return None

        def get_timeline(self, session_id: str):
            return None

        def get_history_messages(self, platform: str, external_session_id: str):
            return []

    class _RetryServiceStub:
        def __init__(self) -> None:
            self.calls = 0

        def enqueue_failed_ingest(self, payload: IngestEventRequest, request_id: str, error_message: str) -> None:
            self.calls += 1
            assert payload.event_id == "evt_fail_1"
            assert request_id
            assert "boom" in error_message

    retry_stub = _RetryServiceStub()

    monkeypatch.setattr("app.main.store", _BoomStore())
    monkeypatch.setattr("app.main.retry_service", retry_stub)

    response = client.post(
        "/api/v1/events/ingest",
        json={
            "platform": "hermes",
            "event_id": "evt_fail_1",
            "event_type": "message_created",
            "external_session_id": "sess_fail_1",
            "title": "fail",
            "payload_json": {},
            "message": {"role": "user", "content": "x"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"].startswith("pending_")
    assert retry_stub.calls == 1

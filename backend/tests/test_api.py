from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"


def test_list_sessions_returns_seed_data() -> None:
    response = client.get("/api/v1/sessions")
    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) >= 1
    assert any(s["id"] == "sess_demo_1" for s in sessions)


def test_get_session_timeline() -> None:
    response = client.get("/api/v1/sessions/sess_demo_1/timeline")
    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "sess_demo_1"
    assert len(payload["messages"]) >= 1


def test_get_cockpit() -> None:
    response = client.get("/api/v1/board/cockpit", params={"session_id": "sess_demo_1"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["id"] == "sess_demo_1"
    assert isinstance(payload["tasks"], list)


def test_ingest_idempotent_by_platform_and_event_id() -> None:
    body = {
        "platform": "hermes",
        "event_id": "evt_same_1",
        "event_type": "message_created",
        "external_session_id": "hermes_demo_2",
        "title": "Second Session",
        "payload_json": {"k": "v"},
        "message": {"role": "user", "content": "hello"},
    }

    first = client.post("/api/v1/events/ingest", json=body)
    second = client.post("/api/v1/events/ingest", json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert first.json()["session_id"] == second.json()["session_id"]

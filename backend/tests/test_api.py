from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"


def test_list_sessions_returns_empty_initially() -> None:
    response = client.get("/api/v1/sessions")
    assert response.status_code == 200
    sessions = response.json()
    assert sessions == []


def test_get_session_timeline_not_found_for_missing_session() -> None:
    response = client.get("/api/v1/sessions/sess_missing/timeline")
    assert response.status_code == 404


def test_get_cockpit_not_found_for_missing_session() -> None:
    response = client.get("/api/v1/board/cockpit", params={"session_id": "sess_missing"})
    assert response.status_code == 404


def test_ingest_creates_session_and_exposes_timeline_and_cockpit() -> None:
    body = {
        "platform": "hermes",
        "event_id": "evt_create_1",
        "event_type": "message_created",
        "external_session_id": "hermes_real_1",
        "title": "Planning Session",
        "payload_json": {"k": "v"},
        "message": {"role": "user", "content": "hello"},
    }

    ingest_response = client.post("/api/v1/events/ingest", json=body)
    assert ingest_response.status_code == 200
    session_id = ingest_response.json()["session_id"]

    timeline_response = client.get(f"/api/v1/sessions/{session_id}/timeline")
    assert timeline_response.status_code == 200
    timeline_payload = timeline_response.json()
    assert timeline_payload["session_id"] == session_id
    assert len(timeline_payload["messages"]) == 1

    cockpit_response = client.get("/api/v1/board/cockpit", params={"session_id": session_id})
    assert cockpit_response.status_code == 200
    cockpit_payload = cockpit_response.json()
    assert cockpit_payload["session"]["id"] == session_id
    assert isinstance(cockpit_payload["tasks"], list)


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

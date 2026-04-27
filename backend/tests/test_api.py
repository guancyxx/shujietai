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


def test_hermes_webhook_ingest_message_event() -> None:
    payload = {
        "event_id": "hermes_evt_1",
        "event_type": "message_created",
        "external_session_id": "hermes_sess_1",
        "title": "Hermes Session",
        "message": {
            "id": "msg_1",
            "role": "assistant",
            "content": "hello from hermes",
        },
        "meta": {"source": "hermes-webhook"},
    }

    webhook_response = client.post("/api/v1/connectors/hermes/webhook", json=payload)
    assert webhook_response.status_code == 200
    assert webhook_response.json()["event_id"] == "hermes_evt_1"

    session_id = webhook_response.json()["session_id"]
    timeline_response = client.get(f"/api/v1/sessions/{session_id}/timeline")
    assert timeline_response.status_code == 200
    timeline_payload = timeline_response.json()
    assert len(timeline_payload["messages"]) == 1
    assert timeline_payload["messages"][0]["content"] == "hello from hermes"
    assert timeline_payload["messages"][0]["role"] == "assistant"


def test_hermes_chat_endpoint_creates_user_and_assistant_messages(monkeypatch) -> None:
    def fake_ask_hermes(prompt: str) -> str:
        assert "What is your name?" in prompt
        return "I am Hermes."

    monkeypatch.setattr("app.main.ask_hermes_response", fake_ask_hermes)

    response = client.post(
        "/api/v1/connectors/hermes/chat",
        json={
            "external_session_id": "hermes_chat_sess_1",
            "title": "Hermes Chat",
            "user_message": "What is your name?",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["assistant_message"] == "I am Hermes."
    assert payload["event_id"]
    assert payload["session_id"]

    timeline_response = client.get(f"/api/v1/sessions/{payload['session_id']}/timeline")
    assert timeline_response.status_code == 200
    timeline = timeline_response.json()
    assert len(timeline["messages"]) == 2
    assert timeline["messages"][0]["role"] == "user"
    assert timeline["messages"][0]["content"] == "What is your name?"
    assert timeline["messages"][1]["role"] == "assistant"
    assert timeline["messages"][1]["content"] == "I am Hermes."


def test_hermes_chat_endpoint_returns_502_when_hermes_unavailable(monkeypatch) -> None:
    def fake_ask_hermes(_: str) -> str:
        raise RuntimeError("hermes_failed")

    monkeypatch.setattr("app.main.ask_hermes_response", fake_ask_hermes)

    response = client.post(
        "/api/v1/connectors/hermes/chat",
        json={
            "external_session_id": "hermes_chat_sess_2",
            "title": "Hermes Chat",
            "user_message": "ping",
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "hermes_unavailable"

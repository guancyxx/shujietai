import httpx
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert "metrics" in payload
    assert set(payload["metrics"].keys()) == {
        "ingest_success_total",
        "ingest_retry_total",
        "ingest_dlq_total",
    }


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
    def fake_ask_hermes(history_messages: list[dict[str, str]], user_message: str) -> str:
        assert history_messages == []
        assert user_message == "What is your name?"
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
    def fake_ask_hermes(_: list[dict[str, str]], __: str) -> str:
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


def test_hermes_chat_endpoint_reuses_session_history_on_next_turn(monkeypatch) -> None:
    captured_histories: list[list[dict[str, str]]] = []

    def fake_ask_hermes(history_messages: list[dict[str, str]], user_message: str) -> str:
        captured_histories.append(history_messages)
        return f"echo:{user_message}"

    monkeypatch.setattr("app.main.ask_hermes_response", fake_ask_hermes)

    first = client.post(
        "/api/v1/connectors/hermes/chat",
        json={
            "external_session_id": "hermes_chat_history_sess_1",
            "title": "Hermes Chat History",
            "user_message": "first",
        },
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/connectors/hermes/chat",
        json={
            "external_session_id": "hermes_chat_history_sess_1",
            "title": "Hermes Chat History",
            "user_message": "second",
        },
    )
    assert second.status_code == 200

    assert len(captured_histories) == 2
    assert captured_histories[0] == []
    assert captured_histories[1] == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "echo:first"},
    ]


def test_ask_hermes_response_openai_api_success(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": "api ok",
                        }
                    }
                ]
            }

    captured: dict = {}

    def fake_post(url: str, headers: dict, json: dict, timeout: float):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("HERMES_API_BASE_URL", "http://localhost:8642/v1")
    monkeypatch.setenv("HERMES_API_KEY", "test-key")
    monkeypatch.setenv("HERMES_MODEL", "gpt-5.3-codex")
    monkeypatch.setenv("HERMES_API_TIMEOUT_SECONDS", "33")
    monkeypatch.setattr("app.main.httpx.post", fake_post)

    from app.main import ask_hermes_response

    result = ask_hermes_response(
        [{"role": "assistant", "content": "history"}],
        "new question",
    )

    assert result == "api ok"
    assert captured["url"] == "http://localhost:8642/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["json"]["model"] == "gpt-5.3-codex"
    assert captured["json"]["messages"][-1] == {"role": "user", "content": "new question"}
    assert captured["timeout"] == 33.0


def test_ask_hermes_response_raises_on_empty_content(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "   "}}]}

    monkeypatch.setattr("app.main.httpx.post", lambda *args, **kwargs: FakeResponse())

    from app.main import ask_hermes_response

    try:
        ask_hermes_response([], "ping")
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert str(exc) == "hermes_empty_response"


def test_ask_hermes_response_propagates_http_error(monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        raise httpx.HTTPStatusError(
            "bad gateway",
            request=httpx.Request("POST", "http://localhost:8642/v1/chat/completions"),
            response=httpx.Response(502),
        )

    monkeypatch.setenv("HERMES_CLI_FALLBACK_ENABLED", "0")
    monkeypatch.setattr("app.main.httpx.post", fake_post)

    from app.main import ask_hermes_response

    try:
        ask_hermes_response([], "ping")
        assert False, "expected HTTPStatusError"
    except httpx.HTTPStatusError as exc:
        assert exc.response.status_code == 502


def test_ask_hermes_response_falls_back_to_cli_when_api_unavailable(monkeypatch) -> None:
    def fake_post(*args, **kwargs):
        raise httpx.ConnectError("unreachable")

    monkeypatch.setenv("HERMES_CLI_FALLBACK_ENABLED", "1")
    monkeypatch.setattr("app.main.httpx.post", fake_post)

    def fake_cli(messages: list[dict[str, str]]) -> str:
        assert messages[-1] == {"role": "user", "content": "ping"}
        return "cli ok"

    monkeypatch.setattr("app.main._ask_hermes_via_cli", fake_cli)

    from app.main import ask_hermes_response

    result = ask_hermes_response([], "ping")
    assert result == "cli ok"

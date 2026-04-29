import httpx
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _mock_github_project_flow(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.github_project_service.GitHubProjectService.default_local_path",
        lambda self, repository_url: "/home/guancy/workspace/Hello-World",
    )
    monkeypatch.setattr(
        "app.services.github_project_service.GitHubProjectService.parse_repository_url",
        lambda self, repository_url: ("octocat", "Hello-World"),
    )
    monkeypatch.setattr(
        "app.services.github_project_service.GitHubProjectService.list_repositories",
        lambda self: [
            {
                "name": "Hello-World",
                "full_name": "octocat/Hello-World",
                "url": "https://github.com/octocat/Hello-World",
                "description": "Demo repository",
            },
        ],
    )
    monkeypatch.setattr(
        "app.services.github_project_service.GitHubProjectService.create_repository",
        lambda self, payload: {
            "name": payload.name,
            "full_name": f"octocat/{payload.name}",
            "url": f"https://github.com/octocat/{payload.name}",
            "description": payload.description,
        },
    )



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


def test_get_system_config() -> None:
    response = client.get("/api/v1/system/config")
    assert response.status_code == 200
    payload = response.json()
    assert "github_token_configured" in payload


def test_update_github_token(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.system_config_service.SystemConfigService.update_github_token",
        lambda self, token: None,
    )
    monkeypatch.setattr(
        "app.services.system_config_service.SystemConfigService.get_config",
        lambda self: {"github_token_configured": True},
    )

    response = client.put(
        "/api/v1/system/config/github-token",
        json={"github_token": "ghp_example"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["github_token_configured"] is True


def test_list_sessions_returns_empty_initially() -> None:
    response = client.get("/api/v1/sessions")
    assert response.status_code == 200
    sessions = response.json()
    assert sessions == []


def test_get_session_timeline_not_found_for_missing_session() -> None:
    response = client.get("/api/v1/sessions/sess_missing/timeline")
    assert response.status_code == 404


def test_project_crud_with_optional_directory(monkeypatch) -> None:
    _mock_github_project_flow(monkeypatch)
    create_response = client.post(
        "/api/v1/projects",
        json={
            "repository_url": "https://github.com/octocat/Hello-World",
            "name": "ShuJieTai MVP",
            "description": "Project cockpit implementation",
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()
    assert created["name"] == "ShuJieTai MVP"
    assert created["repository_name"] == "Hello-World"
    assert created["repository_url"] == "https://github.com/octocat/Hello-World"
    assert created["local_path"].endswith("/Hello-World")
    assert created["code"].startswith("proj-")

    list_response = client.get("/api/v1/projects")
    assert list_response.status_code == 200
    listed = list_response.json()["items"]
    assert len(listed) == 1
    assert listed[0]["id"] == created["id"]

    update_response = client.patch(
        f"/api/v1/projects/{created['id']}",
        json={
            "name": "ShuJieTai Project Center",
            "description": "Updated description",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == "ShuJieTai Project Center"
    assert updated["description"] == "Updated description"

    delete_response = client.delete(f"/api/v1/projects/{created['id']}")
    assert delete_response.status_code == 200

    list_after_delete = client.get("/api/v1/projects")
    assert list_after_delete.status_code == 200
    assert list_after_delete.json()["items"] == []


def test_project_create_rejects_invalid_repo_url() -> None:
    response = client.post(
        "/api/v1/projects",
        json={
            "name": "Bad Project",
            "description": "Invalid URL",
            "repository_url": "not-a-github-url",
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_github_repository_url"


def test_task_board_crud_with_filters(monkeypatch) -> None:
    _mock_github_project_flow(monkeypatch)

    project_response = client.post(
        "/api/v1/projects",
        json={
            "repository_url": "https://github.com/octocat/Hello-World",
            "name": "Task Board Project",
            "description": "Task board linkage",
        },
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]

    first_task = client.post(
        "/api/v1/task-board",
        json={
            "name": "Task A",
            "description": "A description",
            "ai_platform": "hermes",
            "project_id": project_id,
            "status": "draft",
        },
    )
    assert first_task.status_code == 200
    first_payload = first_task.json()

    second_task = client.post(
        "/api/v1/task-board",
        json={
            "name": "Task B",
            "description": "B description",
            "ai_platform": "hermes",
            "project_id": project_id,
            "upstream_task_id": first_payload["id"],
            "parent_task_id": first_payload["id"],
            "status": "in_progress",
        },
    )
    assert second_task.status_code == 200
    second_payload = second_task.json()

    list_response = client.get("/api/v1/task-board", params={"project_id": project_id, "keyword": "Task B"})
    assert list_response.status_code == 200
    listed = list_response.json()["items"]
    assert len(listed) == 1
    assert listed[0]["id"] == second_payload["id"]

    update_response = client.patch(
        f"/api/v1/task-board/{second_payload['id']}",
        json={
            "status": "blocked",
            "description": "B blocked",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["status"] == "blocked"
    assert updated["description"] == "B blocked"

    delete_response = client.delete(f"/api/v1/task-board/{first_payload['id']}")
    assert delete_response.status_code == 200

    list_after_delete = client.get("/api/v1/task-board")
    assert list_after_delete.status_code == 200
    remain = list_after_delete.json()["items"]
    assert len(remain) == 1
    assert remain[0]["id"] == second_payload["id"]
    assert remain[0]["upstream_task_id"] is None
    assert remain[0]["parent_task_id"] is None


def test_task_board_create_rejects_missing_project() -> None:
    response = client.post(
        "/api/v1/task-board",
        json={
            "name": "Task A",
            "description": "A description",
            "project_id": "11111111-1111-1111-1111-111111111111",
            "status": "draft",
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "project_not_found"


def test_task_board_update_rejects_self_dependency(monkeypatch) -> None:
    _mock_github_project_flow(monkeypatch)
    project_response = client.post(
        "/api/v1/projects",
        json={
            "repository_url": "https://github.com/octocat/Hello-World",
            "name": "Task Board Project 2",
            "description": "Task board linkage",
        },
    )
    assert project_response.status_code == 200

    task_response = client.post(
        "/api/v1/task-board",
        json={
            "name": "Task Self",
            "description": "self dep",
            "status": "draft",
        },
    )
    assert task_response.status_code == 200
    task_id = task_response.json()["id"]

    update_response = client.patch(
        f"/api/v1/task-board/{task_id}",
        json={
            "upstream_task_id": task_id,
        },
    )
    assert update_response.status_code == 422
    assert update_response.json()["detail"] == "upstream_task_cannot_be_self"


def test_list_github_repositories(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.main.system_config_service.get_github_token",
        lambda: "ghp_mock",
    )
    monkeypatch.setattr(
        "app.main.github_project_service.list_repositories",
        lambda token_override="": [
            {
                "name": "repo-a",
                "full_name": "owner/repo-a",
                "url": "https://github.com/owner/repo-a",
                "description": "Repo A description",
            }
        ],
    )

    response = client.get("/api/v1/projects/github/repos")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["name"] == "repo-a"
    assert items[0]["description"] == "Repo A description"


def test_list_github_repositories_loads_token_from_system_config(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.main.system_config_service.get_github_token",
        lambda: "ghp_from_db",
    )

    captured: dict[str, str] = {}

    def fake_list_repositories(token_override: str = ""):
        captured["token_override"] = token_override
        return [
            {
                "name": "repo-a",
                "full_name": "owner/repo-a",
                "url": "https://github.com/owner/repo-a",
                "description": "Repo A description",
            }
        ]

    monkeypatch.setattr("app.main.github_project_service.list_repositories", fake_list_repositories)

    response = client.get("/api/v1/projects/github/repos")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert captured["token_override"] == "ghp_from_db"


def test_create_github_repository(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.main.github_project_service.create_repository",
        lambda payload: {
            "name": payload.name,
            "full_name": f"owner/{payload.name}",
            "url": f"https://github.com/owner/{payload.name}",
            "description": payload.description,
        },
    )

    response = client.post(
        "/api/v1/projects/github/repos",
        json={"name": "new-repo", "description": "desc", "private": False},
    )
    assert response.status_code == 200
    item = response.json()
    assert item["name"] == "new-repo"
    assert item["full_name"] == "owner/new-repo"
    assert item["description"] == "desc"


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
    def fake_ask_hermes(history_messages: list[dict[str, str]], user_message: str, system_prompt: str | None = None) -> str:
        assert history_messages == []
        assert user_message == "What is your name?"
        assert system_prompt is None
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
    def fake_ask_hermes(_: list[dict[str, str]], __: str, system_prompt: str | None = None) -> str:
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

    def fake_ask_hermes(history_messages: list[dict[str, str]], user_message: str, system_prompt: str | None = None) -> str:
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


def test_hermes_chat_endpoint_uses_runtime_preferences_instead_of_request_fields(monkeypatch) -> None:
    monkeypatch.setattr("app.main.get_selected_model", lambda: "nvidia/z-ai/glm-5.1")

    captured: dict = {}

    def fake_api(messages: list[dict[str, str]], model_override: str | None = None) -> str:
        captured["messages"] = messages
        captured["model_override"] = model_override
        return "runtime preference reply"

    monkeypatch.setattr("app.main._ask_hermes_via_api", fake_api)

    response = client.post(
        "/api/v1/connectors/hermes/chat",
        json={
            "external_session_id": "hermes_chat_pref_sess_1",
            "title": "Hermes Runtime Pref",
            "user_message": "hello runtime",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["assistant_message"] == "runtime preference reply"
    assert captured["model_override"] == "nvidia/z-ai/glm-5.1"
    assert captured["messages"][-1] == {"role": "user", "content": "hello runtime"}


def test_hermes_chat_endpoint_injects_system_prompt_and_persists_it(monkeypatch) -> None:
    captured_messages: list[list[dict[str, str]]] = []

    def fake_api(messages: list[dict[str, str]], model_override: str | None = None) -> str:
        captured_messages.append(messages)
        return "system prompt acknowledged"

    monkeypatch.setattr("app.main._ask_hermes_via_api", fake_api)

    # First turn with system_prompt
    first = client.post(
        "/api/v1/connectors/hermes/chat",
        json={
            "external_session_id": "hermes_chat_sys_sess_1",
            "title": "Hermes System Prompt",
            "user_message": "start task",
            "system_prompt": "[Task Context]\nTask: Build API",
        },
    )
    assert first.status_code == 200
    assert captured_messages[0][0] == {"role": "system", "content": "[Task Context]\nTask: Build API"}
    assert captured_messages[0][-1] == {"role": "user", "content": "start task"}

    # Verify system message persisted in timeline
    timeline = client.get(f"/api/v1/sessions/{first.json()['session_id']}/timeline")
    timeline_messages = timeline.json()["messages"]
    assert timeline_messages[0]["role"] == "system"
    assert "Build API" in timeline_messages[0]["content"]


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
    monkeypatch.setattr("app.main.get_selected_model", lambda: "")
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

    def fake_cli(
        messages: list[dict[str, str]],
        model_override: str | None = None,
        provider_override: str | None = None,
    ) -> str:
        assert messages[-1] == {"role": "user", "content": "ping"}
        assert isinstance(model_override, str) or model_override is None
        assert isinstance(provider_override, str) or provider_override is None
        return "cli ok"

    monkeypatch.setattr("app.main._ask_hermes_via_cli", fake_cli)

    from app.main import ask_hermes_response

    result = ask_hermes_response([], "ping")
    assert result == "cli ok"

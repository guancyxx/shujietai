from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import DispatchTaskItem

client = TestClient(app)


def _task(task_id: str, status: str, external_session_id: str) -> DispatchTaskItem:
    now = datetime.now(UTC)
    return DispatchTaskItem(
        id=task_id,
        task_board_item_id=None,
        status=status,
        ai_platform="hermes",
        external_session_id=external_session_id,
        current_run_id="dr_test",
        last_sequence=0,
        config={},
        initial_prompt="hello",
        error_message=None,
        started_at=now,
        finished_at=None,
        created_at=now,
        updated_at=now,
    )


def test_resolve_dispatch_session_returns_resume_when_active_task_exists() -> None:
    svc = MagicMock()
    active = _task("dt_active", "running", "web_api_resume")
    svc.resolve_session_dispatch.return_value = {
        "platform": "hermes",
        "external_session_id": "web_api_resume",
        "recommended_action": "resume",
        "active_dispatch_task": active,
        "latest_dispatch_task": active,
    }
    app.state.dispatch_service = svc

    response = client.get("/api/v1/dispatch/session/web_api_resume?platform=hermes")

    assert response.status_code == 200
    data = response.json()
    svc.resolve_session_dispatch.assert_called_once_with("hermes", "web_api_resume")
    assert data["platform"] == "hermes"
    assert data["external_session_id"] == "web_api_resume"
    assert data["recommended_action"] == "resume"
    assert data["active_dispatch_task"]["id"] == "dt_active"
    assert data["latest_dispatch_task"]["id"] == "dt_active"


def test_resolve_dispatch_session_returns_view_history_when_only_latest_exists() -> None:
    svc = MagicMock()
    latest = _task("dt_latest", "completed", "web_api_history")
    svc.resolve_session_dispatch.return_value = {
        "platform": "yuanbao",
        "external_session_id": "web_api_history",
        "recommended_action": "view_history",
        "active_dispatch_task": None,
        "latest_dispatch_task": latest,
    }
    app.state.dispatch_service = svc

    response = client.get("/api/v1/dispatch/session/web_api_history?platform=yuanbao")

    assert response.status_code == 200
    data = response.json()
    svc.resolve_session_dispatch.assert_called_once_with("yuanbao", "web_api_history")
    assert data["platform"] == "yuanbao"
    assert data["recommended_action"] == "view_history"
    assert data["active_dispatch_task"] is None
    assert data["latest_dispatch_task"]["id"] == "dt_latest"


def test_resolve_dispatch_session_returns_create_new_when_no_task_exists() -> None:
    svc = MagicMock()
    svc.resolve_session_dispatch.return_value = {
        "platform": "hermes",
        "external_session_id": "web_api_new",
        "recommended_action": "create_new",
        "active_dispatch_task": None,
        "latest_dispatch_task": None,
    }
    app.state.dispatch_service = svc

    response = client.get("/api/v1/dispatch/session/web_api_new?platform=hermes")

    assert response.status_code == 200
    data = response.json()
    svc.resolve_session_dispatch.assert_called_once_with("hermes", "web_api_new")
    assert data == {
        "platform": "hermes",
        "external_session_id": "web_api_new",
        "recommended_action": "create_new",
        "active_dispatch_task": None,
        "latest_dispatch_task": None,
    }

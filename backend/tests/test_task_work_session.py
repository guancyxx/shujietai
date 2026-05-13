"""Tests for task work-session resolver."""

from unittest.mock import MagicMock, patch

import pytest

from app.schemas import DispatchCreateRequest
from app.services.dispatch_service import DispatchService


class TestDispatchServiceWorkSession:
    """Test resolve_work_session and helper lookup methods."""

    @pytest.fixture
    def svc(self):
        """Return a DispatchService with a MagicMock session factory."""
        session_factory = MagicMock()
        return DispatchService(session_factory)

    def test_get_latest_task_for_task_board_item_empty_id(self, svc):
        """get_latest_task returns None when input is empty/whitespace."""
        assert svc.get_latest_task_for_task_board_item("") is None
        assert svc.get_latest_task_for_task_board_item("   ") is None

    def test_resolve_work_session_empty_id(self, svc):
        """Empty task_board_item_id returns create_new."""
        result = svc.resolve_work_session("")
        assert result["recommended_action"] == "create_new"
        assert result["active_dispatch_task"] is None

    def test_resolve_work_session_has_active_task(self, svc):
        """Active non-terminal task returns resume."""
        fake_task = MagicMock()
        fake_task.status = "running"
        # Patch get_active_task_for_task_board_item to return our fake task
        svc.get_active_task_for_task_board_item = MagicMock(return_value=fake_task)

        result = svc.resolve_work_session("task-123")
        assert result["recommended_action"] == "resume"
        assert result["active_dispatch_task"] is fake_task

    def test_resolve_work_session_terminal_only(self, svc):
        """Only terminal task leads to view_history."""
        fake_task = MagicMock()
        fake_task.status = "completed"
        svc.get_active_task_for_task_board_item = MagicMock(return_value=None)
        svc.get_latest_task_for_task_board_item = MagicMock(return_value=fake_task)

        result = svc.resolve_work_session("task-123")
        assert result["recommended_action"] == "view_history"
        assert result["active_dispatch_task"] is None
        assert result["latest_dispatch_task"] is fake_task

    def test_resolve_work_session_nothing(self, svc):
        """No task at all returns create_new."""
        svc.get_active_task_for_task_board_item = MagicMock(return_value=None)
        svc.get_latest_task_for_task_board_item = MagicMock(return_value=None)

        result = svc.resolve_work_session("task-123")
        assert result["recommended_action"] == "create_new"
        assert result["active_dispatch_task"] is None
        assert result["latest_dispatch_task"] is None

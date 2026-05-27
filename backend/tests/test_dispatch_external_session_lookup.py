from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db import models  # noqa: F401
from app.db.models import DispatchTaskEntity
from app.schemas import DispatchCreateRequest
from app.services.dispatch_service import DispatchService


def _make_service() -> DispatchService:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return DispatchService(sessionmaker(bind=engine, expire_on_commit=False))


def test_get_latest_task_by_external_session_id_returns_latest_created_task() -> None:
    service = _make_service()
    first = service.create_task(
        DispatchCreateRequest(
            ai_platform="hermes",
            initial_prompt="first run",
            external_session_id="web_lookup_session",
        )
    )
    second = service.create_task(
        DispatchCreateRequest(
            ai_platform="hermes",
            initial_prompt="second run",
            external_session_id="web_lookup_session",
        )
    )

    resolved = service.get_latest_task_by_external_session_id("hermes", "web_lookup_session")

    assert resolved is not None
    assert resolved.id == second.id
    assert resolved.external_session_id == "web_lookup_session"
    assert resolved.id != first.id


def test_get_active_task_by_external_session_id_prefers_non_terminal_task() -> None:
    service = _make_service()
    completed = service.create_task(
        DispatchCreateRequest(
            ai_platform="hermes",
            initial_prompt="completed run",
            external_session_id="web_active_session",
        )
    )
    service.transition_task(completed.id, "running")
    service.transition_task(completed.id, "completed")

    active = service.create_task(
        DispatchCreateRequest(
            ai_platform="hermes",
            initial_prompt="active run",
            external_session_id="web_active_session",
        )
    )
    service.transition_task(active.id, "running")

    resolved = service.get_active_task_by_external_session_id("hermes", "web_active_session")

    assert resolved is not None
    assert resolved.id == active.id
    assert resolved.status == "running"


def test_get_active_task_by_external_session_id_returns_none_when_only_terminal_tasks_exist() -> None:
    service = _make_service()
    created = service.create_task(
        DispatchCreateRequest(
            ai_platform="hermes",
            initial_prompt="completed only",
            external_session_id="web_terminal_session",
        )
    )
    service.transition_task(created.id, "running")
    service.transition_task(created.id, "completed")

    resolved = service.get_active_task_by_external_session_id("hermes", "web_terminal_session")

    assert resolved is None


def test_resolve_session_dispatch_prefers_resume_when_active_task_exists() -> None:
    service = _make_service()
    created = service.create_task(
        DispatchCreateRequest(
            ai_platform="hermes",
            initial_prompt="active run",
            external_session_id="web_resolve_session",
        )
    )
    service.transition_task(created.id, "running")

    resolved = service.resolve_session_dispatch("hermes", "web_resolve_session")

    assert resolved["platform"] == "hermes"
    assert resolved["recommended_action"] == "resume"
    assert resolved["active_dispatch_task"] is not None
    assert resolved["active_dispatch_task"].id == created.id
    assert resolved["latest_dispatch_task"].id == created.id


def test_external_session_lookup_is_scoped_by_platform() -> None:
    service = _make_service()
    hermes_task = service.create_task(
        DispatchCreateRequest(
            ai_platform="hermes",
            initial_prompt="hermes run",
            external_session_id="web_same_session",
        )
    )

    now = datetime.now(UTC)
    with service._session_factory() as db:  # noqa: SLF001 - test-only fixture setup
        yuanbao_task = DispatchTaskEntity(
            id=str(uuid4()),
            task_board_item_id=None,
            status="completed",
            ai_platform="yuanbao",
            external_session_id="web_same_session",
            config={},
            initial_prompt="yuanbao run",
            error_message=None,
            current_run_id="dr_test_yuanbao",
            last_sequence=0,
            started_at=now,
            finished_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(yuanbao_task)
        db.commit()

    hermes_latest = service.get_latest_task_by_external_session_id("hermes", "web_same_session")
    yuanbao_latest = service.get_latest_task_by_external_session_id("yuanbao", "web_same_session")

    assert hermes_latest is not None
    assert yuanbao_latest is not None
    assert hermes_latest.id == hermes_task.id
    assert yuanbao_latest.id == yuanbao_task.id

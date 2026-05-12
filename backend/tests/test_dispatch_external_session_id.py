from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db import models  # noqa: F401
from app.schemas import DispatchCreateRequest
from app.services.dispatch_service import DispatchService


def _make_service() -> DispatchService:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return DispatchService(sessionmaker(bind=engine, expire_on_commit=False))


def test_create_dispatch_task_preserves_supplied_external_session_id() -> None:
    service = _make_service()

    created = service.create_task(
        DispatchCreateRequest(
            ai_platform="hermes",
            initial_prompt="Continue this conversation",
            external_session_id="web_existing_session",
        )
    )

    assert created.external_session_id == "web_existing_session"


def test_create_dispatch_task_generates_external_session_id_when_omitted() -> None:
    service = _make_service()

    created = service.create_task(
        DispatchCreateRequest(
            ai_platform="hermes",
            initial_prompt="Start a new conversation",
        )
    )

    assert created.external_session_id == f"dispatch_{created.id}"

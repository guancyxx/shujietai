from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import SystemConfigEntity
from app.services.system_config_service import SystemConfigService
from sqlalchemy import create_engine


def _build_service() -> tuple[SystemConfigService, sessionmaker]:
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    return SystemConfigService(session_factory), session_factory


def test_update_and_get_config_from_database() -> None:
    service, _session_factory = _build_service()

    service.update_github_token("ghp_test_db_token")
    config = service.get_config()

    assert config.github_token_configured is True
    assert service.get_github_token() == "ghp_test_db_token"


def test_update_token_overwrites_existing_value() -> None:
    service, session_factory = _build_service()

    service.update_github_token("first-token")
    service.update_github_token("second-token")

    with session_factory() as db:
        entity = db.get(SystemConfigEntity, "github_token")
        assert entity is not None
        assert entity.value == "second-token"
        assert isinstance(entity.updated_at, datetime)


def test_empty_token_is_treated_as_not_configured() -> None:
    service, _session_factory = _build_service()

    service.update_github_token("   ")

    assert service.get_github_token() == ""
    assert service.get_config().github_token_configured is False

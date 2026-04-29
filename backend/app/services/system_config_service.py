from __future__ import annotations

import os
from datetime import UTC, datetime
from threading import Lock

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import SystemConfigEntity
from app.schemas import SystemConfigResponse


class SystemConfigService:
    def __init__(self, session_factory: sessionmaker | None = None) -> None:
        self._lock = Lock()
        self._session_factory = session_factory

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def _upsert_config(self, db: Session, key: str, value: str) -> None:
        entity = db.get(SystemConfigEntity, key)
        if entity is None:
            db.add(SystemConfigEntity(key=key, value=value, updated_at=self._now()))
            return
        entity.value = value
        entity.updated_at = self._now()

    def _read_config(self, db: Session, key: str) -> str:
        entity = db.execute(select(SystemConfigEntity).where(SystemConfigEntity.key == key)).scalar_one_or_none()
        if entity is None:
            return ""
        return entity.value.strip()

    def update_github_token(self, token: str) -> None:
        normalized = token.strip()
        if self._session_factory is not None:
            with self._lock:
                with self._session_factory.begin() as db:
                    self._upsert_config(db, "github_token", normalized)
            return
        os.environ["GITHUB_TOKEN"] = normalized

    def get_github_token(self) -> str:
        if self._session_factory is not None:
            with self._session_factory() as db:
                token = self._read_config(db, "github_token")
                if token:
                    return token
        return os.getenv("GITHUB_TOKEN", "").strip()

    def get_config(self) -> SystemConfigResponse:
        token = self.get_github_token()
        return SystemConfigResponse(github_token_configured=bool(token))

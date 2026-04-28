from __future__ import annotations

import os

from app.services.session_store import SessionStore
from app.services.sqlalchemy_store import SqlAlchemySessionStore


def build_store() -> SessionStore | SqlAlchemySessionStore:
    backend = os.getenv("SESSION_STORE_BACKEND", "sqlalchemy").strip().lower()
    if backend == "sqlalchemy":
        database_url = os.getenv("DATABASE_URL", "postgresql+psycopg2://shujietai:shujietai_dev@postgres:5432/shujietai")
        return SqlAlchemySessionStore(database_url)
    return SessionStore()

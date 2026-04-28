def test_build_store_defaults_to_memory_store(monkeypatch) -> None:
    monkeypatch.delenv("SESSION_STORE_BACKEND", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    from app.services.store_factory import build_store
    from app.services.session_store import SessionStore

    store = build_store()

    assert isinstance(store, SessionStore)


def test_build_store_uses_sqlalchemy_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_STORE_BACKEND", "sqlalchemy")
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")

    from app.services.store_factory import build_store
    from app.services.sqlalchemy_store import SqlAlchemySessionStore

    store = build_store()

    assert isinstance(store, SqlAlchemySessionStore)

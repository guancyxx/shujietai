def test_build_store_defaults_to_sqlalchemy_store(monkeypatch) -> None:
    monkeypatch.delenv("SESSION_STORE_BACKEND", raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")

    from app.services.store_factory import build_store
    from app.services.sqlalchemy_store import SqlAlchemySessionStore

    store = build_store()

    assert isinstance(store, SqlAlchemySessionStore)


def test_build_store_uses_memory_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_STORE_BACKEND", "memory")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    from app.services.store_factory import build_store
    from app.services.session_store import SessionStore

    store = build_store()

    assert isinstance(store, SessionStore)

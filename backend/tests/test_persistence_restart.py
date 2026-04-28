from __future__ import annotations

from app.schemas import IngestEventRequest
from app.services.sqlalchemy_store import SqlAlchemySessionStore


def test_sqlalchemy_store_persists_after_store_recreation(tmp_path) -> None:
    sqlite_path = tmp_path / "persist_restart.db"
    database_url = f"sqlite+pysqlite:///{sqlite_path}"

    first_store = SqlAlchemySessionStore(database_url)
    payload = IngestEventRequest(
        platform="hermes",
        event_id="evt_persist_restart_1",
        event_type="message_created",
        external_session_id="persist_sess_1",
        title="Persist Check",
        payload_json={"source": "test"},
        message={"role": "user", "content": "hello"},
    )
    first_session_id, first_duplicate = first_store.ingest(payload)

    assert first_duplicate is False

    second_store = SqlAlchemySessionStore(database_url)
    sessions = second_store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].id == first_session_id
    assert sessions[0].external_session_id == "persist_sess_1"

    timeline = second_store.get_timeline(first_session_id)
    assert timeline is not None
    assert len(timeline.messages) == 1
    assert timeline.messages[0].content == "hello"

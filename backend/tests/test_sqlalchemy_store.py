from app.schemas import IngestEventRequest


def test_sqlalchemy_store_ingest_and_query_roundtrip() -> None:
    from app.services.sqlalchemy_store import SqlAlchemySessionStore

    store = SqlAlchemySessionStore("sqlite+pysqlite:///:memory:")

    payload = IngestEventRequest(
        platform="hermes",
        event_id="evt_sql_1",
        event_type="message_created",
        external_session_id="sql_sess_1",
        title="SQL Session",
        payload_json={"source": "test"},
        message={"role": "user", "content": "hello"},
    )

    session_id, duplicate = store.ingest(payload)

    assert duplicate is False
    assert session_id

    sessions = store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].external_session_id == "sql_sess_1"

    timeline = store.get_timeline(session_id)
    assert timeline is not None
    assert len(timeline.messages) == 1
    assert timeline.messages[0].content == "hello"

    history = store.get_history_messages("hermes", "sql_sess_1")
    assert history == [{"role": "user", "content": "hello"}]

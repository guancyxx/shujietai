from datetime import UTC, datetime, timedelta

from app.schemas import IngestEventRequest, ProjectCreateRequest, TaskBoardCreateRequest, TaskBoardUpdateRequest


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


def test_sqlalchemy_store_list_sessions_orders_by_recent_activity_desc_and_exposes_timestamps() -> None:
    from app.services.sqlalchemy_store import SqlAlchemySessionStore

    store = SqlAlchemySessionStore("sqlite+pysqlite:///:memory:")
    base = datetime(2026, 5, 11, 9, 0, tzinfo=UTC)
    ticks = iter(
        [
            base,
            base,
            base,
            base + timedelta(minutes=1),
            base + timedelta(minutes=2),
            base + timedelta(minutes=3),
            base + timedelta(minutes=10),
            base + timedelta(minutes=10),
            base + timedelta(minutes=10),
            base + timedelta(minutes=11),
            base + timedelta(minutes=12),
            base + timedelta(minutes=13),
            base + timedelta(minutes=20),
            base + timedelta(minutes=21),
            base + timedelta(minutes=22),
        ]
    )
    store.now = lambda: next(ticks)

    older_payload = IngestEventRequest(
        platform="hermes",
        event_id="evt_sql_order_1",
        event_type="message_created",
        external_session_id="sql_old",
        title="Older Session",
        payload_json={"source": "test"},
        message={"role": "user", "content": "hello old"},
    )
    newer_payload = IngestEventRequest(
        platform="hermes",
        event_id="evt_sql_order_2",
        event_type="message_created",
        external_session_id="sql_new",
        title="Newer Session",
        payload_json={"source": "test"},
        message={"role": "user", "content": "hello new"},
    )
    refresh_payload = IngestEventRequest(
        platform="hermes",
        event_id="evt_sql_order_3",
        event_type="message_created",
        external_session_id="sql_old",
        title="Older Session",
        payload_json={"source": "test"},
        message={"role": "assistant", "content": "recent reply"},
    )

    older_session_id, older_duplicate = store.ingest(older_payload)
    newer_session_id, newer_duplicate = store.ingest(newer_payload)
    refreshed_session_id, refreshed_duplicate = store.ingest(refresh_payload)

    assert older_duplicate is False
    assert newer_duplicate is False
    assert refreshed_duplicate is False
    assert refreshed_session_id == older_session_id

    sessions = store.list_sessions()
    assert [session.external_session_id for session in sessions] == ["sql_old", "sql_new"]
    assert sessions[0].updated_at > sessions[1].updated_at
    assert sessions[0].created_at.replace(tzinfo=UTC) == base
    assert sessions[0].updated_at.replace(tzinfo=UTC) > sessions[0].created_at.replace(tzinfo=UTC)
    assert sessions[1].updated_at.replace(tzinfo=UTC) >= sessions[1].created_at.replace(tzinfo=UTC)
    assert sessions[1].created_at.replace(tzinfo=UTC) >= sessions[0].created_at.replace(tzinfo=UTC)

    detail = store.get_session(older_session_id)
    assert detail is not None
    assert detail.created_at.replace(tzinfo=UTC) == sessions[0].created_at.replace(tzinfo=UTC)
    assert detail.updated_at.replace(tzinfo=UTC) == sessions[0].updated_at.replace(tzinfo=UTC)


def test_sqlalchemy_store_project_roundtrip() -> None:
    from app.services.sqlalchemy_store import SqlAlchemySessionStore

    store = SqlAlchemySessionStore("sqlite+pysqlite:///:memory:")
    store._github_service.parse_repository_url = lambda url: ("owner", "repo1")
    store._github_service.default_local_path = lambda url: "/home/guancy/workspace/repo1"

    created = store.create_project(
        ProjectCreateRequest(
            repository_url="https://github.com/owner/repo1",
            name="repo1",
            description="demo",
        )
    )

    assert created.repository_name == "repo1"
    assert created.local_path == "/home/guancy/workspace/repo1"

    listed = store.list_projects()
    assert len(listed) == 1
    assert listed[0].id == created.id


def test_sqlalchemy_store_task_board_crud_and_filters() -> None:
    from app.services.sqlalchemy_store import SqlAlchemySessionStore

    store = SqlAlchemySessionStore("sqlite+pysqlite:///:memory:")
    store._github_service.parse_repository_url = lambda url: ("owner", "repo1")
    store._github_service.default_local_path = lambda url: "/home/guancy/workspace/repo1"

    project = store.create_project(
        ProjectCreateRequest(
            repository_url="https://github.com/owner/repo1",
            name="repo1",
            description="demo",
        )
    )

    first = store.create_task_board_item(
        TaskBoardCreateRequest(
            name="Task A",
            description="A description",
            ai_platform="hermes",
            project_id=project.id,
            status="draft",
        )
    )

    second = store.create_task_board_item(
        TaskBoardCreateRequest(
            name="Task B",
            description="B description",
            ai_platform="hermes",
            project_id=project.id,
            upstream_task_id=first.id,
            parent_task_id=first.id,
            status="in_progress",
        )
    )

    listed_all = store.list_task_board_items()
    assert len(listed_all) == 2

    listed_by_project = store.list_task_board_items(project_id=str(project.id))
    assert len(listed_by_project) == 2

    listed_by_keyword = store.list_task_board_items(keyword="Task B")
    assert len(listed_by_keyword) == 1
    assert listed_by_keyword[0].id == second.id

    updated = store.update_task_board_item(
        str(second.id),
        TaskBoardUpdateRequest(
            status="blocked",
            description="B updated",
        ),
    )
    assert updated is not None
    assert updated.status == "blocked"
    assert updated.description == "B updated"

    deleted = store.delete_task_board_item(str(first.id))
    assert deleted is True

    remaining = store.list_task_board_items()
    assert len(remaining) == 1
    assert remaining[0].id == second.id
    assert remaining[0].upstream_task_id is None
    assert remaining[0].parent_task_id is None

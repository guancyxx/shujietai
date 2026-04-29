from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import EventEntity, MessageEntity, ProjectEntity, SessionEntity, SessionMetricsEntity, TaskBoardEntity, TaskEntity
from app.schemas import (
    CockpitResponse,
    EventItem,
    IngestEventRequest,
    MessageItem,
    ProjectCreateRequest,
    ProjectItem,
    ProjectUpdateRequest,
    SessionDetail,
    SessionMetrics,
    SessionSummary,
    TaskBoardCreateRequest,
    TaskBoardItem,
    TaskBoardUpdateRequest,
    TaskItem,
    TimelineResponse,
)
from app.services.hermes_runtime_catalog import build_runtime_state
from app.services.github_project_service import GitHubProjectService
from app.services.system_config_service import SystemConfigService


class SqlAlchemySessionStore:
    def __init__(self, database_url: str) -> None:
        self._lock = Lock()
        self._engine = self._build_engine(database_url)
        if database_url.startswith("sqlite"):
            Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(self._engine, expire_on_commit=False)
        self._github_service = GitHubProjectService()
        self._system_config_service = SystemConfigService(self._session_factory)

    def _build_engine(self, database_url: str) -> Engine:
        if database_url.startswith("sqlite"):
            engine_kwargs: dict = {"connect_args": {"check_same_thread": False}}
            if database_url.endswith(":memory:"):
                from sqlalchemy.pool import StaticPool

                engine_kwargs["poolclass"] = StaticPool
            return create_engine(database_url, **engine_kwargs)
        return create_engine(database_url)

    def _build_next_project_code(self, db: Session) -> str:
        latest_project = db.execute(select(ProjectEntity).order_by(ProjectEntity.created_at.desc())).scalars().first()
        if latest_project is None:
            return "proj-0001"

        parts = latest_project.code.split("-")
        if len(parts) == 2 and parts[1].isdigit():
            sequence = int(parts[1]) + 1
            return f"proj-{sequence:04d}"
        return f"proj-{uuid4().hex[:8]}"

    @property
    def session_factory(self) -> sessionmaker:
        return self._session_factory

    def now(self) -> datetime:
        return datetime.now(UTC)

    def ingest(self, payload: IngestEventRequest) -> tuple[str, bool]:
        with self._lock:
            with self._session_factory.begin() as db:
                session_entity = self._get_or_create_session(db, payload)
                duplicate = db.get(EventEntity, payload.event_id)
                if duplicate is not None and duplicate.platform == payload.platform:
                    return session_entity.id, True

                db.add(
                    EventEntity(
                        id=payload.event_id,
                        platform=payload.platform,
                        session_id=session_entity.id,
                        event_type=payload.event_type,
                        payload_json=payload.payload_json,
                        created_at=self.now(),
                    )
                )

                if payload.message is not None:
                    db.add(
                        MessageEntity(
                            id=f"msg_{uuid4().hex[:10]}",
                            session_id=session_entity.id,
                            role=payload.message.role,
                            content=payload.message.content,
                            content_type=payload.message.content_type,
                            created_at=self.now(),
                            meta_json=payload.message.meta_json,
                        )
                    )

                if payload.task is not None:
                    db.add(
                        TaskEntity(
                            id=f"task_{uuid4().hex[:10]}",
                            session_id=session_entity.id,
                            title=payload.task.title,
                            lane=payload.task.lane,
                            priority=payload.task.priority,
                            assignee=payload.task.assignee,
                            updated_at=self.now(),
                        )
                    )

                self._refresh_metrics(db, session_entity.id)
                self._refresh_counts(db, session_entity.id)
                return session_entity.id, False

    def _get_or_create_session(self, db: Session, payload: IngestEventRequest) -> SessionEntity:
        existing = db.execute(
            select(SessionEntity).where(
                SessionEntity.platform == payload.platform,
                SessionEntity.external_session_id == payload.external_session_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        session = SessionEntity(
            id=f"sess_{uuid4().hex[:12]}",
            platform=payload.platform,
            external_session_id=payload.external_session_id,
            title=payload.title or f"Session {payload.external_session_id}",
            status="active",
            started_at=self.now(),
            ended_at=None,
            message_count=0,
            task_count=0,
        )
        db.add(session)
        db.add(
            SessionMetricsEntity(
                session_id=session.id,
                token_in=0,
                token_out=0,
                latency_ms_p50=0,
                error_count=0,
                updated_at=self.now(),
            )
        )
        return session

    def _refresh_metrics(self, db: Session, session_id: str) -> None:
        metrics = db.get(SessionMetricsEntity, session_id)
        if metrics is None:
            metrics = SessionMetricsEntity(
                session_id=session_id,
                token_in=0,
                token_out=0,
                latency_ms_p50=0,
                error_count=0,
                updated_at=self.now(),
            )
            db.add(metrics)

        event_count = db.query(EventEntity).filter(EventEntity.session_id == session_id).count()
        metrics.token_in += 10
        metrics.token_out += 8
        metrics.latency_ms_p50 = max(100, 100 + event_count * 5)
        metrics.updated_at = self.now()

    def _refresh_counts(self, db: Session, session_id: str) -> None:
        session = db.get(SessionEntity, session_id)
        if session is None:
            return
        session.message_count = db.query(MessageEntity).filter(MessageEntity.session_id == session_id).count()
        session.task_count = db.query(TaskEntity).filter(TaskEntity.session_id == session_id).count()

    def list_sessions(self) -> list[SessionSummary]:
        with self._session_factory() as db:
            rows = db.execute(select(SessionEntity).order_by(SessionEntity.started_at.asc())).scalars().all()
            return [
                SessionSummary(
                    id=row.id,
                    platform=row.platform,
                    external_session_id=row.external_session_id,
                    title=row.title,
                    status=row.status,
                    started_at=row.started_at,
                    ended_at=row.ended_at,
                )
                for row in rows
            ]

    def get_session(self, session_id: str) -> SessionDetail | None:
        with self._session_factory() as db:
            row = db.get(SessionEntity, session_id)
            if row is None:
                return None
            return SessionDetail(
                id=row.id,
                platform=row.platform,
                external_session_id=row.external_session_id,
                title=row.title,
                status=row.status,
                started_at=row.started_at,
                ended_at=row.ended_at,
                message_count=row.message_count,
                task_count=row.task_count,
            )

    def get_timeline(self, session_id: str) -> TimelineResponse | None:
        with self._session_factory() as db:
            session = db.get(SessionEntity, session_id)
            if session is None:
                return None

            message_rows = db.execute(
                select(MessageEntity).where(MessageEntity.session_id == session_id).order_by(MessageEntity.created_at.asc())
            ).scalars().all()
            event_rows = db.execute(
                select(EventEntity).where(EventEntity.session_id == session_id).order_by(EventEntity.created_at.asc())
            ).scalars().all()

            return TimelineResponse(
                session_id=session_id,
                messages=[
                    MessageItem(
                        id=row.id,
                        session_id=row.session_id,
                        role=row.role,
                        content=row.content,
                        content_type=row.content_type,
                        created_at=row.created_at,
                        meta_json=row.meta_json or {},
                    )
                    for row in message_rows
                ],
                events=[
                    EventItem(
                        id=row.id,
                        session_id=row.session_id,
                        event_type=row.event_type,
                        payload_json=row.payload_json or {},
                        created_at=row.created_at,
                    )
                    for row in event_rows
                ],
            )

    def get_history_messages(self, platform: str, external_session_id: str) -> list[dict[str, str]]:
        with self._session_factory() as db:
            session_entity = db.execute(
                select(SessionEntity).where(
                    SessionEntity.platform == platform,
                    SessionEntity.external_session_id == external_session_id,
                )
            ).scalar_one_or_none()
            if session_entity is None:
                return []

            rows = db.execute(
                select(MessageEntity)
                .where(MessageEntity.session_id == session_entity.id)
                .order_by(MessageEntity.created_at.asc())
            ).scalars().all()

            history: list[dict[str, str]] = []
            for row in rows:
                if row.role in ("user", "assistant", "system"):
                    history.append({"role": row.role, "content": row.content})
            return history

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            with self._session_factory.begin() as db:
                session_row = db.get(SessionEntity, session_id)
                if session_row is None:
                    return False

                db.query(MessageEntity).filter(MessageEntity.session_id == session_id).delete(synchronize_session=False)
                db.query(EventEntity).filter(EventEntity.session_id == session_id).delete(synchronize_session=False)
                db.query(TaskEntity).filter(TaskEntity.session_id == session_id).delete(synchronize_session=False)
                db.query(SessionMetricsEntity).filter(SessionMetricsEntity.session_id == session_id).delete(synchronize_session=False)
                db.delete(session_row)
                return True

    def list_project_directory_options(self) -> list[str]:
        return []

    def list_projects(self) -> list[ProjectItem]:
        with self._session_factory() as db:
            rows = db.execute(select(ProjectEntity).order_by(ProjectEntity.created_at.asc())).scalars().all()
            return [
                ProjectItem(
                    id=UUID(row.id),
                    code=row.code,
                    name=row.name,
                    description=row.description,
                    repository_url=row.repository_url,
                    repository_name=row.repository_name,
                    local_path=row.local_path,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in rows
            ]

    def create_project(self, payload: ProjectCreateRequest) -> ProjectItem:
        with self._lock:
            with self._session_factory.begin() as db:
                project_code = self._build_next_project_code(db)
                repository_url = payload.repository_url.strip()
                _owner, repository_name = self._github_service.parse_repository_url(repository_url)
                local_path = self._github_service.default_local_path(repository_url)
                project_id = str(uuid4())
                now = self.now()
                entity = ProjectEntity(
                    id=project_id,
                    code=project_code,
                    name=(payload.name or repository_name).strip(),
                    description=payload.description.strip(),
                    repository_url=repository_url,
                    repository_name=repository_name,
                    local_path=local_path,
                    created_at=now,
                    updated_at=now,
                )
                db.add(entity)
                return ProjectItem(
                    id=UUID(project_id),
                    code=entity.code,
                    name=entity.name,
                    description=entity.description,
                    repository_url=entity.repository_url,
                    repository_name=entity.repository_name,
                    local_path=entity.local_path,
                    created_at=entity.created_at,
                    updated_at=entity.updated_at,
                )

    def update_project(self, project_id: str, payload: ProjectUpdateRequest) -> ProjectItem | None:
        with self._lock:
            with self._session_factory.begin() as db:
                entity = db.get(ProjectEntity, project_id)
                if entity is None:
                    return None

                if payload.name is not None:
                    entity.name = payload.name.strip()
                if payload.description is not None:
                    entity.description = payload.description.strip()
                entity.updated_at = self.now()

                return ProjectItem(
                    id=UUID(entity.id),
                    code=entity.code,
                    name=entity.name,
                    description=entity.description,
                    repository_url=entity.repository_url,
                    repository_name=entity.repository_name,
                    local_path=entity.local_path,
                    created_at=entity.created_at,
                    updated_at=entity.updated_at,
                )

    def delete_project(self, project_id: str) -> bool:
        with self._lock:
            with self._session_factory.begin() as db:
                entity = db.get(ProjectEntity, project_id)
                if entity is None:
                    return False
                db.delete(entity)
                return True

    def _build_task_board_item(self, db: Session, row: TaskBoardEntity) -> TaskBoardItem:
        project = db.get(ProjectEntity, row.project_id) if row.project_id else None
        upstream = db.get(TaskBoardEntity, row.upstream_task_id) if row.upstream_task_id else None
        parent = db.get(TaskBoardEntity, row.parent_task_id) if row.parent_task_id else None
        return TaskBoardItem(
            id=UUID(row.id),
            name=row.name,
            description=row.description,
            ai_platform=row.ai_platform,
            project_id=UUID(row.project_id) if row.project_id else None,
            project_name=project.name if project else None,
            project_repository_url=project.repository_url if project else None,
            project_repository_name=project.repository_name if project else None,
            upstream_task_id=UUID(row.upstream_task_id) if row.upstream_task_id else None,
            upstream_task_name=upstream.name if upstream else None,
            parent_task_id=UUID(row.parent_task_id) if row.parent_task_id else None,
            parent_task_name=parent.name if parent else None,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def list_task_board_items(self, project_id: str | None = None, keyword: str | None = None) -> list[TaskBoardItem]:
        with self._session_factory() as db:
            statement = select(TaskBoardEntity).order_by(TaskBoardEntity.created_at.asc())
            if project_id:
                statement = statement.where(TaskBoardEntity.project_id == project_id)
            rows = db.execute(statement).scalars().all()
            normalized_keyword = (keyword or "").strip().lower()
            if normalized_keyword:
                rows = [
                    row
                    for row in rows
                    if normalized_keyword in f"{row.name} {row.description} {row.ai_platform}".lower()
                ]
            return [self._build_task_board_item(db, row) for row in rows]

    def create_task_board_item(self, payload: TaskBoardCreateRequest) -> TaskBoardItem:
        with self._lock:
            with self._session_factory.begin() as db:
                if payload.project_id is not None and db.get(ProjectEntity, str(payload.project_id)) is None:
                    raise ValueError("project_not_found")
                if payload.upstream_task_id is not None and db.get(TaskBoardEntity, str(payload.upstream_task_id)) is None:
                    raise ValueError("upstream_task_not_found")
                if payload.parent_task_id is not None and db.get(TaskBoardEntity, str(payload.parent_task_id)) is None:
                    raise ValueError("parent_task_not_found")

                item_id = str(uuid4())
                now = self.now()
                entity = TaskBoardEntity(
                    id=item_id,
                    name=payload.name.strip(),
                    description=payload.description.strip(),
                    ai_platform=(payload.ai_platform or "hermes").strip() or "hermes",
                    project_id=str(payload.project_id) if payload.project_id is not None else None,
                    upstream_task_id=str(payload.upstream_task_id) if payload.upstream_task_id is not None else None,
                    parent_task_id=str(payload.parent_task_id) if payload.parent_task_id is not None else None,
                    status=payload.status,
                    created_at=now,
                    updated_at=now,
                )
                db.add(entity)
                db.flush()
                return self._build_task_board_item(db, entity)

    def update_task_board_item(self, task_id: str, payload: TaskBoardUpdateRequest) -> TaskBoardItem | None:
        with self._lock:
            with self._session_factory.begin() as db:
                entity = db.get(TaskBoardEntity, task_id)
                if entity is None:
                    return None

                if payload.name is not None:
                    entity.name = payload.name.strip()
                if payload.description is not None:
                    entity.description = payload.description.strip()
                if payload.ai_platform is not None:
                    entity.ai_platform = payload.ai_platform.strip() or "hermes"
                if payload.status is not None:
                    entity.status = payload.status

                if "project_id" in payload.model_fields_set:
                    project_id = str(payload.project_id) if payload.project_id is not None else None
                    if project_id is not None and db.get(ProjectEntity, project_id) is None:
                        raise ValueError("project_not_found")
                    entity.project_id = project_id

                if "upstream_task_id" in payload.model_fields_set:
                    upstream_task_id = str(payload.upstream_task_id) if payload.upstream_task_id is not None else None
                    if upstream_task_id == task_id:
                        raise ValueError("upstream_task_cannot_be_self")
                    if upstream_task_id is not None and db.get(TaskBoardEntity, upstream_task_id) is None:
                        raise ValueError("upstream_task_not_found")
                    entity.upstream_task_id = upstream_task_id

                if "parent_task_id" in payload.model_fields_set:
                    parent_task_id = str(payload.parent_task_id) if payload.parent_task_id is not None else None
                    if parent_task_id == task_id:
                        raise ValueError("parent_task_cannot_be_self")
                    if parent_task_id is not None and db.get(TaskBoardEntity, parent_task_id) is None:
                        raise ValueError("parent_task_not_found")
                    entity.parent_task_id = parent_task_id

                entity.updated_at = self.now()
                db.flush()
                return self._build_task_board_item(db, entity)

    def delete_task_board_item(self, task_id: str) -> bool:
        with self._lock:
            with self._session_factory.begin() as db:
                entity = db.get(TaskBoardEntity, task_id)
                if entity is None:
                    return False
                related_rows = db.query(TaskBoardEntity).filter(
                    (TaskBoardEntity.parent_task_id == task_id) | (TaskBoardEntity.upstream_task_id == task_id)
                ).all()
                for row in related_rows:
                    if row.parent_task_id == task_id:
                        row.parent_task_id = None
                    if row.upstream_task_id == task_id:
                        row.upstream_task_id = None
                    row.updated_at = self.now()
                db.delete(entity)
                return True

    def clear_sessions(self) -> int:
        with self._lock:
            with self._session_factory.begin() as db:
                session_ids = [row[0] for row in db.execute(select(SessionEntity.id)).all()]
                if not session_ids:
                    return 0

                db.query(MessageEntity).filter(MessageEntity.session_id.in_(session_ids)).delete(synchronize_session=False)
                db.query(EventEntity).filter(EventEntity.session_id.in_(session_ids)).delete(synchronize_session=False)
                db.query(TaskEntity).filter(TaskEntity.session_id.in_(session_ids)).delete(synchronize_session=False)
                db.query(SessionMetricsEntity).filter(SessionMetricsEntity.session_id.in_(session_ids)).delete(synchronize_session=False)
                db.query(SessionEntity).filter(SessionEntity.id.in_(session_ids)).delete(synchronize_session=False)
                return len(session_ids)

    def get_cockpit(self, session_id: str) -> CockpitResponse | None:
        session = self.get_session(session_id)
        timeline = self.get_timeline(session_id)
        if session is None or timeline is None:
            return None

        with self._session_factory() as db:
            metrics_row = db.get(SessionMetricsEntity, session_id)
            if metrics_row is None:
                return None

            task_rows = db.execute(
                select(TaskEntity).where(TaskEntity.session_id == session_id).order_by(TaskEntity.updated_at.asc())
            ).scalars().all()

            return CockpitResponse(
                session=session,
                tasks=[
                    TaskItem(
                        id=row.id,
                        session_id=row.session_id,
                        title=row.title,
                        lane=row.lane,
                        priority=row.priority,
                        assignee=row.assignee,
                        updated_at=row.updated_at,
                    )
                    for row in task_rows
                ],
                timeline=timeline,
                metrics=SessionMetrics(
                    session_id=metrics_row.session_id,
                    token_in=metrics_row.token_in,
                    token_out=metrics_row.token_out,
                    latency_ms_p50=metrics_row.latency_ms_p50,
                    error_count=metrics_row.error_count,
                    updated_at=metrics_row.updated_at,
                ),
                runtime=build_runtime_state(),
            )

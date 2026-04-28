from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import EventEntity, MessageEntity, SessionEntity, SessionMetricsEntity, TaskEntity
from app.schemas import (
    CockpitResponse,
    EventItem,
    IngestEventRequest,
    MessageItem,
    SessionDetail,
    SessionMetrics,
    SessionSummary,
    TaskItem,
    TimelineResponse,
)


class SqlAlchemySessionStore:
    def __init__(self, database_url: str) -> None:
        self._lock = Lock()
        self._engine = self._build_engine(database_url)
        if database_url.startswith("sqlite"):
            Base.metadata.create_all(self._engine)
        self._session_factory = sessionmaker(self._engine, expire_on_commit=False)

    def _build_engine(self, database_url: str) -> Engine:
        if database_url.startswith("sqlite"):
            engine_kwargs: dict = {"connect_args": {"check_same_thread": False}}
            if database_url.endswith(":memory:"):
                from sqlalchemy.pool import StaticPool

                engine_kwargs["poolclass"] = StaticPool
            return create_engine(database_url, **engine_kwargs)
        return create_engine(database_url)

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
            )

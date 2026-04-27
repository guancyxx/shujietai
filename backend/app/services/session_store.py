from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4

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


class SessionStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._dedupe_keys: set[tuple[str, str]] = set()
        self._session_id_by_external: dict[tuple[str, str], str] = {}
        self._sessions: dict[str, SessionDetail] = {}
        self._messages: dict[str, list[MessageItem]] = {}
        self._events: dict[str, list[EventItem]] = {}
        self._tasks: dict[str, list[TaskItem]] = {}
        self._metrics: dict[str, SessionMetrics] = {}

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def ingest(self, payload: IngestEventRequest) -> tuple[str, bool]:
        with self._lock:
            dedupe_key = (payload.platform, payload.event_id)
            session_id = self._get_or_create_session(payload)
            if dedupe_key in self._dedupe_keys:
                return session_id, True

            self._dedupe_keys.add(dedupe_key)
            self._append_event(session_id, payload)
            self._append_optional_message(session_id, payload)
            self._append_optional_task(session_id, payload)
            self._refresh_metrics(session_id)
            self._refresh_counts(session_id)
            return session_id, False

    def _get_or_create_session(self, payload: IngestEventRequest) -> str:
        key = (payload.platform, payload.external_session_id)
        existing = self._session_id_by_external.get(key)
        if existing:
            return existing

        session_id = f"sess_{uuid4().hex[:12]}"
        self._session_id_by_external[key] = session_id
        self._sessions[session_id] = SessionDetail(
            id=session_id,
            platform=payload.platform,
            external_session_id=payload.external_session_id,
            title=payload.title or f"Session {payload.external_session_id}",
            status="active",
            started_at=self._now(),
            message_count=0,
            task_count=0,
        )
        self._messages[session_id] = []
        self._events[session_id] = []
        self._tasks[session_id] = []
        self._metrics[session_id] = SessionMetrics(
            session_id=session_id,
            token_in=0,
            token_out=0,
            latency_ms_p50=0,
            error_count=0,
            updated_at=self._now(),
        )
        return session_id

    def _append_event(self, session_id: str, payload: IngestEventRequest) -> None:
        self._events[session_id].append(
            EventItem(
                id=payload.event_id,
                session_id=session_id,
                event_type=payload.event_type,
                payload_json=payload.payload_json,
                created_at=self._now(),
            )
        )

    def _append_optional_message(self, session_id: str, payload: IngestEventRequest) -> None:
        if payload.message is None:
            return
        self._messages[session_id].append(
            MessageItem(
                id=f"msg_{uuid4().hex[:10]}",
                session_id=session_id,
                role=payload.message.role,
                content=payload.message.content,
                content_type=payload.message.content_type,
                created_at=self._now(),
                meta_json=payload.message.meta_json,
            )
        )

    def _append_optional_task(self, session_id: str, payload: IngestEventRequest) -> None:
        if payload.task is None:
            return
        self._tasks[session_id].append(
            TaskItem(
                id=f"task_{uuid4().hex[:10]}",
                session_id=session_id,
                title=payload.task.title,
                lane=payload.task.lane,
                priority=payload.task.priority,
                assignee=payload.task.assignee,
                updated_at=self._now(),
            )
        )

    def _refresh_metrics(self, session_id: str) -> None:
        current = self._metrics[session_id]
        message_count = len(self._messages[session_id])
        event_count = len(self._events[session_id])
        self._metrics[session_id] = SessionMetrics(
            session_id=session_id,
            token_in=current.token_in + 10,
            token_out=current.token_out + 8,
            latency_ms_p50=max(100, 100 + event_count * 5),
            error_count=current.error_count,
            updated_at=self._now(),
        )

    def _refresh_counts(self, session_id: str) -> None:
        session = self._sessions[session_id]
        self._sessions[session_id] = SessionDetail(
            id=session.id,
            platform=session.platform,
            external_session_id=session.external_session_id,
            title=session.title,
            status=session.status,
            started_at=session.started_at,
            ended_at=session.ended_at,
            message_count=len(self._messages[session_id]),
            task_count=len(self._tasks[session_id]),
        )

    def list_sessions(self) -> list[SessionSummary]:
        return [
            SessionSummary(
                id=s.id,
                platform=s.platform,
                external_session_id=s.external_session_id,
                title=s.title,
                status=s.status,
                started_at=s.started_at,
                ended_at=s.ended_at,
            )
            for s in self._sessions.values()
        ]

    def get_session(self, session_id: str) -> SessionDetail | None:
        return self._sessions.get(session_id)

    def get_timeline(self, session_id: str) -> TimelineResponse | None:
        if session_id not in self._sessions:
            return None
        return TimelineResponse(
            session_id=session_id,
            messages=self._messages.get(session_id, []),
            events=self._events.get(session_id, []),
        )

    def get_history_messages(self, platform: str, external_session_id: str) -> list[dict[str, str]]:
        with self._lock:
            session_id = self._session_id_by_external.get((platform, external_session_id))
            if session_id is None:
                return []

            history: list[dict[str, str]] = []
            for message in self._messages.get(session_id, []):
                if message.role in ("user", "assistant", "system"):
                    history.append({"role": message.role, "content": message.content})
            return history

    def get_cockpit(self, session_id: str) -> CockpitResponse | None:
        session = self.get_session(session_id)
        timeline = self.get_timeline(session_id)
        metrics = self._metrics.get(session_id)
        if session is None or timeline is None or metrics is None:
            return None
        return CockpitResponse(
            session=session,
            tasks=self._tasks.get(session_id, []),
            timeline=timeline,
            metrics=metrics,
        )


store = SessionStore()

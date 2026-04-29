from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock
from uuid import uuid4

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
        self._project_sequence = 0
        self._projects: dict[str, ProjectItem] = {}
        self._task_board_items: dict[str, TaskBoardItem] = {}
        self._github_service = GitHubProjectService()

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

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session is None:
                return False

            session_events = self._events.pop(session_id, [])
            self._messages.pop(session_id, None)
            self._tasks.pop(session_id, None)
            self._metrics.pop(session_id, None)
            self._session_id_by_external.pop((session.platform, session.external_session_id), None)

            event_keys = {(session.platform, event.id) for event in session_events}
            self._dedupe_keys = {key for key in self._dedupe_keys if key not in event_keys}
            return True

    def clear_sessions(self) -> int:
        with self._lock:
            deleted_count = len(self._sessions)
            self._sessions.clear()
            self._messages.clear()
            self._events.clear()
            self._tasks.clear()
            self._metrics.clear()
            self._session_id_by_external.clear()
            self._dedupe_keys.clear()
            return deleted_count

    def list_project_directory_options(self) -> list[str]:
        return []

    def _next_project_code(self) -> str:
        self._project_sequence += 1
        return f"proj-{self._project_sequence:04d}"

    def list_projects(self) -> list[ProjectItem]:
        with self._lock:
            return sorted(self._projects.values(), key=lambda item: item.created_at)

    def create_project(self, payload: ProjectCreateRequest) -> ProjectItem:
        with self._lock:
            project_code = self._next_project_code()
            now = self._now()
            repository_url = payload.repository_url.strip()
            _owner, repository_name = self._github_service.parse_repository_url(repository_url)
            local_path = self._github_service.default_local_path(repository_url)
            project = ProjectItem(
                id=uuid4(),
                code=project_code,
                name=(payload.name or repository_name).strip(),
                description=payload.description.strip(),
                repository_url=repository_url,
                repository_name=repository_name,
                local_path=local_path,
                created_at=now,
                updated_at=now,
            )
            self._projects[str(project.id)] = project
            return project

    def update_project(self, project_id: str, payload: ProjectUpdateRequest) -> ProjectItem | None:
        with self._lock:
            current = self._projects.get(project_id)
            if current is None:
                return None

            next_name = payload.name.strip() if payload.name is not None else current.name
            next_description = payload.description.strip() if payload.description is not None else current.description

            updated = current.model_copy(
                update={
                    "name": next_name,
                    "description": next_description,
                    "updated_at": self._now(),
                }
            )
            self._projects[project_id] = updated
            return updated

    def delete_project(self, project_id: str) -> bool:
        with self._lock:
            return self._projects.pop(project_id, None) is not None

    def list_task_board_items(self, project_id: str | None = None, keyword: str | None = None) -> list[TaskBoardItem]:
        with self._lock:
            rows = sorted(self._task_board_items.values(), key=lambda item: item.created_at)
            if project_id:
                rows = [item for item in rows if str(item.project_id) == project_id]
            normalized_keyword = (keyword or "").strip().lower()
            if normalized_keyword:
                rows = [
                    item
                    for item in rows
                    if normalized_keyword in f"{item.name} {item.description} {item.ai_platform}".lower()
                ]
            return rows

    def create_task_board_item(self, payload: TaskBoardCreateRequest) -> TaskBoardItem:
        with self._lock:
            project_item = None
            if payload.project_id is not None:
                project_item = self._projects.get(str(payload.project_id))
                if project_item is None:
                    raise ValueError("project_not_found")

            upstream_item = None
            if payload.upstream_task_id is not None:
                upstream_item = self._task_board_items.get(str(payload.upstream_task_id))
                if upstream_item is None:
                    raise ValueError("upstream_task_not_found")

            parent_item = None
            if payload.parent_task_id is not None:
                parent_item = self._task_board_items.get(str(payload.parent_task_id))
                if parent_item is None:
                    raise ValueError("parent_task_not_found")

            now = self._now()
            created = TaskBoardItem(
                id=uuid4(),
                name=payload.name.strip(),
                description=payload.description.strip(),
                ai_platform=(payload.ai_platform or "hermes").strip() or "hermes",
                project_id=payload.project_id,
                project_name=project_item.name if project_item else None,
                upstream_task_id=payload.upstream_task_id,
                upstream_task_name=upstream_item.name if upstream_item else None,
                parent_task_id=payload.parent_task_id,
                parent_task_name=parent_item.name if parent_item else None,
                status=payload.status,
                created_at=now,
                updated_at=now,
            )
            self._task_board_items[str(created.id)] = created
            return created

    def update_task_board_item(self, task_id: str, payload: TaskBoardUpdateRequest) -> TaskBoardItem | None:
        with self._lock:
            current = self._task_board_items.get(task_id)
            if current is None:
                return None

            next_name = payload.name.strip() if payload.name is not None else current.name
            next_description = payload.description.strip() if payload.description is not None else current.description
            next_ai_platform = payload.ai_platform.strip() if payload.ai_platform is not None else current.ai_platform
            next_status = payload.status if payload.status is not None else current.status

            next_project_id = current.project_id
            if "project_id" in payload.model_fields_set:
                next_project_id = payload.project_id
            next_project_name = None
            if next_project_id is not None:
                project_item = self._projects.get(str(next_project_id))
                if project_item is None:
                    raise ValueError("project_not_found")
                next_project_name = project_item.name

            next_upstream_task_id = current.upstream_task_id
            if "upstream_task_id" in payload.model_fields_set:
                next_upstream_task_id = payload.upstream_task_id
            next_upstream_task_name = None
            if next_upstream_task_id is not None:
                if str(next_upstream_task_id) == task_id:
                    raise ValueError("upstream_task_cannot_be_self")
                upstream_item = self._task_board_items.get(str(next_upstream_task_id))
                if upstream_item is None:
                    raise ValueError("upstream_task_not_found")
                next_upstream_task_name = upstream_item.name

            next_parent_task_id = current.parent_task_id
            if "parent_task_id" in payload.model_fields_set:
                next_parent_task_id = payload.parent_task_id
            next_parent_task_name = None
            if next_parent_task_id is not None:
                if str(next_parent_task_id) == task_id:
                    raise ValueError("parent_task_cannot_be_self")
                parent_item = self._task_board_items.get(str(next_parent_task_id))
                if parent_item is None:
                    raise ValueError("parent_task_not_found")
                next_parent_task_name = parent_item.name

            updated = current.model_copy(
                update={
                    "name": next_name,
                    "description": next_description,
                    "ai_platform": next_ai_platform or "hermes",
                    "project_id": next_project_id,
                    "project_name": next_project_name,
                    "upstream_task_id": next_upstream_task_id,
                    "upstream_task_name": next_upstream_task_name,
                    "parent_task_id": next_parent_task_id,
                    "parent_task_name": next_parent_task_name,
                    "status": next_status,
                    "updated_at": self._now(),
                }
            )
            self._task_board_items[task_id] = updated
            return updated

    def delete_task_board_item(self, task_id: str) -> bool:
        with self._lock:
            removed = self._task_board_items.pop(task_id, None)
            if removed is None:
                return False
            for key, value in list(self._task_board_items.items()):
                update_data = {}
                if value.parent_task_id and str(value.parent_task_id) == task_id:
                    update_data["parent_task_id"] = None
                    update_data["parent_task_name"] = None
                if value.upstream_task_id and str(value.upstream_task_id) == task_id:
                    update_data["upstream_task_id"] = None
                    update_data["upstream_task_name"] = None
                if update_data:
                    update_data["updated_at"] = self._now()
                    self._task_board_items[key] = value.model_copy(update=update_data)
            return True

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
            runtime=build_runtime_state(),
        )


store = SessionStore()

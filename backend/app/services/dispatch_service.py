"""Dispatch service — CRUD and state machine for dispatch orchestration layer (ADR-0004).

Manages DispatchTask lifecycle: create, status transitions, crash recovery.
All DB operations use the shared SQLAlchemy session factory.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import DispatchEventEntity, DispatchTaskEntity, MessageEntity, SessionEntity, TaskBoardEntity
from app.schemas import (
    DispatchCreateRequest,
    DispatchEventItem,
    DispatchResumeRequest,
    DispatchTaskItem,
    DispatchTaskStatus,
    normalize_platform,
)
from app.services.title_generator import generate_session_title

logger = logging.getLogger(__name__)

# Valid state transitions: from_status -> set of allowed to_statuses
_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "cancelled"},
    "running": {"completed", "failed", "awaiting_input", "paused", "cancelled", "aborted"},
    "awaiting_input": {"running", "cancelled", "aborted"},
    "paused": {"running", "cancelled", "aborted"},
    "completed": set(),
    "failed": set(),  # terminal
    "cancelled": set(),  # terminal
    "aborted": set(),  # terminal
}

_TERMINAL_STATUSES = {"completed", "failed", "cancelled", "aborted"}
_ACTIVE_STATUSES = {"queued", "running", "awaiting_input", "paused"}
_DISPATCH_NON_TERMINAL_STATUSES = {"queued", "running", "awaiting_input", "paused"}


def _now() -> datetime:
    return datetime.now(UTC)


def _entity_to_item(entity: DispatchTaskEntity) -> DispatchTaskItem:
    return DispatchTaskItem(
        id=entity.id,
        task_board_item_id=entity.task_board_item_id,
        status=entity.status,
        ai_platform=entity.ai_platform,
        external_session_id=entity.external_session_id,
        current_run_id=entity.current_run_id,
        last_sequence=entity.last_sequence or 0,
        config=entity.config or {},
        initial_prompt=entity.initial_prompt,
        error_message=entity.error_message,
        started_at=entity.started_at,
        finished_at=entity.finished_at,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def _event_entity_to_item(entity: DispatchEventEntity) -> DispatchEventItem:
    return DispatchEventItem(
        id=entity.id,
        task_id=entity.task_id,
        seq=entity.seq,
        event_type=entity.event_type,
        event_name=entity.event_name,
        status=entity.status,
        run_id=entity.run_id,
        tool_call_id=entity.tool_call_id,
        payload=entity.payload or {},
        created_at=entity.created_at,
    )


def _build_task_board_dispatch_prompt(item: TaskBoardEntity, project: object | None) -> str:
    project_name = getattr(project, "name", "") if project is not None else ""
    repository_url = getattr(project, "repository_url", "") if project is not None else ""
    lines = [
        "Execute the following task from ShuJieTai task board.",
        "",
        f"Task: {item.name}",
        f"Priority: P{max(0, int(item.priority or 3) - 1)}",
    ]
    if project_name:
        lines.append(f"Project: {project_name}")
    if repository_url:
        lines.append(f"Repository: {repository_url}")
    if item.description:
        lines.extend(["", "Task details:", item.description])
    lines.extend([
        "",
        "Follow the task requirements exactly. Keep progress visible through tool calls and final response.",
    ])
    return "\n".join(lines)


class DispatchService:
    """Stateless service class; receives session_factory on init."""

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    # --- Task board status writeback (ADR-0004 Step 3) ---

    # Map dispatch terminal status -> task board status
    _DISPATCH_TO_TASK_BOARD_STATUS: dict[str, str] = {
        "completed": "completed",
        "failed": "blocked",
        "cancelled": "cancelled",
        "aborted": "cancelled",
    }

    def _writeback_task_board_status(self, task_id: str, dispatch_status: str) -> None:
        """When a dispatch task reaches a terminal status, update linked task_board_item."""
        from app.db.models import TaskBoardEntity

        tb_status = self._DISPATCH_TO_TASK_BOARD_STATUS.get(dispatch_status)
        if tb_status is None:
            return

        with self._session_factory.begin() as db:
            # Find the dispatch task to get task_board_item_id
            dispatch_entity = db.get(DispatchTaskEntity, task_id)
            if dispatch_entity is None or dispatch_entity.task_board_item_id is None:
                return

            tb_entity = db.get(TaskBoardEntity, dispatch_entity.task_board_item_id)
            if tb_entity is None:
                return

            tb_entity.status = tb_status
            tb_entity.updated_at = _now()
            logger.info(
                "Writeback: dispatch task %s -> task_board_item %s status=%s",
                task_id, tb_entity.id, tb_status,
            )

    # --- CRUD ---

    def list_tasks(self, status: str | None = None) -> list[DispatchTaskItem]:
        with self._session_factory.begin() as db:
            stmt = select(DispatchTaskEntity).order_by(DispatchTaskEntity.created_at.desc())
            if status:
                stmt = stmt.where(DispatchTaskEntity.status == status)
            rows = db.execute(stmt).scalars().all()
            return [_entity_to_item(r) for r in rows]

    def get_task(self, task_id: str) -> DispatchTaskItem | None:
        with self._session_factory() as db:
            entity = db.get(DispatchTaskEntity, task_id)
            if entity is None:
                return None
            return _entity_to_item(entity)

    def create_task(self, payload: DispatchCreateRequest) -> DispatchTaskItem:
        config = {
            "system_prompt": payload.system_prompt or "",
            "model": payload.model or "",
            "skills": payload.skills or [],
            "mcp_servers": payload.mcp_servers or [],
        }
        now = _now()
        task_id = f"dt_{uuid4().hex[:12]}"
        run_id = f"dr_{uuid4().hex[:12]}"
        entity = DispatchTaskEntity(
            id=task_id,
            task_board_item_id=payload.task_board_item_id,
            status="queued",
            ai_platform=payload.ai_platform,
            external_session_id=payload.external_session_id or f"dispatch_{task_id}",
            current_run_id=run_id,
            last_sequence=0,
            config=config,
            initial_prompt=payload.initial_prompt,
            error_message=None,
            started_at=None,
            finished_at=None,
            created_at=now,
            updated_at=now,
        )
        with self._session_factory.begin() as db:
            db.add(entity)

        return _entity_to_item(entity)

    def get_active_task_for_task_board_item(self, task_board_item_id: str) -> DispatchTaskItem | None:
        with self._session_factory() as db:
            row = db.execute(
                select(DispatchTaskEntity)
                .where(
                    DispatchTaskEntity.task_board_item_id == task_board_item_id,
                    DispatchTaskEntity.status.in_(_DISPATCH_NON_TERMINAL_STATUSES),
                )
                .order_by(DispatchTaskEntity.created_at.desc())
            ).scalar_one_or_none()
            return _entity_to_item(row) if row is not None else None

    def get_latest_task_for_task_board_item(self, task_board_item_id: str) -> DispatchTaskItem | None:
        """Return the most recent dispatch task for a given task-board item, regardless of status."""
        if not task_board_item_id.strip():
            return None
        with self._session_factory() as db:
            row = db.execute(
                select(DispatchTaskEntity)
                .where(DispatchTaskEntity.task_board_item_id == task_board_item_id)
                .order_by(DispatchTaskEntity.created_at.desc())
            ).scalar_one_or_none()
            return _entity_to_item(row) if row is not None else None

    def get_active_task_by_external_session_id(self, platform: str, external_session_id: str) -> DispatchTaskItem | None:
        normalized_platform = normalize_platform(platform)
        normalized = external_session_id.strip()
        if not normalized:
            return None
        with self._session_factory() as db:
            row = db.execute(
                select(DispatchTaskEntity)
                .where(
                    DispatchTaskEntity.ai_platform == normalized_platform,
                    DispatchTaskEntity.external_session_id == normalized,
                    DispatchTaskEntity.status.in_(_DISPATCH_NON_TERMINAL_STATUSES),
                )
                .order_by(DispatchTaskEntity.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            return _entity_to_item(row) if row is not None else None

    def get_latest_task_by_external_session_id(self, platform: str, external_session_id: str) -> DispatchTaskItem | None:
        normalized_platform = normalize_platform(platform)
        normalized = external_session_id.strip()
        if not normalized:
            return None
        with self._session_factory() as db:
            row = db.execute(
                select(DispatchTaskEntity)
                .where(
                    DispatchTaskEntity.ai_platform == normalized_platform,
                    DispatchTaskEntity.external_session_id == normalized,
                )
                .order_by(DispatchTaskEntity.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            return _entity_to_item(row) if row is not None else None

    def resolve_work_session(self, task_board_item_id: str) -> dict:
        """Resolve the canonical work session for a task-board item.

        Returns a dict with:
          - recommended_action: 'resume' | 'view_history' | 'create_new'
          - active_dispatch_task: the running/awaiting_input/paused dispatch or None
          - latest_dispatch_task: the most recent dispatch (any status) or None
          - task_board_item_id: the resolved item id (passthrough)
        """
        if not task_board_item_id.strip():
            return {
                "task_board_item_id": task_board_item_id,
                "recommended_action": "create_new",
                "active_dispatch_task": None,
                "latest_dispatch_task": None,
            }

        active = self.get_active_task_for_task_board_item(task_board_item_id)
        if active is not None:
            return {
                "task_board_item_id": task_board_item_id,
                "recommended_action": "resume",
                "active_dispatch_task": active,
                "latest_dispatch_task": active,
            }

        latest = self.get_latest_task_for_task_board_item(task_board_item_id)
        if latest is not None:
            return {
                "task_board_item_id": task_board_item_id,
                "recommended_action": "view_history",
                "active_dispatch_task": None,
                "latest_dispatch_task": latest,
            }

        return {
            "task_board_item_id": task_board_item_id,
            "recommended_action": "create_new",
            "active_dispatch_task": None,
            "latest_dispatch_task": None,
        }

    def resolve_session_dispatch(self, platform: str, external_session_id: str) -> dict:
        normalized_platform = normalize_platform(platform)
        normalized = external_session_id.strip()
        if not normalized:
            return {
                "platform": normalized_platform,
                "external_session_id": external_session_id,
                "recommended_action": "create_new",
                "active_dispatch_task": None,
                "latest_dispatch_task": None,
            }

        active = self.get_active_task_by_external_session_id(normalized_platform, normalized)
        if active is not None:
            return {
                "platform": normalized_platform,
                "external_session_id": normalized,
                "recommended_action": "resume",
                "active_dispatch_task": active,
                "latest_dispatch_task": active,
            }

        latest = self.get_latest_task_by_external_session_id(normalized_platform, normalized)
        if latest is not None:
            return {
                "platform": normalized_platform,
                "external_session_id": normalized,
                "recommended_action": "view_history",
                "active_dispatch_task": None,
                "latest_dispatch_task": latest,
            }

        return {
            "platform": normalized_platform,
            "external_session_id": normalized,
            "recommended_action": "create_new",
            "active_dispatch_task": None,
            "latest_dispatch_task": None,
        }

    def list_pending_execution_task_board_items(self, limit: int = 20) -> list[TaskBoardEntity]:
        with self._session_factory() as db:
            rows = db.execute(
                select(TaskBoardEntity)
                .where(TaskBoardEntity.status == "pending_execution")
                .order_by(TaskBoardEntity.updated_at.asc(), TaskBoardEntity.created_at.asc())
                .limit(limit)
            ).scalars().all()
            return [row for row in rows]

    def prerequisites_satisfied(self, task_board_item_id: str) -> bool:
        """Check whether a task-board item's upstream/parent dependencies are completed."""
        with self._session_factory() as db:
            entity = db.get(TaskBoardEntity, task_board_item_id)
            if entity is None:
                return True
            for dep_id in (entity.upstream_task_id, entity.parent_task_id):
                if dep_id is None:
                    continue
                dep = db.get(TaskBoardEntity, dep_id)
                if dep is None or dep.status != "completed":
                    return False
            return True

    def mark_task_board_item_status(self, task_board_item_id: str, status: str) -> bool:
        with self._session_factory.begin() as db:
            entity = db.get(TaskBoardEntity, task_board_item_id)
            if entity is None:
                return False
            entity.status = status
            entity.updated_at = _now()
            return True

    def create_task_for_task_board_item(self, task_board_item_id: str) -> DispatchTaskItem | None:
        with self._session_factory() as db:
            item = db.get(TaskBoardEntity, task_board_item_id)
            if item is None:
                return None
            project = None
            if item.project_id:
                from app.db.models import ProjectEntity
                project = db.get(ProjectEntity, item.project_id)
            prompt = _build_task_board_dispatch_prompt(item, project)
            project_part = f"project_{item.project_id}_" if item.project_id else "task_board_"
            external_session_id = f"{project_part}{item.id}"

        return self.create_task(
            DispatchCreateRequest(
                task_board_item_id=task_board_item_id,
                ai_platform=normalize_platform(item.ai_platform),
                initial_prompt=prompt,
                external_session_id=external_session_id,
            )
        )

    def list_events(self, task_id: str, limit: int = 200, offset: int = 0) -> list[DispatchEventItem]:
        with self._session_factory() as db:
            stmt = (
                select(DispatchEventEntity)
                .where(DispatchEventEntity.task_id == task_id)
                .order_by(DispatchEventEntity.seq.asc(), DispatchEventEntity.created_at.asc())
                .limit(limit)
                .offset(offset)
            )
            rows = db.execute(stmt).scalars().all()
            return [_event_entity_to_item(r) for r in rows]

    def get_event(self, event_id: str) -> DispatchEventItem | None:
        with self._session_factory() as db:
            entity = db.get(DispatchEventEntity, event_id)
            if entity is None:
                return None
            return _event_entity_to_item(entity)

    def add_event(
        self,
        task_id: str,
        event_type: str,
        payload: dict,
        *,
        event_name: str | None = None,
        status: str | None = None,
        run_id: str | None = None,
        tool_call_id: str | None = None,
    ) -> str:
        """Append a dispatch event and return the event ID."""
        event_id = f"de_{uuid4().hex[:12]}"
        with self._session_factory.begin() as db:
            task = db.get(DispatchTaskEntity, task_id)
            if task is None:
                raise ValueError(f"dispatch_task_not_found: {task_id}")

            next_seq = max(0, task.last_sequence or 0) + 1
            now = _now()
            db.add(DispatchEventEntity(
                id=event_id,
                task_id=task_id,
                seq=next_seq,
                event_type=event_type,
                event_name=event_name or event_type,
                status=status,
                run_id=run_id or task.current_run_id,
                tool_call_id=tool_call_id,
                payload=payload,
                created_at=now,
            ))
            task.last_sequence = next_seq
            task.updated_at = now

        return event_id

    def start_new_run(self, task_id: str) -> DispatchTaskItem | None:
        """Create and assign a new run ID for a task run."""
        with self._session_factory.begin() as db:
            entity = db.get(DispatchTaskEntity, task_id)
            if entity is None:
                return None
            now = _now()
            entity.current_run_id = f"dr_{uuid4().hex[:12]}"
            if entity.started_at is None:
                entity.started_at = now
            entity.finished_at = None
            entity.updated_at = now
            db.flush()
            return _entity_to_item(entity)

    # --- State machine ---

    def _transition(self, db: Session, task_id: str, to_status: str, error_message: str | None = None) -> DispatchTaskEntity | None:
        """Attempt a state transition. Returns the updated entity or None if invalid."""
        entity = db.get(DispatchTaskEntity, task_id)
        if entity is None:
            return None

        allowed = _TRANSITIONS.get(entity.status, set())
        if to_status not in allowed:
            return None

        now = _now()
        entity.status = to_status
        entity.updated_at = now

        if to_status == "running" and entity.started_at is None:
            entity.started_at = now
        if to_status in _TERMINAL_STATUSES:
            entity.finished_at = now

        if error_message is not None:
            entity.error_message = error_message
        return entity

    def transition_task(
        self,
        task_id: str,
        to_status: str,
        error_message: str | None = None,
        *,
        emit_status_event: bool = True,
    ) -> DispatchTaskItem | None:
        """Transition a task's status. Returns updated item or None if transition is invalid."""
        with self._session_factory.begin() as db:
            entity = self._transition(db, task_id, to_status, error_message=error_message)
            if entity is None:
                return None
            db.flush()
            item = _entity_to_item(entity)

        if emit_status_event:
            self.add_event(
                task_id,
                "status",
                {
                    "status": to_status,
                    "error_message": error_message,
                },
                event_name="task.status.changed",
                status=to_status,
                run_id=item.current_run_id,
            )

        # Writeback to task board item if terminal status reached
        if to_status in _TERMINAL_STATUSES:
            self._writeback_task_board_status(task_id, to_status)

        return item

    def set_external_session_id(self, task_id: str, external_session_id: str) -> None:
        with self._session_factory.begin() as db:
            entity = db.get(DispatchTaskEntity, task_id)
            if entity is not None:
                entity.external_session_id = external_session_id
                entity.updated_at = _now()

    # --- Resume ---

    def resume_task(self, task_id: str, payload: DispatchResumeRequest) -> DispatchTaskItem | None:
        """Resume an awaiting_input or paused task with user input."""
        task = self.get_task(task_id)
        if task is None:
            return None
        if task.status not in ("awaiting_input", "paused"):
            return None

        # Store the user's resume message as an event
        self.add_event(
            task_id,
            "content_delta",
            {
                "role": "user",
                "content": payload.user_message,
            },
            event_name="message.user.delta",
            status="running",
            run_id=task.current_run_id,
        )

        # Transition to running
        return self.transition_task(task_id, "running", emit_status_event=False)

    # --- Cancel / Abort ---

    def cancel_task(self, task_id: str) -> DispatchTaskItem | None:
        return self.transition_task(task_id, "cancelled")

    def abort_task(self, task_id: str) -> DispatchTaskItem | None:
        return self.transition_task(task_id, "aborted")

    def interrupt_task(self, task_id: str, user_message: str) -> DispatchTaskItem | None:
        """Record an interrupt on a running task — keeps it non-terminal.

        The task stays in 'running' status. Events are appended by the worker.
        """
        _ = user_message  # used in worker-issued events, kept for signature clarity
        return self.get_task(task_id)  # re-read from DB for freshness

    def emergency_stop(self) -> int:
        """Cancel all running/queued tasks. Returns the number of cancelled tasks."""
        with self._session_factory.begin() as db:
            stmt = (
                update(DispatchTaskEntity)
                .where(DispatchTaskEntity.status.in_(["queued", "running", "awaiting_input"]))
                .values(status="cancelled", updated_at=_now())
            )
            result = db.execute(stmt)
            count = result.rowcount or 0

        # Writeback for all cancelled tasks
        if count > 0:
            affected = self.list_tasks(status="cancelled")
            for task in affected:
                self._writeback_task_board_status(task.id, "cancelled")

        return count

    # --- Crash recovery ---

    def recover_running_tasks(self) -> int:
        """Mark all 'running' tasks as 'paused' for crash recovery on startup."""
        with self._session_factory.begin() as db:
            stmt = (
                update(DispatchTaskEntity)
                .where(DispatchTaskEntity.status == "running")
                .values(status="paused", updated_at=_now())
            )
            result = db.execute(stmt)
            return result.rowcount or 0

    # --- Query helpers ---

    def get_active_tasks(self) -> list[DispatchTaskItem]:
        with self._session_factory() as db:
            stmt = (
                select(DispatchTaskEntity)
                .where(DispatchTaskEntity.status.in_(_ACTIVE_STATUSES))
                .order_by(DispatchTaskEntity.created_at.asc())
            )
            rows = db.execute(stmt).scalars().all()
            return [_entity_to_item(r) for r in rows]

    def reconstruct_history(self, task_id: str) -> list[dict[str, str]]:
        """Reconstruct message history from dispatch events for session resumption.

        Merges consecutive content_deltas of the same role into single messages.
        After a task.interrupted event, discards the partial assistant output from
        the old run (it's preserved in UI events but not fed back to the AI).
        """
        events = self.list_events(task_id, limit=10000)
        history: list[dict[str, str]] = []
        saw_interrupted = False
        discarding_old_assistant = False
        for event in events:
            if event.event_type == "interrupted":
                saw_interrupted = True
                discarding_old_assistant = True
                # Discard the stale partial assistant content that was being accumulated
                while history and history[-1]["role"] == "assistant":
                    history.pop()
                continue
            if event.event_type == "content_delta":
                role = event.payload.get("role", "assistant")
                content = event.payload.get("content", "")
                if role in ("user", "assistant", "system") and content:
                    if discarding_old_assistant:
                        if role == "assistant":
                            # Still discarding old-run assistant deltas
                            pass
                        else:
                            # First non-assistant message after interrupt stops discarding
                            discarding_old_assistant = False
                            history.append({"role": role, "content": content})
                    elif not saw_interrupted:
                        if history and history[-1]["role"] == role:
                            history[-1]["content"] += content
                        else:
                            history.append({"role": role, "content": content})
                    else:
                        # After interrupt, post-discard: merge like normal
                        if history and history[-1]["role"] == role:
                            history[-1]["content"] += content
                        else:
                            history.append({"role": role, "content": content})
            elif event.event_type == "content_full":
                role = event.payload.get("role", "assistant")
                content = event.payload.get("content", "")
                if role in ("user", "assistant", "system") and content:
                    if history and history[-1]["role"] == role:
                        history.pop()
                    history.append({"role": role, "content": content})
        return history

    def persist_message_to_session(
        self,
        platform: str,
        external_session_id: str,
        role: str,
        content: str,
        content_type: str = "text/markdown",
    ) -> None:
        """Persist a chat message into the canonical session/message timeline store."""
        if not external_session_id.strip() or not content.strip():
            return

        now = _now()
        with self._session_factory.begin() as db:
            session_entity = db.execute(
                select(SessionEntity).where(
                    SessionEntity.platform == platform,
                    SessionEntity.external_session_id == external_session_id,
                )
            ).scalar_one_or_none()

            if session_entity is None:
                title = generate_session_title(content) if role == "user" else None
                session_entity = SessionEntity(
                    id=f"sess_{uuid4().hex[:12]}",
                    platform=platform,
                    external_session_id=external_session_id,
                    title=title or f"Session {external_session_id}",
                    status="active",
                    started_at=now,
                    ended_at=None,
                    message_count=0,
                    task_count=0,
                )
                db.add(session_entity)

            db.add(
                MessageEntity(
                    id=f"msg_{uuid4().hex[:10]}",
                    session_id=session_entity.id,
                    role=role,
                    content=content,
                    content_type=content_type,
                    created_at=now,
                    meta_json={"source": "dispatch_worker"},
                )
            )
            session_entity.message_count = max(0, session_entity.message_count) + 1
            session_entity.ended_at = now
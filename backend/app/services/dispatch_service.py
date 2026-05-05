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

from app.db.models import DispatchEventEntity, DispatchTaskEntity, MessageEntity, SessionEntity
from app.schemas import (
    DispatchCreateRequest,
    DispatchEventItem,
    DispatchResumeRequest,
    DispatchTaskItem,
    DispatchTaskStatus,
)

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


def _now() -> datetime:
    return datetime.now(UTC)


def _entity_to_item(entity: DispatchTaskEntity) -> DispatchTaskItem:
    return DispatchTaskItem(
        id=entity.id,
        task_board_item_id=entity.task_board_item_id,
        status=entity.status,
        ai_platform=entity.ai_platform,
        external_session_id=entity.external_session_id,
        config=entity.config or {},
        initial_prompt=entity.initial_prompt,
        error_message=entity.error_message,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def _event_entity_to_item(entity: DispatchEventEntity) -> DispatchEventItem:
    return DispatchEventItem(
        id=entity.id,
        task_id=entity.task_id,
        event_type=entity.event_type,
        payload=entity.payload or {},
        created_at=entity.created_at,
    )


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
        entity = DispatchTaskEntity(
            id=task_id,
            task_board_item_id=payload.task_board_item_id,
            status="queued",
            ai_platform=payload.ai_platform,
            external_session_id=f"dispatch_{task_id}",
            config=config,
            initial_prompt=payload.initial_prompt,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        with self._session_factory.begin() as db:
            db.add(entity)

        return _entity_to_item(entity)

    def list_events(self, task_id: str, limit: int = 200, offset: int = 0) -> list[DispatchEventItem]:
        with self._session_factory() as db:
            stmt = (
                select(DispatchEventEntity)
                .where(DispatchEventEntity.task_id == task_id)
                .order_by(DispatchEventEntity.created_at.asc())
                .limit(limit)
                .offset(offset)
            )
            rows = db.execute(stmt).scalars().all()
            return [_event_entity_to_item(r) for r in rows]

    def add_event(self, task_id: str, event_type: str, payload: dict) -> str:
        """Append a dispatch event and return the event ID."""
        event_id = f"de_{uuid4().hex[:12]}"
        with self._session_factory.begin() as db:
            db.add(DispatchEventEntity(
                id=event_id,
                task_id=task_id,
                event_type=event_type,
                payload=payload,
                created_at=_now(),
            ))
        return event_id

    # --- State machine ---

    def _transition(self, db: Session, task_id: str, to_status: str, error_message: str | None = None) -> DispatchTaskEntity | None:
        """Attempt a state transition. Returns the updated entity or None if invalid."""
        entity = db.get(DispatchTaskEntity, task_id)
        if entity is None:
            return None

        allowed = _TRANSITIONS.get(entity.status, set())
        if to_status not in allowed:
            return None

        entity.status = to_status
        entity.updated_at = _now()
        if error_message is not None:
            entity.error_message = error_message
        return entity

    def transition_task(self, task_id: str, to_status: str, error_message: str | None = None) -> DispatchTaskItem | None:
        """Transition a task's status. Returns updated item or None if transition is invalid."""
        with self._session_factory.begin() as db:
            entity = self._transition(db, task_id, to_status, error_message=error_message)
            if entity is None:
                return None
            db.flush()
            item = _entity_to_item(entity)

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
        self.add_event(task_id, "content_delta", {
            "role": "user",
            "content": payload.user_message,
        })

        # Transition to running
        return self.transition_task(task_id, "running")

    # --- Cancel / Abort ---

    def cancel_task(self, task_id: str) -> DispatchTaskItem | None:
        return self.transition_task(task_id, "cancelled")

    def abort_task(self, task_id: str) -> DispatchTaskItem | None:
        return self.transition_task(task_id, "aborted")

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
        """Reconstruct message history from dispatch events for session resumption."""
        events = self.list_events(task_id, limit=10000)
        history: list[dict[str, str]] = []
        for event in events:
            if event.event_type == "content_delta":
                role = event.payload.get("role", "assistant")
                content = event.payload.get("content", "")
                if role in ("user", "assistant", "system") and content:
                    history.append({"role": role, "content": content})
            elif event.event_type == "content_full":
                role = event.payload.get("role", "assistant")
                content = event.payload.get("content", "")
                if role in ("user", "assistant", "system") and content:
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
                session_entity = SessionEntity(
                    id=f"sess_{uuid4().hex[:12]}",
                    platform=platform,
                    external_session_id=external_session_id,
                    title=f"Session {external_session_id}",
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
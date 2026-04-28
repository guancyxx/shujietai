from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


TaskLane = Literal["todo", "doing", "done"]
MessageRole = Literal["user", "assistant", "system", "tool"]


class IngestMessagePayload(BaseModel):
    role: MessageRole
    content: str
    content_type: str = "text/plain"
    meta_json: dict[str, Any] = Field(default_factory=dict)


class IngestTaskPayload(BaseModel):
    title: str
    lane: TaskLane = "todo"
    priority: int = 3
    assignee: str | None = None


class IngestEventRequest(BaseModel):
    platform: str
    event_id: str
    event_type: str
    external_session_id: str
    title: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    message: IngestMessagePayload | None = None
    task: IngestTaskPayload | None = None


class IngestEventResponse(BaseModel):
    request_id: str
    duplicate: bool
    session_id: str
    event_id: str


class HermesWebhookMessagePayload(BaseModel):
    id: str | None = None
    role: MessageRole
    content: str
    content_type: str = "text/plain"
    meta_json: dict[str, Any] = Field(default_factory=dict)


class HermesWebhookEventRequest(BaseModel):
    event_id: str
    event_type: str
    external_session_id: str
    title: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)
    message: HermesWebhookMessagePayload | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class HermesChatRequest(BaseModel):
    external_session_id: str
    user_message: str = Field(min_length=1, max_length=8000)
    title: str | None = None


class HermesChatResponse(BaseModel):
    request_id: str
    session_id: str
    event_id: str
    assistant_message: str


class SessionSummary(BaseModel):
    id: str
    platform: str
    external_session_id: str
    title: str
    status: str
    started_at: datetime
    ended_at: datetime | None = None


class SessionDetail(SessionSummary):
    message_count: int
    task_count: int


class MessageItem(BaseModel):
    id: str
    session_id: str
    role: MessageRole
    content: str
    content_type: str
    created_at: datetime
    meta_json: dict[str, Any] = Field(default_factory=dict)


class EventItem(BaseModel):
    id: str
    session_id: str
    event_type: str
    payload_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class TimelineResponse(BaseModel):
    session_id: str
    messages: list[MessageItem]
    events: list[EventItem]


class TaskItem(BaseModel):
    id: str
    session_id: str
    title: str
    lane: TaskLane
    priority: int
    assignee: str | None = None
    updated_at: datetime


class SessionMetrics(BaseModel):
    session_id: str
    token_in: int = 0
    token_out: int = 0
    latency_ms_p50: int = 0
    error_count: int = 0
    updated_at: datetime


class CockpitResponse(BaseModel):
    session: SessionDetail
    tasks: list[TaskItem]
    timeline: TimelineResponse
    metrics: SessionMetrics


class DeadLetterItem(BaseModel):
    id: str
    event_id: str
    platform: str
    external_session_id: str
    event_type: str
    request_id: str
    payload_json: dict[str, Any] = Field(default_factory=dict)
    message_json: dict[str, Any] | None = None
    task_json: dict[str, Any] | None = None
    error_message: str
    attempt_count: int
    replay_count: int = 0
    replayed_at: datetime | None = None
    replayed_by: str | None = None
    created_at: datetime


class DeadLetterListResponse(BaseModel):
    items: list[DeadLetterItem]


class DeadLetterReplayResponse(BaseModel):
    id: str
    status: Literal["replayed", "failed"]
    detail: str


class DeadLetterReplayRequest(BaseModel):
    force: bool = False

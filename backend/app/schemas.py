from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


TaskLane = Literal["todo", "doing", "done"]
TaskBoardStatus = Literal["draft", "in_progress", "blocked", "completed", "cancelled"]
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
    platform: str | None = None
    system_prompt: str | None = Field(default=None, max_length=4000)


class RuntimePreferenceUpdateRequest(BaseModel):
    selected_model: str | None = None
    selected_skills: list[str] | None = None
    selected_mcp_servers: list[str] | None = None


class SystemConfigUpdateRequest(BaseModel):
    github_token: str = Field(default="", max_length=512)


class SystemConfigResponse(BaseModel):
    github_token_configured: bool


class ProjectCreateRequest(BaseModel):
    repository_url: str = Field(min_length=1, max_length=1024)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class GitHubRepoOption(BaseModel):
    name: str
    full_name: str
    url: str
    description: str = ""


class GitHubRepoCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    private: bool = False


class ProjectItem(BaseModel):
    id: UUID
    code: str
    name: str
    description: str
    repository_url: str
    repository_name: str
    local_path: str
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    items: list[ProjectItem]


class TaskBoardCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4000)
    ai_platform: str = Field(default="hermes", min_length=1, max_length=64)
    project_id: UUID | None = None
    parent_task_id: UUID | None = None
    upstream_task_id: UUID | None = None
    status: TaskBoardStatus = "draft"


class TaskBoardUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    ai_platform: str | None = Field(default=None, min_length=1, max_length=64)
    project_id: UUID | None = None
    parent_task_id: UUID | None = None
    upstream_task_id: UUID | None = None
    status: TaskBoardStatus | None = None


class TaskBoardItem(BaseModel):
    id: UUID
    name: str
    description: str
    ai_platform: str
    project_id: UUID | None = None
    project_name: str | None = None
    project_repository_url: str | None = None
    project_repository_name: str | None = None
    upstream_task_id: UUID | None = None
    upstream_task_name: str | None = None
    parent_task_id: UUID | None = None
    parent_task_name: str | None = None
    status: TaskBoardStatus
    created_at: datetime
    updated_at: datetime


class TaskBoardListResponse(BaseModel):
    items: list[TaskBoardItem]


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


class RuntimeSkillItem(BaseModel):
    name: str
    description: str = ""


class RuntimeModelItem(BaseModel):
    name: str
    provider: str = ""


class RuntimeState(BaseModel):
    current_model: str
    current_model_provider: str = ""
    selected_model: str
    selected_model_provider: str = ""
    available_models: list[str] = Field(default_factory=list)
    available_model_items: list[RuntimeModelItem] = Field(default_factory=list)
    selected_skills: list[str] = Field(default_factory=list)
    available_skills: list[str] = Field(default_factory=list)
    available_skill_items: list[RuntimeSkillItem] = Field(default_factory=list)
    selected_mcp_servers: list[str] = Field(default_factory=list)
    available_mcp_servers: list[str] = Field(default_factory=list)


class CockpitResponse(BaseModel):
    session: SessionDetail
    tasks: list[TaskItem]
    timeline: TimelineResponse
    metrics: SessionMetrics
    runtime: RuntimeState


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


# --- Dispatch Orchestration Layer (ADR-0004) ---

DispatchTaskStatus = Literal[
    "queued", "running", "awaiting_input", "paused",
    "completed", "failed", "cancelled", "aborted",
]


class DispatchCreateRequest(BaseModel):
    task_board_item_id: str | None = Field(default=None, max_length=64)
    ai_platform: str = Field(default="hermes", min_length=1, max_length=64)
    initial_prompt: str = Field(min_length=1, max_length=16000)
    system_prompt: str | None = Field(default=None, max_length=4000)
    model: str | None = Field(default=None, max_length=128)
    skills: list[str] | None = None
    mcp_servers: list[str] | None = None


class DispatchResumeRequest(BaseModel):
    user_message: str = Field(min_length=1, max_length=8000)


class DispatchTaskItem(BaseModel):
    id: str
    task_board_item_id: str | None = None
    status: DispatchTaskStatus
    ai_platform: str
    external_session_id: str | None = None
    current_run_id: str | None = None
    last_sequence: int = 0
    config: dict[str, Any] = Field(default_factory=dict)
    initial_prompt: str
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DispatchTaskListResponse(BaseModel):
    items: list[DispatchTaskItem]


class DispatchEventItem(BaseModel):
    id: str
    task_id: str
    seq: int = 0
    event_type: str
    event_name: str = ""
    status: str | None = None
    run_id: str | None = None
    tool_call_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class DispatchEventListResponse(BaseModel):
    items: list[DispatchEventItem]


class EmergencyStopResponse(BaseModel):
    cancelled_count: int

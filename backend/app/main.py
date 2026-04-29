from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import (
    DeadLetterListResponse,
    DeadLetterReplayRequest,
    DeadLetterReplayResponse,
    GitHubRepoCreateRequest,
    GitHubRepoOption,
    HermesChatRequest,
    HermesChatResponse,
    HermesWebhookEventRequest,
    IngestEventRequest,
    IngestEventResponse,
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectUpdateRequest,
    RuntimePreferenceUpdateRequest,
    SystemConfigResponse,
    SystemConfigUpdateRequest,
    TaskBoardCreateRequest,
    TaskBoardListResponse,
    TaskBoardUpdateRequest,
)
from app.services.hermes_runtime_catalog import build_runtime_state, get_selected_model, set_runtime_preferences
from app.services.github_project_service import GitHubProjectService
from app.services.system_config_service import SystemConfigService
from app.services.cockpit_service import get_cockpit_by_session
from app.services.ingest_retry_service import DeadLetterQuery, IngestRetryService
from app.services.retry_worker import RetryWorkerConfig, run_retry_loop
from app.services.store_factory import build_store
from app.connectors.registry import build_default_registry

store = build_store()
github_project_service = GitHubProjectService()
config_session_factory = store.session_factory if hasattr(store, "session_factory") else None
system_config_service = SystemConfigService(config_session_factory)
connector_registry = build_default_registry()
retry_service = None
retry_counters = {
    "ingest_success_total": 0,
    "ingest_retry_total": 0,
    "ingest_dlq_total": 0,
}
if hasattr(store, "session_factory"):
    retry_service = IngestRetryService(store.session_factory)


def _build_retry_worker_config() -> RetryWorkerConfig:
    max_retries = int(os.getenv("INGEST_MAX_RETRIES", "3"))
    delays_raw = os.getenv("INGEST_RETRY_DELAYS", "1,3,10")
    backoff = [int(item.strip()) for item in delays_raw.split(",") if item.strip()]
    loop_interval_seconds = float(os.getenv("INGEST_RETRY_LOOP_INTERVAL_SECONDS", "1"))
    return RetryWorkerConfig(
        enabled=True,
        loop_interval_seconds=loop_interval_seconds,
        max_retries=max_retries,
        backoff_seconds=backoff,
    )


def _build_retry_tick_hook(counters: dict[str, int]):
    def tick_hook(result) -> None:
        counters["ingest_retry_total"] += result.retried_count
        counters["ingest_success_total"] += result.succeeded_count
        counters["ingest_dlq_total"] += result.dead_letter_count

    return tick_hook


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    retry_task = None
    if retry_service is not None:
        retry_enabled = os.getenv("INGEST_RETRY_ENABLED", "true").lower() == "true"
        if retry_enabled:
            config = _build_retry_worker_config()
            retry_task = asyncio.create_task(
                run_retry_loop(
                    retry_service=retry_service,
                    ingest_callable=store.ingest,
                    config=config,
                    on_tick=_build_retry_tick_hook(retry_counters),
                )
            )
            app_instance.state.retry_task = retry_task

    try:
        yield
    finally:
        existing_retry_task = getattr(app_instance.state, "retry_task", None)
        if existing_retry_task is not None:
            existing_retry_task.cancel()
            try:
                await existing_retry_task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="ShuJieTai API", version="0.1.0", lifespan=lifespan)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid4()))
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


@app.get("/api/v1/health")
def health() -> dict[str, object]:
    return {
        "status": "healthy",
        "service": "shujietai-backend",
        "metrics": {
            "ingest_success_total": retry_counters["ingest_success_total"],
            "ingest_retry_total": retry_counters["ingest_retry_total"],
            "ingest_dlq_total": retry_counters["ingest_dlq_total"],
        },
    }


def _build_history_messages(history_messages: list[dict[str, str]], user_message: str) -> list[dict[str, str]]:
    messages = [
        {
            "role": message["role"],
            "content": message["content"],
        }
        for message in history_messages
        if message.get("role") in {"system", "user", "assistant"} and message.get("content")
    ]
    messages.append({"role": "user", "content": user_message})
    return messages


def _ask_hermes_via_api(messages: list[dict[str, str]], model_override: str | None = None) -> str:
    base_url = os.getenv("HERMES_API_BASE_URL", "http://host.docker.internal:8642/v1").rstrip("/")
    api_key = os.getenv("HERMES_API_KEY", "")
    model = model_override or os.getenv("HERMES_MODEL", "gpt-5.3-codex")
    timeout_seconds = float(os.getenv("HERMES_API_TIMEOUT_SECONDS", "120"))

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    response = httpx.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json={"model": model, "messages": messages},
        timeout=timeout_seconds,
    )
    response.raise_for_status()

    payload = response.json()
    content = payload.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    if not content:
        raise RuntimeError("hermes_empty_response")
    return content


def _resolve_provider_for_model(model_name: str | None) -> str:
    if not model_name:
        return ""
    try:
        runtime = build_runtime_state()
    except Exception:
        return ""

    for item in runtime.available_model_items:
        if item.name == model_name and item.provider:
            return item.provider
    return ""


def _ask_hermes_via_cli(
    messages: list[dict[str, str]],
    model_override: str | None = None,
    provider_override: str | None = None,
) -> str:
    from subprocess import run

    hermes_bin = os.getenv("HERMES_BIN", "hermes")
    timeout_seconds = float(os.getenv("HERMES_API_TIMEOUT_SECONDS", "120"))

    prompt_lines: list[str] = ["Conversation history:"]
    for message in messages[:-1]:
        prompt_lines.append(f"{message['role']}: {message['content']}")
    prompt_lines.append("Now reply to the latest user message:")
    prompt_lines.append(messages[-1]["content"])
    prompt = "\n".join(prompt_lines)

    command: list[str] = [hermes_bin]
    if provider_override:
        command.extend(["--provider", provider_override])
    if model_override:
        command.extend(["-m", model_override])
    command.extend(["-z", prompt])

    result = run(
        command,
        capture_output=True,
        text=True,
        timeout=int(timeout_seconds),
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("hermes_command_failed")
    content = result.stdout.strip()
    if not content:
        raise RuntimeError("hermes_empty_response")
    return content


def ask_hermes_response(
    history_messages: list[dict[str, str]],
    user_message: str,
) -> str:
    messages = _build_history_messages(history_messages, user_message)
    model_for_request = get_selected_model() or os.getenv("HERMES_MODEL", "").strip()
    provider_for_request = _resolve_provider_for_model(model_for_request)

    try:
        return _ask_hermes_via_api(messages, model_override=model_for_request)
    except httpx.HTTPError:
        cli_fallback_enabled = os.getenv("HERMES_CLI_FALLBACK_ENABLED", "1") == "1"
        if not cli_fallback_enabled:
            raise
        return _ask_hermes_via_cli(
            messages,
            model_override=model_for_request,
            provider_override=provider_for_request,
        )


def _parse_since_datetime(since: str) -> datetime:
    normalized = since.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    return datetime.fromisoformat(normalized)


def _ingest_and_build_response(payload: IngestEventRequest, request: Request) -> IngestEventResponse:
    request_id = request.headers.get("x-request-id", str(uuid4()))
    try:
        session_id, duplicate = store.ingest(payload)
        retry_counters["ingest_success_total"] += 1
    except Exception as exc:
        if retry_service is not None:
            retry_service.enqueue_failed_ingest(payload=payload, request_id=request_id, error_message=str(exc))
            retry_counters["ingest_retry_total"] += 1
            session_id = f"pending_{payload.external_session_id}"
            duplicate = False
        else:
            raise
    return IngestEventResponse(
        request_id=request_id,
        duplicate=duplicate,
        session_id=session_id,
        event_id=payload.event_id,
    )


@app.post("/api/v1/events/ingest", response_model=IngestEventResponse)
def ingest_event(payload: IngestEventRequest, request: Request) -> IngestEventResponse:
    return _ingest_and_build_response(payload, request)


@app.post("/api/v1/connectors/hermes/webhook", response_model=IngestEventResponse)
def ingest_hermes_webhook(payload: HermesWebhookEventRequest, request: Request) -> IngestEventResponse:
    hermes_adapter = connector_registry.get("hermes")
    ingest_payload = hermes_adapter.to_ingest_event(payload)
    return _ingest_and_build_response(ingest_payload, request)


@app.post("/api/v1/connectors/hermes/chat", response_model=HermesChatResponse)
def hermes_chat(payload: HermesChatRequest, request: Request) -> HermesChatResponse:
    selected_platform = (payload.platform or "hermes").strip() or "hermes"
    history_messages = store.get_history_messages(selected_platform, payload.external_session_id)
    try:
        assistant_message = ask_hermes_response(
            history_messages,
            payload.user_message,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="hermes_unavailable") from exc

    user_event_id = f"evt_user_{uuid4().hex}"
    user_ingest = IngestEventRequest(
        platform=selected_platform,
        event_id=user_event_id,
        event_type="message_created",
        external_session_id=payload.external_session_id,
        title=payload.title,
        payload_json={"source": "shujietai-chat"},
        message={"role": "user", "content": payload.user_message},
    )
    session_id, _ = store.ingest(user_ingest)

    assistant_event_id = f"evt_assistant_{uuid4().hex}"
    assistant_ingest = IngestEventRequest(
        platform=selected_platform,
        event_id=assistant_event_id,
        event_type="message_created",
        external_session_id=payload.external_session_id,
        title=payload.title,
        payload_json={"source": "shujietai-chat"},
        message={"role": "assistant", "content": assistant_message},
    )
    store.ingest(assistant_ingest)

    request_id = request.headers.get("x-request-id", str(uuid4()))
    return HermesChatResponse(
        request_id=request_id,
        session_id=session_id,
        event_id=assistant_event_id,
        assistant_message=assistant_message,
    )


@app.get("/api/v1/dlq", response_model=DeadLetterListResponse)
def list_dead_letters(
    limit: int = Query(default=50, ge=1, le=200),
    only_unreplayed: bool = Query(default=False),
    platform: str | None = Query(default=None),
    since: str | None = Query(default=None),
) -> DeadLetterListResponse:
    if retry_service is None:
        raise HTTPException(status_code=503, detail="retry_service_unavailable")

    since_dt = None
    if since is not None:
        try:
            since_dt = _parse_since_datetime(since)
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid_since") from None

    query = DeadLetterQuery(
        limit=limit,
        only_unreplayed=only_unreplayed,
        platform=platform,
        since=since_dt,
    )
    items = retry_service.list_dead_letters(query=query)
    return DeadLetterListResponse(items=items)


@app.post("/api/v1/dlq/{dlq_id}/replay", response_model=DeadLetterReplayResponse)
def replay_dead_letter(dlq_id: str, request: Request, payload: DeadLetterReplayRequest | None = None) -> DeadLetterReplayResponse:
    if retry_service is None:
        raise HTTPException(status_code=503, detail="retry_service_unavailable")
    replayed_by = request.headers.get("x-replayed-by", "system")
    force = payload.force if payload is not None else False
    result = retry_service.replay_dead_letter(
        dlq_id=dlq_id,
        ingest_callable=store.ingest,
        replayed_by=replayed_by,
        force=force,
    )
    if result.status == "replayed":
        retry_counters["ingest_success_total"] += 1
        return DeadLetterReplayResponse(id=dlq_id, status="replayed", detail=result.detail)
    if result.detail == "dead_letter_not_found":
        raise HTTPException(status_code=404, detail=result.detail)
    if result.detail == "dead_letter_already_replayed":
        raise HTTPException(status_code=409, detail=result.detail)
    raise HTTPException(status_code=409, detail=result.detail)


@app.get("/api/v1/runtime/catalog")
def get_runtime_catalog(platform: str = Query(default="hermes")):
    normalized_platform = (platform or "hermes").strip() or "hermes"
    available_platforms = connector_registry.names()
    if normalized_platform not in available_platforms:
        raise HTTPException(status_code=404, detail="platform_not_supported")

    runtime = build_runtime_state()
    runtime_dict = runtime.model_dump()
    runtime_dict["platform"] = normalized_platform
    runtime_dict["available_platforms"] = available_platforms
    return runtime_dict


@app.put("/api/v1/runtime/preferences")
def update_runtime_preferences(payload: RuntimePreferenceUpdateRequest):
    set_runtime_preferences(
        selected_model=payload.selected_model,
        selected_skills=payload.selected_skills,
        selected_mcp_servers=payload.selected_mcp_servers,
    )
    return build_runtime_state().model_dump()


@app.get("/api/v1/system/config", response_model=SystemConfigResponse)
def get_system_config() -> SystemConfigResponse:
    return system_config_service.get_config()


@app.put("/api/v1/system/config/github-token", response_model=SystemConfigResponse)
def update_github_token(payload: SystemConfigUpdateRequest) -> SystemConfigResponse:
    system_config_service.update_github_token(payload.github_token)
    return system_config_service.get_config()


@app.get("/api/v1/projects/github/repos", response_model=list[GitHubRepoOption])
def list_github_repositories() -> list[GitHubRepoOption]:
    try:
        token = system_config_service.get_github_token()
        return github_project_service.list_repositories(token_override=token)
    except RuntimeError as exc:
        detail = str(exc)
        if detail in {"gh_cli_unavailable", "github_api_failed"}:
            raise HTTPException(status_code=503, detail=detail) from exc
        raise HTTPException(status_code=502, detail=detail) from exc


@app.post("/api/v1/projects/github/repos", response_model=GitHubRepoOption)
def create_github_repository(payload: GitHubRepoCreateRequest) -> GitHubRepoOption:
    try:
        return github_project_service.create_repository(payload)
    except RuntimeError as exc:
        detail = str(exc)
        if detail == "gh_cli_unavailable":
            raise HTTPException(status_code=503, detail=detail) from exc
        raise HTTPException(status_code=502, detail=detail) from exc


@app.get("/api/v1/projects", response_model=ProjectListResponse)
def list_projects() -> ProjectListResponse:
    return ProjectListResponse(items=store.list_projects())


@app.post("/api/v1/projects")
def create_project(payload: ProjectCreateRequest):
    try:
        return store.create_project(payload)
    except ValueError as exc:
        detail = str(exc)
        if detail in {"invalid_github_repository_url", "local_path_outside_workspace"}:
            raise HTTPException(status_code=422, detail=detail) from exc
        raise


@app.patch("/api/v1/projects/{project_id}")
def update_project(project_id: str, payload: ProjectUpdateRequest):
    item = store.update_project(project_id, payload)
    if item is None:
        raise HTTPException(status_code=404, detail="project_not_found")
    return item


@app.delete("/api/v1/projects/{project_id}")
def delete_project(project_id: str):
    deleted = store.delete_project(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="project_not_found")
    return {"deleted": 1, "project_id": project_id}


@app.get("/api/v1/task-board", response_model=TaskBoardListResponse)
def list_task_board_items(
    project_id: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
) -> TaskBoardListResponse:
    return TaskBoardListResponse(items=store.list_task_board_items(project_id=project_id, keyword=keyword))


@app.post("/api/v1/task-board")
def create_task_board_item(payload: TaskBoardCreateRequest):
    try:
        return store.create_task_board_item(payload)
    except ValueError as exc:
        detail = str(exc)
        if detail in {
            "project_not_found",
            "upstream_task_not_found",
            "parent_task_not_found",
        }:
            raise HTTPException(status_code=422, detail=detail) from exc
        raise


@app.patch("/api/v1/task-board/{task_id}")
def update_task_board_item(task_id: str, payload: TaskBoardUpdateRequest):
    try:
        item = store.update_task_board_item(task_id, payload)
    except ValueError as exc:
        detail = str(exc)
        if detail in {
            "project_not_found",
            "upstream_task_not_found",
            "parent_task_not_found",
            "upstream_task_cannot_be_self",
            "parent_task_cannot_be_self",
        }:
            raise HTTPException(status_code=422, detail=detail) from exc
        raise
    if item is None:
        raise HTTPException(status_code=404, detail="task_board_item_not_found")
    return item


@app.delete("/api/v1/task-board/{task_id}")
def delete_task_board_item(task_id: str):
    deleted = store.delete_task_board_item(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="task_board_item_not_found")
    return {"deleted": 1, "task_id": task_id}


@app.get("/api/v1/sessions")
def list_sessions():
    return store.list_sessions()


@app.delete("/api/v1/sessions/{session_id}")
def delete_session(session_id: str):
    deleted = store.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="session_not_found")
    return {"deleted": 1, "session_id": session_id}


@app.delete("/api/v1/sessions")
def clear_sessions():
    deleted_count = store.clear_sessions()
    return {"deleted": deleted_count}


@app.get("/api/v1/sessions/{session_id}")
def get_session(session_id: str):
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    return session


@app.get("/api/v1/sessions/{session_id}/timeline")
def get_timeline(session_id: str):
    timeline = store.get_timeline(session_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    return timeline


@app.get("/api/v1/board/cockpit")
def get_cockpit(session_id: str):
    cockpit = get_cockpit_by_session(store, session_id)
    if cockpit is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    return cockpit

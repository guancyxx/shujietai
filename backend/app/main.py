from __future__ import annotations
import asyncio
import json as json_module
import os
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

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
from app.services.hermes_runtime_catalog import build_runtime_state, get_selected_model, invalidate_runtime_cache, set_runtime_preferences
from app.services.github_project_service import GitHubProjectService
from app.services.system_config_service import SystemConfigService
from app.services.cockpit_service import get_cockpit_by_session
from app.services.ingest_retry_service import DeadLetterQuery, IngestRetryService
from app.services.retry_worker import RetryWorkerConfig, run_retry_loop
from app.services.store_factory import build_store
from app.services.dispatch_service import DispatchService
from app.services.dispatch_worker import DispatchWorkerPool
from app.services.pending_execution_worker import PendingExecutionWorkerConfig, run_pending_execution_loop
from app.services.ws_manager import WsManager
from app.connectors.registry import register_defaults, list_platforms
from app.connectors.hermes import HermesConnectorAdapter

class _ConnectorAdapterRegistry:
    def __init__(self) -> None:
        self._adapters = {"hermes": HermesConnectorAdapter()}

    def get(self, name: str):
        return self._adapters[name]

    def names(self) -> list[str]:
        return sorted(set(self._adapters.keys()) | set(list_platforms()))


connector_registry = _ConnectorAdapterRegistry()

store = build_store()
github_project_service = GitHubProjectService()
config_session_factory = store.session_factory if hasattr(store, "session_factory") else None
system_config_service = SystemConfigService(config_session_factory)
register_defaults()
retry_service = None
retry_counters = {
    "ingest_success_total": 0,
    "ingest_retry_total": 0,
    "ingest_dlq_total": 0,
}
if hasattr(store, "session_factory"):
    retry_service = IngestRetryService(store.session_factory)

ws_manager = WsManager()
dispatch_service = DispatchService(store.session_factory) if hasattr(store, "session_factory") else None
worker_pool = DispatchWorkerPool(dispatch_service, ws_manager) if dispatch_service else None


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


def _build_pending_execution_worker_config() -> PendingExecutionWorkerConfig:
    return PendingExecutionWorkerConfig(
        enabled=os.getenv("PENDING_EXECUTION_WORKER_ENABLED", "true").lower() == "true",
        loop_interval_seconds=float(os.getenv("PENDING_EXECUTION_WORKER_INTERVAL_SECONDS", "2")),
        batch_size=int(os.getenv("PENDING_EXECUTION_WORKER_BATCH_SIZE", "20")),
    )


def _build_retry_tick_hook(counters: dict[str, int]):
    def tick_hook(result) -> None:
        counters["ingest_retry_total"] += result.retried_count
        counters["ingest_success_total"] += result.succeeded_count
        counters["ingest_dlq_total"] += result.dead_letter_count

    return tick_hook


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    # Crash recovery: mark any orphaned 'running' tasks as 'paused'
    if dispatch_service is not None:
        recovered = dispatch_service.recover_running_tasks()
        if recovered > 0:
            import logging
            logging.getLogger(__name__).warning(
                "Recovered %d orphaned dispatch tasks (set to paused)", recovered,
            )

    # Attach singletons to app.state for route access
    app_instance.state.dispatch_service = dispatch_service
    app_instance.state.worker_pool = worker_pool
    app_instance.state.ws_manager = ws_manager

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

    pending_execution_task = None
    if dispatch_service is not None and worker_pool is not None:
        pending_config = _build_pending_execution_worker_config()
        if pending_config.enabled:
            pending_execution_task = asyncio.create_task(
                run_pending_execution_loop(
                    dispatch_service=dispatch_service,
                    worker_pool=worker_pool,
                    config=pending_config,
                    ingest_fn=store.ingest,
                ),
                name="pending-execution-worker",
            )
            app_instance.state.pending_execution_task = pending_execution_task

    try:
        yield
    finally:
        existing_pending_task = getattr(app_instance.state, "pending_execution_task", None)
        if existing_pending_task is not None:
            existing_pending_task.cancel()
            try:
                await existing_pending_task
            except asyncio.CancelledError:
                pass

        # Cancel dispatch worker pool tasks
        if worker_pool is not None:
            worker_pool.cancel_all()

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

# Dispatch orchestration routes (ADR-0004)
from app.api.routes_dispatch import router as dispatch_router
from app.api.routes_ws import router as ws_router
app.include_router(dispatch_router)
app.include_router(ws_router)


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


def _build_history_messages(history_messages: list[dict[str, str]], user_message: str, system_prompt: str | None = None) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system_prompt and system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt.strip()})
    messages.extend(
        {
            "role": message["role"],
            "content": message["content"],
        }
        for message in history_messages
        if message.get("role") in {"system", "user", "assistant"} and message.get("content")
    )
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
    system_prompt: str | None = None,
) -> str:
    messages = _build_history_messages(history_messages, user_message, system_prompt=system_prompt)
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
            system_prompt=payload.system_prompt,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="hermes_unavailable") from exc

    if payload.system_prompt and payload.system_prompt.strip() and not history_messages:
        system_event_id = f"evt_system_{uuid4().hex}"
        system_ingest = IngestEventRequest(
            platform=selected_platform,
            event_id=system_event_id,
            event_type="message_created",
            external_session_id=payload.external_session_id,
            title=payload.title,
            payload_json={"source": "shujietai-chat"},
            message={"role": "system", "content": payload.system_prompt.strip()},
        )
        store.ingest(system_ingest)

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


async def _stream_hermes_chat(payload: HermesChatRequest):
    """Async generator yielding SSE events for streaming Hermes chat."""
    selected_platform = (payload.platform or "hermes").strip() or "hermes"
    history_messages = store.get_history_messages(selected_platform, payload.external_session_id)

    messages = _build_history_messages(
        history_messages, payload.user_message, system_prompt=payload.system_prompt,
    )
    model_for_request = get_selected_model() or os.getenv("HERMES_MODEL", "").strip()

    base_url = os.getenv("HERMES_API_BASE_URL", "http://host.docker.internal:8643/v1").rstrip("/")
    api_key = os.getenv("HERMES_API_KEY", "")
    timeout_seconds = float(os.getenv("HERMES_API_TIMEOUT_SECONDS", "120"))

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    # Ingest user message before streaming starts
    if payload.system_prompt and payload.system_prompt.strip() and not history_messages:
        store.ingest(IngestEventRequest(
            platform=selected_platform,
            event_id=f"evt_system_{uuid4().hex}",
            event_type="message_created",
            external_session_id=payload.external_session_id,
            title=payload.title,
            payload_json={"source": "shujietai-chat-stream"},
            message={"role": "system", "content": payload.system_prompt.strip()},
        ))

    user_event_id = f"evt_user_{uuid4().hex}"
    session_id, _ = store.ingest(IngestEventRequest(
        platform=selected_platform,
        event_id=user_event_id,
        event_type="message_created",
        external_session_id=payload.external_session_id,
        title=payload.title,
        payload_json={"source": "shujietai-chat-stream"},
        message={"role": "user", "content": payload.user_message},
    ))

    # Yield session info as first event
    yield f"data: {json_module.dumps({'type': 'session', 'session_id': session_id, 'user_event_id': user_event_id})}\n\n"

    # Stream from Hermes API
    request_body = {
        "model": model_for_request or "hermes-agent",
        "messages": messages,
        "stream": True,
    }

    full_content = ""
    tool_calls_log = []

    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds, connect=10.0)) as client:
        async with client.stream(
            "POST",
            f"{base_url}/chat/completions",
            headers=headers,
            json=request_body,
        ) as response:
            if response.status_code != 200:
                error_body = await response.aread()
                yield f"data: {json_module.dumps({'type': 'error', 'status': response.status_code, 'detail': error_body.decode(errors='replace')[:200]})}\n\n"
                return

            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json_module.loads(data_str)
                except json_module.JSONDecodeError:
                    continue

                choices = chunk.get("choices", [])
                if not choices:
                    continue
                choice = choices[0]
                delta = choice.get("delta", {})

                # Handle content delta
                if "content" in delta and delta["content"]:
                    full_content += delta["content"]
                    yield f"data: {json_module.dumps({'type': 'content', 'content': delta['content']})}\n\n"

                # Handle tool calls delta (agent thinking/tool-use chain)
                if "tool_calls" in delta:
                    for tc in delta["tool_calls"]:
                        tc_info = {
                            "index": tc.get("index", 0),
                            "id": tc.get("id", ""),
                            "function_name": tc.get("function", {}).get("name", ""),
                            "function_args_delta": tc.get("function", {}).get("arguments", ""),
                        }
                        tool_calls_log.append(tc_info)
                        yield f"data: {json_module.dumps({'type': 'tool_call', **tc_info})}\n\n"

                # Handle finish_reason
                finish = choice.get("finish_reason")
                if finish:
                    usage = chunk.get("usage", {})
                    yield f"data: {json_module.dumps({'type': 'finish', 'reason': finish, 'usage': usage})}\n\n"

    # Ingest the completed assistant message
    assistant_event_id = f"evt_assistant_{uuid4().hex}"
    meta = {}
    if tool_calls_log:
        meta["tool_calls"] = tool_calls_log
    store.ingest(IngestEventRequest(
        platform=selected_platform,
        event_id=assistant_event_id,
        event_type="message_created",
        external_session_id=payload.external_session_id,
        title=payload.title,
        payload_json={"source": "shujietai-chat-stream"},
        message={"role": "assistant", "content": full_content},
    ))

    # Final done event with complete data
    yield f"data: {json_module.dumps({'type': 'done', 'event_id': assistant_event_id, 'session_id': session_id, 'content_length': len(full_content)})}\n\n"


@app.post("/api/v1/connectors/hermes/chat/stream")
async def hermes_chat_stream(payload: HermesChatRequest, request: Request):
    """Streaming variant of hermes/chat using SSE."""
    return StreamingResponse(
        _stream_hermes_chat(payload),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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


@app.get("/api/v1/skills")
def get_skills_catalog():
    """Return all available skills grouped by provider.

    Hermes is currently the only provider. The response shape uses a providers[]
    envelope so future providers can be added without breaking clients.
    """
    runtime = build_runtime_state()
    skill_items = runtime.available_skill_items

    hermes_skills = []
    for item in skill_items:
        name = item.name
        # category = first path segment (e.g. "devops" from "devops/kanban-worker")
        category = name.split("/")[0] if "/" in name else "general"
        hermes_skills.append({
            "name": name,
            "description": item.description,
            "category": category,
            "skill_type": item.skill_type,
        })

    return {
        "providers": [
            {
                "id": "hermes",
                "label": "Hermes Agent",
                "skills": hermes_skills,
            }
        ],
        "total": len(hermes_skills),
    }


@app.get("/api/v1/skills/graph")
def get_skills_graph():
    """Return a node-link graph for the skill catalog.

    Nodes are skill categories (macro view). Edges connect categories that share
    at least one tag in common across their member skills.

    Node shape: {id, label, skill_count, tags}
    Edge shape: {source, target, weight}
    """
    import re as _re
    import yaml as _yaml

    skills_dir = Path(os.getenv("HERMES_SKILLS_DIR", "/home/guancy/.hermes/skills"))
    personal_dir = Path(os.getenv("HERMES_PERSONAL_SKILLS_DIR", "/home/guancy/.hermes/personal-skills"))

    # category -> {skill_name -> [tags]}
    cat_skills: dict[str, dict[str, list[str]]] = {}

    for base_dir in (personal_dir, skills_dir):
        if not base_dir.exists():
            continue
        for skill_md in base_dir.rglob("SKILL.md"):
            try:
                text = skill_md.read_text(encoding="utf-8")
            except Exception:
                continue
            m = _re.match(r"^---\n(.*?)\n---", text, _re.DOTALL)
            tags: list[str] = []
            name = ""
            if m:
                try:
                    fm = _yaml.safe_load(m.group(1)) or {}
                    name = fm.get("name", "")
                    tags = (
                        fm.get("tags")
                        or (fm.get("metadata") or {}).get("hermes", {}).get("tags", [])
                        or []
                    )
                    if not isinstance(tags, list):
                        tags = []
                except Exception:
                    pass
            # Derive category and short name from filesystem path relative to base_dir
            try:
                rel = skill_md.relative_to(base_dir)
                parts = rel.parts  # e.g. ('devops', 'kanban-worker', 'SKILL.md')
                if len(parts) >= 3:
                    category = parts[0]
                    skill_key = f"{parts[0]}/{parts[1]}"
                elif len(parts) == 2:
                    category = "general"
                    skill_key = parts[0]
                else:
                    category = "general"
                    skill_key = name or skill_md.parent.name
            except Exception:
                category = name.split("/")[0] if "/" in name else "general"
                skill_key = name or skill_md.parent.name
            if not name:
                name = skill_key
            cat_skills.setdefault(category, {})[skill_key] = tags

    # Build nodes
    nodes = []
    for cat, skills in sorted(cat_skills.items()):
        all_tags: set[str] = set()
        for t in skills.values():
            all_tags.update(t)
        nodes.append({
            "id": cat,
            "label": cat,
            "skill_count": len(skills),
            "tags": sorted(all_tags),
            "skills": [
                {"name": n, "tags": t}
                for n, t in sorted(skills.items())
            ],
        })

    # Build edges: categories sharing >=1 tag
    node_tags = {n["id"]: set(n["tags"]) for n in nodes}
    edges = []
    node_ids = [n["id"] for n in nodes]
    for i, a in enumerate(node_ids):
        for b in node_ids[i + 1 :]:
            shared = node_tags[a] & node_tags[b]
            if shared:
                edges.append({"source": a, "target": b, "weight": len(shared), "shared_tags": sorted(shared)})

    return {"nodes": nodes, "edges": edges}


@app.get("/api/v1/skills/{skill_name:path}/content")
def get_skill_content(skill_name: str):
    """Return the raw SKILL.md content for a given skill name (e.g. 'devops/kanban-worker')."""
    skills_dir = Path(os.getenv("HERMES_SKILLS_DIR", "/home/guancy/.hermes/skills"))
    personal_dir = Path(os.getenv("HERMES_PERSONAL_SKILLS_DIR", "/home/guancy/.hermes/personal-skills"))

    # Search personal first, then builtin
    for base_dir in (personal_dir, skills_dir):
        if not base_dir.exists():
            continue
        # skill_name may be "category/name" — look for SKILL.md two levels deep
        parts = skill_name.split("/", 1)
        candidates = []
        if len(parts) == 2:
            candidates.append(base_dir / parts[0] / parts[1] / "SKILL.md")
        candidates.append(base_dir / skill_name / "SKILL.md")
        for candidate in candidates:
            if candidate.is_file():
                try:
                    content = candidate.read_text(encoding="utf-8")
                    return {"name": skill_name, "content": content, "path": str(candidate)}
                except Exception as e:
                    raise HTTPException(status_code=500, detail=str(e))
        # Flat name fallback: recursively search subdirectories for <name>/SKILL.md
        try:
            for found in base_dir.rglob(f"**/{skill_name}/SKILL.md"):
                try:
                    content = found.read_text(encoding="utf-8")
                    return {"name": skill_name, "content": content, "path": str(found)}
                except Exception as e:
                    raise HTTPException(status_code=500, detail=str(e))
        except OSError:
            pass

    raise HTTPException(status_code=404, detail=f"SKILL.md not found for: {skill_name}")


@app.put("/api/v1/runtime/preferences")
def update_runtime_preferences(payload: RuntimePreferenceUpdateRequest):
    set_runtime_preferences(
        selected_model=payload.selected_model,
        selected_skills=payload.selected_skills,
        selected_mcp_servers=payload.selected_mcp_servers,
    )
    invalidate_runtime_cache()
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
        token = system_config_service.get_github_token()
        try:
            return github_project_service.create_repository(payload, token_override=token)
        except TypeError as exc:
            if "token_override" not in str(exc):
                raise
            return github_project_service.create_repository(payload)
    except RuntimeError as exc:
        detail = str(exc)
        if detail in {"gh_cli_unavailable", "github_repo_create_unavailable"}:
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
            "task_status_reason_required",
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
            "task_status_reason_required",
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

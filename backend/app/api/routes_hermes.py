from __future__ import annotations
import json as json_module
import os
from datetime import datetime
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.schemas import (
    DeadLetterListResponse,
    DeadLetterReplayRequest,
    DeadLetterReplayResponse,
    HermesChatRequest,
    HermesChatResponse,
    HermesWebhookEventRequest,
    IngestEventRequest,
    IngestEventResponse,
)
from app.services.hermes_runtime_catalog import build_runtime_state, get_selected_model
from app.services.ingest_retry_service import DeadLetterQuery
from app.container import store, retry_service, retry_counters, connector_registry

router = APIRouter(prefix="", tags=["hermes"])


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


@router.post("/api/v1/events/ingest", response_model=IngestEventResponse)
def ingest_event(payload: IngestEventRequest, request: Request) -> IngestEventResponse:
    return _ingest_and_build_response(payload, request)


@router.post("/api/v1/connectors/hermes/webhook", response_model=IngestEventResponse)
def ingest_hermes_webhook(payload: HermesWebhookEventRequest, request: Request) -> IngestEventResponse:
    hermes_adapter = connector_registry.get("hermes")
    ingest_payload = hermes_adapter.to_ingest_event(payload)
    return _ingest_and_build_response(ingest_payload, request)


@router.post("/api/v1/connectors/hermes/chat", response_model=HermesChatResponse)
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


@router.post("/api/v1/connectors/hermes/chat/stream")
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


@router.get("/api/v1/dlq", response_model=DeadLetterListResponse)
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


@router.post("/api/v1/dlq/{dlq_id}/replay", response_model=DeadLetterReplayResponse)
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

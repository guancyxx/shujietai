from __future__ import annotations

import os
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import (
    HermesChatRequest,
    HermesChatResponse,
    HermesWebhookEventRequest,
    IngestEventRequest,
    IngestEventResponse,
)
from app.services.cockpit_service import get_cockpit_by_session
from app.services.store_factory import build_store

store = build_store()

app = FastAPI(title="ShuJieTai API", version="0.1.0")

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
def health() -> dict[str, str]:
    return {"status": "healthy", "service": "shujietai-backend"}


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


def _ask_hermes_via_api(messages: list[dict[str, str]]) -> str:
    base_url = os.getenv("HERMES_API_BASE_URL", "http://host.docker.internal:8642/v1").rstrip("/")
    api_key = os.getenv("HERMES_API_KEY", "")
    model = os.getenv("HERMES_MODEL", "gpt-5.3-codex")
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


def _ask_hermes_via_cli(messages: list[dict[str, str]]) -> str:
    from subprocess import run

    hermes_bin = os.getenv("HERMES_BIN", "hermes")
    timeout_seconds = float(os.getenv("HERMES_API_TIMEOUT_SECONDS", "120"))

    prompt_lines: list[str] = ["Conversation history:"]
    for message in messages[:-1]:
        prompt_lines.append(f"{message['role']}: {message['content']}")
    prompt_lines.append("Now reply to the latest user message:")
    prompt_lines.append(messages[-1]["content"])
    prompt = "\n".join(prompt_lines)

    result = run(
        [hermes_bin, "-z", prompt],
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


def ask_hermes_response(history_messages: list[dict[str, str]], user_message: str) -> str:
    messages = _build_history_messages(history_messages, user_message)

    try:
        return _ask_hermes_via_api(messages)
    except httpx.HTTPError:
        cli_fallback_enabled = os.getenv("HERMES_CLI_FALLBACK_ENABLED", "1") == "1"
        if not cli_fallback_enabled:
            raise
        return _ask_hermes_via_cli(messages)


def _ingest_and_build_response(payload: IngestEventRequest, request: Request) -> IngestEventResponse:
    session_id, duplicate = store.ingest(payload)
    request_id = request.headers.get("x-request-id", str(uuid4()))
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
    ingest_message = None
    if payload.message is not None:
        ingest_message = {
            "role": payload.message.role,
            "content": payload.message.content,
            "content_type": payload.message.content_type,
            "meta_json": payload.message.meta_json,
        }

    ingest_payload = IngestEventRequest(
        platform="hermes",
        event_id=payload.event_id,
        event_type=payload.event_type,
        external_session_id=payload.external_session_id,
        title=payload.title,
        payload_json={**payload.payload_json, "meta": payload.meta},
        message=ingest_message,
    )
    return _ingest_and_build_response(ingest_payload, request)


@app.post("/api/v1/connectors/hermes/chat", response_model=HermesChatResponse)
def hermes_chat(payload: HermesChatRequest, request: Request) -> HermesChatResponse:
    history_messages = store.get_history_messages("hermes", payload.external_session_id)
    try:
        assistant_message = ask_hermes_response(history_messages, payload.user_message)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="hermes_unavailable") from exc

    user_event_id = f"evt_user_{uuid4().hex}"
    user_ingest = IngestEventRequest(
        platform="hermes",
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
        platform="hermes",
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


@app.get("/api/v1/sessions")
def list_sessions():
    return store.list_sessions()


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

from __future__ import annotations

import os
from uuid import uuid4

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
from app.services.session_store import store

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


def ask_hermes_response(prompt: str) -> str:
    from subprocess import run

    hermes_bin = os.getenv("HERMES_BIN", "hermes")
    result = run(
        [hermes_bin, "-z", prompt],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("hermes_command_failed")
    content = result.stdout.strip()
    if not content:
        raise RuntimeError("hermes_empty_response")
    return content


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
    try:
        assistant_message = ask_hermes_response(payload.user_message)
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
    cockpit = get_cockpit_by_session(session_id)
    if cockpit is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    return cockpit

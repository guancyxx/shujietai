from __future__ import annotations

import os
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import IngestEventRequest, IngestEventResponse
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


@app.post("/api/v1/events/ingest", response_model=IngestEventResponse)
def ingest_event(payload: IngestEventRequest, request: Request) -> IngestEventResponse:
    session_id, duplicate = store.ingest(payload)
    request_id = request.headers.get("x-request-id", str(uuid4()))
    return IngestEventResponse(
        request_id=request_id,
        duplicate=duplicate,
        session_id=session_id,
        event_id=payload.event_id,
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

from __future__ import annotations
from fastapi import APIRouter, HTTPException

from app.services.cockpit_service import get_cockpit_by_session
from app.container import dispatch_service, store

router = APIRouter(prefix="", tags=["sessions"])


def _enrich_session_with_dispatch(session):
    if dispatch_service is None or session is None:
        return session
    resolved = dispatch_service.resolve_session_dispatch(session.platform, session.external_session_id)
    latest = resolved.get("latest_dispatch_task")
    return session.model_copy(update={
        "canonical_dispatch_task_id": latest.id if latest is not None else None,
        "has_dispatch_history": latest is not None,
    })


@router.get("/api/v1/sessions")
def list_sessions():
    return [_enrich_session_with_dispatch(session) for session in store.list_sessions()]


@router.delete("/api/v1/sessions/{session_id}")
def delete_session(session_id: str):
    deleted = store.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="session_not_found")
    return {"deleted": 1, "session_id": session_id}


@router.delete("/api/v1/sessions")
def clear_sessions():
    deleted_count = store.clear_sessions()
    return {"deleted": deleted_count}


@router.get("/api/v1/sessions/{session_id}")
def get_session(session_id: str):
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    return _enrich_session_with_dispatch(session)


@router.get("/api/v1/sessions/{session_id}/timeline")
def get_timeline(session_id: str):
    timeline = store.get_timeline(session_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    return timeline


@router.get("/api/v1/board/cockpit")
def get_cockpit(session_id: str):
    cockpit = get_cockpit_by_session(store, session_id)
    if cockpit is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    return cockpit.model_copy(update={"session": _enrich_session_with_dispatch(cockpit.session)})

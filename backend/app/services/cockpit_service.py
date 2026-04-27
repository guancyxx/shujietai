from __future__ import annotations

from app.schemas import CockpitResponse
from app.services.session_store import store


def get_cockpit_by_session(session_id: str) -> CockpitResponse | None:
    return store.get_cockpit(session_id)

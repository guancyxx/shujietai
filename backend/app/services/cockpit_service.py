from __future__ import annotations

from app.schemas import CockpitResponse


def get_cockpit_by_session(store, session_id: str) -> CockpitResponse | None:
    return store.get_cockpit(session_id)

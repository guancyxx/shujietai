from __future__ import annotations

from app.schemas import IngestEventRequest


class NewConnectorTemplate:
    connector_name = "replace_me"

    def to_ingest_event(self, raw_payload: dict) -> IngestEventRequest:
        return IngestEventRequest(
            platform="replace_me",
            event_id=raw_payload["event_id"],
            event_type=raw_payload["event_type"],
            external_session_id=raw_payload["external_session_id"],
            title=raw_payload.get("title"),
            payload_json=raw_payload.get("payload_json", {}),
            message=raw_payload.get("message"),
            task=raw_payload.get("task"),
        )

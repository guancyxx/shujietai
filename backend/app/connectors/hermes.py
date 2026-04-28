from __future__ import annotations

from app.schemas import HermesWebhookEventRequest, IngestEventRequest


class HermesConnectorAdapter:
    connector_name = "hermes"

    def to_ingest_event(self, payload: HermesWebhookEventRequest) -> IngestEventRequest:
        ingest_message = None
        if payload.message is not None:
            ingest_message = {
                "role": payload.message.role,
                "content": payload.message.content,
                "content_type": payload.message.content_type,
                "meta_json": payload.message.meta_json,
            }

        return IngestEventRequest(
            platform="hermes",
            event_id=payload.event_id,
            event_type=payload.event_type,
            external_session_id=payload.external_session_id,
            title=payload.title,
            payload_json={**payload.payload_json, "meta": payload.meta},
            message=ingest_message,
        )

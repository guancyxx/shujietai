from __future__ import annotations

from typing import Protocol

from app.schemas import HermesWebhookEventRequest, IngestEventRequest


class ConnectorAdapter(Protocol):
    connector_name: str

    def to_ingest_event(self, payload: HermesWebhookEventRequest) -> IngestEventRequest:
        ...

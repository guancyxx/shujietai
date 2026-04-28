from __future__ import annotations

from app.connectors.hermes import HermesConnectorAdapter
from app.schemas import HermesWebhookEventRequest


def test_hermes_connector_contract_to_ingest_event() -> None:
    adapter = HermesConnectorAdapter()
    payload = HermesWebhookEventRequest(
        event_id="evt_contract_1",
        event_type="message_created",
        external_session_id="sess_contract_1",
        title="contract",
        payload_json={"source": "fixture"},
        message={"role": "assistant", "content": "hello"},
        meta={"platform": "hermes"},
    )

    ingest_event = adapter.to_ingest_event(payload)

    assert ingest_event.platform == "hermes"
    assert ingest_event.event_id == "evt_contract_1"
    assert ingest_event.external_session_id == "sess_contract_1"
    assert ingest_event.message is not None
    assert ingest_event.message.role == "assistant"
    assert ingest_event.payload_json["meta"] == {"platform": "hermes"}

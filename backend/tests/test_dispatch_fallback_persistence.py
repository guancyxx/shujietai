from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.connectors.hermes_streaming import HermesStreamingConnector
from app.schemas import DispatchTaskItem
from app.services.dispatch_worker import TaskWorker


class _FakeStreamResponse:
    def __init__(self, lines: list[str], status_code: int = 200) -> None:
        self._lines = lines
        self.status_code = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self) -> bytes:
        return b""


class _FakeNonStreamResponse:
    def __init__(self, content: str, status_code: int = 200) -> None:
        self.status_code = status_code
        self._content = content
        self.text = content

    def json(self) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": self._content,
                    }
                }
            ]
        }


def test_hermes_streaming_connector_falls_back_to_non_stream_when_stream_has_no_content(monkeypatch) -> None:
    call_log: list[tuple[str, bool]] = []

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method: str, url: str, headers: dict, json: dict):
            call_log.append(("stream", bool(json.get("stream"))))
            lines = [
                'data: {"choices":[{"delta":{"role":"assistant"}}]}',
                'data: {"choices":[{"finish_reason":"stop"}],"usage":{"total_tokens":10}}',
                'data: [DONE]',
            ]
            return _FakeStreamResponse(lines)

        async def post(self, url: str, headers: dict, json: dict):
            call_log.append(("post", bool(json.get("stream"))))
            return _FakeNonStreamResponse("fallback assistant reply")

    monkeypatch.setattr("app.connectors.hermes_streaming.httpx.AsyncClient", _FakeAsyncClient)

    async def _collect() -> list[dict]:
        connector = HermesStreamingConnector()
        chunks: list[dict] = []
        async for chunk in connector.stream_completion(
            messages=[{"role": "user", "content": "hello"}],
            config={"model": "hermes-agent"},
        ):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(_collect())
    assert ("stream", True) in call_log
    assert ("post", False) in call_log
    assert any(c.get("type") == "finish" for c in chunks)
    assert any(c.get("type") == "content" and "fallback assistant reply" in c.get("content", "") for c in chunks)


class _FakeDispatchService:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict]] = []
        self.persist_calls: list[dict] = []
        self.transitions: list[tuple[str, str]] = []

    def reconstruct_history(self, task_id: str) -> list[dict[str, str]]:
        return []

    def add_event(self, task_id: str, event_type: str, payload: dict) -> str:
        self.events.append((task_id, event_type, payload))
        return f"evt_{len(self.events)}"

    def persist_message_to_session(self, platform: str, external_session_id: str, role: str, content: str, content_type: str = "text/markdown") -> None:
        self.persist_calls.append(
            {
                "platform": platform,
                "external_session_id": external_session_id,
                "role": role,
                "content": content,
                "content_type": content_type,
            }
        )

    def transition_task(self, task_id: str, status: str, error_message: str | None = None):
        self.transitions.append((task_id, status))

    def cancel_task(self, task_id: str) -> None:
        return None


class _FakeWsManager:
    def __init__(self) -> None:
        self.broadcasts: list[tuple[str, str, dict]] = []

    async def broadcast(self, task_id: str, event_type: str, payload: dict) -> None:
        self.broadcasts.append((task_id, event_type, payload))


class _FallbackShapeConnector:
    async def stream_completion(self, messages: list[dict[str, str]], config: dict):
        yield {"type": "finish", "finish_reason": "stop", "usage": {"total_tokens": 12}}
        yield {"type": "content", "content": "fallback persisted reply"}


def test_dispatch_worker_persists_assistant_message_even_if_content_arrives_after_finish(monkeypatch) -> None:
    monkeypatch.setattr("app.services.dispatch_worker.get_connector", lambda _: _FallbackShapeConnector())

    service = _FakeDispatchService()
    ws = _FakeWsManager()
    now = datetime.now(timezone.utc)
    task = DispatchTaskItem(
        id="dt_test_fallback_persist",
        task_board_item_id=None,
        status="running",
        ai_platform="hermes",
        external_session_id="dispatch_dt_test_fallback_persist",
        config={"model": "hermes-agent"},
        initial_prompt="hello",
        error_message=None,
        created_at=now,
        updated_at=now,
    )

    worker = TaskWorker(task=task, dispatch_service=service, ws_manager=ws)
    asyncio.run(worker.run())

    assert any(evt_type == "content_full" and payload.get("content") == "fallback persisted reply" for _, evt_type, payload in service.events)
    assert any(
        event_type == "content_delta"
        and payload.get("role") == "assistant"
        and payload.get("content") == "fallback persisted reply"
        for _, event_type, payload in ws.broadcasts
    )
    assert len(service.persist_calls) == 1
    assert service.persist_calls[0]["external_session_id"] == "dispatch_dt_test_fallback_persist"
    assert service.persist_calls[0]["role"] == "assistant"
    assert service.persist_calls[0]["content"] == "fallback persisted reply"
    assert ("dt_test_fallback_persist", "completed") in service.transitions

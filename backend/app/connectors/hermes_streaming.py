"""Compatibility connector for legacy OpenAI-style Hermes chat streaming tests.

Production dispatch now uses the Hermes runs connector registered as ``hermes``.
This module remains intentionally unregistered so older regression tests and
imports that exercise the blank-stream fallback path keep working.
"""

from __future__ import annotations

import json
import os
from typing import Any, AsyncIterator

import httpx

from app.connectors.ai_base import StreamingAIConnector


class HermesStreamingConnector:
    """OpenAI-compatible chat completion connector with blank-stream fallback."""

    platform_name = "hermes_streaming"

    def _env(self) -> tuple[str, str, float]:
        base_url = os.getenv("HERMES_API_BASE_URL", "http://host.docker.internal:8643/v1").rstrip("/")
        api_key = os.getenv("HERMES_API_KEY", "")
        timeout = float(os.getenv("HERMES_API_TIMEOUT_SECONDS", "120"))
        return base_url, api_key, timeout

    def _headers(self, api_key: str) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        config: dict[str, Any],
    ) -> AsyncIterator[dict]:
        base_url, api_key, timeout = self._env()
        headers = self._headers(api_key)
        model = config.get("model") or os.getenv("HERMES_MODEL", "hermes-agent")
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }

        saw_content = False
        finish_chunk: dict | None = None
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", f"{base_url}/chat/completions", headers=headers, json=payload) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode(errors="replace")[:500]
                    yield {"type": "error", "error": f"hermes_streaming_error_{response.status_code}: {body}"}
                    return

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    raw = line[6:]
                    if raw == "[DONE]":
                        break
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0] or {}
                    delta = choice.get("delta") or {}
                    content = delta.get("content") or ""
                    if content:
                        saw_content = True
                        yield {"type": "content", "content": content}
                    finish_reason = choice.get("finish_reason")
                    if finish_reason:
                        finish_chunk = {
                            "type": "finish",
                            "finish_reason": finish_reason,
                            "usage": event.get("usage") or {},
                        }

            if not saw_content:
                fallback_payload = dict(payload)
                fallback_payload["stream"] = False
                fallback_response = await client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=fallback_payload,
                )
                if fallback_response.status_code >= 400:
                    yield {
                        "type": "error",
                        "error": f"hermes_non_stream_error_{fallback_response.status_code}: {fallback_response.text[:500]}",
                    }
                    return
                data = fallback_response.json()
                choices = data.get("choices") or []
                if choices:
                    message = (choices[0] or {}).get("message") or {}
                    content = message.get("content") or ""
                    if content:
                        yield {"type": "content", "content": content}

        yield finish_chunk or {"type": "finish", "finish_reason": "stop", "usage": {}}


assert isinstance(HermesStreamingConnector(), StreamingAIConnector)

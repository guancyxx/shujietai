"""Hermes streaming AI connector — OpenAI-compatible chat completions API."""

from __future__ import annotations

import json as json_module
import logging
import os
from typing import Any, AsyncIterator

import httpx

from app.connectors.ai_base import StreamingAIConnector

logger = logging.getLogger(__name__)


class HermesStreamingConnector:
    """OpenAI-compatible streaming connector for the Hermes platform."""

    platform_name = "hermes"

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        config: dict[str, Any],
    ) -> AsyncIterator[dict]:
        """Stream from an OpenAI-compatible API, yielding structured chunks."""
        base_url = os.getenv("HERMES_API_BASE_URL", "http://host.docker.internal:8643/v1").rstrip("/")
        api_key = os.getenv("HERMES_API_KEY", "")
        model = config.get("model") or os.getenv("HERMES_MODEL", "gpt-5.3-codex")
        timeout_seconds = float(os.getenv("HERMES_API_TIMEOUT_SECONDS", "120"))

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        request_body = {
            "model": model,
            "messages": messages,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds, connect=10.0)) as client:
            async with client.stream(
                "POST",
                f"{base_url}/chat/completions",
                headers=headers,
                json=request_body,
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    error_text = error_body.decode(errors="replace")[:500]
                    yield {"type": "error", "error": f"hermes_api_error_{response.status_code}: {error_text}"}
                    return

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break

                    try:
                        chunk = json_module.loads(data_str)
                    except json_module.JSONDecodeError:
                        continue

                    choices = chunk.get("choices", [])
                    if not choices:
                        continue

                    choice = choices[0]
                    delta = choice.get("delta", {})

                    # Content delta
                    if "content" in delta and delta["content"]:
                        yield {"type": "content", "content": delta["content"]}

                    # Tool calls delta
                    if "tool_calls" in delta:
                        for tc in delta["tool_calls"]:
                            yield {
                                "type": "tool_call",
                                "index": tc.get("index", 0),
                                "id": tc.get("id", ""),
                                "function_name": tc.get("function", {}).get("name", ""),
                                "function_args_delta": tc.get("function", {}).get("arguments", ""),
                            }

                    # Finish reason
                    finish = choice.get("finish_reason")
                    if finish:
                        usage = chunk.get("usage", {})
                        yield {"type": "finish", "finish_reason": finish, "usage": usage}
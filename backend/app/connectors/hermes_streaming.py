"""Hermes streaming AI connector — OpenAI-compatible chat completions API."""

from __future__ import annotations

import json as json_module
import os
from typing import Any, AsyncIterator

import httpx

from app.connectors.ai_base import StreamingAIConnector


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
            saw_content = False
            saw_finish = False

            async with client.stream(
                "POST",
                f"{base_url}/chat/completions",
                headers=headers,
                json=request_body,
            ) as response:
                if response.status_code != 200:
                    error_text = (await response.aread()).decode(errors="replace")[:500]
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

                    if "content" in delta and delta["content"]:
                        saw_content = True
                        yield {"type": "content", "content": delta["content"]}

                    if "tool_calls" in delta:
                        for tc in delta["tool_calls"]:
                            yield {
                                "type": "tool_call",
                                "index": tc.get("index", 0),
                                "id": tc.get("id", ""),
                                "function_name": tc.get("function", {}).get("name", ""),
                                "function_args_delta": tc.get("function", {}).get("arguments", ""),
                            }

                    finish = choice.get("finish_reason")
                    if finish:
                        saw_finish = True
                        usage = chunk.get("usage", {})
                        yield {"type": "finish", "finish_reason": finish, "usage": usage}

            # Fallback: some upstreams stream only role+finish and no content.
            if saw_finish and not saw_content:
                payload = dict(request_body)
                payload["stream"] = False
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                if resp.status_code != 200:
                    text = resp.text[:500]
                    yield {"type": "error", "error": f"hermes_api_fallback_error_{resp.status_code}: {text}"}
                    return

                body = resp.json()
                choices = body.get("choices", [])
                if not choices:
                    return

                content = ((choices[0].get("message") or {}).get("content") or "").strip()
                if content:
                    yield {"type": "content", "content": content}


# Ensure this connector satisfies the expected protocol
assert isinstance(HermesStreamingConnector(), StreamingAIConnector)

"""Hermes Agent runs connector — uses /v1/runs + /v1/runs/{run_id}/events SSE.

Compared to HermesStreamingConnector (OpenAI-compatible /chat/completions),
this connector exposes richer structured lifecycle events:

  content_delta   — streaming text chunk
  tool_start      — tool invocation began  (tool name + preview)
  tool_complete   — tool invocation ended  (duration, error flag)
  agent_thinking  — reasoning text (only for extended-thinking-capable models)
  finish          — run completed successfully
  error           — run failed or cancelled

The connector satisfies the StreamingAIConnector protocol so it can be dropped
into the existing registry and picked up by TaskWorker without changes to the
dispatch orchestration layer — TaskWorker only needs to handle the three new
chunk types (tool_start, tool_complete, agent_thinking).
"""

from __future__ import annotations

import json as _json
import logging
import os
from typing import Any, AsyncIterator

import httpx

from app.connectors.ai_base import StreamingAIConnector

logger = logging.getLogger(__name__)

# How long to wait for the /v1/runs POST to respond.
_POST_TIMEOUT = 30.0
# How long the SSE stream can sit idle before we give up (keepalive comes every 30 s).
_STREAM_IDLE_TIMEOUT = 90.0


class HermesRunsConnector:
    """Hermes-native agent runs connector.

    Uses POST /v1/runs to start a run then GET /v1/runs/{run_id}/events to
    consume the structured SSE lifecycle stream.

    Platform name ``hermes_runs`` — register alongside ``hermes`` to let
    callers choose which flavour they want via ``ai_platform`` on the task.
    """

    platform_name = "hermes-runs"

    def _env(self) -> tuple[str, str, float]:
        """Return (base_url, api_key, timeout_seconds) from env."""
        # Strip /v1 suffix if present — we build our own paths.
        raw = os.getenv("HERMES_API_BASE_URL", "http://host.docker.internal:8643/v1")
        base_url = raw.rstrip("/")
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]
        api_key = os.getenv("HERMES_API_KEY", "")
        timeout = float(os.getenv("HERMES_API_TIMEOUT_SECONDS", "120"))
        return base_url, api_key, timeout

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        config: dict[str, Any],
    ) -> AsyncIterator[dict]:
        """Yield structured chunks from a Hermes agent run.

        Input ``messages`` follows the OpenAI format used by the rest of the
        dispatch layer.  The last message with role ``user`` becomes the run
        input; earlier messages are passed as conversation history.

        Yielded chunk shapes:
          {"type": "content_delta", "content": str}
          {"type": "tool_start",    "tool": str, "preview": str | None}
          {"type": "tool_complete", "tool": str, "duration": float | None, "error": bool}
          {"type": "agent_thinking","text": str}
          {"type": "finish",        "finish_reason": "stop", "usage": dict}
          {"type": "error",         "error": str}
        """
        base_url, api_key, _timeout = self._env()

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Split messages into system / history / last user message.
        system_prompt: str | None = None
        history: list[dict[str, str]] = []
        user_input = ""

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system" and system_prompt is None:
                system_prompt = content
            elif role == "user":
                # Keep all user turns in history; the last one is also the input.
                history.append(msg)
                user_input = content
            else:
                history.append(msg)

        if not user_input:
            yield {"type": "error", "error": "hermes_runs_connector: no user message found"}
            return

        # Remove the final user turn from history (it becomes the run input).
        if history and history[-1].get("role") == "user" and history[-1].get("content") == user_input:
            history = history[:-1]

        payload: dict[str, Any] = {"input": user_input}
        if history:
            payload["conversation_history"] = history
        if system_prompt:
            payload["instructions"] = system_prompt

        # Allow caller to override model/session via config.
        if config.get("model"):
            payload["model"] = config["model"]
        if config.get("session_id"):
            payload["session_id"] = config["session_id"]

        # --- Step 1: start the run ---
        run_id: str | None = None
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(_POST_TIMEOUT, connect=10.0)) as client:
                resp = await client.post(
                    f"{base_url}/v1/runs",
                    headers=headers,
                    json=payload,
                )
                if resp.status_code != 202:
                    body = resp.text[:500]
                    yield {"type": "error", "error": f"hermes_runs_start_error_{resp.status_code}: {body}"}
                    return
                run_id = resp.json().get("run_id")
        except Exception as exc:
            yield {"type": "error", "error": f"hermes_runs_start_exception: {exc}"}
            return

        if not run_id:
            yield {"type": "error", "error": "hermes_runs_connector: no run_id returned"}
            return

        logger.debug("[hermes_runs] started run %s", run_id)

        # --- Step 2: subscribe to SSE event stream ---
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=10.0)) as client:
                async with client.stream(
                    "GET",
                    f"{base_url}/v1/runs/{run_id}/events",
                    headers=headers,
                ) as stream:
                    if stream.status_code != 200:
                        body = (await stream.aread()).decode(errors="replace")[:500]
                        yield {"type": "error", "error": f"hermes_runs_events_error_{stream.status_code}: {body}"}
                        return

                    async for line in stream.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue

                        raw = line[6:]
                        try:
                            event = _json.loads(raw)
                        except _json.JSONDecodeError:
                            continue

                        etype = event.get("event", "")

                        if etype == "message.delta":
                            delta = event.get("delta", "")
                            if delta:
                                yield {"type": "content_delta", "content": delta}

                        elif etype == "tool.started":
                            yield {
                                "type": "tool_start",
                                "tool": event.get("tool", ""),
                                "preview": event.get("preview"),
                            }

                        elif etype == "tool.completed":
                            yield {
                                "type": "tool_complete",
                                "tool": event.get("tool", ""),
                                "duration": event.get("duration"),
                                "error": bool(event.get("error", False)),
                            }

                        elif etype == "reasoning.available":
                            text = event.get("text", "")
                            if text:
                                yield {"type": "agent_thinking", "text": text}

                        elif etype == "run.completed":
                            usage = event.get("usage") or {}
                            yield {
                                "type": "finish",
                                "finish_reason": "stop",
                                "usage": usage,
                            }
                            return

                        elif etype in ("run.failed", "run.cancelled"):
                            error_msg = event.get("error") or etype
                            yield {"type": "error", "error": f"hermes_runs_{etype}: {error_msg}"}
                            return

        except httpx.RemoteProtocolError as exc:
            # SSE stream closed by server — treated as normal finish if we
            # already got run.completed; otherwise it is an error.
            yield {"type": "error", "error": f"hermes_runs_stream_closed: {exc}"}
        except Exception as exc:
            logger.exception("[hermes_runs] run %s stream error", run_id)
            yield {"type": "error", "error": f"hermes_runs_stream_exception: {exc}"}


# Satisfy the StreamingAIConnector protocol at import time.
assert isinstance(HermesRunsConnector(), StreamingAIConnector)

"""Hermes Agent connector — uses /v1/runs + /v1/runs/{run_id}/events SSE.

Exposes structured lifecycle events from Hermes runs API:

  content_delta   — streaming text chunk
  tool_start      — tool invocation began  (tool name + preview + arguments)
  tool_complete   — tool invocation ended  (duration, error flag)
  agent_thinking  — reasoning text (only for extended-thinking-capable models)
  finish          — run completed successfully
  error           — run failed or cancelled

For skill_view events, skill name and file path are extracted from event
arguments and preserved in normalized payload fields.
"""

from __future__ import annotations

import json as _json
import logging
import os
import re
from typing import Any, AsyncIterator

import httpx

from app.connectors.ai_base import StreamingAIConnector

logger = logging.getLogger(__name__)

# How long to wait for the /v1/runs POST to respond.
_POST_TIMEOUT = 30.0
# How long the SSE stream can sit idle before we give up (keepalive comes every 30 s).
_STREAM_IDLE_TIMEOUT = 90.0


def _find_first_mapping(*values: Any) -> dict[str, Any] | None:
    for value in values:
        if isinstance(value, dict):
            return value
    return None


def _decode_preview_json(preview: Any) -> dict[str, Any] | None:
    if not isinstance(preview, str) or not preview.strip():
        return None
    try:
        decoded = _json.loads(preview)
    except _json.JSONDecodeError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _extract_skill_name(tool_name: str, preview: Any, arguments: dict[str, Any] | None) -> tuple[str | None, str | None]:
    if tool_name != "skill_view":
        return None, None

    if arguments:
        name = arguments.get("name")
        file_path = arguments.get("file_path")
        if name:
            return str(name), str(file_path or "") or None

    preview_args = _decode_preview_json(preview)
    if preview_args:
        name = preview_args.get("name")
        file_path = preview_args.get("file_path")
        if name:
            return str(name), str(file_path or "") or None

    preview_text = str(preview or "")
    patterns = [
        r"name\s*=\s*'([^']+)'",
        r"name\s*=\s*\"([^\"]+)\"",
        r"\"name\"\s*:\s*\"([^\"]+)\"",
        r"'name'\s*:\s*'([^']+)'",
    ]
    skill_name = None
    for pattern in patterns:
        match = re.search(pattern, preview_text)
        if match:
            skill_name = match.group(1)
            break

    file_match = None
    file_patterns = [
        r"file_path\s*=\s*'([^']+)'",
        r"file_path\s*=\s*\"([^\"]+)\"",
        r"\"file_path\"\s*:\s*\"([^\"]+)\"",
        r"'file_path'\s*:\s*'([^']+)'",
    ]
    for pat in file_patterns:
        file_match = re.search(pat, preview_text)
        if file_match:
            break

    return skill_name, (file_match.group(1) if file_match else None)


def _normalize_tool_event(event: dict[str, Any], *, completed: bool) -> dict[str, Any]:
    tool_name = str(event.get("tool") or event.get("tool_name") or event.get("function_name") or "")
    preview = event.get("preview")
    arguments = _find_first_mapping(
        event.get("arguments"),
        event.get("args"),
        event.get("function_args"),
        event.get("input"),
        _decode_preview_json(preview),
    )
    skill_name, skill_file_path = _extract_skill_name(tool_name, preview, arguments)
    payload: dict[str, Any] = {
        "type": "tool_complete" if completed else "tool_start",
        "tool": tool_name,
        "tool_name": tool_name,
        "function_name": tool_name,
        "preview": preview,
        "arguments": arguments,
        "raw_event": event,
    }
    if event.get("id") or event.get("tool_call_id"):
        payload["tool_call_id"] = event.get("tool_call_id") or event.get("id")
    if skill_name:
        payload["skill_name"] = skill_name
    if skill_file_path:
        payload["skill_file_path"] = skill_file_path
    if completed:
        payload["duration"] = event.get("duration")
        payload["error"] = bool(event.get("error", False))
    return payload


class HermesConnector:
    """Hermes-native agent runs connector.

    Uses POST /v1/runs to start a run then GET /v1/runs/{run_id}/events to
    consume the structured SSE lifecycle stream.

    Platform name ``hermes`` — the canonical connector for all Hermes dispatch tasks.
    """

    platform_name = "hermes"

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
          {"type": "tool_start",    "tool": str, "tool_name": str, ...}
          {"type": "tool_complete", "tool": str, "duration": float | None, "error": bool, ...}
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
            yield {"type": "error", "error": "hermes_connector: no user message found"}
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
            yield {"type": "error", "error": "hermes_connector: no run_id returned"}
            return

        logger.debug("[hermes] started run %s", run_id)

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
                            yield _normalize_tool_event(event, completed=False)

                        elif etype == "tool.completed":
                            yield _normalize_tool_event(event, completed=True)

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
            logger.exception("[hermes] run %s stream error", run_id)
            yield {"type": "error", "error": f"hermes_runs_stream_exception: {exc}"}


# Satisfy the StreamingAIConnector protocol at import time.
assert isinstance(HermesConnector(), StreamingAIConnector)

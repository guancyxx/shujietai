"""TaskWorker — async background runner for dispatch orchestration (ADR-0004).

Each DispatchTask in 'running' state gets an asyncio.Task running this worker.
The worker delegates to the appropriate StreamingAIConnector (via registry),
streams responses into dispatch events, and broadcasts progress via WsManager.

State machine transitions are driven by the worker and persisted by DispatchService.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.connectors.registry import get_connector, list_platforms
from app.schemas import DispatchTaskItem
from app.services.dispatch_service import DispatchService
from app.services.ws_manager import WsManager

logger = logging.getLogger(__name__)

# Marker the AI uses to signal it needs human input.
_AWAITING_INPUT_MARKER = "[AWAITING_INPUT]"


class TaskWorker:
    """Single-task async worker. One instance per dispatch task run."""

    def __init__(
        self,
        task: DispatchTaskItem,
        dispatch_service: DispatchService,
        ws_manager: WsManager,
    ) -> None:
        self._task = task
        self._svc = dispatch_service
        self._ws = ws_manager
        self._cancelled = False

    async def run(self) -> None:
        """Main entry point — called as an asyncio.Task."""
        task_id = self._task.id

        try:
            await self._ws.broadcast(task_id, "status", {"status": "running"})
            await self._execute_ai_call()

        except asyncio.CancelledError:
            # User cancelled via API
            self._svc.cancel_task(task_id)
            await self._ws.broadcast(task_id, "cancelled", {})
            logger.info("Dispatch task %s cancelled", task_id)

        except Exception as exc:
            error_msg = str(exc)[:500]
            self._svc.transition_task(task_id, "failed", error_message=error_msg)
            self._svc.add_event(task_id, "error", {"error": error_msg})
            await self._ws.broadcast(task_id, "error", {"error": error_msg})
            logger.exception("Dispatch task %s failed: %s", task_id, error_msg)

    def _write_assistant_to_store(self, content: str) -> None:
        """Persist the AI reply into the canonical timeline storage."""
        if not content.strip():
            return

        external_id = (self._task.external_session_id or "").strip()
        if not external_id:
            return

        platform = (self._task.ai_platform or "hermes").strip() or "hermes"
        try:
            self._svc.persist_message_to_session(
                platform=platform,
                external_session_id=external_id,
                role="assistant",
                content=content,
                content_type="text/markdown",
            )
        except Exception as exc:
            logger.warning("Failed to persist assistant reply for task %s: %s", self._task.id, exc)

    async def _execute_ai_call(self) -> None:
        """Execute the AI connector call and stream results."""
        task_id = self._task.id
        config = self._task.config or {}
        ai_platform = self._task.ai_platform

        # Look up connector from registry
        connector = get_connector(ai_platform)
        if connector is None:
            available = ", ".join(list_platforms()) or "(none)"
            raise RuntimeError(f"unsupported_ai_platform: {ai_platform} (available: {available})")

        # Build messages from config + history
        history = self._svc.reconstruct_history(task_id)
        messages = self._build_messages(history, config)

        # Determine if this is a fresh call or a resume
        if not history:
            messages.append({"role": "user", "content": self._task.initial_prompt})
            self._svc.add_event(task_id, "content_delta", {
                "role": "user",
                "content": self._task.initial_prompt,
            })

        # Stream from the connector and process chunks
        full_content = ""
        tool_calls_log: list[dict] = []

        async for chunk in connector.stream_completion(messages, config):
            if self._cancelled:
                return

            chunk_type = chunk.get("type")

            if chunk_type == "content":
                content_piece = chunk["content"]
                full_content += content_piece
                self._svc.add_event(task_id, "content_delta", {
                    "role": "assistant",
                    "content": content_piece,
                })
                await self._ws.broadcast(task_id, "content_delta", {
                    "role": "assistant",
                    "content": content_piece,
                })

            elif chunk_type == "tool_call":
                tc_info = {
                    "index": chunk.get("index", 0),
                    "id": chunk.get("id", ""),
                    "function_name": chunk.get("function_name", ""),
                    "function_args_delta": chunk.get("function_args_delta", ""),
                }
                tool_calls_log.append(tc_info)
                self._svc.add_event(task_id, "tool_call", tc_info)
                await self._ws.broadcast(task_id, "tool_call", tc_info)

            elif chunk_type == "finish":
                finish_reason = chunk.get("finish_reason", "")
                usage = chunk.get("usage", {})
                self._svc.add_event(task_id, "progress", {
                    "finish_reason": finish_reason,
                    "usage": usage,
                })

            elif chunk_type == "error":
                raise RuntimeError(chunk.get("error", "unknown_connector_error"))

        # Store the complete assistant message in dispatch events.
        self._svc.add_event(task_id, "content_full", {
            "role": "assistant",
            "content": full_content,
        })
        # Persist into session timeline storage so message survives page switches/reloads.
        self._write_assistant_to_store(full_content)

        # Check if the AI is requesting human input
        if full_content.strip().startswith(_AWAITING_INPUT_MARKER):
            prompt = full_content.strip()[len(_AWAITING_INPUT_MARKER):].strip()
            self._svc.transition_task(task_id, "awaiting_input")
            self._svc.add_event(task_id, "await_input", {"prompt": prompt})
            await self._ws.broadcast(task_id, "await_input", {"prompt": prompt})
        else:
            summary = full_content[:200] if full_content else "(no content)"
            self._svc.transition_task(task_id, "completed")
            self._svc.add_event(task_id, "completed", {"summary": summary})
            await self._ws.broadcast(task_id, "completed", {"summary": summary})

    def _build_messages(
        self,
        history: list[dict[str, str]],
        config: dict[str, Any],
    ) -> list[dict[str, str]]:
        """Build the messages array for the AI API call."""
        messages: list[dict[str, str]] = []
        system_prompt = config.get("system_prompt", "")
        if system_prompt and system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt.strip()})
        messages.extend(history)
        return messages


class DispatchWorkerPool:
    """Manages asyncio.Task instances for active dispatch tasks."""

    def __init__(
        self,
        dispatch_service: DispatchService,
        ws_manager: WsManager,
    ) -> None:
        self._svc = dispatch_service
        self._ws = ws_manager
        # task_id -> asyncio.Task
        self._workers: dict[str, asyncio.Task] = {}

    def start_task(self, task: DispatchTaskItem) -> None:
        """Start a background asyncio.Task for the given dispatch task."""
        if task.id in self._workers:
            return  # Already running

        worker = TaskWorker(task=task, dispatch_service=self._svc, ws_manager=self._ws)
        atask = asyncio.create_task(worker.run(), name=f"dispatch-{task.id}")
        self._workers[task.id] = atask
        atask.add_done_callback(lambda t, tid=task.id: self._workers.pop(tid, None))

    def cancel_task(self, task_id: str) -> bool:
        """Cancel the asyncio.Task for a dispatch task. Returns True if found."""
        atask = self._workers.get(task_id)
        if atask is None:
            return False
        atask.cancel()
        return True

    def cancel_all(self) -> int:
        """Cancel all running asyncio.Tasks. Returns count of cancelled tasks."""
        count = 0
        for task_id, atask in list(self._workers.items()):
            atask.cancel()
            count += 1
        return count

    @property
    def active_count(self) -> int:
        return len(self._workers)

    @property
    def active_task_ids(self) -> list[str]:
        return list(self._workers.keys())
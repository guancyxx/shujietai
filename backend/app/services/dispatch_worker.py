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


def _tool_call_id(chunk: dict[str, Any]) -> str:
    raw = str(chunk.get("id") or "").strip()
    if raw:
        return raw
    index = int(chunk.get("index", 0) or 0)
    function_name = str(chunk.get("function_name") or "tool")
    return f"tc_{index}_{function_name}"


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
            running_task = self._svc.transition_task(task_id, "running", emit_status_event=False)
            if running_task is not None:
                self._task = running_task
            await self._emit_event(
                "status",
                {
                    "status": "running",
                    "updated_at": (self._task.updated_at.isoformat() if self._task.updated_at else None),
                },
                event_name="task.status.changed",
                status="running",
            )
            await self._execute_ai_call()

        except asyncio.CancelledError:
            # User cancelled via API
            cancelled_task = self._svc.cancel_task(task_id)
            if cancelled_task is not None:
                self._task = cancelled_task
            await self._emit_event(
                "cancelled",
                {},
                event_name="task.cancelled",
                status="cancelled",
            )
            logger.info("Dispatch task %s cancelled", task_id)

        except Exception as exc:
            error_msg = str(exc)[:500]
            failed_task = self._svc.transition_task(task_id, "failed", error_message=error_msg)
            if failed_task is not None:
                self._task = failed_task
            await self._emit_event(
                "error",
                {"error": error_msg},
                event_name="task.failed",
                status="failed",
            )
            logger.exception("Dispatch task %s failed: %s", task_id, error_msg)

    async def _emit_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        event_name: str,
        status: str | None = None,
        tool_call_id: str | None = None,
    ) -> None:
        task_id = self._task.id
        event_id = self._svc.add_event(
            task_id,
            event_type,
            payload,
            event_name=event_name,
            status=status,
            run_id=self._task.current_run_id,
            tool_call_id=tool_call_id,
        )
        event_item = self._svc.get_event(event_id)
        await self._ws.broadcast(
            task_id,
            event_type,
            payload,
            event_id=event_id,
            event_name=event_name,
            status=status,
            seq=(event_item.seq if event_item else None),
            run_id=self._task.current_run_id,
            tool_call_id=tool_call_id,
            created_at=(event_item.created_at.isoformat() if event_item else None),
        )

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
            await self._emit_event(
                "content_delta",
                {
                    "role": "user",
                    "content": self._task.initial_prompt,
                },
                event_name="message.user.delta",
                status=self._task.status,
            )

        # Stream from the connector and process chunks
        full_content = ""

        async for chunk in connector.stream_completion(messages, config):
            if self._cancelled:
                return

            chunk_type = chunk.get("type")

            if chunk_type == "content":
                content_piece = chunk["content"]
                full_content += content_piece
                await self._emit_event(
                    "content_delta",
                    {
                        "role": "assistant",
                        "content": content_piece,
                    },
                    event_name="message.assistant.delta",
                    status=self._task.status,
                )

            elif chunk_type == "tool_call":
                tool_call_id = _tool_call_id(chunk)
                function_name = chunk.get("function_name", "")
                function_args_delta = chunk.get("function_args_delta", "")
                await self._emit_event(
                    "tool_call",
                    {
                        "tool_call_id": tool_call_id,
                        "index": chunk.get("index", 0),
                        "id": chunk.get("id", ""),
                        "function_name": function_name,
                        "function_args_delta": function_args_delta,
                    },
                    event_name="tool.call.delta",
                    status=self._task.status,
                    tool_call_id=tool_call_id,
                )

            elif chunk_type == "finish":
                finish_reason = chunk.get("finish_reason", "")
                usage = chunk.get("usage", {})
                await self._emit_event(
                    "progress",
                    {
                        "finish_reason": finish_reason,
                        "usage": usage,
                    },
                    event_name="task.progress.finish",
                    status=self._task.status,
                )

            elif chunk_type == "error":
                raise RuntimeError(chunk.get("error", "unknown_connector_error"))

        # Store the complete assistant message in dispatch events.
        await self._emit_event(
            "content_full",
            {
                "role": "assistant",
                "content": full_content,
            },
            event_name="message.assistant.full",
            status=self._task.status,
        )
        # Persist into session timeline storage so message survives page switches/reloads.
        self._write_assistant_to_store(full_content)

        # Check if the AI is requesting human input
        if full_content.strip().startswith(_AWAITING_INPUT_MARKER):
            prompt = full_content.strip()[len(_AWAITING_INPUT_MARKER):].strip()
            awaiting_task = self._svc.transition_task(task_id, "awaiting_input", emit_status_event=False)
            if awaiting_task is not None:
                self._task = awaiting_task
            await self._emit_event(
                "await_input",
                {"prompt": prompt},
                event_name="task.awaiting_input",
                status="awaiting_input",
            )
        else:
            summary = full_content[:200] if full_content else "(no content)"
            completed_task = self._svc.transition_task(task_id, "completed", emit_status_event=False)
            if completed_task is not None:
                self._task = completed_task
            await self._emit_event(
                "completed",
                {"summary": summary},
                event_name="task.completed",
                status="completed",
            )

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

        refreshed = self._svc.start_new_run(task.id)
        if refreshed is not None:
            task = refreshed

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
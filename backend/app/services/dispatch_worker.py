"""TaskWorker — async background runner for dispatch orchestration (ADR-0004).

Each DispatchTask in 'running' state gets an asyncio.Task running this worker.
The worker delegates to the appropriate StreamingAIConnector (via registry),
streams responses into dispatch events, and broadcasts progress via WsManager.

State machine transitions are driven by the worker and persisted by DispatchService.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any, ClassVar

from app.connectors.registry import get_connector, list_platforms
from app.schemas import DispatchTaskItem, normalize_platform
from app.services.dispatch_service import DispatchService
from app.services.ws_manager import WsManager

logger = logging.getLogger(__name__)

# Marker the AI uses to signal it needs human input.
_AWAITING_INPUT_MARKER = "[AWAITING_INPUT]"


def _stringify_tool_args(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        import json
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(value)


def _normalize_tool_payload(chunk: dict[str, Any], *, tool_call_id: str) -> dict[str, Any]:
    tool_name = str(chunk.get("tool") or chunk.get("tool_name") or chunk.get("function_name") or "tool")
    function_name = str(chunk.get("function_name") or tool_name)
    arguments = chunk.get("arguments")
    function_args = chunk.get("function_args")
    preview = chunk.get("preview") or ""
    if function_args is None:
        function_args = arguments if arguments is not None else preview

    payload: dict[str, Any] = {
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "function_name": function_name,
        "preview": preview,
        "function_args": _stringify_tool_args(function_args),
    }
    if arguments is not None:
        payload["arguments"] = arguments
    if chunk.get("skill_name"):
        payload["skill_name"] = chunk["skill_name"]
    if chunk.get("skill_file_path"):
        payload["skill_file_path"] = chunk["skill_file_path"]
    if chunk.get("raw_event") is not None:
        payload["raw_event"] = chunk["raw_event"]
    return payload


def _tool_call_id(chunk: dict[str, Any]) -> str:
    raw = str(chunk.get("id") or "").strip()
    if raw:
        return raw
    index = int(chunk.get("index", 0) or 0)
    function_name = str(chunk.get("function_name") or "tool")
    return f"tc_{index}_{function_name}"


# ---------------------------------------------------------------------------
# Chunk handler registry types
# ---------------------------------------------------------------------------

@dataclass
class ChunkContext:
    """Mutable context shared across chunk handlers during one streaming call.

    Handler methods receive this as their second argument and can mutate
    ``full_content`` and ``tool_calls_in_flight``.  The ``cancelled`` flag is
    also exposed so handlers can optionally check it before expensive work.
    """

    full_content: str = ""
    tool_calls_in_flight: dict[str, dict[str, Any]] = field(default_factory=dict)
    cancelled: bool = False


# A chunk handler in the registry is an unbound TaskWorker method:
# (self, chunk, ctx) -> Coroutine[None].
ChunkHandler = Callable[
    ["TaskWorker", dict[str, Any], ChunkContext],
    Coroutine[Any, Any, None],
]


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
        self._interrupted = False
        self._interrupt_msg = ""
        self._tool_calls_in_flight: dict[str, dict[str, Any]] = {}

    def interrupt(self, user_message: str) -> None:
        self._interrupted = True
        self._interrupt_msg = user_message.strip()

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
            if self._interrupted:
                # Interrupt (revise) — non-terminal: stop current run, append correction, restart
                interrupted_task = self._svc.interrupt_task(task_id, self._interrupt_msg)
                if interrupted_task is not None:
                    self._task = interrupted_task
                await self._emit_event(
                    "interrupted",
                    {"reason": "user_revise", "user_message": self._interrupt_msg},
                    event_name="task.interrupted",
                    status=self._task.status,
                )
                await self._emit_event(
                    "content_delta",
                    {"role": "user", "content": self._interrupt_msg},
                    event_name="message.user.delta",
                    status=self._task.status,
                )
                self._tool_calls_in_flight.clear()
                self._interrupted = False
                self._interrupt_msg = ""
                # Assign a new run ID for the restarted conversation
                refreshed = self._svc.start_new_run(task_id)
                if refreshed is not None:
                    self._task = refreshed
                # Start a new run in the same dispatch conversation context
                await self._execute_ai_call()
                logger.info("Dispatch task %s interrupted and revised", task_id)
            else:
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
                self._tool_calls_in_flight.clear()
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
            self._tool_calls_in_flight.clear()
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

        platform = normalize_platform(self._task.ai_platform)
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

    # ------------------------------------------------------------------
    # Chunk handlers — one method per chunk type (Open/Closed Principle)
    # ------------------------------------------------------------------

    _chunk_handlers: ClassVar[dict[str, ChunkHandler]] = {}

    async def _handle_content(
        self, chunk: dict[str, Any], ctx: ChunkContext
    ) -> None:
        content_piece = chunk["content"]
        ctx.full_content += content_piece
        await self._emit_event(
            "content_delta",
            {"role": "assistant", "content": content_piece},
            event_name="message.assistant.delta",
            status=self._task.status,
        )

    async def _handle_tool_call(
        self, chunk: dict[str, Any], ctx: ChunkContext
    ) -> None:
        tool_call_id = _tool_call_id(chunk)
        function_name = chunk.get("function_name", "")
        function_args_delta = chunk.get("function_args_delta", "")
        current_tool = ctx.tool_calls_in_flight.get(tool_call_id)

        if current_tool is None:
            current_tool = {
                "function_name": function_name,
                "function_args": "",
                "index": chunk.get("index", 0),
                "id": chunk.get("id", ""),
            }
            ctx.tool_calls_in_flight[tool_call_id] = current_tool
            await self._emit_event(
                "tool_call",
                {
                    "tool_call_id": tool_call_id,
                    "index": current_tool["index"],
                    "id": current_tool["id"],
                    "function_name": function_name,
                },
                event_name="tool.call.started",
                status=self._task.status,
                tool_call_id=tool_call_id,
            )

        if function_name:
            current_tool["function_name"] = function_name
        if function_args_delta:
            current_tool["function_args"] += function_args_delta
            await self._emit_event(
                "tool_call",
                {
                    "tool_call_id": tool_call_id,
                    "function_name": current_tool["function_name"],
                    "function_args_delta": function_args_delta,
                },
                event_name="tool.call.delta",
                status=self._task.status,
                tool_call_id=tool_call_id,
            )

    async def _handle_finish(
        self, chunk: dict[str, Any], ctx: ChunkContext
    ) -> None:
        for tool_call_id, tool_state in list(ctx.tool_calls_in_flight.items()):
            await self._emit_event(
                "tool_call",
                {
                    "tool_call_id": tool_call_id,
                    "function_name": tool_state.get("function_name", "tool"),
                    "function_args": tool_state.get("function_args", ""),
                },
                event_name="tool.call.completed",
                status=self._task.status,
                tool_call_id=tool_call_id,
            )
        ctx.tool_calls_in_flight.clear()

        finish_reason = chunk.get("finish_reason", "")
        usage = chunk.get("usage", {})
        await self._emit_event(
            "progress",
            {"finish_reason": finish_reason, "usage": usage},
            event_name="task.progress.finish",
            status=self._task.status,
        )

    async def _handle_tool_start(
        self, chunk: dict[str, Any], ctx: ChunkContext
    ) -> None:
        # Emitted by the Hermes connector when a tool invocation begins.
        tool_name = str(
            chunk.get("tool")
            or chunk.get("tool_name")
            or chunk.get("function_name")
            or "tool"
        )
        tool_call_id = str(
            chunk.get("tool_call_id")
            or chunk.get("id")
            or f"run_tool_{tool_name}_{id(chunk)}"
        )
        payload = _normalize_tool_payload(chunk, tool_call_id=tool_call_id)
        ctx.tool_calls_in_flight[tool_call_id] = {
            "function_name": payload["function_name"],
            "tool_name": payload["tool_name"],
            "function_args": payload.get("function_args", ""),
            "index": len(ctx.tool_calls_in_flight),
            "id": tool_call_id,
            "started_at": __import__("time").monotonic(),
            "payload": payload,
        }
        await self._emit_event(
            "tool_call",
            payload,
            event_name="tool.call.started",
            status=self._task.status,
            tool_call_id=tool_call_id,
        )

    async def _handle_tool_complete(
        self, chunk: dict[str, Any], ctx: ChunkContext
    ) -> None:
        # Match the in-flight record by stable id first, then tool name.
        tool_name = str(
            chunk.get("tool")
            or chunk.get("tool_name")
            or chunk.get("function_name")
            or "tool"
        )
        matched_id: str | None = (
            str(chunk.get("tool_call_id") or chunk.get("id") or "")
            or None
        )
        if matched_id not in ctx.tool_calls_in_flight:
            matched_id = None
            for tid, state in ctx.tool_calls_in_flight.items():
                if (
                    state.get("tool_name") == tool_name
                    or state.get("function_name") == tool_name
                ):
                    matched_id = tid
                    break
        if matched_id is None:
            matched_id = f"run_tool_{tool_name}_complete"

        duration = chunk.get("duration")
        is_error = bool(chunk.get("error", False))
        state = ctx.tool_calls_in_flight.get(matched_id) or {}
        started = state.get("started_at")
        if duration is None and started is not None:
            import time

            duration = round(time.monotonic() - started, 3)

        base_payload = dict(state.get("payload") or {})
        base_payload.update(
            _normalize_tool_payload(chunk, tool_call_id=matched_id)
        )
        base_payload["duration"] = duration
        base_payload["duration_ms"] = (
            round(float(duration) * 1000) if duration is not None else None
        )
        base_payload["error"] = is_error

        ctx.tool_calls_in_flight.pop(matched_id, None)
        await self._emit_event(
            "tool_call",
            base_payload,
            event_name="tool.call.completed",
            status=self._task.status,
            tool_call_id=matched_id,
        )

    async def _handle_agent_thinking(
        self, chunk: dict[str, Any], ctx: ChunkContext
    ) -> None:
        # Reasoning text from extended-thinking models.
        thinking_text = chunk.get("text", "")
        if thinking_text:
            await self._emit_event(
                "agent_thinking",
                {"text": thinking_text},
                event_name="agent.thinking",
                status=self._task.status,
            )

    # Unused chunk dict; kept so the handler always receives two args.
    async def _handle_error(
        self, chunk: dict[str, Any], _ctx: ChunkContext
    ) -> None:
        raise RuntimeError(
            chunk.get("error", "unknown_connector_error")
        )

    async def _execute_ai_call(self) -> None:
        """Execute the AI connector call and stream results via handler registry."""
        task_id = self._task.id
        config = self._task.config or {}
        ai_platform = self._task.ai_platform

        # Look up connector from registry
        connector = get_connector(ai_platform)
        if connector is None:
            available = ", ".join(list_platforms()) or "(none)"
            raise RuntimeError(
                f"unsupported_ai_platform: {ai_platform} (available: {available})"
            )

        # Build messages from config + history
        history = self._svc.reconstruct_history(task_id)
        messages = self._build_messages(history, config)

        # Determine if this is a fresh call or a resume
        if not history:
            messages.append(
                {"role": "user", "content": self._task.initial_prompt}
            )
            await self._emit_event(
                "content_delta",
                {"role": "user", "content": self._task.initial_prompt},
                event_name="message.user.delta",
                status=self._task.status,
            )

        ctx = ChunkContext(
            full_content="",
            tool_calls_in_flight=self._tool_calls_in_flight,
            cancelled=self._cancelled,
        )

        # Stream from the connector and dispatch via handler registry
        async for chunk in connector.stream_completion(messages, config):
            if self._cancelled:
                return

            chunk_type = chunk.get("type")
            handler = self._chunk_handlers.get(chunk_type)
            if handler is not None:
                ctx.cancelled = self._cancelled
                await handler(self, chunk, ctx)

        # Store the complete assistant message in dispatch events.
        await self._emit_event(
            "content_full",
            {"role": "assistant", "content": ctx.full_content},
            event_name="message.assistant.full",
            status=self._task.status,
        )
        # Persist into session timeline storage so message survives page switches/reloads.
        self._write_assistant_to_store(ctx.full_content)

        # Check if the AI is requesting human input
        if ctx.full_content.strip().startswith(_AWAITING_INPUT_MARKER):
            prompt = (
                ctx.full_content.strip()[len(_AWAITING_INPUT_MARKER) :].strip()
            )
            awaiting_task = self._svc.transition_task(
                task_id, "awaiting_input", emit_status_event=False
            )
            if awaiting_task is not None:
                self._task = awaiting_task
            await self._emit_event(
                "await_input",
                {"prompt": prompt},
                event_name="task.awaiting_input",
                status="awaiting_input",
            )
        else:
            summary = (
                ctx.full_content[:200] if ctx.full_content else "(no content)"
            )
            completed_task = self._svc.transition_task(
                task_id, "completed", emit_status_event=False
            )
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


# ---------------------------------------------------------------------------
# Populate the handler registry (done at module level so all handler names are
# bound; adding a new chunk type requires only this dict + a handler method).
# ---------------------------------------------------------------------------
TaskWorker._chunk_handlers = {
    "content": TaskWorker._handle_content,
    "content_delta": TaskWorker._handle_content,
    "tool_call": TaskWorker._handle_tool_call,
    "finish": TaskWorker._handle_finish,
    "tool_start": TaskWorker._handle_tool_start,
    "tool_complete": TaskWorker._handle_tool_complete,
    "agent_thinking": TaskWorker._handle_agent_thinking,
    "error": TaskWorker._handle_error,
}


class DispatchWorkerPool:
    """Manages asyncio.Task instances for active dispatch tasks."""

    def __init__(
        self,
        dispatch_service: DispatchService,
        ws_manager: WsManager,
    ) -> None:
        self._svc = dispatch_service
        self._ws = ws_manager
        # task_id -> (asyncio.Task, TaskWorker)
        self._workers: dict[str, tuple[asyncio.Task, TaskWorker]] = {}

    def start_task(self, task: DispatchTaskItem) -> None:
        """Start a background asyncio.Task for the given dispatch task."""
        if task.id in self._workers:
            return  # Already running

        refreshed = self._svc.start_new_run(task.id)
        if refreshed is not None:
            task = refreshed

        worker = TaskWorker(task=task, dispatch_service=self._svc, ws_manager=self._ws)
        atask = asyncio.create_task(worker.run(), name=f"dispatch-{task.id}")
        self._workers[task.id] = (atask, worker)
        atask.add_done_callback(lambda t, tid=task.id: self._workers.pop(tid, None))

    def cancel_task(self, task_id: str) -> bool:
        """Cancel the asyncio.Task for a dispatch task. Returns True if found."""
        entry = self._workers.get(task_id)
        if entry is None:
            return False
        atask, _worker = entry
        atask.cancel()
        return True

    def interrupt_task(self, task_id: str, user_message: str) -> bool:
        """Interrupt running worker and restart with user correction."""
        entry = self._workers.get(task_id)
        if entry is None:
            return False
        atask, worker = entry
        if atask.done():
            return False
        worker.interrupt(user_message)
        atask.cancel()  # CancelledError triggers interrupt path in run()
        return True

    def cancel_all(self) -> int:
        """Cancel all running asyncio.Tasks. Returns count of cancelled tasks."""
        count = 0
        for task_id, (atask, _worker) in list(self._workers.items()):
            atask.cancel()
            count += 1
        return count

    @property
    def active_count(self) -> int:
        return len(self._workers)

    @property
    def active_task_ids(self) -> list[str]:
        return list(self._workers.keys())

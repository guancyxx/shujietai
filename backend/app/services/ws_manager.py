"""WebSocket connection manager for dispatch orchestration layer (ADR-0004).

Manages client subscriptions and broadcasts dispatch events to connected clients.
All operations are designed for single-process asyncio deployment (no Redis needed).
"""

from __future__ import annotations

import asyncio
import json as json_module
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class WsManager:
    """In-process WebSocket connection manager.

    Clients subscribe to specific dispatch task IDs.
    When a task emits an event, it is broadcast to all subscribed WebSocket connections.
    """

    def __init__(self) -> None:
        # task_id -> set of WebSocket connections
        self._subscriptions: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, task_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._subscriptions[task_id].add(websocket)

    async def unsubscribe(self, task_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            subs = self._subscriptions.get(task_id)
            if subs:
                subs.discard(websocket)
                if not subs:
                    del self._subscriptions[task_id]

    async def unsubscribe_all(self, websocket: WebSocket) -> None:
        async with self._lock:
            to_remove: list[str] = []
            for task_id, subs in self._subscriptions.items():
                subs.discard(websocket)
                if not subs:
                    to_remove.append(task_id)
            for task_id in to_remove:
                del self._subscriptions[task_id]

    async def broadcast(
        self,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        event_id: str | None = None,
        event_name: str | None = None,
        status: str | None = None,
        seq: int | None = None,
        run_id: str | None = None,
        tool_call_id: str | None = None,
        created_at: str | None = None,
    ) -> None:
        async with self._lock:
            subscribers = list(self._subscriptions.get(task_id, set()))

        message_payload: dict[str, Any] = {
            "event_type": event_type,
            "task_id": task_id,
            "payload": payload,
        }
        if event_id is not None:
            message_payload["event_id"] = event_id
        if event_name is not None:
            message_payload["event_name"] = event_name
        if status is not None:
            message_payload["status"] = status
        if seq is not None:
            message_payload["seq"] = seq
        if run_id is not None:
            message_payload["run_id"] = run_id
        if tool_call_id is not None:
            message_payload["tool_call_id"] = tool_call_id
        if created_at is not None:
            message_payload["created_at"] = created_at

        message = json_module.dumps(message_payload)

        for ws in subscribers:
            try:
                await ws.send_text(message)
            except Exception:
                # Connection likely closed; clean up on next unsubscribe
                pass


# Global singleton
ws_manager = WsManager()
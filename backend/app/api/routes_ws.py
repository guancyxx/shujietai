"""WebSocket endpoint for dispatch orchestration (ADR-0004).

Path: ws://host:18000/api/v1/ws

Protocol:
  Client → Server:
    { "action": "subscribe_task", "task_id": "dt_xxx" }
    { "action": "unsubscribe_task", "task_id": "dt_xxx" }

  Server → Client:
    { "type": "task_status", "task_id": "...", "status": "..." }
    { "type": "content_delta", "task_id": "...", "content": "..." }
    ...etc (see ADR-0004 spec)
"""

from __future__ import annotations

import json as json_module
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.ws_manager import WsManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    ws_manager: WsManager = websocket.app.state.ws_manager
    subscribed_tasks: set[str] = set()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json_module.loads(raw)
            except json_module.JSONDecodeError:
                await websocket.send_text(json_module.dumps({
                    "type": "error",
                    "detail": "invalid_json",
                }))
                continue

            action = message.get("action", "")
            task_id = message.get("task_id", "")

            if not task_id:
                await websocket.send_text(json_module.dumps({
                    "type": "error",
                    "detail": "missing_task_id",
                }))
                continue

            if action == "subscribe_task":
                await ws_manager.subscribe(task_id, websocket)
                subscribed_tasks.add(task_id)
                await websocket.send_text(json_module.dumps({
                    "type": "subscribed",
                    "task_id": task_id,
                }))

            elif action == "unsubscribe_task":
                await ws_manager.unsubscribe(task_id, websocket)
                subscribed_tasks.discard(task_id)
                await websocket.send_text(json_module.dumps({
                    "type": "unsubscribed",
                    "task_id": task_id,
                }))

            else:
                await websocket.send_text(json_module.dumps({
                    "type": "error",
                    "detail": f"unknown_action: {action}",
                }))

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    finally:
        # Clean up all subscriptions
        for task_id in subscribed_tasks:
            await ws_manager.unsubscribe(task_id, websocket)

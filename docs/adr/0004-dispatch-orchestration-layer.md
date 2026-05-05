# ADR-0004: Introduce Dispatch Orchestration Layer

## Status
Accepted

## Date
2026-04-30

## Context

The current architecture couples the frontend directly to AI platforms (Hermes) via synchronous request-response or SSE streaming:

- Frontend clicks "start conversation" on a task card → directly calls `POST /api/v1/connectors/hermes/chat` or `/chat/stream`
- The frontend must stay connected for the entire AI processing duration
- If the AI processing is interrupted (network issue, browser refresh, etc.) the conversation is lost
- If the AI requests human clarification, there is no structured mechanism to pause and resume
- There is no way to forcibly cancel a running AI conversation
- The task board items and AI sessions have no direct operational linkage

Key realization: the user does not need real-time interactive AI conversation. They only need to:
1. Start a task from a task card
2. Know the AI's progress and final result asynchronously
3. Respond when the AI asks for clarification
4. Cancel a task when needed

## Decision

Add a **Dispatch Orchestration Layer** between the frontend and AI connectors. This layer:

1. Converts the synchronous "start conversation" action into an asynchronous task (`DispatchTask`)
2. Runs AI connector calls as background `asyncio.Task` workers
3. Broadcasts progress events via WebSocket to subscribed frontend clients
4. Manages a task state machine for pause/resume/cancel/abort
5. Persists all conversation history in `DispatchEvent` records for crash recovery

### Architecture

```
Frontend ←─WebSocket──→ Dispatch Orchestrator ←─Connector──→ AI Platform (Hermes)
                              │
                        ┌─────┴─────┐
                        │Task Table │
                        └───────────┘
```

### Data Model

**DispatchTask** — one per task card "start" action:
- `id`, `task_board_item_id` (FK to task board), `status`, `ai_platform`
- `external_session_id` (populated after AI session created)
- `current_run_id`, `last_sequence`, `started_at`, `finished_at` (observability and run lifecycle)
- `config` JSON (system_prompt, model, skills, etc.)
- `initial_prompt` (user's first message)
- `error_message`, `created_at`, `updated_at`

**DispatchEvent** — append-only event log per task:
- `id`, `task_id` (FK), `seq`, `event_type`, `event_name`, `status`, `run_id`, `tool_call_id`, `payload` JSON, `created_at`
- `event_type` keeps backward compatibility with older consumers
- `event_name` provides stable semantic names for observability and frontend rendering
- `seq` is strictly increasing per `task_id` and enables deterministic timeline rebuild
- event_types: `status`, `progress`, `content_delta`, `content_full`, `tool_call`, `await_input`, `completed`, `error`, `cancelled`

### Task State Machine

```
queued → running → completed
                 ↘ failed
                 ↘ awaiting_input → running (resume with user input)
                 ↘ paused → running (manual resume)
running → cancelled (user force-cancel)
running → aborted (hard stop, no recovery)
```

### Session Recovery (Problem 1)

Three-layer recovery strategy:

1. **L1 — State persistence**: `DispatchTask.status` + `external_session_id` are persisted in PostgreSQL. On process restart, scan for `status=running` tasks and mark them `paused`.

2. **L2 — Context snapshot**: Every AI response (including partial streaming content) is stored as `DispatchEvent` records. On resume, the dispatcher reconstructs the full message history from events and sends it as `history_messages` to the AI connector.

3. **L3 — Checkpoint resume**: `awaiting_input` tasks auto-pause when AI needs clarification. The frontend receives a WebSocket event with the clarification prompt. User responds via `POST /api/v1/dispatch/{task_id}/resume`. The dispatcher appends the new user message and re-invokes the AI.

### Force Interrupt (Problem 2)

| Operation | API | Behavior |
|-----------|-----|----------|
| Cancel | `POST /dispatch/{id}/cancel` | `asyncio.Task.cancel()`, mark task `cancelled`, partial content preserved in events |
| Abort | `POST /dispatch/{id}/abort` | Cancel + disconnect AI + stop retries, unrecoverable |
| Emergency stop | `POST /dispatch/emergency-stop` | Cancel all running tasks |

### WebSocket Protocol

Path: `ws://localhost:18000/api/v1/ws`

Client → Server:
- `{ action: "subscribe_task", task_id: "..." }`
- `{ action: "unsubscribe_task", task_id: "..." }`

Server → Client (current envelope):
- Base fields:
  - `event_type`, `task_id`, `payload`
- Optional observability fields:
  - `event_id`, `event_name`, `status`, `seq`, `run_id`, `tool_call_id`, `created_at`

Compatibility note:
- Frontend consumer accepts both `event_type` and legacy `type`.
- `event_type` remains the canonical routing key.

## Alternatives Considered

### A: Keep synchronous but add reconnection
- Pros: Minimal code changes
- Cons: Still couples frontend to AI; no structured pause/resume; SSE reconnect can't guarantee message continuity

### B: Use a message queue (Celery/RQ) instead of in-process asyncio
- Pros: More robust for distributed deployment
- Cons: Adds Redis dependency for task broker; overkill for current single-instance MVP; Celery workers don't share asyncio event loop with FastAPI

### C: Use existing ingest retry worker pattern for dispatch
- Pros: Reuses existing infrastructure
- Cons: Ingest retry is fire-and-forget (no streaming, no two-way communication). Dispatch needs bidirectional real-time communication which the retry loop model cannot provide.

## Consequences

- Frontend and AI platform are fully decoupled: frontend talks to dispatch layer only
- WebSocket replaces both REST polling and SSE streaming for AI progress
- Task board items gain operational semantics (start → track → complete)
- `awaiting_input` enables structured human-in-the-loop workflows
- Process crash recovery is automatic on restart
- Event timelines become deterministic and auditable via per-task sequence (`seq`) and run identity (`run_id`)
- Tool call traces become queryable by `tool_call_id` for debugging and postmortem analysis
- Future multi-connector support becomes straightforward (just add new connector adapters)
- The existing `/connectors/hermes/chat` and `/chat/stream` endpoints remain functional for backward compatibility but are superseded by the dispatch API

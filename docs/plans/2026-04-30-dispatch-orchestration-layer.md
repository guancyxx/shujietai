# Dispatch Orchestration Layer — Implementation Spec

## Objective

Decouple the frontend from AI platforms by introducing an async dispatch layer. Users start tasks from task cards, the system runs them asynchronously, and progress/results are pushed via WebSocket.

## Tech Stack

- **Backend**: Python 3.12 + FastAPI + SQLAlchemy + Alembic (existing stack)
- **WS**: FastAPI WebSocket (`fastapi.WebSocket`) — no external dependency
- **Async workers**: `asyncio.Task` within FastAPI event loop (same process)
- **DB**: PostgreSQL 16 (existing)
- **No new infrastructure**: Redis pub/sub NOT used; broadcast is in-process dict

## Data Model

### dispatch_tasks table

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | VARCHAR(64) | PK | `dt_{uuid4_hex[:12]}` |
| task_board_item_id | VARCHAR(64) | FK → task_board_items.id, nullable | Linked task card |
| status | VARCHAR(32) | NOT NULL, default='queued' | queued/running/awaiting_input/paused/completed/failed/cancelled/aborted |
| ai_platform | VARCHAR(64) | NOT NULL, default='hermes' | Which connector to use |
| external_session_id | VARCHAR(255) | nullable | AI platform session ID (populated after first call) |
| config | JSON | NOT NULL, default={} | {system_prompt, model, skills, mcp_servers} |
| initial_prompt | TEXT | NOT NULL | User's first message |
| error_message | TEXT | nullable | Last error if status=failed |
| created_at | TIMESTAMPTZ | NOT NULL | |
| updated_at | TIMESTAMPTZ | NOT NULL | |

Indexes: `ix_dispatch_tasks_status` on status, `ix_dispatch_tasks_task_board_item_id` on task_board_item_id

### dispatch_events table

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | VARCHAR(64) | PK | `de_{uuid4_hex[:12]}` |
| task_id | VARCHAR(64) | FK → dispatch_tasks.id, NOT NULL | Parent task |
| event_type | VARCHAR(64) | NOT NULL | progress/content_delta/tool_call/await_input/completed/error/content_full |
| payload | JSON | NOT NULL, default={} | Event-specific data |
| created_at | TIMESTAMPTZ | NOT NULL | |

Indexes: `ix_dispatch_events_task_id` on task_id, `ix_dispatch_events_created_at` on created_at

## API Endpoints

### REST

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/v1/dispatch | List dispatch tasks (with status filter) |
| POST | /api/v1/dispatch | Create + start a dispatch task |
| GET | /api/v1/dispatch/{task_id} | Get dispatch task detail |
| GET | /api/v1/dispatch/{task_id}/events | Get events for a task (paginated) |
| POST | /api/v1/dispatch/{task_id}/resume | Resume an awaiting_input/paused task |
| POST | /api/v1/dispatch/{task_id}/cancel | Cancel a running/queued task |
| POST | /api/v1/dispatch/{task_id}/abort | Hard abort (unrecoverable) |
| POST | /api/v1/dispatch/emergency-stop | Cancel all running tasks |

### WebSocket

| Path | Description |
|------|-------------|
| ws://host:18000/api/v1/ws | Bidirectional real-time channel |

Client messages:
```json
{ "action": "subscribe_task", "task_id": "dt_xxx" }
{ "action": "unsubscribe_task", "task_id": "dt_xxx" }
```

Server messages:
```json
{ "type": "task_status", "task_id": "dt_xxx", "status": "running" }
{ "type": "content_delta", "task_id": "dt_xxx", "content": "partial..." }
{ "type": "content_full", "task_id": "dt_xxx", "content": "complete..." }
{ "type": "tool_call", "task_id": "dt_xxx", "function_name": "terminal", "function_args_delta": "..." }
{ "type": "await_input", "task_id": "dt_xxx", "prompt": "AI needs clarification on..." }
{ "type": "task_completed", "task_id": "dt_xxx", "summary": "..." }
{ "type": "task_error", "task_id": "dt_xxx", "error": "..." }
{ "type": "task_cancelled", "task_id": "dt_xxx" }
```

## Project Structure

### New files

```
backend/app/
  db/models.py               — add DispatchTaskEntity, DispatchEventEntity
  schemas.py                  — add DispatchCreateRequest, DispatchResumeRequest, etc.
  services/
    dispatch_service.py       — DispatchService (CRUD + state machine)
    dispatch_worker.py        — TaskWorker (asyncio background runner)
    ws_manager.py             — WebSocket connection manager + broadcast
  api/
    routes_dispatch.py        — REST endpoints for /api/v1/dispatch/*
    routes_ws.py              — WebSocket endpoint for /api/v1/ws
```

### Modified files

```
backend/app/main.py           — mount dispatch routes + WS route; add lifespan wiring
  alembic/versions/           — new migration for dispatch tables
```

## State Machine

```
                              ┌─── completed
queued ──► running ──────────┤
                 │            ├─── failed
                 │            │
                 ├──► awaiting_input ──(resume)──► running
                 │
                 ├──► paused ──(resume)──► running
                 │
                 ├──► cancelled
                 │
                 └──► aborted

Transitions:
  queued → running         : worker picks up task
  running → completed      : AI finished normally
  running → failed         : AI call raised exception (after retries exhausted)
  running → awaiting_input : AI response contains clarification request marker
  running → paused         : process crash recovery, or manual pause (future)
  running → cancelled      : user cancels via API
  running → aborted        : user hard-aborts via API
  awaiting_input → running : user provides input via /resume
  paused → running         : user resumes via /resume
```

## Session Recovery

### Crash recovery on process restart

In FastAPI lifespan startup:
1. Query all `DispatchTask` with `status='running'`
2. Set them to `status='paused'`
3. Log a warning for each

### Resume flow

1. User calls `POST /dispatch/{id}/resume` with `{ user_message: "..." }`
2. `DispatchService.resume_task()`:
   a. Validate status is `awaiting_input` or `paused`
   b. Create a `dispatch_event` with `event_type='content_delta'` for the user message
   c. Set status to `running`
   d. Start a new `TaskWorker` for this task
3. `TaskWorker`:
   a. Load all `dispatch_events` for this task
   b. Reconstruct `history_messages` from events
   c. Call AI connector with full history + new message
   d. Stream results → dispatch_events + WebSocket broadcast

## Force Interrupt

### Cancel (soft)

1. API: `POST /dispatch/{id}/cancel`
2. Locate the `asyncio.Task` for this dispatch task
3. Call `task.cancel()` → raises `CancelledError` in worker
4. Worker catches `CancelledError`, sets status to `cancelled`, saves partial events
5. Broadcast `task_cancelled` via WebSocket

### Abort (hard)

1. API: `POST /dispatch/{id}/abort`
2. Same as cancel but also:
   - Set status to `aborted` (not `cancelled`)
   - Do NOT save partial content
   - Close any open HTTP connections to AI platform

### Emergency stop

1. API: `POST /dispatch/emergency-stop`
2. Iterate all `asyncio.Task` in dispatch worker pool, cancel each
3. Set all `status='running'` tasks to `cancelled`

## Testing Strategy

- Unit tests for `DispatchService` state machine transitions
- Unit tests for `TaskWorker` with mocked AI connector
- Unit tests for `WsManager` subscribe/broadcast
- Integration test: create task → check status → resume → cancel
- Integration test: WebSocket subscription → receive events
- Crash recovery test: set running → restart → verify paused

## Success Criteria

1. Task card can start a dispatch task via REST API
2. Progress events stream to frontend via WebSocket in real-time
3. `awaiting_input` tasks can be resumed with new user input
4. Cancelled tasks stop immediately and broadcast cancellation
5. Crashed running tasks are recovered as paused on restart
6. Existing `/connectors/hermes/chat` endpoints still work

## Open Questions

- How does the AI signal `awaiting_input`? → For Hermes: when response contains a specific marker pattern or when tool call returns a "need_human_input" signal. For MVP: parse the assistant response for a convention like `[AWAITING_INPUT]` at the start.
- Should paused tasks auto-retry on restart? → No. MVP requires manual resume.
- Max concurrent dispatch tasks? → No hard limit for MVP; asyncio handles concurrency naturally.
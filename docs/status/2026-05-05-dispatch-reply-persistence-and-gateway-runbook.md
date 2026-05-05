# Dispatch Reply Persistence and Hermes Gateway Runbook

Date: 2026-05-05

## 1) Problem statement

Observed user-facing issue:
- Conversation starts successfully, but chat often shows no AI reply.
- After switching pages and coming back, reply history disappears.

## 2) Root causes confirmed

### A. Dispatch/session split
- Dispatch worker writes streaming data to `dispatch_events`.
- Session timeline API reads from `sessions/messages`.
- Without explicit persistence, replies are not durable in timeline view.

### B. Upstream streaming edge case
- Hermes/OpenAI-compatible stream may return role + finish chunks with no `delta.content`.
- Result: worker marks task completed but `content_full` is empty.

### C. Gateway network accessibility instability
- Hermes API server can bind to `127.0.0.1:8642` or flap during restart.
- Container cannot rely on direct 8642 in this state.

## 3) Code changes applied

### Backend persistence path
File: `backend/app/services/dispatch_worker.py`
- Added `_write_assistant_to_store()`.
- After `content_full` is assembled, persist assistant message into canonical session timeline storage.
- Guard clauses:
  - ignore empty content
  - ignore missing external session id

File: `backend/app/services/dispatch_service.py`
- Added session persistence method used by dispatch worker.
- Ensures assistant message can be written into `sessions/messages` path even for dispatch-created conversations.

### Hermes connector fallback for blank streaming content
File: `backend/app/connectors/hermes_streaming.py`
- Keep normal stream parsing.
- Track `saw_finish` and `saw_content`.
- If stream finished with no content, perform one non-stream fallback call (`stream=false`).
- Emit fallback content as regular `content` chunk to unblock downstream persistence.

## 4) Runtime stabilization

### Temporary transport fallback (recommended while gateway bind is unstable)
- Start host proxy: `0.0.0.0:8643 -> 127.0.0.1:8642`.
- Backend uses:
  - `HERMES_API_BASE_URL=http://host-gateway.internal:8643/v1`

Reason:
- Decouples container path from transient `8642` bind behavior.

## 5) Verified results

### API and stack health
- Backend health: `200`
- Frontend health: `200`

### Dispatch run
- Task reaches `completed`.
- Events now include non-empty assistant payload when stream content is absent:
  - `content_delta assistant ...`
  - `content_full assistant ...`

### Persistence
- Session record exists for dispatch external session id.
- Timeline endpoint returns assistant message after completion.
- Confirms page-switch/reload durability via timeline data source.

## 6) Remaining operational note

Current assistant content may still be an upstream provider error text (for example credits/quota failure), but it is now:
- visible in chat flow
- persisted in session timeline
- diagnosable by users and operators

This is preferred over silent empty completion.

## 7) Standard verification script

1) Create task:
- `POST /api/v1/dispatch`

2) Check task:
- `GET /api/v1/dispatch/{task_id}` should become `completed`

3) Check events:
- `GET /api/v1/dispatch/{task_id}/events`
- expect non-empty `content_full`

4) Check session mapping:
- `GET /api/v1/sessions` contains matching `external_session_id`

5) Check timeline durability:
- `GET /api/v1/sessions/{session_id}/timeline`
- expect assistant message present

## 8) Follow-up recommendations

- Fix Hermes gateway bind at source and remove 8643 proxy once stable.
- Keep non-stream fallback in connector as defensive compatibility behavior.

## 10) 2026-05-05 dispatch observability v2

### Objective
- Add fine-grained, queryable dispatch execution traces without breaking existing clients.
- Keep backward compatibility on `event_type` while introducing structured event metadata.

### Schema and migration
- New migration: `backend/alembic/versions/20260505_0007_dispatch_observability_v2.py`
- `dispatch_tasks` additions:
  - `current_run_id` (run identity)
  - `last_sequence` (monotonic event sequence per task)
  - `started_at`, `finished_at` (run lifecycle timestamps)
- `dispatch_events` additions:
  - `seq` (strict ordering per `task_id`)
  - `event_name` (semantic stable name)
  - `status` (task status snapshot at emit time)
  - `run_id` (links event to concrete run)
  - `tool_call_id` (tool-level trace key)
- Added indexes:
  - `ix_dispatch_events_task_id_seq`
  - `ix_dispatch_events_run_id`
  - `ix_dispatch_events_tool_call_id`
  - `ix_dispatch_tasks_current_run_id`
- Added uniqueness guarantee:
  - `uq_dispatch_events_task_seq` over (`task_id`, `seq`)

### Compatibility and backfill
- Migration backfills run ids, timestamps, and event ordering for existing records.
- SQLite test path is supported with dialect-aware migration logic.
- Existing clients that only read `event_type` continue to work.

### Service and worker behavior changes
- `DispatchService.add_event(...)` now allocates and persists per-task `seq` and rich event metadata.
- `DispatchService.transition_task(...)` emits structured status event (`task.status.changed`) and supports optional suppression for internal transitions.
- `DispatchWorkerPool.start_task(...)` now creates a fresh run id per started/resumed run.
- `TaskWorker` emits normalized semantic events including:
  - `task.status.changed`
  - `message.user.delta`
  - `message.assistant.delta`
  - `message.assistant.full`
  - `tool.call.started`
  - `tool.call.delta`
  - `tool.call.completed`
  - `task.progress.finish`
  - `task.awaiting_input`
  - `task.completed`
  - `task.failed`
  - `task.cancelled`

### WebSocket envelope updates
- Broadcast payload now includes optional observability fields:
  - `event_id`, `event_name`, `status`, `seq`, `run_id`, `tool_call_id`, `created_at`
- Base fields remain unchanged:
  - `event_type`, `task_id`, `payload`

### Integration payload examples (REST + WS)
- REST (`GET /api/v1/dispatch/{task_id}/events`) item example:
```json
{
  "id": "de_abc123",
  "task_id": "dt_abc123",
  "seq": 12,
  "event_type": "tool_call",
  "event_name": "tool.call.delta",
  "status": "running",
  "run_id": "dr_def456",
  "tool_call_id": "call_1",
  "payload": {
    "tool_call_id": "call_1",
    "function_name": "search_files",
    "function_args_delta": "{\"pattern\":\"dispatch\"}"
  },
  "created_at": "2026-05-05T08:00:00Z"
}
```
- WS message example:
```json
{
  "event_type": "tool_call",
  "task_id": "dt_abc123",
  "event_id": "de_abc123",
  "event_name": "tool.call.started",
  "status": "running",
  "seq": 11,
  "run_id": "dr_def456",
  "tool_call_id": "call_1",
  "payload": {
    "tool_call_id": "call_1",
    "function_name": "search_files"
  },
  "created_at": "2026-05-05T07:59:59Z"
}
```

### Frontend aggregation updates
- `frontend/src/composables/useDispatchTask.js` now:
  - merges REST and WS events using `seq + created_at` ordering
  - consumes new metadata (`event_name/status/seq/run_id/tool_call_id`)
  - aggregates tool-call deltas by `tool_call_id` for clearer tool trace display
  - uses robust status extraction from both top-level and payload status

### Verification
- Regression tests:
  - `backend/tests/test_dispatch_fallback_persistence.py`
  - `backend/tests/test_alembic_migration.py`
- Command run:
  - `docker compose exec -T backend pytest -q tests/test_dispatch_fallback_persistence.py tests/test_alembic_migration.py`
- Result:
  - `3 passed`

## 11) 2026-05-05 incremental UX + regression updates

### Frontend UX
- File: `frontend/src/composables/useDispatchTask.js`
- Added upstream-error classifier for common provider failures:
  - 401/authentication failure
  - insufficient credits/quota/billing
  - 429 rate limit
  - model unavailable
- When assistant text matches these upstream error signatures, timeline now renders a friendly `system` message instead of raw provider error body.
- Dispatch operation-level failures (`taskError`) also use the same friendly mapping.
- Fixed streaming merge compatibility: if a `content_delta` arrives without `payload.role`, fallback role now defaults to `assistant` consistently both for grouping and rendering.
- Fixed dispatch create payload shape mismatch: `system_prompt/model/skills/mcp_servers` are now sent as top-level fields (matching backend `DispatchCreateRequest`) instead of nested under `config`, so task context is actually delivered to AI.
- Fixed timeline reset consistency when deleting sessions:
  - `clearActiveTask()` is now called when deleting the currently selected session and when clearing all sessions.
  - Streaming UI state is explicitly reset (`isStreaming=false`, `streamingContent=''`) together with timeline data reset.
  - This prevents stale dispatch/event timeline content from remaining visible after conversation cleanup.
- Added real-time conversation progress panel in chat view (`frontend/src/App.vue` + `frontend/src/style.css`):
  - Replaced placeholder "会话状态" with a 4-step live progress tracker: "消息已发给 AI" → "任务进入调度" → "AI 处理中" → "返回结果".
  - Step states now reactively map from dispatch lifecycle (`queued/running/awaiting_input/completed/failed/cancelled`).
  - Added latest-event hint text sourced from dispatch event stream for immediate operator visibility.
- Refined conversation status UX:
  - Moved status display above the composer input and changed it to single latest status only.
  - Kept the right status panel as placeholder text to avoid duplicate state surfaces.
- Improved task-based session start context payload:
  - On "start conversation from task", frontend now resolves project + repository context from both task snapshot and project registry fallback.
  - Initial prompt now includes project name and repository URL explicitly (plus repository name when available), reducing agent drift from intended codebase.
  - `system_prompt` and `initial_prompt` now share consistent task+project context construction.
- Increased chat composer textarea size for better multi-line input (`min-height: 96px`, `max-height: 220px`, vertical resize enabled).

- File: `frontend/src/App.vue`
- Added `dispatchError` inline alert rendering in timeline header area.

- File: `frontend/src/style.css`
- Added `.dispatch-friendly-error` styling.

### Backend stream event consistency fix
- File: `backend/app/services/dispatch_worker.py`
- WebSocket `content_delta` broadcast now includes role in payload:
  - from `{ "content": "..." }`
  - to `{ "role": "assistant", "content": "..." }`
- This keeps WebSocket payload shape consistent with DB `dispatch_events` payload and prevents frontend from treating each delta as a separate assistant bubble.

### Regression tests
- File: `backend/tests/test_dispatch_fallback_persistence.py`
- Added test: connector stream has finish but no content -> non-stream fallback request is triggered and content chunk is emitted.
- Added test: worker still persists assistant message into session timeline path even when content arrives after a finish chunk (fallback-shaped stream).

# Spec: AI Event Detail Persistence & Display

## Objective
Add expandable detail panels to AI tool events in the ShuJieTai chat timeline. Users can click any tool_call event (including skill_view) to inspect full parameters, results, and error details. All event data persists in dispatch_events table and survives page refresh.

## Tech Stack
- Backend: Python 3.11+, FastAPI, SQLAlchemy, Alembic, httpx
- Frontend: Vue 3 (Composition API), Vite
- Persistence: dispatch_events table (existing)

## What Already Exists
- `dispatch_events` table with fields: id, task_id, seq, event_type, event_name, status, run_id, tool_call_id, payload (JSON)
- Hermes connector emits `tool_start` and `tool_complete` chunks with rich metadata
- Frontend `dispatchMessages` computed renders tool bubbles as `.msg-tool`
- Tool bubbles show: tool name, status icon, duration, collapsible args
- Events survive refresh via `restoreActiveDispatchTask()` + `GET /dispatch/{id}/events`

## What's Missing
- Tool result/output is not stored
- Users cannot click tool bubbles to see detailed event information
- No detail panel exists
- No truncation strategy for large payloads

## Changes

### Backend (Schema + Store)
1. Add `result_json` column to `dispatch_events` (JSON, nullable)
2. Alembic migration
3. Add `result_json` to `DispatchEventEntity` model
4. Add `result_json` to `DispatchEventItem` schema
5. Add `result_json` to `DispatchEventListResponse` (auto from schema)
6. Update `DispatchService.add_event()` to accept and store `result_json`

### Backend (Connector + Worker)
7. Hermes connector: pass through any `result` field from SSE `tool.completed` events
8. Dispatch worker `_execute_ai_call()`: capture result data from connector chunks and persist via add_event

### Frontend
9. Add `selectedEventDetail` ref to App.vue (the event being inspected)
10. Make tool bubbles clickable → set selectedEventDetail
11. Add event detail modal/panel component showing:
    - Event type, seq, timestamp
    - Tool name, function name
    - Status (success/error) with icon
    - Parameters (from function_args, parsed JSON when possible)
    - Result summary (from result_json, truncated)
    - Error details (from tool_error)
    - Duration
    - Raw event data (collapsed by default)
12. Truncation logic: text fields > 2000 chars show first 1500 + "... (click to expand)"
13. Field whitelist for sensitive data filtering (prevent raw API keys in display)
14. Close button to dismiss detail panel

### Verification
15. Docker build succeeds
16. End-to-end smoke: trigger skill_view call, verify detail panel works, refresh page, verify events persist

## Boundaries
- IN SCOPE: tool_call events in dispatch-based chat timeline
- IN SCOPE: skill_view, terminal, web_search, and all other tool events
- OUT OF SCOPE: legacy session events table (separate from dispatch)
- OUT OF SCOPE: non-dispatch chat flows
- OUT OF SCOPE: real-time streaming of large tool results (load on click)

## Success Criteria
1. All tool events in chat timeline are clickable
2. Clicking opens detail panel showing: tool name, args, status, result summary, error (if any)
3. skill_view events show: skill name, file_path, load success/failure, content preview
4. Page refresh preserves all events and detail panel state resets gracefully
5. No raw secrets/API keys exposed in detail panel
6. Text > 2000 chars is truncated with expand toggle
7. Docker build passes; end-to-end smoke test confirms skill_view detail

## Open Questions
- None. Requirements are clear from task description and discovery.

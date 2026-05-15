# Spec: AI Event Message Split Rendering (P1-对话页面)

## Objective

ShuJieTai chat page currently merges AI events into a single content card,
making it impossible for users to distinguish different AI events on a
timeline — thinking, tool calls, status changes, progress markers, output
fragments, and errors all blend into one undifferentiated stream.

Goal: render each distinct AI event as a separate item in the chat timeline,
preserving clear event boundaries while keeping same-assistant text streaming
merged as one bubble.

## Tech Stack

- Frontend: Vue 3 (Composition API), Vite
- Backend: FastAPI, Python 3.11+
- State: Vue composables (useDispatchTask, useWebSocket)
- Styling: CSS modules under frontend/src/styles/

## Current State (Discovered)

The `dispatchMessages` computed in `useDispatchTask.js` already correctly
separates several event categories:

| Event Type | Handler? | Behavior |
|---|---|---|
| `content_delta` | Yes | Merges by role + _groupKey + run_id |
| `tool_call` | Yes | Tracks via toolStates Map |
| `agent_thinking` | Yes | Merges by _groupKey + run_id |
| `error` | Yes | Single system bubble |
| `interrupted` | Yes | Single system bubble |
| `task.interrupted` | Yes | Separator system bubble |
| `progress` | NO | Silently dropped |
| `content_full` | NO | Silently dropped |
| `status` / `completed` | NO | Only handled via handleTaskStatus (state update, no visual) |
| `cancelled` | NO | Only handled via handleTaskStatus |
| `await_input` | NO | Not processed by dispatchMessages |

The existing merge logic is correct — the problem is missing event
handlers for several backend-emitted event types, and no visual
type/timestamp indicators on individual event items.

The backend (`dispatch_worker.py:_emit_event`) already tags events with
`run_id`, `seq`, `event_id`, `created_at` — backend data is sufficient.

## Approach

Add missing event type handlers to `dispatchMessages` computed.
Ensure every event type produces at least one visual item with stable ID.
Add CSS classes for event type badges/time indicators.
No backend changes needed (event structure is complete).

## Success Criteria

1. Tool calls appear as separate cards from assistant text in the chat timeline
2. Thinking/reasoning text appears in its own collapsible bubble (already works)
3. Progress events render as system-status items
4. content_full events render as a complete-message snapshot (or are shown as
   inline status)
5. Status terminal events (completed/cancelled/failed) produce visible
   system messages in the timeline
6. Same assistant text stream still merges into one bubble (not token-by-token)
7. Refresh / re-enter session preserves event split consistency
8. Docker build passes; smoke-verify with multi-event dispatch session

## Boundaries

- Always: use stable IDs from event_id or seq + event_type; keep content_delta
  merge logic unchanged
- Ask first: changes to backend event structure, WebSocket wire format
- Never: break the existing content_delta merge contract (role + run_id boundary)

## Open Questions

None — requirements are fully specified in the task board description.

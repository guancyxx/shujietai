# Spec: Dispatch single presentation layer for chat

Date: 2026-05-27
Status: draft

## Objective
Make dispatch events the only canonical presentation source for AI chat sessions. Completed, failed, cancelled, and resumed conversations must render from dispatch event history instead of falling back to coarse session timeline messages.

## Problem statement
Observed behavior:
1. A dispatch-backed session can initially render rich event history (tool calls, skill loads, thinking, user/assistant deltas).
2. After session switch, refresh, or completed-task restore, the frontend may fail to reattach a dispatch task.
3. When no active dispatch task is attached, `displayMessages` falls back to `timeline.messages`.
4. The session timeline only stores coarse user/assistant/system messages, so the UI collapses back into one full assistant paragraph and loses tool/skill/thinking visibility.

This creates two parallel chat presentation paths and makes the same conversation appear differently depending on restore success.

## Root cause
- Frontend `displayMessages` uses dispatch messages only when `dispatchTaskId` exists; otherwise it renders `timeline.messages`.
- Backend session storage persists only coarse message projections for dispatch replies, not the full event stream.
- Frontend dispatch restore still infers canonical task state from `external_session_id`, with no stable server-provided canonical dispatch task identifier on the session summary/detail payload.
- Restore failure silently clears dispatch state, which triggers the timeline fallback.

## Design
### 1) Chat body presentation must be dispatch-only for dispatch-backed sessions
- Add explicit session metadata indicating whether a session is dispatch-backed and which dispatch task is canonical for presentation.
- Frontend must not render `timeline.messages` as chat body when the selected session is dispatch-backed.
- If dispatch history is unavailable or restore fails, show an explicit empty/error placeholder instead of the coarse message timeline.

### 2) Backend session payloads expose canonical dispatch linkage
- `GET /api/v1/sessions` and `GET /api/v1/sessions/{id}` should include:
  - `canonical_dispatch_task_id`
  - `has_dispatch_history`
- The canonical task should prefer the latest dispatch task linked by `(platform, external_session_id)`.
- This removes restore-time guessing in the frontend.

### 3) Timeline API remains compatibility data, not body presentation source
- Keep `/api/v1/sessions/{id}/timeline` for cockpit/compatibility data and non-dispatch sessions.
- Do not remove coarse message persistence in this change.
- Explicitly treat session timeline as compatibility/index data, not canonical chat rendering for dispatch-backed sessions.

### 4) Frontend restore flow must become explicit
- `restoreActiveDispatchTask()` should first use `selectedSession.canonical_dispatch_task_id` when available.
- It should track restore state (`idle`, `loading`, `ready`, `missing`, `error`) so the UI can explain why dispatch history is absent.
- `displayMessages` should only return dispatch-derived messages for dispatch-backed sessions.

## Files
- `backend/app/schemas.py`
- `backend/app/services/dispatch_service.py`
- `backend/app/services/sqlalchemy_store.py`
- `backend/app/services/session_store.py`
- `frontend/src/stores/useSessionStore.js`
- `frontend/src/components/chat/ChatTimeline.vue`
- `docs/specs/2026-05-27-dispatch-single-presentation-layer.md`

## Acceptance criteria
1. A dispatch-backed completed session no longer falls back to coarse assistant full text in chat body.
2. Tool calls, skill_view events, and thinking events remain visible after refresh/session switch as long as dispatch history exists.
3. Session selection restores dispatch history via canonical task ID instead of only `external_session_id` inference.
4. If dispatch history is missing or restore fails, the chat shows an explicit placeholder/error instead of `timeline.messages`.
5. Non-dispatch sessions still render their normal timeline messages.
6. Frontend production build and backend image build both pass.

## Constraints
- No database migration in this change.
- No removal of compatibility timeline endpoints.
- Keep task-board and history-page entry points functioning with the new canonical dispatch linkage.

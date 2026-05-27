# Spec: Dispatch single presentation layer for AI conversations

## Objective
Make dispatch events the single presentation source for AI conversations in ShuJieTai chat UX.

This change fixes the user-visible inconsistency where:
- live AI conversations show fine-grained dispatch events;
- completed/restored conversations fall back to full assistant text;
- tool/skill/thinking events disappear after recovery;
- new blank-chat conversations still use the legacy synchronous Hermes chat endpoint.

## Problem statement
Current architecture mixes two different conversation representations:

1. Dispatch event timeline
- Source: `dispatch_tasks` + `dispatch_events`
- Preserves `content_delta`, `tool_call`, `agent_thinking`, `await_input`, `completed`, `error`
- Frontend rendering path: `useDispatchTask().dispatchMessages`

2. Legacy session timeline
- Source: `sessions` + `messages`
- Stores coarse user/assistant messages only
- Legacy creation path: `POST /api/v1/connectors/hermes/chat`
- Dispatch worker also writes full assistant text back into session store via `persist_message_to_session()`

This creates inconsistent UX and unclear architecture truth.

## Existing evidence
- `frontend/src/stores/useSessionStore.js`
  - `displayMessages` already prefers `dispatchMessages` when `dispatchTaskId` exists
  - `submitCreateConversation()` still creates conversations through `/api/v1/connectors/hermes/chat`
  - `restoreActiveDispatchTask()` can restore dispatch-backed sessions from `external_session_id`
- `frontend/src/stores/useTaskStore.js`
  - task-board start conversation already creates dispatch tasks
- `backend/app/api/routes_hermes.py`
  - legacy `/api/v1/connectors/hermes/chat` and `/chat/stream` still exist
- `backend/app/services/dispatch_worker.py`
  - emits fine-grained dispatch events
  - also writes assistant full text into session timeline via `_write_assistant_to_store()`
- `backend/app/services/dispatch_service.py`
  - `persist_message_to_session()` stores only coarse message rows, not event projections

## Design decision
### 1. Canonical presentation source for AI conversations
For AI conversations, the canonical presentation source is `dispatch_events`, not `sessions/messages`.

Interpretation:
- Chat reading/rendering must prefer dispatch event reconstruction whenever the selected conversation can be resolved to a dispatch task.
- Session timeline remains a compatibility/index/search layer, not the authoritative reading layer for AI execution traces.

### 2. New blank-chat conversations must use dispatch
`submitCreateConversation()` must stop calling `/api/v1/connectors/hermes/chat`.

Instead it must:
- generate an `external_session_id` for the new conversation;
- create a dispatch task through `/api/v1/dispatch`;
- create the minimal session shell through `/api/v1/events/ingest` so the session list remains populated;
- select the created session and restore dispatch history through the standard chat path.

This aligns blank chat with task-board conversations.

### 3. Session timeline is not the primary rendering truth for dispatch conversations
The frontend should continue to use `displayMessages` as the single UI binding, but the data-resolution rule becomes:
- if current conversation resolves to a dispatch task, render `dispatchMessages`;
- otherwise render legacy `timeline.messages`.

This means completed/restored dispatch conversations must keep resolving back to dispatch history.

### 4. Legacy Hermes chat endpoints remain temporarily for compatibility only
`/api/v1/connectors/hermes/chat` and `/chat/stream` are not removed in this slice.

But they are explicitly downgraded to compatibility endpoints and must no longer be used by the primary chat-page creation flow.

### 5. No schema migration in this slice
This slice does not redesign the persistence model or remove session-message writes from `dispatch_worker`.

Those writes may remain for:
- search/backward compatibility;
- existing timeline endpoints;
- old sessions without dispatch linkage.

However, they must no longer determine the main AI conversation presentation in chat UX.

## Implementation scope
### Frontend
1. Change `submitCreateConversation()` to create a dispatch task instead of calling legacy Hermes chat.
2. After dispatch creation, ingest a minimal session shell for the new `external_session_id`.
3. Refresh sessions, select the matched session, load session data, then call `restoreActiveDispatchTask()`.
4. Keep `displayMessages` as the single binding point.
5. Preserve existing resume/interrupt/terminal-follow-up behavior.

### Backend
No mandatory backend contract change in this slice.

The existing dispatch creation API already supports `external_session_id`, so frontend can migrate immediately.

## Files
- `frontend/src/stores/useSessionStore.js`
- optional follow-up docs:
  - `docs/adr/0004-dispatch-orchestration-layer.md`
  - this spec file itself

## Commands
Build frontend/backend through Docker from the canonical repo root:
- `docker compose build backend frontend`

Recreate app containers if needed:
- `docker stop shujietai-backend shujietai-frontend`
- `docker rm shujietai-backend shujietai-frontend`
- `docker compose create backend frontend`
- `docker compose start backend frontend`

Verify:
- `curl -s -o /tmp/shujietai_health.json -w '%{http_code}\n' http://localhost:18000/api/v1/health`
- `curl -s -o /tmp/shujietai_frontend.html -w '%{http_code}\n' http://localhost:15173/`
- `docker compose logs --tail=80 backend`
- `docker compose logs --tail=80 frontend`

## Project structure
- frontend chat source of truth:
  - `frontend/src/stores/useSessionStore.js`
  - `frontend/src/composables/useDispatchTask.js`
  - `frontend/src/components/chat/ChatTimeline.vue`
- backend compatibility/dispatch layers:
  - `backend/app/api/routes_hermes.py`
  - `backend/app/services/dispatch_worker.py`
  - `backend/app/services/dispatch_service.py`

## Code style
Follow existing Vue composition-store pattern and preserve current API client helpers (`fetchJson`, `postJson`).

Do not add new page-level orchestration outside the session store for this slice.

## Testing strategy
Primary verification is Docker-based build + local runtime smoke.

For this slice:
- frontend production build must pass;
- backend/frontend containers must come up cleanly;
- creating a new conversation should use dispatch path and still populate session list;
- restoring a completed dispatch conversation should keep event-level display instead of falling back to coarse assistant text.

## Boundaries
- Always:
  - keep AI conversation rendering dispatch-first;
  - keep changes inside the task worktree;
  - verify with Docker-based build/smoke.
- Ask first:
  - removing legacy endpoints entirely;
  - changing DB schema or migration;
  - redesigning session/timeline API contracts.
- Never:
  - reintroduce `/api/v1/connectors/hermes/chat` as the default new-conversation path;
  - treat session full-text assistant rows as the canonical AI execution trace.

## Success criteria
1. New blank-chat conversation creation no longer calls `/api/v1/connectors/hermes/chat`.
2. New blank-chat conversation creates a dispatch task with a stable `external_session_id`.
3. The new conversation still appears in the session list.
4. Selecting/restoring a dispatch-backed conversation renders dispatch event projection in chat.
5. Existing task-board dispatch flow remains working.
6. Docker build/smoke checks pass.

## Task breakdown
### Task 1: Convert blank-chat creation to dispatch
- Acceptance:
  - `submitCreateConversation()` creates dispatch task instead of legacy Hermes chat
  - new conversation path uses `external_session_id`
- Verify:
  - code inspection and frontend build
- Files:
  - `frontend/src/stores/useSessionStore.js`
- Scope: S

### Task 2: Preserve session-list visibility for new dispatch conversations
- Acceptance:
  - session shell is ingested for the newly created dispatch conversation
  - chat selection resolves to the created session after refresh
- Verify:
  - code inspection and local smoke through running stack
- Files:
  - `frontend/src/stores/useSessionStore.js`
- Scope: S

### Task 3: Record architecture decision in repo docs
- Acceptance:
  - repo contains spec for dispatch single presentation layer
  - decision is explicit: dispatch events are canonical presentation layer for AI chats
- Verify:
  - file exists in `docs/specs/`
- Files:
  - this spec file
- Scope: XS

## Risks and mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| New blank-chat path creates dispatch task but not visible session | High | ingest `session_started` event immediately after dispatch creation |
| Existing restore logic misses some `external_session_id` formats | Medium | keep current resolver logic unchanged in this slice |
| Legacy session timeline still contains full assistant text and confuses future developers | Medium | document clearly that it is compatibility storage, not canonical presentation |

## Open questions
1. In a later slice, should `dispatch_worker._write_assistant_to_store()` stop writing full assistant text entirely, or should it remain as compatibility/search projection?
2. Should we add a unified backend view endpoint such as `/api/v1/chat-sessions/{id}/view` so the frontend no longer has to resolve dispatch/session duality itself?

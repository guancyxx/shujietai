# Spec and Plan: Session card status and unread indicator

## Objective

Update the chat session list so ordinary users see useful state instead of internal identifiers. Session cards must hide visible session IDs, show the effective conversation status, and show a persistent unread indicator when non-selected conversations receive new events or messages.

## Scope

- Keep `session_id` and `external_session_id` as internal keys and API parameters.
- Remove visible ID text from session cards.
- Add effective status to every session card. Dispatch-backed sessions should use the linked dispatch task status when available. Legacy sessions should keep the session store status.
- Add persistent unread tracking based on `last_read_at` and latest activity timestamp.
- Mark a session read when it is selected/opened.
- Preserve responsive card density and avoid fixed width/height truncation.

## Existing context

- `GET /api/v1/sessions` is rendered directly in `frontend/src/App.vue`.
- Session list cards currently display `item.external_session_id` in `.conversation-task-subtitle`.
- Legacy sessions are in `sessions`; dispatch tasks are in `dispatch_tasks` and are linked through `external_session_id = dispatch_{task_id}`.
- Current session summaries expose `status`, `created_at`, and `updated_at`, but no read state or dispatch status.

## Design

### Backend

Add persistent read-state fields to `sessions`:

- `last_read_at`: nullable timestamp. Null means never explicitly opened/read.
- `last_activity_at`: non-null timestamp. Updated whenever a session event/message/task is ingested.

Expose summary fields:

- `effective_status`: dispatch task status when `external_session_id` links to `dispatch_tasks`, otherwise session status.
- `last_read_at`
- `last_activity_at`
- `unread_count`: 1 when `last_activity_at > last_read_at` and the session has been read before; otherwise 0. This keeps the indicator reliable without introducing message-level read receipts.

Add endpoint:

- `POST /api/v1/sessions/{session_id}/read` marks the session read by setting `last_read_at` to current time.

### Frontend

- Remove card subtitle that renders `external_session_id`.
- Render platform + effective status badges in the header/meta area.
- Render unread dot/count only for non-selected sessions with `unread_count > 0`.
- Call mark-read when selecting a conversation and after default selection during initial load.
- Keep local UI responsive by clearing unread state optimistically after mark-read.

## Verification strategy

- Backend unit/API tests cover unread persistence and dispatch status projection.
- Frontend production build via Docker.
- Docker backend/frontend image build.
- API smoke: create two sessions, mark one read, add a new event to the other, verify unread persists across a fresh `GET /api/v1/sessions`.
- Multi-session smoke: confirm selected/read session does not retain unread while a different session does.

## Task breakdown

1. Backend data model and migration
   - Add `last_read_at` and `last_activity_at` columns.
   - Backfill `last_activity_at` from `started_at`.
   - Keep SQLite auto-create compatibility.

2. Backend store/API behavior
   - Update summaries and detail schemas.
   - Update SQLAlchemy and in-memory stores.
   - Add mark-read endpoint.
   - Join/lookup dispatch status for dispatch-backed sessions.

3. Frontend session list behavior
   - Add status label/class helpers.
   - Remove visible ID text.
   - Add unread indicator and mark-read flow.

4. Tests and smoke verification
   - Add/adjust tests.
   - Run Docker-only verification and smoke calls.

## Acceptance criteria

- Session cards no longer show any visible ID/external session ID line.
- Every card displays an understandable status matching actual session or dispatch state.
- Non-current sessions show unread when new activity arrives.
- Opening a session clears its unread state persistently.
- Refreshing the page preserves read/unread state through backend data.
- Docker build passes and multi-session smoke succeeds.

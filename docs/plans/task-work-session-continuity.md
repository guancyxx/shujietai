# Implementation Plan: Task Board Work Session Continuity

## Overview
Implement a canonical work-session resolver for task-board conversations: when a user opens a task-board item's "会话" from the Kanban page, the system looks up the current active dispatch, latest completed dispatch, or linked session record, then restores or creates the appropriate work context instead of unconditionally creating a new dispatch task.

## Architecture Decisions
- **Use existing `task_board_item_id` in `dispatch_tasks`** as the primary lookup key instead of parsing `external_session_id`.
- **Adopt `task_board_<task_id>` as stable external session id** for new task-board dispatches so conversation identity stays constant across multiple rounds of execution.
- **Add `GET /api/v1/task-board/{task_id}/work-session`** on the existing task-board or dispatch route set; prefer dispatch routes because the lookup is dispatch-centric.
- **Fall back to viewing history** when only terminal dispatches exist (until persistent session timeline merge is added later).

## Task List

### Phase 1: Backend Resolver

- [ ] Task 1: Add `get_latest_task_for_task_board_item` service method + resolver
  - Acceptance:
    - `DispatchService.get_latest_task_for_task_board_item(task_board_item_id)` returns most recent dispatch (any status), ordered by `created_at.desc()`.
    - New method `DispatchService.resolve_work_session(task_board_item_id)` uses existing `get_active_task_for_task_board_item` then the new `get_latest_task_for_task_board_item` to decide `recommended_action`.
  - Verify: targeted pytest via Docker.
  - Files:
    - `backend/app/services/dispatch_service.py`
    - `backend/tests/test_task_work_session.py`

- [ ] Task 2: Add `WorkSessionResponse` schema and `GET /api/v1/dispatch/task-board/{task_id}/work-session` endpoint
  - Acceptance:
    - Endpoint returns `WorkSessionResponse` with `recommended_action`, `active_dispatch`, `latest_dispatch`, and `linked_session_id`.
    - Handles empty task_board_item_id gracefully (404 or create_new).
  - Verify: curl smoke once backend builds.
  - Files:
    - `backend/app/schemas.py`
    - `backend/app/services/dispatch_service.py`
    - `backend/app/api/routes_dispatch.py`

### Phase 3: Frontend Integration

- [ ] Task 3: Refactor `startConversationFromTask` to use work-session resolver
  - Acceptance:
    - Calls `GET /api/v1/dispatch/task-board/<task_id>/work-session` before creating dispatch.
    - On `resume`: selects linked session, calls `restoreActiveDispatchTask`.
    - On `view_history`: selects linked session, calls `restoreActiveDispatchTask`.
    - On `create_new`: creates a dispatch task with `external_session_id: task_board_<taskId>` and `task_board_item_id: task.id`, then creates session + progress messages as before.
    - Does not clear `startingConversationFromTask` flag until all async work completes.
  - Verify: frontend build + Docker compose build frontend.
  - Files:
    - `frontend/src/composables/useDispatchTask.js`
    - `frontend/src/App.vue`

- [ ] Task 4: Extend `restoreActiveDispatchTask` to resolve `task_board_` prefix when `dispatch_` prefix fails
  - Acceptance:
    - When `external_session_id` starts with `task_board_`, extracts `task_board_item_id` segment, calls `resolve_work_session`, and loads the recommended dispatch task.
    - Existing `dispatch_` fallback behavior unchanged.
    - Refactored `getDispatchTaskIdFromExternalSessionId` or new helper handles both prefixes.
  - Verify: frontend build.
  - Files:
    - `frontend/src/App.vue`

### Phase 4: Verification & Ship

- [ ] Task 5: Docker build, test, and PR creation
  - Acceptance:
    - Backend tests pass via Docker.
    - Backend image builds via `docker compose build backend`.
    - Frontend builds via `docker run npm run build`.
    - PR with spec, plan, and all code + test changes pushed.
  - Verify: CI/CR check on PR.
  - Files: PR metadata.

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Legacy `dispatch_` session restore breaks | Medium | Preserve existing `getDispatchTaskIdFromExternalSessionId` and add `task_board_` as new branch, never removing the old path. |
| Missing session record for old tasks | Low | `view_history` action only needs a valid dispatch task; session linking is optional. |
| `task_board_<id>` external session id collides with legacy session records | Low | Session records have `platform + external_session_id` unique constraint; new ids won't conflict with `dispatch_` prefixes. |

## Open Questions
None — resolved during discovery.

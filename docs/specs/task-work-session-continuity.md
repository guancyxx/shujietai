# Spec: Task Board Work Session Continuity

## Objective
Ensure that opening a ShuJieTai task-board conversation always restores the canonical work timeline for that task instead of starting duplicate dispatch executions. The user-facing "会话" action means "open this task's work context" by default, not "start a fresh run every time".

Success means:
- Repeatedly clicking a task-board "会话" button does not create duplicate active dispatch tasks.
- Interrupted or refreshed sessions can resume the same live dispatch timeline.
- Completed historical task sessions open their execution history instead of showing only a stale submit placeholder.
- A new execution is created only when no prior work session exists, or a future explicit restart action is added.

## Tech Stack
- Backend: FastAPI, Pydantic, SQLAlchemy, PostgreSQL in Docker Compose.
- Frontend: Vue 3 Composition API, Vite, Dockerized Node build.
- Runtime: Docker Compose stack rooted at repository `docker-compose.yml`.

## Commands
All project-runtime commands must use Docker or Docker Compose.

Backend targeted tests:
```bash
docker run --rm -v "$PWD/backend:/app" -w /app -e PYTHONPATH=/app python:3.11-slim sh -lc 'pip install -q -r requirements.txt && pytest tests/test_task_work_session.py -q'
```

Backend image build:
```bash
docker compose build backend
```

Frontend production build:
```bash
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/frontend:/app" -w /app node:20-alpine sh -lc 'npm ci && npm run build'
```

Optional live API smoke, only against already-running local stack:
```bash
curl -s http://localhost:18000/api/v1/health
curl -s http://localhost:18000/api/v1/task-board/<task_id>/work-session
```

## Project Structure
- `backend/app/schemas.py`: API response models for dispatch/work-session contracts.
- `backend/app/services/dispatch_service.py`: dispatch lookup and work-session resolution logic.
- `backend/app/api/routes_task_board.py` or existing task-board route area: task-level work-session endpoint.
- `frontend/src/App.vue`: task-board "会话" action orchestration and restore flow.
- `frontend/src/composables/useDispatchTask.js`: dispatch task creation and active-task state utilities.
- `backend/tests/`: targeted backend tests for resolver behavior.
- `docs/plans/`: durable project implementation plan.

## Code Style
Prefer small named helpers and guard clauses over embedding resolver logic directly in large handlers.

Example style:
```python
def get_latest_task_for_task_board_item(self, task_board_item_id: str) -> DispatchTaskItem | None:
    if not task_board_item_id.strip():
        return None
    with self._session_factory() as db:
        row = db.execute(...).scalar_one_or_none()
        return _entity_to_item(row) if row is not None else None
```

Frontend helpers should separate intent:
```javascript
async function openResolvedTaskWorkSession(task, resolved) {
  if (resolved.recommended_action === 'create_new') {
    await createTaskWorkDispatch(task)
    return
  }
  await selectResolvedWorkSession(resolved)
}
```

Comments must be English only. User-facing Chinese strings in Vue templates are allowed because this project already uses direct Chinese UI text.

## Testing Strategy
- Unit/API-level backend tests for resolver decisions:
  - active dispatch returns `resume`.
  - latest terminal dispatch returns `view_history`.
  - no dispatch/session returns `create_new`.
  - stable `task_board_<task_id>` session is selected when present.
- Frontend build verifies Vue syntax and bundling.
- Backend Docker build verifies imports and route registration.
- Optional smoke checks verify response shape against a running stack without restarting services.

## Boundaries
- Always:
  - Use a stable task-level external session id: `task_board_<task_id>` for task-board conversations.
  - Treat `task_board_item_id` as the canonical work-thread identity.
  - Preserve existing `dispatch_<task_id>` compatibility for old sessions.
  - Keep specs/plans committed with implementation.
- Ask first:
  - Database migrations or data backfills beyond optional compatibility lookups.
  - Adding new dependencies.
  - Restarting local/remote services.
- Never:
  - Create a new dispatch run from task-board open when an active run already exists.
  - Destroy or rewrite existing session/dispatch history.
  - Remove support for legacy `dispatch_` external session ids.
  - Use host Python/npm runtimes for verification.

## Success Criteria
1. `GET /api/v1/task-board/{task_id}/work-session` returns a deterministic recommendation with active/latest dispatch and linked session context.
2. `startConversationFromTask()` calls the resolver before creating dispatch.
3. Existing active dispatch is restored and subscribed instead of creating a new dispatch.
4. Existing terminal dispatch history opens in the same visible chat context.
5. New task-board dispatch creation uses `externalSessionId: task_board_<task_id>`.
6. Legacy `dispatch_<dispatch_task_id>` restore still works.
7. Targeted backend tests pass via Docker, frontend build passes via Docker, and backend image builds.

## Open Questions
None for the current scope. A future explicit "重新执行" user action can create a new dispatch intentionally, but it is out of scope for this change.

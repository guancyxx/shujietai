# Spec: Task Board Card Interaction Fix

## Objective
Fix three broken task-board card interactions in ShuJieTai:
1. The Detail button must open a modal showing the selected task’s details.
2. The Session button must start or restore the task’s work session reliably.
3. The inline priority dropdown on each card must persist the new priority value.

This change is a bug fix, not a redesign. It should preserve the current task-board layout, task tree rendering, archive flow, and existing task-board data model.

## Tech Stack
- Frontend: Vue 3 Composition API, Vite
- State: Pinia stores / composables already used by the task board
- Backend: FastAPI task-board endpoints already in place
- Runtime and verification: Docker Compose

## Commands
Use Docker or Docker Compose for all project-runtime verification.

Frontend build:
```bash
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/frontend:/app" -w /app node:20-alpine sh -lc 'npm ci && npm run build'
```

Backend image build:
```bash
docker compose build backend
```

Optional local smoke checks against the running stack:
```bash
curl -s http://localhost:18000/api/v1/task-board
curl -s http://localhost:18000/api/v1/dispatch/task-board/<task_id>/work-session
```

## Project Structure
- `frontend/src/views/TaskBoardPage.vue`: task-board card actions and detail modal UI.
- `frontend/src/stores/useTaskStore.js`: task-board actions, detail/session handlers, quick priority update logic.
- `frontend/src/stores/useSessionStore.js`: session selection and dispatch restore flow.
- `frontend/src/styles/task-board.css`: modal and card styling if any interaction layer needs visual adjustment.
- `docs/specs/`: durable spec for this fix.

## Code Style
- Keep handlers small and single-purpose.
- Prefer guard clauses over nested conditionals.
- Use the existing task store and session store APIs instead of adding new ad hoc state.
- Task-board store actions must not call `useRouter()` inside Pinia actions; navigation should use the app router singleton or be delegated from component setup so the Session action never depends on component injection context.
- Keep comments in English only.

Example style:
```javascript
function openTaskBoardDetailModal(item) {
  if (!item?.id) return
  taskBoardDetailItem.value = item
}
```

## Testing Strategy
1. Verify the task-board page still builds with Vite.
2. Verify the backend image still builds.
3. Smoke the task-board API and the work-session resolver endpoint.
4. Confirm the three card actions work from the UI behavior contract:
   - Detail opens a modal with the selected task.
   - Session resolves to an existing work session or creates a new one when appropriate.
   - Priority changes are sent with the correct numeric value and persisted.

## Boundaries
- Always:
  - Preserve existing task-board layout and card tree behavior.
  - Keep task-board actions wired through the existing store layer.
  - Validate priority updates as integers 1-4.
  - Keep work-session behavior compatible with existing `task_board_<task_id>` and legacy `dispatch_<id>` flows.
- Ask first:
  - Database schema changes.
  - New dependencies.
  - Any change to the task-board work-session contract beyond this fix.
- Never:
  - Rewrite the task board UI structure as part of this bug fix.
  - Break existing archive/edit behavior.
  - Remove legacy session compatibility.

## Success Criteria
1. Clicking Detail on any task card opens a modal populated with that task’s fields.
2. Clicking Session on any task card triggers the work-session resolution flow and no longer appears unresponsive.
3. Changing priority from the card dropdown sends the correct payload and updates the displayed priority after refresh.
4. No unrelated task-board behavior regresses.
5. Frontend build succeeds and backend image build succeeds.

## Open Questions
- None. The reported issues are specific enough to implement directly once the spec is approved.

# Task execution queue, task tree, and chat skill visibility

## Objective

Implement five related ShuJieTai improvements as one coherent product slice:

1. Add a task-board status named `pending_execution` displayed as "待执行".
2. Automatically start AI conversations for tasks moved to `pending_execution`.
3. Render task-board parent/child relationships as collapsible trees without changing the existing kanban grid layout.
4. Show the current chat session's linked task summary in the conversation status bar.
5. Surface loaded Hermes skills in both the chat timeline/tool events and the conversation status bar, with click-through access to skill content.

## Current state

- Task-board statuses are limited to `draft`, `in_progress`, `blocked`, `completed`, and `cancelled`.
- `frontend/src/App.vue` currently groups task-board rows by project and priority. Priority is acting as a collapsible row level.
- Task-board entities already include `parent_task_id`, but the frontend renders all tasks as top-level cards.
- Dispatch tasks already carry `task_board_item_id` and `external_session_id`.
- `GET /api/v1/skills/{skill_name:path}/content` already returns raw SKILL.md content.
- Hermes connector maps `tool.started` to `tool_start`, but only preserves `tool` and `preview`; raw event fields are not retained.

## Source notes: Hermes skill visibility

Hermes Agent exposes skill loading through the `skill_view` tool and has session/tool-call observability through its API Server runs stream. The local ShuJieTai connector currently consumes `/v1/runs/{run_id}/events` SSE and handles events including `tool.started`, `tool.completed`, `message.delta`, and `run.completed`.

Implementation must preserve the raw Hermes SSE event payload where possible so ShuJieTai can display concrete tool metadata instead of generic tool labels. For `skill_view`, extract skill name from the most reliable source in this order:

1. Parsed arguments object, if provided by Hermes.
2. JSON decoded preview text, if preview is a JSON string.
3. Regex fallback from preview text, supporting `name='skill'`, `name="skill"`, and JSON-like `"name":"skill"`.
4. Raw tool/function name only, if no argument data exists.

If Hermes does not emit enough information for an event, preserve `raw_event` and render a clear unknown-skill fallback rather than inventing a name.

## Functional requirements

### 1. `pending_execution` status

- Backend schemas accept `pending_execution` as a valid `TaskBoardStatus`.
- Frontend kanban includes a "待执行" column.
- Moving a task to `pending_execution` does not require the user to manually start a chat session.
- A background worker scans pending-execution tasks and starts dispatch/session creation idempotently.
- A task with an existing non-terminal dispatch task must not start a duplicate dispatch.
- Successful auto-start transitions the task to `in_progress`.
- Failure leaves the task observable and retryable; error details should be recorded in task/dispatch events where feasible.

### 2. Task tree rendering

- Parent/child relationship is based on `parent_task_id`.
- Only root tasks (`parent_task_id == null`) are placed in top-level kanban cells.
- Child tasks render inside their parent card when expanded.
- Existing project row and status column layout remains intact.
- Priority remains a badge and sort key only. It must not create a collapsible row level.
- Sorting order inside a sibling group: priority asc, then updated_at desc, then name asc.

### 3. Chat status task summary

- The status bar resolves the linked task from active dispatch `task_board_item_id`, session payload `task_board_item_id`, or dispatch history metadata.
- Show task name, status, priority, and project name if available.
- Switching sessions clears stale task data and loads the new linked task.
- Clicking the task summary opens the task-board view and highlights or selects the linked task when feasible.

### 4. `skill_view` event visibility

- Hermes connector retains tool name, preview, parsed arguments, and raw event payload for tool start/completion chunks.
- Dispatch worker persists normalized tool-call payload fields:
  - `function_name`
  - `tool_name`
  - `function_args` or `arguments`
  - `skill_name` when function/tool is `skill_view`
  - `skill_file_path` when present
- Frontend timeline renders skill_view events as concrete text such as `读取技能：shujietai-development`.

### 5. Loaded skills status bar and content lookup

- Loaded skills are derived from current session/dispatch events, not manually maintained.
- Status bar displays de-duplicated skill chips in first-seen order.
- Clicking a chip calls the existing skill content endpoint and opens a readable detail panel.
- Loading, not found, and error states are handled without breaking chat flow.

## Architecture decisions

- Use `pending_execution` as the persisted canonical status value; use "待执行" only as UI label.
- Add the auto-starter as an in-process asyncio loop in the backend lifespan. This matches the current single-service MVP and avoids introducing an external scheduler yet.
- Keep background task creation idempotent by checking dispatch tasks linked to the task-board item before creating a new one.
- Keep task tree rendering frontend-derived for now because backend already returns flat tasks with parent IDs.
- Preserve raw Hermes tool events at the connector boundary. Normalization should be additive; do not throw away original metadata.
- Reuse the existing skill content endpoint instead of adding another filesystem scan path.

## Implementation plan

### Task 1: Status foundation and auto-start worker

Files likely touched:
- `backend/app/schemas.py`
- `backend/app/services/session_store.py`
- `backend/app/services/sqlalchemy_store.py`
- `backend/app/services/dispatch_service.py`
- `backend/app/main.py`
- backend tests

Acceptance criteria:
- API accepts and returns `pending_execution`.
- Background worker creates exactly one dispatch for each pending task and transitions it to `in_progress`.
- Duplicate scans are idempotent.

### Task 2: Task-board tree UI

Files likely touched:
- `frontend/src/App.vue`
- `frontend/src/style.css`

Acceptance criteria:
- Top-level cells render only root tasks.
- Parent cards show child count and expand/collapse controls.
- Priority remains badge/sort only.

### Task 3: Chat status task summary

Files likely touched:
- `frontend/src/App.vue`
- possibly backend route/helper for task lookup if list cache is insufficient

Acceptance criteria:
- Task-linked sessions display the correct task summary.
- Switching sessions clears stale task summary.
- Clicking summary navigates to task board and highlights/selects task.

### Task 4: Hermes skill_view event normalization

Files likely touched:
- `backend/app/connectors/hermes_connector.py`
- `backend/app/services/dispatch_worker.py`
- backend tests

Acceptance criteria:
- Tool start/completion events preserve raw metadata.
- `skill_view` events include normalized `skill_name`.
- Dispatch events API exposes the normalized payload.

### Task 5: Loaded skills status bar and content panel

Files likely touched:
- `frontend/src/App.vue`
- `frontend/src/style.css`

Acceptance criteria:
- Status bar displays loaded skill chips derived from events.
- Clicking a chip fetches and displays skill content via existing endpoint.
- Error/loading states are visible and non-blocking.

## Verification plan

- Backend tests for status acceptance, auto-start idempotency, and skill extraction helpers.
- Docker Compose build for backend and frontend.
- Frontend production build in Docker Node container.
- API smoke:
  - create/update task with `pending_execution`.
  - verify auto-start creates dispatch/session and transitions to `in_progress`.
  - create synthetic skill_view dispatch event and verify frontend/backend payload shape.
- Health checks:
  - `GET /api/v1/health`
  - frontend HTTP 200.

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Auto-start duplicates dispatch tasks | Duplicate AI runs | Check existing linked non-terminal and recent dispatch tasks before create |
| Hermes SSE event shape differs by version | Missing skill names | Preserve raw events and implement robust parser fallbacks |
| App.vue grows further | Maintainability debt | Keep helper functions small and mark extraction candidates for later component split |
| Skill content path traversal | Security | Existing endpoint must keep path construction under known skills directories only |

## Open questions resolved by assumption

- The new status value will be `pending_execution`.
- Auto-start worker runs inside the backend process for MVP.
- Priority grouping will be removed from the visual folding model and retained only for sorting/badges.

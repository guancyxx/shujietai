# Task Lifecycle Management

**Status:** draft
**Created:** 2026-05-14
**Author:** Hermes Agent
**PR:** TBD

## Objective

Strengthen ShuJieTai task lifecycle by replacing destructive deletion with
soft archive, ensuring running dispatch tasks are cancelled on archive,
preventing duplicate dispatch execution, and enforcing a clean terminal-state
model through periodic cleanup.

## Motivation

### Problem 1: Delete is destructive without cancellation
`DELETE /api/v1/task-board/{task_id}` removes the `TaskBoardEntity` row but
never interacts with the dispatch layer. If the task has a running
`DispatchTaskEntity` (status `running`/`queued`/`awaiting_input`), the
asyncio worker continues executing unseen, wasting resources.

### Problem 2: No duplicate execution guard
`start_task()` in `DispatchWorkerPool` silently returns if `task.id` is
already in `_workers`, but the same task_board_item can get a *new* dispatch
task created via a second `POST /api/v1/dispatch` while the first is still
running. The `resolve_work_session()` endpoint exists but is not enforced —
callers can bypass it.

### Problem 3: Orphan cancelled/disconnected tasks accumulate
Cancelled dispatch tasks stay in the database forever with status
`cancelled`. The task_board_item stays in `cancelled` state. There is no
healing mechanism. Only two terminal states should exist long-term:
- **completed** — task achieved its goal
- **blocked** — task needs user clarification (human input required)

### Problem 3b: Cleanup overrides explicit user recovery
The cleanup loop must be idempotent and must not override a user's later
status correction. If a cancelled dispatch already moved a task-board item
to `blocked`, and a user moves that item back to `draft`, subsequent cleanup
runs must treat that manual status change as the newer source of truth.
Historical cancelled dispatch rows must not push the item back into
`blocked`.

### Problem 4: UI uses × button suggesting deletion
The red `×` button for task-board cards implies permanent deletion. Users
already have `archive` for completed/cancelled tasks. All removal should be
archive (reversible, audit-friendly), not delete (destructive).

## Design

### New component: TaskLifecycleService

A single coordination service that owns cross-cutting task lifecycle rules.
It composes (not replaces) `DispatchService` and `DispatchWorkerPool`.

```
┌─────────────────────────────────────┐
│        TaskLifecycleService         │
│                                     │
│  archive_task(task_board_item_id)   │
│    ├─ find active dispatch          │
│    ├─ cancel asyncio.Task           │
│    ├─ transition dispatch→cancelled │
│    └─ archive task_board_item       │
│                                     │
│  start_task_safe(task, item_id)     │
│    ├─ check duplicate               │
│    ├─ wait if existing running      │
│    └─ start or skip                 │
│                                     │
│  cleanup_cancelled_tasks()          │
│    ├─ list cancelled dispatch tasks │
│    ├─ verify cancellation complete  │
│    └─ reconcile task_board status   │
│                                     │
└──────────┬──────────┬───────────────┘
           │          │
   DispatchService  DispatchWorkerPool
```

### API Changes

| Method | Path | Change |
|--------|------|--------|
| DELETE | `/api/v1/task-board/{id}` | **Removed**. Replace with archive. |
| PATCH | `/api/v1/task-board/{id}/archive` | **Extended**. Now allows any status, cancels dispatch. |
| GET | `/api/v1/task-board/archived` | Unchanged. |
| POST | `/api/v1/dispatch` | **Hardened**. Enforce dedup via lifecycle service before creating. |
| — | (internal) | `cleanup_cancelled_tasks` runs as background loop in lifespan. |

### Backend Files

| File | Change |
|------|--------|
| `backend/app/services/task_lifecycle.py` | **New.** TaskLifecycleService class. |
| `backend/app/api/routes_dispatch.py` | Wire lifecycle into create/resume. |
| `backend/app/main.py` | Mount lifecycle service; add cleanup loop; remove DELETE route; extend archive route. |
| `backend/app/db/models.py` | No change (no FK added — keep loose coupling). |

### Frontend Files

| File | Change |
|------|--------|
| `frontend/src/App.vue` | Replace `deleteTaskBoardItem()` with `archiveTaskBoardItem()` for all states. Change × button to archive icon. Update confirm dialog text. |
| `frontend/src/styles/base.css` | Adjust `.card-delete-btn` or add `.card-archive-btn`. |

### State Machine — Terminal States Only

```
           ┌──────────┐
           │  draft   │
           └────┬─────┘
                │
    ┌───────────┼───────────┐
    ▼           ▼           ▼
┌────────┐ ┌────────┐ ┌──────────┐
│in_prog…│ │pending_│ │ cancelled │──→ archive (immediate)
│        │ │execution│ │          │
└───┬────┘ └───┬────┘ └──────────┘
    │          │
    ▼          ▼
   ╔══════════════╗   ╔══════════════╗
   ║  completed   ║   ║   blocked    ║
   ║  (terminal)  ║   ║  (terminal)  ║
   ╚══════════════╝   ╚══════════════╝
```

All other statuses (`cancelled`, `aborted`) are transient — they should
resolve to either completed (retried successfully) or blocked (user
clarification needed). The cleanup loop enforces this.

## Implementation Tasks

### T1: Create TaskLifecycleService
- New file: `backend/app/services/task_lifecycle.py`
- Class with constructor taking `dispatch_service`, `worker_pool`, `session_factory`
- Methods:
  - `archive_task(task_board_item_id: str) -> bool`
  - `start_task_safe(task: DispatchTaskItem, task_board_item_id: str | None) -> bool`
  - `cleanup_cancelled_tasks() -> int`

### T2: Implement archive_task with cascade cancel
- Lookup active dispatch via `dispatch_service.get_active_task_for_task_board_item()`
- If found: `worker_pool.cancel_task(dispatch_task_id)`, then `dispatch_service.cancel_task()`
- Set `TaskBoardEntity.archived = True` and `archived_at = now()`
- Wrap in transaction

### T3: Implement start_task_safe with dedup
- If `task_board_item_id` is provided, check for existing active dispatch
- If one exists and is running: do NOT create duplicate; return/keep the active task
- If one exists and is terminal: allow new creation
- Call `worker_pool.start_task()` only when safe

### T4: Implement cleanup_cancelled_tasks background loop
- Query `dispatch_tasks WHERE status = 'cancelled'`
- For each: only reconcile when the linked task_board_item is still `cancelled`
- Never override later user status changes such as `blocked` -> `draft`
- Log counts; do not auto-retry (user decision required)
- Run every 60s in FastAPI lifespan as asyncio background task

### T5: Update backend routes
- Remove `DELETE /api/v1/task-board/{task_id}` route
- Extend `PATCH /api/v1/task-board/{task_id}/archive` to accept all statuses
- Wire archive route to `TaskLifecycleService.archive_task()`
- Wire dispatch create route through `start_task_safe()`

### T6: Update frontend
- Remove `deleteTaskBoardItem()` function
- Extend `archiveTaskBoardItem()` to work for all statuses
- Replace `×` button with archive icon (`🗄️` or SVG)
- Update confirm dialog: "归档任务"{name}"？进行中的任务将被取消。"
- Remove `deletingTaskBoardItemId` ref, reuse `archivingTaskId`

### T7: Wire lifecycle service in main.py lifespan
- Create `TaskLifecycleService` singleton on `app.state`
- Start `cleanup_cancelled_tasks` as `asyncio.create_task()` in lifespan startup
- Cancel on shutdown

## Boundaries

- No new database migrations needed (all fields exist)
- No FK constraint changes (keep loose coupling between task_board and dispatch)
- Cleanup loop is best-effort; does not guarantee exactly-once semantics
- `start_task_safe` is advisory — direct API callers can still bypass it

## Success Criteria

1. Clicking archive on a running task cancels its dispatch worker within 1 second
2. No duplicate dispatch tasks can be created for the same task_board_item while one is active
3. Cancelled dispatch tasks are logged and tracked by the cleanup loop
4. Cleanup is idempotent: after a user moves a previously blocked item back to draft, old cancelled dispatch rows do not block it again
5. No `DELETE /api/v1/task-board/{id}` endpoint remains
6. Frontend shows archive icon instead of × for all task states
7. Archive confirm dialog reflects cancellation warning when task is in progress

## Open Questions

- Should archive of `in_progress` task also close the active WebSocket
  connection? (Current: cancel propagates via WS `cancelled` event, frontend
  already handles this in `useDispatchTask`.)
- Should `pending_execution` tasks auto-retry after cleanup? (Current: no,
  user must manually restart.)

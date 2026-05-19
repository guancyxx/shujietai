# Task Board Priority Sorting

## Background

The task board matrix groups cards by project and status. Users expect cards within every project/status cell to be ordered by task priority from P0 to P3.

Current frontend rendering uses `frontend/src/stores/useTaskStore.js`. A helper service already exists at `frontend/src/services/taskBoardTree.js`, but the active store has an inline `buildTaskTree()` implementation that preserves API order and does not sort sibling cards.

## Requirement

For every project row in the task board, task cards must be displayed by priority in this order:

1. P0
2. P1
3. P2
4. P3

The rule applies to:

- Root task cards inside each project/status column.
- Child task cards under a parent task.
- Grandchild task cards under a child task.

## Priority model

The persisted priority values are numeric:

- `1` = P0
- `2` = P1
- `3` = P2
- `4` = P3

Invalid or missing priority values should fall back to P2 (`3`) so unexpected data does not break rendering.

## Tie-breakers

When two sibling tasks have the same priority, keep a deterministic secondary order:

1. Newer `updated_at` first.
2. Task name ascending.

This keeps the board stable while still prioritizing urgent tasks.

## Implementation plan

- Make the active Pinia task store use the shared task tree helpers from `frontend/src/services/taskBoardTree.js`.
- Remove duplicate inline tree-building logic from the store.
- Keep the task-board matrix project sorting unchanged.
- Verify with Docker-based frontend build.

## Acceptance checks

- Frontend Docker build succeeds.
- The running frontend and backend endpoints return HTTP 200 after rebuild/recreate.
- No unrelated untracked files from the primary checkout are included in this change.

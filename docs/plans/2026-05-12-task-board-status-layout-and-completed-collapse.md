# Task Board Status Layout and Completed Column Collapse

## Goal

Fix the task-board matrix layout after adding the pending-execution status, keep status columns in the intended workflow order, and allow users to collapse the completed column to reduce horizontal clutter.

## Scope

- Keep the task-board status order consistent across selects and the matrix board: draft, pending_execution, in_progress, blocked, cancelled, completed.
- Update the Kanban matrix grid so all six status columns fit in the same row instead of the last status wrapping to a second row.
- Keep the task-board page itself full width across viewport breakpoints; it must not inherit the two-column chat `.main-grid` layout.
- Add a column-collapse control for the completed status column.
- When completed is collapsed, preserve the column position and show a compact per-project count instead of full cards.
- Keep drag/drop targets for visible columns unchanged.

## Non-goals

- No backend schema or API change.
- No changes to task-board persistence, dispatch writeback, or status transition rules.
- No browser-based verification required for this UI-only change; Docker build is sufficient.

## Design notes

- Use one source of truth for status order: `KANBAN_STATUSES`.
- Derive the matrix grid template from the same status array and collapsed-column state instead of hard-coding `repeat(5, ...)`.
- Override inherited `.main-grid` behavior at the page-specific `.task-board-grid` level and force the board panel to span `grid-column: 1 / -1`; this prevents future generic breakpoint rules from shrinking the board to the first chat-style column.
- Limit column collapse to `completed` for now because this is the noisy terminal bucket requested by the user.
- Keep the collapsed column keyboard-accessible with a real button in the header.

## Implementation tasks

1. Reorder status options and `KANBAN_STATUSES` so cancelled appears before completed.
2. Add collapsed-status state and a `kanbanGridTemplate` computed value.
3. Apply the computed grid template to matrix header and row grids.
4. Add completed-header collapse button and compact collapsed-cell rendering.
5. Update CSS for six-column layout, collapsed columns, full-width page containment, and responsive widths.
6. Run Docker-based frontend build and inspect git diff.

## Verification plan

- `docker compose build frontend`
- Disposable Docker Node frontend build if needed: `docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/frontend:/app" -w /app node:20-alpine sh -lc 'npm ci && npm run build'`
- Confirm no backend/API files changed.
- Confirm `.task-board-grid` keeps a single full-width column and `.task-board-panel` spans `1 / -1` so generic `.main-grid` breakpoints cannot squeeze the board.
- Confirm the diff contains no hard-coded `repeat(5, ...)` matrix template for the six-status board.

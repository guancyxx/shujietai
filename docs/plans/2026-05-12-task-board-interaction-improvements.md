# Task Board Interaction Improvements

## Goal

Improve daily task-board operations so a user can inspect task details quickly, update status by dragging cards between status columns, and adjust priority directly from a task card without opening the edit form.

## Scope

- Add a task detail modal from each task card.
- Render task descriptions as sanitized Markdown in the detail modal.
- Keep edit/create payload contracts unchanged and only use existing `PATCH /api/v1/task-board/{task_id}` for status and priority updates.
- Make the task description textarea in the edit dialog larger for long task handoff content.
- Add HTML5 drag/drop support on the matrix status cells to change task status.
- Replace the static task-card priority badge with a compact select control that updates priority immediately.

## Non-goals

- No backend schema change.
- No new drag/drop dependency.
- No browser verification requirement for this UI-only change; Docker build and service health verification are sufficient.

## Design notes

- Drag/drop must preserve project and priority grouping while changing only the task status.
- Priority quick change must be disabled while another quick update for the same task is pending.
- Markdown rendering must use the existing `marked` plus `DOMPurify` pipeline already used by chat messages.
- Task cards should keep their current compact layout; detail modal is the full information surface.

## Verification plan

- Build frontend through Docker or Docker Compose.
- If running from the worktree, verify whether fixed container names conflict with the primary checkout before recreating containers.
- Check the frontend endpoint returns HTTP 200.
- Check the task-board API endpoint returns HTTP 200.
- Inspect git diff for unexpected backend/API changes.

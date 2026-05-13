# Task Board Blocked/Cancelled Reason Spec

## Goal
Enforce a ShuJieTai project rule: when a task enters `blocked` or `cancelled`, a human-readable reason must be recorded and visible both in task board context and in the linked conversation status area.

## Scope
- Backend task-board schema, persistence, API validation
- Frontend task create/edit/detail/card rendering
- Frontend quick status updates (including drag/drop)
- Conversation status bar linked-task summary

## Functional Requirements
1. Task board items gain a new optional text field: `status_reason`.
2. `status_reason` is required when `status` is `blocked` or `cancelled`.
3. `status_reason` must be cleared automatically when status changes to any non-blocked/non-cancelled state.
4. Create/edit forms must show a multiline reason field only when status is `blocked` or `cancelled`.
5. Task cards should display a short reason summary for blocked/cancelled tasks.
6. Task detail modal should display the full reason.
7. Conversation linked-task status chip/summary should include the reason for blocked/cancelled tasks.
8. Quick status updates must not silently bypass reason capture:
   - If changing to `blocked`/`cancelled` and no reason exists, redirect user to edit modal with target status prefilled.
   - If reason already exists, quick update may proceed.

## Validation Rules
- Backend returns `422 task_status_reason_required` when blocked/cancelled is saved without a non-empty reason.
- Reason max length: 2000 chars.
- Reason whitespace-only values are treated as empty.

## Data Model
Add nullable `status_reason TEXT` to `task_board_items`.

## UX Notes
- Use adaptive layout; no fixed-height modal hacks.
- Show concise preview on cards, full text in detail modal.
- Keep copy in Chinese; code/comments remain English.

## Verification
- API tests cover create/update validation and clearing behavior.
- Store tests cover persistence and normalization.
- Frontend build passes.
- Docker-based backend/frontend verification passes.

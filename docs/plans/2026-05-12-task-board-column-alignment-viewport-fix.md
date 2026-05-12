# Task Board Column Alignment and Viewport Containment Fix

## Goal

Fix task-board matrix visual misalignment and overflow issues:
- Add explicit "项目" header before the first status column.
- Ensure collapsed "已完成" column remains readable in horizontal text (no vertical stacking of Chinese chars).
- Align status header tracks and card tracks consistently.
- Reduce over-wide card columns while preserving readability.
- Keep the board fully contained inside viewport width; use internal scroll when content exceeds available width.

## Scope

- Frontend template and CSS only (`frontend/src/App.vue`, `frontend/src/styles/task-board.css`, `frontend/src/styles/task-board-matrix.css`).
- No backend/API/schema changes.

## Non-goals

- No task status workflow change.
- No drag/drop behavior change.
- No browser E2E verification for this UI-only fix.

## Design notes

- Keep one grid template source for header and body row columns through shared CSS custom properties.
- Add visible label text for row-header track (`项目`) to avoid blank leading header cell.
- Collapsed status header keeps horizontal text with enough min width for three Chinese characters.
- Matrix wrapper constrained to panel width (`max-width: 100%`) and scrolls internally (`overflow: auto`) instead of pushing outer page width.
- Matrix header/body use `min-width: 100%` + `width: max-content` so they stay aligned and still support horizontal overflow when needed.

## Verification plan

- `docker compose build frontend`
- Inspect diff to ensure only frontend files + plan doc changed.
- Confirm no backend files changed.

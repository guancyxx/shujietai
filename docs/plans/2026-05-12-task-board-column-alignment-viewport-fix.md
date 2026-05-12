# Task Board Column Alignment, Adaptive Expansion, and Viewport Containment Fix

## Goal

Fully fix the task-board matrix layout so status headers and task-card columns stay aligned under all supported task-board states.

This fix must address the reported regressions together:
- status header columns and task-card columns drift out of alignment;
- the board can push the page wider than the viewport instead of containing overflow inside the board panel;
- expanding the `completed` column can cause the visible card layout to collapse into an incorrect single-column-looking flow;
- expanding `completed` must make the other visible columns and cards adaptively shrink just enough to make room, while still preserving readability.

## Scope

- Frontend task-board matrix implementation only.
- Allowed files:
  - `frontend/src/App.vue`
  - `frontend/src/styles/task-board.css`
  - `frontend/src/styles/task-board-matrix.css`
  - small supporting constants/helpers only if needed for the matrix refactor
- No backend/API/schema changes.

## Non-goals

- No task status workflow change.
- No drag/drop contract change.
- No browser E2E requirement for this UI-only fix.
- No unrelated task-board feature work.

## Current diagnosis

The current matrix layout derives header/body tracks from aggregate counts of expanded vs collapsed columns. That keeps the template compact, but it is too indirect for a six-status kanban with one collapsible status:
- header/body alignment depends on repeated track groups instead of an explicit per-status track list;
- the layout is harder to reason about when one column changes between collapsed and expanded states;
- column width adaptation is not expressed as a direct function of the current status order;
- overflow containment and card shrink behavior are fragile when the board needs to re-balance space after `completed` is expanded.

## Design notes

### 1. One ordered source of truth for visible tracks

The matrix must derive its header/body `grid-template-columns` from the exact `KANBAN_STATUSES` order, not from grouped counts.

Required outcome:
- the first track is always the project label/spacer track;
- every following track maps one-to-one to the matching status in `KANBAN_STATUSES`;
- collapsed and expanded widths are selected per status in order.

### 2. Shared measurable template for header and body

Header and project rows must bind the exact same computed track template.

Required outcome:
- header labels always sit directly above their card columns;
- opening/closing `completed` never changes the relative status order;
- the body cannot silently fall back to auto-placement or implicit tracks.

### 3. Adaptive shrink before overflow

When `completed` expands, the board should first redistribute width across all visible status columns using adaptive `minmax(...)` tracks. Only when the container becomes genuinely too narrow should the board use internal horizontal scrolling.

Required outcome:
- columns narrow smoothly but remain readable;
- cards wrap their internal controls/content naturally instead of forcing a fake single-column board layout;
- the board panel, not the whole page, owns overflow.

### 4. Panel-contained overflow

The task-board page and panel must keep `min-width: 0` / single-column containment so generic page-grid breakpoints cannot reintroduce horizontal page overflow.

### 5. Card layout resilience inside narrow columns

Task cards inside matrix cells must tolerate narrower column widths:
- top section may stack responsively;
- action buttons may wrap;
- long names/descriptions must clamp and break safely;
- child task cards must inherit the same resilience.

## Acceptance criteria

1. Header/body alignment
   - Every status header aligns with the task cards in the same status column.
   - No status column appears visually shifted relative to its cards.

2. Completed-column expansion behavior
   - Expanding `completed` keeps all statuses in the intended order.
   - Other visible columns shrink adaptively to make room.
   - The board does not degenerate into an incorrect “all cards in one vertical strip” presentation.

3. Viewport containment
   - The task-board panel stays within the page width.
   - Any necessary horizontal overflow is contained inside the matrix wrapper.
   - The page itself should not be widened by the board.

4. Existing interaction safety
   - Current drag/drop behavior for visible columns still works.
   - Collapsed-column summary behavior still works.
   - No backend/API payload behavior changes.

## Implementation tasks

1. Replace count-driven matrix track generation with an explicit per-status track template derived from `KANBAN_STATUSES` and collapsed state.
2. Bind the shared template to both matrix header and matrix body rows.
3. Tighten task-board panel containment so board overflow stays internal.
4. Adjust matrix/card CSS so expanded `completed` causes adaptive narrowing before scroll fallback.
5. Keep collapsed `completed` rendering and drag/drop guards intact.
6. Run Docker-based frontend verification and diff inspection.

## Verification plan

- `docker compose build frontend`
- Disposable frontend production build:
  - `docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/frontend:/app" -w /app node:20-alpine sh -lc 'npm ci && npm run build'`
- HTTP smoke from the existing local stack:
  - `curl -s -o /tmp/shujietai_frontend_taskboard.html -w '%{http_code}\n' http://localhost:15173/`
  - `curl -s -o /tmp/shujietai_taskboard_api.json -w '%{http_code}\n' http://localhost:18000/api/v1/task-board`
- Diff inspection:
  - confirm only frontend task-board files and this plan doc changed;
  - confirm no backend/API/schema files changed.

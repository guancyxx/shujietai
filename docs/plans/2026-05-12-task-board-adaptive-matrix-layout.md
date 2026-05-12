# Task Board Adaptive Matrix Layout Plan

## Problem

The previous task-board matrix fix used explicit pixel widths for the row label, expanded status columns, and collapsed status columns. That prevented the cancelled status from wrapping, but it also made the layout feel fixed instead of adaptive.

## Requirements

- Keep the status order: 草稿 / 待执行 / 进行中 / 阻塞 / 取消 / 已完成.
- Keep the completed column collapsible.
- Remove fixed JavaScript pixel constants for matrix layout sizing.
- Let the matrix adapt to available panel width with CSS grid fractions and `minmax()`.
- Avoid squeezing cards into unreadable shapes; if the viewport is too narrow, allow the board to scroll horizontally as a natural overflow fallback.
- Avoid fixed task-card action widths; let action buttons wrap based on available width.

## Design

- Use CSS custom properties from Vue only for the number of expanded columns and collapsed columns.
- Define matrix tracks in CSS:
  - label column: `minmax(clamp(8rem, 14vw, 12rem), 0.55fr)`
  - expanded columns: `repeat(var(--kanban-expanded-columns), minmax(clamp(11rem, 14vw, 17rem), 1fr))`
  - collapsed columns: `repeat(var(--kanban-collapsed-columns), minmax(3.5rem, 0.18fr))`
- Keep a content-based `min-width: max-content` on the matrix rows/header so narrow screens scroll instead of crushing content.
- Keep card top layout responsive: default two-column action area where space allows; inside matrix cells, allow it to become a single column naturally via container width rules.

## Verification plan

- Docker build frontend from the worktree.
- Docker-run frontend production build if needed.
- Refresh local app containers from the main checkout after merge or for local validation.
- Browser/DOM check: matrix header and row use CSS var-driven adaptive columns; no JS fixed width constants remain.

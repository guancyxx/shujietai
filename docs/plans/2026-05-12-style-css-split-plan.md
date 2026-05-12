# Spec: Frontend style.css Modular Split (ShuJieTai)

## Objective
将 `frontend/src/style.css` 从单文件（3463 lines）拆分为按职责分层的模块化样式文件，降低维护复杂度与样式回归风险。

目标不是视觉重构，而是“零视觉行为变化”的结构化拆分：
- Preserve existing selectors and cascade behavior.
- Preserve responsive breakpoints and page-specific overrides.
- Keep `App.vue` as orchestration shell, while reducing CSS coupling.

## Context Snapshot (Read-Only Discovery)
- Current entry: `frontend/src/main.js` imports only `./style.css`.
- Current stylesheet size: 3463 lines.
- Major style domains detected in same file:
  - global tokens/reset/layout shell
  - chat/timeline/composer
  - project management page
  - task board + kanban matrix
  - model/system config + picker modal
  - dispatch runtime + dispatch history
  - skills catalog + skill detail modal
  - responsive media queries (1439/1023/767/900)
- Existing risks to preserve:
  - Single-column page variant overrides under `@media (max-width: 1439px)`.
  - Multiple repeated selectors used intentionally by breakpoint cascade.
  - Legacy duplicate selector blocks near file end (e.g. task-status color blocks) must keep effective order.

## Non-Goals
- No UI redesign.
- No selector rename.
- No class semantic change.
- No Vue template refactor in this task.

## Tech Stack
- Vue 3 + Vite
- Plain CSS (no CSS Modules, no Sass)
- Docker Compose build/test flow

## Commands (Docker-first)
- Build frontend image:
  - `docker compose build frontend`
- Frontend production build in disposable container (worktree-safe):
  - `docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/frontend:/app" -w /app node:20-alpine sh -lc 'npm ci && npm run build'`
- Smoke checks (primary running stack):
  - `curl -s -o /tmp/shujietai_frontend_check.html -w '%{http_code}\n' http://localhost:15173/`
  - `curl -s -o /tmp/shujietai_task_board_check.json -w '%{http_code}\n' http://localhost:18000/api/v1/task-board`

## Project Structure (Target)
新增目录：`frontend/src/styles/`

Planned files:
- `index.css` (import aggregator only)
- `base.css` (root variables, reset, shell, generic utilities)
- `layout.css` (topbar, nav, main grid, shared panel/layout primitives)
- `chat.css` (conversation list, timeline, composer, thinking/tool bubbles, markdown in timeline)
- `projects.css` (project page and cards)
- `task-board.css` (task board cards, tree, detail modal, status/priority, matrix board)
- `config.css` (state panel, picker modal, model/system config)
- `dispatch.css` (dispatch status bar, history page, detail overlay)
- `skills-catalog.css` (skills catalog list/cards/modals/graph toggle)
- `responsive.css` (all media query rules centralized, keeping original order semantics)

Entry switch:
- `frontend/src/main.js` from `import './style.css'` to `import './styles/index.css'`

Compatibility phase:
- Keep `style.css` temporarily as deprecated passthrough or remove in final step after build passes.

## Code Style
- English comments only.
- Preserve selector text exactly unless technically required.
- Keep same declaration order within each moved block to avoid cascade drift.
- For cross-file cascade requirements, enforce import order in `styles/index.css`.

## Boundary Rules
### Always
- Keep behavior and visuals unchanged.
- Move CSS in contiguous blocks with minimal edits.
- Preserve media query override precedence.
- Run Docker-based verification after split.

### Ask First
- Any selector rename/merge that changes specificity.
- Any breakpoint value change.
- Any removal of duplicate declarations whose intent is uncertain.

### Never
- Introduce host runtime (`npm run` directly on host project env).
- Combine style split with feature/UI redesign.
- Modify unrelated backend/frontend logic.

## Proposed Implementation Plan (Task Breakdown)

### Task 1: Bootstrap modular style entry (S)
Acceptance:
- [ ] `frontend/src/styles/index.css` created with deterministic import order.
- [ ] `main.js` imports `./styles/index.css`.
Verify:
- [ ] `docker compose build frontend` passes.

### Task 2: Extract base + layout domains (M)
Acceptance:
- [ ] base/reset/shell/layout/topbar/nav/main-grid rules moved to `base.css` + `layout.css`.
- [ ] No selector/value change except path/import updates.
Verify:
- [ ] frontend build passes in disposable container.

### Task 3: Extract page domains (L -> split into small batches)
3a chat, 3b projects, 3c task-board, 3d config, 3e dispatch, 3f skills-catalog
Acceptance:
- [ ] Each domain moved to dedicated file.
- [ ] Original intra-domain rule order preserved.
Verify:
- [ ] frontend build passes after each sub-batch.

### Task 4: Responsive consolidation (M)
Acceptance:
- [ ] media query blocks centralized in `responsive.css`.
- [ ] Single-column variant overrides (`task-board-grid`, `dispatch-history-grid`, `config-grid`) remain effective at 1439/1023/767 breakpoints.
Verify:
- [ ] build passes; no missing selector errors.

### Task 5: Cleanup + parity checks (S)
Acceptance:
- [ ] old `style.css` either removed or replaced by documented deprecation shim.
- [ ] no duplicate import loops.
- [ ] git diff scoped to CSS/import changes.
Verify:
- [ ] `docker compose build frontend`
- [ ] disposable `npm ci && npm run build`
- [ ] smoke endpoints return 200.

## Risk Register
1) Cascade regression risk (HIGH)
- Mitigation: preserve rule order + deterministic index import + sub-batch builds.

2) Breakpoint override loss (HIGH)
- Mitigation: explicit checklist for 1439/1023/767 blocks and single-column page variants.

3) Hidden duplicate selector semantics (MEDIUM)
- Mitigation: do not deduplicate in this task; move as-is first.

## Success Criteria
- `style.css` no longer monolithic for primary maintenance path.
- New modular files under `frontend/src/styles/` own all styling.
- Frontend Docker build and production build pass.
- API smoke endpoints used by frontend remain 200.
- No intentional visual/behavior change introduced.

## Open Questions (Need Your Confirmation)
1. `style.css` final state preference:
   - A) delete file completely
   - B) keep as deprecated shim with comment and `@import './styles/index.css';`
2. Whether to place all media queries in `responsive.css` (recommended), or keep media rules with each domain file.

## Next Step
等待你确认上面两个 Open Questions；确认后我按该计划开始实施拆分。
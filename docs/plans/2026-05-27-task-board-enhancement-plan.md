# Implementation Plan: Task Board Enhancement

## Overview

Three independent enhancements to the ShuJieTai task board:
1. Worktree continuity convention in skill-created task descriptions
2. Markdown/HTML rendering for task detail descriptions
3. Prerequisite-check mechanism to block premature task execution

## Architecture Decisions

- **Markdown renderer**: Reuse existing `useMarkdownRenderer` (marked + DOMPurify) — no new deps
- **Prerequisite check**: Backend-first — new endpoint returns canonical status; frontend and worker both call it
- **Worker enforcement**: `pending_execution_worker` also checks prerequisites before dispatching — defense in depth
- **Worktree format**: `worktree: <name>` (bare name, no path) — kept simple, the worker/repo path is already known context

## Task List

### Phase 1: Quick Wins (independent of each other)

- [ ] **Task 1**: Markdown/HTML rendering for task detail descriptions
- [ ] **Task 2**: Worktree continuity convention in skills

### Checkpoint: Phase 1
- [ ] TaskBoardPage detail modal renders markdown correctly
- [ ] Skills are updated with worktree conventions

### Phase 2: Prerequisite Checks

- [ ] **Task 3**: Backend prerequisite-check endpoint
- [ ] **Task 4**: Frontend prerequisite gate + worker enforcement

### Checkpoint: Complete
- [ ] All three features working end-to-end
- [ ] Docker build + health check pass
- [ ] PR created

---

## Task 1: Markdown/HTML rendering for task detail descriptions

**Description:** Replace plain-text `{{ }}` interpolation with `v-html` + `renderMarkdown()` in both `TaskBoardPage.vue` and `TaskArchivePage.vue` detail modals. The `useMarkdownRenderer` composable already exists and is used in chat messages — just import and use it.

**Acceptance criteria:**
- [ ] `TaskBoardPage.vue` line 187: description rendered via `v-html="renderMarkdown(ts.taskBoardDetailItem.description || '暂无描述')"`
- [ ] `TaskArchivePage.vue` line 75: same treatment for archived task detail
- [ ] `.task-detail-markdown` CSS already has rules for `code`, `pre`, `p`, `ul`, `ol`, `blockquote` — verify compatibility
- [ ] XSS safe: DOMPurify is built into `useMarkdownRenderer`
- [ ] Docker build succeeds, frontend loads, task description with markdown (e.g. `**bold**`, `- list item`, `\`code\``) renders correctly

**Verification:**
- [ ] `docker compose build frontend && docker compose up -d --force-recreate frontend`
- [ ] `curl -s -o /dev/null -w '%{http_code}' http://localhost:15173/` → 200
- [ ] Open task with markdown in description → detail modal shows formatted content

**Dependencies:** None

**Files likely touched:**
- `frontend/src/views/TaskBoardPage.vue` (~4 lines changed)
- `frontend/src/views/TaskArchivePage.vue` (~4 lines changed)

**Estimated scope:** XS (2 files, import + template change)

---

## Task 2: Worktree continuity convention in skills

**Description:** Update three skill files to encode the worktree continuity pattern:
1. `shujietai-task-board-create-workflow` — add requirement that series tasks include `worktree: <name>` in description
2. `sequential-subtask-execution.md` — change workflow: don't delete worktree between subtasks, push to remote after each, create PR only after all done
3. `shujietai-task-project-management` — update "Sequential Subtask Execution Workflow" section

**Acceptance criteria:**
- [ ] `shujietai-task-board-create-workflow` task description contract includes: `worktree: <name>` field in description for series tasks; subsequent tasks use `worktree: <same-name> (reuse)`
- [ ] `sequential-subtask-execution.md` flow updated: step 9 changes from "Remove worktree + delete branch" to "Push branch to remote (git push origin <branch>), keep worktree for next subtask"; add final step after all subtasks: "Create PR → merge → remove worktree"
- [ ] `shujietai-task-project-management` "Sequential Subtask Execution Workflow" matches the updated pattern

**Verification:**
- [ ] Review updated skill files — convention is clear and actionable to a future agent

**Dependencies:** None

**Files likely touched:**
- `~/.hermes/personal-skills/devops/shujietai-task-board-create-workflow/SKILL.md`
- `~/.hermes/personal-skills/devops/shujietai-task-project-management/references/sequential-subtask-execution.md`
- `~/.hermes/personal-skills/devops/shujietai-task-project-management/SKILL.md`

**Estimated scope:** S (3 skill files, documentation-only)

---

## Task 3: Backend prerequisite-check endpoint

**Description:** Add `GET /api/v1/task-board/{task_id}/prerequisites-check` that checks whether `upstream_task_id` and `parent_task_id` dependencies are `completed`. Returns structured response with per-dependency status.

**Acceptance criteria:**
- [ ] New `TaskBoardPrerequisiteCheck` response schema in `schemas.py`:
  ```python
  class PrerequisiteCheckItem(BaseModel):
      dependency_type: Literal["upstream", "parent"]
      task_id: UUID | None
      task_name: str | None
      status: str | None
      satisfied: bool
  class TaskBoardPrerequisiteCheckResponse(BaseModel):
      all_satisfied: bool
      checks: list[PrerequisiteCheckItem]
  ```
- [ ] New endpoint in `routes_task_board.py`: `GET /api/v1/task-board/{task_id}/prerequisites-check`
- [ ] Logic: for a given task, look up `upstream_task_id` and `parent_task_id`. If null → satisfied=true. If set → check their status === "completed"
- [ ] Returns 200 with check results; returns 404 if task not found
- [ ] curl verify:
  ```bash
  curl http://localhost:18000/api/v1/task-board/<task_id>/prerequisites-check
  # → {"all_satisfied": false, "checks": [{"dependency_type":"upstream","task_id":"...","task_name":"...","status":"draft","satisfied":false}]}
  ```

**Verification:**
- [ ] `docker compose build backend && docker compose up -d --force-recreate backend`
- [ ] `curl http://localhost:18000/api/v1/health` → 200
- [ ] Create two tasks (A=completed, B with upstream=A) → check B's prerequisites → all_satisfied=true
- [ ] Create task C with upstream=B (B not completed) → check C → all_satisfied=false

**Dependencies:** None (standalone endpoint)

**Files likely touched:**
- `backend/app/schemas.py` (~15 lines added)
- `backend/app/api/routes_task_board.py` (~30 lines added)
- `backend/app/services/sqlalchemy_store.py` (~20 lines, query method)

**Estimated scope:** S (3 files, ~65 lines)

---

## Task 4: Frontend prerequisite gate + worker enforcement

**Description:** Wire up the prerequisite check on the frontend to block status transitions, and add the same check to the `pending_execution_worker` as a backend safety net.

**Acceptance criteria:**
- [ ] `useTaskStore.js`: new `checkPrerequisites(task)` action that calls `GET /api/v1/task-board/{id}/prerequisites-check`
- [ ] Frontend gate: when user tries to move a task to `pending_execution` or `in_progress` (via drag-and-drop or quick status change), call `checkPrerequisites` first. If `all_satisfied=false`, show a warning with unsatisfied dependency names and block the transition
- [ ] Warning uses `window.confirm`-style modal listing: "前置任务未完成: [task_name] (状态: [status])"
- [ ] Edit modal save also enforces the check on those status transitions
- [ ] `pending_execution_worker.py`: in `process_pending_execution_once`, before dispatching, call the prerequisite check (via `dispatch_service` or direct DB query) and skip tasks whose `all_satisfied=false`, logging a warning
- [ ] Worker skip: `logger.warning("Skipping task_board_item=%s: prerequisites not satisfied", ...)`

**Verification:**
- [ ] Create task A (draft), task B (draft, parent=A). Attempt to move B to `in_progress` → blocked with warning
- [ ] Complete task A. Move B to `in_progress` → succeeds
- [ ] Docker build both: `docker compose build backend frontend && docker compose up -d --force-recreate backend frontend`
- [ ] Health checks pass

**Dependencies:** Task 3 (backend endpoint must exist)

**Files likely touched:**
- `frontend/src/stores/useTaskStore.js` (~30 lines, new action + gate logic)
- `backend/app/services/pending_execution_worker.py` (~20 lines, pre-dispatch check)

**Estimated scope:** S (2 files, ~50 lines)

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| `v-html` in detail modal exposes XSS | High | DOMPurify is already in `useMarkdownRenderer` — all output is sanitized |
| Prerequisite check blocks legitimate manual overrides | Med | Only blocks `pending_execution`/`in_progress` transitions; user can still set other statuses. Future: add force-override flag |
| Worker skip creates silent failure | Low | `logger.warning` ensures discoverability in backend logs |

## Open Questions

None — all resolved in spec.

# Spec: Task Board Enhancement — Worktree Continuity, Markdown Rendering, Prerequisite Checks

## Objective

增强 ShuJieTai 任务看板三个核心能力：

1. **Worktree 连续性与跨编码器协作**：skill 创建的系列任务在描述中明确 worktree 名称，子任务链复用同一 worktree（不删除、不合并 PR），跨机器编码时推送更改到远端。
2. **任务详情 Markdown/HTML 渲染**：任务描述支持富文本渲染（Markdown + safe HTML），前端详情弹窗使用 v-html 渲染而非纯文本。
3. **前置任务完成校验**：任务进入 `pending_execution` 或 `in_progress` 之前，检查其 `upstream_task_id` 和 `parent_task_id` 指向的任务是否已完成。

## Tech Stack

- Backend: FastAPI + SQLAlchemy + PostgreSQL
- Frontend: Vue 3 (Composition API, Pinia stores) + Vite
- Markdown rendering: marked + DOMPurify (already in `useMarkdownRenderer.js`)
- Existing codebase: `/home/guancy/workspace/shujietai`

## Commands

```
Build:  docker compose build backend frontend
Start:  docker compose up -d backend frontend
Verify: curl http://localhost:18000/api/v1/health
        curl http://localhost:15173/
Lint:   docker exec shujietai-backend ruff check /app
        docker exec shujietai-frontend npx eslint src/
```

## Project Structure

```
backend/app/
├── api/routes_task_board.py      ← 新增 prerequisite check endpoint
├── schemas.py                    ← 新增 TaskBoardPrerequisiteCheckResponse
├── services/sqlalchemy_store.py  ← 新增 prerequisite check 查询方法
├── services/task_lifecycle.py    ← 新增前置任务检查逻辑

frontend/src/
├── views/TaskBoardPage.vue       ← 详情弹窗改用 v-html + renderMarkdown
├── views/TaskArchivePage.vue     ← 同步改为 v-html 渲染
├── stores/useTaskStore.js        ← 新增 prerequisite check store action
├── styles/task-board.css         ← 已有 .task-detail-markdown CSS, 可能需要微调

docs/plans/
├── 2026-05-27-task-board-enhancement-plan.md  ← 实施计划

skills/
├── devops/shujietai-task-board-create-workflow  ← 更新：worktree 名称约定
├── devops/shujietai-task-project-management     ← 更新：sequential workflow 不删除 worktree
```

## Code Style

- Backend: Python 3.12+, type hints, Pydantic models, SQLAlchemy 2.0 syntax
- Frontend: Vue 3 `<script setup>`, Pinia stores, existing class names and CSS conventions
- Comments in English only; user-facing text in Chinese
- Follows existing project patterns (see shujietai-development skill)

## Testing Strategy

- Backend: manual curl verification + Docker health check
- Frontend: Docker build verify + manual UI smoke test
- No new test framework dependencies

## Boundaries

- Always: build via Docker before commit; verify endpoints respond 200; PR-first workflow
- Ask first: database migrations (Alembic); changes to `.env`; npm package additions
- Never: skip spec review; merge to main without PR; change CSS class names without cross-referencing existing files

## Success Criteria

### 需求1 — Worktree 连续性

1. `shujietai-task-board-create-workflow` skill 更新：创建多任务时，首任务描述包含 `worktree: <repo>/.worktrees/<name>`；后续任务描述包含 `worktree: <same-name> (reuse)`
2. `sequential-subtask-execution.md` 更新：子任务之间不删除 worktree；每个子任务完成后推送到远端（git push origin <branch>）；所有子任务完成后再创建 PR 合并
3. 新约定写入 `shujietai-task-project-management` skill 的 "Sequential Subtask Execution Workflow" 章节

### 需求2 — Markdown/HTML 渲染

1. `TaskBoardPage.vue` 第 187 行：`<div class="task-detail-markdown">{{ ts.taskBoardDetailItem.description || '暂无描述' }}</div>` 改为 `v-html` + `renderMarkdown()`
2. `TaskArchivePage.vue` 第 75 行：同样改为 `v-html` + `renderMarkdown()`
3. 现有 `.task-detail-markdown` CSS 规则已验证兼容（code/pre/p/ul/ol/blockquote）
4. 安全：经过 DOMPurify sanitize，XSS 防护
5. Docker 构建成功 + 前端访问正常渲染

### 需求3 — 前置任务检查

1. 后端新增 `GET /api/v1/task-board/{task_id}/prerequisites-check` 端点，返回：
   ```json
   {
     "all_satisfied": true/false,
     "checks": [
       {"dependency_type": "upstream|parent", "task_id": "...", "task_name": "...", "status": "completed|...", "satisfied": true/false}
     ]
   }
   ```
2. 前端 `useTaskStore` 新增 `checkPrerequisites(task)` action
3. 任务状态切换到 `pending_execution` 或 `in_progress` 时自动调用检查
4. 检查不通过时显示警告弹窗（使用 `window.confirm` 或 modal），列出未完成的前置任务，阻止状态变更
5. `pending_execution_worker` 在拾取任务前也执行相同检查，跳过前置未完成的任务

## Open Questions (Resolved)

1. **`pending_execution_worker` 前置检查**：是，worker 拾取任务前先检查前置依赖是否满足，不满足则跳过。
2. **Worktree 名称格式**：使用简短名称 `worktree: <name>`（如 `worktree: fix-auth-bug`），不含完整路径。
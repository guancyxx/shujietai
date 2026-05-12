# App.vue SOLID Decomposition Spec

## Objective

Refactor `frontend/src/App.vue` from a large orchestration component into smaller files with focused responsibilities while preserving current runtime behavior and UI contracts.

## Scope

- Keep `App.vue` as the top-level orchestration shell.
- Extract stable constants and label maps into dedicated modules.
- Extract HTTP/API helpers into a reusable service module.
- Extract markdown rendering cache into a focused composable.
- Extract timeline auto-scroll state into a focused composable.
- Avoid changing backend APIs, routes, CSS ownership, or visual layout.

## Non-goals

- No redesign of UI layout.
- No backend changes.
- No dependency changes unless required by build.
- No behavioral rewrites of dispatch/session/task-board flows.

## Target structure

- `frontend/src/constants/appConstants.js`: page whitelist, status maps, role maps, kanban maps, runtime option labels.
- `frontend/src/services/apiClient.js`: JSON request helpers and API error mapping.
- `frontend/src/composables/useMarkdownRenderer.js`: marked + DOMPurify rendering with bounded cache.
- `frontend/src/composables/useTimelineScroll.js`: scroll-to-bottom and user-scroll tracking behavior.
- `frontend/src/App.vue`: shell state orchestration and page-level flow coordination.

## SOLID mapping

- Single Responsibility: constants, API transport, markdown rendering, and scrolling each have one reason to change.
- Open/Closed: new labels/statuses can be added in constants without touching transport/rendering logic.
- Dependency Inversion: App shell depends on small modules instead of owning low-level HTTP/DOM/markdown details.
- Interface Segregation: each extracted module exposes a narrow API used by App.vue.

## Safety constraints

- Preserve existing user-facing Chinese strings and API payload shapes.
- Do not log tokens or secret values.
- Keep comments in English only.
- Use Docker-based verification only.

## Verification

- `docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/frontend:/app" -w /app node:20-alpine sh -lc 'npm ci && npm run build'`
- `docker compose build frontend`
- `git diff --check`

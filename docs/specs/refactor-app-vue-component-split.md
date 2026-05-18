# Refactor: Split App.vue into Pinia Stores + Component/View Tree

## Status: IMPLEMENTED

## Goal
The original `App.vue` was 3309 lines — a monolith containing all state management, 8 pages, 8 modals, chat UI, WebSocket management, and 4 composable integrations. This refactor extracted state into 4 Pinia stores alpha map the UI into modular components and page views.

## Technical Stack
- Vue 3.4 + Composition API (`<script setup>`)
- Pinia 2.2 state management
- Vite 5.4 build tooling
- All CSS remains in `frontend/src/styles/` (unchanged)

## Architecture

### Before
```
App.vue (3309 lines)
├── Script: ~2400 lines — all state, all logic, all API calls
├── Template: ~900 lines — navbar, 8 pages (v-if), 8 modals
```

### After
```
frontend/src/
├── App.vue                     ~130 lines (thin shell: layout + navbar + page switching)
├── stores/
│   ├── useSessionStore.js      ~19KB  — sessions, messages, WS, dispatch task
│   ├── useTaskStore.js         ~23KB  — task board, archive, kanban
│   ├── useProjectStore.js      ~6KB   — projects CRUD, GitHub repos
│   └── useConfigStore.js       ~9KB   — runtime config, models, skills, MCP
├── views/
│   ├── ChatPage.vue                     — session list + timeline + composer
│   ├── ProjectsPage.vue                 — project cards + create/edit/delete
│   ├── TaskBoardPage.vue                — kanban matrix with drag-drop
│   ├── TaskArchivePage.vue              — archived task list + detail
│   ├── ModelConfigPage.vue              — model/Skill/MCP config tables
│   ├── SystemConfigPage.vue             — system-level config
│   ├── DispatchHistoryPage.vue           — dispatch task history
│   └── SkillsCatalogPage.vue            — skills catalog browser
├── components/
│   ├── chat/
│   │   ├── ChatSessionList.vue          — left sidebar session list
│   │   ├── ChatTimeline.vue             — message timeline with WS streaming
│   │   └── ChatComposer.vue             — message composer + platform selector
│   └── modals/
│       ├── CreateConversationModal.vue   — new conversation form
│       ├── ProjectCreateModal.vue        — new project form
│       ├── ProjectEditModal.vue          — edit project form
│       ├── ModelModal.vue                — model add/edit
│       ├── SkillModal.vue                — skill add/edit
│       ├── McpModal.vue                  — MCP tool add/edit
│       ├── TaskBoardCreateModal.vue      — new task form
│       └── TaskBoardEditModal.vue        — edit task form
```

## Key Decisions

1. **Pinia over provide/inject**: Stores provide time-travel debugging, devtools integration, and cleaner dependency tracking.
2. **No router (vue-router removed)**: Navigation uses `activePage` ref + `v-if` in App.vue shell. Consistent with pre-refactor design; avoids unnecessary router complexity when there are no URL-based routes.
3. **Composables unchanged**: `useWebSocket`, `useDispatchTask`, `useTimelineScroll`, `useMarkdownRenderer` remain as-is; stores compose them.
4. **Styles untouched**: All CSS files in `frontend/src/styles/` remain exactly as they were.
5. **Spec-first**: Two spec documents: `refactor-app-vue-component-split-plan.md` (tasks) and this file (architecture).

## Verification

- `npx vite build`: 67 modules transformed, 0 errors
- Output: `dist/index.html` + `dist/assets/index-B4fmuB6n.css` (54KB gzip 11.5KB) + `dist/assets/index-D8bVHxhC.js` (250KB gzip 80KB)
- Dev runtime: All composable imports verified in stores via compatibility check

## File Changes
- `frontend/src/App.vue`: ~3309 → ~130 lines
- `frontend/src/main.js`: Added Pinia plugin registration
- `frontend/package.json`: Added `pinia` dependency
- New: 4 stores, 3 chat components, 8 modals, 8 pages
- Docs: 2 spec files in `docs/specs/`

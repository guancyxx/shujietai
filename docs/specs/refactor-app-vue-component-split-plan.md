# Implementation Plan: Refactor App.vue — Component Split

## Overview

Decompose the 3309-line `App.vue` into a ~80-line shell, 8 page views, ~13 sub-components, and 4 Pinia stores. Behavior-preserving: every page, modal, button, and API call must work identically.

## Architecture Decisions

- Pinia stores capture ALL state currently in 95 `ref()` declarations in App.vue.
- Existing composables (`useTaskBoard`, `useProjects`, `useArchive`, `useRuntimeConfig`) are KEPT but may be invoked from stores or page components instead of App.vue.
- Page-level components own `v-if="activePage === 'X'"` logic; App.vue becomes a `<component :is="...">` or `v-if` router.
- Sub-components (modals, chat pieces) use Pinia stores directly via `useXxxStore()` — no prop drilling.

## Task List

### Phase 1: Foundation — Infrastructure + Stores

**Task 1: Install Pinia + Update main.js** [Size: S — 2 files]

- Acceptance:
  - `pinia` added to `package.json` dependencies
  - `main.js` imports and registers `createPinia()`
  - `docker compose build frontend` succeeds
- Verify: `docker compose build frontend` exits 0
- Files: `frontend/package.json`, `frontend/src/main.js`
- Depends on: None

**Task 2: Create useSessionStore** [Size: M — 1 file, ~200 lines]
- Acceptance:
  - All chat/session state extracted from App.vue: `sessions`, `selectedSessionId`, `selectedExternalSessionId`, `timeline`, `cockpit`, `composerText`, `sending`, `isBlankChatMode`, `blankChatProvider`, `streamingContent`, `isStreaming`, `streamAbortController`, `deletingSessionId`, `clearingSessions`, `displayMessages`, `conversationLatestStatus`, `currentLinkedTask`, `currentLoadedSkills`
  - All session-related actions: `loadSessions`, `loadTimeline`, `loadCockpit`, `sendMessage`, `createConversation`, `deleteSession`, `clearAllSessions`, `activateBlankChat`, `selectConversation`, `refreshData`
- Verify: No runtime errors on store import; can be tested after Task 5
- Files: `frontend/src/stores/useSessionStore.js`
- Depends on: Task 1

**Task 3: Create useTaskStore** [Size: M — 1 file, ~200 lines]
- Acceptance:
  - All task board/archive state: `taskBoardItems`, filters, collapse state, drag state, create/edit modal state, forms, `taskBoardMatrix`, `archivedTaskItems`, archive filters/modal/loading state
  - All task actions: `loadTaskBoardItems`, `loadArchivedTasks`, `archiveTaskBoardItem`, `unarchiveTaskBoardItem`, kanban collapse/drag handlers, CRUD operations
- Verify: No runtime errors; can be tested after Task 5
- Files: `frontend/src/stores/useTaskStore.js`
- Depends on: Task 1

**Task 4: Create useProjectStore + useConfigStore** [Size: M — 2 files, ~150 lines each]
- Acceptance:
  - `useProjectStore`: `projects`, `githubRepos`, project CRUD state, modals, forms (all from `useProjects` composable + App.vue glue)
  - `useConfigStore`: `selectedModel`, `selectedSkills`, `selectedMcpServers`, all modal temp-state, `systemConfig`, `skillsCatalog`, `createConversation` state (all from `useRuntimeConfig` composable + App.vue glue)
- Verify: No runtime errors; can be tested after Task 5
- Files: `frontend/src/stores/useProjectStore.js`, `frontend/src/stores/useConfigStore.js`
- Depends on: Task 1

### Checkpoint: Foundation
- [ ] 4 Pinia stores exist with complete state + actions
- [ ] `main.js` registers Pinia
- [ ] `docker compose build frontend` passes

### Phase 2: Sub-Components

**Task 5: Create chat sub-components** [Size: L — 5 files, ~50-100 lines each]
- Acceptance:
  - `ChatSidebar.vue`: session list, new/clear buttons, blank chat entry, delete buttons
  - `ChatTimeline.vue`: message list with scroll, thinking/tool/normal bubble rendering, dispatch status bar
  - `ChatMessage.vue`: single message — thinking bubble (collapsible), tool call bubble, normal message with markdown
  - `ChatComposer.vue`: textarea + send button, conversation status bar, skill chips, linked task chip
  - `DispatchStatusBar.vue`: task status indicator with cancel/resume/clear buttons
  - Each component imports the relevant Pinia store(s) directly
- Verify: Build succeeds; visually identical to current App.vue chat section
- Files: `frontend/src/components/chat/ChatSidebar.vue`, `ChatTimeline.vue`, `ChatMessage.vue`, `ChatComposer.vue`, `DispatchStatusBar.vue`
- Depends on: Task 2, Task 3

**Task 6: Create all 8 modals** [Size: L — 8 files, ~40-80 lines each]
- Acceptance:
  - `ModelModal.vue`: model picker with search + provider filter
  - `SkillModal.vue`: skill checkbox picker with search
  - `McpModal.vue`: MCP server checkbox picker with search
  - `CreateConversationModal.vue`: platform + initial message form
  - `TaskBoardCreateModal.vue`: task creation form with all fields
  - `TaskBoardEditModal.vue`: task edit form
  - `ProjectCreateModal.vue`: project creation form
  - `ProjectEditModal.vue`: project edit form
  - Each modal imports relevant Pinia store, template copied from App.vue modal sections
- Verify: Build succeeds; each modal opens/closes/submits identically
- Files: 8 files under `frontend/src/components/modals/`
- Depends on: Task 2, Task 3, Task 4

### Checkpoint: Sub-Components
- [ ] All 13 sub-components exist
- [ ] `docker compose build frontend` passes
- [ ] No import resolution errors

### Phase 3: Page Views + Shell

**Task 7: Create all 8 page views** [Size: L — 8 files, ~30-200 lines each]
- Acceptance:
  - Each view composes relevant sub-components + modals
  - `ChatView.vue`: composes ChatSidebar + ChatTimeline + ChatComposer + all modals (~200 lines)
  - `ProjectsView.vue`: project list + cards + create/edit modals (~100 lines)
  - `TaskBoardView.vue`: kanban matrix + create/edit modals (~200 lines)
  - `TaskArchiveView.vue`: archived task list + detail view (~100 lines)
  - `ModelConfigView.vue`: model config display + model modal (~60 lines)
  - `SystemConfigView.vue`: system settings display (~60 lines)
  - `DispatchHistoryView.vue`: dispatch history list + detail (~100 lines)
  - `SkillsCatalogView.vue`: skills list + skill detail (~80 lines)
  - Each view uses activePage condition; App.vue will route to exactly one at a time
- Verify: All imports resolve; build succeeds
- Files: 8 files under `frontend/src/views/`
- Depends on: Tasks 5, 6

**Task 8: Rewrite App.vue as thin shell** [Size: S — 1 file, ~80 lines]
- Acceptance:
  - App.vue contains only: top nav bar (8 buttons), error banner, `<component :is>` or `v-if` routing for 8 pages
  - activePage state + localStorage persistence (may move to a store or keep inline)
  - `onMounted` initializes stores
  - All 3309 original lines removed
- Verify: `docker compose build frontend` succeeds with no errors
- Files: `frontend/src/App.vue` (rewrite)
- Depends on: Task 7

### Checkpoint: Shell + Integration
- [ ] App.vue < 150 lines
- [ ] All 8 pages accessible via top nav
- [ ] No missing imports or component references

### Phase 4: Verify + Ship

**Task 9: Build, verify, commit, push, PR** [Size: M — verification only]
- Acceptance:
  - `docker compose build frontend` exits 0
  - `docker compose up -d frontend` starts, HTTP 200 on `:15173`
  - All 8 pages render correctly, all 9 modals work
  - Zero new console errors
  - Backend health `:18000/api/v1/health` returns 200
  - All changes committed as single atomic commit
  - Branch pushed, PR created
- Verify: Manual browser check of all pages + modals; curl health checks
- Depends on: Task 8

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Pinia store state shape mismatches composable expectations | Medium | Stores wrap composable state exactly — composables continue to work internally |
| Sub-component template extraction introduces subtle DOM differences | Medium | Diff template line-by-line against original App.vue sections |
| CSS scoping changes (no `<style scoped>` added — using global CSS) | Low | All CSS is already global (10 external files); no `<style>` blocks in new components |
| Active page state + localStorage behavior breaks | Low | Either keep in App.vue or move to a simple `useAppStore` |
| Modal `v-if` on parent vs. component breaks overlay click behavior | Medium | Each modal is self-contained with its own overlay; store controls visibility |

## Parallelization Opportunities

- Tasks 2, 3, 4 (stores) can be created in parallel — they have no cross-dependencies.
- Tasks 5, 6 (chat sub-components + modals) can be parallel after stores exist.
- No task within Phase 3 can start before Phase 2 completes.

## Success Verification Checklist

- [ ] `docker compose build frontend` exits 0
- [ ] `App.vue` < 150 lines (down from 3309)
- [ ] 21+ new files created (8 views + 13 components + 4 stores)
- [ ] `curl http://localhost:15173/` → 200
- [ ] `curl http://localhost:18000/api/v1/health` → 200
- [ ] Top nav renders all 8 buttons
- [ ] Each page navigable via top nav
- [ ] All 9 modals functional
- [ ] Page persists after refresh (localStorage)
- [ ] No console errors
- [ ] Git commit + push + PR created

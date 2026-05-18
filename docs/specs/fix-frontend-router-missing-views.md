# Spec: Fix Frontend Router Missing Views and vue-router Resolution Error

## Objective
Fix two frontend startup errors:
1. `Failed to resolve import "vue-router"` — `vue-router` is listed in `package.json` but missing from the Docker container's `node_modules`.
2. `Failed to resolve import "../views/SessionsView.vue"` (and all other `views/` lazy imports) — the `frontend/src/router/index.js` references view files that do not exist.

## Root Cause
`main.js` unconditionally imports and installs `router`. The router uses `createWebHistory()` and lazy-loads view components. However:
- The container does not have `vue-router` installed in `node_modules`.
- The referenced `views/*.vue` files were never created.
- `App.vue` manages all page navigation via a reactive `activePage` ref and `v-if` conditionals; there is no `<router-view>` in the template anywhere.

The router is unused and non-functional. Its presence in `main.js` is the sole source of both errors.

## Fix
Remove the router import and `app.use(router)` from `frontend/src/main.js`. The router file can remain on disk (unimported) but will not affect runtime.

## Tech Stack
Vue 3, Vite 5, vue-router 4 (unused)

## Success Criteria
- `curl http://localhost:15173/` returns 200
- No `Failed to resolve import "vue-router"` in frontend logs after container reload
- No `Failed to resolve import "../views/..."` in frontend logs after container reload
- `docker compose logs frontend --tail 30` shows clean Vite startup

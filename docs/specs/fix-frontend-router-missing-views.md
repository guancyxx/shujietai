# Spec: Fix Frontend Router Missing Views and vue-router Resolution Error

## Status: RESOLVED (router deleted)

## Resolution
The `frontend/src/router/index.js` file has been completely deleted. It referenced
6 non-existent views and was unused — `App.vue` uses manual `activePage` ref +
`v-if` for navigation, and `main.js` does not install vue-routeridis.

Additionally, `frontend/src/SkillGraph.vue` (654 lines, zero imports) was deleted
as dead code.

## Verification
- Frontend Docker build passes (`docker compose build frontend`)
- `curl http://localhost:15173/` returns 200
- Git commit: `chore: delete dead frontend files (router/index.js, SkillGraph.vue)`

# Plan: 2026-05-19 Dispatch follow-up clarification message persistence

## Scope
Frontend-only fix for dispatch chat continuation handover when user sends next-step clarification after terminal status.

## Steps
1. Update dispatch task creation API in frontend composable
   - Add `preserveExistingEvents` option to `createDispatchTask()`.
   - Gate both pre-request and post-subscribe event reset operations with this flag.

2. Update send path for terminal continuation
   - In `useSessionStore.sendMessageToHermes()`, capture whether current dispatch history exists before calling `clearActiveTask()`.
   - Pass `preserveExistingEvents` to `createDispatchTask()` when creating a next round from terminal task.

3. Stabilize live event ordering
   - In `handleTaskEvent`, sort by `created_at` then `seq` for cross-source event consistency.

4. Verification
   - Run frontend Docker production build.
   - Run backend+frontend compose build to ensure no integration regression.
   - Report changed files and verification output.

## Verification commands
```bash
# frontend build (docker-only)
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/frontend:/app" -w /app node:20-alpine \
  sh -lc 'npm ci && npm run build'

# compose build sanity
docker compose build backend frontend
```

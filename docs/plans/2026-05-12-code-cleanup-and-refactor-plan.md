# ShuJieTai Code Cleanup and Refactor Plan (2026-05-12)

## 1. Background and goal

This task executes the task-board item `代码清理和重构`.

Goal for this iteration:
- reduce maintainability cost without changing core behavior
- remove verified dead code/files
- keep dispatch/chat/task-board main flow unchanged
- complete Docker-based verification after cleanup

Non-goal for this iteration:
- large-scale architecture rewrite
- API contract changes
- UI interaction redesign

## 2. Discovery summary

Current low-risk cleanup candidates found from repository scan:

1) Duplicate backend connector implementation
- `backend/app/connectors/hermes_connector.py` is the active connector (`platform_name = "hermes"`, registered in `registry.py`).
- `backend/app/connectors/hermes_runs_connector.py` contains almost the same implementation but is not registered and not imported by runtime path.
- Search shows no runtime references requiring this duplicate file.

2) Tracked temporary artifact
- `tmp/hermes_v1_models_response.json` is a captured response sample under `tmp/`.
- It is not used by runtime code and should not be version-controlled as source.

## 3. Change plan (low risk -> high risk)

Batch A (low risk, this PR):
1. Remove duplicate unregistered connector file:
   - delete `backend/app/connectors/hermes_runs_connector.py`
2. Remove temporary tracked artifact:
   - delete `tmp/hermes_v1_models_response.json`
3. Prevent re-accumulation of tmp artifacts:
   - update `.gitignore` to ignore `tmp/`
4. Keep behavior unchanged:
   - no change to registered connector map (`registry.py` remains `HermesConnector` only)

Batch B (deferred, higher risk):
- split oversized `frontend/src/App.vue`
- split oversized `frontend/src/style.css`
- endpoint layering cleanup in `backend/app/main.py`

These are intentionally deferred because they require larger regression scope.

## 4. Acceptance criteria for this iteration

1. No runtime import error after deleting duplicate connector file.
2. Connector registry still exposes expected platform behavior.
3. Temporary artifact removed and ignored from future commits.
4. Docker build passes for backend and frontend.
5. Core APIs still healthy (`/api/v1/health`, `/api/v1/task-board`).

## 5. Verification plan

Use Docker-only verification:
1. `docker compose build backend frontend`
2. health smoke:
   - `curl http://localhost:18000/api/v1/health`
   - `curl http://localhost:18000/api/v1/task-board`
3. backend syntax smoke in container:
   - `python -m compileall /app/app`

## 6. Risk and rollback

Risk:
- hidden dependency on deleted duplicate connector file

Mitigation:
- full-text search before deletion
- Docker build + API smoke after deletion

Rollback:
- revert this commit to restore deleted file and tmp artifact

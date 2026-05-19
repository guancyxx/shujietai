# Task Board Platform Normalization

## Objective

Ensure every task-board item and dispatch task has a valid, executable `ai_platform`. The only platform available is `hermes`. Values like `none`, empty string, or unknown platforms must never reach persistence.

## Current State (2026-05-19)

- 84 task-board items: all `ai_platform=hermes`
- 194 dispatch tasks: all `ai_platform=hermes`
- Alembic migration `20260513_0011` already exists (idempotent `none`/empty → `hermes`)
- Backend schema whitelist `VALID_AI_PLATFORMS = ("hermes",)`
- Backend `normalize_platform()` in schemas.py as store-level safety net
- Frontend create/edit forms: `<select>` with only `hermes` option
- Frontend store default: `ai_platform: 'hermes'` in both create and edit forms
- Frontend `openTaskBoardEditModal()` converts `none` → `hermes` on edit

## Design

### Backend (three-layer defense)

1. Schema validation (`TaskBoardCreateRequest.check_ai_platform`): rejects anything not in `VALID_AI_PLATFORMS` at the API boundary with HTTP 422.
2. Schema default: `ai_platform: str = Field(default="hermes", ...)` — when omitted, Pydantic fills in `"hermes"` before validation runs.
3. Store normalization (`normalize_platform`): called in `create_task_board_item` and `update_task_board_item`. Maps `none`/empty to `hermes` as idempotent safety net for store-mediated writes (including migration/backfill scripts that use store APIs). Direct DB writes bypass this layer and must be controlled through operational audits/backfills.

### Frontend

- Create modal: `<select>` with single `<option value="hermes">hermes</option>`. No `none` option exposed.
- Edit modal: same single-option select.
- Store state (create): `taskBoardCreateForm` defaults `ai_platform` to `'hermes'`, and `resetTaskBoardCreateForm()` clears it back to `'hermes'`.
- Store state (edit): `taskBoardEditForm` also uses `'hermes'` as its default/populated platform value, but there is no corresponding edit-form reset on close; closing the edit modal clears only the edit id and leaves edit form state until the next open.
- `openTaskBoardEditModal()`: if loaded item has `ai_platform=none` or falsy, normalizes to `'hermes'` before populating the form.
- `startConversationFromTask()`: treats `none` as `hermes` when starting dispatch.
- `buildTaskSystemPrompt()`: treats `none` as `hermes` in the system prompt.

### Data migration

`20260513_0011_normalize_ai_platform_none_to_hermes.py` is idempotent:

```sql
UPDATE task_board_items SET ai_platform = 'hermes'
 WHERE LOWER(ai_platform) IN ('none', '') OR ai_platform IS NULL;

UPDATE dispatch_tasks SET ai_platform = 'hermes'
 WHERE LOWER(ai_platform) IN ('none', '') OR ai_platform IS NULL;
```

Downgrade is a deliberate no-op (cannot restore original `none` assignments).

## Acceptance Criteria

1. No task-board item or dispatch task has `ai_platform=none` / empty / null.
2. `POST /api/v1/task-board` without `ai_platform` field returns `ai_platform: "hermes"`.
3. `POST /api/v1/task-board` with `ai_platform: "none"` returns HTTP 422.
4. Frontend create/edit forms show only `hermes` in platform dropdown.
5. Docker build passes; API smoke confirms zero `none` items.
6. Alembic migration `20260513_0011` is applied and idempotent.
7. Regression test covers: default platform, `none` rejection, `normalize_platform` edge cases.

## Verification Commands

```bash
# Audit persisted rows: all task-board items (including archived) and all dispatch tasks
docker exec shujietai-backend python -c "
import sqlite3

conn = sqlite3.connect('/app/data/shujietai.db')
cur = conn.cursor()
invalid = \"ai_platform IS NULL OR TRIM(ai_platform) = '' OR LOWER(TRIM(ai_platform)) = 'none'\"

task_board_invalid = cur.execute(
    f'SELECT COUNT(*) FROM task_board_items WHERE {invalid}'
).fetchone()[0]
dispatch_invalid = cur.execute(
    f'SELECT COUNT(*) FROM dispatch_tasks WHERE {invalid}'
).fetchone()[0]

print(f'task_board_items none/empty/null: {task_board_invalid}')
print(f'dispatch_tasks none/empty/null: {dispatch_invalid}')
print(f'total none/empty/null: {task_board_invalid + dispatch_invalid}')
"

# Test default platform on create
curl -s -X POST http://localhost:18000/api/v1/task-board \
  -H 'Content-Type: application/json' \
  -d '{"name":"regression-test"}' | python3 -c "
import json, sys; d=json.load(sys.stdin)
assert d.get('ai_platform')=='hermes', f'FAIL: {d.get(\"ai_platform\")}'
print('PASS: default=hermes')"

# Test none rejection
curl -s -X POST http://localhost:18000/api/v1/task-board \
  -H 'Content-Type: application/json' \
  -d '{"name":"test","ai_platform":"none"}' \
  -w '\n%{http_code}' | python3 -c "
import sys
payload = sys.stdin.read().rstrip('\n')
if '\n' not in payload:
    raise AssertionError(f'FAIL: unexpected curl output format: {payload!r}')
body, status = payload.rsplit('\n', 1)
assert status == '422', f'FAIL: expected 422, got {status}. body={body}'
print('PASS: none rejected with 422')"

# Run backend tests
docker exec shujietai-backend python -m pytest tests/test_sqlalchemy_store.py -v
```

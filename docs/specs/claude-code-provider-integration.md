# Claude Code Provider Integration Specification

## Objective

Integrate Claude Code as the second AI provider under ShuJieTai's Dispatch Orchestration Layer (ADR-0004), making it the primary execution platform for coding tasks while Hermes remains available for conversational and non-coding workflows.

## Technology Stack

| Layer | Component | Notes |
|-------|-----------|-------|
| Dispatch | `StreamingAIConnector` interface | Same contract as HermesRunsConnector |
| AI CLI | `claude` (Anthropic CLI) | Runs on host, spawned as subprocess |
| Execution mode | Print mode (`claude -p`) | Non-interactive, exits when done |
| Output format | `--output-format stream-json` | NDJSON, one JSON object per line |
| Isolation | Git worktree | `<repo>/.worktrees/claude-code/<task_id>` |
| Transport | asyncio subprocess | stdout streaming, SIGTERM on cancel |
| Storage | `dispatch_tasks` + `dispatch_events` | Same tables, same event types |

## Contracts

### Connector Interface

Claude Code must implement the existing `StreamingAIConnector` from `backend/app/connectors/ai_base.py`:

```python
class ClaudeCodeConnector:
    platform_name = "claude-code"

    async def stream_completion(
        self, messages: list[dict[str, str]], config: dict
    ) -> AsyncIterator[dict]:
        """Yield: {"type": "content", "content": str}
                  {"type": "tool_call", "function_name": str, "function_args_delta": str, "index": int, "id": str}
                  {"type": "finish", "finish_reason": str, "usage": dict}
                  {"type": "error", "error": str}"""
```

Registration in `registry.py`:

```python
from app.connectors.claude_code_connector import ClaudeCodeConnector
register_connector(ClaudeCodeConnector())
```

Post-registration verification: `list_platforms()` must return `["hermes", "claude-code"]`.

### CLI Invocation

```bash
claude -p "$(cat prompt.md)" \
  --output-format stream-json \
  --verbose \
  --max-turns 20 \
  --allowedTools "Read,Edit,Write,Bash(git *),Bash(docker *),Bash(python3 *)"
```

CLI flags contract:

| Flag | Purpose | Default |
|------|---------|---------|
| `-p` | Non-interactive print mode, exit when done | — |
| `--output-format stream-json` | NDJSON events, parseable in Python | — |
| `--verbose` | Full turn-by-turn output including tool use | — |
| `--max-turns` | Prevents runaway loops | 20 (configurable) |
| `--allowedTools` | Restricts tool permissions | Configurable per task |

`--dangerously-skip-permissions` is NOT used for MVP — `allowedTools` provides safer scoping.

### Event Mapping

Claude Code stream-json events mapped to dispatch event types:

| Claude Code stream-json event | Dispatch event_type | Payload shape |
|---|---|---|
| `assistant` text delta | `content_delta` | `{"role": "assistant", "content": "..."}` |
| `tool_use` (start) | `tool_call` | `{"name": "...", "input": {...}}` |
| `tool_result` | `tool_call` | `{"name": "...", "result_summary": "..."}` |
| final `result` (subtype=success) | `completed` | `{"summary": "...", "session_id": "...", "cost_usd": 0.0, "duration_ms": 0}` |
| final `result` (subtype=error_max_turns) | `error` | `{"reason": "max_turns_reached", "detail": "..."}` |
| process exit != 0 | `error` | `{"reason": "process_error", "detail": "..."}` |
| user cancel (SIGTERM) | `cancelled` | `{"reason": "user_cancelled"}` |

Parsing rules:
- Parse NDJSON line by line
- Unknown/unexpected event types → log as raw event, continue (no crash)
- `content_delta` payload MUST include `role` field — frontend merge logic treats each chunk as separate bubble without it

## Structure

### Files

```
backend/app/connectors/
  ai_base.py                  # Existing: StreamingAIConnector base class
  hermes_connector.py         # Existing
  claude_code_connector.py    # NEW: ClaudeCodeConnector class
  registry.py                 # Modified: register ClaudeCodeConnector

backend/app/services/
  dispatch_worker.py          # Modified: route ai_platform="claude-code" to new connector

frontend/src/
  views/TaskBoardPage.vue     # Modified: add claude-code option to platform dropdown

backend/.env                  # Modified: add CLAUDE_CODE_* variables

.claude/settings.json         # NEW: deny list for security boundary
```

### Data Model

No new tables. Reuse existing `dispatch_tasks` and `dispatch_events`.

`dispatch_tasks.payload_json` extension for Claude Code tasks:

```json
{
  "provider": "claude-code",
  "task_type": "coding",
  "worktree_path": "/home/guancy/workspace/shujietai/.worktrees/claude-code/dt_xxx",
  "branch": "ai/claude-code/dt_xxx-feature",
  "claude_session_id": "uuid",
  "verification_status": "pending"
}
```

### Config / Env

Backend `.env` additions:

```
CLAUDE_CODE_ENABLED=true
CLAUDE_CODE_DEFAULT_MODEL=sonnet
CLAUDE_CODE_MAX_TURNS=20
CLAUDE_CODE_MAX_BUDGET_USD=
```

### Frontend Provider Selection

Dropdown values for `aiPlatform`:

```
{ value: "hermes", label: "Hermes Agent" }
{ value: "claude-code", label: "Claude Code" }
{ value: "none", label: "手动任务" }
```

New coding tasks default to `"claude-code"`. Existing tasks preserve their `ai_platform`.

## Code Style

- Connector class follows established `StreamingAIConnector` pattern (see `hermes_connector.py`)
- `platform_name` uses hyphen (`"claude-code"`), matches frontend `aiPlatform` exactly
- NDJSON parsing: one line at a time, defensive JSON parse, unknown keys logged and skipped
- Subprocess management: `asyncio.create_subprocess_exec`, stdout pipe, SIGTERM on cancel, SIGKILL after grace period
- Worktree operations: `_ensure_worktree()` idempotent (checks `wt_dir.is_dir()` and reuses)
- Prompt assembly: inject worktree path, deny rules, and project context into the prompt sent to Claude Code
- Error handling: connector init checks `claude --version`, fails fast if not installed

## Testing

### Unit Tests

- `test_claude_code_connector.py`: NDJSON parsing, event mapping, error handling
- Mock `asyncio.create_subprocess_exec` to simulate Claude Code output streams
- Test malformed JSON lines, unknown event types, timeout scenarios

### Integration Tests

- Worktree creation and cleanup
- End-to-end: real `claude -p` invocation with a trivial prompt ("write a hello.py file")
- Cancel via SIGTERM, verify worktree preserved

### Smoke Tests

- `POST /api/v1/dispatch` with `ai_platform=claude-code` → task completes
- Verify `dispatch_events` contain expected event types
- Verify frontend renders Claude Code tool calls and content deltas
- Verify worktree exists and contains expected output

## Boundaries

### IN Scope (MVP)

1. Print mode subprocess execution (`claude -p`)
2. stream-json NDJSON parsing with all listed event types
3. Worktree isolation per task
4. Cancel via SIGTERM with worktree preservation
5. Security: `.claude/settings.json` deny list + prompt-enforced rules
6. Config: `CLAUDE_CODE_*` env variables
7. Frontend: `claude-code` option in platform dropdown
8. Registry: connector registration and `list_platforms()` verification

### OUT of Scope (MVP)

1. Interactive mode / TUI — print mode only
2. Dialog handling / `await_input` for Claude Code — Hermes already handles this
3. Multi-repo worktree — single repo per task
4. Budget enforcement beyond `--max-turns` — `CLAUDE_CODE_MAX_BUDGET_USD` env var defined but not enforced
5. Claude Code installation — assumed present on host (`claude` CLI)
6. Container-based Claude Code execution — subprocess only
7. Post-completion PR creation — task completes with verification_status=pending, PR creation is manual

### Hard Boundaries (Never)

- No `--dangerously-skip-permissions`
- No production `.env` modification
- No `docker compose down -v` or `rm -rf` from Claude Code
- No `git push` or PR creation from Claude Code
- No writing outside the task's worktree

## Security

### Deny List (`.claude/settings.json`)

```json
{
  "permissions": {
    "deny": [
      "Read(.env)",
      "Read(.env.*)",
      "Read(**/id_rsa)",
      "Bash(rm -rf *)",
      "Bash(docker compose down -v*)",
      "Bash(git push --force*)"
    ]
  }
}
```

### Prompt-Enforced Rules

Injected into every prompt sent to Claude Code:
- Work only inside the current git worktree
- Use Docker/Compose for build/test/migration/seed
- Do NOT modify production `.env`
- Do NOT run `docker compose up` from worktree (fixed container_name collision)
- Do NOT `git push` or create PRs
- Keep specs/docs in git
- At the end, provide: files changed, verification run, remaining risks, suggested PR title/body

## Error Modes

| Failure | Behavior |
|---------|----------|
| `claude` not installed | Connector init check: `claude --version` → fail fast with clear error |
| Auth failure | Claude Code exits non-zero → connector catches, yields `{"type": "error"}` |
| Malformed JSON line | Parser logs line, skips, continues — does not crash |
| max_turns reached | `result.subtype = "error_max_turns"` → dispatch event `error` |
| Process timeout | SIGTERM, then SIGKILL after 30s grace period → `error` event |
| Docker network pool exhaustion | Documented pitfall: `docker network prune -f` before compose from worktree |

## Acceptance Criteria

1. `POST /api/v1/dispatch` with `ai_platform=claude-code` creates a dispatch task that completes successfully
2. All seven event types from the event mapping table are produced and rendered in the frontend
3. Worktree is created under `<repo>/.worktrees/claude-code/<task_id>`
4. Cancel (SIGTERM) preserves worktree, task status becomes `cancelled`
5. Security deny list is active: `.env` reads, `rm -rf`, `docker compose down -v` are blocked
6. Frontend platform dropdown includes `claude-code` option
7. `list_platforms()` returns `["hermes", "claude-code"]`
8. `claude` CLI absence produces a clear, early error (not a cryptic subprocess crash)
9. Docker build passes; backend tests pass; smoke test confirms end-to-end flow

## Pitfalls

1. `platform_name` mismatch: `"claude-code"` (hyphen) in both connector and frontend. Underscore causes silent registry miss.
2. Missing `--max-turns`: without it, `claude -p` can loop indefinitely.
3. `docker compose up` from worktree: fixed container names collide with primary checkout. Prohibited by prompt + settings.
4. Events API default limit 200: long Claude Code tasks can produce 200+ events. Always use `?limit=2000` when loading history.
5. Wrong working directory: worktree must be the cwd when spawning `claude -p`. Verify with `os.chdir(worktree_path)` before subprocess.
6. Docker network pool exhaustion: each worktree compose creates a named network. After several accumulate, Docker may exhaust pools. Fix: `docker network prune -f`.
7. `git commit` in worktrees requires author identity: set `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_COMMITTER_NAME`, `GIT_COMMITTER_EMAIL` in subprocess env.
8. Claude CLI may be pre-installed on host: connector init test must use `shutil.which("claude")` to detect and adapt.

## Success Standards

1. A coding task dispatched with `ai_platform=claude-code` completes within configurable `--max-turns` limit
2. Claude Code output (tool calls, content, final result) is visible in the ShuJieTai chat timeline with correct event types
3. Cancelling a running Claude Code task stops the subprocess within 5 seconds and preserves the worktree
4. Zero production `.env` or system files are modified by Claude Code
5. Existing Hermes tasks are unaffected — connector routing is based on `ai_platform` field

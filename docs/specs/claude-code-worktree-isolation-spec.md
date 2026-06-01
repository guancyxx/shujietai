# Claude Code Provider Integration — Specification (Worktree Isolation)

## Objective

Add per-task git worktree isolation for every Claude Code dispatch. Each dispatch
task gets its own checkout so Claude Code never touches the canonical working copy.

## Scope (this slice)

Only the worktree-isolation layer — the Claude Code CLI invocation is upstream (T4).

1. Create a git worktree at `.worktrees/claude-code/<task_id>` inside the project repo.
2. Branch name: `ai/claude-code/<task_id>-<slug>`.
3. Copy `.env`, `.worktreeinclude`, `AGENTS.md`, `CLAUDE.md` into the worktree.
4. Set the worktree as the execution cwd for the Claude Code subprocess.

## Non-goals

- `claude` CLI invocation itself (T4 upstream).
- Frontend provider dropdown.
- `--max-turns`, `--allowedTools` tuning.
- Auto PR creation.

## Commands

```bash
# Verify worktree exists
git worktree list | grep ".worktrees/claude-code/<task_id>"
ls -d .worktrees/claude-code/<task_id>
```

## Project Structure (new / changed files)

```
backend/app/connectors/
  claude_code_connector.py    ← new: worktree setup + stub stream_completion
backend/app/connectors/
  registry.py                 ← register ClaudeCodeConnector
backend/app/schemas.py        ← add "claude-code" to VALID_AI_PLATFORMS
backend/tests/
  test_claude_code_connector.py  ← connector tests
docs/specs/
  claude-code-worktree-isolation-spec.md  ← this file
```

## Event Mapping

The stub connector yields a single `error` chunk when Claude Code is not
installed; the real stream-json mapping lives in the upstream T4
implementation.

## Success Criteria

1. `POST /api/v1/dispatch` with `ai_platform: "claude-code"` creates a running task.
2. `git worktree list` shows a per-task worktree under `.worktrees/claude-code/<task_id>`.
3. Branch `ai/claude-code/<task_id>-<slug>` exists in the repo.
4. `.env` and project config files are present in the worktree.
5. Dispatch events include a clear error when Claude Code CLI is missing.
6. `list_platforms()` returns `["hermes", "claude-code"]`.

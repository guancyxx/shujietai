# ADR-0005: Claude Code as Coding Provider via Dispatch Layer

## Status

Proposed

## Date

2026-06-01

## Context

ShuJieTai currently has a single AI provider — Hermes Agent — connected through the Dispatch Orchestration Layer (ADR-0004). Hermes handles all task types: coding, research, conversation, and operations. However, coding tasks present distinct requirements that differ from conversational tasks:

- Coding tasks need filesystem access (read, write, edit files)
- Coding tasks benefit from tight git integration (branch management, diff generation)
- Coding tasks need build-system awareness (Docker, tests, linters)
- Coding tasks are inherently scoped to a repository and should be isolated from the primary checkout

Claude Code is purpose-built for these requirements. It provides a non-interactive print mode (`claude -p`) that reads a prompt, executes tool calls (read, write, edit, bash), and exits with a summary — all via NDJSON stream-json output that is trivially parseable by an existing `StreamingAIConnector` adapter.

The alternative is to continue routing all coding tasks through Hermes, which does not natively support git worktree isolation and treats coding as a general conversational problem. As the volume and complexity of coding tasks grows, this becomes increasingly inefficient.

## Decision

We will integrate Claude Code as a second AI provider under the Dispatch Orchestration Layer:

1. Claude Code will run in **print mode** (`claude -p`), not interactive mode. This decision trades interactive refinement (TUI, multi-turn dialog) for deterministic termination, structured output, and simple subprocess management. Print mode guarantees the process exits when done — no dangling sessions, no TUI escape-sequence parsing.

2. Claude Code will **NOT run inside a Docker container**. It runs as a subprocess on the host, spawned by the backend connector via `asyncio.create_subprocess_exec`. Rationale:
   - Claude Code requires the `claude` CLI with Anthropic auth, which is already configured on the host
   - Running inside a container would require mounting the host's auth credentials and Claude CLI binary, adding complexity without security benefit
   - File isolation is achieved through git worktrees, not container boundaries — the worktree is the security perimeter

3. All Claude Code invocations will go through the **Dispatch Orchestration Layer**, not a direct HTTP endpoint. This ensures:
   - Same event types, WebSocket broadcasting, and cancellation mechanics as Hermes tasks
   - Same `dispatch_tasks` + `dispatch_events` persistence model
   - Same frontend rendering pipeline (status, content_delta, tool_call, completed, error, cancelled events)
   - Same frontend restore-on-refresh behavior

4. Each Claude Code task creates a **temporary git worktree**. This isolates file writes from the primary checkout, prevents container-name collisions with the running Docker Compose stack, and allows inspection of partial results even after cancellation. The worktree lives at `<repo>/.worktrees/claude-code/<task_id>`.

5. Code changes produced by Claude Code are **reviewed by a human before merging**. Claude Code does not push, create PRs, or modify branches outside its worktree. It produces a final summary with: files changed, verification results, remaining risks, and a suggested PR title/body.

## Alternatives Considered

### A: Continue routing all tasks through Hermes only

- Pros: No new integration surface. Single connector to maintain.
- Cons: Hermes lacks native worktree isolation. Coding tasks compete with conversational tasks for the same provider. Claude Code's tool-use patterns (Read, Edit, Write, Bash with granular permissions) are purpose-built for coding in a way Hermes's general-purpose toolset is not.

### B: Interactive Claude Code TUI mode

- Pros: Full Claude Code experience with multi-turn refinement, user approval for each tool call.
- Cons: Requires PTY session management, escape-sequence parsing, and an indefinite session lifetime. Dispatch tasks are designed for finite, async execution with explicit status transitions — an indefinite TUI session breaks the state machine model.

### C: Container-based Claude Code execution

- Pros: Stronger isolation boundary. No host dependency on `claude` CLI.
- Cons: Requires shipping Claude CLI + auth inside a Docker image, maintaining that image, and mounting host git repos. The auth credential problem (Anthropic API key or OAuth token) inside containers is non-trivial. Worktree isolation already provides sufficient filesystem safety without the container overhead.

### D: Direct Claude Code endpoint bypassing Dispatch

- Pros: Fewer layers between frontend and Claude Code.
- Cons: Loses all Dispatch benefits: WebSocket broadcasting, event persistence, cancel/recovery semantics, uniform frontend rendering. Creates a second code path that must be maintained in parallel.

## Consequences

- ShuJieTai now has two AI providers (Hermes for general tasks, Claude Code for coding tasks), selected via the `ai_platform` field on task board items
- The `VALID_AI_PLATFORMS` whitelist in the backend must be updated from `("hermes",)` to `("hermes", "claude-code")`
- Frontend platform dropdown gains a "Claude Code" option; new coding tasks default to it
- Security boundary is enforced at two layers: `.claude/settings.json` deny list (filesystem) and prompt-injected rules (behavioral)
- Worktree accumulation becomes an operational concern — periodic cleanup of completed worktrees is needed
- Docker network pool exhaustion risk documented and mitigated with `docker network prune -f` in the pitfall checklist
- Claude Code availability on the host becomes a deployment prerequisite — backend connector fails fast if `claude` CLI is absent
- The existing Hermes connector and all Hermes-specific features are unaffected

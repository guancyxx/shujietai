# ADR 0003: Project creation stores metadata only (no repository clone)

Status: Accepted
Date: 2026-04-29

## Context

Project creation previously attempted to clone the GitHub repository into local workspace during API create flow.

This caused operational coupling and avoidable failures:
- project creation depended on `git` runtime availability;
- network/transient GitHub failures blocked basic metadata CRUD;
- create latency and error surface increased for a non-essential side effect.

User requirement is explicit: backend create flow should only persist project information.

## Decision

1. Remove auto-clone behavior from project create flow.
2. Keep repository URL validation and repository name parsing.
3. Compute deterministic default `local_path` under workspace (`<workspace_root>/<repo_name>`) and store it as metadata only.
4. Keep API response shape unchanged.

## Consequences

Positive:
- Project creation is fast and stable.
- No runtime dependency on `git` command for create API.
- Better separation between metadata management and repository synchronization.

Negative:
- Stored local path may not exist until an explicit clone/sync action is executed by user/tooling.

## Verification

- `docker compose run --rm backend pytest -q`
- `curl -sS -X POST http://127.0.0.1:18000/api/v1/projects ...`
- `curl -sS http://127.0.0.1:18000/api/v1/projects`

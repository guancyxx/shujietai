# ADR 0002: Store system config in database instead of env files

Status: Accepted
Date: 2026-04-29

## Context

Project management UX depends on GitHub repository discovery. The previous implementation persisted `github_token` in an env file and hydrated process environment variables at runtime.

This approach has multiple problems:
- Runtime behavior depends on container-local file paths.
- Config state is not part of the same persistence boundary as application data.
- Multi-instance consistency is harder when config is file-based.

The project already uses SQLAlchemy + Alembic with PostgreSQL as the default store backend.

## Decision

1. Persist system configuration (including `github_token`) in a dedicated database table (`system_configs`).
2. Read token from database in `SystemConfigService`.
3. Pass token to GitHub repository listing flow explicitly, instead of relying on env-file hydration.
4. Keep env token only as a non-persistent fallback for non-SQLAlchemy test/runtime paths.

## Consequences

Positive:
- Configuration persistence is durable and centralized.
- Runtime behavior is independent from container file path quirks.
- Easier future extension for more system config keys.

Negative:
- Adds one migration and one new table.
- Requires DB availability for full config functionality.

## Implementation Notes

- Add `SystemConfigEntity` model and Alembic migration.
- Refactor `SystemConfigService` to use DB session factory when available.
- Keep API shape stable: `GET /api/v1/system/config` and `PUT /api/v1/system/config/github-token`.

## Verification

- `docker compose run --rm backend alembic upgrade head`
- `docker compose run --rm backend pytest -q`
- `curl -sS http://127.0.0.1:18000/api/v1/system/config`
- `curl -sS http://127.0.0.1:18000/api/v1/projects/github/repos`

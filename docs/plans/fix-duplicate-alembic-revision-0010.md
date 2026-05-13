# Plan: Fix Duplicate Alembic Revision 20260513_0010

## Tasks

1. Confirm duplicate revision ids in `backend/alembic/versions`.
2. Rename the ai_platform normalization migration file from `20260513_0010_...` to `20260513_0011_...`.
3. Update the migration docstring metadata:
   - `Revision ID: 20260513_0011`
   - `Revises: 20260513_0010`
4. Update Alembic identifiers:
   - `revision = "20260513_0011"`
   - `down_revision = "20260513_0010"`
5. Verify with Docker:
   - backend image builds
   - `alembic heads` reports a single head
   - `alembic upgrade head` succeeds against the local running PostgreSQL-backed backend container after syncing migration files
6. Commit, push, and open a PR.

## Rollback

Revert the migration file rename and identifier changes. No data migration rollback is required because the normalization UPDATE is idempotent and only changes invalid `ai_platform` values to the canonical `hermes` value.

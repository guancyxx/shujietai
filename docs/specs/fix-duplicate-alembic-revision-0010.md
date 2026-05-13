# Spec: Fix Duplicate Alembic Revision 20260513_0010

## Problem

The Alembic migration graph currently contains two different migration files with the same revision id `20260513_0010`:

- `20260513_0010_task_board_archive_fields.py`
- `20260513_0010_normalize_ai_platform_none_to_hermes.py`

This makes `alembic upgrade head` fail because Alembic cannot build a valid linear migration graph with duplicate revision identifiers.

## Root Cause

Two independent branches introduced migrations using the same timestamp-based revision id. After squash merging both branches, the repository ended up with duplicate revision identifiers pointing to the same parent `20260513_0009`.

## Required Behavior

- The migration graph must contain unique revision ids.
- `alembic heads` must return exactly one head.
- `alembic upgrade head` must succeed in the local Docker/PostgreSQL environment.
- The archive fields migration remains revision `20260513_0010`.
- The ai_platform normalization migration becomes the next linear revision `20260513_0011`, with `down_revision = "20260513_0010"`.
- The ai_platform normalization migration remains idempotent so it is safe when invalid values have already been cleaned up.

## Compatibility Notes

Existing local environments may already have `alembic_version = 20260513_0010`. After this fix, Alembic interprets that value as the archive-fields migration and applies `20260513_0011` next. That is safe because the 0011 migration only performs idempotent UPDATE statements.

## Out of Scope

- No application schema/model changes.
- No frontend behavior changes.
- No data deletion.

# Session List Descending Order Fix

## Status
Implemented

## Date
2026-05-11

## Context
The chat page conversation list is expected to show the most recently active sessions first. Users report the list is still not ordered in descending time.

Current frontend logic in `frontend/src/App.vue` sorts sessions by `updated_at || created_at`, but the backend session summary contract currently exposes `started_at` and `ended_at` rather than explicit `created_at` and `updated_at`. This likely causes the frontend sort key to be empty or inconsistent.

## Objective
Restore deterministic descending ordering for the conversation list so the newest or most recently active sessions always appear at the top.

## Scope
- Inspect the `/api/v1/sessions` response contract and actual store implementation.
- Align backend and frontend on one canonical recency field.
- Keep selection behavior unchanged except for choosing from the correctly sorted list.
- Update repository docs to record the contract.

## Non-Goals
- Redesign session list UI.
- Add pagination or search changes.
- Change session persistence semantics beyond ordering metadata.

## Decision
Use backend-provided `updated_at` as the canonical session recency field, with `created_at` as fallback. Keep frontend defensive sorting, but ensure the API contract actually includes the fields it sorts on.

## Implementation Plan
1. Verify actual `/api/v1/sessions` payload and store serialization path.
2. Extend session summary schema/store mapping to expose `created_at` and `updated_at` consistently.
3. Update frontend sorting and selection code to use the sorted array, not the raw fetch order.
4. Build and verify the frontend and backend.

## Success Criteria
- `/api/v1/sessions` returns `created_at` and `updated_at` for each session summary.
- Chat page conversation list renders with most recent sessions first.
- Initial/default selection also follows the sorted order.
- Frontend build passes.

## Verification
- Inspect API response for returned ordering fields.
- Run project build commands.
- Re-check the first several sessions and confirm descending timestamps.

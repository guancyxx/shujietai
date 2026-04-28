# ADR 0001: MVP store default and connector extension path

Status: Accepted (updated)
Date: 2026-04-28

## Context

ShuJieTai MVP must remain runnable with stable canonical APIs while improving runtime durability and ingest reliability.

Initial MVP planning used an in-memory store to accelerate early delivery. After baseline delivery, SQLAlchemy persistence and Alembic migrations were implemented, and retry/DLQ reliability became part of the required runtime baseline.

Connector strategy still requires extension readiness for future platforms while keeping current implementation scope controlled.

## Decision

1. Use SQLAlchemy (PostgreSQL) as the default runtime store backend.
2. Keep in-memory store implementation only as fallback for isolated tests and emergency local fallback scenarios.
3. Keep Hermes as the only active connector implementation in current MVP runtime.
4. Preserve connector extension interfaces so future connectors (for example OpenClaw) can be added without changing session core and cockpit contracts.
5. Keep Alembic as mandatory schema evolution mechanism.
6. Keep retry + DLQ as required ingest reliability baseline.

## Consequences

Positive:
- Runtime data durability is available by default.
- Schema changes are versioned and operable.
- Ingest failure handling is explicit and replayable.
- Connector architecture stays open for future platform growth.

Negative:
- Operational complexity is higher than pure in-memory mode.
- Retry worker is currently in-process and depends on backend process liveness.
- OpenClaw is not yet delivered, so cross-platform runtime coverage remains incomplete.

## Implementation notes

Current runtime facts:
- Default store backend is SQLAlchemy (`SESSION_STORE_BACKEND=sqlalchemy`).
- Connector endpoints delivered for Hermes webhook/chat.
- DLQ replay supports operator identity (`x-replayed-by`) and force replay (`{"force": true}`).
- Replay audit fields are persisted on DLQ rows (`replay_count`, `replayed_at`, `replayed_by`).

## Deferred items

1. OpenClaw connector implementation and contract fixtures
2. Security middleware hardening beyond current baseline
3. Retry worker externalization to dedicated queue workers
4. Optional append-only replay audit history table

## Verification

Reference verification commands:
- `docker compose run --rm backend pytest -q`
- `docker compose run --rm backend alembic upgrade head`
- `curl -sS http://127.0.0.1:18000/api/v1/health`
- `curl -sS http://127.0.0.1:18000/api/v1/dlq`

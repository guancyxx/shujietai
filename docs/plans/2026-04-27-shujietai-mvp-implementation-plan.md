# ShuJieTai MVP Implementation Plan (Updated Baseline)

Goal: Keep a runnable Hermes-first cockpit MVP with stable contracts, SQLAlchemy default persistence, Alembic migration discipline, and retry/DLQ reliability baseline.

Architecture: FastAPI backend + Vue 3 frontend, orchestrated by Docker Compose with PostgreSQL and Redis.

Tech Stack: FastAPI, Uvicorn, Pydantic, SQLAlchemy, Alembic, Pytest, Vue 3, Vite, Docker Compose, PostgreSQL, Redis.

---

## Phase 0: Scope lock (current)

In scope now:
- Hermes connector runtime implementation
- Canonical ingest/query/cockpit APIs
- SQLAlchemy default persistence path
- Alembic baseline migrations
- Retry + DLQ pipeline and replay operations

Out of scope now:
- OpenClaw connector runtime implementation
- Security hardening expansion beyond current baseline

---

## Task 1: Baseline environment and contracts

Objective: Keep one-command local startup and stable API surface.

Files:
- `docker-compose.yml`
- `.env.example`
- `backend/app/main.py`
- `backend/app/schemas.py`

Acceptance:
- Compose stack starts with backend/frontend/postgres/redis
- API routes match documented current surface

Verify:
- `docker compose up -d --build`
- `docker compose ps`
- `curl -sS http://127.0.0.1:18000/api/v1/health`

---

## Task 2: Persistence and migration baseline

Objective: Ensure SQLAlchemy default path and migration operability.

Files:
- `backend/app/services/store_factory.py`
- `backend/app/services/sqlalchemy_store.py`
- `backend/alembic.ini`
- `backend/alembic/env.py`
- `backend/alembic/versions/20260428_0001_baseline_schema.py`
- `backend/alembic/versions/20260428_0002_dlq_replay_audit_fields.py`

Acceptance:
- Default store backend resolves to SQLAlchemy
- Alembic upgrade and downgrade commands are executable

Verify:
- `docker compose run --rm backend alembic upgrade head`
- `docker compose run --rm backend alembic downgrade base`

---

## Task 3: Reliability baseline (retry + DLQ)

Objective: Keep ingest failures recoverable and observable.

Files:
- `backend/app/services/ingest_retry_service.py`
- `backend/app/services/retry_worker.py`
- `backend/app/main.py`
- `backend/app/schemas.py`

Acceptance:
- Failed ingest enters retry path
- Exceeded retries moves to DLQ
- Replay endpoint supports default and force behavior
- Replay audit fields are updated

Verify:
- `curl -sS http://127.0.0.1:18000/api/v1/dlq`
- `curl -sS -X POST http://127.0.0.1:18000/api/v1/dlq/<dlq_id>/replay`
- `curl -sS -X POST http://127.0.0.1:18000/api/v1/dlq/<dlq_id>/replay -H 'Content-Type: application/json' -d '{"force":true}'`

---

## Task 4: Connector extension guardrail

Objective: Keep connector abstraction stable while Hermes path remains active.

Files:
- `backend/app/connectors/base.py`
- `backend/app/connectors/registry.py`
- `backend/app/connectors/hermes.py`
- `backend/tests/test_connector_contract_hermes.py`

Acceptance:
- Hermes webhook/chat routes remain functional
- Connector base/registry APIs remain stable for next connector

Verify:
- `docker compose run --rm backend pytest -q`

---

## Task 5: Documentation alignment (this round)

Objective: Remove doc drift and ensure all core docs reflect runtime facts.

Files:
- `README.md`
- `docs/superpowers/specs/2026-04-27-shujietai-mvp-design.md`
- `docs/adr/0001-mvp-store-and-connector-extension.md`
- `docs/status/2026-04-28-project-status.md`
- `docs/status/2026-04-28-implementation-timeline.md`
- `docs/status/2026-04-28-sqlalchemy-cutover-runbook.md`

Acceptance:
- No contradiction on connector scope or persistence default
- Verification commands and ports are consistent

Verify:
- Run doc consistency scan (`OpenClaw delivered`, `in-memory default`) and ensure these claims are not present as delivered facts

---

## Task 6: Next-phase backlog (not executed in this plan)

1. Implement OpenClaw connector and contract tests
2. Upgrade security middleware baseline
3. Externalize retry worker when throughput requires
4. Consider append-only replay audit history for compliance granularity

---

## Execution notes

- Keep commits small and scoped.
- Keep comments in English.
- Keep deferred items explicit in docs.
- Validate compose + tests after service-level changes.

# Spec: ShuJieTai MVP Current Baseline (Updated)

Date: 2026-04-28
Scope: Runtime baseline and documentation alignment after SQLAlchemy cutover

## Assumptions

1. MVP runtime connector implementation remains Hermes-only in this round.
2. Connector extension points must stay stable for future OpenClaw integration.
3. SQLAlchemy + PostgreSQL is the default persistence path in production-like local runs.
4. Retry + DLQ is required reliability baseline for ingest failures.
5. Security hardening beyond workspace-token baseline is intentionally deferred.

## 1) Objective

Build and maintain a runnable multi-platform conversation cockpit MVP with a stable canonical API contract, where:
- current implementation is Hermes-first,
- architecture remains extension-ready,
- persistence and reliability baselines are production-oriented (SQLAlchemy + Alembic + Retry/DLQ),
- documentation reflects actual running behavior, not planned-but-undelivered scope.

Primary users:
- Developers integrating platform connectors
- Operators verifying ingestion reliability and replay flow

Success means:
- One-command Docker Compose startup works
- Backend API + Frontend cockpit are reachable
- Alembic migrations are executable and reversible
- Retry/DLQ behavior is testable and observable through APIs
- Documentation statements match current implementation

## 2) Tech Stack

- Backend: FastAPI, Pydantic, SQLAlchemy, Alembic
- Frontend: Vue 3 + Vite
- Database: PostgreSQL 16
- Cache/Realtime reservation: Redis 7
- Orchestration: Docker Compose
- Test: Pytest

## 3) Commands (single source of truth)

Environment initialization:
- `cp .env.example .env`

Build and start:
- `docker compose up -d --build`

Service status:
- `docker compose ps`

Backend tests:
- `docker compose run --rm backend pytest -q`

Health check:
- `curl -sS http://127.0.0.1:18000/api/v1/health`

Sessions:
- `curl -sS http://127.0.0.1:18000/api/v1/sessions`

DLQ list:
- `curl -sS http://127.0.0.1:18000/api/v1/dlq`

Alembic upgrade:
- `docker compose run --rm backend alembic upgrade head`

Alembic downgrade:
- `docker compose run --rm backend alembic downgrade base`

Alembic roundtrip check:
- `docker compose run --rm backend sh -lc 'DATABASE_URL=sqlite+pysqlite:///tmp/alembic_check.db alembic upgrade head && DATABASE_URL=sqlite+pysqlite:///tmp/alembic_check.db alembic downgrade base && DATABASE_URL=sqlite+pysqlite:///tmp/alembic_check.db alembic upgrade head'`

## 4) Project Structure

- `backend/app/main.py` -> API routes, lifespan, retry loop bootstrap
- `backend/app/schemas.py` -> canonical request/response schemas
- `backend/app/services/store_factory.py` -> store backend selection (default SQLAlchemy)
- `backend/app/services/sqlalchemy_store.py` -> persistence implementation
- `backend/app/services/ingest_retry_service.py` -> retry/DLQ core logic
- `backend/app/services/retry_worker.py` -> retry worker loop
- `backend/alembic/` -> schema migrations
- `frontend/src/App.vue` -> cockpit UI shell
- `docker-compose.yml` -> unified local service orchestration
- `docs/status/` -> delivery status and timeline
- `docs/adr/` -> architectural decision records
- `docs/plans/` -> implementation plans and follow-up work items

## 5) API and Code Style Baseline

Canonical MVP APIs:
- `POST /api/v1/events/ingest`
- `GET /api/v1/sessions`
- `GET /api/v1/sessions/{id}`
- `GET /api/v1/sessions/{id}/timeline`
- `GET /api/v1/board/cockpit?session_id=...`
- `GET /api/v1/health`
- `GET /api/v1/dlq`
- `POST /api/v1/dlq/{dlq_id}/replay`
- `POST /api/v1/connectors/hermes/webhook`
- `POST /api/v1/connectors/hermes/chat`

Style constraints:
- Keep contracts explicit via typed Pydantic models
- Keep connector boundaries stable (`connectors/base.py`, `connectors/registry.py`)
- Keep comments and implementation naming consistent with current runtime behavior
- Document deferred scope explicitly; avoid writing future scope as if already delivered

## 6) Testing Strategy

Test framework:
- Pytest in `backend/tests`

Required test layers:
1. API behavior and contract tests
2. Store behavior tests (factory + persistence restart)
3. Migration tests (upgrade/downgrade roundtrip)
4. Retry and DLQ semantics (enqueue/replay/force replay)
5. Connector contract tests (Hermes path active, extension path preserved)

Entry command:
- `docker compose run --rm backend pytest -q`

Acceptance baseline:
- Full backend test suite passes in containerized environment

## 7) Boundaries

Always do:
- Keep docs aligned with actual runtime behavior
- Verify commands and endpoints before documenting
- Keep deferred scope clearly marked as deferred

Ask first:
- Changing canonical API names or response contracts
- Changing migration history policy or resetting existing revisions
- Enabling security hardening that may alter integration behavior

Never do:
- Claim OpenClaw runtime support as delivered before implementation exists
- Describe SQLAlchemy path as optional fallback when it is the default path
- Remove migration/reliability verification sections from operator docs

## 8) Current Scope Statement

In scope now:
- Hermes connector runtime integration
- SQLAlchemy default runtime store
- Alembic baseline + replay-audit migration
- Retry + DLQ with replay API and audit fields

Deferred now:
- OpenClaw connector implementation
- Security middleware hardening beyond current baseline
- Externalized retry worker infrastructure

## 9) Success Criteria

1. README, ADR, plan, and status docs contain no contradictory claims about connector scope or persistence default.
2. Core commands in docs are executable against current compose stack and port mapping.
3. API list in docs matches `backend/app/main.py` exported endpoints.
4. Deferred items are represented as deferred in all updated docs.
5. New contributors can start, verify, and operate the MVP using docs only.

## 10) Open Questions

1. Should OpenClaw implementation be the immediate next delivery milestone, or should security baseline hardening come first?
2. Should replay history remain row-aggregated, or move to append-only audit events in next phase?
3. Should retry worker be externalized before introducing a second connector?

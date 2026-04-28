# ShuJieTai Implementation Timeline (2026-04-28)

Date: 2026-04-28

## Purpose

This timeline summarizes the delivered increments in execution order, with scope decisions, implementation checkpoints, and verification evidence.

## 0) Scope Decisions Locked

- MVP connector scope: Hermes only (OpenClaw deferred)
- Persistence baseline: SQLAlchemy required as default runtime path
- Migration baseline: Alembic required
- Reliability baseline: retry + DLQ required
- Security hardening: explicitly deferred in this round

## 1) Persistence Formalization

### 1.1 SQLAlchemy cutover

Delivered:
- Default store backend switched to SQLAlchemy
- Memory store retained for fallback and test isolation

Key artifacts:
- `backend/app/services/store_factory.py`
- `backend/app/services/sqlalchemy_store.py`
- `backend/tests/test_store_factory.py`
- `backend/tests/test_persistence_restart.py`

### 1.2 Schema evolution with Alembic

Delivered migrations:
- `20260428_0001`: baseline schema
- `20260428_0002`: DLQ replay audit fields (`replay_count`, `replayed_at`, `replayed_by`)

Key artifacts:
- `backend/alembic.ini`
- `backend/alembic/env.py`
- `backend/alembic/versions/20260428_0001_baseline_schema.py`
- `backend/alembic/versions/20260428_0002_dlq_replay_audit_fields.py`
- `backend/tests/test_alembic_migration.py`

## 2) Reliability Formalization (Retry + DLQ)

### 2.1 Retry pipeline

Delivered:
- Failed ingest enqueue path
- Retry processing state machine with backoff
- In-process retry worker loop
- Configurable retry controls via env vars

Key artifacts:
- `backend/app/services/ingest_retry_service.py`
- `backend/app/services/retry_worker.py`
- `backend/tests/test_ingest_retry_enqueue.py`
- `backend/tests/test_ingest_retry_service.py`

### 2.2 DLQ operations and audit semantics

Delivered APIs:
- `GET /api/v1/dlq`
  - supports `limit`, `only_unreplayed`, `platform`, `since`
- `POST /api/v1/dlq/{dlq_id}/replay`
  - supports optional `x-replayed-by` header
  - supports optional body `{ "force": true }`

Behavior:
- Replay success updates audit fields on the same DLQ row
- Replay does not delete DLQ row
- Already replayed records require `force=true` for replay rerun

Key artifacts:
- `backend/app/main.py`
- `backend/app/schemas.py`
- `backend/tests/test_dlq_api.py`
- `backend/tests/test_ingest_retry_replay_behavior.py`

## 3) Connector Architecture Guardrail

Delivered:
- Hermes connector contract remains active
- Connector extension points preserved for future connectors

Key artifacts:
- `backend/app/connectors/base.py`
- `backend/app/connectors/hermes.py`
- `backend/app/connectors/registry.py`
- `backend/tests/test_connector_contract_hermes.py`

## 4) Operational & Runbook Updates

Updated docs:
- `README.md`
- `docs/status/2026-04-28-project-status.md`
- `docs/status/2026-04-28-sqlalchemy-cutover-runbook.md`

Runbook now includes:
- Alembic migration and roundtrip checks
- DLQ list filters query examples
- Replay with operator identity
- Forced replay request example

## 5) Verification Snapshot

Validation commands used:
- `docker compose run --rm backend pytest -q`
- `docker compose up -d --build backend`
- `docker compose run --rm backend alembic upgrade head`
- `docker compose run --rm backend alembic current`
- `curl http://127.0.0.1:18000/api/v1/health`
- `curl http://127.0.0.1:18000/api/v1/dlq`

Latest test status in this round:
- `34 passed, 1 warning`

## 6) Deferred Items

Still deferred by decision:
- OpenClaw implementation
- Security baseline hardening

Potential next layer:
- Append-only replay history table (if audit/compliance granularity is required)
- Retry worker externalization under higher throughput

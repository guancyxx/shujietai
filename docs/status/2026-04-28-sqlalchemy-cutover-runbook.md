# ShuJieTai SQLAlchemy Cutover Runbook

Date: 2026-04-28

## Goal

Run backend with SQLAlchemy as default store, apply Alembic schema, and verify persistence plus retry/DLQ baseline behavior.

## Scope in this round

In scope:
- SQLAlchemy default runtime
- Alembic baseline migration
- Retry + DLQ pipeline

Out of scope:
- OpenClaw connector implementation
- Security middleware hardening

## Preconditions

- Compose stack is available
- postgres container is healthy
- backend image includes sqlalchemy, psycopg2-binary, alembic

## Configuration

In `.env`, set:

SESSION_STORE_BACKEND=sqlalchemy
DATABASE_URL=postgresql+psycopg2://shujietai:<password>@postgres:5432/shujietai
INGEST_RETRY_ENABLED=true
INGEST_MAX_RETRIES=3
INGEST_RETRY_DELAYS=1,3,10
INGEST_RETRY_LOOP_INTERVAL_SECONDS=1

## Cutover Steps

1) Rebuild backend image

docker compose build backend

2) Apply migration

docker compose run --rm backend alembic upgrade head

3) Restart backend with updated env

docker compose up -d backend

4) Verify backend health

curl -sS http://127.0.0.1:18000/api/v1/health

5) Run backend tests

docker compose run --rm backend pytest -q

## Persistence Sanity Check

1) Ingest one event:

curl -sS -X POST http://127.0.0.1:18000/api/v1/events/ingest -H 'Content-Type: application/json' -d '{"platform":"hermes","event_id":"evt_persist_1","event_type":"message_created","external_session_id":"persist_sess_1","title":"Persist Check","payload_json":{"source":"runbook"},"message":{"role":"user","content":"hello"}}'

2) List sessions and record returned session id.

3) Restart backend container:

docker compose restart backend

4) Query sessions again and confirm the session is still present.

## Alembic Roundtrip Check

docker compose run --rm backend sh -lc 'DATABASE_URL=sqlite+pysqlite:///tmp/alembic_check.db alembic upgrade head && DATABASE_URL=sqlite+pysqlite:///tmp/alembic_check.db alembic downgrade base && DATABASE_URL=sqlite+pysqlite:///tmp/alembic_check.db alembic upgrade head'

## Retry + DLQ Sanity Check

- Trigger an ingest failure (temporary DB issue or simulated store error in tests)
- Confirm retry queue receives record
- Confirm retry attempts follow configured backoff
- Confirm record moves to dead_letter_events after max retries

Inspect dead letters:

curl -sS http://127.0.0.1:18000/api/v1/dlq

Inspect unreplayed dead letters for a platform since a timestamp:

curl -sS 'http://127.0.0.1:18000/api/v1/dlq?only_unreplayed=true&platform=hermes&since=2026-01-01T00:00:00Z'

Replay one dead letter by id:

curl -sS -X POST http://127.0.0.1:18000/api/v1/dlq/<dlq_id>/replay

Replay one dead letter and record operator identity:

curl -sS -X POST http://127.0.0.1:18000/api/v1/dlq/<dlq_id>/replay -H 'x-replayed-by: ops-user'

Force replay for an already replayed record:

curl -sS -X POST http://127.0.0.1:18000/api/v1/dlq/<dlq_id>/replay -H 'Content-Type: application/json' -d '{"force":true}'

## Rollback

If issues occur:

1) Set SESSION_STORE_BACKEND=memory in `.env`
2) Restart backend:

docker compose up -d backend

3) Verify health endpoint

## Notes

- Current retry worker is in-process and lightweight by design
- Future migration may move retry execution to dedicated queue workers while preserving existing contracts

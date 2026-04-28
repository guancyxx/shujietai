# ShuJieTai SQLAlchemy Cutover Runbook

Date: 2026-04-28

## Goal

Switch backend session store from in-memory mode to SQLAlchemy mode under Docker Compose, then verify basic persistence behavior and API health.

## Preconditions

- Compose stack is available
- postgres container is healthy
- backend image includes sqlalchemy and psycopg2-binary

## Configuration

In `.env`, set:

SESSION_STORE_BACKEND=sqlalchemy
DATABASE_URL=postgresql+psycopg2://shujietai:<password>@postgres:5432/shujietai

Notes:
- Use compose service name `postgres` as database host.
- Keep API contracts unchanged; this is storage-backend only.

## Cutover Steps

1) Rebuild backend image

`docker compose build backend`

2) Restart backend with updated env

`docker compose up -d backend`

3) Verify backend health

`curl -sS http://127.0.0.1:18000/api/v1/health`

4) Run backend test suite

`docker compose run --rm backend pytest -q`

## Persistence Sanity Check

1) Ingest one event:

`curl -sS -X POST http://127.0.0.1:18000/api/v1/events/ingest -H 'Content-Type: application/json' -d '{"platform":"hermes","event_id":"evt_persist_1","event_type":"message_created","external_session_id":"persist_sess_1","title":"Persist Check","payload_json":{"source":"runbook"},"message":{"role":"user","content":"hello"}}'`

2) List sessions and record returned session id.

3) Restart backend container:

`docker compose restart backend`

4) Query sessions again and confirm the session is still present.

## Rollback

If issues occur:

1) Set `SESSION_STORE_BACKEND=memory` in `.env`
2) Restart backend:

`docker compose up -d backend`

3) Verify health endpoint

## Known Limitations (current stage)

- No formal migration tooling (Alembic) in repo yet.
- SQLAlchemy store currently acts as baseline implementation; repository interface split is the next step.
- Reliability hardening (retry/DLQ) not included in this runbook.

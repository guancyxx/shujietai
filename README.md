# ShuJieTai (枢界台)

Multi-platform agent conversation cockpit MVP.

## Current Snapshot (2026-04-28)

Implemented:
- Docker Compose one-command startup for full stack
- Backend API based on FastAPI
- Frontend cockpit UI based on Vue 3
- Store factory with default SQLAlchemy backend (memory backend kept for fallback)
- Alembic migration baseline + replay-audit migration, with roundtrip migration tests
- Hermes connector endpoints:
  - webhook ingest
  - direct chat relay (OpenAI-compatible API + CLI fallback)
- Retry + DLQ pipeline for ingest failures (configurable)
- Health metrics for ingest success/retry/dlq counters
- Backend test suite (34 tests)

Deferred in this round:
- OpenClaw connector implementation (extension points preserved)
- Security baseline middleware (workspace token verification hardening)

## Service Topology

- frontend: Vue 3 + Vite cockpit UI
- backend: FastAPI API server
- postgres: persistent storage
- redis: reserved for future cache/realtime migration

## Quick Start

1) Copy env file

cp .env.example .env

2) Start all services

docker compose up -d --build

3) Open cockpit UI

http://localhost:15173

4) Check backend health

http://localhost:18000/api/v1/health

## Runtime Ports (default)

- frontend: 15173 -> container 5173
- backend: 18000 -> container 8000
- postgres: internal only (5432)
- redis: internal only (6379)

## API Surface (current)

Core MVP:
- POST /api/v1/events/ingest
- GET /api/v1/sessions
- GET /api/v1/sessions/{id}
- GET /api/v1/sessions/{id}/timeline
- GET /api/v1/board/cockpit?session_id=...
- GET /api/v1/health
- GET /api/v1/dlq (filters: limit, only_unreplayed, platform, since)
- POST /api/v1/dlq/{dlq_id}/replay (optional header: x-replayed-by; optional body: {"force": true})

Hermes-specific:
- POST /api/v1/connectors/hermes/webhook
- POST /api/v1/connectors/hermes/chat

## Verification Commands

Stack status:

docker compose ps

Backend tests:

docker compose run --rm backend pytest -q

Health check:

curl -sS http://127.0.0.1:18000/api/v1/health

Sessions list:

curl -sS http://127.0.0.1:18000/api/v1/sessions

## Alembic Commands

Apply latest migration:

docker compose run --rm backend alembic upgrade head

Rollback to base:

docker compose run --rm backend alembic downgrade base

Roundtrip check on ephemeral sqlite:

docker compose run --rm backend sh -lc 'DATABASE_URL=sqlite+pysqlite:///tmp/alembic_check.db alembic upgrade head && DATABASE_URL=sqlite+pysqlite:///tmp/alembic_check.db alembic downgrade base && DATABASE_URL=sqlite+pysqlite:///tmp/alembic_check.db alembic upgrade head'

## Retry and DLQ

Configuration:
- INGEST_RETRY_ENABLED
- INGEST_MAX_RETRIES
- INGEST_RETRY_DELAYS
- INGEST_RETRY_LOOP_INTERVAL_SECONDS

Behavior:
- ingest write failures are queued for retry
- retry backoff defaults: 1s, 3s, 10s
- after max retries, event is moved to dead_letter_events
- dead letters can be listed via GET /api/v1/dlq
- list supports filters: only_unreplayed, platform, since (ISO8601)
- a dead letter can be replayed via POST /api/v1/dlq/{dlq_id}/replay
- replay does not delete DLQ record; audit fields are updated (replay_count, replayed_at, replayed_by)
- replay of an already replayed item requires force=true in request body

## Environment Variables (high impact)

Backend and frontend:
- SESSION_STORE_BACKEND
- DATABASE_URL
- BACKEND_PORT
- FRONTEND_PORT
- VITE_API_BASE_URL
- CORS_ORIGINS

Reliability:
- INGEST_RETRY_ENABLED
- INGEST_MAX_RETRIES
- INGEST_RETRY_DELAYS
- INGEST_RETRY_LOOP_INTERVAL_SECONDS

Hermes relay:
- HERMES_API_BASE_URL
- HERMES_API_KEY
- HERMES_MODEL
- HERMES_API_TIMEOUT_SECONDS
- HERMES_CLI_FALLBACK_ENABLED
- HERMES_BIN

Mount-related:
- HERMES_CLI_PATH
- HERMES_AGENT_ROOT
- HERMES_HOME_DIR
- HERMES_UV_ROOT

## Additional Project Docs

- docs/superpowers/specs/2026-04-27-shujietai-mvp-design.md
- docs/plans/2026-04-27-shujietai-mvp-implementation-plan.md
- docs/status/2026-04-28-project-status.md
- docs/status/2026-04-28-sqlalchemy-cutover-runbook.md
- docs/status/2026-04-28-implementation-timeline.md

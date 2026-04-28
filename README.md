# ShuJieTai (枢界台)

Multi-platform agent conversation cockpit MVP.

## Current Snapshot (2026-04-28)

Implemented:
- Docker Compose one-command startup for full stack
- Backend API based on FastAPI
- Frontend cockpit UI based on Vue 3
- In-memory session store with idempotent ingest logic
- Optional SQLAlchemy store (configurable by env)
- Store factory-based backend wiring (memory/sqlalchemy switch without API contract change)
- Hermes connector endpoints:
  - webhook ingest
  - direct chat relay (OpenAI-compatible API + CLI fallback)
- Health checks for postgres and redis in compose
- Backend test suite (17 tests) covering core MVP paths, store factory, and SQLAlchemy store baseline

Not implemented yet:
- OpenClaw connector
- Production-grade PostgreSQL repository migration completeness (currently optional SQLAlchemy store path)
- Redis cache/realtime layer in application path
- Retry + dead-letter pipeline for failed ingest
- RBAC and workspace token verification middleware

## Service Topology

- frontend: Vue 3 + Vite cockpit UI
- backend: FastAPI API server
- postgres: reserved for future persistence migration
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

## Environment Variables (high impact)

Backend and frontend:
- SESSION_STORE_BACKEND
- DATABASE_URL
- BACKEND_PORT
- FRONTEND_PORT
- VITE_API_BASE_URL
- CORS_ORIGINS

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

## Architecture Notes

The current backend defaults to an in-memory store for delivery speed, while preserving stable request/response contracts to reduce migration risk.

A store factory (`app/services/store_factory.py`) selects the store backend at startup, enabling controlled cutover without changing API handlers.

An optional SQLAlchemy-backed store is available and can be enabled by setting:
- SESSION_STORE_BACKEND=sqlalchemy
- DATABASE_URL=postgresql+psycopg2://...

Migration direction is documented in:
- docs/adr/0001-mvp-store-and-connector-extension.md

## Additional Project Docs

- docs/superpowers/specs/2026-04-27-shujietai-mvp-design.md
- docs/plans/2026-04-27-shujietai-mvp-implementation-plan.md
- docs/status/2026-04-28-project-status.md

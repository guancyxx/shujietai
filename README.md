# ShuJieTai (枢界台)

Multi-platform agent conversation cockpit MVP.

## Services

- backend: FastAPI API server
- frontend: Vue 3 cockpit UI
- postgres: future persistence target
- redis: future cache/realtime target

## Quick Start

1) Copy env file

cp .env.example .env

2) Start all services

docker compose up -d --build

3) Open UI

http://localhost:15173

4) Check API health

http://localhost:18000/api/v1/health

## MVP APIs

- POST /api/v1/events/ingest
- GET /api/v1/sessions
- GET /api/v1/sessions/{id}
- GET /api/v1/sessions/{id}/timeline
- GET /api/v1/board/cockpit?session_id=...
- GET /api/v1/health

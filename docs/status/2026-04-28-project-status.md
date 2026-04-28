# ShuJieTai Project Status

Date: 2026-04-28

## 1) Scope baseline locked

In scope this round:
- MVP keeps Hermes as the only implemented connector
- Connector architecture remains extension-ready
- SQLAlchemy persistence becomes default runtime path
- Alembic baseline migration is required
- Retry + DLQ ingest reliability is required
- DLQ replay audit fields + filtered list/replay-force operations are included

Out of scope this round:
- OpenClaw connector implementation
- Security middleware hardening (workspace token verification upgrade)

## 2) What is running now

Compose services:
- shujietai-backend
- shujietai-frontend
- shujietai-postgres
- shujietai-redis

Observed host mappings:
- backend: 18000 -> 8000
- frontend: 15173 -> 5173

## 3) Completed capabilities in this iteration

Backend and storage:
- Store factory defaults to SQLAlchemy backend
- In-memory backend kept as fallback option
- Alembic migrations added under backend/alembic:
  - 20260428_0001 baseline schema
  - 20260428_0002 DLQ replay audit fields
- Migration roundtrip test added (upgrade -> downgrade -> upgrade)
- Persistence restart test added (data survives store recreation)

Reliability:
- Ingest retry queue table and DLQ table added
- Retry state machine service added
- Configurable retry settings (enabled/max retries/delay schedule/loop interval)
- In-process retry worker loop added for MVP
- DLQ API operations added:
  - list dead letters with filters (only_unreplayed/platform/since)
  - replay dead letter with optional force mode and operator identity
- Replay audit fields tracked on DLQ rows: replay_count/replayed_at/replayed_by
- Health endpoint now exposes ingest_success_total / ingest_retry_total / ingest_dlq_total counters

Connector scope:
- Hermes webhook + chat paths preserved and compatible
- OpenClaw still deferred as planned

## 4) Verification checks executed

Commands executed:
- docker compose build backend
- docker compose run --rm backend pytest -q

Result:
- backend tests: 34 passed

## 5) Remaining gaps versus long-term design

Pending after this round:
- OpenClaw connector and contract fixtures
- Redis-backed cache/realtime application path
- Security baseline hardening and auth middleware expansion
- Retry worker extraction to external queue workers (optional future scaling step)

## 6) Risk notes

- Retry worker currently runs in backend process; restart pauses retry loop until service recovers
- Health counters are in-process counters and reset on backend restart
- Replay audit fields are persisted, but replay history is aggregated on-row (not append-only event log)

## 7) Recommended next step order

1. Connector extension implementation (OpenClaw)
2. Security baseline upgrade
3. Replay history externalization (append-only audit trail) if compliance requires finer traceability
4. Retry worker externalization if throughput increases

## 8) Timeline document

For a change-log style delivery timeline, see:
- docs/status/2026-04-28-implementation-timeline.md

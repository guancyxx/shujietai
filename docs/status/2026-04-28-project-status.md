# ShuJieTai Project Status

Date: 2026-04-28

## 1) What is running now

Compose services are up and healthy:
- shujietai-backend
- shujietai-frontend
- shujietai-postgres (healthy)
- shujietai-redis (healthy)

Observed host mappings:
- backend: 18000 -> 8000
- frontend: 15173 -> 5173

## 2) Verified checks performed

Commands executed:
- docker compose ps
- docker compose run --rm backend pytest -q
- curl -sS http://127.0.0.1:18000/api/v1/health
- curl -sS http://127.0.0.1:18000/api/v1/sessions

Results:
- backend tests: 17 passed
- health endpoint: healthy
- sessions endpoint: empty array on fresh memory state

## 3) Implemented capabilities

Backend:
- Canonical ingest and query APIs for MVP
- Request-id propagation middleware
- CORS config via environment variable
- In-memory session/event/message/task/metrics store
- Optional SQLAlchemy-backed session/event/message/task/metrics store
- Idempotency by (platform, event_id)

Hermes connector path:
- /api/v1/connectors/hermes/webhook for normalized webhook ingest
- /api/v1/connectors/hermes/chat for direct chat relay
- OpenAI-compatible API call path
- Optional CLI fallback when API path fails

Frontend:
- Three-column cockpit layout
- Session selection + timeline rendering
- Task lane rendering (todo/doing/done)
- Session metrics cards and state panel
- Composer for direct Hermes chat via backend

## 4) Gaps versus MVP design target

From design docs, these are still pending:
- OpenClaw connector implementation
- Production-grade PostgreSQL migration and cutover verification under compose runtime
- Redis-backed cache/realtime behavior in app path
- Retry strategy and dead-letter queue for failed ingest
- Security hardening beyond CORS and env-based keying

## 5) Risks and constraints

- Data durability risk: default memory mode loses session data on backend restart unless SQLAlchemy store is enabled.
- Integration risk: current connector scope is Hermes-only.
- Reliability risk: ingest path lacks retry/dead-letter mechanics.

## 6) Recommended next-step options

Option A (recommended first): Persistence hardening and cutover verification
- Keep store factory + SQLAlchemy store as baseline
- Add compose-level cutover runbook (memory -> sqlalchemy)
- Add restart-persistence verification checklist
- Add repository interface split for sessions/messages/events/tasks/metrics

Option B: Connector expansion
- Implement OpenClaw connector adapter + normalization mapping
- Add contract tests with fixture payloads

Option C: Reliability hardening
- Add retry policy and dead-letter storage for ingest failures
- Add observability counters and error surfaces

Option D: Security baseline upgrade
- Add workspace token validation middleware
- Add endpoint-level auth checks and audit logs

## 7) Suggested execution order

1. Option A (persistence)
2. Option C (reliability)
3. Option B (OpenClaw)
4. Option D (security)

Reasoning:
- Persistence and reliability reduce operational risk before widening platform surface.
- Connector expansion after persistence avoids a second migration wave.

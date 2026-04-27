# ADR 0001: MVP store and connector extension path

Status: Accepted
Date: 2026-04-27

## Context

ShuJieTai MVP needs to deliver quickly with stable APIs for ingest, sessions, timeline, and cockpit. The design also requires future extension for multi-platform connectors and durable persistence.

## Decision

Use an in-memory session store in MVP while keeping canonical schema contracts and service boundaries stable.

- Keep API contracts final for MVP scope.
- Keep service boundaries explicit: connector -> normalizer -> session core -> board service.
- Keep Docker services for PostgreSQL/Redis available from day one to simplify migration.

## Consequences

Positive:
- Fast delivery for UI and API integration.
- Low migration risk because API/schemas are already stable.
- Connector plugins can be added without changing cockpit contract.

Negative:
- In-memory store is not durable across backend restarts.
- No historical retention until persistence layer is implemented.

## Migration plan

1. Add repository interfaces for sessions/messages/events/tasks/metrics.
2. Implement PostgreSQL repositories behind those interfaces.
3. Replace in-memory service wiring with repository-backed service wiring.
4. Add Redis cache for cockpit hot queries.
5. Add connector modules for Hermes and OpenClaw payload normalization.

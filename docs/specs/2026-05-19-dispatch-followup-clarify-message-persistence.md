# Spec: Dispatch follow-up clarification message persistence

## Objective
Fix the chat path where the user sends a follow-up message after an AI round has ended and is waiting for clarification, but the frontend timeline temporarily drops all previous messages and the newly sent message disappears after refresh/session switch.

## Problem statement
Observed behavior:
1. User opens an existing dispatch conversation with history.
2. AI reaches a terminal state (`completed/failed/cancelled/aborted`) and user sends a new instruction.
3. Frontend clears active dispatch state and creates a new dispatch run.
4. Existing timeline disappears immediately.
5. If user refreshes before assistant full reply is persisted, the newly sent message is gone and old history reappears.

This breaks “continue commanding AI in same conversation” UX.

## Root cause
- `sendMessageToHermes()` clears active dispatch state for terminal tasks before creating a new run.
- `clearActiveTask()` empties `dispatchTaskEvents`, so `displayMessages` becomes empty during run handover.
- `createDispatchTask()` unconditionally clears `taskEvents` again, so historical context is dropped even though `selectedExternalSessionId` stays the same.

## Design
### 1) Preserve historical dispatch events during terminal -> next-run handover
- Add optional flag `preserveExistingEvents` in `createDispatchTask()`.
- Only clear `taskEvents` when this flag is false.
- In `sendMessageToHermes()`, detect whether current view has dispatch context (`dispatchTaskId && dispatchTaskEvents.length > 0`) before terminal cleanup.
- Pass `preserveExistingEvents: true` when creating the next run from a terminal conversation.

### 2) Event ordering preference for better continuity
- Sort incoming live events by `created_at` first, then `seq`.
- Keeps cross-run merge order stable when WebSocket and REST fallback events are mixed.

## Files
- `frontend/src/composables/useDispatchTask.js`
- `frontend/src/stores/useSessionStore.js`
- `docs/plans/2026-05-19-dispatch-followup-clarify-message-persistence.md`

## Acceptance criteria
1. Sending a follow-up message after terminal status no longer wipes timeline immediately.
2. Historical messages remain visible while next run starts.
3. New user instruction remains visible in dispatch timeline and is not lost by transient handover.
4. Frontend production build passes in Docker.

## Constraints
- No schema migration.
- No API contract changes.
- Preserve existing terminal/resume/interrupt behavior.

# Dispatch Chat Continuation and Interrupt Plan

## Objective

Fix the chat-page no-op that happens when a user sends another message after an AI dispatch task has reached a terminal status. A terminal dispatch task represents a finished run, not a closed conversation.

This plan also records the follow-up interrupt-and-revise direction, but the P0 implementation scope in this branch is limited to terminal-task continuation.

## Current Behavior

The frontend may keep an active `dispatchTaskId` after the linked dispatch task becomes `completed`, `failed`, `cancelled`, or `aborted`.

`sendMessageToHermes()` currently supports resumable dispatch tasks and new dispatch tasks, but a terminal active dispatch task is neither resumable nor absent. The composer can clear while no resume/create request starts, so the UI appears frozen.

## Desired P0 Behavior

When the user sends a message after a terminal dispatch task:

1. Detect that the active dispatch task is terminal.
2. Clear the active dispatch state for the old task.
3. Create a new dispatch task for the next user turn.
4. Preserve the selected visible conversation when an `external_session_id` is available.
5. Keep `awaiting_input` and `paused` resume behavior unchanged.
6. Do not route `queued` or `running` through terminal continuation.

## Flow

```text
User sends message after completed
  -> App.vue sendMessageToHermes
  -> detect active dispatch status is terminal
  -> clear/rotate active dispatch state
  -> create new dispatch task with selected session external_session_id
  -> REST/WebSocket events render the next AI response
```

## Implementation Scope

Frontend:

- Add a terminal-status helper for dispatch tasks.
- Update `sendMessageToHermes()` decision order so terminal tasks fall through to new dispatch creation.
- Clear active dispatch state before creating the next task.
- Keep composer text until a resume/create request is about to start, preventing silent no-op clearing.

Backend:

- Allow dispatch creation payloads to carry an optional `external_session_id`.
- Use that value when present; otherwise continue generating `dispatch_<task_id>`.
- Preserve existing API compatibility for callers that omit the field.

Out of scope for this P0:

- Full interrupt-and-revise API.
- Upstream Hermes run cancellation.
- Major chat-page component decomposition.

## Testing Strategy

Frontend:

- Unit-test or static guard the terminal-status branch if the existing frontend test setup supports it.
- Production build through Docker or a disposable Docker node container.

Backend:

- Add or update tests proving `DispatchCreateRequest.external_session_id` is accepted and persisted.
- Verify existing dispatch creation still works without the optional field.

Smoke:

- Create a dispatch with a supplied `external_session_id` through the API and verify the returned task preserves it.
- Confirm the frontend bundle builds.

## Success Criteria

1. After `completed`, sending another message creates a new dispatch instead of no-oping.
2. Composer text is not silently discarded before a request starts.
3. The new dispatch can preserve the current session via `external_session_id`.
4. `awaiting_input` and `paused` continue to resume instead of creating new tasks.
5. Docker-based build/tests/smoke checks pass.

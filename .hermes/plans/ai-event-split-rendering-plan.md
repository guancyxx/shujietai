# Implementation Plan: AI Event Split Rendering

## Overview

Add missing event type handlers to `dispatchMessages` in `useDispatchTask.js`
so every backend-emitted event type produces a visible timeline item. Add
CSS for event type badges so users can distinguish thinking/tool/output/status
events at a glance. No backend changes needed.

## Architecture Decision

Approach A (additive): Keep existing content_delta merge logic untouched.
Add new else-if branches for unhandled event types. No signature changes.
This is zero-risk for the existing merge contract.

## Task List

### Task 1: Add missing event type handlers to dispatchMessages (S, 1 file)

Acceptance:
- progress events render as system-status items with icon and summary
- content_full events appear as a completion marker (compact system item)
- status transitions (completed, cancelled, failed) produce timeline system messages
- await_input events render as a system item with prompt preview
- All new items have stable IDs derived from event_id + event_type

Verification:
- Read useDispatchTask.js lines 364-564, add handlers as new else-if blocks
- Each handler pushes a message with unique id, role='system', and descriptive content
- No changes to existing merge logic

Files: frontend/src/composables/useDispatchTask.js

### Task 2: Add visual event type indicators with CSS (S, 1 file)

Acceptance:
- System/status messages have distinct visual style from content messages
- Event type badges (tool/thinking/completed/error/etc.) are visually distinguishable
- Tool call bubbles show event timestamp
- All existing rendering classes untouched

Verification:
- Add CSS rules to chat.css for system-event, event-timestamp classes
- Ensure no breakage of existing bubble/tool/thinking styles

Files: frontend/src/styles/chat.css

### Task 3: Verify with Docker build + smoke test (S, 3 commands)

Acceptance:
- `docker compose build frontend` succeeds
- Frontend serves without errors at http://localhost:15173/
- Backend health check passes at http://localhost:18000/api/v1/health

Verification:
- Create a dispatch task that produces tool calls + content_delta + thinking
- Verify in API response that event types are separated in timeline rendering

Files: none (verification only)

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Event ID collision | Low (new IDs use event_id prefix) | Use `evt.id + '_status'` pattern |
| CSS cascade break | Low | Additive rules only, no selector changes |

## Checkpoint: Complete

- All tasks done
- Docker build passes
- dispatchMessages handles all event types from backend
- Event timeline shows visual separation between tool/text/status events
- PR created

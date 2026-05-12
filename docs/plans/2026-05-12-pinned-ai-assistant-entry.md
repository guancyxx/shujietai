# Spec: Pinned AI Assistant Entry in Session List

## Objective

Add a permanently pinned "AI Assistant" entry at the top of the chat page's
conversation list. This entry acts as a quick-access shortcut to start a
blank chat session with any configured AI provider.

The entry must:
- Be always visible at the top of the session list, regardless of scroll position
- Include a provider dropdown so the user can select which AI provider to use
- Clicking the entry puts the chat panel into "blank chat" mode — no
  selected session, no history loaded
- Typing a message in this mode creates a new dispatch task with the chosen provider

## Tech Stack

- Vue 3 (Composition API, <script setup>)
- No backend changes needed — this is purely a frontend UI addition
- Uses existing `POST /api/v1/dispatch` endpoint for new conversations
- Uses existing `cockpit.runtime.available_model_items` for provider list

## Commands

```bash
# Build frontend (from worktree)
docker compose build frontend

# Verify via smoke check
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:15173/
```

## Project Structure

Worktree: `/home/guancy/workspace/shujietai/.worktrees/pinned-ai-assistant`

Files touched:
```
frontend/src/App.vue        # Pinned entry template + JS logic
frontend/src/style.css      # CSS for pinned entry + provider dropdown
```

## Code Style

Existing conventions from App.vue:
- `<script setup>` with `ref()`, `computed()`, `watch()`
- CSS classes prefixed with feature: `conversation-*`, `pinned-*`
- API calls via `fetchJson()`, `postJson()` helpers
- `import.meta.env.VITE_API_BASE_URL` for API base

## Testing Strategy

- Manual verification: Docker build succeeds, page loads at :15173
- Smoke test: pinned entry renders, provider dropdown works, clicking enters blank mode
- No unit tests needed for this UI-only change

## Boundaries

- Always: match existing CSS design system (dark theme, border glows, hover effects)
- Always: provider list comes from `cockpit.runtime.available_model_items` (providers extracted via `item.provider`)
- Ask first: any backend schema or API changes
- Never: modify the session/ingest system to create fake sessions for this entry
- Never: store pinned entry state in the sessions table

## Success Criteria

1. Pinned "AI Assistant" entry is rendered at top of `.conversation-only-list`, above the
   scrollable `v-for` session list
2. Entry includes a provider `<select>` dropdown populated from available providers
3. Clicking the entry sets `selectedSessionId = ''` and enters blank chat mode
4. Provider selector changes are reflected in `selectedBlankChatProvider`
5. Sending a message in blank chat mode creates a dispatch task using the selected provider
6. After dispatch task creation, the normal dispatch flow takes over (session created via ingest)
7. Entry stays visible when scrolling the session list below

## Open Questions

None — task requirements are fully specified.

## Design Decisions

1. **Pinned entry is NOT a real session.** It does not appear in the sessions table or
   backend API. It is a synthetic UI element in the frontend list.

2. **Blank chat mode is simply `selectedSessionId = ''` with `blankChatProvider` set.**
   When `selectedSessionId` is empty and `blankChatProvider` is set, the composer is
   still active and the "send" handler creates a new dispatch task.

3. **Provider list is derived from `cockpit.runtime.available_model_items`.**
   Each `RuntimeModelItem` has a `.provider` field. We extract unique provider names
   for the dropdown. This avoids a separate API call.

4. **The pinned entry is placed OUTSIDE the scrollable `v-for` container.**
   Structure: a fixed `.pinned-entry` div, then the scrollable `.conversation-only-list`
   with the normal `v-for`.

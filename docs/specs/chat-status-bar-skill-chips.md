# Spec: Chat Status Bar Skill Chips

Date: 2026-05-18
Status: draft

## What

When a dispatch task runs and Hermes loads skills via `skill_view`, the chat
status bar shows which skills were loaded as clickable chips (badges).

## How

### Data Source

`currentLoadedSkills` is a computed property that scans the session's
`dispatchTaskEvents`. For every tool event where `function_name === 'skill_view'`,
extract `skill_name` and `file_path` from the payload. Deduplicate by skill name
preserving first-seen order.

Events are already normalized by `hermes_connector.py` with `skill_name` and
`skill_file_path` fields.

### UI

Chips render in `ChatComposer.vue` status bar area (`cockpit-status`).
Each chip shows the skill name. Clicking a chip opens the skill detail
view using `GET /api/v1/skills/{skill_name:path}/content`.

### States

- No skills loaded: chips area is hidden
- Loading: chip click triggers fetch, shows spinner in detail panel
- 404/missing: friendly error in detail panel
- Network error: friendly error in detail panel

### Cleanup

- Switching sessions clears `dispatchTaskEvents`, thus chips clear
- `clearActiveTask()` clears `taskEvents`, thus chips clear

## Verification

1. Run dispatch task that triggers `skill_view` -> chips appear in status bar
2. Click chip -> detail panel shows SKILL.md content
3. Switch session -> chips clear
4. 404 skill fetch shows friendly error
5. Docker build passes

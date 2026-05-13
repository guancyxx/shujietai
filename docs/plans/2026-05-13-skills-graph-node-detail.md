# Spec: Skills Graph Node Click Detail

## Objective

Enable clicking skill nodes in the skills graph (skill-level mode) to view detailed metadata: name, description, category, tags, filesystem path, related skills, and content summary. Reuse the existing SKILL.md content API and add a parsed detail endpoint.

## Tech Stack

- Backend: Python 3.12, FastAPI, PyYAML
- Frontend: Vue 3, D3 v7, CSS scoped

## Commands

Build: `docker compose build backend frontend`
Smoke: `curl -s http://localhost:18000/api/v1/skills/devops/kanban-worker/detail`

## Project Structure

```
backend/app/main.py          → Add GET /api/v1/skills/{name}/detail
frontend/src/SkillGraph.vue  → Enhance click handler + detail panel
```

## Code Style

- Comments in English
- Vue template: use `v-if`/`v-else` for state branches
- Backend: fastapi `HTTPException` for errors

## Testing Strategy

- Backend: manual curl smoke test
- Frontend: Docker build + manual click verification in UI

## Boundaries

- Always: reuse existing APIs, don't break D3 zoom/drag, handle loading/error/empty states
- Ask first: none needed for this spec
- Never: modify App.vue (SkillGraph is self-contained), change graph data format

## Success Criteria

1. Click a skill node in skill-level graph → detail panel shows name, description, category, tags, path, related skills, content summary from SKILL.md
2. Click a different skill node → detail panel updates immediately
3. Close button (✕) hides detail panel
4. Loading spinner shown while fetching
5. Error state shown on 404 or network failure
6. Graph zoom/drag/pan unaffected by clicks
7. Docker build passes

## Implementation Plan

### Task 1: Backend — Add GET /api/v1/skills/{name}/detail (S)

Add a new endpoint that returns parsed SKILL.md frontmatter + body summary.

Response shape:
```json
{
  "name": "devops/kanban-worker",
  "description": "Pitfalls, examples, and edge cases for Hermes Kanban workers...",
  "category": "devops",
  "tags": ["kanban", "worker", "devops"],
  "path": "/home/guancy/.hermes/skills/devops/kanban-worker/SKILL.md",
  "related_skills": [],
  "content_summary": "First ~500 chars of body after frontmatter...",
  "skill_type": "custom"
}
```

Files: `backend/app/main.py`
Acceptance: `curl http://localhost:18000/api/v1/skills/devops/kanban-worker/detail` returns valid JSON
Verify: `docker compose build backend && docker compose up -d --force-recreate backend && curl ...`

### Task 2: Frontend — Enhance SkillGraph click handler + detail panel (M)

Modify SkillGraph.vue:
- On skill node click: fetch `/api/v1/skills/{name}/detail`
- Add reactive state: `detailLoading`, `detailError`, `skillDetail`
- Update detail panel template to show parsed metadata
- Add loading spinner / error / empty states
- Keep `selected = d` for graph data fallback

Files: `frontend/src/SkillGraph.vue`
Acceptance: Click skill node → loads detail from API and shows rich info
Verify: `docker compose build frontend && docker compose up -d --force-recreate frontend && curl http://localhost:15173/` + manual click smoke

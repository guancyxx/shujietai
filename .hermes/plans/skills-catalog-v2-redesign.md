# Spec: Skills Catalog Page v2 Redesign

**Date:** 2026-05-10
**Branch:** feat/skills-catalog-v2
**Status:** Draft

## Problem

The current skills catalog page has four issues:
1. Scrollbar style is inconsistent with the rest of the UI (every component has its own ad-hoc scrollbar CSS)
2. Skills cannot be distinguished as builtin / custom / third-party
3. Page uses container-width layout; does not fill the full viewport
4. Card design is bare — category badge + name + truncated description only

## Goals

1. **Global scrollbar style** — extract a single shared scrollbar CSS class/mixin applied to all scrollable elements; apply it to skills catalog and consolidate existing duplicated scrollbar rules
2. **Skill type badge** — distinguish builtin (Hermes default), custom (personal-skills), and third-party (plugins) via a colored badge on each card
3. **Full-viewport layout** — skills-catalog-grid should stretch to fill 100% of available height/width, not be constrained by container padding
4. **Card redesign** — richer card: type badge + category + name (bold) + description (multi-line, clamped) + click to open detail modal

## Non-Goals

- No changes to backend data model (RuntimeSkillItem fields stay the same)
- No pagination — lazy search/filter is sufficient for current volume
- No editing skills from the UI

## Solution

### 1. Global Scrollbar Utility Class

Add a shared `.scrollbar-themed` CSS class at the top of style.css:
```
.scrollbar-themed {
  scrollbar-width: thin;
  scrollbar-color: rgba(111,186,255,0.3) transparent;
}
.scrollbar-themed::-webkit-scrollbar { width: 5px; }
.scrollbar-themed::-webkit-scrollbar-thumb { background: rgba(111,186,255,0.25); border-radius: 3px; }
.scrollbar-themed::-webkit-scrollbar-thumb:hover { background: rgba(111,186,255,0.5); }
.scrollbar-themed::-webkit-scrollbar-track { background: transparent; }
```
Apply `.scrollbar-themed` to skills-catalog-list and any other scrollable containers that currently repeat this pattern. Do NOT mass-migrate existing scrollbar rules in this PR (scope risk); just use the class for new elements.

### 2. Skill Type Classification

**Backend:** Upgrade `GET /api/v1/skills` to add a `skill_type` field.

Classification logic (in priority order):
1. If `hermes skills list` output is available → use the `source` column directly:
   - `source == "personal-skills"` → `"custom"`
   - `source == "builtin"` or `source == "skills"` → `"builtin"`
   - anything else non-empty → `"third-party"`
2. Fallback (filesystem scan only): check if SKILL.md path contains `personal-skills` → `"custom"`, else `"builtin"`

**Backend change:** modify `_collect_skill_items_from_hermes_cli()` to also capture source, and expose it in `RuntimeSkillItem`. Then expose `skill_type` in the `/api/v1/skills` response.

**Frontend badge colors:**
- `builtin` → blue-grey (`rgba(111,186,255,0.15)` bg, `#6fbаff` text) — label: "内置"
- `custom` → amber (`rgba(255,190,60,0.15)` bg, `#ffbe3c` text) — label: "自建"
- `third-party` → teal (`rgba(60,220,180,0.12)` bg, `#3cdcb4` text) — label: "第三方"

### 3. Full-Viewport Layout

Change `.skills-catalog-grid` from a container layout to:
```css
.skills-catalog-grid {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  padding: 0;
}
.skills-catalog-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-radius: 0;
  margin: 0;
}
.skills-catalog-list {
  flex: 1;
  overflow-y: auto;
  /* use .scrollbar-themed */
}
```

### 4. Card Redesign

Card layout (each card):
```
┌─────────────────────────────────────────────┐
│ [自建]  [devops]                       ↗    │
│ skill-name                                  │
│ Description text, up to 3 lines, then ...   │
└─────────────────────────────────────────────┘
```

- Card is clickable (cursor: pointer) — clicking opens a detail modal
- Card hover: subtle border highlight (`rgba(111,186,255,0.3)`)
- Grid: 3-column auto-fill, min 280px cards
- Card padding: 16px

**Detail Modal:**
- Reuse existing `.picker-modal` / `.picker-modal-overlay` pattern
- Shows: full name, type badge, category, full description, skill_type (from YAML if available)
- Close via ✕ button or clicking overlay

## Files to Change

### Backend
- `backend/app/schemas.py` — add `skill_type: str` to `RuntimeSkillItem`
- `backend/app/services/hermes_runtime_catalog.py` — capture source from CLI output, add fallback path-based detection
- `backend/app/main.py` — pass `skill_type` in `/api/v1/skills` response

### Frontend
- `frontend/src/style.css` — add `.scrollbar-themed` utility; add/update skills catalog CSS
- `frontend/src/App.vue` — card HTML redesign + detail modal + JS state for modal

## Acceptance Criteria

1. Skills page fills the full viewport with no visible horizontal container constraint
2. Each skill card shows a colored type badge (内置/自建/第三方)
3. Clicking a card opens a modal with full description
4. Scrollbar in skill list matches system style (thin blue-grey)
5. No regressions on other pages (scrollbar changes are additive only)
6. docker compose build exits 0

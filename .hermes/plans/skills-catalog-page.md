# Spec: Skills Catalog Page

## Goal

Add a dedicated "Skills 库" page to shujietai that lists and displays all skills
from Hermes (and future providers). Hermes is just one provider — the architecture
must remain extensible.

## Constraints

- Hermes is a provider, not the only source. Use provider abstraction from day one.
- Backend already scans ~/.hermes/skills/ via hermes_runtime_catalog. Reuse this.
- Do NOT add heavy dependencies. Pure fetch, no new npm packages.
- Follow shujietai CSS/layout conventions (panel, main-grid, config-grid, picker-* classes).
- No browser verification needed after changes — build + Docker rebuild + commit.

## Backend Changes

### 1. New endpoint: GET /api/v1/skills

Returns skills from all configured providers. Response shape:

```json
{
  "providers": [
    {
      "id": "hermes",
      "label": "Hermes Agent",
      "skills": [
        { "name": "devops/docker-health-check", "description": "...", "category": "devops" },
        ...
      ]
    }
  ],
  "total": 142
}
```

- category = first path segment of skill name (e.g. "devops" from "devops/kanban-worker")
  or "general" if no slash.
- source: reuse _collect_skill_items_from_filesystem() from hermes_runtime_catalog.py
  (already cached via TTL cache in build_runtime_state).
- Future providers: add to a SKILL_PROVIDERS registry list, each provider implements
  a collect() -> list[RuntimeSkillItem] interface.

### 2. Add route in main.py

Register GET /api/v1/skills handler. No auth needed (same as other endpoints).

## Frontend Changes

### 1. New nav button

Add "Skills 库" button in top-nav, activePage = 'skills-catalog'.
Position: after "模型配置" button.

### 2. New page section

```html
<section v-else-if="activePage === 'skills-catalog'" class="main-grid skills-catalog-grid">
  ...
</section>
```

### 3. Skills catalog state

```javascript
const skillsCatalog = ref(null)         // raw API response
const skillsCatalogLoading = ref(false)
const skillsCatalogError = ref('')
const skillsCatalogSearch = ref('')
const skillsCatalogCategoryFilter = ref('全部')
const skillsCatalogProviderFilter = ref('hermes')  // default to hermes
```

### 4. loadSkillsCatalog()

Fetch GET /api/v1/skills on page mount and when user switches to this page.
Cache in skillsCatalog ref (no TTL on frontend — user can manually refresh).

### 5. Computed: filteredCatalogSkills

Filter by provider + category + search keyword.
Returns flat list of { name, description, category, provider_id, provider_label }.

### 6. UI layout

- Left sidebar: provider selector + category list (accordion or flat list with counts)
- Main area: skills grid/list with name + description cards
- Top: search input + total count badge
- Each card: skill name (bold), category badge, description text

### 7. CSS additions

```css
.skills-catalog-grid { grid-template-columns: minmax(0, 1fr); }
/* @media overrides for 1439px and 1023px breakpoints — MANDATORY per CSS pitfall */
.skills-catalog-panel { ... }
.skill-card { ... }
.skill-card-name { ... }
.skill-card-desc { ... }
.skill-category-badge { ... }
```

## File Changes

| File | Change |
|------|--------|
| backend/app/api/routes_dispatch.py OR new routes_skills.py | Add GET /api/v1/skills |
| backend/app/main.py | Register new router |
| frontend/src/App.vue | Nav button + page section + JS state/computed + CSS |

## Acceptance Criteria

1. GET /api/v1/skills returns JSON with providers[].skills[]
2. "Skills 库" nav button appears and switches page
3. Skills list loads and displays all hermes skills with name + description
4. Search filters by name or description
5. Category filter works
6. Docker build passes (no new errors)
7. Responsive layout correct at all breakpoints (no 36%/64% split bug)

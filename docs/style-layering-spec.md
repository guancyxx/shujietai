# Style Layering Specification

ShuJieTai frontend CSS architecture. Defines ownership boundaries and import order for all stylesheets.

## Layer Model

```
Layer 0: Tokens + Reset           → base.css
Layer 1: Shell + Layout           → shell.css
Layer 2: Shared Utilities         → base.css (tail section)
Layer 3: Shared Components        → (co-located with component or in shell.css)
Layer 4: Page Modules             → {page}.css
Layer 5: Feature Modules          → {feature}.css
Layer 6: Global Responsive        → responsive.css
```

| Layer | Purpose | What belongs | What does NOT belong |
|-------|---------|-------------|---------------------|
| **Tokens + Reset** | Design tokens, box-sizing, html/body reset | `:root` vars, `* { box-sizing }`, html/body/#app reset | Any UI component |
| **Shell + Layout** | App chrome — topbar, navigation, toolbar, session controls | `.app-shell`, `.bg-layer`, `.cockpit-wrap`, `.topbar`, `.top-nav`, `.toolbar`, `.session-*` | Page-specific content areas |
| **Shared Utilities** | Cross-page low-level helpers | `.scrollbar-themed`, `.scrollbar-themed-auto-hide`, `.muted`, `.error`, `.panel` | Component-specific rules |
| **Shared Components** | Reusable UI primitives | `.panel`, `.panel-soft` (shared glass card), `.picker-*` | Page-specific layout grids |
| **Page Modules** | One file per page/section | `.chat-grid`/chat components, `.task-board-*`, `.config-*`, `.dispatch-*`, `.skills-catalog-*`, `.projects-*` | Another page's styles |
| **Feature Modules** | Cross-cutting features | `.task-board-matrix.css` (kanban layout), skill graph | — |
| **Global Responsive** | All `@media` breakpoint overrides | 1439px, 1023px, 767px global layout rules | Component-level responsive (keep with component) |

## Import Order (main.js)

```
1. base.css         — tokens, reset, shared utilities
2. shell.css        — app chrome (topbar, nav, toolbar, session)
3. chat.css         — chat page (grid, timeline, conversation list)
4. projects.css     — projects page
5. task-board.css   — task board page
6. config.css       — config page
7. dispatch.css     — dispatch history page
8. skills-catalog.css — skills catalog page
9. task-board-matrix.css — kanban matrix feature
10. responsive.css  — global breakpoint overrides (MUST be last)
```

## Responsive Strategy

**Choice: centralized `responsive.css`** — all global media queries live in a single file, loaded last.

Rationale:
- Three breakpoints (1439px, 1023px, 767px) interact across pages via source-order specificity
- Scattering @media blocks across page modules creates silent cascade bugs (e.g. `.main-grid` override in one file unintentionally affecting another page)
- Centralization makes the breakpoint cascade explicit and auditable

**Component-owned responsive rules stay with their module.** If a component has internal responsive behavior that does NOT affect other pages (e.g. `.skill-card` layout changes), those rules stay in the component's page module. Only rules that touch shared grid classes (`.main-grid`, `.chat-grid`, `.cockpit-wrap`, etc.) go in responsive.css.

## Ownership Rules

1. **Only truly shared rules go in base.css / shell.css.** If a rule targets a class exclusive to one page, it belongs in that page's module.
2. **New pages get their own .css file.** Do not add page-specific styles to base/shell/responsive.
3. **shared utilities must be low-level and page-agnostic.** `.muted`, `.error`, `.scrollbar-themed` — yes. `.kpi-corner`, `.session-chip` — no (these are shell components, not utilities).
4. **responsive.css is read-only for new page-specific rules.** New page breakpoint overrides go in the page module, not responsive.css. Only update responsive.css when modifying global grid layout behavior.
5. **No duplicate selector definitions across modules.** One canonical location per class.

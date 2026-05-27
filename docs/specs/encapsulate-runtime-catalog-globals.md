# Spec: Encapsulate hermes_runtime_catalog globals into RuntimeCatalogService

## Objective

Replace module-level mutable globals (`_preferences`, `_runtime_cache`) and their associated locks with a `RuntimeCatalogService` class that supports dependency injection, enabling testing and multi-instance use.

## Scope

Refactor `backend/app/services/hermes_runtime_catalog.py` to move state into a class while keeping pure helper functions at module level. Wire the new service through `container.py` as a singleton and update all call sites.

## Current Problem

- `_preferences` dict and `_preferences_lock` are module-level singletons — no way to test with isolated state or run multiple instances
- `_runtime_cache` dict and `_runtime_cache_lock` have the same problem
- Five public functions (`build_runtime_state`, `invalidate_runtime_cache`, `set_runtime_preferences`, `get_selected_model`, `_sanitize_preferences`) touch these globals

## Design

### Class: `RuntimeCatalogService`

Instance state:
- `_preferences_lock: Lock`
- `_preferences: dict[str, object]`
- `_runtime_cache_lock: Lock`
- `_runtime_cache: dict[str, object]`
- `_cache_ttl: float` (default 60.0, injected for testability)

Public methods:
- `build_runtime_state() -> RuntimeState`
- `invalidate_runtime_cache() -> None`
- `set_runtime_preferences(selected_model, selected_skills, selected_mcp_servers) -> None`
- `get_selected_model() -> str`

### What stays module-level

Pure functions that don't touch globals:
- `_load_hermes_config()`, `_load_hermes_env_file()` — filesystem reads
- `_resolve_provider_base_url()`, `_resolve_provider_api_key()` — config lookups
- `_fetch_models_for_provider()` — HTTP fetch
- `_collect_models_from_config()` — config parsing
- `_extract_skill_description()`, `_source_to_skill_type()` — parsing
- `_collect_skill_items_from_filesystem()`, `_collect_skill_items_from_hermes_cli()` — data collection
- `_infer_provider_from_model_name()`, `_collect_mcp()` — helpers
- `_PROVIDER_API_DEFAULTS`, `_PROVIDER_API_KEY_ENV_KEYS`, `_PROVIDER_BASE_URL_ENV_KEYS` — immutable constants

### What moves into the class

- `_preferences` + `_preferences_lock` → instance attributes
- `_runtime_cache` + `_runtime_cache_lock` → instance attributes
- `_sanitize_preferences()` → instance method (reads `self._preferences`)
- `build_runtime_state()` → instance method
- `invalidate_runtime_cache()` → instance method
- `set_runtime_preferences()` → instance method
- `get_selected_model()` → instance method

### DI wiring in container.py

```python
from app.services.hermes_runtime_catalog import RuntimeCatalogService
runtime_catalog = RuntimeCatalogService()
```

### Call site changes

| File | Old | New |
|------|-----|-----|
| `routes_skills.py` | `from ...hermes_runtime_catalog import build_runtime_state, ...` | `from app.container import runtime_catalog` then `runtime_catalog.build_runtime_state()` |
| `routes_hermes.py` | `from ...hermes_runtime_catalog import build_runtime_state, get_selected_model` | `from app.container import runtime_catalog` then `runtime_catalog.build_runtime_state()`, `runtime_catalog.get_selected_model()` |
| `session_store.py` | `from ...hermes_runtime_catalog import build_runtime_state` then `build_runtime_state()` | `from app.container import runtime_catalog` then `runtime_catalog.build_runtime_state()` |
| `sqlalchemy_store.py` | Same pattern | Same fix |

## Files Changed

1. `backend/app/services/hermes_runtime_catalog.py` — add class, remove globals
2. `backend/app/container.py` — create singleton instance
3. `backend/app/api/routes_skills.py` — use container instance
4. `backend/app/api/routes_hermes.py` — use container instance
5. `backend/app/services/session_store.py` — use container instance
6. `backend/app/services/sqlalchemy_store.py` — use container instance

## Success Criteria

- No module-level mutable state in `hermes_runtime_catalog.py` (immutable constants OK)
- All call sites use the container singleton
- Backend builds and starts without import errors
- `GET /api/v1/health` returns 200
- `GET /api/v1/runtime?platform=hermes` returns valid runtime state with models and skills
- `PUT /api/v1/runtime/preferences` updates and returns fresh state
- Existing tests (if any) still pass

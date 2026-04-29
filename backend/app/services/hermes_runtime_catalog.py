from __future__ import annotations

import os
from pathlib import Path
from threading import Lock
from subprocess import run

import httpx

from app.schemas import RuntimeModelItem, RuntimeSkillItem, RuntimeState

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

_preferences_lock = Lock()
_preferences: dict[str, object] = {
    "selected_model": "",
    "selected_skills": [],
    "selected_mcp_servers": [],
}

_PROVIDER_API_DEFAULTS: dict[str, str] = {
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "ollama-cloud": "https://ollama.com/v1",
    "opencode-go": "https://opencode.ai/zen/go/v1",
    "ollama-launch": "http://127.0.0.1:11434/v1",
    "xiaomi": "https://api.xiaomimimo.com/v1",
}

_PROVIDER_API_KEY_ENV_KEYS: dict[str, tuple[str, ...]] = {
    "nvidia": ("NVIDIA_API_KEY",),
    "ollama-cloud": ("OLLAMA_API_KEY",),
    "opencode-go": ("OPENCODE_GO_API_KEY",),
    "ollama-launch": tuple(),
    "xiaomi": ("XIAOMI_API_KEY",),
}

_PROVIDER_BASE_URL_ENV_KEYS: dict[str, tuple[str, ...]] = {
    "nvidia": ("NVIDIA_BASE_URL",),
    "ollama-cloud": ("OLLAMA_BASE_URL",),
    "opencode-go": ("OPENCODE_GO_BASE_URL",),
    "ollama-launch": ("OLLAMA_BASE_URL",),
    "xiaomi": ("XIAOMI_BASE_URL",),
}


def _load_hermes_config() -> dict:
    config_path = Path(os.getenv("HERMES_CONFIG_PATH", "/home/guancy/.hermes/config.yaml"))
    if not config_path.exists() or yaml is None:
        return {}
    try:
        content = config_path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(content)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _load_hermes_env_file() -> dict[str, str]:
    env_path = Path(os.getenv("HERMES_ENV_PATH", "/home/guancy/.hermes/.env"))
    if not env_path.exists():
        return {}

    parsed: dict[str, str] = {}
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env_key = key.strip()
            if not env_key:
                continue
            parsed[env_key] = value.strip().strip('"').strip("'")
    except Exception:
        return {}

    return parsed


def _resolve_provider_base_url(
    provider_name: str,
    provider_data: dict,
    model_cfg: dict,
    env_values: dict[str, str],
) -> str:
    normalized_provider = provider_name.strip()
    model_provider = str(model_cfg.get("provider", "")).strip()

    candidates: list[str] = []
    if isinstance(provider_data.get("api"), str):
        candidates.append(provider_data.get("api", ""))
    if isinstance(provider_data.get("base_url"), str):
        candidates.append(provider_data.get("base_url", ""))

    for env_key in _PROVIDER_BASE_URL_ENV_KEYS.get(normalized_provider, tuple()):
        candidates.append(env_values.get(env_key, ""))

    if model_provider == normalized_provider:
        candidates.append(str(model_cfg.get("base_url", "")))

    candidates.append(_PROVIDER_API_DEFAULTS.get(normalized_provider, ""))

    for value in candidates:
        normalized = str(value or "").strip()
        if normalized:
            return normalized.rstrip("/")

    return ""


def _resolve_provider_api_key(provider_name: str, env_values: dict[str, str]) -> str:
    normalized_provider = provider_name.strip()
    for env_key in _PROVIDER_API_KEY_ENV_KEYS.get(normalized_provider, tuple()):
        value = (os.getenv(env_key, "") or env_values.get(env_key, "") or "").strip()
        if value:
            return value
    return ""


def _fetch_models_for_provider(provider_name: str, base_url: str, api_key: str) -> set[str]:
    if not base_url:
        return set()

    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = httpx.get(f"{base_url.rstrip('/')}/models", headers=headers, timeout=10.0)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return set()

    data = payload.get("data", []) if isinstance(payload, dict) else []
    models: set[str] = set()
    if not isinstance(data, list):
        return models

    for item in data:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if isinstance(model_id, str) and model_id.strip():
            models.add(model_id.strip())

    return models


def _collect_models_from_config(config: dict) -> tuple[str, set[str], dict[str, str]]:
    model_cfg = config.get("model", {}) if isinstance(config.get("model"), dict) else {}
    selected_model = str(model_cfg.get("default", "")).strip()
    selected_provider = str(model_cfg.get("provider", "")).strip()
    env_values = _load_hermes_env_file()

    collected: set[str] = set()
    provider_map: dict[str, str] = {}
    if selected_model:
        collected.add(selected_model)
        if selected_provider:
            provider_map[selected_model] = selected_provider

    providers = config.get("providers", {}) if isinstance(config.get("providers"), dict) else {}
    for provider_name, provider_data in providers.items():
        if not isinstance(provider_data, dict):
            continue

        normalized_provider = str(provider_name).strip()

        base_url = _resolve_provider_base_url(normalized_provider, provider_data, model_cfg, env_values)
        api_key = _resolve_provider_api_key(normalized_provider, env_values)
        api_models = _fetch_models_for_provider(normalized_provider, base_url, api_key)

        if not api_models:
            default_model = provider_data.get("default_model")
            if isinstance(default_model, str) and default_model.strip():
                api_models.add(default_model.strip())

            models = provider_data.get("models", [])
            if isinstance(models, list):
                for item in models:
                    if isinstance(item, str) and item.strip():
                        api_models.add(item.strip())

        for model_name in sorted(api_models):
            collected.add(model_name)
            if normalized_provider and model_name not in provider_map:
                provider_map[model_name] = normalized_provider

    return selected_model, collected, provider_map


def _extract_skill_description(skill_file: Path) -> str:
    try:
        content = skill_file.read_text(encoding="utf-8")
    except Exception:
        return ""

    if not content.startswith("---\n"):
        return ""

    end_index = content.find("\n---\n", 4)
    if end_index < 0:
        return ""

    frontmatter = content[4:end_index]
    for line in frontmatter.splitlines():
        stripped = line.strip()
        if not stripped.startswith("description:"):
            continue
        value = stripped.split(":", 1)[1].strip()
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            return value[1:-1].strip()
        if value.startswith("'") and value.endswith("'") and len(value) >= 2:
            return value[1:-1].strip()
        return value

    return ""


def _collect_skill_items_from_filesystem() -> list[RuntimeSkillItem]:
    skills_dir = Path(os.getenv("HERMES_SKILLS_DIR", "/home/guancy/.hermes/skills"))
    if not skills_dir.exists():
        return []

    items: list[RuntimeSkillItem] = []
    seen: set[str] = set()

    for skill_file in skills_dir.rglob("SKILL.md"):
        if not skill_file.is_file():
            continue

        rel = skill_file.parent.relative_to(skills_dir)
        parts = rel.parts
        if len(parts) == 1:
            full_name = parts[0]
        elif len(parts) >= 2:
            full_name = f"{parts[0]}/{parts[1]}"
        else:
            continue

        if full_name in seen:
            continue

        seen.add(full_name)
        items.append(
            RuntimeSkillItem(
                name=full_name,
                description=_extract_skill_description(skill_file),
            )
        )

    items.sort(key=lambda item: item.name)
    return items


def _collect_skill_items_from_hermes_cli() -> list[RuntimeSkillItem]:
    try:
        result = run(
            ["hermes", "skills", "list"],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
            env={**os.environ, "COLUMNS": "240"},
        )
    except Exception:
        return []

    if result.returncode != 0:
        return []

    items: list[RuntimeSkillItem] = []
    seen: set[str] = set()

    for raw_line in result.stdout.splitlines():
        line = raw_line.strip("\n")
        if "│" not in line:
            continue
        if line.startswith("┏") or line.startswith("┗") or line.startswith("┡"):
            continue

        parts = [part.strip() for part in line.split("│")]
        if len(parts) < 6:
            continue

        name = parts[1]
        category = parts[2]
        source = parts[3]
        trust = parts[4]
        status = parts[5]
        if not name or name.lower() in {"name", "-"}:
            continue
        if status and status not in {"enabled", "disabled"}:
            continue

        full_name = f"{category}/{name}" if category else name
        if full_name in seen:
            continue

        seen.add(full_name)
        description = f"source={source or '-'} · trust={trust or '-'} · status={status or '-'}"
        items.append(RuntimeSkillItem(name=full_name, description=description))

    items.sort(key=lambda item: item.name)
    return items


def _infer_provider_from_model_name(model_name: str) -> str:
    candidate = (model_name or "").strip()
    if not candidate:
        return ""

    if "/" in candidate:
        return candidate.split("/", 1)[0].strip()

    normalized = candidate.lower()
    known_prefixes = [
        "openai",
        "anthropic",
        "google",
        "gemini",
        "xai",
        "grok",
        "nvidia",
        "deepseek",
        "qwen",
        "ollama",
        "openrouter",
        "mistral",
        "moonshot",
        "azure",
    ]
    for prefix in known_prefixes:
        if normalized.startswith(prefix):
            return prefix

    return ""


def _collect_mcp(config: dict) -> tuple[list[str], list[str]]:
    mcp_servers = config.get("mcp_servers", {}) if isinstance(config.get("mcp_servers"), dict) else {}
    available = sorted(mcp_servers.keys())

    enabled_in_config: list[str] = []
    for name, server in mcp_servers.items():
        if not isinstance(server, dict):
            enabled_in_config.append(name)
            continue
        if server.get("enabled", True):
            enabled_in_config.append(name)

    return sorted(enabled_in_config), available


def _sanitize_preferences(
    available_models: list[str],
    available_skills: list[str],
    available_mcp_servers: list[str],
    default_model: str,
    default_mcp: list[str],
) -> tuple[str, list[str], list[str]]:
    with _preferences_lock:
        selected_model = str(_preferences.get("selected_model", "")).strip()
        selected_skills = _preferences.get("selected_skills", [])
        selected_mcp_servers = _preferences.get("selected_mcp_servers", [])

    model = selected_model if selected_model in available_models else (default_model if default_model in available_models else "")
    if not model and available_models:
        model = available_models[0]

    valid_skills = set(available_skills)
    skills = [
        item for item in selected_skills
        if isinstance(item, str) and item in valid_skills
    ]

    valid_mcp = set(available_mcp_servers)
    mcp = [
        item for item in selected_mcp_servers
        if isinstance(item, str) and item in valid_mcp
    ]
    if not mcp:
        mcp = [item for item in default_mcp if item in valid_mcp]

    return model, sorted(set(skills)), sorted(set(mcp))


def set_runtime_preferences(
    selected_model: str | None = None,
    selected_skills: list[str] | None = None,
    selected_mcp_servers: list[str] | None = None,
) -> None:
    with _preferences_lock:
        if selected_model is not None:
            _preferences["selected_model"] = selected_model.strip()
        if selected_skills is not None:
            _preferences["selected_skills"] = selected_skills
        if selected_mcp_servers is not None:
            _preferences["selected_mcp_servers"] = selected_mcp_servers


def get_selected_model() -> str:
    runtime = build_runtime_state()
    return runtime.selected_model


def build_runtime_state() -> RuntimeState:
    config = _load_hermes_config()

    config_default_model, config_models, config_provider_map = _collect_models_from_config(config)
    env_model = os.getenv("HERMES_MODEL", "").strip()

    merged_models = set(config_models)
    if env_model:
        merged_models.add(env_model)
    if config_default_model:
        merged_models.add(config_default_model)

    available_models = sorted(merged_models)

    model_provider_map: dict[str, str] = {}
    for model_name in available_models:
        provider = config_provider_map.get(model_name) or _infer_provider_from_model_name(model_name)
        model_provider_map[model_name] = provider

    cli_skill_items = _collect_skill_items_from_hermes_cli()
    fs_skill_items = _collect_skill_items_from_filesystem()
    fs_desc_map = {item.name: item.description for item in fs_skill_items if item.description}

    merged_skill_map: dict[str, RuntimeSkillItem] = {}
    for item in cli_skill_items:
        merged_skill_map[item.name] = RuntimeSkillItem(
            name=item.name,
            description=fs_desc_map.get(item.name, item.description),
        )
    for item in fs_skill_items:
        if item.name not in merged_skill_map:
            merged_skill_map[item.name] = item

    skill_items = sorted(merged_skill_map.values(), key=lambda item: item.name)
    available_skills = [item.name for item in skill_items]

    enabled_mcp_in_config, available_mcp_servers = _collect_mcp(config)

    selected_model, selected_skills, selected_mcp_servers = _sanitize_preferences(
        available_models=available_models,
        available_skills=available_skills,
        available_mcp_servers=available_mcp_servers,
        default_model=config_default_model or env_model,
        default_mcp=enabled_mcp_in_config,
    )

    current_model = env_model or selected_model or config_default_model or "gpt-5.3-codex"

    if current_model and current_model not in available_models:
        available_models = sorted(set(available_models + [current_model]))
        model_provider_map[current_model] = model_provider_map.get(current_model) or _infer_provider_from_model_name(current_model)

    available_model_items = [
        RuntimeModelItem(name=model_name, provider=model_provider_map.get(model_name, ""))
        for model_name in available_models
    ]

    selected_model_resolved = selected_model or current_model
    selected_model_provider = model_provider_map.get(selected_model_resolved, "") or _infer_provider_from_model_name(selected_model_resolved)
    current_model_provider = model_provider_map.get(current_model, "") or _infer_provider_from_model_name(current_model)

    return RuntimeState(
        current_model=current_model,
        current_model_provider=current_model_provider,
        selected_model=selected_model_resolved,
        selected_model_provider=selected_model_provider,
        available_models=available_models,
        available_model_items=available_model_items,
        selected_skills=selected_skills,
        available_skills=available_skills,
        available_skill_items=skill_items,
        selected_mcp_servers=selected_mcp_servers,
        available_mcp_servers=available_mcp_servers,
    )

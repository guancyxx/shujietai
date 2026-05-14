from __future__ import annotations
import os
import re as _re
from pathlib import Path

import yaml as _yaml
from fastapi import APIRouter, HTTPException, Query

from app.schemas import RuntimePreferenceUpdateRequest
from app.services.hermes_runtime_catalog import build_runtime_state, invalidate_runtime_cache, set_runtime_preferences
from app.container import connector_registry

router = APIRouter(prefix="", tags=["skills"])


def _skill_base_dirs() -> tuple[Path, Path]:
    return (
        Path(os.getenv("HERMES_PERSONAL_SKILLS_DIR", "/home/guancy/.hermes/personal-skills")),
        Path(os.getenv("HERMES_SKILLS_DIR", "/home/guancy/.hermes/skills")),
    )


def _find_skill_markdown(skill_name: str) -> Path | None:
    safe_name = skill_name.strip().strip("/")
    if not safe_name or ".." in safe_name.split("/") or any(ch in safe_name for ch in "*?[]"):
        return None

    for base_dir in _skill_base_dirs():
        if not base_dir.exists():
            continue
        parts = safe_name.split("/", 1)
        candidates = []
        if len(parts) == 2:
            candidates.append(base_dir / parts[0] / parts[1] / "SKILL.md")
        candidates.append(base_dir / safe_name / "SKILL.md")
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        try:
            for found in base_dir.rglob(f"**/{safe_name}/SKILL.md"):
                if found.is_file():
                    return found
        except OSError:
            continue
    return None


def _normalize_string_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _extract_skill_summary(content: str, frontmatter_end: int) -> str:
    body = content[frontmatter_end:].strip() if frontmatter_end >= 0 else content.strip()
    clean_lines = [line.strip() for line in body.splitlines() if line.strip() and not line.strip().startswith("#")]
    summary = " ".join(clean_lines)
    return summary[:700]


@router.get("/api/v1/skills")
def get_skills_catalog():
    """Return all available skills grouped by provider."""
    runtime = build_runtime_state()
    skill_items = runtime.available_skill_items

    hermes_skills = []
    for item in skill_items:
        name = item.name
        category = name.split("/")[0] if "/" in name else "general"
        hermes_skills.append({
            "name": name,
            "description": item.description,
            "category": category,
            "skill_type": item.skill_type,
        })

    return {
        "providers": [
            {
                "id": "hermes",
                "label": "Hermes Agent",
                "skills": hermes_skills,
            }
        ],
        "total": len(hermes_skills),
    }


@router.get("/api/v1/skills/graph")
def get_skills_graph():
    """Return a node-link graph for the skill catalog."""
    skills_dir = Path(os.getenv("HERMES_SKILLS_DIR", "/home/guancy/.hermes/skills"))
    personal_dir = Path(os.getenv("HERMES_PERSONAL_SKILLS_DIR", "/home/guancy/.hermes/personal-skills"))

    cat_skills: dict[str, dict[str, list[str]]] = {}

    for base_dir in (personal_dir, skills_dir):
        if not base_dir.exists():
            continue
        for skill_md in base_dir.rglob("SKILL.md"):
            try:
                text = skill_md.read_text(encoding="utf-8")
            except Exception:
                continue
            m = _re.match(r"^---\n(.*?)\n---", text, _re.DOTALL)
            tags: list[str] = []
            name = ""
            if m:
                try:
                    fm = _yaml.safe_load(m.group(1)) or {}
                    name = fm.get("name", "")
                    tags = (
                        fm.get("tags")
                        or (fm.get("metadata") or {}).get("hermes", {}).get("tags", [])
                        or []
                    )
                    if not isinstance(tags, list):
                        tags = []
                except Exception:
                    pass
            try:
                rel = skill_md.relative_to(base_dir)
                parts = rel.parts
                if len(parts) >= 3:
                    category = parts[0]
                    skill_key = f"{parts[0]}/{parts[1]}"
                elif len(parts) == 2:
                    category = "general"
                    skill_key = parts[0]
                else:
                    category = "general"
                    skill_key = name or skill_md.parent.name
            except Exception:
                category = name.split("/")[0] if "/" in name else "general"
                skill_key = name or skill_md.parent.name
            if not name:
                name = skill_key
            cat_skills.setdefault(category, {})[skill_key] = tags

    nodes = []
    for cat, skills in sorted(cat_skills.items()):
        all_tags: set[str] = set()
        for t in skills.values():
            all_tags.update(t)
        nodes.append({
            "id": cat,
            "label": cat,
            "skill_count": len(skills),
            "tags": sorted(all_tags),
            "skills": [
                {"name": n, "tags": t}
                for n, t in sorted(skills.items())
            ],
        })

    node_tags = {n["id"]: set(n["tags"]) for n in nodes}
    edges = []
    node_ids = [n["id"] for n in nodes]
    for i, a in enumerate(node_ids):
        for b in node_ids[i + 1:]:
            shared = node_tags[a] & node_tags[b]
            if shared:
                edges.append({"source": a, "target": b, "weight": len(shared), "shared_tags": sorted(shared)})

    return {"nodes": nodes, "edges": edges}


@router.get("/api/v1/skills/{skill_name:path}/detail")
def get_skill_detail(skill_name: str):
    """Return parsed metadata and a compact summary for a SKILL.md file."""
    skill_md = _find_skill_markdown(skill_name)
    if skill_md is None:
        raise HTTPException(status_code=404, detail=f"SKILL.md not found for: {skill_name}")

    try:
        content = skill_md.read_text(encoding="utf-8")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    frontmatter: dict = {}
    frontmatter_end = -1
    match = _re.match(r"^---\n(.*?)\n---", content, _re.DOTALL)
    if match:
        frontmatter_end = match.end()
        try:
            loaded = _yaml.safe_load(match.group(1)) or {}
            if isinstance(loaded, dict):
                frontmatter = loaded
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Invalid skill frontmatter: {exc}") from exc

    rel_category = "general"
    for base_dir in _skill_base_dirs():
        try:
            rel = skill_md.relative_to(base_dir)
        except ValueError:
            continue
        if len(rel.parts) >= 3:
            rel_category = rel.parts[0]
        break

    metadata = frontmatter.get("metadata") if isinstance(frontmatter.get("metadata"), dict) else {}
    hermes_meta = metadata.get("hermes") if isinstance(metadata.get("hermes"), dict) else {}
    tags = _normalize_string_list(frontmatter.get("tags") or hermes_meta.get("tags"))
    related_skills = _normalize_string_list(
        frontmatter.get("related_skills")
        or frontmatter.get("requires_skills")
        or hermes_meta.get("related_skills")
    )

    return {
        "name": skill_name,
        "display_name": frontmatter.get("name") or skill_name,
        "description": frontmatter.get("description") or "",
        "category": rel_category,
        "tags": tags,
        "path": str(skill_md),
        "related_skills": related_skills,
        "skill_type": frontmatter.get("skill_type") or "unknown",
        "content_summary": _extract_skill_summary(content, frontmatter_end),
    }


@router.get("/api/v1/skills/{skill_name:path}/content")
def get_skill_content(skill_name: str):
    """Return the raw SKILL.md content for a given skill name."""
    skill_md = _find_skill_markdown(skill_name)
    if skill_md is None:
        raise HTTPException(status_code=404, detail=f"SKILL.md not found for: {skill_name}")
    try:
        content = skill_md.read_text(encoding="utf-8")
        return {"name": skill_name, "content": content, "path": str(skill_md)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/v1/runtime/catalog")
def get_runtime_catalog(platform: str = Query(default="hermes")):
    normalized_platform = (platform or "hermes").strip() or "hermes"
    available_platforms = connector_registry.names()
    if normalized_platform not in available_platforms:
        raise HTTPException(status_code=404, detail="platform_not_supported")

    runtime = build_runtime_state()
    runtime_dict = runtime.model_dump()
    runtime_dict["platform"] = normalized_platform
    runtime_dict["available_platforms"] = available_platforms
    return runtime_dict


@router.put("/api/v1/runtime/preferences")
def update_runtime_preferences(payload: RuntimePreferenceUpdateRequest):
    set_runtime_preferences(
        selected_model=payload.selected_model,
        selected_skills=payload.selected_skills,
        selected_mcp_servers=payload.selected_mcp_servers,
    )
    invalidate_runtime_cache()
    return build_runtime_state().model_dump()

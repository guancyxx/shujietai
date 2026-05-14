from __future__ import annotations
from fastapi import APIRouter, HTTPException

from app.schemas import (
    GitHubRepoCreateRequest,
    GitHubRepoOption,
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectUpdateRequest,
)
from app.container import store, system_config_service, github_project_service

router = APIRouter(prefix="", tags=["projects"])


@router.get("/api/v1/projects/github/repos", response_model=list[GitHubRepoOption])
def list_github_repositories() -> list[GitHubRepoOption]:
    try:
        token = system_config_service.get_github_token()
        return github_project_service.list_repositories(token_override=token)
    except RuntimeError as exc:
        detail = str(exc)
        if detail in {"gh_cli_unavailable", "github_api_failed"}:
            raise HTTPException(status_code=503, detail=detail) from exc
        raise HTTPException(status_code=502, detail=detail) from exc


@router.post("/api/v1/projects/github/repos", response_model=GitHubRepoOption)
def create_github_repository(payload: GitHubRepoCreateRequest) -> GitHubRepoOption:
    try:
        token = system_config_service.get_github_token()
        try:
            return github_project_service.create_repository(payload, token_override=token)
        except TypeError as exc:
            if "token_override" not in str(exc):
                raise
            return github_project_service.create_repository(payload)
    except RuntimeError as exc:
        detail = str(exc)
        if detail in {"gh_cli_unavailable", "github_repo_create_unavailable"}:
            raise HTTPException(status_code=503, detail=detail) from exc
        raise HTTPException(status_code=502, detail=detail) from exc


@router.get("/api/v1/projects", response_model=ProjectListResponse)
def list_projects() -> ProjectListResponse:
    return ProjectListResponse(items=store.list_projects())


@router.post("/api/v1/projects")
def create_project(payload: ProjectCreateRequest):
    try:
        return store.create_project(payload)
    except ValueError as exc:
        detail = str(exc)
        if detail in {"invalid_github_repository_url", "local_path_outside_workspace"}:
            raise HTTPException(status_code=422, detail=detail) from exc
        raise


@router.patch("/api/v1/projects/{project_id}")
def update_project(project_id: str, payload: ProjectUpdateRequest):
    item = store.update_project(project_id, payload)
    if item is None:
        raise HTTPException(status_code=404, detail="project_not_found")
    return item


@router.delete("/api/v1/projects/{project_id}")
def delete_project(project_id: str):
    deleted = store.delete_project(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="project_not_found")
    return {"deleted": 1, "project_id": project_id}

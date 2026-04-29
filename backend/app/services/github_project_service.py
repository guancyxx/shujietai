from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from app.schemas import GitHubRepoCreateRequest, GitHubRepoOption


class GitHubProjectService:
    def __init__(self) -> None:
        self._http_pattern = re.compile(r"^https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$")
        self._ssh_pattern = re.compile(r"^git@github\.com:(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?$")

    def _workspace_root(self) -> Path:
        return Path(os.getenv("WORKSPACE_ROOT", "/home/guancy/workspace")).resolve()

    def _run_command(self, command: list[str]) -> str:
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:
            if command and command[0] == "gh":
                raise RuntimeError("gh_cli_unavailable") from exc
            if command and command[0] == "git":
                raise RuntimeError("git_cli_unavailable") from exc
            raise

        if result.returncode != 0:
            if command and command[0] == "gh":
                raise RuntimeError("gh_command_failed")
            if command and command[0] == "git":
                raise RuntimeError("git_command_failed")
            raise RuntimeError("command_failed")
        return result.stdout.strip()

    def _gh_command(self) -> list[str] | None:
        if shutil.which("gh"):
            return ["gh"]

        token = os.getenv("GITHUB_TOKEN", "").strip()
        if token:
            return ["gh", "auth", "login", "--with-token"]
        return None

    def _list_with_gh(self) -> list[GitHubRepoOption]:
        output = self._run_command(["gh", "repo", "list", "--limit", "200", "--json", "name,nameWithOwner,url,description"])
        if not output:
            return []
        rows = json.loads(output)
        items: list[GitHubRepoOption] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            full_name = str(row.get("nameWithOwner") or "").strip()
            url = str(row.get("url") or "").strip()
            description = str(row.get("description") or "").strip()
            if not name or not full_name or not url:
                continue
            items.append(GitHubRepoOption(name=name, full_name=full_name, url=url, description=description))
        return items

    def _list_with_token(self, token: str) -> list[GitHubRepoOption]:
        import httpx

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        items: list[GitHubRepoOption] = []
        page = 1
        while page <= 4:
            response = httpx.get(
                "https://api.github.com/user/repos",
                params={"per_page": 100, "page": page, "sort": "updated"},
                headers=headers,
                timeout=20,
            )
            if response.status_code >= 400:
                raise RuntimeError("github_api_failed")
            rows = response.json()
            if not isinstance(rows, list) or len(rows) == 0:
                break
            for row in rows:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("name") or "").strip()
                full_name = str(row.get("full_name") or "").strip()
                url = str(row.get("html_url") or "").strip()
                description = str(row.get("description") or "").strip()
                if not name or not full_name or not url:
                    continue
                items.append(GitHubRepoOption(name=name, full_name=full_name, url=url, description=description))
            if len(rows) < 100:
                break
            page += 1
        return items

    def _list_public_by_owner(self, owner: str) -> list[GitHubRepoOption]:
        import httpx

        response = httpx.get(
            f"https://api.github.com/users/{owner}/repos",
            params={"per_page": 100, "sort": "updated"},
            headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
            timeout=20,
        )
        if response.status_code >= 400:
            raise RuntimeError("github_api_failed")

        rows = response.json()
        if not isinstance(rows, list):
            return []

        items: list[GitHubRepoOption] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            full_name = str(row.get("full_name") or "").strip()
            url = str(row.get("html_url") or "").strip()
            description = str(row.get("description") or "").strip()
            if not name or not full_name or not url:
                continue
            items.append(GitHubRepoOption(name=name, full_name=full_name, url=url, description=description))
        return items

    def list_repositories(self, token_override: str = "") -> list[GitHubRepoOption]:
        try:
            return self._list_with_gh()
        except (RuntimeError, json.JSONDecodeError):
            token = token_override.strip() or os.getenv("GITHUB_TOKEN", "").strip()
            if token:
                return self._list_with_token(token)

            owner = os.getenv("GITHUB_OWNER", "").strip()
            if owner:
                return self._list_public_by_owner(owner)
            return []

    def parse_repository_url(self, repository_url: str) -> tuple[str, str]:
        value = repository_url.strip()
        http_match = self._http_pattern.match(value)
        if http_match is not None:
            return http_match.group("owner"), http_match.group("repo")

        ssh_match = self._ssh_pattern.match(value)
        if ssh_match is not None:
            return ssh_match.group("owner"), ssh_match.group("repo")

        raise ValueError("invalid_github_repository_url")

    def create_repository(self, payload: GitHubRepoCreateRequest) -> GitHubRepoOption:
        command = [
            "gh",
            "api",
            "user/repos",
            "-f",
            f"name={payload.name.strip()}",
            "-f",
            f"description={payload.description.strip()}",
            "-F",
            f"private={'true' if payload.private else 'false'}",
        ]
        output = self._run_command(command)

        row = json.loads(output)
        name = str(row.get("name") or "").strip()
        full_name = str(row.get("full_name") or "").strip()
        url = str(row.get("html_url") or "").strip()
        description = str(row.get("description") or "").strip()
        if not name or not full_name or not url:
            raise RuntimeError("gh_repo_create_failed")
        return GitHubRepoOption(name=name, full_name=full_name, url=url, description=description)

    def default_local_path(self, repository_url: str) -> str:
        _owner, repo = self.parse_repository_url(repository_url)
        workspace_root = self._workspace_root()
        local_path = (workspace_root / repo).resolve()
        try:
            local_path.relative_to(workspace_root)
        except ValueError as exc:
            raise ValueError("local_path_outside_workspace") from exc
        return str(local_path)
